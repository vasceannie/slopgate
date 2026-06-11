"""Thin-wrapper enrichment handler."""

from __future__ import annotations

from typing import TYPE_CHECKING

from slopgate.enrichment._helpers import (
    append_enrichment_message,
    metadata_str,
    path_source_from_metadata,
)
from slopgate.enrichment.local_context import find_local_call_sites

if TYPE_CHECKING:
    from slopgate.context import HookContext
    from slopgate.models import RuleFinding


def enrich_thin_wrapper(finding: RuleFinding, ctx: HookContext) -> None:
    """Enrich thin-wrapper findings with inlining guidance."""
    func_name = metadata_str(finding.metadata, "function")
    wrapped = metadata_str(finding.metadata, "wraps")
    loaded = path_source_from_metadata(finding, ctx)
    if loaded is None:
        return
    if func_name is None:
        return
    loaded_path, loaded_source = loaded
    call_count = loaded_source.count(f"{func_name}(")
    extras: list[str] = []
    if call_count > 1:
        extras.append(
            f"\n`{func_name}` is called ~{call_count - 1} time(s) in this file."
        )
        replacement = (
            f"`{wrapped}(...)`" if wrapped is not None else "the wrapped function"
        )
        extras.append(
            f"Replace each `{func_name}(...)` call with {replacement}, then remove "
            "the wrapper."
        )
    else:
        call_sites = find_local_call_sites(func_name, ctx, loaded_path)
        if call_sites:
            extras.append("\nLocal call sites to update before removing this wrapper:")
            extras.extend(f"- {site}" for site in call_sites)
        else:
            extras.append(
                f"\n`{func_name}` appears to be called from other files. Search for all usages before inlining."
            )
    extras.append(
        "Boundary check before keeping the wrapper: it must validate/normalize, "
        "name a domain boundary, centralize policy/caching/permission/logging, "
        "adapt interfaces, or shield unstable third-party APIs."
    )
    append_enrichment_message(finding, extras)
