import { describe, expect, it } from "vitest";
import { fireEvent, render, within } from "@testing-library/react";
import { VideoAnalysisCard } from "./VideoAnalysisCard";
import type {
  BallTrajectoryArtifact,
  BounceEventsArtifact,
  MatchSummary,
  PipelineTrackPoint,
  PlayerMarker,
  TimelineMarker,
  TrackingOverlayArtifact,
  VideoOverlayLabel,
} from "../../types/report";

const match: MatchSummary = {
  title: "Test Match",
  subtitle: "",
  date: "2026",
  venue: "Court",
  teams: "A vs B",
  score: "0-0",
  currentRally: "",
  currentTime: "0:00",
  duration: "",
};

const emptyPlayers: PlayerMarker[] = [];
const emptyTimeline: TimelineMarker[] = [];
const emptyLabels: VideoOverlayLabel[] = [];

function makeTrackOverlay(
  detections: Array<{ player_id?: string; track_id?: string; confidence?: number }>
): TrackingOverlayArtifact {
  return {
    job_id: "test",
    status: "available",
    detail: "",
    source: { width: 1920, height: 1080 },
    fps: 30,
    frame_count: 1,
    processed_frame_count: 1,
    frame_stride: 1,
    frames: [
      {
        frame_index: 0,
        timestamp_seconds: 0,
        detections: detections.map((d, i) => ({
          frame_index: 0,
          timestamp_seconds: 0,
          bbox: [i * 100, i * 100, (i + 1) * 100, (i + 1) * 100],
          confidence: d.confidence ?? 0.9,
          class_name: "person" as const,
          track_id: d.track_id ?? `${i + 1}`,
          player_id: d.player_id,
          source_width: 1920,
          source_height: 1080,
        })),
      },
    ],
  };
}

describe("VideoAnalysisCard detection labels", () => {
  it("renders canonical P1..P4 for detections with player_id", () => {
    const overlay = makeTrackOverlay([
      { player_id: "Player_1" },
      { player_id: "Player_3" },
    ]);

    const { container } = render(
      <VideoAnalysisCard
        labels={emptyLabels}
        match={match}
        players={emptyPlayers}
        timeline={emptyTimeline}
        trackingOverlay={overlay}
        trackingOverlayLoadState="available"
        videoSrc="/test.mp4"
      />
    );

    expect(container.textContent).toContain("P1");
    expect(container.textContent).toContain("P3");
    // 不应泄漏原始 track_id 数字作为标签
    expect(container.textContent).not.toMatch(/\bID\s*[12]\b/);
  });

  it("shows 'person' for detections without player_id (pre-lock frames)", () => {
    const overlay = makeTrackOverlay([
      { track_id: "1", player_id: undefined },
    ]);

    const { container } = render(
      <VideoAnalysisCard
        labels={emptyLabels}
        match={match}
        players={emptyPlayers}
        timeline={emptyTimeline}
        trackingOverlay={overlay}
        trackingOverlayLoadState="available"
        videoSrc="/test.mp4"
      />
    );

    // 未锁定的检测显示 "person"，不显示原始 track_id
    expect(container.textContent).toContain("person");
    expect(container.textContent).not.toContain("ID 1");
  });

  it("does not leak raw track_id into labels", () => {
    // When player_id is canonical (Player_2), label must be P2 not ID 2 or track_id
    const overlay = makeTrackOverlay([
      { player_id: "Player_2", track_id: "164" },
    ]);

    const { container } = render(
      <VideoAnalysisCard
        labels={emptyLabels}
        match={match}
        players={emptyPlayers}
        timeline={emptyTimeline}
        trackingOverlay={overlay}
        trackingOverlayLoadState="available"
        videoSrc="/test.mp4"
      />
    );

    expect(container.textContent).toContain("P2");
    expect(container.textContent).not.toContain("164");
    expect(container.textContent).not.toContain("ID 164");
    expect(container.textContent).not.toContain("ID164");
  });

  it("keeps ball point, ball path, and bounce candidates as independent real-data layers", () => {
    const ballTrajectory: BallTrajectoryArtifact = {
      schema_version: "cleaned_ball_trajectory.v1",
      job_id: "test",
      status: "available",
      detail: "",
      samples: [
        { frame_index: 1, timestamp_sec: -0.1, image_xy: [100, 100], court_xy: [8, 14], confidence: 0.9 },
        { frame_index: 2, timestamp_sec: 0, image_xy: [140, 120], court_xy: [9, 15], confidence: 0.8, interpolated: true },
      ],
    };
    const bounceEvents: BounceEventsArtifact = {
      schema_version: "bounce_events.v1",
      job_id: "test",
      status: "available",
      detail: "",
      events: [{ event_id: "bounce", frame_index: 1, timestamp_sec: 0, image_xy: [100, 100], court_xy: [8, 14], confidence: 0.8, detection_method: "test" }],
    };
    const { container } = render(
      <VideoAnalysisCard
        ballTrajectory={ballTrajectory}
        ballTrajectoryLoadState="available"
        bounceEvents={bounceEvents}
        bounceEventsLoadState="available"
        labels={emptyLabels}
        match={match}
        players={emptyPlayers}
        timeline={emptyTimeline}
        videoSrc="/test.mp4"
      />,
    );
    const card = within(container);

    expect(card.getByTestId("video-ball-current")).toBeTruthy();
    expect(card.getByTestId("video-ball-segment")).toBeTruthy();
    expect(card.getByTestId("video-bounce")).toBeTruthy();

    fireEvent.click(card.getByLabelText("隐藏球路"));
    expect(card.getByLabelText("显示球路").getAttribute("aria-pressed")).toBe("false");
    expect(card.queryByTestId("video-ball-segment")).toBeNull();
    expect(card.getByTestId("video-ball-current")).toBeTruthy();
    expect(card.getByTestId("video-bounce")).toBeTruthy();
  });

  it("disables ball layers when the real artifact is unavailable", () => {
    const { container } = render(
      <VideoAnalysisCard
        ballTrajectoryLoadState="unavailable"
        bounceEventsLoadState="unavailable"
        labels={emptyLabels}
        match={match}
        players={emptyPlayers}
        timeline={emptyTimeline}
        videoSrc="/test.mp4"
      />,
    );
    const card = within(container);

    expect(card.getByLabelText("隐藏球点").hasAttribute("disabled")).toBe(true);
    expect(card.getByLabelText("隐藏球路").hasAttribute("disabled")).toBe(true);
    expect(card.getByLabelText("隐藏弹跳候选").hasAttribute("disabled")).toBe(true);
  });
});

describe("VideoAnalysisCard court HUD collapse", () => {
  function makeTracks(): PipelineTrackPoint[] {
    return [
      {
        frame_index: 0,
        timestamp_seconds: 0,
        track_id: "Player_1",
        image_point: { x: 100, y: 200 },
        confidence: 0.9,
        side: "near",
        court_point: { x: 10, y: 10 },
      },
    ];
  }

  it("collapses the court HUD by default and expands on demand", () => {
    const { container } = render(
      <VideoAnalysisCard
        labels={emptyLabels}
        match={match}
        players={emptyPlayers}
        pipelineTracks={makeTracks()}
        timeline={emptyTimeline}
        videoSrc="/test.mp4"
      />
    );
    const card = within(container);

    // 默认收起：只显示"球场地图"按钮，不渲染完整 HUD
    expect(card.getByLabelText("展开球场地图")).toBeTruthy();
    expect(card.queryByTestId("court-minimap-hud")).toBeNull();

    // 点击展开后显示完整 HUD，按钮文案/语义切换
    fireEvent.click(card.getByLabelText("展开球场地图"));
    expect(card.queryByTestId("court-minimap-hud")).toBeTruthy();
    expect(card.getByLabelText("收起球场地图")).toBeTruthy();

    // 再次点击收起
    fireEvent.click(card.getByLabelText("收起球场地图"));
    expect(card.queryByTestId("court-minimap-hud")).toBeNull();
  });
});
