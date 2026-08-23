import { afterEach, describe, expect, it, vi } from "vitest";
import {
  getAnalysisRuntimeSnapshot,
  listWatchedAnalysisJobs,
  seedAnalysisRuntimeSnapshot,
  subscribeAnalysisRuntime,
  unwatchAnalysisJob,
  watchAnalysisJob,
} from "./analysisRuntimeStore";

describe("analysisRuntimeStore", () => {
  afterEach(() => {
    for (const id of [...listWatchedAnalysisJobs()]) unwatchAnalysisJob(id, true);
  });

  it("stores and reads a seeded snapshot", () => {
    seedAnalysisRuntimeSnapshot({
      jobId: "job-1",
      status: "processing",
      progress: 42,
      stage: "轨迹跟踪",
      stages: [],
    });
    const snap = getAnalysisRuntimeSnapshot("job-1");
    expect(snap?.progress).toBe(42);
    expect(snap?.stage).toBe("轨迹跟踪");
  });

  it("watches active jobs (deduplicated), notifies subscribers, and unwatch clears snapshot", () => {
    watchAnalysisJob("job-1");
    expect(listWatchedAnalysisJobs()).toContain("job-1");

    const listener = vi.fn();
    const unsubscribe = subscribeAnalysisRuntime(listener);

    // 去重：重复 watch 不产生第二个
    watchAnalysisJob("job-1");
    expect(listWatchedAnalysisJobs().length).toBe(1);

    seedAnalysisRuntimeSnapshot({ jobId: "job-1", status: "processing", progress: 10, stages: [] });
    expect(getAnalysisRuntimeSnapshot("job-1")?.progress).toBe(10);

    unwatchAnalysisJob("job-1", true);
    expect(listWatchedAnalysisJobs()).not.toContain("job-1");
    expect(getAnalysisRuntimeSnapshot("job-1")).toBeUndefined();

    unsubscribe();
  });

  it("tracks multiple watched jobs independently", () => {
    watchAnalysisJob("job-a");
    watchAnalysisJob("job-b");
    seedAnalysisRuntimeSnapshot({ jobId: "job-a", status: "processing", progress: 5, stages: [] });
    seedAnalysisRuntimeSnapshot({ jobId: "job-b", status: "queued", progress: 0, stages: [] });

    expect(listWatchedAnalysisJobs().sort()).toEqual(["job-a", "job-b"]);
    expect(getAnalysisRuntimeSnapshot("job-a")?.progress).toBe(5);
    expect(getAnalysisRuntimeSnapshot("job-b")?.status).toBe("queued");

    unwatchAnalysisJob("job-a", true);
    expect(getAnalysisRuntimeSnapshot("job-a")).toBeUndefined();
    expect(getAnalysisRuntimeSnapshot("job-b")?.progress).toBe(0);
  });
});
