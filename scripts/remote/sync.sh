#!/usr/bin/env bash
# 本地 ↔ 远程算力服务器 的文件同步
#
# 用法（在本地项目根执行）：
#   bash scripts/remote/sync.sh code              推送代码（backend + scripts）
#   bash scripts/remote/sync.sh models            推送模型权重
#   bash scripts/remote/sync.sh push-video <file> 上传待分析视频到远程 uploads
#   bash scripts/remote/sync.sh pull-results      把远程分析结果拉回本地
#   bash scripts/remote/sync.sh pull-job <job_id> 只拉回某个任务的产物
#   bash scripts/remote/sync.sh pull-capture-results <YYYY-MM-DD>
#                                             拉回录制会话的 analysis 产物（不拉原视频）
#   bash scripts/remote/sync.sh disk              查看远程磁盘占用
#
# 设计取舍：
#   - 代码与模型单向推送（本地为权威），不使用 --delete，避免误删远程产物。
#   - 结果单向拉回（远程为权威）。远程 output 目录只增不减，本地同名文件会被覆盖。
#   - 不上传 backend/data/outputs 的历史产物与 .venv，远程保持干净的计算环境。
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=remote.env
source "${HERE}/remote.env"

PROJECT_ROOT="$(cd "${HERE}/../.." && pwd)"
SSH_CMD="ssh -i ${REMOTE_KEY} -p ${REMOTE_PORT} -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"
TARGET="${REMOTE_USER}@${REMOTE_HOST}"
REMOTE_PROJECT="${REMOTE_ROOT}"

ensure_remote_dirs() {
  ssh -i "${REMOTE_KEY}" -p "${REMOTE_PORT}" -o BatchMode=yes \
    -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "${TARGET}" \
    "mkdir -p ${REMOTE_PROJECT}/backend/data/uploads ${REMOTE_PROJECT}/backend/data/outputs ${REMOTE_PROJECT}/scripts"
}

case "${1:-}" in
  code)
    ensure_remote_dirs
    echo "推送 backend 与 scripts ..."
    rsync -a --partial --exclude='.venv/' --exclude='__pycache__/' --exclude='*.pyc' \
      --exclude='data/' --exclude='.pytest_cache/' --exclude='build/' --exclude='*.egg-info/' \
      -e "${SSH_CMD}" "${PROJECT_ROOT}/backend/" "${TARGET}:${REMOTE_PROJECT}/backend/"
    rsync -a --partial --exclude='__pycache__/' -e "${SSH_CMD}" \
      "${PROJECT_ROOT}/scripts/remote/" "${TARGET}:${REMOTE_PROJECT}/scripts/remote/"
    echo "代码推送完成"
    ;;

  models)
    echo "推送 models（约 250MB，视网络 3-6 分钟）..."
    rsync -a --partial -e "${SSH_CMD}" \
      "${PROJECT_ROOT}/models/" "${TARGET}:${REMOTE_PROJECT}/models/"
    echo "模型推送完成"
    ;;

  push-video)
    if [[ -z "${2:-}" || ! -f "${2}" ]]; then
      echo "用法: $0 push-video <本地视频路径>" >&2
      exit 1
    fi
    ensure_remote_dirs
    echo "上传 $(basename "$2") ..."
    rsync -a --partial --progress -e "${SSH_CMD}" \
      "$2" "${TARGET}:${REMOTE_PROJECT}/backend/data/uploads/"
    echo "上传完成。远程路径：${REMOTE_PROJECT}/backend/data/uploads/$(basename "$2")"
    ;;

  pull-results)
    mkdir -p "${PROJECT_ROOT}/backend/data/outputs"
    echo "拉回远程分析结果 ..."
    rsync -a --partial --stats -e "${SSH_CMD}" \
      "${TARGET}:${REMOTE_PROJECT}/backend/data/outputs/" "${PROJECT_ROOT}/backend/data/outputs/"
    echo "结果拉回完成"
    ;;

  pull-job)
    if [[ -z "${2:-}" ]]; then
      echo "用法: $0 pull-job <job_id>" >&2
      exit 1
    fi
    local_dir="${PROJECT_ROOT}/backend/data/outputs/${2}"
    mkdir -p "${local_dir}"
    rsync -a --partial --progress -e "${SSH_CMD}" \
      "${TARGET}:${REMOTE_PROJECT}/backend/data/outputs/${2}/" "${local_dir}/"
    rsync -a --partial -e "${SSH_CMD}" \
      "${TARGET}:${REMOTE_PROJECT}/backend/data/outputs/jobs/${2}.json" \
      "${PROJECT_ROOT}/backend/data/outputs/jobs/" 2>/dev/null || true
    echo "任务 ${2} 产物已拉回"
    ;;

  pull-capture-results)
    if [[ -z "${2:-}" || ! "${2}" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
      echo "用法: $0 pull-capture-results <YYYY-MM-DD>" >&2
      exit 1
    fi
    capture_date="${2}"
    local_capture_root="${PROJECT_ROOT}/backend/data/recordings/captures/${capture_date}"
    mkdir -p "${local_capture_root}" "${PROJECT_ROOT}/backend/data/outputs/jobs"
    echo "拉回 ${capture_date} 录制会话的分析产物（不含原视频）..."
    rsync -a --partial --prune-empty-dirs \
      --include='*/' --include='analysis/***' --exclude='*' \
      -e "${SSH_CMD}" \
      "${TARGET}:${REMOTE_PROJECT}/backend/data/recordings/captures/${capture_date}/" \
      "${local_capture_root}/"
    rsync -a --partial -e "${SSH_CMD}" \
      "${TARGET}:${REMOTE_PROJECT}/backend/data/outputs/jobs/" \
      "${PROJECT_ROOT}/backend/data/outputs/jobs/"
    echo "录制会话分析产物已拉回"
    ;;

  disk)
    ssh -i "${REMOTE_KEY}" -p "${REMOTE_PORT}" -o BatchMode=yes \
      -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "${TARGET}" \
      "echo '=== 数据盘 ==='; df -h /root/autodl-tmp | tail -1; \
       echo '=== 项目占用 ==='; du -sh ${REMOTE_PROJECT}/* 2>/dev/null; \
       echo '=== outputs ==='; du -sh ${REMOTE_PROJECT}/backend/data/outputs 2>/dev/null"
    ;;

  *)
    sed -n '2,16p' "${BASH_SOURCE[0]}"
    exit 1
    ;;
esac
