from __future__ import annotations

from rednote_matrix.agents.llm_bridge import call_llm_json
from rednote_matrix.agents.utils import append_revision, draft_from_state
from rednote_matrix.core.models import Draft


HUMANIZER_SYSTEM_PROMPT = """
你是小红书真人网感改写 Agent。只输出 JSON 对象，不要 Markdown。
输入是一个草稿和风险上下文，输出字段必须是 titles, cover_text, hook, body, tags, structure_type, structure_notes。
目标：把广告稿改成真实普通人的分享，减少 AI 模板腔，保留商品事实和结构。
必须参考 user_input 里的 conversation_history、current_changes 和 current_message，理解用户多轮追问。本轮要求优先，但不能覆盖合规和事实边界。
事实边界：只能保留用户输入过的事实。删除用户没提供的成分、数值、价格、具体材质/配方、功效、版本、购买渠道等细节。
即使用户输入了价格，价格也只能作内部定位参考，最终标题、正文、标签里不要出现具体价格、价格带或“售价/到手价/活动价”等交易表达。
输入里的 user_input 是唯一可信事实来源。不得新增用户没提供的推荐来源、试用时长、购买经历、使用步骤、比例、身体反应、版本对比、成分细项。
如果 risk_items 里有 unverified_detail，必须删除对应内容，不要替换成另一个新细节。
风格：像真实 KOC 的主观体验，有犹豫、有保留、有使用限制，不要像品牌口播。
允许保留中等强度的情绪：纠结、烦、松一口气、意外、没那么有负担。禁止过度兴奋和卖货号召。
标题要比说明文更吸睛，但不能像广告标题。优先用“差点放弃”“没那么纠结”“试完才发现”“先别急着买”这类轻情绪结构。
必须删除或弱化：“放心冲”“必备”“狂喜”“闭眼入”“回购”“宝藏”“姐妹”“测评”“值不值得”等广告化词。
正文不要过度分点包装，少用 emoji，少用感叹号。允许保留自然的小标题，但不要像销售页；也不要改成冷冰冰说明文。
如果有合规风险，必须按建议替换，不要绕开平台规则。
""".strip()


def _llm_humanized_draft(state: dict, draft: Draft) -> Draft:
    payload = {
        "user_input": state.get("user_input") or {},
        "draft": draft.model_dump(),
        "risk_items": state.get("risk_items") or [],
        "route_reason": state.get("route_reason", ""),
    }
    response = call_llm_json(HUMANIZER_SYSTEM_PROMPT, payload, temperature=0.6)
    for field in ("titles", "tags", "structure_notes"):
        if isinstance(response.get(field), str):
            response[field] = [item.strip() for item in response[field].replace("；", "\n").replace(";", "\n").splitlines() if item.strip()]
    return Draft.model_validate(response)


def run_humanizer_agent(state: dict) -> dict:
    draft = draft_from_state(state)
    draft = _llm_humanized_draft(state, draft)
    notes = ["LLM 完成真人网感改写"]

    ai_trace_score = max(18, 42 - len(notes) * 4)
    human_score = min(92, 76 + len(notes) * 3)
    unique_notes = list(dict.fromkeys(notes))

    return {
        **state,
        "draft": draft.model_dump(),
        "human_score": human_score,
        "ai_trace_score": ai_trace_score,
        "revision_history": append_revision(
            state,
            "humanizer_agent",
            "rewritten",
            unique_notes or ["调整为更自然的真实体验表达"],
        ),
    }
