import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { VidatWorkbenchPanel } from "./VidatWorkbenchPanel";

const api = vi.hoisted(() => ({
  listVidatPackages: vi.fn(), createVidatPackage: vi.fn(), openVidatPackage: vi.fn(), startVidatService: vi.fn(),
  getVidatServiceStatus: vi.fn(), stopVidatService: vi.fn(), deriveVidatPackage: vi.fn(), updateVidatPackage: vi.fn(),
  deleteVidatPackage: vi.fn(), purgeVidatPackage: vi.fn(), compareVidatPackages: vi.fn(),
  previewVidatImport: vi.fn(), confirmVidatImport: vi.fn(),
}));
vi.mock("../../services/analysisClient", () => api);

const pkg = { id: "vap_1", capture_take_id: "ct_1", version: 1, package_dir: "/tmp/pkg", manifest: {}, imported_at: null,
  name: "第 1 版", owner: null, note: null, provenance: "generated", source_package_id: null, created_at: null, deleted_at: null, is_active: false };
const pkg2 = { ...pkg, id: "vap_2", version: 2, name: "复核版本" };

describe("VidatWorkbenchPanel", () => {
  afterEach(() => { cleanup(); vi.restoreAllMocks(); });
  beforeEach(() => {
    vi.clearAllMocks();
    api.listVidatPackages.mockResolvedValue([pkg]);
    api.openVidatPackage.mockResolvedValue({ url: "http://localhost:8888/?package=vap_1" });
    api.createVidatPackage.mockResolvedValue(pkg2);
    api.deriveVidatPackage.mockResolvedValue(pkg2);
    api.updateVidatPackage.mockResolvedValue({ ...pkg, name: "已重命名" });
    api.deleteVidatPackage.mockResolvedValue({ ...pkg, deleted_at: "now" });
    api.purgeVidatPackage.mockResolvedValue({ package_id: "vap_1", purged: true });
    api.compareVidatPackages.mockResolvedValue({ capture_take_id: "ct_1", before: pkg, after: pkg2, changes: [{ kind: "winner_changed" }] });
    api.startVidatService.mockResolvedValue({ url: "http://localhost:8888", status: "running", running: true, controlled: true, started: false });
    api.getVidatServiceStatus.mockResolvedValue({ url: "http://localhost:8888", status: "stopped", running: false, controlled: false });
    api.stopVidatService.mockResolvedValue({ url: "http://localhost:8888", status: "stopped", running: false, controlled: false, stopped: true });
    api.previewVidatImport.mockResolvedValue({ preview_id: "vip", confirmation_token: "token", expires_at: "later",
      operations: [], coding_actions: [], changes: [{ kind: "winner_changed" }], blocking_errors: [], conflicts: [],
      score_summary: { affected_scores: [{ score_a: 1 }], final: { match_winner: "A" } } });
    api.confirmVidatImport.mockResolvedValue({ audit_id: "via", source_package_id: "vap_1", result_package_id: "vap_2", active_vidat_package_id: "vap_2", operations: [] });
  });

  it("loads status and exports a new immutable version", async () => {
    render(<VidatWorkbenchPanel captureTakeId="ct_1" onImported={() => {}} />);
    expect(await screen.findByRole("combobox", { name: "选择标注包" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Vidat 视频标注" })).toBeTruthy();
    expect(screen.getByText("第 1 版 · generated · 待编辑")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "导出新版本" }));
    await waitFor(() => expect(api.createVidatPackage).toHaveBeenCalledWith("ct_1", expect.any(Object)));
  });

  it("previews and confirms an import then refreshes projections", async () => {
    const onImported = vi.fn();
    api.listVidatPackages.mockResolvedValue([pkg, pkg2]);
    const { container } = render(<VidatWorkbenchPanel captureTakeId="ct_1" onImported={onImported} />);
    await screen.findByRole("combobox", { name: "选择标注包" });
    const file = new File(["{}"], "annotation.json", { type: "application/json" });
    Object.defineProperty(file, "text", { value: async () => "{}" });
    fireEvent.change(container.querySelector('input[type="file"]')!, { target: { files: [file] } });
    expect(await screen.findByText("变更 1")).toBeTruthy();
    expect(screen.getByText("最终胜者 A")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "确认导入并重建比分" }));
    await waitFor(() => expect(api.confirmVidatImport).toHaveBeenCalledWith("vap_1", "token", {}));
    await waitFor(() => expect(onImported).toHaveBeenCalled());
    expect((screen.getByRole("combobox", { name: "选择标注包" }) as HTMLSelectElement).value).toBe("vap_2");
  });

  it("shows backend errors without losing the package", async () => {
    api.createVidatPackage.mockRejectedValue(new Error("主机位视频尚未就绪"));
    render(<VidatWorkbenchPanel captureTakeId="ct_1" onImported={() => {}} />);
    await screen.findByRole("combobox", { name: "选择标注包" });
    fireEvent.click(screen.getByRole("button", { name: "导出新版本" }));
    expect((await screen.findByRole("alert")).textContent).toContain("主机位视频尚未就绪");
  });

  it("edits metadata, derives and compares versions", async () => {
    api.listVidatPackages.mockResolvedValue([pkg, pkg2]);
    render(<VidatWorkbenchPanel captureTakeId="ct_1" onImported={() => {}} />);
    await screen.findByRole("combobox", { name: "选择标注包" });
    fireEvent.click(screen.getByRole("button", { name: "填写元数据" }));
    fireEvent.change(screen.getByLabelText("名称"), { target: { value: "教练复核" } });
    fireEvent.click(screen.getByRole("button", { name: "保存当前元数据" }));
    await waitFor(() => expect(api.updateVidatPackage).toHaveBeenCalled());
    fireEvent.click(screen.getByRole("button", { name: "比较版本" }));
    await waitFor(() => expect(api.compareVidatPackages).toHaveBeenCalledWith("vap_2", "vap_1"));
    expect(await screen.findByText("版本差异")).toBeTruthy();
  });

  it("opens a platform-owned tab and closes only that tab", async () => {
    const close = vi.fn();
    vi.spyOn(window, "open").mockReturnValue({ closed: false, close } as unknown as Window);
    render(<VidatWorkbenchPanel captureTakeId="ct_1" onImported={() => {}} />);
    await screen.findByRole("combobox", { name: "选择标注包" });
    fireEvent.click(screen.getByRole("button", { name: "打开 Vidat" }));
    await waitFor(() => expect(window.open).toHaveBeenCalled());
    fireEvent.click(screen.getByRole("button", { name: "关闭 Vidat 标签页" }));
    expect(close).toHaveBeenCalledTimes(1);
  });

  it("deletes a version and stops the Vidat service from the workbench", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<VidatWorkbenchPanel captureTakeId="ct_1" onImported={() => {}} />);
    await screen.findByRole("combobox", { name: "选择标注包" });
    fireEvent.click(screen.getByRole("button", { name: "删除版本" }));
    await waitFor(() => expect(api.deleteVidatPackage).toHaveBeenCalledWith("vap_1"));
    fireEvent.click(screen.getByRole("button", { name: "停止 Vidat 服务" }));
    await waitFor(() => expect(api.stopVidatService).toHaveBeenCalled());
  });
});
