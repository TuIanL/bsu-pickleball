"""
动作分类预处理 —— 纯图像处理工具函数。

这些函数只做"图像/数值计算"，不碰文件、不碰模型，是 exporter.py 的底层积木。
涉及的图像处理库是 OpenCV（代码里写作 `cv2`），以及 NumPy 数组：
- 在 OpenCV 里，一张图就是一个多维数组（numpy array）：
  - 彩色图 shape 是 (高, 宽, 3)，3 个通道是 BGR（注意是蓝-绿-红，不是 RGB）；
  - 灰度图 shape 是 (高, 宽)。
- 用 `frame[y1:y2, x1:x2]` 这种切片，就能裁出"从 y1 到 y2 行、x1 到 x2 列"的子图。
"""

# `from __future__ import annotations`：让较新的类型写法在老 Python 上也兼容。
from __future__ import annotations

# Any：表示"任意类型"，这里用来泛指"一张图（numpy array）"。
from typing import Any

# ROIConfig 是 ROI 的比例配置；ROIRecord 是裁剪后的记录。都来自同包的 schemas。
from app.vision.action_classification_preprocessing.schemas import ROIConfig, ROIRecord


def sample_frame_indices(
    *,
    fps: float,
    frame_count: int,
    target_fps: float,
    start_seconds: float = 0.0,
    end_seconds: float | None = None,
) -> list[tuple[int, float]]:
    """
    计算"应该抽取哪些帧"，返回一串 (帧序号, 时间戳秒) 的列表。

    原视频可能是 30fps，但我们只想按 target_fps（比如 20fps）抽帧，
    目的是降采样、统一不同视频的帧率，让训练样本更规整。

    参数（都用了 `*` 隔开，表示后面的参数必须"按名字"传，不能按位置）：
    - fps：原视频帧率；
    - frame_count：原视频总帧数；
    - target_fps：目标采样帧率；
    - start_seconds / end_seconds：只在 [start, end] 这段时间里抽帧。

    返回：[(帧序号, 该帧时间戳秒), ...]，例如 [(0, 0.0), (2, 0.05), ...]。
    """
    if fps <= 0:
        raise ValueError("fps must be greater than 0")
    if frame_count <= 0:
        return []
    if target_fps <= 0:
        raise ValueError("target_fps must be greater than 0")
    if start_seconds < 0:
        raise ValueError("start_seconds must be greater than or equal to 0")

    # 视频总时长（秒）= 总帧数 / 帧率
    duration = frame_count / fps
    # 结束时间：没给 end_seconds 就用整段时长；给了就取"给定值"和"总时长"的较小者（不能超出视频）
    end = duration if end_seconds is None else min(end_seconds, duration)
    if end < start_seconds:
        return []

    samples: list[tuple[int, float]] = []   # 结果列表
    seen: set[int] = set()                  # 已选过的帧序号集合，防止同一帧被选两次
    timestamp = start_seconds
    step = 1.0 / target_fps                 # 相邻抽样点之间的时间间隔（秒）
    # 按时间步进：每走一步算一个"期望时间戳"，再换算成"最近的帧序号"
    while timestamp <= end + 1e-9:          # +1e-9 是为了抵消浮点误差，确保边界帧不错过
        frame_index = int(round(timestamp * fps))   # 时间戳 × 帧率 ≈ 帧序号，四舍五入取整
        if frame_index >= frame_count:
            break
        if frame_index not in seen:
            seen.add(frame_index)
            samples.append((frame_index, frame_index / fps))
        timestamp += step
    return samples


def crop_court_roi(frame: Any, roi: ROIConfig) -> tuple[Any, ROIRecord]:
    """
    按 ROI 比例，从整张图里裁出"场地那一块"。

    返回：(裁好的子图, 这次裁剪的记录 ROIRecord)。
    """
    height, width = frame.shape[:2]   # 取图的高和宽（shape 前两个维度）
    # 把"比例"换算成"像素坐标"，并用 max/min 夹紧到合法范围，避免越界
    x1 = max(0, min(width - 1, int(round(width * roi.x1_ratio))))
    y1 = max(0, min(height - 1, int(round(height * roi.y1_ratio))))
    # x2/y2 至少要比 x1/y1 大 1 像素，保证裁出来的图不为空
    x2 = max(x1 + 1, min(width, int(round(width * roi.x2_ratio))))
    y2 = max(y1 + 1, min(height, int(round(height * roi.y2_ratio))))
    # 记下这次裁剪的元信息，便于后续把"相对 ROI 的框"换算回原图坐标
    record = ROIRecord(
        ratios={
            "x1_ratio": roi.x1_ratio,
            "y1_ratio": roi.y1_ratio,
            "x2_ratio": roi.x2_ratio,
            "y2_ratio": roi.y2_ratio,
        },
        bbox=[x1, y1, x2, y2],
        source_width=width,
        source_height=height,
    )
    # NumPy 数组切片：行方向 [y1:y2]，列方向 [x1:x2]
    return frame[y1:y2, x1:x2], record


def apply_clahe_bgr(frame: Any, *, clip_limit: float = 2.0, tile_grid_size: int = 8) -> Any:
    """
    对 BGR 彩色图做 CLAHE 亮度增强。

    CLAHE 在 LAB 颜色空间的 L（亮度）通道上做对比度均衡，
    这样既提亮了暗部，又不会把颜色搞乱。

    这里用函数内部 `import cv2` 的方式（延迟导入），
    是为了让"只用纯逻辑、不需要 OpenCV"的场景也能导入本模块而不报错。
    """
    import cv2  # type: ignore

    # BGR → LAB 颜色空间；LAB 分 L（亮度）、A、B 三个通道
    lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
    l_channel, a_channel, b_channel = cv2.split(lab)   # 拆成三个单通道图
    # 创建 CLAHE 对象并作用在亮度通道上
    clahe = cv2.createCLAHE(clipLimit=float(clip_limit), tileGridSize=(int(tile_grid_size), int(tile_grid_size)))
    enhanced_l = clahe.apply(l_channel)
    # 把增强后的亮度通道和原来的 A、B 通道合并回去
    enhanced = cv2.merge((enhanced_l, a_channel, b_channel))
    # LAB → 转回 BGR，方便后续 OpenCV 继续处理/保存
    return cv2.cvtColor(enhanced, cv2.COLOR_LAB2BGR)


def apply_light_denoise(frame: Any, *, kernel_size: int = 3, sigma: float = 0.0) -> Any:
    """
    轻量去噪：对整张图做一次高斯模糊。

    高斯模糊会让画面稍微糊一点，从而压掉噪点。kernel_size 越大越糊。
    """
    import cv2  # type: ignore

    return cv2.GaussianBlur(frame, (int(kernel_size), int(kernel_size)), float(sigma))


def expand_box(box: list[float], frame_shape: tuple[int, ...], *, scale: float = 1.4) -> list[int]:
    """
    把检测框按中心点"等比放大" scale 倍，并夹紧到图像范围内。

    检测框往往贴着人体边缘，裁剪时留点余量（放大一点）能避免切掉手脚。
    返回放大后的整数像素框 [nx1, ny1, nx2, ny2]。
    """
    height, width = frame_shape[:2]
    x1, y1, x2, y2 = [float(value) for value in box[:4]]   # 取前 4 个数作为框
    cx = (x1 + x2) / 2.0   # 框中心 x
    cy = (y1 + y2) / 2.0   # 框中心 y
    box_width = max(1.0, (x2 - x1) * scale)    # 放大后的宽（至少 1 像素）
    box_height = max(1.0, (y2 - y1) * scale)   # 放大后的高（至少 1 像素）
    # 以中心为基准，向两边各扩一半，再夹紧到 [0, 宽/高] 内
    nx1 = max(0, int(round(cx - box_width / 2.0)))
    ny1 = max(0, int(round(cy - box_height / 2.0)))
    nx2 = min(width, int(round(cx + box_width / 2.0)))
    ny2 = min(height, int(round(cy + box_height / 2.0)))
    # 极端情况下放大后宽/高变成 0，强制至少 1 像素，避免裁出空图
    if nx2 <= nx1:
        nx2 = min(width, nx1 + 1)
    if ny2 <= ny1:
        ny2 = min(height, ny1 + 1)
    return [nx1, ny1, nx2, ny2]


def offset_box(box: list[float] | list[int], x_offset: float, y_offset: float) -> list[float]:
    """
    把框整体平移一个偏移量。

    因为 ROI 裁掉了左上方一块，所以"相对 ROI 的框"要加上 ROI 左上角的偏移，
    才能得到"相对整张原图的框"。这里的 x_offset/y_offset 就是那个偏移。
    """
    x1, y1, x2, y2 = [float(value) for value in box[:4]]
    return [x1 + x_offset, y1 + y_offset, x2 + x_offset, y2 + y_offset]


def crop_player(frame: Any, box: list[float], *, output_size: int = 224, scale: float = 1.4) -> tuple[Any, list[int]]:
    """
    从整张图里裁出"某个球员"，并 resize 成固定正方形。

    参数：
    - frame：原图（通常是增强后的 ROI 图）；
    - box：选中球员在图里的框 [x1,y1,x2,y2]；
    - output_size：输出边长（正方形，如 224，对应很多分类模型的输入尺寸）；
    - scale：裁剪前先把框放大多少倍（调用 expand_box）。

    返回：(裁好并 resize 的方形图, 实际使用的整数裁剪框)。
    """
    import cv2  # type: ignore

    crop_box = expand_box(box, frame.shape, scale=scale)   # 先放大框
    x1, y1, x2, y2 = crop_box
    crop = frame[y1:y2, x1:x2]                             # 按框裁出子图
    resized = cv2.resize(crop, (int(output_size), int(output_size)))  # 缩放到固定尺寸
    return resized, crop_box


def build_clip_windows(frame_count: int, *, clip_length: int, clip_stride: int) -> list[list[int]]:
    """
    把一串帧"切"成多个不重叠/部分重叠的 clip 窗口。

    例如 frame_count=40、clip_length=16、clip_stride=16：
    会得到 [[0..15], [16..31], [32..39(不足则停止)]]，即每 16 帧一个 clip、相邻不重叠。

    返回：[[帧序号, ...], [帧序号, ...], ...]，每个内层列表是一个 clip 的帧序号集合。
    """
    if clip_length <= 0:
        raise ValueError("clip_length must be greater than 0")
    if clip_stride <= 0:
        raise ValueError("clip_stride must be greater than 0")
    windows: list[list[int]] = []
    start = 0
    # 只要"起始 + 片段长度"不超过总帧数，就切出一个窗口，然后整体往后跳 clip_stride 帧
    while start + clip_length <= frame_count:
        windows.append(list(range(start, start + clip_length)))
        start += clip_stride
    return windows
