#include "sil_app_ds.h"
#include "../usb_pcdc/sil_usb_pcdc.h"
#include "../app/sil_app_touch.h"
#include "../globals/sil_globals.h"
#include "../protocol_atcmds/sil_atcmds.h"

// Key scancodes
#define KEY_UP    (0x52U)
#define KEY_DOWN  (0x51U)
#define KEY_LEFT  (0x50U)
#define KEY_RIGHT (0x4FU)
#define KEY_SPACE (0x2CU)

// Thresholds
#define THRESH_PRESS    (16500U)
#define THRESH_RELEASE  (16000U)

// Active states
static bool g_key_up_active = false;
static bool g_key_down_active = false;
static bool g_key_left_active = false;
static bool g_key_right_active = false;

extern usb_ctrl_t * gp_usb_ctrl;
extern volatile bool g_hid_write_complete;

fsp_err_t SIL_APP_DS_Enter1(void) {
    return FSP_SUCCESS;
}

fsp_err_t SIL_APP_DS_Enter2(void) {
    g_key_up_active = false;
    g_key_down_active = false;
    g_key_left_active = false;
    g_key_right_active = false;
    return FSP_SUCCESS;
}

void SIL_APP_DS_MainLoop1(void) {
}

void SIL_APP_DS_MainLoop2(void) {
    static uint8_t last_report[8] = {0};
    static uint32_t last_scan_time = 0;
    static bool last_key_up_active = false;
    static bool last_key_down_active = false;
    static bool last_key_left_active = false;
    static bool last_key_right_active = false;
    
    uint32_t current_time = SIL_DTC_RESET_GetMs();
    if (current_time - last_scan_time < 20) // Limit scanning to 50Hz (every 20ms)
    {
        return;
    }
    last_scan_time = current_time;
    
    if (!SIL_USB_PCDC_IsConnected())
    {
        return;
    }
    
    // Read raw touch channel data (6 channels in Glove mode)
    uint16_t raw_data[6] = {0};
    SIL_APP_TOUCH_GetAllChannelsDataGlove(raw_data, 6);
    
    // CH2 -> DOWN
    if (raw_data[1] > THRESH_PRESS) g_key_down_active = true;
    else if (raw_data[1] < THRESH_RELEASE) g_key_down_active = false;
    
    // CH3 -> UP
    if (raw_data[2] > THRESH_PRESS) g_key_up_active = true;
    else if (raw_data[2] < THRESH_RELEASE) g_key_up_active = false;
    
    // CH4 -> LEFT
    if (raw_data[3] > THRESH_PRESS) g_key_left_active = true;
    else if (raw_data[3] < THRESH_RELEASE) g_key_left_active = false;
    
    // CH5 -> RIGHT
    if (raw_data[4] > THRESH_PRESS) g_key_right_active = true;
    else if (raw_data[4] < THRESH_RELEASE) g_key_right_active = false;
    
    // Build report
    uint8_t current_report[8] = {0};
    uint8_t key_idx = 2; // key scancodes start from report byte 2
    
    if (g_key_up_active) current_report[key_idx++] = KEY_UP;
    if (g_key_down_active) current_report[key_idx++] = KEY_DOWN;
    
    // CH4 (LEFT) + CH5 (RIGHT) simultaneously pressed -> Spacebar
    if (g_key_left_active && g_key_right_active)
    {
        current_report[key_idx++] = KEY_SPACE;
    }
    else
    {
        if (g_key_left_active) current_report[key_idx++] = KEY_LEFT;
        if (g_key_right_active) current_report[key_idx++] = KEY_RIGHT;
    }
    
    // Compare with last sent report
    if (memcmp(current_report, last_report, 8) != 0)
    {
        /* DS mode BLE gesture sync: send on press edge only (UART6 / TOBLE). */
        if (g_key_down_active && !last_key_down_active)
            SIL_ATCMDS_SendSilGesture(ATCMDS_IO_TOBLE, "DOWN");
        if (g_key_up_active && !last_key_up_active)
            SIL_ATCMDS_SendSilGesture(ATCMDS_IO_TOBLE, "UP");
        if (g_key_left_active && !last_key_left_active)
            SIL_ATCMDS_SendSilGesture(ATCMDS_IO_TOBLE, "LEFT");
        if (g_key_right_active && !last_key_right_active)
            SIL_ATCMDS_SendSilGesture(ATCMDS_IO_TOBLE, "RIGHT");

        if (g_hid_write_complete)
        {
            g_hid_write_complete = false;
            fsp_err_t err = R_USB_Write(gp_usb_ctrl, current_report, 8, USB_CLASS_PHID);
            if (FSP_SUCCESS == err)
            {
                memcpy(last_report, current_report, 8);
            }
            else
            {
                g_hid_write_complete = true;
            }
        }
    }

    last_key_up_active = g_key_up_active;
    last_key_down_active = g_key_down_active;
    last_key_left_active = g_key_left_active;
    last_key_right_active = g_key_right_active;
}

void SIL_APP_DS_Exit(void) {
}
