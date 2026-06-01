#ifndef SIL_APP_TYPE_H
#define SIL_APP_TYPE_H


/*
#if defined(__ICCARM__)

void R_BSP_WarmStart(bsp_warm_start_event_t event);

 #pragma weak R_BSP_WarmStart

#elif defined(__GNUC__) || defined(__ARMCC_VERSION)

void R_BSP_WarmStart(bsp_warm_start_event_t event) __attribute__((weak));

#endif
// */

typedef enum SIL_APP_TYPE_E {
	SIL_APP_UNKNOWN_E = -1,
	SIL_APP_USJ_E = 0,		// Ultra Slow Jogging
	SIL_APP_JRC_E = 1,		// Jump Rope Count
	SIL_APP_FP_E,				// Force Plate

	SIL_APP_FINAL_E,
	SIL_APP_MAXS_E = (SIL_APP_FINAL_E + 2)

} sil_app_type_e;

































#endif //#ifndef SIL_APP_RTC_H
