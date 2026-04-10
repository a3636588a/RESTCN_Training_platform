#include "sil_uart_dtc.h"
#include <stdlib.h>
#include <stdio.h>
#include "..\app\sil_app_ticks.h"

static void SIL_UART_DTC_Regs_Mapping(
							sil_uart_dtc_s *obj
							) {

	sil_uart_dtc_s *p_obj = obj;
	
	if (p_obj && p_obj->p_uart && p_obj->p_uart->p_cfg) {
		switch (p_obj->p_uart->p_cfg->channel) {
		case 0:
			p_obj->p_regs = R_SCI0;
			break;
		case 1:
			p_obj->p_regs = R_SCI1;
			break;
		case 2:
			p_obj->p_regs = R_SCI2;
			break;
		case 3:
			p_obj->p_regs = R_SCI3;
			break;
		case 4:
			p_obj->p_regs = R_SCI4;
			break;
		case 5:
			p_obj->p_regs = R_SCI5;
			break;
		case 6:
			p_obj->p_regs = R_SCI6;
			break;
		case 7:
			p_obj->p_regs = R_SCI7;
			break;
		case 8:
			p_obj->p_regs = R_SCI8;
			break;
		case 9:
			p_obj->p_regs = R_SCI9;
			break;
		default:
			p_obj->p_regs = (R_SCI0_Type *) 0;
			break;
		}
	}
	
}

/*
static void SIL_UART_DTC_NNop(int16_t n) {

	while (n -- > 0) {
		__asm volatile (
			"nop \n"
		);	
	};
}
// */

/*
static fsp_err_t SIL_UART_DTC_Tx_Reset(
                            sil_uart_dtc_s *obj,
                            uint8_t *buf,
                            uint16_t len
                            ) {
    fsp_err_t err = -1;
    sil_uart_dtc_s *p_obj = obj;
    uart_instance_t *uart = (uart_instance_t *) 0;
    transfer_instance_t *tx = (transfer_instance_t *) 0;

    (void) uart;

    if (p_obj) {
        uart = (p_obj->p_uart) ? p_obj->p_uart : (uart_instance_t *) 0;
        tx = (p_obj->p_transfer_tx) ? (transfer_instance_t *)p_obj->p_transfer_tx : (transfer_instance_t *) 0;

        //R_DTC_Disable(tx->p_ctrl);
        tx->p_cfg->p_info->p_src = buf;
        tx->p_cfg->p_info->p_dest = (void *)&p_obj->p_regs->TDR;
        tx->p_cfg->p_info->length = len;

        err = R_DTC_Reconfigure(tx->p_ctrl, tx->p_cfg->p_info);

        //R_DTC_Enable(tx->p_ctrl);
    }

    return err;
}
// */

fsp_err_t SIL_UART_DTC_Rcv_Reset(
							sil_uart_dtc_s *obj
							) {
	fsp_err_t err = -1;
    sil_uart_dtc_s *p_obj = obj;
    uart_instance_t *uart = (uart_instance_t *) 0;
    transfer_instance_t *rx = (transfer_instance_t *) 0;
	
    (void) uart;

    if (p_obj && p_obj->initialized) {
		uart = (p_obj->p_uart) ? p_obj->p_uart : (uart_instance_t *) 0;
		rx = (p_obj->p_transfer_rx) ? (transfer_instance_t *)p_obj->p_transfer_rx : (transfer_instance_t *) 0;

		p_obj->dtc_rcvd_last_len = 0;

		err = R_DTC_Reset(
						rx->p_ctrl,
						(void const * volatile) &p_obj->p_regs->RDR,	// UART RX source
						(void * volatile) p_obj->a_buf_rx,          	// destination
						p_obj->buf_rx_len
						);
	}

	return err;
}

uint16_t SIL_UART_DTC_GetDtcRcvdDataLen(sil_uart_dtc_s *obj) {
	
    uint16_t len = 0;
	sil_uart_dtc_s *p_obj = obj;
	transfer_instance_t *rx = (p_obj->p_transfer_rx) ? (transfer_instance_t *)p_obj->p_transfer_rx : (transfer_instance_t *) 0;
	transfer_cfg_t *p_rx_cfg = (rx->p_cfg) ? (transfer_cfg_t *) rx->p_cfg : (transfer_cfg_t *) 0;
    uint16_t remaining = 0;

    if (p_obj && p_obj->initialized && rx && p_rx_cfg) {
        remaining = (uint32_t) p_rx_cfg->p_info->length;

        if (remaining > p_obj->buf_rx_len) remaining = 0;

        len = (uint16_t)((p_obj->buf_rx_len - remaining) % p_obj->buf_rx_len);
    }
    return len;
}

bool SIL_UART_DTC_DoesRcvdIdle(sil_uart_dtc_s *obj) {

	sil_uart_dtc_s *p_obj = obj;	
	bool ret = false;
    uint16_t rcved_len = 0;

    if (p_obj && p_obj->initialized) {
		rcved_len = SIL_UART_DTC_GetDtcRcvdDataLen(p_obj);
		
		if (p_obj->dtc_rcvd_last_len == rcved_len) ret = true;
		else {
			
		}
		p_obj->dtc_rcvd_last_len = rcved_len;
	}
	
	return ret;
}

fsp_err_t SIL_UART_DTC_ReadRestart(sil_uart_dtc_s *obj) {
	
	fsp_err_t err = -1;
    sil_uart_dtc_s *p_obj = obj;
    uart_instance_t *uart = (uart_instance_t *) 0;
    //transfer_instance_t *rx = (transfer_instance_t *) 0;
	
    if (p_obj && p_obj->initialized) {
		uart = (p_obj->p_uart) ? p_obj->p_uart : (uart_instance_t *) 0;
		//rx = (p_obj->p_transfer_rx) ? (transfer_instance_t *)p_obj->p_transfer_rx : (transfer_instance_t *) 0;
		
		
		memset(p_obj->a_buf_rx, 0x00, sizeof(uint8_t) * p_obj->buf_rx_len);
		if (uart && uart->p_ctrl) err = R_SCI_UART_Read(uart->p_ctrl, p_obj->a_buf_rx, p_obj->buf_rx_len);
		if (FSP_SUCCESS == err) err = SIL_UART_DTC_Rcv_Reset(p_obj);
	}
	
	return err;
}

void SIL_UART_DTC_Rcvd_Enqeue(
							sil_uart_dtc_s *obj,
							uint8_t *buf,
							uint16_t len
							) {
	sil_uart_dtc_s *p_obj = obj;
	uint16_t i;
	
	if (p_obj && p_obj->initialized) for (i = 0; i < len; i ++) SIL_RINGBUF_Enqueue(&p_obj->ringbuf_rx, buf[i]);

}

uint16_t SIL_UART_DTC_Rcvd_Dequeue(
							sil_uart_dtc_s *obj,
							uint8_t *buf,
							uint16_t *len
							) {
	sil_uart_dtc_s *p_obj = obj;
	uint16_t i, rcvd_len = 0;
	uint8_t d;
	
	if (p_obj && p_obj->initialized && buf && len) {
		rcvd_len = SIL_RINGBUF_GetDataLength(&p_obj->ringbuf_rx);

		if (rcvd_len > 0) {
            if (rcvd_len >= *len) rcvd_len = *len;
            *len = rcvd_len;

            for (i = 0; i < rcvd_len; i ++) {
                SIL_RINGBUF_Dequeue(&p_obj->ringbuf_rx, &d);
                buf[i] = (uint8_t)(d & 0xff);
            }
		}
		else *len = 0;
	}

	return rcvd_len;
}

static void SIL_UART_DTC_DtcToRxBuffer(sil_uart_dtc_s *obj) {

    sil_uart_dtc_s *p_obj = obj;
	uint16_t rcvd_len = 0;

	if (p_obj && p_obj->initialized) {
		rcvd_len = SIL_UART_DTC_GetDtcRcvdDataLen(p_obj);

		if (rcvd_len > 0) {
		    if (rcvd_len > p_obj->buf_rx_len) rcvd_len = p_obj->buf_rx_len;

            SIL_UART_DTC_Rcvd_Enqeue(
                                    p_obj,
                                    p_obj->a_buf_rx,
                                    rcvd_len
                                    );
            SIL_UART_DTC_ReadRestart(p_obj);
		}
	}
}

void SIL_UART_DTC_WriteToRxBuffer(sil_uart_dtc_s *obj, uint8_t *buf, uint16_t len) {
	
    sil_uart_dtc_s *p_obj = obj;
    if (p_obj && p_obj->initialized) SIL_UART_DTC_Rcvd_Enqeue(
                                                            p_obj,
                                                            buf,
                                                            len
                                                            );
	
}

fsp_err_t SIL_UART_DTC_Write(sil_uart_dtc_s *obj, uint8_t *buf, uint16_t len) {
	
	fsp_err_t err = -1;
    sil_uart_dtc_s *p_obj = obj;
    uart_instance_t *uart = (uart_instance_t *) 0;
	
    if (p_obj && p_obj->initialized) {
		uart = (p_obj->p_uart) ? p_obj->p_uart : (uart_instance_t *) 0;
		if (uart && uart->p_ctrl && buf && (len > 0)) {
		    //err = SIL_UART_DTC_Tx_Reset(
		    //                            p_obj,
		    //                            buf,
		    //                            len
		    //                            );
		    //if (err == FSP_SUCCESS) err = R_SCI_UART_Write(uart->p_ctrl, buf, len);
			
			err = R_SCI_UART_Write(uart->p_ctrl, buf, len);
		}
	}
	
	return err;
}

void SIL_UART_DTC_Txd_Enqeue(
							sil_uart_dtc_s *obj,
							uint8_t *buf,
							uint16_t len
							) {
	sil_uart_dtc_s *p_obj = obj;
	uint16_t i;
	
	if (p_obj && p_obj->initialized) for (i = 0; i < len; i ++) SIL_RINGBUF_Enqueue(&p_obj->ringbuf_tx, buf[i]);

}

void SIL_UART_DTC_Txd_Dequeue(
							sil_uart_dtc_s *obj,
							uint8_t *buf,
							uint16_t *len
							) {
	sil_uart_dtc_s *p_obj = obj;
	uint16_t i, txd_len = 0;
	uint8_t d = 0;
	
	if (p_obj && p_obj->initialized && buf && len) {
		txd_len = SIL_RINGBUF_GetDataLength(&p_obj->ringbuf_tx);
		if (txd_len >= *len) txd_len = *len;
		*len = txd_len;
		
		for (i = 0; i < txd_len; i ++) {
			SIL_RINGBUF_Dequeue(&p_obj->ringbuf_tx, &d);
			buf[i] = (uint8_t)(d & 0xff);
		}
	}

}

void SIL_UART_DTC_WriteToTxBuffer(sil_uart_dtc_s *obj, uint8_t *buf, uint16_t len) {
	
    sil_uart_dtc_s *p_obj = obj;
	
    if (p_obj && p_obj->initialized) SIL_UART_DTC_Txd_Enqeue(
                                                            p_obj,
                                                            buf,
                                                            len
                                                            );

}

void SIL_UART_DTC_FlushWriteBuffer(sil_uart_dtc_s *obj) {

    sil_uart_dtc_s *p_obj = obj;
	volatile sil_uart_dtc_sts_tx_e event;
	uint16_t len;
	volatile uint16_t txd_len = 0;
	
	if (p_obj && p_obj->initialized) {
        txd_len = SIL_RINGBUF_GetDataLength(&p_obj->ringbuf_tx);
        if (txd_len) {
            event = SIL_UART_DTC_GetTxEvent(p_obj);

            len = (SILCNTS_UART_DTC_BUF_LEN_DEFAULT * 80) / 100;    // force send
            if (((UART_DTC_STS_TX_COMPLETE == event) || (txd_len >= len)) && (p_obj->event_tx_delay -- <= 0)) {

                SIL_UART_DTC_SetTxEvent(p_obj, UART_DTC_STS_TX_UNKNOWN_E);

                memset((void *)p_obj->a_buf_tx, 0x00, sizeof(uint8_t) * p_obj->buf_tx_len);

                SIL_UART_DTC_Txd_Dequeue(
                                        p_obj,
                                        p_obj->a_buf_tx,
                                        &len
                                        );

                SIL_UART_DTC_Write(p_obj, p_obj->a_buf_tx, len);
            }
			
			if ((p_obj->count_reset ++ % (uint32_t) 0x0003FFFF) == (uint32_t)(0x0003FFFF - 1)) {
				SIL_UART_DTC_Restart(p_obj);
			}
        }
	}
}


sil_uart_dtc_sts_tx_e SIL_UART_DTC_GetTxEvent(sil_uart_dtc_s *obj) {
	sil_uart_dtc_sts_tx_e last = UART_DTC_STS_TX_UNKNOWN_E;
    sil_uart_dtc_s *p_obj = obj;

    if (p_obj && p_obj->initialized) last = p_obj->event_tx;
	
	return last;
}

void SIL_UART_DTC_SetTxEvent(sil_uart_dtc_s *obj, sil_uart_dtc_sts_tx_e event) {
    sil_uart_dtc_s *p_obj = obj;
	
    if (p_obj && p_obj->initialized) {
        if ((event >= UART_DTC_STS_TX_UNKNOWN_E) && (event < UART_DTC_STS_TX_MAXS_E)) {

            if (UART_DTC_STS_TX_COMPLETE == event) p_obj->event_tx_delay = 16;
            p_obj->event_tx = event;
        }
    }
}

sil_uart_dtc_sts_rx_e SIL_UART_DTC_GetRxEvent(sil_uart_dtc_s *obj) {
	sil_uart_dtc_sts_rx_e last = UART_DTC_STS_RX_UNKNOWN_E;
    sil_uart_dtc_s *p_obj = obj;

    if (p_obj && p_obj->initialized) last = p_obj->event_rx;
	
	return last;
}

void SIL_UART_DTC_SetRxEvent(sil_uart_dtc_s *obj, sil_uart_dtc_sts_rx_e event) {
    sil_uart_dtc_s *p_obj = obj;
	
    if (p_obj && p_obj->initialized) {
        if ((event >= UART_DTC_STS_RX_UNKNOWN_E) && (event < UART_DTC_STS_RX_MAXS_E)) {
            p_obj->event_rx = event;
        }
    }
}

uint8_t *SIL_UART_DTC_GetTmpBuf(sil_uart_dtc_s *obj, uint16_t *buf_len, uint8_t do_zero) {

    sil_uart_dtc_s *p_obj = obj;
    uint8_t *p = (uint8_t *) 0;

    if (p_obj && p_obj->initialized) {
        if (do_zero) memset(p_obj->a_buf_tmp, 0x00, sizeof(uint8_t) * SILCNTS_UART_DTC_BUF_LEN_DEFAULT);
        *buf_len = p_obj->a_buf_tmp_len;

        p = p_obj->a_buf_tmp;
    }

    return p;

}

uint8_t *SIL_UART_DTC_GetTmpMainLoopBuf(sil_uart_dtc_s *obj, uint16_t *buf_len) {

    sil_uart_dtc_s *p_obj = obj;
    uint8_t *p = (uint8_t *) 0;

    if (p_obj && p_obj->initialized) {
        memset(p_obj->a_buf_mainloop, 0x00, sizeof(uint8_t) * SILCNTS_UART_DTC_BUF_LEN_DEFAULT);
        *buf_len = p_obj->a_buf_mainloop_len;

        p = p_obj->a_buf_mainloop;
    }

    return p;

}

void SIL_UART_DTC_MoveDtcRxDataToLocal(sil_uart_dtc_s *obj) {
	sil_uart_dtc_s *p_obj = obj;
	sil_uart_dtc_sts_rx_e event_rx = UART_DTC_STS_RX_UNKNOWN_E;
	bool ret = false;

	if (p_obj && p_obj->initialized) {
		ret = SIL_UART_DTC_DoesRcvdIdle(p_obj);
		event_rx = SIL_UART_DTC_GetRxEvent(p_obj);

		if ((ret) ||
			(UART_DTC_STS_RX_COMPLETE == event_rx)) {
			SIL_UART_DTC_DtcToRxBuffer(p_obj);
			
			if (UART_DTC_STS_RX_COMPLETE == event_rx) SIL_UART_DTC_SetRxEvent(p_obj, UART_DTC_STS_RX_UNKNOWN_E);
		}
	}
}

fsp_err_t SIL_UART_DTC_Enter1(
                                sil_uart_dtc_s *obj,
                                uart_instance_t *uart,
                                transfer_instance_t *tx,
                                transfer_instance_t *rx
                                ) {

	sil_uart_dtc_s *p_obj = obj;
    fsp_err_t err = -1;

	if (p_obj && tx && rx) {

	    p_obj->initialized = 0;
		p_obj->count_reset = 0;
		p_obj->p_uart = uart;
		p_obj->p_transfer_tx = (transfer_instance_t *)tx;
		p_obj->p_transfer_rx = (transfer_instance_t *)rx;

		if (tx->p_cfg && tx->p_cfg->p_info) SIL_RINGBUF_Init(
															&p_obj->ringbuf_tx
															);
															
		if (rx->p_cfg && rx->p_cfg->p_info) SIL_RINGBUF_Init(&p_obj->ringbuf_rx
															);

		if (rx->p_cfg->p_info->length) p_obj->buf_rx_len = rx->p_cfg->p_info->length;
		else p_obj->buf_rx_len = SILCNTS_UART_DTC_BUF_LEN_DEFAULT;
		memset(p_obj->a_buf_rx, 0x00, sizeof(uint8_t) * p_obj->buf_rx_len);

		
		if (tx->p_cfg->p_info->length) p_obj->buf_tx_len = tx->p_cfg->p_info->length;
		else p_obj->buf_tx_len = SILCNTS_UART_DTC_BUF_LEN_DEFAULT;
		memset(p_obj->a_buf_tx, 0x00, sizeof(uint8_t) * p_obj->buf_tx_len);
		
		p_obj->a_buf_tmp_len = SILCNTS_UART_DTC_BUF_LEN_DEFAULT;
		p_obj->a_buf_mainloop_len = SILCNTS_UART_DTC_BUF_LEN_DEFAULT;
		memset(p_obj->a_buf_tmp, 0x00, sizeof(uint8_t) * p_obj->a_buf_tmp_len);
		
		p_obj->event_tx = UART_DTC_STS_TX_COMPLETE;
		p_obj->event_rx = UART_DTC_STS_RX_COMPLETE;

		err = R_SCI_UART_Open(uart->p_ctrl, uart->p_cfg);
		if (FSP_SUCCESS == err) {
			SIL_UART_DTC_Regs_Mapping(p_obj);
			err = R_DTC_Open(tx->p_ctrl, tx->p_cfg);
			if ((FSP_SUCCESS == err) || (FSP_ERR_IN_USE == err)) {
			    err = R_DTC_Open(rx->p_ctrl, rx->p_cfg);
			}
			
		}
		p_obj->initialized = 1;
	}
	
	return err;
}

fsp_err_t SIL_UART_DTC_Enter2(sil_uart_dtc_s *obj) {

    fsp_err_t err = -1;
    sil_uart_dtc_s *p_obj = obj;
    uart_instance_t *uart = (p_obj->p_uart) ? p_obj->p_uart : (uart_instance_t *) 0;
    transfer_instance_t *tx = (transfer_instance_t *) 0;
    transfer_instance_t *rx = (transfer_instance_t *) 0;

    (void) uart;

    if (p_obj && (p_obj->initialized == 1)) {
        uart = (p_obj->p_uart) ? p_obj->p_uart : (uart_instance_t *) 0;
		tx = (p_obj->p_transfer_tx) ? (transfer_instance_t *)p_obj->p_transfer_tx : (transfer_instance_t *) 0;
		rx = (p_obj->p_transfer_rx) ? (transfer_instance_t *)p_obj->p_transfer_rx : (transfer_instance_t *) 0;
		
        if (tx && tx->p_ctrl) err = R_DTC_Enable(tx->p_ctrl);
        if (rx && rx->p_ctrl) err = R_DTC_Enable(rx->p_ctrl);

        p_obj->initialized = 2;

        err = SIL_UART_DTC_ReadRestart(p_obj);
    }
	
	return err;
}

fsp_err_t SIL_UART_DTC_MainLoop1(sil_uart_dtc_s *obj) {
	
	fsp_err_t err = FSP_SUCCESS;
	sil_uart_dtc_s *p_obj = (sil_uart_dtc_s *)obj;
	
	if (p_obj && p_obj->initialized) SIL_UART_DTC_FlushWriteBuffer(p_obj);
	
	return err;
}

fsp_err_t SIL_UART_DTC_MainLoop2(sil_uart_dtc_s *obj) {
	
	return SIL_UART_DTC_MainLoop1(obj) ;
}

fsp_err_t SIL_UART_DTC_Exit(sil_uart_dtc_s *obj) {
	(void) obj;
	
	sil_uart_dtc_s *p_obj = obj;
	uart_instance_t *uart;
	transfer_instance_t *tx;
	transfer_instance_t *rx;
	fsp_err_t err = -1;

	if (p_obj && p_obj->initialized) {
	    p_obj->initialized = 0;
        uart = (p_obj->p_uart) ? p_obj->p_uart : (uart_instance_t *) 0;
        tx = (transfer_instance_t *) p_obj->p_transfer_tx;
        rx = (transfer_instance_t *) p_obj->p_transfer_rx;

        err = R_SCI_UART_Close(uart->p_ctrl);

        if (err == FSP_SUCCESS) err = R_DTC_Disable(tx->p_ctrl);
        if (err == FSP_SUCCESS) err = R_DTC_Disable(rx->p_ctrl);
        if (err == FSP_SUCCESS) err = R_DTC_Close(tx->p_ctrl);
        if (err == FSP_SUCCESS) err = R_DTC_Close(rx->p_ctrl);

        SIL_RINGBUF_Deinit(&p_obj->ringbuf_tx);
        SIL_RINGBUF_Deinit(&p_obj->ringbuf_rx);

        memset(p_obj->a_buf_rx, 0x00, p_obj->buf_rx_len);
        memset(p_obj->a_buf_tx, 0x00, p_obj->buf_tx_len);


	}
	return err;
}

fsp_err_t SIL_UART_DTC_Restart(sil_uart_dtc_s *obj) {

    sil_uart_dtc_s *p_obj = obj;
    fsp_err_t err = -1;

    if (p_obj) {
        err = SIL_UART_DTC_Exit(p_obj);

        if (err == FSP_SUCCESS) err = SIL_UART_DTC_Enter1(
                                                        p_obj,
                                                        p_obj->p_uart,
                                                        p_obj->p_transfer_tx,
                                                        p_obj->p_transfer_rx
                                                        );

        if (err == FSP_SUCCESS) err = SIL_UART_DTC_Enter2(p_obj);
        //if (err == FSP_SUCCESS) SIL_APP_TICKS_Delay(1, SIL_TICK_SYS_DLY_MS_1);


    }
    return err;
}



















