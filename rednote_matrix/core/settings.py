from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values


@dataclass(frozen=True)
class AgentSettings:
    openai_api_key: str = ""
    deepseek_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = ""
    timeout_seconds: int = 60


def load_settings() -> AgentSettings:
    env_file = dotenv_values(Path.cwd() / ".env")

    def read_setting(key: str, default: str = "", prefer_env: bool = False) -> str:
        env_value = os.getenv(key)
        file_value = env_file.get(key)
        if prefer_env and env_value is not None:
            return env_value.strip()
        if file_value is not None:
            return str(file_value).strip()
        if env_value is not None:
            return env_value.strip()
        return default

    timeout_raw = read_setting("OPENAI_TIMEOUT_SECONDS", "60")
    timeout_seconds = int(timeout_raw) if timeout_raw.isdigit() else 60

    return AgentSettings(
        openai_api_key=read_setting("OPENAI_API_KEY"),
        deepseek_api_key=read_setting("DEEPSEEK_API_KEY"),
        openai_base_url=read_setting("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        openai_model=read_setting("OPENAI_MODEL"),
        timeout_seconds=timeout_seconds,
    )
