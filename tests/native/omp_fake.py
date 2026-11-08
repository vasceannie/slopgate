"""Deterministic fake OMP executable for native installer tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from tests.native.launchers import write_python_launcher


OMP_PLUGIN_ID = "omp-slopgate@slopgate-runtime"


def write_fake_omp(bin_dir: Path) -> Path:
    """Write an executable fake named ``omp`` and return its path."""
    return write_python_launcher(bin_dir, "omp", _SCRIPT)


def read_fake_state(state_path: Path) -> dict[str, object]:
    """Read the state owned by one isolated fake OMP process."""
    if not state_path.exists():
        return {"marketplaces": {}, "registrations": [], "calls": []}
    return cast(dict[str, object], json.loads(state_path.read_text(encoding="utf-8")))


_SCRIPT = r"""
import json
import os
import sys
from pathlib import Path

state_path = Path(os.environ["FAKE_OMP_STATE"])
args = sys.argv[1:]
cwd = Path.cwd().resolve()
state = {"marketplaces": {}, "registrations": [], "calls": []}
if state_path.exists():
    state = json.loads(state_path.read_text(encoding="utf-8"))


def fail_requested():
    marker = os.environ.get("FAKE_OMP_FAIL_ON", "")
    return bool(marker) and marker in " ".join(args)


def save():
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, sort_keys=True), encoding="utf-8")


def market_source(name):
    return state["marketplaces"].get(name)


def plugin_version(identity):
    plugin_name, separator, market_name = identity.partition("@")
    if not separator:
        raise SystemExit("invalid plugin identity")
    root = Path(market_source(market_name))
    catalog_path = root / ".omp-plugin" / "marketplace.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    entry = next(item for item in catalog["plugins"] if item["name"] == plugin_name)
    relative = str(entry["source"]).removeprefix("./")
    manifest = json.loads((root / relative / "package.json").read_text(encoding="utf-8"))
    return str(manifest["version"])


def find_registration(scope, identity):
    for item in state["registrations"]:
        if item["scope"] != scope or item["id"] != identity:
            continue
        if scope == "project" and item.get("project") != str(cwd):
            continue
        return item
    return None


if args[:3] == ["plugin", "marketplace", "list"]:
    if not state["marketplaces"]:
        print("No marketplaces configured\n")
        print("Add one with: omp plugin marketplace add <source>")
    else:
        print("Configured Marketplaces:\n")
        for name, source in state["marketplaces"].items():
            print(f"  {name}  {source}")
    raise SystemExit(0)

fail_after = os.environ.get("FAKE_OMP_FAIL_AFTER_MUTATION") == "1"
should_fail = fail_requested()
if should_fail and not fail_after:
    print("injected OMP failure before mutation", file=sys.stderr)
    raise SystemExit(1)

if args[:3] == ["plugin", "marketplace", "add"]:
    source = str(Path(args[3]).resolve())
    catalog = json.loads((Path(source) / ".omp-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    state["marketplaces"][catalog["name"]] = source
elif args[:3] == ["plugin", "marketplace", "update"]:
    if args[3] not in state["marketplaces"]:
        print("marketplace not found", file=sys.stderr)
        raise SystemExit(1)
elif args[:3] == ["plugin", "marketplace", "remove"]:
    state["marketplaces"].pop(args[3], None)
elif args[:2] == ["plugin", "list"]:
    plugins = []
    for item in state["registrations"]:
        if item["scope"] == "project" and item.get("project") != str(cwd):
            continue
        entry = {"scope": item["scope"], "installPath": "/fake/cache", "version": item["version"]}
        if item.get("enabled") is False:
            entry["enabled"] = False
        plugins.append({"id": item["id"], "scope": item["scope"], "entries": [entry]})
    print(json.dumps({"npm": [], "marketplace": plugins}))
    raise SystemExit(0)
elif args[:2] == ["plugin", "install"]:
    scope = args[args.index("--scope") + 1]
    identity = args[-1]
    entry = find_registration(scope, identity)
    version = plugin_version(identity)
    if entry is None:
        entry = {"id": identity, "scope": scope, "project": str(cwd) if scope == "project" else None, "version": version, "enabled": True}
        state["registrations"].append(entry)
    else:
        entry["version"] = version
    print(f"Installed {identity} ({version})")
elif args[:2] in (["plugin", "disable"], ["plugin", "enable"]):
    scope = args[args.index("--scope") + 1]
    entry = find_registration(scope, args[-1])
    if entry is None:
        print("registration not found", file=sys.stderr)
        raise SystemExit(1)
    entry["enabled"] = args[1] == "enable"
elif args[:2] == ["plugin", "uninstall"]:
    scope = args[args.index("--scope") + 1]
    entry = find_registration(scope, args[-1])
    if entry is not None:
        state["registrations"].remove(entry)
else:
    print("unsupported fake OMP command", file=sys.stderr)
    raise SystemExit(2)

state["calls"].append(args)
save()
if should_fail and fail_after:
    print("injected OMP failure after mutation", file=sys.stderr)
    raise SystemExit(1)
raise SystemExit(0)
"""
