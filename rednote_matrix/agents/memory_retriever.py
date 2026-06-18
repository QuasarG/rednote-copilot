from __future__ import annotations

from rednote_matrix.agents.utils import append_revision
from rednote_matrix.core.models import AgentInput, MemoryContext, MemorySnippet
from rednote_matrix.memory.store import MemoryRecord, MemoryStore


KIND_GROUPS = {
    "product_facts": ["product_fact"],
    "brand_voice": ["brand_voice"],
    "risk_rules": ["risk_rule"],
    "examples": ["example"],
    "documents": ["document_chunk", "brand_doc"],
}


def _namespace_for(user_input: AgentInput) -> str:
    if user_input.memory_namespace:
        return user_input.memory_namespace
    brand = user_input.brand_name or "default"
    return f"{brand}/{user_input.product_name}"


def _query_for(user_input: AgentInput) -> str:
    parts = [
        user_input.product_name,
        user_input.brand_name,
        user_input.target_audience,
        user_input.scenario,
        *user_input.selling_points,
    ]
    return " ".join(part for part in parts if part)


def _snippet(record: MemoryRecord) -> MemorySnippet:
    return MemorySnippet(
        namespace=record.namespace,
        kind=record.kind,
        title=record.title,
        content=record.content,
        score=round(record.score, 4),
    )


def retrieve_memory_context(user_input: AgentInput, store: MemoryStore | None = None) -> MemoryContext:
    store = store or MemoryStore()
    namespace = _namespace_for(user_input)
    query = _query_for(user_input)
    payload: dict[str, list[MemorySnippet] | str] = {"namespace": namespace}
    for group, kinds in KIND_GROUPS.items():
        records = store.search(namespace, query, kinds=kinds, limit=5, include_global=True)
        payload[group] = [_snippet(record) for record in records]
    return MemoryContext.model_validate(payload)


def run_memory_retriever(state: dict) -> dict:
    user_input = AgentInput.model_validate(state["user_input"])
    context = retrieve_memory_context(user_input)
    counts = {
        "商品事实": len(context.product_facts),
        "品牌语气": len(context.brand_voice),
        "风险规则": len(context.risk_rules),
        "样例": len(context.examples),
        "文档": len(context.documents),
    }
    return {
        **state,
        "memory_context": context.model_dump(),
        "revision_history": append_revision(
            state,
            "memory_retriever",
            "retrieved",
            [f"命名空间 {context.namespace}", f"检索结果 {counts}"],
        ),
    }
