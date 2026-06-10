from __future__ import annotations

from pytest import MonkeyPatch

from tests.test_enrichment import (
    Path,
    mkdir,
    pretool_write_payload,
    write_text,
    evaluate_payload,
    support,
)
from slopgate.enrichment.quality_enrichers import _magic_numbers


class TestPYLOG001Enrichment:
    LOG_CODE = "import logging\n\nlogger = logging.getLogger(__name__)\n"

    def test_detects_structlog_in_deps(self, tmp_project: Path) -> None:
        """When project uses structlog, denial mentions it."""
        req = tmp_project / "requirements.txt"
        write_text(req, "structlog==23.1.0\nrequests\n")

        payload = pretool_write_payload(
            "src/app.py",
            self.LOG_CODE,
            str(tmp_project),
        )
        result = evaluate_payload(payload)
        support.assert_denied_by(result, "PY-LOG-001")

        reason = support.required_string(
            support.hook_output(result), "permissionDecisionReason"
        )
        assert "structlog" in reason.lower(), f"Expected structlog mention: {reason}"

    def test_finds_project_logger(self, tmp_project: Path) -> None:
        """When project has a logger module, denial points to it."""
        src_dir = tmp_project / "src"
        mkdir(src_dir, exist_ok=True)
        write_text(
            src_dir / "logger.py",
            "import structlog\n\ndef get_logger(name):\n    return structlog.get_logger(name)\n",
        )

        payload = pretool_write_payload(
            "src/app.py",
            self.LOG_CODE,
            str(tmp_project),
        )
        result = evaluate_payload(payload)
        support.assert_denied_by(result, "PY-LOG-001")

        reason = support.required_string(
            support.hook_output(result), "permissionDecisionReason"
        )
        assert "logger.py" in reason, f"Expected logger.py reference: {reason}"


class TestPYTYPE002Enrichment:
    def test_identifies_specific_suppression(self, tmp_project: Path) -> None:
        """Denial should identify the specific type: ignore code."""
        code = "def process(x):\n    return x.value  # type: ignore[union-attr]\n"
        payload = pretool_write_payload("src/proc.py", code, str(tmp_project))
        result = evaluate_payload(payload)
        support.assert_denied_by(result, "PY-TYPE-002")

        reason = support.required_string(
            support.hook_output(result), "permissionDecisionReason"
        )
        assert "union-attr" in reason, f"Expected error code in reason: {reason}"

    def test_gives_fix_advice_for_arg_type(self, tmp_project: Path) -> None:
        """Denial should give specific fix advice for arg-type errors."""
        code = "def send(msg):\n    channel.post(msg)  # type: ignore[arg-type]\n"
        payload = pretool_write_payload("src/sender.py", code, str(tmp_project))
        result = evaluate_payload(payload)
        support.assert_denied_by(result, "PY-TYPE-002")

        reason = support.required_string(
            support.hook_output(result), "permissionDecisionReason"
        )
        assert "arg-type" in reason, f"Expected arg-type advice: {reason}"


class TestPYQUALITY010Enrichment:
    def test_finds_constants_module(self, tmp_project: Path) -> None:
        """When project has constants.py, denial points to it."""
        src_dir = tmp_project / "src"
        mkdir(src_dir, exist_ok=True)
        write_text(src_dir / "constants.py", "MAX_RETRIES = 3\nTIMEOUT = 30\n")

        # Magic numbers regex requires 3+ digits (starting with 2-9) or 4+ digits
        code = "def retry():\n    timeout = 300\n    if timeout > 500:\n        pass\n"
        payload = pretool_write_payload("src/retry.py", code, str(tmp_project))
        result = evaluate_payload(payload)
        support.assert_denied_by(result, "PY-QUALITY-010")

        reason = support.required_string(
            support.hook_output(result), "permissionDecisionReason"
        )
        assert "constants.py" in reason, f"Expected constants.py reference: {reason}"
        assert "Nearby importable constants" in reason, (
            f"Expected nearby constant suggestions: {reason}"
        )
        assert "from constants import MAX_RETRIES, TIMEOUT" in reason, (
            f"Expected importable constants in reason: {reason}"
        )

    def test_suggests_exact_importable_constant(self, tmp_project: Path) -> None:
        """When constants.py has the literal value, denial suggests importing it."""
        src_dir = tmp_project / "src"
        mkdir(src_dir, exist_ok=True)
        write_text(
            src_dir / "constants.py",
            "MAX_RETRIES = 3\nAPI_TIMEOUT_SECONDS = 300\nTIMEOUT_CEILING = 500\n",
        )

        code = "def retry():\n    timeout = 300\n    if timeout > 500:\n        pass\n"
        payload = pretool_write_payload("src/retry.py", code, str(tmp_project))
        result = evaluate_payload(payload)
        support.assert_denied_by(result, "PY-QUALITY-010")

        reason = support.required_string(
            support.hook_output(result), "permissionDecisionReason"
        )
        assert "Exact constant match" in reason, f"Expected exact match: {reason}"
        assert "API_TIMEOUT_SECONDS = 300" in reason, (
            f"Expected exact constant: {reason}"
        )
        assert "from constants import API_TIMEOUT_SECONDS" in reason, (
            f"Expected exact import suggestion: {reason}"
        )

    def test_suggests_creating_constants(self, tmp_project: Path) -> None:
        """When no constants module exists, suggest creating one."""
        code = "def retry():\n    timeout = 3600\n    pass\n"
        payload = pretool_write_payload("src/retry.py", code, str(tmp_project))
        result = evaluate_payload(payload)
        support.assert_denied_by(result, "PY-QUALITY-010")

        reason = support.required_string(
            support.hook_output(result), "permissionDecisionReason"
        )
        assert "constants" in reason.lower(), f"Expected constants suggestion: {reason}"

    def test_names_triggered_literals_and_lines(self, tmp_project: Path) -> None:
        """Denial should point agents at exact candidate literals before retrying."""
        code = "def retry():\n    timeout = 300\n    if timeout > 500:\n        pass\n"
        payload = pretool_write_payload("src/retry.py", code, str(tmp_project))
        result = evaluate_payload(payload)
        support.assert_denied_by(result, "PY-QUALITY-010")

        reason = support.required_string(
            support.hook_output(result), "permissionDecisionReason"
        )
        assert "Triggered magic number candidates" in reason
        assert "line 2: 300" in reason
        assert "line 3: 500" in reason

    def test_negative_magic_number_is_not_double_reported(
        self, tmp_project: Path
    ) -> None:
        code = "def retry(timeout):\n    if timeout < -300:\n        return False\n    return True\n"
        payload = pretool_write_payload("src/retry.py", code, str(tmp_project))
        result = evaluate_payload(payload)
        support.assert_denied_by(result, "PY-QUALITY-010")

        reason = support.required_string(
            support.hook_output(result), "permissionDecisionReason"
        )
        assert "line 2: -300" in reason
        assert "line 2: 300" not in reason


class TestPYQUALITY009Enrichment:
    def test_finds_path_config(self, tmp_project: Path) -> None:
        """When project has path config, denial points to it."""
        src_dir = tmp_project / "src"
        mkdir(src_dir, exist_ok=True)
        write_text(
            src_dir / "config.py",
            "from pathlib import Path\nBASE_DIR = Path(__file__).parent.parent\n",
        )

        code = 'DATA = "/home/user/data/file.csv"\n'
        payload = pretool_write_payload("src/loader.py", code, str(tmp_project))
        result = evaluate_payload(payload)
        support.assert_denied_by(result, "PY-QUALITY-009")

        reason = support.required_string(
            support.hook_output(result), "permissionDecisionReason"
        )
        assert "config.py" in reason, f"Expected config.py reference: {reason}"

    def test_suggests_pathlib_pattern(self, tmp_project: Path) -> None:
        """When no path config exists, suggest pathlib pattern."""
        code = 'DATA = "/home/user/data/file.csv"\n'
        payload = pretool_write_payload("src/loader.py", code, str(tmp_project))
        result = evaluate_payload(payload)
        support.assert_denied_by(result, "PY-QUALITY-009")

        reason = support.required_string(
            support.hook_output(result), "permissionDecisionReason"
        )
        assert "pathlib" in reason.lower() or "Path(" in reason, (
            f"Expected pathlib suggestion: {reason}"
        )


class TestEnrichmentConstantIndexScope:
    def test_unrelated_quality_rule_does_not_build_constant_index(
        self, tmp_project: Path, monkeypatch: MonkeyPatch
    ) -> None:
        calls: list[Path] = []

        def _track_build(root: Path, **_: object) -> object:
            calls.append(root)
            return object()

        monkeypatch.setattr(
            _magic_numbers,
            "build_project_constant_index",
            _track_build,
        )

        code = 'DATA = "/home/user/data/file.csv"\n'
        payload = pretool_write_payload("src/loader.py", code, str(tmp_project))
        result = evaluate_payload(payload)
        support.assert_denied_by(result, "PY-QUALITY-009")
        assert calls == []
