import { afterEach, describe, expect, it, vi } from "vitest";
import {
  confirmSyncAnchors,
  createAnalysisJob,
  createMultiviewAnalysisJob,
  deleteRecordingAnalysis,
  getAnalysisReport,
  getStructuredVizData,
  getMultiviewBallStereoEvidence,
  getShotRallyEvents,
  getSyncAnchorExportUrl,
  getSyncAnchorStatus,
  listAnalysisJobs,
  saveSyncAnchorDraft,
} from "./analysisClient";
import structuredVisualizationFixture from "../test/fixtures/structured-visualization.zone-stats.v1.json";

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

  it("reads Parent-owned multiview stereo evidence through the scoped artifact URL", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({
        schema_version: "multiview_ball_stereo_evidence.v1",
        measurements: [],
      }), { status: 200, headers: { "content-type": "application/json" } }),
    );

    const result = {
      artifacts: {
        multiview_ball_stereo_evidence_url: "/api/analysis/jobs/job-parent/artifacts/multiview-ball-stereo-evidence",
      },
    } as never;
    await expect(getMultiviewBallStereoEvidence(result)).resolves.toMatchObject({
      schema_version: "multiview_ball_stereo_evidence.v1",
    });
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/analysis/jobs/job-parent/artifacts/multiview-ball-stereo-evidence"),
      expect.any(Object),
    );
  });

  it("reads the job-scoped structured visualization artifact without replacing it with demo data", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(structuredVisualizationFixture), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );

    const data = await getStructuredVizData("job-zone-fixture");
    expect(data?.zone_stats?.players[0]?.id).toBe("Player_1");
    expect(data?.zone_stats?.players[0]?.zones).toHaveLength(3);
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/analysis/jobs/job-zone-fixture/visualization-data"),
      expect.any(Object),
    );
  });

  it("preserves a missing historical structured artifact for the evidence layer to classify", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("not found", { status: 404 }));
    await expect(getStructuredVizData("job-old")).rejects.toMatchObject({ status: 404 });
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

  it("treats a missing historical shot-rally artifact as unavailable", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("not found", { status: 404 }));
    const result = { artifacts: { shot_rally_events_url: "/api/analysis/jobs/job-old/artifacts/shot-rally-events" } } as never;

    await expect(getShotRallyEvents(result)).resolves.toBeNull();
  });

  it("surfaces malformed shot-rally artifact payloads to the independent card state", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("{malformed", { status: 200, headers: { "content-type": "application/json" } }));
    const result = { artifacts: { shot_rally_events_url: "/api/analysis/jobs/job-bad/artifacts/shot-rally-events" } } as never;

    await expect(getShotRallyEvents(result)).rejects.toBeTruthy();
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

  it("keeps structured sync-anchor errors intact for conflict and validation UI", async () => {
    const errorBody = {
      code: "revision_conflict",
      message: "sync anchor revision conflict",
      current_revision: 4,
      issues: [],
    };
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(errorBody), { status: 409, statusText: "Conflict", headers: { "content-type": "application/json" } }),
    );

    await expect(saveSyncAnchorDraft("take-1", {
      reference_camera: "camera-a",
      cameras: ["camera-a", "camera-b"],
      anchors: [],
      expected_revision: 3,
    })).rejects.toMatchObject({ status: 409, backendDetail: JSON.stringify(errorBody) });
  });

  it("uses the dedicated sync-anchor endpoints and leaves export read-only", async () => {
    const status = {
      capture_take_id: "take-1",
      state: "confirmed",
      analysis_allowed: true,
      reason_codes: [],
      source: "manual_anchors",
      revision: 4,
      provenance: [],
      invalidation_reasons: [],
    };
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(JSON.stringify(status), { status: 200, headers: { "content-type": "application/json" } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ status, calibration: {}, anchors: { reference_camera: "camera-a", cameras: [], anchors: [] } }), { status: 200, headers: { "content-type": "application/json" } }));

    await expect(getSyncAnchorStatus("take-1")).resolves.toMatchObject({ state: "confirmed", revision: 4 });
    await expect(confirmSyncAnchors("take-1", {
      reference_camera: "camera-a",
      cameras: ["camera-a", "camera-b"],
      anchors: [],
      expected_revision: 4,
    })).resolves.toMatchObject({ status: { state: "confirmed" } });
    expect(getSyncAnchorExportUrl("take-1")).toContain("/api/capture-takes/take-1/sync-anchors/export");
    expect(fetchMock.mock.calls[0][0]).toContain("/sync-anchors/status");
    expect(fetchMock.mock.calls[1][1]?.method).toBe("POST");
  });

  it("sends a multiview clip only when the caller enables it", async () => {
    const responseJob = {
      id: "job-multiview",
      status: "queued",
      stage: "queue",
      progress: 10,
      createdAt: "2026-08-03T00:00:00.000Z",
      updatedAt: "2026-08-03T00:00:00.000Z",
      metadata: {
        fileName: "dual.mp4",
        matchTitle: "双摄",
        venue: "测试球场",
        matchDate: "2026-08-03",
        matchFormat: "doubles",
        cameraAngle: "baseline",
        athleteLabel: "Player A",
        level: "MVP",
      },
      stages: [],
    };
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(responseJob), { status: 200, headers: { "content-type": "application/json" } }),
    );
    const metadata = { ...responseJob.metadata, matchFormat: "doubles", cameraAngle: "baseline", level: "MVP" } as const;
    await createMultiviewAnalysisJob({
      metadata,
      referenceViewId: "cam_1",
      clipStartMs: 2000,
      clipEndMs: 4000,
      views: [
        { viewId: "cam_1", videoId: "v1", calibrationId: "c1", courtOrientation: "identity" },
        { viewId: "cam_2", videoId: "v2", calibrationId: "c2", courtOrientation: "rotate_180" },
      ],
    });
    const body = JSON.parse(String(fetchMock.mock.calls[0][1]?.body));
    expect(body.clipStartMs).toBe(2000);
    expect(body.clipEndMs).toBe(4000);
    expect(body.multiview.executionMode).toBe("late_fusion_v1");

    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify(responseJob), { status: 200, headers: { "content-type": "application/json" } }),
    );
    await createMultiviewAnalysisJob({
      metadata,
      referenceViewId: "cam_1",
      views: [
        { viewId: "cam_1", videoId: "v1", calibrationId: "c1", courtOrientation: "identity" },
        { viewId: "cam_2", videoId: "v2", calibrationId: "c2", courtOrientation: "rotate_180" },
      ],
    });
    const bodyWithoutClip = JSON.parse(String(fetchMock.mock.calls[1][1]?.body));
    expect(bodyWithoutClip).not.toHaveProperty("clipStartMs");
    expect(bodyWithoutClip).not.toHaveProperty("clipEndMs");

    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify(responseJob), { status: 200, headers: { "content-type": "application/json" } }),
    );
    await createMultiviewAnalysisJob({
      metadata,
      referenceViewId: "cam_1",
      executionMode: "joint_tracking_v2",
      views: [
        { viewId: "cam_1", cameraId: "hardware-a", videoId: "v1", calibrationId: "c1", courtOrientation: "identity" },
        { viewId: "cam_2", cameraId: "hardware-b", videoId: "v2", calibrationId: "c2", courtOrientation: "rotate_180" },
      ],
    });
    const jointBody = JSON.parse(String(fetchMock.mock.calls[2][1]?.body));
    expect(jointBody.multiview.executionMode).toBe("joint_tracking_v2");
    expect(jointBody.multiview.views[1].cameraId).toBe("hardware-b");
  });
});

describe("deleteRecordingAnalysis", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it("calls the recording-scoped analysis delete endpoint", async () => {
    const results = [
      { job_id: "job-parent", status: "deleted", detail: "ok" },
      { job_id: "job-single", status: "blocked", detail: "active" },
    ];
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(results), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );

    const out = await deleteRecordingAnalysis("sync_1");

    expect(out).toEqual(results);
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("/api/sync-recordings/sync_1/analysis");
    expect(init?.method).toBe("DELETE");
  });

  it("surfaces blocked results without treating them as deleted", async () => {
    const results = [
      { job_id: "job-active", status: "blocked", detail: "analysis in progress" },
    ];
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(results), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );

    const out = await deleteRecordingAnalysis("sync_1");
    expect(out).toHaveLength(1);
    expect(out[0].status).toBe("blocked");
  });
});
