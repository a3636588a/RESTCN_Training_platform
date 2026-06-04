# RESTCN - UI_V6 訓練/偵測平台

本專案提供 `ui_v6.py` 圖形介面，整合資料掃描、模型訓練、即時偵測與（後續）MCU codegen 流程。

## 1. 目前重點功能
- 訓練支援 `model_backbone` 切換：`cnn` / `ds_tcn`
- Train 頁面可直接調 `label_smoothing`
- 維持既有 I/O 介面：
  - `input_waveform`: `(WINDOW_LEN, ch*2)`（raw + delta）
  - `input_variance`: `(ch,)`
  - `input_mean`: `(ch,)`
  - 輸出：`softmax(num_classes)`
- Detect 流程可直接沿用（`model_type="cnn"` 路徑）
- Detect 支援 `Replay CSV Detect`，可用單一 CSV 逐 window 重播推論
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

## 3. 網路架構

### 3.1 原本 1D-CNN 架構
- 輸入：`(80, 12)`（6ch raw/dn + 6ch delta）
- Waveform 主幹：
  - `Conv1D(48, k=5, padding="same")`
  - `BatchNormalization`
  - `LeakyReLU`
  - `SE Block 1`
  - `MaxPool1D(2)`（80 -> 40）
  - `Conv1D(64, k=3, padding="same")`
  - `BatchNormalization`
  - `LeakyReLU`
  - `SE Block 2`
  - `MaxPool1D(2)`（40 -> 20）
- Pooling：
  - `GlobalAveragePooling1D`
  - `GlobalMaxPooling1D`
  - `Concatenate`
  - `Dropout(0.4)`
- 輔助分支：
  - `input_variance -> Dense(32) -> LeakyReLU`
  - `input_mean -> Dense(32) -> LeakyReLU`
- Head：
  - `Concatenate(waveform, variance, mean)`
  - `Dense(128) -> LeakyReLU -> Dropout(0.3)`
  - `Dense(64) -> LeakyReLU`
  - `Dense(num_classes, softmax)`

備註：
- 這版是「2-layer CNN + SE + multi-pooling + variance/mean fusion」。
- 舊註解裡提到第 3 層卷積被拿掉，原因是節省記憶體與推論時間。

### 3.2 DS-TCN 架構（目前版本）
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

設計差異：
- 1D-CNN：偏向標準卷積 + SE 做 channel reweighting。
- DS-TCN：前段用 depthwise separable conv 壓參數，後段用 dilation TCN 擴大 temporal receptive field。

## 4. 如何訓練
1. 啟動 UI
```powershell
& C:\Users\USE\miniconda3\python.exe C:\Users\USE\Desktop\SEAN_CODE\RESTCN\ui_v6.py
```

2. Train 頁面設定
- 載入 labels JSON（例如 `sleep_labels4_9label_demo.json`）
- 設定 `output_dir`（例如 `C:\Users\USE\Desktop\SEAN_CODE\RESTCN\sleep\plk\RESTCN`）
- `model_backbone` 選 `cnn` 或 `ds_tcn`
- `label_smoothing` 可直接在 `Model` 區塊調整
- `WINDOW_LEN=80`、`STEP=3`（依你目前流程）

3. 按 `Scan` 確認資料數量，再按 `Train`

## 4.1 label_smoothing 說明
Train 頁面的 `Model` 區塊可調：
- `epochs`
- `batch_size`
- `learning_rate`
- `label_smoothing`

`label_smoothing` 會直接影響：
- 模型 top1 confidence 上限傾向
- cross-entropy loss 的理論下限

以目前常用的 `9` 類分類為例：

| label_smoothing | 正解目標機率 | 其他類別目標機率 | Detect 常見 top1 | 理論最低 loss 約 |
|---|---:|---:|---:|---:|
| `0.00` | `1.0000` | `0.0000` | `0.99~1.00` | `0.000` |
| `0.03` | `0.9733` | `0.0033` | `0.97` 左右 | `0.178` |
| `0.08` | `0.9289` | `0.0089` | `0.93` 左右 | `0.406` |

解讀方式：
- 若 `label_smoothing=0.03`，Detect 常看到 `0.97` 左右是正常現象，不代表模型壞掉。
- 若 `label_smoothing=0.08`，train/val loss 長期停在 `0.40` 左右也屬正常，因為 target 本來就不是 one-hot。
- Detect log 目前只顯示到小數點後 2 位，所以其他類別常看到 `0.00`，多半只是實際值很小（例如 `0.003`）被四捨五入。

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

Detect 目前有兩種使用方式：
- 即時模式：`Start Detect`
- 離線重播：`Replay CSV Detect`

`Replay CSV Detect` 會：
- 讀取單一 CSV
- 用目前載入的 `model + meta`
- 依照即時 Detect 相同邏輯逐列餵資料
- buffer 滿後每個新 window 都跑一次推論
- 在 terminal 印出每個 window 的 `pred / conf / stable / top-k`

補充：
- CSV 檔名若是 `2-23.csv`，系統會自動把 `2` 當成 expected label 顯示在 log 中。
- expected label 只用來比對，不代表模型一定會輸出該類別。

`meta` 必要欄位需包含：
- `feature_cols: ["raw_window", "delta"]`
- `flags: {"use_raw": true, "use_delta": true}`
- `windowing`、`id_to_name`、`num_classes`

若缺欄位會出現：`meta.feature_cols missing/empty (v5 detect requires this)`。

## 7. 已知結論（本輪驗證）
- `ds_tcn` 在目前資料上可正常收斂，val_acc 約 0.992~0.993。
- loss/val_loss 平台期屬正常現象（label smoothing + class_weight 共同影響）。
- `label_smoothing=0.03` 時，Detect top1 約 `0.97` 屬正常。
- `label_smoothing=0.08` 時，Detect top1 約 `0.93` 屬正常。
- 目前弱點類別可優先關注 `Turn_right` 相關誤判流向。

## 8. 後續建議（可選）
- 若要擴大時序感受野：可試 `dilation=1,2,4`。
- 若想讓 loss 更有下降空間：可試 `label_smoothing 0.08 -> 0.03`。
- 若以速度優先：可再做一個更純的 `ds_cnn_fast` backbone 比對。
