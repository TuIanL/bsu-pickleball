import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { createFieldSession } from "../services/analysisClient";
import { CaptureWizardPage } from "./CaptureWizardPage";

vi.mock("../services/analysisClient", () => ({
  createFieldSession: vi.fn(),
}));

const mockedCreateFieldSession = vi.mocked(createFieldSession);

afterEach(() => {
  cleanup();
  mockedCreateFieldSession.mockReset();
});

function moveToAnalysisStep() {
  fireEvent.click(screen.getByRole("button", { name: "下一步" }));
  fireEvent.click(screen.getByRole("button", { name: "下一步" }));
}

describe("CaptureWizard showcase configuration", () => {
  it("forces dual cameras when showcase mode is selected", async () => {
    mockedCreateFieldSession.mockResolvedValue({
      id: "field-showcase",
      title: "展示任务",
      venue: "",
      court_name: "",
      capture_mode: "practice",
      match_format: "doubles",
      camera_setup: "dual",
      display_mode: "showcase",
      status: "planned",
      notes: "",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    });
    const onNavigate = vi.fn();
    render(<CaptureWizardPage onNavigate={onNavigate} />);
    moveToAnalysisStep();

    fireEvent.click(screen.getByRole("button", { name: /现场展示模式/ }));
    expect(screen.getByText(/展示模式已锁定双摄方案/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /创建采集任务/ }));

    await waitFor(() => expect(mockedCreateFieldSession).toHaveBeenCalledWith(expect.objectContaining({
      camera_setup: "dual",
      display_mode: "showcase",
    })));
    expect(onNavigate).toHaveBeenCalledWith("/capture/field-showcase");
  });

  it("keeps standard mode as a non-showcase request", async () => {
    mockedCreateFieldSession.mockResolvedValue({
      id: "field-standard",
      title: "标准任务",
      venue: "",
      court_name: "",
      capture_mode: "practice",
      match_format: "doubles",
      camera_setup: "dual",
      display_mode: "standard",
      status: "planned",
      notes: "",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    });
    render(<CaptureWizardPage onNavigate={vi.fn()} />);
    moveToAnalysisStep();
    fireEvent.click(screen.getByRole("button", { name: /现场展示模式/ }));
    fireEvent.click(screen.getByRole("button", { name: /标准模式/ }));
    fireEvent.click(screen.getByRole("button", { name: /创建采集任务/ }));

    await waitFor(() => expect(mockedCreateFieldSession).toHaveBeenCalledWith(expect.objectContaining({
      display_mode: "standard",
    })));
  });
});
