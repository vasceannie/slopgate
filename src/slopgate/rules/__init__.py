from __future__ import annotations

__all__ = [
    "HookContext",
    "DENY",
    "PERMISSION_REQUEST",
    "POST_TOOL_USE",
    "PRE_TOOL_USE",
    "SESSION_ID",
    "RuleFinding",
    "Severity",
    "Rule",
    "is_edit_like_tool",
    "FullFileReadRule",
    "GitNoVerifyRule",
    "PostEditQualityRule",
    "PostEditLintRule",
    "PromptContextRule",
    "ProtectedPathsRule",
    "SearchReminderRule",
    "SensitiveDataRule",
    "SystemProtectionRule",
    "RegexRule",
    "LangGraphDeprecatedAPIRule",
    "LangGraphStateMutationRule",
    "LangGraphStateReducerRule",
    "BaselineGuardRule",
    "BashFailureReinforcementRule",
    "BashOutputErrorRule",
    "ConfigChangeGuardRule",
    "HookInfraExecProtectionRule",
    "IgnorePreexistingRule",
    "RepoEnrollmentProtectionRule",
    "RequireQualityCheckRule",
    "RulebookSecurityRule",
    "SessionStartContextRule",
    "WarnLargeFileRule",
    "_PYTHON_AST_IMPORT_REPORTED",
    "_python_ast_import_reported",
]

from slopgate.context import HookContext
from slopgate.constants import (
    DENY,
    PERMISSION_REQUEST,
    POST_TOOL_USE,
    PRE_TOOL_USE,
    SESSION_ID,
)
from slopgate.models import RuleFinding, Severity
from slopgate.rules.base import Rule
from slopgate.util.payloads import is_edit_like_tool
from slopgate.rules.common import (
    FullFileReadRule,
    GitNoVerifyRule,
    PostEditQualityRule,
    PostEditLintRule,
    PromptContextRule,
    ProtectedPathsRule,
    SearchReminderRule,
    SensitiveDataRule,
    SystemProtectionRule,
)
from slopgate.rules.regex_rule import RegexRule
from slopgate.rules.langgraph import (
    LangGraphDeprecatedAPIRule,
    LangGraphStateMutationRule,
    LangGraphStateReducerRule,
)
from slopgate.rules.baseline_guard import BaselineGuardRule
from slopgate.rules.error_rules import (
    BashFailureReinforcementRule,
    BashOutputErrorRule,
)
from slopgate.rules.stop_rules import (
    ConfigChangeGuardRule,
    HookInfraExecProtectionRule,
    IgnorePreexistingRule,
    RepoEnrollmentProtectionRule,
    RequireQualityCheckRule,
    RulebookSecurityRule,
    SessionStartContextRule,
    WarnLargeFileRule,
)


_PYTHON_AST_IMPORT_ERROR: Exception | None = None
_PYTHON_AST_IMPORT_REPORTED = False

# Backward-compatible aliases for older internal references.
_python_ast_import_error: Exception | None = None
_python_ast_import_reported = False


class PythonAstImportFailureRule(Rule):
    rule_id = "PY-AST-IMPORT-001"
    title = "Python AST engine unavailable"
    events = (PRE_TOOL_USE, PERMISSION_REQUEST, POST_TOOL_USE)

    def __init__(self, error: Exception) -> None:
        self._error = error

    def evaluate(self, ctx: HookContext) -> list[RuleFinding]:
        decision = None
        if is_edit_like_tool(ctx.tool_name):
            decision = (
                DENY
                if ctx.event_name in (PRE_TOOL_USE, PERMISSION_REQUEST)
                else "block"
            )
        blocking = decision is not None
        return [
            RuleFinding(
                rule_id=self.rule_id,
                title=self.title,
                severity=Severity.HIGH if blocking else Severity.MEDIUM,
                decision=decision,
                message=(
                    "Python AST checks are unavailable due to import failure. "
                    "Non-edit commands may continue; Python edits remain blocked "
                    "until Slopgate's AST rule package imports cleanly."
                ),
                additional_context=repr(self._error),
                metadata={"kind": "import_error", "blocking": blocking},
            )
        ]


def _trace_python_ast_import_error(ctx: HookContext, error: Exception) -> None:
    ctx.trace.rule(
        {
            "platform": "any",
            "event_name": ctx.event_name,
            SESSION_ID: ctx.session_id,
            "tool_name": ctx.tool_name,
            "rule_id": "PY-AST-IMPORT-001",
            "severity": "high",
            "decision": None,
            "message": "Python AST rules disabled due to import error",
            "additional_context": repr(error),
            "metadata": {"kind": "import_error"},
        }
    )


def _python_ast_import_failure_rules(ctx: HookContext) -> list[Rule] | None:
    global _python_ast_import_reported

    current_error = _PYTHON_AST_IMPORT_ERROR or _python_ast_import_error
    already_reported = _PYTHON_AST_IMPORT_REPORTED or _python_ast_import_reported
    if current_error is None:
        return None
    if not already_reported:
        _python_ast_import_reported = True
        _trace_python_ast_import_error(ctx, current_error)
    return [PythonAstImportFailureRule(current_error)]


def _import_python_ast_rule_classes() -> tuple[type[Rule], ...]:
    from slopgate.rules.python_ast import (
        PythonAstHealthRule,
        PythonBoundaryLoggingRule,
        PythonBroadExceptLoggerRule,
        PythonCyclomaticComplexityRule,
        PythonDeadCodeRule,
        PythonDeepNestingRule,
        PythonFeatureEnvyRule,
        PythonFlatFileSiblingsRule,
        PythonGodClassRule,
        PythonImportAliasRule,
        PythonImportFanoutRule,
        PythonLongLineRule,
        PythonLongMethodRule,
        PythonLongParameterRule,
        PythonModuleSizeRule,
        PythonPrivateImportChainRule,
        PythonPytestAsyncioRule,
        PythonSilentExceptRule,
        PythonThinWrapperRule,
    )

    return (
        PythonAstHealthRule,
        PythonBoundaryLoggingRule,
        PythonBroadExceptLoggerRule,
        PythonSilentExceptRule,
        PythonLongMethodRule,
        PythonLongParameterRule,
        PythonLongLineRule,
        PythonModuleSizeRule,
        PythonDeepNestingRule,
        PythonFeatureEnvyRule,
        PythonThinWrapperRule,
        PythonGodClassRule,
        PythonCyclomaticComplexityRule,
        PythonDeadCodeRule,
        PythonFlatFileSiblingsRule,
        PythonImportAliasRule,
        PythonPrivateImportChainRule,
        PythonPytestAsyncioRule,
        PythonImportFanoutRule,
    )


def _build_python_ast_rules(ctx: HookContext) -> list[Rule]:
    global _python_ast_import_error

    if _PYTHON_AST_IMPORT_ERROR is not None or _python_ast_import_error is not None:
        return []

    try:
        rule_classes = _import_python_ast_rule_classes()
    except Exception as exc:  # pragma: no cover - exercised in import-failure test
        _python_ast_import_error = exc
        return _build_python_ast_rules(ctx)
    return [rule_class() for rule_class in rule_classes]


def build_always_on_rules(ctx: HookContext) -> list[Rule]:
    rules: list[Rule] = [
        ProtectedPathsRule(),
        SensitiveDataRule(),
        SystemProtectionRule(),
    ]
    import_failure = _python_ast_import_failure_rules(ctx)
    if import_failure is not None:
        rules.extend(import_failure)
    return rules


def build_repo_strict_rules(ctx: HookContext) -> list[Rule]:
    rules: list[Rule] = [
        PromptContextRule(),
        FullFileReadRule(),
        GitNoVerifyRule(),
        SearchReminderRule(),
        PostEditQualityRule(),
        PostEditLintRule(),
        BaselineGuardRule(),
        IgnorePreexistingRule(),
        RequireQualityCheckRule(),
        WarnLargeFileRule(),
        HookInfraExecProtectionRule(),
        RepoEnrollmentProtectionRule(),
        RulebookSecurityRule(),
        ConfigChangeGuardRule(),
        SessionStartContextRule(),
        BashOutputErrorRule(),
        BashFailureReinforcementRule(),
        LangGraphStateReducerRule(),
        LangGraphStateMutationRule(),
        LangGraphDeprecatedAPIRule(),
    ]
    rules.extend(_build_python_ast_rules(ctx))
    rules.extend(
        RegexRule(
            config=regex_rule,
            enabled=ctx.config.enabled_rules.get(regex_rule.rule_id, True),
        )
        for regex_rule in ctx.config.regex_rules
    )
    return rules


def build_rules(ctx: HookContext) -> list[Rule]:
    """Backward-compatible aggregate of always-on and repo-strict rules."""
    return [*build_always_on_rules(ctx), *build_repo_strict_rules(ctx)]
