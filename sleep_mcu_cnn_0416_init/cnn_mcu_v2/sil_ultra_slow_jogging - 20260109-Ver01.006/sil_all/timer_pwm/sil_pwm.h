#ifndef SIL_PWM_H
#define SIL_PWM_H

#include "..\globals\sil_globals.h"

/*
#if defined(__ICCARM__)

void R_BSP_WarmStart(bsp_warm_start_event_t event);

 #pragma weak R_BSP_WarmStart

#elif defined(__GNUC__) || defined(__ARMCC_VERSION)

void R_BSP_WarmStart(bsp_warm_start_event_t event) __attribute__((weak));

#endif
// */


#define SILCNTS_PWM_DUTY_DFT	65
												// RA6M5	// RA6M2
#define SILCNTS_PWM_BEEP_ONE_MINIMUM_TIME_MS 	100			// 800
#define SILCNTS_PWM_BEEP_USED_TIMER_PERIOD_US 62500 

typedef struct SIL_PWM_S {
//const timer_instance_t g_timer3 =
//{ .p_ctrl = &g_timer3_ctrl, .p_cfg = &g_timer3_cfg, .p_api = &g_timer_on_gpt };
	timer_instance_t *p_pwm;
	
	uint8_t output_on;	// 1: output on, 0: output off
	uint8_t duty;
	uint32_t count_62500us;
	

} sil_pwm_s;

void SIL_PWM_TimerLoop(sil_pwm_s *obj);	// 16Hz timer
void SIL_PWM_Off(sil_pwm_s *obj);
void SIL_PWM_On(sil_pwm_s *obj, uint32_t ms);
void SIL_PWM_SetDuty(sil_pwm_s *obj, uint8_t duty);
fsp_err_t SIL_PWM_Enter1(sil_pwm_s *obj, timer_instance_t *tmr);
fsp_err_t SIL_PWM_Enter2(sil_pwm_s *obj);
void SIL_PWM_MainLoop1(sil_pwm_s *obj);
void SIL_PWM_MainLoop2(sil_pwm_s *obj);

































#endif //#ifndef SIL_PWM_H
