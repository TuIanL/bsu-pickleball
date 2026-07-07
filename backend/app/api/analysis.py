"""
分析 API 模块（兼容层）

历史原因：早期分析任务的接口直接写在 analysis.py 里。
后来为了文件职责更清晰，真正的接口实现被搬到了 routes_analysis.py。
本文件只做"再导出（re-export）"——把新文件里的 router 重新暴露出来，
这样旧的导入写法（`from app.api.analysis import router`）依然能用，
不必改动 main.py 里对它的引用。
"""

# 从新的实现文件 routes_analysis.py 导入真正的路由表（router）
from app.api.routes_analysis import router

# 声明本模块对外公开的名字，方便其他地方用
# `from app.api.analysis import router` 这种方式导入
__all__ = ["router"]
