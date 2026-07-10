# calibration-quality-diagnostics Specification

## Purpose
TBD - created by syncing change improve-player-court-projection-reliability.

## Requirements
### Requirement: 标定重投影误差计算

系统 SHALL 在球场标定完成后，使用标定控制点（4 个球场角点）和派生球场线点（网线两端、厨房线交点、中线交点）计算重投影误差（pixel 级别），并汇总输出平均误差和最大误差。派生点基于标准球场几何生成，不依赖用户额外标注。

#### Scenario: 标定角点重投影误差计算

- **WHEN** 使用 4 对图像点→球场点计算 homography
- **THEN** 系统 SHALL 对每个角点计算 image_point 与 `court_to_image(court_point, inv_H)` 之间的欧氏距离（像素）
- **AND** 输出 `corner_reprojection_errors_px: [e1, e2, e3, e4]`
- **AND** 输出 `corner_mean_error_px` 和 `corner_max_error_px`

#### Scenario: 派生球场线点投影校验

- **WHEN** homography 计算完成
- **THEN** 系统 SHALL 生成以下派生 court 点并投影回图像：
  - 网线两端点（0, 22）和（20, 22）
  - 近端厨房线两端点（0, 15）和（20, 15）
  - 远端厨房线两端点（0, 29）和（20, 29）
  - 近端中线与厨房线交点（10, 15）
  - 远端中线与厨房线交点（10, 29）
- **AND** 系统 SHALL 验证所有投影点落在图像范围内（0 < px < frame_width, 0 < py < frame_height）
- **AND** 系统 SHALL 验证派生点投影的相对空间关系合理（网线在两条厨房线之间、近端在上/下端）

#### Scenario: 重投影误差超过阈值

- **WHEN** `corner_max_error_px > 10.0` 或派生点投影明显异常
- **THEN** 系统 SHALL 设置 `calibration_quality = "suspect"`
- **AND** 系统 SHALL 在诊断中发出警告 `"Corner reprojection error or derived point anomaly — may indicate poor calibration or swapped points"`

#### Scenario: 重投影误差正常

- **WHEN** `corner_max_error_px <= 5.0` 且派生点投影全部合理
- **THEN** 系统 SHALL 设置 `calibration_quality = "good"`

### Requirement: 球场比例偏差检测

系统 SHALL 计算投影后球场的宽高比，并与标准 20ft × 44ft 的比例进行比较。

#### Scenario: 比例偏差正常

- **WHEN** 投影后球场宽高比 `|actual_ratio - 20/44| / (20/44) <= 0.10`
- **THEN** 系统 SHALL 不报告比例异常

#### Scenario: 比例偏差异常

- **WHEN** 投影后球场宽高比偏差超过 10%
- **THEN** 系统 SHALL 设置 `calibration_quality = "suspect"`
- **AND** 系统 SHALL 在诊断中记录 `aspect_ratio_error` 值

### Requirement: 基线方向校验

系统 SHALL 验证近端底线（y=0）和远端底线（y=44）在 homography 映射下的方向合理性，检测可能的近/远端顺序颠倒。

#### Scenario: 基线方向正确

- **WHEN** 近端底线 court_points 投影到图像后在画面下部（较大 image_y），远端底线投影到画面上部（较小 image_y）
- **THEN** 系统 SHALL 不报告方向异常

#### Scenario: 基线方向颠倒

- **WHEN** 近端底线投影到画面上部，远端底线投影到画面下部（与典型俯拍视角相反）
- **THEN** 系统 SHALL 设置 `calibration_quality = "suspect"`
- **AND** 系统 SHALL 输出警告 `"Near/far baseline may be swapped — near court projects to top of image"`

### Requirement: homography 条件数诊断

系统 SHALL 计算 homography 矩阵的条件数（condition number），作为标定数值稳定性的指标。

#### Scenario: 条件数正常

- **WHEN** homography 矩阵条件数 < 1000
- **THEN** 系统 SHALL 记录 condition_number 但不触发警告

#### Scenario: 条件数过大

- **WHEN** homography 矩阵条件数 >= 10000
- **THEN** 系统 SHALL 设置 `calibration_quality = "suspect"`
- **AND** 系统 SHALL 输出警告 `"Homography is ill-conditioned — calibration points may be near-collinear"`

### Requirement: 标定诊断 artifact 输出

系统 SHALL 将标定诊断结果写入 `calibration_diagnostics.json` artifact，供前端和调试使用。

#### Scenario: 标定诊断 artifact 内容

- **WHEN** 标定完成且诊断运行
- **THEN** 系统 SHALL 写入包含以下字段的 JSON artifact：
  - `calibration_quality`: "good" | "suspect" | "bad"
  - `corner_reprojection_errors_px`: 各角点重投影误差列表
  - `corner_mean_error_px`: 角点平均误差
  - `corner_max_error_px`: 角点最大误差
  - `derived_points_within_frame`: 派生球场线点是否全部在图像范围内（bool）
  - `aspect_ratio_error`: 比例偏差
  - `baseline_direction_valid`: 基线方向是否正常
  - `homography_condition_number`: 矩阵条件数
  - `warnings`: 字符串警告列表

#### Scenario: 标定诊断对 pipeline 无阻断

- **WHEN** `calibration_quality == "bad"`
- **THEN** 系统 SHALL NOT 使整个分析任务失败
- **AND** 系统 SHALL 在 AnalysisPipelineResult 中记录降级状态
