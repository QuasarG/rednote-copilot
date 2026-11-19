<div align="center">

<img src="rednote_matrix/web/static/rednote-copilot-logo.png" alt="RedNote Copilot logo" width="720">

# RedNote Copilot

[English README](./README_EN.md)

[![Python](https://img.shields.io/badge/Python-3.13-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-1C3C3C?style=flat-square&logo=langchain&logoColor=white)](https://www.langchain.com/langgraph)
[![LangChain](https://img.shields.io/badge/LangChain-1C3C3C?style=flat-square&logo=langchain&logoColor=white)](https://www.langchain.com/)
[![Docker](https://img.shields.io/badge/Docker-ready-2496ED?style=flat-square&logo=docker&logoColor=white)](./Dockerfile)
[![Tests](https://img.shields.io/badge/Tests-unittest-E5A50A?style=flat-square)](./tests)
[![RAG](https://img.shields.io/badge/RAG-Memory_Agent-7C4DFF?style=flat-square)]()
[![License](https://img.shields.io/badge/License-MIT-00C853?style=flat-square)](./LICENSE)

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

## 使用案例

https://github.com/user-attachments/assets/0559377c-969f-44f8-8d24-ce56f78ecfb3

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

<table align="center">
  <tr>
    <td align="center">
      <img src="docs/assets/need-theme-counts.png" alt="小红书运营痛点主题分布" width="460"><br>
      <sub>图 1. 小红书运营痛点主题分布</sub>
    </td>
    <td align="center">
      <img src="docs/assets/wordcloud.png" alt="运营讨论关键词云" width="460"><br>
      <sub>图 2. 运营讨论关键词云</sub>
    </td>
  </tr>
</table>

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

**直接调用通用 LLM API 的输出：**

```text
标题：厨房油污清洁湿巾真的太好用了！

家人们，今天发现一个厨房清洁神器 CleanMint 油污清洁湿巾，一擦就干净，油烟机、灶台、墙面都能用。价格也很划算，租房党一定要冲。做饭之后抽一张擦一擦，厨房马上焕然一新。

#厨房清洁 #清洁神器 #租房好物 #油污清洁
```

**RedNote Copilot Agent 的输出：**

```text
标题：
1. 下班后懒得收拾厨房，结果被一包湿巾救了
2. 刚炒完菜灶台油乎乎，别急着拿钢丝球

正文：
下班到家做饭，炒完菜灶台上总会有一层油，手都不想伸过去。以前我会先找手套、喷清洁剂，再来回擦好几遍，整个人更累了。

最近换成 CleanMint 这种厨房油污清洁湿巾后，最舒服的是不用把清洁流程搞得很隆重。做完饭顺手抽一张，把灶台边缘和台面带一下，油膜基本能擦掉，也没有很刺鼻的味道。

它不是那种“神奇到不用收拾”的东西，重油污还是要多擦几下。但对租房小厨房来说，日常做完饭顺手清一下，确实省心很多。

你们做饭后一般怎么收拾灶台？有没有更省事的方法？

标签：#厨房清洁 #租房女生 #下班做饭 #懒人清洁 #去油膜 #CleanMint
```

为什么更好：RedNote Copilot 不是把提示词直接丢给模型，而是把商品信息、用户约束、爆款结构和合规风险拆成多个节点处理。它能避免直给价格、硬广口吻和模板化表达，最终交付更像真实使用经历、也更适合小红书语境的标题、正文和标签。

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

首次使用小红书实时检索功能时，系统会提示你登录小红书。请按弹出的浏览器窗口或二维码完成登录，并保持登录窗口存活，直到工作台提示登录成功；否则后续检索节点会失败或跳过。

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

## 测试环境说明

由于时间和设备有限，本项目主要在本机 Arch Linux 环境完成开发与测试，Docker 与本地开发路径均在此环境下验证通过。其他操作系统或硬件平台在理论上具备可迁移性，但尚未实际验证。本次交付以 MVP 为目标，跨端兼容与部署不是当前最核心的功能点。

## 英文文档

英文版说明见：[README_EN.md](./README_EN.md)
