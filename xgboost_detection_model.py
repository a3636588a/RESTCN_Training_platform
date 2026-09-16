"""XGBoost 統計與時間特徵手勢模型的即時偵測器。"""

from collections import deque
import json
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
from xgboost import XGBClassifier

from detection_contracts import ModelPrediction


TIME_SEGMENT_COUNT = 10
FEATURES_PER_CHANNEL = {"stats40": 8, "time140": 28}


class XGBoostRealtimeGestureDetector:
    """使用 training_xgboost.py 產生的 JSON 模型與 labels metadata。"""

    def __init__(
        self,
        model_path: str,
        metadata_path: str,
        slope_factor: float = 0.0,
        manual_holdavg: Optional[Dict[int, int]] = None,
    ):
        del slope_factor  # API 相容參數；XGBoost 不使用 CNN slope。
        self.manual_holdavg = {int(key): float(value) for key, value in (manual_holdavg or {}).items()}
        metadata_file = Path(metadata_path)
        with metadata_file.open("r", encoding="utf-8") as file:
            self.meta = json.load(file)

        self.channels: List[int] = [int(channel) for channel in self.meta["channels"]]
        self.window_len = int(self.meta["window_len"])
        self.signal_mode = str(self.meta.get("signal_mode", "d")).lower()
        self.feature_set = str(self.meta.get("feature_set", "stats40")).lower()
        self.feature_cols: List[str] = list(self.meta["feature_names"])
        labels = self.meta["labels"]
        self.id_to_name = {index: str(label) for index, label in enumerate(labels)}
        self.model_type = "xgboost"

        if self.feature_set not in FEATURES_PER_CHANNEL:
            raise ValueError(f"Unsupported XGBoost feature set: {self.feature_set}")
        if len(self.feature_cols) != len(self.channels) * FEATURES_PER_CHANNEL[self.feature_set]:
            raise ValueError("XGBoost metadata feature count does not match the configured feature set")
        if self.signal_mode not in {"d", "dn"}:
            raise ValueError(f"Unsupported XGBoost signal mode: {self.signal_mode}")

        self.clf = XGBClassifier()
        self.clf.load_model(model_path)
        self.window_row = {channel: deque(maxlen=self.window_len) for channel in self.channels}
        self.window_base = {channel: deque(maxlen=self.window_len) for channel in self.channels}
        self.window_hold = {channel: deque(maxlen=self.window_len) for channel in self.channels}

    def clear_buffers(self) -> None:
        for channel in self.channels:
            self.window_row[channel].clear()
            self.window_base[channel].clear()
            self.window_hold[channel].clear()

    def push_data(
        self,
        row_vals: Dict[int, int],
        base_vals: Dict[int, int],
        hold_vals: Dict[int, int],
        gain_map: Dict[int, float],
    ) -> None:
        """保存訓練一致的 ROW、MOVBASE、HOLDAVG；不使用 CNN gain。"""
        del gain_map
        if any(channel not in row_vals or channel not in base_vals for channel in self.channels):
            return
        if self.signal_mode == "dn" and any(
            channel not in hold_vals and channel not in self.manual_holdavg
            for channel in self.channels
        ):
            return
        for channel in self.channels:
            self.window_row[channel].append(float(row_vals[channel]))
            self.window_base[channel].append(float(base_vals[channel]))
            self.window_hold[channel].append(float(hold_vals.get(channel, self.manual_holdavg.get(channel, 0.0))))

    def is_buffer_full(self) -> bool:
        return all(len(self.window_row[channel]) == self.window_len for channel in self.channels)

    def predict(self, gain_map: Dict[int, float]) -> Optional[ModelPrediction]:
        del gain_map
        if not self.is_buffer_full():
            return None

        row = np.stack([np.asarray(self.window_row[channel], dtype=np.float32) for channel in self.channels], axis=1)
        base = np.stack([np.asarray(self.window_base[channel], dtype=np.float32) for channel in self.channels], axis=1)
        hold = np.stack([np.asarray(self.window_hold[channel], dtype=np.float32) for channel in self.channels], axis=1)
        signal = row - base
        if self.signal_mode == "dn":
            signal = signal / np.maximum(np.abs(hold - base), 1.0)
        features = self.extract_features(signal, self.feature_set)
        probabilities = self.clf.predict_proba(features.reshape(1, -1))[0]
        pred_id = int(np.argmax(probabilities))
        return ModelPrediction(
            pred_id=pred_id,
            confidence=float(probabilities[pred_id]),
            probabilities=tuple(float(value) for value in probabilities),
        )

    @staticmethod
    def extract_40_features(window_d: np.ndarray) -> np.ndarray:
        """重現 training_xgboost.extract_40_features。"""
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

        return np.concatenate(
            [mean, std, peak_to_peak, mean_abs_diff, segment_1_mean,
             segment_2_mean, segment_3_mean, segment_3_minus_1]
        ).astype(np.float32)

    @classmethod
    def extract_features(cls, window_d: np.ndarray, feature_set: str) -> np.ndarray:
        static_features = cls.extract_40_features(window_d)
        if feature_set == "stats40":
            return static_features
        if feature_set != "time140":
            raise ValueError(f"Unsupported XGBoost feature set: {feature_set}")
        if window_d.shape[0] < TIME_SEGMENT_COUNT:
            raise ValueError(f"time140 requires at least {TIME_SEGMENT_COUNT} rows, got {window_d.shape[0]}")
        segments = np.array_split(window_d, TIME_SEGMENT_COUNT, axis=0)
        segment_means = [np.mean(segment, axis=0) for segment in segments]
        segment_slopes = [np.mean(np.diff(segment, axis=0), axis=0) for segment in segments]
        return np.concatenate([static_features, *segment_means, *segment_slopes]).astype(np.float32)
