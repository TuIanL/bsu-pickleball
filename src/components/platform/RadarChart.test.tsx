import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";
import { RadarChart } from "./RadarChart";
import { PLAYER_SCORE_DIMENSIONS } from "../../types/report";

describe("RadarChart", () => {
  const values = [8.4, 7.2, 8.0, 6.8, 7.5, 7.9];

  it("renders six dimension axis labels", () => {
    const { container } = render(<RadarChart color="#22C55E" values={values} />);
    const text = container.textContent ?? "";
    for (const dimension of PLAYER_SCORE_DIMENSIONS) {
      expect(text).toContain(dimension.label);
    }
  });

  it("renders vertex scores with one decimal", () => {
    const { container } = render(<RadarChart color="#22C55E" values={values} />);
    const text = container.textContent ?? "";
    expect(text).toContain("8.4");
    expect(text).toContain("7.2");
    // 整数分值同样保留 1 位小数
    expect(text).toContain("8.0");
  });

  it("fills the player polygon with the canonical color", () => {
    const { container } = render(<RadarChart color="#F97316" values={values} />);
    expect(container.querySelector("polygon[fill='#F97316']")).not.toBeNull();
  });

  it("renders five grid rings, one player polygon and six vertex circles", () => {
    const { container } = render(<RadarChart color="#22C55E" values={values} />);
    expect(container.querySelectorAll("polygon").length).toBe(6); // 5 环 + 1 球员多边形
    expect(container.querySelectorAll("circle").length).toBe(6);
  });
});
