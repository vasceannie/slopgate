from __future__ import annotations

from tests.test_enrichment import (
    Path,
    mkdir,
    pretool_write_payload,
    write_text,
    evaluate_payload,
    support,
)


def _write_source_and_denial_reason(
    tmp_project: Path, relative_path: str, code: str, rule_id: str
) -> str:
    target = tmp_project / relative_path
    mkdir(target.parent, exist_ok=True)
    write_text(target, code)
    payload = pretool_write_payload(relative_path, code, str(tmp_project))
    result = evaluate_payload(payload)
    support.assert_denied_by(result, rule_id)
    return support.required_string(
        support.hook_output(result), "permissionDecisionReason"
    )


class TestPYCODE008Enrichment:
    """PY-CODE-008: long method denial includes function structure."""

    def test_shows_extraction_points(self, tmp_project: Path) -> None:
        """Denial should list if-blocks, loops, try-blocks as extraction points."""
        long_func = "def process_data(items):\n"
        long_func += "    if not items:\n        return []\n"
        long_func += "    for item in items:\n        pass\n"
        long_func += "    try:\n        result = compute()\n    except ValueError:\n        pass\n"
        # Pad to exceed 50 lines
        for i in range(45):
            long_func += f"    x_{i} = {i}\n"
        reason = _write_source_and_denial_reason(
            tmp_project, "src/processor.py", long_func, "PY-CODE-008"
        )
        assert "extraction" in reason.lower() or "structure" in reason.lower(), (
            f"Expected extraction hints in reason: {reason}"
        )

    def test_shows_split_strategy(self, tmp_project: Path) -> None:
        """Denial should include the split strategy suggestion."""
        long_func = "def big_func():\n"
        for i in range(55):
            long_func += f"    line_{i} = {i}\n"
        reason = _write_source_and_denial_reason(
            tmp_project, "src/big.py", long_func, "PY-CODE-008"
        )
        assert "split" in reason.lower() or "helper" in reason.lower(), (
            f"Expected split advice: {reason}"
        )


class TestPYCODE009Enrichment:
    def test_lists_parameters(self, tmp_project: Path) -> None:
        """Denial should list the actual parameter names."""
        src_dir = tmp_project / "src"
        mkdir(src_dir, exist_ok=True)
        code = (
            "def configure(host, port, user, password, database, timeout, retries):\n"
            "    pass\n"
        )
        write_text(src_dir / "db.py", code)

        payload = pretool_write_payload("src/db.py", code, str(tmp_project))
        result = evaluate_payload(payload)
        support.assert_denied_by(result, "PY-CODE-009")

        reason = support.required_string(
            support.hook_output(result), "permissionDecisionReason"
        )
        assert "`host`" in reason or "`port`" in reason, (
            f"Expected parameter names in reason: {reason}"
        )

    def test_finds_existing_dataclass(self, tmp_project: Path) -> None:
        """When file has dataclasses, enrichment mentions them."""
        src_dir = tmp_project / "src"
        mkdir(src_dir, exist_ok=True)
        code = (
            "from dataclasses import dataclass\n\n"
            "@dataclass\n"
            "class DbConfig:\n"
            "    host: str\n"
            "    port: int\n\n"
            "def configure(host, port, user, password, database, timeout, retries):\n"
            "    pass\n"
        )
        write_text(src_dir / "db.py", code)

        payload = pretool_write_payload("src/db.py", code, str(tmp_project))
        result = evaluate_payload(payload)
        support.assert_denied_by(result, "PY-CODE-009")

        reason = support.required_string(
            support.hook_output(result), "permissionDecisionReason"
        )
        assert "DbConfig" in reason, f"Expected existing dataclass ref: {reason}"


class TestPYCODE013RepoLocalEnrichment:
    def test_thin_wrapper_cites_repo_local_call_sites(self, tmp_project: Path) -> None:
        src_dir = tmp_project / "src"
        mkdir(src_dir, exist_ok=True)
        code = (
            "def load_config(path):\n"
            '    return {"path": path}\n\n'
            "def read_config(path):\n"
            "    return load_config(path)\n"
        )
        write_text(src_dir / "api.py", code)
        write_text(
            src_dir / "cli.py",
            "from .api import read_config\n\nVALUE = read_config('settings.toml')\n",
        )

        payload = pretool_write_payload("src/api.py", code, str(tmp_project))
        result = evaluate_payload(payload)
        support.assert_denied_by(result, "PY-CODE-013")
        reason = support.required_string(
            support.hook_output(result), "permissionDecisionReason"
        )

        assert "Local call sites" in reason
        assert "src/cli.py" in reason
        assert "read_config" in reason


class TestPYCODE015Enrichment:
    def test_shows_complexity_breakdown(self, tmp_project: Path) -> None:
        """Denial should break down the sources of complexity."""
        # Build a function with complexity > 10
        # Each if/elif adds 1, each loop adds 1, each `and`/`or` adds 1
        code = "def complex_func(x, y, z):\n"
        code += "    if x > 0 and y > 0:\n        a = 1\n"
        code += "    elif x < 0 or y < 0:\n        a = 2\n"
        code += "    elif x == 0:\n        a = 3\n"
        code += "    elif y == 0:\n        a = 4\n"
        code += "    else:\n        a = 5\n"
        code += "    for i in range(x):\n"
        code += "        if i > 0:\n            pass\n"
        code += "        elif i < 0:\n            pass\n"
        code += "    for j in range(y):\n"
        code += "        if j > 0 and j < 10:\n            pass\n"
        code += "    try:\n        compute()\n"
        code += "    except ValueError:\n        pass\n"
        code += "    except TypeError:\n        pass\n"
        reason = _write_source_and_denial_reason(
            tmp_project, "src/logic.py", code, "PY-CODE-015"
        )
        assert "branch" in reason.lower() or "if" in reason.lower(), (
            f"Expected complexity breakdown: {reason}"
        )


class TestPYCODE012Enrichment:
    def test_shows_envied_object_context(self, tmp_project: Path) -> None:
        """Denial should include advice about the envied object."""
        src_dir = tmp_project / "src"
        mkdir(src_dir, exist_ok=True)
        # Feature envy rule excludes parameters — use a module-level object
        # and access it enough times (>= min_accesses, default 6) with
        # >60% of total accesses targeting one object
        code = (
            "import config\n\n"
            "def process():\n"
            "    a = config.host\n"
            "    b = config.port\n"
            "    c = config.user\n"
            "    d = config.password\n"
            "    e = config.database\n"
            "    f = config.timeout\n"
            "    g = config.retries\n"
            "    return a, b, c, d, e, f, g\n"
        )
        write_text(src_dir / "envy.py", code)

        payload = pretool_write_payload("src/envy.py", code, str(tmp_project))
        result = evaluate_payload(payload)

        # Feature envy is decision="context", not deny — check findings directly
        envy_findings = [f for f in result.findings if f.rule_id == "PY-CODE-012"]
        assert len(envy_findings) >= 1, (
            f"Expected PY-CODE-012 finding, got: {[f.rule_id for f in result.findings]}"
        )
        msg = envy_findings[0].message
        assert msg is not None
        assert "moving" in msg.lower() or "restructur" in msg.lower(), (
            f"Expected refactoring advice: {msg}"
        )


class TestPYCODE013Enrichment:
    def test_shows_call_count(self, tmp_project: Path) -> None:
        """Denial should mention usage count when wrapper is called in same file."""
        code = (
            "def get_value(key):\n"
            "    return lookup(key)\n\n"
            "def main():\n"
            "    a = get_value('x')\n"
            "    b = get_value('y')\n"
            "    return a, b\n"
        )
        reason = _write_source_and_denial_reason(
            tmp_project, "src/wrappers.py", code, "PY-CODE-013"
        )
        assert "called" in reason.lower() or "time" in reason.lower(), (
            f"Expected usage info: {reason}"
        )
        assert "Replace each `get_value(...)` call with `lookup(...)`" in reason


class TestPYEXC002Enrichment:
    SILENT_EXCEPT_CODE = (
        "def load_config(path):\n"
        "    try:\n"
        "        data = read_file(path)\n"
        "        return parse_json(data)\n"
        "    except Exception:\n"
        "        return None\n"
    )

    def test_lists_called_functions(self, tmp_project: Path) -> None:
        """Denial should list functions called in the try block."""
        payload = pretool_write_payload(
            "src/config.py",
            self.SILENT_EXCEPT_CODE,
            str(tmp_project),
        )
        result = evaluate_payload(payload)
        support.assert_denied_by(result, "PY-EXC-002")

        reason = support.required_string(
            support.hook_output(result), "permissionDecisionReason"
        )
        assert "`read_file`" in reason or "`parse_json`" in reason, (
            f"Expected called function names: {reason}"
        )

    def test_includes_common_exceptions(self, tmp_project: Path) -> None:
        """Denial should include common specific exception suggestions."""
        payload = pretool_write_payload(
            "src/config.py",
            self.SILENT_EXCEPT_CODE,
            str(tmp_project),
        )
        result = evaluate_payload(payload)
        support.assert_denied_by(result, "PY-EXC-002")

        reason = support.required_string(
            support.hook_output(result), "permissionDecisionReason"
        )
        assert "FileNotFoundError" in reason or "ValueError" in reason, (
            f"Expected specific exception suggestions: {reason}"
        )
