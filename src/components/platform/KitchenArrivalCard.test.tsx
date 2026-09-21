import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { KitchenArrivalArtifact } from "../../types/kitchenArrival";
import { KitchenArrivalCard } from "./KitchenArrivalCard";

const base = {
  schema_version: "kitchen-arrival.v1" as const,
  job_id: "job-1",
  generated_at: "2026-09-20T00:00:00Z",
  aggregation_scope: "formal_rally_batch" as const,
  reference: {
    schema_version: "kitchen-arrival-reference.v1" as const,
    arrival_band_m: 0.75,
    stable_ms: 500,
    arrival_min_detected_support_ms: 250,
    not_arrived_min_coverage_ratio: 0.8,
    not_arrived_max_gap_ms: 500,
    min_sample_count: 3,
  },
  rallies: [],
  diagnostics: { total_rallies: 3, eligible_samples: 3, excluded_samples: 0, excluded_reasons: {}, coverage_ratios: {}, max_gaps_ms: {}, warnings: [] },
  source_artifacts: [],
  provenance: {},
} satisfies Omit<KitchenArrivalArtifact, "status" | "detail" | "players">;

describe("KitchenArrivalCard", () => {
  afterEach(() => cleanup());

  it("shows per-player ratio lanes for available evidence", () => {
    const artifact: KitchenArrivalArtifact = {
      ...base,
      status: "available",
      detail: "ok",
      players: [
        { player_id: "Player_1", display_name: "小明", team_id: "A", arrived_count: 3, eligible_count: 3, sample_count: 3, excluded_count: 0, arrival_rate: 1, status: "available", rally_ids: ["r1", "r2", "r3"] },
        { player_id: "Player_3", display_name: "小红", team_id: "B", arrived_count: 2, eligible_count: 3, sample_count: 3, excluded_count: 0, arrival_rate: 2 / 3, status: "available", rally_ids: ["r1", "r2", "r3"] },
      ],
    };
    render(<KitchenArrivalCard artifact={artifact} loadState="available" />);
    expect(screen.getByText("发球队 · 网前到位率")).toBeTruthy();
    expect(screen.getByTestId("kitchen-arrival-court-profile")).toBeTruthy();
    expect(screen.getByText("100%")).toBeTruthy();
    expect(screen.getByText("67%")).toBeTruthy();
  });

  it("does not show a percentage when evidence is insufficient", () => {
    const artifact: KitchenArrivalArtifact = {
      ...base,
      status: "insufficient_evidence",
      detail: "有效回合不足",
      players: [{ player_id: "Player_1", team_id: "A", arrived_count: 1, eligible_count: 1, sample_count: 1, excluded_count: 0, arrival_rate: null, status: "insufficient_evidence", reason: "样本不足", rally_ids: ["r1"] }],
    };
    render(<KitchenArrivalCard artifact={artifact} loadState="available" />);
    expect(screen.getByText(/样本不足/)).toBeTruthy();
    expect(screen.getByText("—")).toBeTruthy();
  });

  it("keeps a local failed state without blocking the rest of the page", () => {
    render(<KitchenArrivalCard artifact={null} loadState="failed" detail="接口失败" />);
    expect(screen.getByTestId("kitchen-arrival-card")).toBeTruthy();
    expect(screen.getByText(/读取失败/)).toBeTruthy();
    expect(screen.queryByText(/%/)).toBeNull();
  });
});
