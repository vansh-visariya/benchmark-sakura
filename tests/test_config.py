from pathlib import Path
import os
from config import Config, load_config, DEFAULT_SANDBOX_TIMEOUT_SECONDS, SANDBOX_IMAGE


def test_default_config():
    cfg = Config()
    assert cfg.sandbox_image == SANDBOX_IMAGE
    assert cfg.sandbox_timeout_seconds == DEFAULT_SANDBOX_TIMEOUT_SECONDS
    assert cfg.docker_network == "none"
    assert "all" in cfg.default_task_tags


def test_load_config_env_overrides(monkeypatch):
    monkeypatch.setenv("SAKURA_SANDBOX_IMAGE", "custom-image:1.0")
    monkeypatch.setenv("SAKURA_SANDBOX_TIMEOUT", "45")
    monkeypatch.setenv("SAKURA_SANDBOX_MEM_MB", "1024")
    monkeypatch.setenv("SAKURA_SANDBOX_CPUS", "2.0")
    monkeypatch.setenv("SAKURA_SANDBOX_PIDS", "256")
    monkeypatch.setenv("SAKURA_TASK_TAGS", "codegen,hard")
    monkeypatch.setenv("SAKURA_DATABASE_URL", "https://custom.api")

    cfg = load_config()
    assert cfg.sandbox_image == "custom-image:1.0"
    assert cfg.sandbox_timeout_seconds == 45.0
    assert cfg.sandbox_mem_limit_mb == 1024
    assert cfg.sandbox_cpus == 2.0
    assert cfg.sandbox_pids_limit == 256
    assert cfg.default_task_tags == ("codegen", "hard")
    assert cfg.database_url == "https://custom.api"
