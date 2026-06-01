#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
train_gesture_ds_tcn_v1.py

DS-CNN + lightweight TCN trainer with the same I/O contract as train_gesture_cnn_v1.
Inputs: [waveform(window, ch*2), variance(ch), mean(ch)]
Output: softmax(num_classes)
"""

import pathlib
import random
import threading
import time
from typing import Callable

import joblib
import numpy as np
import tensorflow as tf
from sklearn.metrics import confusion_matrix, classification_report
from sklearn.model_selection import train_test_split
from sklearn.utils import class_weight
from tensorflow.keras import layers, models

import train_gesture_cnn_v1 as cnn_v1


TrainCfg = cnn_v1.TrainCfg
UIProgressCallback = cnn_v1.UIProgressCallback
load_raw_windows_from_csv = cnn_v1.load_raw_windows_from_csv
plot_training_results = cnn_v1.plot_training_results


def _ds_conv_block(x, out_ch: int, kernel: int):
    x = layers.SeparableConv1D(out_ch, kernel_size=kernel, padding="same", use_bias=False)(x)
    x = layers.BatchNormalization()(x)
    x = layers.LeakyReLU(negative_slope=0.1)(x)
    return x


def _tcn_block(x, out_ch: int, dilation: int):
    x = layers.Conv1D(out_ch, kernel_size=3, padding="same", dilation_rate=dilation, use_bias=False)(x)
    x = layers.BatchNormalization()(x)
    x = layers.LeakyReLU(negative_slope=0.1)(x)
    return x


def train_ds_tcn_from_cfg(cfg: TrainCfg, log_fn: Callable[[str], None] = None, stop_event: threading.Event = None):
    if log_fn is None:
        import functools
        log_fn = functools.partial(print, flush=True)
    log_fn(f"Starting DS-TCN Training... TF version: {tf.__version__}")

    folder = pathlib.Path(cfg.data_dir)
    files = sorted(folder.glob("*.csv"))

    X_win_all = []
    X_var_all = []
    X_mean_all = []
    y_all = []
    X_files_all = []

    log_fn(f"Scanning {len(files)} files...")
    for f in files:
        if stop_event and stop_event.is_set():
            break
        counts = cfg.aug_copies if cfg.enable_augmentation else 1
        for _ in range(counts):
            dg, sg, do, tw = None, None, None, 1.0
            if cfg.enable_augmentation:
                dg = {ch: random.uniform(cfg.aug_delta_gain_min, cfg.aug_delta_gain_max) for ch in cfg.ch_list}
                sg = {ch: random.uniform(cfg.aug_span_gain_min, cfg.aug_span_gain_max) for ch in cfg.ch_list}
                if cfg.enable_offset_aug:
                    do = {
                        ch: max(-cfg.aug_offset_clip, min(cfg.aug_offset_clip, random.gauss(0.0, cfg.aug_offset_sigma)))
                        for ch in cfg.ch_list
                    }
                if cfg.enable_time_warp:
                    tw = random.uniform(cfg.time_warp_min, cfg.time_warp_max)

            Xw, Xv, Xm, y = load_raw_windows_from_csv(f, cfg, delta_gain=dg, span_gain=sg, delta_offset=do, time_warp_factor=tw)
            if Xw is not None:
                X_win_all.append(Xw)
                X_var_all.append(Xv)
                X_mean_all.append(Xm)
                y_all.append(y)
                rel_path = str(pathlib.Path(f.parent.name) / f.name)
                X_files_all.extend([rel_path] * Xw.shape[0])

    if not X_win_all:
        raise RuntimeError("No valid data found.")

    X_win = np.concatenate(X_win_all, axis=0)
    X_var = np.concatenate(X_var_all, axis=0)
    X_mean = np.concatenate(X_mean_all, axis=0)
    y = np.concatenate(y_all, axis=0)
    X_files = np.array(X_files_all)

    num_classes = len(cfg.id_to_name)
    log_fn(f"[TRAIN_DS_TCN] Data Loaded: {X_win.shape}, Var: {X_var.shape}, Classes: {num_classes}")
    log_fn(f"[TRAIN] X_shape: {X_win.shape}")
    log_fn(f"[TRAIN] num_classes: {num_classes}")
    log_fn(f"[TRAIN] num_files: {len(list(cfg.data_dir.glob('*.csv'))) if cfg.data_dir.is_dir() else 0}")

    file_labels = []
    valid_files = []
    for f in files:
        prefix = f.name.split("-")[0].lower()
        if prefix in cfg.prefix_to_id:
            file_labels.append(prefix)
            valid_files.append(f)
    if not valid_files:
        raise RuntimeError("No valid files with recognized prefixes found for splitting.")

    files_train, files_val_split = train_test_split(
        valid_files, test_size=0.2, stratify=file_labels, random_state=42
    )
    train_set = set([str(pathlib.Path(f.parent.name) / f.name) for f in files_train])
    val_set = set([str(pathlib.Path(f.parent.name) / f.name) for f in files_val_split])
    idx_train = np.array([i for i, f in enumerate(X_files) if f in train_set])
    idx_val = np.array([i for i, f in enumerate(X_files) if f in val_set])

    X_win_train, X_win_val = X_win[idx_train], X_win[idx_val]
    X_var_train, X_var_val = X_var[idx_train], X_var[idx_val]
    X_mean_train, X_mean_val = X_mean[idx_train], X_mean[idx_val]
    y_train, y_val = y[idx_train], y[idx_val]

    in_win = layers.Input(shape=(cfg.window_len, len(cfg.ch_list) * 2), name="input_waveform")
    x = _ds_conv_block(in_win, out_ch=48, kernel=5)
    x = _ds_conv_block(x, out_ch=64, kernel=3)
    x = layers.MaxPooling1D(pool_size=2)(x)  # keep full 80-sample input, only internal downsample to 40
    x = _tcn_block(x, out_ch=64, dilation=1)
    x = _tcn_block(x, out_ch=64, dilation=2)

    gap = layers.GlobalAveragePooling1D()(x)
    gmp = layers.GlobalMaxPooling1D()(x)
    x_pooled = layers.Concatenate()([gap, gmp])
    x_pooled = layers.Dropout(0.35)(x_pooled)

    in_var = layers.Input(shape=(len(cfg.ch_list),), name="input_variance")
    v = layers.Dense(32)(in_var)
    v = layers.LeakyReLU(negative_slope=0.1)(v)

    in_mean = layers.Input(shape=(len(cfg.ch_list),), name="input_mean")
    m = layers.Dense(32)(in_mean)
    m = layers.LeakyReLU(negative_slope=0.1)(m)

    merged = layers.Concatenate()([x_pooled, v, m])
    d = layers.Dense(96)(merged)
    d = layers.LeakyReLU(negative_slope=0.1)(d)
    d = layers.Dropout(0.3)(d)
    d = layers.Dense(64)(d)
    d = layers.LeakyReLU(negative_slope=0.1)(d)
    out = layers.Dense(num_classes, activation="softmax")(d)

    model = models.Model(inputs=[in_win, in_var, in_mean], outputs=out)
    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=cfg.learning_rate),
        loss=tf.keras.losses.CategoricalCrossentropy(label_smoothing=0.08),
        metrics=["accuracy"],
    )
    model.summary(print_fn=log_fn)

    callbacks = [
        tf.keras.callbacks.EarlyStopping(patience=cfg.early_stop_patience, restore_best_weights=True),
        tf.keras.callbacks.ReduceLROnPlateau(monitor="val_loss", factor=0.5, patience=cfg.lr_patience, min_lr=1e-6, verbose=1),
        UIProgressCallback(log_fn, cfg.epochs),
    ]
    if stop_event:
        class StopCallback(tf.keras.callbacks.Callback):
            def on_batch_end(self, batch, logs=None):
                if stop_event.is_set():
                    self.model.stop_training = True
        callbacks.append(StopCallback())

    cw = class_weight.compute_class_weight(class_weight="balanced", classes=np.unique(y_train), y=y_train)
    class_weight_dict = {i: w for i, w in zip(np.unique(y_train), cw)}
    log_fn(f"[TRAIN] Computed class weights: {class_weight_dict}")

    y_train_one_hot = tf.keras.utils.to_categorical(y_train, num_classes)
    y_val_one_hot = tf.keras.utils.to_categorical(y_val, num_classes)

    start_time = time.time()
    history = model.fit(
        [X_win_train, X_var_train, X_mean_train],
        y_train_one_hot,
        validation_data=([X_win_val, X_var_val, X_mean_val], y_val_one_hot),
        batch_size=cfg.batch_size,
        epochs=cfg.epochs,
        verbose=0,
        callbacks=callbacks,
        class_weight=class_weight_dict,
    )
    training_time = time.time() - start_time

    out_path = cfg.out_model_path
    if out_path.lower().endswith(".pkl"):
        out_path = out_path[:-4] + ".keras"
        log_fn(f"Note: Adjusting model extension for Keras: {cfg.out_model_path} -> {out_path}")
    model.save(out_path)

    meta = {
        "model_type": "cnn",
        "backbone": "ds_tcn",
        "channels": cfg.ch_list,
        "windowing": {"window_len": cfg.window_len, "window_step": cfg.window_step},
        "window_len": cfg.window_len,
        "window_step": cfg.window_step,
        "id_to_name": cfg.id_to_name,
        "num_classes": num_classes,
        "feature_cols": ["raw_window", "delta"],
        "slope_factor": cfg.slope_factor,
        "flags": {"use_raw": True, "use_delta": True},
    }
    joblib.dump(meta, cfg.out_meta_path)
    log_fn(f"[TRAIN] Saved model: {out_path}")
    log_fn(f"[TRAIN] Saved labels: {cfg.out_meta_path}")

    y_pred_probs = model.predict([X_win_val, X_var_val, X_mean_val], verbose=0)
    y_pred = np.argmax(y_pred_probs, axis=1)
    y_true = y_val

    # Detailed report (same style as original CNN trainer)
    log_fn("\n[TRAIN] [REPORT] confusion_matrix:")
    cm = confusion_matrix(y_true, y_pred)
    log_fn(str(cm))

    log_fn("\n[TRAIN] [REPORT] classification_report:")
    report_text = classification_report(y_true, y_pred, digits=3)
    log_fn(report_text)

    log_fn("\n[TRAIN] [REPORT] Error Analysis by File:")
    error_indices = np.where(y_pred != y_true)[0]
    if len(error_indices) == 0:
        log_fn("No errors found in validation set!")
    else:
        from collections import Counter
        error_by_class = {}
        files_val = X_files[idx_val]
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
            counts = Counter(fnames)
            for fname, count in counts.most_common(5):
                log_fn(f"  - 檔案: {fname} (發生 {count} 次)")

    report = classification_report(y_true, y_pred, output_dict=True, zero_division=0)
    log_fn(f"\n[TRAIN] accuracy: {history.history['val_accuracy'][-1]}")
    log_fn(f"[TRAIN] training_time: {training_time}")
    try:
        plot_training_results(history, y_true, y_pred, cfg.id_to_name, cfg.out_model_path)
        log_fn("[TRAIN] Graphical report saved as training_report.png")
    except Exception as e:
        log_fn(f"[WARN] Failed to save training report plot: {e}")

    return {
        "model_path": out_path,
        "meta_path": cfg.out_meta_path,
        "history": history.history,
        "report": report,
        "training_time": training_time,
    }
