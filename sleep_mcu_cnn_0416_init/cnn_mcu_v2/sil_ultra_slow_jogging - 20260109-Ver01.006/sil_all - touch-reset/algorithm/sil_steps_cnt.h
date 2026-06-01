#ifndef SIL_STEPS_CNT_H
#define SIL_STEPS_CNT_H

#include "..\globals\sil_globals.h"
#include "..\touch\sil_touch.h"

/*
#if defined(__ICCARM__)

void R_BSP_WarmStart(bsp_warm_start_event_t event);

 #pragma weak R_BSP_WarmStart

#elif defined(__GNUC__) || defined(__ARMCC_VERSION)

void R_BSP_WarmStart(bsp_warm_start_event_t event) __attribute__((weak));

#endif
// */

#include "..\filter_ma\sil_filter_ma.h"

#ifndef SILCNTS_TOUCH_FORCE_ZERO_THRD
#   define SILCNTS_STEPS_CNT_THRD_DEFAULT 80   //70
#else
#   define SILCNTS_STEPS_CNT_THRD_DEFAULT ((SILCNTS_TOUCH_FORCE_ZERO_THRD * 1100) / 1000)
#endif
#define SILCNTS_STEPS_CNT_INTERVAL_DEFAULT 5
#define SILCNTS_STEPS_CNT_MA_PNTS_DEFAULT 10

// jump rope count
#define SILCNTS_STEPS_CNT_JRC_THRD_DEFAULT ((SILCNTS_STEPS_CNT_THRD_DEFAULT * 23) / 10)
#define SILCNTS_STEPS_CNT_JRC_INTERVAL_DEFAULT 7


typedef struct SIL_STEPS_CNT_S {
	
	int32_t last_val;
	uint32_t count_up;
	uint32_t count_down;
	uint8_t dir;

	int32_t count;
	int32_t last_count;
	
	int32_t thrd;
	int32_t interval;
	
	sil_filter_ma_s ma;
	uint16_t ma_points;
} sil_steps_cnt_s;

bool SIL_STEPS_CNT_Init(sil_steps_cnt_s *obj, uint16_t ma_points, int32_t thrd, int32_t interval);
void SIL_STEPS_CNT_Deinit(sil_steps_cnt_s *obj);
void SIL_STEPS_CNT_CountSteps(sil_steps_cnt_s *obj, uint16_t *leg, uint8_t channs);































#endif //#ifndef SIL_STEPS_CNT_H
