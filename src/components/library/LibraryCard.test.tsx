import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { LibraryItemViewModel } from "../../services/libraryAdapter";
import { LibraryCard } from "./LibraryCard";

afterEach(() => cleanup());
function item(partial: Partial<LibraryItemViewModel>): LibraryItemViewModel {
  return {
    ref: { kind: "upload", sourceId: "video-1" },
    title: "测试素材",
    sourceType: "upload",
    mediaState: "ready",
    availabilityState: "available",
    analysisState: "not_started",
    displayState: "pending",
    analysisHistoryCount: 0,
    ...partial,
  } as LibraryItemViewModel;
}

function openMenu() {
  fireEvent.click(screen.getByLabelText("更多操作"));
}

describe("LibraryCard 分析入口", () => {
  it("未分析的单摄录制显示「开始分析」且触发 onReanalyze", () => {
    const onReanalyze = vi.fn();
    render(
      <LibraryCard
        item={item({
          ref: { kind: "recording", sourceId: "rec-1" },
          sourceType: "recording",
          videoId: "video-rec",
        })}
        onNavigate={vi.fn()}
        onReanalyze={onReanalyze}
      />,
    );
    openMenu();
    const entry = screen.getByText("开始分析");
    expect(entry).toBeTruthy();
    fireEvent.click(entry);
    expect(onReanalyze).toHaveBeenCalledTimes(1);
  });

  it("已分析素材显示「再次分析」", () => {
    render(
      <LibraryCard
        item={item({
          ref: { kind: "sync_recording", sourceId: "sync-1" },
          sourceType: "sync_recording",
          analysisState: "succeeded",
          captureTakeId: "take-9",
        })}
        onNavigate={vi.fn()}
        onReanalyze={vi.fn()}
      />,
    );
    openMenu();
    expect(screen.getByText("再次分析")).toBeTruthy();
  });

  it("素材媒体未就绪（录音中）时不显示分析入口", () => {
    render(
      <LibraryCard
        item={item({
          ref: { kind: "recording", sourceId: "rec-1" },
          sourceType: "recording",
          mediaState: "recording",
          videoId: "video-rec",
        })}
        onNavigate={vi.fn()}
        onReanalyze={vi.fn()}
      />,
    );
    openMenu();
    expect(screen.queryByText("开始分析")).toBeNull();
    expect(screen.queryByText("再次分析")).toBeNull();
  });

  it("单摄录制缺 videoId（不可分析）时不显示分析入口", () => {
    render(
      <LibraryCard
        item={item({
          ref: { kind: "recording", sourceId: "rec-x" },
          sourceType: "recording",
          videoId: undefined,
        })}
        onNavigate={vi.fn()}
        onReanalyze={vi.fn()}
      />,
    );
    openMenu();
    expect(screen.queryByText("开始分析")).toBeNull();
  });
});

describe("LibraryCard 元数据内联编辑（library-card-metadata-editing）", () => {
  it("标题编辑：点击铅笔进入 input，回车保存并触发 onUpdateTitle", () => {
    const onUpdateTitle = vi.fn().mockResolvedValue(undefined);
    const onUpdateDate = vi.fn().mockResolvedValue(undefined);
    render(
      <LibraryCard
        item={item({ ref: { kind: "upload", sourceId: "video-1" }, sourceType: "upload" })}
        onNavigate={vi.fn()}
        onUpdateTitle={onUpdateTitle}
        onUpdateDate={onUpdateDate}
      />,
    );
    const editBtn = screen.getByLabelText("重命名标题");
    fireEvent.click(editBtn);
    const input = screen.getByRole("textbox", { name: "重命名标题" });
    fireEvent.change(input, { target: { value: "自定义名称" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onUpdateTitle).toHaveBeenCalledTimes(1);
    expect(onUpdateTitle).toHaveBeenCalledWith(expect.objectContaining({ ref: { kind: "upload", sourceId: "video-1" } }), "自定义名称");
  });

  it("标题编辑 Esc 取消，不触发保存", () => {
    const onUpdateTitle = vi.fn().mockResolvedValue(undefined);
    render(
      <LibraryCard
        item={item({ ref: { kind: "upload", sourceId: "video-1" }, sourceType: "upload" })}
        onNavigate={vi.fn()}
        onUpdateTitle={onUpdateTitle}
        onUpdateDate={vi.fn().mockResolvedValue(undefined)}
      />,
    );
    fireEvent.click(screen.getByLabelText("重命名标题"));
    const input = screen.getByRole("textbox", { name: "重命名标题" });
    fireEvent.change(input, { target: { value: "不保存" } });
    fireEvent.keyDown(input, { key: "Escape" });
    expect(onUpdateTitle).not.toHaveBeenCalled();
  });

  it("日期编辑：点击进入 date input，选择即保存并触发 onUpdateDate", () => {
    const onUpdateDate = vi.fn().mockResolvedValue(undefined);
    render(
      <LibraryCard
        item={item({
          ref: { kind: "upload", sourceId: "video-1" },
          sourceType: "upload",
          startedAt: "2026-08-20T09:00:00Z",
        })}
        onNavigate={vi.fn()}
        onUpdateTitle={vi.fn().mockResolvedValue(undefined)}
        onUpdateDate={onUpdateDate}
      />,
    );
    fireEvent.click(screen.getByLabelText("修改比赛日期"));
    const dateInput = screen.getByLabelText("修改比赛日期");
    expect(dateInput).toHaveProperty("type", "date");
    fireEvent.change(dateInput, { target: { value: "2026-08-15" } });
    expect(onUpdateDate).toHaveBeenCalledTimes(1);
    expect(onUpdateDate).toHaveBeenCalledWith(expect.anything(), "2026-08-15");
  });

  it("无编辑回调时不显示铅笔入口（upload 无 onUpdateTitle/onUpdateDate）", () => {
    render(
      <LibraryCard
        item={item({ ref: { kind: "upload", sourceId: "video-1" }, sourceType: "upload" })}
        onNavigate={vi.fn()}
      />,
    );
    expect(screen.queryByLabelText("重命名标题")).toBeNull();
    expect(screen.queryByLabelText("修改比赛日期")).toBeNull();
  });

  it("无场次的 recording（无 fieldSessionId）不显示编辑入口（design Q2 决议 B）", () => {
    render(
      <LibraryCard
        item={item({
          ref: { kind: "recording", sourceId: "rec-1" },
          sourceType: "recording",
        })}
        onNavigate={vi.fn()}
        onUpdateTitle={vi.fn().mockResolvedValue(undefined)}
        onUpdateDate={vi.fn().mockResolvedValue(undefined)}
      />,
    );
    expect(screen.queryByLabelText("重命名标题")).toBeNull();
    expect(screen.queryByLabelText("修改比赛日期")).toBeNull();
  });
});