# RedNoteMatrix Copilot

小红书种草内容 Agent 原型。当前重点是后端闭环：结构化爆款生成、真人网感改写、合规防限流扫描，以及基于 LangGraph 的 reject 回炉。

## 环境

项目使用本地 `.venv`，不要污染全局 Python。

```bash
uv pip install -r requirements.txt
```

## 运行 Demo

```bash
uv run python -m rednote_matrix.cli examples/sample_input.json
uv run python -m rednote_matrix.cli examples/risky_input.json
```

Agent 生成节点默认调用 OpenAI-compatible LLM。项目不再保留离线规则生成模式；合规扫描仍使用本地风控词表和记忆库风险规则。
默认输出是给用户直接复制的小红书内容：标题、正文、标签。调试完整状态时再加 `--json`：

```bash
uv run python -m rednote_matrix.cli examples/sample_input.json --json
```

当前项目内置了 `rednote_matrix.skills.xiaohongshu`，沉淀了小红书写作/笔记分析方法论，以及 2026-06-18 轻量抓取的高互动种草样本模式：

- 标题模式：情绪/悬念先行、强场景、轻反差、人群标签、避坑型
- 内容结构：具体场景、原先困扰/误判、发现过程、真实感受、限制/避坑、互动收尾
- 评分维度：关键词覆盖、结构完整度、时效性、内容质量

它已经作为 `trend_agent` 接入 LangGraph，不是给 Codex 用的外部技能。
该轮 MediaCrawler 操作、数据口径和模式总结见 `docs/xhs_viral_seed_20260618.md`。

用户可以输入价格信息，但价格只作为内部定位和预算判断参考。最终标题、正文、标签默认不外显具体价格、售价、到手价、活动价等交易表达，以降低硬广和审核风险。

## XHS Core 实时爆款检索

小红书实时检索核心能力已经抽进本项目运行时，不需要再配置外部 MediaCrawler 仓库。实现参考并借鉴了 MediaCrawler 的小红书登录、二维码捕获、cookie 管理和搜索接口调用思路，后续保留致谢说明即可。

实时检索功能由用户开关控制，但后端依赖仍是必配：`playwright` 负责二维码登录，`xhshow` 负责小红书请求签名。后端会在 `/health` 和 `/integrations/xhs/status` 暴露环境状态。深度检查：

```bash
curl 'http://localhost:8000/integrations/xhs/status?deep=true'
```

如果小红书 cookie 已保存，后端会直接调用内置 XHS Core 轻量搜索；如果没有登录态，可以启动二维码登录会话：

```bash
curl -X POST http://localhost:8000/integrations/xhs/login/qrcode \
  -H 'Content-Type: application/json' \
  -d '{"use_virtual_display": true, "timeout_seconds": 180}'
```

接口返回 `session_id`、`qrcode_path` 和 `qrcode_url`。Web 工作台应展示 `qrcode_url`，不要直接读取容器内部文件路径：

```bash
curl http://localhost:8000/integrations/xhs/login/{session_id}/qrcode --output qrcode.png
```

前端扫码后轮询：

```bash
curl http://localhost:8000/integrations/xhs/login/{session_id}
```

`use_virtual_display=true` 是 Docker 部署推荐模式：容器内用 Xvfb 提供虚拟显示器，让 Chromium 以有头模式通过风控，但不会在宿主机弹出真实 Chrome 窗口。Windows、macOS、Linux 宿主机只需要运行 Linux Docker 容器，不需要单独安装 Xvfb。裸机直接运行时，如果系统没有 Xvfb，首次二维码登录会返回明确错误；已有 cookie 的实时检索不需要浏览器窗口。

手动写入 cookie：

```bash
curl -X POST http://localhost:8000/integrations/xhs/auth/cookie \
  -H 'Content-Type: application/json' \
  -d '{"cookie":"web_session=...; ..."}'
```

轻量搜索接口默认按点赞和评论粗排，返回高互动笔记：

```bash
curl -X POST http://localhost:8000/integrations/xhs/search \
  -H 'Content-Type: application/json' \
  -d '{"keywords":["桌面收纳托盘 爆款笔记","租房小桌面 桌面收纳托盘"],"max_notes_count":6}'
```

Agent 输入里设置 `enable_realtime_research: true` 后会默认搜索相关关键词的爆款笔记。关键词生成优先围绕商品/品类、目标人群、场景、卖点和“真实体验/避坑”等小红书高互动意图；如果用户提供 `realtime_research_keywords`，则优先使用用户关键词。

配置 LLM：

```bash
cp .env.example .env
```

然后填写：

```bash
OPENAI_API_KEY=你的 key
# 或使用 DEEPSEEK_API_KEY=你的 DeepSeek key
OPENAI_MODEL=你的模型名
OPENAI_BASE_URL=https://api.openai.com/v1
```

DeepSeek 示例：

```bash
DEEPSEEK_API_KEY=你的 DeepSeek key
OPENAI_MODEL=deepseek-v4-pro
OPENAI_BASE_URL=https://api.deepseek.com
```

再运行同一个命令即可。`OPENAI_BASE_URL` 支持 OpenAI-compatible Chat Completions 接口。

`--json` 调试输出包含：

- `draft`：双标题、封面文案、钩子、正文、标签
- `risk_items`：合规、硬广、AI 模板腔风险
- `revision_history`：LangGraph 节点执行与回炉记录
- `publish_checklist`：发布前人工终审清单

## 测试

```bash
uv run python -m unittest discover -s tests -v
```

## Flask Web 工作台

当前前端是一个 Flask 工作台，采用 Neo Brutalism 风格的三栏工作台：左侧是商品背景和 JSON 导入，中间是 Agent 对话流和补充 Prompt，右侧是只读文案输出卡。它直接复用后端 LangGraph 节点，并通过 SSE 把节点进度插入中间对话流；最终完整文案不会塞回聊天气泡，而是被前端解析到右侧的标题、正文、标签三个只读区域。

```bash
uv run flask --app rednote_matrix.web.workbench run --host 0.0.0.0 --port 8501
```

浏览器打开：

```text
http://localhost:8501
```

工作台能力：

- 在中间对话流展示 `memory_retriever -> market_research_agent -> trend_agent -> structure_agent -> humanizer_agent -> compliance_agent -> revision_router -> final_packager` 的节点进度
- 节点开始、完成、回炉状态会以 token 式流式文字更新
- 左侧支持导入 JSON 示例并自动解析商品、人群、卖点、禁用词和补充 Prompt
- 最终文案解析到右侧只读输出卡，按标题、正文、标签分区展示
- 标题、正文、标签分别提供复制按钮
- `MediaCrawler Node` 开关可控制是否启用实时小红书爆款检索

注意：小红书实时检索目前可能返回 `verification_required`，这是平台安全验证/请求过频导致的降级状态，不影响 Agent 主链路生成文案。

## Docker

```bash
docker build -t rednote-matrix-agent .
docker run --rm rednote-matrix-agent
```

Docker 镜像默认启动 FastAPI 服务，监听 `8000`。
如果要启动 Flask 工作台：

```bash
docker run --rm -p 8501:8501 --env-file .env -v "$PWD/data:/app/data" rednote-matrix-agent \
  flask --app rednote_matrix.web.workbench run --host 0.0.0.0 --port 8501
```

```bash
docker compose up --build
```

常用接口：

- `GET /health`
- `POST /chat`
- `POST /memories`
- `GET /memories`
- `POST /documents/path`
- `POST /documents/upload`
- `GET /integrations/xhs/status`
- `POST /integrations/xhs/login/qrcode`
- `GET /integrations/xhs/login/{session_id}`
- `POST /integrations/xhs/auth/cookie`
- `POST /integrations/xhs/search`

Docker 镜像安装 `requirements-agent.txt`，包含 API、RAG、记忆层以及 XHS Core 实时检索依赖；构建时会安装 Playwright Chromium。
镜像还内置 Xvfb，用于无宿主机窗口的二维码登录。也就是说，Windows 上用 Docker Desktop 跑容器时，用户只会在前端看到二维码，不会被弹出的 Chrome 打扰。

示例：

```bash
curl -X POST http://localhost:8000/memories \
  -H 'Content-Type: application/json' \
  -d '{"namespace":"brand/acme/tray","kind":"product_fact","title":"商品事实","content":"桌面收纳托盘是雾白色，售价 39 元。"}'

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

## 当前 Agent 图

```text
memory_retriever
  -> market_research_agent
  -> trend_agent
  -> structure_agent
  -> humanizer_agent
  -> compliance_agent
  -> revision_router
      -> pass -> final_packager
      -> compliance/ai_trace reject -> humanizer_agent -> compliance_agent
      -> structure reject -> structure_agent -> humanizer_agent -> compliance_agent
```

`market_research_agent` 由用户开关控制。关闭时只记录 skipped；打开时会先检查 XHS Core 环境和小红书登录态，已登录则抓取相关爆款笔记，没有登录态则返回二维码会话信息。

`compliance_agent` 是核心路由节点。命中极限词、硬广导流词或 AI 模板腔时，会把草稿打回 `humanizer_agent` 修订；结构分不足时会回到 `structure_agent` 补框架；达到最大回炉次数仍未解决的内容会输出 `needs_review`。
