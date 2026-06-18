#include "cnn_model_data.h"
#include <stddef.h>
const uint16_t STD_BASELINE_A_U16[CNN_CH_USED] = { 15374, 15391, 15334, 15370, 15339 };
const uint16_t STD_HOLDAVG_A_U16[CNN_CH_USED] = { 16941, 18938, 18921, 19132, 16512 };
const char* const CNN_GESTURE_NAMES[CNN_OUT_DIM] = {
    "0",
    "1",
    "2",
    "3",
    "4",
    "5",
    "6",
};
