// dynamic_feature.h
#pragma once
#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

#define DYN_MAX_TOKENS 64   // 足夠覆蓋 7s window（你現在很安全）

typedef struct {
    uint16_t tok[DYN_MAX_TOKENS];
    uint32_t ts[DYN_MAX_TOKENS];   // timestamp in ms
    uint16_t count;               // valid tokens
    int16_t  last_tok;             // for de-dup
    uint32_t last_trigger_ms;      // cooldown control
} dyn_ctx_t;

/* init once */
void dyn_init(dyn_ctx_t* ctx);

/*
 * Feed ONLY when stable gesture changes (same as PC)
 * return true if a dynamic gesture is triggered
 * out_name points to g_dyn_gestures[i].name
 */
bool dyn_feed(dyn_ctx_t* ctx,
              int16_t stable_id,
              uint32_t now_ms,
              const char** out_name);

#ifdef __cplusplus
}
#endif
