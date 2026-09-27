"""预检运行时装配 —— 把真实视频、标定、同步与外观模块接到纯预检引擎上。

分工：`player_bootstrap_preflight` 只做"给定帧源/检测器/投影器，产出候选"的纯逻辑；
本模块负责**取真实依赖**并把它们包成引擎需要的可注入接口：

- `Cv2ViewFrameSource` —— 按帧序号从每个机位的源视频读取帧；
- `resolve_preflight_context()` —— 从 `capture_take_id` 解析出场次目录、双摄机位
  （`CaptureTrack`）、场景标定（`MetricCourtSceneService`）与同步质量；
- `build_court_projector()` —— 复用既有单应矩阵把脚点投影到 canonical 球场坐标；
- `build_video_signature()` —— 视频版本签名（进缓存键）；
- `sync_is_trusted()` —— 只有 good/degraded 的同步才允许跨机位补强。

所有取依赖失败都返回 None / 空并附带原因，**不抛异常**：预检是可选前置，
不能因为缺标定或缺模型而阻塞普通分析创建。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from app.schemas.rally_context import PlayerBootstrapQualityDiagnostic

DIAG_RUNTIME_NO_TAKE_DIR = "bootstrap_runtime_take_dir_unavailable"
DIAG_RUNTIME_NO_SCENE = "bootstrap_runtime_scene_calibration_unavailable"
DIAG_RUNTIME_SCENE_NOT_READY = "bootstrap_runtime_scene_calibration_not_ready"
_VIDEO_METADATA_CACHE: dict[tuple[str, int, int], tuple[float, int]] = {}
_VIDEO_METADATA_CACHE_LIMIT = 64


def clear_video_metadata_cache() -> None:
    _VIDEO_METADATA_CACHE.clear()


@dataclass
class PreflightViewContext:
    """单个机位参与预检所需的全部输入。"""

    view_id: str
    video_id: str | None = None
    camera_id: str | None = None
    video_path: Path | None = None
    calibration_id: str | None = None
    court_orientation: str | None = None
    fps: float = 25.0
    frame_count: int = 0
    sync_offset_seconds: float = 0.0
    sync_rate: float = 1.0


@dataclass
class PreflightRuntimeContext:
    """一次预检的运行时上下文。"""

    take_dir: Path | None = None
    views: list[PreflightViewContext] = field(default_factory=list)
    sync_quality: str | None = None
    sync_trusted: bool = False
    sync_reason: str | None = None
    diagnostics: list[PlayerBootstrapQualityDiagnostic] = field(default_factory=list)
    unreadable_reason: str | None = None

    @property
    def view_ids(self) -> list[str]:
        return [view.view_id for view in self.views]


def build_video_signature(path: Path | None) -> str:
    """视频版本签名：路径 + 大小 + mtime。文件不可读时退化为路径哈希。"""
    if path is None:
        return "none"
    try:
        stat = path.stat()
        material = f"{path.resolve()}:{stat.st_size}:{int(stat.st_mtime)}"
    except OSError:
        material = str(path)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


def build_calibration_signature(scene_revision: int | None, calibration_ids: list[str]) -> str:
    material = f"rev={scene_revision}:" + ",".join(sorted(value or "" for value in calibration_ids))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


def sync_is_trusted(sync: Any | None) -> tuple[bool, str | None]:
    """只有 good / degraded 的同步映射才允许跨机位证据融合。"""
    if sync is None:
        return False, "未找到双摄同步校准产物"
    try:
        from app.vision.multiview.sync import evaluate_sync_gate

        decision, reason = evaluate_sync_gate(sync)
    except Exception as exc:  # noqa: BLE001 - 同步判定的实现异常按不可信处理
        return False, f"同步质量判定失败：{exc}"
    return decision in {"fuse", "fuse_degraded"}, reason


class Cv2ViewFrameSource:
    """按帧序号读取多机位源帧；seek 语义即"源视频 PTS"，与正式产物的时间基准一致。"""

    def __init__(self, views: list[PreflightViewContext]) -> None:
        self._views = {view.view_id: view for view in views}
        self._captures: dict[str, Any] = {}
        self._fps = 25.0
        self._frame_count = 0
        if views:
            if views[0].fps > 0:
                self._fps = float(views[0].fps)
            if views[0].frame_count > 0:
                self._frame_count = int(views[0].frame_count)

    @property
    def fps(self) -> float:
        return self._fps

    @property
    def frame_count(self) -> int:
        return self._frame_count

    def fps_for_view(self, view_id: str) -> float:
        view = self._views.get(view_id)
        return float(view.fps) if view is not None and view.fps > 0 else self._fps

    def frame_count_for_view(self, view_id: str) -> int:
        view = self._views.get(view_id)
        return int(view.frame_count) if view is not None else 0

    def source_timestamp_ms(self, view_id: str, reference_timestamp_ms: int) -> int:
        view = self._views.get(view_id)
        if view is None:
            return reference_timestamp_ms
        return max(0, round(1000 * view.sync_offset_seconds + view.sync_rate * reference_timestamp_ms))

    def _capture(self, view_id: str) -> Any | None:
        if view_id in self._captures:
            return self._captures[view_id]
        view = self._views.get(view_id)
        if view is None or view.video_path is None:
            self._captures[view_id] = None
            return None
        try:
            import cv2  # type: ignore

            capture = cv2.VideoCapture(str(view.video_path))
            if not capture.isOpened():
                capture.release()
                self._captures[view_id] = None
                return None
            self._captures[view_id] = capture
            return capture
        except Exception:  # noqa: BLE001 - 缺 cv2 或打不开视频 → 该机位不可用
            self._captures[view_id] = None
            return None

    def read(self, view_id: str, frame_index: int) -> Any | None:
        capture = self._capture(view_id)
        if capture is None:
            return None
        try:
            import cv2  # type: ignore

            capture.set(cv2.CAP_PROP_POS_FRAMES, float(max(0, int(frame_index))))
            ok, frame = capture.read()
            return frame if ok else None
        except Exception:  # noqa: BLE001
            return None

    def release(self) -> None:
        for capture in self._captures.values():
            if capture is not None:
                try:
                    capture.release()
                except Exception:  # noqa: BLE001
                    continue
        self._captures.clear()

    def __enter__(self) -> "Cv2ViewFrameSource":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.release()


def build_court_projector(
    *,
    calibration_id: str | None,
    court_orientation: str | None,
) -> Callable[[float, float], tuple[float, float] | None] | None:
    """用既有单应矩阵 + 机位朝向构造"图像脚点 → canonical 球场坐标"的投影函数。

    缺少标定或缺少已声明的朝向时返回 None：不知道 local 帧如何对齐 canonical 时
    **禁止**用投影式猜测（与 `court_frame.local_to_canonical` 的约束一致）。
    """
    if not calibration_id or not court_orientation:
        return None
    try:
        from app.services.calibration_service import calibration_service
        from app.vision.courtvision_calibration_engine.homography import image_to_court
        from app.vision.multiview.court_frame import CourtOrientation, local_to_canonical

        calibration = calibration_service.get_calibration(calibration_id)
        if calibration is None:
            return None
        homography = calibration.homography.values
        orientation = CourtOrientation(court_orientation)
    except Exception:  # noqa: BLE001 - 标定不可用时诚实降级为"无球场证据"
        return None

    def _project(x: float, y: float) -> tuple[float, float] | None:
        try:
            local_x, local_y = image_to_court((float(x), float(y)), homography)
            return local_to_canonical(float(local_x), float(local_y), orientation)
        except Exception:  # noqa: BLE001 - 单点投影失败只丢该点
            return None

    return _project


def build_appearance_extractor() -> Any | None:
    """衣着外观描述子提取器；缺 cv2/numpy 时返回 None（外观只是辅助证据）。"""
    try:
        from app.vision.player_tracking_engine.player_appearance import ClothingAppearanceExtractor

        return ClothingAppearanceExtractor()
    except Exception:  # noqa: BLE001
        return None


def resolve_preflight_context(
    db: Any,
    *,
    capture_take_id: str | None,
    video_id: str | None,
    video_id_b: str | None = None,
) -> PreflightRuntimeContext:
    """解析场次目录、机位（含标定与朝向）与同步可信度。

    这是预检唯一的"取真实依赖"入口；任何一步失败都只记录诊断并继续，
    让引擎在没有标定/没有同步的情况下仍能产出可用候选。
    """
    context = PreflightRuntimeContext()
    if not capture_take_id:
        context.unreadable_reason = DIAG_RUNTIME_NO_TAKE_DIR
        context.diagnostics.append(
            PlayerBootstrapQualityDiagnostic(
                code=DIAG_RUNTIME_NO_TAKE_DIR,
                detail="缺少 capture_take_id，预检无法读取场次标定与同步，只能按单机位画面连续性给候选",
                severity="info",
            )
        )
        return context

    try:
        from app.models.capture_take import CaptureTake

        take = db.query(CaptureTake).filter(CaptureTake.id == capture_take_id).first()
    except Exception:  # noqa: BLE001 - 控制面不可用不应阻塞预检
        take = None
    if take is None or not getattr(take, "session_dir", None):
        context.unreadable_reason = DIAG_RUNTIME_NO_TAKE_DIR
        context.diagnostics.append(
            PlayerBootstrapQualityDiagnostic(
                code=DIAG_RUNTIME_NO_TAKE_DIR,
                detail="该录制场次没有 session_dir，预检无法读取标定与同步",
                severity="info",
            )
        )
        return context
    context.take_dir = Path(take.session_dir)

    scene = None
    try:
        from app.services.metric_court_scene_service import metric_court_scene_service

        scene = metric_court_scene_service.get_current(context.take_dir)
    except Exception:  # noqa: BLE001
        scene = None
    if scene is None:
        context.diagnostics.append(
            PlayerBootstrapQualityDiagnostic(
                code=DIAG_RUNTIME_NO_SCENE,
                detail="该场次没有已发布的场景标定，候选缺少球场坐标证据",
                severity="warning",
            )
        )
    elif getattr(scene, "status", None) != "ready":
        context.diagnostics.append(
            PlayerBootstrapQualityDiagnostic(
                code=DIAG_RUNTIME_SCENE_NOT_READY,
                detail=f"场景标定状态为 {getattr(scene, 'status', 'unknown')}，不作为球场证据使用",
                severity="warning",
            )
        )
        scene = None

    scene_views: list[Any] = list(getattr(scene, "views", []) or []) if scene is not None else []
    scene_by_view = {
        str(getattr(view, "view_id", "")): view for view in scene_views if getattr(view, "view_id", None)
    }

    # 未提供 video_id 时，用场景标定里记录的 video_id 兜底（同一 take 的视角声明）。
    resolved_primary = video_id
    if not resolved_primary and scene_views:
        resolved_primary = getattr(scene_views[0], "video_id", None)

    ordered_view_ids: list[str] = []
    for candidate in ("cam_1", "cam_2"):
        if candidate in scene_by_view:
            ordered_view_ids.append(candidate)
    for view_id in sorted(scene_by_view):
        if view_id not in ordered_view_ids:
            ordered_view_ids.append(view_id)
    if not ordered_view_ids:
        ordered_view_ids = ["cam_1"]

    secondary_video = video_id_b
    for view_id in ordered_view_ids:
        scene_view = scene_by_view.get(view_id)
        if scene_view is None:
            continue
        if view_id == "cam_2" and secondary_video is None:
            secondary_video = getattr(scene_view, "video_id", None)

    for index, view_id in enumerate(ordered_view_ids):
        scene_view = scene_by_view.get(view_id)
        if index == 0:
            resolved_video = resolved_primary or getattr(scene_view, "video_id", None)
        else:
            resolved_video = secondary_video or getattr(scene_view, "video_id", None)
        context.views.append(
            PreflightViewContext(
                view_id=view_id,
                video_id=resolved_video,
                camera_id=(str(scene_view.camera_id) if scene_view is not None and getattr(scene_view, "camera_id", None) else None),
                calibration_id=(str(scene_view.calibration_id) if scene_view is not None and getattr(scene_view, "calibration_id", None) else None),
                court_orientation=(str(scene_view.court_orientation) if scene_view is not None and getattr(scene_view, "court_orientation", None) else None),
            )
        )

    try:
        from app.vision.multiview.sync import load_sync_calibration

        sync = load_sync_calibration(context.take_dir)
    except Exception:  # noqa: BLE001
        sync = None
    trusted, reason = sync_is_trusted(sync)
    context.sync_trusted = trusted
    context.sync_quality = (
        getattr(sync, "worst_quality", lambda: None)() if sync is not None else None
    )
    context.sync_reason = reason
    if trusted and sync is not None:
        for view in context.views:
            mapping = sync.mapping_for(view.camera_id) if view.camera_id else None
            if mapping is None:
                context.sync_trusted = False
                context.sync_reason = f"{view.view_id} 缺少双摄时间映射"
                break
            view.sync_offset_seconds = float(mapping.offset_seconds)
            view.sync_rate = float(mapping.rate)
    return context


def attach_video_paths(context: PreflightRuntimeContext, video_service: Any) -> None:
    """给每个机位补上视频路径、fps 与帧数（读不到就留空，由引擎按不可读处理）。"""
    for view in context.views:
        if not view.video_id:
            continue
        try:
            video = video_service.get_available_video(view.video_id)
        except Exception:  # noqa: BLE001
            video = None
        if video is None:
            continue
        view.video_path = Path(video.path)
        try:
            stat = view.video_path.stat()
            metadata_key = (str(view.video_path.resolve()), stat.st_size, stat.st_mtime_ns)
        except OSError:
            metadata_key = None
        cached = _VIDEO_METADATA_CACHE.get(metadata_key) if metadata_key is not None else None
        if cached is not None:
            view.fps, view.frame_count = cached
            continue
        try:
            import cv2  # type: ignore

            capture = cv2.VideoCapture(str(view.video_path))
            if capture.isOpened():
                view.fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0) or view.fps
                view.frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
                if metadata_key is not None:
                    if len(_VIDEO_METADATA_CACHE) >= _VIDEO_METADATA_CACHE_LIMIT:
                        _VIDEO_METADATA_CACHE.pop(next(iter(_VIDEO_METADATA_CACHE)))
                    _VIDEO_METADATA_CACHE[metadata_key] = (view.fps, view.frame_count)
            capture.release()
        except Exception:  # noqa: BLE001 - 探帧失败不阻塞，引擎读帧时再降级
            continue
