# CI/CD troubleshooting

Notes for Windows GitHub Actions and cross-platform pytest failures.

## Windows hook installer tests

On `win32`, slopgate wraps hook commands in PowerShell. Tests that assert
exact POSIX strings like `slopgate handle` fail unless they use platform-aware
helpers:

- `count_slopgate_hook_commands()` — count owned slopgate hooks
- `command_includes_slopgate_handle()` — match hook fragments across shells
- `expected_hook_command()` / `hook_command()` — build expected command for the
  current platform

Do not compare raw hook JSON strings to shlex-quoted POSIX commands on Windows.

## Platform-specific scheduler tests

Do not simulate Linux systemd or macOS launchd on a Windows runner. Mark tests
with the platform they actually require:

- `SKIP_LINUX_ONLY` — systemd user units, XDG config layout
- `SKIP_DARWIN_ONLY` — LaunchAgents, plist plans
- `SKIP_WINDOWS_ONLY` — schtasks / PowerShell scheduler shims
- `SKIP_UNIX_ONLY` — bash-only scripts, `/etc` paths, POSIX shell helpers

The Windows workflow uses `shell: pwsh` and runs native Windows scheduler tests
(`test_windows_scheduler_plan_uses_schtasks`, Windows hook installer coverage).
Linux/macOS scheduler cases are skipped automatically on `win32`.

## Linux scheduler tests on Windows runners

Avoid patching `_suite.is_windows` to fake Linux on `win32`. That leaves real
Windows path resolution (`%APPDATA%`, PowerShell-wrapped `ExecStart`) in place
and produces flaky failures. Skip instead, or run those tests on Linux/macOS
matrix jobs only.

## Unix-only tests

Marked with `tests.support.SKIP_UNIX_ONLY`:

- `/etc`, `/dev` system-path engine cases
- bash bundle scripts (`verify-local.sh`, `unlink-local.sh`)
- POSIX shell helpers (`printf`, `pwd`)

## Dry-run output assertions

`slopgate update --dry-run` prints commands through `shell_command()`. On
Windows the log is PowerShell-wrapped; assert on fragments (`tool`, `install`,
`--force`, `pip`, `--upgrade`) rather than literal POSIX command strings.

## Path output in logs

Windows paths appear with backslashes in installer status lines. Normalize with
`.replace("\\", "/")` when asserting on relative paths in captured stdout.
