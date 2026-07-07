"""匹克球运动表现引擎 —— MVP 阶段提供移动距离、速度、热力图等指标。"""

# 从轨迹指标模块导出“总移动距离”计算函数，作为本引擎对外的统一入口之一。
from app.vision.pickleball_performance_engine.trajectory_metrics import total_distances

# 显式声明本包对外公开的符号，避免 `from app.vision.pickleball_performance_engine import *` 时引入多余名字。
__all__ = ["total_distances"]
