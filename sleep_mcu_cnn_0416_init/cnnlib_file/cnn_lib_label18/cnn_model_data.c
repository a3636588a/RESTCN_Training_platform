#include "cnn_model_data.h"
#include <stddef.h>
const uint16_t STD_BASELINE_A_U16[6] = { 15299, 15400, 15217, 15358, 15490, 15285 };
const uint16_t STD_HOLDAVG_A_U16[6] = { 35299, 35400, 35217, 35358, 35490, 35285 };
const char* const CNN_GESTURE_NAMES[CNN_OUT_DIM] = {
    "Turn_left",
    "Turn_right",
    "Getout_of_bed",
    "lying_down",
    "Lying_left",
    "Lying_right",
    "Raising_right_hand",
    "Raising_left_hand",
    "Raising_right_foot",
    "Raising_left_foot",
    "put_feet_up",
    "Get_up",
};
