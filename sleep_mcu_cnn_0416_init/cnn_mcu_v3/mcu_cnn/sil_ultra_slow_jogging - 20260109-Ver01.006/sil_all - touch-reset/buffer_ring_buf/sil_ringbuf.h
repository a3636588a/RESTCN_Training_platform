#ifndef SIL_RINGBUF_H
#define SIL_RINGBUF_H

#include "..\globals\sil_globals.h"
#include <stdbool.h>

/*
#if defined(__ICCARM__)

void R_BSP_WarmStart(bsp_warm_start_event_t event);

 #pragma weak R_BSP_WarmStart

#elif defined(__GNUC__) || defined(__ARMCC_VERSION)

void R_BSP_WarmStart(bsp_warm_start_event_t event) __attribute__((weak));

#endif
// */

#define SILCNTS_RINGBUF_SIZE_DEFAULT 512

typedef struct SIL_RINGBUF_S {
	bool initialized;
	uint8_t a_buf[SILCNTS_RINGBUF_SIZE_DEFAULT];
	uint16_t len;
	uint32_t head;
	uint32_t tail;
	uint16_t count;
} sil_ringbuf_s;


// public func.

// Initialize the ring buffer
void SIL_RINGBUF_Init(sil_ringbuf_s *rb);
void SIL_RINGBUF_Deinit(sil_ringbuf_s *rb);
// get data length
uint16_t SIL_RINGBUF_GetDataLength(sil_ringbuf_s *rb);


// Add an element to the buffer
bool SIL_RINGBUF_Enqueue(sil_ringbuf_s *rb, uint8_t data);
// Remove an element from the buffer
bool SIL_RINGBUF_Dequeue(sil_ringbuf_s *rb, uint8_t *data);
// empty all 
void SIL_RINGBUF_Flush(sil_ringbuf_s *rb);





























#endif //#ifndef SIL_RINGBUF_H
