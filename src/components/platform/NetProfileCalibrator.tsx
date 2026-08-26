import { useEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import { CheckCircle2, Info, Move } from "lucide-react";
import type {
  NetProfile,
  SceneImagePoint,
  ScenePoint3D,
  SceneCalibrationSource,
} from "../../types/metricCourtScene";
import { STANDARD_NET_HEIGHT_FT, buildStandardNetProfile } from "../../types/metricCourtScene";

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
  onCancel: () => void;
  isSubmitting?: boolean;
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

function makeProfile(mode: "standard" | "measured", endpointCm: number, centerCm: number, confirmed: boolean): NetProfile {
  const controls = buildStandardNetProfile(confirmed).control_points.map((point) => {
    const cm = point.id === "center" ? centerCm : endpointCm;
    const world: ScenePoint3D = { ...point.world, z: cm / 30.48 };
    return {
      ...point,
      world,
      provenance: (mode === "standard" ? "manual" : "manual_verified") as SceneCalibrationSource,
      confirmed,
    };
  });
  return {
    profile_type: mode,
    height_source: mode === "standard" ? "standard" : "measured",
    coordinate_units: "feet",
    control_points: controls,
    sampled_top_profile: [],
    post_world_points: [
      { x: -1, y: 22, z: endpointCm / 30.48 },
      { x: 21, y: 22, z: endpointCm / 30.48 },
    ],
  };
}

export function NetProfileCalibrator({
  videoSrc,
  viewId,
  courtOrientation = "identity",
  initial,
  onComplete,
  onCancel,
  isSubmitting = false,
}: NetProfileCalibratorProps) {
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

  const profile = useMemo(() => makeProfile(mode, endpointCm, centerCm, confirmed), [centerCm, confirmed, endpointCm, mode]);
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
    if (!complete || !confirmed || isSubmitting) return;
    onComplete({ profile, annotations, holdoutAnnotations, imageWidth: imageSize.width, imageHeight: imageSize.height, frameIndex });
  };

  return (
    <div className="grid gap-5 lg:grid-cols-[minmax(0,1.35fr)_minmax(260px,0.65fr)]" data-testid={`net-profile-calibrator-${viewId}`}>
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
        <div>
          <div className="text-xs font-bold uppercase tracking-[0.14em] text-[#168A34]">{viewId} · 球网高度模型</div>
          <p className="mt-2 text-sm leading-6 text-slate-500">两路视频使用同一 Canonical Court Frame，点位仍保留各自 image-space 坐标。</p>
        </div>
        <label className="block text-sm font-semibold text-[#14241B]">
          profile 类型
          <select className="field-input mt-1" value={mode} onChange={(event) => setMode(event.target.value as "standard" | "measured")}>
            <option value="standard">标准网高（36 / 34 / 36 英寸）</option>
            <option value="measured">现场实测高度</option>
          </select>
        </label>
        <div className="grid grid-cols-2 gap-3">
          <label className="text-sm font-semibold text-[#14241B]">
            两侧高度（cm）
            <input className="field-input mt-1" min={1} step={0.1} type="number" value={endpointCm.toFixed(2)} onChange={(event) => setEndpointCm(Number(event.target.value))} />
          </label>
          <label className="text-sm font-semibold text-[#14241B]">
            中心高度（cm）
            <input className="field-input mt-1" min={1} step={0.1} type="number" value={centerCm.toFixed(2)} onChange={(event) => setCenterCm(Number(event.target.value))} />
          </label>
        </div>
        <div className="rounded-xl border border-[#DDE9D6] bg-[#F5FAF1] p-3 text-xs leading-5 text-[#416248]">
          <Info size={14} className="mb-1 text-[#168A34]" aria-hidden="true" />
          标准值：两侧 91.44 cm，中心 86.36 cm。后端以英尺存储并在发布时生成采样剖面。蓝色四分之一点会作为 hold-out 回投检查，不参与 profile 拟合。
        </div>
        <label className="flex items-start gap-2 text-sm font-semibold text-[#14241B]">
          <input className="mt-0.5" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} type="checkbox" />
          <span>我已确认三个控制点、两个 hold-out 点和高度 profile，可用于发布场景标定 revision。</span>
        </label>
        <div className="flex justify-end gap-2 pt-2">
          <button className="quiet-button px-3 py-2 text-sm" onClick={onCancel} type="button">上一步</button>
          <button className="green-button px-4 py-2 text-sm disabled:opacity-40" disabled={!complete || !confirmed || isSubmitting} onClick={handleComplete} type="button">
            <CheckCircle2 size={15} aria-hidden="true" /> 完成球网标注（含验证点）
          </button>
        </div>
      </div>
    </div>
  );
}
