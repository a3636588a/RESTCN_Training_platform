# TinyOL Head 快閃記憶體 (Code Flash) 儲存問題與修正記錄

本專案中針對將 TinyOL 自訂/活動權重 (Active Head) 儲存至 Code Flash 時遇到的擦除失敗問題，在此進行記錄，以便回溯與追蹤。

---

## 1. 遭遇問題現象

在使用 AT 指令 `$SILOLAPPLY` 寫入 Head 資料，或是進行快閃記憶體診斷測試時，終端機回傳以下錯誤記錄：

```text
[RX] $SILNOTIFY,TINYOL,FLASHTEST,ERASE_START,addr=0x000E8000,len=98304,err=0,FAWMON=0x80008000,FSTATR=0x00008000*48
[RX] $SILNOTIFY,TINYOL,FLASHTEST,ERASE_FAIL,addr=0x000E8000,len=8192,err=25,FAWMON=0x80008000,FSTATR=0x00008000*09
[RX] $SILNOTIFY,TINYOL,FLASH,APPLY_ERASE_START,addr=0x000E8000,len=12,val=0,FAWMON=0x80008000,FSTATR=0x00008000*7E
[RX] $SILNOTIFY,TINYOL,FLASH,APPLY_ERASE_FAIL,addr=0x000E8000,len=12,val=25,FAWMON=0x80008000,FSTATR=0x00008000*0B
```

* 錯誤代碼 `25` 代表 `FSP_ERR_ERASE_FAILED` (擦除失敗)。
* `FAWMON` 暫存器值為 `0x80008000` (FSPR 解鎖且 Access Window 設定為區塊 0，代表防寫保護未啟用)。
* `FSTATR` 在擦除操作後顯示為 `0x00008000` (由於 Driver 退出 P/E 模式時已發送清除狀態命令，故讀回為正常狀態)。

---

## 2. 根本原因分析

1. **快閃記憶體區塊大小 (Block Size) 的實體差異：**
   Renesas RA6M5 的 Code Flash (Flash HP) 物理上分為兩個不同的區域：
   - **Region 0** (`0x00000000` ~ `0x0000FFFF`，共 64KB)：每個 Block 的大小為 **8KB**。
   - **Region 1** (`0x00010000` 之後)：每個 Block 的大小為 **32KB**。

2. **程式碼計算數量時誤用 Region 0 的 8KB：**
   - 目前劃分給儲存 Head 的專用區段 `FLASH_CM33_C` 位址為 `0x000E8000` (大小 `0x18000` / 96KB)，顯然位在 **Region 1** 內，其每個 Block 的實體大小是 **32KB**。
   - 但程式碼中原先是直接讀取 Block Array 的第一個元素：
     ```c
     block_size = flash_info.code_flash.p_block_array->block_size;
     ```
     這只拿到了 Region 0 的 Block 大小（即 `8KB`）。
   - 程式隨後以 `96KB` 空間除以 `8KB`，算出了 `12` 個 Block，並將 `12` 作為參數傳給 FSP 的擦除 API：
     ```c
     err = R_FLASH_HP_Erase(&g_flash0_ctrl, 0x000E8000, 12);
     ```

3. **實體位址越界導致硬體出錯：**
   - FSP Driver 內部依據起點 `0x000E8000` 屬於 Region 1，使用 **32KB** 作為 Block 大小執行擦除。
   - 當傳入 `num_blocks = 12` 時，Driver 會嘗試擦除 `12 * 32KB = 384KB` 的位址範圍，亦即從 `0x000E8000` 擦除到 `0x00148000`。
   - 由於這顆 RA6M5 晶片的快閃記憶體實體大小為 **1MB** (`0x00100000`)，位址高於 `0x00100000` 後已無實體記憶體，寫入硬體暫存器引發非法位址錯誤，導致擦除操作失敗。
   - 單獨擦除 1 個 Block 會成功，是因為 1 個 32KB Block (`0x000E8000` ~ `0x000F0000`) 未超出 1MB 的實體快閃記憶體邊界。

---

## 3. 解決方案 (待修改計畫)

我們需要讓程式碼動態取得正確的 Block 大小：
1. 新增 `SIL_APP_TINYOL_GetBlockSize` 函式，若位址高於 `64KB`，則使用 `32KB` 作為 Block 大小。
2. 修正 `SIL_APP_TINYOL_EraseActiveHead`、`SIL_APP_TINYOL_ApplyActiveHeadToFlash` 與 `RunFlashBlockTest`。
3. 計算後，要擦除整個 `96KB` 空間，Block 數量將精確計算為 `3` 個 Block (`3 * 32KB = 96KB`)，完美避免越界出錯。
