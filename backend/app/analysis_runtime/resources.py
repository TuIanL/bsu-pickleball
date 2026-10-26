"""窗口内帧资源，单节点生命周期；不持久化 RGB。"""
from __future__ import annotations

import json
import os
from contextlib import ExitStack
from pathlib import Path

from app.analysis_runtime.hashing import AnalysisRuntimeError
from app.analysis_runtime.sources import parse_sync


def configure_model_cache(tmp_root):
    """只在模型 miss 时设置可写运行缓存，避免字体/配置回退到只读用户目录。"""
    root = (Path(tmp_root)/"analysis-model-cache").resolve()
    for key, folder in [("MPLCONFIGDIR", "matplotlib"), ("YOLO_CONFIG_DIR", "ultralytics"), ("XDG_CACHE_HOME", "cache")]:
        if key not in os.environ:
            directory = root/folder
            directory.mkdir(parents=True, exist_ok=True)
            os.environ[key] = str(directory)


class BoundedCapture:
    def __init__(self, source, counters, check):
        import cv2
        self.cv2, self.source, self.counters, self.check = cv2, source, counters, check
        self.capture = cv2.VideoCapture(source.media_path)
        counters["capture_opens"] += 1
        self.cursor = None
        if not self.capture.isOpened():
            self.capture.release()
            raise AnalysisRuntimeError("source_decode_failed", "无法打开源视频")

    def read(self, index: int):
        self.check()
        if self.cursor is None or index < self.cursor:
            if not self.capture.set(self.cv2.CAP_PROP_POS_FRAMES, index):
                raise AnalysisRuntimeError("window_seek_failed", "窗口定位失败")
            actual = self.capture.get(self.cv2.CAP_PROP_POS_FRAMES)
            if abs(actual-index) > 0.5:
                raise AnalysisRuntimeError("window_seek_failed", "解码位置不符合冻结窗口")
            self.cursor = index
            self.counters.setdefault("seek_frames", []).append(index)
        while self.cursor < index:
            self.check()
            if not self.capture.grab():
                raise AnalysisRuntimeError("source_decode_failed", "窗口内源帧不可解码")
            self.counters["decoded_frames"] += 1
            self.cursor += 1
        ok, frame = self.capture.read()
        if not ok:
            raise AnalysisRuntimeError("source_decode_failed", "窗口内源帧不可解码")
        self.cursor = index + 1
        self.counters["decoded_frames"] += 1
        self.counters.setdefault("read_frame_ranges", {}).setdefault(self.source.view_id, [index, index])
        self.counters["read_frame_ranges"][self.source.view_id][1] = index
        return frame

    def close(self):
        self.capture.release()


def iter_frames(plan, node, counters, check):
    from app.services.dual_camera_sync import FrameTiming
    from app.services.frame_timing_provider import FrameTimingProvider, TimingProvenance
    from app.vision.multiview.analysis_clock import CanonicalAnalysisClock

    reference = next(s for s in plan.sources if s.view_id == plan.reference_view_id)
    providers = {}
    for source in plan.sources:
        rows = json.loads(Path(source.timing_path).read_text())
        providers[source.view_id] = FrameTimingProvider(
            frames=tuple(FrameTiming(**row) for row in rows),
            provenance=TimingProvenance(authority=source.timing_authority), fps=source.fps)
    ref_provider = providers[reference.view_id]
    origin = ref_provider.first_timestamp_seconds or 0
    samples = [f for f in ref_provider.frames if node.effective_window.start_ms <= (f.pts_seconds-origin)*1000 < node.effective_window.end_ms]
    if not samples:
        raise AnalysisRuntimeError("window_no_samples", "窗口内没有来源帧")
    anchor = 0 if plan.sampling.anchor == "source_frame_0" else samples[0].frame_index
    samples = [f for f in samples if (f.frame_index-anchor-plan.sampling.phase) % plan.sampling.stride == 0]
    secondary = next((s for s in plan.sources if s.view_id != reference.view_id), None)
    clock = None
    if secondary:
        sec_provider = providers[secondary.view_id]
        clock = CanonicalAnalysisClock(
            reference_view_id=reference.view_id, secondary_view_id=secondary.view_id,
            secondary_frames=list(sec_provider.frames_with_origin()),
            sync=parse_sync(plan.sync), secondary_camera_id=secondary.camera_id,
            reference_timing_provider=ref_provider, secondary_timing_provider=sec_provider,
            reference_timing_authority=reference.timing_authority,
            secondary_timing_authority=secondary.timing_authority,
        )
    counters["decoder_backend"] = "opencv"
    counters["backend_gop_preread"] = "internal_not_exposed"
    with ExitStack() as resources:
        captures = {}
        degraded = set()
        for sample in samples:
            check()
            time_ms = (sample.pts_seconds-origin)*1000
            if clock:
                bundle = clock.tick(reference_frame_index=sample.frame_index, reference_timestamp_seconds=time_ms/1000)
                items = [(source, bundle.views.get(source.view_id), bundle.frame_status[source.view_id]) for source in plan.sources]
            else:
                from app.vision.multiview.analysis_clock import FrameSample
                items = [(reference, FrameSample(sample.frame_index, sample.pts_seconds*1000, time_ms), "available")]
            for source, frame_sample, status in items:
                if source.view_id in degraded:
                    status = "unavailable_decode"
                counts = counters.setdefault("mapping_status_counts", {})
                counts[source.view_id + ":" + status] = counts.get(source.view_id + ":" + status, 0) + 1
                row = {"view_id": source.view_id, "canonical_time_ms": time_ms, "mapping_status": status,
                       "source_frame_index": frame_sample.source_frame_index if frame_sample else None,
                       "source_pts_ms": frame_sample.source_timestamp_ms if frame_sample else None,
                       "timing_authority": source.timing_authority}
                if status != "available" or frame_sample is None:
                    yield source, row, None
                    continue
                try:
                    if source.view_id not in captures:
                        capture = BoundedCapture(source, counters, check)
                        captures[source.view_id] = capture
                        resources.callback(capture.close)
                    frame = captures[source.view_id].read(frame_sample.source_frame_index)
                except AnalysisRuntimeError:
                    if source == reference or node.implementation.secondary_failure_policy != "degrade":
                        raise
                    degraded.add(source.view_id)
                    counters["secondary_degraded"] = True
                    row["mapping_status"] = "unavailable_decode"
                    yield source, row, None
                    continue
                yield source, row, frame
