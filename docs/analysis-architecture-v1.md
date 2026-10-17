# 能力级局部分析开发指南

`analysis-architecture-v1` 提供单摄、双摄共用的局部验证入口。指定能力和时间窗口后，Planner 展开最小依赖，既有 Worker 执行节点，并发布可跨任务复用的不可变产物。普通产品请求继续使用 `legacy_v1`；开发请求显式选择 `modular_v1`。

## 当前可运行范围

| 能力 | 实现 | 输出 | 必需依赖 |
| --- | --- | --- | --- |
| `player.detect` | `player.yolo.v1` | 像素坐标人框、观测身份 | 来源帧 |
| `ball.detect` | `ball.yolo.v1` | 原始二维球候选 | 来源帧；双摄额外需要 PTS 和同步快照 |
| `pose.sequence` | `pose.rtmpose26.v1` | 每帧姿态观测 | 人框产物、来源帧 |

三者均可在无球场标定时执行。姿态的主体是 observation，未做稳定跨帧身份关联。只请求球不会加载人或姿态模型。模块任务返回 `ModularRunManifest`，任务详情显示节点、缓存、部分产物和技术详情。

完整能力地图在 `backend/app/analysis_runtime/registry.py`，可通过 `GET /api/analysis/capabilities` 查询。21 个未来条目为 `planned`：人员跟踪/身份、球轨迹/清洗/事件/3D、球拍检测/跟踪/归属、姿态关联、上肢运动证据、挥拍、接触、动作属性、Shot、落点、Rally、击球语义、战术、评估和指标。其类型骨架位于 `analysis_capabilities/catalog/contracts.py` 及 `analysis_runtime/contracts/`；请求 planned 能力会在创建 Job 前明确拒绝。

## CLI：先准备，再预览和执行

以下命令在 `backend` 目录运行，沿用后端环境变量、模型配置和同一控制数据库。准备阶段会读取媒体、PTS 和权重计算强摘要，应与窗口推理耗时分开看。

```sh
.venv/bin/python scripts/analysis_dev.py prepare-source /absolute/path/video.mp4 --view-id cam_1 --camera-id 174
.venv/bin/python scripts/analysis_dev.py prepare-models
```

复制第一条输出的 `source_id` 到请求文件，例如 `/tmp/local-analysis.json`：

```json
{
  "source_ids": ["source-替换为准备返回的ID"],
  "targets": ["ball.detect", "pose.sequence"],
  "window": {"start_ms": 60000, "end_ms": 90000},
  "sampling": {"stride": 30, "phase": 0},
  "parameters": {},
  "new_version": true
}
```

```sh
.venv/bin/python scripts/analysis_dev.py plan --request /tmp/local-analysis.json
.venv/bin/python scripts/analysis_dev.py run --request /tmp/local-analysis.json --wait
.venv/bin/python scripts/analysis_dev.py inspect job-替换为返回的ID
.venv/bin/python scripts/analysis_dev.py inspect artifact-替换为返回的ID
```

`plan` 和 `inspect` 只读，不打开视频、不构造模型、不创建持久化目录或修改 schema；缺少准备信息时返回 `preparation_required`。`run` 提交到既有队列，`--wait` 使用同一 Worker 在当前进程执行；没有该参数则由已启动的后端 Worker 领取。成功退出 0，校验错误或失败/取消/中断退出 2。

相同 `engine + plan_hash` 默认去重并返回原 Job。需要检验“新任务复用旧产物”时，使用请求内 `new_version: true` 或参数模式的 `--new-version`；这会创建带 `previousJobId`/`analysisVersion` 的新 Job，仍允许节点缓存命中。CLI 使用 `--request` 时以文件内字段为准。

只重算姿态可把请求的 `parameters` 改为 `{"pose.sequence":{"confidence":0.45}}`。人框和球的配置不变时继续命中各自产物。

双摄分别准备 `cam_1`、`cam_2`，均传 `--require-pts` 和真实硬件 camera ID。请求的 `source_ids` 放两路 ID，`reference_view_id` 设为 `cam_1`，`sync` 放现有 `dual_camera_sync_calibration.v1` 文件的 JSON 内容。Planner 验证参考机位、同步权威和时间域；运行复用 `FrameTimingProvider`/`CanonicalAnalysisClock`，记录每路 frame index、PTS、canonical time 和 `no_new_frame`。双摄不能用名义 FPS 冒充 PTS。

## API 和任务页面

| 方法与路径 | 用途 |
| --- | --- |
| `GET /api/analysis/capabilities` | 静态能力目录，不加载视觉模型 |
| `POST /api/analysis/sources/prepare` | `{"video_id":"已登记视频ID","view_id":"cam_1","camera_id":"174","require_pts":false}`；API 不接受任意文件路径 |
| `POST /api/analysis/models/prepare` | 准备后端配置指定的模型身份 |
| `POST /api/analysis/plans/preview` | 请求体为上述 `AnalysisRequest` |
| `POST /api/analysis/jobs` | 既有提交入口，增加 engine 判别和模块请求 |
| `GET /api/analysis/jobs/{id}/manifest` | 节点和产物清单，失败/取消后也可查看已发布部分 |
| `POST /api/analysis/jobs/{id}/resume` | 显式恢复 failed/interrupted Job 的原冻结计划 |
| `GET /api/analysis/artifacts/{id}` | 受控 Manifest、availability；`?content=true` 读取 payload |

提交示例：

```json
{
  "analysisEngine": "modular_v1",
  "metadata": {
    "fileName": "局部验证", "matchTitle": "局部验证", "venue": "",
    "matchDate": "2026-10-17", "matchFormat": "doubles",
    "cameraAngle": "unknown", "athleteLabel": "", "level": ""
  },
  "modularRequest": {
    "source_ids": ["source-替换为准备返回的ID"],
    "targets": ["ball.detect"],
    "window": {"start_ms": 60000, "end_ms": 90000},
    "sampling": {"stride": 30},
    "new_version": true
  }
}
```

模块推理配置来自冻结的 implementation/parameters/model，不从 legacy 的 `enableModelInference` 等字段推断。也可用既有顶层 `requestNewVersion: true` 创建新版本。任务列表 `/analysis/tasks` 会识别模块任务，结果入口 `/analysis/{id}` 展示清单，不依赖报告 ID。

## 窗口、缓存和状态规则

- 窗口为毫秒半开区间 `[start_ms,end_ms)`。请求窗口、上游所需窗口、计算窗口、来源裁剪后的有效窗口、输出选择分别保存。依赖向上游反向传播；默认累计扩展预算为前后各 2000ms，raw 检测自身不扩展。超预算、空交集、seek 失败明确失败，不回退全片。
- 采样冻结 stride、phase、anchor 和 `window_reset` 初始化。相同步长不同相位不能共用缓存。`sample_time.v1`、`contact_time.v1`、`interval_intersects.v1` 分开表达点、接触和跨界片段的选择规则。
- `plan_hash` 排除随机 ID、创建时间、缓存提示和物理路径。节点缓存使用实际输入内容摘要、消费上下文、模型/实现/schema/taxonomy 版本、窗口和采样。未消费的名册/比分不会使纯图像节点失效。
- 产物先在 attempt 私有 staging 写入，再 finalize；只有 lease 有效的数据库发布事务成功后才可发现。`cache_key` 与不可变 `artifact_id` 分开，损坏重建产生新 ID，旧固定引用不被改写。
- 节点状态、产物 availability、证据 quality、Job 终态/完整性相互独立。合法无候选可缓存；`sufficient` 只表示合同所需证据存在，不代表预测准确。默认 `all_targets`；显式 `best_effort` 才允许任务成功但结果 partial。
- 节点失败可以有限重试；显式恢复重用冻结计划和已发布上游，从失败节点重新执行，不支持节点内 checkpoint。取消、超时、lease 丢失保留部分证据和失败历史。trace v2 记录 node/attempt/cache/window/resource，兼容 v1 固定 event 枚举。
- 共享根默认 `outputs/_artifacts`，可用 `PICKLEBALL_MODULAR_ARTIFACTS_DIR` 指定。血缘与 source pin 覆盖间接上游；删除 Job 不递归删除共享证据。被 pin 的源文件删除会被阻止。v1 保守保留，无自动 GC。

当前每次实际运行都会重新核验强媒体摘要，即使全部命中缓存也要读源文件。约 1GB 单路全缓存验收耗时 10.313s、两路 20.077s；它们的视频打开、模型构造和推理次数均为 0。首次三能力冷启动为 204.916s，主要受 RTMPose 依赖初始化影响；这些是本机样本，不是统一性能保证。

节点之间允许对同一短窗口重新解码。`decoded_frames` 记录应用层 read/grab，`read_frame_ranges` 记录实际请求帧范围；OpenCV 不暴露内部 GOP 预读，明确标为 `internal_not_exposed`。因此不承诺物理解码仅一次或精确测得底层全部预读。

## 增加能力或实现

1. 在 `analysis_capabilities/<domain>/` 放适配器和该领域类型，纯合同不得导入 cv2/torch 或构造模型。先明确输出类型、schema、坐标单位、主体命名空间、时间域及 quality。
2. 在静态 Registry 声明 CapabilitySpec 和 ImplementationSpec。动作分类的 pose-only、RGB-only、多模态算法各自声明实际 InputSpec；Planner 按所选实现展开，不把所有可能输入同时设为必需。
3. 声明参数默认值和校验 schema、消费上下文、前后上下文、选择规则、资源和重试策略。需要米制输出时声明并验证 `CalibrationContext` 的机位/时间/坐标有效域。修改输出含义、算法或分类体系时分别升级 schema、implementation 或 taxonomy，不覆盖历史解释。
4. 有真实模型后才将能力设为 implemented，并在 `analysis_capabilities/runner.py` 的静态工厂表注册懒加载入口；模型资产准备/核验接入 `sources.py`。无模型实现可不声明 `model` 资源。
5. 适配器输出结构化 payload，所有资源 finally 释放，不能在内部调用完整 Pipeline、报告或其他能力模型。跨域通过 ArtifactRef 和严格 ObjectRef/Association 关联，不按最近时间或数组顺序猜主体。观测轨迹、清洗轨迹和事件约束重建分别建类型，避免 DAG 环。
6. 新增合同/最小闭包/缓存失效/窗口/失败测试，再用真实短窗口验证并保存摘要、计数、耗时。生产 Registry 不注册测试 fixture。

已有可参考实现：`players/adapter.py`、`ball/adapter.py`、`pose/adapter.py`。未来类型骨架区分 Swing/Contact/StrokeAttributes/Shot/Landing/Rally/Semantics/Tactics：动作分类与落点可作为 `shot.semantic` 的显式输入；丁克等语义可独立升级而不改写原始姿态或球观测。

## 诊断、回滚和验收

`preparation_required`：先准备来源/模型；`capability_not_implemented`：尚为 planned；`source_revision_mismatch`：同路径内容变化需重新准备；`authoritative_sync_required`：补齐双摄 PTS/同步；`window_budget_exceeded`：缩小上下文或显式调整有限预算；`window_seek_failed`：检查编码/解码定位；`location_unavailable`：挂载原存储位置，勿把离线根当空目录重建；`corrupt`：保留旧引用，通过新任务重建。

回滚新提交：设置 `PICKLEBALL_MODULAR_ANALYSIS_ENABLED=false` 并按通常方式重启服务；已有模块记录、reader 和运行计划保留。对正在运行的任务可调用既有取消接口，等待 Worker 退出或以 interrupted 对账；不要删除 schema、共享根或来源 pin。完整产品仍走 legacy，未来模型和产品迁移分别提出 change。

本期验收记录见 [validation.md](../openspec/changes/analysis-architecture-v1/validation.md)，真实 60–90s 单/双摄记录见 [real-window-validation.json](../openspec/changes/analysis-architecture-v1/evidence/real-window-validation.json)。未做带人工标签的检测/动作/战术准确率评估。
