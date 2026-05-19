#ifndef SIL_DTC_RESET_H
#define SIL_DTC_RESET_H

#include "..\globals\sil_globals.h"
#include "..\timer_reset\sil_reset.h"

/*
#if defined(__ICCARM__)

void R_BSP_WarmStart(bsp_warm_start_event_t event);

 #pragma weak R_BSP_WarmStart

#elif defined(__GNUC__) || defined(__ARMCC_VERSION)

void R_BSP_WarmStart(bsp_warm_start_event_t event) __attribute__((weak));

#endif
// */
void SIL_DTC_RESET_CountIncreasing();
uint32_t SIL_DTC_RESET_GetMs();
fsp_err_t SIL_DTC_RESET_Enter1();
fsp_err_t SIL_DTC_RESET_Enter2();
void SIL_DTC_RESET_MainLoop1();
void SIL_DTC_RESET_MainLoop2();

































#endif //#ifndef SIL_DTC_RESET_H
