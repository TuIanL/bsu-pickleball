## Why

当前名册确认要求用户从视频中寻找画面、截帧并逐个画框；首次分析的自动预检又只看前 3 秒，开场球员尚未入场时容易把场外人员选为候选。即使用户看到了四张裁剪图，现有画面锚点与正式分析轨迹之间仍可能缺少可验证的身份连接，无法可靠判断 P1–P4 是否锁定正确。

## What Changes

- 分析前自动从视频中段及其邻近的多个时间窗口寻找目标球场内稳定可见的四名球员；双摄素材可综合两路证据。选择依据包含目标球场位置、短时连续性、画面质量、球衣外观与跨机位一致性，而非随机抽一帧或仅按检测人数排序。
- 确认页优先直接呈现带 P1–P4 标记的四张人物卡片和参考画面。清晰度足够时可展示脸部放大图，但完整人物与球衣是远景素材的基本身份依据。用户可以交换或纠正对应关系；自动证据不足时提供重新选帧和手工框选入口。
- 将用户确认的画面锚点及其时间、机位、球场位置和外观证据传入正式分析，按同一时间段的实际观测核验 P1–P4 绑定。绑定失败须明确标注，不得凭候选顺序或宽松的全片位置匹配宣称身份已确认。
- 保留 Team A/B 和初始端位的人工确认，以支持依赖正式队伍身份的指标；普通分析继续允许跳过。第一阶段暂不提供姓名录入，界面始终显示 P1–P4，并保留现有 `display_name` 字段供后续姓名功能使用。

## Capabilities

### New Capabilities

- `automatic-player-roster-candidates`: 定义多时段、多证据的四人候选选取、可展示画面和不足四人时的降级行为。

### Modified Capabilities

- `analysis-roster-confirmation`: 将默认交互改为自动候选核对，并强化人工确认结果与正式分析身份的可审计绑定。

## Impact

- 后端预检与身份核验：`backend/app/services/analysis_rally_context_service.py`、`backend/app/api/routes_analysis_roster.py`、相关视觉检测、球场选择、外观与双摄关联模块。
- 前端确认页与请求契约：`src/components/platform/AnalysisRosterConfirmation.tsx`、`src/types/rallyContext.ts`、`src/services/analysisClient.ts`，以及三个使用该组件的分析入口。
- 需要补充自动候选、画面与 bbox 同时刻一致性、P1–P4 纠正、正式绑定和降级路径的测试；无需新增球员姓名存储接口。
