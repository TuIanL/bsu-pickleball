"""显式准备媒体/模型身份；preview 只读取这些已登记快照。"""
from __future__ import annotations

import json
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from app.analysis_runtime.contracts import ModelAsset, ModelSnapshot, SourceSnapshot
from app.analysis_runtime.hashing import AnalysisRuntimeError, canonical_json, digest, file_digest


def parse_sync(payload: dict):
    from app.services.dual_camera_sync import calibration_from_dict
    from app.vision.multiview.sync import MultiViewSyncCalibration
    try:
        if payload.get("schema_version") != "dual_camera_sync_calibration.v1":
            raise ValueError("unsupported sync schema")
        sync = MultiViewSyncCalibration(
            reference_camera=payload["reference_camera"],
            mappings={key: calibration_from_dict(value) for key, value in payload["mappings"].items()},
            anchor_count=payload.get("anchor_count"), source=payload.get("source"),
            anchor_validation=payload.get("anchor_validation"),
        )
        if not sync.reference_camera or not sync.mappings:
            raise ValueError("empty sync")
        if any(mapping.quality not in {"good", "degraded"} for mapping in sync.mappings.values()):
            raise ValueError("sync quality unavailable")
        return sync
    except (KeyError, TypeError, ValueError) as exc:
        raise AnalysisRuntimeError("sync_snapshot_invalid", "同步快照无效") from exc


def sync_contract(payload: dict) -> dict:
    from app.services.dual_camera_sync import calibration_to_dict
    sync = parse_sync(payload)
    return {"schema_version": sync.schema_version, "reference_camera": sync.reference_camera,
            "anchor_count": sync.anchor_count, "source": sync.source,
            "anchor_validation": sync.anchor_validation, "revision": payload.get("revision"),
            "mappings": {key: calibration_to_dict(value) for key, value in sorted(sync.mappings.items())}}


def prepare_source(store, path: Path, *, view_id="cam_1", camera_id=None, video_id=None, require_pts=False) -> SourceSnapshot:
    import cv2
    from app.services.frame_timing_provider import FrameTimingProvider

    path = path.expanduser().resolve()
    if not path.is_file():
        raise AnalysisRuntimeError("source_missing", "来源媒体不存在")
    before_hash = file_digest(path)
    capture = cv2.VideoCapture(str(path))
    try:
        if not capture.isOpened():
            raise AnalysisRuntimeError("source_unreadable", "来源媒体无法打开")
        fps = float(capture.get(cv2.CAP_PROP_FPS))
        count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        width, height = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)), int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    finally:
        capture.release()
    if fps <= 0 or count <= 0 or min(width, height) <= 0:
        raise AnalysisRuntimeError("source_metadata_invalid", "媒体元数据无效")
    sidecar = Path(str(path) + ".pts.jsonl")
    sidecar_before = file_digest(sidecar) if sidecar.is_file() else None
    try:
        timing = (FrameTimingProvider.from_sidecar(sidecar, media_path=path) if sidecar.is_file()
                  else FrameTimingProvider.from_media(path, frame_count=count, fps=fps, allow_nominal_fallback=not require_pts))
    except (ValueError, OSError) as exc:
        raise AnalysisRuntimeError("source_timing_invalid", "已有 PTS 无效，不能静默替换为 FPS") from exc
    if timing.provenance.authority == "missing":
        raise AnalysisRuntimeError("authoritative_pts_required", "正式双摄需要来源 PTS")
    rows = [{"frame_index": f.frame_index, "pts_seconds": f.pts_seconds, "dts_seconds": f.dts_seconds, "keyframe": f.keyframe} for f in timing.frames]
    timing_text = canonical_json(rows) + "\n"
    source_id = "source-" + digest({"media": before_hash, "timing": rows, "view": view_id, "camera": camera_id or view_id, "video_id": video_id})[:32]
    source_dir = store.root.parent / "_sources" / source_id
    source_dir.mkdir(parents=True, exist_ok=True)
    timing_path = source_dir / "timing.json"
    if timing_path.exists() and timing_path.read_text() != timing_text:
        raise AnalysisRuntimeError("source_snapshot_conflict", source_id)
    if not timing_path.exists():
        timing_path.write_text(timing_text)
    if file_digest(path) != before_hash:
        raise AnalysisRuntimeError("source_changed_during_preparation", "来源在准备过程中变化")
    if timing.is_source_pts and file_digest(sidecar) != sidecar_before:
        raise AnalysisRuntimeError("source_changed_during_preparation", "PTS 在准备过程中变化")
    source = SourceSnapshot(
        source_id=source_id, video_id=video_id, view_id=view_id, camera_id=camera_id or view_id,
        media_path=str(path), media_sha256=before_hash,
        sidecar_path=str(sidecar) if timing.is_source_pts else None,
        sidecar_sha256=file_digest(sidecar) if timing.is_source_pts else None,
        timing_path=str(timing_path), timing_sha256=file_digest(timing_path),
        timing_authority=timing.provenance.authority, frame_count=count, fps=fps,
        duration_ms=max(1, round(timing.duration_seconds * 1000)), width=width, height=height,
    )
    store.register_source(source)
    return source


def prepare_models(store, settings) -> dict:
    detector = Path(settings.default_detector_model).expanduser()
    model_root = settings.resolve_path(settings.model_dir)
    if not detector.is_file() and (model_root / detector).is_file():
        detector = model_root / detector
    candidates = {
        "player.yolo.v1": ({"weights": detector}, {"device": settings.detector_device or "cpu"}),
        "ball.yolo.v1": ({"weights": Path(settings.ball_model_path)} if settings.ball_model_path else {}, {"device": "cpu"}),
        "pose.rtmpose26.v1": (
            {"weights": Path(settings.rtmpose_checkpoint_path), "config": Path(settings.rtmpose_config_path)}
            if settings.rtmpose_checkpoint_path and settings.rtmpose_config_path else {}, {"device": settings.rtmpose_device or "cpu"}),
    }
    result = {}
    for implementation_id, (paths, configuration) in candidates.items():
        packages = ["torch", "numpy", "ultralytics"] if implementation_id != "pose.rtmpose26.v1" else ["torch", "numpy", "scipy", "mmpose", "mmcv", "mmengine"]
        configuration["runtime_versions"] = runtime_versions(packages)
        missing = [key for key, path in paths.items() if not path.is_file()]
        if not paths or missing:
            result[implementation_id] = {"status": "model_environment", "missing": missing or ["assets"]}
            continue
        if implementation_id == "pose.rtmpose26.v1":
            # 模型配置包含相对 _base_；同时冻结同一配置树，避免只校验入口文件。
            config_root = paths["config"].parent
            for parent in paths["config"].parents:
                if parent.name == "configs":
                    config_root = parent
                    break
            for support in config_root.rglob("*.py"):
                paths["support:" + str(support.relative_to(config_root))] = support
        assets = {key: ModelAsset(path=str(path.resolve()), sha256=file_digest(path)) for key, path in sorted(paths.items())}
        store.register_model(ModelSnapshot(implementation_id=implementation_id, assets=assets, configuration=configuration))
        result[implementation_id] = {"status": "prepared", "assets": {k: a.sha256 for k, a in assets.items()}}
    return result


def verify_sources(sources) -> None:
    for source in sources:
        pairs = [(source.media_path, source.media_sha256), (source.timing_path, source.timing_sha256)]
        if source.sidecar_path:
            pairs.append((source.sidecar_path, source.sidecar_sha256))
        for path, expected in pairs:
            try:
                valid = file_digest(Path(path)) == expected
            except OSError:
                valid = False
            if not valid:
                raise AnalysisRuntimeError("source_revision_mismatch", "来源内容或 PTS 快照已改变")


def verify_model(model: ModelSnapshot) -> None:
    expected = model.configuration.get("runtime_versions", {})
    if expected and runtime_versions(expected) != expected:
        raise AnalysisRuntimeError("model_environment", "已冻结推理依赖版本与当前环境不符")
    for asset in model.assets.values():
        try:
            valid = file_digest(Path(asset.path)) == asset.sha256
        except OSError:
            valid = False
        if not valid:
            raise AnalysisRuntimeError("model_revision_mismatch", "已冻结模型资源不可用或内容改变")


def runtime_versions(packages):
    result = {}
    for package in packages:
        try:
            result[package] = version(package)
        except PackageNotFoundError:
            result[package] = "missing"
    return result
