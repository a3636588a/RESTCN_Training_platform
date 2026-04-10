#include "cnn_model_data.h"
#include <stddef.h>
const uint16_t STD_BASELINE_A_U16[6] = { 15475, 15293, 15383, 15360, 15299, 15228 };
const uint16_t STD_HOLDAVG_A_U16[6] = { 17275, 20308, 20071, 20077, 17761, 15242 };
const char* const CNN_GESTURE_NAMES[CNN_OUT_DIM] = {
    "0",
    "1",
    "2",
    "3",
    "4",
    "5",
    "6",
    "7",
    "8",
    "9",
    "ok",
    "good",
    "fuck",
    "sucku",
    "sos",
    "catch",
};
