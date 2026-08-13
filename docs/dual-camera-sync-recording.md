# 双摄同步录制说明

## 概述

「拍动视析」支持通过 Web 控制台同时录制两路 RTSP 摄像头（主机位 + 副机位），由后端统一协调启动、停止和异常恢复，实现双摄同步采集。

## 前置条件

| 依赖 | 说明 |
|------|------|
| FFmpeg | 系统 PATH 中需有 `ffmpeg` 命令（用于拉流与录制） |
| OpenCV (`cv2`) | 用于提取首帧/尾帧截图（已包含在项目依赖中） |
| Python 3.11+ | 后端运行环境 |
| 两个摄像头 | 通过 RTSP 协议推流，地址可被后端所在机器访问 |

## 架构概要

```
                      ┌─────────────────────────────────┐
                      │         FastAPI Backend          │
                      │                                  │
  Camera A (RTSP) ───▶│  SyncRecorder                   │
                      │  ├─ FFmpeg proc A → cam_a_s1.ts │
  Camera B (RTSP) ───▶│  ├─ FFmpeg proc B → cam_b_s1.ts │
                      │  └─ 同步控制 → 分段重启          │
                      │                                  │
                      │  SyncRecordingService            │
                      │  ├─ 会话持久化 (JSON)            │
                      │  ├─ 主机位合并/登记              │
                      │  └─ 分析任务创建入口             │
                      └─────────────────────────────────┘
                                │
                                ▼
                      ┌─────────────────────────────────┐
                      │      React Frontend              │
                      │  CaptureConsolePage (dual mode)  │
                      │  ├─ 机位槽位选择                │
                      │  ├─ 短录测试                    │
                      │  ├─ 同步开始/停止               │
                      │  ├─ 分段状态展示                │
                      │  └─ 完成面板 → 创建分析         │
                      └─────────────────────────────────┘
```

## 核心设计

### 同步控制模型

采用师哥独立脚本 `ShouDong.py` 验证过的控制模型：

1. **同时启动**：主控制线程同时为两路摄像头各创建一个 FFmpeg 子进程
2. **分段录制**：每路输出为 `.ts` 分段文件，按 `{camera_id}_s{segment_index}.ts` 命名
3. **异常重启**：任一路 FFmpeg 异常退出后，控制线程终止另一路并同步进入下一分段
4. **统一停止**：用户点击停止后，终止所有进程，合并主机位分段并登记视频

### 会话存储

- 目录：`backend/data/sync-recordings/sessions/{session_id}.json`
- 测试输出：`backend/data/sync-recordings/tests/{timestamp}/`
- 录制输出：`backend/data/sync-recordings/{date}/{session_id}/`

### API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/sync-recordings/start` | 开始同步录制 |
| POST | `/api/sync-recordings/{id}/stop` | 停止录制，返回分析可用性 |
| POST | `/api/sync-recordings/{id}/cancel` | 取消录制 |
| GET | `/api/sync-recordings` | 列表（支持 status/filed_session_id 过滤） |
| GET | `/api/sync-recordings/active` | 查询活跃会话 |
| GET | `/api/sync-recordings/{id}` | 单个会话详情 |
| POST | `/api/sync-recordings/test` | 短录测试（3-30秒） |
| DELETE | `/api/sync-recordings/{id}` | 删除终态会话 |

## 现场推荐流程

### 1. 登记摄像头
在「设备管理」中注册两个摄像头，填写 RTSP 地址。

### 2. 创建双摄 Field Session
在采集向导中选择「双摄」方案，创建 Field Session。

### 3. 分配机位
进入采集控制台后，为「主机位（底线高机位）」和「副机位（侧面机位）」分别选择摄像头。

### 4. 短录测试
点击「短录测试 (5秒)」验证：
- 两路 RTSP 均可达
- FFmpeg 能正常拉流并输出 .ts 文件
- 首帧/尾帧可正常提取

### 5. 开始同步录制
确认测试通过后，点击「开始同步录制」。录制中可查看：
- 录制时长
- 当前分段编号
- 已保存分段数
- 重启次数与最近错误

### 6. 停止录制
点击「停止录制」后系统：
1. 终止两路 FFmpeg 进程
2. 合并主机位 `.ts` 分段为 MP4
3. 登记主机位视频到 VideoService
4. 展示完成面板

### 7. 创建分析任务
在完成面板点击「创建分析任务」，主机位视频进入现有分析流程。

## 当前限制

### 不是帧级硬同步
两路 FFmpeg 同步启动可保证毫秒级同步精度，但不是帧级硬同步。多视角联合分析需要在后续版本中通过时间戳对齐来实现。

### 双视角联合分析不在范围内
本次 change 将双摄同步采集、录制级同步锚点和双摄分析前置检查串成一条流程。副机位视频作为 CaptureTake 的关联素材保存，双摄分析只消费当前 CaptureTake 的权威时间线资产。

## 同步锚点与分析前置

双摄 CaptureTake 的同步资产位于其 `timeline/` 目录：

```text
sync_anchor_draft.json
sync_anchors.v1.json
sync_calibration.json
sync_anchor_confirmation.json
sync_anchor_history/revision-*/
```

工作台从双摄分析向导的“素材检查”进入，首先读取服务端状态和草稿；草稿保存到 CaptureTake 后可在离开页面或更换浏览器后继续。首次发现旧浏览器 `localStorage` 草稿时，只显示一次“导入旧浏览器草稿”操作，导入成功后服务端草稿成为权威来源。

状态和含义如下：

| 状态 | 含义 | 默认门禁 |
| --- | --- | --- |
| `not_required` | 当前策略无需人工锚点，通常适用于单摄或明确允许降级的场景 | 允许分析 |
| `required` | 双摄素材可用，但没有可复用的人工确认 | 需要开始标注 |
| `draft` | 已保存部分锚点，尚未完成服务端确认 | 需要继续标注 |
| `confirmed` | `manual_anchors` 与当前素材 provenance 匹配，拟合质量和覆盖率通过 | 允许复用 |
| `auto_degraded` | 只有 `auto_degraded_from_recording_timing` 估算，不代表人工确认 | 普通模式可按策略允许，`joint_tracking_v2` 需人工确认 |
| `invalidated` | 已确认结果与当前 registered video、camera identity 或 PTS sidecar 不匹配 | 需要重新标注 |

确认至少需要 3 组跨越素材时间范围的共同事件。服务端重新验证 camera identity、source PTS、覆盖率和 residual，并以同一 revision 原子发布 anchors、calibration、confirmation metadata。JSON 导出保留给诊断和 CLI 互操作使用，不是完成确认的必要步骤。

每次创建双摄 AnalysisJob 都重新执行 preflight。后续分析只记录 `syncCalibrationRevision` 引用，不复制锚点内容；同一 CaptureTake 的新分析、重试、分析窗口或算法配置变化不会使确认失效。若 registered video 或 timing sidecar 被替换，状态会变为 `invalidated`，旧 revision 仍保留在 `sync_anchor_history` 中，但不会再被当前分析使用。

分析向导进入 A 机位球场标定前执行一次前端门禁，点击“开始双摄协同分析”时后端再执行一次。若页面打开后素材发生变化，创建接口返回结构化 `multiview_preflight_failed` 错误且不落盘 Parent/child 部分任务；用户回到素材检查后可从同一工作台继续处理草稿。

### `.ts` 分段格式
原始录制输出为 `.ts` 分段文件（使用 `-c copy -f mpegts`），优点是低开销、适合 RTSP 原始流保存。停止时自动合并主机位分段为 MP4。

### 不支持三路及以上
当前设计固定为两路（primary + secondary），如需扩展需修改模型和前端 UI。

## 测试

```bash
# 运行单元测试（不依赖硬件）
cd backend && PYTHONPATH=. pytest tests/test_sync_recording.py -v -k "not Integration"

# 运行集成测试（需要 FFmpeg + 真实 RTSP 流）
cd backend && PYTHONPATH=. pytest tests/test_sync_recording.py -v -k "Integration"
```
