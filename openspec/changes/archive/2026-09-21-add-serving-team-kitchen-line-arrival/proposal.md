## Why

现有位置热图和三区占用只能描述全场站位，不能回答双打发球队在一分中是否成功推进至己方厨房线。发球队、名册、端位与正式窗口的可审计事实链由前置 change `add-analysis-roster-and-rally-context` 建立；本变更只在该上下文可用时消费真实轨迹，生成诚实的描述性到位率。

## What Changes

- 新增 `kitchen-arrival.v1` 汇总产物和 `metric-snapshot.v1` player metric：`serving_team_kitchen_line_arrival_rate`；已经稳定到位的球员计为成功。
- 到位以真实检测轨迹的距离和稳定时间证明；未到位还要求覆盖率、最大缺口和无不确定跨越到位带的完整反证。
- 非可用指标必须保留计数与状态：`insufficient_evidence` 的 `value=null`，不得显示误导性的百分比。
- 在视频分析工作区增加独立加载的“发球队 · 网前到位率”场地控制主卡；当前以双打入口 feature flag 优先开放，但 calculator 不写死镜头格式。

## Capabilities

### New Capabilities

- `serving-team-kitchen-line-arrival`: 消费冻结上下文与真实轨迹，计算发球队厨房线到位率及充分度状态。
- `serving-team-arrival-visualization`: 在真实任务的视频分析工作区展示发球队网前到位率主卡。

### Modified Capabilities

- `shot-rally-event-metrics`: `metric-snapshot.v1` 镜像厨房线到位率及其充分度状态。
- `visual-analysis-workspace`: 已完成真实任务新增独立加载的场地控制主卡与正确降级状态。

## Impact

- 后端：厨房线目标解析、轨迹充分度状态机、汇总/metric artifact、artifact 路由与测试。
- 前端：视频分析页的数据加载与场地控制卡。
- 前置依赖：只接受 `add-analysis-roster-and-rally-context` 产出的 job-bound `AnalysisRallyContextSnapshot`、identity audit 和正式窗口绑定；缺任一权威输入即 honest unavailable。
