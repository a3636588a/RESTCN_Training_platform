#include "sil_steps_cnt.h"
#include <stdlib.h>

static void SIL_STEPS_CNT_Clear(sil_steps_cnt_s *obj) {

	sil_steps_cnt_s *p_obj = obj;

	if (p_obj) {
		
		p_obj->last_val = -1;
		p_obj->count_up = 0;
		p_obj->count_down = 0;
		p_obj->dir = 0;
		p_obj->count = 0;
		p_obj->last_count = 0;

		SIL_FILTER_MA_Clear(&p_obj->ma);
		
	}
}

static bool SIL_STEPS_CNT_VerifySteps(sil_steps_cnt_s *obj, uint32_t dat) {

	sil_steps_cnt_s *p_obj = obj;
	int32_t val = (int32_t)dat;
	bool ret = false;
	
	if (p_obj) {
		
		p_obj->count ++;
		
		val = SIL_FILTER_MA_Get(&p_obj->ma, val);

		if (val > (p_obj->last_val + p_obj->thrd)) {    // val big
			// down
			if (p_obj->dir == 0) {
				p_obj->count_down = p_obj->count_down + 1;
				p_obj->dir = 1;
			}
		}
		else if (val < (p_obj->last_val - p_obj->thrd)) {   // val small
			// Up
			if (p_obj->dir == 1) {
				p_obj->count_up = p_obj->count_up + 1;
				p_obj->dir = 0;
			}
		}

/*
	char buf[64];
	snprintf(buf, 64, "%d, %d, %d\r\n", val, p_obj->last_val, p_obj->dir);
	SIL_UART_DTC_TOPC_WriteToTxBuffer((uint8_t *) buf, (uint16_t) strlen(buf));
	SIL_UART_DTC_TOBLE_WriteToTxBuffer((uint8_t *) buf, (uint16_t) strlen(buf));
// */

		//if (p_obj->count > (p_obj->last_count + 3))	{
		if (p_obj->count > (p_obj->last_count + p_obj->interval)) {
			p_obj->last_val = val;
			p_obj->last_count = p_obj->count;
		}

		ret = true;
	}
	return ret;
}

bool SIL_STEPS_CNT_Init(sil_steps_cnt_s *obj, uint16_t ma_points, int32_t thrd, int32_t interval) {
	sil_steps_cnt_s *p_obj = obj;
	
	if (p_obj) {
		if (thrd < 5) p_obj->thrd = SILCNTS_STEPS_CNT_THRD_DEFAULT;
		else p_obj->thrd = thrd;

		if (interval <= 0) p_obj->interval = SILCNTS_STEPS_CNT_INTERVAL_DEFAULT;
		else p_obj->interval = interval;

		if (ma_points == 0) p_obj->ma_points = SILCNTS_STEPS_CNT_MA_PNTS_DEFAULT;
		else p_obj->ma_points = ma_points;

		SIL_FILTER_MA_Init(&p_obj->ma, p_obj->ma_points);
		SIL_STEPS_CNT_Clear(p_obj);
		return true;
	}

	return false;
}

void SIL_STEPS_CNT_Deinit(sil_steps_cnt_s *obj) {
	sil_steps_cnt_s *p_obj = obj;
	
	if (p_obj) SIL_STEPS_CNT_Clear(p_obj);
}

void SIL_STEPS_CNT_CountSteps(sil_steps_cnt_s *obj, uint16_t *leg, uint8_t channs) {
	
	sil_steps_cnt_s *p_obj = obj;
	uint8_t i = 0;
	uint32_t sum = 0;
	
	if (p_obj) {
		for (i = 0; i < channs; i ++) {
			sum += leg[i];
		}

		SIL_STEPS_CNT_VerifySteps(p_obj, sum);
	}
	
}





