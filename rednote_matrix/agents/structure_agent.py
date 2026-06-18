from __future__ import annotations

from rednote_matrix.agents.llm_bridge import call_llm_json
from rednote_matrix.agents.utils import append_revision, strip_price_mentions
from rednote_matrix.core.models import AgentInput, Draft, MemoryContext, TrendInsight


STRUCTURE_SYSTEM_PROMPT = """
你是小红书种草内容结构 Agent。只输出 JSON 对象，不要 Markdown。
字段必须是 titles, cover_text, hook, body, tags, structure_type, structure_notes。
首要目标：像真实普通用户的分享草稿，不像品牌广告、营销号、带货口播。
要求：双标题兼顾搜索和点击；开头用具体痛点或情绪钩子；正文按场景、犹豫、试用过程、个人限制、避坑组织。
标题要求：更吸睛一点，允许轻微情绪表达，比如“差点放弃”“终于没那么纠结”“松了一口气”，但不要喊口号、不要夸张惊叹。
正文要求：增加一点真实情绪和文案张力，比如纠结、怀疑、松一口气、意外、仍有保留；不要写成冷冰冰说明文。
爆款样本抽象：优先使用“生活瞬间/强场景 + 轻反差/意外 + 对象”的标题，不要只写“XX真实体验分享”。
正文不要一上来卖产品，先写用户处境或原先误判，再自然带出产品。
必须参考输入里的 trend_insight：标题模式、开头钩子、内容结构、互动策略、标签策略。
必须参考 conversation_history、current_changes 和 current_message：历史记录用于理解连续修改意图，本轮 current_message 与 current_changes 优先级最高。
如果用户说“加上/强调/删掉/更像/换成”等追问，要基于上一轮方向调整，但仍必须遵守事实边界与合规规则。
严格事实边界：只能使用用户输入的商品名、品牌、卖点、人群、场景和自定义要求。禁止编造未输入的成分、数值、具体材质/配方、功效、版本、购买渠道。
价格只作为内部判断预算和定位的参考，最终标题、正文、标签里不要出现具体价格、价格带或“售价/到手价/活动价”等交易表达。
不得新增用户没提供的推荐来源、试用时长、购买经历、使用步骤、比例、身体反应、版本对比、成分细项。
如果想表达体验，只能围绕输入卖点做主观转述，不要扩写成未提供的参数、操作细节或因果结论。
表达约束：少用感叹号和 emoji；禁止“放心冲”“必备”“狂喜”“闭眼入”“回购”“姐妹”等广告化表达。
结论要克制：可以说“我会继续观察”“适合某些场景”，不要说“直接买”“强推”。
禁止极限承诺、硬广导流、医疗功效承诺和夸张模板腔。
""".strip()


def _llm_draft(user_input: AgentInput, trend_insight: TrendInsight, memory_context: MemoryContext) -> Draft:
    safe_memory_context = memory_context.model_copy(deep=True)
    for snippet in safe_memory_context.product_facts:
        snippet.content = strip_price_mentions(snippet.content)
    payload = {
        "product_name": user_input.product_name,
        "brand_name": user_input.brand_name,
        "price": user_input.price,
        "selling_points": user_input.selling_points,
        "target_audience": user_input.target_audience,
        "scenario": user_input.scenario,
        "account_persona": user_input.account_persona,
        "tone": user_input.tone,
        "custom_prompt": user_input.custom_prompt,
        "current_message": user_input.current_message,
        "current_changes": user_input.current_changes,
        "conversation_history": user_input.conversation_history,
        "memory_namespace": user_input.memory_namespace,
        "forbidden_words": user_input.forbidden_words,
        "trend_insight": trend_insight.model_dump(),
        "memory_context": safe_memory_context.model_dump(),
    }
    response = call_llm_json(STRUCTURE_SYSTEM_PROMPT, payload, temperature=0.5)
    for field in ("titles", "tags", "structure_notes"):
        if isinstance(response.get(field), str):
            response[field] = [item.strip() for item in response[field].replace("；", "\n").replace(";", "\n").splitlines() if item.strip()]
    return Draft.model_validate(response)


def run_structure_agent(state: dict) -> dict:
    user_input = AgentInput.model_validate(state["user_input"])
    trend_insight = TrendInsight.model_validate(state.get("trend_insight") or {})
    memory_context = MemoryContext.model_validate(state.get("memory_context") or {})
    draft = _llm_draft(user_input, trend_insight, memory_context)

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
