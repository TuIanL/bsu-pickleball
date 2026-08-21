import type { FusedPlayerOverlayEntity, FusedPlayerEvidenceType } from "../types/report";
import { describe, expect, it } from "vitest";
import {
  resolveDisplayGeometry,
  resolveEffectiveDisplayState,
  resolveEvidencePresentation,
  resolvePlayerIdentityHue,
} from "./overlayPresentation";

const ALL_EVIDENCE: FusedPlayerEvidenceType[] = [
  "base_observed",
  "guided_observed",
  "refined_observed",
  "cross_view_projected",
  "predicted_only",
  "bootstrap_backfill",
];

function entity(overrides: Partial<FusedPlayerOverlayEntity>): FusedPlayerOverlayEntity {
  return {
    player_id: "Player_1",
    bbox: null,
    evidence_type: "base_observed",
    source_confidence: 0.5,
    overlay_confidence: 0.5,
    ...overrides,
  };
}

describe("resolvePlayerIdentityHue（Stabilize-Temporal-0.4 / 身份色跨 evidence 恒定）", () => {
  it("同一 canonical Player 跨所有 evidence 恒 hue（identity_color_switch_count == 0）", () => {
    const hues = ALL_EVIDENCE.map(() => resolvePlayerIdentityHue("Player_1"));
    expect(new Set(hues).size).toBe(1);
  });

  it("不同 canonical Player 产生不同 hue", () => {
    const hues = ["Player_1", "Player_2", "Player_3", "Player_4"].map((id) => resolvePlayerIdentityHue(id));
    expect(new Set(hues).size).toBe(4);
  });

  it("legacy ID 归一到 canonical palette", () => {
    for (const legacy of ["P3", "p3", "player_3", "global_player_3"]) {
      expect(resolvePlayerIdentityHue(legacy)).toBe(resolvePlayerIdentityHue("Player_3"));
    }
  });

  it("unknown ID 用确定性 hash palette 且同一 ID 稳定", () => {
    const a = resolvePlayerIdentityHue("some_unknown_track_99");
    expect(resolvePlayerIdentityHue("some_unknown_track_99")).toBe(a);
  });
});

describe("resolveEvidencePresentation（evidence 只表达 provenance）", () => {
  it("真实检测为实线", () => {
    for (const ev of ["base_observed", "guided_observed", "refined_observed"] as const) {
      expect(resolveEvidencePresentation(ev).solid).toBe(true);
    }
  });
  it("cross_view/predicted 为虚线且淡化", () => {
    expect(resolveEvidencePresentation("cross_view_projected").solid).toBe(false);
    expect(resolveEvidencePresentation("predicted_only").solid).toBe(false);
    expect(resolveEvidencePresentation("cross_view_projected").opacity).toBeLessThan(1);
    expect(resolveEvidencePresentation("predicted_only").opacity).toBeLessThan(0.7);
  });
});

describe("resolveDisplayGeometry / resolveEffectiveDisplayState", () => {
  it("display_state 决定 topology", () => {
    expect(resolveDisplayGeometry("REAL_BOX")).toBe("box");
    expect(resolveDisplayGeometry("ASSISTED_BOX")).toBe("box");
    expect(resolveDisplayGeometry("PROJECTED_BOX")).toBe("box");
    expect(resolveDisplayGeometry("PROJECTED_POINT")).toBe("point");
    expect(resolveDisplayGeometry("PREDICTED_POINT")).toBe("point");
    expect(resolveDisplayGeometry("HIDDEN")).toBe("hidden");
    expect(resolveDisplayGeometry(undefined)).toBeUndefined();
  });

  it("PROJECTED_BOX 复用 last-real geometry（cross_view + display_state=PROJECTED_BOX ⇒ box）", () => {
    const e = entity({ evidence_type: "cross_view_projected", display_state: "PROJECTED_BOX", bbox: [0, 0, 10, 20] });
    expect(resolveEffectiveDisplayState(e)).toBe("PROJECTED_BOX");
    expect(resolveDisplayGeometry(resolveEffectiveDisplayState(e))).toBe("box");
  });

  it("真实 bbox 缺失不得保留 REAL_BOX（证据降级后 effective 为 PROJECTED_BOX）", () => {
    const e = entity({ evidence_type: "cross_view_projected", display_state: "PROJECTED_BOX" });
    expect(resolveEffectiveDisplayState(e)).toBe("PROJECTED_BOX");
  });

  it("旧产物缺失 display_state 时由 evidence + bbox 推导 legacy", () => {
    expect(resolveEffectiveDisplayState(entity({ evidence_type: "predicted_only" }))).toBe("PREDICTED_POINT");
    expect(resolveEffectiveDisplayState(entity({ evidence_type: "cross_view_projected", bbox: [0, 0, 1, 1] }))).toBe("PROJECTED_BOX");
    expect(resolveEffectiveDisplayState(entity({ evidence_type: "cross_view_projected", bbox: null }))).toBe("PROJECTED_POINT");
    expect(resolveEffectiveDisplayState(entity({ evidence_type: "refined_observed" }))).toBe("ASSISTED_BOX");
    expect(resolveEffectiveDisplayState(entity({ evidence_type: "base_observed" }))).toBe("REAL_BOX");
  });
});