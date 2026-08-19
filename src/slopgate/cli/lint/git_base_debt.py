"""Git-base debt scanning and cache support for lint checks."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Protocol

from slopgate._types import object_dict, object_list
from slopgate.cli.lint.report import LintFiles
from slopgate.config._repo import GIT_BIN
from slopgate.lint._baseline import Violation
from slopgate.lint.project_index.cache_trust import cache_path_is_trusted
from slopgate.util.atomic_files import write_text_atomic_locked

GIT_BASE_DEBT_CACHE_VERSION = 1
GIT_BASE_DEBT_CACHE_ROOT = ".slopgate/cache/git-base-debt"
GIT_COMMAND_TIMEOUT_SECONDS = 10
GIT_ARCHIVE_TIMEOUT_SECONDS = 30


class ConfiguredLintFiles(Protocol):
    def __call__(self, root: Path, *, force_all_scope: bool) -> LintFiles: ...


class _GitArchiveProcess(Protocol):
    def wait(self, timeout: int) -> int: ...

    def kill(self) -> None: ...


@dataclass(frozen=True, slots=True)
class GitBaseDebt:
    ref_name: str
    base_sha: str
    rules: dict[str, set[str]]
    cache_hit: bool = False
    scan_seconds: float = 0.0

    @property
    def inherited_count(self) -> int:
        return sum((len(ids) for ids in self.rules.values()))

    @property
    def note(self) -> str:
        return (
            f"{self.ref_name} @ {self.base_sha[:12]} "
            f"({self.inherited_count} inherited id(s))"
        )

    @property
    def profile_line(self) -> str:
        from slopgate.lint._helpers.profile import format_profile_seconds

        if self.cache_hit:
            return f"HIT sha={self.base_sha}"
        return f"MISS scan={format_profile_seconds(self.scan_seconds)}"


@dataclass(frozen=True, slots=True)
class _GitBaseDebtCacheKey:
    base_sha: str
    detector_signature: str


def _run_git(root: Path, *args: str) -> str | None:
    try:
        completed = subprocess.run(
            [GIT_BIN, "-C", str(root), *args],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=GIT_COMMAND_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    return _stripped_output(completed.stdout)


def _stripped_output(output: str) -> str | None:
    stripped = output.strip()
    if not stripped:
        return None
    return stripped


def _candidate_base_refs(root: Path) -> list[str]:
    candidates: list[str] = []
    explicit = os.environ.get("SLOPGATE_LINT_BASE_REF")
    if explicit:
        candidates.append(explicit)
    upstream = _run_git(
        root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"
    )
    if upstream:
        candidates.append(upstream)
    candidates.extend(["origin/main", "origin/master", "main", "master"])
    unique: list[str] = []
    for candidate in candidates:
        if candidate not in unique:
            unique.append(candidate)
    return unique


def _is_current_branch_ref(ref: str, current_branch: str | None) -> bool:
    if current_branch is None or current_branch == "HEAD":
        return False
    return ref in {current_branch, f"refs/heads/{current_branch}"}


def _discover_git_base(root: Path) -> tuple[str, str] | None:
    head = _run_git(root, "rev-parse", "--verify", "HEAD^{commit}")
    if head is None:
        return None
    current_branch = _run_git(root, "rev-parse", "--abbrev-ref", "HEAD")
    for ref in _candidate_base_refs(root):
        if _run_git(root, "rev-parse", "--verify", f"{ref}^{{commit}}") is None:
            continue
        base_sha = _run_git(root, "merge-base", "HEAD", ref)
        if base_sha and (
            base_sha != head or not _is_current_branch_ref(ref, current_branch)
        ):
            return (ref, base_sha)
    return None


def _extract_git_archive(root: Path, base_sha: str, destination: Path) -> bool:
    git_process = subprocess.Popen(
        [GIT_BIN, "-C", str(root), "archive", "--format=tar", base_sha],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    if git_process.stdout is None:
        _finish_git_archive_process(git_process)
        return False
    try:
        extract = subprocess.run(
            ["tar", "-xf", "-", "-C", str(destination)],
            check=False,
            stdin=git_process.stdout,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=GIT_ARCHIVE_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        git_process.kill()
        _finish_git_archive_process(git_process)
        return False
    finally:
        git_process.stdout.close()
    return _finish_git_archive_process(git_process) and extract.returncode == 0


def _finish_git_archive_process(git_process: _GitArchiveProcess) -> bool:
    try:
        return git_process.wait(timeout=GIT_COMMAND_TIMEOUT_SECONDS) == 0
    except subprocess.TimeoutExpired:
        git_process.kill()
    try:
        return git_process.wait(timeout=GIT_COMMAND_TIMEOUT_SECONDS) == 0
    except subprocess.TimeoutExpired:
        return False


def _collector_ids_by_rule(
    collectors: list[tuple[str, list[Violation]]],
) -> dict[str, set[str]]:
    return {
        rule: {violation.stable_id for violation in violations}
        for rule, violations in collectors
        if violations
    }


def _git_base_debt_detector_signature(project_root: Path) -> str:
    from slopgate.lint.project_index.fingerprint import engine_fingerprint

    digest = hashlib.sha256()
    digest.update(str(GIT_BASE_DEBT_CACHE_VERSION).encode("ascii"))
    digest.update(b"\0")
    digest.update(engine_fingerprint(project_root).encode("ascii"))
    return digest.hexdigest()


def _git_base_debt_cache_path(
    project_root: Path, cache_key: _GitBaseDebtCacheKey
) -> Path:
    key_digest = hashlib.sha256(
        f"{cache_key.base_sha}\0{cache_key.detector_signature}".encode("utf-8")
    ).hexdigest()
    return project_root / GIT_BASE_DEBT_CACHE_ROOT / f"{key_digest}.json"


def _git_base_debt_from_cache_payload(
    payload: Mapping[str, object], ref_name: str, cache_key: _GitBaseDebtCacheKey
) -> GitBaseDebt | None:
    if payload.get("version") != GIT_BASE_DEBT_CACHE_VERSION:
        return None
    if payload.get("base_sha") != cache_key.base_sha:
        return None
    if payload.get("detector_signature") != cache_key.detector_signature:
        return None
    rules_payload = object_dict(payload.get("rules"))
    rules: dict[str, set[str]] = {}
    for rule_name, ids_payload in rules_payload.items():
        stable_ids = {
            item for item in object_list(ids_payload) if isinstance(item, str)
        }
        if stable_ids:
            rules[rule_name] = stable_ids
    if not rules:
        return None
    return GitBaseDebt(ref_name=ref_name, base_sha=cache_key.base_sha, rules=rules)


def _read_git_base_debt_cache(
    cache_path: Path, ref_name: str, cache_key: _GitBaseDebtCacheKey
) -> GitBaseDebt | None:
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return _git_base_debt_from_cache_payload(object_dict(payload), ref_name, cache_key)


def _write_git_base_debt_cache(
    cache_path: Path, cache_key: _GitBaseDebtCacheKey, debt: GitBaseDebt
) -> None:
    payload = {
        "version": GIT_BASE_DEBT_CACHE_VERSION,
        "base_sha": cache_key.base_sha,
        "detector_signature": cache_key.detector_signature,
        "rules": {
            rule: sorted(stable_ids) for rule, stable_ids in sorted(debt.rules.items())
        },
    }
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        write_text_atomic_locked(
            cache_path,
            json.dumps(payload, sort_keys=True),
            prefix="git-base-debt-",
            suffix=".json",
        )
    except OSError:
        return


def _git_worktree_clean(root: Path) -> bool:
    try:
        completed = subprocess.run(
            [GIT_BIN, "-C", str(root), "status", "--porcelain"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=GIT_COMMAND_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0 and not completed.stdout.strip()


def _attach_profile(debt: GitBaseDebt) -> None:
    from slopgate.lint._helpers.profile import attach_git_base_profile_line

    attach_git_base_profile_line(debt.profile_line)


def scan_git_base_debt(
    project_root: Path, *, configured_lint_files: ConfiguredLintFiles
) -> GitBaseDebt | None:
    discovered = _discover_git_base(project_root)
    if discovered is None:
        return None
    ref_name, base_sha = discovered
    cache_key = _GitBaseDebtCacheKey(
        base_sha=base_sha,
        detector_signature=_git_base_debt_detector_signature(project_root),
    )
    cache_path = _git_base_debt_cache_path(project_root, cache_key)
    cache_trusted = cache_path_is_trusted(project_root, cache_path)
    cached = (
        _read_git_base_debt_cache(cache_path, ref_name, cache_key)
        if cache_trusted
        else None
    )
    if cached is not None:
        hit = replace(cached, cache_hit=True)
        _attach_profile(hit)
        return hit
    from time import perf_counter

    started = perf_counter()
    reuse = _run_git(project_root, "rev-parse", "HEAD") == base_sha and _git_worktree_clean(
        project_root
    )
    with tempfile.TemporaryDirectory(prefix="slopgate-git-base-") as tmpdir:
        scan_root = project_root if reuse else Path(tmpdir)
        if not reuse and not _extract_git_archive(project_root, base_sha, scan_root):
            return None
        files = configured_lint_files(scan_root, force_all_scope=True)
        from slopgate.lint._collectors import CollectorRunOptions, run_all_collectors

        collectors = run_all_collectors(
            files.src_files,
            files.test_files,
            CollectorRunOptions(persist_index=False, use_index=reuse),
        )
    scan_seconds = perf_counter() - started
    rules = _collector_ids_by_rule(collectors)
    if not rules:
        return None
    debt = GitBaseDebt(ref_name=ref_name, base_sha=base_sha, rules=rules, scan_seconds=scan_seconds)
    if cache_trusted:
        _write_git_base_debt_cache(cache_path, cache_key, debt)
    _attach_profile(debt)
    return debt


__all__ = ["ConfiguredLintFiles", "GitBaseDebt", "scan_git_base_debt"]
