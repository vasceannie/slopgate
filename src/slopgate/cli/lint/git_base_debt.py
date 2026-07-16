"""Git-base debt scanning and cache support for lint checks."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from slopgate._types import object_dict, object_list
from slopgate.cli.lint.report import LintFiles
from slopgate.lint._baseline import Violation
from slopgate.util.atomic_files import write_text_atomic_locked

GIT_BASE_DEBT_CACHE_VERSION = 1
GIT_BASE_DEBT_CACHE_ROOT = ".slopgate/cache/git-base-debt"
GIT_BASE_DEBT_DETECTOR_PATTERNS = (
    "src/slopgate/lint/**/*.py",
    "src/slopgate/rules/python_ast/**/*.py",
)
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

    @property
    def inherited_count(self) -> int:
        return sum((len(ids) for ids in self.rules.values()))

    @property
    def note(self) -> str:
        return (
            f"{self.ref_name} @ {self.base_sha[:12]} "
            f"({self.inherited_count} inherited id(s))"
        )


@dataclass(frozen=True, slots=True)
class _GitBaseDebtCacheKey:
    base_sha: str
    detector_signature: str


def _run_git(root: Path, *args: str) -> str | None:
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), *args],
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
        ["git", "-C", str(root), "archive", "--format=tar", base_sha],
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
    digest = hashlib.sha256()
    for pattern in GIT_BASE_DEBT_DETECTOR_PATTERNS:
        for path in sorted(project_root.glob(pattern)):
            if not path.is_file():
                continue
            stat = path.stat()
            relative = path.relative_to(project_root)
            digest.update(str(relative).encode("utf-8"))
            digest.update(b"\0")
            digest.update(str(stat.st_mtime_ns).encode("ascii"))
            digest.update(b"\0")
            digest.update(str(stat.st_size).encode("ascii"))
            digest.update(b"\0")
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


def scan_git_base_debt(
    project_root: Path, *, configured_lint_files: ConfiguredLintFiles
) -> GitBaseDebt | None:
    from slopgate.lint._collectors import run_all_collectors

    discovered = _discover_git_base(project_root)
    if discovered is None:
        return None
    ref_name, base_sha = discovered
    cache_key = _GitBaseDebtCacheKey(
        base_sha=base_sha,
        detector_signature=_git_base_debt_detector_signature(project_root),
    )
    cache_path = _git_base_debt_cache_path(project_root, cache_key)
    cached = _read_git_base_debt_cache(cache_path, ref_name, cache_key)
    if cached is not None:
        return cached
    with tempfile.TemporaryDirectory(prefix="slopgate-git-base-") as tmpdir:
        archive_root = Path(tmpdir)
        if not _extract_git_archive(project_root, base_sha, archive_root):
            return None
        files = configured_lint_files(archive_root, force_all_scope=True)
        collectors = run_all_collectors(files.src_files, files.test_files)
    rules = _collector_ids_by_rule(collectors)
    if not rules:
        return None
    debt = GitBaseDebt(ref_name=ref_name, base_sha=base_sha, rules=rules)
    _write_git_base_debt_cache(cache_path, cache_key, debt)
    return debt


__all__ = ["ConfiguredLintFiles", "GitBaseDebt", "scan_git_base_debt"]
