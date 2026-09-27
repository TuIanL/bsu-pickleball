import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  getPlayerBootstrap: vi.fn(),
}));

vi.mock("../../services/analysisClient", () => ({
  getPlayerBootstrap: mocks.getPlayerBootstrap,
  getVideoStreamUrl: (videoId?: string) => (videoId ? `/api/videos/${videoId}/stream` : null),
  resolveAnalysisApiUrl: (path?: string | null) => (path ? `http://localhost:8000${path}` : null),
}));

import { AnalysisRosterConfirmation } from "./AnalysisRosterConfirmation";
import type { RosterConfirmationRequest } from "../../types/rallyContext";

function candidatesV2(count = 4) {
  return Array.from({ length: count }, (_, index) => ({
    candidate_id: `bp_cam_1_${index + 1}_${index + 1}`,
    suggested_slot: index + 1,
    view_id: "cam_1",
    timestamp_ms: (index + 1) * 1000,
    bbox: [(index + 1) * 100, 20, (index + 1) * 100 + 60, 180],
    frame_url: `/api/analysis/players/bootstrap/frame?videoId=v&timestampMs=${(index + 1) * 1000}`,
    crop_url: `/api/analysis/players/bootstrap/frame?videoId=v&timestampMs=${(index + 1) * 1000}&bbox=1,2,3,4`,
    court_xy: [index + 1, index + 2],
    confidence: 0.8,
    score: 0.7,
    source_views: ["cam_1"],
    evidence: {
      target_court_membership: 0.9,
      target_court_occupancy: 0.9,
      mean_target_court_distance_ft: 0.5,
      continuity: 0.8,
      coverage_ratio: 0.6,
      sampled_hits: 6,
      sampled_frames: 10,
      body_crop_quality: 0.7,
      appearance_quality: null,
      appearance_margin: null,
      multiview_agreement: null,
    },
  }));
}

function bootstrapV2(overrides: Record<string, unknown> = {}) {
  return {
    schema_version: "player-bootstrap.v2",
    status: "available",
    owner_key: "take-1",
    capture_take_id: "take-1",
    video_id: "v",
    match_format: "doubles",
    expected_player_count: 4,
    clip_start_ms: 0,
    clip_end_ms: 60_000,
    bootstrap_run_id: "run-1",
    bootstrap_model_version: "yolo11n.pt",
    bootstrap_cache_key: "cache-1",
    views: ["cam_1"],
    multiview_used: false,
    sampled_frame_count: 12,
    reference_frame: {
      view_id: "cam_1",
      timestamp_ms: 1000,
      frame_url: "/api/analysis/players/bootstrap/frame?videoId=v&timestampMs=1000",
      candidate_ids: ["bp_cam_1_1_1"],
      observed_bboxes: { bp_cam_1_1_1: [100, 20, 160, 180] },
    },
    candidates: candidatesV2(),
    diagnostics: [],
    skippable: true,
    consumers_enabled: true,
    ...overrides,
  };
}

function bootstrapV1(overrides: Record<string, unknown> = {}) {
  return {
    schema_version: "player-bootstrap.v1",
    status: "available",
    owner_key: "take-1",
    reference_timestamp_ms: 1000,
    reference_frame_url: "/api/analysis/players/bootstrap/frame?videoId=v&timestampMs=1000",
    skippable: true,
    consumers_enabled: true,
    diagnostics: [],
    candidates: [1, 2, 3, 4].map((index) => ({
      canonical_player_id: `Player_${index}`,
      display_name: `球员${index}`,
      anchor_timestamp_ms: index * 1000,
      anchor_bbox: [index * 100, 20, index * 100 + 60, 180],
      anchor_court_xy: [index, index + 1],
      confidence: 0.8,
    })),
    ...overrides,
  };
}

function makeOnChange() {
  return vi.fn<(request: RosterConfirmationRequest) => void>();
}

type OnChange = ReturnType<typeof makeOnChange>;

function lastRequest(onChange: OnChange): RosterConfirmationRequest {
  return onChange.mock.calls.at(-1)?.[0] as RosterConfirmationRequest;
}

async function renderRoster(onChange: OnChange, matchFormat: "singles" | "doubles" = "doubles") {
  render(
    <AnalysisRosterConfirmation captureTakeId="take-1" videoId="v" matchFormat={matchFormat} onChange={onChange} />,
  );
  const root = await screen.findByTestId("analysis-roster-confirmation");
  await waitFor(() => {
    expect(root.getAttribute("data-roster-status")).not.toBe("loading");
    // 自动候选必须已就位，否则"未识别"与"候选取不到"无法区分，断言会变成竞态。
    expect(root.getAttribute("data-slots-ready")).toBe("true");
  });
  return root;
}

describe("AnalysisRosterConfirmation", () => {
  afterEach(() => cleanup());

  it("默认直接展示四张带 P 编号的卡片，并请求 v2 契约", async () => {
    mocks.getPlayerBootstrap.mockResolvedValue(bootstrapV2());
    const onChange = makeOnChange();
    const root = await renderRoster(onChange);

    expect(mocks.getPlayerBootstrap).toHaveBeenCalledWith(
      expect.objectContaining({ contract: "v2", captureTakeId: "take-1", videoId: "v" }),
    );
    expect(root.getAttribute("data-contract")).toBe("v2");
    for (const playerId of ["Player_1", "Player_2", "Player_3", "Player_4"]) {
      expect(screen.getByTestId(`roster-candidate-${playerId}`)).toBeTruthy();
    }
    // P 标签常显
    for (let index = 0; index < 4; index += 1) {
      expect(screen.getByTestId(`roster-slot-label-${index}`).textContent).toBe(`P${index + 1}`);
    }
    // 默认不推断 Team A/B
    for (const playerId of ["Player_1", "Player_2", "Player_3", "Player_4"]) {
      expect(screen.getByTestId(`roster-candidate-${playerId}`).getAttribute("data-team-assignment")).toBe(
        "unassigned",
      );
    }
    // 手工选帧入口默认不展开（自动候选完整）
    expect(screen.queryByTestId("roster-manual-picker")).toBeNull();
    expect(lastRequest(onChange).entries).toEqual([]);
  });

  it("每张卡片显示真实的来源机位与时间", async () => {
    mocks.getPlayerBootstrap.mockResolvedValue(bootstrapV2());
    const onChange = makeOnChange();
    await renderRoster(onChange);

    expect(screen.getByTestId("roster-candidate-source-0").textContent).toContain("A 机位");
    expect(screen.getByTestId("roster-candidate-source-0").textContent).toContain("1000ms");
    expect(screen.getByTestId("roster-candidate-source-3").textContent).toContain("4000ms");
  });

  it("主参考画面只叠加该帧实际观测到的候选框", async () => {
    mocks.getPlayerBootstrap.mockResolvedValue(bootstrapV2());
    const onChange = makeOnChange();
    await renderRoster(onChange);

    const image = screen.getByAltText("主参考画面（1000ms）");
    Object.defineProperty(image, "naturalWidth", { configurable: true, value: 1920 });
    Object.defineProperty(image, "naturalHeight", { configurable: true, value: 1080 });
    fireEvent.load(image);

    const overlay = await screen.findByTestId("roster-reference-overlay");
    expect(overlay.getAttribute("viewBox")).toBe("0 0 1920 1080");
    // 参考帧只观测到 P1；其余槽位的时间不同，不得把它们的框画在这一帧上
    expect(screen.getByTestId("roster-anchor-slot-0").textContent).toContain("P1");
    expect(screen.queryByTestId("roster-anchor-slot-1")).toBeNull();
  });

  it("人工确认队伍与端位后回抛冻结名册（含 candidate_id 与锚点）", async () => {
    mocks.getPlayerBootstrap.mockResolvedValue(bootstrapV2());
    const onChange = makeOnChange();
    await renderRoster(onChange);
    fireEvent.click(screen.getByTestId("roster-team-0-A"));
    fireEvent.click(screen.getByTestId("roster-team-1-A"));
    fireEvent.click(screen.getByTestId("roster-team-2-B"));
    fireEvent.click(screen.getByTestId("roster-team-3-B"));
    fireEvent.click(screen.getByTestId("court-end-end_a"));

    await waitFor(() => {
      const request = lastRequest(onChange);
      expect(request.skipped).toBe(false);
      expect(request.initial_team_a_end).toBe("end_a");
      expect(request.entries).toHaveLength(4);
      expect(request.entries.map((entry) => entry.team_id)).toEqual(["A", "A", "B", "B"]);
      expect(request.entries.map((entry) => entry.canonical_player_id)).toEqual([
        "Player_1",
        "Player_2",
        "Player_3",
        "Player_4",
      ]);
      expect(request.entries[0].candidate_id).toBe("bp_cam_1_1_1");
      expect(request.entries[0].slot_index).toBe(0);
      expect(request.entries[0].source_view_id).toBe("cam_1");
      expect(request.entries[0].anchor_timestamp_ms).toBe(1000);
      expect(request.entries[0].anchor_court_xy).toEqual([1, 2]);
      expect(request.bootstrap_run_id).toBe("run-1");
      expect(request.bootstrap_model_version).toBe("yolo11n.pt");
    });

    expect(screen.getByTestId("roster-ready").textContent).toContain("4 名球员");
    // 本阶段不提供姓名录入：提交数据里名字保持为空
    expect(lastRequest(onChange).entries.every((entry) => entry.display_name == null)).toBe(true);
  });

  it("交换候选后同一候选不会重复占槽", async () => {
    mocks.getPlayerBootstrap.mockResolvedValue(bootstrapV2());
    const onChange = makeOnChange();
    await renderRoster(onChange);
    // 先释放 P2 的候选，才能把它明确选给 P1
    fireEvent.change(screen.getByTestId("roster-player-select-1"), { target: { value: "" } });
    fireEvent.change(screen.getByTestId("roster-player-select-0"), {
      target: { value: "bp_cam_1_2_2" },
    });
    fireEvent.click(screen.getByTestId("roster-team-0-A"));

    await waitFor(() => {
      const request = lastRequest(onChange);
      expect(request.entries[0].candidate_id).toBe("bp_cam_1_2_2");
      expect(request.entries[0].anchor_timestamp_ms).toBe(2000);
    });
    expect((screen.getByTestId("roster-player-select-1") as HTMLSelectElement).value).toBe("");
    expect(
      screen.getByTestId("roster-player-select-1").querySelector('option[value="bp_cam_1_2_2"]'),
    ).toHaveProperty("disabled", true);
  });

  it("替换已占用槽位的候选会释放原槽位", async () => {
    mocks.getPlayerBootstrap.mockResolvedValue(bootstrapV2());
    const onChange = makeOnChange();
    await renderRoster(onChange);
    // 把 P1 的候选指派给 P2（占用 P1 的候选）
    fireEvent.change(screen.getByTestId("roster-player-select-1"), {
      target: { value: "bp_cam_1_1_1" },
    });

    await waitFor(() => {
      expect((screen.getByTestId("roster-player-select-0") as HTMLSelectElement).value).toBe("");
      expect((screen.getByTestId("roster-player-select-1") as HTMLSelectElement).value).toBe(
        "bp_cam_1_1_1",
      );
    });
    // P1 被"抢走"候选后回到未识别：不会有两个槽位指向同一个候选
    const submitted = lastRequest(onChange).entries;
    expect(submitted.every((entry) => entry.candidate_id !== "bp_cam_1_1_1")).toBe(true);
    expect(submitted.some((entry) => entry.canonical_player_id === "Player_1")).toBe(false);
  });

  it("候选不足时保留可靠的人，并自动展开手工补全入口", async () => {
    mocks.getPlayerBootstrap.mockResolvedValue(
      bootstrapV2({
        status: "insufficient_candidates",
        unavailable_reason: "bootstrap_preflight_insufficient_candidates",
        candidates: candidatesV2(1),
        reference_frame: {
          view_id: "cam_1",
          timestamp_ms: 1000,
          frame_url: "/api/analysis/players/bootstrap/frame?videoId=v&timestampMs=1000",
          candidate_ids: ["bp_cam_1_1_1"],
          observed_bboxes: { bp_cam_1_1_1: [100, 20, 160, 180] },
        },
        diagnostics: [
          { code: "bootstrap_preflight_insufficient_candidates", detail: "仅得到 1 名可靠候选", severity: "warning" },
        ],
      }),
    );
    const onChange = makeOnChange();
    const root = await renderRoster(onChange);

    expect(root.getAttribute("data-roster-status")).toBe("insufficient_candidates");
    expect(screen.getByTestId("roster-diagnostic").textContent).toContain("自动候选不足");
    expect(screen.getByTestId("roster-quality-diagnostics").textContent).toContain(
      "bootstrap_preflight_insufficient_candidates",
    );
    // 手工入口自动展开
    expect(screen.getByTestId("roster-manual-picker")).toBeTruthy();
    // 未识别的槽位仍然渲染 P 标签，且没有伪造的人物画面
    expect(screen.getByTestId("roster-slot-label-2").textContent).toBe("P3");
    expect(screen.getByTestId("roster-candidate-Player_3").getAttribute("data-candidate-id")).toBe("none");
    expect(screen.getByTestId("roster-candidate-Player_3").getAttribute("data-has-anchor")).toBe("false");
    expect(screen.queryByTestId("roster-ready")).toBeNull();
    expect(screen.getByTestId("roster-incomplete").textContent).toContain("尚未完整");
  });

  it("无可用候选时显式 unavailable，单打只渲染两个槽位", async () => {
    mocks.getPlayerBootstrap.mockResolvedValue(
      bootstrapV2({
        status: "unavailable",
        unavailable_reason: "bootstrap_preflight_no_detections",
        candidates: [],
        reference_frame: null,
        diagnostics: [
          { code: "bootstrap_preflight_no_detections", detail: "采样窗口内没有稳定的人体候选", severity: "warning" },
        ],
      }),
    );
    const onChange = makeOnChange();
    const root = await renderRoster(onChange, "singles");

    expect(root.getAttribute("data-roster-status")).toBe("unavailable");
    expect(screen.getByTestId("roster-candidate-Player_1")).toBeTruthy();
    expect(screen.getByTestId("roster-candidate-Player_2")).toBeTruthy();
    expect(screen.queryByTestId("roster-candidate-Player_3")).toBeNull();
    expect(screen.getByTestId("roster-no-reference-frame")).toBeTruthy();
  });

  it("显式跳过：回抛 skipped 请求且不提供姓名输入", async () => {
    mocks.getPlayerBootstrap.mockResolvedValue(bootstrapV2());
    const onChange = makeOnChange();
    await renderRoster(onChange);

    expect(document.querySelectorAll('input[type="text"]')).toHaveLength(0);
    fireEvent.click(screen.getByTestId("roster-skip-toggle"));

    await waitFor(() => {
      const request = lastRequest(onChange);
      expect(request.skipped).toBe(true);
      expect(request.entries).toEqual([]);
      expect(request.initial_team_a_end).toBeNull();
    });
    expect(screen.getByTestId("roster-skipped-note").textContent).toContain("不会推断 Team A/B");
  });

  it("feature gate 关闭时降级为仅提示，且只提交跳过", async () => {
    mocks.getPlayerBootstrap.mockResolvedValue(bootstrapV2({ consumers_enabled: false }));
    const onChange = makeOnChange();
    const root = await renderRoster(onChange);

    expect(root.getAttribute("data-consumers-enabled")).toBe("false");
    expect(screen.getByTestId("roster-consumers-disabled").textContent).toContain("未启用分析回合上下文消费");
    expect(root.getAttribute("data-skipped")).toBe("true");
    await waitFor(() => {
      const request = lastRequest(onChange);
      expect(request.skipped).toBe(true);
      expect(request.entries).toEqual([]);
    });
    expect(screen.queryByTestId("roster-team-0-A")).toBeNull();
  });

  it("旧版 v1 响应仍可降级渲染", async () => {
    mocks.getPlayerBootstrap.mockResolvedValue(bootstrapV1());
    const onChange = makeOnChange();
    const root = await renderRoster(onChange);

    expect(root.getAttribute("data-contract")).toBe("v1");
    expect(screen.getByTestId("roster-candidate-Player_4")).toBeTruthy();
    fireEvent.click(screen.getByTestId("roster-team-0-A"));
    await waitFor(() => expect(lastRequest(onChange).entries[0].candidate_id).toBe("Player_1"));
    // v1 没有 candidate_id 语义：槽位仍按 P 编号提交，且锚点来自旧字段
    expect(lastRequest(onChange).entries[0].anchor_timestamp_ms).toBe(1000);
  });

  it("预检请求失败不阻断页面，用户仍可继续或跳过", async () => {
    mocks.getPlayerBootstrap.mockRejectedValue(new Error("network down"));
    const onChange = makeOnChange();
    render(<AnalysisRosterConfirmation captureTakeId="take-1" videoId="v" onChange={onChange} />);

    await screen.findByTestId("roster-load-error");
    expect(screen.getByTestId("roster-load-error").textContent).toContain("network down");
    await waitFor(() => expect(lastRequest(onChange).entries).toEqual([]));

    fireEvent.click(screen.getByTestId("roster-skip-toggle"));
    await waitFor(() => expect(lastRequest(onChange).skipped).toBe(true));
  });

  it("把所选片段与双摄视频传给预检", async () => {
    mocks.getPlayerBootstrap.mockResolvedValue(bootstrapV2());
    const onChange = makeOnChange();
    render(
      <AnalysisRosterConfirmation
        captureTakeId="take-1"
        videoId="vA"
        videoIdB="vB"
        matchFormat="doubles"
        clipStartMs={1500}
        clipEndMs={9500}
        onChange={onChange}
      />,
    );
    await screen.findByTestId("analysis-roster-confirmation");
    expect(mocks.getPlayerBootstrap).toHaveBeenCalledWith(
      expect.objectContaining({ videoIdB: "vB", clipStartMs: 1500, clipEndMs: 9500 }),
    );
  });
});
