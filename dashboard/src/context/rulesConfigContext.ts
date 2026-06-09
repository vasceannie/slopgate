import { createContext } from "react";
import type { SlopgateConfig } from "@/types/slopgate";

type SaveStatus = "idle" | "saving" | "saved" | "error";

export interface RulesConfigContextValue {
  config: SlopgateConfig;
  pendingCount: number;
  toggleRule: (rule_id: string) => void;
  setExclusions: (rule_id: string, globs: string[]) => void;
  setSkipPaths: (paths: string[]) => void;
  saveConfig: () => Promise<void>;
  discardChanges: () => void;
  saveStatus: SaveStatus;
  saveError: string | null;
  apiAvailable: boolean;
  loading: boolean;
}

export const EMPTY_CONFIG: SlopgateConfig = { enabled_rules: {}, regex_rules: [], skip_paths: [] };

export const RulesConfigContext = createContext<RulesConfigContextValue | null>(null);
