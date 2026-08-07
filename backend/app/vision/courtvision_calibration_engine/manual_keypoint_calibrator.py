"""
手工关键点标定器（manual_keypoint_calibrator）。

封装"手工四角标定"这个流程的引擎入口。所谓手工标定：用户在视频画面上
点出球场的四个角（左上、右上、右下、左下），后端据此算出单应性矩阵。

本文件只是一个很薄的"包装层"：它把上层传来的请求，转交给真正干活的
calibration_service 去执行，自己不重复写标定逻辑。
"""

# `from __future__ import annotations`：兼容较新类型写法。
from __future__ import annotations

# 标定相关的数据结构（来自 schemas.calibration）。
# - ManualKeypointCalibrationRequest：手工四角标定的请求体；
# - CalibrationCreate：更通用的标定创建请求；
# - CalibrationResult：标定结果。
from app.schemas.calibration import CalibrationCreate, CalibrationResult, ManualKeypointCalibrationRequest

# 真正执行标定计算的 service 层。
from app.services.calibration_service import CalibrationService


class ManualKeypointCalibrator:
    """手工球场关键点标定的引擎包装器（Engine wrapper for manual court keypoint calibration）。"""

    def __init__(self, service: CalibrationService | None = None) -> None:
        # 没传入 service 就新建一个默认的；传入则复用（便于测试/共享）。
        self.service = service or CalibrationService()

    def calibrate(self, payload: ManualKeypointCalibrationRequest | CalibrationCreate) -> CalibrationResult:
        """
        执行一次标定。

        根据请求类型分流：
        - 若是手工四角标定请求（ManualKeypointCalibrationRequest）→ 调 create_manual_calibration；
        - 否则当作通用标定创建请求（CalibrationCreate）→ 调 create_calibration。
        返回统一的 CalibrationResult。
        """
        if isinstance(payload, ManualKeypointCalibrationRequest):
            return self.service.create_manual_calibration(payload)
        return self.service.create_calibration(payload)
