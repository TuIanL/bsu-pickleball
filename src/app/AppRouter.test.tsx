import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { RouteState } from "./navigationTypes";

vi.mock("../pages/BallTrajectoryPage", () => ({
  BallTrajectoryPage: ({ jobId }: { jobId: string }) => <div>trajectory-page:{jobId}</div>,
}));
vi.mock("../services/analysisClient", () => ({ getCaptureTake: vi.fn() }));

import { AppRouter } from "./AppRouter";
import { getCaptureTake } from "../services/analysisClient";

describe("AppRouter ball trajectory route", () => {
  it("loads the task-scoped trajectory page with the parsed job id", async () => {
    const route: RouteState = {
      name: "ball-trajectory",
      path: "/analysis/job-trajectory/trajectory",
      jobId: "job-trajectory",
      shellMode: "standard",
      navigationSection: "analysis",
    };

    render(<AppRouter route={route} onNavigate={vi.fn()} recentJob={null} />);

    expect((await screen.findByText("trajectory-page:job-trajectory")).textContent).toBe("trajectory-page:job-trajectory");
  });
});

describe("AppRouter legacy segment redirect", () => {
  it("replaces the old segment URL with the matching material analysis view", async () => {
    vi.mocked(getCaptureTake).mockResolvedValue({
      id: "take-1",
      field_session_id: "fs-1",
      source_session_type: "sync_recording",
      source_session_id: "sync-session-1",
      capture_mode: "dual",
      status: "completed",
      started_at: "2026-09-01T00:00:00Z",
      revision: 1,
    });
    const onNavigate = vi.fn();
    const route: RouteState = {
      name: "legacy-segments-redirect",
      path: "/capture/fs-1/takes/take-1/segments",
      takeId: "take-1",
      shellMode: "standard",
      navigationSection: "capture",
    };

    render(<AppRouter route={route} onNavigate={onNavigate} recentJob={null} />);

    expect(await screen.findByText("正在打开素材分析视图…")).toBeTruthy();
    await vi.waitFor(() => expect(onNavigate).toHaveBeenCalledWith(
      "/library/sync_recording/sync-session-1?view=analysis",
      { replace: true },
    ));
  });
});
