from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from rednote_matrix.memory.ingestion import chunk_text, ingest_document
from rednote_matrix.memory.store import MemoryStore


class MemoryStoreTest(unittest.TestCase):
    def test_namespace_search_and_global_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = MemoryStore(Path(tmpdir) / "memory.sqlite3")
            store.add_memory("global", "risk_rule", "禁止使用绝对、第一、全网最低等极限词", "平台合规")
            store.add_memory("brand/acme/tray", "product_fact", "桌面收纳托盘售价 39 元，适合租房小桌面", "商品事实")
            store.add_memory("brand/other", "product_fact", "护手霜主打滋润", "其他商品")

            results = store.search("brand/acme/tray", "租房小桌面 极限词", limit=5)
            titles = [record.title for record in results]

            self.assertIn("商品事实", titles)
            self.assertIn("平台合规", titles)
            self.assertNotIn("其他商品", titles)

    def test_ingest_markdown_document(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            doc = root / "brand.md"
            doc.write_text(
                "品牌语气：克制、真实、不喊口号。\n\n"
                "商品事实：托盘颜色是雾白色，售价 39 元。\n\n"
                "禁用表达：闭眼入、全网最低。",
                encoding="utf-8",
            )
            store = MemoryStore(root / "memory.sqlite3")

            records = ingest_document(store, "brand/acme/tray", doc, kind="brand_doc", max_chars=40)
            results = store.search("brand/acme/tray", "雾白色 售价", kinds=["brand_doc"])

            self.assertGreaterEqual(len(records), 2)
            self.assertTrue(any("雾白色" in record.content for record in results))

    def test_chunk_text_keeps_overlap_for_long_lines(self) -> None:
        text = "a" * 80
        chunks = chunk_text(text, max_chars=30, overlap=5)

        self.assertEqual(len(chunks), 3)
        self.assertEqual(chunks[0][-5:], chunks[1][:5])


if __name__ == "__main__":
    unittest.main()
