import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { NetProfileCalibrator } from "./NetProfileCalibrator";
import { buildStandardNetProfile } from "../../types/metricCourtScene";

const initial = {
  profile: buildStandardNetProfile(true),
  annotations: {
    left: { x: 200, y: 360 },
    center: { x: 640, y: 340 },
    right: { x: 1080, y: 360 },
  },
  holdoutAnnotations: {
    holdout_left_quarter: { x: 420, y: 350 },
    holdout_right_quarter: { x: 860, y: 350 },
  },
  imageWidth: 1280,
  imageHeight: 720,
  frameIndex: 30,
};

describe("NetProfileCalibrator", () => {
  afterEach(() => cleanup());

  it("requires manual confirmation before completing three-point annotation", () => {
    render(
      <NetProfileCalibrator
        initial={{ ...initial, profile: buildStandardNetProfile(false) }}
        onCancel={vi.fn()}
        onComplete={vi.fn()}
        videoSrc="/video.mp4"
        viewId="cam_1"
      />,
    );

    expect(screen.getByText("球网左端")).toBeTruthy();
    expect(screen.getByText("球网中心")).toBeTruthy();
    expect(screen.getByText("球网右端")).toBeTruthy();
    expect(screen.getByRole("button", { name: /完成球网标注/ })).toHaveProperty("disabled", true);
  });

  it("returns a confirmed standard profile with view annotations", () => {
    const onComplete = vi.fn();
    render(
      <NetProfileCalibrator
        initial={initial}
        onCancel={vi.fn()}
        onComplete={onComplete}
        videoSrc="/video.mp4"
        viewId="cam_2"
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /完成球网标注/ }));

    expect(onComplete).toHaveBeenCalledWith(expect.objectContaining({
      imageWidth: 1280,
      imageHeight: 720,
      annotations: expect.objectContaining({ center: { x: 640, y: 340 } }),
      holdoutAnnotations: expect.objectContaining({ holdout_left_quarter: { x: 420, y: 350 } }),
    }));
  });
});
