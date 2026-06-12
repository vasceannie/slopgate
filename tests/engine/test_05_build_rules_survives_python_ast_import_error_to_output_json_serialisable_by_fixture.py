from __future__ import annotations
import slopgate.rules
from tests.test_engine import (
    FIXTURE_FILE_NAMES,
    LoadFixture,
    MonkeyPatch,
    ObjectDict,
    Path,
    VALID_TOP_LEVEL_KEYS,
    VIRTUALENV_PARSE_SKIP_PATHS,
    BashBuilder,
    WriteBuilder,
    fixture_output,
    rule_build_context,
    assert_denied_by,
    cast,
    evaluate_payload,
    finding_ids,
    hook_output,
    json,
    nested_output,
    object_dict,
    output_string,
    pytest,
    require_output,
)


def test_build_rules_survives_python_ast_import_error(
    load_fixture: LoadFixture, monkeypatch: MonkeyPatch
) -> None:
    _rules_mod, ctx = rule_build_context(load_fixture)
    healthy_ids = {rule.rule_id for rule in slopgate.rules.build_rules(ctx)}
    assert "PY-CODE-008" in healthy_ids, (
        f"Missing AST rule in healthy build: {healthy_ids}"
    )
    assert "PY-IMPORT-001" in healthy_ids, (
        f"Missing import rule in healthy build: {healthy_ids}"
    )
    monkeypatch.setattr(
        slopgate.rules,
        "_PYTHON_AST_IMPORT_ERROR",
        SyntaxError("synthetic import failure"),
        raising=False,
    )
    monkeypatch.setattr(
        slopgate.rules, "_PYTHON_AST_IMPORT_REPORTED", False, raising=False
    )
    fallback_ids = {rule.rule_id for rule in slopgate.rules.build_rules(ctx)}
    assert "GIT-001" in fallback_ids, f"Fallback build lost regex rules: {fallback_ids}"
    assert "PY-CODE-008" not in fallback_ids, (
        f"Fallback should skip AST rules: {fallback_ids}"
    )
    assert "PY-IMPORT-001" not in fallback_ids, (
        f"Fallback should skip import AST rules: {fallback_ids}"
    )
    assert "PY-AST-IMPORT-001" in fallback_ids, (
        f"Missing import-error sentinel: {fallback_ids}"
    )


def _force_python_ast_import_error(monkeypatch: MonkeyPatch) -> None:
    import slopgate.rules

    monkeypatch.setattr(
        slopgate.rules,
        "_PYTHON_AST_IMPORT_ERROR",
        SyntaxError("synthetic import failure"),
        raising=False,
    )
    monkeypatch.setattr(slopgate.rules, "_python_ast_import_error", None, raising=False)
    monkeypatch.setattr(
        slopgate.rules, "_PYTHON_AST_IMPORT_REPORTED", False, raising=False
    )
    monkeypatch.setattr(
        slopgate.rules, "_python_ast_import_reported", False, raising=False
    )


def test_python_ast_import_error_allows_bash_validation_commands(
    pretool_bash: BashBuilder, monkeypatch: MonkeyPatch, bundle_root: Path
) -> None:
    _force_python_ast_import_error(monkeypatch)
    result = evaluate_payload(
        pretool_bash(
            "uv run ruff check src/slopgate/engine/_evaluation.py && "
            "uv run basedpyright src/slopgate/engine/_evaluation.py 2>&1 | tail -5",
            cwd=str(bundle_root),
        )
    )
    assert any((f.rule_id == "PY-AST-IMPORT-001" for f in result.findings))
    assert output_string(hook_output(result), "permissionDecision") != "deny"


def test_python_ast_import_error_still_blocks_python_edits(
    pretool_write: WriteBuilder, monkeypatch: MonkeyPatch
) -> None:
    _force_python_ast_import_error(monkeypatch)
    result = evaluate_payload(pretool_write("src/example.py", "value = 1\n"))
    assert any((f.rule_id == "PY-AST-IMPORT-001" for f in result.findings))
    assert_denied_by(result, "PY-AST-IMPORT-001")


def test_python_ast_parse_failure_is_reported(pretool_write: WriteBuilder) -> None:
    result = evaluate_payload(pretool_write("src/bad.py", "def broken(:\n    pass\n"))
    assert_denied_by(result, "PY-AST-001")
    assert "PY-AST-001" in finding_ids(result), (
        "syntax-broken Python writes should emit the AST parse-health rule"
    )


@pytest.mark.parametrize("path_value", VIRTUALENV_PARSE_SKIP_PATHS)
def test_python_ast_parse_failure_skips_virtualenv_paths(
    pretool_write: WriteBuilder, path_value: str
) -> None:
    result = evaluate_payload(pretool_write(path_value, "def broken(:\n    pass\n"))
    assert "PY-AST-001" not in finding_ids(result)


def test_python_ast_virtualenv_skip_uses_exact_path_components(
    pretool_write: WriteBuilder,
) -> None:
    result = evaluate_payload(pretool_write("src/environment/bad.py", "def broken(:\n"))
    assert_denied_by(result, "PY-AST-001")
    assert "PY-AST-001" in finding_ids(result), (
        "only real virtualenv path components should be skipped by AST parse checks"
    )


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param({}, id="empty-payload"),
        pytest.param(
            {"session_id": "t", "hook_event_name": "PreToolUse", "tool_name": "Bash"},
            id="missing-tool-input",
        ),
        pytest.param(
            {
                "session_id": "t",
                "hook_event_name": "FutureEvent",
                "tool_name": "Write",
                "tool_input": {"file_path": "x.py", "content": "x"},
            },
            id="unknown-event",
        ),
    ],
)
def test_robustness_no_crash(payload: dict[str, object]) -> None:
    result = evaluate_payload(payload)
    assert isinstance(result.findings, list)


@pytest.mark.parametrize(
    "event_name, extra_fields",
    [
        ("Stop", {"stop_response": "done"}),
        ("SubagentStop", {"stop_response": "done"}),
        ("ConfigChange", {"source": "user_settings", "changes": {}}),
        (
            "PostToolUseFailure",
            {"tool_name": "Bash", "tool_input": {"command": "false"}},
        ),
        ("TaskCompleted", {}),
        ("TeammateIdle", {}),
    ],
)
def test_no_hookSpecificOutput_on_banned_events(
    bundle_root: Path, event_name: str, extra_fields: dict[str, object]
) -> None:
    payload: ObjectDict = {
        "session_id": "t",
        "cwd": str(bundle_root),
        "hook_event_name": event_name,
    }
    payload |= extra_fields
    result = evaluate_payload(payload)
    assert result.output is None or "hookSpecificOutput" not in result.output, (
        f"{event_name} emitted hookSpecificOutput (invalid per Claude Code schema): {result.output}"
    )


def test_stop_blocking_uses_top_level_decision(load_fixture: LoadFixture) -> None:
    result = evaluate_payload(load_fixture("stop_preexisting.json"))
    output = require_output(result)
    assert output["decision"] == "block", f"Expected block output, got: {output}"
    assert "reason" in output, f"Expected reason in output, got: {output}"
    assert "hookSpecificOutput" not in output, (
        f"Unexpected hookSpecificOutput: {output}"
    )
    assert "permissionDecision" not in output, (
        f"Unexpected permissionDecision: {output}"
    )


def test_pretooluse_uses_hookSpecificOutput(load_fixture: LoadFixture) -> None:
    result = evaluate_payload(load_fixture("pretool_git_no_verify.json"))
    spec = hook_output(result)
    assert spec["hookEventName"] == "PreToolUse", f"Wrong hook event payload: {spec}"
    assert "permissionDecision" in spec, f"Missing permissionDecision: {spec}"


def test_permission_request_uses_decision_behavior(bundle_root: Path) -> None:
    payload = {
        "session_id": "t",
        "cwd": str(bundle_root),
        "hook_event_name": "PermissionRequest",
        "tool_name": "Bash",
        "tool_input": {"command": "git commit --no-verify -m x"},
    }
    result = evaluate_payload(payload)
    spec = hook_output(result)
    assert spec["hookEventName"] == "PermissionRequest", (
        f"Wrong hook event payload: {spec}"
    )
    assert nested_output(spec, "decision")["behavior"] == "deny", (
        f"Wrong decision payload: {spec}"
    )


def test_stop_clean_uses_systemMessage(bundle_root: Path) -> None:
    payload = {
        "session_id": "t",
        "cwd": str(bundle_root),
        "hook_event_name": "Stop",
        "stop_response": "Done.",
    }
    result = evaluate_payload(payload)
    output = require_output(result)
    assert "systemMessage" in output, f"Expected systemMessage output, got: {output}"
    assert "hookSpecificOutput" not in output, (
        f"Unexpected hookSpecificOutput: {output}"
    )


def test_configchange_uses_decision_and_reason(load_fixture: LoadFixture) -> None:
    result = evaluate_payload(load_fixture("configchange_disable_hooks.json"))
    output = require_output(result)
    assert "decision" in output, f"Expected decision in output, got: {output}"
    assert "reason" in output, f"Expected reason in output, got: {output}"
    assert "permissionDecision" not in output, (
        f"Unexpected permissionDecision: {output}"
    )


@pytest.mark.parametrize("fixture_name", FIXTURE_FILE_NAMES)
def test_output_json_shape_by_fixture(
    load_fixture: LoadFixture, fixture_name: str
) -> None:
    """Each fixture output must have only recognised top-level keys."""
    event, output = fixture_output(load_fixture, fixture_name)
    invalid_keys: set[str] = (
        set(output.keys()) - VALID_TOP_LEVEL_KEYS if output is not None else set()
    )
    assert not invalid_keys, f"{fixture_name}: unknown keys {sorted(invalid_keys)!r}"
    spec = object_dict(output.get("hookSpecificOutput")) if output is not None else {}
    assert not spec or output_string(spec, "hookEventName") == event, (
        f"{fixture_name}: hookEventName mismatch"
    )


@pytest.mark.parametrize("fixture_name", FIXTURE_FILE_NAMES)
def test_output_json_serialisable_by_fixture(
    load_fixture: LoadFixture, fixture_name: str
) -> None:
    _event, output = fixture_output(load_fixture, fixture_name)
    roundtrip = (
        object_dict(cast(object, json.loads(json.dumps(output))))
        if output is not None
        else None
    )
    assert output is None or output == roundtrip, (
        f"{fixture_name}: not JSON round-trip safe"
    )
