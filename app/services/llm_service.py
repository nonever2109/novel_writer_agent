import json
from typing import Any

from app import config
from app.providers.base import BaseLLMProvider
from app.providers.mock_provider import MockLLMProvider
from app.providers.openai_compatible_provider import OpenAICompatibleProvider


def get_provider() -> BaseLLMProvider:
    if config.PROVIDER == "openai":
        if not config.OPENAI_API_KEY:
            raise ValueError("PROVIDER=openai requires OPENAI_API_KEY.")
        return OpenAICompatibleProvider(
            api_key=config.OPENAI_API_KEY,
            model=config.OPENAI_MODEL,
            timeout=config.LLM_TIMEOUT_SECONDS,
        )
    if config.PROVIDER in {"compatible", "openai_compatible"}:
        if not config.COMPAT_API_KEY:
            raise ValueError("PROVIDER=compatible requires COMPAT_API_KEY.")
        if not config.COMPAT_MODEL:
            raise ValueError("PROVIDER=compatible requires COMPAT_MODEL.")
        return OpenAICompatibleProvider(
            api_key=config.COMPAT_API_KEY,
            model=config.COMPAT_MODEL,
            base_url=config.COMPAT_BASE_URL,
            timeout=config.LLM_TIMEOUT_SECONDS,
        )
    return MockLLMProvider()


def llm_enabled() -> bool:
    return config.PROVIDER not in {"", "mock", "none", "template"}


def generate_json(
    system_prompt: str,
    user_prompt: str,
    fallback: dict[str, Any],
    temperature: float | None = None,
) -> dict[str, Any]:
    if not llm_enabled():
        return fallback

    try:
        _progress("请求模型生成 JSON")
        text = get_provider().generate_text(system_prompt, user_prompt, temperature=temperature)
    except Exception as exc:
        _progress(f"模型调用失败：{type(exc).__name__}")
        raise
    _trace(system_prompt, user_prompt, text)
    try:
        return _extract_json_object(text)
    except ValueError as exc:
        raise ValueError("模型没有返回可解析 JSON。") from exc


def generate_text(
    system_prompt: str,
    user_prompt: str,
    fallback: str,
    temperature: float | None = None,
) -> str:
    if not llm_enabled():
        return fallback
    try:
        _progress("请求模型生成文本")
        text = get_provider().generate_text(system_prompt, user_prompt, temperature=temperature)
    except Exception as exc:
        _progress(f"模型调用失败：{type(exc).__name__}")
        raise
    _trace(system_prompt, user_prompt, text)
    cleaned = text.strip()
    if not cleaned:
        raise ValueError("模型返回了空文本。")
    return cleaned


def _extract_json_object(text: str) -> dict[str, Any]:
    start = text.find("{")
    if start == -1:
        raise ValueError("No JSON object found.")

    depth = 0
    in_string = False
    escape = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start : index + 1])
    raise ValueError("No complete JSON object found.")


def _trace(system_prompt: str, user_prompt: str, response: str) -> None:
    if not config.LLM_TRACE:
        return
    limit = config.LLM_TRACE_MAX_CHARS
    print("\n===== LLM SYSTEM =====\n")
    print(system_prompt[:limit])
    print("\n===== LLM USER =====\n")
    print(user_prompt[:limit])
    print("\n===== LLM RESPONSE =====\n")
    print(response[:limit])


def _progress(message: str) -> None:
    if config.LLM_PROGRESS:
        print(f"[LLM] {message} (provider={config.PROVIDER}, timeout={config.LLM_TIMEOUT_SECONDS}s)", flush=True)
