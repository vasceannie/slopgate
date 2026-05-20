from __future__ import annotations

from tests.test_engine import (
    BashBuilder,
    WriteBuilder,
    assert_denied_by,
    assert_not_denied,
    evaluate_payload,
    finding_ids,
    pytest,
)

class TestSensitiveDataSafeSuffixes:
    """Test that .example, .sample, .template etc. bypass the sensitive data rule."""

    # --- Path-based tests (Write tool) ---

    @pytest.mark.parametrize(
        "file_path",
        [
            ".env.example",
            ".env.sample",
            ".env.template",
            ".env.defaults",
            ".env.dist",
            ".env.test",
            ".env.bak",
            "config/.env.example",
            "deploy/.env.template",
            "infra/staging/.env.sample",
        ],
    )
    def test_safe_suffix_path_allowed(
        self, pretool_write: WriteBuilder, file_path: str
    ) -> None:
        """Files with safe suffixes must NOT be blocked."""
        result = evaluate_payload(pretool_write(file_path, "DB_HOST=localhost\n"))
        assert_not_denied(result)
        assert "GLOBAL-BUILTIN-SENSITIVE-DATA" not in finding_ids(result), (
            f"safe-suffix env path {file_path} should not trigger sensitive-data protection"
        )

    @pytest.mark.parametrize(
        "file_path",
        [
            "project/.env",
            "project/.env.local",
            "project/.env.production",
            "project/.env.development",
            "config/.env",
            "deploy/.env.local",
        ],
    )
    def test_real_env_files_still_blocked(
        self, pretool_write: WriteBuilder, file_path: str
    ) -> None:
        """Actual secret .env files must still be blocked."""
        result = evaluate_payload(pretool_write(file_path, "SECRET_KEY=hunter2\n"))
        assert_denied_by(result, "GLOBAL-BUILTIN-SENSITIVE-DATA")
        assert "GLOBAL-BUILTIN-SENSITIVE-DATA" in finding_ids(result), (
            f"real env file {file_path} should remain blocked"
        )

    @pytest.mark.parametrize(
        "file_path",
        [
            ".ssh/id_rsa",
            ".aws/credentials",
            ".kube/config",
            "certs/server.pem",
            "certs/server.key",
            "keys/id_ed25519",
            "project/.npmrc",
            "project/.pypirc",
        ],
    )
    def test_other_sensitive_files_still_blocked(
        self, pretool_write: WriteBuilder, file_path: str
    ) -> None:
        """Non-.env sensitive files must still be blocked."""
        result = evaluate_payload(pretool_write(file_path, "secret stuff\n"))
        assert_denied_by(result, "GLOBAL-BUILTIN-SENSITIVE-DATA")
        assert "GLOBAL-BUILTIN-SENSITIVE-DATA" in finding_ids(result), (
            f"sensitive path {file_path} should remain blocked"
        )

    # --- Bash command tests ---

    @pytest.mark.parametrize(
        "command",
        [
            "cat .env.example",
            "cp .env.example .env",
            "diff .env.template .env.sample",
            "cat config/.env.defaults",
        ],
    )
    def test_safe_suffix_in_bash_allowed(
        self, pretool_bash: BashBuilder, command: str
    ) -> None:
        """Bash commands referencing safe-suffix files must NOT be blocked."""
        result = evaluate_payload(pretool_bash(command))
        assert_not_denied(result)
        assert "GLOBAL-BUILTIN-SENSITIVE-DATA" not in finding_ids(result), (
            f"safe-suffix command {command!r} should not be blocked as sensitive data"
        )

    @pytest.mark.parametrize(
        "command",
        [
            "cat project/.env",
            "cat ~/.ssh/id_rsa",
            "cat .aws/credentials",
            "cat project/.env.local",
            "cat project/.env.production",
        ],
    )
    def test_real_sensitive_bash_still_blocked(
        self, pretool_bash: BashBuilder, command: str
    ) -> None:
        """Bash commands referencing actual secrets must still be blocked."""
        result = evaluate_payload(pretool_bash(command))
        assert_denied_by(result, "GLOBAL-BUILTIN-SENSITIVE-DATA")
        assert "GLOBAL-BUILTIN-SENSITIVE-DATA" in finding_ids(result), (
            f"sensitive Bash command {command!r} should remain blocked"
        )

    # --- Docker compose files are NOT blocked ---

    @pytest.mark.parametrize(
        "file_path",
        [
            "docker-compose.yml",
            "docker-compose.yaml",
            "compose.yml",
            "compose.yaml",
            "docker-compose.override.yml",
            "docker-compose.prod.yml",
            "infra/docker-compose.yml",
            "Dockerfile",
            "deploy/Dockerfile.prod",
        ],
    )
    def test_docker_files_not_blocked(
        self, pretool_write: WriteBuilder, file_path: str
    ) -> None:
        """Docker and compose files must never be blocked by sensitive data rule."""
        result = evaluate_payload(
            pretool_write(
                file_path, "version: '3'\nservices:\n  web:\n    image: nginx\n"
            )
        )
        ids = finding_ids(result)
        assert "GLOBAL-BUILTIN-SENSITIVE-DATA" not in ids, (
            f"Docker file {file_path} should not be blocked by sensitive data rule"
        )

    # --- Edge cases (case sensitivity) ---

    def test_env_example_case_insensitive(self, pretool_write: WriteBuilder) -> None:
        """Safe suffix check must be case-insensitive."""
        result = evaluate_payload(pretool_write(".ENV.EXAMPLE", "DB=localhost\n"))
        assert_not_denied(result)
        assert "GLOBAL-BUILTIN-SENSITIVE-DATA" not in finding_ids(result), (
            "uppercase safe suffix should not trigger sensitive-data protection"
        )

    def test_env_example_uppercase(self, pretool_write: WriteBuilder) -> None:
        """Mixed-case safe suffix."""
        result = evaluate_payload(pretool_write(".env.Example", "DB=localhost\n"))
        assert_not_denied(result)
        assert "GLOBAL-BUILTIN-SENSITIVE-DATA" not in finding_ids(result), (
            "mixed-case safe suffix should not trigger sensitive-data protection"
        )

    def test_env_with_extra_dots_not_safe(self, pretool_write: WriteBuilder) -> None:
        """.env.local.bak is safe (ends with .bak) but .env.staging is not."""
        result_bak = evaluate_payload(
            pretool_write("project/.env.local.bak", "SECRET=x\n")
        )
        assert_not_denied(result_bak)
        assert "GLOBAL-BUILTIN-SENSITIVE-DATA" not in finding_ids(result_bak), (
            "safe .bak suffix should override env-looking path"
        )

        result_staging = evaluate_payload(
            pretool_write("project/.env.staging", "SECRET=x\n")
        )
        assert_denied_by(result_staging, "GLOBAL-BUILTIN-SENSITIVE-DATA")
        assert "GLOBAL-BUILTIN-SENSITIVE-DATA" in finding_ids(result_staging), (
            "unsafe env staging path should remain blocked"
        )

    def test_bash_mixed_safe_and_unsafe(self, pretool_bash: BashBuilder) -> None:
        """A command with both .env.example and .env — still blocked due to .env."""
        # The command mentions project/.env (no safe suffix) so it should still be blocked
        result = evaluate_payload(pretool_bash("cp .env.example project/.env"))
        # This should be blocked because /.env (without safe suffix) appears in the command
        assert_denied_by(result, "GLOBAL-BUILTIN-SENSITIVE-DATA")
        assert "GLOBAL-BUILTIN-SENSITIVE-DATA" in finding_ids(result), (
            "mixed safe and unsafe env command should remain blocked"
        )

class TestSensitiveDataSafeSuffixEdgeCases:
    """Edge cases for safe-suffix bypass: cert files, package files, unrelated paths."""

    def test_pem_example_allowed(self, pretool_write: WriteBuilder) -> None:
        """A .pem.example file should be allowed."""
        result = evaluate_payload(
            pretool_write("certs/server.pem.example", "-----BEGIN FAKE-----\n")
        )
        assert_not_denied(result)
        assert "GLOBAL-BUILTIN-SENSITIVE-DATA" not in finding_ids(result), (
            "certificate example files should remain allowed"
        )

    def test_key_example_allowed(self, pretool_write: WriteBuilder) -> None:
        """A .key.example file should be allowed."""
        result = evaluate_payload(
            pretool_write("certs/server.key.example", "fake-key-data\n")
        )
        assert_not_denied(result)
        assert "GLOBAL-BUILTIN-SENSITIVE-DATA" not in finding_ids(result), (
            "key example files should remain allowed"
        )

    def test_npmrc_example_allowed(self, pretool_write: WriteBuilder) -> None:
        """.npmrc.example should be allowed."""
        result = evaluate_payload(
            pretool_write(".npmrc.example", "registry=https://registry.npmjs.org/\n")
        )
        assert_not_denied(result)
        assert "GLOBAL-BUILTIN-SENSITIVE-DATA" not in finding_ids(result), (
            "npmrc example files should remain allowed"
        )

    def test_pypirc_template_allowed(self, pretool_write: WriteBuilder) -> None:
        """.pypirc.template should be allowed."""
        result = evaluate_payload(
            pretool_write(".pypirc.template", "[pypi]\nusername = __token__\n")
        )
        assert_not_denied(result)
        assert "GLOBAL-BUILTIN-SENSITIVE-DATA" not in finding_ids(result), (
            "pypirc template files should remain allowed"
        )

    def test_env_in_unrelated_path_not_blocked(
        self, pretool_write: WriteBuilder
    ) -> None:
        """A path like 'environment.py' shouldn't trigger the rule."""
        result = evaluate_payload(pretool_write("src/environment.py", "ENV = 'prod'\n"))
        assert_not_denied(result)
        assert "GLOBAL-BUILTIN-SENSITIVE-DATA" not in finding_ids(result), (
            "environment.py should not be treated as an env secret file"
        )

    def test_dotenv_package_not_blocked(self, pretool_write: WriteBuilder) -> None:
        """A path like 'node_modules/dotenv/lib/main.js' shouldn't be blocked."""
        result = evaluate_payload(
            pretool_write("node_modules/dotenv/lib/main.js", "module.exports = {}\n")
        )
        assert_not_denied(result)
        assert "GLOBAL-BUILTIN-SENSITIVE-DATA" not in finding_ids(result), (
            "dotenv package paths should not be treated as env secret files"
        )

    def test_python_key_module_not_blocked(self, pretool_write: WriteBuilder) -> None:
        """A dotted module path like src.keys is not a .key secret file."""
        result = evaluate_payload(pretool_write("src.keys", "API_KEYS = {}\n"))
        assert_not_denied(result)
        assert "GLOBAL-BUILTIN-SENSITIVE-DATA" not in finding_ids(result), (
            "dotted module names should not be classified as secret key files"
        )

    def test_key_file_still_blocked(self, pretool_write: WriteBuilder) -> None:
        result = evaluate_payload(pretool_write("certs/server.key", "secret\n"))
        assert_denied_by(result, "GLOBAL-BUILTIN-SENSITIVE-DATA")
        assert "GLOBAL-BUILTIN-SENSITIVE-DATA" in finding_ids(result), (
            ".key file writes should remain blocked as sensitive data"
        )
