#include "sil_tick_sys.h"
#include <stdlib.h>


void SIL_TICK_SYS_Delay(sil_tick_sys_s *obj, uint32_t delay, sil_tick_sys_dly_e base) {
	sil_tick_sys_s *p_obj = (sil_tick_sys_s *)obj;
	uint64_t tick_base;
	
	if (p_obj) {
		
		switch(base) {
	    case SIL_TICK_SYS_DLY_US_10:
	        tick_base = delay;;
	        break;
		case SIL_TICK_SYS_DLY_MS_1:
		    tick_base = ((delay * 1000) / 10);
			break;
		case SIL_TICK_SYS_DLY_S_1:
		default:
			tick_base = ((delay * 1000 * 1000) / 10);
			break;
		}
		
		p_obj->ticks_remains = (int32_t) tick_base;
		
		while (p_obj->ticks_remains > 0);
	}
}

void SIL_TICK_SYS_Decrease(sil_tick_sys_s *obj) {
	sil_tick_sys_s *p_obj = (sil_tick_sys_s *)obj;
	
	if (p_obj && (p_obj->ticks_remains > 0)) p_obj->ticks_remains --;
}

// issue one interrupt per 10us
fsp_err_t SIL_TICK_SYS_Enter1(sil_tick_sys_s *obj, uint32_t *sys_clock) {
	
	fsp_err_t err = FSP_ERR_INVALID_POINTER;
	sil_tick_sys_s *p_obj = (sil_tick_sys_s *)obj;
	
	if (p_obj && sys_clock) {

		p_obj->p_sys_clock = sys_clock;
		p_obj->period =  SILCNTS_TICK_SYS_CLOCK_BASE_US_10;
		
		err = SysTick_Config(p_obj->period);

	}
	
	return err;
}

fsp_err_t SIL_TICK_SYS_Enter2(sil_tick_sys_s *obj) {

    fsp_err_t err = FSP_ERR_INVALID_POINTER;
    sil_tick_sys_s *p_obj = (sil_tick_sys_s *)obj;

	if (p_obj) err = SIL_TICK_SYS_Enter1(p_obj, p_obj->p_sys_clock);
	
	return err;
}

void SIL_TICK_SYS_MainLoop1(sil_tick_sys_s *obj) {
    sil_tick_sys_s *p_obj = (sil_tick_sys_s *)obj;

    (void) p_obj;


}

void SIL_TICK_SYS_MainLoop2(sil_tick_sys_s *obj) {

    sil_tick_sys_s *p_obj = (sil_tick_sys_s *)obj;

    (void) p_obj;

}




