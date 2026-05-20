from __future__ import annotations

from tests.test_engine import (
    BashBuilder,
    MonkeyPatch,
    Path,
    WriteBuilder,
    _fake_vibeforcer_worktree_git_output,
    _init_git_worktree,
    assert_denied_by,
    assert_not_denied,
    evaluate_payload,
    finding_ids,
    pytest,
    subprocess,
)

class TestTypeScriptRules:
    def test_ts_type_001_any_denied(self, pretool_write: WriteBuilder) -> None:
        code = "function parse(input: any): string {\n  return String(input);\n}\n"
        result = evaluate_payload(pretool_write("src/parser.ts", code))
        assert "TS-TYPE-001" in finding_ids(result)

    def test_ts_type_001_specific_type_allowed(
        self, pretool_write: WriteBuilder
    ) -> None:
        code = "function parse(input: string): number {\n  return parseInt(input);\n}\n"
        result = evaluate_payload(pretool_write("src/parser.ts", code))
        assert "TS-TYPE-001" not in finding_ids(result)

    def test_ts_type_001_array_any_denied(self, pretool_write: WriteBuilder) -> None:
        code = "const values: Array<any> = [];\n"
        result = evaluate_payload(pretool_write("src/parser.ts", code))
        assert "TS-TYPE-001" in finding_ids(result)

    def test_ts_type_001_generic_default_any_denied(
        self, pretool_write: WriteBuilder
    ) -> None:
        code = "type Box<T = any> = { value: T };\n"
        result = evaluate_payload(pretool_write("src/parser.ts", code))
        assert "TS-TYPE-001" in finding_ids(result)

    def test_ts_type_002_as_any_denied(self, pretool_write: WriteBuilder) -> None:
        code = "const x = value as any;\n"
        result = evaluate_payload(pretool_write("src/util.ts", code))
        assert "TS-TYPE-002" in finding_ids(result)

    def test_ts_type_002_as_unknown_denied(self, pretool_write: WriteBuilder) -> None:
        code = "const x = value as unknown;\n"
        result = evaluate_payload(pretool_write("src/util.tsx", code))
        assert "TS-TYPE-002" in finding_ids(result)

    def test_ts_type_002_as_array_any_denied(self, pretool_write: WriteBuilder) -> None:
        code = "const x = value as Array<any>;\n"
        result = evaluate_payload(pretool_write("src/util.ts", code))
        assert "TS-TYPE-002" in finding_ids(result)

    def test_ts_type_002_as_string_allowed(self, pretool_write: WriteBuilder) -> None:
        code = "const x = value as string;\n"
        result = evaluate_payload(pretool_write("src/util.ts", code))
        assert "TS-TYPE-002" not in finding_ids(result)

    def test_ts_lint_001_shell_ignore_inject(self, pretool_bash: BashBuilder) -> None:
        result = evaluate_payload(
            pretool_bash("sed -i '1i // @ts-ignore' src/broken.ts")
        )
        assert "TS-LINT-001" in finding_ids(result)

    def test_ts_lint_001_shell_eslint_disable(self, pretool_bash: BashBuilder) -> None:
        result = evaluate_payload(
            pretool_bash("echo '// eslint-disable-next-line' >> src/util.tsx")
        )
        assert "TS-LINT-001" in finding_ids(result)

class TestRustRules:
    def test_rs_quality_001_todo_denied(self, pretool_write: WriteBuilder) -> None:
        code = 'fn main() {\n    // TODO: fix this\n    println!("hello");\n}\n'
        result = evaluate_payload(pretool_write("src/main.rs", code))
        assert "RS-QUALITY-001" in finding_ids(result)

    def test_rs_quality_001_fixme_denied(self, pretool_write: WriteBuilder) -> None:
        code = "// FIXME: handle error\nfn run() {}\n"
        result = evaluate_payload(pretool_write("src/lib.rs", code))
        assert "RS-QUALITY-001" in finding_ids(result)

    def test_rs_quality_001_normal_comment_ok(
        self, pretool_write: WriteBuilder
    ) -> None:
        code = "// This function handles parsing.\nfn parse() {}\n"
        result = evaluate_payload(pretool_write("src/lib.rs", code))
        assert "RS-QUALITY-001" not in finding_ids(result)

    def test_rs_quality_003_magic_number_denied(
        self, pretool_write: WriteBuilder
    ) -> None:
        code = "fn retry() {\n    if attempts > 1000 {\n        return;\n    }\n}\n"
        result = evaluate_payload(pretool_write("src/retry.rs", code))
        assert "RS-QUALITY-003" in finding_ids(result)

    def test_rs_quality_003_const_ok(self, pretool_write: WriteBuilder) -> None:
        code = "const MAX_RETRIES: u32 = 1000;\n"
        result = evaluate_payload(pretool_write("src/retry.rs", code))
        assert "RS-QUALITY-003" not in finding_ids(result)

class TestConfigProtection:
    def test_config_002_write_denied(self, pretool_write: WriteBuilder) -> None:
        result = evaluate_payload(
            pretool_write(".claude/hook-layer/config.json", '{"regex_rules": []}')
        )
        ids = finding_ids(result)
        assert "CONFIG-002" in ids or "GLOBAL-BUILTIN-HOOK-INFRA-EXEC" in ids

    def test_config_003_sed_denied(self, pretool_bash: BashBuilder) -> None:
        result = evaluate_payload(
            pretool_bash("sed -i 's/true/false/' .claude/hook-layer/config.json")
        )
        ids = finding_ids(result)
        assert "CONFIG-003" in ids or "GLOBAL-BUILTIN-HOOK-INFRA-EXEC" in ids

    def test_config_003_tee_denied(self, pretool_bash: BashBuilder) -> None:
        result = evaluate_payload(
            pretool_bash("echo '{}' | tee .claude/hook-layer/config.json")
        )
        ids = finding_ids(result)
        assert "CONFIG-003" in ids or "GLOBAL-BUILTIN-HOOK-INFRA-EXEC" in ids

    def test_config_003_cat_allowed(self, pretool_bash: BashBuilder) -> None:
        result = evaluate_payload(pretool_bash("cat .claude/hook-layer/config.json"))
        assert "CONFIG-003" not in finding_ids(result)

class TestHookInfraWorktreeException:
    def test_worktree_exception_requires_vibeforcer_repo_and_non_default_branch(
        self, tmp_path: Path, pretool_write: WriteBuilder, monkeypatch: MonkeyPatch
    ) -> None:
        repo, worktree = _init_git_worktree(tmp_path)

        def fake_git_output(
            args: list[str], cwd: Path | None = None, timeout: int = 3
        ) -> str | None:
            if args[-3:] == ["remote", "get-url", "origin"]:
                return "https://lab.baked.rocks/claude/vibeforcer.git"
            result = subprocess.run(
                args,
                cwd=str(cwd) if cwd is not None else None,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            return result.stdout.strip() or None

        monkeypatch.setattr(
            "vibeforcer.rules.stop_rules._git_output",
            fake_git_output,
        )

        result = evaluate_payload(
            pretool_write(
                ".claude/hooks/run-pretool.sh",
                "echo hi\n",
                cwd=str(worktree),
            )
        )
        assert "GLOBAL-BUILTIN-HOOK-INFRA-EXEC" not in finding_ids(result)
        assert repo.exists()

    def test_worktree_exception_denied_on_default_branch(
        self, tmp_path: Path, pretool_write: WriteBuilder, monkeypatch: MonkeyPatch
    ) -> None:
        _repo, worktree = _init_git_worktree(tmp_path)
        monkeypatch.setattr(
            "vibeforcer.rules.stop_rules._git_output",
            _fake_vibeforcer_worktree_git_output,
        )

        result = evaluate_payload(
            pretool_write(
                ".claude/hooks/run-pretool.sh",
                "echo hi\n",
                cwd=str(worktree),
            )
        )
        assert_denied_by(result, "BUILTIN-PROTECTED-PATHS")
        assert "BUILTIN-PROTECTED-PATHS" in finding_ids(result), (
            "worktree hook exceptions should not apply on non-default branches"
        )

    def test_worktree_exception_denied_for_non_vibeforcer_repo(
        self, tmp_path: Path, pretool_write: WriteBuilder
    ) -> None:
        _repo, worktree = _init_git_worktree(tmp_path)

        result = evaluate_payload(
            pretool_write(
                ".claude/hooks/run-pretool.sh",
                "echo hi\n",
                cwd=str(worktree),
            )
        )
        assert_denied_by(result, "BUILTIN-PROTECTED-PATHS")
        assert "BUILTIN-PROTECTED-PATHS" in finding_ids(result), (
            "worktree hook exceptions should not apply to non-vibeforcer repos"
        )

@pytest.mark.parametrize(
    "command, rule_id",
    [
        ("sed -i 's/off/error/' .eslintrc.json", "FE-LINTER-002"),
        ("echo '{}' | tee prettier.config.js", "FE-LINTER-002"),
        ("sed -i 's/strict/basic/' .flake8", "PY-LINTER-002"),
        ("echo 'line-length = 120' >> ruff.toml", "PY-LINTER-002"),
        ("sed -i 's/strict/basic/' pyrightconfig.json", "PY-LINTER-002"),
        ("echo '[pytest]' >> pytest.ini", "PY-LINTER-002"),
    ],
)
def test_linter_shell_edit_denied(
    pretool_bash: BashBuilder, command: str, rule_id: str
) -> None:
    result = evaluate_payload(pretool_bash(command))
    assert rule_id in finding_ids(result), f"Expected {rule_id} on: {command}"

class TestQAPathRules:
    def test_qa_path_001_write_denied(self, pretool_write: WriteBuilder) -> None:
        result = evaluate_payload(
            pretool_write(
                "src/test/code-quality.test.ts", "describe('quality', () => {});\n"
            )
        )
        assert "QA-PATH-001" in finding_ids(result)

    def test_qa_path_002_sed_denied(self, pretool_bash: BashBuilder) -> None:
        result = evaluate_payload(
            pretool_bash("sed -i 's/strict/lax/' src/test/code-quality.test.ts")
        )
        assert "QA-PATH-002" in finding_ids(result)

    def test_qa_path_004_redirect_denied(self, pretool_bash: BashBuilder) -> None:
        result = evaluate_payload(
            pretool_bash("echo 'pass' >> tests/quality/test_lint.py")
        )
        assert "QA-PATH-004" in finding_ids(result)

    def test_qa_path_004_cat_allowed(self, pretool_bash: BashBuilder) -> None:
        result = evaluate_payload(pretool_bash("cat tests/quality/test_lint.py"))
        assert "QA-PATH-004" not in finding_ids(result)

class TestSearchReminder:
    def test_grep_triggers_reminder(self, pretool_bash: BashBuilder) -> None:
        result = evaluate_payload(pretool_bash("grep -rn 'TODO' src/"))
        assert "REMIND-SEARCH-001" in finding_ids(result)
        assert_not_denied(result)

    def test_ripgrep_no_reminder(self, pretool_bash: BashBuilder) -> None:
        result = evaluate_payload(pretool_bash("rg 'TODO' src/"))
        assert "REMIND-SEARCH-001" not in finding_ids(result)

class TestBaselineWarnings:
    def test_baseline_path_warns(self, pretool_write: WriteBuilder) -> None:
        result = evaluate_payload(pretool_write("baselines.json", '{"rules": {}}\n'))
        assert "WARN-BASELINE-001" in finding_ids(result)

    def test_baseline_shell_edit_warns(self, pretool_bash: BashBuilder) -> None:
        result = evaluate_payload(pretool_bash("sed -i 's/old/new/' baselines.json"))
        assert "WARN-BASELINE-002" in finding_ids(result)

    def test_baseline_cat_no_warn(self, pretool_bash: BashBuilder) -> None:
        result = evaluate_payload(pretool_bash("cat baselines.json"))
        assert "WARN-BASELINE-002" not in finding_ids(result)
