from app.providers.base import BaseLLMProvider


class MockLLMProvider(BaseLLMProvider):
    def generate_text(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float | None = None,
    ) -> str:
        return ""
