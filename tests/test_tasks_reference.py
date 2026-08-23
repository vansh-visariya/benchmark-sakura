import sqlite3
import pytest
from task import Manifest, Task


def execute_python_task_locally(task: Task):
    """Executes a Python task reference code and its tests in a local test namespace."""
    ns = {}
    exec(compile(task.reference, f"<reference:{task.id}>", "exec"), ns)
    for test_name, test_code in task.tests.items():
        test_ns = dict(ns)
        exec(compile(test_code, f"<test:{test_name}>", "exec"), test_ns)


def execute_sql_task_locally(task: Task):
    """Executes a SQL task reference query and compares to expected."""
    conn = sqlite3.connect(":memory:")
    try:
        if task.sql_schema:
            conn.executescript(task.sql_schema)
        if task.sql_setup:
            conn.executescript(task.sql_setup)
        rows = [list(r) for r in conn.execute(task.reference).fetchall()]
        assert rows == task.expected, f"Task {task.id} reference produced {rows}, expected {task.expected}"
    finally:
        conn.close()


@pytest.fixture
def manifest():
    return Manifest.load()


def test_all_tasks_reference_solutions_pass(manifest):
    assert len(manifest) >= 23
    for task in manifest:
        if task.sql_schema:
            execute_sql_task_locally(task)
        else:
            execute_python_task_locally(task)
