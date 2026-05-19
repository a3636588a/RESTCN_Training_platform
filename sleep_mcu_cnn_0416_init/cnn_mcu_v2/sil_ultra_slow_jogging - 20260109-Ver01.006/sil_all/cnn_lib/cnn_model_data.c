#include "cnn_model_data.h"
#include <stddef.h>
const uint16_t STD_BASELINE_A_U16[6] = { 15348, 15248, 15163, 15396, 15443, 15443 };
const uint16_t STD_HOLDAVG_A_U16[6] = { 35348, 35248, 35163, 35396, 35443, 35443 };
const char* const CNN_GESTURE_NAMES[CNN_OUT_DIM] = {
    "Turn_left",
    "Turn_right",
    "Getout_of_bed",
    "lying_down",
    "Lying_left",
    "Lying_right",
    "Raising_right_foot",
    "Raising_left_foot",
    "Get_up",
};
