# AI 平台介面介紹

> 本文件整理自 [HackMD 原始文件](https://hackmd.io/CGMLfpkOSw6uLC1kDEhjiw?both)。

## Training table

![Training Data](https://hackmd.io/_uploads/rkbkMBRuzx.png)

![Training Settings](https://hackmd.io/_uploads/r1eYGBAuzx.png)

### Augment

| 名稱 | 說明 | 圖中設定 |
|---|---|---|
| `channels` | 選擇要送進 Model 的 Sensor Channel。Training 與 Detection 使用的 Channel 必須一致。 | 使用 CH1～CH5，未使用 CH6 |
| `window_len` | 每次送進 Model 的連續資料筆數。 | 每個 Window 使用 35 筆資料 |
| `slope_factor` | 將相鄰資料的變化量（Slope／Delta）放大。用來讓微小動作變化更明顯。 | 放大 20 倍 |
| `window_step` | Sliding Window 每次向後移動幾筆資料。 | 每次移動 5 筆 |
| `enable_augmentation` | 是否啟用資料擴增。未勾選時，下方擴增參數不生效。 | 已啟用 |
| `aug_copies` | 每個 CSV 重複處理幾次，每次使用不同的隨機擴增參數。 | 每個 CSV 產生 10 個版本 |
| `delta_gain min/max` | 對動作差值 `ROW - MOVBASE` 乘上隨機倍率。 | 模擬原始動作幅度的 75%～125% |
| `span_gain min/max` | 對 `abs(HOLDAVG - MOVBASE)` 的 Sensor Span 乘上隨機倍率。 | 模擬原始 Span 的 80%～120% |
| `enable_offset_aug` | 是否加入隨機 Sensor Offset。 | 已啟用 |
| `sigma` | Offset 隨機分布的標準差。越大，可能產生的偏移越明顯。 | 30 |
| `clip` | 限制 Offset 的最大絕對值。 | 限制於 -100～+100 |
| `enable_time_warp` | 是否隨機縮短或拉長資料時間軸，模擬不同動作速度。 | 已啟用 |
| `time_warp min/max` | 時間軸縮放倍率範圍。 | 0.8～1.3 倍 |
| `model_backbone` | 選擇 Model Architecture。 | 使用 `cnn` |
| `test_size` | Dataset 中保留作為 Validation 的檔案比例。 | 20% Validation、80% Training |
| `random_state` | Dataset Split 使用的 Random Seed。相同 Dataset 與 Seed 通常會得到相同切分。 | 42 |
| `epochs` | 完整訓練資料最多重複訓練幾輪。 | 最多 200 輪 |
| `batch_size` | 每次更新 Model Weight 使用多少 Samples。 | 每批 32 個 Samples |
| `learning_rate` | Optimizer 每次調整 Model Weight 的幅度。 | 0.001 |
| `label_smoothing` | 將標準 One-hot Label 稍微平滑化，避免 Model 過度自信。 | 0.08 |
| `EarlyStop Patience` | `val_loss` 沒有改善後，最多再等待幾個 Epoch。 | 等待 15 次 |
| `ReduceLR Patience` | `val_loss` 沒有改善後，等待幾個 Epoch 才降低 Learning Rate。 | 等待 10 次 |

## Detect table

![Detection Settings](https://hackmd.io/_uploads/rkXUhuR_zl.png)

### Dynamic Gesture

| 名稱 | 說明 |
|---|---|
| `Dynamic Result` | 顯示多個 Stable Gesture 依序組合後得到的 Dynamic Gesture。 |
| `Dynamic gestures JSON` | 定義 Dynamic Gesture 名稱、Gesture Sequence 與允許時間的 JSON 設定檔。 |
| `Browse...` | 選擇 Dynamic Gesture JSON 檔案。 |

### CNN Post-Processing

| 名稱 | 說明 |
|---|---|
| `Smoothing Alpha` | Probability 的 EWMA 平滑係數。數值越小越穩定但反應較慢；越大反應越快但容易抖動。 |
| `Switching Margin` | 從目前 Active Gesture 切換到新 Gesture 時，新 Gesture 必須領先的最小機率差。 |
| `Latch Exit Thresh` | Active Gesture 的機率低於此門檻時，解除目前的 Gesture 鎖定。 |
| `Inference Stride` | UART 每累積幾筆有效 Sensor Data 才執行一次 `predict()`。所有資料仍會進入 Model Buffer。 |
| `Slope Factor` | 放大相鄰 Sensor Data 的變化量，應與 Training 使用的設定一致。 |
| `Global Defaults` | 定義 Fast、Normal、Strict 三種 Gesture 判斷等級的預設條件。 |
| `Tier` | Gesture 的判斷等級，分為 Fast、Normal 與 Strict。 |
| `Stable` | 相同 Gesture 必須連續成為最佳候選的推論次數。 |
| `Thresh` | Gesture Probability 必須達到的最低門檻。 |

### Tier 設定

| Tier | Stable | Thresh | 說明 |
|---|---:|---:|---|
| `Fast` | 0 | 0.70 | Probability 達到 70% 後立即接受，適合需要快速反應的 Gesture。 |
| `Normal` | 10 | 0.50 | Probability 達到 50%，且連續穩定 10 次推論後接受。 |
| `Strict` | 20 | 0.75 | Probability 達到 75%，且連續穩定 20 次推論後接受，適合容易誤判的 Gesture。 |

### Manual HOLDAVG

| 名稱 | 說明 |
|---|---|
| `Enable manual holdavg` | UART 沒有提供 `SILHOLD`／`HOLDAVG` 時，允許使用畫面設定的手動 HOLDAVG。 |
| `CH` | Sensor Channel 編號，例如 CH1～CH6。 |
| `holdavg` | 該 Channel 在 Hold 狀態下的平均 Sensor 值，用於正規化與 Gain 計算。 |

### Gain Map

| 名稱 | 說明 |
|---|---|
| `Gain Map (align B → A)` | 將目前裝置 B 的 Sensor 變化幅度對齊 Training 使用的標準裝置 A。 |
| `Enable gain map` | 是否啟用跨裝置 Sensor 尺度修正。未啟用時，各 Channel Gain 維持 `1.0`。 |
| `STD_BASELINE_A` | 標準裝置 A 在基準狀態下的 Sensor 值。 |
| `STD_HOLDAVG_A` | 標準裝置 A 在 Hold 狀態下的平均 Sensor 值。 |
| `span_A` | 標準裝置跨度，計算方式為 `abs(STD_HOLDAVG_A - STD_BASELINE_A)`。 |
| `span_B` | 目前裝置跨度，計算方式為 `abs(current_hold_B - current_base_B)`。 |
| `gain` | 尺度修正倍率，計算方式為 `span_A / span_B`。 |

## Gen Code Table

![Gen Code Main](https://hackmd.io/_uploads/rkjPj1ZtGg.png)

![Gen Code Tiers](https://hackmd.io/_uploads/BJh_jyWFfg.png)

| 名稱 | 說明 |
|---|---|
| `Smoothing Alpha` | Probability 的 EWMA 平滑係數。越小越穩定但反應較慢；越大反應越快但容易抖動。 |
| `Switching Margin` | 從目前 Gesture 切換到新 Gesture 時，新 Gesture 必須領先的最小機率差。 |
| `Exit Threshold` | 目前 Active Gesture 機率低於此值時解除鎖定。 |
| `Inference Stride` | MCU 每累積幾筆資料才執行一次 CNN 推論。 |
| `Slope Factor` | 放大相鄰 Sensor Data 的變化量，必須和 Training 設定一致。 |
| `Tier Definitions` | 設定 Fast、Normal、Strict 三種判斷等級的預設 Stable 與 Threshold。 |
| `Gesture Tiers` | 為每一個 Gesture 指定 Tier，也可顯示實際套用的 Stable 與 Threshold。 |
