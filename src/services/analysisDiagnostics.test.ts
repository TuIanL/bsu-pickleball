import { describe, expect, it } from "vitest";
import { AnalysisApiError, isAnalysisApiError } from "./analysisClient";
import { automaticCalibrationNotice, errorToNotice } from "./analysisDiagnostics";
import type { AutomaticCalibrationResponse } from "../types/report";

describe("analysis diagnostics", () => {
  it("turns structured API errors into renderable detail rows", () => {
    const error = new AnalysisApiError({
      backendDetail: "Uploaded video not found",
      isNetworkError: false,
      message: "failed",
      path: "/api/analysis/jobs",
      status: 404,
      statusText: "Not Found",
      url: "http://localhost:8000/api/analysis/jobs",
    });

    const notice = errorToNotice("读取失败", "请检查后端服务。", error, isAnalysisApiError);

    expect(notice.title).toBe("读取失败");
    expect(notice.detailItems).toContainEqual(["接口", "/api/analysis/jobs"]);
    expect(notice.detailItems).toContainEqual(["状态", "404 Not Found"]);
    expect(notice.detailItems).toContainEqual(["后端信息", "Uploaded video not found"]);
  });

  it("keeps automatic calibration diagnostics stable for partial unavailable responses", () => {
    const response = {
      status: "unavailable",
      detail: "Court-line model path is not configured",
      mask: {
        model_configured: false,
        detail: "Court-line model path is not configured",
        line_count: 0,
      },
    } satisfies AutomaticCalibrationResponse;

    const notice = automaticCalibrationNotice(response, "unavailable", null);

    expect(notice?.title).toBe("自动识别不可用");
    expect(notice?.detailItems).toContainEqual(["模型已配置", "否"]);
    expect(notice?.detailItems).toContainEqual(["后端说明", "Court-line model path is not configured"]);
  });

  it("includes frame, confidence, mask, and quality diagnostics for available suggestions", () => {
    const response = {
      status: "available",
      detail: "Automatic court calibration suggestion is ready",
      confidence: 0.82,
      selected_frame: {
        video_id: "video-1",
        frame_index: 42,
        timestamp_seconds: 1.4,
        width: 1280,
        height: 720,
      },
      keypoints: {
        top_left: { x: 10, y: 20 },
        top_right: { x: 200, y: 20 },
        bottom_right: { x: 200, y: 320 },
        bottom_left: { x: 10, y: 320 },
      },
      quality: {
        reprojection_error: 0.1234,
        status: "ok",
      },
      mask: {
        model_configured: true,
        model_path: "model.pt",
        confidence: 0.9,
        mask_area_ratio: 0.12,
        line_count: 4,
        detail: "Court-line mask was converted into ordered court keypoints",
      },
    } satisfies AutomaticCalibrationResponse;

    const notice = automaticCalibrationNotice(response, "ready", null);

    expect(notice?.title).toBe("自动识别已就绪");
    expect(notice?.detailItems).toContainEqual(["综合置信度", "82%"]);
    expect(notice?.detailItems).toContainEqual(["Mask 面积占比", "12%"]);
    expect(notice?.detailItems).toContainEqual(["选中帧", "#42 · 1.40s"]);
    expect(notice?.detailItems).toContainEqual(["重投影误差", "0.123 ft · ok"]);
  });
});
