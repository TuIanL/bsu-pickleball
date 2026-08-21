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