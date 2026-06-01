#ifndef SIL_APP_TICKS_H
#define SIL_APP_TICKS_H

#include "..\globals\sil_globals.h"
#include "..\tick_sys\sil_tick_sys.h"
/*
#if defined(__ICCARM__)

void R_BSP_WarmStart(bsp_warm_start_event_t event);

 #pragma weak R_BSP_WarmStart

#elif defined(__GNUC__) || defined(__ARMCC_VERSION)

void R_BSP_WarmStart(bsp_warm_start_event_t event) __attribute__((weak));

#endif
// */

void SIL_APP_TICKS_Delay(uint32_t delay, sil_tick_sys_dly_e base);
void SIL_APP_TICKS_Decrease();

// sys_clock: clocks per 1 seconds
// freq: interrupt times per seconds
fsp_err_t SIL_APP_TICKS_Enter1();
fsp_err_t SIL_APP_TICKS_Enter2();
void SIL_APP_TICKS_MainLoop1();
void SIL_APP_TICKS_MainLoop2();

										



























#endif //#ifndef SIL_APP_TICKS_H
