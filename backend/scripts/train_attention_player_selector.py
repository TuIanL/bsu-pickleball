"""Train the optional court-aware attention player selector.

This is a scaffold for future labeled data. It intentionally stays outside the
default runtime path so the product can use the rule selector without PyTorch.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.vision.player_tracking_engine.attention_player_selector import build_model


def main() -> None:
    parser = argparse.ArgumentParser(description="Train attention player selector from exported samples.")
    parser.add_argument("samples", type=Path, help="JSON file exported by player-selection-training-samples")
    parser.add_argument("--output", type=Path, default=Path("attention_player_selector.pt"))
    args = parser.parse_args()

    payload = json.loads(args.samples.read_text(encoding="utf-8"))
    labeled = [sample for sample in payload.get("samples", []) if sample.get("label") != "uncertain"]
    if not labeled:
        raise SystemExit("No labeled samples found. Label samples before training.")

    model = build_model()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        import torch
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"PyTorch is required for training: {exc}") from exc

    torch.save({"model_state": model.state_dict(), "labels": payload.get("labels", [])}, args.output)
    print(f"Wrote untrained scaffold checkpoint to {args.output}. Add training loop when labeled data is ready.")


if __name__ == "__main__":
    main()
