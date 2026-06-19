from __future__ import annotations

import re

from rednote_matrix.agents.utils import append_revision, draft_from_state
from rednote_matrix.core.models import MemoryContext, RiskItem
from rednote_matrix.rules.xhs_rules import (
    AD_STYLE_MARKERS,
    AI_STYLE_MARKERS,
    EXTREME_CLAIM_WORDS,
    HARD_SELL_WORDS,
)


def _collect_text(draft) -> str:
    return "\n".join(
        [
            *draft.titles,
            draft.cover_text,
            draft.hook,
            draft.body,
            " ".join(draft.tags),
        ]
    )


def _price_mentions(text: str) -> list[str]:
    patterns = [
        r"(售价|价格|到手价|入手价|活动价|原价|现价)\s*[：:]?\s*\d+(?:\.\d+)?\s*(?:元|块|rmb|RMB)?",
        r"\d+(?:\.\d+)?\s*(?:元|块|rmb|RMB)",
    ]
    hits: list[str] = []
    for pattern in patterns:
        hits.extend(match.group(0) for match in re.finditer(pattern, text, flags=re.I))
    return list(dict.fromkeys(hit.strip() for hit in hits if hit.strip()))


def _allow_price_in_copy(user_input: dict) -> bool:
    price_text = str(user_input.get("price") or "").strip()
    if not price_text:
        return False
    intent_text = f"{user_input.get('current_message') or ''}\n{user_input.get('custom_prompt') or ''}".lower()
    return any(keyword in intent_text for keyword in ("加上价格", "加入价格", "写价格", "带价格", "标价格", "价格"))


def run_compliance_agent(state: dict) -> dict:
    draft = draft_from_state(state)
    text = _collect_text(draft)
    user_input = state.get("user_input") or {}
    memory_context = MemoryContext.model_validate(state.get("memory_context") or {})
    custom_forbidden = user_input.get("forbidden_words") or []
    risks: list[RiskItem] = []

    for word in EXTREME_CLAIM_WORDS:
        if word in text:
            risks.append(
                RiskItem(
                    type="extreme_claim",
                    text=word,
                    reason="可能触发广告法或平台夸大承诺风险",
                    suggestion="改成主观体验或弱承诺表达",
                    severity="high",
                )
            )

    for word in HARD_SELL_WORDS:
        if word in text:
            risks.append(
                RiskItem(
                    type="hard_sell",
                    text=word,
                    reason="硬广或导流表达可能降低推荐和审核通过率",
                    suggestion="改成平台内自然咨询或体验描述",
                    severity="medium",
                )
            )

    if not _allow_price_in_copy(user_input):
        for mention in _price_mentions(text):
            risks.append(
                RiskItem(
                    type="price_mention",
                    text=mention,
                    reason="最终文案外显具体价格会增强交易和硬广感，可能增加审核风险",
                    suggestion="删除具体价格，改成预算友好、价格不高、先看预算等弱表达",
                    severity="medium",
                )
            )

    for marker in AD_STYLE_MARKERS:
        if marker in text:
            risks.append(
                RiskItem(
                    type="ad_style",
                    text=marker,
                    reason="表达偏营销号或品牌广告，削弱真人分享感",
                    suggestion="改成犹豫、试用过程、个人限制或弱结论",
                    severity="medium",
                )
            )

    for word in custom_forbidden:
        if word and word in text:
            risks.append(
                RiskItem(
                    type="custom_forbidden",
                    text=word,
                    reason="命中用户配置的品牌或行业禁用词",
                    suggestion="替换为更中性的描述",
                    severity="high",
                )
            )

    for rule in memory_context.risk_rules:
        rule_words = [part.strip() for part in rule.content.replace("，", ",").replace("、", ",").split(",") if part.strip()]
        for word in rule_words:
            if word and word in text:
                risks.append(
                    RiskItem(
                        type="memory_risk_rule",
                        text=word,
                        reason=f"命中记忆库风险规则：{rule.title}",
                        suggestion="按品牌/平台记忆规则替换为更中性的表达",
                        severity="high",
                    )
                )

    for rule in memory_context.writing_rules:
        if rule.kind != "fact_boundary":
            continue
        rule_words = [part.strip() for part in rule.content.replace("，", ",").replace("、", ",").split(",") if part.strip()]
        for word in rule_words:
            if word and word in text:
                risks.append(
                    RiskItem(
                        type="memory_fact_boundary",
                        text=word,
                        reason=f"命中事实边界记忆：{rule.title}",
                        suggestion="删除或改成未亲测的观察/筛选/关注点表达",
                        severity="medium",
                    )
                )

    ai_hits = [marker for marker in AI_STYLE_MARKERS if marker in text]
    for marker in ai_hits:
        risks.append(
            RiskItem(
                type="ai_trace",
                text=marker,
                reason="表达偏模板化，可能降低真实感",
                suggestion="改成具体体验、场景细节或个人感受",
                severity="low",
            )
        )

    compliance_score = max(0, 100 - sum(22 if risk.severity == "high" else 12 if risk.severity == "medium" else 6 for risk in risks))
    ai_trace_score = min(100, state.get("ai_trace_score", 40) + len(ai_hits) * 10)

    has_blocking_risk = any(risk.severity in {"high", "medium"} for risk in risks)
    if has_blocking_risk or compliance_score < 80:
        route_reason = "compliance_reject"
    elif ai_trace_score > 60:
        route_reason = "ai_trace_reject"
    elif state.get("structure_score", 0) < 70:
        route_reason = "structure_reject"
    else:
        route_reason = "pass"

    return {
        **state,
        "risk_items": [risk.model_dump() for risk in risks],
        "compliance_score": compliance_score,
        "ai_trace_score": ai_trace_score,
        "route_reason": route_reason,
        "revision_history": append_revision(
            state,
            "compliance_agent",
            "checked",
            [f"合规分 {compliance_score}", f"AI痕迹分 {ai_trace_score}", f"路由 {route_reason}"],
        ),
    }
