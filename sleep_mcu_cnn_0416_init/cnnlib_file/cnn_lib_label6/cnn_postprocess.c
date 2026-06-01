#include "cnn_postprocess.h"
#include <string.h>

void cnn_post_init(cnn_post_ctx_t *ctx) {
    if (!ctx) return;
    cnn_post_reset_buffer(ctx);
}

void cnn_post_reset_buffer(cnn_post_ctx_t *ctx) {
    if (!ctx) return;
    for (int i = 0; i < (int)CNN_OUT_DIM; i++) ctx->proba_smooth[i] = 0.0f;
    ctx->active_id = -1;
    ctx->last_best_id = -1;
    ctx->stable_count = 0;
    ctx->stable_threshold = CNN_POST_STABLE_NORMAL;
}

static bool is_priority(int id) {
    return (id == 0 || id == 1 || id == 3);
}

static bool is_restricted(int id) {
    return (false);
}

int cnn_post_update(cnn_post_ctx_t *ctx, const float *raw_proba) {
    if (!ctx || !raw_proba) return -1;

    /* 1. Apply EWMA Smoothing to all classes and find best candidate */
    int best_id = -1;
    float max_smooth_val = 0.0f;
    for (int i = 0; i < (int)CNN_OUT_DIM; i++) {
        ctx->proba_smooth[i] = (CNN_POST_ALPHA_DEFAULT * raw_proba[i]) + (1.0f - CNN_POST_ALPHA_DEFAULT) * ctx->proba_smooth[i];
        if (ctx->proba_smooth[i] > max_smooth_val) {
            max_smooth_val = ctx->proba_smooth[i];
            best_id = i;
        }
    }

    /* 2. Force reset to convert if current active signal becomes too weak (Latch Exit) */
    if (ctx->active_id != -1) {
        if (ctx->proba_smooth[ctx->active_id] < CNN_POST_EXIT_DEFAULT) {
            ctx->active_id = -1;
        }
    }

    /* 3. Tiered Validation Logic (Instant for Priority, Stable for Normal) */
    if (best_id != -1 && best_id != ctx->active_id) {
        bool qual = false;

        bool priority_flag = is_priority(best_id);
        bool restricted_flag = is_restricted(best_id);

        if (priority_flag) {
            /* [TIER 1: FAST / HIGH PRIORITY] */
            if (best_id == ctx->last_best_id) {
                ctx->stable_count++;
            } else {
                ctx->stable_count = 1;
            }

            if (max_smooth_val >= CNN_POST_THRESH_FAST && ctx->stable_count > CNN_POST_STABLE_FAST) {
                qual = true;
            }
        } else {
            /* [TIER 2 & 3] Stability required */
            if (best_id == ctx->last_best_id) {
                ctx->stable_count++;
            } else {
                ctx->stable_count = 1;
            }

            if (restricted_flag) {
                /* [TIER 3: RESTRICTED] Strict validation */
                if (max_smooth_val >= CNN_POST_THRESH_RESTRICTED && ctx->stable_count >= CNN_POST_STABLE_RESTRICTED) {
                    qual = true;
                }
            } else if (max_smooth_val >= CNN_POST_THRESH_NORMAL) {
                /* [TIER 2: NORMAL] standard stability */
                if (ctx->stable_count >= CNN_POST_STABLE_NORMAL) {
                    qual = true;
                }
            }
        }

        /* 4. Switching Guard: Apply margin to prevent ID jitter */
        if (qual && ctx->active_id != -1) {
            float active_prob = ctx->proba_smooth[ctx->active_id];
            if (max_smooth_val < (active_prob + CNN_POST_MARGIN_DEFAULT)) {
                qual = false; 
            }
        }

        if (qual) {
            ctx->active_id = best_id;
            ctx->stable_count = 0;
        }
    } else if (best_id == ctx->active_id) {
        ctx->stable_count = 0;
    }

    ctx->last_best_id = best_id;
    return ctx->active_id;
}
