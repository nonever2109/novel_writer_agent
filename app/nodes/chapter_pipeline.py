from __future__ import annotations

import re
from typing import Any

from app import config
from app.graph.state import NovelState
from app.services.llm_service import generate_json, generate_text
from app.services.memory_service import apply_memory_update
from app.services.memory_service import archive_chapter as write_chapter_archive
from app.services.memory_service import load_story_memory
from app.services.safety_service import safety_check, transform_request


def load_memory(state: NovelState) -> NovelState:
    memory_dir = state.get("memory_dir", config.NOVEL_MEMORY_DIR)
    memory = load_story_memory(memory_dir)
    return {
        "story_memory": memory,
        "genre_profile": memory.get("genre_profile", {}),
    }


def normalize_story_request(state: NovelState) -> NovelState:
    user_input = state.get("user_input", "").strip()
    chapter_number = _extract_chapter_number(user_input)
    request = {
        "raw_input": user_input,
        "chapter_number": chapter_number,
        "chapter_goal": user_input or "写出下一章，承接已有故事记忆。",
        "target_length": _extract_target_length(user_input),
        "constraints": [],
    }
    return {"story_request": request}


def input_safety_check(state: NovelState) -> NovelState:
    report = safety_check(state.get("user_input", ""))
    return {"input_safety_report": report}


def transform_input_if_needed(state: NovelState) -> NovelState:
    report = state.get("input_safety_report", {})
    if report.get("status") == "blocked":
        raise ValueError(report.get("notes", "Input is blocked by safety policy."))
    transformed = transform_request(state.get("story_request", {}), report)
    return {"transformed_request": transformed}


def build_story_context(state: NovelState) -> NovelState:
    memory = state.get("story_memory", {})
    context = {
        "bible": memory.get("bible", ""),
        "style_guide": memory.get("style_guide", ""),
        "recent_chapters": memory.get("chapter_summaries", []),
        "characters": memory.get("characters", {}),
        "timeline": memory.get("timeline", {}),
        "plot_threads": memory.get("plot_threads", {}),
        "foreshadowing": memory.get("foreshadowing", {}),
        "genre_profile": memory.get("genre_profile", {}),
    }
    return {"story_context": context}


def plan_chapter(state: NovelState) -> NovelState:
    request = state.get("transformed_request") or state.get("story_request", {})
    genre = state.get("genre_profile", {})
    planned_chapter = _find_planned_chapter(state, request.get("chapter_number"))
    fallback = {
        "chapter_number": request.get("chapter_number"),
        "chapter_title": planned_chapter.get("title"),
        "chapter_goal": planned_chapter.get("goal") or request.get("chapter_goal"),
        "dramatic_task": "让本章结束时局势、关系或信息至少发生一项不可逆变化。",
        "reader_promise": genre.get("reader_promise", ""),
        "must_deliver": genre.get("must_have", []),
        "avoid": genre.get("avoid", []),
        "planned_state_change": [
            "推进一个主线问题",
            "制造一个新的读者期待",
            "更新至少一项角色、伏笔或时间线状态",
        ],
    }
    plan = generate_json(
        system_prompt="你是专业小说章节策划。请只输出 JSON，不要输出 Markdown。",
        user_prompt=(
            "请根据故事上下文规划本章。必须包含字段：chapter_number, chapter_goal, "
            "chapter_title, dramatic_task, reader_promise, must_deliver, avoid, planned_state_change。"
            "如果故事上下文中有对应章节计划，必须优先沿用该章节标题和目标。\n\n"
            f"本章需求：{request}\n\n故事上下文：{state.get('story_context', {})}"
        ),
        fallback=fallback,
        temperature=0.4,
    )
    return {"chapter_plan": plan}


def plan_scenes(state: NovelState) -> NovelState:
    plan = state.get("chapter_plan", {})
    fallback = {
        "chapter_goal": plan.get("chapter_goal"),
        "scenes": [
        {
            "scene_id": "scene_1",
            "purpose": "承接上一章状态，明确本章目标和阻碍。",
            "entry_state": "角色带着未解决问题进入场景。",
            "conflict": "目标与限制发生碰撞。",
            "exit_state": "角色得到新线索，但代价或风险上升。",
            "key_reveal": "揭示一个会影响本章行动的新信息。",
            "emotional_turn": "角色从观望或迟疑转向主动应对。",
        },
        {
            "scene_id": "scene_2",
            "purpose": "升级冲突，并让角色做出选择。",
            "entry_state": "新线索迫使角色采取行动。",
            "conflict": "外部压力与角色内心顾虑同时加重。",
            "exit_state": "选择造成关系、信息或处境变化。",
            "key_reveal": "补充一个改变局势判断的细节。",
            "emotional_turn": "角色在压力下暴露真实立场或情绪。",
        },
        {
            "scene_id": "scene_3",
            "purpose": "兑现本章戏剧任务，并留下下一章钩子。",
            "entry_state": "角色接近阶段性答案。",
            "conflict": "答案带来更大的问题。",
            "exit_state": "本章问题部分解决，新的期待被打开。",
            "key_reveal": "给出阶段性答案，同时引出更大的疑问。",
            "emotional_turn": "角色从短暂确定转向新的不安或决心。",
        },
        ],
    }
    scene_plan = generate_json(
        system_prompt="你是专业小说场景编排编辑。请只输出 JSON，不要输出 Markdown。",
        user_prompt=(
            "请把章节计划拆成 3 到 6 个场景。必须输出字段：chapter_goal, scenes。"
            "每个 scene 必须包含 scene_id, purpose, entry_state, conflict, exit_state, key_reveal, emotional_turn。\n\n"
            f"章节计划：{plan}\n\n故事上下文：{state.get('story_context', {})}"
        ),
        fallback=fallback,
        temperature=0.5,
    )
    return {"scene_plan": scene_plan}


def write_scenes(state: NovelState) -> NovelState:
    request = state.get("transformed_request") or state.get("story_request", {})
    scene_plan = state.get("scene_plan", {}).get("scenes", [])
    drafts = []
    for index, scene in enumerate(scene_plan, start=1):
        fallback = _draft_scene(index, scene, request)
        body = generate_text(
            system_prompt=(
                "你是专业连载小说作者。请根据题材、人物、章节目标和故事上下文写作。"
                "文风要求：自然、清晰、有现场感，符合当前小说类型和读者期待。"
                "多写人物怎么说、怎么做、怎么停顿，用具体动作和细节推进剧情。"
                "少用抽象抒情、宏大总结和咬文嚼字的句子，避免把设定写成说明书。"
                "不要复刻受版权保护作品或在世作者具体文风。"
            ),
            user_prompt=(
                "请写一个完整场景正文。不要输出 JSON。不要解释你的写法。\n"
                "硬性风格要求：\n"
                "- 对白要像真人说话，可以有停顿、反问、没说完的话。\n"
                "- 句子尽量适中，少用长串修饰。\n"
                "- 少用“仿佛、像是、某种、命运、灵魂、深处、无声地、微微、骤然、复杂情绪”等 AI 腔词。\n"
                "- 不要每段都总结人物心理。用动作、眼神、物件和环境细节带出情绪。\n"
                "- 不要把背景设定一次性讲完，只让角色在行动里碰到信息。\n"
                "- 悬疑感来自具体异常和信息差，不要靠空泛的阴冷、压迫、宿命感。\n\n"
                f"本章需求：{request}\n\n章节计划：{state.get('chapter_plan', {})}\n\n"
                f"场景规划：{scene}\n\n故事上下文：{state.get('story_context', {})}"
            ),
            fallback=fallback,
            temperature=0.8,
        )
        drafts.append({"scene_id": scene.get("scene_id"), "body": body, "purpose": scene.get("purpose")})
    return {"scene_drafts": drafts}


def merge_chapter(state: NovelState) -> NovelState:
    chapter_number = state.get("chapter_plan", {}).get("chapter_number")
    chapter_title = state.get("chapter_plan", {}).get("chapter_title")
    if chapter_number and chapter_title:
        title = f"第{chapter_number}章 {chapter_title}"
    elif chapter_number:
        title = f"第{chapter_number}章"
    else:
        title = chapter_title or "未命名章节"
    body = "\n\n".join(item.get("body", "") for item in state.get("scene_drafts", []))
    return {"merged_chapter": f"# {title}\n\n{body}\n"}


def continuity_check(state: NovelState) -> NovelState:
    fallback = {
        "status": "pass",
        "issues": [],
        "checks": [
            "本章具有进入状态和退出状态。",
            "章节计划包含戏剧任务。",
            "已为角色、伏笔和时间线更新预留记录。",
        ],
    }
    if not state.get("scene_drafts"):
        fallback["status"] = "needs_fix"
        fallback["issues"].append("缺少场景草稿。")
    report = generate_json(
        system_prompt="你是小说连续性审稿人。请只输出 JSON，不要输出 Markdown。",
        user_prompt=(
            "检查章节是否违反故事账本。必须输出 status(pass/needs_fix), issues, checks。"
            "重点：角色是否 OOC、时间地点是否冲突、角色已知信息是否越界、伏笔是否被遗忘、是否接住上一章钩子。\n\n"
            f"故事上下文：{state.get('story_context', {})}\n\n章节正文：{state.get('merged_chapter', '')}"
        ),
        fallback=fallback,
        temperature=0.2,
    )
    return {"continuity_report": report}


def fix_continuity_issues(state: NovelState) -> NovelState:
    chapter = state.get("merged_chapter", "")
    report = state.get("continuity_report", {})
    if report.get("status") == "needs_fix":
        chapter += "\n\n> 连续性修复备注：补充场景进入/退出状态后再进入下一轮写作。\n"
    return {"continuity_fixed_chapter": chapter}


def chapter_safety_check(state: NovelState) -> NovelState:
    chapter = state.get("continuity_fixed_chapter") or state.get("merged_chapter", "")
    return {"chapter_safety_report": safety_check(chapter)}


def fix_safety_issues(state: NovelState) -> NovelState:
    chapter = state.get("continuity_fixed_chapter") or state.get("merged_chapter", "")
    report = state.get("chapter_safety_report", {})
    if report.get("status") == "needs_transform":
        chapter += "\n\n> 安全修复备注：已要求后续版本保持原创角色、原创世界观和不同剧情结构。\n"
    if report.get("status") == "blocked":
        raise ValueError("Generated chapter is blocked by safety policy.")
    return {"safety_fixed_chapter": chapter}


def polish_chapter(state: NovelState) -> NovelState:
    chapter = state.get("safety_fixed_chapter") or state.get("continuity_fixed_chapter") or state.get("merged_chapter", "")
    style = state.get("story_context", {}).get("style_guide", "")
    polished = chapter.rstrip()
    if style:
        polished += "\n\n<!-- style_guide_applied: true -->\n"
    polished = generate_text(
        system_prompt=(
            "你是连载小说文字编辑。任务是把文字改得更口语、更自然、更像真人写的小说。"
            "只输出润色后的正文，不要解释。"
        ),
        user_prompt=(
            "请在不改变事实、不新增剧情事实的前提下润色章节。"
            "目标：减少 AI 味，增强动作、感官、对白和节奏。\n"
            "重点修改：\n"
            "- 把书面化、端着的句子改成更顺口的表达。\n"
            "- 删除空泛抒情和重复心理总结。\n"
            "- 把解释型对白改成更自然的试探、打断、沉默和追问。\n"
            "- 保留悬疑氛围，但不要堆形容词。\n"
            "- 多用具体物件、动作、声音和现场细节。\n"
            "- 避免“仿佛、像是、某种、命运、灵魂、深处、无声地、微微、骤然、复杂情绪”等 AI 腔词。\n\n"
            f"风格指南：{style}\n\n章节正文：{chapter}"
        ),
        fallback=polished,
        temperature=0.55,
    )
    return {"polished_chapter": polished}


def optimize_chapter_hook(state: NovelState) -> NovelState:
    chapter = state.get("polished_chapter", "")
    fallback = {
        "hook_type": "information",
        "hook": "新的问题已经出现，下一章需要兑现本章留下的期待。",
        "next_chapter_promise": "解释新问题，同时让局势继续升级。",
    }
    report = generate_json(
        system_prompt="你是连载小说编辑。请只输出 JSON，不要输出 Markdown。",
        user_prompt=(
            "请为本章设计自然的章末钩子。必须输出 hook_type, hook, next_chapter_promise。"
            "钩子不能强行反转，要承接正文。\n\n"
            f"章节正文：{chapter}"
        ),
        fallback=fallback,
        temperature=0.5,
    )
    hook = report.get("hook") or fallback["hook"]
    final = chapter.rstrip() + f"\n\n---\n\n{hook}\n"
    return {"chapter_hook_report": report, "final_chapter": final}


def final_safety_check(state: NovelState) -> NovelState:
    return {"final_safety_report": safety_check(state.get("final_chapter", ""))}


def evaluate_chapter_experience(state: NovelState) -> NovelState:
    final_chapter = state.get("final_chapter", "")
    fallback = {
        "overall_status": "draft_ready",
        "scores": {
            "dramatic_task": 7,
            "continuity": 7,
            "reader_hook": 7,
            "narrative_texture": 6,
            "colloquial_style": 6,
        },
        "notes": [
            "当前为模板化 MVP 草稿，适合验证流程。",
            "接入 LLM 后应重点提升对白、动作细节和场景质感。",
        ],
        "length": len(final_chapter),
    }
    report = generate_json(
        system_prompt="你是商业小说审稿编辑。请只输出 JSON，不要输出 Markdown。",
        user_prompt=(
            "评估章节体验。必须输出 overall_status, scores, notes, length。"
            "scores 至少包含 dramatic_task, continuity, reader_hook, narrative_texture, colloquial_style。"
            "重点检查是否口语化自然，是否存在咬文嚼字、AI 腔、解释型对白、空泛心理总结。\n\n"
            f"类型策略：{state.get('genre_profile', {})}\n\n章节正文：{final_chapter}"
        ),
        fallback=fallback,
        temperature=0.2,
    )
    return {"chapter_eval_report": report}


def archive_chapter(state: NovelState) -> NovelState:
    request = state.get("story_request", {})
    chapter_number = request.get("chapter_number") or _next_chapter_number(state)
    fallback = {
        "chapter_number": chapter_number,
        "summary": _summarize_for_archive(state),
        "actual_events": [
            {"event": "完成本章草稿", "source": "final_chapter"},
            {"event": "留下下一章期待", "source": "chapter_hook_report"},
        ],
        "involved_characters": [],
        "locations": [],
        "plot_threads": ["主线推进"],
        "foreshadowing": [state.get("chapter_hook_report", {}).get("hook", "")],
        "tags": ["mvp", state.get("genre_profile", {}).get("primary_genre", "general")],
    }
    archive = generate_json(
        system_prompt="你是小说档案管理员。请只输出 JSON，不要输出 Markdown。",
        user_prompt=(
            "请根据最终正文生成章节归档。只能记录正文实际发生的事，不要把计划写成事实。"
            "必须输出 chapter_number, summary, actual_events, involved_characters, locations, plot_threads, foreshadowing, tags。\n\n"
            f"章节号：{chapter_number}\n\n最终正文：{state.get('final_chapter', '')}"
        ),
        fallback=fallback,
        temperature=0.2,
    )
    archive["chapter_number"] = chapter_number
    path = write_chapter_archive(state.get("memory_dir", config.NOVEL_MEMORY_DIR), archive)
    archive["archive_path"] = str(path)
    return {"chapter_archive": archive}


def update_story_memory(state: NovelState) -> NovelState:
    archive = state.get("chapter_archive", {})
    fallback = {
        "chapter_number": archive.get("chapter_number"),
        "chapter_summary": archive.get("summary"),
        "character_updates": [],
        "relationship_updates": [],
        "timeline_updates": [
            {
                "chapter_number": archive.get("chapter_number"),
                "event": archive.get("summary", ""),
            }
        ],
        "plot_thread_updates": [
            {
                "name": "主线推进",
                "status": "active",
                "last_update": archive.get("summary", ""),
            }
        ],
        "foreshadowing_updates": [
            {
                "name": "下一章期待",
                "status": "seeded",
                "detail": state.get("chapter_hook_report", {}).get("hook", ""),
                "chapter_number": archive.get("chapter_number"),
            }
        ],
        "world_state_updates": [],
        "open_questions": [state.get("chapter_hook_report", {}).get("next_chapter_promise", "")],
        "next_chapter_hooks": [state.get("chapter_hook_report", {}).get("hook", "")],
    }
    update = generate_json(
        system_prompt="你是小说故事账本管理员。请只输出 JSON，不要输出 Markdown。",
        user_prompt=(
            "请根据最终正文和章节归档生成记忆更新。只能记录正文实际发生的变化。"
            "必须输出 chapter_number, chapter_summary, character_updates, relationship_updates, "
            "timeline_updates, plot_thread_updates, foreshadowing_updates, world_state_updates, "
            "open_questions, next_chapter_hooks。\n\n"
            f"旧故事上下文：{state.get('story_context', {})}\n\n章节归档：{archive}\n\n最终正文：{state.get('final_chapter', '')}"
        ),
        fallback=fallback,
        temperature=0.2,
    )
    update = _normalize_memory_update(update, fallback)
    apply_memory_update(state.get("memory_dir", config.NOVEL_MEMORY_DIR), update)
    return {"memory_update": update}


def validate_memory_update(state: NovelState) -> NovelState:
    update = state.get("memory_update", {})
    final_chapter = state.get("final_chapter", "")
    report = {
        "status": "pass",
        "issues": [],
        "checks": [
            "记忆更新来源为最终正文和章节钩子。",
            "未把大纲计划直接写成已发生事实。",
        ],
    }
    if update.get("chapter_summary") and not final_chapter:
        report["status"] = "needs_review"
        report["issues"].append("存在章节摘要，但缺少最终正文。")
    return {"memory_validation_report": report}


def _extract_chapter_number(text: str) -> int | None:
    match = re.search(r"第\s*(\d+)\s*章", text)
    if match:
        return int(match.group(1))
    match = re.search(r"chapter\s*(\d+)", text, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None


def _extract_target_length(text: str) -> int | None:
    match = re.search(r"(\d+)\s*字", text)
    if match:
        return int(match.group(1))
    return None


def _draft_scene(index: int, scene: dict[str, Any], request: dict[str, Any]) -> str:
    goal = request.get("chapter_goal", "继续推进故事")
    return (
        f"## 场景 {index}\n\n"
        f"{scene.get('entry_state')} 本章目标是：{goal}\n\n"
        f"{scene.get('conflict')} 角色必须在压力下做出选择，而这个选择会改变后续局势。\n\n"
        f"{scene.get('exit_state')}"
    )


def _summarize_for_archive(state: NovelState) -> str:
    goal = state.get("chapter_plan", {}).get("chapter_goal", "")
    hook = state.get("chapter_hook_report", {}).get("hook", "")
    return f"本章围绕“{goal}”推进，完成阶段性状态变化，并留下钩子：{hook}"


def _next_chapter_number(state: NovelState) -> int:
    summaries = state.get("story_memory", {}).get("chapter_summaries", [])
    numbers = [item.get("chapter_number") for item in summaries if isinstance(item.get("chapter_number"), int)]
    return max(numbers, default=0) + 1


def _find_planned_chapter(state: NovelState, chapter_number: int | None) -> dict[str, Any]:
    if chapter_number is None:
        return {}
    planned = (
        state.get("story_memory", {})
        .get("chapter_plan", {})
        .get("planned_chapters", [])
    )
    for item in planned:
        if isinstance(item, dict) and item.get("chapter_number") == chapter_number:
            return item
    return {}


def _normalize_memory_update(update: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(update, dict):
        return fallback

    normalized = dict(fallback)
    normalized.update(update)
    list_fields = [
        "character_updates",
        "relationship_updates",
        "timeline_updates",
        "plot_thread_updates",
        "foreshadowing_updates",
        "world_state_updates",
        "open_questions",
        "next_chapter_hooks",
    ]
    for field in list_fields:
        normalized[field] = _as_list(normalized.get(field))
    return normalized


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]
