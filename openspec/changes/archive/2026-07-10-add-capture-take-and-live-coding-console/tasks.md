## 1. 数据库迁移（Alembic）

- [x] 1.1 安装和配置 Alembic
- [x] 1.2 生成 initial baseline migration（现有 schema）
- [x] 1.3 创建 capture_takes 表（含 CHECK、UNIQUE、INDEX）
- [x] 1.4 创建 capture_tracks 表（含 FK、UNIQUE、INDEX）
- [x] 1.5 创建 capture_coding_actions 表（含 UNIQUE、INDEX）
- [x] 1.6 创建 live_coding_states 表（含 FK）
- [x] 1.7 创建 capture_segments 表（含 FK、CHECK、INDEX）
- [x] 1.8 ALTER session_timeline_events 增加 capture_take_id 列
- [x] 1.9 ALTER session_timeline_events 增加 is_undone 列
- [x] 1.10 编写 migration 回滚脚本
- [x] 1.11 测试 migration 在现有数据库上的执行

## 2. CaptureTake 模型与生命周期

- [x] 2.1 创建 CaptureTake SQLAlchemy ORM 模型
- [x] 2.2 创建 CaptureTrack SQLAlchemy ORM 模型
- [x] 2.3 实现 CaptureTake CRUD 服务
- [x] 2.4 实现 CaptureTrack 创建（单摄：一个 primary track）
- [x] 2.5 实现 CaptureTrack 创建（双摄：两个 track，计算 offset）
- [x] 2.6 实现 CaptureTake 生命周期管理（创建/停止/失败/取消）
- [x] 2.7 实现旧数据适配逻辑（RecordingSession → CaptureTake）
- [x] 2.8 实现 CaptureTake 归档（archived_at）而非硬删除
- [x] 2.9 实现 CaptureTake 查询 API
- [x] 2.10 编写 CaptureTake 服务单元测试

## 3. 录制服务适配 CaptureTake

- [x] 3.1 修改单摄录制启动逻辑：创建 CaptureTake + CaptureTrack
- [x] 3.2 修改单摄录制停止逻辑：补偿流程关闭 CaptureTake
- [x] 3.3 修改双摄录制启动逻辑：创建 CaptureTake + 两个 CaptureTrack
- [x] 3.4 修改双摄录制停止逻辑：补偿流程关闭 CaptureTake
- [x] 3.5 修改录制响应，返回 capture_take_id
- [x] 3.6 编写录制适配集成测试

## 4. TimelineEvent Service 重构

- [x] 4.1 拆分 create_timeline_event：提取 _add_timeline_event 内部方法
- [x] 4.2 _add_timeline_event 执行 db.add + db.flush，不 commit
- [x] 4.3 旧 API 方法迁移到 with db.begin() + _add_timeline_event
- [x] 4.4 修改 TimelineEvent 查询支持 capture_take_id 筛选
- [x] 4.5 修改 TimelineEvent 查询支持 include_undone 参数
- [x] 4.6 修改 TimelineEvent 时间戳策略（CaptureTake 优先于 RecordingSession）
- [x] 4.7 编写 TimelineEvent 重构单元测试

## 5. CaptureCodingAction 与 LiveCodingState

- [x] 5.1 创建 CaptureCodingAction SQLAlchemy ORM 模型
- [x] 5.2 实现 CaptureCodingAction 持久化服务
- [x] 5.3 实现 client_action_id 幂等检查
- [x] 5.4 实现 request_hash 重放攻击检测
- [x] 5.5 实现 revision 冲突检测（409）
- [x] 5.6 实现 duplicate_action 检测与原始结果返回
- [x] 5.7 创建 LiveCodingState ORM 模型
- [x] 5.8 实现 LiveCodingState 初始化
- [x] 5.9 实现 LiveCodingState 每次 action 同步更新
- [x] 5.10 实现 LiveCodingState 查询 API
- [x] 5.11 实现 LiveCodingState 重放恢复（从 CaptureCodingAction）
- [x] 5.12 编写 LiveCodingState 单元测试

## 6. Coding Actions API

- [x] 6.1 实现 coding-actions 路由和请求校验
- [x] 6.2 实现 start_set action（关闭 rally + game + 上一个 set）
- [x] 6.3 实现 start_game action（关闭 rally + 上一个 game，缺 set 创建 inferred）
- [x] 6.4 实现 start_next_rally action（关闭上一个 rally，缺父级创建 inferred）
- [x] 6.5 实现 end_rally / end_game / end_set action（no-op 策略）
- [x] 6.6 实现 toggle_non_play action（开启关闭 rally，保留 set/game）
- [x] 6.7 实现 change_side action（点事件，不改变层级）
- [x] 6.8 实现 add_note action
- [x] 6.9 实现 undo action（创建 undo record，设置 is_undone，重建状态）
- [x] 6.10 实现事务内统一执行（action log + events + segments + state）
- [x] 6.11 实现录制停止自动关闭 open 区间（inferred 状态）
- [x] 6.12 实现时间戳校验（±5s 范围）
- [x] 6.13 编写 coding-actions 集成测试
- [x] 6.14 编写幂等性测试（相同 client_action_id）
- [x] 6.15 编写 undo 测试

## 7. CaptureSegment 最小投影

- [x] 7.1 创建 CaptureSegment 服务（创建/关闭/查询）
- [x] 7.2 实现层级关系管理（parent_segment_id）
- [x] 7.3 实现 inferred 状态和 close_reason 设置
- [x] 7.4 实现按 CaptureTake + segment_type 查询 API
- [x] 7.5 编写 CaptureSegment 单元测试

## 8. 前端 LiveCodingState 与 FIFO Outbox

- [x] 8.1 实现 LiveCodingState 类型定义
- [x] 8.2 实现 optimistic update reducer
- [x] 8.3 实现 server confirmed reducer（以后端返回为准）
- [x] 8.4 实现 server rejected reducer（409 回滚，不自动重试）
- [x] 8.5 实现 localStorage Outbox 存储
- [x] 8.6 实现单路 FIFO 发送队列（每 Take 一个）
- [x] 8.7 实现 ~400ms 按钮 debounce（误双击抑制）
- [x] 8.8 实现序列号顺序保证（前一条确认后才发送下一条）
- [x] 8.9 实现失败阻塞后续（blocked 状态）
- [x] 8.10 实现指数退避重试（1s → 2s → 4s → 8s，最多 5 次）
- [x] 8.11 实现重试保留原始 timestampMs
- [x] 8.12 实现刷新恢复（localStorage → 按 sequenceNumber 顺序重发）
- [x] 8.13 实现同步状态 UI 显示（pending/sending/synced/blocked/failed）
- [x] 8.14 更新 API 客户端类型（CaptureTake、coding-actions）
- [x] 8.15 编写 FIFO Outbox 单元测试

## 9. 前端 Live Coding 控制台与时间线

- [x] 9.1 实现 .capture-workspace 局部深色 CSS 变量
- [x] 9.2 实现按钮颜色编码（盘橙/局蓝/分绿/暂停黄/换边紫/非比赛灰/撤销红）
- [x] 9.3 实现当前结构显示（第X盘/第X局/第X分）
- [x] 9.4 实现事件打点按钮组件（盘开始/局开始/下一分/暂停/换边/非比赛/撤销）
- [x] 9.5 实现"下一分"一键推进按钮逻辑
- [x] 9.6 实现键盘快捷键支持（1-6、H、Backspace）
- [x] 9.7 实现快捷键仅在焦点不在 input/textarea/select 时响应
- [x] 9.8 实现按钮上显示快捷键标注
- [x] 9.9 实现只读多轨时间线组件（盘/局/分轨道 + 事件标记）
- [x] 9.10 实现播放头（当前录制时间指示器）
- [x] 9.11 实现 open 区间动态延伸动画
- [x] 9.12 实现时间线自动缩放（最近 N 分钟满视口）
- [x] 9.13 重构 CaptureConsolePage（统一单摄/双摄状态）
- [x] 9.14 实现双摄录制事件打点面板
- [x] 9.15 修复 QuickEventDef 的 note/payload_json 提交
- [x] 9.16 实现录制停止后显示区间列表（只读）
- [x] 9.17 编写控制台集成测试
- [x] 9.18 编写刷新恢复端到端测试
