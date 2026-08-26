## Why

当前 joint_tracking_v2 的视频分析结果在参考视角存在明显的可视化不稳定：P2/P4 的本视角关联在真实检测与跨视角投影之间快速切换，导致框位置跳变、闪烁和局部重叠；这会让用户误以为球员身份发生互换。与此同时，球路片段按各自质量选择 `primary_view_id`，前端又会短暂保留已结束片段，造成相邻片段在边界处同时显示，并可能把不同摄像头的 image-space 坐标叠加到同一个视频画面中。现在需要把“参考视角展示稳定性”和“球路视频叠加坐标连续性”收敛为明确、可测试的契约。

## What Changes

- 强化跨视角球员关联的 incumbent 保持、候选重关联确认和参考视角关联诊断，避免 P2/P4 因单帧歧义频繁切换。
- 约束 fused overlay 的跨视角投影：所有投影框必须绑定当前参考视角，经过几何、连续性和碰撞/跳变门控；投影证据不得覆盖更可靠的本视角证据。
- 增加展示几何的时间连续性约束，使真实框、投影框和回退框在证据切换时保持稳定位置与尺寸，同时继续诚实标注 `evidence_type`。
- 为球路视频叠加固定单一渲染视角；当任务视频是 `cam_1` 时，片段必须提供或转换为 `cam_1` 的 image-space 坐标，禁止按片段随意混用 `cam_1`/`cam_2` 坐标。
- 修正相邻球路片段的边界合成：边界时间只允许一个活动渲染上下文，已结束片段的保留窗口不得与下一片段产生重复轨迹；保留端点时也必须经过同一视角和时间边界去重。
- 补充球员 overlay 与球路 compositor 的回归测试、artifact diagnostics 和可观测质量字段。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `multiview-player-association`：加强参考视角关联的迟滞、候选歧义处理和重关联诊断。
- `multiview-fused-player-overlay`：收紧参考视角投影证据、投影几何门控和证据切换时的展示契约。
- `stabilize-multiview-overlay-display`：增加真实框与投影框之间的几何连续性和跳变抑制要求。
- `hybrid-segmented-ball-trajectory-delivery`：为视频叠加定义任务级固定视角、片段坐标转换和边界保留语义。
- `ball-trajectory-visualization`：禁止相邻片段在同一时刻重复渲染，并要求前端按统一视角与稳定边界消费轨迹。

## Impact

- 后端：`GlobalPlayerAssociator`、fused player overlay builder、target-view projection、ball segment view selection 与 artifact diagnostics。
- 前端：`VideoAnalysisCard`、球路叠加路径解析、segment 时间窗口与视角选择逻辑。
- API/artifact：可能新增 reference-view、projection gate、trajectory render view、边界去重和保留原因等诊断字段；既有字段保持兼容。
- 测试：增加 P2/P4 8–13 秒证据切换回放用例、投影框跳变/重叠用例、33 秒相邻片段边界用例、不同 `primary_view_id` 的坐标空间用例。
