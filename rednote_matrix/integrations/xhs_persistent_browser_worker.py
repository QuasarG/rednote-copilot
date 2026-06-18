from __future__ import annotations

import sys

from rednote_matrix.integrations.xhs_core import run_persistent_browser_worker


def main() -> None:
    timeout_text = sys.argv[1] if len(sys.argv) > 1 else "0"
    timeout_seconds = int(timeout_text) if timeout_text.isdigit() else 0
    run_persistent_browser_worker(timeout_seconds)


if __name__ == "__main__":
    main()
