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

## 数据依据

项目早期围绕“小红书运营太难了”“被限流”“笔记违规”“做小红书多账号”“爆款文案怎么写”等关键词抓取并分析了一批真实运营讨论数据。清洗后的文本分析结论显示，用户最集中的焦虑不是“缺一段文案”，而是：

| 痛点 | 数据表现 | 对应产品能力 |
| --- | --- | --- |
| 流量与曝光焦虑 | 低互动、低浏览、起号困难相关内容占比最高 | 爆款样本检索、趋势归纳、结构化标题和开头 |
| 违规与限流恐惧 | 违规、审核、限流相关评论情绪强烈 | 合规扫描、风险词改写、循环回炉 |
| 文案结构缺失 | 用户反复讨论标题、开头、框架和节奏 | 双标题、场景钩子、正文结构生成 |
| AI 味与信任问题 | 频率不如流量焦虑高，但影响内容可信度 | 真人网感改写、弱化模板化表达 |

推荐佐证图表位于本地数据目录：

`data/xhs_ops_research_20260618/analysis/need_theme_analysis/theme_counts.png`

相关分析报告：

- `data/xhs_ops_research_20260618/analysis/need_theme_analysis/need_theme_report.md`
- `data/xhs_ops_research_20260618/analysis/ai_tool_need_validation/ai_tool_need_validation_report.md`

`data/` 目录默认不进入 Git 仓库。

## 核心能力

- **LangGraph Agent 工作流**：输入解析、记忆检索、爆款检索、趋势归纳、结构生成、真人改写、合规检查、最终打包。
- **小红书实时检索节点**：支持 Chrome 登录态、搜索高互动笔记，并逐条把样本推送到前端。
- **多轮对话**：用户可以继续补充需求，例如“更口语一点”“这版加上价格”，后端会继承上一轮上下文。
- **记忆隔离**：按品牌、商品和命名空间检索本地记忆，避免不同商品互相污染。
- **本地历史会话**：工作台历史保存在 `.rednote_workbench_history/`，不会进入仓库。
- **只读输出卡片**：前端右侧固定展示标题、正文、标签，并提供复制按钮。

## Agent 流程

```text
input_parser
  -> memory_retriever
  -> market_research_agent
  -> trend_agent
  -> structure_agent
  -> humanizer_agent
  -> compliance_agent
  -> revision_router
      -> pass -> final_packager
      -> reject -> humanizer_agent
```

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

## 环境配置

建议使用项目内 `.venv`，不要污染全局 Python 环境。

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-agent.txt
playwright install chromium
```

根目录维护 `.env`，该文件已被 `.gitignore` 忽略：

```bash
DEEPSEEK_API_KEY=your_key_here
OPENAI_BASE_URL=https://api.deepseek.com
OPENAI_MODEL=deepseek-chat
```

## 运行方式

CLI 示例：

```bash
.venv/bin/python -m rednote_matrix.cli examples/sample_input.json
```

FastAPI：

```bash
.venv/bin/python -m rednote_matrix.server.api
```

Flask 工作台：

```bash
.venv/bin/flask --app rednote_matrix.web.workbench run --host 0.0.0.0 --port 8501
```

打开：

```text
http://localhost:8501
```

Docker：

```bash
docker build -t rednote-copilot-agent .
docker run --rm -p 8000:8000 --env-file .env -v "$PWD/data:/app/data" rednote-copilot-agent
```

运行工作台：

```bash
docker run --rm -p 8501:8501 --env-file .env -v "$PWD/data:/app/data" rednote-copilot-agent \
  flask --app rednote_matrix.web.workbench run --host 0.0.0.0 --port 8501
```

## 测试

```bash
.venv/bin/python -m unittest tests.test_api tests.test_workbench tests.test_agent_graph -v
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
- `.env`、`.venv`、`data/`、`.rednote_workbench_history/` 都不应提交。

## 英文文档

英文版说明见：[README_EN.md](./README_EN.md)
