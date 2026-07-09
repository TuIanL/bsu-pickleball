import { describe, expect, it } from "vitest";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type { FieldSession, RecordingSession } from "../../types/report";
import { FieldSessionGroupCard } from "./FieldSessionGroupCard";
import { groupRecordingsByFieldSession } from "../../services/recordingGrouping";

function makeFieldSession(id: string): FieldSession {
  return {
    id,
    title: `采集任务-${id}`,
    venue: "北京体育馆",
    court_name: "1号场",
    capture_mode: "practice",
    match_format: "doubles",
    camera_setup: "single",
    status: "planned",
    notes: "",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  };
}

function makeRecording(id: string, fieldSessionId: string | undefined, status: RecordingSession["status"]): RecordingSession {
  return {
    session_id: id,
    camera_id: "cam-1",
    field_session_id: fieldSessionId,
    court_name: "1号场",
    match_format: "doubles",
    camera_angle: "high",
    fps: 30,
    resolution: "1920x1080",
    auto_analyze_after_stop: false,
    status,
    started_at: "2026-02-01T00:00:00Z",
  };
}

const noop = () => {};

describe("FieldSessionGroupCard", () => {
  it("渲染采集任务标题、场地、录制数与展开控件，并复用 RecordingTaskCard", () => {
    const html = renderToStaticMarkup(
      createElement(FieldSessionGroupCard, {
        fieldSession: makeFieldSession("fs-1"),
        recordings: [makeRecording("r1", "fs-1", "completed")],
        onNavigate: noop,
        onRefresh: noop,
        onPlay: noop,
      }),
    );
    expect(html).toContain("采集任务-fs-1");
    expect(html).toContain("北京体育馆");
    expect(html).toContain("1 条");
    expect(html).toContain("录制视频"); // RecordingTaskCard 已被复用
    expect(html).toContain("aria-expanded"); // 展开/收起控件
  });

  it("组内存在录制中任务时显示录制中高亮", () => {
    const html = renderToStaticMarkup(
      createElement(FieldSessionGroupCard, {
        fieldSession: makeFieldSession("fs-1"),
        recordings: [makeRecording("r1", "fs-1", "recording")],
        onNavigate: noop,
        onRefresh: noop,
        onPlay: noop,
      }),
    );
    expect(html).toContain("录制中");
  });

  it("空分组显示暂无录制占位", () => {
    const html = renderToStaticMarkup(
      createElement(FieldSessionGroupCard, {
        fieldSession: makeFieldSession("fs-1"),
        recordings: [],
        onNavigate: noop,
        onRefresh: noop,
        onPlay: noop,
      }),
    );
    expect(html).toContain("暂无录制");
    expect(html).toContain("0 条");
  });

  it("未归类组显示「未归类录制」标题", () => {
    const html = renderToStaticMarkup(
      createElement(FieldSessionGroupCard, {
        fieldSession: null,
        recordings: [makeRecording("r-orphan", undefined, "completed")],
        onNavigate: noop,
        onRefresh: noop,
        onPlay: noop,
      }),
    );
    expect(html).toContain("未归类录制");
    expect(html).toContain("录制视频");
  });

  it("模拟录制 Tab 分组列表：未归类组置底且任务条复用", () => {
    const fsOld = makeFieldSession("fs-old");
    const fsNew = makeFieldSession("fs-new");
    const groups = groupRecordingsByFieldSession(
      [fsOld, fsNew],
      [
        makeRecording("r-old", "fs-old", "completed"),
        makeRecording("r-new", "fs-new", "completed"),
        makeRecording("r-orphan", undefined, "completed"),
      ],
    );
    const listHtml = groups
      .map((group) =>
        renderToStaticMarkup(
          createElement(FieldSessionGroupCard, {
            fieldSession: group.fieldSession,
            recordings: group.recordings,
            onNavigate: noop,
            onRefresh: noop,
            onPlay: noop,
          }),
        ),
      )
      .join("");
    const uncategorizedIndex = listHtml.indexOf("未归类录制");
    const fsOldIndex = listHtml.indexOf("采集任务-fs-old");
    const fsNewIndex = listHtml.indexOf("采集任务-fs-new");
    expect(uncategorizedIndex).toBeGreaterThan(fsOldIndex);
    expect(uncategorizedIndex).toBeGreaterThan(fsNewIndex);
    expect(listHtml).toContain("录制视频"); // RecordingTaskCard 在分组内复用
  });
});
