from __future__ import annotations

from collections.abc import Callable
from typing import Any

from rednote_matrix.agents.utils import append_revision
from rednote_matrix.core.models import AgentInput, MarketResearchContext
from rednote_matrix.integrations.xhs_core import (
    build_default_keywords,
    check_xhs_environment,
    search_xhs_keywords,
)


def run_market_research_agent(state: dict) -> dict:
    return _run_market_research_agent(state)


def run_market_research_agent_stream(
    state: dict,
    on_note: Callable[[dict[str, Any]], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> dict:
    return _run_market_research_agent(state, on_note=on_note, should_stop=should_stop)


def _run_market_research_agent(
    state: dict,
    on_note: Callable[[dict[str, Any]], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> dict:
    user_input = AgentInput.model_validate(state["user_input"])

    if not user_input.enable_realtime_research:
        context = MarketResearchContext(enabled=False, status="disabled", message="用户未启用实时爆款检索")
        return {
            **state,
            "market_research_context": context.model_dump(),
            "revision_history": append_revision(state, "market_research_agent", "skipped", [context.message]),
        }

    # 多轮会话是否跳过爬虫由显式状态控制，不能仅因有历史对话就跳过。
    if user_input.research_completed:
        context = MarketResearchContext(
            enabled=True,
            status="completed",
            message="本会话已完成爆款检索，后续轮次跳过爬虫",
            keywords=user_input.realtime_research_keywords,
        )
        return {
            **state,
            "market_research_context": context.model_dump(),
            "revision_history": append_revision(state, "market_research_agent", "skipped", [context.message]),
        }

    # 首轮：准备关键词
    keywords = user_input.realtime_research_keywords or build_default_keywords(user_input)

    # 检查环境
    env = check_xhs_environment(deep=False)
    if not env.configured:
        context = MarketResearchContext(
            enabled=True,
            status="unconfigured",
            keywords=keywords,
            message="小红书核心环境未就绪：" + ("；".join(env.errors) or "未知错误"),
        )
        return {
            **state,
            "market_research_context": context.model_dump(),
            "revision_history": append_revision(state, "market_research_agent", "unconfigured", [context.message]),
        }

    # search_xhs_keywords 负责两阶段登录：未登录时只打开 Chrome 登录窗口，不执行搜索。
    result = search_xhs_keywords(
        keywords=keywords,
        max_notes_count=user_input.realtime_research_max_notes,
        headless=False,
        execute=True,
        on_note=on_note,
        should_stop=should_stop,
    )
    allowed_statuses = {"completed", "needs_login", "unconfigured", "verification_required", "error", "ready"}
    status = result.status if result.status in allowed_statuses else "error"

    # 标记首轮爬取完成（搜索结果不论成败，后续不再爬）
    updated_input = {**state["user_input"], "research_completed": True}
    context = MarketResearchContext(
        enabled=True,
        status=status,
        keywords=keywords,
        message=result.message,
        login_session_id=result.login_session_id,
        qrcode_path=result.qrcode_path,
        qrcode_url=result.qrcode_url,
        output_dir=result.output_dir,
        notes=result.notes,
    )
    return {
        **state,
        "user_input": updated_input,
        "market_research_context": context.model_dump(),
        "revision_history": append_revision(
            state,
            "market_research_agent",
            status,
            [result.message or "完成实时爆款检索", f"读取笔记 {len(result.notes)} 条"],
        ),
    }
