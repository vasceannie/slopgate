"""Deterministic fake `pi` executable for native installer tests."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Protocol, cast

from tests.native.launchers import write_python_launcher

# Matches the pinned Pi runtime contract in tests/runtime/pi/package.json.
PINNED_PI_VERSION = "0.85.1"


class _EnvironmentPatch(Protocol):
    def setenv(self, name: str, value: str) -> None: ...


class FakePi:
    """An isolated Pi command that mutates only test-owned settings files."""

    def __init__(self, root: Path, agent_dir: Path) -> None:
        self.bin_dir = root / "bin"
        self.state_path = root / "state.json"
        self.calls_path = root / "calls.jsonl"
        self.agent_dir = agent_dir
        self.script_path = write_python_launcher(self.bin_dir, "pi", _FAKE_SCRIPT)
        self.state_path.write_text(
            json.dumps(
                {
                    "failure_action": None,
                    "failure_scope": None,
                    "failure_mutates": False,
                    "project_trusted": True,
                    "version": PINNED_PI_VERSION,
                }
            ),
            encoding="utf-8",
        )

    def activate(self, monkeypatch: _EnvironmentPatch) -> None:
        """Put the fake first on PATH and direct Pi user state into its sandbox."""
        monkeypatch.setenv("FAKE_PI_STATE", str(self.state_path))
        current_path = os.environ.get("PATH", "")
        monkeypatch.setenv("PATH", str(self.bin_dir) + os.pathsep + current_path)
        monkeypatch.setenv("PI_CODING_AGENT_DIR", str(self.agent_dir))

    def fail(
        self, action: str, scope: str, *, mutate_before_failure: bool = False
    ) -> None:
        state = self._state()
        state.update(
            {
                "failure_action": action,
                "failure_scope": scope,
                "failure_mutates": mutate_before_failure,
            }
        )
        self._write_state(state)

    def set_version(self, version: str) -> None:
        state = self._state()
        state["version"] = version
        self._write_state(state)

    def set_project_trusted(self, trusted: bool) -> None:
        state = self._state()
        state["project_trusted"] = trusted
        self._write_state(state)

    def calls(self) -> list[dict[str, object]]:
        if not self.calls_path.exists():
            return []
        records = [
            json.loads(line)
            for line in self.calls_path.read_text(encoding="utf-8").splitlines()
        ]
        return cast(list[dict[str, object]], records)

    def _state(self) -> dict[str, object]:
        return cast(
            dict[str, object], json.loads(self.state_path.read_text(encoding="utf-8"))
        )

    def _write_state(self, state: dict[str, object]) -> None:
        self.state_path.write_text(json.dumps(state), encoding="utf-8")


_FAKE_SCRIPT = r"""#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

state_path = Path(os.environ["FAKE_PI_STATE"])
state = json.loads(state_path.read_text(encoding="utf-8"))
args = sys.argv[1:]
action = args[0] if args else ""
scope = "project" if "-l" in args else "user"
source_arg = next((arg for arg in args[1:] if not arg.startswith("-")), "")
source = Path(source_arg).expanduser().resolve() if source_arg else None
cwd = Path.cwd()
agent_dir = Path(os.environ["PI_CODING_AGENT_DIR"]).resolve()
settings_dir = cwd / ".pi" if scope == "project" else agent_dir
settings_path = settings_dir / "settings.json"
calls_path = state_path.with_name("calls.jsonl")
record = {"argv": args, "cwd": str(cwd), "scope": scope}
with calls_path.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps(record) + "\n")


def read_settings():
    if not settings_path.exists():
        return {"packages": []}
    return json.loads(settings_path.read_text(encoding="utf-8"))


def source_of(entry):
    if isinstance(entry, str):
        return entry
    if isinstance(entry, dict) and isinstance(entry.get("source"), str):
        return entry["source"]
    return ""


def resolves_to(entry, target):
    value = source_of(entry)
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = settings_dir / path
    return path.resolve() == target


def write_settings(document):
    settings_dir.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")


def should_fail():
    return state.get("failure_action") == action and state.get("failure_scope") == scope


def fail_now():
    print("injected fake Pi failure", file=sys.stderr)
    raise SystemExit(2)


if action in ("install", "remove", "uninstall") and source is not None:
    if action in ("remove", "uninstall") and scope == "project" and not state.get("project_trusted", True):
        print("Project is not trusted. Use --approve to modify local package config.", file=sys.stderr)
        raise SystemExit(1)
    if should_fail() and not state.get("failure_mutates", False):
        fail_now()
    document = read_settings()
    packages = document.setdefault("packages", [])
    if action == "install":
        if not any(resolves_to(entry, source) for entry in packages):
            relative = os.path.relpath(source, settings_dir)
            packages.append(relative)
    else:
        document["packages"] = [entry for entry in packages if not resolves_to(entry, source)]
    write_settings(document)
    if should_fail():
        fail_now()
    print(("Installed " if action == "install" else "Removed ") + str(source))
elif action == "--version":
    print(state["version"])
elif action == "list":
    document = read_settings()
    packages = document.get("packages", [])
    if not packages:
        print("No packages installed.")
    else:
        print("User packages:")
        for entry in packages:
            source_text = source_of(entry)
            source_path = Path(source_text).expanduser()
            if not source_path.is_absolute():
                source_path = settings_dir / source_path
            filtered = isinstance(entry, dict) and any(
                key in entry for key in ("extensions", "skills", "prompts", "themes")
            )
            print("  " + source_text + (" (filtered)" if filtered else ""))
            print("    " + str(source_path.resolve()))
else:
    print("unsupported fake Pi command", file=sys.stderr)
    raise SystemExit(2)
"""
