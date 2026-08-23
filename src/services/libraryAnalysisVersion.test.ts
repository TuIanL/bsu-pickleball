import { describe, expect, it } from "vitest";
import type { LibraryItemViewModel } from "./libraryAdapter";
import { buildLibraryWorkspacePath, resolveSelectedAnalysisJob } from "./libraryAnalysisVersion";

const baseItem = {
  ref: { kind: "sync_recording", sourceId: "sync/1" },
  primaryResultAnalysisJobId: "new",
  primaryAnalysisJobId: "new",
  analysisJobs: [
    { id: "new", status: "completed", createdAt: "2026-08-02" },
    { id: "old", status: "completed", createdAt: "2026-08-01" },
    { id: "failed", status: "failed", createdAt: "2026-07-31" },
    { id: "active", status: "processing", createdAt: "2026-08-03" },
  ],
} as LibraryItemViewModel;

describe("library analysis version", () => {
  it.each([
    [undefined, "new", false, false],
    ["old", "old", true, false],
    ["failed", "failed", true, false],
    ["other-material", "new", false, true],
    ["internal-child", "new", false, true],
    ["active", "new", false, true],
  ])("resolves %s", (requested, selected, explicit, invalid) => {
    expect(resolveSelectedAnalysisJob(baseItem, requested)).toMatchObject({
      selectedJobId: selected,
      explicit,
      invalidRequestedJob: invalid,
    });
  });

  it("falls back safely after a selected job is deleted", () => {
    expect(resolveSelectedAnalysisJob(baseItem, "deleted").selectedJobId).toBe("new");
  });

  it("merges view/version/time while preserving unrelated query", () => {
    expect(buildLibraryWorkspacePath(baseItem.ref, {
      view: "report",
      analysisJobId: "old",
      time: 12.5,
      search: "?view=analysis&foo=bar",
    })).toBe("/library/sync_recording/sync%2F1?view=report&foo=bar&analysisJob=old&t=12.5");
  });

  it("can remove only an invalid analysisJob", () => {
    expect(buildLibraryWorkspacePath(baseItem.ref, {
      analysisJobId: null,
      search: "?view=trajectory&analysisJob=forged&t=4&foo=bar",
    })).toContain("view=trajectory&t=4&foo=bar");
  });
});
