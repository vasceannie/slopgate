from __future__ import annotations

from slopgate._types import is_object_dict

from tests.support import SKIP_UNIX_ONLY
from tests.engine.enforcement_modes_support import (
    _evaluate_post_edit_lint_for_touched_source,
    _repo_with_touched_source_coverage,
)
from tests.test_engine import (
    MonkeyPatch,
    Path,
    assert_worktree_marker_copied,
    disable_default_post_edit_quality,
    enable_failing_post_edit_quality_command,
    evaluate_post_edit_bash,
    evaluate_pretool_bash,
    evaluate_pretool_write,
    init_git_worktree,
    post_edit_bash_payload,
    pretool_bash_payload,
    pretool_write_payload,
    strict_rule_id_sets,
    write_config_from_defaults,
    write_slopgate,
    write_skip_paths_config,
    assert_blocked,
    evaluate_payload,
    finding_ids,
)


class TestEnforcementModes:
    def test_outside_repo_runs_safety_only(self, tmp_path: Path) -> None:
        outside = tmp_path / "outside"
        outside.mkdir(parents=True)

        benign = evaluate_payload(
            pretool_write_payload(outside, "src/app.py", "print('ok')\n")
        )
        assert "PY-CODE-001" not in finding_ids(benign)

        protected = evaluate_payload(
            pretool_write_payload(outside, "Makefile", "all:\n")
        )
        assert "BUILTIN-PROTECTED-PATHS" in finding_ids(protected)

    def test_enrolled_repo_runs_full_strict_stack(self, tmp_path: Path) -> None:
        repo = write_slopgate(tmp_path / "repo_strict")
        always_on_ids, strict_ids = strict_rule_id_sets(repo)

        assert "BUILTIN-PROTECTED-PATHS" in always_on_ids, (
            "always-on rule set should retain protected path enforcement"
        )
        assert "GIT-001" in strict_ids, (
            "repo-strict rule set should include git bypass protection"
        )
        assert any(rule_id.startswith("PY-CODE-") for rule_id in strict_ids), (
            f"repo-strict rule set should include Python code rules, got {strict_ids}"
        )
        assert any(rule_id.startswith("PY-") for rule_id in strict_ids), (
            f"repo-strict rule set should include Python quality/test rules, got {strict_ids}"
        )

    def test_enrolled_repo_subdirectory_stays_repo_strict(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo_strict_subdir"
        subdir = repo / "src"
        subdir.mkdir(parents=True)
        _ = (repo / "slopgate.toml").write_text(
            "[slopgate]\nenabled = true\n", encoding="utf-8"
        )

        candidate = evaluate_payload(
            pretool_bash_payload(subdir, 'git commit -n -m "skip checks"')
        )
        assert "GIT-001" in finding_ids(candidate)

    def test_worktree_auto_enrolls_from_repo_marker(self, tmp_path: Path) -> None:
        repo, worktree = init_git_worktree(tmp_path)
        worktree_marker = worktree / "slopgate.toml"
        worktree_marker.unlink()

        result = evaluate_payload(
            pretool_bash_payload(worktree, 'git commit -n -m "skip checks"')
        )

        assert_worktree_marker_copied(repo, worktree_marker)
        assert "GIT-001" in finding_ids(result)

    @SKIP_UNIX_ONLY
    def test_enrolled_repo_with_noqualitygate_is_relaxed(self, tmp_path: Path) -> None:
        repo = write_slopgate(tmp_path / "repo_relaxed")
        _ = (repo / ".noslopgate").write_text("", encoding="utf-8")

        strict_candidate = evaluate_pretool_bash(repo, 'git commit -n -m "skip checks"')
        assert "GIT-001" not in finding_ids(strict_candidate)

        safety_candidate = evaluate_pretool_write(repo, "/etc/passwd", "root:x:0:0\n")
        assert "GLOBAL-BUILTIN-SYSTEM-PROTECTION" in finding_ids(safety_candidate)

    def test_skip_paths_suppresses_strict_not_safety(
        self, tmp_path: Path, monkeypatch: MonkeyPatch
    ) -> None:
        repo = write_slopgate(tmp_path / "repo_skip")
        write_skip_paths_config(tmp_path, monkeypatch, repo)

        strict_candidate = evaluate_pretool_bash(repo, 'git commit -n -m "skip checks"')
        assert "GIT-001" not in finding_ids(strict_candidate)

        safety_candidate = evaluate_pretool_write(repo, "Makefile", "all:\n")
        assert "BUILTIN-PROTECTED-PATHS" in finding_ids(safety_candidate)

    def test_post_edit_quality_runs_from_repo_root(
        self, tmp_path: Path, monkeypatch: MonkeyPatch
    ) -> None:
        repo = write_slopgate(tmp_path / "repo_quality_cwd")
        subdir = repo / "nested"
        subdir.mkdir(parents=True)
        write_config_from_defaults(
            tmp_path,
            monkeypatch,
            enable_failing_post_edit_quality_command,
        )

        result = evaluate_post_edit_bash(subdir)
        assert "QUALITY-POST-001" in finding_ids(result)
        finding = next(
            item for item in result.findings if item.rule_id == "QUALITY-POST-001"
        )
        assert finding.message is not None
        assert str(repo.resolve()) in finding.message

    def test_post_edit_quality_skips_readonly_shell_probe_outside_repo(
        self, tmp_path: Path, monkeypatch: MonkeyPatch
    ) -> None:
        repo = write_slopgate(tmp_path / "repo_quality_readonly_shell")
        asset = tmp_path / "canvas" / "forcedash" / "assets" / "index-rTQrJY9a.js"
        asset.parent.mkdir(parents=True)
        _ = asset.write_text("const TopRules = 'ComposedChart';\n", encoding="utf-8")

        def fail_js_quality(defaults: dict[str, object]) -> None:
            post_edit_quality = defaults["post_edit_quality"]
            assert is_object_dict(post_edit_quality)
            post_edit_quality["enabled"] = True
            post_edit_quality["block_on_failure"] = True
            post_edit_quality["commands_by_language"] = {"js_ts": ["false"]}

        write_config_from_defaults(tmp_path, monkeypatch, fail_js_quality)

        result = evaluate_post_edit_bash(
            repo,
            f'if grep -c "Top Pressure Rules\\|Pareto\\|TopRules\\|ComposedChart" {asset} 2>&1; '
            'then echo "FOUND"; else echo "NOT FOUND"; fi',
        )

        assert "QUALITY-POST-001" not in finding_ids(result)

    def test_post_edit_quality_skips_npm_when_no_package_json(
        self, tmp_path: Path, monkeypatch: MonkeyPatch
    ) -> None:
        """QUALITY-POST-001 must not run npm quality commands when no
        package.json exists anywhere in the candidate path ancestry or
        repo root. This prevents the Bash wrapper from running
        ``npm run lint`` from ``/`` during read-only probes such as
        Playwright browser geometry checks."""
        repo = write_slopgate(tmp_path / "repo_no_package_json")

        def enable_npm_quality(defaults: dict[str, object]) -> None:
            post_edit_quality = defaults["post_edit_quality"]
            assert is_object_dict(post_edit_quality)
            post_edit_quality["enabled"] = True
            post_edit_quality["block_on_failure"] = True
            post_edit_quality["commands_by_language"] = {"js_ts": ["npm run lint"]}

        write_config_from_defaults(tmp_path, monkeypatch, enable_npm_quality)

        # A .js file outside the repo ensures languages includes js_ts
        # but no package.json exists in the path ancestry or repo root.
        asset = tmp_path / "canvas" / "assets" / "index-rTQrJY9a.js"
        asset.parent.mkdir(parents=True)
        _ = asset.write_text("const TopRules = 'ComposedChart';\n")

        result = evaluate_post_edit_bash(
            repo,
            f"npx playwright open {asset} 2>&1 || true",
        )

        # Must not fire QUALITY-POST-001 — npm run lint would fail
        # from '/' with no package.json in scope.
        assert "QUALITY-POST-001" not in finding_ids(result)

    def test_post_edit_quality_runs_npm_when_package_json_exists(
        self, tmp_path: Path, monkeypatch: MonkeyPatch
    ) -> None:
        """QUALITY-POST-001 must fire for mutating bash in an npm project
        that has a package.json."""
        repo = tmp_path / "repo_with_package_json"
        write_slopgate(repo)
        _ = (repo / "package.json").write_text('{"scripts": {"lint": "exit 1"}}\n')

        def enable_npm_quality(defaults: dict[str, object]) -> None:
            post_edit_quality = defaults["post_edit_quality"]
            assert is_object_dict(post_edit_quality)
            post_edit_quality["enabled"] = True
            post_edit_quality["block_on_failure"] = True
            post_edit_quality["commands_by_language"] = {"js_ts": ["npm run lint"]}

        write_config_from_defaults(tmp_path, monkeypatch, enable_npm_quality)

        result = evaluate_payload(
            post_edit_bash_payload(
                repo,
                "echo 'export const x = 1;' > app.js",
            )
        )
        nm_findings = [f for f in result.findings if f.rule_id == "QUALITY-POST-001"]
        assert nm_findings, (
            "Mutating bash in an npm project with package.json should "
            f"fire QUALITY-POST-001; got {finding_ids(result)}"
        )

    def test_repo_toml_can_enable_post_edit_quality(
        self, tmp_path: Path, monkeypatch: MonkeyPatch
    ) -> None:
        repo = write_slopgate(
            tmp_path / "repo_quality_gate_runtime",
            (
                "[slopgate]\n"
                "enabled = true\n\n"
                "[post_edit_quality]\n"
                "enabled = true\n"
                "block_on_failure = true\n\n"
                "[post_edit_quality.commands_by_language]\n"
                'python = ["false"]\n'
            ),
        )
        write_config_from_defaults(
            tmp_path, monkeypatch, disable_default_post_edit_quality
        )

        result = evaluate_payload(post_edit_bash_payload(repo))
        assert "QUALITY-POST-001" in finding_ids(result)

    def test_post_edit_lint_rule_reports_touched_file_issues(
        self, tmp_path: Path
    ) -> None:
        repo = tmp_path / "repo_lint_touched"
        tests_dir = repo / "tests"
        tests_dir.mkdir(parents=True)
        _ = (repo / "slopgate.toml").write_text(
            "[slopgate]\nenabled = true\n", encoding="utf-8"
        )
        _ = (tests_dir / "test_smell.py").write_text(
            "def test_smell():\n    x = 1\n",
            encoding="utf-8",
        )
        payload = {
            "session_id": "t",
            "cwd": str(repo),
            "hook_event_name": "PostToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "cat tests/test_smell.py"},
        }
        result = evaluate_payload(payload)
        assert "QUALITY-LINT-001" in finding_ids(result)
        assert_blocked(result, "QUALITY-LINT-001")

    def test_post_edit_lint_uses_suite_tests_for_touched_source_coverage(
        self, tmp_path: Path
    ) -> None:
        repo = _repo_with_touched_source_coverage(tmp_path)
        result = _evaluate_post_edit_lint_for_touched_source(repo)

        assert "QUALITY-LINT-001" not in finding_ids(result), (
            "touched-source lint must not ignore existing tests and invent 0% static coverage"
        )

    def test_posttool_ast_health_resolves_relative_paths_from_cwd(
        self, tmp_path: Path
    ) -> None:
        repo = tmp_path / "repo_ast_posttool"
        nested = repo / "nested"
        nested.mkdir(parents=True)
        _ = (repo / "slopgate.toml").write_text(
            "[slopgate]\nenabled = true\n", encoding="utf-8"
        )
        _ = (nested / "bad.py").write_text("def broken(:\n    pass\n", encoding="utf-8")
        payload = {
            "session_id": "t",
            "cwd": str(nested),
            "hook_event_name": "PostToolUse",
            "tool_name": "Edit",
            "tool_input": {
                "file_path": "bad.py",
                "content": "def broken(:\n    pass\n",
            },
            "tool_response": {"filePath": "bad.py", "success": True},
        }
        result = evaluate_payload(payload)
        ast_findings = [f for f in result.findings if f.rule_id == "PY-AST-001"]
        assert ast_findings
        assert ast_findings[0].metadata.get("kind") == "parse_error"

    def test_posttool_bash_glob_does_not_trigger_ast_read_error(
        self,
        tmp_path: Path,
    ) -> None:
        repo = tmp_path / "repo_ast_glob_posttool"
        repo.mkdir(parents=True)
        _ = (repo / "slopgate.toml").write_text(
            "[slopgate]\nenabled = true\n",
            encoding="utf-8",
        )
        payload = {
            "session_id": "t",
            "cwd": str(repo),
            "hook_event_name": "PostToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "python -m py_compile *.py"},
        }
        result = evaluate_payload(payload)
        ast_findings = [f for f in result.findings if f.rule_id == "PY-AST-001"]
        assert not ast_findings
