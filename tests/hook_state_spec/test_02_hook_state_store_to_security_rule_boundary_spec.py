from __future__ import annotations

from tests.test_hook_state_spec import (
    BUNDLE_ROOT,
    Path,
    InspectableHookStateStore,
    bash_payload,
    collect_process_failures,
    ensure_enrolled,
    grep_payload,
    missing_full_read_records,
    run_payload_in_subprocess,
    start_full_read_record_processes,
    assert_denied_by,
    assert_not_denied,
    evaluate_payload,
    finding_ids,
    get_adapter,
    json,
    object_dict,
    time,
)


def _deny_key_for_test(
    session_id: str, rule_id: str, path: str | None, attempt_fingerprint: str | None
) -> str:
    normalized_path = str(Path(path).resolve(strict=False)) if path else "__pathless__"
    return json.dumps(
        {
            "session_id": session_id.strip(),
            "rule_id": rule_id.strip(),
            "path": normalized_path,
            "attempt_fingerprint": attempt_fingerprint or "__unknown_attempt__",
        },
        sort_keys=True,
    )


def _seed_deny_hits(store: InspectableHookStateStore, hits: dict[str, int]) -> None:
    store.save_state_for_test({"deny_hits": hits})


def _loaded_deny_hits(store: InspectableHookStateStore) -> dict[str, object]:
    return object_dict(store.load_state_for_test().get("deny_hits"))


class _DirectClearStore(InspectableHookStateStore):
    def _deny_key_matches(self, key: str, pattern: object) -> bool:
        raise AssertionError("exact deny-hit clear should not scan every key")


class TestHookStateStore:
    def test_ttl_expiry_filters_stale_full_reads(self, tmp_path: Path) -> None:
        store = InspectableHookStateStore(tmp_path)
        key = json.dumps(
            {
                "path": str((tmp_path / "module.py").resolve(strict=False)),
                "session_id": "session-a",
            },
            sort_keys=True,
        )
        store.save_state_for_test(
            {"full_reads": {key: int(time()) - store.ttl_seconds - 5}}
        )

        assert not store.has_full_read("session-a", str(tmp_path / "module.py"))

    def test_large_deny_hit_state_is_bounded_but_keeps_repeated_signal(
        self, tmp_path: Path
    ) -> None:
        limit = 512
        store = InspectableHookStateStore(tmp_path)
        noisy_hits = {
            _deny_key_for_test(
                "session-a",
                "PY-NOISE-001",
                str(tmp_path / f"module_{idx}.py"),
                f"attempt-{idx}",
            ): 1
            for idx in range(limit + 75)
        }
        repeated_key = _deny_key_for_test(
            "session-a", "PY-CODE-013", str(tmp_path / "thin.py"), "important-attempt"
        )
        _seed_deny_hits(store, {**noisy_hits, repeated_key: 8})

        deny_hits = _loaded_deny_hits(store)

        assert len(deny_hits) <= limit
        assert deny_hits[repeated_key] == 8

    def test_exact_deny_hit_clear_uses_direct_key_without_scanning(
        self, tmp_path: Path
    ) -> None:
        store = _DirectClearStore(tmp_path)
        target_key = _deny_key_for_test(
            "session-a", "PY-CODE-013", str(tmp_path / "thin.py"), "attempt-a"
        )
        other_key = _deny_key_for_test(
            "session-a", "PY-CODE-013", str(tmp_path / "thin.py"), "attempt-b"
        )
        _seed_deny_hits(store, {target_key: 2, other_key: 2})

        store.clear_deny_hit(
            "session-a", "PY-CODE-013", str(tmp_path / "thin.py"), "attempt-a"
        )
        deny_hits = _loaded_deny_hits(store)

        assert target_key not in deny_hits
        assert deny_hits[other_key] == 2

    def test_parallel_subprocess_writes_complete_without_losing_entries(
        self, tmp_path: Path
    ) -> None:
        store = InspectableHookStateStore(tmp_path)
        targets, processes = start_full_read_record_processes(tmp_path, 8)

        timed_out_processes, failed_processes = collect_process_failures(processes)

        assert timed_out_processes == []
        assert failed_processes == []

        state = store.load_state_for_test()
        missing_full_reads = missing_full_read_records(store, targets)

        assert len(object_dict(state.get("full_reads"))) == len(targets)
        assert missing_full_reads == []


class TestSearchReminderCurrentGuards:
    def test_bash_grep_still_triggers_reminder(self, tmp_path: Path) -> None:
        result = evaluate_payload(
            bash_payload("grep -rn 'TODO' src/", cwd=str(tmp_path))
        )
        assert "REMIND-SEARCH-001" in finding_ids(result)

    def test_ripgrep_does_not_trigger_reminder(self, tmp_path: Path) -> None:
        result = evaluate_payload(bash_payload("rg 'TODO' src/", cwd=str(tmp_path)))
        assert "REMIND-SEARCH-001" not in finding_ids(result)

    def test_embedded_grep_token_does_not_trigger_reminder(
        self, tmp_path: Path
    ) -> None:
        result = evaluate_payload(bash_payload("egrep 'TODO' src/", cwd=str(tmp_path)))
        assert "REMIND-SEARCH-001" not in finding_ids(result)

    def test_new_session_still_gets_search_reminder(self, tmp_path: Path) -> None:
        _ = evaluate_payload(
            bash_payload("grep -rn 'TODO' src/", cwd=str(tmp_path), session_id="s1")
        )
        result = evaluate_payload(
            bash_payload("grep -rn 'TODO' src/", cwd=str(tmp_path), session_id="s2")
        )

        assert "REMIND-SEARCH-001" in finding_ids(result)


class TestSearchReminderStatefulSpec:
    def test_native_grep_tool_does_not_self_remind(self, tmp_path: Path) -> None:
        result = evaluate_payload(grep_payload("TODO", cwd=str(tmp_path)))
        assert "REMIND-SEARCH-001" not in finding_ids(result)

    def test_second_shell_grep_same_session_is_deduped(self, tmp_path: Path) -> None:
        first = evaluate_payload(
            bash_payload("grep -rn 'TODO' src/", cwd=str(tmp_path), session_id="s1")
        )
        second = evaluate_payload(
            bash_payload("grep -rn 'FIXME' src/", cwd=str(tmp_path), session_id="s1")
        )

        assert "REMIND-SEARCH-001" in finding_ids(first)
        assert "REMIND-SEARCH-001" not in finding_ids(second)

    def test_same_session_dedupe_must_survive_subprocess_boundary(
        self, tmp_path: Path
    ) -> None:
        first = run_payload_in_subprocess(
            bash_payload("grep -rn 'TODO' src/", cwd=str(tmp_path), session_id="s1")
        )
        second = run_payload_in_subprocess(
            bash_payload("grep -rn 'FIXME' src/", cwd=str(tmp_path), session_id="s1")
        )

        assert "REMIND-SEARCH-001" in first["finding_ids"]
        assert "REMIND-SEARCH-001" not in second["finding_ids"]


class TestCrossPlatformSessionIdentityCurrentGuards:
    def test_codex_adapter_preserves_session_id(self) -> None:
        payload = {
            "session_id": "codex-session",
            "cwd": str(BUNDLE_ROOT),
            "hook_event_name": "PreToolUse",
            "tool_name": "Read",
            "tool_input": {"file_path": "src/example.py"},
        }
        normalized = get_adapter("codex").normalize_payload(payload)
        assert normalized["session_id"] == "codex-session"
        assert normalized["hook_event_name"] == "PreToolUse"

    def test_opencode_session_idle_maps_to_stop_and_preserves_session_id(self) -> None:
        payload = {
            "session_id": "oc-session",
            "cwd": str(BUNDLE_ROOT),
            "hook_event_name": "session.idle",
            "tool_name": "bash",
            "tool_input": {"command": "echo hi"},
        }
        normalized = get_adapter("opencode").normalize_payload(payload)
        assert normalized["session_id"] == "oc-session"
        assert normalized["hook_event_name"] == "Stop"
        assert normalized["tool_name"] == "Bash"


class TestSecurityRuleCurrentGuards:
    def test_real_source_bypass_still_denied(self, tmp_path: Path) -> None:
        ensure_enrolled(str(tmp_path))
        payload = {
            "session_id": "spec-session",
            "cwd": str(tmp_path),
            "hook_event_name": "PreToolUse",
            "tool_name": "Write",
            "tool_input": {
                "file_path": "src/settings.py",
                "content": "BYPASS_PERMISSIONS = True\n",
            },
        }
        result = evaluate_payload(payload)
        assert any(
            finding.rule_id == "BUILTIN-RULEBOOK-SECURITY"
            and "bypass" in (finding.message or "")
            for finding in result.findings
        ), "real source bypass settings should remain security-rule violations"
        assert_denied_by(result, "BUILTIN-RULEBOOK-SECURITY", "bypass")

    def test_fixture_like_paths_remain_allowed(self, tmp_path: Path) -> None:
        ensure_enrolled(str(tmp_path))
        payload = {
            "session_id": "spec-session",
            "cwd": str(tmp_path),
            "hook_event_name": "PreToolUse",
            "tool_name": "Write",
            "tool_input": {
                "file_path": "tests/fixtures/security_fixture.json",
                "content": '{"allowManagedHooksOnly": true}\n',
            },
        }
        result = evaluate_payload(payload)
        assert all(
            finding.rule_id != "BUILTIN-RULEBOOK-SECURITY"
            for finding in result.findings
        ), "fixture examples should not trip source security bypass enforcement"
        assert_not_denied(result)


class TestSecurityRuleBoundarySpec:
    def test_markdown_docs_can_describe_bypass_settings(self, tmp_path: Path) -> None:
        ensure_enrolled(str(tmp_path))
        payload = {
            "session_id": "spec-session",
            "cwd": str(tmp_path),
            "hook_event_name": "PreToolUse",
            "tool_name": "Write",
            "tool_input": {
                "file_path": "docs/security.md",
                "content": "Use `bypass_permissions` only in emergency rollback guidance.\n",
            },
        }
        result = evaluate_payload(payload)
        assert all(
            finding.rule_id != "BUILTIN-RULEBOOK-SECURITY"
            for finding in result.findings
        ), "markdown documentation should be allowed to describe bypass settings"
        assert_not_denied(result)

    def test_json_examples_can_show_guardrail_settings(self, tmp_path: Path) -> None:
        ensure_enrolled(str(tmp_path))
        payload = {
            "session_id": "spec-session",
            "cwd": str(tmp_path),
            "hook_event_name": "PreToolUse",
            "tool_name": "Write",
            "tool_input": {
                "file_path": "docs/examples/hooks.json",
                "content": '{"allowManagedHooksOnly": true}\n',
            },
        }
        result = evaluate_payload(payload)
        assert all(
            finding.rule_id != "BUILTIN-RULEBOOK-SECURITY"
            for finding in result.findings
        ), "JSON documentation examples should not be treated as live guardrail config"
        assert_not_denied(result)
