import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AnalysisFlowSelector } from "./AnalysisFlowSelector";

describe("AnalysisFlowSelector", () => {
  it("shows the new flow as the selected default and allows legacy fallback", () => {
    const onChange = vi.fn();
    render(<AnalysisFlowSelector value="new" onChange={onChange} />);

    expect(screen.getByTestId("analysis-flow-new").getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByTestId("analysis-flow-legacy").getAttribute("aria-pressed")).toBe("false");

    fireEvent.click(screen.getByTestId("analysis-flow-legacy"));
    expect(onChange).toHaveBeenCalledWith("legacy");
  });
});
