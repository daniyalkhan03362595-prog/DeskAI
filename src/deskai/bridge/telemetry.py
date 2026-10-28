"""
Host System Telemetry Bridge Module.
Reports CPU, RAM, and platform metrics across Linux, Windows, and macOS.
"""

import logging
import os
from typing import Any

from deskai.bridge.base import BaseBridgeModule

logger = logging.getLogger(__name__)


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

            # Attempt psutil telemetry across platforms (Linux, Windows, macOS)
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
                with open("/proc/meminfo", "r") as f:
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
