## Why

真实视频分析中，脚点投影和身份追踪会产生少量处在标准球场边界附近的观测点，例如 `y = 44.2195 ft`。这些点处在跟踪容差内，但当前 `ProjectedTrackPoint` 复用严格标定点 schema，导致 Pydantic 在多目标跟踪阶段抛出校验错误并中断整个分析任务。

## What Changes

- 将标定控制点和跟踪投影观测点的 schema 语义拆开：标定点继续限制在标准 20 ft x 44 ft 球场内，投影观测点允许表达容差内或边界外坐标。
- 明确运动指标、热力图、厨房区、双打间距和标准球场可视化只消费经过边界处理的标准球场内点。
- 为投影轨迹导出增加边界语义，避免容差内越界观测点触发分析阶段失败。
- 增加回归覆盖，确保 `y` 略大于 `44 ft` 的容差观测不会让多目标跟踪阶段失败。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `player-tracking-engine`: 修改投影轨迹 schema 要求，区分严格标定点、原始投影观测点和指标消费点的边界语义。

## Impact

- 影响 Python backend 的 tracking/calibration schema、投影器、身份轨迹导出和分析管线指标入口。
- 影响 `ProjectedTrackPoint` 的 `court_point` 字段校验语义；JSON 字段形状保持 `{ "x": number, "y": number }`，不引入前端破坏性字段变更。
- 需要更新 tracking、identity、metrics 相关测试，覆盖容差内越界点的序列化和指标过滤行为。
