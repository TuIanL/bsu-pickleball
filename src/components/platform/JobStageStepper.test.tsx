import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { AnalysisStage } from "../../types/report";
import { JobStageStepper } from "./JobStageStepper";

function makeStages(overrides: Array<Partial<AnalysisStage> | undefined> = []): AnalysisStage[] {
  const base: AnalysisStage[] = [
    { id: "upload", label: "视频上传", status: "done", detail: "保存视频和基础比赛信息" },
    { id: "queue", label: "任务排队", status: "done", detail: "等待视觉分析任务执行" },
    { id: "frame-sampling", label: "抽帧采样", status: "active", detail: "正在逐帧分析：已处理 412/1200 帧" },
    { id: "detection", label: "目标检测", status: "pending", detail: "运行或跳过人体检测模型" },
    { id: "report", label: "报告生成", status: "pending", detail: "生成报告 JSON 并交给前端展示" },
  ];
  return base.map((stage, index) => (overrides[index] ? { ...stage, ...overrides[index] } : stage));
}

describe("JobStageStepper", () => {
  afterEach(() => {
    cleanup();
  });

  it("渲染胶囊节点并标注每个阶段状态", () => {
    render(<JobStageStepper stages={makeStages()} />);
    const capsules = screen.getAllByTestId("stage-capsule");
    expect(capsules).toHaveLength(5);
    expect(capsules[0].dataset.stageStatus).toBe("done");
    expect(capsules[2].dataset.stageStatus).toBe("active");
    expect(capsules[3].dataset.stageStatus).toBe("pending");
  });

  it("高亮当前 active 阶段", () => {
    render(<JobStageStepper stages={makeStages()} />);
    const active = screen.getByText("抽帧采样").closest("[data-stage-active]");
    expect(active?.getAttribute("data-stage-active")).toBe("true");
    expect(screen.getByText("视频上传").closest("[data-stage-active]")).toBeNull();
  });

  it("失败阶段优先于 active 被聚焦", () => {
    const stages = makeStages([
      undefined,
      undefined,
      { status: "failed", detail: "抽帧失败" },
      { status: "active", detail: "处理中" },
    ]);
    render(<JobStageStepper stages={stages} />);
    const failed = screen.getByText("抽帧采样").closest("[data-stage-active]");
    expect(failed?.getAttribute("data-stage-active")).toBe("true");
  });

  it("compact 模式只渲染状态圆点", () => {
    render(<JobStageStepper compact stages={makeStages()} />);
    expect(screen.queryAllByTestId("stage-capsule")).toHaveLength(0);
    const dots = screen.getAllByTestId("stage-dot");
    expect(dots).toHaveLength(5);
    expect(dots[2].dataset.stageStatus).toBe("active");
  });

  it("无目标阶段（全 done / pending）时正常渲染", () => {
    const stages = makeStages([
      { status: "done" },
      { status: "skipped" },
      { status: "pending" },
      { status: "pending" },
      { status: "pending" },
    ]);
    const { container } = render(<JobStageStepper stages={stages} />);
    expect(screen.getAllByTestId("stage-capsule")).toHaveLength(5);
    expect(container.querySelector('[data-stage-active="true"]')).toBeNull();
  });
});
