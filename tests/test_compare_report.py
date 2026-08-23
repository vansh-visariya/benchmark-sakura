from compare import compare_runs, _format_diff
from report import generate_markdown_report


def sample_run(model="model-a", pass_rate=0.8, throughput=25.0):
    return {
        "model": model,
        "version": "0.1.0",
        "hardware": {
            "platform": "win32",
            "cpu_cores": 16,
            "ram_total_gb": 32.0,
            "gpus": [{"name": "RTX 4090", "memory_total_gb": 24.0}],
        },
        "metrics": {
            "pass_rate": pass_rate,
            "solved_count": int(pass_rate * 10),
            "task_count": 10,
            "throughput_tokens_per_sec": throughput,
            "avg_time_to_first_token_ms": 120.5,
            "total_time_s": 4.5,
            "errors": 0,
            "category_pass_rate": {"codegen": 1.0, "sql": 0.5},
        },
        "task_results": [
            {
                "task_id": "codegen_fibonacci",
                "category": "codegen",
                "passed": True,
                "passed_tests": ["test_1"],
                "failed_tests": [],
            },
            {
                "task_id": "sql_join_customers",
                "category": "sql",
                "passed": False,
                "passed_tests": [],
                "failed_tests": ["test_1"],
                "test_details": [{"name": "test_1", "status": "fail", "detail": "mismatch"}],
            },
        ],
    }


def test_format_diff():
    assert _format_diff(10.0, 15.0) == "+5.00"
    assert _format_diff(15.0, 10.0) == "-5.00"
    assert _format_diff(10.0, 10.0) == "="


def test_compare_runs():
    r1 = sample_run("model-a", 0.6, 20.0)
    r2 = sample_run("model-b", 0.9, 35.0)
    out = compare_runs(r1, r2)
    assert "SAKURA RUN COMPARISON: model-a vs model-b" in out
    assert "Pass Rate" in out
    assert "Throughput" in out
    assert "codegen_fibonacci" in out


def test_generate_markdown_report():
    run = sample_run("qwen2.5-coder:7b", 0.75, 42.0)
    md = generate_markdown_report(run)
    assert "# Sakura Benchmark Report: `qwen2.5-coder:7b`" in md
    assert "Overall Metrics" in md
    assert "Category Breakdown" in md
    assert "Task-by-Task Results" in md
    assert "Failure & Error Details" in md
    assert "sql_join_customers" in md
