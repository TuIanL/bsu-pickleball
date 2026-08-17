import { describe, expect, it } from "vitest";
import { availabilityWeight, deriveHealthScore } from "./observabilityViz";
import type { HealthScoreInput, VizAvailability } from "./observabilityViz";

function input(availability: Record<string, VizAvailability>, extra?: Partial<HealthScoreInput>): HealthScoreInput {
  return { availability, ...extra };
}

describe("availabilityWeight", () => {
  it("maps four availability states to weights", () => {
    expect(availabilityWeight("available")).toBe(1);
    expect(availabilityWeight("partial")).toBe(0.6);
    expect(availabilityWeight("unavailable")).toBe(0);
    expect(availabilityWeight("not_applicable")).toBeNull();
  });
});

describe("deriveHealthScore", () => {
  it("scores high when all four domains are available with good fusion and recovery", () => {
    const result = deriveHealthScore(
      input(
        { sync: "available", fusion: "available", recovery: "available", refinement: "available" },
        { effectiveMultiviewRatio: 0.87, recoverySuccessRate: 0.92 },
      ),
    );
    expect(result.score).toBeGreaterThanOrEqual(90);
    expect(result.applicableCount).toBe(4);
    expect(result.conclusion).toContain("运行良好");
  });

  it("penalizes unavailable domains", () => {
    const result = deriveHealthScore(
      input({ sync: "available", fusion: "unavailable", recovery: "available", refinement: "available" }),
    );
    expect(result.score).toBeLessThan(80);
    expect(result.conclusion).toContain("证据缺失");
    expect(result.conclusion).toContain("fusion");
  });

  it("treats partial as degraded but not failed", () => {
    const result = deriveHealthScore(input({ sync: "available", fusion: "partial", recovery: "partial", refinement: "available" }));
    expect(result.score).toBeGreaterThan(50);
    expect(result.score).toBeLessThan(90);
    expect(result.conclusion).toContain("降级");
  });

  it("excludes not_applicable domains from the denominator", () => {
    const allAvailable = deriveHealthScore(input({ sync: "available", fusion: "available", recovery: "available", refinement: "available" }, { recoverySuccessRate: 0.5 }));
    const lateFusion = deriveHealthScore(input({ sync: "available", fusion: "available", recovery: "not_applicable", refinement: "not_applicable" }));
    expect(lateFusion.applicableCount).toBe(2);
    expect(lateFusion.score).toBeGreaterThan(allAvailable.score);
    expect(lateFusion.conclusion).toContain("融合模式");
  });

  it("uses neutral ratio score when ratio is missing but fusion is available", () => {
    const result = deriveHealthScore(input({ sync: "available", fusion: "available", recovery: "not_applicable", refinement: "not_applicable" }, { effectiveMultiviewRatio: null }));
    // base=1 → 0.5*100 + 0.25*50 + 0.25*100 = 87.5 → 88
    expect(result.score).toBe(88);
  });

  it("scores zero when all domains are unavailable", () => {
    const result = deriveHealthScore(input({ sync: "unavailable", fusion: "unavailable", recovery: "unavailable", refinement: "unavailable" }));
    expect(result.score).toBe(0);
  });

  it("clamps ratio and recovery rate to [0,1]", () => {
    const result = deriveHealthScore(input({ sync: "available", fusion: "available", recovery: "available", refinement: "available" }, { effectiveMultiviewRatio: 1.5, recoverySuccessRate: -0.2 }));
    expect(result.score).toBeGreaterThanOrEqual(0);
    expect(result.score).toBeLessThanOrEqual(100);
  });
});
