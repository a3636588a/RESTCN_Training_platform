/* generated vector source file - do not edit */
#include "bsp_api.h"
/* Do not build these data structures if no interrupts are currently allocated because IAR will have build errors. */
#if VECTOR_DATA_IRQ_COUNT > 0
        BSP_DONT_REMOVE const fsp_vector_t g_vector_table[BSP_ICU_VECTOR_NUM_ENTRIES] BSP_PLACE_IN_SECTION(BSP_SECTION_APPLICATION_VECTORS) =
        {
                        [4] = agt_int_isr, /* AGT1 INT (AGT interrupt) */
            [5] = sci_uart_rxi_isr, /* SCI9 RXI (Receive data full) */
            [6] = sci_uart_txi_isr, /* SCI9 TXI (Transmit data empty) */
            [7] = sci_uart_tei_isr, /* SCI9 TEI (Transmit end) */
            [8] = sci_uart_eri_isr, /* SCI9 ERI (Receive error) */
            [9] = agt_int_isr, /* AGT0 INT (AGT interrupt) */
            [10] = ctsu_write_isr, /* CTSU WRITE (Write request interrupt) */
            [11] = ctsu_read_isr, /* CTSU READ (Measurement data transfer request interrupt) */
            [12] = ctsu_end_isr, /* CTSU END (Measurement end interrupt) */
            [13] = sci_uart_rxi_isr, /* SCI0 RXI (Receive data full) */
            [14] = sci_uart_txi_isr, /* SCI0 TXI (Transmit data empty) */
            [15] = sci_uart_tei_isr, /* SCI0 TEI (Transmit end) */
            [16] = sci_uart_eri_isr, /* SCI0 ERI (Receive error) */
            [17] = gpt_counter_overflow_isr, /* GPT0 COUNTER OVERFLOW (Overflow) */
            [18] = sci_uart_rxi_isr, /* SCI6 RXI (Receive data full) */
            [19] = sci_uart_txi_isr, /* SCI6 TXI (Transmit data empty) */
            [20] = sci_uart_tei_isr, /* SCI6 TEI (Transmit end) */
            [21] = sci_uart_eri_isr, /* SCI6 ERI (Receive error) */
            [22] = fcu_frdyi_isr, /* FCU FRDYI (Flash ready interrupt) */
            [23] = fcu_fiferr_isr, /* FCU FIFERR (Flash access error interrupt) */
            [24] = rtc_alarm_periodic_isr, /* RTC PERIOD (Periodic interrupt) */
            [25] = rtc_carry_isr, /* RTC CARRY (Carry interrupt) */
            [26] = usbfs_interrupt_handler, /* USBFS INT (USBFS interrupt) */
            [27] = usbfs_resume_handler, /* USBFS RESUME (USBFS resume interrupt) */
            [28] = usbfs_d0fifo_handler, /* USBFS FIFO 0 (DMA/DTC transfer request 0) */
            [29] = usbfs_d1fifo_handler, /* USBFS FIFO 1 (DMA/DTC transfer request 1) */
        };
        #if BSP_FEATURE_ICU_HAS_IELSR
        const bsp_interrupt_event_t g_interrupt_event_link_select[BSP_ICU_VECTOR_NUM_ENTRIES] =
        {
            [4] = BSP_PRV_VECT_ENUM(EVENT_AGT1_INT,GROUP4), /* AGT1 INT (AGT interrupt) */
            [5] = BSP_PRV_VECT_ENUM(EVENT_SCI9_RXI,GROUP5), /* SCI9 RXI (Receive data full) */
            [6] = BSP_PRV_VECT_ENUM(EVENT_SCI9_TXI,GROUP6), /* SCI9 TXI (Transmit data empty) */
            [7] = BSP_PRV_VECT_ENUM(EVENT_SCI9_TEI,GROUP7), /* SCI9 TEI (Transmit end) */
            [8] = BSP_PRV_VECT_ENUM(EVENT_SCI9_ERI,GROUP0), /* SCI9 ERI (Receive error) */
            [9] = BSP_PRV_VECT_ENUM(EVENT_AGT0_INT,GROUP1), /* AGT0 INT (AGT interrupt) */
            [10] = BSP_PRV_VECT_ENUM(EVENT_CTSU_WRITE,GROUP2), /* CTSU WRITE (Write request interrupt) */
            [11] = BSP_PRV_VECT_ENUM(EVENT_CTSU_READ,GROUP3), /* CTSU READ (Measurement data transfer request interrupt) */
            [12] = BSP_PRV_VECT_ENUM(EVENT_CTSU_END,GROUP4), /* CTSU END (Measurement end interrupt) */
            [13] = BSP_PRV_VECT_ENUM(EVENT_SCI0_RXI,GROUP5), /* SCI0 RXI (Receive data full) */
            [14] = BSP_PRV_VECT_ENUM(EVENT_SCI0_TXI,GROUP6), /* SCI0 TXI (Transmit data empty) */
            [15] = BSP_PRV_VECT_ENUM(EVENT_SCI0_TEI,GROUP7), /* SCI0 TEI (Transmit end) */
            [16] = BSP_PRV_VECT_ENUM(EVENT_SCI0_ERI,GROUP0), /* SCI0 ERI (Receive error) */
            [17] = BSP_PRV_VECT_ENUM(EVENT_GPT0_COUNTER_OVERFLOW,GROUP1), /* GPT0 COUNTER OVERFLOW (Overflow) */
            [18] = BSP_PRV_VECT_ENUM(EVENT_SCI6_RXI,GROUP2), /* SCI6 RXI (Receive data full) */
            [19] = BSP_PRV_VECT_ENUM(EVENT_SCI6_TXI,GROUP3), /* SCI6 TXI (Transmit data empty) */
            [20] = BSP_PRV_VECT_ENUM(EVENT_SCI6_TEI,GROUP4), /* SCI6 TEI (Transmit end) */
            [21] = BSP_PRV_VECT_ENUM(EVENT_SCI6_ERI,GROUP5), /* SCI6 ERI (Receive error) */
            [22] = BSP_PRV_VECT_ENUM(EVENT_FCU_FRDYI,GROUP6), /* FCU FRDYI (Flash ready interrupt) */
            [23] = BSP_PRV_VECT_ENUM(EVENT_FCU_FIFERR,GROUP7), /* FCU FIFERR (Flash access error interrupt) */
            [24] = BSP_PRV_VECT_ENUM(EVENT_RTC_PERIOD,GROUP0), /* RTC PERIOD (Periodic interrupt) */
            [25] = BSP_PRV_VECT_ENUM(EVENT_RTC_CARRY,GROUP1), /* RTC CARRY (Carry interrupt) */
            [26] = BSP_PRV_VECT_ENUM(EVENT_USBFS_INT,GROUP2), /* USBFS INT (USBFS interrupt) */
            [27] = BSP_PRV_VECT_ENUM(EVENT_USBFS_RESUME,GROUP3), /* USBFS RESUME (USBFS resume interrupt) */
            [28] = BSP_PRV_VECT_ENUM(EVENT_USBFS_FIFO_0,GROUP4), /* USBFS FIFO 0 (DMA/DTC transfer request 0) */
            [29] = BSP_PRV_VECT_ENUM(EVENT_USBFS_FIFO_1,GROUP5), /* USBFS FIFO 1 (DMA/DTC transfer request 1) */
        };
        #endif
        #endif
