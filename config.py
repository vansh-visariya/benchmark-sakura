"""Central configuration and shared paths.

Everything the rest of the package depends on (paths, defaults, logging) is
defined here so the rest of the code never reaches for ``os.environ`` directly
or invents its own locations for files.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BENCHMARK_DIR = ROOT / "benchmark"
TASKS_DIR = BENCHMARK_DIR / "tasks"
RESULTS_DIR = ROOT / ".results"
LOG_DIR = ROOT / ".logs"
DEFAULT_DATABASE_URL = "https://sakura.vaansh.dev"
DEFAULT_DATABASE_TIMEOUT = 30

SANDBOX_IMAGE = "sakura-executor:0.3.0"
DEFAULT_SANDBOX_TIMEOUT_SECONDS = 30
DEFAULT_SANDBOX_MEM_LIMIT_MB = 512
DEFAULT_SANDBOX_CPUS = 0.5
DEFAULT_SANDBOX_PIDS_LIMIT = 128

DEFAULT_AGENT_MAX_STEPS = 20
DEFAULT_AGENT_STEP_TIMEOUT_SECONDS = 30
DEFAULT_WORKSPACE_TMPFS_MB = 256

DEFAULT_TASK_TAGS = ("all",)


def _env_int(name: str, default: int, minimum: int | None = None) -> int:
    """Read an integer env var, falling back to the default on bad values."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        print(f"warning: {name}={raw!r} is not an integer; using default {default}", flush=True)
        return default
    if minimum is not None and value < minimum:
        print(f"warning: {name}={value} is below the minimum {minimum}; using {minimum}", flush=True)
        return minimum
    return value


def _env_float(name: str, default: float, minimum: float | None = None) -> float:
    """Read a float env var, falling back to the default on bad values."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError:
        print(f"warning: {name}={raw!r} is not a number; using default {default}", flush=True)
        return default
    if minimum is not None and value < minimum:
        print(f"warning: {name}={value} is below the minimum {minimum}; using {minimum}", flush=True)
        return minimum
    return value


@dataclass
class Config:
    """Runtime configuration. Instances are cheap to build and fully overridable."""

    ollama_base_url: str = "http://127.0.0.1:11434"
    database_url: str = DEFAULT_DATABASE_URL
    database_timeout: int = DEFAULT_DATABASE_TIMEOUT
    results_dir: Path = field(default_factory=lambda: RESULTS_DIR)
    log_dir: Path = field(default_factory=lambda: LOG_DIR)
    docker_network: str = "none"
    sandbox_image: str = SANDBOX_IMAGE
    sandbox_timeout_seconds: float = DEFAULT_SANDBOX_TIMEOUT_SECONDS
    sandbox_mem_limit_mb: int = DEFAULT_SANDBOX_MEM_LIMIT_MB
    sandbox_cpus: float = DEFAULT_SANDBOX_CPUS
    sandbox_pids_limit: int = DEFAULT_SANDBOX_PIDS_LIMIT
    agent_max_steps: int = DEFAULT_AGENT_MAX_STEPS
    agent_step_timeout_seconds: float = DEFAULT_AGENT_STEP_TIMEOUT_SECONDS
    workspace_tmpfs_mb: int = DEFAULT_WORKSPACE_TMPFS_MB
    default_task_tags: tuple[str, ...] = field(default_factory=lambda: DEFAULT_TASK_TAGS)

    # --- paths (kept here so tests can point everything at a temp dir) ---
    def ensure_dirs(self) -> None:
        for directory in (self.results_dir, self.log_dir):
            directory.mkdir(parents=True, exist_ok=True)

    def log_path(self, name: str = "sakura.log") -> Path:
        return self.log_dir / name


def load_config() -> Config:
    """Build a :class:`Config`, overriding only the values found in env vars.

    This is the single place environment variables are read, so the rest of the
    codebase has one predictable source of truth for configuration.
    """
    return Config(
        ollama_base_url=os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
        database_url=os.environ.get("SAKURA_DATABASE_URL", DEFAULT_DATABASE_URL),
        database_timeout=_env_int("SAKURA_DATABASE_TIMEOUT", DEFAULT_DATABASE_TIMEOUT, minimum=1),
        docker_network=os.environ.get("SAKURA_DOCKER_NETWORK", "none"),
        sandbox_image=os.environ.get(
            "SAKURA_SANDBOX_IMAGE", SANDBOX_IMAGE
        ),
        sandbox_timeout_seconds=_env_float(
            "SAKURA_SANDBOX_TIMEOUT", DEFAULT_SANDBOX_TIMEOUT_SECONDS, minimum=1.0
        ),
        sandbox_mem_limit_mb=_env_int("SAKURA_SANDBOX_MEM_MB", DEFAULT_SANDBOX_MEM_LIMIT_MB, minimum=64),
        sandbox_cpus=_env_float("SAKURA_SANDBOX_CPUS", DEFAULT_SANDBOX_CPUS, minimum=0.1),
        sandbox_pids_limit=_env_int("SAKURA_SANDBOX_PIDS", DEFAULT_SANDBOX_PIDS_LIMIT, minimum=16),
        agent_max_steps=_env_int("SAKURA_AGENT_MAX_STEPS", DEFAULT_AGENT_MAX_STEPS, minimum=1),
        agent_step_timeout_seconds=_env_float(
            "SAKURA_AGENT_STEP_TIMEOUT", DEFAULT_AGENT_STEP_TIMEOUT_SECONDS, minimum=1.0
        ),
        workspace_tmpfs_mb=_env_int("SAKURA_WORKSPACE_MB", DEFAULT_WORKSPACE_TMPFS_MB, minimum=32),
        default_task_tags=tuple(
            tag.strip()
            for tag in os.environ.get("SAKURA_TASK_TAGS", ",".join(DEFAULT_TASK_TAGS)).split(",")
            if tag.strip()
        ),
    )
