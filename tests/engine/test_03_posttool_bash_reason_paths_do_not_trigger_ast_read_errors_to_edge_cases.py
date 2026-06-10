from __future__ import annotations

from tests.test_engine import (
    BashBuilder,
    EvaluateFn,
    Path,
    WriteBuilder,
    assert_bash_negative_case,
    assert_write_negative_case,
    repo_with_moved_parse_error,
    assert_not_denied,
    evaluate_payload,
    finding_ids,
    pytest,
)

EXC_002_BOUNDARY_CASES = [
    pytest.param(
        "def safe_int(s):\n    try:\n        return int(s)\n    except ValueError:\n        pass\n",
        False,
        id="specific-exception-pass-allowed",
    ),
    pytest.param(
        "def get_item(d, k):\n    try:\n        return d[k]\n    except KeyError:\n        return None\n",
        False,
        id="specific-exception-return-none-allowed",
    ),
    pytest.param(
        (
            "def process(items):\n"
            "    for i in items:\n"
            "        try:\n"
            "            do(i)\n"
            "        except Exception:\n"
            "            continue\n"
        ),
        True,
        id="except-exception-continue-denied",
    ),
    pytest.param(
        (
            "def fetch(url):\n"
            "    try:\n"
            "        return get(url).json()\n"
            "    except Exception:\n"
            "        return None\n"
        ),
        True,
        id="except-exception-return-none-denied",
    ),
    pytest.param(
        "def cleanup():\n    try:\n        os.remove(f)\n    except:\n        pass\n",
        True,
        id="bare-except-pass-denied",
    ),
]


def test_posttool_bash_reason_paths_do_not_trigger_ast_read_errors(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / "slopgate.toml").write_text(
        "[slopgate]\nenabled = true\n",
        encoding="utf-8",
    )
    payload = {
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash",
        "tool_input": {
            "command": (
                'bd close job-hunter-6vc1 --reason="Centralized parsing in '
                "src/sse_parsing.py and cloud agent_stream/sse.py; moved "
                'runtime_lifecycle.py."'
            )
        },
        "cwd": str(repo),
        "session_id": "t",
    }
    result = evaluate_payload(payload)
    assert "PY-AST-001" not in finding_ids(result)


def test_posttool_bash_move_skips_old_missing_path_but_checks_new_path(
    tmp_path: Path,
) -> None:
    repo = repo_with_moved_parse_error(tmp_path)
    payload = {
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "mv src/pkg/worker.py src/pkg/moved/worker.py"},
        "cwd": str(repo),
        "session_id": "t",
    }

    result = evaluate_payload(payload)

    ast_findings = [f for f in result.findings if f.rule_id == "PY-AST-001"]
    assert [(f.metadata.get("path"), f.metadata.get("kind")) for f in ast_findings] == [
        ("src/pkg/moved/worker.py", "parse_error")
    ]


def test_morph_tool_is_edit_like() -> None:
    from slopgate.util.payloads import is_edit_like_tool

    assert is_edit_like_tool("morph")
    assert is_edit_like_tool("morph_edit_file")
    assert is_edit_like_tool("str_replace_editor")


@pytest.mark.parametrize(
    "file_path, content, forbidden_rule",
    [
        pytest.param(
            "src/models/user.py",
            "from dataclasses import dataclass\n\n@dataclass\nclass User:\n    name: str\n    email: str\n",
            None,
            id="clean-python",
        ),
        pytest.param(
            "src/utils/format.ts",
            "export function formatDate(d: Date): string {\n  return d.toISOString();\n}\n",
            None,
            id="clean-typescript",
        ),
        pytest.param(
            "tests/conftest.py",
            "import pytest\n\n@pytest.fixture\ndef client():\n    return TestClient()\n",
            "PY-TEST-004",
            id="conftest-fixture-allowed",
        ),
        pytest.param(
            "src/hook_layer/config.py",
            "enabled_rules = {}\n",
            "BUILTIN-RULEBOOK-SECURITY",
            id="hook-source-not-blocked-by-security",
        ),
    ],
)
def test_write_not_denied(
    pretool_write: WriteBuilder,
    file_path: str,
    content: str,
    forbidden_rule: str | None,
) -> None:
    passed, detail = assert_write_negative_case(
        pretool_write, file_path, content, forbidden_rule
    )
    assert passed, detail


@pytest.mark.parametrize(
    "command, forbidden_rule",
    [
        pytest.param("npm test", None, id="npm-test"),
        pytest.param("cat Makefile", None, id="cat-makefile"),
        pytest.param("cat .claude/hooks/run-pretool.sh", None, id="cat-hook-file"),
        pytest.param(
            "grep -n import src/hook_layer/engine.py",
            "PY-SHELL-001",
            id="grep-not-shell-edit",
        ),
    ],
)
def test_bash_not_denied(
    pretool_bash: BashBuilder,
    evaluate: EvaluateFn,
    command: str,
    forbidden_rule: str | None,
) -> None:
    passed, detail = assert_bash_negative_case(
        pretool_bash, evaluate, command, forbidden_rule
    )
    assert passed, detail


def test_read_hook_file_allowed(bundle_root: Path) -> None:
    payload = {
        "session_id": "t",
        "cwd": str(bundle_root),
        "hook_event_name": "PreToolUse",
        "tool_name": "Read",
        "tool_input": {"file_path": ".claude/hooks/run-pretool.sh"},
    }
    result = evaluate_payload(payload)
    assert_not_denied(result)
    assert "BUILTIN-PROTECTED-PATHS" not in finding_ids(result), (
        "read-only access to hook files should not trigger edit protections"
    )


def test_two_asserts_below_threshold(pretool_write: WriteBuilder) -> None:
    result = evaluate_payload(
        pretool_write(
            "tests/test_safe.py",
            "def test_ok():\n    assert x == 1\n    assert y == 2\n",
        )
    )
    assert "PY-TEST-001" not in finding_ids(result), "2 asserts below threshold"


class TestEdgeCases:
    """Verify rules don't over-match on similar-looking but valid code."""

    @pytest.mark.parametrize("code, should_deny", EXC_002_BOUNDARY_CASES)
    def test_exc_002_boundaries(
        self, pretool_write: WriteBuilder, code: str, should_deny: bool
    ) -> None:
        result = evaluate_payload(pretool_write("src/module.py", code))
        ids = finding_ids(result)
        assert ("PY-EXC-002" in ids) is should_deny, (
            f"Unexpected PY-EXC-002 result for code:\n{code}"
        )

    def test_exc_002_single_line_default_return_denied(
        self, pretool_write: WriteBuilder
    ) -> None:
        code = "def f():\n    try:\n        return run()\n    except Exception: return []\n"
        result = evaluate_payload(pretool_write("src/module.py", code))
        assert "PY-EXC-002" in finding_ids(result)

    def test_any_builtin_not_denied(self, pretool_write: WriteBuilder) -> None:
        """Python's builtin any() must not trigger PY-TYPE-001."""
        result = evaluate_payload(
            pretool_write(
                "src/check.py",
                "def has_errors(items: list[str]) -> bool:\n"
                "    return any(item.startswith('ERROR') for item in items)\n",
            )
        )
        assert "PY-TYPE-001" not in finding_ids(result)

    def test_normal_git_commit_allowed(self, pretool_bash: BashBuilder) -> None:
        result = evaluate_payload(pretool_bash("git commit -m 'fix: thing'"))
        assert "GIT-001" not in finding_ids(result)

    def test_safe_redirect_allowed(self, pretool_bash: BashBuilder) -> None:
        result = evaluate_payload(pretool_bash("echo hello > output.txt"))
        assert "SHELL-001" not in finding_ids(result)

    def test_asserts_with_messages_allowed(self, pretool_write: WriteBuilder) -> None:
        code = (
            "def test_validated():\n"
            "    assert x == 1, 'expected 1'\n"
            "    assert y == 2, 'expected 2'\n"
            "    assert z == 3, 'expected 3'\n"
            "    assert w == 4, 'expected 4'\n"
        )
        result = evaluate_payload(pretool_write("tests/test_good.py", code))
        assert "PY-TEST-001" not in finding_ids(result)

    @pytest.mark.parametrize(
        "file_path, content",
        [
            pytest.param(
                "docs/README.md",
                "# Exceptions\n\nexcept Exception:\n    pass\n\nfrom typing import Any\n",
                id="markdown",
            ),
            pytest.param(
                "config.json",
                '{\n  "type": "Any"\n}\n',
                id="json",
            ),
        ],
    )
    def test_non_python_not_denied_by_python_rules(
        self, pretool_write: WriteBuilder, file_path: str, content: str
    ) -> None:
        result = evaluate_payload(pretool_write(file_path, content))
        py_rules = {r for r in finding_ids(result) if r.startswith("PY-")}
        assert not py_rules, f"Non-Python file should not trigger: {py_rules}"
