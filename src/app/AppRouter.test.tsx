import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { RouteState } from "./navigationTypes";

vi.mock("../pages/BallTrajectoryPage", () => ({
  BallTrajectoryPage: ({ jobId }: { jobId: string }) => <div>trajectory-page:{jobId}</div>,
}));

import { AppRouter } from "./AppRouter";

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
