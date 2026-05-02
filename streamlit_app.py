import difflib
import html
import json
from pathlib import Path
from typing import Any

import streamlit as st
import streamlit.components.v1 as components

from app import config
from app.graph.workflow import run_workflow
from app.services.memory_service import ensure_default_memory, load_story_memory
from app.services.output_service import write_run_outputs
from app.services.outline_service import generate_story_outline


DEFAULT_OUTLINE_INPUT = """
写一部都市悬疑小说，主角是旧档案修复师。
旧城里有一宗二十年前失踪案。
故事要有强记忆、伏笔回收和章末钩子。
""".strip()

DEFAULT_CHAPTER_INPUT = "第1章，按照本项目章节计划开始写作。"

WORKSPACES = ["故事大纲", "故事写作"]


def main() -> None:
    st.set_page_config(
        page_title="小说 AI 写作工作台",
        layout="wide",
    )
    _init_session_state()

    with st.sidebar:
        st.subheader("运行配置")
        st.caption("配置读取自 .env。修改 .env 后请重启 Streamlit。")
        st.text_input("Provider", value=config.PROVIDER, disabled=True)
        st.text_input("Memory Dir", value=config.NOVEL_MEMORY_DIR, disabled=True)
        st.text_input("Output Dir", value=config.NOVEL_OUTPUT_DIR, disabled=True)
        st.checkbox("LLM_TRACE", value=config.LLM_TRACE, disabled=True)
        st.checkbox("LLM_FALLBACK_ON_ERROR", value=config.LLM_FALLBACK_ON_ERROR, disabled=True)

        memory_dir = st.text_input("本次记忆目录", value=config.NOVEL_MEMORY_DIR)
        output_dir = st.text_input("本次输出目录", value=config.NOVEL_OUTPUT_DIR)
        show_debug = st.toggle("显示调试区", value=True)

    _apply_pending_workspace()

    active_workspace = st.radio(
        "工作区",
        options=WORKSPACES,
        horizontal=True,
        key="active_workspace_widget",
        on_change=_sync_active_workspace,
        label_visibility="collapsed",
    )
    st.session_state["active_workspace"] = active_workspace

    if active_workspace == "故事大纲":
        _render_outline_workspace(memory_dir)
    else:
        _render_writing_workspace(memory_dir, output_dir, show_debug)


def _init_session_state() -> None:
    st.session_state.setdefault("outline_input", DEFAULT_OUTLINE_INPUT)
    st.session_state.setdefault("chapter_input", DEFAULT_CHAPTER_INPUT)
    st.session_state.setdefault("active_workspace", "故事大纲")
    if st.session_state["active_workspace"] not in WORKSPACES:
        st.session_state["active_workspace"] = "故事写作"
    st.session_state.setdefault("active_workspace_widget", st.session_state["active_workspace"])
    if st.session_state["active_workspace_widget"] not in WORKSPACES:
        st.session_state["active_workspace_widget"] = st.session_state["active_workspace"]


def _sync_active_workspace() -> None:
    st.session_state["active_workspace"] = st.session_state["active_workspace_widget"]


def _apply_pending_workspace() -> None:
    pending_workspace = st.session_state.pop("pending_workspace", None)
    if pending_workspace not in WORKSPACES:
        return
    st.session_state["active_workspace"] = pending_workspace
    st.session_state["active_workspace_widget"] = pending_workspace


def _navigate_to(workspace: str) -> None:
    st.session_state["pending_workspace"] = workspace
    st.rerun()


def _render_outline_workspace(memory_dir: str) -> None:
    st.caption("先建立故事底座：故事 bible、风格指南、逐章计划、角色、伏笔和主线线程。")

    outline_input = st.text_area(
        "小说项目创作需求",
        height=240,
        key="outline_input",
        placeholder="写清楚类型、主角、核心冲突、长期悬念、风格偏好和必须避免的内容。",
    )
    chapters = st.number_input("规划章节数", min_value=1, max_value=500, value=30, step=1)

    col_a, col_b = st.columns([1, 3])
    with col_a:
        generate = st.button("生成故事大纲", type="primary")
    with col_b:
        if st.button("初始化默认记忆文件"):
            ensure_default_memory(memory_dir)
            st.success(f"已初始化：{memory_dir}")

    if not generate:
        return
    if not outline_input.strip():
        st.warning("请先填写小说项目创作需求。")
        return

    try:
        with st.spinner("正在生成故事大纲和结构化记忆..."):
            outline = generate_story_outline(
                outline_input.strip(),
                memory_dir,
                target_chapter_count=int(chapters),
            )
    except Exception as exc:
        st.error(f"大纲生成失败：{exc}")
        return

    st.session_state["outline"] = outline
    st.session_state["memory_snapshot"] = load_story_memory(memory_dir)
    st.success(f"大纲已写入：{memory_dir}")
    _render_outline_summary(outline)
    _navigate_to("故事写作")


def _render_chapter_composer(memory_dir: str, output_dir: str) -> None:
    st.caption("章节生成直接复用 CLI 后端流程：run_workflow -> write_run_outputs。")

    chapter_input = st.text_area(
        "本章写作需求",
        height=220,
        key="chapter_input",
        placeholder="例如：第3章，主角追查旧档案编号，发现盟友隐瞒了关键线索。",
    )

    col_a, col_b = st.columns([1, 3])
    with col_a:
        generate = st.button("生成章节", type="primary")
    with col_b:
        init_memory = st.checkbox("运行前补齐默认记忆文件", value=True)

    if not generate:
        return
    if not chapter_input.strip():
        st.warning("请先填写本章写作需求。")
        return

    _run_chapter_agent(chapter_input.strip(), memory_dir, output_dir, init_memory)


def _run_chapter_agent(user_input: str, memory_dir: str, output_dir: str, init_memory: bool) -> None:
    progress = st.progress(0, text="正在准备章节工作流...")
    try:
        if init_memory:
            ensure_default_memory(memory_dir)
        progress.progress(15, text="正在运行章节工作流...")
        with st.spinner("Agent 正在规划、写作、检查并更新故事记忆..."):
            result = run_workflow(
                {
                    "user_input": user_input,
                    "memory_dir": memory_dir,
                    "output_dir": output_dir,
                }
            )
        progress.progress(85, text="正在保存运行产物...")
        output_path = write_run_outputs(result, output_dir)
        progress.progress(100, text="生成完成")
    except Exception as exc:
        progress.empty()
        st.error(f"章节生成失败：{exc}")
        return

    st.session_state["result"] = result
    st.session_state["output_path"] = str(output_path)
    st.session_state["selected_result"] = result
    st.session_state["selected_output_path"] = str(output_path)
    st.session_state["memory_snapshot"] = load_story_memory(memory_dir)
    st.success(f"生成完成，产物已保存到：{output_path}")
    _navigate_to("故事写作")


def _render_result(
    result: dict[str, Any],
    output_path: str | None,
    show_debug: bool,
    key_prefix: str = "result",
) -> None:
    final_chapter = result.get("final_chapter", "")
    eval_report = result.get("chapter_eval_report", {})
    continuity_report = result.get("continuity_report", {})
    safety_report = result.get("final_safety_report", {})
    archive = result.get("chapter_archive", {})

    col_a, col_b, col_c, col_d = st.columns(4)
    col_a.metric("章节号", archive.get("chapter_number", "-"))
    col_b.metric("体验状态", eval_report.get("overall_status", "-"))
    col_c.metric("连续性", continuity_report.get("status", "-"))
    col_d.metric("安全状态", safety_report.get("status", "-"))

    st.subheader("最终章节")
    st.text_area("最终正文", value=final_chapter, height=560, key=f"{key_prefix}_final_chapter")
    if output_path:
        st.caption(f"输出目录：{output_path}")

    report_tab, compare_tab, memory_tab, debug_tab = st.tabs(["报告", "版本对比", "记忆更新", "调试"])

    with report_tab:
        _render_reports(result)

    with compare_tab:
        _render_version_compare(result, key_prefix=key_prefix)

    with memory_tab:
        st.markdown("#### 章节归档")
        st.json(archive, expanded=False)
        st.markdown("#### 记忆更新")
        st.json(result.get("memory_update", {}), expanded=False)
        st.markdown("#### 记忆校验")
        st.json(result.get("memory_validation_report", {}), expanded=False)

    with debug_tab:
        if show_debug:
            _render_debug(result)
        else:
            st.info("调试区已在侧边栏关闭。")


def _render_reports(result: dict[str, Any]) -> None:
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("#### 输入安全")
        st.json(result.get("input_safety_report", {}), expanded=False)
        st.markdown("#### 连续性检查")
        st.json(result.get("continuity_report", {}), expanded=False)
        st.markdown("#### 章节体验")
        st.json(result.get("chapter_eval_report", {}), expanded=False)
    with col_b:
        st.markdown("#### 正文安全")
        st.json(result.get("chapter_safety_report", {}), expanded=False)
        st.markdown("#### 最终安全")
        st.json(result.get("final_safety_report", {}), expanded=False)
        st.markdown("#### 章末钩子")
        st.json(result.get("chapter_hook_report", {}), expanded=False)


def _render_version_compare(result: dict[str, Any], key_prefix: str = "result") -> None:
    versions = _chapter_versions(result)
    if len(versions) < 2:
        st.info("当前可对比的版本不足。")
        return

    labels = list(versions)
    col_a, col_b = st.columns(2)
    with col_a:
        left_label = st.selectbox("左侧版本", labels, index=0, key=f"{key_prefix}_compare_left_label")
    with col_b:
        right_label = st.selectbox(
            "右侧版本",
            labels,
            index=len(labels) - 1,
            key=f"{key_prefix}_compare_right_label",
        )

    left_text = versions[left_label]
    right_text = versions[right_label]
    col_left, col_right = st.columns(2)
    with col_left:
        st.text_area(left_label, value=left_text, height=420, key=f"{key_prefix}_compare_left_text")
    with col_right:
        st.text_area(right_label, value=right_text, height=420, key=f"{key_prefix}_compare_right_text")

    diff = difflib.unified_diff(
        left_text.splitlines(),
        right_text.splitlines(),
        fromfile=left_label,
        tofile=right_label,
        lineterm="",
    )
    st.markdown("#### 文本差异")
    st.code("\n".join(diff) or "两个版本文本一致。", language="diff")


def _chapter_versions(result: dict[str, Any]) -> dict[str, str]:
    candidates = [
        ("合并初稿", result.get("merged_chapter", "")),
        ("连续性修复后", result.get("continuity_fixed_chapter", "")),
        ("安全修复后", result.get("safety_fixed_chapter", "")),
        ("润色后", result.get("polished_chapter", "")),
        ("最终章节", result.get("final_chapter", "")),
    ]
    versions = {}
    for label, text in candidates:
        if text and text not in versions.values():
            versions[label] = text
    return versions


def _render_writing_workspace(memory_dir: str, output_dir: str, show_debug: bool) -> None:
    st.caption("从章节计划进入写作，或查看已生成章节的写作结果。")

    if st.button("刷新故事记忆"):
        st.session_state["memory_snapshot"] = load_story_memory(memory_dir)

    memory = st.session_state.get("memory_snapshot")
    if memory is None:
        memory = load_story_memory(memory_dir)
        st.session_state["memory_snapshot"] = memory

    summary = _memory_summary(memory)
    col_a, col_b, col_c, col_d = st.columns(4)
    col_a.metric("计划章节", summary["planned_chapters"])
    col_b.metric("归档章节", summary["chapter_summaries"])
    col_c.metric("角色记录", summary["characters"])
    col_d.metric("伏笔记录", summary["foreshadowing"])

    plan_tab, composer_tab, result_tab, ledger_tab = st.tabs(["章节计划", "本章写作", "写作结果", "故事账本"])
    with plan_tab:
        _render_selected_result_inline(show_debug, show_empty=False, key_prefix="plan")
        _render_chapter_plan(memory, output_dir)

    with composer_tab:
        _render_chapter_composer(memory_dir, output_dir)

    with result_tab:
        _render_selected_result_inline(show_debug, key_prefix="result")

    with ledger_tab:
        st.markdown("#### Story Bible")
        st.text_area("bible.md", value=memory.get("bible", ""), height=300)
        st.markdown("#### Style Guide")
        st.text_area("style_guide.md", value=memory.get("style_guide", ""), height=240)
        st.markdown("#### Characters")
        st.json(memory.get("characters", {}), expanded=False)
        st.markdown("#### Timeline")
        st.json(memory.get("timeline", {}), expanded=False)
        st.markdown("#### Plot Threads")
        st.json(memory.get("plot_threads", {}), expanded=False)
        st.markdown("#### Foreshadowing")
        st.json(memory.get("foreshadowing", {}), expanded=False)
        with st.expander("原始 story_memory", expanded=False):
            st.json(memory, expanded=False)


def _render_outline_summary(outline: dict[str, Any]) -> None:
    planned = outline.get("chapter_plan", {}).get("planned_chapters", [])
    st.markdown("#### 大纲摘要")
    col_a, col_b = st.columns(2)
    col_a.metric("计划章节", len(planned))
    col_b.metric("主类型", outline.get("genre_profile", {}).get("primary_genre", "-"))
    if planned:
        st.json({"first_chapter": planned[0], "last_chapter": planned[-1]}, expanded=False)


def _render_chapter_plan(memory: dict[str, Any], output_dir: str) -> None:
    planned = memory.get("chapter_plan", {}).get("planned_chapters", [])
    if not planned:
        st.info("当前还没有逐章计划。可以先到“故事大纲”生成大纲。")
        return

    archived_numbers = _archived_chapter_numbers(memory)
    st.caption("点击某章后的按钮，会把该章计划填入章节生成输入框；已归档章节会显示为“重新写作”。")
    for index, chapter in enumerate(planned, start=1):
        if not isinstance(chapter, dict):
            continue
        action_label = _chapter_action_label(chapter, archived_numbers)
        with st.container(border=True):
            components.html(_chapter_plan_card_html(chapter), height=128, scrolling=False)
            col_a, col_b, col_c = st.columns([1, 1, 4], vertical_alignment="center")
            with col_a:
                if st.button(action_label, key=f"start_chapter_{index}", type="primary"):
                    _start_chapter_writing(chapter)
            with col_b:
                if st.button("查看写作结果", key=f"view_chapter_{index}"):
                    _select_chapter_result(chapter, memory, output_dir)
            with col_c:
                st.caption(_chapter_writing_prompt(chapter))


def _start_chapter_writing(chapter: dict[str, Any]) -> None:
    st.session_state["chapter_input"] = _chapter_writing_prompt(chapter)
    _navigate_to("故事写作")


def _select_chapter_result(chapter: dict[str, Any], memory: dict[str, Any], output_dir: str) -> None:
    chapter_number = chapter.get("chapter_number")
    result, output_path = _find_latest_result_for_chapter(output_dir, chapter_number)
    if result:
        st.session_state["selected_result"] = result
        st.session_state["selected_output_path"] = output_path
        st.session_state["selected_archive"] = None
        st.session_state["selected_missing_chapter"] = None
        return

    st.session_state["selected_result"] = None
    st.session_state["selected_output_path"] = None
    st.session_state["selected_archive"] = _find_archive_for_chapter(memory, chapter_number)
    st.session_state["selected_missing_chapter"] = chapter_number


def _render_selected_result_inline(
    show_debug: bool,
    show_empty: bool = True,
    key_prefix: str = "result",
) -> None:
    selected_result = st.session_state.get("selected_result")
    selected_archive = st.session_state.get("selected_archive")
    if selected_result:
        st.divider()
        _render_result(
            selected_result,
            st.session_state.get("selected_output_path"),
            show_debug,
            key_prefix=key_prefix,
        )
    elif selected_archive:
        st.divider()
        st.info("未找到该章节的完整运行结果，仅显示章节归档。")
        st.json(selected_archive, expanded=False)
    else:
        if not show_empty:
            return
        missing = st.session_state.get("selected_missing_chapter")
        if missing:
            st.info(f"第 {missing} 章还没有可查看的写作结果。")
        else:
            st.info("点击章节卡片里的“查看写作结果”后，这里会显示对应章节结果。")


def _chapter_writing_prompt(chapter: dict[str, Any]) -> str:
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


def _archived_chapter_numbers(memory: dict[str, Any]) -> set[int]:
    numbers = set()
    for item in memory.get("chapter_summaries", []):
        if not isinstance(item, dict):
            continue
        number = item.get("chapter_number")
        if isinstance(number, int):
            numbers.add(number)
    return numbers


def _chapter_action_label(chapter: dict[str, Any], archived_numbers: set[int]) -> str:
    chapter_number = chapter.get("chapter_number")
    if isinstance(chapter_number, int) and chapter_number in archived_numbers:
        return "重新写作"
    return "开始写作"


def _find_archive_for_chapter(memory: dict[str, Any], chapter_number: Any) -> dict[str, Any] | None:
    if not isinstance(chapter_number, int):
        return None
    for item in memory.get("chapter_summaries", []):
        if isinstance(item, dict) and item.get("chapter_number") == chapter_number:
            return item
    return None


def _find_latest_result_for_chapter(output_dir: str, chapter_number: Any) -> tuple[dict[str, Any] | None, str | None]:
    if not isinstance(chapter_number, int):
        return None, None

    base = Path(output_dir)
    if not base.exists():
        return None, None

    run_dirs = [item for item in base.iterdir() if item.is_dir()]
    run_dirs.sort(key=lambda item: item.stat().st_mtime, reverse=True)
    for run_dir in run_dirs:
        state_path = run_dir / "state.json"
        if not state_path.exists():
            continue
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if _result_chapter_number(state) == chapter_number:
            return state, str(run_dir)
    return None, None


def _result_chapter_number(result: dict[str, Any]) -> int | None:
    candidates = [
        result.get("chapter_archive", {}).get("chapter_number"),
        result.get("story_request", {}).get("chapter_number"),
        result.get("chapter_plan", {}).get("chapter_number"),
    ]
    for candidate in candidates:
        if isinstance(candidate, int):
            return candidate
    return None


def _chapter_plan_card_html(chapter: dict[str, Any]) -> str:
    chapter_number = html.escape(str(chapter.get("chapter_number") or "-"))
    title = html.escape(str(chapter.get("title") or "未命名章节"))
    goal = html.escape(str(chapter.get("goal") or ""))
    expected_hook = html.escape(str(chapter.get("expected_hook") or ""))
    volume = html.escape(str(chapter.get("volume") or ""))

    volume_badge = f'<span class="badge">{volume}</span>' if volume else ""
    hook_html = f'<div class="hook">章末期待：{expected_hook}</div>' if expected_hook else ""
    return f"""
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{
    margin: 0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    color: #1f2937;
    background: transparent;
  }}
  .chapter-card {{
    box-sizing: border-box;
    min-height: 110px;
    padding: 2px 2px 0;
    background: transparent;
  }}
  .meta {{
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 8px;
    color: #64748b;
    font-size: 13px;
  }}
  .number {{
    font-weight: 700;
    color: #2563eb;
  }}
  .badge {{
    padding: 2px 8px;
    border-radius: 999px;
    background: #eef2ff;
    color: #3730a3;
    font-size: 12px;
  }}
  .title {{
    margin: 0 0 8px;
    font-size: 18px;
    line-height: 1.35;
    font-weight: 700;
    color: #111827;
  }}
  .goal {{
    margin: 0;
    font-size: 14px;
    line-height: 1.55;
  }}
  .hook {{
    margin-top: 8px;
    font-size: 13px;
    line-height: 1.45;
    color: #475569;
  }}
</style>
</head>
<body>
  <section class="chapter-card">
    <div class="meta"><span class="number">第 {chapter_number} 章</span>{volume_badge}</div>
    <h3 class="title">{title}</h3>
    <p class="goal">{goal}</p>
    {hook_html}
  </section>
</body>
</html>
"""


def _render_debug(result: dict[str, Any]) -> None:
    sections = [
        ("Story Request", result.get("story_request")),
        ("Story Context", result.get("story_context")),
        ("Chapter Plan", result.get("chapter_plan")),
        ("Scene Plan", result.get("scene_plan")),
        ("Scene Drafts", result.get("scene_drafts")),
        ("Workflow Trace", result.get("workflow_trace")),
    ]
    for label, value in sections:
        with st.expander(label):
            if isinstance(value, (dict, list)):
                st.json(value, expanded=False)
            else:
                st.write(value or "无")


def _memory_summary(memory: dict[str, Any]) -> dict[str, int]:
    return {
        "planned_chapters": len(memory.get("chapter_plan", {}).get("planned_chapters", [])),
        "chapter_summaries": len(memory.get("chapter_summaries", [])),
        "characters": len(memory.get("characters", {}).get("characters", [])),
        "foreshadowing": len(memory.get("foreshadowing", {}).get("items", [])),
    }


def _safe_relative_path(path: str, root: str | Path = ".") -> str:
    try:
        return str(Path(path).resolve().relative_to(Path(root).resolve()))
    except ValueError:
        return str(Path(path))


if __name__ == "__main__":
    main()
