from __future__ import annotations

import json
import os
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def default_history_dir() -> Path:
    configured = os.environ.get("REDNOTE_WORKBENCH_HISTORY_DIR")
    return Path(configured) if configured else PROJECT_ROOT / ".rednote_workbench_history"


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _clean_id(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,80}", value):
        return ""
    return value


def _title_from_input(agent_input: dict[str, Any], fallback: str = "") -> str:
    title = str(agent_input.get("product_name") or agent_input.get("brand_name") or fallback or "未命名对话").strip()
    return title[:48]


class LocalConversationStore:
    def __init__(self, history_dir: str | Path | None = None) -> None:
        self.history_dir = Path(history_dir) if history_dir else default_history_dir()
        self.history_dir.mkdir(parents=True, exist_ok=True)

    def list_conversations(self) -> list[dict[str, Any]]:
        items = [self._summary(record) for record in self._read_all()]
        return sorted(items, key=lambda item: item.get("updated_at", ""), reverse=True)

    def get(self, conversation_id: str) -> dict[str, Any] | None:
        safe_id = _clean_id(conversation_id)
        if not safe_id:
            return None
        path = self._path(safe_id)
        if not path.exists():
            return None
        return self._read(path)

    def start_turn(
        self,
        conversation_id: str | None,
        agent_input: dict[str, Any],
        message: str = "",
        changes: list[dict[str, Any]] | None = None,
    ) -> tuple[dict[str, Any], str]:
        record = self.get(conversation_id or "") if conversation_id else None
        timestamp = _now()
        if not record:
            conversation_id = str(uuid.uuid4())
            record = {
                "schema_version": 1,
                "id": conversation_id,
                "title": _title_from_input(agent_input),
                "created_at": timestamp,
                "updated_at": timestamp,
                "agent_input": {},
                "turns": [],
            }
        turn_id = str(uuid.uuid4())
        record["title"] = _title_from_input(agent_input, record.get("title", ""))
        record["updated_at"] = timestamp
        record["agent_input"] = _public_agent_input(agent_input)
        record.setdefault("turns", []).append(
            {
                "id": turn_id,
                "created_at": timestamp,
                "updated_at": timestamp,
                "status": "running",
                "message": str(message or ""),
                "changes": changes or [],
                "agent_input": _public_agent_input(agent_input),
                "events": [],
                "result": None,
                "output_parts": None,
                "error": "",
            }
        )
        self._write(record)
        return record, turn_id

    def append_event(self, conversation_id: str, turn_id: str, event: dict[str, Any]) -> None:
        record = self.get(conversation_id)
        if not record:
            return
        turn = _find_turn(record, turn_id)
        if not turn:
            return
        timestamp = _now()
        turn["updated_at"] = timestamp
        turn.setdefault("events", []).append(event)
        record["updated_at"] = timestamp
        self._write(record)

    def finish_turn(self, conversation_id: str, turn_id: str, event: dict[str, Any]) -> None:
        record = self.get(conversation_id)
        if not record:
            return
        turn = _find_turn(record, turn_id)
        if not turn:
            return
        timestamp = _now()
        result = event.get("result") or {}
        turn["status"] = "completed"
        turn["updated_at"] = timestamp
        turn["result"] = result
        turn["output_parts"] = output_parts_from_result(result)
        turn.setdefault("events", []).append(event)
        record["updated_at"] = timestamp
        self._write(record)

    def fail_turn(self, conversation_id: str, turn_id: str, message: str) -> None:
        record = self.get(conversation_id)
        if not record:
            return
        turn = _find_turn(record, turn_id)
        if not turn:
            return
        timestamp = _now()
        turn["status"] = "error"
        turn["updated_at"] = timestamp
        turn["error"] = str(message or "")
        record["updated_at"] = timestamp
        self._write(record)

    def history_for_agent(self, record: dict[str, Any] | None, limit: int = 8) -> list[dict[str, Any]]:
        if not record:
            return []
        turns = [turn for turn in record.get("turns", []) if turn.get("status") == "completed"]
        history = []
        for turn in turns[-limit:]:
            output = turn.get("output_parts") or {}
            history.append(
                {
                    "user_message": turn.get("message", ""),
                    "changes": turn.get("changes", []),
                    "final_titles": output.get("titles", ""),
                    "final_body": _truncate(output.get("body", ""), 420),
                    "final_tags": output.get("tags", ""),
                }
            )
        return history

    def _path(self, conversation_id: str) -> Path:
        return self.history_dir / f"{conversation_id}.json"

    def _read_all(self) -> list[dict[str, Any]]:
        records = []
        for path in sorted(self.history_dir.glob("*.json")):
            record = self._read(path)
            if record:
                records.append(record)
        return records

    def _read(self, path: Path) -> dict[str, Any] | None:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def _write(self, record: dict[str, Any]) -> None:
        path = self._path(record["id"])
        tmp_path = path.with_suffix(".json.tmp")
        tmp_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(path)

    def _summary(self, record: dict[str, Any]) -> dict[str, Any]:
        turns = record.get("turns", [])
        latest = turns[-1] if turns else {}
        return {
            "id": record.get("id", ""),
            "title": record.get("title", "未命名对话"),
            "created_at": record.get("created_at", ""),
            "updated_at": record.get("updated_at", ""),
            "turn_count": len(turns),
            "latest_message": latest.get("message", ""),
            "latest_status": latest.get("status", ""),
        }


def output_parts_from_result(result: dict[str, Any]) -> dict[str, str]:
    draft = result.get("draft") or {}
    titles = draft.get("titles") or []
    tags = [str(tag) if str(tag).startswith("#") else f"#{tag}" for tag in draft.get("tags") or []]
    return {
        "titles": "\n".join(f"{index + 1}. {title}" for index, title in enumerate(titles)),
        "body": str(draft.get("body") or ""),
        "tags": " ".join(tags),
    }


def _find_turn(record: dict[str, Any], turn_id: str) -> dict[str, Any] | None:
    for turn in record.get("turns", []):
        if turn.get("id") == turn_id:
            return turn
    return None


def _public_agent_input(agent_input: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in agent_input.items()
        if key not in {"conversation_history", "current_changes", "current_message"}
    }


def _truncate(value: Any, limit: int) -> str:
    text = str(value or "")
    return text if len(text) <= limit else f"{text[:limit]}..."
