"""Tests for runner dispatch + per-task fault tolerance on terminal tasks."""
import pytest

from config import Config
from detect import HardwareReport
from runner import Runner
from sandbox import ExecutionOutcome, ExecutionResult
from task import Manifest, Task


def _terminal_task() -> Task:
    return Task(
        id="t1", category="bugfix", prompt="fix /workspace/app.py",
        reference="", tests={}, kind="terminal",
        tests_cmd="python /opt/tests/check.py", tags=("all", "terminal"),
    )


class _ExplodingClient:
    """Client whose chat() (used by terminal tasks) always raises."""

    def chat(self, messages, model, tools=None):
        raise RuntimeError("model server exploded")


class _FakeSandbox:
    def __init__(self, exec_results):
        self._results = list(exec_results)
        self.running = False

    def start(self):
        self.running = True

    def close(self):
        pass

    def reset_workspace(self):
        pass

    def install_files(self, files, dest):
        pass

    def exec_shell(self, command, cwd="/workspace"):
        return self._results.pop(0) if self._results else ExecutionResult(ExecutionOutcome.OK, exit_code=0)


class _FakeExecutor:
    def __init__(self, exec_results=None):
        self.sandbox = _FakeSandbox(exec_results or [])

    def close(self):
        self.sandbox.close()


def _hardware() -> HardwareReport:
    return HardwareReport(
        gpus=[], cpu_model="x", cpu_cores=1, ram_total_mb=1, ram_available_mb=1,
        platform="p", os_release="o", python_version="3.13", detected_at="2024-01-01T00:00:00Z",
    )


class _ScriptedClient:
    """Client that returns scripted chat turns for terminal tasks."""

    def __init__(self, turns):
        self.turns = list(turns)

    def chat(self, messages, model, tools=None):
        return self.turns.pop(0)


def test_runner_continues_past_failed_task():
    manifest = Manifest([_terminal_task()])
    runner = Runner(
        manifest=manifest,
        client=_ExplodingClient(),
        executor=_FakeExecutor(),
        hardware=_hardware(),
        config=Config(),
    )
    result = runner.run(model="m")
    # The exception was caught, recorded as ERROR, and the run survived.
    assert len(result.task_results) == 1
    tr = result.task_results[0]
    assert tr["passed"] is False
    assert tr["test_details"][0]["status"] == "error"
    assert "model server exploded" in tr["test_details"][0]["detail"]


def test_runner_runs_terminal_task_successfully():
    from models import ChatTurnResult, ToolCall

    turns = [
        ChatTurnResult(text="ok", tool_calls=[ToolCall("bash", {"command": "echo hi"})],
                       prompt_tokens=3, output_tokens=1, time_to_first_token=0.01, total_time=0.2),
        ChatTurnResult(text="", tool_calls=[],  # agent declares done
                       prompt_tokens=1, output_tokens=1, time_to_first_token=0.005, total_time=0.1),
    ]
    exec_results = [
        ExecutionResult(outcome=ExecutionOutcome.OK, stdout="hi", exit_code=0, elapsed_seconds=0.1),
        ExecutionResult(outcome=ExecutionOutcome.OK, exit_code=0, elapsed_seconds=0.05),  # scorer
    ]
    manifest = Manifest([_terminal_task()])
    runner = Runner(
        manifest=manifest,
        client=_ScriptedClient(turns),
        executor=_FakeExecutor(exec_results),
        hardware=_hardware(),
        config=Config(),
    )
    result = runner.run(model="m")
    tr = result.task_results[0]
    assert tr["passed"] is True
    assert tr["steps_used"] == 1
    assert tr["tokens_output"] == 2
