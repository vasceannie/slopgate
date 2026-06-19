/**
 * RulesConfigContext — manages slopgate rule config state.
 *
 * On mount: loads window.__SLOPGATE_CONFIG__ (baked at build time),
 * then fetches live config from /api/config for up-to-date enabled states.
 *
 * Provides:
 *   - config: current merged SlopgateConfig
 *   - pendingCount: number of unsaved changes
 *   - toggleRule(rule_id): flip enabled/disabled
 *   - setExclusions(rule_id, globs): replace exclude_path_globs for a regex rule
 *   - saveConfig(): POST patch to /api/config
 *   - discardChanges(): revert to last-saved state
 *   - saveStatus: "idle" | "saving" | "saved" | "error"
 *   - apiAvailable: false when running without the serve.py API server
 */
import { type ReactNode, useCallback, useEffect, useState } from "react";
import type { RuleCliSurface, RuleHookSurface, SlopgateConfig } from "@/types/slopgate";

import { RulesConfigContext, type SaveStatus } from "./rulesConfigContext";

const API_BASE = window.location.origin + import.meta.env.BASE_URL.replace(/\/$/, "");
const CONFIG_ENDPOINT = `${API_BASE}/api/config`;

/** Get the config baked at build time (may be stale) */
function getBakedConfig(): SlopgateConfig | null {
  const w = window as unknown as { __SLOPGATE_CONFIG__?: SlopgateConfig };
  return w.__SLOPGATE_CONFIG__ ?? null;
}

function normalizeConfig(config: SlopgateConfig | null): SlopgateConfig {
  return {
    enabled_rules: config?.enabled_rules ?? {},
    enabled_cli_rules: config?.enabled_cli_rules ?? {},
    rule_surfaces: config?.rule_surfaces ?? {},
    rule_counterparts: config?.rule_counterparts ?? {},
    regex_rules: config?.regex_rules ?? [],
    skip_paths: config?.skip_paths ?? [],
  };
}

/** Deep-clone a config object */
function cloneConfig(c: SlopgateConfig): SlopgateConfig {
  return JSON.parse(JSON.stringify(c));
}

/** Count differences between two enabled_rules dicts */
function countBoolMapDiffs(saved: Record<string, boolean>, current: Record<string, boolean>): number {
  let n = 0;
  const allKeys = new Set([...Object.keys(saved), ...Object.keys(current)]);
  for (const k of allKeys) {
    if ((saved[k] ?? true) !== (current[k] ?? true)) n++;
  }
  return n;
}

function countPending(saved: SlopgateConfig, current: SlopgateConfig): number {
  let n = countBoolMapDiffs(saved.enabled_rules, current.enabled_rules);
  n += countBoolMapDiffs(saved.enabled_cli_rules, current.enabled_cli_rules);
  if (JSON.stringify(saved.rule_surfaces) !== JSON.stringify(current.rule_surfaces)) n++;
  // Count exclusion diffs for regex rules
  const savedGlobs = new Map(saved.regex_rules.map((r) => [r.rule_id, r.exclude_path_globs ?? []]));
  for (const r of current.regex_rules) {
    const savedG = savedGlobs.get(r.rule_id) ?? [];
    const curG = r.exclude_path_globs ?? [];
    if (JSON.stringify([...savedG].sort()) !== JSON.stringify([...curG].sort())) n++;
  }
  // Count skip_paths diffs
  if (JSON.stringify([...saved.skip_paths].sort()) !== JSON.stringify([...current.skip_paths].sort())) n++;
  return n;
}

export function RulesConfigProvider({ children }: { children: ReactNode }) {
  const [bakedConfig] = useState(() => normalizeConfig(getBakedConfig()));
  const [savedConfig, setSavedConfig] = useState<SlopgateConfig>(bakedConfig);
  const [config, setConfig] = useState<SlopgateConfig>(bakedConfig);
  const [saveStatus, setSaveStatus] = useState<SaveStatus>("idle");
  const [saveError, setSaveError] = useState<string | null>(null);
  const [apiAvailable, setApiAvailable] = useState(false);
  const [loading, setLoading] = useState(true);

  // Fetch live config once on mount
  useEffect(() => {
    let cancelled = false;
    fetch(`${API_BASE}/api/health`, { signal: AbortSignal.timeout(4000) })
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (cancelled || !data?.ok) {
          setLoading(false);
          return;
        }
        setApiAvailable(true);
        return fetch(CONFIG_ENDPOINT, { signal: AbortSignal.timeout(6000) });
      })
      .then((r) => (r?.ok ? r.json() : null))
      .then((data) => {
        if (cancelled || !data) {
          setLoading(false);
          return;
        }
        // Merge: prefer baked regex_rules (with merged exclusions), but use live enabled_rules
        const live: SlopgateConfig = {
          enabled_rules: data.enabled_rules ?? {},
          enabled_cli_rules: data.enabled_cli_rules ?? {},
          rule_surfaces: data.rule_surfaces ?? {},
          rule_counterparts: data.rule_counterparts ?? bakedConfig.rule_counterparts,
          regex_rules: bakedConfig.regex_rules.length ? bakedConfig.regex_rules : (data.regex_rules ?? []),
          skip_paths: data.skip_paths ?? [],
        };
        setSavedConfig(cloneConfig(live));
        setConfig(cloneConfig(live));
        setLoading(false);
      })
      .catch(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [bakedConfig.regex_rules, bakedConfig.rule_counterparts]);

  const toggleRule = useCallback((rule_id: string) => {
    setConfig((prev) => {
      const current = prev.enabled_rules[rule_id] ?? true;
      return {
        ...prev,
        enabled_rules: { ...prev.enabled_rules, [rule_id]: !current },
      };
    });
  }, []);

  const toggleCliRule = useCallback((rule_id: string) => {
    setConfig((prev) => {
      const current = prev.enabled_cli_rules[rule_id] ?? true;
      return {
        ...prev,
        enabled_cli_rules: {
          ...prev.enabled_cli_rules,
          [rule_id]: !current,
        },
      };
    });
  }, []);

  const setCliRules = useCallback((rule_ids: string[], enabled: boolean) => {
    setConfig((prev) => {
      const enabled_cli_rules = { ...prev.enabled_cli_rules };
      for (const rule_id of rule_ids) {
        enabled_cli_rules[rule_id] = enabled;
      }
      return { ...prev, enabled_cli_rules };
    });
  }, []);

  const setRuleHookSurface = useCallback((rule_id: string, hook: RuleHookSurface) => {
    setConfig((prev) => ({
      ...prev,
      rule_surfaces: {
        ...prev.rule_surfaces,
        [rule_id]: {
          ...(prev.rule_surfaces[rule_id] ?? {}),
          hook: {
            ...(prev.rule_surfaces[rule_id]?.hook ?? {}),
            ...hook,
          },
        },
      },
    }));
  }, []);

  const setRuleCliSurface = useCallback((rule_id: string, cliRuleIds: string[], cli: RuleCliSurface) => {
    setConfig((prev) => {
      const enabled_cli_rules = { ...prev.enabled_cli_rules };
      if (typeof cli.enabled === "boolean") {
        for (const cliRuleId of cliRuleIds) {
          enabled_cli_rules[cliRuleId] = cli.enabled;
        }
      }
      return {
        ...prev,
        enabled_cli_rules,
        rule_surfaces: {
          ...prev.rule_surfaces,
          [rule_id]: {
            ...(prev.rule_surfaces[rule_id] ?? {}),
            cli: {
              ...(prev.rule_surfaces[rule_id]?.cli ?? {}),
              ...cli,
            },
          },
        },
      };
    });
  }, []);

  const setExclusions = useCallback((rule_id: string, globs: string[]) => {
    setConfig((prev) => ({
      ...prev,
      regex_rules: prev.regex_rules.map((r) => (r.rule_id === rule_id ? { ...r, exclude_path_globs: globs } : r)),
    }));
  }, []);

  const setSkipPaths = useCallback((paths: string[]) => {
    setConfig((prev) => ({ ...prev, skip_paths: paths }));
  }, []);

  const saveConfig = useCallback(async () => {
    setSaveStatus("saving");
    setSaveError(null);
    try {
      const patch = {
        enabled_rules: config.enabled_rules,
        enabled_cli_rules: config.enabled_cli_rules,
        rule_surfaces: config.rule_surfaces,
        regex_rules: config.regex_rules,
        skip_paths: config.skip_paths,
      };
      const r = await fetch(CONFIG_ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch),
        signal: AbortSignal.timeout(10000),
      });
      const body = await r.json();
      if (!r.ok || body.error) throw new Error(body.error ?? `HTTP ${r.status}`);
      setSavedConfig(cloneConfig(config));
      setSaveStatus("saved");
      setTimeout(() => setSaveStatus("idle"), 3000);
    } catch (e) {
      setSaveStatus("error");
      setSaveError(e instanceof Error ? e.message : String(e));
    }
  }, [config]);

  const discardChanges = useCallback(() => {
    setConfig(cloneConfig(savedConfig));
    setSaveStatus("idle");
    setSaveError(null);
  }, [savedConfig]);

  const pendingCount = countPending(savedConfig, config);

  return (
    <RulesConfigContext.Provider
      value={{
        config,
        savedConfig,
        pendingCount,
        toggleRule,
        toggleCliRule,
        setCliRules,
        setRuleHookSurface,
        setRuleCliSurface,
        setExclusions,
        setSkipPaths,
        saveConfig,
        discardChanges,
        saveStatus,
        saveError,
        apiAvailable,
        loading,
      }}
    >
      {children}
    </RulesConfigContext.Provider>
  );
}
