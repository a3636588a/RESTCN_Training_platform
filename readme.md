# RESTCN - UI_V6 訓練/偵測平台

本專案提供 `ui_v6.py` 圖形介面，整合資料掃描、模型訓練、即時偵測與（後續）MCU codegen 流程。

## 1. 目前重點功能
- 訓練支援 `model_backbone` 切換：`cnn` / `ds_tcn`
- Train 頁面可直接調 `label_smoothing`
- `TinyOL` 頁面可做 head-only online learning PoC（`Dense(64) + Dense(num_classes)`）
- 維持既有 I/O 介面：
  - `input_waveform`: `(WINDOW_LEN, ch*2)`（raw + delta）
  - `input_variance`: `(ch,)`
  - `input_mean`: `(ch,)`
  - 輸出：`softmax(num_classes)`
- Detect 流程可直接沿用（`model_type="cnn"` 路徑）
- Detect 支援 `Replay CSV Detect`，可用單一 CSV 逐 window 重播推論
- `TinyOL` 支援 UART 錄 raw data、replay 抽樣、OL 微調、驗證摘要與 MCU `.h/.c` 匯出
- 訓練 log 自動寫入你設定的輸出資料夾（plk）

## 2. 檔案對應
- `ui_v6.py`
  - 主 UI（Train / Detect / TinyOL / Codegen）
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

## 6.1 TinyOL 使用注意
`TinyOL` 是獨立於 Detect 的 online learning 驗證頁，目標是先在 PC 端模擬未來板端 (`RA6M5`) 的 head-only OL 流程。

目前規格：
- 只更新 head 最後兩層：`Dense(64) + Dense(num_classes)`
- 類別來源以 `meta.pkl` 為主
- `Train Log` 用來推薦 `confusable classes`
- `window_len`、`channels`、`feature_cols` 依目前載入的 `meta` 固定
- 若 `Train Log` 沒提供 prefix mapping，會改用 `meta + replay data dir` 自動推 `prefix`

`TinyOL` 目前工作流：
1. 載入 `Model / Meta / Train Log / Replay data dir / Export dir`
2. 選 `Target Class`
3. `Auto Recommend Confusables`
4. `Create Session` → `Lock Session`
5. 用 `UART` 錄製 target raw data
6. 依規則提取 target window
7. `Build Replay`
8. `Run OL`
9. `Run Validation`
10. `Export MCU Files`

UART 錄製與 window 提取：
- 目前沿用 Detect 相同 UART 解析格式（如 `SILMOVBASE`、`SILHOLDAVG`、`SILROW`）
- 每次預設錄滿 `150` rows
- 再依 `start_offset=30` 取出 `window_len` 長度的 target window
- 例如 `window_len=35` 時，會取 `rows[30:65]`

Replay 策略：
- 若 log 有直接混淆類別，就優先抽 `confusable replay`
- 若沒有混淆類別，也允許走 `anchor-only replay`
- `replay data dir` 的 CSV 若檔名是 `0-12.csv`、`3-7.csv` 這種 prefix 形式，系統會依 prefix 抽樣

目前 `TinyOL` 會自動忽略多餘通道，只使用 `meta.channels` 指定的通道：
- `CSV / UART` 多給 channel 可以
- 缺少 `meta.channels` 需要的欄位才會報錯

訓練與 terminal 輸出：
- 可在 UI 設定 `Batch Size`、`Epochs`、`Learning Rate`
- terminal 會輸出：
  - dataset/replay 組成
  - trainable dense layers
  - train mix（target/replay/oversample）
  - train config（epochs/batch/lr）
  - 每一輪 `loss / acc / val_loss / val_acc`
  - 最後 validation summary

目前 validation 規則：
- target 必須有提升才會 `PASS`
- 若 baseline 本來就已經全對，即使訓練成功但沒有提升，也可能顯示 `REJECT`
- 因此 `TinyOL` 的 `PASS` 比較偏向「此 target 經 OL 後確實被拉升」

MCU 匯出：
- 可輸出 `tinyol_session_windows.h`
- 可輸出 `tinyol_session_windows.c`
- 可輸出 `tinyol_session_manifest.json`
- 目前格式為每個 label 各自獨立：
  - `tinyol_cls_<id>_windows`
  - `tinyol_cls_<id>_base`
  - `tinyol_cls_<id>_hold`

## 7. 已知結論（本輪驗證）
- `ds_tcn` 在目前資料上可正常收斂，val_acc 約 0.992~0.993。
- loss/val_loss 平台期屬正常現象（label smoothing + class_weight 共同影響）。
- `label_smoothing=0.03` 時，Detect top1 約 `0.97` 屬正常。
- `label_smoothing=0.08` 時，Detect top1 約 `0.93` 屬正常。
- 目前弱點類別可優先關注 `Turn_right` 相關誤判流向。
- `TinyOL` 目前已可完成：
  - UART 錄製
  - replay 抽樣
  - head-only OL
  - validation summary
  - MCU 匯出
- `TinyOL` 已出現可重現的 `PASS` 案例：
  - 目標類別可透過 `Dense(64) + Dense(num_classes)` 的 head-only OL 被拉升
  - 實測案例中，`target recall` 可由 `0.800 -> 1.000`
  - 同次案例中，`target f1` 可由 `0.889 -> 1.000`
  - 同次案例中，整體 `accuracy` 可由 `0.909 -> 1.000`
- 目前 `TinyOL PASS` 的意義偏向：
  - 證明現行流程可行
  - 證明 head-only OL 對部分弱類別有效
  - 尚不等同於最終泛化能力已完全驗證
- 目前常見 `PASS` / `REJECT` 解讀：
  - `PASS`：target 類別經 OL 後確實提升
  - `REJECT`：不一定代表流程失敗，也可能是 baseline 本來就已經全對，沒有提升空間
- `TinyOL` 若使用 `reuse-train-as-eval`：
  - 比較適合當 PoC / 流程驗證結果
  - 後續若要確認泛化，建議再用未參與本次 OL 的新資料重測

## 8. 後續建議（可選）
- 若要擴大時序感受野：可試 `dilation=1,2,4`。
- 若想讓 loss 更有下降空間：可試 `label_smoothing 0.08 -> 0.03`。
- 若以速度優先：可再做一個更純的 `ds_cnn_fast` backbone 比對。

## 9. 打包指令
目前使用 PyInstaller 打包 `ui_v6.py`：

```powershell
& "C:/Users/USE/miniconda3/envs/mlp/python.exe" -m PyInstaller --noconfirm ui_v6.spec
```

打包完成後輸出位置：
- `dist\ML_Station.exe`

補充：
- `ui_v6.spec` 已設定 EXE 名稱為 `ML_Station`
- 主視窗標題也已改為 `ML_Station`
