import os
import sys
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
'''


# --- 2. Template for Industrial-grade Inference Engine ---
TEMPLATE_DETECT_C = '''#include "cnn_detect.h"
#include "cnn_weights.h"
#include "cnn_features_lib.h"
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

/* 1D Convolution with Same Padding */
static void conv1d_same_padding(const float *input, int input_len, int in_ch,
                               const float *weights, const float *bias,
                               int out_ch, int kernel_size, float *output) {
    int pad = kernel_size / 2;
    for (int oc = 0; oc < out_ch; oc++) {
        for (int i = 0; i < input_len; i++) {
            float sum = bias[oc];
            for (int k = 0; k < kernel_size; k++) {
                int idx = i + k - pad;
                if (idx >= 0 && idx < input_len) {
                    for (int ic = 0; ic < in_ch; ic++) {
                        sum += input[idx * in_ch + ic] * weights[((k * in_ch + ic) * out_ch) + oc];
                    }
                }
            }
            output[i * out_ch + oc] = sum;
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

int cnn_detect_predict(const float *waveform_in, const float *var_in, const float *mean_in, float *proba_out) {
    // L1: Conv1D (WIN, CH) -> (WIN, 32) -> SE -> MaxPool(WIN/2, 32)
    int l1_len = (int)CNN_WIN_LEN;
    conv1d_same_padding(waveform_in, l1_len, (int)CNN_INPUT_CH_TOTAL, CONV1_W, CONV1_B, 32, 5, workspace_a);
    leaky_relu(workspace_a, l1_len * 32, 0.1f);
    se_block(workspace_a, l1_len, 32, CONV1_SE_SQ_W, CONV1_SE_SQ_B, CONV1_SE_EX_W, CONV1_SE_EX_B);
    maxpool1d(workspace_a, l1_len, 32, 2, workspace_b);
    int l1_out_len = l1_len / 2;

    // L2: Conv1D (L1_OUT, 32) -> (L1_OUT, 64) -> SE -> MaxPool(L1_OUT/2, 64)
    int l2_len = l1_out_len;
    conv1d_same_padding(workspace_b, l2_len, 32, CONV2_W, CONV2_B, 64, 3, workspace_a);
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
    float f2_out[64];
    for (int oc = 0; oc < 64; oc++) {
        float sum = DENSE_F2_B[oc];
        for (int ic = 0; ic < 128; ic++) sum += f1_out[ic] * DENSE_F2_W[ic * 64 + oc];
        f2_out[oc] = (sum > 0) ? sum : sum * 0.1f;
    }

    // Final Dense (Softmax Output): 64 -> CNN_OUT_DIM
    float scores[CNN_OUT_DIM];
    float max_score = -1e30f;
    for (int oc = 0; oc < (int)CNN_OUT_DIM; oc++) {
        float sum = DENSE_OUT_B[oc];
        for (int ic = 0; ic < 64; ic++) sum += f2_out[ic] * DENSE_OUT_W[ic * CNN_OUT_DIM + oc];
        scores[oc] = sum;
        if (sum > max_score) max_score = sum;
    }

    float exp_sum = 0;
    for (int i = 0; i < (int)CNN_OUT_DIM; i++) {
        scores[i] = expf(scores[i] - max_score);
        exp_sum += scores[i];
    }
    for (int i = 0; i < (int)CNN_OUT_DIM; i++) proba_out[i] = scores[i] / exp_sum;

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

def generate_cnn_lib(out_dir, tflite_path, std_base_a, std_hold_a, meta_path, model_path=None, log_fn=None, post_cfg=None):
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
    infer_stride = post_cfg.get('infer_stride', 10) if post_cfg else 10
    
    id_to_name = meta.get('id_to_name', {})
    num_classes = meta.get('num_classes', len(id_to_name))
    gesture_names = [id_to_name.get(i, f"cl{i}") for i in range(num_classes)]
    
    _log(f"Config: WIN={win_len}, CH={chs_used}, STRIDE={infer_stride}, CLASSES={num_classes}")

    # --- Backfill Parameters from UI ---
    pcfg = post_cfg or {
        'alpha': 0.60, 'margin': 0.05, 'thresh_entry': 0.50, 
        'stable_normal': 10, 'stable_restricted': 20, 
        'thresh_priority': 0.70, 'thresh_restricted': 0.75,
        'priority_ids': [14, 15, 5, 10, 11, 0], 'restricted_ids': [1, 2, 13]
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
    
    # --- Write Files ---
    files_to_write = {
        "cnn_detect.c": detect_c,
        "cnn_detect.h": f"#ifndef CNN_DETECT_H\n#define CNN_DETECT_H\n#define CNN_OUT_DIM {num_classes}u\n#ifdef __cplusplus\nextern \"C\" {{\n#endif\nint cnn_detect_init(void);\nint cnn_detect_predict(const float *waveform_in, const float *variance_in, const float *mean_in, float *out_proba);\n#ifdef __cplusplus\n}}\n#endif\n#endif\n",
        "cnn_model_data.c": f'#include "cnn_model_data.h"\n#include <stddef.h>\nconst uint16_t STD_BASELINE_A_U16[6] = {{ {", ".join(map(str, std_base_a))} }};\nconst uint16_t STD_HOLDAVG_A_U16[6] = {{ {", ".join(map(str, std_hold_a))} }};\nconst char* const CNN_GESTURE_NAMES[CNN_OUT_DIM] = {{\n' + "".join([f'    "{n}",\n' for n in gesture_names]) + "};\n",
        "cnn_model_data.h": '#ifndef CNN_MODEL_DATA_H\n#define CNN_MODEL_DATA_H\n#include <stdint.h>\n#include "cnn_detect.h"\nextern const uint16_t STD_BASELINE_A_U16[6];\nextern const uint16_t STD_HOLDAVG_A_U16[6];\nextern const char* const CNN_GESTURE_NAMES[CNN_OUT_DIM];\n#endif\n',
        "cnn_features_lib.c": features_c,
        "cnn_features_lib.h": features_h,
        "cnn_postprocess.c": post_c,
        "cnn_postprocess.h": post_h
    }

    for filename, content in files_to_write.items():
        with open(os.path.join(out_dir, filename), "w") as f:
            f.write(content)
            
    _log(f"SUCCESS: Generated 8 Industrial CNN files in {out_dir}")
    return True

if __name__ == "__main__":
    generate_cnn_lib(".", None, [0]*6, [0]*6, "gesture_model_meta_v5.pkl")
