from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from .native import OMP_ID, omp_entries, omp_registration, package_root
from .sandbox import Sandbox, SmokeFailure, run_command


@dataclass(frozen=True, slots=True)
class RuntimeEvidence:
    host: str
    payload: dict[str, object]


@dataclass(frozen=True, slots=True)
class BunScript:
    workspace: Path
    host: str
    script: str
    args: list[str]


def _json_object(stdout: str, label: str) -> dict[str, object]:
    parsed = json.loads(stdout)
    if not isinstance(parsed, dict):
        raise SmokeFailure(f"{label} did not return a JSON object")
    return cast(dict[str, object], parsed)


def _bun_script(sandbox: Sandbox, request: BunScript) -> str:
    command = ["bun", "run", request.script, *request.args]
    return run_command(
        command,
        request.workspace,
        sandbox.environment(request.host),
        f"Running registered {request.host} runtime script {request.script}",
    ).stdout


def pi_discovered_paths(sandbox: Sandbox) -> list[Path]:
    workspace = sandbox.repo / "tests" / "runtime" / "pi"
    output = _bun_script(
        sandbox,
        BunScript(
            workspace,
            "pi",
            "scripts/discover-registered.ts",
            [str(sandbox.project), str(sandbox.pi_agent)],
        ),
    )
    result = _json_object(output, "Pi native discovery")
    errors = result.get("errors")
    if not isinstance(errors, list) or errors:
        raise SmokeFailure(f"Pi native discovery reported errors: {errors!r}")
    raw_extensions = result.get("extensions")
    if not isinstance(raw_extensions, list):
        raise SmokeFailure("Pi native discovery returned no extension list")
    paths: list[Path] = []
    for raw_path in cast(list[object], raw_extensions):
        if not isinstance(raw_path, str) or not Path(raw_path).is_absolute():
            raise SmokeFailure(
                f"Pi native discovery returned an invalid path: {raw_path!r}"
            )
        paths.append(Path(raw_path).resolve())
    return paths


def _registered_omp_index(sandbox: Sandbox, registration: dict[str, object]) -> Path:
    install_path = registration.get("installPath")
    if not isinstance(install_path, str):
        raise SmokeFailure("OMP native registration has no installPath")
    index_path = (Path(install_path) / "index.ts").resolve()
    if sandbox.root.resolve() not in index_path.parents or not index_path.is_file():
        raise SmokeFailure(
            f"OMP registered extension path is not sandboxed: {index_path}"
        )
    return index_path


def assert_omp_inventory(sandbox: Sandbox, active_scope: str | None) -> Path | None:
    if active_scope is None:
        enabled = [
            entry
            for entry in omp_entries(sandbox, OMP_ID)
            if entry.get("enabled") is not False
        ]
        if enabled:
            raise SmokeFailure(
                f"OMP inventory still exposes enabled Slopgate entries: {enabled}"
            )
        return None
    registration = omp_registration(sandbox, active_scope)
    if registration is None or registration.get("enabled") is False:
        raise SmokeFailure(
            f"OMP native inventory has no enabled {active_scope} registration"
        )
    return _registered_omp_index(sandbox, registration)


def assert_pi_discovery(sandbox: Sandbox, expected_active: bool) -> Path | None:
    package_index = (package_root(sandbox, "pi") / "index.ts").resolve()
    discovered = pi_discovered_paths(sandbox)
    active = [path for path in discovered if path == package_index]
    if expected_active and len(active) != 1:
        raise SmokeFailure(
            f"Pi native discovery did not load exactly one registered package: {discovered}"
        )
    if not expected_active and active:
        raise SmokeFailure(f"Pi native discovery still loads Slopgate: {active}")
    return package_index if active else None


def run_omp_extension(sandbox: Sandbox, index_path: Path) -> RuntimeEvidence:
    workspace = sandbox.repo / "tests" / "runtime" / "omp"
    record_path = sandbox.root / "records" / "omp.jsonl"
    output = _bun_script(
        sandbox,
        BunScript(
            workspace,
            "omp",
            "scripts/load-installed.ts",
            [str(index_path), str(sandbox.project), str(record_path)],
        ),
    )
    return RuntimeEvidence("omp", _json_object(output, "OMP ExtensionRunner contract"))


def run_pi_extension(sandbox: Sandbox, index_path: Path) -> RuntimeEvidence:
    workspace = sandbox.repo / "tests" / "runtime" / "pi"
    record_path = sandbox.root / "records" / "pi.jsonl"
    output = _bun_script(
        sandbox,
        BunScript(
            workspace,
            "pi",
            "scripts/load-installed.ts",
            [
                str(index_path),
                str(sandbox.project),
                str(sandbox.pi_agent),
                str(record_path),
            ],
        ),
    )
    return RuntimeEvidence("pi", _json_object(output, "Pi ExtensionRunner contract"))


def package_guard_gaps(evidence: RuntimeEvidence) -> list[str]:
    raw_writes = evidence.payload.get("packageWrites")
    if not isinstance(raw_writes, dict):
        raise SmokeFailure(
            f"{evidence.host} runtime harness omitted package-write results"
        )
    writes = cast(dict[str, object], raw_writes)
    gaps: list[str] = []
    for filename in ("index", "manifest"):
        raw_result = writes.get(filename)
        if not isinstance(raw_result, dict):
            raise SmokeFailure(
                f"{evidence.host} harness omitted package {filename} result"
            )
        result = cast(dict[str, object], raw_result)
        if result.get("blocked") is not True:
            gaps.append(
                f"{evidence.host} relocated package guard: write to {filename} was allowed; "
                "the loaded native package directory is not protected by the bridge guard"
            )
        elif not isinstance(result.get("reason"), str) or not result.get("reason"):
            gaps.append(
                f"{evidence.host} package {filename} was blocked without an infrastructure reason"
            )
    return gaps


def assert_runtime_contract(evidence: RuntimeEvidence) -> list[str]:
    payload = evidence.payload
    blocked = payload.get("blocked")
    if evidence.host == "pi":
        blocked = {"write": payload.get("blockedWrite")}
    if not isinstance(blocked, dict):
        raise SmokeFailure(
            f"{evidence.host} runtime harness omitted protected-write results"
        )
    blocked_data = cast(dict[str, object], blocked)
    targets = (
        ("write", "hashline", "applyPatch") if evidence.host == "omp" else ("write",)
    )
    for target in targets:
        reason = blocked_data.get(target)
        if not isinstance(reason, str) or not reason:
            raise SmokeFailure(
                f"{evidence.host} did not block the protected {target} target"
            )
    if "slopgate.toml" not in str(blocked_data.get("write")):
        raise SmokeFailure(
            f"{evidence.host} protected write reason does not identify slopgate.toml"
        )
    if evidence.host == "omp":
        session = payload.get("session")
        if not isinstance(session, str) or not session:
            raise SmokeFailure(
                "OMP runtime harness omitted the native session identity"
            )
    return package_guard_gaps(evidence)
