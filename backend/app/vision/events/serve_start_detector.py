"""上下文发球时刻候选检测器（Serve Start Detector）。

本模块的目标：在一场匹克球比赛视频里，自动找出"运动员发球的那一刻"，
并给出每个候选时刻的"证据分数"和"判定理由"，供前端展示、剪辑定位和研发调试使用。

所谓"上下文发球检测"，是指它不是靠识别球拍挥动这一单一动作，
而是综合判断一整套上下文线索：

  1. 站位：运动员是否站在己方底线附近（发球员通常站在底线后）；
  2. 静止：发球前身体是否有一段低速/稳定的准备期；
  3. 局部运动峰值：发球瞬间手臂（手腕/肘部）或身体 ROI 出现速度峰值；
  4. 后续回合：发球后对手/双方是否进入来回对打状态；
  5. 接球方等待：发球前，对手是否处于低速等待状态。

检测支持多种"信号来源"（ServeSignal）：
  - tracking：人体检测框（YOLO 等得到的 bounding box）的运动；
  - pose：姿态关键点（手腕、肘部）的运动；
  - trajectory：球员在球场坐标系下的轨迹运动；
  - roi：对某个局部区域（ROI）计算的运动峰值。

注意：本模块在 MVP 阶段"暂不启用"（见同目录 __init__.py），
但代码逻辑是完整的，可作为后续回合/事件分析的参考实现。

本文件不依赖任何外部服务，纯算法；输出为标准 Pydantic 数据模型（见 app/schemas/events.py）。
"""

# ---------------------------------------------------------------------------
# 标准库导入
# ---------------------------------------------------------------------------
from __future__ import annotations  # 允许使用较新的类型注解写法（如 list[int]），兼容旧版本 Python

from collections import defaultdict  # 带默认值的字典，用于按 track_id 分组
from dataclasses import dataclass, field  # 数据类装饰器：用更简洁的方式定义"只装数据"的类
from math import hypot  # 计算两点间直线距离（勾股定理）
from typing import Any  # 任意类型，主要用于调试信息字典

# ---------------------------------------------------------------------------
# 本项目的内部模块导入
# ---------------------------------------------------------------------------
# 事件相关的数据模型（发球信号、候选事件、完整产物、覆盖度诊断、调试引用等）
from app.schemas.events import (
    ServeCoverageDiagnostics,  # 各信号源"覆盖度"诊断模型
    ServeDebugArtifactRefs,  # 调试产物（各种调试文件 URL）的引用
    ServeEventCandidate,  # 单个发球事件候选
    ServeEventsArtifact,  # 一次分析的完整发球事件产物
    ServeSignal,  # 信号来源类型（tracking/pose/trajectory/roi/video）
    ServeSignalScores,  # 各类信号的得分（0~1）
)

# 姿态相关数据模型（姿态叠加帧、姿态对象）
from app.schemas.pose import PoseOverlayFrame

# 追踪相关数据模型（球员轨迹产物、轨迹采样点、追踪结果）
from app.schemas.tracking import PlayerTrajectoryArtifact, PlayerTrajectorySample, TrackingResult

# 球场单位换算工具（英尺↔米、标准球场尺寸）
from app.vision.courtvision_calibration_engine.court_units import (
    court_dimensions_for_unit,  # 根据单位返回球场 (宽, 长)
    feet_value_for_unit,  # 把"英尺值"换算成目标单位下的值
    normalize_court_unit,  # 把各种单位写法统一成 "m" / "ft" / None
)

# 共享上肢证据模块（腕/肘关键点索引与运动强度，与击球归属共用）
from app.vision.pickleball_game_analysis.upper_limb_evidence import upper_limb_motion_by_track


@dataclass(frozen=True)
class ServeStartDetectorConfig:
    """
    检测器超参数配置（全部带默认值，可整体调优）。

    这些数值决定了"多接近底线才算发球位""静止窗口多长""速度阈值多少"等判据。
    frozen=True 表示这个配置对象创建后不可修改，保证检测过程参数稳定。
    """

    min_gap_seconds: float = 6.0  # 两个候选事件之间的最小时间间隔（秒），用于去重
    pre_roll_seconds: float = 1.5  # 事件发生前多少秒作为"跳转/定位"时间点
    min_confidence: float = 0.35  # 候选事件的最低置信度门槛
    baseline_margin_ft: float = 6.0  # 底线判定容差（英尺）：距底线多近才算"在底线附近"
    pre_still_window_seconds: float = 1.5  # 发球前"静止期"观察窗口长度（秒）
    pre_still_gap_seconds: float = 0.2  # 静止窗口与发球时刻之间的间隔（秒），避免把动作本身算进静止
    post_rally_window_seconds: float = 3.0  # 发球后"回合"观察窗口长度（秒）
    still_speed_threshold: float = 0.8  # 判定"静止"的速度阈值（单位/秒以下算静止）
    rally_speed_threshold: float = 0.9  # 判定"进入回合"的速度阈值（单位/秒以上算活跃）
    arm_speed_peak_threshold: float = 120.0  # 手臂动作峰值阈值（用于把 pose 运动归一到 0~1）
    roi_speed_peak_threshold: float = 30.0  # ROI/轨迹运动峰值阈值（用于归一到 0~1）
    pose_smooth_window_frames: int = 5  # 姿态运动平滑的窗口帧数（取前后各半做滑动平均）
    clip_pre_seconds: float = 2.0  # 候选事件片段（clip）开始前时长（秒）
    clip_post_seconds: float = 4.0  # 候选事件片段开始后时长（秒）


@dataclass
class ServeDetectionDebug:
    """
    调试信息收集器（不参与正式判定，仅供研发诊断）。

    每次 detect() 调用都会重置，并把"候选""被拒样本""评分序列"等记录下来，
    方便排查为什么某些时刻没被识别为发球。
    """

    candidates: list[dict[str, Any]] = field(default_factory=list)  # 通过筛选的候选样本明细
    rejected: list[dict[str, Any]] = field(default_factory=list)  # 被拒样本明细（最多保留 200 条）
    score_series: list[dict[str, Any]] = field(default_factory=list)  # 每个采样点的各信号评分序列
    rejected_buckets: list[dict[str, Any]] = field(default_factory=list)  # 被拒样本按时间分桶统计
    coverage: dict[str, Any] = field(default_factory=dict)  # 覆盖度诊断（转 dict 形式）
    thresholds: dict[str, Any] = field(default_factory=dict)  # 本次使用的阈值快照
    debug_artifacts: ServeDebugArtifactRefs | None = None  # 调试产物文件引用


@dataclass(frozen=True)
class _CourtContext:
    """
    球场上下文（内部使用）：把检测所需的球场几何信息打包。

    一旦确定球场单位，就把"宽、长、底线容差"统一成该单位下的值，
    后续所有距离比较都基于这个对象，避免反复换算。
    """

    unit: str  # 单位："m" 或 "ft"
    width: float  # 球场宽度
    length: float  # 球场长度
    baseline_margin: float  # 底线判定容差（与 unit 同单位）


@dataclass
class _CandidateDraft:
    """
    候选事件草稿（内部使用）：在正式生成 ServeEventCandidate 之前的中间对象。

    相比最终对象，它多带 reason / source_signals / detection_mode 等辅助字段，
    便于打分、记录调试信息；最终通过 _candidate() 转成对外模型。
    """

    sample: PlayerTrajectorySample  # 触发该候选的轨迹采样点
    confidence: float  # 综合置信度
    reason: str  # 人类可读的判定理由
    source_signals: list[ServeSignal]  # 本次判定用到的信号来源
    detection_mode: str  # 主检测模式：pose / roi / trajectory
    signals: ServeSignalScores  # 各信号得分明细


class ServeStartDetector:
    """发球时刻候选检测器主类：对外暴露 detect()，内部是一整套打分式上下文检测逻辑。"""

    # 检测器版本号：写入产物，便于前端/调试区分不同算法版本
    version = "serve-moment-context-v1"

    def __init__(self, config: ServeStartDetectorConfig | None = None) -> None:
        """
        初始化检测器。

        参数:
            config: 可选的配置对象；为 None 时使用默认 ServeStartDetectorConfig。
        """
        self.config = config or ServeStartDetectorConfig()
        self.last_debug = ServeDetectionDebug()  # 初始化空的调试信息（每次 detect 会重置）

    def detect(
        self,
        *,
        job_id: str,
        video_id: str | None,
        tracking: TrackingResult | None = None,
        player_trajectories: PlayerTrajectoryArtifact | None = None,
        pose_frames: list[PoseOverlayFrame] | None = None,
        debug_artifacts: ServeDebugArtifactRefs | None = None,
    ) -> ServeEventsArtifact:
        """
        主入口：对一次分析作业做发球时刻检测，返回完整产物 ServeEventsArtifact。

        参数（均为关键字参数，避免传参顺序出错）:
            job_id:            作业 ID（写入产物，便于追溯）
            video_id:          视频 ID（可空）
            tracking:          人体追踪结果（含每帧检测框、fps、帧数等）
            player_trajectories: 球员在球场坐标系下的轨迹产物（最理想的输入）
            pose_frames:       姿态叠加帧（含手腕/肘部关键点）
            debug_artifacts:   调试产物文件引用（可空）

        返回:
            ServeEventsArtifact，其中 status 取值：
              - "unavailable"：缺少关键输入，无法检测
              - "available"：找到候选，且至少一个是 pose 模式
              - "partial"：找到候选，但信息量不足（如只有 tracking 模式）
              - "no_candidates"：检测跑完但没有任何达到阈值的候选
        """

        # 每次检测重置调试信息，并把外部传入的调试产物引用挂上
        self.last_debug = ServeDetectionDebug(debug_artifacts=debug_artifacts)

        # 先算出视频时长（秒），供后续裁剪边界、覆盖度诊断使用
        duration_seconds = self._duration_seconds(tracking)

        # 情况 1：完全没有可用 tracking 帧 → 直接返回 unavailable
        if not tracking or tracking.processed_frame_count == 0:
            coverage = self._build_coverage(
                tracking=tracking,
                player_trajectories=player_trajectories,
                pose_frames=pose_frames or [],
                events=[],
                duration_seconds=duration_seconds,
            )
            return self._artifact(
                job_id=job_id,
                video_id=video_id,
                status="unavailable",
                detail="缺少可用 tracking 帧，无法识别发球时刻候选",
                tracking=tracking,
                duration_seconds=duration_seconds,
                coverage=coverage,
            )

        # 按球员分组提取轨迹采样点（仅保留非插值点，并按时间排序）
        samples_by_player = self._trajectory_samples(player_trajectories)
        # 解析球场上下文（单位、尺寸、底线容差）；若无法识别则返回 None
        court_context = self._court_context(player_trajectories)

        # 情况 2：有轨迹数据，但球场单位无法识别 → 无法安全应用底线阈值，返回 unavailable
        if samples_by_player and court_context is None:
            coverage = self._build_coverage(
                tracking=tracking,
                player_trajectories=player_trajectories,
                pose_frames=pose_frames or [],
                events=[],
                duration_seconds=duration_seconds,
            )
            return self._artifact(
                job_id=job_id,
                video_id=video_id,
                status="unavailable",
                detail="缺少或无法识别 court_unit，无法安全应用底线阈值",
                tracking=tracking,
                duration_seconds=duration_seconds,
                debug_artifacts=debug_artifacts,
                coverage=coverage,
            )

        # 预计算每个 track 的姿态运动（手腕/肘部速度），用于 pose 信号打分
        pose_by_track = upper_limb_motion_by_track(
            pose_frames or [],
            smooth_window_frames=self.config.pose_smooth_window_frames,
        )

        # 情况 3（主路径）：既有轨迹数据，又能识别球场单位 → 走"上下文打分"检测
        if samples_by_player and court_context is not None:
            # 3a. 对所有轨迹采样点打分，生成候选草稿
            drafts = self._drafts_from_context(samples_by_player, court_context, pose_by_track)
            # 3b. 把草稿转成正式候选事件，并按置信度/时间做去重
            context_events = self._dedupe(
                [self._candidate(index + 1, draft, duration_seconds) for index, draft in enumerate(drafts)]
            )
            fallback_events = []
            # 3c. 若轨迹在中途就中断了（比 tracking 早很多结束），降级用 tracking/pose 信号补一段候选
            if self._trajectory_ends_before_tracking(player_trajectories, tracking):
                fallback_events = self._events_from_tracking_frames(
                    tracking.overlay_frames,
                    pose_by_track=pose_by_track,
                    after_seconds=self._trajectory_last_timestamp(player_trajectories),
                    reason_prefix="player trajectory 提前中断，已降级使用 tracking/pose 信号：",
                )
            # 3d. 合并主路径候选与降级候选，再次去重
            events = self._dedupe([*context_events, *fallback_events])
            # 3e. 决定整体检测模式（优先 pose → roi → tracking → trajectory）
            detection_mode = self._artifact_detection_mode(events)
            # 3f. 根据是否有候选、是否含 pose 模式，确定最终状态
            status = (
                "available"
                if events and any(event.detection_mode == "pose" for event in events)
                else "partial"
                if events
                else "no_candidates"
            )
            # 3g. 构建覆盖度诊断
            coverage = self._build_coverage(
                tracking=tracking,
                player_trajectories=player_trajectories,
                pose_frames=pose_frames or [],
                events=events,
                duration_seconds=duration_seconds,
            )
            detail = (
                f"已基于底线站位、发球前静止、局部运动峰值和后续回合状态识别 {len(events)} 个发球时刻候选"
                if events
                else "上下文发球检测已运行，但没有达到阈值的发球时刻候选"
            )
            if coverage.warnings:
                detail = f"{detail}；覆盖诊断：{coverage.warnings[0]}"
            return self._artifact(
                job_id=job_id,
                video_id=video_id,
                status=status,
                detail=detail,
                tracking=tracking,
                duration_seconds=duration_seconds,
                events=events,
                detection_mode=detection_mode,
                available_signals=self._available_signals(events, pose_available=bool(pose_by_track)),
                debug_artifacts=debug_artifacts,
                coverage=coverage,
            )

        # 情况 4：没有可用球员轨迹，但有 tracking 帧 → 仅用人体框动态做"低信息量"检测
        events = self._events_from_tracking_frames(tracking.overlay_frames, pose_by_track=pose_by_track)
        coverage = self._build_coverage(
            tracking=tracking,
            player_trajectories=player_trajectories,
            pose_frames=pose_frames or [],
            events=events,
            duration_seconds=duration_seconds,
        )
        # 找到了候选：标记为 partial（信息量较低）
        if events:
            return self._artifact(
                job_id=job_id,
                video_id=video_id,
                status="partial",
                detail=f"缺少可用球员轨迹，已基于人体框动态识别 {len(events)} 个低信息量发球时刻候选",
                tracking=tracking,
                duration_seconds=duration_seconds,
                events=events,
                detection_mode="tracking",
                available_signals=["tracking"] + (["pose"] if pose_by_track else []),
                debug_artifacts=debug_artifacts,
                coverage=coverage,
            )

        # 情况 5：连 tracking 都没给出任何候选 → no_candidates
        return self._artifact(
            job_id=job_id,
            video_id=video_id,
            status="no_candidates",
            detail="上下文发球检测已运行，但没有达到阈值的发球时刻候选",
            tracking=tracking,
            duration_seconds=duration_seconds,
            debug_artifacts=debug_artifacts,
            coverage=coverage,
        )

    def unavailable(
        self,
        *,
        job_id: str,
        video_id: str | None,
        detail: str,
    ) -> ServeEventsArtifact:
        """
        便捷方法：当上游已经确定无法检测时，直接构造一个 unavailable 产物，
        避免调用方重复写 _artifact 的参数。
        """
        return self._artifact(job_id=job_id, video_id=video_id, status="unavailable", detail=detail)

    def _drafts_from_context(
        self,
        samples_by_player: dict[str, list[PlayerTrajectorySample]],
        court: _CourtContext,
        pose_by_track: dict[str, dict[int, float]],
    ) -> list[_CandidateDraft]:
        """
        核心打分逻辑（主路径）：遍历每个球员、每个轨迹采样点，综合多路信号打分，
        对达到门槛的采样点生成"候选草稿"。

        打分维度（每项 0~1）：
          - baseline_position_score：是否站在底线附近
          - pre_stillness_score：    发球前是否静止
          - arm_motion_peak_score：  手臂（pose）运动峰值
          - roi_motion_peak_score：  轨迹/ROI 运动峰值
          - rally_after_score：      发球后是否进入回合
          - receiver_waiting_score： 接球方是否在等待

        被任意门槛筛掉的采样点会记入调试"被拒"列表（含拒绝原因）。
        """

        drafts: list[_CandidateDraft] = []
        for player_id, samples in samples_by_player.items():
            # 采样点太少（<3）无法判断静止/运动窗口，直接跳过该球员
            if len(samples) < 3:
                continue
            for index, sample in enumerate(samples):
                # 维度 1：底线站位分；若不在底线附近（得分<=0）则拒绝
                baseline_score = self._baseline_position_score(sample, court)
                if baseline_score <= 0:
                    self._record_rejection(sample, "not_near_baseline", baseline_position_score=baseline_score)
                    continue
                # 维度 2：发球前静止分；低于 0.55 视为没有充分准备期，拒绝
                pre_stillness_score = self._pre_stillness_score(samples, index)
                if pre_stillness_score < 0.55:
                    self._record_rejection(
                        sample,
                        "missing_pre_serve_stillness",
                        baseline_position_score=baseline_score,
                        pre_stillness_score=pre_stillness_score,
                    )
                    continue
                # 维度 3：局部运动峰值（取手臂 pose 与轨迹 roi 二者较高者）
                arm_score = self._pose_peak_score(sample, pose_by_track)
                roi_score = self._trajectory_peak_score(samples, index)
                # 维度 4：发球后回合分（对手/双方是否进入来回）
                rally_score = self._rally_after_score(samples_by_player, sample.timestamp_seconds)
                # 维度 5：接球方等待分（发球前对手是否低速等待）
                receiver_score = self._receiver_waiting_score(samples_by_player, sample.timestamp_seconds, player_id)
                peak_score = max(arm_score, roi_score)
                # 没有任何局部运动峰值（<0.35）则拒绝
                if peak_score < 0.35:
                    self._record_rejection(
                        sample,
                        "no_local_motion_peak",
                        baseline_position_score=baseline_score,
                        pre_stillness_score=pre_stillness_score,
                        arm_motion_peak_score=arm_score,
                        roi_motion_peak_score=roi_score,
                    )
                    continue
                # 综合置信度：各维度加权求和，上限 0.96
                confidence = min(
                    0.96,
                    0.18
                    + baseline_score * 0.12
                    + pre_stillness_score * 0.18
                    + peak_score * 0.38
                    + rally_score * 0.18
                    + receiver_score * 0.06,
                )
                # 若发球后没有进入回合（rally_score<=0），说明可能只是普通移动，压低置信度上限
                if rally_score <= 0:
                    confidence = min(confidence, 0.68)
                elif rally_score < 0.5:
                    confidence = min(confidence, 0.78)
                # 置信度未达最低门槛则拒绝
                if confidence < self.config.min_confidence:
                    self._record_rejection(sample, "low_confidence", confidence=confidence)
                    continue
                # 决定主检测模式：优先 pose（手臂峰值更高且>0），其次 roi，否则 trajectory
                detection_mode = (
                    "pose" if arm_score >= roi_score and arm_score > 0 else "roi" if roi_score > 0 else "trajectory"
                )
                # 打包各信号得分（保留 3 位小数）
                signals = ServeSignalScores(
                    baseline_position_score=round(baseline_score, 3),
                    pre_stillness_score=round(pre_stillness_score, 3),
                    arm_motion_peak_score=round(arm_score, 3),
                    roi_motion_peak_score=round(roi_score, 3),
                    rally_after_score=round(rally_score, 3),
                    receiver_waiting_score=round(receiver_score, 3),
                )
                # 记录本次判定用到的信号来源
                source_signals: list[ServeSignal] = ["trajectory", "tracking"]
                if arm_score > 0:
                    source_signals.append("pose")
                if detection_mode == "roi":
                    source_signals.append("roi")
                # 生成人类可读的判定理由
                reason = self._candidate_reason(player_id, detection_mode, signals)
                draft = _CandidateDraft(
                    sample=sample,
                    confidence=confidence,
                    reason=reason,
                    source_signals=source_signals,
                    detection_mode=detection_mode,
                    signals=signals,
                )
                drafts.append(draft)
                self._record_candidate(draft)
                # 把每个采样点的评分写入调试序列，便于后续覆盖度/分桶分析
                self.last_debug.score_series.append(
                    {
                        "timestamp_seconds": round(sample.timestamp_seconds, 3),
                        "frame_index": sample.frame_index,
                        "player_id": player_id,
                        "baseline_position_score": signals.baseline_position_score,
                        "pre_stillness_score": signals.pre_stillness_score,
                        "arm_motion_peak_score": signals.arm_motion_peak_score,
                        "roi_motion_peak_score": signals.roi_motion_peak_score,
                        "rally_after_score": signals.rally_after_score,
                        "receiver_waiting_score": signals.receiver_waiting_score,
                        "confidence": round(confidence, 3),
                    }
                )
        # 记录本次使用的阈值快照，供调试查看
        self.last_debug.thresholds = {
            "baseline_margin": court.baseline_margin,
            "court_unit": court.unit,
            "court_width": court.width,
            "court_length": court.length,
            "pre_still_window_seconds": self.config.pre_still_window_seconds,
            "post_rally_window_seconds": self.config.post_rally_window_seconds,
            "min_gap_seconds": self.config.min_gap_seconds,
        }
        return drafts

    def _candidate(self, index: int, draft: _CandidateDraft, duration_seconds: float | None) -> ServeEventCandidate:
        """
        把一个候选草稿转成正式对外模型 ServeEventCandidate。

        会围绕事件发生时刻，计算用于"跳转/剪辑"的时间窗口：
          - seek_time_seconds：跳转到该候选的推荐时间点（事件前 pre_roll 秒）
          - start_time_seconds / end_time_seconds：候选片段（clip）的起止时间
        """
        sample = draft.sample
        timestamp = max(0.0, float(sample.timestamp_seconds))
        start_time = max(0.0, timestamp - self.config.clip_pre_seconds)
        end_time = timestamp + self.config.clip_post_seconds
        # 片段结束时间不能超过视频总时长
        if duration_seconds is not None:
            end_time = min(duration_seconds, end_time)
        return ServeEventCandidate(
            id=f"serve-{index:03d}",
            timestamp_seconds=timestamp,
            frame_index=sample.frame_index,
            confidence=round(draft.confidence, 3),
            seek_time_seconds=max(0.0, timestamp - self.config.pre_roll_seconds),
            start_time_seconds=start_time,
            end_time_seconds=max(timestamp, end_time),
            reason=draft.reason,
            source_signals=draft.source_signals,
            track_id=str(sample.track_id) if sample.track_id is not None else None,
            player_id=sample.player_id,
            detection_mode=draft.detection_mode,  # type: ignore[arg-type]
            context_state="ready_to_serve",
            court_position=[round(sample.court_x, 4), round(sample.court_y, 4)],
            court_unit=sample.court_unit,
            signals=draft.signals,
        )

    def _events_from_tracking_frames(
        self,
        frames,
        *,
        pose_by_track: dict[str, dict[int, float]],
        after_seconds: float | None = None,
        reason_prefix: str = "",
    ) -> list[ServeEventCandidate]:
        """
        降级/备用检测路径：没有可用球员轨迹时，直接用人体检测框（tracking）动态找候选。

        思路：对每个 track，按时间排列其检测框中心点；若某个点"前一点低速（静止）、
        后一点高速（爆发）"，且未伴随过高速度或足够 pose 动作，则视为一次发球候选。

        参数:
            frames:        tracking 的叠加帧列表
            pose_by_track: 每个 track 的姿态运动（用于把部分候选升级为 pose 模式）
            after_seconds: 可选，只处理该时间之后的帧（用于轨迹中断后的补充检测）
            reason_prefix: 拒绝/理由文案前缀（降级场景会说明"已降级使用 tracking/pose 信号"）
        """
        by_track = defaultdict(list)
        # 先把每帧里每个检测框的中心点收集到对应 track 下
        for frame in frames:
            # 若指定了 after_seconds，则只处理该时刻之后的帧
            if after_seconds is not None and frame.timestamp_seconds <= after_seconds:
                continue
            for detection in frame.detections:
                if detection.track_id is None:
                    continue
                x1, y1, x2, y2 = detection.bbox
                by_track[detection.track_id].append(
                    (frame.frame_index, frame.timestamp_seconds, (x1 + x2) / 2, (y1 + y2) / 2, detection.player_id)
                )

        candidates: list[ServeEventCandidate] = []
        for track_id, points in by_track.items():
            points.sort(key=lambda item: item[1])
            # 采样点太少无法判断静止/爆发窗口，跳过
            if len(points) < 3:
                continue
            # 用连续三点 (前、中、后) 做一次"静止→爆发"判断
            for previous, current, next_point in zip(points, points[1:], points[2:], strict=False):
                # previous 与 current 之间的速度（静止期）
                still_speed = self._point_speed(previous, current)
                # current 与 next 之间的速度（爆发期）
                burst_speed = self._point_speed(current, next_point)
                # 该帧对应的姿态运动（若有）
                pose_motion = pose_by_track.get(str(track_id), {}).get(current[0], 0.0)
                pose_score = self._clamp01(pose_motion / max(1.0, self.config.arm_speed_peak_threshold))
                # 排除：静止期速度过大（一直在动，不是发球准备）；
                # 或爆发期速度过小且姿态动作也不明显（没有发球动作）
                if still_speed > 25.0 or (burst_speed < self.config.roi_speed_peak_threshold and pose_score < 0.35):
                    continue
                # 把爆发速度归一到 0~1 作为 roi 分
                roi_score = self._clamp01(burst_speed / max(1.0, self.config.roi_speed_peak_threshold * 2))
                # 主检测模式：pose 动作足够强则标为 pose，否则 tracking
                detection_mode = "pose" if pose_score >= roi_score and pose_score >= 0.35 else "tracking"
                # 综合置信度（上限 0.68，低于上下文主路径）
                confidence = min(0.68, 0.34 + max(roi_score, pose_score) * 0.26 + (0.08 if pose_by_track else 0))
                source_signals: list[ServeSignal] = ["tracking"]
                if detection_mode == "pose":
                    source_signals.append("pose")
                candidates.append(
                    ServeEventCandidate(
                        id=f"serve-{len(candidates) + 1:03d}",
                        timestamp_seconds=current[1],
                        frame_index=current[0],
                        confidence=round(confidence, 3),
                        seek_time_seconds=max(0.0, current[1] - self.config.pre_roll_seconds),
                        start_time_seconds=max(0.0, current[1] - self.config.clip_pre_seconds),
                        end_time_seconds=current[1] + self.config.clip_post_seconds,
                        reason=f"{reason_prefix}Track {track_id} 人体框短暂稳定后出现局部运动峰值",
                        source_signals=source_signals,
                        track_id=str(track_id),
                        player_id=current[4],
                        detection_mode=detection_mode,
                        context_state="candidate",
                        signals=ServeSignalScores(
                            arm_motion_peak_score=round(pose_score, 3) if detection_mode == "pose" else None,
                            roi_motion_peak_score=round(roi_score, 3),
                        ),
                    )
                )
        # 同一条 track 内、或不同 track 间距离过近的候选要去重
        return self._dedupe(candidates)

    def _dedupe(self, candidates: list[ServeEventCandidate]) -> list[ServeEventCandidate]:
        """
        候选去重：把时间上太接近（间隔 < min_gap_seconds）的候选合并，只保留更可信的那个。

        步骤：
          1. 先按"置信度降序、时间升序"排序，让高置信度候选排在前面；
          2. 逐个加入结果，若与结果中任一候选间隔过近则跳过；
          3. 最后按时间重新排序，并重新分配连续 id（serve-001, serve-002, ...）。
        """
        result: list[ServeEventCandidate] = []
        for candidate in sorted(candidates, key=lambda item: (-item.confidence, item.timestamp_seconds)):
            if any(
                abs(candidate.timestamp_seconds - existing.timestamp_seconds) < self.config.min_gap_seconds
                for existing in result
            ):
                continue
            result.append(candidate)
        result.sort(key=lambda item: item.timestamp_seconds)
        return [
            candidate.model_copy(update={"id": f"serve-{index:03d}"}) for index, candidate in enumerate(result, start=1)
        ]

    def _court_context(self, player_trajectories: PlayerTrajectoryArtifact | None) -> _CourtContext | None:
        """
        从轨迹产物里解析球场上下文（单位、尺寸、底线容差）。

        返回 None 表示无法安全识别单位（此时调用方应放弃主路径检测）。
        """
        if player_trajectories is None:
            return None
        unit = normalize_court_unit(player_trajectories.court.court_unit)
        dimensions = court_dimensions_for_unit(unit)
        margin = feet_value_for_unit(self.config.baseline_margin_ft, unit)
        if unit is None or dimensions is None or margin is None:
            return None
        return _CourtContext(unit=unit, width=dimensions[0], length=dimensions[1], baseline_margin=margin)

    @staticmethod
    def _trajectory_samples(
        player_trajectories: PlayerTrajectoryArtifact | None,
    ) -> dict[str, list[PlayerTrajectorySample]]:
        """
        把轨迹产物按球员分组，并过滤/排序：

          - 丢弃插值点（is_interpolated=True，这些点是算法补的，不代表真实观测）；
          - 每个球员的点按时间升序排列。

        返回 dict：player_id -> 排序后的采样点列表；空轨迹的球员会被忽略。
        """
        if player_trajectories is None:
            return {}
        return {
            player_id: sorted(
                [sample for sample in samples if not sample.is_interpolated],
                key=lambda sample: sample.timestamp_seconds,
            )
            for player_id, samples in player_trajectories.players.items()
            if samples
        }

    def _baseline_position_score(self, sample: PlayerTrajectorySample, court: _CourtContext) -> float:
        """
        维度 1 评分：底线站位分（0~1）。

        计算采样点到"最近一条底线"的距离（球场 y 轴两端即两条底线），
        距离越近分越高；超出底线容差则直接记 0（不在发球位）。
        """
        distance = min(abs(sample.court_y), abs(court.length - sample.court_y))
        if distance > court.baseline_margin:
            return 0.0
        return self._clamp01(1.0 - distance / max(0.001, court.baseline_margin))

    def _pre_stillness_score(self, samples: list[PlayerTrajectorySample], index: int) -> float:
        """
        维度 2 评分：发球前静止分（0~1）。

        取当前采样点之前一个"静止观察窗口"（pre_still_window_seconds），
        但用 pre_still_gap_seconds 与发球时刻隔开（避免把发球动作本身算进静止）。
        计算该窗口内相邻点的平均速度，越慢越接近 1。
        若窗口内点太少则回退到前 2 个点，仍不够则返回 0。
        """
        current = samples[index]
        start = current.timestamp_seconds - self.config.pre_still_window_seconds
        end = current.timestamp_seconds - self.config.pre_still_gap_seconds
        window = [sample for sample in samples[: index + 1] if start <= sample.timestamp_seconds <= end]
        if len(window) < 2 and index >= 2:
            window = samples[max(0, index - 2) : index]
        if len(window) < 2:
            return 0.0
        speeds = [self._sample_speed(a, b) for a, b in zip(window, window[1:], strict=False)]
        if not speeds:
            return 0.0
        mean_speed = sum(speeds) / len(speeds)
        return self._clamp01(1.0 - mean_speed / max(0.001, self.config.still_speed_threshold))

    def _trajectory_peak_score(self, samples: list[PlayerTrajectorySample], index: int) -> float:
        """
        维度 3（轨迹侧）评分：当前采样点与其下一个点之间的瞬时速度峰值（0~1）。

        把速度除以阈值（rally_speed_threshold * 2.5）后归一到 0~1。
        若是最后一个采样点（无后继）则返回 0。
        """
        if index >= len(samples) - 1:
            return 0.0
        speed = self._sample_speed(samples[index], samples[index + 1])
        return self._clamp01(speed / max(0.001, self.config.rally_speed_threshold * 2.5))

    def _rally_after_score(self, samples_by_player: dict[str, list[PlayerTrajectorySample]], timestamp: float) -> float:
        """
        维度 4 评分：发球后回合分（0~1）。

        观察发球时刻之后 post_rally_window_seconds 窗口内，有多少球员处于"活跃"（平均速度
        >= rally_speed_threshold）。活跃球员数 / 2 即得分（最多计 2 人）。
        用于区分"发球后进入对打"和"只是自己动了一下"。
        """
        active_players = 0
        for samples in samples_by_player.values():
            window = [
                sample
                for sample in samples
                if timestamp <= sample.timestamp_seconds <= timestamp + self.config.post_rally_window_seconds
            ]
            if len(window) < 2:
                continue
            speeds = [self._sample_speed(a, b) for a, b in zip(window, window[1:], strict=False)]
            if speeds and sum(speeds) / len(speeds) >= self.config.rally_speed_threshold:
                active_players += 1
        return self._clamp01(active_players / 2.0)

    def _receiver_waiting_score(
        self,
        samples_by_player: dict[str, list[PlayerTrajectorySample]],
        timestamp: float,
        server_player_id: str,
    ) -> float:
        """
        维度 5 评分：接球方等待分（0~1）。

        在发球时刻之前的静止窗口内，统计"非发球方"球员中有多少处于低速等待状态
        （平均速度 <= still_speed_threshold），占"被考察球员"的比例即为得分。
        若没有可考察的其他球员（如单打场景缺数据）则返回 0。
        """
        waiting = 0
        considered = 0
        start = timestamp - self.config.pre_still_window_seconds
        end = timestamp - self.config.pre_still_gap_seconds
        for player_id, samples in samples_by_player.items():
            if player_id == server_player_id:
                continue
            window = [sample for sample in samples if start <= sample.timestamp_seconds <= end]
            if len(window) < 2:
                continue
            considered += 1
            speeds = [self._sample_speed(a, b) for a, b in zip(window, window[1:], strict=False)]
            if speeds and sum(speeds) / len(speeds) <= self.config.still_speed_threshold:
                waiting += 1
        if considered == 0:
            return 0.0
        return self._clamp01(waiting / considered)

    def _pose_peak_score(self, sample: PlayerTrajectorySample, pose_by_track: dict[str, dict[int, float]]) -> float:
        """
        维度 3（姿态侧）评分：当前采样点对应帧的手臂（手腕/肘部）运动峰值（0~1）。

        从预计算的 pose_by_track 里取该 track 该帧的运动值，除以手臂阈值后归一到 0~1。
        若没有 track 或没有 pose 数据则返回 0。
        """
        if sample.track_id is None:
            return 0.0
        track_motion = pose_by_track.get(str(sample.track_id))
        if not track_motion:
            return 0.0
        raw = track_motion.get(sample.frame_index, 0.0)
        return self._clamp01(raw / max(1.0, self.config.arm_speed_peak_threshold))

    @staticmethod
    def _sample_speed(current: PlayerTrajectorySample, next_sample: PlayerTrajectorySample) -> float:
        """
        计算两个相邻轨迹采样点之间的平均速度（球场单位/秒）。

        用球场坐标 (court_x, court_y) 的直线距离除以时间差；时间差<=0 视为无效，返回 0。
        """
        dt = next_sample.timestamp_seconds - current.timestamp_seconds
        if dt <= 0:
            return 0.0
        return hypot(next_sample.court_x - current.court_x, next_sample.court_y - current.court_y) / dt

    @staticmethod
    def _point_speed(current, next_point) -> float:
        """
        与 _sample_speed 类似，但针对 tracking 中心的 (frame_index, timestamp, x, y) 元组。

        元组结构见 _events_from_tracking_frames：
          current / next_point = (frame_index, timestamp_seconds, center_x, center_y, player_id)
        """
        dt = next_point[1] - current[1]
        if dt <= 0:
            return 0.0
        return hypot(next_point[2] - current[2], next_point[3] - current[3]) / dt

    @staticmethod
    def _duration_seconds(tracking: TrackingResult | None) -> float | None:
        """
        计算视频时长（秒）：

          - 优先用 frame_count / fps（若有有效 fps 和帧数）；
          - 否则用最后一帧的时间戳作为时长；
          - 都没有则返回 None。
        """
        if tracking is None:
            return None
        if tracking.fps > 0 and tracking.frame_count > 0:
            return tracking.frame_count / tracking.fps
        timestamps = [frame.timestamp_seconds for frame in tracking.overlay_frames]
        return max(timestamps) if timestamps else None

    @staticmethod
    def _clamp01(value: float) -> float:
        """
        把任意数值夹到 [0, 1] 区间（所有"分数"都需在此范围）。
        """
        return min(1.0, max(0.0, float(value)))

    @staticmethod
    def _artifact_detection_mode(events: list[ServeEventCandidate]) -> str | None:
        """
        根据候选列表里的检测模式，确定整体产物的检测模式优先级：
          pose > roi > tracking > trajectory；没有任何候选则返回 None。
        """
        if any(event.detection_mode == "pose" for event in events):
            return "pose"
        if any(event.detection_mode == "roi" for event in events):
            return "roi"
        if any(event.detection_mode == "tracking" for event in events):
            return "tracking"
        if events:
            return "trajectory"
        return None

    @staticmethod
    def _available_signals(events: list[ServeEventCandidate], *, pose_available: bool) -> list[ServeSignal]:
        """
        汇总本次检测"实际用到了哪些信号来源"，保持顺序去重。

        基础为 trajectory + tracking；有 pose 数据则加 pose；有任何 roi 候选则加 roi。
        """
        signals: list[ServeSignal] = ["trajectory", "tracking"]
        if pose_available:
            signals.append("pose")
        if any(event.detection_mode == "roi" for event in events):
            signals.append("roi")
        return list(dict.fromkeys(signals))

    @staticmethod
    def _candidate_reason(player_id: str, detection_mode: str, signals: ServeSignalScores) -> str:
        """
        生成候选事件的人类可读理由文案。

        根据检测模式说明"峰值来自手腕/肘部"还是"ROI/轨迹局部运动"，
        并附上后续回合激活分，便于前端展示与调试阅读。
        """
        mode_label = "手腕/肘部峰值" if detection_mode == "pose" else "ROI/轨迹局部运动峰值"
        return (
            f"{player_id} 位于底线附近，发球前低速准备后出现{mode_label}，"
            f"后续回合激活分 {signals.rally_after_score or 0:.2f}"
        )

    def _record_candidate(self, draft: _CandidateDraft) -> None:
        """
        把通过筛选的候选草稿追加进调试信息（last_debug.candidates），供研发查看明细。
        """
        sample = draft.sample
        self.last_debug.candidates.append(
            {
                "timestamp_seconds": round(sample.timestamp_seconds, 3),
                "frame_index": sample.frame_index,
                "player_id": sample.player_id,
                "track_id": sample.track_id,
                "bbox": sample.bbox,
                "court_position": [sample.court_x, sample.court_y],
                "court_unit": sample.court_unit,
                "confidence": round(draft.confidence, 3),
                "detection_mode": draft.detection_mode,
                "reason": draft.reason,
                "signals": draft.signals.model_dump(mode="json"),
            }
        )

    def _record_rejection(self, sample: PlayerTrajectorySample, reason: str, **signals: Any) -> None:
        """
        记录被拒绝的采样点（含拒绝原因与当时各信号分数）。

        最多保留 200 条被拒记录（防止调试数据无限膨胀）。
        同时写入 score_series，并打上 rejected_reason 标记，便于后续分桶统计"为什么被拒"。
        """
        if len(self.last_debug.rejected) < 200:
            self.last_debug.rejected.append(
                {
                    "timestamp_seconds": round(sample.timestamp_seconds, 3),
                    "frame_index": sample.frame_index,
                    "player_id": sample.player_id,
                    "track_id": sample.track_id,
                    "court_position": [sample.court_x, sample.court_y],
                    "court_unit": sample.court_unit,
                    "reason": reason,
                    "signals": signals,
                }
            )
        self.last_debug.score_series.append(
            {
                "timestamp_seconds": round(sample.timestamp_seconds, 3),
                "frame_index": sample.frame_index,
                "player_id": sample.player_id,
                "baseline_position_score": signals.get("baseline_position_score"),
                "pre_stillness_score": signals.get("pre_stillness_score"),
                "arm_motion_peak_score": signals.get("arm_motion_peak_score"),
                "roi_motion_peak_score": signals.get("roi_motion_peak_score"),
                "rally_after_score": signals.get("rally_after_score"),
                "receiver_waiting_score": signals.get("receiver_waiting_score"),
                "rejected_reason": reason,
            }
        )

    def _artifact(
        self,
        *,
        job_id: str,
        video_id: str | None,
        status: str,
        detail: str,
        tracking: TrackingResult | None = None,
        duration_seconds: float | None = None,
        events: list[ServeEventCandidate] | None = None,
        detection_mode: str | None = None,
        available_signals: list[ServeSignal] | None = None,
        debug_artifacts: ServeDebugArtifactRefs | None = None,
        coverage: ServeCoverageDiagnostics | None = None,
    ) -> ServeEventsArtifact:
        """
        统一构造最终产物 ServeEventsArtifact 的工厂方法。

        从 tracking 里搬运 fps / 帧数 / 已处理帧数 / 帧步长等元信息，
        并填入状态、详情、检测器版本、事件列表、覆盖度诊断等。
        """
        return ServeEventsArtifact(
            job_id=job_id,
            video_id=video_id,
            status=status,  # type: ignore[arg-type]
            detail=detail,
            detector_version=self.version,
            duration_seconds=duration_seconds,
            fps=tracking.fps if tracking else 0.0,
            frame_count=tracking.frame_count if tracking else 0,
            processed_frame_count=tracking.processed_frame_count if tracking else 0,
            frame_stride=tracking.frame_stride if tracking else 1,
            detection_mode=detection_mode,  # type: ignore[arg-type]
            available_signals=available_signals or [],
            debug_artifacts=debug_artifacts,
            coverage=coverage,
            events=events or [],
        )

    def _build_coverage(
        self,
        *,
        tracking: TrackingResult | None,
        player_trajectories: PlayerTrajectoryArtifact | None,
        pose_frames: list[PoseOverlayFrame],
        events: list[ServeEventCandidate],
        duration_seconds: float | None,
    ) -> ServeCoverageDiagnostics:
        """
        构建"覆盖度诊断"：检查各信号源（tracking / pose / trajectory / 评分序列 / 候选）
        在时间轴上覆盖到了哪里、覆盖率如何，并给出警告（warnings）和缺口（gaps）。

        典型警告：
          - score_series_ends_before_source_video：评分序列没覆盖到视频后段
          - trajectory_ends_before_source_video：轨迹在中途就结束了
          - missing_player_trajectory：有 tracking 但没有球员轨迹
        """
        tracking_times = [frame.timestamp_seconds for frame in tracking.overlay_frames] if tracking else []
        pose_times = [frame.timestamp_seconds for frame in pose_frames]
        trajectory_times = [
            sample.timestamp_seconds
            for samples in (player_trajectories.players.values() if player_trajectories else [])
            for sample in samples
        ]
        score_times = [
            float(item["timestamp_seconds"])
            for item in self.last_debug.score_series
            if isinstance(item.get("timestamp_seconds"), (int, float))
        ]
        event_times = [event.timestamp_seconds for event in events]
        source_duration = duration_seconds
        last_score = max(score_times) if score_times else None
        last_tracking = max(tracking_times) if tracking_times else None
        last_trajectory = max(trajectory_times) if trajectory_times else None
        warnings: list[str] = []
        gaps: list[str] = []
        reference_end = source_duration or last_tracking
        # 评分序列若只覆盖到视频前 75% 以下，认为覆盖不足
        if reference_end and last_score is not None and last_score < reference_end * 0.75:
            warnings.append("score_series_ends_before_source_video")
            gaps.append("serve scoring did not cover late video")
        # 轨迹若在中途就结束，记录缺口
        if reference_end and last_trajectory is not None and last_trajectory < reference_end * 0.75:
            warnings.append("trajectory_ends_before_source_video")
            gaps.append("player trajectory ended while video/tracking continued")
        # 有 tracking 却没轨迹，单独告警
        if last_tracking is not None and last_trajectory is None:
            warnings.append("missing_player_trajectory")
            gaps.append("tracking exists but player trajectory is unavailable")
        coverage_ratio = (last_score / reference_end) if reference_end and last_score is not None else None
        coverage = ServeCoverageDiagnostics(
            source_duration_seconds=source_duration,
            tracking_first_timestamp_seconds=min(tracking_times) if tracking_times else None,
            tracking_last_timestamp_seconds=last_tracking,
            pose_first_timestamp_seconds=min(pose_times) if pose_times else None,
            pose_last_timestamp_seconds=max(pose_times) if pose_times else None,
            trajectory_first_timestamp_seconds=min(trajectory_times) if trajectory_times else None,
            trajectory_last_timestamp_seconds=last_trajectory,
            score_series_first_timestamp_seconds=min(score_times) if score_times else None,
            score_series_last_timestamp_seconds=last_score,
            score_series_count=len(score_times),
            candidate_first_timestamp_seconds=min(event_times) if event_times else None,
            candidate_last_timestamp_seconds=max(event_times) if event_times else None,
            candidate_count=len(events),
            coverage_ratio=coverage_ratio,
            warnings=warnings,
            gaps=gaps,
        )
        # 把覆盖度与被拒分桶写入调试信息
        self.last_debug.coverage = coverage.model_dump(mode="json")
        self.last_debug.rejected_buckets = self._rejected_buckets(source_duration or last_tracking)
        return coverage

    def _rejected_buckets(self, duration_seconds: float | None) -> list[dict[str, Any]]:
        """
        把"被拒采样点"按时间分桶（默认 12 桶）聚合统计，便于看出"在哪段时间被拒最多、因为什么"。

        每个桶记录：时间区间、样本数、各拒绝原因计数、各球员计数。
        若没有任何被拒样本，返回空列表。
        """
        rejected = [item for item in self.last_debug.score_series if item.get("rejected_reason")]
        if not rejected:
            return []
        bucket_count = 12
        if duration_seconds and duration_seconds > 0:
            bucket_size = max(10.0, duration_seconds / bucket_count)
        else:
            max_time = max(float(item.get("timestamp_seconds", 0.0)) for item in rejected)
            bucket_size = max(10.0, max_time / bucket_count) if max_time > 0 else 10.0
        buckets: dict[int, dict[str, Any]] = {}
        for item in rejected:
            timestamp = float(item.get("timestamp_seconds", 0.0))
            bucket_index = int(timestamp // bucket_size)
            bucket = buckets.setdefault(
                bucket_index,
                {
                    "start_seconds": round(bucket_index * bucket_size, 3),
                    "end_seconds": round((bucket_index + 1) * bucket_size, 3),
                    "count": 0,
                    "reasons": {},
                    "player_ids": {},
                },
            )
            reason = str(item.get("rejected_reason") or "unknown")
            player_id = str(item.get("player_id") or "unknown")
            bucket["count"] += 1
            bucket["reasons"][reason] = bucket["reasons"].get(reason, 0) + 1
            bucket["player_ids"][player_id] = bucket["player_ids"].get(player_id, 0) + 1
        return [buckets[index] for index in sorted(buckets)]

    @staticmethod
    def _trajectory_last_timestamp(player_trajectories: PlayerTrajectoryArtifact | None) -> float | None:
        """
        返回球员轨迹里最晚的采样时间戳；没有轨迹则返回 None。
        用于判断"轨迹是否比 tracking 更早就结束"（需要降级补充检测）。
        """
        if player_trajectories is None:
            return None
        values = [sample.timestamp_seconds for samples in player_trajectories.players.values() for sample in samples]
        return max(values) if values else None

    def _trajectory_ends_before_tracking(
        self,
        player_trajectories: PlayerTrajectoryArtifact | None,
        tracking: TrackingResult,
    ) -> bool:
        """
        判断轨迹是否明显早于 tracking 结束（低于 tracking 时长的 75%）。
        若是，detect() 会降级用 tracking/pose 信号补充后面时间段的候选。
        """
        trajectory_last = self._trajectory_last_timestamp(player_trajectories)
        tracking_last = max((frame.timestamp_seconds for frame in tracking.overlay_frames), default=None)
        if trajectory_last is None or tracking_last is None:
            return False
        return trajectory_last < tracking_last * 0.75
