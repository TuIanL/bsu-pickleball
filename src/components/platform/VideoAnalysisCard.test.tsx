import { describe, expect, it } from "vitest";
import { fireEvent, render, within } from "@testing-library/react";
import { useState } from "react";
import { VideoAnalysisCard } from "./VideoAnalysisCard";
import { resolvePlayerIdentityHue } from "../../utils/overlayPresentation";
import type {
  BallTrajectoryArtifact,
  BounceEventsArtifact,
  MatchSummary,
  PipelineTrackPoint,
  PlayerMarker,
  TimelineMarker,
  TrackingOverlayArtifact,
  VideoOverlayLabel,
  FusedPlayerOverlayArtifact,
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
    expect(container.querySelector(`rect[stroke='${resolvePlayerIdentityHue("Player_1")}']`)).toBeTruthy();
    expect(container.querySelector(`rect[stroke='${resolvePlayerIdentityHue("Player_3")}']`)).toBeTruthy();
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

    expect(card.getByLabelText("球点不可用").hasAttribute("disabled")).toBe(true);
    expect(card.getByLabelText("球路不可用").hasAttribute("disabled")).toBe(true);
    expect(card.getByLabelText("弹跳候选不可用").hasAttribute("disabled")).toBe(true);
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

describe("VideoAnalysisCard multiview display", () => {
  function makeDualViewOverlay(): FusedPlayerOverlayArtifact {
    const frame = (x: number, courtX: number) => ({
      frame_index: 0,
      timestamp_seconds: 0,
      players: [{
        player_id: "Player_1",
        label: "P1",
        bbox: [x, 100, x + 80, 300],
        footpoint: [x + 40, 300],
        evidence_type: "base_observed" as const,
        source_confidence: 0.9,
        overlay_confidence: 0.9,
        canonical_court_position_ft: [courtX, 10],
      }],
    });
    return {
      schema_version: "multiview-fused-player-overlay.v2",
      job_id: "job-dual",
      reference_view_id: "cam_1",
      status: "available",
      detail: "",
      frame_count: 1,
      processed_frame_count: 1,
      source: { width: 1920, height: 1080 },
      frames: [frame(100, 4)],
      views: {
        cam_1: { view_id: "cam_1", status: "available", detail: "", source: { width: 1920, height: 1080 }, frames: [frame(100, 4)] },
        cam_2: { view_id: "cam_2", status: "available", detail: "", source: { width: 1920, height: 1080 }, frames: [frame(900, 16)] },
      },
    };
  }

  it("switches Player overlay and minimap together to the selected view", () => {
    function Harness() {
      const [view, setView] = useState("cam_1");
      return (
        <VideoAnalysisCard
          displayViewId={view}
          displayViewOptions={[
            { id: "cam_1", label: "A 机位", available: true },
            { id: "cam_2", label: "B 机位", available: true },
          ]}
          fusedPlayerOverlay={makeDualViewOverlay()}
          fusedPlayerOverlayLoadState="available"
          labels={emptyLabels}
          match={match}
          onDisplayViewChange={setView}
          players={emptyPlayers}
          timeline={emptyTimeline}
          videoSrc="/test.mp4"
        />
      );
    }

    const { container } = render(<Harness />);
    const card = within(container);
    expect(card.getByTestId("fused-player-Player_1").querySelector("rect")?.getAttribute("x")).toBe("100");
    fireEvent.click(card.getByLabelText("展开球场地图"));
    const aHudX = card.getByTestId("hud-player-1").querySelector("circle")?.getAttribute("cx");
    fireEvent.click(card.getByRole("button", { name: "B 机位" }));
    expect(card.getByTestId("fused-player-Player_1").querySelector("rect")?.getAttribute("x")).toBe("900");
    const bHudX = card.getByTestId("hud-player-1").querySelector("circle")?.getAttribute("cx");
    expect(aHudX).not.toBeNull();
    expect(bHudX).not.toBe(aHudX);
  });

  it("keeps canonical Player identity through an A→B→A round trip", () => {
    function Harness() {
      const [view, setView] = useState("cam_1");
      return (
        <VideoAnalysisCard
          displayViewId={view}
          displayViewOptions={[
            { id: "cam_1", label: "A 机位", available: true },
            { id: "cam_2", label: "B 机位", available: true },
          ]}
          fusedPlayerOverlay={makeDualViewOverlay()}
          fusedPlayerOverlayLoadState="available"
          labels={emptyLabels}
          match={match}
          onDisplayViewChange={setView}
          players={emptyPlayers}
          timeline={emptyTimeline}
          videoSrc="/test.mp4"
        />
      );
    }

    const { container } = render(<Harness />);
    const card = within(container);
    const player = () => card.getByTestId("fused-player-Player_1").querySelector("rect")?.getAttribute("x");

    expect(player()).toBe("100");
    fireEvent.click(card.getByRole("button", { name: "B 机位" }));
    expect(player()).toBe("900");
    fireEvent.click(card.getByRole("button", { name: "A 机位" }));
    expect(player()).toBe("100");
    expect(card.getByText("P1")).toBeTruthy();
  });

  it("keeps a missing target-view bbox hidden without borrowing another Player's box", () => {
    const artifact = makeDualViewOverlay();
    const targetView = artifact.views?.cam_2;
    if (!targetView) {
      throw new Error("Expected dual-view fixture to include cam_2");
    }
    const sourcePlayer = targetView.frames[0].players[0];
    targetView.frames[0].players = [
      { ...sourcePlayer, bbox: null, footpoint: null, evidence_type: "cross_view_projected" },
      { ...sourcePlayer, player_id: "Player_2", label: "P2", bbox: [1200, 100, 1280, 300], footpoint: [1240, 300] },
    ];

    const { container } = render(
      <VideoAnalysisCard
        displayViewId="cam_2"
        displayViewOptions={[{ id: "cam_2", label: "B 机位", available: true }]}
        fusedPlayerOverlay={artifact}
        fusedPlayerOverlayLoadState="available"
        labels={emptyLabels}
        match={match}
        players={emptyPlayers}
        timeline={emptyTimeline}
        videoSrc="/test.mp4"
      />,
    );
    const card = within(container);

    expect(card.queryByTestId("fused-player-Player_1")).toBeNull();
    expect(card.getByTestId("fused-player-Player_2")).toBeTruthy();
    expect(card.getByText("P2")).toBeTruthy();
  });

});
