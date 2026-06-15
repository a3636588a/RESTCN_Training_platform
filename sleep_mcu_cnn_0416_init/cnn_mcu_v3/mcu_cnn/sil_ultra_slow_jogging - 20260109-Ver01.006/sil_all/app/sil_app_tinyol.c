#include "sil_app_tinyol.h"

#include "..\app\sil_app_touch.h"
#include "..\cnn_lib\cnn_model_data.h"
#include "..\protocol_atcmds\sil_atcmds.h"
#include "..\uart_dtc\sil_uart_dtc_topc.h"
#include <string.h>

static sil_app_tinyol_s g_tinyol = {0};

#define TINYOL_NOTIFY_BASE_TICKS 250U
#define TINYOL_CALIB_BASE_TICKS 500U
#define TINYOL_NOTIFY_HOLD_TICKS 250U
#define TINYOL_CALIB_HOLD_TICKS 500U

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
    g_tinyol.anchor_windows = 2;
    g_tinyol.handshake_sent = 0;
    g_tinyol.recalibration_requested = 0;
    g_tinyol.calibration_active = 0;
    g_tinyol.recording_requested = 0;
    g_tinyol.recording_active = 0;
    g_tinyol.timer_cnt = 0;
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
}

void SIL_APP_TINYOL_RequestRecording(void)
{
    g_tinyol.recording_requested = 1;
    g_tinyol.recording_active = 0;
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

uint8_t SIL_APP_TINYOL_IsCalibrationActive(void) { return g_tinyol.calibration_active; }
uint8_t SIL_APP_TINYOL_IsRecordingActive(void) { return g_tinyol.recording_active; }

uint16_t SIL_APP_TINYOL_GetTargetLabel(void) { return g_tinyol.target_label; }
uint16_t SIL_APP_TINYOL_GetClassCount(void) { return g_tinyol.class_count; }
uint16_t SIL_APP_TINYOL_GetEpochs(void) { return g_tinyol.epochs; }
uint8_t SIL_APP_TINYOL_GetHandshakeSent(void) { return g_tinyol.handshake_sent; }
uint8_t SIL_APP_TINYOL_GetRecalibrationRequested(void) { return g_tinyol.recalibration_requested; }
