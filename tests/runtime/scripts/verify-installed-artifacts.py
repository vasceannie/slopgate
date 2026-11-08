"""Validate native OMP, Pi, and Claude registrations in a disposable sandbox.

Usage: python3 tests/runtime/scripts/verify-installed-artifacts.py
"""

from __future__ import annotations

from native_smoke import run


if __name__ == "__main__":
    raise SystemExit(run())
