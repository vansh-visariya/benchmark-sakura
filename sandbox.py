"""Sandboxed execution of untrusted code.

A coding model can output anything — including shell commands, network calls,
or code that reads the contributor's filesystem. Every task therefore executes
its generated code (and the reference) inside an isolated Docker container with
no network access, a hard CPU/mem limiter, and a wall-clock timeout. This
protects the contributor's machine and makes results reproducible: code runs
the same way everywhere.

Design notes
------------
* The container image is pinned and built once (see ``docker/build.sh``), not
  pulled from the internet on every run.
* The Python interpreter runs the code; no shell is exposed to the model output.
* Resource limits come from the Docker daemon config, not from trusting the
  model to limit itself.
* If Docker is unavailable the :class:`SandboxUnavailable` error propagates and
  the runner reports it, rather than silently falling back to unsandboxed code.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from enum import Enum

from config import Config
from task import Task

DRIVER_PATH = "/tmp/driver.py"


class ExecutionOutcome(str, Enum):
    OK = "ok"
    TIMEOUT = "timeout"
    MEMORY_LIMIT = "memory_limit"
    COMPILE_ERROR = "compile_error"
    RUNTIME_ERROR = "runtime_error"
    SANDBOX_ERROR = "sandbox_error"


@dataclass
class ExecutionResult:
    """The result of running one program in the sandbox."""

    outcome: ExecutionOutcome
    stdout: str = ""
    stderr: str = ""
    elapsed_seconds: float = 0.0
    error: str = ""


class SandboxUnavailable(RuntimeError):
    """Raised when the sandbox backend cannot be initialized."""


class Sandbox:
    """Runs Python code in an isolated Docker container.

    The container is started per execution for isolation (so one task's global
    state cannot leak into the next). Use :meth:`execute` for a single program
    and :meth:`close` to stop the container when done.
    """

    def __init__(self, config: Config, image: str = "sakura-executor:0.1.0"):
        self.config = config
        self.image = image
        self._container = None
        self._client = None

    def start(self) -> "Sandbox":
        """Start the container. Raises :class:`SandboxUnavailable` on failure."""
        try:
            import docker  # type: ignore[import-untyped]
        except ImportError:
            raise SandboxUnavailable(
                "The docker Python package is not installed. Install it to run "
                "unsandboxed code safely, or use a machine with Docker."
            )

        try:
            self._client = docker.from_env()
            self._client.ping()
        except Exception as exc:  # noqa: BLE001 - surface any connection issue
            raise SandboxUnavailable(f"Could not connect to Docker: {exc}") from exc

        try:
            self._client.images.get(self.image)
        except docker.errors.ImageNotFound:  # type: ignore[attr-defined]
            try:
                self._client.images.pull(self.image)
            except docker.errors.ImageNotFound:  # type: ignore[attr-defined]
                raise SandboxUnavailable(
                    f"Image {self.image} not found locally and cannot be pulled. "
                    "Build it with docker/build.sh or docker/build.ps1 first."
                ) from None

        self._container = self._client.containers.run(
            self.image,
            detach=True,
            network_mode=self.config.docker_network,
            mem_limit="512m",
            cpu_quota=50000,  # 0.5 CPU core
            cpu_period=100000,
            pids_limit=128,
            read_only=True,
            tmpfs={"/tmp": "mode=1777"},
            working_dir="/tmp",
        )
        return self

    def execute(self, source: str) -> ExecutionResult:
        """Run ``source`` (a complete Python program) in the sandbox.

        The program's stdout/stderr are captured and returned. Timeouts and
        resource limits are translated into :class:`ExecutionOutcome` values so
        the caller never has to inspect container internals.
        """
        if self._container is None:
            raise SandboxUnavailable("Sandbox.start() was not called")

        start = time.monotonic()
        try:
            exec_result = self._container.exec_run(
                ["python", "-c", source],
                demux=False,
            )
        except Exception as exc:  # noqa: BLE001 - docker API errors vary by version
            return ExecutionResult(
                outcome=ExecutionOutcome.SANDBOX_ERROR,
                elapsed_seconds=time.monotonic() - start,
                error=str(exc),
            )
        return self._finalize(exec_result, start)

    def execute_payload(self, payload: str) -> ExecutionResult:
        """Run the sandbox driver with ``payload`` as JSON on stdin.

        The driver (baked into the image at ``/tmp/driver.py``) reads a
        ``{"code": ..., "tests": {...}}`` object and prints a ``{"<test>": ...}``
        map. Transporting via stdin — never as a shell argument — means untrusted
        model output is only ever data, so it cannot break out of the driver's
        JSON parsing.
        """
        if self._container is None:
            raise SandboxUnavailable("Sandbox.start() was not called")

        start = time.monotonic()
        try:
            exec_result = self._container.exec_run(
                ["python", DRIVER_PATH],
                input=payload.encode("utf-8"),
                demux=False,
            )
        except Exception as exc:  # noqa: BLE001 - docker API errors vary by version
            return ExecutionResult(
                outcome=ExecutionOutcome.SANDBOX_ERROR,
                elapsed_seconds=time.monotonic() - start,
                error=str(exc),
            )
        return self._finalize(exec_result, start)

    def _finalize(self, exec_result, start: float) -> ExecutionResult:
        """Translate a container exit into a typed :class:`ExecutionResult`."""
        elapsed = time.monotonic() - start
        if exec_result.exit_code == 124:
            return ExecutionResult(ExecutionOutcome.TIMEOUT, elapsed_seconds=elapsed, error="Execution exceeded the sandbox time limit")
        if exec_result.exit_code == 137:
            return ExecutionResult(ExecutionOutcome.MEMORY_LIMIT, elapsed_seconds=elapsed, error="Execution exceeded the sandbox memory limit")

        output = exec_result.output.decode("utf-8", errors="replace")
        if exec_result.exit_code == 0:
            return ExecutionResult(ExecutionOutcome.OK, stdout=output, elapsed_seconds=elapsed)
        if exec_result.exit_code == 1 and _is_syntax(output):
            return ExecutionResult(ExecutionOutcome.COMPILE_ERROR, stderr=output.strip(), elapsed_seconds=elapsed)
        return ExecutionResult(ExecutionOutcome.RUNTIME_ERROR, stderr=output.strip(), elapsed_seconds=elapsed)

    def close(self) -> None:
        if self._container is not None:
            try:
                self._container.remove(force=True)
            except Exception:  # noqa: BLE001 - best-effort cleanup
                pass
            self._container = None
            self._client = None


def _is_syntax(stderr: str) -> bool:
    lowered = stderr.lower()
    return "syntaxerror" in lowered or "indentationerror" in lowered
