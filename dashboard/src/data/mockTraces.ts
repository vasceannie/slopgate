import type {
  Decision,
  EventName,
  HookEvent,
  HookResult,
  Platform,
  RuleFinding,
  RuntimeConfig,
  Severity,
  SubprocessRun,
} from "@/types/slopgate";

// Deterministic seed-based random
let seed = 42;
function rand() {
  seed = (seed * 16807 + 0) % 2147483647;
  return (seed - 1) / 2147483646;
}
function pick<T>(arr: T[]): T {
  return arr[Math.floor(rand() * arr.length)];
}
function pickN<T>(arr: T[], n: number): T[] {
  const shuffled = [...arr].sort(() => rand() - 0.5);
  return shuffled.slice(0, n);
}

const PLATFORMS: Platform[] = ["claude", "codex", "opencode", "cursor", "pi"];
const _EVENT_NAMES: EventName[] = ["SessionStart", "PreToolUse", "PermissionRequest", "PostToolUse", "PostToolUseFailure", "Stop"];
const _DECISIONS: Decision[] = ["allow", "deny", "block", "ask", "context", "warn"];
const SEVERITIES: Severity[] = ["LOW", "MEDIUM", "HIGH", "CRITICAL"];

const TOOLS = [
  "Write",
  "Edit",
  "Read",
  "Bash",
  "Search",
  "Grep",
  "ListDir",
  "WebSearch",
  "TodoRead",
  "TodoWrite",
  "Glob",
  "Task",
  "MultiEdit",
];

const LANGUAGES = ["python", "typescript", "javascript", "rust", "go", "java", "ruby", "shell"];

const PATHS = [
  "src/main.py",
  "src/utils.ts",
  "lib/core.rs",
  "app/handler.go",
  "tests/test_main.py",
  "src/components/App.tsx",
  "scripts/deploy.sh",
  "src/models/user.py",
  "src/services/auth.ts",
  "config/settings.yaml",
];

const PYTHON_RULES = [
  "no-bare-except",
  "no-eval-exec",
  "no-hardcoded-secrets",
  "no-assert-in-prod",
  "no-mutable-default",
  "no-star-import",
  "no-print-statements",
  "no-todo-fixme",
  "no-broad-exception",
  "no-nested-ternary",
  "no-magic-numbers",
  "no-global-state",
  "no-circular-import",
  "no-unused-variable",
  "no-shadowed-builtin",
  "repeated-code-block",
  "duplicate-call-sequence",
  "semantic-clone",
  "no-long-function",
  "no-deep-nesting",
  "no-complex-comprehension",
  "no-unsafe-yaml",
  "no-pickle-loads",
  "no-subprocess-shell",
  "no-tempfile-race",
  "no-sql-injection",
  "no-os-system",
  "no-weak-crypto",
  "no-debug-left",
  "no-empty-except",
];

const REGEX_RULES = [
  "no-console-log",
  "no-debugger",
  "no-alert",
  "no-inline-style",
  "no-any-type",
  "no-ts-ignore",
  "no-eslint-disable",
  "no-fixme",
  "no-hack-comment",
  "no-xxx-comment",
  "no-password-literal",
  "no-api-key-literal",
  "no-localhost-url",
  "no-http-url",
  "no-hardcoded-ip",
  "no-empty-catch",
  "no-var-declaration",
  "no-document-write",
  "no-innerhtml",
  "no-onclick-handler",
  "no-jquery",
  "no-lodash-fp",
  "no-moment-js",
  "no-sync-xhr",
  "no-window-eval",
  "no-with-statement",
  "no-label-statement",
  "no-comma-operator",
  "no-void-operator",
  "no-bitwise-operator",
  "no-nested-callback",
  "no-prototype-builtin",
  "no-new-object",
  "no-new-array",
  "no-delete-operator",
  "no-caller-callee",
  "no-iterator",
  "no-restricted-globals",
  "no-implicit-coercion",
  "no-sequences",
];

const ALL_RULES = [...PYTHON_RULES, ...REGEX_RULES];
const DUPLICATION_RULES = ["repeated-code-block", "duplicate-call-sequence", "semantic-clone"];

const ASYNC_COMMANDS = [
  "ruff check --fix .",
  "mypy --strict .",
  "pytest -x --tb=short",
  "eslint --fix src/",
  "tsc --noEmit",
  "cargo clippy -- -D warnings",
  "go vet ./...",
  "rubocop -a",
  "shellcheck scripts/*.sh",
  "black --check .",
];

function genSessions(count: number, _startDate: Date, _endDate: Date) {
  const sessions: string[] = [];
  for (let i = 0; i < count; i++) {
    sessions.push(`sess_${i.toString(36).padStart(6, "0")}_${Math.floor(rand() * 1e6).toString(36)}`);
  }
  return sessions;
}

function randomDate(start: Date, end: Date): Date {
  return new Date(start.getTime() + rand() * (end.getTime() - start.getTime()));
}

export function generateMockData() {
  seed = 42;
  const now = new Date();
  const start = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
  const sessions = genSessions(200, start, now);

  const events: HookEvent[] = [];
  const rules: RuleFinding[] = [];
  const results: HookResult[] = [];
  const subprocesses: SubprocessRun[] = [];

  for (const sid of sessions) {
    const platform = pick(PLATFORMS);
    const sessionStart = randomDate(start, now);
    const eventCount = 2 + Math.floor(rand() * 8);
    const sessionLangs = pickN(LANGUAGES, 1 + Math.floor(rand() * 3));

    const isSlopgateRepo = rand() < 0.75;
    const enforcementMode = isSlopgateRepo ? (rand() < 0.8 ? "repo_strict" : "repo_relaxed") : "outside_repo";
    const resolvedRepoRoot = isSlopgateRepo
      ? rand() < 0.6
        ? "/home/trav/.openclaw/workspace-hooker/slopgate"
        : "/home/trav/projects/website"
      : rand() < 0.5
        ? "/home/trav/scratchpad"
        : null;

    const rawPaths = pickN(PATHS, 1 + Math.floor(rand() * 4));
    const sessionPaths = rawPaths.map((p) => {
      return resolvedRepoRoot ? `${resolvedRepoRoot}/${p}` : `/home/trav/${p}`;
    });

    // Session lifecycle
    const sessionEvents: EventName[] = ["SessionStart"];
    for (let i = 0; i < eventCount; i++) {
      const ev = pick(["PreToolUse", "PostToolUse", "PermissionRequest"] as EventName[]);
      sessionEvents.push(ev);
    }
    if (rand() > 0.1) sessionEvents.push("Stop");
    if (rand() < 0.05) sessionEvents.push("PostToolUseFailure");

    let ts = sessionStart.getTime();
    for (const evName of sessionEvents) {
      ts += Math.floor(rand() * 30000) + 1000;
      const tool = evName === "SessionStart" || evName === "Stop" ? "" : pick(TOOLS);
      const timestamp = new Date(ts).toISOString();

      let model: string | null = null;
      let provider: string | null = null;
      let command: string | null = null;
      let tool_output: string | null = null;

      if (evName === "PreToolUse" || evName === "PostToolUse" || evName === "PermissionRequest") {
        if (platform === "claude") {
          model = "claude-3-5-sonnet-20241022";
          provider = "Anthropic";
        } else if (platform === "codex") {
          model = "gpt-5.4-preview";
          provider = "OpenAI";
        } else if (platform === "pi") {
          model = "pi-2";
          provider = "Inflection";
        } else {
          model = "gemini-3-flash-agent";
          provider = "Google";
        }

        if (tool === "Bash") {
          command = pick(["pytest tests/", "git commit -m 'wip'", "npm run build", "python scripts/cleanup.py"]);
          tool_output = "stdout:\n  10 passed, 0 failed in 1.2s\n  Done.";
        } else if (tool === "Write" || tool === "Edit") {
          command = `file: ${pick(sessionPaths)}`;
          tool_output = "Wrote/Edited 120 lines successfully.";
        }
      }

      events.push({
        timestamp,
        platform,
        event_name: evName,
        session_id: sid,
        tool_name: tool,
        candidate_paths: evName === "SessionStart" ? [] : pickN(sessionPaths, 1 + Math.floor(rand() * 2)),
        languages: sessionLangs,
        enforcement_mode: enforcementMode,
        resolved_repo_root: resolvedRepoRoot,
        model,
        provider,
        command,
        tool_output,
      });

      // Generate rule findings for tool events
      if (evName === "PreToolUse" || evName === "PostToolUse" || evName === "PermissionRequest") {
        const findingCount = Math.floor(rand() * 4);
        const sessionFindings: RuleFinding[] = [];

        for (let f = 0; f < findingCount; f++) {
          // Bias toward duplication rules occasionally
          const ruleId = rand() < 0.15 ? pick(DUPLICATION_RULES) : pick(ALL_RULES);
          const severity = PYTHON_RULES.includes(ruleId) ? pick(["MEDIUM", "HIGH", "CRITICAL"] as Severity[]) : pick(SEVERITIES);
          const decision: Decision =
            severity === "CRITICAL"
              ? pick(["block", "deny"] as Decision[])
              : severity === "HIGH"
                ? pick(["deny", "ask", "warn"] as Decision[])
                : severity === "MEDIUM"
                  ? pick(["ask", "warn", "context"] as Decision[])
                  : pick(["allow", "context", "warn"] as Decision[]);

          const finding: RuleFinding = {
            timestamp,
            platform,
            event_name: evName,
            session_id: sid,
            tool_name: tool,
            rule_id: ruleId,
            severity,
            decision,
            message: `${ruleId}: Found violation in ${pick(sessionPaths)}`,
            additional_context: `Rule ${ruleId} triggered by ${tool} on ${platform}`,
            metadata: {
              category: DUPLICATION_RULES.includes(ruleId) ? "duplication" : "general",
            },
            enforcement_mode: enforcementMode,
            resolved_repo_root: resolvedRepoRoot,
          };
          sessionFindings.push(finding);
          rules.push(finding);
        }

        // Determine final decision
        const worstDecision: Decision =
          sessionFindings.length === 0
            ? "allow"
            : sessionFindings.some((f) => f.decision === "block")
              ? "block"
              : sessionFindings.some((f) => f.decision === "deny")
                ? "deny"
                : sessionFindings.some((f) => f.decision === "ask")
                  ? "ask"
                  : sessionFindings.some((f) => f.decision === "warn")
                    ? "warn"
                    : sessionFindings.some((f) => f.decision === "context")
                      ? "context"
                      : "allow";

        const skipped = rand() < 0.05;
        results.push({
          timestamp,
          platform,
          event_name: evName,
          session_id: sid,
          tool_name: tool,
          findings: sessionFindings.map((f) => ({
            rule_id: f.rule_id,
            severity: f.severity,
            decision: f.decision,
            message: f.message,
          })),
          errors: rand() < 0.03 ? [`RuleEngineError: timeout evaluating ${pick(ALL_RULES)}`] : [],
          output:
            worstDecision === "allow"
              ? null
              : {
                  summary: `Decision: ${worstDecision} — ${sessionFindings.length} finding(s)`,
                },
          skipped,
          reason: skipped ? "Path in skip_paths" : undefined,
          enforcement_mode: enforcementMode,
          resolved_repo_root: resolvedRepoRoot,
        });
      }

      // Async jobs after PostToolUse
      if (evName === "PostToolUse" && rand() < 0.3) {
        const cmd = pick(ASYNC_COMMANDS);
        const success = rand() > 0.25;
        subprocesses.push({
          timestamp: new Date(ts + Math.floor(rand() * 5000)).toISOString(),
          event_name: "async_subprocess",
          session_id: sid,
          command: cmd,
          cwd: `/repo/${pick(["frontend", "backend", "infra", "shared"])}`,
          returncode: success ? 0 : pick([1, 2, 127]),
          stdout: success ? `${cmd}: all checks passed` : "",
          stderr: success ? "" : `${cmd}: 3 errors found\n  line 42: violation\n  line 87: violation\n  line 133: violation`,
          duration_ms: Math.floor(rand() * 15000) + 500,
        });
      }
    }
  }

  // Sort all by timestamp
  events.sort((a, b) => a.timestamp.localeCompare(b.timestamp));
  rules.sort((a, b) => a.timestamp.localeCompare(b.timestamp));
  results.sort((a, b) => a.timestamp.localeCompare(b.timestamp));
  subprocesses.sort((a, b) => a.timestamp.localeCompare(b.timestamp));

  return { events, rules, results, subprocesses };
}

export const mockConfig: RuntimeConfig = {
  disabled_rules: [
    { rule_id: "no-console-log", disabled_date: "2026-04-01" },
    { rule_id: "no-todo-fixme", disabled_date: "2026-03-28" },
    { rule_id: "no-magic-numbers", disabled_date: "2026-04-05" },
  ],
  severity_overrides: [
    { rule_id: "no-any-type", original: "MEDIUM", override: "HIGH" },
    { rule_id: "no-eval-exec", original: "HIGH", override: "CRITICAL" },
    { rule_id: "repeated-code-block", original: "LOW", override: "MEDIUM" },
  ],
  skip_paths: ["node_modules/**", "dist/**", ".git/**", "vendor/**", "__pycache__/**"],
  skip_repos: ["legacy-monolith", "archived-experiment"],
};
