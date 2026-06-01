# ui_v4.py (Train + Detect tabs, shared terminal, busy lock)
from __future__ import annotations

import json
import os
import re
import sys
import threading
import time
from datetime import datetime
import numpy as np
import joblib
import serial
from dataclasses import dataclass, field
from pathlib import Path
import csv
from collections import Counter, deque
from typing import Optional, Dict, List, Any, Callable

from PySide6.QtCore import Qt, QThread, Signal, QObject, QTimer, QEvent
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QPushButton, QLabel, QLineEdit, QFileDialog, QCheckBox, QSpinBox, QDoubleSpinBox,
    QComboBox, QTextEdit, QMessageBox, QGroupBox, QScrollArea,
    QTableWidget, QTableWidgetItem, QHeaderView, QSplitter, QTabWidget,
    QDialog, QDialogButtonBox, QProgressBar, QGridLayout
)

import gen_cnn_lib
import gen_dynamic_model_header as gen_dyn


# =========================
# StdIO Redirection (For Frozen/Windowed mode)
# =========================
class QLogRedirector(QObject):
    log_signal = Signal(str)

    def write(self, s):
        # Filter purely empty writes to avoid noise
        if s and s.strip():
            self.log_signal.emit(s.strip())

    def flush(self):
        pass


# =========================
# Dynamic Matcher
# =========================
class DynamicMatcher:
    def __init__(self, gestures: List[dict]):
        self.gestures = gestures
        self.prefix_to_id = {}  # 從 detect 的 id_to_name 反轉
        self.reset()

    def set_prefix_to_id(self, id_to_name: Dict[int, str]):
        self.prefix_to_id = {v.lower(): k for k, v in id_to_name.items()}

    def reset(self):
        self.buffer = []
        self.timestamps = []
        self.last_trigger_time = 0.0

    def feed(self, stable_id: int, ts: float) -> Optional[str]:
        # cooldown 5 秒
        if ts - self.last_trigger_time < 1.0:
            return None

        # 去重
        if not self.buffer or self.buffer[-1] != stable_id:
            self.buffer.append(stable_id)
            self.timestamps.append(ts)

        # 時間窗裁剪（每個 gesture 用自己的 time_window）
        # 為了簡單，這裡用最大值；若要精確每個不同，要在 match 內裁剪
        max_win = max((g.get("time_window", 2.0) for g in self.gestures), default=2.0)
        while self.timestamps and ts - self.timestamps[0] > max_win:
            self.buffer.pop(0)
            self.timestamps.pop(0)

        # 按長度優序匹配（長的先）
        for g in sorted(self.gestures, key=lambda g: -len(g["sequence"].split(","))):
            if self._match(g, self.buffer, ts):
                self.reset()
                self.last_trigger_time = ts
                return g["name"]
        return None

    def _resolve_token(self, token: str) -> int:
        token = token.strip()
        # 純數字當 id
        if token.isdigit():
            return int(token)
        # 否則當 label name（不區分大小寫）
        return self.prefix_to_id.get(token.lower(), -1)

    def _match(self, g: dict, seq: List[int], ts: float) -> bool:
        target_seq = [self._resolve_token(tok) for tok in g["sequence"].split(",")]
        if -1 in target_seq:
            return False  # 有 token 解析失敗
        max_gap = g.get("max_gap", 2)
        time_window = g.get("time_window", 2.0)

        # 滑動窗口 + 容錯匹配
        for start in range(len(seq) - len(target_seq) + 1):
            # 檢查時間窗
            if len(seq) >= start + len(target_seq):
                t_start = self.timestamps[start]
                t_end = self.timestamps[start + len(target_seq) - 1]
                if t_end - t_start > time_window:
                    continue
            if self._match_with_gap(seq[start:], target_seq, max_gap):
                return True
        return False

    def _match_with_gap(self, seq: List[int], target: List[int], max_gap: int) -> bool:
        i = 0
        gaps = 0
        for t in target:
            while i < len(seq) and seq[i] != t:
                i += 1
                gaps += 1
                if gaps > max_gap:
                    return False
            if i >= len(seq):
                return False
            i += 1
        return True


# =========================
# Trainer
# =========================
import train_gesture_cnn_v1 as cnn_trainer
import train_gesture_ds_tcn_v1 as ds_tcn_trainer

# =========================
# Detector
# =========================
import detect_gesture_universal_manual_holdavg_v5 as detect

# =========================
# Codegen tools
# =========================
import gen_dynamic_model_header as gen_dyn
import gen_cnn_lib


# -------------------------
# ✅ Completely disable wheel for SpinBox / DoubleSpinBox
# -------------------------
class NoWheelSpinBox(QSpinBox):
    def wheelEvent(self, e):
        e.ignore()


class NoWheelDoubleSpinBox(QDoubleSpinBox):
    def wheelEvent(self, e):
        e.ignore()


def _tag_line(tag: str, s: str) -> str:
    return f"[{tag}] {s}"


class CnnPostProcessor:
    def __init__(self, alpha: float, margin: float, exit_thresh: float, tier_data: dict, num_classes: int):
        self.alpha = alpha
        self.margin = margin
        self.exit_thresh = exit_thresh
        self.tier_data = tier_data
        
        self.num_classes = num_classes
        self.smoothed_probs = np.zeros(num_classes, dtype=np.float32)
        self.active_id = -1
        self.last_best_id = -1
        self.stable_count = 0
        
        # Mapping tiers from UI terminology to MCU logic
        self.p_ids = set(tier_data.get('priority_ids', []))     # "Fast" Tier
        self.r_ids = set(tier_data.get('restricted_ids', []))   # "Strict" Tier
        
        self.tp = tier_data.get('thresh_priority', 0.70)
        self.tr = tier_data.get('thresh_restricted', 0.75)
        self.tn = tier_data.get('thresh_entry', 0.50)
        self.sn = tier_data.get('stable_normal', 10)
        self.sr = tier_data.get('stable_restricted', 20)

    def update(self, probs: list) -> int:
        probs_np = np.array(probs, dtype=np.float32)
        
        # 1. EWMA Smoothing (Identical to C: ctx->proba_smooth[i] = (ALPHA * raw) + (1-ALPHA)*ctx->proba_smooth[i])
        if np.sum(self.smoothed_probs) == 0:
            self.smoothed_probs = probs_np
        else:
            self.smoothed_probs = self.alpha * probs_np + (1.0 - self.alpha) * self.smoothed_probs
        
        # Find current best candidate
        best_id = int(np.argmax(self.smoothed_probs))
        max_smooth_val = self.smoothed_probs[best_id]
        
        # 2. Latch Exit (Force reset if active signal becomes too weak)
        if self.active_id != -1:
            if self.smoothed_probs[self.active_id] < self.exit_thresh:
                self.active_id = -1
        
        # 3. Tiered Validation Logic
        if best_id != -1 and best_id != self.active_id:
            qual = False
            is_p = (best_id in self.p_ids)
            is_r = (best_id in self.r_ids)
            
            if is_p and max_smooth_val >= self.tp:
                # [TIER 1: PRIORITY / FAST] Instant
                qual = True
            else:
                # [TIER 2 & 3] Stability required
                if best_id == self.last_best_id:
                    self.stable_count += 1
                else:
                    self.stable_count = 1
                
                if is_r:
                    # [TIER 3: RESTRICTED / STRICT]
                    if max_smooth_val >= self.tr and self.stable_count >= self.sr:
                        qual = True
                elif max_smooth_val >= self.tn:
                    # [TIER 2: STANDARD / NORMAL]
                    if self.stable_count >= self.sn:
                        qual = True
            
            # 4. Switching Guard (Margin)
            if qual and self.active_id != -1:
                active_prob = self.smoothed_probs[self.active_id]
                if max_smooth_val < (active_prob + self.margin):
                    qual = False
            
            if qual:
                self.active_id = best_id
                self.stable_count = 0
                
        elif best_id == self.active_id:
            self.stable_count = 0
            
        self.last_best_id = best_id
        return self.active_id


# =========================
# Train worker
# =========================
class TrainWorker(QObject):
    log_line = Signal(str)
    finished_ok = Signal(dict)
    finished_err = Signal(str)

    def __init__(self, cfg: cnn_trainer.TrainCfg, stop_event: threading.Event, backbone: str = "cnn"):
        super().__init__()
        self.cfg = cfg
        self.stop_event = stop_event
        self.backbone = (backbone or "cnn").strip().lower()

    def run(self):
        try:
            if self.backbone == "ds_tcn":
                res = ds_tcn_trainer.train_ds_tcn_from_cfg(
                    self.cfg,
                    log_fn=lambda s: self.log_line.emit(_tag_line("TRAIN_DS_TCN", s)),
                    stop_event=self.stop_event
                )
            else:
                res = cnn_trainer.train_cnn_from_cfg(
                    self.cfg,
                    log_fn=lambda s: self.log_line.emit(_tag_line("TRAIN_CNN", s)),
                    stop_event=self.stop_event
                )
            self.finished_ok.emit(res)
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.finished_err.emit(str(e))


# =========================
# Detect worker
# =========================
@dataclass
class DetectCfg:
    port: str
    baud: int
    model_path: str
    meta_path: str

    # Post-processing (Sync with MCU logic)
    post_alpha: float
    post_margin: float
    post_tier_data: dict
    post_exit_thresh: float
    post_slope_factor: float
    infer_stride: int
    print_proba: bool

    # manual holdavg
    use_manual_holdavg: bool
    manual_holdavg: Dict[int, int]

    # gain map
    enable_gain_map: bool
    std_baseline_a: Dict[int, int]
    std_holdavg_a: Dict[int, int]
    min_span_b: float
    gain_clamp_min: float
    gain_clamp_max: float


@dataclass
class GenCnnCodeCfg:
    meta_path: str
    model_path: str
    outdir: str
    base_name: str = "cnn"
    std_base_a: list[int] = field(default_factory=list)
    std_hold_a: list[int] = field(default_factory=list)
    data_dir: str = ""
    # Post-processing
    alpha: float = 0.20
    margin: float = 0.45
    exit_thresh: float = 0.25
    infer_stride: int = 6
    slope_factor: float = 20.0
    tier_data: dict = field(default_factory=dict)




@dataclass
class AutoBuildCfg:
    detect_proj_dir: str
    feature_proj_dir: str
    rebuild_proj_dir: str
    build_tool_dir: str
    last_gencode_output_dir: str
    auto_cleanup: bool = True


class DetectWorker(QObject):
    log_line = Signal(str)
    finished_ok = Signal(dict)
    finished_err = Signal(str)
    dynamic_triggered = Signal(str)
    stable_changed = Signal(str)

    def __init__(self, cfg: DetectCfg, stop_event: threading.Event):
        super().__init__()
        self.cfg = cfg
        self.stop_event = stop_event

    def _log(self, s: str):
        self.log_line.emit(_tag_line("DETECT", s))

    def _load_dynamic_gestures(self) -> List[dict]:
        path_str = getattr(self, "dynamic_json_path", "dynamic_gestures.json")
        try:
            path = Path(path_str)
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                return data.get("dynamic_gestures", [])
        except Exception:
            pass
        return [{"name": "NICE", "sequence": "ok,peace", "max_gap": 2, "time_window": 2.0}]

    def run(self):
        try:
            detect.PORT = self.cfg.port
            detect.BAUD = int(self.cfg.baud)
            detect.MODEL_PATH = self.cfg.model_path
            detect.META_PATH = self.cfg.meta_path
            detect.PRINT_PROBA = bool(self.cfg.print_proba)
            detect.USE_MANUAL_HOLDAVG = bool(self.cfg.use_manual_holdavg)
            detect.MANUAL_HOLDAVG = {int(k): int(v) for k, v in (self.cfg.manual_holdavg or {}).items()}
            detect.ENABLE_GAIN_MAP = bool(self.cfg.enable_gain_map)
            detect.STD_BASELINE_A = {int(k): int(v) for k, v in (self.cfg.std_baseline_a or {}).items()}
            detect.STD_HOLDAVG_A = {int(k): int(v) for k, v in (self.cfg.std_holdavg_a or {}).items()}
            detect.MIN_SPAN_B = float(self.cfg.min_span_b)
            detect.GAIN_CLAMP_MIN = float(self.cfg.gain_clamp_min)
            detect.GAIN_CLAMP_MAX = float(self.cfg.gain_clamp_max)
            detect.SLOPE_FACTOR = float(self.cfg.post_slope_factor)
            detect.GAIN_READY = False

            self._log("--- Detect started ---")
            
            # --- Auto-healing for CNN model paths ---
            try:
                if Path(detect.META_PATH).exists():
                    import joblib
                    meta = joblib.load(detect.META_PATH)
                    if meta.get("model_type") == "cnn":
                        if detect.MODEL_PATH.endswith(".pkl"):
                            p = Path(detect.MODEL_PATH)
                            keras_path = str(p.with_suffix(".keras"))
                            if Path(keras_path).exists():
                                self._log(f"[FIX] Detected CNN model type in meta, but Model Path was .pkl. Auto-switching to: {keras_path}")
                                detect.MODEL_PATH = keras_path
                            else:
                                parent_keras = str(p.parent.parent / p.name.replace(".pkl", ".keras"))
                                if Path(parent_keras).exists():
                                    self._log(f"[FIX] CNN model found in PARENT folder. Auto-switching to: {parent_keras}")
                                    detect.MODEL_PATH = parent_keras
                                else:
                                    self._log("[WARN] Meta says model_type='cnn' but no .keras file found. Keras 3 may fail to load .pkl.")
            except Exception as e:
                self._log(f"[WARN] Failed to pre-check meta for healing: {e}")

            self._log(f"Port: {detect.PORT}, Baud: {detect.BAUD}")
            self._log(f"Model: {detect.MODEL_PATH}")
            self._log(f"Meta : {detect.META_PATH}")

            dynamic_cfg = self._load_dynamic_gestures()
            matcher = DynamicMatcher(dynamic_cfg)

            try:
                ser = serial.Serial(detect.PORT, detect.BAUD, timeout=0.1)
                ser.reset_input_buffer()
                self._log("Serial opened & Buffer reset.")
                self._log(f"[INIT] Stride: {self.cfg.infer_stride}, Exit: {self.cfg.post_exit_thresh}, Alpha: {self.cfg.post_alpha}")
            except Exception as e:
                raise RuntimeError(f"Open serial failed: {e}")

            detector = detect.RealtimeGestureDetector()
            matcher.set_prefix_to_id(detector.id_to_name)

            current_hold_map = {}
            channels = list(getattr(detector, "channels", [1, 2, 3, 4, 5, 6]))
            current_base_map = dict(detect.STD_BASELINE_A)
            
            if current_base_map:
                self._log(f"[INIT] Using static baseline from UI: {current_base_map}")
            
            if detect.ENABLE_GAIN_MAP:
                try:
                    detect._try_update_gain_from_pending(current_base_map, current_hold_map, channels)
                except Exception: pass

            post_proc = None
            if detector and detector.clf is not None:
                post_proc = CnnPostProcessor(
                    alpha=self.cfg.post_alpha,
                    margin=self.cfg.post_margin,
                    exit_thresh=self.cfg.post_exit_thresh,
                    tier_data=self.cfg.post_tier_data,
                    num_classes=len(detector.id_to_name)
                )

            row_counter = 0
            while not self.stop_event.is_set():
                try:
                    line = ser.readline().decode(errors="ignore").strip()
                    if not line:
                        continue

                    parsed = detect.parse_line(line)
                    if parsed is None:
                        continue
                    msg, cnt, chn, vals = parsed

                    if msg.startswith("SILMOVBASE"):
                        for i in range(min(int(chn), len(vals))):
                            current_base_map[i + 1] = vals[i]
                        if detect.ENABLE_GAIN_MAP:
                            detect._try_update_gain_from_pending(current_base_map, current_hold_map, channels)

                    elif msg.startswith("SILHOLD") or msg.startswith("SILHOLDAVG"):
                        for i in range(min(int(chn), len(vals))):
                            current_hold_map[i + 1] = vals[i]
                        if detect.ENABLE_GAIN_MAP:
                            detect._try_update_gain_from_pending(current_base_map, current_hold_map, channels)

                    elif msg.startswith("SILROWDATA") or msg.startswith("SILROW") or msg.startswith("SILINO"):
                        if not current_base_map:
                            continue

                        row_map = {i + 1: vals[i] for i in range(min(int(chn), len(vals)))}
                        hold_map = dict(current_hold_map)
                        if detect.USE_MANUAL_HOLDAVG:
                            for ch in detector.channels:
                                if ch not in hold_map and ch in detect.MANUAL_HOLDAVG:
                                    hold_map[ch] = detect.MANUAL_HOLDAVG[ch]

                        detector.push_data(row_map, current_base_map, hold_map, detect.GAIN_MAP)
                        
                        # Apply Inference Stride (MCU-parity)
                        row_counter += 1
                        if (row_counter % self.cfg.infer_stride) != 0:
                            continue

                        pred_id, conf, probs = detector.predict(detect.GAIN_MAP)
                        
                        if pred_id is not None:
                            stable_id = -1
                            if post_proc:
                                stable_id = post_proc.update(list(probs))
                            
                            pred_name = detector.id_to_name.get(pred_id, str(pred_id))
                            stable_name = detector.id_to_name.get(stable_id, str(stable_id)) if stable_id != -1 else "convert"

                            last_id = getattr(self, "_last_sent_stable_id", -2)
                            changed = (stable_id != last_id)

                            if changed:
                                self._last_sent_stable_id = stable_id
                                self.stable_changed.emit(stable_name)

                            if changed or stable_id != -1:
                                trig = matcher.feed(stable_id, time.time())
                                if trig:
                                    self._log(f"[DYNAMIC] {trig}")
                                    self.dynamic_triggered.emit(trig)

                            if detect.PRINT_PROBA and probs is not None:
                                probs_l = list(probs)
                                top_idx = sorted(range(len(probs_l)), key=lambda i: probs_l[i], reverse=True)[:5]
                                top = " | ".join([f"{detector.id_to_name.get(i, str(i))}:{probs_l[i]:.2f}" for i in top_idx])
                                self._log(f"[PRED] {pred_name} ({conf:.2f}) -> {stable_name} | {top}")
                            elif changed:
                                self._log(f"[STABLE] {stable_name}")

                except Exception as e:
                    self._log(f"[PRED_ERR] {e}")

            try:
                ser.close()
            except Exception: pass
            self.finished_ok.emit({"stopped": True})
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.finished_err.emit(str(e))


# =========================
# Build worker
# =========================
@dataclass
class BuildCfg:
    proj_dir: str
    build_tool_dir: str
    config_name: str = "Debug"
    do_clean: bool = False
    target_name: str = "glove_ml_mlp"



class BuildWorker(QObject):
    log_line = Signal(str)
    finished_ok = Signal(dict)
    finished_err = Signal(str)

    def __init__(self, cfg: BuildCfg, stop_event: threading.Event):
        super().__init__()
        self.cfg = cfg
        self.stop_event = stop_event

    def _log(self, s: str):
        self.log_line.emit(_tag_line("BUILD", s))

    def run(self):
        try:
            import subprocess
            import os

            self._log("--- Build started ---")
            self._log(f"Project: {self.cfg.proj_dir}")
            self._log(f"Build tool: {self.cfg.build_tool_dir}")

            # 檢查 build bat 是否存在
            build_bat = os.path.join(self.cfg.build_tool_dir, "build_glove_debug.bat")
            if not os.path.exists(build_bat):
                raise RuntimeError(f"Build script not found: {build_bat}")

            # 執行建置命令：build_glove_debug.bat <PROJ_DIR> Debug clean --require-fsp
            
            config_name = getattr(self.cfg, "config_name", "Debug")
            do_clean = getattr(self.cfg, "do_clean", False)
            target_name = getattr(self.cfg, "target_name", "glove_ml_mlp_v1")
            
            cmd = [
                build_bat,
                self.cfg.proj_dir,
                config_name,
            ]
            
            if do_clean:
                cmd.append("clean")
            
            # Always add target as the last parameter
            cmd.append(target_name)

            self._log(f"Executing: {' '.join(cmd)}")
            self._log(f"Target: {target_name}")

            # 執行建置
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',
                errors='replace',
                bufsize=1,
                universal_newlines=True,
                cwd=self.cfg.build_tool_dir
            )

            # 即時輸出日誌
            while True:
                if self.stop_event.is_set():
                    process.terminate()
                    self._log("Build stopped by user")
                    break

                output = process.stdout.readline()
                if output == '' and process.poll() is not None:
                    break
                if output:
                    self._log(output.strip())

            # 等待程序完成
            return_code = process.poll()
            if return_code == 0:
                self._log("--- Build completed successfully ---")
                self.finished_ok.emit({"return_code": return_code})
            else:
                self._log(f"--- Build failed with return code: {return_code} ---")
                self.finished_err.emit(f"Build failed with return code: {return_code}")

        except Exception as e:
            self._log(f"Build error: {str(e)}")
            self.finished_err.emit(str(e))


# =========================
# Flash worker
# =========================
@dataclass
class FlashCfg:
    srec_path: str
    com_port: str
    tool_dir: str

class FlashWorker(QObject):
    log_line = Signal(str)
    finished_ok = Signal(dict)
    finished_err = Signal(str)
    retry_requested = Signal(str)  # Special signal when device not responding

    def __init__(self, cfg: FlashCfg, stop_event: threading.Event):
        super().__init__()
        self.cfg = cfg
        self.stop_event = stop_event

    def _log(self, s: str):
        self.log_line.emit(_tag_line("FLASH", s))

    def run(self):
        try:
            import subprocess
            import os

            self._log("--- Flash started ---")
            self._log(f"SREC: {self.cfg.srec_path}")
            self._log(f"Port: {self.cfg.com_port}")

            # Try finding flash.bat
            # 1. in cfg.tool_dir/flashtool/flash.bat
            flash_bat = os.path.join(self.cfg.tool_dir, "flashtool", "flash.bat")
            if not os.path.exists(flash_bat):
                 # 2. in cfg.tool_dir/../flashtool/flash.bat (if tool_dir was buildtool)
                 flash_bat = os.path.join(os.path.dirname(self.cfg.tool_dir), "flashtool", "flash.bat")

            if not os.path.exists(flash_bat):
                # 3. Last resort: relative to this script
                base_dir = os.path.dirname(os.path.abspath(__file__))
                flash_bat = os.path.join(base_dir, "flashtool", "flash.bat")

            if not os.path.exists(flash_bat):
                raise RuntimeError(f"Flash script 'flashtool/flash.bat' not found.")

            cmd = [
                flash_bat,
                self.cfg.srec_path,
                self.cfg.com_port
            ]
            self._log(f"Executing: {' '.join(cmd)}")

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True
            )

            # Monitor output
            while True:
                if self.stop_event.is_set():
                    process.terminate()
                    self._log("Flash stopped by user")
                    break

                output = process.stdout.readline()
                if output == '' and process.poll() is not None:
                    break
                if output:
                    line = output.strip()
                    self._log(line)
                    
                    # Detect Key Events
                    if "E3000105" in line or "device is not responding" in line:
                         process.terminate()
                         self.retry_requested.emit("Device not responding")
                         return 

            return_code = process.poll()
            if return_code == 0:
                self._log("--- Flash success ---")
                self.finished_ok.emit({})
            else:
                 self._log(f"--- Flash failed with return code: {return_code} ---")
                 self.finished_err.emit(f"Return code: {return_code}")

        except Exception as e:
            self._log(f"Flash error: {str(e)}")
            self.finished_err.emit(str(e))



class GenCodeWorker(QObject):
    log_line = Signal(str)
    finished_ok = Signal(dict)
    finished_err = Signal(str)




class GenCnnCodeWorker(QObject):
    log_line = Signal(str)
    finished_ok = Signal(dict)
    finished_err = Signal(str)

    def __init__(self, cfg: GenCnnCodeCfg):
        super().__init__()
        self.cfg = cfg

    def _log(self, s: str):
        self.log_line.emit(_tag_line("GEN_CNN", s))

    def run(self):
        try:
            import os
            import gen_cnn_lib
            import importlib
            importlib.reload(gen_cnn_lib)
            
            tflite_path = None

            post_cfg = {
                'alpha': self.cfg.alpha,
                'margin': self.cfg.margin,
                'infer_stride': self.cfg.infer_stride,
                'slope_factor': self.cfg.slope_factor,
                'thresh_entry': self.cfg.tier_data.get('thresh_entry', 0.50),
                'stable_fast': self.cfg.tier_data.get('stable_fast', 0),
                'stable_normal': self.cfg.tier_data.get('stable_normal', 10),
                'stable_restricted': self.cfg.tier_data.get('stable_restricted', 20),
                'thresh_priority': self.cfg.tier_data.get('thresh_priority', 0.70),
                'thresh_restricted': self.cfg.tier_data.get('thresh_restricted', 0.75),
                'priority_ids': self.cfg.tier_data.get('priority_ids', []),
                'restricted_ids': self.cfg.tier_data.get('restricted_ids', [])
            }

            res = gen_cnn_lib.generate_cnn_lib(
                meta_path=self.cfg.meta_path,
                model_path=self.cfg.model_path,
                out_dir=self.cfg.outdir,
                std_base_a=self.cfg.std_base_a,
                std_hold_a=self.cfg.std_hold_a,
                tflite_path=tflite_path,
                log_fn=self._log,
                post_cfg=post_cfg
            )
            
            if res:
                self._log("OK: Generated CNN library (cnn_lib)")
                self.finished_ok.emit({"out_dir": self.cfg.outdir})
            else:
                self.finished_err.emit("Generation failed (check log)")
                
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.finished_err.emit(str(e))


class AutoBuildWorker(QObject):
    log_line = Signal(str)
    finished_ok = Signal(dict)
    finished_err = Signal(str)

    def __init__(self, cfg: AutoBuildCfg, stop_event: threading.Event):
        super().__init__()
        self.cfg = cfg
        self.stop_event = stop_event

    def _log(self, s: str):
        self.log_line.emit(_tag_line("AUTOBUILD", s))

    def run(self):
        try:
            import subprocess
            import shutil
            import os
            from pathlib import Path

            self._log("--- Auto Build started ---")
            output_dir = Path(self.cfg.last_gencode_output_dir)
            is_cnn = (output_dir / "cnn_features_lib.h").exists()

            if is_cnn:
                self._log("[AUTOBUILD] CNN Model detected. Skipping MLP library build steps...")
                # For CNN, we go straight to sync and firmware build
            else:
                self._log("[AUTOBUILD] MLP Model detected. Starting 5-step library build...")
                # Step 1: Generate remaining library files for mlp_detect
                self._log("Step 1: Generating mlp_detect library files...")
                try:
                    import gen_remaining_libs as gen_rem
                    gen_rem.main([str(self.cfg.last_gencode_output_dir)])
                except Exception as e:
                    raise RuntimeError(f"gen_remaining_libs failed: {e}")
                self._log("[OK] Generated mlp_detect support files")

                # Step 2: Copy files to mlp_detect/src
                self._log("Step 2: Copying files to mlp_detect/src...")
                detect_src = Path(self.cfg.detect_proj_dir) / "src"
                files_detect = [
                    "dynamic_model.h", "mlp_model.h", "mlp_features_lib.h", "mlp_features_lib.c",
                    "dynamic_feature.h", "dynamic_feature.c", "hal_warmstart.c", "mlp_detect.h", "mlp_detect.c"
                ]
                detect_src.mkdir(parents=True, exist_ok=True)
                for f in files_detect:
                    src_f = output_dir / f
                    if src_f.exists():
                        shutil.copy2(src_f, detect_src / f)
                        self._log(f"  Copied: {f}")
                self._log("[OK] Copied files to mlp_detect/src")

                # Step 3: Build libmlp_detect.a
                self._log("Step 3: Building libmlp_detect.a...")
                build_bat = Path(self.cfg.build_tool_dir) / "build_static.bat"
                if not self._run_build_process([str(build_bat), self.cfg.detect_proj_dir, "Debug", "clean", "libmlp_detect.a"]):
                    return 

                # Step 4: Generate feature library files
                self._log("Step 4: Generating mlp_feature library files...")
                try:
                    import gen_feature_libs as gen_feat
                    gen_feat.main([str(Path(self.cfg.feature_proj_dir) / "src")])
                except Exception as e:
                    raise RuntimeError(f"gen_feature_libs failed: {e}")
                self._log("[OK] Generated and moved files to mlp_feature/src")

                # Step 5: Build libmlp_feature.a
                self._log("Step 5: Building libmlp_feature.a...")
                if not self._run_build_process([str(build_bat), self.cfg.feature_proj_dir, "Debug", "clean", "libmlp_feature.a"]):
                    return

                # Step 6: Copy libraries
                self._log("Step 6: Copying libraries to rebuild/lib...")
                rebuild_lib = Path(self.cfg.rebuild_proj_dir) / "lib"
                rebuild_lib.mkdir(parents=True, exist_ok=True)
                shutil.copy2(Path(self.cfg.detect_proj_dir) / "Debug" / "libmlp_detect.a", rebuild_lib / "libmlp_detect.a")
                shutil.copy2(Path(self.cfg.feature_proj_dir) / "Debug" / "libmlp_feature.a", rebuild_lib / "libmlp_feature.a")
                self._log("[OK] Libraries copied")

            # Step 7: Sync Headers and Sources to Main Project
            self._log("Step 7: Synchronizing files to main project...")
            rebuild_src = Path(self.cfg.rebuild_proj_dir) / "src"
            rebuild_src.mkdir(parents=True, exist_ok=True)
            
            if is_cnn:
                files_to_sync = [
                    "cnn_features_lib.h", "cnn_features_lib.c",
                    "cnn_detect.h", "cnn_detect.c",
                    "cnn_model_data.h", "cnn_model_data.c"
                ]
            else:
                files_to_sync = ["dynamic_model.h", "mlp_model.h", "mlp_features_lib.h", "mlp_detect.h", "dynamic_feature.h"]
            
            for f in files_to_sync:
                src_f = output_dir / f
                if src_f.exists():
                    shutil.copy2(src_f, rebuild_src / f)
                    self._log(f"  Synced: {f}")
            self._log("[OK] Files synchronized to main project")


            # Step 8: Patch paths in makefiles to match current environment if needed
            self._log("Step 8.1: Patching hardcoded paths in makefiles...")
            try:
                self._patch_makefile_paths(Path(self.cfg.rebuild_proj_dir) / "Debug")
            except Exception as e:
                self._log(f"  [WARN] Path patching failed: {e}")

            # Step 8.2: Build glove_mlp_rebuild (Firmware)
            self._log("Step 8.2: Building glove_mlp_rebuild.srec...")
            firmware_bat = Path(self.cfg.build_tool_dir) / "build_glove_debug.bat"
            if not firmware_bat.exists():
                raise RuntimeError(f"Firmware build script not found: {firmware_bat}")

            if not self._run_build_process([str(firmware_bat), self.cfg.rebuild_proj_dir, "Debug", "clean", "glove_mlp_rebuild"]):
                return

            # Step 9: Secure Cleanup
            if self.cfg.auto_cleanup:
                self._log("Step 9: Cleaning up intermediate artifacts (Auto Cleanup ON)...")
                self._perform_cleanup()
                cleaned = True
            else:
                self._log("Step 9: Skipped Cleanup (Engineer Mode - Keep Files)")
                cleaned = False

            self._log("[OK] All build steps completed successfully!")
            self.finished_ok.emit({
                "completed": True, 
                "srec_path": str(Path(self.cfg.rebuild_proj_dir) / "Debug" / "glove_mlp_rebuild.srec"),
                "cleaned": cleaned
            })

        except Exception as e:
            self._log(f"[ERROR] Auto Build error: {str(e)}")
            self.finished_err.emit(str(e))

    def _patch_makefile_paths(self, debug_dir: Path):
        """
        Scan all .mk, makefile, and .bat in Debug/BuildTool directory and replace 
        hardcoded absolute paths with current project path.
        Also replaces 'timeout' with 'ping' in .bat files to avoid redirection errors.
        """
        import os
        import re
        if not debug_dir.exists():
            return
            
        # Determine the current project root (the directory containing Debug, e.g., glove_mlp_rebuild/)
        # Or in a flat structure, just the parent of the Debug folder.
        current_proj_root = debug_dir.parent.absolute()
        current_root_str_forward = str(current_proj_root).replace("\\", "/")
        
        # Parent of project root - the overall station root containing sibling projects
        station_root = current_proj_root.parent.absolute()
        station_root_str = str(station_root).replace("\\", "/")
        
        # Keywords of sibling projects we want to redirect
        siblings = ["glove_mlp_rebuild", "mlp_detect", "mlp_feature", "buildtool"]
        
        count = 0
        
        # Scan Debug dir (for makefiles) and also buildtool dir (for batch scripts)
        search_dirs = [debug_dir]
        buildtool_dir = station_root / "buildtool"
        if buildtool_dir.exists():
            search_dirs.append(buildtool_dir)

        for sdir in search_dirs:
            for root, dirs, files in os.walk(sdir):
                for file in files:
                    # Patch makefiles and batch scripts
                    ext = file.lower()
                    if ext.endswith(".mk") or file == "makefile" or ext.endswith(".in") or \
                       ext == "compile_commands.json" or ext.endswith(".bat"):
                        
                        fpath = Path(root) / file
                        try:
                            content = fpath.read_text(encoding="utf-8", errors="replace")
                            new_content = content
                            modified = False
                            
                            # A. Aggressive Absolute Path Redirection
                            # Matches potential absolute paths like C:/... or D:\...
                            path_pattern = rf'[A-Za-z]:[\\/][^"\'\s;]*'
                            
                            def _match_replace(m):
                                nonlocal modified
                                original_path = m.group(0)
                                # Normalize slashes for internal logic
                                normalized = original_path.replace("\\", "/")
                                lower_path = normalized.lower()
                                
                                # Check if this path points to any of our known projects
                                for sib in siblings:
                                    sib_l = sib.lower()
                                    target_marker = f"/{sib_l}"
                                    
                                    if target_marker in lower_path:
                                        try:
                                            # Find the index of the start of the project name
                                            start_idx = lower_path.find(target_marker) + 1
                                            rel_path = normalized[start_idx:]
                                            
                                            # --- HEALING LOGIC ---
                                            # If the path looks like ".../mlp_detect.a" (broken by previous regex)
                                            # we heal it to ".../mlp_detect/Debug/libmlp_detect.a"
                                            if rel_path.lower() == "mlp_detect.a":
                                                rel_path = "mlp_detect/Debug/libmlp_detect.a"
                                            elif rel_path.lower() == "mlp_feature.a":
                                                rel_path = "mlp_feature/Debug/libmlp_feature.a"
                                            # ----------------------

                                            new_path = station_root_str + "/" + rel_path
                                            
                                            if normalized != new_path:
                                                modified = True
                                                return new_path
                                        except:
                                            pass
                                return original_path

                            new_content = re.sub(path_pattern, _match_replace, new_content)

                            # B. Specific patch for .bat files (fix timeout error)
                            if ext.endswith(".bat"):
                                if "timeout /t" in new_content or "timeout /T" in new_content:
                                    # replace timeout /t 1 with ping delay
                                    new_content = re.sub(r'timeout\s+/[tT]\s+\d+\s+/nobreak\s+>nul', 'ping -n 2 127.0.0.1 >nul', new_content)
                                    new_content = re.sub(r'timeout\s+/[tT]\s+\d+\s+>nul', 'ping -n 2 127.0.0.1 >nul', new_content)
                                    modified = True

                            # C. Generic Slash Normalization (always good for Clang @files)
                            # This ensures ANY absolute path found uses forward slashes
                            if ext.endswith(".mk") or file == "makefile" or ext.endswith(".in"):
                                lines = new_content.splitlines()
                                fixed_lines = []
                                for line in lines:
                                    # Identify lines containing absolute paths
                                    if ":" in line and ("/" in line or "\\" in line):
                                        # Standardize to forward slashes
                                        # Preserve trailing backslash for line continuation
                                        endswith_backslash = line.rstrip().endswith("\\")
                                        temp_line = line.replace("\\", "/")
                                        if endswith_backslash and not temp_line.rstrip().endswith("\\"):
                                            temp_line = temp_line.rstrip() + " \\"
                                        
                                        if temp_line != line:
                                            modified = True
                                        fixed_lines.append(temp_line)
                                    else:
                                        fixed_lines.append(line)
                                new_content = "\n".join(fixed_lines)

                            if modified:
                                fpath.write_text(new_content, encoding="utf-8")
                                count += 1
                        except Exception as e:
                            self._log(f"  [WARN] Failed to patch {file}: {e}")
        
        if count > 0:
            self._log(f"  [OK] Universal Patch: Redirected {count} files to use current root: {station_root_str}")
        else:
            self._log("  [INFO] No paths needed redirection.")

    def _perform_cleanup(self):
        """Permanently delete intermediate source files and directories"""
        import shutil
        from pathlib import Path
        
        base_dir = Path(__file__).parent
        
        # 1. Clear mlp_detect/src (Keep folder, delete files)
        detect_src = Path(self.cfg.detect_proj_dir) / "src"
        if detect_src.exists():
            for f in detect_src.iterdir():
                if f.is_file(): f.unlink()
            self._log("  Cleared: mlp_detect/src")

        # 2. Clear mlp_feature/src (Keep folder, delete files)
        feat_src = Path(self.cfg.feature_proj_dir) / "src"
        if feat_src.exists():
            for f in feat_src.iterdir():
                if f.is_file(): f.unlink()
            self._log("  Cleared: mlp_feature/src")

        # 3. Delete Gen Code output directory (e.g., testarea)
        if self.cfg.last_gencode_output_dir:
            out_dir = Path(self.cfg.last_gencode_output_dir)
            if out_dir.exists():
                shutil.rmtree(out_dir)
                self._log(f"  Deleted: {out_dir.name} (Source folder)")

        # 4. Delete testarea_feature if exists
        feat_testarea = base_dir / "testarea_feature"
        if feat_testarea.exists():
            shutil.rmtree(feat_testarea)
            self._log("  Deleted: testarea_feature")
            
        self._log("[OK] Secure Cleanup finished (No files in Recycle Bin)")

    def _run_build_process(self, cmd: List[str]) -> bool:
        """Helper to run a build process and stream logs"""
        import subprocess
        self._log(f"  Running: {' '.join(cmd)}")
        
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
            errors='replace',
            bufsize=1,
            universal_newlines=True,
            cwd=str(self.cfg.build_tool_dir)
        )

        while True:
            if self.stop_event.is_set():
                process.terminate()
                self._log("Build stopped by user")
                return False
            
            output = process.stdout.readline()
            if output == '' and process.poll() is not None:
                break
            if output:
                line = output.strip()
                if line:
                    self.log_line.emit(_tag_line("BUILD", line))

        rc = process.poll()
        if rc != 0:
            raise RuntimeError(f"Build failed with return code: {rc}")
        return True



class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Gesture Trainer + Detector (UI v6 + Build/Flash)")
        self.resize(1280, 850)

        self.busy_mode: Optional[str] = None
        self.is_engineer_mode = False
        self.tab_click_count = 0
        self.last_tab_click_time = 0
        
        # Background click for Build tab unlock
        self.bg_click_count = 0
        self.last_bg_click_time = 0
        
        # Background stop events
        self.stop_event_train = threading.Event()
        self.stop_event_detect = threading.Event()
        self.stop_event_flash = threading.Event()
        self.stop_event_autobuild = threading.Event()

        # Apply modern commercial dark theme
        self._apply_dark_theme()

    def _apply_dark_theme(self):
        """
        Apply a modern, commercial-grade dark theme using QSS.
        Does not change layout or functionality, only aesthetics.
        """
        # Base64 SVG Icons for SpinBox Arrows (White, clean)
        # Up Arrow (Chevron Up)
        icon_up = "url(data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIxNiIgaGVpZ2h0PSIxNiIgdmlld0JveD0iMCAwIDI0IDI0IiBmaWxsPSJub25lIiBzdHJva2U9IndoaXRlIiBzdHJva2Utd2lkdGg9IjIiIHN0cm9rZS1saW5lY2FwPSJyb3VuZCIgc3Ryb2tlLWxpbmVqb2luPSJyb3VuZCI+PHBvbHlsaW5lIHBvaW50cz0iMTggMTUgMTIgOSA2IDE1Ij48L3BvbHlsaW5lPjwvc3ZnPg==)"
        # Down Arrow (Chevron Down)
        icon_down = "url(data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIxNiIgaGVpZ2h0PSIxNiIgdmlld0JveD0iMCAwIDI0IDI0IiBmaWxsPSJub25lIiBzdHJva2U9IndoaXRlIiBzdHJva2Utd2lkdGg9IjIiIHN0cm9rZS1saW5lY2FwPSJyb3VuZCIgc3Ryb2tlLWxpbmVqb2luPSJyb3VuZCI+PHBvbHlsaW5lIHBvaW50cz0iNiA5IDEyIDE1IDE4IDkiPjwvcG9seWxpbmU+PC9zdmc+)"

        dark_qss = f"""
        /* =======================================================
           Global Palette & Typography
           Background: #1e1e1e (Deep Dark)
           Surface:    #252526 (Lighter Dark for panels)
           Primary:    #007acc (VS Code Blue)
           Text:       #cccccc (Light Gray)
           Border:     #3e3e42
           ======================================================= */
        
        QWidget {{
            background-color: #1e1e1e;
            color: #d4d4d4;
            font-family: "Segoe UI", "Microsoft JhengHei", sans-serif;
            font-size: 10pt;
        }}

        /* GroupBox: Card-like look with subtle borders */
        QGroupBox {{
            border: 1px solid #3e3e42;
            border-radius: 6px;
            margin-top: 22px; /* Leave space for title */
            background-color: #252526; 
            font-weight: bold;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            subcontrol-position: top left;
            padding: 0 5px;
            left: 10px;
            color: #007acc; /* Accent color for titles */
        }}

        /* Inputs: Modern flat style with focus highlight */
        QLineEdit, QComboBox {{
            background-color: #333337;
            border: 1px solid #3e3e42;
            border-radius: 4px;
            padding: 4px;
            color: white;
            selection-background-color: #264f78;
        }}
        QLineEdit:focus, QComboBox:focus {{
            border: 1px solid #007acc;
        }}

        /* --- SPINBOX FIX --- */
        QAbstractSpinBox {{
            background-color: #333337;
            border: 1px solid #3e3e42;
            border-radius: 4px;
            padding-right: 25px; /* Room for wider buttons */
            color: white;
            selection-background-color: #264f78;
            min-height: 24px;
        }}
        QAbstractSpinBox:focus {{
            border: 1px solid #007acc;
        }}
        
        QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {{
            subcontrol-origin: border;
            width: 24px; /* Wider click target */
            background-color: #3e3e42;
            border-left: 1px solid #4e4e52;
        }}
        
        QAbstractSpinBox::up-button {{
            subcontrol-position: top right;
            border-top-right-radius: 4px;
            border-bottom: 1px solid #4e4e52; 
        }}
        
        QAbstractSpinBox::down-button {{
            subcontrol-position: bottom right;
            border-bottom-right-radius: 4px;
        }}
        
        QAbstractSpinBox::up-button:hover, QAbstractSpinBox::down-button:hover {{
            background-color: #55555a;
        }}
        
        QAbstractSpinBox::up-button:pressed, QAbstractSpinBox::down-button:pressed {{
            background-color: #007acc;
        }}

        /* Arrows from SVG */
        QAbstractSpinBox::up-arrow {{
            image: {icon_up};
            width: 12px;
            height: 12px;
        }}
        QAbstractSpinBox::down-arrow {{
            image: {icon_down};
            width: 12px;
            height: 12px;
        }}

        /* Buttons: Prominent, rounded, interactive */
        QPushButton {{
            background-color: #0e639c;
            color: white;
            border: none;
            border-radius: 4px;
            padding: 6px 12px;
            font-weight: bold;
        }}
        QPushButton:hover {{
            background-color: #1177bb;
        }}
        QPushButton:pressed {{
            background-color: #094771;
        }}
        QPushButton:disabled {{
            background-color: #333333;
            color: #888888;
        }}

        /* Tabs: Modern flat tabs */
        QTabWidget::pane {{
            border: 1px solid #3e3e42;
            background-color: #1e1e1e;
        }}
        QTabBar::tab {{
            background-color: #252526;
            color: #d4d4d4;
            padding: 8px 16px;
            border-top-left-radius: 4px;
            border-top-right-radius: 4px;
            margin-right: 1px;
        }}
        QTabBar::tab:selected {{
            background-color: #1e1e1e; /* Connects with pane */
            color: #007acc;
            border-bottom: 2px solid #007acc;
        }}
        QTabBar::tab:hover:!selected {{
            background-color: #2d2d30;
        }}

        /* ScrollBar: Minimalist */
        QScrollBar:vertical {{
            border: none;
            background-color: #1e1e1e;
            width: 12px;
            margin: 0px;
        }}
        QScrollBar::handle:vertical {{
            background-color: #424242;
            min-height: 20px;
            border-radius: 6px;
        }}
        QScrollBar::handle:vertical:hover {{
            background-color: #686868;
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0px;
        }}

        /* Table: Clean grid */
        QTableWidget {{
            background-color: #252526;
            gridline-color: #3e3e42;
            border: 1px solid #3e3e42;
            selection-background-color: #264f78;
        }}
        QHeaderView::section {{
            background-color: #333337;
            padding: 4px;
            border: 1px solid #3e3e42;
            font-weight: bold;
        }}
        
        /* Table items text color fix */
        QTableWidget::item {{
            color: #d4d4d4;
        }}

        /* Terminal Area: Code-like appearance */
        QTextEdit {{
            background-color: #101010; /* Very dark for terminal */
            color: #4EC9B0; /* Code green/blueish */
            border: 1px solid #3e3e42;
            border-radius: 4px;
        }}
        
        /* Checkbox */
        QCheckBox::indicator {{
            width: 16px;
            height: 16px;
            background-color: #333337;
            border: 1px solid #3e3e42;
            border-radius: 3px;
        }}
        QCheckBox::indicator:checked {{
            background-color: #007acc;
            image: none; /* Can add tick icon here if needed, color change usually enough */
        }}
        """
        self.setStyleSheet(dark_qss)


        self.thread_train: Optional[QThread] = None
        self.worker_train: Optional[TrainWorker] = None

        self.thread_detect: Optional[QThread] = None
        self.worker_detect: Optional[DetectWorker] = None

        self.thread_gen_cnn: Optional[QThread] = None
        self.worker_gen_cnn: Optional[GenCnnCodeWorker] = None

        self.thread_build: Optional[QThread] = None
        self.worker_build: Optional[BuildWorker] = None

        self.thread_flash: Optional[QThread] = None
        self.worker_flash: Optional[FlashWorker] = None

        self.thread_autobuild: Optional[QThread] = None
        self.worker_autobuild: Optional[AutoBuildWorker] = None

        

        # Dynamic gestures JSON path (for detect)
        self.dynamic_json_path = "dynamic_gestures.json"
        
        # Auto build related
        self.last_gencode_output_dir = None

        # =========================
        # Shared terminal (right)
        # =========================
        self.term = QTextEdit()
        self.term.setReadOnly(True)
        self.term.setLineWrapMode(QTextEdit.NoWrap)
        self.term.setFontFamily("Consolas")

        self.btn_term_clear = QPushButton("Clear")
        self.btn_term_copy = QPushButton("Copy All")

        # =========================
        # Tabs (left)
        # =========================
        self.tabs = QTabWidget()
        self.tab_train = QWidget()
        self.tab_detect = QWidget()
        self.tab_gencode_cnn = QWidget()
        self.tab_build = QWidget()
        self.tab_autobuild = QWidget()
        self.tabs.addTab(self.tab_train, "Train")
        self.tabs.addTab(self.tab_detect, "Detect")
        self.tabs.addTab(self.tab_gencode_cnn, "Gen Code (CNN)")
        # self.tabs.addTab(self.tab_build, "Build") # Hidden by default (15-click unlock)
        self.tabs.addTab(self.tab_autobuild, "Auto Build")
        
        # Detect clicks on "Auto Build" tab for Engineer Mode
        self.tabs.tabBar().installEventFilter(self)

        # =========================
        # Main Layout: Left tabs (scroll) + Right terminal
        # =========================
        root = QWidget()
        self.setCentralWidget(root)
        main = QHBoxLayout(root)
        main.setContentsMargins(6, 6, 6, 6)

        left_container = QWidget()
        left_layout = QVBoxLayout(left_container)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(self.tabs)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(left_container)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        term_toolbar = QHBoxLayout()
        term_toolbar.addWidget(QLabel("Terminal"))
        term_toolbar.addStretch(1)
        term_toolbar.addWidget(self.btn_term_clear)
        term_toolbar.addWidget(self.btn_term_copy)

        right_layout.addLayout(term_toolbar)
        right_layout.addWidget(self.term, 1)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(scroll)
        splitter.addWidget(right_widget)
        splitter.setChildrenCollapsible(False)

        # ✅ 讓左邊拿到足夠寬度
        splitter.setStretchFactor(0, 1)   # left
        splitter.setStretchFactor(1, 0)   # right (terminal)

        # ✅ 給左邊一個足夠大的最小寬度，確保 6 CH 介面直接展開
        scroll.setMinimumWidth(1150)
        right_widget.setMinimumWidth(400)

        # ✅ 設定視窗初始大小，並分配 splitter 比例
        self.resize(1650, 950)
        splitter.setSizes([1200, 450])


        main.addWidget(splitter)

        self.btn_term_clear.clicked.connect(self.on_term_clear)
        self.btn_term_copy.clicked.connect(self.on_term_copy)

        # =========================
        # Build tabs  (✅ Train/Detect 保留你原本 UI)
        # =========================
        self._build_train_tab()
        self._build_detect_tab()
        self._build_gencode_cnn_tab()
        self._build_build_tab()
        self._build_autobuild_tab()

        # Initial populate ports (After all tabs built)
        self.on_flash_refresh_ports()

        self._set_busy(None)

        # Auto-load default dynamic_gestures.json if exists
        if self.tbl_dynamic.rowCount() == 0:
            self._load_default_dynamic_gestures()

    # -------------------------
    # Terminal helpers
    # -------------------------
    def append_log(self, s: str):
        self.term.append(s)
        sb = self.term.verticalScrollBar()
        sb.setValue(sb.maximum())
        fp = getattr(self, "_train_log_fp", None)
        if fp is not None:
            try:
                fp.write(s + "\n")
                fp.flush()
            except Exception:
                pass

    def _open_train_log_file(self, out_dir: Path):
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d-%H%M%S")
            log_path = out_dir / f"train_log_{ts}.txt"
            self._train_log_fp = open(log_path, "a", encoding="utf-8")
            self._train_log_path = str(log_path)
            self.append_log(_tag_line("TRAIN", f"[UI] Train log file: {log_path}"))
        except Exception as e:
            self._train_log_fp = None
            self._train_log_path = ""
            self.append_log(_tag_line("TRAIN", f"[WARN] Failed to open train log file: {e}"))

    def _close_train_log_file(self):
        fp = getattr(self, "_train_log_fp", None)
        if fp is not None:
            try:
                fp.flush()
                fp.close()
            except Exception:
                pass
        self._train_log_fp = None

    # backwards compatible name (有些舊段落用 append_term)
    def append_term(self, s: str):
        self.append_log(s)

    def on_term_clear(self):
        self.term.clear()

    def on_term_copy(self):
        QApplication.clipboard().setText(self.term.toPlainText())
        QMessageBox.information(self, "Copied", "Terminal log copied.")

    # -------------------------
    # Busy lock
    # -------------------------
    # -------------------------
    # Event Filter (for Engineer Mode)
    # -------------------------
    def eventFilter(self, obj, event):
        if obj == self.tabs.tabBar() and event.type() == QEvent.MouseButtonPress:
            index = self.tabs.tabBar().tabAt(event.position().toPoint())
            if index >= 0 and self.tabs.widget(index) == self.tab_autobuild:
                now = time.time()
                if now - self.last_tab_click_time < 0.5: # 500ms threshold
                    self.tab_click_count += 1
                else:
                    self.tab_click_count = 1
                self.last_tab_click_time = now
                
                if self.tab_click_count >= 5:
                    self._toggle_engineer_mode()
                    self.tab_click_count = 0
        return super().eventFilter(obj, event)

    def _toggle_engineer_mode(self):
        self.is_engineer_mode = not self.is_engineer_mode
        state = "ENABLED" if self.is_engineer_mode else "DISABLED"
        self.append_log(_tag_line("SYSTEM", f"Engineer Mode {state}"))
        
        # Update visibility
        self.btn_secure_clean.setVisible(self.is_engineer_mode)
        self.cb_auto_cleanup.setVisible(self.is_engineer_mode)
        
        if self.is_engineer_mode:
            self.cb_auto_cleanup.setChecked(False) # 進入工程師模式預設不自動清理
            QMessageBox.information(self, "Engineer Mode", "Engineer Mode Activated!\n- 'Secure Clean' button unlocked.\n- Auto Cleanup turned OFF by default.")
        else:
            # Force default behavior
            self.cb_auto_cleanup.setChecked(True)
            QMessageBox.information(self, "Engineer Mode", "Engineer Mode Deactivated.")

    def mousePressEvent(self, event):
        # Detect background clicks for hidden Build tab
        now = time.time()
        if now - self.last_bg_click_time < 0.5:
            self.bg_click_count += 1
        else:
            self.bg_click_count = 1
        self.last_bg_click_time = now
        
        if self.bg_click_count >= 15:
            self._toggle_build_tab()
            self.bg_click_count = 0
        super().mousePressEvent(event)

    def _toggle_build_tab(self):
        # Check if already added
        indices = [i for i in range(self.tabs.count()) if self.tabs.widget(i) == self.tab_build]
        if indices:
            self.tabs.removeTab(indices[0])
            self.append_log(_tag_line("SYSTEM", "Build tab HIDDEN"))
        else:
            # Insert at index 3 (standard position)
            # If current tabs are [0:Train, 1:Detect, 2:GenCode, 3:AutoBuild]
            # insertTab(3, ...) makes it [0:Train, 1:Detect, 2:GenCode, 3:Build, 4:AutoBuild]
            self.tabs.insertTab(3, self.tab_build, "Build")
            self.append_log(_tag_line("SYSTEM", "Build tab REVEALED"))
            QMessageBox.information(self, "Secret Feature", "Build tab has been unlocked!")

    def _set_busy(self, mode: Optional[str]):
        self.busy_mode = mode
        busy = mode is not None

        # 允許畫面操作，但禁止切 tab
        self.tabs.tabBar().setEnabled(not busy)

        # 互斥
        if mode == "train":
            self.btn_detect_start.setEnabled(False)
        elif mode == "detect":
            self.btn_train.setEnabled(False)
            self.btn_scan.setEnabled(False)
        elif mode == "gen_cnn":
            self.btn_train.setEnabled(False)
            self.btn_scan.setEnabled(False)
            self.btn_detect_start.setEnabled(False)
            self.btn_gen_cnn_all.setEnabled(False)
            self.btn_autobuild_flash.setEnabled(False)
        elif mode == "build":
            self.btn_train.setEnabled(False)
            self.btn_scan.setEnabled(False)
            self.btn_detect_start.setEnabled(False)
            self.btn_gen_cnn_all.setEnabled(False)
            self.btn_build.setEnabled(False)
            self.btn_flash.setEnabled(False)
            self.btn_autobuild_flash.setEnabled(False)
        elif mode == "flash":
            self.btn_train.setEnabled(False)
            self.btn_scan.setEnabled(False)
            self.btn_detect_start.setEnabled(False)
            self.btn_gen_cnn_all.setEnabled(False)
            self.btn_build.setEnabled(False)
            self.btn_flash.setEnabled(False)
            self.btn_startbuild.setEnabled(False)
            self.btn_autobuild_flash.setEnabled(False)
            self.btn_autobuild_flash.setText("Flashing...")
        elif mode == "autobuild":
            self.btn_train.setEnabled(False)
            self.btn_scan.setEnabled(False)
            self.btn_detect_start.setEnabled(False)
            self.btn_gen_cnn_all.setEnabled(False)
            self.btn_build.setEnabled(False)
            self.btn_flash.setEnabled(False)
            self.btn_startbuild.setEnabled(False)
            self.btn_startbuild.setText("Building...")
            self.btn_autobuild_flash.setEnabled(False)
        else:
            # Idle
            self.btn_train.setEnabled(True)
            self.btn_scan.setEnabled(True)
            self.btn_detect_start.setEnabled(True)
            self.btn_gen_cnn_all.setEnabled(True)
            self.btn_build.setEnabled(True)
            self.btn_flash.setEnabled(True)
            self.btn_flash.setText("FLASH")
            self.btn_startbuild.setEnabled(True)
            self.btn_startbuild.setText("StartBuild")
            self.btn_autobuild_flash.setEnabled(True)
            self.btn_autobuild_flash.setText("FLASH")
            self.btn_autobuild_flash_refresh.setEnabled(True)


        if not busy:
            # Re-apply visibility based on mode
            self.btn_secure_clean.setVisible(self.is_engineer_mode)
            self.cb_auto_cleanup.setVisible(self.is_engineer_mode)
            if self.thread_train is None:
                self.btn_train.setEnabled(True)
                self.btn_scan.setEnabled(True)
            if self.thread_detect is None:
                self.btn_detect_start.setEnabled(True)
            if self.thread_gen_cnn is None:
                self.btn_gen_cnn_all.setEnabled(True)
            if self.thread_build is None:
                self.btn_build.setEnabled(True)
            if self.thread_flash is None:
                self.btn_flash.setEnabled(True)
            if self.thread_autobuild is None:
                self.btn_startbuild.setEnabled(True)


    # =========================
    # Train Tab  (⚠️ 這整段保留你原本的，不改 UI/參數)
    # =========================
    def _build_train_tab(self):
        # === 原本 ui_v4.py 的 Train UI 全部  ===
        # （以下內容就是你原本那份 ui_v4.py 的 Train 介面）
        layout = QVBoxLayout(self.tab_train)
        layout.setSpacing(8)

        # Data
        self.edit_data_dir = QLineEdit()
        self.btn_browse_data = QPushButton("Browse...")
        self.btn_scan = QPushButton("Scan")

        self.chk_scan_show_unknown_summary = QCheckBox("Scan: show unknown prefix summary (recommended)")
        self.chk_scan_show_unknown_summary.setChecked(True)

        self.chk_scan_show_invalid_detail = QCheckBox("Scan: show invalid file details")
        self.chk_scan_show_invalid_detail.setChecked(False)

        self.spin_scan_invalid_n = NoWheelSpinBox()
        self.spin_scan_invalid_n.setRange(0, 500)
        self.spin_scan_invalid_n.setValue(40)

        g_data = QGroupBox("Data")
        f_data = QFormLayout(g_data)

        w_data = QWidget()
        h_data = QHBoxLayout(w_data)
        h_data.setContentsMargins(0, 0, 0, 0)
        h_data.addWidget(self.edit_data_dir, 1)
        h_data.addWidget(self.btn_browse_data)
        f_data.addRow("data_dir:", w_data)
        f_data.addRow("", self.btn_scan)

        f_data.addRow("", self.chk_scan_show_unknown_summary)

        w_invalid = QWidget()
        h_invalid = QHBoxLayout(w_invalid)
        h_invalid.setContentsMargins(0, 0, 0, 0)
        h_invalid.addWidget(self.chk_scan_show_invalid_detail)
        h_invalid.addWidget(QLabel("max N:"))
        h_invalid.addWidget(self.spin_scan_invalid_n)
        h_invalid.addStretch(1)
        f_data.addRow("", w_invalid)

        layout.addWidget(g_data)

        # Label Definitions
        g_labels = QGroupBox("Label Definitions")
        v_labels = QVBoxLayout(g_labels)

        # hint
        v_labels.addWidget(QLabel("CSV filename must be: prefix-xxx.csv  (prefix must exist in table)"))

        row_btns = QWidget()
        hbtn = QHBoxLayout(row_btns)
        hbtn.setContentsMargins(0, 0, 0, 0)

        self.btn_label_add = QPushButton("Add")
        self.btn_label_remove = QPushButton("Remove selected")
        self.chk_auto_id = QCheckBox("Auto-ID (0..N-1)")
        self.chk_auto_id.setChecked(True)

        hbtn.addWidget(self.btn_label_add)
        hbtn.addWidget(self.btn_label_remove)
        hbtn.addStretch(1)
        hbtn.addWidget(self.chk_auto_id)
        v_labels.addWidget(row_btns)

        row_json = QWidget()
        hjson = QHBoxLayout(row_json)
        hjson.setContentsMargins(0, 0, 0, 0)

        self.btn_labels_load = QPushButton("Load labels JSON...")
        self.btn_labels_save = QPushButton("Save labels JSON...")
        hjson.addWidget(self.btn_labels_load)
        hjson.addStretch(1)
        hjson.addWidget(self.btn_labels_save)
        v_labels.addWidget(row_json)

        self.tbl_labels = QTableWidget(0, 3)
        self.tbl_labels.setHorizontalHeaderLabels(["prefix", "name", "id"])
        self.tbl_labels.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        v_labels.addWidget(self.tbl_labels, 1)

        g_labels.setMinimumHeight(500)   # 你想要多高自己調

        layout.addWidget(g_labels)

        # Dynamic Gestures
        self.g_dynamic = QGroupBox("Dynamic Gestures")
        v_dynamic = QVBoxLayout(self.g_dynamic)

        # Buttons
        row_btns = QWidget()
        hbtn = QHBoxLayout(row_btns); hbtn.setContentsMargins(0, 0, 0, 0)
        self.btn_dynamic_add = QPushButton("Add")
        self.btn_dynamic_remove = QPushButton("Remove selected")
        hbtn.addWidget(self.btn_dynamic_add)
        hbtn.addWidget(self.btn_dynamic_remove)
        hbtn.addStretch(1)
        v_dynamic.addWidget(row_btns)

        # JSON load/save
        row_json = QWidget()
        hjson = QHBoxLayout(row_json); hjson.setContentsMargins(0, 0, 0, 0)
        self.btn_dynamic_load = QPushButton("Load dynamic JSON...")
        self.btn_dynamic_save = QPushButton("Save dynamic JSON...")
        hjson.addWidget(self.btn_dynamic_load)
        hjson.addStretch(1)
        hjson.addWidget(self.btn_dynamic_save)
        v_dynamic.addWidget(row_json)

        # Table: name | sequence | max_gap | time_window
        self.tbl_dynamic = QTableWidget(0, 4)
        self.tbl_dynamic.setHorizontalHeaderLabels(["name", "sequence", "max_gap", "time_window"])
        self.tbl_dynamic.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        v_dynamic.addWidget(self.tbl_dynamic, 1)

        self.g_dynamic.setMinimumHeight(500)
        layout.addWidget(self.g_dynamic)

        # Features (Simplified for CNN)
        self.g_features = QGroupBox("Features")
        self.f_features = QFormLayout(self.g_features)

        # channels
        self.chk_ch = []
        w_ch = QWidget()
        hch = QHBoxLayout(w_ch)
        hch.setContentsMargins(0, 0, 0, 0)
        hch.addWidget(QLabel("channels:"))
        for i in range(6):
            cb = QCheckBox(f"CH{i+1}")
            cb.setChecked(True if i < 5 else False)
            self.chk_ch.append(cb)
            hch.addWidget(cb)
        hch.addStretch(1)
        self.f_features.addRow("", w_ch)

        self.spin_window_len = NoWheelSpinBox()
        self.spin_window_len.setRange(5, 200)
        self.spin_window_len.setValue(35)
        self.f_features.addRow("window_len (窗口長度):", self.spin_window_len)

        self.dsb_slope_factor = NoWheelDoubleSpinBox()
        self.dsb_slope_factor.setRange(1.0, 500.0)
        self.dsb_slope_factor.setValue(20.0)
        self.dsb_slope_factor.setToolTip("斜率放大倍率：放大信號微小變化（如呼氣）的關鍵係數。")
        self.f_features.addRow("slope_factor (斜率放大):", self.dsb_slope_factor)

        self.spin_window_step = NoWheelSpinBox()
        self.spin_window_step.setRange(1, 200)
        self.spin_window_step.setValue(5)
        self.f_features.addRow("window_step:", self.spin_window_step)

        layout.addWidget(self.g_features)

        # Augmentation
        self.g_aug = QGroupBox("Augmentation")
        self.f_aug = QFormLayout(self.g_aug)

        self.chk_enable_aug = QCheckBox("enable_augmentation")
        self.chk_enable_aug.setChecked(True)
        self.f_aug.addRow("", self.chk_enable_aug)

        self.spin_aug_copies = NoWheelSpinBox()
        self.spin_aug_copies.setRange(0, 200)
        self.spin_aug_copies.setValue(10)
        self.f_aug.addRow("aug_copies:", self.spin_aug_copies)

        self.dsb_delta_min = NoWheelDoubleSpinBox()
        self.dsb_delta_min.setDecimals(2)
        self.dsb_delta_min.setRange(0.0, 5.0)
        self.dsb_delta_min.setValue(0.75)
        self.dsb_delta_max = NoWheelDoubleSpinBox()
        self.dsb_delta_max.setDecimals(2)
        self.dsb_delta_max.setRange(0.0, 5.0)
        self.dsb_delta_max.setValue(1.25)

        w_dg = QWidget()
        hdg = QHBoxLayout(w_dg)
        hdg.setContentsMargins(0, 0, 0, 0)
        hdg.addWidget(QLabel("min:"))
        hdg.addWidget(self.dsb_delta_min)
        hdg.addWidget(QLabel("max:"))
        hdg.addWidget(self.dsb_delta_max)
        hdg.addStretch(1)
        self.f_aug.addRow("delta_gain:", w_dg)

        self.dsb_span_min = NoWheelDoubleSpinBox()
        self.dsb_span_min.setDecimals(2)
        self.dsb_span_min.setRange(0.0, 5.0)
        self.dsb_span_min.setValue(0.80)
        self.dsb_span_max = NoWheelDoubleSpinBox()
        self.dsb_span_max.setDecimals(2)
        self.dsb_span_max.setRange(0.0, 5.0)
        self.dsb_span_max.setValue(1.20)

        w_sg = QWidget()
        hsg = QHBoxLayout(w_sg)
        hsg.setContentsMargins(0, 0, 0, 0)
        hsg.addWidget(QLabel("min:"))
        hsg.addWidget(self.dsb_span_min)
        hsg.addWidget(QLabel("max:"))
        hsg.addWidget(self.dsb_span_max)
        hsg.addStretch(1)
        self.f_aug.addRow("span_gain:", w_sg)

        self.chk_offset_aug = QCheckBox("enable_offset_aug")
        self.chk_offset_aug.setChecked(True)
        self.dsb_sigma = NoWheelDoubleSpinBox()
        self.dsb_sigma.setDecimals(2)
        self.dsb_sigma.setRange(0.0, 999999)
        self.dsb_sigma.setValue(30.0)
        self.dsb_clip = NoWheelDoubleSpinBox()
        self.dsb_clip.setDecimals(2)
        self.dsb_clip.setRange(0.0, 999999)
        self.dsb_clip.setValue(100.0)

        w_off = QWidget()
        hoff = QHBoxLayout(w_off)
        hoff.setContentsMargins(0, 0, 0, 0)
        hoff.addWidget(self.chk_offset_aug)
        hoff.addWidget(QLabel("sigma:"))
        hoff.addWidget(self.dsb_sigma)
        hoff.addWidget(QLabel("clip:"))
        hoff.addWidget(self.dsb_clip)
        hoff.addStretch(1)
        self.f_aug.addRow("", w_off)

        self.chk_time_warp = QCheckBox("enable_time_warp")
        self.chk_time_warp.setChecked(True)
        self.dsb_tw_min = NoWheelDoubleSpinBox()
        self.dsb_tw_min.setDecimals(2)
        self.dsb_tw_min.setRange(0.1, 5.0)
        self.dsb_tw_min.setValue(0.80)
        self.dsb_tw_max = NoWheelDoubleSpinBox()
        self.dsb_tw_max.setDecimals(2)
        self.dsb_tw_max.setRange(0.1, 5.0)
        self.dsb_tw_max.setValue(1.30)

        w_tw = QWidget()
        htw = QHBoxLayout(w_tw)
        htw.setContentsMargins(0, 0, 0, 0)
        htw.addWidget(self.chk_time_warp)
        htw.addWidget(QLabel("min:"))
        htw.addWidget(self.dsb_tw_min)
        htw.addWidget(QLabel("max:"))
        htw.addWidget(self.dsb_tw_max)
        htw.addStretch(1)
        self.f_aug.addRow("", w_tw)

        layout.addWidget(self.g_aug)

        # Model
        self.g_model = QGroupBox("Model")
        self.f_model = QFormLayout(self.g_model)

        self.combo_model_backbone = QComboBox()
        self.combo_model_backbone.addItems(["cnn", "ds_tcn"])
        self.combo_model_backbone.setCurrentText("cnn")
        self.f_model.addRow("model_backbone:", self.combo_model_backbone)

        self.dsb_test_size = NoWheelDoubleSpinBox()
        self.dsb_test_size.setDecimals(2)
        self.dsb_test_size.setRange(0.0, 0.99)
        self.dsb_test_size.setValue(0.20)
        self.f_model.addRow("test_size:", self.dsb_test_size)

        self.spin_random_state = NoWheelSpinBox()
        self.spin_random_state.setRange(0, 999999)
        self.spin_random_state.setValue(42)
        self.f_model.addRow("random_state:", self.spin_random_state)

        # CNN Specific
        self.spin_cnn_epochs = NoWheelSpinBox()
        self.spin_cnn_epochs.setRange(1, 100000)
        self.spin_cnn_epochs.setValue(200)
        self.f_model.addRow("epochs (倫次):", self.spin_cnn_epochs)

        self.spin_batch_size = NoWheelSpinBox()
        self.spin_batch_size.setRange(1, 1024)
        self.spin_batch_size.setValue(32)
        self.f_model.addRow("batch_size:", self.spin_batch_size)

        self.dsb_learning_rate = NoWheelDoubleSpinBox()
        self.dsb_learning_rate.setDecimals(4)
        self.dsb_learning_rate.setRange(0.0001, 0.1)
        self.dsb_learning_rate.setValue(0.001)
        self.f_model.addRow("learning_rate:", self.dsb_learning_rate)

        # Patience params
        self.spin_early_stop_patience = NoWheelSpinBox()
        self.spin_early_stop_patience.setRange(1, 100)
        self.spin_early_stop_patience.setValue(15)
        self.f_model.addRow("EarlyStop Patience (次數):", self.spin_early_stop_patience)

        self.spin_lr_patience = NoWheelSpinBox()
        self.spin_lr_patience.setRange(1, 100)
        self.spin_lr_patience.setValue(10)
        self.f_model.addRow("ReduceLR Patience (次數):", self.spin_lr_patience)

        layout.addWidget(self.g_model)

        # Output
        self.g_out = QGroupBox("Output")
        self.f_out = QFormLayout(self.g_out)

        self.edit_out_dir = QLineEdit()
        self.btn_browse_out = QPushButton("Browse...")
        w_out = QWidget()
        hout = QHBoxLayout(w_out)
        hout.setContentsMargins(0, 0, 0, 0)
        hout.addWidget(self.edit_out_dir, 1)
        hout.addWidget(self.btn_browse_out)
        self.f_out.addRow("output_dir:", w_out)

        self.edit_out_model_path = QLineEdit("gesture_model_v5.pkl")
        self.edit_out_meta_path = QLineEdit("gesture_model_meta_v5.pkl")
        self.f_out.addRow("out_model_path:", self.edit_out_model_path)
        self.f_out.addRow("out_meta_path:", self.edit_out_meta_path)

        layout.addWidget(self.g_out)

        # Bottom buttons
        self.btn_train = QPushButton("Train")
        self.btn_stop_train = QPushButton("Stop")
        self.btn_stop_train.setEnabled(False)
        self.btn_view_report = QPushButton("View Training Report")
        self.btn_view_report.setStyleSheet("background-color: #4EC9B0; color: black;")

        w_bottom = QWidget()
        hb = QHBoxLayout(w_bottom)
        hb.setContentsMargins(0, 0, 0, 0)
        hb.addWidget(self.btn_train, 2)
        hb.addWidget(self.btn_stop_train, 1)
        hb.addWidget(self.btn_view_report, 2)
        layout.addWidget(w_bottom)

        layout.addStretch(1)

        # connections
        self.btn_browse_data.clicked.connect(lambda: self._browse_dir(self.edit_data_dir))
        self.btn_browse_out.clicked.connect(lambda: self._browse_dir(self.edit_out_dir))

        self.btn_label_add.clicked.connect(self._add_label_row)
        self.btn_label_remove.clicked.connect(self._remove_selected_label_rows)
        self.btn_labels_load.clicked.connect(self.on_load_labels_json)
        self.btn_labels_save.clicked.connect(self.on_save_labels_json)

        self.chk_auto_id.stateChanged.connect(self._maybe_auto_reassign_ids)

        self.btn_scan.clicked.connect(self.on_scan)
        self.btn_train.clicked.connect(self.on_train)
        self.btn_stop_train.clicked.connect(self.on_stop_train)
        self.btn_view_report.clicked.connect(self.on_view_report)

        # Dynamic gestures connections
        self.btn_dynamic_add.clicked.connect(self._add_dynamic_row)
        self.btn_dynamic_remove.clicked.connect(self._remove_selected_dynamic_rows)
        self.btn_dynamic_load.clicked.connect(self.on_load_dynamic_json)
        self.btn_dynamic_save.clicked.connect(self.on_save_dynamic_json)

        # seed 2 rows (0/1) like your screenshot (optional)
        if self.tbl_labels.rowCount() == 0:
            self._add_label_row(prefix="0", name="0", _id=0)
            self._add_label_row(prefix="reject", name="MISS", _id=0)
            self._add_label_row(prefix="1", name="1", _id=1)

    def _build_detect_tab(self):
        # === 原本 ui_v4.py 的 Detect UI 全部 그대로 ===
        layout = QVBoxLayout(self.tab_detect)
        layout.setSpacing(8)

        # Basic
        g_basic = QGroupBox("Connection / Model")
        f = QFormLayout(g_basic)

        # Import Button for Detect parameters
        btn_detect_import = QPushButton("Import STD/HOLDAVG from CSV (Select Log)")
        btn_detect_import.clicked.connect(self.on_detect_import_csv)
        f.addRow("", btn_detect_import)

        self.edit_port = QLineEdit(getattr(detect, "PORT", "COM6"))
        self.combo_baud = QComboBox()
        self.combo_baud.addItems(["115200", "230400", "460800", "921600", "1000000","1500000"])

        self.edit_model = QLineEdit(str(getattr(detect, "MODEL_PATH", "gesture_model_v5.pkl")))
        self.btn_browse_model = QPushButton("Browse...")

        w_model = QWidget()
        hm = QHBoxLayout(w_model)
        hm.setContentsMargins(0, 0, 0, 0)
        hm.addWidget(self.edit_model)
        hm.addWidget(self.btn_browse_model)

        self.edit_meta = QLineEdit(str(getattr(detect, "META_PATH", "gesture_model_meta_v5.pkl")))
        self.btn_browse_meta = QPushButton("Browse...")

        w_meta = QWidget()
        hmeta = QHBoxLayout(w_meta)
        hmeta.setContentsMargins(0, 0, 0, 0)
        hmeta.addWidget(self.edit_meta)
        hmeta.addWidget(self.btn_browse_meta)

        f.addRow("Port:", self.edit_port)
        f.addRow("Baud:", self.combo_baud)
        f.addRow("Model:", w_model)
        f.addRow("Meta:", w_meta)

        self.chk_print_proba = QCheckBox("Print proba / top5")
        self.chk_print_proba.setChecked(bool(getattr(detect, "PRINT_PROBA", True)))
        f.addRow("", self.chk_print_proba)

        self.btn_detect_start = QPushButton("Start Detect")
        self.btn_detect_stop = QPushButton("Stop Detect")
        self.btn_detect_stop.setEnabled(False)

        row_btn = QWidget()
        hb = QHBoxLayout(row_btn)
        hb.setContentsMargins(0, 0, 0, 0)
        hb.addWidget(self.btn_detect_start)
        hb.addWidget(self.btn_detect_stop)
        hb.addStretch(1)
        f.addRow("", row_btn)

        layout.addWidget(g_basic)

        # Dynamic Result
        g_dynamic_result = QGroupBox("Dynamic Result")
        v_dyn = QVBoxLayout(g_dynamic_result)
        self.lbl_dynamic_result = QLabel("--")
        self.lbl_dynamic_result.setAlignment(Qt.AlignCenter)
        font = self.lbl_dynamic_result.font()
        font.setPointSize(24)
        font.setBold(True)
        self.lbl_dynamic_result.setFont(font)
        v_dyn.addWidget(self.lbl_dynamic_result)
        layout.addWidget(g_dynamic_result)

        # Dynamic Gestures Config
        g_dynamic_cfg = QGroupBox("Dynamic Gestures Config")
        f_dyn_cfg = QFormLayout(g_dynamic_cfg)

        self.edit_dynamic_json = QLineEdit("dynamic_gestures.json")
        self.btn_browse_dynamic_json = QPushButton("Browse...")
        w_dyn = QWidget()
        h_dyn = QHBoxLayout(w_dyn); h_dyn.setContentsMargins(0, 0, 0, 0)
        h_dyn.addWidget(self.edit_dynamic_json, 1)
        h_dyn.addWidget(self.btn_browse_dynamic_json)
        f_dyn_cfg.addRow("Dynamic gestures JSON:", w_dyn)

        layout.addWidget(g_dynamic_cfg)

        # New: Real-time Post-Processing Config for Detect Tab
        g_detect_post = QGroupBox("CNN Post-Processing (Real-time Tuning)")
        f_dp = QFormLayout(g_detect_post)

        self.dsb_detect_alpha = NoWheelDoubleSpinBox()
        self.dsb_detect_alpha.setRange(0.01, 1.0); self.dsb_detect_alpha.setValue(0.20)
        self.dsb_detect_alpha.setToolTip(
            "指數加權移動平均 (EWMA) 平滑係數，範圍從 0.01 到 1.0。\n"
            "- 較低值 (如 0.10-0.30)：加重歷史數值的權重，最大化穩定性，有效過濾瞬時雜訊，但會增加響應延遲。\n"
            "- 較高值 (如 0.50-0.80)：加重當前輸入的權重，提供即時反應速度，但信號微弱時可能會產生閃爍 (抖動)。"
        )
        lbl_alpha = QLabel("Smoothing Alpha:")
        lbl_alpha.setToolTip(self.dsb_detect_alpha.toolTip())
        f_dp.addRow(lbl_alpha, self.dsb_detect_alpha)

        self.dsb_detect_margin = NoWheelDoubleSpinBox()
        self.dsb_detect_margin.setRange(0.0, 1.0); self.dsb_detect_margin.setValue(0.45)
        self.dsb_detect_margin.setToolTip(
            "當前活動手勢切換至新手勢所需的機率差門檻。\n"
            "- 設置較高 (如 0.40+)：當兩個手勢特徵相似時，可防止 UI 在兩者間頻繁切換 (跳動)，提升穩定度。\n"
            "- 設置較低 (如 0.10)：允許更靈敏的手勢切換速度，但極易受原始信號雜訊干擾而產生誤觸。"
        )
        lbl_margin = QLabel("Switching Margin:")
        lbl_margin.setToolTip(self.dsb_detect_margin.toolTip())
        f_dp.addRow(lbl_margin, self.dsb_detect_margin)

        self.dsb_detect_exit = NoWheelDoubleSpinBox()
        self.dsb_detect_exit.setRange(0.0, 1.0); self.dsb_detect_exit.setValue(0.25)
        self.dsb_detect_exit.setToolTip(
            "維持當前手勢「鎖定輸出」狀態的最低機率門檻。\n"
            "- 如果目前活動手勢的機率低於此門檻，輸出將自動重設為「convert」狀態。\n"
            "- 高值：系統容易解除手勢輸出。低值：即使信號微弱也會保持鎖定，直到完全消失。"
        )
        lbl_exit = QLabel("Latch Exit Thresh:")
        lbl_exit.setToolTip(self.dsb_detect_exit.toolTip())
        f_dp.addRow(lbl_exit, self.dsb_detect_exit)

        self.sb_detect_stride = NoWheelSpinBox()
        self.sb_detect_stride.setRange(1, 100); self.sb_detect_stride.setValue(6)
        self.sb_detect_stride.setToolTip(
            "在 MCU 端執行推理 (Inference) 之間，所跳過的原始資料幀 (Frames) 數量。\n"
            "- STRIDE=1：每幀資料皆進行推理 (CPU 負載最高，可能降低序列埠輸出頻率至 ~32Hz)。\n"
            "- STRIDE=6+：平衡運算負擔與響應速度的最佳選擇，確保序列輸出能維持在 100Hz 的高頻率。"
        )
        lbl_stride = QLabel("Inference Stride:")
        lbl_stride.setToolTip(self.sb_detect_stride.toolTip())
        f_dp.addRow(lbl_stride, self.sb_detect_stride)

        self.dsb_detect_slope = NoWheelDoubleSpinBox()
        self.dsb_detect_slope.setRange(1.0, 500.0); self.dsb_detect_slope.setValue(20.0)
        self.dsb_detect_slope.setToolTip("即時調整斜率放大倍率。若模型辨識「呼氣」不靈敏，可嘗試調大此值。")
        lbl_slope = QLabel("Slope Factor (斜率放大):")
        lbl_slope.setToolTip(self.dsb_detect_slope.toolTip())
        f_dp.addRow(lbl_slope, self.dsb_detect_slope)

        # Macro Tier Definition (Independent for Detect)
        self.tbl_detect_tier_base = QTableWidget(3, 3)
        self.tbl_detect_tier_base.setHorizontalHeaderLabels(["Tier", "Stable", "Thresh"])
        self.tbl_detect_tier_base.setRowCount(3); self.tbl_detect_tier_base.verticalHeader().setVisible(False)
        self.tbl_detect_tier_base.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_detect_tier_base.setMinimumHeight(125)
        self.tbl_detect_tier_base.setToolTip(
            "用於快速定義手勢靈敏度的型板：\n"
            "- 快速 (Fast)：0 幀穩定，0.70 信心門檻 (訴求最高響應速度)。\n"
            "- 標準 (Normal)：10 幀穩定，0.50 信心門檻 (平衡穩定與反應)。\n"
            "- 嚴格 (Strict)：20 幀穩定，0.75 信心門檻 (高準確度導向，防止誤判)。"
        )
        
        tier_names = ["Fast", "Normal", "Strict"]
        default_vals = [(0, 0.70), (10, 0.50), (20, 0.75)]
        for i, (name, (s, t)) in enumerate(zip(tier_names, default_vals)):
            self.tbl_detect_tier_base.setItem(i, 0, QTableWidgetItem(name))
            self.tbl_detect_tier_base.item(i, 0).setFlags(Qt.ItemIsEnabled)
            sb = NoWheelSpinBox(); sb.setRange(0, 100); sb.setValue(s)
            self.tbl_detect_tier_base.setCellWidget(i, 1, sb)
            dsb = NoWheelDoubleSpinBox(); dsb.setRange(0.0, 1.0); dsb.setValue(t); dsb.setDecimals(2)
            self.tbl_detect_tier_base.setCellWidget(i, 2, dsb)
            sb.valueChanged.connect(lambda: self._sync_tier_rows(self.tbl_detect_tier_base, self.tbl_detect_gestures))
            dsb.valueChanged.connect(lambda: self._sync_tier_rows(self.tbl_detect_tier_base, self.tbl_detect_gestures))

        lbl_tier = QLabel("Global Defaults:")
        lbl_tier.setToolTip(self.tbl_detect_tier_base.toolTip())
        f_dp.addRow(lbl_tier, self.tbl_detect_tier_base)

        self.tbl_detect_gestures = QTableWidget(0, 5)
        self.tbl_detect_gestures.setHorizontalHeaderLabels(["ID", "Name", "Tier", "Stable", "Thresh"])
        self.tbl_detect_gestures.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_detect_gestures.setMinimumHeight(250)
        self.tbl_detect_gestures.setToolTip(
            "個別手勢覆蓋設定。這些設定的優先權高於「全域靈敏度預設值」。\n"
            "- 適用於將關鍵手勢設為「快速」或將容易出錯的手勢設為「嚴格」。"
        )
        lbl_ges = QLabel("Gesture Settings:")
        lbl_ges.setToolTip(self.tbl_detect_gestures.toolTip())
        f_dp.addRow(lbl_ges, self.tbl_detect_gestures)

        layout.addWidget(g_detect_post)

        # Manual holdavg
        g_hold = QGroupBox("Manual HOLDAVG (used if SILHOLD missing)")
        vh = QVBoxLayout(g_hold)

        self.chk_use_manual = QCheckBox("Enable manual holdavg")
        self.chk_use_manual.setChecked(bool(getattr(detect, "USE_MANUAL_HOLDAVG", True)))
        vh.addWidget(self.chk_use_manual)

        self.tbl_hold = QTableWidget(6, 2)
        self.tbl_hold.setHorizontalHeaderLabels(["CH", "holdavg"])
        self.tbl_hold.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_hold.setMinimumHeight(215) # Show 6 rows without scrollbar
        vh.addWidget(self.tbl_hold)

        for i in range(6):
            self.tbl_hold.setItem(i, 0, QTableWidgetItem(str(i + 1)))
            v = int(getattr(detect, "MANUAL_HOLDAVG", {}).get(i + 1, 0))
            if v == 0 and i == 5: v = 17966 # default for CH6
            self.tbl_hold.setItem(i, 1, QTableWidgetItem(str(v)))

        layout.addWidget(g_hold)

        # Gain map
        g_gain = QGroupBox("Gain Map (align B -> A)")
        fg = QFormLayout(g_gain)

        self.chk_gain = QCheckBox("Enable gain map")
        self.chk_gain.setChecked(bool(getattr(detect, "ENABLE_GAIN_MAP", True)))

        self.tbl_base_a = QTableWidget(6, 2)
        self.tbl_base_a.setHorizontalHeaderLabels(["CH", "STD_BASELINE_A"])
        self.tbl_base_a.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_base_a.setMinimumHeight(215)

        self.tbl_hold_a = QTableWidget(6, 2)
        self.tbl_hold_a.setHorizontalHeaderLabels(["CH", "STD_HOLDAVG_A"])
        self.tbl_hold_a.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_hold_a.setMinimumHeight(215)

        std_base = getattr(detect, "STD_BASELINE_A", {})
        std_hold = getattr(detect, "STD_HOLDAVG_A", {})
        for i in range(6):
            self.tbl_base_a.setItem(i, 0, QTableWidgetItem(str(i + 1)))
            v_b = int(std_base.get(i + 1, 0))
            if v_b == 0 and i == 5: v_b = 15956
            self.tbl_base_a.setItem(i, 1, QTableWidgetItem(str(v_b)))

            self.tbl_hold_a.setItem(i, 0, QTableWidgetItem(str(i + 1)))
            v_h = int(std_hold.get(i + 1, 0))
            if v_h == 0 and i == 5: v_h = 17966
            self.tbl_hold_a.setItem(i, 1, QTableWidgetItem(str(v_h)))

        self.dsb_min_span = NoWheelDoubleSpinBox()
        self.dsb_min_span.setDecimals(1)
        self.dsb_min_span.setRange(0, 999999)
        self.dsb_min_span.setValue(float(getattr(detect, "MIN_SPAN_B", 500.0)))

        self.dsb_gmin = NoWheelDoubleSpinBox()
        self.dsb_gmin.setDecimals(3)
        self.dsb_gmin.setRange(0.0, 10.0)
        self.dsb_gmin.setValue(float(getattr(detect, "GAIN_CLAMP_MIN", 0.5)))

        self.dsb_gmax = NoWheelDoubleSpinBox()
        self.dsb_gmax.setDecimals(3)
        self.dsb_gmax.setRange(0.0, 10.0)
        self.dsb_gmax.setValue(float(getattr(detect, "GAIN_CLAMP_MAX", 2.5)))

        fg.addRow("", self.chk_gain)
        fg.addRow("STD_BASELINE_A:", self.tbl_base_a)
        fg.addRow("STD_HOLDAVG_A:", self.tbl_hold_a)
        fg.addRow("MIN_SPAN_B:", self.dsb_min_span)
        fg.addRow("GAIN_CLAMP_MIN:", self.dsb_gmin)
        fg.addRow("GAIN_CLAMP_MAX:", self.dsb_gmax)

        layout.addWidget(g_gain)
        layout.addStretch(1)

        self.btn_browse_model.clicked.connect(self.on_browse_model)
        self.btn_browse_meta.clicked.connect(self.on_browse_meta)
        self.btn_browse_dynamic_json.clicked.connect(self.on_browse_dynamic_json)
        self.btn_detect_start.clicked.connect(self.on_detect_start)
        self.btn_detect_stop.clicked.connect(self.on_detect_stop)
        
        self.edit_meta.textChanged.connect(self.on_detect_meta_changed)


    def _build_gencode_cnn_tab(self):
        layout = QVBoxLayout(self.tab_gencode_cnn)
        layout.setSpacing(8)

        g_in = QGroupBox("CNN Meta / Model / Output")
        f = QFormLayout(g_in)

        self.le_gen_cnn_meta = QLineEdit()
        self.btn_gen_cnn_browse_meta = QPushButton("Browse...")
        self.btn_gen_cnn_browse_meta.clicked.connect(self.on_gen_cnn_browse_meta)
        w1 = QWidget()
        h1 = QHBoxLayout(w1); h1.setContentsMargins(0, 0, 0, 0)
        h1.addWidget(self.le_gen_cnn_meta); h1.addWidget(self.btn_gen_cnn_browse_meta)
        f.addRow("Meta (.pkl):", w1)

        self.le_gen_cnn_model = QLineEdit()
        self.btn_gen_cnn_browse_model = QPushButton("Browse...")
        self.btn_gen_cnn_browse_model.clicked.connect(self.on_gen_cnn_browse_model)
        w2 = QWidget()
        h2 = QHBoxLayout(w2); h2.setContentsMargins(0, 0, 0, 0)
        h2.addWidget(self.le_gen_cnn_model); h2.addWidget(self.btn_gen_cnn_browse_model)
        f.addRow("Model (.keras/.h5):", w2)

        self.le_gen_cnn_outdir = QLineEdit()
        self.btn_gen_cnn_browse_outdir = QPushButton("Browse...")
        self.btn_gen_cnn_browse_outdir.clicked.connect(self.on_gen_cnn_browse_outdir)
        w3 = QWidget()
        h3 = QHBoxLayout(w3); h3.setContentsMargins(0, 0, 0, 0)
        h3.addWidget(self.le_gen_cnn_outdir); h3.addWidget(self.btn_gen_cnn_browse_outdir)
        f.addRow("Output dir (cnn_lib):", w3)

        self.le_gen_cnn_basename = QLineEdit("cnn")
        f.addRow("Base output name:", self.le_gen_cnn_basename)

        self.le_gen_cnn_meta.textChanged.connect(self.on_gen_cnn_meta_changed)

        layout.addWidget(g_in)

        # Mapping (STD A) settings
        g_std = QGroupBox("Mapping / Sensitivity (STD A)")
        f_std = QVBoxLayout(g_std)


        def mk_std_row_cnn(title: str):
            w = QWidget()
            lay = QHBoxLayout(w); lay.setContentsMargins(0, 0, 0, 0)
            lay.addWidget(QLabel(title))
            spins = []
            for i in range(6):
                lay.addWidget(QLabel(f"CH{i+1}"))
                sb = NoWheelSpinBox()
                sb.setRange(0, 65535)
                sb.setValue(0)
                lay.addWidget(sb)
                spins.append(sb)
            return w, spins

        row1_w, self.gen_cnn_std_base_spins = mk_std_row_cnn("STD_BASELINE_A:")
        row2_w, self.gen_cnn_std_hold_spins = mk_std_row_cnn("STD_HOLDAVG_A: ")
        f_std.addWidget(row1_w)
        f_std.addWidget(row2_w)

        self.btn_gen_cnn_import_std = QPushButton("Import STD Scale from CSV (Log)")
        self.btn_gen_cnn_import_std.clicked.connect(self.on_gen_cnn_import_std)
        f_std.addWidget(self.btn_gen_cnn_import_std)
        
        layout.addWidget(g_std)

        # Post-Processing Settings
        g_post = QGroupBox("Post-Processing & Tiered Validation")
        f_post = QFormLayout(g_post)

        self.lbl_gen_cnn_alpha = QLabel("Smoothing Alpha:")
        self.lbl_gen_cnn_alpha.setToolTip(
            "指數加權移動平均 (EWMA) 平滑係數，範圍從 0.01 到 1.0。\n"
            "- 較低值 (如 0.10-0.30)：加重歷史數值的權重，最大化穩定性，有效過濾瞬時雜訊，但會顯著增加延遲感。\n"
            "- 較高值 (如 0.50-0.80)：加重當端輸入的權重，提供即時反應速度，但可能導致預測閃爍 (抖動)。"
        )
        self.dsb_gen_cnn_alpha = NoWheelDoubleSpinBox()
        self.dsb_gen_cnn_alpha.setRange(0.01, 1.0)
        self.dsb_gen_cnn_alpha.setValue(0.20)
        self.dsb_gen_cnn_alpha.setSingleStep(0.05)
        f_post.addRow(self.lbl_gen_cnn_alpha, self.dsb_gen_cnn_alpha)

        self.lbl_gen_cnn_margin = QLabel("Switching Margin:")
        self.lbl_gen_cnn_margin.setToolTip(
            "當前活動手勢切換至新手勢所需的機率差門檻。\n"
            "- 設置較高 (如 0.40+)：當兩個手勢特徵相似時，可防止 UI 在兩者間頻繁切換 (跳動)，提升穩定度。\n"
            "- 設置較低 (如 0.10)：允許更靈敏的手勢切換速度，但極易受原始信號雜訊干擾而產生誤觸。"
        )
        self.dsb_gen_cnn_margin = NoWheelDoubleSpinBox()
        self.dsb_gen_cnn_margin.setRange(0.0, 1.0)
        self.dsb_gen_cnn_margin.setValue(0.45)
        self.dsb_gen_cnn_margin.setSingleStep(0.05)
        f_post.addRow(self.lbl_gen_cnn_margin, self.dsb_gen_cnn_margin)

        self.lbl_gen_cnn_stride = QLabel("Inference Stride:")
        self.lbl_gen_cnn_stride.setToolTip(
            "在 MCU 端執行推理 (Inference) 之間，所跳過的原始資料幀 (Frames) 數量。\n"
            "- Stride=1：每幀資料皆進行推理 (CPU 負載最高，可能迫使序列埠頻率下降)。\n"
            "- Stride=6-10：平衡運算負擔與響應速度的最佳選擇，確保序列輸出能維持高頻率。"
        )
        self.spin_gen_cnn_stride = NoWheelSpinBox()
        self.spin_gen_cnn_stride.setRange(1, 100)
        self.spin_gen_cnn_stride.setValue(6)
        f_post.addRow(self.lbl_gen_cnn_stride, self.spin_gen_cnn_stride)

        self.lbl_gen_cnn_slope = QLabel("Slope Factor (斜率放大):")
        self.lbl_gen_cnn_slope.setToolTip("特徵提取時的斜率放大倍率。若模型辨識呼氣不靈敏，可調大此值。")
        self.dsb_gen_cnn_slope = NoWheelDoubleSpinBox()
        self.dsb_gen_cnn_slope.setRange(1.0, 500.0)
        self.dsb_gen_cnn_slope.setValue(20.0)
        f_post.addRow(self.lbl_gen_cnn_slope, self.dsb_gen_cnn_slope)

        # Tier Definitions (Macro Settings)
        f_post.addRow("Tier Definitions:", QLabel("(Set global defaults for each level)"))
        self.tbl_tier_base = QTableWidget(3, 3)
        self.tbl_tier_base.setHorizontalHeaderLabels(["Tier", "Stable", "Thresh"])
        self.tbl_tier_base.setRowCount(3)
        self.tbl_tier_base.verticalHeader().setVisible(False)
        self.tbl_tier_base.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_tier_base.setMinimumHeight(125)
        
        tier_names = ["Fast", "Normal", "Strict"]
        default_vals = [(0, 0.70), (10, 0.50), (20, 0.75)]
        for i, (name, (s, t)) in enumerate(zip(tier_names, default_vals)):
            self.tbl_tier_base.setItem(i, 0, QTableWidgetItem(name))
            # Make sure ID/Name is not editable
            self.tbl_tier_base.item(i, 0).setFlags(Qt.ItemIsEnabled)
            
            sb_b = NoWheelSpinBox()
            sb_b.setRange(0, 100); sb_b.setValue(s)
            self.tbl_tier_base.setCellWidget(i, 1, sb_b)
            
            dsb_b = NoWheelDoubleSpinBox()
            dsb_b.setRange(0.0, 1.0); dsb_b.setValue(t); dsb_b.setDecimals(2); dsb_b.setSingleStep(0.05)
            self.tbl_tier_base.setCellWidget(i, 2, dsb_b)
            
            sb_b.valueChanged.connect(lambda: self._sync_tier_rows(self.tbl_tier_base, self.tbl_gen_cnn_tiers))
            dsb_b.valueChanged.connect(lambda: self._sync_tier_rows(self.tbl_tier_base, self.tbl_gen_cnn_tiers))

        f_post.addRow("", self.tbl_tier_base)

        self.tbl_gen_cnn_tiers = QTableWidget(0, 5)
        self.tbl_gen_cnn_tiers.setHorizontalHeaderLabels(["ID", "Name", "Tier", "Stable", "Thresh"])
        # Set ToolTips for Table Headers
        self.tbl_gen_cnn_tiers.horizontalHeaderItem(2).setToolTip("驗證階層：\n- 快速 (Fast): 即時響應 (用於關鍵指令如 SOS)\n- 標準 (Normal): 標準穩定 (大多數數字)\n- 嚴格 (Strict): 嚴格過濾 (針對容易誤碼的雜訊手勢)")
        self.tbl_gen_cnn_tiers.horizontalHeaderItem(3).setToolTip("穩定幀數：切換至該手勢前，必須連續檢測到的次數。")
        self.tbl_gen_cnn_tiers.horizontalHeaderItem(4).setToolTip("判定門檻：該手勢推論信心值必須高過此數值才被採納。")
        
        self.tbl_gen_cnn_tiers.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_gen_cnn_tiers.setMinimumHeight(250)
        f_post.addRow("Gesture Tiers:", self.tbl_gen_cnn_tiers)

        layout.addWidget(g_post)


        self.btn_gen_cnn_all = QPushButton("GENERATE ALL (cnn_lib)")
        self.btn_gen_cnn_all.setFixedHeight(40)
        self.btn_gen_cnn_all.setStyleSheet("background-color: #2c3e50; color: white; font-weight: bold;")
        self.btn_gen_cnn_all.clicked.connect(self.on_gen_cnn_all)
        layout.addWidget(self.btn_gen_cnn_all)

        layout.addStretch(1)

    def on_gen_cnn_browse_meta(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select CNN Meta", "", "Pickle (*.pkl)")
        if path: self.le_gen_cnn_meta.setText(path)

    def on_gen_cnn_browse_model(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select CNN Model", "", "Keras/H5 (*.keras *.h5)")
        if path: self.le_gen_cnn_model.setText(path)

    def on_gen_cnn_browse_outdir(self):
        path = QFileDialog.getExistingDirectory(self, "Select Output Directory (cnn_lib)")
        if path: self.le_gen_cnn_outdir.setText(path)

    def on_gen_cnn_import_std(self):
        # Mirroring the logic from Detect tab
        default_path = r"C:\Users\USE\Desktop\SEAN_CODE\mlp_station_git\station_v15\15手勢log"
        if not os.path.exists(default_path):
            default_path = ""
            
        path, _ = QFileDialog.getOpenFileName(self, "Import STD values from CSV (Log)", default_path, "CSV (*.csv);;All files (*.*)")
        if not path:
            return
        
        try:
            with open(path, mode='r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                row = next(reader)
                
                for i in range(6):
                    # HOLDAVG
                    key_h = f"HOLDAVG{i+1}"
                    if key_h in row:
                        val_h = int(float(row[key_h]))
                        self.gen_cnn_std_hold_spins[i].setValue(val_h)
                    
                    # MOVBASE
                    key_b = f"MOVBASE{i+1}"
                    if key_b in row:
                        val_b = int(float(row[key_b]))
                        self.gen_cnn_std_base_spins[i].setValue(val_b)
                        
            self.append_log(_tag_line("GEN_CNN", f"Imported STD Scale from: {path}"))
            
        except StopIteration:
            QMessageBox.warning(self, "Import CSV", "The CSV file is empty!")
        except Exception as e:
            QMessageBox.critical(self, "Import CSV Error", str(e))

    def on_detect_meta_changed(self):
        self._populate_tier_table(self.edit_meta.text(), self.tbl_detect_gestures, self.tbl_detect_tier_base)

    def on_gen_cnn_meta_changed(self):
        self._populate_tier_table(self.le_gen_cnn_meta.text(), self.tbl_gen_cnn_tiers, self.tbl_tier_base)

    def _populate_tier_table(self, meta_path: str, target_tbl: QTableWidget, base_tbl: QTableWidget):
        path = meta_path.strip()
        if not path or not os.path.exists(path):
            target_tbl.setRowCount(0)
            return
        try:
            import joblib
            meta = joblib.load(path)
            id_to_name = meta.get('id_to_name', {})
            num_classes = meta.get('num_classes', len(id_to_name))
            
            target_tbl.setRowCount(0)
            target_tbl.setRowCount(num_classes)
            
            vips = [0, 5, 10, 11, 14, 15]
            restricteds = [1, 2, 13]

            for i in range(num_classes):
                name = id_to_name.get(i, f"cl{i}")
                target_tbl.setItem(i, 0, QTableWidgetItem(str(i)))
                target_tbl.setItem(i, 1, QTableWidgetItem(name))
                
                combo = QComboBox()
                combo.addItems(["Fast", "Normal", "Strict"])
                
                default_tier = "Normal"
                low_name = name.lower()
                if i in vips or "sos" in low_name: default_tier = "Fast"
                elif i in restricteds: default_tier = "Strict"
                combo.setCurrentText(default_tier)
                target_tbl.setCellWidget(i, 2, combo)
                
                sb_s = NoWheelSpinBox(); sb_s.setRange(0, 100); sb_s.setEnabled(False)
                dsb_t = NoWheelDoubleSpinBox(); dsb_t.setRange(0.0, 1.0); dsb_t.setDecimals(2); dsb_t.setEnabled(False)
                target_tbl.setCellWidget(i, 3, sb_s)
                # Correct lambda to capture current tables for sync
                combo.currentTextChanged.connect(lambda _, b=base_tbl, t=target_tbl: self._sync_tier_rows(b, t))
            
            # Initial trigger
            self._sync_tier_rows(base_tbl, target_tbl)

            # ✅ 自動從 Meta 更新斜率係數 (如果有)
            if hasattr(self, "dsb_detect_slope") and "slope_factor" in meta:
                self.dsb_detect_slope.setValue(float(meta["slope_factor"]))
                self.append_log(_tag_line("DETECT", f"Auto-synced Slope Factor from meta: {meta['slope_factor']}"))
        except Exception as e:
            print(f"[UI] Table populate error: {e}")

    def _sync_tier_rows(self, base_tbl: QTableWidget, target_tbl: QTableWidget):
        base_map = {}
        for i in range(3):
            name = base_tbl.item(i, 0).text()
            s = base_tbl.cellWidget(i, 1).value()
            t = base_tbl.cellWidget(i, 2).value()
            base_map[name] = (s, t)
            
        for i in range(target_tbl.rowCount()):
            combo = target_tbl.cellWidget(i, 2)
            if combo and combo.currentText() in base_map:
                s, t = base_map[combo.currentText()]
                sb = target_tbl.cellWidget(i, 3)
                dsb = target_tbl.cellWidget(i, 4)
                if sb: sb.setValue(s)
                if dsb: dsb.setValue(t)

    def _extract_tier_data_from_ui(self, base_tbl: QTableWidget, target_tbl: QTableWidget) -> dict:
        def get_v(row):
            return base_tbl.cellWidget(row, 1).value(), base_tbl.cellWidget(row, 2).value()
        sf, tp = get_v(0); sn, tn = get_v(1); sr, tr = get_v(2)
        p_ids, r_ids = [], []
        for i in range(target_tbl.rowCount()):
            it = target_tbl.item(i, 0)
            if not it: continue
            idx = int(it.text())
            combo = target_tbl.cellWidget(i, 2)
            if not combo: continue
            tier = combo.currentText()
            if tier == "Fast": p_ids.append(idx)
            elif tier == "Strict": r_ids.append(idx)
        return {
            'priority_ids': p_ids, 'restricted_ids': r_ids, 
            'thresh_priority': tp, 'thresh_restricted': tr, 'thresh_entry': tn, 
            'stable_fast': sf, 'stable_normal': sn, 'stable_restricted': sr
        }


    def on_gen_cnn_all(self):
        if self.thread_gen_cnn is not None:
            return
        
        cfg = GenCnnCodeCfg(
            meta_path=self.le_gen_cnn_meta.text().strip(),
            model_path=self.le_gen_cnn_model.text().strip(),
            outdir=self.le_gen_cnn_outdir.text().strip(),
            base_name=self.le_gen_cnn_basename.text().strip(),
            std_base_a=[sb.value() for sb in self.gen_cnn_std_base_spins],
            std_hold_a=[sb.value() for sb in self.gen_cnn_std_hold_spins],
            data_dir=self.edit_data_dir.text().strip(),
            alpha=self.dsb_gen_cnn_alpha.value(),
            margin=self.dsb_gen_cnn_margin.value(),
            infer_stride=self.spin_gen_cnn_stride.value(),
            slope_factor=self.dsb_gen_cnn_slope.value(),
            tier_data=self._extract_tier_data_from_ui(self.tbl_tier_base, self.tbl_gen_cnn_tiers)
        )

        self.append_log(_tag_line("GEN_CNN", "[UI] Starting CNN Gen All ..."))
        self._set_busy("gen_cnn")

        self.thread_gen_cnn = QThread()
        self.worker_gen_cnn = GenCnnCodeWorker(cfg)
        self.worker_gen_cnn.moveToThread(self.thread_gen_cnn)

        self.thread_gen_cnn.started.connect(self.worker_gen_cnn.run)
        self.worker_gen_cnn.log_line.connect(self.append_log)
        self.worker_gen_cnn.finished_ok.connect(self.on_gen_cnn_ok)
        self.worker_gen_cnn.finished_err.connect(self.on_gen_cnn_err)

        self.worker_gen_cnn.finished_ok.connect(self.thread_gen_cnn.quit)
        self.worker_gen_cnn.finished_err.connect(self.thread_gen_cnn.quit)
        self.thread_gen_cnn.finished.connect(self.on_gen_cnn_thread_finished)

        self.thread_gen_cnn.start()

    def on_gen_cnn_ok(self, res: dict):
        self.append_log(_tag_line("GEN_CNN", "=== GEN CNN SUCCESS ==="))
        # Store output dir for Auto Build
        self.last_gencode_output_dir = res.get("out_dir")
        self.lbl_autobuild_output_dir.setText(f"Output Directory: {self.last_gencode_output_dir}")
        QMessageBox.information(self, "Gen CNN", "CNN Library (cnn_lib) generated successfully!")

    def on_gen_cnn_err(self, err: str):
        self.append_log(_tag_line("GEN_CNN", f"=== GEN CNN ERROR ===\n{err}"))
        QMessageBox.critical(self, "Gen CNN Error", f"Failed to generate CNN code:\n{err}")

    def on_gen_cnn_thread_finished(self):
        self.thread_gen_cnn = None
        self.worker_gen_cnn = None
        self._set_busy(None)

    def _build_build_tab(self):
        layout = QVBoxLayout(self.tab_build)
        layout.setSpacing(8)

        # Main horizontal layout: Left (Settings/Build), Right (Flash)
        main_h = QHBoxLayout()
        left_w = QWidget()
        left_layout = QVBoxLayout(left_w)
        right_w = QWidget()
        right_layout = QVBoxLayout(right_w)
        
        # === 1. Build Section ===
        g_build = QGroupBox("Build Firmware")
        l_build = QVBoxLayout(g_build)

        # Project Directory
        f_proj = QFormLayout()
        self.edit_build_proj_dir = QLineEdit()
        self.edit_build_proj_dir.textChanged.connect(self.update_srec_path) # Auto update SREC
        self.btn_browse_build_proj = QPushButton("Browse...")
        w_proj = QWidget()
        h_proj = QHBoxLayout(w_proj)
        h_proj.setContentsMargins(0, 0, 0, 0)
        h_proj.addWidget(self.edit_build_proj_dir, 1)
        h_proj.addWidget(self.btn_browse_build_proj)
        f_proj.addRow("Project Directory:", w_proj)

        # Config & Clean
        self.combo_build_cfg = QComboBox()
        self.combo_build_cfg.addItems(["Debug", "Release"])
        self.combo_build_cfg.currentTextChanged.connect(self.update_srec_path) # Auto update SREC

        self.chk_build_clean = QCheckBox("Clean first (recommended for fresh builds)")
        
        f_proj.addRow("Configuration:", self.combo_build_cfg)
        f_proj.addRow("", self.chk_build_clean)
        l_build.addLayout(f_proj)

        # Build Actions
        self.btn_build = QPushButton("Build")
        self.btn_build.setMinimumHeight(40)
        self.btn_build_stop = QPushButton("Stop Build")
        self.btn_build_stop.setEnabled(False)
        self.btn_build_stop.setVisible(False) # User requested to hide

        h_act = QHBoxLayout()
        h_act.addWidget(self.btn_build, 2)
        h_act.addWidget(self.btn_build_stop, 1)
        l_build.addLayout(h_act)

        layout.addWidget(g_build)

        # === 2. Flash Section ===
        g_flash = QGroupBox("Flash Firmware")
        l_flash = QVBoxLayout(g_flash)

        f_flash = QFormLayout()
        
        # SREC Selection (Read-only, calculated)
        self.edit_flash_srec = QLineEdit()
        self.edit_flash_srec.setReadOnly(True)
        self.edit_flash_srec.setPlaceholderText("Auto-generated path to .srec file")
        f_flash.addRow("SREC Path:", self.edit_flash_srec)

        # COM Port
        self.edit_flash_port = QComboBox()
        self.edit_flash_port.setEditable(True)
        self.btn_flash_refresh = QPushButton("Refresh Ports")
        self.btn_flash_refresh.clicked.connect(self.on_flash_refresh_ports)
        
        w_port = QWidget()
        h_port = QHBoxLayout(w_port)
        h_port.setContentsMargins(0, 0, 0, 0)
        h_port.addWidget(self.edit_flash_port, 1)
        h_port.addWidget(self.btn_flash_refresh)
        f_flash.addRow("COM Port:", w_port)

        l_flash.addLayout(f_flash)

        # Flash Actions
        self.btn_flash = QPushButton("FLASH")
        self.btn_flash.setMinimumHeight(50)
        self.btn_flash.setStyleSheet("font-weight: bold; font-size: 14px;")
        
        self.btn_flash_stop = QPushButton("Stop Flash")
        self.btn_flash_stop.setEnabled(False)
        self.btn_flash_stop.setVisible(False) # User requested to hide

        h_flash_act = QHBoxLayout()
        h_flash_act.addWidget(self.btn_flash, 2)
        h_flash_act.addWidget(self.btn_flash_stop, 1)
        l_flash.addLayout(h_flash_act)

        layout.addWidget(g_flash)

        layout.addStretch(1)

        # Connections
        self.btn_browse_build_proj.clicked.connect(self.on_browse_build_proj)
        self.btn_build.clicked.connect(self.on_build_start)
        self.btn_build_stop.clicked.connect(self.on_build_stop)
        
        self.btn_flash.clicked.connect(self.on_flash_start)
        self.btn_flash_stop.clicked.connect(self.on_flash_stop)
        
        # Initial populate ports (MOVED to _apply_dark_theme end)
        # self.on_flash_refresh_ports()

    def _build_autobuild_tab(self):
        layout = QVBoxLayout(self.tab_autobuild)
        layout.setSpacing(8)

        # Auto Build Status
        g_status = QGroupBox("Auto Build Status")
        l_status = QVBoxLayout(g_status)
        
        self.lbl_autobuild_status = QLabel("Ready for Auto Build")
        self.lbl_autobuild_status.setStyleSheet("font-weight: bold; color: #4EC9B0;")
        l_status.addWidget(self.lbl_autobuild_status)
        
        # Output Directory Display
        self.lbl_autobuild_output_dir = QLabel("Output Directory: Not set")
        self.lbl_autobuild_output_dir.setStyleSheet("color: #cccccc; font-family: Consolas;")
        self.lbl_autobuild_output_dir.setWordWrap(True)
        l_status.addWidget(self.lbl_autobuild_output_dir)
        
        layout.addWidget(g_status)

        # Auto Build Actions
        g_actions = QGroupBox("Auto Build Actions")
        l_actions = QVBoxLayout(g_actions)
        
        self.btn_startbuild = QPushButton("StartBuild")
        self.btn_startbuild.setFixedHeight(40)
        self.btn_startbuild.setStyleSheet("background-color: #0e639c; font-weight: bold; font-size: 14pt;")
        
        self.btn_secure_clean = QPushButton("Secure Clean (Cleanup)")
        self.btn_secure_clean.setFixedHeight(30)
        self.btn_secure_clean.setStyleSheet("background-color: #5a1d1d; color: #ff9d9d;")
        self.btn_secure_clean.setVisible(False)
        
        self.cb_auto_cleanup = QCheckBox("Auto Cleanup after Build (Un-check for Debug)")
        self.cb_auto_cleanup.setChecked(True)
        self.cb_auto_cleanup.setVisible(False)
        self.cb_auto_cleanup.setStyleSheet("color: #ff9d9d; font-style: italic;")
        
        l_actions.addWidget(self.btn_startbuild)
        l_actions.addWidget(self.btn_secure_clean)
        l_actions.addWidget(self.cb_auto_cleanup)
        
        layout.addWidget(g_actions)

        # Flash Section (Mirrored from Build Tab)
        g_flash = QGroupBox("Flash Firmware")
        l_flash = QVBoxLayout(g_flash)
        f_flash = QFormLayout()

        self.edit_autobuild_flash_srec = QLineEdit()
        self.edit_autobuild_flash_srec.setReadOnly(True)
        self.edit_autobuild_flash_srec.setPlaceholderText("Auto-generated path to .srec file")
        f_flash.addRow("SREC Path:", self.edit_autobuild_flash_srec)

        self.edit_autobuild_flash_port = QComboBox()
        self.edit_autobuild_flash_port.setEditable(True)
        self.btn_autobuild_flash_refresh = QPushButton("Refresh Ports")
        
        w_port = QWidget()
        h_port = QHBoxLayout(w_port)
        h_port.setContentsMargins(0, 0, 0, 0)
        h_port.addWidget(self.edit_autobuild_flash_port, 1)
        h_port.addWidget(self.btn_autobuild_flash_refresh)
        f_flash.addRow("COM Port:", w_port)
        l_flash.addLayout(f_flash)

        self.btn_autobuild_flash = QPushButton("FLASH")
        self.btn_autobuild_flash.setMinimumHeight(50)
        self.btn_autobuild_flash.setStyleSheet("font-weight: bold; font-size: 14pt; background-color: #0e639c;")
        l_flash.addWidget(self.btn_autobuild_flash)

        layout.addWidget(g_flash)
        layout.addStretch(1)

        # Connections
        self.btn_startbuild.clicked.connect(self.on_startbuild_clicked)
        self.btn_secure_clean.clicked.connect(self.on_secure_clean_clicked)
        self.btn_autobuild_flash_refresh.clicked.connect(self.on_flash_refresh_ports)
        self.btn_autobuild_flash.clicked.connect(self.on_flash_start)

        # Sync COM Port selection with Build tab
        self.edit_autobuild_flash_port.currentTextChanged.connect(
            lambda t: self.edit_flash_port.setCurrentText(t) if self.edit_flash_port.currentText() != t else None
        )
        self.edit_flash_port.currentTextChanged.connect(
            lambda t: self.edit_autobuild_flash_port.setCurrentText(t) if self.edit_autobuild_flash_port.currentText() != t else None
        )

    def on_startbuild_clicked(self):
        """Handle StartBuild button click (Asynchronous)"""
        if not self.last_gencode_output_dir:
            QMessageBox.warning(self, "Auto Build", "No GenCode output directory available!\nPlease run Gen Code first.")
            return
        
        if self.busy_mode:
            return

        self._set_busy("autobuild")
        self.autobuild_stop_event.clear()
        
        cfg = AutoBuildCfg(
            detect_proj_dir=str(Path(__file__).parent / "mlp_detect"),
            feature_proj_dir=str(Path(__file__).parent / "mlp_feature"),
            rebuild_proj_dir=str(Path(__file__).parent / "glove_mlp_rebuild"),
            build_tool_dir=str(Path(__file__).parent / "buildtool"),
            last_gencode_output_dir=self.last_gencode_output_dir,
            auto_cleanup=self.cb_auto_cleanup.isChecked()
        )
        
        self.thread_autobuild = QThread()
        self.worker_autobuild = AutoBuildWorker(cfg, self.stop_event_autobuild)
        self.worker_autobuild.moveToThread(self.thread_autobuild)
        
        self.thread_autobuild.started.connect(self.worker_autobuild.run)
        self.worker_autobuild.log_line.connect(self.append_log)
        self.worker_autobuild.finished_ok.connect(self.on_autobuild_finished_ok)
        self.worker_autobuild.finished_err.connect(self.on_autobuild_finished_err)
        
        self.thread_autobuild.start()

    def on_autobuild_finished_ok(self, res):
        self._set_busy(None)
        self.thread_autobuild.quit()
        self.thread_autobuild.wait()
        
        # Clear path since it was deleted in Step 9
        if res.get("cleaned"):
            self.last_gencode_output_dir = None
            self.update_autobuild_display()

        msg = "Auto Build completed successfully!\n"
        msg += "1. libmlp_detect.a & libmlp_feature.a generated\n"
        msg += "2. glove_mlp_rebuild.srec generated\n"
        msg += "3. Intermediate source files SECURELY DELETED.\n"
        if "srec_path" in res:
            msg += f"\nPath: {res['srec_path']}"
            # Automatically set Flash path in Auto Build tab
            self.edit_autobuild_flash_srec.setText(res['srec_path'])
            # Also set in Build tab for consistency
            self.edit_flash_srec.setText(res['srec_path'])
            
        QMessageBox.information(self, "Auto Build", msg)

    def on_secure_clean_clicked(self):
        """Manually trigger secure cleanup"""
        reply = QMessageBox.warning(self, "Secure Cleanup", 
                                  "This will permanently delete ALL intermediate source files and the GenCode output folder.\n"
                                  "This action CANNOT be undone (bypasses Trash).\nProceed?",
                                  QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.No:
            return

        self.append_log(_tag_line("CLEANUP", "Starting manual secure cleanup..."))
        
        # Use dummy Cfg for manual cleanup
        cfg = AutoBuildCfg(
            detect_proj_dir=str(Path(__file__).parent / "mlp_detect"),
            feature_proj_dir=str(Path(__file__).parent / "mlp_feature"),
            rebuild_proj_dir=str(Path(__file__).parent / "glove_mlp_rebuild"),
            build_tool_dir=str(Path(__file__).parent / "buildtool"),
            last_gencode_output_dir=self.last_gencode_output_dir
        )
        
        # Create a temporary worker just for cleanup
        stop_evt = threading.Event()
        worker = AutoBuildWorker(cfg, stop_evt)
        worker.log_line.connect(self.append_log)
        
        # Inline run since it's mostly file IO
        try:
            worker._perform_cleanup()
            self.last_gencode_output_dir = None
            self.update_autobuild_display()
            QMessageBox.information(self, "Cleanup", "Secure cleanup finished successfully!")
        except Exception as e:
            QMessageBox.critical(self, "Cleanup Error", f"Cleanup failed: {e}")

    def on_autobuild_finished_err(self, err):
        self._set_busy(None)
        self.thread_autobuild.quit()
        self.thread_autobuild.wait()
        QMessageBox.critical(self, "Auto Build Error", f"Build failed:\n{err}")

    def update_autobuild_display(self):
        """Update Auto Build tab display with current gencode output directory"""
        if self.last_gencode_output_dir:
            self.lbl_autobuild_status.setText("Ready for Auto Build")
            self.lbl_autobuild_status.setStyleSheet("font-weight: bold; color: #4EC9B0;")
            self.lbl_autobuild_output_dir.setText(f"Output Directory: {self.last_gencode_output_dir}")
        else:
            self.lbl_autobuild_status.setText("No GenCode output available")
            self.lbl_autobuild_status.setStyleSheet("font-weight: bold; color: #FFA500;")
            self.lbl_autobuild_output_dir.setText("Output Directory: Not set")


    # -------------------------
    # Train label table helpers (原本)
    # -------------------------
    def _add_label_row(self, prefix: str = "", name: str = "", _id: Optional[int] = None):
        r = self.tbl_labels.rowCount()
        self.tbl_labels.insertRow(r)
        self.tbl_labels.setItem(r, 0, QTableWidgetItem(prefix))
        self.tbl_labels.setItem(r, 1, QTableWidgetItem(name))
        if _id is None:
            _id = r
        self.tbl_labels.setItem(r, 2, QTableWidgetItem(str(_id)))
        # ✅ 新增完後也檢查一下是否要排號
        self._maybe_auto_reassign_ids()

    def _remove_selected_label_rows(self):
        rows = sorted({i.row() for i in self.tbl_labels.selectedIndexes()}, reverse=True)
        for r in rows:
            self.tbl_labels.removeRow(r)
        self._maybe_auto_reassign_ids()

    def _maybe_auto_reassign_ids(self):
        if not self.chk_auto_id.isChecked():
            return
        for r in range(self.tbl_labels.rowCount()):
            it = self.tbl_labels.item(r, 2)
            if it:
                it.setText(str(r))

    def _browse_dir(self, edit: QLineEdit):
        path = QFileDialog.getExistingDirectory(self, "Select folder", edit.text().strip() or "")
        if path:
            edit.setText(path)

    def on_load_labels_json(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load labels JSON", "", "JSON (*.json);;All files (*.*)")
        if not path:
            return
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            rows = data.get("label_defs", [])
            self.tbl_labels.setRowCount(0)
            for r in rows:
                self._add_label_row(
                    prefix=str(r.get("prefix", "")),
                    name=str(r.get("name", "")),
                    _id=int(r.get("id", 0)),
                )
            # ✅ 載入完也重新排序 (如果 Auto-ID 有勾)
            self._maybe_auto_reassign_ids()
            self.append_log(_tag_line("TRAIN", f"Loaded labels: {path}"))
        except Exception as e:
            QMessageBox.critical(self, "Load labels", str(e))

    def on_save_labels_json(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save labels JSON", "labels.json", "JSON (*.json)")
        if not path:
            return
        try:
            rows = []
            for r in range(self.tbl_labels.rowCount()):
                prefix = (self.tbl_labels.item(r, 0).text() if self.tbl_labels.item(r, 0) else "").strip()
                name = (self.tbl_labels.item(r, 1).text() if self.tbl_labels.item(r, 1) else "").strip()
                _id = int((self.tbl_labels.item(r, 2).text() if self.tbl_labels.item(r, 2) else "0").strip())
                if not prefix:
                    continue
                rows.append({"prefix": prefix, "name": name or prefix, "id": _id})
            Path(path).write_text(json.dumps({"label_defs": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
            self.append_log(_tag_line("TRAIN", f"Saved labels: {path}"))
        except Exception as e:
            QMessageBox.critical(self, "Save labels", str(e))

    # -------------------------
    # Train build cfg + actions (原本)
    # -------------------------
    def _parse_int_tuple(self, s: str) -> tuple[int, ...]:
        s = (s or "").strip()
        if not s:
            return tuple()
        return tuple(int(x.strip()) for x in s.split(",") if x.strip())

    def _selected_channels(self) -> list[int]:
        res = []
        for i, cb in enumerate(self.chk_ch):
            if cb.isChecked():
                res.append(i + 1) # Use 1-based for CNN to match ROWCH1-6
        return res

    def build_train_cfg(self) -> cnn_trainer.TrainCfg:
        label_defs = []
        for r in range(self.tbl_labels.rowCount()):
            prefix = (self.tbl_labels.item(r, 0).text() if self.tbl_labels.item(r, 0) else "").strip()
            name = (self.tbl_labels.item(r, 1).text() if self.tbl_labels.item(r, 1) else "").strip()
            _id = int((self.tbl_labels.item(r, 2).text() if self.tbl_labels.item(r, 2) else "0").strip())
            if not prefix:
                continue
            label_defs.append({"prefix": prefix, "name": name or prefix, "id": _id})

        out_dir = Path(self.edit_out_dir.text().strip()) if self.edit_out_dir.text().strip() else Path(".")
        out_model_name = self.edit_out_model_path.text().strip()
        out_meta_name  = self.edit_out_meta_path.text().strip()

        cfg = cnn_trainer.TrainCfg(
            data_dir=Path(self.edit_data_dir.text().strip()),
            out_model_path=str(out_dir / out_model_name),
            out_meta_path=str(out_dir / out_meta_name),

            label_defs=label_defs,
            channels=self._selected_channels(),

            window_len=int(self.spin_window_len.value()),
            window_step=int(self.spin_window_step.value()),
            slope_factor=float(self.dsb_slope_factor.value()),

            # CNN Params
            epochs=int(self.spin_cnn_epochs.value()),
            batch_size=int(self.spin_batch_size.value()),
            learning_rate=float(self.dsb_learning_rate.value()),
            early_stop_patience=int(self.spin_early_stop_patience.value()),
            lr_patience=int(self.spin_lr_patience.value()),

            # Augmentation
            enable_augmentation=bool(self.chk_enable_aug.isChecked()),
            aug_copies=int(self.spin_aug_copies.value()),
            aug_delta_gain_min=float(self.dsb_delta_min.value()),
            aug_delta_gain_max=float(self.dsb_delta_max.value()),
            aug_span_gain_min=float(self.dsb_span_min.value()),
            aug_span_gain_max=float(self.dsb_span_max.value()),

            enable_offset_aug=bool(self.chk_offset_aug.isChecked()),
            aug_offset_sigma=float(self.dsb_sigma.value()),
            aug_offset_clip=float(self.dsb_clip.value()),

            enable_time_warp=bool(self.chk_time_warp.isChecked()),
            time_warp_min=float(self.dsb_tw_min.value()),
            time_warp_max=float(self.dsb_tw_max.value())
        )
        return cfg

    def _scan_dataset_cnn(self, cfg: cnn_trainer.TrainCfg) -> dict:
        """Simplified scanner for CNN dataset"""
        import os
        from pathlib import Path
        
        counts = {}
        unknown = {}
        total = 0
        valid = 0
        
        prefixes = {d["prefix"].lower().strip() for d in cfg.label_defs}
        
        if not cfg.data_dir.exists():
            return {"total_found": 0, "total_valid": 0}
            
        for f in cfg.data_dir.glob("*.csv"):
            total += 1
            p = f.name.split("-")[0].lower().strip()
            if p in prefixes:
                counts[p] = counts.get(p, 0) + 1
                valid += 1
            else:
                unknown[p] = unknown.get(p, 0) + 1
                
        return {
            "total_found": total,
            "total_valid": valid,
            "label_counts": counts,
            "unknown_prefix_counts": unknown,
            "invalid": [],
            "fatal_invalid": []
        }

    def on_scan(self):
        cfg = self.build_train_cfg()
        if not cfg.data_dir or not Path(cfg.data_dir).exists():
            QMessageBox.warning(self, "Scan", f"data_dir not found: {cfg.data_dir}")
            return
        if not cfg.label_defs:
            QMessageBox.warning(self, "Scan", "Label table empty.")
            return

        self.append_log(_tag_line("TRAIN", "[UI] Scan ..."))
        try:
            scan = self._scan_dataset_cnn(cfg)

            total_found = scan.get("total_found", 0)
            total_valid = scan.get("total_valid", 0)

            # v8 keys
            label_counts = scan.get("label_counts", {})                 # ✅ 類別統計（你要的）
            unknown = scan.get("unknown_prefix_counts", {})             # ✅ unknown prefix summary
            invalids = scan.get("invalid", [])                          # ✅ list[(path, reason)]
            fatal_invalids = scan.get("fatal_invalid", [])              # ✅ list[(path, reason)]

            self.append_log(_tag_line(
                "SCAN",
                f"total_found={total_found} total_valid={total_valid} invalid={len(invalids)} fatal={len(fatal_invalids)}"
            ))

            # ✅ 列類別（prefix -> name）
            if label_counts:
                p2name = {str(d.get("prefix")): str(d.get("name", d.get("prefix")))
                        for d in (cfg.label_defs or [])}

                self.append_log(_tag_line("SCAN", "label counts:"))
                for prefix, n in sorted(label_counts.items(), key=lambda kv: kv[0]):
                    name = p2name.get(str(prefix), str(prefix))
                    self.append_log(_tag_line("SCAN", f"  label '{prefix}' ({name}): {n} files"))

            # ✅ unknown prefix summary（照你 checkbox）
            if self.chk_scan_show_unknown_summary.isChecked():
                if unknown:
                    self.append_log(_tag_line("SCAN", "unknown prefix summary:"))
                    for k, v in sorted(unknown.items(), key=lambda kv: kv[0]):
                        self.append_log(_tag_line("SCAN", f"  unknown '{k}': {v} files"))

            # ✅ invalid details（照你 checkbox + max N）
            if self.chk_scan_show_invalid_detail.isChecked():
                show_list = fatal_invalids if fatal_invalids else invalids
                if show_list:
                    self.append_log(_tag_line("ERR", "Invalid filenames detected:"))
                    n = int(self.spin_scan_invalid_n.value())
                    for p, reason in show_list[:n]:
                        self.append_log(_tag_line("ERR", f"[INVALID] {p} => {reason}"))
                    if len(show_list) > n:
                        self.append_log(_tag_line("ERR", f"... ({len(show_list)-n} more)"))

        except Exception as e:
            QMessageBox.critical(self, "Scan", str(e))


    def on_train(self):
        if self.thread_train is not None:
            return

        cfg = self.build_train_cfg()
        if not cfg.data_dir or not Path(cfg.data_dir).exists():
            QMessageBox.warning(self, "Train", f"data_dir not found: {cfg.data_dir}")
            return

        # ✅ 檢查 ID 連續性
        ids = sorted([d["id"] for d in cfg.label_defs])
        if ids != list(range(len(ids))):
            ans = QMessageBox.warning(self, "ID Continuity check Failed",
                f"Gesture IDs are NOT continuous: {ids}\n"
                "This will cause AI and MCU mismatch!\n\n"
                "Do you want to AUTO-REASSIGN IDs now?",
                QMessageBox.Yes | QMessageBox.No)
            if ans == QMessageBox.Yes:
                self.chk_auto_id.setChecked(True)
                self._maybe_auto_reassign_ids()
                cfg = self.build_train_cfg() # 更新 cfg
            else:
                return

        if not cfg.label_defs:
            QMessageBox.warning(self, "Train", "Label table empty.")
            return

        self.stop_event_train.clear()
        self.btn_stop_train.setEnabled(True)
        out_dir = Path(self.edit_out_dir.text().strip()) if self.edit_out_dir.text().strip() else Path(".")
        self._open_train_log_file(out_dir)
        self.append_log(_tag_line("TRAIN", "[UI] Starting training ..."))
        self._set_busy("train")

        self.thread_train = QThread()
        selected_backbone = self.combo_model_backbone.currentText().strip().lower() if hasattr(self, "combo_model_backbone") else "cnn"
        self.append_log(_tag_line("TRAIN", f"[UI] Backbone: {selected_backbone}"))
        self.worker_train = TrainWorker(cfg, self.stop_event_train, backbone=selected_backbone)
        self.worker_train.moveToThread(self.thread_train)

        self.thread_train.started.connect(self.worker_train.run)
        self.worker_train.log_line.connect(self.append_log)

        self.worker_train.finished_ok.connect(self.on_train_ok)
        self.worker_train.finished_err.connect(self.on_train_err)

        self.worker_train.finished_ok.connect(self.thread_train.quit)
        self.worker_train.finished_err.connect(self.thread_train.quit)
        self.thread_train.finished.connect(self.on_train_thread_finished)

        self.thread_train.start()

    def on_stop_train(self):
        if self.thread_train is None:
            return
        self.append_log(_tag_line("TRAIN", "[UI] Stop requested ..."))
        self.stop_event_train.set()
        self.btn_stop_train.setEnabled(False)

    def on_train_ok(self, res: dict):
        self.append_log(_tag_line("TRAIN", "=== TRAIN DONE ==="))
        for k, v in res.items():
            self.append_log(_tag_line("TRAIN", f"{k}: {v}"))

    def on_train_err(self, msg: str):
        self.append_log(_tag_line("TRAIN", "=== TRAIN ERROR ==="))
        self.append_log(_tag_line("TRAIN", msg))
        QMessageBox.critical(self, "Train", msg)

    def on_train_thread_finished(self):
        self._close_train_log_file()
        self.btn_stop_train.setEnabled(False)
        self.thread_train = None
        self.worker_train = None
        self._set_busy(None)

    def on_view_report(self):
        """Open the training report PNG in the default system viewer"""
        import os
        output_dir = self.edit_out_dir.text().strip()
        if not output_dir:
            output_dir = "."
        report_path = os.path.join(output_dir, "training_report.png")
        if os.path.exists(report_path):
            os.startfile(os.path.abspath(report_path))
        else:
            QMessageBox.warning(self, "Report Not Found", f"Report file not found at:\n{report_path}\nPlease run training first.")

    # -------------------------
    # Dynamic gestures table helpers
    # -------------------------
    def _load_default_dynamic_gestures(self):
        """Auto-load default dynamic_gestures.json if exists"""
        try:
            path = Path("dynamic_gestures.json")
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                gestures = data.get("dynamic_gestures", [])
                for g in gestures:
                    name = g.get("name", "")
                    sequence = g.get("sequence", "")
                    max_gap = g.get("max_gap", 2)
                    time_window = g.get("time_window", 2.0)
                    self._add_dynamic_row(name, sequence, max_gap, time_window)
                self.append_log(f"[Train] Loaded {len(gestures)} dynamic gestures from dynamic_gestures.json")
        except Exception as e:
            self.append_log(f"[Train] Failed to load default dynamic_gestures.json: {e}")
            # Fallback to basic examples if loading fails
            self._add_dynamic_row("love", "5,6,0", 2, 2.0)
            self._add_dynamic_row("sos", "5,4,0", 2, 2.0)

    def _add_dynamic_row(self, name: str = "", sequence: str = "", max_gap: int = 2, time_window: float = 2.0):
        r = self.tbl_dynamic.rowCount()
        self.tbl_dynamic.insertRow(r)
        self.tbl_dynamic.setItem(r, 0, QTableWidgetItem(name))
        self.tbl_dynamic.setItem(r, 1, QTableWidgetItem(sequence))
        self.tbl_dynamic.setItem(r, 2, QTableWidgetItem(str(max_gap)))
        self.tbl_dynamic.setItem(r, 3, QTableWidgetItem(f"{time_window:.1f}"))

    def _remove_selected_dynamic_rows(self):
        rows = sorted({i.row() for i in self.tbl_dynamic.selectedIndexes()}, reverse=True)
        for r in rows:
            self.tbl_dynamic.removeRow(r)

    def on_load_dynamic_json(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load dynamic gestures JSON", "", "JSON (*.json);;All files (*.*)")
        if not path:
            return
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            rows = data.get("dynamic_gestures", [])
            self.tbl_dynamic.setRowCount(0)
            for r in rows:
                self._add_dynamic_row(
                    name=str(r.get("name", "")),
                    sequence=str(r.get("sequence", "")),
                    max_gap=int(r.get("max_gap", 2)),
                    time_window=float(r.get("time_window", 2.0)),
                )
            self.append_log(_tag_line("TRAIN", f"Loaded dynamic gestures: {path}"))
        except Exception as e:
            QMessageBox.critical(self, "Load dynamic gestures", str(e))

    def on_save_dynamic_json(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save dynamic gestures JSON", "dynamic_gestures.json", "JSON (*.json)")
        if not path:
            return
        try:
            rows = []
            for r in range(self.tbl_dynamic.rowCount()):
                name = (self.tbl_dynamic.item(r, 0).text() if self.tbl_dynamic.item(r, 0) else "").strip()
                seq = (self.tbl_dynamic.item(r, 1).text() if self.tbl_dynamic.item(r, 1) else "").strip()
                max_gap = (self.tbl_dynamic.item(r, 2).text() if self.tbl_dynamic.item(r, 2) else "2").strip()
                tw = (self.tbl_dynamic.item(r, 3).text() if self.tbl_dynamic.item(r, 3) else "2.0").strip()
                if not name or not seq:
                    continue
                rows.append({
                    "name": name,
                    "sequence": seq,
                    "max_gap": int(max_gap),
                    "time_window": float(tw),
                })
            Path(path).write_text(json.dumps({"dynamic_gestures": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
            self.append_log(_tag_line("TRAIN", f"Saved dynamic gestures: {path}"))
        except Exception as e:
            QMessageBox.critical(self, "Save dynamic gestures", str(e))

    def on_dynamic_triggered(self, name: str):
        self.lbl_dynamic_result.setText(name.upper())
        self.append_log(_tag_line("DETECT", f"[DYNAMIC] {name}"))

    # =========================
    # Gen Code tab handlers
    # =========================
    def on_gen_browse_meta(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select meta (.pkl)", "", "Pickle (*.pkl);;All files (*.*)")
        if path:
            self.le_gen_meta.setText(path)


    def on_detect_import_csv(self):
        # Default to the known log directory if it exists
        default_path = r"C:\Users\USE\Desktop\SEAN_CODE\mlp_station_git\station_v15\15手勢log"
        if not os.path.exists(default_path):
            default_path = ""
            
        path, _ = QFileDialog.getOpenFileName(self, "Import STD values from CSV (Log)", default_path, "CSV (*.csv);;All files (*.*)")
        if not path:
            return
        
        try:
            with open(path, mode='r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                row = next(reader) # Get first data row
                
                # 1. Manual HOLDAVG (tbl_hold) -> HOLDAVG1-6
                # 2. Gain Map STD_HOLDAVG_A (tbl_hold_a) -> HOLDAVG1-6
                for i in range(6):
                    key = f"HOLDAVG{i+1}"
                    if key in row:
                        val_str = str(int(float(row[key])))
                        self.tbl_hold.setItem(i, 1, QTableWidgetItem(val_str))
                        self.tbl_hold_a.setItem(i, 1, QTableWidgetItem(val_str))
                
                # 3. Gain Map STD_BASELINE_A (tbl_base_a) -> MOVBASE1-6
                for i in range(6):
                    key = f"MOVBASE{i+1}"
                    if key in row:
                        val_str = str(int(float(row[key])))
                        self.tbl_base_a.setItem(i, 1, QTableWidgetItem(val_str))
                        
            self.append_log(_tag_line("DETECT", f"Imported Detect parameters from: {path}"))
            
        except StopIteration:
            QMessageBox.warning(self, "Import CSV", "The CSV file is empty!")
        except Exception as e:
            QMessageBox.critical(self, "Import CSV Error", str(e))



    # -------------------------
    # Detect handlers
    # -------------------------
    def on_browse_model(self):
        filter_str = "Model Files (*.keras *.h5 *.pkl);;Keras V3 (*.keras);;H5 (*.h5);;Pickle (*.pkl);;All files (*.*)"
        path, _ = QFileDialog.getOpenFileName(self, "Select model file", "", filter_str)
        if path:
            self.edit_model.setText(path)

    def on_browse_meta(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select meta (.pkl)", "", "Pickle (*.pkl);;All files (*.*)")
        if path:
            self.edit_meta.setText(path)

    def on_browse_dynamic_json(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select dynamic gestures JSON", "", "JSON (*.json);;All files (*.*)")
        if path:
            self.edit_dynamic_json.setText(path)

    def _read_ch_table_int_map(self, tbl: QTableWidget) -> Dict[int, int]:
        out: Dict[int, int] = {}
        for r in range(tbl.rowCount()):
            ch_item = tbl.item(r, 0)
            v_item = tbl.item(r, 1)
            if not ch_item or not v_item:
                continue
            try:
                ch = int(ch_item.text().strip())
                v = int(float(v_item.text().strip()))
            except Exception:
                continue
            out[ch] = v
        return out

    def _validate_detect_cfg(self, cfg: DetectCfg) -> Optional[str]:
        if not cfg.port:
            return "PORT is empty"
        if not cfg.model_path or not Path(cfg.model_path).exists():
            return f"MODEL_PATH not found: {cfg.model_path}"
        if not cfg.meta_path or not Path(cfg.meta_path).exists():
            return f"META_PATH not found: {cfg.meta_path}"
        if cfg.enable_gain_map and cfg.gain_clamp_min >= cfg.gain_clamp_max:
            return "GAIN_CLAMP min must be < max"
        return None

    def on_detect_start(self):
        if self.thread_detect is not None:
            return

        cfg = DetectCfg(
            port=self.edit_port.text().strip(),
            baud=int(self.combo_baud.currentText()),
            model_path=self.edit_model.text().strip(),
            meta_path=self.edit_meta.text().strip(),
            post_alpha=self.dsb_detect_alpha.value(),
            post_margin=self.dsb_detect_margin.value(),
            post_exit_thresh=self.dsb_detect_exit.value(),
            post_slope_factor=self.dsb_detect_slope.value(), 
            infer_stride=self.sb_detect_stride.value(),
            post_tier_data=self._extract_tier_data_from_ui(self.tbl_detect_tier_base, self.tbl_detect_gestures),
            print_proba=bool(self.chk_print_proba.isChecked()),
            use_manual_holdavg=bool(self.chk_use_manual.isChecked()),
            manual_holdavg=self._read_ch_table_int_map(self.tbl_hold),
            enable_gain_map=bool(self.chk_gain.isChecked()),
            std_baseline_a=self._read_ch_table_int_map(self.tbl_base_a),
            std_holdavg_a=self._read_ch_table_int_map(self.tbl_hold_a),
            min_span_b=float(self.dsb_min_span.value()),
            gain_clamp_min=float(self.dsb_gmin.value()),
            gain_clamp_max=float(self.dsb_gmax.value()),
        )

        err = self._validate_detect_cfg(cfg)
        if err:
            QMessageBox.warning(self, "Detect", err)
            return

        self.stop_event_detect.clear()
        self.btn_detect_stop.setEnabled(True)
        self.append_log(_tag_line("DETECT", "[UI] Starting detection ..."))
        self._set_busy("detect")

        # 傳入 UI 指定的 dynamic_gestures.json 路徑
        self.dynamic_json_path = self.edit_dynamic_json.text().strip() or "dynamic_gestures.json"

        self.thread_detect = QThread()
        self.worker_detect = DetectWorker(cfg, self.stop_event_detect)
        self.worker_detect.dynamic_json_path = self.dynamic_json_path
        self.worker_detect.moveToThread(self.thread_detect)

        self.thread_detect.started.connect(self.worker_detect.run)
        self.worker_detect.log_line.connect(self.append_log)

        self.worker_detect.finished_ok.connect(self.on_detect_ok)
        self.worker_detect.finished_err.connect(self.on_detect_err)

        self.worker_detect.finished_ok.connect(self.thread_detect.quit)
        self.worker_detect.finished_err.connect(self.thread_detect.quit)
        self.thread_detect.finished.connect(self.on_detect_thread_finished)

        self.worker_detect.dynamic_triggered.connect(self.on_dynamic_triggered)
        self.worker_detect.stable_changed.connect(self.lbl_dynamic_result.setText)

        self.thread_detect.start()

    def on_detect_stop(self):
        if self.thread_detect is None:
            return
        self.append_log(_tag_line("DETECT", "[UI] Stop detect requested (disconnect) ..."))
        self.stop_event_detect.set()
        self.btn_detect_stop.setEnabled(False)

    def on_detect_ok(self, res: dict):
        self.append_log(_tag_line("DETECT", "=== DETECT STOPPED ==="))
        for k, v in res.items():
            self.append_log(_tag_line("DETECT", f"{k}: {v}"))

    def on_detect_err(self, err: str):
        self.append_log(_tag_line("DETECT", "=== DETECT ERROR ==="))
        self.append_log(_tag_line("DETECT", err))
        QMessageBox.critical(self, "Detect", err)

    def on_detect_thread_finished(self):
        self.btn_detect_stop.setEnabled(False)
        self.stop_event_detect.clear()
        self.thread_detect = None
        self.worker_detect = None
        self._set_busy(None)

    # -------------------------
    # Build handlers
    # -------------------------
    def on_browse_build_proj(self):
        path = QFileDialog.getExistingDirectory(self, "Select project folder", "")
        if path:
            self.edit_build_proj_dir.setText(path)

    def on_build_start(self):
        if self.thread_build is not None:
            return

        proj_dir = self.edit_build_proj_dir.text().strip()
        if not proj_dir:
            QMessageBox.warning(self, "Build", "Project directory is empty.")
            return

        if not Path(proj_dir).exists():
            QMessageBox.warning(self, "Build", f"Project directory not found: {proj_dir}")
            return

        # 取得 buildtool 目錄（相對於當前腳本）
        build_tool_dir = Path(__file__).parent / "buildtool"
        if not build_tool_dir.exists():
            QMessageBox.warning(self, "Build", f"Build tool directory not found: {build_tool_dir}")
            return

        cfg = BuildCfg(
            proj_dir=proj_dir,
            build_tool_dir=str(build_tool_dir),
            config_name=self.combo_build_cfg.currentText(),
            do_clean=self.chk_build_clean.isChecked()
        )

        self.stop_event_build = threading.Event()
        self.btn_build_stop.setEnabled(True)
        self.append_log(_tag_line("BUILD", f"Starting build ({cfg.config_name})..."))
        self._set_busy("build")
        self.append_log(_tag_line("BUILD", "[UI] Starting build ..."))
        self._set_busy("build")

        self.thread_build = QThread()
        self.worker_build = BuildWorker(cfg, self.stop_event_build)
        self.worker_build.moveToThread(self.thread_build)

        self.thread_build.started.connect(self.worker_build.run)
        self.worker_build.log_line.connect(self.append_log)

        self.worker_build.finished_ok.connect(self.on_build_ok)
        self.worker_build.finished_err.connect(self.on_build_err)

        self.worker_build.finished_ok.connect(self.thread_build.quit)
        self.worker_build.finished_err.connect(self.thread_build.quit)
        self.thread_build.finished.connect(self.on_build_thread_finished)

        self.thread_build.start()

    def on_build_stop(self):
        if self.thread_build is None:
            return
        self.append_log(_tag_line("BUILD", "[UI] Stop build requested ..."))
        self.stop_event_build.set()
        self.btn_build_stop.setEnabled(False)

    def on_build_ok(self, res: dict):
        self.append_log(_tag_line("BUILD", "=== BUILD DONE ==="))
        for k, v in res.items():
            self.append_log(_tag_line("BUILD", f"{k}: {v}"))

    def on_build_err(self, msg: str):
        self.append_log(_tag_line("BUILD", "=== BUILD ERROR ==="))
        self.append_log(_tag_line("BUILD", msg))
        QMessageBox.critical(self, "Build", msg)

    def on_build_thread_finished(self):
        self.btn_build_stop.setEnabled(False)
        self.thread_build = None
        self.worker_build = None
        self._set_busy(None)

    # -------------------------
    # Flash handlers
    # -------------------------
    def on_flash_refresh_ports(self):
        import serial.tools.list_ports
        
        # Check if both UI sets exist
        has_auto = hasattr(self, 'edit_autobuild_flash_port')
        
        current = self.edit_flash_port.currentText()
        self.edit_flash_port.clear()
        if has_auto:
            self.edit_autobuild_flash_port.clear()
        
        # Try to pull from detect tab if available
        detect_port = self.edit_port.text().strip()
        if detect_port:
             self.edit_flash_port.addItem(detect_port)
             if has_auto:
                self.edit_autobuild_flash_port.addItem(detect_port)
             
        # Scan system ports
        ports = serial.tools.list_ports.comports()
        seen = {detect_port} if detect_port else set()
        
        for p in ports:
            name = p.device
            if name not in seen:
                self.edit_flash_port.addItem(name)
                if has_auto:
                    self.edit_autobuild_flash_port.addItem(name)
                seen.add(name)
                
        # Restore selection if possible, else select first
        combos = [self.edit_flash_port]
        if has_auto:
            combos.append(self.edit_autobuild_flash_port)

        for combo in combos:
            idx = combo.findText(current)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            elif combo.count() > 0:
                combo.setCurrentIndex(0)

    def update_srec_path(self):
        proj = self.edit_build_proj_dir.text().strip()
        cfg = self.combo_build_cfg.currentText().strip() or "Debug"
        
        if not proj:
            self.edit_flash_srec.setText("")
            return
            
        # Assumption: output is at <PROJ>/<CFG>/<TARGET>.srec
        srec = Path(proj) / cfg / "glove_mlp_rebuild.srec"
        self.edit_flash_srec.setText(str(srec))
        self.edit_autobuild_flash_srec.setText(str(srec))

    def on_flash_start(self):
        if self.thread_flash is not None:
            return

        # 1. Validation - Get values from source tab
        if self.tabs.currentIndex() == 4: # Auto Build Tab
            srec = self.edit_autobuild_flash_srec.text().strip()
            port = self.edit_autobuild_flash_port.currentText().strip()
        else: # Build Tab or others
            srec = self.edit_flash_srec.text().strip()
            port = self.edit_flash_port.currentText().strip()
        
        if not srec:
            self.update_srec_path() # Try update
            srec = self.edit_flash_srec.text().strip()
            
        if not srec or not Path(srec).exists():
            QMessageBox.warning(self, "Flash", f"SREC file not found or invalid path:\n{srec}\n\nPlease build first.")
            return

        if not port:
            QMessageBox.warning(self, "Flash", "Please select a COM port.")
            return
            
        # 2. Safety Checks (Dialog)
        # 1. J16 Short
        # 2. Power Cycle
        # 3. Reset Pressed
        
        dlg = QDialog(self)
        dlg.setWindowTitle("Pre-Flash Safety Check")
        dlg.resize(400, 250)
        
        l = QVBoxLayout(dlg)
        l.addWidget(QLabel("Please confirm the following before flashing:"))
        
        chk1 = QCheckBox("1. Confirm J16 is SHORTED")
        chk2 = QCheckBox("2. Confirm Board Power Cycled (Re-plugged)")
        chk3 = QCheckBox("3. Confirm Reset Button PRESSED")
        
        # Bigger font for emphasis
        f = chk1.font()
        f.setBold(True)
        f.setPointSize(11)
        chk1.setFont(f); chk2.setFont(f); chk3.setFont(f)
        
        l.addWidget(chk1)
        l.addWidget(chk2)
        l.addWidget(chk3)
        
        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.button(QDialogButtonBox.Ok).setEnabled(False) # check all to enable
        l.addWidget(btn_box)
        
        def check_status():
            ok = chk1.isChecked() and chk2.isChecked() and chk3.isChecked()
            btn_box.button(QDialogButtonBox.Ok).setEnabled(ok)
            
        chk1.stateChanged.connect(check_status)
        chk2.stateChanged.connect(check_status)
        chk3.stateChanged.connect(check_status)
        
        btn_box.accepted.connect(dlg.accept)
        btn_box.rejected.connect(dlg.reject)
        
        if dlg.exec_() != QDialog.Accepted:
            return # Cancelled
            
        # 3. Stop Detect if running
        if self.thread_detect is not None:
            self.append_log(_tag_line("FLASH", "Stopping active detection for flash..."))
            self.on_detect_stop()
        
        # 4. Start Flash Worker
        self._start_flash_worker(srec, port)

    def _start_flash_worker(self, srec, port):
        self.stop_event_flash.clear()
        self.btn_flash_stop.setEnabled(True)
        self.append_log(_tag_line("FLASH", f"Starting Flash on {port}..."))
        self._set_busy("flash")
        
        # BuildTool dir:
        build_tool_dir = Path(__file__).parent / "buildtool"
        
        cfg = FlashCfg(
            srec_path=srec,
            com_port=port,
            tool_dir=str(build_tool_dir)
        )
        
        self.thread_flash = QThread()
        self.worker_flash = FlashWorker(cfg, self.stop_event_flash)
        self.worker_flash.moveToThread(self.thread_flash)
        
        self.thread_flash.started.connect(self.worker_flash.run)
        self.worker_flash.log_line.connect(self.append_log)
        self.worker_flash.finished_ok.connect(self.on_flash_ok)
        self.worker_flash.finished_err.connect(self.on_flash_err)
        self.worker_flash.retry_requested.connect(self.on_flash_retry_requested)
        
        self.worker_flash.finished_ok.connect(self.thread_flash.quit)
        self.worker_flash.finished_err.connect(self.thread_flash.quit)
        self.thread_flash.finished.connect(self.on_flash_thread_finished)
        
        self.thread_flash.start()
        
    def on_flash_stop(self):
        if self.thread_flash is None:
            return
        self.stop_event_flash.set()
        self.btn_flash_stop.setEnabled(False)
        self.append_log(_tag_line("FLASH", "Stop requested..."))

    def on_flash_ok(self, res):
        self.append_log(_tag_line("FLASH", "=== FLASH COMPLETE ==="))
        QMessageBox.information(self, "Flash", "Flash completed successfully!")

    def on_flash_err(self, msg):
        self.append_log(_tag_line("FLASH", "=== FLASH ERROR ==="))
        self.append_log(_tag_line("FLASH", msg))
        QMessageBox.critical(self, "Flash Error", msg)

    def on_flash_retry_requested(self, reason):
        self.append_log(_tag_line("FLASH", f"Retry requested: {reason}"))
        
        # We must explicitly quit the thread here because the worker returned 
        # without emitting finished_ok/err, so the auto-quit connection won't fire.
        if self.thread_flash is not None and self.thread_flash.isRunning():
            self.thread_flash.quit()
            self.thread_flash.wait()
        
        # Pop Dialog
        reply = QMessageBox.question(
            self, 
            "Device Not Responding",
            "Error: Device is not responding (E3000105).\n\n"
            "Please PRESS THE RESET BUTTON on the board.\n"
            "Then click Yes immediately to retry.\n\n"
            "Click No to abort.",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            # Restart immediately via timer
            QTimer.singleShot(500, self.on_flash_restart_trigger)
        else:
            self.on_flash_thread_finished() # Cleanup UI state
            self.append_log(_tag_line("FLASH", "User aborted on retry."))

    def on_flash_restart_trigger(self):
        self.append_log(_tag_line("FLASH", "Retrying flash..."))
        
        # Cleanup previous thread/worker references carefully before creating new ones
        if self.thread_flash is not None:
             if self.thread_flash.isRunning():
                 self.thread_flash.quit()
                 self.thread_flash.wait()
             self.thread_flash = None
        self.worker_flash = None
        
        # Restart worker directly, bypassing the 3-checkbox dialog
        srec = self.edit_flash_srec.text().strip()
        port = self.edit_flash_port.currentText().strip()
        
        # Quick validation again just in case
        if not srec or not port:
            self.append_log(_tag_line("FLASH", "Retry failed: SREC or Port missing"))
            self.on_flash_thread_finished()
            return
            
        self._start_flash_worker(srec, port)

    
    def on_flash_thread_finished(self):
        # Only cleanup if we are not in the middle of a retry restart
        # (But retry logic handles its own cleanup, so this is for normal finishes)
        if self.thread_flash is not None:
            if self.thread_flash.isRunning():
                self.thread_flash.quit()
                self.thread_flash.wait()
        
        self.btn_flash_stop.setEnabled(False)
        self.thread_flash = None
        self.worker_flash = None
        self._set_busy(None)



def main():
    app = QApplication(sys.argv)
    w = MainWindow()

    # --- Robust Log Redirection ---
    # In PyInstaller 'console=False' mode, sys.stdout/stderr are None.
    # We redirect them to the UI terminal only when frozen (packaged).
    if getattr(sys, 'frozen', False):
        # We must keep a reference to prevent garbage collection
        global _redirector
        _redirector = QLogRedirector()
        _redirector.log_signal.connect(w.append_log)
        sys.stdout = _redirector
        sys.stderr = _redirector

    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
