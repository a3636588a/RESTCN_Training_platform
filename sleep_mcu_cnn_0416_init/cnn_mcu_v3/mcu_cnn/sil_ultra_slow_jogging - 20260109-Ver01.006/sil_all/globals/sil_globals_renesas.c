/*
 * sil_globals_renesas.c
 *
 *  Created on: 2025年10月3日
 *      Author: Sheng
 */

#include "stdio.h"
#include "sil_globals.h"
#include "sil_globals_renesas.h"
#include "../uart_dtc/sil_uart_dtc_topc.h"
#include "../uart_dtc/sil_uart_dtc_toble.h"
#include "../protocol_atcmds/sil_atcmds.h"
#include "../app/sil_app_ultra_slow_jogging.h"
#include "../app/sil_app_tinyol.h"
#include "../timer_reset/sil_dtc_reset.h"
#include "../flash/sil_flash_data.h"
#include "../app/sil_app_rtc.h"
#include "../app/sil_app_buzzer.h"
#include "../app/sil_app_ticks.h"


// CapTouch using this timer callback when start scan. 
// It has nothing to do with the number of seconds set to generate interrupts
// issue period interrupt in 10 ms.
void g_timer0_cb(timer_callback_args_t *p_args) {

    (void) p_args;

	SIL_APP_TOUCH_GetChannelsDataPeriod();
	
	// FSP's CTSU Scan Start Trigger use software.
	// the below move to sil_touch.c: SIL_TOUCH_GetChannelsData(sil_touch_s *obj)
	//SIL_APP_TOUCH_StartScan();
	
	SIL_APP_USJ_GetChannelsDataPeriod();

}

// period issue in 5 ms. reset dtc setting when uart receiving idle
static uint8_t gsil_globals_renesas_rtc_fire = 0;
void g_timer1_cb(timer_callback_args_t *p_args) {

    (void) p_args;
	static int32_t cnt = 0;

	SIL_UART_DTC_TOPC_MoveDtcRxDataToLocal();
	SIL_UART_DTC_TOBLE_MoveDtcRxDataToLocal();
	SIL_DTC_RESET_CountIncreasing();

	cnt ++;


	//if ((cnt % 200) == 0) { // 1 s
	if (gsil_globals_renesas_rtc_fire) {
		gsil_globals_renesas_rtc_fire = 0;
		SIL_APP_RTC_GetTime((rtc_time_t *) 0);
	}
	if ((cnt % 12) == 0) { // 62.5 ms. ~ 60.0 ms.
	    if (gsil_globals_current_app == SIL_APP_USJ_E || gsil_globals_current_app == SIL_APP_JRC_E) {
	        SIL_APP_USJ_OutputSteps();
	    }
	}
    if ((cnt % 2) == 0) {	// 10 ms
	    if (gsil_globals_current_app != SIL_APP_TINYOL_E ||
            SIL_APP_TINYOL_IsCalibrationActive() ||
            SIL_APP_TINYOL_IsRecordingActive()) {
	        SIL_APP_TOUCH_RawDataToOutside();
	    }
	    if (gsil_globals_current_app == SIL_APP_USJ_E || gsil_globals_current_app == SIL_APP_JRC_E) {
	        SIL_APP_USJ_CountSteps();
	    }
	}

}

// period issue in 62500 us. 16Hz
void g_timer2_cb(timer_callback_args_t *p_args) {
    (void) p_args;

	SIL_APP_BUZZER_TimerLoop();
	//SIL_APP_USJ_OutputSteps();
}

// uart to PC callback function when interrupt
void g_uart9_cb(uart_callback_args_t *p_args) {

    sil_uart_dtc_sts_tx_e event_tx = UART_DTC_STS_TX_UNKNOWN_E;
    sil_uart_dtc_sts_rx_e event_rx = UART_DTC_STS_RX_UNKNOWN_E;

    if (p_args == NULL) return;

    switch(p_args->event) {
        case UART_EVENT_RX_CHAR:        // when DTC disabled, uart can issue this event
            event_rx = UART_DTC_STS_RX_CHAR;
            break;
        case UART_EVENT_RX_COMPLETE:
            event_rx = UART_DTC_STS_RX_COMPLETE;
            break;
        case UART_EVENT_TX_COMPLETE:
            event_tx = UART_DTC_STS_TX_COMPLETE;
            break;
        case UART_EVENT_TX_DATA_EMPTY:
            event_tx = UART_DTC_STS_TX_DATA_EMPTY;
            break;
        default:
            break;

    }

    if (event_tx != UART_DTC_STS_TX_UNKNOWN_E) SIL_UART_DTC_TOPC_SetTxEvent(event_tx);
    if (event_rx != UART_DTC_STS_RX_UNKNOWN_E) SIL_UART_DTC_TOPC_SetRxEvent(event_rx);



}

// uart to BLE callback function when interrupt
void g_uart6_cb(uart_callback_args_t *p_args) {

    sil_uart_dtc_sts_tx_e event_tx = UART_DTC_STS_TX_UNKNOWN_E;
    sil_uart_dtc_sts_rx_e event_rx = UART_DTC_STS_RX_UNKNOWN_E;

    if (p_args == NULL) return;

    switch(p_args->event) {
        case UART_EVENT_RX_CHAR:        // when DTC disabled, uart can issue this event
            event_rx = UART_DTC_STS_RX_CHAR;
            break;
        case UART_EVENT_RX_COMPLETE:
            event_rx = UART_DTC_STS_RX_COMPLETE;
            break;
        case UART_EVENT_TX_COMPLETE:
            event_tx = UART_DTC_STS_TX_COMPLETE;
            break;
        case UART_EVENT_TX_DATA_EMPTY:
            event_tx = UART_DTC_STS_TX_DATA_EMPTY;
            break;
        default:
            break;

    }

    if (event_tx != UART_DTC_STS_TX_UNKNOWN_E) SIL_UART_DTC_TOBLE_SetTxEvent(event_tx);
    if (event_rx != UART_DTC_STS_RX_UNKNOWN_E) SIL_UART_DTC_TOBLE_SetRxEvent(event_rx);



}

void g_flash0_cb(flash_callback_args_t *p_args) {
	
	SIL_FLASH_DATA_Callback(p_args);
	SIL_APP_TINYOL_FlashCallback(p_args);
	
}

void g_rtc0_cb(rtc_callback_args_t *p_args) {

    switch (p_args->event) {

	case RTC_EVENT_PERIODIC_IRQ:	// 1 second.
        //SIL_APP_RTC_GetTime((rtc_time_t *) 0);
		gsil_globals_renesas_rtc_fire = 1;
		break;
	default:
		break;
	}
}

extern void SysTick_Handler(void);
void SysTick_Handler(void) {

	SIL_APP_TICKS_Decrease();
}







