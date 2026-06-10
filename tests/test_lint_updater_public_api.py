from __future__ import annotations

from pathlib import Path

from hypothesis import given, strategies

from slopgate.lint import __version__
from slopgate.lint._updater import (
    diff_config,
    render_slopgate_toml,
    update_toml_file,
)

SECTION_NAMES = strategies.sampled_from(
    ["slopgate", "duplicates", "tests", "pytest", "unknown"]
)
KEY_VALUES = strategies.dictionaries(
    keys=strategies.text(alphabet="abc_", min_size=1, max_size=8),
    values=strategies.one_of(strategies.booleans(), strategies.integers(0, 5)),
    max_size=4,
)


def test_render_slopgate_toml_includes_version_and_defaults() -> None:
    rendered = render_slopgate_toml(version="1.2.3")

    assert {
        "header": rendered.startswith("# Quality Gate Configuration\n"),
        "version": 'version = "1.2.3"' in rendered,
        "slopgate": "[slopgate]" in rendered,
        "thresholds": "[thresholds]" in rendered,
    } == {
        "header": True,
        "version": True,
        "slopgate": True,
        "thresholds": True,
    }


def test_diff_config_returns_only_missing_sections_and_keys() -> None:
    missing = diff_config(
        {
            "slopgate": {"enabled": False},
            "thresholds": {"max_complexity": 99},
        }
    )

    assert {
        "quality_gate_enabled": missing["slopgate"].get("enabled"),
        "quality_gate_version": "version" in missing["slopgate"],
        "threshold_max_complexity": missing["thresholds"].get("max_complexity"),
        "threshold_max_params": missing["thresholds"]["max_params"],
        "paths": "paths" in missing,
    } == {
        "quality_gate_enabled": None,
        "quality_gate_version": True,
        "threshold_max_complexity": None,
        "threshold_max_params": 4,
        "paths": True,
    }


def test_update_toml_file_preserves_existing_values_and_injects_missing(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "slopgate.toml"
    config_path.write_text("[slopgate]\nenabled = false\n", encoding="utf-8")

    missing = update_toml_file(config_path)
    updated = config_path.read_text(encoding="utf-8")

    assert {
        "enabled": "enabled = false" in updated,
        "version_added": f'version = "{__version__}"' in updated,
        "thresholds_added": "[thresholds]" in updated,
        "missing_quality_gate": "version" in missing["slopgate"],
    } == {
        "enabled": True,
        "version_added": True,
        "thresholds_added": True,
        "missing_quality_gate": True,
    }


def test_update_toml_file_dry_run_reports_without_writing(tmp_path: Path) -> None:
    config_path = tmp_path / "slopgate.toml"
    original = "[slopgate]\nenabled = false\n"
    config_path.write_text(original, encoding="utf-8")

    missing = update_toml_file(config_path, dry_run=True)

    assert {
        "unchanged": config_path.read_text(encoding="utf-8"),
        "reported": "version" in missing["slopgate"],
    } == {
        "unchanged": original,
        "reported": True,
    }


@given(
    strategies.dictionaries(
        keys=SECTION_NAMES,
        values=KEY_VALUES,
        max_size=5,
    )
)
def test_diff_config_never_reports_present_keys_property(
    existing: dict[str, dict[str, object]],
) -> None:
    missing = diff_config(existing)
    overlapping_keys = {
        (section, key)
        for section, values in missing.items()
        for key in values
        if key in existing.get(section, {})
    }

    assert overlapping_keys == set()
