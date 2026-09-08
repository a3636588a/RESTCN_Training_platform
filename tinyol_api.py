"""UI-independent operations for the PC TinyOL proof of concept."""

from __future__ import annotations

import csv
import json
import re
import threading
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

import joblib
import numpy as np
import pandas as pd
import serial
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score, recall_score
from sklearn.model_selection import train_test_split

import training_cnn as cnn_trainer


LogFn = Optional[Callable[[str], None]]
ProgressFn = Optional[Callable[[int], None]]


class TinyOlCancelledError(RuntimeError):
    """Raised when the caller requests cancellation before an operation finishes."""


@dataclass(frozen=True)
class TinyOlRecordConfig:
    """Fixed UART and window settings for one TinyOL target recording."""

    serial_port: str
    baud: int
    output_dir: str
    session_id: str
    segment_index: int
    target_id: int
    target_name: str
    record_samples: int
    start_offset: int
    window_len: int
    channels: List[int]
    use_manual_holdavg: bool
    manual_holdavg: Dict[int, int]
    std_baseline_a: Dict[int, int]
    std_holdavg_a: Dict[int, int]


@dataclass(frozen=True)
class TinyOlTrainConfig:
    """Model and dataset settings for one PC TinyOL head update."""

    model_path: str
    metadata_path: str
    output_dir: str
    session_id: str
    target_id: int
    target_name: str
    slope_factor: float
    batch_size: int
    epochs: int
    learning_rate: float
    channels: List[int] = field(default_factory=list)
    target_window_csvs: List[str] = field(default_factory=list)
    replay_window_csvs: List[str] = field(default_factory=list)


def _tinyol_log(log_fn: LogFn, message: str) -> None:
    if log_fn is not None:
        log_fn(message)


def tinyol_validate_record_config(config: TinyOlRecordConfig) -> List[str]:
    """Return validation messages without opening UART or creating files."""

    issues: List[str] = []
    if not config.serial_port:
        issues.append("TinyOL PORT is empty")
    if not config.output_dir:
        issues.append("TinyOL output dir is empty")
    if config.start_offset < 0:
        issues.append("TinyOL start offset must be >= 0")
    if config.window_len <= 0:
        issues.append("TinyOL window_len must be > 0")
    required_rows = config.start_offset + config.window_len
    if config.record_samples < required_rows:
        issues.append(f"record_samples must be >= start_offset + window_len ({required_rows})")
    return issues


def tinyol_record_from_config(
    config: TinyOlRecordConfig,
    log_fn: LogFn = None,
    progress_fn: ProgressFn = None,
    stop_event: Optional[threading.Event] = None,
) -> dict:
    """Capture one UART segment and return paths for its raw and window CSV files."""

    issues = tinyol_validate_record_config(config)
    if issues:
        raise ValueError(issues[0])
    effective_stop = stop_event or threading.Event()
    output_dir = Path(config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    rows: List[dict] = []
    current_base_map = dict(config.std_baseline_a or {})
    current_hold_map = dict(config.std_holdavg_a or {})
    effective_channels = [int(channel) for channel in (config.channels or [])]
    if config.use_manual_holdavg:
        for channel, value in (config.manual_holdavg or {}).items():
            current_hold_map.setdefault(int(channel), int(value))

    serial_handle = serial.Serial(config.serial_port, config.baud, timeout=0.1)
    try:
        serial_handle.reset_input_buffer()
        _tinyol_log(log_fn, f"UART record opened: {config.serial_port} @ {config.baud}")
        while not effective_stop.is_set():
            line = serial_handle.readline().decode(errors="ignore").strip()
            if not line:
                continue
            # Keep the serial grammar shared with Detection so firmware frames are interpreted once.
            import detection_api

            parsed = detection_api.detection_parse_serial_line(line)
            if parsed is None:
                continue
            message, _, channel_count_raw, values = parsed
            channel_count = min(int(channel_count_raw), len(values))
            if effective_channels:
                channel_count = min(channel_count, len(effective_channels))
            if message.startswith("SILMOVBASE"):
                for index in range(channel_count):
                    channel = effective_channels[index] if effective_channels else index + 1
                    current_base_map[channel] = int(values[index])
                continue
            if message.startswith("SILHOLD") or message.startswith("SILHOLDAVG"):
                for index in range(channel_count):
                    channel = effective_channels[index] if effective_channels else index + 1
                    current_hold_map[channel] = int(values[index])
                continue
            if not message.startswith(("SILROWDATA", "SILROW", "SILINO")) or not current_base_map:
                continue
            row = {"SEQ": len(rows), "GESTURE": config.target_name, "TARGET_ID": config.target_id}
            for index in range(channel_count):
                channel = effective_channels[index] if effective_channels else index + 1
                row[f"ROWCH{channel}"] = int(values[index])
                row[f"MOVBASE{channel}"] = int(current_base_map.get(channel, 0))
                row[f"HOLDAVG{channel}"] = int(current_hold_map.get(channel, 0))
            rows.append(row)
            if progress_fn is not None:
                progress_fn(len(rows))
            if len(rows) >= config.record_samples:
                _tinyol_log(log_fn, f"Reached target samples: {len(rows)}")
                break
    finally:
        serial_handle.close()

    if not rows:
        if effective_stop.is_set():
            raise TinyOlCancelledError("TinyOL recording cancelled before any row was captured.")
        raise RuntimeError("No UART rows captured.")

    export_channels = effective_channels or sorted(current_base_map) or sorted(current_hold_map)
    fieldnames = (["SEQ"] + [f"ROWCH{i}" for i in export_channels]
                  + [f"MOVBASE{i}" for i in export_channels]
                  + [f"HOLDAVG{i}" for i in export_channels] + ["GESTURE", "TARGET_ID"])
    raw_path = output_dir / f"{config.session_id}_target_raw_{config.segment_index:03d}.csv"
    with raw_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    start = int(config.start_offset)
    end = start + int(config.window_len)
    window_path: Optional[Path] = None
    if len(rows) >= end:
        window_path = output_dir / f"{config.session_id}_target_window_{config.segment_index:03d}.csv"
        with window_path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows[start:end])
        _tinyol_log(log_fn, f"Extracted target window rows[{start}:{end}]")

    return {
        "raw_csv": str(raw_path),
        "window_csv": str(window_path) if window_path else "",
        "rows": len(rows),
        "window_start": start,
        "window_len": int(config.window_len),
    }


def _tinyol_load_window_csv(path: str, slope_factor: float, label_id: int, channels_hint: List[int]):
    frame = pd.read_csv(path)
    channels = [int(channel) for channel in channels_hint if all(
        f"{prefix}{int(channel)}" in frame.columns for prefix in ("ROWCH", "MOVBASE", "HOLDAVG")
    )]
    if not channels:
        channels = sorted({int(re.sub(r"\D", "", name)) for name in frame.columns if name.startswith("ROWCH")})
    if not channels:
        raise RuntimeError(f"No ROWCH columns found in {path}")
    signals = []
    for channel in channels:
        row = frame[f"ROWCH{channel}"].to_numpy(dtype=np.float32)
        base = frame[f"MOVBASE{channel}"].to_numpy(dtype=np.float32)
        hold = frame[f"HOLDAVG{channel}"].to_numpy(dtype=np.float32)
        signals.append((row - base) / np.maximum(np.abs(hold - base), 1.0))
    signal = np.stack(signals, axis=1)
    delta = np.zeros_like(signal)
    delta[1:] = np.diff(signal, axis=0) * float(slope_factor)
    waveform = np.concatenate([signal, delta], axis=1)[np.newaxis, :, :].astype(np.float32)
    variance = np.var(signal, axis=0, keepdims=True).astype(np.float32)
    mean = np.mean(signal, axis=0, keepdims=True).astype(np.float32)
    return waveform, variance, mean, np.array([label_id], dtype=np.int32)


def _tinyol_build_dataset(config: TinyOlTrainConfig):
    metadata = joblib.load(config.metadata_path)
    id_to_name = metadata.get("id_to_name", {})
    name_to_id = {str(name): int(class_id) for class_id, name in id_to_name.items()}
    waveforms, variances, means, labels, sources, roles = [], [], [], [], [], []
    for path in config.target_window_csvs:
        parts = _tinyol_load_window_csv(path, config.slope_factor, config.target_id, config.channels)
        for bucket, value in zip((waveforms, variances, means, labels), parts):
            bucket.append(value)
        sources.append({"path": path, "label_id": config.target_id, "role": "target"})
        roles.append("target")
    for path in config.replay_window_csvs:
        header = pd.read_csv(path, nrows=1)
        label_id = None
        if "TARGET_ID" in header.columns:
            try:
                label_id = int(header.iloc[0]["TARGET_ID"])
            except (TypeError, ValueError):
                pass
        if label_id is None and "GESTURE" in header.columns:
            label_id = name_to_id.get(str(header.iloc[0]["GESTURE"]), config.target_id)
        if label_id is None:
            raise RuntimeError(f"Cannot determine label id for replay window: {path}")
        parts = _tinyol_load_window_csv(path, config.slope_factor, label_id, config.channels)
        for bucket, value in zip((waveforms, variances, means, labels), parts):
            bucket.append(value)
        sources.append({"path": path, "label_id": label_id, "role": "replay"})
        roles.append("replay")
    if not waveforms:
        raise RuntimeError("No TinyOL dataset windows available.")
    arrays = tuple(np.concatenate(items, axis=0) for items in (waveforms, variances, means, labels))
    return metadata, *arrays, sources, np.asarray(roles, dtype=object)


def _tinyol_select_trainable_head(model) -> List[str]:
    dense_layers = [layer for layer in model.layers if layer.__class__.__name__ == "Dense"]
    if len(dense_layers) < 2:
        raise RuntimeError("Model does not have enough Dense layers for TinyOL head update.")
    names = {dense_layers[-1].name, dense_layers[-2].name}
    for layer in model.layers:
        layer.trainable = layer.name in names
    return sorted(names)


def tinyol_train_from_config(
    config: TinyOlTrainConfig,
    log_fn: LogFn = None,
    stop_event: Optional[threading.Event] = None,
) -> dict:
    """Fine-tune the final two Dense layers and return the base/candidate comparison."""

    if stop_event is not None and stop_event.is_set():
        raise TinyOlCancelledError("TinyOL training cancelled before start.")
    metadata, waveform, variance, mean, labels, sources, roles = _tinyol_build_dataset(config)
    num_classes = int(metadata.get("num_classes", len(metadata.get("id_to_name", {}))))
    indices = np.arange(len(labels))
    counts = Counter(labels.tolist())
    split_mode = "reuse-train-as-eval"
    train_indices = eval_indices = indices
    if len(labels) >= 8 and all(count >= 2 for count in counts.values()):
        try:
            train_indices, eval_indices = train_test_split(indices, test_size=0.25, random_state=42, stratify=labels)
            train_indices, eval_indices, split_mode = np.asarray(train_indices), np.asarray(eval_indices), "stratified"
        except ValueError:
            pass
    _tinyol_log(log_fn, f"Dataset windows: total={len(labels)} train={len(train_indices)} eval={len(eval_indices)} mode={split_mode}")

    model = cnn_trainer.tf.keras.models.load_model(config.model_path, compile=False)
    trainable_names = _tinyol_select_trainable_head(model)
    _tinyol_log(log_fn, f"Trainable Dense layers: {', '.join(trainable_names)}")
    model.compile(
        optimizer=cnn_trainer.tf.keras.optimizers.SGD(learning_rate=float(config.learning_rate)),
        loss=cnn_trainer.tf.keras.losses.CategoricalCrossentropy(),
        metrics=["accuracy"],
    )
    target_mask = roles[train_indices] == "target"
    target_count = int(np.sum(target_mask))
    replay_count = int(len(train_indices) - target_count)
    oversample = min(8, max(1, int(np.ceil(replay_count / max(target_count, 1)))))
    expanded = np.asarray(train_indices, dtype=np.int32)
    sample_weight = np.ones(len(expanded), dtype=np.float32)
    if target_count and replay_count > target_count:
        target_indices = train_indices[target_mask]
        replay_indices = train_indices[~target_mask]
        expanded = np.concatenate([replay_indices] + [target_indices] * oversample).astype(np.int32)
        sample_weight = np.ones(len(expanded), dtype=np.float32)
        sample_weight[len(replay_indices):] = 2.0
    _tinyol_log(log_fn, f"Train mix: target={target_count} replay={replay_count} oversample={oversample} expanded_train={len(expanded)}")
    _tinyol_log(log_fn, f"Train config: epochs={config.epochs} batch={config.batch_size} lr={config.learning_rate:.6f}")

    history = model.fit(
        [waveform[expanded], variance[expanded], mean[expanded]],
        cnn_trainer.tf.keras.utils.to_categorical(labels[expanded], num_classes),
        validation_data=(
            [waveform[eval_indices], variance[eval_indices], mean[eval_indices]],
            cnn_trainer.tf.keras.utils.to_categorical(labels[eval_indices], num_classes),
        ),
        sample_weight=sample_weight,
        batch_size=int(config.batch_size),
        epochs=int(config.epochs),
        verbose=0,
    )
    history_data = history.history
    for epoch_index in range(len(history_data.get("loss", []))):
        _tinyol_log(log_fn, f"Epoch {epoch_index + 1}/{config.epochs} | loss={history_data['loss'][epoch_index]:.4f} acc={history_data['accuracy'][epoch_index]:.4f} val_loss={history_data['val_loss'][epoch_index]:.4f} val_acc={history_data['val_accuracy'][epoch_index]:.4f}")

    base_model = cnn_trainer.tf.keras.models.load_model(config.model_path, compile=False)
    model_inputs = [waveform[eval_indices], variance[eval_indices], mean[eval_indices]]
    base_predictions = np.argmax(base_model.predict(model_inputs, verbose=0), axis=1)
    candidate_predictions = np.argmax(model.predict(model_inputs, verbose=0), axis=1)
    true_labels = labels[eval_indices]
    output_dir = Path(config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    candidate_path = output_dir / f"{config.session_id}_tinyol.keras"
    model.save(candidate_path)

    class_ids = list(range(num_classes))
    recall_base = recall_score(true_labels, base_predictions, labels=class_ids, average=None, zero_division=0)
    recall_new = recall_score(true_labels, candidate_predictions, labels=class_ids, average=None, zero_division=0)
    f1_base = f1_score(true_labels, base_predictions, labels=class_ids, average=None, zero_division=0)
    f1_new = f1_score(true_labels, candidate_predictions, labels=class_ids, average=None, zero_division=0)
    target_id = int(config.target_id)
    accuracy_base = accuracy_score(true_labels, base_predictions)
    accuracy_new = accuracy_score(true_labels, candidate_predictions)
    non_target_ids = [class_id for class_id in class_ids if class_id != target_id]
    recall_delta = float(recall_new[target_id] - recall_base[target_id])
    f1_delta = float(f1_new[target_id] - f1_base[target_id])
    accuracy_delta = float(accuracy_new - accuracy_base)
    worst_recall_delta = min((float(recall_new[i] - recall_base[i]) for i in non_target_ids), default=0.0)
    mean_f1_delta = float(np.mean([f1_new[i] - f1_base[i] for i in non_target_ids])) if non_target_ids else 0.0
    passed = ((recall_delta >= 0.05 or f1_delta >= 0.03) and accuracy_delta >= -0.01
              and worst_recall_delta >= -0.03 and mean_f1_delta >= -0.02)
    report = {
        "target_recall_base": float(recall_base[target_id]), "target_recall_new": float(recall_new[target_id]),
        "target_recall_delta": recall_delta, "target_f1_base": float(f1_base[target_id]),
        "target_f1_new": float(f1_new[target_id]), "target_f1_delta": f1_delta,
        "overall_acc_base": float(accuracy_base), "overall_acc_new": float(accuracy_new),
        "overall_acc_delta": accuracy_delta, "worst_non_target_recall_delta": worst_recall_delta,
        "mean_non_target_f1_delta": mean_f1_delta, "decision": "PASS" if passed else "REJECT",
        "split_mode": split_mode, "target_train_count": target_count, "replay_train_count": replay_count,
        "target_oversample_factor": oversample, "expanded_train_count": int(len(expanded)),
        "candidate_model_path": str(candidate_path), "trainable_dense_layers": trainable_names,
        "confusion_matrix_base": confusion_matrix(true_labels, base_predictions, labels=class_ids).tolist(),
        "confusion_matrix_new": confusion_matrix(true_labels, candidate_predictions, labels=class_ids).tolist(),
        "classification_report_new": classification_report(true_labels, candidate_predictions, labels=class_ids, zero_division=0, output_dict=True),
        "source_rows": sources,
    }
    summary_path = output_dir / f"{config.session_id}_validation_summary.json"
    summary_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report["summary_path"] = str(summary_path)
    _tinyol_log(log_fn, f"Validation result: decision={report['decision']} target_recall={report['target_recall_base']:.3f}->{report['target_recall_new']:.3f} target_f1={report['target_f1_base']:.3f}->{report['target_f1_new']:.3f} acc={report['overall_acc_base']:.3f}->{report['overall_acc_new']:.3f}")
    return report


__all__ = [
    "TinyOlCancelledError",
    "TinyOlRecordConfig",
    "TinyOlTrainConfig",
    "tinyol_record_from_config",
    "tinyol_train_from_config",
    "tinyol_validate_record_config",
]
