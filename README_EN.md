<div align="center">

<img src="rednote_matrix/web/static/rednote-copilot-logo.png" alt="RedNote Copilot logo" width="720">

# RedNote Copilot

[中文 README](./README.md)

[![Release](https://img.shields.io/badge/Release-v0.1.0--alpha-0066FF?style=flat-square)](./CHANGELOG.md)
[![Python](https://img.shields.io/badge/Python-3.13-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-00C853?style=flat-square)](./LICENSE)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-1C3C3C?style=flat-square&logo=langchain&logoColor=white)](https://www.langchain.com/langgraph)
[![Docker](https://img.shields.io/badge/Docker-ready-2496ED?style=flat-square&logo=docker&logoColor=white)](./Dockerfile)
[![Tests](https://img.shields.io/badge/Tests-unittest-E5A50A?style=flat-square)](./tests)
[![RAG](https://img.shields.io/badge/RAG-Memory_Agent-7C4DFF?style=flat-square)]()

**AI-native content agent for Xiaohongshu (小红书) brand seeding.**<br>
Research-backed trend mining → structured viral drafting → humanized rewrite → compliance scanning → publish-ready copy.

<!-- HERO: Replace with app/workbench screenshot or demo GIF -->
<!-- Place video/screenshot at: docs/assets/hero-screenshot.png -->
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/hero-screenshot-dark.png">
  <source media="(prefers-color-scheme: light)" srcset="docs/assets/hero-screenshot-light.png">
  <img alt="RedNote Copilot workbench preview" src="docs/assets/hero-screenshot-light.png" width="100%">
</picture>

</div>

---

## Why RedNote Copilot?

Most AI copywriting tools produce generic, templated Xiaohongshu posts that feel like ads and get buried by the algorithm. RedNote Copilot is built from the opposite direction: **we start with real creator anxiety data, mine high-interaction seeding patterns, and let a LangGraph agent generate, humanize, and police the copy until it passes compliance.**

### Workflow Overview

<p align="center">
  <img src="docs/assets/agent-flow.png" alt="RedNote Copilot Agent workflow" width="760">
</p>

### Evidence: what creators actually worry about

We analyzed Xiaohongshu operation-related posts and comments to avoid building the product from imagined needs. The key point from the data is simple: users are not primarily asking for "more copy"; they are anxious about **traffic, visibility, compliance risk, and not knowing what structure makes a note work**.

**Data scope and denominator**

- Raw crawl: **15,832 JSONL rows**
- Target posts: **50 posts** around Xiaohongshu operation difficulty, limited traffic, note violation, multi-account operation, and viral-copy writing
- Comment pipeline: 4,962 raw comments -> 4,798 deduped comments -> **4,623 valid comments**
- Theme analysis denominator: **4,035 cleaned comments** after removing boilerplate/noise and very short unusable comments
- Coding method: fixed dictionary, multi-label topic coding; one comment can match multiple themes

| Rank | Pain point | Theme-coded comments | Share of coded comments | What it means for our agent |
|------|------------|----------------------|-------------------------|-----------------------------|
| 1 | Traffic / visibility anxiety | 810 | **20.07%** | Real-time viral search + trend pattern injection |
| 2 | Account growth & followers | 402 | **9.96%** | Audience-aware hooks and retention-oriented structure |
| 3 | Compliance / restriction risk | 201 | **4.98%** | Local compliance scanner + revision loop |
| 4 | Structured viral framework | 167 | **4.14%** | Title, cover, hook, body, and tag skeleton |
| 5 | Human voice / anti-AI feeling | 55 | **1.36%** | Humanizer node with multi-turn rewrite |

This means the product argument should be framed carefully:

- The strongest observed pain point is **low visibility / low traffic**, not AI itself.
- Compliance and restriction anxiety is lower in frequency, but severe enough to justify a risk-control layer.
- AI-specific complaints are sparse, so "anti-AI feeling" should be positioned as a quality and trust layer, not as the highest-frequency pain point.
- The strongest product need is a workflow: **structured generation -> humanized rewrite -> compliance scan -> revision**, which a one-shot chat model does not provide.

<p align="center">
  <img src="docs/assets/need-theme-counts.png" alt="Theme distribution of Xiaohongshu operation pain points" width="760">
</p>

Research summary:

| Metric | Value |
|--------|------:|
| Target posts | 50 |
| Raw comments | 4,962 |
| Deduplicated comments | 4,798 |
| Valid comments | 4,623 |
| Theme-analysis sample | 4,035 |

<!-- DEMO VIDEO: Replace with your recorded demo -->
<!-- Place demo video at: docs/assets/demo-video.mp4 -->

https://github.com/user-attachments/assets/rednote-copilot-demo-placeholder

---

## Features

<div align="center">

| Research | Drafting | Humanization | Compliance | Delivery |
|----------|----------|--------------|------------|----------|
| Real-time XHS viral search | Structured 6-part seeding skeleton | Anti-AI rewrite with voice memory | Local risk lexicon + LLM judge | CLI, API, and web workbench |
| Trend pattern injection | Dual-title + hook + tag generation | Rejection-driven revision loop | Hard-ad /导流 /极限词 scan | Copy-ready title, body, tags |
| Memory-backed brand facts | Scenario-first storytelling | Max-loop safety cap | Publish checklist + `needs_review` flag | SSE node streaming |

</div>

### Highlights

- **LangGraph-native workflow** — deterministic state machine with explicit reject/revision loops.
- **XHS Core integration** — built-in persistent browser, QR-code login, cookie management, and signed search (inspired by MediaCrawler).
- **Memory layer** — brand facts, product specs, and audience personas persist across sessions.
- **Compliance-first** — every draft is scanned before delivery; risky drafts are sent back for humanization or restructuring.
- **Three interfaces** — command-line, FastAPI, and a Flask web workbench.

---

## Agent Flow

```text
input_parser
  -> market_research_agent   (real-time XHS search if research not completed)
  -> trend_agent             (pattern injection from xhs_viral_seed_20260618)
  -> structure_agent         (6-part seeding skeleton + dual title)
  -> humanizer_agent         (anti-AI, scenario-first rewrite)
  -> compliance_agent        (risk scan + structural score)
  -> revision_router
      -> pass -> final_packager
      -> compliance/ai_trace reject -> humanizer_agent -> compliance_agent
      -> structure reject -> structure_agent -> humanizer_agent -> compliance_agent
```

Nodes run as a LangGraph state machine. `market_research_agent` performs real-time Xiaohongshu search only when the research flag has not been satisfied. `compliance_agent` is the core rejection node: drafts that hit forbidden words, hard-ad导流 patterns, or AI-template phrasing are sent back to `humanizer_agent`; drafts with insufficient structure return to `structure_agent`. If the maximum revision loop count is reached without resolution, the output is flagged as `needs_review` and delivered with a publish checklist.

---

## Quick Start

### 1. Environment

The project uses a local `.venv`. Do not pollute the system Python.

```bash
uv pip install -r requirements.txt
```

### 2. Configure LLM

```bash
cp .env.example .env
```

```bash
# OpenAI-compatible
OPENAI_API_KEY=your_key
OPENAI_MODEL=your_model
OPENAI_BASE_URL=https://api.openai.com/v1

# Or DeepSeek
DEEPSEEK_API_KEY=your_key
OPENAI_MODEL=deepseek-v4-pro
OPENAI_BASE_URL=https://api.deepseek.com
```

### 3. Run CLI demo

```bash
uv run python -m rednote_matrix.cli examples/sample_input.json
uv run python -m rednote_matrix.cli examples/risky_input.json
```

Add `--json` for the full state:

```bash
uv run python -m rednote_matrix.cli examples/sample_input.json --json
```

---

## Usage

### CLI

Default output is user-facing Xiaohongshu copy (title, body, tags). Debug output includes `draft`, `risk_items`, `revision_history`, and `publish_checklist`.

### FastAPI server

```bash
uv run python -m rednote_matrix.server.api
```

Health check:

```bash
curl http://localhost:8000/health
```

Chat endpoint:

```bash
curl -X POST http://localhost:8000/chat \
  -H 'Content-Type: application/json' \
  -d '{
    "message": "帮我写一条种草笔记",
    "debug": true,
    "agent_input": {
      "product_name": "桌面收纳托盘",
      "selling_points": ["小桌面也能放下", "拿东西不用翻半天"],
      "target_audience": "租房小桌面用户",
      "scenario": "晚上一边办公一边找东西",
      "memory_namespace": "brand/acme/tray"
    }
  }'
```

### XHS Core real-time research

Check integration status:

```bash
curl 'http://localhost:8000/integrations/xhs/status?deep=true'
```

Start QR-code login:

```bash
curl -X POST http://localhost:8000/integrations/xhs/login/qrcode \
  -H 'Content-Type: application/json' \
  -d '{"use_virtual_display": true, "timeout_seconds": 180}'
```

Poll the session:

```bash
curl http://localhost:8000/integrations/xhs/login/{session_id}
```

Lightweight search:

```bash
curl -X POST http://localhost:8000/integrations/xhs/search \
  -H 'Content-Type: application/json' \
  -d '{"keywords": ["桌面收纳托盘 爆款笔记", "租房小桌面 桌面收纳托盘"], "max_notes_count": 6}'
```

### Web workbench

```bash
uv run flask --app rednote_matrix.web.workbench run --host 0.0.0.0 --port 8501
```

Open http://localhost:8501

The workbench shows the LangGraph node stream in the center panel and renders final copy into read-only title/body/tags cards on the right.

<!-- WORKBENCH SCREENSHOT: Replace with your actual workbench screenshot -->
<!-- Place screenshot at: docs/assets/workbench-screenshot.png -->

<img alt="Workbench" src="docs/assets/workbench-screenshot.png" width="100%">

---

## Research Methodology

Our trend rules are not hand-waved. They are distilled from a **2026-06-18 lightweight crawl** of high-interaction Xiaohongshu seeding content and creator operations discussions.

### Extracted viral patterns

- **Title patterns**: emotion/suspense first, strong scenario, light contrast, audience label, pitfall-avoidance.
- **Content skeleton**: specific scenario → old struggle/misconception → discovery moment → real feeling → limits/pitfalls → engagement hook.
- **Scoring dimensions**: keyword coverage, structural completeness, timeliness, content quality.

These patterns live in `rednote_matrix/skills/xiaohongshu/` and are consumed by `trend_agent` inside the LangGraph workflow. Full research notes: [`docs/xhs_viral_seed_20260618.md`](./docs/xhs_viral_seed_20260618.md).

### Pricing note

Users may input price information, but prices are used only for internal positioning and budget judgment. Final titles, bodies, and tags do **not** expose specific prices, selling prices, or promotional prices by default, reducing hard-ad and review risk.

---

## Docker

```bash
docker build -t rednote-matrix-agent .
docker run --rm rednote-matrix-agent
```

The image starts the FastAPI server on port `8000` by default.

To run the Flask workbench:

```bash
docker run --rm -p 8501:8501 --env-file .env -v "$PWD/data:/app/data" rednote-matrix-agent \
  flask --app rednote_matrix.web.workbench run --host 0.0.0.0 --port 8501
```

Or use Docker Compose:

```bash
docker compose up --build
```

The Docker image installs `requirements-agent.txt` (API, RAG, memory, and XHS Core) and pre-installs Playwright Chromium. Xvfb is bundled for QR-code login without a host display.

---

## Testing

```bash
uv run python -m unittest discover -s tests -v
```

---

## Roadmap

- [x] LangGraph agent end-to-end loop
- [x] XHS Core real-time search integration
- [x] Flask web workbench with SSE streaming
- [x] Memory layer and brand fact persistence
- [x] Compliance scanner with reject/revision loop
- [ ] Account-permission resilience for XHS search
- [ ] Frontend progress events during QR-code wait
- [ ] Logo and visual identity
- [ ] Demo video and screenshot gallery
- [ ] Multi-platform export (copy, Markdown, PDF)

---

## Contributing

Issues, PRs, and research feedback are welcome. Please keep changes minimal and aligned with the existing LangGraph structure. If you update features documented in `AGENTS.md`, update the corresponding docs as well.

## License

[MIT](./LICENSE)

---

<div align="center">

Built with ❤️ for creators who are tired of sounding like ads.

</div>
