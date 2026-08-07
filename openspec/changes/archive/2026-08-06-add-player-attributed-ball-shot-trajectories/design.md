## Context

重建链已输出 `reconstructed_ball_trajectory.v1`（事件切段 + 锚定 2.5D 重建），但击球事件没有球员归属；`BallContactEventDetector` 与 `BallEventResolver` **双重执行**对称 ±8 帧弹地抑制（`ball_contact_event_detector.py:144-154` 与 `ball_event_resolver.py:94`），被抑制候选仍被 Resolver 输出为正式 HIT 事件，Segmenter 把所有 HIT 当切段边界。

可用资产已齐备：

- `PlayerTrajectoryArtifact`：canonical `player_id` + `track_id` + bbox + image_footpoint + court 坐标（身份真值主源）。
- `PoseOverlayFrame`：per-track wrist/elbow 关键点；`ServeStartDetector._pose_motion_by_track()` 已实现上肢运动强度索引（serve_start_detector.py:756），可提取复用。
- `TrackingResult.overlay_frames`：逐帧检测，`analysis_pipeline.py:2005-2007` 已写入 canonical `player_id`（仅 `detected/tentative` 身份映射成功者）。
- `player-render-trajectory.v2`：roster / render_slot / identity_epoch，用于前端展示。

## Goals / Non-Goals

**Goals:**

- 为每次击球判定 hit 球员，输出 `confirmed / ambiguous / unassigned`，绝不强制归属。
- 建立 `shot_id` 概念，使"一次击球产生的完整球路"跨弹地段落传播 owner。
- 弹地抑制收敛为单一权威，防止快速网前击球被误抑制。
- 产物升级 v2，前端按 Shot 筛选/选中/统计，兼容旧 v1 产物。

**Non-Goals:**

- 不做球拍检测 / 挥拍方向判定。
- 不做整段 Shot 序列的动态规划 / Viterbi 解码（数据量足够后可作为后续演进）。
- 不重做球员跟踪与身份管理。
- 不改动 raw / cleaned 轨迹产物。

## Decisions

### D1. 两遍式事件链：prefilter → attribute → finalize

```
BallContactEventDetector（纯球侧突变检测）
        ↓ raw HitCandidate[]
BallEventResolver.prefilter()        ← 弹地抑制唯一权威
        ↓ SurvivingHitCandidate[]
BallHitPlayerAttributor.attribute()  ← 只对幸存候选计算球员证据
        ↓ PlayerAttribution[]
BallEventResolver.finalize()         ← 输出最终 TrajectoryEvent[]（含 event_status / ownership）
        ↓
BallFlightSegmenter → BallShotAssembler
```

使用三种独立数据对象，避免 `TrajectoryEvent` 在不同阶段变义：

- `PrefilteredHitCandidate`：`prefilter_status ∈ {survived, suppressed, rejected}`，suppressed/rejected 只进入 diagnostics，**不生成正式事件**。
- `PlayerAttribution`：`status ∈ {confirmed, ambiguous, unassigned}`，含 `player_id / confidence / score_margin / attributed_frame_index / candidate_scores`。
- `TrajectoryEvent`：增加 `event_status ∈ {confirmed, ambiguous}`、`hitter_player_id`、`ownership_status ∈ {confirmed, ambiguous, unassigned, not_applicable}`、`attribution`。

替代方案：两次调用同一个 `resolve()` 并修改对象——拒绝，阶段语义不清晰，易漂移。

### D2. 弹地抑制收敛为单一权威（I7, I8, I11）

- `BallContactEventDetector.detect()` **不再接收 `bounce_events`**，删除内部对称窗口抑制逻辑（ball_contact_event_detector.py:144-154），只负责方向突变、速度突变、局部拟合残差、refractory。
- `ResolverConfig` 改用时间语义：

```python
bounce_suppress_before_sec: float = 0.07
bounce_suppress_after_sec:   float = 0.10
bounce_suppress_confidence:  float = 0.60
```

- 判定公式（有符号时间差）：

```python
delta_sec = candidate.timestamp_sec - bounce.timestamp_sec
should_suppress = -before_sec <= delta_sec <= after_sec
```

- 语义：bounce 前 0.07s 内（落地前后轨迹突变误差）可抑制；bounce 后 0.10s 内（弹地定位误差容差）可抑制；**bounce 后超过 0.10s 的候选不得仅凭时间接近判死**，必须放行到 Attributor 由球员时空证据继续判断。这保护网前快速垫击（dead dink）。
- 配置快照写入产物 diagnostics：`{bounce_suppress_before_sec, bounce_suppress_after_sec, effective_fps, frame_stride}`。

### D3. 共享上肢证据模块（提取复用，而非直接调用私有方法）

从 `ServeStartDetector` 提取（不保留反向耦合，球路模块不得调用其私有方法）：

```python
@dataclass(frozen=True)
class UpperLimbFrameEvidence:
    track_id: str
    frame_index: int
    timestamp_seconds: float
    left_wrist_xy: tuple[float, float] | None
    right_wrist_xy: tuple[float, float] | None
    left_elbow_xy: tuple[float, float] | None
    right_elbow_xy: tuple[float, float] | None
    arm_motion_px_per_second: float

def build_upper_limb_evidence_index(pose_frames, *, smooth_window_frames) -> UpperLimbEvidenceIndex: ...
```

关键点：现有 `_pose_motion_by_track()` 只保留运动强度标量，**丢弃了 wrist/elbow 坐标**；而"球—手腕空间接近度"是归属最高权重证据，所以共享模块必须同时保留坐标与运动值。`ServeStartDetector` 迁移到共享索引，以行为回归测试保证发球结果不变。

### D4. 身份胶水层：PlayerTrajectoryArtifact 为主源

数据优先级：

| 用途 | 数据源 |
|---|---|
| 算法侧 canonical 真值 | `PlayerTrajectoryArtifact`（player_id + track_id + bbox + footpoint + court） |
| 姿态证据 | `PoseOverlayFrame`（track_id + wrist/elbow） |
| 降级来源 | `TrackingResult.overlay_frames`（仅 detected/tentative 有 canonical id） |
| 前端展示 | `player-render-trajectory.v2`（roster / render_slot / identity_epoch） |

**`TrackKey = str`** 统一规范化为字符串，禁止模块间混用 int/str：

```python
def normalize_track_key(track_id: int | str | None) -> str | None: ...
```

管线中确实存在"字符串检测 ID 转整数查 canonical 映射"的路径（analysis_pipeline.py:2005），契约测试必须覆盖：

```python
PlayerTrajectorySample(track_id=17, player_id="Player_2")
PoseSubject(track_id="17")
FrameDetection(track_id="17")
→ attribution 结果 player_id == "Player_2"
```

### D5. 归属评分与判定

多证据评分（证据不可用时对剩余权重重新归一化，RTMPose 未启用不使功能失效）：

```text
wrist_proximity       0.35   ← 球—任一手腕图像距离（人体尺度归一化）
bbox_proximity        0.25   ← 球—扩展人体框距离
arm_motion_peak       0.20   ← 接触窗口内上肢运动峰值
court_side            0.15   ← 球员所在半场一致性
temporal_freshness    0.05   ← 时间采样距离
```

- 球—手腕距离按人体尺度归一化：`normalized = pixel_distance / max(bbox_diagonal, minimum_scale_px)`，否则远端球员因画面尺度小而天然吃亏。
- 判定：

```text
confirmed   best_score >= attribution_min_score 且 best_score - second_score >= margin
ambiguous   分数达最低范围但第一/第二候选差距不足
unassigned  无足够球员证据
```

- 发球直接播种：`serve event.player_id → serve_seeded attribution → shot owner`，不走普通推断；`_serve_reset_events()` 补传被丢弃的 `player_id`（reconstruction_engine.py:44-67）。
- 归属结果只允许 canonical `Player_N`，不保存瞬时 track_id（I9）。

### D6. 接触时间窗：秒语义 + 非对称

不用固定帧数（任务可能 30/60fps、frame_stride 1/2/3、Pose 缺帧）：

```python
class HitPlayerAttributionConfig:
    contact_window_before_sec: float = 0.15   # ≈ 30fps 下 4.5 帧
    contact_window_after_sec:  float = 0.08   # ≈ +2.4 帧
    maximum_pose_sample_gap_sec:     float = 0.10
    maximum_tracking_sample_gap_sec: float = 0.12
```

hit 事件帧是"突变被检测到的帧"，真实接触在其前 1–3 帧，腕部速度峰值又在接触附近：查询 `[t - 0.15, t + 0.08]`，取球—任一手腕归一化距离最小帧，保存为 `attributed_frame_index`；运动峰值取窗口内 `max(arm_motion)`。

### D7. Shot 生命周期

```
边界                      对当前 Shot        是否开启新 Shot
confirmed hit            关闭               是
confirmed serve          关闭               是
ambiguous hit            关闭               是（owner 为 ambiguous/unassigned）
bounce                   保持               否（只切 flight segment）
suppressed / rejected hit 完全忽略           否
long tracking loss       关闭               否
end of stream            关闭               否
```

关键语义：**suppressed/rejected hit 是"误判候选被取消"而非球路中断**，不得关闭 Shot（否则 P1 球路在弹地后丢失归属，重新制造本变更要解决的问题）。`shot_id=null` 段（视频首拍前、long loss 后残余）不参与统计。

### D8. 半场交替序列校验（sanity check，非评分项）

Shot 序列完成后执行：连续两次 confirmed contact 归到同一半场 → 记录 `side_alternation_violation`。使用 **contact 时刻动态 side**（`hitter_side_at_contact`），不用 roster `initial_side`（换边后已过时）。

```python
if previous_side == current_side:
    if confidence < 0.85 or score_margin < 0.25:
        降级为 ambiguous（player_id 置 None）
    else:
        保留高可信视觉结论，仅打 diagnostics
```

错误来源可能为：当前 Shot 归属错、上一 Shot 归属错、side 数据漂移、伪 hit——故不无条件推翻。

### D9. 产物协议 v2

- 顶层 `player_roster`：`[{player_id, render_slot, initial_side}]`（来自 render v2）。
- 事件：`event_status`、`hitter_player_id`、`hitter_render_slot`、`attribution {status, confidence, method, candidate_scores, attributed_frame_index}`。
- 段：`segment_id`、`shot_id`、`hitter_player_id`、`ownership_status ∈ {confirmed, ambiguous, unassigned, not_applicable}`、`ownership_confidence`、`ownership_source_event_id`。
- `event_status`（是否为可信击球）与 `ownership_status`（能否确定击球者）严格分离。
- 旧 v1 产物不回写覆盖，前端读取时兼容降级。

### D10. 前端 Shot 级交互

- 保留扁平 segments 供 Three.js 渲染，新增 Shot 视图模型：

```ts
interface EstimatedBallShot {
  shotId: string;
  hitterPlayerId: string | null;
  hitterRenderSlot: string | null;
  ownershipStatus: "confirmed" | "ambiguous" | "unassigned" | "not_applicable";
  segmentIds: string[];
  startTimeSeconds: number; endTimeSeconds: number;
  durationSeconds: number; pointCount: number;
}
```

- Scene 选中升级为 `selectedShotId`：点击任意 segment 通过 `line.userData.shotId` 选中整个 Shot，多段同时高亮；3D 渲染仍为独立 segment line strip，不拼接几何线。
- 筛选按钮来自产物 `player_roster`（单打/双打/识别不足自适应），旧任务无归属字段隐藏筛选。
- "未归属"分组内部保留两个标签：**击球者不明**（unassigned/ambiguous shot）与 **无 Shot 上下文**（shotId=null segment），统计语义：总 Shot 数 = `shot_id` 去重（含 unassigned、不含 null）；球员击球数 = shot 去重且 `hitter_player_id == Player_N`。

## 不变量（写入规格与测试）

```
I1. 被 suppressed/rejected 的 hit candidate 不得进入正式事件列表。
I2. bounce 可创建新 flight segment，但不得改变 shot_id 或 hitter。
I3. 只有 confirmed/ambiguous contact、long loss 与流终止能改变 Shot 生命周期。
I4. 所有算法归属以 canonical Player_N 表示，瞬时 track_id 仅作证据索引键。
I5. 一次 Shot 可含一个或多个 segment；前端筛选、选中、统计均以 shot_id 为单位。
I6. 归属不充分时必须输出 ambiguous/unassigned，不得强制选择最近球员。
I7. Resolver.prefilter 是 bounce suppression 唯一权威；Detector 不得依据 bounce_events 修改候选状态。
I8. bounce suppression 使用有符号非对称时间窗口；超出 bounce 后容差的候选必须进入归属阶段。
I9. track_id 内部统一规范化为字符串；事件与 Shot 只保存 canonical Player_N。
I10. shot_id=null 表示无 Shot 上下文，不参与统计；ownership_status=unassigned 表示有 Shot 但击球者未知。
I11. suppressed/rejected candidate 不创建事件、不关闭/开启 Shot、不改动现有 Shot owner。
I12. bounce 只切分 flight segment；bounce 后快速真实击球必须能关闭上一 Shot 并开启下一 Shot。
```

## Risks / Trade-offs

- [弹地窗口参数偏差导致真实击球被抑制] → 非对称窗口 + 配置快照进 diagnostics；窗口边界测试（-0.05s / +0.08s / +0.12s / +0.20s）硬验收。
- [腕部证据在远端球员画面尺度小被低估] → 人体尺度归一化；无姿态时权重重归一化降级。
- [共享模块迁移改变 Serve 检测行为] → 行为回归测试保证发球结果不变，迁移与归属实现分开提交。
- [归属错误污染球员统计] → 宁缺毋滥：低证据必须 unassigned；半场交替只做降级与诊断，不硬改。
- [双打网前两名队友距离近锁错人] → 腕部运动峰值与手腕距离权重最高，bbox 距离次之；禁止仅用"最近脚点"。

## Migration Plan

1. 提取共享上肢证据模块 + Serve 检测迁移（回归测试通过后再进入下一步）。
2. Detector 移除弹地抑制、Resolver 拆 prefilter/finalize（现有行为经边界测试验证）。
3. Attributor + ShotAssembler 接入 pipeline，产物升级 v2。
4. 前端 Shot 级交互上线（v1 兼容路径保持可用）。
5. 回滚策略：v1 产物与旧前端路径保留，可逐层回退。

## Open Questions

- 半场交替校验需要动态 side 数据源：`hitter_side_at_contact` 从 PlayerTrajectoryArtifact 的 court 坐标推导，是否需要为该字段增加独立存储（当前设计为推导值）。
- 归属参数（attribution_min_score / margin）初始值需用小标注集标定，先给保守默认值。
