#ifndef SIL_APP_USJ_H
#define SIL_APP_USJ_H

#include "..\globals\sil_globals.h"
#include "..\touch\sil_touch.h"
#include "..\algorithm\sil_steps_cnt.h"
#include "..\app\sil_app_touch.h"

/*
#if defined(__ICCARM__)

void R_BSP_WarmStart(bsp_warm_start_event_t event);

 #pragma weak R_BSP_WarmStart

#elif defined(__GNUC__) || defined(__ARMCC_VERSION)

void R_BSP_WarmStart(bsp_warm_start_event_t event) __attribute__((weak));

#endif
// */

#ifdef SILCNTS_GLOBALS_CHS_RIGHT
#	define SILCNTS_APP_USJ_CHS_RIGHT SILCNTS_GLOBALS_CHS_RIGHT
#else 
#	define SILCNTS_APP_USJ_CHS_RIGHT 2	
#endif

#ifdef SILCNTS_GLOBALS_CHS_LEFT
#	define SILCNTS_APP_USJ_CHS_LEFT SILCNTS_GLOBALS_CHS_LEFT
#else 
#	define SILCNTS_APP_USJ_CHS_LEFT 2
#endif

#ifdef SILCNTS_GLOBALS_TOPC_N_TIMES_TOBLE
#	define SILCNTS_APP_USJ_TOPC_N_TIMES_TOBLE SILCNTS_GLOBALS_TOPC_N_TIMES_TOBLE
#else
#	define SILCNTS_APP_USJ_TOPC_N_TIMES_TOBLE 7	
#endif

#ifdef SILCNTS_GLOBALS_FORCE_RESET_AFTER_N_SECS
#	define SILCNTS_APP_USJ_FORCE_RESET_AFTER_N_SECS SILCNTS_GLOBALS_FORCE_RESET_AFTER_N_SECS
#else
#	define SILCNTS_APP_USJ_FORCE_RESET_AFTER_N_SECS 30	
#endif



typedef struct SIL_APP_USJ_S {

	uint16_t a_data_ch[SILCNTS_APP_USJ_CHS_RIGHT + SILCNTS_APP_USJ_CHS_LEFT];
	uint8_t a_data_len;

	uint32_t count;
	uint32_t force_reset_count;
	uint32_t force_reset_thrd;

	uint8_t chs_l;
	sil_steps_cnt_s steps_l;

	uint8_t chs_r;
	sil_steps_cnt_s steps_r;

	uint8_t chs_jumps;
	sil_steps_cnt_s jumps;

	timer_instance_t *p_timer;
	
	
	
	
	
	
	
	// bottom
	sil_app_type_e *p_app;
	
} sil_app_usj_s;


void SIL_APP_USJ_OutputSteps();
void SIL_APP_USJ_CountSteps();
void SIL_APP_USJ_SwitchType(sil_app_type_e app);

void SIL_APP_USJ_GetChannelsDataPeriod();
fsp_err_t SIL_APP_USJ_Enter1();
fsp_err_t SIL_APP_USJ_Enter2();
void SIL_APP_USJ_MainLoop1();
void SIL_APP_USJ_MainLoop2();

































#endif //#ifndef SIL_APP_USJ_H
