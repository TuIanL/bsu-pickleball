import { describe, expect, it } from "vitest";
import type { AnalysisUploadMetadata, RecordingStartRequest, SyncStartRequest } from "../types/report";

describe("source FPS request metadata", () => {
  it("analysis upload metadata carries user-confirmed FPS", () => {
    const metadata: AnalysisUploadMetadata = {
      fileName: "match.mp4",
      sourceFps: 90,
      matchTitle: "训练赛",
      venue: "Court A",
      matchDate: "2026-07-10",
      matchFormat: "doubles",
      cameraAngle: "elevated",
      athleteLabel: "A",
      level: "club",
    };

    expect(metadata.sourceFps).toBe(90);
  });

  it("single and dual recording requests can use selected FPS", () => {
    const single: RecordingStartRequest = {
      camera_id: "cam-1",
      fps: 60,
    };
    const dual: SyncStartRequest = {
      cam_1_id: "cam-1",
      cam_2_id: "cam-2",
      fps: 60,
    };

    expect(single.fps).toBe(60);
    expect(dual.fps).toBe(60);
  });
});
