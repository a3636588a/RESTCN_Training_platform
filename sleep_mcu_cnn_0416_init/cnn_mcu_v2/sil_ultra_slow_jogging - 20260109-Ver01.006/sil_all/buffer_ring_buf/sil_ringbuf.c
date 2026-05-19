#include "sil_ringbuf.h"
#include <stdlib.h>

// ring buffer functions
// Initialize the ring buffer
void SIL_RINGBUF_Init(sil_ringbuf_s *rb) {

	if (rb) {
		memset(rb, 0x00, sizeof(sil_ringbuf_s));
		rb->len = SILCNTS_RINGBUF_SIZE_DEFAULT;
		//memset(rb->a_buf, 0x00, rb->len * sizeof(uint8_t));
		rb->count = 0;
		rb->initialized = true;
	}
}

void SIL_RINGBUF_Deinit(sil_ringbuf_s *rb) {

	if ((rb) && (rb->initialized)) memset(rb, 0x00, sizeof(sil_ringbuf_s));
}

// get data length
uint16_t SIL_RINGBUF_GetDataLength(sil_ringbuf_s *rb) {

	uint16_t len = 0;

	if ((rb) && (rb->initialized)) {
		len = rb->count;
	}
	
	return len;

}

// get data length
void SIL_RINGBUF_Flush(sil_ringbuf_s *rb) {

	if (rb) {
		rb->head = 0;
		rb->tail = 0;
		rb->count = 0;

		memset(rb->a_buf, 0x00, rb->len);
	}
}

// Add an element to the buffer
bool SIL_RINGBUF_Enqueue(sil_ringbuf_s *rb, uint8_t data) {

	volatile uint8_t *d1 = (uint8_t *) rb->a_buf;

	if (rb) {
	    if (rb->count >= rb->len) {
	        SIL_RINGBUF_Flush(rb);
	    }

		d1[rb->head] = data;
		rb->head = (rb->head + 1) % rb->len;
		rb->count ++;
		return true;
	}
	return false;
}

// Remove an element from the buffer
bool SIL_RINGBUF_Dequeue(sil_ringbuf_s *rb, uint8_t *data) {
    volatile uint8_t *d1 = (uint8_t *) rb->a_buf;

	if (rb) {
		if ((rb->count == 0) || (rb->count >= rb->len)) {
			SIL_RINGBUF_Flush(rb);
			return false;
		}
		
		*data = d1[rb->tail];
		
		rb->tail = (rb->tail + 1) % rb->len;
		rb->count --;
		
		return true;

	}
	
	return  false;
}

