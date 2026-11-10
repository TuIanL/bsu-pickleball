import { describe, expect, it } from "vitest";
import { selectVisualOverlay } from "./visualOverlayViews";

describe("camera-specific pixel overlays", () => {
  const artifact = {
    reference_view_id: "cam_1", frames: ["reference"], source: { width: 1920, height: 1080 },
    skeleton_edges: ["edge"], views: {
      cam_2: { frames: ["secondary"], source: { width: 1280, height: 720 } },
    },
  };
  it("keeps camera pixel coordinates and inherited skeleton schema together", () => {
    const selected = selectVisualOverlay(artifact, "cam_2");
    expect(selected?.frames).toEqual(["secondary"]);
    expect(selected?.source.width).toBe(1280);
    expect(selected?.skeleton_edges).toEqual(["edge"]);
    expect(artifact.frames).toEqual(["reference"]);
  });
  it("does not draw reference poses or balls on a camera without evidence", () => {
    expect(selectVisualOverlay(artifact, "cam_3")).toBeNull();
    expect(selectVisualOverlay({ frames: ["legacy"] }, "cam_2")).toBeNull();
  });
  it("preserves old single-camera artifacts on their own view", () => {
    expect(selectVisualOverlay({ frames: ["legacy"] })?.frames).toEqual(["legacy"]);
    expect(selectVisualOverlay({ frames: ["legacy"] }, "cam_2", "cam_2")?.frames).toEqual(["legacy"]);
  });
});
