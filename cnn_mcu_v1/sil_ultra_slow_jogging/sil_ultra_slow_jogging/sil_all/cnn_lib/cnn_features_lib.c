#include "cnn_features_lib.h"
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

    static float window_dn[CNN_CH_USED][60];
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
