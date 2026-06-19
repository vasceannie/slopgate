import { getRuleDescription } from "@/lib/ruleDescriptions";
import type { RuleMetadata, Severity, SlopgateConfig } from "@/types/slopgate";
export const QUALITY_LINT_RULE_ID = "QUALITY-LINT-001";

export const HOOK_ACTIONS = ["deny", "ask", "block", "allow", "context", "warn"] as const;

export const HOOK_EVENT_OPTIONS = [
  "PreToolUse",
  "PermissionRequest",
  "PostToolUse",
  "PostToolUseFailure",
  "UserPromptSubmit",
  "Stop",
] as const;

export const CLI_RULE_IDS = [
  "assertion-free-test",
  "assertion-roulette",
  "banned-any",
  "boundary-logging",
  "broad-except-swallow",
  "conditional-assertion",
  "deep-nesting",
  "deprecated-pattern",
  "dead-code",
  "direct-get-logger",
  "duplicate-call-sequence",
  "eager-test",
  "feature-envy",
  "fixture-outside-conftest",
  "flat-sibling-files",
  "god-class",
  "hand-built-test-payload",
  "high-complexity",
  "hypothesis-candidate",
  "import-alias",
  "import-fanout",
  "langgraph-deprecated-api",
  "langgraph-state-mutation",
  "langgraph-state-reducer",
  "long-line",
  "long-method",
  "long-test",
  "missing-integration-test",
  "mock-theater",
  "mocked-integration-test",
  "obsolete-or-deprecated-test",
  "oversized-module",
  "oversized-module-soft",
  "python-parse-error",
  "private-import-chain",
  "pytest-asyncio-pattern",
  "repeated-code-block",
  "repeated-magic-number",
  "repeated-string-literal",
  "schema-bypass-test-data",
  "semantic-clone",
  "silent-datetime-fallback",
  "silent-except",
  "too-many-params",
  "type-suppression",
  "unnecessary-wrapper",
  "untested-production-code",
  "weak-test-assertion",
  "wrong-logger-name",
] as const;

export const CLI_RULE_ID_SET = new Set<string>(CLI_RULE_IDS);
export const CLI_EXECUTABLE_REGEX_TARGETS = new Set<string>(["content", "path"]);

export const CLI_DEFAULT_OFF_RULE_IDS = new Set<string>([
  "dead-code",
  "boundary-logging",
  "feature-envy",
  "flat-sibling-files",
  "import-alias",
  "import-fanout",
  "langgraph-deprecated-api",
  "langgraph-state-mutation",
  "langgraph-state-reducer",
  "private-import-chain",
  "pytest-asyncio-pattern",
]);

export const CLI_CATEGORY = { label: "CLI · Batch lint", emoji: "🧪" };

export const COMMAND_ONLY_RULE_PREFIXES = ["GIT-", "REMIND-", "PY-SHELL-", "SHELL-"] as const;

export const CONFIG_SAFETY_RULE_PREFIXES = ["BASELINE-", "CONFIG-", "FE-LINTER-", "PY-LINTER-", "QA-PATH-", "WARN-BASELINE-"] as const;

export const SESSION_LIFECYCLE_RULE_PREFIXES = [
  "BUILTIN-ENFORCE-FULL-READ",
  "BUILTIN-INJECT-PROMPT",
  "REPO-ENROLL-",
  "SESSION-",
  "STOP-",
  "WARN-LARGE-",
] as const;

export function hasAnyPrefix(rule_id: string, prefixes: readonly string[]): boolean {
  return prefixes.some((prefix) => rule_id.startsWith(prefix));
}

export function cliUnsupportedReason(rule_id: string, regexRule?: { target: string }): string {
  if (regexRule?.target === "command") return "command only";
  if (rule_id === "BUILTIN-PROTECTED-PATHS") return "protected mutation";
  if (hasAnyPrefix(rule_id, CONFIG_SAFETY_RULE_PREFIXES)) return "config safety";
  if (hasAnyPrefix(rule_id, COMMAND_ONLY_RULE_PREFIXES)) return "command only";
  if (hasAnyPrefix(rule_id, SESSION_LIFECYCLE_RULE_PREFIXES)) {
    return "session lifecycle";
  }
  return "runtime payload";
}

export function formatCliTitle(rule_id: string): string {
  return rule_id
    .split("-")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

export function directHookRuleCliCounterparts(config: SlopgateConfig): Record<string, string[]> {
  return Object.fromEntries(Object.entries(config.rule_counterparts).filter(([rule_id]) => rule_id !== QUALITY_LINT_RULE_ID));
}

export function hookCounterpartsForCli(rule_id: string, counterparts: Record<string, string[]>): string[] {
  return Object.entries(counterparts)
    .filter(([_hookRuleId, cliRuleIds]) => cliRuleIds.includes(rule_id))
    .map(([hookRuleId]) => hookRuleId);
}

export function surfaceHookEnabled(config: SlopgateConfig, rule_id: string): boolean {
  const surfaceEnabled = config.rule_surfaces[rule_id]?.hook?.enabled;
  if (surfaceEnabled !== undefined) return surfaceEnabled;
  const enabledVal = config.enabled_rules[rule_id];
  return enabledVal === undefined ? true : Boolean(enabledVal);
}

export function surfaceCliEnabled(
  config: SlopgateConfig,
  rule_id: string,
  cliCounterparts: string[],
  defaultEnabled: boolean,
): { enabled: boolean; partiallyEnabled: boolean } {
  const surfaceEnabled = config.rule_surfaces[rule_id]?.cli?.enabled;
  if (surfaceEnabled !== undefined) {
    return { enabled: surfaceEnabled, partiallyEnabled: false };
  }
  const cliStates = cliCounterparts.map((cliRuleId) => config.enabled_cli_rules[cliRuleId] ?? defaultEnabled);
  const enabled = cliStates.length > 0 ? cliStates.every(Boolean) : defaultEnabled;
  return {
    enabled,
    partiallyEnabled: cliStates.some(Boolean) && !enabled,
  };
}

export function hookEventsForRule(config: SlopgateConfig, rule_id: string): string[] {
  return config.rule_surfaces[rule_id]?.hook?.events ?? [];
}

export const CATEGORY_MAP: Array<{
  prefix: string | string[];
  label: string;
  emoji: string;
}> = [
  { prefix: "BUILTIN", label: "Infrastructure", emoji: "🏗️" },
  { prefix: "GLOBAL", label: "Global", emoji: "🌐" },
  {
    prefix: ["PY-CODE", "PY-EXC", "PY-LOG", "PY-TYPE", "PY-SHELL", "LG"],
    label: "Python · Code",
    emoji: "🐍",
  },
  {
    prefix: ["PY-QUALITY", "PY-TEST", "PY-LINTER"],
    label: "Python · Quality",
    emoji: "✅",
  },
  { prefix: ["TS", "FE"], label: "TypeScript / Frontend", emoji: "⚡" },
  { prefix: "RS", label: "Rust", emoji: "🦀" },
  { prefix: "GIT", label: "Git", emoji: "📦" },
  { prefix: ["SHELL", "QA", "ERRORS"], label: "Shell / QA", emoji: "🐚" },
  { prefix: ["WARN", "STOP"], label: "Warnings / Stop", emoji: "⚠️" },
  { prefix: ["SESSION", "CONFIG"], label: "Session / Config", emoji: "⚙️" },
  { prefix: ["STYLE", "REMIND"], label: "Style / Reminders", emoji: "💅" },
];

export function getCategory(rule_id: string): { label: string; emoji: string } {
  if (CLI_RULE_ID_SET.has(rule_id)) return CLI_CATEGORY;
  for (const { prefix, label, emoji } of CATEGORY_MAP) {
    const prefixes = Array.isArray(prefix) ? prefix : [prefix];
    if (prefixes.some((p) => rule_id.startsWith(p))) return { label, emoji };
  }
  return { label: "Other", emoji: "📋" };
}

export function categorySortIndex(label: string): number {
  if (label === CLI_CATEGORY.label) return CATEGORY_MAP.length;
  const index = CATEGORY_MAP.findIndex((c) => c.label === label);
  return index === -1 ? CATEGORY_MAP.length + 1 : index;
}

export function getCliRuleIds(rule_id: string, config: SlopgateConfig): string[] {
  const regexMap = new Map(config.regex_rules.map((r) => [r.rule_id, r]));
  const directCounterparts = directHookRuleCliCounterparts(config);
  const regexRule = regexMap.get(rule_id);
  const cliCounterparts = directCounterparts[rule_id] ?? [];
  const regexCliExecutable = regexRule !== undefined && CLI_EXECUTABLE_REGEX_TARGETS.has(regexRule.target);
  return cliCounterparts.length > 0 ? cliCounterparts : regexCliExecutable ? [rule_id] : [];
}

export function getCliDefaultEnabled(rule_id: string, config: SlopgateConfig, cliRuleIds: string[]): boolean {
  const directCounterparts = directHookRuleCliCounterparts(config);
  const cliCounterparts = directCounterparts[rule_id] ?? [];
  return cliCounterparts.length > 0 && cliRuleIds.every((cliRuleId) => !CLI_DEFAULT_OFF_RULE_IDS.has(cliRuleId));
}

export function buildRuleMetadata(config: SlopgateConfig, fireCounts: Map<string, number>): RuleMetadata[] {
  const regexMap = new Map(config.regex_rules.map((r) => [r.rule_id, r]));
  const directCounterparts = directHookRuleCliCounterparts(config);
  const directCliCounterpartIds = new Set<string>(Object.values(directCounterparts).flat());
  const hookRuleIds = new Set<string>([
    ...Object.keys(config.enabled_rules),
    ...Object.keys(config.rule_surfaces).filter((ruleId) => !CLI_RULE_ID_SET.has(ruleId)),
    ...config.regex_rules.map((r) => r.rule_id),
  ]);
  const cliRuleIds = new Set<string>([
    ...CLI_RULE_IDS,
    ...Object.keys(config.enabled_cli_rules),
    ...Object.keys(config.rule_surfaces).filter((ruleId) => CLI_RULE_ID_SET.has(ruleId)),
  ]);

  const hookRules = [...hookRuleIds].map((rule_id) => {
    const regexRule = regexMap.get(rule_id);
    const hookEnabled = surfaceHookEnabled(config, rule_id);
    const cliCounterparts = directCounterparts[rule_id] ?? [];
    const regexCliExecutable = regexRule !== undefined && CLI_EXECUTABLE_REGEX_TARGETS.has(regexRule.target);
    const cliRuleIds = cliCounterparts.length > 0 ? cliCounterparts : regexCliExecutable ? [rule_id] : [];
    const { enabled: cliEnabled, partiallyEnabled: cliPartiallyEnabled } = surfaceCliEnabled(
      config,
      rule_id,
      cliRuleIds,
      cliCounterparts.length > 0 && cliRuleIds.every((cliRuleId) => !CLI_DEFAULT_OFF_RULE_IDS.has(cliRuleId)),
    );
    const hookAction = config.rule_surfaces[rule_id]?.hook?.action ?? regexRule?.action ?? "deny";
    const hookEvents = hookEventsForRule(config, rule_id);

    return {
      rule_id,
      title: regexRule?.title ?? rule_id,
      description: getRuleDescription(rule_id) ?? regexRule?.message?.split("\n")[0] ?? "",
      severity: (regexRule?.severity ?? "MEDIUM") as Severity,
      category: getCategory(rule_id).label,
      source: regexRule ? "regex" : "builtin",
      enabled: hookEnabled || cliEnabled || cliPartiallyEnabled,
      hookSupported: true,
      cliSupported: cliRuleIds.length > 0,
      hookEnabled,
      cliEnabled,
      cliPartiallyEnabled,
      cliUnsupportedReason: cliRuleIds.length > 0 ? undefined : cliUnsupportedReason(rule_id, regexRule),
      fireCount: (fireCounts.get(rule_id) ?? 0) + cliCounterparts.reduce((total, cliRuleId) => total + (fireCounts.get(cliRuleId) ?? 0), 0),
      action: hookAction as RuleMetadata["action"],
      hookAction: hookAction as RuleSurfaceAction,
      hookEvents,
      path_globs: regexRule?.path_globs ?? [],
      exclude_path_globs: regexRule?.exclude_path_globs ?? [],
      events: regexRule?.events ?? [],
      cliRuleIds,
      cliCounterparts,
      hookCounterparts: [],
    } satisfies RuleMetadata;
  });

  const cliRules = [...cliRuleIds]
    .filter((rule_id) => !directCliCounterpartIds.has(rule_id))
    .map((rule_id) => {
      const surfaceEnabled = config.rule_surfaces[rule_id]?.cli?.enabled;
      const enabledVal = config.enabled_cli_rules[rule_id];
      const cliEnabled = surfaceEnabled ?? (enabledVal === undefined ? !CLI_DEFAULT_OFF_RULE_IDS.has(rule_id) : Boolean(enabledVal));

      return {
        rule_id,
        title: formatCliTitle(rule_id),
        description: "CLI lint collector used by slopgate lint.",
        severity: "MEDIUM" as Severity,
        category: CLI_CATEGORY.label,
        source: "cli",
        enabled: cliEnabled,
        hookSupported: false,
        cliSupported: true,
        hookEnabled: true,
        cliEnabled,
        cliPartiallyEnabled: false,
        hookUnsupportedReason: "source lint available",
        fireCount: fireCounts.get(rule_id) ?? 0,
        action: "lint",
        hookAction: "deny",
        hookEvents: [],
        path_globs: [],
        exclude_path_globs: [],
        events: ["slopgate lint"],
        cliRuleIds: [rule_id],
        cliCounterparts: [],
        hookCounterparts: hookCounterpartsForCli(rule_id, directCounterparts),
      } satisfies RuleMetadata;
    });

  const all = [...hookRules, ...cliRules];

  return all;
}

export function getRuleChangedFields(rule_id: string, saved: SlopgateConfig, current: SlopgateConfig): string[] {
  const fields: string[] = [];

  // Hook placement change
  const savedHook = surfaceHookEnabled(saved, rule_id);
  const curHook = surfaceHookEnabled(current, rule_id);
  if (savedHook !== curHook) {
    fields.push("hook placement");
  }

  // CLI placement change
  const cliRuleIds = getCliRuleIds(rule_id, current);
  const cliDefault = getCliDefaultEnabled(rule_id, current, cliRuleIds);
  const savedCli = surfaceCliEnabled(saved, rule_id, cliRuleIds, cliDefault);
  const curCli = surfaceCliEnabled(current, rule_id, cliRuleIds, cliDefault);
  if (savedCli.enabled !== curCli.enabled || savedCli.partiallyEnabled !== curCli.partiallyEnabled) {
    fields.push("CLI placement");
  }

  // Hook action change
  const savedAction = saved.rule_surfaces[rule_id]?.hook?.action;
  const curAction = current.rule_surfaces[rule_id]?.hook?.action;
  if (savedAction !== curAction) {
    fields.push("hook action");
  }

  // Hook events change
  const savedEvents = saved.rule_surfaces[rule_id]?.hook?.events ?? [];
  const curEvents = current.rule_surfaces[rule_id]?.hook?.events ?? [];
  if (JSON.stringify([...savedEvents].sort()) !== JSON.stringify([...curEvents].sort())) {
    fields.push("hook events");
  }

  // Exclusions change
  const savedRegex = saved.regex_rules.find((r) => r.rule_id === rule_id);
  const curRegex = current.regex_rules.find((r) => r.rule_id === rule_id);
  const savedExcl = savedRegex?.exclude_path_globs ?? [];
  const curExcl = curRegex?.exclude_path_globs ?? [];
  if (JSON.stringify([...savedExcl].sort()) !== JSON.stringify([...curExcl].sort())) {
    fields.push("exclusions");
  }

  return fields;
}

export function getPendingChangesList(
  savedConfig: SlopgateConfig,
  config: SlopgateConfig,
  allRules: RuleMetadata[],
): Array<{ rule_id: string; title: string; fields: string[] }> {
  const list: Array<{ rule_id: string; title: string; fields: string[] }> = [];
  for (const rule of allRules) {
    const fields = getRuleChangedFields(rule.rule_id, savedConfig, config);
    if (fields.length > 0) {
      list.push({
        rule_id: rule.rule_id,
        title: rule.title,
        fields,
      });
    }
  }
  return list;
}
