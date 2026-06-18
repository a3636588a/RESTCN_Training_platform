#ifndef TINYOL_MCU_LAYOUT_EXAMPLE_H
#define TINYOL_MCU_LAYOUT_EXAMPLE_H

#include <stdint.h>

#define TINYOL_LABEL_COUNT 9
#define TINYOL_WINDOW_LEN 100
#define TINYOL_CHANNEL_COUNT 6

#define TINYOL_LABEL1_COUNT 2
#define TINYOL_LABEL2_COUNT 2
#define TINYOL_LABEL3_COUNT 2
#define TINYOL_LABEL4_COUNT 2
#define TINYOL_LABEL5_COUNT 2
#define TINYOL_LABEL6_COUNT 2
#define TINYOL_LABEL7_COUNT 2
#define TINYOL_LABEL8_COUNT 2
#define TINYOL_LABEL9_COUNT 2

extern const uint16_t tinyol_label1_windows[TINYOL_LABEL1_COUNT][TINYOL_WINDOW_LEN][TINYOL_CHANNEL_COUNT];
extern const uint16_t tinyol_label2_windows[TINYOL_LABEL2_COUNT][TINYOL_WINDOW_LEN][TINYOL_CHANNEL_COUNT];
extern const uint16_t tinyol_label3_windows[TINYOL_LABEL3_COUNT][TINYOL_WINDOW_LEN][TINYOL_CHANNEL_COUNT];
extern const uint16_t tinyol_label4_windows[TINYOL_LABEL4_COUNT][TINYOL_WINDOW_LEN][TINYOL_CHANNEL_COUNT];
extern const uint16_t tinyol_label5_windows[TINYOL_LABEL5_COUNT][TINYOL_WINDOW_LEN][TINYOL_CHANNEL_COUNT];
extern const uint16_t tinyol_label6_windows[TINYOL_LABEL6_COUNT][TINYOL_WINDOW_LEN][TINYOL_CHANNEL_COUNT];
extern const uint16_t tinyol_label7_windows[TINYOL_LABEL7_COUNT][TINYOL_WINDOW_LEN][TINYOL_CHANNEL_COUNT];
extern const uint16_t tinyol_label8_windows[TINYOL_LABEL8_COUNT][TINYOL_WINDOW_LEN][TINYOL_CHANNEL_COUNT];
extern const uint16_t tinyol_label9_windows[TINYOL_LABEL9_COUNT][TINYOL_WINDOW_LEN][TINYOL_CHANNEL_COUNT];

extern const uint16_t tinyol_label1_base[TINYOL_LABEL1_COUNT][TINYOL_CHANNEL_COUNT];
extern const uint16_t tinyol_label2_base[TINYOL_LABEL2_COUNT][TINYOL_CHANNEL_COUNT];
extern const uint16_t tinyol_label3_base[TINYOL_LABEL3_COUNT][TINYOL_CHANNEL_COUNT];
extern const uint16_t tinyol_label4_base[TINYOL_LABEL4_COUNT][TINYOL_CHANNEL_COUNT];
extern const uint16_t tinyol_label5_base[TINYOL_LABEL5_COUNT][TINYOL_CHANNEL_COUNT];
extern const uint16_t tinyol_label6_base[TINYOL_LABEL6_COUNT][TINYOL_CHANNEL_COUNT];
extern const uint16_t tinyol_label7_base[TINYOL_LABEL7_COUNT][TINYOL_CHANNEL_COUNT];
extern const uint16_t tinyol_label8_base[TINYOL_LABEL8_COUNT][TINYOL_CHANNEL_COUNT];
extern const uint16_t tinyol_label9_base[TINYOL_LABEL9_COUNT][TINYOL_CHANNEL_COUNT];

extern const uint16_t tinyol_label1_hold[TINYOL_LABEL1_COUNT][TINYOL_CHANNEL_COUNT];
extern const uint16_t tinyol_label2_hold[TINYOL_LABEL2_COUNT][TINYOL_CHANNEL_COUNT];
extern const uint16_t tinyol_label3_hold[TINYOL_LABEL3_COUNT][TINYOL_CHANNEL_COUNT];
extern const uint16_t tinyol_label4_hold[TINYOL_LABEL4_COUNT][TINYOL_CHANNEL_COUNT];
extern const uint16_t tinyol_label5_hold[TINYOL_LABEL5_COUNT][TINYOL_CHANNEL_COUNT];
extern const uint16_t tinyol_label6_hold[TINYOL_LABEL6_COUNT][TINYOL_CHANNEL_COUNT];
extern const uint16_t tinyol_label7_hold[TINYOL_LABEL7_COUNT][TINYOL_CHANNEL_COUNT];
extern const uint16_t tinyol_label8_hold[TINYOL_LABEL8_COUNT][TINYOL_CHANNEL_COUNT];
extern const uint16_t tinyol_label9_hold[TINYOL_LABEL9_COUNT][TINYOL_CHANNEL_COUNT];

#endif
