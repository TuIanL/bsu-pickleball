import { useEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import { CheckCircle2, Info, Move } from "lucide-react";
import type { NetProfile, SceneImagePoint } from "../../types/metricCourtScene";
import { STANDARD_NET_HEIGHT_FT, buildNetProfile, buildStandardNetProfile } from "../../types/metricCourtScene";

const CONTROL_ORDER = [
  { id: "left", label: "球网左端", x: 0 },
  { id: "center", label: "球网中心", x: 10 },
  { id: "right", label: "球网右端", x: 20 },
] as const;

/**
 * Hold-out points are deliberately not part of the three points used to fit
 * the net profile. They are independent image observations used by the
 * backend to check whether the refined camera generalises away from its
 * fitting points.
 */
export const HOLDOUT_ORDER = [
  { id: "holdout_left_quarter", label: "左四分之一点", x: 5 },
  { id: "holdout_right_quarter", label: "右四分之一点", x: 15 },
] as const;

export interface NetAnnotationDraft {
  profile: NetProfile;
  annotations: Record<string, SceneImagePoint>;
  holdoutAnnotations?: Record<string, SceneImagePoint>;
  imageWidth: number;
  imageHeight: number;
  frameIndex: number | null;
}

export interface NetProfileCalibratorProps {
  videoSrc: string;
  viewId: string;
  courtOrientation?: "identity" | "rotate_180" | "mirror_x" | "mirror_y";
  initial?: NetAnnotationDraft | null;
  onComplete: (draft: NetAnnotationDraft) => void;
  /** 嵌入模式下由外层统一提供导航，可省略 */
  onCancel?: () => void;
  isSubmitting?: boolean;
  /**
   * 呈现模式。`standalone`（默认）为完整双列卡片；`embedded` 用于双摄向导内两路并排——
   * 强制单列并默认隐藏高度参数面板（高度由向导页统一持有，两路共用一份）。
   */
  variant?: "standalone" | "embedded";
  /** 显式控制高度参数面板显隐；未指定时跟随 `variant` */
  hideProfilePanel?: boolean;
}

const DEFAULT_IMAGE_SIZE = { width: 1280, height: 720 };

function defaultAnnotations(width: number, height: number): Record<string, SceneImagePoint> {
  return {
    left: { x: width * 0.2, y: height * 0.5 },
    center: { x: width * 0.5, y: height * 0.46 },
    right: { x: width * 0.8, y: height * 0.5 },
  };
}

function defaultHoldoutAnnotations(width: number, height: number): Record<string, SceneImagePoint> {
  return {
    holdout_left_quarter: { x: width * 0.35, y: height * 0.485 },
    holdout_right_quarter: { x: width * 0.65, y: height * 0.485 },
  };
}

/** Match backend sample_net_top_profile() for the hold-out world x positions. */
export function estimateNetProfileHeight(profile: NetProfile, x: number): number {
  const controls = [...profile.control_points].sort((first, second) => first.world.x - second.world.x);
  if (controls.length === 0) return 0;
  if (controls.length === 1) return controls[0].world.z;

  if (controls.length === 3) {
    return controls.reduce((result, control, index) => {
      const basis = controls.reduce((product, other, otherIndex) => {
        if (index === otherIndex) return product;
        return product * ((x - other.world.x) / (control.world.x - other.world.x));
      }, 1);
      return result + control.world.z * basis;
    }, 0);
  }

  for (let index = 0; index < controls.length - 1; index += 1) {
    const first = controls[index];
    const second = controls[index + 1];
    if (first.world.x <= x && x <= second.world.x) {
      const ratio = (x - first.world.x) / Math.max(second.world.x - first.world.x, 1e-9);
      return first.world.z + ratio * (second.world.z - first.world.z);
    }
  }
  return x < controls[0].world.x ? controls[0].world.z : controls[controls.length - 1].world.z;
}

function pointToPercent(point: SceneImagePoint, width: number, height: number): SceneImagePoint {
  return { x: (point.x / Math.max(width, 1)) * 100, y: (point.y / Math.max(height, 1)) * 100 };
}

export interface NetProfileSettingsValue {
  mode: "standard" | "measured";
  endpointCm: number;
  centerCm: number;
  confirmed: boolean;
}

export interface NetProfileSettingsProps {
  value: NetProfileSettingsValue;
  onChange: (next: NetProfileSettingsValue) => void;
  /** 面板标题；单摄流程传入「<viewId> · 球网高度模型」 */
  heading?: string;
  /** 是否渲染确认勾选（嵌入模式下由向导页统一确认时传 false） */
  showConfirm?: boolean;
}

/**
 * 球网高度参数面板。抽成独立组件是为了让双摄向导把高度收敛为**一份共享**取值：
 * 同一张球网只有一个高度模型，两路标注器只贡献各自的 image-space 点位。
 */
export function NetProfileSettings({
  value,
  onChange,
  heading = "球网高度模型",
  showConfirm = true,
}: NetProfileSettingsProps) {
  return (
    <div className="space-y-4">
      <div>
        <div className="text-xs font-bold uppercase tracking-[0.14em] text-[var(--ui-brand-deep)]">{heading}</div>
        <p className="mt-2 text-sm leading-6 text-slate-500">两路视频使用同一 Canonical Court Frame，点位仍保留各自 image-space 坐标。</p>
      </div>
      <label className="block text-sm font-semibold text-[var(--ui-ink)]">
        profile 类型
        <select
          className="field-input mt-1"
          value={value.mode}
          onChange={(event) => onChange({ ...value, mode: event.target.value as "standard" | "measured" })}
        >
          <option value="standard">标准网高（36 / 34 / 36 英寸）</option>
          <option value="measured">现场实测高度</option>
        </select>
      </label>
      <div className="grid grid-cols-2 gap-3">
        <label className="text-sm font-semibold text-[var(--ui-ink)]">
          两侧高度（cm）
          <input
            className="field-input mt-1"
            min={1}
            onChange={(event) => onChange({ ...value, endpointCm: Number(event.target.value) })}
            step={0.1}
            type="number"
            value={value.endpointCm.toFixed(2)}
          />
        </label>
        <label className="text-sm font-semibold text-[var(--ui-ink)]">
          中心高度（cm）
          <input
            className="field-input mt-1"
            min={1}
            onChange={(event) => onChange({ ...value, centerCm: Number(event.target.value) })}
            step={0.1}
            type="number"
            value={value.centerCm.toFixed(2)}
          />
        </label>
      </div>
      <div className="rounded-xl border border-[var(--ui-border)] bg-[var(--ui-surface-soft)] p-3 text-xs leading-5 text-[#416248]">
        <Info size={14} className="mb-1 text-[var(--ui-brand-deep)]" aria-hidden="true" />
        标准值：两侧 91.44 cm，中心 86.36 cm。后端以英尺存储并在发布时生成采样剖面。蓝色四分之一点会作为 hold-out 回投检查，不参与 profile 拟合。
      </div>
      {showConfirm ? (
        <label className="flex items-start gap-2 text-sm font-semibold text-[var(--ui-ink)]">
          <input
            className="mt-0.5"
            checked={value.confirmed}
            onChange={(event) => onChange({ ...value, confirmed: event.target.checked })}
            type="checkbox"
          />
          <span>我已确认三个控制点、两个 hold-out 点和高度 profile，可用于发布场景标定 revision。</span>
        </label>
      ) : null}
    </div>
  );
}

export function NetProfileCalibrator({
  videoSrc,
  viewId,
  courtOrientation = "identity",
  initial,
  onComplete,
  onCancel,
  isSubmitting = false,
  variant = "standalone",
  hideProfilePanel,
}: NetProfileCalibratorProps) {
  const embedded = variant === "embedded";
  const panelHidden = hideProfilePanel ?? embedded;
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const overlayRef = useRef<SVGSVGElement | null>(null);
  const dragRef = useRef<{ layer: "net" | "holdout"; id: string } | null>(null);
  const usingDefaultAnnotations = useRef(!initial?.annotations);
  const usingDefaultHoldoutAnnotations = useRef(!initial?.holdoutAnnotations);
  const [imageSize, setImageSize] = useState(initial ? {
    width: initial.imageWidth,
    height: initial.imageHeight,
  } : DEFAULT_IMAGE_SIZE);
  const [annotations, setAnnotations] = useState<Record<string, SceneImagePoint>>(
    initial?.annotations ?? defaultAnnotations(imageSize.width, imageSize.height),
  );
  const [holdoutAnnotations, setHoldoutAnnotations] = useState<Record<string, SceneImagePoint>>(
    initial?.holdoutAnnotations ?? defaultHoldoutAnnotations(imageSize.width, imageSize.height),
  );
  const [holdoutTouched, setHoldoutTouched] = useState<Record<string, boolean>>(() => Object.fromEntries(
    HOLDOUT_ORDER.map((control) => [control.id, Boolean(initial?.holdoutAnnotations?.[control.id])]),
  ));
  const initialProfile = initial?.profile ?? buildStandardNetProfile();
  const [mode, setMode] = useState<"standard" | "measured">(initialProfile.profile_type);
  const [endpointCm, setEndpointCm] = useState(() => (initialProfile.control_points[0]?.world.z ?? STANDARD_NET_HEIGHT_FT.endpoint) * 30.48);
  const [centerCm, setCenterCm] = useState(() => (initialProfile.control_points[1]?.world.z ?? STANDARD_NET_HEIGHT_FT.center) * 30.48);
  const [confirmed, setConfirmed] = useState(() => initialProfile.control_points.length === 3 && initialProfile.control_points.every((point) => point.confirmed));
  const [frameIndex, setFrameIndex] = useState<number | null>(initial?.frameIndex ?? null);
  const displayOrder = useMemo(() => {
    const flipsCanonicalX = courtOrientation === "rotate_180" || courtOrientation === "mirror_x";
    return flipsCanonicalX ? [...CONTROL_ORDER].reverse() : CONTROL_ORDER;
  }, [courtOrientation]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    const syncSize = () => {
      if (video.videoWidth > 0 && video.videoHeight > 0) {
        setImageSize({ width: video.videoWidth, height: video.videoHeight });
        if (usingDefaultAnnotations.current) {
          setAnnotations(defaultAnnotations(video.videoWidth, video.videoHeight));
        }
        if (usingDefaultHoldoutAnnotations.current) {
          setHoldoutAnnotations(defaultHoldoutAnnotations(video.videoWidth, video.videoHeight));
        }
      }
    };
    video.addEventListener("loadedmetadata", syncSize);
    syncSize();
    return () => video.removeEventListener("loadedmetadata", syncSize);
  }, [videoSrc]);

  useEffect(() => {
    const move = (event: PointerEvent) => {
      const id = dragRef.current;
      const svg = overlayRef.current;
      if (!id || !svg) return;
      const rect = svg.getBoundingClientRect();
      const x = Math.max(0, Math.min(100, ((event.clientX - rect.left) / Math.max(rect.width, 1)) * 100));
      const y = Math.max(0, Math.min(100, ((event.clientY - rect.top) / Math.max(rect.height, 1)) * 100));
      const point = { x: (x / 100) * imageSize.width, y: (y / 100) * imageSize.height };
      if (id.layer === "net") {
        setAnnotations((current) => ({ ...current, [id.id]: point }));
      } else {
        setHoldoutAnnotations((current) => ({ ...current, [id.id]: point }));
      }
    };
    const stop = () => { dragRef.current = null; };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", stop);
    return () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", stop);
    };
  }, [imageSize.height, imageSize.width]);

  const profile = useMemo(() => buildNetProfile(mode, endpointCm, centerCm, confirmed), [centerCm, confirmed, endpointCm, mode]);
  const complete = [...CONTROL_ORDER, ...HOLDOUT_ORDER].every((control) => {
    const point = (control.id.startsWith("holdout_") ? holdoutAnnotations : annotations)[control.id];
    return point && Number.isFinite(point.x) && Number.isFinite(point.y);
  }) && HOLDOUT_ORDER.every((control) => holdoutTouched[control.id]);

  const handlePointerDown = (event: ReactPointerEvent<SVGCircleElement>, layer: "net" | "holdout", id: string) => {
    event.preventDefault();
    if (layer === "net") usingDefaultAnnotations.current = false;
    else {
      usingDefaultHoldoutAnnotations.current = false;
      setHoldoutTouched((current) => ({ ...current, [id]: true }));
    }
    dragRef.current = { layer, id };
  };

  const handleComplete = () => {
    // 嵌入模式下 confirmed 由向导页统一确认（两路共用一份高度模型），组件自身不再拦截。
    if (!complete || isSubmitting || (!embedded && !confirmed)) return;
    onComplete({ profile, annotations, holdoutAnnotations, imageWidth: imageSize.width, imageHeight: imageSize.height, frameIndex });
  };

  return (
    <div
      className={embedded ? "grid gap-4" : "grid gap-5 lg:grid-cols-[minmax(0,1.35fr)_minmax(260px,0.65fr)]"}
      data-testid={`net-profile-calibrator-${viewId}`}
    >
      <div>
        <div className="relative overflow-hidden rounded-2xl border border-[#CFE3D0] bg-black">
          <video
            ref={videoRef}
            className="block aspect-video w-full object-contain"
            controls
            muted
            playsInline
            preload="metadata"
            src={videoSrc}
            onTimeUpdate={(event) => {
              const video = event.currentTarget;
              setFrameIndex(Number.isFinite(video.currentTime) ? Math.max(0, Math.round(video.currentTime * 60)) : null);
            }}
          />
          <svg
            ref={overlayRef}
            aria-label={`${viewId} 球网标注画布`}
            className="absolute inset-0 h-full w-full touch-none"
            viewBox="0 0 100 100"
          >
            <polyline
              fill="none"
              points={displayOrder.map((control) => {
                const point = pointToPercent(annotations[control.id] ?? { x: 0, y: 0 }, imageSize.width, imageSize.height);
                return `${point.x},${point.y}`;
              }).join(" ")}
              stroke="#F59E0B"
              strokeDasharray="1.2 0.8"
              strokeWidth="0.55"
            />
            {displayOrder.map((control) => {
              const point = pointToPercent(annotations[control.id] ?? { x: 0, y: 0 }, imageSize.width, imageSize.height);
              return (
                <g key={control.id}>
                  <circle
                    cx={point.x}
                    cy={point.y}
                    fill="#168A34"
                    r="2.2"
                    stroke="white"
                    strokeWidth="0.6"
                    onPointerDown={(event) => handlePointerDown(event, "net", control.id)}
                  />
                  <text fill="white" fontSize="3.2" fontWeight="700" x={point.x + 2.5} y={point.y - 2}>{control.label}</text>
                </g>
              );
            })}
            {HOLDOUT_ORDER.map((control) => {
              const point = pointToPercent(holdoutAnnotations[control.id] ?? { x: 0, y: 0 }, imageSize.width, imageSize.height);
              return (
                <g key={control.id}>
                  <circle
                    aria-label={control.label}
                    cx={point.x}
                    cy={point.y}
                    fill="#2563EB"
                    r="1.8"
                    stroke="white"
                    strokeWidth="0.6"
                    onPointerDown={(event) => handlePointerDown(event, "holdout", control.id)}
                  />
                  <text fill="white" fontSize="2.6" fontWeight="700" x={point.x + 2.2} y={point.y - 2}>{control.label}</text>
                </g>
              );
            })}
          </svg>
        </div>
        <p className="mt-2 flex items-center gap-1.5 text-xs text-slate-500">
          <Move size={13} aria-hidden="true" /> 拖动三个绿色点贴合球网顶部，再拖动两个蓝色点到四分之一位置；蓝色点不参与拟合，只用于独立质量验证。
        </p>
      </div>

      <div className="space-y-4">
        {panelHidden ? null : (
          <NetProfileSettings
            heading={`${viewId} · 球网高度模型`}
            onChange={(next) => {
              setMode(next.mode);
              setEndpointCm(next.endpointCm);
              setCenterCm(next.centerCm);
              setConfirmed(next.confirmed);
            }}
            value={{ mode, endpointCm, centerCm, confirmed }}
          />
        )}
        <div className="flex justify-end gap-2 pt-2">
          {onCancel && !embedded ? (
            <button className="quiet-button px-3 py-2 text-sm" onClick={onCancel} type="button">上一步</button>
          ) : null}
          <button className="green-button px-4 py-2 text-sm disabled:opacity-40" disabled={!complete || (!embedded && !confirmed) || isSubmitting} onClick={handleComplete} type="button">
            <CheckCircle2 size={15} aria-hidden="true" /> 完成球网标注（含验证点）
          </button>
        </div>
      </div>
    </div>
  );
}
