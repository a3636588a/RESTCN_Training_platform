#include "majority_chain.h"

#include <string.h>

void majority_chain_reset(majority_chain_t *c)
{
    if (!c) return;
    memset(c->buf, 0, sizeof(c->buf));
    c->len = 0;
    c->head = 0;
    c->current = -1;
}

void majority_chain_update(
    majority_chain_t *c,
    uint8_t pred,
    int8_t *out_state,
    bool *out_changed)
{
    if (!c)
    {
        if (out_state) *out_state = -1;
        if (out_changed) *out_changed = false;
        return;
    }

    // push into ring
    c->buf[c->head] = pred;
    c->head = (uint8_t)((c->head + 1u) % MAJ_CHAIN_LEN);
    if (c->len < MAJ_CHAIN_LEN)
    {
        c->len++;
    }

    if (c->len < MAJ_CHAIN_MIN_MAJ)
    {
        if (out_state) *out_state = -1;
        if (out_changed) *out_changed = false;
        return;
    }

    // count
    uint8_t cnt[MAJ_MAX_CLASSES];
    memset(cnt, 0, sizeof(cnt));
    for (uint8_t i = 0; i < c->len; i++)
    {
        uint8_t v = c->buf[i];
        if (v < MAJ_MAX_CLASSES)
        {
            cnt[v]++;
        }
    }

    // most common
    uint8_t best_lbl = 0;
    uint8_t best_n = 0;
    for (uint8_t i = 0; i < MAJ_MAX_CLASSES; i++)
    {
        if (cnt[i] > best_n)
        {
            best_n = cnt[i];
            best_lbl = i;
        }
    }

    bool changed = false;
    if ((best_n >= MAJ_CHAIN_MIN_MAJ) && ((int8_t)best_lbl != c->current))
    {
        c->current = (int8_t)best_lbl;
        changed = true;
    }

    if (out_state) *out_state = c->current;
    if (out_changed) *out_changed = changed;
}
