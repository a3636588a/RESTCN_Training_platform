#include "cnn_detect.h"
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

/* 1D Convolution with Same Padding - 優化版 (100Hz 目標) */
static void conv1d_same_padding(const float *input, int input_len, int in_ch,
                               const float *weights, const float *bias,
                               int out_ch, int kernel_size, float *output) {
    int pad = kernel_size / 2;

    /* --- 新邏輯：空間優先與快取優化 (Cache Optimization) --- */
    /* 將 oc (輸出通道) 移至最內層循環，因為權重在記憶體中 oc 是連續存放的 */
    /* 這能讓 CPU 進入連讀模式，大幅提升 100Hz 運算效率 */

    // 1. 初始化輸出為 Bias 
    for (int i = 0; i < input_len; i++) {
        memcpy(&output[i * out_ch], bias, out_ch * sizeof(float));
    }

    // 2. 執行卷積累加
    for (int i = 0; i < input_len; i++) {
        for (int k = 0; k < kernel_size; k++) {
            int idx = i + k - pad;
            if (idx >= 0 && idx < input_len) {
                for (int ic = 0; ic < in_ch; ic++) {
                    float in_val = input[idx * in_ch + ic];
                    // 核心優化：權重指針連續偏移
                    const float *w_ptr = &weights[((k * in_ch + ic) * out_ch)];
                    float *out_ptr = &output[i * out_ch];
                    for (int oc = 0; oc < out_ch; oc++) {
                        out_ptr[oc] += in_val * w_ptr[oc];
                    }
                }
            }
        }
    }

    /* --- 舊邏輯 (已註解)：Filter優先 (快取命中率低) --- */
    /*
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
    */
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
