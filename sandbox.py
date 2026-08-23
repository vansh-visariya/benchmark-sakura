"""Sandboxed execution of untrusted code.

A coding model can output anything — including shell commands, network calls,
or code that reads the contributor's filesystem. Every task therefore executes
its generated code (and the reference) inside an isolated Docker container with
no network access, hard CPU/memory/PID limits, and a wall-clock timeout. This
protects the contributor's machine and makes results reproducible: code runs
the same way everywhere.

Design notes
------------
* The container image is built once locally (see ``docker/build.sh``); it is
  never pulled from a registry, so the executed code always matches the source
  tree. A missing image is an error, not a silent download.
* One long-lived container serves a whole benchmark run; ``/tmp`` is wiped
  between executions so one task's state cannot leak into the next.
* Each execution is wrapped in GNU ``timeout`` inside the container, so a
  runaway model answer surfaces as :attr:`ExecutionOutcome.TIMEOUT` instead of
  hanging the run.
* The payload travels through the Docker API environment parameter (never a
  shell argument) and the driver drops to an unprivileged user before running
  model code, so model output cannot read the tests back out of the driver's
  environment.
* Resource limits come from the Docker daemon config, not from trusting the
  model to limit itself.
* If Docker is unavailable the :class:`SandboxUnavailable` error propagates and
  the runner reports it, rather than silently falling back to unsandboxed code.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum

from config import Config

DRIVER_PATH = "/opt/sakura/driver.py"


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

    A single container is started once per benchmark run and reused across
    tasks (starting a fresh container per execution would dominate run time);
    writable state is confined to a ``/tmp`` tmpfs that is cleared before every
    execution. Use :meth:`execute_payload` for driver runs and :meth:`close`
    to remove the container when done.
    """

    def __init__(self, config: Config):
        self.config = config
        self.image = config.sandbox_image
        self._container = None
        self._client = None

    @property
    def running(self) -> bool:
        return self._container is not None

    def start(self) -> "Sandbox":
        """Start the container. Raises :class:`SandboxUnavailable` on failure."""
        try:
            import docker  # type: ignore[import-untyped]
        except ImportError:
            raise SandboxUnavailable(
                "The docker Python package is not installed. "
                "Install dependencies with `pip install -e .`."
            )

        try:
            self._client = docker.from_env()
            self._client.ping()
        except Exception as exc:  # noqa: BLE001 - surface any connection issue
            raise SandboxUnavailable(f"Could not connect to Docker: {exc}") from exc

        try:
            self._client.images.get(self.image)
        except docker.errors.ImageNotFound:  # type: ignore[attr-defined]
            raise SandboxUnavailable(
                f"Sandbox image {self.image} not found locally. Build it first "
                "with docker/build.sh or docker/build.ps1."
            ) from None

        self._container = self._client.containers.run(
            self.image,
            detach=True,
            network_mode=self.config.docker_network,
            mem_limit=f"{self.config.sandbox_mem_limit_mb}m",
            cpu_quota=int(self.config.sandbox_cpus * 100000),
            cpu_period=100000,
            pids_limit=self.config.sandbox_pids_limit,
            read_only=True,
            tmpfs={"/tmp": "mode=1777"},
            working_dir="/tmp",
            security_opt=["no-new-privileges"],
            cap_drop=["ALL"],
        )
        return self

    def execute_payload(self, payload: str) -> ExecutionResult:
        """Run the sandbox driver over a ``{"code": ..., "tests": {...}}`` payload.

        The driver (baked into the image at ``/opt/sakura/driver.py``) prints a
        sentinel-delimited JSON map of test outcomes. Transporting the payload
        via the Docker API environment parameter — never through a shell —
        means untrusted model output remains data for JSON parsing, and the
        driver's privilege drop keeps it away from the model process.
        """
        if self._container is None:
            raise SandboxUnavailable("Sandbox.start() was not called")

        self._clean_tmp()

        start = time.monotonic()
        timeout_seconds = max(1, int(self.config.sandbox_timeout_seconds))
        try:
            exec_result = self._container.exec_run(
                ["timeout", "-k", "5", f"{timeout_seconds}s", "python", DRIVER_PATH],
                environment={"SAKURA_PAYLOAD": payload},
                demux=True,
            )
        except Exception as exc:  # noqa: BLE001 - docker API errors vary by version
            return ExecutionResult(
                outcome=ExecutionOutcome.SANDBOX_ERROR,
                elapsed_seconds=time.monotonic() - start,
                error=str(exc),
            )
        return self._finalize(exec_result, start)

    def _clean_tmp(self) -> None:
        """Clear the writable tmpfs so tasks cannot observe each other."""
        try:
            self._container.exec_run(
                ["sh", "-c", "rm -rf /tmp/* /tmp/.[!.]* 2>/dev/null; true"],
                demux=True,
            )
        except Exception:  # noqa: BLE001 - cleanup is best-effort
            pass

    def _finalize(self, exec_result, start: float) -> ExecutionResult:
        """Translate a container exit into a typed :class:`ExecutionResult`."""
        elapsed = time.monotonic() - start
        stdout_b, stderr_b = exec_result.output or (b"", b"")
        stdout = (stdout_b or b"").decode("utf-8", errors="replace")
        stderr = (stderr_b or b"").decode("utf-8", errors="replace")

        if exec_result.exit_code == 124:
            return ExecutionResult(
                ExecutionOutcome.TIMEOUT,
                stdout=stdout,
                stderr=stderr,
                elapsed_seconds=elapsed,
                error="Execution exceeded the sandbox time limit",
            )
        if exec_result.exit_code == 137:
            return ExecutionResult(
                ExecutionOutcome.MEMORY_LIMIT,
                stdout=stdout,
                stderr=stderr,
                elapsed_seconds=elapsed,
                error="Execution exceeded the sandbox memory limit",
            )

        if exec_result.exit_code == 0:
            return ExecutionResult(ExecutionOutcome.OK, stdout=stdout, elapsed_seconds=elapsed)
        if exec_result.exit_code == 1 and _is_syntax(stderr):
            return ExecutionResult(
                ExecutionOutcome.COMPILE_ERROR, stderr=stderr.strip(), elapsed_seconds=elapsed
            )
        return ExecutionResult(
            ExecutionOutcome.RUNTIME_ERROR, stderr=stderr.strip(), elapsed_seconds=elapsed
        )

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
