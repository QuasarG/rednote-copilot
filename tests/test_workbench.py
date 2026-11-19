from __future__ import annotations

import os
import json
import tempfile
import unittest
from unittest.mock import patch

from rednote_matrix.web.workbench import app
from tests.llm_fixtures import mock_agent_llm


def _sse_events(body: str) -> list[dict]:
    events = []
    for part in body.split("\n\n"):
        line = next((item for item in part.splitlines() if item.startswith("data: ")), "")
        if line:
            events.append(json.loads(line[6:]))
    return events


class WorkbenchTest(unittest.TestCase):
    def test_workbench_index_and_stream(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            old_data_dir = os.environ.get("REDNOTE_DATA_DIR")
            old_history_dir = os.environ.get("REDNOTE_WORKBENCH_HISTORY_DIR")
            os.environ["REDNOTE_DATA_DIR"] = tmpdir
            os.environ["REDNOTE_WORKBENCH_HISTORY_DIR"] = os.path.join(tmpdir, "history")
            try:
                client = app.test_client()
                index = client.get("/")
                with mock_agent_llm():
                    response = client.post(
                        "/ui/agent/stream",
                        json={
                            "message": "帮我写桌面收纳托盘的小红书文案，给租房小桌面用户看，强调小桌面也能放下和拿东西方便，语气自然可信",
                        },
                        buffered=True,
                    )
                    body = response.get_data(as_text=True)
            finally:
                if old_data_dir is None:
                    os.environ.pop("REDNOTE_DATA_DIR", None)
                else:
                    os.environ["REDNOTE_DATA_DIR"] = old_data_dir
                if old_history_dir is None:
                    os.environ.pop("REDNOTE_WORKBENCH_HISTORY_DIR", None)
                else:
                    os.environ["REDNOTE_WORKBENCH_HISTORY_DIR"] = old_history_dir

        self.assertEqual(index.status_code, 200)
        page = index.get_data(as_text=True)
        self.assertIn("种草文案", page)
        self.assertIn("Agent 工作台", page)
        self.assertIn("复制标题", page)
        self.assertIn("复制正文", page)
        self.assertIn("复制标签", page)
        self.assertIn("爆款样本", page)
        self.assertIn("检索条数", page)
        self.assertIn("可总结经验", page)
        self.assertNotIn("Final Copy", page)
        self.assertNotIn("systemPill", page)
        self.assertNotIn("填入示例", page)
        self.assertNotIn("导入 JSON", page)
        self.assertNotIn("自定义 Prompt", page)
        self.assertNotIn("商品背景", page)
        self.assertNotIn("小红书连接", page)
        self.assertNotIn("Agent 节点进度", page)
        self.assertEqual(response.status_code, 200)
        self.assertIn('"node": "input_parser"', body)
        self.assertIn('"node": "memory_retriever"', body)
        self.assertIn('"node": "final_packager"', body)
        self.assertIn('"type": "result"', body)
        self.assertIn('"conversation_id"', body)

    def test_workbench_saves_and_restores_local_conversation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            old_data_dir = os.environ.get("REDNOTE_DATA_DIR")
            old_history_dir = os.environ.get("REDNOTE_WORKBENCH_HISTORY_DIR")
            os.environ["REDNOTE_DATA_DIR"] = tmpdir
            os.environ["REDNOTE_WORKBENCH_HISTORY_DIR"] = os.path.join(tmpdir, "history")
            try:
                client = app.test_client()
                with mock_agent_llm():
                    first = client.post(
                        "/ui/agent/stream",
                        json={
                            "message": "帮我写桌面收纳托盘的小红书文案，给租房小桌面用户看，强调小桌面也能放下",
                        },
                        buffered=True,
                    )
                    first_events = _sse_events(first.get_data(as_text=True))
                conversation_id = first_events[0]["conversation_id"]
                with mock_agent_llm():
                    second = client.post(
                        "/ui/agent/stream",
                        json={
                            "conversation_id": conversation_id,
                            "product_name": "桌面收纳托盘",
                            "selling_points": "小桌面也能放下",
                            "target_audience": "租房小桌面用户",
                            "scenario": "晚上办公找东西",
                            "tone": "自然、可信、轻种草",
                            "message": "标题再像真人一点",
                        },
                        buffered=True,
                    )
                listing = client.get("/ui/conversations")
                detail = client.get(f"/ui/conversations/{conversation_id}")
                delete_response = client.delete(f"/ui/conversations/{conversation_id}")
                deleted_listing = client.get("/ui/conversations")
                deleted_detail = client.get(f"/ui/conversations/{conversation_id}")
            finally:
                if old_data_dir is None:
                    os.environ.pop("REDNOTE_DATA_DIR", None)
                else:
                    os.environ["REDNOTE_DATA_DIR"] = old_data_dir
                if old_history_dir is None:
                    os.environ.pop("REDNOTE_WORKBENCH_HISTORY_DIR", None)
                else:
                    os.environ["REDNOTE_WORKBENCH_HISTORY_DIR"] = old_history_dir

        self.assertEqual(second.status_code, 200)
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(delete_response.status_code, 200)
        self.assertEqual(deleted_detail.status_code, 404)
        self.assertEqual(listing.get_json()["items"][0]["id"], conversation_id)
        self.assertEqual(len(listing.get_json()["items"][0]["turns"]), 2)
        self.assertIn("reply_preview", listing.get_json()["items"][0]["turns"][0])
        self.assertEqual(deleted_listing.get_json()["items"], [])
        record = detail.get_json()
        self.assertEqual(len(record["turns"]), 2)
        self.assertEqual(record["turns"][1]["message"], "标题再像真人一点")
        self.assertEqual(record["agent_input"]["product_name"], "桌面收纳托盘")
        self.assertEqual(record["turns"][0]["status"], "completed")
        self.assertIn("titles", record["turns"][0]["output_parts"])

    def test_workbench_streams_market_notes_incrementally(self) -> None:
        def fake_search(*args, **kwargs):
            from rednote_matrix.integrations.xhs_core import XhsSearchResult

            notes = [
                {
                    "title": "小桌面收纳爆了",
                    "note_url": "https://www.xiaohongshu.com/explore/1",
                    "liked_count": "1200",
                    "comment_count": "88",
                    "source_keyword": "桌面收纳 爆款笔记",
                },
                {
                    "title": "租房桌面真的别乱买",
                    "note_url": "https://www.xiaohongshu.com/explore/2",
                    "liked_count": "980",
                    "comment_count": "140",
                    "source_keyword": "桌面收纳 避坑",
                },
            ]
            on_note = kwargs.get("on_note")
            for note in notes:
                if on_note:
                    on_note(note)
            return XhsSearchResult("completed", "/tmp/xhs", {"keywords": []}, notes, return_code=0, message="搜索完成")

        with tempfile.TemporaryDirectory() as tmpdir:
            old_data_dir = os.environ.get("REDNOTE_DATA_DIR")
            old_history_dir = os.environ.get("REDNOTE_WORKBENCH_HISTORY_DIR")
            os.environ["REDNOTE_DATA_DIR"] = tmpdir
            os.environ["REDNOTE_WORKBENCH_HISTORY_DIR"] = os.path.join(tmpdir, "history")
            try:
                client = app.test_client()
                from rednote_matrix.integrations.xhs_core import XhsCoreEnvironment

                with (
                    mock_agent_llm(),
                    patch(
                        "rednote_matrix.agents.market_research_agent.check_xhs_environment",
                        return_value=XhsCoreEnvironment(True, True, True, [], []),
                    ),
                    patch("rednote_matrix.agents.market_research_agent.search_xhs_keywords", side_effect=fake_search),
                ):
                    response = client.post(
                        "/ui/agent/stream",
                        json={
                            "message": "帮我写桌面收纳托盘的小红书文案",
                            "enable_realtime_research": True,
                            "realtime_research_max_notes": 2,
                        },
                        buffered=True,
                    )
                    events = _sse_events(response.get_data(as_text=True))
            finally:
                if old_data_dir is None:
                    os.environ.pop("REDNOTE_DATA_DIR", None)
                else:
                    os.environ["REDNOTE_DATA_DIR"] = old_data_dir
                if old_history_dir is None:
                    os.environ.pop("REDNOTE_WORKBENCH_HISTORY_DIR", None)
                else:
                    os.environ["REDNOTE_WORKBENCH_HISTORY_DIR"] = old_history_dir

        market_events = [event for event in events if event.get("type") == "market_note"]
        market_note_index = next(index for index, event in enumerate(events) if event.get("type") == "market_note")
        market_done_index = next(
            index
            for index, event in enumerate(events)
            if event.get("type") == "node"
            and event.get("node") == "market_research_agent"
            and event.get("status") == "done"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(market_events), 2)
        self.assertLess(market_note_index, market_done_index)
        self.assertEqual(market_events[0]["note"]["title"], "小桌面收纳爆了")
        self.assertIn("note_url", market_events[0]["note"])

    def test_workbench_followup_inherits_price_and_can_add_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            old_data_dir = os.environ.get("REDNOTE_DATA_DIR")
            old_history_dir = os.environ.get("REDNOTE_WORKBENCH_HISTORY_DIR")
            os.environ["REDNOTE_DATA_DIR"] = tmpdir
            os.environ["REDNOTE_WORKBENCH_HISTORY_DIR"] = os.path.join(tmpdir, "history")
            try:
                client = app.test_client()
                with mock_agent_llm():
                    first = client.post(
                        "/ui/agent/stream",
                        json={
                            "product_name": "桌面收纳托盘",
                            "price": "39元",
                            "selling_points": "小桌面也能放下",
                            "target_audience": "租房小桌面用户",
                            "scenario": "租房小书桌",
                            "message": "先写一版",
                        },
                        buffered=True,
                    )
                    conversation_id = _sse_events(first.get_data(as_text=True))[0]["conversation_id"]
                with mock_agent_llm():
                    second = client.post(
                        "/ui/agent/stream",
                        json={"conversation_id": conversation_id, "message": "加上价格"},
                        buffered=True,
                    )
                    second_events = _sse_events(second.get_data(as_text=True))
            finally:
                if old_data_dir is None:
                    os.environ.pop("REDNOTE_DATA_DIR", None)
                else:
                    os.environ["REDNOTE_DATA_DIR"] = old_data_dir
                if old_history_dir is None:
                    os.environ.pop("REDNOTE_WORKBENCH_HISTORY_DIR", None)
                else:
                    os.environ["REDNOTE_WORKBENCH_HISTORY_DIR"] = old_history_dir

        result = next(event["result"] for event in second_events if event.get("type") == "result")
        body = result["draft"]["body"]
        self.assertEqual(second.status_code, 200)
        self.assertIn("39元", body)
        self.assertEqual(result["resolved_user_input"]["price"], "39元")

    def test_natural_language_followup_inherits_resolved_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            old_data_dir = os.environ.get("REDNOTE_DATA_DIR")
            old_history_dir = os.environ.get("REDNOTE_WORKBENCH_HISTORY_DIR")
            os.environ["REDNOTE_DATA_DIR"] = tmpdir
            os.environ["REDNOTE_WORKBENCH_HISTORY_DIR"] = os.path.join(tmpdir, "history")
            try:
                client = app.test_client()
                with mock_agent_llm():
                    first = client.post(
                        "/ui/agent/stream",
                        json={
                            "message": (
                                "帮我写一篇小红书种草文案。产品是厨房油污清洁湿巾，品牌叫 CleanMint，"
                                "目标人群是经常做饭但不想花太多时间刷灶台的租房女生。价格是 29.9 元一包，"
                                "但正文里不要直接写价格。重点写做完饭顺手擦一下就干净、不用戴手套刷半天。"
                            ),
                            "enable_realtime_research": False,
                        },
                        buffered=True,
                    )
                    conversation_id = _sse_events(first.get_data(as_text=True))[0]["conversation_id"]
                with mock_agent_llm():
                    second = client.post(
                        "/ui/agent/stream",
                        json={"conversation_id": conversation_id, "message": "试试把价格加上去"},
                        buffered=True,
                    )
                    second_events = _sse_events(second.get_data(as_text=True))
                detail = client.get(f"/ui/conversations/{conversation_id}")
            finally:
                if old_data_dir is None:
                    os.environ.pop("REDNOTE_DATA_DIR", None)
                else:
                    os.environ["REDNOTE_DATA_DIR"] = old_data_dir
                if old_history_dir is None:
                    os.environ.pop("REDNOTE_WORKBENCH_HISTORY_DIR", None)
                else:
                    os.environ["REDNOTE_WORKBENCH_HISTORY_DIR"] = old_history_dir

        result = next(event["result"] for event in second_events if event.get("type") == "result")
        record = detail.get_json()
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(result["resolved_user_input"]["product_name"], "厨房油污清洁湿巾")
        self.assertEqual(result["resolved_user_input"]["brand_name"], "CleanMint")
        self.assertEqual(result["resolved_user_input"]["price"], "29.9元一包")
        self.assertIn("29.9元一包", result["draft"]["body"])
        self.assertEqual(record["agent_input"]["product_name"], "厨房油污清洁湿巾")
        self.assertEqual(record["turns"][0]["agent_input"]["product_name"], "厨房油污清洁湿巾")


if __name__ == "__main__":
    unittest.main()
