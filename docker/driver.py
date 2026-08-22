"""Sandbox driver: executes model code and runs tests in isolation.

Reads JSON from stdin::

    {"code": "...", "tests": {"test_name": "assert ..."}}

Prints a JSON map of test outcomes to stdout.
"""
from __future__ import annotations

import json
import sys
import traceback


def main() -> None:
    payload = json.load(sys.stdin)
    code = payload.get("code", "")
    tests = payload.get("tests") or {}
    namespace: dict = {}

    results: dict[str, dict] = {}
    try:
        exec(compile(code, "<model>", "exec"), namespace)
    except SyntaxError as exc:
        detail = f"{exc.msg} (line {exc.lineno})"
        for name in tests:
            results[name] = {"status": "error", "detail": detail}
        print(json.dumps(results))
        return
    except Exception as exc:
        detail = f"{type(exc).__name__}: {exc}"
        for name in tests:
            results[name] = {"status": "error", "detail": detail}
        print(json.dumps(results))
        return

    if not tests:
        print(json.dumps({}))
        return

    for name, test_source in tests.items():
        local_ns = dict(namespace)
        try:
            exec(compile(test_source, f"<test:{name}>", "exec"), local_ns)
            results[name] = {"status": "pass"}
        except AssertionError as exc:
            results[name] = {"status": "fail", "detail": str(exc) or "assertion failed"}
        except Exception as exc:
            results[name] = {"status": "error", "detail": f"{type(exc).__name__}: {exc}"}

    print(json.dumps(results))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
