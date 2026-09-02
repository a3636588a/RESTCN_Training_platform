"""Framework-independent structured outputs for model detection."""

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class ModelPrediction:
    """Raw model output before label mapping or Detect API post-processing."""

    pred_id: int
    confidence: float
    probabilities: tuple[float, ...]

    def to_dict(self) -> Dict[str, Any]:
        """Return serialization-friendly fields for non-Python applications."""
        return asdict(self)


@dataclass(frozen=True)
class DetectionResult:
    """Terminal state returned by a complete UART or CSV detection operation."""

    status: str
    source: str
    message: Optional[str] = None
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        result = dict(self.payload)
        result.update({"status": self.status, "source": self.source})
        if self.message:
            result["message"] = self.message
        return result
