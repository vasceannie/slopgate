from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path

import pytest
from hypothesis import given, strategies as st

from slopgate.bundle_prompt_sync import (
    MANAGED_BLOCK_ID,
    PromptSyncOptions,
    managed_block_markers,
    remove_managed_block,
    sync_skill_routing_prompts,
    update_managed_block,
)
from slopgate.cli.parsers import build_parser
from slopgate.cli.commands_bundle import cmd_bundle_sync_prompts
from slopgate.cli.parsers_bundle import add_bundle_parsers
from slopgate.constants import PLATFORM_CLAUDE, PLATFORM_CODEX, PLATFORM_CURSOR, PLATFORM_OPENCODE

START_TOKEN = f"slopgate:managed:start id={MANAGED_BLOCK_ID}"
ROUTING_SOURCE = "slopgate.resources.bundle/shared/prompt-fragments/slopgate-skill-routing.md"
SAFE_TEXT = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters="\r"),
    max_size=200,
).filter(
    lambda value: START_TOKEN not in value
    and f"slopgate:managed:end id={MANAGED_BLOCK_ID}" not in value
)


def test_update_managed_block_appends_without_clobbering_existing_text() -> None:
    original = "# Existing instructions\n\nKeep this.\n"

    updated = update_managed_block(
        original,
        managed_content="Use slopgate-test-extender for test-integrity findings.\n",
        source_label=ROUTING_SOURCE,
    )

    assert original in updated, "preexisting prompt text must remain intact"
    assert START_TOKEN in updated, "managed routing block should be appended"
    assert "Use slopgate-test-extender" in updated, "new routing text should be present"
    assert updated.count(START_TOKEN) == 1, "sync should create one managed block"


@given(original=SAFE_TEXT, managed_content=SAFE_TEXT)
def test_update_managed_block_preserves_unmanaged_content_property(
    original: str,
    managed_content: str,
) -> None:
    updated = update_managed_block(
        original,
        managed_content=managed_content,
        source_label=ROUTING_SOURCE,
    )

    assert original in updated, "unmanaged prompt content should survive append"
    assert managed_content.rstrip() in updated, "managed content should be embedded"
    assert updated.count(START_TOKEN) == 1, "append should create exactly one block"


def test_update_managed_block_replaces_only_the_managed_region() -> None:
    first = update_managed_block(
        "# Existing\n",
        managed_content="old routing\n",
        source_label="source.md",
    )

    second = update_managed_block(
        first,
        managed_content="new routing\n",
        source_label="source.md",
    )

    assert "# Existing" in second, "unmanaged heading should stay unchanged"
    assert "new routing" in second, "new managed content should be written"
    assert "old routing" not in second, "old managed content should be replaced"
    assert second.count(START_TOKEN) == 1, "replace should preserve one managed block"


def test_remove_managed_block_preserves_preexisting_prefix_and_suffix() -> None:
    original = "# Existing\n\nKeep this.\n"
    with_block = update_managed_block(
        original,
        managed_content="managed routing\n",
        source_label=ROUTING_SOURCE,
    )
    prompt_with_suffix = f"{with_block}\n## User notes\nNever clobber me.\n"

    removed = remove_managed_block(prompt_with_suffix)

    assert "managed routing" not in removed, "managed block body should be removed"
    assert START_TOKEN not in removed, "managed start marker should be removed"
    assert "# Existing\n\nKeep this.\n" in removed, "preexisting prefix survives"
    assert "## User notes\nNever clobber me.\n" in removed, "preexisting suffix survives"


@given(prefix=SAFE_TEXT, suffix=SAFE_TEXT)
def test_remove_managed_block_preserves_unmanaged_content_property(
    prefix: str,
    suffix: str,
) -> None:
    managed = update_managed_block(
        prefix,
        managed_content="managed routing\n",
        source_label=ROUTING_SOURCE,
    )
    original = f"{managed}{suffix}"

    removed = remove_managed_block(original)

    assert prefix in removed, "remove should preserve unmanaged prefix text"
    assert suffix in removed, "remove should preserve unmanaged suffix text"
    assert START_TOKEN not in removed, "remove should clear the managed marker"


def test_remove_managed_block_is_noop_without_managed_region() -> None:
    original = "# Existing\n\nNo Slopgate managed prompt block here.\n"

    assert remove_managed_block(original) == original, "remove without block should not rewrite"


def test_update_managed_block_rejects_duplicate_regions() -> None:
    start, end = managed_block_markers("source.md", "0" * 64)
    malformed = f"{start}\none\n{end}\n{start}\ntwo\n{end}\n"

    with pytest.raises(ValueError, match="multiple managed blocks"):
        update_managed_block(malformed, managed_content="new\n", source_label="source.md")


def test_sync_skill_routing_prompts_uses_home_and_preserves_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    claude_file = tmp_path / ".claude" / "CLAUDE.md"
    claude_file.parent.mkdir(parents=True)
    claude_file.write_text("# Claude local rules\n\nDo not clobber.\n", encoding="utf-8")

    results = sync_skill_routing_prompts(platforms=(PLATFORM_CLAUDE,), scope="user")

    assert [result.path for result in results] == [claude_file], "Claude user target path"
    text = claude_file.read_text(encoding="utf-8")
    assert "Do not clobber." in text, "preexisting Claude prompt should be preserved"
    assert "slopgate-test-extender" in text, "routing fragment should name test skill"
    assert "/home/trav/.openclaw" not in text, "fragment must not hardcode repo checkout"


def test_sync_skill_routing_prompts_remove_preserves_preexisting_file_content(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    claude_file = tmp_path / ".claude" / "CLAUDE.md"
    claude_file.parent.mkdir(parents=True)
    preexisting = "# Claude local rules\n\nKeep my local rule.\n"
    claude_file.write_text(preexisting, encoding="utf-8")
    sync_skill_routing_prompts(platforms=(PLATFORM_CLAUDE,), scope="user")

    results = sync_skill_routing_prompts(
        platforms=(PLATFORM_CLAUDE,),
        scope="user",
        options=PromptSyncOptions(remove=True),
    )

    assert results[0].changed is True, "remove should report a changed prompt file"
    assert claude_file.read_text(encoding="utf-8") == preexisting, (
        "remove should restore the preexisting unmanaged prompt content"
    )


def _dry_run_remove_snapshot(tmp_path: Path) -> tuple[bool, str, str]:
    claude_file = tmp_path / ".claude" / "CLAUDE.md"
    claude_file.parent.mkdir(parents=True)
    claude_file.write_text("# Claude local rules\n", encoding="utf-8")
    sync_skill_routing_prompts(platforms=(PLATFORM_CLAUDE,), scope="user")
    before = claude_file.read_text(encoding="utf-8")
    results = sync_skill_routing_prompts(
        platforms=(PLATFORM_CLAUDE,),
        scope="user",
        options=PromptSyncOptions(dry_run=True, remove=True),
    )
    after = claude_file.read_text(encoding="utf-8")
    return results[0].changed, before, after


def test_sync_skill_routing_prompts_remove_dry_run_does_not_modify_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))

    changed, before, after = _dry_run_remove_snapshot(tmp_path)

    assert changed is True, "dry-run remove should report pending change"
    assert after == before, "dry-run remove must not write"


def _sync_twice_in_temp_home(existing: str) -> tuple[bool, bool, str]:
    old_home = os.environ.get("HOME")
    with tempfile.TemporaryDirectory() as raw_tmpdir:
        tmp_path = Path(raw_tmpdir)
        os.environ["HOME"] = str(tmp_path)
        try:
            claude_file = tmp_path / ".claude" / "CLAUDE.md"
            claude_file.parent.mkdir(parents=True)
            claude_file.write_text(existing, encoding="utf-8")
            first = sync_skill_routing_prompts(platforms=(PLATFORM_CLAUDE,), scope="user")
            second = sync_skill_routing_prompts(platforms=(PLATFORM_CLAUDE,), scope="user")
            text = claude_file.read_text(encoding="utf-8")
        finally:
            if old_home is None:
                os.environ.pop("HOME", None)
            else:
                os.environ["HOME"] = old_home
    return first[0].changed, second[0].changed, text


@given(existing=SAFE_TEXT)
def test_sync_skill_routing_prompts_is_idempotent_property(existing: str) -> None:
    first_changed, second_changed, text = _sync_twice_in_temp_home(existing)

    assert first_changed is True, "first sync should append or replace the block"
    assert second_changed is False, "second sync should be idempotent"
    assert existing in text, "sync should preserve arbitrary unmanaged prompt text"
    assert text.count(START_TOKEN) == 1, "idempotent sync keeps one block"


def test_sync_skill_routing_prompts_deduplicates_project_agents_file(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()

    results = sync_skill_routing_prompts(
        platforms=(PLATFORM_OPENCODE, PLATFORM_CODEX, PLATFORM_CURSOR),
        scope="project",
        project_root=project_root,
    )

    assert [result.path for result in results] == [project_root / "AGENTS.md"], "deduped file"
    text = (project_root / "AGENTS.md").read_text(encoding="utf-8")
    assert text.count(START_TOKEN) == 1, "shared AGENTS.md should get one block"
    assert "slopgate-hygiene-orchestrator" in text, "routing fragment should name skills"


def test_add_bundle_parsers_registers_sync_command_directly() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command")

    add_bundle_parsers(sub)
    args = parser.parse_args(["bundle", "sync-prompts", "--only", PLATFORM_CLAUDE])

    assert args.command == "bundle", "direct parser helper should add bundle command"
    assert args.bundle_command == "sync-prompts", "direct helper should add sync subcommand"
    assert args.only == PLATFORM_CLAUDE, "direct helper should preserve platform choice"
    assert args.func is cmd_bundle_sync_prompts, "direct helper should attach bundle handler"


def test_add_bundle_parsers_registers_uninstall_alias_directly() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command")

    add_bundle_parsers(sub)
    args = parser.parse_args(["bundle", "uninstall-prompts", "--only", PLATFORM_CLAUDE])

    assert args.command == "bundle", "direct parser helper should add bundle command"
    assert args.bundle_command == "uninstall-prompts", "direct helper should add uninstall alias"
    assert args.only == PLATFORM_CLAUDE, "alias should preserve platform choice"
    assert args.remove is True, "alias should default to remove mode"
    assert args.func is cmd_bundle_sync_prompts, "alias should use bundle prompt handler"


def test_bundle_sync_prompts_parser_is_registered() -> None:
    parser = build_parser()
    args = parser.parse_args(
        ["bundle", "sync-prompts", "--dry-run", "--remove", "--only", PLATFORM_CLAUDE]
    )

    assert args.command == "bundle", "top-level command should be bundle"
    assert args.bundle_command == "sync-prompts", "subcommand should be sync-prompts"
    assert args.only == PLATFORM_CLAUDE, "--only should preserve selected platform"
    assert args.dry_run is True, "--dry-run should be parsed"
    assert args.remove is True, "--remove should be parsed"
    assert callable(args.func), "parser should attach command handler"


def test_bundle_uninstall_prompts_alias_parser_is_registered() -> None:
    parser = build_parser()
    args = parser.parse_args(
        ["bundle", "uninstall-prompts", "--dry-run", "--only", PLATFORM_CLAUDE]
    )

    assert args.command == "bundle", "top-level command should be bundle"
    assert args.bundle_command == "uninstall-prompts", "subcommand should be uninstall-prompts"
    assert args.only == PLATFORM_CLAUDE, "--only should preserve selected platform"
    assert args.dry_run is True, "--dry-run should be parsed"
    assert args.remove is True, "alias should default to remove mode"
    assert callable(args.func), "parser should attach command handler"
