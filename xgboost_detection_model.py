"""XGBoost 40 維手勢模型的即時偵測器。"""

from collections import deque
import json
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
from xgboost import XGBClassifier

from detection_contracts import ModelPrediction


class XGBoostRealtimeGestureDetector:
    """使用 training_xgboost.py 產生的 JSON 模型與 labels metadata。"""

    def __init__(
        self,
        model_path: str,
        metadata_path: str,
        slope_factor: float = 0.0,
        manual_holdavg: Optional[Dict[int, int]] = None,
    ):
        del slope_factor, manual_holdavg  # API 相容參數；本模型只使用 ROW 與 MOVBASE。
        metadata_file = Path(metadata_path)
        with metadata_file.open("r", encoding="utf-8") as file:
            self.meta = json.load(file)

        self.channels: List[int] = [int(channel) for channel in self.meta["channels"]]
        self.window_len = int(self.meta["window_len"])
        self.feature_cols: List[str] = list(self.meta["feature_names"])
        labels = self.meta["labels"]
        self.id_to_name = {index: str(label) for index, label in enumerate(labels)}
        self.model_type = "xgboost"

        if len(self.feature_cols) != len(self.channels) * 8:
            raise ValueError("XGBoost metadata feature count does not match 8 features per channel")

        self.clf = XGBClassifier()
        self.clf.load_model(model_path)
        self.window_row = {channel: deque(maxlen=self.window_len) for channel in self.channels}
        self.window_base = {channel: deque(maxlen=self.window_len) for channel in self.channels}

    def clear_buffers(self) -> None:
        for channel in self.channels:
            self.window_row[channel].clear()
            self.window_base[channel].clear()

    def push_data(
        self,
        row_vals: Dict[int, int],
        base_vals: Dict[int, int],
        hold_vals: Dict[int, int],
        gain_map: Dict[int, float],
    ) -> None:
        """保存訓練一致的原始 d = ROW - MOVBASE；不使用 dn、hold 或 gain。"""
        del hold_vals, gain_map
        if any(channel not in row_vals or channel not in base_vals for channel in self.channels):
            return
        for channel in self.channels:
            self.window_row[channel].append(float(row_vals[channel]))
            self.window_base[channel].append(float(base_vals[channel]))

    def is_buffer_full(self) -> bool:
        return all(len(self.window_row[channel]) == self.window_len for channel in self.channels)

    def predict(self, gain_map: Dict[int, float]) -> Optional[ModelPrediction]:
        del gain_map
        if not self.is_buffer_full():
            return None

        signal_d = np.stack(
            [
                np.asarray(self.window_row[channel], dtype=np.float32)
                - np.asarray(self.window_base[channel], dtype=np.float32)
                for channel in self.channels
            ],
            axis=1,
        )
        features = self.extract_40_features(signal_d)
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
