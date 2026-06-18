#ifndef CNN_DETECT_H
#define CNN_DETECT_H
#define CNN_OUT_DIM 7u

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
