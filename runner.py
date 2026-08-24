"""The benchmark runner.

Ties the pieces together: detect the host, load the task manifest, run each
selected task against a model, and collect timing + accuracy metrics into a
single :class:`RunResult` that can be saved locally or submitted.

The runner owns the model + executor lifecycles and is the only place that
knows *how* a task is executed. Tests exercise it with fakes injected through
the constructor.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from config import Config
from detect import HardwareReport, detect
from executor import Executor, run_task
from models import CompletionRequest, ModelVariant, OllamaClient
from sandbox import ExecutionOutcome
from scoring import (
    RunMetrics,
    TaskResult,
    TestResult,
    TestStatus,
    score_task,
    summarize,
    normalize_task_results,
)
from task import Manifest, Task

from agent import EpisodeResult, TerminalAgent


@dataclass
class TaskRun:
    """One task's scored outcome plus model timing."""

    task_result: TaskResult
    metrics: RunMetrics


@dataclass
class RunResult:
    """A complete benchmark run: everything the leaderboard needs."""

    model: str
    version: str
    hardware: dict
    metrics: dict
    task_results: list[dict]
    model_variant: ModelVariant | None = None

    def to_dict(self) -> dict:
        payload = {
            "model": self.model,
            "version": self.version,
            "hardware": self.hardware,
            "metrics": self.metrics,
            "task_results": self.task_results,
        }
        if self.model_variant is not None:
            variant = {k: v for k, v in self.model_variant.to_dict().items() if v}
            if variant:
                payload["model_variant"] = variant
        return payload


_CODE_FENCE = re.compile(r"```(?:python|py|sql)?\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)


def extract_code(text: str) -> str:
    """Pull code from markdown fences when the model wraps its answer."""
    match = _CODE_FENCE.search(text)
    if match:
        return match.group(1).strip()
    return text.strip()


def _terminal_task_result(task: Task, episode: EpisodeResult) -> TaskResult:
    """Map a terminal-agent episode into a scored :class:`TaskResult`.

    ``solved is True`` -> a single PASS; ``solved is False`` -> FAIL (the tests
    ran and the agent lost); ``solved is None`` -> ERROR (the environment itself
    broke during scoring, so the agent is not at fault).
    """
    if episode.solved is True:
        results = [TestResult(name="solution", status=TestStatus.PASS)]
    elif episode.solved is False:
        detail = episode.score_error or "tests failed"
        results = [TestResult(name="solution", status=TestStatus.FAIL, detail=detail)]
    else:
        detail = episode.score_error or "scoring environment error"
        results = [TestResult(name="solution", status=TestStatus.ERROR, detail=detail)]
    return score_task(
        task=task,
        test_results=results,
        steps_used=episode.steps_used,
        wall_time_s=episode.wall_time_s,
        tokens_prompt=episode.tokens_prompt,
        tokens_output=episode.tokens_output,
        trajectory=episode.trajectory,
    )


class Runner:
    """Executes a benchmark run against a model."""

    def __init__(
        self,
        manifest: Manifest,
        client: OllamaClient,
        executor: Executor | None,
        hardware: HardwareReport,
        config: Config | None = None,
    ):
        self.manifest = manifest
        self.client = client
        self.executor = executor
        self.hardware = hardware
        self.config = config or Config()

    @classmethod
    def from_config(cls, config: Config, client: OllamaClient | None = None) -> "Runner":
        """Build a runner for the current host.

        The executor is created lazily (it starts a Docker container) so that
        read-only operations like listing tasks don't require Docker.
        """
        hardware = detect(config)
        manifest = Manifest.load()
        client = client or OllamaClient(config.ollama_base_url, timeout=600.0)
        return cls(manifest, client, executor=None, hardware=hardware, config=config)

    def list_tasks(self) -> list[Task]:
        """Return the tasks that would be run for the configured tags."""
        return self.manifest.select(self.config.default_task_tags)

    def run(
        self,
        model: str,
        system_prompt: str = "You are a helpful coding assistant. Answer with the code only.",
        tags: tuple[str, ...] | None = None,
        think: bool = False,
    ) -> RunResult:
        """Run the benchmark and return a :class:`RunResult`.

        The executor starts the Docker sandbox on first Python task and closes
        on exit, so the caller never manages that lifecycle.
        """
        tasks = self.manifest.select(tags or self.config.default_task_tags)
        if not tasks:
            raise ValueError("No tasks selected. Check --tags or the manifest.")

        executor = self._ensure_executor()
        try:
            runs: list[TaskRun] = []
            for task in tasks:
                try:
                    runs.append(self._run_one(task, model, system_prompt, executor, think))
                except Exception as exc:  # noqa: BLE001 - keep the run alive
                    runs.append(self._error_task_run(task, exc))
        finally:
            executor.close()

        task_results = [run.task_result for run in runs]
        summary = summarize(task_results)
        metrics = {**summary, **self._aggregate_metrics(runs)}
        return RunResult(
            model=model,
            version="0.2.0",
            hardware=self.hardware.to_dict(),
            metrics=metrics,
            task_results=self._serialize_task_runs(runs),
            model_variant=self.resolve_variant(model),
        )

    def resolve_variant(self, model: str) -> ModelVariant:
        """Variant metadata for a model: explicit override, else /api/show."""
        override = self.config.model_variant
        if override:
            parts = [p.strip() for p in override.split("/") if p.strip()]
            return ModelVariant(
                quantization=parts[0] if parts else None,
                parameter_size=parts[1] if len(parts) > 1 else None,
                family=parts[2] if len(parts) > 2 else None,
            )
        try:
            return self.client.show(model)
        except Exception:  # noqa: BLE001 - metadata must never fail a run
            return ModelVariant()

    def save_result(self, result: RunResult, path: Path | None = None) -> Path:
        """Write a run result to ``.results/`` (or an explicit path)."""
        self.config.ensure_dirs()
        if path is None:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            safe_model = re.sub(r"[^\w.-]+", "_", result.model)
            path = self.config.results_dir / f"{stamp}_{safe_model}.json"
        path.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
        return path

    def _ensure_executor(self) -> Executor:
        if self.executor is None:
            self.executor = Executor(self.config)
        return self.executor

    def _run_one(
        self, task: Task, model: str, system_prompt: str, executor: Executor, think: bool
    ) -> TaskRun:
        """Run one task end to end and return scored outcome + timing."""
        if task.kind == "terminal":
            return self._run_terminal_one(task, model, executor)
        prompt = task.prompt
        if task.sql_schema:
            prompt = f"{task.prompt}\n\nDatabase schema:\n{task.sql_schema}"
        request = CompletionRequest(model=model, prompt=prompt, system=system_prompt, think=think)
        completion = self.client.complete(request)
        source = extract_code(completion.text)
        task_result = run_task(task, source, executor)
        return TaskRun(
            task_result=task_result,
            metrics=RunMetrics(
                time_to_first_token=completion.time_to_first_token,
                total_time=completion.total_time,
                output_tokens=completion.output_tokens,
                prompt_tokens=completion.prompt_tokens,
            ),
        )

    def _run_terminal_one(self, task: Task, model: str, executor: Executor) -> TaskRun:
        """Run a terminal-agent episode for a single task."""
        if not executor.sandbox.running:
            executor.sandbox.start()
        executor.sandbox.reset_workspace()
        if task.environment_files:
            executor.sandbox.install_files(task.environment_files, dest="/workspace")
        if task.setup_cmd:
            setup = executor.sandbox.exec_shell(task.setup_cmd)
            if setup.outcome is not ExecutionOutcome.OK:
                return TaskRun(
                    task_result=score_task(
                        task,
                        [TestResult(name="setup", status=TestStatus.ERROR, detail=setup.error)],
                    ),
                    metrics=RunMetrics(time_to_first_token=0.0, total_time=0.0, output_tokens=0),
                )
        episode = TerminalAgent(self.client, executor.sandbox, self.config).run_episode(task, model)
        task_result = _terminal_task_result(task, episode)
        return TaskRun(
            task_result=task_result,
            metrics=RunMetrics(
                time_to_first_token=0.0,
                total_time=episode.wall_time_s,
                output_tokens=episode.tokens_output,
                prompt_tokens=episode.tokens_prompt,
            ),
        )

    def _error_task_run(self, task: Task, exc: BaseException) -> TaskRun:
        """A failed task becomes an ERROR result rather than aborting the run."""
        return TaskRun(
            task_result=score_task(
                task,
                [TestResult(name="run", status=TestStatus.ERROR, detail=f"{type(exc).__name__}: {exc}")],
            ),
            metrics=RunMetrics(time_to_first_token=0.0, total_time=0.0, output_tokens=0),
        )

    def _aggregate_metrics(self, runs: list[TaskRun]) -> dict:
        total_time = sum(r.metrics.total_time for r in runs)
        total_output = sum(r.metrics.output_tokens for r in runs)
        throughput = total_output / total_time if total_time > 0 else 0.0
        ttft_values = [r.metrics.time_to_first_token for r in runs if r.metrics.time_to_first_token > 0]
        avg_ttft = sum(ttft_values) / len(ttft_values) if ttft_values else 0.0
        return {
            "total_time_s": round(total_time, 2),
            "total_output_tokens": total_output,
            "throughput_tokens_per_sec": round(throughput, 2),
            "avg_time_to_first_token_ms": round(avg_ttft * 1000, 1),
        }

    def _serialize_task_runs(self, runs: list[TaskRun]) -> list[dict]:
        base = normalize_task_results([run.task_result for run in runs])
        for entry, run in zip(base, runs):
            entry["timing"] = run.metrics.to_dict()
        return base
