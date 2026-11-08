from __future__ import annotations

import os
import shlex
import shutil
import stat
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

COMMAND_TIMEOUT_SECONDS = 180
_REQUIRED_HOSTS = ("omp", "pi", "claude", "bun", "node", "git")
_SYSTEM_PATHS = ("/usr/local/bin", "/usr/bin", "/bin")
_FORBIDDEN_PROFILE_PREFIXES = ("ORCA_", "OMP", "PI_", "CLAUDE_CODE_")


class SmokeFailure(RuntimeError):
    """A native install smoke assertion or command failed."""


@dataclass(frozen=True, slots=True)
class Sandbox:
    repo: Path
    root: Path
    home: Path
    project: Path
    omp_agent: Path
    pi_agent: Path
    binaries: dict[str, str]
    slopgate_binary: Path
    xdg_config: Path
    xdg_data: Path
    xdg_state: Path
    xdg_cache: Path
    xdg_runtime: Path
    slopgate_config: Path
    slopgate_root: Path
    slopgate_log: Path
    daemon_socket: Path
    alternate_bin: Path

    def environment(self, host: str, alternate_binary: bool = False) -> dict[str, str]:
        path_entries = [self.slopgate_binary.parent]
        path_entries.extend(Path(value).parent for value in self.binaries.values())
        path_entries.extend(Path(item) for item in _SYSTEM_PATHS)
        if alternate_binary:
            path_entries.insert(0, self.alternate_bin)
        path_value = os.pathsep.join(dict.fromkeys(str(item) for item in path_entries))
        env = {
            "PATH": path_value,
            "HOME": str(self.home),
            "XDG_CONFIG_HOME": str(self.xdg_config),
            "XDG_DATA_HOME": str(self.xdg_data),
            "XDG_STATE_HOME": str(self.xdg_state),
            "XDG_CACHE_HOME": str(self.xdg_cache),
            "XDG_RUNTIME_DIR": str(self.xdg_runtime),
            "CLAUDE_CONFIG_DIR": str(self.home / ".claude"),
            "SLOPGATE_CONFIG_DIR": str(self.slopgate_config),
            "SLOPGATE_ROOT": str(self.slopgate_root),
            "SLOPGATE_LOG_DIR": str(self.slopgate_log),
            "SLOPGATE_DAEMON_SOCKET": str(self.daemon_socket),
            "TMPDIR": str(self.root / "tmp"),
            "TEMP": str(self.root / "tmp"),
            "TMP": str(self.root / "tmp"),
            "TERM": "dumb",
            "NO_COLOR": "1",
            "LANG": "C.UTF-8",
        }
        if host in {"omp", "pi"}:
            selected_agent = self.omp_agent if host == "omp" else self.pi_agent
            env["PI_CODING_AGENT_DIR"] = str(selected_agent)
        if os.name == "nt":
            env.update(
                {
                    "APPDATA": str(self.root / "appdata"),
                    "LOCALAPPDATA": str(self.root / "localappdata"),
                    "USERPROFILE": str(self.home),
                    "SYSTEMROOT": os.environ.get("SYSTEMROOT", "C:\\Windows"),
                    "COMSPEC": os.environ.get("COMSPEC", "cmd.exe"),
                }
            )
        _validate_environment(self, env, host, alternate_binary)
        return env


def _slopgate_executable(repo: Path) -> Path:
    relative = (
        Path("Scripts") / "slopgate.exe"
        if os.name == "nt"
        else Path("bin") / "slopgate"
    )
    executable = repo / ".venv" / relative
    if not executable.is_file():
        raise SmokeFailure(f"Checkout Slopgate executable is missing: {executable}")
    return executable.resolve()


def _host_binaries() -> dict[str, str]:
    binaries: dict[str, str] = {}
    missing: list[str] = []
    for name in _REQUIRED_HOSTS:
        executable = shutil.which(name)
        if executable is None:
            missing.append(name)
        else:
            binaries[name] = str(Path(executable).absolute())
    if missing:
        raise SmokeFailure(
            f"Required installed host/runtime executables are missing: {', '.join(missing)}"
        )
    return binaries


def _make_directories(root: Path) -> dict[str, Path]:
    paths = {
        "home": root / "home",
        "project": root / "project with spaces",
        "omp_agent": root / "agents" / "omp",
        "pi_agent": root / "agents" / "pi",
        "xdg_config": root / "xdg" / "config",
        "xdg_data": root / "xdg" / "data",
        "xdg_state": root / "xdg" / "state",
        "xdg_cache": root / "xdg" / "cache",
        "xdg_runtime": root / "xdg" / "runtime",
        "slopgate_config": root / "slopgate-config",
        "slopgate_root": root / "slopgate-state",
        "slopgate_log": root / "slopgate-log",
        "alternate_bin": root / "alternate-bin",
    }
    for directory in paths.values():
        directory.mkdir(parents=True, exist_ok=True)
    (root / "tmp").mkdir(exist_ok=True)
    paths["xdg_runtime"].chmod(stat.S_IRWXU)
    if os.name == "nt":
        (root / "appdata").mkdir(exist_ok=True)
        (root / "localappdata").mkdir(exist_ok=True)
    return paths


def create_sandbox(repo: Path) -> Sandbox:
    resolved_repo = repo.resolve()
    binaries = _host_binaries()
    slopgate_binary = _slopgate_executable(resolved_repo)
    root = Path(tempfile.mkdtemp(prefix="slopgate-native-smoke-")).resolve()
    paths = _make_directories(root)
    sandbox = Sandbox(
        repo=resolved_repo,
        root=root,
        home=paths["home"],
        project=paths["project"],
        omp_agent=paths["omp_agent"],
        pi_agent=paths["pi_agent"],
        binaries=binaries,
        slopgate_binary=slopgate_binary,
        xdg_config=paths["xdg_config"],
        xdg_data=paths["xdg_data"],
        xdg_state=paths["xdg_state"],
        xdg_cache=paths["xdg_cache"],
        xdg_runtime=paths["xdg_runtime"],
        slopgate_config=paths["slopgate_config"],
        slopgate_root=paths["slopgate_root"],
        slopgate_log=paths["slopgate_log"],
        daemon_socket=paths["slopgate_root"] / "unused-private-daemon.sock",
        alternate_bin=paths["alternate_bin"],
    )
    if sandbox.daemon_socket.exists():
        raise SmokeFailure(
            f"Expected an unused private daemon socket path: {sandbox.daemon_socket}"
        )
    return sandbox


def _validate_profile(env: dict[str, str]) -> None:
    unexpected = [
        name
        for name in env
        if name.startswith(_FORBIDDEN_PROFILE_PREFIXES)
        and name != "PI_CODING_AGENT_DIR"
    ]
    if unexpected or "CLAUDE_CODE_PLUGIN_DIRS" in env:
        raise SmokeFailure(
            f"Sandbox environment contains host profile overrides: {unexpected}"
        )


def _validate_roots(sandbox: Sandbox, env: dict[str, str]) -> None:
    if env["HOME"] != str(sandbox.home):
        raise SmokeFailure("Sandbox HOME escaped its disposable root")
    if env["CLAUDE_CONFIG_DIR"] != str(sandbox.home / ".claude"):
        raise SmokeFailure("CLAUDE_CONFIG_DIR must exactly match sandbox HOME/.claude")


def _validate_agent_dir(sandbox: Sandbox, env: dict[str, str], host: str) -> None:
    if (
        host == "omp"
        and Path(env["PI_CODING_AGENT_DIR"]).resolve() != sandbox.omp_agent.resolve()
    ):
        raise SmokeFailure("OMP legacy agent directory is not the sandbox OMP root")
    if (
        host == "pi"
        and Path(env["PI_CODING_AGENT_DIR"]).resolve() != sandbox.pi_agent.resolve()
    ):
        raise SmokeFailure("Pi agent directory is not the sandbox Pi root")
    if host == "claude" and "PI_CODING_AGENT_DIR" in env:
        raise SmokeFailure(
            "Claude environment unexpectedly inherited a Pi agent directory"
        )


def _validate_slopgate_path(
    sandbox: Sandbox, env: dict[str, str], alternate_binary: bool
) -> None:
    resolved = shutil.which("slopgate", path=env["PATH"])
    expected = (
        sandbox.alternate_bin / ("slopgate.exe" if os.name == "nt" else "slopgate")
        if alternate_binary
        else sandbox.slopgate_binary
    )
    if resolved is None or Path(resolved).resolve() != expected.resolve():
        raise SmokeFailure(
            "PATH does not resolve Slopgate to the selected sandbox executable"
        )


def _validate_environment(
    sandbox: Sandbox, env: dict[str, str], host: str, alternate_binary: bool
) -> None:
    _validate_profile(env)
    _validate_roots(sandbox, env)
    _validate_agent_dir(sandbox, env, host)
    _validate_slopgate_path(sandbox, env, alternate_binary)


def run_command(
    command: list[str], cwd: Path, env: dict[str, str], label: str
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=COMMAND_TIMEOUT_SECONDS,
        check=False,
    )
    if completed.returncode != 0:
        detail = "\n".join(
            part.strip()
            for part in (completed.stdout, completed.stderr)
            if part.strip()
        )
        raise SmokeFailure(
            f"{label} exited {completed.returncode}: {shlex.join(command)}\n{detail}"
        )
    return completed
