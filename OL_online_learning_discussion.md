# OL Online Learning 討論紀錄

## 目標
在 `RESTCN` 的 `cnn` 模型上，透過 `ui_v6` 規劃一條 `online learning (OL)` 驗證流程，先在 PC 平台確認：
- OL 是否可行
- OL 更新成本占比
- OL 對準確率與穩定性的影響
- 後續是否值得移植到 `RA6M5`
- 另外新增一個 `tinyol` tab，作為 OL 驗證入口
- `tinyol` tab 要獨立於 `Detect`，不要混成同一條流程
- `tinyol` 只承接 OL 相關操作，不直接依賴 `Detect` 的狀態機或交握流程

## 目前模型
現有 `cnn` head 結構：
- `Dense(128) -> LeakyReLU -> Dropout(0.3)`
- `Dense(64) -> LeakyReLU`
- `Dense(num_classes, softmax)`

目前共同認知：
- 這三層可作為 OL 的第一版驗證範圍
- 但不建議一開始就三層全開一起重算
- 更合理的方式是先從最小更新範圍開始，再逐步擴大

## 建議的 OL 反向推論順序
### Phase 1
只更新：
- `Dense(num_classes, softmax)`

目的：
- 驗證最小成本下是否能適應新樣本
- 確認分類頭是否已經足夠吸收新資訊

### Phase 2
更新：
- `Dense(64)`
- `Dense(num_classes, softmax)`

目的：
- 檢查增加一層可學參數後，準確率是否明顯改善
- 觀察額外計算成本是否值得

### Phase 3
更新：
- `Dense(128)`
- `Dense(64)`
- `Dense(num_classes, softmax)`

目的：
- 評估完整 head 的 online adaptation 上限
- 作為 PC 平台可行性與效能占比的上界版本

## 凍結策略
OL 第一版建議先凍結整個 backbone：
- `Conv1D`
- `BatchNormalization`
- `SE Block`
- `MaxPool`
- `GlobalAveragePooling1D`
- `GlobalMaxPooling1D`
- `input_variance` 投影分支
- `input_mean` 投影分支

先只讓 head 學新東西的原因：
- backbone 是穩定特徵提取器
- OL 的目標是快速適應，不是重新學表徵
- 這樣之後移植到 `RA6M5` 也比較容易做成低成本更新

## OL 更新切點
目前已定案的板端等價 OL 邊界：
- 凍結到 `Dense(128)` 為止
- 只更新：
  - `Dense(64)`
  - `Dense(num_classes, softmax)`

更精確地說：
- `merged -> Dense(128) -> LeakyReLU` 這一段仍視為固定特徵提取流程的一部分
- `Dropout` 在訓練時屬 regularization，部署/推論時不作為可更新權重
- 真正提供給 OL 可學習區塊的輸入，可視為 `Dense(128)` 後的固定 embedding

這樣的理由：
- 比更新完整 head 更省資源
- 比只更新最後一層更有適應能力
- 比較接近未來 `RA6M5` 可承受的 on-device incremental update 複雜度

## 驗證重點
要在平台上記錄的指標：
- accuracy
- confusion matrix
- replay CSV detect 結果
- update latency
- inference latency
- model size
- 訓練/更新成本
- 遺忘舊類別的程度

## Replay 資料配方（考慮未來 RA6M5）
以未來要移植到 `RA6M5` 為前提，replay 不應以「整個 CSV 檔數」思考，而應以「window 數」思考。

### 基本單位
- 1 個 replay 單位 = 1 個 `window`
- 以目前模型設定為例：
  - `window_len = 100`
  - `channels = 6`
  - 以 raw row data 儲存即可
  - `delta` 在重訓前可再計算，不一定要存

### 第一版建議配方
- `target new data`
  - 目標類別新錄資料：`20 ~ 40 windows`
- `confusable replay`
  - 最容易混淆的 `2 ~ 3` 類
  - 每類 `5 ~ 10 windows`
- `anchor replay`
  - 其餘非目標類別
  - 每類 `1 ~ 3 windows`

### 建議預設值
作為第一版實作用的預設值：
- `target windows = 30`
- `confusable class count = 3`
- `confusable windows per class = 8`
- `anchor windows per class = 2`

若為 9 類模型，總量約為：
- `target`: `30`
- `confusable`: `3 x 8 = 24`
- `anchor`: `5 x 2 = 10`
- 合計約 `64 windows`

### 為什麼這樣定義
- `target` 負責讓模型學會修正目標類別
- `confusable replay` 負責保住真正容易混淆的決策邊界
- `anchor replay` 不追求重新學好所有類別，只負責降低 catastrophic forgetting
- 這個量級比「全部類別大量重錄」更接近未來可落地到 `RA6M5` 的設計

## 板端等價 OL 訓練配方
第一版先用保守設定，目的不是把 loss 壓到最低，而是小步修正且避免破壞舊知識。

### 更新層
- `Dense(64)`
- `Dense(num_classes, softmax)`

### 資料量
- `target`: `30 windows`
- `confusable`: `3 類 x 8 windows = 24`
- `anchor`: 其餘類別各 `2 windows`
- 總量約 `60 ~ 70 windows`

### 訓練參數
- `batch_size = 4`
- `epochs = 5`
- `learning_rate = 3e-4`
- optimizer 第一版傾向使用較簡化、較輕量的形式，避免板端成本過高

### 設計原則
- 不允許把整包 `data_all_select` 全量塞進來重訓
- 不允許臨時改模型結構
- 不允許改 feature pipeline
- 不允許讓資料量膨脹成接近完整 retrain
- PC 版 `tinyol` 也要遵守同樣限制，作為 `RA6M5` 模擬器

## OL 驗證通過門檻
第一版建議採用以下規格：

### target 必須改善
- `target class recall` 至少提升 `+5%`
或
- `target class F1` 至少提升 `+3%`

### 全局不得明顯退化
- 整體 `accuracy` 不可下降超過 `1%`
- 任一非目標類別 `recall` 不可下降超過 `3%`
- 所有非目標類別平均 `F1` 不可下降超過 `2%`

### 決策規則
- 若 target 提升不足，則本次 OL 標記為 `reject`
- 若任一保護條件被觸發，則本次 OL 標記為 `reject`
- 若通過，則允許使用者決定是否切換為 active model

## 模型輸出與切換
目前傾向：
- OL 完成後輸出新的 `.keras`
- 主 `meta.pkl` 在類別、`window_len`、`feature_cols`、`flags` 都不變的前提下，可沿用原本內容
- 但仍建議額外保留 session/provenance 記錄，以便追蹤這次 OL 的 target data、replay 配方與驗證結果

### 切換策略
- OL 完成後不自動覆蓋舊模型
- UI 顯示本次結果為 `pass` 或 `reject`
- 只有 `pass` 才提供 `Set Active Model` 動作
- rollback 方式為回切到前一版 `.keras`

## `tinyol` Tab UI 規格草案
`tinyol` tab 的定位：
- 不等同一般 Train/Detect 頁
- 要模擬未來 `RA6M5` 的 on-device head-only OL 流程
- UI 與流程應盡量貼近板端交握與限制

### 區塊 1：Active Model
用途：
- 顯示當前 OL 會使用的模型版本與 metadata

欄位：
- `Active Keras`
- `Meta PKL`
- `Model Type`
- `Window Len`
- `Window Step`
- `Channels`
- `Feature Cols`
- `Flags`
- `Target Update Scope`：固定顯示 `Dense(64) + Dense(num_classes)`

按鈕：
- `Load Active Model`
- `Refresh Meta`

### 區塊 2：Class Selection
用途：
- 從 `meta.pkl` 的 `id_to_name` 顯示可做 OL 的類別

欄位：
- class table：`ID / Name / Prefix(若可推得) / Recent Error Rank`
- `Target Class`
- `Recommended Confusables`

按鈕：
- `Auto Recommend Confusables`
- `Use Recommendation`

規則：
- target class 由使用者選
- confusable class 由系統依 `confusion matrix / error analysis` 推薦

### 區塊 3：Session Snapshot
用途：
- 建立本次 OL session 的固定上下文

欄位：
- `Session ID`
- `Created Time`
- `Target Class`
- `Window Len`
- `Slope Factor`
- `Channel Config`
- `Base/Hold Source`
- `Replay Policy`

按鈕：
- `Create Session`
- `Lock Session`

規則：
- session 建立後，核心參數不可隨意變更
- 未建立 session 前不可開始錄製

### 區塊 4：Target Recording
用途：
- 錄製本次要補強的 target raw row data

欄位：
- `Target Windows Collected`
- `Estimated Segments`
- `Recording Status`
- `Base/Hold Snapshot`
- `Window Goal`，預設 `30`

按鈕：
- `Start Record`
- `Stop Record`
- `Discard Last`
- `Clear Target Buffer`

規則：
- 錄製資料一律保存 raw row data
- 完成後自動標記為 target class
- 以 windows 數判定是否達標

### 區塊 5：Replay Builder
用途：
- 自動建立 confusable replay 與 anchor replay

欄位：
- `Confusable Classes`
- `Confusable Windows Per Class`
- `Anchor Windows Per Class`
- `Replay Source`
- `Replay Summary`

按鈕：
- `Build Replay`
- `Preview Replay`
- `Rebuild Replay`

預設：
- `confusable class count = 3`
- `confusable windows per class = 8`
- `anchor windows per class = 2`

### 區塊 6：OL Training
用途：
- 依板端等價配方執行 head-only incremental update

欄位：
- `Trainable Layers`：固定顯示 `Dense(64), Dense(num_classes)`
- `Batch Size`：預設 `4`
- `Epochs`：預設 `5`
- `Learning Rate`：預設 `3e-4`
- `Total Windows`
- `Training Status`

按鈕：
- `Run OL`
- `Abort`

規則：
- 未完成 target data 與 replay build 前不可開始
- 訓練前需二次確認提示框

### 區塊 7：Validation
用途：
- 比較 OL 前後模型是否通過門檻

欄位：
- `Target Recall Delta`
- `Target F1 Delta`
- `Overall Accuracy Delta`
- `Worst Non-target Recall Delta`
- `Mean Non-target F1 Delta`
- `Decision`

按鈕：
- `Run Validation`
- `Open Report`

決策顯示：
- `PASS`
- `REJECT`

### 區塊 8：Output / Switch
用途：
- 輸出新模型與控制 active model 切換

欄位：
- `Output Keras Path`
- `Session Log Path`
- `Validation Result`
- `Current Active Model`
- `Candidate Model`

按鈕：
- `Export New Keras`
- `Set Active Model`
- `Rollback`

規則：
- `REJECT` 狀態下不得啟用 `Set Active Model`
- rollback 必須可回到前一版 `.keras`

## `tinyol` 狀態機
建議狀態如下：

1. `Idle`
- 尚未載入 active model

2. `ModelReady`
- 已成功讀取 `keras + meta`

3. `SessionReady`
- target class 已選定
- session 已建立並鎖定

4. `Recording`
- 正在錄 target raw row data

5. `ReplayReady`
- target data 已達門檻
- replay 已建立

6. `Training`
- 正在執行 `Dense(64) + Dense(num_classes)` 更新

7. `Validating`
- 正在比較舊模型與新模型

8. `Pass`
- 驗證通過，可輸出/切換

9. `Reject`
- 驗證未過，只可保留結果或放棄

## 使用者操作順序
建議固定成這條路徑：

1. `Load Active Model`
2. `Select Target Class`
3. `Auto Recommend Confusables`
4. `Create Session`
5. `Start/Stop Record`
6. `Build Replay`
7. `Run OL`
8. `Run Validation`
9. `Export New Keras`
10. `Set Active Model` 或 `Rollback`

## Window 提取與 MCU 輸出規格
為了貼近未來板端使用情境，target 錄製完成後，除了提供給 OL 訓練使用，也要能輸出為 MCU 可直接編譯/載入的資料格式。

### 錄製與提取規則
- 每段 target 錄製原始長度先以 `150 samples` 為基準
- 有效訓練 window 固定從第 `30` 筆開始提取
- 若目前模型 `window_len = 100`，則有效區間為：
  - `raw[30 : 130]`

### 提取結果輸出
- 每個提取完成的 target window，要能獨立輸出成單獨檔案
- 輸出目錄由使用者在 `tinyol` tab 指定
- 這批檔案的用途：
  - 作為 OL session 的固定樣本
  - 作為未來 `RA6M5` / MCU 端測試與導入資料

### 不建議直接保留 CSV 作為 MCU 輸入
- MCU 無法直接理解 CSV
- CSV 適合 PC 端檢查與除錯
- 若是未來要進 MCU，提取後應再轉成 MCU 可編譯格式

### 建議的 MCU 輸出格式
第一版建議：
- 保留一份 PC 可讀的中介檔（例如 CSV 或 JSON 摘要）供除錯
- 同時輸出一份 MCU 可讀格式

MCU 可讀格式優先建議：
1. `header-only` 方案
- 產生 `.h`
- 內容為固定長度的陣列，例如：
  - `const uint16_t tinyol_target_windows[][100][6]`
- 優點：
  - 最容易直接納入 MCU 專案
  - 不需要額外檔案系統解析器
  - 適合先做驗證

2. `c + h` 方案
- `.h`：宣告資料結構與 extern
- `.c`：實際陣列資料
- 優點：
  - 檔案分工較乾淨
  - 適合資料量稍大時維護

### 第一版建議選擇
第一版比較建議使用：
- `.h + .c`

理由：
- 若未來 target / replay windows 數量增加，全部塞在單一 `.h` 會過於龐大
- `.c` 放資料、`.h` 放宣告，較符合 MCU 專案管理方式
- 後面若要區分 target / confusable / anchor，也比較容易拆分

### 建議輸出內容
可考慮輸出：
- `tinyol_session_windows.h`
- `tinyol_session_windows.c`
- `tinyol_session_manifest.json`

其中：
- `.h/.c` 給 MCU 使用
- `manifest.json` 給 PC / UI 記錄：
  - session id
  - target class
  - window_len
  - start offset
  - sample count
  - source record id
  - 是否為 target / confusable / anchor

### UI 需求
`tinyol` tab 應新增：
- `Extract Output Dir`
- `Export Extracted Windows`
- `Export MCU Files`

### 目前建議
- 錄製後先抽出固定 window
- 每個 window 先形成獨立樣本
- 再由系統統一彙整輸出成：
  - PC 用的 session 記錄
  - MCU 用的 `.h/.c`

## 自動化規則
### 1. 類別來源
- 一律從當前 `meta.pkl` 的 `id_to_name` 讀取
- 不以 labels json 作為 OL 類別真實來源

### 2. 目標類別選定
- 使用者在 `tinyol` tab 選擇要優化的 `target class`
- UI 建立本次 `OL session`

### 3. session 快照
建立 session 時自動保存：
- `model path`
- `meta path`
- `window_len`
- `window_step`
- `channels`
- `feature_cols`
- `flags`
- `slope_factor`
- 當下使用的 `base / hold` 設定
- `target class id / name`
- session 建立時間

### 4. raw data 錄製
- 錄製資料一律保存為 raw row data
- 錄製完成後，自動標記為本次 `target class`
- 不直接儲存成 feature tensor，避免失去之後重切 window、重做 QC、重算 delta 的彈性

### 5. replay 自動抽樣
系統自動從既有資料集抽 replay：
- `confusable replay`
  - 來源：歷史 error analysis 或 confusion matrix
  - 若目前沒有自動分析結果，可先由使用者手選 `2 ~ 3` 類
- `anchor replay`
  - 來源：除 target 與 confusable 類別之外的其餘類別
  - 每類自動抽固定少量 windows

### 6. 抽樣優先順序
- 優先使用與目前模型 `meta` 一致的資料來源
- 優先抽品質正常、長度正常、未被標為異常的 CSV
- 若某類 replay 不足，UI 要明確提示「樣本不足」，不要默默用空集合訓練

### 7. 訓練觸發條件
只有同時滿足以下條件才允許開始 OL：
- target 新錄資料達最小門檻
- confusable replay 已選定
- anchor replay 已建立
- session 快照完成
- 使用者於提示框再次確認

### 8. OL 更新策略
第一版預設：
- 只更新 head
- 不更新 backbone
- 不直接覆蓋舊模型

更新順序：
1. `Dense(num_classes, softmax)`
2. `Dense(64) + Dense(num_classes)`
3. `Dense(128) + Dense(64) + Dense(num_classes)`

### 9. 輸出自動化
每次 OL 完成後自動輸出：
- 新版 `.keras`
- 新版 `meta.pkl`
- `session_log.json` 或等價紀錄檔
- replay 抽樣摘要
- 訓練前後比較摘要

### 10. 安全機制
- 新模型不得直接覆蓋舊模型
- 要保留 rollback 能力
- 若驗證結果劣化超過門檻，UI 應標記本次 OL 結果為不建議採用

## 需要注意的點
- `Dropout` 不算可訓練層，不是 OL 重點
- `label_smoothing` 和 `class_weight` 對 offline training 有幫助，但 OL 小步更新時要另外評估是否保留
- OL 的核心問題不是只有能不能訓練，還包括會不會快速遺忘舊知識

## 暫定結論
1. 先做 head-only OL 驗證
2. 再做 last-two-layer OL 驗證
3. 最後才考慮 full head OL
4. 先在 PC 平台量化效能，再決定是否移植到 `RA6M5`
5. `tinyol` tab 與 `Detect` 分離，兩者只共享必要的模型/資料讀取能力，不共享交握邏輯

## 後續待討論
- OL 的資料來源要用哪一種
- 每次更新要用幾筆樣本
- 是否需要 replay buffer
- 是否要限制只更新高置信錯誤樣本
- `ui_v6` 要怎麼新增 OL tab 與操作流程
- `tinyol` tab 要有哪些獨立功能
- `tinyol` tab 與 `Detect` 之間要完全切開到什麼程度
- confusable 類別要由使用者選、還是由 error analysis 自動推薦
- replay 抽樣結果要如何在 UI 中讓使用者覆核
