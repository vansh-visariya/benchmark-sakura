"""Command-line interface for benchmark-sakura."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from config import load_config
from detect import detect
from runner import Runner
from submit import submit_result


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
        default="all",
        help="Comma-separated task tags (all must match). Default: all",
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

    sub.add_parser("list", help="List tasks that would run for the configured tags")
    sub.add_parser("detect", help="Print detected hardware (anti-cheat probe)")

    args = parser.parse_args(argv)
    config = load_config()

    if args.command == "detect":
        print(json.dumps(detect(config).to_dict(), indent=2))
        return 0

    runner = Runner.from_config(config)

    if args.command == "list":
        tasks = runner.list_tasks()
        for task in tasks:
            tags = ", ".join(task.tags)
            print(f"{task.id:40} {task.category:10} [{tags}]")
        print(f"\n{len(tasks)} task(s)")
        return 0

    if args.command == "run":
        tags = tuple(t.strip() for t in args.tags.split(",") if t.strip())
        print(f"Running {len(runner.manifest.select(tags))} task(s) with model {args.model!r}...")
        result = runner.run(model=args.model, system_prompt=args.system, tags=tags)
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

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
