from __future__ import annotations
import argparse
import json
from pathlib import Path
from typing import cast
from slopgate._types import object_dict
from slopgate.constants import UNKNOWN_VALUE
from slopgate.cli.platforms import (
    INSTALL_TARGETS,
    PLATFORM_HELP,
    RUNTIME_PLATFORMS,
    VALID_PLATFORMS,
)
from slopgate.cli._config_commands import (
    cmd_config_init,
    cmd_config_path,
    cmd_config_show,
)
from slopgate.cli.hook_runtime import cmd_daemon, cmd_handle, cmd_handle_async
from slopgate.cli.io import CliInputError, string_arg

__all__ = [
    "VALID_PLATFORMS",
    "RUNTIME_PLATFORMS",
    "INSTALL_TARGETS",
    "PLATFORM_HELP",
    "CliInputError",
    "cmd_config_init",
    "cmd_config_path",
    "cmd_config_show",
    "cmd_daemon",
    "cmd_handle",
    "cmd_handle_async",
]


def _bool_arg(args: argparse.Namespace, name: str, default: bool = False) -> bool:
    value = getattr(args, name, default)
    return value if isinstance(value, bool) else default


def _int_arg(args: argparse.Namespace, name: str) -> int | None:
    value = getattr(args, name, None)
    return value if isinstance(value, int) else None


def _project_root_arg(args: argparse.Namespace) -> Path | None:
    value = string_arg(args, "project_root")
    if not value.strip():
        return None
    return Path(value).expanduser().resolve()


def cmd_check(args: argparse.Namespace) -> int:
    from slopgate.config import (
        is_path_skipped,
        is_repo_disabled,
        load_config,
        resolve_git_root,
        resolve_main_git_repo_root,
        resolve_repo_root,
    )

    target = Path(string_arg(args, "path", ".")).resolve()
    config = load_config(repo_root=target, ensure_enrollment=False, ensure_trace=False)
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
                "resolved_repo_root": str(resolved_repo_root)
                if resolved_repo_root is not None
                else None,
                "git_root": str(git_root) if git_root is not None else None,
                "main_repo_root": str(main_repo_root)
                if main_repo_root is not None
                else None,
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

    target = Path(string_arg(args, "path", ".")).resolve()
    include_worktrees = not _bool_arg(args, "no_worktrees")
    repo_root, written_roots = enroll_repo(target, include_worktrees=include_worktrees)
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

    payload_path = Path(string_arg(args, "payload")).resolve()
    parsed = cast(object, json.loads(payload_path.read_text(encoding="utf-8")))
    payload = object_dict(parsed)
    platform = string_arg(args, "platform", UNKNOWN_VALUE)
    result = evaluate_payload(payload, platform=platform)
    if _bool_arg(args, "pretty"):
        print(json.dumps(result.output, indent=2))
    else:
        print(json.dumps(result.output, separators=(",", ":")))
    return 0


def cmd_install(args: argparse.Namespace) -> int:
    from slopgate.installer import SuiteInstallOptions, install_platform, install_suite
    from slopgate.installer._suite import (
        DEFAULT_UPDATE_INTERVAL_MINUTES,
        install_autoupdate,
    )

    platform = string_arg(args, "platform")
    if platform == "all":
        return install_suite(
            SuiteInstallOptions(
                dry_run=_bool_arg(args, "dry_run"),
                include_missing=_bool_arg(args, "include_missing"),
                with_autoupdate=_bool_arg(args, "with_autoupdate"),
                source=string_arg(args, "source"),
                interval_minutes=_int_arg(args, "interval_minutes")
                or DEFAULT_UPDATE_INTERVAL_MINUTES,
                install_scope=string_arg(args, "install_scope", "user"),
                project_root=_project_root_arg(args),
            )
        )
    status = install_platform(
        platform,
        dry_run=_bool_arg(args, "dry_run"),
        install_scope=string_arg(args, "install_scope", "user"),
        project_root=_project_root_arg(args),
    )
    if not _bool_arg(args, "with_autoupdate") or status != 0:
        return status
    return (
        install_autoupdate(
            dry_run=_bool_arg(args, "dry_run"),
            source=string_arg(args, "source"),
            include_missing=_bool_arg(args, "include_missing"),
            interval_minutes=_int_arg(args, "interval_minutes")
            or DEFAULT_UPDATE_INTERVAL_MINUTES,
        )
        or status
    )


def cmd_uninstall(args: argparse.Namespace) -> int:
    from slopgate.installer import (
        SuiteUninstallOptions,
        uninstall_autoupdate,
        uninstall_platform,
        uninstall_suite,
    )

    platform = string_arg(args, "platform")
    if platform == "all":
        return uninstall_suite(
            SuiteUninstallOptions(
                dry_run=_bool_arg(args, "dry_run"),
                with_autoupdate=_bool_arg(args, "with_autoupdate"),
                install_scope=string_arg(args, "install_scope", "user"),
                project_root=_project_root_arg(args),
            )
        )
    status = uninstall_platform(
        platform,
        dry_run=_bool_arg(args, "dry_run"),
        install_scope=string_arg(args, "install_scope", "user"),
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
            source=string_arg(args, "source"),
            interval_minutes=_int_arg(args, "interval_minutes")
            or DEFAULT_UPDATE_INTERVAL_MINUTES,
            install_scope=string_arg(args, "install_scope", "user"),
            project_root=_project_root_arg(args),
        )
    )


def cmd_update_suite(args: argparse.Namespace) -> int:
    from slopgate.installer import SuiteUpdateOptions, update_suite

    return update_suite(
        SuiteUpdateOptions(
            dry_run=_bool_arg(args, "dry_run"),
            source=string_arg(args, "source"),
            include_missing=_bool_arg(args, "include_missing"),
            refresh_hooks=_bool_arg(args, "refresh_hooks"),
            install_scope=string_arg(args, "install_scope", "user"),
            project_root=_project_root_arg(args),
        )
    )


def cmd_stats(args: argparse.Namespace) -> int:
    from slopgate.stats import run_stats

    return run_stats(
        log_path=string_arg(args, "log") or None,
        days=_int_arg(args, "days"),
        as_json=_bool_arg(args, "json"),
    )


def cmd_test(args: argparse.Namespace) -> int:
    from slopgate.cli._self_test import cmd_test

    return cmd_test(args)


def cmd_version(_args: argparse.Namespace) -> int:
    from slopgate import __version__

    print(f"slopgate {__version__}")
    return 0
