"""Scoring engine: turns raw test outcomes into per-task and per-run metrics.

The engine is deliberately decoupled from *how* tests are executed (Docker,
interpreter, etc.) — :class:`TestResult` is a plain dataclass that any executor
produces. That keeps the scoring logic pure and trivially unit-testable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from task import Task


class TestStatus(str, Enum):
    __test__ = False
    PASS = "pass"
    FAIL = "fail"
    ERROR = "error"  # test raised an exception or timed out


@dataclass
class TestResult:
    """The outcome of running one test against one piece of generated code."""

    __test__ = False
    name: str
    status: TestStatus
    detail: str = ""


@dataclass
class TaskResult:
    """The scored outcome of running one task."""

    task: Task
    test_results: list[TestResult]
    passed: bool = field(init=False)
    passed_tests: list[str] = field(default_factory=list, init=False)
    failed_tests: list[str] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        self.passed_tests = [tr.name for tr in self.test_results if tr.status is TestStatus.PASS]
        self.failed_tests = [tr.name for tr in self.test_results if tr.status is not TestStatus.PASS]
        self.passed = len(self.test_results) > 0 and not self.failed_tests


@dataclass
class RunMetrics:
    """Timing/throughput data captured while running a model."""

    time_to_first_token: float
    total_time: float
    output_tokens: int
    prompt_tokens: int = 0

    @property
    def throughput(self) -> float:
        """Tokens per second (0.0 if nothing was produced or no time elapsed)."""
        if self.total_time <= 0 or self.output_tokens == 0:
            return 0.0
        return self.output_tokens / self.total_time

    def to_dict(self) -> dict:
        return {
            "time_to_first_token_ms": round(self.time_to_first_token * 1000, 1),
            "total_time_ms": round(self.total_time * 1000, 1),
            "output_tokens": self.output_tokens,
            "prompt_tokens": self.prompt_tokens,
            "throughput_tokens_per_sec": round(self.throughput, 2),
        }


def score_task(task: Task, test_results: list[TestResult]) -> TaskResult:
    """Build a :class:`TaskResult` from a task and its test outcomes."""
    return TaskResult(task=task, test_results=test_results)


def summarize(results: list[TaskResult]) -> dict:
    """Aggregate per-task results into a run-level summary.

    The primary accuracy metric is the **pass rate** — the fraction of tasks
    where every test passed. This is the metric the leaderboard ranks on. We
    also surface per-category pass rates and an error count so contributors can
    see whether a low score is a model weakness or a sandbox/execution problem.
    """
    total = len(results)
    if total == 0:
        return {"task_count": 0, "pass_rate": 0.0, "errors": 0}

    solved = sum(1 for r in results if r.passed)
    errors = sum(
        1
        for r in results
        if r.test_results and any(tr.status is TestStatus.ERROR for tr in r.test_results)
    )

    by_category: dict[str, dict] = {}
    for r in results:
        agg = by_category.setdefault(r.task.category, {"total": 0, "solved": 0})
        agg["total"] += 1
        if r.passed:
            agg["solved"] += 1

    category_pass_rate = {
        cat: round(agg["solved"] / agg["total"], 4) if agg["total"] else 0.0
        for cat, agg in by_category.items()
    }

    return {
        "task_count": total,
        "solved_count": solved,
        "pass_rate": round(solved / total, 4),
        "errors": errors,
        "category_pass_rate": category_pass_rate,
    }


def normalize_task_results(results: list[TaskResult]) -> list[dict]:
    """Serialize task results for inclusion in a submission payload."""
    return [
        {
            "task_id": r.task.id,
            "category": r.task.category,
            "tags": list(r.task.tags),
            "passed": r.passed,
            "passed_tests": r.passed_tests,
            "failed_tests": r.failed_tests,
            "test_details": [
                {"name": tr.name, "status": tr.status.value, "detail": tr.detail}
                for tr in r.test_results
                if tr.status is not TestStatus.PASS and tr.detail
            ],
        }
        for r in results
    ]

