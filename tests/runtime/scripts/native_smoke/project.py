from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import cast

from .sandbox import Sandbox, SmokeFailure, run_command

OMP_MANIFEST = {
    "name": "omp-slopgate",
    "private": True,
    "type": "module",
    "omp": {"extensions": ["./index.ts"]},
    "peerDependencies": {
        "@oh-my-pi/pi-coding-agent": "*",
        "@oh-my-pi/pi-tui": "*",
    },
}
_OMP_INDEX = '// OMP Slopgate Extension\nconst SLOPGATE_ARGV = ["__SLOPGATE_BIN__"]\n// slopgate handle --platform omp\n'
_PI_INDEX = '// Pi Slopgate Extension\nconst SLOPGATE_ARGV = ["__SLOPGATE_BIN__"]\n// slopgate handle --platform pi\n'
_PI_LEGACY_PACKAGE_ENTRY = "// pi-slopgate\n// slopgate handle --platform pi\n"
_PI_PACKAGE_METADATA = {
    "private": True,
    "type": "module",
    "dependencies": {"@earendil-works/pi-tui": "*"},
}
_CLAUDE_OWNED_MARKER = "slopgate handle --platform claude"


def _link_runtime_peer_scope(sandbox: Sandbox, name: str, workspace: str) -> None:
    source = sandbox.repo / "tests" / "runtime" / workspace / "node_modules" / name
    if not source.is_dir():
        raise SmokeFailure(f"Pinned runtime peer dependencies are missing: {source}")
    target = sandbox.root / "node_modules" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        shutil.copytree(source, target)
    else:
        target.symlink_to(source, target_is_directory=True)


def _link_runtime_peers(sandbox: Sandbox) -> None:
    _link_runtime_peer_scope(sandbox, "@oh-my-pi", "omp")
    _link_runtime_peer_scope(sandbox, "@earendil-works", "pi")


def _trust_pi_sandbox_project(sandbox: Sandbox) -> None:
    # Model the operator's explicit trust decision without a CLI approval flag.
    trust_path = sandbox.pi_agent / "trust.json"
    trust_path.write_text(
        json.dumps({str(sandbox.project.resolve()): True}, indent=2) + "\n",
        encoding="utf-8",
    )


def prepare_project(sandbox: Sandbox) -> None:
    sandbox.project.mkdir(parents=True, exist_ok=True)
    (sandbox.project / "slopgate.toml").write_text(
        "[slopgate]\nenabled = true\n", encoding="utf-8"
    )
    (sandbox.project / "README.md").write_text(
        "Native installer smoke project.\n", encoding="utf-8"
    )
    run_command(
        ["git", "init", "--quiet", str(sandbox.project)],
        sandbox.root,
        sandbox.environment("claude"),
        "Initializing enrolled smoke project",
    )
    _trust_pi_sandbox_project(sandbox)
    _link_runtime_peers(sandbox)


def legacy_paths(sandbox: Sandbox, host: str, scope: str) -> tuple[Path, ...]:
    root = _scope_root(sandbox, host, scope)
    if host == "omp":
        package = root / "extensions" / "omp-slopgate"
        return (package / "index.ts", package / "package.json")
    if host == "pi":
        extension = root / "extensions" / "pi-slopgate"
        return (
            extension / "index.ts",
            extension / "index.js",
            extension / "package.json",
            extension / "config.json",
            root / "extensions" / "slopgate.ts",
        )
    return ()


def _scope_root(sandbox: Sandbox, host: str, scope: str) -> Path:
    if scope == "user":
        if host == "omp":
            return sandbox.omp_agent
        if host == "pi":
            return sandbox.pi_agent
        return sandbox.home
    if scope == "project" and host == "omp":
        return sandbox.project / ".omp"
    if scope == "project" and host == "pi":
        return sandbox.project / ".pi"
    if scope == "project":
        return sandbox.project
    raise SmokeFailure(f"Unsupported legacy scope: {scope}")


def _write_omp_legacy(sandbox: Sandbox) -> None:
    for scope in ("user", "project"):
        index, manifest = legacy_paths(sandbox, "omp", scope)
        index.parent.mkdir(parents=True, exist_ok=True)
        index.write_text(_OMP_INDEX, encoding="utf-8")
        manifest.write_text(json.dumps(OMP_MANIFEST, indent=2) + "\n", encoding="utf-8")


def _write_pi_package(root: Path) -> None:
    extension = root / "extensions" / "pi-slopgate"
    extension.mkdir(parents=True, exist_ok=True)
    (extension / "index.ts").write_text(_PI_INDEX, encoding="utf-8")
    (extension / "index.js").write_text(_PI_LEGACY_PACKAGE_ENTRY, encoding="utf-8")
    (extension / "package.json").write_text(
        json.dumps(_PI_PACKAGE_METADATA, indent=2) + "\n", encoding="utf-8"
    )
    (extension / "config.json").write_text(
        json.dumps({"name": "pi-slopgate"}, indent=2) + "\n", encoding="utf-8"
    )


def _write_pi_legacy(sandbox: Sandbox) -> None:
    for scope in ("user", "project"):
        root = _scope_root(sandbox, "pi", scope)
        _write_pi_package(root)
        standalone = root / "extensions" / "slopgate.ts"
        standalone.parent.mkdir(parents=True, exist_ok=True)
        standalone.write_text(_PI_INDEX, encoding="utf-8")


def _settings_document(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise SmokeFailure(f"Claude settings are not an object: {path}")
    return cast(dict[str, object], parsed)


def _write_claude_hooks(path: Path, binary: Path, scope: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    settings = _settings_document(path)
    hooks = settings.get("hooks", {})
    if not isinstance(hooks, dict):
        raise SmokeFailure(
            f"Cannot seed legacy Claude hooks into malformed settings: {path}"
        )
    hooks_dict = cast(dict[str, object], hooks)
    raw_groups = hooks_dict.get("PreToolUse", [])
    if not isinstance(raw_groups, list):
        raise SmokeFailure(f"Cannot seed legacy Claude PreToolUse group: {path}")
    groups = cast(list[object], raw_groups)
    groups.append(
        {
            "matcher": "*",
            "hooks": [
                {"type": "command", "command": f"{binary} handle --platform claude"}
            ],
        }
    )
    groups.append(
        {
            "matcher": "Bash",
            "hooks": [{"type": "command", "command": "echo preserved-user-hook"}],
        }
    )
    hooks_dict["PreToolUse"] = groups
    settings["hooks"] = hooks_dict
    settings[f"smoke_{scope}_setting"] = "preserve-me"
    path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")


def _write_claude_legacy(sandbox: Sandbox) -> None:
    _write_claude_hooks(
        sandbox.home / ".claude" / "settings.json", sandbox.slopgate_binary, "user"
    )
    _write_claude_hooks(
        sandbox.project / ".claude" / "settings.json",
        sandbox.slopgate_binary,
        "project",
    )


def seed_legacy_installations(sandbox: Sandbox) -> None:
    _write_omp_legacy(sandbox)
    _write_pi_legacy(sandbox)
    _write_claude_legacy(sandbox)


def active_legacy_paths(sandbox: Sandbox, host: str) -> tuple[Path, ...]:
    return tuple(
        path
        for scope in ("user", "project")
        for path in legacy_paths(sandbox, host, scope)
    )


def assert_legacy_paths_removed(sandbox: Sandbox, host: str) -> None:
    remaining = [
        str(path) for path in active_legacy_paths(sandbox, host) if path.exists()
    ]
    if remaining:
        raise SmokeFailure(
            f"{host} legacy active copies remain after native cutover: {remaining}"
        )


def _is_owned_command(command: object) -> bool:
    if not isinstance(command, dict):
        return False
    data = cast(dict[str, object], command)
    return _CLAUDE_OWNED_MARKER in str(data.get("command", ""))


def _group_has_owned_hook(group: object, path: Path) -> bool:
    if not isinstance(group, dict):
        raise SmokeFailure(f"Claude hook group is malformed after cutover: {path}")
    group_data = cast(dict[str, object], group)
    raw_commands = group_data.get("hooks", [])
    if not isinstance(raw_commands, list):
        raise SmokeFailure(f"Claude hook commands are malformed after cutover: {path}")
    commands = cast(list[object], raw_commands)
    return any(_is_owned_command(command) for command in commands)


def _settings_have_owned_hook(path: Path) -> bool:
    hooks = _settings_document(path).get("hooks", {})
    if not isinstance(hooks, dict):
        raise SmokeFailure(f"Claude hooks settings are malformed after cutover: {path}")
    for raw_groups in cast(dict[str, object], hooks).values():
        if not isinstance(raw_groups, list):
            raise SmokeFailure(
                f"Claude hook groups are malformed after cutover: {path}"
            )
        groups = cast(list[object], raw_groups)
        if any(_group_has_owned_hook(group, path) for group in groups):
            return True
    return False


def _settings_have_preserved_hook(path: Path) -> bool:
    hooks = _settings_document(path).get("hooks", {})
    return "echo preserved-user-hook" in json.dumps(hooks)


def assert_claude_legacy_hooks_removed(sandbox: Sandbox) -> None:
    settings_paths = (
        sandbox.home / ".claude" / "settings.json",
        sandbox.project / ".claude" / "settings.json",
    )
    for path in settings_paths:
        if _settings_have_owned_hook(path):
            raise SmokeFailure(f"Legacy Slopgate Claude hook remains active in {path}")
        if not _settings_have_preserved_hook(path):
            raise SmokeFailure(f"Unrelated Claude hook was not preserved in {path}")
    user_settings = _settings_document(settings_paths[0])
    project_settings = _settings_document(settings_paths[1])
    if user_settings.get("smoke_user_setting") != "preserve-me":
        raise SmokeFailure(
            f"Unrelated user Claude setting was not preserved: {settings_paths[0]}"
        )
    if project_settings.get("smoke_project_setting") != "preserve-me":
        raise SmokeFailure(
            f"Unrelated project Claude setting was not preserved: {settings_paths[1]}"
        )
