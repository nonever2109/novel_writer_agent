from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"

PROVIDERS = {
    "1": {
        "name": "OpenAI 官方",
        "provider": "openai",
        "base_url": "",
        "model": "gpt-4.1-mini",
    },
    "2": {
        "name": "阿里百炼 DashScope",
        "provider": "openai_compatible",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-plus",
    },
    "3": {
        "name": "OpenRouter",
        "provider": "openai_compatible",
        "base_url": "https://openrouter.ai/api/v1",
        "model": "openai/gpt-4.1-mini",
    },
    "4": {
        "name": "DeepSeek",
        "provider": "openai_compatible",
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",
    },
    "5": {
        "name": "硅基流动 SiliconFlow",
        "provider": "openai_compatible",
        "base_url": "https://api.siliconflow.cn/v1",
        "model": "deepseek-ai/DeepSeek-V3",
    },
    "6": {
        "name": "自定义 OpenAI Compatible",
        "provider": "openai_compatible",
        "base_url": "",
        "model": "",
    },
}

ORDERED_KEYS = [
    "PROVIDER",
    "OPENAI_API_KEY",
    "OPENAI_MODEL",
    "COMPAT_API_KEY",
    "COMPAT_BASE_URL",
    "COMPAT_MODEL",
    "LLM_TRACE",
    "LLM_TRACE_MAX_CHARS",
    "LLM_TIMEOUT_SECONDS",
    "LLM_PROGRESS",
    "LLM_FALLBACK_ON_ERROR",
    "NOVEL_MEMORY_DIR",
    "NOVEL_OUTPUT_DIR",
    "NOVEL_PROJECTS_INDEX",
]


def main() -> None:
    values = read_env(ENV_PATH)
    print()
    print("小说助手初始化配置")
    print("=" * 30)
    print("1. OpenAI 官方")
    print("2. 阿里百炼 DashScope")
    print("3. OpenRouter")
    print("4. DeepSeek")
    print("5. 硅基流动 SiliconFlow")
    print("6. 自定义 OpenAI Compatible")
    print("0. Mock 测试模式（无需 API Key）")
    choice = ask_choice("请选择供应商序号", {"0", *PROVIDERS.keys()})

    if choice == "0":
        values["PROVIDER"] = "mock"
        apply_defaults(values)
        write_env(ENV_PATH, values)
        print("\n已保存 Mock 测试模式。")
        return

    selected = PROVIDERS[choice]
    model = ask_with_default("请输入模型名称", selected["model"])
    api_key = ask_required("请输入 API Key")

    if selected["provider"] == "openai":
        values["PROVIDER"] = "openai"
        values["OPENAI_MODEL"] = model
        values["OPENAI_API_KEY"] = api_key
        values.setdefault("COMPAT_BASE_URL", "https://openrouter.ai/api/v1")
        values.setdefault("COMPAT_MODEL", "")
        values.setdefault("COMPAT_API_KEY", "")
    else:
        base_url = selected["base_url"] or ask_required("请输入 OpenAI Compatible API 地址")
        values["PROVIDER"] = "openai_compatible"
        values["COMPAT_BASE_URL"] = base_url
        values["COMPAT_MODEL"] = model
        values["COMPAT_API_KEY"] = api_key
        values.setdefault("OPENAI_API_KEY", "")
        values.setdefault("OPENAI_MODEL", "gpt-4.1-mini")
    apply_defaults(values)
    write_env(ENV_PATH, values)
    print()
    print(f"配置已保存：{selected['name']} / {model}")
    print(f"配置文件：{ENV_PATH}")
    print("\r\n----------------------------------------------------------")
    print("\r\n配置完成按下任意键关闭窗口，点击“启动小说助手”启动服务。\r\n")
    print("----------------------------------------------------------\r\n")


def read_env(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = unquote(value.strip())
    return values


def write_env(path: Path, values: dict[str, str]) -> None:
    lines = []
    for key in ORDERED_KEYS:
        if key in values:
            lines.append(f"{key}={quote(values[key])}")
    for key in sorted(set(values) - set(ORDERED_KEYS)):
        lines.append(f"{key}={quote(values[key])}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def apply_defaults(values: dict[str, str]) -> None:
    values.setdefault("LLM_TRACE", "false")
    values.setdefault("LLM_TRACE_MAX_CHARS", "6000")
    values.setdefault("LLM_TIMEOUT_SECONDS", "600")
    values.setdefault("LLM_PROGRESS", "true")
    values.setdefault("LLM_FALLBACK_ON_ERROR", "false")
    values.setdefault("NOVEL_MEMORY_DIR", "projects/default/story_memory")
    values.setdefault("NOVEL_OUTPUT_DIR", "projects/default/outputs")
    values.setdefault("NOVEL_PROJECTS_INDEX", "novel_projects.json")


def ask_choice(prompt: str, choices: set[str]) -> str:
    while True:
        value = input(f"{prompt}: ").strip()
        if value in choices:
            return value
        print("输入无效，请重新输入。")


def ask_required(prompt: str) -> str:
    while True:
        value = input(f"{prompt}: ").strip()
        if value:
            return value
        print("不能为空。")


def ask_with_default(prompt: str, default: str) -> str:
    if default:
        value = input(f"{prompt}，直接回车使用默认 [{default}]: ").strip()
        return value or default
    return ask_required(prompt)


def quote(value: str) -> str:
    if value == "" or any(ch.isspace() for ch in value) or "#" in value or '"' in value:
        return '"' + value.replace('"', '\\"') + '"'
    return value


def unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


if __name__ == "__main__":
    main()
