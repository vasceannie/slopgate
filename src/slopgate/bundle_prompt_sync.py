"""Synchronize package-managed Slopgate prompt fragments into harness markdown.

The source fragment is loaded from installed ``ai-slopgate`` package resources, so
``uv tool install ai-slopgate`` can orchestrate updates without relying on a
source checkout path.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from importlib import resources
from pathlib import Path

from slopgate.constants import (
    PLATFORM_CLAUDE,
    PLATFORM_CODEX,
    PLATFORM_CURSOR,
    PLATFORM_OPENCODE,
)

from slopgate.installer._install_scope import (
    INSTALL_SCOPE_BOTH,
    INSTALL_SCOPE_PROJECT,
    INSTALL_SCOPE_USER,
    InstallScope,
)

PromptPlatform = str
PromptScope = InstallScope

VALID_PROMPT_PLATFORMS: tuple[PromptPlatform, ...] = (
    PLATFORM_CLAUDE,
    PLATFORM_OPENCODE,
    PLATFORM_CODEX,
    PLATFORM_CURSOR,
)
MANAGED_BLOCK_ID = "slopgate-skill-routing"
PROMPT_FRAGMENT_RESOURCE = "bundle/shared/prompt-fragments/slopgate-skill-routing.md"
PROMPT_FRAGMENT_SOURCE_LABEL = (
    "slopgate.resources/bundle/shared/prompt-fragments/slopgate-skill-routing.md"
)


@dataclass(frozen=True)
class PromptSyncOptions:
    """Execution options for prompt sync or removal."""

    dry_run: bool = False
    remove: bool = False


@dataclass(frozen=True)
class PromptSyncResult:
    """Result for one managed prompt target."""

    platform: str
    scope: str
    path: Path
    changed: bool
    dry_run: bool


def load_skill_routing_fragment() -> str:
    """Read the packaged Slopgate skill-routing prompt fragment."""

    resource = resources.files(__name__.partition(".")[0]).joinpath(
        "resources", PROMPT_FRAGMENT_RESOURCE
    )
    return resource.read_text(encoding="utf-8")


def managed_block_markers(source_label: str, digest: str) -> tuple[str, str]:
    """Return start/end comments for the managed prompt block."""

    start = (
        f"<!-- slopgate:managed:start id={MANAGED_BLOCK_ID} "
        f"source={source_label} sha256={digest} -->"
    )
    end = f"<!-- slopgate:managed:end id={MANAGED_BLOCK_ID} -->"
    return start, end


def _managed_block_bounds(original: str) -> tuple[int, int] | None:
    start_token = f"<!-- slopgate:managed:start id={MANAGED_BLOCK_ID} "
    end_token = f"<!-- slopgate:managed:end id={MANAGED_BLOCK_ID} -->"

    start_count = original.count(start_token)
    end_count = original.count(end_token)
    if start_count > 1 or end_count > 1:
        raise ValueError(f"multiple managed blocks found for {MANAGED_BLOCK_ID}")
    if start_count != end_count:
        raise ValueError(f"malformed managed block markers for {MANAGED_BLOCK_ID}")
    if start_count == 0:
        return None

    start_index = original.index(start_token)
    end_index = original.index(end_token) + len(end_token)
    suffix_start = end_index
    if suffix_start < len(original) and original[suffix_start] == "\n":
        suffix_start += 1
    return (start_index, suffix_start)


def update_managed_block(
    original: str,
    *,
    managed_content: str,
    source_label: str = PROMPT_FRAGMENT_SOURCE_LABEL,
) -> str:
    """Append or replace the Slopgate managed block without touching other text."""

    digest = sha256(managed_content.encode("utf-8")).hexdigest()
    start, end = managed_block_markers(source_label, digest)
    bounds = _managed_block_bounds(original)

    block = f"{start}\n{managed_content.rstrip()}\n{end}\n"
    if bounds is None:
        separator = (
            "" if not original else "\n\n" if original.endswith("\n") else "\n\n"
        )
        return f"{original}{separator}{block}"

    start_index, suffix_start = bounds
    return f"{original[:start_index]}{block}{original[suffix_start:]}"


def remove_managed_block(original: str) -> str:
    """Remove only the Slopgate managed block from prompt text."""

    bounds = _managed_block_bounds(original)
    if bounds is None:
        return original
    start_index, suffix_start = bounds
    prefix = original[:start_index]
    if prefix.endswith("\n\n"):
        prefix = prefix[:-2]
    return f"{prefix}{original[suffix_start:]}"


def _user_prompt_targets(platform: PromptPlatform) -> tuple[Path, ...]:
    home = Path.home()
    if platform == PLATFORM_CLAUDE:
        return (home / ".claude" / "CLAUDE.md",)
    if platform == PLATFORM_OPENCODE:
        return (home / ".config" / PLATFORM_OPENCODE / "AGENTS.md",)
    if platform == PLATFORM_CODEX:
        return (home / ".codex" / "AGENTS.md",)
    if platform == PLATFORM_CURSOR:
        return (home / ".cursor" / "AGENTS.md",)
    raise ValueError(f"unsupported platform: {platform}")


def _project_prompt_targets(
    platform: PromptPlatform, project_root: Path
) -> tuple[Path, ...]:
    if platform == PLATFORM_CLAUDE:
        return (project_root / "CLAUDE.md",)
    if platform in {PLATFORM_OPENCODE, PLATFORM_CODEX, PLATFORM_CURSOR}:
        return (project_root / "AGENTS.md",)
    raise ValueError(f"unsupported platform: {platform}")


def _requested_platforms(
    platforms: tuple[str, ...] | list[str] | None,
) -> tuple[PromptPlatform, ...]:
    if not platforms or "all" in platforms:
        return VALID_PROMPT_PLATFORMS
    invalid = [
        platform for platform in platforms if platform not in VALID_PROMPT_PLATFORMS
    ]
    if invalid:
        raise ValueError(f"unsupported platform(s): {', '.join(invalid)}")
    requested: list[PromptPlatform] = []
    for platform in platforms:
        requested.append(platform)
    return tuple(requested)


def _requested_scopes(scope: PromptScope) -> tuple[str, ...]:
    if scope == INSTALL_SCOPE_BOTH:
        return (INSTALL_SCOPE_USER, INSTALL_SCOPE_PROJECT)
    if scope in {INSTALL_SCOPE_USER, INSTALL_SCOPE_PROJECT}:
        return (scope,)
    raise ValueError(f"unsupported prompt scope: {scope}")


def _target_paths(
    *,
    platforms: tuple[PromptPlatform, ...],
    scope: PromptScope,
    project_root: Path | None,
) -> list[tuple[str, str, Path]]:
    resolved_project_root = (project_root or Path.cwd()).expanduser().resolve()
    targets: list[tuple[str, str, Path]] = []
    seen: set[Path] = set()
    for prompt_scope in _requested_scopes(scope):
        for platform in platforms:
            paths = (
                _user_prompt_targets(platform)
                if prompt_scope == INSTALL_SCOPE_USER
                else _project_prompt_targets(platform, resolved_project_root)
            )
            for path in paths:
                resolved = path.expanduser()
                if resolved in seen:
                    continue
                seen.add(resolved)
                targets.append((platform, prompt_scope, resolved))
    return targets


def sync_skill_routing_prompts(
    *,
    platforms: tuple[str, ...] | list[str] | None = None,
    scope: PromptScope = INSTALL_SCOPE_USER,
    project_root: Path | None = None,
    options: PromptSyncOptions | None = None,
) -> list[PromptSyncResult]:
    """Synchronize or remove packaged skill-routing blocks in prompt markdown files."""

    resolved_options = options or PromptSyncOptions()
    requested_platforms = _requested_platforms(platforms)
    managed_content = "" if resolved_options.remove else load_skill_routing_fragment()
    results: list[PromptSyncResult] = []
    for platform, target_scope, path in _target_paths(
        platforms=requested_platforms,
        scope=scope,
        project_root=project_root,
    ):
        original = path.read_text(encoding="utf-8") if path.exists() else ""
        updated = (
            remove_managed_block(original)
            if resolved_options.remove
            else update_managed_block(original, managed_content=managed_content)
        )
        changed = updated != original
        if changed and not resolved_options.dry_run:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(updated, encoding="utf-8")
        results.append(
            PromptSyncResult(
                platform=platform,
                scope=target_scope,
                path=path,
                changed=changed,
                dry_run=resolved_options.dry_run,
            )
        )
    return results
