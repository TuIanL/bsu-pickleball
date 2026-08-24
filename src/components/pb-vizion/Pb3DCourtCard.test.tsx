import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ReconstructedBallTrajectoryArtifact } from "../../types/report";
import type { PbReportContextValue } from "../../types/pbReport";
import Pb3DCourtCard from "./Pb3DCourtCard";
import { usePbReport } from "../../contexts/PbReportContext";

vi.mock("../../contexts/PbReportContext", () => ({
  usePbReport: vi.fn(),
}));

vi.mock("../platform/BallTrajectoryScene", () => ({
  BallTrajectoryScene: ({ trajectories }: { trajectories: unknown[] }) => (
    <div data-testid="shared-report-3d" data-trajectory-count={trajectories.length} />
  ),
}));

const artifact: ReconstructedBallTrajectoryArtifact = {
  schema_version: "reconstructed_ball_trajectory.v4",
  job_id: "job-report",
  status: "partial",
  detail: "partial trajectory",
  reconstruction_mode: "hybrid_segmented",
  overall_status: "UNAVAILABLE",
  display_trajectory_status: "degraded",
  events: [],
  segments: [{
    segment_id: "segment-1",
    reconstruction_mode: "single_view_visual_arc",
    status: "available",
    display_level: "medium",
    anchors: [],
    samples: [
      { frame_index: 1, timestamp_sec: 1, court_xy: [8, 10], estimated_height_ft: 2, source: "detected" },
      { frame_index: 2, timestamp_sec: 1.1, court_xy: [9, 12], estimated_height_ft: 1, source: "anchor" },
    ],
  }],
};

describe("Pb3DCourtCard", () => {
  afterEach(() => vi.clearAllMocks());

  it("uses the partial reconstructed artifact in the shared 3D card without SVG diagnostics", () => {
    vi.mocked(usePbReport).mockReturnValue({
      trajectoryArtifact: artifact,
      selectedPlayerId: "Player_1",
      stageFilter: "all",
      qualityThreshold: 0,
      evidence: undefined,
    } as unknown as PbReportContextValue);

    render(<Pb3DCourtCard />);

    expect(screen.getByText("分段球路报告")).toBeTruthy();
    expect(screen.getByText("1 段")).toBeTruthy();
    expect(screen.getByTestId("shared-report-3d").getAttribute("data-trajectory-count")).toBe("1");
    expect(screen.queryByText(/2\.5D|可能界外落点|环境离群/)).toBeNull();
    expect(document.querySelector("svg")).toBeNull();
  });
});
