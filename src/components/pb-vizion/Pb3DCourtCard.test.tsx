import { cleanup, render, screen } from "@testing-library/react";
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
    <div
      data-testid="shared-report-3d"
      data-trajectory-count={trajectories.length}
      data-trajectory-ids={(trajectories as Array<{ id: string }>).map((trajectory) => trajectory.id).join(",")}
      data-hitters={(trajectories as Array<{ hitterPlayerId: string | null }>).map((trajectory) => trajectory.hitterPlayerId).join(",")}
    />
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
  segments: [
    {
      segment_id: "segment-p1-a",
      reconstruction_mode: "single_view_visual_arc",
      status: "available",
      display_level: "medium",
      shot_id: "shot-p1",
      hitter_player_id: "Player_1",
      ownership_status: "confirmed",
      anchors: [],
      samples: [
        { frame_index: 1, timestamp_sec: 1, court_xy: [8, 10], estimated_height_ft: 2, source: "detected" },
        { frame_index: 2, timestamp_sec: 1.1, court_xy: [9, 12], estimated_height_ft: 1, source: "anchor" },
      ],
    },
    {
      segment_id: "segment-p1-b",
      reconstruction_mode: "single_view_visual_arc",
      status: "available",
      display_level: "medium",
      shot_id: "shot-p1",
      hitter_player_id: "Player_1",
      ownership_status: "confirmed",
      anchors: [],
      samples: [
        { frame_index: 3, timestamp_sec: 1.2, court_xy: [9, 12], estimated_height_ft: 1, source: "detected" },
        { frame_index: 4, timestamp_sec: 1.3, court_xy: [10, 14], estimated_height_ft: 0, source: "anchor" },
      ],
    },
    {
      segment_id: "segment-p2",
      reconstruction_mode: "single_view_visual_arc",
      status: "available",
      display_level: "medium",
      shot_id: "shot-p2",
      hitter_player_id: "Player_2",
      ownership_status: "confirmed",
      anchors: [],
      samples: [
        { frame_index: 5, timestamp_sec: 2, court_xy: [10, 14], estimated_height_ft: 2, source: "detected" },
        { frame_index: 6, timestamp_sec: 2.1, court_xy: [11, 16], estimated_height_ft: 0, source: "anchor" },
      ],
    },
    {
      segment_id: "segment-unknown",
      reconstruction_mode: "single_view_visual_arc",
      status: "available",
      display_level: "medium",
      shot_id: "shot-unknown",
      hitter_player_id: null,
      ownership_status: "unassigned",
      anchors: [],
      samples: [
        { frame_index: 7, timestamp_sec: 3, court_xy: [11, 16], estimated_height_ft: 2, source: "detected" },
        { frame_index: 8, timestamp_sec: 3.1, court_xy: [12, 18], estimated_height_ft: 0, source: "anchor" },
      ],
    },
  ],
};

describe("Pb3DCourtCard", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  function mockReportContext(selectedPlayerId: string) {
    vi.mocked(usePbReport).mockReturnValue({
      trajectoryArtifact: artifact,
      selectedPlayerId,
      stageFilter: "all",
      qualityThreshold: 0,
      evidence: undefined,
    } as unknown as PbReportContextValue);
  }

  it("uses only the selected player's confirmed Shot segments in the shared 3D card", () => {
    mockReportContext("Player_1");

    render(<Pb3DCourtCard />);

    expect(screen.getByText("分段球路报告")).toBeTruthy();
    expect(screen.getByText("2 段")).toBeTruthy();
    expect(screen.getByTestId("shared-report-3d").getAttribute("data-trajectory-count")).toBe("2");
    expect(screen.getByTestId("shared-report-3d").getAttribute("data-trajectory-ids")).toBe("segment-p1-a,segment-p1-b");
    expect(screen.getByTestId("shared-report-3d").getAttribute("data-hitters")).toBe("Player_1,Player_1");
    expect(screen.queryByText(/2\.5D|可能界外落点|环境离群/)).toBeNull();
    expect(document.querySelector("svg")).toBeNull();
  });

  it("切换球员后不残留上一名球员的轨迹", () => {
    mockReportContext("Player_1");
    const view = render(<Pb3DCourtCard />);

    mockReportContext("Player_2");
    view.rerender(<Pb3DCourtCard />);

    expect(screen.getByText("1 段")).toBeTruthy();
    expect(screen.getByTestId("shared-report-3d").getAttribute("data-trajectory-ids")).toBe("segment-p2");
    expect(screen.getByTestId("shared-report-3d").getAttribute("data-hitters")).toBe("Player_2");
  });

  it("没有匹配球路时显示空态，不回退显示整场球路", () => {
    mockReportContext("Player_4");

    render(<Pb3DCourtCard />);

    expect(screen.getByText("当前筛选下没有可显示的球路")).toBeTruthy();
    expect(screen.queryByTestId("shared-report-3d")).toBeNull();
  });
});
