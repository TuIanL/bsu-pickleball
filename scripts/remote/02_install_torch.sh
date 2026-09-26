#!/usr/bin/env bash
# 远程 torch / torchvision 安装
#
# 用法（在远程服务器上执行）：
#   bash 02_install_torch.sh
#
# 关键：必须匹配宿主机的 NVIDIA 驱动能力。
#   本实例驱动为 570.124.04（NVRM），可支持的 CUDA runtime 上限是 12.8。
#   PyPI 上的 torch 2.13.0 默认是 +cu130（CUDA 13），装上去虽然能 import，
#   但会警告 "The NVIDIA driver on your system is too old (found version 12080)"，
#   切到有卡模式后 GPU 仍然不可用。
#   因此固定从 cu126 轮子索引安装：CUDA 12.6 runtime 在 12.8 驱动上受
#   minor version compatibility 支持，版本号仍是 2.13.0，与本地一致。
#
#   如需变更 CUDA 版本，改 TORCH_INDEX 即可（cu126 / cu128 / cpu）。
set -euo pipefail

ENV_PREFIX=/root/autodl-tmp/envs/pickleball
PIP="${ENV_PREFIX}/bin/pip"
TORCH_INDEX="https://download.pytorch.org/whl/cu126"
PYPI_MIRROR="https://pypi.tuna.tsinghua.edu.cn/simple"

export PIP_CACHE_DIR=/root/autodl-tmp/pip-cache
export PIP_DISABLE_PIP_VERSION_CHECK=1

echo "=== 清理其它 CUDA 版本的 torch 与运行时依赖 ==="
"${PIP}" uninstall -y torch torchvision triton >/dev/null 2>&1 || true
# cu130 的 nvidia-* / cuda-* 包与 cu126 的（多为带 cu12 后缀的同名包）包名不同，
# pip 不会自动替换，需显式清理，否则白占数 GB 数据盘。
"${PIP}" freeze 2>/dev/null | grep -iE "^(nvidia|cuda-|triton)" | cut -d= -f1 \
  | xargs -r "${PIP}" uninstall -y >/dev/null 2>&1 || true

echo "=== 安装 torch / torchvision（索引：${TORCH_INDEX}）==="
"${PIP}" install \
  --index-url "${TORCH_INDEX}" \
  --extra-index-url "${PYPI_MIRROR}" \
  "torch==2.13.0" "torchvision==0.28.0"

echo "=== 校验 ==="
"${ENV_PREFIX}/bin/python" - <<'PY'
import torch, torchvision
print("torch:", torch.__version__)
print("torchvision:", torchvision.__version__)
print("cuda available:", torch.cuda.is_available())
print("cpu threads:", torch.get_num_threads())
PY

echo "=== TORCH_INSTALL_DONE ==="
