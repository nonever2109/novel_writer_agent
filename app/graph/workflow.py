from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from time import perf_counter

from app.graph.state import NovelState
from app.nodes.chapter_pipeline import archive_chapter
from app.nodes.chapter_pipeline import build_story_context
from app.nodes.chapter_pipeline import chapter_safety_check
from app.nodes.chapter_pipeline import continuity_check
from app.nodes.chapter_pipeline import evaluate_chapter_experience
from app.nodes.chapter_pipeline import final_safety_check
from app.nodes.chapter_pipeline import fix_continuity_issues
from app.nodes.chapter_pipeline import fix_safety_issues
from app.nodes.chapter_pipeline import input_safety_check
from app.nodes.chapter_pipeline import load_memory
from app.nodes.chapter_pipeline import normalize_story_request
from app.nodes.chapter_pipeline import optimize_chapter_hook
from app.nodes.chapter_pipeline import plan_chapter
from app.nodes.chapter_pipeline import polish_chapter
from app.nodes.chapter_pipeline import transform_input_if_needed
from app.nodes.chapter_pipeline import update_story_memory
from app.nodes.chapter_pipeline import validate_memory_update
from app.nodes.chapter_pipeline import write_chapter_draft


Node = Callable[[NovelState], NovelState]
ProgressCallback = Callable[[dict], None]


WORKFLOW_LABELS = {
    "load_memory": "读取故事记忆",
    "normalize_story_request": "解析章节需求",
    "input_safety_check": "检查输入安全",
    "transform_input_if_needed": "调整写作请求",
    "build_story_context": "整理故事上下文",
    "plan_chapter": "规划章节结构",
    "write_chapter_draft": "生成章节正文",
    "continuity_check": "检查故事连续性",
    "fix_continuity_issues": "修正连续性问题",
    "chapter_safety_check": "检查章节安全",
    "fix_safety_issues": "修正安全问题",
    "polish_chapter": "润色章节",
    "optimize_chapter_hook": "生成章末钩子",
    "final_safety_check": "最终安全检查",
    "evaluate_chapter_experience": "评估章节体验",
    "archive_chapter": "归档章节摘要",
    "update_story_memory": "更新故事记忆",
    "validate_memory_update": "校验记忆更新",
}


WORKFLOW: list[tuple[str, Node]] = [
    ("load_memory", load_memory),
    ("normalize_story_request", normalize_story_request),
    ("input_safety_check", input_safety_check),
    ("transform_input_if_needed", transform_input_if_needed),
    ("build_story_context", build_story_context),
    ("plan_chapter", plan_chapter),
    ("write_chapter_draft", write_chapter_draft),
    ("continuity_check", continuity_check),
    ("fix_continuity_issues", fix_continuity_issues),
    ("chapter_safety_check", chapter_safety_check),
    ("fix_safety_issues", fix_safety_issues),
    ("polish_chapter", polish_chapter),
    ("optimize_chapter_hook", optimize_chapter_hook),
    ("final_safety_check", final_safety_check),
    ("evaluate_chapter_experience", evaluate_chapter_experience),
    ("archive_chapter", archive_chapter),
    ("update_story_memory", update_story_memory),
    ("validate_memory_update", validate_memory_update),
]


def run_workflow(initial_state: NovelState, progress_callback: ProgressCallback | None = None) -> NovelState:
    state: NovelState = {
        "run_id": datetime.now().strftime("%Y%m%d_%H%M%S"),
        "workflow_trace": [],
        **initial_state,
    }
    total = len(WORKFLOW)
    for index, (name, node) in enumerate(WORKFLOW, start=1):
        started_at = perf_counter()
        print(f"[workflow] {index}/{total} {name}", flush=True)
        _emit_progress(progress_callback, "step_started", name, index, total)
        patch = node(state)
        state.update(patch)
        duration = round(perf_counter() - started_at, 3)
        state.setdefault("workflow_trace", []).append(
            {
                "node": name,
                "updated_keys": sorted(patch.keys()),
                "duration_seconds": duration,
            }
        )
        _emit_progress(progress_callback, "step_completed", name, index, total, duration)
    return state


def _emit_progress(
    progress_callback: ProgressCallback | None,
    event_type: str,
    node: str,
    index: int,
    total: int,
    duration_seconds: float | None = None,
) -> None:
    if not progress_callback:
        return
    event = {
        "type": event_type,
        "step": node,
        "label": WORKFLOW_LABELS.get(node, node),
        "index": index,
        "total": total,
    }
    if duration_seconds is not None:
        event["duration_seconds"] = duration_seconds
    progress_callback(event)
