"""XGBoost 統計與時間特徵手勢模型的即時偵測器。"""

from collections import deque
import json
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
from xgboost import XGBClassifier

from detection_contracts import ModelPrediction
from xgboost_motion_features import motion_features, sync_features
from xgboost_motion_features import onset_features, relative_onset_features


TIME_SEGMENT_COUNT = 10
WAVE_SAMPLE_COUNT = 25
WAVE_LANDMARK_COUNT = 4
WAVE_DYNAMIC_COUNT = 6
HYBRID_WAVE_SAMPLE_COUNT = 20
HYBRID_SHARE_SAMPLE_COUNT = 10
FEATURES_PER_CHANNEL = {"stats40": 8, "time140": 28, "wave215": 8 + WAVE_SAMPLE_COUNT + WAVE_LANDMARK_COUNT + WAVE_DYNAMIC_COUNT}
SUPPORTED_FEATURE_SETS = {*FEATURES_PER_CHANNEL, "hybrid225"}
FEATURES_PER_CHANNEL["motion75"] = 15
SUPPORTED_FEATURE_SETS.add("motion75")
SUPPORTED_FEATURE_SETS.add("onset95")
SUPPORTED_FEATURE_SETS.add("onset60")
SUPPORTED_FEATURE_SETS.add("onset60_v2")
SUPPORTED_FEATURE_SETS.add("sync47")


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
        # 舊模型未記錄此欄位，保留過去可使用負差值的推論結果。
        self.negative_delta_mode = str(self.meta.get("negative_delta_mode", "allow")).lower()
        self.feature_set = str(self.meta.get("feature_set", "stats40")).lower()
        if self.feature_set in {"motion75", "onset95"} and self.window_len < 12:
            raise ValueError(f"{self.feature_set} requires window_len >= 12")
        if self.feature_set in {"onset60", "onset60_v2"} and self.window_len < 8:
            raise ValueError("onset60 requires window_len >= 8")
        if self.feature_set in {"onset95", "onset60", "onset60_v2"} and self.signal_mode != "dn":
            raise ValueError(f"{self.feature_set} requires signal_mode=dn")
        self.history_len = self.window_len
        if self.feature_set == "sync47":
            if self.channels != [1,2,3,4,5] or self.signal_mode != "dn" or self.window_len < 3:
                raise ValueError("sync47 requires CH1..5, dn, window_len >=3")
            self.history_len = 3*self.window_len
            if int(self.meta.get("history_len", 0)) != self.history_len:
                raise ValueError("sync47 metadata history_len must equal 3 * window_len")
        self.feature_cols: List[str] = list(self.meta["feature_names"])
        labels = self.meta["labels"]
        self.id_to_name = {index: str(label) for index, label in enumerate(labels)}
        self.model_type = "xgboost"

        if self.feature_set not in SUPPORTED_FEATURE_SETS:
            raise ValueError(f"Unsupported XGBoost feature set: {self.feature_set}")
        expected_feature_count = int(self.meta.get(
            "feature_count",
            len(self.channels) * FEATURES_PER_CHANNEL.get(self.feature_set, 0),
        ))
        if len(self.feature_cols) != expected_feature_count:
            raise ValueError("XGBoost metadata feature count does not match the configured feature set")
        if self.signal_mode not in {"d", "dn"}:
            raise ValueError(f"Unsupported XGBoost signal mode: {self.signal_mode}")
        if self.negative_delta_mode not in {"allow", "clip_zero"}:
            raise ValueError(f"Unsupported XGBoost negative delta mode: {self.negative_delta_mode}")

        self.clf = XGBClassifier()
        self.clf.load_model(model_path)
        self.window_row = {channel: deque(maxlen=self.history_len) for channel in self.channels}
        self.window_base = {channel: deque(maxlen=self.history_len) for channel in self.channels}
        self.window_hold = {channel: deque(maxlen=self.history_len) for channel in self.channels}

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
        return all(len(self.window_row[channel]) == self.history_len for channel in self.channels)

    def predict(self, gain_map: Dict[int, float]) -> Optional[ModelPrediction]:
        del gain_map
        if not self.is_buffer_full():
            return None

        row = np.stack([np.asarray(self.window_row[channel], dtype=np.float32) for channel in self.channels], axis=1)
        base = np.stack([np.asarray(self.window_base[channel], dtype=np.float32) for channel in self.channels], axis=1)
        hold = np.stack([np.asarray(self.window_hold[channel], dtype=np.float32) for channel in self.channels], axis=1)
        signal = row - base
        if self.negative_delta_mode == "clip_zero":
            signal = np.maximum(signal, 0.0)
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
        if feature_set == "sync47":
            extra = sync_features(window_d)
            return np.concatenate([cls.extract_40_features(window_d[-(len(window_d)//3):]), extra])
        static_features = cls.extract_40_features(window_d)
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
        if feature_set != "wave215":
            raise ValueError(f"Unsupported XGBoost feature set: {feature_set}")
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
