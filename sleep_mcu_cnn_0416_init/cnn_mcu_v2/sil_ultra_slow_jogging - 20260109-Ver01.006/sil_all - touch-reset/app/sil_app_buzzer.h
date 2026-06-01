#ifndef SIL_APP_BUZZER_H
#define SIL_APP_BUZZER_H

#include "..\timer_pwm\sil_pwm.h"

/*
#if defined(__ICCARM__)

void R_BSP_WarmStart(bsp_warm_start_event_t event);

 #pragma weak R_BSP_WarmStart

#elif defined(__GNUC__) || defined(__ARMCC_VERSION)

void R_BSP_WarmStart(bsp_warm_start_event_t event) __attribute__((weak));

#endif
// */

typedef enum SIL_APP_BUZZER_BEEP_S {
    APP_BUZZER_BEEP_UNKNOWN_E = -1,
    APP_BUZZER_BEEP_1 = 0,	// 800
    APP_BUZZER_BEEP_2,		// 900
	APP_BUZZER_BEEP_3,		// 1000
	APP_BUZZER_BEEP_4,		// 1100
	APP_BUZZER_BEEP_5,		// 1200
	APP_BUZZER_BEEP_6,		// 1300

    APP_BUZZER_BEEP_FINAL_E,
    APP_BUZZER_BEEP_MAXS_E = (APP_BUZZER_BEEP_FINAL_E + 2)

} sil_app_buzzer_beep_e;

typedef struct SIL_APP_BUZZER_S {
	sil_pwm_s pwm;
	uint8_t reset_in_software;

} sil_app_buzzer_s;

void SIL_APP_BUZZER_SetDuty(uint8_t duty);
void SIL_APP_BUZZER_TimerLoop();
void SIL_APP_BUZZER_Off();

// 800: beep 1, 
// 900: beep 2, 
// 1000: beep 3
// 1100: beep 4
// 1200: beep 5
// 1300: beep 6
void SIL_APP_BUZZER_On(sil_app_buzzer_beep_e n);	
void SIL_APP_BUZZER_SetSoftwareReset(uint8_t reset);



fsp_err_t SIL_APP_BUZZER_Enter1();
fsp_err_t SIL_APP_BUZZER_Enter2();
void SIL_APP_BUZZER_MainLoop1();
void SIL_APP_BUZZER_MainLoop2();

































#endif //#ifndef SIL_APP_BUZZER_H
