from __future__ import annotations

from pytest import MonkeyPatch

from tests.test_hook_state_spec import (
    Path,
    config_with_enabled_rules,
    read_payload,
    run_payload_in_subprocess,
    assert_denied_by,
    assert_not_denied,
    evaluate_payload,
    json,
    pytest,
)


class TestFullReadCurrentGuards:
    def test_partial_python_read_is_denied_when_rule_enabled(
        self, tmp_path: Path, monkeypatch: MonkeyPatch
    ) -> None:
        config_with_enabled_rules(tmp_path, monkeypatch, "BUILTIN-ENFORCE-FULL-READ")
        target = tmp_path / "sample.py"
        target.write_text("print('hi')\n", encoding="utf-8")

        result = evaluate_payload(
            read_payload(str(target), cwd=str(tmp_path), offset=1, limit=1)
        )

        assert any(
            finding.rule_id == "BUILTIN-ENFORCE-FULL-READ"
            and "full first" in (finding.message or "")
            for finding in result.findings
        ), "partial Python reads should explain the full-first-read contract"
        assert_denied_by(result, "BUILTIN-ENFORCE-FULL-READ", "full first")

    def test_partial_json_read_is_allowed_when_rule_enabled(
        self, tmp_path: Path, monkeypatch: MonkeyPatch
    ) -> None:
        config_with_enabled_rules(tmp_path, monkeypatch, "BUILTIN-ENFORCE-FULL-READ")
        target = tmp_path / "data.json"
        target.write_text('{"ok": true}\n', encoding="utf-8")

        result = evaluate_payload(
            read_payload(str(target), cwd=str(tmp_path), offset=1, limit=1)
        )

        assert all(
            finding.rule_id != "BUILTIN-ENFORCE-FULL-READ"
            for finding in result.findings
        ), "JSON partial reads should stay outside the Python full-read guard"
        assert_not_denied(result)

    def test_large_python_read_is_exempt_when_rule_enabled(
        self, tmp_path: Path, monkeypatch: MonkeyPatch
    ) -> None:
        config_with_enabled_rules(tmp_path, monkeypatch, "BUILTIN-ENFORCE-FULL-READ")
        target = tmp_path / "large.py"
        target.write_text("x = 1\n" * 10000, encoding="utf-8")

        result = evaluate_payload(
            read_payload(str(target), cwd=str(tmp_path), offset=1, limit=20)
        )

        assert all(
            finding.rule_id != "BUILTIN-ENFORCE-FULL-READ"
            for finding in result.findings
        ), "large Python files should remain exempt from full-read enforcement"
        assert_not_denied(result)

    @pytest.mark.parametrize(
        "path_value",
        (
            ".venv/lib/python3.12/site-packages/pkg/module.py",
            ".venvs/job-hunter/lib/python3.12/site-packages/pkg/module.py",
            "venv/lib/python3.12/site-packages/pkg/module.py",
            "env/lib/python3.12/site-packages/pkg/module.py",
            "src/pkg/site-packages/vendor/module.py",
        ),
    )
    def test_partial_virtualenv_python_read_is_allowed_when_rule_enabled(
        self, tmp_path: Path, monkeypatch: MonkeyPatch, path_value: str
    ) -> None:
        config_with_enabled_rules(tmp_path, monkeypatch, "BUILTIN-ENFORCE-FULL-READ")
        target = tmp_path / path_value
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("a = 1\nb = 2\n", encoding="utf-8")

        result = evaluate_payload(
            read_payload(str(target), cwd=str(tmp_path), offset=1, limit=1)
        )

        assert all(
            finding.rule_id != "BUILTIN-ENFORCE-FULL-READ"
            for finding in result.findings
        ), "virtualenv/library files should not trigger full-read hook enforcement"
        assert_not_denied(result)

    def test_other_session_still_denied_without_stateful_unlock(
        self, tmp_path: Path, monkeypatch: MonkeyPatch
    ) -> None:
        config_with_enabled_rules(tmp_path, monkeypatch, "BUILTIN-ENFORCE-FULL-READ")
        target = tmp_path / "module.py"
        target.write_text("a = 1\nb = 2\n", encoding="utf-8")

        _ = evaluate_payload(
            read_payload(str(target), cwd=str(tmp_path), session_id="session-a")
        )
        result = evaluate_payload(
            read_payload(
                str(target),
                cwd=str(tmp_path),
                session_id="session-b",
                offset=1,
                limit=1,
            )
        )

        assert any(
            finding.rule_id == "BUILTIN-ENFORCE-FULL-READ"
            for finding in result.findings
        ), "a full read in another session must not unlock this session"
        assert_denied_by(result, "BUILTIN-ENFORCE-FULL-READ")

    def test_other_file_still_denied_without_stateful_unlock(
        self, tmp_path: Path, monkeypatch: MonkeyPatch
    ) -> None:
        config_with_enabled_rules(tmp_path, monkeypatch, "BUILTIN-ENFORCE-FULL-READ")
        file_a = tmp_path / "a.py"
        file_b = tmp_path / "b.py"
        file_a.write_text("a = 1\n", encoding="utf-8")
        file_b.write_text("b = 2\n", encoding="utf-8")

        _ = evaluate_payload(
            read_payload(str(file_a), cwd=str(tmp_path), session_id="session-a")
        )
        result = evaluate_payload(
            read_payload(
                str(file_b),
                cwd=str(tmp_path),
                session_id="session-a",
                offset=1,
                limit=1,
            )
        )

        assert any(
            finding.rule_id == "BUILTIN-ENFORCE-FULL-READ"
            for finding in result.findings
        ), "a full read of another file must not unlock the requested file"
        assert_denied_by(result, "BUILTIN-ENFORCE-FULL-READ")


class TestFullReadStatefulSpec:
    def test_partial_jsonl_read_is_allowed_when_rule_enabled(
        self, tmp_path: Path, monkeypatch: MonkeyPatch
    ) -> None:
        config_with_enabled_rules(tmp_path, monkeypatch, "BUILTIN-ENFORCE-FULL-READ")
        target = tmp_path / "events.jsonl"
        target.write_text('{"event": 1}\n{"event": 2}\n', encoding="utf-8")

        result = evaluate_payload(
            read_payload(str(target), cwd=str(tmp_path), offset=2, limit=1)
        )

        assert all(
            finding.rule_id != "BUILTIN-ENFORCE-FULL-READ"
            for finding in result.findings
        ), "JSONL partial reads should stay outside the Python full-read guard"
        assert_not_denied(result)

    def test_full_read_unlocks_follow_up_partial_read_in_same_session(
        self, tmp_path: Path, monkeypatch: MonkeyPatch
    ) -> None:
        config_with_enabled_rules(tmp_path, monkeypatch, "BUILTIN-ENFORCE-FULL-READ")
        target = tmp_path / "module.py"
        target.write_text("a = 1\nb = 2\nc = 3\n", encoding="utf-8")
        session_id = "same-session"

        first = evaluate_payload(
            read_payload(str(target), cwd=str(tmp_path), session_id=session_id)
        )
        second = evaluate_payload(
            read_payload(
                str(target),
                cwd=str(tmp_path),
                session_id=session_id,
                offset=2,
                limit=1,
            )
        )

        assert first.output is None or "deny" not in json.dumps(first.output)
        assert_not_denied(second)

    def test_absolute_and_relative_paths_share_unlock_key(
        self, tmp_path: Path, monkeypatch: MonkeyPatch
    ) -> None:
        config_with_enabled_rules(tmp_path, monkeypatch, "BUILTIN-ENFORCE-FULL-READ")
        target = tmp_path / "pkg" / "module.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("a = 1\nb = 2\n", encoding="utf-8")
        session_id = "same-session"

        _ = evaluate_payload(
            read_payload(str(target), cwd=str(tmp_path), session_id=session_id)
        )
        result = evaluate_payload(
            read_payload(
                "pkg/module.py",
                cwd=str(tmp_path),
                session_id=session_id,
                offset=1,
                limit=1,
            )
        )

        assert all(
            finding.rule_id != "BUILTIN-ENFORCE-FULL-READ"
            for finding in result.findings
        ), "absolute full reads should unlock equivalent relative paths"
        assert_not_denied(result)

    def test_same_session_unlock_must_survive_subprocess_boundary(
        self, tmp_path: Path, monkeypatch: MonkeyPatch
    ) -> None:
        config_with_enabled_rules(tmp_path, monkeypatch, "BUILTIN-ENFORCE-FULL-READ")
        target = tmp_path / "module.py"
        target.write_text("a = 1\nb = 2\nc = 3\n", encoding="utf-8")
        session_id = "same-session"

        first = run_payload_in_subprocess(
            read_payload(str(target), cwd=str(tmp_path), session_id=session_id)
        )
        second = run_payload_in_subprocess(
            read_payload(
                str(target),
                cwd=str(tmp_path),
                session_id=session_id,
                offset=2,
                limit=1,
            )
        )

        assert "BUILTIN-ENFORCE-FULL-READ" not in first["finding_ids"]
        assert "BUILTIN-ENFORCE-FULL-READ" not in second["finding_ids"]

    def test_subprocess_unlock_survives_absolute_to_relative_path_flow(
        self, tmp_path: Path, monkeypatch: MonkeyPatch
    ) -> None:
        config_with_enabled_rules(tmp_path, monkeypatch, "BUILTIN-ENFORCE-FULL-READ")
        target = tmp_path / "pkg" / "module.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("a = 1\nb = 2\nc = 3\n", encoding="utf-8")
        session_id = "same-session"

        first = run_payload_in_subprocess(
            read_payload(str(target), cwd=str(tmp_path), session_id=session_id)
        )
        second = run_payload_in_subprocess(
            read_payload(
                "pkg/module.py",
                cwd=str(tmp_path),
                session_id=session_id,
                offset=2,
                limit=1,
            )
        )

        assert "BUILTIN-ENFORCE-FULL-READ" not in first["finding_ids"]
        assert "BUILTIN-ENFORCE-FULL-READ" not in second["finding_ids"]

    def test_symlinked_paths_share_unlock_key(
        self, tmp_path: Path, monkeypatch: MonkeyPatch
    ) -> None:
        config_with_enabled_rules(tmp_path, monkeypatch, "BUILTIN-ENFORCE-FULL-READ")
        target = tmp_path / "module.py"
        link_path = tmp_path / "alias.py"
        target.write_text("a = 1\nb = 2\n", encoding="utf-8")
        link_path.symlink_to(target)
        session_id = "same-session"

        _ = evaluate_payload(
            read_payload(str(target), cwd=str(tmp_path), session_id=session_id)
        )
        result = evaluate_payload(
            read_payload(
                str(link_path),
                cwd=str(tmp_path),
                session_id=session_id,
                offset=1,
                limit=1,
            )
        )

        assert all(
            finding.rule_id != "BUILTIN-ENFORCE-FULL-READ"
            for finding in result.findings
        ), "symlink paths should share the canonical full-read unlock key"
        assert_not_denied(result)

    def test_missing_files_do_not_create_unlock_state(
        self, tmp_path: Path, monkeypatch: MonkeyPatch
    ) -> None:
        config_with_enabled_rules(tmp_path, monkeypatch, "BUILTIN-ENFORCE-FULL-READ")
        missing = tmp_path / "missing.py"
        session_id = "same-session"

        _ = evaluate_payload(
            read_payload(str(missing), cwd=str(tmp_path), session_id=session_id)
        )
        result = evaluate_payload(
            read_payload(
                str(missing),
                cwd=str(tmp_path),
                session_id=session_id,
                offset=1,
                limit=1,
            )
        )

        assert any(
            finding.rule_id == "BUILTIN-ENFORCE-FULL-READ"
            for finding in result.findings
        ), "missing files should not create full-read unlock state"
        assert_denied_by(result, "BUILTIN-ENFORCE-FULL-READ")
