# court-view-roi-gating Specification

## Purpose
Define court-view gate, camera-view candidate segments, calibration-aware detection ROI, and diagnostics for real calibrated pickleball video analysis without claiming ball, shot, score, or complete rally semantics.

## Requirements
### Requirement: 球场视角门控 artifact
系统 SHALL 为完成的真实已标定视频分析任务生成或明确标记 court-view gate artifact，用于描述处理帧是否处于可分析的目标球场视角。

#### Scenario: 球场视角门控可用
- **WHEN** 真实视频分析任务具备可读视频、有效标定和可用参考帧
- **THEN** 系统 SHALL 输出 court-view gate artifact，包含 job/video 标识、状态、检测器版本、阈值、处理帧计数、球场视角帧计数、非球场视角帧计数和候选片段列表

#### Scenario: 球场视角门控不可用
- **WHEN** 真实视频分析任务缺少有效标定、参考帧、OpenCV 或其他最低输入
- **THEN** 系统 SHALL 将 court-view gate artifact 标记为 `unavailable` 或 `skipped`，并说明缺失前置条件

#### Scenario: 门控结果不等于正式回合
- **WHEN** court-view gate artifact 包含候选片段
- **THEN** 系统 SHALL 将这些片段标记为球场视角候选或 camera rally candidates，不得声明它们是完整 rally、得分回合、击球序列或战术结论

### Requirement: 连续帧球场视角状态机
系统 SHALL 使用连续帧阈值从 frame-level court-view 分数中生成稳定候选片段，避免单帧误判直接开启或结束片段。

#### Scenario: 连续球场视角开启候选片段
- **WHEN** 连续达到配置阈值的处理帧被判定为球场视角
- **THEN** 系统 SHALL 开启或延续一个 court-view candidate segment，并记录起始 frame、起始 timestamp 和触发原因

#### Scenario: 连续非球场视角结束候选片段
- **WHEN** 已开启候选片段后连续达到配置阈值的处理帧被判定为非球场视角
- **THEN** 系统 SHALL 结束当前 candidate segment，并记录结束 frame、结束 timestamp、持续时间和结束原因

#### Scenario: 短暂抖动不切断片段
- **WHEN** 当前候选片段中出现少量低于门槛的孤立帧但未达到连续非球场阈值
- **THEN** 系统 SHALL 保持候选片段开启，并在诊断中记录低分帧数量

### Requirement: 标定感知 detection ROI
系统 SHALL 从已接受的球场四角图像点或等效标定数据中推导 expanded detection ROI，用于减少目标球场外人物和背景干扰。

#### Scenario: ROI 从四角点推导
- **WHEN** 标定记录包含有序球场外角图像点和源视频 frame dimensions
- **THEN** 系统 SHALL 生成 expanded ROI，包含源帧坐标、扩展比例、裁剪边界、来源标定 id 和是否裁剪到画面边界的诊断

#### Scenario: ROI 缺少输入时降级
- **WHEN** 标定记录缺少可用图像角点或 frame dimensions
- **THEN** 系统 SHALL 将 ROI 状态标记为 `unavailable`，并允许现有全帧检测路径继续运行

#### Scenario: ROI 保留源帧坐标一致性
- **WHEN** person detection 在裁剪 ROI 上运行或 detection 结果被 ROI 过滤
- **THEN** 系统 SHALL 保证下游 tracking、pose overlay、footpoint projection 和 frontend overlay 继续使用源视频 frame coordinate system

### Requirement: 门控与 ROI 诊断
系统 SHALL 为 court-view gate 和 ROI 输出可复盘诊断，使用户和开发者能判断检测被跳过、过滤或降级的原因。

#### Scenario: 诊断包含计数
- **WHEN** court-view/ROI 能力运行完成
- **THEN** artifact SHALL 包含 processed frame count、gated frame count、ROI-filtered detection count、full-frame fallback count 和配置阈值摘要

#### Scenario: 诊断包含低置信度原因
- **WHEN** court-view 分数低于阈值或 ROI 几何异常
- **THEN** artifact SHALL 记录低置信度、几何异常、缺少参考帧或缺少标定等原因，而不是只返回空结果

#### Scenario: 当前能力不产生球事件
- **WHEN** court-view/ROI artifact 被下游报告或 UI 消费
- **THEN** 系统 SHALL 不得从该 artifact 推断 ball trajectory、bounce、hit、out-of-bounds、score 或完整 rally 结果
