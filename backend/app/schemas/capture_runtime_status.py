"""CaptureTake 运行状态响应 schema —— 录制工作台展示用。

设计依据：openspec/changes/redesign-live-recording-workspace-runtime-status
- 响应分为 storage、recording、tracks、sync、updated_at 五个区域。
- 字段使用明确的状态联合：ready / collecting / unavailable / error，
  以便前端区分"暂时没有测量结果"和"系统故障"。
- 不得把目标配置（target_fps、target_width 等）伪装成实测值。
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# 指标可用性状态联合：
# - ready        已有可读测量值
# - collecting   采集中，尚未产生可用结果（如刚启动的有效帧率）
# - unavailable  当前录制链路无法提供该指标（如缺少诊断）
# - error        读取或计算失败，附带可读错误信息
MetricAvailability = Literal["ready", "collecting", "unavailable", "error"]


class MetricValue(BaseModel):
    """通用指标值：每个指标独立表达可用性，避免单项失败掩盖整体。"""

    state: MetricAvailability
    value: float | None = None
    message: str | None = Field(
        default=None,
        description="error 或 unavailable 时的可读原因，便于前端诊断展示",
    )


class StorageCapacity(BaseModel):
    """存储容量快照，基于会话目录所在文件系统。"""

    state: MetricAvailability
    total_bytes: int | None = None
    used_bytes: int | None = None
    free_bytes: int | None = None
    message: str | None = None


class RecordingMetrics(BaseModel):
    """录制会话总体运行指标。

    target_* 字段是录制配置（来自会话/启动请求），不是实测值；
    实测指标（file_size_bytes、effective_fps、avg_bitrate_bps）使用 MetricValue
    明确区分可用性，不得用 target 值伪装为实测。
    """

    phase: str = Field(
        description="CaptureTake 当前阶段：starting/recording/completed/partial/failed/canceled 等",
    )
    started_at: datetime | None = None
    elapsed_ms: int | None = Field(
        default=None,
        description="当前录制已持续毫秒数（终态时为最后测得值）",
    )
    duration_ms: int | None = Field(
        default=None,
        description="终态时的最终时长（毫秒）；活跃状态下为空",
    )
    target_fps: float | None = Field(default=None, description="目标帧率配置，非实测")
    target_width: int | None = Field(default=None, description="目标分辨率宽度，非实测")
    target_height: int | None = Field(default=None, description="目标分辨率高度，非实测")
    file_size_bytes: MetricValue = Field(
        description="当前会话文件大小（汇总已完成和活动分片）",
    )
    effective_fps: MetricValue = Field(
        description="有效帧率（来自媒体诊断）；无测量时返回 collecting 或 unavailable",
    )
    avg_bitrate_bps: MetricValue = Field(
        description="后端测得的平均写入码率（bps），非编码器瞬时码率",
    )


class TrackRuntimeStatus(BaseModel):
    """单轨运行状态：每个 slot 独立汇报，便于前端解释局部异常。"""

    track_id: str
    slot: str = Field(description="cam_1 或 cam_2")
    camera_id: str
    phase: str = Field(
        description="轨道级阶段：starting/recording/completed/failed/interrupted 等",
    )
    file_size_bytes: MetricValue
    effective_fps: MetricValue
    error: str | None = None


class SyncRuntimeStatus(BaseModel):
    """双路同步与事件编码同步状态摘要。

    双摄模式下必填；单摄模式下可为 None。
    仅展示后端可观测的同步状态，不渲染虚构的同步状态。
    """

    dual_sync: MetricAvailability = Field(
        description="双路时间同步状态；单摄时为 unavailable",
    )
    dual_sync_quality: str | None = Field(
        default=None,
        description="同步质量：good / degraded / unknown",
    )
    event_sync: MetricAvailability = Field(
        description="事件编码 outbox 同步状态；无活跃 outbox 时为 ready",
    )
    message: str | None = None


class CaptureTakeRuntimeStatus(BaseModel):
    """CaptureTake 运行状态响应 —— 供前端工作台轮询消费。

    五个区域：storage / recording / tracks / sync / updated_at。
    前端不得因为单项指标缺失而隐藏整个工作台；应按 MetricValue.state
    独立展示 loading / 采集中 / 不可用 / 错误。
    """

    capture_take_id: str
    capture_mode: str = Field(description="single 或 dual")
    storage: StorageCapacity
    recording: RecordingMetrics
    tracks: list[TrackRuntimeStatus] = []
    sync: SyncRuntimeStatus | None = None
    updated_at: datetime = Field(description="本快照生成时间（UTC ISO 8601）")
