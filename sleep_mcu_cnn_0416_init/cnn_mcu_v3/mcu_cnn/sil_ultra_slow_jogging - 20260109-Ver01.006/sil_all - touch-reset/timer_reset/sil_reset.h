#ifndef SIL_PERIOD_RESET_H
#define SIL_PERIOD_RESET_H

#include "..\globals\sil_globals.h"

/*
#if defined(__ICCARM__)

void R_BSP_WarmStart(bsp_warm_start_event_t event);

 #pragma weak R_BSP_WarmStart

#elif defined(__GNUC__) || defined(__ARMCC_VERSION)

void R_BSP_WarmStart(bsp_warm_start_event_t event) __attribute__((weak));

#endif
// */


typedef struct SIL_PERIOD_RESET_S {
//const timer_instance_t g_timer1 =
//{ .p_ctrl = &g_timer1_ctrl, .p_cfg = &g_timer1_cfg, .p_api = &g_timer_on_agt };
	timer_instance_t *p_timer;
	uint32_t count_always;
	uint8_t ms_base;

} sil_period_reset_s;

void SIL_PERIOD_RESET_CountIncreasing(sil_period_reset_s *obj);
uint32_t SIL_PERIOD_RESET_GetMs(sil_period_reset_s *obj);
fsp_err_t SIL_PERIOD_RESET_Enter1(sil_period_reset_s *obj, timer_instance_t *tmr);
fsp_err_t SIL_PERIOD_RESET_Enter2(sil_period_reset_s *obj);
void SIL_PERIOD_RESET_MainLoop1();
void SIL_PERIOD_RESET_MainLoop2();

































#endif //#ifndef SIL_PERIOD_RESET_H
