#ifndef SIL_UART_DTC_H
#define SIL_UART_DTC_H

#include "..\buffer_ring_buf\sil_ringbuf.h"
#include <stdbool.h>


/*
#if defined(__ICCARM__)

void R_BSP_WarmStart(bsp_warm_start_event_t event);

 #pragma weak R_BSP_WarmStart

#elif defined(__GNUC__) || defined(__ARMCC_VERSION)

void R_BSP_WarmStart(bsp_warm_start_event_t event) __attribute__((weak));

#endif
// */

typedef enum SIL_UART_DTC_STS_TX_E {
	UART_DTC_STS_TX_UNKNOWN_E = -1,
	UART_DTC_STS_TX_DATA_EMPTY = 0,
	UART_DTC_STS_TX_COMPLETE,

	UART_DTC_STS_TX_FINAL_E,
	UART_DTC_STS_TX_MAXS_E = (UART_DTC_STS_TX_FINAL_E + 2)

} sil_uart_dtc_sts_tx_e;

typedef enum SIL_UART_DTC_STS_RX_E {
	UART_DTC_STS_RX_UNKNOWN_E = -1,
	UART_DTC_STS_RX_COMPLETE,
	UART_DTC_STS_RX_CHAR,

	UART_DTC_STS_RX_FINAL_E,
	UART_DTC_STS_RX_MAXS_E = (UART_DTC_STS_RX_FINAL_E + 2)

} sil_uart_dtc_sts_rx_e;


#ifndef SILCNTS_RINGBUF_SIZE_DEFAULT
#   define SILCNTS_UART_DTC_BUF_LEN_DEFAULT 256
#else
#   define SILCNTS_UART_DTC_BUF_LEN_DEFAULT SILCNTS_RINGBUF_SIZE_DEFAULT
#endif

typedef struct SIL_UART_DTC_S {
    uint8_t initialized;
	uint32_t count_reset;
//const uart_instance_t g_uart9 =
//	{ .p_ctrl = &g_uart9_ctrl, .p_cfg = &g_uart9_cfg, .p_api = &g_uart_on_sci };
	uart_instance_t *p_uart;

//const transfer_instance_t g_transfer9_tx =
//	{ .p_ctrl = &g_transfer9_tx_ctrl, .p_cfg = &g_transfer9_tx_cfg, .p_api = &g_transfer_on_dtc };
	transfer_instance_t *p_transfer_tx;
	
//const transfer_instance_t g_transfer9_rx =
//	{ .p_ctrl = &g_transfer9_rx_ctrl, .p_cfg = &g_transfer9_rx_cfg, .p_api = &g_transfer_on_dtc };
	transfer_instance_t *p_transfer_rx;

	R_SCI0_Type *p_regs;		// R_SCI9->RDR, 
	uint8_t a_buf_rx[SILCNTS_UART_DTC_BUF_LEN_DEFAULT];
	uint16_t buf_rx_len;
	uint16_t dtc_rcvd_last_len;
	
	uint8_t a_buf_tx[SILCNTS_UART_DTC_BUF_LEN_DEFAULT];
	uint16_t buf_tx_len;
	sil_ringbuf_s ringbuf_tx;
	sil_ringbuf_s ringbuf_rx;
	
	sil_uart_dtc_sts_tx_e event_tx;
	int16_t event_tx_delay;
	sil_uart_dtc_sts_rx_e event_rx;
	
	uint8_t a_buf_tmp[SILCNTS_UART_DTC_BUF_LEN_DEFAULT];
	uint16_t a_buf_tmp_len;
	uint8_t a_buf_mainloop[SILCNTS_UART_DTC_BUF_LEN_DEFAULT];
	uint16_t a_buf_mainloop_len;

} sil_uart_dtc_s;




uint16_t SIL_UART_DTC_GetDtcRcvdDataLen(sil_uart_dtc_s *obj);
fsp_err_t SIL_UART_DTC_ReadRestart(sil_uart_dtc_s *obj);
fsp_err_t SIL_UART_DTC_Write(sil_uart_dtc_s *obj, uint8_t *buf, uint16_t len);
fsp_err_t SIL_UART_DTC_Rcv_Reset(sil_uart_dtc_s *obj);
bool SIL_UART_DTC_DoesRcvdIdle(sil_uart_dtc_s *obj);
void SIL_UART_DTC_Rcvd_Enqeue(
							sil_uart_dtc_s *obj,
							uint8_t *buf,
							uint16_t len
							);
uint16_t SIL_UART_DTC_Rcvd_Dequeue(
							sil_uart_dtc_s *obj,
							uint8_t *buf,
							uint16_t *len
							);
void SIL_UART_DTC_Txd_Enqeue(
							sil_uart_dtc_s *obj,
							uint8_t *buf,
							uint16_t len
							);
void SIL_UART_DTC_Txd_Dequeue(
							sil_uart_dtc_s *obj,
							uint8_t *buf,
							uint16_t *len
							);

void SIL_UART_DTC_WriteToRxBuffer(sil_uart_dtc_s *obj, uint8_t *buf, uint16_t len);


void SIL_UART_DTC_WriteToTxBuffer(sil_uart_dtc_s *obj, uint8_t *buf, uint16_t len);
void SIL_UART_DTC_FlushWriteBuffer(sil_uart_dtc_s *obj);


sil_uart_dtc_sts_tx_e SIL_UART_DTC_GetTxEvent(sil_uart_dtc_s *obj);
void SIL_UART_DTC_SetTxEvent(sil_uart_dtc_s *obj, sil_uart_dtc_sts_tx_e event);

sil_uart_dtc_sts_rx_e SIL_UART_DTC_GetRxEvent(sil_uart_dtc_s *obj);
void SIL_UART_DTC_SetRxEvent(sil_uart_dtc_s *obj, sil_uart_dtc_sts_rx_e event);

void SIL_UART_DTC_MoveDtcRxDataToLocal(sil_uart_dtc_s *obj);
uint8_t *SIL_UART_DTC_GetTmpBuf(sil_uart_dtc_s *obj, uint16_t *buf_len, uint8_t do_zero);
uint8_t *SIL_UART_DTC_GetTmpMainLoopBuf(sil_uart_dtc_s *obj, uint16_t *buf_len);





fsp_err_t SIL_UART_DTC_Enter1(
								sil_uart_dtc_s *obj, 
								uart_instance_t *uart, 
								transfer_instance_t *tx, 
								transfer_instance_t *rx
								);

fsp_err_t SIL_UART_DTC_Enter2(sil_uart_dtc_s *obj);
fsp_err_t SIL_UART_DTC_MainLoop1(sil_uart_dtc_s *obj);
fsp_err_t SIL_UART_DTC_MainLoop2(sil_uart_dtc_s *obj);
fsp_err_t SIL_UART_DTC_Exit(sil_uart_dtc_s *obj);
fsp_err_t SIL_UART_DTC_Restart(sil_uart_dtc_s *obj);























#endif //#ifndef SIL_UART_DTC_H
