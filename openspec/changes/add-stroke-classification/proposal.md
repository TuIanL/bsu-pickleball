## Why

动作分类模型已经在独立仓库训练完成（baseline4 四类，XGBoost Fold-macro 0.606），但主系统里 `stroke.classify` 至今仍是 `analysis_runtime` 的 **planned** 能力，`ShotEvent.stroke_type` 字段存在却从未写入。要在系统里看到"这一拍是什么动作"，目前只能人工在仓库外跑脚本，无法在产品界面复现，也无法对历史分析任务回放。

同时，离线验证已经确认两处一阶落差，必须在模块边界上处理，而不是靠调参：

- **尺度**：系统双摄七场的人体框高中位 216 px（p5–p95 108–396，同帧最大/最小比 2.63），训练素材为 254 px（p5–p95 196–328）。按七场尺度分布扰动后，现成权重的 Macro-F1 从 0.547 掉到 **0.366**，预测一致率仅 55.9%。
- **窗口**：训练集用的是 `clip_extent`（5–81 帧不等），换到相位窗口 `[b,e]` 对冻结权重无收益（−0.004），但重训模型可高 +0.028 —— 说明窗口口径必须在训练与推理两端一致，不能一端改。

因此这个 change 的目标是把"尺度归一 → 挥拍切窗 → 击球人归属 → 分类与弃判 → 产物与读取接口"这条链固化成系统能力，形态是**对已有分析任务的后处理模块**，不改动主分析链路。

## What Changes

- 新增后处理模块：读既有 `pose_overlay.json`，产出 `action_classification.json`，不改动 12 阶段分析状态机
- 新增 `POST /api/analysis/jobs/{id}/action-classification` 触发接口与 `GET` 读取接口
- 新增尺度归一化步骤：推理前按每名球员的 bbox 高度把坐标缩放到训练参考尺度（254 px），并在产物中记录实际缩放因子
- 新增挥拍窗口与击球人归属：输出 `[start_ms, end_ms]` + `hitter`，多人同时挥拍时允许并列候选，不强制单选
- 新增分类与弃判语义：输出类别、置信度与 `evidence_sufficiency`；低于阈值必须输出 `unclassified`，不得强行归入四类
- 新增前端读取入口：在分析详情页提供击球动作区块（或独立页），展示时间、球员、类别、置信度与弃判状态
- 不训练新模型，不引入球轨迹依赖，不改动 `analysis_pipeline.py` 的既有阶段，不新增产品运行时的重型依赖

## Capabilities

### New Capabilities

- `stroke-classification`：把姿态骨架转成逐次挥拍的动作类别事实，包括尺度归一、挥拍窗口与击球人归属、分类与弃判、产物与读取接口

### Modified Capabilities

- 无。本 change 只新增行为，不修改任何既有 capability 的需求。`action-classification-preprocessing` 管训练侧数据导出、`swing-skeleton-export` 管离线 CLI，`pose-estimation-engine` 提供 `pose_overlay.json`，三者均按既有契约复用，不做 delta。

## Impact

- 代码：
  - 新增 `backend/app/vision/stroke_classification/`（窗口、尺度、特征、推理）
  - 新增 `backend/app/services/stroke_classification_service.py`
  - 修改 `backend/app/api/routes_analysis.py`（新增触发与读取端点）
  - 新增 `backend/app/schemas/stroke_classification.py`（产物 schema，复用 `analysis_runtime.contracts.StrokeAttributes` 的语义）
  - 前端新增读取入口与路由（`/analysis/:jobId/actions` 或详情页区块）
- API：新增两个端点，均为幂等读取/计算型，不改变既有端点行为
- 依赖：不引入 `xgboost` 到产品运行时；模型权重以冻结的树结构导出，用纯 numpy 求值（设计与等价性验证见 design.md）
- 存储：产物落在既有 job artifact 目录，沿用 `StorageService` 的路径约定与外接盘分支
- 口径影响：产物必须显式携带 `model_version`、`scale_reference_px`、`window_policy`、`abstain_threshold`，使任何一次输出都可追溯到具体的推理配置
