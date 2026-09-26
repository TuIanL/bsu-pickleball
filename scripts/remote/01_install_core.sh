#!/usr/bin/env bash
# 远程核心后端依赖安装（版本严格对齐本地 backend/.venv 的 pip freeze）
#
# 用法（在远程服务器上执行）：
#   bash 01_install_core.sh
#
# 说明：远程环境为数据盘上的 conda env，路径 /root/autodl-tmp/envs/pickleball。
#       pip 缓存与 env 同放数据盘，避免撑爆 30G 系统盘。
set -euo pipefail

ENV_PREFIX=/root/autodl-tmp/envs/pickleball
PIP="${ENV_PREFIX}/bin/pip"

export PIP_CACHE_DIR=/root/autodl-tmp/pip-cache
export PIP_DISABLE_PIP_VERSION_CHECK=1

"${PIP}" config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
"${PIP}" config set global.trusted-host pypi.tuna.tsinghua.edu.cn

echo "=== 开始安装核心后端依赖 ==="
"${PIP}" install \
  "fastapi==0.141.1" \
  "uvicorn[standard]==0.52.1" \
  "pydantic==2.13.4" \
  "python-multipart==0.0.32" \
  "numpy==1.26.4" \
  "scipy==1.17.1" \
  "opencv-python==4.11.0.86" \
  "pandas==3.0.5" \
  "SQLAlchemy==2.0.51" \
  "alembic==1.20.0" \
  "python-dotenv==1.2.2" \
  "matplotlib==3.11.1" \
  "shapely==2.1.2" \
  "pytest==9.1.1" \
  "httpx==0.28.1" \
  "psutil==7.2.2"

echo "=== CORE_INSTALL_DONE ==="
