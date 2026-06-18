# TinyOL Mode 規劃文件

## 1. 目的
- 在 `RA6M5` MCU 上新增一個獨立的 `TinyOL mode`
- 讓使用者可針對單一表現不佳的類別做 head-only online learning
- 流程要盡量與目前 PC 端 `TinyOL` PoC 一致
- `TinyOL` 與 `Detect` 分離，不混在同一個頁面或 mode 內

## 2. 目前共識

### 2.1 更新範圍
- 只更新：
  - `Dense_F2`
  - `Dense_OUT`
- 不動 backbone / feature extractor

### 2.2 模型切點
- 以前段 frozen feature extractor 為主
- MCU 端 TinyOL 視為：
  - 前段固定推論出 embedding / feature
  - 後段 `Dense_F2 + Dense_OUT` 做 online update

### 2.3 權重持久化
- `default / factory weights`
  - 跟 firmware 一起放在 code flash / `cnn_lib`
- `active TinyOL head`
  - 獨立存放在保留 flash 區
  - 開機時若存在且有效，覆蓋 `Dense_F2 + Dense_OUT`
  - 若不存在或驗證失敗，回退到 factory head

### 2.4 Bootloader 責任邊界
- Bootloader / MCUboot 只負責：
  - bootloader
  - primary image
  - secondary image
  - image validate / boot
- 不應管理 TinyOL active weights
- TinyOL active weights 是 application-owned persistent storage

## 3. MCU 模式架構

### 3.1 新增獨立 app mode
- TinyOL mode 應比照 `sil_app_ds.*` 再開一條 app
- 建議新增：
  - `sil_app_tinyol.h`
  - `sil_app_tinyol.c`
  - `SIL_APP_TINYOL_E`

### 3.2 切換方式
- 由 PC 經 UART / ATCMD 發送 mode switch
- 沿用現有：
  - `$SILAPP`
  - `SIL_GLOBALS_SwitchApp()`

### 3.3 與 Detect 的關係
- Detect 繼續跑原本即時辨識
- TinyOL mode 是另一個獨立 mode
- 使用者只有在想做 OL 時才切進 TinyOL mode

## 4. 使用者情境

### 4.1 典型流程
- 使用者在 Detect 發現某個 gesture 類別不準
- PC 端 UI 選擇 target class
- PC 切換板子到 TinyOL mode
- TinyOL mode 完成校正、錄製、重訓、驗證
- 若成功，將新 head 寫回 active storage
- 再切回原本 CNN mode

### 4.2 target 類型
- 以單一 target class 為核心
- 不要求 10 類全部重錄
- 但 replay 必須帶入：
  - confusable replay
  - anchor replay

## 5. TinyOL Mode 完整流程

### Step 1：切 mode 前準備
- PC 先記錄使用者當前設定：
  - model / meta
  - target class
  - epochs
  - target 錄製次數
  - replay policy
- `base / hold` 不直接沿用 detect 中的殘值
- 建議在切入 TinyOL mode 後重新校正一次

### Step 2：切到 TinyOL mode
- PC 發送 mode switch 指令
- MCU 停止原本 detect row data stream
- 進入 `TinyOL mode`

### Step 3：TinyOL mode 初始化
- MCU 回報：
  - mode ready
  - class table
  - model signature
  - active head 狀態
- PC 顯示可選類別與目前 session 設定

### Step 4：重新校正
- TinyOL mode 先做 base / hold 校正
- 理由：
  - 與未來板端真實使用情境一致
  - 避免 detect mode 殘留狀態影響 TinyOL 錄製

### Step 5：PC 下發 session config
- PC 傳送：
  - target class id
  - target windows count
  - confusable class count
  - confusable windows per class
  - anchor windows per class
  - batch size
  - epochs
  - learning rate
  - record samples
  - window start offset

### Step 6：Target 錄製
- MCU 發送錄製請求 / ready 訊號
- PC 確認後送出 start record cmd
- MCU 開始收 raw row data
- 錄製完成後：
  - MCU 回報 raw capture done
  - 依規則切出 target window
  - 為這批資料標上 target label

### Step 7：Replay 準備
- target data 來源：
  - 當次錄製的 raw row data 切窗
- replay 來源：
  - 板上預燒的 default data
- replay 組成：
  - target windows
  - confusable replay
  - anchor replay

### Step 8：載入 active head
- MCU 啟動訓練前先決定 head 來源：
  - 若 active head 有效，先用 active head
  - 否則用 factory head

### Step 9：執行 TinyOL
- MCU 只更新：
  - `Dense_F2`
  - `Dense_OUT`
- 其餘層全部 frozen
- 訓練中 UART 持續回傳：
  - epoch
  - loss
  - accuracy / target recall（若有）
  - pass/fail 中間狀態

### Step 10：訓練後驗證
- MCU 用同一批 session data 或驗證切分做 quick validation
- 驗證關注：
  - target recall 是否提升
  - 整體 accuracy 是否明顯退化
  - 其他類別是否明顯崩壞

### Step 11：寫入 active head
- 若 validation pass：
  - 將新 head 寫入 active storage
- 若 fail：
  - 不覆蓋原 active head
  - 保留原本版本

### Step 12：切回 CNN mode
- TinyOL mode 回報最終結果
- PC 視需要切回 CNN mode
- 下次再次進入 TinyOL mode 時：
  - 以 active head 為起點再訓練

## 6. UART / PC-MCU 交握規劃

### 6.1 方向
- PC 是 session orchestrator
- MCU 是訓練執行者

### 6.2 建議責任分配
- PC 負責：
  - UI
  - target class 選擇
  - session config 下發
  - log 顯示
  - 流程控制
- MCU 負責：
  - mode 切換
  - base/hold 校正
  - raw capture
  - window 萃取
  - replay 組包
  - head 訓練
  - active head 讀寫

### 6.3 建議 command 類別
- mode control
  - enter tinyol
  - exit tinyol
- session control
  - create session
  - send session config
  - lock session
- calibration
  - start calibrate
  - calibrate done
- recording
  - record ready
  - record start
  - record stop
  - record done
- training
  - build replay
  - run ol
  - training log
  - validation result
- storage
  - load active head status
  - save active head
  - clear active head

## 7. Replay Policy

### 7.1 目標
- 避免只錄 target class 導致類別塌縮
- 控制 MCU 記憶體與訓練時間

### 7.2 建議預設
- `target windows = 30`
- `confusable class count = 3`
- `confusable windows per class = 8`
- `anchor windows per class = 2`

### 7.3 說明
- target
  - 當次要修正的類別
- confusable replay
  - 與 target 最容易混淆的 2~3 類
- anchor replay
  - 其他類別少量代表資料，避免 catastrophic forgetting

### 7.4 自動化方向
- 由 PC 依：
  - confusion matrix
  - train log / error analysis
  自動推薦 confusable classes

## 8. 板端 default data 與 active data

### 8.1 default data
- 由 PC 平台匯出 `.h/.c`
- 跟 firmware 一起編進 code flash
- 用於：
  - replay
  - 初始訓練對照
  - 無 active head 時的 baseline

### 8.2 active head
- 只存訓練後的：
  - `Dense_F2_W`
  - `Dense_F2_B`
  - `Dense_OUT_W`
  - `Dense_OUT_B`
- 不存整個模型

### 8.3 建議 metadata
- magic
- format version
- model signature
- class count
- tensor shape
- payload size
- payload crc
- valid flag

## 9. Flash / Boot / OTA 邊界

### 9.1 目前共識
- TinyOL active storage 不屬於 boot image
- 不應被 OTA image erase/write 蓋掉
- OTA 只碰 secondary slot

### 9.2 分工
- MCUboot:
  - primary/secondary image
- OTA:
  - secondary image only
- TinyOL runtime:
  - active head storage only

## 10. 訓練配方（第一版）

### 10.1 更新層
- `Dense_F2 + Dense_OUT`

### 10.2 預設訓練參數
- `batch_size = 4`
- `epochs = 8`
- `learning_rate = 5e-4`

### 10.3 必須與 PC 版一致的邏輯
- loss
- softmax
- gradient 方向
- optimizer update 規則
- learning rate
- batch 累積方式

## 11. 驗證標準

### 11.1 通過條件（建議）
- target recall 提升至少 `+5%`
- 或 target F1 提升至少 `+3%`

### 11.2 拒絕條件（建議）
- overall accuracy 下降超過 `1%`
- 非 target 類別 recall 下降超過 `3%`
- 任何關鍵類別出現明顯崩壞

### 11.3 實務說明
- 第一版 MCU TinyOL 驗證可偏務實
- 先確認：
  - target 類別能被拉升
  - 其他類別沒有嚴重毀損

## 12. 尚未完全定案的項目

### 12.1 UART command 完整格式
- 還需要整理成正式 command table

### 12.2 active head 寫入格式
- header 結構、crc 欄位、版本欄位仍要定稿

### 12.3 validation dataset 切法
- 要用同 session reuse
- 或切出一小部分 validation

### 12.4 target 錄製互動細節
- 由 MCU 主動提示 ready
- 還是 PC UI 主動倒數後送 start

## 13. 建議開發順序

### Phase A：Mode / Storage 打通
- 新增 `TinyOL mode`
- 加入 active head storage 讀寫
- 確保 boot / OTA / active head 邊界正確

### Phase B：UART 協定打通
- mode switch
- session config
- record start/stop
- training log output

### Phase C：板端訓練最小閉環
- target record
- replay build
- `Dense_F2 + Dense_OUT` update
- validation
- write active head

### Phase D：與 PC UI 整合
- `ui_v6` 或獨立工具控制 TinyOL mode
- 顯示 session、錄製、訓練、驗證狀態

## 14. 下一步建議
- 先定 UART command table
- 再定 active head header format
- 再實作 `sil_app_tinyol.*` 的 mode 骨架
