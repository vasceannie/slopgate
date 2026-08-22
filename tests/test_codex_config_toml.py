from __future__ import annotations

from pathlib import Path

import pytest

from slopgate.installer._codex import enable_codex_hooks_toml
from slopgate.installer._shared import UnsafeInstallPathError


class TestEnableCodexHooksToml:
    def test_creates_features_section_when_config_does_not_exist(
        self, tmp_path: Path
    ) -> None:
        config_path = tmp_path / "config_codex_not_exists.toml"
        enable_codex_hooks_toml(config_path)
        content = config_path.read_text(encoding="utf-8")
        assert content.strip() == "[features]\nhooks = true", (
            f"Expected hooks feature flag, got: {content!r}"
        )

    def test_creates_features_section_when_config_exists_no_features(
        self, tmp_path: Path
    ) -> None:
        config_path = tmp_path / "config_codex_other_sections.toml"
        config_path.write_text("[other]\nkey = 1\n", encoding="utf-8")
        enable_codex_hooks_toml(config_path)
        content = config_path.read_text(encoding="utf-8")
        assert "[other]" in content, "Existing sections should be preserved"
        assert "[features]" in content, "Missing [features] should be appended"
        assert "hooks = true" in content, "hooks flag must be enabled"

    def test_sets_hooks_true_when_hooks_false(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config_codex_hooks_false.toml"
        config_path.write_text("[features]\nhooks = false\n", encoding="utf-8")
        enable_codex_hooks_toml(config_path)
        content = config_path.read_text(encoding="utf-8")
        assert "hooks = true" in content, (
            f"hooks should be set to true, got: {content!r}"
        )

    def test_migrates_codex_hooks_to_hooks(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config_codex_legacy.toml"
        config_path.write_text("[features]\ncodex_hooks = false\n", encoding="utf-8")
        enable_codex_hooks_toml(config_path)
        content = config_path.read_text(encoding="utf-8")
        assert "hooks = true" in content, (
            f"should replace codex_hooks with hooks = true, got: {content!r}"
        )
        assert "codex_hooks" not in content, (
            f"legacy codex_hooks key should be removed, got: {content!r}"
        )

    def test_removes_multiple_codex_hooks_entries(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config_codex_multi_legacy.toml"
        config_path.write_text(
            "[features]\ncodex_hooks = false\ncodex_hooks = true\n",
            encoding="utf-8",
        )
        enable_codex_hooks_toml(config_path)
        content = config_path.read_text(encoding="utf-8")
        assert "hooks = true" in content, f"should add hooks = true, got: {content!r}"
        assert content.count("codex_hooks") == 0, (
            f"all codex_hooks entries should be removed, got: {content!r}"
        )

    def test_inserts_hooks_when_features_is_last_section(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config_codex_last_feature.toml"
        config_path.write_text("[other]\nkey = 1\n[features]\n", encoding="utf-8")
        enable_codex_hooks_toml(config_path)
        content = config_path.read_text(encoding="utf-8")
        assert "hooks = true" in content, (
            f"should add hooks flag under [features] as last section, got: {content!r}"
        )

    def test_only_modifies_features_section(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config_codex_hooks_before_features.toml"
        config_path.write_text("hooks = false\n[features]\n[other]\n", encoding="utf-8")
        enable_codex_hooks_toml(config_path)
        content = config_path.read_text(encoding="utf-8")
        lines = content.splitlines()
        features_idx = next(
            i for i, line in enumerate(lines) if line.strip() == "[features]"
        )
        hooks_line_idx = next(
            (i for i, line in enumerate(lines) if "hooks = true" in line), None
        )
        assert hooks_line_idx is not None, "Expected a hooks line in the output"
        assert hooks_line_idx > features_idx, (
            f"hooks = true should be inside [features], not before it. Lines: {lines}"
        )

    def test_preserves_comment_in_hooks_line(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config_codex_comment.toml"
        config_path.write_text(
            "[features]\nhooks = false # disabled for now\n", encoding="utf-8"
        )
        enable_codex_hooks_toml(config_path)
        content = config_path.read_text(encoding="utf-8")
        assert "hooks = true" in content, (
            f"should set hooks = true preserving comment, got: {content!r}"
        )

    def test_refuses_leaf_symlink_and_preserves_external(self, tmp_path: Path) -> None:
        outside = tmp_path / "outside" / "secret.toml"
        outside.parent.mkdir()
        outside.write_text("KEEP = true\n", encoding="utf-8")
        config_path = tmp_path / "config.toml"
        config_path.symlink_to(outside)
        with pytest.raises(UnsafeInstallPathError, match="symlink"):
            enable_codex_hooks_toml(config_path)
        assert outside.read_text(encoding="utf-8") == "KEEP = true\n", (
            "TOML leaf symlink writes must not overwrite the external target"
        )
        assert config_path.is_symlink(), "the planted leaf symlink must remain a symlink"
