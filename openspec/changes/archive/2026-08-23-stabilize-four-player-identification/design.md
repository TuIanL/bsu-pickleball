## Context

当前单视角链路为 `person detector → greedy IoU tracker → projection → selector/lock → identity`，joint 模式再将两路 local identity 送入 global association、roster、fusion 与正式产物。仓库已经具备四槽位、ROI/guidance、reconnect、global roster、fused overlay 和诊断能力，但这些机制仍建立在容易碎裂的 source track 与不完整的 local slot 上：一旦 P2 在 reference view 漏检或被 tracker 换 ID，后续尺度投影、global binding、canonical trajectory 和热力图会放大早期错误。

本设计把“检测到人”“维持 source track”“认定 canonical player”“为缺失视角生成展示投影”分成四个不同 authority。投影框只能补充展示，不能反向证明人物身份；质量产物用于验收和定位，但识别算法必须先产出正确的四人链路。

## Goals / Non-Goals

**Goals:**

- 在真实双打中稳定维护 2 near + 2 far 的四名参赛球员，提高弱小/遮挡球员的 detector-backed recall。
- 减少交叉、短暂遮挡和尺度突变导致的 source track fragmentation 与 ID switch，并让衣服颜色/外观在几何歧义时提供可解释的软证据。
- 维持 track↔local slot↔global↔canonical 的一对一不变量，阻止 P2 绑定到 P1 或污染 P3/P4。
- 让 trajectory、scatter、heatmap、report 只消费身份可信样本，并把被隔离样本显式计数。
- 通过新 Job、固定片段和结构化指标证明相对 baseline 的改善。

**Non-Goals:**

- 不修改球路/球检测算法，不把球员位置当成球路质量的替代证据。
- 不承诺仅靠跨视角投影生成真实人体检测；没有像素证据时只允许预测/投影展示状态。
- 不在本变更中训练新 YOLO 或强制引入 ByteTrack、BoT-SORT、learned ReID 模型服务；但本次 SHALL 实装无需新模型的衣服颜色/粗纹理 descriptor。
- 不改变 `Player_1..Player_4`、AnalysisResult、visualization API 的既有公开字段语义。

## Decisions

### 1. 检测召回采用受约束的两级路径

每个 attempted court-view tick 先运行现有 base detector。若赛制为 doubles 且已确认/预期槽位未形成合格观测，再根据该槽位的 motion prediction、另一视角 guidance 和 target-view geometry 生成小范围 ROI，执行一次受预算约束的二次检测。ROI candidate 必须有真实 detector bbox，经过置信度、bbox 尺度、脚点、目标球场和与现有检测去重门控后才能进入 tracker。

选择该方案是因为它直接改善 P2 漏检，同时复用现有 guidance/ROI 基础。全帧多次降低阈值会显著增加观众误检；纯投影框没有像素证据，不能进入身份链。

### 2. Tracker 使用运动感知的一对一关联

保留 `MultiObjectTracker` 的 detection-in/track-out 接口，内部为每条 track 保存 bbox velocity、footpoint velocity、尺度趋势和 uncertainty。每 tick 构造 track×detection 代价矩阵，先应用 hard gates，再用 maximum-cardinality/min-cost 一对一匹配。排序代价包含 predicted IoU、normalized footpoint distance、log area/aspect change、检测 confidence 与 projection reliability；稳定 incumbent 获得 continuity bonus，单帧交叉不得换 ID。lost track 在有限窗口内保留预测，超过上限才终止。

不立即绑定第三方 tracker，可降低模型、CUDA 和许可证风险；接口与代价分解允许后续用 ByteTrack/BoT-SORT 替换。合格 appearance descriptor 作为软代价项接入，但永不成为绕过几何/运动 hard gate 的条件。

### 3. 衣服外观采用分区颜色描述子与质量门控

新增 `PlayerAppearanceDescriptor` protocol。首版 extractor 对 detector-backed bbox 做内缩，优先借助可用 pose 分割 torso/legs；pose 不可用时按人体框相对高度切分上衣区（约 20%–55%）和下装区（约 55%–90%）。每区提取 HSV 的 H/S 直方图、Lab 的 a/b 直方图、颜色 moments 和可选低维粗纹理，descriptor 同时携带 bbox clipping、有效像素数、blur、brightness、saturation、occlusion 与 `quality`。

质量不足、区域被截断或像素过少时 descriptor 标记 unavailable，不用黑色/背景填充伪造特征。皮肤高概率区域和 bbox 边缘背景应被排除。首版不保存人脸特征，默认不落盘原始衣服 crop，只在诊断中保存数值相似度、质量、模板年龄和裁决贡献。

每条 tracklet 维护短期 descriptor gallery；PlayerSlot 仅用 `confirmed_observed`、高质量、非歧义帧更新长期 template，采用质量加权 robust EMA/medoid，设最大更新步长防止模板被换人帧污染。lost、projected、interpolated、ambiguous 状态冻结模板。新 track 与 slot 比较时分别计算 upper/lower similarity；若四名球员衣服颜色互相接近导致 discriminative margin 不足，appearance 权重自动归零。

选择 handcrafted descriptor 是因为现有仓库已有 OpenCV/NumPy、无需下载 ReID 权重，且颜色贡献可解释。替代方案 learned ReID 对服装相似、跨摄域差异仍需本场校准，并增加模型部署成本；通过 protocol 保留后续替换能力。

### 4. 跨摄 appearance 先归一化再使用

同摄相似度可直接作为 tracker/lock 的软排序项；跨摄比较必须先使用每路 camera color profile 做归一化。profile 从同步窗口中的球场/背景中性区域或已确认同一 global 的高质量成对观测估计 robust Lab affine/statistical transform，并记录样本数、残差与 confidence。profile 不可用、样本不足或残差过大时，跨摄 appearance SHALL 降权为 0，不能用未经校正的颜色否决几何合法匹配。

appearance 融合发生在 hard gates 之后：`total_cost = geometry_motion_scale_cost + w_app × appearance_distance`。`w_app` 由 descriptor quality、camera profile confidence 和四人间 discriminative margin 共同决定。身份切换仍需连续 N tick、incumbent 优势被稳定超过、且 appearance margin 与其他证据方向一致；单帧颜色最像不得换人。

### 5. Bootstrap 以 tracklet 窗口做全局四槽位分配

bootstrap 收集一段时间内的 tracklet summary，而非看到一帧就永久锁定。summary 包含可见 tick、median confidence、side stability、court/image horizontal rank、bbox scale continuity、duplicate overlap 与稳健 appearance template。窗口达到最小证据后，对四个 slot 与候选 tracklet 做有 side quota 的全局一对一匹配。证据不足的槽位保持 searching；同一 tracklet 绝不能填两个 slot。appearance 只在 side/geometry 可行候选间排序。

这样既能补回第 2 秒暂时缺失的 P2，又避免为了“凑够四人”把 P1 重复锁进 P2。既有纵向可判、图像横向兜底继续作为候选特征，而不是单帧最终裁决。

### 6. 身份切换使用状态机与双射校验

每层维护显式 binding epoch 和双射索引。incumbent 可见时优先保持；候选接管必须满足同 side、预测距离、尺度连续、未被其他 slot 占用、连续 N tick 强证据和 ambiguity margin。任何层发现 duplicate binding、cross-side challenger 或两个候选近似等价时，输出 `ambiguous` 并保持旧身份/空槽，不直接覆盖。

local slot 的变化不会自动改 global→canonical mapping。roster confirmed 后 canonical mapping 冻结；只允许经记录旧 mapping、新 mapping、证据窗口和原因的 controlled repair 恢复到同一物理球员，不允许重排其他 P 编号。

### 7. 跨视角尺度投影是展示证据，不是身份 authority

`cross_view_projected`/尺度投影必须携带 donor global、target canonical slot、geometry residual、target bbox memory owner 和 age。只有 donor global 已确认、target slot 映射一致、bbox memory 属于同一 global 且 residual/age 达标时才可绘制。投影不得创建 source track、填 local slot、改变 global binding 或写入 detector-backed trajectory。

这直接阻止“P2 投影到 P1 身上”：如果 target bbox memory 属于 P1，P2 的 projected entity 必须拒绝或退化为无 bbox 的脚点/缺失状态。

### 8. 正式轨迹采用样本级身份状态与污染隔离

每个 canonical sample 增加内部 `identity_status`：`confirmed_observed | confirmed_recovered | interpolated | ambiguous | duplicate | cross_side | unresolved`。仅前三类可进入正式 trajectory、scatter、heatmap 和 metrics；其余写入 quarantine diagnostics。短缺口插值只能在同一 canonical player 的前后 confirmed sample 之间进行，不能跨 identity epoch 或 side。

下游不得自行从 raw track ID 重建 canonical identity。zone heatmap 返回每名球员 accepted/quarantined sample count、coverage 与 sufficiency，避免被污染轨迹仍显示为可信百分比。

### 9. 新增统一质量产物与真实回归

`four-player-identification-quality.v1` 聚合 attempted ticks、base/ROI detection、track fragments、appearance availability/template updates/decision contribution、slot/global/canonical binding、trajectory quarantine，按 P1-P4 输出 coverage、longest gap、source track count、reconnect/switch、duplicate/cross-side/ambiguous 计数。默认验收门为：双打 confirmed roster=4；任何同 tick 双射冲突=0；未裁决 identity switch=0；正式 cross-side contamination=0；每人 canonical coverage≥0.70；最长连续缺失≤2.0s。阈值和配置 snapshot 必须写入产物，不能静默降低。

真实回归必须创建新 Job，并与指定 baseline Job/片段比较。除硬不变量外，新 Job 的 minimum per-player coverage、P2 coverage 和最长缺口不得劣于 baseline；第 2 秒、第 4 秒使用人工标注的小型 acceptance fixture 做定点验证。

## Risks / Trade-offs

- [ROI 二次检测增加推理耗时] → 仅对缺失槽位触发，限制每 view/tick 的 ROI 数与面积，并记录触发率和耗时。
- [运动模型在快速变向时预测偏差] → uncertainty-aware gate、脚点与 bbox 多特征联合，lost 状态不直接输出正式样本。
- [四槽位约束误锁观众] → side/court membership、tracklet duration、bbox scale 和一对一约束共同门控；宁可空槽不误锁。
- [运动员服装相似导致 appearance 无区分度] → 计算本场模板间 discriminative margin，低于阈值时自动将 appearance 权重降为 0，保持几何/运动路径。
- [双摄白平衡与曝光差异导致颜色距离失真] → 仅在 camera color profile 置信度达标后使用跨摄 appearance；否则只允许同摄软特征。
- [错误绑定污染外观模板并形成自证循环] → 只用 confirmed observed 高质量帧限幅更新；歧义、投影、恢复初期冻结模板，并提供模板 reset/rollback 诊断。
- [隔离后热力图点数减少] → 同时展示 coverage/sufficiency；数据不足优于错误地把 P2 轨迹算给 P3/P4。
- [旧任务没有新质量产物] → API 返回结构化 unavailable；不重写旧 artifact，用户可通过新历史版本对照。

## Migration Plan

1. 先落诊断计数、baseline runner 与定点 fixture，不改变现有正式输出。
2. 实现 appearance extractor/template/color profile，在 shadow mode 记录相似度与消融结果但不参与裁决。
3. 在 feature flag 下启用 motion-aware tracker、appearance soft cost 和 ROI recovery，生成 shadow comparison。
4. 启用 tracklet bootstrap、双射校验和 projection provenance gate。
5. 启用 trajectory quarantine，并让 visualization/heatmap 改读 accepted samples。
6. 真实新 Job 达到硬不变量、baseline 改善且 appearance ablation 不退化后设为默认；保留 appearance 权重归零与 legacy tracker 两级回滚。

## Open Questions

- 用于第 2 秒/第 4 秒定点验收的两路视频帧与人工 P2 bbox/slot 标注需要在实施 Phase 0 固化；二进制视频不提交仓库。
- `min_player_coverage=0.70` 与 `max_gap=2.0s` 是否需按镜头遮挡比例调整，必须由 baseline 数据决定并形成显式评审记录。
- 首版 upper/lower HSV/Lab bins、质量阈值和跨摄 profile 方法需由 Phase 0 fixture 做参数校准；配置与消融结果必须入档。
- 若 handcrafted descriptor 在同色服装片段贡献不足，后续可通过同一 protocol 评估 learned ReID embedding，但不得在本次实施中用未验证模型替换。
