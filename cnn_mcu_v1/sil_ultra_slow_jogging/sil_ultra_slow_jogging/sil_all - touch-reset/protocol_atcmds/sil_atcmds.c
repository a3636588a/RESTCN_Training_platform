#include "..\globals\sil_globals.h"
#include "sil_atcmds.h"
#include "..\uart_dtc\sil_uart_dtc_topc.h"
#include "..\uart_dtc\sil_uart_dtc_toble.h"
#include "..\app\sil_app_rtc.h"
#include "..\app\sil_app_buzzer.h"
#include "..\app\sil_app_ultra_slow_jogging.h"
#include "..\app\sil_app_ticks.h"
#include <stdlib.h>

// msg: $GPVTG,,T,,M,0.00,N,0.0,K,A*13\n
// calculating data "GPVTG,,T,,M,0.00,N,0.0,K,A"
// v = at_cmds_checksum("$GPVTG,,T,,M,0.00,N,0.0,K,A*13\n");
// v = 0x13
uint16_t SIL_ATCMDS_Checksum(uint8_t *d) {
	uint8_t crc = 0, *p = d;
	int32_t i = 0, datLen;
	
	datLen = (int32_t) strlen((char *) d);
    // the first $ sign and the last two bytes of original CRC + the * sign
	for (i = 0; i < datLen; i ++) {
		if (p[i] == (uint8_t)'$') {
			continue;
		}
		if (p[i] == (uint8_t)'*') {
			break;
		}
        crc ^= d[i];
    }
    return crc;
}

void SIL_ATCMDS_IntToAsciiDecimal(int32_t s, uint8_t *d, uint16_t size) {
	uint32_t l, i;
	uint8_t tmp;
	uint8_t negative = 0;
	
	if (s < 0) {
		s = (-1) * s;
		negative = 1;
	}
	
	memset ((char *)d, 0x00, size);
	for (i = 0; i < size; i ++) {
		d[i] = (uint8_t)((s % 10) + 0x30);
		s = s / 10;
		if (s == 0) {
			break;
		}
	}
	if (i > 0) {
		for (l=0; l<((i + 1) / 2); l++) {
			tmp = d[i-l];
			d[i-l] = d[l];
			d[l] = tmp;
		}
	}
	if (negative) {
		l = strlen((char *) d);
		for (i = l; i > 0; i --) {
			d[i] = d[i-1];
		}
		d[0] = '-';
	}
}

void SIL_ATCMDS_ChecksumToHex(int32_t s, uint8_t *d, uint16_t size) {
	uint8_t hex[16] = {'0', '1', '2', '3', '4', '5', '6', '7', '8', '9', 'A', 'B', 'C', 'D', 'E', 'F'};
	
	memset (d, 0x00, size);
	d[1] = hex[(s % 16)];
	s = s / 16;
	d[0] = hex[(s % 16)];
	
}

void SIL_ATCMDS_SendSiljrc(sil_atcmds_io_e io, uint32_t cnt, uint32_t jumps) {
	
	uint16_t cs;
	uint8_t buf[SILCNTS_ATCMDS_UART_MAX_BS] = {0};

	memset(buf, 0x00, SILCNTS_ATCMDS_UART_MAX_BS * sizeof(uint8_t));
	// "$SILJRC,%d,%d,%d*%02X\r\n"
	snprintf((char *)buf, SILCNTS_ATCMDS_UART_MAX_BS,
	        SILCNTS_ATCMDS_SILJRC_OUT,
	        SILCNTS_ATCMDS_SILJRC_OUT_VER,
	        (unsigned int)cnt,
	        (unsigned int)jumps,
	        0);

	cs = SIL_ATCMDS_Checksum(buf);
	snprintf((char *)buf, SILCNTS_ATCMDS_UART_MAX_BS,
	        SILCNTS_ATCMDS_SILJRC_OUT,
	        SILCNTS_ATCMDS_SILJRC_OUT_VER,
	        (unsigned int)cnt,
	        (unsigned int)jumps,
	        cs);

	if (io == ATCMDS_IO_TOPC) SIL_UART_DTC_TOPC_WriteToTxBuffer(buf, (uint16_t) strlen((char *)buf));
	if (io == ATCMDS_IO_TOBLE) SIL_UART_DTC_TOBLE_WriteToTxBuffer(buf, (uint16_t) strlen((char *)buf));
	

}

//	$SILUSJSTPS,20240130,2,1.5,1.0*2F
void SIL_ATCMDS_SendSilusjstps(sil_atcmds_io_e io, uint32_t cnt, uint32_t left, uint32_t right) {
	
	uint16_t cs;
	uint8_t buf[SILCNTS_ATCMDS_UART_MAX_BS] = {0};

	memset(buf, 0x00, SILCNTS_ATCMDS_UART_MAX_BS * sizeof(uint8_t));
	// "$SILUSJSTPS,%d,%d,%0.1f,%0.1f*%02X\r\n"
	snprintf((char *)buf, SILCNTS_ATCMDS_UART_MAX_BS,
	        SILCNTS_ATCMDS_SILUSJSTPS_OUT,
	        SILCNTS_ATCMDS_SILUSJSTPS_OUT_VER,
	        (unsigned int)cnt,
	        (unsigned int)left,
	        (unsigned int)right,
	        0);

	cs = SIL_ATCMDS_Checksum(buf);
	snprintf((char *)buf, SILCNTS_ATCMDS_UART_MAX_BS,
	        SILCNTS_ATCMDS_SILUSJSTPS_OUT,
	        SILCNTS_ATCMDS_SILUSJSTPS_OUT_VER,
	        (unsigned int)cnt,
	        (unsigned int)left,
	        (unsigned int)right,
	        cs);

	if (io == ATCMDS_IO_TOPC) SIL_UART_DTC_TOPC_WriteToTxBuffer(buf, (uint16_t) strlen((char *)buf));
	if (io == ATCMDS_IO_TOBLE) SIL_UART_DTC_TOBLE_WriteToTxBuffer(buf, (uint16_t) strlen((char *)buf));
	

}

// $SILI5O,20240130,7454,241.000,-212.000,241.000,-212.000,241.000*64
// $SILI6O,20240130,7454,241.000,-212.000,241.000,-212.000,241.000,241.000*62
void SIL_ATCMDS_SendSilino(sil_atcmds_io_e io, uint32_t cnt, uint16_t *ch, uint16_t size) {

    uint16_t cs;
    uint8_t buf[SILCNTS_ATCMDS_UART_MAX_BS] = {0};
    uint8_t tmp[32] = {0};
    uint16_t index = 0;
    uint32_t i;
	
    //$SILINO,%d,%d,%d,%d*%02X\r\n
	snprintf((char *)buf, SILCNTS_ATCMDS_UART_MAX_BS, "$SILINO,%d,%u,%u,", 
												SILCNTS_ATCMDS_SILINO_OUT_VER,
												(unsigned int)cnt,
												(unsigned int)size
												);


    for (i = 0; i < size; i ++) {
		snprintf((char *)tmp, 32, "%u,", (unsigned int)ch[i]);
		index = (uint16_t)strlen((char *)buf);
		memcpy(&buf[index], tmp, strlen((char *)tmp));
    }
	index = (uint16_t)strlen((char *)buf);
    buf[index - 1] = '*';

    cs = SIL_ATCMDS_Checksum(buf);
    SIL_ATCMDS_ChecksumToHex(cs, tmp, 4);
    memcpy(&buf[index], tmp, strlen((char *)tmp));
    index += (uint16_t) strlen((char *)tmp);
    buf[index++] = '\r';
    buf[index++] = '\n';
    buf[index++] = 0;


    if (io == ATCMDS_IO_TOPC) SIL_UART_DTC_TOPC_WriteToTxBuffer(buf, (uint16_t) strlen((char *)buf));
    //if (io == ATCMDS_IO_TOBLE) SIL_UART_DTC_TOBLE_WriteToTxBuffer(buf, (uint16_t) strlen((char *)buf));



}

static int32_t SIL_ATCMDS_StrToInt(char *str, uint32_t len, int base) {
    char *tt;
    long ret = -1;
    char buf[16+1];

    if (len <= 16) {
        memset(buf, 0x00, sizeof(buf));
        memcpy(buf, str, (size_t)len);
        ret = strtol((char *)buf, &tt, base);
    }
    return (int32_t) ret;
}

#if 0
static float SIL_ATCMDS_StrToFloat(char *str, int32_t len) {
    char *tt;
    float ret = -1.0;
    char buf[16+1];

    if (len <= 16) {
        memset(buf, 0x00, sizeof(buf));
        memcpy(buf, str, (size_t)len);
        ret = strtof((char *)buf, &tt);
    }
    return ret;
}
#endif

char *SIL_ATCMDS_CutCommand(char *in, uint32_t *offset) {
    int32_t len = (int32_t) strlen(in), i = 0;

    if (len > SILCNTS_ATCMDS_UART_MAX_BS) return (char *) 0;


    for (i = 0; i < len; i ++) {
        if (in[i] != ',') continue;
        in[i] = 0;
        break;
    }
    *offset = (uint32_t)(i + 1);

    return in;
}

// nD: next Data pointer
sil_atcmds_cmds_in_e SIL_ATCMDS_ProcessAtcmds(char *d, char **nD) {
    uint32_t len = (uint32_t)strlen(d), ll = 0;
    int result = 0;
    char buf[4];
    int cs;
    char *p = d;
    sil_atcmds_cmds_in_e cmd = ATCMDS_CMDS_IN_UNKNOWN_E;

    if (len > SILCNTS_ATCMDS_UART_MAX_BS) goto EXIT;


    // check checksum
    cs = SIL_ATCMDS_Checksum((uint8_t *)p);
    snprintf(buf, 4, "%02X", cs);
    result = strncmp(buf, (const char *) &p[len - 4], 2);
    if (result != 0) goto EXIT;

    // SILSFI
    ll = strlen(SILCNTS_ATCMDS_SILSFI);
    result = strncmp(SILCNTS_ATCMDS_SILSFI, (const char *) p, (size_t)ll);
    if (result == 0) {
        *nD = d + ll;
        p[len - 5] = ',';
        p[len - 4] = 0;
        cmd = ATCMDS_CMDS_IN_SILSFI_E;
        goto EXIT;
    }

    // SILSWRB
    ll = strlen(SILCNTS_ATCMDS_SILSWRB);
    result = strncmp(SILCNTS_ATCMDS_SILSWRB, (const char *) p, (size_t)ll);
    if (result == 0) {
        *nD = d + ll;
        p[len - 5] = ',';
        p[len - 4] = 0;
        cmd = ATCMDS_CMDS_IN_SILSWRB_E;
        goto EXIT;
    }

	// SILRTCI
    ll = strlen(SILCNTS_ATCMDS_SILRTCI);
    result = strncmp(SILCNTS_ATCMDS_SILRTCI, (const char *) p, (size_t)ll);
    if (result == 0) {
        *nD = d + ll;
        p[len - 5] = ',';
        p[len - 4] = 0;
        cmd = ATCMDS_CMDS_IN_SILRTCI_E;
        goto EXIT;
    }

    // SILAPP
    ll = strlen(SILCNTS_ATCMDS_SILAPP);
    result = strncmp(SILCNTS_ATCMDS_SILAPP, (const char *) p, (size_t)ll);
    if (result == 0) {
        *nD = d + ll;
        p[len - 5] = ',';
        p[len - 4] = 0;
        cmd = ATCMDS_CMDS_IN_SILAPP_E;
        goto EXIT;
    }
	
	


EXIT:
    return cmd;
}

// $SILAPP,20240130,0*21\r\n
static void SIL_ATCMDS_DispatchSilapp(uint8_t *buf, uint16_t len) {
    uint8_t *d;
    uint8_t *p = buf;
    uint32_t offset = 0;
    int32_t ver;
	sil_app_type_e app = SIL_APP_UNKNOWN_E;

    (void) len;

    d = (uint8_t *)SIL_ATCMDS_CutCommand((char *)p, &offset);
    ver = SIL_ATCMDS_StrToInt((char *)p, (uint32_t)strlen((char *)d), 10);  // 20240130
    p = p + offset;

    if (ver == SILCNTS_ATCMDS_SILAPP_IN_VER) {
        d = (uint8_t *)SIL_ATCMDS_CutCommand((char *)p, &offset);
        app = SIL_ATCMDS_StrToInt((char *)p, (uint32_t)strlen((char *)d), 10);
        p = p + offset;
		
		SIL_APP_USJ_SwitchType(app);
    }
}

// $SILSWRT,20240130,3,16,32,2*79\r\n
static void SIL_ATCMDS_DispatchSilswrb(uint8_t *buf, uint16_t len) {
    uint8_t *d;
    uint8_t *p = buf;
    uint32_t offset = 0;
    int32_t ver;

    (void) len;

    d = (uint8_t *)SIL_ATCMDS_CutCommand((char *)p, &offset);
    ver = SIL_ATCMDS_StrToInt((char *)p, (uint32_t)strlen((char *)d), 10);  // 20240130
    p = p + offset;

    if (ver == SILCNTS_ATCMDS_SILSWRB_IN_VER) {
		//SIL_APP_BUZZER_SetSoftwareReset(1);

        //SIL_APP_TICKS_Delay(1, SIL_TICK_SYS_DLY_S_1);
        SIL_GLOBALS_Reboot();

    }
}

// $SILRTCI,20240130,125,10,30,04,09,28,18*66\r\n
static void SIL_ATCMDS_DispatchSilrtci(uint8_t *buf, uint16_t len) {
    uint8_t *d;
    uint8_t *p = buf;
    uint32_t offset = 0;
    int32_t ver;
    rtc_time_t time_current;

    (void) len;

    d = (uint8_t *)SIL_ATCMDS_CutCommand((char *)p, &offset);
    ver = SIL_ATCMDS_StrToInt((char *)p, (uint32_t)strlen((char *)d), 10);  // 20240130
    p = p + offset;

    if (ver == SILCNTS_ATCMDS_SILRTCI_IN_VER) {
        d = (uint8_t *)SIL_ATCMDS_CutCommand((char *)p, &offset);
        time_current.tm_year = SIL_ATCMDS_StrToInt((char *)p, (uint32_t)strlen((char *)d), 10);
        p = p + offset;

        d = (uint8_t *)SIL_ATCMDS_CutCommand((char *)p, &offset);
        time_current.tm_mon = SIL_ATCMDS_StrToInt((char *)p, (uint32_t)strlen((char *)d), 10);
		time_current.tm_mon = time_current.tm_mon - 1;
        p = p + offset;

        d = (uint8_t *)SIL_ATCMDS_CutCommand((char *)p, &offset);
        time_current.tm_mday = SIL_ATCMDS_StrToInt((char *)p, (uint32_t)strlen((char *)d), 10);
        p = p + offset;

        d = (uint8_t *)SIL_ATCMDS_CutCommand((char *)p, &offset);
        time_current.tm_wday = SIL_ATCMDS_StrToInt((char *)p, (uint32_t)strlen((char *)d), 10);
        p = p + offset;

        d = (uint8_t *)SIL_ATCMDS_CutCommand((char *)p, &offset);
        time_current.tm_hour = SIL_ATCMDS_StrToInt((char *)p, (uint32_t)strlen((char *)d), 10);
        p = p + offset;

        d = (uint8_t *)SIL_ATCMDS_CutCommand((char *)p, &offset);
        time_current.tm_min = SIL_ATCMDS_StrToInt((char *)p, (uint32_t)strlen((char *)d), 10);
        p = p + offset;

        d = (uint8_t *)SIL_ATCMDS_CutCommand((char *)p, &offset);
        time_current.tm_sec = SIL_ATCMDS_StrToInt((char *)p, (uint32_t)strlen((char *)d), 10);
		
		SIL_APP_RTC_SetTime(&time_current);
    }
}


void SIL_ATCMDS_DispatchCmds(sil_atcmds_io_e io, sil_atcmds_cmds_in_e cmd, char *buf, uint16_t len) {

    (void) io;
    (void) buf;
    (void) len;


    switch (cmd) {
    case ATCMDS_CMDS_IN_SILSFI_E:

        break;

    case ATCMDS_CMDS_IN_SILSWRB_E:
        SIL_ATCMDS_DispatchSilswrb((uint8_t *)buf, len);
        break;

	case ATCMDS_CMDS_IN_SILRTCI_E:
		SIL_ATCMDS_DispatchSilrtci((uint8_t *)buf, len);
		break;

	case ATCMDS_CMDS_IN_SILAPP_E:
		SIL_ATCMDS_DispatchSilapp((uint8_t *)buf, len);
        break;

    default:
        break;
    }
}

static void SIL_ATCMDS_ParseCmds(sil_atcmds_io_e io, char *buf, uint16_t len) {

    sil_atcmds_cmds_in_e cmd;

    char tmpB[256] = {0};
    char *pStart = tmpB;
    char *pEnd = 0;
    uint16_t cnt = 0, cnt1 = 0;
    int i;

    char *pFullPckt = (char *) 0;
	uint16_t pLen = 0;
    char *p = (char *) 0;
    char *pNd = NULL;

	if (io == ATCMDS_IO_TOPC) {
		pFullPckt = (char *) SIL_UART_DTC_TOPC_GetTmpBuf(&pLen, 0);
	}
	else if (io == ATCMDS_IO_TOBLE) {
		pFullPckt = (char *) SIL_UART_DTC_TOBLE_GetTmpBuf(&pLen, 0);
	}
	else return;

    //printf("%s", buf);
    memset(tmpB, 0x00, sizeof(tmpB));
    memcpy(tmpB, pFullPckt, strlen(pFullPckt));
    if (strlen(buf) == (size_t) len) memcpy(tmpB + strlen(pFullPckt), buf, (size_t) len);
    memset(pFullPckt, 0x00, pLen);
    len = (uint16_t) strlen(tmpB);


    while (len > 0) {
        cnt = 0;
        p = (char *) pFullPckt;
        pStart = tmpB;

        for (i = 0; i < len; i++) {
            cnt ++;
            if (*pStart != '$') {
                pStart ++;
                continue;
            }
            else if (*pStart == '$') {
                pEnd = pStart + 1;
                *p++ = *pStart;
                break;
            }

        }
        len = len - cnt;

        cnt1 = 0;
        for (i = 0; i < len; i++) {
            cnt1 ++;

            if (*pEnd == '$') {
                memset(pFullPckt, 0x00, pLen);
                p = (char *) pFullPckt;
                pStart = pEnd;
                *p++ = *pStart;
                pEnd ++;
                continue;
            }

            if (*pEnd != '\n') {
                *p++ = *pEnd;
                pEnd ++;
                continue;
            }
            else if (*pEnd == '\n') {
                *p++ = *pEnd;

                //SIL_UART_DTC_TOPC_WriteToTxBuffer((uint8_t *)pFullPckt, (uint16_t)strlen(pFullPckt));
                //SIL_UART_DTC_TOBLE_WriteToTxBuffer((uint8_t *)pFullPckt, (uint16_t)strlen(pFullPckt));

                cmd = SIL_ATCMDS_ProcessAtcmds(pFullPckt, &pNd);
                SIL_ATCMDS_DispatchCmds(io, cmd, pNd, (uint16_t)strlen(pNd));

                pStart = pEnd + 1;
                if (*pStart) {
                    memcpy(pFullPckt, pStart, strlen(pStart));
                    memset(pFullPckt + strlen(pStart), 0x00, pLen - strlen(pStart));
                    memset(tmpB, 0x00, sizeof(tmpB));
                    memcpy(tmpB, pFullPckt, strlen(pFullPckt));
                }
                else memset(pFullPckt, 0x00, pLen);
                break;
            }
        }

        len = len - cnt1;

        if (len <= 0) break;

    }

}

void SIL_ATCMDS_Enter1() {
}

void SIL_ATCMDS_Enter2() {
}

void SIL_ATCMDS_MainLoop1(sil_atcmds_io_e io) {
	uint8_t *p_buf;
	uint16_t buf_len = 0;
	
	if (io == ATCMDS_IO_TOPC) {
		p_buf = SIL_UART_DTC_TOPC_GetTmpMainLoopBuf(&buf_len);
		SIL_UART_DTC_TOPC_Rcvd_Dequeue(
								p_buf,
								&buf_len
								);
	}
	else if (io == ATCMDS_IO_TOBLE) {
		p_buf = SIL_UART_DTC_TOBLE_GetTmpMainLoopBuf(&buf_len);
		SIL_UART_DTC_TOBLE_Rcvd_Dequeue(
								p_buf,
								&buf_len
								);
	}
	
	if (buf_len) SIL_ATCMDS_ParseCmds(io, (char *) p_buf, buf_len);
	
}

void SIL_ATCMDS_MainLoop2(sil_atcmds_io_e io) {
	SIL_ATCMDS_MainLoop1(io);
}












