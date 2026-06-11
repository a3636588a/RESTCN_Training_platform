#include "cnn_model_data.h"
#include <stddef.h>
const uint16_t STD_BASELINE_A_U16[6] = { 15342, 15211, 15495, 15194, 15288, 16102 };
const uint16_t STD_HOLDAVG_A_U16[6] = { 35342, 35211, 35495, 35194, 35288, 36102 };
const char* const CNN_GESTURE_NAMES[CNN_OUT_DIM] = {
    "0",
    "1",
    "2",
    "3",
    "4",
};
