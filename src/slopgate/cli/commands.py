from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import cast

from slopgate._types import ObjectDict, ObjectMapping, object_dict
from slopgate.cli._claude_retry import claude_team_event_feedback
from slopgate.cli._config_commands import (
    cmd_config_init as cmd_config_init,
    cmd_config_path as cmd_config_path,
    cmd_config_show as cmd_config_show,
)

VALID_PLATFORMS = ("claude", "codex", "opencode", "cursor")
INSTALL_TARGETS = (*VALID_PLATFORMS, "all")
PLATFORM_HELP = (
    f"Target platform. Choices: {', '.join(VALID_PLATFORMS)} (default: claude)"
)


class CliInputError(ValueError):
    """Clean user-facing CLI input error."""


def _stdin_is_interactive() -> bool:
    isatty = getattr(sys.stdin, "isatty", None)
    return bool(isatty()) if callable(isatty) else False


def _load_stdin_json() -> ObjectDict:
    if _stdin_is_interactive():
        raise CliInputError(
            "No JSON payload on stdin. 'slopgate handle' is a hook entrypoint; "
            "pipe a harness payload, e.g. echo '{}' | slopgate handle --platform cursor"
        )
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        parsed = cast(object, json.loads(raw))
    except json.JSONDecodeError as exc:
        raise CliInputError(f"Invalid JSON on stdin: {exc.msg}") from None
    return object_dict(parsed)


def _report_cli_input_error(exc: CliInputError) -> int:
    print(str(exc), file=sys.stderr)
    return 1


def _string_arg(args: argparse.Namespace, name: str, default: str = "") -> str:
    value = getattr(args, name, default)
    return value if isinstance(value, str) else default


def _bool_arg(args: argparse.Namespace, name: str, default: bool = False) -> bool:
    value = getattr(args, name, default)
    return value if isinstance(value, bool) else default


def _int_arg(args: argparse.Namespace, name: str) -> int | None:
    value = getattr(args, name, None)
    return value if isinstance(value, int) else None


def _project_root_arg(args: argparse.Namespace) -> Path | None:
    value = _string_arg(args, "project_root")
    if not value.strip():
        return None
    return Path(value).expanduser().resolve()


def _dump_output(output: ObjectMapping | None) -> int:
    if output:
        _ = sys.stdout.write(json.dumps(output, separators=(",", ":")) + "\n")
    return 0


def cmd_handle(args: argparse.Namespace) -> int:
    from slopgate.engine import evaluate_payload

    try:
        payload = _load_stdin_json()
    except CliInputError as exc:
        return _report_cli_input_error(exc)
    if not payload:
        return 0
    platform = _string_arg(args, "platform", "claude")
    result = evaluate_payload(payload, platform=platform)
    if platform.strip().lower() == "claude":
        feedback = claude_team_event_feedback(result)
        if feedback:
            _ = sys.stderr.write(feedback.rstrip() + "\n")
            return 2
    return _dump_output(result.output)


def cmd_handle_async(_args: argparse.Namespace) -> int:
    from slopgate.async_jobs import run_async_jobs

    try:
        payload = _load_stdin_json()
    except CliInputError as exc:
        return _report_cli_input_error(exc)
    summary, _errors = run_async_jobs(payload)
    if summary:
        _ = sys.stdout.write(summary + "\n")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    from slopgate.config import (
        is_path_skipped,
        is_repo_disabled,
        load_config,
        resolve_git_root,
        resolve_main_git_repo_root,
        resolve_repo_root,
    )

    target = Path(_string_arg(args, "path", ".")).resolve()
    config = load_config(
        repo_root=target,
        ensure_enrollment=False,
        ensure_trace=False,
    )
    resolved_repo_root = resolve_repo_root(target)
    git_root = resolve_git_root(target)
    main_repo_root = resolve_main_git_repo_root(target)
    disabled = resolved_repo_root is not None and is_repo_disabled(resolved_repo_root)
    skipped = is_path_skipped(resolved_repo_root or target, config.skip_paths)
    if resolved_repo_root is None:
        status = "NOT_ENROLLED"
    elif skipped:
        status = "SKIPPED"
    elif disabled:
        status = "RELAXED"
    else:
        status = "ENROLLED"
    print(
        json.dumps(
            {
                "path": str(target),
                "status": status,
                "resolved_repo_root": (
                    str(resolved_repo_root) if resolved_repo_root is not None else None
                ),
                "git_root": str(git_root) if git_root is not None else None,
                "main_repo_root": (
                    str(main_repo_root) if main_repo_root is not None else None
                ),
                "repo_disabled": disabled,
                "path_skipped": skipped,
                "skip_paths": config.skip_paths,
            },
            indent=2,
        )
    )
    return 0


def cmd_enroll(args: argparse.Namespace) -> int:
    from slopgate.config import enroll_repo, list_git_worktrees

    target = Path(_string_arg(args, "path", ".")).resolve()
    include_worktrees = not _bool_arg(args, "no_worktrees")
    repo_root, written_roots = enroll_repo(
        target,
        include_worktrees=include_worktrees,
    )
    worktrees = list_git_worktrees(repo_root) if include_worktrees else []
    print(
        json.dumps(
            {
                "path": str(target),
                "status": "ENROLLED",
                "repo_root": str(repo_root),
                "include_worktrees": include_worktrees,
                "worktree_count": max(0, len(worktrees) - 1) if worktrees else 0,
                "written_roots": [str(path) for path in written_roots],
            },
            indent=2,
        )
    )
    return 0


def cmd_replay(args: argparse.Namespace) -> int:
    from slopgate.engine import evaluate_payload

    payload_path = Path(_string_arg(args, "payload")).resolve()
    parsed = cast(object, json.loads(payload_path.read_text(encoding="utf-8")))
    payload = object_dict(parsed)
    platform = _string_arg(args, "platform", "claude")
    result = evaluate_payload(payload, platform=platform)
    if _bool_arg(args, "pretty"):
        print(json.dumps(result.output, indent=2))
    else:
        print(json.dumps(result.output, separators=(",", ":")))
    return 0


def cmd_install(args: argparse.Namespace) -> int:
    from slopgate.installer import SuiteInstallOptions, install_platform, install_suite
    from slopgate.installer._suite import DEFAULT_UPDATE_INTERVAL_MINUTES, install_autoupdate

    platform = _string_arg(args, "platform")
    if platform == "all":
        return install_suite(
            SuiteInstallOptions(
                dry_run=_bool_arg(args, "dry_run"),
                include_missing=_bool_arg(args, "include_missing"),
                with_autoupdate=_bool_arg(args, "with_autoupdate"),
                source=_string_arg(args, "source"),
                interval_minutes=(
                    _int_arg(args, "interval_minutes") or DEFAULT_UPDATE_INTERVAL_MINUTES
                ),
                install_scope=_string_arg(args, "install_scope", "user"),
                project_root=_project_root_arg(args),
            )
        )

    status = install_platform(
        platform,
        dry_run=_bool_arg(args, "dry_run"),
        install_scope=_string_arg(args, "install_scope", "user"),
        project_root=_project_root_arg(args),
    )
    if not _bool_arg(args, "with_autoupdate") or status != 0:
        return status
    return install_autoupdate(
        dry_run=_bool_arg(args, "dry_run"),
        source=_string_arg(args, "source"),
        include_missing=_bool_arg(args, "include_missing"),
        interval_minutes=(
            _int_arg(args, "interval_minutes") or DEFAULT_UPDATE_INTERVAL_MINUTES
        ),
    ) or status


def cmd_uninstall(args: argparse.Namespace) -> int:
    from slopgate.installer import (
        SuiteUninstallOptions,
        uninstall_autoupdate,
        uninstall_platform,
        uninstall_suite,
    )

    platform = _string_arg(args, "platform")
    if platform == "all":
        return uninstall_suite(
            SuiteUninstallOptions(
                dry_run=_bool_arg(args, "dry_run"),
                with_autoupdate=_bool_arg(args, "with_autoupdate"),
                install_scope=_string_arg(args, "install_scope", "user"),
                project_root=_project_root_arg(args),
            )
        )

    status = uninstall_platform(
        platform,
        dry_run=_bool_arg(args, "dry_run"),
        install_scope=_string_arg(args, "install_scope", "user"),
        project_root=_project_root_arg(args),
    )
    if not _bool_arg(args, "with_autoupdate"):
        return status
    return uninstall_autoupdate(dry_run=_bool_arg(args, "dry_run")) or status


def cmd_install_suite(args: argparse.Namespace) -> int:
    from slopgate.installer import SuiteInstallOptions, install_suite
    from slopgate.installer._suite import DEFAULT_UPDATE_INTERVAL_MINUTES

    return install_suite(
        SuiteInstallOptions(
            dry_run=_bool_arg(args, "dry_run"),
            include_missing=_bool_arg(args, "include_missing"),
            with_autoupdate=_bool_arg(args, "with_autoupdate"),
            source=_string_arg(args, "source"),
            interval_minutes=(
                _int_arg(args, "interval_minutes") or DEFAULT_UPDATE_INTERVAL_MINUTES
            ),
            install_scope=_string_arg(args, "install_scope", "user"),
            project_root=_project_root_arg(args),
        )
    )


def cmd_update_suite(args: argparse.Namespace) -> int:
    from slopgate.installer import SuiteUpdateOptions, update_suite

    return update_suite(
        SuiteUpdateOptions(
            dry_run=_bool_arg(args, "dry_run"),
            source=_string_arg(args, "source"),
            include_missing=_bool_arg(args, "include_missing"),
            install_scope=_string_arg(args, "install_scope", "user"),
            project_root=_project_root_arg(args),
        )
    )


def cmd_stats(args: argparse.Namespace) -> int:
    from slopgate.stats import run_stats

    return run_stats(
        log_path=_string_arg(args, "log") or None,
        days=_int_arg(args, "days"),
        as_json=_bool_arg(args, "json"),
    )


def cmd_test(args: argparse.Namespace) -> int:
    from slopgate.cli._self_test import cmd_test as _cmd_test

    return _cmd_test(args)


def cmd_version(_args: argparse.Namespace) -> int:
    from slopgate import __version__

    print(f"slopgate {__version__}")
    return 0
