import { describe, expect, it } from "vitest";
import type { AnalysisPipelineResult } from "../types/report";
import { getReportCapability } from "./reportCapability";

const completedJob = { status: "completed" as const };

function result(overrides: Partial<AnalysisPipelineResult> = {}): AnalysisPipelineResult {
  return {
    job_id: "job-1",
    status: "completed",
    generated_at: "2026-08-26T00:00:00Z",
    stages: [],
    tracks: [],
    metrics: {
      distances: [],
      speeds: [],
      kitchen_dwell: [],
      doubles_spacing: [],
      heatmap: { rows: 0, cols: 0, cells: [] },
    },
    artifacts: {},
    message: "done",
    ...overrides,
  };
}

describe("getReportCapability", () => {
  it("manifest 读取中保持 loading", () => {
    expect(getReportCapability({ job: completedJob, manifest: null, manifestState: "loading" }).state).toBe("loading");
  });

  it("空、失败或非有限证据不能打开报告", () => {
    const empty = getReportCapability({ job: completedJob, manifest: result(), manifestState: "loaded" });
    expect(empty.state).toBe("unavailable");

    const invalidTrack = getReportCapability({
      job: completedJob,
      manifest: result({ tracks: [{ track_id: "Player_1", court_point: { x: Number.NaN, y: 20 } } as never] }),
      manifestState: "loaded",
    });
    expect(invalidTrack.state).toBe("unavailable");
  });

  it("有效 canonical 轨迹或运动指标均可打开报告", () => {
    const tracks = getReportCapability({
      job: completedJob,
      manifest: result({ tracks: [{ track_id: "Player_1", court_point: { x: 10, y: 20 } } as never] }),
      manifestState: "loaded",
    });
    expect(tracks.state).toBe("available");

    const metrics = getReportCapability({
      job: completedJob,
      manifest: result({
        metrics: {
          distances: [{ track_id: "Player_2", distance_ft: 35 }],
          speeds: [], kitchen_dwell: [], doubles_spacing: [], heatmap: { rows: 0, cols: 0, cells: [] },
        },
      }),
      manifestState: "loaded",
    });
    expect(metrics.state).toBe("available");
  });

  it("available structured visualization artifact 可作为独立报告证据", () => {
    const capability = getReportCapability({
      job: completedJob,
      manifest: result({
        artifacts: {
          structured_visualization_data_path: "/artifacts/job-1/visualization/data.json",
          position_visualizations_status: "available",
        },
      }),
      manifestState: "loaded",
    });
    expect(capability.state).toBe("available");
    expect(capability.evidence.structuredVisualization).toBe(true);
  });
});
