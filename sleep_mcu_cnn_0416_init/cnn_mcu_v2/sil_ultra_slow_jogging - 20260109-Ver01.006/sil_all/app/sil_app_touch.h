#ifndef SIL_APP_TOUCH_H
#define SIL_APP_TOUCH_H

#include "..\globals\sil_globals.h"
#include "..\touch\sil_touch.h"


/*
#if defined(__ICCARM__)

void R_BSP_WarmStart(bsp_warm_start_event_t event);

 #pragma weak R_BSP_WarmStart

#elif defined(__GNUC__) || defined(__ARMCC_VERSION)

void R_BSP_WarmStart(bsp_warm_start_event_t event) __attribute__((weak));

#endif
// */

#ifdef SILCNTS_GLOBALS_CHS_RIGHT
#	define SILCNTS_APP_TOUCH_CHS_RIGHT SILCNTS_GLOBALS_CHS_RIGHT
#else 
#	define SILCNTS_APP_TOUCH_CHS_RIGHT 3	
#endif

#ifdef SILCNTS_GLOBALS_CHS_LEFT
#	define SILCNTS_APP_TOUCH_CHS_LEFT SILCNTS_GLOBALS_CHS_LEFT
#else 
#	define SILCNTS_APP_TOUCH_CHS_LEFT 3
#endif

#ifdef SILCNTS_GLOBALS_TOPC_N_TIMES_TOBLE
#	define SILCNTS_APP_TOUCH_TOPC_N_TIMES_TOBLE SILCNTS_GLOBALS_TOPC_N_TIMES_TOBLE
#else
#	define SILCNTS_APP_TOUCH_TOPC_N_TIMES_TOBLE 7	
#endif



typedef struct SIL_APP_TOUCH_S {

	sil_touch_s sensor;

	volatile uint32_t count;	

	
} sil_app_touch_s;

extern sil_app_touch_s gsil_app_touch;

fsp_err_t SIL_APP_TOUCH_StartScan();
void SIL_APP_TOUCH_GetAllChannelsData(uint16_t *data, uint8_t chs);
void SIL_APP_TOUCH_GetAllChannelsDataGlove(uint16_t *data, uint8_t chs);
void SIL_APP_TOUCH_RawDataToOutside();
fsp_err_t SIL_APP_TOUCH_GetChannelsDataPeriod();



fsp_err_t SIL_APP_TOUCH_Enter1();
fsp_err_t SIL_APP_TOUCH_Enter2();
void SIL_APP_TOUCH_MainLoop1();
void SIL_APP_TOUCH_MainLoop2();
void SIL_APP_TOUCH_Exit();
































#endif //#ifndef SIL_APP_TOUCH_H
