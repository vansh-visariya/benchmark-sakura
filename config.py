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
PACKAGE_DIR = ROOT / "sakura"
BENCHMARK_DIR = ROOT / "benchmark"
TASKS_DIR = BENCHMARK_DIR / "tasks"
RESULTS_DIR = ROOT / ".results"
LOG_DIR = ROOT / ".logs"
DEFAULT_DATABASE_URL = "https://sakura.vaansh.dev"
DEFAULT_DATABASE_TIMEOUT = 30

DEFAULT_TASK_TAGS = ("all",)


@dataclass
class Config:
    """Runtime configuration. Instances are cheap to build and fully overridable."""

    ollama_base_url: str = "http://127.0.0.1:11434"
    database_url: str = DEFAULT_DATABASE_URL
    database_timeout: int = DEFAULT_DATABASE_TIMEOUT
    results_dir: Path = field(default_factory=lambda: RESULTS_DIR)
    log_dir: Path = field(default_factory=lambda: LOG_DIR)
    docker_network: str = "none"
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
        database_timeout=int(os.environ.get("SAKURA_DATABASE_TIMEOUT", str(DEFAULT_DATABASE_TIMEOUT))),
        docker_network=os.environ.get("SAKURA_DOCKER_NETWORK", "none"),
        default_task_tags=tuple(
            tag.strip()
            for tag in os.environ.get("SAKURA_TASK_TAGS", ",".join(DEFAULT_TASK_TAGS)).split(",")
            if tag.strip()
        ),
    )
