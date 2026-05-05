from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app import config
from app.services.json_service import read_json, write_json


DEFAULT_PROJECT_ID = "default"
DEFAULT_PROJECT_NAME = "新小说"


def project_index_path() -> Path:
    path = Path(config.NOVEL_PROJECTS_INDEX)
    if not path.is_absolute():
        path = config.project_root() / path
    return path


def load_project_index(index_path: str | Path | None = None) -> dict[str, Any]:
    path = Path(index_path) if index_path is not None else project_index_path()
    index = read_json(path, {})
    if _valid_index(index):
        return index
    index = _default_index()
    save_project_index(index, path)
    return index


def save_project_index(index: dict[str, Any], index_path: str | Path | None = None) -> None:
    path = Path(index_path) if index_path is not None else project_index_path()
    write_json(path, _normalize_index(index))


def list_projects(index_path: str | Path | None = None) -> list[dict[str, Any]]:
    return load_project_index(index_path).get("projects", [])


def get_active_project(index_path: str | Path | None = None) -> dict[str, Any]:
    index = load_project_index(index_path)
    active_project_id = index.get("active_project_id")
    return get_project(active_project_id, index_path=index_path)


def set_active_project(project_id: str, index_path: str | Path | None = None) -> dict[str, Any]:
    index = load_project_index(index_path)
    project = _find_project(index, project_id)
    if project is None:
        raise ValueError(f"Project not found: {project_id}")
    index["active_project_id"] = project["id"]
    save_project_index(index, index_path)
    return project


def delete_project(project_id: str, index_path: str | Path | None = None) -> dict[str, Any]:
    index = load_project_index(index_path)
    project = _find_project(index, project_id)
    if project is None:
        raise ValueError(f"Project not found: {project_id}")

    remaining = [
        item
        for item in index.get("projects", [])
        if isinstance(item, dict) and item.get("id") != project_id
    ]
    index["projects"] = remaining
    if index.get("active_project_id") == project_id:
        index["active_project_id"] = remaining[0]["id"] if remaining else DEFAULT_PROJECT_ID
    save_project_index(index, index_path)
    normalized = load_project_index(index_path)
    return {
        "deleted_project": project,
        "active_project_id": normalized["active_project_id"],
        "projects": normalized["projects"],
    }


def get_project(project_id: str | None, index_path: str | Path | None = None) -> dict[str, Any]:
    index = load_project_index(index_path)
    selected_id = project_id or index.get("active_project_id") or DEFAULT_PROJECT_ID
    project = _find_project(index, selected_id)
    if project is None:
        raise ValueError(f"Project not found: {selected_id}")
    return project


def create_project(name: str, index_path: str | Path | None = None) -> dict[str, Any]:
    clean_name = name.strip()
    if not clean_name:
        raise ValueError("Project name is required.")

    index = load_project_index(index_path)
    for project in index.get("projects", []):
        if project.get("name") == clean_name:
            raise ValueError(f"Project name already exists: {clean_name}")

    project_id = _unique_project_id(clean_name, index, index_path)
    now = _utc_now()
    project_root = Path("projects") / project_id
    project = {
        "id": project_id,
        "name": clean_name,
        "memory_dir": str(project_root / "story_memory"),
        "output_dir": str(project_root / "outputs"),
        "created_at": now,
        "updated_at": now,
    }
    index.setdefault("projects", []).append(project)
    index["active_project_id"] = project_id
    save_project_index(index, index_path)
    return project


def create_numbered_project(name: str, index_path: str | Path | None = None) -> dict[str, Any]:
    clean_name = name.strip()
    if not clean_name:
        raise ValueError("Project name is required.")

    index = load_project_index(index_path)
    project_id = _next_numbered_project_id(index, index_path)
    now = _utc_now()
    project_root = Path("projects") / project_id
    project = {
        "id": project_id,
        "name": clean_name,
        "memory_dir": str(project_root / "story_memory"),
        "output_dir": str(project_root / "outputs"),
        "created_at": now,
        "updated_at": now,
    }
    index.setdefault("projects", []).append(project)
    index["active_project_id"] = project_id
    save_project_index(index, index_path)
    return project


def project_paths(project_id: str | None = None, index_path: str | Path | None = None) -> tuple[str, str]:
    project = get_project(project_id, index_path=index_path)
    return str(project["memory_dir"]), str(project["output_dir"])


def resolve_project_context(
    project_id: str | None = None,
    memory_dir: str | None = None,
    output_dir: str | None = None,
    index_path: str | Path | None = None,
) -> dict[str, str]:
    if project_id:
        project = get_project(project_id, index_path=index_path)
        return {
            "project_id": str(project["id"]),
            "project_name": str(project["name"]),
            "memory_dir": str(project["memory_dir"]),
            "output_dir": str(project["output_dir"]),
        }

    if memory_dir or output_dir:
        return {
            "project_id": "",
            "project_name": "",
            "memory_dir": memory_dir or config.NOVEL_MEMORY_DIR,
            "output_dir": output_dir or config.NOVEL_OUTPUT_DIR,
        }

    project = get_active_project(index_path=index_path)
    return {
        "project_id": str(project["id"]),
        "project_name": str(project["name"]),
        "memory_dir": str(project["memory_dir"]),
        "output_dir": str(project["output_dir"]),
    }


def _default_index() -> dict[str, Any]:
    now = _utc_now()
    return {
        "active_project_id": DEFAULT_PROJECT_ID,
        "projects": [
            {
                "id": DEFAULT_PROJECT_ID,
                "name": DEFAULT_PROJECT_NAME,
                "memory_dir": config.NOVEL_MEMORY_DIR,
                "output_dir": config.NOVEL_OUTPUT_DIR,
                "created_at": now,
                "updated_at": now,
            }
        ],
    }


def _normalize_index(index: dict[str, Any]) -> dict[str, Any]:
    if not _valid_index(index):
        return _default_index()

    projects = []
    seen = set()
    for project in index.get("projects", []):
        if not isinstance(project, dict):
            continue
        project_id = str(project.get("id") or "").strip()
        name = str(project.get("name") or "").strip()
        if not project_id or not name or project_id in seen:
            continue
        seen.add(project_id)
        projects.append(
            {
                "id": project_id,
                "name": name,
                "memory_dir": str(project.get("memory_dir") or Path("projects") / project_id / "story_memory"),
                "output_dir": str(project.get("output_dir") or Path("projects") / project_id / "outputs"),
                "created_at": str(project.get("created_at") or _utc_now()),
                "updated_at": str(project.get("updated_at") or project.get("created_at") or _utc_now()),
            }
        )

    if not projects:
        return _default_index()

    active_project_id = str(index.get("active_project_id") or projects[0]["id"])
    if active_project_id not in {project["id"] for project in projects}:
        active_project_id = projects[0]["id"]
    return {"active_project_id": active_project_id, "projects": projects}


def _valid_index(index: Any) -> bool:
    return isinstance(index, dict) and isinstance(index.get("projects"), list)


def _find_project(index: dict[str, Any], project_id: str | None) -> dict[str, Any] | None:
    for project in index.get("projects", []):
        if isinstance(project, dict) and project.get("id") == project_id:
            return project
    return None


def _unique_project_id(name: str, index: dict[str, Any], index_path: str | Path | None = None) -> str:
    base = _slugify(name) or "novel"
    existing = {project.get("id") for project in index.get("projects", []) if isinstance(project, dict)}
    if base not in existing and not _managed_project_root_exists(base, index_path):
        return base
    counter = 2
    while f"{base}-{counter}" in existing or _managed_project_root_exists(f"{base}-{counter}", index_path):
        counter += 1
    return f"{base}-{counter}"


def _next_numbered_project_id(index: dict[str, Any], index_path: str | Path | None = None) -> str:
    existing = {str(project.get("id")) for project in index.get("projects", []) if isinstance(project, dict)}
    counter = 1
    while f"novel-{counter}" in existing or _managed_project_root_exists(f"novel-{counter}", index_path):
        counter += 1
    return f"novel-{counter}"


def _managed_project_root_exists(project_id: str, index_path: str | Path | None = None) -> bool:
    return (_project_index_base_dir(index_path) / "projects" / project_id).exists()


def _project_index_base_dir(index_path: str | Path | None = None) -> Path:
    if index_path is not None:
        path = Path(index_path)
        if not path.is_absolute():
            path = config.project_root() / path
        return path.parent
    return project_index_path().parent


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return slug[:48].strip("-")


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
