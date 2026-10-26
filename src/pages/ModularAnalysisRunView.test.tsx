import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AnalysisJobSummary, ModularRunManifest } from "../types/report";
import { AnalysisJobPage } from "./AnalysisJobPage";
import * as client from "../services/analysisClient";

vi.mock("../services/analysisClient", () => ({
  getAnalysisJob: vi.fn(), getAnalysisModuleManifest: vi.fn(), getAnalysisModuleArtifact: vi.fn(),
  getAnalysisRunTrace: vi.fn().mockResolvedValue(null), getAnalysisResult: vi.fn(),
  rememberAnalysisJob: vi.fn(), cancelAnalysisJob: vi.fn(), isAnalysisApiError: () => false,
}));

const job: AnalysisJobSummary = {
  id: "job-module", analysisEngine: "modular_v1", resultKind: "modular", status: "completed",
  canonicalStatus: "succeeded", stage: "modular", stages: [], progress: 100,
  createdAt: "2026-10-17", updatedAt: "2026-10-17", clipStartMs: 60000, clipEndMs: 90000,
  planId: "plan-one", planHash: "hash-one",
  metadata: { fileName: "clip.mp4", matchTitle: "窗口验证", venue: "", matchDate: "2026-10-17",
              matchFormat: "doubles", cameraAngle: "unknown", athleteLabel: "", level: "" },
};

const manifest: ModularRunManifest = {
  schema_version: "modular-run.v1", result_kind: "modular", job_id: job.id,
  plan_id: "plan-one", plan_hash: "hash-one", status: "succeeded", completeness: "partial",
  targets: ["player.detect", "ball.detect"],
  nodes: [
    { node_key: "player.detect", capability_id: "player.detect", status: "cached", node_attempt: 0,
      implementation_id: "player.yolo.v1", counters: { capture_opens: 0, model_executions: 0 },
      artifact: { artifact_id: "artifact-one", artifact_type: "player.observations", schema_version: "1" } },
    { node_key: "ball.detect", capability_id: "ball.detect", status: "failed", node_attempt: 1,
      message: "球模型不可用", error_code: "model_environment", counters: {} },
  ], artifacts: [{ artifact_id: "artifact-one", artifact_type: "player.observations", schema_version: "1" }],
};

afterEach(() => { cleanup(); vi.clearAllMocks(); });

describe("模块任务结果入口", () => {
  it("显示部分结果与缓存，并通过受控入口读取观测，不查询产品报告", async () => {
    vi.mocked(client.getAnalysisJob).mockResolvedValue(job);
    vi.mocked(client.getAnalysisModuleManifest).mockResolvedValue(manifest);
    vi.mocked(client.getAnalysisModuleArtifact).mockResolvedValue({ observations: [{ observation_id: "person-one" }] });
    render(<AnalysisJobPage jobId={job.id} onNavigate={vi.fn()} />);
    expect(await screen.findByText("局部能力分析")).toBeInTheDocument();
    expect(await screen.findByText("部分目标未完成，已保留的产物仍可查看。")).toBeInTheDocument();
    expect(screen.getByText("球模型不可用")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "查看观测产物" }));
    expect(await screen.findByText(/person-one/)).toBeInTheDocument();
    expect(client.getAnalysisModuleArtifact).toHaveBeenCalledWith("artifact-one");
    expect(client.getAnalysisResult).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: /报告/ })).not.toBeInTheDocument();
  });

  it("失联任务保留节点结果并停止产品结果跳转", async () => {
    vi.mocked(client.getAnalysisJob).mockResolvedValue({ ...job, status: "interrupted", canonicalStatus: "interrupted" });
    vi.mocked(client.getAnalysisModuleManifest).mockResolvedValue({ ...manifest, status: "interrupted" });
    render(<AnalysisJobPage jobId={job.id} onNavigate={vi.fn()} />);
    expect(await screen.findByText(/任务失联/)).toBeInTheDocument();
    expect(client.getAnalysisResult).not.toHaveBeenCalled();
  });
});

it("separates completeness, artifact quality and availability, with lazy loading and retries", async () => {
  vi.mocked(client.getAnalysisJob).mockResolvedValue(job);
  vi.mocked(client.getAnalysisModuleManifest).mockRejectedValueOnce(new Error("offline")).mockResolvedValue({ ...manifest, artifact_details: [{ manifest: { ref: manifest.artifacts[0], quality: "no_candidates" }, availability: "location_unavailable" }] });
  render(<AnalysisJobPage jobId={job.id} onNavigate={vi.fn()} />);
  fireEvent.click(await screen.findByRole("button", { name: "重试读取清单" }));
  expect(await screen.findByText(/执行完成，未检测到候选 · 存储暂不可用/)).toBeInTheDocument();
  expect(client.getAnalysisModuleArtifact).not.toHaveBeenCalled();
  vi.mocked(client.getAnalysisModuleArtifact).mockRejectedValueOnce(new Error("missing")).mockResolvedValueOnce({ observations: [] });
  fireEvent.click(screen.getByRole("button", { name: "查看观测产物" }));
  expect(await screen.findByText("观测产物暂时不可读，请检查存储可用性。")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "查看观测产物" }));
  expect(await screen.findByText(/"observations": \[\]/)).toBeInTheDocument();
  expect(client.getAnalysisResult).not.toHaveBeenCalled();
});
