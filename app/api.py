from __future__ import annotations

import mimetypes
import re
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app import config
from app.graph.workflow import run_workflow
from app.services.memory_service import ensure_default_memory, load_story_memory
from app.services.outline_service import generate_story_outline
from app.services.outline_service import reset_writing_records
from app.services.outline_service import save_outline_request
from app.services.output_service import write_run_outputs
from app.services.project_service import create_project
from app.services.project_service import create_numbered_project
from app.services.project_service import delete_project
from app.services.project_service import list_projects
from app.services.project_service import resolve_project_context
from app.services.project_service import set_active_project
from app.services.run_service import find_archive_for_chapter
from app.services.run_service import find_latest_result_for_chapter
from app.services.run_service import export_final_chapter_text
from app.services.run_service import list_run_summaries
from app.services.run_service import result_chapter_number
from app.services.setup_service import save_setup_config
from app.services.setup_service import setup_config
from app.services.setup_service import setup_status
from app.services.setup_service import test_setup_config
from app.services.task_service import create_task
from app.services.task_service import get_task
from app.services.topic_service import TOPIC_CATEGORIES
from app.services.topic_service import suggest_topics

mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("application/javascript", ".mjs")
mimetypes.add_type("text/css", ".css")


class ProjectCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)


class SetupConfigRequest(BaseModel):
    PROVIDER: str = Field(default="openai_compatible", max_length=40)
    OPENAI_API_KEY: str = Field(default="", max_length=400)
    OPENAI_MODEL: str = Field(default="gpt-4.1-mini", max_length=120)
    COMPAT_API_KEY: str = Field(default="", max_length=400)
    COMPAT_BASE_URL: str = Field(default="https://openrouter.ai/api/v1", max_length=300)
    COMPAT_MODEL: str = Field(default="", max_length=160)
    LLM_TIMEOUT_SECONDS: float = Field(default=600, ge=1, le=3600)
    LLM_TRACE: bool = False
    LLM_PROGRESS: bool = True
    LLM_FALLBACK_ON_ERROR: bool = False
    NOVEL_PROJECTS_INDEX: str = Field(default="novel_projects.json", max_length=160)


class TopicSuggestionRequest(BaseModel):
    reader: str = Field(default="不限", max_length=20)
    category: str = Field(default="不限", max_length=40)
    count: int = Field(default=5, ge=1, le=10)
    keywords: str = Field(default="", max_length=500)


class TopicUseRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=80)
    outline_prompt: str = Field(..., min_length=1, max_length=4000)
    chapters: int = Field(default=30, ge=1, le=500)
    target_words_per_chapter: int | None = Field(default=3000, ge=100, le=50000)


class OutlineRequest(BaseModel):
    user_input: str = Field(..., min_length=1)
    project_id: str | None = None
    memory_dir: str | None = None
    output_dir: str | None = None
    chapters: int = Field(default=30, ge=1, le=500)
    target_words_per_chapter: int | None = Field(default=None, ge=100, le=50000)
    reset_writing_records: bool = False


class ChapterWriteRequest(BaseModel):
    user_input: str = Field(..., min_length=1)
    project_id: str | None = None
    memory_dir: str | None = None
    output_dir: str | None = None
    init_memory: bool = True


def create_app() -> FastAPI:
    app = FastAPI(title="novel_writer_agent API")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/config")
    def read_config() -> dict[str, Any]:
        return {
            "provider": config.PROVIDER,
            "compat_model": config.COMPAT_MODEL,
            "memory_dir": config.NOVEL_MEMORY_DIR,
            "output_dir": config.NOVEL_OUTPUT_DIR,
            "projects_index": config.NOVEL_PROJECTS_INDEX,
            "llm_trace": config.LLM_TRACE,
            "llm_timeout_seconds": config.LLM_TIMEOUT_SECONDS,
            "llm_fallback_on_error": config.LLM_FALLBACK_ON_ERROR,
        }

    @app.get("/api/setup/status")
    def read_setup_status() -> dict[str, Any]:
        return setup_status()

    @app.get("/api/setup/config")
    def read_setup_config() -> dict[str, Any]:
        return setup_config()

    @app.post("/api/setup/config")
    def write_setup_config(payload: SetupConfigRequest) -> dict[str, Any]:
        try:
            return save_setup_config(payload.dict())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/setup/test")
    def test_setup(payload: SetupConfigRequest) -> dict[str, Any]:
        try:
            return test_setup_config(payload.dict())
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/projects")
    def read_projects() -> dict[str, Any]:
        projects = list_projects()
        active = resolve_project_context()
        return {"active_project_id": active["project_id"], "projects": projects}

    @app.post("/api/projects")
    def add_project(payload: ProjectCreateRequest) -> dict[str, Any]:
        try:
            project = create_project(payload.name)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        ensure_default_memory(project["memory_dir"])
        Path(project["output_dir"]).mkdir(parents=True, exist_ok=True)
        return project

    @app.get("/api/topic-options")
    def read_topic_options() -> dict[str, Any]:
        return {
            "readers": ["不限", "男频", "女频"],
            "categories": TOPIC_CATEGORIES,
        }

    @app.post("/api/topic-suggestions")
    def create_topic_suggestions(payload: TopicSuggestionRequest) -> dict[str, Any]:
        return suggest_topics(payload.reader, payload.category, payload.count, payload.keywords)

    @app.post("/api/topic-suggestions/use")
    def use_topic(payload: TopicUseRequest) -> dict[str, Any]:
        try:
            project = create_numbered_project(payload.title)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        ensure_default_memory(project["memory_dir"])
        Path(project["output_dir"]).mkdir(parents=True, exist_ok=True)
        save_outline_request(
            project["memory_dir"],
            payload.outline_prompt,
            chapters=payload.chapters,
            target_words_per_chapter=payload.target_words_per_chapter,
        )
        return project

    @app.post("/api/projects/{project_id}/activate")
    def activate_project(project_id: str) -> dict[str, Any]:
        try:
            return set_active_project(project_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.delete("/api/projects/{project_id}")
    def remove_project(project_id: str) -> dict[str, Any]:
        try:
            return delete_project(project_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/memory")
    def read_memory(
        project_id: str | None = Query(default=None),
        memory_dir: str | None = Query(default=None),
    ) -> dict[str, Any]:
        context = _project_context(project_id=project_id, memory_dir=memory_dir)
        return load_story_memory(context["memory_dir"])

    @app.post("/api/memory/init")
    def init_memory(
        project_id: str | None = Query(default=None),
        memory_dir: str | None = Query(default=None),
    ) -> dict[str, str]:
        context = _project_context(project_id=project_id, memory_dir=memory_dir)
        ensure_default_memory(context["memory_dir"])
        return {"status": "ok", **context}

    @app.post("/api/outline")
    def write_outline(payload: OutlineRequest) -> dict[str, Any]:
        context = _project_context(
            project_id=payload.project_id,
            memory_dir=payload.memory_dir,
            output_dir=payload.output_dir,
        )

        def runner(progress_callback):
            if payload.reset_writing_records:
                progress_callback({"type": "outline_reset", "label": "重置旧写作记录"})
                reset_writing_records(context["memory_dir"], context["output_dir"])
            outline = generate_story_outline(
                payload.user_input,
                context["memory_dir"],
                target_chapter_count=payload.chapters,
                target_words_per_chapter=payload.target_words_per_chapter,
                progress_callback=progress_callback,
            )
            return {"project": context, "outline": outline}

        return create_task("生成故事大纲", runner)

    @app.post("/api/chapters/write")
    def write_chapter(payload: ChapterWriteRequest) -> dict[str, Any]:
        context = _project_context(
            project_id=payload.project_id,
            memory_dir=payload.memory_dir,
            output_dir=payload.output_dir,
        )
        chapter_number = _extract_chapter_number(payload.user_input)

        def runner(progress_callback):
            if payload.init_memory:
                ensure_default_memory(context["memory_dir"])
            result = run_workflow(
                {
                    "user_input": payload.user_input,
                    "memory_dir": context["memory_dir"],
                    "output_dir": context["output_dir"],
                },
                progress_callback=progress_callback,
            )
            progress_callback({"type": "writing_outputs", "label": "写入章节结果"})
            output_path = write_run_outputs(result, context["output_dir"])
            result["output_path"] = str(output_path)
            result["project"] = context
            return {
                "project": context,
                "output_path": str(output_path),
                "chapter_number": result_chapter_number(result),
            }

        return create_task("章节写作", runner, chapter_number=chapter_number)

    @app.get("/api/tasks/{task_id}")
    def read_task(task_id: str) -> dict[str, Any]:
        try:
            return get_task(task_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Task not found.") from exc

    @app.get("/api/chapters/{chapter_number}/result")
    def read_chapter_result(
        chapter_number: int,
        project_id: str | None = Query(default=None),
        memory_dir: str | None = Query(default=None),
        output_dir: str | None = Query(default=None),
    ) -> dict[str, Any]:
        context = _project_context(project_id=project_id, memory_dir=memory_dir, output_dir=output_dir)
        result, output_path = find_latest_result_for_chapter(context["output_dir"], chapter_number)
        if result:
            return {"kind": "result", "project": context, "output_path": output_path, "result": result}

        archive = find_archive_for_chapter(load_story_memory(context["memory_dir"]), chapter_number)
        if archive:
            return {"kind": "archive", "project": context, "archive": archive}

        raise HTTPException(status_code=404, detail="Chapter result not found.")

    @app.post("/api/chapters/{chapter_number}/finalize")
    def finalize_chapter(
        chapter_number: int,
        project_id: str | None = Query(default=None),
    ) -> dict[str, Any]:
        context = _project_context(project_id=project_id)
        try:
            return export_final_chapter_text(
                context["output_dir"],
                context["project_name"],
                chapter_number,
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/runs")
    def read_runs(
        project_id: str | None = Query(default=None),
        output_dir: str | None = Query(default=None),
    ) -> dict[str, Any]:
        context = _project_context(project_id=project_id, output_dir=output_dir)
        return {"project": context, "runs": list_run_summaries(context["output_dir"])}

    web_dist = config.project_root() / "web" / "dist"
    if web_dist.exists():
        app.mount("/", StaticFiles(directory=web_dist, html=True), name="web")

    return app


def _project_context(
    project_id: str | None = None,
    memory_dir: str | None = None,
    output_dir: str | None = None,
) -> dict[str, str]:
    try:
        return resolve_project_context(project_id=project_id, memory_dir=memory_dir, output_dir=output_dir)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _extract_chapter_number(text: str) -> int | None:
    match = re.search(r"第\s*(\d+)\s*章", text)
    if match:
        return int(match.group(1))
    match = re.search(r"chapter\s*(\d+)", text, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None


app = create_app()
