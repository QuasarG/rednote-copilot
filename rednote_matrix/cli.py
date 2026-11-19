from __future__ import annotations

import json
import sys
from pathlib import Path

from rednote_matrix.core.render import render_user_copy
from rednote_matrix.core.runner import run_agent


def main() -> None:
    debug_json = "--json" in sys.argv
    args = [arg for arg in sys.argv[1:] if arg != "--json"]
    input_path = Path(args[0]) if args else Path("examples/sample_input.json")
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    result = run_agent(payload)
    if debug_json:
        print(json.dumps(result.model_dump(), ensure_ascii=False, indent=2))
    else:
        print(render_user_copy(result))


if __name__ == "__main__":
    main()
