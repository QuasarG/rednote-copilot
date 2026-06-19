from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from rednote_matrix.core.models import AgentInput, AgentResult
from rednote_matrix.core.render import render_user_copy
from rednote_matrix.core.runner import run_agent
from rednote_matrix.integrations.xhs_core import (
    check_xhs_auth,
    check_xhs_environment,
    login_session_status,
    persistent_browser_status,
    result_to_dict,
    save_cookie,
    search_xhs_keywords,
    start_persistent_browser,
    start_qrcode_login_process,
    stop_persistent_browser,
)
from rednote_matrix.memory.conversation import ConversationStore
from rednote_matrix.memory.ingestion import ingest_document
from rednote_matrix.memory.store import MemoryStore, default_db_path


app = FastAPI(title="RedNoteMatrix Copilot API", version="0.1.0")


class ChatRequest(BaseModel):
    conversation_id: str | None = None
    message: str = ""
    agent_input: dict[str, Any] = Field(default_factory=dict)
    debug: bool = False


class ChatResponse(BaseModel):
    conversation_id: str
    output: str
    result: AgentResult | None = None


class MemoryCreateRequest(BaseModel):
    namespace: str
    kind: str
    content: str
    title: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentPathRequest(BaseModel):
    namespace: str
    file_path: str
    kind: str = "document_chunk"
    title: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CookieRequest(BaseModel):
    cookie: str


class QrcodeLoginRequest(BaseModel):
    timeout_seconds: int = 180


class PersistentBrowserRequest(BaseModel):
    timeout_seconds: int = 0
    force_restart: bool = False


class XhsSearchRequest(BaseModel):
    keywords: list[str]
    max_notes_count: int = 12
    execute: bool = True
    headless: bool = True
    browser_fallback: bool = True


@app.get("/health")
def health() -> dict[str, Any]:
    xhs_env = check_xhs_environment(deep=False)
    return {
        "status": "ok",
        "db_path": str(default_db_path()),
        "xhs_core": result_to_dict(xhs_env),
        "xhs_auth": result_to_dict(check_xhs_auth()),
    }


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    conversations = ConversationStore()
    agent_patch = _agent_input_patch_from_chat_request(request)
    conversation = conversations.upsert_conversation(
        conversation_id=request.conversation_id,
        title=agent_patch.get("product_name", ""),
        agent_input=agent_patch,
    )
    if request.message:
        conversations.add_message(conversation.id, "user", request.message, {"agent_input": agent_patch})

    try:
        agent_input = AgentInput.model_validate(conversation.agent_input)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="输入格式不合法，请检查商品背景或自然语言需求") from exc
    try:
        result = run_agent(agent_input)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    output = render_user_copy(result)
    conversations.add_message(conversation.id, "assistant", output, result.model_dump())
    conversations.upsert_conversation(
        conversation_id=conversation.id,
        title=result.resolved_user_input.get("product_name", ""),
        agent_input=_public_resolved_input(result.resolved_user_input),
    )

    return ChatResponse(
        conversation_id=conversation.id,
        output=output,
        result=result if request.debug else None,
    )


def _agent_input_patch_from_chat_request(request: ChatRequest) -> dict[str, Any]:
    patch = dict(request.agent_input or {})
    message = request.message.strip()
    if message:
        patch["current_message"] = message
        if not patch.get("raw_user_request") and not patch.get("product_name"):
            patch["raw_user_request"] = message
    return patch


def _public_resolved_input(agent_input: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in agent_input.items()
        if key not in {"conversation_history", "current_changes", "current_message", "raw_user_request"}
    }


@app.post("/memories")
def create_memory(request: MemoryCreateRequest) -> dict[str, Any]:
    store = MemoryStore()
    record = store.add_memory(
        namespace=request.namespace,
        kind=request.kind,
        title=request.title,
        content=request.content,
        metadata=request.metadata,
    )
    return {"id": record.id, "namespace": record.namespace, "kind": record.kind, "title": record.title}


@app.get("/memories")
def search_memories(namespace: str, query: str = "", kind: str = "", limit: int = 8) -> dict[str, Any]:
    store = MemoryStore()
    kinds = [kind] if kind else None
    records = store.search(namespace, query, kinds=kinds, limit=limit)
    return {
        "items": [
            {
                "id": record.id,
                "namespace": record.namespace,
                "kind": record.kind,
                "title": record.title,
                "content": record.content,
                "score": record.score,
                "metadata": record.metadata,
            }
            for record in records
        ]
    }


@app.get("/integrations/xhs/status")
def xhs_status(deep: bool = False) -> dict[str, Any]:
    return {
        "environment": result_to_dict(check_xhs_environment(deep=deep)),
        "xhs_auth": result_to_dict(check_xhs_auth()),
    }


@app.post("/integrations/xhs/auth/cookie")
def set_xhs_cookie(request: CookieRequest) -> dict[str, Any]:
    if "web_session=" not in request.cookie:
        raise HTTPException(status_code=400, detail="cookie 缺少 web_session")
    return result_to_dict(save_cookie(request.cookie))


@app.post("/integrations/xhs/browser/start")
def start_xhs_persistent_browser(request: PersistentBrowserRequest) -> dict[str, Any]:
    status = start_persistent_browser(timeout_seconds=request.timeout_seconds, force_restart=request.force_restart)
    if status.status == "error":
        raise HTTPException(status_code=500, detail=status.message)
    return result_to_dict(status)


@app.get("/integrations/xhs/browser/status")
def get_xhs_persistent_browser_status() -> dict[str, Any]:
    return result_to_dict(persistent_browser_status())


@app.post("/integrations/xhs/browser/stop")
def stop_xhs_persistent_browser() -> dict[str, Any]:
    return result_to_dict(stop_persistent_browser())


@app.get("/integrations/xhs/browser/qrcode")
def get_xhs_persistent_browser_qrcode() -> FileResponse:
    status = persistent_browser_status()
    path = Path(status.qrcode_path)
    if not status.qrcode_path or not path.exists():
        raise HTTPException(status_code=404, detail="二维码尚未生成")
    return FileResponse(path, media_type="image/png")


@app.post("/integrations/xhs/login/qrcode")
def start_xhs_qrcode_login(request: QrcodeLoginRequest) -> dict[str, Any]:
    session = start_qrcode_login_process(
        timeout_seconds=request.timeout_seconds,
    )
    if session.status == "error":
        raise HTTPException(status_code=500, detail=session.message)
    payload = result_to_dict(session)
    payload["qrcode_url"] = f"/integrations/xhs/login/{session.session_id}/qrcode"
    return payload


@app.get("/integrations/xhs/login/{session_id}")
def get_xhs_login_session(session_id: str) -> dict[str, Any]:
    session = login_session_status(session_id)
    payload = result_to_dict(session)
    payload["qrcode_url"] = f"/integrations/xhs/login/{session.session_id}/qrcode" if session.session_id else ""
    return payload


@app.get("/integrations/xhs/login/{session_id}/qrcode")
def get_xhs_login_qrcode(session_id: str) -> FileResponse:
    session = login_session_status(session_id)
    if not session.qrcode_path:
        raise HTTPException(status_code=404, detail="二维码尚未生成")
    path = Path(session.qrcode_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="二维码尚未生成")
    return FileResponse(path, media_type="image/png")


@app.post("/integrations/xhs/search")
def xhs_search(request: XhsSearchRequest) -> dict[str, Any]:
    if not request.keywords:
        raise HTTPException(status_code=400, detail="至少需要 1 个关键词")
    result = search_xhs_keywords(
        keywords=request.keywords,
        max_notes_count=request.max_notes_count,
        headless=request.headless,
        execute=request.execute,
        browser_fallback=request.browser_fallback,
    )
    return result_to_dict(result)


@app.post("/documents/path")
def ingest_document_path(request: DocumentPathRequest) -> dict[str, Any]:
    store = MemoryStore()
    records = ingest_document(
        store=store,
        namespace=request.namespace,
        file_path=request.file_path,
        kind=request.kind,
        title=request.title,
        metadata=request.metadata,
    )
    return {"count": len(records), "ids": [record.id for record in records]}


@app.post("/documents/upload")
async def ingest_document_upload(
    namespace: str,
    kind: str = "document_chunk",
    title: str | None = None,
    file: UploadFile = File(...),
) -> dict[str, Any]:
    data_dir = Path(os.getenv("REDNOTE_DATA_DIR", "data"))
    upload_dir = data_dir / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(file.filename or "upload.txt").suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix, dir=upload_dir) as tmp:
        tmp.write(await file.read())
        tmp_path = Path(tmp.name)

    store = MemoryStore()
    records = ingest_document(
        store=store,
        namespace=namespace,
        file_path=tmp_path,
        kind=kind,
        title=title or Path(file.filename or tmp_path.name).stem,
        metadata={"uploaded_filename": file.filename or ""},
    )
    return {"count": len(records), "ids": [record.id for record in records], "stored_path": str(tmp_path)}
