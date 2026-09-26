#!/usr/bin/env bash
# 远程视觉与姿态推理依赖安装（ultralytics + mmpose 技术栈）
#
# 用法（在远程服务器上执行）：
#   bash 03_install_vision_pose.sh
#
# 设计说明：
#   - ultralytics 提供人员 / 球 / 场地线三套 YOLO 检测的推理后端。
#   - mmpose + mmcv 提供 RTMPose-26 (halpe26) 姿态推理。
#   - mmcv 2.1.0 在 Linux 上默认会尝试编译 CUDA 自定义算子，无卡模式下必然失败。
#     RTMPose 推理只用到 mmcv 的 Python 侧工具（registry / transforms / 图像处理），
#     不使用 deformable conv 等算子，因此以 MMCV_WITH_OPS=0 走纯 Python 安装。
#   - 若日后需要 mmcv 的算子（如换用带 mmdet 检测器的 top-down 全流程），
#     再在有卡模式下用 MMCV_WITH_OPS=1 重装即可。
set -euo pipefail

ENV_PREFIX=/root/autodl-tmp/envs/pickleball
PIP="${ENV_PREFIX}/bin/pip"

export PIP_CACHE_DIR=/root/autodl-tmp/pip-cache
export PIP_DISABLE_PIP_VERSION_CHECK=1

echo "=== 1/4 安装 ultralytics ==="
"${PIP}" install "ultralytics==8.4.115"

echo "=== 2/4 安装 mmengine ==="
"${PIP}" install "mmengine==0.10.7"

echo "=== 3/4 安装 mmcv（使用纯 Python 分发包 mmcv-lite） ==="
# 为什么不用 `pip install mmcv==2.1.0`：
#   1) PyPI 上 mmcv 2.x 只有 sdist；源码在 MMCV_WITH_OPS=0 时会把分发名改成 mmcv-lite，
#      与需求名 mmcv 不一致，pip 判定 inconsistent name 后直接丢弃该文件；
#   2) 走 MMCV_WITH_OPS=1 需要编译自定义算子，而无卡模式镜像里没有 nvcc；
#      OpenMMLab 也没有 torch 2.13 对应的预编译 wheel（cu126/torch2.13 索引返回 404）。
# 官方 PyPI 上有独立的 mmcv-lite 分发包：纯 Python 实现，装完提供同名的 mmcv 模块。
# RTMPose 推理只用到 mmcv 的 Python 侧能力（registry / transforms / 图像处理），
# 不使用 deformable conv 等自定义算子，因此直接采用它。
"${PIP}" install --index-url https://pypi.org/simple --no-deps "mmcv-lite==2.1.0"

echo "=== 4/4 安装 mmdet / mmpose 与辅助依赖 ==="
# mmcv-lite 的分发名不是 mmcv，pip 无法据此判定 mmpose/mmdet 的 mmcv 依赖已满足，
# 因此先以 --no-deps 跳过解析，再由下面显式补齐两者的真实运行依赖。
"${PIP}" install --no-deps "mmdet==3.3.0" "mmpose==1.3.2"
"${PIP}" install \
  "pycocotools==2.0.11" \
  "xtcocotools==1.14.3" \
  "shapely==2.1.2" \
  "json-tricks==3.17.3" \
  "addict==2.4.0" \
  "terminaltables==3.1.10" \
  "munkres==1.1.4"

echo "=== 校验 ==="
"${ENV_PREFIX}/bin/python" - <<'PY'
import mmcv, mmengine
print("mmcv:", mmcv.__version__)
print("mmengine:", mmengine.__version__)
import mmpose
print("mmpose:", mmpose.__version__)
try:
    import mmdet
    print("mmdet:", mmdet.__version__)
except Exception as exc:
    print("mmdet import 失败:", exc)
import ultralytics
print("ultralytics:", ultralytics.__version__)
PY

echo "=== POSE_INSTALL_DONE ==="
