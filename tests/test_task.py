from pathlib import Path
import pytest
from task import Task, Manifest


def test_task_from_dict():
    data = {
        "id": "t1",
        "category": "codegen",
        "prompt": "write foo",
        "reference": "def foo(): pass",
        "tests": {"test_1": "assert foo() is None"},
        "tags": ["all", "easy"],
    }
    task = Task.from_dict(data)
    assert task.id == "t1"
    assert task.category == "codegen"
    assert task.test_count == 1
    assert task.tags == ("all", "easy")


def test_task_from_dict_missing_field():
    with pytest.raises(ValueError, match="missing required fields"):
        Task.from_dict({"id": "t1"})


def test_manifest_select():
    t1 = Task(id="t1", category="codegen", prompt="p", reference="r", tests={}, tags=("all", "easy"))
    t2 = Task(id="t2", category="sql", prompt="p", reference="r", tests={}, tags=("all", "hard"))
    t3 = Task(id="t3", category="sql", prompt="p", reference="r", tests={}, tags=("sql",))

    manifest = Manifest([t1, t2, t3])
    assert len(manifest) == 3
    assert manifest.ids() == ["t1", "t2", "t3"]
    assert len(manifest.by_category("sql")) == 2

    # Select with tag matching (intersection)
    assert manifest.select(("all", "easy")) == [t1]
    assert manifest.select(("all",)) == [t1, t2]
    assert manifest.select(("sql",)) == [t3]
    assert manifest.select(None) == [t1, t2, t3]


def test_manifest_load_default():
    manifest = Manifest.load()
    assert len(manifest) >= 23
    assert "codegen_fibonacci" in manifest.ids()
