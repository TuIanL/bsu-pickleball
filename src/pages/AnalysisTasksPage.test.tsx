import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AnalysisJobSummary, SyncRecordingSession } from "../types/report";
import { AnalysisTaskCard, SyncRecordingTaskCard } from "./AnalysisTasksPage";

function makeSession(overrides: Partial<SyncRecordingSession> = {}): SyncRecordingSession {
  return {
    session_id: "sync_1",
    status: "completed",
    camera_slots: {},
    segments: [],
    output_dir: "/tmp/out",
    associated_video_paths: [],
    court_name: "测试球场",
    match_format: "doubles",
    fps: 60,
    resolution: "1920x1080",
    auto_analyze_after_stop: false,
    total_restarts: 0,
    registered_video_ids: { cam_1: "v1", cam_2: "v2" },
    merge_status: "completed",
    capture_take_id: "ct_1",
    ...overrides,
  };
}

function makeJob(id: string, kind = "multiview"): AnalysisJobSummary {
  return {
    id,
    status: "completed",
    stages: [],
    progress: 100,
    createdAt: "2026-08-08T00:00:00.000Z",
    updatedAt: "2026-08-08T00:00:00.000Z",
    analysisKind: kind,
    analysisMode: "real",
    metadata: {
      fileName: "dual.mp4",
      matchTitle: "测试比赛",
      venue: "测试球场",
      matchDate: "2026-08-08",
      matchFormat: "doubles",
      cameraAngle: "baseline",
      athleteLabel: "球采集",
      level: "大众进阶",
    },
  } as unknown as AnalysisJobSummary;
}

function renderCard(props: {
  analysisJobs?: AnalysisJobSummary[];
  deletingAnalysis?: boolean;
  onDeleteAnalysis?: (sessionId: string) => void;
  onDeleteJob?: (job: AnalysisJobSummary) => void;
  onNavigate?: (path: string) => void;
}) {
  const onDeleteAnalysis = props.onDeleteAnalysis ?? vi.fn();
  const onDeleteJob = props.onDeleteJob ?? vi.fn();
  const onNavigate = props.onNavigate ?? vi.fn();
  const utils = render(
    <SyncRecordingTaskCard
      session={makeSession()}
      analysisJobs={props.analysisJobs}
      deletingAnalysis={props.deletingAnalysis ?? false}
      onDeleteAnalysis={onDeleteAnalysis}
      onDeleteJob={onDeleteJob}
      onDelete={vi.fn()}
      onNavigate={onNavigate}
      onPlay={vi.fn()}
      onMerge={vi.fn()}
    />,
  );
  return { onDeleteAnalysis, onDeleteJob, onNavigate, ...utils };
}

describe("SyncRecordingTaskCard 双摄分析任务", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("有分析任务时显示录制级清除入口", () => {
    renderCard({ analysisJobs: [makeJob("job-parent")] });
    expect(screen.getByRole("button", { name: /清除本录制全部分析/ })).toBeTruthy();
  });

  it("无分析任务时不显示录制级清除入口", () => {
    renderCard({ analysisJobs: [] });
    expect(screen.queryByRole("button", { name: /清除本录制全部分析/ })).toBeNull();
  });

  it("点击清除入口回调 onDeleteAnalysis 并保留 session id", () => {
    const { onDeleteAnalysis } = renderCard({ analysisJobs: [makeJob("job-parent")] });
    fireEvent.click(screen.getByRole("button", { name: /清除本录制全部分析/ }));
    expect(onDeleteAnalysis).toHaveBeenCalledWith("sync_1");
  });

  it("删除中禁用按钮", () => {
    renderCard({ analysisJobs: [makeJob("job-parent")], deletingAnalysis: true });
    const button = screen.getByRole("button", { name: /清除分析中/ });
    expect((button as HTMLButtonElement).disabled).toBe(true);
  });

  it("同一 Parent 存在历史任务时默认显示最新任务并可展开历史", () => {
    const current = makeJob("job-new", "multiview");
    const history = makeJob("job-old", "multiview");
    current.updatedAt = "2026-08-10T12:00:00.000Z";
    history.updatedAt = "2026-08-10T11:00:00.000Z";

    renderCard({ analysisJobs: [history, current] });

    expect(screen.getByText("job-new")).toBeTruthy();
    expect(screen.queryByText("job-old")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /历史 1 个/ }));
    expect(screen.getByText("job-old")).toBeTruthy();
  });

  it("任务级删除绑定当前任务的 job id", () => {
    const job = makeJob("job-specific");
    const { onDeleteJob } = renderCard({ analysisJobs: [job] });

    fireEvent.click(screen.getByRole("button", { name: "删除此任务" }));

    expect(onDeleteJob).toHaveBeenCalledWith(job);
  });

  it("双摄任务入口携带来源和 session 上下文", () => {
    const job = makeJob("job-context");
    const { onNavigate } = renderCard({ analysisJobs: [job] });

    fireEvent.click(screen.getByRole("button", { name: "查看双摄分析报告" }));
    expect(onNavigate).toHaveBeenCalledWith(
      "/analysis/job-context/vision?taskSource=sync_recording&taskSession=sync_1",
    );
  });

  it("外接盘未挂载时提示具体挂载动作而非通用文案", () => {
    render(
      <SyncRecordingTaskCard
        session={makeSession({
          storage_root: "/Volumes/Elements/项目/匹克球/视频录制",
          video_availability: { cam_1: "unavailable", cam_2: "unavailable" },
        })}
        analysisJobs={[]}
        onDeleteAnalysis={vi.fn()}
        onDeleteJob={vi.fn()}
        onDelete={vi.fn()}
        onNavigate={vi.fn()}
        onPlay={vi.fn()}
        onMerge={vi.fn()}
      />,
    );
    expect(screen.getByText("外接盘 Elements 未挂载：请挂载外接盘后刷新页面")).toBeTruthy();
  });

  it("非外接盘路径不可访问时保留通用文案", () => {
    render(
      <SyncRecordingTaskCard
        session={makeSession({
          video_availability: { cam_1: "unavailable", cam_2: "unavailable" },
        })}
        analysisJobs={[]}
        onDeleteAnalysis={vi.fn()}
        onDeleteJob={vi.fn()}
        onDelete={vi.fn()}
        onNavigate={vi.fn()}
        onPlay={vi.fn()}
        onMerge={vi.fn()}
      />,
    );
    expect(screen.getByText("视频存储位置暂不可访问，恢复后请刷新")).toBeTruthy();
  });
});

describe("AnalysisTaskCard 列表卡进度区", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  function makeTaskJob(overrides: Partial<AnalysisJobSummary> = {}): AnalysisJobSummary {
    return {
      id: "job-card",
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
        { id: "upload", label: "视频上传", status: "done", detail: "d" },
        { id: "queue", label: "任务排队", status: "done", detail: "d" },
        { id: "frame-sampling", label: "抽帧采样", status: "active", detail: "正在逐帧分析", progress: 40 },
        { id: "detection", label: "目标检测", status: "pending", detail: "d" },
      ],
      ...overrides,
    } as unknown as AnalysisJobSummary;
  }

  function renderTaskCard(job: AnalysisJobSummary) {
    return render(
      <AnalysisTaskCard
        job={job}
        onCancel={vi.fn()}
        onDelete={vi.fn()}
        onNavigate={vi.fn()}
        onToggleSelected={vi.fn()}
      />,
    );
  }

  it("processing 任务显示百分比、当前阶段名与 compact stepper", () => {
    renderTaskCard(makeTaskJob());
    expect(screen.getByText("34%")).toBeTruthy();
    expect(screen.getByText("抽帧采样")).toBeTruthy();
    expect(screen.getAllByTestId("stage-dot").length).toBeGreaterThan(0);
    expect(screen.queryAllByTestId("stage-capsule")).toHaveLength(0);
  });

  it("failed 任务不显示进度条，以错误摘要为主", () => {
    const job = makeTaskJob({
      status: "failed",
      stage: "detection",
      progress: 42,
      publicErrorMessage: "模型加载失败",
      stages: makeTaskJob().stages.map((stage) =>
        stage.id === "detection" ? { ...stage, status: "failed" } : stage,
      ),
    });
    renderTaskCard(job);
    expect(screen.queryByTestId("job-stage-stepper")).toBeNull();
    expect(screen.queryByText("42%")).toBeNull();
    expect(screen.getByText(/模型加载失败/)).toBeTruthy();
  });

  it("interrupted 任务显示任务失联和重新分析入口，不显示分析中进度条", () => {
    const job = makeTaskJob({
      status: "interrupted",
      progress: 42,
      workerHeartbeatAt: "2026-08-12T01:00:00.000Z",
      publicErrorMessage: "Worker 在规定时间内没有心跳",
    });
    const onNavigate = vi.fn();
    render(
      <AnalysisTaskCard
        job={job}
        onCancel={vi.fn()}
        onDelete={vi.fn()}
        onNavigate={onNavigate}
        onToggleSelected={vi.fn()}
      />,
    );
    expect(screen.getByText("任务失联")).toBeTruthy();
    expect(screen.getByText(/Worker 在规定时间内没有心跳/)).toBeTruthy();
    expect(screen.queryByText("42%")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "重新分析" }));
    expect(onNavigate).toHaveBeenCalledWith("/analysis/new");
    expect(screen.queryByRole("button", { name: "取消任务" })).toBeNull();
  });
});
