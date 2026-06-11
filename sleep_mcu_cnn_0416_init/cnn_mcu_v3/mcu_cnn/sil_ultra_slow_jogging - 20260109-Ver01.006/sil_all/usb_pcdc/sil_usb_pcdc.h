#ifndef SIL_USB_PCDC_H
#define SIL_USB_PCDC_H

#include "hal_data.h"

#define USB_READ_BUF_SIZE    (512U)
#define NUM_STRING_DESCRIPTOR (7U)

typedef enum {
    SIL_USB_TYPE_PCDC,
    SIL_USB_TYPE_PHID
} sil_usb_type_t;

/* API Function Declarations */
fsp_err_t SIL_USB_Open(sil_usb_type_t type);
fsp_err_t SIL_USB_PCDC_Open(void);
void SIL_USB_PCDC_EventPoll(void);
fsp_err_t SIL_USB_PCDC_Write(uint8_t *p_buf, uint32_t len);
bool SIL_USB_PCDC_IsConnected(void);

void SIL_USB_PHID_SendString(const char *str);
void SIL_USB_PHID_Process(void);
void SIL_USB_PHID_KeyScan(void);

#endif // SIL_USB_PCDC_H
