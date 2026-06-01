#include "sil_globals.h"
#include "..\timer_reset\sil_dtc_reset.h"
#include "..\protocol_atcmds\sil_atcmds.h"
#include "..\uart_dtc\sil_uart_dtc_topc.h"
#include "..\uart_dtc\sil_uart_dtc_toble.h"
#include "..\app\sil_app_ultra_slow_jogging.h"
#include "..\flash\sil_flash_data.h"
#include "..\app\sil_app_rtc.h"
#include "..\app\sil_app_eep.h"
#include "..\app\sil_app_buzzer.h"
#include "..\app\sil_app_ticks.h"


static volatile sil_globals_sts_e gsil_globals_state = GLOBALS_STS_UNKNOWN_E;
__attribute__((section(".noinit"))) sil_app_type_e gsil_globals_current_app = SIL_APP_USJ_E;
__attribute__((section(".noinit"))) uint8_t gsil_globals_disable_boot_buzzer = 0;

void SIL_GLOBALS_SetBootBuzzer(uint8_t enable) {
	gsil_globals_disable_boot_buzzer = enable ? 0 : 1;
}

static uint8_t SIL_GLOBALS_GetBootBuzzerStatus() {
	return gsil_globals_disable_boot_buzzer ? 0 : 1;
}

sil_app_type_e *SIL_GLOBALS_GetPointerCurrentApp() {
	return &gsil_globals_current_app;
}

sil_globals_sts_e SIL_GLOBALS_GetStatus() {

	return gsil_globals_state;
}

static void SIL_GLOBALS_SetStatus(sil_globals_sts_e sts) {
	
	gsil_globals_state = sts;
}

fsp_err_t SIL_GLOBALS_Exit(void) {
	fsp_err_t err = FSP_ERR_UNSUPPORTED;



	return err;
}

void SIL_GLOBALS_Reboot() {
	NVIC_SystemReset();
	while (1);
}

// --> for ..\..\src\hal_entry.c
fsp_err_t SIL_GLOBALS_Enter1(void) {
	fsp_err_t err = FSP_ERR_UNSUPPORTED;
	char buf[64];
	

	SIL_DTC_RESET_Enter1();

	// tick app
	SIL_APP_TICKS_Enter1();

	// uart to PC
	SIL_UART_DTC_TOPC_Enter1();

	// uart to ble
	SIL_UART_DTC_TOBLE_Enter1();

	// atcmds
	SIL_ATCMDS_Enter1();

	// buzzer
	SIL_APP_BUZZER_Enter1();
	
	// flash data
	SIL_FLASH_DATA_Enter1();

	// eeprom data
	SIL_APP_EEP_Enter1();
	
	// rtc
	SIL_APP_RTC_Enter1();
	
	snprintf(buf, 64, 
					SILCNTS_GLOBALS_APP_FORMAT,
					SILCNTS_GLOBALS_APP_NAME,
					SILCNTS_GLOBALS_APP_RELEASE_YEAR,
					SILCNTS_GLOBALS_APP_RELEASE_MONTH,
					SILCNTS_GLOBALS_APP_RELEASE_DAT,
					SILCNTS_GLOBALS_APP_MAJOR_VER,
					SILCNTS_GLOBALS_APP_MINOR_VER,
					SILCNTS_GLOBALS_APP_CPU
					);

	// firmware version output
	SIL_UART_DTC_TOPC_WriteToTxBuffer(
	                                (uint8_t *)buf,
	                                (uint16_t)strlen(buf)
	                                );

	// banner to pc
	SIL_UART_DTC_TOPC_WriteToTxBuffer((uint8_t *)"SIL_GLOBALS_Enter1\r\n", (uint16_t) strlen("SIL_GLOBALS_Enter1\r\n"));
	
	// touch
	SIL_APP_TOUCH_Enter1();
	
	// usj app
	SIL_APP_USJ_Enter1();
	
	SIL_GLOBALS_SetStatus(GLOBALS_STS_ENTER2);
	return err;
}

fsp_err_t SIL_GLOBALS_Enter2(void) {
	fsp_err_t err = FSP_ERR_UNSUPPORTED;

	SIL_DTC_RESET_Enter2();

	// tick app
	SIL_APP_TICKS_Enter2();

	// uart to pc
	SIL_UART_DTC_TOPC_Enter2();

	// uart to ble
	SIL_UART_DTC_TOBLE_Enter2();

	// atcmds
	SIL_ATCMDS_Enter2();
	
	// buzzer
	SIL_APP_BUZZER_Enter2();
	
	// data flash
	SIL_FLASH_DATA_Enter2();

	// eeprom data
	SIL_APP_EEP_Enter2();
	
	// rtc
	SIL_APP_RTC_Enter2();
	
	// banner to PC
	SIL_UART_DTC_TOPC_WriteToTxBuffer((uint8_t *)"SIL_GLOBALS_Enter2\r\n", (uint16_t) strlen("SIL_GLOBALS_Enter2\r\n"));

	// touch
	SIL_APP_TOUCH_Enter2();

	// usj app
	SIL_APP_USJ_Enter2();

	SIL_GLOBALS_SetStatus(GLOBALS_STS_MAINLOOP1);

	return err;
}

fsp_err_t SIL_GLOBALS_MainLoop1(void) {
	fsp_err_t err = FSP_ERR_UNSUPPORTED;
	static uint32_t ms = 0;
	static uint8_t is_first = true;
	
	if (is_first) {
		SIL_UART_DTC_TOPC_WriteToTxBuffer((uint8_t *)"GLOBALS_STS_MAINLOOP1\r\n", (uint16_t) strlen("GLOBALS_STS_MAINLOOP1\r\n"));
		is_first = false;
	}

	// tick app
	SIL_APP_TICKS_MainLoop1();

	// to pc
	SIL_UART_DTC_TOPC_MainLoop1();
	// at commands
	SIL_ATCMDS_MainLoop1(ATCMDS_IO_TOPC);
	
	// to ble
	SIL_UART_DTC_TOBLE_MainLoop1();

	// at commands
	SIL_ATCMDS_MainLoop1(ATCMDS_IO_TOBLE);
	
	// buzzer
	SIL_APP_BUZZER_MainLoop1();
	
	// flash data
	SIL_FLASH_DATA_MainLoop1();
	
	// eeprom data
	SIL_APP_EEP_MainLoop1();
	
	// RTC
	SIL_APP_RTC_MainLoop1();
	
	// touch
	SIL_APP_TOUCH_MainLoop1();

	// usj app
	SIL_APP_USJ_MainLoop1();

		
	// the bottom
	ms = SIL_DTC_RESET_GetMs();
	if (ms >= SILCNTS_GLOBALS_RUN_MAINLOOP1_IN_MS) {
	    if (SIL_GLOBALS_GetBootBuzzerStatus()) SIL_APP_BUZZER_On(APP_BUZZER_BEEP_1);

        SIL_GLOBALS_SetBootBuzzer(1);
	    SIL_GLOBALS_SetStatus(GLOBALS_STS_MAINLOOP2);
	}
	
	return err;

}

fsp_err_t SIL_GLOBALS_MainLoop2(void) {
	fsp_err_t err = FSP_ERR_UNSUPPORTED;
	static volatile uint8_t is_first = true;
	static uint8_t delay = 150;

	if (is_first) {
	    while (delay -- ) {
	        SIL_APP_TICKS_Delay(1, SIL_TICK_SYS_DLY_MS_1);
	        // to pc
	        SIL_UART_DTC_TOPC_MainLoop2();
	        // to ble
	        SIL_UART_DTC_TOBLE_MainLoop2();
	    }
	    SIL_APP_BUZZER_Off();
		SIL_UART_DTC_TOPC_WriteToTxBuffer((uint8_t *)"GLOBALS_STS_MAINLOOP2\r\n", (uint16_t) strlen("GLOBALS_STS_MAINLOOP2\r\n"));
		is_first = false;
	}
	
	// tick app
	SIL_APP_TICKS_MainLoop2();

	// to pc
	SIL_UART_DTC_TOPC_MainLoop2();
	// at commands
	SIL_ATCMDS_MainLoop2(ATCMDS_IO_TOPC);
	
	// to ble
	SIL_UART_DTC_TOBLE_MainLoop2();
	// at commands
	SIL_ATCMDS_MainLoop2(ATCMDS_IO_TOBLE);
	
	// buzzer
	SIL_APP_BUZZER_MainLoop2();
	
	// flash data
	SIL_FLASH_DATA_MainLoop2();
	
	// RTC
	SIL_APP_RTC_MainLoop2();
	
	// touch
	SIL_APP_TOUCH_MainLoop2();
	
	// usj app
	SIL_APP_USJ_MainLoop2();
	
	
	
	return err;

}

// <-- for ..\..\src\hal_entry.c








