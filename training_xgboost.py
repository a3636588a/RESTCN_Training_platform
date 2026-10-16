"""XGBoost 統計與時間特徵手勢訓練器。"""

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
from xgboost_motion_features import MOTION_TYPES, motion_features
from xgboost_motion_features import onset_names, onset_features
from xgboost_motion_features import relative_onset_features, sync_features, SYNC_NAMES
from training_contracts import TrainingProgress, training_raise_if_cancelled

STAT_FEATURE_TYPES = ("mean", "std", "peak_to_peak", "mean_abs_diff", "segment_1_mean", "segment_2_mean", "segment_3_mean", "segment_3_minus_1")
TIME_SEGMENT_COUNT = 10
WAVE_SAMPLE_COUNT = 25
WAVE_LANDMARK_TYPES = ("max_position", "min_position", "max_rise_position", "max_fall_position")
WAVE_DYNAMIC_TYPES = ("total_variation", "positive_slope_ratio", "negative_slope_ratio", "fft_low_energy", "fft_mid_energy", "fft_high_energy")
HYBRID_WAVE_SAMPLE_COUNT = 20
HYBRID_SHARE_SAMPLE_COUNT = 10
HYBRID_GLOBAL_TYPES = ("activity_total", "activity_peak_position", "activity_total_variation", "dominant_channel_switches", "mean_channel_entropy")
XGBOOST_FEATURE_SETS = {
    "fatigue12": 12,
    "motion75": 15,
    "onset95": None,
    "onset60": None,
    "onset60_v2": None,
    "sync47": None,
    "stats40": len(STAT_FEATURE_TYPES),
    "time140": len(STAT_FEATURE_TYPES) + TIME_SEGMENT_COUNT * 2,
    "wave215": len(STAT_FEATURE_TYPES) + WAVE_SAMPLE_COUNT + len(WAVE_LANDMARK_TYPES) + len(WAVE_DYNAMIC_TYPES),
    # Hybrid225 同時保留靜態統計、每通道波形，以及全通道的相對活動狀態。
    "hybrid225": None,
}
XGBOOST_SIGNAL_MODES = {"d", "dn"}
XGBOOST_NEGATIVE_DELTA_MODES = {"allow", "clip_zero"}


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


def make_feature_names(channels: Iterable[int], feature_set: str) -> List[str]:
    channels = list(channels)
    if feature_set == "fatigue12":
        if channels != [1]:
            raise ValueError("fatigue12 requires channels=[1]")
        from fatigue_xgboost import FEATURE_NAMES
        return list(FEATURE_NAMES)
    names = [f"{feature_type}_ch{channel}" for feature_type in STAT_FEATURE_TYPES for channel in channels]
    if feature_set == "sync47":
        names.extend(SYNC_NAMES)
    if feature_set in {"motion75", "onset95"}:
        names.extend(f"{kind}_ch{channel}" for kind in MOTION_TYPES for channel in channels)
    if feature_set == "onset95":
        names.extend(onset_names(channels))
    if feature_set in {"onset60", "onset60_v2"}:
        names.extend('relative_' + name for name in onset_names(channels))
    if feature_set == "time140":
        names.extend(
            f"time_segment_{index:02d}_mean_ch{channel}"
            for index in range(1, TIME_SEGMENT_COUNT + 1)
            for channel in channels
        )
        names.extend(
            f"time_segment_{index:02d}_slope_ch{channel}"
            for index in range(1, TIME_SEGMENT_COUNT + 1)
            for channel in channels
        )
    if feature_set == "wave215":
        names.extend(
            f"wave_sample_{index:02d}_ch{channel}"
            for index in range(1, WAVE_SAMPLE_COUNT + 1)
            for channel in channels
        )
        names.extend(
            f"{feature_type}_ch{channel}"
            for feature_type in WAVE_LANDMARK_TYPES
            for channel in channels
        )
        names.extend(
            f"{feature_type}_ch{channel}"
            for feature_type in WAVE_DYNAMIC_TYPES
            for channel in channels
        )
    if feature_set == "hybrid225":
        names.extend(
            f"hybrid_wave_sample_{index:02d}_ch{channel}"
            for index in range(1, HYBRID_WAVE_SAMPLE_COUNT + 1)
            for channel in channels
        )
        names.extend(f"global_activity_sample_{index:02d}" for index in range(1, HYBRID_WAVE_SAMPLE_COUNT + 1))
        names.extend(
            f"channel_share_sample_{index:02d}_ch{channel}"
            for index in range(1, HYBRID_SHARE_SAMPLE_COUNT + 1)
            for channel in channels
        )
        names.extend(f"channel_total_share_ch{channel}" for channel in channels)
        names.extend(f"channel_peak_position_ch{channel}" for channel in channels)
        names.extend(HYBRID_GLOBAL_TYPES)
    return names


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


def extract_features(window_d: np.ndarray, feature_set: str) -> np.ndarray:
    """依 feature_set 建立統計特徵、分段摘要或保留波形形狀的特徵。"""
    if feature_set not in XGBOOST_FEATURE_SETS:
        raise ValueError(f"Unsupported XGBoost feature set: {feature_set}")
    if feature_set == "fatigue12":
        raise ValueError("fatigue12 uses fatigue_xgboost.extract_features(raw_ch1, FatigueConfig)")
    if feature_set == "sync47":
        extra = sync_features(window_d)
        return np.concatenate([extract_40_features(window_d[-(len(window_d)//3):]), extra])
    static_features = extract_40_features(window_d)
    if feature_set in {"onset60", "onset60_v2"}:
        return np.concatenate([static_features, relative_onset_features(window_d, stable_range=.08 if feature_set == "onset60_v2" else .03)])
    if feature_set == "onset95":
        return np.concatenate([static_features, motion_features(window_d), onset_features(window_d)])
    if feature_set == "motion75":
        return np.concatenate([static_features, motion_features(window_d)])
    if feature_set == "stats40":
        return static_features
    if feature_set == "time140":
        if window_d.shape[0] < TIME_SEGMENT_COUNT:
            raise ValueError(f"time140 requires at least {TIME_SEGMENT_COUNT} rows, got {window_d.shape[0]}")
        segments = np.array_split(window_d, TIME_SEGMENT_COUNT, axis=0)
        segment_means = [np.mean(segment, axis=0) for segment in segments]
        segment_slopes = [np.mean(np.diff(segment, axis=0), axis=0) for segment in segments]
        return np.concatenate([static_features, *segment_means, *segment_slopes]).astype(np.float32)

    if feature_set == "hybrid225":
        old_x = np.linspace(0.0, 1.0, num=window_d.shape[0], dtype=np.float32)
        wave_x = np.linspace(0.0, 1.0, num=HYBRID_WAVE_SAMPLE_COUNT, dtype=np.float32)
        share_x = np.linspace(0.0, 1.0, num=HYBRID_SHARE_SAMPLE_COUNT, dtype=np.float32)
        waveform = np.column_stack([
            np.interp(wave_x, old_x, window_d[:, channel])
            for channel in range(window_d.shape[1])
        ])
        positive_signal = np.maximum(window_d, 0.0)
        activity = np.sum(positive_signal, axis=1)
        activity_curve = np.interp(wave_x, old_x, activity)
        sampled_positive = np.column_stack([
            np.interp(share_x, old_x, positive_signal[:, channel])
            for channel in range(window_d.shape[1])
        ])
        sampled_share = sampled_positive / np.maximum(np.sum(sampled_positive, axis=1, keepdims=True), 1e-6)
        total_per_channel = np.sum(positive_signal, axis=0)
        total_share = total_per_channel / max(float(np.sum(total_per_channel)), 1e-6)
        channel_peak_position = np.argmax(positive_signal, axis=0) / max(window_d.shape[0] - 1, 1)
        active_rows = activity > 1e-6
        dominant_channels = np.argmax(positive_signal[active_rows], axis=1) if np.any(active_rows) else np.empty(0, dtype=int)
        dominant_switches = float(np.sum(np.diff(dominant_channels) != 0)) if len(dominant_channels) > 1 else 0.0
        instantaneous_share = positive_signal / np.maximum(activity[:, None], 1e-6)
        entropy = -np.sum(instantaneous_share * np.log(np.maximum(instantaneous_share, 1e-6)), axis=1)
        global_features = np.array([
            np.sum(activity),
            np.argmax(activity) / max(window_d.shape[0] - 1, 1),
            np.sum(np.abs(np.diff(activity))),
            dominant_switches,
            np.mean(entropy[active_rows]) if np.any(active_rows) else 0.0,
        ], dtype=np.float32)
        return np.concatenate([
            static_features, waveform.reshape(-1), activity_curve, sampled_share.reshape(-1),
            total_share, channel_peak_position, global_features,
        ]).astype(np.float32)

    # wave215: 以等距內插保留整段形狀，再加入關鍵位置與整體動態特徵。
    old_x = np.linspace(0.0, 1.0, num=window_d.shape[0], dtype=np.float32)
    sample_x = np.linspace(0.0, 1.0, num=WAVE_SAMPLE_COUNT, dtype=np.float32)
    waveform = np.column_stack([
        np.interp(sample_x, old_x, window_d[:, channel])
        for channel in range(window_d.shape[1])
    ]).astype(np.float32)
    diffs = np.diff(window_d, axis=0)
    max_position = np.argmax(window_d, axis=0) / max(window_d.shape[0] - 1, 1)
    min_position = np.argmin(window_d, axis=0) / max(window_d.shape[0] - 1, 1)
    max_rise_position = np.argmax(diffs, axis=0) / max(diffs.shape[0] - 1, 1)
    max_fall_position = np.argmin(diffs, axis=0) / max(diffs.shape[0] - 1, 1)
    total_variation = np.sum(np.abs(diffs), axis=0)
    variation_floor = np.maximum(total_variation, 1e-6)
    positive_slope_ratio = np.sum(np.maximum(diffs, 0.0), axis=0) / variation_floor
    negative_slope_ratio = np.sum(np.maximum(-diffs, 0.0), axis=0) / variation_floor
    spectrum = np.abs(np.fft.rfft(window_d - np.mean(window_d, axis=0), axis=0)) ** 2
    frequency_bands = np.array_split(spectrum[1:], 3, axis=0)
    band_energy = np.asarray([np.sum(band, axis=0) for band in frequency_bands])
    band_energy /= np.maximum(np.sum(band_energy, axis=0, keepdims=True), 1e-6)
    return np.concatenate([
        static_features,
        waveform.reshape(-1),
        max_position, min_position, max_rise_position, max_fall_position,
        total_variation, positive_slope_ratio, negative_slope_ratio,
        *band_energy,
    ]).astype(np.float32)


def get_label_from_filename(csv_path: Path) -> str:
    return csv_path.stem.split("-", 1)[0].lower()


def build_signal(
    row: np.ndarray,
    base: np.ndarray,
    hold: np.ndarray,
    signal_mode: str,
    delta_gain=1.0,
    span_gain=1.0,
    delta_offset=0.0,
    negative_delta_mode: str = "allow",
) -> np.ndarray:
    """建立 d 或 dn，並在訓練時套用與 CNN 一致的校正資料擴增。"""
    d = (row - base) * delta_gain + delta_offset
    if negative_delta_mode == "clip_zero":
        d = np.maximum(d, 0.0)
    elif negative_delta_mode != "allow":
        raise ValueError(f"Unsupported XGBoost negative delta mode: {negative_delta_mode}")
    if signal_mode == "d":
        return d
    if signal_mode == "dn":
        span = np.maximum(np.abs(hold - base) * span_gain, 1.0)
        return d / span
    raise ValueError(f"Unsupported XGBoost signal mode: {signal_mode}")


def _resample_columns(values: np.ndarray, new_len: int) -> np.ndarray:
    if values.shape[0] == new_len:
        return values.copy()
    old_x = np.linspace(0.0, 1.0, num=values.shape[0], dtype=np.float32)
    new_x = np.linspace(0.0, 1.0, num=new_len, dtype=np.float32)
    return np.column_stack([
        np.interp(new_x, old_x, values[:, channel])
        for channel in range(values.shape[1])
    ]).astype(np.float32)


def load_file_windows(
    csv_path: Path,
    channels: List[int],
    window_len: int,
    window_step: int,
    signal_mode: str,
    feature_set: str,
    negative_delta_mode: str,
    delta_gain=1.0,
    span_gain=1.0,
    delta_offset=0.0,
    time_warp_factor: float = 1.0,
) -> np.ndarray:
    """讀取單一 CSV，依設定的視窗長度與步長產生特徵。"""
    if feature_set == "sync47" and (list(channels) != [1,2,3,4,5] or signal_mode != "dn"):
        raise ValueError("sync47 requires channels=[1,2,3,4,5] and signal_mode=dn")
    history_len = window_len * 3 if feature_set == "sync47" else window_len
    df = pd.read_csv(csv_path)
    row = df[[f"ROWCH{channel}" for channel in channels]].to_numpy(np.float32)
    base = df[[f"MOVBASE{channel}" for channel in channels]].to_numpy(np.float32)
    hold = df[[f"HOLDAVG{channel}" for channel in channels]].to_numpy(np.float32)
    if abs(time_warp_factor - 1.0) > 1e-3:
        new_len = max(window_len + 5, int(len(row) * time_warp_factor))
        row = _resample_columns(row, new_len)
        base = _resample_columns(base, new_len)
        hold = _resample_columns(hold, new_len)
    signal = build_signal(
        row, base, hold, signal_mode, delta_gain, span_gain, delta_offset,
        negative_delta_mode,
    )
    features = [extract_features(signal[start:start + history_len], feature_set) for start in range(0, len(signal) - history_len + 1, window_step)]
    return np.asarray(features, dtype=np.float32)


def build_dataset(
    file_paths: Iterable[Path],
    channels: List[int],
    window_len: int,
    window_step: int,
    signal_mode: str,
    feature_set: str,
    negative_delta_mode: str,
    prefix_to_id: Dict[str, int],
    stop_event=None,
    delta_gain=1.0,
    span_gain=1.0,
    delta_offset=0.0,
    time_warp_factor: float = 1.0,
) -> Tuple[np.ndarray, np.ndarray]:
    x_list, y_list = [], []
    for csv_path in file_paths:
        training_raise_if_cancelled(stop_event)
        label_name = get_label_from_filename(csv_path)
        if label_name not in prefix_to_id:
            continue
        file_features = load_file_windows(
            csv_path, channels, window_len, window_step, signal_mode, feature_set, negative_delta_mode,
            delta_gain, span_gain, delta_offset, time_warp_factor,
        )
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


def _build_augmented_training_dataset(
    train_files: Iterable[Path],
    channels: List[int],
    config: TrainingConfig,
    signal_mode: str,
    feature_set: str,
    negative_delta_mode: str,
    prefix_to_id: Dict[str, int],
    stop_event=None,
) -> Tuple[np.ndarray, np.ndarray]:
    """只對訓練檔建立 aug_copies 份隨機校正與時間變形的視窗。"""
    if not config.enable_augmentation:
        return build_dataset(
            train_files, channels, config.window_len, config.window_step,
            signal_mode, feature_set, negative_delta_mode, prefix_to_id, stop_event,
        )

    rng = np.random.default_rng(config.random_state)
    x_copies, y_copies = [], []
    for _ in range(max(1, config.aug_copies)):
        delta_gain = rng.uniform(config.aug_delta_gain_min, config.aug_delta_gain_max, len(channels))
        span_gain = rng.uniform(config.aug_span_gain_min, config.aug_span_gain_max, len(channels))
        delta_offset = np.zeros(len(channels), dtype=np.float32)
        if config.enable_offset_aug:
            delta_offset = np.clip(
                rng.normal(0.0, config.aug_offset_sigma, len(channels)),
                -config.aug_offset_clip,
                config.aug_offset_clip,
            )
        time_warp_factor = (
            float(rng.uniform(config.time_warp_min, config.time_warp_max))
            if config.enable_time_warp else 1.0
        )
        X_copy, y_copy = build_dataset(
            train_files, channels, config.window_len, config.window_step,
            signal_mode, feature_set, negative_delta_mode, prefix_to_id, stop_event,
            delta_gain, span_gain, delta_offset, time_warp_factor,
        )
        x_copies.append(X_copy)
        y_copies.append(y_copy)
    return np.vstack(x_copies), np.concatenate(y_copies)


def training_run_xgboost(config: TrainingConfig, log_fn: Optional[Callable[[str], None]] = None, progress_fn=None, stop_event=None) -> dict:
    """訓練 XGBoost，並回傳由 training_api 正規化的輸出資料。"""
    if config.xgboost_feature_set.strip().lower() == "fatigue12":
        from training_fatigue import training_run_fatigue
        return training_run_fatigue(config, log_fn, progress_fn, stop_event)
    log = log_fn or print
    training_raise_if_cancelled(stop_event)
    channels = list(config.ch_list)

    if config.window_len < 3:
        raise ValueError("XGBoost window_len must be at least 3.")
    if config.window_step < 1:
        raise ValueError("XGBoost window_step must be at least 1.")
    if config.xgboost_log_interval < 1:
        raise ValueError("XGBoost log interval must be at least 1.")
    signal_mode = config.xgboost_signal_mode.strip().lower()
    if signal_mode not in XGBOOST_SIGNAL_MODES:
        raise ValueError(f"XGBoost signal mode must be one of {sorted(XGBOOST_SIGNAL_MODES)}.")
    negative_delta_mode = config.xgboost_negative_delta_mode.strip().lower()
    if negative_delta_mode not in XGBOOST_NEGATIVE_DELTA_MODES:
        raise ValueError(
            f"XGBoost negative delta mode must be one of {sorted(XGBOOST_NEGATIVE_DELTA_MODES)}."
        )
    feature_set = config.xgboost_feature_set.strip().lower()
    if feature_set == "sync47":
        if channels != [1,2,3,4,5] or signal_mode != "dn":
            raise ValueError("sync47 requires channels=[1,2,3,4,5] and signal_mode=dn")
        log(f"[XGBOOST] sync47: short={config.window_len}, history={3*config.window_len}, stride={config.window_step}; short CSVs/shortened augmented copies cannot form a history window.")
    if feature_set in {"motion75", "onset95"} and config.window_len < 12:
        raise ValueError(f"{feature_set} requires window_len >= 12")
    if feature_set in {"onset60", "onset60_v2"} and config.window_len < 8:
        raise ValueError("onset60 requires window_len >= 8")
    if feature_set in {"onset95", "onset60", "onset60_v2"} and signal_mode != "dn":
        raise ValueError(f"{feature_set} requires signal_mode=dn for its activation thresholds")
    if feature_set not in XGBOOST_FEATURE_SETS:
        raise ValueError(f"XGBoost feature set must be one of {sorted(XGBOOST_FEATURE_SETS)}.")
    if feature_set == "time140" and config.window_len < TIME_SEGMENT_COUNT:
        raise ValueError(f"XGBoost time140 requires window_len >= {TIME_SEGMENT_COUNT}.")
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
    X_train, y_train = _build_augmented_training_dataset(
        train_files, channels, config, signal_mode, feature_set, negative_delta_mode, prefix_to_id, stop_event,
    )
    X_test, y_test = build_dataset(
        test_files, channels, config.window_len, config.window_step, signal_mode,
        feature_set, negative_delta_mode, prefix_to_id, stop_event,
    )
    log(f"[XGBOOST] X_train: {X_train.shape}")
    log(f"[XGBOOST] X_test : {X_test.shape}")
    log(f"[XGBOOST] Augmentation: enabled={config.enable_augmentation}, copies={config.aug_copies if config.enable_augmentation else 1}")
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
    feature_names = make_feature_names(channels, feature_set)
    metadata_path.write_text(json.dumps({"labels": labels, "channels": channels, "window_len": config.window_len, "history_len": config.window_len * 3 if feature_set == "sync47" else config.window_len, "stride": config.window_step, "signal_mode": signal_mode, "negative_delta_mode": negative_delta_mode, "feature_set": feature_set, "features_per_channel": XGBOOST_FEATURE_SETS[feature_set], "feature_count": len(feature_names), "feature_names": feature_names}, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"[XGBOOST] Signal mode: {signal_mode}")
    log(f"[XGBOOST] Negative delta mode: {negative_delta_mode}")
    log(f"[XGBOOST] Feature set: {feature_set} ({len(feature_names)} features)")
    importances = model.feature_importances_
    top_indices = np.argsort(importances)[::-1][:min(15, len(importances))]
    log("[XGBOOST] Top feature importances:")
    for rank, feature_index in enumerate(top_indices, start=1):
        log(f"[XGBOOST]   {rank:02d}. {feature_names[feature_index]} = {importances[feature_index]:.5f}")
    log(f"[XGBOOST] Window accuracy: {accuracy:.2%}")
    log(f"[XGBOOST] Model saved: {model_path}")
    log(f"[XGBOOST] Labels saved: {metadata_path}")
    return {"model_path": str(model_path), "metadata_path": str(metadata_path), "report": report, "validation_accuracy": accuracy, "training_time_seconds": training_time}


if __name__ == "__main__":
    raise SystemExit("Use training_api.training_run_from_config(..., backbone='xgboost').")
