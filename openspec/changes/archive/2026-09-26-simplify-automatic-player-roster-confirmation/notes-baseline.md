# 预检数据与时间基准核对（任务组 1）

本文件是 change `simplify-automatic-player-roster-confirmation` 实施前的**事实核对记录**，
回答 tasks.md 的 1.1 / 1.2 / 1.3。结论都指向仓库中的具体实现，不是估计值。

## 1.1 时间基准与"同一时刻"匹配可用的字段

### 各环节的时间来源

| 环节 | 时间字段 | 语义 |
| --- | --- | --- |
| 前端所选片段 | `clipStartMs` / `clipEndMs` | **源视频**毫秒（`MultiViewAnalysisSetupPage.tsx` 由秒 × 1000 得出） |
| 预检取帧 | `cv2.CAP_PROP_POS_FRAMES` → 帧时刻 | 该机位**源文件 PTS**；帧号 = `round(ms/1000*fps)` |
| 双摄同步 | `dual_camera_sync.SyncCalibration`：`offset_seconds` / `rate` | `camera_time = offset + rate * reference_time` |
| 正式多视角轨迹 | `samples[].take_timestamp_ms` | canonical 参考机位时间轴（毫秒） |
| 正式多视角逐机位 | `view_observations[view_id].source_timestamp_ms` / `mapped_take_timestamp_ms` | 该机位源 PTS / 映射到 canonical 的时间 |
| 正式单视角轨迹 | `players[Player_N][].timestamp_seconds` | 处理时间轴（秒） |

### 可直接用于同时刻匹配的字段与误差

- **参考（A）机位**：预检帧时刻与正式 `take_timestamp_ms` 同源（同一文件 PTS + canonical 参考时间轴），
  误差只来自抽帧取整，量级 ≤ 一个抽帧步长；`frame_stride=2 @60fps` 约 33 ms。
- **B 机位**：预检帧时刻是 B 文件 PTS，正式产物给的是 canonical 时间；
  换算必须经 `map_reference_time(calibration, t)`，其帧选择误差由
  `CanonicalAnalysisClock` 的 `max_pairing_error_ms`（默认 `1000/30 ≈ 33.3 ms`）门控，
  超限即标 `unavailable_selection_error`。
- **单视角**：只有秒级 `timestamp_seconds`，且坐标单位是**米**（`court_unit: "m"`），
  与多视角的 ft 不同，必须换算（`×3.280839895`）。

### 由此确定的匹配容差

正式审计的锚点匹配容差取 **500 ms / 3.0 ft**（见
`analysis_rally_context_service.DEFAULT_ANCHOR_TIME_TOLERANCE_MS` /
`DEFAULT_ANCHOR_COURT_TOLERANCE_FT`）。

依据：球员移动速度约 6 ft/s，2 秒窗口内会位移约 12 ft，那样"位置相符"就失去证明力，
会退化为本 change 明确要取消的"全片宽松位置匹配"；500 ms 足够覆盖抽帧步长与 30/60 fps 取整误差。

## 1.2 可复用接口与降级原因

| 能力 | 复用入口 | 不可用时的降级 |
| --- | --- | --- |
| 场地标定 / 投影 | `calibration_service.get_calibration` → `homography.values`；`courtvision_calibration_engine.homography.image_to_court` | `bootstrap_preflight_calibration_unavailable`：候选按画面连续性排序，`court_xy=null`，明确不排除场外人员 |
| 机位朝向 | `court_frame.local_to_canonical`（`orientation=None` 时**抛错**，禁止猜测） | 同上；缺 `court_orientation` 时不投影 |
| 场景标定 | `MetricCourtSceneService.get_current(take_dir)` → `views[].{view_id, video_id, calibration_id, court_orientation}` | `bootstrap_runtime_scene_calibration_unavailable` / `..._not_ready` |
| 目标球场成员 | `PrimaryPlayerSelector` 的 `court_margin_ft`（配置 `primary_player_court_margin_ft=12.0`）与 `target_court_threshold=0.65` 语义 | 门槛不通过 → 排除且计入 `bootstrap_preflight_off_target_court`，**不补空槽** |
| 衣着描述子 | `player_appearance.ClothingAppearanceExtractor`（`clothing-hsv-lab.v1`，需要 ≥18×48 px 的框）+ `appearance_distance` | `bootstrap_preflight_appearance_unavailable`：外观只作辅助分，缺失不阻断 |
| 双机位关联 | `multiview.sync.load_sync_calibration` + `evaluate_sync_gate`（good/degraded → 可融合） | 非 good/degraded → `bootstrap_preflight_sync_untrusted`，各机位独立呈现 |
| 身份质量诊断 | `four_player_quality.py` / `four_player_identification_quality.json` | 既有产物质量不合格时不直接当候选（v2 走重新预检） |

## 1.3 可用的复核素材与抽帧预算

### 素材可得性（2026-09-27 更正）

- `backend/data/outputs/` 有 88 个 job 目录，其中 `players_trajectory.json` 均为**单视角 v1**
  形态（`players` 为 `Player_N → 观测列表` 的映射，坐标单位米）。
- 外接盘的 `2026-07-20/take_sync_20260720_122645_317228` 有两路真实视频、场景标定、
  同步校准和历史多视角正式产物；其中 `analysis/smoke-3c86f64f29/` 有
  `fused_player_trajectory.json` 与正式身份映射文件 `roster.json`。
  早先只查了 `roster_manifest.json`，误以为缺少正式映射；仓库的
  `StorageService.roster_manifest_json_path` 实际返回 `roster.json`。
- 因此本机可以做真实双摄候选人工核对和正式绑定审计。具体结果见
  [verification-real-take.md](verification-real-take.md)。

### 抽帧预算

本机全流程推理在 CPU（无 CUDA）。真实两路 1080p 视频的 16 帧预检实测
28.37 s，约 1.77 s/采样帧；另有首次打开视频探测媒体信息的耗时。
预检默认预算：`window_count=5`、`window_span_ms=3000`、`frames_per_window=4`、
`max_frames_total=20` → 单机位最多 20 帧、双机位同样 20 帧总量，
按实测比例，20 帧预检约 35 s；首次页面请求还受两路视频各约 13 s 的媒体信息探测影响。
预算耗尽时返回 `bootstrap_preflight_budget_exhausted`，并优先保留已完成窗口的候选。

### 时长的确定性

`plan_windows` 中段优先（0, −1, +1, −2, +2 …）决定**采样优先级**，而实际处理按时间升序，
以保证短时关联在时间轴上单调（否则从窗口 A 跳到更早的窗口 B 会被误判成新轨迹——
此问题在实施期由任务 5.1 的场景测试暴露并修复）。


真实素材的人工候选核对、耗时及正式绑定审计结果见 [verification-real-take.md](verification-real-take.md)。
