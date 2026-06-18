from __future__ import annotations

import os
import tempfile
import unittest

from rednote_matrix.web.workbench import app
from tests.llm_fixtures import mock_agent_llm


class WorkbenchTest(unittest.TestCase):
    def test_workbench_index_and_stream(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            old_data_dir = os.environ.get("REDNOTE_DATA_DIR")
            os.environ["REDNOTE_DATA_DIR"] = tmpdir
            try:
                client = app.test_client()
                index = client.get("/")
                with mock_agent_llm():
                    response = client.post(
                        "/ui/agent/stream",
                        json={
                            "product_name": "桌面收纳托盘",
                            "selling_points": "小桌面也能放下\n拿东西不用翻半天",
                            "target_audience": "租房小桌面用户",
                            "scenario": "晚上办公找东西",
                            "tone": "自然、可信、轻种草",
                        },
                    )
                body = response.get_data(as_text=True)
            finally:
                if old_data_dir is None:
                    os.environ.pop("REDNOTE_DATA_DIR", None)
                else:
                    os.environ["REDNOTE_DATA_DIR"] = old_data_dir

        self.assertEqual(index.status_code, 200)
        page = index.get_data(as_text=True)
        self.assertIn("种草文案", page)
        self.assertIn("Agent 工作台", page)
        self.assertIn("复制标题", page)
        self.assertIn("复制正文", page)
        self.assertIn("复制标签", page)
        self.assertIn("导入 JSON", page)
        self.assertIn("禁用词", page)
        self.assertNotIn("Final Copy", page)
        self.assertNotIn("systemPill", page)
        self.assertNotIn("填入示例", page)
        self.assertNotIn("自定义 Prompt", page)
        self.assertNotIn("小红书连接", page)
        self.assertNotIn("Agent 节点进度", page)
        self.assertEqual(response.status_code, 200)
        self.assertIn('"node": "memory_retriever"', body)
        self.assertIn('"node": "final_packager"', body)
        self.assertIn('"type": "result"', body)


if __name__ == "__main__":
    unittest.main()
