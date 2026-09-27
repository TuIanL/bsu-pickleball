## 1. 配置、契约与诊断码

- [x] 1.1 在 `BootstrapPreflightConfig` 新增 `court_half_length_ft: float = 22.0`、`side_dead_zone_ft: float = 2.0`、`merge_radius_normalized: float = 0.08`、`min_exclusive_observations: int = 2`、`merge_appearance_max_distance: float = 0.3`，确认全部进入 `signature()`（改配置即失效缓存）
- [x] 1.2 在 `schemas/rally_context.py` 的 `PlayerBootstrapCandidateEvidence` 新增可选字段 `side: str | None = None`（`"end_a"` / `"end_b"` / `None`），保持向后兼容，不升契约大版本
- [x] 1.3 新增诊断码 `DIAG_PREFLIGHT_SIDE_QUOTA_UNFILLED = "bootstrap_preflight_side_quota_unfilled"`（字符串文案一次定死，供下游与测试断言）
- [x] 1.4 保持预检引擎纯逻辑边界：不新增 cv2 / ultralytics 依赖

## 2. 同机位跨帧同人合并

- [x] 2.1 实现 `_merge_duplicate_tracklets(tracklets, config)`：同机位两两判定——互斥时刻数 ≥ `min_exclusive_observations`、最近配对距离与共享时刻距离均 < `merge_radius_normalized`、双方均有外观描述子时外观距离 ≤ `merge_appearance_max_distance`（否决条件）
- [x] 2.2 合并动作：按时间序拼接观测，同一时刻两条观测取置信度更高者，`first_*` 取最早观测，同步拼接 `hits` / `court_points` / `body_qualities` / 外观序列
- [x] 2.3 在 `run_bootstrap_preflight` 采样循环之后、`_select_candidates` 之前对每个机位调用合并，并保持逐帧吸收规则（"一条轨迹一帧至多吸收一个检测"）不变
- [x] 2.4 新增用例：同一时刻对同一人给出两个重叠框、此后该球员的观测被两条轨迹交替认领 → 只产生一个候选，锚点为最早观测，`candidate_id` 使用最早发生的帧
- [x] 2.5 新增用例：两条轨迹在多数采样时刻各自都有观测且位置保持分离（间距处于关联半径内）→ 不合并，仍是两名候选
- [x] 2.6 回归：`test_one_tracklet_cannot_absorb_two_people_in_one_frame` 保持通过（逐帧规则未被放宽）

## 3. 分侧配额选取与诚实降级

- [x] 3.1 实现侧向判定：对候选全部有效投影点的 canonical y 取中位数，`|中位 y − court_half_length_ft| < side_dead_zone_ft` → 未知，否则 `y < 22ft` → `end_a`、`y > 22ft` → `end_b`
- [x] 3.2 删除"分数前 N 名再按首帧画面中心 x 取最左"的收尾排序；改为证据排序（`(机位优先级, -综合分, 首帧时刻, 首帧中心 x, 首帧中心 y)`）后按赛制分侧配额取满，画面位置只作同侧内部稳定排序键
- [x] 3.3 槽位编号按端分组：`end_a` 侧 → P1、P2，`end_b` 侧 → P3、P4，同侧内部按首帧中心 x 升序；侧向未知的候选可被任一侧的剩余配额吸收
- [x] 3.4 一侧不足时不跨侧补位：写出 `bootstrap_preflight_side_quota_unfilled` 诊断（detail 含 `match_format`、每侧 expected / actual），状态按候选总数置 `insufficient_candidates`
- [x] 3.5 在候选证据里回填 `side`，让诊断与审计可核对每名候选落在哪一侧
- [x] 3.6 契约测试：`BootstrapPreflightConfig().side_dead_zone_ft == _BootstrapTracklet.SIDE_DEAD_ZONE_FT`，防止预检与正式管线的分侧语义漂移
- [x] 3.7 新增用例：综合证据分更高但画面更靠右的候选必须入选（本次错人的直接回归）
- [x] 3.8 新增用例：双打一侧 3 名高分、另一侧 2 名 → 每侧各取 2 名，槽位按侧分组，单侧不占 3 槽
- [x] 3.9 新增用例：一侧候选不足 → 不跨侧补位 + 出现 `side_quota_unfilled` 诊断 + 状态候选不足
- [x] 3.10 新增用例：无场地投影（`projector=False`）→ 侧向全未知，仍按证据分给出期望人数的候选，且既有"缺少标定"诊断保持可见

## 4. 更新既有预检测试场景数据

- [x] 4.1 把 `test_player_bootstrap_preflight.py` 的四人场景数据改为两侧各两名（如 `index < 2` 用 `y=6.0`、`index >= 2` 用 `y=38.0`），保持各用例原有断言意图（候选数量、诊断码、参考帧、双摄来源）
- [x] 4.2 复核并调整受口径影响的既有断言：`test_middle_window_wins_when_players_arrive_late`、`test_reference_frame_overlay_only_contains_same_moment_boxes`、`test_singles_only_returns_two_candidates`（单打需一侧一名）、`test_secondary_view_supplies_candidates_missing_from_primary`、`test_secondary_view_does_not_refill_slots_with_the_same_two_people`
- [x] 4.3 确认口径无关用例不被改动即通过：`test_same_input_is_deterministic_and_cached`、`test_frame_budget_is_bounded_and_reported`、`test_clip_range_beyond_media_is_clamped_and_reported`、`test_window_planning_starts_at_the_middle_and_expands_outwards`、`test_window_timestamps_are_sorted_and_deduped`、`test_source_timestamp_mapping_is_preserved_on_secondary_candidates`
- [x] 4.4 不得为了让旧断言通过而放宽分侧配额或恢复画面位置排序

## 5. 真实双摄素材离线验证（只读）

- [x] 5.1 用 `take ct_9997fa5aedf7`（clip `0–587166ms`、`sync_calibration` quality=good、`calib-398eec6b20` + `calib-4770b1cc59`）离线重跑预检，确认 P1–P4 变为正确的 2+2：近端 `(8.8, 49.1)` 与 `(16.1, 44.8)`，远端 `(7.1, -2.3)` 与 `(15.4, 0.5)`
- [x] 5.2 确认重复候选消失：不再出现 `bp_cam_1_17405_*` 这条由 f17405 重复框派生的轨迹，四条候选互不相同且综合分排序不再被画面 x 覆盖
- [x] 5.3 把前后对照（候选 id / `court_xy` / 综合分 / `hits` / 诊断码清单）写入 `openspec/changes/fix-preflight-candidate-selection/verification-real-take.md`；复现过程为只读，不写任何分析产物
- [x] 5.4 回归：`pytest backend/tests/test_player_bootstrap_preflight.py backend/tests/test_player_bootstrap_v2_contract.py`；并对预检相关后端选择集跑一次回归，确认无新增失败（既有基线失败只报告、不擅自修）

## 6. 收口

- [x] 6.1 `openspec validate fix-preflight-candidate-selection --strict` 通过
- [x] 6.2 复核 `proposal.md` 的 Impact 与实际改动一致（未越界到 `court_margin_ft`、冷请求耗时、抽帧预算记账、前端组件、正式 tracking 管线）
