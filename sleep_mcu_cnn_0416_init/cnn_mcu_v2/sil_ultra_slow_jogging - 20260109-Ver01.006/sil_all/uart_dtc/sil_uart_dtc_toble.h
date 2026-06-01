#ifndef SIL_UART_DTC_TOBLE_H
#define SIL_UART_DTC_TOBLE_H

#include "sil_uart_dtc.h"
#include <stdbool.h>


/*
#if defined(__ICCARM__)

void R_BSP_WarmStart(bsp_warm_start_event_t event);

 #pragma weak R_BSP_WarmStart

#elif defined(__GNUC__) || defined(__ARMCC_VERSION)

void R_BSP_WarmStart(bsp_warm_start_event_t event) __attribute__((weak));

#endif
// */

extern sil_uart_dtc_s gsil_uart_toble;

fsp_err_t SIL_UART_DTC_TOBLE_ReadRestart();
bool SIL_UART_DTC_TOBLE_DoesRcvdIdle();

void SIL_UART_DTC_TOBLE_DtcToRxBuffer();

void SIL_UART_DTC_TOBLE_WriteToRxBuffer(uint8_t *buf, uint16_t len);
void SIL_UART_DTC_TOBLE_WriteToTxBuffer(uint8_t *buf, uint16_t len);

sil_uart_dtc_sts_tx_e SIL_UART_DTC_TOBLE_GetTxEvent();
void SIL_UART_DTC_TOBLE_SetTxEvent(sil_uart_dtc_sts_tx_e event);
sil_uart_dtc_sts_rx_e SIL_UART_DTC_TOBLE_GetRxEvent();
void SIL_UART_DTC_TOBLE_SetRxEvent(sil_uart_dtc_sts_rx_e event);

void SIL_UART_DTC_TOBLE_MoveDtcRxDataToLocal();
uint16_t SIL_UART_DTC_TOBLE_Rcvd_Dequeue(
							uint8_t *buf,
							uint16_t *len
							);

uint8_t *SIL_UART_DTC_TOBLE_GetTmpBuf(uint16_t *buf_len, uint8_t do_zero);
uint8_t *SIL_UART_DTC_TOBLE_GetTmpMainLoopBuf(uint16_t *buf_len);



fsp_err_t SIL_UART_DTC_TOBLE_Enter1(void);
fsp_err_t SIL_UART_DTC_TOBLE_Enter2(void);
fsp_err_t SIL_UART_DTC_TOBLE_MainLoop1(void);
fsp_err_t SIL_UART_DTC_TOBLE_MainLoop2(void);
fsp_err_t SIL_UART_DTC_TOBLE_Exit(void);
fsp_err_t SIL_UART_DTC_TOBLE_Exit(void);
fsp_err_t SIL_UART_DTC_TOBLE_Restart(void);


















#endif //#ifndef SIL_UART_DTC_TOBLE_H
