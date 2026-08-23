"""Tests for the terminal task kind and resilient manifest loading."""
import json

import pytest

from task import Task, Manifest


def test_terminal_task_from_dict():
    data = {
        "id": "t1", "category": "bugfix", "kind": "terminal", "prompt": "fix it",
        "tests_cmd": "python /opt/tests/check.py",
        "environment_files": {"app.py": "x = 1"},
        "test_files": {"check.py": "assert True"},
        "tags": ["all", "terminal"], "max_steps": 12,
    }
    t = Task.from_dict(data)
    assert t.kind == "terminal"
    assert t.tests_cmd == "python /opt/tests/check.py"
    assert t.environment_files == {"app.py": "x = 1"}
    assert t.test_files == {"check.py": "assert True"}
    assert t.max_steps == 12
    assert t.tags == ("all", "terminal")


def test_terminal_task_defaults_kind_for_codegen():
    data = {"id": "t", "category": "codegen", "prompt": "p", "reference": "r", "tests": {}}
    assert Task.from_dict(data).kind == "codegen"


def test_terminal_requires_tests_cmd():
    with pytest.raises(ValueError, match="missing required fields"):
        Task.from_dict({"id": "t", "category": "bugfix", "kind": "terminal", "prompt": "p"})


def test_unknown_kind_rejected():
    with pytest.raises(ValueError, match="unknown task kind 'weird'"):
        Task.from_dict({"id": "t", "category": "bugfix", "kind": "weird", "prompt": "p"})


def test_manifest_loads_terminal_tasks():
    manifest = Manifest.load()
    terminal = [t for t in manifest if t.kind == "terminal"]
    assert len(terminal) == 4
    ids = {t.id for t in terminal}
    assert "terminal_config_fix" in ids


def test_manifest_skips_and_names_malformed_files(tmp_path):
    good = {
        "id": "good", "category": "bugfix", "kind": "terminal", "prompt": "p",
        "tests_cmd": "true", "tags": ["all"],
    }
    (tmp_path / "good.json").write_text(json.dumps(good))
    (tmp_path / "bad.json").write_text("{not valid json")
    (tmp_path / "missing_field.json").write_text(json.dumps({"id": "x"}))
    manifest = Manifest.load(tmp_path)
    assert [t.id for t in manifest] == ["good"]
