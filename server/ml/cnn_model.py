"""Small 2D CNN for two-receiver CSI activity classification."""

from __future__ import annotations

from dataclasses import asdict, dataclass

import torch
from torch import nn

from ml.constants import CLASS_NAMES


@dataclass(frozen=True)
class CNNModelConfig:
    input_receivers: int = 2
    input_subcarriers: int = 20
    class_count: int = len(CLASS_NAMES)
    dropout: float = 0.30
    normalization_layer: str = "batchnorm"

    def __post_init__(self):
        if self.input_receivers <= 0 or self.input_subcarriers <= 0:
            raise ValueError("CNN input dimensions must be positive")
        if self.class_count < 2:
            raise ValueError("class_count must be at least two")
        if not 0.0 <= self.dropout < 1.0:
            raise ValueError("dropout must be in [0, 1)")
        if self.normalization_layer not in {"batchnorm", "groupnorm"}:
            raise ValueError("normalization_layer must be batchnorm or groupnorm")

    def to_dict(self) -> dict:
        return asdict(self)


class SmallCSIConvNet(nn.Module):
    """Predict activity logits from [batch, receiver, time, subcarrier]."""

    def __init__(self, config: CNNModelConfig = CNNModelConfig()):
        super().__init__()
        self.config = config

        def normalization(channels: int) -> nn.Module:
            if config.normalization_layer == "batchnorm":
                return nn.BatchNorm2d(channels)
            groups = 8 if channels >= 32 else 4
            return nn.GroupNorm(groups, channels)

        self.features = nn.Sequential(
            nn.Conv2d(config.input_receivers, 16, kernel_size=(5, 3), padding=(2, 1)),
            normalization(16),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(kernel_size=(2, 2)),
            nn.Conv2d(16, 32, kernel_size=(5, 3), padding=(2, 1)),
            normalization(32),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(kernel_size=(2, 2)),
            nn.Conv2d(32, 64, kernel_size=(3, 3), padding=1),
            normalization(64),
            nn.ReLU(inplace=True),
            nn.AdaptiveAvgPool2d((1, 1)),
        )
        self.classifier = nn.Sequential(
            nn.Flatten(),
            nn.Dropout(config.dropout),
            nn.Linear(64, config.class_count),
        )

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        if inputs.ndim != 4:
            raise ValueError(
                "CNN input must have shape [batch, receiver, time, subcarrier]"
            )
        if inputs.shape[1] != self.config.input_receivers:
            raise ValueError(
                f"expected {self.config.input_receivers} receivers, got {inputs.shape[1]}"
            )
        if inputs.shape[3] != self.config.input_subcarriers:
            raise ValueError(
                f"expected {self.config.input_subcarriers} subcarriers, "
                f"got {inputs.shape[3]}"
            )
        if not torch.isfinite(inputs).all():
            raise ValueError("CNN input contains NaN or Inf")
        return self.classifier(self.features(inputs))
