#ifndef SIL_APP_GLOVE_ML_H
#define SIL_APP_GLOVE_ML_H

#include "..\globals\sil_globals.h"
#include "..\app\sil_app_touch.h"

typedef enum SIL_APP_GLOVE_ML_STS_E {
    SIL_APP_GLOVE_ML_STS_WARMUP = 0,
    SIL_APP_GLOVE_ML_STS_NOTIFY_BASE,            // Send INITBASE for 10s
    SIL_APP_GLOVE_ML_STS_CALIB_BASE,
    SIL_APP_GLOVE_ML_STS_NOTIFY_HOLD,            // Send INITHOLD for 10s
    SIL_APP_GLOVE_ML_STS_CALIB_HOLD,
    SIL_APP_GLOVE_ML_STS_NOTIFY_DETECT,          // Send DETECT START for 10s
    SIL_APP_GLOVE_ML_STS_INFERENCE,
} sil_app_glove_ml_sts_e;

typedef struct SIL_APP_GLOVE_ML_S {
    sil_app_glove_ml_sts_e state;
    uint32_t timer_cnt;
    uint32_t sample_cnt;
    uint32_t blink_timer; // For non-blocking LED blink
    uint8_t  blink_cnt;   // Toggle count
    
    uint32_t base_sum[6];
    uint16_t base_avg[6];
    uint16_t base_min[6];
    uint16_t base_max[6];

    uint32_t hold_sum[6]; // Second phase (HOLD)
    uint16_t hold_avg[6];
    uint16_t hold_min[6];
    uint16_t hold_max[6];
} sil_app_glove_ml_s;


#ifdef __cplusplus
extern "C" {
#endif

fsp_err_t SIL_APP_GLOVE_ML_Enter1();
fsp_err_t SIL_APP_GLOVE_ML_Enter2();
void SIL_APP_GLOVE_ML_MainLoop1();
void SIL_APP_GLOVE_ML_MainLoop2();
void SIL_APP_GLOVE_ML_Exit();

#ifdef __cplusplus
}
#endif

#endif
