from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional


class TrainingCancelledError(RuntimeError):
    """Raised when a requested cancellation must stop artifact publication."""



##Stand Output##
@dataclass(frozen=True)
class TrainingProgress:
    """Structured per-epoch metrics for non-UI training consumers."""

    epoch: int
    total_epochs: int
    loss: float
    accuracy: float
    validation_loss: float
    validation_accuracy: float

    def to_dict(self) -> Dict[str, Any]:
        """Return a serialization-friendly progress payload."""
        return asdict(self)


### stand Output ###
@dataclass(frozen=True)
class TrainingResult:
    """Stable result shared by every training backbone.

    ``status`` is ``completed`` only after artifacts have been published. A
    cancelled result intentionally carries no artifact paths so callers cannot
    mistake an interrupted model for a completed output.
    """

    status: str
    backbone: str
    model_path: Optional[str] = None
    metadata_path: Optional[str] = None
    report_path: Optional[str] = None
    top_1_accuracy: Optional[float] = None
    precision: Optional[float] = None
    recall: Optional[float] = None
    f1_score: Optional[float] = None
    validation_accuracy: Optional[float] = None
    training_time_seconds: Optional[float] = None
    message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert the immutable core result to the dict expected by Qt signals."""
        return asdict(self)

    # These aliases preserve callers written against the previous public result.
    @property
    def meta_path(self) -> Optional[str]:
        return self.metadata_path

    @property
    def accuracy(self) -> Optional[float]:
        return self.validation_accuracy

    @property
    def training_time(self) -> Optional[float]:
        return self.training_time_seconds


def training_raise_if_cancelled(stop_event) -> None:
    """Abort the current stage before it can publish partial training output."""
    if stop_event is not None and stop_event.is_set():
        raise TrainingCancelledError("Training cancelled by user.")
