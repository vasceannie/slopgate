from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from subprocess import CompletedProcess
from typing import cast

from .sandbox import Sandbox, SmokeFailure, run_command

OMP_ID = "omp-slopgate@slopgate-runtime"
CLAUDE_ID = "slopgate-enforcement@slopgate-runtime"
PI_NAME = "pi-slopgate"
UNRELATED_OMP_ID = "smoke-unrelated@smoke-other"
UNRELATED_CLAUDE_ID = "smoke-unrelated@smoke-other"
UNRELATED_PI_NAME = "smoke-unrelated"
SCOPES = ("user", "project")


@dataclass(frozen=True, slots=True)
class SlopgateAction:
    action: str
    host: str
    scope: str
    dry_run: bool = False
    alternate_binary: bool = False


def stage_root(sandbox: Sandbox, host: str) -> Path:
    data_root = (
        sandbox.root / "localappdata"
        if os.name == "nt"
        else sandbox.home / ".local" / "share"
    )
    return data_root / "slopgate" / "native" / host


def package_root(sandbox: Sandbox, host: str) -> Path:
    root = stage_root(sandbox, host)
    return root / ("package" if host == "pi" else "marketplace")


def run_host(
    sandbox: Sandbox, host: str, args: list[str], cwd: Path | None = None
) -> CompletedProcess[str]:
    if host not in sandbox.binaries:
        raise SmokeFailure(f"No sandbox executable was selected for host {host}")
    binary = Path(sandbox.binaries[host]).resolve()
    if not binary.is_file():
        raise SmokeFailure(f"Selected {host} executable is missing: {binary}")
    return run_command(
        [str(binary), *args],
        cwd or sandbox.project,
        sandbox.environment(host),
        f"Running native {host} command",
    )


def run_slopgate(sandbox: Sandbox, request: SlopgateAction) -> CompletedProcess[str]:
    command = ["slopgate", request.action, request.host]
    if request.dry_run:
        command.append("--dry-run")
    command.extend(
        (
            "--install-scope",
            request.scope,
            "--project-root",
            str(sandbox.project),
            "--disable-autoupdate",
        )
    )
    if command.count("--disable-autoupdate") != 1:
        raise SmokeFailure(
            f"Slopgate {request.action} command omitted its autoupdate guard"
        )
    env = sandbox.environment(request.host, request.alternate_binary)
    return run_command(
        command,
        sandbox.repo,
        env,
        f"Slopgate {request.action} {request.host} ({request.scope} scope)",
    )


def _json_object(stdout: str, label: str) -> dict[str, object]:
    parsed = json.loads(stdout)
    if not isinstance(parsed, dict):
        raise SmokeFailure(f"{label} did not return a JSON object")
    return cast(dict[str, object], parsed)


def _json_list(stdout: str, label: str) -> list[object]:
    parsed = json.loads(stdout)
    if not isinstance(parsed, list):
        raise SmokeFailure(f"{label} did not return a JSON array")
    return cast(list[object], parsed)


def omp_inventory(sandbox: Sandbox) -> dict[str, object]:
    output = run_host(sandbox, "omp", ["plugin", "list", "--json"]).stdout
    return _json_object(output, "omp plugin list --json")


def omp_entries(sandbox: Sandbox, plugin_id: str = OMP_ID) -> list[dict[str, object]]:
    inventory = omp_inventory(sandbox)
    marketplaces = inventory.get("marketplace")
    if not isinstance(marketplaces, list):
        raise SmokeFailure("OMP native inventory has no marketplace array")
    matches: list[dict[str, object]] = []
    for raw_plugin in cast(list[object], marketplaces):
        if not isinstance(raw_plugin, dict):
            raise SmokeFailure("OMP native inventory contains a malformed plugin")
        plugin = cast(dict[str, object], raw_plugin)
        if plugin.get("id") != plugin_id:
            continue
        entries = plugin.get("entries")
        if not isinstance(entries, list):
            raise SmokeFailure(f"OMP registration {plugin_id} has no entries list")
        for raw_entry in cast(list[object], entries):
            if not isinstance(raw_entry, dict):
                raise SmokeFailure(
                    f"OMP registration {plugin_id} has a malformed entry"
                )
            matches.append(cast(dict[str, object], raw_entry))
    return matches


def omp_registration(sandbox: Sandbox, scope: str) -> dict[str, object] | None:
    entries = [entry for entry in omp_entries(sandbox) if entry.get("scope") == scope]
    if len(entries) > 1:
        raise SmokeFailure(f"OMP has duplicate {scope} registrations for {OMP_ID}")
    return entries[0] if entries else None


def omp_marketplace_source(
    sandbox: Sandbox, name: str = "slopgate-runtime"
) -> Path | None:
    output = run_host(sandbox, "omp", ["plugin", "marketplace", "list"]).stdout
    lines = output.splitlines()
    if "Configured Marketplaces:" not in lines:
        if "No marketplaces configured" in lines:
            return None
        raise SmokeFailure("Cannot parse OMP marketplace list")
    sources: list[str] = []
    start = lines.index("Configured Marketplaces:") + 1
    for line in lines[start:]:
        if not line.strip():
            continue
        columns = line.strip().split(maxsplit=1)
        if len(columns) != 2:
            raise SmokeFailure(f"Malformed OMP marketplace list entry: {line!r}")
        if columns[0] == name:
            sources.append(columns[1])
    if len(sources) > 1:
        raise SmokeFailure(f"OMP marketplace {name} is ambiguous")
    return Path(sources[0]).resolve() if sources else None


def pi_settings_path(sandbox: Sandbox, scope: str) -> Path:
    if scope == "user":
        return sandbox.pi_agent / "settings.json"
    if scope == "project":
        return sandbox.project / ".pi" / "settings.json"
    raise SmokeFailure(f"Unsupported Pi settings scope: {scope}")


def pi_settings(sandbox: Sandbox, scope: str) -> dict[str, object]:
    path = pi_settings_path(sandbox, scope)
    if not path.exists():
        return {}
    return _json_object(path.read_text(encoding="utf-8"), f"Pi {scope} settings")


def pi_package_source(
    sandbox: Sandbox, scope: str, target: Path | None = None
) -> dict[str, object] | None:
    settings = pi_settings(sandbox, scope)
    packages = settings.get("packages", [])
    if not isinstance(packages, list):
        raise SmokeFailure(f"Pi {scope} packages setting is not a list")
    settings_dir = pi_settings_path(sandbox, scope).parent
    expected = (target or package_root(sandbox, "pi")).resolve()
    matches: list[dict[str, object]] = []
    for raw_entry in cast(list[object], packages):
        if isinstance(raw_entry, str):
            source = raw_entry
            entry = cast(dict[str, object], {"source": source})
        elif isinstance(raw_entry, dict):
            entry = cast(dict[str, object], raw_entry)
            raw_source = entry.get("source")
            if not isinstance(raw_source, str):
                raise SmokeFailure(f"Pi {scope} package entry has no source")
            source = raw_source
        else:
            raise SmokeFailure(f"Pi {scope} package entry is malformed: {raw_entry!r}")
        source_path = Path(source).expanduser()
        if not source_path.is_absolute():
            source_path = settings_dir / source_path
        if source_path.resolve() == expected:
            matches.append(entry)
    if len(matches) > 1:
        raise SmokeFailure(f"Pi {scope} settings duplicate package source {expected}")
    return matches[0] if matches else None


def pi_list(sandbox: Sandbox) -> str:
    return run_host(sandbox, "pi", ["list"]).stdout


def claude_inventory(sandbox: Sandbox) -> list[object]:
    output = run_host(sandbox, "claude", ["plugin", "list", "--json"]).stdout
    return _json_list(output, "claude plugin list --json")


def claude_marketplaces(sandbox: Sandbox) -> list[object]:
    output = run_host(
        sandbox, "claude", ["plugin", "marketplace", "list", "--json"]
    ).stdout
    return _json_list(output, "claude plugin marketplace list --json")


def claude_plugins(
    sandbox: Sandbox, plugin_id: str = CLAUDE_ID
) -> list[dict[str, object]]:
    output = run_host(sandbox, "claude", ["plugin", "list", "--json"]).stdout
    entries = _json_list(output, "claude plugin list --json")
    matches: list[dict[str, object]] = []
    for raw_entry in entries:
        if not isinstance(raw_entry, dict):
            continue
        entry = cast(dict[str, object], raw_entry)
        if entry.get("id") == plugin_id:
            matches.append(entry)
    return matches


def claude_registration(sandbox: Sandbox, scope: str) -> dict[str, object] | None:
    matches = [
        entry for entry in claude_plugins(sandbox) if entry.get("scope") == scope
    ]
    if len(matches) > 1:
        raise SmokeFailure(
            f"Claude has duplicate {scope} registrations for {CLAUDE_ID}"
        )
    return matches[0] if matches else None


def claude_marketplace_source(
    sandbox: Sandbox, name: str = "slopgate-runtime"
) -> Path | None:
    output = run_host(
        sandbox, "claude", ["plugin", "marketplace", "list", "--json"]
    ).stdout
    matches: list[Path] = []
    for raw_entry in _json_list(output, "claude plugin marketplace list --json"):
        if not isinstance(raw_entry, dict):
            raise SmokeFailure("Claude marketplace inventory contains malformed entry")
        entry = cast(dict[str, object], raw_entry)
        if entry.get("name") == name:
            source = entry.get("path")
            if not isinstance(source, str):
                raise SmokeFailure(f"Claude marketplace {name} has no source path")
            matches.append(Path(source).resolve())
    if len(matches) > 1:
        raise SmokeFailure(f"Claude marketplace {name} is ambiguous")
    return matches[0] if matches else None


def native_inventory_snapshot(sandbox: Sandbox) -> str:
    return json.dumps(
        {
            "omp": omp_inventory(sandbox),
            "omp_marketplaces": run_host(
                sandbox, "omp", ["plugin", "marketplace", "list"]
            ).stdout,
            "pi": {scope: pi_settings(sandbox, scope) for scope in SCOPES},
            "pi_list": pi_list(sandbox),
            "claude_plugins": claude_inventory(sandbox),
            "claude_marketplaces": claude_marketplaces(sandbox),
        },
        sort_keys=True,
    )


def assert_initial_inventory_clear(sandbox: Sandbox) -> None:
    if omp_entries(sandbox):
        raise SmokeFailure(
            "OMP inventory unexpectedly contains the Slopgate plugin before install"
        )
    if claude_plugins(sandbox):
        raise SmokeFailure(
            "Claude inventory unexpectedly contains the Slopgate plugin before install"
        )
    for scope in SCOPES:
        if pi_package_source(sandbox, scope) is not None:
            raise SmokeFailure(
                f"Pi {scope} inventory unexpectedly contains Slopgate before install"
            )
