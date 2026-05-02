from pathlib import Path
from typing import Any

from app.services.json_service import read_json, write_json


DEFAULT_GENRE_PROFILE = {
    "primary_genre": "general",
    "secondary_genres": [],
    "reader_promise": "每章都推动情节、角色关系或悬念。",
    "must_have": ["明确戏剧任务", "场景状态变化", "章末期待"],
    "avoid": ["水章", "解释型对白", "角色无动机行动"],
    "chapter_check_focus": ["本章是否发生不可逆变化", "角色选择是否符合目标与底线"],
}


def load_story_memory(memory_dir: str) -> dict[str, Any]:
    base = Path(memory_dir)
    return {
        "bible": _read_text(base / "bible.md"),
        "style_guide": _read_text(base / "style_guide.md"),
        "genre_profile": read_json(base / "genre_profile.json", DEFAULT_GENRE_PROFILE),
        "outline_request": read_json(base / "outline" / "outline_request.json", {}),
        "chapter_plan": read_json(base / "outline" / "chapter_plan.json", {"planned_chapters": []}),
        "timeline": _ensure_list_container(read_json(base / "current_state" / "timeline.json", {"events": []}), "events"),
        "characters": _ensure_list_container(read_json(base / "current_state" / "characters.json", {"characters": []}), "characters"),
        "plot_threads": _ensure_list_container(read_json(base / "current_state" / "plot_threads.json", {"threads": []}), "threads"),
        "foreshadowing": _ensure_list_container(read_json(base / "current_state" / "foreshadowing.json", {"items": []}), "items"),
        "chapter_summaries": _load_recent_chapter_summaries(base / "chapter_summaries"),
    }


def archive_chapter(memory_dir: str, archive: dict[str, Any]) -> Path:
    chapter_number = archive.get("chapter_number") or "draft"
    file_name = f"chapter_{int(chapter_number):03d}.json" if isinstance(chapter_number, int) else f"{chapter_number}.json"
    path = Path(memory_dir) / "chapter_summaries" / file_name
    write_json(path, archive)
    return path


def apply_memory_update(memory_dir: str, memory_update: dict[str, Any]) -> None:
    base = Path(memory_dir) / "current_state"
    _append_events(base / "timeline.json", _as_list(memory_update.get("timeline_updates", [])), "events")
    _append_events(base / "plot_threads.json", _as_list(memory_update.get("plot_thread_updates", [])), "threads")
    _append_events(base / "foreshadowing.json", _as_list(memory_update.get("foreshadowing_updates", [])), "items")
    _merge_character_updates(base / "characters.json", _as_list(memory_update.get("character_updates", [])))


def ensure_default_memory(memory_dir: str) -> None:
    base = Path(memory_dir)
    base.mkdir(parents=True, exist_ok=True)
    _ensure_text(
        base / "bible.md",
        "# Story Bible\n\n记录世界观规则、核心秘密、长期限制和结局方向。\n",
    )
    _ensure_text(
        base / "style_guide.md",
        "# Style Guide\n\n"
        "- 口语化、自然、克制，像人在讲故事。\n"
        "- 多用动作、对白和现场细节。\n"
        "- 不要生成无关剧情的重复描写。\n"
        "- 避免咬文嚼字、空泛抒情和解释型对白。\n"
        "- 不要大量的并列句和否定又肯定的句子。\n"
        "- 不要频繁使用“仿佛、像是、某种、命运、灵魂、深处、无声地、微微、骤然、复杂情绪”等 AI 腔词。\n"
        "- 情绪尽量用动作、停顿、物件和环境细节带出来，不要每段都总结心理。\n",
    )
    write_json_if_missing(base / "genre_profile.json", DEFAULT_GENRE_PROFILE)
    write_json_if_missing(base / "outline" / "chapter_plan.json", {"planned_chapters": []})
    write_json_if_missing(base / "current_state" / "timeline.json", {"events": []})
    write_json_if_missing(base / "current_state" / "characters.json", {"characters": []})
    write_json_if_missing(base / "current_state" / "plot_threads.json", {"threads": []})
    write_json_if_missing(base / "current_state" / "foreshadowing.json", {"items": []})
    for name in ["chapter_summaries", "characters", "locations", "factions", "safety", "outline"]:
        (base / name).mkdir(parents=True, exist_ok=True)


def write_json_if_missing(path: Path, data: Any) -> None:
    if not path.exists():
        write_json(path, data)


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _ensure_text(path: Path, content: str) -> None:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def _load_recent_chapter_summaries(path: Path, limit: int = 5) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    summaries = []
    for item in sorted(path.glob("chapter_*.json"))[-limit:]:
        summaries.append(read_json(item, {}))
    return summaries


def _append_events(path: Path, updates: list[Any], key: str) -> None:
    if not updates:
        return
    data = _ensure_list_container(read_json(path, {key: []}), key)
    data[key].extend(_coerce_event_updates(updates))
    write_json(path, data)


def _merge_character_updates(path: Path, updates: list[Any]) -> None:
    if not updates:
        return
    data = _ensure_list_container(read_json(path, {"characters": []}), "characters")
    characters = {
        item.get("name"): item
        for item in data.get("characters", [])
        if isinstance(item, dict) and item.get("name")
    }
    for update in updates:
        if isinstance(update, str):
            update = {"name": update, "notes": update}
        if not isinstance(update, dict):
            continue
        name = update.get("name")
        if not name:
            note = update.get("note") or update.get("notes") or update.get("summary")
            if note:
                name = f"未命名角色更新{len(characters) + 1}"
                update["name"] = name
            else:
                continue
        name = str(name)
        update["name"] = name
        if not update:
            continue
        current = characters.get(name, {"name": name})
        current.update(update)
        characters[name] = current
    write_json(path, {"characters": list(characters.values())})


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _ensure_list_container(data: Any, key: str) -> dict[str, list[Any]]:
    if isinstance(data, dict):
        items = data.get(key, [])
        if isinstance(items, list):
            return {**data, key: items}
        return {**data, key: _as_list(items)}
    if isinstance(data, list):
        return {key: data}
    if data in (None, ""):
        return {key: []}
    return {key: [data]}


def _coerce_event_updates(updates: list[Any]) -> list[dict[str, Any]]:
    coerced = []
    for update in updates:
        if isinstance(update, dict):
            coerced.append(update)
        elif isinstance(update, str):
            coerced.append({"event": update})
    return coerced
