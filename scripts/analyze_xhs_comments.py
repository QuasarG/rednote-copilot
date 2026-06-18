from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import jieba
import pandas as pd
from sklearn.decomposition import LatentDirichletAllocation
from sklearn.feature_extraction.text import CountVectorizer
from wordcloud import WordCloud


BASE_DIR = Path("data/xhs_ops_research_20260618")
RAW_DIR = BASE_DIR / "raw"
ANALYSIS_DIR = BASE_DIR / "analysis"
COMMENTS_FILE = RAW_DIR / "comments_50posts/xhs/jsonl/detail_comments_2026-06-18.jsonl"
DETAILS_FILE = RAW_DIR / "comments_50posts/xhs/jsonl/detail_contents_2026-06-18.jsonl"
TITLE_FILES = [
    RAW_DIR / "title_search_initial/xhs/jsonl/search_contents_2026-06-18.jsonl",
    RAW_DIR / "title_search_more/xhs/jsonl/search_contents_2026-06-18.jsonl",
]
FONT_PATH = Path("/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc")
TOP_NOTES_LIMIT = 50
LDA_TOPIC_COUNT = 8
LDA_TOP_WORDS = 15


CUSTOM_WORDS = [
    "小红书",
    "小眼睛",
    "被限流",
    "限流",
    "违规",
    "笔记违规",
    "违禁词",
    "爆款文案",
    "浏览量",
    "推流",
    "二次推流",
    "账号诊断",
    "薯条",
    "互赞",
    "一换一",
    "矩阵号",
    "做矩阵",
    "运营",
    "涨粉",
    "封面",
    "标题",
]

STOPWORDS = {
    "的",
    "了",
    "我",
    "你",
    "他",
    "她",
    "它",
    "们",
    "和",
    "是",
    "就",
    "都",
    "也",
    "在",
    "不",
    "有",
    "没",
    "很",
    "太",
    "又",
    "还",
    "被",
    "把",
    "给",
    "要",
    "想",
    "做",
    "发",
    "看",
    "去",
    "来",
    "能",
    "会",
    "让",
    "到",
    "上",
    "下",
    "里",
    "吗",
    "呢",
    "啊",
    "吧",
    "呀",
    "嘛",
    "哦",
    "啦",
    "对",
    "跟",
    "与",
    "及",
    "或",
    "并",
    "而",
    "而且",
    "然后",
    "用户",
    "社区",
    "环境",
    "一下",
    "一个",
    "一点",
    "一些",
    "这个",
    "那个",
    "就是",
    "可以",
    "不是",
    "没有",
    "觉得",
    "感觉",
    "真的",
    "这么",
    "怎么",
    "什么",
    "还是",
    "因为",
    "所以",
    "如果",
    "但是",
    "自己",
    "我们",
    "你们",
    "他们",
    "姐妹",
    "宝宝",
    "老师",
    "求求",
    "哈哈",
    "哈哈哈",
    "啊啊啊",
    "呜呜",
    "回复",
    "评论",
    "点赞",
    "收藏",
    "转发",
    "关注",
    "小红书",
    "笔记",
    "红薯",
    "学习",
    "分享",
    "感谢",
    "作为",
    "现在",
    "别人",
    "这样",
    "知道",
    "看到",
    "其实",
    "随便",
    "大家",
    "需要",
    "很多",
    "一直",
    "已经",
    "起来",
    "发现",
    "还有",
    "这种",
    "一样",
    "时候",
    "这里",
    "东西",
    "直接",
    "问题",
    "为什么",
    "不要",
    "不到",
    "只有",
    "特别",
    "一定",
}

BOILERPLATE_MARKERS = [
    "非常重视社区环境",
    "始终保持尊重他人",
    "保护隐私",
    "共同维护良好",
    "保障正常的交流和分享",
    "要发布十五个字以上",
    "十五个字以上才可以涨热度",
    "复制这段话",
    "复制一遍就能恢复",
]


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def clean_text(text: str) -> str:
    text = re.sub(r"https?://\S+", " ", str(text))
    text = re.sub(r"@\S+", " ", text)
    text = re.sub(r"\[[^\]]{1,12}R?\]", " ", text)
    text = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def is_boilerplate_noise(text: str) -> bool:
    marker_count = sum(1 for marker in BOILERPLATE_MARKERS if marker in text)
    return marker_count >= 2


def tokenize(text: str) -> list[str]:
    cleaned = clean_text(text)
    words = []
    for word in jieba.lcut(cleaned):
        word = word.strip().lower()
        if not word or word in STOPWORDS:
            continue
        if len(word) == 1:
            continue
        if word.isdigit():
            continue
        words.append(word)
    return words


def to_int(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def ts_to_str(value: object) -> str:
    ts = to_int(value)
    if not ts:
        return ""
    return datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d %H:%M:%S")


def build_note_meta() -> dict[str, dict]:
    meta: dict[str, dict] = {}
    for path in TITLE_FILES + [DETAILS_FILE]:
        for row in load_jsonl(path):
            note_id = row.get("note_id") or row.get("id")
            if not note_id:
                continue
            current = meta.setdefault(str(note_id), {})
            for key in [
                "title",
                "desc",
                "type",
                "liked_count",
                "collected_count",
                "comment_count",
                "share_count",
                "note_url",
                "source_keyword",
                "last_modify_ts",
            ]:
                if row.get(key) not in (None, ""):
                    current[key] = row.get(key)
    return meta


def dedupe_comments(rows: list[dict]) -> list[dict]:
    seen = set()
    deduped = []
    for idx, row in enumerate(rows):
        note_id = str(row.get("note_id") or "")
        comment_id = str(row.get("comment_id") or f"{note_id}-{idx}")
        if not note_id or comment_id in seen:
            continue
        seen.add(comment_id)
        deduped.append(row)
    return deduped


def select_note_ids(comments: list[dict]) -> list[str]:
    ids = []
    seen = set()
    for row in comments:
        note_id = str(row.get("note_id") or "")
        if note_id and note_id not in seen:
            ids.append(note_id)
            seen.add(note_id)
        if len(ids) >= TOP_NOTES_LIMIT:
            break
    return ids


def export_clean_data(comments: list[dict], note_ids: list[str], note_meta: dict[str, dict]) -> pd.DataFrame:
    note_set = set(note_ids)
    records = []
    for row in comments:
        note_id = str(row.get("note_id") or "")
        if note_id not in note_set:
            continue
        text = clean_text(row.get("content", ""))
        if not text:
            continue
        records.append(
            {
                "comment_id": row.get("comment_id", ""),
                "note_id": note_id,
                "note_title": note_meta.get(note_id, {}).get("title", ""),
                "content": text,
                "is_boilerplate_noise": is_boilerplate_noise(text),
                "like_count": to_int(row.get("like_count")),
                "sub_comment_count": to_int(row.get("sub_comment_count")),
                "ip_location": row.get("ip_location", ""),
                "create_time": ts_to_str(row.get("create_time")),
            }
        )
    df = pd.DataFrame(records)
    df.to_csv(ANALYSIS_DIR / "comments_50posts_clean.csv", index=False, encoding="utf-8-sig")
    df.to_json(ANALYSIS_DIR / "comments_50posts_clean.jsonl", orient="records", lines=True, force_ascii=False)
    return df


def export_note_summary(comments_df: pd.DataFrame, note_ids: list[str], note_meta: dict[str, dict]) -> pd.DataFrame:
    grouped = comments_df.groupby("note_id").agg(
        crawled_comments=("comment_id", "count"),
        crawled_comment_likes=("like_count", "sum"),
        max_comment_like=("like_count", "max"),
    )
    records = []
    for idx, note_id in enumerate(note_ids, 1):
        meta = note_meta.get(note_id, {})
        stats = grouped.loc[note_id].to_dict() if note_id in grouped.index else {}
        records.append(
            {
                "rank": idx,
                "note_id": note_id,
                "title": meta.get("title", ""),
                "source_keyword": meta.get("source_keyword", ""),
                "note_liked_count": to_int(meta.get("liked_count")),
                "note_collected_count": to_int(meta.get("collected_count")),
                "note_comment_count": to_int(meta.get("comment_count")),
                "crawled_comments": int(stats.get("crawled_comments", 0)),
                "crawled_comment_likes": int(stats.get("crawled_comment_likes", 0)),
                "max_comment_like": int(stats.get("max_comment_like", 0)),
                "note_url": meta.get("note_url", ""),
            }
        )
    df = pd.DataFrame(records)
    df.to_csv(ANALYSIS_DIR / "target_notes_50_summary.csv", index=False, encoding="utf-8-sig")
    df.to_json(ANALYSIS_DIR / "target_notes_50_summary.jsonl", orient="records", lines=True, force_ascii=False)
    return df


def export_top_comments(comments_df: pd.DataFrame) -> None:
    top_comments = (
        comments_df.sort_values(["note_id", "like_count"], ascending=[True, False])
        .groupby("note_id")
        .head(20)
        .reset_index(drop=True)
    )
    top_comments.to_csv(ANALYSIS_DIR / "top_liked_comments_by_note_top20.csv", index=False, encoding="utf-8-sig")
    top_comments.to_json(ANALYSIS_DIR / "top_liked_comments_by_note_top20.jsonl", orient="records", lines=True, force_ascii=False)


def export_word_frequency(comments_df: pd.DataFrame) -> tuple[pd.DataFrame, Counter, list[list[str]]]:
    analysis_df = comments_df[~comments_df["is_boilerplate_noise"]].copy()
    analysis_df.to_csv(ANALYSIS_DIR / "comments_for_text_analysis.csv", index=False, encoding="utf-8-sig")
    analysis_df.to_json(ANALYSIS_DIR / "comments_for_text_analysis.jsonl", orient="records", lines=True, force_ascii=False)
    token_docs = [tokenize(text) for text in analysis_df["content"].fillna("")]
    freq = Counter(word for words in token_docs for word in words)
    rows = [{"word": word, "count": count} for word, count in freq.most_common()]
    df = pd.DataFrame(rows)
    df.to_csv(ANALYSIS_DIR / "word_frequency.csv", index=False, encoding="utf-8-sig")
    return df, freq, token_docs


def export_wordcloud(freq: Counter) -> None:
    if not freq:
        return
    cloud = WordCloud(
        font_path=str(FONT_PATH),
        width=1800,
        height=1200,
        background_color="white",
        max_words=220,
        collocations=False,
        random_state=42,
    ).generate_from_frequencies(freq)
    cloud.to_file(str(ANALYSIS_DIR / "wordcloud.png"))


def export_lda(token_docs: list[list[str]]) -> pd.DataFrame:
    docs = [" ".join(words) for words in token_docs if len(words) >= 2]
    if len(docs) < LDA_TOPIC_COUNT:
        raise RuntimeError("有效评论文档太少，LDA没法跑。")
    vectorizer = CountVectorizer(
        token_pattern=r"(?u)\b\w+\b",
        min_df=3,
        max_df=0.5,
        max_features=2500,
    )
    matrix = vectorizer.fit_transform(docs)
    lda = LatentDirichletAllocation(
        n_components=LDA_TOPIC_COUNT,
        max_iter=30,
        learning_method="batch",
        random_state=42,
    )
    lda.fit(matrix)
    words = vectorizer.get_feature_names_out()
    rows = []
    for topic_idx, topic in enumerate(lda.components_, 1):
        top_indices = topic.argsort()[-LDA_TOP_WORDS:][::-1]
        top_words = [words[i] for i in top_indices]
        rows.append(
            {
                "topic_id": topic_idx,
                "top_words": " / ".join(top_words),
                "topic_weight": round(float(topic.sum()), 4),
            }
        )
    df = pd.DataFrame(rows)
    df.to_csv(ANALYSIS_DIR / "lda_topics.csv", index=False, encoding="utf-8-sig")
    return df


def write_summary(
    comments_df: pd.DataFrame,
    notes_df: pd.DataFrame,
    word_df: pd.DataFrame,
    lda_df: pd.DataFrame,
) -> None:
    source_counts = notes_df["source_keyword"].replace("", "未知").value_counts().to_dict()
    top_words = "、".join(word_df.head(30)["word"].tolist())
    topic_lines = "\n".join(
        f"- 主题{row.topic_id}: {row.top_words}" for row in lda_df.itertuples(index=False)
    )
    summary = f"""# 小红书运营吐槽评论文本分析

## 数据口径

- 原始帖子标题候选：初始搜索 200 行，补充搜索 300 行。
- 最终评论样本：{len(notes_df)} 个帖子，{len(comments_df)} 条去重评论。
- 文本分析样本：{int((~comments_df["is_boilerplate_noise"]).sum())} 条；剔除疑似复制模板评论 {int(comments_df["is_boilerplate_noise"].sum())} 条。
- 抓取策略：每个帖子最多抓取 100 条主评论；可见评论不足 100 的帖子按实际数量保留。
- 隐私处理：分析文件不导出用户ID、昵称、头像。

## 来源关键词分布

{json.dumps(source_counts, ensure_ascii=False, indent=2)}

## 高频词 Top30

{top_words}

## LDA 主题

{topic_lines}

## 产物

- `comments_50posts_clean.csv/jsonl`
- `comments_for_text_analysis.csv/jsonl`
- `target_notes_50_summary.csv/jsonl`
- `top_liked_comments_by_note_top20.csv/jsonl`
- `word_frequency.csv`
- `lda_topics.csv`
- `wordcloud.png`
"""
    (ANALYSIS_DIR / "summary.md").write_text(summary, encoding="utf-8")


def main() -> None:
    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    for word in CUSTOM_WORDS:
        jieba.add_word(word)

    comments = dedupe_comments(load_jsonl(COMMENTS_FILE))
    note_ids = select_note_ids(comments)
    note_meta = build_note_meta()
    comments_df = export_clean_data(comments, note_ids, note_meta)
    notes_df = export_note_summary(comments_df, note_ids, note_meta)
    export_top_comments(comments_df)
    word_df, freq, token_docs = export_word_frequency(comments_df)
    export_wordcloud(freq)
    lda_df = export_lda(token_docs)
    write_summary(comments_df, notes_df, word_df, lda_df)

    print(f"notes={len(notes_df)}")
    print(f"comments={len(comments_df)}")
    print(f"analysis_dir={ANALYSIS_DIR.resolve()}")
    print("top_words=" + " / ".join(word_df.head(20)["word"].tolist()))


if __name__ == "__main__":
    main()
