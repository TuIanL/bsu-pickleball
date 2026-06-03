## Why

当前双打球员锁定在多人同场景视频中仍容易把隔壁球场正在运动的球员纳入目标场四人，因为现有主球员选择更多依赖单个 track 的置信度、框质量、持久性和宽松场地范围。拍摄素材里隔壁场球员也会持续运动并保持高置信度，因此需要把“目标球场归属”和“四人组关系”作为一等能力。

## What Changes

- 新增目标球场感知的候选 tracklet 评分能力，基于手动/自动标定的目标场 homography、脚点投影、目标场 polygon 距离、时间窗口内场地占用比例和双打阵型一致性判断候选是否属于目标场。
- 增强主球员选择逻辑，从逐帧独立选前四个 track 转向窗口级 tracklet 排序和四人组选择，减少隔壁场运动员、场边路人和错误投影人员进入 overlay 与下游身份轨迹。
- 新增可选 self-attention player selector 的数据接口、推理降级策略和训练样本导出约定；没有训练权重时使用规则增强 selector，有权重时使用 attention selector，并在低置信度或不可用时回退。
- 扩展诊断输出，记录候选被保留或排除的原因，包括目标场归属分、四人组分、attention 置信度、回退路径和 hard negative 类型。
- 不移除现有 YOLO、tracker、footpoint projection、player identity contract；本 change 在既有管线中增加一层目标场选择和可学习模型接口。

## Capabilities

### New Capabilities

- `court-aware-attention-player-selection`: 定义目标球场感知的四人锁定、规则增强 selector、可选 self-attention selector、训练样本导出和诊断要求。

### Modified Capabilities

- `player-tracking-engine`: 主球员 overlay 选择需要从单帧 track 质量扩展为目标球场感知、窗口级候选选择，并保留现有 tracker/projection 接口兼容性。
- `player-trajectory-identity`: 稳定身份分配需要消费目标球场候选资格和 attention/规则分数，避免把隔壁场 track 绑定到最终四名 `player_id`。

## Impact

- 后端视觉模块：`backend/app/vision/player_tracking_engine/primary_player_selector.py`、`player_identity.py`、`player_projector.py` 及相关 schema/test。
- 分析流水线：`backend/app/services/analysis_pipeline.py` 需要在 projection、overlay、identity 之间传递目标场候选分、选择诊断和可选模型状态。
- 模型与数据：新增可选 PyTorch 模型文件位置、训练样本 JSON/CSV artifact、模型不可用时的 fallback 状态；不要求首个实现必须完成训练。
- 前端与 artifact：tracking overlay、player trajectory diagnostics、分析详情页可展示更清楚的“为什么这个人被排除/保留”的调试信息。
