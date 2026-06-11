#ifndef SIL_FLASH_H
#define SIL_FLASH_H

#include "..\globals\sil_globals.h"
#include <stdbool.h>

/*
#if defined(__ICCARM__)

void R_BSP_WarmStart(bsp_warm_start_event_t event);

 #pragma weak R_BSP_WarmStart

#elif defined(__GNUC__) || defined(__ARMCC_VERSION)

void R_BSP_WarmStart(bsp_warm_start_event_t event) __attribute__((weak));

#endif
// */

// we just use 1K Bytes data flash
#define SILCNTS_FLASH_DATA_SIZE	1024
#define SILCNTS_FLASH_DATA_WRITE_TIMEOUT_COUNT	512

typedef enum SIL_FLASH_WR_STS_E {
	FLASH_WR_STS_UNKNOWN_E = -1,
	FLASH_WR_STS_GET_BLK_INDEX,
	FLASH_WR_STS_ERASE,
	FLASH_WR_STS_BLANK_CHECK,
	FLASH_WR_STS_WRITE,
	FLASH_WR_STS_VERIFY,

	FLASH_WR_STS_FINAL_E,
	FLASH_WR_STS_MAXS_E = (FLASH_WR_STS_FINAL_E + 2)

} sil_flash_wr_sts_e;

typedef struct SIL_FLASH_S {
	
//const flash_instance_t g_flash0 =
//{ .p_ctrl = &g_flash0_ctrl, .p_cfg = &g_flash0_cfg, .p_api = &g_flash_on_flash_hp };
	flash_instance_t *p_flash;

	bool flag_erase_complete;
    bool flag_write_complete;
    bool flag_event_blank;
    bool flag_event_not_blank;
    bool flag_event_error;
	flash_event_t event_error_type;
	flash_info_t info;
	

	bool flag_bgo;
	uint8_t *p_data;
	uint16_t data_len;
	uint32_t data_dirty;
	uint32_t index_wr_curr;
	uint16_t count_wr_reset;
	sil_flash_wr_sts_e sts_wr;

} sil_flash_s;


void SIL_FLASH_FlushWriteBuffer(sil_flash_s *obj);
fsp_err_t SIL_FLASH_Read(sil_flash_s *obj, uint16_t start, uint8_t *buf, uint16_t *size);
fsp_err_t SIL_FLASH_WriteToCache(sil_flash_s *obj, uint16_t start, uint8_t *buf, uint16_t size);
void SIL_FLASH_Callback(sil_flash_s *obj, flash_callback_args_t *p_args);
fsp_err_t SIL_FLASH_Enter1(sil_flash_s *obj, flash_instance_t *flash);
fsp_err_t SIL_FLASH_Enter2(sil_flash_s *obj);
void SIL_FLASH_MainLoop1();
void SIL_FLASH_MainLoop2();

























#endif //#ifndef SIL_FLASH_H
