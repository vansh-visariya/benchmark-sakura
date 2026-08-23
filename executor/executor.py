"""Turns a model's answer into a scored task result.

Two kinds of task are supported and handled distinctly:

* **Python tasks** -- the model produces Python source. We run it (and a
  reference solution) inside the Docker sandbox via a fixed driver that reads
  ``{"code", "tests"}`` and prints a sentinel-delimited ``{"test": outcome}``
  map on stdout. The payload travels through the Docker API environment
  parameter, never a shell argument, so untrusted text is only ever data.
* **SQL tasks** -- the model produces a SQL query string. We execute it against
  an in-memory SQLite database guarded by an authorizer that denies filesystem
  and extension operations (``ATTACH``, ``PRAGMA``, ``load_extension``, virtual
  tables), plus a statement timeout so runaway queries cannot hang the run.
  SQL never touches the real filesystem.

Scoring is strict: a task passes only if every test passes.
"""
from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass, field

from config import Config
from task import Task
from scoring import TaskResult, TestResult, TestStatus, score_task
from sandbox import Sandbox, ExecutionOutcome, ExecutionResult

# Must match SENTINEL in docker/driver.py (the driver ships standalone in the
# image, so the constant cannot be imported from here).
SENTINEL = "SAKURA_RESULTS:"
SQL_STATEMENT_TIMEOUT_SECONDS = 5

# Authorizer action codes that could reach the host filesystem or load native
# code. DDL is intentionally allowed during the trusted schema/setup phase;
# the authorizer is installed only once untrusted SQL starts running.
# Some constants are missing on older Python builds; getattr keeps this robust.
_BLOCKED_SQL_ACTIONS = frozenset(
    code
    for code in (
        getattr(sqlite3, name, None)
        for name in (
            "SQLITE_ATTACH",
            "SQLITE_DETACH",
            "SQLITE_PRAGMA",
            "SQLITE_COPY",
            "SQLITE_CREATE_VTABLE",
            "SQLITE_DROP_VTABLE",
        )
    )
    if code is not None
)


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
        if not self.sandbox.running:
            self.sandbox.start()
        return self._run_python(context)

    def _run_python(self, context: CodeContext) -> ExecutorResult:
        # First run the reference with empty tests to confirm the sandbox can
        # execute Python at all; a failure here is a broken environment, not a
        # model failure.
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
            # Schema/setup come from trusted task files, before hardening.
            if context.sql_schema:
                conn.executescript(context.sql_schema)
            if context.sql_setup:
                conn.executescript(context.sql_setup)

            # Harden the connection before any untrusted SQL runs.
            conn.set_authorizer(_make_authorizer())
            deadline = time.monotonic() + SQL_STATEMENT_TIMEOUT_SECONDS
            conn.set_progress_handler(
                lambda: 1 if time.monotonic() > deadline else 0, 10000
            )

            # Validate the task by running the reference query first.
            if context.reference:
                conn.execute(context.reference).fetchall()

            rows = [list(row) for row in conn.execute(context.source).fetchall()]
            if context.expected is None:
                return ExecutorResult(passed=False, error="SQL task is missing an 'expected' field")
            main = TestResult(
                name="main",
                status=TestStatus.PASS if rows == context.expected else TestStatus.FAIL,
                detail=f"expected {context.expected}, got {rows}",
            )
            return ExecutorResult(passed=main.status is TestStatus.PASS, test_results=[main])
        except sqlite3.Error as exc:
            if getattr(exc, "sqlite_errorcode", None) == sqlite3.SQLITE_AUTH:
                return ExecutorResult(passed=False, error=f"Forbidden SQL operation blocked: {exc}")
            return ExecutorResult(passed=False, error=f"SQL execution failed: {exc}")
        finally:
            conn.close()

    def close(self) -> None:
        self.sandbox.close()


def _payload(source: str, tests: dict[str, str]) -> str:
    return json.dumps({"code": source, "tests": tests})


def _make_authorizer():
    def authorizer(action, arg1, arg2, db_name, trigger_name):
        if action == sqlite3.SQLITE_FUNCTION and str(arg2).lower() == "load_extension":
            return sqlite3.SQLITE_DENY
        if action in _BLOCKED_SQL_ACTIONS:
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    return authorizer


def _parse_python_results(tests: dict[str, str], result: ExecutionResult) -> list[TestResult]:
    """Translate a driver run into per-test results.

    Environment-level failures (timeout, OOM, sandbox errors) are reported as
    ERROR tests carrying the reason, so a broken sandbox never silently looks
    like a clean model failure.
    """
    if result.outcome is ExecutionOutcome.TIMEOUT:
        detail = f"execution timed out after {result.elapsed_seconds:.0f}s"
        return [TestResult(name=name, status=TestStatus.ERROR, detail=detail) for name in tests]
    if result.outcome is ExecutionOutcome.MEMORY_LIMIT:
        detail = "execution exceeded the sandbox memory limit"
        return [TestResult(name=name, status=TestStatus.ERROR, detail=detail) for name in tests]
    if result.outcome is ExecutionOutcome.SANDBOX_ERROR:
        detail = result.error or "sandbox failure"
        return [TestResult(name=name, status=TestStatus.ERROR, detail=detail) for name in tests]

    try:
        parsed = _extract_results(result.stdout)
    except ValueError as exc:
        return [
            TestResult(name=name, status=TestStatus.ERROR, detail=f"no result produced ({exc})")
            for name in tests
        ]

    results = []
    for name in tests:
        entry = parsed.get(name)
        if not isinstance(entry, dict):
            results.append(TestResult(name=name, status=TestStatus.ERROR, detail="malformed result"))
        elif entry.get("status") == "pass":
            results.append(TestResult(name=name, status=TestStatus.PASS))
        elif entry.get("status") == "fail":
            results.append(TestResult(name=name, status=TestStatus.FAIL, detail=entry.get("detail", "")))
        else:
            results.append(
                TestResult(name=name, status=TestStatus.ERROR, detail=entry.get("detail", "unknown error"))
            )
    return results


def _extract_results(stdout: str) -> dict:
    """Find the driver's sentinel line in stdout and parse its JSON map.

    Model code may print anything before the sentinel; only the sentinel line
    is protocol, so verbose-but-correct solutions score correctly.
    """
    for line in stdout.splitlines():
        stripped = line.strip()
        if stripped.startswith(SENTINEL):
            json_part = stripped[len(SENTINEL):].strip()
            return json.loads(json_part)
    raise ValueError("driver produced no sentinel line")


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
        if execution.test_results:
            return score_task(task, execution.test_results)
        return score_task(
            task,
            [TestResult(name=name, status=TestStatus.ERROR, detail=execution.error) for name in task.tests],
        )
    return score_task(task, execution.test_results)
