import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AsyncJobs } from "./AsyncJobs";

describe("AsyncJobs", () => {
  it("renders idle state as a compact status row", () => {
    render(<AsyncJobs passCount={0} failCount={0} byCommand={[]} />);

    const idleState = screen.getByText("No async jobs ran in this window").closest("div");
    expect(idleState).toHaveClass("px-3");
    expect(idleState).toHaveClass("py-2");
    expect(screen.queryByText("Pass / Fail")).not.toBeInTheDocument();
  });
});
