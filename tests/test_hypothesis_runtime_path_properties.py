from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from hypothesis import given, strategies

from slopgate._types import ObjectDict
from slopgate.adapters.base import render_request_from_call
from slopgate.search import config, runtime
from slopgate.util.payloads import is_edit_like_tool
from slopgate.util.platform import normalize_path_for_match, resolve_path_for_match

TEXT_ALPHABET = "abcdefghijklmnopqrstuvwxyz0123456789 _.-/"
SHORT_TEXT = strategies.text(alphabet=TEXT_ALPHABET, max_size=40)
TOOL_NAMES = strategies.sampled_from(
    ["Edit", "Write", "edit_file", "morph_edit", "Read"]
)


@given(model_name=SHORT_TEXT)
def test_embedding_like_is_boolean_property(model_name: str) -> None:
    assert isinstance(runtime.embedding_like(model_name), bool)


def test_fetch_runtime_models_returns_list_when_env_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RUNTIME_API_KEY", "secret")

    def fake_fetch_models(_base: str, _key: str | None) -> list[str]:
        return ["model-a"]

    monkeypatch.setattr(runtime, "fetch_models", fake_fetch_models)
    cfg = config.SearchConfig(
        base_url="https://llm.example", api_key_env="RUNTIME_API_KEY"
    )
    assert runtime.fetch_runtime_models(cfg) == ["model-a"]


@given(tool=TOOL_NAMES)
def test_is_edit_like_tool_matches_edit_family_property(tool: str) -> None:
    assert isinstance(is_edit_like_tool(tool), bool)


@given(value=SHORT_TEXT)
def test_normalize_path_for_match_is_idempotent_property(value: str) -> None:
    once = normalize_path_for_match(value)
    twice = normalize_path_for_match(once)
    assert once == twice


@given(value=SHORT_TEXT)
def test_resolve_path_for_match_lowercases_relative_paths_property(value: str) -> None:
    with TemporaryDirectory() as raw_path:
        resolved = resolve_path_for_match(value, Path(raw_path))
    assert resolved == resolved.casefold()


@given(
    event=strategies.sampled_from(["PreToolUse", "PostToolUse", "stop"]),
    decision=strategies.one_of(
        strategies.none(), strategies.just("deny"), strategies.just("allow")
    ),
)
def test_render_request_from_call_accepts_adapter_args_property(
    event: str, decision: str | None
) -> None:
    kwargs: ObjectDict = {}
    if decision is not None:
        kwargs["decision"] = decision
    request = render_request_from_call((event, []), kwargs)
    assert request.event_name == event
