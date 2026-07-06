## Context

当前自动标定流程已经具备完整主链路：从代表帧提取、court-line segmentation、`mask_to_court_keypoints()` 后处理，到 `AutomaticCalibrationService` 返回 `available` / `rejected` / `unavailable` 结果，并生成预览图。现有实现的主要诊断信号包括：

- segmentation model confidence
- `mask_area_ratio`
- Hough/contour 派生的 `line_count`
- 基础几何置信度与 `CalibrationQuality`

这套信息足以判断“有没有结果”，但不足以解释“结果为什么可信”或“为什么被拒绝”。目前后处理的几何置信度主要依赖四边形面积、对边平衡、线条数量等内部指标，缺少把标准匹克球场结构重新投影回图像后，对预测掩码进行 line-level 一致性验证的证据层。

项目中已经具备可复用的基础能力：

- 标准球场几何与球场线定义：`court_geometry.py`
- `court_to_image` / `image_to_court` 单应映射
- 自动标定预览图写入能力

因此这次设计聚焦于在不替换现有 segmentation 或 keypoint 拟合主路径的前提下，增加一层 reference line support 诊断，并把该诊断组织成前后端都能消费的结构化结果。

## Goals / Non-Goals

**Goals:**

- 为自动标定结果增加基于标准球场线投影的一致性评分，而不是只依赖模型 confidence 和几何形状分数。
- 将最终自动标定 confidence 组织成可解释的组合结果，明确暴露 segmentation、geometry、reference support 三类来源。
- 扩展自动标定预览图和响应字段，使用户能看到“检测到什么”“支持证据来自哪里”“为什么被接受或拒绝”。
- 保持现有自动标定主路径稳定：已有的 mask 推理、四角点拟合、semi-automatic accept 流程不需要重写。

**Non-Goals:**

- 不替换当前 segmentation 模型，也不修改训练数据约定或训练脚本。
- 不把 reference line support 变成新的角点拟合算法主路径；它是诊断与校验层，不是单独的标定求解器。
- 不引入新的前端交互流程，例如额外的审核步骤或强制人工确认步骤。
- 不扩展到球员 tracking、court-view gate 或比赛事件分析。

## Decisions

### 1. 在 keypoint 后处理之后计算 reference line support，而不是直接在原始 mask 上独立求解球场

选择：
先沿用当前 `mask_to_court_keypoints()` 产出的四角点与几何置信度，再根据这些角点构建 court-to-image 投影，把标准球场线重新投影回图像，并用预测 mask 或其距离图评估线支持度。

原因：

- 现有主链路已经能稳定产出四角点和 preview，改动成本最低。
- 诊断层绑定“当前候选结果”，更适合回答“这个候选值不值得信”。
- 可以复用 Good-Pickleball 的 reference line support 思路，同时保持我们现有的 segmentation-first 架构。

备选方案：

- 方案 A：像 Good-Pickleball 一样，直接从图像线段独立求解球场模型。
  这个方案更像兜底标定器，不适合本 change 的“增强诊断而非替换主路径”目标。
- 方案 B：只在 preview 上画 projected lines，不计算分数。
  这只能改善可视化，不能改善自动 accept / reject 的可解释性。

### 2. 新增结构化 `reference` diagnostics 和 `confidence_breakdown`，而不是把所有字段塞进现有 `mask.detail`

选择：
保留现有 `mask.detail` 作为简短总结；新增可选结构化字段，例如：

- `reference`: reference line support 诊断
- `confidence_breakdown`: segmentation、geometry、reference、combined 的组成项

原因：

- 前端需要稳定字段来做展示和降级兼容，不能依赖解析文案。
- `mask` 目前语义偏向 segmentation 结果，直接混入全部组合评分会让职责变模糊。
- 单独的 breakdown 便于后续调参和 debug artifact 扩展。

备选方案：

- 方案 A：把 reference score 和 combined confidence 全部塞进 `AutomaticCalibrationMaskDiagnostics`。
  这样实现简单，但语义混杂，不利于前端分区展示。

### 3. 将最终 accept / reject 判定建立在组合置信度和 reference 下限上，而不是只取 `min(segmentation, geometry)`

选择：
把最终 confidence 设计为组合结果，同时保留显式硬门槛：

- `geometry` 仍然必须通过基础有效性验证
- `reference_score` 低于下限时，结果可以直接 `rejected`
- `combined_confidence` 用于 available / rejected 的最终用户可见 score

原因：

- `min(segmentation, geometry)` 过于保守，但解释力弱，无法体现“几何合理但线支持不足”的情况。
- reference 下限可以更准确地区分“角点凑成了四边形”和“球场结构真的被 mask 支持”。

备选方案：

- 方案 A：完全放弃几何分数，只看 segmentation + reference。
  这会削弱当前对异常四边形的防护。
- 方案 B：仍然使用 `min()` 但把 reference score 只作附加显示。
  这不能改变 reject 依据，达不到“更强自动标定诊断”的目标。

### 4. preview 强化为“检测证据图”，而不是仅保留当前的叠加图

选择：
在当前 preview 基础上继续保留 mask 着色、关键点和 court overlay，同时增加：

- projected standard court lines 的高亮
- reference support summary 文本
- 当结果被拒绝时显示主要 rejection reason

原因：

- 用户和开发者都需要视觉上核对“线支撑是不是对齐了”。
- 这比单纯暴露数字更适合人工复核。

备选方案：

- 方案 A：只返回结构化数值，不改 preview。
  会让前端或开发者难以快速判断分数是否合理。

## Risks / Trade-offs

- [Risk] reference score 对噪声 mask 或强反光场地较敏感
  → Mitigation：采用距离变换和容忍像素阈值，而不是要求 projected line 完全落在 mask 上。

- [Risk] 新增字段后，旧前端或旧缓存响应可能没有这些字段
  → Mitigation：所有新增诊断字段保持 optional，沿用当前“Older automatic calibration response lacks diagnostics”的兼容要求。

- [Risk] 组合置信度权重不合理会让 accept / reject 行为抖动
  → Mitigation：保留显式分项 diagnostics，并让 reference 下限和 combined 权重配置独立可调。

- [Risk] preview 文本信息过多会降低可读性
  → Mitigation：将详细数值以 1 到 2 行 summary 显示，完整信息仍通过 API 字段提供。

## Migration Plan

1. 扩展自动标定 response schema，新增 optional 的 `reference` 与 `confidence_breakdown` 字段。
2. 在 `courtvision_calibration_engine` 中增加 reference line support 计算逻辑，输入为 mask 与 keypoints，输出为结构化诊断。
3. 调整 `AutomaticCalibrationService.suggest()` 的 accept / reject 判定与 preview 文本来源。
4. 更新前端自动标定建议展示，优先读取新增 diagnostics；缺失时回落到现有字段。
5. 通过现有自动标定 preview 和 response contract 验证 available / rejected / unavailable 三类结果。

回滚策略：
若新评分逻辑导致误拒绝升高，可保留新增 diagnostics 字段和 preview 增强，但暂时回退为“旧 accept/reject 规则 + 新 diagnostics 仅展示”。

## Open Questions

- reference score 的默认权重和 reject 下限是否直接写入配置，还是先以代码常量稳定一轮实现。
- preview 文本是否需要区分“低 reference score”与“低 combined confidence”两个拒绝原因标签。
