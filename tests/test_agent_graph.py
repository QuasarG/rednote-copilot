from __future__ import annotations

import unittest
import os
import tempfile
from pathlib import Path

from rednote_matrix.core.models import AgentInput
from rednote_matrix.core.runner import run_agent
from rednote_matrix.integrations.xhs_core import build_default_keywords
from rednote_matrix.memory.store import MemoryStore
from tests.llm_fixtures import mock_agent_llm


def _all_draft_text(result) -> str:
    draft = result.draft
    return "\n".join([*draft.titles, draft.cover_text, draft.hook, draft.body, " ".join(draft.tags)])


class AgentGraphTest(unittest.TestCase):
    def test_sample_input_returns_publishable_result(self) -> None:
        with mock_agent_llm():
            result = run_agent(
                {
                    "product_name": "桌面收纳托盘",
                    "selling_points": ["小桌面也能放下", "拿东西不用翻半天", "颜色不突兀"],
                    "target_audience": "桌面总是越用越乱的人",
                    "scenario": "租房小书桌",
                }
            )

        self.assertEqual(result.status, "pass")
        self.assertEqual(result.draft.structure_type, "痛点-细节-避坑")
        self.assertGreaterEqual(result.structure_score, 80)
        self.assertGreaterEqual(result.compliance_score, 80)
        self.assertGreaterEqual(result.trend_score, 70)
        self.assertIn("project_builtin:xiaohongshu_framework", result.trend_insight.source)
        self.assertEqual(result.revision_history[0].node, "memory_retriever")
        self.assertEqual(result.revision_history[1].node, "market_research_agent")
        self.assertEqual(result.revision_history[2].node, "trend_agent")
        self.assertEqual(result.market_research_context.status, "disabled")
        self.assertGreaterEqual(len(result.draft.titles), 2)

    def test_risky_selling_points_are_softened(self) -> None:
        with mock_agent_llm():
            result = run_agent(
                {
                    "product_name": "精华水",
                    "selling_points": ["全网最低", "绝对提亮", "立刻见效"],
                    "target_audience": "熬夜后脸色暗沉的人",
                    "scenario": "早八上妆前",
                }
            )

        text = _all_draft_text(result)
        self.assertNotIn("全网最低", text)
        self.assertNotIn("绝对", text)
        self.assertNotIn("立刻见效", text)
        self.assertEqual(result.route_reason, "pass")
        self.assertGreaterEqual(result.loop_count, 1)
        self.assertEqual(result.status, "pass")

    def test_agent_retrieves_product_memory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            old_data_dir = os.environ.get("REDNOTE_DATA_DIR")
            os.environ["REDNOTE_DATA_DIR"] = tmpdir
            try:
                store = MemoryStore(Path(tmpdir) / "rednote_matrix.sqlite3")
                store.add_memory(
                    "brand/acme/tray",
                    "product_fact",
                    "这款桌面收纳托盘是雾白色，售价 39 元。",
                    "商品事实",
                )

                with mock_agent_llm():
                    result = run_agent(
                        {
                            "product_name": "桌面收纳托盘",
                            "selling_points": ["小桌面也能放下", "拿东西不用翻半天"],
                            "target_audience": "租房小桌面用户",
                            "scenario": "晚上一边办公一边找东西",
                            "memory_namespace": "brand/acme/tray",
                        }
                    )
            finally:
                if old_data_dir is None:
                    os.environ.pop("REDNOTE_DATA_DIR", None)
                else:
                    os.environ["REDNOTE_DATA_DIR"] = old_data_dir

        self.assertEqual(result.revision_history[0].node, "memory_retriever")
        self.assertEqual(result.memory_context.namespace, "brand/acme/tray")
        self.assertTrue(result.memory_context.product_facts)
        self.assertIn("雾白色", result.draft.body)
        self.assertNotIn("39", _all_draft_text(result))
        self.assertNotIn("售价", _all_draft_text(result))

    def test_price_input_is_not_exposed_in_final_copy(self) -> None:
        with mock_agent_llm():
            result = run_agent(
                {
                    "product_name": "桌面收纳托盘",
                    "price": "39元",
                    "selling_points": ["小桌面也能放下", "拿东西不用翻半天"],
                    "target_audience": "租房小桌面用户",
                    "scenario": "晚上一边办公一边找东西",
                }
            )

        text = _all_draft_text(result)
        self.assertEqual(result.status, "pass")
        self.assertNotIn("39", text)
        self.assertNotIn("价格大概", text)
        self.assertFalse(any(risk.type == "price_mention" for risk in result.risk_items))

    def test_medium_hard_sell_words_are_revised(self) -> None:
        with mock_agent_llm():
            result = run_agent(
                {
                    "product_name": "桌面收纳托盘",
                    "selling_points": ["下单后桌面更整齐", "链接里有尺寸"],
                    "target_audience": "租房小桌面用户",
                    "scenario": "晚上一边办公一边找东西",
                }
            )

        text = _all_draft_text(result)
        self.assertNotIn("下单", text)
        self.assertNotIn("链接", text)
        self.assertEqual(result.route_reason, "pass")
        self.assertGreaterEqual(result.loop_count, 1)
        self.assertEqual(result.status, "pass")

    def test_default_realtime_keywords_focus_related_viral_notes(self) -> None:
        keywords = build_default_keywords(
            AgentInput.model_validate(
                {
                "product_name": "桌面收纳托盘",
                "selling_points": ["小桌面也能放下", "拿东西不用翻半天"],
                "target_audience": "租房小桌面用户",
                "scenario": "晚上一边办公一边找东西",
                }
            )
        )

        joined = "\n".join(keywords)
        self.assertIn("桌面收纳托盘 爆款笔记", keywords)
        self.assertIn("桌面收纳托盘 真实体验", keywords)
        self.assertIn("桌面收纳托盘 避坑", keywords)
        self.assertIn("租房小桌面用户", joined)


if __name__ == "__main__":
    unittest.main()
