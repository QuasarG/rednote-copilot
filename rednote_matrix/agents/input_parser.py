from __future__ import annotations

from rednote_matrix.agents.llm_bridge import call_llm_json
from rednote_matrix.agents.utils import append_revision
from rednote_matrix.core.models import AgentInput, ParsedUserInput


INPUT_PARSER_PROMPT = """
你是一个小红书种草文案助手的输入解析 Agent。
用户的输入是自然语言，可能包含商品信息、人群、场景、语气等。
请从用户的输入中提取结构化信息。只输出 JSON，不要 Markdown。

字段说明：
- product_name: 商品或服务名称
- brand_name: 品牌名称（如果有）
- price: 价格信息（内部参考，不写进文案）
- selling_points: 核心卖点列表
- target_audience: 目标人群
- scenario: 使用场景
- account_persona: 账号人设（如"真实分享型种草博主"）
- tone: 语气偏好（如"自然、可信、轻种草"）
- custom_prompt: 用户额外的创作要求
- forbidden_words: 品牌或行业禁用词列表
- realtime_research_keywords: 用于小红书爆款检索的关键词列表（3-5个），围绕商品品类、人群、场景生成高互动意图的搜索词
- memory_namespace: 品牌/商品记忆命名空间，用品牌名或商品名

注意：如果用户没有明确提供某些信息，不要编造，留空即可。
realtime_research_keywords 必须生成，用于后续爬取爆款笔记。
""".strip()


def run_input_parser(state: dict) -> dict:
    user_input = AgentInput.model_validate(state["user_input"])
    raw = user_input.raw_user_request.strip() or user_input.current_message.strip()
    source = "raw_user_request" if user_input.raw_user_request.strip() else "current_message"

    if not raw:
        if not user_input.product_name.strip():
            raise ValueError("请先告诉我商品或服务名称，可以直接用自然语言描述需求")
        return {
            **state,
            "parsed_input": ParsedUserInput().model_dump(),
            "revision_history": append_revision(state, "input_parser", "skipped", ["没有用户输入需要解析"]),
        }

    # 构建当前已知信息（如果是多轮，携带已有信息让 LLM 做增量）
    known = {}
    if user_input.product_name:
        known["已提取商品"] = user_input.product_name
    if user_input.brand_name:
        known["已提取品牌"] = user_input.brand_name
    if user_input.price:
        known["已提取价格"] = user_input.price
    if user_input.selling_points:
        known["已提取卖点"] = user_input.selling_points
    if user_input.target_audience:
        known["已提取人群"] = user_input.target_audience
    if user_input.conversation_history:
        known["对话轮次"] = f"第 {len(user_input.conversation_history) + 1} 轮"

    payload = {
        "当前输入": raw,
        "已知信息（如为空则是首轮）": known,
    }

    response = call_llm_json(INPUT_PARSER_PROMPT, payload, temperature=0.3)
    parsed = ParsedUserInput.model_validate(response)

    # 更新 user_input 中的字段（合并已有信息+新提取）
    updated_input = user_input.model_dump()
    if parsed.product_name:
        updated_input["product_name"] = parsed.product_name
    if parsed.brand_name:
        updated_input["brand_name"] = parsed.brand_name
    if parsed.price:
        updated_input["price"] = parsed.price
    if parsed.selling_points:
        existing = set(user_input.selling_points)
        updated_input["selling_points"] = list(dict.fromkeys([*user_input.selling_points, *parsed.selling_points]))
    if parsed.target_audience:
        updated_input["target_audience"] = parsed.target_audience
    if parsed.scenario:
        updated_input["scenario"] = parsed.scenario
    if parsed.account_persona:
        updated_input["account_persona"] = parsed.account_persona
    if parsed.tone:
        updated_input["tone"] = parsed.tone
    if parsed.custom_prompt:
        updated_input["custom_prompt"] = (
            f"{user_input.custom_prompt}\n{parsed.custom_prompt}" if user_input.custom_prompt else parsed.custom_prompt
        )
    if parsed.forbidden_words:
        existing_fw = set(user_input.forbidden_words)
        updated_input["forbidden_words"] = list(dict.fromkeys([*user_input.forbidden_words, *parsed.forbidden_words]))
    if parsed.realtime_research_keywords:
        updated_input["realtime_research_keywords"] = parsed.realtime_research_keywords
    if parsed.memory_namespace:
        updated_input["memory_namespace"] = parsed.memory_namespace

    resolved = AgentInput.model_validate(updated_input)
    if not resolved.product_name.strip():
        raise ValueError("没有识别到商品或服务名称，请补充要写的小红书种草对象")

    return {
        **state,
        "user_input": resolved.model_dump(),
        "parsed_input": parsed.model_dump(),
        "revision_history": append_revision(
            state,
            "input_parser",
            "parsed",
            [f"来源: {source}", f"提取商品: {parsed.product_name or '(未提供)'}"],
        ),
    }
