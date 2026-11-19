from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib import font_manager
import pandas as pd


BASE_DIR = Path("data/xhs_ops_research_20260618/analysis")
COMMENTS_FILE = BASE_DIR / "comments_50posts_clean.csv"
NOTES_FILE = BASE_DIR / "target_notes_50_summary.csv"
OUTPUT_DIR = BASE_DIR / "need_theme_analysis"
FONT_PATH = Path("/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc")


THEMES = {
    "traffic_visibility": {
        "name": "流量/可见性焦虑",
        "need": "发布后流量诊断、冷启动推流解释、小眼睛异常排查",
        "terms": [
            "流量",
            "小眼睛",
            "浏览量",
            "播放量",
            "推流",
            "曝光",
            "没人看",
            "没流量",
            "个位数",
            "不过百",
            "搜不到",
            "看不到",
            "隐藏",
        ],
    },
    "risk_compliance": {
        "name": "违规/限流/审核风险",
        "need": "发布前合规检测、违禁风险提示、申诉和账号恢复建议",
        "terms": [
            "违规",
            "限流",
            "审核",
            "屏蔽",
            "风控",
            "异常",
            "申诉",
            "违禁词",
            "判违规",
            "提示违规",
            "账号检测",
            "薯条",
            "推不了",
            "被隐藏",
        ],
    },
    "ai_tool_risk": {
        "name": "AI工具风险",
        "need": "AI生成内容的合规校验、违禁词预警、AI痕迹风险提示",
        "terms": [
            "ai",
            "deepseek",
            "chatgpt",
            "gpt",
            "人工智能",
            "提示词",
            "机器人",
            "AI违规",
            "AI提示",
        ],
    },
    "human_voice": {
        "name": "真人网感/去AI味",
        "need": "把AI草稿改成真实、有网感、不模板化的小红书表达",
        "terms": [
            "一眼ai",
            "ai味",
            "ai感",
            "机器味",
            "机器人",
            "模板",
            "复制粘贴",
            "抄",
            "同质化",
            "垃圾文章",
            "真情实感",
            "网感",
            "生硬",
            "不像人",
            "伪人",
            "空洞",
        ],
    },
    "structured_content": {
        "name": "结构化爆款框架",
        "need": "标题、封面、钩子、正文结构、选题模板和发布策略",
        "terms": [
            "标题",
            "封面",
            "开头",
            "钩子",
            "双标题",
            "黄金3秒",
            "猫式",
            "文案",
            "选题",
            "脚本",
            "爆款",
            "结构",
            "模板",
            "tag",
            "BGM",
            "痛点",
            "爽点",
            "停留",
        ],
    },
    "diagnosis_guidance": {
        "name": "求诊断/求指导",
        "need": "账号、笔记、赛道、发布时间、标题封面的个性化诊断",
        "terms": [
            "帮我看看",
            "帮我分析",
            "求帮",
            "求指导",
            "请教",
            "怎么办",
            "正常吗",
            "为什么",
            "哪里有问题",
            "诊断",
            "求支招",
            "怎么改善",
        ],
    },
    "account_growth": {
        "name": "起号/账号增长",
        "need": "起号路径、账号定位、矩阵运营、涨粉和活跃策略",
        "terms": [
            "新号",
            "起号",
            "矩阵",
            "账号",
            "定位",
            "垂直",
            "运营",
            "涨粉",
            "粉丝",
            "断更",
            "活跃",
            "养号",
            "赛道",
        ],
    },
}


STRATEGIC_NEEDS = {
    "need_1_ai_compliance": {
        "name": "AI合规与限流风险控制",
        "base_themes": ["traffic_visibility", "risk_compliance"],
        "evidence_themes": ["ai_tool_risk", "risk_compliance"],
        "logic": "高频基本盘是流量/限流焦虑；AI显式出现不多，但一旦与违规共现，风险强、后果明确。",
    },
    "need_2_human_voice": {
        "name": "去AI味与真人网感",
        "base_themes": ["human_voice", "structured_content"],
        "evidence_themes": ["human_voice", "ai_tool_risk"],
        "logic": "不是最高频痛点，但能解释用户对模板化、AI文本和信任下降的抵触。",
    },
    "need_3_structured_growth": {
        "name": "结构化爆款框架",
        "base_themes": ["traffic_visibility", "diagnosis_guidance"],
        "evidence_themes": ["structured_content", "traffic_visibility"],
        "logic": "结构类词与流量焦虑、求诊断共现，说明用户要的是可执行框架，不只是文案片段。",
    },
}


def normalize_text(text: object) -> str:
    text = str(text)
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"@\S+", " ", text)
    text = re.sub(r"\[[^\]]{1,16}R?\]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def term_pattern(term: str) -> re.Pattern:
    if term.lower() in {"ai", "gpt"}:
        return re.compile(rf"(?i)\b{re.escape(term)}\b")
    return re.compile(re.escape(term), re.IGNORECASE)


def hit_terms(text: str, terms: list[str]) -> list[str]:
    hits = []
    for term in terms:
        if term_pattern(term).search(text):
            hits.append(term)
    return hits


def hit_theme_terms(theme_id: str, text: str) -> list[str]:
    hits = hit_terms(text, THEMES[theme_id]["terms"])
    if theme_id == "human_voice":
        contextual_patterns = {
            "真实": r"(ai|deepseek|文案|内容|表达|草稿|小红书|博主|创作|写).{0,12}真实|真实.{0,12}(ai|deepseek|文案|内容|表达|草稿|小红书|博主|创作|写)",
            "真人": r"(ai|deepseek|文案|内容|表达|草稿|小红书|博主|创作|写).{0,12}真人|真人.{0,12}(ai|deepseek|文案|内容|表达|草稿|小红书|博主|创作|写)",
            "人类情感": r"人类的真实情感|没有人类",
        }
        for term, pattern in contextual_patterns.items():
            if re.search(pattern, text, flags=re.IGNORECASE):
                hits.append(term)
    return sorted(set(hits), key=lambda value: (-len(value), value))


def load_corpus() -> tuple[pd.DataFrame, pd.DataFrame]:
    comments = pd.read_csv(COMMENTS_FILE).fillna("")
    notes = pd.read_csv(NOTES_FILE).fillna("")
    comments = comments[~comments["is_boilerplate_noise"].astype(bool)].copy()
    comments["text"] = comments["content"].map(normalize_text)
    comments = comments[comments["text"].str.len() >= 4].copy()

    note_lookup = notes.set_index("note_id")[["note_url", "source_keyword"]].to_dict("index")
    comments["note_url"] = comments["note_id"].map(lambda note_id: note_lookup.get(note_id, {}).get("note_url", ""))
    comments["source_keyword"] = comments["note_id"].map(lambda note_id: note_lookup.get(note_id, {}).get("source_keyword", ""))
    notes["text"] = notes["title"].map(normalize_text)
    return comments, notes


def code_comments(comments: pd.DataFrame) -> pd.DataFrame:
    coded = comments.copy()
    for theme_id, theme in THEMES.items():
        hit_col = f"{theme_id}_terms"
        bool_col = f"theme_{theme_id}"
        coded[hit_col] = coded["text"].map(lambda text: " / ".join(hit_theme_terms(theme_id, text)))
        coded[bool_col] = coded[hit_col].astype(str).str.len() > 0
    theme_cols = [f"theme_{theme_id}" for theme_id in THEMES]
    coded["theme_count"] = coded[theme_cols].sum(axis=1)
    coded["matched_theme_names"] = coded.apply(
        lambda row: " / ".join(THEMES[theme_id]["name"] for theme_id in THEMES if row[f"theme_{theme_id}"]),
        axis=1,
    )
    return coded


def summarize_themes(coded: pd.DataFrame, notes: pd.DataFrame) -> pd.DataFrame:
    rows = []
    total_comments = len(coded)
    total_notes = coded["note_id"].nunique()
    for theme_id, theme in THEMES.items():
        mask = coded[f"theme_{theme_id}"]
        title_hits = notes["text"].map(lambda text: bool(hit_theme_terms(theme_id, text))).sum()
        term_counter = Counter()
        for value in coded.loc[mask, f"{theme_id}_terms"]:
            term_counter.update(term for term in str(value).split(" / ") if term)
        rows.append(
            {
                "theme_id": theme_id,
                "theme_name": theme["name"],
                "comment_count": int(mask.sum()),
                "comment_pct": round(mask.mean() * 100, 2),
                "note_count": int(coded.loc[mask, "note_id"].nunique()),
                "note_pct": round(coded.loc[mask, "note_id"].nunique() / total_notes * 100, 2),
                "title_count": int(title_hits),
                "top_terms": " / ".join(term for term, _ in term_counter.most_common(12)),
                "product_need": theme["need"],
            }
        )
    return pd.DataFrame(rows).sort_values("comment_count", ascending=False)


def build_cooccurrence(coded: pd.DataFrame) -> pd.DataFrame:
    rows = []
    theme_ids = list(THEMES)
    for left in theme_ids:
        left_mask = coded[f"theme_{left}"]
        for right in theme_ids:
            right_mask = coded[f"theme_{right}"]
            rows.append(
                {
                    "theme_left": left,
                    "theme_right": right,
                    "count": int((left_mask & right_mask).sum()),
                    "pct_of_left": round(((left_mask & right_mask).sum() / max(left_mask.sum(), 1)) * 100, 2),
                }
            )
    return pd.DataFrame(rows)


def summarize_strategic_needs(coded: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for need_id, need in STRATEGIC_NEEDS.items():
        base_masks = [coded[f"theme_{theme_id}"] for theme_id in need["base_themes"]]
        evidence_masks = [coded[f"theme_{theme_id}"] for theme_id in need["evidence_themes"]]
        base_union_mask = base_masks[0]
        for mask in base_masks[1:]:
            base_union_mask = base_union_mask | mask
        evidence_intersection_mask = evidence_masks[0]
        for mask in evidence_masks[1:]:
            evidence_intersection_mask = evidence_intersection_mask & mask
        rows.append(
            {
                "need_id": need_id,
                "need_name": need["name"],
                "base_theme_comment_count": int(base_union_mask.sum()),
                "base_theme_comment_pct": round(base_union_mask.mean() * 100, 2),
                "direct_evidence_comment_count": int(evidence_intersection_mask.sum()),
                "direct_evidence_comment_pct": round(evidence_intersection_mask.mean() * 100, 2),
                "base_themes": " / ".join(THEMES[theme_id]["name"] for theme_id in need["base_themes"]),
                "direct_evidence_rule": " AND ".join(THEMES[theme_id]["name"] for theme_id in need["evidence_themes"]),
                "logic": need["logic"],
            }
        )
    return pd.DataFrame(rows)


def representative_examples(coded: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for theme_id, theme in THEMES.items():
        subset = coded[coded[f"theme_{theme_id}"]].copy()
        if subset.empty:
            continue
        subset["example_score"] = subset["like_count"].astype(int).clip(lower=0).map(lambda value: min(value, 50))
        subset["example_score"] += subset["text"].str.len().between(18, 180).astype(int) * 10
        subset = subset.sort_values(["example_score", "like_count"], ascending=False).head(8)
        for row in subset.itertuples(index=False):
            rows.append(
                {
                    "theme_id": theme_id,
                    "theme_name": theme["name"],
                    "note_id": row.note_id,
                    "note_url": row.note_url,
                    "note_title": row.note_title,
                    "text": row.text,
                    "like_count": int(row.like_count),
                    "matched_terms": getattr(row, f"{theme_id}_terms"),
                }
            )
    return pd.DataFrame(rows)


def plot_theme_counts(summary: pd.DataFrame) -> None:
    if FONT_PATH.exists():
        font_manager.fontManager.addfont(str(FONT_PATH))
        plt.rcParams["font.family"] = "Noto Sans CJK JP"
    plt.rcParams["axes.unicode_minus"] = False

    plot_df = summary.sort_values("comment_count")
    plt.figure(figsize=(10, 5.6))
    plt.barh(plot_df["theme_name"], plot_df["comment_count"], color="#3B82F6")
    plt.xlabel("Matched comments")
    plt.title("Need Theme Coverage Across Cleaned Comments")
    for idx, value in enumerate(plot_df["comment_count"]):
        pct = plot_df.iloc[idx]["comment_pct"]
        plt.text(value + 3, idx, f"{value} ({pct}%)", va="center", fontsize=9)
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "theme_counts.png", dpi=180)
    plt.close()


def markdown_table(df: pd.DataFrame) -> str:
    if df.empty:
        return ""
    columns = list(df.columns)
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for row in df.itertuples(index=False):
        values = []
        for value in row:
            text = str(value).replace("\n", " ").replace("|", "/")
            values.append(text)
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def write_report(
    coded: pd.DataFrame,
    summary: pd.DataFrame,
    strategic: pd.DataFrame,
    cooccurrence: pd.DataFrame,
) -> None:
    total = len(coded)
    ai_count = int(coded["theme_ai_tool_risk"].sum())
    ai_risk_count = int((coded["theme_ai_tool_risk"] & coded["theme_risk_compliance"]).sum())
    ai_human_count = int((coded["theme_ai_tool_risk"] & coded["theme_human_voice"]).sum())
    traffic_count = int(coded["theme_traffic_visibility"].sum())
    structure_count = int(coded["theme_structured_content"].sum())
    risk_count = int(coded["theme_risk_compliance"].sum())
    structure_traffic = int((coded["theme_structured_content"] & coded["theme_traffic_visibility"]).sum())
    diagnosis_structure = int((coded["theme_diagnosis_guidance"] & coded["theme_structured_content"]).sum())

    summary_table = summary[
        ["theme_name", "comment_count", "comment_pct", "note_count", "title_count", "top_terms", "product_need"]
    ]
    strategic_table = strategic[
        [
            "need_name",
            "base_theme_comment_count",
            "base_theme_comment_pct",
            "direct_evidence_comment_count",
            "direct_evidence_comment_pct",
            "base_themes",
            "direct_evidence_rule",
            "logic",
        ]
    ]

    report = f"""# 需求主题文本分析

## 方法

- 语料：剔除复制模板后的评论 {total} 条，来自 50 个帖子；同时统计 50 个帖子标题命中。
- 清洗：移除 URL、@、表情标记和多余空白；保留中文语义词和原句顺序。
- 方法：关键词辅助主题编码。每条评论可命中多个主题，输出全量编码表、主题覆盖率、共现矩阵和代表样本。
- 说明：这不是把 100 条评论挑出来倒推结论，而是在全量清洗语料上用固定词典复跑得到的结果。

## 关键判断

1. 数据不支持把“AI味太浓”说成最高频痛点：显式 AI/DeepSeek/提示词相关评论为 {ai_count} 条，占 {round(ai_count / total * 100, 2)}%；AI 与违规/限流共现为 {ai_risk_count} 条。
2. 更稳的主线是：流量/可见性焦虑为 {traffic_count} 条，占 {round(traffic_count / total * 100, 2)}%；违规/限流/审核风险为 {risk_count} 条，占 {round(risk_count / total * 100, 2)}%。
3. “去AI味”应定位为低频但高风险的信任问题：AI 与真人网感/模板化相关共现 {ai_human_count} 条，适合做产品差异点，不适合包装成最高频痛点。
4. 结构化爆款框架有更稳定证据：结构/标题/封面/钩子相关评论为 {structure_count} 条，占 {round(structure_count / total * 100, 2)}%；其中与流量焦虑共现 {structure_traffic} 条，与求诊断共现 {diagnosis_structure} 条。

## 三个需求如何从数据推出

| 需求 | 更严谨的解释 |
|---|---|
| AI合规与限流风险控制 | 高频痛点是“限流/违规/流量异常”，AI不是高频来源，但一旦出现会被用户直接关联到违规和限流，因此适合作为发布前风险检测能力。 |
| 去AI味与真人网感 | 数据中不是最高频，但存在对 AI 文案、模板化、复制感和不真实表达的反感；应作为提升信任和互动的质量层能力。 |
| 结构化爆款框架 | 标题、封面、开头、钩子、文案等结构词与流量焦虑、求诊断共现，说明用户要的是可执行框架，而不是单段文案。 |

## 主题覆盖

{markdown_table(summary_table)}

## 战略需求覆盖

这里把“基础需求土壤”和“直接证据”分开，避免把低频 AI 现象包装成高频结论。

{markdown_table(strategic_table)}

## 产物

- `theme_summary.csv`：主题覆盖率和产品需求映射
- `strategic_need_summary.csv`：三个需求的聚合覆盖
- `theme_cooccurrence.csv`：主题共现矩阵
- `theme_evidence_examples.csv`：各主题代表样本，含帖子链接
- `theme_coded_comments.csv`：全量评论逐行编码，含命中词和帖子链接
- `theme_counts.png`：主题覆盖柱状图
"""
    (OUTPUT_DIR / "need_theme_report.md").write_text(report, encoding="utf-8")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    comments, notes = load_corpus()
    coded = code_comments(comments)
    summary = summarize_themes(coded, notes)
    cooccurrence = build_cooccurrence(coded)
    strategic = summarize_strategic_needs(coded)
    evidence = representative_examples(coded)

    coded.to_csv(OUTPUT_DIR / "theme_coded_comments.csv", index=False, encoding="utf-8-sig")
    summary.to_csv(OUTPUT_DIR / "theme_summary.csv", index=False, encoding="utf-8-sig")
    cooccurrence.to_csv(OUTPUT_DIR / "theme_cooccurrence.csv", index=False, encoding="utf-8-sig")
    strategic.to_csv(OUTPUT_DIR / "strategic_need_summary.csv", index=False, encoding="utf-8-sig")
    evidence.to_csv(OUTPUT_DIR / "theme_evidence_examples.csv", index=False, encoding="utf-8-sig")

    plot_theme_counts(summary)
    write_report(coded, summary, strategic, cooccurrence)

    print(f"comments={len(coded)}")
    print(f"output_dir={OUTPUT_DIR.resolve()}")
    print(summary[["theme_name", "comment_count", "comment_pct", "note_count", "title_count"]].to_string(index=False))
    print()
    print(strategic[["need_name", "base_theme_comment_count", "base_theme_comment_pct", "direct_evidence_comment_count"]].to_string(index=False))


if __name__ == "__main__":
    main()
