/*
 * dynamic_feature.c
 *
 *  Created on: 2026年1月29日
 *      Author: USE
 */
// dynamic_feature.c
#include "dynamic_feature.h"
#include "dynamic_model.h"
#include <string.h>

/* ---------------- internal helpers ---------------- */

static void trim_by_time(dyn_ctx_t* ctx, uint32_t now_ms)
{
    while (ctx->count > 0)
    {
        uint32_t dt = now_ms - ctx->ts[0];
        if (dt <= g_dyn_global_max_time_window_ms)
            break;

        // shift left
        memmove(&ctx->tok[0], &ctx->tok[1], (ctx->count - 1) * sizeof(uint16_t));
        memmove(&ctx->ts[0],  &ctx->ts[1],  (ctx->count - 1) * sizeof(uint32_t));
        ctx->count--;
    }
}

/* PC-style: total gap allowance */
static bool match_with_gap(const uint16_t* seq,
                           uint16_t seq_len,
                           const uint16_t* target,
                           uint16_t target_len,
                           uint16_t max_gap)
{
    uint16_t i = 0;
    uint16_t gaps = 0;

    for (uint16_t t = 0; t < target_len; t++)
    {
        uint16_t want = target[t];

        while (i < seq_len && seq[i] != want)
        {
            i++;
            gaps++;
            if (gaps > max_gap)
                return false;
        }

        if (i >= seq_len)
            return false;

        i++; // consume match
    }
    return true;
}

/* ---------------- public API ---------------- */

void dyn_init(dyn_ctx_t* ctx)
{
    memset(ctx, 0, sizeof(*ctx));
    ctx->last_tok = -1;
}

bool dyn_feed(dyn_ctx_t* ctx,
              int16_t stable_id,
              uint32_t now_ms,
              const char** out_name)
{
    *out_name = NULL;

    /* PC behavior: de-dup */
    if (stable_id == ctx->last_tok)
        return false;

    ctx->last_tok = stable_id;

    /* append token */
    if (ctx->count < DYN_MAX_TOKENS)
    {
        ctx->tok[ctx->count] = (uint16_t)stable_id;
        ctx->ts[ctx->count]  = now_ms;
        ctx->count++;
    }
    else
    {
        /* drop oldest */
        memmove(&ctx->tok[0], &ctx->tok[1], (DYN_MAX_TOKENS - 1) * sizeof(uint16_t));
        memmove(&ctx->ts[0],  &ctx->ts[1],  (DYN_MAX_TOKENS - 1) * sizeof(uint32_t));
        ctx->tok[DYN_MAX_TOKENS - 1] = (uint16_t)stable_id;
        ctx->ts[DYN_MAX_TOKENS - 1]  = now_ms;
    }

    /* trim by time window */
    trim_by_time(ctx, now_ms);

    /* cooldown (global, same as PC matcher) */
    if ((now_ms - ctx->last_trigger_ms) < 1000u)
        return false;

    /* try match: LONGER sequence first (array already sorted) */
    for (uint16_t g = 0; g < g_dyn_gestures_count; g++)
    {
        const dyn_gesture_t* dg = &g_dyn_gestures[g];

        if (ctx->count < dg->seq_len)
            continue;

        /* sliding window */
        for (uint16_t start = 0; start + dg->seq_len <= ctx->count; start++)
        {
            uint32_t t_start = ctx->ts[start];
            uint32_t t_end   = ctx->ts[start + dg->seq_len - 1];

            if ((t_end - t_start) > dg->time_window_ms)
                continue;

            const uint16_t* sub = &ctx->tok[start];
            const uint16_t* target = &g_dyn_seq_tokens[dg->seq_off];

            if (match_with_gap(sub,
                               ctx->count - start,
                               target,
                               dg->seq_len,
                               dg->max_gap))
            {
                ctx->last_trigger_ms = now_ms;
                *out_name = dg->name;
                // ✅ 清空，避免同一串序列被重複掃到
                ctx->count = 0;
                ctx->last_tok = -1;
                return true;
            }
        }
    }

    return false;
}
