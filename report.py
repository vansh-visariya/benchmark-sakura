"""Generate Markdown reports from Sakura benchmark run results."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_run_data(target: str | Path | dict) -> dict[str, Any]:
    if isinstance(target, dict):
        return target
    path = Path(target)
    if not path.exists():
        raise FileNotFoundError(f"Result file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def generate_markdown_report(data: dict[str, Any]) -> str:
    """Generate a clean Markdown report from a benchmark run."""
    model = data.get("model", "Unknown Model")
    version = data.get("version", "0.1.0")
    metrics = data.get("metrics", {})
    hardware = data.get("hardware", {})
    task_results = data.get("task_results", [])

    lines: list[str] = []
    lines.append(f"# Sakura Benchmark Report: `{model}`\n")
    lines.append(f"- **Benchmark Version**: `{version}`")
    lines.append(f"- **Platform**: `{hardware.get('platform', 'unknown')}`")
    gpu_name = (hardware.get("gpus") or [{}])[0].get("name", "CPU only")
    lines.append(f"- **Primary GPU**: `{gpu_name}`")
    lines.append(f"- **CPU Cores**: `{hardware.get('cpu_cores', 'N/A')}`")
    lines.append(f"- **Host RAM**: `{hardware.get('ram_total_gb', 'N/A')} GB`\n")

    # High-level metrics
    pass_rate = metrics.get("pass_rate", 0.0) * 100
    solved = metrics.get("solved_count", 0)
    total = metrics.get("task_count", len(task_results))
    throughput = metrics.get("throughput_tokens_per_sec", 0.0)
    avg_ttft = metrics.get("avg_time_to_first_token_ms", 0.0)
    total_time = metrics.get("total_time_s", 0.0)

    lines.append("## Overall Metrics\n")
    lines.append("| Metric | Value |")
    lines.append("| :--- | :--- |")
    lines.append(f"| **Pass Rate** | **{pass_rate:.1f}%** ({solved}/{total}) |")
    lines.append(f"| **Throughput** | **{throughput:.2f} tokens/s** |")
    lines.append(f"| **Avg Time to First Token** | **{avg_ttft:.1f} ms** |")
    lines.append(f"| **Total Run Duration** | **{total_time:.2f} s** |")
    lines.append(f"| **Execution Errors** | `{metrics.get('errors', 0)}` |")
    lines.append("")

    # Category breakdown
    cat_rates = metrics.get("category_pass_rate", {})
    if cat_rates:
        lines.append("## Category Breakdown\n")
        lines.append("| Category | Pass Rate |")
        lines.append("| :--- | :--- |")
        for cat, rate in sorted(cat_rates.items()):
            lines.append(f"| `{cat}` | {rate * 100:.1f}% |")
        lines.append("")

    # Task Results Table
    if task_results:
        lines.append("## Task-by-Task Results\n")
        lines.append("| Task ID | Category | Status | Solved Tests | Failed Tests |")
        lines.append("| :--- | :--- | :---: | :--- | :--- |")
        for tr in task_results:
            status = "✅ PASS" if tr.get("passed") else "❌ FAIL"
            tid = tr.get("task_id", "-")
            cat = tr.get("category", "-")
            p_tests = len(tr.get("passed_tests", []))
            f_tests = len(tr.get("failed_tests", []))
            lines.append(f"| `{tid}` | `{cat}` | {status} | {p_tests} | {f_tests} |")
        lines.append("")

    # Failure Details
    failing_tasks = [t for t in task_results if not t.get("passed")]
    if failing_tasks:
        lines.append("## Failure & Error Details\n")
        for tr in failing_tasks:
            tid = tr.get("task_id")
            details = tr.get("test_details", [])
            lines.append(f"### `{tid}`\n")
            if details:
                for d in details:
                    lines.append(f"- **Test `{d.get('name')}`** (`{d.get('status')}`):")
                    if d.get("detail"):
                        lines.append(f"  ```\n  {d.get('detail')}\n  ```")
            else:
                lines.append("- No explicit test failure trace provided.")
            lines.append("")

    return "\n".join(lines)
