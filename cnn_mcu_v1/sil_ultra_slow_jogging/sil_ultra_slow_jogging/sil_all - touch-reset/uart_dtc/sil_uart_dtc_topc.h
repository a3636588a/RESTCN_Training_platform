#ifndef SIL_UART_DTC_TOPC_H
#define SIL_UART_DTC_TOPC_H

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

extern sil_uart_dtc_s gsil_uart_topc;

fsp_err_t SIL_UART_DTC_TOPC_ReadRestart();
bool SIL_UART_DTC_TOPC_DoesRcvdIdle();

void SIL_UART_DTC_TOPC_DtcToRxBuffer();

void SIL_UART_DTC_TOPC_WriteToRxBuffer(uint8_t *buf, uint16_t len);
void SIL_UART_DTC_TOPC_WriteToTxBuffer(uint8_t *buf, uint16_t len);

sil_uart_dtc_sts_tx_e SIL_UART_DTC_TOPC_GetTxEvent();
void SIL_UART_DTC_TOPC_SetTxEvent(sil_uart_dtc_sts_tx_e event);
sil_uart_dtc_sts_rx_e SIL_UART_DTC_TOPC_GetRxEvent();
void SIL_UART_DTC_TOPC_SetRxEvent(sil_uart_dtc_sts_rx_e event);

void SIL_UART_DTC_TOPC_MoveDtcRxDataToLocal();
uint16_t SIL_UART_DTC_TOPC_Rcvd_Dequeue(
							uint8_t *buf,
							uint16_t *len
							);

uint8_t *SIL_UART_DTC_TOPC_GetTmpBuf(uint16_t *buf_len, uint8_t do_zero);
uint8_t *SIL_UART_DTC_TOPC_GetTmpMainLoopBuf(uint16_t *buf_len);



fsp_err_t SIL_UART_DTC_TOPC_Enter1(void);
fsp_err_t SIL_UART_DTC_TOPC_Enter2(void);
fsp_err_t SIL_UART_DTC_TOPC_MainLoop1(void);
fsp_err_t SIL_UART_DTC_TOPC_MainLoop2(void);
fsp_err_t SIL_UART_DTC_TOPC_Exit(void);
fsp_err_t SIL_UART_DTC_TOPC_Restart(void);


















#endif //#ifndef SIL_UART_DTC_TOPC_H
