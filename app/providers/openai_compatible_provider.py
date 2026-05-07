import time
from collections.abc import Callable
from typing import TypeVar

from openai import APIConnectionError, APITimeoutError, InternalServerError, OpenAI, RateLimitError

from app.providers.base import BaseLLMProvider


_T = TypeVar("_T")
RETRYABLE_OPENAI_ERRORS = (APIConnectionError, APITimeoutError, InternalServerError, RateLimitError)


class OpenAICompatibleProvider(BaseLLMProvider):
    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str | None = None,
        timeout: float | None = None,
        retry_attempts: int = 3,
    ) -> None:
        kwargs = {"api_key": api_key, "timeout": timeout, "max_retries": 0}
        if base_url:
            kwargs["base_url"] = base_url
        self.client = OpenAI(**kwargs)
        self.model = model
        self.retry_attempts = max(1, retry_attempts)

    def generate_text(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float | None = None,
    ) -> str:
        response = self._with_retries(
            lambda: self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temperature if temperature is not None else 0.7,
            )
        )
        return response.choices[0].message.content or ""

    def _with_retries(self, action: Callable[[], _T]) -> _T:
        delay_seconds = 1.0
        for attempt in range(1, self.retry_attempts + 1):
            try:
                return action()
            except RETRYABLE_OPENAI_ERRORS:
                if attempt >= self.retry_attempts:
                    raise
                time.sleep(delay_seconds)
                delay_seconds = min(delay_seconds * 2, 8.0)
        raise RuntimeError("Retry loop exited unexpectedly.")
