"""Native OMP marketplace registration adapter."""

from __future__ import annotations

import json
from pathlib import Path

from slopgate._types import bool_value, object_dict, object_list, string_value
from slopgate.constants import INSTALL_SCOPE_PROJECT, INSTALL_SCOPE_USER
from slopgate.installer._shared import shell_command
from slopgate.installer.native.commands import (
    LIST_SUBCOMMAND,
    REMOVE_SUBCOMMAND,
    NativeCommandError,
    run_native_command,
)
from slopgate.installer.native.marketplace import (
    MarketplaceCommands,
    MarketplaceHost,
)
from slopgate.installer.native.model import (
    LegacyCutover,
    LegacyRefusal,
    NativeRequest,
    Registration,
    VERSION_KEY,
)
from slopgate.installer._omp_support import MANIFEST_PAYLOAD
from slopgate.installer.native.omp_legacy import (
    OmpLegacyCutover,
    omp_agent_dir,
    omp_project_extension_path,
    omp_user_extension_path,
)
from slopgate.installer.native.packages import (
    MARKETPLACE_NAME,
    MarketplaceSpec,
    PackagePlan,
    marketplace_plan,
)
from slopgate.installer.template_rendering import InvocationTemplateRenderer
from slopgate.resources import resource_path
from slopgate.util.platform import is_link_or_junction

OMP_PLUGIN_NAME = "omp-slopgate"
OMP_PLUGIN_ID = f"{OMP_PLUGIN_NAME}@{MARKETPLACE_NAME}"
OMP_LIST_COMMAND = "omp plugin list --json"
_OMP_ARGV_PLACEHOLDER = '["__SLOPGATE_BIN__"]'

render_omp_extension = InvocationTemplateRenderer(
    _OMP_ARGV_PLACEHOLDER,
    "OMP extension template is missing the slopgate binary placeholder",
)


def _install_argv(scope: str, force: bool) -> list[str]:
    argv = ["omp", "plugin", "install"]
    if force:
        argv.append("--force")
    argv.extend(("--scope", scope, OMP_PLUGIN_ID))
    return argv


def _checked_output(argv: list[str], cwd: Path) -> str:
    completed = run_native_command(argv, cwd=cwd, platform="omp")
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise NativeCommandError(
            f"{shell_command(argv)} exited {completed.returncode}: {detail}"
        )
    return completed.stdout


def _parse_marketplace_sources(output: str) -> dict[str, str]:
    lines = output.splitlines()
    if lines == [
        "No marketplaces configured",
        "",
        "Add one with: omp plugin marketplace add <source>",
    ]:
        return {}
    if lines.count("Configured Marketplaces:") != 1:
        raise LegacyRefusal("Unable to parse OMP marketplace list unambiguously")
    header = lines.index("Configured Marketplaces:")
    sources: dict[str, str] = {}
    for line in lines[header + 1 :]:
        if not line.strip() or not line.startswith("  "):
            continue
        columns = line.strip().split(maxsplit=1)
        if len(columns) != 2:
            raise LegacyRefusal("Malformed entry in OMP marketplace list")
        name, source = columns
        if name in sources:
            raise LegacyRefusal(f"Ambiguous OMP marketplace entry: {name}")
        sources[name] = source
    return sources


def _effective_project_root(cwd: Path) -> Path:
    root = cwd.resolve()
    home = Path.home().resolve()
    for candidate in (root, *root.parents):
        if candidate.resolve() == home:
            break
        if (candidate / ".omp").exists() or (candidate / ".git").exists():
            return candidate
    return root


def _registration_from_entry(
    identity: str, entry: object, project_root: Path
) -> Registration:
    data = object_dict(entry)
    scope = string_value(data.get("scope"))
    if scope not in {INSTALL_SCOPE_USER, INSTALL_SCOPE_PROJECT}:
        raise LegacyRefusal(
            f"Malformed OMP registration for {identity}: unsupported scope {scope!r}"
        )
    version = string_value(data.get("version"))
    if version is None:
        raise LegacyRefusal(
            f"Malformed OMP registration for {identity}: version missing"
        )
    enabled = bool_value(data.get("enabled"))
    if enabled is None:
        if "enabled" in data:
            raise LegacyRefusal(f"Malformed OMP registration for {identity}: enabled")
        enabled = True
    project = project_root if scope == INSTALL_SCOPE_PROJECT else None
    return Registration(identity, scope, version, enabled, project)


def _parse_registrations(output: str, project_root: Path) -> list[Registration]:
    try:
        document = object_dict(json.loads(output))
    except json.JSONDecodeError as exc:
        raise LegacyRefusal("OMP plugin inventory is malformed JSON") from exc
    if not isinstance(document.get("marketplace"), list):
        raise LegacyRefusal("OMP plugin inventory is missing marketplace entries")
    registrations: list[Registration] = []
    for raw_plugin in object_list(document.get("marketplace")):
        plugin = object_dict(raw_plugin)
        identity = string_value(plugin.get("id"))
        if identity is None or identity != OMP_PLUGIN_ID:
            continue
        raw_entries = plugin.get("entries")
        entries = object_list(raw_entries)
        if not isinstance(raw_entries, list):
            raise LegacyRefusal(f"Malformed OMP inventory entries for {identity}")
        registrations.extend(
            _registration_from_entry(identity, entry, project_root) for entry in entries
        )
    return registrations


class OmpMarketplaceCommands(MarketplaceCommands):
    """Exact argument vectors for OMP's native marketplace manager."""

    def marketplace_add(self, entry_root: Path) -> list[str]:
        return ["omp", "plugin", "marketplace", "add", str(entry_root.resolve())]

    def marketplace_update(self) -> list[str]:
        return ["omp", "plugin", "marketplace", "update", MARKETPLACE_NAME]

    def marketplace_remove(self) -> list[str]:
        return ["omp", "plugin", "marketplace", REMOVE_SUBCOMMAND, MARKETPLACE_NAME]

    def install(self, scope: str, previous: Registration | None) -> list[list[str]]:
        commands = [_install_argv(scope, previous is not None)]
        if previous is not None and previous.enabled is False:
            commands.append(
                ["omp", "plugin", "disable", "--scope", scope, OMP_PLUGIN_ID]
            )
        return commands

    def replace(self, scope: str, previous: Registration) -> list[list[str]]:
        commands = [_install_argv(scope, True)]
        if previous.enabled is False:
            commands.append(
                ["omp", "plugin", "disable", "--scope", scope, OMP_PLUGIN_ID]
            )
        return commands

    def uninstall(self, scope: str) -> list[str]:
        return ["omp", "plugin", "uninstall", "--scope", scope, OMP_PLUGIN_ID]


class OmpMarketplaceHost(MarketplaceHost):
    """Package planning, inventory and anchoring for OMP."""

    platform = "omp"
    label = "OMP"
    executable = "omp"
    plugin_name = OMP_PLUGIN_NAME
    list_command = OMP_LIST_COMMAND
    activation_note = "Start a new OMP session before claiming the extension is active."
    commands = OmpMarketplaceCommands()

    def build_plan(self, binary: str) -> PackagePlan:
        template = resource_path("omp_extension.ts").read_text(encoding="utf-8")

        def render(version: str) -> dict[str, str]:
            manifest = {**MANIFEST_PAYLOAD, VERSION_KEY: version}
            return {
                "package.json": json.dumps(manifest, indent=2) + "\n",
                "index.ts": render_omp_extension(template, binary),
            }

        return marketplace_plan(
            "omp",
            MarketplaceSpec(
                catalog_dir=".omp-plugin",
                plugin_name=OMP_PLUGIN_NAME,
                description="Slopgate code hygiene enforcement",
                render=render,
            ),
        )

    def legacy_cutover(self, request: NativeRequest) -> LegacyCutover:
        supported = {INSTALL_SCOPE_USER, INSTALL_SCOPE_PROJECT}
        if not request.scopes or any(
            scope not in supported for scope in request.scopes
        ):
            raise LegacyRefusal(
                "OMP native registration requires explicit user/project scopes"
            )
        return OmpLegacyCutover(request)

    def marketplace_sources(self, cwd: Path) -> dict[str, str]:
        output = _checked_output(["omp", "plugin", "marketplace", LIST_SUBCOMMAND], cwd)
        return _parse_marketplace_sources(output)

    def registrations(self, cwd: Path) -> list[Registration]:
        output = _checked_output(["omp", "plugin", LIST_SUBCOMMAND, "--json"], cwd)
        return _parse_registrations(output, _effective_project_root(cwd))

    def project_anchor_issue(self, root: Path) -> str | None:
        requested = root.resolve()
        omp_dir = requested / ".omp"
        # Check the link first: exists() follows a dangling junction and returns False.
        if is_link_or_junction(omp_dir) or (omp_dir.exists() and not omp_dir.is_dir()):
            return f"OMP project anchor is not a safe directory: {omp_dir}"
        anchor = _effective_project_root(requested)
        if anchor != requested:
            return (
                f"OMP project scope would target ancestor {anchor}, not requested "
                f"project root {requested}; add {omp_dir} or use the anchor root"
            )
        return None

    def project_anchor_action(self, root: Path) -> str | None:
        anchor = root.resolve() / ".omp"
        return None if anchor.exists() else f"Would create OMP project anchor: {anchor}"

    def ensure_project_anchor(self, root: Path) -> Path | None:
        anchor = root / ".omp"
        if anchor.exists():
            return None
        anchor.mkdir()
        return anchor


__all__ = [
    "OMP_LIST_COMMAND",
    "OMP_PLUGIN_ID",
    "OMP_PLUGIN_NAME",
    "OmpMarketplaceCommands",
    "OmpMarketplaceHost",
    "omp_agent_dir",
    "omp_project_extension_path",
    "omp_user_extension_path",
    "render_omp_extension",
]
