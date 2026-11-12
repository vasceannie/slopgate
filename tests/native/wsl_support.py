"""Fake ``wsl`` and WSL-hosted ``claude`` commands for Windows-bridge tests."""

from __future__ import annotations

import os
from pathlib import Path

from pytest import MonkeyPatch

from tests.native.launchers import write_python_launcher

WSL_HOME_UNC = "\\\\wsl.localhost\\Ubuntu\\home\\trav\\.claude"
WSL_SOURCE = "/mnt/c/Users/PC/AppData/Local/slopgate/native/claude/marketplace"
WSL_PROJECT = "/mnt/c/Users/PC/project"

# The fake honours ``-d <distro>`` and ``-u <user>`` before ``-e`` so tests can
# tell which distribution and home a bridge call reached. The payload
# translation script (``sh -c <script> sh <paths...>``) resolves each path
# against the directory in FAKE_WSL_FS (the distribution's "/"), so tests build
# real symlinks there; unset, nothing exists and resolution is lexical. Drives
# are mounted under FAKE_WSL_AUTOMOUNT (default "/mnt/"), like wsl.conf's
# automount root.
_FAKE_WSL = r"""
import os
import sys

args = sys.argv[1:]
distro, user = "Ubuntu", "trav"
while args[:1] in (["-d"], ["-u"]):
    if args[0] == "-d":
        distro = args[1]
    else:
        user = args[1]
    args = args[2:]
translate = args[:3] == ["-e", "sh", "-c"] and args[4:5] == ["sh"]
logged = args[:3] + ["<script>"] + args[4:] if translate else args
with open(os.environ.get("FAKE_WSL_LOG", os.devnull), "a", encoding="utf-8") as log:
    log.write(distro + " " + user + " " + " ".join(logged) + "\n")


def windows(path):
    mount = os.environ.get("FAKE_WSL_AUTOMOUNT", "/mnt/")
    rest = path[len(mount):]
    if path.startswith(mount) and rest[:1].isalpha() and rest[1:2] in ("", "/"):
        return rest[0].upper() + ":\\" + rest[2:].replace("/", "\\")
    return "\\\\wsl.localhost\\" + distro + path.replace("/", "\\")


if translate:
    root = os.environ.get("FAKE_WSL_FS", os.path.join(os.sep, "nonexistent-fake-wsl"))
    for path in args[5:]:
        resolved = os.path.realpath(root + path)
        sys.stdout.write(windows(resolved[len(root):] or "/") + "\0")
    raise SystemExit(0)
if args[:3] == ["-e", "wslpath", "-w"]:
    print(windows(args[3]))
    raise SystemExit(0)
if args[:3] == ["-e", "sh", "-c"]:
    print("/home/" + user + "/.claude")
    raise SystemExit(0)
print("unsupported fake wsl call: " + " ".join(args), file=sys.stderr)
raise SystemExit(2)
"""

_FAKE_CLAUDE = r"""
import json
import sys

args = sys.argv[1:]
if args[:3] == ["plugin", "marketplace", "list"]:
    print(json.dumps([{
        "name": "slopgate-runtime",
        "source": "directory",
        "path": "%s",
    }]))
elif args[:2] == ["plugin", "list"]:
    print(json.dumps([{
        "id": "slopgate-enforcement@slopgate-runtime",
        "scope": "project",
        "version": "1.0.0",
        "projectEnabled": True,
        "projectPath": "%s",
    }]))
else:
    raise SystemExit(2)
""" % (WSL_SOURCE, WSL_PROJECT)


def install_wsl_commands(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    """Put a fake ``wsl`` and a Linux-path-reporting ``claude`` first on PATH."""
    bin_dir = tmp_path / "wsl-bin"
    write_python_launcher(bin_dir, "wsl", _FAKE_WSL)
    write_python_launcher(bin_dir, "claude", _FAKE_CLAUDE)
    monkeypatch.setenv("PATH", str(bin_dir) + os.pathsep + os.environ.get("PATH", ""))


def install_failing_wsl(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    """Put a ``wsl`` that always exits 3 first on PATH."""
    install_wsl_script(tmp_path, monkeypatch, "raise SystemExit(3)\n")


def install_wsl_script(tmp_path: Path, monkeypatch: MonkeyPatch, body: str) -> None:
    """Put a ``wsl`` running the Python ``body`` first on PATH."""
    bin_dir = tmp_path / "scripted-wsl-bin"
    write_python_launcher(bin_dir, "wsl", body)
    monkeypatch.setenv("PATH", str(bin_dir) + os.pathsep + os.environ.get("PATH", ""))
