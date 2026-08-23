## 1. Baseline、标注与质量契约

- [x] 1.1 为当前真实 sync recording 创建/登记 baseline Job，导出 P1-P4 coverage、最长缺口、source track history、duplicate/cross-side 与热力图轨迹摘要
- [x] 1.2 固化约第 2 秒 P2 可见、第 4 秒 P2 不得占用 P1 bbox 的轻量人工标注 fixture；只提交时间、bbox/slot 与期望，不提交视频二进制
- [x] 1.3 定义 `four-player-identification-quality.v1` schema、逐球员摘要、阈值 snapshot、pipeline funnel counters 与 verdict 规则
- [x] 1.4 实现 baseline/new Job 质量对比纯函数与 CLI runner，区分硬不变量、绝对阈值和相对改善
- [x] 1.5 为质量 schema、阈值不可静默降低、旧 Job unavailable 与 baseline comparison 补充单元测试
- [x] 1.6 为定点 fixture 标注 P1-P4 上衣/下装主色区、遮挡/截断状态与可区分度，建立 appearance enabled/disabled 消融基线

## 2. 运动感知 MultiObjectTracker

- [x] 2.1 扩展内部 track state，维护 bbox/footpoint velocity、area/aspect trend、last timestamp、lost age 与 uncertainty，同时保持既有 Track 对外接口
- [x] 2.2 实现 predicted bbox/footpoint 与 track×detection 特征提取，统一归一化 IoU、位移、尺度、置信度和 projection reliability
- [x] 2.3 实现 hard gate + maximum-cardinality/min-cost 一对一匹配，替换当前按 IoU 降序贪心分配
- [x] 2.4 实现 incumbent continuity、lost-window prediction 与 uncertainty-aware reacquire；超时后再终止 track
- [x] 2.5 保留 legacy IoU tracker feature flag 与算法/config signature，支持 shadow 对照和安全回滚
- [x] 2.6 补充交叉跑位、短遮挡、尺度突变、矩形候选、重复 detection 和确定性重跑测试
- [x] 2.7 定义 `PlayerAppearanceDescriptor` protocol、extractor version、upper/lower feature schema 与 quality/provenance 字段
- [x] 2.8 实现 pose 优先、bbox 相对分区兜底的上衣/下装 crop，提取 HSV/Lab histogram、颜色 moments 与可选粗纹理
- [x] 2.9 实现 clipping、有效像素、背景/肤色排除、blur、brightness、saturation、occlusion 质量判定；低质量 descriptor fail closed
- [x] 2.10 实现 tracklet descriptor gallery、质量加权 robust template、限幅更新、冻结与 reset/rollback 诊断
- [x] 2.11 将 appearance distance 作为 hard gate 后的可选 min-cost 项，按 descriptor quality 与本场 discriminative margin 动态降权
- [x] 2.12 为颜色变换、上下装不同、同色球员、低光/过曝、bbox 截断、模板污染防护和 appearance disabled 等价路径补充测试

## 3. 四人 detector-backed ROI 召回

- [x] 3.1 在 ViewTrackingSession 中建立“attempted view + 缺失已知/预期 slot”的 recovery opportunity，禁止从 overlay/projected entity 反推 detection
- [x] 3.2 基于 motion prediction、donor guidance 与 target geometry 生成受面积、数量和 cooldown 限制的 per-slot ROI
- [x] 3.3 运行 ROI person detection 并映射回源帧坐标，保留 `base`/`roi_recovery` provenance
- [x] 3.4 对 ROI candidate 应用 confidence、bbox scale/aspect、footpoint、court membership、base detection 去重和 slot ownership 门控
- [x] 3.5 增加 ROI attempts/hits/reject reasons/latency counters，并验证同一 frame detector/tracker update-once 不变量
- [x] 3.6 补充 P2 base 漏检后 ROI 命中、无像素证据不创建 track、观众误检、预算/cooldown 与 provenance 测试
- [x] 3.7 仅为通过 ROI 门控的 detector-backed bbox 提取 appearance，验证 projected/predicted entity 不进入 extractor

## 4. Tracklet bootstrap 与 PlayerLock 双射

- [x] 4.1 实现 bootstrap tracklet summary，累计可见 tick、median confidence、side/quadrant stability、image rank、scale continuity 与 duplicate overlap
- [x] 4.2 实现带 near/far quota 的 tracklet×slot 全局一对一分配，复用纵向可判与图像横向兜底但取消单帧永久裁决
- [x] 4.3 允许迟到的稳定 P2 tracklet 在 bootstrap window 内填充空槽；证据不足时保持 searching
- [x] 4.4 在 PlayerLockManager 增加 active track↔slot 双射断言和 owner index，拒绝 track-owned、duplicate 与 cross-side recovery
- [x] 4.5 将 reconnect 改为连续强证据 + ambiguity margin + scale/motion continuity，并在成功时增加 identity epoch
- [x] 4.6 为三人初始/P2 迟到、同一 track 重复填槽、四人交叉、第四候选是裁判及 reconnect 竞争补充状态机测试
- [x] 4.7 将合格 tracklet appearance template 接入 slot 可行候选软排序，并确保 side/geometry/ownership hard gate 优先
- [x] 4.8 限制 PlayerSlot template 只由 confirmed observed 样本更新，reconnect probation/ambiguous/projected/interpolated 状态冻结

## 5. Global association、roster 与尺度投影归属

- [x] 5.1 在 GlobalPlayerAssociator 同时校验 local-slot→global 与 global→per-view-local-slot 双射，冲突 challenger 进入 pending/unresolved
- [x] 5.2 将 side consistency、slot owner、尺度连续和 ambiguity margin 纳入 challenger 可行性，保留既有 geometry/uncertainty/PendingReassociation 语义
- [x] 5.3 扩展 cross-view projected provenance，记录 donor global、target slot、geometry residual、bbox memory owner/age
- [x] 5.4 修改 fused overlay builder：bbox memory owner 与 projected player 不一致时拒绝 bbox，且 projected evidence 不创建 binding/trajectory sample
- [x] 5.5 在 roster 确认前验证四个 occupant 的独立 source evidence、双射和 side stability；冲突时保持 BOOTSTRAPPING/CONFLICTED
- [x] 5.6 冻结 confirmed global→canonical mapping，并实现只恢复原物理球员、不重排其他 P 编号的 controlled repair audit
- [x] 5.7 补充 P2 投到 P1 bbox、两个 global 抢 reference P1、单路 P2 漏检、epoch reset 与 deterministic rerun 测试
- [x] 5.8 实现 per-camera color profile 的估计、版本、样本数、残差与 confidence；不可用时跨摄 appearance 权重归零
- [x] 5.9 在 GlobalPlayerAssociator hard gate 后接入已校正 appearance soft prior，并记录支持/冲突/未使用原因
- [x] 5.10 补充跨摄白平衡差异、profile 不足、同色服装、颜色支持错误 global 但几何拒绝及单帧不得切换测试

## 6. Canonical trajectory 污染隔离与可视化

- [x] 6.1 为内部 trajectory sample 增加 identity status 与 binding provenance，保持公开兼容字段 additive
- [x] 6.2 实现 accepted/quarantine 分流：ambiguous、duplicate、cross-side、unresolved 不进入正式 trajectory 与 metrics
- [x] 6.3 限制短缺口插值只能连接同 canonical player、同 side、未跨 identity epoch 的 confirmed samples
- [x] 6.4 修改 scatter/position heatmap/zone heatmap 生成器只消费 accepted samples，禁止从 raw track ID 重新推断 P 编号
- [x] 6.5 在 visualization data 中 additive 输出 accepted/quarantined count、coverage、sufficiency 与 quarantine reason summary
- [x] 6.6 补充 P2 橙色轨迹跨入 P3/P4 side 被隔离、跨 epoch 不插值和数据不足展示测试

## 7. 质量产物、API 与技术详情

- [x] 7.1 聚合 detector、tracker、appearance availability/template/decision contribution、lock、association、roster 与 trajectory counters，生成 `four-player-identification-quality.v1`
- [x] 7.2 增加 storage path、AnalysisArtifacts URL/status/detail 与 artifact API route；缺失历史产物返回结构化 unavailable
- [x] 7.3 在 multiview observability/技术详情加载质量摘要，展示 P1-P4 coverage、最长缺口、track fragments、reconnect 与隔离计数
- [x] 7.4 对 roster 不完整、双射冲突、P2 长缺口和身份可信样本不足提供明确诊断，不以“分析完成”掩盖失败
- [x] 7.5 补充 schema/API、旧任务兼容、前端 available/unavailable/failed 和逐人详情测试
- [x] 7.6 在技术详情展示 appearance descriptor 可用率、模板年龄、裁决贡献、camera profile confidence 与 non-discriminative 降级原因，不展示原始衣服 crop

## 8. 集成回归与启用

- [x] 8.1 运行后端 tracking/lock/multiview/visualization 测试与前端 TypeScript/Vitest，修复契约回归
- [x] 8.2 在 shadow mode 对 baseline 素材创建新 Job，保存 legacy/new tracker 与 ROI recovery 的结构化对比
- [x] 8.3 先以 appearance shadow mode 记录相似度而不影响裁决，核对 P1-P4 模板区分度与跨摄 profile 可靠性
- [x] 8.4 验收第 2 秒 P2 detector-backed/accepted evidence 存在，第 4 秒 P2 不使用 P1 bbox owner
- [x] 8.5 验收四人 confirmed roster、同 tick 双射冲突=0、未裁决 identity switch=0、正式 cross-side contamination=0
- [x] 8.6 验收每名 coverage/longest gap 绝对门与 baseline 不退化，确认 P2 热力图不再进入 P3/P4 side
- [x] 8.7 对同一新 Job 配置运行 appearance disabled/enabled 消融，确认交叉/恢复指标改善或保持且所有硬不变量不退化
- [x] 8.8 记录 ROI 与 appearance 额外耗时、触发率和失败原因，确认资源预算可接受后将新算法设为默认
- [x] 8.9 保留并演练 legacy feature flag 回滚，确认回滚不修改旧 Job artifact 或历史版本选择
- [x] 8.10 验证 appearance 权重归零可独立回滚到 geometry/motion 路径，且无需关闭 motion-aware tracker 或 ROI recovery
