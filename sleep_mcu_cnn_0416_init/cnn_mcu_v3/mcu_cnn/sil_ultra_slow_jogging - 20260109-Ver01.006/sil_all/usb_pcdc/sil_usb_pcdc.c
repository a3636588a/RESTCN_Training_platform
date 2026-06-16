#include <string.h>
#include <stdio.h>
#include "sil_usb_pcdc.h"
#include "r_usb_basic.h"
#include "r_usb_basic_api.h"
#include "r_usb_pcdc_api.h"
#include "r_usb_phid_api.h"
#include "r_flash_hp.h"
#include "r_flash_api.h"
#include "../app/sil_app_type.h"
#include "r_ioport.h"

/* Extern references to descriptors and flash instance */
extern const usb_descriptor_t g_usb_descriptor_pcdc;
extern const usb_descriptor_t g_usb_descriptor_phid;
extern const uint8_t g_apl_report_phid[];
extern uint8_t g_apl_configuration_phid[];

extern flash_hp_instance_ctrl_t g_flash0_ctrl;
extern const flash_cfg_t g_flash0_cfg;

extern ioport_instance_ctrl_t g_ioport_ctrl;
extern const ioport_instance_t g_ioport;

extern sil_app_type_e gsil_globals_current_app;

/* Global active descriptor structure referenced by ra_gen/hal_data.c */
usb_descriptor_t g_usb_descriptor = {0};

/* Active USB controller control block pointer */
usb_ctrl_t * gp_usb_ctrl = &g_basic0_ctrl;

/* Line coding configuration block for USB virtual COM port setup */
#define LINE_CODING_LENGTH            (0x07U)
static usb_pcdc_linecoding_t        g_line_coding;

/* State variables */
static volatile bool                g_usb_connected = false;
static volatile bool                g_usb_write_complete = true;
static uint8_t                      g_usb_read_buf[USB_READ_BUF_SIZE];

/* OTA engine state variables matching user's ota_usb_ui.py */
static bool                         g_ota_active = false;
static uint32_t                     g_ota_expected_size = 0;
static uint32_t                     g_ota_write_addr = 0x00078000;
static uint32_t                     g_ota_received_bytes = 0;
static uint32_t                     g_ota_last_prog = 0;

#define OTA_TEMP_BUF_SIZE           (2048U)
static uint8_t                      g_ota_temp_buf[OTA_TEMP_BUF_SIZE];
static uint32_t                     g_ota_temp_count = 0;

/* --- PHID Simulated Keyboard State Variables --- */
typedef enum {
    SEND_STATE_IDLE,
    SEND_STATE_KEY_DOWN,
    SEND_STATE_WAIT_KEY_DOWN,
    SEND_STATE_KEY_UP,
    SEND_STATE_WAIT_KEY_UP
} send_state_t;

static send_state_t                 g_send_state = SEND_STATE_IDLE;
static char                         g_send_buffer[32] = {0};
static uint8_t                      g_send_len = 0;
static uint8_t                      g_send_idx = 0;
volatile bool                g_hid_write_complete = true;
static uint8_t                      g_hid_report_data[8] = {0};
static uint8_t                      g_hid_null_report[8] = {0};
static uint16_t                     g_numlock = 0;
static uint8_t                      g_idle = 0;

#define ALIGN_VAL                     (4U)
#define CD_LENGTH                     (18U)
#define USB_RECEIVE_REPORT_DESCRIPTOR (76U)
#define USB_RECEIVE_HID_DESCRIPTOR    (9U)
#define IDLE_VAL_INDEX                (1U)
#define SIZE_NUM                      (2U)

static uint8_t                      send_data_align[16] BSP_ALIGN_VARIABLE(ALIGN_VAL);

/* Extern functions */
extern fsp_err_t SIL_UART_DTC_TOPC_WriteToTxBuffer(uint8_t *p_buf, uint16_t len);
extern uint32_t SIL_DTC_RESET_GetMs(void);

/**
 * @brief CRC32 Calculation Helper.
 */
static uint32_t calculate_crc32(const uint8_t *data, size_t len)
{
    uint32_t crc = 0xFFFFFFFF;
    for (size_t i = 0; i < len; i++)
    {
        crc ^= data[i];
        for (int j = 0; j < 8; j++)
        {
            if (crc & 1)
            {
                crc = (crc >> 1) ^ 0xEDB88320;
            }
            else
            {
                crc >>= 1;
            }
        }
    }
    return ~crc;
}

/**
 * @brief Initialize and open the USB driver instance dynamically by type.
 */
fsp_err_t SIL_USB_Open(sil_usb_type_t type)
{
    fsp_err_t err = FSP_SUCCESS;
    
    // Drop pull-up/ensure controller is closed first
    R_USB_Close(&g_basic0_ctrl);
    R_USB_Close(&g_basic1_ctrl);
    
    // Hardware disconnect debounce delay (100ms) to let PC register disconnect
    R_BSP_SoftwareDelay(100, BSP_DELAY_UNITS_MILLISECONDS);
    
    g_usb_connected = false;
    g_usb_write_complete = true;
    g_hid_write_complete = true;
    g_send_state = SEND_STATE_IDLE;
    g_ota_active = false;
    g_ota_temp_count = 0;
    memset(g_usb_read_buf, 0, sizeof(g_usb_read_buf));
    memset(g_hid_report_data, 0, sizeof(g_hid_report_data));
    memset(g_hid_null_report, 0, sizeof(g_hid_null_report));
    
    if (type == SIL_USB_TYPE_PCDC)
    {
        g_usb_descriptor = g_usb_descriptor_pcdc;
        gp_usb_ctrl = &g_basic0_ctrl;
        err = R_USB_Open(&g_basic0_ctrl, &g_basic0_cfg);
    }
    else // SIL_USB_TYPE_PHID
    {
        g_usb_descriptor = g_usb_descriptor_phid;
        gp_usb_ctrl = &g_basic1_ctrl;
        
        /* Configure S1 (P005) and S2 (P004) as GPIO Input with pull-up enabled to bypass Disabled default in configuration.xml */
        R_IOPORT_PinCfg(&g_ioport_ctrl, BSP_IO_PORT_00_PIN_05, IOPORT_CFG_PORT_DIRECTION_INPUT | IOPORT_CFG_PULLUP_ENABLE);
        R_IOPORT_PinCfg(&g_ioport_ctrl, BSP_IO_PORT_00_PIN_04, IOPORT_CFG_PORT_DIRECTION_INPUT | IOPORT_CFG_PULLUP_ENABLE);
        
        err = R_USB_Open(&g_basic1_ctrl, &g_basic1_cfg);
    }

    /* Debug log to SCI UART console */
    char dbg_buf[64];
    int dbg_len = snprintf(dbg_buf, sizeof(dbg_buf), "[USB Open] Type: %d, err: 0x%X\r\n", (int)type, (unsigned int)err);
    SIL_UART_DTC_TOPC_WriteToTxBuffer((uint8_t *)dbg_buf, (uint16_t)dbg_len);

    return err;
}

/**
 * @brief Legacy initializer wrapper selecting USB type based on current app.
 */
fsp_err_t SIL_USB_PCDC_Open(void)
{
    if (gsil_globals_current_app == SIL_APP_DS_E)
    {
        return SIL_USB_Open(SIL_USB_TYPE_PHID);
    }
    else
    {
        return SIL_USB_Open(SIL_USB_TYPE_PCDC);
    }
}

/**
 * @brief Get the current USB connection state.
 */
bool SIL_USB_PCDC_IsConnected(void)
{
    return g_usb_connected;
}

/**
 * @brief Send raw data to the Host over the virtual COM port (CDC class).
 */
fsp_err_t SIL_USB_PCDC_Write(uint8_t *p_buf, uint32_t len)
{
    if (!g_usb_connected)
    {
        return FSP_ERR_NOT_OPEN;
    }
    
    /* Wait for previous write operation to finish (poll USB events while waiting) */
    uint32_t timeout = 5000000;
    while (!g_usb_write_complete && timeout > 0)
    {
        SIL_USB_PCDC_EventPoll();
        timeout--;
    }
    
    g_usb_write_complete = false;
    fsp_err_t err = R_USB_Write(gp_usb_ctrl, p_buf, len, USB_CLASS_PCDC);
    if (FSP_SUCCESS != err)
    {
        g_usb_write_complete = true;
    }
    return err;
}

/**
 * @brief Convert ASCII characters to standard USB HID Keyboard Scancodes.
 */
static bool char_to_usb_keycode(char c, uint8_t *p_keycode, uint8_t *p_modifier)
{
    *p_modifier = 0; // Default: no modifier
    
    if (c >= 'a' && c <= 'z')
    {
        *p_keycode = (uint8_t)(0x04 + (c - 'a'));
        return true;
    }
    if (c >= 'A' && c <= 'Z')
    {
        *p_keycode = (uint8_t)(0x04 + (c - 'A'));
        *p_modifier = 0x02; // Left Shift
        return true;
    }
    if (c >= '1' && c <= '9')
    {
        *p_keycode = (uint8_t)(0x1E + (c - '1'));
        return true;
    }
    if (c == '0')
    {
        *p_keycode = 0x27;
        return true;
    }
    if (c == '_')
    {
        *p_keycode = 0x2D;   // '-' key with shift is underscore '_'
        *p_modifier = 0x02;  // Left Shift
        return true;
    }
    if (c == ' ')
    {
        *p_keycode = 0x2C;   // Spacebar
        return true;
    }
    return false;
}

/**
 * @brief Trigger simulated keyboard input string.
 */
void SIL_USB_PHID_SendString(const char *str)
{
    if (!g_usb_connected)
    {
        return;
    }
    if (g_send_state != SEND_STATE_IDLE)
    {
        return; /* Busy sending another string */
    }
    
    strncpy(g_send_buffer, str, sizeof(g_send_buffer) - 1);
    g_send_buffer[sizeof(g_send_buffer) - 1] = '\0';
    g_send_len = (uint8_t)strlen(g_send_buffer);
    g_send_idx = 0;
    g_send_state = SEND_STATE_KEY_DOWN;
    
    char log_buf[64];
    int len = snprintf(log_buf, sizeof(log_buf), "[USB KeySim] Start string: %s\r\n", g_send_buffer);
    SIL_UART_DTC_TOPC_WriteToTxBuffer((uint8_t *)log_buf, (uint16_t)len);
}

/**
 * @brief Process simulated keyboard string state machine.
 */
void SIL_USB_PHID_Process(void)
{
    if (!g_usb_connected)
    {
        return;
    }
    
    fsp_err_t err = FSP_SUCCESS;
    switch (g_send_state)
    {
        case SEND_STATE_IDLE:
            break;
            
        case SEND_STATE_KEY_DOWN:
        {
            if (g_hid_write_complete)
            {
                uint8_t keycode = 0;
                uint8_t modifier = 0;
                char c = g_send_buffer[g_send_idx];
                
                if (char_to_usb_keycode(c, &keycode, &modifier))
                {
                    memset(g_hid_report_data, 0, sizeof(g_hid_report_data));
                    g_hid_report_data[0] = modifier;
                    g_hid_report_data[2] = keycode;
                    
                    g_hid_write_complete = false;
                    err = R_USB_Write(gp_usb_ctrl, g_hid_report_data, 8, USB_CLASS_PHID);
                    if (FSP_SUCCESS == err)
                    {
                        g_send_state = SEND_STATE_WAIT_KEY_DOWN;
                    }
                    else
                    {
                        g_hid_write_complete = true;
                        g_send_state = SEND_STATE_IDLE;
                    }
                }
                else
                {
                    /* Unmapped char, skip it */
                    g_send_idx++;
                    if (g_send_idx >= g_send_len)
                    {
                        g_send_state = SEND_STATE_IDLE;
                    }
                }
            }
            break;
        }
        
        case SEND_STATE_WAIT_KEY_DOWN:
        {
            if (g_hid_write_complete)
            {
                g_send_state = SEND_STATE_KEY_UP;
            }
            break;
        }
        
        case SEND_STATE_KEY_UP:
        {
            if (g_hid_write_complete)
            {
                g_hid_write_complete = false;
                err = R_USB_Write(gp_usb_ctrl, g_hid_null_report, 8, USB_CLASS_PHID);
                if (FSP_SUCCESS == err)
                {
                    g_send_state = SEND_STATE_WAIT_KEY_UP;
                }
                else
                {
                    g_hid_write_complete = true;
                    g_send_state = SEND_STATE_IDLE;
                }
            }
            break;
        }
        
        case SEND_STATE_WAIT_KEY_UP:
        {
            if (g_hid_write_complete)
            {
                g_send_idx++;
                if (g_send_idx < g_send_len)
                {
                    g_send_state = SEND_STATE_KEY_DOWN;
                }
                else
                {
                    g_send_state = SEND_STATE_IDLE;
                    SIL_UART_DTC_TOPC_WriteToTxBuffer((uint8_t *)"[USB KeySim] Completed\r\n", 24);
                }
            }
            break;
        }
    }
}

/**
 * @brief Scan S1 (P005) and S2 (P004) hardware buttons with software debounce.
 */
void SIL_USB_PHID_KeyScan(void)
{
    static uint32_t last_scan_tick = 0;
    static bsp_io_level_t last_s1_state = BSP_IO_LEVEL_HIGH;
    static bsp_io_level_t last_s2_state = BSP_IO_LEVEL_HIGH;
    
    uint32_t current_tick = SIL_DTC_RESET_GetMs();
    if (current_tick - last_scan_tick < 20)
    {
        return;
    }
    last_scan_tick = current_tick;
    
    bsp_io_level_t s1_level = BSP_IO_LEVEL_HIGH;
    bsp_io_level_t s2_level = BSP_IO_LEVEL_HIGH;
    
    R_IOPORT_PinRead(&g_ioport_ctrl, BSP_IO_PORT_00_PIN_05, &s1_level);
    R_IOPORT_PinRead(&g_ioport_ctrl, BSP_IO_PORT_00_PIN_04, &s2_level);
    
    /* Detect falling edge (button pressed down) */
    if (last_s1_state == BSP_IO_LEVEL_HIGH && s1_level == BSP_IO_LEVEL_LOW)
    {
        SIL_USB_PHID_SendString("input_s1");
    }
    last_s1_state = s1_level;
    
    if (last_s2_state == BSP_IO_LEVEL_HIGH && s2_level == BSP_IO_LEVEL_LOW)
    {
        SIL_USB_PHID_SendString("input_s2");
    }
    last_s2_state = s2_level;
}

/**
 * @brief USB Event Polling and State Machine.
 * Must be executed periodically inside the application's main loop.
 */
void SIL_USB_PCDC_EventPoll(void)
{
    /* --- Keyboard Simulator String State Machine & Hardware Pin Scanning --- */
    if (g_usb_connected && gp_usb_ctrl == &g_basic1_ctrl)
    {
        SIL_USB_PHID_Process();
        SIL_USB_PHID_KeyScan();
    }

    fsp_err_t err = FSP_SUCCESS;
    usb_status_t usb_event = USB_STATUS_DETACH;
    usb_event_info_t event_info = {0};
    
    /* Obtain USB driver queue events */
    err = R_USB_EventGet(&event_info, &usb_event);
    if (FSP_SUCCESS != err || usb_event == USB_STATUS_NONE)
    {
        return; /* No event or event reading failed */
    }
    
    // char ev_buf[64];
    // int ev_len = snprintf(ev_buf, sizeof(ev_buf), "[USB Event] 0x%X, Class: %d\r\n", (unsigned int)usb_event, (int)event_info.type);
    // SIL_UART_DTC_TOPC_WriteToTxBuffer((uint8_t *)ev_buf, (uint16_t)ev_len);
    
    switch (usb_event)
    {
        case USB_STATUS_CONFIGURED:
        {
            /* USB Connection successfully established and configured by PC Host */
            g_usb_connected = true;
            g_usb_write_complete = true;
            g_hid_write_complete = true;
            g_send_state = SEND_STATE_IDLE;
            g_ota_active = false;
            g_ota_temp_count = 0;
            
            /* Start asynchronous read operation if currently configured as COM port */
            if (gp_usb_ctrl == &g_basic0_ctrl)
            {
                err = R_USB_Read(gp_usb_ctrl, g_usb_read_buf, USB_READ_BUF_SIZE, USB_CLASS_PCDC);
            }
            break;
        }
        
        case USB_STATUS_READ_COMPLETE:
        {
            if (g_usb_connected && gp_usb_ctrl == &g_basic0_ctrl)
            {
                uint32_t data_len = event_info.data_size;
                
                if (data_len > 0)
                {
                    /* --- 1. Handle command mode when OTA is not active --- */
                    if (!g_ota_active)
                    {
                        if (strncmp((char *)g_usb_read_buf, "PING", 4) == 0)
                        {
                            SIL_USB_PCDC_Write((uint8_t *)"PONG\r\n", 6);
                        }
                        else if (strncmp((char *)g_usb_read_buf, "INFO", 4) == 0)
                        {
                            /* VTOR Address tells us which image is running */
                            uint32_t vtor_addr = SCB->VTOR;
                            int app_num = (vtor_addr >= 0x00078000) ? 2 : 1;
                            char info_msg[64];
                            int info_len = snprintf(info_msg, sizeof(info_msg), "App %d is running! (VTOR: 0x%08X)\n", app_num, (unsigned int)vtor_addr);
                            SIL_USB_PCDC_Write((uint8_t *)info_msg, (uint32_t)info_len);
                        }
                        else if (strncmp((char *)g_usb_read_buf, "ERASE", 5) == 0)
                        {
                            /* Unlock flash HP registers */
                            (*(uint32_t *)0x400C4800) |= (1U << 10);
                            R_FLASH_HP_Open(&g_flash0_ctrl, &g_flash0_cfg);
                            
                            __disable_irq();
                            fsp_err_t erase_err = R_FLASH_HP_Erase(&g_flash0_ctrl, 0x00078000, 14);
                            __enable_irq();
                            
                            if (FSP_SUCCESS == erase_err)
                            {
                                SIL_USB_PCDC_Write((uint8_t *)"ERASE_OK\n", 9);
                            }
                            else
                            {
                                SIL_USB_PCDC_Write((uint8_t *)"ERASE_ERR\n", 10);
                            }
                        }
                        else if (strncmp((char *)g_usb_read_buf, "SIZE:", 5) == 0)
                        {
                            uint32_t expected_size = 0;
                            sscanf((char *)g_usb_read_buf + 5, "%lu", (unsigned long *)&expected_size);
                            
                            if (expected_size > 0 && expected_size <= 0x70000)
                            {
                                g_ota_expected_size = expected_size;
                                g_ota_write_addr = 0x00078000;
                                g_ota_received_bytes = 0;
                                g_ota_temp_count = 0;
                                g_ota_last_prog = 0;
                                g_ota_active = true;
                                
                                (*(uint32_t *)0x400C4800) |= (1U << 10);
                                R_FLASH_HP_Open(&g_flash0_ctrl, &g_flash0_cfg);
                                
                                SIL_USB_PCDC_Write((uint8_t *)"SIZE_OK\n", 8);
                            }
                            else
                            {
                                SIL_USB_PCDC_Write((uint8_t *)"SIZE_ERR\n", 9);
                            }
                        }
                    }
                    /* --- 2. Handle binary data stream in active OTA mode --- */
                    else
                    {
                        if (g_ota_temp_count + data_len <= OTA_TEMP_BUF_SIZE)
                        {
                            memcpy(g_ota_temp_buf + g_ota_temp_count, g_usb_read_buf, data_len);
                            g_ota_temp_count += data_len;
                            g_ota_received_bytes += data_len;
                            
                            uint32_t write_idx = 0;
                            while (g_ota_temp_count - write_idx >= 128)
                            {
                                uint32_t block_size = 32768;
                                uint32_t space_in_block = block_size - (g_ota_write_addr % block_size);
                                uint32_t write_len = 128;
                                
                                if (write_len > space_in_block)
                                {
                                    write_len = space_in_block;
                                }
                                
                                if (write_len == 0)
                                {
                                    break;
                                }
                                
                                __disable_irq();
                                fsp_err_t wr_err = R_FLASH_HP_Write(&g_flash0_ctrl, 
                                                                    (uint32_t)(g_ota_temp_buf + write_idx), 
                                                                    g_ota_write_addr, 
                                                                    write_len);
                                __enable_irq();
                                
                                if (FSP_SUCCESS == wr_err)
                                {
                                    g_ota_write_addr += write_len;
                                    write_idx += write_len;
                                }
                                else
                                {
                                    char wr_msg[32];
                                    int w_len = snprintf(wr_msg, sizeof(wr_msg), "WRITE_ERR:%d\n", (int)wr_err);
                                    SIL_USB_PCDC_Write((uint8_t *)wr_msg, (uint32_t)w_len);
                                    g_ota_active = false;
                                    break;
                                }
                            }
                            
                            if (write_idx > 0 && g_ota_temp_count > write_idx)
                            {
                                memmove(g_ota_temp_buf, g_ota_temp_buf + write_idx, g_ota_temp_count - write_idx);
                            }
                            g_ota_temp_count -= write_idx;
                            
                            if (g_ota_received_bytes - g_ota_last_prog >= 32768)
                            {
                                char prog_msg[32];
                                int p_len = snprintf(prog_msg, sizeof(prog_msg), "PROG:%lu\n", (unsigned long)g_ota_received_bytes);
                                SIL_USB_PCDC_Write((uint8_t *)prog_msg, (uint32_t)p_len);
                                g_ota_last_prog = g_ota_received_bytes;
                            }
                            
                            if (g_ota_received_bytes >= g_ota_expected_size)
                            {
                                g_ota_active = false;
                                
                                if (g_ota_temp_count > 0)
                                {
                                    memset(g_ota_temp_buf + g_ota_temp_count, 0xFF, 128 - g_ota_temp_count);
                                    __disable_irq();
                                    R_FLASH_HP_Write(&g_flash0_ctrl, (uint32_t)g_ota_temp_buf, g_ota_write_addr, 128);
                                    __enable_irq();
                                }
                                
                                char prog_msg[32];
                                int p_len = snprintf(prog_msg, sizeof(prog_msg), "PROG:%lu\n", (unsigned long)g_ota_received_bytes);
                                SIL_USB_PCDC_Write((uint8_t *)prog_msg, (uint32_t)p_len);
                                
                                R_FLASH_HP_Close(&g_flash0_ctrl);
                                
                                uint32_t calculated_crc = calculate_crc32((const uint8_t *)0x00078000, g_ota_received_bytes);
                                
                                char done_msg[128];
                                int d_len = snprintf(done_msg, sizeof(done_msg), "DONE:%lu\nCRC:%08X\n", 
                                                     (unsigned long)g_ota_received_bytes, 
                                                     (unsigned int)calculated_crc);
                                SIL_USB_PCDC_Write((uint8_t *)done_msg, (uint32_t)d_len);
                                
                                for (int delay_cnt = 0; delay_cnt < 150; delay_cnt++)
                                {
                                    R_BSP_SoftwareDelay(10, BSP_DELAY_UNITS_MILLISECONDS);
                                    SIL_USB_PCDC_EventPoll();
                                }
                                
                                __NVIC_SystemReset();
                            }
                        }
                        else
                        {
                            SIL_USB_PCDC_Write((uint8_t *)"BUF_OVERFLOW\n", 13);
                            g_ota_active = false;
                        }
                    }
                }
                
                memset(g_usb_read_buf, 0, sizeof(g_usb_read_buf));
                err = R_USB_Read(gp_usb_ctrl, g_usb_read_buf, USB_READ_BUF_SIZE, USB_CLASS_PCDC);
            }
            break;
        }
        
        case USB_STATUS_REQUEST:
        {
            if (gp_usb_ctrl == &g_basic0_ctrl)
            {
                if (USB_PCDC_SET_LINE_CODING == (event_info.setup.request_type & USB_BREQUEST))
                {
                    R_USB_PeriControlDataGet(gp_usb_ctrl, (uint8_t *)&g_line_coding, LINE_CODING_LENGTH);
                }
                else if (USB_PCDC_GET_LINE_CODING == (event_info.setup.request_type & USB_BREQUEST))
                {
                    R_USB_PeriControlDataSet(gp_usb_ctrl, (uint8_t *)&g_line_coding, LINE_CODING_LENGTH);
                }
                else if (USB_PCDC_SET_CONTROL_LINE_STATE == (event_info.setup.request_type & USB_BREQUEST))
                {
                    R_USB_PeriControlStatusSet(gp_usb_ctrl, USB_SETUP_STATUS_ACK);
                }
            }
            else if (gp_usb_ctrl == &g_basic1_ctrl)
            {
                uint16_t req_type = event_info.setup.request_type & USB_BREQUEST;
                if (USB_SET_REPORT == req_type)
                {
                    err = R_USB_PeriControlDataGet(gp_usb_ctrl, (uint8_t *)&g_numlock, SIZE_NUM);
                    if (FSP_SUCCESS != err)
                    {
                        R_USB_Close(gp_usb_ctrl);
                    }
                }
                else if (USB_GET_DESCRIPTOR == req_type)
                {
                    if (USB_GET_REPORT_DESCRIPTOR == event_info.setup.request_value)
                    {
                        err = R_USB_PeriControlDataSet(gp_usb_ctrl, (uint8_t *)g_apl_report_phid, USB_RECEIVE_REPORT_DESCRIPTOR);
                        if (FSP_SUCCESS != err)
                        {
                            R_USB_Close(gp_usb_ctrl);
                        }
                    }
                    else if (USB_GET_HID_DESCRIPTOR == event_info.setup.request_value)
                    {
                        for (uint8_t i = 0; i < USB_RECEIVE_HID_DESCRIPTOR; i++)
                        {
                            send_data_align[i] = g_apl_configuration_phid[CD_LENGTH + i];
                        }
                        err = R_USB_PeriControlDataSet(gp_usb_ctrl, send_data_align, USB_RECEIVE_HID_DESCRIPTOR);
                        if (FSP_SUCCESS != err)
                        {
                            R_USB_Close(gp_usb_ctrl);
                        }
                    }
                }
                else if (USB_SET_IDLE == req_type)
                {
                    uint8_t *p_idle_value = (uint8_t *)&event_info.setup.request_value;
                    g_idle = p_idle_value[IDLE_VAL_INDEX];
                    err = R_USB_PeriControlStatusSet(gp_usb_ctrl, USB_SETUP_STATUS_ACK);
                    if (FSP_SUCCESS != err)
                    {
                        R_USB_Close(gp_usb_ctrl);
                    }
                }
            }
            break;
        }
        
        case USB_STATUS_REQUEST_COMPLETE:
        {
            if (gp_usb_ctrl == &g_basic1_ctrl)
            {
                uint16_t req_type = event_info.setup.request_type & USB_BREQUEST;
                if (USB_SET_IDLE == req_type)
                {
                    uint8_t *p_idle_value = (uint8_t *)&event_info.setup.request_value;
                    g_idle = p_idle_value[IDLE_VAL_INDEX];
                }
                else if (USB_SET_PROTOCOL == req_type)
                {
                }
                else if (USB_SET_REPORT == req_type)
                {
                }
                else
                {
                    /* Send initial all-zero NULL report to wake up HID interrupt IN channel */
                    g_hid_write_complete = false;
                    err = R_USB_Write(gp_usb_ctrl, g_hid_null_report, 8, USB_CLASS_PHID);
                    if (FSP_SUCCESS != err)
                    {
                        g_hid_write_complete = true;
                        R_USB_Close(gp_usb_ctrl);
                    }
                }
            }
            break;
        }
        
        case USB_STATUS_WRITE_COMPLETE:
        {
            if (gp_usb_ctrl == &g_basic0_ctrl)
            {
                g_usb_write_complete = true;
            }
            else
            {
                g_hid_write_complete = true;
            }
            break;
        }
        
        case USB_STATUS_DETACH:
        {
            g_usb_connected = false;
            g_usb_write_complete = true;
            g_hid_write_complete = true;
            g_send_state = SEND_STATE_IDLE;
            g_ota_active = false;
            memset(g_usb_read_buf, 0, sizeof(g_usb_read_buf));
            break;
        }
        
        case USB_STATUS_SUSPEND:
        {
            break;
        }
        
        case USB_STATUS_RESUME:
        {
            g_usb_connected = true;
            break;
        }
        
        default:
            break;
    }
}
