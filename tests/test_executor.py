import json
import pytest
from executor.executor import (
    SENTINEL,
    CodeContext,
    Executor,
    _extract_results,
    _parse_python_results,
    _make_authorizer,
)
from sandbox import ExecutionResult, ExecutionOutcome
from scoring import TestStatus
from config import Config


def test_extract_results_sentinel():
    stdout = f"some debug logs from model\nhello world\n{SENTINEL}{{\"test_1\": {{\"status\": \"pass\"}}}}\ntrailing line\n"
    res = _extract_results(stdout)
    assert res == {"test_1": {"status": "pass"}}


def test_extract_results_missing_sentinel():
    stdout = "just some debug logs without sentinel"
    with pytest.raises(ValueError, match="no sentinel line"):
        _extract_results(stdout)


def test_parse_python_results_success():
    tests = {"t1": "assert True", "t2": "assert False"}
    stdout = f"{SENTINEL}{{\"t1\": {{\"status\": \"pass\"}}, \"t2\": {{\"status\": \"fail\", \"detail\": \"assertion failed\"}}}}"
    exec_res = ExecutionResult(outcome=ExecutionOutcome.OK, stdout=stdout)
    parsed = _parse_python_results(tests, exec_res)
    assert len(parsed) == 2
    assert parsed[0].name == "t1"
    assert parsed[0].status is TestStatus.PASS
    assert parsed[1].name == "t2"
    assert parsed[1].status is TestStatus.FAIL
    assert parsed[1].detail == "assertion failed"


def test_parse_python_results_timeout():
    tests = {"t1": "assert True"}
    exec_res = ExecutionResult(outcome=ExecutionOutcome.TIMEOUT, elapsed_seconds=30.0)
    parsed = _parse_python_results(tests, exec_res)
    assert len(parsed) == 1
    assert parsed[0].status is TestStatus.ERROR
    assert "timed out" in parsed[0].detail


def test_sql_execution_success():
    cfg = Config()
    executor = Executor(cfg)
    ctx = CodeContext(
        source="SELECT id, name FROM users WHERE id = 1;",
        tests={"main": "assert ..."},
        sql_schema="CREATE TABLE users (id INT, name TEXT);",
        sql_setup="INSERT INTO users VALUES (1, 'Alice'), (2, 'Bob');",
        expected=[[1, "Alice"]],
    )
    res = executor.execute(ctx)
    assert res.passed is True
    assert len(res.test_results) == 1
    assert res.test_results[0].status is TestStatus.PASS


def test_sql_execution_authorizer_blocks_attach():
    cfg = Config()
    executor = Executor(cfg)
    ctx = CodeContext(
        source="ATTACH DATABASE ':memory:' AS attached_db;",
        tests={"main": "assert ..."},
        sql_schema="CREATE TABLE users (id INT);",
        expected=[],
    )
    res = executor.execute(ctx)
    assert res.passed is False
    assert "Forbidden SQL operation blocked" in res.error or "not authorized" in res.error.lower()
