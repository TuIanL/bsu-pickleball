## Context

当前 `smooth-minimap-player-motion` 已归档并合入，`CourtTrackPostProcessor`、`CourtTrackObservation`、`CourtTrackEvent`、`RenderFrame`、`player_render_trajectory.json` 均已存在于主干。该 artifact 当前只包含扁平坐标序列（`frame_index`, `timestamp_seconds`, `x_ft`, `y_ft`, `source`, `confidence`），缺少以下关键渲染语义：

1. **渲染身份槽位**：前端 `StructuredScatterPlot` 按后端 `PLAYER_HEX_COLORS` 分配颜色，`StandardCourtPlan` 按前端 `TRACK_COLORS` 分配颜色，两套调色板互不统一，且 track ID 更换会导致颜色变化
2. **分段信息**：三个前端视觉组件各自推导轨迹连续性规则（跳距、时间缺口），缺乏统一的断线数据源
3. **投影质量**：前端无法感知点的投影可信度，无法对低质量点做样式区分
4. **视觉主题**：前后端颜色、半径、阈值各自硬编码，无统一契约

本变更将 artifact 从 v1 扩展为 v2，在不改变扁平 `samples` 结构的核心语义下，增补 `players` 和 `segments` 元数据、`render_slot`、`side`、`segment_id`、`identity_epoch`、投影质量字段和 `style_profile` 快照。

## Goals / Non-Goals

**Goals:**
- `render_slot` 由 PostProcessor 在完整轨迹上一次性分配，保证同 `player_id` 跨 track ID 颜色不变
- 基于 `(player_id, identity_epoch)` 和时空连续性进行语义分段，输出 `segment_id` 和 `segment` 元数据
- 在 `RenderFrame` 中保留投影质量字段（`projection_status`, `projection_confidence`, `footpoint_method`）
- 将视觉主题快照写入 artifact 的 `style_profile` 字段
- 保持扁平 `samples` 数组为唯一数据真源，`players` 和 `segments` 只存元数据
- `OverlayVideoWriter` 兼容 v2，仅在 `segment_id` 变化时清空 deque
- 前端提供 v1/v2 归一化函数，旧版 artifact 可降级使用

**Non-Goals:**
- 不修改 `MinimapVisualizer`、`PositionVisualizer`、`OverlayVideoWriter` 的颜色/主题/标记大小
- 不创建共享前端渲染组件库（`CourtSurface`、`TrajectoryLayer` 等）
- 不迁移 `StructuredScatterPlot` 或 `StandardCourtPlan` 到新数据源
- 不实现 `BounceMarker` 涟漪动画或 `useVideoClock`
- 不新增根目录 `shared/` JSON 文件
- 不修改 `PlayerIdentityManager` 或 `PlayerLockManager` 的 player_id 格式

## Decisions

### D1: render_slot 由 PostProcessor 一次性全量分配（固定 4 槽位）

**Decision:** `CourtTrackPostProcessor` 在输入所有 `CourtTrackObservation` 后，先建立全局 player roster，再按确定规则一次性分配 `render_slot`。不支持增量或流式分配。

`MAX_RENDER_SLOTS = 4`，`RenderSlot = Literal["slot_1", "slot_2", "slot_3", "slot_4"]`。不做可配置扩展——当前产品模式为单打 2 人或双打 4 人，身份管理层也最多维护四个稳定身份。未来若需支持 5 名以上真实人物，需重定义 slot 语义（跟随球员还是位置、换人后是否复用）、颜色表和主题资源，那应作为独立 Change。

**分配规则：**
1. 收集全部唯一 `player_id`（经 `canonical_player_id()` 规范化）
2. 若 `observed_player_count > MAX_RENDER_SLOTS`，抛出 `RenderSlotOverflowError`
3. natural sort（数字后缀优先解析：`Player_2` 排在 `Player_10` 前）
4. 无数字后缀时，按 `first_reliable_frame` 排序
5. 最后以完整 `player_id` 字符串为 tie-breaker
6. 同一 artifact 内不回收、不重新分配 slot；`identity_epoch` 变化不改变 slot

**错误处理:** `RenderSlotOverflowError` 应被 visualization/post-processing 阶段捕获，仅将 `player_render_trajectory` artifact 标记为 `failed`，不改动 tracking、ball、report 等其他 artifact 的状态。

**Rationale:**
- PostProcessor 在 `_run_tracking` 末尾调用，此时全部观测已收集完毕，天然适合全局视角分配
- 全局分配消解了"后半程新球员插入导致颜色交换"的问题
- 显式报错而非静默复用颜色，避免诊断困难
- 固定 4 槽位避免类型（`Literal["slot_1", ..."slot_4"]`）、配置值（`max_render_slots`）和主题颜色表（`slot_1~4`）三处不同步

**Alternatives considered:**
- 前端按 `player_id` 排序分配：导致多个组件各自排序结果可能不一致
- 按 `side + first_seen_order` 分配：side 随时间变化，换边后语义失效
- 可配置 max_render_slots：与 Literal 类型和主题颜色表冲突，且当前业务不需要

### D2: 扁平 samples 数组是唯一数据真源

**Decision:** artifact 保持 `samples: RenderFrame[]` 扁平数组，`players` 和 `segments` 仅保存元数据引用，不重复存储坐标。

```text
player_render_trajectory.json
├── players:  [{ player_id, render_slot, initial_side, ... }]
├── segments: [{ segment_id, player_id, break_before, start_frame_index, ... }]
└── samples:  [{ sequence_index, frame_index, player_id, segment_id, x_ft, y_ft, ... }]
```

**Rationale:**
- OverlayVideoWriter 按 `frame_index` 索引读取，扁平结构天然适合
- 前端时间窗口小地图按 `timestamp_seconds` 二分查找，同样适合扁平结构
- 避免嵌套结构与扁平结构数据不同步的问题

**Alternatives considered:**
- `players[].segments[].samples[]` 嵌套：OverlayVideoWriter 需要遍历多层才能找到当前帧
- 同时输出两套结构：数据重复，未来一致性难以保证

### D3: break_before 仅保存在 segment metadata 上

**Decision:** `RenderFrame` 不携带 `break_before` 字段。断线由 `segment_id` 变化驱动，断点原因仅在 `RenderSegmentMetadata.break_before` 中保存一次。

**Rationale:**
- 99% 的 sample 的 `break_before` 为 null，增加 JSON 体积无意义
- `segment_id` 变化本身已驱动 OverlayVideoWriter 的 deque 清空逻辑
- 断点原因只需一份用于调试/报告，不需要在每个 sample 上重复

### D4: identity_epoch 由上游身份管理链路生成，PostProcessor 只消费

**Decision:** `CourtTrackObservation.identity_epoch` 由上游身份管理链路（`PlayerIdentityManager` / `PlayerLockManager` / pipeline diagnostics cursor）生成并写入。`CourtTrackPostProcessor` 将其视为权威输入，不负责递增或重新计算 epoch。

**PostProcessor 处理顺序：读取上游 identity_epoch → 判读 epoch 变化与 CourtTrackEvent → 选择 break_reason → 切 segment。**

epoch 变化是最高优先级断点。当前只有已实现的 `player_reset_after_prolonged_loss` 事件会改变 epoch（通过 pipeline 侧的 `identity_epoch_by_player` 计数器递增）。未来上游实现 canonical identity reassignment 后，只要递增 `identity_epoch`，PostProcessor 无需修改即可自动切段。

首批保留 `identity_reassigned` 枚举值但当前不产生该事件。遇到未知 epoch 变化事件时生成 `identity_reset` 作为保守断点（不抛 NotImplemented）。

**segment 触发条件（PostProcessor 读取 epoch 后执行）：**

| 条件 | 新 segment | break_before |
|------|:---------:|--------------|
| `identity_epoch` 变化 | 是 | `identity_reset`（或 `identity_reassigned`） |
| 时间 gap > `max_visible_gap_seconds` | 是 | `visible_gap` |
| 距离跳变 > 阈值 | 是 | `distance_jump` |
| 投影连续失败后恢复 ^1 | 是 | `projection_gap` |
| 普通 track ID 碎片重连（时空连续） | 否 | — |
| side 从 near 变 far | 否 | — |

^1: 仅在 `CourtTrackEvent` 明确提供投影失败/恢复事件时，才生成 `projection_gap`。只有时间缺口、无明确投影失败事件时，统一生成 `visible_gap`。当前 `CourtTrackEvent` 尚不支持投影失败事件，首批不生成 `projection_gap`——该值保留在枚举中但不触发。

**Rationale:**
- `identity_epoch` 语义属于身份管理，不应在渲染层重新推导
- 上游增加新断点事件后 PostProcessor 自动适配，零维护成本
- `segment_id` 表达"当前点是否可以和上一个点连续画线"，独立于 epoch 语义

### D5: style_profile 与 segmentation_profile 分离写入 artifact

**Decision:** 视觉主题参数和轨迹分段参数作为两个独立快照写入 artifact，不混入同一对象。主题源文件放在 `backend/app/resources/court_render_profile.v1.json`，Python 通过 `importlib.resources` 读取。

**分离后的结构：**
```json
{
  "style_profile": {
    "version": "court-visual-theme.v1",
    "players": {
      "slot_1": "#22D3EE",
      "slot_2": "#FBBF24",
      "slot_3": "#A78BFA",
      "slot_4": "#F97316"
    },
    "ball": "#67E8F9",
    "bounce": "#FB923C",
    "outside_player": "#94A3B8",
    "player_trail_seconds": 2.5,
    "ball_trail_seconds": 1.0,
    "bounce_display_seconds": 0.8,
    "radius": { "min_px": 2.0, "max_px": 6.0 }
  },
  "segmentation_profile": {
    "version": "court-track-segmentation.v1",
    "jump_threshold_ft": 9.84,
    "max_visible_gap_seconds": 0.75
  }
}
```

**Rationale:**
- `style_profile` 是前端展示参数（颜色、半径、拖尾时长）；`segmentation_profile` 是 artifact 生成依据（跳距阈值、gap 阈值）
- 修改颜色不应使同一视频产生不同的 segment 划分
- 分开后两个 profile 可以独立升级：theme v2 只改颜色不改分段，segmentation v2 只调阈值不动视觉

前端 `DEFAULT_COURT_VISUAL_THEME_V1` 持续仅包含 style_profile 部分。

### D6: canonical_player_id() 在 PostProcessor 入口显式调用

**Decision:** PostProcessor 的 `build_tracks()` 入口处对所有 `obs.player_id` 执行 `canonical_player_id()` 规范化，即使输入观测已经在 pipeline 侧规范化过。

**Rationale:**
- 防止外部调用方绕过 pipeline 规范直接传入裸 `player_` 前缀
- 一行代码的防御性成本，避免 slot 分配和分段出现大小写不一致的 player_id

### D7: OverlayVideoWriter 仅做 segment-aware deque 清空

**Decision:** `OverlayVideoWriter` 继续消费扁平 `samples` 数组构建 `frame_table`。在更新每个球员的 deque 时，比较新 sample 的 `segment_id` 与 deque 队尾 sample 的 `segment_id`，不同则清空 deque 再追加。

```python
previous = trail[-1] if trail else None
if previous is not None and previous.segment_id != point.segment_id:
    trail.clear()
trail.append(point)
```

**Rationale:**
- frame_table 构建方式不变，回退路径不变
- 不引入颜色主题替换或 marker 尺寸重构
- 最小增量的语义修正

### D8: 前端 v1/v2 归一化

**Decision:** 前端提供 `normalizePlayerRenderTrajectory()` 函数，接受 `RawPlayerRenderTrajectoryV1 | RawPlayerRenderTrajectoryV2` 联合类型，输出统一的 `NormalizedPlayerRenderTrajectory`（所有字段必填）。

旧版 artifact 没有 `segment_id` 时，normalizer 使用统一的 continuity helper 推导多个 segment：
- `segment_id = legacy:{player_id}:e{epoch}:s{segment_index}`
- 按 `(player_id, identity_epoch)` 分组后，根据时间 gap 进一步切段（复用同一套 continuity 检查逻辑）
- 不假设一个 epoch 只对应一个 segment
- `render_slot` 按 player_id natural sort 分配（前端 fallback，仅用于旧数据）
- `side` 根据 y_ft 或已有 side 字段推导

新版 artifact 的 `render_slot` 由后端生成，normalizer 直接透传，不覆盖。

### D9: build_tracks() 保持向后兼容，新接口使用 process()

**Decision:** 当前 `build_tracks()` 返回 `list[RenderFrame]`，保留该签名不变。新增 `process()` 方法返回 `CourtTrackPostProcessResult`。`build_tracks()` 内部委托给 `process()`：

```python
def process(self, observations, events, fps, total_frames) -> CourtTrackPostProcessResult:
    result = self._normalize_player_ids(observations)
    result = self._build_roster(result)
    result = self._assign_render_slots(result)
    result = self._build_segments(result)
    result = self._filter_spikes_and_interpolate(result, fps, total_frames)
    return CourtTrackPostProcessResult(players=..., segments=..., samples=...)

def build_tracks(self, observations, events, fps, total_frames) -> list[RenderFrame]:
    return self.process(observations, events, fps, total_frames).samples
```

**Rationale:**
- 现有调用方（OverlayVideoWriter、测试）不被迫立即迁移
- `process()` 暴露完整结果供 pipeline 层消费
- 后续所有 consumer 迁移完成后可考虑废弃 `build_tracks()`

### D10: RenderFrame 分两层兼容（Raw vs Normalized）

**Decision:** 前端类型分为两层：

```ts
// JSON 反序列化层——字段全部可选，兼容 v1/v2
interface RawPlayerRenderFrame {
  frame_index: number;
  player_id: string;
  x_ft: number;
  y_ft: number;
  source: string;
  render_slot?: string | null;
  segment_id?: string | null;
  identity_epoch?: number | null;
  side?: string | null;
  // ...
}

// 归一化层——字段全部必填，normalizer 输出
interface NormalizedRenderFrame {
  frame_index: number;
  player_id: string;
  x_ft: number;
  y_ft: number;
  source: string;
  render_slot: string;
  segment_id: string;
  identity_epoch: number;
  side: "near" | "far" | "unknown";
  // ...
}
```

Python 侧同理：`RenderFrame` dataclass 保留默认值兼容旧调用方，v2 serializer 序列化前做完整性校验。

**Rationale:**
- 前端业务组件不应长期面对一堆 `?` 可选字段
- normalizer 是唯一需要处理兼容差异的地方

### D11: side 委托给项目已存在的 canonical side classifier

**Decision:** PostProcessor 不重新硬编码 `y > 22` 判断 near/far。side 赋值规则：

1. 原始 observation 已有可信 `side` 时，直接透传至对应 `RenderFrame`
2. 插值点继承当前 segment 内最近的 detected sample 的 side
3. 只有缺失时才调用统一 `classify_court_side(y_ft)` 推导

`RenderPlayerMetadata.initial_side`：第一个 `source == "detected"` 且 `confidence != null` 的 sample 的 side。`dominant_side`：统计 detected samples 中 near/far 占比，比例相同时为 `mixed`，无可靠点时为 `unknown`。

**Rationale:**
- 球场坐标约定和 near/far 定义已存在于 court geometry 模块，不应在 PostProcessor 中重复实现
- 避免任务层面 near/远端描述矛盾的问题

## Risks / Trade-offs

| Risk | Mitigation |
|------|------------|
| v2 artifact 新增必填字段（如 `render_slot`）导致旧 consumer 解析失败 | TypeScript 分为 `RawPlayerRenderFrame`（字段可选，接收 JSON）和 `NormalizedRenderFrame`（字段必填，normalizer 输出）；Python 使用 `getattr(obj, "render_slot", None)` |
| `first_reliable_frame` 因检测间隔/投影成功率波动导致两次 pipeline 的 slot 分配顺序不同 | 这不是 bug——渲染 artifact 是单次 pipeline 产物的快照。测试 fixture 固定 first_reliable_frame 即可 |
| `observed_player_count > MAX_RENDER_SLOTS`（如 5+ 球员） | 显式抛出 `RenderSlotOverflowError`，被 visualization 阶段捕获后仅标记 render trajectory artifact 为 `failed`，不传播到 tracking/ball/report |
| 普通 track ID 碎片重连错误触发 epoch 递增 | D4 明确定义：epoch 由上游决定，PostProcessor 只消费；只有 `player_reset_after_prolonged_loss` 改变 epoch |
| segment_id 变化导致 OverlayVideoWriter deque 被清空，拖尾视觉跳变 | 预期行为。segment 断开意味着无法连续画线，清空 deque 是正确的渲染表现 |
| JSON 体积因 `players`/`segments` 元数据和新增字段增加 | 元数据只存摘要不存坐标；新增字段均为扁平追加，gzip 压缩后增量可忽略 |
| `projection_gap` 无 CourtTrackEvent 来源 | 首批保留枚举值但不触发；只有显式 projection failure/recovery event 存在时才生成，否则统一生成 `visible_gap` |

## Open Questions

- `identity_reset_after_prolonged_loss` 的 lost 时长阈值当前依赖 `PlayerLockManager.lost_max_frames_locked`，未来可能需要从 PostProcessor 独立配置——暂不在本 Change 处理
- 未来上游实现 canonical identity reassignment 事件后，PostProcessor 是否需要额外区分 `identity_reassigned` 和 `identity_reset` 的 break_before 原因——当前两者都生成新 segment，仅 break_before 标签不同，后续 Change 决定
