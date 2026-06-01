#ifndef SIL_FILTER_MDN_H
#define SIL_FILTER_MDN_H

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

// public func.

// 

void SIL_FILTER_MDN_BubbleSort(uint16_t *dat, uint8_t size);
uint16_t SIL_FILTER_MDN_GetFiltered(uint16_t *window, uint8_t size);































#endif //#ifndef SIL_FILTER_MA_H
