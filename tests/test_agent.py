"""Tests for the terminal-agent episode loop (agent.py)."""
import pytest

from agent import TerminalAgent, MAX_OBS_CHARS
from config import Config
from models import ChatTurnResult, ToolCall
from sandbox import ExecutionOutcome, ExecutionResult
from task import Task


def _turn(tool_call=None, text="") -> ChatTurnResult:
    calls = [ToolCall(name="bash", arguments={"command": tool_call})] if tool_call else []
    return ChatTurnResult(
        text=text, tool_calls=calls, prompt_tokens=2, output_tokens=1,
        time_to_first_token=0.01, total_time=0.2,
    )


def _terminal_task(test_files=None, max_steps=None) -> Task:
    return Task(
        id="t1", category="bugfix", prompt="Fix the bug in /workspace/app.py",
        reference="", tests={}, kind="terminal",
        tests_cmd="python /opt/tests/check.py",
        test_files=test_files or {"check.py": "assert True"},
        tags=("all", "terminal"), max_steps=max_steps,
    )


class _FakeChatClient:
    def __init__(self, turns):
        self.turns = list(turns)
        self.calls = []

    def chat(self, messages, model, tools=None):
        self.calls.append({"messages": messages, "model": model, "tools": tools})
        return self.turns.pop(0)


class _FakeSandbox:
    def __init__(self, exec_results):
        self._results = list(exec_results)
        self.running = False
        self.started = False
        self.calls = []
        self.installed = []

    def start(self):
        self.started = True
        self.running = True
        self.calls.append(("start",))

    def close(self):
        pass

    def reset_workspace(self):
        self.calls.append(("reset_workspace",))

    def install_files(self, files, dest):
        self.installed.append((dest, files))
        self.calls.append(("install_files", dest))

    def exec_shell(self, command, cwd="/workspace"):
        self.calls.append(("exec_shell", command))
        return self._results.pop(0)


def _exec(outcome, stdout="", stderr="", exit_code=0, error="") -> ExecutionResult:
    return ExecutionResult(
        outcome=outcome, stdout=stdout, stderr=stderr, exit_code=exit_code,
        error=error, elapsed_seconds=0.05,
    )


def _done_turns(first_call):
    """One tool-calling turn, then a silent stop turn."""
    return [_turn(tool_call=first_call, text="working"), _turn(text="done")]


def test_agent_solves_when_tests_pass():
    turns = _done_turns("echo hello")
    exec_results = [
        _exec(ExecutionOutcome.OK, stdout="hello", exit_code=0),   # agent's command
        _exec(ExecutionOutcome.OK, exit_code=0),                     # scoring tests_cmd
    ]
    sandbox = _FakeSandbox(exec_results)
    agent = TerminalAgent(_FakeChatClient(turns), sandbox, Config())
    ep = agent.run_episode(_terminal_task(), "m")

    assert ep.solved is True
    assert ep.steps_used == 1
    assert ep.tokens_prompt == 4 and ep.tokens_output == 2  # 2+2 / 1+1
    # tests must be installed AFTER the agent stopped issuing commands
    names = [c[0] for c in sandbox.calls]
    assert names.index("exec_shell") < names.index("install_files")
    assert sandbox.installed[0][0] == "/opt/tests"


def test_agent_stops_after_first_tool_call_when_no_second_call():
    turns = _done_turns("ls")
    exec_results = [
        _exec(ExecutionOutcome.OK, stdout="a.py", exit_code=0),
        _exec(ExecutionOutcome.OK, exit_code=0),
    ]
    sandbox = _FakeSandbox(exec_results)
    client = _FakeChatClient(turns)
    agent = TerminalAgent(client, sandbox, Config())
    ep = agent.run_episode(_terminal_task(), "m")
    assert ep.solved is True
    assert ep.steps_used == 1
    assert len(client.turns) == 0  # both turns consumed


def test_agent_respects_max_steps():
    task = _terminal_task(max_steps=2)
    client = _FakeChatClient([
        _turn(tool_call="echo 1"), _turn(tool_call="echo 2"), _turn(tool_call="echo 3"),
    ])
    exec_results = [
        _exec(ExecutionOutcome.OK, exit_code=0),
        _exec(ExecutionOutcome.OK, exit_code=0),
        _exec(ExecutionOutcome.OK, exit_code=0),  # scoring
    ]
    sandbox = _FakeSandbox(exec_results)
    agent = TerminalAgent(client, sandbox, Config())
    ep = agent.run_episode(task, "m")
    assert ep.steps_used == 2
    assert len(client.turns) == 1  # third turn never consumed (budget exhausted)


def test_agent_solved_false_when_tests_fail():
    turns = _done_turns("echo hi")
    exec_results = [
        _exec(ExecutionOutcome.OK, stdout="hi", exit_code=0),
        _exec(ExecutionOutcome.RUNTIME_ERROR, stderr="assert", exit_code=1),  # scoring fails
    ]
    sandbox = _FakeSandbox(exec_results)
    agent = TerminalAgent(_FakeChatClient(turns), sandbox, Config())
    ep = agent.run_episode(_terminal_task(), "m")
    assert ep.solved is False
    assert ep.score_error == ""


def test_agent_solved_none_on_scoring_environment_error():
    turns = _done_turns("echo hi")
    exec_results = [
        _exec(ExecutionOutcome.OK, stdout="hi", exit_code=0),
        _exec(ExecutionOutcome.SANDBOX_ERROR, error="docker exploded"),  # scoring env broke
    ]
    sandbox = _FakeSandbox(exec_results)
    agent = TerminalAgent(_FakeChatClient(turns), sandbox, Config())
    ep = agent.run_episode(_terminal_task(), "m")
    assert ep.solved is None
    assert "scoring failed in the environment" in ep.score_error


def test_trajectory_stdout_is_truncated():
    big = "x" * (MAX_OBS_CHARS + 2000)
    turns = _done_turns("cat big")
    exec_results = [
        _exec(ExecutionOutcome.OK, stdout=big, exit_code=0),
        _exec(ExecutionOutcome.OK, exit_code=0),
    ]
    sandbox = _FakeSandbox(exec_results)
    agent = TerminalAgent(_FakeChatClient(turns), sandbox, Config())
    ep = agent.run_episode(_terminal_task(), "m")
    assert len(ep.trajectory[0]["stdout"]) <= MAX_OBS_CHARS + 60
    assert ep.trajectory[0]["stdout"].startswith("x")
    assert "truncated" in ep.trajectory[0]["stdout"]


def test_agent_rejects_non_terminal_task():
    task = Task(id="t", category="codegen", prompt="p", reference="r", tests={}, kind="codegen")
    agent = TerminalAgent(_FakeChatClient([]), _FakeSandbox([]), Config())
    with pytest.raises(ValueError, match="terminal tasks"):
        agent.run_episode(task, "m")
