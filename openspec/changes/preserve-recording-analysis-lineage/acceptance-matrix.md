# 验收矩阵：preserve-recording-analysis-lineage

共 49 项，编号连续。A-11 / A-12 / A-13 / A-17 / A-19 为按 DEC-014 增补（标 ★）；A-25 / A-26 为前轮独立复审补入；A-27～A-49 为 P0-01 最终技术评审补充。E1 / E2a / E2b 为 Apply 后必验，E3 需负责人单独授权。

| ID | 场景 | 触发条件 | 期望结果 | 任务 | 级别 |
|---|---|---|---|---|---|
| A-01 | 单摄 Full 发起后任务归属该录制 | 从录制页对已停止录制发起 Full 分析 | 创建成功；`sourceSnapshot.kind=recording`、`sessionId` 为该 Session、`videoId` 为登记视频；素材历史可见该任务 | 1.1 1.4 2.1 3.1 | E1/E2b |
| A-02 | 单摄 Modular 发起保持计划身份 | 同上但走 `analysisEngine=modular_v1` | 来源核验通过；`plan_hash` 与改动前逐字相同；节点缓存键不变 | 2.1 3.2 | E1 |
| A-03 | 普通 Upload 无来源仍合法 | 上传视频直接创建分析，不带 session/take | 创建成功；`sourceSnapshot.kind=upload`、`provenance=none`、`sourceStatus=upload`；不与任何录制来源等价 | 1.4 2.1 3.4 6.6 | E1/E2a |
| A-04 | 声明了来源但无法解析 | 请求带 `capture_take_id`，但无 `recording_session_id`/`videoId`，且无法从 Take 推出所属 Session 与视频 | HTTP 400 `recording_source_required`；不创建 Job | 2.2 2.3 | E1 |
| A-05 | 声明的登记对象不存在 | 请求声明的 Session、登记 Video 或显式 Take ID 不存在 | HTTP 404 `recording_source_not_found`；不创建 Job | 2.2 2.3 | E1 |
| A-06 | Video 不属于该 Session | Session 存在，`videoId` 不在其登记视频集合内 | HTTP 409 `source_ownership_mismatch`；不创建 Job | 2.2 2.3 | E1 |
| A-07 | Take 与 Session 不匹配 | Take 存在但其 `source_session_id` ≠ 请求 Session | HTTP 409 `source_ownership_mismatch` | 1.2 2.2 2.3 | E1 |
| A-08 | 来源登记或已登记存储不可访问 | 注入 DB 查询异常、超时或外接卷离线 | 来源核验返回 HTTP 503 `recording_source_unavailable`；产物读取返回 `location_unavailable`；**不得**当作「无来源」放行或切到本地目录 | 1.3 1.5 2.2 2.3 | E1 |
| A-09 | 未显式声明 Take 且查询确认零 Take | 请求没有 `capture_take_id`；Take 查询成功返回零条；Session↔Video 已核实 | 允许 `session-only`：`captureTakeId=null`、`provenance=verified_declared`；查询异常或显式 Take ID 不适用此降级 | 1.3 2.1 | E1 |
| A-10 | 唯一 Take 被补齐 | 该 Session 恰有 1 个 Take 且与 Video 一致 | 任务 `sourceSnapshot.captureTakeId` 被补齐为该 Take | 1.1 1.2 | E1 |
| A-11 ★ | 顶层与 metadata 来源冲突的候选不遮挡同源候选 | 同签名候选 3 条：Job A 的 `metadata.recording_session_id` 与请求相同但顶层 `recordingSessionId` 冲突；Job B 两处均与请求相同；Job C 两处均为异源 | 跳过 A（不可证明）与 C，复用 B；不新建；顶层字段不进签名，故 A 与 B 签名相同 | 1.2 3.1 3.3 | E1 |
| A-12 ★ | 异源候选全部不可用则新建 | 同签名候选仅异源/无来源 | 新建独立 Job；旧 Job payload 与状态不变 | 3.2 3.4 | E1 |
| A-13 ★ | 多个同源候选稳定选择 | 同签名、同来源存在 2 条（一个 `succeeded`、一个 `canceled`） | 选中 `succeeded` 那条；连续两次调用结果一致；新进程重启后仍一致 | 3.2 3.3 | E1 |
| A-14 | Take 多候选拒绝 | 同一 `(source_type, source_id)` 命中 2 条 Take | HTTP 409 来源不唯一；不自动选第一条；不回填任何 Take | 1.1 1.3 | E1 |
| A-15 | 签名无法证明等价不复用 | 旧候选签名缺失或与当前不同 | 不复用；新建独立 Job；不改写旧候选签名；该旧任务在任务列表中仍可见且来源显示为未知 | 3.2 3.4 6.3 | E1 |
| A-16 | 单摄省略 camera_slot 合法 | 单摄请求不带 `camera_slot` | 创建成功（与改动前一致）；不写入默认 slot 到 `sourceSnapshot` | 5.1 | E1 |
| A-17 ★ | 默认视图不能充当来源身份 | 仅提供 `camera_slot="cam_1"`，无 session/take/video 归属 | 不得据此通过来源核验；按 A-04 返回 400 | 5.1 5.3 | E1 |
| A-18 | 双摄 A/B 绑定回归 | 双摄 Parent 创建，A/B slot 与 scene 标定一致 | 复用既有绑定契约通过；来源快照记录完整 `(video_id, slot, camera_id)` 集合；slot 与绑定不一致时仍按既有逻辑拒绝 | 5.2 | E1/E3 |
| A-19 ★ | 400/409 machine code 兼容 | 旧 Modular 返回 400 + `source_ownership_mismatch`；新后端返回 409 + 同 code | 前端两路进入同一提示分支；普通 400（其他 code）落默认分支，不被解释为来源冲突 | 6.1 6.2 6.4 | E2a |
| A-20 | 内部自动分析创建并带来源 | `auto_analyze_after_stop=true`，`rally_context_enabled=false` | 任务创建；`sourceSnapshot.provenance=verified_internal`、`declaredBy=session_stop`；metadata 含 `recording_session_id`；`auto_analysis_job_id` 非空 | 4.1 4.2 | E1 |
| A-21 | 自动分析失败不影响停录 | 令创建入口抛错 | 录制状态 `completed`；`auto_analysis_job_id=null`；Session 快照落盘成功；`write_capture_metadata` 执行；错误仅进日志 | 4.3 | E1 |
| A-22 | HTTP 伪造内部来源无效 | 在 `metadata` 中加入 `trusted=true` / 伪造 `session_dir` 等字段 | 不获得内部信任；仍走 HTTP 来源核验；伪造字段不进入 `sourceSnapshot.provenance` | 4.1 4.4 | E1 |
| A-23 | rally_context gate 开/关 | 分别以 `rally_context_enabled` 开、关执行停录 | 开：不自动创建，等待确认入口（既有行为）；关：自动创建并按 A-20 带来源 | 4.2 4.4 | E1 |
| A-24 | E2b 由 QA Agent 隔离执行 | Apply 后按 D-10 执行 | 真实前后端 + 临时 SQLite + 临时存储根 + 合成夹具；归档请求/响应、DB 查询结果、浏览器证据；负责人审阅后签字 | 7.2 7.3 | E2b |
| A-25 | 素材历史按同源收拢 | 某素材下同时存在同源任务与「挂到同素材但来源会话不同」的异源任务 | 工作区只列出同源任务；打开异源任务时不按本素材展示其结果并给出可理解提示 | 6.5 | E1 |
| A-26 | Take 路径优先且不参与来源身份 | 内部自动分析创建后重启 Worker；Take 与 Session 的服务端路径都可用 | 解析器选 Take 的持久化路径；`metadata.session_dir` 不参与来源判定或路径定位；历史 Job 仍可读取 | 1.5 4.2 | E1 |
| A-27 | Modular 同计划同来源复用 | `modular_v1` 两次提交相同 `plan_hash` 与等价来源，第二次未请求新版本 | 第二次返回同源且状态可复用的既有 Job | 3.7 3.8 | E1 |
| A-28 | Modular 同计划异来源新建 | `modular_v1` 两次提交相同 `plan_hash`，但 Session/Video/Take 来源身份不同 | 第二次创建独立 Job；不得返回或改写第一个 Job | 3.7 3.8 | E1 |
| A-29 | Modular 同源新版本关联前序 | 同源 Modular Job 已存在，提交相同计划的新版本 | 新 Job 设置 `previousJobId` 指向同源前序 Job | 3.7 3.8 | E1 |
| A-30 | Modular 异源新版本不串链 | 只有异源同 `plan_hash` Job 时提交新版本 | 新 Job 不设置该异源 Job 的 `previousJobId`；无同源前序时字段为空 | 3.7 3.8 | E1 |
| A-31 | 计算缓存与 Job 身份分离 | 不同录制来源的 Job 消费符合既有缓存合同的同一计算输入 | 符合条件时可共享不可变计算产物；Job、sourceSnapshot 与版本链仍独立；来源不进入 `plan_hash`/节点缓存键 | 3.7 3.8 | E1 |
| A-32 | 一致的旧来源声明可重核验 | 历史 Job 无快照，但声明完整一致且 Session/Video/Take 重核验通过 | 作为临时 `verified_declared` 候选参与同源比较；旧 payload 不回写 | 3.5 3.6 | E1 |
| A-33 | 冲突或不可证旧声明保持未知 | 历史 Job 顶层与 metadata 声明冲突、来源声明全缺失或 fingerprint 与规范身份不符 | `sourceStatus=unknown`；不复用且不归入任一录制历史；一般任务列表仍可读取 | 3.5 3.6 6.3 6.7 | E1/E2a |
| A-34 | 来源身份不受获取方式影响 | 来源业务身份一致，但一侧 `provenance=verified_internal`、另一侧为 `verified_declared`；`declaredBy` 不同 | 身份等价；fingerprint 不包含获取方式；若双方 slot 都有值则必须相等，单侧缺省须由登记唯一证明 | 3.5 3.6 | E1 |
| A-35 | 新请求重复来源字段冲突 | 顶层与 metadata 同时声明不同 Session 或机位 | HTTP 409 `source_ownership_mismatch`；不创建 Job，不任选字段 | 1.6 2.2 2.3 | E1 |
| A-36 | 单入口声明可归一化 | 只在一个契约允许入口声明完整来源，其他重复字段未提供 | 服务端核验后归一化并创建任务；不强制客户端重复提交字段 | 1.6 2.1 | E1 |
| A-37 | 显式 Take 不存在不降级 | Session/Video 有效，但请求显式声明的 `capture_take_id` 不存在 | HTTP 404 `recording_source_not_found`；不得按零 Take 创建 session-only Job | 1.6 2.2 2.3 | E1 |
| A-38 | 任务摘要安全投影三态 | 读取已核实录制、明确 Upload、不可证历史 Job | 分别返回 `verified_recording` / `upload` / `unknown`；不返回完整 `sourceSnapshot`、绝对路径或可信存储根 | 6.6 6.7 | E1/E2a |
| A-39 | 后端 Session 筛选排除未知冲突任务 | 请求 `GET /api/analysis/jobs?recording_session_id=<sid>`，候选含同源、异源及冲突旧 Job | 只返回与该 Session 规范化来源等价的已核实任务；冲突/未知 Job 不出现在任一冲突 Session 的筛选结果 | 6.5 6.6 6.7 | E1 |
| A-40 | 前端录制历史与后端归属一致 | Library 同时加载同源任务、异源任务与冲突旧任务 | 只把已核实且身份等价的任务归入录制；未知任务不显示为该录制结果 | 6.3 6.5 6.7 | E2a |
| A-41 | 上传历史只接纳明确 Upload | 上传素材关联任务包含明确 Upload、录制任务及无快照旧任务 | 仅 `sourceStatus=upload` 且 Video ID 相同的任务归入上传素材；unknown 不被猜作上传 | 6.5 6.6 6.7 | E2a |
| A-42 | Take 路径缺失时使用 Session 路径 | Take 没有持久化路径值，所属 Session 有可用服务端路径 | 只读解析器使用 Session 路径；不读取 HTTP `metadata.session_dir` | 1.5 | E1 |
| A-43 | Take/Session 路径缺失时使用可信 Job 路径 | Take 与 Session 均无路径值，Job payload 有服务端写入且独立于 metadata 的可信产物根 | 解析器使用可信 Job 产物根；Worker 不依赖进程内上下文 | 1.5 | E1 |
| A-44 | 已登记外接卷离线不回退 | Take 路径指向未挂载外接卷，Session 或本地目录另有路径 | 返回 `location_unavailable`；不得因外接卷离线转用 Session/本地目录伪装成功 | 1.5 | E1 |
| A-45 | 无可信路径返回不可用 | Take、Session 与服务端 Job 产物根均无可用持久化位置 | 返回 `location_unavailable`；不得依据客户端路径创建目录或推测路径 | 1.5 | E1 |
| A-46 | HTTP 伪造 session_dir 不参与定位 | 请求 metadata 中提供指向其他目录的 `session_dir` | 来源结论和产物根均不受影响；字段不复制进可信产物定位字段 | 1.5 4.4 | E1 |
| A-47 | Worker 重启后恢复可信位置 | 新 Job 创建后重启 Worker，仅保留 Take/Session/可信 Job payload | Worker 仅凭持久化关系恢复产物根，不依赖内存上下文 | 1.5 4.2 | E1 |
| A-48 | 历史 Job 产物仍按旧路径读取 | 读取具有既有 ArtifactRef/产物根的历史 Job | 原有 Job ID 与受控历史读取路径继续可读；不把历史 metadata.session_dir 升格为可信根 | 1.5 | E1 |
| A-49 | 第二视角变化时双摄 Parent 不复用 | 同 Take、同参考机位与同计划，但第二路登记 Video 或完整绑定三元组集合变化 | 创建独立 Parent；不得仅凭 `plan_hash` 或参考机位复用旧 Parent | 5.2 5.4 3.7 3.8 | E1 |

## 覆盖说明

- **T1 Legacy 枚举**：A-11、A-12、A-13、A-15。异源首条遮挡（A-11）与稳定顺序（A-13）是本次最关键的回归。
- **T2 Take 唯一性**：A-08（异常 ≠ 零个）、A-09（零个才可 session-only）、A-10（唯一补齐）、A-14（多个拒绝）。
- **T3 camera_slot**：A-16（省略合法）、A-17（默认视图不是来源身份）、A-18（双摄绑定回归）。
- **T4 内部可信入口**：A-20、A-21、A-22、A-23。
- **Q1 兼容**：A-19。
- **Q2 保守新建**：A-12（允许新建）、A-04~A-08（拒绝创建）两组必须能同时通过，才说明边界没被混淆。
- **Q3 E2b**：A-24。
- **素材工作区**：A-25（独立复审补入）。
- **Modular Job 身份与计算缓存分离**：A-27～A-31。
- **历史来源解析与等价**：A-32～A-34。
- **请求来源冲突与显式 Take**：A-35～A-37。
- **来源状态投影与素材归属**：A-38～A-41。
- **可信产物定位与历史兼容**：A-42～A-48。
- **双摄 Parent 完整来源身份**：A-49。

- **任务覆盖**：35 项任务中 34 项被至少一个场景显式引用（见「任务」列）。7.1 是 E1/E2a 的**整体执行任务本身**，其覆盖由级别为 E1/E2a 的全部场景共同构成；不单独挂到某一条场景。其余任务均有明确场景映射。

## 不作为通过证据的项

- 前端 53 项、后端 93 项是修复前基线，只说明既有行为现状。
- OpenSpec `--strict` 通过只证明提案结构有效，不证明代码已实现或行为已验证。
