import { describe, expect, it } from "vitest";
import {
  buildCourtOverlayGeometry,
  buildNetOverlayPoints,
  canonicalToLocalCourtPoint,
  clipNetOverlayPointsToCourt,
  projectCourtPointToImage,
} from "./videoCourtOverlay";

const identityHomography = [
  [1, 0, 0],
  [0, 1, 0],
  [0, 0, 1],
];

describe("video court overlay geometry", () => {
  it("projects court coordinates and scales calibration pixels to the video source", () => {
    expect(
      projectCourtPointToImage(
        [
          [10, 0, 0],
          [0, 10, 0],
          [0, 0, 1],
        ],
        { x: 20, y: 44 },
        { width: 200, height: 440 },
        { width: 400, height: 880 },
      ),
    ).toEqual({ x: 400, y: 880 });
  });

  it("keeps local court geometry independent from the view orientation", () => {
    const geometry = buildCourtOverlayGeometry(identityHomography, null, { width: 20, height: 44 });
    expect(geometry?.boundary[0]).toEqual({ x: 0, y: 0 });
    expect(geometry?.boundary[2]).toEqual({ x: 20, y: 44 });
  });

  it("applies orientation only at the canonical-to-local boundary", () => {
    expect(canonicalToLocalCourtPoint({ x: 2, y: 4 }, "identity")).toEqual({ x: 2, y: 4 });
    expect(canonicalToLocalCourtPoint({ x: 2, y: 4 }, "rotate_180")).toEqual({ x: 18, y: 40 });
    expect(canonicalToLocalCourtPoint({ x: 2, y: 4 }, "mirror_x")).toEqual({ x: 18, y: 4 });
    expect(canonicalToLocalCourtPoint({ x: 2, y: 4 }, "mirror_y")).toEqual({ x: 2, y: 40 });
  });

  it("scales the manually marked net points without mirroring image coordinates", () => {
    expect(
      buildNetOverlayPoints(
        { left: { x: 10, y: 100 }, center: { x: 20, y: 80 }, right: { x: 30, y: 100 } },
        { width: 100, height: 200 },
        { width: 200, height: 400 },
      ),
    ).toEqual([
      { x: 20, y: 200 },
      { x: 40, y: 160 },
      { x: 60, y: 200 },
    ]);
  });

  it("returns no net geometry when any required point is missing", () => {
    expect(
      buildNetOverlayPoints({ left: { x: 10, y: 100 }, center: { x: 20, y: 80 } }, null, { width: 200, height: 400 }),
    ).toBeNull();
  });

  it("clips an over-wide net line to the projected court sidelines", () => {
    const court = buildCourtOverlayGeometry(identityHomography, null, { width: 1000, height: 1000 });
    const clipped = clipNetOverlayPointsToCourt(
      [
        { x: 0, y: 500 },
        { x: 500, y: 500 },
        { x: 1000, y: 500 },
      ],
      {
        boundary: [
          { x: 100, y: 100 },
          { x: 900, y: 100 },
          { x: 900, y: 900 },
          { x: 100, y: 900 },
          { x: 100, y: 100 },
        ],
        lines: [],
      },
    );
    expect(clipped).toEqual([
      { x: 0, y: 500 },
      { x: 500, y: 500 },
      { x: 1000, y: 500 },
    ]);
    expect(court).not.toBeNull();
  });
});
