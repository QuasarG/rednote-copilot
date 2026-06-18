# RedNoteMatrix Agent 架构边界

## 用户输入

MVP 输入字段：

- `product_name`：商品或服务名称，必填
- `brand_name`：品牌名，可选
- `price`：售价或价格带，可选
- `selling_points`：卖点列表
- `target_audience`：目标客户群体
- `scenario`：使用场景
- `account_persona`：账号人设
- `tone`：常用语气
- `custom_prompt`：用户额外创作要求
- `memory_namespace`：品牌/商品独立记忆命名空间
- `forbidden_words`：品牌或行业禁用词

## 用户输出

默认只输出用户可直接复制的内容：

- 标题
- 正文
- 标签

内部评分、风险、执行轨迹只给调试、工作台或后端 API 使用，不作为普通用户默认输出。

## 当前 LangGraph 工作流

```text
memory_retriever
  -> market_research_agent
  -> trend_agent
  -> structure_agent
  -> humanizer_agent
  -> compliance_agent
  -> revision_router
      -> pass -> final_packager
      -> compliance/ai_trace reject -> humanizer_agent
      -> structure reject -> structure_agent -> humanizer_agent
```

## 记忆与 RAG 边界

不同品牌、不同商品必须使用独立命名空间：

```text
memory/{brand_name}/{product_name}
```

建议拆成三类记忆：

- `brand_voice`：品牌语气、常用表达、禁用语气
- `product_facts`：商品事实、价格、参数、卖点、不可编造边界
- `risk_rules`：品牌禁用词、行业敏感词、平台风险表达

RAG 检索只负责提供事实和约束，不直接生成文案。生成节点必须遵守：未检索到的事实不能编造。

当前 MVP 已落地：

- `MemoryStore`：SQLite + FTS5，默认数据库 `data/rednote_matrix.sqlite3`
- `ConversationStore`：会话和消息持久化
- `memory_retriever`：在 LangGraph 入口检索商品事实、品牌语气、风险规则、样例和文档片段
- 文档入库：支持 `.txt`、`.md`、`.pdf`
- API：FastAPI 暴露 `/chat`、`/memories`、`/documents/*`

当前先使用 SQLite/FTS5，便于 Docker 单容器部署。后续需要更强语义检索时，可在 `MemoryStore` 接口下替换为 Postgres + pgvector 或 Qdrant。

## 实时爬取节点边界

可选节点：

```text
market_research_agent -> trend_agent
```

职责：

- 调用 MediaCrawler 轻量搜索相关商品/品类关键词
- 只抓公开笔记标题、正文摘要、互动数据
- 控制频率，不抓评论正文作为默认行为
- 筛选高互动样本
- 输出爆款标题模式、正文结构、互动触发点

该节点是增强项，不是主流程必需项。没有实时爬取结果时，`trend_agent` 使用项目内置通用模式。

当前实现已能完成二维码登录和 cookie 写入，但小红书搜索接口与浏览器搜索页可能触发 `verification_required` / HTTP 461 / 请求过频安全验证。工作台和 Agent 会把该状态作为降级信号，不再把 0 条结果伪装成成功。

## 高互动模式文档

当前已有样本报告：

```text
data/xhs_viral_seed_20260618/analysis/viral_pattern_report.md
```

抓取操作、数据口径和落地影响记录：

```text
docs/xhs_viral_seed_20260618.md
```

核心结论：

- 标题先给情绪或悬念，再交代对象
- 强场景优先于强卖点
- 轻反差比硬夸更像真人
- 情绪可感知但不过载
- 正文结构常见为：场景 -> 困扰/误判 -> 发现过程 -> 感受 -> 限制/避坑 -> 互动
