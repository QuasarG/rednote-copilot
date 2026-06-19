from __future__ import annotations

from collections.abc import Generator, Iterator
from queue import Queue
from threading import Event, Thread
from typing import Any

from rednote_matrix.agents.compliance_agent import run_compliance_agent
from rednote_matrix.agents.final_packager import run_final_packager
from rednote_matrix.agents.humanizer_agent import run_humanizer_agent
from rednote_matrix.agents.input_parser import run_input_parser
from rednote_matrix.agents.market_research_agent import run_market_research_agent_stream
from rednote_matrix.agents.memory_retriever import run_memory_retriever
from rednote_matrix.agents.structure_agent import run_structure_agent
from rednote_matrix.agents.trend_agent import run_trend_agent
from rednote_matrix.core.graph import MAX_REVISION_LOOPS, route_after_compliance
from rednote_matrix.core.models import AgentInput, AgentResult
from rednote_matrix.core.render import render_user_copy


NODE_LABELS = {
    "input_parser": "输入解析",
    "memory_retriever": "记忆检索",
    "market_research_agent": "爆款检索",
    "trend_agent": "趋势归纳",
    "structure_agent": "结构生成",
    "humanizer_agent": "真人网感",
    "compliance_agent": "合规风控",
    "revision_router": "回炉路由",
    "final_packager": "最终打包",
}


def _market_note_preview(note: Any) -> dict[str, str]:
    if hasattr(note, "model_dump"):
        data = note.model_dump()
    elif isinstance(note, dict):
        data = note
    else:
        data = {}
    return {
        "title": str(data.get("title") or "")[:120],
        "desc": str(data.get("desc") or "")[:180],
        "note_url": str(data.get("note_url") or ""),
        "liked_count": str(data.get("liked_count") or ""),
        "comment_count": str(data.get("comment_count") or ""),
        "source_keyword": str(data.get("source_keyword") or ""),
    }


def _node_event(node: str, status: str, message: str = "", payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "type": "node",
        "node": node,
        "label": NODE_LABELS.get(node, node),
        "status": status,
        "message": message,
        "payload": payload or {},
    }


def _market_note_event(note: dict[str, Any], index: int) -> dict[str, Any]:
    return {
        "type": "market_note",
        "node": "market_research_agent",
        "label": NODE_LABELS["market_research_agent"],
        "index": index,
        "note": _market_note_preview(note),
    }


def _run_node(state: dict[str, Any], node: str, handler) -> tuple[dict[str, Any], dict[str, Any]]:
    next_state = handler(state)
    return next_state, _summarize_node(node, next_state)


def _stream_market_research_node(state: dict[str, Any]) -> Generator[dict[str, Any], None, dict[str, Any]]:
    event_queue: Queue[tuple[str, Any]] = Queue()
    stop_event = Event()

    def on_note(note: dict[str, Any]) -> None:
        event_queue.put(("note", note))

    def should_stop() -> bool:
        return stop_event.is_set()

    def worker() -> None:
        try:
            next_state = run_market_research_agent_stream(state, on_note=on_note, should_stop=should_stop)
            event_queue.put(("state", next_state))
        except Exception as exc:
            event_queue.put(("error", exc))

    thread = Thread(target=worker, daemon=True)
    thread.start()
    note_index = 0
    try:
        while True:
            kind, payload = event_queue.get()
            if kind == "note":
                note_index += 1
                yield _market_note_event(payload, note_index)
                continue
            if kind == "state":
                thread.join(timeout=0.2)
                return payload
            if kind == "error":
                thread.join(timeout=0.2)
                raise payload
    finally:
        stop_event.set()


def _summarize_node(node: str, state: dict[str, Any]) -> dict[str, Any]:
    if node == "input_parser":
        parsed = state.get("parsed_input") or {}
        product = parsed.get("product_name") or "未提取"
        kws = parsed.get("realtime_research_keywords") or []
        return {"message": f"提取商品: {product}，生成 {len(kws)} 个搜索关键词", "metric": len(kws)}
    if node == "memory_retriever":
        memory = state.get("memory_context") or {}
        count = sum(
            len(memory.get(key, []))
            for key in ("product_facts", "brand_voice", "writing_rules", "risk_rules", "examples", "documents")
        )
        return {"message": f"命中 {count} 条品牌/商品记忆", "metric": count}
    if node == "market_research_agent":
        context = state.get("market_research_context") or {}
        notes = context.get("notes") or []
        status = context.get("status", "")
        return {
            "message": context.get("message") or f"实时检索状态：{status}",
            "status": status,
            "metric": len(notes),
            "keywords": context.get("keywords") or [],
            "output_dir": context.get("output_dir") or "",
            "qrcode_url": context.get("qrcode_url") or "",
            "login_session_id": context.get("login_session_id") or "",
            "notes": [_market_note_preview(note) for note in notes[:30]],
        }
    if node == "trend_agent":
        insight = state.get("trend_insight") or {}
        return {"message": f"趋势评分 {state.get('trend_score', 0)}，来源 {insight.get('source', 'local')}", "metric": state.get("trend_score", 0)}
    if node == "structure_agent":
        draft = state.get("draft") or {}
        return {"message": f"生成 {len(draft.get('titles') or [])} 个标题候选", "metric": state.get("structure_score", 0)}
    if node == "humanizer_agent":
        return {"message": f"真人感评分 {state.get('human_score', 0)}", "metric": state.get("human_score", 0)}
    if node == "compliance_agent":
        risks = state.get("risk_items") or []
        return {"message": f"合规评分 {state.get('compliance_score', 0)}，风险 {len(risks)} 项", "metric": state.get("compliance_score", 0)}
    if node == "revision_router":
        route = route_after_compliance(state)
        return {"message": f"路由到 {NODE_LABELS.get(route, route)}，已回炉 {state.get('loop_count', 0)} 次", "route": route}
    if node == "final_packager":
        result = AgentResult.model_validate(state["final_output"])
        return {"message": f"输出状态：{result.status}", "metric": result.compliance_score}
    return {"message": "节点完成"}


def stream_agent_events(user_input: dict[str, Any] | AgentInput) -> Iterator[dict[str, Any]]:
    validated_input = user_input if isinstance(user_input, AgentInput) else AgentInput.model_validate(user_input)
    state: dict[str, Any] = {
        "user_input": validated_input.model_dump(),
        "loop_count": 0,
        "revision_history": [],
    }
    handlers = {
        "input_parser": run_input_parser,
        "memory_retriever": run_memory_retriever,
        "trend_agent": run_trend_agent,
        "structure_agent": run_structure_agent,
        "humanizer_agent": run_humanizer_agent,
        "compliance_agent": run_compliance_agent,
        "final_packager": run_final_packager,
    }

    for node in ("input_parser", "memory_retriever", "market_research_agent", "trend_agent", "structure_agent", "humanizer_agent", "compliance_agent"):
        yield _node_event(node, "running", f"{NODE_LABELS[node]}处理中")
        if node == "market_research_agent":
            state = yield from _stream_market_research_node(state)
            summary = _summarize_node(node, state)
        else:
            state, summary = _run_node(state, node, handlers[node])
        yield _node_event(node, "done", summary["message"], summary)

    while True:
        node = "revision_router"
        yield _node_event(node, "running", "检查是否需要回炉")
        route_reason = state.get("route_reason", "pass")
        if route_reason != "pass":
            state = {**state, "loop_count": int(state.get("loop_count", 0)) + 1}
        summary = _summarize_node(node, state)
        yield _node_event(node, "done", summary["message"], summary)

        route = summary.get("route")
        if route == "final_packager" or int(state.get("loop_count", 0)) > MAX_REVISION_LOOPS:
            break
        revision_nodes = ["structure_agent", "humanizer_agent"] if route == "structure_agent" else ["humanizer_agent"]
        for node in revision_nodes:
            yield _node_event(node, "running", f"{NODE_LABELS.get(node, node)}回炉修改")
            state, summary = _run_node(state, node, handlers[node])
            yield _node_event(node, "done", summary["message"], summary)
        node = "compliance_agent"
        yield _node_event(node, "running", "复检修改后的内容")
        state, summary = _run_node(state, node, handlers[node])
        yield _node_event(node, "done", summary["message"], summary)

    node = "final_packager"
    yield _node_event(node, "running", "整理标题、正文和标签")
    state, summary = _run_node(state, node, handlers[node])
    result = AgentResult.model_validate(state["final_output"])
    output = render_user_copy(result)
    yield _node_event(node, "done", summary["message"], summary)
    yield {"type": "result", "output": output, "result": result.model_dump()}
