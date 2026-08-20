"""fix-multiview-player-identity D2：playerMarkers team 语义与稳定排序回归测试。"""

from __future__ import annotations

from types import SimpleNamespace

from app.schemas.analysis import canonical_player_side
from app.services.real_report_builder import _tracks_to_player_markers


def _fake_track(track_id: str, x_ft: float = 5.0, y_ft: float = 10.0):
    return SimpleNamespace(
        track_id=track_id,
        court_point=SimpleNamespace(x=x_ft, y=y_ft),
    )


def test_canonical_player_side_doubles() -> None:
    """双打：Player_1/2 → near，Player_3/4 → far。"""
    assert canonical_player_side("Player_1", True) == "near"
    assert canonical_player_side("Player_2", True) == "near"
    assert canonical_player_side("Player_3", True) == "far"
    assert canonical_player_side("Player_4", True) == "far"


def test_canonical_player_side_singles() -> None:
    """单打：Player_1 → near，Player_2 → far。"""
    assert canonical_player_side("Player_1", False) == "near"
    assert canonical_player_side("Player_2", False) == "far"


def test_canonical_player_side_non_canonical() -> None:
    """非 canonical id 返回空串（调用方兜底）。"""
    assert canonical_player_side("candidate_3", True) == ""
    assert canonical_player_side("track_7", False) == ""


def test_tracks_to_player_markers_sorted_by_number_and_side() -> None:
    """乱序输入 → 按 Player_N 数字升序，team 按槽位语义分侧。"""
    tracks = [
        _fake_track("Player_2"),
        _fake_track("Player_4"),
        _fake_track("Player_1"),
        _fake_track("Player_3"),
    ]
    markers = _tracks_to_player_markers(tracks, doubles=True)
    assert [m["id"] for m in markers] == ["Player_1", "Player_2", "Player_3", "Player_4"]
    assert [m["team"] for m in markers] == ["near", "near", "far", "far"]
    assert [m["label"] for m in markers] == ["A", "B", "C", "D"]


def test_tracks_to_player_markers_singles() -> None:
    """单打：Player_1=near、Player_2=far。"""
    tracks = [_fake_track("Player_2"), _fake_track("Player_1")]
    markers = _tracks_to_player_markers(tracks, doubles=False)
    assert [m["id"] for m in markers] == ["Player_1", "Player_2"]
    assert [m["team"] for m in markers] == ["near", "far"]


def test_tracks_to_player_markers_non_canonical_fallback() -> None:
    """非 canonical id 按 court_point.y 兜底（y<22 → near），不崩溃。"""
    tracks = [_fake_track("global_player_1", y_ft=5.0), _fake_track("global_player_2", y_ft=30.0)]
    markers = _tracks_to_player_markers(tracks, doubles=True)
    assert markers[0]["team"] == "near"
    assert markers[1]["team"] == "far"
