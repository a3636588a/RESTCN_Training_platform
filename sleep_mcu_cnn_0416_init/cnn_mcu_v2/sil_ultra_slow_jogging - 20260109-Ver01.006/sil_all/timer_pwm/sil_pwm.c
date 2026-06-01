#include "sil_pwm.h"
#include <stdlib.h>



void SIL_PWM_SetDuty(sil_pwm_s *obj, uint8_t duty) {

	sil_pwm_s *p_obj = (sil_pwm_s *)obj;
    timer_info_t info;
    uint32_t current_period_counts;
    uint32_t duty_cycle_counts;

	if (p_obj && p_obj->p_pwm->p_ctrl) {

		if (duty > 100) duty = 100; // 0 ~ 100

		p_obj->duty = duty;

		R_GPT_InfoGet(p_obj->p_pwm->p_ctrl, &info);

		current_period_counts = info.period_counts;

		duty_cycle_counts = (uint32_t)(((uint64_t) current_period_counts * duty) / 100);

		if (p_obj->p_pwm->p_cfg->mode == TIMER_MODE_PWM) R_GPT_DutyCycleSet(p_obj->p_pwm->p_ctrl, duty_cycle_counts, GPT_IO_PIN_GTIOCA);
	}
}

void SIL_PWM_On(sil_pwm_s *obj, uint32_t ms) {
    sil_pwm_s *p_obj = (sil_pwm_s *)obj;

    //const timer_instance_t g_timer3 =
    //{ .p_ctrl = &g_timer3_ctrl, .p_cfg = &g_timer3_cfg, .p_api = &g_timer_on_gpt };
    if (p_obj) {
		if (ms < SILCNTS_PWM_BEEP_ONE_MINIMUM_TIME_MS) ms = SILCNTS_PWM_BEEP_ONE_MINIMUM_TIME_MS;
        p_obj->output_on = 1;
        p_obj->count_62500us = ((ms * 1000) + (SILCNTS_PWM_BEEP_USED_TIMER_PERIOD_US - 1)) / SILCNTS_PWM_BEEP_USED_TIMER_PERIOD_US;
        R_GPT_Start(p_obj->p_pwm->p_ctrl);

    }
}

void SIL_PWM_Off(sil_pwm_s *obj) {
    sil_pwm_s *p_obj = (sil_pwm_s *)obj;

        //const timer_instance_t g_timer3 =
    //{ .p_ctrl = &g_timer3_ctrl, .p_cfg = &g_timer3_cfg, .p_api = &g_timer_on_gpt };
        if (p_obj) {
            p_obj->output_on = 0;
            p_obj->count_62500us = 0;
            R_GPT_Stop(p_obj->p_pwm->p_ctrl);
        }
}

void SIL_PWM_TimerLoop(sil_pwm_s *obj) {
    sil_pwm_s *p_obj = (sil_pwm_s *)obj;
    int64_t cnt = 0;

    if (p_obj && p_obj->output_on) {
        cnt = p_obj->count_62500us;

        cnt --;
        if (cnt <= 0) SIL_PWM_Off(p_obj);

        p_obj->count_62500us = (uint32_t)cnt;

    }

}

fsp_err_t SIL_PWM_Enter1(sil_pwm_s *obj, timer_instance_t *tmr) {
	
	fsp_err_t err = -1;
	sil_pwm_s *p_obj = (sil_pwm_s *)obj;
	
	//const timer_instance_t g_timer3 =
//{ .p_ctrl = &g_timer3_ctrl, .p_cfg = &g_timer3_cfg, .p_api = &g_timer_on_gpt };
	if (p_obj && tmr) {

		p_obj->p_pwm = tmr;
		p_obj->output_on = 0;	// 1: output on, 0: output off
		p_obj->duty = 0;

		/* init. GPT module */
		err = R_GPT_Open(p_obj->p_pwm->p_ctrl, p_obj->p_pwm->p_cfg);
		SIL_PWM_SetDuty(p_obj, SILCNTS_PWM_DUTY_DFT);
	}

	return err;
}

fsp_err_t SIL_PWM_Enter2(sil_pwm_s *obj) {

    fsp_err_t err = -1;
    sil_pwm_s *p_obj = (sil_pwm_s *)obj;

    (void) p_obj;

    //const timer_instance_t g_timer3 =
    //{ .p_ctrl = &g_timer3_ctrl, .p_cfg = &g_timer3_cfg, .p_api = &g_timer_on_agt };



    return err;
}

void SIL_PWM_MainLoop1(sil_pwm_s *obj) {
    sil_pwm_s *p_obj = (sil_pwm_s *)obj;

    (void) p_obj;


}

void SIL_PWM_MainLoop2(sil_pwm_s *obj) {

    sil_pwm_s *p_obj = (sil_pwm_s *)obj;

    (void) p_obj;

}




