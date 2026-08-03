import { afterEach, describe, expect, it, vi } from "vitest";
import { createAnalysisJob, getAnalysisReport, listAnalysisJobs } from "./analysisClient";

describe("analysis job compatibility", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it("normalizes legacy recording metadata without requiring top-level fields", async () => {
    const legacyJob = {
      id: "job-legacy-recording",
      status: "completed",
      stage: "report",
      progress: 100,
      createdAt: "2026-08-03T00:00:00.000Z",
      updatedAt: "2026-08-03T00:00:00.000Z",
      metadata: {
        fileName: "legacy.mp4",
        matchTitle: "历史任务",
        venue: "测试球场",
        matchDate: "2026-08-03",
        matchFormat: "doubles",
        cameraAngle: "baseline",
        athleteLabel: "Player A",
        level: "MVP",
        recording_session_id: "rec-legacy",
        camera_slot: "cam_2",
      },
      stages: [],
    };

    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify([legacyJob]), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );

    const [job] = await listAnalysisJobs();

    expect(job.recordingSessionId).toBe("rec-legacy");
    expect(job.cameraSlot).toBe("cam_2");
    expect(job.metadata.recording_session_id).toBe("rec-legacy");
    expect(job.metadata.camera_slot).toBe("cam_2");
  });

  it("does not turn a real API failure into a local demo job", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("backend offline"));

    await expect(createAnalysisJob({
      metadata: {
        fileName: "real.mp4",
        matchTitle: "真实任务",
        venue: "测试球场",
        matchDate: "2026-08-03",
        matchFormat: "doubles",
        cameraAngle: "baseline",
        athleteLabel: "Player A",
        level: "MVP",
      },
      videoId: "video-real",
      useDemoFallback: false,
    })).rejects.toMatchObject({
      name: "AnalysisApiError",
      isNetworkError: true,
    });
  });

  it("only uses the local job list when demo fallback is explicit", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("backend offline"));
    const metadata = {
      fileName: "demo.mp4",
      matchTitle: "样例任务",
      venue: "测试球场",
      matchDate: "2026-08-03",
      matchFormat: "doubles" as const,
      cameraAngle: "baseline" as const,
      athleteLabel: "Player A",
      level: "MVP" as const,
    };

    const demoJob = await createAnalysisJob({ metadata, useDemoFallback: true });
    await expect(listAnalysisJobs()).rejects.toMatchObject({ name: "AnalysisApiError" });
    await expect(listAnalysisJobs({ useDemoFallback: true })).resolves.toEqual([demoJob]);
    await expect(getAnalysisReport(demoJob.id)).resolves.toMatchObject({ source: "job", jobId: demoJob.id });
  });

  it("preserves HTTP errors instead of reading unrelated local jobs", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: "database unavailable" }), {
        status: 503,
        statusText: "Service Unavailable",
        headers: { "content-type": "application/json" },
      }),
    );

    await expect(listAnalysisJobs()).rejects.toMatchObject({
      name: "AnalysisApiError",
      status: 503,
      isNetworkError: false,
      backendDetail: "database unavailable",
    });
  });
});
