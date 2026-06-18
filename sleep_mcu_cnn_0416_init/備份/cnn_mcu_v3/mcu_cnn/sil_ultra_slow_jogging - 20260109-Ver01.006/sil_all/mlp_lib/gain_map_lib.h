#pragma once
#include <stdint.h>
#include <stdbool.h>

#ifndef GAIN_CHN
#define GAIN_CHN 6u
#endif

#define RELEASE_EVAL_N 3u

typedef struct
{
    float g[GAIN_CHN];
    bool  ready;

    float   rel_hist[GAIN_CHN][RELEASE_EVAL_N];
    uint8_t rel_len[GAIN_CHN];
    uint8_t rel_idx[GAIN_CHN];
} gain_map_t;

void  gainmap_init(gain_map_t *gm);
bool  gainmap_is_ready(const gain_map_t *gm);
float gainmap_get(const gain_map_t *gm, uint8_t ch);

bool gainmap_update_from_holdavg(gain_map_t *gm,
                                 const uint16_t holdavg_b[GAIN_CHN],
                                 const uint16_t movbase_b[GAIN_CHN]);

bool gainmap_tune_from_release(gain_map_t *gm,
                               const uint16_t rel_avg[GAIN_CHN],
                               const uint16_t movbase_b[GAIN_CHN]);

uint16_t gainmap_apply_row_u16(const gain_map_t *gm,
                               uint8_t ch,
                               uint16_t row,
                               uint16_t movbase);
