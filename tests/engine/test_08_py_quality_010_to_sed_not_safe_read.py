from __future__ import annotations

from tests.test_engine import (
    BashBuilder,
    ObjectDict,
    Path,
    WriteBuilder,
    _init_git_worktree,
    evaluate_payload,
    finding_ids,
    output_string,
    pytest,
)
from vibeforcer.models import RuleFinding

@pytest.mark.parametrize(
    "code, should_deny",
    [
        pytest.param(
            "def retry():\n    if count > 1000:\n        return\n",
            True,
            id="magic-1000",
        ),
        pytest.param(
            "MAX_RETRIES = 1000\ndef retry():\n    pass\n",
            False,
            id="named-constant-ok",
        ),
        pytest.param(
            "x = 1\ny = 0\n",
            False,
            id="small-numbers-ok",
        ),
    ],
)
def test_py_quality_010(
    pretool_write: WriteBuilder, code: str, should_deny: bool
) -> None:
    result = evaluate_payload(pretool_write("src/numbers.py", code))
    ids = finding_ids(result)
    assert ("PY-QUALITY-010" in ids) is should_deny, (
        f"Unexpected PY-QUALITY-010 result for code:\n{code}"
    )

def test_py_code_012_feature_envy(tmp_project: Path) -> None:
    """Function where >60% of attribute accesses target one external object."""
    code = (
        "def process_order(order):\n"
        "    name = order.customer.name\n"
        "    addr = order.customer.address\n"
        "    phone = order.customer.phone\n"
        "    email = order.customer.email\n"
        "    city = order.customer.city\n"
        "    state = order.customer.state\n"
        "    zip_code = order.customer.zip_code\n"
        "    return f'{name} {addr} {phone} {email} {city} {state} {zip_code}'\n"
    )
    target = tmp_project / "src" / "envy.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    _ = target.write_text(code)
    payload: ObjectDict = {
        "session_id": "t",
        "cwd": str(tmp_project),
        "hook_event_name": "PostToolUse",
        "tool_name": "Write",
        "tool_input": {"file_path": "src/envy.py", "content": code},
        "tool_response": {"filePath": "src/envy.py", "success": True},
    }
    result = evaluate_payload(payload)
    finding_012 = next((f for f in result.findings if f.rule_id == "PY-CODE-012"), None)
    assert finding_012 is None or finding_012.decision is None, (
        "PY-CODE-012 must remain advisory when emitted"
    )

def test_py_code_013_thin_wrapper_positive(tmp_project: Path) -> None:
    """Single-line delegation should fire PY-CODE-013."""
    code = "def get_all_users():\n    return UserRepository.find_all()\n"
    target = tmp_project / "src" / "thin.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    _ = target.write_text(code)
    payload: ObjectDict = {
        "session_id": "t",
        "cwd": str(tmp_project),
        "hook_event_name": "PostToolUse",
        "tool_name": "Write",
        "tool_input": {"file_path": "src/thin.py", "content": code},
        "tool_response": {"filePath": "src/thin.py", "success": True},
    }
    result = evaluate_payload(payload)
    finding_013 = next((f for f in result.findings if f.rule_id == "PY-CODE-013"), None)
    assert finding_013 is not None, "Expected PY-CODE-013 finding"
    assert finding_013.rule_id == "PY-CODE-013"

def test_py_code_013_multi_line_not_thin(tmp_project: Path) -> None:
    """Multi-statement functions are not thin wrappers."""
    code = (
        "def get_all_users():\n"
        "    users = UserRepository.find_all()\n"
        "    return [u for u in users if u.active]\n"
    )
    target = tmp_project / "src" / "not_thin.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    _ = target.write_text(code)
    payload: ObjectDict = {
        "session_id": "t",
        "cwd": str(tmp_project),
        "hook_event_name": "PostToolUse",
        "tool_name": "Write",
        "tool_input": {"file_path": "src/not_thin.py", "content": code},
        "tool_response": {"filePath": "src/not_thin.py", "success": True},
    }
    result = evaluate_payload(payload)
    assert not any(f.rule_id == "PY-CODE-013" for f in result.findings)

def test_py_code_016_dead_code_after_return(tmp_project: Path) -> None:
    """Code after unconditional return should fire PY-CODE-016."""
    code = "def func():\n    return 42\n    x = 1\n    y = 2\n    print(x + y)\n"
    target = tmp_project / "src" / "dead.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    _ = target.write_text(code)
    payload: ObjectDict = {
        "session_id": "t",
        "cwd": str(tmp_project),
        "hook_event_name": "PostToolUse",
        "tool_name": "Write",
        "tool_input": {"file_path": "src/dead.py", "content": code},
        "tool_response": {"filePath": "src/dead.py", "success": True},
    }
    result = evaluate_payload(payload)
    finding_016 = next((f for f in result.findings if f.rule_id == "PY-CODE-016"), None)
    assert finding_016 is not None, "Expected PY-CODE-016 finding"
    assert finding_016.rule_id == "PY-CODE-016"

@pytest.mark.parametrize(
    "path, should_deny",
    [
        ("src/agents/_executor_fill.py", True),
        ("src/_parser_utils.py", True),
        ("src/agents/_judge_helpers.py", True),
        ("src/_helpers.py", False),
        ("src/executor/__init__.py", False),
        ("tests/conftest.py", False),
        ("src/__main__.py", False),
    ],
)
def test_py_quality_011(
    pretool_write: WriteBuilder, path: str, should_deny: bool
) -> None:
    result = evaluate_payload(pretool_write(path, "x = 1\n"))
    ids = finding_ids(result)
    assert ("PY-QUALITY-011" in ids) is should_deny, (
        f"Unexpected PY-QUALITY-011 result for path: {path}"
    )

class TestFlatFileSiblings:
    def _posttool(self, tmp_project: Path, rel_path: str) -> ObjectDict:
        return {
            "session_id": "t",
            "cwd": str(tmp_project),
            "hook_event_name": "PostToolUse",
            "tool_name": "Write",
            "tool_input": {"file_path": rel_path, "content": "pass"},
            "tool_response": {"filePath": rel_path, "success": True},
        }

    def test_three_siblings_triggers(self, tmp_project: Path) -> None:
        pkg = tmp_project / "src" / "agents"
        pkg.mkdir(parents=True, exist_ok=True)
        _ = (pkg / "_parser_lexer.py").write_text("pass")
        _ = (pkg / "_parser_ast.py").write_text("pass")
        _ = (pkg / "_parser_visitor.py").write_text("pass")
        result = evaluate_payload(
            self._posttool(tmp_project, "src/agents/_parser_visitor.py")
        )
        assert any(f.rule_id == "PY-CODE-017" for f in result.findings)

    def test_two_siblings_ok(self, tmp_project: Path) -> None:
        pkg = tmp_project / "src" / "agents"
        pkg.mkdir(parents=True, exist_ok=True)
        _ = (pkg / "_parser_lexer.py").write_text("pass")
        _ = (pkg / "_parser_ast.py").write_text("pass")
        result = evaluate_payload(
            self._posttool(tmp_project, "src/agents/_parser_ast.py")
        )
        assert not any(f.rule_id == "PY-CODE-017" for f in result.findings)

    def test_different_prefixes_dont_combine(self, tmp_project: Path) -> None:
        pkg = tmp_project / "src" / "agents"
        pkg.mkdir(parents=True, exist_ok=True)
        _ = (pkg / "_parser_lexer.py").write_text("pass")
        _ = (pkg / "_parser_ast.py").write_text("pass")
        _ = (pkg / "_util_logging.py").write_text("pass")
        result = evaluate_payload(
            self._posttool(tmp_project, "src/agents/_util_logging.py")
        )
        assert not any(f.rule_id == "PY-CODE-017" for f in result.findings)

    def test_message_suggests_package_structure(self, tmp_project: Path) -> None:
        pkg = tmp_project / "src" / "agents"
        pkg.mkdir(parents=True, exist_ok=True)
        _ = (pkg / "_exec_fill.py").write_text("pass")
        _ = (pkg / "_exec_route.py").write_text("pass")
        _ = (pkg / "_exec_trace.py").write_text("pass")
        result = evaluate_payload(
            self._posttool(tmp_project, "src/agents/_exec_trace.py")
        )
        f017 = [f for f in result.findings if f.rule_id == "PY-CODE-017"]
        assert f017, "Expected PY-CODE-017 finding for 3+ _exec_* siblings"
        assert "__init__.py" in (f017[0].message or ""), "Should suggest __init__.py"
        assert "sub-package" in (f017[0].message or ""), "Should suggest sub-package"
        assert f017[0].metadata["prefix"] == "exec", "Should detect 'exec' prefix"

    def test_read_tool_skipped(self, tmp_project: Path) -> None:
        pkg = tmp_project / "src" / "agents"
        pkg.mkdir(parents=True, exist_ok=True)
        _ = (pkg / "_parser_lexer.py").write_text("pass")
        _ = (pkg / "_parser_ast.py").write_text("pass")
        _ = (pkg / "_parser_visitor.py").write_text("pass")
        payload: ObjectDict = {
            "session_id": "t",
            "cwd": str(tmp_project),
            "hook_event_name": "PostToolUse",
            "tool_name": "Read",
            "tool_input": {"file_path": "src/agents/_parser_visitor.py"},
            "tool_response": {"content": "pass"},
        }
        result = evaluate_payload(payload)
        assert not any(f.rule_id == "PY-CODE-017" for f in result.findings)

    @staticmethod
    def _worktree_with_flat_siblings(tmp_path: Path) -> tuple[Path, Path, Path]:
        repo, worktree = _init_git_worktree(tmp_path)
        pkg = worktree / "src" / "agents"
        pkg.mkdir(parents=True, exist_ok=True)
        _ = (pkg / "_parser_lexer.py").write_text("pass")
        _ = (pkg / "_parser_ast.py").write_text("pass")
        _ = (pkg / "_parser_visitor.py").write_text("pass")
        return repo, worktree, pkg

    def _py_code_017_findings(self, worktree: Path) -> list[RuleFinding]:
        result = evaluate_payload(
            self._posttool(worktree, "src/agents/_parser_visitor.py")
        )
        return [f for f in result.findings if f.rule_id == "PY-CODE-017"]

    def test_worktree_cwd_scans_worktree_directory(self, tmp_path: Path) -> None:
        repo, worktree, pkg = self._worktree_with_flat_siblings(tmp_path)
        f017 = self._py_code_017_findings(worktree)
        assert f017, "Expected PY-CODE-017 to fire from worktree cwd"
        directory = output_string(f017[0].metadata, "directory")
        assert directory == str(pkg)
        assert str(worktree) in directory
        assert Path(directory) != repo / "src" / "agents"

class TestSedNotSafeRead:
    """sed is a transform tool, not a read tool. Even without -i,
    `sed 's/x/y/' file > file` is destructive. It should not be
    in SAFE_READ_SHELL_VERBS."""

    def test_sed_without_redirect_blocked_on_protected_path(
        self, pretool_bash: BashBuilder
    ) -> None:
        """Plain sed (no -i, no redirect) on a protected path should be denied.
        Currently passes because sed is in SAFE_READ_SHELL_VERBS."""
        result = evaluate_payload(
            pretool_bash("sed 's/true/false/' .claude/hooks/run-pretool.sh")
        )
        # sed to stdout is harmless, but it shouldn't exempt the command
        # from protected path checks. The path is protected regardless.
        ids = finding_ids(result)
        assert (
            "BUILTIN-PROTECTED-PATHS" in ids or "GLOBAL-BUILTIN-HOOK-INFRA-EXEC" in ids
        )

    def test_sed_i_blocked_on_protected_path(self, pretool_bash: BashBuilder) -> None:
        """sed -i on a protected path must always be blocked."""
        result = evaluate_payload(
            pretool_bash("sed -i 's/true/false/' .claude/hooks/run-pretool.sh")
        )
        ids = finding_ids(result)
        assert (
            "BUILTIN-PROTECTED-PATHS" in ids or "GLOBAL-BUILTIN-HOOK-INFRA-EXEC" in ids
        )

    def test_sed_redirect_blocked_on_protected_path(
        self, pretool_bash: BashBuilder
    ) -> None:
        """sed with > redirect on a protected path must be blocked."""
        result = evaluate_payload(
            pretool_bash(
                "sed 's/x/y/' .claude/hooks/run-pretool.sh > .claude/hooks/run-pretool.sh"
            )
        )
        ids = finding_ids(result)
        assert (
            "BUILTIN-PROTECTED-PATHS" in ids or "GLOBAL-BUILTIN-HOOK-INFRA-EXEC" in ids
        )
