from __future__ import annotations

import re
from copy import deepcopy

from rednote_matrix.core.models import Draft


def normalize_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", str(text)).strip()


def strip_price_mentions(text: str) -> str:
    updated = str(text)
    patterns = [
        r"(售价|价格|到手价|入手价|活动价|原价|现价)\s*[：:]?\s*\d+(?:\.\d+)?\s*(?:元|块|rmb|RMB)?",
        r"\d+(?:\.\d+)?\s*(?:元|块|rmb|RMB)",
    ]
    for pattern in patterns:
        updated = re.sub(pattern, "", updated, flags=re.I)
    updated = re.sub(r"\s{2,}", " ", updated)
    updated = re.sub(r"[，,。；;]\s*([，,。；;])", r"\1", updated)
    return updated.strip(" ，,。；;")


def draft_from_state(state: dict) -> Draft:
    return Draft.model_validate(state.get("draft") or {})


def append_revision(state: dict, node: str, action: str, notes: list[str]) -> list[dict]:
    history = deepcopy(state.get("revision_history") or [])
    history.append({"node": node, "action": action, "notes": notes})
    return history
