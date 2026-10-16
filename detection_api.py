"""Qt-independent UART and CSV gesture detection operations."""

import csv
import json
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import numpy as np
import serial

import detection_contracts as contracts
import detection_model as detect
import xgboost_detection_model as xgboost_detect


__all__ = [
    "DetectionConfig",
    "DetectionRuntimeState",
    "detection_parse_serial_line",
    "detection_run_serial_from_config",
    "detection_run_csv_from_config",
]


@dataclass
class DetectionConfig:
    """UART 與 CSV Detect 共用的固定輸入；執行期間不應修改。"""
    ########X#########For CNN Use#########################
    ######################################################
    serial_port: str  # UART 裝置名稱，例如 COM6；CSV Replay 不使用。
    baud: int  # UART baud rate；CSV Replay 不使用。
    model_path: str  # Keras／Joblib Model 檔案路徑。
    metadata_path: str  # Training 產生的 Metadata，定義 Model 類型、Channel 與 Feature。

    post_alpha: float  # Probability EWMA 權重，範圍 0～1；越大越偏重最新結果。
    post_margin: float  # 切換 Active Label 時，新候選需領先目前 Label 的最小機率差。
    post_tier_data: dict  # 各 Gesture Tier 的門檻、Stable Frames 與 Class ID 清單。
    post_exit_thresh: float  # Active Label 低於此機率時回到 inactive 狀態。
    post_slope_factor: float  # Metadata 缺少 slope_factor 時使用的推論倍率 fallback。
    infer_stride: int  # UART／CSV 每累積幾筆有效 Raw Data 呼叫一次 predict。
    print_proba: bool  # 是否將各 Class 的預測機率寫入 log_fn。

    use_manual_holdavg: bool  # 缺少即時 Hold 值時，是否允許使用 manual_holdavg。
    manual_holdavg: Dict[int, int]  # Channel ID → 手動 Hold Average Sensor 值。
    enable_gain_map: bool  # 是否依標準裝置與目前裝置的 Span 計算 Channel Gain。
    std_baseline_a: Dict[int, int]  # Channel ID → 標準裝置 Baseline，供 Gain 計算。
    std_holdavg_a: Dict[int, int]  # Channel ID → 標準裝置 Hold Average，供 Gain 計算。
    min_span_b: float  # 目前裝置 Span 小於此值時不更新 Gain，避免除以過小數值。
    gain_clamp_min: float  # Gain 下限，避免輸入被過度縮小。
    gain_clamp_max: float  # Gain 上限，避免雜訊被過度放大。

    dynamic_json_path: str = "dynamic_gestures.json"  # Dynamic Gesture sequence 設定檔。
    use_manual_baseline: bool = False  # MCU 尚未送出 Baseline 時，是否先使用手動值。
    manual_baseline: Dict[int, int] = field(default_factory=dict)  # Channel ID → 手動 Baseline。
    ######################################################
    ########X#########For CNN Use#########################

    # Compatibility aliases are intentionally read-only so one canonical field
    # remains responsible for serialization and new API documentation.
    @property
    def port(self) -> str:
        return self.serial_port

    @property
    def meta_path(self) -> str:
        return self.metadata_path


@dataclass
class DetectionRuntimeState:
    """單次 Detect 執行期間可變的校正與輸入狀態。

    此物件不能跨 run 共用，否則上一台裝置的 baseline、hold 或 gain
    可能污染下一次推論。
    """

    gain_map: Dict[int, float] = field(default_factory=dict)
    gain_ready: bool = False
    current_base_map: Dict[int, int] = field(default_factory=dict)
    current_hold_map: Dict[int, int] = field(default_factory=dict)


@dataclass(frozen=True)
class _DetectionUpdate:
    prediction: contracts.ModelPrediction
    stable_id: int
    stable_name: str
    stable_changed: bool
    dynamic_name: Optional[str]


def detection_parse_serial_line(line: str):
    """解析並驗證 MCU `$SIL...` UART 封包；無效或截斷資料回傳 ``None``。"""

    line = line.strip()
    if not line.startswith("$"):
        return None
    main = line.split("*", 1)[0]
    parts = main.split(",")
    if len(parts) < 5:
        return None

    try:
        message = parts[0][1:]
        count = int(parts[2])
        channel_count = int(parts[3])
        if channel_count < 0 or channel_count > 32:
            return None

        values = []
        for raw_value in parts[4:]:
            raw_value = raw_value.strip()
            if not raw_value:
                continue
            try:
                values.append(int(raw_value))
            except ValueError:
                break

        # 截斷封包不能進入 Runtime State，否則 Channel 會錯位。
        if len(values) < channel_count:
            return None
        return message, count, channel_count, values[:channel_count]
    except (TypeError, ValueError):
        return None


class _DynamicMatcher:
    """Own the time-ordered stable-label state used by dynamic gestures."""

    def __init__(self, gestures: List[dict]):
        self.gestures = gestures
        self.prefix_to_id: Dict[str, int] = {}
        self.reset()

    def set_prefix_to_id(self, id_to_name: Dict[int, str]) -> None:
        self.prefix_to_id = {value.lower(): key for key, value in id_to_name.items()}

    def reset(self) -> None:
        self.buffer: List[int] = []
        self.timestamps: List[float] = []
        self.last_trigger_time = 0.0

    def feed(self, stable_id: int, timestamp: float) -> Optional[str]:
        if timestamp - self.last_trigger_time < 1.0:
            return None
        if not self.buffer or self.buffer[-1] != stable_id:
            self.buffer.append(stable_id)
            self.timestamps.append(timestamp)

        max_window = max((gesture.get("time_window", 2.0) for gesture in self.gestures), default=2.0)
        while self.timestamps and timestamp - self.timestamps[0] > max_window:
            self.buffer.pop(0)
            self.timestamps.pop(0)

        for gesture in sorted(self.gestures, key=lambda item: -len(item["sequence"].split(","))):
            if self._match(gesture, self.buffer):
                self.reset()
                self.last_trigger_time = timestamp
                return gesture["name"]
        return None

    def _resolve_token(self, token: str) -> int:
        token = token.strip()
        return int(token) if token.isdigit() else self.prefix_to_id.get(token.lower(), -1)

    def _match(self, gesture: dict, sequence: List[int]) -> bool:
        target = [self._resolve_token(token) for token in gesture["sequence"].split(",")]
        if -1 in target:
            return False
        max_gap = gesture.get("max_gap", 2)
        time_window = gesture.get("time_window", 2.0)
        for start in range(len(sequence) - len(target) + 1):
            start_time = self.timestamps[start]
            end_time = self.timestamps[start + len(target) - 1]
            if end_time - start_time > time_window:
                continue
            if self._match_with_gap(sequence[start:], target, max_gap):
                return True
        return False

    @staticmethod
    def _match_with_gap(sequence: List[int], target: List[int], max_gap: int) -> bool:
        index = 0
        gaps = 0
        for target_id in target:
            while index < len(sequence) and sequence[index] != target_id:
                index += 1
                gaps += 1
                if gaps > max_gap:
                    return False
            if index >= len(sequence):
                return False
            index += 1
        return True


class _CnnPostProcessor:
    """Own probability smoothing, tier thresholds, and active-label latch state."""

    def __init__(self, config: DetectionConfig, num_classes: int):
        self.alpha = config.post_alpha
        self.margin = config.post_margin
        self.exit_thresh = config.post_exit_thresh
        self.smoothed_probs = np.zeros(num_classes, dtype=np.float32)
        self.active_id = -1
        self.last_best_id = -1
        self.stable_count = 0
        tier_data = config.post_tier_data
        self.priority_ids = set(tier_data.get("priority_ids", []))
        self.restricted_ids = set(tier_data.get("restricted_ids", []))
        self.priority_threshold = tier_data.get("thresh_priority", 0.70)
        self.restricted_threshold = tier_data.get("thresh_restricted", 0.75)
        self.entry_threshold = tier_data.get("thresh_entry", 0.50)
        self.normal_stable_frames = tier_data.get("stable_normal", 10)
        self.restricted_stable_frames = tier_data.get("stable_restricted", 20)

    def update(self, probabilities: List[float]) -> int:
        current = np.array(probabilities, dtype=np.float32)
        if np.sum(self.smoothed_probs) == 0:
            self.smoothed_probs = current
        else:
            self.smoothed_probs = self.alpha * current + (1.0 - self.alpha) * self.smoothed_probs

        best_id = int(np.argmax(self.smoothed_probs))
        best_probability = self.smoothed_probs[best_id]
        if self.active_id != -1 and self.smoothed_probs[self.active_id] < self.exit_thresh:
            self.active_id = -1

        if best_id != self.active_id:
            is_qualified = False
            if best_id in self.priority_ids and best_probability >= self.priority_threshold:
                is_qualified = True
            else:
                self.stable_count = self.stable_count + 1 if best_id == self.last_best_id else 1
                if best_id in self.restricted_ids:
                    is_qualified = (
                        best_probability >= self.restricted_threshold
                        and self.stable_count >= self.restricted_stable_frames
                    )
                elif best_probability >= self.entry_threshold:
                    is_qualified = self.stable_count >= self.normal_stable_frames

            if is_qualified and self.active_id != -1:
                active_probability = self.smoothed_probs[self.active_id]
                is_qualified = best_probability >= active_probability + self.margin
            if is_qualified:
                self.active_id = best_id
                self.stable_count = 0
        else:
            self.stable_count = 0

        self.last_best_id = best_id
        return self.active_id


class _DetectionSession:
    """協調單次 Detect 的共用處理流程。

    UART 與 CSV 都將解析後的 Sensor sample 交給此物件；它負責維護
    Runtime State、更新 Gain、累積 Model Window、控制推論間隔，以及串接
    Stable／Dynamic 後處理。Session 只屬於單次 run，不可跨 run 共用。
    """

    def __init__(
        self,
        config: DetectionConfig,
        detector,
        dynamic_gestures: List[dict],
        runtime_state: DetectionRuntimeState,
        log_fn: Callable[[str], None],
    ):
        self.config = config
        self.detector = detector
        # Runtime State 保存本次操作持續變動的 Base、Hold 與 Gain；固定設定
        # 仍由 DetectionConfig 擁有，避免把執行狀態寫回使用者的 config。
        self.runtime_state = runtime_state
        self.log_fn = log_fn
        # JSON callers commonly provide numeric channel keys as strings. Keep
        # config immutable from the session's perspective and normalize copies.
        self.manual_holdavg = {
            int(key): int(value) for key, value in (config.manual_holdavg or {}).items()
        }
        self.std_baseline_a = {
            int(key): int(value) for key, value in (config.std_baseline_a or {}).items()
        }
        self.std_holdavg_a = {
            int(key): int(value) for key, value in (config.std_holdavg_a or {}).items()
        }
        self.matcher = _DynamicMatcher(dynamic_gestures)
        self.matcher.set_prefix_to_id(detector.id_to_name)
        self.post_processor = (
            _CnnPostProcessor(config, len(detector.id_to_name)) if detector.clf is not None else None
        )
        self.row_counter = 0
        self.last_stable_id = -2

    def update_gain_map(self, force: bool = False) -> bool:
        """依本次 run 的 baseline/hold 更新 gain，不讀寫 module globals。"""

        if not self.config.enable_gain_map:
            return False

        updated = False
        state = self.runtime_state
        for channel in self.detector.channels:
            if channel not in state.current_base_map:
                continue
            if channel in state.current_hold_map:
                hold_value = float(state.current_hold_map[channel])
            elif self.config.use_manual_holdavg and channel in self.manual_holdavg:
                hold_value = float(self.manual_holdavg[channel])
            else:
                continue

            span_input = abs(hold_value - float(state.current_base_map[channel]))
            if span_input < self.config.min_span_b:
                continue
            span_reference = float(
                self.std_holdavg_a.get(channel, 0)
                - self.std_baseline_a.get(channel, 0)
            )
            if span_reference <= 1.0:
                continue

            raw_gain = span_reference / span_input
            new_gain = max(self.config.gain_clamp_min, min(self.config.gain_clamp_max, raw_gain))
            old_gain = state.gain_map.get(channel, 1.0)
            if force or abs(new_gain - old_gain) > 0.02:
                state.gain_map[channel] = new_gain
                updated = True

        if updated:
            state.gain_ready = True
            self.log_fn(f"[GAIN] Updated Coarse: {state.gain_map}")
        return updated

    def process_sample(
        self,
        row_map: Dict[int, int],
        base_map: Dict[int, int],
        hold_map: Dict[int, int],
        timestamp: float,
        apply_config_stride: bool,
    ) -> Optional[_DetectionUpdate]:
        """處理一筆完整 sample，並在符合推論條件時回傳 Detection Update。

        每筆有效資料都會先更新 Runtime State 並送入 Model Window；
        ``infer_stride`` 只控制呼叫 predict() 的頻率，不會丟棄 Sensor sample。
        """

        # Model 使用的每個 Channel 都必須同時具備 Row 與 Baseline，否則這筆
        # 資料無法正規化，也不能安全放入 Model Window。
        if any(channel not in row_map or channel not in base_map for channel in self.detector.channels):
            return None

        state = self.runtime_state
        state.current_base_map.update(base_map)
        state.current_hold_map.update(hold_map)
        effective_hold = dict(state.current_hold_map)
        if self.config.use_manual_holdavg:
            for channel in self.detector.channels:
                if channel not in effective_hold and channel in self.manual_holdavg:
                    effective_hold[channel] = self.manual_holdavg[channel]

        state.current_hold_map.update(effective_hold)
        # Gain 必須在 push_data() 前更新，確保這一筆資料與之後的 predict()
        # 使用同一份校正狀態。
        self.update_gain_map()
        self.detector.push_data(row_map, state.current_base_map, effective_hold, state.gain_map)

        # Stride 僅延後推論；上面的 push_data() 仍會接收每一筆有效輸入。
        self.row_counter += 1
        if apply_config_stride and self.row_counter % max(1, self.config.infer_stride) != 0:
            return None

        prediction = self.detector.predict(state.gain_map)
        if prediction is None:
            return None

        stable_id = self.post_processor.update(prediction.probabilities) if self.post_processor else -1
        stable_name = (
            self.detector.id_to_name.get(stable_id, str(stable_id)) if stable_id != -1 else "convert"
        )
        stable_changed = stable_id != self.last_stable_id
        if stable_changed:
            self.last_stable_id = stable_id

        # UART historically records the transition back to the inactive label;
        # CSV now follows the same rule so both sources match the same sequence.
        should_feed_matcher = stable_changed or stable_id != -1
        dynamic_name = self.matcher.feed(stable_id, timestamp) if should_feed_matcher else None
        return _DetectionUpdate(
            prediction=prediction,
            stable_id=stable_id,
            stable_name=stable_name,
            stable_changed=stable_changed,
            dynamic_name=dynamic_name,
        )


def _detection_load_dynamic_gestures(path_text: str) -> List[dict]:
    try:
        path = Path(path_text)
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            return data.get("dynamic_gestures", [])
    except Exception:
        pass
    return [{"name": "NICE", "sequence": "ok,peace", "max_gap": 2, "time_window": 2.0}]


def _detection_format_exception(exc: Exception) -> str:
    """保留例外類型，避免 UI 只顯示無法判讀的數字訊息。"""

    return f"{type(exc).__name__}: {exc!r}"


def _detection_initial_base_map(
    config: DetectionConfig,
    fallback: Optional[Dict[int, int]] = None,
) -> Dict[int, int]:
    """建立本次 Detect 的初始 Baseline。

    手動 Baseline 是目前裝置的暫時輸入，不與 Gain Map 的
    STD_BASELINE_A（標準裝置參考值）共用設定。
    """

    source = config.manual_baseline if config.use_manual_baseline else (fallback or {})
    return {int(channel): int(value) for channel, value in source.items()}


def _detection_apply_uart_baseline(
    config: DetectionConfig,
    runtime_state: DetectionRuntimeState,
    channel_count: int,
    values: List[int],
) -> bool:
    """依 Enable 選項決定 Baseline 來源。

    啟用手動 Baseline 時固定使用 Config 值，不讓 UART 資料覆寫；
    未啟用時才將 SILBASEEXT／SILMOVBASE 寫入 Runtime State。
    """

    if config.use_manual_baseline:
        return False
    for index in range(min(int(channel_count), len(values))):
        runtime_state.current_base_map[index + 1] = values[index]
    return True


def _detection_resolve_model_path(config: DetectionConfig, log_fn: Callable[[str], None]) -> str:
    """依 metadata 修正 CNN 副檔名，但不改動 config 或 module globals。"""

    resolved_model_path = config.model_path
    try:
        # XGBoost 使用 labels JSON，不是 joblib metadata；不需要 CNN 副檔名修正。
        if _detection_is_xgboost_metadata(config.metadata_path):
            return resolved_model_path
        if Path(config.metadata_path).exists():
            import joblib

            metadata = joblib.load(config.metadata_path)
            if metadata.get("model_type") == "cnn" and resolved_model_path.endswith(".pkl"):
                model_path = Path(resolved_model_path)
                candidates = (
                    model_path.with_suffix(".keras"),
                    model_path.parent.parent / model_path.name.replace(".pkl", ".keras"),
                )
                matching_path = next((path for path in candidates if path.exists()), None)
                if matching_path is not None:
                    resolved_model_path = str(matching_path)
                    log_fn(f"[FIX] Auto-switching CNN model path to: {matching_path}")
                else:
                    log_fn("[WARN] Meta uses CNN but no matching .keras model was found.")
    except Exception as exc:
        log_fn(f"[WARN] Failed to pre-check model path: {exc}")
    return resolved_model_path


def _detection_is_xgboost_metadata(metadata_path: str) -> bool:
    """只依 XGBoost labels JSON 選擇獨立的偵測模型，避免誤判其他 JSON。"""

    path = Path(metadata_path)
    if path.suffix.lower() != ".json" or not path.exists():
        return False
    try:
        metadata = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return all(key in metadata for key in ("labels", "channels", "window_len", "feature_names"))


def _detection_create_detector(config: DetectionConfig, model_path: str):
    """依 metadata 建立 CNN／MLP 或獨立 XGBoost detector。"""

    detector_type = (
        xgboost_detect.XGBoostRealtimeGestureDetector
        if _detection_is_xgboost_metadata(config.metadata_path)
        else detect.RealtimeGestureDetector
    )
    return detector_type(
        model_path=model_path,
        metadata_path=config.metadata_path,
        slope_factor=config.post_slope_factor,
        manual_holdavg=config.manual_holdavg,
    )


def _detection_emit_result_update(
    update: _DetectionUpdate,
    detector,
    log_fn: Callable[[str], None],
    stable_fn: Optional[Callable[[str], None]],
    dynamic_fn: Optional[Callable[[str], None]],
    prediction_fn: Optional[Callable[[contracts.ModelPrediction], None]],
    print_proba: bool,
    log_prefix: str,
    row_index: Optional[int] = None,
) -> None:
    """將 Model 原始輸出與 API 後處理結果送到各自的 callback。"""

    if prediction_fn:
        prediction_fn(update.prediction)

    if update.stable_changed and stable_fn:
        stable_fn(update.stable_name)
    if update.dynamic_name:
        log_fn(f"[DYNAMIC] {update.dynamic_name}")
        if dynamic_fn:
            dynamic_fn(update.dynamic_name)

    prediction = update.prediction
    pred_name = detector.id_to_name.get(prediction.pred_id, str(prediction.pred_id))
    if print_proba or log_prefix == "CSV_PRED":
        top_ids = sorted(
            range(len(prediction.probabilities)),
            key=lambda index: prediction.probabilities[index],
            reverse=True,
        )[:5]
        top = " | ".join(
            f"{detector.id_to_name.get(index, str(index))}:{prediction.probabilities[index]:.2f}"
            for index in top_ids
        )
        row_text = f" row={row_index}" if row_index is not None else ""
        log_fn(
            f"[{log_prefix}]{row_text} pred={pred_name} ({prediction.confidence:.2f}) "
            f"-> {update.stable_name} | {top}"
        )
    elif update.stable_changed:
        log_fn(f"[STABLE] {update.stable_name}")


def detection_run_serial_from_config(
    config: DetectionConfig,
    log_fn: Optional[Callable[[str], None]] = None,
    stable_fn: Optional[Callable[[str], None]] = None,
    dynamic_fn: Optional[Callable[[str], None]] = None,
    stop_event=None,
    prediction_fn: Optional[Callable[[contracts.ModelPrediction], None]] = None,
) -> contracts.DetectionResult:
    """Run UART detection and emit each valid raw model result once.

    ``prediction_fn`` receives only ``ModelPrediction``; label mapping, stable
    state, and dynamic matching remain API-owned outputs. The serial resource is
    always closed before this operation returns.
    """

    effective_log = log_fn or print
    serial_handle = None
    try:
        model_path = _detection_resolve_model_path(config, effective_log)
        effective_log("--- Detect started ---")
        effective_log(f"Port: {config.serial_port}, Baud: {config.baud}")
        effective_log(f"Model: {model_path}")
        effective_log(f"Meta : {config.metadata_path}")

        detector = _detection_create_detector(config, model_path)
        runtime_state = DetectionRuntimeState(
            gain_map={int(channel): 1.0 for channel in detector.channels},
            current_base_map=_detection_initial_base_map(config),
        )
        session = _DetectionSession(
            config,
            detector,
            _detection_load_dynamic_gestures(config.dynamic_json_path),
            runtime_state,
            effective_log,
        )
        serial_handle = serial.Serial(config.serial_port, int(config.baud), timeout=0.1)
        serial_handle.reset_input_buffer()
        effective_log("Serial opened & Buffer reset.")
        if runtime_state.current_base_map:
            effective_log(
                "[INIT] Manual baseline enabled; SILBASEEXT/SILMOVBASE updates are ignored."
            )
        else:
            effective_log("[INIT] Waiting for dynamic baseline from SILBASEEXT/SILMOVBASE.")

        channel_error_logged = False
        while stop_event is None or not stop_event.is_set():
            try:
                line = serial_handle.readline().decode(errors="ignore").strip()
            except Exception as exc:
                # A broken serial stream cannot recover by retrying the same
                # handle forever; fail the operation so finally can close it.
                raise RuntimeError(f"Serial read failed: {exc}") from exc
            if not line:
                continue

            try:
                parsed = detection_parse_serial_line(line)
                if parsed is None:
                    continue
                message, count, channel_count, values = parsed
                if message.startswith(("SILMOVBASE", "SILBASEEXT")):
                    _detection_apply_uart_baseline(
                        config,
                        runtime_state,
                        channel_count,
                        values,
                    )
                elif message.startswith(("SILHOLD", "SILHOLDAVG")):
                    for index in range(min(int(channel_count), len(values))):
                        runtime_state.current_hold_map[index + 1] = values[index]
                    effective_log(
                        f"[HOLD] Received {message} cnt={count}, "
                        f"current_hold_map={runtime_state.current_hold_map}"
                    )
                elif message.startswith(("SILROWDATA", "SILROW", "SILINO")):
                    if not runtime_state.current_base_map:
                        continue
                    row_map = {index + 1: values[index] for index in range(min(int(channel_count), len(values)))}
                    missing = [channel for channel in detector.channels if channel not in row_map]
                    if missing:
                        if not channel_error_logged:
                            channel_error_logged = True
                            effective_log(
                                f"[INPUT_ERR] Model channels={detector.channels}, "
                                f"received channels={sorted(row_map)}, missing={missing}"
                            )
                        continue
                    update = session.process_sample(
                        row_map,
                        runtime_state.current_base_map,
                        runtime_state.current_hold_map,
                        time.time(),
                        apply_config_stride=True,
                    )
                    if update:
                        _detection_emit_result_update(
                            update,
                            detector,
                            effective_log,
                            stable_fn,
                            dynamic_fn,
                            prediction_fn,
                            config.print_proba,
                            "PRED",
                        )
            except Exception as exc:
                effective_log(f"[PRED_ERR] {exc}")

        return contracts.DetectionResult(
            status="cancelled",
            source="serial",
            message="Detection cancelled by user.",
            payload={"stopped": True},
        )
    except Exception as exc:
        message = _detection_format_exception(exc)
        effective_log(f"[DETECT_ERR] {message}")
        return contracts.DetectionResult(status="failed", source="serial", message=message)
    finally:
        # Serial ownership belongs to this operation, including exception paths.
        if serial_handle is not None:
            try:
                serial_handle.close()
            except Exception:
                pass


def _detection_parse_csv_channel_map(row: dict, prefix: str, channels: List[int]) -> Dict[int, int]:
    """依 model channel 順序解析一組 CSV 欄位，缺少的 channel 留給 session 驗證。"""

    values: Dict[int, int] = {}
    for channel in channels:
        raw = str(row.get(f"{prefix}{channel}", "")).strip()
        if raw:
            values[channel] = int(float(raw))
    return values


def detection_run_csv_from_config(
    config: DetectionConfig,
    csv_path: str,
    log_fn: Optional[Callable[[str], None]] = None,
    stable_fn: Optional[Callable[[str], None]] = None,
    dynamic_fn: Optional[Callable[[str], None]] = None,
    stop_event=None,
    prediction_fn: Optional[Callable[[contracts.ModelPrediction], None]] = None,
) -> contracts.DetectionResult:
    """Replay CSV data with the same stride and raw model contract used by UART.

    Rows that do not produce a model prediction do not invoke ``prediction_fn``.
    Every valid row still enters the rolling Model Buffer before stride gating.
    """

    effective_log = log_fn or print
    try:
        model_path = _detection_resolve_model_path(config, effective_log)
        effective_log("--- CSV replay detect started ---")
        effective_log(f"CSV  : {csv_path}")
        effective_log(f"Model: {model_path}")
        effective_log(f"Meta : {config.metadata_path}")

        detector = _detection_create_detector(config, model_path)
        runtime_state = DetectionRuntimeState(
            gain_map={int(channel): 1.0 for channel in detector.channels},
            # CSV 保留舊的 STD fallback；只有明確啟用手動值才優先使用。
            current_base_map=_detection_initial_base_map(config, config.std_baseline_a),
            current_hold_map={
                int(key): int(value) for key, value in config.std_holdavg_a.items()
            },
        )
        if config.use_manual_holdavg:
            runtime_state.current_hold_map.update(
                {int(key): int(value) for key, value in config.manual_holdavg.items()}
            )
        session = _DetectionSession(
            config,
            detector,
            _detection_load_dynamic_gestures(config.dynamic_json_path),
            runtime_state,
            effective_log,
        )

        prefix = Path(csv_path).stem.split("-", 1)[0].strip()
        expected_id = int(prefix) if prefix.lstrip("-").isdigit() else None
        if expected_id is not None:
            expected_name = detector.id_to_name.get(expected_id, str(expected_id))
            effective_log(f"[CSV] Expected label from filename: {expected_id} ({expected_name})")
        else:
            effective_log("[CSV] Filename prefix is not numeric; skipping expected-label check.")

        if config.enable_gain_map and runtime_state.current_base_map:
            session.update_gain_map(force=True)

        prediction_count = 0
        raw_counts: Counter = Counter()
        stable_counts: Counter = Counter()
        with open(csv_path, mode="r", encoding="utf-8") as csv_file:
            for row_index, row in enumerate(csv.DictReader(csv_file), start=1):
                if stop_event is not None and stop_event.is_set():
                    return contracts.DetectionResult(
                        status="cancelled",
                        source="csv",
                        message="Detection cancelled by user.",
                        payload={"csv_path": csv_path, "expected_id": expected_id, "num_predictions": prediction_count},
                    )

                row_map = _detection_parse_csv_channel_map(row, "ROWCH", detector.channels)
                if len(row_map) < len(detector.channels):
                    continue
                base_map = _detection_parse_csv_channel_map(row, "MOVBASE", detector.channels)
                hold_map = _detection_parse_csv_channel_map(row, "HOLDAVG", detector.channels)
                if base_map:
                    runtime_state.current_base_map.update(base_map)
                if hold_map:
                    runtime_state.current_hold_map.update(hold_map)
                if not runtime_state.current_base_map:
                    continue

                update = session.process_sample(
                    row_map,
                    runtime_state.current_base_map,
                    runtime_state.current_hold_map,
                    time.time(),
                    apply_config_stride=True,
                )
                if not update:
                    continue
                prediction_count += 1
                raw_counts[update.prediction.pred_id] += 1
                if update.stable_id != -1:
                    stable_counts[update.stable_id] += 1
                _detection_emit_result_update(
                    update,
                    detector,
                    effective_log,
                    stable_fn,
                    dynamic_fn,
                    prediction_fn,
                    config.print_proba,
                    "CSV_PRED",
                    row_index=row_index,
                )

        payload: Dict[str, Any] = {
            "csv_path": csv_path,
            "expected_id": expected_id,
            "num_predictions": prediction_count,
        }
        if raw_counts:
            best_id, best_count = raw_counts.most_common(1)[0]
            payload.update(
                top_raw_id=best_id,
                top_raw_name=detector.id_to_name.get(best_id, str(best_id)),
                top_raw_count=best_count,
            )
        if stable_counts:
            best_id, best_count = stable_counts.most_common(1)[0]
            payload.update(
                top_stable_id=best_id,
                top_stable_name=detector.id_to_name.get(best_id, str(best_id)),
                top_stable_count=best_count,
            )
        return contracts.DetectionResult(status="completed", source="csv", payload=payload)
    except Exception as exc:
        message = _detection_format_exception(exc)
        effective_log(f"[DETECT_ERR] {message}")
        return contracts.DetectionResult(status="failed", source="csv", message=message)
