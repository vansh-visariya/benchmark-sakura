import sys
from detect import (
    GPUInfo,
    HardwareReport,
    build_report,
    detect,
    _read_cpu_model,
    _read_os_release,
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
