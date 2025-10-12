"""Performance guardrails for CLI import-time."""

from __future__ import annotations

import importlib
import sys
import time


def test_cli_import_time_under_half_second() -> None:
    """Importing recozik.cli should stay fast to keep the UX responsive."""
    module_name = "recozik.cli"
    original = sys.modules.pop(module_name, None)

    start = time.perf_counter()
    module = importlib.import_module(module_name)
    elapsed = time.perf_counter() - start

    if original is not None:
        sys.modules[module_name] = original
        sys.modules["recozik"].cli = original
    else:
        sys.modules[module_name] = module
        sys.modules["recozik"].cli = module

    assert elapsed < 0.5, f"recozik.cli import took {elapsed:.3f}s (expected < 0.5s)"
