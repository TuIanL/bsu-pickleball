import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { LibraryCover, coverLayout } from "./LibraryCover";
import { FRAME_CACHE_LIMIT, getCachedFrame, setCachedFrame } from "./CoverVideo";

describe("coverLayout（按来源分派）", () => {
  it("upload 无封面 → 单画面且 src 为空", () => {
    expect(coverLayout({ sourceType: "upload", cameraSetup: "single" })).toEqual({ kind: "single", src: undefined });
  });

  it("recording 单摄有 coverVideoUrl → 单画面", () => {
    expect(coverLayout({ sourceType: "recording", cameraSetup: "single", coverVideoUrl: "/v/a/stream" })).toEqual({
      kind: "single",
      src: "/v/a/stream",
    });
  });

  it("双摄两路机位流 → 左右拼接", () => {
    const layout = coverLayout({
      sourceType: "sync_recording",
      cameraSetup: "dual",
      cameraCoverSources: { cam_1: "/v/cam1/stream", cam_2: "/v/cam2/stream" },
    });
    expect(layout).toEqual({ kind: "dual", left: "/v/cam1/stream", right: "/v/cam2/stream" });
  });

  it("双摄仅一路机位流 → 另一路缺省（占位交由渲染层）", () => {
    const layout = coverLayout({
      sourceType: "sync_recording",
      cameraSetup: "dual",
      cameraCoverSources: { cam_1: "/v/cam1/stream" },
    });
    expect(layout).toEqual({ kind: "dual", left: "/v/cam1/stream", right: undefined });
  });

  it("双摄无机位流 → 退回单画面 coverVideoUrl", () => {
    const layout = coverLayout({
      sourceType: "sync_recording",
      cameraSetup: "dual",
      coverVideoUrl: "/v/default/stream",
      cameraCoverSources: {},
    });
    expect(layout).toEqual({ kind: "single", src: "/v/default/stream" });
  });
});

describe("封面帧缓存（会话内 dataURL + LRU）", () => {
  it("写入后可命中读取", () => {
    setCachedFrame("src://test-1", "data:image/jpeg;base64,x");
    expect(getCachedFrame("src://test-1")).toBe("data:image/jpeg;base64,x");
  });

  it("LRU 有界：超限时淘汰最久未用", () => {
    const base = "__lru_bounded__";
    const total = FRAME_CACHE_LIMIT + 10;
    for (let i = 0; i < total; i++) setCachedFrame(`${base}:${i}`, `data:${i}`);
    expect(getCachedFrame(`${base}:0`)).toBeUndefined(); // 最早写入被淘汰
    expect(getCachedFrame(`${base}:${total - 1}`)).toBe(`data:${total - 1}`); // 最近写入仍在
  });
});

describe("LibraryCover 渲染", () => {
  it("双摄封面渲染「双摄」角标", () => {
    render(
      <LibraryCover
        item={{
          sourceType: "sync_recording",
          cameraSetup: "dual",
          cameraCoverSources: { cam_1: "/v/cam1/stream", cam_2: "/v/cam2/stream" },
        }}
      />,
    );
    expect(screen.getByText("双摄")).toBeTruthy();
  });
});