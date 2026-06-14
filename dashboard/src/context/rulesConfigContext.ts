import { createContext } from "react";
import type {
	RuleCliSurface,
	RuleHookSurface,
	SlopgateConfig,
} from "@/types/slopgate";

export type SaveStatus = "idle" | "saving" | "saved" | "error";

export interface RulesConfigContextValue {
	config: SlopgateConfig;
	savedConfig: SlopgateConfig;
	pendingCount: number;
	toggleRule: (rule_id: string) => void;
	toggleCliRule: (rule_id: string) => void;
	setCliRules: (rule_ids: string[], enabled: boolean) => void;
	setRuleHookSurface: (rule_id: string, hook: RuleHookSurface) => void;
	setRuleCliSurface: (
		rule_id: string,
		cliRuleIds: string[],
		cli: RuleCliSurface,
	) => void;
	setExclusions: (rule_id: string, globs: string[]) => void;
	setSkipPaths: (paths: string[]) => void;
	saveConfig: () => Promise<void>;
	discardChanges: () => void;
	saveStatus: SaveStatus;
	saveError: string | null;
	apiAvailable: boolean;
	loading: boolean;
}

export const EMPTY_CONFIG: SlopgateConfig = {
	enabled_rules: {},
	enabled_cli_rules: {},
	rule_surfaces: {},
	rule_counterparts: {},
	regex_rules: [],
	skip_paths: [],
};

export const RulesConfigContext = createContext<RulesConfigContextValue | null>(
	null,
);
