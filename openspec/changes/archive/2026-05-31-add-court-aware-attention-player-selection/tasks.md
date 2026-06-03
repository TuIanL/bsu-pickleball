## 1. Selector 数据与诊断基础

- [x] 1.1 定义候选 tracklet 聚合数据结构，覆盖 bbox、confidence、image footpoint、court position、速度、出现帧数和目标场几何特征
- [x] 1.2 定义主球员选择诊断 schema，记录 selection mode、fallback reason、目标球场归属分、tracklet 质量分、四人组分和排除原因
- [x] 1.3 为分析流水线增加 selector 配置项，包括 participant count、窗口长度、规则阈值、attention 启用开关和模型权重路径

## 2. 规则增强 Court-Aware Selector

- [x] 2.1 实现窗口级 tracklet 聚合，从 projected positions 和 tracks 构建候选摘要
- [x] 2.2 实现 `target_court_score`，结合目标场容差内占比、polygon 距离统计、投影有效性和短暂越界容忍
- [x] 2.3 实现 `tracklet_quality_score`，结合检测置信度、持续帧数、轨迹连续性、bbox 合理性和投影稳定性
- [x] 2.4 实现 `group_consistency_score`，优先选择符合目标场双打空间分布的最多四名候选
- [x] 2.5 将规则增强 selector 接入 overlay subject selection，并保留现有输出兼容字段

## 3. Identity 与 Pipeline 集成

- [x] 3.1 将 selector 输出的 eligible track IDs 和诊断传递给 `PlayerIdentityManager`
- [x] 3.2 更新身份分配逻辑，使非目标场候选不会创建或更新最终 `Player_1..4`
- [x] 3.3 更新分析 artifact 写出逻辑，持久化主球员选择诊断和 fallback 状态
- [x] 3.4 确保 metrics 消费稳定 `player_id` 轨迹时只使用目标场 eligible samples

## 4. Attention 模型接口与样本导出

- [x] 4.1 新增可选 self-attention selector adapter，定义输入 tensor/feature schema 和输出概率语义
- [x] 4.2 实现模型加载与 fallback：权重缺失、依赖不可用、推理异常或低置信度时回退规则增强 selector
- [x] 4.3 新增训练样本导出 artifact，包含候选时间窗口、几何/运动特征、规则分数和标注占位字段
- [x] 4.4 提供最小 PyTorch 模型骨架和训练脚本入口，用于后续标注数据训练，不作为默认运行依赖

## 5. 测试与验证

- [x] 5.1 添加规则 selector 单元测试，覆盖目标场四人、隔壁场运动员、短暂越界、遮挡缺员和候选超过四人的场景
- [x] 5.2 更新 `PlayerIdentityManager` 测试，验证非目标场 track 不会绑定到最终 player identity
- [x] 5.3 添加 pipeline 集成测试，验证 attention 不可用时自动回退且任务仍完成
- [x] 5.4 更新 QA 文档，加入隔壁场 hard negative 复核清单和训练样本标注说明
