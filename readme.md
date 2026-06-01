# RESTCN - UI_V6 訓練/偵測平台

本專案提供 `ui_v6.py` 圖形介面，整合資料掃描、模型訓練、即時偵測與（後續）MCU codegen 流程。

## 1. 目前重點功能
- 訓練支援 `model_backbone` 切換：`cnn` / `ds_tcn`
- 維持既有 I/O 介面：
  - `input_waveform`: `(WINDOW_LEN, ch*2)`（raw + delta）
  - `input_variance`: `(ch,)`
  - `input_mean`: `(ch,)`
  - 輸出：`softmax(num_classes)`
- Detect 流程可直接沿用（`model_type="cnn"` 路徑）
- 訓練 log 自動寫入你設定的輸出資料夾（plk）

## 2. 檔案對應
- `ui_v6.py`
  - 主 UI（Train / Detect / Codegen）
- `train_gesture_cnn_v1.py`
  - 原本 1D-CNN 訓練器
- `train_gesture_ds_tcn_v1.py`
  - 新增 DS-CNN + 輕量 TCN 訓練器
- `detect_gesture_universal_manual_holdavg_v5.py`
  - 即時偵測主程式（UI Detect 會呼叫）

## 3. DS-TCN 架構（目前版本）
- 輸入：`(80, 12)`（6ch + delta）
- 主幹：
  - `SeparableConv1D(48, k=5)`
  - `SeparableConv1D(64, k=3)`
  - `MaxPool1D(2)`（80 -> 40）
  - `TCN Conv1D(64, dilation=1)`
  - `TCN Conv1D(64, dilation=2)`
  - `GAP + GMP`
- 輔助分支：`variance`、`mean` 各自 Dense(32)
- Head：`Dense(96) -> Dense(64) -> softmax`
- 參數量：約 55K（9 classes 時）

## 4. 如何訓練
1. 啟動 UI
```powershell
& C:\Users\USE\miniconda3\python.exe C:\Users\USE\Desktop\SEAN_CODE\RESTCN\ui_v6.py
```

2. Train 頁面設定
- 載入 labels JSON（例如 `sleep_labels4_9label_demo.json`）
- 設定 `output_dir`（例如 `C:\Users\USE\Desktop\SEAN_CODE\RESTCN\sleep\plk\RESTCN`）
- `model_backbone` 選 `cnn` 或 `ds_tcn`
- `WINDOW_LEN=80`、`STEP=3`（依你目前流程）

3. 按 `Scan` 確認資料數量，再按 `Train`

## 5. 訓練輸出
輸出資料夾（`output_dir`）會包含：
- `gesture_model_v5.keras`
- `gesture_model_meta_v5.pkl`
- `training_report.png`
- `train_log_YYYYMMDD-HHMMSS.txt`（自動新增）

訓練 log 檔會同步記錄 UI terminal 內容，包含：
- epoch 指標
- confusion matrix
- classification report
- error analysis by file

## 6. Detect 使用注意
Detect 頁面請選：
- Model: `...\gesture_model_v5.keras`
- Meta: `...\gesture_model_meta_v5.pkl`

`meta` 必要欄位需包含：
- `feature_cols: ["raw_window", "delta"]`
- `flags: {"use_raw": true, "use_delta": true}`
- `windowing`、`id_to_name`、`num_classes`

若缺欄位會出現：`meta.feature_cols missing/empty (v5 detect requires this)`。

## 7. 已知結論（本輪驗證）
- `ds_tcn` 在目前資料上可正常收斂，val_acc 約 0.992~0.993。
- loss/val_loss 平台期屬正常現象（label smoothing + class_weight 共同影響）。
- 目前弱點類別可優先關注 `Turn_right` 相關誤判流向。

## 8. 後續建議（可選）
- 若要擴大時序感受野：可試 `dilation=1,2,4`。
- 若想讓 loss 更有下降空間：可試 `label_smoothing 0.08 -> 0.03`。
- 若以速度優先：可再做一個更純的 `ds_cnn_fast` backbone 比對。
