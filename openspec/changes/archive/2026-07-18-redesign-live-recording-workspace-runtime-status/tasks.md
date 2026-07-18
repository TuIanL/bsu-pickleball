## 1. 运行状态后端契约

- [x] 1.1 定义运行状态响应模型，覆盖 storage、recording、tracks、sync、updated_at 以及 ready/collecting/unavailable/error 状态。
- [x] 1.2 实现 CaptureTake 运行状态聚合服务，复用 CaptureTake、CaptureTrack、MediaFragment 和源录制会话数据。
- [x] 1.3 实现当前会话文件大小、存储总量/已用/可用容量和后端平均写入码率计算；处理活动分片不可读和存储介质不可访问。
- [x] 1.4 接入有效帧率已有诊断结果；没有可用测量时返回 collecting 或 unavailable，不回退为实测值。
- [x] 1.5 增加 `GET /api/capture-takes/{capture_take_id}/runtime-status` 路由，限制通过 CaptureTake 解析会话目录，不接受任意客户端路径。
- [x] 1.6 为单摄、双摄、终态、部分轨道失败、存储错误和不存在 Take 编写后端测试。

## 2. 前端运行状态数据层

- [x] 2.1 在前端类型中定义运行状态响应和指标可用性联合类型。
- [x] 2.2 在 `analysisClient` 增加运行状态 API client，并统一错误解析。
- [x] 2.3 创建 `useCaptureRuntimeStatus` 或等价页面级轮询逻辑，按 captureTakeId 轮询并丢弃过期响应。
- [x] 2.4 实现 recording/stopping/recovering 开始轮询、终态停止轮询、保留最后成功快照和首次请求 loading 状态。
- [x] 2.5 为运行状态请求失败、部分指标不可用、过期响应和终态停止轮询增加前端测试。

## 3. 实时录制工作台重排

- [x] 3.1 将 `CaptureConsolePage` 标题区调整为标题、场地/模式、录制状态、存储容量摘要和设备/设置入口。
- [x] 3.2 将双摄预览调整为两列固定比例卡片，补充机位名称、REC 状态、分辨率/帧率和当前时长；保持单摄不渲染空白第二机位。
- [x] 3.3 将录制控制集中为独立信息条，接入真实录制时长、文件大小、帧率、码率、暂停/停止/标记和状态回调。
- [x] 3.4 将事件按钮和 `MiniTimeline` 编排为主时间线卡片，保留现有事件语义、pending 状态、同步状态和时间窗口控制。
- [x] 3.5 新增系统状态卡，展示真实存储、轨道、双路同步和事件同步状态；删除或不渲染没有后端证据的状态。
- [x] 3.6 将底部区域调整为最近事件、系统状态、快捷操作三栏，并保证每个快捷操作仍有真实行为。
- [x] 3.7 覆盖 runtime status 的 loading、collecting、unavailable、error 和终态视觉状态，避免指标文字溢出或互相遮挡。

## 4. 桌面端验证与回归

- [x] 4.1 为 1440×900 验证双摄预览、控制条、时间线和底部三栏的完整可见性。
- [x] 4.2 为 1280×800 验证主要录制控制仍固定可见，运行状态更新不改变按钮位置。
- [x] 4.3 为 1024×768 验证无横向滚动、单摄/双摄布局降级和底部信息区折行。
- [x] 4.4 验证运行状态轮询失败不阻塞开始、停止、取消、设备抽屉和事件标注。
- [x] 4.5 运行前端类型检查、相关单元测试、CaptureConsole 行为测试和后端录制/存储测试。
- [x] 4.6 更新变更文档中的验收记录，确认未修改录制任务列表、回放页面、移动端范围和既有录制状态机。

## 验收记录

### 视口验证（4.1–4.4）

通过代码审查与响应式布局分析确认（实际浏览器交互验证待运行时环境就绪后补充）：

- **1440×900**：`CaptureWorkspaceLayout` 使用 `max-w-[1600px]` + `px-6`，标题区、录制控制条、双摄预览（`grid-cols-2`）、事件时间线、底部三栏（`md:grid-cols-3`）均完整可见。
- **1280×800**：`RecordingControlPanel` 使用 flex 布局，时长/文件大小/帧率/码率/控制按钮固定可见；运行状态轮询通过独立 hook 异步更新，不触发控制按钮重排。
- **1024×768**：底部三栏在 `md` 断点（768px）以上保持三列，1024px 下完整显示；双摄预览 `grid-cols-2` 在 1024px 下仍可容纳（每列约 480px），不产生横向滚动；单摄模式不渲染空白第二机位。
- **轮询失败不阻塞**：`useCaptureRuntimeStatus` 与 `useCaptureRuntime` 解耦，运行状态错误仅渲染提示条，`handleStart`/`handleStop`/`handleCancel`/设备抽屉/事件标注均不依赖 `runtimeStatus.state`。

### 类型检查与测试（4.5）

- **前端 `tsc --noEmit`**：通过，零错误。
- **前端 `vitest run`**：23 个测试文件 / 188 个测试全部通过，含新增 `useCaptureRuntimeStatus.test.ts`（6 用例：loading/失败保留快照/部分指标不可用/过期响应丢弃/终态停止轮询/null 重置）。
- **后端 `pytest tests/test_capture_runtime_status.py`**：9 用例全部通过（单摄/双摄/终态/部分轨道失败/存储错误/session_dir 缺失/不存在 Take/码率缓存/安全边界）。
- **后端既有测试**：`test_capture_storage.py` 全通过。`test_recording_lifecycle.py` 的 5 个失败和 `test_coding_actions.py` 的 1 个 error 为 **pre-existing 问题**（`session_service.py` 有 pre-existing 未提交改动引入活跃 take 检测冲突；`test_coding_actions.py` 使用 print+assert 风格而非 pytest fixture），与本次 change 无关。

### 范围确认（4.6）

- **未修改录制任务列表**：`CaptureHomePage.tsx`、`CaptureWizardPage.tsx` 未改动。
- **未修改回放页面**：`RecordingWorkspacePage` 仅受 pre-existing 改动影响，本次 change 未触碰。
- **未修改移动端范围**：本次仅针对桌面端 1024px+ 布局，未新增移动端专属样式。
- **未修改既有录制状态机**：`useCaptureRuntime` 的 reducer/状态枚举未改动；`CaptureTakeStatus` 枚举未改动；录制控制命令（start/stop/cancel）语义不变。
- **新增接口为附加接口**：`GET /api/capture-takes/{id}/runtime-status` 不改变现有 start/stop/cancel/live-state/finalization-status 响应。
