#ifndef CNN_DETECT_H
#define CNN_DETECT_H
#define CNN_OUT_DIM 12u
#ifdef __cplusplus
extern "C" {
#endif
int cnn_detect_init(void);
int cnn_detect_predict(const float *waveform_in, const float *variance_in, const float *mean_in, float *out_proba);
#ifdef __cplusplus
}
#endif
#endif
