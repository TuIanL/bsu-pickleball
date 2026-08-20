"""per-player-zone-heatmap 变更测试：热力图按球员拆分 + 区域空间热力图 + 有效时间窗口。"""

from __future__ import annotations

from app.vision.pickleball_game_analysis.effective_time_windows import (
    rally_windows_from_events,
    resolve_effective_windows,
)
from app.vision.pickleball_game_analysis.visualization_data_builder import (
    PLAYER_HEX_COLORS,
    PositionVisualizationDataBuilder,
    _structured_to_dict,
)
from app.vision.pickleball_game_analysis.visualization_schemas import (
    VisualizationPoint,
    canonical_player_id,
    display_player_label,
    player_palette_color,
)
from app.vision.pickleball_game_analysis.zone_stats import compute_zone_stats
from app.vision.pickleball_performance_engine.zone_metrics import zone_for


def _points(samples: list[tuple[str, float, float, float]]) -> list[VisualizationPoint]:
    """构造轨迹点：[(label, x_ft, y_ft, timestamp_seconds), ...]"""
    return [VisualizationPoint(x_ft=x, y_ft=y, timestamp_seconds=t, label=label) for label, x, y, t in samples]


# ── 6.1 builder：每球员网格 + 标签 + 空数据 ─────────────────────────


def test_builder_produces_per_player_grids_with_own_max_count():
    builder = PositionVisualizationDataBuilder()
    points = _points(
        [
            ("Player_1", 10, 20, 0.0),
            ("Player_1", 10, 20, 1.0),
            ("Player_1", 10, 20, 2.0),
            ("Player_2", 5, 5, 0.0),
        ]
    )
    data = builder.build(player_points=points, ball_points=[], bounce_points=[])

    assert data.heatmaps is not None
    assert data.heatmaps.visual_grid is not None
    # 合并网格 = 全局峰值（Player_1 三连点）
    assert data.heatmaps.visual_grid.max_count == 3
    assert [p.label for p in data.heatmaps.players] == ["P1", "P2"]
    max_counts = {p.label: p.grid.max_count for p in data.heatmaps.players}
    assert max_counts["P1"] == 3
    assert max_counts["P2"] == 1


def test_builder_empty_points_yield_null_heatmaps_and_zone_stats():
    data = PositionVisualizationDataBuilder().build(player_points=[], ball_points=[], bounce_points=[])
    assert data.heatmaps is None
    assert data.zone_stats is None


def test_display_player_label_mapping():
    assert display_player_label("Player_1") == "P1"
    assert display_player_label("player_3") == "P3"
    assert display_player_label("Unknown") == "Unknown"


# ── 6.2 zone stats：占用 / KCR / 平均距离 / 充分性 / 反馈 ────────────


def test_zone_for_three_bands_and_out_of_court():
    assert zone_for(10, 20) == "kitchen"
    assert zone_for(10, 29) == "kitchen"
    assert zone_for(10, 10) == "transition"
    assert zone_for(10, 37) == "transition"
    assert zone_for(10, 3) == "backcourt"
    assert zone_for(10, 40) == "backcourt"
    assert zone_for(10, 45) is None
    assert zone_for(10, -1) is None


def test_kcr_with_effective_windows():
    points = _points(
        [("Player_1", 10, 20, 0.0), ("Player_1", 10, 20, 1.0), ("Player_1", 10, 20, 2.0), ("Player_1", 10, 20, 3.0)]
    )
    stats = compute_zone_stats(points, effective_windows=[(0.0, 4.0)])
    player = stats[0]
    # 三对相邻帧均在窗口内 → kitchen 3s；分母=窗口总长 4s
    assert player.kitchen_control_rate == 0.75
    assert player.data_sufficiency == "sufficient"
    kitchen = next(z for z in player.zones if z.zone == "kitchen")
    assert kitchen.seconds == 3.0
    assert kitchen.occupancy == 0.75


def test_kcr_falls_back_to_total_duration_without_windows():
    points = _points([("Player_1", 10, 20, 0.0), ("Player_1", 10, 20, 1.0), ("Player_1", 10, 20, 2.0)])
    player = compute_zone_stats(points)[0]
    # 无窗口 → 分母 = 轨迹跨度 2s，厨房 2s
    assert player.denominator_seconds == 2.0
    assert player.kitchen_control_rate == 1.0


def test_data_sufficiency_marks_insufficient_when_sparse():
    points = _points([("Player_1", 10, 20, 0.0), ("Player_1", 10, 20, 1.0)])
    player = compute_zone_stats(points, effective_windows=[(0.0, 10.0)])[0]
    # 仅 1s 跟踪时间 / 10s 分母 = 0.1 < 0.3
    assert player.tracked_seconds == 1.0
    assert player.data_sufficiency == "insufficient"


def test_avg_distance_to_kitchen_line_time_weighted_in_meters():
    # 站在厨房线上 → 距离 0m → near_line（描述性档位，非能力评价）
    on_line = compute_zone_stats(_points([("P", 10, 15, 0.0), ("P", 10, 15, 1.0)]))[0]
    assert on_line.avg_distance_to_kitchen_line_m == 0.0
    assert on_line.feedback.level == "near_line"

    # 距厨房线 4ft ≈ 1.2m → moderate（0.9 < 1.2 ≤ 1.35）
    good = compute_zone_stats(_points([("P", 10, 19, 0.0), ("P", 10, 19, 1.0)]))[0]
    assert good.avg_distance_to_kitchen_line_m == round(4 * 0.3048, 1)
    assert good.feedback.level == "moderate"

    # 距厨房线 7ft ≈ 2.13m → deep
    far = compute_zone_stats(_points([("P", 10, 8, 0.0), ("P", 10, 8, 1.0)]))[0]
    assert far.avg_distance_to_kitchen_line_m == round(7 * 0.3048, 1)
    assert far.feedback.level == "deep"
    assert "参考基准" in far.feedback.summary
    # 描述性文案不携带能力评价措辞（design D4）。
    for word in ("优秀", "良好", "不足"):
        assert word not in far.feedback.summary


def test_nvz_occupancy_rate_and_deprecated_alias():
    """nvz_occupancy_rate 为 canonical 字段；kitchen_control_rate 为同值 deprecated alias。"""
    player = compute_zone_stats(_points([("Player_1", 10, 15, 0.0), ("Player_1", 10, 15, 1.0)]))[0]
    assert player.nvz_occupancy_rate == player.kitchen_control_rate


def test_avg_distance_own_side_kitchen_line():
    """own-side 口径：球员主半场为 near 时量 near 厨房线，不量对方线。

    near 侧厨房线 y=15（距网 7ft）；far 侧厨房线 y=29。球员站 y=4（near 后场）：
    - own-side 距离 = |4-15| = 11ft；
    - 旧口径（最近线）也是 11ft（near 线更近），此处验证跨中线点不量对方线。
    """
    # 球员主半场 near（中位 y=10 < net 22），单点短暂越过中线到 y=30（对方 NVZ 附近）。
    # own-side：该点仍量 near 线 |30-15|=15ft；旧口径会量 far 线 |30-29|=1ft。
    points = _points(
        [
            ("Player_1", 10, 5, 0.0),
            ("Player_1", 10, 10, 1.0),
            ("Player_1", 10, 10, 2.0),
            ("Player_1", 10, 30, 3.0),
        ]
    )
    player = compute_zone_stats(points)[0]
    # 时间加权：[(5→10): 5ft, (10→10): 0ft, (10→30): 15ft] → 平均 (5+0+15)/3 ≈ 6.67ft ≈ 2.0m
    expected_ft = (5.0 + 0.0 + 15.0) / 3.0
    assert player.avg_distance_to_kitchen_line_m == round(expected_ft * 0.3048, 1)


def test_zone_stats_ordered_like_scatter():
    points = _points([("Player_2", 5, 5, 0.0), ("Player_1", 10, 20, 0.0)])
    stats = compute_zone_stats(points, colors=["#a", "#b"])
    assert [p.label for p in stats] == ["P1", "P2"]
    assert stats[0].id == "Player_1"
    assert stats[1].id == "Player_2"
    assert stats[0].color == "#a"
    assert stats[1].color == "#b"


# ── 6.3 有效时间窗口解析 ──────────────────────────────────────────


def test_resolve_windows_clip_single_window():
    assert resolve_effective_windows(clip_start_ms=1000, clip_end_ms=5000) == [(1.0, 5.0)]


def test_resolve_windows_none_when_no_data():
    assert resolve_effective_windows() is None


def test_rally_windows_exclude_non_play_and_merge():
    events = [
        ("rally_start", 0),
        ("rally_end", 2000),
        ("non_play_start", 2100),
        ("non_play_end", 2800),
        ("rally_start", 3000),
        ("rally_end", 5000),
        ("rally_start", 2000),  # 与前一窗口重叠 → 合并
        ("rally_end", 4000),
    ]
    windows = rally_windows_from_events(events)
    assert windows == [(0.0, 5.0)]


def test_rally_windows_clamp_dangling_to_video_end():
    events = [("rally_start", 6000)]
    assert rally_windows_from_events(events, video_duration_ms=8000) == [(6.0, 8.0)]


def test_rally_windows_drop_invalid_pairs():
    assert rally_windows_from_events([("rally_end", 1000)]) == []
    assert rally_windows_from_events([("rally_start", 5000), ("rally_start", 6000), ("rally_end", 7000)]) == [
        (5.0, 7.0)
    ]


# ── 6.4 序列化契约：新字段存在 + 旧字段保留 ────────────────────────


def test_structured_to_dict_includes_players_and_zone_stats():
    points = _points([("Player_1", 10, 20, 0.0), ("Player_1", 10, 20, 1.0)])
    data = PositionVisualizationDataBuilder().build(player_points=points, ball_points=[], bounce_points=[])
    payload = _structured_to_dict(data)

    assert payload["heatmaps"]["visual_grid"]["max_count"] == 2
    assert payload["heatmaps"]["players"][0]["label"] == "P1"
    assert payload["heatmaps"]["players"][0]["id"] == "Player_1"
    assert payload["zone_stats"]["players"][0]["kitchen_control_rate"] == 1.0
    assert payload["zone_stats"]["players"][0]["zones"][0]["zone"] == "kitchen"
    assert payload["zone_stats"]["players"][0]["feedback"]["summary"]


def test_structured_to_dict_omits_zone_stats_when_absent():
    data = PositionVisualizationDataBuilder().build(player_points=[], ball_points=[], bounce_points=[])
    payload = _structured_to_dict(data)
    assert "zone_stats" not in payload
    assert "heatmaps" not in payload


# ── 6.5 canonical 身份对齐：id=Player_N、label=P1..P4、颜色按 canonical 序号 ──


def test_structured_players_use_canonical_ids_and_labels():
    points = _points(
        [
            ("Player_2", 5, 30, 0.0),
            ("Player_1", 10, 20, 0.0),
            ("Player_4", 15, 35, 0.0),
            ("Player_3", 5, 10, 0.0),
        ]
    )
    data = PositionVisualizationDataBuilder().build(player_points=points, ball_points=[], bounce_points=[])

    assert data.heatmaps is not None
    assert [p.id for p in data.heatmaps.players] == ["Player_1", "Player_2", "Player_3", "Player_4"]
    assert [p.label for p in data.heatmaps.players] == ["P1", "P2", "P3", "P4"]
    assert [p.id for p in data.scatter_plots.players] == ["Player_1", "Player_2", "Player_3", "Player_4"]
    assert [p.label for p in data.scatter_plots.players] == ["P1", "P2", "P3", "P4"]
    assert [p.id for p in data.player_trajectories] == ["Player_1", "Player_2", "Player_3", "Player_4"]
    assert [p.label for p in data.player_trajectories] == ["P1", "P2", "P3", "P4"]
    assert data.zone_stats is not None
    assert [p.id for p in data.zone_stats.players] == ["Player_1", "Player_2", "Player_3", "Player_4"]
    assert [p.label for p in data.zone_stats.players] == ["P1", "P2", "P3", "P4"]


def test_player_palette_color_by_canonical_number():
    colors = ["#c0", "#c1", "#c2", "#c3"]
    # 按 canonical 序号分配，与排序位置无关
    assert player_palette_color(colors, 0, "Player_1") == "#c0"
    assert player_palette_color(colors, 3, "Player_2") == "#c1"
    assert player_palette_color(colors, 0, "Player_4") == "#c3"
    # 非 canonical 回退排序索引
    assert player_palette_color(colors, 2, "unknown") == "#c2"
    assert player_palette_color([], 0, "Player_1") == ""


def test_structured_player_colors_assigned_by_canonical_number():
    points = _points(
        [
            ("Player_3", 5, 10, 0.0),
            ("Player_1", 10, 20, 0.0),
        ]
    )
    data = PositionVisualizationDataBuilder().build(player_points=points, ball_points=[], bounce_points=[])

    assert data.heatmaps is not None
    by_label = {p.label: p.color for p in data.heatmaps.players}
    # 保持现有调色板：Player_1 → PLAYER_HEX_COLORS[0]、Player_3 → PLAYER_HEX_COLORS[2]
    assert by_label["P1"] == PLAYER_HEX_COLORS[0]
    assert by_label["P3"] == PLAYER_HEX_COLORS[2]


def test_canonical_player_id_uppercases_lowercase_prefix():
    assert canonical_player_id("player_2") == "Player_2"
    assert canonical_player_id("Player_2") == "Player_2"
