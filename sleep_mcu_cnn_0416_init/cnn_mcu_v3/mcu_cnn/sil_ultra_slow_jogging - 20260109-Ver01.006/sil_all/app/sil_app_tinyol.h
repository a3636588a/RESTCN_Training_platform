#ifndef SIL_APP_TINYOL_H
#define SIL_APP_TINYOL_H

#include "..\globals\sil_globals.h"

#define TINYOL_RECORD_MAX_SLOTS 3U
#define TINYOL_RECORD_MAX_SAMPLES 150U
#define TINYOL_RECORD_CHS 6U
#define TINYOL_ACTIVE_HEAD_FLASH_ADDR 0x000E8000U
#define TINYOL_ACTIVE_HEAD_FLASH_SIZE  0x00018000U

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
    SIL_APP_TINYOL_STS_RUN_READY,
    SIL_APP_TINYOL_STS_RUN_START,
    SIL_APP_TINYOL_STS_VAL_START,
    SIL_APP_TINYOL_STS_RESULT_READY,
    SIL_APP_TINYOL_STS_APPLY_READY,
    SIL_APP_TINYOL_STS_ROLLBACK_READY,
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
    uint8_t replay_ready;
    uint8_t replay_built;
    uint8_t run_in_progress;
    uint8_t training_done;
    uint8_t validation_in_progress;
    uint8_t validation_done;
    uint8_t result_ready;
    uint8_t validation_passed;
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
    float last_train_loss;
    float last_train_acc;
    float last_val_loss;
    float last_val_acc;
    float last_target_recall;
    float last_overall_acc;
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
fsp_err_t SIL_APP_TINYOL_BuildReplay(void);
fsp_err_t SIL_APP_TINYOL_RunTraining(void);
fsp_err_t SIL_APP_TINYOL_RunValidation(void);
void SIL_APP_TINYOL_SetRunReady(void);
void SIL_APP_TINYOL_SetValidationReady(void);
void SIL_APP_TINYOL_SetResultReady(void);
fsp_err_t SIL_APP_TINYOL_RunFlashBlockTest(void);
fsp_err_t SIL_APP_TINYOL_LoadActiveHead(void);
fsp_err_t SIL_APP_TINYOL_SelectHeadMode(uint8_t use_active_head);
fsp_err_t SIL_APP_TINYOL_SaveActiveHead(void);
fsp_err_t SIL_APP_TINYOL_EraseActiveHead(void);
fsp_err_t SIL_APP_TINYOL_RestoreDefaultHead(void);
uint8_t SIL_APP_TINYOL_GetLastFlashOpStage(void);
uint32_t SIL_APP_TINYOL_GetLastFlashOpError(void);
uint32_t SIL_APP_TINYOL_GetLastFlashTestChecksum(void);
uint8_t SIL_APP_TINYOL_IsCalibrationActive(void);
uint8_t SIL_APP_TINYOL_IsRecordingActive(void);
uint8_t SIL_APP_TINYOL_IsReplayReady(void);
uint8_t SIL_APP_TINYOL_IsReplayBuilt(void);
uint8_t SIL_APP_TINYOL_IsRunInProgress(void);
uint8_t SIL_APP_TINYOL_IsTrainingDone(void);
uint8_t SIL_APP_TINYOL_IsValidationInProgress(void);
uint8_t SIL_APP_TINYOL_IsValidationDone(void);
uint8_t SIL_APP_TINYOL_IsResultReady(void);
uint8_t SIL_APP_TINYOL_IsValidationPassed(void);
uint8_t SIL_APP_TINYOL_HasActiveHead(void);
uint8_t SIL_APP_TINYOL_IsActiveHeadEnabled(void);
uint32_t SIL_APP_TINYOL_GetSavedRecordLabel(void);
uint8_t SIL_APP_TINYOL_HasSavedRecord(void);
uint32_t SIL_APP_TINYOL_GetActiveWeightSlot(void);
uint32_t SIL_APP_TINYOL_GetActiveHeadVersion(void);
uint32_t SIL_APP_TINYOL_GetActiveHeadChecksum(void);
uint32_t SIL_APP_TINYOL_GetActiveHeadBytes(void);
uint32_t SIL_APP_TINYOL_GetActiveHeadMagic(void);
void SIL_APP_TINYOL_CopyActiveHeadDump(uint8_t *dst, uint32_t len);
uint32_t SIL_APP_TINYOL_GetLastFlashTestAddress(void);
float SIL_APP_TINYOL_GetLastTrainLoss(void);
float SIL_APP_TINYOL_GetLastTrainAcc(void);
float SIL_APP_TINYOL_GetLastValLoss(void);
float SIL_APP_TINYOL_GetLastValAcc(void);
float SIL_APP_TINYOL_GetLastTargetRecall(void);
float SIL_APP_TINYOL_GetLastOverallAcc(void);
uint16_t SIL_APP_TINYOL_GetTargetLabel(void);
uint16_t SIL_APP_TINYOL_GetClassCount(void);
uint16_t SIL_APP_TINYOL_GetEpochs(void);
uint8_t SIL_APP_TINYOL_GetHandshakeSent(void);
uint8_t SIL_APP_TINYOL_GetRecalibrationRequested(void);
const float *SIL_APP_TINYOL_GetDenseF2Weights(void);
const float *SIL_APP_TINYOL_GetDenseF2Bias(void);
const float *SIL_APP_TINYOL_GetDenseOutWeights(void);
const float *SIL_APP_TINYOL_GetDenseOutBias(void);
void SIL_APP_TINYOL_FlashCallback(flash_callback_args_t *p_args);

#ifdef __cplusplus
}
#endif

#endif
