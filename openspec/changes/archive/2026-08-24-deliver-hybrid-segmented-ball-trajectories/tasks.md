## 1. 时间语义与现有重建缺陷修复

- [x] 1.1 为球 tracker 和击球检测配置增加 effective FPS、frame stride 与基于秒的连续性阈值
- [x] 1.2 将 `BallContactEventDetector` 的固定相邻帧差判断改为 timestamp/stride-aware 判断
- [x] 1.3 将击球 refractory period、上下文窗口和长缺失诊断统一为真实时间语义
- [x] 1.4 修复 `single_anchor_warp`，分别正确处理起点锚点和终点锚点
- [x] 1.5 增加 stride 1/2、起点单锚点、终点单锚点和未知端渐隐的单元测试
- [x] 1.6 使用历史 `job-96a28d6ff0` 清洗轨迹建立回归测试，验证 stride=2 不再产生零击球候选

## 2. 球候选时序质量提升

- [x] 2.1 抽取 detector 单次输出后的基础候选过滤器，使 tracker 与 stereo associator 消费同一过滤集合
- [x] 2.2 在基础过滤中接入场地 ROI、bbox 尺度/长宽比、静态位置黑名单和结构化拒绝原因
- [x] 2.3 为 tracker 增加多帧尺度变化、预测方向、速度与短缺口一致性评分
- [x] 2.4 保证短缺口样本标记 predicted，且不进入权威 bounce、landing、speed 或 peak-height 证据
- [x] 2.5 输出逐帧候选、最终选择、静态误检与物理门诊断，并增加确定性测试
- [x] 2.6 增加静态广告牌误检、高速模糊球、遮挡重捕获和多个同类候选的回归用例

## 3. 事件切段与场外证据分类

- [x] 3.1 在 canonical joint 球链中复用 `BallEventResolver` 与 `BallFlightSegmenter`
- [x] 3.2 将 hit、bounce、serve reset、长丢失和 end-of-stream 映射到 canonical 时间轴的 segment 边界
- [x] 3.3 禁止 `finish()` 将完整分析窗口组装为唯一 `seg_canonical_1`，改为逐 segment 输出
- [x] 3.4 定义标准球场边线、可配置比赛环境边界与标定不确定度数据结构
- [x] 3.5 实现 `in_court`、`legal_out_candidate`、`calibration_uncertain`、`environment_outlier` 分类器
- [x] 3.6 结合轨迹连续性、静态/跳变、回投残差和跨视角支持决定环境离群拒绝
- [x] 3.7 增加真实界外球、底线外发球、轻微标定偏差和观众席静态误检测试，验证场外点不会仅凭越线被删除

## 4. 段级主视角与稀疏双摄关联

- [x] 4.1 为每个视角按 segment 计算覆盖率、连续性、检测置信度、拟合残差、预测比例和静态误检比例
- [x] 4.2 实现确定性的段级主视角评分与滞回规则，并记录选择理由
- [x] 4.3 从 tracker 暴露只读 pre-tick 预测与连续性快照，不允许 stereo 反向修改 tracker 状态
- [x] 4.4 将 tracker 连续性、上一可信 3D 路径连续性、尺度/方向一致性传入 `associate_views`
- [x] 4.5 为高回投/epipolar 残差配对增加低质量标记，禁止其成为高可信 stereo anchor
- [x] 4.6 在 stereo evidence 中为 observation、pairing 和 measurement 增加 `segment_id` 与质量分量
- [x] 4.7 增加主摄切换、稀疏重叠、静态误配和异步真实 timestamp 的关联测试

## 5. 混合 2.5D/3D 重建与质量资格

- [x] 5.1 定义并序列化 `stereo_estimated_3d`、`stereo_anchored_2_5d`、`single_view_event_anchored_2_5d`、`single_view_visual_arc` 和 `unavailable`
- [x] 5.2 将段级 B-spline 优化改为只消费同一 `FlightSegment` 内的双摄和单摄观测
- [x] 5.3 使用合格 stereo measurement 作为稀疏初始化/锚点，并在各摄像机真实观测时刻计算回投损失
- [x] 5.4 为单摄段接入鲁棒 image-space 拟合、pseudo court path 和事件端点感知二次高度弧
- [x] 5.5 对 hit、bounce、loss/unknown 分别执行接触高度先验、地面硬锚和未知端渐隐
- [x] 5.6 为每段计算 display level、metric validity、speed/height/landing eligibility 与结构化 reason
- [x] 5.7 验证 3D 不合格段不会阻断同任务其他 3D 段或合格 2.5D 段发布
- [x] 5.8 增加跨多拍不连线、短缺口虚线、事件端点高度和确定性重建测试

## 6. Artifact、Composer 与 API

- [x] 6.1 扩展重建 schema，保存任务 3D overall status、`display_trajectory_status` 和逐段 reconstruction mode
- [x] 6.2 为 sample 保存 source view、detected/interpolated/predicted/stereo-anchor provenance、置信度和 validity
- [x] 6.3 为 endpoint 保存 hit/bounce/loss 语义、标准场地位置、环境分类、标定不确定度和非判罚声明
- [x] 6.4 在 result composer 中发布混合轨迹 artifact，并使球失败继续与球员结果隔离
- [x] 6.5 保持统一 `reconstructed-ball-trajectory` API slug，并兼容历史 v1/v2/v3 读取
- [x] 6.6 确保已完成任务 evidence 不被回写，重跑生成新 job 范围的版本化 artifact
- [x] 6.7 增加 schema、API、历史兼容和不可变性测试

## 7. 视频、球路页与报告呈现

- [x] 7.1 更新前端类型与 adapter，按 schema version、segment mode 和 metric eligibility 解析混合产物
- [x] 7.2 移除“只要存在 v3 状态就永不展示 2.5D”的整页阻断逻辑，改用 `display_trajectory_status`
- [x] 7.3 在视频分析图层中按当前机位 image-space 轨迹和播放时间绘制当前 segment 尾迹
- [x] 7.4 为 detected、interpolated、predicted 区间实现实线、过渡线和虚线编码，并在段结束后短暂保留轨迹
- [x] 7.5 在球路页展示混合段、动态视角、击球菱形、弹地圆环、未知端渐隐和来源说明
- [x] 7.6 在球路报告中复用同一 segment artifact，显示简化弧线与端点标记
- [x] 7.7 对 `legal_out_candidate` 在边线外真实位置显示“可能界外落点，非自动判罚”，不得吸附回场内
- [x] 7.8 对 `environment_outlier` 仅在诊断视图显示原始证据和拒绝原因，不进入正式报告曲线
- [x] 7.9 为估算 2.5D 持续显示 visualization-only 提示，并隐藏无资格速度、最高点和权威落点
- [x] 7.10 增加视频时间同步、页面降级、WebGL 轨迹、报告一致性和无证据空态测试

## 8. 真实样本验收与发布

- [x] 8.1 建立包含当前双摄样本、真实界外球、遮挡、静态误检和不同 stride 的固定回归数据集
- [x] 8.2 输出旧 canonical v3 与新 hybrid 结果的段数、双摄锚点、残差、预测比例和事件对比报告
- [x] 8.3 人工抽检视频尾迹与报告弧线，确认不跨击球/弹地连接且端点时间一致
- [x] 8.4 验证当前 60 秒样本在真实 3D 仍不可用时至少能发布通过门槛的估算分段球路
- [x] 8.5 验证真实界外落点保留、环境离群误检排除、标定不确定点降级三种结果
- [x] 8.6 增加 feature flag 和旧读取路径回滚测试，在新链路异常时保留历史任务与球员分析
- [x] 8.7 运行后端/前端相关测试、类型检查和生产构建，并记录最终验收指标
