import { act, cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AUTO_RALLY_CUE_MIN_GAP_MS, AUTO_RALLY_CUE_VISIBLE_MS, RallyCueOverlay } from "./RallyCueOverlay";

describe("RallyCueOverlay", () => {
  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  const state = () => document.querySelector("[data-auto-rally-cue]")?.getAttribute("data-auto-rally-cue");
  const text = () => document.querySelector("[data-auto-rally-cue]")?.textContent;

  it("shows for about two seconds and merges rally changes into the open cue", () => {
    vi.useFakeTimers();
    const { rerender } = render(<RallyCueOverlay cue={{ id: "r1", ordinal: 1, cause: "user" }} />);
    expect(state()).toBe("visible");
    rerender(<RallyCueOverlay cue={{ id: "r2", ordinal: 2, cause: "autoAdvance" }} />);
    expect(text()).toContain("第2回合");
    act(() => vi.advanceTimersByTime(AUTO_RALLY_CUE_VISIBLE_MS));
    expect(state()).toBe("hidden");
  });

  it("throttles automatic advances after fade-out but never throttles user navigation", () => {
    vi.useFakeTimers();
    const { rerender } = render(<RallyCueOverlay cue={{ id: "r1", ordinal: 1, cause: "user" }} />);
    act(() => vi.advanceTimersByTime(AUTO_RALLY_CUE_VISIBLE_MS));
    rerender(<RallyCueOverlay cue={{ id: "r2", ordinal: 2, cause: "autoAdvance" }} />);
    expect(state()).toBe("hidden");
    act(() => vi.advanceTimersByTime(AUTO_RALLY_CUE_MIN_GAP_MS));
    rerender(<RallyCueOverlay cue={{ id: "r3", ordinal: 3, cause: "autoAdvance" }} />);
    expect(state()).toBe("visible");
    act(() => vi.advanceTimersByTime(AUTO_RALLY_CUE_VISIBLE_MS));
    rerender(<RallyCueOverlay cue={{ id: "r4", ordinal: 4, cause: "user" }} />);
    expect(state()).toBe("visible");
    expect(text()).toContain("第4回合");
  });

  it("preserves the quiet-gap timestamp when auto-advance briefly leaves all rallies", () => {
    vi.useFakeTimers();
    const { rerender } = render(<RallyCueOverlay cue={{ id: "r1", ordinal: 1, cause: "user" }} />);
    act(() => vi.advanceTimersByTime(AUTO_RALLY_CUE_VISIBLE_MS + AUTO_RALLY_CUE_MIN_GAP_MS));
    rerender(<RallyCueOverlay cue={null} />);
    rerender(<RallyCueOverlay cue={{ id: "r2", ordinal: 2, cause: "autoAdvance" }} />);
    expect(state()).toBe("visible");
    expect(text()).toContain("第2回合");
  });

  it("repeats a user cue for a second navigation to the same rally", () => {
    vi.useFakeTimers();
    const { rerender } = render(<RallyCueOverlay cue={{ id: "r1", ordinal: 1, cause: "user", cueKey: 1 }} />);
    act(() => vi.advanceTimersByTime(AUTO_RALLY_CUE_VISIBLE_MS));
    act(() => vi.advanceTimersByTime(AUTO_RALLY_CUE_MIN_GAP_MS));
    rerender(<RallyCueOverlay cue={{ id: "r1", ordinal: 1, cause: "user", cueKey: 2 }} />);
    expect(state()).toBe("visible");
  });

  it("clears the cue when the playhead leaves a rally and lets pointer events pass through", () => {
    const { rerender } = render(<RallyCueOverlay cue={{ id: "r1", ordinal: 1, cause: "user" }} />);
    const overlay = document.querySelector<HTMLElement>("[data-auto-rally-cue]")!;
    expect(overlay.className).toContain("pointer-events-none");
    expect(overlay.getAttribute("aria-hidden")).toBe("true");
    rerender(<RallyCueOverlay cue={null} />);
    expect(document.querySelector("[data-auto-rally-cue]")).toBeNull();
  });
});
