from __future__ import annotations

import math
import re
from collections import Counter
from pathlib import Path

import pandas as pd


BASE_DIR = Path("data/xhs_ops_research_20260618/analysis")
COMMENTS_FILE = BASE_DIR / "comments_for_text_analysis.csv"
NOTES_FILE = BASE_DIR / "target_notes_50_summary.csv"
OUTPUT_FILE = BASE_DIR / "selected_need_signals_top100.csv"
TARGET_SIZE = 100
MAX_PER_NOTE = 8
MAX_TITLES = 20


CATEGORY_RULES = {
    "低流量焦虑": {
        "keywords": ["流量", "小眼睛", "浏览量", "播放量", "推流", "曝光", "没人看", "没流量", "个位数", "不过百", "破百", "搜不到"],
        "need": "需要流量诊断、冷启动解释、推流机制和低浏览量修复方案",
    },
    "限流违规困惑": {
        "keywords": ["限流", "违规", "违禁词", "审核", "申诉", "屏蔽", "处罚", "封号", "异常", "提示违规", "搜不到"],
        "need": "需要违规排查清单、内容安全边界、申诉和账号恢复指导",
    },
    "求诊断求指导": {
        "keywords": ["帮我看看", "帮我分析", "看看我的", "求帮", "求指导", "请教", "怎么办", "哪里有问题", "有什么问题", "麻烦看", "诊断"],
        "need": "需要账号或单篇笔记诊断、明确问题定位和可执行修改建议",
    },
    "内容文案卡点": {
        "keywords": ["文案", "标题", "封面", "开头", "选题", "脚本", "内容", "爆款", "模板", "素材", "怎么写", "写不出来"],
        "need": "需要爆款文案、标题封面、选题模板和可复制内容框架",
    },
    "起号涨粉矩阵": {
        "keywords": ["新号", "起号", "矩阵", "账号", "定位", "垂直", "运营", "涨粉", "粉丝", "断更", "活跃", "养号"],
        "need": "需要起号路径、账号定位、矩阵运营和涨粉节奏规划",
    },
    "工具投放提效": {
        "keywords": ["薯条", "投流", "投放", "工具", "ai", "飞书", "剪映", "数据", "效率", "客流"],
        "need": "需要工具清单、AI提效流程、投放策略和数据复盘方法",
    },
    "互助社群增长": {
        "keywords": ["一换一", "互赞", "互助", "挨个", "回访", "举手", "dd", "浏览一下", "互相"],
        "need": "需要低成本冷启动、社群互助反馈和早期互动增长方法",
    },
}

EMOTION_WORDS = [
    "焦虑",
    "崩溃",
    "救命",
    "哭",
    "太难",
    "难",
    "烦",
    "疯",
    "无语",
    "服了",
    "气",
    "emo",
    "累",
    "绝望",
    "迷茫",
    "不懂",
    "到底",
    "为什么",
    "怎么办",
    "求",
    "正常吗",
    "不行",
    "没人",
    "好低",
    "没用",
    "绷不住",
    "急",
    "害怕",
    "担心",
    "避雷",
    "踩雷",
]

LOW_INFO_PATTERNS = [
    r"^1+$",
    r"^111+$",
    r"^dd+$",
    r"^看看$",
    r"^谢谢$",
    r"^加油$",
    r"^蹲$",
]

TEMPLATE_MARKERS = [
    "复制一遍",
    "复制这段话",
    "复制粘贴这段话",
    "复制粘贴",
    "特此反馈",
    "恳请团队",
    "官方能重新审核",
    "审核员您好",
    "审核员 你好",
    "薯队能够慎重考虑",
    "始终坚信",
    "严格遵守社区",
    "积极分享正能量",
    "自觉维护良好的互动环境",
    "社区规范与公约",
    "恢复其流量及薯条推广功能",
    "十五个字以上才可以涨热度",
    "借个楼评论",
    "尊敬的薯队审核员",
    "恳请你慎重考虑",
    "深知违规行为的重要性",
    "改过自新重新开始",
    "不胜感激",
    "本人账号没有发布任何违规内容",
    "本人非常愿意根据平台",
    "本人已经明白社区规范",
    "辛苦核实反馈",
    "恢复账号",
]

ADVICE_OR_BRAG_MARKERS = [
    "告诉大家一个技巧",
    "我已经一万粉",
    "我已经把小红书玩明白了",
    "我才起号",
    "不信你可以来我主页",
    "你可以看我主页",
    "其实起号压根就没那么难",
    "其实起号一点都不难",
    "第一 要把帐号活跃起来",
    "只要你不断更",
    "做火了就是博主",
    "听劝 养号真的有用",
    "作为新手博主 我算是把",
    "作为美妆博主 我算是把",
    "新人要日更",
    "发文之后不要立刻离开",
    "心得分享一下",
    "别着急 涨粉慢",
    "其实小红书也不是特别难运营",
    "我找到流量密码了",
    "我算是通过这个笔记学到了",
    "告诉大家一个技巧",
    "大家可以借鉴我的",
    "到处增加曝光",
    "系统就会识别到你是活跃用户",
    "来我主页看",
    "照抄就行",
    "到处评论互动",
    "别人就会好奇",
    "看我是什么玩意",
    "新人一开始不要太着急",
    "账号不够活跃",
    "只要内容好根本不影响",
    "我除了爆款",
    "我的理解是",
    "我觉得小红书定位",
    "做小红书的目的是什么",
    "真的 现在有一股风气",
    "你猜猜那些新媒体运营",
    "有点局限了",
    "新媒体运营方面的",
    "奇怪还总有人问",
    "短短几天",
    "短短一个月",
    "涨到现在",
    "冷知识",
    "红薯推广就能搞定",
    "没有小眼睛也不要担心",
    "隔三差五的去修改一下",
    "不想管小眼睛",
    "无所求必满载而归",
    "能看出AI味",
    "完全可以 用小红书网友",
    "提示词",
    "每天阅读 点赞 收藏 评论",
    "模仿活跃用户",
    "普通人的阅读习惯",
    "提高自身的权重",
    "有争议的 现在很多人起号",
    "这波流量持续不了多久",
    "技术是工具 人才是主角",
    "符合正能量要求",
    "希望平台多鼓励原创",
]

CREATOR_CONTEXT_TERMS = [
    "小红书",
    "账号",
    "笔记",
    "内容",
    "标题",
    "封面",
    "文案",
    "选题",
    "视频",
    "图文",
    "作品",
    "主页",
    "博主",
    "粉丝",
    "流量",
    "小眼睛",
    "浏览量",
    "播放量",
    "推流",
    "曝光",
    "违规",
    "限流",
    "审核",
    "申诉",
    "屏蔽",
    "薯条",
    "投流",
    "运营",
    "起号",
    "养号",
    "矩阵",
    "赛道",
    "发布",
    "剪视频",
    "tag",
    "ai",
    "原创",
    "互赞",
    "互助",
]

INTERACTION_SPAM_MARKERS = [
    "回1就去看看",
    "回复1",
    "回复1我去看",
    "扣6我去看",
    "点1 去看",
    "点1去看",
    "滴1我去看",
    "看完dd",
    "看完回复",
    "我去看你",
    "我立刻回点",
    "挨个去浏览",
    "挨个看",
    "浏览一下就行",
    "浏览量低于200的回复",
    "浏览量低于200的宝宝举手",
    "浏览量低于500的宝宝举手",
    "浏览量低于500的请举手",
    "来看看我的",
    "可以顺便看看我的",
    "来瞅瞅我",
    "互助互利",
    "新人博主需要流量",
    "求浏览量",
    "谁帮我看看",
    "好心人也来看看我",
    "宝宝们能不能看看我的主页",
    "我一定会回看的",
    "能不能给一个赞",
    "给一个赞支持",
    "给我点赞",
    "给我推推流",
    "帮我带一下流量",
    "带一下流量",
    "实体店快撑不住",
    "大家帮我去看看",
    "求互",
    "点的时候停留",
    "一换一 一直在",
    "我也看你",
    "我去看看你",
    "都看看我吧",
    "留个言 我去看看你",
    "浏览量低于100",
    "浏览量低于500",
    "浏览量低于600",
    "dd我",
]

OFF_TOPIC_MARKERS = [
    "考公",
    "考研",
    "跨考",
    "选专业",
    "志愿",
    "留学",
    "美国读研",
    "求职",
    "hr让我",
    "我是hr",
    "住家陪伴师",
    "陪伴师",
    "中学生",
    "叔叔阿姨",
    "应聘",
    "岗位要求",
    "找工作",
    "工作经验",
    "工资",
    "学历要求",
    "电商的运营助理",
    "离婚",
    "树洞",
    "南昌",
    "银行面试",
    "个人主页怎么办",
    "升学",
    "实体店",
    "直播间",
    "卖货账号",
    "NPD",
    "父PUA",
    "心理和英语",
    "网络即世界",
    "选定道路",
    "别人一味的给你建议",
]

ADVICE_INTRO_PATTERNS = [
    r"^告诉大家",
    r"^听劝",
    r"^作为.{0,8}博主",
    r"^我已经把",
    r"^我找到",
    r"^我算是通过",
    r"^别着急",
    r"^只要内容好",
    r"^我自己这阵子也研究",
    r"^运营很简单",
    r"^我觉得",
    r"^我的理解是",
    r"^做小红书的目的是什么",
    r"^真的 现在",
    r"^新人一开始",
    r"^你猜猜",
    r"^有点局限",
    r"^奇怪还总有人问",
    r"^账号不够活跃",
    r"^只要内容好",
    r"^冷知识",
    r"^没有小眼睛也不要担心",
    r"^不想管小眼睛",
    r"^能看出AI味",
]

TEACHING_TITLE_MARKERS = [
    "攻略",
    "指南",
    "技巧",
    "必看",
    "直接抄",
    "亲测有效",
    "路径全解答",
    "讲清",
    "分享一个",
    "作弊",
    "不要做",
    "这样",
    "5步",
    "六大",
]

TITLE_PAIN_MARKERS = [
    "正常吗",
    "为什么",
    "搜不到",
    "没有浏览量",
    "浏览量才",
    "小眼睛",
    "低于",
    "卡死",
    "违规",
    "限流",
    "太难",
    "不火",
    "做不起来",
]


def normalize_text(text: str) -> str:
    text = str(text).strip()
    text = re.sub(r"\s+", " ", text)
    return text


def duplicate_key(text: str) -> str:
    text = normalize_text(text).lower()
    text = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]+", "", text)
    text = re.sub(r"\d+", "0", text)
    return text[:80]


def is_low_info(text: str) -> bool:
    compact = re.sub(r"\s+", "", normalize_text(text).lower())
    if len(compact) < 8:
        return True
    return any(re.match(pattern, compact) for pattern in LOW_INFO_PATTERNS)


def is_template_or_advice(text: str) -> bool:
    if any(marker in text for marker in TEMPLATE_MARKERS + ADVICE_OR_BRAG_MARKERS):
        return True
    return any(re.search(pattern, text) for pattern in ADVICE_INTRO_PATTERNS)


def has_creator_context(text: str) -> bool:
    lowered = text.lower()
    return any(term.lower() in lowered for term in CREATOR_CONTEXT_TERMS)


def is_interaction_spam(text: str) -> bool:
    lowered = text.lower()
    return any(marker.lower() in lowered for marker in INTERACTION_SPAM_MARKERS)


def is_off_topic(text: str) -> bool:
    lowered = text.lower()
    return any(marker.lower() in lowered for marker in OFF_TOPIC_MARKERS)


def has_need_signal(text: str, source_type: str) -> bool:
    if source_type == "note_title":
        if any(marker in text for marker in TEACHING_TITLE_MARKERS) and not any(marker in text for marker in TITLE_PAIN_MARKERS):
            return False
        return any(marker in text for marker in TITLE_PAIN_MARKERS)

    if source_type == "comment" and not re.search(
        r"我|我的|自己|新手|新人|刚|求|请教|帮我|帮忙|看看|怎么办|正常吗|为什么|到底|不懂|不知道|搞不懂|不理解|无语|服了|急|焦虑|迷茫|不会|没人|搜不到|违规|限流|屏蔽|小眼睛|浏览量|流量|播放量|发了|发布|账号|笔记|作品",
        text,
    ):
        return False
    if source_type == "comment" and not re.search(
        r"求|请教|帮我|帮忙|看看我的|老师|老大|怎么办|正常吗|为什么|到底|不懂|不知道|搞不懂|不理解|无语|服了|急|焦虑|迷茫|不会|没人|搜不到|违规|限流|屏蔽|异常|很低|太低|个位数|几十|没有流量|没流量|没浏览|小眼睛|浏览量|播放量|掉|改了|发了|新开|刚开|起号|运营|做账号|怎么改善",
        text,
    ):
        return False
    if re.search(r"求|请教|帮我|帮忙|看看我的|看看我|麻烦|怎么办|正常吗|为什么|到底|怎么做|怎么改|有没有|能不能", text):
        return True
    if emotion_score(text) > 0:
        return True
    return bool(
        re.search(
            r"(我的|我|账号|笔记|内容|标题|封面|流量|浏览量).{0,12}(没|不|低|掉|搜不到|违规|限流|屏蔽|卡|焦虑|迷茫|不会|不知道|不懂)",
            text,
        )
    )


def match_categories(text: str) -> list[str]:
    matched = []
    lowered = text.lower()
    for category, rule in CATEGORY_RULES.items():
        if any(keyword.lower() in lowered for keyword in rule["keywords"]):
            matched.append(category)
    return matched


def matched_keywords(text: str) -> list[str]:
    lowered = text.lower()
    hits = []
    for rule in CATEGORY_RULES.values():
        for keyword in rule["keywords"]:
            if keyword.lower() in lowered:
                hits.append(keyword)
    for word in EMOTION_WORDS:
        if word.lower() in lowered:
            hits.append(word)
    return sorted(set(hits), key=lambda item: (-len(item), item))


def emotion_score(text: str) -> int:
    lowered = text.lower()
    score = sum(1 for word in EMOTION_WORDS if word.lower() in lowered)
    score += text.count("！") + text.count("!") + text.count("？") + text.count("?")
    if re.search(r"(.)\1{2,}", text):
        score += 1
    return score


def category_score(categories: list[str]) -> int:
    return sum(3 for _ in categories)


def best_need_hint(categories: list[str]) -> str:
    if not categories:
        return ""
    return CATEGORY_RULES[categories[0]]["need"]


def score_record(text: str, like_count: int, source_type: str) -> tuple[float, list[str], list[str]]:
    categories = match_categories(text)
    if not categories:
        return 0.0, [], []
    score = category_score(categories)
    score += emotion_score(text) * 2.2
    if re.search(r"我|我的|自己|新手|新人|小白", text):
        score += 2
    if re.search(r"求|请教|帮我|看看|怎么办|正常吗|为什么|到底", text):
        score += 4
    if 18 <= len(text) <= 180:
        score += 2
    if source_type == "note_title":
        score += 5
    score += min(math.log1p(max(like_count, 0)), 5) * 0.8
    return score, categories, matched_keywords(text)


def load_candidates() -> list[dict]:
    comments = pd.read_csv(COMMENTS_FILE).fillna("")
    notes = pd.read_csv(NOTES_FILE).fillna("")
    note_meta = notes.set_index("note_id").to_dict("index")

    candidates = []
    for row in comments.itertuples(index=False):
        text = normalize_text(row.content)
        if (
            is_low_info(text)
            or is_template_or_advice(text)
            or is_interaction_spam(text)
            or is_off_topic(text)
            or not has_creator_context(text)
            or not has_need_signal(text, "comment")
        ):
            continue
        if len(text) > 320:
            continue
        note = note_meta.get(row.note_id, {})
        score, categories, keywords = score_record(text, int(row.like_count), "comment")
        if score <= 0:
            continue
        candidates.append(
            {
                "source_type": "comment",
                "note_id": row.note_id,
                "note_url": note.get("note_url", ""),
                "note_title": normalize_text(row.note_title),
                "source_keyword": note.get("source_keyword", ""),
                "text": text,
                "like_count": int(row.like_count),
                "score": round(score, 3),
                "signal_type": " / ".join(categories),
                "matched_keywords": " / ".join(keywords[:12]),
                "need_hint": best_need_hint(categories),
            }
        )

    for row in notes.itertuples(index=False):
        text = normalize_text(row.title)
        if is_low_info(text) or is_template_or_advice(text) or is_off_topic(text) or not has_need_signal(text, "note_title"):
            continue
        if len(text) > 220:
            continue
        score, categories, keywords = score_record(text, int(row.note_liked_count), "note_title")
        if score <= 0:
            continue
        candidates.append(
            {
                "source_type": "note_title",
                "note_id": row.note_id,
                "note_url": row.note_url,
                "note_title": text,
                "source_keyword": row.source_keyword,
                "text": text,
                "like_count": int(row.note_liked_count),
                "score": round(score, 3),
                "signal_type": " / ".join(categories),
                "matched_keywords": " / ".join(keywords[:12]),
                "need_hint": best_need_hint(categories),
            }
        )
    return candidates


def select_top(candidates: list[dict]) -> pd.DataFrame:
    selected = []
    seen_text = set()
    per_note = Counter()
    title_count = 0

    for item in sorted(candidates, key=lambda row: row["score"], reverse=True):
        key = duplicate_key(item["text"])
        if key in seen_text:
            continue
        if per_note[item["note_id"]] >= MAX_PER_NOTE:
            continue
        if item["source_type"] == "note_title" and title_count >= MAX_TITLES:
            continue
        selected.append(item)
        seen_text.add(key)
        per_note[item["note_id"]] += 1
        if item["source_type"] == "note_title":
            title_count += 1
        if len(selected) >= TARGET_SIZE:
            break

    df = pd.DataFrame(selected)
    df.insert(0, "rank", range(1, len(df) + 1))
    columns = [
        "rank",
        "source_type",
        "note_id",
        "note_url",
        "note_title",
        "source_keyword",
        "text",
        "like_count",
        "score",
        "signal_type",
        "matched_keywords",
        "need_hint",
    ]
    df = df[columns]
    return df


def main() -> None:
    candidates = load_candidates()
    selected = select_top(candidates)
    selected.to_csv(OUTPUT_FILE, index=False, encoding="utf-8-sig")
    print(f"candidates={len(candidates)}")
    print(f"selected={len(selected)}")
    print(f"output={OUTPUT_FILE.resolve()}")
    print(selected[["rank", "source_type", "signal_type", "text"]].head(20).to_string(index=False))


if __name__ == "__main__":
    main()
