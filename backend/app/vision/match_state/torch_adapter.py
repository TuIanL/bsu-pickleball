"""Optional torch adapter for a signed formal match-state package.

The module is intentionally independent from ``scripts/train_*``. Deployments
can point ``runtime.entrypoint`` at :func:`load_model`; preprocessing remains a
caller concern so CaptureTake timing/provenance is preserved at the sampler
boundary.
"""

from __future__ import annotations

from typing import Any, Iterable

from .package import ModelPackageError, ProductionModelPackage


def load_model(package: ProductionModelPackage, device: str):
    """Load an RGB R3D-18 state-dict package and expose ``predict_samples``."""
    try:
        import torch
        from torch import nn
        from torchvision.models.video import r3d_18
    except Exception as exc:  # pragma: no cover - optional deployment dependency
        raise ModelPackageError(f"torch 运行时不可用: {exc}", code="model_unavailable") from exc

    class RGBLateFusion(nn.Module):
        def __init__(self, class_count: int) -> None:
            super().__init__()
            self.encoder = r3d_18(weights=None)
            feature_dim = int(self.encoder.fc.in_features)
            self.encoder.fc = nn.Identity()
            self.head = nn.Linear(feature_dim, class_count)

        def forward(self, inputs):
            # [batch, camera, time, channels, height, width]
            logits = []
            for camera_index in range(inputs.shape[1]):
                view = inputs[:, camera_index].permute(0, 2, 1, 3, 4)
                logits.append(self.head(self.encoder(view)))
            return torch.stack(logits, dim=1).mean(dim=1)

        def predict_samples(self, samples: Iterable[dict[str, Any]]):
            samples = tuple(samples)
            tensors = []
            for sample in samples:
                tensor = sample.get("model_input")
                if tensor is None:
                    tensor = sample.get("tensor")
                if tensor is None:
                    raise ModelPackageError(
                        "正式 RGB 适配器需要 sample.model_input（双摄张量）",
                        code="input_unavailable",
                    )
                if not torch.is_tensor(tensor):
                    tensor = torch.as_tensor(tensor)
                tensors.append(tensor)
            if not tensors:
                return []
            batch = torch.stack(tensors, dim=0).to(device)
            with torch.inference_mode():
                values = torch.softmax(self(batch), dim=-1).detach().cpu().tolist()
            return [
                {
                    **sample,
                    "state_probabilities": {
                        "rally_active": float(probabilities[0]),
                        "non_play": float(probabilities[1]) if len(probabilities) > 1 else 0.0,
                        "unknown": float(probabilities[2]) if len(probabilities) > 2 else 0.0,
                    },
                }
                for sample, probabilities in zip(samples, values, strict=True)
            ]

    try:
        checkpoint = torch.load(
            str(package.directory / str(package.manifest["artifacts"]["weights"])),
            map_location="cpu",
            weights_only=False,
        )
        state_dict = checkpoint.get("model_state_dict", checkpoint) if isinstance(checkpoint, dict) else checkpoint
        head_weight = state_dict.get("head.weight") if isinstance(state_dict, dict) else None
        checkpoint_class_count = int(head_weight.shape[0]) if getattr(head_weight, "ndim", 0) == 2 else 0
        declared_class_count = len(package.manifest.get("classes", []))
        class_count = checkpoint_class_count or declared_class_count
        if class_count not in {2, 3}:
            raise ModelPackageError(
                f"模型输出类别数不受支持: {class_count}",
                code="model_unavailable",
            )
        model = RGBLateFusion(class_count)
        model.load_state_dict(state_dict)
        return model.to(device).eval()
    except ModelPackageError:
        raise
    except Exception as exc:
        raise ModelPackageError(f"模型权重与运行时结构不兼容: {exc}", code="model_unavailable") from exc
