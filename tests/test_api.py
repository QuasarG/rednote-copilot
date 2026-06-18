from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from rednote_matrix.integrations.xhs_core import (
    XhsCoreEnvironment,
    search_xhs_keywords,
    start_persistent_browser,
    start_qrcode_login_process,
)
from rednote_matrix.server.api import app
from tests.llm_fixtures import mock_agent_llm


class ApiTest(unittest.TestCase):
    def test_chat_and_memory_endpoints(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            old_data_dir = os.environ.get("REDNOTE_DATA_DIR")
            os.environ["REDNOTE_DATA_DIR"] = tmpdir
            try:
                client = TestClient(app)
                memory_response = client.post(
                    "/memories",
                    json={
                        "namespace": "brand/acme/tray",
                        "kind": "product_fact",
                        "title": "商品事实",
                        "content": "桌面收纳托盘是雾白色，售价 39 元。",
                    },
                )
                with mock_agent_llm():
                    chat_response = client.post(
                        "/chat",
                        json={
                            "message": "帮我写一条",
                            "debug": True,
                            "agent_input": {
                                "product_name": "桌面收纳托盘",
                                "selling_points": ["小桌面也能放下", "拿东西不用翻半天"],
                                "target_audience": "租房小桌面用户",
                                "scenario": "晚上一边办公一边找东西",
                                "memory_namespace": "brand/acme/tray",
                            },
                        },
                    )
            finally:
                if old_data_dir is None:
                    os.environ.pop("REDNOTE_DATA_DIR", None)
                else:
                    os.environ["REDNOTE_DATA_DIR"] = old_data_dir

        self.assertEqual(memory_response.status_code, 200)
        self.assertEqual(chat_response.status_code, 200)
        payload = chat_response.json()
        self.assertIn("标题：", payload["output"])
        self.assertIn("雾白色", payload["output"])
        self.assertNotIn("39", payload["output"])
        self.assertNotIn("售价", payload["output"])
        self.assertEqual(payload["result"]["memory_context"]["namespace"], "brand/acme/tray")

    def test_chat_requires_product_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            old_data_dir = os.environ.get("REDNOTE_DATA_DIR")
            os.environ["REDNOTE_DATA_DIR"] = tmpdir
            try:
                client = TestClient(app)
                response = client.post("/chat", json={"message": "先聊聊"})
            finally:
                if old_data_dir is None:
                    os.environ.pop("REDNOTE_DATA_DIR", None)
                else:
                    os.environ["REDNOTE_DATA_DIR"] = old_data_dir

        self.assertEqual(response.status_code, 400)

    def test_xhs_status_and_search_without_cookie(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            old_data_dir = os.environ.get("REDNOTE_DATA_DIR")
            os.environ["REDNOTE_DATA_DIR"] = tmpdir
            try:
                client = TestClient(app)
                status_response = client.get("/integrations/xhs/status")
                search_response = client.post(
                    "/integrations/xhs/search",
                    json={"keywords": ["桌面收纳托盘 爆款笔记"], "max_notes_count": 2, "execute": False},
                )
            finally:
                if old_data_dir is None:
                    os.environ.pop("REDNOTE_DATA_DIR", None)
                else:
                    os.environ["REDNOTE_DATA_DIR"] = old_data_dir

        self.assertEqual(status_response.status_code, 200)
        self.assertIn("environment", status_response.json())
        self.assertEqual(search_response.status_code, 200)
        self.assertEqual(search_response.json()["status"], "needs_login")

    def test_qrcode_login_uses_detached_worker_process(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            old_data_dir = os.environ.get("REDNOTE_DATA_DIR")
            os.environ["REDNOTE_DATA_DIR"] = tmpdir
            try:
                with (
                    patch(
                        "rednote_matrix.integrations.xhs_core.check_xhs_environment",
                        return_value=XhsCoreEnvironment(True, True, True, True, [], []),
                    ),
                    patch("rednote_matrix.integrations.xhs_core.shutil.which", return_value="/usr/bin/Xvfb"),
                    patch("rednote_matrix.integrations.xhs_core.subprocess.Popen") as popen,
                ):
                    session = start_qrcode_login_process(headless=False, timeout_seconds=33)
                    log_text = Path(session.log_path).read_text(encoding="utf-8")
            finally:
                if old_data_dir is None:
                    os.environ.pop("REDNOTE_DATA_DIR", None)
                else:
                    os.environ["REDNOTE_DATA_DIR"] = old_data_dir

        self.assertEqual(session.status, "started")
        self.assertIn("starting", log_text)
        popen.assert_called_once()
        args, kwargs = popen.call_args
        self.assertEqual(args[0][2], "rednote_matrix.integrations.xhs_login_worker")
        self.assertEqual(args[0][-3:], ["false", "33", "true"])
        self.assertTrue(kwargs["start_new_session"])

    def test_qrcode_image_endpoint_returns_404_before_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            old_data_dir = os.environ.get("REDNOTE_DATA_DIR")
            os.environ["REDNOTE_DATA_DIR"] = tmpdir
            try:
                client = TestClient(app)
                response = client.get("/integrations/xhs/login/missing-session/qrcode")
            finally:
                if old_data_dir is None:
                    os.environ.pop("REDNOTE_DATA_DIR", None)
                else:
                    os.environ["REDNOTE_DATA_DIR"] = old_data_dir

        self.assertEqual(response.status_code, 404)

    def test_persistent_browser_uses_detached_worker_process(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            old_data_dir = os.environ.get("REDNOTE_DATA_DIR")
            os.environ["REDNOTE_DATA_DIR"] = tmpdir
            try:
                with (
                    patch(
                        "rednote_matrix.integrations.xhs_core.check_xhs_environment",
                        return_value=XhsCoreEnvironment(True, True, True, True, [], []),
                    ),
                    patch("rednote_matrix.integrations.xhs_core.shutil.which", return_value="/usr/bin/Xvfb"),
                    patch("rednote_matrix.integrations.xhs_core.subprocess.Popen") as popen,
                ):
                    popen.return_value.pid = 12345
                    status = start_persistent_browser(timeout_seconds=3600)
                    log_text = Path(status.log_path).read_text(encoding="utf-8")
            finally:
                if old_data_dir is None:
                    os.environ.pop("REDNOTE_DATA_DIR", None)
                else:
                    os.environ["REDNOTE_DATA_DIR"] = old_data_dir

        self.assertEqual(status.status, "stopped")
        self.assertEqual(status.pid, 12345)
        self.assertIn("starting", log_text)
        popen.assert_called_once()
        args, kwargs = popen.call_args
        self.assertEqual(args[0][2], "rednote_matrix.integrations.xhs_persistent_browser_worker")
        self.assertEqual(args[0][-1], "3600")
        self.assertTrue(kwargs["start_new_session"])

    def test_xhs_search_reports_verification_required(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            old_data_dir = os.environ.get("REDNOTE_DATA_DIR")
            os.environ["REDNOTE_DATA_DIR"] = tmpdir
            cookie_path = Path(tmpdir) / "xhs_core" / "xhs_cookie.json"
            cookie_path.parent.mkdir(parents=True, exist_ok=True)
            cookie_path.write_text('{"cookie": "web_session=test-session"}', encoding="utf-8")
            response = Mock()
            response.status_code = 461
            response.headers = {"Verifytype": "216", "Verifyuuid": "verify-uuid"}
            response.json.return_value = {"code": 0, "success": True, "data": {}}
            response.text = '{"code":0,"success":true,"data":{}}'
            try:
                with (
                    patch(
                        "rednote_matrix.integrations.xhs_core.check_xhs_environment",
                        return_value=XhsCoreEnvironment(True, True, True, True, [], []),
                    ),
                    patch("rednote_matrix.integrations.xhs_core._signed_headers", return_value={}),
                    patch("rednote_matrix.integrations.xhs_core.httpx.AsyncClient") as client_class,
                ):
                    client = client_class.return_value.__aenter__.return_value
                    client.post.return_value = response
                    result = search_xhs_keywords(
                        ["小红书运营太难了"],
                        max_notes_count=2,
                        browser_fallback=False,
                    )
            finally:
                if old_data_dir is None:
                    os.environ.pop("REDNOTE_DATA_DIR", None)
                else:
                    os.environ["REDNOTE_DATA_DIR"] = old_data_dir

        self.assertEqual(result.status, "verification_required")
        self.assertEqual(result.return_code, 461)
        self.assertIn("Verifytype=216", result.message)


if __name__ == "__main__":
    unittest.main()
