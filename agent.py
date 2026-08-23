"""Terminal-agent benchmark loop.

Where :class:`sakura.runner.Runner` does one-shot code generation, this module
drives a model as an *agent*: it talks to the model over several turns, executes
the shell commands the model requests inside the sandbox, and feeds the
observations back. A single episode ends when the model stops emitting tool
calls or the step budget is exhausted; hidden tests are then installed and run
to decide solved / not-solved.

The loop is transport-agnostic: it only needs an object with a ``chat()``
method matching the shape of :class:`models.OllamaClient` and a :class:`Sandbox`
with ``exec_shell``/``install_files``. Both are injected, which is what makes the
loop unit-testable with fakes.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from config import Config
from models import BASH_TOOL_SPEC, ChatTurnResult
from sandbox import ExecutionOutcome, Sandbox, TESTS_DIR, WORKSPACE_DIR
from task import Task

# Cap observation size so a verbose command (e.g. ``git diff`` of a big file)
# cannot blow up the model's context window mid-episode.
MAX_OBS_CHARS = 4000


@dataclass
class EpisodeResult:
    """The scored outcome of one terminal-agent episode."""

    solved: bool | None
    steps_used: int
    trajectory: list[dict] = field(default_factory=list)
    tokens_prompt: int = 0
    tokens_output: int = 0
    wall_time_s: float = 0.0
    score_error: str = ""


class TerminalAgent:
    """Runs a model as a terminal agent inside the sandbox."""

    def __init__(self, client, sandbox: Sandbox, config: Config):
        self.client = client
        self.sandbox = sandbox
        self.config = config

    def run_episode(self, task: Task, model: str) -> EpisodeResult:
        """Run one terminal task end to end and return its scored outcome."""
        if task.kind != "terminal":
            raise ValueError(f"TerminalAgent can only run terminal tasks, got {task.kind!r}")
        if not task.tests_cmd:
            raise ValueError(f"terminal task {task.id!r} is missing tests_cmd")

        max_steps = min(task.max_steps or self.config.agent_max_steps, self.config.agent_max_steps)
        messages: list[dict] = [
            {"role": "system", "content": _system_prompt(max_steps)},
            {"role": "user", "content": task.prompt},
        ]

        trajectory: list[dict] = []
        tokens_prompt = 0
        tokens_output = 0
        start = time.monotonic()

        for step in range(max_steps):
            turn = self.client.chat(messages, model, tools=[BASH_TOOL_SPEC])
            tokens_prompt += turn.prompt_tokens
            tokens_output += turn.output_tokens
            messages.append(_assistant_message(turn))

            if not turn.tool_calls:
                break  # model considers the task done

            command = _extract_command(turn.tool_calls[0])
            if command is None:
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Invalid tool call: your `bash` arguments were missing or "
                            "malformed. Respond with exactly one bash tool call, e.g. "
                            "bash {\"command\": \"ls\"}."
                        ),
                    }
                )
                continue

            result = self.sandbox.exec_shell(command)
            messages.append({"role": "tool", "content": _format_observation(result, command)})
            trajectory.append(
                {
                    "step": step + 1,
                    "command": command,
                    "stdout": result.stdout[:MAX_OBS_CHARS],
                    "stderr": result.stderr[:MAX_OBS_CHARS],
                    "exit_code": result.exit_code,
                }
            )

        solved, score_error = self._score(task)
        return EpisodeResult(
            solved=solved,
            steps_used=len(trajectory),
            trajectory=trajectory,
            tokens_prompt=tokens_prompt,
            tokens_output=tokens_output,
            wall_time_s=round(time.monotonic() - start, 2),
            score_error=score_error,
        )

    def _score(self, task: Task) -> tuple[bool | None, str]:
        """Install hidden tests and run the verification command.

        Hidden test files are copied in only here -- after the episode's last
        turn -- so the model never observed them mid-run. An environment-level
        failure during scoring is reported as ``(None, error)`` so the agent is
        not penalized for harness breakage; the tests existing but failing is
        simply ``(False, "")``.
        """
        try:
            if task.test_files:
                self.sandbox.install_files(task.test_files, dest=TESTS_DIR)
            outcome = self.sandbox.exec_shell(task.tests_cmd or "", cwd=WORKSPACE_DIR)
        except Exception as exc:  # noqa: BLE001 - scoring must never crash the run
            return None, f"scoring environment error: {exc}"

        if outcome.outcome is ExecutionOutcome.OK:
            return True, ""
        if outcome.outcome in (
            ExecutionOutcome.TIMEOUT,
            ExecutionOutcome.MEMORY_LIMIT,
            ExecutionOutcome.SANDBOX_ERROR,
        ):
            return None, f"scoring failed in the environment: {outcome.error or outcome.outcome.value}"
        return False, ""


def _system_prompt(max_steps: int) -> str:
    return (
        "You are a terminal agent working inside a Linux sandbox at /workspace. "
        "You have a `bash` tool that runs shell commands and returns stdout, "
        "stderr, and the exit code. Files you create persist within /workspace. "
        f"You may take up to {max_steps} tool calls. When you believe the task is "
        "complete, reply WITHOUT making a tool call. Each command runs under a "
        "timeout and the filesystem is otherwise read-only."
    )


def _assistant_message(turn: ChatTurnResult) -> dict:
    msg: dict = {"role": "assistant", "content": turn.text or ""}
    calls = [
        {
            "function": {
                "name": call.name,
                "arguments": call.arguments,
            }
        }
        for call in turn.tool_calls
    ]
    if calls:
        msg["tool_calls"] = calls
    return msg


def _extract_command(call) -> str | None:
    raw = call.arguments.get("command")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return None


def _format_observation(result, command: str) -> str:
    def _cut(value: str) -> str:
        if len(value) > MAX_OBS_CHARS:
            tail = len(value) - MAX_OBS_CHARS
            return value[:MAX_OBS_CHARS] + f"\n...[truncated {tail} chars...]"
        return value

    return (
        f"exit_code: {result.exit_code}\n"
        f"stdout:\n{_cut(result.stdout)}\n"
        f"stderr:\n{_cut(result.stderr)}"
    )
