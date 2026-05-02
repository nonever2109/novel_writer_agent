from typing import Any, TypedDict


class NovelState(TypedDict, total=False):
    # Input and run metadata
    user_input: str
    memory_dir: str
    output_dir: str
    run_id: str

    # Story memory and strategy
    story_memory: dict[str, Any]
    genre_profile: dict[str, Any]
    story_context: dict[str, Any]

    # Planning
    story_request: dict[str, Any]
    input_safety_report: dict[str, Any]
    transformed_request: dict[str, Any]
    chapter_plan: dict[str, Any]
    scene_plan: dict[str, Any]

    # Drafting
    scene_drafts: list[dict[str, Any]]
    merged_chapter: str
    continuity_report: dict[str, Any]
    continuity_fixed_chapter: str
    chapter_safety_report: dict[str, Any]
    safety_fixed_chapter: str
    polished_chapter: str
    chapter_hook_report: dict[str, Any]
    final_safety_report: dict[str, Any]
    final_chapter: str

    # Evaluation and memory
    chapter_eval_report: dict[str, Any]
    chapter_archive: dict[str, Any]
    memory_update: dict[str, Any]
    memory_validation_report: dict[str, Any]

    # Output
    output_path: str
    workflow_trace: list[dict[str, Any]]
