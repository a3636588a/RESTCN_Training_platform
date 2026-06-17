/*
                  Linker File for Renesas FSP
*/

INCLUDE memory_regions.ld

/* =========================================================================
   【1MB 晶片雙 Slot 運行起點強行覆蓋配置區】
   預設情況下，FSP 自動生成的 FLASH_START 已經是 Slot 1 的 0x00008100。
   如果您需要手動指定此 APP 特定運行在特定的 Slot 中，請在此切換註解：
   ========================================================================= */

/*FLASH_START = 0x00000000;*/

/* 🟢 編譯為 Slot 1 (APP1) 運行（預設起點：32KB BL + 256B Header 偏移 = 0x8100） */
/*FLASH_START = 0x00008100; */

/* 🔵 編譯為 Slot 2 (APP2) 運行（起點：448KB Slot 2 + 256B Header 偏移 = 0x00078100）
   (如果要特定編譯給 Slot 2 運行，請「取消」下方這行的註解，並將上方的 Slot 1 「加上」註解) */
/*FLASH_START = 0x00078100;*/


FLASH_START = 0x00008100;

INCLUDE fsp_gen.ld
