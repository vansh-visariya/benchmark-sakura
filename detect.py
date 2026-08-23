"""Host hardware detection.

The benchmark's anti-cheat rests on measuring the host's real capabilities
rather than trusting user-entered values. A contributor cannot claim to have
run an 8B model on a GPU with too little VRAM, because the report records the
*measured* VRAM the probe found.

This module probes for a discrete GPU first, then falls back to CPU-only
detection. It deliberately tolerates platforms where a particular probe is
unavailable (e.g. no ``nvidia-smi`` on AMD-only or integrated systems) so the
runner still produces a usable report.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psutil

from config import Config


@dataclass(frozen=True)
class GPUInfo:
    """A single discrete GPU, or a CPU-only fallback."""

    name: str
    memory_total_mb: int | None = None
    is_cpu: bool = False

    @property
    def memory_total_gb(self) -> float | None:
        return None if self.memory_total_mb is None else round(self.memory_total_mb / 1024, 2)


@dataclass(frozen=True)
class HardwareReport:
    """A point-in-time snapshot of the host, ready to serialize to the result."""

    gpus: list[GPUInfo]
    cpu_model: str
    cpu_cores: int
    ram_total_mb: int
    ram_available_mb: int
    platform: str
    os_release: str
    python_version: str
    detected_at: str  # ISO 8601, UTC

    @property
    def discrete_gpu(self) -> GPUInfo | None:
        for gpu in self.gpus:
            if not gpu.is_cpu:
                return gpu
        return None

    @property
    def has_discrete_gpu(self) -> bool:
        return self.discrete_gpu is not None

    @property
    def max_vram_gb(self) -> float | None:
        vram = [gpu.memory_total_gb for gpu in self.gpus if gpu.memory_total_gb]
        return max(vram) if vram else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "gpus": [
                {
                    "name": gpu.name,
                    "memory_total_mb": gpu.memory_total_mb,
                    "memory_total_gb": gpu.memory_total_gb,
                    "is_cpu": gpu.is_cpu,
                }
                for gpu in self.gpus
            ],
            "cpu_model": self.cpu_model,
            "cpu_cores": self.cpu_cores,
            "ram_total_mb": self.ram_total_mb,
            "ram_available_mb": self.ram_available_mb,
            "ram_total_gb": round(self.ram_total_mb / 1024, 2),
            "platform": self.platform,
            "os_release": self.os_release,
            "python_version": self.python_version,
            "detected_at": self.detected_at,
        }


def _iso_now() -> str:
    # datetime is unavailable inside workflow scripts, but this is application
    # code, not a workflow, so the normal import is fine here.
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def _read_cpu_model() -> str:
    if sys.platform == "win32":
        try:
            import winreg

            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
            )
            val, _ = winreg.QueryValueEx(key, "ProcessorNameString")
            winreg.CloseKey(key)
            if val:
                return str(val).strip()
        except Exception:
            pass
        try:
            import wmi  # type: ignore[import-untyped]

            for cpu in wmi.WMI().Win32_Processor():
                return str(cpu.Name)
        except Exception:
            return "unknown"
    if sys.platform == "darwin":
        out = _safe_run(["sysctl", "-n", "machdep.cpu.brand_string"])
        if out:
            return out.strip()
    out = _safe_run(["cat", "/proc/cpuinfo"])
    if out:
        for line in out.splitlines():
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    return "unknown"


def _read_os_release() -> str:
    if sys.platform == "win32":
        v = sys.getwindowsversion()
        return f"{v.major}.{v.minor}.{v.build}"
    out = _safe_run(["cat", "/etc/os-release"])
    if out:
        for line in out.splitlines():
            if line.startswith("PRETTY_NAME="):
                return line.split("=", 1)[1].strip().strip('"')
    return sys.platform


def _safe_run(args: list[str]) -> str:
    result = subprocess.run(args, capture_output=True, text=True, timeout=5)
    if result.returncode != 0:
        return ""
    return result.stdout


def _read_nvidia_gpu() -> GPUInfo | None:
    nvidia_smi = shutil.which("nvidia-smi")
    if not nvidia_smi:
        return None
    out = _safe_run([nvidia_smi, "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"])
    if not out:
        return None
    name = out.splitlines()[0].split(",")[0].strip() if out.strip() else "NVIDIA GPU"
    total_mb = 0
    for line in out.splitlines():
        if line.strip():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 2:
                try:
                    total_mb = max(total_mb, int(float(parts[1])))
                except ValueError:
                    continue
    return GPUInfo(name=name, memory_total_mb=total_mb)


def _read_gpu() -> GPUInfo | None:
    """Probe for a discrete GPU across vendors; return None if none is found."""
    for probe in (_read_nvidia_gpu, _read_amd_gpu, _read_intel_gpu):
        try:
            gpu = probe()
        except Exception:
            gpu = None
        if gpu is not None:
            return gpu
    return None


def _read_amd_gpu() -> GPUInfo | None:
    rocminfo = shutil.which("rocminfo")
    if not rocminfo:
        return None
    out = _safe_run([rocminfo])
    name = "AMD GPU"
    mem = 0
    for line in out.splitlines():
        if "Name" in line:
            name = line.split(":", 1)[1].strip() if ":" in line else name
        if "Number of bytes" in line:
            try:
                mem = max(mem, int(line.split(":", 1)[1].strip().split()[0]))
            except (IndexError, ValueError):
                continue
    return GPUInfo(name=name, memory_total_mb=mem // (1024 * 1024))


def _read_intel_gpu() -> GPUInfo | None:
    intel_gpu_info = shutil.which("intel_gpu_info")
    if not intel_gpu_info:
        return None
    out = _safe_run([intel_gpu_info, "-v"])
    mem = 0
    for line in out.splitlines():
        if "Memory" in line.lower():
            try:
                mem = int(line.split(":")[1].split()[0])
            except (IndexError, ValueError):
                continue
    return GPUInfo(name="Intel GPU", memory_total_mb=mem)


def _read_cpu_cores() -> int:
    logical = psutil.cpu_count(logical=True) or 0
    physical = psutil.cpu_count(logical=False) or 0
    return physical or logical


def build_report(config: Config | None = None) -> HardwareReport:
    """Assemble a :class:`HardwareReport` for the current host.

    A discrete GPU is reported first if one is found; otherwise a CPU-only
    :class:`GPUInfo` stands in so downstream code has a uniform shape.
    """
    discrete = _read_gpu()
    if discrete is not None:
        gpus = [discrete]
    else:
        gpus = [GPUInfo(name="CPU", memory_total_mb=None, is_cpu=True)]

    return HardwareReport(
        gpus=gpus,
        cpu_model=_read_cpu_model(),
        cpu_cores=_read_cpu_cores(),
        ram_total_mb=psutil.virtual_memory().total // (1024 * 1024),
        ram_available_mb=psutil.virtual_memory().available // (1024 * 1024),
        platform=sys.platform,
        os_release=_read_os_release(),
        python_version=".".join(str(part) for part in sys.version_info[:3]),
        detected_at=_iso_now(),
    )


def detect(config: Config | None = None) -> HardwareReport:
    """Public entry point; identical to :func:`build_report`."""
    return build_report(config)
