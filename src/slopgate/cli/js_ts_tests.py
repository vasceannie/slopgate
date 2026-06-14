"""JS/TS changed-test selection helpers for the ``slopgate test`` workflow."""

from __future__ import annotations

import subprocess
from collections.abc import Iterable, Sequence
from pathlib import Path

from slopgate.cli.io import CliInputError
from slopgate.constants import LANGUAGE_BY_SUFFIX

JS_TS_LANGUAGE = "js_ts"
JS_TS_TEST_MARKERS = (".test", ".spec")
SKIPPED_DISCOVERY_DIRS = frozenset(
    {".git", ".venv", "node_modules", "dist", "build", "coverage", "__pycache__"}
)


def is_js_ts_path(path: str) -> bool:
    return LANGUAGE_BY_SUFFIX.get(Path(path).suffix.lower()) == JS_TS_LANGUAGE


def is_js_ts_test_path(path: str) -> bool:
    if not is_js_ts_path(path):
        return False
    lowered_name = Path(path).name.lower()
    return any(marker in lowered_name for marker in JS_TS_TEST_MARKERS)


def select_js_ts_tests(changed_files: Iterable[str], *, root: Path) -> tuple[str, ...]:
    changed_js_ts = tuple(path for path in changed_files if is_js_ts_path(path))
    if not changed_js_ts:
        return ()
    changed_test_paths = {path for path in changed_js_ts if is_js_ts_test_path(path)}
    changed_source_keys = {
        _js_ts_match_key(path) for path in changed_js_ts if not is_js_ts_test_path(path)
    }
    selected = set(changed_test_paths)
    for test_path in _discover_js_ts_tests(root):
        if _js_ts_match_key(test_path) in changed_source_keys:
            selected.add(test_path)
    return tuple(sorted(selected))


def changed_files_in_submodules(root: Path, since_ref: str) -> tuple[str, ...]:
    submodule_roots = _git_submodule_roots(root)
    changed_files: list[str] = []
    for submodule_root in submodule_roots:
        diff_ref = since_ref if since_ref == "HEAD" else f"{since_ref}..."
        changed_files.extend(
            _prefixed_submodule_changes(root, submodule_root, diff_ref)
        )
    return tuple(sorted(changed_files))


def execute_default_js_ts_tests(
    selected_tests: Sequence[str], *, runner_args: Sequence[str] = (), root: Path
) -> int:
    grouped_tests = _group_tests_by_package_root(selected_tests, root=root)
    for package_root, tests in grouped_tests:
        command = ["npm", "test", "--", *tests, *runner_args]
        try:
            completed = subprocess.run(command, cwd=package_root, check=False)
        except FileNotFoundError as exc:
            raise CliInputError(
                "npm executable was not found for JS/TS changed-test selection"
            ) from exc
        if completed.returncode != 0:
            return completed.returncode
    return 0


def _discover_js_ts_tests(root: Path) -> tuple[str, ...]:
    tests: set[str] = set()
    for path in root.rglob("*"):
        if not path.is_file() or any(
            part in SKIPPED_DISCOVERY_DIRS for part in path.relative_to(root).parts
        ):
            continue
        relative = path.relative_to(root).as_posix()
        if is_js_ts_test_path(relative):
            tests.add(relative)
    return tuple(sorted(tests))


def _git_submodule_roots(root: Path) -> tuple[Path, ...]:
    completed = subprocess.run(
        ["git", "submodule", "status", "--recursive"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return ()
    roots: list[Path] = []
    for line in completed.stdout.splitlines():
        parts = line.strip().split()
        if len(parts) >= 2:
            roots.append(root / parts[1])
    return tuple(roots)


def _prefixed_submodule_changes(
    root: Path, submodule_root: Path, diff_ref: str
) -> tuple[str, ...]:
    gitlink_ref = _parent_recorded_submodule_ref(root, submodule_root)
    current_ref = _submodule_current_ref(submodule_root)
    if gitlink_ref and current_ref and gitlink_ref != current_ref:
        diff_ref = f"{gitlink_ref}..HEAD"
    completed = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=AMR", diff_ref],
        cwd=submodule_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return ()
    prefix = submodule_root.relative_to(root).as_posix()
    return tuple(
        f"{prefix}/{path.strip()}"
        for path in completed.stdout.splitlines()
        if path.strip()
    )


def _parent_recorded_submodule_ref(root: Path, submodule_root: Path) -> str | None:
    relative_path = submodule_root.relative_to(root).as_posix()
    completed = subprocess.run(
        ["git", "ls-tree", "HEAD", relative_path],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return None
    parts = completed.stdout.strip().split()
    if len(parts) < 3:
        return None
    return parts[2]


def _submodule_current_ref(submodule_root: Path) -> str | None:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=submodule_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return None
    return completed.stdout.strip() or None


def _group_tests_by_package_root(
    selected_tests: Sequence[str], *, root: Path
) -> tuple[tuple[Path, tuple[str, ...]], ...]:
    grouped: dict[Path, list[str]] = {}
    for test_path in selected_tests:
        package_root = _nearest_package_root(root / test_path, root=root)
        if package_root is None:
            raise CliInputError(f"JS/TS test {test_path!r} is not under a package.json")
        grouped.setdefault(package_root, []).append(
            (root / test_path).relative_to(package_root).as_posix()
        )
    return tuple(
        (package_root, tuple(tests)) for package_root, tests in grouped.items()
    )


def _nearest_package_root(test_path: Path, *, root: Path) -> Path | None:
    current = test_path.parent
    while current != current.parent:
        if (current / "package.json").is_file():
            return current
        if current == root:
            return None
        current = current.parent
    return None


def _js_ts_match_key(path: str) -> str:
    raw_path = Path(path)
    suffix = raw_path.suffix
    basename = raw_path.name[: -len(suffix)] if suffix else raw_path.name
    for marker in JS_TS_TEST_MARKERS:
        marker_segment = f"{marker}."
        marker_index = basename.find(marker_segment)
        if marker_index >= 0:
            basename = basename[:marker_index]
            break
        if basename.endswith(marker):
            basename = basename[: -len(marker)]
            break
    return (raw_path.parent / basename).as_posix().lower()
