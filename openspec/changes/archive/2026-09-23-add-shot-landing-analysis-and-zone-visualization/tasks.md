## 1. 后端契约与分区基础

- [x] 1.1 新增 `shot-landings.v1` Pydantic schema，覆盖 artifact envelope、Landing 三维状态、绝对/标准化坐标、profile、summary、diagnostics 和 provenance，并为非法状态组合增加校验测试。
- [x] 1.2 实现版本化 `landing-classification.v1`、`landing-orientation.v1` 和 `project12.v1` profile，明确 0.1 ft 缺省不确定容差、250 ms 接触邻域及 K/T/D/VD × L/C/R 边界 basis。
- [x] 1.3 为 `project12.v1` 添加纯函数单元测试，覆盖 1/3、2/3、7/12/17/22 ft 精确边界、左右视角、非有限值和不合格落点不入区。

## 2. Shot Landing Composer

- [x] 2.1 实现从 `ShotEvent.trajectory.segment_ids` 到 reconstructed Segment 再到 `end_event_id`/Event 的严格索引与确定性排序，禁止创建 Shot ID 或使用时间最近邻。
- [x] 2.2 实现 first formal Bounce 选取与 `available | no_bounce_before_next_contact | bounce_without_court_coordinate | ambiguous_bounce | unavailable` 状态机，覆盖多次 Bounce、Hit→Hit、Loss/EOS 和悬空引用。
- [x] 2.3 实现绝对 court coordinate 保留、基于 uncertainty/保守容差的 `court_location` 分类与不 clamp 界外坐标的行为。
- [x] 2.4 实现 canonical Player_N 在 `contact_ms ± 250 ms` 的动态半场解析，对单摄使用 `player_render_trajectory.v2`、对双摄 Parent 使用公开 canonical fused trajectory，并测试投影失败/身份不匹配时不采用。
- [x] 2.5 实现 `trajectory_direction` 二级 fallback、`identity | rotate_180` 方向变换、`u/v` 标准化与证据不足时 fail closed，确保不使用落点半场反推方向。
- [x] 2.6 实现 `target_relation`、`project12.v1` 标签、逐条 profile/provenance 与 artifact summary 的分子分母，保持 `paper6` 字段为 null。
- [x] 2.7 增加 Composer 端到端 fixture 测试，验证相同输入除 `generated_at` 外逐字段一致，且每条可用 Landing 都能解析到存在的 canonical Shot、Segment 和 Event。

## 3. Artifact 生成与发布链路

- [x] 3.1 在 StorageService 新增兼容 CaptureTake 和上传任务的 `shot_landings_json_path(job_id)`，并测试 session analysis root 与 legacy output root 解析。
- [x] 3.2 将 Shot Landing Composer 接入 canonical Shot/Rally 生成后的可选 post-processing，使用已冻结的任务轨迹输入，并确保新 artifact 失败不改变主 pipeline 完成状态。
- [x] 3.3 扩展 Backend Pipeline Result schema 与公开 manifest，发布可选 `shot_landings_json_path/url/status/detail` 并确保 CaptureTake 结果不泄漏绝对路径。
- [x] 3.4 在 artifact route 注册 `shot-landings`，实现已生成 JSON 返回 200、已知但缺失返回 404、跨 job/任意路径读取被拒绝的 API 测试。
- [x] 3.5 增加单摄、双摄 Parent、无 Shot、无 reconstructed input 和 Composer 异常的发布集成测试，验证 status/detail/path/url 一致性。

## 4. 前端数据契约与 capability

- [x] 4.1 新增 `ShotLandingsArtifact` 及 Landing/profile/summary TypeScript 类型，并为缺失可选字段和非法 payload 增加安全解析测试。
- [x] 4.2 在 `analysisClient` 实现 `getShotLandings(result)`，覆盖有 URL、无 URL、404 和 malformed JSON 的测试。
- [x] 4.3 将 `landing` 加入 LibraryView、路由 query 解析与 workspace Tab，并保持 selected `analysisJob` 在 view 切换中稳定。
- [x] 4.4 实现基于 selected Job `shot_landings_url` 的独立 `landingReady` 门控，测试“球路不可用但落点可用”和“球路可用但落点缺失”两个方向。
- [x] 4.5 增加历史 Job 切换、跨素材 Job、internal child、已删除 Job 与再次分析期间旧结果保留的 Landing capability 回归测试。

## 5. 落点可视化与交互

- [x] 5.1 实现纯 `landingVisualization` 适配层，完成 Player/Rally/Stage/confidence 筛选、状态分组、十二区 count/ratio 和摘要分子分母，并添加单元测试。
- [x] 5.2 实现专用 LandingCourtMap，绘制标准化连续落点、界外 buffer 点与选中状态，确保界外点不 clamp 且缺坐标 Shot 不会被绘制到 `(0,0)`。
- [x] 5.3 实现 LandingZoneGrid，以可入区 Landing 数为分母显示 12 区 count/ratio 与颜色深浅，不复用球员停留时间 `StructuredHeatmap` 契约。
- [x] 5.4 实现 LandingFilterToolbar、LandingSummary 和 LandingShotList，使所有组件共享同一筛选集合与 selected `shot_id`，并显式呈现无弹地、无坐标、界外、己方和方向不明状态。
- [x] 5.5 实现 LandingAnalysis Content/Page 的 loading、available、empty、partial/unavailable 和 failed 状态，首版开放“连续落点 / 项目十二区”并将“论文六区·待配置”置为禁用。
- [x] 5.6 将 Landing view 以 lazy-loaded embedded content 接入 LibraryItemWorkspace，测试成功/空/错误状态不泄漏旧 page shell。

## 6. Shot 选中与视频回溯

- [x] 6.1 实现散点、分区 overlay 和 Shot 列表间的 selected `shot_id` 同步，并在筛选排除当前 Shot 时确定性清除/重选。
- [x] 6.2 实现落点详情卡，显示 Shot/Rally/拍序/球员/时间/绝对坐标/分区/质量与 provenance，对 null/unavailable 字段使用诚实文案。
- [x] 6.3 实现“查看视频”联动，以 replace 语义转到同一素材 `view=video`，保留 selected `analysisJob`，并使用 `max(0, timestamp_ms-1200)` 作为定位时间。
- [x] 6.4 增加工作区路由和播放器集成测试，验证落点跳转不新增多余浏览器历史、不丢失 Job 版本且播放器使用预滚动时间。

## 7. 验收与文档

- [x] 7.1 使用至少一份真实或已脱敏 artifact 组合做冒烟验证，手工核对 Shot→Segment→Bounce 链路、旋转方向、界外点和视频时刻。
- [x] 7.2 运行前端 build/test/lint 与后端相关 pytest，修复新增失败，并记录无模型环境下未覆盖的真实视频风险。
- [x] 7.3 更新 canonical Shot/Rally 交接、artifact 发布和素材工作区文档，明确 `shot-landings.v1` 的身份权威、分母、非裁判语义、profile 版本及首版 OUT 范围。

## 8. 真实双摄运行修复（不接入骨架）

- [x] 8.1 启用本地人物推理，正式双摄禁止空检测器，补齐阶段转换与空产物失败检查。
- [x] 8.2 双摄球路接入正式 Shot assembler，保留事件、段与落点证据；修复视频球层与双视角发布。
- [x] 8.3 修复 formal segmentation 洞察来源校验、产物状态与误导性完成文案。
- [x] 8.4 复用已有产物验证后处理恢复，以真实短回合验证人物、球路、事件、落点与报告，并记录实际限制。
