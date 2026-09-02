#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
training_cnn.py

1D-CNN Training Script for Gesture Recognition (RA6M5 optimized).
Instead of manual feature extraction, this script uses raw signal windows.
Input Shape: (WindowLen, Channels)
Architecture: Conv1D -> BatchNormalization -> ReLU -> GlobalAveragePooling1D -> Dense
"""

import os
import json
import pathlib
import random
import threading
from dataclasses import dataclass
from typing import List, Optional, Tuple, Dict, Any, Callable

import numpy as np
import pandas as pd
import joblib
import tensorflow as tf
from tensorflow.keras import layers, models
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import confusion_matrix, classification_report
from sklearn.utils import class_weight
import time
import matplotlib.pyplot as plt
from training_contracts import training_raise_if_cancelled
try:
    import seaborn as sns
except Exception:
    sns = None

@dataclass
class TrainingConfig:
    """集中保存 CNN 與 DS-TCN 共用的 training 設定。"""

    data_dir: pathlib.Path = pathlib.Path("./")
    label_defs: Optional[List[Dict[str, Any]]] = None
    channels: List[int] = None # e.g. [1, 2, 3, 4, 5, 6]
    window_len: int = 40
    window_step: int = 2

    # --- Feature Engineering ---
    slope_factor: float = 20.0  # Amplify the Delta (slope) channel

    # CNN Params
    batch_size: int = 32
    epochs: int = 200
    learning_rate: float = 0.001
    label_smoothing: float = 0.08
    early_stop_patience: int = 15
    lr_patience: int = 10

    # Metadata
    out_model_path: str = "gesture_model_cnn_v1.h5" # Keras format
    out_meta_path: str = "gesture_model_meta_cnn_v1.pkl"

    # Augmentation Params
    enable_augmentation: bool = True
    aug_copies: int = 10
    aug_delta_gain_min: float = 0.75
    aug_delta_gain_max: float = 1.25
    aug_span_gain_min: float = 0.8
    aug_span_gain_max: float = 1.2
    enable_offset_aug: bool = True
    aug_offset_sigma: float = 30.0
    aug_offset_clip: float = 100.0
    enable_time_warp: bool = True
    time_warp_min: float = 0.8
    time_warp_max: float = 1.3

    @property
    def ch_list(self) -> List[int]:
        return self.channels if self.channels else [1, 2, 3, 4, 5]

    @property
    def prefix_to_id(self) -> Dict[str, int]:
        if self.label_defs:
            return {str(row["prefix"]).lower().strip(): int(row["id"]) for row in self.label_defs if str(row.get("prefix","")).strip()}
        return {str(i): i for i in range(10)}

    @property
    def id_to_name(self) -> Dict[int, str]:
        if self.label_defs:
            return {int(row["id"]): str(row.get("name", row.get("prefix", row["id"]))) for row in self.label_defs}
        return {i: str(i) for i in range(10)}


# 舊名稱保留給既有 script；新程式請使用完整名稱 TrainingConfig。
TrainCfg = TrainingConfig

def _resample_1d(sig: np.ndarray, new_len: int) -> np.ndarray:
    if new_len <= 1:
        return sig[:1].copy()
    x_old = np.linspace(0.0, 1.0, num=sig.shape[0], dtype=np.float32)
    x_new = np.linspace(0.0, 1.0, num=new_len, dtype=np.float32)
    return np.interp(x_new, x_old, sig).astype(np.float32)

def dataset_load_windows_from_csv(
    csv_path: pathlib.Path, 
    cfg: TrainingConfig,
    delta_gain: Optional[Dict[int, float]] = None,
    span_gain: Optional[Dict[int, float]] = None,
    delta_offset: Optional[Dict[int, float]] = None,
    time_warp_factor: float = 1.0
):
    """將單一 CSV 轉成 trainer 使用的 waveform、統計值與 label。"""

    df = pd.read_csv(csv_path)
    prefix = csv_path.name.split("-")[0].lower()
    if prefix not in cfg.prefix_to_id:
        # All loader exits keep the same four-part contract so unrelated CSV
        # files can be skipped without breaking trainer tuple unpacking.
        return None, None, None, None
    label = cfg.prefix_to_id[prefix]
    
    chs = cfg.ch_list
    data_list = []
    
    for ch in chs:
        row = df[f"ROWCH{ch}"].values.astype(np.float32)
        base = df[f"MOVBASE{ch}"].values.astype(np.float32)
        hold = df[f"HOLDAVG{ch}"].values.astype(np.float32) if f"HOLDAVG{ch}" in df.columns else (base + 1000.0)

        # Apply Time Warp
        if cfg.enable_time_warp and abs(time_warp_factor - 1.0) > 1e-3:
            new_len = max(cfg.window_len + 5, int(len(row) * time_warp_factor))
            row = _resample_1d(row, new_len)
            base = _resample_1d(base, new_len)
            hold = _resample_1d(hold, new_len)

        # Calculate Delta & Span with Augmentation
        dg = delta_gain[ch] if delta_gain and ch in delta_gain else 1.0
        sg = span_gain[ch] if span_gain and ch in span_gain else 1.0
        do = delta_offset[ch] if delta_offset and ch in delta_offset else 0.0

        d_mapped = (row - base) * dg + do
        span_mapped = np.abs(hold - base) * sg
        span_mapped = np.maximum(span_mapped, 1.0)
        
        dn = d_mapped / span_mapped
        data_list.append(dn)
    
    # Stack channels (Time, Channels)
    signal = np.stack(data_list, axis=1) # (N, num_channels)
    
    # --- Round 10: Robustness Augmentation ---
    # Apply jitter once per call (The caller/UI handles the loop for multiples)
    aug_signal = signal.copy()
    
    # We always apply a small random jitter if augmentation is enabled to improve baseline robustness
    # The caller provides dg, sg, do from the UI's generic augmentation logic
    # But for Round 10 "Robustness", we want specific bend fraction jitter.
    
    # Use random jitter within function for bend-fraction (Level)
    # Gain: 0.8x ~ 1.2x, Offset: -0.1 ~ 0.1
    # Disabling augmentation must also preserve deterministic input and avoid
    # consuming RNG state that could affect later training stages.
    if cfg.enable_augmentation:
        jitter_gain = np.random.uniform(0.8, 1.2, size=(1, len(chs)))
        jitter_offset = np.random.uniform(-0.10, 0.10, size=(1, len(chs)))
        aug_signal = aug_signal * jitter_gain + jitter_offset
            
    # Re-calculate Delta (Slope) for the augmented signal
    aug_delta = np.zeros_like(aug_signal)
    # Amplify the slope feature to make tiny movements (like Exhale) visible to the CNN
    aug_delta[1:] = np.diff(aug_signal, axis=0) * cfg.slope_factor
    aug_combined = np.concatenate([aug_signal, aug_delta], axis=1)

    all_windows = []
    all_vars = []
    all_means = []

    # Sliding window
    for i in range(0, len(aug_combined) - cfg.window_len + 1, cfg.window_step):
        win = aug_combined[i : i + cfg.window_len]
        all_windows.append(win)
        all_vars.append(np.var(win[:, :len(chs)], axis=0))
        all_means.append(np.mean(win[:, :len(chs)], axis=0))

    if not all_windows:
        return None, None, None, None
        
    return np.array(all_windows, dtype=np.float32), np.array(all_vars, dtype=np.float32), np.array(all_means, dtype=np.float32), np.full(len(all_windows), label, dtype=np.int32)


# 相容入口僅轉向同一實作，避免舊呼叫端產生兩套 loader 行為。
load_raw_windows_from_csv = dataset_load_windows_from_csv

class UIProgressCallback(tf.keras.callbacks.Callback):
    def __init__(self, log_fn, total_epochs):
        super().__init__()
        self.log_fn = log_fn
        self.total_epochs = total_epochs

    def on_epoch_end(self, epoch, logs=None):
        if logs:
            l = logs
            acc = l.get('accuracy', 0)
            val_acc = l.get('val_accuracy', 0)
            loss = l.get('loss', 0)
            
            # Simple progress message without unicode bars
            msg = f"Epoch {epoch+1:3d}/{self.total_epochs} | acc={acc:.4f}, val_acc={val_acc:.4f}, loss={loss:.4f}, val_loss={l.get('val_loss', 0):.4f}"
            self.log_fn(msg)
            if hasattr(self.log_fn, 'flush'): self.log_fn.flush()

def _cnn_build_squeeze_excitation_block(input_tensor, ratio=8):
    """
    Squeeze-and-Excitation block for 1D convolution.
    Weights each channel based on their global characteristics.
    """
    filters = input_tensor.shape[-1]
    # Squeeze: Global Average Pooling to get a channel descriptor
    se = layers.GlobalAveragePooling1D()(input_tensor)
    # Excitation: Two small Dense layers to learn channel importance
    se = layers.Dense(filters // ratio, activation='relu')(se)
    se = layers.Dense(filters, activation='sigmoid')(se)
    # Scale: Element-wise multiplication back to the original feature map
    return layers.Multiply()([input_tensor, se])


def training_run_cnn(cfg: TrainingConfig, log_fn: Callable[[str], None] = None, stop_event: threading.Event = None):
    """依設定執行 CNN training；取消時不發布 artifact。"""

    if log_fn is None:
        import functools
        log_fn = functools.partial(print, flush=True)
    log_fn(f"Starting CNN Training... TF version: {tf.__version__}")
    training_raise_if_cancelled(stop_event)
    
    folder = pathlib.Path(cfg.data_dir)
    files = sorted(folder.glob("*.csv"))
    
    X_win_all = []
    X_var_all = []
    X_mean_all = []
    y_all = []
    X_files_all = [] # 👈 Track file origins
    
    log_fn(f"Scanning {len(files)} files...")
    for f in files:
        training_raise_if_cancelled(stop_event)
        
        counts = cfg.aug_copies if cfg.enable_augmentation else 1
        for _ in range(counts):
            training_raise_if_cancelled(stop_event)
            dg, sg, do, tw = None, None, None, 1.0
            if cfg.enable_augmentation:
                dg = {ch: random.uniform(cfg.aug_delta_gain_min, cfg.aug_delta_gain_max) for ch in cfg.ch_list}
                sg = {ch: random.uniform(cfg.aug_span_gain_min, cfg.aug_span_gain_max) for ch in cfg.ch_list}
                if cfg.enable_offset_aug:
                    do = {ch: max(-cfg.aug_offset_clip, min(cfg.aug_offset_clip, random.gauss(0.0, cfg.aug_offset_sigma))) for ch in cfg.ch_list}
                if cfg.enable_time_warp:
                    tw = random.uniform(cfg.time_warp_min, cfg.time_warp_max)

            Xw, Xv, Xm, y = dataset_load_windows_from_csv(f, cfg, delta_gain=dg, span_gain=sg, delta_offset=do, time_warp_factor=tw)
            if Xw is not None:
                X_win_all.append(Xw)
                X_var_all.append(Xv)
                X_mean_all.append(Xm)
                y_all.append(y)
                # Save the relative path (e.g., "randy/10-100.csv")
                rel_path = os.path.join(f.parent.name, f.name)
                X_files_all.extend([rel_path] * Xw.shape[0])

    training_raise_if_cancelled(stop_event)
    
    if not X_win_all:
        raise RuntimeError("No valid data found.")
        
    X_win = np.concatenate(X_win_all, axis=0)
    X_var = np.concatenate(X_var_all, axis=0)
    X_mean = np.concatenate(X_mean_all, axis=0)
    y = np.concatenate(y_all, axis=0)
    X_files = np.array(X_files_all)
    
    num_classes = len(cfg.id_to_name)
    log_fn(f"[TRAIN_CNN] Data Loaded: {X_win.shape}, Var: {X_var.shape}, Classes: {num_classes}")
    log_fn(f"[TRAIN] X_shape: {X_win.shape}") # Aligned with MLP report
    log_fn(f"[TRAIN] num_classes: {num_classes}")
    log_fn(f"[TRAIN] num_files: {len(list(cfg.data_dir.glob('*.csv'))) if cfg.data_dir.is_dir() else 0}")
    
    # Split by File (Stratified) to prevent data leakage
    log_fn("[TRAIN] Splitting data by file (stratified) to prevent leakage...")
    
    # Get labels for each file for stratification
    file_labels = []
    valid_files = []
    for f in files:
        prefix = f.name.split("-")[0].lower()
        if prefix in cfg.prefix_to_id:
            file_labels.append(prefix)
            valid_files.append(f)
            
    if not valid_files:
        raise RuntimeError("No valid files with recognized prefixes found for splitting.")
        
    # Split the files
    files_train, files_val_split = train_test_split(
        valid_files, test_size=0.2, stratify=file_labels, random_state=42
    )
    
    # Create sets for fast lookup
    train_set = set([os.path.join(f.parent.name, f.name) for f in files_train])
    val_set = set([os.path.join(f.parent.name, f.name) for f in files_val_split])
    
    # Map windows to train/val based on their file origin
    idx_train = np.array([i for i, f in enumerate(X_files) if f in train_set])
    idx_val = np.array([i for i, f in enumerate(X_files) if f in val_set])
    
    log_fn(f"[TRAIN] Split files: {len(files_train)} train, {len(files_val_split)} val")
    log_fn(f"[TRAIN] Split windows: {len(idx_train)} train, {len(idx_val)} val")
    
    X_win_train, X_win_val = X_win[idx_train], X_win[idx_val]
    X_var_train, X_var_val = X_var[idx_train], X_var[idx_val]
    X_mean_train, X_mean_val = X_mean[idx_train], X_mean[idx_val]
    y_train, y_val = y[idx_train], y[idx_val]
    files_val = X_files[idx_val] # 👈 Track validation file origins
    
    # Model Architecture (Optimized Deep CNN with Multi-Pooling)
    in_win = layers.Input(shape=(cfg.window_len, len(cfg.ch_list) * 2), name="input_waveform")
    
    # Waveform Branch (Now 2-Layer with SE)
    x = layers.Conv1D(48, kernel_size=5, padding='same')(in_win)
    x = layers.BatchNormalization()(x)
    x = layers.LeakyReLU(negative_slope=0.1)(x)
    x = _cnn_build_squeeze_excitation_block(x, ratio=4) # SE Block 1
    x = layers.MaxPooling1D(pool_size=2)(x)
    
    x = layers.Conv1D(64, kernel_size=3, padding='same')(x)
    x = layers.BatchNormalization()(x)
    x = layers.LeakyReLU(negative_slope=0.1)(x)
    x = _cnn_build_squeeze_excitation_block(x, ratio=4) # SE Block 2
    x = layers.MaxPooling1D(pool_size=2)(x)
    
    # Layer 3 removed to save memory and inference time. 
    # SE Blocks provide better channel selection to compensate.

    # Pooling features for Waveform branch
    gap = layers.GlobalAveragePooling1D()(x)
    gmp = layers.GlobalMaxPooling1D()(x)
    x_pooled = layers.Concatenate()([gap, gmp])
    x_pooled = layers.Dropout(0.4)(x_pooled)
    
    # Branch 2: Variance
    in_var = layers.Input(shape=(len(cfg.ch_list),), name="input_variance")
    v = layers.Dense(32)(in_var)
    v = layers.LeakyReLU(alpha=0.1)(v)

    # Branch 3: Mean Level (Pose Bias)
    in_mean = layers.Input(shape=(len(cfg.ch_list),), name="input_mean")
    m = layers.Dense(32)(in_mean)
    m = layers.LeakyReLU(alpha=0.1)(m)
    
    # Merge all 3 branches
    merged = layers.Concatenate()([x_pooled, v, m])
    
    # Final Dense (Deepened)
    d = layers.Dense(128)(merged)
    d = layers.LeakyReLU(alpha=0.1)(d)
    d = layers.Dropout(0.3)(d)
    d = layers.Dense(64)(d)
    d = layers.LeakyReLU(alpha=0.1)(d)
    out = layers.Dense(num_classes, activation='softmax')(d)
    
    model = models.Model(inputs=[in_win, in_var, in_mean], outputs=out)
    
    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=cfg.learning_rate),
        loss=tf.keras.losses.CategoricalCrossentropy(label_smoothing=cfg.label_smoothing),
        metrics=['accuracy']
    )
    
    model.summary(print_fn=log_fn)
    
    # Training
    callbacks = [
        tf.keras.callbacks.EarlyStopping(patience=cfg.early_stop_patience, restore_best_weights=True),
        tf.keras.callbacks.ReduceLROnPlateau(monitor='val_loss', factor=0.5, patience=cfg.lr_patience, min_lr=1e-6, verbose=1),
        UIProgressCallback(log_fn, cfg.epochs)
    ]
    
    if stop_event:
        # Simple stop callback
        class StopCallback(tf.keras.callbacks.Callback):
            def on_batch_end(self, batch, logs=None):
                if stop_event.is_set():
                    self.model.stop_training = True
        callbacks.append(StopCallback())

    # ✅ Calculate Class Weights to handle imbalance (e.g. SOS vs MISS)
    cw = class_weight.compute_class_weight(
        class_weight='balanced',
        classes=np.unique(y_train),
        y=y_train
    )
    class_weight_dict = {i: w for i, w in zip(np.unique(y_train), cw)}
    log_fn(f"[TRAIN] Computed class weights: {class_weight_dict}")

    start_time = time.time()
    
    # Convert labels to one-hot for CategoricalCrossentropy with label smoothing
    y_train_one_hot = tf.keras.utils.to_categorical(y_train, num_classes)
    y_val_one_hot = tf.keras.utils.to_categorical(y_val, num_classes)
    
    history = model.fit(
        [X_win_train, X_var_train, X_mean_train], y_train_one_hot,
        validation_data=([X_win_val, X_var_val, X_mean_val], y_val_one_hot),
        batch_size=cfg.batch_size,
        epochs=cfg.epochs,
        verbose=0, # Use UI callback instead
        callbacks=callbacks,
        class_weight=class_weight_dict
    )
    training_time = time.time() - start_time
    # Keras returns normally after ``model.stop_training``. Re-check here so a
    # user cancellation cannot publish the partially trained model as success.
    training_raise_if_cancelled(stop_event)
    
    # Save Model
    out_path = cfg.out_model_path
    if not (out_path.endswith(".h5") or out_path.endswith(".keras")):
        old = out_path
        if out_path.endswith(".pkl"):
            out_path = out_path[:-4] + ".keras"
        else:
            out_path = out_path + ".keras"
        log_fn(f"Note: Adjusting model extension for Keras: {old} -> {out_path}")

    model.save(out_path)
    log_fn(f"Model saved to {out_path}")
    
    # Save Meta
    meta = {
        "model_type": "cnn",
        "channels": cfg.ch_list,
        "windowing": {"window_len": cfg.window_len, "window_step": cfg.window_step},
        "id_to_name": cfg.id_to_name,
        "num_classes": num_classes,
        "feature_cols": ["raw_window", "delta"], 
        "slope_factor": cfg.slope_factor,  # ✅ 保存斜率倍率，供偵測端自動對其
        "flags": {"use_raw": True, "use_delta": True}
    }
    joblib.dump(meta, cfg.out_meta_path)
    log_fn(f"[TRAIN] Saved labels: {cfg.out_meta_path}") # More aligned with MLP
    log_fn(f"Metadata saved to {cfg.out_meta_path}")
    
    # --- Detailed Reporting ---
    log_fn("\n[TRAIN] [REPORT] confusion_matrix:")
    y_pred_probs = model.predict([X_win_val, X_var_val, X_mean_val], verbose=0)
    y_pred = np.argmax(y_pred_probs, axis=1)
    
    # Since we use sparse_categorical_crossentropy, y_val is already integer labels (1D)
    y_true = y_val 
    
    cm = confusion_matrix(y_true, y_pred)
    log_fn(str(cm))
    
    log_fn("\n[TRAIN] [REPORT] classification_report:")
    report_text = classification_report(y_true, y_pred, digits=3)
    report = classification_report(y_true, y_pred, output_dict=True, zero_division=0)
    log_fn(report_text)

    # 👈 New: Error Analysis by File
    log_fn("\n[TRAIN] [REPORT] Error Analysis by File:")
    error_indices = np.where(y_pred != y_true)[0]
    
    if len(error_indices) == 0:
        log_fn("No errors found in validation set!")
    else:
        error_by_class = {}
        for idx in error_indices:
            true_cls = int(y_true[idx])
            pred_cls = int(y_pred[idx])
            fname = files_val[idx]
            
            key = (true_cls, pred_cls)
            if key not in error_by_class:
                error_by_class[key] = []
            error_by_class[key].append(fname)
            
        for (true_cls, pred_cls), fnames in sorted(error_by_class.items()):
            true_name = cfg.id_to_name.get(true_cls, str(true_cls))
            pred_name = cfg.id_to_name.get(pred_cls, str(pred_cls))
            
            log_fn(f"\n動作 [{true_name}] 被誤判為 [{pred_name}]，共 {len(fnames)} 次:")
            
            # Count occurrences of each file
            from collections import Counter
            counts = Counter(fnames)
            # Show top 5 problematic files
            for fname, count in counts.most_common(5):
                log_fn(f"  - 檔案: {fname} (發生 {count} 次)")
    
    log_fn("\n[TRAIN] === TRAIN DONE ===")
    log_fn(f"[TRAIN] accuracy: {history.history['val_accuracy'][-1]}")
    log_fn(f"[TRAIN] training_time: {training_time}")
    
    # --- Graphical Report ---
    try:
        training_plot_results(history, y_true, y_pred, cfg.id_to_name, cfg.out_model_path)
        log_fn(f"[TRAIN] Graphical report saved as training_report.png")
    except Exception as e:
        log_fn(f"[TRAIN] [WARN] Failed to generate graphical report: {e}")
    
    return {
        "model_path": out_path,
        "meta_path": cfg.out_meta_path,
        "accuracy": history.history['val_accuracy'][-1],
        "history": history.history,
        "report": report,
        "training_time": training_time,
    }


# 舊公開名稱仍可使用，但核心與新呼叫端統一走 training_run_cnn。
train_cnn_from_cfg = training_run_cnn

def training_plot_results(history, y_true, y_pred, id_to_name, model_path):
    """
    Generates a 2-panel figure: Training History and Confusion Matrix Heatmap
    """
    import matplotlib
    matplotlib.use('Agg') # Force non-interactive backend for thread safety
    import matplotlib.pyplot as plt
    plt.figure(figsize=(16, 6))
    
    # Panel 1: Training History
    plt.subplot(1, 2, 1)
    acc = history.history.get('accuracy', history.history.get('acc', []))
    val_acc = history.history.get('val_accuracy', history.history.get('val_acc', []))
    loss = history.history.get('loss', [])
    val_loss = history.history.get('val_loss', [])
    epochs = range(len(acc))
    
    plt.plot(epochs, acc, 'b-', label='train_acc')
    plt.plot(epochs, val_acc, 'c-', label='val_acc')
    plt.plot(epochs, loss, 'r--', label='train_loss')
    plt.plot(epochs, val_loss, 'orange', linestyle='--', label='val_loss')
    
    plt.title('Training History')
    plt.xlabel('Epoch')
    plt.ylabel('Value')
    plt.legend(loc='lower right')
    plt.grid(True, alpha=0.3)
    
    # Panel 2: Confusion Matrix Heatmap
    plt.subplot(1, 2, 2)
    num_classes = len(id_to_name)
    labels = [id_to_name.get(i, str(i)) for i in range(num_classes)]
    
    cm = confusion_matrix(y_true, y_pred, labels=range(num_classes))
    if sns is not None:
        sns.heatmap(cm, annot=True, fmt='d', cmap='Blues', xticklabels=labels, yticklabels=labels)
    else:
        plt.imshow(cm, interpolation='nearest', cmap='Blues')
        plt.colorbar()
        plt.xticks(range(len(labels)), labels, rotation=45, ha='right')
        plt.yticks(range(len(labels)), labels)
        for i in range(cm.shape[0]):
            for j in range(cm.shape[1]):
                plt.text(j, i, str(cm[i, j]), ha='center', va='center', color='black', fontsize=8)
    plt.title('Confusion Matrix Heatmap')
    plt.xlabel('Predicted')
    plt.ylabel('True')
    
    plt.tight_layout()
    
    # Save to the same directory as model
    report_path = pathlib.Path(model_path).parent / "training_report.png"
    plt.savefig(str(report_path))
    plt.close()

if __name__ == "__main__":
    # Example usage (usually called from UI)
    cfg = TrainingConfig(data_dir=pathlib.Path("./data"))
    training_run_cnn(cfg)
