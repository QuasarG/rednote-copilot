<div align="center">

<img src="rednote_matrix/web/static/rednote-copilot-logo.png" alt="RedNote Copilot logo" width="720">

# RedNote Copilot

[English README](./README_EN.md)

面向小红书种草场景的 AI Agent 工作台：爆款样本检索、结构化文案生成、真人网感改写、合规风险检查和多轮对话交付。

</div>

---

## 项目定位

RedNote Copilot 不是“一键生成小红书文案”的普通聊天工具，而是围绕小红书内容运营的核心目标设计的 Agent 工作流：

- 找到更接近真实平台语境的高互动样本。
- 把商品信息转成适合小红书的标题、正文和标签。
- 尽量避免硬广、极限词、价格直给等潜在风险。
- 用多轮对话持续修改，并保留本地历史。
- 通过前端工作台展示节点进度、样本列表和最终只读文案。

## 工作台预览

<p align="center">
  <img src="docs/assets/workbench-overview.png" alt="RedNote Copilot 工作台总览" width="900">
</p>

## 工作流概览

<p align="center">
  <img src="docs/assets/agent-flow.png" alt="RedNote Copilot Agent 工作流" width="760">
</p>

## 数据依据

项目早期围绕“小红书运营太难了”“被限流”“笔记违规”“做小红书多账号”“爆款文案怎么写”等关键词抓取并分析了一批真实运营讨论数据。清洗后的文本分析结论显示，用户最集中的焦虑不是“缺一段文案”，而是：

| 痛点 | 数据表现 | 对应产品能力 |
| --- | --- | --- |
| 流量与曝光焦虑 | 低互动、低浏览、起号困难相关内容占比最高 | 爆款样本检索、趋势归纳、结构化标题和开头 |
| 违规与限流恐惧 | 违规、审核、限流相关评论情绪强烈 | 合规扫描、风险词改写、循环回炉 |
| 文案结构缺失 | 用户反复讨论标题、开头、框架和节奏 | 双标题、场景钩子、正文结构生成 |
| AI 味与信任问题 | 频率不如流量焦虑高，但影响内容可信度 | 真人网感改写、弱化模板化表达 |

<p align="center">
  <img src="docs/assets/need-theme-counts.png" alt="小红书运营痛点主题分布" width="760">
</p>

核心数据摘要：

| 指标 | 数值 |
| --- | --- |
| 目标帖子 | 50 条 |
| 原始评论 | 4,962 条 |
| 去重后评论 | 4,798 条 |
| 有效评论 | 4,623 条 |
| 主题分析样本 | 4,035 条 |

## 核心能力

- **LangGraph Agent 工作流**：输入解析、记忆检索、爆款检索、趋势归纳、结构生成、真人改写、合规检查、最终打包。
- **小红书实时检索节点**：支持 Chrome 登录态、搜索高互动笔记，并逐条把样本推送到前端。
- **多轮对话**：用户可以继续补充需求，例如“更口语一点”“这版加上价格”，后端会继承上一轮上下文。
- **记忆隔离**：按品牌、商品和命名空间检索本地记忆，避免不同商品互相污染。
- **本地历史会话**：工作台历史保存在 `.rednote_workbench_history/`，不会进入仓库。
- **只读输出卡片**：前端右侧固定展示标题、正文、标签，并提供复制按钮。

## 同样输入下的差异

示例输入：`帮我写一篇小红书种草文案。产品是厨房油污清洁湿巾，品牌 CleanMint，目标人群是经常做饭但不想花太多时间刷灶台的租房女生。价格 29.9 元一包，但正文里不要直接写价格。语气要像真实朋友分享，别太广告。`

| 对比维度 | 直接调用通用 LLM API | RedNote Copilot Agent |
| --- | --- | --- |
| 输入理解 | 往往把所有信息一次性塞进文案，价格、卖点和限制容易混在一起 | 先解析商品、品牌、人群、价格限制和语气要求，再进入后续节点 |
| 爆款结构 | 常见输出是“标题 + 正文 + 标签”的普通模板 | 按小红书场景组织：痛点场景、使用前后变化、克制种草、互动结尾 |
| 平台语境 | 不知道当前小红书同类内容常见表达，容易泛化 | 可选实时检索高互动笔记，把标题、评论和趋势样本作为参考 |
| 合规风险 | 可能直接写价格、夸张承诺或硬广词，需要人工复查 | 合规节点检查极限词、硬广感、价格直给和导流风险，并触发回炉 |
| 真人感 | 容易出现“家人们冲”“闭眼入”等模板化表达 | 真人网感节点弱化广告腔，改成更像真实使用经历的表达 |
| 多轮修改 | 下一轮容易丢失上一轮上下文，需要用户反复解释 | 保留会话状态和商品记忆，可继续说“更口语一点”“这版加上价格” |
| 最终交付 | 一整段文本，用户还要自己拆标题、正文、标签 | 前端自动拆成标题、正文、标签三张只读卡片，分别复制 |

## 目录结构

```text
rednote_matrix/
  agents/          Agent 节点
  core/            LangGraph、模型和流式运行器
  integrations/    小红书检索与登录相关集成
  memory/          SQLite/FTS 本地记忆
  rules/           合规规则
  server/          FastAPI 接口
  web/             Flask 工作台
docs/              PRD、架构图和流程图
examples/          示例输入
tests/             单元测试
scripts/           数据分析脚本
```

## 快速启动（Docker 推荐）

Docker 会在镜像内安装后端依赖和 Playwright Chromium，适合快速演示和部署。首次启动前先准备 `.env`：

```bash
cp .env.example .env
```

至少配置一个 OpenAI-compatible 模型服务。DeepSeek 示例：

```bash
DEEPSEEK_API_KEY=your_key_here
OPENAI_BASE_URL=https://api.deepseek.com
OPENAI_MODEL=deepseek-chat
```

构建镜像：

```bash
docker build -t rednote-copilot-agent .
```

启动 Web 工作台（推荐）：

```bash
docker run --rm -p 8501:8501 --env-file .env -v "$PWD/data:/app/data" rednote-copilot-agent \
  flask --app rednote_matrix.web.workbench run --host 0.0.0.0 --port 8501
```

打开：

```text
http://localhost:8501
```

如果只需要 FastAPI：

```bash
docker run --rm -p 8000:8000 --env-file .env -v "$PWD/data:/app/data" rednote-copilot-agent
```

健康检查：

```bash
curl http://localhost:8000/health
```

也可以使用 Docker Compose 启动默认 API 服务：

```bash
docker compose up --build
```

注意：当前 compose 默认运行 FastAPI；如果要打开工作台，请使用上面的 Web 工作台启动命令。

## 本地开发启动（可选）

请在任意隔离 Python 环境中运行，例如 conda、venv 或 uv。项目不会提交本地环境目录。

```bash
pip install -r requirements-agent.txt
playwright install chromium
cp .env.example .env
```

CLI 示例：

```bash
python -m rednote_matrix.cli examples/sample_input.json
```

启动 FastAPI：

```bash
python -m rednote_matrix.server.api
```

启动 Flask 工作台：

```bash
flask --app rednote_matrix.web.workbench run --host 0.0.0.0 --port 8501
```

打开：

```text
http://localhost:8501
```

## 测试

```bash
python -m unittest tests.test_api tests.test_workbench tests.test_agent_graph -v
```

当前核心测试覆盖：

- 自然语言输入解析。
- 多轮对话继承上下文。
- 用户显式要求价格时的处理。
- 工作台 SSE 流式输出。
- 小红书登录、搜索和异常状态接口。

## 注意事项

- 用户可以输入价格，但默认不建议直接在最终文案中输出价格，避免触发平台风险或硬广感。
- 小红书实时检索依赖登录态，可能受平台风控影响。
- 本项目借鉴了 MediaCrawler 的小红书抓取思路，但保留为项目内轻量集成。
- `.env`、本地 Python 环境目录、`data/`、`.rednote_workbench_history/` 都不应提交。

## 英文文档

英文版说明见：[README_EN.md](./README_EN.md)
