## Why

当前项目已经具备视频上传、标定、球场几何、分析任务和运动分析基础，但仍缺少从球检测结果到可用球轨迹、弹跳事件之间的独立后处理层。迁移 Good-Pickleball 的球候选筛选、轨迹连续性过滤、短缺失处理、轨迹清洗、插值和规则弹跳检测，可以先补齐核心算法能力，再由后续 change 决定何时接入 `AnalysisPipeline` 和前端展示。

## What Changes

- 新增一个独立的球轨迹与弹跳点核心引擎包，用于处理 detector 输出的球候选点。
- 定义 detector-agnostic 的球检测输入协议，不在本 change 中绑定 YOLO、TrackNet 或具体模型权重。
- 新增球候选筛选、ROI gating、轨迹连续性过滤、异常跳变拒绝和短时缺失记录能力。
- 新增轨迹清洗与短缺失线性插值能力，并标记插值点来源。
- 新增基于固定时间窗口的规则弹跳检测能力，第一阶段仅迁移 `trajectory_lag20` 思路，不迁移 classifier 模型。
- 统一球场坐标输出为现有 CourtVision 英尺制坐标，避免引入 Good-Pickleball 的米制 CourtMapper 常量。
- 定义原始球轨迹、清洗球轨迹和弹跳事件的可序列化 schema，并与已预留的 artifact contract 保持兼容。
- 增加单元测试覆盖候选筛选、轨迹过滤、插值、弹跳检测、坐标适配和 artifact 序列化。
- 不接入 `AnalysisPipeline`、不修改分析 API 路由、不生成视频 overlay、小地图、热力图或前端展示。

## Capabilities

### New Capabilities
- `ball-trajectory-and-bounce-engine`: 定义独立球轨迹后处理、清洗插值、英尺制球场坐标适配和规则弹跳事件检测能力。

### Modified Capabilities
- `analysis-artifacts`: 对已预留的球轨迹和弹跳事件 artifact schema 进行最小补充，使新引擎输出字段与 artifact contract 对齐，但不改变当前 pipeline 是否生成这些产物的行为。

## Impact

- 影响后端 vision 层：新增 `backend/app/vision/pickleball_game_analysis/` 下的核心模块。
- 影响后端测试：新增球轨迹、轨迹清洗、弹跳检测、court adapter 和 writer 的单元测试。
- 影响 OpenSpec 能力契约：新增 `ball-trajectory-and-bounce-engine` spec，并对 `analysis-artifacts` 增加字段对齐 delta。
- 不影响当前 `AnalysisPipeline`、`routes_analysis.py`、前端页面或现有真实分析任务默认输出。
- 不新增强制运行时依赖；本 change 的核心逻辑应基于 Python 标准库、NumPy 和项目已有 homography / court geometry 能力。
