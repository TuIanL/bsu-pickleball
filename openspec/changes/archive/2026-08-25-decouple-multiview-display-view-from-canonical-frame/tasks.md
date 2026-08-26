## 1. 展示视角与数据契约

- [x] 1.1 定义 `displayViewId`、可用 view 列表、默认 `referenceViewId` 和 view-scoped display manifest 的前后端类型。
- [x] 1.2 明确 `displayViewId` 不进入 AnalysisJob 创建请求、input/config signature、preflight 或 canonical frame 持久化，并补充契约测试。
- [x] 1.3 为历史任务补充 display manifest/overlay 归一化读取：缺失展示字段时默认 reference view，不猜测未知 view。
- [x] 1.4 统一 metric scene calibration、canonical frame 和 Parent 产物中的实际 `ccf_...` canonical frame id 引用。

## 2. 双摄展示 manifest 与统一时间映射

- [x] 2.1 从 Parent 的 `jointViewInputs`、camera identity、registered video metadata 和 sync authority 组装只读展示 manifest。
- [x] 2.2 为每个 view 暴露 video id、媒体尺寸、canonical timestamp 到 source timestamp/frame 的映射引用及有效区间。
- [x] 2.3 实现目标 view 不可映射、超出有效区间和媒体缺失时的结构化 unavailable/degraded 状态。
- [x] 2.4 增加 canonical time → cam_1/cam_2 source time 的映射单元测试和真实双摄时间切换测试。

## 3. 按 view 生成 Player overlay

- [x] 3.1 将 joint fused Player overlay 扩展为 view-scoped v2，使用同一 canonical tick 输出 cam_1/cam_2 frames。
- [x] 3.2 让每路 overlay 只读复用同一份 global roster，验证 P1-P4 的 `player_id`、`render_slot`、标签、颜色和击球归属在两路完全一致。
- [x] 3.3 保留 view-specific bbox/footpoint/evidence/quality；目标 view 无可靠 bbox 时输出 null 或明确不可见状态，不跨 Player 借框。
- [x] 3.4 为历史单路 overlay 增加 reference-view-only 适配器，并让前端安全禁用不可用的另一视角。
- [x] 3.5 增加 A→B→A、遮挡、缺帧、cross-view projected 和 Player identity stability 测试。

## 4. 球路与小地图的 view-aware 渲染

- [x] 4.1 让视频球路 renderer 根据 `displayViewId` 选择 `image_paths_by_view`，禁止从 canonical court 坐标伪造像素路径。
- [x] 4.2 让视频 Player overlay、球路和小地图在同一 canonical tick 下更新；小地图继续使用 canonical court 坐标。
- [x] 4.3 为目标 view 缺少球路 path、单视角降级和部分 segment 不可用增加明确 UI 状态。
- [x] 4.4 增加视角切换后 Player、球路、小地图位置与标签一致性测试。

## 5. 分析工作区视角切换 UI

- [x] 5.1 在双摄结果主视频分析卡增加 A/B 展示机位切换控件，默认值来自 `referenceViewId`。
- [x] 5.2 实现 `displayView` URL 参数读写，与 workspace `view`、`analysisJob` 共存，并使用 replace 语义更新。
- [x] 5.3 切换时保存 canonical time，加载目标视频并恢复对应 source time；避免播放器重置到错误的 raw frame。
- [x] 5.4 对非法、缺失产物或目标 view 不可用的 displayView 做回退和可解释提示。
- [x] 5.5 增加刷新、Tab 切换、嵌入式工作区和 A/B/A 回归测试。

## 6. Canonical frame 冲突修复

- [x] 6.1 设置页加载已有 canonical frame 的 endpoint definition 和 `orientation_by_view`，恢复当前 take 的物理朝向。
- [x] 6.2 将展示机位选择从 `canonicalFrame.endA/endB` 和 `courtOrientation` 的编辑路径中移除。
- [x] 6.3 对真实朝向变更保留显式新标定/revision 入口；普通展示切换不得触发 canonical frame conflict。
- [x] 6.4 为同一 take 重试、已存在 frame、切换默认展示机位和反向端点输入增加 preflight contract tests。

## 7. 集成验证与兼容发布

- [x] 7.1 运行现有 multiview orchestration、canonical frame、sync、fused overlay、ball trajectory 和 navigation 回归测试。
- [x] 7.2 用真实双摄任务验证分析只创建一次，A/B 切换不新增 Job，且 P1-P4、球路归属和小地图状态不变化。
- [x] 7.3 验证历史 v1 artifact、缺失 cam_2 overlay、媒体不可读和 sync degraded 场景的安全降级。
- [x] 7.4 增加 feature flag/回滚路径：view-scoped v2 失败时保留 reference-view 结果，不删除历史产物。
