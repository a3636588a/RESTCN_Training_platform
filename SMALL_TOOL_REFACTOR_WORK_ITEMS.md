# 小型工具重構工作項目

## 目標

在不更換既有 ML framework、模型格式、MCU 整合方式及 Detect 行為的前提下，重構桌面訓練專案，使資料實體職責更集中，並提供穩定的共用 API。

## 限制

- 保留既有公開 trainer function，以維持相容性。
- Qt worker 僅作為精簡的 framework adapter。
- 不修改 `TEST`、無關的 MCU 檔案或 generated file。
- 重新命名或移除公開 function 前，必須先分析所有呼叫端。
- 每次修改程式碼後，必須提供 diff 與驗證摘要。
- 關鍵邏輯必須加入說明原因、contract 或 invariant 的註解。

## 工作項目

- [x] 檢查目前的訓練入口與 lifecycle 風險。
- [x] 第一階段：新增共用 training API 與結果 contract。
- [x] 第一階段：取消訓練時禁止發布 artifact。
- [x] 第一階段：讓 CSV loader 與 augmentation 行為確實遵循設定。
- [x] 第一階段：讓 Qt training worker 改用共用 API。
- [x] 第一階段：替關鍵 API、取消流程及 augmentation 決策補上註解。
- [x] 第二階段：將純設定驗證邏輯從 `MainWindow` 分離。
- [x] 第二階段：為 codegen、build 與 flash 建立職責集中的操作邊界。
- [x] 第三階段：檢查命名偏差，並在維持相容性的前提下遷移公開名稱。
- [x] 第四階段：為 UART 與 CSV replay Detect 建立不依賴 Qt 的共用 API。
- [x] 第四階段：共用 sample preprocessing、模型推論、post-processing 與 dynamic matching 流程。
- [x] 第四階段：讓 Detect Qt worker 僅轉接 log、stable／dynamic event 與終止狀態。
- [x] 第四階段：收斂 Detect 全域狀態與 serial lifecycle，避免重複執行互相污染。
- [x] 第四階段：將 Detect 純設定驗證從 `MainWindow` 分離。
- [x] 第五階段：移除主要 Python module 的歷史版本號，改用責任導向檔名。
- [x] 第五階段：依 `module_action_target()` 統一內部 function naming。
- [x] 第五階段：更新 UI、common API、PyInstaller 與 README 的 module reference。
- [x] Gen Code：將 `exit_thresh` 從 UI 經 common API 接入 MCU `CNN_POST_EXIT_DEFAULT`。
- [x] Training 標準輸出：新增 `TrainingProgress` callback，並統一完成結果的 artifact、Top-1、macro Precision／Recall／F1 與秒數欄位。
- [x] Detect 標準輸出：新增 `ModelPrediction` 與 `prediction_fn`，只公開 Model 原始 `pred_id`、`confidence`、`probabilities`。
- [x] Training API export：由 `training_api` 統一公開 `TrainingProgress`、`TrainingResult` 與 `training_run_from_config`。
- [x] Contract 一致化：Training／Detection 標準輸出改由各自的 `*_contracts.py` 公開，API 僅公開 operation。
- [x] Config 入口一致化：將唯一的 `TrainingConfig` 定義移到 `training_api.py`，UI 與外部應用統一從 API 建立設定。

## TrainingConfig 搬移對比

| 修改前 | 修改後 | 功能 |
|---|---|---|
| `training_cnn.py::TrainingConfig` | `training_api.py::TrainingConfig` | Config 所有權由 CNN 實作移到共用 operation API。 |
| UI 從 `training_cnn` 建立 Config | UI 從 `training_api` 建立 Config | CNN／DS-TCN 與外部呼叫端使用一致入口。 |
| API 在 module 載入時 Import Trainers | API 在執行 operation 時延遲 Import Trainers | 避免 API 與 Trainer 因共用 Config 產生循環 Import。 |
| 舊 Script 使用 `training_cnn.TrainingConfig` | 保留相同 Class 的相容別名 | 不複製 Dataclass，也不立即破壞舊入口。 |

## Contract module 一致化對比

| 修改前 | 修改後 | 功能 |
|---|---|---|
| Training output 在 `training_contracts.py`，並由 API re-export | Training output 只由 `training_contracts.py` 公開 | API 不再兼任資料型別入口。 |
| Detect output 宣告在 `detection_api.py` | 新增 `detection_contracts.py` | Training／Detection 使用一致的 Contract module 配置。 |
| `detection_model.predict()` 回傳 Tuple | 回傳 `ModelPrediction` 或 `None` | Model 本身直接遵循三欄位標準輸出。 |
| Detect API 再將 Tuple 包裝成標準輸出 | Detect API 直接接收 `ModelPrediction` | 移除重複轉換與兩種原始輸出表示法。 |

## Detect Model 標準輸出對比

| 修改前 | 修改後 | 功能 |
|---|---|---|
| Model 原始 tuple 只留在 Detect 內部 | `ModelPrediction` | 將三個原始推論欄位轉成 immutable、可序列化的公開資料。 |
| 外部只能接收 Log／Stable／Dynamic 字串 | `prediction_fn(ModelPrediction)` | 其他應用可逐次接收原始模型結果，不必解析 Log。 |
| `_DetectionUpdate` 重複保存三個原始欄位 | `_DetectionUpdate.prediction` | 原始模型結果維持單一來源；Stable／Dynamic 仍屬於 API 後處理。 |

`stable_fn`、`dynamic_fn` 與 `log_fn` 保留既有行為；`prediction_fn` 放在公開 API
參數最後，避免改變既有 positional caller 的參數意義。

## Training 標準輸出對比

| 修改前 | 修改後 | 功能 |
|---|---|---|
| Epoch 資訊僅由 `log_fn(str)` 輸出 | `progress_fn(TrainingProgress)` | 讓其他應用直接接收結構化 Epoch metrics，不需要解析文字。 |
| `meta_path` | `metadata_path` | 對外使用完整名稱；保留唯讀相容 property。 |
| `accuracy` | `validation_accuracy` | 明確表示原值來自最後一個 Epoch 的 Validation Accuracy。 |
| 無標準分類指標 | `top_1_accuracy`、`precision`、`recall`、`f1_score` | Top-1 使用 Validation prediction accuracy；其餘使用 classification report 的 macro average。 |
| `training_time` | `training_time_seconds` | 明確標示單位；保留唯讀相容 property。 |
| Report 僅寫檔與記錄 Log | `report_path` | 其他應用可直接取得 `training_report.png` 路徑。 |

## 第五階段命名對比與功能

### Python module

| 修改前 | 修改後 | 功能 |
|---|---|---|
| `ui_v6.py` | `gesture_tool_ui.py` | Qt UI；收集設定並轉接 Training、Detect、Codegen、Build 與 Flash operation。 |
| `train_gesture_cnn_v1.py` | `training_cnn.py` | CNN dataset loading、model training、artifact 與 training report 輸出。 |
| `train_gesture_ds_tcn_v1.py` | `training_ds_tcn.py` | DS-TCN model 建立與 training；沿用共用 `TrainingConfig` 與 dataset loader。 |
| `detect_gesture_universal_manual_holdavg_v5.py` | `detection_model.py` | Model／Metadata 載入、Sensor Window Buffer、特徵建立與 `predict()`。 |
| `ui_v6.spec` | `gesture_tool_ui.spec` | PyInstaller 打包入口與必要 module 清單。 |

### Function

| 修改前 | 修改後 | 功能 |
|---|---|---|
| `parse_line()` | `detection_parse_serial_line()` | 解析 MCU `$SIL...` UART 封包。 |
| `clamp()` | `_detection_clamp_value()` | 將 Gain 限制在設定範圍。 |
| `_try_update_gain_from_pending()` | `detection_update_gain_map()` | 舊版單檔入口依 Baseline／Hold 更新 Gain Map；新版 Detection API 不再呼叫此 global-state function。 |
| `squeeze_excitation_block()` | `_cnn_build_squeeze_excitation_block()` | 建立 CNN 內部的 Squeeze-and-Excitation block。 |
| `plot_training_results()` | `training_plot_results()` | 輸出 training history 與 confusion matrix。 |
| `_ds_conv_block()` | `_ds_tcn_build_conv_block()` | 建立 DS-TCN 前段 SeparableConv1D block。 |
| `_tcn_block()` | `_ds_tcn_build_block()` | 建立具有 dilation 的 TCN block。 |
| `_detection_apply_config()` | `_detection_resolve_model_path()` | 僅依 Metadata 解析實際 Model path，不再把 config 寫入 legacy globals。 |
| `_detection_csv_int_map()` | `_detection_parse_csv_channel_map()` | 將 CSV 欄位解析成 channel-value map。 |
| `_detection_emit_update()` | `_detection_emit_result_update()` | 將 stable／dynamic／probability 結果送到 log 與 callback。 |

第五階段不更改 `training_run_from_config()`、`detection_run_serial_from_config()`、
`detection_run_csv_from_config()` 等 common API，也不修改 model architecture、artifact 格式或 `predict()` 邏輯。
舊 module 檔名不再作為入口；外部 script 必須依上表更新 import。

## 第一階段驗收條件

- UI 僅呼叫 `training_run_from_config()` 單一入口。
- CNN 與 DS-TCN 對 UI 提供相同的結果欄位。
- 取消訓練後，不得儲存模型或回報模型已完成。
- 遇到未知 label 的 CSV 時直接略過，不會發生 tuple 解包錯誤。
- 停用 augmentation 時，同時停用 random jitter。
- 根目錄下所有 Python module 均通過 syntax parsing。
- 關鍵公開 API 與 lifecycle 決策具備正確且未過期的註解。

## 第二階段驗收條件

- training config 驗證不依賴 Qt、TensorFlow 或 `MainWindow`。
- Scan 與 Train 共用 `training_validate_config()` 驗證入口。
- 純驗證層只回報 issue，不顯示 `QMessageBox` 或修改 UI。
- label ID 自動重新編號仍由 UI 取得使用者同意後執行。
- UI table 變更後會重新建立 config 並再次驗證。
- codegen、build 與 flash 核心操作不依賴 Qt worker。
- Qt worker 僅轉接 log 與 completed／cancelled／failed／retry signal。
- subprocess 取消時會依序執行 terminate、等待，必要時再 kill。
- subprocess 結束後會關閉 stdout pipe 並回收 process handle。

## 第三階段驗收條件

- 設定實體統一使用完整的 `Config`，不再新增 `Cfg` 縮寫。
- training 公開入口使用 `training_run_*`，資料載入入口使用 `dataset_load_*`。
- UI 內部建立與驗證方法使用 `_build_*_config`、`_validate_*_config`。
- 舊的 `TrainCfg`、`train_*_from_cfg` 與 `load_raw_windows_from_csv` 仍可呼叫。
- 相容名稱只指向新實作，不複製商業邏輯。
- 本階段不變更 Qt callback、模型架構、training 行為或 artifact 格式。

## 第四階段驗收條件

- 提供 `detection_run_serial_from_config()` 與 `detection_run_csv_from_config()` 兩個明確入口。
- Detect config 與結果 contract 不依賴 Qt，非 UI script 可直接啟動推論。
- UART 與 CSV replay 共用 `detection_validate_config()`，純驗證層不依賴 Qt 或開啟裝置。
- UART 與 CSV replay 共用由完整 sample 到 stable／dynamic result 的核心流程。
- `DetectWorker` 與 `CsvDetectReplayWorker` 不再直接建立模型或修改 Detect module 全域設定。
- log、stable label、dynamic gesture 與取消能力以 optional callback／`stop_event` 注入。
- completed、cancelled 與 failed 為不同終止狀態；使用者停止不得回報成功。
- serial 在成功、取消或例外時都會於 `finally` 關閉，且重複啟動不沿用前次 runtime state。
- 保留目前 baseline、hold average、gain map、channel 檢查、stride、CNN input shape 與 post-processing 行為。
- UART 與 CSV replay 對相同 sample sequence 產生一致的 raw、stable 與 dynamic 結果。
- 可使用假資料來源驗證正常推論、資料不足、缺少 channel、取消及輸入例外，不需要連接實體裝置。

## 第六階段：Detection Config 與 Runtime State 分離

### 欄位歸屬

| 類型 | 欄位／資料 | 原因 |
|---|---|---|
| `DetectionConfig` | `serial_port`、`baud`、`model_path`、`metadata_path` | 啟動前由 UI／CLI 指定，執行期間不應改變。 |
| `DetectionConfig` | `print_proba`、`use_manual_holdavg`、`enable_gain_map` | Boolean feature switch，屬於本次操作的固定規則。 |
| `DetectionConfig` | Post-process、Manual Hold、Gain reference 與 clamp 參數 | 用來定義推論規則，不是執行中產生的結果。 |
| `DetectionRuntimeState` | `current_base_map`、`current_hold_map` | 由 UART／CSV sample 持續更新，只對單次 run 有效。 |
| `DetectionRuntimeState` | `gain_map`、`gain_ready` | 由本次裝置資料計算的 calibration state，不可跨 run 共用。 |
| `_DetectionSession` | `row_counter`、stable latch、dynamic sequence | 屬於單次推論 pipeline 的處理狀態，由 session 擁有。 |

### 修改前後對比

| 修改前 | 修改後 | 功能與影響 |
|---|---|---|
| API 將 `DetectionConfig` 寫入 `detection_model.py` globals | API 直接把固定參數傳給 `RealtimeGestureDetector` | 避免不同 run 或 thread 互相覆蓋設定。 |
| `GAIN_MAP`、`GAIN_READY` 為 module globals | 每次 operation 建立 `DetectionRuntimeState` | UART 與 CSV 的 calibration state 彼此隔離。 |
| UART 的 baseline／hold 使用 operation local dict | baseline／hold 統一由 runtime state 擁有 | 狀態 owner 明確，gain update 與 model input 使用同一份資料。 |
| `_detection_emit_result_update()` 讀取 `PRINT_PROBA` global | 由 API 明確傳入 `config.print_proba` | Output 行為完全由本次 config 決定。 |
| Detector 從 globals 載入 model／metadata／slope／manual hold | Detector constructor 接收對應參數 | `DetectionConfig -> API -> Detector` 資料流可追蹤且可測試。 |

### 第六階段驗收條件

- COM port、baud 與所有 Boolean feature switch 只由 `DetectionConfig` 提供。
- UART／CSV 每次啟動都建立新的 `DetectionRuntimeState`。
- Detection API 不讀寫 `detection_model.py` 的 configuration／gain globals。
- `RealtimeGestureDetector()` 無參數建構仍保留，供舊版單檔入口相容使用。
- Model architecture、Metadata 格式、`ModelPrediction` 與公開 run API 簽章維持不變。

## 第七階段：README Refactor 文件

- 將 README 改為目前乾淨分支的專案入口文件。
- 移除已不屬於此分支的 MCU workspace 狀態、歷史 Bug 長篇紀錄與重複 TinyOL 內容。
- 補上現行 module 責任、Training／Detection flow、非 UI API 範例與標準輸出。
- 明確記錄 Config validation、Runtime State 隔離、取消與 resource cleanup 規則。
- 保留舊版與 Refactor module 名稱對照，方便既有使用者更新 import。

## 第八階段：Config 與跨模組欄位命名統一

| 修改前 | 修改後 | 適用範圍 |
|---|---|---|
| `out_model_path` | `output_model_path` | `TrainingConfig` 與 Trainer。 |
| `out_meta_path`／`meta_path` | `output_metadata_path`／`metadata_path` | Training、Detection、Codegen 與 TinyOL。 |
| `outdir`／`out_dir` | `output_dir` | Gencode Config、operation 與 result payload。 |
| `proj_dir`／`*_proj_dir` | `project_dir`／`*_project_dir` | Build 與 Auto Build。 |
| `port`／`com_port` | `serial_port` | Detection、TinyOL UART 與 Flash。 |

- `CodegenConfig`、`BuildConfig`、`FlashConfig` 集中到 `tool_operations.py`，讓非 UI caller 可直接建立完整 Config。
- 舊欄位保留唯讀 property，提供讀取相容；專案內建構與存取統一使用新名稱。
- Trainer 回傳的內部 dictionary 同步使用 `metadata_path`、`validation_accuracy` 與 `training_time_seconds`。
- `AutoBuildConfig` 補上流程既有使用、但原先未宣告的 `auto_cleanup` Boolean 欄位。
- 所有公開 Config path 統一接受 `str`；需要 filesystem 操作時再由 implementation 轉成 `Path`。

## 第九階段：Tool Operations 模組責任確認

- 保留 `tool_operations.py`，集中 Codegen、Build、Flash 的 Config、operation 與共用 process lifecycle。
- 使用 `CodegenConfig` 與 `codegen_run_from_config()`，名稱與既有 Codegen 用語一致。
- UI 直接 import `tool_operations`；此 module 擁有實際流程，不是單純轉接層。
- 移除 `gencode_api.py`，避免 module 名稱讓人誤以為只負責 Codegen。
- 修正 CNN／DS-TCN 的 `progress_fn` contract，兩種 Backbone 都透過 `TrainingProgress` 回報每個 Epoch。
- 修正 CNN 將 `TrainingConfig.data_dir` 的 `str` 直接當成 `Path` 使用，filesystem 操作統一改用 operation 內正規化的 `folder`。
- 新增 `tests/test_training_api.py`，以 Default `TrainingConfig` 驗證 Backbone routing、Result、Progress 與 Cancellation contract。
- 移除 CNN 內重複的 `TrainingConfig` 定義；CNN、DS-TCN、UI 與外部 caller 統一使用 `training_api.TrainingConfig`。
- Training API test 補入專案根目錄 import boundary，同時支援直接執行與 `unittest discover`。
- 移除 `detection_model.py` 內第二套 predict stride；推論頻率統一由 `DetectionConfig.infer_stride` 與 Detection API 控制。

## Gain Map 使用者注意事項

- 目前先保留既有 Gain Map 設定與計算行為，不調整 `DetectionConfig` 或演算法。
- `span_input` 是目前裝置的實際量測跨度，計算方式為 `abs(hold_value - current_base)`。
- `min_span_b` 是允許更新 Gain 的最低門檻，不會取代或覆寫 `span_input`。
- 當 `span_input < min_span_b` 時，本次資料不更新 Gain；當跨度符合門檻時，仍以實際的 `span_input` 作為 Gain 計算分母。
- 使用者應將 `min_span_b` 設為大於零且符合感測器雜訊範圍的數值，避免接近零的跨度造成 Gain 過度放大。

## Detection Model 新版 API 專用化

- `detection_model.py` 不再作為可單獨執行的 UART 程式，只保留 Model resource、Sensor Window、Feature 與 `predict()`。
- 移除舊版 `main()`、COM／Model path Globals、Global Gain State 與重複的 `MajorityChain` 後處理。
- `detection_parse_serial_line()` 搬到 `detection_api.py`，UART protocol parsing 不再由 Model module 負責。
- `RealtimeGestureDetector` 必須由 Detection API 明確傳入 Model、Metadata、Slope 與 Manual Hold，不再暗中使用 module defaults。
- UART lifecycle、固定設定與單次執行狀態分別由 `detection_api.py`、`DetectionConfig` 與 `DetectionRuntimeState` 負責。
- UI 初始值留在 UI 層，只用來建立 `DetectionConfig`，不再由 Model module 提供。

## UI Disable View

- 簡化 Training 畫面，隱藏 Dynamic Gestures 編輯區、`slope_factor` 與 `window_step`。
- Augmentation 僅顯示總開關；詳細參數仍保留既有預設值並送入 `TrainingConfig`。
- 隱藏 `random_state`、`batch_size`、`label_smoothing`、EarlyStop 與 ReduceLR；功能與資料流仍保留。
- 比較訓練完成後，UI 的 `label_smoothing` 固定為 `0.0` 並維持隱藏；由 UI 啟動的 Training 不套用 Label Smoothing。
- Detect 畫面隱藏 Dynamic Result、Dynamic Gestures Config 與 CNN Post-Processing 進階參數，只保留可調整的 `Inference Stride`。
- Detect Gesture Tier 預設全部設為 `Fast`；隱藏的 Tier table 仍保留既有 Config extraction 與 API 資料流。
- 主畫面隱藏 `Gen Code (CNN)` 與 `Auto Build` 分頁；頁面物件、Signal 與底層 operation 保留，不更動 API。
