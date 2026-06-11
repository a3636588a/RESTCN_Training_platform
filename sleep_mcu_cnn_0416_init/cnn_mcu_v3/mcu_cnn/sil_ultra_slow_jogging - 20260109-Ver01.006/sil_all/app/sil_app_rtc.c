#include "sil_app_rtc.h"
#include "..\uart_dtc\sil_uart_dtc_topc.h"
#include <stdlib.h>
#include <stdio.h>

__attribute__((section(".noinit"))) sil_rtc_s gsil_app_rtc;
//__attribute__((section(".noinit"))) uint32_t abc = 0;


void SIL_APP_RTC_GetTime(rtc_time_t *time) {
	uint8_t buf[64];
	
	//static int cnt = 0;

	if (time == 0) time = &gsil_app_rtc.time_current;
	SIL_RTC_GetTime(&gsil_app_rtc, time);
	
	snprintf((char*)buf, 64, "\r\n%d-%02d-%02d-%02d:%02d:%02d\r\n",
						time->tm_year + 1900, 
						time->tm_mon + 1, 
						time->tm_mday,
						time->tm_hour, 
						time->tm_min, 
						time->tm_sec
						);

	//*if (cnt ++ % 2)*/ SIL_UART_DTC_TOPC_WriteToTxBuffer(buf, (uint16_t) strlen((char *)buf));
	
}

void SIL_APP_RTC_SetTime(rtc_time_t *time) {
	SIL_RTC_SetTime(&gsil_app_rtc, time);
}

fsp_err_t SIL_APP_RTC_Enter1() {
	return SIL_RTC_Enter1(&gsil_app_rtc, (rtc_instance_t *)&SILVAR_TMR_RTC);
}

fsp_err_t SIL_APP_RTC_Enter2() {
	
	return SIL_RTC_Enter2(&gsil_app_rtc);
}

void SIL_APP_RTC_MainLoop1() {
	SIL_RTC_MainLoop1();
}

void SIL_APP_RTC_MainLoop2() {
	
	SIL_RTC_MainLoop2();
	
}




