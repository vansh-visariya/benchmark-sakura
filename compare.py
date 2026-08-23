"""Compare two Sakura benchmark run results side-by-side."""
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


def _format_diff(val1: float, val2: float, suffix: str = "", higher_is_better: bool = True) -> str:
    diff = val2 - val1
    if abs(diff) < 1e-4:
        return "="
    sign = "+" if diff > 0 else ""
    return f"{sign}{diff:.2f}{suffix}"


def compare_runs(run1: dict[str, Any], run2: dict[str, Any]) -> str:
    """Generate a formatted comparison between two run results."""
    m1_name = run1.get("model", "Run 1")
    m2_name = run2.get("model", "Run 2")

    met1 = run1.get("metrics", {})
    met2 = run2.get("metrics", {})

    hw1 = run1.get("hardware", {})
    hw2 = run2.get("hardware", {})

    lines: list[str] = []
    lines.append("=" * 80)
    lines.append(f" SAKURA RUN COMPARISON: {m1_name} vs {m2_name}")
    lines.append("=" * 80)

    # Overview table
    lines.append("\n--- Overall Metrics ---")
    lines.append(f"{'Metric':<28} {'Run 1 (' + m1_name + ')':<24} {'Run 2 (' + m2_name + ')':<24} {'Delta'}")
    lines.append("-" * 85)

    p1 = met1.get("pass_rate", 0.0) * 100
    p2 = met2.get("pass_rate", 0.0) * 100
    s1 = f"{p1:.1f}% ({met1.get('solved_count', 0)}/{met1.get('task_count', 0)})"
    s2 = f"{p2:.1f}% ({met2.get('solved_count', 0)}/{met2.get('task_count', 0)})"
    lines.append(f"{'Pass Rate':<28} {s1:<24} {s2:<24} {_format_diff(p1, p2, '%')}")

    tp1 = met1.get("throughput_tokens_per_sec", 0.0)
    tp2 = met2.get("throughput_tokens_per_sec", 0.0)
    lines.append(f"{'Throughput':<28} {f'{tp1:.2f} tok/s':<24} {f'{tp2:.2f} tok/s':<24} {_format_diff(tp1, tp2, ' tok/s')}")

    ttft1 = met1.get("avg_time_to_first_token_ms", 0.0)
    ttft2 = met2.get("avg_time_to_first_token_ms", 0.0)
    lines.append(f"{'Avg Time to First Token':<28} {f'{ttft1:.1f} ms':<24} {f'{ttft2:.1f} ms':<24} {_format_diff(ttft1, ttft2, ' ms', higher_is_better=False)}")

    t1 = met1.get("total_time_s", 0.0)
    t2 = met2.get("total_time_s", 0.0)
    lines.append(f"{'Total Execution Time':<28} {f'{t1:.2f} s':<24} {f'{t2:.2f} s':<24} {_format_diff(t1, t2, ' s', higher_is_better=False)}")

    # Hardware Info
    lines.append("\n--- Hardware Specs ---")
    gpu1 = (hw1.get("gpus") or [{}])[0].get("name", "CPU only")
    gpu2 = (hw2.get("gpus") or [{}])[0].get("name", "CPU only")
    lines.append(f"{'GPU':<20} {str(gpu1):<30} {str(gpu2)}")
    lines.append(f"{'CPU Cores':<20} {str(hw1.get('cpu_cores', '-')):<30} {str(hw2.get('cpu_cores', '-'))}")
    lines.append(f"{'RAM':<20} {str(hw1.get('ram_total_gb', '-')) + ' GB':<30} {str(hw2.get('ram_total_gb', '-')) + ' GB'}")
    lines.append(f"{'Platform':<20} {str(hw1.get('platform', '-')):<30} {str(hw2.get('platform', '-'))}")

    # Category breakdown
    cat1 = met1.get("category_pass_rate", {})
    cat2 = met2.get("category_pass_rate", {})
    all_cats = sorted(set(cat1.keys()) | set(cat2.keys()))

    if all_cats:
        lines.append("\n--- Category Breakdown ---")
        lines.append(f"{'Category':<20} {'Run 1 Pass %':<18} {'Run 2 Pass %':<18} {'Delta'}")
        lines.append("-" * 65)
        for cat in all_cats:
            cp1 = cat1.get(cat, 0.0) * 100
            cp2 = cat2.get(cat, 0.0) * 100
            lines.append(f"{cat:<20} {f'{cp1:.1f}%':<18} {f'{cp2:.1f}%':<18} {_format_diff(cp1, cp2, '%')}")

    # Per-task matrix
    tasks1 = {t.get("task_id", ""): t for t in run1.get("task_results", [])}
    tasks2 = {t.get("task_id", ""): t for t in run2.get("task_results", [])}
    all_task_ids = sorted(set(tasks1.keys()) | set(tasks2.keys()))

    if all_task_ids:
        lines.append("\n--- Task Matrix ---")
        lines.append(f"{'Task ID':<36} {'Run 1':<12} {'Run 2':<12} {'Match?'}")
        lines.append("-" * 70)
        for tid in all_task_ids:
            res1 = tasks1.get(tid)
            res2 = tasks2.get(tid)

            st1 = "PASS" if (res1 and res1.get("passed")) else ("FAIL" if res1 else "N/A")
            st2 = "PASS" if (res2 and res2.get("passed")) else ("FAIL" if res2 else "N/A")

            match = "✓ Same" if st1 == st2 else ("▲ Improved" if st2 == "PASS" else "▼ Regressed")
            lines.append(f"{tid:<36} {st1:<12} {st2:<12} {match}")

    lines.append("=" * 80)
    return "\n".join(lines)
