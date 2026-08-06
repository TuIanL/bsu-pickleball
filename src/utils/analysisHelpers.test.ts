import { describe, expect, it } from "vitest";
import {
  ANALYSIS_MODES,
  applyModeSelection,
  canonicalPlayerNumber,
  eligibleJobsByMode,
  formatPlayerId,
  isTerminalAnalysisJob,
  modeSelectionState,
  sortAnalysisJobs,
} from "./analysisHelpers";
import type { AnalysisJobSummary } from "../types/report";

function makeJob(
  id: string,
  status: AnalysisJobSummary["status"],
  createdAt: string,
  updatedAt?: string,
  analysisMode?: AnalysisJobSummary["analysisMode"],
): AnalysisJobSummary {
  return {
    id,
    status,
    stage: "queue",
    progress: 0,
    createdAt,
    updatedAt: updatedAt ?? createdAt,
    analysisMode,
    metadata: {} as AnalysisJobSummary["metadata"],
    stages: [],
  } as AnalysisJobSummary;
}

describe("canonicalPlayerNumber", () => {
  it("parses Player_1..Player_4 as numbers 1..4", () => {
    expect(canonicalPlayerNumber("Player_1")).toBe(1);
    expect(canonicalPlayerNumber("Player_2")).toBe(2);
    expect(canonicalPlayerNumber("Player_3")).toBe(3);
    expect(canonicalPlayerNumber("Player_4")).toBe(4);
  });

  it("returns null for non-canonical inputs", () => {
    expect(canonicalPlayerNumber(null)).toBeNull();
    expect(canonicalPlayerNumber(undefined)).toBeNull();
    expect(canonicalPlayerNumber("")).toBeNull();
    expect(canonicalPlayerNumber("Player_0")).toBeNull();
    expect(canonicalPlayerNumber("Player_5")).toBeNull();
    expect(canonicalPlayerNumber("164")).toBeNull();
    expect(canonicalPlayerNumber("T164")).toBeNull();
    expect(canonicalPlayerNumber("player_1")).toBeNull();
    expect(canonicalPlayerNumber(" ID 172 ")).toBeNull();
  });

  it("handles leading/trailing whitespace", () => {
    expect(canonicalPlayerNumber("  Player_3  ")).toBe(3);
  });
});

describe("formatPlayerId", () => {
  it("formats canonical player ids as P1..P4", () => {
    expect(formatPlayerId("Player_1")).toBe("P1");
    expect(formatPlayerId("Player_2")).toBe("P2");
    expect(formatPlayerId("Player_3")).toBe("P3");
    expect(formatPlayerId("Player_4")).toBe("P4");
  });

  it("returns empty string for non-canonical values", () => {
    expect(formatPlayerId(null)).toBe("");
    expect(formatPlayerId(undefined)).toBe("");
    expect(formatPlayerId("")).toBe("");
    expect(formatPlayerId("164")).toBe("");
    expect(formatPlayerId("player_1")).toBe("");
  });
});

describe("isTerminalAnalysisJob", () => {
  it("returns true for failed and canceled tasks", () => {
    expect(isTerminalAnalysisJob(makeJob("a", "failed", "2026-01-01T00:00:00Z"))).toBe(true);
    expect(isTerminalAnalysisJob(makeJob("b", "canceled", "2026-01-01T00:00:00Z"))).toBe(true);
  });

  it("returns false for other statuses", () => {
    expect(isTerminalAnalysisJob(makeJob("c", "completed", "2026-01-01T00:00:00Z"))).toBe(false);
    expect(isTerminalAnalysisJob(makeJob("d", "processing", "2026-01-01T00:00:00Z"))).toBe(false);
    expect(isTerminalAnalysisJob(makeJob("e", "queued", "2026-01-01T00:00:00Z"))).toBe(false);
    expect(isTerminalAnalysisJob(makeJob("f", "uploaded", "2026-01-01T00:00:00Z"))).toBe(false);
  });
});

describe("sortAnalysisJobs", () => {
  const old = makeJob("old", "completed", "2026-01-01T00:00:00Z");
  const mid = makeJob("mid", "failed", "2026-02-01T00:00:00Z");
  const recent = makeJob("recent", "completed", "2026-03-01T00:00:00Z");

  it("sorts by createdAt newest first by default direction", () => {
    const sorted = sortAnalysisJobs([old, recent, mid], "createdAt", "desc");
    expect(sorted.map((j) => j.id)).toEqual(["recent", "mid", "old"]);
  });

  it("sorts by createdAt oldest first when asc", () => {
    const sorted = sortAnalysisJobs([recent, old, mid], "createdAt", "asc");
    expect(sorted.map((j) => j.id)).toEqual(["old", "mid", "recent"]);
  });

  it("prefers updatedAt over createdAt when sorting by update time", () => {
    const a = makeJob("a", "completed", "2026-01-01T00:00:00Z", "2026-02-01T00:00:00Z");
    const b = makeJob("b", "completed", "2026-03-01T00:00:00Z", "2026-01-01T00:00:00Z");
    const sorted = sortAnalysisJobs([a, b], "updatedAt", "desc");
    expect(sorted.map((j) => j.id)).toEqual(["a", "b"]);
  });

  it("falls back to createdAt when updatedAt is empty", () => {
    const a = makeJob("a", "completed", "2026-01-01T00:00:00Z", "");
    const b = makeJob("b", "completed", "2026-02-01T00:00:00Z", "2026-03-01T00:00:00Z");
    const sorted = sortAnalysisJobs([b, a], "updatedAt", "asc");
    expect(sorted.map((j) => j.id)).toEqual(["a", "b"]);
  });

  it("does not mutate the input array", () => {
    const input = [old, recent, mid];
    sortAnalysisJobs(input, "createdAt", "desc");
    expect(input.map((j) => j.id)).toEqual(["old", "recent", "mid"]);
  });
});

describe("ANALYSIS_MODES", () => {
  it("covers demo, limited and real in order", () => {
    expect(ANALYSIS_MODES).toEqual(["demo", "limited", "real"]);
  });
});

describe("eligibleJobsByMode", () => {
  it("filters deletable jobs by analysis mode", () => {
    const jobs = [
      makeJob("a", "completed", "2026-01-01T00:00:00Z", undefined, "demo"),
      makeJob("b", "completed", "2026-01-01T00:00:00Z", undefined, "real"),
      makeJob("c", "failed", "2026-01-01T00:00:00Z", undefined, "demo"),
      makeJob("d", "completed", "2026-01-01T00:00:00Z", undefined, "limited"),
      makeJob("e", "completed", "2026-01-01T00:00:00Z", undefined, undefined),
    ];
    expect(eligibleJobsByMode(jobs, "demo").map((j) => j.id)).toEqual(["a", "c"]);
    expect(eligibleJobsByMode(jobs, "real").map((j) => j.id)).toEqual(["b"]);
    expect(eligibleJobsByMode(jobs, "limited").map((j) => j.id)).toEqual(["d"]);
  });

  it("excludes active jobs from mode selection", () => {
    const jobs = [
      makeJob("active-demo", "processing", "2026-01-01T00:00:00Z", undefined, "demo"),
      makeJob("done-demo", "completed", "2026-01-01T00:00:00Z", undefined, "demo"),
      makeJob("queued-real", "queued", "2026-01-01T00:00:00Z", undefined, "real"),
      makeJob("canceled-limited", "canceled", "2026-01-01T00:00:00Z", undefined, "limited"),
    ];
    expect(eligibleJobsByMode(jobs, "demo").map((j) => j.id)).toEqual(["done-demo"]);
    expect(eligibleJobsByMode(jobs, "real").map((j) => j.id)).toEqual([]);
    expect(eligibleJobsByMode(jobs, "limited").map((j) => j.id)).toEqual(["canceled-limited"]);
  });
});

describe("modeSelectionState", () => {
  it("returns checked when all eligible ids are selected", () => {
    expect(modeSelectionState(["a", "b"], ["a", "b"])).toBe("checked");
    expect(modeSelectionState(["a", "b"], ["x", "a", "b"])).toBe("checked");
  });

  it("returns unchecked when none are selected", () => {
    expect(modeSelectionState(["a", "b"], [])).toBe("unchecked");
    expect(modeSelectionState(["a", "b"], ["c"])).toBe("unchecked");
  });

  it("returns indeterminate on partial selection", () => {
    expect(modeSelectionState(["a", "b"], ["a"])).toBe("indeterminate");
    expect(modeSelectionState(["a", "b"], ["a", "c"])).toBe("indeterminate");
  });

  it("returns unchecked for an empty eligible set", () => {
    expect(modeSelectionState([], ["a"])).toBe("unchecked");
  });
});

describe("applyModeSelection", () => {
  it("adds all eligible ids when checking", () => {
    expect(applyModeSelection([], ["a", "b"], true)).toEqual(["a", "b"]);
    expect(applyModeSelection(["c"], ["a", "b"], true).sort()).toEqual(["a", "b", "c"]);
  });

  it("removes all eligible ids when unchecking", () => {
    expect(applyModeSelection(["a", "b", "c"], ["a", "b"], false)).toEqual(["c"]);
  });

  it("keeps unrelated selections untouched and deduplicates", () => {
    expect(applyModeSelection(["a"], ["a"], true)).toEqual(["a"]);
    expect(applyModeSelection(["a", "b"], ["c"], false)).toEqual(["a", "b"]);
  });

  it("does not mutate the input array", () => {
    const input = ["a"];
    const result = applyModeSelection(input, ["b"], true);
    expect(input).toEqual(["a"]);
    expect(result).toEqual(["a", "b"]);
  });
});
