import { describe, expect, it } from "vitest";
import { parsePath, parseLocation } from "./router";
import type { RouteState } from "./navigationTypes";

describe("parsePath", () => {
  const cases: { pathname: string; expected: Partial<RouteState> }[] = [
    // Core product routes
    { pathname: "/", expected: { name: "landing", path: "/", shellMode: "landing", navigationSection: null } },
    { pathname: "", expected: { name: "landing", path: "/", shellMode: "landing", navigationSection: null } },
    { pathname: "/upload", expected: { name: "upload", path: "/upload", shellMode: "landing", navigationSection: null } },
    { pathname: "/tasks", expected: { name: "tasks", path: "/tasks", shellMode: "standard", navigationSection: "analysis" } },
    { pathname: "/capture", expected: { name: "captureHome", path: "/capture", shellMode: "standard", navigationSection: "videos" } },
    { pathname: "/capture/new", expected: { name: "captureNew", path: "/capture/new", shellMode: "standard", navigationSection: "capture" } },
    { pathname: "/showcase/showcase-1", expected: { name: "showcase", path: "/showcase/showcase-1", runtimeId: "showcase-1", shellMode: "landing", navigationSection: null } },
    // captureConsole (dynamic sessionId)
    { pathname: "/capture/fs-1", expected: { name: "captureConsole", path: "/capture/fs-1", sessionId: "fs-1", shellMode: "capture", navigationSection: "capture" } },
    { pathname: "/capture/fs-1/analyze", expected: { name: "recording-analyze", path: "/capture/fs-1/analyze", sessionId: "fs-1", shellMode: "standard", navigationSection: "analysis" } },
    // Segment manager
    {
      pathname: "/capture/fs-1/takes/take-1/segments",
      expected: {
        name: "segmentManager",
        path: "/capture/fs-1/takes/take-1/segments",
        fieldSessionId: "fs-1",
        takeId: "take-1",
        shellMode: "standard",
        navigationSection: "capture",
      },
    },
    // Workspace
    { pathname: "/workspace", expected: { name: "workspace", path: "/workspace", shellMode: "standard", navigationSection: "capture" } },
    // Analysis routes
    { pathname: "/analysis/tasks", expected: { name: "analysis-tasks", path: "/analysis/tasks", shellMode: "standard", navigationSection: "analysis" } },
    { pathname: "/analysis/job-1", expected: { name: "analysis-job", path: "/analysis/job-1", jobId: "job-1", shellMode: "standard", navigationSection: "analysis" } },
    { pathname: "/analysis/job-1/details", expected: { name: "analysis-details", path: "/analysis/job-1/details", jobId: "job-1", shellMode: "standard", navigationSection: "analysis" } },
    { pathname: "/analysis/job-1/vision", expected: { name: "vision", path: "/analysis/job-1/vision", jobId: "job-1", shellMode: "standard", navigationSection: "analysis" } },
    { pathname: "/analysis/job-1/trajectory", expected: { name: "ball-trajectory", path: "/analysis/job-1/trajectory", jobId: "job-1", shellMode: "standard", navigationSection: "analysis" } },
    {
      pathname: "/analysis/job-1/reports/movement",
      expected: { name: "report", path: "/analysis/job-1/reports/movement", reportType: "movement", jobId: "job-1", shellMode: "standard", navigationSection: "reports" },
    },
    {
      pathname: "/analysis/job-1/reports/diagnosis",
      expected: { name: "report", path: "/analysis/job-1/reports/diagnosis", reportType: "diagnosis", jobId: "job-1", shellMode: "standard", navigationSection: "reports" },
    },
    // Standalone reports
    { pathname: "/reports/movement", expected: { name: "report", path: "/reports/movement", reportType: "movement", shellMode: "standard", navigationSection: "reports" } },
    { pathname: "/reports/diagnosis", expected: { name: "report", path: "/reports/diagnosis", reportType: "diagnosis", shellMode: "standard", navigationSection: "reports" } },
    // Camera
    { pathname: "/camera", expected: { name: "camera-hub", path: "/camera", shellMode: "standard", navigationSection: "devices" } },
    // Training / Hardware
    { pathname: "/training", expected: { name: "training", path: "/training", shellMode: "standard", navigationSection: "settings" } },
    { pathname: "/hardware", expected: { name: "hardware", path: "/hardware", shellMode: "standard", navigationSection: "settings" } },
    // Standalone vision
    { pathname: "/vision", expected: { name: "vision", path: "/vision", shellMode: "standard", navigationSection: "analysis" } },
    // Recording workspace
    { pathname: "/recording/sess-1", expected: { name: "recordingWorkspace", path: "/recording/sess-1", sessionId: "sess-1", shellMode: "standard", navigationSection: "videos" } },
    // Upload with query params
    {
      pathname: "/upload?videoId=video-1&source=recording",
      expected: { name: "upload", path: "/upload", videoId: "video-1", source: "recording", shellMode: "landing", navigationSection: null },
    },
    // Unknown -> landing
    { pathname: "/unknown", expected: { name: "landing", path: "/", shellMode: "landing", navigationSection: null } },
  ];

  it.each(cases)("parses $pathname -> $expected.name", ({ pathname, expected }) => {
    const result = parsePath(pathname);
    for (const key of Object.keys(expected) as (keyof RouteState)[]) {
      expect(result[key]).toEqual(expected[key]);
    }
  });
});

describe("parseLocation", () => {
  it("parses initial load with pathname and search", () => {
    const result = parseLocation("/upload", "?videoId=video-1&source=recording");
    expect(result).toEqual({
      name: "upload",
      path: "/upload",
      videoId: "video-1",
      source: "recording",
      shellMode: "landing",
      navigationSection: null,
    });
  });

  it("parses initial load without search on upload", () => {
    const result = parseLocation("/upload", "");
    expect(result).toEqual({ name: "upload", path: "/upload", shellMode: "landing", navigationSection: null });
  });

  it("hands normal routes through to parsePath ignoring search", () => {
    const result = parseLocation("/tasks", "?foo=bar");
    expect(result).toEqual({ name: "tasks", path: "/tasks", shellMode: "standard", navigationSection: "analysis" });
  });

  it("restores the dual-camera task tab and session from the URL", () => {
    expect(parseLocation("/analysis/tasks", "?source=sync_recording&session=sync-1")).toMatchObject({
      name: "analysis-tasks",
      taskSource: "sync_recording",
      taskSessionId: "sync-1",
    });
  });

  it("preserves a safe workbench return path across direct loads", () => {
    expect(parseLocation("/sync-calibration", "?take=take-1&return=%2Fcapture%2Ftakes%2Ftake-1%2Fanalyze")).toMatchObject({
      name: "sync-calibration",
      captureTakeId: "take-1",
      returnPath: "/capture/takes/take-1/analyze",
    });
    expect(parseLocation("/sync-calibration", "?take=take-1&return=https%3A%2F%2Fevil.invalid")).toMatchObject({
      name: "sync-calibration",
      captureTakeId: "take-1",
      returnPath: undefined,
    });
  });

  it("falls back to the upload task tab for an invalid URL source", () => {
    expect(parseLocation("/analysis/tasks", "?source=unknown")).toMatchObject({
      name: "analysis-tasks",
      taskSource: "upload",
    });
  });
});
