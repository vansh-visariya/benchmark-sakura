"""Coding task definitions and the manifest loader.

A *task* is a single coding problem: a prompt the model sees, plus the hidden
information (reference solution and tests) used to score it. Tasks are declared
in JSON files under ``benchmark/tasks/`` and loaded through :class:`Manifest`.

The manifest is the version-controlled catalog of every task in the benchmark.
Keeping it separate from the raw files means contributors add tasks by dropping
a JSON file into ``benchmark/tasks/`` and editing the manifest, and the runner
never has to glob the filesystem itself.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from config import TASKS_DIR

MANIFEST_FILENAME = "manifest.json"


@dataclass(frozen=True)
class Task:
    """One coding problem.

    Attributes:
        reference: The canonical solution. Not shown to the model; used only to
            build the reference output the sandbox compares against. Kept as raw
            source so the sandbox can execute it the same way it executes model
            output.
        prompt: What the model is asked to produce.
        tests: A dict of ``{test_name: test_source}``. Each is executed in the
            sandbox; all must pass for the task to count as solved.
        tags: Searchable labels (e.g. ``"codegen"``, ``"sql"``, ``"7b"``) used
            to filter which tasks the runner executes.
    """

    id: str
    category: str
    prompt: str
    reference: str
    tests: dict[str, str]
    tags: tuple[str, ...] = field(default_factory=tuple)
    sql: str | None = None
    sql_schema: str | None = None
    sql_setup: str | None = None
    expected: list[list[Any]] | None = None

    @property
    def test_count(self) -> int:
        return len(self.tests)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Task":
        missing = [key for key in ("id", "category", "prompt", "reference", "tests") if key not in data]
        if missing:
            raise ValueError(f"task is missing required fields: {', '.join(missing)}")
        tags = tuple(data.get("tags", ()))
        expected = None
        if data.get("expected") is not None:
            expected = [list(row) for row in data["expected"]]
        return cls(
            id=data["id"],
            category=data["category"],
            prompt=data["prompt"],
            reference=data["reference"],
            tests={str(k): str(v) for k, v in data["tests"].items()},
            tags=tags,
            sql=data.get("sql"),
            sql_schema=data.get("sql_schema"),
            sql_setup=data.get("sql_setup"),
            expected=expected,
        )


class Manifest:
    """The ordered catalog of tasks, each backed by a JSON file on disk."""

    def __init__(self, tasks: list[Task]):
        self._tasks = tasks
        self._by_id = {task.id: task for task in tasks}

    def __len__(self) -> int:
        return len(self._tasks)

    def __iter__(self):
        return iter(self._tasks)

    def __getitem__(self, task_id: str) -> Task:
        return self._by_id[task_id]

    def ids(self) -> list[str]:
        return [task.id for task in self._tasks]

    def by_category(self, category: str) -> list[Task]:
        return [task for task in self._tasks if task.category == category]

    def tags(self) -> set[str]:
        return {tag for task in self._tasks for tag in task.tags}

    def select(self, tags: tuple[str, ...] | None = None) -> list[Task]:
        """Return tasks matching ALL of the given tags.

        ``None`` (or an empty tuple) selects everything. Matching is
        intersection, not union: a task must carry every requested tag. This
        lets callers express "7b tasks that are also codegen" as
        ``select(("7b", "codegen"))``.
        """
        if not tags:
            return list(self._tasks)
        wanted = set(tags)
        return [task for task in self._tasks if wanted.issubset(set(task.tags))]

    @classmethod
    def load(cls, tasks_dir: Path | None = None) -> "Manifest":
        """Load every task JSON in ``tasks_dir`` (default: ``benchmark/tasks``).

        The manifest is sorted by id so iteration order is stable and reproducible
        across runs and machines.
        """
        directory = Path(tasks_dir or TASKS_DIR)
        manifest_path = directory / MANIFEST_FILENAME
        if manifest_path.exists():
            manifest = _load_json(manifest_path)
            filenames = manifest.get("tasks", [])
            tasks = [Task.from_dict(_load_json(directory / name)) for name in filenames]
        else:
            files = sorted(p for p in directory.glob("*.json") if p.name != MANIFEST_FILENAME)
            tasks = [Task.from_dict(_load_json(path)) for path in files]
        return cls(tasks)


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)
