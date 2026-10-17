## Context

当前代码基线为 2665bc3b974656cec45cd54e875d03cd3a8994c6。本设计综合 Downloads 中的原始 analysis-architecture-v1 包、此前建议和本地代码检查，替代原包中的不完整约束；不把附件中的“立即 apply”等措辞当作用户指令。

用户需要持续增加球、球拍、挥拍、动作分类和击球语义，同时能够用单摄或双摄的几十秒窗口验证单个能力。当前主要障碍是计算、产品编排和产物归属共用一条路径：

- AnalysisPipeline.run() 包含输入/标定检查、人员、球、姿态、后处理和结果组装；共享帧循环使独立验证困难。现有部分模型已懒加载，问题还包括无关前置条件和完成回调。
- SingleViewAnalysisExecutor 重建请求；当前存在已持久化推理开关未完整传递的风险。新路径必须冻结有效配置，并将旧路径的配置保真作为兼容检查。
- Worker 的返回类型、整体重试、成功回调和阶段重建绑定 AnalysisPipelineResult；只新增目录不能解除这些约束。
- 双摄 joint 已消费窗口与 canonical clock，但正式 segmentation prerequisite 仍可能从 0 扫完整 take；模块局部验证必须完全避开这个无关前置任务。
- SQLite 控制面已负责跨进程队列、lease、heartbeat、取消和中断，应继续复用。
- 现有产物字段和 Job 目录适合产品结果读取，不能直接用作跨 Job 不可变证据仓库；删除任务还涉及源文件生命周期。
- 现有事件与重建并非简单“3D 轨迹先于所有事件”：球路 finish 先解析事件、分段，再进行事件约束重建。
- action_classification_preprocessing 是数据准备，export_swing_skeleton 是独立骨架导出，均不等于完整挥拍或动作分类器。

受影响的主要使用者是开发者、研究验证人员、现有产品用户和维护 Worker 的开发者。完整产品路径的稳定性与开发验证速度同时作为约束。详细代码证据见 RESEARCH_AND_AUDIT.md。

## Goals / Non-Goals

**Goals:**

1. 定义完整的能力、实现、产物、上下文、关系与计划骨架，后续功能通过声明依赖和新增适配器接入。
2. 用共用入口完成单摄/双摄局部 plan/run/inspect，能解释实际执行、缓存和窗口扩展。
3. 支持输入级缓存、窄重算、已发布节点恢复和跨 Job 证据保留。
4. 真实接入 player.detect、ball.detect、pose.sequence，证明结构能够离开完整 Pipeline 独立运行。
5. 显式修改旧 Executor、编排与 trace 规格，使新增路径有合法执行合同。

**Non-Goals:**

本期不完成球拍模型、稳定人拍关联、完整挥拍、动作分类、丁克球等语义模型；不迁移完整 Shot/Rally/指标/报告；不改变身份门槛或现有算法阈值；不拆开 joint 内部状态机；不建立动态插件、第二套队列、分布式调度或节点内部 checkpoint；不承诺所有能力只解码一次。未来能力须有明确位置和类型，真实模型交付留给后续 change。

## Decisions

### D1. 将模块运行加入既有控制面

引入 analysisEngine=legacy_v1 | modular_v1，缺省为 legacy_v1。analysisKind 继续表示单摄/多视角的来源模式，不承担“模块类型”含义。

~~~text
CLI / API
    -> 同一 Registry + Planner
    -> 冻结 AnalysisPlan + AnalysisJob（既有 SQLite 控制面）
    -> Worker / lease / heartbeat / cancellation
    -> resolve_executor
         legacy_v1 -> 现有 single / multi / prerequisite / joint -> 产品结果
         modular_v1 -> ModularAnalysisExecutor -> 节点产物 + 运行清单
~~~

Protocol 返回带 engine/resultKind 判别的 AnalysisPipelineResult 或 ModularRunManifest。Worker 根据结果合同选择发布器；模块路径不经过 legacy on_completed、stage_from_pipeline 或 metrics/insights/report 组装。Worker 的队列、优先级和任务级资源上限复用，节点资源不能再次争用同一不可重入锁导致死锁。

考虑过直接给 AnalysisPipeline 增加开关：仍会继承标定/切分/回调/阶段假设。考虑过独立脚本执行器：会造成 API、CLI 和 Worker 三条语义。采用共享控制面与并行 engine 边界。

### D2. 能力地图覆盖完整分析域

CapabilitySpec 表示做什么，ImplementationSpec 表示算法如何做，Artifact schema 表示数据结构，taxonomy 表示标签含义。四者独立版本化。Registry 静态注册，只装载元信息，不构造模型。

| 域 | 能力 ID | v1 状态与输出边界 |
| --- | --- | --- |
| 球员观测 | player.detect | implemented；每帧人框，observation-scoped |
| 球员状态 | player.track、player.identity | planned；view-local track / global identity 分开 |
| 球观测 | ball.detect | implemented；每机位原始二维候选与时间 |
| 球路 | ball.track_2d、ball.clean_2d、ball.events、ball.reconstruct_3d | planned；原始、清洗、事件约束重建分别定型 |
| 球拍 | racket.detect、racket.track、racket.player_association | planned；检测/跟踪/主体关联独立 |
| 姿态 | pose.sequence、pose.associate | 首项 implemented；姿态观测与跨帧主体关联分开 |
| 运动证据 | motion.upper_limb | planned；坐标和单位明确的派生证据 |
| 挥拍与接触 | swing.segment、contact.detect | planned；阶段区间、接触候选及关联 |
| 动作属性 | stroke.classify | planned；pose-only、RGB-only、多模态实现可选 |
| Shot/Rally | shot.assemble、shot.landing、context.rally | planned；严格事件引用及版本化上下文 |
| 击球语义 | shot.semantic | planned；融合动作、球路、落点、球场、回合证据 |
| 战术与评价 | tactics.analyze、evaluation.quality、metrics.compute | planned；派生解释、质量与指标 |
| 产品组合 | 明确版本的完整分析组合计划 | 后续 change；v1 完整产品继续 legacy |

planned 不因现有 legacy 内部有部分算法就自动成为 modular implemented。生产 run 请求没有可执行实现时，在创建可运行 Job 前返回 capability_not_implemented；preview 可展示缺项。测试 fixture 使用独立测试注册，不出现在生产可执行列表。

ImplementationSpec 至少声明：capability/implementation 版本，输入类型/schema，required/optional/alternative 绑定，有效参数，模型内容摘要，消费上下文投影，窗口策略，输出类型/选择规则，CPU/GPU/解码需求和有限重试策略。

不采用一个“万能动作节点”强制依赖所有模态。不同实现只需要其实际声明的证据；例如 pose-only stroke.classify 不应加载球拍模型。

### D3. 六类核心合同

| 对象 | 职责 | 不承担的职责 |
| --- | --- | --- |
| CapabilitySpec / ImplementationSpec | 静态能力、实现及输入输出声明 | 不保存运行状态 |
| AnalysisPlan | 冻结的计算合同与 DAG | 不以动态 cache hit 决定身份 |
| ArtifactRef / ArtifactManifest | 引用与不可变证据元数据 | 不以 Job 作为内容身份 |
| ContextSnapshot | 冻结来源/时间/空间/身份事实 | 不把所有字段强制注入每个节点 |
| Association / ObjectRef | 版本化证据关系和歧义 | 不制造执行环或反写源证据 |
| RuntimeResource | capture、模型、clock、临时句柄 | 不作为可跨进程复用的持久产物 |

ArtifactRef 是轻量的 artifact_id、type、schema_version 引用；Manifest 保存详细 provenance。使用某个产物的 Job 通过 job_artifact_refs 绑定 role、node_id、is_target。created_by_job_id 仅用于追溯生产者。

大型 JSONL/数组放文件系统，SQLite 保存 manifest 与索引，不把视频/RGB 塞进数据库。v1 精确匹配窗口/采样缓存；更大窗口的自动裁切复用不是必交付。未来支持时必须显式产生 selection binding 或新派生产物。

建议代码边界如下；未来域先放合同/目录说明，不为尚未实现的模型生成空执行器：

~~~text
backend/app/analysis_runtime/
  contracts/          # plan、artifact、context、association、result
  registry.py         # 纯元信息与静态实现选择
  planner.py          # 依赖、窗口、采样、合同冻结
  artifact_store.py   # Manifest、缓存指针、血缘与来源 pin
  executor.py         # 节点调度、重试、控制信号
  publisher.py        # 文件校验/finalize 与 lease 保护发布
  resources.py        # capture、模型、clock 的按需生命周期
backend/app/analysis_capabilities/
  players/  ball/  pose/       # 三个真实适配器
  catalog/                    # racket、motion、swing、contact、stroke、
                              # shot、rally、semantic、tactics、evaluation 合同
backend/app/vision/             # 保留现有算法实现
backend/scripts/analysis_dev.py # 共用服务的开发入口
~~~

依赖方向是 API/CLI -> runtime -> adapter -> vision。纯合同/Registry 不 import 视觉运行时，适配器工厂在真正执行时再加载算法；vision 不反向依赖 Worker 或产品报告。

### D4. 规划顺序、冻结与稳定指纹

规划分成无副作用的预览和提交冻结：

1. 校验请求与已准备的媒体/模型元数据；强身份或 PTS 缺失时返回待准备项。
2. 选择显式实现或已解析默认实现，展开最小依赖闭包，验证固定 ArtifactRef、替代方案和 DAG。
3. 从目标向上游传播输入窗口/输出选择，合并同一节点需求并校验有限扩展预算。
4. 冻结来源、消费上下文、有效参数、模型摘要、采样/初始化、资源和失败策略。
5. 计算 semantic plan_hash，随后生成独立 cache_hints。未知实际上游的提示为 pending_binding。
6. run 复用同一规划逻辑，在控制面事务中写入计划与 queued Job；Worker 不重新选择默认实现。
7. 节点运行前，解析实际上游绑定并核验缓存。预览命中不能免除这一步。

plan_hash = SHA-256(canonical_json(semantic_contract))。白名单包含 engine/合同版本、目标与选择规则、确定性 node key、实现/schema/taxonomy 版本、有效模型/参数、媒体/采样/窗口、消费上下文投影、依赖/可选绑定策略、固定输入身份、资源/失败策略。排除随机 plan_id/job_id、created_at、输出路径、plan_hash 本身、运行状态、缓存提示和非消费快照字段。

规范化要求默认值已展开，集合稳定排序，时间使用整数单位，禁止 NaN 和不稳定浮点表示。节点 key 从计算声明确定，不使用随机执行 ID。可选证据启用策略冻结；实际可用/缺失、实际消费引用在执行绑定中记录，进入最终节点缓存身份，不修改原计划。

示意合同，字段以实现期类型定义为准：

~~~json
{
  "schema_version": "analysis-plan.v1",
  "analysis_engine": "modular_v1",
  "plan_id": "随机运行标识，不进入指纹",
  "plan_hash": "规范化合同摘要",
  "source": {"media_revision": "内容身份", "time_snapshot": "PTS/同步身份"},
  "requested_window": {"start_ms": 42000, "end_ms": 72000},
  "context_budget": {"before_ms": 2000, "after_ms": 2000},
  "targets": [{"node_key": "ball-node", "selector": "sample_time.v1"}],
  "failure_policy": "all_targets",
  "nodes": [{
    "node_key": "ball-node",
    "capability_id": "ball.detect",
    "implementation_id": "已冻结实现",
    "implementation_version": "已冻结版本",
    "compute_window": {"start_ms": 42000, "end_ms": 72000},
    "sampling": {"mode": "source_stride", "stride": 2, "anchor": "source_frame_0"},
    "inputs": [],
    "consumed_context": ["media", "frame_time"]
  }]
}
~~~

拒绝“先查缓存再定窗口”与“把随机 plan_id 纳入 hash”，否则相同请求无法稳定复用，或者会错用不同范围产物。

### D5. 局部窗口、上下文与输出选择

窗口均为半开区间。分别记录 requested_window、required_input/compute_window、source-clamped effective_window、model sample range、GOP pre-read range 和 output selector。

- 原始 ball.detect、player.detect 不默认继承 legacy 的 1500/500ms 预热；无上下文需求时计算窗口等于请求与源有效范围的交集。
- 有状态算法的预热/后看必须声明，参与缓存身份；局部重启状态与整场历史状态不保证数值相同。
- 由消费者向上游传播上下文，并将中间产物输出范围保留至消费者真正需要的证据范围，不能先裁成用户窗口。
- v1 默认扩展预算前后各 2000ms。预算约束从用户窗口算起的累计扩展，禁止每层各自再加 2 秒无限累积。用户显式提高预算可得到不同计划。
- 静态必需范围超预算：window_budget_exceeded，入队前拒绝。动态事件边界搜索到预算就停止，按契约给出 truncated/insufficient_evidence。
- 边界部分越界记录裁剪与上下文缺口；无有效交集、缺少成对范围、逆序或 seek 不满足合同均显式错误。
- GOP 预读受有限定位策略控制、单独计数；不能把范围外帧交给未声明需要它的模型。定位失败不从头跑完整视频。

样本按 sample_time 选取；挥拍可按 contact_time 选取；Rally 可按 interval_intersects 选取。选择规则须版本化，记录实际事件起止。41s 开始、43s 接触的挥拍，在 42s–72s 的 contact_time 规则中应保留；不将其开始伪改成 42s。此例用 fixture 验证，不能宣称本期已有挥拍算法。

### D6. 来源、时间、空间与主体上下文

新媒体登记/显式准备操作生成强内容摘要或可核验不可变版本，以及 PTS sidecar 摘要；旧 VideoMetadata 缺这些字段，不能只用路径/mtime 直接信任。首次准备可能读取整份文件做哈希，这是一次来源身份准备，不是全链路分析；后续按受控不可变存储复用。外部可变源在运行前必须核验或重新登记。

preview 只读准备结果，不打开视频、不加载模型、不写文件/数据库；缺项返回 preparation_required。正式 run 使用相同合同，不在推理阶段静默补猜 PTS。API 与 CLI 都通过显式媒体准备服务复用登记结果。

双摄用现有 FrameTimingProvider、CanonicalAnalysisClock 和 sync mapping。观测保留 view_id/source_frame_index/source_pts/canonical_time/map_status。no_new_frame 不重复送入有状态模型；原始观测可以记录该 tick 无新样本。reference 永久失败是节点失败；secondary 缺帧/降级策略由所选实现明确声明并记入计划/质量，禁止暗中切换实现。

主体分别使用 detection observation、view-local track、global player 命名空间；local_id 附来源、view 与 epoch。原始姿态适配以 observation 为主体，不假装已完成跨帧追踪。RTMPose26 的 track_id 可见性历史必须关闭或用 observation key 隔离，避免框序号改变造成状态串人。后续 pose.associate/玩家身份能力提供稳定关联。

image_px、normalized_image、court_m、world_3d 明确区分。标定只约束消费它的换算/融合节点；原始观测不依赖球场标定或名册。消费的快照字段形成投影摘要；不消费 roster/score 的图像检测不因比分变化失效。二维运动证据只声明像素及像素/秒，不能输出无依据的生物力学量。

### D7. 缓存、不可变版本与血缘

cache_key = SHA-256(实现与输出合同 + 来源/机位 + 窗口/输出选择 + 采样/初始化 + 有效参数/模型 + 实际输入内容身份 + 消费上下文投影)。

具体 ArtifactRef 的固定绑定保留 artifact_id 与内容摘要；普通依赖按实际物理内容身份和选择合同生成键，并在 Manifest 记录真实输入引用。重建得到内容不同时消费者必失效；内容相同也须重新核验实际引用。节点缓存判断在输入可用后发生，不拿上游预期计算键代替实际输入内容。

content_sha256 表示完整性，cache_key 表示计算身份。质量 no_candidates 是合法完成结果，可复用。缓存读取校验发布状态、schema、输入绑定、物理完整性和位置可读性。location_unavailable、missing、corrupt 分开，均不能冒充 hit。原位置离线可按显式策略重算至批准位置或报错，不能静默改道。

最小新增索引：

| 表 | 核心内容 |
| --- | --- |
| analysis_plans | plan_id、plan_hash、不可变合同、来源/上下文引用 |
| analysis_node_attempts | job_id、node_key、job_attempt、node_attempt、状态/实际绑定/诊断 |
| analysis_artifacts | artifact_id 主键、cache_key 非唯一、Manifest、内容/位置/发布信息 |
| analysis_cache_entries | cache_key 主键、current_artifact_id、版本/更新条件 |
| analysis_job_artifact_refs | Job 使用绑定及目标/输入角色 |
| analysis_artifact_edges | consumer_artifact_id -> input_artifact_id 血缘 |
| analysis_source_refs | 计划/产物/活动运行对媒体与快照的 pin |

同键可有多个不可变产物，单独缓存指针决定当前可用版本。A 损坏后重算 B，旧 artifact_id/引用保持，不通过覆盖 A 修复历史。并发计算允许重复工作，事务 CAS 选择可用指针；不要求 v1 建立跨 Job 的复杂计算锁。

默认共享存储可在 capture 会话的 analysis/_artifacts/<artifact_id>/ 或本地 outputs/_artifacts/<artifact_id>/；locator 以 storage_id 与相对键表示。staging 位于同卷受控暂存区，确保 finalize 不依赖跨卷 rename。Job 私有清单/trace 继续位于其授权 Job 根。所有根由既有存储索引/配置解析，不能根据客户端路径猜测；位置策略不参与计算身份。

Job 删除只解绑其直接引用。仍被下游血缘、其他 Job、固定输入或活动运行使用的产物/媒体不能删。v1 默认保守保留，提供检查与显式回收资格判断，自动 GC 后置。保留成本优于损失研究证据。trace 为 Job 私有文件，随 Job 清理；共享计算 Artifact 不随 Job 根目录递归删除。若历史私有目录含仍被 pin 的源或证据，先安全迁移并原子更新 locator；无法安全迁移则明确 blocked，不能先递归删除再修补引用。

所有可能物理删除已登记源的入口都需检查 pin；显式删除整条录制/上传源时如仍有存活依赖，返回引用阻断原因或走已有明确级联策略，不能绕过证据保留规则。

### D8. 运行资源、节点边界与多视角协同

v1 节点间采用持久化产物边界。player.detect 发布人框，pose.sequence 读取人框并在相同有界范围取得 RGB；缓存人框时不再跑 detector，但姿态可能重新解码。一个 Job 可在顺序节点间安全复用兼容模型句柄，但不能以此改变独立输入/发布合同；全缓存必须零 capture、零模型构造/执行。

RuntimeResource 工厂在实际 cache miss 后调用，finally 释放 capture/模型会话/临时文件；模型的重试状态不能沿用失败实例的隐含历史。不持久化整片 RGB 帧。

未来可引入显式 streaming execution group，定义扇出、背压、窗口、失败/重放和发布边界后再减少重复解码。本期不使用模糊“共享流”承诺单遍执行；先取得可审计、可恢复的窄重算。

现有 joint 内部两路跟踪、global state、barrier 和 ball 协同维持不透明边界。新双摄 ball.detect 使用 canonical clock 做原始二维观测，不启动 joint 人员跟踪，也不声称替代现有权威三维链路。

### D9. 执行状态与 Job 成功策略

| 维度 | v1 值/规则 |
| --- | --- |
| Job canonicalStatus | queued、running、succeeded、failed、canceled、interrupted |
| 节点状态 | pending、running、cached、completed、failed、blocked、canceled、skipped |
| Artifact availability | available、location_unavailable、missing、corrupt |
| Artifact quality | sufficient、insufficient_evidence、truncated、no_candidates，按类型细化 |
| 运行完整性 | complete、partial、none |
| 默认失败策略 | all_targets；全部请求目标 completed/cached 才成功 |
| 可选失败策略 | best_effort；至少一个请求目标完成才可 succeeded+partial |

可选证据失败不等于必需依赖失败，所选实现需声明缺失行为。若没有任何可用目标，best_effort 也失败。正常执行产生 no_candidates/insufficient_evidence 的合法产物可 completed；这不保证其能满足另一个实现的最低证据需求。必需上游执行失败则消费者 blocked，不加载模型。一个分支失败不提前终止其他独立请求分支；控制信号可终止剩余计算。

节点重试有限、从该节点起点重跑，已发布上游和独立分支保留。Job 的执行 attempt 与 node_attempt 独立。中断先由原控制面对账为 interrupted，显式恢复沿原计划核验产物后调度，不能自动伪装旧 Worker 仍在运行。消费者绑定变化触发缓存重新判定。

总体进度在冻结计划上用稳定权重聚合；节点重试可以回退节点局部进度，总体展示采用已确认进度的单调值。缓存节点完成权重立即计入。AnalysisStage 只用于 legacy，modular 使用 nodeRuns，不塞入任意能力名称。

### D10. 发布协议与故障边界

1. 在 attempt 隔离路径写临时文件并响应 token。
2. 校验 schema、内容摘要、Manifest 和输入引用，finalize 到不可变 artifact_id 位置。
3. SQLite 事务核验 job lease/attempt；写 Manifest、血缘、使用引用、节点完成与缓存指针。
4. 提交后产物才是 published；消费者只读控制面可见的已发布产物。
5. 更新 Job 运行清单与终态时同样校验 lease，清单保留 partial/none 状态。

文件系统 rename 与 SQLite 无法组成单个物理事务。finalize 后、DB 提交前崩溃会留下 orphan；后续按发布记录对账，不能扫描文件名就当缓存命中。事务失败不能覆盖已发布内容。旧租约迟到发布拒绝；新尝试使用新 artifact_id。

共享产物一旦合法发布，不因生产 Job 后续失败而失效。Job 结果不能保留“本次完整成功”的错误声明；运行清单明确标识部分完成，和 legacy failed Job 不返回 stale completed result 的规则分别处理。

### D11. 事件关系与语义扩展

执行 DAG 只表示生产/消费，Association 表示证据关系。类型示例：

~~~text
ball.detect -> ball.track_2d -> ball.clean_2d
                                      -> 接触/弹跳候选 -> ball.events
ball.clean_2d + ball.events -> ball.reconstruct_3d

player.detect + RGB -> pose.sequence -> motion.upper_limb -> swing.segment
racket.detect + player 证据 -> racket.player_association
所选 pose/RGB/racket 证据 -> stroke.classify

Swing + Contact + BallEvent -> 版本化 Association
事件/球路 -> shot.assemble -> shot.landing
stroke 属性 + landing + court/rally/context -> shot.semantic -> tactics.analyze
~~~

这是能力扩展示意，不是本期完整执行图；依赖以具体实现声明为准。contact.detect 可有纯球路或多模态实现，不能让所有接触算法强制依赖挥拍再反向约束同一挥拍。后续迭代需新类型/版本明确阶段，禁止用单一 trajectory 名称形成环。

ObjectRef 包含 artifact_id/object_type/local_id 和适用作用域；Association 包含关系类型、候选、时间/主体约束、score、歧义和实现版本。Shot/Landing 保留现有 exact segment/event 引用，不能用最近时间补齐。

stroke 属性、shot semantic、rally stage、is_volley 分开；shot_type=stage 的历史含义保留。语义升级只生成新派生产物，保留原始证据。置信度与 evidence_sufficiency 分别表达；缺球落点时不能凭高分类分数输出确定丁克球结论。

### D12. 共用 CLI/API 与最小产品接入

拟定 CLI 为 backend/scripts/analysis_dev.py，命令组：
- prepare-source：显式生成并登记来源/时间元数据。
- plan：只读预览，输出计算合同、窗口/资源/缓存提示和缺项。
- run：创建/复用 Job，可有界等待结果；执行仍由同一 Worker 完成。
- inspect：按 Job/plan/artifact 查看节点、输入、质量、可用性与 trace。

选项包含 source 或 take、targets、实现选择、start/end、sampling、有限 context budget、failure policy、固定输入和有效参数。参数 schema 与 API 共用。命令名及 API 路径在实现时可按既有 CLI 约定调整，不能改变上述行为。

最小 API 计划为 POST /analysis/plans/preview、POST /analysis/jobs（新增 engine 与模块请求）、GET /analysis/jobs/{job_id}/manifest、GET /analysis/artifacts/{artifact_id}。这里均相对于既有路由前缀。使用独立 /manifest 避开现有 artifacts/{artifact_name} Literal 路由；禁止返回绝对路径或任意文件读取。

前端只补充判别类型、模块 Job 状态和清单/技术详情读取，不建设完整“分析工作室”。legacy 结果页保留。模块任务不应跳到要求 reportId 的报告页；部分结果明确显示目标未完成原因。

### D13. trace 版本兼容与可验证指标

legacy analysis-run-trace.v1 保持原字段/枚举；modular v2 增加 plan/node/capability/implementation/node_attempt、outcome、cache_decision、绑定与产物引用。event 沿用 start/end/retry/fail/lease_lost/canceled/trace_sink_unavailable，避免直接扩充严格 v1 枚举。

cache hit 写节点 start/end 和 outcome=cached，不计推理。blocked 写原因引用，不伪造异常。trace 与节点索引联查可解释“为什么扩窗、为什么重算、为什么没有加载其他模型”。节点计数包括 capture opens、实际解码范围/数量、送模样本、模型构造/执行次数、耗时；fixture 与真实数据记录分开。

重试在重跑前记录原异常/digest/frames/策略；节点与 Job 汇总不得双计同一失败。取消、lease 丢失、超时沿用控制信号归因，终态保留 failureEvidence/retryHistory。公开错误脱敏，内部诊断受控。

## Risks / Trade-offs

- [节点间重新解码增加耗时] → v1 先使用有界范围和独立缓存，记录成本；明确 streaming group 合同后再优化。
- [媒体强摘要首次需要整文件读取] → 显式准备并缓存不可变来源身份，避免每次 preview 读取视频；身份准备和模型分析分别计时。
- [局部有状态结果不同于整场历史] → 冻结初始化/采样相位，记录预热和截断，不宣称两者数值等价。
- [保守保留导致磁盘增长] → inspect 提供引用/位置/体积与回收资格；自动 GC 延后，不用直接引用计数删除间接证据。
- [SQLite 与文件跨资源发布崩溃] → DB 是可见性边界，attempt 隔离和 orphan 对账，故障注入验证。
- [模型、PTS 或真实双摄素材缺失] → 记录未完成验收，不以 fixture 或 fallback nominal FPS 替代真实通过。
- [共享 Executor 与活跃身份 change 冲突] → 独立合同/适配可先推进；触碰共享文件前固定基线并明确文件归属，不混入身份算法调整。
- [新增 engine 回滚后无法读取模块 Job] → 保留兼容读取与存储迁移，先关闭新提交并排空执行，不能直接用旧代码解释新任务。

## Migration Plan

1. 固定现有 legacy 代表性样本、阶段/产物/取消行为和失败证据基线；记录已有失败，不把既存算法缺陷伪装成本 change 回归。
2. 新增纯合同、Registry、Planner、窗口/上下文与 fixture；先不改默认产品请求。
3. 向既有 SQLite 做幂等增量迁移，新增计划/节点/产物/缓存/引用表及默认 engine；历史 JSON 只在既有启动/显式导入边界处理。
4. 接入模块 Executor/发布器、nodeRuns 与 v2 trace；显式 engine 才启用。legacy 单/多摄及 prerequisite 分派回归通过。
5. 接入真实三个能力和共用 CLI/API，完成短窗口单摄/双摄、窄重算、故障恢复、引用删除及资源隔离验收。
6. 保留完整产品 legacy 默认，交付开发验证文档和真实证据。未来能力根据独立 change 逐个从 planned 升为 implemented。
7. 回滚：关闭模块新提交；协作式结束/中断现有模块运行；保留新数据表、共享产物和兼容 reader，不删除证据或把模块任务改成 legacy。需要二进制整体回滚时先导出/保存新记录，并明确旧 reader 不支持模块任务的限制。

## Open Questions

以下为实施验收需确认的环境事实，不阻塞已确定的架构合同：
- 用于真实单摄/双摄验收的短片、模型权重及 PTS/同步快照的可访问位置；准备时登记强身份。
- 四人身份 change 在进入共享 executor 编辑时的最新基线与文件归属。
- 现有 legacy 回归的稳定样本与已知失败清单，以及真实窗口的耗时/显存基线。

本轮没有执行模型或媒体分析，不能给出真实性能提升或算法准确率结论。
