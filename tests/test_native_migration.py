from __future__ import annotations

from typing import cast

from hypothesis import given, settings, strategies

from slopgate.installer.native.migration import extract_owned_hooks

PROPERTY_EXAMPLES = 40
MAX_HOOK_GROUPS = 12
OWNED_COMMAND = "slopgate handle --platform claude"
USER_COMMAND = "git status"
OWNED_FLAGS = strategies.lists(
    strategies.booleans(), min_size=0, max_size=MAX_HOOK_GROUPS
)


def _hook_case(
    owned_flags: list[bool],
) -> tuple[dict[str, object], list[dict[str, object]]]:
    groups: list[dict[str, object]] = [
        {
            "matcher": f"tool-{index}",
            "timeout": index,
            "hooks": [
                {
                    "type": "command",
                    "command": OWNED_COMMAND if is_owned else USER_COMMAND,
                }
            ],
        }
        for index, is_owned in enumerate(owned_flags)
    ]
    expected = [
        {
            **group,
            "hooks": [cast(dict[str, object], cast(list[object], group["hooks"])[0])],
        }
        for group, is_owned in zip(groups, owned_flags, strict=True)
        if is_owned
    ]
    return {"PreToolUse": groups}, expected


@settings(max_examples=PROPERTY_EXAMPLES, deadline=None)
@given(owned_flags=OWNED_FLAGS)
def test_extract_owned_hooks_preserves_metadata_and_idempotence(
    owned_flags: list[bool],
) -> None:
    source, expected = _hook_case(owned_flags)
    extracted = extract_owned_hooks(source)
    observed = (
        extracted.get("PreToolUse", []) == expected,
        extract_owned_hooks(extracted) == extracted,
    )

    assert observed == (True, True), (
        "owned hook extraction should retain source metadata and be idempotent"
    )
