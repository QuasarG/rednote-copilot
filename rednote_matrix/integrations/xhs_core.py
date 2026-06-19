from __future__ import annotations

import asyncio
import base64
import json
import os
import platform
import random
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, is_dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from rednote_matrix.core.models import AgentInput, MarketNote
from rednote_matrix.memory.store import default_db_path


XHS_HOST = "https://edith.xiaohongshu.com"
XHS_DOMAIN = "https://www.xiaohongshu.com"
DEFAULT_SEARCH_TIMEOUT_SECONDS = 60
DEFAULT_PAGE_SIZE = 20
VERIFY_STATUS_CODES = {461, 471}
VIRAL_LIKE_FLOOR = 1000
CDP_DEBUG_PORT = 9222
BROWSER_LAUNCH_TIMEOUT_SECONDS = 35


@dataclass(frozen=True)
class XhsCoreEnvironment:
    configured: bool
    playwright_ok: bool
    xhshow_ok: bool
    errors: list[str]
    messages: list[str]


@dataclass(frozen=True)
class XhsAuthStatus:
    available: bool
    cookie_path: str
    has_web_session: bool
    message: str = ""
    verified: bool = False
    browser_synced: bool = False


@dataclass(frozen=True)
class XhsLoginSession:
    session_id: str
    status: str
    qrcode_path: str = ""
    cookie_path: str = ""
    log_path: str = ""
    message: str = ""
    display_mode: str = ""


@dataclass(frozen=True)
class XhsPersistentBrowserStatus:
    status: str
    session_id: str = "persistent"
    qrcode_path: str = ""
    qrcode_url: str = ""
    cookie_path: str = ""
    log_path: str = ""
    pid: int | None = None
    message: str = ""
    display_mode: str = "headed"


@dataclass(frozen=True)
class XhsSearchResult:
    status: str
    output_dir: str
    sanitized_request: dict[str, Any]
    notes: list[dict[str, Any]]
    return_code: int | None = None
    message: str = ""
    login_session_id: str = ""
    qrcode_path: str = ""
    qrcode_url: str = ""


class XhsVerificationRequired(RuntimeError):
    def __init__(self, status_code: int, verify_type: str = "", verify_uuid: str = "") -> None:
        self.status_code = status_code
        self.verify_type = verify_type
        self.verify_uuid = verify_uuid
        message = f"小红书触发安全验证 HTTP {status_code}"
        if verify_type or verify_uuid:
            message = f"{message}，Verifytype={verify_type or '-'}，Verifyuuid={verify_uuid or '-'}"
        super().__init__(message)


def xhs_data_dir() -> Path:
    root = default_db_path().parent / "xhs_core"
    root.mkdir(parents=True, exist_ok=True)
    return root


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def cookie_path() -> Path:
    return xhs_data_dir() / "xhs_cookie.json"


def persistent_browser_dir() -> Path:
    path = xhs_data_dir() / "persistent_browser"
    path.mkdir(parents=True, exist_ok=True)
    return path


def browser_profile_dir() -> Path:
    path = xhs_data_dir() / "browser_profile"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _cdp_status_path() -> Path:
    return persistent_browser_dir() / "cdp_status.json"


def check_xhs_environment(deep: bool = False) -> XhsCoreEnvironment:
    errors: list[str] = []
    messages: list[str] = []
    playwright_ok = False
    xhshow_ok = False

    try:
        import xhshow  # noqa: F401

        xhshow_ok = True
        messages.append("xhshow 签名依赖可用")
    except Exception as exc:
        errors.append(f"缺少 xhshow 签名依赖: {exc}")

    try:
        import playwright  # noqa: F401

        playwright_ok = True
        messages.append("playwright 依赖可用")
    except Exception as exc:
        errors.append(f"缺少 playwright 登录依赖: {exc}")

    if deep and playwright_ok:
        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                browser.close()
            messages.append("playwright chromium 可启动")
        except Exception as exc:
            errors.append(f"playwright chromium 启动失败: {exc}")
            playwright_ok = False

    browser_path = _find_browser_path()
    if browser_path:
        messages.append(f"系统浏览器可用: {browser_path}")
    else:
        errors.append("未找到可用的 Chrome/Chromium/Edge 浏览器")

    messages.append("浏览器以有头模式运行，Chrome 窗口会弹出")

    return XhsCoreEnvironment(
        configured=xhshow_ok and playwright_ok and bool(browser_path),
        playwright_ok=playwright_ok,
        xhshow_ok=xhshow_ok,
        errors=errors,
        messages=messages,
    )


def check_xhs_auth(sync_browser: bool = True) -> XhsAuthStatus:
    path = cookie_path()
    if not path.exists():
        if sync_browser:
            synced = sync_cookie_from_active_browser(verify=False)
            if synced:
                return synced
        return XhsAuthStatus(False, str(path), False, "未找到本地小红书 cookie")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return XhsAuthStatus(False, str(path), False, "cookie 文件不是合法 JSON")
    cookie_text = payload.get("cookie", "")
    has_web_session = "web_session=" in cookie_text
    if not has_web_session:
        return XhsAuthStatus(False, str(path), False, "cookie 缺少 web_session")
    ok, message = _verify_cookie_sync(cookie_text)
    if not ok and sync_browser:
        synced = sync_cookie_from_active_browser(verify=False)
        if synced:
            return synced
    return XhsAuthStatus(ok, str(path), True, message, ok)


def save_cookie(cookie: str) -> XhsAuthStatus:
    path = cookie_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"cookie": cookie, "saved_at": int(time.time())}, ensure_ascii=False, indent=2), encoding="utf-8")
    has_web_session = "web_session=" in cookie
    return XhsAuthStatus(has_web_session, str(path), has_web_session, "cookie 已保存，待验证", False)


def sync_cookie_from_active_browser(verify: bool = False) -> XhsAuthStatus | None:
    try:
        return asyncio.run(_sync_cookie_from_active_browser(verify=verify))
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_sync_cookie_from_active_browser(verify=verify))
        finally:
            loop.close()
    except Exception:
        return None


async def _sync_cookie_from_active_browser(verify: bool = False) -> XhsAuthStatus | None:
    cdp_status = _read_json_file(_cdp_status_path())
    pid = cdp_status.get("pid")
    if not _process_alive(int(pid) if isinstance(pid, int) else None):
        return None
    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as playwright:
            context, _browser, _cdp = await _connect_cdp_context(playwright, headless=False)
            cookie_text = _cookie_string(await context.cookies(urls=[XHS_DOMAIN]))
    except Exception:
        return None
    if "web_session=" not in cookie_text:
        return None
    saved = save_cookie(cookie_text)
    if not verify:
        return XhsAuthStatus(True, saved.cookie_path, True, "已从 Chrome 同步登录态", False, True)
    ok, message = _verify_cookie_sync(cookie_text)
    return XhsAuthStatus(ok, saved.cookie_path, True, message, ok, True)


def current_cookie() -> str:
    path = cookie_path()
    if not path.exists():
        return ""
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("cookie", "")
    except json.JSONDecodeError:
        return ""


def _verify_cookie_sync(cookie: str) -> tuple[bool, str]:
    try:
        return asyncio.run(_verify_cookie(cookie))
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_verify_cookie(cookie))
        finally:
            loop.close()
    except Exception as exc:
        return False, f"登录态验证失败: {exc}"


async def _verify_cookie(cookie: str) -> tuple[bool, str]:
    uri = "/api/sns/web/v1/user/selfinfo"
    headers = {**_base_headers(cookie), **_signed_headers(uri, {}, cookie, "GET")}
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        response = await client.get(f"{XHS_HOST}{uri}", headers=headers)
    if response.status_code in VERIFY_STATUS_CODES:
        verify_type = response.headers.get("Verifytype", "")
        verify_uuid = response.headers.get("Verifyuuid", "")
        return False, f"登录态触发安全验证 Verifytype={verify_type or '-'}，Verifyuuid={verify_uuid or '-'}"
    try:
        payload = response.json()
    except json.JSONDecodeError:
        return False, f"登录态验证返回非 JSON: HTTP {response.status_code}"
    if payload.get("data", {}).get("result", {}).get("success"):
        return True, "登录态有效"
    return False, str(payload.get("msg") or "登录已过期")


def write_qrcode_image(base64_qrcode: str, session_dir: Path) -> str:
    session_dir.mkdir(parents=True, exist_ok=True)
    if "," in base64_qrcode:
        base64_qrcode = base64_qrcode.split(",", 1)[1]
    image_bytes = base64.b64decode(base64_qrcode)
    qrcode_path = session_dir / "qrcode.png"
    qrcode_path.write_bytes(image_bytes)
    return str(qrcode_path)


def _append_session_log(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        file = path.open("a", encoding="utf-8")
    except PermissionError:
        file = path.with_name(f"{path.stem}.local{path.suffix}").open("a", encoding="utf-8")
    with file:
        file.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _read_json_file(path: Path) -> dict[str, Any]:
    fallback = path.with_name(f"{path.stem}.local{path.suffix}")
    source = fallback if fallback.exists() else path
    if not source.exists():
        return {}
    try:
        return json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _write_json_file(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    try:
        path.write_text(text, encoding="utf-8")
    except PermissionError:
        fallback = path.with_name(f"{path.stem}.local{path.suffix}")
        fallback.write_text(text, encoding="utf-8")


def _process_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _find_browser_path() -> str:
    configured = [
        os.environ.get("XHS_BROWSER_PATH", ""),
        os.environ.get("CHROME_PATH", ""),
        os.environ.get("CUSTOM_BROWSER_PATH", ""),
    ]
    for path in configured:
        if path and Path(path).is_file():
            return path

    system = platform.system()
    if system == "Windows":
        candidates = [
            os.path.expandvars(r"%PROGRAMFILES%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%PROGRAMFILES(X86)%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%PROGRAMFILES%\Microsoft\Edge\Application\msedge.exe"),
            os.path.expandvars(r"%PROGRAMFILES(X86)%\Microsoft\Edge\Application\msedge.exe"),
        ]
    elif system == "Darwin":
        candidates = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Google Chrome Beta.app/Contents/MacOS/Google Chrome Beta",
            "/Applications/Google Chrome Dev.app/Contents/MacOS/Google Chrome Dev",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        ]
    else:
        candidates = [
            str(Path.home() / ".local/bin/google-chrome"),
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/usr/bin/chromium-browser",
            "/usr/bin/chromium",
            "/snap/bin/chromium",
            "/usr/bin/microsoft-edge",
            "/usr/bin/microsoft-edge-stable",
        ]

    commands = [
        "google-chrome",
        "google-chrome-stable",
        "chromium-browser",
        "chromium",
        "microsoft-edge",
        "msedge",
    ]
    candidates.extend(str(Path(found)) for command in commands if (found := shutil.which(command)))
    for path in dict.fromkeys(candidates):
        if path and Path(path).is_file():
            return path
    return ""


def _find_available_port(start_port: int = CDP_DEBUG_PORT) -> int:
    for port in range(start_port, start_port + 100):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError(f"未找到可用 CDP 端口: {start_port}-{start_port + 99}")


async def _cdp_websocket_url(port: int, timeout_seconds: int = 10) -> str:
    deadline = time.time() + timeout_seconds
    last_error = ""
    while time.time() < deadline:
        try:
            async with httpx.AsyncClient(timeout=3) as client:
                response = await client.get(f"http://127.0.0.1:{port}/json/version")
            if response.status_code == 200:
                ws_url = response.json().get("webSocketDebuggerUrl", "")
                if ws_url:
                    return ws_url
        except Exception as exc:
            last_error = str(exc)
        await asyncio.sleep(0.5)
    raise RuntimeError(f"Chrome CDP 端口未就绪: {last_error or port}")


def _terminate_process_tree(pid: int | None) -> None:
    if not _process_alive(pid):
        return
    if platform.system() == "Windows":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True, check=False)
        return
    try:
        os.killpg(os.getpgid(int(pid)), signal.SIGTERM)
    except ProcessLookupError:
        return
    except Exception:
        os.kill(int(pid), signal.SIGTERM)


async def _ensure_cdp_browser(headless: bool = False, force_restart: bool = False) -> dict[str, Any]:
    status_path = _cdp_status_path()
    current = _read_json_file(status_path)
    pid = current.get("pid")
    port = int(current.get("port") or 0)
    if force_restart:
        _terminate_process_tree(int(pid) if isinstance(pid, int) else None)
    elif _process_alive(pid) and port:
        try:
            ws_url = await _cdp_websocket_url(port, timeout_seconds=3)
            return {"pid": int(pid), "port": port, "ws_url": ws_url, "browser_path": current.get("browser_path", "")}
        except Exception:
            pass

    browser_path = _find_browser_path()
    if not browser_path:
        raise RuntimeError("未找到可用的 Chrome/Chromium/Edge 浏览器")

    port = _find_available_port()
    user_data_dir = browser_profile_dir()
    cdp_log = persistent_browser_dir() / "chrome_cdp.log"
    args = [
        browser_path,
        f"--remote-debugging-port={port}",
        "--remote-debugging-address=127.0.0.1",
        "--remote-allow-origins=*",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-background-timer-throttling",
        "--disable-backgrounding-occluded-windows",
        "--disable-renderer-backgrounding",
        "--disable-features=TranslateUI",
        "--disable-ipc-flooding-protection",
        "--disable-hang-monitor",
        "--disable-prompt-on-repost",
        "--disable-sync",
        "--disable-dev-shm-usage",
        "--disable-infobars",
        "--start-maximized",
        f"--user-data-dir={user_data_dir}",
        XHS_DOMAIN,
    ]
    if headless:
        args.remove("--start-maximized")
        args.extend(["--headless=new", "--disable-gpu"])

    if platform.system() == "Windows":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP
        process = subprocess.Popen(args, stdout=cdp_log.open("a", encoding="utf-8"), stderr=subprocess.STDOUT, creationflags=creationflags)
    else:
        process = subprocess.Popen(args, stdout=cdp_log.open("a", encoding="utf-8"), stderr=subprocess.STDOUT, start_new_session=True)

    ws_url = await _cdp_websocket_url(port, timeout_seconds=BROWSER_LAUNCH_TIMEOUT_SECONDS)
    payload = {
        "pid": process.pid,
        "port": port,
        "browser_path": browser_path,
        "user_data_dir": str(user_data_dir),
        "log_path": str(cdp_log),
        "headless": headless,
        "updated_at": int(time.time()),
    }
    _write_json_file(status_path, payload)
    return {**payload, "ws_url": ws_url}


async def _connect_cdp_context(playwright: Any, headless: bool = False, force_restart: bool = False) -> tuple[Any, Any, dict[str, Any]]:
    cdp = await _ensure_cdp_browser(headless=headless, force_restart=force_restart)
    browser = await playwright.chromium.connect_over_cdp(cdp["ws_url"], timeout=BROWSER_LAUNCH_TIMEOUT_SECONDS * 1000)
    context = browser.contexts[0] if browser.contexts else await browser.new_context(
        viewport={"width": 1280, "height": 900},
        user_agent=_user_agent(),
        accept_downloads=True,
    )
    return context, browser, cdp


def _persistent_paths() -> dict[str, Path]:
    base = persistent_browser_dir()
    return {
        "base": base,
        "status": base / "status.json",
        "log": base / "browser.log",
        "worker_log": base / "worker.log",
        "qrcode": base / "qrcode.png",
        "user_data": browser_profile_dir(),
    }


def start_persistent_browser(timeout_seconds: int = 0, force_restart: bool = False) -> XhsPersistentBrowserStatus:
    env = check_xhs_environment(deep=False)
    paths = _persistent_paths()
    if not env.configured:
        return XhsPersistentBrowserStatus("error", message="；".join(env.errors) or "小红书核心环境未配置")

    current = _read_json_file(paths["status"])
    pid = current.get("pid")
    if not force_restart and _process_alive(pid):
        return persistent_browser_status()

    if force_restart and _process_alive(pid):
        stop_persistent_browser()

    paths["base"].mkdir(parents=True, exist_ok=True)
    paths["user_data"].mkdir(parents=True, exist_ok=True)
    status = {
        "status": "starting",
        "session_id": "persistent",
        "qrcode_path": str(paths["qrcode"]),
        "cookie_path": str(cookie_path()),
        "log_path": str(paths["log"]),
        "message": "常驻浏览器后台任务已启动",
        "display_mode": "headed",
        "updated_at": int(time.time()),
    }
    _write_json_file(paths["status"], status)
    _append_session_log(paths["log"], {"status": "starting", "message": "常驻浏览器后台任务已启动", "display_mode": "headed"})
    cmd = [
        sys.executable,
        "-m",
        "rednote_matrix.integrations.xhs_persistent_browser_worker",
        str(max(0, int(timeout_seconds))),
    ]
    with paths["worker_log"].open("w", encoding="utf-8") as worker_log:
        process = subprocess.Popen(
            cmd,
            cwd=str(project_root()),
            stdout=worker_log,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
    status["pid"] = process.pid
    _write_json_file(paths["status"], status)
    return persistent_browser_status()


def persistent_browser_status() -> XhsPersistentBrowserStatus:
    paths = _persistent_paths()
    status = _read_json_file(paths["status"])
    cdp_status = _read_json_file(_cdp_status_path())
    pid = status.get("pid")
    cdp_pid = cdp_status.get("pid")
    alive = _process_alive(pid) or _process_alive(cdp_pid)
    auth = check_xhs_auth()
    raw_status = str(status.get("status") or "stopped")
    if raw_status == "stopped" and not _process_alive(cdp_pid):
        alive = False
    if raw_status not in {"stopped", "error", "blocked", "timeout"}:
        raw_status = raw_status if alive else "stopped"
    elif raw_status == "stopped" and alive:
        raw_status = "browser_ready"
    if auth.available and alive:
        raw_status = "logged_in"
        message = "常驻浏览器运行中，已检测到登录态"
    else:
        message = str(status.get("message") or ("常驻浏览器运行中" if alive else "常驻浏览器未运行"))
    return XhsPersistentBrowserStatus(
        status=raw_status,
        qrcode_path=str(status.get("qrcode_path") or paths["qrcode"]),
        qrcode_url="/integrations/xhs/browser/qrcode",
        cookie_path=auth.cookie_path,
        log_path=str(status.get("log_path") or paths["log"]),
        pid=int(cdp_pid) if isinstance(cdp_pid, int) else (int(pid) if isinstance(pid, int) else None),
        message=message,
        display_mode=str(status.get("display_mode") or "headed"),
    )


def stop_persistent_browser() -> XhsPersistentBrowserStatus:
    paths = _persistent_paths()
    status = _read_json_file(paths["status"])
    pid = status.get("pid")
    if _process_alive(pid):
        os.kill(int(pid), 15)
        for _ in range(20):
            if not _process_alive(pid):
                break
            time.sleep(0.1)
    cdp_status = _read_json_file(_cdp_status_path())
    cdp_pid = cdp_status.get("pid")
    if isinstance(cdp_pid, int):
        _terminate_process_tree(cdp_pid)
        cdp_status.update({"pid": None, "status": "stopped", "updated_at": int(time.time())})
        _write_json_file(_cdp_status_path(), cdp_status)
    status.update({"status": "stopped", "pid": None, "message": "常驻浏览器已停止", "updated_at": int(time.time())})
    _write_json_file(paths["status"], status)
    _append_session_log(paths["log"], {"status": "stopped", "message": "常驻浏览器已停止"})
    return persistent_browser_status()


def start_qrcode_login_process(
    headless: bool = False,
    timeout_seconds: int = 180,
) -> XhsLoginSession:
    env = check_xhs_environment(deep=False)
    display_mode = "headed"
    if not env.configured:
        return XhsLoginSession("", "error", message="；".join(env.errors) or "小红书核心环境未配置", display_mode=display_mode)

    session_id = f"{int(time.time())}-{uuid.uuid4().hex[:8]}"
    session_dir = xhs_data_dir() / "sessions" / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    log_path = session_dir / "login.log"
    qrcode_path = session_dir / "qrcode.png"
    worker_log_path = session_dir / "worker.log"
    _append_session_log(log_path, {"status": "starting", "message": "二维码登录后台任务已启动", "display_mode": display_mode})

    cmd = [
        sys.executable,
        "-m",
        "rednote_matrix.integrations.xhs_login_worker",
        session_id,
        "false",
        str(timeout_seconds),
        "false",
    ]
    with worker_log_path.open("w", encoding="utf-8") as worker_log:
        subprocess.Popen(
            cmd,
            cwd=str(project_root()),
            stdout=worker_log,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
    return XhsLoginSession(
        session_id=session_id,
        status="started",
        qrcode_path=str(qrcode_path),
        cookie_path=str(cookie_path()),
        log_path=str(log_path),
        message="二维码登录后台任务已启动",
        display_mode=display_mode,
    )


def run_login_worker(session_id: str, headless: bool, timeout_seconds: int, use_virtual_display: bool = False) -> None:
    asyncio.run(_run_login_worker(session_id, timeout_seconds))


def run_persistent_browser_worker(timeout_seconds: int = 0) -> None:
    asyncio.run(_run_persistent_browser_worker(timeout_seconds))


async def _run_persistent_browser_worker(timeout_seconds: int) -> None:
    paths = _persistent_paths()
    log_path = paths["log"]
    status_path = paths["status"]

    def write_status(payload: dict[str, Any]) -> None:
        current = _read_json_file(status_path)
        current.update(
            {
                "session_id": "persistent",
                "qrcode_path": str(paths["qrcode"]),
                "cookie_path": str(cookie_path()),
                "log_path": str(log_path),
                "display_mode": "headed",
                "updated_at": int(time.time()),
                **payload,
            }
        )
        _write_json_file(status_path, current)
        _append_session_log(log_path, payload)

    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as playwright:
            context, browser, cdp = await _connect_cdp_context(playwright, headless=False)
            write_status({"status": "browser_ready", "pid": cdp.get("pid"), "message": "CDP Chrome 已启动，等待登录"})
            page = context.pages[0] if context.pages else await context.new_page()
            await page.goto(XHS_DOMAIN, wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)
            security_message = await _security_limit_message(page)
            if security_message:
                write_status({"status": "blocked", "message": security_message})
                return

            login_ready = False
            cookie_str = _cookie_string(await context.cookies(urls=[XHS_DOMAIN]))
            if "web_session=" in cookie_str:
                ok, message = await _verify_cookie(cookie_str)
                if ok:
                    save_cookie(cookie_str)
                    login_ready = True
                    write_status({"status": "logged_in", "message": "常驻浏览器已复用现有登录态"})
                else:
                    await _clear_xhs_cookies(context)
                    write_status({"status": "login_expired", "message": f"旧登录态无效：{message}，等待重新扫码"})

            if not login_ready:
                base64_qrcode = await _find_login_qrcode(page)
                if not base64_qrcode:
                    clicked = await _click_login_entry(page)
                    if clicked:
                        base64_qrcode = await _find_login_qrcode(page)
                if not base64_qrcode:
                    raise RuntimeError("未找到小红书登录二维码")
                written_path = write_qrcode_image(base64_qrcode, paths["base"])
                if Path(written_path) != paths["qrcode"]:
                    Path(written_path).replace(paths["qrcode"])
                write_status({"status": "qrcode_ready", "message": "二维码已生成，等待扫码"})

            deadline = time.time() + timeout_seconds if timeout_seconds > 0 else None
            while deadline is None or time.time() < deadline:
                cookie_str = _cookie_string(await context.cookies(urls=[XHS_DOMAIN]))
                if "web_session=" in cookie_str:
                    ok, message = await _verify_cookie(cookie_str)
                    if ok:
                        save_cookie(cookie_str)
                        write_status({"status": "logged_in", "message": "常驻浏览器运行中，已同步登录态"})
                    else:
                        write_status({"status": "waiting_login", "message": f"检测到 cookie 但未验证通过：{message}"})
                await asyncio.sleep(10)

            write_status({"status": "timeout", "message": "常驻浏览器达到设定运行时长"})
    except Exception as exc:
        write_status({"status": "error", "message": str(exc)})


async def _run_login_worker(session_id: str, timeout_seconds: int) -> None:
    session_dir = xhs_data_dir() / "sessions" / session_id
    log_path = session_dir / "login.log"
    qrcode_path = session_dir / "qrcode.png"

    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as playwright:
            context, _browser, cdp = await _connect_cdp_context(playwright, headless=False)
            _append_session_log(
                log_path,
                {
                    "status": "browser_ready",
                    "message": "CDP Chrome 已启动，等待二维码登录",
                    "pid": cdp.get("pid"),
                    "port": cdp.get("port"),
                    "display_mode": "headed",
                },
            )
            page = context.pages[0] if context.pages else await context.new_page()
            await page.goto(XHS_DOMAIN, wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)
            security_message = await _security_limit_message(page)
            if security_message:
                _append_session_log(log_path, {"status": "blocked", "message": security_message})
                return

            cookie_str = _cookie_string(await context.cookies(urls=[XHS_DOMAIN]))
            if "web_session=" in cookie_str:
                ok, message = await _verify_cookie(cookie_str)
                if ok:
                    save_cookie(cookie_str)
                    _append_session_log(log_path, {"status": "logged_in", "cookie_path": str(cookie_path()), "display_mode": "headed"})
                    return
                await _clear_xhs_cookies(context)
                _append_session_log(log_path, {"status": "login_expired", "message": f"旧登录态无效：{message}，等待重新扫码", "display_mode": "headed"})
                await page.goto(XHS_DOMAIN, wait_until="domcontentloaded")
                await page.wait_for_timeout(1500)

            base64_qrcode = await _find_login_qrcode(page)
            if not base64_qrcode:
                clicked = await _click_login_entry(page)
                if not clicked:
                    security_message = await _security_limit_message(page)
                    if security_message:
                        _append_session_log(log_path, {"status": "blocked", "message": security_message})
                        return
                    raise RuntimeError("未找到小红书登录入口")
                base64_qrcode = await _find_login_qrcode(page)
            if not base64_qrcode:
                raise RuntimeError("未找到小红书登录二维码")

            written_path = write_qrcode_image(base64_qrcode, session_dir)
            _append_session_log(log_path, {"status": "qrcode_ready", "qrcode_path": written_path, "display_mode": "headed"})
            deadline = time.time() + timeout_seconds
            logged_in = False
            cookie_str = ""
            while time.time() < deadline:
                cookie_str = _cookie_string(await context.cookies(urls=[XHS_DOMAIN]))
                if "web_session=" in cookie_str:
                    page_ready = not await _page_requires_login(page)
                    ok, message = await _verify_cookie(cookie_str)
                    if ok or page_ready:
                        logged_in = True
                        if not ok:
                            _append_session_log(
                                log_path,
                                {
                                    "status": "browser_cookie_ready",
                                    "message": f"Chrome 已出现登录态，接口验证暂未通过：{message}",
                                    "display_mode": "headed",
                                },
                            )
                        break
                await asyncio.sleep(1)

            if not logged_in:
                _append_session_log(log_path, {"status": "timeout", "qrcode_path": str(qrcode_path), "display_mode": "headed"})
                return

            (session_dir / "cookie.json").write_text(json.dumps({"cookie": cookie_str}, ensure_ascii=False, indent=2), encoding="utf-8")
            save_cookie(cookie_str)
            _append_session_log(log_path, {"status": "logged_in", "cookie_path": str(cookie_path()), "display_mode": "headed"})
    except Exception as exc:
        _append_session_log(log_path, {"status": "error", "message": str(exc)})


def login_session_status(session_id: str) -> XhsLoginSession:
    session_dir = xhs_data_dir() / "sessions" / session_id
    qrcode_path = session_dir / "qrcode.png"
    log_path = session_dir / "login.log"
    auth = check_xhs_auth()
    if auth.available or auth.browser_synced:
        return XhsLoginSession(session_id, "logged_in", str(qrcode_path), auth.cookie_path, str(log_path), "已检测到登录态")
    if not session_dir.exists():
        return XhsLoginSession(session_id, "missing", message="找不到登录会话")
    tail = _tail_json(log_path)
    status = tail.get("status", "starting")
    message = tail.get("message", "等待二维码生成")
    display_mode = str(tail.get("display_mode") or "")
    if status == "qrcode_ready":
        message = "二维码已生成，等待扫码"
    elif status == "timeout":
        message = "扫码登录超时"
    elif status == "blocked":
        message = str(tail.get("message") or "小红书安全限制，当前网络或浏览器环境被拦截")
    return XhsLoginSession(session_id, status, str(qrcode_path), auth.cookie_path, str(log_path), message, display_mode)


def build_default_keywords(user_input: AgentInput, limit: int = 5) -> list[str]:
    product = user_input.product_name.strip()
    audience = user_input.target_audience.strip()
    scenario = user_input.scenario.strip()
    points = [point.strip() for point in user_input.selling_points if point.strip()]
    candidates = [
        f"{product} 爆款笔记",
        f"{product} 真实体验",
        f"{product} 避坑",
        f"{audience} {product}" if audience else "",
        f"{scenario} {product}" if scenario else "",
    ]
    for point in points[:2]:
        candidates.append(f"{point} {product}")
    keywords = [item for item in dict.fromkeys(candidates) if item.strip()]
    return keywords[:limit]


def search_xhs_keywords(
    keywords: list[str],
    max_notes_count: int = 12,
    headless: bool = True,
    output_dir: str | Path | None = None,
    execute: bool = True,
    timeout_seconds: int = DEFAULT_SEARCH_TIMEOUT_SECONDS,
    browser_fallback: bool = True,
    on_note: Callable[[dict[str, Any]], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> XhsSearchResult:
    env = check_xhs_environment(deep=False)
    if not env.configured:
        return XhsSearchResult("unconfigured", "", {"keywords": keywords}, [], message="；".join(env.errors) or "小红书核心环境未配置")

    clean_keywords = [keyword.strip() for keyword in keywords if keyword.strip()]
    if not clean_keywords:
        return XhsSearchResult("error", "", {"keywords": []}, [], message="缺少搜索关键词")
    safe_count = max(1, min(int(max_notes_count), 30))
    output_path = Path(output_dir) if output_dir else xhs_data_dir() / "search_runs" / str(int(time.time()))
    output_path.mkdir(parents=True, exist_ok=True)
    request_meta = {"keywords": clean_keywords, "max_notes_count": safe_count, "headless": headless, "browser_fallback": browser_fallback}
    if not execute:
        return XhsSearchResult("ready", str(output_path), request_meta, [], message="已准备小红书轻量搜索")

    started = time.time()
    search_mode = "http"
    emitted_notes: list[dict[str, Any]] = []

    def record_note(note: dict[str, Any]) -> None:
        emitted_notes.append(note)
        _emit_note(on_note, note)

    auth = check_xhs_auth()
    if not auth.available:
        if auth.has_web_session and browser_fallback:
            try:
                notes = asyncio.run(_search_keywords_with_browser(clean_keywords, safe_count, timeout_seconds, record_note, should_stop))
                search_mode = "browser"
                notes = _dedupe_notes([*emitted_notes, *notes])
                if notes:
                    notes.sort(key=lambda item: _interaction_score(item), reverse=True)
                    notes = notes[:safe_count]
                    result_file = output_path / "xhs_search_notes.jsonl"
                    result_file.write_text("\n".join(json.dumps(item, ensure_ascii=False) for item in notes), encoding="utf-8")
                    viral_count = sum(1 for item in notes if _is_viral_note(item))
                    message = f"搜索完成，用时 {round(time.time() - started, 1)}s，模式 {search_mode}，读取 {len(notes)} 条笔记，其中高互动候选 {viral_count} 条"
                    return XhsSearchResult("completed", str(output_path), request_meta, notes, return_code=0, message=message)
            except Exception as browser_exc:
                return XhsSearchResult(
                    "verification_required",
                    str(output_path),
                    {**request_meta, "fallback": "browser", "auth_message": auth.message, "fallback_error": str(browser_exc)},
                    [],
                    return_code=1,
                    message=f"Chrome 登录态已同步，但浏览器检索失败: {browser_exc}",
                )
        if not browser_fallback:
            return XhsSearchResult("needs_login", str(output_path), request_meta, [], message=auth.message)
        session = start_qrcode_login_process(timeout_seconds=timeout_seconds)
        return XhsSearchResult(
            "needs_login",
            str(output_path),
            {**request_meta, "auth_message": auth.message},
            [],
            message=f"{auth.message}；已启动 Chrome 登录窗口，请扫码登录后重新执行搜索",
            login_session_id=session.session_id,
            qrcode_path=session.qrcode_path,
            qrcode_url=f"/integrations/xhs/login/{session.session_id}/qrcode" if session.session_id else "",
        )
    try:
        notes = asyncio.run(_search_keywords(clean_keywords, safe_count, timeout_seconds, record_note, should_stop))
    except XhsVerificationRequired as exc:
        if not browser_fallback:
            return XhsSearchResult(
                "verification_required",
                str(output_path),
                {**request_meta, "verify_type": exc.verify_type, "verify_uuid": exc.verify_uuid},
                [],
                return_code=exc.status_code,
                message=str(exc),
            )
        try:
            notes = asyncio.run(_search_keywords_with_browser(clean_keywords, safe_count, timeout_seconds, record_note, should_stop))
            search_mode = "browser"
            notes = _dedupe_notes([*emitted_notes, *notes])
            if not notes:
                return XhsSearchResult(
                    "verification_required",
                    str(output_path),
                    {**request_meta, "verify_type": exc.verify_type, "verify_uuid": exc.verify_uuid, "fallback": "browser"},
                    [],
                    return_code=exc.status_code,
                    message=f"{exc}；浏览器 fallback 已执行但未抓到可用笔记",
                )
        except XhsVerificationRequired as browser_exc:
            return XhsSearchResult(
                "verification_required",
                str(output_path),
                {
                    **request_meta,
                    "verify_type": browser_exc.verify_type or exc.verify_type,
                    "verify_uuid": browser_exc.verify_uuid or exc.verify_uuid,
                    "fallback": "browser",
                },
                [],
                return_code=browser_exc.status_code,
                message=f"{browser_exc}；浏览器 fallback 也被安全验证拦截",
            )
        except Exception as browser_exc:
            return XhsSearchResult(
                "verification_required",
                str(output_path),
                {**request_meta, "verify_type": exc.verify_type, "verify_uuid": exc.verify_uuid, "fallback_error": str(browser_exc)},
                [],
                return_code=exc.status_code,
                message=f"{exc}；浏览器 fallback 未拿到结果: {browser_exc}",
            )
    except Exception as exc:
        if not browser_fallback:
            return XhsSearchResult("error", str(output_path), request_meta, [], return_code=1, message=f"小红书搜索失败: {exc}")
        try:
            notes = asyncio.run(_search_keywords_with_browser(clean_keywords, safe_count, timeout_seconds, record_note, should_stop))
            search_mode = "browser"
            notes = _dedupe_notes([*emitted_notes, *notes])
            if not notes:
                return XhsSearchResult(
                    "needs_login",
                    str(output_path),
                    {**request_meta, "fallback": "browser", "http_error": str(exc)},
                    [],
                    return_code=1,
                    message=f"HTTP 搜索不可用：{exc}；Chrome 已打开，请在窗口内完成登录后重试搜索",
                )
        except Exception as browser_exc:
            return XhsSearchResult(
                "error",
                str(output_path),
                {**request_meta, "fallback_error": str(browser_exc), "http_error": str(exc)},
                [],
                return_code=1,
                message=f"小红书搜索失败: {exc}；浏览器 fallback 失败: {browser_exc}",
            )

    notes = _dedupe_notes([*emitted_notes, *notes])
    notes.sort(key=lambda item: _interaction_score(item), reverse=True)
    notes = notes[:safe_count]
    result_file = output_path / "xhs_search_notes.jsonl"
    result_file.write_text("\n".join(json.dumps(item, ensure_ascii=False) for item in notes), encoding="utf-8")
    viral_count = sum(1 for item in notes if _is_viral_note(item))
    message = f"搜索完成，用时 {round(time.time() - started, 1)}s，模式 {search_mode}，读取 {len(notes)} 条笔记，其中高互动候选 {viral_count} 条"
    return XhsSearchResult("completed", str(output_path), request_meta, notes, return_code=0, message=message)


async def _search_keywords(
    keywords: list[str],
    limit: int,
    timeout_seconds: int,
    on_note: Callable[[dict[str, Any]], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> list[dict[str, Any]]:
    cookie = current_cookie()
    headers = _base_headers(cookie)
    notes: list[dict[str, Any]] = []
    seen: set[str] = set()
    per_keyword = max(DEFAULT_PAGE_SIZE, min(limit, DEFAULT_PAGE_SIZE))
    async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=True) as client:
        for keyword in keywords:
            if _should_stop(should_stop):
                return notes
            payload = {
                "keyword": keyword,
                "page": 1,
                "page_size": per_keyword,
                "search_id": _get_search_id(),
                "sort": "popularity_descending",
                "note_type": 0,
            }
            signed_headers = _signed_headers("/api/sns/web/v1/search/notes", payload, cookie, "POST")
            response = await client.post(
                f"{XHS_HOST}/api/sns/web/v1/search/notes",
                content=json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                headers={**headers, **signed_headers},
            )
            if response.status_code in VERIFY_STATUS_CODES:
                raise XhsVerificationRequired(
                    response.status_code,
                    response.headers.get("Verifytype", ""),
                    response.headers.get("Verifyuuid", ""),
                )
            data = response.json()
            if not data.get("success"):
                raise RuntimeError(data.get("msg") or response.text[:200])
            if not data.get("data") and response.headers.get("Verifytype"):
                raise XhsVerificationRequired(
                    response.status_code,
                    response.headers.get("Verifytype", ""),
                    response.headers.get("Verifyuuid", ""),
                )
            for item in data.get("data", {}).get("items", []):
                if item.get("model_type") in {"rec_query", "hot_query"}:
                    continue
                note = _note_from_search_item(item, keyword)
                note_id = note.get("note_id") or note.get("note_url")
                if not note_id or note_id in seen:
                    continue
                seen.add(note_id)
                notes.append(note)
                _emit_note(on_note, note)
                if len(notes) >= limit:
                    return notes
                if _should_stop(should_stop):
                    return notes
            await asyncio.sleep(1.2 + random.random() * 1.5)
    return notes


_browser_context = None
_browser_playwright = None


def _get_shared_browser():
    """获取共享浏览器实例，首次调用时创建，之后复用且不关闭。"""
    return _browser_context, _browser_playwright


def _set_shared_browser(context, playwright):
    global _browser_context, _browser_playwright
    _browser_context = context
    _browser_playwright = playwright


async def _search_keywords_with_browser(
    keywords: list[str],
    limit: int,
    timeout_seconds: int,
    on_note: Callable[[dict[str, Any]], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> list[dict[str, Any]]:
    from playwright.async_api import async_playwright

    notes: list[dict[str, Any]] = []
    seen: set[str] = set()
    context = _browser_context
    playwright_mgr = _browser_playwright
    if context is None:
        playwright_mgr = await async_playwright().start()
        context, _browser, _cdp = await _connect_cdp_context(playwright_mgr, headless=False)
        _set_shared_browser(context, playwright_mgr)

    cookie_items = _playwright_cookies_from_cookie_string(current_cookie())
    if cookie_items:
        await context.add_cookies(cookie_items)
    try:
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(XHS_DOMAIN, wait_until="domcontentloaded", timeout=timeout_seconds * 1000)
        await page.wait_for_timeout(2500)
        security_message = await _security_limit_message(page)
        if security_message:
            raise XhsVerificationRequired(461, verify_type="browser", verify_uuid="")
        cookie_str = _cookie_string(await context.cookies(urls=[XHS_DOMAIN]))
        if "web_session=" in cookie_str:
            ok, _ = await _verify_cookie(cookie_str)
            if ok or not await _page_requires_login(page):
                save_cookie(cookie_str)

        for keyword in keywords:
            if _should_stop(should_stop):
                return notes
            captured: list[dict[str, Any]] = []
            response_tasks: list[asyncio.Task] = []
            verification: XhsVerificationRequired | None = None

            async def capture_response(response: Any) -> None:
                nonlocal verification
                url = response.url
                if "/api/sns/web/v1/search/notes" not in url:
                    return
                if response.status in VERIFY_STATUS_CODES:
                    verification = XhsVerificationRequired(
                        response.status,
                        response.headers.get("Verifytype", ""),
                        response.headers.get("Verifyuuid", ""),
                    )
                    return
                try:
                    payload = await response.json()
                except Exception:
                    return
                for item in payload.get("data", {}).get("items", []):
                    note = _note_from_search_item(item, keyword)
                    if note.get("note_id") or note.get("note_url") or note.get("title"):
                        captured.append(note)

            def schedule_capture(response: Any) -> None:
                response_tasks.append(asyncio.create_task(capture_response(response)))

            page.on("response", schedule_capture)
            search_url = f"{XHS_DOMAIN}/search_result?keyword={quote(keyword)}&source=web_search_result_notes"
            try:
                await page.goto(search_url, wait_until="domcontentloaded", timeout=timeout_seconds * 1000)
                await page.wait_for_timeout(3500 + int(random.random() * 1500))
                if await _page_requires_login(page):
                    await _wait_for_browser_login(page, context, timeout_seconds)
                    await page.goto(search_url, wait_until="domcontentloaded", timeout=timeout_seconds * 1000)
                    await page.wait_for_timeout(3500 + int(random.random() * 1500))
                for _ in range(3):
                    await page.mouse.wheel(0, 700)
                    await page.wait_for_timeout(1000 + int(random.random() * 800))
                if response_tasks:
                    await asyncio.gather(*response_tasks, return_exceptions=True)
                if verification:
                    raise verification
                security_message = await _security_limit_message(page)
                if security_message:
                    raise XhsVerificationRequired(461, verify_type="browser", verify_uuid="")

                page_notes = [*captured, *await _extract_notes_from_search_page(page, keyword)]
                for note in page_notes:
                    note_id = note.get("note_id") or note.get("note_url") or note.get("title")
                    if not note_id or note_id in seen:
                        continue
                    seen.add(note_id)
                    notes.append(note)
                    _emit_note(on_note, note)
                    if len(notes) >= limit:
                        return notes
                    if _should_stop(should_stop):
                        return notes
            finally:
                page.remove_listener("response", schedule_capture)
            await asyncio.sleep(2.5 + random.random() * 2.0)
    finally:
        cookie_str = _cookie_string(await context.cookies(urls=[XHS_DOMAIN]))
        if "web_session=" in cookie_str:
            ok, _ = await _verify_cookie(cookie_str)
            if ok or (context.pages and not await _page_requires_login(context.pages[0])):
                save_cookie(cookie_str)
    return notes


def _emit_note(on_note: Callable[[dict[str, Any]], None] | None, note: dict[str, Any]) -> None:
    if not on_note:
        return
    try:
        on_note(dict(note))
    except Exception:
        return


def _dedupe_notes(notes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique_notes: list[dict[str, Any]] = []
    seen: set[str] = set()
    for note in notes:
        key = str(note.get("note_id") or note.get("note_url") or note.get("title") or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        unique_notes.append(note)
    return unique_notes


def _should_stop(should_stop: Callable[[], bool] | None) -> bool:
    if not should_stop:
        return False
    try:
        return bool(should_stop())
    except Exception:
        return False


async def _page_requires_login(page: Any) -> bool:
    try:
        body = await page.locator("body").inner_text(timeout=3000)
    except Exception:
        return False
    text = " ".join(body.split())
    return "登录后查看搜索结果" in text or "扫码" in text and "手机号登录" in text


async def _wait_for_browser_login(page: Any, context: Any, timeout_seconds: int) -> None:
    deadline = time.time() + max(30, timeout_seconds)
    while time.time() < deadline:
        cookie_str = _cookie_string(await context.cookies(urls=[XHS_DOMAIN]))
        if "web_session=" in cookie_str:
            ok, _ = await _verify_cookie(cookie_str)
            if ok and not await _page_requires_login(page):
                save_cookie(cookie_str)
                return
        try:
            if await _page_looks_logged_in(page):
                ok, _ = await _verify_cookie(cookie_str)
                if ok:
                    save_cookie(cookie_str)
                    return
        except Exception:
            pass
        await asyncio.sleep(2)


async def _extract_notes_from_search_page(page: Any, keyword: str) -> list[dict[str, Any]]:
    try:
        cards = await page.locator("a[href*='/explore/']").evaluate_all(
            """
            nodes => nodes.map(node => {
                const card = node.closest('.note-item, .cover, section, div') || node;
                const text = (card.innerText || node.innerText || '').trim();
                return { href: node.href || node.getAttribute('href') || '', text };
            })
            """
        )
    except Exception:
        return []

    notes: list[dict[str, Any]] = []
    for card in cards:
        note = _note_from_dom_card(card, keyword)
        if note:
            notes.append(note)
    return notes


def _note_from_dom_card(card: dict[str, Any], keyword: str) -> dict[str, Any] | None:
    href = str(card.get("href") or "")
    text = " ".join(str(card.get("text") or "").split())
    match = re.search(r"/explore/([A-Za-z0-9]+)", href)
    note_id = match.group(1) if match else ""
    if not note_id and not text:
        return None
    lines = [line.strip() for line in re.split(r"[\n\r]+", str(card.get("text") or "")) if line.strip()]
    title = lines[0] if lines else text[:80]
    liked = _first_count_after(text, ["赞", "点赞", "喜欢"])
    comment = _first_count_after(text, ["评论"])
    return {
        **MarketNote(
            title=title[:120],
            desc=text[:600],
            note_url=href,
            liked_count=liked,
            comment_count=comment,
            source_keyword=keyword,
        ).model_dump(),
        "note_id": note_id,
        "source": "browser_dom",
    }


def _first_count_after(text: str, labels: list[str]) -> str:
    for label in labels:
        match = re.search(rf"([0-9]+(?:\\.[0-9]+)?\\s*[万千kK]?)\\s*{label}|{label}\\s*([0-9]+(?:\\.[0-9]+)?\\s*[万千kK]?)", text)
        if match:
            return (match.group(1) or match.group(2) or "").strip()
    return ""


async def _find_login_qrcode(page: Any) -> str:
    selectors = [
        "xpath=//img[contains(@class, 'qrcode') or contains(@src, 'qrcode') or contains(@src, 'qr')]",
        "img.qrcode-img",
        "img[class*=qrcode]",
        "canvas",
    ]
    for selector in selectors:
        try:
            element = await page.wait_for_selector(selector=selector, timeout=4000)
            if selector == "canvas":
                screenshot = await element.screenshot()
                return base64.b64encode(screenshot).decode("utf-8")
            src = str(await element.get_attribute("src") or "")
            if not src:
                continue
            if src.startswith("http"):
                async with httpx.AsyncClient(follow_redirects=True) as client:
                    resp = await client.get(src, headers={"User-Agent": _user_agent()})
                    resp.raise_for_status()
                    return base64.b64encode(resp.content).decode("utf-8")
            return src
        except Exception:
            continue
    return ""


async def _click_login_entry(page: Any) -> bool:
    locators = [
        page.get_by_text("登录", exact=True),
        page.get_by_text("登录 / 注册", exact=False),
        page.get_by_role("button", name=re.compile("登录|注册")),
        page.locator("button").filter(has_text=re.compile("登录|注册")),
        page.locator("xpath=//*[contains(text(), '登录') or contains(text(), '注册')]"),
    ]
    for locator in locators:
        try:
            if await locator.count() == 0:
                continue
            await locator.first.click(timeout=3000)
            await page.wait_for_timeout(1500)
            return True
        except Exception:
            continue
    return False


async def _security_limit_message(page: Any) -> str:
    url = page.url
    try:
        body = await page.locator("body").inner_text(timeout=3000)
    except Exception:
        body = ""
    if "安全限制" in body or "IP存在风险" in body or "error_code=300012" in url:
        text = " ".join(body.split())
        return text[:300] or "小红书安全限制：当前 IP 或浏览器环境存在风险"
    return ""


async def _page_looks_logged_in(page: Any) -> bool:
    try:
        profile_entry = page.locator("xpath=//a[contains(@href, '/user/profile/')]//span[normalize-space()='我']")
        if await profile_entry.first.is_visible(timeout=500):
            return True
    except Exception:
        pass
    try:
        profile_link = page.locator("a[href*='/user/profile/']")
        return await profile_link.first.is_visible(timeout=500)
    except Exception:
        return False


async def _clear_xhs_cookies(context: Any) -> None:
    try:
        cookies = await context.cookies()
        names = {
            str(cookie.get("name"))
            for cookie in cookies
            if "xiaohongshu.com" in str(cookie.get("domain") or "")
        }
        if not names:
            return
        await context.clear_cookies()
    except Exception:
        return


def _note_from_search_item(item: dict[str, Any], keyword: str) -> dict[str, Any]:
    card = item.get("note_card") or item
    interact = card.get("interact_info") or {}
    note_id = item.get("id") or card.get("note_id") or ""
    xsec_token = item.get("xsec_token") or card.get("xsec_token") or ""
    note_url = f"{XHS_DOMAIN}/explore/{note_id}?xsec_token={xsec_token}&xsec_source=pc_search" if note_id else ""
    return MarketNote(
        title=str(card.get("display_title") or card.get("title") or ""),
        desc=str(card.get("desc") or "")[:600],
        note_url=note_url,
        liked_count=str(interact.get("liked_count") or card.get("liked_count") or ""),
        comment_count=str(interact.get("comment_count") or card.get("comment_count") or ""),
        source_keyword=keyword,
    ).model_dump()


def _base_headers(cookie: str) -> dict[str, str]:
    return {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json;charset=UTF-8",
        "Cookie": cookie,
        "Origin": XHS_DOMAIN,
        "Referer": f"{XHS_DOMAIN}/",
        "User-Agent": _user_agent(),
    }


def _signed_headers(uri: str, payload: dict[str, Any], cookie: str, method: str) -> dict[str, str]:
    from xhshow import Xhshow

    signer = Xhshow()
    if method.upper() == "POST":
        headers = signer.sign_headers_post(uri=uri, cookies=cookie, payload=payload)
    else:
        headers = signer.sign_headers_get(uri=uri, cookies=cookie, params=payload)
    return {
        "X-S": headers.get("x-s", ""),
        "X-T": str(headers.get("x-t", "")),
        "x-S-Common": headers.get("x-s-common", ""),
        "X-B3-Traceid": headers.get("x-b3-traceid", ""),
    }


def _get_search_id() -> str:
    value = (int(time.time() * 1000) << 64) + int(random.uniform(0, 2147483646))
    return _base36(value)


def _base36(number: int) -> str:
    alphabet = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    if number == 0:
        return "0"
    result = ""
    while number:
        number, index = divmod(number, len(alphabet))
        result = alphabet[index] + result
    return result


def _cookie_string(cookies: list[dict[str, Any]]) -> str:
    return ";".join(f"{cookie.get('name')}={cookie.get('value')}" for cookie in cookies)


def _cookie_dict(cookies: list[dict[str, Any]]) -> dict[str, str]:
    return {str(cookie.get("name")): str(cookie.get("value")) for cookie in cookies if cookie.get("name")}


def _playwright_cookies_from_cookie_string(cookie: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for part in cookie.split(";"):
        if "=" not in part:
            continue
        name, value = part.split("=", 1)
        name = name.strip()
        value = value.strip()
        if not name:
            continue
        items.append(
            {
                "name": name,
                "value": value,
                "domain": ".xiaohongshu.com",
                "path": "/",
                "secure": True,
                "sameSite": "Lax",
            }
        )
    return items


def _tail_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    lines = [line for line in path.read_text(encoding="utf-8", errors="ignore").splitlines() if line.strip()]
    if not lines:
        return {}
    try:
        return json.loads(lines[-1])
    except json.JSONDecodeError:
        return {"status": "error", "message": lines[-1][-500:]}


def _interaction_score(item: dict[str, Any]) -> float:
    return _count_to_number(item.get("liked_count", "")) * 1.0 + _count_to_number(item.get("comment_count", "")) * 1.4


def _is_viral_note(item: dict[str, Any]) -> bool:
    return _count_to_number(item.get("liked_count", "")) >= VIRAL_LIKE_FLOOR


def _count_to_number(value: Any) -> float:
    text = str(value or "").strip()
    if not text:
        return 0
    match = re.search(r"(\d+(?:\.\d+)?)", text)
    if not match:
        return 0
    number = float(match.group(1))
    if "万" in text:
        return number * 10000
    return number


def _user_agent() -> str:
    return "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.7827.114 Safari/537.36"


def result_to_dict(result: Any) -> dict[str, Any]:
    if is_dataclass(result):
        return asdict(result)
    if hasattr(result, "model_dump"):
        return result.model_dump()
    if isinstance(result, dict):
        return result
    return dict(result.__dict__)
