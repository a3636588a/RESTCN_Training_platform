#include "sil_filter_mdn.h"
#include <stdlib.h>

// sorting data
void SIL_FILTER_MDN_BubbleSort(uint16_t *dat, uint8_t size) {
	
	uint8_t i, j;
	uint16_t temp;
	
    for (i = 0; i < (size - 1); i++) {
        for (j = 0; j < (size - i - 1); j++) {
            if (dat[j] > dat[j + 1]) {
                
				temp = dat[j];
                dat[j] = dat[j + 1];
                dat[j + 1] = temp;
				
            }
        }
    }
}

uint16_t SIL_FILTER_MDN_GetFiltered(uint16_t *window, uint8_t size) {
    SIL_FILTER_MDN_BubbleSort(window, size);
    return window[size / 2];
}






