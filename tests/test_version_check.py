from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from types import TracebackType

import pytest
from hypothesis import assume, given, strategies

import slopgate.cli._version_check


class _FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc: BaseException | None,
        _traceback: TracebackType | None,
    ) -> bool:
        return False

    def read(self) -> bytes:
        return self._payload


def test_fetch_latest_version_reads_valid_pypi_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = json.dumps({"info": {"version": "1.2.3"}}).encode()

    def fake_urlopen(request: object, *, timeout: int) -> _FakeResponse:
        assert timeout == slopgate.cli._version_check._REQUEST_TIMEOUT, (
            "expected request timeout"
        )
        assert isinstance(request, urllib.request.Request), (
            "expected a urllib request object"
        )
        assert request.full_url == slopgate.cli._version_check._PYPI_URL, (
            "expected PyPI request URL"
        )
        return _FakeResponse(payload)

    monkeypatch.setattr(
        slopgate.cli._version_check.urllib.request,
        "urlopen",
        fake_urlopen,
    )

    assert slopgate.cli._version_check._fetch_latest_version() == "1.2.3", (
        "expected PyPI version"
    )


def test_fetch_latest_version_ignores_recoverable_network_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(_request: object, *, timeout: int) -> _FakeResponse:
        assert timeout == slopgate.cli._version_check._REQUEST_TIMEOUT, (
            "expected request timeout"
        )
        raise urllib.error.URLError("offline")

    monkeypatch.setattr(
        slopgate.cli._version_check.urllib.request,
        "urlopen",
        fake_urlopen,
    )

    assert slopgate.cli._version_check._fetch_latest_version() is None, (
        "expected offline check skip"
    )


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param({}, id="missing-info"),
        pytest.param({"info": {}}, id="missing-version"),
        pytest.param({"info": {"version": 123}}, id="non-string-version"),
    ],
)
def test_version_from_payload_rejects_malformed_response(
    payload: dict[str, object],
) -> None:
    assert slopgate.cli._version_check._version_from_payload(payload) is None, (
        "expected no version"
    )


def test_check_version_uses_fresh_cache(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    cache_path = tmp_path / "version-cache.json"
    cache_path.write_text(
        json.dumps(
            {"latest": "2.0.0", "checked_at": slopgate.cli._version_check.time.time()}
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(slopgate.cli._version_check, "_CACHE_PATH", cache_path)
    monkeypatch.setattr(
        slopgate.cli._version_check, "_should_skip_check", lambda: False
    )

    result = slopgate.cli._version_check.check_version("1.0.0")

    assert result.current == "1.0.0", "expected current version preserved"
    assert result.latest == "2.0.0", "expected latest version from cache"


@given(version=strategies.text(min_size=1, max_size=16))
def test_format_update_notice_suppresses_missing_or_same_latest(version: str) -> None:
    assert slopgate.cli._version_check.format_update_notice(version, None) is None, (
        "no latest"
    )
    assert slopgate.cli._version_check.format_update_notice(version, version) is None, (
        "same version"
    )


@given(
    current=strategies.text(min_size=1, max_size=16),
    latest=strategies.text(min_size=1, max_size=16),
)
def test_format_update_notice_mentions_different_latest(
    current: str,
    latest: str,
) -> None:
    assume(current != latest)

    assert slopgate.cli._version_check.format_update_notice(current, latest) == (
        f"update:   {latest} available — run `slopgate update` to upgrade"
    ), "expected update guidance"
