#ifndef SIL_APP_RTC_H
#define SIL_APP_RTC_H

#include "..\timer_rtc\sil_rtc.h"

/*
#if defined(__ICCARM__)

void R_BSP_WarmStart(bsp_warm_start_event_t event);

 #pragma weak R_BSP_WarmStart

#elif defined(__GNUC__) || defined(__ARMCC_VERSION)

void R_BSP_WarmStart(bsp_warm_start_event_t event) __attribute__((weak));

#endif
// */

void SIL_APP_RTC_SetTime(rtc_time_t *time);
void SIL_APP_RTC_GetTime(rtc_time_t *time);
fsp_err_t SIL_APP_RTC_Enter1();
fsp_err_t SIL_APP_RTC_Enter2();
void SIL_APP_RTC_MainLoop1();
void SIL_APP_RTC_MainLoop2();

































#endif //#ifndef SIL_APP_RTC_H
