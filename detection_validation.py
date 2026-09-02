"""Pure Detect configuration validation shared by UI and script callers."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Tuple


@dataclass(frozen=True)
class DetectionConfigIssue:
    """One Detect configuration issue with a stable machine-readable code."""

    code: str
    message: str


def detection_validate_config(config: Any, source: str = "serial") -> Tuple[DetectionConfigIssue, ...]:
    """Return deterministic issues without importing Qt or opening resources."""

    issues = []
    selected_source = (source or "").strip().lower()
    if selected_source not in {"serial", "csv"}:
        return (DetectionConfigIssue(
            code="source_unsupported",
            message=f"Unsupported Detect source: {source}",
        ),)

    if selected_source == "serial":
        port = str(getattr(config, "serial_port", getattr(config, "port", "")) or "").strip()
        if not port:
            issues.append(DetectionConfigIssue(code="port_empty", message="PORT is empty"))
        baud = getattr(config, "baud", 0)
        if not isinstance(baud, int) or isinstance(baud, bool) or baud <= 0:
            issues.append(DetectionConfigIssue(
                code="baud_invalid",
                message=f"BAUD must be a positive integer: {baud}",
            ))

    for field_name, legacy_field_name, code, label in (
        ("model_path", "model_path", "model_path_not_found", "MODEL_PATH"),
        ("metadata_path", "meta_path", "metadata_path_not_found", "METADATA_PATH"),
    ):
        path_value = getattr(config, field_name, getattr(config, legacy_field_name, None))
        if not path_value or not Path(path_value).exists():
            issues.append(DetectionConfigIssue(
                code=code,
                message=f"{label} not found: {path_value or '<empty>'}",
            ))

    tier_data = getattr(config, "post_tier_data", None)
    if not isinstance(tier_data, dict):
        issues.append(DetectionConfigIssue(
            code="post_tier_data_invalid",
            message="POST_TIER_DATA must be a dictionary",
        ))

    for field_name, code, label in (
        ("post_alpha", "post_alpha_invalid", "POST_ALPHA"),
        ("post_exit_thresh", "post_exit_thresh_invalid", "POST_EXIT_THRESH"),
    ):
        value = getattr(config, field_name, None)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not 0.0 <= float(value) <= 1.0:
            issues.append(DetectionConfigIssue(
                code=code,
                message=f"{label} must be between 0 and 1: {value}",
            ))

    margin = getattr(config, "post_margin", None)
    if not isinstance(margin, (int, float)) or isinstance(margin, bool) or margin < 0:
        issues.append(DetectionConfigIssue(
            code="post_margin_invalid",
            message=f"POST_MARGIN must be >= 0: {margin}",
        ))

    slope_factor = getattr(config, "post_slope_factor", None)
    if not isinstance(slope_factor, (int, float)) or isinstance(slope_factor, bool) or slope_factor <= 0:
        issues.append(DetectionConfigIssue(
            code="post_slope_factor_invalid",
            message=f"POST_SLOPE_FACTOR must be > 0: {slope_factor}",
        ))

    infer_stride = getattr(config, "infer_stride", None)
    if not isinstance(infer_stride, int) or isinstance(infer_stride, bool) or infer_stride < 1:
        issues.append(DetectionConfigIssue(
            code="infer_stride_invalid",
            message=f"INFER_STRIDE must be a positive integer: {infer_stride}",
        ))

    if bool(getattr(config, "enable_gain_map", False)):
        min_span = getattr(config, "min_span_b", None)
        gain_min = getattr(config, "gain_clamp_min", None)
        gain_max = getattr(config, "gain_clamp_max", None)
        if not isinstance(min_span, (int, float)) or isinstance(min_span, bool) or min_span < 0:
            issues.append(DetectionConfigIssue(
                code="min_span_b_invalid",
                message=f"MIN_SPAN_B must be >= 0: {min_span}",
            ))
        if (
            not isinstance(gain_min, (int, float))
            or isinstance(gain_min, bool)
            or not isinstance(gain_max, (int, float))
            or isinstance(gain_max, bool)
            or gain_min >= gain_max
        ):
            issues.append(DetectionConfigIssue(
                code="gain_clamp_invalid",
                message="GAIN_CLAMP min must be < max",
            ))

    return tuple(issues)
