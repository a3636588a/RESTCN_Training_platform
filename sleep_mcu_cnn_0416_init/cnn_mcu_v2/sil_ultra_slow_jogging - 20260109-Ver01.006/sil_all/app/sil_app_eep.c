#include "sil_app_eep.h"
#include "..\flash\sil_flash_data.h"
#include <stdlib.h>
#include <stdio.h>

sil_app_eep_s gsil_app_eep = {
								//uint8_t chs_ttl_lr; // total channels: left channels + right channels
								TOUCH_CHS_FINAL_E,

								//uint16_t a_value_zero[TOUCH_CHS_FINAL_E];   // get from a_data_zero_max of "struct sil_touch_s"
								{0x55, 0x55, 0x55, 0x55},
								
								//uint16_t a_value_high[TOUCH_CHS_FINAL_E];
								{0x55AA, 0x55AA, 0x55AA, 0x55AA},
								
								//uint16_t a_kg_zero[TOUCH_CHS_FINAL_E];   // get from a_data_zero_max of "struct sil_touch_s"
								{
									SILCNTS_APP_EEP_KG_ZERO, 
									SILCNTS_APP_EEP_KG_ZERO, 
									SILCNTS_APP_EEP_KG_ZERO, 
									SILCNTS_APP_EEP_KG_ZERO
								},
								
								//uint16_t a_kg_high[TOUCH_CHS_FINAL_E];
								{
									SILCNTS_APP_EEP_KG_HIGH, 
									SILCNTS_APP_EEP_KG_HIGH, 
									SILCNTS_APP_EEP_KG_HIGH, 
									SILCNTS_APP_EEP_KG_HIGH
								},
								
								//uint32_t cs;            // checksum. xor every 4 bytes from "chs_ttl_left" to befor "cs"
								0,
								
								//uint8_t dirty;
								0
							};


uint32_t SIL_APP_EEP_GetChecksum(uint8_t *buf, uint16_t len) {
	uint32_t cs = 0;
	uint8_t dat[sizeof(uint32_t)] = {0, 0, 0, 0};
	uint32_t *p_dat = (uint32_t *)dat;
	uint16_t i = 0;
	uint16_t len_alignment = 0;
	
	if (buf) {
		
		len_alignment = (uint16_t)((len + (sizeof(uint32_t) - 1)) / sizeof(uint32_t));	// alignment sizeof(uint32_t) -- 4 bytes
		len_alignment = len_alignment * sizeof(uint32_t);

		memset(dat, 0x00, sizeof(dat));

		for (i = 0; i < len_alignment; i ++) {
			
			if (i < len) dat[i % sizeof(uint32_t)] = buf[i];
			else dat[i % sizeof(uint32_t)] = 0;

			if ((i % sizeof(uint32_t)) == (sizeof(uint32_t) - 1)) {
				cs ^= *p_dat;
			}
		}
	}
	
	return cs;
}

fsp_err_t SIL_APP_EEP_Enter1() {
	fsp_err_t err = FSP_SUCCESS;
	
	gsil_app_eep.cs = SIL_APP_EEP_GetChecksum(
												(uint8_t *)&gsil_app_eep, 
												sizeof(gsil_app_eep) - sizeof(uint32_t) - sizeof(uint8_t)
												);
	gsil_app_eep.dirty = 0;
	
	return err;
}

fsp_err_t SIL_APP_EEP_Enter2() {

	fsp_err_t err = FSP_ERR_INVALID_ARGUMENT;
	sil_app_eep_s eep;
	uint16_t len = 0;
	uint32_t cs = 0;

	len = sizeof(eep);
	err = SIL_FLASH_DATA_Read(SILCNTS_APP_EEP_START_ADDR, (uint8_t *) &eep, &len);

	if ((err == FSP_SUCCESS) && (len == sizeof(eep))) {
		cs = SIL_APP_EEP_GetChecksum(
									(uint8_t *)&eep, 
									sizeof(eep) - sizeof(uint32_t) - sizeof(uint8_t)
									);
		
		gsil_app_eep.dirty = 0;
		if (cs != eep.cs) gsil_app_eep.dirty = 1;
		else gsil_app_eep = eep;
			
	}
	
	return err;
}

void SIL_APP_EEP_MainLoop1() {
	fsp_err_t err = FSP_ERR_INVALID_ARGUMENT;
	
	(void) err;

	if (gsil_app_eep.dirty) {
		gsil_app_eep.dirty = 0;
		err = SIL_FLASH_DATA_WriteToCache(SILCNTS_APP_EEP_START_ADDR, (uint8_t *)&gsil_app_eep, sizeof(gsil_app_eep));
	}
	
}

void SIL_APP_EEP_MainLoop2() {
	

	
}




