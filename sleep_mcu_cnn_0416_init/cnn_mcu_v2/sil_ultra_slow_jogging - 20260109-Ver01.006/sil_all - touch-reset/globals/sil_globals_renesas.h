/*
 * sil_globals_renesas.h
 *
 *  Created on: 2025年10月3日
 *      Author: Sheng
 */

#ifndef SIL_GLOBALS_RENESAS_H
#define SIL_GLOBALS_RENESAS_H

#include "hal_data.h"
#include "qe_touch_config.h"


// --> UART
// to pc uart
#define SILVAR_UART_TOPC g_uart9
#define SILVAR_UART_DTC_TX_TOPC g_transfer9_tx
#define SILVAR_UART_DTC_RX_TOPC g_transfer9_rx

// bo ble uart
//#define SILVAR_UART_TOBLE g_uart0
//#define SILVAR_UART_DTC_TX_TOBLE g_transfer0_tx
//#define SILVAR_UART_DTC_RX_TOBLE g_transfer0_rx

#define SILVAR_UART_TOBLE g_uart6
#define SILVAR_UART_DTC_TX_TOBLE g_transfer6_tx
#define SILVAR_UART_DTC_RX_TOBLE g_transfer6_rx


// reset uart dtc rx dtc setting, timer1
#define SILVAR_TMR_DTC_RX_RESET g_timer1




// <-- UART


// --> Touch
// ELC: touch call back link
#define SILVAR_ELC_TOUCH g_elc

// timer0 touch period scan
#define SILVAR_TMR_TOUCH_PERIOD_SCAN g_timer0

// cap touch
#define SILVAR_TOUCH_CNFG01 g_qe_touch_instance_config01

// touch pressed flag
#define SILVAR_TOUCH_FLAG g_qe_touch_flag
#define SILVAR_TOUCH_CTSU_EVENT g_qe_ctsu_event

// <-- Touch


// --> data/code flash

#define SILVAR_FLASH_HANDLER g_flash0

// <-- data/code flash


// --> RTC
#define SILVAR_TMR_RTC g_rtc0


// <-- RTC

// --> system core clock
#define SILVAR_CLK_SYS_CORE SystemCoreClock


// <-- system core clock



// --> PWM
#define SILVAR_TMR_BUZZER g_timer3
// <-- PWM


// --> Ultra Slow Jogging
#define SILVAR_TMR_STEPS_OUTPUT g_timer2


// <-- Ultra Slow Jogging





#endif /* SIL_GLOBALS_RENESAS_H */
