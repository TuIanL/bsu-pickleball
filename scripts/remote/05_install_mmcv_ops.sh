#!/usr/bin/env bash
# 远程安装 mmcv 完整版（含 CPU 自定义算子）
#
# 用法（在远程服务器上执行）：
#   bash 05_install_mmcv_ops.sh
#
# 为什么需要这一步：
#   mmpose 1.3.2 的 mmpose/models/heads/__init__.py 会无条件导入 transformer_heads，
#   其中 edpose_head.py 第 14 行是 `from mmcv.ops import MultiScaleDeformableAttention`，
#   而 mmcv/ops/__init__.py 又依赖编译扩展 mmcv._ext。
#   mmcv-lite 不含该扩展 → `import mmcv._ext` 直接 ModuleNotFoundError
#   → 连带 `from mmpose.apis import init_model` 失败，RTMPose 整条链路不可用。
#   因此必须装带算子的 mmcv。
#
# 无卡模式没有 nvcc，mmcv 只编译 CPU 部分即可满足需要。
set -euo pipefail

ENV_PREFIX=/root/autodl-tmp/envs/pickleball
PIP="${ENV_PREFIX}/bin/pip"

export PIP_CACHE_DIR=/root/autodl-tmp/pip-cache
export PIP_DISABLE_PIP_VERSION_CHECK=1
# 本机 192 核，但并行度过高容易吃满内存并触发 OOM，32 是稳妥值。
export MAX_JOBS=32

echo "=== 1/3 准备构建依赖 ==="
# mmcv 2.1.0 的 setup.py 顶部是 `from pkg_resources import ...`，而 setuptools 81+
# 已移除 pkg_resources 模块，必须先固定到 80.x，否则 metadata 生成直接失败。
"${PIP}" install "setuptools==80.10.2" "wheel==0.47.0" "ninja==1.13.0" "pybind11>=2.6.0"

echo "=== 2/3 移除 mmcv-lite ==="
# mmcv 与 mmcv-lite 提供同名的 mmcv 模块，两者不能共存，先卸载干净。
"${PIP}" uninstall -y mmcv-lite >/dev/null 2>&1 || true

echo "=== 3/3 编译安装 mmcv（仅 CPU 算子）==="
cd /tmp
MMCV_WITH_OPS=1 "${PIP}" install --no-build-isolation "mmcv==2.1.0"

echo "=== 校验 ==="
"${ENV_PREFIX}/bin/python" - <<'PY'
import mmcv
print("mmcv:", mmcv.__version__)
try:
    from mmcv.ops import MultiScaleDeformableAttention
    print("mmcv.ops 可用")
except Exception as exc:
    print("mmcv.ops 仍不可用:", exc)
try:
    from mmpose.apis import init_model
    print("mmpose.apis 可用")
except Exception as exc:
    print("mmpose.apis 仍不可用:", exc)
PY

echo "=== MMCV_OPS_INSTALL_DONE ==="
