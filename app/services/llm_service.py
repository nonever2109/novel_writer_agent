import json
import re
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
            retry_attempts=config.LLM_RETRY_ATTEMPTS,
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
            retry_attempts=config.LLM_RETRY_ATTEMPTS,
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
        fallback = dict(fallback)
        fallback["llm_parse_error"] = "模型没有返回可解析 JSON，已使用本地结构化 fallback 继续流程。"
        fallback["raw_model_output"] = text[: config.LLM_TRACE_MAX_CHARS]
        _progress("模型返回 JSON 解析失败，已使用本地结构化 fallback 继续流程")
        return fallback


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
    text = _strip_json_fence(text.strip())
    starts = [index for index, char in enumerate(text) if char == "{"]
    if not starts:
        raise ValueError("No JSON object found.")

    last_error: Exception | None = None
    for start in starts:
        try:
            return _parse_json_object_at(text, start)
        except (json.JSONDecodeError, ValueError) as exc:
            last_error = exc
            continue
    if last_error:
        raise ValueError(f"No valid JSON object found: {last_error}") from last_error
    raise ValueError("No complete JSON object found.")


def _strip_json_fence(text: str) -> str:
    match = re.fullmatch(r"```(?:json|JSON)?\s*(.*?)\s*```", text, flags=re.DOTALL)
    return match.group(1).strip() if match else text


def _parse_json_object_at(text: str, start: int) -> dict[str, Any]:
    candidate = _slice_json_object(text, start)
    try:
        value = json.loads(candidate)
    except json.JSONDecodeError:
        value = json.loads(_remove_trailing_commas(candidate))
    if not isinstance(value, dict):
        raise ValueError("Parsed JSON value is not an object.")
    return value


def _slice_json_object(text: str, start: int) -> str:
    if text[start] != "{":
        raise ValueError("JSON object must start with '{'.")

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
                return text[start : index + 1]
    raise ValueError("No complete JSON object found.")


def _remove_trailing_commas(text: str) -> str:
    return re.sub(r",\s*([}\]])", r"\1", text)


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
        print(
            f"[LLM] {message} "
            f"(provider={config.PROVIDER}, timeout={config.LLM_TIMEOUT_SECONDS}s, retries={config.LLM_RETRY_ATTEMPTS})",
            flush=True,
        )
