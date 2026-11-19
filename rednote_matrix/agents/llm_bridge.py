from __future__ import annotations

from typing import Any

from rednote_matrix.core.llm_client import OpenAICompatibleClient
from rednote_matrix.core.settings import load_settings


def call_llm_json(system_prompt: str, user_payload: dict[str, Any], temperature: float = 0.4) -> dict[str, Any]:
    settings = load_settings()
    client = OpenAICompatibleClient(settings)
    return client.chat_json(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"输入 JSON：\n{user_payload}"},
        ],
        temperature=temperature,
    )
