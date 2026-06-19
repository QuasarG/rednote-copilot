from __future__ import annotations

from rednote_matrix.agents.utils import append_revision, draft_from_state
from rednote_matrix.core.models import AgentResult, MarketResearchContext, MemoryContext, RevisionRecord, RiskItem, TrendInsight


def _build_checklist(state: dict) -> list[str]:
    risk_items = [RiskItem.model_validate(item) for item in state.get("risk_items") or []]
    checklist = [
        "标题包含搜索词和点击钩子，但不使用极限承诺",
        "正文保留具体场景、主观体验和避坑提醒",
        "发布前复查品牌禁用词、医疗功效词和导流表达",
    ]
    if risk_items:
        checklist.append("仍有风险项，发布前按建议人工复核")
    else:
        checklist.append("未发现高风险词或明显模板腔，可进入人工终审")
    return checklist


def run_final_packager(state: dict) -> dict:
    draft = draft_from_state(state)
    risks = [RiskItem.model_validate(item) for item in state.get("risk_items") or []]
    high_or_medium_risks = [risk for risk in risks if risk.severity in {"high", "medium"}]
    route_reason = state.get("route_reason", "")
    forced_stop = route_reason != "pass" and state.get("loop_count", 0) >= 2
    status = "needs_review" if high_or_medium_risks or forced_stop else "pass"

    revision_history = append_revision(
        state,
        "final_packager",
        "packaged",
        [f"最终状态 {status}", f"风险项 {len(risks)}"],
    )
    result = AgentResult(
        status=status,
        draft=draft,
        resolved_user_input=state.get("user_input") or {},
        structure_score=int(state.get("structure_score", 0)),
        human_score=int(state.get("human_score", 0)),
        compliance_score=int(state.get("compliance_score", 0)),
        ai_trace_score=int(state.get("ai_trace_score", 0)),
        trend_score=int(state.get("trend_score", 0)),
        trend_insight=TrendInsight.model_validate(state.get("trend_insight") or {}),
        market_research_context=MarketResearchContext.model_validate(state.get("market_research_context") or {}),
        memory_context=MemoryContext.model_validate(state.get("memory_context") or {}),
        route_reason=str(state.get("route_reason", "")),
        loop_count=int(state.get("loop_count", 0)),
        risk_items=risks,
        revision_history=[RevisionRecord.model_validate(item) for item in revision_history],
        publish_checklist=_build_checklist({**state, "risk_items": [risk.model_dump() for risk in risks]}),
    )

    return {
        **state,
        "revision_history": revision_history,
        "final_output": result.model_dump(),
    }
