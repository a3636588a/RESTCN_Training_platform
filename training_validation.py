"""Pure training configuration validation shared by UI and script callers."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Tuple


TRAINING_ISSUE_DATA_DIR_NOT_FOUND = "data_dir_not_found"
TRAINING_ISSUE_LABELS_EMPTY = "labels_empty"
TRAINING_ISSUE_LABEL_IDS_NONCONTIGUOUS = "label_ids_noncontiguous"


@dataclass(frozen=True)
class TrainingConfigIssue:
    """One validation failure with a stable code and user-facing message."""

    code: str
    message: str


def training_validate_config(config: Any) -> Tuple[TrainingConfigIssue, ...]:
    """Return every deterministic configuration issue without UI side effects.

    The function reports facts only. Decisions such as offering automatic label
    ID reassignment belong to the caller because they require user consent.
    """

    issues = []
    data_dir_value = getattr(config, "data_dir", None)
    data_dir = Path(data_dir_value) if data_dir_value else None
    if data_dir is None or not data_dir.exists():
        issues.append(TrainingConfigIssue(
            code=TRAINING_ISSUE_DATA_DIR_NOT_FOUND,
            message=f"data_dir not found: {data_dir_value or '<empty>'}",
        ))

    label_defs = getattr(config, "label_defs", None) or []
    if not label_defs:
        issues.append(TrainingConfigIssue(
            code=TRAINING_ISSUE_LABELS_EMPTY,
            message="Label table empty.",
        ))
        return tuple(issues)

    label_ids = sorted(int(label["id"]) for label in label_defs)
    expected_ids = list(range(len(label_ids)))
    if label_ids != expected_ids:
        # Consecutive zero-based IDs are shared by model output indices and MCU
        # labels; a gap would make the two sides interpret classes differently.
        issues.append(TrainingConfigIssue(
            code=TRAINING_ISSUE_LABEL_IDS_NONCONTIGUOUS,
            message=f"Gesture IDs are NOT continuous: {label_ids}",
        ))

    return tuple(issues)
