from __future__ import annotations

import sys

from rednote_matrix.integrations.xhs_core import run_login_worker


def main() -> None:
    session_id = sys.argv[1] if len(sys.argv) > 1 else ""
    headless_text = sys.argv[2].lower() if len(sys.argv) > 2 else "true"
    timeout_text = sys.argv[3] if len(sys.argv) > 3 else "180"
    virtual_display_text = sys.argv[4].lower() if len(sys.argv) > 4 else "false"
    if not session_id:
        raise SystemExit("missing session_id")
    timeout_seconds = int(timeout_text) if timeout_text.isdigit() else 180
    run_login_worker(session_id, headless_text == "true", timeout_seconds, virtual_display_text == "true")


if __name__ == "__main__":
    main()
