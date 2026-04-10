#include "sil_app_touch.h"
#include <stdlib.h>
#include "..\protocol_atcmds\sil_atcmds.h"

sil_app_touch_s gsil_app_touch;

fsp_err_t SIL_APP_TOUCH_StartScan() {
	return SIL_TOUCH_StartScan(&gsil_app_touch.sensor);
}

fsp_err_t SIL_APP_TOUCH_GetChannelsDataPeriod() {
	return SIL_TOUCH_GetChannelsData(&gsil_app_touch.sensor);
}

void SIL_APP_TOUCH_GetAllChannelsData(uint16_t *data, uint8_t chs) {
	
	uint16_t i;
	
	if (data && (chs == (uint8_t)(SILCNTS_APP_TOUCH_CHS_RIGHT + SILCNTS_APP_TOUCH_CHS_LEFT))) {
		for (i = 0; i < chs; i ++) data[i] = gsil_app_touch.sensor.a_data_ch[i];
	}
	
}


void SIL_APP_TOUCH_RawDataToOutside() {
	
	gsil_app_touch.sensor.count ++;
	SIL_ATCMDS_SendSilino(ATCMDS_IO_TOPC, gsil_app_touch.sensor.count, gsil_app_touch.sensor.a_data_ch, TOUCH_CHS_FINAL_E);

	if ((gsil_app_touch.sensor.count % SILCNTS_APP_TOUCH_TOPC_N_TIMES_TOBLE) == 0) {
		SIL_ATCMDS_SendSilino(
								ATCMDS_IO_TOBLE, 
								gsil_app_touch.sensor.count / SILCNTS_APP_TOUCH_TOPC_N_TIMES_TOBLE, 
								gsil_app_touch.sensor.a_data_ch, 
								TOUCH_CHS_FINAL_E
								);
	}

/*	
	char buf[64];
	snprintf(buf, 64, "%d,%d,%d,%d,%d,%d,%d,%d\r\n", 
													data[TOUCH_CHS_LEFT_UP], 
													data[TOUCH_CHS_LEFT_DWN],
													data[TOUCH_CHS_RIGHT_UP], 
													data[TOUCH_CHS_RIGHT_DWN],
													gsil_app_touch.sensor.a_data_zero_max[TOUCH_CHS_LEFT_UP],
													gsil_app_touch.sensor.a_data_zero_max[TOUCH_CHS_LEFT_DWN],
													gsil_app_touch.sensor.a_data_zero_max[TOUCH_CHS_RIGHT_UP],
													gsil_app_touch.sensor.a_data_zero_max[TOUCH_CHS_RIGHT_DWN]);
	SIL_UART_DTC_TOPC_WriteToTxBuffer((uint8_t *) buf, (uint16_t) strlen(buf));
	SIL_UART_DTC_TOBLE_WriteToTxBuffer((uint8_t *) buf, (uint16_t) strlen(buf));
// */

}

static void SIL_APP_TOUCH_Clear(sil_app_touch_s *obj) {
	sil_app_touch_s *p_obj = obj;
	
	if (p_obj) p_obj->count = 0;

}

fsp_err_t SIL_APP_TOUCH_Enter1() {
	
    fsp_err_t err;
	sil_touch_flag_s flag = {&SILVAR_TOUCH_FLAG, &SILVAR_TOUCH_CTSU_EVENT};

	err = SIL_TOUCH_Enter1(
							&gsil_app_touch.sensor, 
							(timer_instance_t *) &SILVAR_TMR_TOUCH_PERIOD_SCAN,
							(elc_instance_t *) &SILVAR_ELC_TOUCH,
							(touch_instance_t *) &SILVAR_TOUCH_CNFG01,
							//(uint8_t *) &SILVAR_TOUCH_FLAG,
                            //(ctsu_event_t *) &SILVAR_TOUCH_CTSU_EVENT,
							flag,
                            SILCNTS_TOUCH_FILTER_MA_POINTS_DEFAULT,
                            SILCNTS_TOUCH_FILTER_MDN_COLLECT_POINTS_DEFAULT
							);


	return err;
}

fsp_err_t SIL_APP_TOUCH_Enter2() {

    fsp_err_t err;
	err = SIL_TOUCH_Enter2(&gsil_app_touch.sensor);
	SIL_APP_TOUCH_Clear(&gsil_app_touch);


	return err;
}

void SIL_APP_TOUCH_MainLoop1() {
	SIL_TOUCH_MainLoop1(&gsil_app_touch.sensor);



}

void SIL_APP_TOUCH_MainLoop2() {
	SIL_TOUCH_MainLoop2(&gsil_app_touch.sensor);


}




