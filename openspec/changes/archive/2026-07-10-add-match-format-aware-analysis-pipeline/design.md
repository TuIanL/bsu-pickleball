## Context

当前比赛制式（单打/双打）虽然在前端上传页面可选、在 `AnalysisUploadMetadata` 中持久化、并在任务详情页展示为标签，但从未影响分析流水线的行为。PrimaryPlayerSelector、PlayerLockManager、PlayerIdentityManager 全部从全局配置读取固定的 `4` 人设置，导致单打视频分析时可能出现：

- 多余的身份槽位（Player_3/Player_4）
- 无意义的双打间距指标
- 热力图和散点图为不存在的球员生成空白图
- 前端报告不区分"单打不适用"和"双打识别不完整"

## Goals / Non-Goals

**Goals:**
- 上传页的"单打/双打"选择在完整分析链路中生效（按钮 → API → Job → Worker → Pipeline → 球员框 → 骨架 → 身份 → 轨迹 → 热力图 → 指标 → 报告）
- 单打严格限制正式目标球员为 2 人，双打保持 4 人，且分侧配额强制执行
- `doubles_spacing` 等双打专属指标在单打中标记为 `not_applicable`
- 识别不完整（expected≠observed）时输出诊断但不伪造球员
- 历史任务（matchFormat 缺失或为 doubles）完全兼容，不改变现有结果

**Non-Goals:**
- 不修改 YOLO 检测逻辑（YOLO 仍需检测画面中所有人，赛制感知模块从中选择目标比赛球员）
- 不回退或重写现有的四人跟踪、骨架、小地图、热力图实现——只让它们根据 MatchAnalysisContext 动态适配
- 不引入新的前端展示组件（只是隐藏/显示现有模块）
- 不修改标定、球场检测、球检测等非球员相关组件

## Decisions

### D1: MatchAnalysisContext 只包含领域事实

`MatchAnalysisContext` 只封装稳定的比赛领域事实。算法内部配置（如 `PlayerGroupProfile`）由独立的派生函数构建，不存储在 Context 中。

```python
MatchFormat = Literal["singles", "doubles"]

class MatchAnalysisContext(BaseModel):
    schema_version: Literal["match-analysis-context.v1"]
    match_format: MatchFormat
    expected_player_count: Literal[2, 4]
    players_per_side: Literal[1, 2]
    near_side_quota: Literal[1, 2]
    far_side_quota: Literal[1, 2]
    enable_doubles_spacing: bool
```

映射规则：

| 字段 | singles | doubles |
|------|---------|---------|
| `match_format` | `"singles"` | `"doubles"` |
| `expected_player_count` | `2` | `4` |
| `players_per_side` | `1` | `2` |
| `near_side_quota` | `1` | `2` |
| `far_side_quota` | `1` | `2` |
| `enable_doubles_spacing` | `False` | `True` |

`PlayerGroupProfile` 由 `build_player_group_profile(context)` 派生：

```python
def build_player_group_profile(ctx: MatchAnalysisContext) -> PlayerGroupProfile:
    if ctx.match_format == "singles":
        return PlayerGroupProfile(expected_same_side_others=0, expected_opposite_players=1)
    return PlayerGroupProfile(expected_same_side_others=1, expected_opposite_players=2)
```

**理由**：artifact 中不暴露内部评分实现，未来修改 group score 不需要升级 MatchContext Schema。JSON 序列化更稳定。AnalysisPipelineResult 使用 Pydantic BaseModel 更符合项目 schema 风格。

### D2: PlayerGroupProfile 替代 group consistency 硬编码

`_group_consistency_scores()` 中现有硬编码：

```python
side_score = min(1.0, same_side_count / 1.0) * 0.45 \
           + min(1.0, opposite_side_count / 2.0) * 0.55
```

`same_side_count` 和 `opposite_side_count` 均排除了当前候选自身。改用赛制配置：

```python
@dataclass(frozen=True)
class PlayerGroupProfile:
    expected_same_side_others: int  # 除自己外的同侧期望人数
    expected_opposite_players: int  # 对侧期望人数

singles_profile = PlayerGroupProfile(
    expected_same_side_others=0,
    expected_opposite_players=1,
)

doubles_profile = PlayerGroupProfile(
    expected_same_side_others=1,
    expected_opposite_players=2,
)
```

评分方式改为偏差匹配分而非除法：

```python
def _count_match_score(actual: int, expected: int) -> float:
    return 1.0 - min(1.0, abs(actual - expected) / max(1, expected))

side_score = (
    _count_match_score(same_side_count, profile.expected_same_side_others) * 0.45
    + _count_match_score(opposite_side_count, profile.expected_opposite_players) * 0.55
)
```

**理由**：临时的 `group_weight=0.0` 解决方案回避了问题而非解决它。单打中如果同侧出现路人，`group_consistency_score` 应该正确反映"同侧不应有其他人"的语义，而不是关闭评分。

### D3: PrimaryPlayerSelector 移入 _run_tracking + quota-aware 最终选择

当前 PrimaryPlayerSelector 在 `AnalysisPipeline.__init__` 中创建。改为在 `_run_tracking` 中创建：

```python
def _run_tracking(self, ..., match_context: MatchAnalysisContext) -> _TrackingRunOutput:
    group_profile = build_player_group_profile(match_context)
    primary_player_selector = PrimaryPlayerSelector(
        max_subjects=match_context.expected_player_count,
        group_profile=group_profile,
        ...
    )
```

**理由**：
1. PrimaryPlayerSelector 持有 `_qualities`、`_history`、诊断和训练样本等每轮 tracking run 的状态，在 Pipeline 级别持有会造成跨任务污染（即使当前 factory 每任务重建，语义上也不应如此）
2. 三个带状态的球员组件（Selector、LockManager、IdentityManager）生命周期完全一致——都在 `_run_tracking` 中创建，在结束时销毁
3. `AnalysisPipeline.__init__` 继续只负责全局基础依赖，不接受任务级参数

**但仅靠评分排序不能保证分侧配额**。当前 `select()` 最终是 `candidates[:max_subjects]`，同侧高置信度路人可能挤掉另一侧正式球员。因此 Selector 末尾增加 quota-aware 最终选择：

```python
selected_candidates = self._select_balanced_candidates(
    candidates=candidates,
    positions_by_track_id={},
    near_quota=match_context.near_side_quota,
    far_quota=match_context.far_side_quota,
)
```

规则：
1. 所有候选按 side 分组（从 `positions_by_track_id` 或 `feature.mean_court_position` 推断）
2. 每组内按评分排序，最多取该侧配额数
3. `unknown` 侧候选暂不占用明确配额，在配额用尽前可进入任一侧
4. 两侧均不足时再进入 fallback

**Attention 路径必须同样经过 quota-aware final selection**。不能由 `selected_by_attention` 直接覆盖选择结果。

### D4: Bootstrap 分侧配额与统一分配路径

**当前问题**：
- `_try_early_lock` 和 `_try_lock_slot` 不设置 `side_hint`
- `_finalize_bootstrap` 按置信度排序后顺序分配到 slot，不分近端/远端
- 单打中两个候选可能都被分配到同一侧

**改造**：

第一步：重命名 `_is_in_near_court_area` → `_is_in_court_neighborhood`，消除语义混淆。

第二步：BootstrapTracklet 增加稳定的 side 推断方法：

```python
@dataclass
class _BootstrapTracklet:
    frame_indices: list[int] = field(default_factory=list)
    confidences: list[float] = field(default_factory=list)
    court_xs: list[float] = field(default_factory=list)
    court_ys: list[float] = field(default_factory=list)

    SIDE_DEAD_ZONE_FT = 2.0

    def inferred_side(self, half_length: float) -> str | None:
        if not self.court_ys:
            return None
        median_y = statistics.median(self.court_ys)
        if abs(median_y - half_length) < self.SIDE_DEAD_ZONE_FT:
            return None
        return "near" if median_y < half_length else "far"
```

使用中位数而非均值——对抗单帧投影异常点。

第三步：新增 PlayerLockConfig 中的分侧配额：

```python
@dataclass
class PlayerLockConfig:
    target_player_count: int = 4
    near_side_quota: int = 2      # 新增
    far_side_quota: int = 2       # 新增
    allow_quota_fallback: bool = True  # 新增
    ...
```

第四步：创建统一分配方法，替代三条路径各自的分配逻辑：

```python
def _assign_candidate_to_slot(
    self,
    slot: PlayerSlot,
    track_id: int,
    side: str | None,
    frame_index: int,
    confidence: float,
    observed_frames: int,
) -> AssignResult:
```

这个方法统一负责：检查 side quota、绑定 `current_track_id`、记录 `track_id_history`、设置 `assignment_side`、设置 tentative/locked 状态、更新 `_track_to_slot`、记录 diagnostic。

第五步：slot 新增 `assignment_side` 字段（不同于 `side_hint`——只记录首次分配时的半场，不随比赛移动更新），同时保留逐帧动态的 `current_side`。

第六步：side occupancy 不从可变计数器读取，改为从 slot 状态派生：

```python
@property
def near_occupancy(self) -> int:
    return sum(
        1 for slot in self.slots.values()
        if slot.assignment_side == "near"
        and slot.state in ("tentative", "locked", "lost")
    )
```

最多 4 个 slot，实时扫描几乎无成本，且避免 reset/reassign/fallback 替换导致计数器不一致。

### D5: Bootstrap deadline fallback + fallback_tentative 可纠正状态

```
bootstrap_max_frames 前:
  严格按配额分配
  near_occupancy < near_side_quota 才能占 near slot
  far_occupancy < far_side_quota 才能占 far slot

bootstrap_max_frames 后:
  1. 先分配 side 明确且配额未满的候选
  2. 再考虑 side=unknown 的候选（位于 dead zone）
  3. 仍不足时，allow_quota_fallback=True 允许降级
  4. 必须记录 side_quota_fallback diagnostic
```

**关键：fallback 分配的身份不应永久锁定。** 单打中如果远端球员被遮挡导致 fallback 选择了第二名近端路人，而 20 帧后远端球员出现，当前设计"不允许抢占"会导致整场使用错误身份。

新增 `fallback_tentative` slot 状态：

```
状态流:
  严格配额分配 → tentative → locked
  fallback 分配 → fallback_tentative

fallback_tentative slot:
  - 可以输出为低置信度临时候选
  - 可以被缺失侧的正式候选替换
  - 替换必须记录 diagnostic
  - 达到 fallback_promotion 条件后才转 locked

locked slot:
  - 不允许普通候选抢占
  - 只通过正常 reset/reassign 机制改变
```

替换条件：

```python
can_replace_fallback(
    fallback_slot: PlayerSlot,
    new_candidate: PlayerFramePosition,
    half_length: float,
) -> bool:
    # 必须有明确的 side
    # 如果 candidate_side == missing_side
    # 且 candidate_confidence > fallback_slot.confidence_ema * margin
    # 且 candidate 持续出现超过 fallback_replacement_min_frames
```

增加配置：

```python
fallback_promotion_frames: int = 90       # fallback_tentative 持续多久可升级为 tentative
fallback_replacement_margin: float = 1.15  # 替换需要置信度超过原 candidate 的比例
```

降级诊断示例：

```python
# 初始 fallback
{
  "event": "side_quota_fallback",
  "match_format": "singles",
  "expected": {"near": 1, "far": 1},
  "assigned": {"near": 2, "far": 0}
}

# fallback 被替换
{
  "event": "side_quota_fallback_replaced",
  "slot_id": "player_2",
  "old_track_id": 18,
  "new_track_id": 25,
  "expected_side": "far",
  "reason": "correct_side_candidate_appeared"
}
```

### D6: Metrics 赛制感知（兼容式扩展）

当前 `PerformanceMetrics.doubles_spacing` 类型为 `List[DoublesSpacingSummary]`，前端对应 `Array<{pair, ...}>`。改为对象类型属于合同变更。

采用兼容式扩展：保持 `doubles_spacing: List[DoublesSpacingSummary]` 不变（单打时空数组），新增 `metric_statuses` 旁路字段。

```python
class PerformanceMetrics(BaseModel):
    distances: List[DistanceMetric]
    speeds: List[SpeedSummary]
    kitchen_dwell: List[ZoneDwellMetric]
    doubles_spacing: List[DoublesSpacingSummary]  # 不变，单打时空数组
    heatmap: Heatmap
    metric_statuses: dict[str, MetricStatus] = {}  # 新增
    ...
```

```python
class MetricStatus(BaseModel):
    status: Literal["available", "not_applicable", "insufficient_players"]
    reason: str = ""
    expected_player_count: int | None = None
    observed_player_count: int | None = None
```

`_compute_metrics` 接收 `match_context`：

```python
statuses = {}
if match_context.enable_doubles_spacing:
    statuses["doubles_spacing"] = MetricStatus(status="available")
else:
    statuses["doubles_spacing"] = MetricStatus(
        status="not_applicable",
        reason="singles_match",
        expected_player_count=2,
    )
```

双打但人数不足时通过调用点设置 `insufficient_players`。

前端通过 `metric_statuses.doubles_spacing?.status === "not_applicable"` 判断是否隐藏双打模块。旧前端忽略 `metric_statuses` 字段，`doubles_spacing` 为空数组不会崩溃。

### D7: 统一 `player_analysis_hard_limit` + 配置校验

三个独立人数上限（`primary_player_max_subjects`、`player_identity_max_players`、`player_lock_target_player_count`）可能配置成不一致值。合并为一个统一容量配置：

```python
# 新增
player_analysis_hard_limit: int = 4
```

三个旧配置名保留为 deprecated alias，启动时检测冲突：

```python
# 启动校验示例
if settings.player_analysis_hard_limit < match_context.expected_player_count:
    raise PipelineConfigurationError(
        code="PLAYER_CAPACITY_BELOW_MATCH_REQUIREMENT",
        expected=match_context.expected_player_count,
        configured_limit=settings.player_analysis_hard_limit,
    )
```

运行时每个组件统一使用经过校验的 `effective_player_count`：

```python
effective_player_count = min(
    match_context.expected_player_count,
    settings.player_analysis_hard_limit,
)
```

但容量不足时**不静默 min**——采用明确拒绝：

```python
if settings.player_analysis_hard_limit < match_context.expected_player_count:
    raise PipelineConfigurationError(...)
```

**理由**：三个独立值配置不一致时难以排查（如 Selector=4, Lock=2, Identity=3）。统一后系统容量声明与比赛需求不匹配时明确报错，而非伪装成识别失败。

### D8: Formal eligibility 链修正

当前 Pipeline 中正式 eligible track 的构造：

```python
primary_selections = self.primary_player_selector.select(...)
lock_update = player_lock_manager.update(
    positions=frame_positions,
    suggestions=primary_selections,
)
eligible_track_ids = lock_update.eligible_track_ids | suggested_track_ids
```

这个并集意味着即使 LockManager 因配额拒绝了一名候选，`suggested_track_ids` 仍会把它带回正式链路。修正为：

```python
formal_eligible_track_ids = lock_update.eligible_track_ids
```

两种集合的用途分离：

| 集合 | 用途 |
|------|------|
| `suggested_track_ids` | bootstrap 排序提示、debug overlay、selector diagnostics、attention 训练样本 |
| `formal_eligible_track_ids` | PlayerIdentityManager、tracking overlay、RTMPose、player trajectory、minimap、heatmap、metrics |

```python
frame_detections = self._tracks_to_frame_detections(
    ...,
    eligible_track_ids=lock_update.eligible_track_ids,  # 仅 LockManager 接纳的 track
)
player_samples = identity_manager.update(
    ...,
    eligible_track_ids=lock_update.eligible_track_ids,
)
```

如果担心 Bootstrap 前几十帧没有正式框（LockManager 尚未锁定任何 slot），可以单独定义一个 `preview_candidate_ids` 用于 debug overlay，但不能写入正式 artifact。

### D9: 分析结果携带 match_context

`AnalysisPipelineResult` 和 `PlayerTrajectoryArtifact` 增加：

```json
{
  "match_context": {
    "match_format": "singles",
    "expected_player_count": 2,
    "players_per_side": 1
  },
  "observed_player_count": 2,
  "player_ids": ["Player_1", "Player_2"]
}
```

前端报告据此判断：
- `expected=2, observed=2` → 正常单打
- `expected=2, observed=1` → 一名球员未稳定识别
- `expected=4, observed=2` → 双打识别不完整

## Risks / Trade-offs

| Risk | Mitigation |
|------|-----------|
| 现有全局配置统一为 `player_analysis_hard_limit` 后，旧 `.env` 中三个独立值可能冲突 | 启动时检测旧配置名并 warn，以 `player_analysis_hard_limit` 为准；冲突时拒绝启动 |
| `fallback_tentative` 替换条件过于激进导致身份抖动 | 设置 `fallback_replacement_margin=1.15` 和 `fallback_replacement_min_frames`，仅在缺失侧确有更稳定候选时替换 |
| `fallback_tentative` 替换条件过于保守导致错误身份永久驻留 | 设置 `fallback_promotion_frames`，超时后升级为 `tentative`（不再可替换） |
| 历史任务无 matchFormat 字段 | build_match_context 对 None 返回 doubles 配置并写入 `match_format_defaulted` 兼容诊断 |
| 新请求传入非法 matchFormat（如 `"single"`） | API schema 的 Literal 校验会在进入 build_match_context 前返回 422 |
| PrimaryPlayerSelector 移入 _run_tracking 后诊断样本生命周期变短 | 诊断在每个 tracking run 结束时异步写入 artifact，不影响分析 |
| side=unknown（dead zone）的候选在 fallback 中分配到错误半场 | dead zone 阈值（SIDE_DEAD_ZONE_FT=2ft）需在实际数据中验证，可在配置中调整 |
| 历史 artifact 中 `doubles_spacing` 为数组，新 artifact 仍为数组 | 兼容式扩展：List 类型不变，新增 `metric_statuses` 旁路；旧前端不崩溃 |
