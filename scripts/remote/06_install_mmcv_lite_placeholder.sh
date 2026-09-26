#!/usr/bin/env bash
# 安装 mmcv-lite 并补一个占位扩展模块，使 mmpose 可以正常导入
#
# 用法（在远程服务器上执行）：
#   bash 06_install_mmcv_lite_placeholder.sh
#
# 背景——为什么最终走到这一步：
#   1. mmpose 1.3.2 的 mmpose/models/heads/__init__.py 会**无条件**导入 transformer_heads，
#      其中 edpose_head.py:14 执行 `from mmcv.ops import MultiScaleDeformableAttention`，
#      而 mmcv/ops/__init__.py 又依赖编译扩展 mmcv._ext。缺失该扩展时 `import mmcv._ext`
#      抛 ModuleNotFoundError，连带 `from mmpose.apis import init_model` 整体失败，
#      RTMPose 链路完全不可用。
#   2. 正解是编译带算子的 mmcv：
#        pip install "setuptools==80.10.2"
#        cd /tmp && MMCV_WITH_OPS=1 pip install --no-build-isolation mmcv==2.1.0
#      但本实例是 AutoDL **无卡模式**，cgroup memory.max 仅 2GB，编译 spconv 模板时
#      g++ (cc1plus) 被 OOM Killer 杀死，无法完成编译（见 05_install_mmcv_ops.sh）。
#   3. 因此改用 mmcv-lite + 占位 mmcv._ext：
#        - mmcv-lite 提供 mmcv 的全部 Python 侧能力；
#        - 占位 _ext 让 import 链通过，未实现的算子只在**被真正调用时**才报错。
#      RTMPose 是 ResNet backbone + SimCC head，不使用 deformable conv 等自定义算子，
#      因此这条路径足以支撑姿态推理。
#   4. 切到有卡模式后（内存充裕且带 nvcc），建议改回真实编译，执行 05_install_mmcv_ops.sh
#      覆盖为完整版 mmcv。
set -euo pipefail

ENV_PREFIX=/root/autodl-tmp/envs/pickleball
PIP="${ENV_PREFIX}/bin/pip"
SITE_PACKAGES="${ENV_PREFIX}/lib/python3.11/site-packages"

export PIP_CACHE_DIR=/root/autodl-tmp/pip-cache
export PIP_DISABLE_PIP_VERSION_CHECK=1

echo "=== 1/3 安装 mmcv-lite ==="
"${PIP}" install --index-url https://pypi.org/simple --no-deps "mmcv-lite==2.1.0"

echo "=== 2/3 写入占位扩展模块 mmcv/_ext.py ==="
# 注意顺序：必须先装 mmcv-lite 再写这个文件，否则会被 pip 重装时清掉。
cat > "${SITE_PACKAGES}/mmcv/_ext.py" <<'PY'
"""mmcv 编译扩展的占位实现（mmcv-lite 环境专用）。

当前部署环境（AutoDL 无卡模式）容器内存上限 2GB，无法编译 mmcv 的 C++ 自定义算子。
本模块让 `import mmcv._ext` 与 `mmcv.utils.ext_loader.load_ext` 能够通过，
从而解开 mmpose -> mmcv.ops -> mmcv._ext 的导入链。

未实现的算子只会在**被真正调用时**抛出 NotImplementedError，不会静默返回错误结果。
RTMPose（ResNet backbone + SimCC head）不依赖任何自定义算子，因此不受影响。

如需真实算子：在有卡模式下执行 scripts/remote/05_install_mmcv_ops.sh 重新编译 mmcv，
完整版 mmcv 会覆盖本文件所在目录。
"""


def __getattr__(name):
    """任何未定义的算子都返回一个「调用即报错」的占位函数。"""
    if name.startswith("__"):
        raise AttributeError(name)

    def _unavailable(*args, **kwargs):
        raise NotImplementedError(
            f"mmcv._ext.{name} 不可用：当前为 mmcv-lite + 占位扩展。"
            "如需真实算子，请在有卡模式下重新编译 mmcv（scripts/remote/05_install_mmcv_ops.sh）。"
        )

    return _unavailable
PY

echo "=== 3/3 校验 ==="
"${ENV_PREFIX}/bin/python" - <<'PY'
import mmcv
print("mmcv:", mmcv.__version__)
import mmcv._ext  # noqa: F401
print("mmcv._ext 占位模块可导入")
from mmcv.ops import MultiScaleDeformableAttention  # noqa: F401
print("mmcv.ops 可导入")
from mmpose.apis import init_model  # noqa: F401
print("mmpose.apis 可导入")
PY

echo "=== MMCV_LITE_PLACEHOLDER_DONE ==="
