## 1. 基线与变更边界

- [ ] 1.1 固定 legacy 单摄/双摄代表性请求、结果、阶段和取消/重试基线，记录已有失败及实际环境。
- [ ] 1.2 核对活跃四人身份 change 的最新状态；在编辑共享 executor/身份文件前固定基线和文件归属，独立合同工作不等待其算法验收。
- [ ] 1.3 确认增量 schema/数据兼容和模块提交开关，列出本期不迁移的产品路径。

## 2. 纯合同与静态 Registry

- [ ] 2.1 创建 analysis_runtime 与 analysis_capabilities 边界，保证合同/Registry import 不加载 cv2、ultralytics 或模型。
- [ ] 2.2 定义 CapabilitySpec、ImplementationSpec、输入替代/可选策略、资源和实现可用状态。
- [ ] 2.3 定义 AnalysisPlan/节点、ContextSnapshot、ArtifactRef/Manifest、ObjectRef/Association 与 ModularRunManifest 类型。
- [ ] 2.4 固定节点状态、availability、quality、完整性和失败策略的独立枚举，验证非法混用被拒绝。
- [ ] 2.5 注册完整能力地图的 planned 条目和三个试点实现，区分能力/实现/schema/taxonomy 版本。
- [ ] 2.6 验证生产 run 在创建 runnable Job 前拒绝未知/未实现能力，测试 fixture 不注册为生产实现。

## 3. 来源与上下文准备

- [ ] 3.1 增加显式来源登记/准备服务，生成强媒体身份与 PTS/同步快照引用，不依赖路径或 mtime 作为内容身份。
- [ ] 3.2 增加受控不可变来源核验及同路径替换失效检查，区分首次身份准备耗时与窗口分析耗时。
- [ ] 3.3 定义消费字段投影及摘要，验证名册/比分变化只影响真正消费它们的合同。
- [ ] 3.4 复用 FrameTimingProvider/CanonicalAnalysisClock，保留每路 source frame、PTS、公共时间及 no_new_frame 状态。
- [ ] 3.5 定义坐标/单位/标定有效域及 observation、local-track、global-player 命名空间，验证跨 view/epoch 不串身份。

## 4. 最小依赖规划与冻结

- [ ] 4.1 实现显式/默认实现选择及有效参数解析，冻结模型摘要和推理开关。
- [ ] 4.2 实现 required/optional/alternative 依赖闭包、固定 ArtifactRef 输入验证和最小 DAG，拒绝循环及 schema 不兼容。
- [ ] 4.3 实现确定性节点 key、canonical JSON 和 semantic plan_hash 白名单，排除随机 ID、时间、缓存提示和输出位置。
- [ ] 4.4 将窗口/采样/消费上下文解析放在缓存提示前；未知上游输出标记 pending_binding。
- [ ] 4.5 实现只读 preview，缺少已准备元数据时返回 preparation_required，验证零 capture、零模型构造、零持久化写入。
- [ ] 4.6 验证 CLI/API 规范化合同一致，缓存变化不改 plan_hash，默认配置变化不改已冻结计划。
- [ ] 4.7 验证 raw ball 最小闭包不含人、姿态、切分、指标或报告，替代动作 fixture 只展开实际输入。

## 5. 有界窗口与输出选择

- [ ] 5.1 复用现有半开时间窗口语义，分开请求、输入/计算、有效范围、模型采样、GOP 预读与输出选择。
- [ ] 5.2 实现消费者向上游的窗口反向传播与合并，中间产物保留所需上下文。
- [ ] 5.3 实现累计有限预算，默认前后各 2000ms；静态超预算入队前拒绝，动态搜索在预算内终止。
- [ ] 5.4 实现明确的 sample_time/contact_time/interval_intersects 选择合同，fixture 验证 41s 开始、43s 接触的跨界动作。
- [ ] 5.5 验证源边界裁剪、缺失成对范围、空交集、seek 失败和有限 GOP 预读，不允许整场 fallback。
- [ ] 5.6 冻结 stride/频率、相位锚点和初始化方式，验证相同 stride 不同相位不复用缓存。

## 6. 不可变产物、缓存和引用存储

- [ ] 6.1 在既有 SQLite 增量创建计划、节点尝试、产物、缓存指针、Job 引用、血缘和来源 pin 表，验证幂等迁移。
- [ ] 6.2 实现受控逻辑定位及 Manifest 内容/schema/摘要校验，大 payload 保留在文件系统。
- [ ] 6.3 实现实际输入级 cache_key，包含窗口/选择/采样/有效配置/消费上下文，不包含 Job 与无关配置。
- [ ] 6.4 分开缓存指针和不可变 artifact_id，验证同键损坏后生产新版本、固定旧引用不被改写。
- [ ] 6.5 实现命中核验及 available/location_unavailable/missing/corrupt 分类，验证 no_candidates 可复用。
- [ ] 6.6 实现跨 Job 引用与间接血缘/来源保留，覆盖任务及源媒体物理删除入口；历史私有目录内被 pin 内容须安全迁移或明确 blocked，防止递归误删。
- [ ] 6.7 提供引用和 orphan 对账/回收资格检查；v1 保守保留，不交付基于直接引用数的自动 GC。

## 7. 模块执行与发布

- [ ] 7.1 实现节点就绪/阻断/可选缺失调度，在实际输入绑定后重新判断缓存。
- [ ] 7.2 实现 all_targets 和 best_effort 目标策略，验证独立成功、可选失败、全部失败和质量不足的不同结论。
- [ ] 7.3 实现 cache miss 后的资源懒加载与 finally 释放，复用现有任务级 CPU/GPU 限制并防止嵌套限流死锁。
- [ ] 7.4 实现 attempt 隔离写入、校验和不可变 finalize，禁止未发布文件被缓存发现。
- [ ] 7.5 实现 lease 保护的 DB 发布事务，原子登记 Manifest/引用/血缘/节点完成/缓存指针。
- [ ] 7.6 故障注入验证 finalize 后 DB 前崩溃、租约丢失迟到发布及同键并发发布。
- [ ] 7.7 实现有限节点重试与原计划恢复，区分 job attempt/node_attempt，保留上游且不要求节点内部 checkpoint。

## 8. 既有 Worker 与结果兼容接入

- [ ] 8.1 增加 analysisEngine 缺省 legacy_v1 和带判别的返回类型，保持历史 Job/结果可读。
- [ ] 8.2 扩展唯一静态 resolve_executor，先分 engine 再分 legacy 类型/模式/角色；Worker 不感知具体能力。
- [ ] 8.3 扩展 is_runnable，使已准备的模块单摄/双摄可领取，不等待 legacy Parent fusion_ready。
- [ ] 8.4 将冻结计划与 queued Job 在既有控制面持久化，重复提交按 engine+plan_hash 去重，新版本保持可追溯。
- [ ] 8.5 为 ModularRunManifest 接入独立发布/完成路径，验证不调用 legacy on_completed、stage_from_pipeline 或报告生成。
- [ ] 8.6 增加 nodeRuns/稳定权重进度，保持 legacy AnalysisStage 与报告顺序；验证总体进度在节点重试时单调。
- [ ] 8.7 接通取消/超时/lease 控制信号与 interrupted 对账/显式恢复，验证部分产物保留及 stale success 不被读取。
- [ ] 8.8 验证 legacy 请求重建传递已持久化有效推理配置；若接入改动暴露配置丢失，只修复配置保真，不调整算法阈值。

## 9. 三个真实能力适配

- [ ] 9.1 适配 player.detect，输出带来源/机位/帧身份的人框，不启动 tracking、标定、球或报告链路。
- [ ] 9.2 适配单摄 ball.detect，输出原始二维候选与时间，不调用事件解析/Shot/3D finish。
- [ ] 9.3 适配正式双摄 ball.detect，使用 canonical clock 与 PTS/同步快照，只运行两路原始检测。
- [ ] 9.4 验证双摄 no_new_frame、reference 失败及显式 secondary 降级策略，不重复送入同一帧或偷用 nominal FPS。
- [ ] 9.5 适配 pose.sequence，从固定/缓存人框和有界 RGB 推理，不依赖球场标定、稳定身份或其他产品能力。
- [ ] 9.6 隔离 RTMPose track_id 可见性状态，框顺序改变不能串人；声明 observation scope 与未完成跨帧关联。
- [ ] 9.7 验证资源构造计数：只球不加载人/姿态，缓存人框不跑 detector，全命中不开视频/模型。
- [ ] 9.8 验证模型缺失、合法无候选和二维单位分别输出稳定诊断/质量，不能用 mock 冒充真实模型成功。

## 10. 关系与未来能力扩展验证

- [ ] 10.1 为未来域补充类型/schema 位置及输入声明，不实现新的球拍/挥拍/语义模型。
- [ ] 10.2 创建 pose-only、RGB-only、多模态 stroke.classify/swing 测试 fixture，验证替代依赖闭包。
- [ ] 10.3 创建 racket.player_association、motion.upper_limb、contact.detect、shot.assemble、context.rally fixture，验证对象引用、机位/主体/时间约束与歧义。
- [ ] 10.4 创建 shot.semantic/tactics.analyze 派生 fixture，验证动作属性、阶段、落点和 taxonomy 分离，升级解释不改源证据。
- [ ] 10.5 验证观测/清洗/事件约束重建类型不会形成执行环，Landing 缺引用时不按最近时间猜配。

## 11. 共用 CLI、API 与 trace

- [ ] 11.1 提供 prepare-source、plan、run、inspect 命令，共用请求/规划/Worker 服务并返回稳定 JSON 与退出码。
- [ ] 11.2 增加 preview、模块提交、Job manifest、ArtifactRef 读取 API，验证 plan_hash 与 CLI 一致及计划预览只读。
- [ ] 11.3 验证新固定路由不会被现有 Literal 动态 artifact 路由吞掉，所有公开引用使用受控入口并脱敏。
- [ ] 11.4 扩展 analysis-run-trace.v2 节点/缓存/绑定/窗口/资源计数，保持 v1 固定 event 枚举与读取兼容。
- [ ] 11.5 验证 retry 前失败证据落盘、节点/Job 汇总不双计、blocked 不伪造异常及取消不抹除 failureEvidence。
- [ ] 11.6 前端最小接入模块 Job 判别、nodeRuns、清单/部分结果和技术详情，避免无 reportId 的任务跳入报告页。

## 12. 集成与真实短窗口验收

- [ ] 12.1 运行合同/控制面/缓存/发布测试，覆盖本 change 的 14 份 delta specs，并记录命令和结果。
- [ ] 12.2 运行受影响的 legacy 单/双摄、prerequisite、历史结果读取与取消/重试回归，对照 1.1 的已有失败。
- [ ] 12.3 使用登记过身份的真实单摄短片验证三能力、无标定执行、实际解码/推理范围与结果可读。
- [ ] 12.4 使用真实双摄短窗口验证 PTS/同步映射与原始球观测，确认未启动整场 segmentation/joint tracking/报告。
- [ ] 12.5 对同窗口重复执行，确认全缓存零 capture/模型；只改姿态参数后人框/球命中、姿态窄重算。
- [ ] 12.6 只改名册/比分验证纯图像缓存不失效，修改权重/采样/消费上下文验证对应分支失效。
- [ ] 12.7 验证失败节点重试/Worker 中断恢复、已发布输入损坏、外接盘离线、Job 删除后间接血缘与源 pin。
- [ ] 12.8 将 fixture/集成/真实推理/质量四类证据分别归档，记录媒体/模型摘要、计划/产物、计数、耗时；缺素材/模型明确未完成，不勾选真实通过。

## 13. 文档、发布和后续边界

- [ ] 13.1 更新开发入口说明、增加新能力/实现示例、窗口/缓存规则与诊断指南，链接完整能力地图。
- [ ] 13.2 更新系统架构文档和 CODEX_HANDOFF，去除过时的固定阶段/测试数量描述，并记录本期仍为 planned 的能力。
- [ ] 13.3 验证关闭模块提交、排空/中断运行并保留新记录/兼容 reader 的回滚步骤，不删除共享证据。
- [ ] 13.4 严格校验 OpenSpec，确认实现任务与验收证据一致；完整产品模块化及各未来模型分别提出后续 change。
