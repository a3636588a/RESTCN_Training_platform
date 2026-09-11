# Issue 解決報告：Detection Window Delta 對齊

## 1. 問題摘要

Training 與 Detection 使用相同的正規化與 Delta 特徵，但原本在 Window 邊界的處理方式不同。

- Training：先對完整 CSV 時間序列計算 Delta，再切成多個 Window。
- Detection：先取得目前 Window，再於 Window 內計算 Delta，因此每個 Window 的第一筆 Delta 固定為 `0`。

這會讓 Detection 每次推論的第一筆 Delta 與 Training Data 不完全一致。

## 2. 原本行為

原本 Detection 只計算目前 Window 內相鄰資料的差值：

```python
delta_signal = np.zeros_like(normalized_signal)
delta_signal[1:] = np.diff(normalized_signal, axis=0) * slope_factor
```

因此每個 Window 都會得到：

```python
delta_signal[0] = 0
```

假設目前 Window 是第 7～41 筆，第一個 Delta 正確應使用：

```text
第 7 筆 - 第 6 筆
```

原本 Detection 因為沒有保存第 6 筆，所以直接填入 `0`。

## 3. 解決方式

Detection 保存「即將被 Rolling Buffer 擠出的資料」，也就是下一個 Window 第一筆之前的相鄰資料。

簡化後的處理如下：

```python
# Buffer 已滿時，先保存即將被擠出的第一筆資料。
if buffer_is_full:
    sample_before_window = normalize(buffer[0])

# 每一筆有效資料仍然都會進入 Rolling Buffer。
buffer.append(new_sample)
```

推論時，使用保存的相鄰資料計算 Window 第一筆 Delta：

```python
delta_signal = np.zeros_like(normalized_signal)

# Window 內部的 Delta。
delta_signal[1:] = np.diff(normalized_signal, axis=0) * slope_factor

# Window 第一筆與前一筆真實資料的 Delta。
if sample_before_window is not None:
    delta_signal[0] = (
        normalized_signal[0] - sample_before_window
    ) * slope_factor
```

第一次填滿 Buffer 時還沒有前一筆資料，因此第一個 Delta 維持 `0`。

## 4. 與 Inference Stride 的關係

相鄰資料是在 `push_data()` 中更新，而 Stride 是在資料進入 Buffer 後才判斷：

```text
收到有效 Sensor Data
    → 更新相鄰資料
    → 放入 Rolling Buffer
    → 累加 row_counter
    → 檢查 infer_stride
    → 符合條件才執行 predict()
```

所以不論 `infer_stride` 設為 `1`、`3` 或 `6`：

- 每筆有效 Sensor Data 都會進入 Buffer。
- `sample_before_window` 會按照每筆資料向前移動。
- Stride 只控制推論頻率，不會造成 Delta 跨錯資料。

不能使用「上一個推論 Window 的最後一筆」，因為 Sliding Window 可能重疊。例如：

```text
前一個 Window：第 1～35 筆
目前 Window：  第 7～41 筆
```

目前 Window 的第一筆是第 7 筆，應與第 6 筆相減，而不是與第 35 筆相減。

## 5. CSV Detect API 驗證

### 驗證條件

- API：`detection_run_csv_from_config()`
- Model：`plk_default_addjump__nowuse/gesture_model_v5.keras`
- Metadata：`plk_default_addjump__nowuse/gesture_model_meta_v5.pkl`
- Dataset：8 個 Gesture 類別各選取 1 份 CSV
- Ground Truth：使用 CSV 檔名前綴，例如 `strike-0.csv` 的正確類別為 `strike`
- 總比較數：929 次 Model Prediction

### 驗證結果

| 類別 | 修改前正確率 | 修改後正確率 | 結果 |
|---|---:|---:|---|
| down | 100.00% | 100.00% | 不變 |
| empty | 100.00% | 100.00% | 不變 |
| left | 25.86% | 26.72% | 改善 1 筆 |
| right | 100.00% | 100.00% | 不變 |
| stand | 100.00% | 100.00% | 不變 |
| up | 100.00% | 100.00% | 不變 |
| strike | 52.99% | 60.68% | 改善 9 筆 |
| jump | 0.00% | 0.00% | Class 有變化，但仍判斷錯誤 |
| **整體** | **72.34%** | **73.41%** | **提升 1.07 個百分點** |

修改前後共有 23 次 `pred_id` 改變：

- 11 次：修改前錯誤，修改後正確。
- 1 次：修改前正確，修改後錯誤。
- 11 次：修改前後皆錯誤，但預測 Class 不同。
- 淨增加 10 次正確推論。

## 6. 驗證項目

- Python 語法檢查通過。
- Rolling Buffer 相鄰樣本移動測試通過。
- 原有 Detection Stride 測試 2 項全部通過。
- CSV Detect API 修改前後比較完成。
- `clear_buffers()` 會同步清除 `sample_before_window`，避免不同 Detection Run 共用舊資料。

## 7. 結論

此次修改讓 Detection 的 Delta Window 邊界處理與 Training 更一致，且不改變 Model Architecture、Detection API 或輸入輸出格式。

抽樣驗證結果顯示整體 Raw Accuracy 從 72.34% 提升到 73.41%，沒有發現整體退步。改善主要出現在 `strike`，而 `jump` 仍有獨立的辨識問題，不能視為本次 Delta 修正已解決。

正式發佈前若需要更完整的統計信心，建議再對 Dataset 中全部 896 份 CSV 執行相同的修改前後比較。
