from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from flask import Flask, Response, jsonify, render_template, request, send_file, stream_with_context

from rednote_matrix.core.models import AgentInput
from rednote_matrix.core.stream_runner import NODE_LABELS, stream_agent_events
from rednote_matrix.integrations.xhs_core import (
    check_xhs_auth,
    check_xhs_environment,
    login_session_status,
    persistent_browser_status,
    result_to_dict,
    start_qrcode_login_process,
)
from rednote_matrix.memory.store import default_db_path
from rednote_matrix.web.local_history import LocalConversationStore


def create_app() -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config["JSON_AS_ASCII"] = False

    @app.get("/")
    def index() -> str:
        return render_template("workbench.html", node_labels=NODE_LABELS)

    @app.get("/ui/status")
    def ui_status() -> Response:
        return jsonify(
            {
                "status": "ok",
                "db_path": str(default_db_path()),
                "history_dir": str(LocalConversationStore().history_dir),
                "xhs_environment": result_to_dict(check_xhs_environment(deep=False)),
                "xhs_auth": result_to_dict(check_xhs_auth()),
                "persistent_browser": result_to_dict(persistent_browser_status()),
            }
        )

    @app.get("/ui/conversations")
    def ui_conversations() -> Response:
        return jsonify({"items": LocalConversationStore().list_conversations()})

    @app.get("/ui/conversations/<conversation_id>")
    def ui_conversation_detail(conversation_id: str) -> Response:
        record = LocalConversationStore().get(conversation_id)
        if not record:
            return jsonify({"detail": "对话不存在"}), 404
        return jsonify(record)

    @app.post("/ui/xhs/login/qrcode")
    def ui_xhs_login_qrcode() -> Response:
        payload = request.get_json(silent=True) or {}
        session = start_qrcode_login_process(
            headless=False,
            timeout_seconds=int(payload.get("timeout_seconds") or 240),
            use_virtual_display=True,
        )
        data = result_to_dict(session)
        data["qrcode_url"] = f"/ui/xhs/login/{session.session_id}/qrcode" if session.session_id else ""
        return jsonify(data)

    @app.get("/ui/xhs/login/<session_id>")
    def ui_xhs_login_status(session_id: str) -> Response:
        session = login_session_status(session_id)
        data = result_to_dict(session)
        data["qrcode_url"] = f"/ui/xhs/login/{session.session_id}/qrcode" if session.session_id else ""
        return jsonify(data)

    @app.get("/ui/xhs/login/<session_id>/qrcode")
    def ui_xhs_login_image(session_id: str):
        session = login_session_status(session_id)
        path = Path(session.qrcode_path)
        if not session.qrcode_path or not path.exists():
            return jsonify({"detail": "二维码尚未生成"}), 404
        return send_file(path, mimetype="image/png")

    @app.post("/ui/agent/stream")
    def ui_agent_stream() -> Response:
        payload = request.get_json(force=True)

        def generate():
            conversation_id = ""
            turn_id = ""
            store = LocalConversationStore()
            try:
                conversation_payload = _prepare_conversation_payload(payload, store)
                conversation_id = conversation_payload["conversation_id"]
                turn_id = conversation_payload["turn_id"]
                agent_input = _agent_input_from_payload(conversation_payload["agent_input"])
                accepted_event = {
                    "type": "accepted",
                    "message": "任务已进入 Agent 图",
                    "conversation_id": conversation_id,
                    "turn_id": turn_id,
                }
                store.append_event(conversation_id, turn_id, accepted_event)
                yield _sse(accepted_event)
                for event in stream_agent_events(agent_input):
                    if event.get("type") == "result":
                        store.finish_turn(conversation_id, turn_id, event)
                    else:
                        store.append_event(conversation_id, turn_id, event)
                    yield _sse(event)
            except Exception as exc:
                if conversation_id and turn_id:
                    store.fail_turn(conversation_id, turn_id, str(exc))
                yield _sse({"type": "error", "message": str(exc)})

        return Response(stream_with_context(generate()), mimetype="text/event-stream")

    return app


def _prepare_conversation_payload(payload: dict[str, Any], store: LocalConversationStore) -> dict[str, Any]:
    message = str(payload.get("message") or "").strip()
    conversation_id = str(payload.get("conversation_id") or "").strip() or None
    changes = payload.get("changes") if isinstance(payload.get("changes"), list) else []
    agent_patch = {key: value for key, value in payload.items() if key not in {"message", "conversation_id", "changes"}}
    existing_record = store.get(conversation_id or "") if conversation_id else None
    agent_patch["current_message"] = message
    agent_patch["current_changes"] = changes
    agent_patch["conversation_history"] = store.history_for_agent(existing_record)
    record, turn_id = store.start_turn(
        conversation_id=conversation_id,
        agent_input=agent_patch,
        message=message,
        changes=changes,
    )
    return {"conversation_id": record["id"], "turn_id": turn_id, "agent_input": agent_patch}


def _agent_input_from_payload(payload: dict[str, Any]) -> AgentInput:
    selling_points = payload.get("selling_points", [])
    forbidden_words = payload.get("forbidden_words", [])
    keywords = payload.get("realtime_research_keywords", [])
    data = {
        **payload,
        "selling_points": _lines_to_list(selling_points),
        "forbidden_words": _lines_to_list(forbidden_words),
        "realtime_research_keywords": _lines_to_list(keywords),
        "enable_realtime_research": bool(payload.get("enable_realtime_research")),
    }
    return AgentInput.model_validate(data)


def _lines_to_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [line.strip() for line in str(value or "").replace("，", "\n").replace(",", "\n").splitlines() if line.strip()]


def _sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


app = create_app()
