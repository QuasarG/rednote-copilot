from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import patch

from rednote_matrix.rules.xhs_rules import SAFE_REPLACEMENTS


def _draft_from_payload(payload: dict) -> dict:
    product = str(payload.get("product_name") or "产品")
    selling_points = [str(item) for item in payload.get("selling_points") or ["日常使用方便"]]
    target = str(payload.get("target_audience") or "想省心做选择的人")
    scenario = str(payload.get("scenario") or "日常使用")
    viral_rules = payload.get("viral_rules") or {}
    price_policy = payload.get("price_policy") or {}
    price_line = ""
    if price_policy.get("allow_price_in_body") and payload.get("price"):
        price_line = f"\n价格大概 {payload.get('price')}，我会把它当作预算参考，不当成主要判断。"
    viral_notes = [str(item) for item in viral_rules.get("rules", [])[:3] if item]
    memory_context = payload.get("memory_context") or {}
    facts = [
        item.get("content", "")
        for item in memory_context.get("product_facts", [])
        if isinstance(item, dict) and item.get("content")
    ]
    writing_rules = [
        item.get("content", "")
        for item in memory_context.get("writing_rules", [])
        if isinstance(item, dict) and item.get("content")
    ]
    fact_line = f"\n补充事实：{'；'.join(facts[:2])}" if facts else ""
    rule_line = f"\n写作细则：{'；'.join(writing_rules[:2])}" if writing_rules else ""
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
            f"所以我比较在意：{selling_line}。{fact_line}{rule_line}\n"
            f"{price_line}"
            f"如果你也是{target}，可以先看它是不是能减少一点选择负担。"
        ),
        "tags": ["真实体验", "选购建议", "避坑指南", scenario, product],
        "structure_type": "痛点-细节-避坑",
        "structure_notes": viral_notes or ["场景痛点", "真实体验", "避坑收尾"],
    }


def _sanitize_text(text: str, risk_items: list[dict], allow_price: bool = False) -> str:
    updated = str(text)
    for risk in risk_items:
        bad = str(risk.get("text") or "")
        if not bad:
            continue
        replacement = SAFE_REPLACEMENTS.get(bad, "")
        updated = updated.replace(bad, replacement)
    for bad, replacement in sorted(SAFE_REPLACEMENTS.items(), key=lambda item: len(item[0]), reverse=True):
        updated = updated.replace(bad, replacement)
    if not allow_price:
        updated = updated.replace("39 元", "").replace("39元", "").replace("售价", "")
    return updated.strip()


def _humanized_from_payload(payload: dict) -> dict:
    draft = dict(payload.get("draft") or {})
    risk_items = payload.get("risk_items") or []
    price_policy = payload.get("price_policy") or {}
    allow_price = bool(price_policy.get("allow_price_in_body"))
    if not risk_items:
        return draft
    updated = {}
    for key, value in draft.items():
        if isinstance(value, str):
            updated[key] = _sanitize_text(value, risk_items, allow_price)
        elif isinstance(value, list):
            updated[key] = [_sanitize_text(item, risk_items, allow_price) if isinstance(item, str) else item for item in value]
        else:
            updated[key] = value
    return updated


def _parsed_from_payload(payload: dict) -> dict:
    raw = str(payload.get("当前输入") or "")
    product = ""
    if "桌面收纳" in raw:
        product = "桌面收纳托盘"
    elif "厨房油污" in raw or "清洁湿巾" in raw:
        product = "厨房油污清洁湿巾"
    selling_points = []
    if "小桌面" in raw or "桌面小" in raw:
        selling_points.append("小桌面也能放下")
    if "拿东西" in raw or "方便" in raw:
        selling_points.append("拿东西方便")
    if "颜色" in raw or "不突兀" in raw:
        selling_points.append("颜色不突兀")
    if "顺手擦" in raw or "擦一下" in raw:
        selling_points.append("做完饭顺手擦一下")
    if "手套" in raw:
        selling_points.append("不用戴手套刷半天")
    price = ""
    if "29.9" in raw:
        price = "29.9元一包"
    elif "价格" in raw:
        price = str(payload.get("已知信息（如为空则是首轮）", {}).get("已提取价格") or "")
    return {
        "product_name": product,
        "brand_name": "CleanMint" if "CleanMint" in raw else "",
        "price": price,
        "selling_points": selling_points,
        "target_audience": "租房小桌面用户" if "租房" in raw and "桌面" in raw else ("经常做饭的租房女生" if "租房女生" in raw else ""),
        "scenario": "桌面收纳" if "桌面" in raw else ("厨房清洁" if "厨房" in raw else ""),
        "account_persona": "",
        "tone": "自然、可信、轻种草",
        "custom_prompt": raw,
        "forbidden_words": [],
        "realtime_research_keywords": [
            f"{product or '小红书'} 爆款笔记",
            f"{product or '小红书'} 真实体验",
            f"{product or '小红书'} 避坑",
        ],
        "memory_namespace": product,
    }


def mock_call_llm_json(system_prompt: str, user_payload: dict, temperature: float = 0.4) -> dict:
    if "输入解析 Agent" in system_prompt:
        return _parsed_from_payload(user_payload)
    if "结构 Agent" in system_prompt:
        return _draft_from_payload(user_payload)
    if "真人网感改写 Agent" in system_prompt:
        return _humanized_from_payload(user_payload)
    raise AssertionError(f"unexpected LLM prompt: {system_prompt[:80]}")


@contextmanager
def mock_agent_llm():
    with (
        patch("rednote_matrix.agents.input_parser.call_llm_json", side_effect=mock_call_llm_json),
        patch("rednote_matrix.agents.structure_agent.call_llm_json", side_effect=mock_call_llm_json),
        patch("rednote_matrix.agents.humanizer_agent.call_llm_json", side_effect=mock_call_llm_json),
    ):
        yield
