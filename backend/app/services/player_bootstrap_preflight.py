"""自动候选预检（player bootstrap preflight）—— 有界多窗口的四人候选选取。

分工与边界：

- 本模块**只在所选分析片段内**抽取若干个短窗口做人体检测与短时关联，
  绝不启动完整跟踪器、标定器或指标计算，也绝不写任何分析产物。
- 候选身份（`candidate_id`）是**预检运行内**的稳定标识，**不是**正式 `Player_N`，
  也不等于用户确认的 P 槽位。三者的分离由 `schemas/rally_context.py` 的 v2 契约承载。
- 目标球场成员筛选、球场投影、衣着外观与双机位关联都复用既有实现
  （`PrimaryPlayerSelector` 的球场外扩语义、`ClothingAppearanceExtractor`、
  `multiview.sync.resolve_sync_authority`），本模块负责把它们**编排**进预检。
- 证据不足时返回 `insufficient_candidates` / `unavailable` 并给出诊断码，
  绝不为了凑满人数接纳场外人员，也绝不伪造人物裁剪图。

设计要点（对应 change `simplify-automatic-player-roster-confirmation`）：

1. 中段窗口优先、必要时向前后扩展；总抽帧数有硬预算。
2. 同一输入（视频 + 片段 + 同步/标定 + 模型 + 配置）产生**确定性**的候选顺序，
   并给出可缓存的 `cache_key`。
3. 主参考画面只叠加**该帧实际观测到**的框；每名候选的裁剪图各自带自己的时间与机位。
"""

from __future__ import annotations

import hashlib
import json
import statistics
from dataclasses import dataclass, field
from math import hypot
from typing import Any, Callable, Iterable, Protocol, Sequence

from app.schemas.rally_context import (
    PlayerBootstrapCandidateEvidence,
    PlayerBootstrapCandidateV2,
    PlayerBootstrapQualityDiagnostic,
    PlayerBootstrapReferenceFrame,
)

PREFLIGHT_SCHEMA_VERSION = "player-bootstrap-preflight.v1"

# ── 诊断码（下游与测试按字符串断言，不得随意改写文案）──

DIAG_PREFLIGHT_NO_WINDOWS = "bootstrap_preflight_no_windows"
DIAG_PREFLIGHT_BUDGET_EXHAUSTED = "bootstrap_preflight_budget_exhausted"
DIAG_PREFLIGHT_NO_DETECTIONS = "bootstrap_preflight_no_detections"
DIAG_PREFLIGHT_INSUFFICIENT = "bootstrap_preflight_insufficient_candidates"
DIAG_PREFLIGHT_NO_CALIBRATION = "bootstrap_preflight_calibration_unavailable"
DIAG_PREFLIGHT_NO_SYNC = "bootstrap_preflight_sync_untrusted"
DIAG_PREFLIGHT_NO_APPEARANCE = "bootstrap_preflight_appearance_unavailable"
DIAG_PREFLIGHT_OUT_OF_TARGET_COURT = "bootstrap_preflight_off_target_court"
DIAG_PREFLIGHT_FRAME_UNREADABLE = "bootstrap_preflight_frame_unreadable"
DIAG_PREFLIGHT_STABLE_ORDER = "bootstrap_preflight_deterministic_order"
# 片段范围被媒体长度收窄：如果不收窄，越界的窗口全部读不到帧，预检会静默给出
# "零候选"，而真实原因只是片段请求超出了视频长度 —— 这两者对使用者含义完全不同。
DIAG_PREFLIGHT_CLIP_CLAMPED = "bootstrap_preflight_clip_clamped"
# 某一侧的可靠候选少于该侧配额：刻意**不用对侧候选补位**。候选一旦被用户确认就会冻结成
# 名册快照，错误的第 N 名会静默污染 Team A/B 与所有依赖正式身份的指标；而少一名是使用者
# 可以手工补全的状态。两者对使用者的含义完全不同。
DIAG_PREFLIGHT_SIDE_QUOTA_UNFILLED = "bootstrap_preflight_side_quota_unfilled"

# 目标球场在 canonical 球场帧中的物理 extent（ft），与 court_frame 保持一致。
COURT_WIDTH_FT = 20.0
COURT_LENGTH_FT = 44.0


@dataclass(frozen=True)
class BootstrapPreflightConfig:
    """预检预算与门槛。所有字段都进 `cache_key`，改动即失效缓存。"""

    window_count: int = 5
    window_span_ms: int = 3000
    frames_per_window: int = 4
    max_frames_total: int = 20
    min_hits_for_candidate: int = 2
    association_radius: float = 0.15
    max_association_gap_ms: int = 2500
    min_bbox_width_px: int = 18
    min_bbox_height_px: int = 48
    # 目标球场成员门槛：复用 `primary_player_court_margin_ft` 的外扩语义。
    court_margin_ft: float = 12.0
    target_court_threshold: float = 0.65
    # 人物画面质量：相对画面的最小/最大框面积占比。
    min_box_area_ratio: float = 0.0005
    max_box_area_ratio: float = 0.85
    appearance_enabled: bool = True
    # 双摄门槛：只有 sync_quality ∈ {good, degraded} 才允许跨机位补强。
    trusted_sync_qualities: tuple[str, ...] = ("good", "degraded")
    # 分侧判据（与 `_BootstrapTracklet.inferred_side` 同语义）：canonical y 中位数落在
    # 中线 ± 死区 内视为"侧向未知"。契约测试断言两处常量一致，防止实现漂移。
    court_half_length_ft: float = 22.0
    side_dead_zone_ft: float = 2.0
    # 跨帧同人合并：互斥观测次数下限 + 归一化中心距离上限（刻意小于 association_radius：
    # 合并是不可逆的身份断言，误并会把两名队友并成一名）。
    min_exclusive_observations: int = 2
    merge_radius_normalized: float = 0.08
    # 外观只作否决：双方都有描述子且距离超过该值时**不合并**；缺描述子时不参与判定。
    merge_appearance_max_distance: float = 0.3

    def signature(self) -> str:
        payload = {
            key: (list(value) if isinstance(value, tuple) else value)
            for key, value in self.__dict__.items()
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:16]


class PreflightFrameSource(Protocol):
    """按帧序号读取某机位源帧；读不到返回 None（不抛异常）。"""

    fps: float
    frame_count: int

    def read(self, view_id: str, frame_index: int) -> Any | None: ...


class _Detector(Protocol):
    def detect(self, frame: Any) -> list[Any]: ...


@dataclass(frozen=True)
class PreflightWindow:
    """一个采样窗口。`ordinal` 越小越靠近片段中段。"""

    ordinal: int
    start_ms: int
    end_ms: int
    origin: str  # "mid" | "earlier" | "later"


@dataclass
class _Tracklet:
    view_id: str
    first_timestamp_ms: int
    first_frame_index: int
    first_bbox: list[float]
    first_center: tuple[float, float]
    timestamps_ms: list[int] = field(default_factory=list)
    canonical_timestamps_ms: list[int] = field(default_factory=list)
    bboxes: list[list[float]] = field(default_factory=list)
    confidences: list[float] = field(default_factory=list)
    # 与 timestamps_ms / bboxes 按索引对齐；投影失败时保留 None。
    court_points: list[tuple[float, float] | None] = field(default_factory=list)
    body_qualities: list[float] = field(default_factory=list)
    frame_area_ratios: list[float] = field(default_factory=list)
    appearance_vectors: list[Any] = field(default_factory=list)
    appearance_qualities: list[float] = field(default_factory=list)
    # 该轨迹观测所在帧的像素尺寸：合并判据要在归一化坐标系里比距离，必须与逐帧关联
    # 使用同一套归一化基准；缺尺寸（0）时宁可不合并，也不用猜测的基准去下身份断言。
    frame_width: float = 0.0
    frame_height: float = 0.0

    @property
    def hits(self) -> int:
        return len(self.timestamps_ms)

    @property
    def last_center(self) -> tuple[float, float]:
        return self.first_center

    def center_at(self, index: int) -> tuple[float, float]:
        bbox = self.bboxes[index]
        return ((bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0)

    def best_observation_index(self) -> int:
        """最佳画面：优先人物画面质量，其次置信度，最后**最早**的时刻（确定性）。"""
        if not self.timestamps_ms:
            return -1
        best = 0
        for index in range(1, len(self.timestamps_ms)):
            candidate = (
                self.body_qualities[index] if index < len(self.body_qualities) else 0.0,
                self.confidences[index] if index < len(self.confidences) else 0.0,
            )
            current = (
                self.body_qualities[best] if best < len(self.body_qualities) else 0.0,
                self.confidences[best] if best < len(self.confidences) else 0.0,
            )
            if candidate > current:
                best = index
        return best


@dataclass
class PlayerBootstrapPreflightResult:
    """预检结果（与 v2 契约同形，但只表达"预检跑出了什么"，不含业务接线）。"""

    schema_version: str
    status: str
    unavailable_reason: str | None
    cache_key: str
    candidates: list[PlayerBootstrapCandidateV2] = field(default_factory=list)
    reference_frame: PlayerBootstrapReferenceFrame | None = None
    diagnostics: list[PlayerBootstrapQualityDiagnostic] = field(default_factory=list)
    sampled_frame_count: int = 0
    windows: list[PreflightWindow] = field(default_factory=list)
    multiview_used: bool = False
    # 实际生效的片段范围（已按媒体长度收窄）；调用方据此回填响应字段。
    clip_start_ms: int = 0
    clip_end_ms: int | None = None


# ── 结果缓存：同一输入复用同一次预检，避免页面重开时建议顺序漂移 ──

_PREFLIGHT_CACHE: dict[str, PlayerBootstrapPreflightResult] = {}
_PREFLIGHT_CACHE_LIMIT = 32


def clear_preflight_cache() -> None:
    """清空进程内预检缓存（测试与配置变更时使用）。"""
    _PREFLIGHT_CACHE.clear()


def preflight_cache_size() -> int:
    return len(_PREFLIGHT_CACHE)


def cached_preflight(cache_key: str) -> PlayerBootstrapPreflightResult | None:
    """让服务层在加载检测模型前复用已完成的预检。"""
    return _PREFLIGHT_CACHE.get(cache_key) if cache_key else None


def _remember(result: PlayerBootstrapPreflightResult) -> PlayerBootstrapPreflightResult:
    if len(_PREFLIGHT_CACHE) >= _PREFLIGHT_CACHE_LIMIT:
        # 简单 FIFO 淘汰：键顺序稳定，不依赖 hash 随机化。
        oldest = next(iter(_PREFLIGHT_CACHE))
        _PREFLIGHT_CACHE.pop(oldest, None)
    _PREFLIGHT_CACHE[result.cache_key] = result
    return result


def bootstrap_cache_key(
    *,
    video_signature: str,
    clip_start_ms: int,
    clip_end_ms: int,
    match_format: str | None,
    sync_signature: str,
    calibration_signature: str,
    model_version: str,
    config: BootstrapPreflightConfig,
    secondary_signature: str = "",
) -> str:
    """缓存键：视频版本 + 片段 + 同步/标定 + 模型 + 配置（含双摄机位来源）。"""
    material = {
        "schema": PREFLIGHT_SCHEMA_VERSION,
        "video": video_signature,
        "secondary": secondary_signature,
        "clip_start_ms": int(clip_start_ms),
        "clip_end_ms": int(clip_end_ms),
        "match_format": match_format,
        "sync": sync_signature,
        "calibration": calibration_signature,
        "model": model_version,
        "config": config.signature(),
    }
    return hashlib.sha256(
        json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


# ── 窗口规划 ──


def _clamp_clip_range(
    *,
    clip_start_ms: int,
    clip_end_ms: int | None,
    fps: float,
    frame_count: int,
    diagnostics: list[PlayerBootstrapQualityDiagnostic],
) -> tuple[int, int]:
    """把所选片段收窄到媒体实际长度，并记录诊断。

    媒体长度已知时，越界的窗口只会全部读不到帧；若不收窄，预检会以
    `no_detections` 收场，掩盖"请求的片段超出视频长度"这一真实原因。
    请求范围完全落在媒体之后时回退到媒体尾部的一段，而不是空窗口。
    """
    start = max(0, int(clip_start_ms or 0))
    duration_ms: int | None = None
    if fps > 0 and frame_count > 0:
        duration_ms = int(frame_count / float(fps) * 1000)
    requested_end = int(clip_end_ms) if clip_end_ms is not None else None

    if requested_end is not None and requested_end > start:
        end = requested_end
    elif duration_ms is not None and duration_ms > start:
        end = duration_ms
    else:
        end = start + 60_000

    if duration_ms is not None and duration_ms > 0 and end > duration_ms:
        end = duration_ms
        if start >= end:
            # 请求范围整体越界：改为媒体尾部的一段，并明确告知已收窄。
            start = max(0, end - 60_000)
        diagnostics.append(
            PlayerBootstrapQualityDiagnostic(
                code=DIAG_PREFLIGHT_CLIP_CLAMPED,
                detail=(
                    f"所选片段超出视频长度（媒体约 {duration_ms}ms），"
                    f"已收窄到 {start}–{end}ms"
                ),
                severity="info",
            )
        )
    if end <= start:
        end = start + 1
    return start, end


def plan_windows(
    *,
    clip_start_ms: int,
    clip_end_ms: int,
    config: BootstrapPreflightConfig,
) -> list[PreflightWindow]:
    """中段优先、向前后交替扩展的窗口序列。

    中段优先是刻意的：开场球员尚未入场、邻场人员走动都会污染开头几秒，
    而中段通常是回合进行中、目标球场球员持续可见的时段。
    """
    start = max(0, int(clip_start_ms))
    end = max(start + 1, int(clip_end_ms))
    span = end - start
    span_ms = max(1, min(int(config.window_span_ms), span))
    mid = start + span // 2

    # 偏移序列：0, -1, +1, -2, +2 ... 保证同一输入的窗口顺序完全确定。
    offsets: list[int] = []
    step = 0
    while len(offsets) < max(1, int(config.window_count)):
        if step == 0:
            offsets.append(0)
        else:
            offsets.extend((-step, step))
        step += 1
    offsets = offsets[: max(1, int(config.window_count))]

    windows: list[PreflightWindow] = []
    for ordinal, offset in enumerate(offsets):
        center = mid + offset * span_ms
        window_start = center - span_ms // 2
        window_start = max(start, min(window_start, end - span_ms))
        windows.append(
            PreflightWindow(
                ordinal=ordinal,
                start_ms=int(window_start),
                end_ms=int(window_start + span_ms),
                origin="mid" if offset == 0 else ("earlier" if offset < 0 else "later"),
            )
        )
    return windows


def sample_timestamps_ms(window: PreflightWindow, count: int) -> list[int]:
    """在窗口内均匀取 `count` 个时刻（含两端），保持升序且不重复。"""
    count = max(1, int(count))
    if count == 1:
        return [int((window.start_ms + window.end_ms) // 2)]
    span = max(1, window.end_ms - window.start_ms)
    values = [int(window.start_ms + span * index / (count - 1)) for index in range(count)]
    ordered: list[int] = []
    for value in values:
        if not ordered or value > ordered[-1]:
            ordered.append(value)
    return ordered


# ── 目标球场成员判定 ──


def distance_from_target_court(x_ft: float, y_ft: float) -> float:
    """点到标准球场矩形的欧氏距离（球场内为 0）。"""
    dx = max(0.0, max(-x_ft, x_ft - COURT_WIDTH_FT))
    dy = max(0.0, max(-y_ft, y_ft - COURT_LENGTH_FT))
    return hypot(dx, dy)


def _appearance_distance(left: Any, right: Any) -> float | None:
    if left is None or right is None:
        return None
    try:
        import numpy as np

        a = left.vector() if hasattr(left, "vector") else None
        b = right.vector() if hasattr(right, "vector") else None
        if a is None or b is None or a.shape != b.shape:
            return None
        denominator = a + b + 1e-6
        chi_square = 0.5 * float(np.sum(((a - b) ** 2) / denominator)) / max(1, a.size)
        return max(0.0, min(1.0, chi_square * 8.0))
    except Exception:  # noqa: BLE001 - 外观只是辅助证据，失败不得中断预检
        return None


# ── 主流程 ──


def run_bootstrap_preflight(
    *,
    frame_source: PreflightFrameSource,
    detector: _Detector,
    view_ids: Sequence[str],
    clip_start_ms: int,
    clip_end_ms: int,
    expected_player_count: int,
    config: BootstrapPreflightConfig | None = None,
    court_projector_for: Callable[[str], Callable[[float, float], tuple[float, float] | None] | None]
    | None = None,
    appearance_extractor_for: Callable[[str], Any | None] | None = None,
    sync_trusted: bool = False,
    multiview_reason: str | None = None,
    cache_key: str = "",
    match_format: str | None = None,
) -> PlayerBootstrapPreflightResult:
    """执行受限多窗口预检，返回候选、主参考画面与诊断。

    参数全部显式注入，便于在不加载 cv2/ultralytics 的情况下做契约与场景测试。
    """
    config = config or BootstrapPreflightConfig()
    diagnostics: list[PlayerBootstrapQualityDiagnostic] = []
    views = [view for view in view_ids if view]
    if not views:
        return PlayerBootstrapPreflightResult(
            schema_version=PREFLIGHT_SCHEMA_VERSION,
            status="unavailable",
            unavailable_reason=DIAG_PREFLIGHT_NO_WINDOWS,
            cache_key=cache_key,
            diagnostics=[
                PlayerBootstrapQualityDiagnostic(
                    code=DIAG_PREFLIGHT_NO_WINDOWS,
                    detail="没有可用的源视频机位，无法进行候选预检",
                    severity="warning",
                )
            ],
        )
    if cache_key and cache_key in _PREFLIGHT_CACHE:
        return _PREFLIGHT_CACHE[cache_key]

    fps = max(1e-3, float(getattr(frame_source, "fps", 25.0) or 25.0))
    frame_count = int(getattr(frame_source, "frame_count", 0) or 0)
    clip_start_ms, clip_end_ms = _clamp_clip_range(
        clip_start_ms=clip_start_ms,
        clip_end_ms=clip_end_ms,
        fps=fps,
        frame_count=frame_count,
        diagnostics=diagnostics,
    )

    windows = plan_windows(
        clip_start_ms=clip_start_ms, clip_end_ms=clip_end_ms, config=config
    )
    if not windows:
        return _remember(
            PlayerBootstrapPreflightResult(
                schema_version=PREFLIGHT_SCHEMA_VERSION,
                status="unavailable",
                unavailable_reason=DIAG_PREFLIGHT_NO_WINDOWS,
                cache_key=cache_key,
                clip_start_ms=clip_start_ms,
                clip_end_ms=clip_end_ms,
                diagnostics=diagnostics
                + [
                    PlayerBootstrapQualityDiagnostic(
                        code=DIAG_PREFLIGHT_NO_WINDOWS,
                        detail="所选片段内没有可采样的时间窗口",
                        severity="warning",
                    )
                ],
            )
        )

    projectors = {view: (court_projector_for(view) if court_projector_for else None) for view in views}
    extractors = {
        view: (appearance_extractor_for(view) if appearance_extractor_for else None) for view in views
    }
    any_projection = any(projector is not None for projector in projectors.values())

    tracklets: dict[str, list[_Tracklet]] = {view: [] for view in views}
    unreadable = 0
    sampled = 0
    sampled_by_view: dict[str, int] = {view: 0 for view in views}
    budget = max(1, int(config.max_frames_total))
    seen_frame_keys: set[tuple[str, int]] = set()

    # 先按"中段优先"的顺序挑出采样点并施加预算，再**按时间升序**逐帧处理：
    # 窗口优先级决定"先看哪一段"，但短时关联必须在时间轴上单调前进，
    # 否则从窗口 A 跳到更早的窗口 B 会被误判成新轨迹。
    planned: list[tuple[PreflightWindow, int]] = []
    slots = 0
    for window in windows:
        if slots >= budget:
            diagnostics.append(
                PlayerBootstrapQualityDiagnostic(
                    code=DIAG_PREFLIGHT_BUDGET_EXHAUSTED,
                    detail=f"抽帧预算（{budget} 帧）已用尽，后续窗口未采样",
                    severity="info",
                )
            )
            break
        for timestamp_ms in sample_timestamps_ms(window, config.frames_per_window):
            if slots >= budget:
                break
            planned.append((window, timestamp_ms))
            slots += len(views)

    for window, timestamp_ms in sorted(planned, key=lambda item: item[1]):
        if sampled >= budget:
            break
        for view in views:
            if sampled >= budget:
                break
            source_time = getattr(frame_source, "source_timestamp_ms", None)
            source_timestamp_ms = int(source_time(view, timestamp_ms)) if callable(source_time) else timestamp_ms
            view_fps_getter = getattr(frame_source, "fps_for_view", None)
            view_fps = float(view_fps_getter(view)) if callable(view_fps_getter) else fps
            frame_index = int(round(source_timestamp_ms / 1000.0 * view_fps))
            view_count_getter = getattr(frame_source, "frame_count_for_view", None)
            view_count = int(view_count_getter(view)) if callable(view_count_getter) else frame_count
            if view_count > 0:
                frame_index = min(frame_index, view_count - 1)
            frame_index = max(0, frame_index)
            if (view, frame_index) in seen_frame_keys:
                continue
            seen_frame_keys.add((view, frame_index))
            frame = frame_source.read(view, frame_index)
            sampled += 1
            sampled_by_view[view] = sampled_by_view.get(view, 0) + 1
            if frame is None:
                unreadable += 1
                continue
            detections = _detect(detector, frame, config)
            _absorb_detections(
                tracklets=tracklets[view],
                view_id=view,
                frame=frame,
                frame_index=frame_index,
                timestamp_ms=source_timestamp_ms,
                canonical_timestamp_ms=timestamp_ms,
                detections=detections,
                config=config,
                projector=projectors.get(view),
                extractor=extractors.get(view),
            )

    if unreadable:
        diagnostics.append(
            PlayerBootstrapQualityDiagnostic(
                code=DIAG_PREFLIGHT_FRAME_UNREADABLE,
                detail=f"{unreadable} 个采样帧无法读取，已跳过",
                severity="info",
            )
        )

    # 采样与逐帧吸收完成后做一次同机位同人合并：检测器在同一时刻对同一人给出多个重叠框时，
    # 逐帧规则只允许一条轨迹吸收一个检测，剩下的框会新建轨迹并在此后的时刻与前者交替抢检测，
    # 表现为"同一名球员被识别成两个人"。合并必须发生在选取之前，否则重复轨迹会占掉候选位。
    for view in views:
        tracklets[view] = _merge_duplicate_tracklets(tracklets[view], config)

    result = _select_candidates(
        tracklets=tracklets,
        views=views,
        expected_player_count=max(1, int(expected_player_count)),
        config=config,
        diagnostics=diagnostics,
        any_projection=any_projection,
        sync_trusted=sync_trusted,
        multiview_reason=multiview_reason,
        cache_key=cache_key,
        sampled=sampled,
        sampled_by_view=sampled_by_view,
        windows=windows,
        clip_start_ms=clip_start_ms,
        clip_end_ms=clip_end_ms,
        match_format=match_format,
    )
    return _remember(result)


def _detect(
    detector: _Detector, frame: Any, config: BootstrapPreflightConfig
) -> list[tuple[list[float], float]]:
    """返回 (bbox, 检测置信度) 列表；bbox 为 [x1, y1, x2, y2]。

    置信度必须来自检测器本身：预检候选的置信度是给用户和审计看的证据，
    不允许用占位常数填充。
    """
    try:
        raw = detector.detect(frame)
    except Exception:  # noqa: BLE001 - 单帧检测失败不应中断整个预检
        return []
    boxes: list[tuple[list[float], float]] = []
    for item in raw or []:
        bbox = getattr(item, "bbox", None)
        if bbox is None or len(bbox) < 4:
            continue
        values = [float(value) for value in bbox[:4]]
        if not all(value == value for value in values):  # NaN 过滤
            continue
        x1, y1, x2, y2 = values
        if x2 - x1 < config.min_bbox_width_px or y2 - y1 < config.min_bbox_height_px:
            continue
        raw_confidence = getattr(item, "confidence", None)
        try:
            confidence = float(raw_confidence) if raw_confidence is not None else 0.0
        except (TypeError, ValueError):
            confidence = 0.0
        boxes.append((values, confidence))
    return boxes


def _body_crop_quality(frame: Any, bbox: Sequence[float], config: BootstrapPreflightConfig) -> tuple[float, float]:
    """人物画面质量与框面积占比；不依赖可选图像库时退化为几何估计。"""
    try:
        height, width = frame.shape[:2]
    except Exception:  # noqa: BLE001
        return 0.0, 0.0
    x1, y1, x2, y2 = [float(value) for value in bbox[:4]]
    box_width = max(0.0, x2 - x1)
    box_height = max(0.0, y2 - y1)
    area_ratio = (box_width * box_height) / max(1.0, float(width) * float(height))
    # 裁切惩罚：bbox 越接近/越出画面边缘，画面越可能不完整。
    clipped = max(0.0, -x1) + max(0.0, -y1) + max(0.0, x2 - width) + max(0.0, y2 - height)
    clipping_ratio = min(1.0, clipped / max(1.0, box_width + box_height))
    size_score = 1.0 if 0.02 <= area_ratio <= 0.35 else 0.35
    blur_score = 1.0
    try:
        import cv2  # type: ignore

        crop = frame[max(0, int(y1)) : max(0, int(y2)), max(0, int(x1)) : max(0, int(x2)), :3]
        if getattr(crop, "size", 0):
            gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
            blur_score = min(1.0, float(cv2.Laplacian(gray, cv2.CV_64F).var()) / 48.0)
    except Exception:  # noqa: BLE001 - 无 cv2 时按几何质量代替
        blur_score = 1.0
    quality = max(0.0, min(1.0, size_score * blur_score * (1.0 - clipping_ratio)))
    return quality, area_ratio


def _absorb_detections(
    *,
    tracklets: list[_Tracklet],
    view_id: str,
    frame: Any,
    frame_index: int,
    timestamp_ms: int,
    canonical_timestamp_ms: int | None = None,
    detections: Sequence[tuple[Sequence[float], float]],
    config: BootstrapPreflightConfig,
    projector: Callable[[float, float], tuple[float, float] | None] | None,
    extractor: Any | None,
) -> None:
    """把一帧的检测按"归一化中心距离"关联进已有 tracklet，或新建 tracklet。"""
    try:
        height, width = frame.shape[:2]
    except Exception:  # noqa: BLE001
        return
    frame_width = max(1.0, float(width))
    frame_height = max(1.0, float(height))

    ordered = sorted(detections, key=lambda item: (float(item[0][0]), float(item[0][1])))
    # 一帧内一条轨迹至多接收一次观测。先按距离匹配已有轨迹，再为剩余检测
    # 建新轨迹；逐检测贪心会把相邻的两个人都塞进同一轨迹，虚增命中次数。
    pairs: list[tuple[float, int, int]] = []
    for detection_index, (bbox, _confidence) in enumerate(ordered):
        x1, y1, x2, y2 = [float(value) for value in bbox[:4]]
        cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
        for tracklet_index, tracklet in enumerate(tracklets):
            if tracklet.hits and abs(timestamp_ms - tracklet.timestamps_ms[-1]) > config.max_association_gap_ms:
                continue
            last_index = tracklet.hits - 1
            if last_index < 0:
                continue
            last_bbox = tracklet.bboxes[last_index]
            last_cx = (last_bbox[0] + last_bbox[2]) / 2.0
            last_cy = (last_bbox[1] + last_bbox[3]) / 2.0
            distance = hypot((cx - last_cx) / frame_width, (cy - last_cy) / frame_height)
            if distance < config.association_radius:
                pairs.append((distance, tracklet_index, detection_index))
    assigned: dict[int, _Tracklet] = {}
    claimed_tracklets: set[int] = set()
    for _distance, tracklet_index, detection_index in sorted(pairs):
        if detection_index in assigned or tracklet_index in claimed_tracklets:
            continue
        assigned[detection_index] = tracklets[tracklet_index]
        claimed_tracklets.add(tracklet_index)

    for detection_index, (bbox, confidence) in enumerate(ordered):
        x1, y1, x2, y2 = [float(value) for value in bbox[:4]]
        cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
        best = assigned.get(detection_index)
        if best is None:
            best = _Tracklet(
                view_id=view_id,
                first_timestamp_ms=int(timestamp_ms),
                first_frame_index=int(frame_index),
                first_bbox=[x1, y1, x2, y2],
                first_center=(cx, cy),
            )
            tracklets.append(best)

        quality, area_ratio = _body_crop_quality(frame, [x1, y1, x2, y2], config)
        # 归一化基准随观测一起记下：合并判据与逐帧关联必须用同一套基准。
        best.frame_width = frame_width
        best.frame_height = frame_height
        best.timestamps_ms.append(int(timestamp_ms))
        best.canonical_timestamps_ms.append(
            int(canonical_timestamp_ms) if canonical_timestamp_ms is not None else int(timestamp_ms)
        )
        best.bboxes.append([x1, y1, x2, y2])
        best.confidences.append(float(confidence))
        best.body_qualities.append(quality)
        best.frame_area_ratios.append(area_ratio)
        # 用 bbox 底边中点作为脚点，与既有投影管线一致。
        foot = ((x1 + x2) / 2.0, y2)
        point = _safe_project(projector, foot) if projector is not None else None
        best.court_points.append(
            (float(point[0]), float(point[1])) if point is not None else None
        )
        if extractor is not None and config.appearance_enabled:
            descriptor = _extract_appearance(extractor, frame, [x1, y1, x2, y2])
            if descriptor is not None:
                best.appearance_vectors.append(descriptor)
                appearance_quality = getattr(getattr(descriptor, "quality", None), "score", None)
                if appearance_quality is not None:
                    best.appearance_qualities.append(float(appearance_quality))


def _safe_project(
    projector: Callable[[float, float], tuple[float, float] | None],
    point: tuple[float, float],
) -> tuple[float, float] | None:
    try:
        return projector(point[0], point[1])
    except Exception:  # noqa: BLE001 - 单点投影失败不应中断预检
        return None


def _extract_appearance(extractor: Any, frame: Any, bbox: Sequence[float]) -> Any | None:
    try:
        return extractor.extract(frame, bbox, provenance="base")
    except Exception:  # noqa: BLE001
        return None


def _score_tracklet(
    tracklet: _Tracklet,
    *,
    config: BootstrapPreflightConfig,
    sampled_frames: int,
    any_projection: bool,
    best_appearance_distance: float | None,
) -> tuple[float, dict[str, float | None], bool]:
    """返回 (综合分, 证据字典, 是否通过目标球场成员门槛)。

    综合分刻意把"目标球场成员概率"与"短时连续性"放在最前面：仅凭检测到人
    或短暂路过不足以成为候选。
    """
    sampled = max(1, sampled_frames)
    coverage = min(1.0, tracklet.hits / float(sampled))
    persistence = min(1.0, tracklet.hits / max(1.0, float(config.min_hits_for_candidate * 2)))
    occupancy: float | None = None
    mean_distance: float | None = None
    valid_court_points = [point for point in tracklet.court_points if point is not None]
    if valid_court_points:
        distances = [distance_from_target_court(x, y) for x, y in valid_court_points]
        occupancy = sum(1 for value in distances if value <= config.court_margin_ft) / len(distances)
        mean_distance = sum(distances) / len(distances)
    membership = occupancy if occupancy is not None else None
    passed_membership = True
    if membership is not None:
        passed_membership = membership >= config.target_court_threshold
    quality = (
        sum(tracklet.body_qualities) / len(tracklet.body_qualities) if tracklet.body_qualities else 0.0
    )
    appearance_quality = (
        sum(tracklet.appearance_qualities) / len(tracklet.appearance_qualities)
        if tracklet.appearance_qualities
        else None
    )
    # 区分度：与其他候选外观距离越大越可信（距离近 = 难以区分 → 扣分）。
    discriminative = 1.0 if best_appearance_distance is None else min(1.0, best_appearance_distance * 2.0)
    membership_score = 0.5 if membership is None else membership
    score = max(
        0.0,
        min(
            1.0,
            membership_score * 0.40
            + persistence * 0.22
            + quality * 0.18
            + coverage * 0.12
            + discriminative * 0.08,
        ),
    )
    evidence: dict[str, float | None] = {
        "target_court_membership": membership,
        "target_court_occupancy": occupancy,
        "mean_target_court_distance_ft": mean_distance,
        "continuity": persistence,
        "coverage_ratio": coverage,
        "sampled_hits": float(tracklet.hits),
        "sampled_frames": float(sampled),
        "body_crop_quality": quality,
        "appearance_quality": appearance_quality,
        "appearance_margin": best_appearance_distance,
        "multiview_agreement": None,
    }
    del any_projection
    return score, evidence, passed_membership


def _cross_view_distance(left: _Tracklet, right: _Tracklet) -> float | None:
    """同一 canonical 时刻的球场轨迹距离；不足两对观测不作跨机位断言。"""
    left_times = left.canonical_timestamps_ms or left.timestamps_ms
    right_times = right.canonical_timestamps_ms or right.timestamps_ms
    right_points = [
        (timestamp, point)
        for timestamp, point in zip(right_times, right.court_points, strict=False)
        if point is not None
    ]
    distances: list[float] = []
    for timestamp, point in zip(left_times, left.court_points, strict=False):
        if point is None or not right_points:
            continue
        nearest_time, nearest_point = min(right_points, key=lambda item: abs(item[0] - timestamp))
        if abs(nearest_time - timestamp) <= 150:
            distances.append(hypot(point[0] - nearest_point[0], point[1] - nearest_point[1]))
    if len(distances) < 2:
        return None
    ordered = sorted(distances)
    return ordered[len(ordered) // 2]


SIDE_KEYS: tuple[str, str] = ("end_a", "end_b")


def _side_label(side: str) -> str:
    return {"end_a": "A 端侧", "end_b": "B 端侧"}.get(side, side)


def _tracklet_side(
    court_points: Sequence[tuple[float, float] | None],
    config: BootstrapPreflightConfig,
) -> str | None:
    """按 canonical 球场 y 的中位数判定候选落在哪一侧。

    与正式管线 `_BootstrapTracklet.inferred_side` 同语义：用**中位数**而非单点，中线 ± 死区
    内判为未知（返回 None），未知的候选不受分侧配额约束。没有投影时同样返回 None。
    """
    ys = [float(point[1]) for point in court_points if point is not None]
    if not ys:
        return None
    median_y = statistics.median(ys)
    if abs(median_y - config.court_half_length_ft) < config.side_dead_zone_ft:
        return None
    return "end_a" if median_y < config.court_half_length_ft else "end_b"


def _side_quotas(expected_player_count: int) -> dict[str, int]:
    """赛制分侧配额：双打 2+2、单打 1+1（有余数时 A 端侧先取一名）。"""
    total = max(1, int(expected_player_count))
    first = (total + 1) // 2
    return {SIDE_KEYS[0]: first, SIDE_KEYS[1]: total - first}


def _select_by_side_quota(
    ordered: Sequence[tuple[str, _Tracklet, float, dict[str, float | None]]],
    *,
    expected_player_count: int,
    config: BootstrapPreflightConfig,
) -> tuple[
    list[tuple[str, _Tracklet, float, dict[str, float | None]]],
    dict[int, str | None],
    dict[str, tuple[int, int]],
]:
    """按证据顺序做分侧配额选取，返回 (入选项, 各轨迹侧向, 未填满的侧)。

    已判定侧向的候选只能在**自己那一侧**的配额内入选；侧向未知的候选不受配额约束，
    被用来填当前较空的一侧（保持两侧均衡）。某侧可靠候选不足时**不用对侧补位**，
    由调用方据此写出诊断并把状态降级。
    """
    side_by_tracklet = {
        id(tracklet): _tracklet_side(tracklet.court_points, config) for _, tracklet, _, _ in ordered
    }
    quota = _side_quotas(expected_player_count)
    buckets: dict[str, list[tuple[str, _Tracklet, float, dict[str, float | None]]]] = {
        side: [] for side in SIDE_KEYS
    }
    known = [item for item in ordered if side_by_tracklet[id(item[1])]]
    unknown = [item for item in ordered if not side_by_tracklet[id(item[1])]]
    for item in known:
        side = side_by_tracklet[id(item[1])]
        if side is not None and len(buckets[side]) < quota[side]:
            buckets[side].append(item)
    for item in unknown:
        primary, secondary = SIDE_KEYS
        if len(buckets[primary]) < quota[primary] and len(buckets[primary]) <= len(buckets[secondary]):
            buckets[primary].append(item)
        elif len(buckets[secondary]) < quota[secondary]:
            buckets[secondary].append(item)
        elif len(buckets[primary]) < quota[primary]:
            buckets[primary].append(item)

    selected: list[tuple[str, _Tracklet, float, dict[str, float | None]]] = []
    for side in SIDE_KEYS:
        # 同侧内部按画面位置编号，让使用者看到"从左到右"的稳定顺序；
        # 这只是槽位编号，不参与谁入选。
        group = sorted(
            buckets[side],
            key=lambda item: (
                float(item[1].first_center[0]),
                float(item[1].first_center[1]),
                int(item[1].first_timestamp_ms),
            ),
        )
        selected.extend(group)
    unfilled = {
        side: (len(buckets[side]), quota[side])
        for side in SIDE_KEYS
        if len(buckets[side]) < quota[side]
    }
    return selected, side_by_tracklet, unfilled


# ── 跨帧同人合并（同一机位内）──


def _center_distance(
    left_bbox: Sequence[float],
    right_bbox: Sequence[float],
    *,
    frame_width: float,
    frame_height: float,
) -> float | None:
    """两个 bbox 中心的归一化距离；缺画面尺寸时返回 None（不猜基准、不下判断）。"""
    if frame_width <= 0 or frame_height <= 0:
        return None
    left_cx = (float(left_bbox[0]) + float(left_bbox[2])) / 2.0
    left_cy = (float(left_bbox[1]) + float(left_bbox[3])) / 2.0
    right_cx = (float(right_bbox[0]) + float(right_bbox[2])) / 2.0
    right_cy = (float(right_bbox[1]) + float(right_bbox[3])) / 2.0
    return hypot((left_cx - right_cx) / frame_width, (left_cy - right_cy) / frame_height)


def _nearest_paired_distance(
    left: _Tracklet,
    right: _Tracklet,
    config: BootstrapPreflightConfig,
) -> float | None:
    """把每条观测与另一条轨迹时间最接近的观测配对（两侧各算一遍），取最小距离。"""
    frame_width = left.frame_width or right.frame_width
    frame_height = left.frame_height or right.frame_height
    distances: list[float] = []
    for source, target in ((left, right), (right, left)):
        target_times = list(target.timestamps_ms)
        if not target_times:
            continue
        for timestamp, bbox in zip(source.timestamps_ms, source.bboxes, strict=False):
            nearest_time = min(target_times, key=lambda value: abs(int(value) - int(timestamp)))
            if abs(nearest_time - int(timestamp)) > config.max_association_gap_ms:
                continue
            index = target_times.index(nearest_time)
            distance = _center_distance(
                bbox,
                target.bboxes[index],
                frame_width=frame_width,
                frame_height=frame_height,
            )
            if distance is not None:
                distances.append(distance)
    return min(distances) if distances else None


def _appearance_vetoes_merge(
    left: _Tracklet,
    right: _Tracklet,
    config: BootstrapPreflightConfig,
) -> bool:
    """外观只作否决：双方都有描述子且明显不同时不合并；缺描述子时不参与判定。"""
    if not left.appearance_vectors or not right.appearance_vectors:
        return False
    distance = _appearance_distance(left.appearance_vectors[-1], right.appearance_vectors[-1])
    if distance is None:
        return False
    return distance > config.merge_appearance_max_distance


def _tracklets_are_same_player(
    left: _Tracklet,
    right: _Tracklet,
    config: BootstrapPreflightConfig,
) -> bool:
    """判定同一机位的两条轨迹是否其实是同一名球员。

    主判据是**时间互斥**：同一时刻只允许一条轨迹吸收该时刻的检测，所以"同一名球员被检测器
    拆成两个框"必然表现为两条轨迹在若干采样时刻交替出现（一方有观测、另一方没有）。真正的
    两名队友在几乎每个采样时刻都各有观测，互斥次数约为 0，因此不会被合并——只靠距离做不到
    这一点（远端两名队友相距约 0.10 归一化，仍在关联半径 0.15 之内）。
    """
    if min(left.hits, right.hits) < config.min_exclusive_observations:
        return False
    frame_width = left.frame_width or right.frame_width
    frame_height = left.frame_height or right.frame_height
    left_by_time = {int(t): b for t, b in zip(left.timestamps_ms, left.bboxes, strict=False)}
    right_by_time = {int(t): b for t, b in zip(right.timestamps_ms, right.bboxes, strict=False)}
    exclusive = 0
    shared: list[float] = []
    for timestamp in sorted(set(left_by_time) | set(right_by_time)):
        in_left = timestamp in left_by_time
        in_right = timestamp in right_by_time
        if in_left and in_right:
            distance = _center_distance(
                left_by_time[timestamp],
                right_by_time[timestamp],
                frame_width=frame_width,
                frame_height=frame_height,
            )
            if distance is not None:
                shared.append(distance)
        elif in_left != in_right:
            exclusive += 1
    if exclusive < config.min_exclusive_observations:
        return False
    # 双方同刻都被观测到时从未分开过，才允许合并。
    if shared and max(shared) >= config.merge_radius_normalized:
        return False
    nearest = _nearest_paired_distance(left, right, config)
    if nearest is None or nearest >= config.merge_radius_normalized:
        return False
    return not _appearance_vetoes_merge(left, right, config)


def _merge_tracklet_into(keep: _Tracklet, other: _Tracklet) -> None:
    """把 `other` 的观测并入 `keep`：同一时刻取置信度更高者，锚点回到最早观测。"""
    keep_first_timestamp = int(keep.first_timestamp_ms)
    records: dict[int, dict[str, Any]] = {}
    for source in (keep, other):
        for index, raw_timestamp in enumerate(source.timestamps_ms):
            timestamp = int(raw_timestamp)
            confidence = float(source.confidences[index]) if index < len(source.confidences) else 0.0
            existing = records.get(timestamp)
            if existing is not None and float(existing["confidence"]) >= confidence:
                continue
            records[timestamp] = {
                "confidence": confidence,
                "bbox": [float(value) for value in source.bboxes[index]]
                if index < len(source.bboxes)
                else None,
                "canonical": int(source.canonical_timestamps_ms[index])
                if index < len(source.canonical_timestamps_ms)
                else timestamp,
                "court": source.court_points[index] if index < len(source.court_points) else None,
                "quality": float(source.body_qualities[index])
                if index < len(source.body_qualities)
                else 0.0,
                "area": float(source.frame_area_ratios[index])
                if index < len(source.frame_area_ratios)
                else 0.0,
            }
    ordered = [(timestamp, record) for timestamp, record in sorted(records.items()) if record["bbox"]]
    if not ordered:
        return
    keep.timestamps_ms = [timestamp for timestamp, _ in ordered]
    keep.canonical_timestamps_ms = [record["canonical"] for _, record in ordered]
    keep.bboxes = [record["bbox"] for _, record in ordered]
    keep.confidences = [record["confidence"] for _, record in ordered]
    keep.body_qualities = [record["quality"] for _, record in ordered]
    keep.frame_area_ratios = [record["area"] for _, record in ordered]
    keep.court_points = [record["court"] for _, record in ordered]
    # 外观描述子不保证与逐观测对齐（提取失败时会缺项），按"先 keep 后 other"近似时间序拼接。
    keep.appearance_vectors = list(keep.appearance_vectors) + list(other.appearance_vectors)
    keep.appearance_qualities = list(keep.appearance_qualities) + list(other.appearance_qualities)
    first_timestamp, first_record = ordered[0]
    keep.first_timestamp_ms = int(first_timestamp)
    keep.first_bbox = list(first_record["bbox"])
    keep.first_center = (
        (keep.first_bbox[0] + keep.first_bbox[2]) / 2.0,
        (keep.first_bbox[1] + keep.first_bbox[3]) / 2.0,
    )
    if int(other.first_timestamp_ms) < keep_first_timestamp:
        # 锚点帧序号必须跟着最早观测走：candidate_id 用它表达锚点所在帧。
        keep.first_frame_index = int(other.first_frame_index)


def _merge_duplicate_tracklets(
    tracklets: Sequence[_Tracklet],
    config: BootstrapPreflightConfig,
) -> list[_Tracklet]:
    """反复合并同一机位内被判为同一名球员的轨迹，直到没有可合并的一对。"""
    merged = list(tracklets)
    merged_any = True
    while merged_any:
        merged_any = False
        for left_index in range(len(merged)):
            for right_index in range(left_index + 1, len(merged)):
                if _tracklets_are_same_player(merged[left_index], merged[right_index], config):
                    _merge_tracklet_into(merged[left_index], merged[right_index])
                    merged.pop(right_index)
                    merged_any = True
                    break
            if merged_any:
                break
    return merged


def _select_candidates(
    *,
    tracklets: dict[str, list[_Tracklet]],
    views: Sequence[str],
    expected_player_count: int,
    config: BootstrapPreflightConfig,
    diagnostics: list[PlayerBootstrapQualityDiagnostic],
    any_projection: bool,
    sync_trusted: bool,
    multiview_reason: str | None,
    cache_key: str,
    sampled: int,
    sampled_by_view: dict[str, int],
    windows: Sequence[PreflightWindow],
    clip_start_ms: int,
    clip_end_ms: int,
    match_format: str | None = None,
) -> PlayerBootstrapPreflightResult:
    reference_view = views[0]
    diagnostics = list(diagnostics)
    if not any_projection:
        diagnostics.append(
            PlayerBootstrapQualityDiagnostic(
                code=DIAG_PREFLIGHT_NO_CALIBRATION,
                detail="缺少可用场地标定，候选只能按画面连续性排序，无法排除场外人员",
                severity="warning",
            )
        )
    views_used = [reference_view]
    multiview_eligible = False
    if len(views) > 1:
        if sync_trusted and all(
            any(point is not None for track in tracklets.get(view, []) for point in track.court_points)
            for view in views
        ):
            views_used = list(views)
            multiview_eligible = True
        else:
            diagnostics.append(
                PlayerBootstrapQualityDiagnostic(
                    code=DIAG_PREFLIGHT_NO_SYNC if not sync_trusted else DIAG_PREFLIGHT_NO_CALIBRATION,
                    detail=(multiview_reason or "双摄时间映射不可信") if not sync_trusted else "双摄缺少可对齐的球场坐标，不合并候选",
                    severity="warning",
                )
            )

    scored: list[tuple[str, _Tracklet, float, dict[str, float | None]]] = []
    rejected_off_court = 0
    for view in views_used:
        candidates_for_view: list[tuple[_Tracklet, float, dict[str, float | None]]] = []
        for tracklet in tracklets.get(view, []):
            if tracklet.hits < config.min_hits_for_candidate:
                continue
            if not tracklet.frame_area_ratios:
                continue
            mean_area = sum(tracklet.frame_area_ratios) / len(tracklet.frame_area_ratios)
            if not (config.min_box_area_ratio <= mean_area <= config.max_box_area_ratio):
                continue
            candidates_for_view.append((tracklet, 0.0, {}))
        # 先算互相之间的外观区分度，再定分。
        for index, (tracklet, _score, _evidence) in enumerate(candidates_for_view):
            others = [
                _appearance_distance(
                    tracklet.appearance_vectors[-1] if tracklet.appearance_vectors else None,
                    other.appearance_vectors[-1] if other.appearance_vectors else None,
                )
                for other_index, (other, _s, _e) in enumerate(candidates_for_view)
                if other_index != index
            ]
            valid = [value for value in others if value is not None]
            margin = min(valid) if valid else None
            score, evidence, passed = _score_tracklet(
                tracklet,
                config=config,
                sampled_frames=sampled_by_view.get(view, sampled),
                any_projection=any_projection,
                best_appearance_distance=margin,
            )
            if not passed:
                rejected_off_court += 1
                continue
            scored.append((view, tracklet, score, evidence))

    if rejected_off_court:
        diagnostics.append(
            PlayerBootstrapQualityDiagnostic(
                code=DIAG_PREFLIGHT_OUT_OF_TARGET_COURT,
                detail=f"{rejected_off_court} 条轨迹因不在目标球场范围内被排除（不补入候选）",
                severity="info",
            )
        )

    # 确定性排序：机位优先级 → 分数降序 → 首次时刻 → 首次中心 x → 首次中心 y。
    # 画面位置只作最末位的稳定兜底键：它 MUST NOT 决定谁入选（入选由证据分与分侧配额决定），
    # 否则画面里靠右的真实球员会被画面里靠左的重复轨迹挤掉。
    view_priority = {view: index for index, view in enumerate(views_used)}
    ordered = sorted(
        scored,
        key=lambda item: (
            view_priority.get(item[0], len(view_priority)),
            -float(item[2]),
            int(item[1].first_timestamp_ms),
            float(item[1].first_center[0]),
            float(item[1].first_center[1]),
        ),
    )
    # 同一机位内避免极近距离的重复轨迹（同一人被拆成两条）。
    deduped: list[tuple[str, _Tracklet, float, dict[str, float | None]]] = []
    supporting_views: dict[int, set[str]] = {}
    supporting_distance: dict[int, float] = {}
    for item in ordered:
        duplicate = False
        for kept in deduped:
            if kept[0] != item[0] and multiview_eligible:
                distance = _cross_view_distance(kept[1], item[1])
                if distance is not None and distance <= 3.0:
                    supporting_views.setdefault(id(kept[1]), set()).add(item[0])
                    supporting_distance[id(kept[1])] = min(
                        distance, supporting_distance.get(id(kept[1]), float("inf"))
                    )
                    duplicate = True
                    break
            if kept[0] != item[0] or kept[1].first_frame_index != item[1].first_frame_index:
                continue
            keep_bbox = kept[1].first_bbox
            item_bbox = item[1].first_bbox
            if _iou(keep_bbox, item_bbox) >= 0.5:
                duplicate = True
                break
        if not duplicate:
            deduped.append(item)

    # 分侧配额选取：双打每侧各两名、单打每侧各一名；一侧不足时不用对侧补位。
    selected, side_by_tracklet, unfilled = _select_by_side_quota(
        deduped,
        expected_player_count=expected_player_count,
        config=config,
    )
    if unfilled:
        quota_detail = "、".join(
            f"{_side_label(side)} {filled}/{quota}" for side, (filled, quota) in sorted(unfilled.items())
        )
        diagnostics.append(
            PlayerBootstrapQualityDiagnostic(
                code=DIAG_PREFLIGHT_SIDE_QUOTA_UNFILLED,
                detail=(
                    f"match_format={match_format or 'unknown'}：{quota_detail}；"
                    "不足的一侧不用对侧候选补位，请手工补全未完成槽位或跳过"
                ),
                severity="warning",
            )
        )

    candidates: list[PlayerBootstrapCandidateV2] = []
    candidate_tracklets: list[tuple[PlayerBootstrapCandidateV2, _Tracklet]] = []
    for index, (view, tracklet, score, evidence) in enumerate(selected, start=1):
        best_index = tracklet.best_observation_index()
        if best_index < 0:
            continue
        bbox = [float(value) for value in tracklet.bboxes[best_index]]
        timestamp_ms = int(tracklet.timestamps_ms[best_index])
        court_xy = None
        if best_index < len(tracklet.court_points) and tracklet.court_points[best_index] is not None:
            point = tracklet.court_points[best_index]
            court_xy = [float(point[0]), float(point[1])]
        candidate = PlayerBootstrapCandidateV2(
                candidate_id=f"bp_{view}_{tracklet.first_frame_index}_{index}",
                suggested_slot=index,
                view_id=view,
                timestamp_ms=timestamp_ms,
                bbox=bbox,
                court_xy=court_xy,
                confidence=(
                    sum(tracklet.confidences) / len(tracklet.confidences)
                    if tracklet.confidences
                    else None
                ),
                score=round(float(score), 4),
                source_views=[view, *sorted(supporting_views.get(id(tracklet), set()))],
                evidence=PlayerBootstrapCandidateEvidence(
                    side=side_by_tracklet.get(id(tracklet)),
                    target_court_membership=_round_or_none(evidence.get("target_court_membership")),
                    target_court_occupancy=_round_or_none(evidence.get("target_court_occupancy")),
                    mean_target_court_distance_ft=_round_or_none(
                        evidence.get("mean_target_court_distance_ft")
                    ),
                    continuity=_round_or_none(evidence.get("continuity")),
                    coverage_ratio=_round_or_none(evidence.get("coverage_ratio")),
                    sampled_hits=int(evidence.get("sampled_hits") or 0),
                    sampled_frames=int(evidence.get("sampled_frames") or 0),
                    body_crop_quality=_round_or_none(evidence.get("body_crop_quality")),
                    appearance_quality=_round_or_none(evidence.get("appearance_quality")),
                    appearance_margin=_round_or_none(evidence.get("appearance_margin")),
                    multiview_agreement=(
                        round(max(0.0, 1.0 - supporting_distance[id(tracklet)] / 3.0), 4)
                        if id(tracklet) in supporting_distance else None
                    ),
                ),
            )
        candidates.append(candidate)
        candidate_tracklets.append((candidate, tracklet))

    reference_frame = _build_reference_frame(candidate_tracklets=candidate_tracklets, windows=windows)
    multiview_used = any(len(candidate.source_views) > 1 or candidate.view_id != reference_view for candidate in candidates)

    if not candidates:
        diagnostics.append(
            PlayerBootstrapQualityDiagnostic(
                code=DIAG_PREFLIGHT_NO_DETECTIONS,
                detail="采样窗口内没有稳定的人体候选；请重新选帧或手工框选，也可直接跳过",
                severity="warning",
            )
        )
        return PlayerBootstrapPreflightResult(
            schema_version=PREFLIGHT_SCHEMA_VERSION,
            status="unavailable",
            unavailable_reason=DIAG_PREFLIGHT_NO_DETECTIONS,
            cache_key=cache_key,
            candidates=[],
            reference_frame=None,
            diagnostics=diagnostics,
            sampled_frame_count=sampled,
            windows=list(windows),
            multiview_used=multiview_used,
            clip_start_ms=clip_start_ms,
            clip_end_ms=clip_end_ms,
        )

    status = "available" if len(candidates) >= expected_player_count else "insufficient_candidates"
    if status == "insufficient_candidates":
        diagnostics.append(
            PlayerBootstrapQualityDiagnostic(
                code=DIAG_PREFLIGHT_INSUFFICIENT,
                detail=(
                    f"仅得到 {len(candidates)} 名可靠候选（预期 {expected_player_count} 名）；"
                    "未识别的槽位需手工补全或跳过"
                ),
                severity="warning",
            )
        )
    else:
        diagnostics.append(
            PlayerBootstrapQualityDiagnostic(
                code=DIAG_PREFLIGHT_STABLE_ORDER,
                detail=f"预检缓存键 {cache_key}：同一输入会复用同一候选顺序",
                severity="info",
            )
        )
    return PlayerBootstrapPreflightResult(
        schema_version=PREFLIGHT_SCHEMA_VERSION,
        status=status,
        unavailable_reason=None if status == "available" else DIAG_PREFLIGHT_INSUFFICIENT,
        cache_key=cache_key,
        candidates=candidates,
        reference_frame=reference_frame,
        diagnostics=diagnostics,
        sampled_frame_count=sampled,
        windows=list(windows),
        multiview_used=multiview_used,
        clip_start_ms=clip_start_ms,
        clip_end_ms=clip_end_ms,
    )


def _build_reference_frame(
    *,
    candidate_tracklets: Sequence[tuple[PlayerBootstrapCandidateV2, _Tracklet]],
    windows: Sequence[PreflightWindow],
) -> PlayerBootstrapReferenceFrame | None:
    """选一张"同帧可见候选最多"的主参考画面。

    `observed_bboxes` 只收录**在该帧实际观测到**的候选；不同时刻的框绝不画在同一帧上。
    """
    if not candidate_tracklets:
        return None
    midpoint = (windows[0].start_ms + windows[0].end_ms) // 2 if windows else 0
    # 卡片的最佳裁剪帧可以不同；主画面须从所有真实观测中找同帧最多的时刻。
    observed: dict[tuple[str, int], dict[str, list[float]]] = {}
    for candidate, tracklet in candidate_tracklets:
        for timestamp_ms, bbox in zip(tracklet.timestamps_ms, tracklet.bboxes, strict=True):
            observed.setdefault((candidate.view_id, timestamp_ms), {})[candidate.candidate_id] = [
                float(value) for value in bbox
            ]
    (view_id, best_timestamp), present = sorted(
        observed.items(),
        key=lambda item: (-len(item[1]), abs(item[0][1] - midpoint), item[0][0], item[0][1]),
    )[0]
    return PlayerBootstrapReferenceFrame(
        view_id=view_id,
        timestamp_ms=int(best_timestamp),
        candidate_ids=sorted(present),
        observed_bboxes={candidate_id: present[candidate_id] for candidate_id in sorted(present)},
    )


def _round_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), 4)
    except (TypeError, ValueError):
        return None


def _iou(left: Sequence[float], right: Sequence[float]) -> float:
    lx1, ly1, lx2, ly2 = [float(value) for value in left[:4]]
    rx1, ry1, rx2, ry2 = [float(value) for value in right[:4]]
    inter_x1 = max(lx1, rx1)
    inter_y1 = max(ly1, ry1)
    inter_x2 = min(lx2, rx2)
    inter_y2 = min(ly2, ry2)
    if inter_x2 <= inter_x1 or inter_y2 <= inter_y1:
        return 0.0
    intersection = (inter_x2 - inter_x1) * (inter_y2 - inter_y1)
    union = (lx2 - lx1) * (ly2 - ly1) + (rx2 - rx1) * (ry2 - ry1) - intersection
    return intersection / union if union > 0 else 0.0


def iter_window_timestamps(
    windows: Iterable[PreflightWindow], per_window: int
) -> list[tuple[PreflightWindow, int]]:
    """展开 (窗口, 时刻) 序列，供诊断与测试复用。"""
    return [
        (window, timestamp)
        for window in windows
        for timestamp in sample_timestamps_ms(window, per_window)
    ]
