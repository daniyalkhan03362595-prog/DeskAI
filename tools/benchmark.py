#!/usr/bin/env python3
"""
DeskAI Layer 1 Benchmark Utility.
Measures cold startup time and memory footprint (RSS) of DeskAI supervisor and presentation stack.
"""
import resource
import time
from deskai.server.supervisor import DesktopServer


def benchmark_supervisor_startup():
    print("[Benchmark] Measuring DesktopServer cold startup...")
    t0 = time.perf_counter()
    server = DesktopServer()
    server.start()
    t1 = time.perf_counter()
    startup_ms = (t1 - t0) * 1000

    # Read memory usage
    max_rss_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    max_rss_mb = max_rss_kb / 1024.0

    print(f"[Benchmark] Cold Start Time: {startup_ms:.2f} ms")
    print(f"[Benchmark] Peak RSS Memory: {max_rss_mb:.2f} MB")

    server.stop()
    return startup_ms, max_rss_mb


if __name__ == "__main__":
    benchmark_supervisor_startup()
