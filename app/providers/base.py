from abc import ABC, abstractmethod


class BaseLLMProvider(ABC):
    @abstractmethod
    def generate_text(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float | None = None,
    ) -> str:
        raise NotImplementedError
