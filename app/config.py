import os
from pathlib import Path

from dotenv import load_dotenv


ENV_KEYS = [
    "PROVIDER",
    "OPENAI_API_KEY",
    "OPENAI_MODEL",
    "COMPAT_API_KEY",
    "COMPAT_BASE_URL",
    "COMPAT_MODEL",
    "LLM_TRACE",
    "LLM_TRACE_MAX_CHARS",
    "LLM_TIMEOUT_SECONDS",
    "LLM_RETRY_ATTEMPTS",
    "LLM_PROGRESS",
    "LLM_FALLBACK_ON_ERROR",
    "NOVEL_MEMORY_DIR",
    "NOVEL_OUTPUT_DIR",
    "NOVEL_PROJECTS_INDEX",
]


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def env_path() -> Path:
    return project_root() / ".env"


def reload() -> None:
    for key in ENV_KEYS:
        os.environ.pop(key, None)
    load_dotenv(env_path(), override=True)
    globals().update(
        {
            "PROVIDER": os.getenv("PROVIDER", "mock").strip().lower(),
            "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY", ""),
            "OPENAI_MODEL": os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
            "COMPAT_API_KEY": os.getenv("COMPAT_API_KEY", ""),
            "COMPAT_BASE_URL": os.getenv("COMPAT_BASE_URL", "https://openrouter.ai/api/v1"),
            "COMPAT_MODEL": os.getenv("COMPAT_MODEL", ""),
            "LLM_TRACE": os.getenv("LLM_TRACE", "false").strip().lower() in {"1", "true", "yes", "on"},
            "LLM_TRACE_MAX_CHARS": int(os.getenv("LLM_TRACE_MAX_CHARS", "6000") or "6000"),
            "LLM_TIMEOUT_SECONDS": float(os.getenv("LLM_TIMEOUT_SECONDS", "60") or "60"),
            "LLM_RETRY_ATTEMPTS": int(os.getenv("LLM_RETRY_ATTEMPTS", "3") or "3"),
            "LLM_PROGRESS": os.getenv("LLM_PROGRESS", "true").strip().lower() in {"1", "true", "yes", "on"},
            "LLM_FALLBACK_ON_ERROR": False,
            "NOVEL_MEMORY_DIR": os.getenv("NOVEL_MEMORY_DIR", "projects/default/story_memory"),
            "NOVEL_OUTPUT_DIR": os.getenv("NOVEL_OUTPUT_DIR", "projects/default/outputs"),
            "NOVEL_PROJECTS_INDEX": os.getenv("NOVEL_PROJECTS_INDEX", "novel_projects.json"),
        }
    )


reload()
