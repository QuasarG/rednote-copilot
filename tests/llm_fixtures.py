from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import patch

from rednote_matrix.rules.xhs_rules import SAFE_REPLACEMENTS


def _draft_from_payload(payload: dict) -> dict:
    product = str(payload.get("product_name") or "产品")
    selling_points = [str(item) for item in payload.get("selling_points") or ["日常使用方便"]]
    target = str(payload.get("target_audience") or "想省心做选择的人")
    scenario = str(payload.get("scenario") or "日常使用")
    memory_context = payload.get("memory_context") or {}
    facts = [
        item.get("content", "")
        for item in memory_context.get("product_facts", [])
        if isinstance(item, dict) and item.get("content")
    ]
    fact_line = f"\n补充事实：{'；'.join(facts[:2])}" if facts else ""
    selling_line = "、".join(selling_points)
    return {
        "titles": [
            f"{scenario}里试了{product}，我先看这几个细节",
            f"{target}选{product}，别只看表面卖点",
        ],
        "cover_text": f"{product}先看适不适合你",
        "hook": f"一开始我也只是被{selling_points[0]}吸引，真正放到{scenario}里才发现细节更重要。",
        "body": (
            f"我不是一开始就被{product}说服的。\n"
            f"主要是{scenario}这个场景太频繁，想省点心，又怕选错。\n"
            f"所以我比较在意：{selling_line}。{fact_line}\n"
            f"如果你也是{target}，可以先看它是不是能减少一点选择负担。"
        ),
        "tags": ["真实体验", "选购建议", "避坑指南", scenario, product],
        "structure_type": "痛点-细节-避坑",
        "structure_notes": ["场景痛点", "真实体验", "避坑收尾"],
    }


def _sanitize_text(text: str, risk_items: list[dict]) -> str:
    updated = str(text)
    for risk in risk_items:
        bad = str(risk.get("text") or "")
        if not bad:
            continue
        replacement = SAFE_REPLACEMENTS.get(bad, "")
        updated = updated.replace(bad, replacement)
    for bad, replacement in sorted(SAFE_REPLACEMENTS.items(), key=lambda item: len(item[0]), reverse=True):
        updated = updated.replace(bad, replacement)
    return updated.replace("39 元", "").replace("39元", "").replace("售价", "").strip()


def _humanized_from_payload(payload: dict) -> dict:
    draft = dict(payload.get("draft") or {})
    risk_items = payload.get("risk_items") or []
    if not risk_items:
        return draft
    updated = {}
    for key, value in draft.items():
        if isinstance(value, str):
            updated[key] = _sanitize_text(value, risk_items)
        elif isinstance(value, list):
            updated[key] = [_sanitize_text(item, risk_items) if isinstance(item, str) else item for item in value]
        else:
            updated[key] = value
    return updated


def mock_call_llm_json(system_prompt: str, user_payload: dict, temperature: float = 0.4) -> dict:
    if "结构 Agent" in system_prompt:
        return _draft_from_payload(user_payload)
    if "真人网感改写 Agent" in system_prompt:
        return _humanized_from_payload(user_payload)
    raise AssertionError(f"unexpected LLM prompt: {system_prompt[:80]}")


@contextmanager
def mock_agent_llm():
    with (
        patch("rednote_matrix.agents.structure_agent.call_llm_json", side_effect=mock_call_llm_json),
        patch("rednote_matrix.agents.humanizer_agent.call_llm_json", side_effect=mock_call_llm_json),
    ):
        yield
