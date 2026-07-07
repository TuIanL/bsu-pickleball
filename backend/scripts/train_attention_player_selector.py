"""Train the optional court-aware attention player selector.

This is a scaffold for future labeled data. It intentionally stays outside the
default runtime path so the product can use the rule selector without PyTorch.
"""

# 训练「球场感知 attention 球员选择器」的脚本（脚手架）。
# 说明：这是一个为「未来有标注数据」预留的占位实现。它刻意放在默认运行路径之外，
# 这样产品即使没有 PyTorch，也能使用基于规则的球员选择器。

from __future__ import annotations

import argparse
import json
from pathlib import Path

# 复用 attention_player_selector 里的 build_model（构建模型结构）。
from app.vision.player_tracking_engine.attention_player_selector import build_model


def main() -> None:
    parser = argparse.ArgumentParser(description="Train attention player selector from exported samples.")
    # 位置参数：由 player-selection-training-samples 导出的样本 JSON 文件。
    parser.add_argument("samples", type=Path, help="JSON file exported by player-selection-training-samples.")
    # 输出 checkpoint 路径。
    parser.add_argument("--output", type=Path, default=Path("attention_player_selector.pt"))
    args = parser.parse_args()

    # 读取样本 JSON。
    payload = json.loads(args.samples.read_text(encoding="utf-8"))
    # 只保留有明确标签的样本，丢弃标记为 "uncertain"（不确定）的。
    labeled = [sample for sample in payload.get("samples", []) if sample.get("label") != "uncertain"]
    if not labeled:
        raise SystemExit("No labeled samples found. Label samples before training.")

    # 构建模型（此时只是空结构，尚未训练）。
    model = build_model()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        import torch
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"PyTorch is required for training: {exc}") from exc

    # 保存一个「未训练」的脚手架 checkpoint（含模型结构与标签列表）。
    torch.save({"model_state": model.state_dict(), "labels": payload.get("labels", [])}, args.output)
    print(f"Wrote untrained scaffold checkpoint to {args.output}. Add training loop when labeled data is ready.")


if __name__ == "__main__":
    main()
