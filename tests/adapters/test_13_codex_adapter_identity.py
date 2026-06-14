from __future__ import annotations

from tests.test_adapters import CodexAdapter


class TestCodexAdapterIdentity:
    def test_normalize_preserves_codex_thread_identity_metadata(self) -> None:
        adapter = CodexAdapter()
        raw = {
            "hook_event_name": "SessionStart",
            "session_id": "slopgate-codex-session",
            "threadId": "thr_native_codex",
            "threadName": "Fix Codex trace grouping",
        }

        canonical = adapter.normalize_payload(raw)

        assert canonical["session_id"] == "slopgate-codex-session", (
            "Codex adapter must preserve the canonical Slopgate session_id"
        )
        assert canonical["codex_session_id"] == "thr_native_codex", (
            "Codex adapter must preserve the native thread id as side metadata"
        )
        assert canonical["session_identity_source"] == "codex-thread", (
            "Native Codex identity provenance should be explicit"
        )
        assert canonical["session_title"] == "Fix Codex trace grouping", (
            "Codex threadName should become dashboard session_title metadata"
        )
        assert canonical["session_title_source"] == "codex-thread", (
            "Codex title provenance should be explicit"
        )
        assert canonical["secondary_session_ids"] == ["slopgate-codex-session"], (
            "Canonical Slopgate id should remain searchable as a secondary id"
        )

    def test_normalize_uses_thread_id_when_session_id_is_absent(self) -> None:
        adapter = CodexAdapter()
        raw = {
            "method": "thread/started",
            "params": {"thread": {"id": "thr_native_codex", "name": "Named thread"}},
        }

        canonical = adapter.normalize_payload(raw)

        assert canonical["session_id"] == "thr_native_codex", (
            "Codex native thread id should backfill session_id when no canonical id exists"
        )
        assert canonical["codex_session_id"] == "thr_native_codex", (
            "Codex native thread id should also be preserved as native metadata"
        )
        assert canonical["session_title"] == "Named thread", (
            "Codex thread.name should become dashboard title metadata"
        )

    def test_normalize_does_not_trust_generic_jsonrpc_id_or_title(self) -> None:
        adapter = CodexAdapter()
        raw = {
            "hook_event_name": "SessionStart",
            "id": "jsonrpc-request-id",
            "title": "Generic page title",
        }

        canonical = adapter.normalize_payload(raw)

        assert "codex_session_id" not in canonical, (
            "JSON-RPC request id must not be treated as native Codex thread id"
        )
        assert "session_title" not in canonical, (
            "Bare top-level title must not be treated as Codex thread title"
        )
