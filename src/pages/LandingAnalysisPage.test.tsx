import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { LandingAnalysisPage } from "./LandingAnalysisPage";
import { getAnalysisResult, getShotLandings } from "../services/analysisClient";

vi.mock("../services/analysisClient", () => ({ getAnalysisResult: vi.fn(), getShotLandings: vi.fn() }));
afterEach(() => { cleanup(); vi.clearAllMocks(); });

const result = { job_id: "job-1", status: "completed", metrics: {}, artifacts: { shot_landings_url: "/landing" } } as never;

describe("LandingAnalysisPage embedded states", () => {
  it("renders successful content without a legacy page shell", async () => {
    vi.mocked(getAnalysisResult).mockResolvedValue(result);
    vi.mocked(getShotLandings).mockResolvedValue({
      schema_version: "shot-landings.v1", job_id: "job-1", status: "available", detail: "ok", generated_at: "2026-09-21T00:00:00Z",
      normalization_profile: { profile_id: "landing-orientation.v1", parameters: {} }, zone_profiles: {},
      summary: { shot_count: 1, available_landing_count: 1, formal_bounce_shot_count: 1, spatially_measurable_count: 1, no_bounce_before_next_contact_count: 0, zone_eligible_count: 0, spatial_measurability_numerator: 1, spatial_measurability_denominator: 1, zone_12_counts: {} },
      landings: [{ landing_id: "l1", shot_id: "s1", landing_status: "available", court_location: "inside_court", target_relation: "unknown", orientation_transform: "unavailable", canonicalization_basis: "unavailable", source_artifacts: [], diagnostics: [] }],
    });
    render(<LandingAnalysisPage jobId="job-1" onNavigate={vi.fn()} embedded videoPath={() => "/library/upload/v?view=video" as never} />);
    expect(await screen.findByText("球落点分析")).toBeTruthy();
    expect(screen.queryByText("返回任务管理")).toBeNull();
  });

  it("renders empty and error states without stale successful content", async () => {
    vi.mocked(getAnalysisResult).mockResolvedValue(result);
    vi.mocked(getShotLandings).mockResolvedValueOnce({
      schema_version: "shot-landings.v1", job_id: "job-1", status: "unavailable", detail: "没有可分析 Shot", generated_at: "2026-09-21T00:00:00Z",
      normalization_profile: { profile_id: "landing-orientation.v1", parameters: {} }, zone_profiles: {}, landings: [],
      summary: { shot_count: 0, available_landing_count: 0, formal_bounce_shot_count: 0, spatially_measurable_count: 0, no_bounce_before_next_contact_count: 0, zone_eligible_count: 0, spatial_measurability_numerator: 0, spatial_measurability_denominator: 0, zone_12_counts: {} },
    });
    const first = render(<LandingAnalysisPage jobId="job-1" onNavigate={vi.fn()} embedded videoPath={() => "/" as never} />);
    expect(await screen.findByText("本次分析暂无可用落点")).toBeTruthy();
    first.unmount();
    vi.mocked(getShotLandings).mockRejectedValueOnce(new Error("malformed payload"));
    render(<LandingAnalysisPage jobId="job-1" onNavigate={vi.fn()} embedded videoPath={() => "/" as never} />);
    expect(await screen.findByText("落点分析加载失败")).toBeTruthy();
    expect(screen.queryByText("球落点分析")).toBeNull();
  });
});
