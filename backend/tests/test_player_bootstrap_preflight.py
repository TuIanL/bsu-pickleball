"""自动候选预检的契约与场景测试。

覆盖 change `simplify-automatic-player-roster-confirmation` 任务 5.1 的场景：
开头未入场、邻场误检、异时刻图框、单打、双摄互补/失同步、模型不可用、
部分候选（旧产物质量不合格的等价降级路径）与预算耗尽。

这里的帧源与检测器都是显式注入的替身：预检引擎本身不依赖 cv2 / ultralytics，
因此这些用例验证的是**判定逻辑**，不是模型精度。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

import pytest

from app.services.player_bootstrap_preflight import (
    COURT_LENGTH_FT,
    DIAG_PREFLIGHT_BUDGET_EXHAUSTED,
    DIAG_PREFLIGHT_CLIP_CLAMPED,
    DIAG_PREFLIGHT_INSUFFICIENT,
    DIAG_PREFLIGHT_NO_CALIBRATION,
    DIAG_PREFLIGHT_NO_DETECTIONS,
    DIAG_PREFLIGHT_NO_SYNC,
    DIAG_PREFLIGHT_OUT_OF_TARGET_COURT,
    DIAG_PREFLIGHT_SIDE_QUOTA_UNFILLED,
    BootstrapPreflightConfig,
    bootstrap_cache_key,
    clear_preflight_cache,
    plan_windows,
    run_bootstrap_preflight,
    sample_timestamps_ms,
    _Tracklet,
    _absorb_detections,
    _build_reference_frame,
    _merge_duplicate_tracklets,
    _select_by_side_quota,
    _tracklet_side,
    _tracklets_are_same_player,
    PreflightWindow,
)
from app.schemas.rally_context import PlayerBootstrapCandidateV2

FRAME_HEIGHT = 120
FRAME_WIDTH = 240


@dataclass(frozen=True)
class _Detection:
    bbox: list[float]
    confidence: float


@dataclass
class _Person:
    """一次场景里"某个位置上有个人"。"""

    bbox: list[float]
    court_xy: tuple[float, float] | None = None
    active_from_ms: int = 0
    active_to_ms: int = 10**9

    def active(self, timestamp_ms: int) -> bool:
        return self.active_from_ms <= timestamp_ms <= self.active_to_ms


@dataclass
class _PersonIndexedFrameSource:
    """把真实时刻（毫秒）写进像素，供替身检测器读取。"""

    fps: float = 30.0
    frame_count: int = 60_000
    reads: list[tuple[str, int]] = field(default_factory=list)

    def read(self, view_id: str, frame_index: int) -> Any:
        import numpy as np

        self.reads.append((view_id, frame_index))
        timestamp_ms = int(round(frame_index / self.fps * 1000))
        frame = np.zeros((FRAME_HEIGHT, FRAME_WIDTH, 3), dtype="uint8")
        frame[0, 0, 0] = timestamp_ms & 0xFF
        frame[0, 0, 1] = (timestamp_ms >> 8) & 0xFF
        frame[0, 0, 2] = (timestamp_ms >> 16) & 0xFF
        return frame


@dataclass
class _TimestampDetector:
    persons: list[_Person]
    raise_always: bool = False

    def detect(self, frame: Any) -> list[_Detection]:
        if self.raise_always:
            raise RuntimeError("inference backend unavailable")
        timestamp_ms = int(frame[0, 0, 0]) | (int(frame[0, 0, 1]) << 8) | (int(frame[0, 0, 2]) << 16)
        return [
            _Detection(bbox=list(person.bbox), confidence=0.8)
            for person in self.persons
            if person.active(timestamp_ms)
        ]


def _projector_for(persons: Iterable[_Person]):
    """按 bbox 中心横向位置匹配到场景里的人员，返回其球场坐标。"""
    lookup = [person for person in persons if person.court_xy is not None]

    def _projector(x: float, _y: float) -> tuple[float, float] | None:
        best: _Person | None = None
        best_distance = 1e9
        for person in lookup:
            center_x = (person.bbox[0] + person.bbox[2]) / 2.0
            distance = abs(center_x - x)
            if distance < best_distance:
                best = person
                best_distance = distance
        return best.court_xy if best is not None else None

    return _projector


def _box(x: float) -> list[float]:
    """在 (x, 40) 处生成一个 24x56 的框。"""
    return [x, 40.0, x + 24.0, 96.0]


def _court_xy(index: int) -> tuple[float, float]:
    """双打四人的真实球场位置：前两名落在 A 端侧（y<22ft），后两名落在 B 端侧。

    分侧配额选取要求每侧各两名，场景数据因此也必须是两侧各两名：四人同侧会让预检
    诚实地降级为"候选不足"——那是本次变更要消除的旧数据形态，不是期望行为。x 坐标
    刻意保持 2/6/10/14，使投影仍按 bbox 中心 x 匹配到同一名球员。
    """
    return (2.0 + index * 4.0, 6.0 if index < 2 else 38.0)


TEST_CONFIG = BootstrapPreflightConfig(
    window_count=3,
    window_span_ms=2000,
    frames_per_window=4,
    max_frames_total=20,
    min_hits_for_candidate=2,
    min_bbox_width_px=4,
    min_bbox_height_px=6,
    target_court_threshold=0.65,
)


@pytest.fixture(autouse=True)
def _clean_cache():
    clear_preflight_cache()
    yield
    clear_preflight_cache()


def _run(
    *,
    persons: list[_Person],
    views: list[str] | None = None,
    expected: int = 4,
    config: BootstrapPreflightConfig = TEST_CONFIG,
    sync_trusted: bool = False,
    projector: bool = True,
    detector: Any | None = None,
):
    views = views or ["cam_1"]
    source = _PersonIndexedFrameSource()
    return run_bootstrap_preflight(
        frame_source=source,
        detector=detector if detector is not None else _TimestampDetector(persons=persons),
        view_ids=views,
        clip_start_ms=0,
        clip_end_ms=10_000,
        expected_player_count=expected,
        config=config,
        court_projector_for=(lambda _view_id: _projector_for(persons)) if projector else None,
        sync_trusted=sync_trusted,
        multiview_reason="双摄同步不可信",
    )


# ── 开场尚未入场 ──


def test_middle_window_wins_when_players_arrive_late():
    """开头只有两名场外人员、中段四名目标球员持续可见时，选中段四人。"""
    inside = [
        _Person(bbox=_box(20 + index * 40), court_xy=_court_xy(index)) for index in range(4)
    ]
    outside = [_Person(bbox=_box(200), court_xy=(-30.0, 70.0), active_to_ms=3900)]
    persons = inside + outside
    for person in inside:
        person.active_from_ms = 4000

    result = _run(persons=persons)

    assert result.status == "available"
    assert len(result.candidates) == 4
    assert all(candidate.timestamp_ms >= 4000 for candidate in result.candidates)
    assert all(
        candidate.evidence.target_court_membership >= 0.65 for candidate in result.candidates
    )
    assert len({candidate.candidate_id for candidate in result.candidates}) == 4
    assert result.reference_frame is not None
    assert result.reference_frame.timestamp_ms >= 4000


def test_off_target_court_people_are_never_used_to_fill_slots():
    """邻场人员必须被排除；排不出四人时返回不足，而不是凑满。"""
    inside = [_Person(bbox=_box(20 + index * 40), court_xy=_court_xy(index)) for index in range(2)]
    neighbours = [
        _Person(bbox=_box(180), court_xy=(-40.0, 80.0)),
        _Person(bbox=_box(205), court_xy=(-45.0, 85.0)),
    ]
    result = _run(persons=inside + neighbours)

    assert result.status == "insufficient_candidates"
    assert len(result.candidates) == 2
    codes = {item.code for item in result.diagnostics}
    assert DIAG_PREFLIGHT_OUT_OF_TARGET_COURT in codes
    assert DIAG_PREFLIGHT_INSUFFICIENT in codes


# ── 主参考画面只画该帧实际观测到的框 ──


def test_reference_frame_overlay_only_contains_same_moment_boxes():
    """候选的最佳画面来自不同帧时，主参考画面不得混用异时刻的框。"""
    persons = [_Person(bbox=_box(20 + index * 40), court_xy=_court_xy(index)) for index in range(4)]
    # P1 只在 8000ms 之后出现，其余三人全程可见 → 参考帧不可能同时含四人。
    persons[0].active_from_ms = 8000
    result = _run(persons=persons)

    reference = result.reference_frame
    assert reference is not None
    observed_ids = set(reference.observed_bboxes)
    assert observed_ids
    # 主参考画面里的每个框都必须属于"该帧真的观测到"的候选
    for candidate_id, bbox in reference.observed_bboxes.items():
        candidate = next(item for item in result.candidates if item.candidate_id == candidate_id)
        assert candidate.view_id == reference.view_id
        assert bbox == candidate.bbox


def test_singles_only_returns_two_candidates():
    persons = [_Person(bbox=_box(20 + index * 40), court_xy=_court_xy(index)) for index in range(4)]
    result = _run(persons=persons, expected=2)
    assert result.status == "available"
    assert len(result.candidates) == 2
    assert [candidate.suggested_slot for candidate in result.candidates] == [1, 2]


# ── 双机位 ──


def test_secondary_view_is_used_only_when_sync_is_trusted():
    persons = [_Person(bbox=_box(20 + index * 40), court_xy=_court_xy(index)) for index in range(4)]
    untrusted = _run(persons=persons, views=["cam_1", "cam_2"], sync_trusted=False)
    assert untrusted.multiview_used is False
    assert DIAG_PREFLIGHT_NO_SYNC in {item.code for item in untrusted.diagnostics}

    trusted = _run(persons=persons, views=["cam_1", "cam_2"], sync_trusted=True)
    assert trusted.multiview_used is True
    assert DIAG_PREFLIGHT_NO_SYNC not in {item.code for item in trusted.diagnostics}


def test_secondary_view_supplies_candidates_missing_from_primary():
    """A 机位只有两人可靠，B 机位在对应时间可补足 —— 可信同步下允许补强。"""
    persons = [_Person(bbox=_box(20 + index * 40), court_xy=_court_xy(index)) for index in range(4)]
    source = _CompositeFrameSource(
        {
            "cam_1": [persons[0], persons[1]],
            "cam_2": [persons[2], persons[3]],
        }
    )
    result = run_bootstrap_preflight(
        frame_source=source,
        detector=_PerViewTimestampDetector(
            {"cam_1": [persons[0], persons[1]], "cam_2": [persons[2], persons[3]]}
        ),
        view_ids=["cam_1", "cam_2"],
        clip_start_ms=0,
        clip_end_ms=10_000,
        expected_player_count=4,
        config=TEST_CONFIG,
        court_projector_for=lambda _view_id: _projector_for(persons),
        sync_trusted=True,
    )
    assert result.multiview_used is True
    assert result.status == "available"
    assert {candidate.view_id for candidate in result.candidates} == {"cam_1", "cam_2"}


def test_secondary_view_does_not_refill_slots_with_the_same_two_people():
    persons = [_Person(bbox=_box(20 + index * 40), court_xy=_court_xy(index)) for index in range(4)]
    source = _CompositeFrameSource({"cam_1": persons[:2], "cam_2": persons})
    result = run_bootstrap_preflight(
        frame_source=source,
        detector=_PerViewTimestampDetector({"cam_1": persons[:2], "cam_2": persons}),
        view_ids=["cam_1", "cam_2"], clip_start_ms=0, clip_end_ms=10_000,
        expected_player_count=4, config=TEST_CONFIG,
        court_projector_for=lambda _view_id: _projector_for(persons), sync_trusted=True,
    )

    assert result.status == "available"
    assert [candidate.view_id for candidate in result.candidates].count("cam_1") == 2
    assert [candidate.view_id for candidate in result.candidates].count("cam_2") == 2
    assert sorted(round(candidate.court_xy[0]) for candidate in result.candidates) == [2, 6, 10, 14]
    assert all("cam_2" in candidate.source_views for candidate in result.candidates)


def test_source_timestamp_mapping_is_preserved_on_secondary_candidates():
    persons = [_Person(bbox=_box(20 + index * 40), court_xy=_court_xy(index)) for index in range(4)]

    class _OffsetFrameSource(_CompositeFrameSource):
        def source_timestamp_ms(self, view_id: str, reference_timestamp_ms: int) -> int:
            return reference_timestamp_ms + (100 if view_id == "cam_2" else 0)

    source = _OffsetFrameSource({"cam_1": persons[:2], "cam_2": persons[2:]})
    result = run_bootstrap_preflight(
        frame_source=source,
        detector=_PerViewTimestampDetector({"cam_1": persons[:2], "cam_2": persons[2:]}),
        view_ids=["cam_1", "cam_2"], clip_start_ms=0, clip_end_ms=10_000,
        expected_player_count=4, config=TEST_CONFIG,
        court_projector_for=lambda _view_id: _projector_for(persons), sync_trusted=True,
    )

    assert result.status == "available"
    canonical_times = {
        timestamp for window in result.windows for timestamp in sample_timestamps_ms(window, TEST_CONFIG.frames_per_window)
    }
    assert all(
        candidate.timestamp_ms - 100 in canonical_times
        for candidate in result.candidates if candidate.view_id == "cam_2"
    )


class _CompositeFrameSource:
    """同一时刻不同机位返回不同场景的替身帧源。"""

    def __init__(self, persons_by_view: dict[str, list[_Person]]) -> None:
        self.persons_by_view = persons_by_view
        self.fps = 30.0
        self.frame_count = 60_000

    def read(self, view_id: str, frame_index: int) -> Any:
        import numpy as np

        timestamp_ms = int(round(frame_index / self.fps * 1000))
        frame = np.zeros((FRAME_HEIGHT, FRAME_WIDTH, 3), dtype="uint8")
        frame[0, 0, 0] = timestamp_ms & 0xFF
        frame[0, 0, 1] = (timestamp_ms >> 8) & 0xFF
        frame[0, 0, 2] = (timestamp_ms >> 16) & 0xFF
        # 机位 id 用第 60 行标记，供 PerView 检测器区分。
        frame[60, 0, 0] = 1 if view_id == "cam_1" else 2
        return frame


class _PerViewTimestampDetector:
    def __init__(self, persons_by_view: dict[str, list[_Person]]) -> None:
        self.persons_by_view = persons_by_view

    def detect(self, frame: Any) -> list[_Detection]:
        timestamp_ms = int(frame[0, 0, 0]) | (int(frame[0, 0, 1]) << 8) | (int(frame[0, 0, 2]) << 16)
        view_id = "cam_1" if int(frame[60, 0, 0]) == 1 else "cam_2"
        return [
            _Detection(bbox=list(person.bbox), confidence=0.8)
            for person in self.persons_by_view.get(view_id, [])
            if person.active(timestamp_ms)
        ]


# ── 降级路径 ──


def test_detector_failure_degrades_instead_of_raising():
    result = _run(
        persons=[],
        detector=_TimestampDetector(persons=[], raise_always=True),
    )
    assert result.status == "unavailable"
    assert DIAG_PREFLIGHT_NO_DETECTIONS in {item.code for item in result.diagnostics}


def test_missing_calibration_is_reported_and_no_court_evidence_is_faked():
    persons = [_Person(bbox=_box(20 + index * 40), court_xy=None) for index in range(4)]
    result = _run(persons=persons, projector=False)
    assert DIAG_PREFLIGHT_NO_CALIBRATION in {item.code for item in result.diagnostics}
    assert all(
        candidate.evidence.target_court_membership is None for candidate in result.candidates
    )
    assert all(candidate.court_xy is None for candidate in result.candidates)


def test_frame_budget_is_bounded_and_reported():
    config = BootstrapPreflightConfig(
        window_count=6,
        window_span_ms=2000,
        frames_per_window=4,
        max_frames_total=5,
        min_hits_for_candidate=2,
    )
    persons = [_Person(bbox=_box(20 + index * 40), court_xy=_court_xy(index)) for index in range(4)]
    result = _run(persons=persons, config=config)
    assert result.sampled_frame_count <= 5
    assert DIAG_PREFLIGHT_BUDGET_EXHAUSTED in {item.code for item in result.diagnostics}


def test_same_input_is_deterministic_and_cached():
    persons = [_Person(bbox=_box(20 + index * 40), court_xy=_court_xy(index)) for index in range(4)]
    cache_key = bootstrap_cache_key(
        video_signature="v1",
        clip_start_ms=0,
        clip_end_ms=10_000,
        match_format="doubles",
        sync_signature="good",
        calibration_signature="cal-1",
        model_version="yolo11n.pt",
        config=TEST_CONFIG,
    )
    first = _run(persons=persons)
    source = _PersonIndexedFrameSource()
    second = run_bootstrap_preflight(
        frame_source=source,
        detector=_TimestampDetector(persons=persons),
        view_ids=["cam_1"],
        clip_start_ms=0,
        clip_end_ms=10_000,
        expected_player_count=4,
        config=TEST_CONFIG,
        court_projector_for=lambda _view_id: _projector_for(persons),
        cache_key=cache_key,
    )
    assert [item.candidate_id for item in second.candidates]
    # 同一 key 再次请求 → 命中缓存，不再读帧。
    reads_before = len(source.reads)
    third = run_bootstrap_preflight(
        frame_source=source,
        detector=_TimestampDetector(persons=persons),
        view_ids=["cam_1"],
        clip_start_ms=0,
        clip_end_ms=10_000,
        expected_player_count=4,
        config=TEST_CONFIG,
        court_projector_for=lambda _view_id: _projector_for(persons),
        cache_key=cache_key,
    )
    assert len(source.reads) == reads_before
    assert [item.candidate_id for item in third.candidates] == [
        item.candidate_id for item in second.candidates
    ]
    assert [item.bbox for item in first.candidates] == [item.bbox for item in second.candidates]


# ── 窗口规划 ──


def test_clip_range_beyond_media_is_clamped_and_reported():
    """片段请求超出视频长度时必须收窄并说明，而不是静默给出"零候选"。"""
    persons = [_Person(bbox=_box(20 + index * 40), court_xy=_court_xy(index)) for index in range(4)]
    # 300 帧 @30fps → 10 秒媒体；却请求 0–60 秒
    source = _PersonIndexedFrameSource(frame_count=300)
    result = run_bootstrap_preflight(
        frame_source=source,
        detector=_TimestampDetector(persons=persons),
        view_ids=["cam_1"],
        clip_start_ms=0,
        clip_end_ms=60_000,
        expected_player_count=4,
        config=TEST_CONFIG,
        court_projector_for=lambda _view_id: _projector_for(persons),
    )
    codes = {item.code for item in result.diagnostics}
    assert DIAG_PREFLIGHT_CLIP_CLAMPED in codes
    assert result.clip_end_ms == 10_000
    assert result.status == "available"
    assert all(candidate.timestamp_ms <= 10_000 for candidate in result.candidates)
    assert all(window.end_ms <= 10_000 for window in result.windows)


def test_window_planning_starts_at_the_middle_and_expands_outwards():
    windows = plan_windows(clip_start_ms=0, clip_end_ms=20_000, config=TEST_CONFIG)
    assert windows[0].origin == "mid"
    assert [window.origin for window in windows[1:3]] == ["earlier", "later"]
    assert all(0 <= window.start_ms < window.end_ms <= 20_000 for window in windows)


def test_window_timestamps_are_sorted_and_deduped():
    windows = plan_windows(clip_start_ms=0, clip_end_ms=2000, config=TEST_CONFIG)
    for window in windows:
        values = sample_timestamps_ms(window, 4)
        assert values == sorted(set(values))
        assert len(values) == 4
        assert values[0] >= window.start_ms
        assert values[-1] <= window.end_ms


def test_one_tracklet_cannot_absorb_two_people_in_one_frame():
    import numpy as np

    frame = np.zeros((FRAME_HEIGHT, FRAME_WIDTH, 3), dtype="uint8")
    tracklets: list[_Tracklet] = []
    common = dict(
        tracklets=tracklets, view_id="cam_1", frame=frame,
        config=TEST_CONFIG, projector=lambda x, y: (x / 10, y / 10), extractor=None,
    )
    _absorb_detections(
        **common, frame_index=0, timestamp_ms=0,
        detections=[(_box(20), 0.8)],
    )
    _absorb_detections(
        **common, frame_index=1, timestamp_ms=100,
        detections=[(_box(22), 0.8), (_box(38), 0.8)],
    )

    assert len(tracklets) == 2
    assert sorted(tracklet.hits for tracklet in tracklets) == [1, 2]
    assert all(len(set(tracklet.timestamps_ms)) == tracklet.hits for tracklet in tracklets)
    assert all(len(tracklet.court_points) == tracklet.hits for tracklet in tracklets)


def test_reference_frame_uses_all_real_observations_not_only_best_crops():
    candidates = []
    for index in range(4):
        tracklet = _Tracklet(
            view_id="cam_1", first_timestamp_ms=100, first_frame_index=3,
            first_bbox=_box(20 + index * 40), first_center=(32 + index * 40, 68),
            timestamps_ms=[100, 200],
            bboxes=[_box(20 + index * 40), _box(22 + index * 40)],
        )
        candidate = PlayerBootstrapCandidateV2(
            candidate_id=f"candidate-{index}", suggested_slot=index + 1,
            view_id="cam_1", timestamp_ms=200, bbox=_box(22 + index * 40),
        )
        candidates.append((candidate, tracklet))

    reference = _build_reference_frame(
        candidate_tracklets=candidates,
        windows=[PreflightWindow(ordinal=0, start_ms=50, end_ms=150, origin="mid")],
    )
    assert reference is not None
    assert reference.timestamp_ms == 100
    assert len(reference.candidate_ids) == 4
    assert reference.observed_bboxes["candidate-0"] == _box(20)


# ── 跨帧同人合并 ──


def _absorb_sequence(
    detections_by_time: list[tuple[int, int, list[list[float]]]],
) -> list[_Tracklet]:
    """按 (frame_index, timestamp_ms, bboxes) 序列喂给逐帧吸收，返回轨迹列表。"""
    import numpy as np

    frame = np.zeros((FRAME_HEIGHT, FRAME_WIDTH, 3), dtype="uint8")
    tracklets: list[_Tracklet] = []
    for frame_index, timestamp_ms, bboxes in detections_by_time:
        _absorb_detections(
            tracklets=tracklets,
            view_id="cam_1",
            frame=frame,
            frame_index=frame_index,
            timestamp_ms=timestamp_ms,
            detections=[(bbox, 0.8) for bbox in bboxes],
            config=TEST_CONFIG,
            projector=lambda x, y: (x / 10, y / 10),
            extractor=None,
        )
    return tracklets


def test_duplicate_boxes_for_one_player_are_merged_into_one_tracklet():
    """检测器对同一人给出重叠框后，同一名球员只应产生一条轨迹。"""
    tracklets = _absorb_sequence(
        [
            (0, 0, [_box(20)]),  # 首次出现
            (1, 100, [_box(22), _box(23)]),  # 同一人的两个重叠框 → 逐帧规则只能收一个
            (2, 200, [_box(24)]),  # 此后单框被第二条轨迹认领
            (3, 300, [_box(25)]),
        ]
    )
    assert len(tracklets) == 2, "同刻两个框必须先各自成轨，才谈得上合并"
    left, right = tracklets
    assert left.hits == 2 and right.hits == 3
    assert _tracklets_are_same_player(left, right, TEST_CONFIG) is True

    merged = _merge_duplicate_tracklets(tracklets, TEST_CONFIG)

    assert len(merged) == 1
    assert merged[0].timestamps_ms == [0, 100, 200, 300]
    assert merged[0].first_timestamp_ms == 0
    assert merged[0].first_frame_index == 0
    assert len(merged[0].court_points) == merged[0].hits


def test_two_teammates_standing_close_are_not_merged():
    """每个采样时刻都各自有观测的两名球员必须保持两条轨迹，即使贴得很近。"""
    tracklets = _absorb_sequence(
        [
            (0, 0, [_box(20), _box(22)]),
            (1, 100, [_box(20), _box(22)]),
            (2, 200, [_box(20), _box(22)]),
        ]
    )

    assert len(tracklets) == 2
    left, right = tracklets
    assert min(left.hits, right.hits) == 3
    assert _tracklets_are_same_player(left, right, TEST_CONFIG) is False
    assert len(_merge_duplicate_tracklets(tracklets, TEST_CONFIG)) == 2


# ── 分侧配额选取 ──


def _scored(
    view: str,
    *,
    x: float,
    court_y: float,
    score: float,
    timestamp_ms: int = 0,
) -> tuple[str, _Tracklet, float, dict]:
    tracklet = _Tracklet(
        view_id=view,
        first_timestamp_ms=timestamp_ms,
        first_frame_index=0,
        first_bbox=_box(x),
        first_center=(x + 12.0, 68.0),
        timestamps_ms=[timestamp_ms],
        bboxes=[_box(x)],
        confidences=[0.8],
        court_points=[(5.0, court_y)],
        frame_width=FRAME_WIDTH,
        frame_height=FRAME_HEIGHT,
    )
    return (view, tracklet, score, {})


def test_selection_prefers_evidence_over_screen_position():
    """综合分更高的候选必须入选，哪怕它在画面里更靠右（旧实现按最左 4 个取人）。"""
    ordered = [
        _scored("cam_1", x=200.0, court_y=6.0, score=0.90),  # 分最高但最靠右
        _scored("cam_1", x=20.0, court_y=6.0, score=0.50, timestamp_ms=10),
        _scored("cam_1", x=40.0, court_y=6.0, score=0.40, timestamp_ms=20),
        _scored("cam_1", x=60.0, court_y=6.0, score=0.30, timestamp_ms=30),
        _scored("cam_1", x=80.0, court_y=6.0, score=0.20, timestamp_ms=40),
        _scored("cam_1", x=300.0, court_y=38.0, score=0.70, timestamp_ms=50),
    ]

    selected, side_by_tracklet, unfilled = _select_by_side_quota(
        ordered, expected_player_count=4, config=TEST_CONFIG
    )

    assert 0.90 in [item[2] for item in selected], "分数最高（也最靠右）的候选不得因画面位置被丢弃"
    # A 端侧两名按画面 x 编号，其后是 B 端侧一名
    assert [item[2] for item in selected] == [0.50, 0.90, 0.70]
    assert side_by_tracklet[id(ordered[0][1])] == "end_a"
    assert unfilled == {"end_b": (1, 2)}


def test_doubles_quota_takes_two_per_side():
    """一侧的高分候选再多也不能占满槽位：每侧各取两名。"""
    ordered = [
        _scored("cam_1", x=20.0, court_y=6.0, score=0.90),
        _scored("cam_1", x=60.0, court_y=6.0, score=0.80),
        _scored("cam_1", x=100.0, court_y=6.0, score=0.70),  # 同侧第三名必须落选
        _scored("cam_1", x=140.0, court_y=38.0, score=0.60),
        _scored("cam_1", x=180.0, court_y=38.0, score=0.50),
    ]

    selected, side_by_tracklet, unfilled = _select_by_side_quota(
        ordered, expected_player_count=4, config=TEST_CONFIG
    )

    assert [item[2] for item in selected] == [0.90, 0.80, 0.60, 0.50]
    assert [side_by_tracklet[id(item[1])] for item in selected] == [
        "end_a",
        "end_a",
        "end_b",
        "end_b",
    ]
    assert unfilled == {}


def test_candidates_carry_side_evidence():
    persons = [_Person(bbox=_box(20 + index * 40), court_xy=_court_xy(index)) for index in range(4)]

    result = _run(persons=persons)

    assert result.status == "available"
    assert [candidate.evidence.side for candidate in result.candidates] == [
        "end_a",
        "end_a",
        "end_b",
        "end_b",
    ]


def test_one_side_shortfall_is_reported_and_not_backfilled():
    """一侧可靠候选不足时不得用对侧补位：保留 2 名 A 端侧 + 1 名 B 端侧。"""
    persons = [
        _Person(bbox=_box(20), court_xy=(2.0, 6.0)),
        _Person(bbox=_box(60), court_xy=(6.0, 6.0)),
        _Person(bbox=_box(100), court_xy=(10.0, 6.0)),
        _Person(bbox=_box(140), court_xy=(2.0, 38.0)),
    ]

    result = _run(persons=persons)

    assert result.status == "insufficient_candidates"
    assert len(result.candidates) == 3
    assert DIAG_PREFLIGHT_SIDE_QUOTA_UNFILLED in {item.code for item in result.diagnostics}
    sides = [candidate.evidence.side for candidate in result.candidates]
    assert sides.count("end_a") == 2
    assert sides.count("end_b") == 1


def test_missing_projection_keeps_candidate_count_and_reports_no_calibration():
    """侧向全未知（无标定）时仍按证据分给出期望人数，不因为分侧而减少候选。"""
    persons = [_Person(bbox=_box(20 + index * 40), court_xy=_court_xy(index)) for index in range(4)]

    result = _run(persons=persons, projector=False)

    assert result.status == "available"
    assert len(result.candidates) == 4
    assert all(candidate.evidence.side is None for candidate in result.candidates)
    assert DIAG_PREFLIGHT_NO_CALIBRATION in {item.code for item in result.diagnostics}


# ── 与正式管线的语义一致性 ──


def test_side_semantics_match_formal_pipeline():
    """预检的分侧语义必须与正式管线同源：死区常量不得各写一份而漂移。"""
    from app.vision.player_tracking_engine.player_lock_manager import _BootstrapTracklet

    config = BootstrapPreflightConfig()

    assert config.side_dead_zone_ft == _BootstrapTracklet.SIDE_DEAD_ZONE_FT
    assert config.court_half_length_ft == COURT_LENGTH_FT / 2.0
    assert _tracklet_side([(5.0, 6.0)], config) == "end_a"
    assert _tracklet_side([(5.0, 38.0)], config) == "end_b"
    assert _tracklet_side([(5.0, 22.0)], config) is None
    assert _tracklet_side([(5.0, 21.0)], config) is None
    assert _tracklet_side([None], config) is None
