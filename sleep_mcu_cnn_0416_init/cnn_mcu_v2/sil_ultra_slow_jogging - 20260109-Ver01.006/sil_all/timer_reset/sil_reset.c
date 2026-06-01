#include "sil_reset.h"
#include <stdlib.h>

void SIL_PERIOD_RESET_CountIncreasing(sil_period_reset_s *obj) {

    sil_period_reset_s *p_obj = (sil_period_reset_s *)obj;

    if (p_obj) p_obj->count_always ++;
}

uint32_t SIL_PERIOD_RESET_GetMs(sil_period_reset_s *obj) {
	sil_period_reset_s *p_obj = (sil_period_reset_s *)obj;
	uint32_t ms = 0;
	
	if (p_obj) ms = p_obj->count_always * p_obj->ms_base;

	return ms;
}

fsp_err_t SIL_PERIOD_RESET_Enter1(sil_period_reset_s *obj, timer_instance_t *tmr) {
	
	fsp_err_t err = -1;
	sil_period_reset_s *p_obj = (sil_period_reset_s *)obj;
	agt_instance_ctrl_t *tmr_ctrl = (agt_instance_ctrl_t *)0;
	timer_cfg_t *tmr_cfg = (timer_cfg_t *)0;
	
	//const timer_instance_t g_timer1 =
	//{ .p_ctrl = &g_timer1_ctrl, .p_cfg = &g_timer1_cfg, .p_api = &g_timer_on_agt };
	
	if (p_obj && tmr) {
		p_obj->p_timer = tmr;
		if (tmr->p_ctrl) tmr_ctrl = tmr->p_ctrl;
		if (tmr->p_cfg) tmr_cfg = (timer_cfg_t *)tmr->p_cfg;
		
		if (tmr_ctrl && tmr_cfg) err = R_AGT_Open(tmr_ctrl, tmr_cfg);
		p_obj->count_always = 0;
		
		//if (tmr_cfg) p_obj->ms_base = p_obj->p_timer->p_cfg->period_counts;
		if (tmr_cfg) p_obj->ms_base = 6;
	}

	return err;
}

fsp_err_t SIL_PERIOD_RESET_Enter2(sil_period_reset_s *obj) {
	
	fsp_err_t err = -1;
	sil_period_reset_s *p_obj = (sil_period_reset_s *)obj;
	agt_instance_ctrl_t *tmr_ctrl = (agt_instance_ctrl_t *)0;
	
	//const timer_instance_t g_timer0 =
	//{ .p_ctrl = &g_timer0_ctrl, .p_cfg = &g_timer0_cfg, .p_api = &g_timer_on_agt };
	
	if (p_obj && p_obj->p_timer && p_obj->p_timer->p_ctrl) {
		tmr_ctrl = p_obj->p_timer->p_ctrl;
		err = R_AGT_Start(tmr_ctrl);
	}

	return err;
}

void SIL_PERIOD_RESET_MainLoop1() {



}

void SIL_PERIOD_RESET_MainLoop2() {



}




