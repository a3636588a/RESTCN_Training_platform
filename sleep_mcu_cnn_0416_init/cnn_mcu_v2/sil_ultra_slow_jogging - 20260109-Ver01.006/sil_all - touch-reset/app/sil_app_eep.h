#ifndef SIL_APP_EEP_H
#define SIL_APP_EEP_H

#include "..\flash\sil_flash.h"
#include "..\touch\sil_touch.h"

/*
#if defined(__ICCARM__)

void R_BSP_WarmStart(bsp_warm_start_event_t event);

 #pragma weak R_BSP_WarmStart

#elif defined(__GNUC__) || defined(__ARMCC_VERSION)

void R_BSP_WarmStart(bsp_warm_start_event_t event) __attribute__((weak));

#endif
// */

#define SILCNTS_APP_EEP_START_ADDR	0
#define SILCNTS_APP_EEP_KG_ZERO	0
#define SILCNTS_APP_EEP_KG_HIGH	13

#pragma pack(push, 1)
typedef struct SIL_APP_EEP_S {
	
	// calibrated data.
    uint8_t chs_ttl_lr; // total channels: left channels + right channels
    uint16_t a_value_zero[TOUCH_CHS_FINAL_E];   // get from a_data_zero_max of "struct sil_touch_s"
    uint16_t a_value_high[TOUCH_CHS_FINAL_E];
	uint16_t a_kg_zero[TOUCH_CHS_FINAL_E];   // get from a_data_zero_max of "struct sil_touch_s"
    uint16_t a_kg_high[TOUCH_CHS_FINAL_E];
	
	

	uint32_t cs;            // checksum. xor every 4 bytes from "chs_ttl_left" to befor "cs"
	uint8_t dirty;
} __attribute__((packed)) sil_app_eep_s;
#pragma pack(pop)

uint32_t SIL_APP_EEP_GetChecksum(uint8_t *buf, uint16_t len);
fsp_err_t SIL_APP_EEP_Enter1();
fsp_err_t SIL_APP_EEP_Enter2();
void SIL_APP_EEP_MainLoop1();
void SIL_APP_EEP_MainLoop2();

































#endif //#ifndef SIL_APP_EEP_H
