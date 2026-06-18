from __future__ import annotations

from pathlib import Path
from typing import Any

from rednote_matrix.memory.store import MemoryRecord, MemoryStore


SUPPORTED_EXTENSIONS = {".txt", ".md", ".pdf"}


def read_document_text(file_path: str | Path) -> str:
    path = Path(file_path)
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"暂不支持的文档类型: {suffix}")
    if suffix in {".txt", ".md"}:
        return path.read_text(encoding="utf-8")
    return _read_pdf(path)


def chunk_text(text: str, max_chars: int = 900, overlap: int = 120) -> list[str]:
    cleaned = "\n".join(line.strip() for line in str(text).splitlines() if line.strip())
    if not cleaned:
        return []

    paragraphs = cleaned.splitlines()
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if len(current) + len(paragraph) + 1 <= max_chars:
            current = f"{current}\n{paragraph}".strip()
            continue
        if current:
            chunks.append(current)
        if len(paragraph) <= max_chars:
            current = paragraph
        else:
            chunks.extend(_split_long_text(paragraph, max_chars, overlap))
            current = ""
    if current:
        chunks.append(current)
    return chunks


def ingest_document(
    store: MemoryStore,
    namespace: str,
    file_path: str | Path,
    kind: str = "document_chunk",
    title: str | None = None,
    metadata: dict[str, Any] | None = None,
    max_chars: int = 900,
) -> list[MemoryRecord]:
    path = Path(file_path)
    text = read_document_text(path)
    chunks = chunk_text(text, max_chars=max_chars)
    records: list[MemoryRecord] = []
    base_title = title or path.stem
    for index, chunk in enumerate(chunks, 1):
        record = store.add_memory(
            namespace=namespace,
            kind=kind,
            title=f"{base_title} #{index}",
            content=chunk,
            metadata={
                "source_file": str(path),
                "chunk_index": index,
                "chunk_count": len(chunks),
                **(metadata or {}),
            },
        )
        records.append(record)
    return records


def _split_long_text(text: str, max_chars: int, overlap: int) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = min(len(text), start + max_chars)
        chunks.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(0, end - overlap)
    return [chunk for chunk in chunks if chunk]


def _read_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("读取 PDF 需要安装 pypdf") from exc

    reader = PdfReader(str(path))
    pages = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    return "\n".join(pages).strip()
