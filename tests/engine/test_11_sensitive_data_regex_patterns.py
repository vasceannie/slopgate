from __future__ import annotations
from tests.test_engine import Callable, cast, re


class TestSensitiveDataRegexPatterns:
    """Test that the regex compilation in SensitiveDataRule works correctly."""

    @staticmethod
    def compile_sensitive_patterns() -> Callable[[list[str]], list[re.Pattern[str]]]:
        from slopgate.rules import common

        return cast(
            Callable[[list[str]], list[re.Pattern[str]]],
            common.__dict__["compile_sensitive_patterns"],
        )

    def test_pattern_auto_escaping(self) -> None:
        """Plain substring patterns are auto-escaped (dots become literal)."""
        compiled = self.compile_sensitive_patterns()(["/.env"])
        assert compiled[0].search("/project/.env"), "Should match /.env"
        assert not compiled[0].search("/xenv"), "Escaped dot should not match 'x'"

    def test_regex_pattern_preserved(self) -> None:
        """Patterns with regex metacharacters are compiled as-is."""
        compiled = self.compile_sensitive_patterns()(
            ["\\.env\\.(local|staging|production)$"]
        )
        assert compiled[0].search("config/.env.local"), "Should match .env.local"
        assert compiled[0].search("config/.env.production"), (
            "Should match .env.production"
        )
        assert not compiled[0].search("config/.env.example"), (
            "Should not match .env.example"
        )

    def test_empty_patterns_skipped(self) -> None:
        """Empty or whitespace-only patterns are silently skipped."""
        compiled = self.compile_sensitive_patterns()(["", "  ", "/.env"])
        assert len(compiled) == 1, f"Expected 1 compiled pattern, got {len(compiled)}"

    def test_key_extension_pattern_does_not_match_key_prefix(self) -> None:
        compiled = self.compile_sensitive_patterns()([".key"])
        pattern = compiled[0]
        assert pattern.search("certs/server.key"), "Expected .key suffix to match"
        assert pattern.search("certs/server.key.txt"), (
            "Expected .key path segment to match"
        )
        assert not pattern.search("src.keys"), "Should not match .keys extension"
        assert not pattern.search("src/keys.py"), "Should not match keys.py prefix"

    def test_safe_suffixes_constant(self) -> None:
        """Verify the safe suffixes list includes expected entries."""
        from slopgate.rules.common import SensitiveDataRule

        rule = SensitiveDataRule()
        expected = {
            ".example",
            ".sample",
            ".template",
            ".defaults",
            ".dist",
            ".test",
            ".bak",
        }
        assert expected == set(rule.SAFE_SUFFIXES), (
            f"SAFE_SUFFIXES mismatch: expected {expected}, got {set(rule.SAFE_SUFFIXES)}"
        )
