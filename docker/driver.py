"""Sandbox driver: executes model code and runs tests in isolation.

Reads a JSON payload from ``SAKURA_PAYLOAD`` (or stdin)::

    {"code": "...", "tests": {"test_name": "assert ..."}}

Executes the code once into a namespace, runs each test against a fresh copy
of that namespace, and prints results as one sentinel-delimited JSON line::

    SAKURA_RESULTS: {"<test>": {"status": "pass"|"fail"|"error", ...}}

The sentinel lets the harness separate its own protocol line from anything
the model's code prints, so verbose-but-correct solutions still score
correctly. The same line is echoed to stderr for human debugging.
"""
from __future__ import annotations

import json
import os
import sys
import traceback

SENTINEL = "SAKURA_RESULTS:"


def main() -> None:
    payload_text = os.environ.get("SAKURA_PAYLOAD")
    if payload_text is not None:
        try:
            payload = json.loads(payload_text)
        except ValueError:
            print(f"driver: malformed payload ({len(payload_text)} bytes)", file=sys.stderr)
            sys.exit(1)
    else:
        payload = json.load(sys.stdin)
    code = payload.get("code", "")
    tests = payload.get("tests") or {}
    results: dict[str, dict] = {}

    def emit(outcomes: dict[str, dict]) -> None:
        line = f"{SENTINEL} {json.dumps(outcomes)}"
        print(line, flush=True)
        print(line, file=sys.stderr, flush=True)

    namespace: dict = {}
    try:
        exec(compile(code, "<model>", "exec"), namespace)
    except SyntaxError as exc:
        detail = f"{exc.msg} (line {exc.lineno})"
        emit({name: {"status": "error", "detail": detail} for name in tests})
        return
    except SystemExit:
        detail = "model code called sys.exit() at module level"
        emit({name: {"status": "error", "detail": detail} for name in tests})
        return
    except BaseException as exc:  # noqa: BLE001 - untrusted code raises anything
        detail = f"{type(exc).__name__}: {exc}"
        emit({name: {"status": "error", "detail": detail} for name in tests})
        return

    if not tests:
        emit({})
        return

    for name, test_source in tests.items():
        local_ns = dict(namespace)
        try:
            exec(compile(test_source, f"<test:{name}>", "exec"), local_ns)
            results[name] = {"status": "pass"}
        except AssertionError as exc:
            results[name] = {"status": "fail", "detail": str(exc) or "assertion failed"}
        except BaseException as test_exc:  # noqa: BLE001 - untrusted code
            if isinstance(test_exc, SystemExit):
                results[name] = {"status": "error", "detail": "test called sys.exit()"}
            else:
                results[name] = {
                    "status": "error",
                    "detail": f"{type(test_exc).__name__}: {test_exc}",
                }

    emit(results)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
