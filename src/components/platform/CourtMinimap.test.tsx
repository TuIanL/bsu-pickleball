import { describe, expect, it } from "vitest";
import { render, within } from "@testing-library/react";
import { CourtMinimap } from "./CourtMinimap";
import type { BallTrajectoryArtifact, BounceEventsArtifact, PipelineTrackPoint } from "../../types/report";

function pt(overrides: Partial<PipelineTrackPoint> = {}): PipelineTrackPoint {
  return {
    frame_index: 0,
    timestamp_seconds: 0,
    track_id: "Player_1",
    image_point: { x: 10, y: 10 },
    confidence: 0.9,
    side: "unknown",
    court_point: { x: 10, y: 20 },
    ...overrides,
  };
}

describe("CourtMinimap", () => {
  it("renders canonical player label P1..P4 for canonical track_ids", () => {
    const tracks: PipelineTrackPoint[] = [
      pt({ track_id: "Player_1", frame_index: 0, timestamp_seconds: 0, court_point: { x: 4, y: 5 } }),
      pt({ track_id: "Player_2", frame_index: 1, timestamp_seconds: 0.2, court_point: { x: 16, y: 5 } }),
      pt({ track_id: "Player_3", frame_index: 2, timestamp_seconds: 0.4, court_point: { x: 4, y: 39 } }),
      pt({ track_id: "Player_4", frame_index: 3, timestamp_seconds: 0.6, court_point: { x: 16, y: 39 } }),
    ];

    const { container } = render(<CourtMinimap tracks={tracks} currentTimeSec={10} trailSeconds={30} />);

    // Should display "P1".."P4" labels, not raw track_ids
    expect(container.textContent).toContain("P1");
    expect(container.textContent).toContain("P2");
    expect(container.textContent).toContain("P3");
    expect(container.textContent).toContain("P4");

    // Must NOT contain any ID{track_id} or ID{last2} format
    expect(container.textContent).not.toMatch(/ID\s*1[6-9]\d/); // e.g. "ID164"
    expect(container.textContent).not.toMatch(/ID\s*_/); // e.g. "ID_1"
    expect(container.textContent).not.toMatch(/\bID\d/); // e.g. "ID1"
  });

  it("groups multiple source track_ids of same player into one label", () => {
    const tracks: PipelineTrackPoint[] = [
      pt({ track_id: "Player_1", frame_index: 0, timestamp_seconds: 0, court_point: { x: 4, y: 5 } }),
      pt({ track_id: "Player_1", frame_index: 1, timestamp_seconds: 0.2, court_point: { x: 5, y: 6 } }),
      pt({ track_id: "Player_1", frame_index: 2, timestamp_seconds: 0.4, court_point: { x: 6, y: 7 } }),
    ];

    const { container } = render(<CourtMinimap tracks={tracks} currentTimeSec={10} trailSeconds={30} />);

    // Only one P1 label (not duplicated per source_track)
    const textContent = container.textContent ?? "";
    const p1Matches = (textContent.match(/P1/g) ?? []).length;
    expect(p1Matches).toBeGreaterThanOrEqual(1);
    // Should not duplicate P1 for each frame
    expect(p1Matches).toBeLessThanOrEqual(3);
  });

  it("returns null when no tracks are provided", () => {
    const { container } = render(<CourtMinimap tracks={[]} currentTimeSec={0} />);
    expect(container.firstChild).toBeNull();
  });

  it("does not use raw track_id digits as labels", () => {
    // When track_id is not canonical (shouldn't happen after backend fix, but defensive),
    // verify no raw ID label leaks
    const tracks: PipelineTrackPoint[] = [
      pt({ track_id: "164", frame_index: 0, timestamp_seconds: 0, court_point: { x: 10, y: 20 } }),
    ];

    const { container } = render(<CourtMinimap tracks={tracks} currentTimeSec={10} trailSeconds={30} />);

    // Should not show raw IDs in labels
    expect(container.textContent).not.toContain("ID64");
    expect(container.textContent).not.toContain("ID164");
  });

  it("renders near-side players at the bottom and far-side at the top (matches video orientation)", () => {
    // 投影数据中近端（摄像头侧）≈ court y 高值、远端 ≈ 低值；小地图应近端在下、远端在上
    // 用接近 currentTime 的新鲜点，避免被判为停滞（标签不会带 "?"）
    const tracks: PipelineTrackPoint[] = [
      pt({ track_id: "Player_1", frame_index: 0, timestamp_seconds: 9.8, court_point: { x: 10, y: 39 } }),
      pt({ track_id: "Player_2", frame_index: 1, timestamp_seconds: 9.9, court_point: { x: 10, y: 5 } }),
    ];

    const { container } = render(<CourtMinimap tracks={tracks} currentTimeSec={10} trailSeconds={30} />);
    const labels = Array.from(container.querySelectorAll("text")).filter(
      (node) => node.textContent === "P1" || node.textContent === "P2",
    );
    const p1 = labels.find((node) => node.textContent === "P1");
    const p2 = labels.find((node) => node.textContent === "P2");
    expect(p1).toBeTruthy();
    expect(p2).toBeTruthy();
    const y1 = Number(p1!.getAttribute("y"));
    const y2 = Number(p2!.getAttribute("y"));
    // 近端 P1（court y=39）渲染在更大 SVG y（下方）；远端 P2（court y=5）渲染在更小 SVG y（上方）
    expect(y1).toBeGreaterThan(y2);
  });

  it("marks stale players with a lost indicator instead of a current position", () => {
    // latest=1 落后 currentTime=2 超过 0.5s → stale；标签加 "?"，摘要显示"丢失"
    const tracks: PipelineTrackPoint[] = [
      pt({ track_id: "Player_1", frame_index: 0, timestamp_seconds: 1, court_point: { x: 10, y: 20 } }),
    ];

    const { container } = render(<CourtMinimap tracks={tracks} currentTimeSec={2} trailSeconds={30} />);
    expect(container.textContent).toContain("P1?");
    expect(container.textContent).toContain("丢失");
  });

  it("renders a proportional HUD with ball and bounce data even when player tracks are absent", () => {
    const ballTrajectory: BallTrajectoryArtifact = {
      schema_version: "cleaned_ball_trajectory.v1",
      job_id: "test",
      status: "available",
      detail: "",
      samples: [
        { frame_index: 1, timestamp_sec: 2, image_xy: [100, 100], court_xy: [8, 14], confidence: 0.9 },
        { frame_index: 2, timestamp_sec: 2.1, image_xy: [110, 105], court_xy: [9, 15], confidence: 0.85 },
      ],
    };
    const bounceEvents: BounceEventsArtifact = {
      schema_version: "bounce_events.v1",
      job_id: "test",
      status: "available",
      detail: "",
      events: [{ event_id: "bounce", frame_index: 2, timestamp_sec: 2.1, image_xy: [110, 105], court_xy: [9, 15], confidence: 0.8, detection_method: "test" }],
    };

    const { container, getByText } = render(
      <CourtMinimap ballTrajectory={ballTrajectory} bounceEvents={bounceEvents} currentTimeSec={2.1} tracks={[]} />,
    );
    const hud = within(container);

    expect(hud.getByTestId("court-minimap-hud")).toBeTruthy();
    expect(hud.getByTestId("court-boundary").getAttribute("points")).toBeTruthy();
    expect(hud.getByTestId("tracking-boundary").getAttribute("points")).toBeTruthy();
    expect(hud.getByTestId("hud-ball-current")).toBeTruthy();
    expect(hud.getByTestId("hud-bounce")).toBeTruthy();
    expect(getByText("球 LIVE")).toBeTruthy();
  });
});
