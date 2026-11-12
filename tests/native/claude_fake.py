"""Deterministic stateful fake for Claude's local plugin-manager CLI."""

from __future__ import annotations

from pathlib import Path

from tests.native.launchers import write_python_launcher


PLUGIN_ID = "slopgate-enforcement@slopgate-runtime"
MARKETPLACE_NAME = "slopgate-runtime"


def write_fake_claude(bin_dir: Path) -> Path:
    """Write an executable fake named ``claude`` and return its path."""
    return write_python_launcher(bin_dir, "claude", _SCRIPT)


_SCRIPT = r"""
import json
import os
import sys
from pathlib import Path

def state_path():
    return Path(os.environ["FAKE_CLAUDE_STATE"])

def load_state():
    path = state_path()
    if not path.exists():
        return {"marketplaces": {}, "plugins": []}
    return json.loads(path.read_text(encoding="utf-8"))

def save_state(state):
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")

def log_call(argv):
    path_value = os.environ.get("FAKE_CLAUDE_LOG")
    if not path_value:
        return
    path = Path(path_value)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(argv) + "\n")

def scope_settings_path(scope):
    if scope == "project":
        return Path.cwd() / ".claude" / "settings.json"
    return Path(os.environ["CLAUDE_CONFIG_DIR"]) / "settings.json"

def setting_enabled(scope, plugin_id):
    path = scope_settings_path(scope)
    if not path.exists():
        return True
    settings = json.loads(path.read_text(encoding="utf-8"))
    enabled = settings.get("enabledPlugins", {})
    return enabled.get(plugin_id, True) if isinstance(enabled, dict) else True

def set_setting_enabled(scope, plugin_id, enabled):
    path = scope_settings_path(scope)
    settings = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    plugins = settings.setdefault("enabledPlugins", {})
    if not isinstance(plugins, dict):
        plugins = {}
        settings["enabledPlugins"] = plugins
    if enabled is None:
        plugins.pop(plugin_id, None)
    else:
        plugins[plugin_id] = enabled
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")

def registration(state, plugin_id, scope, cwd):
    return next(
        (
            item for item in state["plugins"]
            if item.get("id") == plugin_id
            and item.get("scope") == scope
            and (scope != "project" or item.get("projectPath") == cwd)
        ),
        None,
    )

def scoped_enabled(state, plugin_id, scope, cwd):
    item = registration(state, plugin_id, scope, cwd)
    return bool(item.get("enabled", True)) if item is not None else setting_enabled(scope, plugin_id)

def effective_enabled(state, plugin_id, cwd):
    project_item = registration(state, plugin_id, "project", cwd)
    if project_item is not None:
        return scoped_enabled(state, plugin_id, "project", cwd)
    return scoped_enabled(state, plugin_id, "user", cwd)

def listed_plugins(state, cwd):
    entries = []
    for item in state["plugins"]:
        if item.get("scope") == "project" and item.get("projectPath") != cwd:
            continue
        listed = dict(item)
        plugin_id = item.get("id")
        if isinstance(plugin_id, str):
            listed["enabled"] = effective_enabled(state, plugin_id, cwd)
            listed["projectEnabled"] = scoped_enabled(state, plugin_id, "project", cwd)
        entries.append(listed)
    return entries

def set_enabled(scope, plugin_id, enabled):
    set_setting_enabled(scope, plugin_id, enabled)

def set_known_marketplace(name, path):
    settings_path = Path(os.environ["CLAUDE_CONFIG_DIR"]) / "settings.json"
    settings = json.loads(settings_path.read_text(encoding="utf-8")) if settings_path.exists() else {}
    known = settings.setdefault("extraKnownMarketplaces", {})
    if path is None:
        known.pop(name, None)
    else:
        known[name] = {"source": {"source": "directory", "path": path}}
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")


def failure_matches(action, scope):
    requests = os.environ.get("FAKE_CLAUDE_FAIL", "").split(";")
    return any(request == action or request == f"{action}:{scope}" for request in requests)

def fail(message):
    print(message, file=sys.stderr)
    raise SystemExit(1)

def catalog(path):
    catalog_path = Path(path) / ".claude-plugin" / "marketplace.json"
    return json.loads(catalog_path.read_text(encoding="utf-8"))

def marketplace_root(marketplace):
    return marketplace.get("root", marketplace["path"])

def plugin_version(marketplace):
    source = marketplace_root(marketplace)
    data = catalog(source)
    plugin = data["plugins"][0]
    manifest_path = Path(source) / plugin["source"].removeprefix("./") / ".claude-plugin" / "plugin.json"
    if not manifest_path.exists():
        manifest_path = Path(source) / plugin["source"].removeprefix("./") / "plugin.json"
    return json.loads(manifest_path.read_text(encoding="utf-8"))["version"]

def matches(plugin, plugin_id, scope):
    if plugin.get("id") != plugin_id or plugin.get("scope") != scope:
        return False
    if scope == "project":
        return plugin.get("projectPath") == str(Path.cwd().resolve())
    return True

def main(args):
    log_call(args)
    if len(args) < 2 or args[0] != "plugin":
        fail("unsupported fake claude command")
    action = args[1]
    scope = None
    if "--scope" in args:
        scope = args[args.index("--scope") + 1]
    elif action == "marketplace" and len(args) > 2:
        scope = args[2]
    should_fail = failure_matches(action, scope)
    fail_after = os.environ.get("FAKE_CLAUDE_FAIL_AFTER") == "1"
    if should_fail and not fail_after:
        fail(f"injected failure: {action}:{scope}")
    state = load_state()
    if action == "marketplace":
        if len(args) < 3:
            fail("marketplace action missing")
        market_action = args[2]
        if market_action == "add":
            root = str(Path(args[3]).resolve())
            data = catalog(root)
            # FAKE_CLAUDE_RELATIVE_SOURCE: report the source as given, like a
            # CLI that does not canonicalize a ./relative marketplace path.
            reported = args[3] if os.environ.get("FAKE_CLAUDE_RELATIVE_SOURCE") == "1" else root
            state["marketplaces"][data["name"]] = {"path": reported, "root": root, "source": "directory"}
            set_known_marketplace(data["name"], root)
            save_state(state)
        elif market_action == "update":
            name = args[3]
            if name not in state["marketplaces"]:
                fail(f"unknown marketplace: {name}")
        elif market_action == "remove":
            state["marketplaces"].pop(args[3], None)
            set_known_marketplace(args[3], None)
            save_state(state)
        elif market_action == "list":
            entries = [
                {"name": name, "source": "directory", "path": entry["path"], "installLocation": entry["path"]}
                for name, entry in state["marketplaces"].items()
            ]
            print(json.dumps(entries))
        else:
            fail(f"unsupported marketplace action: {market_action}")
    elif action == "list":
        cwd = str(Path.cwd().resolve())
        print(json.dumps(listed_plugins(state, cwd)))
    elif action in {"install", "uninstall", "disable", "enable"}:
        if len(args) < 3:
            fail("plugin identity missing")
        plugin_id = args[2]
        if scope not in {"user", "project"}:
            fail(f"invalid scope: {scope}")
        found = next((item for item in state["plugins"] if matches(item, plugin_id, scope)), None)
        if action == "install":
            if found is not None:
                fail(f"already installed: {plugin_id} ({scope})")
            marketplace_name = plugin_id.split("@", 1)[1]
            marketplace = state["marketplaces"].get(marketplace_name)
            if marketplace is None:
                fail(f"unknown marketplace: {marketplace_name}")
            entry = {
                "id": plugin_id,
                "version": plugin_version(marketplace),
                "scope": scope,
                "enabled": True,
                "installPath": marketplace_root(marketplace),
            }
            if scope == "project":
                entry["projectPath"] = str(Path.cwd().resolve())
            state["plugins"].append(entry)
            set_enabled(scope, plugin_id, True)
            save_state(state)
        elif action == "uninstall":
            state["plugins"] = [item for item in state["plugins"] if not matches(item, plugin_id, scope)]
            set_enabled(scope, plugin_id, None)
            save_state(state)
        elif action in {"disable", "enable"}:
            if found is None:
                fail(f"not installed: {plugin_id} ({scope})")
            enabled = action == "enable"
            found["enabled"] = enabled
            set_enabled(scope, plugin_id, enabled)
            save_state(state)
        else:
            fail(f"unsupported plugin action: {action}")
    else:
        fail(f"unsupported action: {action}")
    if should_fail and fail_after:
        fail(f"injected post-mutation failure: {action}:{scope}")

main(sys.argv[1:])
"""
