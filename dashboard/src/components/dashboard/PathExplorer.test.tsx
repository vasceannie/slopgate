import { render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import {
	RulesConfigContext,
	type RulesConfigContextValue,
} from "@/context/rulesConfigContext";
import type { HookEvent, RuleFinding } from "@/types/slopgate";
import { PathExplorer } from "./PathExplorer";

vi.mock("./FlagButton", () => ({
	FlagButton: () => <button type="button">flag</button>,
}));

const CONFIG = {
	enabled_rules: { "PY-CODE-013": true },
	enabled_cli_rules: {},
	rule_surfaces: { "PY-CODE-013": { hook: { enabled: true } } },
	rule_counterparts: {},
	regex_rules: [],
	skip_paths: [],
};

function renderWithRuleConfig(children: ReactNode) {
	const value: RulesConfigContextValue = {
		config: CONFIG,
		savedConfig: CONFIG,
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
			{children}
		</RulesConfigContext.Provider>,
	);
}

function event(overrides: Partial<HookEvent> = {}): HookEvent {
	return {
		timestamp: "2026-06-14T12:00:00.000Z",
		platform: "opencode",
		event_name: "PreToolUse",
		session_id: "session-1",
		tool_name: "Edit",
		candidate_paths: [],
		languages: [],
		enforcement_mode: "repo_strict",
		resolved_repo_root: "/workspace/projects/slopgate",
		...overrides,
	};
}

function finding(overrides: Partial<RuleFinding> = {}): RuleFinding {
	return {
		timestamp: "2026-06-14T12:00:01.000Z",
		platform: "opencode",
		event_name: "PostToolUse",
		session_id: "session-1",
		tool_name: "Edit",
		rule_id: "PY-CODE-013",
		severity: "HIGH",
		decision: "block",
		message: "Feature envy detected",
		additional_context: null,
		metadata: {},
		enforcement_mode: "repo_strict",
		resolved_repo_root: "/workspace/projects/slopgate",
		...overrides,
	};
}

describe("PathExplorer", () => {
	it("scopes absolute candidate paths to project-relative rows and counts", () => {
		renderWithRuleConfig(
			<PathExplorer
				activePathFilter={null}
				events={[
					event({
						timestamp: "2026-06-14T12:00:00.000Z",
						candidate_paths: ["/workspace/projects/slopgate/src/hot.py"],
					}),
					event({
						timestamp: "2026-06-14T12:00:02.000Z",
						candidate_paths: ["/workspace/projects/slopgate/src/hot.py"],
					}),
				]}
				onPathFilter={vi.fn()}
				rules={[finding()]}
				defaultTab="telemetry"
			/>
		);

		const srcRow = screen.getByRole("button", { name: "src" }).closest("tr");

		expect(screen.getAllByText("slopgate").length).toBeGreaterThan(0);
		expect(screen.queryByRole("button", { name: "workspace" })).not.toBeInTheDocument();
		if (!srcRow) throw new Error("Expected src row to render");

		const cells = srcRow.querySelectorAll("td");
		expect(cells.item(1)).toHaveTextContent("2");
		expect(cells.item(2)).toHaveTextContent("1");
		expect(cells.item(3)).toHaveTextContent("1");
	});

	it("excludes absolute paths outside the project root from project file counts", () => {
		renderWithRuleConfig(
			<PathExplorer
				activePathFilter={null}
				events={[
					event({
						candidate_paths: ["/workspace/other-device/outside.py"],
					}),
				]}
				onPathFilter={vi.fn()}
				rules={[finding()]}
				defaultTab="telemetry"
			/>
		);

		const table = screen.getByRole("table");

		expect(within(table).queryByRole("button", { name: "workspace" })).not.toBeInTheDocument();
		expect(within(table).queryByRole("button", { name: "outside.py" })).not.toBeInTheDocument();
		expect(screen.getAllByText("1 events · 1 findings").length).toBeGreaterThan(0);
	});
});
