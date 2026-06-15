#ifndef SIL_APP_TINYOL_H
#define SIL_APP_TINYOL_H

#include "..\globals\sil_globals.h"

#define TINYOL_RECORD_MAX_SLOTS 3U
#define TINYOL_RECORD_MAX_SAMPLES 150U
#define TINYOL_RECORD_CHS 6U

typedef enum SIL_APP_TINYOL_STS_E {
    SIL_APP_TINYOL_STS_IDLE = 0,
    SIL_APP_TINYOL_STS_SEND_LABEL_TABLE,
    SIL_APP_TINYOL_STS_WAIT_PC_ACK,
    SIL_APP_TINYOL_STS_READY,
    SIL_APP_TINYOL_STS_NOTIFY_BASE,
    SIL_APP_TINYOL_STS_CALIB_BASE,
    SIL_APP_TINYOL_STS_NOTIFY_HOLD,
    SIL_APP_TINYOL_STS_CALIB_HOLD,
    SIL_APP_TINYOL_STS_NOTIFY_DONE,
    SIL_APP_TINYOL_STS_DONE,
} sil_app_tinyol_sts_e;

typedef struct SIL_APP_TINYOL_S {
    sil_app_tinyol_sts_e state;
    uint16_t target_label;
    uint16_t class_count;
    uint16_t epochs;
    uint16_t capture_count;
    uint16_t record_samples;
    uint16_t window_start_offset;
    uint16_t batch_size;
    float learning_rate;
    uint16_t confusable_count;
    uint16_t confusable_windows;
    uint16_t anchor_windows;
    uint8_t handshake_sent;
    uint8_t recalibration_requested;
    uint8_t calibration_active;
    uint8_t recording_requested;
    uint8_t recording_active;
    uint32_t timer_cnt;
    uint32_t sample_cnt;
    uint32_t last_touch_cnt;
    uint32_t base_sum[6];
    uint16_t base_avg[6];
    uint16_t base_min[6];
    uint16_t base_max[6];
    uint32_t hold_sum[6];
    uint16_t hold_avg[6];
    uint16_t hold_min[6];
    uint16_t hold_max[6];
    uint16_t record_labels[TINYOL_RECORD_MAX_SLOTS];
    uint16_t record_raw[TINYOL_RECORD_MAX_SLOTS][TINYOL_RECORD_MAX_SAMPLES][TINYOL_RECORD_CHS];
    uint16_t record_slot_cnt;
    uint16_t record_sample_cnt;
    uint16_t record_capture_count;
} sil_app_tinyol_s;

#ifdef __cplusplus
extern "C" {
#endif

fsp_err_t SIL_APP_TINYOL_Enter1(void);
fsp_err_t SIL_APP_TINYOL_Enter2(void);
void SIL_APP_TINYOL_MainLoop1(void);
void SIL_APP_TINYOL_MainLoop2(void);
void SIL_APP_TINYOL_Exit(void);
void SIL_APP_TINYOL_SetSessionConfig(uint16_t target_label, uint16_t epochs,
                                     uint16_t capture_count,
                                     uint16_t record_samples,
                                     uint16_t window_start_offset,
                                     uint16_t batch_size,
                                     float learning_rate,
                                     uint16_t confusable_count,
                                     uint16_t confusable_windows,
                                     uint16_t anchor_windows);
void SIL_APP_TINYOL_RequestRecalibration(void);
void SIL_APP_TINYOL_RequestRecording(void);
void SIL_APP_TINYOL_StartRecording(void);
void SIL_APP_TINYOL_StopRecording(void);
uint8_t SIL_APP_TINYOL_IsCalibrationActive(void);
uint8_t SIL_APP_TINYOL_IsRecordingActive(void);
uint16_t SIL_APP_TINYOL_GetTargetLabel(void);
uint16_t SIL_APP_TINYOL_GetClassCount(void);
uint16_t SIL_APP_TINYOL_GetEpochs(void);
uint8_t SIL_APP_TINYOL_GetHandshakeSent(void);
uint8_t SIL_APP_TINYOL_GetRecalibrationRequested(void);

#ifdef __cplusplus
}
#endif

#endif
