from __future__ import annotations

from rednote_matrix.agents.utils import append_revision
from rednote_matrix.core.models import AgentInput, MarketResearchContext
from rednote_matrix.integrations.xhs_core import (
    build_default_keywords,
    check_xhs_auth,
    check_xhs_environment,
    search_xhs_keywords,
    start_qrcode_login_process,
)


def run_market_research_agent(state: dict) -> dict:
    user_input = AgentInput.model_validate(state["user_input"])
    if not user_input.enable_realtime_research:
        context = MarketResearchContext(enabled=False, status="disabled", message="用户未启用实时爆款检索")
        return {
            **state,
            "market_research_context": context.model_dump(),
            "revision_history": append_revision(state, "market_research_agent", "skipped", [context.message]),
        }

    keywords = user_input.realtime_research_keywords or build_default_keywords(user_input)
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

    auth = check_xhs_auth()
    if not auth.available:
        session = start_qrcode_login_process(headless=False, use_virtual_display=True)
        status = "needs_login" if session.session_id else "error"
        qrcode_url = f"/integrations/xhs/login/{session.session_id}/qrcode" if session.session_id else ""
        context = MarketResearchContext(
            enabled=True,
            status=status,
            keywords=keywords,
            login_session_id=session.session_id,
            qrcode_path=session.qrcode_path,
            qrcode_url=qrcode_url,
            message=f"{auth.message}，{session.message or '已尝试启动二维码登录会话'}",
        )
        return {
            **state,
            "market_research_context": context.model_dump(),
            "revision_history": append_revision(
                state,
                "market_research_agent",
                status,
                [context.message, f"二维码接口：{qrcode_url or '未生成'}"],
            ),
        }

    result = search_xhs_keywords(
        keywords=keywords,
        max_notes_count=user_input.realtime_research_max_notes,
        headless=True,
        execute=True,
    )
    allowed_statuses = {"completed", "needs_login", "unconfigured", "verification_required", "error", "ready"}
    status = result.status if result.status in allowed_statuses else "error"
    context = MarketResearchContext(
        enabled=True,
        status=status,
        keywords=keywords,
        message=result.message,
        output_dir=result.output_dir,
        notes=result.notes,
    )
    return {
        **state,
        "market_research_context": context.model_dump(),
        "revision_history": append_revision(
            state,
            "market_research_agent",
            status,
            [result.message or "完成实时爆款检索", f"读取笔记 {len(result.notes)} 条"],
        ),
    }
