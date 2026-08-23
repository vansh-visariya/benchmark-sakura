from scoring import (
    TestStatus,
    TestResult,
    TaskResult,
    RunMetrics,
    score_task,
    summarize,
    normalize_task_results,
)
from task import Task


def make_dummy_task(task_id: str = "t1", category: str = "codegen") -> Task:
    return Task(
        id=task_id,
        category=category,
        prompt="prompt",
        reference="reference",
        tests={"test_1": "assert True"},
    )


def test_task_result_passing():
    task = make_dummy_task()
    results = [TestResult(name="test_1", status=TestStatus.PASS)]
    tr = score_task(task, results)
    assert tr.passed is True
    assert tr.passed_tests == ["test_1"]
    assert tr.failed_tests == []


def test_task_result_failing_with_details():
    task = make_dummy_task()
    results = [
        TestResult(name="test_1", status=TestStatus.PASS),
        TestResult(name="test_2", status=TestStatus.FAIL, detail="expected 2 got 1"),
        TestResult(name="test_3", status=TestStatus.ERROR, detail="ZeroDivisionError"),
    ]
    tr = score_task(task, results)
    assert tr.passed is False
    assert tr.passed_tests == ["test_1"]
    assert tr.failed_tests == ["test_2", "test_3"]

    normalized = normalize_task_results([tr])
    assert len(normalized) == 1
    entry = normalized[0]
    assert entry["passed"] is False
    assert len(entry["test_details"]) == 2
    assert entry["test_details"][0] == {
        "name": "test_2",
        "status": "fail",
        "detail": "expected 2 got 1",
    }
    assert entry["test_details"][1] == {
        "name": "test_3",
        "status": "error",
        "detail": "ZeroDivisionError",
    }


def test_summarize():
    task1 = make_dummy_task("t1", "codegen")
    task2 = make_dummy_task("t2", "sql")
    task3 = make_dummy_task("t3", "codegen")

    r1 = score_task(task1, [TestResult(name="t", status=TestStatus.PASS)])
    r2 = score_task(task2, [TestResult(name="t", status=TestStatus.FAIL)])
    r3 = score_task(task3, [TestResult(name="t", status=TestStatus.ERROR, detail="err")])

    summary = summarize([r1, r2, r3])
    assert summary["task_count"] == 3
    assert summary["solved_count"] == 1
    assert summary["pass_rate"] == round(1 / 3, 4)
    assert summary["errors"] == 1
    assert summary["category_pass_rate"]["codegen"] == 0.5
    assert summary["category_pass_rate"]["sql"] == 0.0


def test_run_metrics():
    metrics = RunMetrics(
        time_to_first_token=0.15,
        total_time=2.0,
        output_tokens=100,
        prompt_tokens=50,
    )
    d = metrics.to_dict()
    assert d["time_to_first_token_ms"] == 150.0
    assert d["total_time_ms"] == 2000.0
    assert d["output_tokens"] == 100
    assert d["throughput_tokens_per_sec"] == 50.0
