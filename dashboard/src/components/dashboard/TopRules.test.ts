import { describe, expect, it } from "vitest";
import { DEFAULT_TOP_RULE_VIEW } from "./TopRules";

describe("TopRules defaults", () => {
  it("opens on the enforcement view before advisory firing telemetry", () => {
    expect(DEFAULT_TOP_RULE_VIEW).toBe("blocking");
  });
});
