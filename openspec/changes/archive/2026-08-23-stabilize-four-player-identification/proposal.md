## Why

当前双打分析虽然已有四槽位、质量门和身份诊断，但真实视频仍会出现第四名球员长期漏检、P2 的尺度投影误绑到 P1、canonical identity 跨人漂移，以及 P2 轨迹污染 P3/P4 热力图等问题。此次变更的目标是直接提升四名真实球员的检测召回、跟踪连续性和身份正确率；质量门只负责证明改进是否达标，不能代替正确识别。

## What Changes

- 建立双打四人识别的端到端质量契约：每个有效时间窗应维持近端 2 人、远端 2 人的受约束 roster，并分别统计检测覆盖、canonical 覆盖、身份切换、重复绑定、跨侧污染和最长缺口。
- 将当前仅依赖 bbox IoU 的贪心 tracker 升级为一对一、运动感知的关联：综合预测 bbox、IoU、脚点位移、bbox 尺度变化、检测置信度和球场投影可信度；遮挡或交叉时保留 track 状态，不因单帧最近框直接换 ID。
- 实装球员衣服外观软特征：从 detector-backed 人体框分别提取上衣/下装的 HSV/Lab 颜色直方图、颜色矩和可选粗纹理，形成带质量分的 appearance descriptor；按 tracklet/PlayerSlot 维护稳健模板，辅助交叉、遮挡和 track replacement 后的身份恢复。
- 外观信号只在几何、运动、side 与一对一 hard gate 通过后参与候选排序和歧义消解；颜色相似、光照异常、遮挡、bbox 太小或跨摄颜色未校正时必须降权/停用，MUST NOT 单独决定 P 编号或触发身份切换。
- 增加目标球场四人召回路径：基础检测不足四人时，对缺失 side/quadrant 使用 tracker prediction 与受限 ROI 二次检测；恢复候选必须有真实像素检测并通过尺度、位置、球场归属和一对一冲突检查，禁止仅靠投影制造人体框。
- 将 bootstrap 从“单帧填槽”收敛为时间窗内的轨迹级分配：先形成稳定 tracklet，再按 near/far 与 left/right、持续时间、可见率和投影质量进行全局一对一槽位匹配；证据不足时允许槽位暂缺，禁止把 P1 的 track 同时填入 P2。
- 强化 local slot、global roster 与 canonical `Player_1..Player_4` 的绑定不变量：同一 tick 内 track↔slot、local slot↔global、global↔canonical 均保持双射；身份切换必须经过连续多帧强证据和歧义拒绝，不能因单路漏检或尺度投影直接覆盖 incumbent。
- 对 canonical 轨迹、散点图、热力图和报告实行身份污染隔离：只有已确认或明确恢复的样本进入正式球员产物；ambiguous、duplicate、cross-side、unresolved 样本进入诊断，不得写入其他 P 槽位的轨迹。
- 生成 `four-player-identification-quality.v1` 诊断/验收产物，记录逐球员覆盖率、最长连续缺失、source track history、reconnect、identity switch、duplicate binding、side/quadrant violation 与污染样本计数，并在技术详情中展示真实状态。
- 建立固定片段和真实双摄任务的新 Job 回归：重点断言视频约第 2 秒 P2 可见性、第 4 秒 P2 不误投到 P1，以及 P2 热力图不进入 P3/P4 的对侧区域。回归必须运行新任务并比较结构化 artifact，不以刷新旧结果或人工观看代替。
- 保持现有 Job、AnalysisResult、roster、trajectory、visualization API 向后兼容；新增字段和诊断产物均为 additive change。

## Capabilities

### New Capabilities

- `four-player-identification-quality`: 定义真实双打四人检测、跟踪、canonical identity、污染隔离的端到端指标、诊断产物与回归验收标准。
- `player-appearance-identity-cue`: 定义上衣/下装颜色与粗纹理描述子、模板生命周期、跨摄颜色归一化、软融合约束、隐私边界和消融验收。

### Modified Capabilities

- `player-tracking-engine`: 多目标关联从单一贪心 IoU 提升为运动、尺度、脚点、置信度和合格 appearance descriptor 联合的一对一关联，并增加受限 ROI 四人召回路径。
- `bootstrap-slot-completeness`: 四槽位 bootstrap 改为时间窗 tracklet 级全局分配，禁止为了凑满四人而重复或误锁已有球员。
- `player-lock-state-machine`: 加强 track↔slot 双射、appearance template 生命周期、交叉遮挡保持、恢复歧义拒绝与连续证据切换规则。
- `multiview-player-association`: 强化 local slot↔global 的双射、跨摄 appearance 软先验和尺度投影来源约束，阻止 P2 证据被关联到 P1 incumbent。
- `multiview-global-player-roster`: roster 确认增加四人覆盖与绑定完整性要求，global→canonical 映射冻结后只能通过受控修复流程变更。
- `player-trajectory-identity`: 正式 canonical 轨迹排除 ambiguous、duplicate、cross-side 与 unresolved 样本，阻断身份污染向下游传播。
- `player-zone-heatmap`: 热力图只消费通过身份完整性门控的 canonical 样本，并暴露被隔离样本数量和数据充分性。
- `multiview-visual-acceptance`: 双摄视觉验收增加逐人覆盖、最长缺口、身份切换、重复绑定和跨侧污染的硬不变量与 baseline 对比。

## Impact

- **后端跟踪与身份链**：`backend/app/vision/player_tracking_engine/multi_object_tracker.py`、`person_detector.py`、`view_tracking_session.py`、`player_lock_manager.py`、`player_identity.py`，新增 appearance descriptor/template 模块。
- **双摄关联与 roster**：`backend/app/vision/multiview/association_global.py`、global state/roster、joint run 与 result composer。
- **正式产物**：player trajectory、fused overlay、structured visualization、zone heatmap 生成链增加身份样本状态与隔离统计；`AnalysisArtifacts` additive 增加质量产物 URL/status/detail。
- **前端**：技术详情/双摄 observability 展示四人识别质量摘要和逐球员问题，不把缺失或污染结果伪装成正常热力图。
- **测试与验收**：新增衣服颜色特征/模板质量、tracker 交叉/遮挡序列、四槽位 bootstrap、跨视角误绑、轨迹污染隔离单测，以及真实视频新 Job 对照和 appearance ablation 摘要。
- **依赖与兼容性**：首版使用现有 OpenCV/NumPy 实现 HSV/Lab 描述子，不新增模型服务；保留未来切换 ByteTrack/BoT-SORT 或 learned ReID descriptor 的接口边界。现有 Job/API 不受影响。
