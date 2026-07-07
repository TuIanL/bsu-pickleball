## Context

当前项目已经完成 Good-Pickleball 迁移链路中的前置能力：摄像头/视频输入、CourtVision 标定、player tracking、pose overlay、球轨迹、清洗球轨迹、弹跳候选和球员轨迹 artifact。`StorageService`、`AnalysisArtifacts` 和 artifact API 也已经为 `analysis_overlay.mp4`、heatmap manifest、scatter manifest 预留了固定路径和 URL 字段。

缺口在 `AnalysisPipeline` 的 visualization 阶段：它目前固定追加 skipped 阶段，说明为“MVP 暂不生成叠加视频文件”。因此本 change 的重点不是重新设计 API，而是把已承诺的可视化 artifact 真正生成出来，并让前端可以消费。

Good-Pickleball 提供了可迁移的方向，包括小地图、标注视频、位置热力图/散点图和中英文显示。但本项目的标准球场坐标是 20 ft × 44 ft，Good-Pickleball 的米制场地常量不能直接复制。所有输出必须与现有 CourtVision / bsu-pickleball 坐标约定保持一致。

## Goals / Non-Goals

**Goals:**

- 新增独立可测试的 visualization 模块，保持与 FastAPI route 解耦。
- 生成 `analysis_overlay.mp4`，绘制人物框、姿态骨架、球轨迹、弹跳候选和小地图面板。
- 基于现有标准匹克球场几何生成小地图，支持球员、球和弹跳点绘制。
- 生成 player position heatmaps、player position scatter plots、ball trajectory scatter plot 和 bounce point scatter plot。
- 写入 `position_visualizations/heatmaps/manifest.json` 与 `position_visualizations/scatter_plots/manifest.json`。
- 在 `AnalysisPipeline` 中尊重 `enable_analysis_overlay_video`、`enable_position_visualizations` 和 `visualization_language`。
- 可视化失败时只标记相关 artifact failed/unavailable，不导致整个分析任务失败。
- 前端读取并展示可用的叠加视频、热力图和散点图，同时保留 disabled/missing/failing 的稳定状态。

**Non-Goals:**

- 不做 Kinovea、annotation file persistence、annotation import API 或 normalized annotation schema。
- 不做人工标注报告和 PDF 导出。
- 不替换现有 tracking、pose、ball trajectory、bounce detection 或 player trajectory pipeline。
- 不迁移 Good-Pickleball CLI 入口。
- 不把 Good-Pickleball 的米制 `CourtMapper` 常量作为本项目坐标标准。
- 不要求默认环境强制生成可视化输出；现有默认开关仍可保持关闭。

## Decisions

### 1. 可视化模块放在 `pickleball_game_analysis`

新增模块建议为：

```text
backend/app/vision/pickleball_game_analysis/minimap_visualizer.py
backend/app/vision/pickleball_game_analysis/overlay_video_writer.py
backend/app/vision/pickleball_game_analysis/position_visualizer.py
backend/app/vision/pickleball_game_analysis/visualization_schemas.py
```

理由：这些模块消费 Good-Pickleball 迁移链路中的 game analysis artifact，和 `ball_tracker.py`、`bounce_detector.py` 等已有模块属于同一层。它们不应该依赖 FastAPI route，也不应该把绘制逻辑塞入 `AnalysisPipeline`。

备选方案是把所有绘制代码直接写进 `analysis_pipeline.py`，但这会让 pipeline 变成图像渲染协调器，测试和降级都更困难。

### 2. 小地图以项目标准球场几何为唯一真源

`MinimapVisualizer` 使用 `standard_court()` 提供的 boundary、net、kitchen line、center line 和 service zones。坐标映射从 court feet 到 minimap pixels：

```text
court x: 0..20 ft  -> minimap x: padding..width-padding
court y: 0..44 ft  -> minimap y: padding..height-padding
```

理由：球、弹跳和部分 player trajectory 消费者已经依赖 20 ft × 44 ft 的 CourtVision 语义。小地图必须和这些产物同一坐标系，否则同一 job 的不同图层会出现错位。

备选方案是复用 Good-Pickleball 米制常量后再转换，但这会引入重复标准；本项目已有 court geometry，无需新增第二套真源。

### 3. 统一 artifact reader，容忍缺失输入

可视化阶段读取以下 artifact：

```text
tracking_overlay.json
pose_overlay.json
ball_overlay.json
players_trajectory.json
ball_trajectory.json
cleaned_ball_trajectory.json
bounce_events.json
source video
```

读取策略是“存在则使用，不存在则跳过对应图层”。例如只有 tracking overlay 时仍可生成人物框叠加视频；缺少 pose 时只不画骨架；缺少 cleaned ball trajectory 时可回退 raw ball trajectory；缺少 source video 时不生成 mp4，但仍可生成位置图片。

理由：这些 artifact 都是可选产物，已有 pipeline 允许相关字段为 null。可视化层必须继承这种可选语义。

### 4. Overlay video writer 用 OpenCV 做第一版

`OverlayVideoWriter` 使用 OpenCV 读取源视频并写出 mp4。按 frame_index 或 timestamp 对齐 overlay 数据，绘制顺序为：

```text
source frame
  -> player bbox / ID
  -> pose skeleton
  -> ball marker / recent trail
  -> bounce markers
  -> minimap panel
  -> optional labels
```

理由：项目后端已经使用 OpenCV 读取视频，继续用 OpenCV 可以避免引入 FFmpeg filter graph 或前端 canvas 导出复杂度。视频编码失败时可捕获异常并标记 overlay artifact failed。

备选方案是前端动态叠加后再录制，但这会把重计算和导出交给浏览器，且难以作为稳定后端 artifact 被 API 返回。

### 5. 图片可视化用 manifest 作为唯一前端入口

`PositionVisualizer` 将图片保存到：

```text
position_visualizations/heatmaps/
position_visualizations/scatter_plots/
```

并分别写入 manifest。manifest 顶层包含 `schema_version`、`job_id`、`status`、`detail`、`items`。每个 item 至少包含 `id`、`kind`、`label`、`title`、`description`、`file_name`、`file_path`、`url`、`width`、`height` 和 `source_artifacts`。

理由：API 已经把 `position-heatmaps` 和 `position-scatter-plots` 定义为 manifest JSON，而不是目录 listing。前端只需要读取 manifest，再根据 item URL 展示图片。

备选方案是让前端请求目录下所有图片，但这会把本地目录结构暴露为 API 合同，也不利于未来添加 metadata。

### 6. Label 语言集中配置，字体失败不阻断输出

新增 label resolver，支持 `zh-CN` 和 `en-US`，未识别语言回退到 `zh-CN`。文字渲染只作为增强能力：如果中文字体不可用，OpenCV 文本可退化为英文/ASCII 或跳过文本，但图形输出仍应成功。

理由：Good-Pickleball 有中英文可视化文本，本项目已有 `visualization_language` 设置。中文字体在不同部署环境中不稳定，不能让字体问题导致整个分析失败。

### 7. Pipeline 中 visualization 是可选降级阶段

`AnalysisPipeline` 在 metrics 和球分析 artifact 完成之后执行 visualization：

```text
metrics done
  -> visualization enabled?
      -> overlay video generation
      -> position visualization generation
      -> stage done / partial / skipped / failed
  -> result write
```

如果两个开关都关闭，stage 为 skipped。如果任一输出成功，stage 为 done 或 partial。如果生成异常，设置对应 artifact status/detail，并继续完成 pipeline。

理由：可视化成本高于 JSON artifact，尤其是 mp4 写出。它应该是用户体验增强，而不是核心算法成功的前提。

### 8. 前端先展示 artifact，缺失时展示状态

前端需要扩展类型和 client helper，读取：

```text
analysis_overlay_video_url
heatmaps_url
scatter_plots_url
analysis_overlay_video_status/detail
position_visualizations_status/detail
```

视觉工作台可优先展示 `analysis_overlay.mp4`；若没有叠加视频，则保留现有源视频 + overlay JSON 的播放方式。热力图和散点图根据 manifest items 渲染图片列表，disabled/missing/failed 时显示稳定状态而不是空白。

理由：当前前端已经有 tracking/pose/ball/bounce artifact 状态展示，继续沿用“可用则加载、不可用则说明”的模式即可。

## Risks / Trade-offs

- [Risk] OpenCV mp4 编码在某些环境不可用 → Mitigation：捕获 writer 初始化和写帧异常，设置 `analysis_overlay_video_status=failed`，pipeline 继续 completed。
- [Risk] 中文字体不可用导致 label 渲染乱码 → Mitigation：文字绘制可选，语言回退和无字体降级不阻断图形输出。
- [Risk] player trajectory 可能以 metric metadata 表达，而球轨迹是 feet → Mitigation：可视化入口统一 normalize 到 20 ft × 44 ft，读取 artifact 的 `court_unit` / `coordinate_system` 后转换或跳过不可识别点。
- [Risk] 长视频生成 overlay 成本高 → Mitigation：由 `enable_analysis_overlay_video` 控制，默认可保持关闭；失败或超时不影响核心结果。
- [Risk] manifest 图片 URL 需要能被浏览器读取 → Mitigation：优先通过现有 artifact route 返回 manifest；图片 URL 使用同一 job 下稳定 API 或静态文件服务约定，并在 manifest 中显式写入。
- [Risk] 位置可视化容易被误解为战术结论 → Mitigation：manifest description 使用“候选/估计/轨迹事实”措辞，不声明比分、犯规或击球归因。

## Migration Plan

1. 新增 visualization schema、minimap、position visualization 和 overlay writer 模块及单元测试。
2. 在 `AnalysisPipeline` 中接入可视化阶段，先接 position visualization，再接 overlay video。
3. 扩展前端类型、client helper 和分析结果页展示逻辑。
4. 更新迁移说明文档，记录 Good-Pickleball 到本项目模块和 artifact 的映射。
5. 运行后端单元测试、前端类型检查，并用最小 fixture 验证 manifest 与 mp4 route。

回滚策略：关闭 `enable_analysis_overlay_video` 和 `enable_position_visualizations` 即可恢复为不生成可视化；如需代码回滚，可移除新增模块和 pipeline visualization 调用，既有 artifact API 与历史结果不受影响。

## Open Questions

- 图片文件本身是否通过新增 artifact sub-route 暴露，还是通过现有 outputs 静态服务暴露？
- 第一版 overlay video 是否只处理已抽样 frame，还是按源视频全帧写出并用最近 overlay sample 对齐？
- 位置热力图第一版是否使用 OpenCV/numpy 绘制，还是引入 matplotlib 以获得更好的 colorbar 和标题排版？
