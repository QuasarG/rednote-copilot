from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from rednote_matrix.memory.store import default_db_path


@dataclass(frozen=True)
class Conversation:
    id: str
    title: str
    agent_input: dict[str, Any]


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class ConversationStore:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path else default_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL").close()
        return conn

    @contextmanager
    def _session(self):
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._session() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL DEFAULT '',
                    agent_input_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS conversation_messages (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_conversation ON conversation_messages(conversation_id)")

    def upsert_conversation(
        self,
        conversation_id: str | None = None,
        title: str = "",
        agent_input: dict[str, Any] | None = None,
    ) -> Conversation:
        conversation_id = conversation_id or str(uuid.uuid4())
        existing = self.get_conversation(conversation_id)
        merged_input = _merge_agent_input(existing.agent_input if existing else {}, agent_input or {})
        timestamp = _now()
        with self._session() as conn:
            conn.execute(
                """
                INSERT INTO conversations(id, title, agent_input_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    title = CASE WHEN excluded.title != '' THEN excluded.title ELSE conversations.title END,
                    agent_input_json = excluded.agent_input_json,
                    updated_at = excluded.updated_at
                """,
                (conversation_id, title, json.dumps(merged_input, ensure_ascii=False), timestamp, timestamp),
            )
        return Conversation(id=conversation_id, title=title or (existing.title if existing else ""), agent_input=merged_input)

    def get_conversation(self, conversation_id: str) -> Conversation | None:
        with self._session() as conn:
            row = conn.execute(
                "SELECT id, title, agent_input_json FROM conversations WHERE id = ?",
                (conversation_id,),
            ).fetchone()
        if not row:
            return None
        try:
            agent_input = json.loads(row["agent_input_json"] or "{}")
        except json.JSONDecodeError:
            agent_input = {}
        return Conversation(id=row["id"], title=row["title"], agent_input=agent_input)

    def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        timestamp = _now()
        with self._session() as conn:
            conn.execute(
                """
                INSERT INTO conversation_messages(id, conversation_id, role, content, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (str(uuid.uuid4()), conversation_id, role, content, json.dumps(payload or {}, ensure_ascii=False), timestamp),
            )
            conn.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (timestamp, conversation_id))

    def list_messages(self, conversation_id: str, limit: int = 50) -> list[dict[str, Any]]:
        with self._session() as conn:
            rows = conn.execute(
                """
                SELECT role, content, payload_json, created_at
                FROM conversation_messages
                WHERE conversation_id = ?
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (conversation_id, limit),
            ).fetchall()
        messages = []
        for row in rows:
            try:
                payload = json.loads(row["payload_json"] or "{}")
            except json.JSONDecodeError:
                payload = {}
            messages.append(
                {
                    "role": row["role"],
                    "content": row["content"],
                    "payload": payload,
                    "created_at": row["created_at"],
                }
            )
        return messages


def _merge_agent_input(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in patch.items():
        if value in (None, "", []):
            continue
        merged[key] = value
    return merged
