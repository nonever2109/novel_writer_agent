from openai import OpenAI

from app.providers.base import BaseLLMProvider


class OpenAICompatibleProvider(BaseLLMProvider):
    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str | None = None,
        timeout: float | None = None,
    ) -> None:
        kwargs = {"api_key": api_key, "timeout": timeout}
        if base_url:
            kwargs["base_url"] = base_url
        self.client = OpenAI(**kwargs)
        self.model = model

    def generate_text(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float | None = None,
    ) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature if temperature is not None else 0.7,
        )
        return response.choices[0].message.content or ""
