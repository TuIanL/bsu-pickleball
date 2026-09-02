## 1. 数据资产与标注审计

- [x] 1.1 盘点 7-20 视频、CaptureTake、双摄机位和标注文件的实际路径与关联字段
- [x] 1.2 实现视频媒体元数据与完整解码检查，输出视频级诊断
- [x] 1.3 实现人工回合标注的时间单位、范围、重叠和闭合边界检查
- [x] 1.4 复用片段管理工作台实现双摄有效回合边界确认、修正、排除和审计记录
- [x] 1.4a 在同一工作台支持通过共享播放头补录漏记 rally，并保留创建审计
- [x] 1.4b 在边界复核工作台支持按时间修正 rally ordinal（从当前分连续编号/整段视频从 1 开始）并保留审计
- [x] 1.4c 允许选择并修复边界倒置或其他异常的 rally，保留中间草稿状态
- [x] 1.5 完成首轮精确边界抽样复核，统计人工起止误差并确定 uncertain buffer
- [x] 1.6 生成 `match_state_dataset_audit.v1` 报告和第一版不可变数据清单

## 2. 训练标签与视觉样本生成

- [x] 2.1 定义比赛状态 label profile 和 `high_confidence/uncertain/excluded` 标签规则
- [x] 2.2 本地生成不解码视频、可由远程路径映射解析的统一时间基准 RGB clip manifest
- [x] 2.3 在远程服务器对齐并导出四名球员骨架、球检测/球路和质量 mask
- [x] 2.4 校验双摄同步映射、缺失机位降级和 source provenance
- [x] 2.5 完成按整场比赛分组的 train/validation/test 切分与防泄漏检查
- [x] 2.6 建立 RGB/结构化视觉的统一 take-time 对齐缓存，保留缺失 mask 和 provenance
- [x] 2.7 对球候选做跨帧关联并生成速度、方向、停滞和可见性特征
- [x] 2.8 从骨架生成球员速度、加速度、身体活动和队形变化特征
- [x] 2.9 生成 7 场同步资产 manifest，显式绑定 source PTS、camera identity、sync calibration 和 sync revision
- [x] 2.10 实现复用旧同步核心的 offline CanonicalFeatureClock，支持 authoritative/extrapolated/unavailable 门控
- [x] 2.11 基于 v2 canonical-sync 重新生成对齐层和质量校验报告，不重跑 RTMPose/球/场地线提取

## 3. 离线模型与消融实验

- [x] 3.1 建立可复现训练配置、模型包 schema 和本地 CLI
- [x] 3.2 训练 RGB-only baseline（RTX 4090；自然 early stopping，best epoch=15，验证 macro-F1=0.9799，测试 macro-F1=0.9651）
- [x] 3.1a 归档 RGB baseline 权重并建立 strict artifact SHA-256 校验器
- [ ] 3.3 训练骨架/球路输入 baseline
- [ ] 3.4 训练 RGB+骨架+球路融合模型
- [x] 3.5 加入时序平滑、最短持续时间、迟滞和 unknown 降级
- [ ] 3.6 生成状态指标、边界误差和输入方案消融报告
- [x] 3.6a 实现窗口/回合级状态、IoU、边界 MAE、漏检和误检评估器（全量真实 GPU 评估待 4090 卡模式执行）
- [x] 3.7 更新 RGB manifest/loader 使用 canonical sync 映射，保留 v1 nominal-sync baseline 并准备 v2 重训

## 4. 候选时间线与人工闭环

- [ ] 4.1 生成带概率、边界证据和模型 provenance 的候选时间线 artifact
- [ ] 4.2 在现有时间线/标注工作台展示候选并支持接受、修正、拒绝
- [ ] 4.3 将人工修正结果回流为下一版数据集，保留 revision 和审计记录
- [ ] 4.4 增加模型不可用、输入不足和双摄缺失时的安全降级
- [ ] 4.5 完成离线回归测试和默认流程兼容性验证
