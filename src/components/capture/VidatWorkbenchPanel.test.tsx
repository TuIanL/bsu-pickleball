import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { VidatWorkbenchPanel } from "./VidatWorkbenchPanel";

const api = vi.hoisted(() => ({
  listVidatPackages: vi.fn(), createVidatPackage: vi.fn(), openVidatPackage: vi.fn(),
  previewVidatImport: vi.fn(), confirmVidatImport: vi.fn(),
}));
vi.mock("../../services/analysisClient", () => api);

const pkg = { id: "vap_1", capture_take_id: "ct_1", version: 1, package_dir: "/tmp/pkg", manifest: {}, imported_at: null };

describe("VidatWorkbenchPanel", () => {
  afterEach(cleanup);
  beforeEach(() => {
    vi.clearAllMocks();
    api.listVidatPackages.mockResolvedValue([pkg]);
    api.createVidatPackage.mockResolvedValue({ ...pkg, id: "vap_2", version: 2 });
    api.previewVidatImport.mockResolvedValue({ preview_id: "vip", confirmation_token: "token", expires_at: "later",
      operations: [], coding_actions: [], changes: [{ kind: "winner_changed" }], blocking_errors: [], conflicts: [],
      score_summary: { affected_scores: [{ score_a: 1 }], final: { match_winner: "A" } } });
    api.confirmVidatImport.mockResolvedValue({ audit_id: "via" });
  });

  it("loads status and exports a new immutable version", async () => {
    render(<VidatWorkbenchPanel captureTakeId="ct_1" onImported={() => {}} />);
    expect(await screen.findByText("标注包 1 · 待编辑")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "导出新版本" }));
    await waitFor(() => expect(api.createVidatPackage).toHaveBeenCalledWith("ct_1"));
  });

  it("previews and confirms an import then refreshes projections", async () => {
    const onImported = vi.fn();
    const { container } = render(<VidatWorkbenchPanel captureTakeId="ct_1" onImported={onImported} />);
    await screen.findByText("标注包 1 · 待编辑");
    const file = new File(["{}"], "annotation.json", { type: "application/json" });
    Object.defineProperty(file, "text", { value: async () => "{}" });
    fireEvent.change(container.querySelector('input[type="file"]')!, { target: { files: [file] } });
    expect(await screen.findByText("变更 1")).toBeTruthy();
    expect(screen.getByText("最终胜者 A")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "确认导入并重建比分" }));
    await waitFor(() => expect(api.confirmVidatImport).toHaveBeenCalledWith("vap_1", "token", {}));
    await waitFor(() => expect(onImported).toHaveBeenCalled());
  });

  it("shows backend errors without losing the package", async () => {
    api.createVidatPackage.mockRejectedValue(new Error("主机位视频尚未就绪"));
    render(<VidatWorkbenchPanel captureTakeId="ct_1" onImported={() => {}} />);
    await screen.findByText("标注包 1 · 待编辑");
    fireEvent.click(screen.getByRole("button", { name: "导出新版本" }));
    expect((await screen.findByRole("alert")).textContent).toContain("主机位视频尚未就绪");
  });
});
