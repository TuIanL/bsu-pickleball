## Context

当前系统在球检测、姿态估计、小地图轨迹三个环节均采用「逐帧独立判定 + 硬阈值」策略：每帧的检测结果仅依赖该帧数据，不同帧之间无状态记忆。这在理想视频条件下可正常工作，但面对真实比赛场景中的噪声（球场污渍、远端小目标、模型置信度边界波动）时会表现出三类可靠性问题。本次改动在现有架构内增加轻量级的时序记忆机制，不引入新的外部依赖或数据模型变更。

## Goals / Non-Goals

**Goals:**
- 消除球场细小静止物导致的球位置误报
- 消除远端球员骨架关键点的闪烁现象
- 提高远端球员的人体检测召回率
- 确保小地图中球员轨迹的连续性

**Non-Goals:**
- 不改变球检测模型或姿态估计模型本身（仅调参 + 后处理逻辑）
- 不引入新的 artifact 类型或 API 端点
- 不改变前端渲染逻辑
- 不增加 GPU 计算量
- 不改变 BallFrameSample / PoseSubject 的序列化 schema

## Decisions

### Decision 1: 静止黑名单用离散网格坐标 + 跨帧投票

**选择**：在 BallTracker 内部维护 `_stationary_blacklist: dict[tuple[int,int], int]`，key 为 5px 精度离散化的图像坐标，value 为该位置连续被检测到的帧计数。对所有候选（不只是被选中的那个）进行投票累加。达到 60 帧阈值后加入永久黑名单。

**替代方案**：
- A. 仅扩大 `stationary_window_frames` 和 `stationary_radius_pixels` → 不改架构，但闪烁检测导致窗口频繁重置，效果有限
- B. 为每个候选建独立 mini-tracker → 正确但复杂度高，引入完整的多目标跟踪
- C. 在检测器层面加 ROI mask → 需要用户手动标定过滤区域，不通用

**理由**：方案 B 是最完整的但工程量大，方案 A 不足以解决问题。离散网格 + 投票是折中——不引入新的跟踪复杂度，但解决了「窗口重置」的根本缺陷。60 帧（2 秒 @30fps）是经过权衡的值——足够短以快速生效，足够长以避免短暂静止的真球被误杀。

### Decision 2: Keypoint hysteresis 用双阈值（enter/exit）而非滚动均值

**选择**：在 `RTMPose26Adapter._normalize_keypoints()` 中，每个关键点维护一个跨帧 boolean 状态 `_visible_states: dict[int, dict[str, bool]]`，按 `(track_id, keypoint_name)` 索引。进入阈值默认 0.30，退出阈值默认 0.20。visible 状态在记忆期内保持不变。

**替代方案**：
- A. 关键点置信度做滑动窗口均值平滑 → 引入延迟，跃变场景延迟更大，且对消失后再出现的场景不合理
- B. 降低单一阈值到 0.2 → 假阳性增加，低置信度关键点可能被渲染到错误位置
- C. 根据 bbox 面积自适应阈值 → 合理但增加复杂度，且阈值映射关系需要标定

**理由**：Hysteresis 是处理临界波动的经典方案，零延迟零超调。enter/exit 双阈值给予足够的「防抖区间」而不引入信号延迟。enter_threshold 保持 0.30 不变，exit_threshold 降到 0.20，中间 0.10 宽度提供了约 33% 的缓冲带。`_visible_states` 以 track_id 为索引，随 IoU tracker 的生命周期自动清理（track_id 被回收时对应条目也会被下游丢弃）。

### Decision 3: PersonDetector 阈值降到 0.15，不额外加假阳性过滤

**选择**：`PersonDetector(conf_threshold=0.15)`。

**理由**：降低检测阈值是提高远端球员召回率最直接的手段。顾虑是假阳性增加，但后续链路有足够过滤——检测 ROI 过滤、PrimaryPlayerSelector 的 min_confidence(0.65) 和 min_box_area(0.0005)、PlayerIdentityManager 的 match_threshold(0.55)、court bounds 检查。假阳性会在这些层级被层层过滤，不太可能进入最终输出。0.15 是经过工程常识的取值——显著低于默认的 0.25 但不至于低到让无意义的噪声大量涌入。

### Decision 4: 小地图轨迹连续性暂不作为独立修复，先依赖问题二修复

**选择**：不直接修改 MinimapVisualizer 的数据源。先通过解决问题二（提高检测召回率 + hysteresis）来改善轨迹连续性。若问题二修复后小地图轨迹仍有明显断续，再在后续 change 中使 MinimapVisualizer 使用 `PlayerIdentityManager.get_trajectory(player_id)` 的插值轨迹而非逐帧 observation。

**理由**：小地图轨迹断续的根因在逐帧检测丢失，修复根因后大概率自动改善。若直接改数据源，治标不治本且引入不必要的代码改动。

## Risks / Trade-offs

| Risk | Mitigation |
|------|-----------|
| PersonDetector 阈值降到 0.15 导致假阳性检测框增多，增加下游计算量 | 每帧多出来的候选框数量有限（远端噪声通常不满足 YOLO 的 objectness 条件），且 ROI/球场边界过滤在前端执行，实际增量可忽略 |
| 静止黑名单的离散网格（5px）可能因相机抖动产生偏移，导致同一静止物被识别为多个网格 | 5px 已经给了一定的抖动容差，且相机抖动在固定机位场景中通常不会超过 2-3px。若出现严重抖动，这是视频质量的问题，应在源头解决 |
| Hysteresis 可能导致已消失的关键点短暂保持在错误位置 | 退出阈值为 0.20，足够低以至于不会被噪声触发保持；若 confidence 真降到 0.20 以下，会立即退出。极端情况下（关键点消失但仍显示 1-2 帧）比「闪烁」更可接受 |
| `_visible_states` 的 track_id 索引可能随着 track_id 回收而产生残留 | 状态 dict 仅存在于 RTMPose26Adapter 实例的生命周期内，单个 job 结束后自然释放。track_id 值在 MultiObjectTracker 中递增，碰撞风险极低 |

## Open Questions

- 静止黑名单的 60 帧阈值是否需要通过环境变量可配置？（建议先硬编码，观察效果后再决定）
- enter_threshold=0.30 / exit_threshold=0.20 的取值是否需要在真实匹克球比赛视频上做参数扫描？（当前取值基于工程经验，若效果不佳可在后续版本调优）
