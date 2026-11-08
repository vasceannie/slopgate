"""Shared isolation policy for native host data directories."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class NativeDataPatch(Protocol):
    """Minimal environment-patch surface needed by the isolation policy."""

    def setenv(self, name: str, value: str) -> None: ...


def isolate_native_data_dirs(patch: NativeDataPatch, root: Path) -> None:
    """Redirect Windows user data directories beneath *root*.

    Native installers read ``LOCALAPPDATA`` (falling back to ``APPDATA``) on
    Windows, so both must point inside the caller's disposable sandbox before
    any staging path is calculated.
    """
    patch.setenv("APPDATA", str(root / "AppData" / "Roaming"))
    patch.setenv("LOCALAPPDATA", str(root / "AppData" / "Local"))
