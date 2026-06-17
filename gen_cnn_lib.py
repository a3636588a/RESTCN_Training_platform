import os
import sys
import json
import re
from pathlib import Path

import numpy as np

# --- 1. Templates for Feature Extraction ---
TEMPLATE_FEATURES_H = '''#ifndef CNN_FEATURES_LIB_H
#define CNN_FEATURES_LIB_H

#include <stdint.h>
#include <stdbool.h>

#define CNN_WIN_LEN      {{WIN_LEN}}u
#define CNN_CH_USED       {{CH_USED}}u
#define CNN_INFER_STRIDE  {{INFER_STRIDE}}u
#define CNN_SLOPE_FACTOR  {{SLOPE_FACTOR}}f

/* CNN Input Dimensions (Level + Slope) */
#define CNN_INPUT_CH_LEVEL   {{CH_USED}}
#define CNN_INPUT_CH_SLOPE   {{CH_USED}}
#define CNN_INPUT_CH_TOTAL   (CNN_INPUT_CH_LEVEL + CNN_INPUT_CH_SLOPE)

/* Auxiliary Input Dimensions */
#define CNN_AUX_VAR_DIM      {{CH_USED}}

typedef struct {
    uint16_t row_buf[CNN_CH_USED][{{WIN_LEN}}];
    uint16_t base_buf[CNN_CH_USED][{{WIN_LEN}}];
    uint16_t head;
    uint16_t count;
    uint16_t stride_ctr;
    uint16_t win_len;
    uint16_t infer_stride;
    float slope_factor;
} cnn_feat_ctx_t;

void cnn_feat_init(cnn_feat_ctx_t *ctx, uint16_t win_len, uint16_t infer_stride, float slope_factor);
void cnn_feat_reset(cnn_feat_ctx_t *ctx);

bool cnn_compute_features(
    cnn_feat_ctx_t *ctx,
    const uint16_t *row_u16,
    const uint16_t *base_u16,
    const uint16_t *holdavg_u16,
    float *out_waveform,
    float *out_variance,
    float *out_mean);

bool cnn_compute_features_from_window(
    const uint16_t window_u16[CNN_WIN_LEN][CNN_CH_USED],
    const uint16_t *base_u16,
    const uint16_t *holdavg_u16,
    float *out_waveform,
    float *out_variance,
    float *out_mean);

#endif
'''

TEMPLATE_FEATURES_C = '''#include "cnn_features_lib.h"
#include <math.h>
#include <string.h>

#define CNN_EPS 1e-6f

void cnn_feat_init(cnn_feat_ctx_t *ctx, uint16_t win_len, uint16_t infer_stride, float slope_factor) {
    if (!ctx) return;
    ctx->win_len = (win_len > 0) ? win_len : (uint16_t)CNN_WIN_LEN;
    ctx->infer_stride = (infer_stride > 0) ? infer_stride : (uint16_t)CNN_INFER_STRIDE;
    ctx->slope_factor = (slope_factor > 0) ? slope_factor : 20.0f;
    cnn_feat_reset(ctx);
}

void cnn_feat_reset(cnn_feat_ctx_t *ctx) {
    if (!ctx) return;
    ctx->head = 0;
    ctx->count = 0;
    ctx->stride_ctr = 0;
    memset(ctx->row_buf, 0, sizeof(ctx->row_buf));
    memset(ctx->base_buf, 0, sizeof(ctx->base_buf));
}

static inline float compute_dn(uint16_t row, uint16_t base, uint16_t holdavg) {
    float d = (float)((int32_t)row - (int32_t)base);
    float span = fabsf((float)((int32_t)holdavg - (int32_t)base));
    if (span < 1.0f) span = 1.0f;
    return d / (span + CNN_EPS);
}

static void compute_features_from_window_core(
    const uint16_t window_u16[CNN_WIN_LEN][CNN_CH_USED],
    const uint16_t *base_u16,
    const uint16_t *holdavg_u16,
    float *out_waveform,
    float *out_variance,
    float *out_mean) {
    for (uint8_t ch = 0; ch < (uint8_t)CNN_CH_USED; ch++) {
        float sum = 0.0f;
        float sum_sq = 0.0f;
        float prev_v = 0.0f;
        for (uint16_t i = 0; i < (uint16_t)CNN_WIN_LEN; i++) {
            float v = compute_dn(window_u16[i][ch], base_u16[ch], holdavg_u16[ch]);
            out_waveform[i * (uint16_t)CNN_INPUT_CH_TOTAL + ch] = v;
            if (i == 0) {
                out_waveform[i * (uint16_t)CNN_INPUT_CH_TOTAL + (uint16_t)CNN_INPUT_CH_LEVEL + ch] = 0.0f;
            } else {
                out_waveform[i * (uint16_t)CNN_INPUT_CH_TOTAL + (uint16_t)CNN_INPUT_CH_LEVEL + ch] = (v - prev_v) * CNN_SLOPE_FACTOR;
            }
            prev_v = v;
            sum += v;
            sum_sq += v * v;
        }
        float avg = sum / (float)CNN_WIN_LEN;
        float var = (sum_sq / (float)CNN_WIN_LEN) - (avg * avg);
        out_mean[ch] = avg;
        out_variance[ch] = (var > 0.0f) ? var : 0.0f;
    }
}

bool cnn_compute_features(
    cnn_feat_ctx_t *ctx,
    const uint16_t *row_u16,
    const uint16_t *base_u16,
    const uint16_t *holdavg_u16,
    float *out_waveform,
    float *out_variance,
    float *out_mean) {
    if (!ctx || !row_u16 || !base_u16 || !holdavg_u16 || !out_waveform || !out_variance || !out_mean) return false;

    uint16_t head = ctx->head;
    for (uint8_t ch = 0; ch < (uint8_t)CNN_CH_USED; ch++) {
        ctx->row_buf[ch][head] = row_u16[ch];
        ctx->base_buf[ch][head] = base_u16[ch];
    }
    ctx->head = (uint16_t)((head + 1U) % ctx->win_len);
    if (ctx->count < ctx->win_len) ctx->count++;
    
    ctx->stride_ctr++;
    if (ctx->stride_ctr < ctx->infer_stride) return false;
    ctx->stride_ctr = 0;
    if (ctx->count < ctx->win_len) return false;

    static float window_dn[CNN_CH_USED][{{WIN_LEN}}];
    for (uint16_t i = 0; i < ctx->win_len; i++) {
        uint16_t idx = (uint16_t)((ctx->head + i) % ctx->win_len);
        for (uint8_t ch = 0; ch < (uint8_t)CNN_CH_USED; ch++) {
            window_dn[ch][i] = compute_dn(ctx->row_buf[ch][idx], ctx->base_buf[ch][idx], holdavg_u16[ch]);
        }
    }

    for (uint8_t ch = 0; ch < (uint8_t)CNN_CH_USED; ch++) {
        float sum = 0, sum_sq = 0;
        for (uint16_t i = 0; i < ctx->win_len; i++) {
            float v = window_dn[ch][i];
            sum += v; sum_sq += v * v;
            out_waveform[i * (uint16_t)CNN_INPUT_CH_TOTAL + ch] = v;
            
            float slope = 0.0f;
            if (i > 0) slope = (v - window_dn[ch][i-1]) * ctx->slope_factor;
            out_waveform[i * (uint16_t)CNN_INPUT_CH_TOTAL + (uint16_t)CNN_INPUT_CH_LEVEL + ch] = slope;
        }
        float avg = sum / (float)ctx->win_len;
        float var = (sum_sq / (float)ctx->win_len) - (avg * avg);
        out_mean[ch] = avg;
        out_variance[ch] = (var > 0) ? var : 0;
    }
    return true;
}

bool cnn_compute_features_from_window(
    const uint16_t window_u16[CNN_WIN_LEN][CNN_CH_USED],
    const uint16_t *base_u16,
    const uint16_t *holdavg_u16,
    float *out_waveform,
    float *out_variance,
    float *out_mean) {
    if (!window_u16 || !base_u16 || !holdavg_u16 || !out_waveform || !out_variance || !out_mean) {
        return false;
    }
    compute_features_from_window_core(window_u16, base_u16, holdavg_u16, out_waveform, out_variance, out_mean);
    return true;
}
'''


# --- 2. Template for Industrial-grade Inference Engine ---
TEMPLATE_DETECT_H = '''#ifndef CNN_DETECT_H
#define CNN_DETECT_H
#define CNN_OUT_DIM {{NUM_CLASSES}}u
#include <stdbool.h>

typedef struct {
    float f1_out[128];
    float f2_z[64];
    float f2_out[64];
    float logits[CNN_OUT_DIM];
    float proba[CNN_OUT_DIM];
} cnn_detect_cache_t;

#ifdef __cplusplus
extern "C" {
#endif

int cnn_detect_init(void);
int cnn_detect_predict(const float *waveform_in, const float *variance_in, const float *mean_in, float *out_proba);
bool cnn_detect_forward_cache(const float *waveform_in, const float *variance_in, const float *mean_in, cnn_detect_cache_t *cache);
#ifdef __cplusplus
}
#endif
#endif
'''

TEMPLATE_DETECT_C = '''#include "cnn_detect.h"
#include "cnn_weights.h"
#include "cnn_features_lib.h"
#include "../app/sil_app_tinyol.h"
#include <stdlib.h>
#include <math.h>
#include <string.h>
#include <stdbool.h>

/* Static Workspaces to avoid heap exhaustion issues (Scaled by WIN_LEN) */
static float workspace_a[CNN_WIN_LEN * 64];
static float workspace_b[CNN_WIN_LEN * 64];

/* Helper: Leaky ReLU */
static void leaky_relu(float *data, int size, float alpha) {
    for (int i = 0; i < size; i++) if (data[i] < 0) data[i] *= alpha;
}

/* Helper: Sigmoid */
static float sigmoid(float x) {
    return 1.0f / (1.0f + expf(-x));
}

/* 1D Convolution with Same Padding - Optimized for 100Hz Performance */
static void conv1d_same_padding(const float *input, int input_len, int in_ch,
                               const float *weights, const float *bias,
                               int out_ch, int kernel_size, float *output) {
    int pad = kernel_size / 2;

    /* Optimized Loop: Spatial-First with sequential weight access */
    // 1. Initialize output with bias
    for (int i = 0; i < input_len; i++) {
        memcpy(&output[i * out_ch], bias, out_ch * sizeof(float));
    }

    // 2. Accumulate convolutions (Cache friendly oc-innermost loop)
    for (int i = 0; i < input_len; i++) {
        for (int k = 0; k < kernel_size; k++) {
            int idx = i + k - pad;
            if (idx >= 0 && idx < input_len) {
                for (int ic = 0; ic < in_ch; ic++) {
                    float in_val = input[idx * in_ch + ic];
                    const float *w_ptr = &weights[((k * in_ch + ic) * out_ch)];
                    float *out_ptr = &output[i * out_ch];
                    for (int oc = 0; oc < out_ch; oc++) {
                        out_ptr[oc] += in_val * w_ptr[oc];
                    }
                }
            }
        }
    }
}

/* SE Block: Global Average Pooling -> Dense -> ReLU -> Dense -> Sigmoid -> Multiply */
static void se_block(float *features, int seq_len, int channels,
                    const float *w1, const float *b1,
                    const float *w2, const float *b2) {
    float avg[128]; // Max channels expected
    for (int c = 0; c < channels; c++) {
        float sum = 0;
        for (int i = 0; i < seq_len; i++) sum += features[i * channels + c];
        avg[c] = sum / (float)seq_len;
    }

    int mid_ch = channels / 4;
    if (mid_ch < 1) mid_ch = 1;
    float mid[32]; // Max mid channels

    for (int oc = 0; oc < mid_ch; oc++) {
        float sum = b1[oc];
        for (int ic = 0; ic < channels; ic++) sum += avg[ic] * w1[ic * mid_ch + oc];
        mid[oc] = (sum > 0) ? sum : 0;
    }

    float scale[128];
    for (int oc = 0; oc < channels; oc++) {
        float sum = b2[oc];
        for (int ic = 0; ic < mid_ch; ic++) sum += mid[ic] * w2[ic * channels + oc];
        scale[oc] = sigmoid(sum);
    }

    for (int i = 0; i < seq_len; i++) {
        for (int c = 0; c < channels; c++) {
            features[i * channels + c] *= scale[c];
        }
    }
}

/* 1D Max Pooling */
static void maxpool1d(const float *input, int input_len, int channels, int pool_size, float *output) {
    int out_len = input_len / pool_size;
    for (int i = 0; i < out_len; i++) {
        for (int c = 0; c < channels; c++) {
            float max_v = -1e30f;
            for (int k = 0; k < pool_size; k++) {
                float v = input[(i * pool_size + k) * channels + c];
                if (v > max_v) max_v = v;
            }
            output[i * channels + c] = max_v;
        }
    }
}

int cnn_detect_init(void) {
    return 0;
}

bool cnn_detect_forward_cache(const float *waveform_in, const float *var_in, const float *mean_in, cnn_detect_cache_t *cache) {
    if (!waveform_in || !var_in || !mean_in || !cache) {
        return false;
    }
    // L1: Conv1D (WIN, CH) -> (WIN, 48) -> SE -> MaxPool(WIN/2, 48)
    int l1_len = (int)CNN_WIN_LEN;
    conv1d_same_padding(waveform_in, l1_len, (int)CNN_INPUT_CH_TOTAL, CONV1_W, CONV1_B, 48, 5, workspace_a);
    leaky_relu(workspace_a, l1_len * 48, 0.1f);
    se_block(workspace_a, l1_len, 48, CONV1_SE_SQ_W, CONV1_SE_SQ_B, CONV1_SE_EX_W, CONV1_SE_EX_B);
    maxpool1d(workspace_a, l1_len, 48, 2, workspace_b);
    int l1_out_len = l1_len / 2;

    // L2: Conv1D (L1_OUT, 48) -> (L1_OUT, 64) -> SE -> MaxPool(L1_OUT/2, 64)
    int l2_len = l1_out_len;
    conv1d_same_padding(workspace_b, l2_len, 48, CONV2_W, CONV2_B, 64, 3, workspace_a);
    leaky_relu(workspace_a, l2_len * 64, 0.1f);
    se_block(workspace_a, l2_len, 64, CONV2_SE_SQ_W, CONV2_SE_SQ_B, CONV2_SE_EX_W, CONV2_SE_EX_B);
    maxpool1d(workspace_a, l2_len, 64, 2, workspace_b);
    int l2_out_len = l2_len / 2;

    // Multi-Pooling: GAP + GMP (128 items)
    float pooled[128];
    for (int c = 0; c < 64; c++) {
        float sum = 0, max_v = -1e30f;
        for (int i = 0; i < l2_out_len; i++) {
            float v = workspace_b[i * 64 + c];
            sum += v; if (v > max_v) max_v = v;
        }
        pooled[c] = sum / (float)l2_out_len;
        pooled[64 + c] = max_v;
    }

    // Branch 2 & 3: Variance & Mean (32+32)
    float var_feat[32], mean_feat[32];
    for (int oc = 0; oc < 32; oc++) {
        float s_v = DENSE_VAR_B[oc];
        float s_m = DENSE_MEAN_B[oc];
        for (int ic = 0; ic < (int)CNN_CH_USED; ic++) {
            s_v += var_in[ic] * DENSE_VAR_W[ic * 32 + oc];
            s_m += mean_in[ic] * DENSE_MEAN_W[ic * 32 + oc];
        }
        var_feat[oc] = (s_v > 0) ? s_v : s_v * 0.1f;
        mean_feat[oc] = (s_m > 0) ? s_m : s_m * 0.1f;
    }

    // Concatenate [Pooled(128), Var(32), Mean(32)] -> 192
    float combined[192];
    memcpy(combined, pooled, 128 * sizeof(float));
    memcpy(combined + 128, var_feat, 32 * sizeof(float));
    memcpy(combined + 160, mean_feat, 32 * sizeof(float));

    // Bottleneck F1: 192 -> 128
    float f1_out[128];
    for (int oc = 0; oc < 128; oc++) {
        float sum = DENSE_F1_B[oc];
        for (int ic = 0; ic < 192; ic++) sum += combined[ic] * DENSE_F1_W[ic * 128 + oc];
        f1_out[oc] = (sum > 0) ? sum : sum * 0.1f;
    }

    // Bottleneck F2: 128 -> 64
    const float *dense_f2_w = SIL_APP_TINYOL_GetDenseF2Weights();
    const float *dense_f2_b = SIL_APP_TINYOL_GetDenseF2Bias();
    const float *dense_out_w = SIL_APP_TINYOL_GetDenseOutWeights();
    const float *dense_out_b = SIL_APP_TINYOL_GetDenseOutBias();
    for (int oc = 0; oc < 64; oc++) {
        float sum = dense_f2_b[oc];
        for (int ic = 0; ic < 128; ic++) sum += f1_out[ic] * dense_f2_w[ic * 64 + oc];
        cache->f2_z[oc] = sum;
        cache->f2_out[oc] = (sum > 0) ? sum : sum * 0.1f;
    }
    memcpy(cache->f1_out, f1_out, sizeof(f1_out));

    // Final Dense (Softmax Output): 64 -> CNN_OUT_DIM
    float max_score = -1e30f;
    for (int oc = 0; oc < (int)CNN_OUT_DIM; oc++) {
        float sum = dense_out_b[oc];
        for (int ic = 0; ic < 64; ic++) sum += cache->f2_out[ic] * dense_out_w[ic * CNN_OUT_DIM + oc];
        cache->logits[oc] = sum;
        if (sum > max_score) max_score = sum;
    }

    float exp_sum = 0;
    for (int i = 0; i < (int)CNN_OUT_DIM; i++) {
        cache->proba[i] = expf(cache->logits[i] - max_score);
        exp_sum += cache->proba[i];
    }
    for (int i = 0; i < (int)CNN_OUT_DIM; i++) cache->proba[i] /= exp_sum;
    return true;
}

int cnn_detect_predict(const float *waveform_in, const float *var_in, const float *mean_in, float *proba_out) {
    cnn_detect_cache_t cache;
    if (!cnn_detect_forward_cache(waveform_in, var_in, mean_in, &cache)) {
        return -1;
    }
    for (int i = 0; i < (int)CNN_OUT_DIM; i++) {
        proba_out[i] = cache.proba[i];
    }

    return 0;
}
'''


# --- 3. Templates for Post-processing (The Sophisticated Latching Version) ---
TEMPLATE_POST_H = '''#ifndef CNN_POSTPROCESS_H
#define CNN_POSTPROCESS_H

#include <stdint.h>
#include <stdbool.h>
#include "cnn_detect.h"

/* Default parameters based on UI backfill */
#define CNN_POST_ALPHA_DEFAULT     {{ALPHA}}f
#define CNN_POST_MARGIN_DEFAULT    {{MARGIN}}f
#define CNN_POST_EXIT_DEFAULT      0.25f

/* Tiered Validation Settings */
#define CNN_POST_STABLE_FAST       {{STABLE_FAST}}
#define CNN_POST_STABLE_NORMAL     {{STABLE_NORMAL}}
#define CNN_POST_STABLE_RESTRICTED {{STABLE_RESTRICTED}}

#define CNN_POST_THRESH_FAST       {{THRESH_FAST}}f
#define CNN_POST_THRESH_NORMAL     {{THRESH_NORMAL}}f
#define CNN_POST_THRESH_RESTRICTED {{THRESH_RESTRICTED}}f

typedef struct {
    float proba_smooth[CNN_OUT_DIM];
    int active_id;
    int last_best_id;
    uint32_t stable_count;
    uint32_t stable_threshold; 
} cnn_post_ctx_t;

void cnn_post_init(cnn_post_ctx_t *ctx);
void cnn_post_reset_buffer(cnn_post_ctx_t *ctx);
int cnn_post_update(cnn_post_ctx_t *ctx, const float *raw_proba);

#endif
'''

TEMPLATE_POST_C = '''#include "cnn_postprocess.h"
#include <string.h>

void cnn_post_init(cnn_post_ctx_t *ctx) {
    if (!ctx) return;
    cnn_post_reset_buffer(ctx);
}

void cnn_post_reset_buffer(cnn_post_ctx_t *ctx) {
    if (!ctx) return;
    for (int i = 0; i < (int)CNN_OUT_DIM; i++) ctx->proba_smooth[i] = 0.0f;
    ctx->active_id = -1;
    ctx->last_best_id = -1;
    ctx->stable_count = 0;
    ctx->stable_threshold = CNN_POST_STABLE_NORMAL;
}

static bool is_priority(int id) {
    return ({{PRIORITY_CHECK}});
}

static bool is_restricted(int id) {
    return ({{RESTRICTED_CHECK}});
}

int cnn_post_update(cnn_post_ctx_t *ctx, const float *raw_proba) {
    if (!ctx || !raw_proba) return -1;

    /* 1. Apply EWMA Smoothing to all classes and find best candidate */
    int best_id = -1;
    float max_smooth_val = 0.0f;
    for (int i = 0; i < (int)CNN_OUT_DIM; i++) {
        ctx->proba_smooth[i] = (CNN_POST_ALPHA_DEFAULT * raw_proba[i]) + (1.0f - CNN_POST_ALPHA_DEFAULT) * ctx->proba_smooth[i];
        if (ctx->proba_smooth[i] > max_smooth_val) {
            max_smooth_val = ctx->proba_smooth[i];
            best_id = i;
        }
    }

    /* 2. Force reset to convert if current active signal becomes too weak (Latch Exit) */
    if (ctx->active_id != -1) {
        if (ctx->proba_smooth[ctx->active_id] < CNN_POST_EXIT_DEFAULT) {
            ctx->active_id = -1;
        }
    }

    /* 3. Tiered Validation Logic (Instant for Priority, Stable for Normal) */
    if (best_id != -1 && best_id != ctx->active_id) {
        bool qual = false;

        bool priority_flag = is_priority(best_id);
        bool restricted_flag = is_restricted(best_id);

        if (priority_flag) {
            /* [TIER 1: FAST / HIGH PRIORITY] */
            if (best_id == ctx->last_best_id) {
                ctx->stable_count++;
            } else {
                ctx->stable_count = 1;
            }

            if (max_smooth_val >= CNN_POST_THRESH_FAST && ctx->stable_count > CNN_POST_STABLE_FAST) {
                qual = true;
            }
        } else {
            /* [TIER 2 & 3] Stability required */
            if (best_id == ctx->last_best_id) {
                ctx->stable_count++;
            } else {
                ctx->stable_count = 1;
            }

            if (restricted_flag) {
                /* [TIER 3: RESTRICTED] Strict validation */
                if (max_smooth_val >= CNN_POST_THRESH_RESTRICTED && ctx->stable_count >= CNN_POST_STABLE_RESTRICTED) {
                    qual = true;
                }
            } else if (max_smooth_val >= CNN_POST_THRESH_NORMAL) {
                /* [TIER 2: NORMAL] standard stability */
                if (ctx->stable_count >= CNN_POST_STABLE_NORMAL) {
                    qual = true;
                }
            }
        }

        /* 4. Switching Guard: Apply margin to prevent ID jitter */
        if (qual && ctx->active_id != -1) {
            float active_prob = ctx->proba_smooth[ctx->active_id];
            if (max_smooth_val < (active_prob + CNN_POST_MARGIN_DEFAULT)) {
                qual = false; 
            }
        }

        if (qual) {
            ctx->active_id = best_id;
            ctx->stable_count = 0;
        }
    } else if (best_id == ctx->active_id) {
        ctx->stable_count = 0;
    }

    ctx->last_best_id = best_id;
    return ctx->active_id;
}
'''

def _collect_tinyol_default_windows(meta, data_dir, log_fn, start_offset=30, max_tail_samples=270):
    id_to_name = meta.get("id_to_name", {}) or {}
    if not data_dir:
        return {}, [], []

    data_path = Path(data_dir)
    if not data_path.exists():
        return {}, [], []

    import pandas as pd

    window_len = int(meta.get("windowing", {}).get("window_len", 100))
    channels = [int(ch) for ch in meta.get("channels", [])]
    buckets = {int(k): [] for k in id_to_name}
    manifest = []
    prefix_to_label_id = {}
    for label_id, label_name in id_to_name.items():
        prefix_to_label_id[str(label_id).strip().lower()] = int(label_id)
        if label_name is not None:
            prefix_to_label_id[str(label_name).strip().lower()] = int(label_id)

    best_candidates = {}

    for csv_path in sorted(data_path.glob("*.csv")):
        prefix = csv_path.stem.split("-")[0].strip().lower()
        label_id = None
        if prefix in prefix_to_label_id:
            label_id = prefix_to_label_id[prefix]
        elif prefix.isdigit():
            label_id = int(prefix)
        if label_id is None:
            continue
        if id_to_name and label_id not in id_to_name:
            continue

        try:
            df = pd.read_csv(csv_path)
        except Exception as ex:
            log_fn(f"WARN: Failed to read default data CSV {csv_path}: {ex}")
            continue

        if df.empty or len(df) <= start_offset:
            continue

        if not channels:
            inferred = []
            for col in df.columns:
                if col.startswith("ROWCH"):
                    digits = re.sub(r"\D", "", col)
                    if digits:
                        inferred.append(int(digits))
            channels = sorted(set(inferred))
        if not channels:
            continue

        required_cols = [f"ROWCH{i}" for i in channels]
        if any(col not in df.columns for col in required_cols):
            continue

        usable_tail = min(len(df) - start_offset, int(max_tail_samples))
        if usable_tail < window_len:
            continue

        tail = df.iloc[start_offset:start_offset + usable_tail].copy()
        tail_vals = tail[required_cols].astype(float).to_numpy()
        if tail_vals.shape[0] < window_len:
            continue

        roughness = float(np.abs(np.diff(tail_vals, axis=0)).mean()) if tail_vals.shape[0] > 1 else float("inf")
        base_cols = [f"MOVBASE{i}" for i in channels if f"MOVBASE{i}" in tail.columns]
        hold_cols = [f"HOLDAVG{i}" for i in channels if f"HOLDAVG{i}" in tail.columns]
        base_var = float(tail[base_cols].astype(float).std(ddof=0).mean()) if base_cols else 0.0
        hold_var = float(tail[hold_cols].astype(float).std(ddof=0).mean()) if hold_cols else 0.0
        signal_var = float(tail_vals.std(ddof=0).mean())
        score = (
            round(roughness, 6),
            round(base_var, 6),
            round(hold_var, 6),
            round(signal_var, 6),
            -usable_tail,
            len(df),
            csv_path.name.lower(),
        )
        prev = best_candidates.get(label_id)
        if prev is None or score < prev["score"]:
            best_candidates[label_id] = {
                "score": score,
                "csv_path": csv_path,
                "df": df,
                "usable_tail": usable_tail,
                "roughness": roughness,
                "base_var": base_var,
                "hold_var": hold_var,
                "signal_var": signal_var,
                "required_cols": required_cols,
            }

    for label_id in sorted(best_candidates):
        cand = best_candidates[label_id]
        csv_path = cand["csv_path"]
        df = cand["df"]
        usable_tail = cand["usable_tail"]
        required_cols = cand["required_cols"]
        tail = df.iloc[start_offset:start_offset + usable_tail].copy()
        label_name = str(id_to_name.get(label_id, f"cl{label_id}"))
        tail["GESTURE"] = label_name
        tail["TARGET_ID"] = label_id
        if "SEQ" not in tail.columns:
            tail.insert(0, "SEQ", range(start_offset, start_offset + len(tail)))

        rows = tail[required_cols].astype(int).values.tolist()
        base = [int(tail.iloc[0].get(f"MOVBASE{i}", 0)) for i in channels]
        hold = [int(tail.iloc[0].get(f"HOLDAVG{i}", 0)) for i in channels]

        window_count = usable_tail // window_len
        if window_count <= 0:
            continue
        start_positions = [idx * window_len for idx in range(window_count)]

        for win_idx, start_pos in enumerate(start_positions):
            win_rows = rows[start_pos:start_pos + window_len]
            if len(win_rows) != window_len:
                continue
            buckets.setdefault(label_id, []).append({
                "rows": win_rows,
                "base": base,
                "hold": hold,
                "source_csv": str(csv_path),
                "window_index": win_idx,
                "tail_rows": usable_tail,
            })

        log_fn(
            f"INFO: Default data label={label_id} file={csv_path.name} "
            f"roughness={cand['roughness']:.3f} base_var={cand['base_var']:.3f} "
            f"hold_var={cand['hold_var']:.3f} tail_rows={usable_tail} "
            f"windows={len(buckets.get(label_id, []))}"
        )
        manifest.append({
            "label_id": label_id,
            "label_name": label_name,
            "source_csv": str(csv_path),
            "tail_rows_used": usable_tail,
            "roughness": round(cand["roughness"], 6),
            "base_var": round(cand["base_var"], 6),
            "hold_var": round(cand["hold_var"], 6),
            "window_count": len(buckets.get(label_id, [])),
            "window_step": window_len,
            "window_mode": "non_overlap",
        })

    return buckets, channels, manifest


def _render_tinyol_windows_files(out_dir, file_prefix, header_guard, buckets, channels, window_len, manifest, manifest_name, log_fn):
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    header_path = out_path / f"{file_prefix}.h"
    source_path = out_path / f"{file_prefix}.c"
    manifest_path = out_path / manifest_name

    lines_h = [
        f"#ifndef {header_guard}",
        f"#define {header_guard}",
        "",
        "#include <stdint.h>",
        "",
        "#define TINYOL_DEFAULT_SHARED_BASE_HOLD 1",
        f"#define TINYOL_DEFAULT_WINDOW_LEN {int(window_len)}",
        f"#define TINYOL_DEFAULT_CHANNEL_COUNT {len(channels)}",
        "",
    ]
    lines_c = [f'#include "{file_prefix}.h"', ""]

    for label_id in sorted(buckets):
        samples = buckets[label_id]
        if not samples:
            continue

        count = len(samples)
        lines_h.append(f"#define TINYOL_DEFAULT_CLS_{label_id}_COUNT {count}")
        lines_h.append(
            f"extern const uint16_t tinyol_default_cls_{label_id}_windows[TINYOL_DEFAULT_CLS_{label_id}_COUNT][TINYOL_DEFAULT_WINDOW_LEN][TINYOL_DEFAULT_CHANNEL_COUNT];"
        )
        lines_h.append(
            f"extern const uint16_t tinyol_default_cls_{label_id}_base[TINYOL_DEFAULT_CHANNEL_COUNT];"
        )
        lines_h.append(
            f"extern const uint16_t tinyol_default_cls_{label_id}_hold[TINYOL_DEFAULT_CHANNEL_COUNT];"
        )
        lines_h.append("")

        win_rows = []
        base_rows = []
        hold_rows = []
        for sample in samples:
            row_text = ",\n        ".join("{" + ", ".join(str(int(v)) for v in row) + "}" for row in sample["rows"])
            win_rows.append("    {\n        " + row_text + "\n    }")
            base_rows.append("    {" + ", ".join(str(int(v)) for v in sample["base"]) + "}")
            hold_rows.append("    {" + ", ".join(str(int(v)) for v in sample["hold"]) + "}")

        lines_c.append(
            f"const uint16_t tinyol_default_cls_{label_id}_windows[TINYOL_DEFAULT_CLS_{label_id}_COUNT][TINYOL_DEFAULT_WINDOW_LEN][TINYOL_DEFAULT_CHANNEL_COUNT] = {{"
        )
        lines_c.append(",\n".join(win_rows))
        lines_c.append("};\n")
        lines_c.append(
            f"const uint16_t tinyol_default_cls_{label_id}_base[TINYOL_DEFAULT_CHANNEL_COUNT] = {{"
        )
        lines_c.append("    " + ", ".join(str(int(v)) for v in samples[0]["base"]))
        lines_c.append("};\n")
        lines_c.append(
            f"const uint16_t tinyol_default_cls_{label_id}_hold[TINYOL_DEFAULT_CHANNEL_COUNT] = {{"
        )
        lines_c.append("    " + ", ".join(str(int(v)) for v in samples[0]["hold"]))
        lines_c.append("};\n")

    lines_h.append("#endif")
    header_path.write_text("\n".join(lines_h), encoding="utf-8")
    source_path.write_text("\n".join(lines_c), encoding="utf-8")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    log_fn(f"OK: Default TinyOL data written to {header_path.name}, {source_path.name}")
    return str(header_path), str(source_path), str(manifest_path)


def generate_cnn_lib(out_dir, tflite_path, std_base_a, std_hold_a, meta_path, model_path=None, data_dir=None, log_fn=None, post_cfg=None):
    if log_fn is None: log_fn = print
    def _log(msg): log_fn(f"[GEN_CNN] {msg}")

    os.makedirs(out_dir, exist_ok=True)
    
    # --- Load Metadata ---
    meta = {}
    if meta_path and os.path.exists(meta_path):
        try:
            import joblib
            meta = joblib.load(meta_path)
            _log(f"OK: Loaded Metadata from {meta_path}")
        except Exception:
            try:
                import pickle
                with open(meta_path, 'rb') as f:
                    meta = pickle.load(f)
                _log(f"OK: Loaded Metadata via pickle")
            except Exception as e:
                _log(f"ERROR: Failed to load meta: {e}")
                return False
    else:
        _log(f"ERROR: Meta file not found: {meta_path}")
        return False

    win_len = meta.get('windowing', {}).get('window_len', 55)
    chs_used = len(meta.get('channels', [0,1,2,3,4]))
    infer_stride = post_cfg.get('infer_stride', 3) if post_cfg else 3
    
    id_to_name = meta.get('id_to_name', {})
    num_classes = meta.get('num_classes', len(id_to_name))
    gesture_names = [id_to_name.get(i, f"cl{i}") for i in range(num_classes)]
    
    _log(f"Config: WIN={win_len}, CH={chs_used}, STRIDE={infer_stride}, CLASSES={num_classes}")

    # --- Backfill Parameters from UI ---
    pcfg = post_cfg or {
        'alpha': 0.20, 'margin': 0.45, 'thresh_entry': 0.50, 
        'stable_normal': 10, 'stable_restricted': 20, 
        'thresh_priority': 0.70, 'thresh_restricted': 0.75,
        'priority_ids': [0, 1, 2, 3, 4, 5, 6], 'restricted_ids': []
    }
    
    # Priority check logic for C
    priority_check = " || ".join([f"id == {i}" for i in pcfg['priority_ids']]) if pcfg['priority_ids'] else "false"
    restricted_check = " || ".join([f"id == {i}" for i in pcfg['restricted_ids']]) if pcfg['restricted_ids'] else "false"

    # Fill Templates
    features_h = TEMPLATE_FEATURES_H.replace("{{WIN_LEN}}", str(win_len)) \
                                     .replace("{{CH_USED}}", str(chs_used)) \
                                     .replace("{{INFER_STRIDE}}", str(infer_stride)) \
                                     .replace("{{SLOPE_FACTOR}}", f"{pcfg.get('slope_factor', 20.0):.2f}")
                                     
    features_c = TEMPLATE_FEATURES_C.replace("{{WIN_LEN}}", str(win_len)) \
                                     .replace("{{CH_USED}}", str(chs_used))

    # Inference engine threshold should be loose (0.40f) to allow post-processor to filter
    detect_c = TEMPLATE_DETECT_C.replace("{{THRESHOLD}}", "0.40")
    detect_h = TEMPLATE_DETECT_H.replace("{{NUM_CLASSES}}", str(num_classes))

    post_h = TEMPLATE_POST_H.replace("{{ALPHA}}", f"{pcfg['alpha']:.2f}") \
                             .replace("{{MARGIN}}", f"{pcfg['margin']:.2f}") \
                             .replace("{{STABLE_FAST}}", str(pcfg.get('stable_fast', 0))) \
                             .replace("{{STABLE_NORMAL}}", str(pcfg['stable_normal'])) \
                             .replace("{{STABLE_RESTRICTED}}", str(pcfg['stable_restricted'])) \
                             .replace("{{THRESH_FAST}}", f"{pcfg.get('thresh_priority', 0.70):.2f}") \
                             .replace("{{THRESH_NORMAL}}", f"{pcfg.get('thresh_entry', 0.50):.2f}") \
                             .replace("{{THRESH_RESTRICTED}}", f"{pcfg['thresh_restricted']:.2f}")

    post_c = TEMPLATE_POST_C.replace("{{PRIORITY_CHECK}}", priority_check) \
                             .replace("{{RESTRICTED_CHECK}}", restricted_check)

    # --- Auto-Export Weights ---
    if model_path and os.path.exists(model_path):
        try:
            import export_weights_v2
            import importlib
            importlib.reload(export_weights_v2)
            export_weights_v2.export_cnn_weights(model_path, os.path.join(out_dir, "cnn_weights.h"))
            _log("OK: Weights exported.")
        except Exception as ex:
            _log(f"WARN: Weight export failed: {ex}")

    tinyol_default_paths = {}
    tinyol_buckets, tinyol_channels, tinyol_manifest = _collect_tinyol_default_windows(
        meta=meta,
        data_dir=data_dir,
        log_fn=_log,
        start_offset=30,
    )
    if tinyol_manifest and tinyol_buckets:
        tinyol_window_len = int(meta.get("windowing", {}).get("window_len", 100))
        header_path, source_path, manifest_path = _render_tinyol_windows_files(
            out_dir=out_dir,
            file_prefix="tinyol_default_windows",
            header_guard="TINYOL_DEFAULT_WINDOWS_H",
            buckets=tinyol_buckets,
            channels=tinyol_channels or [0, 1, 2, 3, 4, 5],
            window_len=tinyol_window_len,
            manifest=tinyol_manifest,
            manifest_name="tinyol_default_manifest.json",
            log_fn=_log,
        )
        tinyol_default_paths = {
            "header_path": header_path,
            "source_path": source_path,
            "manifest_path": manifest_path,
        }
    elif data_dir:
        _log(f"WARN: TinyOL default data export skipped (no usable CSV windows found in {data_dir}).")
    
    # --- Write Files ---
    files_to_write = {
        "cnn_detect.c": detect_c,
        "cnn_detect.h": detect_h,
        "cnn_model_data.c": (
            '#include "cnn_model_data.h"\n'
            '#include <stddef.h>\n'
            f'const uint16_t STD_BASELINE_A_U16[{len(std_base_a)}] = {{ {", ".join(map(str, std_base_a))} }};\n'
            f'const uint16_t STD_HOLDAVG_A_U16[{len(std_hold_a)}] = {{ {", ".join(map(str, std_hold_a))} }};\n'
            'const char* const CNN_GESTURE_NAMES[CNN_OUT_DIM] = {\n'
            + "".join([f'    "{n}",\n' for n in gesture_names])
            + "};\n"
        ),
        "cnn_model_data.h": (
            '#ifndef CNN_MODEL_DATA_H\n'
            '#define CNN_MODEL_DATA_H\n'
            '#include <stdint.h>\n'
            '#include "cnn_detect.h"\n'
            f'extern const uint16_t STD_BASELINE_A_U16[{len(std_base_a)}];\n'
            f'extern const uint16_t STD_HOLDAVG_A_U16[{len(std_hold_a)}];\n'
            'extern const char* const CNN_GESTURE_NAMES[CNN_OUT_DIM];\n'
            '#endif\n'
        ),
        "cnn_features_lib.c": features_c,
        "cnn_features_lib.h": features_h,
        "cnn_postprocess.c": post_c,
        "cnn_postprocess.h": post_h
    }

    for filename, content in files_to_write.items():
        with open(os.path.join(out_dir, filename), "w") as f:
            f.write(content)
            
    total_files = len(files_to_write) + (3 if tinyol_default_paths else 0)
    _log(f"SUCCESS: Generated {total_files} files in {out_dir}")
    result = {"out_dir": out_dir}
    if tinyol_default_paths:
        result["tinyol_default"] = tinyol_default_paths
    return result

if __name__ == "__main__":
    generate_cnn_lib(".", None, [0]*6, [0]*6, "gesture_model_meta_v5.pkl")
