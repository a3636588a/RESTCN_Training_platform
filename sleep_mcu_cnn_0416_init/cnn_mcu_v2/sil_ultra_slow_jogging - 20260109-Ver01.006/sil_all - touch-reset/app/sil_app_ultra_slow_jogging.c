#include "sil_app_ultra_slow_jogging.h"
#include <stdlib.h>
#include "..\protocol_atcmds\sil_atcmds.h"
#include "..\uart_dtc\sil_uart_dtc_topc.h"
#include "..\uart_dtc\sil_uart_dtc_toble.h"


sil_app_usj_s gsil_app_usj;

void SIL_APP_USJ_GetChannelsDataPeriod() {
	
	SIL_APP_TOUCH_GetAllChannelsData(gsil_app_usj.a_data_ch, gsil_app_usj.a_data_len);

}

static void SIL_APP_USJ_Clear(sil_app_usj_s *obj) {
	sil_app_usj_s *p_obj = obj;
	int32_t i, thrd;
	
	if (p_obj) {
		p_obj->count = 0;
		
		//if (p_obj->app == SIL_APP_USJ_E) {
			p_obj->chs_l = SILCNTS_APP_USJ_CHS_RIGHT;
			p_obj->chs_r = SILCNTS_APP_USJ_CHS_LEFT;
			SIL_STEPS_CNT_Init(&p_obj->steps_l, 0, -1, -1);
			SIL_STEPS_CNT_Init(&p_obj->steps_r, 0, -1, -1);
		//}
		//else if (p_obj->app == SIL_APP_JRC_E) {
			p_obj->chs_jumps = SILCNTS_APP_USJ_CHS_RIGHT + SILCNTS_APP_USJ_CHS_LEFT;
			thrd = SILCNTS_STEPS_CNT_JRC_THRD_DEFAULT;
			SIL_STEPS_CNT_Init(&p_obj->jumps, 0, thrd, SILCNTS_STEPS_CNT_JRC_INTERVAL_DEFAULT);
		//}

		p_obj->a_data_len = SILCNTS_APP_USJ_CHS_RIGHT + SILCNTS_APP_USJ_CHS_LEFT;
		if (p_obj->a_data_len == (uint8_t)(SILCNTS_APP_USJ_CHS_RIGHT + SILCNTS_APP_USJ_CHS_LEFT)) {
			for (i = 0; i < p_obj->a_data_len; i ++) p_obj->a_data_ch[i] = 0;
		}
	}

}

// call once per 0.0625 seconds
void SIL_APP_USJ_OutputSteps() {

    uint32_t l = 0;
    uint32_t r = 0;
    uint32_t i = 0;
    uint8_t cnt = 0;

	if (*gsil_app_usj.p_app == SIL_APP_USJ_E) {
		if (gsil_app_usj.chs_l == gsil_app_usj.chs_r) {
			gsil_app_usj.count ++;
			l = (gsil_app_usj.steps_r.count_down + gsil_app_usj.steps_r.count_up) / 2;
			r = (gsil_app_usj.steps_l.count_down + gsil_app_usj.steps_l.count_up) / 2;

			SIL_ATCMDS_SendSilusjstps(ATCMDS_IO_TOPC, gsil_app_usj.count, l, r);
			SIL_ATCMDS_SendSilusjstps(ATCMDS_IO_TOBLE, gsil_app_usj.count, l, r);
		}
	}
	else if (*gsil_app_usj.p_app == SIL_APP_JRC_E) {
		gsil_app_usj.count ++;
		l = (gsil_app_usj.jumps.count_down + gsil_app_usj.jumps.count_up) / 2;
		SIL_ATCMDS_SendSiljrc(ATCMDS_IO_TOPC, gsil_app_usj.count, l);
		SIL_ATCMDS_SendSiljrc(ATCMDS_IO_TOBLE, gsil_app_usj.count, l);
	}

	for (i = 0; i < gsil_app_usj.a_data_len; i ++) {
	    if (gsil_app_usj.a_data_ch[i] >= 70) gsil_app_usj.force_reset_count = 0;
	    else cnt ++;
	}

	if (cnt == gsil_app_usj.a_data_len) gsil_app_usj.force_reset_count ++;

}


void SIL_APP_USJ_CountSteps() {

	if (*gsil_app_usj.p_app == SIL_APP_USJ_E) {
		if (gsil_app_usj.chs_l == gsil_app_usj.chs_r) {
			SIL_STEPS_CNT_CountSteps(&gsil_app_usj.steps_r, &gsil_app_usj.a_data_ch[TOUCH_CHS_RIGHT_DWN], gsil_app_usj.chs_l);
			SIL_STEPS_CNT_CountSteps(&gsil_app_usj.steps_l, &gsil_app_usj.a_data_ch[TOUCH_CHS_LEFT_UP], gsil_app_usj.chs_r);
		}
	}
	else if (*gsil_app_usj.p_app == SIL_APP_JRC_E) {
		SIL_STEPS_CNT_CountSteps(&gsil_app_usj.jumps, &gsil_app_usj.a_data_ch[TOUCH_CHS_LEFT_UP], gsil_app_usj.chs_jumps);
	}
	
	
}

void SIL_APP_USJ_SwitchType(sil_app_type_e app) {
	
	if ((app != SIL_APP_USJ_E) && (app != SIL_APP_JRC_E)) return ;
	
	*gsil_app_usj.p_app = app;
}

fsp_err_t SIL_APP_USJ_Enter1() {
	
    fsp_err_t err = FSP_ERR_INVALID_POINTER;
    sil_app_type_e *p_app;
	timer_info_t info;
	float f_unit = 0, f_count = 0;


	gsil_app_usj.p_app = SIL_GLOBALS_GetPointerCurrentApp();
	p_app = gsil_app_usj.p_app;
	if ((*p_app != SIL_APP_USJ_E) && (*p_app != SIL_APP_JRC_E)) *p_app = SIL_APP_USJ_E;

	SIL_APP_USJ_Clear(&gsil_app_usj);

	gsil_app_usj.p_timer = (timer_instance_t *)&SILVAR_TMR_STEPS_OUTPUT;
	if (gsil_app_usj.p_timer->p_ctrl && gsil_app_usj.p_timer->p_cfg)
	    err = R_GPT_Open(gsil_app_usj.p_timer->p_ctrl, gsil_app_usj.p_timer->p_cfg);

	if (err == FSP_SUCCESS) {
		err = R_GPT_InfoGet(gsil_app_usj.p_timer->p_ctrl, &info);
		f_unit = (float)((float)info.period_counts / (float)info.clock_frequency);	// period_counts
		f_count = (float)(SILCNTS_APP_USJ_FORCE_RESET_AFTER_N_SECS) / f_unit;
		
		
		gsil_app_usj.force_reset_count = 0;
		gsil_app_usj.force_reset_thrd = (uint32_t) f_count;
	}

	return err;
}

fsp_err_t SIL_APP_USJ_Enter2() {

    fsp_err_t err = FSP_ERR_INVALID_POINTER;

	SIL_APP_USJ_Clear(&gsil_app_usj);

	if (gsil_app_usj.p_timer->p_ctrl) err = R_GPT_Start(gsil_app_usj.p_timer->p_ctrl);

	return err;
}

void SIL_APP_USJ_MainLoop1() {
}

void SIL_APP_USJ_MainLoop2() {

/*
	if (gsil_app_usj.force_reset_count > gsil_app_usj.force_reset_thrd) {
	    gsil_app_usj.force_reset_count = 0;


	    SIL_GLOBALS_SetBootBuzzer(0);
	    SIL_GLOBALS_Reboot();

	    //SIL_UART_DTC_TOPC_Restart();
	    //SIL_UART_DTC_TOBLE_Restart();
	}

// */


}




