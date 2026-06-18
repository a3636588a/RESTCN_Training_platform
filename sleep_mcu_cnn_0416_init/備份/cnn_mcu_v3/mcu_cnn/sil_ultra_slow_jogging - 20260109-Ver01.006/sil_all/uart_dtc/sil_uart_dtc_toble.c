#include "sil_uart_dtc_toble.h"
#include <stdlib.h>
#include "..\globals\sil_globals_renesas.h"

sil_uart_dtc_s gsil_uart_toble;


bool SIL_UART_DTC_TOBLE_DoesRcvdIdle(void) {
	
	return SIL_UART_DTC_DoesRcvdIdle(&gsil_uart_toble);
	
}

fsp_err_t SIL_UART_DTC_TOBLE_ReadRestart(void) {
	
	return SIL_UART_DTC_ReadRestart(&gsil_uart_toble);

}

void SIL_UART_DTC_TOBLE_MoveDtcRxDataToLocal(void) {
	SIL_UART_DTC_MoveDtcRxDataToLocal(&gsil_uart_toble);
}

void SIL_UART_DTC_TOBLE_WriteToRxBuffer(uint8_t *buf, uint16_t len) {
	SIL_UART_DTC_WriteToRxBuffer(&gsil_uart_toble, buf, len);
}

void SIL_UART_DTC_TOBLE_WriteToTxBuffer(uint8_t *buf, uint16_t len) {
	SIL_UART_DTC_WriteToTxBuffer(&gsil_uart_toble, buf, len);
}

sil_uart_dtc_sts_tx_e SIL_UART_DTC_TOBLE_GetTxEvent(void) {
	return SIL_UART_DTC_GetTxEvent(&gsil_uart_toble);
}

void SIL_UART_DTC_TOBLE_SetTxEvent(sil_uart_dtc_sts_tx_e event) {
	SIL_UART_DTC_SetTxEvent(&gsil_uart_toble, event);
}

sil_uart_dtc_sts_rx_e SIL_UART_DTC_TOBLE_GetRxEvent(void) {
	return SIL_UART_DTC_GetRxEvent(&gsil_uart_toble);
}

void SIL_UART_DTC_TOBLE_SetRxEvent(sil_uart_dtc_sts_rx_e event) {
	SIL_UART_DTC_SetRxEvent(&gsil_uart_toble, event);
}

uint16_t SIL_UART_DTC_TOBLE_Rcvd_Dequeue(
							uint8_t *buf,
							uint16_t *len
							) {
								
	return SIL_UART_DTC_Rcvd_Dequeue(
							&gsil_uart_toble,
							buf,
							len
							);
}

uint8_t *SIL_UART_DTC_TOBLE_GetTmpBuf(uint16_t *buf_len, uint8_t do_zero) {
	return SIL_UART_DTC_GetTmpBuf(&gsil_uart_toble, buf_len, do_zero);
}
uint8_t *SIL_UART_DTC_TOBLE_GetTmpMainLoopBuf(uint16_t *buf_len) {
	return SIL_UART_DTC_GetTmpMainLoopBuf(&gsil_uart_toble, buf_len);
}

fsp_err_t SIL_UART_DTC_TOBLE_Enter1(void) {

    fsp_err_t err = FSP_ERR_UNSUPPORTED;

/*
#define SILVAR_UART_TOBLE g_uart9
#define SILVAR_UART_DTC_TX_TOBLE g_transfer9_tx
#define SILVAR_UART_DTC_RX_TOBLE g_transfer9_rx
// */
	err = SIL_UART_DTC_Enter1(
							&gsil_uart_toble, 
							(uart_instance_t *)&SILVAR_UART_TOBLE, 
							(transfer_instance_t *)&SILVAR_UART_DTC_TX_TOBLE, 
							(transfer_instance_t *)&SILVAR_UART_DTC_RX_TOBLE
							);

	return err;
}

fsp_err_t SIL_UART_DTC_TOBLE_Enter2(void) {
	fsp_err_t err = FSP_ERR_UNSUPPORTED;

	err = SIL_UART_DTC_Enter2(&gsil_uart_toble);
	
	return err;
}

fsp_err_t SIL_UART_DTC_TOBLE_MainLoop1(void) {
    return SIL_UART_DTC_MainLoop1(&gsil_uart_toble);
}

fsp_err_t SIL_UART_DTC_TOBLE_MainLoop2(void) {
    return SIL_UART_DTC_MainLoop2(&gsil_uart_toble);
}

fsp_err_t SIL_UART_DTC_TOBLE_Exit(void) {
    return SIL_UART_DTC_Exit(&gsil_uart_toble);
}

fsp_err_t SIL_UART_DTC_TOBLE_Restart() {
    return SIL_UART_DTC_Restart(&gsil_uart_toble);
}


