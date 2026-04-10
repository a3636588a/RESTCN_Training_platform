#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
detect_gesture_universal_manual_holdavg_v5.py

✅ 配合你提供的 v6 訓練版（Dual-SE 2-Layer CNN）的偵測端

核心改動：
1) ✅ 支援最新的 SE 注意力機制模型 (Squeeze-and-Excitation)
2) ✅ 優化推論效率，僅需 2 層捲積即可達到高精度
3) ✅ 用 meta["feature_cols"] 做「排列對齊」：避免 silent wrong inference
4) ✅ dn 計算方式改成「與訓練一致的 bend fraction」
   - dn = d_mapped / span_mapped
   - 其中 span_mapped = abs(HOLDAVG - MOVBASE) * GAIN_MAP

你只要確保：
- MODEL_PATH / META_PATH 指向 v5 訓練輸出的檔案
- PORT 改成你的 COM
"""

import time
from collections import Counter, deque
from typing import Dict, List, Optional, Tuple, Any

import joblib
import numpy as np
import serial

# =========================
# 使用者設定
# =========================
PORT = "COM6"      # TODO: 改成你的序列埠
BAUD = 921600

# ✅ 改成 v5 訓練輸出
MODEL_PATH = "gesture_model_v5.pkl"
META_PATH  = "gesture_model_meta_v5.pkl"

# 多數決參數（你可調）
CHAIN_LEN = 7
CHAIN_MIN_MAJ = 5

PRINT_PROBA = True

# ---- 手動 HOLDAVG（若 UART 沒送 SILHOLD / SILHOLDAVG）----
USE_MANUAL_HOLDAVG = True
MANUAL_HOLDAVG = {
    1: 17254,
    2: 20107,
    3: 19845,
    4: 19759,
    5: 19427,
    6: 15493,
}

# ---- 手套A（標準）尺度（用於 Gain Mapping 計算 span_A）----
# 注意：只用來計算 Gain，dn 不再用固定 spanA，而是用「span_mapped」
STD_BASELINE_A = {
    1: 15353,
    2: 15366,
    3: 15289,
    4: 15429,
    5: 15393,
    6: 15197,
}
STD_HOLDAVG_A = MANUAL_HOLDAVG  # 你也可以改成你想用的標準 span

# ---- 手套跨設備尺度對齊 (Gain Mapping) ----
ENABLE_GAIN_MAP = True
MIN_SPAN_B = 300.0      # 保護：B 的跨度太小不要用來算 gain（避免爆炸）
GAIN_CLAMP_MIN = 0.5
GAIN_CLAMP_MAX = 2.5

# 每個 CH 的增益（B -> A），沒校正前預設 1.0
GAIN_MAP: Dict[int, float] = {ch: 1.0 for ch in STD_BASELINE_A.keys()}
GAIN_READY = False

# ✅ 解析斜率特徵的放大倍率 (須與訓練端一致，預設 20.0)
SLOPE_FACTOR = 20.0


# ==========================================
# Helper Classes
# ==========================================
class MajorityChain:
    """
    舊版多數決濾波器
    """
    def __init__(self, length=CHAIN_LEN, min_maj=CHAIN_MIN_MAJ):
        self.buffer = deque(maxlen=length)
        self.min_maj = min_maj
        self.current_id = None

    def update(self, pred_id: int) -> Tuple[Optional[int], bool]:
        self.buffer.append(pred_id)
        if len(self.buffer) < self.buffer.maxlen:
            return self.current_id, False

        counts = Counter(self.buffer)
        best_id, count = counts.most_common(1)[0]

        changed = False
        if count >= self.min_maj:
            if best_id != self.current_id:
                self.current_id = best_id
                changed = True
        return self.current_id, changed


def parse_line(line: str):
    """
    解析 MCU 傳來的 $SIL... 字串
    格式（你目前的專案）：
      $SILMOVBASE,YYYYMMDD,CNT,CHNs,base1,base2,...*CS
      $SILHOLD,...  or $SILHOLDAVG,...
      $SILINO,...   or $SILROW,...
    """
    line = line.strip()
    if not line.startswith("$"):
        return None
    if "*" in line:
        main = line.split("*")[0]
    else:
        main = line

    parts = main.split(",")
    if len(parts) < 5:
        return None

    try:
        msg = parts[0][1:]
        cnt = int(parts[2])
        chn = int(parts[3])
        
        if chn < 0 or chn > 32:
            return None
            
        # ✅ 更強健的數值解析：過濾掉空字串或 checksum 殘留
        vals = []
        for v in parts[4:]:
            v = v.strip().split('*')[0] # 徹底過濾 checksum 可能殘留在最後一個數字的情況
            if not v: continue
            try:
                vals.append(int(v))
            except ValueError:
                break 
        
        # ✅ 嚴格檢查：如果收到的數據長度不等於標榜的通道數，視為無效封包 (串口雜訊)
        # 這能防止因為數據截斷導致的通道偏移或增益誤算
        if len(vals) < chn:
            return None
            
        return msg, cnt, chn, vals[:chn]
    except Exception:
        return None


# ==========================================
# Gain / Calibration Logic
# ==========================================
def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _try_update_gain_from_pending(current_base_map: Dict[int, int],
                                  current_hold_map: Dict[int, int],
                                  channels: List[int],
                                  force=False) -> bool:
    """
    使用 HOLD/HOLDAVG 封包來計算粗調 Gain
    gain = span_A / span_B
    """
    global GAIN_READY
    if not ENABLE_GAIN_MAP:
        return False

    updated = False

    for ch in channels:
        if ch not in current_base_map:
            continue

        base_b = float(current_base_map[ch])

        # 來源：優先用 MCU 送的 hold；沒有就用手動 hold
        if ch in current_hold_map:
            hold_b = float(current_hold_map[ch])
        else:
            if not USE_MANUAL_HOLDAVG:
                continue
            hold_b = float(MANUAL_HOLDAVG.get(ch, 0))

        span_b = abs(hold_b - base_b)
        if span_b < MIN_SPAN_B:
            continue

        span_a = float(STD_HOLDAVG_A.get(ch, 0) - STD_BASELINE_A.get(ch, 0))
        if span_a <= 1.0:
            continue

        raw_g = span_a / span_b
        new_g = clamp(raw_g, GAIN_CLAMP_MIN, GAIN_CLAMP_MAX)

        # ✅ 優化：增加死區 (Deadzone)，避免感測器小抖動一值跳更新 Log
        # 只有當增益變化超過 2% (0.02) 時才更新，除非 force=True
        old_g = GAIN_MAP.get(ch, 1.0)
        if force or abs(new_g - old_g) > 0.02:
            GAIN_MAP[ch] = new_g
            updated = True

    if updated:
        GAIN_READY = True
        print(f"[GAIN] Updated Coarse: {GAIN_MAP}")

    return updated


# ==========================================
# Main Detector Class
# ==========================================
class RealtimeGestureDetector:
    def __init__(self):
        self.clf = None
        self.meta: Dict[str, Any] = {}
        # 改回多數決
        self.chain = MajorityChain()

        # window buffers：存「等效 A」的 row / base（row 會做 gain mapping）
        self.window_row: Dict[int, deque] = {}
        self.window_base: Dict[int, deque] = {}
        self.window_hold: Dict[int, deque] = {}  # ✅ v5：dn 需要 span，所以 hold 也要緩存（對齊 window）

        self.channels: List[int] = [1, 2, 3, 4, 5]
        self.window_len = 30

        self.flags: Dict[str, Any] = {}
        self.id_to_name: Dict[int, str] = {}

        self.feature_cols: List[str] = []
        
        # ✅ v5：效能優化與正規化
        self.predict_stride = 10  # ✅ 診斷模式：稍微調慢速度，確保每一幀推論都不丟包 (原為 1)
        self.predict_counter = 0

        self.load_model_resources()
        self._init_buffers()

    def load_model_resources(self):
        print(f"Loading meta from {META_PATH} ...")
        self.meta = joblib.load(META_PATH)
        self.model_type = self.meta.get("model_type", "mlp")

        print(f"Loading model ({self.model_type}) from {MODEL_PATH} ...")
        actual_model_path = MODEL_PATH
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
        
        # ✅ 根據模型類別數量重新初始化濾波器
        if len(self.id_to_name) > 0:
            self.chain = MajorityChain()

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
        self.slope_factor = self.meta.get("slope_factor", SLOPE_FACTOR)
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
        self.chain = MajorityChain()
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
        for ch in self.channels:
            if ch not in row_vals or ch not in base_vals:
                return

            r = float(row_vals[ch])
            b = float(base_vals[ch])
            h = float(hold_vals.get(ch, MANUAL_HOLDAVG.get(ch, 0)))  # fallback

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
        return len(self.window_row[self.channels[0]]) >= self.window_len

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

    def predict(self, gain_map: Dict[int, float]) -> Tuple[Optional[int], float, Optional[np.ndarray]]:
        """
        回傳：
          (pred_id, conf, probs)
        """
        if not self.is_buffer_full():
            return None, 0.0, None

        # ✅ Stride 優化：減少預測頻率
        self.predict_counter += 1
        if self.predict_counter < self.predict_stride:
            return None, 0.0, None
        self.predict_counter = 0

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
            return pred_id, conf, probs
            
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
        return pred_id, conf, probs


# ==========================================
# Main Loop
# ==========================================
def main():
    print(f"--- Gesture Detect V5 (Aligned with Train V5) ---")
    print(f"Port: {PORT}, Baud: {BAUD}")
    print(f"Model: {MODEL_PATH}")
    print(f"Meta : {META_PATH}")

    # Setup Serial
    try:
        ser = serial.Serial(PORT, BAUD, timeout=0.1)
        print("Serial opened.")
    except Exception as e:
        print(f"Serial error: {e}")
        return

    detector = RealtimeGestureDetector()

    # 狀態：最新 base/hold
    current_base_map: Dict[int, int] = {}
    current_hold_map: Dict[int, int] = {}

    try:
        while True:
            line = ser.readline()
            if not line:
                continue

            try:
                line_str = line.decode("utf-8", errors="ignore")
            except Exception:
                continue

            parsed = parse_line(line_str)
            if not parsed:
                continue

            msg, cnt, chn, vals = parsed

            # --- SILMOVBASE ---
            if msg.startswith("SILMOVBASE"):
                for i in range(chn):
                    current_base_map[i + 1] = vals[i]

                # 嘗試更新 Gain（若 hold 也有了）
                if _try_update_gain_from_pending(current_base_map, current_hold_map, detector.channels):
                    detector.clear_buffers()

            # --- SILHOLD / SILHOLDAVG ---
            elif msg.startswith("SILHOLD") or msg.startswith("SILHOLDAVG"):
                for i in range(chn):
                    current_hold_map[i + 1] = vals[i]

                if _try_update_gain_from_pending(current_base_map, current_hold_map, detector.channels):
                    detector.clear_buffers()

            # --- SILINO / SILROW ---
            elif msg.startswith("SILINO") or msg.startswith("SILROW"):
                if not current_base_map:
                    continue

                row_vals = {i + 1: vals[i] for i in range(chn)}

                # hold fallback（若沒收到 SILHOLD）
                hold_vals = dict(current_hold_map)
                if USE_MANUAL_HOLDAVG:
                    for ch in detector.channels:
                        if ch not in hold_vals and ch in MANUAL_HOLDAVG:
                            hold_vals[ch] = MANUAL_HOLDAVG[ch]

                detector.push_data(row_vals, current_base_map, hold_vals, GAIN_MAP)

                try:
                    pred_id, conf, probs = detector.predict(GAIN_MAP)
                except Exception as e:
                    print(f"[PRED_ERR] {e}")
                    continue

                if pred_id is not None:
                    # 使用多數決濾波器更新穩定狀態
                    stable_id, changed = detector.chain.update(pred_id)
                    pred_name = detector.id_to_name.get(pred_id, str(pred_id))
                    stable_name = detector.id_to_name.get(stable_id, str(stable_id)) if stable_id is not None else None

                    if PRINT_PROBA:
                        g1 = GAIN_MAP.get(1, 1.0)
                        print(f"[PRED] {pred_name} ({conf:.2f}) -> Stable: {stable_name} | G1={g1:.2f}")
                    else:
                        if changed:
                            print(f"[STABLE] {stable_name}")

            # 其他封包先忽略
            else:
                continue

    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        try:
            ser.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
