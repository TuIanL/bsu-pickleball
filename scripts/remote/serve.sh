#!/usr/bin/env bash
# 远程算力服务器上的后端服务生命周期管理 + 本地 SSH 隧道
#
# 用法（在本地项目根执行）：
#   bash scripts/remote/serve.sh start    启动远程后端，并建立本地隧道
#   bash scripts/remote/serve.sh stop     停止远程后端与本地隧道
#   bash scripts/remote/serve.sh status   查看两端状态
#   bash scripts/remote/serve.sh logs     查看远程后端日志尾部
#
# 启动后访问入口：
#   本地 http://127.0.0.1:8100  →  SSH 隧道  →  远程 127.0.0.1:8000
# 远程 API 只监听服务器回环地址，不经公网暴露。
#
# 注意：本机若有 HTTP 代理（http_proxy / https_proxy），用 curl 访问 127.0.0.1
#      时必须加 --noproxy '*'，否则请求会被代理截走并返回 502。
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=remote.env
source "${HERE}/remote.env"

SSH_BASE=(-i "${REMOTE_KEY}" -p "${REMOTE_PORT}" -o BatchMode=yes
          -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null
          -o ServerAliveInterval=15 -o ServerAliveCountMax=6
          -o TCPKeepAlive=yes)
TARGET="${REMOTE_USER}@${REMOTE_HOST}"

remote() {
  ssh "${SSH_BASE[@]}" "${TARGET}" "$@"
}

# 隧道是否真的在监听，以本机端口为准（比 PID 文件可靠）
tunnel_alive() {
  lsof -nP -iTCP:"${LOCAL_API_PORT}" -sTCP:LISTEN >/dev/null 2>&1
}

start_remote_api() {
  remote "
# 用「端口能否响应」判定是否已运行，比 pgrep 可靠：
# pgrep -f 会匹配到本次 ssh 会话自身的命令行，从而误判为「已在运行」。
if curl -s -o /dev/null --max-time 3 http://127.0.0.1:${REMOTE_API_PORT}/docs; then
  echo '[远程] 后端已在运行'
else
  mkdir -p ${REMOTE_LOGS}
  cd ${REMOTE_ROOT}/backend || exit 1
  # 可选的运行时分析配置。把它放在数据盘项目目录，重启实例后仍可保留；
  # 使用 set -a 保证其中的 PICKLEBALL_* 变量会传给后台 uvicorn 进程。
  if [ -f ${REMOTE_ROOT}/scripts/remote/runtime.env ]; then
    set -a
    . ${REMOTE_ROOT}/scripts/remote/runtime.env
    set +a
  fi
  setsid nohup ${REMOTE_ENV}/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port ${REMOTE_API_PORT} > ${REMOTE_LOGS}/uvicorn.log 2>&1 < /dev/null &
  sleep 10
  if curl -s -o /dev/null --max-time 3 http://127.0.0.1:${REMOTE_API_PORT}/docs; then
    echo '[远程] 后端已启动'
  else
    echo '[远程] 启动失败，日志见下'
  fi
fi
echo '[远程] 日志尾部：'
tail -12 ${REMOTE_LOGS}/uvicorn.log 2>/dev/null || true
"
}

start_remote_workers() {
  remote "
mkdir -p ${REMOTE_LOGS}
cd ${REMOTE_ROOT}/backend || exit 1
set -a
. ${REMOTE_ROOT}/scripts/remote/runtime.env
set +a
worker_count=\${PICKLEBALL_REMOTE_WORKER_COUNT:-1}
for index in \$(seq 1 \"\$worker_count\"); do
  pid_file=${REMOTE_LOGS}/analysis-worker-\$index.pid
  worker_pid=\$(cat \"\$pid_file\" 2>/dev/null || true)
  if [ -n \"\$worker_pid\" ] && [ -r /proc/\$worker_pid/cmdline ] &&
     tr '\\0' ' ' < /proc/\$worker_pid/cmdline | grep -q 'app.analysis_worker'; then
    echo \"[远程] 分析 Worker \$index 已运行 (PID \$worker_pid)\"
    continue
  fi
  setsid nohup env PICKLEBALL_ANALYSIS_WORKER_ID=remote-worker-\$index \\
    ${REMOTE_ENV}/bin/python -m app.analysis_worker \\
    > ${REMOTE_LOGS}/analysis-worker-\$index.log 2>&1 < /dev/null &
  worker_pid=\$!
  echo \"\$worker_pid\" > \"\$pid_file\"
  echo \"[远程] 分析 Worker \$index 已启动 (PID \$worker_pid)\"
done
"
}

stop_remote_workers() {
  remote "
for pid_file in ${REMOTE_LOGS}/analysis-worker-*.pid; do
  [ -f \"\$pid_file\" ] || continue
  worker_pid=\$(cat \"\$pid_file\" 2>/dev/null || true)
  if [ -n \"\$worker_pid\" ] && [ -r /proc/\$worker_pid/cmdline ] &&
     tr '\\0' ' ' < /proc/\$worker_pid/cmdline | grep -q 'app.analysis_worker'; then
    kill \"\$worker_pid\"
    echo \"[远程] 已停止分析 Worker PID \$worker_pid\"
  fi
  rm -f \"\$pid_file\"
done
"
}

stop_remote_api() {
  remote "
# 模式里的 [.] 是为了避免 pkill 匹配到本会话自身的命令行而自杀。
pkill -f '[u]vicorn app[.]main:app' >/dev/null 2>&1 && echo '[远程] 已发送停止信号' || echo '[远程] 未发现后端进程'
sleep 2
if curl -s -o /dev/null --max-time 3 http://127.0.0.1:${REMOTE_API_PORT}/docs; then
  echo '[远程] 警告：端口仍在响应'
else
  echo '[远程] 端口已释放'
fi
"
}

start_tunnel() {
  if tunnel_alive; then
    echo "[本地] 隧道已在运行（${LOCAL_API_PORT} 已在监听）"
    return 0
  fi
  # 用 ssh -f 让 ssh 自己后台化并脱离终端，比 `nohup ... &` 更不容易被父 shell 回收。
  ssh -f -N "${SSH_BASE[@]}" -o ExitOnForwardFailure=yes \
    -L "${LOCAL_API_PORT}:127.0.0.1:${REMOTE_API_PORT}" \
    "${TARGET}" || { echo "[本地] 隧道启动失败"; return 1; }
  sleep 2
  if tunnel_alive; then
    echo "[本地] 隧道已建立：127.0.0.1:${LOCAL_API_PORT} → 远程 127.0.0.1:${REMOTE_API_PORT}"
    echo "[本地] 提示：本机若有 HTTP 代理，curl 访问需加 --noproxy '*'"
  else
    echo "[本地] 隧道未生效，请确认 ${LOCAL_API_PORT} 端口未被其它进程占用"
    return 1
  fi
}

stop_tunnel() {
  local pids
  pids="$(lsof -nP -iTCP:"${LOCAL_API_PORT}" -sTCP:LISTEN -t 2>/dev/null || true)"
  if [[ -n "${pids}" ]]; then
    # shellcheck disable=SC2086
    kill ${pids} 2>/dev/null || true
    echo "[本地] 隧道已关闭 (PID $(echo "${pids}" | tr '\n' ' '))"
  else
    echo "[本地] 未发现隧道进程"
  fi
}

status() {
  echo "=== 远程后端 ==="
  remote "curl -s -o /dev/null --max-time 3 http://127.0.0.1:${REMOTE_API_PORT}/docs && echo '运行中' || echo '未运行'; \
    echo '环境：'; ${REMOTE_ENV}/bin/python -V; \
    echo '设备：'; ${REMOTE_ENV}/bin/python -c \"import torch;print('cuda=',torch.cuda.is_available())\" 2>/dev/null || echo 'torch 未就绪'"
  echo "=== 本地隧道 ==="
  if tunnel_alive; then
    echo "运行中（${LOCAL_API_PORT} 监听中）"
  else
    echo "未运行"
  fi
  echo "=== 连通性 ==="
  curl -s --noproxy '*' -o /dev/null -w "本地 127.0.0.1:${LOCAL_API_PORT}/docs → %{http_code}\n" \
    --max-time 6 "http://127.0.0.1:${LOCAL_API_PORT}/docs" 2>/dev/null || echo "本地端口无响应"
}

case "${1:-}" in
  start)  start_remote_api; start_remote_workers; start_tunnel ;;
  stop)   stop_tunnel; stop_remote_workers; stop_remote_api ;;
  status) status ;;
  logs)   remote "tail -40 ${REMOTE_LOGS}/uvicorn.log" ;;
  *)      sed -n '2,16p' "${BASH_SOURCE[0]}"; exit 1 ;;
esac
