from __future__ import annotations

import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


DEFAULT_DB_PATH = Path("data/rednote_matrix.sqlite3")


@dataclass(frozen=True)
class MemoryRecord:
    id: str
    namespace: str
    kind: str
    title: str
    content: str
    metadata: dict[str, Any]
    score: float = 0.0


def default_db_path() -> Path:
    data_dir = os.getenv("REDNOTE_DATA_DIR")
    if data_dir:
        return Path(data_dir) / "rednote_matrix.sqlite3"
    return DEFAULT_DB_PATH


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _normalize_namespace(namespace: str) -> str:
    cleaned = str(namespace or "global").strip().strip("/")
    return cleaned or "global"


def _split_query(query: str) -> list[str]:
    cleaned = str(query or "").strip()
    if not cleaned:
        return []
    tokens = [cleaned]
    try:
        import jieba

        tokens.extend(str(token).strip() for token in jieba.lcut(cleaned) if str(token).strip())
    except Exception:
        tokens.extend(part.strip() for part in cleaned.replace("，", " ").replace(",", " ").split() if part.strip())
    return list(dict.fromkeys(token for token in tokens if len(token) >= 2))


def _escape_fts_token(token: str) -> str:
    return str(token).replace('"', " ").strip()


class MemoryStore:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path else default_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL").close()
        conn.execute("PRAGMA foreign_keys=ON").close()
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
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    namespace TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    title TEXT NOT NULL DEFAULT '',
                    content TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_namespace ON memories(namespace)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_kind ON memories(kind)")
            conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
                    id UNINDEXED,
                    namespace,
                    kind,
                    title,
                    content,
                    tokenize='unicode61'
                )
                """
            )

    def add_memory(
        self,
        namespace: str,
        kind: str,
        content: str,
        title: str = "",
        metadata: dict[str, Any] | None = None,
        record_id: str | None = None,
    ) -> MemoryRecord:
        namespace = _normalize_namespace(namespace)
        record_id = record_id or str(uuid.uuid4())
        metadata_json = json.dumps(metadata or {}, ensure_ascii=False)
        timestamp = _now()
        with self._session() as conn:
            conn.execute(
                """
                INSERT INTO memories(id, namespace, kind, title, content, metadata_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    namespace = excluded.namespace,
                    kind = excluded.kind,
                    title = excluded.title,
                    content = excluded.content,
                    metadata_json = excluded.metadata_json,
                    updated_at = excluded.updated_at
                """,
                (record_id, namespace, kind, title, content, metadata_json, timestamp, timestamp),
            )
            conn.execute("DELETE FROM memory_fts WHERE id = ?", (record_id,))
            conn.execute(
                "INSERT INTO memory_fts(id, namespace, kind, title, content) VALUES (?, ?, ?, ?, ?)",
                (record_id, namespace, kind, title, content),
            )
        return MemoryRecord(
            id=record_id,
            namespace=namespace,
            kind=kind,
            title=title,
            content=content,
            metadata=metadata or {},
        )

    def list_memories(self, namespace: str, limit: int = 50) -> list[MemoryRecord]:
        namespace = _normalize_namespace(namespace)
        with self._session() as conn:
            rows = conn.execute(
                """
                SELECT id, namespace, kind, title, content, metadata_json
                FROM memories
                WHERE namespace = ?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (namespace, limit),
            ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def search(
        self,
        namespace: str,
        query: str,
        kinds: list[str] | None = None,
        limit: int = 8,
        include_global: bool = True,
    ) -> list[MemoryRecord]:
        namespace = _normalize_namespace(namespace)
        scopes = ["global", namespace] if include_global and namespace != "global" else [namespace]
        query = str(query or "").strip()
        tokens = _split_query(query)
        if not query and not kinds:
            rows = self._fetch_candidates(scopes, kinds, limit)
            return [self._row_to_record(row) for row in rows]

        candidates: dict[str, MemoryRecord] = {}
        for row in self._fetch_candidates(scopes, kinds, 500):
            record = self._row_to_record(row)
            score = self._score_record(record, query, tokens, namespace)
            if score > 0:
                candidates[record.id] = MemoryRecord(**{**record.__dict__, "score": score})

        for record in self._fts_search(scopes, query, kinds, limit * 4):
            score = max(record.score, self._score_record(record, query, tokens, namespace) + 2)
            candidates[record.id] = MemoryRecord(**{**record.__dict__, "score": score})

        return sorted(candidates.values(), key=lambda item: item.score, reverse=True)[:limit]

    def _fetch_candidates(self, scopes: list[str], kinds: list[str] | None, limit: int) -> list[sqlite3.Row]:
        placeholders = ",".join("?" for _ in scopes)
        params: list[Any] = [*scopes]
        kind_filter = ""
        if kinds:
            kind_placeholders = ",".join("?" for _ in kinds)
            kind_filter = f"AND kind IN ({kind_placeholders})"
            params.extend(kinds)
        params.append(limit)
        with self._session() as conn:
            return conn.execute(
                f"""
                SELECT id, namespace, kind, title, content, metadata_json
                FROM memories
                WHERE namespace IN ({placeholders}) {kind_filter}
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                params,
            ).fetchall()

    def _fts_search(
        self,
        scopes: list[str],
        query: str,
        kinds: list[str] | None,
        limit: int,
    ) -> list[MemoryRecord]:
        if not query:
            return []
        safe_query = " OR ".join(f'"{_escape_fts_token(token)}"' for token in _split_query(query)[:8] if _escape_fts_token(token))
        if not safe_query:
            return []
        placeholders = ",".join("?" for _ in scopes)
        params: list[Any] = [safe_query, *scopes]
        kind_filter = ""
        if kinds:
            kind_placeholders = ",".join("?" for _ in kinds)
            kind_filter = f"AND m.kind IN ({kind_placeholders})"
            params.extend(kinds)
        params.append(limit)
        try:
            with self._session() as conn:
                rows = conn.execute(
                    f"""
                    SELECT m.id, m.namespace, m.kind, m.title, m.content, m.metadata_json,
                           bm25(memory_fts) * -1 AS score
                    FROM memory_fts
                    JOIN memories m ON m.id = memory_fts.id
                    WHERE memory_fts MATCH ?
                      AND m.namespace IN ({placeholders})
                      {kind_filter}
                    ORDER BY score DESC
                    LIMIT ?
                    """,
                    params,
                ).fetchall()
        except sqlite3.OperationalError:
            return []
        return [self._row_to_record(row, score=float(row["score"])) for row in rows]

    @staticmethod
    def _score_record(record: MemoryRecord, query: str, tokens: list[str], namespace: str) -> float:
        text = f"{record.title}\n{record.content}".lower()
        score = 0.0
        if query and query.lower() in text:
            score += 8
        for token in tokens:
            score += text.count(token.lower()) * 2
        if record.namespace == namespace:
            score += 1
        if record.kind in {"product_fact", "risk_rule"}:
            score += 0.5
        return score

    @staticmethod
    def _row_to_record(row: sqlite3.Row, score: float = 0.0) -> MemoryRecord:
        metadata_raw = row["metadata_json"] if "metadata_json" in row.keys() else "{}"
        try:
            metadata = json.loads(metadata_raw or "{}")
        except json.JSONDecodeError:
            metadata = {}
        return MemoryRecord(
            id=row["id"],
            namespace=row["namespace"],
            kind=row["kind"],
            title=row["title"],
            content=row["content"],
            metadata=metadata,
            score=score,
        )
