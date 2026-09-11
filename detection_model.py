#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
detection_model.py

✅ 配合你提供的 v6 訓練版（Dual-SE 2-Layer CNN）的偵測端

核心改動：
1) ✅ 支援最新的 SE 注意力機制模型 (Squeeze-and-Excitation)
2) ✅ 優化推論效率，僅需 2 層捲積即可達到高精度
3) ✅ 用 meta["feature_cols"] 做「排列對齊」：避免 silent wrong inference
4) ✅ dn 計算方式改成「與訓練一致的 bend fraction」
   - dn = d_mapped / span_mapped
   - 其中 span_mapped = abs(HOLDAVG - MOVBASE) * GAIN_MAP

本模組只負責 Model resource、Sensor Window、Feature 與 predict()；
UART、Config、Gain Runtime State 與後處理由 detection_api.py 擁有。
"""

from collections import deque
from typing import Dict, List, Optional, Any

import joblib
import numpy as np

from detection_contracts import ModelPrediction


# ==========================================
# Main Detector Class
# ==========================================
class RealtimeGestureDetector:
    def __init__(
        self,
        model_path: str,
        metadata_path: str,
        slope_factor: float,
        manual_holdavg: Optional[Dict[int, int]] = None,
    ):
        """建立單次推論使用的 Detector，不依賴 API 寫入 module globals。

        呼叫端必須明確傳入 model、metadata 與固定推論設定，讓不同
        Detect run 彼此隔離；本 Model module 不保存使用者 Config。
        """
        self.clf = None
        self.meta: Dict[str, Any] = {}
        self.model_path = model_path
        self.metadata_path = metadata_path
        self.default_slope_factor = float(slope_factor)
        holdavg_source = {} if manual_holdavg is None else manual_holdavg
        self.manual_holdavg = {
            int(key): int(value) for key, value in holdavg_source.items()
        }
        # window buffers：存「等效 A」的 row / base（row 會做 gain mapping）
        self.window_row: Dict[int, deque] = {}
        self.window_base: Dict[int, deque] = {}
        self.window_hold: Dict[int, deque] = {}  # ✅ v5：dn 需要 span，所以 hold 也要緩存（對齊 window）
        self.sample_before_window: Optional[np.ndarray] = None

        self.channels: List[int] = [1, 2, 3, 4, 5]
        self.window_len = 30

        self.flags: Dict[str, Any] = {}
        self.id_to_name: Dict[int, str] = {}

        self.feature_cols: List[str] = []

        self.load_model_resources()
        self._init_buffers()

    def load_model_resources(self):
        print(f"Loading meta from {self.metadata_path} ...")
        self.meta = joblib.load(self.metadata_path)
        self.model_type = self.meta.get("model_type", "mlp")

        print(f"Loading model ({self.model_type}) from {self.model_path} ...")
        actual_model_path = self.model_path
        if self.model_type == "cnn":
            import tensorflow as tf
            import os
            
            # Auto-heal extension if user passed .pkl for a CNN model
            if actual_model_path.lower().endswith(".pkl"):
                # Try same folder first
                healed_keras = actual_model_path[:-4] + ".keras"
                healed_h5 = actual_model_path[:-4] + ".h5"
                
                if os.path.exists(healed_keras):
                    print(f"[FIX] CNN model found with .keras extension, using: {healed_keras}")
                    actual_model_path = healed_keras
                elif os.path.exists(healed_h5):
                    print(f"[FIX] CNN model found with .h5 extension, using: {healed_h5}")
                    actual_model_path = healed_h5
                else:
                    # Try parent folder (useful if selected file is in a subfolder like 'mlp')
                    from pathlib import Path
                    p = Path(actual_model_path)
                    parent_keras = p.parent.parent / p.name.replace(".pkl", ".keras")
                    parent_h5 = p.parent.parent / p.name.replace(".pkl", ".h5")
                    
                    if parent_keras.exists():
                        print(f"[FIX] CNN model found in PARENT folder, using: {parent_keras}")
                        actual_model_path = str(parent_keras)
                    elif parent_h5.exists():
                        print(f"[FIX] CNN model found in PARENT folder, using: {parent_h5}")
                        actual_model_path = str(parent_h5)
            
            if not actual_model_path.lower().endswith((".keras", ".h5")):
                 print(f"[WARN] CNN model type detected but path is {actual_model_path}. Keras 3 may fail to load .pkl files.")

            self.clf = tf.keras.models.load_model(actual_model_path)
        else:
            self.clf = joblib.load(actual_model_path)

        self.channels = self.meta.get("channels", [1, 2, 3, 4, 5])
        self.window_len = int(self.meta.get("windowing", {}).get("window_len", 30))
        self.flags = self.meta.get("flags", {})
        self.id_to_name = self.meta.get("id_to_name", {})
        
        self.feature_cols = self.meta.get("feature_cols", [])
        if not self.feature_cols:
            raise ValueError("meta.feature_cols missing/empty (v5 detect requires this)")

        # ✅ 重新啟用 Scaler (與訓練端 MaxAbsScaler 同步)
        self.scaler_mean = self.meta.get("scaler_mean")
        self.scaler_scale = self.meta.get("scaler_scale")
        if self.scaler_mean is not None:
            self.scaler_mean = np.array(self.scaler_mean, dtype=np.float32)
        if self.scaler_scale is not None:
            self.scaler_scale = np.array(self.scaler_scale, dtype=np.float32)

        print(f"Channels: {self.channels}, window_len={self.window_len}")
        print(f"Flags: {self.flags}")
        print(f"Feature dims: {len(self.feature_cols)}")
        
        # ✅ 更新 SLOPE_FACTOR (優先從 Meta 讀取)
        self.slope_factor = self.meta.get("slope_factor", self.default_slope_factor)
        if "slope_factor" in self.meta:
            print(f"[INIT] Loaded slope_factor from meta: {self.slope_factor}")
        else:
            print(f"[INIT] meta.slope_factor missing, using default: {self.slope_factor}")

    def _init_buffers(self):
        for ch in self.channels:
            self.window_row[ch] = deque(maxlen=self.window_len)
            self.window_base[ch] = deque(maxlen=self.window_len)
            self.window_hold[ch] = deque(maxlen=self.window_len)

    def clear_buffers(self):
        for ch in self.channels:
            self.window_row[ch].clear()
            self.window_base[ch].clear()
            self.window_hold[ch].clear()
        self.sample_before_window = None
        print("[System] Buffers cleared.")

    def push_data(self,
                  row_vals: Dict[int, int],
                  base_vals: Dict[int, int],
                  hold_vals: Dict[int, int],
                  gain_map: Dict[int, float]):
        """
        推入 window：
        - row：做 gain mapping（B->A）
        - base：保留原 base（B 的 base）
        - hold：保留原 hold（B 的 hold）

        為什麼 base/hold 不映射？
        因為我們要在 predict() 內用 span_mapped = abs(hold-base)*gain
        這樣 dn = d_mapped / span_mapped = (row-base)/abs(hold-base)（bend fraction）
        """
        # Validate the complete sample before appending anything.  Returning
        # halfway through this loop would leave channel buffers misaligned.
        if any(ch not in row_vals or ch not in base_vals for ch in self.channels):
            return

        if self.is_buffer_full():
            # 保存即將被 rolling buffer 擠出的相鄰樣本。每筆輸入都會走到這裡，
            # 因此它會隨資料前進，不受 API 的 infer_stride 推論頻率影響。
            previous_normalized = []
            for ch in self.channels:
                previous_row = float(self.window_row[ch][0])
                previous_base = float(self.window_base[ch][0])
                previous_hold = float(self.window_hold[ch][0])
                gain = float(gain_map.get(ch, 1.0))
                previous_span = max(abs(previous_hold - previous_base) * gain, 1.0)
                previous_normalized.append((previous_row - previous_base) / previous_span)
            self.sample_before_window = np.asarray(previous_normalized, dtype=np.float32)

        for ch in self.channels:
            r = float(row_vals[ch])
            b = float(base_vals[ch])
            h = float(hold_vals.get(ch, self.manual_holdavg.get(ch, 0)))  # fallback

            g = float(gain_map.get(ch, 1.0))

            # d_raw = r - b
            # d_mapped = d_raw * g
            # row_mapped = b + d_mapped
            row_mapped = b + (r - b) * g

            self.window_row[ch].append(row_mapped)
            self.window_base[ch].append(b)
            self.window_hold[ch].append(h)

    def is_buffer_full(self) -> bool:
        if not self.channels:
            return False
        return all(
            len(self.window_row[ch]) >= self.window_len
            and len(self.window_base[ch]) >= self.window_len
            and len(self.window_hold[ch]) >= self.window_len
            for ch in self.channels
        )

    # ----------------------------
    # Feature builders (v5 aligned)
    # ----------------------------
    def _extract_stats_named(self, sig: np.ndarray, prefix: str, out: Dict[str, float]) -> None:
        """
        產生與 train v5 相同命名：
          {prefix}mean / {prefix}std / {prefix}energy
        prefix 例： "d_ch1_"、"dn_ch3_"
        """
        if self.flags.get("feat_mean", True):
            out[prefix + "mean"] = float(np.mean(sig))
        if self.flags.get("feat_std", True):
            out[prefix + "std"] = float(np.std(sig))
        if self.flags.get("feat_energy", True):
            out[prefix + "energy"] = float(np.sum(sig * sig) / max(1, sig.size))

    def _extract_ratio_named(self, sig_bin: np.ndarray, key: str, out: Dict[str, float]) -> None:
        """
        train v5 的 high feature 是 window ratio（v5 train 用 _extract_window_high_feats）
        你偵測端是單一 window，所以直接 mean(bin)
        """
        out[key] = float(np.mean(sig_bin))

    def predict(self, gain_map: Dict[int, float]) -> Optional[ModelPrediction]:
        """Buffer 滿時回傳一次原始推論；呼叫頻率由 Detection API 負責。"""
        if not self.is_buffer_full():
            return None

        # if self.model_type == "cnn":
        #     # 1) CNN uses raw time-series window (1, WinLen, Chans)
        #     # Order: CH1, CH2, ... (based on self.channels)
        #     window_data = []
        #     for ch in self.channels:
        #         # ✅ 與訓練集同步：使用 dn (bend fraction)
        #         # dn = (row - base) / abs(hold - base)
        #         ch_row = np.array(self.window_row[ch], dtype=np.float32)
        #         ch_base = np.array(self.window_base[ch], dtype=np.float32)
        #         ch_hold = np.array(self.window_hold[ch], dtype=np.float32)
                
        #         span = np.abs(ch_hold - ch_base)
        #         span = np.maximum(span, 1.0)
        #         dn = (ch_row - ch_base) / span
        #         window_data.append(dn)

    
        if self.model_type == "cnn":
            # 1) CNN uses raw time-series window (1, WinLen, Chans)
            # Order: CH1, CH2, ... (based on self.channels)
            window_data = []
            for ch in self.channels:
                # ✅ 與訓練集同步：使用 dn (bend fraction)
                # 注意：由於 push_data 的 ch_row 已經被展開過 g (Gain) 倍，
                # 分母的 span 也必須同步乘上 g，否則會產生「雙重縮放」Bug 導致數值失真。
                ch_row = np.array(self.window_row[ch], dtype=np.float32)
                ch_base = np.array(self.window_base[ch], dtype=np.float32)
                ch_hold = np.array(self.window_hold[ch], dtype=np.float32)
                
                g = float(gain_map.get(ch, 1.0))
                span_b = np.abs(ch_hold - ch_base)
                span_mapped = span_b * g
                span_mapped = np.maximum(span_mapped, 1.0)
                
                dn = (ch_row - ch_base) / span_mapped
                window_data.append(dn)

            # Transpose to (WinLen, 5)
            signal_norm = np.stack(window_data, axis=1)
            
            # ✅ 加入 Delta 特徵 (一階差分) - 同步訓練邏輯
            # 輔助計算：位移速率
            delta_sig = np.zeros_like(signal_norm)
            # Amplify slope to match training scaling
            delta_sig[1:] = np.diff(signal_norm, axis=0) * self.slope_factor
            if self.sample_before_window is not None:
                # Training 先對完整 CSV 做差分再切 Window；使用 Window 前一筆資料，
                # 讓 rolling detection 的第一個 Delta 保持相同時間連續性。
                delta_sig[0] = (
                    signal_norm[0] - self.sample_before_window
                ) * self.slope_factor
            
            # 組合為 12 通道 (6 Level + 6 Slope)
            combined_signal = np.concatenate([signal_norm, delta_sig], axis=1)
            X_win = np.expand_dims(combined_signal, axis=0) # (1, 35, 10)
            
            # ✅ 新增：計算變異量分支的輸入 - 僅針對原始通道 (前 5)
            X_var = np.var(signal_norm, axis=0)
            X_var = np.expand_dims(X_var, axis=0) # (1, 5)

            # ✅ 新增：計算平均位準 (Mean Level) 分支的輸入 - 這是 v9 強化 CH5 的關鍵
            X_mean = np.mean(signal_norm, axis=0)
            X_mean = np.expand_dims(X_mean, axis=0) # (1, 5)

            # 若有 scaler
            if self.scaler_mean is not None and self.scaler_scale is not None:
                if self.scaler_mean.size == X_win.shape[-1]: # num_channels
                     # print(f"[DEBUG] Applying Scaler to X_win...")
                     X_win = (X_win - self.scaler_mean) / self.scaler_scale
                else:
                     pass # CNN 通常不使用外部 Scaller，因為數據已 native 歸一化

            # ✅ 優化：改用 __call__ 代替 .predict() 以加速單筆推論 (PC 提速 10x)
            import tensorflow as tf
            inputs = [tf.convert_to_tensor(i) for i in [X_win, X_var, X_mean]]
            probs = self.clf(inputs, training=False).numpy()[0]
            
            # ✅ 診斷日誌：讓我們看清 CH5 的真實電平與歸一化平均值
            # 格式: [DIAG] CH5_mean=X.XX | PRED: label (0.XX)
            ch5_idx = 4 # CH5 is at index 4 (0-based)
            if len(self.channels) >= 5:
                # X_mean is (1, num_channels)
                curr_mean_ch5 = float(X_mean[0, ch5_idx])
                # 也獲取 top 2 預測來觀察競爭情況
                sorted_indices = np.argsort(probs)[::-1]
                top1_id = sorted_indices[0]
                top1_conf = float(probs[top1_id])
                top2_id = sorted_indices[1]
                top2_conf = float(probs[top2_id])
                
                name1 = self.id_to_name.get(top1_id, str(top1_id))
                name2 = self.id_to_name.get(top2_id, str(top2_id))
                
                # 每秒大約印 10 次 (依 Stride 而定)
                print(f"[DIAG] CH5_mn={curr_mean_ch5:6.3f} | Top1: {name1:8}({top1_conf:.2f}), Top2: {name2:8}({top2_conf:.2f})")

            pred_id = int(np.argmax(probs))
            conf = float(np.max(probs))
            return ModelPrediction(
                pred_id=pred_id,
                confidence=conf,
                probabilities=tuple(float(value) for value in probs),
            )
            
        # 2) MLP uses feature-based window
        # 1) 準備 window signals
        sig_row = {ch: np.array(self.window_row[ch], dtype=np.float32) for ch in self.channels}
        sig_base = {ch: np.array(self.window_base[ch], dtype=np.float32) for ch in self.channels}
        sig_hold = {ch: np.array(self.window_hold[ch], dtype=np.float32) for ch in self.channels}
        
        # d_mapped
        sig_d = {ch: (sig_row[ch] - sig_base[ch]).astype(np.float32) for ch in self.channels}
        
        # 2) build feat_dict（name -> value）
        feat: Dict[str, float] = {}
        
        # A) d stats
        if self.flags.get("use_delta", False):
            for ch in self.channels:
                self._extract_stats_named(sig_d[ch], prefix=f"d_ch{ch}_", out=feat)
        
        # B) dn stats（✅ v5 對齊：bend fraction）
        if self.flags.get("use_norm_by_holdavg", False):
            eps = 1e-6
            for ch in self.channels:
                # span_mapped = abs(hold-base) * gain
                # dn = d_mapped / span_mapped  == (row-base)/abs(hold-base)
                g = float(gain_map.get(ch, 1.0))
                span_b = np.abs(sig_hold[ch] - sig_base[ch]).astype(np.float32)
                span_mapped = span_b * np.float32(g) + np.float32(eps)
                
                dn = (sig_d[ch] / span_mapped).astype(np.float32)
                self._extract_stats_named(dn, prefix=f"dn_ch{ch}_", out=feat)
        
        # C) high1/high2 ratio
        if self.flags.get("use_high_feature", False):
            h1 = float(self.meta.get("high_feature", {}).get("high_threshold_1", 0.0))
            h2 = float(self.meta.get("high_feature", {}).get("high_threshold_2", 0.0))
            
            for ch in self.channels:
                sig_bin = (sig_d[ch] > h1).astype(np.float32)
                self._extract_ratio_named(sig_bin, key=f"high1_ch{ch}_high1_ratio", out=feat)
            
            for ch in self.channels:
                sig_bin = (sig_d[ch] > h2).astype(np.float32)
                self._extract_ratio_named(sig_bin, key=f"high2_ch{ch}_high2_ratio", out=feat)
        
        # D) thr global
        if self.flags.get("use_thr_features", False):
            stack = np.stack([sig_d[ch] for ch in self.channels], axis=1).astype(np.float32)
            
            thr_act = float(self.meta.get("thr_feature", {}).get("thr_active_threshold", 0.0))
            thr_db = float(self.meta.get("thr_feature", {}).get("thr_pos_deadband", 0.0))
            
            is_active = (stack > thr_act).sum(axis=1).astype(np.float32)
            feat["thr_active_cnt"] = float(np.mean(is_active))
            
            val_clipped = np.maximum(0.0, stack - np.float32(thr_db))
            pos_sum = val_clipped.sum(axis=1).astype(np.float32)
            feat["thr_total_pos"] = float(np.mean(pos_sum))
        
        # E) bool_thr ratio
        if self.flags.get("use_bool_thr_feature", False):
            val = float(self.meta.get("flags", {}).get("bool_thr_value", 100.0))
            for ch in self.channels:
                sig_bin = (sig_d[ch] > val).astype(np.float32)
                self._extract_ratio_named(sig_bin, key=f"bool_thr_ch{ch}_bool_thr_ratio", out=feat)
        
        # 3) ✅ 依 meta.feature_cols 排列 X
        missing = [c for c in self.feature_cols if c not in feat]
        if missing:
            # 缺欄位代表：你的 detect feature 命名/flags 與 train v5 不一致
            raise ValueError(f"[FEAT] missing {len(missing)} cols, e.g. {missing[:8]}")
        
        X = np.array([[feat[c] for c in self.feature_cols]], dtype=np.float32)
        
        # ✅ 執行特徵縮放 (MaxAbsScaler 邏輯：(X - mean) / scale)
        if self.scaler_mean is not None and self.scaler_scale is not None:
            # 確保維度一致
            if X.shape[1] == self.scaler_mean.size == self.scaler_scale.size:
                X = (X - self.scaler_mean) / self.scaler_scale
            else:
                print(f"[WARN] Scaler dim mismatch: X={X.shape[1]}, mean={self.scaler_mean.size}")
        
        # 4) Inference
        probs = self.clf.predict_proba(X)[0]
        pred_id = int(np.argmax(probs))
        conf = float(np.max(probs))
        return ModelPrediction(
            pred_id=pred_id,
            confidence=conf,
            probabilities=tuple(float(value) for value in probs),
        )

# Stable 與 Dynamic 後處理由 Detection API 負責，Model 僅輸出原始預測。
