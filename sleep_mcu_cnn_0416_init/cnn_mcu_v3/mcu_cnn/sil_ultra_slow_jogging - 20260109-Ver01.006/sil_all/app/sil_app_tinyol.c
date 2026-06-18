#include "sil_app_tinyol.h"

#include "..\app\sil_app_touch.h"
#include "..\cnn_lib\cnn_model_data.h"
#include "..\cnn_lib\cnn_features_lib.h"
#include "..\cnn_lib\cnn_detect.h"
#include "..\cnn_lib\tinyol_default_windows.h"
#include "..\protocol_atcmds\sil_atcmds.h"
#include "..\uart_dtc\sil_uart_dtc_topc.h"
#include "r_flash_hp.h"
#include <math.h>
#include <stdio.h>
#include <string.h>

extern const float DENSE_F2_W[];
extern const float DENSE_F2_B[];
extern const float DENSE_OUT_W[];
extern const float DENSE_OUT_B[];
extern flash_hp_instance_ctrl_t g_flash0_ctrl;
extern const flash_cfg_t g_flash0_cfg;

static sil_app_tinyol_s g_tinyol = {0};

#define TINYOL_VALIDATE_TARGET_RECALL_MIN 0.90f
#define TINYOL_VALIDATE_OVERALL_ACC_MIN   0.90f

#define TINYOL_HEAD_MAGIC 0x4C594E54U /* TNYL */
#define TINYOL_HEAD_VERSION 20240130U
#define TINYOL_HEAD_F2_W_COUNT 8192U
#define TINYOL_HEAD_F2_B_COUNT 64U
#define TINYOL_HEAD_OUT_W_COUNT (64U * (uint32_t)CNN_OUT_DIM)
#define TINYOL_HEAD_OUT_B_COUNT ((uint32_t)CNN_OUT_DIM)
#define TINYOL_HEAD_WRITE_CHUNK_MAX 256U
#define TINYOL_FLASHTEST_BUFFER_MAX 32768U
#define TINYOL_FLASHTEST_TEXT "TINYOL_NEXT_BLOCK_TEST"

#define TINYOL_MAX_SAVED_GESTURES 16U

typedef struct {
    uint32_t label;
    uint16_t base_avg[6];
    uint16_t hold_avg[6];
    uint16_t record_raw[TINYOL_RECORD_MAX_SAMPLES][TINYOL_RECORD_CHS];
} sil_app_tinyol_saved_gesture_s;

typedef struct SIL_APP_TINYOL_HEAD_FLASH_S {
    uint32_t magic;
    uint32_t head_version;
    uint32_t active_weight_slot;
    uint32_t active_head_exists;
    uint32_t active_weight_enabled;
    uint32_t f2_w_count;
    uint32_t f2_b_count;
    uint32_t out_w_count;
    uint32_t out_b_count;
    uint32_t weight_bytes;
    uint32_t checksum;
    float dense_f2_w[TINYOL_HEAD_F2_W_COUNT];
    float dense_f2_b[TINYOL_HEAD_F2_B_COUNT];
    float dense_out_w[TINYOL_HEAD_OUT_W_COUNT];
    float dense_out_b[TINYOL_HEAD_OUT_B_COUNT];
    
    /* Golden gesture storage fields */
    uint32_t saved_gesture_count;
    sil_app_tinyol_saved_gesture_s saved_gestures[TINYOL_MAX_SAVED_GESTURES];
} sil_app_tinyol_head_flash_s;

static sil_app_tinyol_head_flash_s g_tinyol_head = {0};
static uint8_t g_tinyol_head_initialized = 0;
static uint8_t g_tinyol_head_exists = 0;
static uint8_t g_tinyol_head_enabled = 0;
static volatile uint8_t g_tinyol_flash_erase_done = 0;
static volatile uint8_t g_tinyol_flash_write_done = 0;
static volatile uint8_t g_tinyol_flash_error = 0;
static volatile uint8_t g_tinyol_flash_op_active = 0;
static uint8_t g_tinyol_last_flash_op_stage = 0;
static uint32_t g_tinyol_last_flash_op_error = 0;
static uint32_t g_tinyol_last_flash_test_checksum = 0;
static uint32_t g_tinyol_last_flash_test_addr = 0;
static float g_tinyol_grad_f2_w[TINYOL_HEAD_F2_W_COUNT];
static float g_tinyol_grad_f2_b[TINYOL_HEAD_F2_B_COUNT];
static float g_tinyol_grad_out_w[TINYOL_HEAD_OUT_W_COUNT];
static float g_tinyol_grad_out_b[TINYOL_HEAD_OUT_B_COUNT];
static uint8_t g_tinyol_flashtest_write_buf[TINYOL_FLASHTEST_BUFFER_MAX];

typedef struct {
    uint8_t is_target;   /* 0: Default Replay, 1: RAM Target, 2: Flash Golden Target */
    uint8_t label;       /* Class label */
    uint16_t sample_idx; /* Index within default windows or target slots */
} sil_train_sample_t;

#define TINYOL_MAX_TRAIN_SAMPLES 128U
static sil_train_sample_t g_train_samples[TINYOL_MAX_TRAIN_SAMPLES];
static uint16_t g_train_sample_count = 0;
static uint16_t g_train_indices[TINYOL_MAX_TRAIN_SAMPLES];

#define TINYOL_NOTIFY_BASE_TICKS 250U
#define TINYOL_CALIB_BASE_TICKS 500U
#define TINYOL_NOTIFY_HOLD_TICKS 250U
#define TINYOL_CALIB_HOLD_TICKS 500U

#ifndef TINYOL_DEFAULT_SHARED_BASE_HOLD
#define TINYOL_DEFAULT_SHARED_BASE_HOLD 0
#endif

static uint32_t SIL_APP_TINYOL_GetBlockSize(uint32_t address)
{
    if (address < 0x00010000U)
    {
        return 8192U; /* Region 0: 8KB */
    }
    else
    {
        return 32768U; /* Region 1: 32KB */
    }
}

static void SIL_APP_TINYOL_EnsureHeadInitialized(void);
static void SIL_APP_TINYOL_LoadDefaultHead(void);
static uint32_t SIL_APP_TINYOL_HeadChecksum(const sil_app_tinyol_head_flash_s *head);
static fsp_err_t SIL_APP_TINYOL_ApplyActiveHeadToFlash(void);
static fsp_err_t SIL_APP_TINYOL_ReadActiveHeadFromFlash(void);
static void SIL_APP_TINYOL_UpdateHeadStatusFlags(void);
static void SIL_APP_TINYOL_SetLastFlashOp(uint8_t stage, fsp_err_t err);
fsp_err_t SIL_APP_TINYOL_RunFlashBlockTest(void);
extern const flash_instance_t g_flash0;

static void SIL_APP_TINYOL_SendAck(const char *topic)
{
    uint16_t cs;
    uint8_t buf[128];
    uint8_t tmp[8] = {0};
    size_t len;

    memset(buf, 0, sizeof(buf));
    snprintf((char *)buf, sizeof(buf), "$ACK,%s*", topic);
    cs = SIL_ATCMDS_Checksum(buf);
    SIL_ATCMDS_ChecksumToHex((int32_t)cs, tmp, sizeof(tmp));
    len = strlen((char *)buf);
    memcpy(&buf[len], tmp, 2);
    len += 2;
    buf[len++] = '\r';
    buf[len++] = '\n';
    buf[len] = 0;

    SIL_UART_DTC_TOPC_WriteToTxBuffer(buf, (uint16_t)strlen((char *)buf));
}

static void SIL_APP_TINYOL_SendHandshake(void)
{
    SIL_ATCMDS_SendSilNotify(ATCMDS_IO_TOPC, "TINYOL,ENTER");
    SIL_ATCMDS_SendSilNotify(ATCMDS_IO_TOPC, "TINYOL,RECALIBRATE_BASE_HOLD");
    SIL_ATCMDS_SendSilTinyolLabelTable(ATCMDS_IO_TOPC, CNN_GESTURE_NAMES, CNN_OUT_DIM);
    SIL_APP_TINYOL_SendAck("TINYOL,ENTER");
}

static uint32_t SIL_APP_TINYOL_HeadChecksum(const sil_app_tinyol_head_flash_s *head)
{
    const uint8_t *bytes;
    uint32_t checksum = 0;
    uint32_t i;
    uint32_t length;

    if (!head) {
        return 0;
    }

    bytes = (const uint8_t *)&head->dense_f2_w[0];
    length = (uint32_t)(sizeof(head->dense_f2_w) + sizeof(head->dense_f2_b) +
                        sizeof(head->dense_out_w) + sizeof(head->dense_out_b) +
                        sizeof(head->saved_gesture_count) +
                        sizeof(head->saved_gestures));
    for (i = 0; i < length; i++) {
        checksum ^= bytes[i];
        checksum = (checksum << 1) | (checksum >> 31);
    }
    return checksum;
}

static void SIL_APP_TINYOL_LoadDefaultHead(void)
{
    memcpy(g_tinyol_head.dense_f2_w, DENSE_F2_W, sizeof(g_tinyol_head.dense_f2_w));
    memcpy(g_tinyol_head.dense_f2_b, DENSE_F2_B, sizeof(g_tinyol_head.dense_f2_b));
    memcpy(g_tinyol_head.dense_out_w, DENSE_OUT_W, sizeof(g_tinyol_head.dense_out_w));
    memcpy(g_tinyol_head.dense_out_b, DENSE_OUT_B, sizeof(g_tinyol_head.dense_out_b));
    g_tinyol_head.magic = TINYOL_HEAD_MAGIC;
    g_tinyol_head.head_version = TINYOL_HEAD_VERSION;
    g_tinyol_head.active_weight_slot = 0;
    g_tinyol_head.active_head_exists = 0;
    g_tinyol_head.active_weight_enabled = 0;
    g_tinyol_head.f2_w_count = TINYOL_HEAD_F2_W_COUNT;
    g_tinyol_head.f2_b_count = TINYOL_HEAD_F2_B_COUNT;
    g_tinyol_head.out_w_count = TINYOL_HEAD_OUT_W_COUNT;
    g_tinyol_head.out_b_count = TINYOL_HEAD_OUT_B_COUNT;
    g_tinyol_head.weight_bytes = (uint32_t)(sizeof(g_tinyol_head.dense_f2_w) +
                                            sizeof(g_tinyol_head.dense_f2_b) +
                                            sizeof(g_tinyol_head.dense_out_w) +
                                            sizeof(g_tinyol_head.dense_out_b));
    g_tinyol_head.saved_gesture_count = 0U;
    memset(g_tinyol_head.saved_gestures, 0, sizeof(g_tinyol_head.saved_gestures));
    g_tinyol_head.checksum = SIL_APP_TINYOL_HeadChecksum(&g_tinyol_head);
}

static void SIL_APP_TINYOL_EnsureHeadInitialized(void)
{
    if (!g_tinyol_head_initialized) {
        SIL_APP_TINYOL_LoadDefaultHead();
        g_tinyol_head_initialized = 1;
        (void)SIL_APP_TINYOL_ReadActiveHeadFromFlash();
    }
}

static void SIL_APP_TINYOL_UpdateHeadStatusFlags(void)
{
    g_tinyol_head_exists = (g_tinyol_head.active_head_exists != 0U) ? 1U : 0U;
    g_tinyol_head_enabled = (g_tinyol_head.active_weight_enabled != 0U) ? 1U : 0U;
}

static void SIL_APP_TINYOL_FillFlashTestString(uint8_t *buf, uint32_t len, uint32_t addr)
{
    if (!buf || (len == 0U)) {
        return;
    }

    memset(buf, 0xFF, len);
    (void)snprintf((char *)buf, len, "%s @0x%08lX", TINYOL_FLASHTEST_TEXT, (unsigned long)addr);
}

static void SIL_APP_TINYOL_SetLastFlashOp(uint8_t stage, fsp_err_t err)
{
    g_tinyol_last_flash_op_stage = stage;
    g_tinyol_last_flash_op_error = (uint32_t)err;
}

static void SIL_APP_TINYOL_SendFlashTestTrace(const char *phase, uint32_t addr, uint32_t len, fsp_err_t err)
{
    char msg[160];

    if (!phase) {
        phase = "UNKNOWN";
    }

    snprintf(msg, sizeof(msg), "TINYOL,FLASHTEST,%s,addr=0x%08lX,len=%lu,err=%d,FAWMON=0x%08lX,FSTATR=0x%08lX",
             phase,
             (unsigned long)addr,
             (unsigned long)len,
             (int)err,
             (unsigned long)R_FACI_HP->FAWMON,
             (unsigned long)R_FACI_HP->FSTATR);
    SIL_ATCMDS_SendSilNotify(ATCMDS_IO_TOPC, msg);
}

static void SIL_APP_TINYOL_SendFlashOpTrace(const char *phase, uint32_t addr, uint32_t len, uint32_t value)
{
    char msg[160];

    if (!phase) {
        phase = "UNKNOWN";
    }

    snprintf(msg, sizeof(msg), "TINYOL,FLASH,%s,addr=0x%08lX,len=%lu,val=%lu,FAWMON=0x%08lX,FSTATR=0x%08lX",
             phase,
             (unsigned long)addr,
             (unsigned long)len,
             (unsigned long)value,
             (unsigned long)R_FACI_HP->FAWMON,
             (unsigned long)R_FACI_HP->FSTATR);
    SIL_ATCMDS_SendSilNotify(ATCMDS_IO_TOPC, msg);
}

static const uint16_t (*SIL_APP_TINYOL_GetDefaultWindowSet(uint16_t label))[TINYOL_DEFAULT_WINDOW_LEN][TINYOL_DEFAULT_CHANNEL_COUNT]
{
    switch (label) {
    case 0: return tinyol_default_cls_0_windows;
    case 1: return tinyol_default_cls_1_windows;
    case 2: return tinyol_default_cls_2_windows;
    case 3: return tinyol_default_cls_3_windows;
    case 4: return tinyol_default_cls_4_windows;
    case 5: return tinyol_default_cls_5_windows;
    case 6: return tinyol_default_cls_6_windows;
    case 7: return tinyol_default_cls_7_windows;
    case 8: return tinyol_default_cls_8_windows;
    case 9: return tinyol_default_cls_9_windows;
    case 10: return tinyol_default_cls_10_windows;
    case 11: return tinyol_default_cls_11_windows;
    case 12: return tinyol_default_cls_12_windows;
    case 13: return tinyol_default_cls_13_windows;
    case 14: return tinyol_default_cls_14_windows;
    case 15: return tinyol_default_cls_15_windows;
    default: return tinyol_default_cls_0_windows;
    }
}

static uint16_t SIL_APP_TINYOL_GetDefaultWindowCount(uint16_t label)
{
    switch (label) {
    case 0: return (uint16_t)TINYOL_DEFAULT_CLS_0_COUNT;
    case 1: return (uint16_t)TINYOL_DEFAULT_CLS_1_COUNT;
    case 2: return (uint16_t)TINYOL_DEFAULT_CLS_2_COUNT;
    case 3: return (uint16_t)TINYOL_DEFAULT_CLS_3_COUNT;
    case 4: return (uint16_t)TINYOL_DEFAULT_CLS_4_COUNT;
    case 5: return (uint16_t)TINYOL_DEFAULT_CLS_5_COUNT;
    case 6: return (uint16_t)TINYOL_DEFAULT_CLS_6_COUNT;
    case 7: return (uint16_t)TINYOL_DEFAULT_CLS_7_COUNT;
    case 8: return (uint16_t)TINYOL_DEFAULT_CLS_8_COUNT;
    case 9: return (uint16_t)TINYOL_DEFAULT_CLS_9_COUNT;
    case 10: return (uint16_t)TINYOL_DEFAULT_CLS_10_COUNT;
    case 11: return (uint16_t)TINYOL_DEFAULT_CLS_11_COUNT;
    case 12: return (uint16_t)TINYOL_DEFAULT_CLS_12_COUNT;
    case 13: return (uint16_t)TINYOL_DEFAULT_CLS_13_COUNT;
    case 14: return (uint16_t)TINYOL_DEFAULT_CLS_14_COUNT;
    case 15: return (uint16_t)TINYOL_DEFAULT_CLS_15_COUNT;
    default: return (uint16_t)TINYOL_DEFAULT_CLS_0_COUNT;
    }
}

static const uint16_t *SIL_APP_TINYOL_GetDefaultBase(uint16_t label)
{
    switch (label) {
#if TINYOL_DEFAULT_SHARED_BASE_HOLD
    case 0: return tinyol_default_cls_0_base;
    case 1: return tinyol_default_cls_1_base;
    case 2: return tinyol_default_cls_2_base;
    case 3: return tinyol_default_cls_3_base;
    case 4: return tinyol_default_cls_4_base;
    case 5: return tinyol_default_cls_5_base;
    case 6: return tinyol_default_cls_6_base;
    case 7: return tinyol_default_cls_7_base;
    case 8: return tinyol_default_cls_8_base;
    case 9: return tinyol_default_cls_9_base;
    case 10: return tinyol_default_cls_10_base;
    case 11: return tinyol_default_cls_11_base;
    case 12: return tinyol_default_cls_12_base;
    case 13: return tinyol_default_cls_13_base;
    case 14: return tinyol_default_cls_14_base;
    case 15: return tinyol_default_cls_15_base;
    default: return tinyol_default_cls_0_base;
#else
    case 0: return tinyol_default_cls_0_base[0];
    case 1: return tinyol_default_cls_1_base[0];
    case 2: return tinyol_default_cls_2_base[0];
    case 3: return tinyol_default_cls_3_base[0];
    case 4: return tinyol_default_cls_4_base[0];
    case 5: return tinyol_default_cls_5_base[0];
    case 6: return tinyol_default_cls_6_base[0];
    case 7: return tinyol_default_cls_7_base[0];
    case 8: return tinyol_default_cls_8_base[0];
    case 9: return tinyol_default_cls_9_base[0];
    case 10: return tinyol_default_cls_10_base[0];
    case 11: return tinyol_default_cls_11_base[0];
    case 12: return tinyol_default_cls_12_base[0];
    case 13: return tinyol_default_cls_13_base[0];
    case 14: return tinyol_default_cls_14_base[0];
    case 15: return tinyol_default_cls_15_base[0];
    default: return tinyol_default_cls_0_base[0];
#endif
    }
}

static const uint16_t *SIL_APP_TINYOL_GetDefaultHold(uint16_t label)
{
    switch (label) {
#if TINYOL_DEFAULT_SHARED_BASE_HOLD
    case 0: return tinyol_default_cls_0_hold;
    case 1: return tinyol_default_cls_1_hold;
    case 2: return tinyol_default_cls_2_hold;
    case 3: return tinyol_default_cls_3_hold;
    case 4: return tinyol_default_cls_4_hold;
    case 5: return tinyol_default_cls_5_hold;
    case 6: return tinyol_default_cls_6_hold;
    case 7: return tinyol_default_cls_7_hold;
    case 8: return tinyol_default_cls_8_hold;
    case 9: return tinyol_default_cls_9_hold;
    case 10: return tinyol_default_cls_10_hold;
    case 11: return tinyol_default_cls_11_hold;
    case 12: return tinyol_default_cls_12_hold;
    case 13: return tinyol_default_cls_13_hold;
    case 14: return tinyol_default_cls_14_hold;
    case 15: return tinyol_default_cls_15_hold;
    default: return tinyol_default_cls_0_hold;
#else
    case 0: return tinyol_default_cls_0_hold[0];
    case 1: return tinyol_default_cls_1_hold[0];
    case 2: return tinyol_default_cls_2_hold[0];
    case 3: return tinyol_default_cls_3_hold[0];
    case 4: return tinyol_default_cls_4_hold[0];
    case 5: return tinyol_default_cls_5_hold[0];
    case 6: return tinyol_default_cls_6_hold[0];
    case 7: return tinyol_default_cls_7_hold[0];
    case 8: return tinyol_default_cls_8_hold[0];
    case 9: return tinyol_default_cls_9_hold[0];
    case 10: return tinyol_default_cls_10_hold[0];
    case 11: return tinyol_default_cls_11_hold[0];
    case 12: return tinyol_default_cls_12_hold[0];
    case 13: return tinyol_default_cls_13_hold[0];
    case 14: return tinyol_default_cls_14_hold[0];
    case 15: return tinyol_default_cls_15_hold[0];
    default: return tinyol_default_cls_0_hold[0];
#endif
    }
}

static bool SIL_APP_TINYOL_BuildFeatureSampleFromDefault(uint16_t label,
                                                         uint16_t sample_idx,
                                                         float *waveform,
                                                         float *variance,
                                                         float *mean);

static void SIL_APP_TINYOL_CopyRecordedWindow(uint16_t slot, uint16_t window[TINYOL_RECORD_MAX_SAMPLES][TINYOL_RECORD_CHS])
{
    uint16_t i;
    uint16_t ch;
    uint16_t start = g_tinyol.window_start_offset;
    if (start + CNN_WIN_LEN > TINYOL_RECORD_MAX_SAMPLES) {
        start = (uint16_t)(TINYOL_RECORD_MAX_SAMPLES - CNN_WIN_LEN);
    }
    if (slot >= TINYOL_RECORD_MAX_SLOTS) {
        memset(window, 0, sizeof(uint16_t) * CNN_WIN_LEN * TINYOL_RECORD_CHS);
        return;
    }
    for (i = 0; i < CNN_WIN_LEN; i++) {
        for (ch = 0; ch < TINYOL_RECORD_CHS; ch++) {
            window[i][ch] = g_tinyol.record_raw[slot][start + i][ch];
        }
    }
}

static bool SIL_APP_TINYOL_BuildFeatureSampleFromDefault(uint16_t label,
                                                         uint16_t sample_idx,
                                                         float *waveform,
                                                         float *variance,
                                                         float *mean) {
    const uint16_t (*windows)[TINYOL_DEFAULT_WINDOW_LEN][TINYOL_DEFAULT_CHANNEL_COUNT] = SIL_APP_TINYOL_GetDefaultWindowSet(label);
    const uint16_t *base = SIL_APP_TINYOL_GetDefaultBase(label);
    const uint16_t *hold = SIL_APP_TINYOL_GetDefaultHold(label);
    uint16_t window_5[CNN_WIN_LEN][CNN_CH_USED];
    uint16_t i;
    uint16_t ch;
    uint16_t window_count;

    window_count = SIL_APP_TINYOL_GetDefaultWindowCount(label);
    if (sample_idx >= window_count) {
        return false;
    }
    for (i = 0; i < CNN_WIN_LEN; i++) {
        for (ch = 0; ch < CNN_CH_USED; ch++) {
            window_5[i][ch] = windows[sample_idx][i][ch];
        }
    }
    return cnn_compute_features_from_window(window_5, base, hold, waveform, variance, mean);
}

static bool SIL_APP_TINYOL_BuildFeatureSampleFromTarget(uint16_t slot,
                                                        float *waveform,
                                                        float *variance,
                                                        float *mean) {
    uint16_t window_5[CNN_WIN_LEN][CNN_CH_USED];
    uint16_t i;
    uint16_t ch;
    uint16_t start = g_tinyol.window_start_offset;

    if (start + CNN_WIN_LEN > TINYOL_RECORD_MAX_SAMPLES) {
        start = (uint16_t)(TINYOL_RECORD_MAX_SAMPLES - CNN_WIN_LEN);
    }
    if (slot >= g_tinyol.record_capture_count) {
        return false;
    }
    for (i = 0; i < CNN_WIN_LEN; i++) {
        for (ch = 0; ch < CNN_CH_USED; ch++) {
            window_5[i][ch] = g_tinyol.record_raw[slot][start + i][ch];
        }
    }
    return cnn_compute_features_from_window(window_5, g_tinyol.base_avg, g_tinyol.hold_avg, waveform, variance, mean);
}

static bool SIL_APP_TINYOL_BuildFeatureSampleFromSaved(uint32_t idx,
                                                       float *waveform,
                                                       float *variance,
                                                       float *mean) {
    uint16_t window_5[CNN_WIN_LEN][CNN_CH_USED];
    uint16_t i;
    uint16_t ch;
    uint16_t start = g_tinyol.window_start_offset;

    if (start + CNN_WIN_LEN > TINYOL_RECORD_MAX_SAMPLES) {
        start = (uint16_t)(TINYOL_RECORD_MAX_SAMPLES - CNN_WIN_LEN);
    }
    if (!g_tinyol_head_exists || idx >= g_tinyol_head.saved_gesture_count) {
        return false;
    }
    for (i = 0; i < CNN_WIN_LEN; i++) {
        for (ch = 0; ch < CNN_CH_USED; ch++) {
            window_5[i][ch] = g_tinyol_head.saved_gestures[idx].record_raw[start + i][ch];
        }
    }
    return cnn_compute_features_from_window(window_5, g_tinyol_head.saved_gestures[idx].base_avg, g_tinyol_head.saved_gestures[idx].hold_avg, waveform, variance, mean);
}

static void SIL_APP_TINYOL_ClearGradients(void)
{
    memset(g_tinyol_grad_f2_w, 0, sizeof(g_tinyol_grad_f2_w));
    memset(g_tinyol_grad_f2_b, 0, sizeof(g_tinyol_grad_f2_b));
    memset(g_tinyol_grad_out_w, 0, sizeof(g_tinyol_grad_out_w));
    memset(g_tinyol_grad_out_b, 0, sizeof(g_tinyol_grad_out_b));
}

static void SIL_APP_TINYOL_ApplyGradients(uint16_t batch_count)
{
    float scale;
    uint32_t i;

    if (batch_count == 0U) {
        return;
    }
    scale = g_tinyol.learning_rate / (float)batch_count;
    for (i = 0; i < TINYOL_HEAD_F2_W_COUNT; i++) {
        g_tinyol_head.dense_f2_w[i] -= scale * g_tinyol_grad_f2_w[i];
        g_tinyol_grad_f2_w[i] = 0.0f;
    }
    for (i = 0; i < TINYOL_HEAD_F2_B_COUNT; i++) {
        g_tinyol_head.dense_f2_b[i] -= scale * g_tinyol_grad_f2_b[i];
        g_tinyol_grad_f2_b[i] = 0.0f;
    }
    for (i = 0; i < TINYOL_HEAD_OUT_W_COUNT; i++) {
        g_tinyol_head.dense_out_w[i] -= scale * g_tinyol_grad_out_w[i];
        g_tinyol_grad_out_w[i] = 0.0f;
    }
    for (i = 0; i < TINYOL_HEAD_OUT_B_COUNT; i++) {
        g_tinyol_head.dense_out_b[i] -= scale * g_tinyol_grad_out_b[i];
        g_tinyol_grad_out_b[i] = 0.0f;
    }
}

static void SIL_APP_TINYOL_AccumulateSampleGradients(const cnn_detect_cache_t *cache,
                                                     uint16_t label)
{
    float dz3[CNN_OUT_DIM];
    float da2[64];
    float dz2[64];
    float prob = cache->proba[label];
    uint32_t i;
    uint32_t j;
    uint32_t k;

    if (prob < 1.0e-6f) {
        prob = 1.0e-6f;
    }

    for (k = 0; k < CNN_OUT_DIM; k++) {
        dz3[k] = cache->proba[k] - ((k == label) ? 1.0f : 0.0f);
        g_tinyol_grad_out_b[k] += dz3[k];
    }

    for (j = 0; j < 64U; j++) {
        float sum = 0.0f;
        for (k = 0; k < CNN_OUT_DIM; k++) {
            sum += dz3[k] * g_tinyol_head.dense_out_w[j * CNN_OUT_DIM + k];
            g_tinyol_grad_out_w[j * CNN_OUT_DIM + k] += cache->f2_out[j] * dz3[k];
        }
        da2[j] = sum;
        dz2[j] = (cache->f2_z[j] > 0.0f) ? da2[j] : (da2[j] * 0.1f);
        g_tinyol_grad_f2_b[j] += dz2[j];
    }

    for (i = 0; i < 128U; i++) {
        for (j = 0; j < 64U; j++) {
            g_tinyol_grad_f2_w[i * 64U + j] += cache->f1_out[i] * dz2[j];
        }
    }
}

static void SIL_APP_TINYOL_ShuffleIndices(uint16_t *indices, uint16_t count)
{
    if (count <= 1U) {
        return;
    }
    static uint32_t rand_state = 123456789U;
    if (rand_state == 123456789U) {
        rand_state += g_tinyol.timer_cnt + gsil_app_touch.sensor.count;
    }
    
    for (uint16_t i = (uint16_t)(count - 1U); i > 0U; i--) {
        rand_state = rand_state * 1103515245U + 12345U;
        uint16_t j = (uint16_t)((rand_state / 65536U) % (i + 1U));
        uint16_t temp = indices[i];
        indices[i] = indices[j];
        indices[j] = temp;
    }
}

static void SIL_APP_TINYOL_AccumulateSampleGradientsCustom(const cnn_detect_cache_t *cache,
                                                           const float dz3[CNN_OUT_DIM])
{
    float da2[64];
    float dz2[64];
    uint32_t i;
    uint32_t j;
    uint32_t k;

    for (k = 0; k < CNN_OUT_DIM; k++) {
        g_tinyol_grad_out_b[k] += dz3[k];
    }

    for (j = 0; j < 64U; j++) {
        float sum = 0.0f;
        for (k = 0; k < CNN_OUT_DIM; k++) {
            sum += dz3[k] * g_tinyol_head.dense_out_w[j * CNN_OUT_DIM + k];
            g_tinyol_grad_out_w[j * CNN_OUT_DIM + k] += cache->f2_out[j] * dz3[k];
        }
        da2[j] = sum;
        dz2[j] = (cache->f2_z[j] > 0.0f) ? da2[j] : (da2[j] * 0.1f);
        g_tinyol_grad_f2_b[j] += dz2[j];
    }

    for (i = 0; i < 128U; i++) {
        for (j = 0; j < 64U; j++) {
            g_tinyol_grad_f2_w[i * 64U + j] += cache->f1_out[i] * dz2[j];
        }
    }
}

void SIL_APP_TINYOL_FlashCallback(flash_callback_args_t *p_args)
{
    if (!p_args) {
        return;
    }
    if (g_tinyol_flash_op_active == 0U) {
        return;
    }

    switch (p_args->event) {
    case FLASH_EVENT_ERASE_COMPLETE:
        g_tinyol_flash_erase_done = 1U;
        SIL_APP_TINYOL_SetLastFlashOp(5U, FSP_SUCCESS);
        break;
    case FLASH_EVENT_WRITE_COMPLETE:
        g_tinyol_flash_write_done = 1U;
        SIL_APP_TINYOL_SetLastFlashOp(6U, FSP_SUCCESS);
        break;
    case FLASH_EVENT_BLANK:
    case FLASH_EVENT_NOT_BLANK:
        break;
    default:
        g_tinyol_flash_error = 1U;
        SIL_APP_TINYOL_SetLastFlashOp(7U, (fsp_err_t)p_args->event);
        break;
    }
}

static fsp_err_t SIL_APP_TINYOL_ReadActiveHeadFromFlash(void)
{
    const sil_app_tinyol_head_flash_s *stored;
    uint32_t checksum;

    stored = (const sil_app_tinyol_head_flash_s *)(uintptr_t)TINYOL_ACTIVE_HEAD_FLASH_ADDR;

    if ((stored->magic != TINYOL_HEAD_MAGIC) ||
        (stored->head_version != TINYOL_HEAD_VERSION) ||
        (stored->f2_w_count != TINYOL_HEAD_F2_W_COUNT) ||
        (stored->f2_b_count != TINYOL_HEAD_F2_B_COUNT) ||
        (stored->out_w_count != TINYOL_HEAD_OUT_W_COUNT) ||
        (stored->out_b_count != TINYOL_HEAD_OUT_B_COUNT) ||
        (stored->weight_bytes != (uint32_t)(sizeof(stored->dense_f2_w) +
                                            sizeof(stored->dense_f2_b) +
                                            sizeof(stored->dense_out_w) +
                                            sizeof(stored->dense_out_b)))) {
        g_tinyol_head.active_head_exists = 0U;
        g_tinyol_head.active_weight_enabled = 0U;
        SIL_APP_TINYOL_UpdateHeadStatusFlags();
        return FSP_ERR_INVALID_DATA;
    }

    checksum = SIL_APP_TINYOL_HeadChecksum(stored);
    if (checksum != stored->checksum) {
        g_tinyol_head.active_head_exists = 0U;
        g_tinyol_head.active_weight_enabled = 0U;
        SIL_APP_TINYOL_UpdateHeadStatusFlags();
        return FSP_ERR_INVALID_DATA;
    }

    memcpy(&g_tinyol_head, stored, sizeof(g_tinyol_head));
    g_tinyol_head.active_head_exists = 1U;
    g_tinyol_head.active_weight_enabled = 1U;
    SIL_APP_TINYOL_UpdateHeadStatusFlags();
    return FSP_SUCCESS;
}

static void SIL_APP_TINYOL_ResetFlashWaitFlags(void)
{
    g_tinyol_flash_erase_done = 0U;
    g_tinyol_flash_write_done = 0U;
    g_tinyol_flash_error = 0U;
}

static fsp_err_t SIL_APP_TINYOL_WaitForFlashDone(volatile uint8_t *flag)
{
    uint32_t timeout = 1000U;

    while ((flag && (*flag == 0U)) && (g_tinyol_flash_error == 0U) && (timeout > 0U)) {
        R_BSP_SoftwareDelay(1, BSP_DELAY_UNITS_MILLISECONDS);
        timeout--;
    }

    if (g_tinyol_flash_error != 0U) {
        return FSP_ERR_ABORTED;
    }
    if ((flag != NULL) && (*flag == 0U)) {
        return FSP_ERR_ABORTED;
    }
    return FSP_SUCCESS;
}

static fsp_err_t SIL_APP_TINYOL_ApplyActiveHeadToFlash(void)
{
    flash_info_t flash_info = {0};
    uint32_t block_size;
    uint32_t erase_blocks;
    uint32_t offset;
    uint8_t chunk[TINYOL_HEAD_WRITE_CHUNK_MAX] = {0xFF};
    const uint8_t *src;
    uint32_t total_bytes;
    uint32_t write_block_size;
    fsp_err_t err;

    SIL_APP_TINYOL_EnsureHeadInitialized();
    if (sizeof(g_tinyol_head) > TINYOL_ACTIVE_HEAD_FLASH_SIZE) {
        SIL_APP_TINYOL_SetLastFlashOp(0U, FSP_ERR_INVALID_DATA);
        return FSP_ERR_INVALID_DATA;
    }
    g_tinyol_flash_op_active = 1U;
    g_tinyol_head.checksum = SIL_APP_TINYOL_HeadChecksum(&g_tinyol_head);
    g_tinyol_head.active_head_exists = 1U;
    g_tinyol_head.active_weight_enabled = 1U;
    SIL_APP_TINYOL_UpdateHeadStatusFlags();

    /* Unlock flash HP registers */
    (*(volatile uint32_t *)0x400C4800) |= (1U << 10);

    err = g_flash0.p_api->open(g_flash0.p_ctrl, g_flash0.p_cfg);
    if (err != FSP_SUCCESS) {
        SIL_APP_TINYOL_SetLastFlashOp(1U, err);
        g_tinyol_flash_op_active = 0U;
        return err;
    }
    err = g_flash0.p_api->infoGet(g_flash0.p_ctrl, &flash_info);
    if (err != FSP_SUCCESS) {
        SIL_APP_TINYOL_SetLastFlashOp(2U, err);
        g_flash0.p_api->close(g_flash0.p_ctrl);
        g_tinyol_flash_op_active = 0U;
        return err;
    }
    if ((flash_info.code_flash.num_regions == 0U) || (flash_info.code_flash.p_block_array == NULL)) {
        SIL_APP_TINYOL_SetLastFlashOp(2U, FSP_ERR_INVALID_DATA);
        g_flash0.p_api->close(g_flash0.p_ctrl);
        g_tinyol_flash_op_active = 0U;
        return FSP_ERR_INVALID_DATA;
    }

    block_size = SIL_APP_TINYOL_GetBlockSize(TINYOL_ACTIVE_HEAD_FLASH_ADDR);
    write_block_size = flash_info.code_flash.p_block_array->block_size_write;
    if ((write_block_size == 0U) || (write_block_size > TINYOL_HEAD_WRITE_CHUNK_MAX)) {
        g_flash0.p_api->close(g_flash0.p_ctrl);
        g_tinyol_flash_op_active = 0U;
        return FSP_ERR_INVALID_DATA;
    }
    erase_blocks = (TINYOL_ACTIVE_HEAD_FLASH_SIZE + block_size - 1U) / block_size;
    SIL_APP_TINYOL_SendFlashOpTrace("APPLY_ERASE_START", TINYOL_ACTIVE_HEAD_FLASH_ADDR, erase_blocks, 0U);
    SIL_APP_TINYOL_ResetFlashWaitFlags();
    __disable_irq();
    err = g_flash0.p_api->erase(g_flash0.p_ctrl, TINYOL_ACTIVE_HEAD_FLASH_ADDR, erase_blocks);
    __enable_irq();
    if (err != FSP_SUCCESS) {
        SIL_APP_TINYOL_SetLastFlashOp(3U, err);
        g_flash0.p_api->close(g_flash0.p_ctrl);
        g_tinyol_flash_op_active = 0U;
        SIL_APP_TINYOL_SendFlashOpTrace("APPLY_ERASE_FAIL", TINYOL_ACTIVE_HEAD_FLASH_ADDR, erase_blocks, (uint32_t)err);
        return err;
    }
    /* Code Flash erase is synchronous, no need to wait for callback */
    SIL_APP_TINYOL_SendFlashOpTrace("APPLY_ERASE_OK", TINYOL_ACTIVE_HEAD_FLASH_ADDR, erase_blocks, 0U);

    src = (const uint8_t *)&g_tinyol_head;
    total_bytes = (uint32_t)sizeof(g_tinyol_head);
    for (offset = 0; offset < TINYOL_ACTIVE_HEAD_FLASH_SIZE; offset += write_block_size) {
        uint32_t copy_bytes = 0U;
        uint32_t write_addr = TINYOL_ACTIVE_HEAD_FLASH_ADDR + offset;

        memset(chunk, 0xFF, sizeof(chunk));
        if (offset < total_bytes) {
            copy_bytes = total_bytes - offset;
            if (copy_bytes > write_block_size) {
                copy_bytes = write_block_size;
            }
            memcpy(chunk, &src[offset], copy_bytes);
        }
        if ((offset % 4096U) == 0U) {
            SIL_APP_TINYOL_SendFlashOpTrace("APPLY_WRITE_START", write_addr, write_block_size, copy_bytes);
        }
        g_tinyol_flash_write_done = 0U;
        __disable_irq();
        err = g_flash0.p_api->write(g_flash0.p_ctrl, (uint32_t)chunk, write_addr, write_block_size);
        __enable_irq();
        if (err != FSP_SUCCESS) {
            SIL_APP_TINYOL_SetLastFlashOp(4U, err);
            g_flash0.p_api->close(g_flash0.p_ctrl);
            g_tinyol_flash_op_active = 0U;
            SIL_APP_TINYOL_SendFlashOpTrace("APPLY_WRITE_FAIL", write_addr, write_block_size, (uint32_t)err);
            return err;
        }
        /* Code Flash write is synchronous, no need to wait for callback */
        if (offset == 0U) {
            SIL_APP_TINYOL_SendFlashOpTrace("APPLY_WRITE_OK", write_addr, write_block_size, (uint32_t)chunk[0]);
        }
    }

    SIL_APP_TINYOL_SendFlashOpTrace("APPLY_VERIFY_OK", TINYOL_ACTIVE_HEAD_FLASH_ADDR, total_bytes,
                                     SIL_APP_TINYOL_HeadChecksum(&g_tinyol_head));
    g_flash0.p_api->close(g_flash0.p_ctrl);
    g_tinyol_flash_op_active = 0U;
    SIL_APP_TINYOL_SetLastFlashOp(0U, FSP_SUCCESS);
    return FSP_SUCCESS;
}

static void SIL_APP_TINYOL_InitCalibBuffers(void)
{
    uint32_t i;

    g_tinyol.sample_cnt = 0;
    g_tinyol.last_touch_cnt = 0;
    for (i = 0; i < 6; i++) {
        g_tinyol.base_sum[i] = 0;
        g_tinyol.hold_sum[i] = 0;
        g_tinyol.base_min[i] = 0xFFFF;
        g_tinyol.base_max[i] = 0;
        g_tinyol.hold_min[i] = 0xFFFF;
        g_tinyol.hold_max[i] = 0;
        g_tinyol.base_avg[i] = 0;
        g_tinyol.hold_avg[i] = 0;
    }
}

static void SIL_APP_TINYOL_ResetRecordingBuffers(void)
{
    uint32_t slot;
    uint32_t sample;
    uint32_t ch;

    g_tinyol.record_slot_cnt = 0;
    g_tinyol.record_sample_cnt = 0;
    g_tinyol.record_capture_count = 0;
    for (slot = 0; slot < TINYOL_RECORD_MAX_SLOTS; slot++) {
        g_tinyol.record_labels[slot] = 0;
        for (sample = 0; sample < TINYOL_RECORD_MAX_SAMPLES; sample++) {
            for (ch = 0; ch < TINYOL_RECORD_CHS; ch++) {
                g_tinyol.record_raw[slot][sample][ch] = 0;
            }
        }
    }
}

fsp_err_t SIL_APP_TINYOL_Enter1(void)
{
    g_tinyol.state = SIL_APP_TINYOL_STS_IDLE;
    g_tinyol.target_label = 0;
    g_tinyol.class_count = CNN_OUT_DIM;
    g_tinyol.epochs = 50;
    g_tinyol.capture_count = 3;
    g_tinyol.record_samples = 150;
    g_tinyol.window_start_offset = 30;
    g_tinyol.batch_size = 4;
    g_tinyol.learning_rate = 0.0005f;
    g_tinyol.confusable_count = 3;
    g_tinyol.confusable_windows = 8;
    g_tinyol.anchor_windows = 3;
    g_tinyol.handshake_sent = 0;
    g_tinyol.recalibration_requested = 0;
    g_tinyol.calibration_active = 0;
    g_tinyol.recording_requested = 0;
    g_tinyol.recording_active = 0;
    g_tinyol.replay_ready = 0;
    g_tinyol.replay_built = 0;
    g_tinyol.run_in_progress = 0;
    g_tinyol.training_done = 0;
    g_tinyol.validation_in_progress = 0;
    g_tinyol.validation_done = 0;
    g_tinyol.result_ready = 0;
    g_tinyol.validation_passed = 0;
    g_tinyol.last_train_loss = 0.0f;
    g_tinyol.last_train_acc = 0.0f;
    g_tinyol.last_val_loss = 0.0f;
    g_tinyol.last_val_acc = 0.0f;
    g_tinyol.last_target_recall = 0.0f;
    g_tinyol.last_overall_acc = 0.0f;
    g_tinyol.timer_cnt = 0;
    (void)SIL_APP_TINYOL_LoadActiveHead();
    SIL_APP_TINYOL_InitCalibBuffers();
    SIL_APP_TINYOL_ResetRecordingBuffers();
    return FSP_SUCCESS;
}

fsp_err_t SIL_APP_TINYOL_Enter2(void)
{
    if (!g_tinyol.handshake_sent) {
        SIL_APP_TINYOL_SendHandshake();
        g_tinyol.handshake_sent = 1;
    }
    g_tinyol.state = SIL_APP_TINYOL_STS_READY;



    return FSP_SUCCESS;
}

void SIL_APP_TINYOL_MainLoop1(void)
{
    uint16_t sensor_raw[6] = {0};
    uint32_t i;
    uint32_t current_touch_cnt;

    if (g_tinyol.state == SIL_APP_TINYOL_STS_IDLE) {
        g_tinyol.state = SIL_APP_TINYOL_STS_SEND_LABEL_TABLE;
        return;
    }

    if (g_tinyol.state == SIL_APP_TINYOL_STS_SEND_LABEL_TABLE) {
        g_tinyol.state = SIL_APP_TINYOL_STS_WAIT_PC_ACK;
        return;
    }

    if (!g_tinyol.calibration_active) {
        if (!g_tinyol.recording_active) {
            return;
        }
    }

    current_touch_cnt = gsil_app_touch.sensor.count;

    if (current_touch_cnt <= g_tinyol.last_touch_cnt) {
        return;
    }

    g_tinyol.last_touch_cnt = current_touch_cnt;
    SIL_APP_TOUCH_GetAllChannelsDataGlove(sensor_raw, 6);

    if (g_tinyol.recording_active) {
        uint16_t sample_limit = g_tinyol.record_samples;
        uint32_t ch_idx;
        uint16_t remaining;

        if (sample_limit == 0) {
            sample_limit = TINYOL_RECORD_MAX_SAMPLES;
        }
        if (sample_limit > TINYOL_RECORD_MAX_SAMPLES) {
            sample_limit = TINYOL_RECORD_MAX_SAMPLES;
        }

        if (g_tinyol.record_slot_cnt >= g_tinyol.capture_count ||
            g_tinyol.record_slot_cnt >= TINYOL_RECORD_MAX_SLOTS) {
            g_tinyol.recording_active = 0;
            g_tinyol.recording_requested = 0;
            return;
        }

        if (g_tinyol.record_sample_cnt == 0) {
            g_tinyol.record_labels[g_tinyol.record_slot_cnt] = g_tinyol.target_label;
        }

        for (ch_idx = 0; ch_idx < TINYOL_RECORD_CHS; ch_idx++) {
            g_tinyol.record_raw[g_tinyol.record_slot_cnt][g_tinyol.record_sample_cnt][ch_idx] = sensor_raw[ch_idx];
        }
        g_tinyol.record_sample_cnt++;

        if (g_tinyol.record_sample_cnt >= sample_limit) {
            g_tinyol.record_slot_cnt++;
            g_tinyol.record_capture_count = g_tinyol.record_slot_cnt;
            g_tinyol.record_sample_cnt = 0;

            remaining = (g_tinyol.capture_count > g_tinyol.record_slot_cnt)
                            ? (uint16_t)(g_tinyol.capture_count - g_tinyol.record_slot_cnt)
                            : 0;
            {
                char msg[80];
                snprintf(msg, sizeof(msg), "TINYOL,REC_DONE,%u,%u,%u",
                         (unsigned int)g_tinyol.target_label,
                         (unsigned int)g_tinyol.record_slot_cnt,
                         (unsigned int)remaining);
                SIL_ATCMDS_SendSilNotify(ATCMDS_IO_TOPC, msg);
            }

            if (remaining == 0 || g_tinyol.record_slot_cnt >= TINYOL_RECORD_MAX_SLOTS) {
                g_tinyol.recording_active = 0;
                g_tinyol.recording_requested = 0;
                g_tinyol.replay_ready = 0U;
                g_tinyol.replay_built = 0U;
                g_tinyol.training_done = 0U;
                g_tinyol.validation_done = 0U;
                g_tinyol.result_ready = 0U;
                g_tinyol.state = SIL_APP_TINYOL_STS_DONE;
                SIL_ATCMDS_SendSilNotify(ATCMDS_IO_TOPC, "TINYOL,REC_ALL_DONE");
            }
        }
        return;
    }

    switch (g_tinyol.state) {
    case SIL_APP_TINYOL_STS_NOTIFY_BASE:
        SIL_ATCMDS_SendSilNotify(ATCMDS_IO_TOPC, "TINYOL,INITBASE");
        if (++g_tinyol.timer_cnt >= TINYOL_NOTIFY_BASE_TICKS) {
            g_tinyol.state = SIL_APP_TINYOL_STS_CALIB_BASE;
            g_tinyol.timer_cnt = 0;
            g_tinyol.sample_cnt = 0;
            for (i = 0; i < 6; i++) {
                g_tinyol.base_sum[i] = 0;
                g_tinyol.base_min[i] = 0xFFFF;
                g_tinyol.base_max[i] = 0;
            }
        }
        break;

    case SIL_APP_TINYOL_STS_CALIB_BASE: {
        uint8_t base_valid = 0;
        for (i = 0; i < 6; i++) {
            if (sensor_raw[i] > 0) {
                base_valid = 1;
                break;
            }
        }
        if (base_valid) {
            for (i = 0; i < 6; i++) {
                g_tinyol.base_sum[i] += sensor_raw[i];
                if (sensor_raw[i] < g_tinyol.base_min[i]) g_tinyol.base_min[i] = sensor_raw[i];
                if (sensor_raw[i] > g_tinyol.base_max[i]) g_tinyol.base_max[i] = sensor_raw[i];
            }
            g_tinyol.sample_cnt++;
        }
        if (g_tinyol.sample_cnt >= TINYOL_CALIB_BASE_TICKS) {
            for (i = 0; i < 6; i++) {
                g_tinyol.base_avg[i] = (uint16_t)(g_tinyol.base_sum[i] / g_tinyol.sample_cnt);
            }
            SIL_ATCMDS_SendSilBaseExt(ATCMDS_IO_TOPC, g_tinyol.sample_cnt,
                                      g_tinyol.base_avg, g_tinyol.base_min,
                                      g_tinyol.base_max, 6);
            g_tinyol.state = SIL_APP_TINYOL_STS_NOTIFY_HOLD;
            g_tinyol.timer_cnt = 0;
        }
        break;
    }

    case SIL_APP_TINYOL_STS_NOTIFY_HOLD:
        SIL_ATCMDS_SendSilNotify(ATCMDS_IO_TOPC, "TINYOL,INITHOLD");
        if (++g_tinyol.timer_cnt >= TINYOL_NOTIFY_HOLD_TICKS) {
            g_tinyol.state = SIL_APP_TINYOL_STS_CALIB_HOLD;
            g_tinyol.timer_cnt = 0;
            g_tinyol.sample_cnt = 0;
            for (i = 0; i < 6; i++) {
                g_tinyol.hold_sum[i] = 0;
                g_tinyol.hold_min[i] = 0xFFFF;
                g_tinyol.hold_max[i] = 0;
            }
        }
        break;

    case SIL_APP_TINYOL_STS_CALIB_HOLD: {
        uint8_t hold_valid = 0;
        for (i = 0; i < 6; i++) {
            if (sensor_raw[i] > 0) {
                hold_valid = 1;
                break;
            }
        }
        if (hold_valid) {
            for (i = 0; i < 6; i++) {
                g_tinyol.hold_sum[i] += sensor_raw[i];
                if (sensor_raw[i] < g_tinyol.hold_min[i]) g_tinyol.hold_min[i] = sensor_raw[i];
                if (sensor_raw[i] > g_tinyol.hold_max[i]) g_tinyol.hold_max[i] = sensor_raw[i];
            }
            g_tinyol.sample_cnt++;
        }
        if (g_tinyol.sample_cnt >= TINYOL_CALIB_HOLD_TICKS) {
            for (i = 0; i < 6; i++) {
                g_tinyol.hold_avg[i] = (uint16_t)(g_tinyol.hold_sum[i] / g_tinyol.sample_cnt);
            }
            SIL_ATCMDS_SendSilHoldExt(ATCMDS_IO_TOPC, g_tinyol.sample_cnt,
                                      g_tinyol.hold_avg, g_tinyol.hold_min,
                                      g_tinyol.hold_max, 6);
            SIL_ATCMDS_SendSilNotify(ATCMDS_IO_TOPC, "TINYOL,CALIB_DONE");
            g_tinyol.state = SIL_APP_TINYOL_STS_NOTIFY_DONE;
            g_tinyol.timer_cnt = 0;
        }
        break;
    }

    case SIL_APP_TINYOL_STS_NOTIFY_DONE:
        if (++g_tinyol.timer_cnt >= 10) {
            g_tinyol.calibration_active = 0;
            g_tinyol.recalibration_requested = 0;
            g_tinyol.state = SIL_APP_TINYOL_STS_READY;
            g_tinyol.timer_cnt = 0;
        }
        break;

    default:
        break;
    }
}

void SIL_APP_TINYOL_MainLoop2(void)
{
    SIL_APP_TINYOL_MainLoop1();
}

void SIL_APP_TINYOL_Exit(void)
{
    memset(&g_tinyol, 0, sizeof(g_tinyol));
}

void SIL_APP_TINYOL_RequestRecalibration(void)
{
    g_tinyol.recalibration_requested = 1;
    g_tinyol.calibration_active = 1;
    g_tinyol.recording_requested = 0;
    g_tinyol.recording_active = 0;
    g_tinyol.replay_ready = 0;
    g_tinyol.replay_built = 0;
    g_tinyol.run_in_progress = 0;
    g_tinyol.training_done = 0;
    g_tinyol.validation_in_progress = 0;
    g_tinyol.validation_done = 0;
    g_tinyol.result_ready = 0;

    SIL_APP_TOUCH_Exit();
    SIL_APP_TOUCH_Enter1();
    SIL_APP_TOUCH_Enter2();

    g_tinyol.state = SIL_APP_TINYOL_STS_NOTIFY_BASE;
    g_tinyol.timer_cnt = 0;
    SIL_APP_TINYOL_InitCalibBuffers();
}

void SIL_APP_TINYOL_SetSessionConfig(uint16_t target_label, uint16_t epochs,
                                     uint16_t capture_count,
                                     uint16_t record_samples,
                                     uint16_t window_start_offset,
                                     uint16_t batch_size,
                                     float learning_rate,
                                     uint16_t confusable_count,
                                     uint16_t confusable_windows,
                                     uint16_t anchor_windows)
{
    if (capture_count > TINYOL_RECORD_MAX_SLOTS) {
        capture_count = TINYOL_RECORD_MAX_SLOTS;
    }
    if (record_samples > TINYOL_RECORD_MAX_SAMPLES) {
        record_samples = TINYOL_RECORD_MAX_SAMPLES;
    }
    g_tinyol.target_label = target_label;
    g_tinyol.epochs = epochs;
    g_tinyol.capture_count = capture_count;
    g_tinyol.record_samples = record_samples;
    g_tinyol.window_start_offset = window_start_offset;
    g_tinyol.batch_size = batch_size;
    g_tinyol.learning_rate = learning_rate;
    g_tinyol.confusable_count = confusable_count;
    g_tinyol.confusable_windows = confusable_windows;
    g_tinyol.anchor_windows = anchor_windows;
    g_tinyol.replay_ready = 0U;
    g_tinyol.replay_built = 0U;
    g_tinyol.run_in_progress = 0U;
    g_tinyol.training_done = 0U;
    g_tinyol.validation_in_progress = 0U;
    g_tinyol.validation_done = 0U;
    g_tinyol.result_ready = 0U;
    g_tinyol.validation_passed = 0U;
}

void SIL_APP_TINYOL_RequestRecording(void)
{
    g_tinyol.recording_requested = 1;
    g_tinyol.recording_active = 0;
    g_tinyol.replay_ready = 0;
    g_tinyol.replay_built = 0;
    g_tinyol.run_in_progress = 0;
    g_tinyol.training_done = 0;
    g_tinyol.validation_in_progress = 0;
    g_tinyol.validation_done = 0;
    g_tinyol.result_ready = 0;
    SIL_APP_TINYOL_ResetRecordingBuffers();
}

void SIL_APP_TINYOL_StartRecording(void)
{
    g_tinyol.recording_requested = 0;
    g_tinyol.recording_active = 1;
}

void SIL_APP_TINYOL_StopRecording(void)
{
    g_tinyol.recording_requested = 0;
    g_tinyol.recording_active = 0;
}

fsp_err_t SIL_APP_TINYOL_BuildReplay(void)
{
    g_train_sample_count = 0;
    
    /* 1. Load default replay data for non-target classes (subject to anchor_windows limits) */
    for (uint16_t label = 0U; label < CNN_OUT_DIM; label++) {
        if (label == g_tinyol.target_label) {
            continue;
        }
        uint16_t default_count = SIL_APP_TINYOL_GetDefaultWindowCount(label);
        uint16_t limit = (default_count < 3U) ? default_count : 3U;
        for (uint16_t i = 0U; i < limit; i++) {
            if (g_train_sample_count < TINYOL_MAX_TRAIN_SAMPLES) {
                g_train_samples[g_train_sample_count].is_target = 0;
                g_train_samples[g_train_sample_count].label = (uint8_t)label;
                g_train_samples[g_train_sample_count].sample_idx = i;
                g_train_indices[g_train_sample_count] = g_train_sample_count;
                g_train_sample_count++;
            }
        }
    }

    /* 2. Load default replay data for target class */
    {
        uint16_t default_count = SIL_APP_TINYOL_GetDefaultWindowCount(g_tinyol.target_label);
        uint16_t limit = (default_count < 3U) ? default_count : 3U;
        for (uint16_t i = 0U; i < limit; i++) {
            if (g_train_sample_count < TINYOL_MAX_TRAIN_SAMPLES) {
                g_train_samples[g_train_sample_count].is_target = 0;
                g_train_samples[g_train_sample_count].label = (uint8_t)g_tinyol.target_label;
                g_train_samples[g_train_sample_count].sample_idx = i;
                g_train_indices[g_train_sample_count] = g_train_sample_count;
                g_train_sample_count++;
            }
        }
    }

    /* 3. Load target recorded data (both RAM targets and Flash golden gestures if they exist) */
    uint16_t target_count = 0;
    if (g_tinyol.record_capture_count > 0U) {
        for (uint16_t slot = 0U; slot < g_tinyol.record_capture_count; slot++) {
            if (g_train_sample_count < TINYOL_MAX_TRAIN_SAMPLES) {
                g_train_samples[g_train_sample_count].is_target = 1; // RAM target
                g_train_samples[g_train_sample_count].label = (uint8_t)g_tinyol.target_label;
                g_train_samples[g_train_sample_count].sample_idx = slot;
                g_train_indices[g_train_sample_count] = g_train_sample_count;
                g_train_sample_count++;
                target_count++;
            }
        }
    }
    if (g_tinyol_head_exists && g_tinyol_head.saved_gesture_count > 0U) {
        for (uint32_t i = 0U; i < g_tinyol_head.saved_gesture_count; i++) {
            if (g_train_sample_count < TINYOL_MAX_TRAIN_SAMPLES) {
                g_train_samples[g_train_sample_count].is_target = 2; // Flash golden gesture
                g_train_samples[g_train_sample_count].label = (uint8_t)g_tinyol_head.saved_gestures[i].label;
                g_train_samples[g_train_sample_count].sample_idx = (uint16_t)i;
                g_train_indices[g_train_sample_count] = g_train_sample_count;
                g_train_sample_count++;
                if (g_tinyol_head.saved_gestures[i].label == g_tinyol.target_label) {
                    target_count++;
                }
            }
        }
    }

    if (g_train_sample_count == 0U || target_count == 0U) {
        return FSP_ERR_INVALID_STATE;
    }

    g_tinyol.replay_built = 1U;
    g_tinyol.replay_ready = 1U;
    g_tinyol.training_done = 0U;
    g_tinyol.validation_done = 0U;
    g_tinyol.result_ready = 0U;
    g_tinyol.state = SIL_APP_TINYOL_STS_RUN_READY;
    {
        char msg[96];
        snprintf(msg, sizeof(msg), "TINYOL,REPLAY_BUILT,target=%u,default=%u,total=%u",
                 (unsigned int)target_count,
                 (unsigned int)(g_train_sample_count - target_count),
                 (unsigned int)g_train_sample_count);
        SIL_ATCMDS_SendSilNotify(ATCMDS_IO_TOPC, msg);
    }
    return FSP_SUCCESS;
}

void SIL_APP_TINYOL_SetRunReady(void)
{
    g_tinyol.run_in_progress = 1U;
    g_tinyol.training_done = 0U;
    g_tinyol.validation_in_progress = 0U;
    g_tinyol.validation_done = 0U;
    g_tinyol.result_ready = 0U;
    g_tinyol.state = SIL_APP_TINYOL_STS_RUN_START;
}

void SIL_APP_TINYOL_SetValidationReady(void)
{
    g_tinyol.validation_in_progress = 1U;
    g_tinyol.run_in_progress = 0U;
    g_tinyol.validation_done = 0U;
    g_tinyol.result_ready = 0U;
    g_tinyol.validation_passed = 0U;
    g_tinyol.state = SIL_APP_TINYOL_STS_VAL_START;
}

void SIL_APP_TINYOL_SetResultReady(void)
{
    g_tinyol.validation_done = 1U;
    g_tinyol.result_ready = 1U;
    g_tinyol.run_in_progress = 0U;
    g_tinyol.validation_in_progress = 0U;
    g_tinyol.state = SIL_APP_TINYOL_STS_RESULT_READY;
}

fsp_err_t SIL_APP_TINYOL_RunTraining(void)
{
    cnn_detect_cache_t cache;
    float train_loss = 0.0f;
    uint32_t train_correct = 0U;
    uint32_t train_total = 0U;
    uint32_t epoch;

    if (!g_tinyol.replay_ready || g_train_sample_count == 0U) {
        return FSP_ERR_INVALID_STATE;
    }

    for (epoch = 0U; epoch < g_tinyol.epochs; epoch++) {
        float epoch_loss = 0.0f;
        uint32_t epoch_correct = 0U;
        uint32_t epoch_total = 0U;
        uint16_t local_batch = 0U;

        /* A. Shuffle dataset indices at the start of each epoch */
        SIL_APP_TINYOL_ShuffleIndices(g_train_indices, g_train_sample_count);
        SIL_APP_TINYOL_ClearGradients();

        /* B. Forward pass and gradient accumulation based on shuffled indices */
        for (uint16_t idx = 0U; idx < g_train_sample_count; idx++) {
            uint16_t sample_pos = g_train_indices[idx];
            sil_train_sample_t *sample = &g_train_samples[sample_pos];
            
            float waveform[CNN_WIN_LEN * CNN_INPUT_CH_TOTAL];
            float variance[CNN_AUX_VAR_DIM];
            float mean[CNN_AUX_VAR_DIM];
            bool success = false;

            if (sample->is_target == 0) {
                success = SIL_APP_TINYOL_BuildFeatureSampleFromDefault(sample->label, sample->sample_idx, waveform, variance, mean);
            } else if (sample->is_target == 1) {
                success = SIL_APP_TINYOL_BuildFeatureSampleFromTarget(sample->sample_idx, waveform, variance, mean);
            } else if (sample->is_target == 2) {
                success = SIL_APP_TINYOL_BuildFeatureSampleFromSaved(sample->sample_idx, waveform, variance, mean);
            }

            if (!success) {
                continue;
            }

            if (!cnn_detect_forward_cache(waveform, variance, mean, &cache)) {
                continue;
            }

            /* C. Calculate Loss with Label Smoothing alignment */
            float label_smoothing = 0.03f; // Align with PC Label Smoothing (usually 0.03f)
            float target_prob = 1.0f - label_smoothing + (label_smoothing / (float)CNN_OUT_DIM);
            float other_prob = label_smoothing / (float)CNN_OUT_DIM;
            
            float prob = cache.proba[sample->label];
            if (prob < 1.0e-6f) prob = 1.0e-6f;
            epoch_loss += -logf(prob);
            train_loss += -logf(prob);

            epoch_total++;
            train_total++;

            /* Determine predicted class */
            uint16_t best = 0U;
            for (uint16_t idx_c = 1U; idx_c < CNN_OUT_DIM; idx_c++) {
                if (cache.proba[idx_c] > cache.proba[best]) {
                    best = idx_c;
                }
            }
            if (best == sample->label) {
                epoch_correct++;
                train_correct++;
            }

            /* D. Accumulate gradients with Label Smoothing */
            float dz3[CNN_OUT_DIM];
            for (uint16_t k = 0U; k < CNN_OUT_DIM; k++) {
                float target = (k == sample->label) ? target_prob : other_prob;
                dz3[k] = cache.proba[k] - target;
            }
            
            SIL_APP_TINYOL_AccumulateSampleGradientsCustom(&cache, dz3);

            local_batch++;
            if (local_batch >= g_tinyol.batch_size) {
                SIL_APP_TINYOL_ApplyGradients(local_batch);
                local_batch = 0U;
            }
        }

        if (local_batch > 0U) {
            SIL_APP_TINYOL_ApplyGradients(local_batch);
        }

        g_tinyol.last_train_loss = (epoch_total > 0U) ? (epoch_loss / (float)epoch_total) : 0.0f;
        g_tinyol.last_train_acc = (epoch_total > 0U) ? ((float)epoch_correct / (float)epoch_total) : 0.0f;
        {
            char msg[96];
            snprintf(msg, sizeof(msg), "TINYOL,TRAIN_EPOCH,%u,loss=%.4f,acc=%.3f",
                     (unsigned int)(epoch + 1U),
                     (double)g_tinyol.last_train_loss,
                     (double)g_tinyol.last_train_acc);
            SIL_ATCMDS_SendSilNotify(ATCMDS_IO_TOPC, msg);
            SIL_UART_DTC_FlushWriteBuffer(&gsil_uart_topc);
        }
    }

    g_tinyol.training_done = 1U;
    g_tinyol.run_in_progress = 0U;
    g_tinyol.state = SIL_APP_TINYOL_STS_VAL_START;
    {
        float train_avg_loss = (train_total > 0U) ? (train_loss / (float)train_total) : train_loss;
        char msg[96];
        snprintf(msg, sizeof(msg), "TINYOL,TRAIN_DONE,loss=%.4f,acc=%.3f",
                 (double)train_avg_loss,
                 (double)((train_total > 0U) ? ((float)train_correct / (float)train_total) : 0.0f));
        SIL_ATCMDS_SendSilNotify(ATCMDS_IO_TOPC, msg);
        SIL_UART_DTC_FlushWriteBuffer(&gsil_uart_topc);
    }
    return FSP_SUCCESS;
}

fsp_err_t SIL_APP_TINYOL_RunValidation(void)
{
    cnn_detect_cache_t cache;
    float val_loss = 0.0f;
    uint32_t val_correct = 0U;
    uint32_t val_total = 0U;
    uint32_t target_correct = 0U;
    uint32_t target_total = 0U;
    uint16_t label;
    uint16_t idx;
    uint16_t sample_idx;

    if (!g_tinyol.training_done) {
        return FSP_ERR_INVALID_STATE;
    }

    for (label = 0U; label < CNN_OUT_DIM; label++) {
        uint16_t default_count = SIL_APP_TINYOL_GetDefaultWindowCount(label);
        for (sample_idx = 0U; sample_idx < default_count; sample_idx++) {
            float waveform[CNN_WIN_LEN * CNN_INPUT_CH_TOTAL];
            float variance[CNN_AUX_VAR_DIM];
            float mean[CNN_AUX_VAR_DIM];
            if (!SIL_APP_TINYOL_BuildFeatureSampleFromDefault(label, sample_idx, waveform, variance, mean)) {
                continue;
            }
            if (!cnn_detect_forward_cache(waveform, variance, mean, &cache)) {
                continue;
            }
            {
                float prob = cache.proba[label];
                uint16_t best = 0U;
                if (prob < 1.0e-6f) {
                    prob = 1.0e-6f;
                }
                val_loss += -logf(prob);
                val_total++;
                for (idx = 1U; idx < CNN_OUT_DIM; idx++) {
                    if (cache.proba[idx] > cache.proba[best]) {
                        best = idx;
                    }
                }
                if (best == label) {
                    val_correct++;
                }
                if (label == g_tinyol.target_label) {
                    target_total++;
                    if (best == label) {
                        target_correct++;
                    }
                }
            }
        }
    }

    /* Validate target recorded data (both RAM targets and Flash golden gesture if they exist) */
    if (g_tinyol.record_capture_count > 0U) {
        for (idx = 0U; idx < g_tinyol.record_capture_count; idx++) {
            float waveform[CNN_WIN_LEN * CNN_INPUT_CH_TOTAL];
            float variance[CNN_AUX_VAR_DIM];
            float mean[CNN_AUX_VAR_DIM];
            if (!SIL_APP_TINYOL_BuildFeatureSampleFromTarget(idx, waveform, variance, mean)) {
                continue;
            }
            if (!cnn_detect_forward_cache(waveform, variance, mean, &cache)) {
                continue;
            }
            {
                float prob = cache.proba[g_tinyol.target_label];
                uint16_t best = 0U;
                if (prob < 1.0e-6f) {
                    prob = 1.0e-6f;
                }
                val_loss += -logf(prob);
                val_total++;
                for (uint16_t idx_c = 1U; idx_c < CNN_OUT_DIM; idx_c++) {
                    if (cache.proba[idx_c] > cache.proba[best]) {
                        best = idx_c;
                    }
                }
                if (best == g_tinyol.target_label) {
                    val_correct++;
                    target_correct++;
                }
                target_total++;
            }
        }
    }
    if (g_tinyol_head_exists && g_tinyol_head.saved_gesture_count > 0U) {
        for (uint32_t s_idx = 0U; s_idx < g_tinyol_head.saved_gesture_count; s_idx++) {
            float waveform[CNN_WIN_LEN * CNN_INPUT_CH_TOTAL];
            float variance[CNN_AUX_VAR_DIM];
            float mean[CNN_AUX_VAR_DIM];
            if (SIL_APP_TINYOL_BuildFeatureSampleFromSaved(s_idx, waveform, variance, mean)) {
                if (cnn_detect_forward_cache(waveform, variance, mean, &cache)) {
                    uint32_t true_label = g_tinyol_head.saved_gestures[s_idx].label;
                    float prob = cache.proba[true_label];
                    uint16_t best = 0U;
                    if (prob < 1.0e-6f) {
                        prob = 1.0e-6f;
                    }
                    val_loss += -logf(prob);
                    val_total++;
                    for (uint16_t idx_c = 1U; idx_c < CNN_OUT_DIM; idx_c++) {
                        if (cache.proba[idx_c] > cache.proba[best]) {
                            best = idx_c;
                        }
                    }
                    if (best == true_label) {
                        val_correct++;
                    }
                    if (true_label == g_tinyol.target_label) {
                        target_total++;
                        if (best == true_label) {
                            target_correct++;
                        }
                    }
                }
            }
        }
    }

    g_tinyol.last_val_loss = (val_total > 0U) ? (val_loss / (float)val_total) : 0.0f;
    g_tinyol.last_val_acc = (val_total > 0U) ? ((float)val_correct / (float)val_total) : 0.0f;
    g_tinyol.last_target_recall = (target_total > 0U) ? ((float)target_correct / (float)target_total) : 0.0f;
    g_tinyol.last_overall_acc = g_tinyol.last_val_acc;
    g_tinyol.validation_passed = ((g_tinyol.last_target_recall >= TINYOL_VALIDATE_TARGET_RECALL_MIN) &&
                                  (g_tinyol.last_overall_acc >= TINYOL_VALIDATE_OVERALL_ACC_MIN))
                                     ? 1U
                                     : 0U;
    g_tinyol.validation_done = 1U;
    g_tinyol.validation_in_progress = 0U;
    g_tinyol.result_ready = 1U;
    g_tinyol.state = SIL_APP_TINYOL_STS_RESULT_READY;
    {
        char msg[128];
        snprintf(msg, sizeof(msg), "TINYOL,VAL_DONE,%s,loss=%.4f,acc=%.3f,target=%.3f",
                 g_tinyol.validation_passed ? "PASS" : "REJECT",
                 (double)g_tinyol.last_val_loss,
                 (double)g_tinyol.last_val_acc,
                 (double)g_tinyol.last_target_recall);
        SIL_ATCMDS_SendSilNotify(ATCMDS_IO_TOPC, msg);
        SIL_UART_DTC_FlushWriteBuffer(&gsil_uart_topc);
    }
    return FSP_SUCCESS;
}

fsp_err_t SIL_APP_TINYOL_LoadActiveHead(void)
{
    fsp_err_t err;

    SIL_APP_TINYOL_EnsureHeadInitialized();
    err = SIL_APP_TINYOL_ReadActiveHeadFromFlash();
    if (err != FSP_SUCCESS) {
        SIL_APP_TINYOL_LoadDefaultHead();
        g_tinyol_head.active_head_exists = 0U;
        g_tinyol_head.active_weight_enabled = 0U;
        SIL_APP_TINYOL_UpdateHeadStatusFlags();
    }
    return err;
}

fsp_err_t SIL_APP_TINYOL_SelectHeadMode(uint8_t use_active_head)
{
    if (use_active_head != 0U) {
        return SIL_APP_TINYOL_LoadActiveHead();
    }

    return SIL_APP_TINYOL_RestoreDefaultHead();
}

fsp_err_t SIL_APP_TINYOL_SaveActiveHead(void)
{
    fsp_err_t err;
    uint8_t prev_exists;
    uint8_t prev_enabled;

    SIL_APP_TINYOL_EnsureHeadInitialized();
    
    /* 每輪只將新錄製手勢中的第 1 筆 (Slot 0) 追加存入 Flash */
    if (g_tinyol.record_capture_count > 0) {
        if (g_tinyol_head.saved_gesture_count < TINYOL_MAX_SAVED_GESTURES) {
            uint32_t idx = g_tinyol_head.saved_gesture_count;
            g_tinyol_head.saved_gestures[idx].label = (uint32_t)g_tinyol.record_labels[0];
            memcpy(g_tinyol_head.saved_gestures[idx].base_avg, g_tinyol.base_avg, sizeof(g_tinyol_head.saved_gestures[idx].base_avg));
            memcpy(g_tinyol_head.saved_gestures[idx].hold_avg, g_tinyol.hold_avg, sizeof(g_tinyol_head.saved_gestures[idx].hold_avg));
            memcpy(g_tinyol_head.saved_gestures[idx].record_raw, g_tinyol.record_raw[0], sizeof(g_tinyol_head.saved_gestures[idx].record_raw));
            g_tinyol_head.saved_gesture_count++;
        }
    }

    /* Notify size and content information via UART before writing to Code Flash */
    {
        char msg[160];
        uint32_t head_size = (uint32_t)sizeof(g_tinyol_head);
        uint32_t data_size = (uint32_t)sizeof(g_tinyol_head.saved_gestures);
        uint32_t count = g_tinyol_head.saved_gesture_count;
        uint32_t label = (count > 0U) ? g_tinyol_head.saved_gestures[count - 1U].label : 0xFFFFU;
        const char *name = "NONE";
        if (label < CNN_OUT_DIM) {
            name = CNN_GESTURE_NAMES[label];
        }
        int32_t flash_free = (int32_t)(TINYOL_ACTIVE_HEAD_FLASH_SIZE - head_size);
        
        uint32_t head_kb_int = head_size / 1024U;
        uint32_t head_kb_frac = ((head_size * 100U) / 1024U) % 100U;
        
        uint32_t data_kb_int = data_size / 1024U;
        uint32_t data_kb_frac = ((data_size * 100U) / 1024U) % 100U;
        
        uint32_t free_kb_int = (uint32_t)flash_free / 1024U;
        uint32_t free_kb_frac = (((uint32_t)flash_free * 100U) / 1024U) % 100U;
        
        snprintf(msg, sizeof(msg), "TINYOL,SAVE_INFO,head_kb=%lu.%02lu,data_kb=%lu.%02lu,label=%lu(%s),free_kb=%lu.%02lu,count=%lu",
                 (unsigned long)head_kb_int, (unsigned long)head_kb_frac,
                 (unsigned long)data_kb_int, (unsigned long)data_kb_frac,
                 (unsigned long)label, name,
                 (unsigned long)free_kb_int, (unsigned long)free_kb_frac,
                 (unsigned long)count);
        SIL_ATCMDS_SendSilNotify(ATCMDS_IO_TOPC, msg);
        SIL_UART_DTC_FlushWriteBuffer(&gsil_uart_topc);
    }

    prev_exists = (uint8_t)g_tinyol_head.active_head_exists;
    prev_enabled = (uint8_t)g_tinyol_head.active_weight_enabled;
    err = SIL_APP_TINYOL_ApplyActiveHeadToFlash();
    if (err == FSP_SUCCESS) {
        g_tinyol_head.active_head_exists = 1U;
        g_tinyol_head.active_weight_enabled = 1U;
        SIL_APP_TINYOL_UpdateHeadStatusFlags();
        return FSP_SUCCESS;
    }
    g_tinyol_head.active_head_exists = prev_exists;
    g_tinyol_head.active_weight_enabled = prev_enabled;
    SIL_APP_TINYOL_UpdateHeadStatusFlags();
    return err;
}

fsp_err_t SIL_APP_TINYOL_EraseActiveHead(void)
{
    fsp_err_t err;
    flash_info_t flash_info = {0};
    uint32_t block_size;
    uint32_t erase_blocks;

    SIL_APP_TINYOL_EnsureHeadInitialized();
    g_tinyol_flash_op_active = 1U;

    /* Unlock flash HP registers */
    (*(volatile uint32_t *)0x400C4800) |= (1U << 10);

    err = g_flash0.p_api->open(g_flash0.p_ctrl, g_flash0.p_cfg);
    if (err != FSP_SUCCESS) {
        SIL_APP_TINYOL_SetLastFlashOp(1U, err);
        g_tinyol_flash_op_active = 0U;
        return err;
    }
    err = g_flash0.p_api->infoGet(g_flash0.p_ctrl, &flash_info);
    if (err != FSP_SUCCESS) {
        SIL_APP_TINYOL_SetLastFlashOp(2U, err);
        g_flash0.p_api->close(g_flash0.p_ctrl);
        g_tinyol_flash_op_active = 0U;
        return err;
    }
    if ((flash_info.code_flash.num_regions == 0U) || (flash_info.code_flash.p_block_array == NULL)) {
        SIL_APP_TINYOL_SetLastFlashOp(2U, FSP_ERR_INVALID_DATA);
        g_flash0.p_api->close(g_flash0.p_ctrl);
        g_tinyol_flash_op_active = 0U;
        return FSP_ERR_INVALID_DATA;
    }

    block_size = SIL_APP_TINYOL_GetBlockSize(TINYOL_ACTIVE_HEAD_FLASH_ADDR);
    erase_blocks = (TINYOL_ACTIVE_HEAD_FLASH_SIZE + block_size - 1U) / block_size;
    SIL_APP_TINYOL_SendFlashOpTrace("ERASE_START", TINYOL_ACTIVE_HEAD_FLASH_ADDR, erase_blocks, 0U);
    SIL_APP_TINYOL_ResetFlashWaitFlags();
    __disable_irq();
    err = g_flash0.p_api->erase(g_flash0.p_ctrl, TINYOL_ACTIVE_HEAD_FLASH_ADDR, erase_blocks);
    __enable_irq();
    if (err != FSP_SUCCESS) {
        SIL_APP_TINYOL_SetLastFlashOp(3U, err);
        g_flash0.p_api->close(g_flash0.p_ctrl);
        g_tinyol_flash_op_active = 0U;
        SIL_APP_TINYOL_SendFlashOpTrace("ERASE_FAIL", TINYOL_ACTIVE_HEAD_FLASH_ADDR, erase_blocks, (uint32_t)err);
        return err;
    }
    /* Code Flash erase is synchronous, no need to wait for callback */
    SIL_APP_TINYOL_SendFlashOpTrace("ERASE_OK", TINYOL_ACTIVE_HEAD_FLASH_ADDR, erase_blocks, 0U);

    SIL_APP_TINYOL_LoadDefaultHead();
    g_tinyol_head.active_head_exists = 0U;
    g_tinyol_head.active_weight_enabled = 0U;
    SIL_APP_TINYOL_UpdateHeadStatusFlags();
    R_FLASH_HP_Close(&g_flash0_ctrl);
    g_tinyol_flash_op_active = 0U;
    SIL_APP_TINYOL_SetLastFlashOp(0U, FSP_SUCCESS);
    SIL_APP_TINYOL_SendFlashOpTrace("ERASE_CLEARED", TINYOL_ACTIVE_HEAD_FLASH_ADDR, block_size, 0U);
    return FSP_SUCCESS;
}

fsp_err_t SIL_APP_TINYOL_RestoreDefaultHead(void)
{
    SIL_APP_TINYOL_EnsureHeadInitialized();
    SIL_APP_TINYOL_LoadDefaultHead();
    g_tinyol_head.active_head_exists = 0U;
    g_tinyol_head.active_weight_enabled = 0U;
    SIL_APP_TINYOL_UpdateHeadStatusFlags();
    return FSP_SUCCESS;
}

fsp_err_t SIL_APP_TINYOL_RunFlashBlockTest(void)
{
    flash_info_t flash_info = {0};
    uint32_t block_size;
    uint32_t write_block_size;
    uint32_t erase_blocks;
    uint32_t offset;
    uint32_t test_addr;
    fsp_err_t err;
    uint32_t checksum = 0U;
    uint32_t limit_addr;
    uint32_t write_len;
    uint32_t padded_len;
    uint8_t chunk[TINYOL_HEAD_WRITE_CHUNK_MAX] = {0xFF};

    SIL_APP_TINYOL_EnsureHeadInitialized();
    g_tinyol_flash_op_active = 1U;

    (*(uint32_t *)0x400C4800) |= (1U << 10);
    err = R_FLASH_HP_Open(&g_flash0_ctrl, &g_flash0_cfg);
    if (err != FSP_SUCCESS) {
        SIL_APP_TINYOL_SetLastFlashOp(1U, err);
        g_tinyol_flash_op_active = 0U;
        return err;
    }
    err = g_flash0.p_api->infoGet(g_flash0.p_ctrl, &flash_info);
    if (err != FSP_SUCCESS) {
        SIL_APP_TINYOL_SetLastFlashOp(2U, err);
        R_FLASH_HP_Close(&g_flash0_ctrl);
        g_tinyol_flash_op_active = 0U;
        return err;
    }
    if ((flash_info.code_flash.num_regions == 0U) || (flash_info.code_flash.p_block_array == NULL)) {
        SIL_APP_TINYOL_SetLastFlashOp(2U, FSP_ERR_INVALID_DATA);
        R_FLASH_HP_Close(&g_flash0_ctrl);
        g_tinyol_flash_op_active = 0U;
        return FSP_ERR_INVALID_DATA;
    }

    block_size = SIL_APP_TINYOL_GetBlockSize(TINYOL_ACTIVE_HEAD_FLASH_ADDR);
    write_block_size = flash_info.code_flash.p_block_array->block_size_write;
    if ((block_size == 0U) || (block_size > TINYOL_FLASHTEST_BUFFER_MAX) ||
        (write_block_size == 0U) || (write_block_size > TINYOL_HEAD_WRITE_CHUNK_MAX) ||
        ((block_size % write_block_size) != 0U) ||
        (block_size > (TINYOL_ACTIVE_HEAD_FLASH_SIZE / 2U))) {
        SIL_APP_TINYOL_SetLastFlashOp(2U, FSP_ERR_INVALID_DATA);
        R_FLASH_HP_Close(&g_flash0_ctrl);
        g_tinyol_flash_op_active = 0U;
        return FSP_ERR_INVALID_DATA;
    }

    test_addr = TINYOL_ACTIVE_HEAD_FLASH_ADDR;
    limit_addr = TINYOL_ACTIVE_HEAD_FLASH_ADDR + TINYOL_ACTIVE_HEAD_FLASH_SIZE;
    if ((test_addr < TINYOL_ACTIVE_HEAD_FLASH_ADDR) || ((test_addr + block_size) > limit_addr)) {
        SIL_APP_TINYOL_SetLastFlashOp(2U, FSP_ERR_INVALID_ADDRESS);
        R_FLASH_HP_Close(&g_flash0_ctrl);
        g_tinyol_flash_op_active = 0U;
        return FSP_ERR_INVALID_ADDRESS;
    }

    g_tinyol_last_flash_test_addr = test_addr;
    SIL_APP_TINYOL_FillFlashTestString(g_tinyol_flashtest_write_buf, block_size, test_addr);
    padded_len = (uint32_t)strlen((const char *)g_tinyol_flashtest_write_buf) + 1U;
    if (padded_len > block_size) {
        padded_len = block_size;
    }

    erase_blocks = (TINYOL_ACTIVE_HEAD_FLASH_SIZE + block_size - 1U) / block_size;
    SIL_APP_TINYOL_SendFlashTestTrace("ERASE_START", test_addr, block_size * erase_blocks, FSP_SUCCESS);
    __disable_irq();
    err = R_FLASH_HP_Erase(&g_flash0_ctrl, test_addr, erase_blocks);
    __enable_irq();
    if (err != FSP_SUCCESS) {
        SIL_APP_TINYOL_SetLastFlashOp(3U, err);
        SIL_APP_TINYOL_SendFlashTestTrace("ERASE_FAIL", test_addr, block_size, err);
        R_FLASH_HP_Close(&g_flash0_ctrl);
        g_tinyol_flash_op_active = 0U;
        return err;
    }
    SIL_APP_TINYOL_SendFlashTestTrace("ERASE_DONE", test_addr, block_size, FSP_SUCCESS);

    for (offset = 0; offset < block_size; offset += write_block_size) {
        memset(chunk, 0xFF, sizeof(chunk));
        write_len = write_block_size;
        if (offset < padded_len) {
            write_len = padded_len - offset;
            if (write_len > write_block_size) {
                write_len = write_block_size;
            }
            memcpy(chunk, &g_tinyol_flashtest_write_buf[offset], write_len);
        }
        if ((offset % 4096U) == 0U) {
            SIL_APP_TINYOL_SendFlashTestTrace("WRITE_START", test_addr + offset, write_block_size, FSP_SUCCESS);
        }
        __disable_irq();
        err = R_FLASH_HP_Write(&g_flash0_ctrl,
                               (uint32_t)chunk,
                               test_addr + offset,
                               write_block_size);
        __enable_irq();
        if (err != FSP_SUCCESS) {
            SIL_APP_TINYOL_SetLastFlashOp(4U, err);
            SIL_APP_TINYOL_SendFlashTestTrace("WRITE_FAIL", test_addr + offset, write_block_size, err);
            R_FLASH_HP_Close(&g_flash0_ctrl);
            g_tinyol_flash_op_active = 0U;
            return err;
        }
        if ((offset % 4096U) == 0U) {
            SIL_APP_TINYOL_SendFlashTestTrace("WRITE_DONE", test_addr + offset, write_block_size, FSP_SUCCESS);
        }
    }

    if (memcmp((const void *)(uintptr_t)test_addr,
               g_tinyol_flashtest_write_buf,
               block_size) != 0) {
        SIL_APP_TINYOL_SetLastFlashOp(7U, FSP_ERR_ASSERTION);
        R_FLASH_HP_Close(&g_flash0_ctrl);
        g_tinyol_flash_op_active = 0U;
        return FSP_ERR_ASSERTION;
    }

    for (offset = 0; offset < block_size; offset++) {
        checksum ^= g_tinyol_flashtest_write_buf[offset];
        checksum = (checksum << 1) | (checksum >> 31);
    }
    R_FLASH_HP_Close(&g_flash0_ctrl);
    g_tinyol_flash_op_active = 0U;
    g_tinyol_last_flash_test_checksum = checksum;
    SIL_APP_TINYOL_SetLastFlashOp(0U, FSP_SUCCESS);
    SIL_APP_TINYOL_SendFlashTestTrace("COMPLETE", test_addr, block_size, FSP_SUCCESS);
    return FSP_SUCCESS;
}

uint8_t SIL_APP_TINYOL_IsCalibrationActive(void) { return g_tinyol.calibration_active; }
uint8_t SIL_APP_TINYOL_IsRecordingActive(void) { return g_tinyol.recording_active; }
uint8_t SIL_APP_TINYOL_IsReplayReady(void) { return g_tinyol.replay_ready; }
uint8_t SIL_APP_TINYOL_IsReplayBuilt(void) { return g_tinyol.replay_built; }
uint8_t SIL_APP_TINYOL_IsRunInProgress(void) { return g_tinyol.run_in_progress; }
uint8_t SIL_APP_TINYOL_IsTrainingDone(void) { return g_tinyol.training_done; }
uint8_t SIL_APP_TINYOL_IsValidationInProgress(void) { return g_tinyol.validation_in_progress; }
uint8_t SIL_APP_TINYOL_IsValidationDone(void) { return g_tinyol.validation_done; }
uint8_t SIL_APP_TINYOL_IsResultReady(void) { return g_tinyol.result_ready; }
uint8_t SIL_APP_TINYOL_IsValidationPassed(void) { return g_tinyol.validation_passed; }
uint8_t SIL_APP_TINYOL_HasActiveHead(void) { SIL_APP_TINYOL_EnsureHeadInitialized(); return g_tinyol_head_exists; }
uint8_t SIL_APP_TINYOL_IsActiveHeadEnabled(void) { SIL_APP_TINYOL_EnsureHeadInitialized(); return g_tinyol_head_enabled; }
uint32_t SIL_APP_TINYOL_GetActiveWeightSlot(void) { SIL_APP_TINYOL_EnsureHeadInitialized(); return g_tinyol_head.active_weight_slot; }
uint32_t SIL_APP_TINYOL_GetActiveHeadVersion(void) { SIL_APP_TINYOL_EnsureHeadInitialized(); return g_tinyol_head.head_version; }
uint32_t SIL_APP_TINYOL_GetActiveHeadChecksum(void) { SIL_APP_TINYOL_EnsureHeadInitialized(); return g_tinyol_head.checksum; }
uint32_t SIL_APP_TINYOL_GetActiveHeadBytes(void) { SIL_APP_TINYOL_EnsureHeadInitialized(); return g_tinyol_head.weight_bytes; }
uint32_t SIL_APP_TINYOL_GetActiveHeadMagic(void) { SIL_APP_TINYOL_EnsureHeadInitialized(); return g_tinyol_head.magic; }
void SIL_APP_TINYOL_CopyActiveHeadDump(uint8_t *dst, uint32_t len)
{
    uint32_t copy_len;

    SIL_APP_TINYOL_EnsureHeadInitialized();
    if ((dst == NULL) || (len == 0U)) {
        return;
    }
    copy_len = (len < (uint32_t)sizeof(g_tinyol_head)) ? len : (uint32_t)sizeof(g_tinyol_head);
    memcpy(dst, &g_tinyol_head, copy_len);
}
uint8_t SIL_APP_TINYOL_GetLastFlashOpStage(void) { return g_tinyol_last_flash_op_stage; }
uint32_t SIL_APP_TINYOL_GetLastFlashOpError(void) { return g_tinyol_last_flash_op_error; }
uint32_t SIL_APP_TINYOL_GetLastFlashTestChecksum(void) { return g_tinyol_last_flash_test_checksum; }
uint32_t SIL_APP_TINYOL_GetLastFlashTestAddress(void) { return g_tinyol_last_flash_test_addr; }
float SIL_APP_TINYOL_GetLastTrainLoss(void) { return g_tinyol.last_train_loss; }
float SIL_APP_TINYOL_GetLastTrainAcc(void) { return g_tinyol.last_train_acc; }
float SIL_APP_TINYOL_GetLastValLoss(void) { return g_tinyol.last_val_loss; }
float SIL_APP_TINYOL_GetLastValAcc(void) { return g_tinyol.last_val_acc; }
float SIL_APP_TINYOL_GetLastTargetRecall(void) { return g_tinyol.last_target_recall; }
float SIL_APP_TINYOL_GetLastOverallAcc(void) { return g_tinyol.last_overall_acc; }

uint16_t SIL_APP_TINYOL_GetTargetLabel(void) { return g_tinyol.target_label; }
uint16_t SIL_APP_TINYOL_GetClassCount(void) { return g_tinyol.class_count; }
uint16_t SIL_APP_TINYOL_GetEpochs(void) { return g_tinyol.epochs; }
uint8_t SIL_APP_TINYOL_GetHandshakeSent(void) { return g_tinyol.handshake_sent; }
uint8_t SIL_APP_TINYOL_GetRecalibrationRequested(void) { return g_tinyol.recalibration_requested; }
const float *SIL_APP_TINYOL_GetDenseF2Weights(void) { SIL_APP_TINYOL_EnsureHeadInitialized(); return g_tinyol_head.dense_f2_w; }
const float *SIL_APP_TINYOL_GetDenseF2Bias(void) { SIL_APP_TINYOL_EnsureHeadInitialized(); return g_tinyol_head.dense_f2_b; }
const float *SIL_APP_TINYOL_GetDenseOutWeights(void) { SIL_APP_TINYOL_EnsureHeadInitialized(); return g_tinyol_head.dense_out_w; }
const float *SIL_APP_TINYOL_GetDenseOutBias(void) { SIL_APP_TINYOL_EnsureHeadInitialized(); return g_tinyol_head.dense_out_b; }

uint32_t SIL_APP_TINYOL_GetSavedRecordLabel(void) {
    SIL_APP_TINYOL_EnsureHeadInitialized();
    return (g_tinyol_head.saved_gesture_count > 0U) ? g_tinyol_head.saved_gestures[g_tinyol_head.saved_gesture_count - 1U].label : 0xFFFFU;
}

uint8_t SIL_APP_TINYOL_HasSavedRecord(void) {
    SIL_APP_TINYOL_EnsureHeadInitialized();
    return (g_tinyol_head_exists && g_tinyol_head.saved_gesture_count > 0U) ? 1U : 0U;
}
