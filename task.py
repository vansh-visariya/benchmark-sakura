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
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from config import TASKS_DIR

MANIFEST_FILENAME = "manifest.json"

_KINDS = ("codegen", "sql", "terminal")
_BASE_REQUIRED_FIELDS = ("id", "category", "prompt", "reference", "tests")
_REQUIRED_FIELDS = {
    "terminal": ("id", "category", "prompt", "tests_cmd"),
}


def _string_map(value: Any) -> dict[str, str] | None:
    """Coerce a JSON object of strings into ``{str: str}``, else None."""
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("expected an object mapping names to string content")
    return {str(k): str(v) for k, v in value.items()}


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
    kind: str = "codegen"
    environment_files: dict[str, str] | None = None
    setup_cmd: str | None = None
    tests_cmd: str | None = None
    test_files: dict[str, str] | None = None
    max_steps: int | None = None

    @property
    def test_count(self) -> int:
        return len(self.tests)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Task":
        kind = data.get("kind", "codegen")
        if kind not in _KINDS:
            raise ValueError(f"unknown task kind {kind!r} (expected one of {sorted(_KINDS)})")
        missing = [
            key for key in _REQUIRED_FIELDS.get(kind, _BASE_REQUIRED_FIELDS)
            if key not in data
        ]
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
            reference=data.get("reference", ""),
            tests={str(k): str(v) for k, v in (data.get("tests") or {}).items()},
            tags=tags,
            sql=data.get("sql"),
            sql_schema=data.get("sql_schema"),
            sql_setup=data.get("sql_setup"),
            expected=expected,
            kind=kind,
            environment_files=_string_map(data.get("environment_files")),
            setup_cmd=data.get("setup_cmd"),
            tests_cmd=data.get("tests_cmd"),
            test_files=_string_map(data.get("test_files")),
            max_steps=data.get("max_steps"),
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
        entries: list[tuple[str, Path]] = []
        if manifest_path.exists():
            manifest = _load_json(manifest_path)
            entries = [(name, directory / name) for name in manifest.get("tasks", [])]
        else:
            entries = [
                (path.name, path)
                for path in sorted(p for p in directory.glob("*.json") if p.name != MANIFEST_FILENAME)
            ]
        tasks: list[Task] = []
        for name, path in entries:
            try:
                tasks.append(Task.from_dict(_load_json(path)))
            except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
                print(
                    f"warning: skipping malformed task file {name}: {exc}",
                    file=sys.stderr,
                    flush=True,
                )
        return cls(tasks)


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)
