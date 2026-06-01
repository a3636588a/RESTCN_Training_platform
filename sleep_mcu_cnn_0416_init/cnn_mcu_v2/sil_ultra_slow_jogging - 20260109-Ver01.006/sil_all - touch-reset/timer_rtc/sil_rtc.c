#include "sil_rtc.h"
#include <stdlib.h>

void SIL_RTC_GetTime(sil_rtc_s *obj, rtc_time_t *time) {
	sil_rtc_s *p_obj = (sil_rtc_s *)obj;
	fsp_err_t err = FSP_ERR_INVALID_POINTER;
	rtc_time_t tm;
	
	if (p_obj && p_obj->p_rtc && p_obj->p_rtc->p_ctrl) {
	    memset(&tm, 0x00, sizeof(tm));
		err = R_RTC_CalendarTimeGet(p_obj->p_rtc->p_ctrl, &tm);
		if (err == FSP_SUCCESS) {
			p_obj->time_current = tm;
			if (time) *time = tm;
		}

		if (p_obj->count_update ++ > SILCNTS_RTC_UPDATE_THRD) {
			p_obj->count_update = 0;
			SIL_RTC_SetTime(p_obj, &tm);
		}
	}
}

void SIL_RTC_SetTime(sil_rtc_s *obj, rtc_time_t *time) {
	sil_rtc_s *p_obj = (sil_rtc_s *)obj;
	fsp_err_t err = FSP_ERR_INVALID_POINTER;
	
	if (p_obj && p_obj->p_rtc && p_obj->p_rtc->p_ctrl && time) {
		err = R_RTC_CalendarTimeSet(p_obj->p_rtc->p_ctrl, time); // set default time
		if (err == FSP_SUCCESS) {
		    __asm volatile (
		        "nop \n"
		        "nop \n"
		        "nop \n"
		        "nop \n"
		        "nop \n"
		    );
		}
	}
}

fsp_err_t SIL_RTC_Enter1(sil_rtc_s *obj, rtc_instance_t *rtc) {
	
	fsp_err_t err = FSP_ERR_INVALID_POINTER;
	sil_rtc_s *p_obj = (sil_rtc_s *)obj;
	rtc_time_t time_current;
	
	//const rtc_instance_t g_rtc0 =
	//{ .p_ctrl = &g_rtc0_ctrl, .p_cfg = &g_rtc0_cfg, .p_api = &g_rtc_on_rtc };
	if (p_obj && rtc) {
		p_obj->p_rtc = rtc;
		
		if (p_obj->p_rtc->p_ctrl && p_obj->p_rtc->p_cfg) {
			
			err = R_RTC_Open(p_obj->p_rtc->p_ctrl, p_obj->p_rtc->p_cfg);

			if (err == FSP_SUCCESS) R_RTC_ClockSourceSet(p_obj->p_rtc->p_ctrl);
			if (err == FSP_SUCCESS) R_RTC_CalendarTimeGet(p_obj->p_rtc->p_ctrl, &time_current);
			
			if (p_obj->time_current.tm_year < (SILCNTS_RTC_YEAR_DFT - 1900)) {
				p_obj->time_current.tm_sec = SILCNTS_RTC_SEC_DFT;
				p_obj->time_current.tm_min = SILCNTS_RTC_MIN_DFT;
				p_obj->time_current.tm_hour = SILCNTS_RTC_HOUR_DFT;
				p_obj->time_current.tm_mday = SILCNTS_RTC_MDAY_DFT;
				p_obj->time_current.tm_wday = SILCNTS_RTC_WDAY_DFT;
				p_obj->time_current.tm_mon = SILCNTS_RTC_MON_DFT - 1;
				p_obj->time_current.tm_year = SILCNTS_RTC_YEAR_DFT - 1900;  // 年份（如今年是2008，這裡輸入2008-1900=108）
			}
			// 這個函數至少呼叫一次以啟動RTC
			err = R_RTC_CalendarTimeSet (p_obj->p_rtc->p_ctrl, &p_obj->time_current); // set default time

		}
	}

	return err;
}

fsp_err_t SIL_RTC_Enter2(sil_rtc_s *obj) {
	
	fsp_err_t err = FSP_ERR_INVALID_POINTER;
	sil_rtc_s *p_obj = (sil_rtc_s *)obj;

	//const timer_instance_t g_timer0 =
	//{ .p_ctrl = &g_timer0_ctrl, .p_cfg = &g_timer0_cfg, .p_api = &g_timer_on_agt };
	
	if (p_obj && p_obj->p_rtc && p_obj->p_rtc->p_ctrl) {
		p_obj->count_update = 0;
		err = R_RTC_PeriodicIrqRateSet(p_obj->p_rtc->p_ctrl, RTC_PERIODIC_IRQ_SELECT_1_SECOND);
	}

	return err;
}

void SIL_RTC_MainLoop1() {



}

void SIL_RTC_MainLoop2() {



}




