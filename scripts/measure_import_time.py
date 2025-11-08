"""Utility script to measure recozik.cli import-time."""

from __future__ import annotations

import importlib
import statistics
import time
from typing import Final

TARGET_MODULE: Final[str] = "recozik.cli"
RUNS: Final[int] = 5


def measure_once() -> float:
    """Import the target module once and return the elapsed time in seconds."""
    start = time.perf_counter()
    importlib.import_module(TARGET_MODULE)
    return time.perf_counter() - start


def main() -> None:
    """Measure multiple runs and print summary statistics."""
    durations = [measure_once() for _ in range(RUNS)]
    mean = statistics.mean(durations)
    best = min(durations)
    worst = max(durations)
    print(f"Measured {TARGET_MODULE} import-time over {RUNS} runs:")
    print(f"  mean:  {mean:.4f}s")
    print(f"  best:  {best:.4f}s")
    print(f"  worst: {worst:.4f}s")


if __name__ == "__main__":
    main()
