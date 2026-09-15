"""XGBoost 40 維特徵手勢訓練器。"""

import json
import time
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.metrics import classification_report
from sklearn.model_selection import train_test_split
from xgboost import XGBClassifier
from xgboost.callback import TrainingCallback

from training_api import TrainingConfig
from training_contracts import TrainingProgress, training_raise_if_cancelled

FEATURE_TYPES = ("mean", "std", "peak_to_peak", "mean_abs_diff", "segment_1_mean", "segment_2_mean", "segment_3_mean", "segment_3_minus_1")


class XGBoostTrainingLogCallback(TrainingCallback):
    """將每隔固定輪數的 XGBoost loss 送到共用 Training log。"""

    def __init__(
        self,
        interval: int,
        total_rounds: int,
        log_fn: Callable[[str], None],
        progress_fn=None,
    ):
        self.interval = max(1, int(interval))
        self.total_rounds = int(total_rounds)
        self.log_fn = log_fn
        self.progress_fn = progress_fn

    def after_iteration(self, model, epoch: int, evals_log) -> bool:
        is_last_round = epoch + 1 == self.total_rounds
        if (epoch + 1) % self.interval != 0 and not is_last_round:
            return False

        train_loss = evals_log.get("validation_0", {}).get("mlogloss", [None])[-1]
        test_loss = evals_log.get("validation_1", {}).get("mlogloss", [None])[-1]
        train_error = evals_log.get("validation_0", {}).get("merror", [None])[-1]
        test_error = evals_log.get("validation_1", {}).get("merror", [None])[-1]
        self.log_fn(
            f"[XGBOOST] round {epoch + 1}: "
            f"train_mlogloss={train_loss:.6f}, test_mlogloss={test_loss:.6f}, "
            f"train_accuracy={1.0 - train_error:.4f}, test_accuracy={1.0 - test_error:.4f}"
        )
        if self.progress_fn:
            self.progress_fn(TrainingProgress(
                epoch=epoch + 1,
                total_epochs=self.total_rounds,
                loss=float(train_loss),
                accuracy=float(1.0 - train_error),
                validation_loss=float(test_loss),
                validation_accuracy=float(1.0 - test_error),
            ))
        return False


def make_feature_names(channels: Iterable[int]) -> List[str]:
    return [f"{feature_type}_ch{channel}" for feature_type in FEATURE_TYPES for channel in channels]


def extract_40_features(window_d: np.ndarray) -> np.ndarray:
    """將一個任意長度的 d 視窗轉為每通道 8 維的統計與時間特徵。"""
    if window_d.ndim != 2 or window_d.shape[0] < 3:
        raise ValueError(f"XGBoost feature window must have at least 3 rows, got {window_d.shape}")
    mean = np.mean(window_d, axis=0)
    std = np.std(window_d, axis=0)
    peak_to_peak = np.ptp(window_d, axis=0)
    mean_abs_diff = np.mean(np.abs(np.diff(window_d, axis=0)), axis=0)
    segment_1, segment_2, segment_3 = np.array_split(window_d, 3, axis=0)
    segment_1_mean = np.mean(segment_1, axis=0)
    segment_2_mean = np.mean(segment_2, axis=0)
    segment_3_mean = np.mean(segment_3, axis=0)
    segment_3_minus_1 = segment_3_mean - segment_1_mean
    return np.concatenate([mean, std, peak_to_peak, mean_abs_diff, segment_1_mean, segment_2_mean, segment_3_mean, segment_3_minus_1]).astype(np.float32)


def get_label_from_filename(csv_path: Path) -> str:
    return csv_path.stem.split("-", 1)[0].lower()


def load_file_windows(csv_path: Path, channels: List[int], window_len: int, window_step: int) -> np.ndarray:
    """讀取單一 CSV，依設定的視窗長度與步長產生特徵。"""
    df = pd.read_csv(csv_path)
    row = df[[f"ROWCH{channel}" for channel in channels]].to_numpy(np.float32)
    base = df[[f"MOVBASE{channel}" for channel in channels]].to_numpy(np.float32)
    d = row - base
    features = [extract_40_features(d[start:start + window_len]) for start in range(0, len(d) - window_len + 1, window_step)]
    return np.asarray(features, dtype=np.float32)


def build_dataset(file_paths: Iterable[Path], channels: List[int], window_len: int, window_step: int, prefix_to_id: Dict[str, int], stop_event=None) -> Tuple[np.ndarray, np.ndarray]:
    x_list, y_list = [], []
    for csv_path in file_paths:
        training_raise_if_cancelled(stop_event)
        label_name = get_label_from_filename(csv_path)
        if label_name not in prefix_to_id:
            continue
        file_features = load_file_windows(csv_path, channels, window_len, window_step)
        if len(file_features):
            x_list.append(file_features)
            y_list.extend([prefix_to_id[label_name]] * len(file_features))
    if not x_list:
        raise ValueError("No usable XGBoost windows were created from the selected CSV files.")
    return np.vstack(x_list), np.asarray(y_list, dtype=np.int32)


def _resolve_output_paths(config: TrainingConfig) -> Tuple[Path, Path]:
    model_path, metadata_path = Path(config.output_model_path), Path(config.output_metadata_path)
    if model_path.suffix.lower() != ".json":
        model_path = model_path.with_suffix(".json")
    if metadata_path.suffix.lower() != ".json":
        metadata_path = metadata_path.with_name(metadata_path.stem + "_labels.json")
    return model_path, metadata_path


def training_run_xgboost(config: TrainingConfig, log_fn: Optional[Callable[[str], None]] = None, progress_fn=None, stop_event=None) -> dict:
    """訓練 XGBoost，並回傳由 training_api 正規化的輸出資料。"""
    log = log_fn or print
    training_raise_if_cancelled(stop_event)
    channels = list(config.ch_list)

    if config.window_len < 3:
        raise ValueError("XGBoost window_len must be at least 3.")
    if config.window_step < 1:
        raise ValueError("XGBoost window_step must be at least 1.")
    if config.xgboost_log_interval < 1:
        raise ValueError("XGBoost log interval must be at least 1.")
    prefix_to_id = config.prefix_to_id
    if not prefix_to_id:
        raise ValueError("XGBoost training requires label_defs.")

    labels = [name for _, name in sorted(config.id_to_name.items())]
    data_dir = Path(config.data_dir)
    csv_files = [path for path in data_dir.glob("*.csv") if get_label_from_filename(path) in prefix_to_id]

    if not csv_files:
        raise ValueError(f"No labelled CSV files found in {data_dir}")

    file_labels = [prefix_to_id[get_label_from_filename(path)] for path in csv_files]
    train_files, test_files = train_test_split(csv_files, test_size=config.test_size, stratify=file_labels, random_state=config.random_state)
    log(f"[XGBOOST] Files: train={len(train_files)}, test={len(test_files)}")
    X_train, y_train = build_dataset(train_files, channels, config.window_len, config.window_step, prefix_to_id, stop_event)
    X_test, y_test = build_dataset(test_files, channels, config.window_len, config.window_step, prefix_to_id, stop_event)
    log(f"[XGBOOST] X_train: {X_train.shape}")
    log(f"[XGBOOST] X_test : {X_test.shape}")
    model = XGBClassifier(
        objective="multi:softprob", num_class=len(labels),
        n_estimators=config.xgboost_n_estimators,
        max_depth=config.xgboost_max_depth,
        learning_rate=config.xgboost_learning_rate,
        subsample=config.xgboost_subsample,
        colsample_bytree=config.xgboost_colsample_bytree,
        min_child_weight=config.xgboost_min_child_weight,
        reg_lambda=config.xgboost_reg_lambda,
        tree_method="hist", eval_metric=["mlogloss", "merror"],
        random_state=config.random_state, n_jobs=-1,
        callbacks=[XGBoostTrainingLogCallback(
            config.xgboost_log_interval,
            config.xgboost_n_estimators,
            log,
            progress_fn,
        )],
    )
    start_time = time.time()
    model.fit(X_train, y_train, eval_set=[(X_train, y_train), (X_test, y_test)], verbose=False)
    training_raise_if_cancelled(stop_event)
    training_time = time.time() - start_time
    y_pred = np.argmax(model.predict_proba(X_test), axis=1)
    accuracy = float(np.mean(y_pred == y_test))
    report = classification_report(y_test, y_pred, labels=list(range(len(labels))), target_names=labels, output_dict=True, zero_division=0)
    model_path, metadata_path = _resolve_output_paths(config)
    model_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    model.save_model(str(model_path))
    metadata_path.write_text(json.dumps({"labels": labels, "channels": channels, "window_len": config.window_len, "stride": config.window_step, "feature_names": make_feature_names(channels)}, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"[XGBOOST] Window accuracy: {accuracy:.2%}")
    log(f"[XGBOOST] Model saved: {model_path}")
    log(f"[XGBOOST] Labels saved: {metadata_path}")
    return {"model_path": str(model_path), "metadata_path": str(metadata_path), "report": report, "validation_accuracy": accuracy, "training_time_seconds": training_time}


if __name__ == "__main__":
    raise SystemExit("Use training_api.training_run_from_config(..., backbone='xgboost').")
