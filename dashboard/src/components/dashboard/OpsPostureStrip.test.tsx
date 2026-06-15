import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { HarnessStatusState } from "@/hooks/useHarnessStatus";
import type { RuntimeConfig } from "@/types/slopgate";
import { OpsPostureStrip } from "./OpsPostureStrip";

const CONFIG: RuntimeConfig = {
	disabled_rules: [],
	severity_overrides: [],
	skip_paths: [],
	skip_repos: [],
};

function renderOpsPostureStrip(harnessStatus: HarnessStatusState) {
	render(
		<OpsPostureStrip
			asyncFailCount={0}
			config={CONFIG}
			harnessStatus={harnessStatus}
		/>,
	);
}

function harnessSummary(): HTMLElement {
	const summary = screen.getByText("Harnesses:").closest("div");
	if (!(summary instanceof HTMLElement)) {
		throw new Error("Harness summary row did not render");
	}
	return summary;
}

describe("OpsPostureStrip", () => {
	it("renders unavailable harness count for empty harness status", () => {
		renderOpsPostureStrip({
			status: { ok: true, platforms: [] },
			loading: false,
			error: null,
		});

		expect(within(harnessSummary()).getByText("—")).toBeInTheDocument();
	});

	it("renders unavailable harness count when harness status fails", () => {
		renderOpsPostureStrip({
			status: null,
			loading: false,
			error: "backend unavailable",
		});

		expect(within(harnessSummary()).getByText("—")).toBeInTheDocument();
	});
});
