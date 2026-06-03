"""可选 self-attention 球员选择模型骨架。

该模块只定义训练/推理边界，不在默认分析路径中强制导入 torch。
"""

from __future__ import annotations

FEATURE_NAMES = [
    "bbox_x1",
    "bbox_y1",
    "bbox_x2",
    "bbox_y2",
    "confidence",
    "court_x",
    "court_y",
    "target_court_occupancy",
    "target_court_distance",
    "mean_speed",
    "continuity",
]


def build_model(feature_dim: int | None = None, hidden_dim: int = 64, heads: int = 4, layers: int = 2):
    """Build a minimal Transformer encoder classifier when torch is available."""

    try:
        import torch
        from torch import nn
    except Exception as exc:  # noqa: BLE001 - this module is optional.
        raise RuntimeError("PyTorch is required to build the attention player selector") from exc

    input_dim = feature_dim or len(FEATURE_NAMES)

    class AttentionPlayerSelectorModel(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.input_projection = nn.Linear(input_dim, hidden_dim)
            encoder_layer = nn.TransformerEncoderLayer(
                d_model=hidden_dim,
                nhead=heads,
                dim_feedforward=hidden_dim * 4,
                batch_first=True,
            )
            self.encoder = nn.TransformerEncoder(encoder_layer, num_layers=layers)
            self.classifier = nn.Linear(hidden_dim, 4)

        def forward(self, features: torch.Tensor) -> torch.Tensor:
            encoded = self.encoder(self.input_projection(features))
            return self.classifier(encoded)

    return AttentionPlayerSelectorModel()
