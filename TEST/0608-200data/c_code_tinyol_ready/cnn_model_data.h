#ifndef CNN_MODEL_DATA_H
#define CNN_MODEL_DATA_H
#include <stdint.h>
#include "cnn_features_lib.h"
#include "cnn_detect.h"
extern const uint16_t STD_BASELINE_A_U16[CNN_CH_USED];
extern const uint16_t STD_HOLDAVG_A_U16[CNN_CH_USED];
extern const char* const CNN_GESTURE_NAMES[CNN_OUT_DIM];
#endif
