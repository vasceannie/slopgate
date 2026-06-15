import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { HookEvent, RuleFinding } from "@/types/slopgate";
import { PathExplorer } from "./PathExplorer";

vi.mock("./FlagButton", () => ({
	FlagButton: () => <button type="button">flag</button>,
}));

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
		render(
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
			/>,
		);

		const srcRow = screen.getByRole("button", { name: "src" }).closest("tr");

		expect(screen.getByText("slopgate")).toBeInTheDocument();
		expect(screen.queryByRole("button", { name: "workspace" })).not.toBeInTheDocument();
		if (!srcRow) throw new Error("Expected src row to render");

		const cells = srcRow.querySelectorAll("td");
		expect(cells.item(1)).toHaveTextContent("2");
		expect(cells.item(2)).toHaveTextContent("1");
		expect(cells.item(3)).toHaveTextContent("1");
	});

	it("excludes absolute paths outside the project root from project file counts", () => {
		render(
			<PathExplorer
				activePathFilter={null}
				events={[
					event({
						candidate_paths: ["/workspace/other-device/outside.py"],
					}),
				]}
				onPathFilter={vi.fn()}
				rules={[finding()]}
			/>,
		);

		const table = screen.getByRole("table");

		expect(within(table).queryByRole("button", { name: "workspace" })).not.toBeInTheDocument();
		expect(within(table).queryByRole("button", { name: "outside.py" })).not.toBeInTheDocument();
		expect(screen.getByText("1 events · 1 findings")).toBeInTheDocument();
	});
});
