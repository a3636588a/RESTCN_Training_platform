#include "sil_touch.h"
#include "..\globals\sil_globals.h"
#include "..\filter_mdn\sil_filter_mdn.h"
#include <stdlib.h>

fsp_err_t SIL_TOUCH_StartScan(sil_touch_s *obj) {

    fsp_err_t err = -1;
    sil_touch_s *p_obj = (sil_touch_s *) obj;

    if (p_obj && p_obj->p_touch_config01 && p_obj->p_ctsu_event && p_obj->p_touch_config01->p_ctrl) {
        if (*p_obj->p_ctsu_event == CTSU_EVENT_SCAN_COMPLETE) {
			*p_obj->p_ctsu_event = -1;

			p_obj->count_reboot = 0;
            err = RM_TOUCH_ScanStart(p_obj->p_touch_config01->p_ctrl);
			if (err == FSP_SUCCESS) p_obj->count_rescan = 0;
        }
        else {
            p_obj->count_reboot ++;
            if (p_obj->count_reboot > 999) {

            }
        }
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

static void SIL_TOUCH_ScaleRawData(uint16_t max, uint16_t *data) {

    int v1 = *data;
    int max1 = max;

    if (data) {
        v1 = v1 - max1;
        *data = (uint16_t) v1;
    }
}

/*
static void SIL_TOUCH_ScaleRawData(uint16_t max, uint16_t *data) {
	
	float max_f = max;
	float dat = *data;
	float dat_calulated;
	

	if (data && max) {
	    max_f = max_f * 2.0f;
		dat_calulated = dat / max_f;
		dat = dat_calulated * 60100;
		
		// *data = (uint16_t) dat;
		*data = (uint16_t)(dat - 30050);
	}
}
// */

static void SIL_TOUCH_GetBaseLevel(sil_touch_s *obj) {
    uint8_t i;
    sil_touch_s *p_obj = (sil_touch_s *)obj;
    uint32_t d, d1;

    if (p_obj && p_obj->is_calibrating) {



        for (i = 0; i < TOUCH_CHS_FINAL_E; i ++) {
            if (p_obj->a_data_zero_max[i] < p_obj->a_data_ch[i]) {
                d = p_obj->a_data_ch[i] - p_obj->a_ref_data_ch[i];
                d1 = p_obj->a_data_zero_max[i];
                //d = d * 1.001f;
                //d = d * 0.999f;
                p_obj->a_data_zero_max[i] = (uint16_t) (d + d1) / 2;
                //if (p_obj->a_data_zero_max[i] > 18500) p_obj->a_data_zero_max[i] = 18500;
            }
        }
    }
}

static void SIL_TOUCH_RemapRawData(sil_touch_s *obj) {

    sil_touch_s *p_obj = (sil_touch_s *)obj;
    uint8_t i;
	uint16_t data[TOUCH_CHS_FINAL_E];
	int32_t d, d1;



    if (p_obj) {
        for (i = 0; i < TOUCH_CHS_FINAL_E; i ++) {
            d = p_obj->a_data_ch[i];
            d1 = p_obj->a_ref_data_ch[i];
            d = d - d1;
            p_obj->a_data_ch[i] = (d > 0) ? (uint16_t) d : 0;
			
			if (p_obj->a_data_ch[i] < p_obj->a_data_zero_max[i]) data[i] = p_obj->a_data_zero_max[i];
			else data[i] = p_obj->a_data_ch[i];

			//data[i] = data[i] - p_obj->a_data_zero_max[i];
			SIL_TOUCH_ScaleRawData(p_obj->a_data_zero_max[i], &data[i]);
			

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
			if (p_obj->a_data_ch[i] <= 40) p_obj->a_data_ch[i] = 0;

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

volatile int galan_count = 0;
volatile int galan_count2 = 0;
fsp_err_t SIL_TOUCH_GetChannelsData(sil_touch_s *obj) {

	fsp_err_t err = -1;
	volatile fsp_err_t err1 = -1;
    sil_touch_s *p_obj = (sil_touch_s *) obj;
	touch_instance_ctrl_t *p_ctrl = (touch_instance_ctrl_t *) 0;
	uint8_t i = 0;
	//uint16_t a_buf_flush[TOUCH_CHS_FINAL_E];

	(void) err1;

    if ((p_obj && p_obj->p_touch_config01 && p_obj->p_touch_config01->p_ctrl) &&
		(p_obj->p_touch_config01->p_cfg->num_buttons >= TOUCH_CHS_FINAL_E)) {

        p_ctrl = p_obj->p_touch_config01->p_ctrl;

		if (*p_obj->p_touch_flag == true) {
			*p_obj->p_touch_flag = false;

			/* Get the sensor data */
			if (*p_obj->p_ctsu_event == CTSU_EVENT_SCAN_COMPLETE) {
			    if (p_ctrl) err = p_ctrl->p_ctsu_instance->p_api->dataGet(p_ctrl->p_ctsu_instance->p_ctrl, p_obj->a_data_ch);
			}
			if (err == FSP_SUCCESS) {
				if (p_ctrl->binfo.p_reference) memcpy(p_obj->a_ref_data_ch, p_ctrl->binfo.p_reference, sizeof(uint16_t) * TOUCH_CHS_FINAL_E);

				for (i = 0; i < TOUCH_CHS_FINAL_E; i ++) {
				    if (p_obj->is_calibrating == 0) p_obj->a_data_ch[i] += 6000;
				}

				SIL_TOUCH_GetBaseLevel(p_obj);
				SIL_TOUCH_RemapRawData(p_obj);
			}
			else RM_TOUCH_ScanStop(p_obj->p_touch_config01->p_ctrl);

			err = -1;
		}

        if ((p_obj->count_rescan == 0) && (*p_obj->p_ctsu_event == CTSU_EVENT_SCAN_COMPLETE)) {
            err = SIL_TOUCH_StartScan(p_obj);
            if (err == FSP_ERR_CTSU_NOT_GET_DATA) {
                //if (p_ctrl) err = p_ctrl->p_ctsu_instance->p_api->dataGet(p_ctrl->p_ctsu_instance->p_ctrl, a_buf_flush);
                if (p_ctrl) err = p_ctrl->p_ctsu_instance->p_api->dataGet(p_ctrl->p_ctsu_instance->p_ctrl, p_obj->a_data_ch);
                galan_count ++;
                if (galan_count > 5) {
                    galan_count = 0;
                }
            }

        }

        if ((err == FSP_SUCCESS) || (p_obj->count_rescan > 10)) {
            if (p_obj->count_rescan >= 10) {
                err1 = RM_TOUCH_ScanStop(p_obj->p_touch_config01->p_ctrl);
                *p_obj->p_ctsu_event = CTSU_EVENT_SCAN_COMPLETE;
            }
            p_obj->count_rescan = 0;
        }
        else {
            p_obj->count_rescan ++;
            if (
                ((p_obj->count_rescan % 5) == 4) ||
                (*p_obj->p_ctsu_event == CTSU_EVENT_OVERFLOW) ||
                (*p_obj->p_ctsu_event == CTSU_EVENT_ICOMP) ||
                (*p_obj->p_ctsu_event == CTSU_EVENT_ICOMP1)
            ) {
                err1 = RM_TOUCH_ScanStop(p_obj->p_touch_config01->p_ctrl);
                galan_count2++;
                if (galan_count2 > 5) {
                    galan_count2 = 0;
                }
            }
            return err;
        }
	}
	return err;
}

fsp_err_t SIL_TOUCH_GetChannelsDataGlove(sil_touch_s *obj) {

	fsp_err_t err = -1;
    sil_touch_s *p_obj = (sil_touch_s *) obj;
	touch_instance_ctrl_t *p_ctrl = (touch_instance_ctrl_t *) 0;

    if (p_obj && p_obj->p_touch_config01 && p_obj->p_touch_config01->p_ctrl) {

        p_ctrl = p_obj->p_touch_config01->p_ctrl;

		if (*p_obj->p_touch_flag == true) {
			*p_obj->p_touch_flag = false;

			/* Get TRULY RAW counts for Glove ML */
			if (*p_obj->p_ctsu_event == CTSU_EVENT_SCAN_COMPLETE) {
			    if (p_ctrl) err = p_ctrl->p_ctsu_instance->p_api->dataGet(p_ctrl->p_ctsu_instance->p_ctrl, p_obj->a_data_ch);
			}
			
            if (err == FSP_SUCCESS) {
                uint16_t tmp_raw[6], tmp_ref[6];
                uint32_t j;
                if (p_ctrl->binfo.p_reference) {
                    /* Remap both raw and reference data immediately at source */
                    for (j = 0; j < 6; j++) {
                        uint8_t raw_idx = g_sil_glove_chn_map[j];
                        tmp_raw[j] = p_obj->a_data_ch[raw_idx];
                        tmp_ref[j] = p_ctrl->binfo.p_reference[raw_idx];
                    }
                    memcpy(p_obj->a_data_ch, tmp_raw, sizeof(tmp_raw));
                    memcpy(p_obj->a_ref_data_ch, tmp_ref, sizeof(tmp_ref));
                }
            }
            else RM_TOUCH_ScanStop(p_obj->p_touch_config01->p_ctrl);
            
			err = -1;
		}

        if (*p_obj->p_ctsu_event == CTSU_EVENT_SCAN_COMPLETE) {
            SIL_TOUCH_StartScan(p_obj);
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

	fsp_err_t err = -1;
	sil_touch_s *p_obj = (sil_touch_s *)obj;
	uint8_t i;
	
	if (p_obj && tmr && elc && touch && flag.p_touch_flag && flag.p_ctsu_event) {
//const timer_instance_t g_timer0 =
//{ .p_ctrl = &g_timer0_ctrl, .p_cfg = &g_timer0_cfg, .p_api = &g_timer_on_agt };
		p_obj->p_timer = tmr;

//const elc_instance_t g_elc =
//{ .p_ctrl = &g_elc_ctrl, .p_api = &g_elc_on_elc, .p_cfg = &g_elc_cfg };
		p_obj->p_elc = elc;
	
//const touch_instance_t g_qe_touch_instance_config01 =
//{
//    .p_ctrl = &g_qe_touch_ctrl_config01,
//    .p_cfg  = &g_qe_touch_cfg_config01,
//    .p_api  = &g_touch_on_ctsu,
//};
		p_obj->p_touch_config01 = touch;
		//p_obj->p_touch_flag = touch_flag;
		p_obj->p_touch_flag = flag.p_touch_flag;
		p_obj->p_ctsu_event = flag.p_ctsu_event;
		*p_obj->p_ctsu_event = -1;
		p_obj->is_calibrating = 1;
		p_obj->count = 0;
		p_obj->count_rescan = 0;
		
		if (p_obj->p_elc->p_ctrl && p_obj->p_elc->p_cfg) 
			err = R_ELC_Open(p_obj->p_elc->p_ctrl, p_obj->p_elc->p_cfg);
		
		if ((err == FSP_SUCCESS) && p_obj->p_touch_config01->p_ctrl && p_obj->p_touch_config01->p_cfg) 
			err = RM_TOUCH_Open(p_obj->p_touch_config01->p_ctrl, p_obj->p_touch_config01->p_cfg);

		if ((err == FSP_SUCCESS) && p_obj->p_timer->p_ctrl && p_obj->p_timer->p_cfg) 
			err = R_AGT_Open(p_obj->p_timer->p_ctrl, p_obj->p_timer->p_cfg);

		p_obj->count_data_collect = 0;
		if (moving_points == 0) moving_points = SILCNTS_TOUCH_FILTER_MA_POINTS_DEFAULT;		
		if (collect_points == 0) collect_points = SILCNTS_TOUCH_FILTER_MDN_COLLECT_POINTS_DEFAULT;
		p_obj->data_collect_points = collect_points;
			
		for (i = 0; i < SILCNTS_GLOVE_CHS_TOTAL; i ++) {
			p_obj->a_data_ch[i] = 0;
			p_obj->a_ref_data_ch[i] = 0;
			p_obj->a_data_zero_max[i] = 0;

			SIL_FILTER_MA_Init(&p_obj->a_filter_ma[i], moving_points);

			p_obj->pa_data_collect[i] = (uint16_t *) malloc(sizeof(uint16_t) * collect_points);
			p_obj->a_data_ch_last[i] = (uint16_t) -1;
	
			memset(p_obj->pa_data_collect[i], 0, sizeof(uint16_t) * collect_points);
		}
	}

	return err;
}

fsp_err_t SIL_TOUCH_Enter2(sil_touch_s *obj) {
	
	fsp_err_t err = -1;
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
		
		if ((err == FSP_SUCCESS) && p_obj->p_touch_config01 && p_obj->p_touch_config01->p_ctrl) {
			p_obj->count_reboot = 0;
			p_obj->count = 0;
			
			err = RM_TOUCH_ScanStart(p_obj->p_touch_config01->p_ctrl);
			if (err == FSP_SUCCESS) p_obj->count_rescan = 0;
		}

		if ((err == FSP_SUCCESS) && p_obj->p_timer && p_obj->p_timer->p_ctrl)
		    err = R_AGT_Start(p_obj->p_timer->p_ctrl);
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

fsp_err_t SIL_TOUCH_Exit(sil_touch_s *obj) {

	sil_touch_s *p_obj = obj;
	fsp_err_t err = FSP_SUCCESS;

	if (p_obj) {
		R_ELC_Disable(p_obj->p_elc->p_ctrl);
		R_AGT_Stop(p_obj->p_timer->p_ctrl);
		RM_TOUCH_ScanStop(p_obj->p_touch_config01->p_ctrl);

		R_ELC_Close(p_obj->p_elc->p_ctrl);
		R_AGT_Close(p_obj->p_timer->p_ctrl);
		RM_TOUCH_Close(p_obj->p_touch_config01->p_ctrl);


	}
	return err;
}


