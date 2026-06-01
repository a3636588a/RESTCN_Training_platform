#include "cnn_model_data.h"
#include <stddef.h>
const uint16_t STD_BASELINE_A_U16[6] = { 15405, 15350, 15337, 15405, 15386, 15348 };
const uint16_t STD_HOLDAVG_A_U16[6] = { 35405, 35350, 35337, 35405, 35386, 35348 };
const char* const CNN_GESTURE_NAMES[CNN_OUT_DIM] = {
    "Turn left",
    "Turn right",
    "Getting out of bed",
    "lying down",
    "Lying on left side",
    "Lying on right side",
};
