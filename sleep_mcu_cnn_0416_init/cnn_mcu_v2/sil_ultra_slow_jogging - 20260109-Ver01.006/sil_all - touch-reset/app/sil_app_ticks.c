#include <stdlib.h>
#include "sil_app_ticks.h"


sil_tick_sys_s gsil_app_ticks;

void SIL_APP_TICKS_Delay(uint32_t delay, sil_tick_sys_dly_e base) {
	
	SIL_TICK_SYS_Delay(&gsil_app_ticks, delay, base);
	
}

void SIL_APP_TICKS_Decrease() {
	SIL_TICK_SYS_Decrease(&gsil_app_ticks);
}

fsp_err_t SIL_APP_TICKS_Enter1() {
	
	return SIL_TICK_SYS_Enter1(&gsil_app_ticks, &SILVAR_CLK_SYS_CORE);
}

fsp_err_t SIL_APP_TICKS_Enter2() {

    fsp_err_t err = FSP_ERR_INVALID_POINTER;

	err = SIL_APP_TICKS_Enter1(&gsil_app_ticks);
	
	return err;
}

void SIL_APP_TICKS_MainLoop1() {
    


}

void SIL_APP_TICKS_MainLoop2() {


}




