#include "sil_globals.h"
#include "..\timer_reset\sil_dtc_reset.h"
#include "..\protocol_atcmds\sil_atcmds.h"
#include "..\uart_dtc\sil_uart_dtc_topc.h"
#include "..\uart_dtc\sil_uart_dtc_toble.h"
#include "..\app\sil_app_ultra_slow_jogging.h"
#include "..\app\sil_app_touch.h"
#include "..\flash\sil_flash_data.h"
#include "..\app\sil_app_rtc.h"
#include "..\app\sil_app_eep.h"
#include "..\app\sil_app_buzzer.h"
#include "..\app\sil_app_ticks.h"
#include "..\app\sil_app_glove_ml.h" // [Sean] Glove ML App
#include "..\app\sil_app_ds.h"       // [Sean] Direct Sensor HID Control App
#include "..\usb_pcdc\sil_usb_pcdc.h"

//* Global mapping for Glove ML: Logic UART Pos X -> Raw Pin Index Y */
const uint8_t g_sil_glove_chn_map[6] = {0, 1, 2, 3, 4, 5};


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

	if (gsil_globals_current_app == SIL_APP_USJ_E || gsil_globals_current_app == SIL_APP_JRC_E) {
		SIL_APP_USJ_Exit();
	} else if (gsil_globals_current_app == SIL_APP_GLOVE_ML_E) {
		// Glove ML exit if any
	} else if (gsil_globals_current_app == SIL_APP_DS_E) {
		SIL_APP_DS_Exit();
	}

	return err;
}

void SIL_GLOBALS_Reboot() {
	SIL_APP_TOUCH_Exit();
	NVIC_SystemReset();
	while (1);
}

void SIL_GLOBALS_SwitchApp(sil_app_type_e app) {
	if (app >= SIL_APP_FINAL_E || app < SIL_APP_USJ_E) {
	    return;
	}
	gsil_globals_current_app = app;
	SIL_GLOBALS_Reboot();
}

// --> for ..\..\src\hal_entry.c
fsp_err_t SIL_GLOBALS_Enter1(void) {
	fsp_err_t err = FSP_ERR_UNSUPPORTED;
	char buf[64];
	

	SIL_DTC_RESET_Enter1();

	// [Sean] Why: gsil_globals_current_app is in .noinit. Check range to avoid zombie state at first boot.
	if (gsil_globals_current_app >= SIL_APP_FINAL_E || gsil_globals_current_app < SIL_APP_USJ_E) {
	    gsil_globals_current_app = SIL_APP_USJ_E;
	}

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
	
	snprintf(
			buf,
			64,
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
	
//	gsil_globals_current_app = SIL_APP_DS_E;

	// [Sean] App Selection
	if (gsil_globals_current_app == SIL_APP_USJ_E || gsil_globals_current_app == SIL_APP_JRC_E) {
		SIL_APP_USJ_Enter1();
	} else if (gsil_globals_current_app == SIL_APP_GLOVE_ML_E) {
		SIL_APP_GLOVE_ML_Enter1();
	} else if (gsil_globals_current_app == SIL_APP_DS_E) {
		SIL_APP_DS_Enter1();
	}

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
	
	// usb pcdc open
	SIL_USB_PCDC_Open();

	
	// rtc
	SIL_APP_RTC_Enter2();
	
	// banner to PC
	SIL_UART_DTC_TOPC_WriteToTxBuffer((uint8_t *)"SIL_GLOBALS_Enter2\r\n", (uint16_t) strlen("SIL_GLOBALS_Enter2\r\n"));

	// touch
	SIL_APP_TOUCH_Enter2();

	// [Sean] App Selection
	if (gsil_globals_current_app == SIL_APP_USJ_E || gsil_globals_current_app == SIL_APP_JRC_E) {
		SIL_APP_USJ_Enter2();
	} else if (gsil_globals_current_app == SIL_APP_GLOVE_ML_E) {
		SIL_APP_GLOVE_ML_Enter2();
	} else if (gsil_globals_current_app == SIL_APP_DS_E) {
		SIL_APP_DS_Enter2();
	}

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

	// [Sean] App Selection
	if (gsil_globals_current_app == SIL_APP_USJ_E || gsil_globals_current_app == SIL_APP_JRC_E) {
		SIL_APP_USJ_MainLoop1();
	} else if (gsil_globals_current_app == SIL_APP_GLOVE_ML_E) {
		SIL_APP_GLOVE_ML_MainLoop1();
	} else if (gsil_globals_current_app == SIL_APP_DS_E) {
		SIL_APP_DS_MainLoop1();
	}

		
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
	
	// usb pcdc event poll
	SIL_USB_PCDC_EventPoll();

	
	// [Sean] App Selection
	if (gsil_globals_current_app == SIL_APP_USJ_E || gsil_globals_current_app == SIL_APP_JRC_E) {
		SIL_APP_USJ_MainLoop2();
	} else if (gsil_globals_current_app == SIL_APP_GLOVE_ML_E) {
		SIL_APP_GLOVE_ML_MainLoop2();
	} else if (gsil_globals_current_app == SIL_APP_DS_E) {
		SIL_APP_DS_MainLoop2();
	}
	
	
	
	return err;

}

// <-- for ..\..\src\hal_entry.c








