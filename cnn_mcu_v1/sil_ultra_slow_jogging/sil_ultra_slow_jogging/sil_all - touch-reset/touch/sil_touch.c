#include "sil_touch.h"
#include "..\filter_mdn\sil_filter_mdn.h"
#include <stdlib.h>

static void SIL_TOUCH_GetZeroLevel(sil_touch_s *obj) {
	uint8_t i;
	sil_touch_s *p_obj = (sil_touch_s *)obj;
	float d;

    if (p_obj && p_obj->is_calibrating) {

	
	
		for (i = 0; i < TOUCH_CHS_FINAL_E; i ++) {
			if (p_obj->a_data_zero_max[i] < p_obj->a_data_ch[i]) {
			    d = p_obj->a_data_ch[i];
				//d = d * 1.001f;
			    //d = d * 0.999f;
			    p_obj->a_data_zero_max[i] = (uint16_t) d;

			}
		}
	}
}

fsp_err_t SIL_TOUCH_StartScan(sil_touch_s *obj) {

    fsp_err_t err = FSP_ERR_INVALID_POINTER;
    sil_touch_s *p_obj = (sil_touch_s *) obj;

    if (p_obj && p_obj->p_touch_config01 && p_obj->p_ctsu_event && p_obj->p_touch_config01->p_ctrl) {
        if (*p_obj->p_ctsu_event == CTSU_EVENT_SCAN_COMPLETE) err = RM_TOUCH_ScanStart(p_obj->p_touch_config01->p_ctrl);
    }

/* for test 
	char buf[64];
	snprintf(buf, 64, "%d, %d, %d, %d\r\n", p_obj->a_data_ch[TOUCH_CHS_LEFT_UP], p_obj->a_data_ch[TOUCH_CHS_LEFT_DWN],
								p_obj->a_data_ch[TOUCH_CHS_RIGHT_UP], p_obj->a_data_ch[TOUCH_CHS_RIGHT_DWN]);
	SIL_UART_DTC_TOPC_WriteToTxBuffer((uint8_t *) buf, (uint16_t) strlen(buf));
	//SIL_UART_DTC_TOBLE_WriteToTxBuffer((uint8_t *) buf, (uint16_t) strlen(buf));
// */
    return err;

}

static void SIL_TOUCH_RemapRawData(sil_touch_s *obj) {

    sil_touch_s *p_obj = (sil_touch_s *)obj;
    uint8_t i;
	uint16_t data[TOUCH_CHS_FINAL_E];
	//int32_t d, d1;


    if (p_obj) {
        for (i = 0; i < TOUCH_CHS_FINAL_E; i ++) {
            p_obj->a_data_ch[i] = p_obj->a_data_ch[i] - p_obj->a_ref_data_ch[i];
			
			if (p_obj->a_data_ch[i] < p_obj->a_data_zero_max[i]) data[i] = p_obj->a_data_zero_max[i];
			else data[i] = p_obj->a_data_ch[i];

			data[i] = data[i] - p_obj->a_data_zero_max[i];

			// get median
			if (p_obj->a_data_ch_last[i] == (uint16_t) -1) {
			    p_obj->a_data_ch_last[i] = data[i];
				p_obj->count_data_collect = 0;
			    memset(p_obj->pa_data_collect[i], 0, sizeof(uint16_t) * p_obj->data_collect_points);
			}
			p_obj->pa_data_collect[i][p_obj->count_data_collect % p_obj->data_collect_points] = data[i];
			if ((uint32_t)(p_obj->count_data_collect % p_obj->data_collect_points) == (uint32_t)(p_obj->data_collect_points - 1)) {

			    p_obj->a_data_ch_last[i] = SIL_FILTER_MDN_GetFiltered(p_obj->pa_data_collect[i], p_obj->data_collect_points);

			    //d = SIL_FILTER_MDN_GetFiltered(p_obj->pa_data_collect[i], p_obj->data_collect_points);
			    //d1 = p_obj->a_data_ch_last[i];
			    //p_obj->a_data_ch_last[i] = (uint16_t)((d - d1) * 0.1 + d1);

			}

			data[i] = p_obj->a_data_ch_last[i];
			p_obj->a_data_ch[i] = (uint16_t) SIL_FILTER_MA_Get(&p_obj->a_filter_ma[i], data[i]);
			//p_obj->a_data_ch[i] = data[i];

			//if (p_obj->a_data_ch[i] < SILCNTS_TOUCH_FORCE_ZERO_THRD) p_obj->a_data_ch[i] = 0;

/*
            if (i != 3) p_obj->a_data_ch[i] = (uint16_t) SIL_FILTER_MA_Get(&p_obj->a_filter_ma[i], data[i]);
            else {
                p_obj->a_data_ch[3] = data[3];
                p_obj->a_data_ch[0] = (uint16_t) SIL_FILTER_MA_Get(&p_obj->a_filter_ma[3], data[3]);
                p_obj->a_data_ch[1] = p_obj->a_data_ch[0];
                p_obj->a_data_ch[2] = p_obj->a_data_ch[0];

            }
// */

        }
        p_obj->count_data_collect ++;
    }
}

fsp_err_t SIL_TOUCH_GetChannelsData(sil_touch_s *obj) {

	fsp_err_t err = FSP_ERR_INVALID_POINTER;
    sil_touch_s *p_obj = (sil_touch_s *)obj;
	touch_instance_ctrl_t *p_ctrl = (touch_instance_ctrl_t *) 0;

    if ((p_obj && p_obj->p_touch_config01 && p_obj->p_touch_config01->p_ctrl) &&
		(p_obj->p_touch_config01->p_cfg->num_buttons == TOUCH_CHS_FINAL_E)) {

		err = FSP_ERR_ETHER_ERROR_NO_DATA;
		
		if (p_obj->count_watchdog_last > (p_obj->count_watchdog + 20)) {
			SIL_TOUCH_Restart(p_obj);
		}
		
		p_obj->count_watchdog_last ++;
		
		if (*p_obj->p_touch_flag == true) {
			*p_obj->p_touch_flag = false;

			p_obj->count_watchdog_last = p_obj->count_watchdog;
			p_obj->count_watchdog ++;

			p_ctrl = p_obj->p_touch_config01->p_ctrl;
			/* Get the sensor data */
			p_ctrl->p_ctsu_instance->p_api->dataGet(p_ctrl->p_ctsu_instance->p_ctrl, p_obj->a_data_ch);

			if (p_ctrl->binfo.p_reference) memcpy(p_obj->a_ref_data_ch, p_ctrl->binfo.p_reference, sizeof(uint16_t) * TOUCH_CHS_FINAL_E);

			SIL_TOUCH_GetZeroLevel(p_obj);
			SIL_TOUCH_RemapRawData(p_obj);
		}
	}
	return err;
}

fsp_err_t SIL_TOUCH_Enter1(
                            sil_touch_s *obj,
                            timer_instance_t *tmr,
                            elc_instance_t *elc,
                            touch_instance_t *touch,
                            //uint8_t *touch_flag,
                            //ctsu_event_t *ctsu_event,
                            sil_touch_flag_s flag,
                            uint8_t moving_points,
                            uint8_t collect_points
							) {

	fsp_err_t err = FSP_ERR_INVALID_POINTER;
	sil_touch_s *p_obj = (sil_touch_s *)obj;
	uint8_t i;
	
	if (p_obj && tmr && elc && touch && flag.p_touch_flag && flag.p_ctsu_event) {
//const timer_instance_t g_timer0 =
//{ .p_ctrl = &g_timer0_ctrl, .p_cfg = &g_timer0_cfg, .p_api = &g_timer_on_agt };
		if (p_obj->clear_watchdog == 0) p_obj->p_timer = tmr;

//const elc_instance_t g_elc =
//{ .p_ctrl = &g_elc_ctrl, .p_api = &g_elc_on_elc, .p_cfg = &g_elc_cfg };
		if (p_obj->clear_watchdog == 0) p_obj->p_elc = elc;
	
//const touch_instance_t g_qe_touch_instance_config01 =
//{
//    .p_ctrl = &g_qe_touch_ctrl_config01,
//    .p_cfg  = &g_qe_touch_cfg_config01,
//    .p_api  = &g_touch_on_ctsu,
//};
		if (p_obj->clear_watchdog == 0) p_obj->p_touch_config01 = touch;
		//p_obj->p_touch_flag = touch_flag;
		if (p_obj->clear_watchdog == 0) p_obj->p_touch_flag = flag.p_touch_flag;
		if (p_obj->clear_watchdog == 0) p_obj->p_ctsu_event = flag.p_ctsu_event;
		if (p_obj->clear_watchdog == 0) p_obj->is_calibrating = 1;
		p_obj->count = 0;
		
		if (p_obj->p_elc->p_ctrl && p_obj->p_elc->p_cfg) 
			err = R_ELC_Open(p_obj->p_elc->p_ctrl, p_obj->p_elc->p_cfg);
		
		if ((err == FSP_SUCCESS) && p_obj->p_touch_config01->p_ctrl && p_obj->p_touch_config01->p_cfg) 
			err = RM_TOUCH_Open(p_obj->p_touch_config01->p_ctrl, p_obj->p_touch_config01->p_cfg);
		
		if ((err == FSP_SUCCESS) && p_obj->p_timer->p_ctrl && p_obj->p_timer->p_cfg) 
			err = R_AGT_Open(p_obj->p_timer->p_ctrl, p_obj->p_timer->p_cfg);

		p_obj->count_data_collect = 0;
		if (p_obj->clear_watchdog == 0) {
			if (moving_points == 0) moving_points = SILCNTS_TOUCH_FILTER_MA_POINTS_DEFAULT;
		}
		if (p_obj->clear_watchdog == 0) {
			if (collect_points == 0) collect_points = SILCNTS_TOUCH_FILTER_MDN_COLLECT_POINTS_DEFAULT;
		}
		
		if (p_obj->clear_watchdog == 0) p_obj->data_collect_points = collect_points;
			
		for (i = 0; i < TOUCH_CHS_FINAL_E; i ++) {
			if (p_obj->clear_watchdog == 0) {
				p_obj->a_data_ch[i] = 0;
				p_obj->a_ref_data_ch[i] = 0;
				p_obj->a_data_zero_max[i] = 0;
			}

			if (p_obj->clear_watchdog == 0) SIL_FILTER_MA_Init(&p_obj->a_filter_ma[i], moving_points);
			else SIL_FILTER_MA_Init(&p_obj->a_filter_ma[i], p_obj->a_filter_ma[i].pts);

			if (p_obj->clear_watchdog == 0) p_obj->pa_data_collect[i] = (uint16_t *) malloc(sizeof(uint16_t) * collect_points);
			if (p_obj->clear_watchdog == 0) p_obj->a_data_ch_last[i] = (uint16_t) -1;
	
			memset(p_obj->pa_data_collect[i], 0, sizeof(uint16_t) * collect_points);
		}
		p_obj->clear_watchdog = 0;
	}

	return err;
}

fsp_err_t SIL_TOUCH_Enter2(sil_touch_s *obj) {
	
	fsp_err_t err = FSP_ERR_INVALID_POINTER;
	sil_touch_s *p_obj = (sil_touch_s *)obj;
	
//const timer_instance_t g_timer0 =
//{ .p_ctrl = &g_timer0_ctrl, .p_cfg = &g_timer0_cfg, .p_api = &g_timer_on_agt };

//const elc_instance_t g_elc =
//{ .p_ctrl = &g_elc_ctrl, .p_api = &g_elc_on_elc, .p_cfg = &g_elc_cfg };

//const touch_instance_t g_qe_touch_instance_config01 =
//{
//    .p_ctrl = &g_qe_touch_ctrl_config01,
//    .p_cfg  = &g_qe_touch_cfg_config01,
//    .p_api  = &g_touch_on_ctsu,
//};
	if (p_obj) {
		if (p_obj->p_elc && p_obj->p_elc->p_ctrl) 
			err = R_ELC_Enable(p_obj->p_elc->p_ctrl);
		
		if ((err == FSP_SUCCESS) && p_obj->p_timer && p_obj->p_timer->p_ctrl) 
			err = R_AGT_Start(p_obj->p_timer->p_ctrl);
		
		if ((err == FSP_SUCCESS) && p_obj->p_touch_config01 && p_obj->p_touch_config01->p_ctrl) {
			p_obj->count_watchdog = 0;
			p_obj->count_watchdog_last = 0;
			err = RM_TOUCH_ScanStart(p_obj->p_touch_config01->p_ctrl);
		}
	}

	return err;
}

void SIL_TOUCH_MainLoop1(sil_touch_s *obj) {
	sil_touch_s *p_obj = (sil_touch_s *)obj;
	
	if (p_obj) p_obj->is_calibrating = 1;

}

void SIL_TOUCH_MainLoop2(sil_touch_s *obj) {
	sil_touch_s *p_obj = (sil_touch_s *)obj;
	
	if (p_obj) p_obj->is_calibrating = 0;
}

void SIL_TOUCH_Exit(sil_touch_s *obj) {
	sil_touch_s *p_obj = (sil_touch_s *)obj;
	volatile fsp_err_t err = FSP_ERR_INVALID_POINTER;
	
	if (p_obj) {
		if (p_obj->clear_watchdog == 1) p_obj->is_calibrating = 0;

		err = RM_TOUCH_ScanStop(p_obj->p_touch_config01->p_ctrl);
		err = R_ELC_Disable(p_obj->p_elc->p_ctrl);
		err = R_AGT_Stop(p_obj->p_timer->p_ctrl);

		err = R_AGT_Close(p_obj->p_timer->p_ctrl);
		err = RM_TOUCH_Close(p_obj->p_touch_config01->p_ctrl);
		err = R_ELC_Close(p_obj->p_elc->p_ctrl);

	}
}

fsp_err_t SIL_TOUCH_Restart(sil_touch_s *obj) {

	fsp_err_t err = FSP_ERR_INVALID_POINTER;
	sil_touch_s *p_obj = (sil_touch_s *)obj;
	sil_touch_flag_s flag = {p_obj->p_touch_flag, p_obj->p_ctsu_event};

	if (p_obj) {
			p_obj->clear_watchdog = 1;

        	SIL_TOUCH_Exit(p_obj);

        	err = SIL_TOUCH_Enter1(
        	                        p_obj,
									p_obj->p_timer,
									p_obj->p_elc,
									p_obj->p_touch_config01,
									flag,
									SILCNTS_TOUCH_FILTER_MA_POINTS_DEFAULT,
									SILCNTS_TOUCH_FILTER_MDN_COLLECT_POINTS_DEFAULT
									);

        	if (err == FSP_SUCCESS) err = SIL_TOUCH_Enter2(p_obj);




			p_obj->is_calibrating = 0;
    	}
    	return err;
}


