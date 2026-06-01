#include "sil_filter_ma.h"
#include <stdlib.h>

void SIL_FILTER_MA_Init(sil_filter_ma_s *obj, uint16_t pts) {
	sil_filter_ma_s *p_obj = (sil_filter_ma_s *)obj;
	
	if (p_obj) {
		p_obj->index = (uint16_t) -1;
		p_obj->sum = 0;
		p_obj->pts = pts;
		
		p_obj->p_buf = (int32_t *)malloc(p_obj->pts * sizeof(int32_t));	
		memset(p_obj->p_buf, 0x00, p_obj->pts * sizeof(int32_t));
	}
}

void SIL_FILTER_MA_Clear(sil_filter_ma_s *obj) {
	sil_filter_ma_s *p_obj = (sil_filter_ma_s *)obj;
	
	if (p_obj) {
		
		p_obj->index = (uint16_t)-1;
		p_obj->sum = 0;
		memset(p_obj->p_buf, 0x00, p_obj->pts * sizeof(int32_t));
	}
}

int32_t SIL_FILTER_MA_Get(sil_filter_ma_s *obj, int32_t in) {
	sil_filter_ma_s *p_obj = (sil_filter_ma_s *)obj;
	int32_t out = 0;
    int32_t i = 0;
    uint16_t pts;
	
	if (p_obj) {
	
	
		if(p_obj->index == (uint16_t) -1) {
			for(i = 0; i < p_obj->pts; i++) {
				p_obj->p_buf[i] = in;
			}
			p_obj->sum = in * p_obj->pts;
			p_obj->index = 0;
		}
		else {
			p_obj->sum -= p_obj->p_buf[p_obj->index % p_obj->pts];
			p_obj->p_buf[p_obj->index % p_obj->pts] = in;
			p_obj->sum += in;
			p_obj->index++;

		}
		
		pts = p_obj->pts;
		out = p_obj->sum / pts;
	
	}
	
	return out;
}







