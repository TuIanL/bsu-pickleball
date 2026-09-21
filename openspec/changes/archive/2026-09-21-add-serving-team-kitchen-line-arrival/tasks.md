## 1. 下游输入契约与计算配置

- [x] 1.1 接入并校验前置 change 交付的 Job-bound `AnalysisRallyContextSnapshot`、identity audit 与 formal binding；缺任何项时稳定返回 unavailable。
- [x] 1.2 定义版本化 `kitchen-arrival-reference.v1`：`arrival_band_m`、`stable_ms`、`arrival_min_detected_support_ms`、`not_arrived_min_coverage_ratio`、`not_arrived_max_gap_ms`、最小样本数与 provenance。

## 2. 厨房线到位率计算与产物

- [x] 2.1 实现 rally-local 厨房线目标解析器，只依据冻结 context 的 Team A/B 端位选择 near/far kitchen line，绝不复用全场 `zone_stats` 推断。
- [x] 2.2 实现以距离、稳定时间和真实 `detected` 支持为依据的状态机，支持 `already_present`、`arrived`、`not_arrived` 与 `excluded`。
- [x] 2.3 实现 not_arrived 的覆盖率、最大缺口及“无不确定跨越到位带”反证门；遮挡或关键空洞不得判为未到位。
- [x] 2.4 生成比赛级/正式 Rally 批次级 `kitchen-arrival.v1`，包含计数、覆盖诊断、input/reference provenance 与 null-valued insufficient 状态。
- [x] 2.5 向 `metric-snapshot.v1` 镜像 metric，写入可审计的 numerator、denominator、sample_count、status、null value 规则及真实 evidence IDs。
- [x] 2.6 注册 artifact 存储/API、任务结果元数据和 TypeScript 类型；覆盖可用、样本不足、前置 context/audit 缺失、关键缺口、already_present 与不适用场景。

## 3. 视频分析页场地控制主卡

- [x] 3.1 在分析客户端实现 `kitchen-arrival.v1` 的独立请求、解析、错误处理和状态映射，不影响视频、同步小地图、位置图或时序图。
- [x] 3.2 实现“发球队 · 网前到位率”四人场地控制卡：按冻结 Team A/B 和 P1–P4 展示比例泳道与分子/分母；明确它是统计对照而非实时站位。
- [x] 3.3 实现 loading、`insufficient_evidence`、not_applicable、unavailable 和 failed 的局部空态；样本不足显示计数和文案而不显示百分比。
- [x] 3.4 将主卡接入 `/analysis/:jobId/vision`；为可用、缺 artifact、数据不足、窄屏及不影响既有可视化添加组件测试。

## 4. 校验、发布与人工核验

- [x] 4.1 执行 calculator、artifact 路由、前端类型/组件和工作区回归测试；前置 context change 的契约测试为必经输入。
- [x] 4.2 使用锁定人工回放样本校准到位带、稳定时间、正证据、缺口、覆盖和最小样本阈值，发布带版本号的 reference 参数。
- [x] 4.3 对代表性双打任务手工验收：已到位、到位、遮挡降级、样本不足、前置上下文缺失和主卡诚实状态。
- [x] 4.4 以 feature flag 先对双打产品入口开放；标记 V1 为 raw serving-rally 描述性指标，不含第三拍机会调整、回跳或技能评分，并保留 artifact/card 停用开关。
