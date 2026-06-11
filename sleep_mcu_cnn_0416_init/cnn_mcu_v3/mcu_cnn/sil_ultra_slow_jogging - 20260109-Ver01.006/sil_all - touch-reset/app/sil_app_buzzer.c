#include "sil_app_buzzer.h"
#include "..\uart_dtc\sil_uart_dtc_topc.h"
#include <stdlib.h>
#include <stdio.h>


sil_app_buzzer_s gsil_app_buzzer;
__attribute__((section(".noinit"))) uint8_t gsil_app_reset_in_software = 0;

void SIL_APP_BUZZER_SetSoftwareReset(uint8_t reset) {

	if (reset) gsil_app_reset_in_software = 1;
	else gsil_app_reset_in_software = 0;
	
}

void SIL_APP_BUZZER_SetDuty(uint8_t duty) {
	SIL_PWM_SetDuty(&gsil_app_buzzer.pwm, duty);
}
void SIL_APP_BUZZER_TimerLoop() {
	SIL_PWM_TimerLoop(&gsil_app_buzzer.pwm);	// 16Hz timer
}

void SIL_APP_BUZZER_Off() {
	SIL_PWM_Off(&gsil_app_buzzer.pwm);
}

void SIL_APP_BUZZER_On(sil_app_buzzer_beep_e n) {
	
	uint16_t ms = 0;

	switch (n) {			// RA6M2,	RA6M5
	case APP_BUZZER_BEEP_1:	// 800		140
		ms = 140;
		break;
	case APP_BUZZER_BEEP_2:	// 900		280
		ms = 280;
		break;
	case APP_BUZZER_BEEP_3:	// 1000		420
		ms = 420;
		break;
	case APP_BUZZER_BEEP_4:	// 1100		560
		ms = 560;
		break;
	case APP_BUZZER_BEEP_5:	// 1200		700
		ms = 700;
		break;
	case APP_BUZZER_BEEP_6:	// 1300		840
		ms = 840;
		break;
	default:
		ms = 0;
		break;
	}

	if (gsil_app_buzzer.reset_in_software) gsil_app_buzzer.reset_in_software = 0;
	else SIL_PWM_On(&gsil_app_buzzer.pwm, ms);
}

fsp_err_t SIL_APP_BUZZER_Enter1() {

	gsil_app_buzzer.reset_in_software = 0;
	if (gsil_app_reset_in_software) {
		gsil_app_buzzer.reset_in_software = 1;
		gsil_app_reset_in_software = 0;
	}
	return SIL_PWM_Enter1(&gsil_app_buzzer.pwm, (timer_instance_t *)&SILVAR_TMR_BUZZER);
}

fsp_err_t SIL_APP_BUZZER_Enter2() {
	
	return SIL_PWM_Enter2(&gsil_app_buzzer.pwm);
}

void SIL_APP_BUZZER_MainLoop1() {
	SIL_PWM_MainLoop1(&gsil_app_buzzer.pwm);
}

void SIL_APP_BUZZER_MainLoop2() {
	
	SIL_PWM_MainLoop2(&gsil_app_buzzer.pwm);
	
}




