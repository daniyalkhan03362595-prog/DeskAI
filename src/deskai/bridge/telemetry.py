"""
Host System Telemetry Bridge Module.
Reports CPU, RAM, and GPU platform metrics across Linux, Windows, and macOS.
"""

import logging
import os
import shutil
import subprocess
import time
from typing import Any

from deskai.bridge.base import BaseBridgeModule

logger = logging.getLogger(__name__)

_GPU_CACHE: dict[str, Any] = {"data": None, "ts": 0.0}
_GPU_CACHE_TTL = 3.0  # seconds


def detect_host_gpu() -> dict[str, Any]:
    """
    Detects host GPU device model, used VRAM (MB), and total VRAM (MB).
    Supports NVIDIA (nvidia-smi), macOS (Apple Silicon unified), and Linux AMD (/sys/class/drm).
    Caches probe results for 3 seconds to avoid subprocess execution overhead.
    """
    now = time.time()
    if _GPU_CACHE["data"] is not None and (now - _GPU_CACHE["ts"]) < _GPU_CACHE_TTL:
        return dict(_GPU_CACHE["data"])

    gpu_info: dict[str, Any] = {
        "gpuName": "--",
        "vramUsedMB": "--",
        "vramTotalMB": "--",
    }

    try:
        # 1. NVIDIA via nvidia-smi
        smi = shutil.which("nvidia-smi")
        if smi:
            try:
                proc = subprocess.run(
                    [smi, "--query-gpu=name,memory.used,memory.total", "--format=csv,noheader,nounits"],
                    capture_output=True,
                    text=True,
                    timeout=1.5,
                    check=False,
                )
                if proc.returncode == 0 and proc.stdout.strip():
                    first_line = proc.stdout.strip().splitlines()[0]
                    parts = [p.strip() for p in first_line.split(",")]
                    if len(parts) >= 3:
                        gpu_info["gpuName"] = parts[0]
                        gpu_info["vramUsedMB"] = int(float(parts[1]))
                        gpu_info["vramTotalMB"] = int(float(parts[2]))
                        _GPU_CACHE["data"] = gpu_info
                        _GPU_CACHE["ts"] = now
                        return dict(gpu_info)
            except Exception as e:
                logger.debug("nvidia-smi probe failed: %s", e)

        # 2. Apple Silicon / macOS
        import platform

        if platform.system() == "Darwin":
            try:
                proc = subprocess.run(
                    ["sysctl", "-n", "machdep.cpu.brand_string"],
                    capture_output=True,
                    text=True,
                    timeout=1.0,
                    check=False,
                )
                brand = proc.stdout.strip()
                if "Apple" in brand:
                    gpu_info["gpuName"] = f"{brand} (Integrated)"
                    try:
                        import psutil

                        vm = psutil.virtual_memory()
                        gpu_info["vramTotalMB"] = int(vm.total // (1024 * 1024))
                        gpu_info["vramUsedMB"] = int(vm.used // (1024 * 1024))
                    except Exception:
                        pass
                    _GPU_CACHE["data"] = gpu_info
                    _GPU_CACHE["ts"] = now
                    return dict(gpu_info)
            except Exception as e:
                logger.debug("macOS Apple Silicon probe failed: %s", e)

        # 3. Linux AMD sysfs VRAM
        if os.name != "nt" and os.path.exists("/sys/class/drm"):
            try:
                for entry in os.listdir("/sys/class/drm"):
                    card_dev = os.path.join("/sys/class/drm", entry, "device")
                    vram_total_path = os.path.join(card_dev, "mem_info_vram_total")
                    vram_used_path = os.path.join(card_dev, "mem_info_vram_used")
                    if os.path.exists(vram_total_path):
                        with open(vram_total_path, "r", encoding="utf-8") as f:
                            total_bytes = int(f.read().strip())
                        used_bytes = 0
                        if os.path.exists(vram_used_path):
                            with open(vram_used_path, "r", encoding="utf-8") as f:
                                used_bytes = int(f.read().strip())
                        gpu_info["gpuName"] = "AMD Radeon GPU"
                        gpu_info["vramTotalMB"] = int(total_bytes // (1024 * 1024))
                        gpu_info["vramUsedMB"] = int(used_bytes // (1024 * 1024))
                        _GPU_CACHE["data"] = gpu_info
                        _GPU_CACHE["ts"] = now
                        return dict(gpu_info)
            except Exception as e:
                logger.debug("Linux AMD sysfs probe failed: %s", e)

    except Exception as e:
        logger.debug("GPU detection error: %s", e)

    _GPU_CACHE["data"] = gpu_info
    _GPU_CACHE["ts"] = now
    return dict(gpu_info)


class TelemetryBridge(BaseBridgeModule):
    """Bridge methods for system telemetry reporting."""

    def get_system_telemetry(self) -> dict:
        """Returns real host system telemetry across Linux, macOS, and Windows, or explicit 'unavailable' fallbacks."""
        if not self._is_origin_allowed():
            return {"status": "error", "message": "Unauthorized origin", "telemetry": None}

        telemetry: dict[str, Any] = {
            "gpuName": "--",
            "vramUsedMB": "--",
            "vramTotalMB": "--",
            "cpuUsagePct": "unavailable",
            "ramUsedMB": "unavailable",
            "ramTotalMB": "unavailable",
            "status": "ready",
        }

        try:
            import platform

            telemetry["platform"] = platform.system()

            # 1. Hardware GPU & VRAM detection
            gpu_data = detect_host_gpu()
            telemetry["gpuName"] = gpu_data["gpuName"]
            telemetry["vramUsedMB"] = gpu_data["vramUsedMB"]
            telemetry["vramTotalMB"] = gpu_data["vramTotalMB"]

            # 2. Host RAM and CPU telemetry across platforms (Linux, Windows, macOS)
            telemetry_obtained = False
            try:
                import psutil

                vm = psutil.virtual_memory()
                telemetry["ramTotalMB"] = int(vm.total // (1024 * 1024))
                telemetry["ramUsedMB"] = int(vm.used // (1024 * 1024))
                cpu = psutil.cpu_percent(interval=None)
                telemetry["cpuUsagePct"] = f"{cpu:.1f}%"
                telemetry_obtained = True
            except Exception:
                telemetry_obtained = False

            if not telemetry_obtained and os.name != "nt" and os.path.exists("/proc/meminfo"):
                mem = {}
                with open("/proc/meminfo", "r", encoding="utf-8") as f:
                    for line in f:
                        parts = line.split(":")
                        if len(parts) == 2:
                            mem[parts[0].strip()] = parts[1].strip()
                if "MemTotal" in mem and "MemAvailable" in mem:
                    total_kb = int(mem["MemTotal"].split()[0])
                    avail_kb = int(mem["MemAvailable"].split()[0])
                    used_mb = (total_kb - avail_kb) // 1024
                    telemetry["ramUsedMB"] = used_mb
                    telemetry["ramTotalMB"] = total_kb // 1024
        except Exception as e:
            logger.debug("Telemetry collection error: %s", e)

        return {"status": "ok", "telemetry": telemetry}
