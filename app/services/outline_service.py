import json
from pathlib import Path
import shutil
import re
from time import perf_counter
from typing import Any
from typing import Callable
from typing import TypeVar

from app.services.json_service import read_json
from app.services.json_service import write_json
from app.services.llm_service import generate_json
from app.services.memory_service import ensure_default_memory

ProgressCallback = Callable[[dict[str, Any]], None]
T = TypeVar("T")
OUTLINE_BATCH_SIZE = 50


def generate_story_outline(
    user_input: str,
    memory_dir: str,
    target_chapter_count: int = 30,
    target_words_per_chapter: int | None = None,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    if target_chapter_count > OUTLINE_BATCH_SIZE:
        return _generate_segmented_story_outline(
            user_input,
            memory_dir,
            target_chapter_count,
            target_words_per_chapter,
            progress_callback,
        )

    total_steps = 5
    _run_outline_step(progress_callback, "初始化故事记忆", 1, total_steps, lambda: ensure_default_memory(memory_dir))

    fallback, system_prompt, user_prompt = _run_outline_step(
        progress_callback,
        "准备大纲提示",
        2,
        total_steps,
        lambda: _build_outline_request(user_input, target_chapter_count, target_words_per_chapter),
    )
    outline = _run_outline_step(
        progress_callback,
        "请求模型生成大纲",
        3,
        total_steps,
        lambda: generate_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            fallback=fallback,
            temperature=0.5,
        ),
    )
    outline = _run_outline_step(
        progress_callback,
        "整理章节计划",
        4,
        total_steps,
        lambda: _normalize_outline(outline, target_chapter_count, target_words_per_chapter),
    )
    _run_outline_step(
        progress_callback,
        "写入故事记忆",
        5,
        total_steps,
        lambda: _write_outline(memory_dir, outline, user_input, target_chapter_count, target_words_per_chapter),
    )
    return outline


def _generate_segmented_story_outline(
    user_input: str,
    memory_dir: str,
    target_chapter_count: int,
    target_words_per_chapter: int | None,
    progress_callback: ProgressCallback | None,
) -> dict[str, Any]:
    batches = _chapter_batches(target_chapter_count, OUTLINE_BATCH_SIZE)
    total_steps = len(batches) + 4
    _run_outline_step(progress_callback, "初始化故事记忆", 1, total_steps, lambda: ensure_default_memory(memory_dir))

    overview_fallback, overview_system_prompt, overview_user_prompt = _build_outline_overview_request(
        user_input,
        target_chapter_count,
        target_words_per_chapter,
    )
    overview = _run_outline_step(
        progress_callback,
        "请求模型生成总纲",
        2,
        total_steps,
        lambda: generate_json(
            system_prompt=overview_system_prompt,
            user_prompt=overview_user_prompt,
            fallback=overview_fallback,
            temperature=0.5,
        ),
    )

    planned_chapters: list[dict[str, Any]] = []
    previous_batch_tail: list[dict[str, Any]] = []
    for offset, (start, end) in enumerate(batches, start=3):
        batch_fallback, batch_system_prompt, batch_user_prompt = _build_chapter_batch_request(
            user_input=user_input,
            overview=overview,
            start_chapter=start,
            end_chapter=end,
            target_words_per_chapter=target_words_per_chapter,
            previous_batch_tail=previous_batch_tail,
        )
        batch_outline = _run_outline_step(
            progress_callback,
            f"请求模型生成第{start}-{end}章",
            offset,
            total_steps,
            lambda fallback=batch_fallback, system_prompt=batch_system_prompt, user_prompt=batch_user_prompt: generate_json(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                fallback=fallback,
                temperature=0.5,
            ),
        )
        batch_plan = normalize_chapter_plan(
            batch_outline.get("chapter_plan", batch_outline),
            target_chapter_count=end,
        )
        batch_chapters = [
            chapter
            for chapter in batch_plan.get("planned_chapters", [])
            if isinstance(chapter, dict) and start <= chapter.get("chapter_number", 0) <= end
        ]
        planned_chapters.extend(batch_chapters)
        previous_batch_tail = batch_chapters[-5:]

    outline = _run_outline_step(
        progress_callback,
        "整理章节计划",
        len(batches) + 3,
        total_steps,
        lambda: _normalize_outline(
            _merge_segmented_outline(overview, planned_chapters, target_words_per_chapter),
            target_chapter_count,
            target_words_per_chapter,
        ),
    )
    _run_outline_step(
        progress_callback,
        "写入故事记忆",
        len(batches) + 4,
        total_steps,
        lambda: _write_outline(memory_dir, outline, user_input, target_chapter_count, target_words_per_chapter),
    )
    return outline


def _build_outline_request(
    user_input: str,
    target_chapter_count: int,
    target_words_per_chapter: int | None,
) -> tuple[dict[str, Any], str, str]:
    fallback = _fallback_outline(user_input, target_chapter_count, target_words_per_chapter)
    word_requirement = (
        f"每章正文目标字数约 {target_words_per_chapter} 字，逐章计划中需要体现该字数要求。"
        if target_words_per_chapter
        else "逐章计划中可按章节任务自然安排正文篇幅。"
    )
    system_prompt = (
        "你是专业长篇小说策划编辑。请只输出一个合法 JSON 对象，不要输出 Markdown。"
        "回复的第一个字符必须是 {，最后一个字符必须是 }。"
        "不要使用注释、尾逗号、中文引号或省略号占位。"
        "JSON 字段名保持英文，所有字段值、章节标题、角色说明、故事设定、风格指南和备注必须使用简体中文。"
        "目标是建立可连载的故事底座，而不是写正文。"
    )
    user_prompt = (
        "根据以下创作需求生成小说项目大纲。必须包含字段："
        "genre_profile, bible, style_guide, chapter_plan, plot_threads, foreshadowing, characters。\n"
        "chapter_plan 必须是逐章计划，格式必须为："
        '{"planned_chapters":[{"chapter_number":1,"title":"...","goal":"...","expected_hook":"..."}]}。'
        f"必须精确生成 {target_chapter_count} 个章节计划，从 1 到 {target_chapter_count} 连续编号。"
        "不要只输出第1-5章、第1-30章这样的范围；如果需要分卷，可额外输出 volume_plan。"
        "所有字符串必须用英文双引号包裹，数组和对象的最后一项后面不要加逗号。"
        "除 JSON 字段名外，所有自然语言内容必须是简体中文，不要输出英文大纲。"
        f"{word_requirement}\n\n"
        f"创作需求：\n{user_input}"
    )
    return fallback, system_prompt, user_prompt


def _build_outline_overview_request(
    user_input: str,
    target_chapter_count: int,
    target_words_per_chapter: int | None,
) -> tuple[dict[str, Any], str, str]:
    fallback = _fallback_outline(user_input, target_chapter_count, target_words_per_chapter)
    fallback["chapter_plan"] = {
        "target_words_per_chapter": target_words_per_chapter,
        "volume_plan": _fallback_volume_plan(target_chapter_count),
        "planned_chapters": [],
    }
    word_requirement = (
        f"每章正文目标字数约 {target_words_per_chapter} 字。"
        if target_words_per_chapter
        else "逐章正文篇幅后续按章节任务自然安排。"
    )
    system_prompt = (
        "你是专业长篇小说策划编辑。请只输出一个合法 JSON 对象，不要输出 Markdown。"
        "回复的第一个字符必须是 {，最后一个字符必须是 }。"
        "不要使用注释、尾逗号、中文引号或省略号占位。"
        "JSON 字段名保持英文，所有字段值必须使用简体中文。"
        "本轮只建立长篇项目总纲，不生成逐章章节表。"
    )
    user_prompt = (
        "根据以下创作需求生成小说项目总纲。必须包含字段："
        "genre_profile, bible, style_guide, chapter_plan, plot_threads, foreshadowing, characters。\n"
        "chapter_plan 本轮只输出 volume_plan，不要输出 planned_chapters。"
        "volume_plan 用数组表示，每卷必须包含 volume_number, name, range, focus, milestones。"
        f"总章数为 {target_chapter_count} 章，后续会按每 {OUTLINE_BATCH_SIZE} 章分批生成逐章计划。"
        "volume_plan 的 range 必须覆盖第1章到最后一章。"
        "除 JSON 字段名外，所有自然语言内容必须是简体中文。"
        f"{word_requirement}\n\n"
        f"创作需求：\n{user_input}"
    )
    return fallback, system_prompt, user_prompt


def _build_chapter_batch_request(
    user_input: str,
    overview: dict[str, Any],
    start_chapter: int,
    end_chapter: int,
    target_words_per_chapter: int | None,
    previous_batch_tail: list[dict[str, Any]],
) -> tuple[dict[str, Any], str, str]:
    fallback = {
        "chapter_plan": {
            "planned_chapters": _fallback_chapters_for_range(start_chapter, end_chapter, target_words_per_chapter)
        }
    }
    word_requirement = (
        f"每章增加 target_words 字段，值必须为 {target_words_per_chapter}。"
        if target_words_per_chapter
        else "每章不需要输出正文字数，只写章节任务。"
    )
    overview_context = _compact_outline_context(overview)
    previous_context = json.dumps(previous_batch_tail, ensure_ascii=False)
    system_prompt = (
        "你是专业长篇小说策划编辑。请只输出一个合法 JSON 对象，不要输出 Markdown。"
        "回复的第一个字符必须是 {，最后一个字符必须是 }。"
        "不要使用注释、尾逗号、中文引号或省略号占位。"
        "本轮只生成指定范围内的逐章计划。"
    )
    user_prompt = (
        f"请只生成第 {start_chapter} 章到第 {end_chapter} 章的逐章计划。"
        "输出格式必须为："
        '{"chapter_plan":{"planned_chapters":[{"chapter_number":1,"title":"...","goal":"...","expected_hook":"..."}]}}。'
        f"chapter_number 必须从 {start_chapter} 到 {end_chapter} 连续编号，不能输出范围外章节。"
        "每章 goal 要写清本章的剧情推进和状态变化，expected_hook 要写清章末期待。"
        f"{word_requirement}"
        "所有自然语言内容必须是简体中文。\n\n"
        f"创作需求：\n{user_input}\n\n"
        f"项目总纲：\n{overview_context}\n\n"
        f"上一批最后几章，用于保持承接：\n{previous_context}"
    )
    return fallback, system_prompt, user_prompt


def _merge_segmented_outline(
    overview: dict[str, Any],
    planned_chapters: list[dict[str, Any]],
    target_words_per_chapter: int | None,
) -> dict[str, Any]:
    outline = dict(overview)
    chapter_plan = dict(outline.get("chapter_plan", {}))
    chapter_plan["planned_chapters"] = planned_chapters
    if target_words_per_chapter:
        chapter_plan["target_words_per_chapter"] = target_words_per_chapter
    outline["chapter_plan"] = chapter_plan
    return outline


def _normalize_outline(
    outline: dict[str, Any],
    target_chapter_count: int,
    target_words_per_chapter: int | None,
) -> dict[str, Any]:
    outline = dict(outline)
    outline["chapter_plan"] = normalize_chapter_plan(
        outline.get("chapter_plan", {}),
        target_chapter_count=target_chapter_count,
    )
    if target_words_per_chapter:
        outline["chapter_plan"]["target_words_per_chapter"] = target_words_per_chapter
        for chapter in outline["chapter_plan"].get("planned_chapters", []):
            if isinstance(chapter, dict):
                chapter.setdefault("target_words", target_words_per_chapter)
    return outline


def _run_outline_step(
    progress_callback: ProgressCallback | None,
    label: str,
    index: int,
    total: int,
    action: Callable[[], T],
) -> T:
    if not progress_callback:
        return action()
    progress_callback({"type": "step_started", "label": label, "index": index, "total": total})
    started = perf_counter()
    result = action()
    progress_callback(
        {
            "type": "step_completed",
            "label": label,
            "index": index,
            "total": total,
            "duration_seconds": round(perf_counter() - started, 1),
        }
    )
    return result


def reset_writing_records(memory_dir: str, output_dir: str | None = None) -> None:
    base = Path(memory_dir)
    _clear_directory(base / "chapter_summaries")
    write_json(base / "current_state" / "timeline.json", {"events": []})

    if output_dir:
        _clear_directory(Path(output_dir))


def repair_chapter_plan(memory_dir: str, target_chapter_count: int | None = None) -> dict[str, Any]:
    path = Path(memory_dir) / "outline" / "chapter_plan.json"
    chapter_plan = read_json(path, {"planned_chapters": []})
    repaired = normalize_chapter_plan(chapter_plan, target_chapter_count=target_chapter_count)
    write_json(path, repaired)
    return repaired


def normalize_chapter_plan(
    chapter_plan: dict[str, Any],
    target_chapter_count: int | None = None,
) -> dict[str, Any]:
    planned = chapter_plan.get("planned_chapters")
    if isinstance(planned, list) and _has_integer_chapters(planned):
        normalized = _normalize_planned_chapter_count(chapter_plan, target_chapter_count)
        normalized["volume_plan"] = _normalize_volume_plan(
            normalized.get("volume_plan"),
            target_chapter_count or len(normalized.get("planned_chapters", [])),
        )
        return _attach_volume_info(normalized)

    volumes = _normalize_volume_plan(_extract_volume_plan(chapter_plan), target_chapter_count)
    if not volumes:
        return {"planned_chapters": []}

    planned_chapters = []
    for volume in volumes:
        start, end = _parse_chapter_range(str(volume.get("range", "")))
        if start is None or end is None:
            continue
        milestones = volume.get("milestones", [])
        for chapter_number in range(start, end + 1):
            milestone = _nearest_milestone(chapter_number, milestones)
            planned_chapters.append(
                {
                    "chapter_number": chapter_number,
                    "title": f"第{chapter_number}章",
                    "goal": volume.get("focus", ""),
                    "expected_hook": milestone or "延续本卷核心悬念，并推进下一章期待。",
                    "volume_number": volume.get("volume_number"),
                    "volume_name": volume.get("name", ""),
                    "volume": volume.get("name", ""),
                }
            )

    normalized = {
        "planned_chapters": planned_chapters,
        "volume_plan": volumes,
    }
    return _attach_volume_info(_normalize_planned_chapter_count(normalized, target_chapter_count))


def _write_outline(
    memory_dir: str,
    outline: dict[str, Any],
    user_input: str,
    target_chapter_count: int,
    target_words_per_chapter: int | None,
) -> None:
    base = Path(memory_dir)
    write_json(
        base / "outline" / "outline_request.json",
        {
            "user_input": user_input,
            "chapters": target_chapter_count,
            "target_words_per_chapter": target_words_per_chapter,
        },
    )
    genre_profile = outline.get("genre_profile", {})
    if genre_profile:
        write_json(base / "genre_profile.json", genre_profile)

    bible = outline.get("bible", "")
    if isinstance(bible, dict):
        bible = _dict_to_md("Story Bible", bible)
    if bible:
        (base / "bible.md").write_text(str(bible), encoding="utf-8")

    style_guide = outline.get("style_guide", "")
    if isinstance(style_guide, dict):
        style_guide = _dict_to_md("Style Guide", style_guide)
    if style_guide:
        (base / "style_guide.md").write_text(str(style_guide), encoding="utf-8")

    chapter_plan = normalize_chapter_plan(outline.get("chapter_plan", {"planned_chapters": []}))
    if target_words_per_chapter:
        chapter_plan["target_words_per_chapter"] = target_words_per_chapter
        for chapter in chapter_plan.get("planned_chapters", []):
            if isinstance(chapter, dict):
                chapter.setdefault("target_words", target_words_per_chapter)
    write_json(base / "outline" / "chapter_plan.json", chapter_plan)
    write_json(base / "current_state" / "plot_threads.json", _normalize_list_container(outline.get("plot_threads", {}), "threads"))
    write_json(base / "current_state" / "foreshadowing.json", _normalize_list_container(outline.get("foreshadowing", {}), "items"))
    write_json(base / "current_state" / "characters.json", _normalize_list_container(outline.get("characters", {}), "characters"))


def save_outline_request(
    memory_dir: str,
    user_input: str,
    chapters: int = 30,
    target_words_per_chapter: int | None = 3000,
) -> None:
    write_json(
        Path(memory_dir) / "outline" / "outline_request.json",
        {
            "user_input": user_input,
            "chapters": chapters,
            "target_words_per_chapter": target_words_per_chapter,
        },
    )


def _clear_directory(path: Path) -> None:
    if not path.exists():
        path.mkdir(parents=True, exist_ok=True)
        return
    for item in path.iterdir():
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()


def _normalize_list_container(value: Any, key: str) -> dict[str, list[Any]]:
    if isinstance(value, dict):
        items = value.get(key)
        if isinstance(items, list):
            return {key: items}
        if items:
            return {key: [items]}
        collected = []
        for item_key, item_value in value.items():
            if item_key == key:
                continue
            if isinstance(item_value, list):
                collected.extend(item_value)
            elif isinstance(item_value, dict):
                collected.append({"name": item_key, **item_value})
            elif item_value:
                collected.append({"name": item_key, "detail": item_value})
        return {key: collected}
    if isinstance(value, list):
        return {key: value}
    if value:
        return {key: [value]}
    return {key: []}


def _chapter_batches(target_chapter_count: int, batch_size: int) -> list[tuple[int, int]]:
    return [
        (start, min(start + batch_size - 1, target_chapter_count))
        for start in range(1, target_chapter_count + 1, batch_size)
    ]


def _compact_outline_context(overview: dict[str, Any]) -> str:
    context = {
        "genre_profile": overview.get("genre_profile", {}),
        "bible": overview.get("bible", ""),
        "style_guide": overview.get("style_guide", ""),
        "volume_plan": overview.get("chapter_plan", {}).get("volume_plan", []),
        "plot_threads": overview.get("plot_threads", {}),
        "foreshadowing": overview.get("foreshadowing", {}),
        "characters": overview.get("characters", {}),
    }
    return json.dumps(context, ensure_ascii=False)


def _fallback_outline(
    user_input: str,
    target_chapter_count: int = 30,
    target_words_per_chapter: int | None = None,
) -> dict[str, Any]:
    return {
        "genre_profile": {
            "primary_genre": "general",
            "secondary_genres": [],
            "reader_promise": "持续推进主线、角色关系和章末期待。",
            "must_have": ["明确戏剧任务", "场景状态变化", "章末期待"],
            "avoid": ["水章", "解释型对白", "角色无动机行动"],
            "chapter_check_focus": ["本章是否发生不可逆变化", "角色选择是否符合目标与底线"],
        },
        "bible": (
            "# Story Bible\n\n"
            f"## 创作需求\n\n{user_input}\n\n"
            "## 核心规则\n\n- 设定以后续大纲和正文为准。\n- 不直接复刻受版权保护作品。\n"
        ),
        "style_guide": (
            "# Style Guide\n\n"
            "- 口语化、自然、克制，像人在讲故事。\n"
            "- 多用动作、对白和现场细节。\n"
            "- 不要生成无关剧情的重复描写。\n"
            "- 避免咬文嚼字、空泛抒情和解释型对白。\n"
            "- 不要大量的并列句和否定又肯定的句子。\n"
            "- 不要频繁使用“仿佛、像是、某种、命运、灵魂、深处、无声地、微微、骤然、复杂情绪”等 AI 腔词。\n"
            "- 情绪尽量用动作、停顿、物件和环境细节带出来，不要每段都总结心理。\n"
        ),
        "chapter_plan": {
            "target_words_per_chapter": target_words_per_chapter,
            "planned_chapters": _fallback_chapters(target_chapter_count, target_words_per_chapter),
        },
        "plot_threads": {"threads": [{"name": "主线", "status": "planned", "last_update": user_input}]},
        "foreshadowing": {"items": []},
        "characters": {"characters": []},
    }


def _fallback_volume_plan(target_chapter_count: int) -> list[dict[str, Any]]:
    volumes = []
    for index, (start, end) in enumerate(_chapter_batches(target_chapter_count, OUTLINE_BATCH_SIZE), start=1):
        volumes.append(
            {
                "volume_number": index,
                "name": f"第{index}卷",
                "range": f"{start}-{end}",
                "focus": "推进主线阶段目标，制造关键转折，并维持连载期待。",
                "milestones": [
                    f"第{start}章：开启本阶段任务。",
                    f"第{end}章：完成阶段转折，并抛出下一阶段悬念。",
                ],
            }
        )
    return volumes


def _dict_to_md(title: str, data: dict[str, Any]) -> str:
    lines = [f"# {title}", ""]
    for key, value in data.items():
        lines.append(f"## {key}")
        lines.append("")
        if isinstance(value, list):
            lines.extend(f"- {item}" for item in value)
        else:
            lines.append(str(value))
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _has_integer_chapters(planned: list[dict[str, Any]]) -> bool:
    return all(isinstance(item, dict) and isinstance(item.get("chapter_number"), int) for item in planned)


def _extract_volume_plan(chapter_plan: dict[str, Any]) -> list[dict[str, Any]]:
    volumes = chapter_plan.get("volume_plan")
    if isinstance(volumes, list):
        return volumes

    extracted = []
    for key, value in chapter_plan.items():
        if not isinstance(value, dict):
            continue
        if "range" not in value and "focus" not in value:
            continue
        volume = dict(value)
        volume.setdefault("name", key)
        extracted.append(volume)
    return extracted


def _normalize_volume_plan(value: Any, target_chapter_count: int | None = None) -> list[dict[str, Any]]:
    volumes = value if isinstance(value, list) else []
    normalized = []
    for index, item in enumerate(volumes, start=1):
        if not isinstance(item, dict):
            continue
        volume = dict(item)
        volume_number = volume.get("volume_number")
        if not isinstance(volume_number, int):
            volume_number = index
        volume["volume_number"] = volume_number
        volume.setdefault("name", f"第{volume_number}卷")
        if "range" not in volume and target_chapter_count:
            start = (index - 1) * OUTLINE_BATCH_SIZE + 1
            end = min(index * OUTLINE_BATCH_SIZE, target_chapter_count)
            volume["range"] = f"{start}-{end}"
        volume.setdefault("focus", "")
        volume.setdefault("milestones", [])
        normalized.append(volume)

    if not normalized and target_chapter_count and target_chapter_count > OUTLINE_BATCH_SIZE:
        return _fallback_volume_plan(target_chapter_count)
    return normalized


def _attach_volume_info(chapter_plan: dict[str, Any]) -> dict[str, Any]:
    volumes = _normalize_volume_plan(chapter_plan.get("volume_plan"))
    if not volumes:
        return chapter_plan

    planned = []
    for chapter in chapter_plan.get("planned_chapters", []):
        if not isinstance(chapter, dict):
            continue
        item = dict(chapter)
        number = item.get("chapter_number")
        volume = _volume_for_chapter(volumes, number if isinstance(number, int) else None)
        if volume:
            item["volume_number"] = volume.get("volume_number")
            item["volume_name"] = volume.get("name", "")
            item["volume"] = volume.get("name", "")
        planned.append(item)

    result = dict(chapter_plan)
    result["volume_plan"] = volumes
    result["planned_chapters"] = planned
    return result


def _volume_for_chapter(volumes: list[dict[str, Any]], chapter_number: int | None) -> dict[str, Any] | None:
    if chapter_number is None:
        return None
    for volume in volumes:
        start, end = _parse_chapter_range(str(volume.get("range", "")))
        if start is not None and end is not None and start <= chapter_number <= end:
            return volume
    return None


def _parse_chapter_range(text: str) -> tuple[int | None, int | None]:
    match = re.search(r"第?\s*(\d+)\s*章?\s*[-到至~—－]\s*第?\s*(\d+)\s*章?", text)
    if match:
        return int(match.group(1)), int(match.group(2))
    match = re.search(r"第\s*(\d+)\s*章", text)
    if match:
        number = int(match.group(1))
        return number, number
    return None, None


def _nearest_milestone(chapter_number: int, milestones: list[Any]) -> str:
    selected = ""
    selected_number = -1
    for milestone in milestones:
        text = str(milestone)
        match = re.search(r"第\s*(\d+)\s*章", text)
        if not match:
            continue
        number = int(match.group(1))
        if number <= chapter_number and number > selected_number:
            selected = text
            selected_number = number
    return selected


def _normalize_planned_chapter_count(
    chapter_plan: dict[str, Any],
    target_chapter_count: int | None,
) -> dict[str, Any]:
    if not target_chapter_count:
        return chapter_plan

    planned = chapter_plan.get("planned_chapters", [])
    if not isinstance(planned, list):
        planned = []

    normalized = []
    by_number = {
        item.get("chapter_number"): item
        for item in planned
        if isinstance(item, dict) and isinstance(item.get("chapter_number"), int)
    }
    for chapter_number in range(1, target_chapter_count + 1):
        item = dict(by_number.get(chapter_number, {}))
        item.setdefault("chapter_number", chapter_number)
        item.setdefault("title", f"第{chapter_number}章")
        item.setdefault("goal", _nearest_existing_goal(chapter_number, planned))
        item.setdefault("expected_hook", "延续主线悬念，并推进下一章期待。")
        normalized.append(item)

    result = dict(chapter_plan)
    result["planned_chapters"] = normalized
    return result


def _nearest_existing_goal(chapter_number: int, planned: list[Any]) -> str:
    selected_goal = "推进主线，制造新的情节变化。"
    selected_distance = 10**9
    for item in planned:
        if not isinstance(item, dict):
            continue
        number = item.get("chapter_number")
        goal = item.get("goal")
        if not isinstance(number, int) or not goal:
            continue
        distance = abs(number - chapter_number)
        if distance < selected_distance:
            selected_distance = distance
            selected_goal = str(goal)
    return selected_goal


def _fallback_chapters(target_chapter_count: int, target_words_per_chapter: int | None = None) -> list[dict[str, Any]]:
    chapters = _fallback_chapters_for_range(1, target_chapter_count, target_words_per_chapter)
    if chapters:
        chapters[0]["title"] = "开端"
        chapters[0]["goal"] = "建立主角处境，投放主线线索。"
        chapters[0]["expected_hook"] = "出现更大的未解问题。"
    if len(chapters) > 1:
        chapters[1]["title"] = "追索"
        chapters[1]["goal"] = "让主角主动追查，并遭遇第一次阻碍。"
        chapters[1]["expected_hook"] = "线索指向更危险的人或地点。"
    return chapters


def _fallback_chapters_for_range(
    start_chapter: int,
    end_chapter: int,
    target_words_per_chapter: int | None = None,
) -> list[dict[str, Any]]:
    chapters = []
    for chapter_number in range(start_chapter, end_chapter + 1):
        chapter = {
            "chapter_number": chapter_number,
            "title": f"第{chapter_number}章",
            "goal": "推进主线，制造新的情节变化。",
            "expected_hook": "延续主线悬念，并推进下一章期待。",
        }
        if target_words_per_chapter:
            chapter["target_words"] = target_words_per_chapter
        chapters.append(chapter)
    return chapters
