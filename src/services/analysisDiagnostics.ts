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
      body: "可以继续手动拖动四个角点，当前视频和比赛信息不会丢失。",
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
  const reference = response?.reference;
  const breakdown = response?.confidence_breakdown;

  const rejectedByReference = reference?.rejection_reason != null;
  const body =
    status === "ready"
      ? "已填入自动角点，仍可手动拖动修正。"
      : status === "rejected"
        ? rejectedByReference
          ? `自动标定被拒绝：球场线参考支持度不足 (ref=${(reference?.reference_score ?? 0).toFixed(2)})。请手动拖动或调整标定帧。`
          : "检测结果未通过几何校验，请手动拖动或调整标定帧。"
        : "自动模型暂不可用，请继续手动拖动四角。";

  return {
    title: status === "ready"
      ? "自动识别已就绪"
      : status === "rejected"
        ? rejectedByReference ? "球场线参考不足" : "自动识别未通过校验"
        : "自动识别不可用",
    body,
    detailItems: [
      ["后端说明", response?.detail],
      ["模型已配置", mask ? (mask.model_configured ? "是" : "否") : undefined],
      ["模型路径", mask?.model_path],
      ["综合置信度", breakdown ? `${formatPercent(breakdown.combined)} (分割${formatPercent(breakdown.segmentation)} + 几何${formatPercent(breakdown.geometry)} + 参考${formatPercent(breakdown.reference)})` : formatPercent(response?.confidence)],
      ["Mask 置信度", formatPercent(mask?.confidence)],
      ["Mask 面积占比", formatPercent(mask?.mask_area_ratio)],
      ["线段数量", mask?.line_count],
      ["球场线参考分", reference ? `${reference.reference_score.toFixed(2)} · ${reference.supported_lines}/${reference.total_lines} 线支持 · 覆盖 ${(reference.coverage * 100).toFixed(0)}%` : undefined],
      ["参考线详情", reference?.summary],
      ["拒绝原因", reference?.rejection_reason],
      ["Mask 说明", mask?.detail],
      ["选中帧", frame ? `#${frame.frame_index} · ${formatSeconds(frame.timestamp_seconds) ?? "时间未知"}` : undefined],
      ["帧尺寸", frame?.width && frame.height ? `${frame.width} x ${frame.height}` : undefined],
      ["重投影误差", response?.quality ? `${response.quality.reprojection_error.toFixed(3)} ft · ${response.quality.status}` : undefined],
    ],
  };
}
