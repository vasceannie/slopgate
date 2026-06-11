from __future__ import annotations

from slopgate._types import is_object_dict
from tests.test_engine import (
    MonkeyPatch,
    Path,
    evaluate_payload,
    post_edit_bash_payload,
    write_config_from_defaults,
    write_slopgate,
)


def test_post_edit_quality_missing_python_reports_environment_failure(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    repo = write_slopgate(tmp_path / "repo_quality_missing_python")

    def enable_missing_python(defaults: dict[str, object]) -> None:
        post_edit_quality = defaults["post_edit_quality"]
        assert is_object_dict(post_edit_quality), (
            "post_edit_quality config should be a mapping"
        )
        post_edit_quality["enabled"] = True
        post_edit_quality["block_on_failure"] = True
        post_edit_quality["commands_by_language"] = {
            "python": ["missing-python {first_file}"]
        }

    write_config_from_defaults(tmp_path, monkeypatch, enable_missing_python)

    result = evaluate_payload(post_edit_bash_payload(repo, "printf 'x = 1\\n' > app.py"))
    finding = next(
        item for item in result.findings if item.rule_id == "QUALITY-POST-001"
    )

    assert finding.message is not None, (
        "missing executable quality failure should include a message"
    )
    assert "could not run" in finding.message, (
        "missing executable should be classified as environment/tooling"
    )
    assert "missing-python" in finding.message, (
        "missing executable message should name the binary"
    )
    assert "before treating this as code quality" in finding.message, (
        "message should not blame source quality for an env failure"
    )
