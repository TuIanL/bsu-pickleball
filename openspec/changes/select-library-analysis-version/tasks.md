## 1. 历史 Job 摘要与选择基础

- [x] 1.1 扩展 LibraryAnalysisJobView 与 libraryAdapter 投影，提供选择器所需的 createdAt、analysisKind、executionMode、分析窗口和状态摘要，同时继续排除 internal child
- [x] 1.2 新增 resolveSelectedAnalysisJob 纯函数，区分显式选择、primary 默认、跨素材、internal、已删除和无结果 fallback
- [x] 1.3 新增统一 buildLibraryWorkspacePath/query merge 纯函数，支持保留 view、analysisJob、t 及其他合法 query
- [x] 1.4 为选择解析和 URL 构造补充表驱动单元测试，覆盖无参数、合法历史 Job、跨素材 Job、internal child、删除后 fallback 和 query 保留

## 2. SelectedAnalysisContext 与任务级 capability

- [x] 2.1 在 LibraryItemWorkspace 建立 URL 驱动的 SelectedAnalysisContext，未显式选择时使用 primaryResultAnalysisJobId，禁止维护第二份可变 selected state
- [x] 2.2 对 selected Job 加载一次轻量 Job/AnalysisResult manifest，并按 Job ID 隔离缓存、loading、error 与过期请求
- [x] 2.3 重构 computeLibraryViewCapabilities/resolveViewCapability，使其显式消费 selected Job 状态、analysisKind 与 manifest，而非隐式读取 primary Job
- [x] 2.4 实现 selected Job 快速切换的请求取消或 stale-response guard，确保 Job A 的迟到响应不会覆盖 Job B
- [x] 2.5 为 completed 缺产物、failed/canceled、单摄与 multiview、快速切换和 manifest 缓存隔离补充 capability/加载状态测试

## 3. 历史版本选择器交互

- [x] 3.1 更新概览历史任务行，显示任务类型、状态、创建时间以及可用的执行模式和分析窗口，缺失历史字段时不伪造值
- [x] 3.2 为 completed 任务增加“查看结果”，为 failed/canceled 增加“查看详情”，active 任务继续显示“查看进度”和“取消”
- [x] 3.3 增加当前选中版本标记、“查看最新版本”入口和显式选择写入 analysisJob 的行为，包括选择当前最新版本时也固定 Job ID
- [x] 3.4 在 active Job 完成且已有显式历史选择时保留当前内容，并显示有新版本可用；无显式选择时继续跟随新的 primary result
- [x] 3.5 在删除当前 selected Job 后执行定向重投影、安全 fallback、URL replace 规范化与非阻塞提示
- [x] 3.6 为历史行 CTA、选中态、新版本提示、active 解耦和删除 selected Job 补充 LibraryItemWorkspace 交互测试

## 4. 全结果 Tab 版本联动

- [x] 4.1 将 Vision、BallTrajectory、Report 与 Technical Content 的 jobId 统一切换为 SelectedAnalysisContext.jobId，移除 workspace 内对 primaryAnalysisJobId 的直接绑定
- [x] 4.2 按 selected Job.analysisKind 分派 Technical Content：multiview 使用 MultiviewObservability，单摄使用 AnalysisDetails
- [x] 4.3 让 workspace Tab 切换与 embedded onSelectView 使用统一 URL builder，跨分析、球路、报告、技术详情、视频和片段均保留合法 analysisJob
- [x] 4.4 让报告证据跳转等带时间定位的内部导航同时保留 analysisJob 与 t，且继续使用 replace 语义
- [x] 4.5 为 selected Job 缺球路/报告、failed/canceled 诊断、sync_recording 选择 A/B 单摄 Job 和四个 Content 同 Job 断言补充集成测试

## 5. 无效深链与 Progress 精确定向

- [x] 5.1 实现 analysisJob 的素材归属 fail-closed 校验；无效、跨素材或 internal Job 不得触发结果/报告/artifact 请求
- [x] 5.2 对无效 analysisJob 使用 replace 清理该参数，保留 view、t 与其他合法 query，并回退到 primary result 或无结果态
- [x] 5.3 更新 Library-origin Progress 完成 CTA，为分析、球路、报告和技术详情路径附加当前 completed Job ID
- [x] 5.4 更新 Capture-origin 成功解析到 LibraryItem 的结果 CTA，使其附加当前 completed Job ID；Task Console origin 保持 legacy 行为
- [x] 5.5 为刷新深链、无效参数规范化、reconciliation 延迟、Library/Capture/Task Console CTA 路由补充导航单元测试

## 6. 回归与验收

- [x] 6.1 运行前端 TypeScript 类型检查和相关 Vitest 测试，修复 Library、routing、capability、Progress 与 Content 回归
- [x] 6.2 使用同一 sync_recording 的两个 completed multiview Job 验收：选择旧版本后四个结果 Tab、刷新和往返视频 view 始终保持旧 Job
- [x] 6.3 使用同一 sync_recording 的 multiview 与 A/B 单摄历史 Job 验收：技术详情类型与各自 manifest capability 正确切换
- [x] 6.4 验收 active 重分析完成、删除 selected Job、failed/canceled 详情和伪造跨素材 analysisJob 的安全边界
