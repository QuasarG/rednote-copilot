from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any

from openai import OpenAI

from rednote_matrix.core.settings import AgentSettings


class LLMConfigError(RuntimeError):
    pass


class LLMCallError(RuntimeError):
    pass


@dataclass(frozen=True)
class OpenAICompatibleClient:
    settings: AgentSettings

    def _validate(self) -> None:
        missing = []
        if not self._api_key:
            missing.append("OPENAI_API_KEY 或 DEEPSEEK_API_KEY")
        if not self.settings.openai_model:
            missing.append("OPENAI_MODEL")
        if missing:
            raise LLMConfigError(f"LLM 模式需要配置: {', '.join(missing)}")

    @property
    def _api_key(self) -> str:
        if self.settings.deepseek_api_key and "deepseek" in self.settings.openai_base_url:
            return self.settings.deepseek_api_key
        return self.settings.openai_api_key or self.settings.deepseek_api_key

    def chat(self, messages: list[dict[str, str]], temperature: float = 0.4) -> str:
        self._validate()
        client = OpenAI(
            api_key=self._api_key,
            base_url=self.settings.openai_base_url,
            timeout=self.settings.timeout_seconds,
        )
        response = None
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                response = client.chat.completions.create(
                    model=self.settings.openai_model,
                    messages=messages,
                    temperature=temperature,
                    stream=False,
                )
                break
            except Exception as error:
                last_error = error
                if attempt < 2:
                    time.sleep(0.8 * (attempt + 1))

        if response is None:
            raise LLMCallError(f"LLM 请求失败: {last_error}") from last_error

        content = response.choices[0].message.content
        if not content:
            raise LLMCallError("LLM 返回内容为空")
        return content

    def chat_json(self, messages: list[dict[str, str]], temperature: float = 0.4) -> dict[str, Any]:
        content = self.chat(messages, temperature=temperature)
        json_text = extract_json_object(content)
        return json.loads(json_text)


def extract_json_object(content: str) -> str:
    text = content.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.S)
    if fenced:
        text = fenced.group(1).strip()

    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < start:
        raise LLMCallError("LLM 没有返回可解析的 JSON 对象")
    return text[start : end + 1]
