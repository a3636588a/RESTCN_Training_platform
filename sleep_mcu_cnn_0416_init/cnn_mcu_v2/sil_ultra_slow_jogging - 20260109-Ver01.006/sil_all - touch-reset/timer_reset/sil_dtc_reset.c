#include "sil_dtc_reset.h"
#include <stdlib.h>

sil_period_reset_s gsil_period_reset;

void SIL_DTC_RESET_CountIncreasing() {
	SIL_PERIOD_RESET_CountIncreasing(&gsil_period_reset);
}

uint32_t SIL_DTC_RESET_GetMs() {
	return SIL_PERIOD_RESET_GetMs(&gsil_period_reset);
}

fsp_err_t SIL_DTC_RESET_Enter1() {
	
	fsp_err_t err = FSP_ERR_INVALID_POINTER;
	
	err = SIL_PERIOD_RESET_Enter1(&gsil_period_reset, (timer_instance_t *)&SILVAR_TMR_DTC_RX_RESET);

	return err;
}

fsp_err_t SIL_DTC_RESET_Enter2() {

	fsp_err_t err = FSP_ERR_INVALID_POINTER;
	
	err = SIL_PERIOD_RESET_Enter2(&gsil_period_reset);

	return err;
}

void SIL_DTC_RESET_MainLoop1() {



}

void SIL_DTC_RESET_MainLoop2() {



}




