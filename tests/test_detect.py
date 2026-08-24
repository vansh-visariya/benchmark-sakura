import sys

import pytest

from detect import (
    GPUInfo,
    HardwareReport,
    build_report,
    detect,
    _read_apple_gpu,
    _read_cpu_model,
    _read_os_release,
    _safe_run,
)


def test_gpu_info_properties():
    gpu = GPUInfo(name="Test GPU", memory_total_mb=8192, is_cpu=False)
    assert gpu.memory_total_gb == 8.0
    assert not gpu.is_cpu

    cpu = GPUInfo(name="CPU", memory_total_mb=None, is_cpu=True)
    assert cpu.memory_total_gb is None
    assert cpu.is_cpu


def test_hardware_report_structure():
    report = detect()
    assert isinstance(report, HardwareReport)
    assert isinstance(report.cpu_model, str)
    assert len(report.cpu_model) > 0
    assert isinstance(report.os_release, str)
    assert isinstance(report.cpu_cores, int)
    assert report.cpu_cores > 0
    assert isinstance(report.ram_total_mb, int)
    assert report.ram_total_mb > 0

    d = report.to_dict()
    assert "gpus" in d
    assert "cpu_model" in d
    assert "os_release" in d
    assert isinstance(d["os_release"], str)
    assert "python_version" in d


def test_read_cpu_model_does_not_crash():
    model = _read_cpu_model()
    assert isinstance(model, str)


def test_read_os_release_is_str():
    rel = _read_os_release()
    assert isinstance(rel, str)
    assert len(rel) > 0


# --- macOS probes (mocked: run on any platform) -------------------------


@pytest.fixture
def fake_run(monkeypatch):
    """Patch detect._safe_run with canned sysctl/sw_vers output."""
    calls: list[list[str]] = []

    def _install(responses: dict[str, str]):
        def _run(args):
            calls.append(args)
            for arg in args:
                if arg in responses:
                    return responses[arg]
            return ""

        monkeypatch.setattr("detect._safe_run", _run)
        return calls

    return _install


def _as_darwin(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")


def test_apple_silicon_gpu_reports_unified_memory(fake_run, monkeypatch):
    _as_darwin(monkeypatch)
    fake_run({
        "machdep.cpu.brand_string": "Apple M2 Pro",
        "hw.memsize": str(32 * 1024**3),
    })
    gpu = _read_apple_gpu()
    assert gpu is not None
    assert gpu.name == "Apple M2 Pro (unified memory)"
    assert gpu.memory_total_mb == 32 * 1024
    assert gpu.memory_total_gb == 32.0
    assert not gpu.is_cpu


def test_apple_gpu_skips_intel_macs(fake_run, monkeypatch):
    _as_darwin(monkeypatch)
    fake_run({"machdep.cpu.brand_string": "Intel(R) Core(TM) i9-9880H CPU @ 2.30GHz"})
    assert _read_apple_gpu() is None


def test_apple_gpu_skips_non_darwin(monkeypatch, fake_run):
    monkeypatch.setattr(sys, "platform", "win32")
    fake_run({"machdep.cpu.brand_string": "Apple M2 Pro"})
    assert _read_apple_gpu() is None


def test_apple_gpu_tolerates_missing_memsize(fake_run, monkeypatch):
    _as_darwin(monkeypatch)
    fake_run({"machdep.cpu.brand_string": "Apple M1"})
    gpu = _read_apple_gpu()
    assert gpu is not None
    assert gpu.name == "Apple M1 (unified memory)"
    assert gpu.memory_total_mb is None


def test_darwin_os_release_uses_sw_vers(fake_run, monkeypatch):
    _as_darwin(monkeypatch)
    fake_run({"-productVersion": "15.3.1"})
    assert _read_os_release() == "macOS 15.3.1"


def test_darwin_os_release_falls_back_when_sw_vers_missing(fake_run, monkeypatch):
    _as_darwin(monkeypatch)
    fake_run({})
    assert _read_os_release() == "darwin"


def test_safe_run_swallows_timeout(monkeypatch):
    from subprocess import TimeoutExpired

    def _hang(args, **kwargs):
        raise TimeoutExpired(cmd=" ".join(args), timeout=5)

    monkeypatch.setattr("detect.subprocess.run", _hang)
    assert _safe_run(["echo", "hi"]) == ""


def test_safe_run_swallows_missing_binary():
    assert _safe_run(["definitely-not-a-real-binary-xyz"]) == ""
