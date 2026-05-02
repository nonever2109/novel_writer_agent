from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.services.output_service import RUN_INDEX_FILE


def result_chapter_number(result: dict[str, Any]) -> int | None:
    candidates = [
        result.get("chapter_archive", {}).get("chapter_number"),
        result.get("story_request", {}).get("chapter_number"),
        result.get("chapter_plan", {}).get("chapter_number"),
    ]
    for candidate in candidates:
        if isinstance(candidate, int):
            return candidate
    return None


def find_latest_result_for_chapter(output_dir: str, chapter_number: Any) -> tuple[dict[str, Any] | None, str | None]:
    if not isinstance(chapter_number, int):
        return None, None

    base = Path(output_dir)
    if not base.exists():
        return None, None

    indexed = _find_latest_result_from_index(base, chapter_number)
    if indexed[0]:
        return indexed

    return _find_latest_result_by_scanning(base, chapter_number)


def list_run_summaries(output_dir: str) -> list[dict[str, Any]]:
    base = Path(output_dir)
    if not base.exists():
        return []

    indexed = _list_run_summaries_from_index(base)
    if indexed:
        return indexed

    return _list_run_summaries_by_scanning(base)


def export_final_chapter_text(output_dir: str, project_name: str, chapter_number: int) -> dict[str, Any]:
    result, output_path = find_latest_result_for_chapter(output_dir, chapter_number)
    if not result:
        raise ValueError(f"Chapter result not found: {chapter_number}")

    final_chapter = result.get("final_chapter")
    if not isinstance(final_chapter, str) or not final_chapter.strip():
        raise ValueError(f"Final chapter is empty: {chapter_number}")

    chapter_title = _chapter_title(result, chapter_number)
    text = markdown_to_plain_text(final_chapter)
    export_dir = Path(output_dir).parent / _safe_path_part(project_name or "未命名小说")
    export_dir.mkdir(parents=True, exist_ok=True)
    export_path = export_dir / f"{chapter_number}-{_safe_path_part(chapter_title)}.txt"
    export_path.write_text(text, encoding="utf-8")
    _mark_run_finalized(Path(output_dir), output_path, chapter_number, export_path)
    return {
        "status": "ok",
        "path": str(export_path),
        "chapter_number": chapter_number,
        "chapter_title": chapter_title,
        "source_output_path": output_path,
        "text_length": len(text),
    }


def markdown_to_plain_text(markdown: str) -> str:
    text = restore_literal_newlines(markdown)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    lines = []
    in_fence = False
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence and re.fullmatch(r"\s*[-*_]{3,}\s*", line):
            continue
        if not in_fence:
            line = re.sub(r"^\s{0,3}#{1,6}\s*", "", line)
            line = re.sub(r"^\s{0,3}>\s?", "", line)
            line = re.sub(r"^\s*[-*+]\s+", "", line)
            line = re.sub(r"^\s*\d+[.)]\s+", "", line)
            line = re.sub(r"\*\*(.*?)\*\*", r"\1", line)
            line = re.sub(r"__(.*?)__", r"\1", line)
            line = re.sub(r"`([^`]*)`", r"\1", line)
            line = re.sub(r"\[(.*?)\]\((.*?)\)", r"\1", line)
            line = line.replace("*", "").replace("_", "")
        lines.append(line.strip())

    normalized = "\n".join(lines)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip() + "\n"


def restore_literal_newlines(text: str) -> str:
    return (
        text.replace("\\r\\n", "\n")
        .replace("\\n", "\n")
        .replace("\\r", "\n")
        .replace('\\"', '"')
    )


def _find_latest_result_from_index(base: Path, chapter_number: int) -> tuple[dict[str, Any] | None, str | None]:
    index = _read_run_index(base)
    records = index.get("chapter_runs", {}).get(str(chapter_number), [])
    if not isinstance(records, list):
        return None, None

    for record in reversed(records):
        if not isinstance(record, dict):
            continue
        run_dir = _record_run_dir(base, record)
        state = _read_run_state(run_dir)
        if state and result_chapter_number(state) == chapter_number:
            return state, str(run_dir)
    return None, None


def _find_latest_result_by_scanning(base: Path, chapter_number: int) -> tuple[dict[str, Any] | None, str | None]:
    run_dirs = [item for item in base.iterdir() if item.is_dir()]
    run_dirs.sort(key=lambda item: item.stat().st_mtime, reverse=True)
    for run_dir in run_dirs:
        state = _read_run_state(run_dir)
        if result_chapter_number(state) == chapter_number:
            return state, str(run_dir)
    return None, None


def _list_run_summaries_from_index(base: Path) -> list[dict[str, Any]]:
    index = _read_run_index(base)
    records = index.get("runs", [])
    if not isinstance(records, list):
        return []

    summaries = []
    for record in reversed(records):
        if not isinstance(record, dict):
            continue
        run_dir = _record_run_dir(base, record)
        state = _read_run_state(run_dir)
        if not state:
            continue
        archive = state.get("chapter_archive", {})
        summaries.append(
            {
                "run_id": record.get("run_id") or run_dir.name,
                "path": str(run_dir),
                "chapter_number": result_chapter_number(state),
                "chapter_title": state.get("chapter_plan", {}).get("chapter_title"),
                "summary": archive.get("summary", ""),
                "status": state.get("chapter_eval_report", {}).get("overall_status", ""),
                "created_at": record.get("created_at", ""),
                "finalized": bool(record.get("finalized")),
                "finalized_path": record.get("finalized_path", ""),
                "finalized_at": record.get("finalized_at", ""),
            }
        )
    return summaries


def _list_run_summaries_by_scanning(base: Path) -> list[dict[str, Any]]:
    runs = []
    run_dirs = [item for item in base.iterdir() if item.is_dir()]
    run_dirs.sort(key=lambda item: item.stat().st_mtime, reverse=True)
    for run_dir in run_dirs:
        state = _read_run_state(run_dir)
        if not state:
            continue
        archive = state.get("chapter_archive", {})
        runs.append(
            {
                "run_id": state.get("run_id") or run_dir.name,
                "path": str(run_dir),
                "chapter_number": result_chapter_number(state),
                "chapter_title": state.get("chapter_plan", {}).get("chapter_title"),
                "summary": archive.get("summary", ""),
                "status": state.get("chapter_eval_report", {}).get("overall_status", ""),
                "finalized": False,
                "finalized_path": "",
                "finalized_at": "",
            }
    )
    return runs


def _mark_run_finalized(output_dir: Path, output_path: str | None, chapter_number: int, export_path: Path) -> None:
    index_path = output_dir / RUN_INDEX_FILE
    index = _read_run_index(output_dir)
    if not index:
        return

    run_id = Path(output_path).name if output_path else ""
    finalized_at = _utc_now()
    updated = False
    for collection in [index.get("runs", []), index.get("chapter_runs", {}).get(str(chapter_number), [])]:
        if not isinstance(collection, list):
            continue
        for record in collection:
            if not isinstance(record, dict):
                continue
            if record.get("run_id") != run_id:
                continue
            record["finalized"] = True
            record["finalized_path"] = str(export_path)
            record["finalized_at"] = finalized_at
            updated = True

    if updated:
        index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")


def _chapter_title(result: dict[str, Any], chapter_number: int) -> str:
    candidates = [
        result.get("chapter_plan", {}).get("chapter_title"),
        result.get("chapter_plan", {}).get("title"),
        result.get("chapter_archive", {}).get("title"),
    ]
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return f"第{chapter_number}章"


def _safe_path_part(value: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value).strip(" .")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned[:80] or "未命名"


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_run_index(base: Path) -> dict[str, Any]:
    index_path = base / RUN_INDEX_FILE
    if not index_path.exists():
        return {}
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return index if isinstance(index, dict) else {}


def _record_run_dir(base: Path, record: dict[str, Any]) -> Path:
    path = record.get("path")
    if isinstance(path, str) and path:
        return Path(path)
    return base / str(record.get("run_id", ""))


def _read_run_state(run_dir: Path) -> dict[str, Any]:
    state_path = run_dir / "state.json"
    state: dict[str, Any] = {}
    if state_path.exists():
        try:
            loaded = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            loaded = {}
        if isinstance(loaded, dict):
            state = loaded

    final_path = run_dir / "final_chapter.md"
    if not state.get("final_chapter") and final_path.exists():
        try:
            state["final_chapter"] = final_path.read_text(encoding="utf-8")
        except OSError:
            pass
    _normalize_result_texts(state)

    reports_path = run_dir / "reports.json"
    if reports_path.exists():
        try:
            reports = json.loads(reports_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            reports = {}
        if isinstance(reports, dict):
            for key, value in reports.items():
                state.setdefault(key, value)

    return state


def _normalize_result_texts(state: dict[str, Any]) -> None:
    for key in [
        "merged_chapter",
        "continuity_fixed_chapter",
        "safety_fixed_chapter",
        "polished_chapter",
        "final_chapter",
    ]:
        value = state.get(key)
        if isinstance(value, str):
            state[key] = restore_literal_newlines(value)


def find_archive_for_chapter(memory: dict[str, Any], chapter_number: Any) -> dict[str, Any] | None:
    if not isinstance(chapter_number, int):
        return None
    for item in memory.get("chapter_summaries", []):
        if isinstance(item, dict) and item.get("chapter_number") == chapter_number:
            return item
    return None


def chapter_writing_prompt(chapter: dict[str, Any]) -> str:
    chapter_number = chapter.get("chapter_number")
    title = str(chapter.get("title") or "").strip()
    goal = str(chapter.get("goal") or "").strip()
    expected_hook = str(chapter.get("expected_hook") or "").strip()

    prefix = f"第{chapter_number}章" if chapter_number else "下一章"
    if title:
        prefix = f"{prefix}《{title}》"

    parts = [f"{prefix}，按照本项目章节计划开始写作。"]
    if goal:
        parts.append(f"本章目标：{goal}")
    if expected_hook:
        parts.append(f"章末期待：{expected_hook}")
    return "\n".join(parts)
