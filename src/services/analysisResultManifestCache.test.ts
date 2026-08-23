import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("./analysisClient", () => ({ getAnalysisResult: vi.fn() }));

import { getAnalysisResult } from "./analysisClient";
import { clearAnalysisResultManifestCache, loadAnalysisResultManifest } from "./analysisResultManifestCache";

describe("analysis result manifest cache", () => {
  beforeEach(() => {
    clearAnalysisResultManifestCache();
    vi.mocked(getAnalysisResult).mockReset();
  });

  it("deduplicates the same job and isolates different job IDs", async () => {
    vi.mocked(getAnalysisResult).mockImplementation(async (jobId) => ({
      job_id: jobId,
      metrics: {},
      artifacts: {},
    }) as never);
    const [a1, a2, b] = await Promise.all([
      loadAnalysisResultManifest("job-a"),
      loadAnalysisResultManifest("job-a"),
      loadAnalysisResultManifest("job-b"),
    ]);
    expect(a1?.job_id).toBe("job-a");
    expect(a2).toBe(a1);
    expect(b?.job_id).toBe("job-b");
    expect(getAnalysisResult).toHaveBeenCalledTimes(2);
  });

  it("does not cache failed requests", async () => {
    vi.mocked(getAnalysisResult).mockRejectedValueOnce(new Error("offline")).mockResolvedValueOnce({
      job_id: "job-a",
      metrics: {},
      artifacts: {},
    } as never);
    await expect(loadAnalysisResultManifest("job-a")).rejects.toThrow("offline");
    await expect(loadAnalysisResultManifest("job-a")).resolves.toMatchObject({ job_id: "job-a" });
    expect(getAnalysisResult).toHaveBeenCalledTimes(2);
  });
});
