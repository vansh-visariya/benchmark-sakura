"""Turns a model's answer into a scored task result.

Two kinds of task are supported and handled distinctly:

* **Python tasks** -- the model produces Python source. We run it (and a
  reference solution) inside the sandbox via a fixed driver that reads
  ``{"code", "tests"}`` from stdin and prints a ``{"test": "pass"/"fail"}`` map.
  Transporting the model's output over stdin (never a shell argument) means the
  untrusted text is only ever data.
* **SQL tasks** -- the model produces a SQL query string. We execute it against
  an in-memory SQLite database and compare the rows to the expected result. SQL
  is deterministic and poses no shell/FS risk, so it runs locally without the
  sandbox.

Scoring is strict: a task passes only if every test passes.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field

from config import Config
from task import Task
from scoring import TaskResult, TestResult, TestStatus, score_task
from sandbox import Sandbox, ExecutionOutcome, ExecutionResult

DRIVER_PATH = "/tmp/driver.py"


@dataclass
class CodeContext:
    """Whatever the model produced, plus the environment to evaluate it in.

    ``source`` is the model's answer: Python code for Python tasks, a SQL query
    string for SQL tasks.
    """

    source: str
    tests: dict[str, str]
    sql_schema: str | None = None
    sql_setup: str | None = None
    expected: list[list] | None = None
    reference: str | None = None


@dataclass
class ExecutorResult:
    """The task-level outcome of running one :class:`CodeContext`."""

    passed: bool
    test_results: list[TestResult] = field(default_factory=list)
    error: str = ""


class Executor:
    """Executes code contexts in the sandbox."""

    def __init__(self, config: Config):
        self.config = config
        self.sandbox = Sandbox(config)

    def start(self) -> "Executor":
        self.sandbox.start()
        return self

    def execute(self, context: CodeContext) -> ExecutorResult:
        """Run the model's answer and score it."""
        if context.sql_schema is not None:
            return self._run_sql(context)
        if self.sandbox._container is None:
            self.sandbox.start()
        return self._run_python(context)

    def _run_python(self, context: CodeContext) -> ExecutorResult:
        # First run the reference to confirm the sandbox can execute Python at
        # all; a failure here is a broken environment, not a model failure.
        reference_payload = _payload(context.reference or context.source, {})
        reference_result = self.sandbox.execute_payload(reference_payload)
        if reference_result.outcome not in (ExecutionOutcome.OK, ExecutionOutcome.RUNTIME_ERROR):
            return ExecutorResult(
                passed=False,
                error=f"Sandbox cannot run Python: {reference_result.outcome.name}",
            )

        generated_payload = _payload(context.source, context.tests)
        generated_result = self.sandbox.execute_payload(generated_payload)
        test_results = _parse_python_results(context.tests, generated_result)
        passed = bool(test_results) and all(tr.status is TestStatus.PASS for tr in test_results)
        return ExecutorResult(passed=passed, test_results=test_results)

    def _run_sql(self, context: CodeContext) -> ExecutorResult:
        conn = sqlite3.connect(":memory:")
        try:
            if context.sql_schema:
                conn.executescript(context.sql_schema)
            if context.sql_setup:
                conn.executescript(context.sql_setup)

            # Validate the task by running the reference query first.
            if context.reference:
                conn.execute(context.reference).fetchall()

            rows = conn.execute(context.source).fetchall()
            if context.expected is None:
                return ExecutorResult(passed=False, error="SQL task is missing an 'expected' field")
            main = TestResult(
                name="main",
                status=TestStatus.PASS if rows == context.expected else TestStatus.FAIL,
                detail=f"expected {context.expected}, got {rows}",
            )
            return ExecutorResult(passed=main.status is TestStatus.PASS, test_results=[main])
        except sqlite3.Error as exc:
            return ExecutorResult(passed=False, error=f"SQL execution failed: {exc}")
        finally:
            conn.close()

    def close(self) -> None:
        self.sandbox.close()


def _payload(source: str, tests: dict[str, str]) -> str:
    return json.dumps({"code": source, "tests": tests})


def _parse_python_results(tests: dict[str, str], result: ExecutionResult) -> list[TestResult]:
    try:
        parsed = json.loads(result.stdout)
    except (ValueError, AttributeError):
        return [TestResult(name=name, status=TestStatus.ERROR, detail="no result produced") for name in tests]

    results = []
    for name in tests:
        entry = parsed.get(name)
        if not isinstance(entry, dict):
            results.append(TestResult(name=name, status=TestStatus.ERROR, detail="malformed result"))
            continue
        if entry.get("status") == "pass":
            results.append(TestResult(name=name, status=TestStatus.PASS))
        elif entry.get("status") == "fail":
            results.append(TestResult(name=name, status=TestStatus.FAIL, detail=entry.get("detail", "")))
        else:
            results.append(
                TestResult(name=name, status=TestStatus.ERROR, detail=entry.get("detail", "unknown error"))
            )
    return results


def run_task(task: Task, generated_source: str, executor: Executor) -> TaskResult:
    """Run one task: build the context, execute, and score.

    Returns a :class:`TaskResult`. If the environment cannot run the task (e.g.
    the reference fails to execute), the result is flagged via ``passed`` being
    False so the runner can report a broken task separately from a genuine model
    failure.
    """
    context = CodeContext(
        source=generated_source,
        tests=task.tests,
        sql_schema=task.sql_schema,
        sql_setup=task.sql_setup,
        expected=task.expected,
        reference=task.reference,
    )
    execution = executor.execute(context)
    if not execution.passed:
        return score_task(
            task,
            [TestResult(name=name, status=TestStatus.ERROR, detail=execution.error) for name in task.tests],
        )
    return score_task(task, execution.test_results)
