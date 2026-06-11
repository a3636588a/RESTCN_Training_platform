#pragma once

#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

#ifndef MAJ_CHAIN_LEN
#define MAJ_CHAIN_LEN     (1u)
#endif

#ifndef MAJ_CHAIN_MIN_MAJ
#define MAJ_CHAIN_MIN_MAJ (1u)
#endif

#ifndef MAJ_MAX_CLASSES
#define MAJ_MAX_CLASSES   (32u) // must be >= your num classes (18)
#endif

typedef struct
{
    uint8_t buf[MAJ_CHAIN_LEN];
    uint8_t len;        // current filled length
    uint8_t head;       // next write index
    int8_t  current;    // current stable label, -1 = unknown
} majority_chain_t;

void majority_chain_reset(majority_chain_t *c);

// Update with new prediction. Returns:
// - out_state: current state after update (or -1 if not enough data)
// - out_changed: true only when state changes (same as Python MajorityChain.update)
void majority_chain_update(
    majority_chain_t *c,
    uint8_t pred,
    int8_t *out_state,
    bool *out_changed
);

#ifdef __cplusplus
}
#endif
