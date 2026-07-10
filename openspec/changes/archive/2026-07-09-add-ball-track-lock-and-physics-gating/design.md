## Context

现有 `BallTracker` 实现了一套基础的候选筛选流程：

```
detector raw candidates
  → 面积/长宽比硬过滤
  → 静止黑名单网格投票（32px 网格，60 帧阈值）
  → 候选评分（conf*1000 - dist*1.4 - area*4000）
  → 距离门控（max_jump_pixels=220, prediction_gate_pixels=260）
  → 静止候选局部检查（30 帧窗口，5px 半径）
  → 球场边界过滤
```

存在的问题：

1. **无状态感知**：评分和门控阈值在轨迹刚开始和已锁定时完全相同
2. **固定门控**：220/260px 阈值不随球速、缺失帧数、帧率变化
3. **预测脆弱**：仅用最后 2 点做线性外推，无速度平滑
4. **缺失恢复短**：统一 5 帧 max_missing，LOCKED 时也一样
5. **静止误报无上下文**：只检查球自身是否静止，不看球员是否还在运动
6. **无结构化拒绝原因**：无法调试为什么某个候选被选或拒

## Goals / Non-Goals

**Goals:**

- 引入四状态 BallTrackState：SEARCHING、TENTATIVE、LOCKED、LOST
- 状态感知的候选评分：不同状态下 detector confidence、prediction proximity、motion consistency、size consistency、court region 权重动态切换
- 动态物理门控：门控距离根据近期球速、缺失帧数、帧率、画面区域自动调整
- Missing-over-false-positive 策略：LOCKED 状态下无物理合理候选时输出 missing + predicted_position，不选远处假候选
- 增强锁定期缺失恢复：LOCKED 状态下容忍 8-12 帧缺失，缺失期间持续输出预测位置
- 球员运动上下文增强静止误检抑制：球不动 + 球员在动 + 比赛进行中 → 判定为静止误检
- 每一帧输出 per-candidate debug metadata（raw_confidence、final_score、rejection_reason、distance_to_prediction 等）

**Non-Goals:**

- 不修改 trajectory_cleaner.py、bounce_detector.py、court_adapter.py 的现有逻辑
- 不替换 YOLO ball detector 或不涉及模型重训练
- 不引入 Kalman filter、multi-hypothesis tracking、3D 物理模型（这些可作为后续增强）
- 不修改 pipeline 的任务编排或 artifact 写入路径
- 不涉及前端 debug overlay（只输出结构化数据字段，不负责渲染）
- 不修改球场边界体系（court_geometry.py）或已有投影逻辑

## Decisions

### Decision 1: State machine design (BallTrackState)

```
SEARCHING
  → 连续 plausible_hits >= tentative_min_hits = 2
  → TENTATIVE
    → 连续 plausible_hits >= lock_min_hits = 4
    → LOCKED
      → 当前帧无候选通过物理门控
      → LOST

LOST
  → 在 max_missing_frames_locked 内找到恢复候选
  → LOCKED

LOST
  → missing_frames > max_missing_frames_locked
  → SEARCHING
```

**Why enum over boolean?**
- 四状态比 `is_locked: bool + missing_frames: int` 更清晰
- 状态转移条件统一集中管理，每个状态的评分行为完全隔离
- 便于输出 debug 状态、测试特定状态转换

**Threshold 原则：**
- `tentative_min_hits`=2：避免单次候选就进入 TENTATIVE，防止单帧假阳初始化短命轨迹
- `lock_min_hits`=4-5：需要足够的多帧证据才能锁定，防止杂物序列意外锁定
- 这些参数应该可配置（在 BallTrackerConfig 中）

### Decision 2: Prediction model — smoothed velocity over last N points

当前实现：`predict_next_position()` 仅用最后 2 点的差值做外推。

改为：用最近 N 个 accepted points（N=3-5）计算平滑速度，然后外推：

```
smoothed_dx = avg(dx over last 3-5 pairs)
smoothed_dy = avg(dy over last 3-5 pairs)
predicted_x = last_x + smoothed_dx * missing_multiplier
predicted_y = last_y + smoothed_dy * missing_multiplier
```

**Why not Kalman filter in V1?**
- 常速度平滑已经能大幅改善当前 2 点外推的抖动问题
- Kalman filter 需要配置过程噪声/观测噪声协方差，调参成本高
- 第一版优先级是"快速修复"，Kalman 可以作为 V2 增强

**Why smoothing over averaging?**
- 直接平均最近 3-5 点位移，而不是用指数移动平均，保持计算简单
- 可以在轨迹点数不足 3-5 时动态退化为 2 点

### Decision 3: Dynamic physics gate calculation

当前固定阈值无法适配不同球速、缺失帧数、帧率。改为：

```
raw_gate = base_gate_pixels
    + speed_factor * recent_speed_px_per_frame
    + missing_factor * missing_frames
    + perspective_adjustment

dynamic_gate_pixels = clamp(raw_gate, min_gate_pixels, max_gate_pixels)
```

- `base_gate_pixels`：最小门控基础值（帧率相关，60fps 时可设为 40-60px）
- `speed_factor`：球速乘子（默认 1.5-2.0，使高速球有更大容差）
- `missing_factor`：每多一帧缺失的额外容差（默认 20-40px）
- `perspective_adjustment`：根据候选所在的画面区域粗略调整。第一版使用简单上下半区分段：
  ```
  近端（下半画面，球靠近镜头时）：multiplier ≈ 1.2-1.5
  远端（上半画面，球远离镜头时）：multiplier ≈ 0.8-1.0
  unknown（无 court metadata）：multiplier = 1.0
  ```
- `min_gate_pixels`：门控硬下限（默认 40-50px），防止慢速球（dink、发球前后）的 gate 过小导致误拒绝
- `max_gate_pixels`：门控硬上限（默认 600px），避免无限扩增

**Why min/max clamp?**
- 当 recent_speed 很低时，gate 不能小于 `min_gate_pixels`（否则发球前后的慢速球容易被误杀）
- 极端速度（扣杀、截击）时，gate 不应超过 `max_gate_pixels`（避免门控完全失效）

**Why simple region multiplier instead of full perspective model?**
- 第一版不需要复杂球场投影来算 perspective；上下半区粗略分段 + unknown fallback 即可
- 未来可升级为基于 homography 的精确视角因子，但不在本 change 范围内

**Why expand gate with speed?**
- 扣杀时球在画面近端可达 100+ px/frame 位移，固定 220px 可能误杀
- 慢速球（发球、近网）位移很小，固定 220px 过于宽松
- 动态门控在高速度时自动扩大，低速度时自动收紧

### Decision 4: Missing-over-false-positive enforcement inside _select_candidate

`_select_candidate()` 本身负责输出最终决策，而非"先选候选再在外面否决"。这样 debug metadata 和实际输出天然一致：

```
def _select_candidate(candidates, track_state) -> tuple[BallCandidate | None, str, str]:
    # 返回 (selected_candidate, overall_decision, reason)

    if not candidates:
        return None, "missing_no_candidates", "no_candidates"

    if track_state in (LOCKED, LOST):
        # 对每个候选先评分，再过滤：
        for c in sorted(candidates, key=score, reverse=True):
            if passes_physics_gate(c):
                return c, "accepted", None
        # 无候选通过门控 → 直接输出 missing
        return None, "missing_predicted_only", "no_candidate_passed_physics_gate"

    if track_state == SEARCHING:
        # 没有锁定轨迹，允许高置信候选初始化新轨迹
        return max(candidates, key=lambda c: c.confidence), "accepted", None

    # TENTATIVE: 综合评分，但不需要 missing-over-false-positive
    return max(candidates, key=score), "accepted", None
```

**Why inside _select_candidate, not after it?**
- 避免"评分说 accepted，但外层推翻为 missing"的不一致
- debug metadata（final_score、passed_physics_gate、rejection_reason）与最终输出同源，不需要额外同步
- SEARCHING 状态直接在函数内跳过 gate 检查，允许高置信远点初始化轨迹

### Decision 5: Player motion context for static suppression

现有静止黑名单的增强点：

**Current:** 仅基于候选自身运动检测静止（30 帧窗口 / 5px 半径）
**Enhanced:** 增加球员运动上下文和非比赛时间信号

接入方式：

```
pipeline 已有的 player centroids / skeletons
  → 计算球员重心帧间位移
  → 如果球员运动 < player_motion_min_pixels → 可能非比赛时间
  → 如果球员运动 > player_motion_min_pixels + 候选静止 → 静止误检
  → 如果球员运动 < player_motion_min_pixels → 不触发（可能发球前/暂停/捡球）
```

**Why not enforce without player context?**
- 发球前球员拿球静止时、捡球后球在地上、暂停时——球确实不动
- 没有球员上下文会误杀这些"合理静止"

**Data flow:**

```
BallTracker.update():
  accepts optional player_motion_pixels: float | None
  if player_motion_pixels is None:
      fallback to existing stationary blacklist-only behavior
  if player_motion_pixels > threshold AND candidate stationary:
      apply static_false_positive_penalty
```

这样 backward compatible：没有球员数据的 pipeline 不受影响。

### Decision 6: Debug metadata schema

每一帧的 debug output 分层存储：`BallFrameSample` 顶层只保留下游常用摘要字段，per-candidate 细节全部放进 `diagnostics`。

```python
# BallFrameSample 顶层新增字段（下游常用，直接可访问）：
@dataclass
class BallFrameSample:
    ...
    track_state: str | None = None          # SEARCHING / TENTATIVE / LOCKED / LOST
    predicted_position: Point2D | None = None
    overall_decision: str | None = None     # "accepted" | "missing_predicted_only" | "missing_no_candidates" | "rejected"

# diagnostics 内部存放完整的 per-candidate 决策记录：
@dataclass
class BallFrameDebug:
    track_state: str
    predicted_position: tuple[float, float] | None
    candidates: list[BallCandidateDebug]
    accepted_candidate_id: str | None
    overall_decision: str

@dataclass
class BallCandidateDebug:
    candidate_id: str
    bbox: tuple[float, float, float, float] | None
    raw_confidence: float
    final_score: float
    distance_to_prediction: float | None
    jump_distance: float | None
    passed_physics_gate: bool
    rejection_reason: str | None  # "physics_gate_rejected" | "static_false_positive" | "accepted" | ...

# 填充方式：BallTracker.update() 将 BallFrameDebug 存入 BallFrameSample.diagnostics
```

**Why split top-level vs diagnostics?**
- 下游消费者（trajectory_cleaner、bounce_detector、前端 overlay）只需要 `track_state`、`predicted_position`、`overall_decision`，不需要逐候选细节
- per-candidate 数据量大，仅在调试/调参时使用，全部塞进顶层会膨胀 schema
- diagnostics 字段已存在且兼容现有序列化（`to_jsonable` 自动处理）

**Why structured over free-text?**
- 后续 debug overlay 和日志分析需要结构化字段
- 测试断言可以直接检查 `sample.diagnostics["candidates"][0]["rejection_reason"] == "physics_gate_rejected"`
- 不做复杂序列化，保持 dataclass 兼容当前 schemas.py

## Risks / Trade-offs

### Risk 1: LOCKED 状态下过度拒绝真实球

**场景**：球速极快导致位移超过动态门控上限。

**Mitigation**：
- `speed_factor` 的默认值经过测试验证
- 增加 `max_gate_cap` 硬上限（如 600px），避免无限制扩增
- 在验收测试中覆盖扣杀、截击等快速场景

### Risk 2: 球员运动数据不可用

**场景**：旧 pipeline 或部分任务不生成 player centroids。

**Mitigation**：
- `player_motion_pixels` 参数为 `None` 时回退到现有静止黑名单行为
- 不影响核心状态机和门控功能

### Risk 3: 状态机参数调优困难

**场景**：`lock_min_hits`=4 在某些视频中太紧或太松。

**Mitigation**：
- 所有参数集中在 `BallTrackerConfig` 可配置
- 默认值通过测试集验证
- debug metadata 可在参数调优时提供每帧状态和决策原因

### Risk 4: 预测位置在 LOST 期逐渐漂离真实球

**场景**：球运动方向突然改变（变向、切球、网前截击），预测位置失效。

**Mitigation**：
- `max_missing_frames_locked`=8-12，不会无限制预测
- 恢复候选门控使用 extended gate（比 LOCKED 时更宽松）
- 长时间 LOST 后自动重置回 SEARCHING
