#include "sil_app_glove_ml.h"
#include "..\app\sil_app_ticks.h"
#include "..\cnn_lib\cnn_detect.h"
#include "..\cnn_lib\cnn_features_lib.h"
#include "..\cnn_lib\cnn_model_data.h"
#include "..\cnn_lib\cnn_postprocess.h"
#include "..\mlp_lib\dynamic_feature.h"
#include "..\mlp_lib\gain_map_lib.h"
#include "..\mlp_lib\majority_chain.h"
#include "..\app\sil_app_tinyol.h"
#include "..\protocol_atcmds\sil_atcmds.h"
#include <math.h>
#include <stdbool.h>
#include <string.h>

// Note: This file is now PURE C. No TFLite Micro or C++ dependency.
// It calls the optimized Pure C Inference engine.

static sil_app_glove_ml_s gsil_app_glove_ml;

/* Algorithm Contexts */
static cnn_feat_ctx_t s_cnn_ctx;
static cnn_post_ctx_t s_post_ctx;   /* Modular Post-processing Context */
static majority_chain_t s_chain;
static dyn_ctx_t s_dyn_ctx;
static gain_map_t s_gain_map;
static bool s_algo_inited = false;

static uint32_t s_time_ms = 0;
static inline void s_time_tick(uint32_t dt) { s_time_ms += dt; }
static inline uint32_t s_get_time_ms(void) { return s_time_ms; }

/* CNN Feature Buffers */
static float s_waveform[CNN_WIN_LEN * CNN_INPUT_CH_TOTAL];
static float s_variance[CNN_CH_USED];
static float s_mean[CNN_CH_USED];
static float s_proba[CNN_OUT_DIM];

fsp_err_t SIL_APP_GLOVE_ML_Enter1() {
  fsp_err_t head_err;
  memset(&gsil_app_glove_ml, 0, sizeof(gsil_app_glove_ml));
  gsil_app_glove_ml.state = SIL_APP_GLOVE_ML_STS_WARMUP;
  gsil_app_glove_ml.timer_cnt = 0;

  head_err = SIL_APP_TINYOL_LoadActiveHead();
  if (head_err == FSP_SUCCESS) {
    SIL_ATCMDS_SendSilNotify(ATCMDS_IO_TOPC, "TINYOL,ACTIVE_HEAD_LOADED");
  } else {
    SIL_ATCMDS_SendSilNotify(ATCMDS_IO_TOPC, "TINYOL,ACTIVE_HEAD_FALLBACK_DEFAULT");
  }
  s_algo_inited = false;
  return FSP_SUCCESS;
}

fsp_err_t SIL_APP_GLOVE_ML_Enter2() { return FSP_SUCCESS; }

void SIL_APP_GLOVE_ML_MainLoop1() {
  uint16_t sensor_raw[6] = {0};
  uint16_t sensor_ref[6] = {0};

  uint32_t i;
  static uint32_t last_touch_cnt = 0;
  uint32_t current_touch_cnt = gsil_app_touch.sensor.count;

  if (last_touch_cnt < current_touch_cnt) {
    last_touch_cnt = current_touch_cnt;

    /* Update local time base (10ms per touch sample) */
    s_time_tick(10);
    uint32_t now_ms = s_get_time_ms();

    /* Data Acquisition */
    SIL_APP_TOUCH_GetAllChannelsDataGlove(sensor_raw, 6);
    for (i = 0; i < 6; i++)
      sensor_ref[i] = gsil_app_touch.sensor.a_ref_data_ch[i];

    switch (gsil_app_glove_ml.state) {
    case SIL_APP_GLOVE_ML_STS_WARMUP:
      if (gsil_app_glove_ml.timer_cnt++ >= 10) {
        gsil_app_glove_ml.state = SIL_APP_GLOVE_ML_STS_NOTIFY_BASE;
        gsil_app_glove_ml.timer_cnt = 0;
      }
      break;

    case SIL_APP_GLOVE_ML_STS_NOTIFY_BASE:
      SIL_ATCMDS_SendSilNotify(ATCMDS_IO_TOPC, "INITBASE");
      if (gsil_app_glove_ml.timer_cnt++ >= 50) {
        gsil_app_glove_ml.state = SIL_APP_GLOVE_ML_STS_CALIB_BASE;
        gsil_app_glove_ml.timer_cnt = 0;
        gsil_app_glove_ml.sample_cnt = 0;
        for (i = 0; i < 6; i++) {
          gsil_app_glove_ml.base_min[i] = 0xFFFF;
          gsil_app_glove_ml.base_max[i] = 0;
          gsil_app_glove_ml.base_sum[i] = 0;
        }
      }
      break;

    case SIL_APP_GLOVE_ML_STS_CALIB_BASE: {
      uint8_t base_valid = 0;
      for (i = 0; i < 6; i++)
        if (sensor_raw[i] > 0)
          base_valid = 1;

      if (base_valid) {
        for (i = 0; i < 6; i++) {
          gsil_app_glove_ml.base_sum[i] += sensor_raw[i];
          if (sensor_raw[i] < gsil_app_glove_ml.base_min[i])
            gsil_app_glove_ml.base_min[i] = sensor_raw[i];
          if (sensor_raw[i] > gsil_app_glove_ml.base_max[i])
            gsil_app_glove_ml.base_max[i] = sensor_raw[i];
        }
        gsil_app_glove_ml.sample_cnt++;
      }

      if (gsil_app_glove_ml.sample_cnt >= 500) {
        for (i = 0; i < 6; i++) {
          gsil_app_glove_ml.base_avg[i] =
              (uint16_t)(gsil_app_glove_ml.base_sum[i] /
                         gsil_app_glove_ml.sample_cnt);

          /* Use base + 20000 to replace manual calibration */
//          gsil_app_glove_ml.hold_avg[i] = (uint16_t)(gsil_app_glove_ml.base_avg[i] + 20000);
//          gsil_app_glove_ml.hold_min[i] = gsil_app_glove_ml.hold_avg[i];
//          gsil_app_glove_ml.hold_max[i] = gsil_app_glove_ml.hold_avg[i];
        }
        SIL_ATCMDS_SendSilBaseExt(ATCMDS_IO_TOPC, gsil_app_glove_ml.sample_cnt,
                                  gsil_app_glove_ml.base_avg,
                                  gsil_app_glove_ml.base_min,
                                  gsil_app_glove_ml.base_max, 6);

        /* Send simulated Hold data to host to maintain protocol flow */
//        SIL_ATCMDS_SendSilHoldExt(ATCMDS_IO_TOPC, 1,
//                                  gsil_app_glove_ml.hold_avg,
//                                  gsil_app_glove_ml.hold_min,
//                                  gsil_app_glove_ml.hold_max, 6);

        /* Skip HOLD calibration states and go to detection directly */
        gsil_app_glove_ml.state = SIL_APP_GLOVE_ML_STS_NOTIFY_HOLD;
        gsil_app_glove_ml.timer_cnt = 0;
      }
    } break;


    case SIL_APP_GLOVE_ML_STS_NOTIFY_HOLD:
      SIL_ATCMDS_SendSilNotify(ATCMDS_IO_TOPC, "INITHOLD");
      if (gsil_app_glove_ml.timer_cnt++ >= 500) {
        gsil_app_glove_ml.state = SIL_APP_GLOVE_ML_STS_CALIB_HOLD;
        gsil_app_glove_ml.timer_cnt = 0;
        gsil_app_glove_ml.sample_cnt = 0;
        for (i = 0; i < 6; i++) {
          gsil_app_glove_ml.hold_min[i] = 0xFFFF;
          gsil_app_glove_ml.hold_max[i] = 0;
          gsil_app_glove_ml.hold_sum[i] = 0;
        }
      }
      break;

    case SIL_APP_GLOVE_ML_STS_CALIB_HOLD: {
      uint8_t hold_valid = 0;
      for (i = 0; i < 6; i++)
        if (sensor_raw[i] > 0)
          hold_valid = 1;

      if (hold_valid) {
        for (i = 0; i < 6; i++) {
          gsil_app_glove_ml.hold_sum[i] += sensor_raw[i];
          if (sensor_raw[i] < gsil_app_glove_ml.hold_min[i])
            gsil_app_glove_ml.hold_min[i] = sensor_raw[i];
          if (sensor_raw[i] > gsil_app_glove_ml.hold_max[i])
            gsil_app_glove_ml.hold_max[i] = sensor_raw[i];
        }
        gsil_app_glove_ml.sample_cnt++;
      }

      if (gsil_app_glove_ml.sample_cnt >= 500) {
        for (i = 0; i < 6; i++) {
          gsil_app_glove_ml.hold_avg[i] =
              (uint16_t)(gsil_app_glove_ml.hold_sum[i] /
                         gsil_app_glove_ml.sample_cnt);
        }
        SIL_ATCMDS_SendSilHoldExt(ATCMDS_IO_TOPC, gsil_app_glove_ml.sample_cnt,
                                  gsil_app_glove_ml.hold_avg,
                                  gsil_app_glove_ml.hold_min,
                                  gsil_app_glove_ml.hold_max, 6);

        gsil_app_glove_ml.state = SIL_APP_GLOVE_ML_STS_NOTIFY_DETECT;
        gsil_app_glove_ml.timer_cnt = 0;
      }
    } break;


    case SIL_APP_GLOVE_ML_STS_NOTIFY_DETECT:
      SIL_ATCMDS_SendSilNotify(ATCMDS_IO_TOPC, "DETECT START");
      if (gsil_app_glove_ml.timer_cnt++ >= 50) {
        gsil_app_glove_ml.state = SIL_APP_GLOVE_ML_STS_INFERENCE;
        gsil_app_glove_ml.timer_cnt = 0;
      }
      break;

    case SIL_APP_GLOVE_ML_STS_INFERENCE: {
      uint16_t current_ref[6];
      for (i = 0; i < 6; i++) {
        current_ref[i] = (sensor_ref[i] != 0) ? sensor_ref[i]
                                              : gsil_app_glove_ml.base_avg[i];
      }

      /* Algorithm Init */
      if (!s_algo_inited) {
        cnn_feat_init(&s_cnn_ctx, CNN_WIN_LEN, CNN_INFER_STRIDE, CNN_SLOPE_FACTOR);
        cnn_detect_init();
        cnn_post_init(&s_post_ctx);  /* Initialize Modular Post-processing */
        majority_chain_reset(&s_chain);
        dyn_init(&s_dyn_ctx);
        gainmap_init(&s_gain_map);

        uint16_t map_hold_6[GAIN_CHN], map_ref_6[GAIN_CHN];
        for (i = 0; i < GAIN_CHN; i++) {
          map_hold_6[i] = gsil_app_glove_ml.hold_avg[i];
          map_ref_6[i] = current_ref[i];
        }
        gainmap_update_from_holdavg(&s_gain_map, map_hold_6, map_ref_6);
        s_algo_inited = true;
      }

      /* Apply Gain mapping */
      uint16_t row_gain[GAIN_CHN], hold_gain[GAIN_CHN], base_gain[GAIN_CHN];
      for (i = 0; i < GAIN_CHN; i++) {
        row_gain[i] = gainmap_apply_row_u16(&s_gain_map, (uint8_t)i,
                                            sensor_raw[i], current_ref[i]);
        hold_gain[i] = gainmap_apply_row_u16(&s_gain_map, (uint8_t)i,
                                             gsil_app_glove_ml.hold_avg[i],
                                             current_ref[i]);
        base_gain[i] = current_ref[i];
      }


      /* CNN Feature extraction (3-branch: waveform, variance, mean) */

      if (cnn_compute_features(&s_cnn_ctx, row_gain, base_gain, hold_gain,
                               s_waveform, s_variance, s_mean)) {

        /* 1. Run Pure-C Inference to get softmax probabilities in s_proba */
        cnn_detect_predict(s_waveform, s_variance, s_mean, s_proba);

        /* 2. Modular Post-processing: EWMA Smoothing + Hysteresis Latching */
        int stable_id = cnn_post_update(&s_post_ctx, s_proba);

        /* 3. Output results to UART and Dynamic Matcher */
        if (stable_id == -1) {
          SIL_ATCMDS_SendSilGesture(ATCMDS_IO_TOPC, "convert");
          SIL_ATCMDS_SendSilGesture(ATCMDS_IO_TOBLE, "convert");
        } else {
          SIL_ATCMDS_SendSilGesture(ATCMDS_IO_TOPC, CNN_GESTURE_NAMES[stable_id]);
          SIL_ATCMDS_SendSilGesture(ATCMDS_IO_TOBLE, CNN_GESTURE_NAMES[stable_id]);

          /* Feed dynamic matcher for sequence detection (e.g. SOS, CATCH) */


//          const char *dyn_name = NULL;
//          if (dyn_feed(&s_dyn_ctx, (int16_t)stable_id, now_ms, &dyn_name)) {
//            SIL_ATCMDS_SendSilDynamicGesture(ATCMDS_IO_TOPC, dyn_name);
//          }

        }
      }

    } break;
    }
  }
}

void SIL_APP_GLOVE_ML_MainLoop2() { SIL_APP_GLOVE_ML_MainLoop1(); }

void SIL_APP_GLOVE_ML_Exit() {}
