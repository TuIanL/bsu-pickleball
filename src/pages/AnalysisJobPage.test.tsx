import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AnalysisJobSummary } from "../types/report";
import { AnalysisJobPage } from "./AnalysisJobPage";
import * as analysisClient from "../services/analysisClient";

vi.mock("../services/analysisClient", () => ({
  getAnalysisJob: vi.fn(),
  getFusedManifest: vi.fn().mockResolvedValue(null),
  getFusionDiagnostics: vi.fn().mockResolvedValue(null),
  rememberAnalysisJob: vi.fn(),
  cancelAnalysisJob: vi.fn(),
}));

function makeJob(overrides: Partial<AnalysisJobSummary> = {}): AnalysisJobSummary {
  return {
    id: "job-test",
    status: "processing",
    stage: "frame-sampling",
    progress: 34,
    createdAt: "2026-08-12T00:00:00.000Z",
    updatedAt: "2026-08-12T00:00:00.000Z",
    analysisKind: "single_view",
    analysisMode: "real",
    metadata: {
      fileName: "match.mp4",
      matchTitle: "测试比赛",
      venue: "测试球场",
      matchDate: "2026-08-12",
      matchFormat: "doubles",
      cameraAngle: "baseline",
      athleteLabel: "测试球员",
      level: "大众进阶",
    },
    stages: [
      { id: "upload", label: "视频上传", status: "done", detail: "保存视频和基础比赛信息" },
      { id: "queue", label: "任务排队", status: "done", detail: "等待视觉分析任务执行" },
      { id: "calibration", label: "场地标定", status: "done", detail: "读取或跳过四角手工标定" },
      { id: "video-read", label: "读取视频", status: "done", detail: "读取上传视频元数据和帧流" },
      { id: "frame-sampling", label: "抽帧采样", status: "active", detail: "正在逐帧分析：已处理 412/1200 帧", progress: 40 },
      { id: "detection", label: "目标检测", status: "pending", detail: "运行或跳过人体检测模型" },
      { id: "pose", label: "人体姿态", status: "pending", detail: "运行或跳过 RTMPose26 关键点识别" },
      { id: "tracking", label: "轨迹跟踪", status: "pending", detail: "关联球员移动轨迹" },
      { id: "projection", label: "脚点投影", status: "pending", detail: "映射画面坐标到匹克球场" },
      { id: "metrics", label: "运动指标", status: "pending", detail: "计算移动距离、速度、厨房区停留和热力图" },
      { id: "visualization", label: "可视化输出", status: "pending", detail: "生成可供前端展示的结果引用" },
      { id: "report", label: "报告生成", status: "pending", detail: "生成报告 JSON 并交给前端展示" },
    ],
    ...overrides,
  } as unknown as AnalysisJobSummary;
}

function renderPage(job: AnalysisJobSummary) {
  vi.mocked(analysisClient.getAnalysisJob).mockResolvedValue(job);
  return render(<AnalysisJobPage jobId={job.id} onNavigate={vi.fn()} />);
}

describe("AnalysisJobPage 进度展示", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("processing 任务渲染胶囊 stepper 与当前阶段详情", async () => {
    renderPage(makeJob());
    expect(await screen.findByTestId("job-stage-stepper")).toBeTruthy();
    // 当前 active 阶段出现在 stepper 胶囊与详情行（至少两处）
    expect(screen.getAllByText("抽帧采样").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText(/正在逐帧分析：已处理 412\/1200 帧/)).toBeTruthy();
    // 整体百分比
    expect(screen.getByText("34%")).toBeTruthy();
  });

  it("queued 任务无 active 阶段时显示等待文案", async () => {
    const job = makeJob({
      status: "queued",
      stage: "queue",
      progress: 8,
      stages: [
        { id: "upload", label: "视频上传", status: "done", detail: "保存视频和基础比赛信息" },
        { id: "queue", label: "任务排队", status: "pending", detail: "等待视觉分析任务执行" },
      ],
    });
    renderPage(job);
    expect(await screen.findByTestId("job-stage-stepper")).toBeTruthy();
    expect(screen.getByText(/等待视觉分析任务执行/)).toBeTruthy();
  });

  it("completed 任务显示阶段完成摘要并把结果入口置顶", async () => {
    const job = makeJob({
      status: "completed",
      stage: "report",
      progress: 100,
      stages: makeJob().stages.map((stage) => ({
        ...stage,
        status: stage.status === "pending" || stage.status === "active" ? "done" : stage.status,
        progress: 100,
      })),
    });
    renderPage(job);
    expect(await screen.findByText(/12\/12 阶段完成/)).toBeTruthy();
    expect(screen.getByRole("button", { name: /打开视频分析/ })).toBeTruthy();
    expect(screen.queryByTestId("job-stage-stepper")).toBeNull();
  });

  it("failed 任务显示失败阶段摘要与重新上传入口", async () => {
    const job = makeJob({
      status: "failed",
      stage: "detection",
      progress: 42,
      publicErrorMessage: "模型加载失败",
      stages: makeJob().stages.map((stage) =>
        stage.id === "detection" ? { ...stage, status: "failed", detail: "模型文件不存在" } : stage,
      ),
    });
    renderPage(job);
    expect(await screen.findByText(/失败阶段：目标检测/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "重新上传" })).toBeTruthy();
    expect(screen.queryByTestId("job-stage-stepper")).toBeNull();
  });
});
