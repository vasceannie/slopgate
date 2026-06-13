import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import {
	RulesConfigContext,
	type RulesConfigContextValue,
} from "@/context/rulesConfigContext";
import type { SlopgateConfig } from "@/types/slopgate";
import { RuleManager } from "./RuleManager";

const CONFIG: SlopgateConfig = {
	enabled_rules: { "PY-CODE-008": true },
	enabled_cli_rules: { "long-method": true },
	rule_surfaces: {},
	rule_counterparts: { "PY-CODE-008": ["long-method"] },
	regex_rules: [],
	skip_paths: [],
};

function renderRuleManager(
	config: SlopgateConfig = CONFIG,
	fireCounts: Map<string, number> = new Map([
		["PY-CODE-008", 1],
		["long-method", 2],
	]),
) {
	const value: RulesConfigContextValue = {
		config,
		pendingCount: 0,
		toggleRule: vi.fn(),
		toggleCliRule: vi.fn(),
		setCliRules: vi.fn(),
		setRuleHookSurface: vi.fn(),
		setRuleCliSurface: vi.fn(),
		setExclusions: vi.fn(),
		setSkipPaths: vi.fn(),
		saveConfig: vi.fn(async () => undefined),
		discardChanges: vi.fn(),
		saveStatus: "idle",
		saveError: null,
		apiAvailable: true,
		loading: false,
	};

	render(
		<RulesConfigContext.Provider value={value}>
			<RuleManager fireCounts={fireCounts} />
		</RulesConfigContext.Provider>,
	);

	return value;
}

describe("RuleManager", () => {
	it("routes hook and CLI surfaces through the canonical rule row", () => {
		const value = renderRuleManager();

		fireEvent.click(
			screen.getByRole("switch", { name: "PY-CODE-008 hook enablement" }),
		);
		fireEvent.click(
			screen.getByRole("switch", { name: "PY-CODE-008 CLI enablement" }),
		);

		expect(value.setRuleHookSurface).toHaveBeenCalledWith("PY-CODE-008", {
			enabled: false,
		});
		expect(value.setRuleCliSurface).toHaveBeenCalledWith(
			"PY-CODE-008",
			["long-method"],
			{ enabled: false },
		);
		expect(value.setCliRules).not.toHaveBeenCalled();
		expect(value.toggleRule).not.toHaveBeenCalledWith("long-method");
		expect(value.toggleCliRule).not.toHaveBeenCalled();
	});

	it("folds mapped CLI checks into their hook rule row", () => {
		renderRuleManager();

		fireEvent.click(screen.getByRole("button", { name: "PY-CODE-008" }));
		expect(screen.getByText("CLI checks: long-method")).toBeInTheDocument();
		expect(
			screen.queryByRole("button", { name: "long-method" }),
		).not.toBeInTheDocument();
	});

	it("exposes hook rules backed by new batch lint collectors as dual-surface", () => {
		const value = renderRuleManager(
			{
				...CONFIG,
				enabled_rules: { "PY-CODE-012": true },
				enabled_cli_rules: { "feature-envy": true },
				rule_counterparts: { "PY-CODE-012": ["feature-envy"] },
			},
			new Map([["PY-CODE-012", 1]]),
		);

		fireEvent.click(
			screen.getByRole("switch", { name: "PY-CODE-012 CLI enablement" }),
		);

		expect(value.setRuleCliSurface).toHaveBeenCalledWith(
			"PY-CODE-012",
			["feature-envy"],
			{ enabled: false },
		);
		expect(
			screen.queryByRole("button", { name: "feature-envy" }),
		).not.toBeInTheDocument();
	});

	it("exposes import hook rules as opt-in CLI counterparts", () => {
		const value = renderRuleManager(
			{
				...CONFIG,
				enabled_rules: { "PY-IMPORT-002": true },
				enabled_cli_rules: {},
				rule_counterparts: { "PY-IMPORT-002": ["import-alias"] },
			},
			new Map([["PY-IMPORT-002", 1]]),
		);

		fireEvent.click(
			screen.getByRole("switch", { name: "PY-IMPORT-002 CLI enablement" }),
		);

		expect(value.setRuleCliSurface).toHaveBeenCalledWith(
			"PY-IMPORT-002",
			["import-alias"],
			{ enabled: true },
		);
		expect(
			screen.queryByRole("button", { name: "import-alias" }),
		).not.toBeInTheDocument();
	});

	it("exposes boundary logging as an opt-in CLI counterpart", () => {
		const value = renderRuleManager(
			{
				...CONFIG,
				enabled_rules: { "PY-LOG-002": true },
				enabled_cli_rules: {},
				rule_counterparts: { "PY-LOG-002": ["boundary-logging"] },
			},
			new Map([["PY-LOG-002", 1]]),
		);

		fireEvent.click(
			screen.getByRole("switch", { name: "PY-LOG-002 CLI enablement" }),
		);

		expect(value.setRuleCliSurface).toHaveBeenCalledWith(
			"PY-LOG-002",
			["boundary-logging"],
			{ enabled: true },
		);
		expect(
			screen.queryByRole("button", { name: "boundary-logging" }),
		).not.toBeInTheDocument();
	});

	it("exposes pytest asyncio as an opt-in CLI counterpart", () => {
		const value = renderRuleManager(
			{
				...CONFIG,
				enabled_rules: { "PY-TEST-005": true },
				enabled_cli_rules: {},
				rule_counterparts: { "PY-TEST-005": ["pytest-asyncio-pattern"] },
			},
			new Map([["PY-TEST-005", 1]]),
		);

		fireEvent.click(
			screen.getByRole("switch", { name: "PY-TEST-005 CLI enablement" }),
		);

		expect(value.setRuleCliSurface).toHaveBeenCalledWith(
			"PY-TEST-005",
			["pytest-asyncio-pattern"],
			{ enabled: true },
		);
		expect(
			screen.queryByRole("button", { name: "pytest-asyncio-pattern" }),
		).not.toBeInTheDocument();
	});

	it("exposes LangGraph rules as opt-in CLI counterparts", () => {
		const value = renderRuleManager(
			{
				...CONFIG,
				enabled_rules: { "LG-API-001": true },
				enabled_cli_rules: {},
				rule_counterparts: {
					"LG-API-001": ["langgraph-deprecated-api"],
				},
			},
			new Map([["LG-API-001", 1]]),
		);

		fireEvent.click(
			screen.getByRole("switch", { name: "LG-API-001 CLI enablement" }),
		);

		expect(value.setRuleCliSurface).toHaveBeenCalledWith(
			"LG-API-001",
			["langgraph-deprecated-api"],
			{ enabled: true },
		);
		expect(
			screen.queryByRole("button", { name: "langgraph-deprecated-api" }),
		).not.toBeInTheDocument();
	});

	it("labels unsupported surfaces instead of rendering an ambiguous dash", () => {
		renderRuleManager({
				...CONFIG,
				enabled_rules: { "CONFIG-001": true },
				enabled_cli_rules: {},
				rule_counterparts: {},
			},
			new Map([["CONFIG-001", 1]]),
		);

		expect(
			screen.getByRole("switch", { name: "CONFIG-001 hook enablement" }),
		).toBeInTheDocument();
		expect(screen.getByText("config safety")).toBeInTheDocument();
		expect(
			screen.queryByRole("switch", { name: "CONFIG-001 CLI enablement" }),
		).not.toBeInTheDocument();
	});

	it("labels hook-only capability boundaries", () => {
		renderRuleManager(
			{
				...CONFIG,
				enabled_rules: {
					"BUILTIN-PROTECTED-PATHS": true,
					"ERRORS-BASH-001": true,
					"GIT-003": true,
					"SESSION-001": true,
				},
				enabled_cli_rules: {},
				rule_counterparts: {},
			},
			new Map([
				["BUILTIN-PROTECTED-PATHS", 1],
				["ERRORS-BASH-001", 1],
				["GIT-003", 1],
				["SESSION-001", 1],
			]),
		);

		expect(screen.getByText("protected mutation")).toBeInTheDocument();
		expect(screen.getByText("runtime payload")).toBeInTheDocument();
		expect(screen.getByText("command only")).toBeInTheDocument();
		expect(screen.getByText("session lifecycle")).toBeInTheDocument();
	});

	it("labels CLI-only rows as source lint", () => {
		renderRuleManager(
			{
				...CONFIG,
				enabled_rules: {},
				enabled_cli_rules: { "long-test": true },
				rule_counterparts: {},
			},
			new Map([["long-test", 1]]),
		);

		expect(screen.getAllByText("source lint available").length).toBeGreaterThan(
			0,
		);
		expect(
			screen.queryByRole("switch", { name: "long-test hook enablement" }),
		).not.toBeInTheDocument();
	});

	it("exposes content regex rules as real hook and CLI surfaces", () => {
		const value = renderRuleManager(
			{
				...CONFIG,
				enabled_rules: { "CUSTOM-CONTENT-001": true },
				enabled_cli_rules: {},
				rule_counterparts: {},
				regex_rules: [
					{
						rule_id: "CUSTOM-CONTENT-001",
						title: "Custom content rule",
						severity: "HIGH",
						events: ["PreToolUse"],
						target: "content",
						patterns: ["secret"],
						action: "deny",
					},
				],
			},
			new Map([["CUSTOM-CONTENT-001", 1]]),
		);

		fireEvent.click(
			screen.getByRole("switch", {
				name: "CUSTOM-CONTENT-001 CLI enablement",
			}),
		);

		expect(
			screen.getByRole("switch", {
				name: "CUSTOM-CONTENT-001 hook enablement",
			}),
		).toBeInTheDocument();
		expect(value.setRuleCliSurface).toHaveBeenCalledWith(
			"CUSTOM-CONTENT-001",
			["CUSTOM-CONTENT-001"],
			{ enabled: true },
		);
	});

	it("edits hook action and event filters through rule surfaces", () => {
		const value = renderRuleManager({
			...CONFIG,
			rule_surfaces: {
				"PY-CODE-008": {
					hook: { action: "ask", events: ["PreToolUse"] },
				},
			},
		});

		fireEvent.click(screen.getByRole("button", { name: "PY-CODE-008" }));
		fireEvent.change(screen.getByRole("combobox"), {
			target: { value: "deny" },
		});
		fireEvent.click(screen.getByRole("button", { name: "PostToolUse" }));
		fireEvent.click(screen.getByRole("button", { name: "PreToolUse" }));

		expect(value.setRuleHookSurface).toHaveBeenCalledWith("PY-CODE-008", {
			action: "deny",
		});
		expect(value.setRuleHookSurface).toHaveBeenCalledWith("PY-CODE-008", {
			events: ["PostToolUse", "PreToolUse"],
		});
		expect(value.setRuleHookSurface).toHaveBeenCalledWith("PY-CODE-008", {
			events: [],
		});
	});
});
