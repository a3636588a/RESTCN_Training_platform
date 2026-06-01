#ifndef SIL_TICK_SYS_H
#define SIL_TICK_SYS_H

#include "..\globals\sil_globals.h"

/*
#if defined(__ICCARM__)

void R_BSP_WarmStart(bsp_warm_start_event_t event);

 #pragma weak R_BSP_WarmStart

#elif defined(__GNUC__) || defined(__ARMCC_VERSION)

void R_BSP_WarmStart(bsp_warm_start_event_t event) __attribute__((weak));

#endif
// */

#define SILCNTS_TICK_SYS_CLOCK_1_MHZ	1000000		
#define SILCNTS_TICK_SYS_CLOCK_BASE_US_10	((10 * SILVAR_CLK_SYS_CORE) / SILCNTS_TICK_SYS_CLOCK_1_MHZ)
typedef enum SIL_TICK_SYS_DLY_E {
	SIL_TICK_SYS_DLY_UNKNOWN_E = -1,
	SIL_TICK_SYS_DLY_S_1 = 0,
	SIL_TICK_SYS_DLY_MS_1 = 1,
	SIL_TICK_SYS_DLY_US_10,

	SIL_TICK_SYS_DLY_FINAL_E,
	SIL_TICK_SYS_DLY_MAXS_E = (SIL_TICK_SYS_DLY_FINAL_E + 2)

} sil_tick_sys_dly_e;

typedef struct SIL_TICK_SYS_S {

	volatile int64_t ticks_remains;
	uint32_t *p_sys_clock;
	uint32_t period;

} sil_tick_sys_s;

void SIL_TICK_SYS_Delay(sil_tick_sys_s *obj, uint32_t delay, sil_tick_sys_dly_e base);
void SIL_TICK_SYS_Decrease(sil_tick_sys_s *obj);

// sys_clock: clocks per 1 seconds
// freq: interrupt times per seconds
fsp_err_t SIL_TICK_SYS_Enter1(sil_tick_sys_s *obj, uint32_t *sys_clock);
fsp_err_t SIL_TICK_SYS_Enter2(sil_tick_sys_s *obj);
void SIL_TICK_SYS_MainLoop1(sil_tick_sys_s *obj);
void SIL_TICK_SYS_MainLoop2(sil_tick_sys_s *obj);

										



























#endif //#ifndef SIL_TICK_SYS_H
