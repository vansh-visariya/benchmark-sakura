"""Code execution for the benchmark.

This subpackage turns a model's generated code (or a reference solution) into
sandboxed executions and scores the outcome. The public surface is intentionally
small:

- :class:`CodeContext` -- bundles a program with its inputs so it can be run in
  isolation without touching the real machine.
- :class:`Executor` -- runs a :class:`CodeContext` in the sandbox and returns a
  :class:`ExecutorResult`.
- :func:`run_task` -- the entry point used by the runner: it builds a
  :class:`CodeContext` from a task + generated code, executes the tests, and
  returns a scored :class:`TaskResult`.
"""

from .executor import (
    CodeContext,
    ExecutorResult,
    Executor,
    run_task,
)

__all__ = ["CodeContext", "ExecutorResult", "Executor", "run_task"]
