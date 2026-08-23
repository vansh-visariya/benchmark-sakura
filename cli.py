"""Command-line interface for benchmark-sakura."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from compare import compare_runs, load_run_data
from config import load_config
from detect import detect
from report import generate_markdown_report
from runner import Runner
from sandbox import SandboxUnavailable
from submit import submit_file, submit_result


def _build_tags_filter(
    tags: str | None = None,
    category: str | None = None,
    difficulty: str | None = None,
) -> tuple[str, ...]:
    tag_set = set()
    if tags:
        tag_set.update(t.strip() for t in tags.split(",") if t.strip())
    if category:
        tag_set.add(category.strip().lower())
    if difficulty:
        tag_set.add(difficulty.strip().lower())
    return tuple(sorted(tag_set)) if tag_set else ("all",)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="sakura",
        description="Benchmark local coding models on consumer hardware.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run_parser = sub.add_parser("run", help="Run the benchmark against a model")
    run_parser.add_argument("--model", "-m", required=True, help="Ollama model name")
    run_parser.add_argument(
        "--tags",
        default="",
        help="Comma-separated task tags (all must match). Default: all",
    )
    run_parser.add_argument(
        "--category",
        "-c",
        help="Filter by category (codegen, bugfix, sql, refactor, systems, protocol)",
    )
    run_parser.add_argument(
        "--difficulty",
        "-d",
        help="Filter by difficulty (easy, medium, hard)",
    )
    run_parser.add_argument("--output", "-o", help="Save results JSON to this path")
    run_parser.add_argument(
        "--submit",
        action="store_true",
        help="Submit results to the Sakura leaderboard after the run",
    )
    run_parser.add_argument(
        "--system",
        default="You are a helpful coding assistant. Answer with the code only.",
        help="System prompt sent to the model",
    )
    run_parser.add_argument(
        "--think",
        action="store_true",
        help="Allow the model to reason before returning its code",
    )

    list_parser = sub.add_parser("list", help="List tasks that would run for the configured tags")
    list_parser.add_argument("--tags", default="", help="Comma-separated tags")
    list_parser.add_argument("--category", "-c", help="Filter by category")
    list_parser.add_argument("--difficulty", "-d", help="Filter by difficulty")

    sub.add_parser("detect", help="Print detected hardware (anti-cheat probe)")

    submit_parser = sub.add_parser("submit", help="Submit a saved .results JSON file to the leaderboard")
    submit_parser.add_argument("file", help="Path to a results JSON file under .results/")

    compare_parser = sub.add_parser("compare", help="Compare two benchmark runs side-by-side")
    compare_parser.add_argument("run1", help="Path to first run JSON file")
    compare_parser.add_argument("run2", help="Path to second run JSON file")

    report_parser = sub.add_parser("report", help="Generate a Markdown report from a benchmark run")
    report_parser.add_argument("file", help="Path to run JSON file")
    report_parser.add_argument("--output", "-o", help="Optional output markdown file path")

    args = parser.parse_args(argv)
    config = load_config()

    if args.command == "detect":
        print(json.dumps(detect(config).to_dict(), indent=2))
        return 0

    runner = Runner.from_config(config)

    if args.command == "list":
        tags = _build_tags_filter(args.tags, args.category, args.difficulty)
        tasks = runner.manifest.select(tags)
        for task in tasks:
            tag_str = ", ".join(task.tags)
            print(f"{task.id:40} {task.category:10} [{tag_str}]")
        print(f"\n{len(tasks)} task(s)")
        return 0

    if args.command == "compare":
        try:
            r1 = load_run_data(args.run1)
            r2 = load_run_data(args.run2)
            print(compare_runs(r1, r2))
            return 0
        except Exception as exc:
            print(f"[Error] Comparison failed: {exc}", file=sys.stderr)
            return 1

    if args.command == "report":
        try:
            data = load_run_data(args.file)
            report_md = generate_markdown_report(data)
            if args.output:
                out_path = Path(args.output)
                out_path.write_text(report_md, encoding="utf-8")
                print(f"Report written to {out_path}")
            else:
                print(report_md)
            return 0
        except Exception as exc:
            print(f"[Error] Report generation failed: {exc}", file=sys.stderr)
            return 1

    if args.command == "run":
        tags = _build_tags_filter(args.tags, args.category, args.difficulty)
        selected_tasks = runner.manifest.select(tags)
        print(f"Running {len(selected_tasks)} task(s) matching tags {tags} with model {args.model!r}...")
        try:
            result = runner.run(model=args.model, system_prompt=args.system, tags=tags, think=args.think)
        except SandboxUnavailable as exc:
            print(f"\n[Error] Sandbox unavailable: {exc}\n", file=sys.stderr)
            print("Make sure Docker is running and the sandbox image is built (`docker/build.ps1` or `docker/build.sh`).", file=sys.stderr)
            return 1
        except Exception as exc:
            print(f"\n[Error] Run failed: {exc}", file=sys.stderr)
            return 1
        output_path = runner.save_result(
            result,
            path=Path(args.output) if args.output else None,
        )
        print(json.dumps(result.metrics, indent=2))
        print(f"\nSaved to {output_path}")
        if args.submit:
            try:
                url = submit_result(result, config)
                print(f"Submitted to {url}")
            except Exception as exc:
                print(f"Submit failed: {exc}", file=sys.stderr)
                return 1
        return 0

    if args.command == "submit":
        try:
            url = submit_file(Path(args.file), config)
            print(f"Submitted to {url}")
        except Exception as exc:
            print(f"Submit failed: {exc}", file=sys.stderr)
            return 1
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())

