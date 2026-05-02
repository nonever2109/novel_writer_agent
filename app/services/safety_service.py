from typing import Any


COPYRIGHT_SIGNALS = [
    "续写",
    "同人",
    "照着",
    "模仿",
    "哈利波特",
    "三体",
    "斗罗大陆",
    "诡秘之主",
]

POLICY_SIGNALS = [
    "露骨色情",
    "未成年人性",
    "自杀教程",
    "制毒",
    "炸药教程",
    "仇恨宣言",
]


def safety_check(text: str) -> dict[str, Any]:
    copyright_hits = [signal for signal in COPYRIGHT_SIGNALS if signal.lower() in text.lower()]
    policy_hits = [signal for signal in POLICY_SIGNALS if signal.lower() in text.lower()]
    if policy_hits:
        status = "blocked"
    elif copyright_hits:
        status = "needs_transform"
    else:
        status = "safe"
    return {
        "status": status,
        "copyright_hits": copyright_hits,
        "policy_hits": policy_hits,
        "notes": _notes(status),
    }


def transform_request(request: dict[str, Any], safety_report: dict[str, Any]) -> dict[str, Any]:
    transformed = dict(request)
    if safety_report.get("status") == "needs_transform":
        transformed["originality_instruction"] = (
            "保留抽象题材体验，改为原创角色、原创世界观和不同剧情结构。"
        )
        transformed["copyright_transform_applied"] = True
    return transformed


def _notes(status: str) -> str:
    if status == "blocked":
        return "输入包含不可生成的安全风险，需要用户改写需求。"
    if status == "needs_transform":
        return "存在版权近似风险，需要转为原创设定。"
    return "未发现明显输入风险。"
