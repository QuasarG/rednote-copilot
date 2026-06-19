from __future__ import annotations

from rednote_matrix.agents.llm_bridge import call_llm_json
from rednote_matrix.agents.utils import append_revision, strip_price_mentions
from rednote_matrix.core.models import AgentInput, Draft, MemoryContext, ParsedUserInput, TrendInsight
from rednote_matrix.skills.xiaohongshu.framework import HIGH_INTERACTION_PATTERN_SOURCE, HIGH_INTERACTION_PATTERNS


STRUCTURE_SYSTEM_PROMPT = """
你是小红书种草内容结构 Agent。只输出 JSON 对象，不要 Markdown。
字段必须是 titles, cover_text, hook, body, tags, structure_type, structure_notes。
首要目标：像真实普通用户的分享草稿，不像品牌广告、营销号、带货口播。
最高优先级：必须优先服从输入里的 viral_rules，这是项目从真实高互动小红书样本沉淀出的爆款结构规则。普通 LLM 写法、实时样本标题、用户语气偏好都不能覆盖 viral_rules。
标题硬约束：标题先给情绪/悬念/生活瞬间，再交代商品对象；避免“品牌 + 卖点列表”式广告标题；双标题分别承担点击和搜索。
开头硬约束：第一段先写具体场景、原先困扰或误判，不要直接介绍产品和卖点。
正文硬约束：默认采用“具体场景 -> 原先困扰/误判 -> 发现过程 -> 真实感受 -> 限制/避坑 -> 互动”的顺序，除非用户明确要求其他结构。
事实填充硬约束：如果用户没有明确提供亲身试用、购买、使用时长、效果反馈等经历，必须把“发现过程/真实感受”写成观察、筛选、看到卖点后的判断、计划重点关注、适用条件推测，不能冒充已经亲测。
情绪硬约束：允许纠结、怀疑、松一口气、意外、有保留，但不要夸张喊口号。
必须参考输入里的 trend_insight：标题模式、开头钩子、内容结构、互动策略、标签策略；其中 viral_rules 权重最高，实时爆款标题只能作为同类语感参考，不能照搬。
必须执行 memory_context.writing_rules 和 memory_context.risk_rules 中检索出的品牌/商品细规则；这些细规则优先级高于普通风格偏好，但不能覆盖合规和事实边界。
structure_notes 必须写出至少 3 条本次实际采用的 viral_rules 或 trend_insight 结构依据，不能只写“真实体验”这种空话。
如果有多轮对话信息（conversation_history, current_message），基于上一轮方向调整，本轮要求优先级最高。
严格事实边界：只能使用用户提供的商品名、品牌、卖点、人群、场景和自定义要求。禁止编造未输入的细节，也不要把“参考实时爆款标题”当成当前商品事实。
价格默认只作为内部预算和定位参考。只有当用户已提供具体价格，且 current_message/custom_prompt 明确要求“加上价格/写价格/标价格/带价格”时，正文允许出现一次弱表达（如“价格在xx左右/预算大概xx”）；标题、标签、封面不要放价格，也不要写“到手价/活动价/下单”等交易表达。
不得新增用户没提供的推荐来源、亲测经历、试用时长、购买经历、使用步骤、比例、版本对比、成分细项、具体效果反馈。
表达约束：少用感叹号和 emoji；禁止"放心冲""必备""狂喜""闭眼入""回购""姐妹"等广告化表达。
""".strip()


def _llm_draft(user_input: AgentInput, parsed: ParsedUserInput, trend_insight: TrendInsight, memory_context: MemoryContext) -> Draft:
    safe_memory_context = memory_context.model_copy(deep=True)
    allow_price = _allow_price_in_copy(user_input)
    if not allow_price:
        for snippet in safe_memory_context.product_facts:
            snippet.content = strip_price_mentions(snippet.content)
    payload = {
        "product_name": parsed.product_name or user_input.product_name,
        "brand_name": parsed.brand_name or user_input.brand_name,
        "price": user_input.price,
        "price_policy": {
            "allow_price_in_body": allow_price,
            "rule": "默认不写价格；只有用户本轮明确要求加价格且已提供价格时，正文最多弱表达一次。",
        },
        "selling_points": parsed.selling_points or user_input.selling_points,
        "target_audience": parsed.target_audience or user_input.target_audience,
        "scenario": parsed.scenario or user_input.scenario,
        "account_persona": parsed.account_persona or user_input.account_persona,
        "tone": parsed.tone or user_input.tone,
        "custom_prompt": parsed.custom_prompt or user_input.custom_prompt,
        "current_message": user_input.current_message,
        "current_changes": user_input.current_changes,
        "conversation_history": user_input.conversation_history,
        "forbidden_words": parsed.forbidden_words or user_input.forbidden_words,
        "viral_rules": {
            "source": HIGH_INTERACTION_PATTERN_SOURCE,
            "priority": "highest",
            "rules": HIGH_INTERACTION_PATTERNS,
            "required_body_order": "具体场景 -> 原先困扰/误判 -> 发现过程 -> 真实感受 -> 限制/避坑 -> 互动",
            "title_priority": "情绪/悬念/生活瞬间先行，商品对象后置",
        },
        "trend_insight": trend_insight.model_dump(),
        "memory_context": safe_memory_context.model_dump(),
    }
    response = call_llm_json(STRUCTURE_SYSTEM_PROMPT, payload, temperature=0.5)
    for field in ("titles", "tags", "structure_notes"):
        if isinstance(response.get(field), str):
            response[field] = [item.strip() for item in response[field].replace("；", "\n").replace(";", "\n").splitlines() if item.strip()]
    return Draft.model_validate(response)


def _allow_price_in_copy(user_input: AgentInput) -> bool:
    if not user_input.price.strip():
        return False
    intent_text = f"{user_input.current_message}\n{user_input.custom_prompt}".lower()
    return any(keyword in intent_text for keyword in ("加上价格", "加入价格", "写价格", "带价格", "标价格", "价格"))


def run_structure_agent(state: dict) -> dict:
    user_input = AgentInput.model_validate(state["user_input"])
    parsed = ParsedUserInput.model_validate(state.get("parsed_input") or {})
    trend_insight = TrendInsight.model_validate(state.get("trend_insight") or {})
    memory_context = MemoryContext.model_validate(state.get("memory_context") or {})
    draft = _llm_draft(user_input, parsed, trend_insight, memory_context)

    return {
        **state,
        "draft": draft.model_dump(),
        "structure_score": int(state.get("trend_score", 82)),
        "revision_history": append_revision(
            state,
            "structure_agent",
            "generated",
            ["LLM 生成双标题、封面文案、钩子和结构化正文"],
        ),
    }
