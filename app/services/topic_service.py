from __future__ import annotations

from typing import Any

from app.services.llm_service import generate_json


TOPIC_CATEGORIES = [
    "不限",
    "都市",
    "都市言情",
    "现代言情",
    "古代言情",
    "玄幻",
    "奇幻",
    "仙侠",
    "武侠",
    "科幻",
    "悬疑",
    "灵异",
    "历史",
    "军事",
    "游戏",
    "体育",
    "轻小说",
    "二次元",
    "现实题材",
    "职场",
    "校园",
    "种田",
    "宫斗宅斗",
    "穿越",
    "重生",
    "系统流",
    "无限流",
    "末世",
    "克苏鲁",
    "西幻",
    "东方玄幻",
]


def suggest_topics(reader: str, category: str, count: int, keywords: str = "") -> dict[str, Any]:
    count = max(1, min(10, count))
    fallback = {"items": _fallback_topics(reader, category, count, keywords)}
    result = generate_json(
        "你是中文网文选题策划助手。只返回 JSON，不要 Markdown。",
        _topic_prompt(reader, category, count, keywords),
        fallback,
        temperature=0.8,
    )
    return {"items": _normalize_topics(result.get("items"), fallback["items"], count)}


def _topic_prompt(reader: str, category: str, count: int, keywords: str) -> str:
    return f"""
请根据用户选择生成 {count} 个中文长篇小说选题。

读者：{reader or "不限"}
分类：{category or "不限"}
关键词/偏好：{keywords or "无"}

要求：
1. 每个选题要有清晰标题、卖点、写作方向、开篇切入、核心冲突、目标读者、风格要求。
2. outline_prompt 是后续生成故事大纲的输入稿，必须能直接放进“故事大纲”输入框。
3. outline_prompt 要包含题材、主角、核心冲突、基调、节奏和写作要求。
4. 不要生成色情、极端暴力、违法教学或仇恨内容。

返回 JSON 格式：
{{
  "items": [
    {{
      "title": "标题",
      "hook": "一句话卖点",
      "direction": "写作方向",
      "opening": "开篇切入点",
      "conflict": "核心冲突",
      "audience": "目标读者",
      "style": "风格要求",
      "outline_prompt": "可直接用于生成故事大纲的完整输入稿"
    }}
  ]
}}
""".strip()


def _normalize_topics(value: Any, fallback: list[dict[str, str]], count: int) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return fallback[:count]
    items = []
    for index, item in enumerate(value[:count]):
        if not isinstance(item, dict):
            continue
        title = _string(item.get("title")) or f"选题 {index + 1}"
        outline_prompt = _string(item.get("outline_prompt")) or _fallback_outline_prompt(title, item)
        items.append(
            {
                "title": title,
                "hook": _string(item.get("hook")),
                "direction": _string(item.get("direction")),
                "opening": _string(item.get("opening")),
                "conflict": _string(item.get("conflict")),
                "audience": _string(item.get("audience")),
                "style": _string(item.get("style")),
                "outline_prompt": outline_prompt,
            }
        )
    return items or fallback[:count]


def _fallback_topics(reader: str, category: str, count: int, keywords: str) -> list[dict[str, str]]:
    selected_reader = reader or "不限"
    selected_category = category or "都市悬疑"
    seed = keywords or "旧城、秘密、命运转折"
    items = []
    for index in range(count):
        title = f"{selected_category}选题{index + 1}"
        hook = f"围绕{seed}展开，用强冲突推动主角完成命运转折。"
        items.append(
            {
                "title": title,
                "hook": hook,
                "direction": f"面向{selected_reader}读者，融合{selected_category}类型期待，突出人物成长和持续悬念。",
                "opening": "从主角遇到一件无法用常理解释的事件切入，迅速建立目标和危机。",
                "conflict": "主角的现实目标与隐藏真相互相冲突，反派持续施压。",
                "audience": selected_reader,
                "style": "节奏紧凑，章末有钩子，人物动机清晰。",
                "outline_prompt": (
                    f"写一部{selected_category}小说，目标读者为{selected_reader}。"
                    f"核心关键词是：{seed}。主角在开篇遭遇一件打破原有生活的事件，"
                    "随后被卷入更大的秘密和持续升级的冲突。要求节奏紧凑，人物目标明确，"
                    "每章末尾保留悬念，整体风格具有强可读性和连续追读感。"
                ),
            }
        )
    return items


def _fallback_outline_prompt(title: str, item: dict[str, Any]) -> str:
    parts = [
        f"写一部名为《{title}》的长篇小说。",
        _string(item.get("direction")),
        _string(item.get("conflict")),
        _string(item.get("style")),
    ]
    return "\n".join(part for part in parts if part)


def _string(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value)
    return ""
