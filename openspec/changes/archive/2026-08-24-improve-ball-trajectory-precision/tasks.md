## 1. 质量门契约与配置

- [x] 1.1 定义候选、track、segment 和双摄 pair 的质量状态、reason code、`display_level`、`display_eligible` 与 provenance 类型，并明确旧 artifact 缺失字段时的兼容默认值
- [x] 1.2 为质量门建立带版本号的任务配置快照，覆盖球场投影、候选尺度、N-of-M 确认、重捕获、运动阈值、最大插值秒数和双摄配对门限
- [x] 1.3 新增统一质量门模块，提供候选过滤、运动连续性、插值资格和双摄 pair 资格的可复用接口，并让每个接口返回结构化 reason code
- [x] 1.4 为质量门配置和输出契约补充序列化/反序列化测试，确保同一配置与输入在重放时产生确定结果

## 2. 单视角候选与跟踪

- [x] 2.1 将标定视角的球场空间棱柱投影接入候选过滤，并为无标定视角提供带降级标记的宽松 ROI
- [x] 2.2 在 `BallTracker` 接入候选置信度、面积比例、宽高比、尺度变化和静态区域约束，区分拒绝候选与仅诊断候选
- [x] 2.3 实现 `tentative`、`locked`、`lost/searching` 状态转移和 N-of-M 确认，禁止未确认候选进入正式球路
- [x] 2.4 为正常跟踪与重捕获分别接入空间、尺度、速度和方向门控，避免单个高置信度误检接管旧轨迹
- [x] 2.5 基于实际 `timestamp_sec` 接入速度、方向变化和加速度约束，并在运动跳变时输出断点及 reason code
- [x] 2.6 为场边物体、单帧误检、网前高速球、遮挡后错误重捕获和合法重捕获补充 `BallTracker` 单元测试

## 3. 时间感知清洗与断点

- [x] 3.1 将 `TrajectoryCleaner` 的最大插值限制从样本点数量改为秒数，并同时保留 frame index 与 timestamp
- [x] 3.2 让清洗器在长缺口、lost/searching、reset、运动跳变和事件边界处结束当前连续段，禁止跨边界插值
- [x] 3.3 为每个 detected、interpolated、model_predicted 样本以及每个 gap boundary 写入 provenance、缺口时长和断点原因
- [x] 3.4 增加不同 `frame_stride`、短缺口、长缺口和重新出现观测的清洗回归测试，验证不再产生跨秒级丢失的直线球路

## 4. 双摄关联与三角测量

- [x] 4.1 确认 joint canonical tick 复用各视角候选，并把每视角的几何质量门输入 `association` 和 `canonical_runner`
- [x] 4.2 为候选 pair 实现时间匹配、重投影误差、三角测量几何、3D 球场棱柱、运动连续性和次优 pair margin 评分
- [x] 4.3 仅允许通过硬门且达到歧义 margin 的 pair 更新权威 tracker、stereo anchor、三角测量和落点证据
- [x] 4.4 将低质量或歧义 pair 保留到 diagnostic，不得作为权威测量或默认 overlay 的证据
- [x] 4.5 为唯一可信 pair、歧义 pair、超出 3D 范围 pair、单视角 tick 和时间不同步场景补充双摄回归测试

## 5. Artifact 与混合轨迹发布

- [x] 5.1 扩展 raw/cleaned/reconstructed 的写出逻辑，记录质量门摘要、观测覆盖、插值/预测比例、断点、配置版本和段级展示资格
- [x] 5.2 调整混合段构建，使 `single_view_visual_arc` 等降级段明确标记 `display_level`，不得因生成成功自动获得默认展示资格
- [x] 5.3 保持 `display_trajectory_status`、3D overall status 和指标级 validity 相互独立，避免低质量段提升整体可用状态
- [x] 5.4 增加历史 v1/v2/v3 artifact 兼容读取测试，确认不回写历史文件、不伪造新质量字段，并保留 raw/cleaned/reconstructed 三套数据
- [x] 5.5 增加 artifact schema/API 回归测试，验证拒绝原因、provenance、断点和 `display_eligible` 与诊断结果一致

## 6. 前端默认展示

- [x] 6.1 扩展前端 artifact 类型与 adapter，读取段级 `display_level`、`display_eligible`、provenance、断点和质量摘要
- [x] 6.2 更新 `VideoAnalysisCard` 的球路解析与 overlay 过滤：默认只绘制合格段，低质量视觉弧和 diagnostic-only 结果仅在调试/原始检测模式显示
- [x] 6.3 让前端严格遵守 artifact 断点，不自行跨长缺口插值、平滑或把相邻 segment 拼接
- [x] 6.4 为默认隐藏、调试显示、低质量状态、断点和旧 artifact 降级读取补充前端 adapter/组件测试

## 7. 离线验收与发布控制

- [x] 7.1 建立可回放的误检 hard-negative fixture，覆盖场边设备、广告区域、网后物体、遮挡和高速球片段
- [x] 7.2 对真实双摄样例 `sync_20260720_122645_317228` 生成新旧链路对比，统计误检点 precision、错误球路秒数、断点跨越率、双摄 pair precision 和默认展示合格率
- [x] 7.3 将质量门配置版本、拒绝原因和降级比例写入任务诊断，确认开发者可以定位“未检测到”和“被规则拒绝”的差异
- [x] 7.4 在通过单元、回归、artifact/API 和前端测试后，记录阈值校准结果与已知召回损失，并准备按配置版本回退的发布方案
