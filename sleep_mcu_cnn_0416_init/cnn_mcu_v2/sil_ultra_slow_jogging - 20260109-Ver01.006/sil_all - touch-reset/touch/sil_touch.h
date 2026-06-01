#ifndef SIL_TOUCH_H
#define SIL_TOUCH_H

#include "..\globals\sil_globals.h"
#include "..\filter_ma\sil_filter_ma.h"

/*
#if defined(__ICCARM__)

void R_BSP_WarmStart(bsp_warm_start_event_t event);

 #pragma weak R_BSP_WarmStart

#elif defined(__GNUC__) || defined(__ARMCC_VERSION)

void R_BSP_WarmStart(bsp_warm_start_event_t event) __attribute__((weak));

#endif
// */


#define SILCNTS_TOUCH_FILTER_MDN_COLLECT_POINTS_DEFAULT     10
#define SILCNTS_TOUCH_FILTER_MA_POINTS_DEFAULT              14
#define SILCNTS_TOUCH_FORCE_ZERO_THRD                       75

typedef enum SIL_TOUCH_CHS_E {
	TOUCH_CHS_UNKNOWN_E = -1,	
/*
								//		-------- RA6M2 --------
								//	
	TOUCH_CHS_RIGHT_DWN = 0,	//	TS08(LEFT_UP)		TS06(RIGHT_UP)
	TOUCH_CHS_RIGHT_UP,			//	----------------	----------------
	TOUCH_CHS_LEFT_UP,			//	TS11(LEFT_DWN)		TS04(RIGHT_DWN)
	TOUCH_CHS_LEFT_DWN,			// 	----------------	----------------
								//  TSCAP -- P205
// */
								//		-------- RA6M5 --------
								//	
	TOUCH_CHS_LEFT_UP = 0,		//	TS01(LEFT_UP)		TS12(RIGHT_UP)
	TOUCH_CHS_LEFT_DWN,			//	----------------	----------------
	TOUCH_CHS_RIGHT_DWN,		//	TS05(LEFT_DWN)		TS09(RIGHT_DWN)
	TOUCH_CHS_RIGHT_UP,			// 	----------------	----------------
								//  TSCAP -- P207

	TOUCH_CHS_FINAL_E,
	TOUCH_CHS_MAXS_E = (TOUCH_CHS_FINAL_E + 2)

} sil_touch_chs_e;

typedef struct SIL_TOUCH_FLAG_S {
	volatile uint8_t *p_touch_flag;
	volatile ctsu_event_t *p_ctsu_event;

} sil_touch_flag_s;

typedef struct SIL_TOUCH_S {
//const timer_instance_t g_timer0 =
//{ .p_ctrl = &g_timer0_ctrl, .p_cfg = &g_timer0_cfg, .p_api = &g_timer_on_agt };
	timer_instance_t *p_timer;

//const elc_instance_t g_elc =
//{ .p_ctrl = &g_elc_ctrl, .p_api = &g_elc_on_elc, .p_cfg = &g_elc_cfg };
	elc_instance_t *p_elc;
	
//const touch_instance_t g_qe_touch_instance_config01 =
//{
//    .p_ctrl = &g_qe_touch_ctrl_config01,
//    .p_cfg  = &g_qe_touch_cfg_config01,
//    .p_api  = &g_touch_on_ctsu,
//};
	touch_instance_t *p_touch_config01;
	
	volatile uint8_t *p_touch_flag;
	volatile ctsu_event_t *p_ctsu_event;

	uint32_t count;
	volatile uint32_t count_watchdog;
	volatile uint32_t count_watchdog_last;
	uint8_t clear_watchdog;
	
	uint16_t a_data_ch[TOUCH_CHS_FINAL_E];
	uint16_t a_ref_data_ch[TOUCH_CHS_FINAL_E];
	uint16_t a_data_zero_max[TOUCH_CHS_FINAL_E];
	uint8_t is_calibrating;

	sil_filter_ma_s a_filter_ma[TOUCH_CHS_FINAL_E];
	
	// filter median
	uint16_t a_data_ch_last[TOUCH_CHS_FINAL_E];
	uint16_t *pa_data_collect[TOUCH_CHS_FINAL_E];
	uint32_t count_data_collect;
	uint8_t data_collect_points;


} sil_touch_s;


fsp_err_t SIL_TOUCH_StartScan(sil_touch_s *obj);
fsp_err_t SIL_TOUCH_GetChannelsData(sil_touch_s *obj);

fsp_err_t SIL_TOUCH_Enter1(
							sil_touch_s *obj, 
							timer_instance_t *tmr,
							elc_instance_t *elc,
							touch_instance_t *touch,
							//uint8_t *touch_flag,
							//ctsu_event_t *ctsu_event,
							sil_touch_flag_s flag,
							uint8_t moving_points,
							uint8_t collect_points
							);
fsp_err_t SIL_TOUCH_Enter2(sil_touch_s *obj);
void SIL_TOUCH_MainLoop1(sil_touch_s *obj);
void SIL_TOUCH_MainLoop2(sil_touch_s *obj);
fsp_err_t SIL_TOUCH_Restart(sil_touch_s *obj);
void SIL_TOUCH_Exit(sil_touch_s *obj);




























#endif //#ifndef SIL_TOUCH_H
