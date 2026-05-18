import type { AnalysisApiError } from "./analysisClient";
import type { AutomaticCalibrationResponse } from "../types/report";

export type DiagnosticNotice = {
  body: string;
  detailItems?: Array<[string, string | number | undefined | null]>;
  title: string;
};

export type AutomaticCalibrationUiStatus =
  | "idle"
  | "uploading"
  | "detecting"
  | "ready"
  | "unavailable"
  | "rejected"
  | "error";

export function formatPercent(value?: number | null) {
  return typeof value === "number" && Number.isFinite(value) ? `${(value * 100).toFixed(0)}%` : undefined;
}

export function formatSeconds(value?: number | null) {
  return typeof value === "number" && Number.isFinite(value) ? `${value.toFixed(2)}s` : undefined;
}

export function errorToNotice(
  title: string,
  fallbackBody: string,
  error: unknown,
  isAnalysisApiError: (error: unknown) => error is AnalysisApiError
): DiagnosticNotice {
  if (isAnalysisApiError(error)) {
    return {
      title,
      body: fallbackBody,
      detailItems: [
        ["接口", error.path],
        ["状态", error.isNetworkError ? "网络请求失败" : error.status ? `${error.status} ${error.statusText ?? ""}`.trim() : undefined],
        ["后端信息", error.backendDetail],
        ["网络信息", error.causeMessage],
      ],
    };
  }

  return {
    title,
    body: fallbackBody,
    detailItems: [["错误信息", error instanceof Error ? error.message : String(error)]],
  };
}

export function automaticCalibrationNotice(
  response: AutomaticCalibrationResponse | null,
  status: AutomaticCalibrationUiStatus,
  error: AnalysisApiError | null
): DiagnosticNotice | null {
  if (status === "idle") {
    return null;
  }
  if (status === "uploading" || status === "detecting") {
    return {
      title: "自动标定准备中",
      body: "正在上传视频或请求后端模型建议。",
    };
  }
  if (status === "error") {
    return {
      title: "自动识别请求失败",
      body: "可以继续手动点选四个角点，当前视频和比赛信息不会丢失。",
      detailItems: [
        ["接口", error?.path],
        ["状态", error?.isNetworkError ? "网络请求失败" : error?.status ? `${error.status} ${error.statusText ?? ""}`.trim() : undefined],
        ["后端信息", error?.backendDetail],
        ["网络信息", error?.causeMessage],
      ],
    };
  }

  const frame = response?.selected_frame;
  const mask = response?.mask;
  const body =
    status === "ready"
      ? "已填入自动角点，仍可手动重新点选修正。"
      : status === "rejected"
        ? "检测结果未通过几何校验，请手动点选或调整标定帧。"
        : "自动模型暂不可用，请继续手动点选四角。";

  return {
    title: status === "ready" ? "自动识别已就绪" : status === "rejected" ? "自动识别未通过校验" : "自动识别不可用",
    body,
    detailItems: [
      ["后端说明", response?.detail],
      ["模型已配置", mask ? (mask.model_configured ? "是" : "否") : undefined],
      ["模型路径", mask?.model_path],
      ["整体置信度", formatPercent(response?.confidence)],
      ["Mask 置信度", formatPercent(mask?.confidence)],
      ["Mask 面积占比", formatPercent(mask?.mask_area_ratio)],
      ["线段数量", mask?.line_count],
      ["Mask 说明", mask?.detail],
      ["选中帧", frame ? `#${frame.frame_index} · ${formatSeconds(frame.timestamp_seconds) ?? "时间未知"}` : undefined],
      ["帧尺寸", frame?.width && frame.height ? `${frame.width} x ${frame.height}` : undefined],
      ["重投影误差", response?.quality ? `${response.quality.reprojection_error.toFixed(3)} ft · ${response.quality.status}` : undefined],
    ],
  };
}
