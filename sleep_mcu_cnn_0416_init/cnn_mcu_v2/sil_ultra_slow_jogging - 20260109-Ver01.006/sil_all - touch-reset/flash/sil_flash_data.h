#ifndef SIL_FLASH_DATA_H
#define SIL_FLASH_DATA_H

#include "..\globals\sil_globals.h"
#include "..\flash\sil_flash.h"

/*
#if defined(__ICCARM__)

void R_BSP_WarmStart(bsp_warm_start_event_t event);

 #pragma weak R_BSP_WarmStart

#elif defined(__GNUC__) || defined(__ARMCC_VERSION)

void R_BSP_WarmStart(bsp_warm_start_event_t event) __attribute__((weak));

#endif
// */





fsp_err_t SIL_FLASH_DATA_Read(uint16_t start, uint8_t *buf, uint16_t *size);
fsp_err_t SIL_FLASH_DATA_WriteToCache(uint16_t start, uint8_t *buf, uint16_t size);
void SIL_FLASH_DATA_Callback(flash_callback_args_t *p_args);
fsp_err_t SIL_FLASH_DATA_Enter1();
fsp_err_t SIL_FLASH_DATA_Enter2();
void SIL_FLASH_DATA_MainLoop1();
void SIL_FLASH_DATA_MainLoop2();

































#endif //#ifndef SIL_FLASH_DATA_H
