from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Lock
from time import perf_counter
from traceback import format_exc, format_exception_only
from typing import Any, Callable
from uuid import uuid4


TaskRunner = Callable[[Callable[[dict[str, Any]], None]], dict[str, Any]]

_executor = ThreadPoolExecutor(max_workers=2)
_lock = Lock()
_tasks: dict[str, dict[str, Any]] = {}


def create_task(label: str, runner: TaskRunner, chapter_number: int | None = None) -> dict[str, Any]:
    task_id = uuid4().hex
    now = _utc_now()
    task = {
        "task_id": task_id,
        "label": label,
        "chapter_number": chapter_number,
        "status": "queued",
        "created_at": now,
        "updated_at": now,
        "completed_at": "",
        "elapsed_seconds": 0.0,
        "events": [],
        "result": None,
        "error": "",
    }
    with _lock:
        _tasks[task_id] = task
    _add_event(task_id, {"type": "task_queued", "label": "任务已创建"})
    _executor.submit(_run_task, task_id, runner)
    return get_task(task_id)


def get_task(task_id: str) -> dict[str, Any]:
    with _lock:
        task = _tasks.get(task_id)
        if not task:
            raise KeyError(task_id)
        snapshot = dict(task)
        snapshot["events"] = list(task["events"])
    if snapshot["status"] in {"queued", "running"}:
        snapshot["elapsed_seconds"] = round(perf_counter() - snapshot["_started_counter"], 1) if "_started_counter" in snapshot else 0.0
    snapshot.pop("_started_counter", None)
    return snapshot


def _run_task(task_id: str, runner: TaskRunner) -> None:
    started = perf_counter()
    with _lock:
        task = _tasks[task_id]
        task["status"] = "running"
        task["updated_at"] = _utc_now()
        task["_started_counter"] = started
    _add_event(task_id, {"type": "task_started", "label": "任务开始执行"})
    try:
        result = runner(lambda event: _add_event(task_id, event))
    except Exception as exc:  # noqa: BLE001 - task boundary must capture user-visible failure
        print(format_exc(), flush=True)
        with _lock:
            task = _tasks[task_id]
            task["status"] = "failed"
            task["error"] = "".join(format_exception_only(type(exc), exc)).strip()
            task["completed_at"] = _utc_now()
            task["updated_at"] = task["completed_at"]
            task["elapsed_seconds"] = round(perf_counter() - started, 1)
        _add_event(task_id, {"type": "task_failed", "label": "任务执行失败"})
        return

    with _lock:
        task = _tasks[task_id]
        task["status"] = "completed"
        task["result"] = result
        task["completed_at"] = _utc_now()
        task["updated_at"] = task["completed_at"]
        task["elapsed_seconds"] = round(perf_counter() - started, 1)
    _add_event(task_id, {"type": "task_completed", "label": "任务已完成"})


def _add_event(task_id: str, event: dict[str, Any]) -> None:
    with _lock:
        task = _tasks.get(task_id)
        if not task:
            return
        now = _utc_now()
        item = {
            "time": now,
            "elapsed_seconds": round(perf_counter() - task.get("_started_counter", perf_counter()), 1)
            if "_started_counter" in task
            else 0.0,
            **event,
        }
        task["events"].append(item)
        task["updated_at"] = now


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
