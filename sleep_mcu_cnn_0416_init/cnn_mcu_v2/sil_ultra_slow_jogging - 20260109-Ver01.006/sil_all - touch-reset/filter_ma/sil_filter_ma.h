#ifndef SIL_FILTER_MA_H
#define SIL_FILTER_MA_H

#include "..\globals\sil_globals.h"
#include <stdbool.h>

/*
#if defined(__ICCARM__)

void R_BSP_WarmStart(bsp_warm_start_event_t event);

 #pragma weak R_BSP_WarmStart

#elif defined(__GNUC__) || defined(__ARMCC_VERSION)

void R_BSP_WarmStart(bsp_warm_start_event_t event) __attribute__((weak));

#endif
// */

#define SILCNTS_FILTER_MA_BYTES 	128

typedef struct SIL_FILTER_MA_S {
	int32_t 	*p_buf;
	uint16_t 	pts;
	int32_t 	sum;
	uint16_t 	index;
} sil_filter_ma_s;


// public func.

// 
void SIL_FILTER_MA_Init(sil_filter_ma_s *obj, uint16_t pts);
int32_t SIL_FILTER_MA_Get(sil_filter_ma_s *obj, int32_t in);
void SIL_FILTER_MA_Clear(sil_filter_ma_s *obj);





























#endif //#ifndef SIL_FILTER_MA_H
