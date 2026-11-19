from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib import font_manager


BASE_DIR = Path("data/xhs_ops_research_20260618/analysis")
THEME_DIR = BASE_DIR / "need_theme_analysis"
OUTPUT_DIR = BASE_DIR / "ai_tool_need_validation"
FONT_PATH = Path("/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc")


AI_CAPABILITIES = [
    {
        "capability_id": "compliance_guard",
        "capability_name": "合规防限流 Agent",
        "pain_chain": "帖子热度低 -> 用户怀疑限流/违规/审核异常 -> AI生成内容可能放大违规风险",
        "base_themes": ["traffic_visibility", "risk_compliance"],
        "direct_evidence_themes": ["ai_tool_risk", "risk_compliance"],
        "product_form": "发布前违禁词/违规风险扫描、AI生成内容审核提示、限流风险解释与修改建议",
        "why_agent": "普通聊天AI只生成文本；Agent能把平台风险扫描、修改建议、复检和发布前检查串成闭环。",
    },
    {
        "capability_id": "human_voice_rewrite",
        "capability_name": "真人网感改写 Agent",
        "pain_chain": "帖子热度低 -> 用户担心内容像模板/机器生成 -> 读者信任和互动下降",
        "base_themes": ["human_voice", "structured_content"],
        "direct_evidence_themes": ["ai_tool_risk", "human_voice"],
        "product_form": "把AI草稿改成小红书口语、真实经历感、低模板感、低机器味表达",
        "why_agent": "普通聊天AI容易继续产出模板腔；Agent能结合账号人设、评论语境和互动目标做多轮去AI味改写。",
    },
    {
        "capability_id": "viral_structure_builder",
        "capability_name": "结构化爆款 Agent",
        "pain_chain": "帖子热度低 -> 用户追问标题/封面/开头/钩子为什么不行 -> 需要可复制结构",
        "base_themes": ["traffic_visibility", "structured_content", "diagnosis_guidance"],
        "direct_evidence_themes": ["traffic_visibility", "structured_content"],
        "product_form": "标题/封面/钩子/正文结构模板、双标题、开头框架、发布前结构诊断",
        "why_agent": "普通聊天AI只给单段文案；Agent能拆成标题、封面、钩子、正文、标签、发布时间和复盘指标。",
    },
]

THEME_NAMES = {
    "traffic_visibility": "流量/可见性焦虑",
    "risk_compliance": "违规/限流/审核风险",
    "ai_tool_risk": "AI工具风险",
    "human_voice": "真人网感/去AI味",
    "structured_content": "结构化爆款框架",
    "diagnosis_guidance": "求诊断/求指导",
    "account_growth": "起号/账号增长",
}

EXAMPLE_EXCLUDE_MARKERS = [
    "回复1",
    "回复",
    "我去看",
    "我就来看",
    "我马上去看",
    "谁要小眼睛",
    "点赞",
    "互助",
    "举手",
    "评1",
    "点1",
    "评论真的会推流",
    "流量来咯",
    "一起来互动",
    "短短一个月",
    "涨到现在",
    "到处评论",
    "别人的评论下面回复",
    "别人就会好奇",
    "系统会认定你是活人",
    "活跃用户",
    "不要太在意小眼睛",
    "平时多去别的评论区",
    "隔三差五",
]

EXAMPLE_NEED_MARKERS = [
    "我",
    "我的",
    "自己",
    "请教",
    "求",
    "帮我",
    "为什么",
    "怎么办",
    "不知道",
    "不懂",
    "搞不懂",
    "不会",
    "无语",
    "焦虑",
    "违规",
    "限流",
    "小眼睛",
    "浏览量",
    "流量",
    "标题",
    "封面",
    "文案",
    "账号",
    "笔记",
]


def setup_font() -> None:
    if FONT_PATH.exists():
        font_manager.fontManager.addfont(str(FONT_PATH))
        plt.rcParams["font.family"] = "Noto Sans CJK JP"
    plt.rcParams["axes.unicode_minus"] = False


def markdown_table(df: pd.DataFrame) -> str:
    if df.empty:
        return ""
    columns = list(df.columns)
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for row in df.itertuples(index=False):
        values = [str(value).replace("\n", " ").replace("|", "/") for value in row]
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def load_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    coded = pd.read_csv(THEME_DIR / "theme_coded_comments.csv").fillna("")
    theme_summary = pd.read_csv(THEME_DIR / "theme_summary.csv").fillna("")
    evidence = pd.read_csv(THEME_DIR / "theme_evidence_examples.csv").fillna("")
    return coded, theme_summary, evidence


def theme_mask(coded: pd.DataFrame, theme_id: str) -> pd.Series:
    return coded[f"theme_{theme_id}"].astype(bool)


def union_mask(coded: pd.DataFrame, theme_ids: list[str]) -> pd.Series:
    mask = theme_mask(coded, theme_ids[0])
    for theme_id in theme_ids[1:]:
        mask = mask | theme_mask(coded, theme_id)
    return mask


def intersection_mask(coded: pd.DataFrame, theme_ids: list[str]) -> pd.Series:
    mask = theme_mask(coded, theme_ids[0])
    for theme_id in theme_ids[1:]:
        mask = mask & theme_mask(coded, theme_id)
    return mask


def filter_example_candidates(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    text = df["text"].astype(str)
    keep = text.map(lambda value: any(marker in value for marker in EXAMPLE_NEED_MARKERS))
    drop = text.map(lambda value: any(marker in value for marker in EXAMPLE_EXCLUDE_MARKERS))
    filtered = df[keep & ~drop].copy()
    return filtered if not filtered.empty else df[~drop].copy()


def build_validation_matrix(coded: pd.DataFrame) -> pd.DataFrame:
    rows = []
    total = len(coded)
    for capability in AI_CAPABILITIES:
        base = union_mask(coded, capability["base_themes"])
        direct = intersection_mask(coded, capability["direct_evidence_themes"])
        heat_related = base | direct
        rows.append(
            {
                "AI工具需求": capability["capability_name"],
                "对应热度链路痛点": capability["pain_chain"],
                "基础痛点覆盖评论数": int(base.sum()),
                "基础痛点覆盖率": round(base.mean() * 100, 2),
                "能力直接证据数": int(direct.sum()),
                "能力直接证据率": round(direct.mean() * 100, 2),
                "关联帖子数": int(coded.loc[heat_related, "note_id"].nunique()),
                "产品形态": capability["product_form"],
                "为什么普通聊天AI不够": capability["why_agent"],
            }
        )
    return pd.DataFrame(rows)


def build_capability_examples(coded: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for capability in AI_CAPABILITIES:
        direct = intersection_mask(coded, capability["direct_evidence_themes"])
        base = union_mask(coded, capability["base_themes"])
        direct_subset = coded[direct].copy()
        base_subset = coded[base & ~direct].copy()
        direct_subset["证据类型"] = "能力直接证据"
        base_subset["证据类型"] = "基础痛点"
        direct_subset = filter_example_candidates(direct_subset)
        base_subset = filter_example_candidates(base_subset)
        subset = pd.concat([direct_subset, base_subset], ignore_index=True)
        subset["evidence_score"] = subset["like_count"].astype(int).clip(upper=50)
        subset["evidence_score"] += subset["text"].str.len().between(15, 180).astype(int) * 10
        subset = subset.sort_values(["证据类型", "evidence_score"], ascending=[False, False]).head(10)
        for row in subset.itertuples(index=False):
            matched_terms = []
            for theme_id in capability["base_themes"] + capability["direct_evidence_themes"]:
                term_col = f"{theme_id}_terms"
                value = getattr(row, term_col, "")
                if value:
                    matched_terms.append(f"{THEME_NAMES[theme_id]}:{value}")
            rows.append(
                {
                    "AI工具需求": capability["capability_name"],
                    "证据类型": row.证据类型,
                    "note_id": row.note_id,
                    "note_url": row.note_url,
                    "note_title": row.note_title,
                    "comment_text": row.text,
                    "like_count": int(row.like_count),
                    "matched_terms": " || ".join(matched_terms),
                }
            )
    return pd.DataFrame(rows)


def plot_theme_bridge(theme_summary: pd.DataFrame) -> None:
    focus = [
        "traffic_visibility",
        "risk_compliance",
        "structured_content",
        "diagnosis_guidance",
        "human_voice",
        "ai_tool_risk",
    ]
    df = theme_summary[theme_summary["theme_id"].isin(focus)].copy()
    order = {theme_id: idx for idx, theme_id in enumerate(focus)}
    df["order"] = df["theme_id"].map(order)
    df = df.sort_values("order")
    colors = ["#2563EB", "#DC2626", "#9333EA", "#0891B2", "#EA580C", "#16A34A"]

    plt.figure(figsize=(11, 5.8))
    bars = plt.bar(df["theme_name"], df["comment_count"], color=colors)
    plt.xticks(rotation=25, ha="right")
    plt.ylabel("评论数")
    plt.title("从热度痛点到AI工具需求的主题覆盖")
    for bar, pct in zip(bars, df["comment_pct"]):
        plt.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 8, f"{int(bar.get_height())}\n{pct}%", ha="center", fontsize=9)
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "ai_need_theme_bridge.png", dpi=180)
    plt.close()


def plot_capability_matrix(matrix: pd.DataFrame) -> None:
    labels = matrix["AI工具需求"].tolist()
    base = matrix["基础痛点覆盖评论数"].tolist()
    direct = matrix["能力直接证据数"].tolist()

    x = range(len(labels))
    plt.figure(figsize=(10, 5.6))
    plt.bar([i - 0.18 for i in x], base, width=0.36, label="基础痛点覆盖", color="#2563EB")
    plt.bar([i + 0.18 for i in x], direct, width=0.36, label="能力直接证据", color="#F97316")
    plt.xticks(list(x), labels, rotation=15, ha="right")
    plt.ylabel("评论数")
    plt.title("AI Agent需求：基础痛点土壤 vs 能力直接证据")
    plt.legend()
    for i, value in enumerate(base):
        plt.text(i - 0.18, value + 8, str(value), ha="center", fontsize=9)
    for i, value in enumerate(direct):
        plt.text(i + 0.18, value + 8, str(value), ha="center", fontsize=9)
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "ai_capability_validation_matrix.png", dpi=180)
    plt.close()


def write_report(matrix: pd.DataFrame, theme_summary: pd.DataFrame, examples: pd.DataFrame, coded: pd.DataFrame) -> None:
    total = len(coded)
    traffic = int(theme_mask(coded, "traffic_visibility").sum())
    risk = int(theme_mask(coded, "risk_compliance").sum())
    ai = int(theme_mask(coded, "ai_tool_risk").sum())
    ai_risk = int((theme_mask(coded, "ai_tool_risk") & theme_mask(coded, "risk_compliance")).sum())
    ai_voice = int((theme_mask(coded, "ai_tool_risk") & theme_mask(coded, "human_voice")).sum())
    structure_traffic = int((theme_mask(coded, "structured_content") & theme_mask(coded, "traffic_visibility")).sum())

    short_matrix = matrix[
        [
            "AI工具需求",
            "基础痛点覆盖评论数",
            "基础痛点覆盖率",
            "能力直接证据数",
            "能力直接证据率",
            "关联帖子数",
            "产品形态",
            "为什么普通聊天AI不够",
        ]
    ]
    example_short = examples.groupby("AI工具需求").head(4)[
        ["AI工具需求", "证据类型", "comment_text", "matched_terms", "note_url"]
    ]

    report = f"""# AI工具需求合理性验证

## 结论

这批数据最强的痛点不是“用户想用AI”，而是 B 端种草博主和小商户想让帖子有热度，同时害怕被限流、违规、审核拖死。  
因此，AI Agent 的合理定位不是“再写一段文案”，而是服务于热度目标的闭环工具：**合规防限流、真人网感改写、结构化爆款生成**。

## 证据链

- 全量编码评论：{total} 条，来自 50 个帖子。
- 热度痛点主轴：流量/可见性焦虑 {traffic} 条，占 {round(traffic / total * 100, 2)}%；违规/限流/审核风险 {risk} 条，占 {round(risk / total * 100, 2)}%。
- AI不是最高频痛点：显式 AI 工具风险 {ai} 条，占 {round(ai / total * 100, 2)}%。这说明用户不是在泛泛讨论 AI，而是在热度/合规/内容质量链路中暴露 AI 工具缺口。
- AI 是热度链路里的风险放大器：AI 与违规/限流共现 {ai_risk} 条；AI 与去AI味/模板化共现 {ai_voice} 条。
- 结构化框架更接近“提热度”的可产品化抓手：结构化爆款框架与流量焦虑共现 {structure_traffic} 条。
- 普通聊天 AI 能生成内容，但不能稳定完成小红书发布前的合规检查、结构诊断、语气改写、复检和复盘；这正是 Agent 产品的切入点。

## AI工具需求验证矩阵

{markdown_table(short_matrix)}

## 代表证据

{markdown_table(example_short)}

## 使用建议

1. 对外不要说“AI味焦虑是最高频痛点”，数据不支持。
2. 应该说：**核心痛点是提高热度，AI Agent 是热度链路里的风控、改写、结构化执行工具。**
3. 产品叙事顺序建议是：先承接“低热度/限流/违规”主焦虑，再强调普通聊天 AI 只会写，Agent 能诊断、改写、检查、复盘。

## 产物

- `ai_tool_need_matrix.csv`：AI工具需求验证矩阵
- `ai_tool_need_examples.csv`：每个需求对应证据，含帖子链接
- `ai_need_theme_bridge.png`：主题覆盖图
- `ai_capability_validation_matrix.png`：基础痛点和能力直接证据对比图
"""
    (OUTPUT_DIR / "ai_tool_need_validation_report.md").write_text(report, encoding="utf-8")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    setup_font()
    coded, theme_summary, _ = load_data()
    matrix = build_validation_matrix(coded)
    examples = build_capability_examples(coded)

    matrix.to_csv(OUTPUT_DIR / "ai_tool_need_matrix.csv", index=False, encoding="utf-8-sig")
    examples.to_csv(OUTPUT_DIR / "ai_tool_need_examples.csv", index=False, encoding="utf-8-sig")
    plot_theme_bridge(theme_summary)
    plot_capability_matrix(matrix)
    write_report(matrix, theme_summary, examples, coded)

    print(f"comments={len(coded)}")
    print(f"output_dir={OUTPUT_DIR.resolve()}")
    print(matrix[["AI工具需求", "基础痛点覆盖评论数", "基础痛点覆盖率", "能力直接证据数", "能力直接证据率"]].to_string(index=False))


if __name__ == "__main__":
    main()
