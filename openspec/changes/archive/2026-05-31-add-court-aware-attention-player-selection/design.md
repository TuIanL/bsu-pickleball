## Context

现有分析管线大致为 `YOLO person detection -> MultiObjectTracker -> FootpointEstimator -> homography projection -> PrimaryPlayerSelector -> PlayerIdentityManager -> metrics/overlay`。当前主球员选择器已经避免了只用严格场内边界做过滤，但它仍主要按单个 track 的置信度、框大小、持久性和宽松场景范围打分。

用户素材的关键难点是：目标场旁边可能有其他球场正在比赛，隔壁场球员同样会持续运动、检测置信度高、轨迹稳定。静止度、运动强度、普通 person confidence 都不足以区分“目标场四名球员”和“隔壁场球员”。因此本设计把选择问题重新定义为：在一段时间窗口内，从所有候选 tracklet 中找出最符合目标球场 homography 与双打四人关系的一组。

## Goals / Non-Goals

**Goals:**

- 在没有训练模型权重时，提供目标球场感知的规则增强 selector，显著降低隔壁场球员进入目标场 overlay 和最终 player trajectory 的概率。
- 定义 self-attention selector 的输入特征、输出语义、模型加载、fallback 和训练样本导出，使后续真实数据训练可以平滑接入。
- 保持现有 YOLO、tracker、projection、identity 和 metrics 的主要 schema 兼容；新增分数与诊断作为扩展字段或旁路 artifact。
- 支持 hard negative 诊断，明确区分 `target_player`、`neighbor_court_player`、`spectator`、`uncertain` 等候选类别。

**Non-Goals:**

- 不在首个实现中承诺训练出可用的 attention 权重，也不要求用户运行训练后才能使用系统。
- 不替换 YOLO person detector、MultiObjectTracker、RTMPose 或 homography 标定流程。
- 不做端到端视频 Transformer 检测器；attention 模型只处理已经形成的候选 tracklet 特征。
- 不把隔壁场本身建模成完整多球场识别系统；首期只围绕目标场几何和候选关系排除非目标场人员。

## Decisions

### 1. 以 tracklet 窗口作为选择单位，而不是单帧 track

主球员锁定应该先聚合一段时间窗口内的候选 observation，形成 tracklet 特征，再选目标场四人。窗口特征包括目标场投影内占比、到目标场 polygon 的距离统计、速度/加速度、bbox 尺寸随透视的合理性、出现帧数、检测置信度和轨迹连续性。

Rationale：隔壁场球员在单帧里可能与目标场球员非常相似，但在目标场坐标系内的长期位置分布和四人组关系会更容易区分。

Alternative considered：继续逐帧选前四个 track。实现简单，但会在候选人数多、隔壁场人员移动活跃时频繁抖动。

### 2. 规则增强 selector 先落地，attention selector 作为可选增强

首个可用实现应提供 deterministic selector：计算 `target_court_score`、`tracklet_quality_score`、`group_consistency_score`，组合成候选选择结果。attention selector 的代码接口、模型定义、推理 adapter 和样本导出同时建立，但没有权重时自动跳过。

Rationale：当前缺少标注训练集；如果直接依赖训练模型，会让功能可用性取决于未完成的数据闭环。规则增强可以先提供收益，也能为后续训练积累 hard negatives。

Alternative considered：直接训练 self-attention 模型并替换规则。风险是数据不足、泛化不稳，且实现周期更长。

### 3. Self-attention 模型输入必须显式包含目标球场几何特征

模型输入不是原始视频帧，而是每个候选 tracklet 的时间序列特征。每个 time step 至少包含 normalized bbox、detection confidence、image footpoint、目标场 court 坐标、目标场 polygon 距离、in-target-court 标记、速度、side/zone、track age 和可选 pose/appearance embedding。模型输出每个候选的类别概率和可选 `player_slot` 分布。

Rationale：如果模型只看“人在运动”，它无法知道用户标定的是哪一块场地。目标场几何必须进入特征，attention 才能学习“这些人是否属于同一个目标场四人组”。

Alternative considered：输入裁剪图像或整帧视频做端到端判断。表达力更强，但数据、算力和工程复杂度都不适合当前阶段。

### 4. Identity manager 消费 eligibility，不自行创造第五个目标场身份

目标场 selector 输出 eligible track IDs 和诊断分数。`PlayerIdentityManager` 应仅在 eligible 候选中创建或重连最终 `Player_1..4`，并把低分或非目标场候选记录为 filtered/unmatched diagnostics。

Rationale：如果 identity 层继续把所有投影有效人员都当候选，前面 selector 的目标场判断会被绕过。最终 metric artifact 应只表达目标场四名球员。

Alternative considered：让 identity 层自己完整判断目标场归属。会把职责混在一起，难以替换规则/模型 selector。

### 5. Fallback 和诊断是产品能力的一部分

当 attention 模型文件缺失、依赖不可用、推理失败或模型置信度低于阈值时，系统必须回退到规则增强 selector，并在 artifact 中记录 `selection_mode`、`fallback_reason` 和候选分数组成。

Rationale：模型训练和本地环境配置都可能不稳定；可解释回退能保证演示和真实分析不中断。

Alternative considered：模型失败时直接失败任务。对用户体验不友好，也不符合当前本地模型可选加载的模式。

## Risks / Trade-offs

- [Risk] 目标场 homography 标定误差会影响 court-aware 分数。→ Mitigation：保留宽容边界、输出距离统计诊断，并允许高质量 track 在轻微越界时继续参与四人组选择。
- [Risk] 隔壁场与目标场平行且距离很近时，仅靠目标场投影可能仍混淆。→ Mitigation：加入四人组空间分布、长期 court occupancy、bbox 透视合理性和 hard negative 标注数据；后续由 attention 模型学习更复杂模式。
- [Risk] 规则权重调参可能过拟合少数素材。→ Mitigation：把分数拆成可观察 components，使用测试夹具覆盖目标场、隔壁场、边界移动、遮挡断线等场景。
- [Risk] Attention 模型引入 PyTorch 依赖和权重管理复杂度。→ Mitigation：推理 adapter 可选加载；没有依赖或权重时不影响规则增强路径。
- [Risk] 窗口级选择可能增加延迟，实时 overlay 不能立即稳定。→ Mitigation：离线分析优先使用窗口级结果；实时预览可使用短窗口/上一窗口锁定结果。

## Migration Plan

1. 添加候选 tracklet 聚合和 court-aware 规则 selector，默认替换现有 `PrimaryPlayerSelector` 的排序核心，但保持输出结构兼容。
2. 将 selector 输出的 eligible track IDs 传给 overlay 和 `PlayerIdentityManager`，并保留旧字段用于诊断。
3. 新增 selection diagnostics artifact，先由规则路径填充。
4. 添加 attention selector adapter、模型配置、权重缺失 fallback 和训练样本导出脚本。
5. 在真实素材上人工复核 hard negatives，积累训练数据后再启用 attention 权重。

Rollback：配置关闭 court-aware selector 时恢复现有 primary selector 行为；attention 失败始终回退规则路径。

## Open Questions

- 初始窗口长度应选择多少帧或多少秒，才能兼顾稳定性和响应速度？
- 训练标签是否只需要 `target_player / non_target`，还是应细分 `neighbor_court_player / spectator / uncertain`？
- 是否需要在前端分析详情页新增候选选择调试视图，还是先只写入 artifact 供离线 QA？
