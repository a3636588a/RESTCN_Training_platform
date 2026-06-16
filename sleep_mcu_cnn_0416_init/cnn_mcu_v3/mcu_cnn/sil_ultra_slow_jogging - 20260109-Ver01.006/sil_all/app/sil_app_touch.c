#include "sil_app_touch.h"
#include <stdlib.h>
#include "..\protocol_atcmds\sil_atcmds.h"

sil_app_touch_s gsil_app_touch;

fsp_err_t SIL_APP_TOUCH_StartScan() {
	return SIL_TOUCH_StartScan(&gsil_app_touch.sensor);
}

fsp_err_t SIL_APP_TOUCH_GetChannelsDataPeriod() {
	if (gsil_globals_current_app == SIL_APP_GLOVE_ML_E || gsil_globals_current_app == SIL_APP_DS_E || gsil_globals_current_app == SIL_APP_TINYOL_E) {
		return SIL_TOUCH_GetChannelsDataGlove(&gsil_app_touch.sensor);
	} else {
		return SIL_TOUCH_GetChannelsData(&gsil_app_touch.sensor);
	}
}

void SIL_APP_TOUCH_GetAllChannelsDataGlove(uint16_t *data, uint8_t chs) {
	
	uint16_t i;
	
	if (data && (chs == SILCNTS_GLOVE_CHS_TOTAL)) {
		for (i = 0; i < chs; i ++) data[i] = gsil_app_touch.sensor.a_data_ch[i];
	}
	
}

void SIL_APP_TOUCH_GetAllChannelsData(uint16_t *data, uint8_t chs) {
	
	uint16_t i;
	
	// Original USJ logic: 4 channels
	if (data && (chs == (uint8_t)(SILCNTS_APP_TOUCH_CHS_RIGHT + SILCNTS_APP_TOUCH_CHS_LEFT))) {
		for (i = 0; i < chs; i ++) data[i] = gsil_app_touch.sensor.a_data_ch[i];
	}
	
}


void SIL_APP_TOUCH_RawDataToOutside() {
	
	gsil_app_touch.sensor.count ++;
	
	if (gsil_globals_current_app == SIL_APP_GLOVE_ML_E || gsil_globals_current_app == SIL_APP_DS_E || gsil_globals_current_app == SIL_APP_TINYOL_E) {
		// Glove/DS Mode: 6 channels Raw
		SIL_ATCMDS_SendSilinoGlove(ATCMDS_IO_TOPC, gsil_app_touch.sensor.count, gsil_app_touch.sensor.a_data_ch, SILCNTS_GLOVE_CHS_TOTAL);
	} else {
		// USJ/JRC Mode: 4 channels Processed (+6000)
		SIL_ATCMDS_SendSilino(ATCMDS_IO_TOPC, gsil_app_touch.sensor.count, gsil_app_touch.sensor.a_data_ch, TOUCH_CHS_FINAL_E);

		if ((gsil_app_touch.sensor.count % SILCNTS_APP_TOUCH_TOPC_N_TIMES_TOBLE) == 0) {
			SIL_ATCMDS_SendSilino(
									ATCMDS_IO_TOBLE, 
									gsil_app_touch.sensor.count / SILCNTS_APP_TOUCH_TOPC_N_TIMES_TOBLE, 
									gsil_app_touch.sensor.a_data_ch, 
									TOUCH_CHS_FINAL_E
									);
		}
	}
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

void SIL_APP_TOUCH_Exit() {
	SIL_TOUCH_Exit(&gsil_app_touch.sensor);
}
