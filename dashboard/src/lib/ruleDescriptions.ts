/**
 * Human-readable descriptions for slopgate rule IDs.
 * Sourced from Python class names and regex rule messages.
 */
export const RULE_DESCRIPTIONS: Record<string, string> = {
  // Python AST rules
  "BASELINE-001": "Baseline guard — enforces project standards",
  "BUILTIN-ENFORCE-FULL-READ": "Requires full file read before edits",
  "BUILTIN-INJECT-PROMPT": "Prompt injection detection",
  "BUILTIN-PROTECTED-PATHS": "Blocks access to protected file paths",
  "BUILTIN-RULEBOOK-SECURITY": "Rulebook security enforcement",
  "CONFIG-001": "Config change guard",
  "CONFIG-002": "Config violation",
  "ERRORS-BASH-001": "Bash output error detection",
  "ERRORS-FAIL-001": "Bash failure reinforcement — retries on error",
  "GIT-001": "Blocks --no-verify on git commits/pushes",
  "GIT-002": "Git quality bypass detection",
  "GLOBAL-BUILTIN-HOOK-INFRA-EXEC": "Protects hook infrastructure from exec",
  "GLOBAL-BUILTIN-SENSITIVE-DATA": "Blocks sensitive data exposure (keys, tokens)",
  "GLOBAL-BUILTIN-SYSTEM-PROTECTION": "System file protection",
  "LG-API-001": "LangGraph deprecated API usage",
  "LG-NODE-001": "LangGraph state mutation detection",
  "LG-STATE-001": "LangGraph state reducer check",
  "PY-CODE-008": "Python method too long",
  "PY-CODE-009": "Python function has too many parameters",
  "PY-CODE-010": "Python line too long",
  "PY-CODE-011": "Python deeply nested code",
  "PY-CODE-012": "Python feature envy — method uses another class too much",
  "PY-CODE-013": "Python thin wrapper — unnecessary delegation layer",
  "PY-CODE-014": "Python god class — class does too much",
  "PY-CODE-015": "Python cyclomatic complexity too high",
  "PY-CODE-016": "Python dead code detection",
  "PY-CODE-017": "Python flat file siblings — missing package structure",
  "PY-IMPORT-001": "Python import fan-out too wide",
  "QUALITY-POST-001": "Post-edit quality check",
  "REMIND-SEARCH-001": "Reminds to search before reimplementing",
  "SESSION-001": "Session start context injection",
  "SHELL-001": "Shell quality bypass detection",
  "STOP-001": "Ignores preexisting issues",
  "STOP-002": "Requires make quality pass before completion",
  "WARN-BASELINE-001": "Baseline warning — threshold exceeded",
  "WARN-BASELINE-002": "Baseline warning — secondary threshold",
  "WARN-LARGE-001": "Warns on large file edits",

  // Regex rules
  "PY-LOG-001": "Blocks stdlib logging — use project logger",
  "PY-EXC-001": "Blocks broad except-and-log — catch specific exceptions",
  "PY-EXC-002": "Blocks silent except pass/continue/return None",
  "PY-TYPE-001": "Blocks Python `Any` type — use concrete types",
  "PY-TYPE-002": "Blocks type/lint suppression comments",
  "TS-LINT-001": "Blocks JS/TS lint suppression injection via bash",
  "TS-LINT-002": "Blocks JS/TS lint suppression comments",
  "TS-TYPE-001": "Blocks TypeScript `any` — use specific types",
  "TS-TYPE-002": "Blocks unsafe TS assertions (as any/unknown/never)",
  "TS-QUALITY-003": "Blocks JS/TS TODO/FIXME markers",
  "STYLE-004": "Blocks complex inline styles — use tokens/classes",
  "STYLE-005": "Blocks hardcoded typography/color hex values",
  "RS-QUALITY-001": "Blocks Rust TODO/FIXME markers",
  "RS-QUALITY-002": "Blocks Rust unwrap() — use ? or expect",
  "RS-QUALITY-003": "Blocks Rust magic numbers",
  "PY-SHELL-001": "Blocks shell edits to Python source files",
  "PY-QUALITY-004": "Blocks datetime.now() as exception fallback",
  "PY-QUALITY-005": "Blocks except-log-return-empty patterns",
  "PY-QUALITY-006": "Blocks except-log-return-None patterns",
  "PY-QUALITY-007": "Blocks Python TODO/FIXME/HACK markers",
  "PY-QUALITY-008": "Blocks commented-out code blocks",
  "PY-QUALITY-009": "Blocks hardcoded file paths — use config/pathlib",
  "PY-QUALITY-010": "Blocks magic numbers outside constants",
  "PY-TEST-001": "Blocks bare asserts without messages",
  "PY-TEST-002": "Blocks test smells (sleep, print, hardcoded)",
  "PY-TEST-003": "Blocks assert-in-loop — use parametrize",
  "PY-TEST-004": "Global fixtures must be in conftest.py",
  "PY-LINTER-001": "Blocks edits to Python linter configs",
  "PY-LINTER-002": "Blocks shell edits to Python linter configs",
  "FE-LINTER-001": "Blocks edits to frontend linter configs",
  "FE-LINTER-002": "Blocks shell edits to frontend linter configs",
  "QA-PATH-001": "Blocks direct edits to code-quality tests",
  "QA-PATH-002": "Blocks shell edits to code-quality tests",
  "QA-PATH-003": "Blocks edits to tests/quality/ (except baselines)",
  "QA-PATH-004": "Blocks shell edits to tests/quality/",
};

/** Look up description, return undefined if unknown */
export function getRuleDescription(ruleId: string): string | undefined {
  return RULE_DESCRIPTIONS[ruleId];
}

/** Get short label: description if available, otherwise the rule ID itself */
export function getRuleLabel(ruleId: string): string {
  return RULE_DESCRIPTIONS[ruleId] || ruleId;
}
