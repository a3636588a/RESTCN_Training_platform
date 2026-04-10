#ifndef CNN_FEATURES_LIB_H
#define CNN_FEATURES_LIB_H

#include <stdint.h>
#include <stdbool.h>

#define CNN_WIN_LEN      60u
#define CNN_CH_USED       5u
#define CNN_INFER_STRIDE  3u
#define CNN_SLOPE_FACTOR  30.00f

/* CNN Input Dimensions (Level + Slope) */
#define CNN_INPUT_CH_LEVEL   5
#define CNN_INPUT_CH_SLOPE   5
#define CNN_INPUT_CH_TOTAL   (CNN_INPUT_CH_LEVEL + CNN_INPUT_CH_SLOPE)

/* Auxiliary Input Dimensions */
#define CNN_AUX_VAR_DIM      5

typedef struct {
    uint16_t row_buf[CNN_CH_USED][60];
    uint16_t base_buf[CNN_CH_USED][60];
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
