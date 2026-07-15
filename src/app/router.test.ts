import { describe, expect, it } from "vitest";
import { parsePath, parseLocation } from "./router";
import type { RouteState } from "./navigationTypes";

describe("parsePath", () => {
  const cases: { pathname: string; expected: Partial<RouteState> }[] = [
    // Core product routes
    { pathname: "/", expected: { name: "landing", path: "/" } },
    { pathname: "", expected: { name: "landing", path: "/" } },
    { pathname: "/upload", expected: { name: "upload", path: "/upload" } },
    { pathname: "/tasks", expected: { name: "tasks", path: "/tasks" } },
    { pathname: "/capture", expected: { name: "captureHome", path: "/capture" } },
    { pathname: "/capture/new", expected: { name: "captureNew", path: "/capture/new" } },
    // captureConsole (dynamic sessionId)
    { pathname: "/capture/fs-1", expected: { name: "captureConsole", path: "/capture/fs-1", sessionId: "fs-1" } },
    // Segment manager
    {
      pathname: "/capture/fs-1/takes/take-1/segments",
      expected: {
        name: "segmentManager",
        path: "/capture/fs-1/takes/take-1/segments",
        fieldSessionId: "fs-1",
        takeId: "take-1",
      },
    },
    // Analysis routes
    { pathname: "/analysis/job-1", expected: { name: "analysis-job", path: "/analysis/job-1", jobId: "job-1" } },
    { pathname: "/analysis/job-1/details", expected: { name: "analysis-details", path: "/analysis/job-1/details", jobId: "job-1" } },
    { pathname: "/analysis/job-1/vision", expected: { name: "vision", path: "/analysis/job-1/vision", jobId: "job-1" } },
    {
      pathname: "/analysis/job-1/reports/movement",
      expected: { name: "report", path: "/analysis/job-1/reports/movement", reportType: "movement", jobId: "job-1" },
    },
    {
      pathname: "/analysis/job-1/reports/diagnosis",
      expected: { name: "report", path: "/analysis/job-1/reports/diagnosis", reportType: "diagnosis", jobId: "job-1" },
    },
    // Standalone vision
    { pathname: "/vision", expected: { name: "vision", path: "/vision" } },
    // Standalone reports
    { pathname: "/reports/movement", expected: { name: "report", path: "/reports/movement", reportType: "movement" } },
    { pathname: "/reports/diagnosis", expected: { name: "report", path: "/reports/diagnosis", reportType: "diagnosis" } },
    // Camera
    { pathname: "/camera", expected: { name: "camera-hub", path: "/camera" } },
    // Training / Hardware
    { pathname: "/training", expected: { name: "training", path: "/training" } },
    { pathname: "/hardware", expected: { name: "hardware", path: "/hardware" } },
    // Recording workspace
    { pathname: "/recording/sess-1", expected: { name: "recordingWorkspace", path: "/recording/sess-1", sessionId: "sess-1" } },
    // Upload with query params
    {
      pathname: "/upload?videoId=video-1&source=recording",
      expected: { name: "upload", path: "/upload", videoId: "video-1", source: "recording" },
    },
    // Old route compat: /analysis/new
    { pathname: "/analysis/new", expected: { name: "new-analysis", path: "/analysis/new" } },
    // Old route compat: /analysis/tasks
    { pathname: "/analysis/tasks", expected: { name: "analysis-tasks", path: "/analysis/tasks" } },
    // Old route compat: /analysis/tasks path when jobId = "tasks"
    { pathname: "/analysis/tasks", expected: { name: "analysis-tasks", path: "/analysis/tasks" } },
    // Unsupported report fallback -> analysis-details
    {
      pathname: "/analysis/job-1/reports/unsupported",
      expected: { name: "analysis-details", path: "/analysis/job-1/details", jobId: "job-1" },
    },
    // Unknown report type on standalone -> fallback to movement
    { pathname: "/reports/unknown", expected: { name: "report", path: "/reports/movement", reportType: "movement" } },
    // Unknown path -> landing
    { pathname: "/unknown", expected: { name: "landing", path: "/" } },
    { pathname: "/random/path", expected: { name: "landing", path: "/" } },
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
    });
  });

  it("parses initial load without search on upload", () => {
    const result = parseLocation("/upload", "");
    expect(result).toEqual({ name: "upload", path: "/upload" });
  });

  it("hands normal routes through to parsePath ignoring search", () => {
    const result = parseLocation("/tasks", "?foo=bar");
    expect(result).toEqual({ name: "tasks", path: "/tasks" });
  });

  it("handles landing page with search", () => {
    const result = parseLocation("/", "?utm=test");
    expect(result).toEqual({ name: "landing", path: "/" });
  });

  describe("navigate consistency", () => {
    it("returns same result as parsePath for upload with query when search contains the query", () => {
      const fromParsePath = parsePath("/upload?videoId=video-1&source=recording");
      const fromParseLocation = parseLocation("/upload", "?videoId=video-1&source=recording");
      expect(fromParseLocation).toEqual(fromParsePath);
    });

    it("returns same result for internal navigate path with query", () => {
      const navigatePath = "/upload?videoId=video-1&source=recording";
      const url = new URL(`http://localhost${navigatePath.startsWith("/") ? navigatePath : `/${navigatePath}`}`);
      const fromParseLocation = parseLocation(url.pathname, url.search);
      const fromParsePath = parsePath(navigatePath);
      expect(fromParseLocation).toEqual(fromParsePath);
    });
  });
});
