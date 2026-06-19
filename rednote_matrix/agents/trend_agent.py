from __future__ import annotations

from rednote_matrix.agents.utils import append_revision
from rednote_matrix.core.models import AgentInput, MarketResearchContext, ParsedUserInput
from rednote_matrix.skills.xiaohongshu import build_trend_insight


def _short_text(text: str, limit: int = 36) -> str:
    text = " ".join(str(text).split())
    return text[:limit] if len(text) > limit else text


def run_trend_agent(state: dict) -> dict:
    user_input = AgentInput.model_validate(state["user_input"])
    parsed = ParsedUserInput.model_validate(state.get("parsed_input") or {})
    market_context = MarketResearchContext.model_validate(state.get("market_research_context") or {})

    # 用 parsed 的字段覆盖 user_input（input_parser 已合并到 user_input，这里保底）
    merged_input = user_input.model_copy()
    if parsed.product_name and not merged_input.product_name:
        merged_input.product_name = parsed.product_name
    if parsed.selling_points and not merged_input.selling_points:
        merged_input.selling_points = parsed.selling_points
    if parsed.target_audience and not merged_input.target_audience:
        merged_input.target_audience = parsed.target_audience
    if parsed.scenario and not merged_input.scenario:
        merged_input.scenario = parsed.scenario

    insight = build_trend_insight(merged_input)

    # 融合实时爬取的爆款笔记
    realtime_notes = market_context.notes[:5]
    if realtime_notes:
        realtime_titles = [_short_text(note.title) for note in realtime_notes if note.title]
        insight.title_patterns = [*realtime_titles, *insight.title_patterns]
        insight.content_structures = [
            "参考实时高互动笔记：先复用其情绪/场景入口，再改写为当前商品的真实体验",
            *insight.content_structures,
        ]
        insight.opening_hooks = [
            "从实时爆款笔记中抽取同类人群的具体处境，不照搬标题和正文",
            *insight.opening_hooks,
        ]
        insight.scoring_dimensions["时效性"] = min(100, max(insight.scoring_dimensions.get("时效性", 65), 88))
        insight.source = f"{insight.source}+xhs_core_realtime"
    trend_score = round(sum(insight.scoring_dimensions.values()) / len(insight.scoring_dimensions))

    realtime_note = "实时爆款检索未启用或未拿到可用结果"
    if market_context.status == "completed":
        realtime_note = f"吸收小红书实时高互动笔记 {len(realtime_notes)} 条"
    elif market_context.status in {"needs_login", "unconfigured", "verification_required", "error"}:
        realtime_note = f"实时爆款检索状态：{market_context.status}，{market_context.message}"

    return {
        **state,
        "trend_insight": insight.model_dump(),
        "trend_score": trend_score,
        "revision_history": append_revision(
            state,
            "trend_agent",
            "adapted_skill",
            [
                "吸收项目内置小红书标题/正文/标签方法论",
                realtime_note,
            ],
        ),
    }
