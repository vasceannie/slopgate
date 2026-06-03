from __future__ import annotations

from tests.test_engine import (
    MonkeyPatch,
    Path,
    _assert_worktree_marker_copied,
    _disable_default_post_edit_quality,
    _enable_failing_post_edit_quality_command,
    _evaluate_post_edit_bash,
    _evaluate_pretool_bash,
    _evaluate_pretool_write,
    _init_git_worktree,
    _post_edit_bash_payload,
    _pretool_bash_payload,
    _pretool_delete_payload,
    _pretool_write_payload,
    _strict_rule_id_sets,
    _write_config_from_defaults,
    _write_quality_gate,
    _write_skip_paths_config,
    assert_blocked,
    assert_denied_by,
    evaluate_payload,
    finding_ids,
)


def _repo_with_touched_source_coverage(tmp_path: Path) -> Path:
    repo = tmp_path / "repo_lint_static_refs"
    src_dir = repo / "src" / "pkg"
    tests_dir = repo / "tests"
    src_dir.mkdir(parents=True)
    tests_dir.mkdir(parents=True)
    _ = (repo / "quality_gate.toml").write_text(
        "[quality_gate]\nenabled = true\n", encoding="utf-8"
    )
    _ = (src_dir / "__init__.py").write_text("", encoding="utf-8")
    _ = (src_dir / "config.py").write_text(
        "class SessionConfig:\n    pass\n",
        encoding="utf-8",
    )
    _ = (tests_dir / "test_config.py").write_text(
        "from pkg.config import SessionConfig\n\n"
        "def test_config_reference():\n"
        "    assert SessionConfig() is not None\n",
        encoding="utf-8",
    )
    return repo


def _evaluate_post_edit_lint_for_touched_source(repo: Path) -> object:
    payload = {
        "session_id": "t",
        "cwd": str(repo),
        "hook_event_name": "PostToolUse",
        "tool_name": "Edit",
        "tool_input": {"file_path": "src/pkg/config.py"},
        "tool_response": {"filePath": "src/pkg/config.py", "success": True},
    }
    return evaluate_payload(payload)


class TestEnforcementModes:
    def test_outside_repo_runs_safety_only(self, tmp_path: Path) -> None:
        outside = tmp_path / "outside"
        outside.mkdir(parents=True)

        benign = evaluate_payload(
            _pretool_write_payload(outside, "src/app.py", "print('ok')\n")
        )
        assert "PY-CODE-001" not in finding_ids(benign)

        protected = evaluate_payload(_pretool_write_payload(outside, "Makefile", "all:\n"))
        assert "BUILTIN-PROTECTED-PATHS" in finding_ids(protected)

    def test_enrolled_repo_runs_full_strict_stack(self, tmp_path: Path) -> None:
        repo = _write_quality_gate(tmp_path / "repo_strict")
        always_on_ids, strict_ids = _strict_rule_id_sets(repo)

        assert "BUILTIN-PROTECTED-PATHS" in always_on_ids, (
            "always-on rule set should retain protected path enforcement"
        )
        assert "GIT-001" in strict_ids, "repo-strict rule set should include git bypass protection"
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
        _ = (repo / "quality_gate.toml").write_text(
            "[quality_gate]\nenabled = true\n", encoding="utf-8"
        )

        candidate = evaluate_payload(
            _pretool_bash_payload(subdir, 'git commit -n -m "skip checks"')
        )
        assert "GIT-001" in finding_ids(candidate)

    def test_worktree_auto_enrolls_from_repo_marker(self, tmp_path: Path) -> None:
        repo, worktree = _init_git_worktree(tmp_path)
        worktree_marker = worktree / "quality_gate.toml"
        worktree_marker.unlink()

        result = evaluate_payload(
            _pretool_bash_payload(worktree, 'git commit -n -m "skip checks"')
        )

        _assert_worktree_marker_copied(repo, worktree_marker)
        assert "GIT-001" in finding_ids(result)

    def test_enrolled_repo_with_noqualitygate_is_relaxed(self, tmp_path: Path) -> None:
        repo = _write_quality_gate(tmp_path / "repo_relaxed")
        _ = (repo / ".noqualitygate").write_text("", encoding="utf-8")

        strict_candidate = _evaluate_pretool_bash(repo, 'git commit -n -m "skip checks"')
        assert "GIT-001" not in finding_ids(strict_candidate)

        safety_candidate = _evaluate_pretool_write(repo, "/etc/passwd", "root:x:0:0\n")
        assert "GLOBAL-BUILTIN-SYSTEM-PROTECTION" in finding_ids(safety_candidate)

    def test_skip_paths_suppresses_strict_not_safety(
        self, tmp_path: Path, monkeypatch: MonkeyPatch
    ) -> None:
        repo = _write_quality_gate(tmp_path / "repo_skip")
        _write_skip_paths_config(tmp_path, monkeypatch, repo)

        strict_candidate = _evaluate_pretool_bash(repo, 'git commit -n -m "skip checks"')
        assert "GIT-001" not in finding_ids(strict_candidate)

        safety_candidate = _evaluate_pretool_write(repo, "Makefile", "all:\n")
        assert "BUILTIN-PROTECTED-PATHS" in finding_ids(safety_candidate)

    def test_post_edit_quality_runs_from_repo_root(self, tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
        repo = _write_quality_gate(tmp_path / "repo_quality_cwd")
        subdir = repo / "nested"
        subdir.mkdir(parents=True)
        _write_config_from_defaults(
            tmp_path,
            monkeypatch,
            _enable_failing_post_edit_quality_command,
        )

        result = _evaluate_post_edit_bash(subdir)
        assert "QUALITY-POST-001" in finding_ids(result)
        finding = next(item for item in result.findings if item.rule_id == "QUALITY-POST-001")
        assert finding.message is not None
        assert str(repo.resolve()) in finding.message

    def test_repo_toml_can_enable_post_edit_quality(
        self, tmp_path: Path, monkeypatch: MonkeyPatch
    ) -> None:
        repo = _write_quality_gate(
            tmp_path / "repo_quality_gate_runtime",
            (
                "[quality_gate]\n"
                "enabled = true\n\n"
                "[post_edit_quality]\n"
                "enabled = true\n"
                "block_on_failure = true\n\n"
                "[post_edit_quality.commands_by_language]\n"
                "python = [\"false\"]\n"
            ),
        )
        _write_config_from_defaults(
            tmp_path, monkeypatch, _disable_default_post_edit_quality
        )

        result = evaluate_payload(_post_edit_bash_payload(repo))
        assert "QUALITY-POST-001" in finding_ids(result)

    def test_post_edit_lint_rule_reports_touched_file_issues(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo_lint_touched"
        tests_dir = repo / "tests"
        tests_dir.mkdir(parents=True)
        _ = (repo / "quality_gate.toml").write_text(
            "[quality_gate]\nenabled = true\n", encoding="utf-8"
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
        _ = (repo / "quality_gate.toml").write_text(
            "[quality_gate]\nenabled = true\n", encoding="utf-8"
        )
        _ = (nested / "bad.py").write_text("def broken(:\n    pass\n", encoding="utf-8")
        payload = {
            "session_id": "t",
            "cwd": str(nested),
            "hook_event_name": "PostToolUse",
            "tool_name": "Edit",
            "tool_input": {"file_path": "bad.py", "content": "def broken(:\n    pass\n"},
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
        _ = (repo / "quality_gate.toml").write_text(
            "[quality_gate]\nenabled = true\n",
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

