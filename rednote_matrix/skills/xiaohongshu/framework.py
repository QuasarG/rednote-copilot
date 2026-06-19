from __future__ import annotations

from rednote_matrix.core.models import AgentInput, Draft, TrendInsight


HIGH_INTERACTION_PATTERN_SOURCE = "data/xhs_viral_seed_20260618/analysis/viral_pattern_report.md"

HIGH_INTERACTION_PATTERNS = [
    "标题先给情绪或悬念，再交代对象",
    "强场景优先于强卖点",
    "轻反差比硬夸更像真人",
    "情绪要可感知但不过载，正文必须回到具体过程和限制",
    "短标题和生活瞬间可以留讨论空间，不要把正文写成完整产品说明书",
    "正文结构：具体场景 -> 原先困扰/误判 -> 发现过程 -> 真实感受 -> 限制/避坑 -> 互动",
]


def _short_scene(scenario: str) -> str:
    return scenario.replace("和", "/").replace("以及", "/").strip(" ，,。")


def _score_keyword_coverage(user_input: AgentInput) -> int:
    score = 55
    if user_input.product_name:
        score += 15
    score += min(len(user_input.selling_points) * 8, 24)
    if user_input.target_audience:
        score += 8
    return min(score, 100)


def build_trend_insight(user_input: AgentInput) -> TrendInsight:
    audience = user_input.target_audience or "目标人群"
    scenario = user_input.scenario or "具体场景"
    short_scene = _short_scene(scenario)
    product = user_input.product_name
    primary_point = user_input.selling_points[0] if user_input.selling_points else "少一点选择负担"
    return TrendInsight(
        title_patterns=[
            "情绪/悬念先行 + 对象后置：先写具体犹豫、误判、意外或松一口气，再交代商品",
            "生活瞬间先行：用早八、通勤、租房、宿舍、做饭、周五晚等具体场景带出商品",
            "轻反差标题：本来以为普通/没必要/会踩雷，结果出现一个小转折",
            f"{short_scene}，我竟然先留下了{product}",
            f"本来以为{product}没必要，结果有点意外",
            f"{audience}先别急着买{product}",
            f"为了{primary_point}看{product}，结果最在意的不是这个",
            f"{product}这件小事，真的能少一点麻烦吗",
        ],
        opening_hooks=[
            "先给一个具体生活瞬间，而不是直接介绍产品",
            "先写原先困扰或误判，再进入发现过程",
            f"从{scenario}里的真实痛点切入",
            "先承认犹豫，再给出主观体验变化",
            "用轻微情绪反差降低硬广感",
            "表达松一口气、纠结、意外但不夸张",
            "用一个生活瞬间开场，而不是直接罗列卖点",
        ],
        content_structures=[
            "必须优先采用：具体场景 -> 原先困扰/误判 -> 发现过程 -> 真实感受 -> 限制/避坑 -> 互动",
            "具体生活场景 + 原先困扰/误判 + 发现过程 + 真实感受 + 限制/避坑 + 互动",
            "轻情绪开场 + 三个细节 + 适用人群 + 保留判断",
            "短标题悬念 + 正文补充上下文 + 评论区讨论点",
            *HIGH_INTERACTION_PATTERNS,
        ],
        interaction_tactics=[
            "结尾引导用户说出自己的场景",
            "邀请用户补充避坑经验，不做硬性导流",
            "用选择题式评论引导提升互动",
            "留下一个可讨论的生活判断，而不是下购买结论",
        ],
        tag_strategy=[
            "产品品类词",
            "目标人群词",
            "场景词",
            "真实体验词",
            "选购/避坑词",
        ],
        scoring_dimensions={
            "关键词覆盖": _score_keyword_coverage(user_input),
            "结构完整度": 85,
            "时效性": 65,
            "内容质量": 82,
        },
        source=f"project_builtin:xiaohongshu_framework+viral_seed_20260618:{HIGH_INTERACTION_PATTERN_SOURCE}",
    )


def score_draft(draft: Draft, insight: TrendInsight) -> dict[str, int]:
    text = "\n".join([*draft.titles, draft.cover_text, draft.hook, draft.body, " ".join(draft.tags)])
    scores = dict(insight.scoring_dimensions)
    scores["结构完整度"] = min(
        100,
        45
        + (20 if draft.hook else 0)
        + (15 if len(draft.titles) >= 2 else 0)
        + (10 if "避坑" in text or "不建议" in text else 0)
        + (10 if len(draft.tags) >= 5 else 0),
    )
    scores["内容质量"] = min(
        100,
        50
        + (15 if len(draft.body.splitlines()) >= 3 else 0)
        + (15 if "体验" in text or "感受" in text else 0)
        + (10 if "适合" in text else 0)
        + (10 if "评论" in text or "你们" in text else 0),
    )
    return scores
