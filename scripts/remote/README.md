# 远程算力服务器（AutoDL）使用说明

把视频分析的重计算放到远程实例上执行，算完把结果拉回本地。

---

## 一、远端布局

| 路径 | 用途 | 是否持久 |
|---|---|---|
| `/root/autodl-tmp/pre-pickleball` | 项目根：代码 + `models/` + `backend/data/` | 是（数据盘） |
| `/root/autodl-tmp/envs/pickleball` | Python 3.11 运行环境 | 是（数据盘） |
| `/root/autodl-tmp/logs` | 安装日志与服务日志 | 是（数据盘） |
| `/root/autodl-tmp/pip-cache` | pip 缓存 | 可删 |

**为什么全部放在 `/root/autodl-tmp`**：该路径挂载数据盘（50G）。系统盘 `/` 只有 30G，装不下 torch 的 CUDA 依赖全家桶（约 5G+）。不要把环境或大文件写进 `/root/` 以外的系统盘路径。

---

## 二、环境说明

| 项 | 值 |
|---|---|
| 系统 | Ubuntu 22.04.5 |
| Python | 3.11.16（conda env，与本地 `backend/.venv` 的 3.11.15 对齐） |
| 依赖来源 | 严格按本地 `backend/.venv` 的 `pip freeze` 版本安装 |
| torch | 2.13.0+cu126 + torchvision 0.28.0+cu126（匹配实例驱动的 CUDA 12.8） |
| 视觉栈 | ultralytics 8.4.115、mmcv 2.1.0、mmpose 1.3.2、mmdet 3.3.0、mmengine 0.10.7 |
| 认证 | 专用 SSH 密钥（路径见 `remote.env` 的 `REMOTE_KEY`，已免密） |

### 安装脚本（远端执行，可重复运行）

```bash
cd /root/autodl-tmp/pre-pickleball/scripts/remote
bash 01_install_core.sh          # 核心后端依赖
bash 02_install_torch.sh         # torch / torchvision（匹配驱动的 cu126）
bash 03_install_vision_pose.sh   # ultralytics + mmpose 技术栈
bash 05_install_mmcv_ops.sh      # 编译含 CPU 算子的 mmcv（替换 mmcv-lite）
```

### 环境自检

```bash
cd /root/autodl-tmp/pre-pickleball/backend
/root/autodl-tmp/envs/pickleball/bin/python \
  /root/autodl-tmp/pre-pickleball/scripts/remote/verify_env.py
```

逐项检查配置导入、五个模型权重、推理设备、三套 YOLO 加载与推理、RTMPose 加载、match_state 包加载；任一项失败以非零码退出。

### torch 版本选择说明（重要，别装错）

本实例的 NVIDIA 驱动是 **570.124.04**，可支持的 CUDA runtime 上限为 **12.8**。

PyPI 上 `torch==2.13.0` 默认是 `+cu130`（CUDA 13）。装上去虽然能正常 `import`，
但会警告 `The NVIDIA driver on your system is too old (found version 12080)`，
**切到有卡模式后 GPU 依然不可用**。所以必须从 cu126 轮子索引安装：版本号仍是
2.13.0（与本地一致），CUDA runtime 降到 12.6，在 12.8 驱动上受 minor version
compatibility 支持。

```bash
pip install --index-url https://download.pytorch.org/whl/cu126 \
  --extra-index-url https://pypi.tuna.tsinghua.edu.cn/simple \
  torch==2.13.0 torchvision==0.28.0
```

要换 CUDA 版本，改 `02_install_torch.sh` 里的 `TORCH_INDEX`（cu126 / cu128 / cpu）。
注意 cu128 索引里没有 2.13.0（最高 2.11.0），若必须用 cu128 得同时降 torch 版本，
而 mmcv 2.1.0 对 torch 版本敏感，降级前先确认姿态链路仍可加载。

### mmcv 的坑（这个必须看）

`pip install mmcv==2.1.0` 在此环境有两条死路，最终解法是**编译含 CPU 算子的 mmcv**：

1. **PyPI 上的 mmcv 2.x 只有 sdist。** 源码在 `MMCV_WITH_OPS=0` 时会把分发名改成 `mmcv-lite`，与需求名 `mmcv` 不一致，pip 判定 `inconsistent name` 后直接丢弃该文件，最后报 `No matching distribution found for mmcv==2.1.0`。

2. **不能止步于 mmcv-lite。** 官方 PyPI 上确实有独立的 `mmcv-lite` 包（纯 Python、装完提供同名的 `mmcv` 模块，`import mmcv` 正常、版本号也是 2.1.0），看起来够用——但 mmpose 1.3.2 的 `mmpose/models/heads/__init__.py` 会**无条件**导入 `transformer_heads`，其中 `edpose_head.py:14` 执行 `from mmcv.ops import MultiScaleDeformableAttention`，而 `mmcv/ops/__init__.py` 又依赖编译扩展 `mmcv._ext`。mmcv-lite 没有这个扩展，于是 `import mmcv._ext` 抛 `ModuleNotFoundError`，连带 `from mmpose.apis import init_model` 失败，**整条 RTMPose 链路不可用**。

3. **必须先把 setuptools 降到 80.x。** mmcv 2.1.0 的 `setup.py` 顶部是 `from pkg_resources import ...`，而 setuptools 81+ 已移除 `pkg_resources` 模块，会直接报 `ModuleNotFoundError: No module named 'pkg_resources'`。

正确做法（已固化进 `05_install_mmcv_ops.sh`）：

```bash
pip install "setuptools==80.10.2" "wheel==0.47.0" "ninja==1.13.0" "pybind11>=2.6.0"
pip uninstall -y mmcv-lite          # 两者提供同名 mmcv 模块，不能共存
cd /tmp && MAX_JOBS=32 MMCV_WITH_OPS=1 pip install --no-build-isolation mmcv==2.1.0
```

无卡模式没有 nvcc，因此只编译 CPU 算子，已足以支撑 RTMPose 推理。切到有卡模式后若要启用 CUDA 算子，在环境里补上 nvcc 再重编一次即可。

`MAX_JOBS=32` 是刻意压低的：本机 192 核，并行度拉满容易吃满内存触发 OOM。

---

## 三、日常使用

### 1. 启动远程后端并建立隧道

```bash
bash scripts/remote/serve.sh start
```

执行后：

- 远程以 `127.0.0.1:8000` 启动 uvicorn（仅服务器回环，不经公网暴露）；
- 本地建立 SSH 隧道，`http://127.0.0.1:8100` 即为远程 API 入口。

其他子命令：

```bash
bash scripts/remote/serve.sh status   # 查看两端状态
bash scripts/remote/serve.sh logs     # 查看远程后端日志
bash scripts/remote/serve.sh stop     # 停止
```

### 2. 同步文件

```bash
bash scripts/remote/sync.sh code                    # 推送代码（本地为权威）
bash scripts/remote/sync.sh models                  # 推送模型权重
bash scripts/remote/sync.sh push-video <视频路径>    # 上传待分析视频
bash scripts/remote/sync.sh pull-results            # 拉回全部分析结果
bash scripts/remote/sync.sh pull-job <job_id>       # 拉回单个任务产物
bash scripts/remote/sync.sh disk                    # 查看远程磁盘占用
```

同步方向是单向的：代码与模型本地 → 远程；分析结果远程 → 本地。脚本不使用 `--delete`，不会误删任何一侧的文件。

### 3. 让本地前端连接远程后端

前端默认连本地后端。要指向远程，需将 API 基址改为 `http://127.0.0.1:8100`（隧道端口），并保持 `serve.sh start` 运行。

---

## 四、已知限制（务必先看第 1 条）

1. **无卡模式内存只有 2GB，跑不动实际推理。** 容器 cgroup `memory.max` = 2147483648 字节（2GB），而 `import torch` 单独就占 498MB，加载一个 YOLO 权重后到 612MB，**做一次推理即被 OOM Killer 杀掉**（进程显示 `Killed`，退出码 137）。实测连续加载三个 YOLO + RTMPose 的自检脚本跑到一半就被杀。也就是说，环境本身配置正确（服务能起、模型能加载、API 可访问），但**必须切到有卡模式**才能真正执行分析任务。这不是配置问题，是实例规格问题。

2. **数据库中的历史路径在远程会失效。** `capture_takes.session_dir` 等字段存的是 macOS 绝对路径（外接盘 `/Volumes/Elements/...`、pytest 临时目录），迁移到 Linux 后这些记录指向不存在的文件。上传类任务不受影响；依赖外接盘双摄素材的历史任务需要在远程重新提供素材。

3. **远程后端与本地后端不共享数据库变更。** 两边各自维护 `backend/data/app.sqlite3`。在远程产生的任务记录不会自动回到本地，反之亦然。

4. **无卡模式下没有 GPU，且 mmcv 是纯 Python 版**（自定义算子为占位实现，见上文）。切到有卡模式后建议执行 `05_install_mmcv_ops.sh` 重编 mmcv，还原完整算子能力。

5. **外接盘素材无法直接参与远程计算。** 双摄原始素材在 `/Volumes/Elements` 上，需先上传到远程才能分析。

6. **本机若有 HTTP 代理，curl 访问本地隧道端口会返回 502**（请求被代理截走）。需加 `--noproxy '*'`；`serve.sh status` 已内置该参数。

---

## 五、连接信息

实际的实例地址、端口、用户名与密钥路径**不入库**，统一由 `remote.env` 提供
（见 `remote.env.example`）。脚本一律 source 该文件取值，不要在脚本或文档里硬编码主机。

| 项 | 来源 |
|---|---|
| 主机 | `remote.env` 的 `REMOTE_HOST` |
| 端口 | `remote.env` 的 `REMOTE_PORT` |
| 用户 | `remote.env` 的 `REMOTE_USER` |
| 密钥 | `remote.env` 的 `REMOTE_KEY`（专用 SSH 密钥，免密登录） |

首次接入：复制模板并填入实例信息。

```bash
cp scripts/remote/remote.env.example scripts/remote/remote.env
$EDITOR scripts/remote/remote.env
```

免密登录验证（用 `remote.env` 里的值替换占位符）：

```bash
source scripts/remote/remote.env
ssh -i "${REMOTE_KEY}" -p "${REMOTE_PORT}" "${REMOTE_USER}@${REMOTE_HOST}" 'echo ok'
```
