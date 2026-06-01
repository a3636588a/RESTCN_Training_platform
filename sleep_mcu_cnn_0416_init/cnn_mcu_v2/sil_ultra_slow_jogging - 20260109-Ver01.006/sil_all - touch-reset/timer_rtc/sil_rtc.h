#ifndef SIL_RTC_H
#define SIL_RTC_H

#include "..\globals\sil_globals.h"

/*
#if defined(__ICCARM__)

void R_BSP_WarmStart(bsp_warm_start_event_t event);

 #pragma weak R_BSP_WarmStart

#elif defined(__GNUC__) || defined(__ARMCC_VERSION)

void R_BSP_WarmStart(bsp_warm_start_event_t event) __attribute__((weak));

#endif
// */


// calandar
#ifdef SILCNTS_GLOBALS_APP_RELEASE_YEAR
#	define SILCNTS_RTC_YEAR_DFT  SILCNTS_GLOBALS_APP_RELEASE_YEAR
#else
#	define SILCNTS_RTC_YEAR_DFT  2025
#endif
#ifdef SILCNTS_GLOBALS_APP_RELEASE_MONTH
#	define SILCNTS_RTC_MON_DFT  SILCNTS_GLOBALS_APP_RELEASE_MONTH
#else
#	define SILCNTS_RTC_MON_DFT  11
#endif
#ifdef SILCNTS_GLOBALS_APP_RELEASE_DAT
#	define SILCNTS_RTC_MDAY_DFT  SILCNTS_GLOBALS_APP_RELEASE_DAT
#else
#	define SILCNTS_RTC_MDAY_DFT  1
#endif

#define SILCNTS_RTC_WDAY_DFT ( \
								(SILCNTS_RTC_YEAR_DFT - 2000 \
								+ ((SILCNTS_RTC_YEAR_DFT - 2000) / 4) \
								- 35 + (26 * (SILCNTS_RTC_MON_DFT + 1))/10 \
								+ SILCNTS_RTC_MDAY_DFT -1 ) % 7 \
								)


// time
#define SILCNTS_RTC_HOUR_DFT  0
#define SILCNTS_RTC_MIN_DFT  0
#define SILCNTS_RTC_SEC_DFT  0	
#define SILCNTS_RTC_UPDATE_THRD (1 * 3600)	// re-set current time every 8 hour



 



typedef struct SIL_RTC_S {
//const rtc_instance_t g_rtc0 =
//{ .p_ctrl = &g_rtc0_ctrl, .p_cfg = &g_rtc0_cfg, .p_api = &g_rtc_on_rtc };
	rtc_instance_t *p_rtc;
	
	rtc_time_t time_current;
	
	uint16_t count_update;
	

} sil_rtc_s;

void SIL_RTC_GetTime(sil_rtc_s *obj, rtc_time_t *time);
void SIL_RTC_SetTime(sil_rtc_s *obj, rtc_time_t *time);

fsp_err_t SIL_RTC_Enter1(sil_rtc_s *obj, rtc_instance_t *rtc);
fsp_err_t SIL_RTC_Enter2(sil_rtc_s *obj);
void SIL_RTC_MainLoop1();
void SIL_RTC_MainLoop2();

































#endif //#ifndef SIL_RTC_H
