from __future__ import annotations

from typing import Literal, TypedDict

from pydantic import BaseModel, Field


class AgentInput(BaseModel):
    product_name: str = Field(..., description="商品或服务名称")
    brand_name: str = Field(default="", description="品牌名称")
    price: str = Field(default="", description="售价或价格带")
    selling_points: list[str] = Field(default_factory=list, description="核心卖点")
    target_audience: str = Field(default="", description="目标人群")
    scenario: str = Field(default="", description="使用场景")
    account_persona: str = Field(default="真实分享型种草博主", description="账号人设")
    tone: str = Field(default="自然、可信、轻种草", description="语气偏好")
    custom_prompt: str = Field(default="", description="用户自定义创作要求")
    current_message: str = Field(default="", description="本轮对话新增要求")
    current_changes: list[dict] = Field(default_factory=list, description="本轮左侧商品背景变更")
    conversation_history: list[dict] = Field(default_factory=list, description="本地多轮对话历史")
    memory_namespace: str = Field(default="", description="品牌/商品独立记忆命名空间")
    forbidden_words: list[str] = Field(default_factory=list, description="品牌或行业禁用词")
    enable_realtime_research: bool = Field(default=False, description="是否启用小红书实时趋势检索")
    realtime_research_keywords: list[str] = Field(default_factory=list, description="实时检索关键词")
    realtime_research_max_notes: int = Field(default=6, description="实时检索最多笔记数")


class Draft(BaseModel):
    titles: list[str] = Field(default_factory=list)
    cover_text: str = ""
    hook: str = ""
    body: str = ""
    tags: list[str] = Field(default_factory=list)
    structure_type: str = ""
    structure_notes: list[str] = Field(default_factory=list)


class RiskItem(BaseModel):
    type: str
    text: str
    reason: str
    suggestion: str
    severity: Literal["low", "medium", "high"] = "medium"


class TrendInsight(BaseModel):
    title_patterns: list[str] = Field(default_factory=list)
    opening_hooks: list[str] = Field(default_factory=list)
    content_structures: list[str] = Field(default_factory=list)
    interaction_tactics: list[str] = Field(default_factory=list)
    tag_strategy: list[str] = Field(default_factory=list)
    scoring_dimensions: dict[str, int] = Field(default_factory=dict)
    source: str = "local_skill_adaptation"


class MarketNote(BaseModel):
    title: str = ""
    desc: str = ""
    note_url: str = ""
    liked_count: str = ""
    comment_count: str = ""
    source_keyword: str = ""


class MarketResearchContext(BaseModel):
    enabled: bool = False
    status: Literal["disabled", "ready", "completed", "needs_login", "unconfigured", "verification_required", "error"] = "disabled"
    keywords: list[str] = Field(default_factory=list)
    source: str = "xhs_core"
    message: str = ""
    login_session_id: str = ""
    qrcode_path: str = ""
    qrcode_url: str = ""
    output_dir: str = ""
    notes: list[MarketNote] = Field(default_factory=list)


class MemorySnippet(BaseModel):
    namespace: str
    kind: str
    title: str
    content: str
    score: float = 0.0


class MemoryContext(BaseModel):
    namespace: str = "global"
    product_facts: list[MemorySnippet] = Field(default_factory=list)
    brand_voice: list[MemorySnippet] = Field(default_factory=list)
    risk_rules: list[MemorySnippet] = Field(default_factory=list)
    examples: list[MemorySnippet] = Field(default_factory=list)
    documents: list[MemorySnippet] = Field(default_factory=list)


class RevisionRecord(BaseModel):
    node: str
    action: str
    notes: list[str] = Field(default_factory=list)


class AgentResult(BaseModel):
    status: Literal["pass", "needs_review"]
    draft: Draft
    structure_score: int
    human_score: int
    compliance_score: int
    ai_trace_score: int
    trend_score: int = 0
    trend_insight: TrendInsight = Field(default_factory=TrendInsight)
    market_research_context: MarketResearchContext = Field(default_factory=MarketResearchContext)
    memory_context: MemoryContext = Field(default_factory=MemoryContext)
    route_reason: str = ""
    loop_count: int = 0
    risk_items: list[RiskItem]
    revision_history: list[RevisionRecord]
    publish_checklist: list[str]


class AgentState(TypedDict, total=False):
    user_input: dict
    draft: dict
    structure_score: int
    human_score: int
    compliance_score: int
    ai_trace_score: int
    trend_score: int
    trend_insight: dict
    market_research_context: dict
    memory_context: dict
    risk_items: list[dict]
    revision_history: list[dict]
    loop_count: int
    route_reason: str
    final_output: dict
