from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

from slopgate.installer.opencode_identity import collect_opencode_install_identity

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "harness_target_drift.py"
)


def _load_drift() -> ModuleType:
    spec = importlib.util.spec_from_file_location("harness_target_drift", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None, (
        "drift script must be importable"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


drift = _load_drift()


def _registry(version: str) -> object:
    return {"dist-tags": {"latest": version}}


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("opencode v2.2.6", "2.2.6"), ("2.2.5", "2.2.5"), ("v18.16.0", "18.16.0")],
)
def test_extract_version_reads_cli_output(raw: str, expected: str) -> None:
    assert drift.extract_version(raw) == expected, f"{raw!r} should parse to {expected}"


@pytest.mark.parametrize(
    ("target", "released", "ahead"),
    [
        ("2.2.5", "2.2.6", True),
        ("2.2.5", "2.2.5", False),
        ("2.2.6", "2.2.5", False),
        ("2.2.9", "2.10.0", True),
    ],
)
def test_drift_compares_numerically(target: str, released: str, ahead: bool) -> None:
    assert drift.Drift("opencode", target, released, None).ahead is ahead, (
        f"{target} vs {released} must compare numerically, never as strings"
    )


@pytest.mark.parametrize(
    "metadata", [{}, {"dist-tags": {}}, [], {"dist-tags": {"latest": 7}}]
)
def test_released_version_rejects_malformed_metadata(metadata: object) -> None:
    with pytest.raises(drift.DriftCheckError):
        drift.released_version(metadata)


def test_opencode_api_target_reads_the_constant_slopgate_uses(tmp_path: Path) -> None:
    identity = collect_opencode_install_identity(
        "slopgate", config_dir=tmp_path, probe_runtime=False
    )
    assert drift.opencode_api_target() == identity["plugin_api_target"], (
        "the declared target must be the one the identity check really compares against"
    )


def test_opencode_api_target_rejects_a_file_without_the_constant(
    tmp_path: Path,
) -> None:
    empty = tmp_path / "opencode_identity.py"
    empty.write_text("OTHER = 1\n", encoding="utf-8")
    with pytest.raises(drift.DriftCheckError):
        drift.opencode_api_target(empty)


def _stub_world(
    monkeypatch: pytest.MonkeyPatch, target: str, released: str, installed: str | None
) -> None:
    def fetch(_package: str) -> object:
        return _registry(released)

    def installed_version(_name: str) -> str | None:
        return installed

    def declared_target() -> str:
        return target

    monkeypatch.setattr(drift, "fetch_registry_metadata", fetch)
    monkeypatch.setattr(drift, "installed_version", installed_version)
    monkeypatch.setattr(
        drift,
        "DECLARED_TARGETS",
        (drift.DeclaredTarget("opencode", "@opencode/plugin", declared_target),),
    )


def test_main_reports_a_release_ahead_of_the_target_without_failing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _stub_world(monkeypatch, target="2.2.5", released="2.2.6", installed="2.2.6")
    status = drift.main()
    assert (status, capsys.readouterr().out.strip()) == (
        drift.EXIT_OK,
        "opencode 2.2.6 released; Slopgate targets 2.2.5; installed 2.2.6",
    ), "a newer release must be reported but never fail the run"


def test_main_is_quiet_about_drift_when_the_target_is_current(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _stub_world(monkeypatch, target="2.2.6", released="2.2.6", installed=None)
    status = drift.main()
    assert (status, "released" in capsys.readouterr().out) == (drift.EXIT_OK, False), (
        "no drift line may be printed when nothing is ahead of the target"
    )


def test_main_fails_when_release_metadata_is_unreadable(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _stub_world(monkeypatch, target="2.2.5", released="2.2.6", installed=None)

    def unreadable(_package: str) -> object:
        return {}

    monkeypatch.setattr(drift, "fetch_registry_metadata", unreadable)
    status = drift.main()
    assert (status, "Could not check" in capsys.readouterr().err) == (
        drift.EXIT_FAILED,
        True,
    ), "an unreadable registry response must be an error, not a silent all-clear"
