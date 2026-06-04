import { useState, useMemo, useCallback, memo } from "react";
import { cn } from "@/lib/utils";
import {
  ChevronRight, ChevronDown, Save, RotateCcw, Plus, X,
  Search, Wifi, WifiOff, Loader2, Check, AlertTriangle,
} from "lucide-react";
import { Switch } from "@/components/ui/switch";
import { Input } from "@/components/ui/input";
import { useRulesConfig } from "@/context/RulesConfigContext";
import { Globe } from "lucide-react";
import { getRuleDescription } from "@/lib/ruleDescriptions";
import { SEVERITY_COLORS } from "@/lib/chartTheme";
import type { RuleMetadata, SlopgateConfig, Severity } from "@/types/slopgate";

interface Props {
  /** Fire counts from trace data (rule_id → count) */
  fireCounts: Map<string, number>;
}

// ── Category grouping ────────────────────────────────────────────────────────
const CATEGORY_MAP: Array<{ prefix: string | string[]; label: string; emoji: string }> = [
  { prefix: "BUILTIN", label: "Infrastructure", emoji: "🏗️" },
  { prefix: "GLOBAL", label: "Global", emoji: "🌐" },
  { prefix: ["PY-CODE", "PY-EXC", "PY-LOG", "PY-TYPE", "PY-SHELL"], label: "Python · Code", emoji: "🐍" },
  { prefix: ["PY-QUALITY", "PY-TEST", "PY-LINTER"], label: "Python · Quality", emoji: "✅" },
  { prefix: ["TS", "FE"], label: "TypeScript / Frontend", emoji: "⚡" },
  { prefix: "RS", label: "Rust", emoji: "🦀" },
  { prefix: "GIT", label: "Git", emoji: "📦" },
  { prefix: ["SHELL", "QA"], label: "Shell / QA", emoji: "🐚" },
  { prefix: ["WARN", "STOP"], label: "Warnings / Stop", emoji: "⚠️" },
  { prefix: ["SESSION", "CONFIG"], label: "Session / Config", emoji: "⚙️" },
  { prefix: ["STYLE", "REMIND"], label: "Style / Reminders", emoji: "💅" },
];

function getCategory(rule_id: string): { label: string; emoji: string } {
  for (const { prefix, label, emoji } of CATEGORY_MAP) {
    const prefixes = Array.isArray(prefix) ? prefix : [prefix];
    if (prefixes.some(p => rule_id.startsWith(p))) return { label, emoji };
  }
  return { label: "Other", emoji: "📋" };
}

// ── Build rule metadata list from config ────────────────────────────────────
function buildRuleMetadata(config: SlopgateConfig, fireCounts: Map<string, number>): RuleMetadata[] {
  const regexMap = new Map(config.regex_rules.map(r => [r.rule_id, r]));
  const allRuleIds = new Set<string>([
    ...Object.keys(config.enabled_rules),
    ...config.regex_rules.map(r => r.rule_id),
  ]);

  return [...allRuleIds].map(rule_id => {
    const regexRule = regexMap.get(rule_id);
    const enabledVal = config.enabled_rules[rule_id];
    const enabled = enabledVal === undefined ? true : Boolean(enabledVal);

    return {
      rule_id,
      title: regexRule?.title ?? rule_id,
      description: getRuleDescription(rule_id) ?? regexRule?.message?.split("\n")[0] ?? "",
      severity: (regexRule?.severity ?? "MEDIUM") as Severity,
      category: getCategory(rule_id).label,
      source: regexRule ? "regex" : "builtin",
      enabled,
      fireCount: fireCounts.get(rule_id) ?? 0,
      action: (regexRule?.action ?? "deny") as RuleMetadata["action"],
      path_globs: regexRule?.path_globs ?? [],
      exclude_path_globs: regexRule?.exclude_path_globs ?? [],
      events: regexRule?.events ?? [],
    } satisfies RuleMetadata;
  }).sort((a, b) => {
    // Sort by category order, then alphabetically
    const catA = CATEGORY_MAP.findIndex(c => a.category === c.label);
    const catB = CATEGORY_MAP.findIndex(c => b.category === c.label);
    if (catA !== catB) return catA - catB;
    return a.rule_id.localeCompare(b.rule_id);
  });
}

// ── Global skip_paths editor ─────────────────────────────────────────────────
const GlobalSkipPathsEditor = memo(function GlobalSkipPathsEditor() {
  const { config, setSkipPaths } = useRulesConfig();
  const [draft, setDraft] = useState("");
  const paths = useMemo(() => config.skip_paths ?? [], [config.skip_paths]);

  const add = useCallback(() => {
    const p = draft.trim();
    if (!p || paths.includes(p)) return;
    setSkipPaths([...paths, p]);
    setDraft("");
  }, [draft, paths, setSkipPaths]);

  const remove = useCallback((p: string) => {
    setSkipPaths(paths.filter(x => x !== p));
  }, [paths, setSkipPaths]);

  return (
    <div className="border border-border rounded-md bg-card/30 p-3 space-y-2">
      <div className="flex items-center gap-2">
        <Globe className="w-3.5 h-3.5 text-muted-foreground" />
        <span className="text-xs font-medium">Global skip_paths</span>
        <span className="text-[10px] text-muted-foreground">— suppresses repo-strict/project rules for matching paths; always-on safety still runs</span>
      </div>
      <div className="flex flex-wrap gap-1.5 min-h-[24px]">
        {paths.length === 0 && (
          <span className="text-[10px] text-muted-foreground/50 italic">no global exclusions</span>
        )}
        {paths.map(p => (
          <span key={p} className="flex items-center gap-1 px-2 py-0.5 bg-muted rounded text-[10px] font-mono">
            {p}
            <button onClick={() => remove(p)} className="hover:text-signal-block ml-1">
              <X className="w-2.5 h-2.5" />
            </button>
          </span>
        ))}
      </div>
      <div className="flex gap-1.5 max-w-sm">
        <Input
          value={draft}
          onChange={e => setDraft(e.target.value)}
          onKeyDown={e => e.key === "Enter" && add()}
          placeholder="src/legacy/** or **/generated/**"
          className="h-6 text-[10px] font-mono bg-background"
        />
        <button
          onClick={add}
          disabled={!draft.trim()}
          className="flex items-center gap-1 px-2 py-0.5 text-[10px] rounded bg-primary/10 text-primary border border-primary/20 hover:bg-primary/20 disabled:opacity-40 transition-colors whitespace-nowrap"
        >
          <Plus className="w-3 h-3" /> Add
        </button>
      </div>
    </div>
  );
});

// ── Summary cards ────────────────────────────────────────────────────────────
const SummaryCards = memo(function SummaryCards({ rules }: { rules: RuleMetadata[] }) {
  const total = rules.length;
  const enabled = rules.filter(r => r.enabled).length;
  const disabled = rules.filter(r => !r.enabled).length;
  const active = rules.filter(r => r.enabled && r.fireCount > 0).length;
  const dormant = rules.filter(r => r.enabled && r.fireCount === 0).length;

  return (
    <div className="grid grid-cols-5 gap-2">
      {[
        { label: "Total Rules", value: total, color: "text-foreground" },
        { label: "Enabled", value: enabled, color: "text-signal-allow" },
        { label: "Disabled", value: disabled, color: "text-muted-foreground" },
        { label: "Active (fired)", value: active, color: "text-signal-ask" },
        { label: "Dormant (0 fires)", value: dormant, color: "text-muted-foreground/60" },
      ].map(({ label, value, color }) => (
        <div key={label} className="px-3 py-2.5 rounded-md border border-border bg-card text-center">
          <div className={cn("text-xl font-semibold leading-tight", color)}>{value}</div>
          <div className="text-[10px] text-muted-foreground uppercase tracking-wider mt-0.5">{label}</div>
        </div>
      ))}
    </div>
  );
});

// ── Exclusion editor (inline) ────────────────────────────────────────────────
const ExclusionEditor = memo(function ExclusionEditor({
  rule_id, globs, onChange, readOnly,
}: {
  rule_id: string;
  globs: string[];
  onChange: (globs: string[]) => void;
  readOnly: boolean;
}) {
  const [draft, setDraft] = useState("");

  const add = useCallback(() => {
    const g = draft.trim();
    if (!g || globs.includes(g)) return;
    onChange([...globs, g]);
    setDraft("");
  }, [draft, globs, onChange]);

  const remove = useCallback((g: string) => {
    onChange(globs.filter(x => x !== g));
  }, [globs, onChange]);

  return (
    <div className="space-y-1.5">
      <div className="text-[10px] text-muted-foreground uppercase tracking-wider">
        Path exclusions (exclude_path_globs)
      </div>
      <div className="flex flex-wrap gap-1.5 min-h-[24px]">
        {globs.length === 0 && (
          <span className="text-[10px] text-muted-foreground/50 italic">no exclusions</span>
        )}
        {globs.map(g => (
          <span key={g} className="flex items-center gap-1 px-2 py-0.5 bg-muted rounded text-[10px] font-mono">
            {g}
            {!readOnly && (
              <button onClick={() => remove(g)} className="hover:text-signal-block ml-1">
                <X className="w-2.5 h-2.5" />
              </button>
            )}
          </span>
        ))}
      </div>
      {!readOnly && (
        <div className="flex gap-1.5 max-w-sm">
          <Input
            value={draft}
            onChange={e => setDraft(e.target.value)}
            onKeyDown={e => e.key === "Enter" && add()}
            placeholder="**/tests/** or src/legacy/**"
            className="h-6 text-[10px] font-mono bg-background"
          />
          <button
            onClick={add}
            disabled={!draft.trim()}
            className="flex items-center gap-1 px-2 py-0.5 text-[10px] rounded bg-primary/10 text-primary border border-primary/20 hover:bg-primary/20 disabled:opacity-40 transition-colors whitespace-nowrap"
          >
            <Plus className="w-3 h-3" /> Add
          </button>
        </div>
      )}
      {readOnly && (
        <div className="text-[10px] text-muted-foreground/50 italic">
          Exclusions only apply to regex rules. Global skip_paths suppress repo-strict/project rules; always-on safety still runs.
        </div>
      )}
    </div>
  );
});

// ── Individual rule row ───────────────────────────────────────────────────────
const RuleRow = memo(function RuleRow({
  rule, onToggle, onExclusionsChange,
}: {
  rule: RuleMetadata;
  onToggle: (id: string) => void;
  onExclusionsChange: (id: string, globs: string[]) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const sevColor = SEVERITY_COLORS[rule.severity] ?? "hsl(210,20%,55%)";

  const actionBadge: Record<string, string> = {
    deny: "bg-signal-block/20 text-signal-block",
    block: "bg-signal-block/20 text-signal-block",
    warn: "bg-signal-warn/20 text-signal-warn",
    ask: "bg-signal-ask/20 text-signal-ask",
    context: "bg-muted text-muted-foreground",
  };

  return (
    <>
      <tr
        className={cn(
          "border-b border-border/30 hover:bg-muted/10 transition-colors",
          !rule.enabled && "opacity-50",
          expanded && "bg-muted/5",
        )}
      >
        {/* expand chevron */}
        <td className="px-2 py-2 w-6 cursor-pointer" onClick={() => setExpanded(e => !e)}>
          {expanded
            ? <ChevronDown className="w-3 h-3 text-muted-foreground" />
            : <ChevronRight className="w-3 h-3 text-muted-foreground" />}
        </td>
        {/* toggle */}
        <td className="px-2 py-2">
          <Switch
            checked={rule.enabled}
            onCheckedChange={() => onToggle(rule.rule_id)}
            className="scale-75 origin-left"
          />
        </td>
        {/* rule id */}
        <td className="px-2 py-2 font-mono text-xs cursor-pointer" onClick={() => setExpanded(e => !e)}>
          <span style={{ color: sevColor }}>{rule.rule_id}</span>
        </td>
        {/* title */}
        <td className="px-2 py-2 text-xs text-muted-foreground max-w-[220px] truncate cursor-pointer" onClick={() => setExpanded(e => !e)}>
          {rule.title !== rule.rule_id ? rule.title : (rule.description.slice(0, 60) || "—")}
        </td>
        {/* severity */}
        <td className="px-2 py-2">
          <span className="text-[9px] px-1.5 py-0.5 rounded font-medium uppercase" style={{
            backgroundColor: `${sevColor}20`, color: sevColor,
          }}>
            {rule.severity}
          </span>
        </td>
        {/* action */}
        <td className="px-2 py-2">
          <span className={cn("text-[9px] px-1.5 py-0.5 rounded uppercase", actionBadge[rule.action] ?? "bg-muted text-muted-foreground")}>
            {rule.action}
          </span>
        </td>
        {/* source */}
        <td className="px-2 py-2">
          <span className="text-[9px] text-muted-foreground">{rule.source}</span>
        </td>
        {/* fire count */}
        <td className="px-2 py-2 text-right">
          <span className={cn(
            "text-xs font-mono",
            rule.fireCount > 0 ? "text-signal-ask font-semibold" : "text-muted-foreground/40",
          )}>
            {rule.fireCount > 0 ? rule.fireCount : "—"}
          </span>
        </td>
        {/* exclusions button — always visible for regex rules */}
        <td className="px-2 py-2 text-right">
          {rule.source === "regex" ? (
            <button
              onClick={e => { e.stopPropagation(); setExpanded(ex => !ex); }}
              title={rule.exclude_path_globs.length > 0 ? `${rule.exclude_path_globs.length} path exclusion(s) — click to edit` : "Add path exclusions"}
              className={cn(
                "text-[10px] px-1.5 py-0.5 rounded border transition-colors",
                rule.exclude_path_globs.length > 0
                  ? "bg-signal-ask/10 text-signal-ask border-signal-ask/20 hover:bg-signal-ask/20"
                  : "text-muted-foreground/50 border-border/50 hover:text-primary hover:border-primary/30 hover:bg-primary/5"
              )}
            >
              {rule.exclude_path_globs.length > 0 ? `${rule.exclude_path_globs.length} excl.` : "+ excl."}
            </button>
          ) : (
            <span
              className="text-[10px] text-muted-foreground/50 border border-border/40 px-1.5 py-0.5 rounded cursor-default"
              title="Builtin rules are not editable here; global skip_paths only suppress repo-strict/project checks, not always-on safety"
            >
              global ↗
            </span>
          )}
        </td>
      </tr>
      {expanded && (
        <tr className="border-b border-border/20 bg-muted/5">
          <td colSpan={9} className="px-8 py-3 space-y-3">
            {/* description */}
            {rule.description && (
              <div className="text-xs text-muted-foreground max-w-2xl leading-relaxed">
                {rule.description}
              </div>
            )}
            {/* exclusions FIRST — most likely reason to expand */}
            <ExclusionEditor
              rule_id={rule.rule_id}
              globs={rule.exclude_path_globs}
              onChange={globs => onExclusionsChange(rule.rule_id, globs)}
              readOnly={rule.source !== "regex"}
            />
            {/* path globs (applies-to) */}
            {rule.path_globs.length > 0 && (
              <div className="space-y-1">
                <div className="text-[10px] text-muted-foreground uppercase tracking-wider">Applies to</div>
                <div className="flex flex-wrap gap-1">
                  {rule.path_globs.map(g => (
                    <span key={g} className="px-1.5 py-0.5 bg-muted rounded text-[10px] font-mono text-muted-foreground">{g}</span>
                  ))}
                </div>
              </div>
            )}
          </td>
        </tr>
      )}
    </>
  );
});

// ── Category group ────────────────────────────────────────────────────────────
const CategoryGroup = memo(function CategoryGroup({
  label, emoji, rules, onToggle, onExclusionsChange,
}: {
  label: string; emoji: string; rules: RuleMetadata[];
  onToggle: (id: string) => void;
  onExclusionsChange: (id: string, globs: string[]) => void;
}) {
  const active = rules.filter(r => r.enabled && r.fireCount > 0).length;
  const [open, setOpen] = useState(active > 0);

  const totalFires = rules.reduce((s, r) => s + r.fireCount, 0);
  const disabled = rules.filter(r => !r.enabled).length;

  return (
    <>
      <tr
        className="border-b border-border/50 bg-card/50 cursor-pointer select-none hover:bg-muted/20"
        onClick={() => setOpen(o => !o)}
      >
        <td colSpan={9} className="px-3 py-2">
          <div className="flex items-center gap-2">
            {open
              ? <ChevronDown className="w-3.5 h-3.5 text-muted-foreground" />
              : <ChevronRight className="w-3.5 h-3.5 text-muted-foreground" />}
            <span className="text-xs font-semibold">{emoji} {label}</span>
            <span className="text-[10px] text-muted-foreground ml-1">{rules.length} rules</span>
            {active > 0 && (
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-signal-ask/20 text-signal-ask">
                {active} active · {totalFires} fires
              </span>
            )}
            {disabled > 0 && (
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground">
                {disabled} disabled
              </span>
            )}
          </div>
        </td>
      </tr>
      {open && rules.map(rule => (
        <RuleRow
          key={rule.rule_id}
          rule={rule}
          onToggle={onToggle}
          onExclusionsChange={onExclusionsChange}
        />
      ))}
    </>
  );
});

// ── Save toolbar ──────────────────────────────────────────────────────────────
const SaveToolbar = memo(function SaveToolbar() {
  const { pendingCount, saveConfig, discardChanges, saveStatus, saveError, apiAvailable, loading } = useRulesConfig();

  if (loading) return null;

  return (
    <div className={cn(
      "flex items-center gap-3 px-3 py-2 rounded-md border text-xs transition-all",
      pendingCount > 0
        ? "border-signal-ask/30 bg-signal-ask/5"
        : "border-border bg-card/30",
    )}>
      {/* API indicator */}
      <span className={cn("flex items-center gap-1 text-[10px]", apiAvailable ? "text-signal-allow" : "text-muted-foreground")}>
        {apiAvailable ? <Wifi className="w-3 h-3" /> : <WifiOff className="w-3 h-3" />}
        {apiAvailable ? "API connected" : "read-only (no API)"}
      </span>

      <span className="text-muted-foreground">·</span>

      {pendingCount > 0 ? (
        <>
          <span className="text-signal-ask font-medium">{pendingCount} unsaved change{pendingCount !== 1 ? "s" : ""}</span>
          <button
            onClick={() => saveConfig()}
            disabled={saveStatus === "saving" || !apiAvailable}
            className="flex items-center gap-1 px-2 py-1 rounded bg-signal-allow/20 text-signal-allow border border-signal-allow/30 hover:bg-signal-allow/30 disabled:opacity-50 transition-colors"
          >
            {saveStatus === "saving" ? <Loader2 className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
            Save to Littlebox
          </button>
          <button
            onClick={discardChanges}
            className="flex items-center gap-1 px-2 py-1 rounded text-muted-foreground hover:bg-muted transition-colors"
          >
            <RotateCcw className="w-3 h-3" /> Discard
          </button>
        </>
      ) : (
        <span className="text-muted-foreground">
          {saveStatus === "saved"
            ? <span className="text-signal-allow flex items-center gap-1"><Check className="w-3 h-3" /> Saved</span>
            : "No pending changes"}
        </span>
      )}

      {saveStatus === "error" && saveError && (
        <span className="text-signal-block text-[10px] flex items-center gap-1">
          <AlertTriangle className="w-3 h-3" /> {saveError}
        </span>
      )}
    </div>
  );
});

// ── Main component ────────────────────────────────────────────────────────────
export function RuleManager({ fireCounts }: Props) {
  const { config, toggleRule, setExclusions, loading } = useRulesConfig();
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<"all" | "active" | "dormant" | "disabled">("all");

  const allRules = useMemo(() => buildRuleMetadata(config, fireCounts), [config, fireCounts]);

  const filtered = useMemo(() => {
    let rules = allRules;
    if (filter === "active") rules = rules.filter(r => r.enabled && r.fireCount > 0);
    else if (filter === "dormant") rules = rules.filter(r => r.enabled && r.fireCount === 0);
    else if (filter === "disabled") rules = rules.filter(r => !r.enabled);
    if (search) {
      const q = search.toLowerCase();
      rules = rules.filter(r =>
        r.rule_id.toLowerCase().includes(q) ||
        r.title.toLowerCase().includes(q) ||
        r.description.toLowerCase().includes(q)
      );
    }
    return rules;
  }, [allRules, filter, search]);

  const grouped = useMemo(() => {
    const map = new Map<string, { emoji: string; rules: RuleMetadata[] }>();
    for (const rule of filtered) {
      const cat = getCategory(rule.rule_id);
      if (!map.has(cat.label)) map.set(cat.label, { emoji: cat.emoji, rules: [] });
      map.get(cat.label)!.rules.push(rule);
    }
    // Sort groups by category order
    return [...map.entries()].sort(([a], [b]) => {
      const ai = CATEGORY_MAP.findIndex(c => c.label === a);
      const bi = CATEGORY_MAP.findIndex(c => c.label === b);
      return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi);
    });
  }, [filtered]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16 text-muted-foreground gap-2">
        <Loader2 className="w-4 h-4 animate-spin" />
        <span className="text-xs">Loading rule configuration…</span>
      </div>
    );
  }

  if (allRules.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-muted-foreground gap-2">
        <span className="text-xs">No rules found. Check that build-standalone.py was run with --ssh.</span>
        <span className="text-[10px]">window.__SLOPGATE_CONFIG__ is missing.</span>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Global skip_paths — suppresses repo-strict/project rules; always-on safety still runs */}
      <GlobalSkipPathsEditor />

      {/* Summary */}
      <SummaryCards rules={allRules} />

      {/* Toolbar */}
      <div className="flex items-center gap-3">
        <div className="relative flex-1 max-w-xs">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3 h-3 text-muted-foreground" />
          <Input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search rules…"
            className="pl-7 h-7 text-xs bg-background"
          />
        </div>
        <div className="flex gap-1">
          {(["all", "active", "dormant", "disabled"] as const).map(f => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={cn(
                "px-2 py-0.5 text-[10px] rounded-sm transition-colors capitalize",
                filter === f ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted"
              )}
            >
              {f}
            </button>
          ))}
        </div>
        <div className="ml-auto">
          <SaveToolbar />
        </div>
      </div>

      {/* Table */}
      <div className="border border-border rounded-md bg-card/30 overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="border-b border-border text-muted-foreground text-[10px] uppercase bg-card/50">
              <th className="px-2 py-2 w-6" />
              <th className="px-2 py-2 text-left w-12">On</th>
              <th className="px-2 py-2 text-left">Rule ID</th>
              <th className="px-2 py-2 text-left">Title / Description</th>
              <th className="px-2 py-2 text-left w-20">Severity</th>
              <th className="px-2 py-2 text-left w-20">Action</th>
              <th className="px-2 py-2 text-left w-14">Source</th>
              <th className="px-2 py-2 text-right w-16">Fires</th>
              <th className="px-2 py-2 text-right w-20">Exclusions</th>
            </tr>
          </thead>
          <tbody>
            {grouped.length === 0 ? (
              <tr><td colSpan={9} className="text-center py-8 text-muted-foreground text-xs">No rules match</td></tr>
            ) : (
              grouped.map(([label, { emoji, rules }]) => (
                <CategoryGroup
                  key={label}
                  label={label}
                  emoji={emoji}
                  rules={rules}
                  onToggle={toggleRule}
                  onExclusionsChange={setExclusions}
                />
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Footer note */}
      <div className="text-[10px] text-muted-foreground/60 text-center">
        Changes are saved to <code className="font-mono">~/.config/slopgate/config.json</code> on Littlebox via SSH.
        Slopgate reads config on every hook invocation — changes take effect immediately.
      </div>
    </div>
  );
}
