#ifndef SIL_GLOBALS_H
#define SIL_GLOBALS_H

#include "hal_data.h"
#include "sil_globals_renesas.h"
#include "..\app\sil_app_type.h"

// APP info.
#define SILCNTS_GLOBALS_APP_FORMAT 			"%s - Firmware Version: %04d%02d%02d Ver%s.%s(%s)\r\n"
#define SILCNTS_GLOBALS_APP_NAME 			"sil_usj"
#define SILCNTS_GLOBALS_APP_RELEASE_YEAR	2026
#define SILCNTS_GLOBALS_APP_RELEASE_MONTH	1
#define SILCNTS_GLOBALS_APP_RELEASE_DAT		30
#define SILCNTS_GLOBALS_APP_MAJOR_VER		"03"
#define SILCNTS_GLOBALS_APP_MINOR_VER		"000"
#define SILCNTS_GLOBALS_APP_CPU				"RA6M5"



// main loop time
#define SILCNTS_GLOBALS_RUN_MAINLOOP1_IN_MS	2000

// using channels
#define SILCNTS_GLOBALS_CHS_RIGHT  2
#define SILCNTS_GLOBALS_CHS_LEFT  2	
#define SILCNTS_GLOVE_CHS_TOTAL   6

#define SILCNTS_GLOBALS_TOPC_N_TIMES_TOBLE 7

// force plate using channels
#define SILCNTS_GLOBALS_FP_CHS_RIGHT  2
#define SILCNTS_GLOBALS_FP_CHS_LEFT  2	

// Force reset after N minutes if there is no action. 
#define SILCNTS_GLOBALS_FORCE_RESET_AFTER_N_SECS (5 * 60)

typedef enum SIL_GLOBALS_STS_E {
	GLOBALS_STS_UNKNOWN_E = -1,
	GLOBALS_STS_ENTER1 = 0,
	GLOBALS_STS_ENTER2 = 1,
	GLOBALS_STS_MAINLOOP1,
	GLOBALS_STS_MAINLOOP2,

	GLOBALS_STS_EXIT,

	GLOBALS_STS_FINAL_E,
	GLOBALS_STS_MAXS_E = (GLOBALS_STS_FINAL_E + 2)

} sil_globals_sts_e;

extern sil_app_type_e gsil_globals_current_app;
extern const uint8_t g_sil_glove_chn_map[6];

void SIL_GLOBALS_Reboot();
void SIL_GLOBALS_SwitchApp(sil_app_type_e app);
void SIL_GLOBALS_SetBootBuzzer(uint8_t enable);
sil_app_type_e *SIL_GLOBALS_GetPointerCurrentApp();
fsp_err_t SIL_GLOBALS_Enter1(void);
fsp_err_t SIL_GLOBALS_Enter2(void);
fsp_err_t SIL_GLOBALS_MainLoop1(void);
fsp_err_t SIL_GLOBALS_MainLoop2(void);
fsp_err_t SIL_GLOBALS_Exit(void);
sil_globals_sts_e SIL_GLOBALS_GetStatus(void);






























#endif //#ifndef SIL_GLOBALS_H
