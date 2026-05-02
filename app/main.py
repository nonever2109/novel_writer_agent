import argparse

from app import config
from app.graph.workflow import run_workflow
from app.services.memory_service import ensure_default_memory
from app.services.output_service import write_run_outputs
from app.services.outline_service import generate_story_outline
from app.utils.console import log_info, log_step


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the novel writer agent CLI.")
    subparsers = parser.add_subparsers(dest="command")

    outline_parser = subparsers.add_parser("outline", help="生成或更新故事大纲与故事记忆。")
    outline_parser.add_argument("--input", dest="user_input", required=True, help="小说项目创作需求。")
    outline_parser.add_argument("--memory-dir", default=config.NOVEL_MEMORY_DIR, help="故事记忆目录。")
    outline_parser.add_argument("--chapters", type=int, default=30, help="要生成的逐章大纲数量，默认 30。")

    chapter_parser = subparsers.add_parser("chapter", help="生成单章正文并更新故事记忆。")
    _add_chapter_args(chapter_parser)

    auto_parser = subparsers.add_parser("auto", help="先生成大纲，再生成第一章。")
    auto_parser.add_argument("--outline-input", required=True, help="小说项目创作需求。")
    auto_parser.add_argument("--chapter-input", help="第一章写作需求。")
    auto_parser.add_argument("--chapters", type=int, default=30, help="要生成的逐章大纲数量，默认 30。")
    auto_parser.add_argument("--memory-dir", default=config.NOVEL_MEMORY_DIR, help="故事记忆目录。")
    auto_parser.add_argument("--output-dir", default=config.NOVEL_OUTPUT_DIR, help="运行产物输出目录。")
    auto_parser.add_argument("--init-memory", action="store_true", help="创建缺失的故事记忆默认文件。")

    # Backward compatible default: no subcommand means chapter mode.
    _add_chapter_args(parser)
    return parser.parse_args()


def _add_chapter_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--input",
        dest="user_input",
        help="本章写作需求，例如：第1章，写主角抵达旧城并发现线索。",
    )
    parser.add_argument("--memory-dir", default=config.NOVEL_MEMORY_DIR, help="故事记忆目录。")
    parser.add_argument("--output-dir", default=config.NOVEL_OUTPUT_DIR, help="运行产物输出目录。")
    parser.add_argument(
        "--init-memory",
        action="store_true",
        help="创建缺失的故事记忆默认文件。",
    )


def main() -> None:
    args = parse_args()
    command = args.command or "chapter"

    if command == "outline":
        _run_outline(args)
        return
    if command == "auto":
        _run_auto(args)
        return
    _run_chapter(args)


def _run_outline(args: argparse.Namespace) -> None:
    log_step("1/2", f"生成故事大纲 (provider={config.PROVIDER})")
    outline = generate_story_outline(args.user_input, args.memory_dir, target_chapter_count=args.chapters)
    log_step("2/2", "完成")
    print("\n===== OUTLINE READY =====\n")
    print(f"memory_dir: {args.memory_dir}")
    print(f"planned_chapters: {len(outline.get('chapter_plan', {}).get('planned_chapters', []))}")


def _run_auto(args: argparse.Namespace) -> None:
    if args.init_memory:
        ensure_default_memory(args.memory_dir)
        log_info(f"已初始化故事记忆目录：{args.memory_dir}")

    log_step("1/4", f"生成故事大纲 (provider={config.PROVIDER})")
    generate_story_outline(args.outline_input, args.memory_dir, target_chapter_count=args.chapters)

    chapter_input = args.chapter_input or "第1章，承接大纲开局，建立主角处境并投放主线线索。"
    log_step("2/4", "运行第一章工作流")
    result = _invoke_chapter(chapter_input, args.memory_dir, args.output_dir)

    log_step("3/4", "写入运行产物")
    output_path = write_run_outputs(result, args.output_dir)
    log_step("4/4", "完成")
    _print_chapter_result(result, output_path)


def _run_chapter(args: argparse.Namespace) -> None:
    if args.init_memory:
        ensure_default_memory(args.memory_dir)
        log_info(f"已初始化故事记忆目录：{args.memory_dir}")

    user_input = args.user_input or "第1章，写主角抵达旧城，发现一个会影响主线的新线索。"
    log_step("1/3", f"运行小说章节工作流 (provider={config.PROVIDER})")
    result = _invoke_chapter(user_input, args.memory_dir, args.output_dir)

    log_step("2/3", "写入运行产物")
    output_path = write_run_outputs(result, args.output_dir)

    log_step("3/3", "完成")
    _print_chapter_result(result, output_path)


def _invoke_chapter(user_input: str, memory_dir: str, output_dir: str) -> dict:
    return run_workflow(
        {
            "user_input": user_input,
            "memory_dir": memory_dir,
            "output_dir": output_dir,
        }
    )


def _print_chapter_result(result: dict, output_path) -> None:
    print("\n===== FINAL CHAPTER =====\n")
    print(result.get("final_chapter", ""))
    print("\n===== OUTPUT DIR =====\n")
    print(output_path)
    print("\n===== MEMORY ARCHIVE =====\n")
    print(result.get("chapter_archive", {}).get("archive_path", ""))


if __name__ == "__main__":
    main()
