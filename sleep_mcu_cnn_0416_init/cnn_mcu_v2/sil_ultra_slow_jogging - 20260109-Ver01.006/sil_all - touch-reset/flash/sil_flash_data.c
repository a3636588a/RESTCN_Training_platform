#include "sil_flash_data.h"
#include <stdlib.h>

sil_flash_s gsil_flash_data;

void SIL_FLASH_DATA_Callback(flash_callback_args_t *p_args) {
	SIL_FLASH_Callback(&gsil_flash_data, p_args);
}

fsp_err_t SIL_FLASH_DATA_Read(uint16_t start, uint8_t *buf, uint16_t *size) {
	return SIL_FLASH_Read(&gsil_flash_data, start, buf, size);
}

fsp_err_t SIL_FLASH_DATA_WriteToCache(uint16_t start, uint8_t *buf, uint16_t size) {
	return SIL_FLASH_WriteToCache(&gsil_flash_data, start, buf, size);
}	

fsp_err_t SIL_FLASH_DATA_Enter1() {
	return SIL_FLASH_Enter1(&gsil_flash_data, (flash_instance_t *)&SILVAR_FLASH_HANDLER);
}

fsp_err_t SIL_FLASH_DATA_Enter2() {

    return SIL_FLASH_Enter2(&gsil_flash_data);
}

void SIL_FLASH_DATA_MainLoop1() {
    SIL_FLASH_MainLoop1(&gsil_flash_data);
}

void SIL_FLASH_DATA_MainLoop2() {
    SIL_FLASH_MainLoop2(&gsil_flash_data);
}




