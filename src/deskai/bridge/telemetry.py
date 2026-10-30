"""
Host System Telemetry Bridge Module.
Reports CPU, RAM, GPU platform metrics, GPU temperature, and CPU usage percentage
across Linux, Windows, and macOS.
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
    Detects host GPU device model, used VRAM (MB), total VRAM (MB), and GPU temperature (°C).
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
        "gpuTempC": "--",
    }

    try:
        # 1. NVIDIA via nvidia-smi
        smi = shutil.which("nvidia-smi")
        if smi:
            try:
                proc = subprocess.run(
                    [smi, "--query-gpu=name,memory.used,memory.total,temperature.gpu", "--format=csv,noheader,nounits"],
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
                        if len(parts) >= 4 and parts[3] not in ("", "[N/A]", "N/A"):
                            gpu_info["gpuTempC"] = int(float(parts[3]))
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
                    # macOS userspace GPU temp is not reliably accessible without SMC
                    gpu_info["gpuTempC"] = "--"
                    _GPU_CACHE["data"] = gpu_info
                    _GPU_CACHE["ts"] = now
                    return dict(gpu_info)
            except Exception as e:
                logger.debug("macOS Apple Silicon probe failed: %s", e)

        # 3. Linux AMD sysfs VRAM + hwmon temperature
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
                        # Try AMD hwmon temperature (millidegrees → degrees)
                        hwmon_base = os.path.join(card_dev, "hwmon")
                        if os.path.exists(hwmon_base):
                            for hwmon in os.listdir(hwmon_base):
                                temp_path = os.path.join(hwmon_base, hwmon, "temp1_input")
                                if os.path.exists(temp_path):
                                    try:
                                        with open(temp_path, "r", encoding="utf-8") as f:
                                            millideg = int(f.read().strip())
                                        gpu_info["gpuTempC"] = millideg // 1000
                                    except Exception:
                                        pass
                                    break
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


def detect_cpu_temperature() -> Any:
    """
    Detects host CPU temperature in degrees Celsius (°C).
    Supports Linux (psutil coretemp/k10temp/thermal_zone sysfs),
    falling back to '--' if unavailable or unsupported on the platform.
    """
    try:
        import psutil

        if hasattr(psutil, "sensors_temperatures"):
            temps = psutil.sensors_temperatures()
            if temps:
                # 1. Known primary CPU thermal sensor drivers
                for key in ("coretemp", "k10temp", "zenpower", "cpu_thermal", "soc_thermal"):
                    if key in temps and temps[key]:
                        # Prefer Package id 0 / Tdie / Tctl
                        for entry in temps[key]:
                            lbl = (entry.label or "").lower()
                            if "package id 0" in lbl or "tdie" in lbl or "tctl" in lbl:
                                if entry.current is not None and entry.current > 0:
                                    return int(round(entry.current))
                        # Fallback to first non-zero entry in this sensor
                        for entry in temps[key]:
                            if entry.current is not None and entry.current > 0:
                                return int(round(entry.current))

                # 2. Any sensor with 'cpu' in key name
                for name, entries in temps.items():
                    if "cpu" in name.lower() and entries:
                        for entry in entries:
                            if entry.current is not None and entry.current > 0:
                                return int(round(entry.current))
    except Exception as e:
        logger.debug("psutil sensors_temperatures probe failed: %s", e)

    # 3. Direct Linux sysfs thermal zone probe fallback
    if os.name != "nt" and os.path.exists("/sys/class/thermal"):
        try:
            for zone in sorted(os.listdir("/sys/class/thermal")):
                if zone.startswith("thermal_zone"):
                    type_p = os.path.join("/sys/class/thermal", zone, "type")
                    temp_p = os.path.join("/sys/class/thermal", zone, "temp")
                    if os.path.exists(type_p) and os.path.exists(temp_p):
                        try:
                            with open(type_p, "r", encoding="utf-8") as f:
                                t_type = f.read().strip().lower()
                            if any(k in t_type for k in ("x86_pkg_temp", "cpu", "k10temp", "coretemp")):
                                with open(temp_p, "r", encoding="utf-8") as f:
                                    raw_val = int(f.read().strip())
                                    if raw_val > 0:
                                        return int(round(raw_val / 1000.0))
                        except Exception:
                            continue
        except Exception as e:
            logger.debug("sysfs thermal zone probe failed: %s", e)

    return "--"


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
            "gpuTempC": "--",
            "cpuTempC": "--",
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
            telemetry["gpuTempC"] = gpu_data.get("gpuTempC", "--")

            # 2. Host RAM and CPU telemetry across platforms (Linux, Windows, macOS)
            telemetry["cpuTempC"] = detect_cpu_temperature()
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
