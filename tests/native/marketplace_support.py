from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Protocol, cast

from slopgate.installer.native.commands import NativeCommandError
from slopgate.installer.native.marketplace.host import (
    MarketplaceCommands,
    MarketplaceHost,
)
from slopgate.installer.native.model import LegacyCutover, NativeRequest, Registration
from slopgate.installer.native.packages import (
    MarketplaceSpec,
    PackagePlan,
    marketplace_plan,
)
from tests.native.environment import isolate_native_data_dirs
from tests.native.launchers import write_python_launcher

FAKE_EXECUTABLE = "native-marketplace-manager"
FAKE_PLUGIN_NAME = "test-enforcement"
FAKE_CATALOG_DIR = ".test-plugin"
FAKE_MARKETPLACE_NAME = "slopgate-runtime"

_FAKE_SCRIPT = r"""import json
import os
import sys
from pathlib import Path
state_path = Path(os.environ["FAKE_MARKETPLACE_STATE"])
log_path = Path(os.environ["FAKE_MARKETPLACE_LOG"])
args = sys.argv[1:]
with log_path.open("a", encoding="utf-8") as stream:
    stream.write(" ".join(args) + "\n")
state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {"marketplaces": {}, "registrations": []}
failure_match = os.environ.get("FAKE_MARKETPLACE_FAIL_MATCH", "")
if failure_match and failure_match in " ".join(args):
    print("injected manager failure", file=sys.stderr)
    raise SystemExit(9)
marketplaces = state["marketplaces"]
registrations = state["registrations"]
action = args[0]
if action == "marketplace-add":
    marketplaces["slopgate-runtime"] = args[1]
elif action == "marketplace-update":
    if "slopgate-runtime" not in marketplaces:
        raise SystemExit(8)
elif action == "marketplace-remove":
    marketplaces.pop("slopgate-runtime", None)
elif action in {"install", "replace"}:
    scope = args[1]
    project = str(Path.cwd().resolve()) if scope == "project" else None
    root = Path(marketplaces["slopgate-runtime"])
    catalog = json.loads((root / ".test-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    version = catalog["plugins"][0]["version"]
    prior = next((entry for entry in registrations if entry["scope"] == scope and entry["project"] == project), None)
    enabled = prior["enabled"] if prior is not None else True
    if prior is not None:
        registrations.remove(prior)
    registrations.append({"scope": scope, "project": project, "version": version, "enabled": enabled})
elif action == "uninstall":
    scope = args[1]
    project = str(Path.cwd().resolve()) if scope == "project" else None
    state["registrations"] = [entry for entry in registrations if not (entry["scope"] == scope and entry["project"] == project)]
else:
    raise SystemExit(7)
state_path.parent.mkdir(parents=True, exist_ok=True)
state_path.write_text(json.dumps(state, sort_keys=True), encoding="utf-8")
"""


class EnvironmentPatch(Protocol):
    def setenv(self, name: str, value: str) -> None: ...


class FakeMarketplaceCommands(MarketplaceCommands):
    def marketplace_add(self, entry_root: Path) -> list[str]:
        return [FAKE_EXECUTABLE, "marketplace-add", str(entry_root)]

    def marketplace_update(self) -> list[str]:
        return [FAKE_EXECUTABLE, "marketplace-update"]

    def marketplace_remove(self) -> list[str]:
        return [FAKE_EXECUTABLE, "marketplace-remove"]

    def install(self, scope: str, previous: Registration | None) -> list[list[str]]:
        _ = previous
        return [[FAKE_EXECUTABLE, "install", scope]]

    def replace(self, scope: str, previous: Registration) -> list[list[str]]:
        _ = previous
        return [[FAKE_EXECUTABLE, "replace", scope]]

    def uninstall(self, scope: str) -> list[str]:
        return [FAKE_EXECUTABLE, "uninstall", scope]


class RecordingCutover(LegacyCutover):
    def __init__(self) -> None:
        self.removed: list[str] = []
        self.restored = 0
        self.refuse = False

    def preflight(self) -> None:
        if self.refuse:
            raise NativeCommandError("injected cutover preflight refusal")

    def describe(self) -> list[str]:
        return ["Would retire the selected test migration entries"]

    def capture(self) -> None:
        return None

    def remove(self, scope: str) -> int:
        self.removed.append(scope)
        return 0

    def restore(self) -> int:
        self.restored += 1
        self.removed.clear()
        return 0


class FakeMarketplaceHost(MarketplaceHost):
    platform = "test-marketplace"
    label = "Test marketplace"
    executable = FAKE_EXECUTABLE
    plugin_name = FAKE_PLUGIN_NAME
    list_command = f"{FAKE_EXECUTABLE} list"
    activation_note = "Start a new test-host session before claiming activation."
    commands = FakeMarketplaceCommands()

    def __init__(self, state_path: Path, project_root: Path) -> None:
        self.state_path = state_path
        self.project_root = project_root.resolve()
        self.cutovers: list[RecordingCutover] = []
        self.project_issue: str | None = None

    def build_plan(self, binary: str) -> PackagePlan:
        def render(version: str) -> dict[str, str]:
            return {
                "index.ts": f"export const binary = {json.dumps(binary)};\n",
                "package.json": json.dumps(
                    {"name": FAKE_PLUGIN_NAME, "version": version}
                )
                + "\n",
            }

        spec = MarketplaceSpec(
            FAKE_CATALOG_DIR,
            FAKE_PLUGIN_NAME,
            "test enforcement plugin",
            render,
        )
        return marketplace_plan("test-marketplace", spec)

    def legacy_cutover(self, request: NativeRequest) -> LegacyCutover:
        _ = request
        cutover = RecordingCutover()
        self.cutovers.append(cutover)
        return cutover

    def marketplace_sources(self, cwd: Path) -> dict[str, str]:
        _ = cwd
        state = read_marketplace_state(self.state_path)
        return cast(dict[str, str], state["marketplaces"])

    def registrations(self, cwd: Path) -> list[Registration]:
        state = read_marketplace_state(self.state_path)
        raw_entries = cast(list[dict[str, object]], state["registrations"])
        visible: list[Registration] = []
        for entry in raw_entries:
            project = entry["project"]
            scope = str(entry["scope"])
            if scope == "project" and (
                project is None or Path(str(project)).resolve() != cwd.resolve()
            ):
                continue
            visible.append(
                Registration(
                    identity=self.plugin_id,
                    scope=scope,
                    version=str(entry["version"]),
                    enabled=bool(entry["enabled"]),
                    project=Path(str(project)) if project is not None else None,
                )
            )
        return visible

    def project_anchor_issue(self, root: Path) -> str | None:
        _ = root
        return self.project_issue

    def seed_state(self, state: Mapping[str, object]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(state), encoding="utf-8")


def activate_fake_manager(
    tmp_path: Path, monkeypatch: EnvironmentPatch
) -> tuple[Path, Path]:
    isolate_native_data_dirs(monkeypatch, tmp_path)
    bin_dir = tmp_path / "bin"
    write_python_launcher(bin_dir, FAKE_EXECUTABLE, _FAKE_SCRIPT)
    state_path = tmp_path / "state" / "marketplaces.json"
    log_path = tmp_path / "state" / "commands.log"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    current_path = os.environ.get("PATH", "")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("PATH", str(bin_dir) + os.pathsep + current_path)
    monkeypatch.setenv("FAKE_MARKETPLACE_STATE", str(state_path))
    monkeypatch.setenv("FAKE_MARKETPLACE_LOG", str(log_path))
    return state_path, log_path


def read_marketplace_state(path: Path) -> dict[str, object]:
    if not path.exists():
        return {"marketplaces": {}, "registrations": []}
    return cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))


def marketplace_command_count(path: Path) -> int:
    if not path.exists():
        return 0
    return len(path.read_text(encoding="utf-8").splitlines())
