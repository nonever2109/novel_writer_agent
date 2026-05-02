from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.services.json_service import read_json
from app.services.json_service import write_json


RUN_INDEX_FILE = "run_index.json"


def write_run_outputs(state: dict[str, Any], output_dir: str) -> Path:
    run_id = state.get("run_id") or datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = Path(output_dir) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    normalized_state = _normalize_output_texts(state)
    final_chapter = normalized_state.get("final_chapter", "")
    (run_dir / "final_chapter.md").write_text(final_chapter, encoding="utf-8")
    write_json(run_dir / "state.json", _serializable_state(normalized_state))
    write_json(
        run_dir / "reports.json",
        {
            "input_safety_report": state.get("input_safety_report", {}),
            "continuity_report": state.get("continuity_report", {}),
            "chapter_safety_report": state.get("chapter_safety_report", {}),
            "final_safety_report": state.get("final_safety_report", {}),
            "chapter_eval_report": state.get("chapter_eval_report", {}),
            "memory_validation_report": state.get("memory_validation_report", {}),
        },
    )
    _update_run_index(Path(output_dir), run_dir, normalized_state)
    return run_dir


def _serializable_state(state: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in state.items() if key != "story_memory"}


def _normalize_output_texts(state: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(state)
    for key in [
        "merged_chapter",
        "continuity_fixed_chapter",
        "safety_fixed_chapter",
        "polished_chapter",
        "final_chapter",
    ]:
        value = normalized.get(key)
        if isinstance(value, str):
            normalized[key] = _restore_literal_newlines(value)
    return normalized


def _restore_literal_newlines(text: str) -> str:
    return (
        text.replace("\\r\\n", "\n")
        .replace("\\n", "\n")
        .replace("\\r", "\n")
        .replace('\\"', '"')
    )


def _update_run_index(output_dir: Path, run_dir: Path, state: dict[str, Any]) -> None:
    index_path = output_dir / RUN_INDEX_FILE
    index = read_json(index_path, {"runs": [], "chapter_runs": {}})
    if not isinstance(index, dict):
        index = {"runs": [], "chapter_runs": {}}

    runs = index.setdefault("runs", [])
    if not isinstance(runs, list):
        runs = []
        index["runs"] = runs

    chapter_runs = index.setdefault("chapter_runs", {})
    if not isinstance(chapter_runs, dict):
        chapter_runs = {}
        index["chapter_runs"] = chapter_runs

    run_id = run_dir.name
    chapter_number = _result_chapter_number(state)
    created_at = _utc_now()
    record = {
        "run_id": run_id,
        "path": str(run_dir),
        "chapter_number": chapter_number,
        "chapter_title": state.get("chapter_plan", {}).get("chapter_title"),
        "summary": state.get("chapter_archive", {}).get("summary", ""),
        "status": state.get("chapter_eval_report", {}).get("overall_status", ""),
        "created_at": created_at,
    }

    runs[:] = [item for item in runs if not (isinstance(item, dict) and item.get("run_id") == run_id)]
    runs.append(record)

    if isinstance(chapter_number, int):
        key = str(chapter_number)
        records = chapter_runs.setdefault(key, [])
        if not isinstance(records, list):
            records = []
            chapter_runs[key] = records
        records[:] = [item for item in records if not (isinstance(item, dict) and item.get("run_id") == run_id)]
        records.append(record)

    write_json(index_path, index)


def _result_chapter_number(state: dict[str, Any]) -> int | None:
    candidates = [
        state.get("chapter_archive", {}).get("chapter_number"),
        state.get("story_request", {}).get("chapter_number"),
        state.get("chapter_plan", {}).get("chapter_number"),
    ]
    for candidate in candidates:
        if isinstance(candidate, int):
            return candidate
    return None


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
