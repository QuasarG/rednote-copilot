#!/usr/bin/env python3
"""
Generate a simple, vertical Excalidraw file for the 2-week lean validation plan (Chinese).
Output: docs/validation_plan_2week.excalidraw
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_PATH = ROOT / "docs/validation_plan_2week.excalidraw"
OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

C_TEXT = "#1f2937"
C_SUB = "#6b7280"
C_BOX = "#ffffff"
C_EDGE = "#374151"
C_LIGHT = "#f3f4f6"
C_BLUE = "#dbeafe"
C_BLUE_EDGE = "#2563eb"
C_GREEN = "#d1fae5"
C_GREEN_EDGE = "#059669"
C_YELLOW = "#fef3c7"
C_YELLOW_EDGE = "#d97706"

FONT = 20
FONT_SM = 16
FONT_LG = 28
STROKE = 1.5


def rect(x, y, w, h, fill=C_BOX, stroke=C_EDGE, label="", font=FONT_SM, color=C_TEXT):
    elems = [{
        "type": "rectangle",
        "x": x, "y": y, "width": w, "height": h,
        "angle": 0,
        "strokeColor": stroke,
        "backgroundColor": fill,
        "fillStyle": "solid",
        "strokeWidth": STROKE,
        "strokeStyle": "solid",
        "roughness": 0,
        "opacity": 100,
        "groupIds": [],
        "frameId": None,
        "roundness": {"type": 3, "value": 4},
        "seed": int((x + y) * 1000),
        "version": 1,
        "versionNonce": int((x + y) * 2000),
        "isDeleted": False,
        "boundElements": None,
        "updated": 1,
        "link": None,
        "locked": False,
        "index": None,
    }]
    if label:
        elems.append(text(x + w / 2, y + h / 2, label, font=font, color=color, align="center"))
    return elems


def text(x, y, content, font=FONT_SM, color=C_TEXT, align="left"):
    return {
        "type": "text",
        "x": x, "y": y,
        "width": len(content) * (font * 0.55),
        "height": font * 1.4,
        "angle": 0,
        "strokeColor": color,
        "backgroundColor": "transparent",
        "fillStyle": "solid",
        "strokeWidth": 1,
        "strokeStyle": "solid",
        "roughness": 0,
        "opacity": 100,
        "groupIds": [],
        "frameId": None,
        "roundness": None,
        "seed": int((x + y) * 3000),
        "version": 1,
        "versionNonce": int((x + y) * 4000),
        "isDeleted": False,
        "boundElements": None,
        "updated": 1,
        "link": None,
        "locked": False,
        "text": content,
        "fontSize": font,
        "fontFamily": 5,
        "textAlign": align,
        "verticalAlign": "middle",
        "containerId": None,
        "originalText": content,
        "lineHeight": 1.35,
        "baseline": 17,
        "index": None,
    }


x = 100
w = 520
y = 40
gap = 30
elements = []

# 标题
elements.append(text(x + w / 2, y, "2 周精益验证计划", font=FONT_LG, color=C_TEXT, align="center"))
y += 45
elements.append(text(x + w / 2, y, "在投入重工程前，先验证真实采纳率与付费意愿", font=FONT_SM, color=C_SUB, align="center"))
y += 60

# 北极星指标
elements.extend(rect(x, y, w, 95, fill=C_LIGHT, stroke=C_EDGE))
elements.append(text(x + 20, y + 25, "北极星指标", font=FONT, color=C_TEXT))
elements.append(text(x + 20, y + 55, "• 真实采纳率：AI 文案未经人工大改即发布 > 40%\n• 发布 48h 后的违规拦截成功率\n• 发布 48h 后的流量跑赢率", font=FONT_SM, color=C_TEXT))
y += 95 + gap

# Phase 1
phase_h = 120
elements.extend(rect(x, y, 90, phase_h, fill=C_BLUE, stroke=C_BLUE_EDGE, label="Day\n1–3", font=FONT, color=C_TEXT))
elements.extend(rect(x + 110, y, w - 110, phase_h, fill=C_BOX, stroke=C_EDGE))
elements.append(text(x + 130, y + 25, "冷启动与精准定向招募", font=FONT, color=C_TEXT))
elements.append(text(x + 130, y + 55, "复用 MediaCrawler 抓取近期吐槽“小眼睛个位数/限流”的\n中腰部店主，私信邀请，组建 30 人高意向商户内测群。", font=FONT_SM, color=C_TEXT))
y += phase_h + gap

# Phase 2
phase_h = 150
elements.extend(rect(x, y, 90, phase_h, fill=C_YELLOW, stroke=C_YELLOW_EDGE, label="Day\n4–9", font=FONT, color=C_TEXT))
elements.extend(rect(x + 110, y, w - 110, phase_h, fill=C_BOX, stroke=C_EDGE))
elements.append(text(x + 130, y + 25, "灰度投放与核心漏斗追踪", font=FONT, color=C_TEXT))
elements.append(text(x + 130, y + 55, "用 Streamlit/Gradio 给 LangGraph 套极简 Web 外壳。\n要求商户做 A/B 测试发布（AI 文案 vs 人工文案）。\n\n追踪：采纳率、违规拦截成功率、48h 流量跑赢率。", font=FONT_SM, color=C_TEXT))
y += phase_h + gap

# Phase 3
phase_h = 135
elements.extend(rect(x, y, 90, phase_h, fill=C_GREEN, stroke=C_GREEN_EDGE, label="Day\n10–14", font=FONT, color=C_TEXT))
elements.extend(rect(x + 110, y, w - 110, phase_h, fill=C_BOX, stroke=C_EDGE))
elements.append(text(x + 130, y + 25, "冒烟测试与双轨定性复盘", font=FONT, color=C_TEXT))
elements.append(text(x + 130, y + 55, "宣布内测结束，抛出 9.9 元/周早鸟版付款码，\n用真实支付转化率测算商业潜力。\n对付费与流失用户进行 1v1 深访，输出 V2.0 PRD。", font=FONT_SM, color=C_TEXT))
y += phase_h + gap

# 资源投入
elements.extend(rect(x, y, w, 115, fill=C_LIGHT, stroke=C_EDGE))
elements.append(text(x + 20, y + 25, "资源投入（极轻量）", font=FONT, color=C_TEXT))
elements.append(text(x + 20, y + 55, "研发：0.5 人力 × 1 天（熟悉 Streamlit/Gradio 的前端/全栈，\n        把 Python 后端套上极简网页外壳）\n预算：约 1500 元\n  • 大模型 API Token 约 500 元\n  • 用户调研激励约 1000 元", font=FONT_SM, color=C_TEXT))
y += 115 + gap

# 原则
elements.append(text(x + w / 2, y, "原则：不追求完美的充值系统，先验证采纳率与付费意愿。",
                     font=FONT_SM, color=C_SUB, align="center"))

excalidraw_data = {
    "type": "excalidraw",
    "version": 2,
    "source": "scripts/generate_validation_plan_excalidraw.py",
    "elements": elements,
    "appState": {
        "gridSize": 20,
        "viewBackgroundColor": "#ffffff",
        "theme": "light",
    },
    "files": {},
}

with open(OUT_PATH, "w", encoding="utf-8") as f:
    json.dump(excalidraw_data, f, ensure_ascii=False, indent=2)

print(f"Saved: {OUT_PATH}")
