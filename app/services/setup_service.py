from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from app import config
from app.providers.openai_compatible_provider import OpenAICompatibleProvider


SETUP_KEYS = [
    "PROVIDER",
    "OPENAI_API_KEY",
    "OPENAI_MODEL",
    "COMPAT_API_KEY",
    "COMPAT_BASE_URL",
    "COMPAT_MODEL",
    "LLM_TIMEOUT_SECONDS",
    "LLM_TRACE",
    "LLM_PROGRESS",
    "LLM_FALLBACK_ON_ERROR",
    "NOVEL_PROJECTS_INDEX",
]


def setup_status() -> dict[str, Any]:
    values = _current_values()
    missing = _missing_required(values, env_exists=config.env_path().exists())
    return {
        "configured": not missing,
        "env_exists": config.env_path().exists(),
        "provider": values["PROVIDER"],
        "missing": missing,
    }


def setup_config() -> dict[str, Any]:
    values = _current_values()
    return {
        **values,
        "OPENAI_API_KEY": "",
        "OPENAI_API_KEY_MASKED": _mask_secret(values["OPENAI_API_KEY"]),
        "COMPAT_API_KEY": "",
        "COMPAT_API_KEY_MASKED": _mask_secret(values["COMPAT_API_KEY"]),
    }


def save_setup_config(payload: dict[str, Any]) -> dict[str, Any]:
    existing = _read_env(config.env_path())
    current = _current_values()
    provider = _normalize_provider(str(payload.get("PROVIDER") or current["PROVIDER"]))
    updates = {
        "PROVIDER": provider,
        "OPENAI_MODEL": _string(payload.get("OPENAI_MODEL")) or current["OPENAI_MODEL"],
        "COMPAT_BASE_URL": _string(payload.get("COMPAT_BASE_URL")) or current["COMPAT_BASE_URL"],
        "COMPAT_MODEL": _string(payload.get("COMPAT_MODEL")) or current["COMPAT_MODEL"],
        "LLM_TIMEOUT_SECONDS": str(float(payload.get("LLM_TIMEOUT_SECONDS") or current["LLM_TIMEOUT_SECONDS"])),
        "LLM_TRACE": _bool_string(payload.get("LLM_TRACE", current["LLM_TRACE"])),
        "LLM_PROGRESS": _bool_string(payload.get("LLM_PROGRESS", current["LLM_PROGRESS"])),
        "LLM_FALLBACK_ON_ERROR": "false",
        "NOVEL_PROJECTS_INDEX": _string(payload.get("NOVEL_PROJECTS_INDEX")) or current["NOVEL_PROJECTS_INDEX"],
    }
    openai_key = _string(payload.get("OPENAI_API_KEY"))
    compat_key = _string(payload.get("COMPAT_API_KEY"))
    if openai_key:
        updates["OPENAI_API_KEY"] = openai_key
    elif "OPENAI_API_KEY" in existing:
        updates["OPENAI_API_KEY"] = existing["OPENAI_API_KEY"]
    if compat_key:
        updates["COMPAT_API_KEY"] = compat_key
    elif "COMPAT_API_KEY" in existing:
        updates["COMPAT_API_KEY"] = existing["COMPAT_API_KEY"]

    merged = {**existing, **updates}
    missing = _missing_required(merged, env_exists=True)
    if missing:
        raise ValueError(f"Missing required config: {', '.join(missing)}")
    _write_env(config.env_path(), merged)
    config.reload()
    return {"status": "ok", **setup_status()}


def test_setup_config(payload: dict[str, Any]) -> dict[str, Any]:
    provider = _normalize_provider(str(payload.get("PROVIDER") or config.PROVIDER))
    timeout = float(payload.get("LLM_TIMEOUT_SECONDS") or config.LLM_TIMEOUT_SECONDS)
    if provider in {"mock", "none", "template", ""}:
        return {"status": "ok", "message": "Mock 模式无需连接测试。"}
    if provider == "openai":
        api_key = _string(payload.get("OPENAI_API_KEY")) or config.OPENAI_API_KEY
        model = _string(payload.get("OPENAI_MODEL")) or config.OPENAI_MODEL
        if not api_key or not model:
            raise ValueError("OpenAI 配置需要 API Key 和模型名称。")
        client = OpenAICompatibleProvider(api_key=api_key, model=model, timeout=timeout)
    elif provider in {"compatible", "openai_compatible"}:
        api_key = _string(payload.get("COMPAT_API_KEY")) or config.COMPAT_API_KEY
        model = _string(payload.get("COMPAT_MODEL")) or config.COMPAT_MODEL
        base_url = _string(payload.get("COMPAT_BASE_URL")) or config.COMPAT_BASE_URL
        if not api_key or not model:
            raise ValueError("OpenAI Compatible 配置需要 API Key 和模型名称。")
        client = OpenAICompatibleProvider(api_key=api_key, model=model, base_url=base_url, timeout=timeout)
    else:
        raise ValueError(f"Unsupported provider: {provider}")
    text = client.generate_text("只回复 OK。", "请回复 OK。", temperature=0)
    return {"status": "ok", "message": f"连接成功：{text[:40] or 'OK'}"}


def _current_values() -> dict[str, Any]:
    values = _read_env(config.env_path())
    return {
        "PROVIDER": _normalize_provider(values.get("PROVIDER", "mock")),
        "OPENAI_API_KEY": values.get("OPENAI_API_KEY", ""),
        "OPENAI_MODEL": values.get("OPENAI_MODEL", "gpt-4.1-mini"),
        "COMPAT_API_KEY": values.get("COMPAT_API_KEY", ""),
        "COMPAT_BASE_URL": values.get("COMPAT_BASE_URL", "https://openrouter.ai/api/v1"),
        "COMPAT_MODEL": values.get("COMPAT_MODEL", ""),
        "LLM_TIMEOUT_SECONDS": _float_value(values.get("LLM_TIMEOUT_SECONDS"), 60),
        "LLM_TRACE": _bool_value(values.get("LLM_TRACE"), False),
        "LLM_PROGRESS": _bool_value(values.get("LLM_PROGRESS"), True),
        "LLM_FALLBACK_ON_ERROR": False,
        "NOVEL_PROJECTS_INDEX": values.get("NOVEL_PROJECTS_INDEX", "novel_projects.json"),
    }


def _missing_required(values: dict[str, Any], env_exists: bool) -> list[str]:
    if not env_exists:
        return [".env"]
    provider = _normalize_provider(str(values.get("PROVIDER") or "mock"))
    if provider in {"mock", "none", "template", ""}:
        return []
    if provider == "openai":
        return [key for key in ["OPENAI_API_KEY", "OPENAI_MODEL"] if not _string(values.get(key))]
    if provider in {"compatible", "openai_compatible"}:
        return [key for key in ["COMPAT_API_KEY", "COMPAT_MODEL"] if not _string(values.get(key))]
    return ["PROVIDER"]


def _read_env(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _write_env(path: Path, values: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered_keys = [key for key in SETUP_KEYS if key in values]
    extra_keys = sorted(key for key in values if key not in SETUP_KEYS)
    lines = [f"{key}={_format_env_value(values[key])}" for key in [*ordered_keys, *extra_keys]]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    for key, value in values.items():
        os.environ[key] = str(value)


def _format_env_value(value: Any) -> str:
    text = str(value)
    if not text or any(char.isspace() for char in text) or "#" in text:
        return '"' + text.replace('"', '\\"') + '"'
    return text


def _mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}****{value[-4:]}"


def _normalize_provider(value: str) -> str:
    normalized = value.strip().lower()
    return "openai_compatible" if normalized == "compatible" else normalized


def _string(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value)
    return ""


def _bool_string(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return "true" if str(value).strip().lower() in {"1", "true", "yes", "on"} else "false"


def _bool_value(value: Any, default: bool) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _float_value(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
