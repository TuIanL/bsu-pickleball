# collapse-calibration-diagnostics — Delta Spec

## MODIFIED Requirements

### Requirement: User-facing automatic calibration diagnostics

系统 SHALL 在 upload workflow 中为 available / unavailable / rejected / failed 的自动球场线标定尝试暴露可操作的诊断信息。开发诊断细节（confidence、模型信息、Mask 统计、选中帧、preview 等）SHALL 默认折叠隐藏，仅通过标题旁 Info (i) 图标展开，避免干扰用户聚焦可拖拽四边形主画面；识别中进度与失败/拒绝的操作指引 SHALL 保持默认可见，不进折叠。

#### Scenario: Automatic calibration is available

- **WHEN** automatic court-line calibration returns an available suggestion
- **THEN** the upload workflow SHALL 默认仅显示主画面与已自动铺设的可拖拽四边形
- **AND** 开发诊断细节（confidence、selected frame reference、keypoint fill status、preview、calibration quality diagnostics）SHALL 折叠隐藏
- **AND** 用户点击标题旁 Info (i) 图标后 SHALL 展开显示上述诊断细节，再次点击 SHALL 收起

#### Scenario: 自动标定进行中显示进度

- **WHEN** 自动标定请求处于上传或识别中（uploading / detecting）
- **THEN** the upload workflow SHALL 默认可见地显示「正在自动识别球场边线…」进度文本
- **AND** 该进度文本 SHALL NOT 被折叠隐藏

#### Scenario: Automatic calibration model is unavailable

- **WHEN** automatic court-line calibration returns unavailable because the model path is unset, missing, or cannot be loaded
- **THEN** the upload workflow SHALL 默认可见地显示模型不可用诊断（包括返回的 configured model path）与人工标定可用指引
- **AND** manual four-corner calibration SHALL 保持可用

#### Scenario: Automatic calibration geometry is rejected

- **WHEN** automatic court-line calibration returns rejected because the mask or fitted geometry fails validation
- **THEN** the upload workflow SHALL 默认可见地显示拒绝指引（提示用户手动拖动或调整标定帧）
- **AND** 用户点击 Info (i) 图标后 SHALL 展开显示 rejection detail、mask confidence、mask area ratio、line count、selected frame reference、preview 等诊断详情

#### Scenario: Automatic calibration request fails

- **WHEN** the automatic calibration request fails with an HTTP or network error
- **THEN** the upload workflow SHALL 默认可见地显示 request failure 状态与可用的后端 detail
- **AND** 系统 SHALL 保留 selected video、metadata 与 manual calibration controls

#### Scenario: Older automatic calibration response lacks diagnostics

- **WHEN** the frontend receives an automatic calibration response without optional diagnostic fields
- **THEN** the upload workflow SHALL 保持稳定，默认显示 concise unavailable 诊断且不崩溃
- **AND** Info (i) 图标 SHALL 在无任何诊断数据时不渲染或不可展开

#### Scenario: 诊断区默认折叠且不持久化

- **WHEN** 用户进入场地标定步骤且自动标定已有结果
- **THEN** 开发诊断区 SHALL 默认处于折叠态
- **AND** 每次进入标定（组件随 videoId 重置）SHALL 重置为折叠态，不持久化展开状态
