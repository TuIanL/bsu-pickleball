"""远程算力服务器环境自检。

在 backend/ 目录下运行：
    /root/autodl-tmp/envs/pickleball/bin/python scripts/remote/verify_env.py

检查内容：
  1. 后端配置能否导入（验证依赖是否齐全）
  2. 五个模型权重是否齐备
  3. 推理设备（无卡模式应为 CPU）
  4. ultralytics 的三个 YOLO 模型能否真正加载并推理
  5. RTMPose-26 能否通过 mmpose 加载（验证 mmcv-lite 是否足够）
  6. match_state 的 R3D-18 包能否加载

任一项失败都以非零退出码结束，便于脚本化判定。
"""
from __future__ import annotations

import gc
import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

os.environ.setdefault("PICKLEBALL_ENABLE_MODEL_INFERENCE", "true")

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok, detail))
    suffix = f" — {detail}" if detail else ""
    print(f"  [{'OK  ' if ok else 'FAIL'}] {name}{suffix}", flush=True)


def main() -> int:
    started = time.time()

    print("=== 1. 导入后端配置 ===", flush=True)
    try:
        from app.core.config import get_settings
        settings = get_settings()
        model_dir = Path(settings.model_dir).resolve()
        check("import app.core.config", True, f"model_dir={model_dir}")
    except Exception as exc:
        check("import app.core.config", False, repr(exc))
        print("\n配置导入失败，后续检查跳过。")
        return 1

    print("=== 2. 模型权重就位情况 ===", flush=True)
    for label, raw in (
        ("RTMPose 配置", settings.rtmpose_config_path),
        ("RTMPose 权重", settings.rtmpose_checkpoint_path),
        ("球检测权重", settings.ball_model_path),
        ("场地线权重", settings.court_line_model_path),
    ):
        path = Path(raw) if raw else None
        if path is not None and path.exists():
            check(label, True, f"{path.name} ({path.stat().st_size / 1e6:.1f} MB)")
        else:
            check(label, False, str(path))

    person_weight = BACKEND_ROOT / "yolov8n.pt"
    check(
        "人员检测权重",
        person_weight.exists(),
        f"{person_weight.name} ({person_weight.stat().st_size / 1e6:.1f} MB)"
        if person_weight.exists()
        else str(person_weight),
    )

    print("=== 3. 推理设备 ===", flush=True)
    try:
        import torch
        check("import torch", True, torch.__version__)
        print(f"       cuda available: {torch.cuda.is_available()}")
        print(f"       cpu threads: {torch.get_num_threads()}")
    except Exception as exc:
        check("import torch", False, repr(exc))
        return 1

    print("=== 4. ultralytics YOLO 加载与推理 ===", flush=True)
    try:
        import numpy as np
        from ultralytics import YOLO

        blank = np.zeros((480, 640, 3), dtype=np.uint8)
        for label, weight in (
            ("人员 YOLO", person_weight),
            ("球 YOLO", Path(settings.ball_model_path) if settings.ball_model_path else None),
            ("场地线 YOLO", Path(settings.court_line_model_path) if settings.court_line_model_path else None),
        ):
            if weight is None or not weight.exists():
                check(label, False, "权重不存在")
                continue
            try:
                model = YOLO(str(weight))
                model(blank, verbose=False, device="cpu")
                check(label, True, "加载并完成一次推理")
                # 无卡模式容器 memory.max 仅 2GB，逐个释放，避免模型累积后触发 OOM Killer
                del model
                gc.collect()
            except Exception as exc:
                check(label, False, repr(exc))
    except Exception as exc:
        check("import ultralytics", False, repr(exc))

    print("=== 5. RTMPose-26 加载（校验 mmcv-lite 是否够用） ===", flush=True)
    try:
        from app.vision.pose.rtmpose26_adapter import RTMPose26Adapter

        adapter = RTMPose26Adapter(
            config_path=settings.rtmpose_config_path,
            checkpoint_path=settings.rtmpose_checkpoint_path,
            device="cpu",
        )
        model = adapter._load_model()
        check("RTMPose26Adapter._load_model", model is not None, type(model).__name__)
        del model, adapter
        gc.collect()
    except Exception as exc:
        check("RTMPose26Adapter._load_model", False, repr(exc))

    print("=== 6. match_state R3D-18 包加载 ===", flush=True)
    try:
        from app.vision.match_state.package import load_production_package
        from app.vision.match_state.torch_adapter import load_model as load_state_model

        # 注意：该字段是相对「项目根」的路径，与 model_dir 的 "../models"（相对 backend）
        # 语义不同，不要拼到 BACKEND_ROOT 上。
        package_root = Path(settings.match_state_segmentation_package_dir)
        if not package_root.is_absolute():
            package_root = PROJECT_ROOT / package_root
        if package_root.exists():
            package = load_production_package(package_root)
            model = load_state_model(package, device="cpu")
            check("match_state 模型加载", model is not None, type(model).__name__)
            del model
            gc.collect()
        else:
            check("match_state 模型加载", False, f"包目录不存在: {package_root}")
    except Exception as exc:
        check("match_state 模型加载", False, repr(exc))

    print("\n=== 汇总 ===", flush=True)
    failed = [name for name, ok, _ in RESULTS if not ok]
    for name, ok, detail in RESULTS:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f" ({detail})" if not ok and detail else ""))
    print(f"\n合计 {len(RESULTS)} 项，通过 {len(RESULTS) - len(failed)} 项，失败 {len(failed)} 项")
    print(f"耗时 {time.time() - started:.1f}s", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
