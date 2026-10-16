"""Common training entry point shared by the GUI and non-UI callers."""

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

import training_contracts as contracts


__all__ = ["TrainingConfig", "training_run_from_config"]


@dataclass
class TrainingConfig:
    """Configuration shared by every training backbone and external caller."""

    data_dir: str = "."
    label_defs: Optional[List[Dict[str, Any]]] = None
    channels: Optional[List[int]] = None
    window_len: int = 40
    window_step: int = 2

    slope_factor: float = 20.0

    batch_size: int = 32
    epochs: int = 200
    learning_rate: float = 0.001
    label_smoothing: float = 0.08
    # Defaults preserve the historical split while allowing UI/CLI callers to
    # request a reproducible alternative without changing trainer internals.
    test_size: float = 0.20
    random_state: int = 42
    early_stop_patience: int = 15
    lr_patience: int = 10

    # XGBoost 專用參數；window_len、window_step、channels、test_size 與
    # random_state 則與其他 backbone 共用。
    xgboost_n_estimators: int = 300
    xgboost_max_depth: int = 5
    xgboost_learning_rate: float = 0.05
    xgboost_subsample: float = 0.8
    xgboost_colsample_bytree: float = 0.8
    xgboost_min_child_weight: float = 2.0
    xgboost_reg_lambda: float = 1.0
    xgboost_log_interval: int = 5
    xgboost_signal_mode: str = "dn"
    # 手勢差值不應為負時，將 ROW - MOVBASE 的負值截斷為 0。
    xgboost_negative_delta_mode: str = "clip_zero"
    # stats40 僅保留統計摘要；time140 保留分段摘要；wave215 保留各通道波形；
    # hybrid225 同時保留靜態統計、通道波形與跨通道動態關係。
    xgboost_feature_set: str = "hybrid225"
    # fatigue12: CH1 raw 壓力；ZIP 為獨立錄製批次，未指定則讀 data_dir CSV。
    fatigue_zip_paths: Optional[List[str]] = None
    fatigue_class_mode: str = "binary"
    fatigue_sample_rate_hz: float = 100.0
    fatigue_smooth_samples: int = 5
    fatigue_peak_prominence_fraction: float = 0.10
    fatigue_peak_distance_s: float = 0.10

    output_model_path: str = "gesture_model_cnn_v1.h5"
    output_metadata_path: str = "gesture_model_meta_cnn_v1.pkl"

    enable_augmentation: bool = True
    aug_copies: int = 10
    aug_delta_gain_min: float = 0.75
    aug_delta_gain_max: float = 1.25
    aug_span_gain_min: float = 0.8
    aug_span_gain_max: float = 1.2
    enable_offset_aug: bool = True
    aug_offset_sigma: float = 30.0
    aug_offset_clip: float = 100.0
    enable_time_warp: bool = True
    time_warp_min: float = 0.8
    time_warp_max: float = 1.3

    @property
    def ch_list(self) -> List[int]:
        return self.channels if self.channels else [1, 2, 3, 4, 5]

    @property
    def prefix_to_id(self) -> Dict[str, int]:
        if self.label_defs:
            return {
                str(row["prefix"]).lower().strip(): int(row["id"])
                for row in self.label_defs
                if str(row.get("prefix", "")).strip()
            }
        return {str(index): index for index in range(10)}

    @property
    def id_to_name(self) -> Dict[int, str]:
        if self.label_defs:
            return {
                int(row["id"]): str(row.get("name", row.get("prefix", row["id"])))
                for row in self.label_defs
            }
        return {index: str(index) for index in range(10)}

    # Read-only aliases keep existing integrations working while all new
    # callers use the same full path terminology as the result contracts.
    @property
    def out_model_path(self) -> str:
        return self.output_model_path

    @property
    def out_meta_path(self) -> str:
        return self.output_metadata_path

    @classmethod
    def xgboost_defaults(cls, **overrides) -> "TrainingConfig":
        """建立 XGBoost 的建議起始設定；傳入的欄位可覆寫任一預設值。"""

        values = {
            "channels": [1, 2, 3, 4, 5],
            "window_len": 50,
            "window_step": 3,
            "test_size": 0.30,
            "output_model_path": "gesture_xgboost_hybrid225.json",
            "output_metadata_path": "gesture_xgboost_hybrid225_labels.json",
            "xgboost_n_estimators": 300,
            "xgboost_max_depth": 5,
            "xgboost_learning_rate": 0.05,
            "xgboost_subsample": 0.8,
            "xgboost_colsample_bytree": 0.8,
            "xgboost_min_child_weight": 2.0,
            "xgboost_reg_lambda": 1.0,
            "xgboost_log_interval": 5,
            "xgboost_signal_mode": "dn",
            "xgboost_negative_delta_mode": "clip_zero",
            "xgboost_feature_set": "hybrid225",
        }
        values.update(overrides)
        return cls(**values)

    @classmethod
    def xgboost_fatigue_defaults(cls, **overrides) -> "TrainingConfig":
        """CH1 fatigue12；預設二分類，可指定 fatigue_class_mode='three_class'。"""
        values = dict(
            channels=[1], window_len=160, window_step=20, test_size=0.67,
            label_defs=[{"id": 0, "prefix": "normal", "name": "normal"},
                        {"id": 1, "prefix": "fatigue", "name": "fatigue"}],
            xgboost_feature_set="fatigue12", xgboost_signal_mode="raw",
            xgboost_negative_delta_mode="allow", enable_augmentation=False,
            xgboost_n_estimators=120, xgboost_max_depth=2,
            xgboost_learning_rate=0.05, xgboost_subsample=0.8,
            xgboost_colsample_bytree=0.9, xgboost_min_child_weight=2.0,
            xgboost_reg_lambda=5.0, xgboost_log_interval=5,
            output_model_path="fatigue_model.json", output_metadata_path="fatigue_meta.json",
        )
        values.update(overrides)
        if values.get("fatigue_class_mode") == "three_class" and "label_defs" not in overrides:
            values["label_defs"] = [{"id": i, "prefix": label, "name": label}
                                    for i, label in enumerate(("normal", "early_fatigue", "fatigue"))]
        return cls(**values)


def _training_resolve_model_path(config) -> str:
    """Mirror legacy trainer extension handling when normalizing old results."""
    model_path = str(config.output_model_path)
    if model_path.lower().endswith(".pkl"):
        return model_path[:-4] + ".keras"
    if not model_path.lower().endswith((".h5", ".keras")):
        return model_path + ".keras"
    return model_path


def training_run_from_config(
    config: TrainingConfig,
    backbone: str = "cnn",
    log_fn: Optional[Callable[[str], None]] = None,
    stop_event=None,
    progress_fn: Optional[Callable[[contracts.TrainingProgress], None]] = None,
) -> contracts.TrainingResult:
    """Run one supported backbone and return the same result contract.

    Cancellation is a normal lifecycle outcome rather than an error. The
    underlying trainers raise before artifact publication; this boundary turns
    that exception into a ``cancelled`` result for UI and script callers.
    """

    selected_backbone = (backbone or "cnn").strip().lower()
    if selected_backbone not in {"cnn", "ds_tcn", "xgboost"}:
        raise ValueError(f"Unsupported training backbone: {selected_backbone}")

    # Trainers import TrainingConfig from this module for one shared config
    # identity. Delay their imports until execution so the dependency cannot
    # form training_api -> trainer -> training_api during module initialization.
    import training_cnn as cnn_trainer
    import training_ds_tcn as ds_tcn_trainer
    import training_xgboost as xgboost_trainer

    try:
        if selected_backbone == "xgboost":
            raw_result = xgboost_trainer.training_run_xgboost(
                config,
                log_fn=log_fn,
                progress_fn=progress_fn,
                stop_event=stop_event,
            )
        elif selected_backbone == "ds_tcn":
            raw_result = ds_tcn_trainer.training_run_ds_tcn(
                config,
                log_fn=log_fn,
                progress_fn=progress_fn,
                stop_event=stop_event,
            )
        else:
            raw_result = cnn_trainer.training_run_cnn(
                config,
                log_fn=log_fn,
                progress_fn=progress_fn,
                stop_event=stop_event,
            )
    except contracts.TrainingCancelledError as exc:
        return contracts.TrainingResult(
            status="cancelled",
            backbone=selected_backbone,
            message=str(exc),
        )

    # Trainer dictionaries are intentionally normalized here so UI and external
    # applications only depend on the stable common result contract.
    report = raw_result.get("report") or {}
    macro_average = report.get("macro avg") or {}
    return contracts.TrainingResult(
        status="completed",
        backbone=selected_backbone,
        model_path=str(raw_result.get("model_path") or _training_resolve_model_path(config)),
        metadata_path=str(
            raw_result.get("metadata_path")
            or raw_result.get("meta_path")
            or config.output_metadata_path
        ),
        report_path=raw_result.get("report_path"),
        top_1_accuracy=report.get("accuracy"),
        precision=macro_average.get("precision"),
        recall=macro_average.get("recall"),
        f1_score=macro_average.get("f1-score"),
        validation_accuracy=(
            raw_result.get("validation_accuracy")
            if "validation_accuracy" in raw_result
            else raw_result.get("accuracy")
        ),
        training_time_seconds=(
            raw_result.get("training_time_seconds")
            if "training_time_seconds" in raw_result
            else raw_result.get("training_time")
        ),
    )
