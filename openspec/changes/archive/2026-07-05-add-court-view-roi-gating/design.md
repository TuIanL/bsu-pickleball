## Context

当前真实视频分析依赖用户或自动流程提供球场四角标定，然后在 `AnalysisPipeline._run_tracking` 中按帧读取视频、运行 person detection、tracking、脚点投影、主球员筛选、姿态估计和后续指标。这个流程已经能输出 player trajectories、tracking overlay、pose overlay 和 serve-start candidates，但它默认把每个采样帧都当作可分析比赛画面处理。

真实比赛素材经常包含切到记分牌、观众、暂停、重放或非目标球场的片段。即使标定有效，非球场帧和邻场人物也会增加误检、ID 断裂、pose 开销和 serve-start 误报。Good-Pickleball 使用模板匹配与连续帧阈值维护一个简单回合状态机，这不是正式比赛语义，但作为输入门控很有价值。

本设计把这类能力放入平台型 pipeline：输出结构化 artifact 和诊断，而不是直接把状态画死在视频里。

## Goals / Non-Goals

**Goals:**

- 为已标定真实视频生成 court-view gate 结果和候选片段 artifact。
- 从标定四角点推导 expanded ROI，并用于限制 person detection 或过滤 detection 结果。
- 在 pipeline stages、raw result artifacts 和 tracking 诊断中暴露 gate/ROI 状态。
- 保持现有 tracking、pose、player identity、metrics 和 serve-start 能力可用，并让它们消费更干净的输入。
- 对缺少标定、缺少模板/参考帧、低置信度或算法不可用场景提供保守降级。

**Non-Goals:**

- 不实现 ball detection、ball trajectory、bounce detection、shot events。
- 不输出完整 rally segmentation、比分、失误原因或战术结论。
- 不把 OpenCV 直接绘制视频作为主要产品输出。
- 不用 Tkinter 或本地窗口交互替代现有 Web calibration flow。
- 不要求新增外部模型依赖。

## Decisions

### 1. 将 court-view 输出命名为候选片段，而不是回合

采用 `court_view_segments` / `camera_rally_candidates` 语义，避免称为正式 rally。候选片段仅表示“连续满足球场视角门槛的时间段”，可以辅助 serve-start 或 UI 跳转，但不得推断得分、击球或失误。

备选方案是直接输出 `rallies`。拒绝原因是当前没有球、弹跳、出界、击球或计分信号，直接叫 rally 会造成产品语义过度承诺。

### 2. 优先使用标定帧/四角点构建 reference，而不是要求用户额外上传模板图

Good-Pickleball 使用独立 court template 做匹配。我们已有 video upload 与 calibration handoff，因此实现应优先复用标定时选中的帧、自动标定预览帧或从视频抽取的参考帧。若没有可用参考帧，则 court-view gate 标记为 `unavailable`，ROI 仍可从四角点推导。

备选方案是要求新增 `template_path`。拒绝原因是 Web 产品流程中本地模板文件会增加用户负担，也不适合 API 化 job orchestration。

### 3. ROI 推导使用四角点 x 范围扩展，作为第一版保守实现

第一版 ROI 可按 Good-Pickleball 的思路从四角点包围盒推导：左右按球场图像宽度扩展配置比例，纵向默认覆盖整帧或使用配置的安全范围。检测前裁剪 ROI 时，需要把 bbox 坐标映射回源帧；如果不裁剪模型输入，也必须在检测后过滤 ROI 外 box 并记录计数。

备选方案是用 homography 反投影标准球场所有线段生成精确多边形 ROI。该方案更精确，但第一版实现和测试复杂度更高；可作为后续增强。

### 4. court-view gate 应支持保守跳过模型推理

当 gate 明确判断当前采样帧不是球场视角时，pipeline 可以跳过 person detection、tracking update、pose estimation，并记录 gated frame。为避免误判导致轨迹大面积断裂，gate 需要连续帧阈值与状态机：短暂低分帧不立即结束片段，短暂高分帧不立即开启片段。

备选方案是所有帧继续跑模型，仅把 gate 结果作为诊断。该方案风险更低但无法减少误检和性能开销；实现时可通过配置保留诊断-only 模式作为回滚开关。

### 5. Artifact 优先于直接 UI 假设

新增 artifact 应包含 frame-level gate summary、segment list、ROI、阈值、计数和状态。前端可以先只展示状态和诊断，不必立即渲染每帧 gate。

备选方案是只在 tracking artifact counters 中塞字段。拒绝原因是 gate/ROI 会被 serve-start、debug、未来 ball tracking 复用，独立 artifact 更清晰。

## Risks / Trade-offs

- 模板匹配受光照、缩放、转播字幕和相机抖动影响 → 使用低分诊断、连续帧阈值和可配置禁用开关；第一版结果只声明候选片段。
- ROI 过窄导致真实球员被裁掉 → 默认扩展比例保守，允许记录 ROI 外检测计数，并在诊断中提示可能过窄。
- 跳过非球场帧会影响 tracker lost 状态 → gated frames 应与普通 missed detections 区分，必要时不推进或以专门状态推进 tracker。
- 缺少标定图像角点或参考帧 → ROI/gate 分别降级；缺 gate 不应阻止现有已标定 tracking 路径运行。
- 新 artifact 增加 schema/API 面 → 通过 storage/result artifacts 统一引用，并保持旧客户端忽略未知字段也能工作。

## Migration Plan

1. 新增 schemas、storage path 和 pipeline artifact 字段，默认状态为 unavailable/skipped，不影响现有 job。
2. 实现 ROI 推导和单元测试，再接入 detection 前裁剪或检测后过滤。
3. 实现 court-view state machine 和 artifact 写入，默认可配置为诊断-only。
4. 将阶段状态接入 job progress 和 raw result。
5. 添加 pipeline 集成测试，确认缺少 gate 资源时现有 tracking/pose/metrics 仍通过。
6. 如出现误门控问题，可通过配置关闭 gate 跳过，仅保留 ROI 或诊断 artifact。

## Open Questions

- 第一版 court-view reference 使用哪个帧最稳：标定帧、视频首个已标定帧，还是自动从前 N 秒抽取的最高匹配帧？
- ROI 是否在第一版裁剪模型输入，还是先做检测后过滤以降低 bbox 坐标转换风险？
- gated frame 对 tracker 生命周期应采用“冻结时间”还是“推进 lost 但标记原因”的策略？
