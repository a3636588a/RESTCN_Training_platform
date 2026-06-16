/* generated vector source file - do not edit */
#include "bsp_api.h"
/* Do not build these data structures if no interrupts are currently allocated because IAR will have build errors. */
#if VECTOR_DATA_IRQ_COUNT > 0
        BSP_DONT_REMOVE const fsp_vector_t g_vector_table[BSP_ICU_VECTOR_NUM_ENTRIES] BSP_PLACE_IN_SECTION(BSP_SECTION_APPLICATION_VECTORS) =
        {
                        [0] = agt_int_isr, /* AGT1 INT (AGT interrupt) */
            [1] = sci_uart_rxi_isr, /* SCI9 RXI (Receive data full) */
            [2] = sci_uart_txi_isr, /* SCI9 TXI (Transmit data empty) */
            [3] = sci_uart_tei_isr, /* SCI9 TEI (Transmit end) */
            [4] = sci_uart_eri_isr, /* SCI9 ERI (Receive error) */
            [5] = agt_int_isr, /* AGT0 INT (AGT interrupt) */
            [6] = ctsu_write_isr, /* CTSU WRITE (Write request interrupt) */
            [7] = ctsu_read_isr, /* CTSU READ (Measurement data transfer request interrupt) */
            [8] = ctsu_end_isr, /* CTSU END (Measurement end interrupt) */
            [9] = sci_uart_rxi_isr, /* SCI0 RXI (Receive data full) */
            [10] = sci_uart_txi_isr, /* SCI0 TXI (Transmit data empty) */
            [11] = sci_uart_tei_isr, /* SCI0 TEI (Transmit end) */
            [12] = sci_uart_eri_isr, /* SCI0 ERI (Receive error) */
            [13] = gpt_counter_overflow_isr, /* GPT0 COUNTER OVERFLOW (Overflow) */
            [14] = sci_uart_rxi_isr, /* SCI6 RXI (Receive data full) */
            [15] = sci_uart_txi_isr, /* SCI6 TXI (Transmit data empty) */
            [16] = sci_uart_tei_isr, /* SCI6 TEI (Transmit end) */
            [17] = sci_uart_eri_isr, /* SCI6 ERI (Receive error) */
            [18] = fcu_frdyi_isr, /* FCU FRDYI (Flash ready interrupt) */
            [19] = fcu_fiferr_isr, /* FCU FIFERR (Flash access error interrupt) */
            [20] = rtc_alarm_periodic_isr, /* RTC PERIOD (Periodic interrupt) */
            [21] = rtc_carry_isr, /* RTC CARRY (Carry interrupt) */
            [22] = usbfs_interrupt_handler, /* USBFS INT (USBFS interrupt) */
            [23] = usbfs_resume_handler, /* USBFS RESUME (USBFS resume interrupt) */
            [24] = usbfs_d0fifo_handler, /* USBFS FIFO 0 (DMA/DTC transfer request 0) */
            [25] = usbfs_d1fifo_handler, /* USBFS FIFO 1 (DMA/DTC transfer request 1) */
        };
        #if BSP_FEATURE_ICU_HAS_IELSR
        const bsp_interrupt_event_t g_interrupt_event_link_select[BSP_ICU_VECTOR_NUM_ENTRIES] =
        {
            [0] = BSP_PRV_VECT_ENUM(EVENT_AGT1_INT,GROUP0), /* AGT1 INT (AGT interrupt) */
            [1] = BSP_PRV_VECT_ENUM(EVENT_SCI9_RXI,GROUP1), /* SCI9 RXI (Receive data full) */
            [2] = BSP_PRV_VECT_ENUM(EVENT_SCI9_TXI,GROUP2), /* SCI9 TXI (Transmit data empty) */
            [3] = BSP_PRV_VECT_ENUM(EVENT_SCI9_TEI,GROUP3), /* SCI9 TEI (Transmit end) */
            [4] = BSP_PRV_VECT_ENUM(EVENT_SCI9_ERI,GROUP4), /* SCI9 ERI (Receive error) */
            [5] = BSP_PRV_VECT_ENUM(EVENT_AGT0_INT,GROUP5), /* AGT0 INT (AGT interrupt) */
            [6] = BSP_PRV_VECT_ENUM(EVENT_CTSU_WRITE,GROUP6), /* CTSU WRITE (Write request interrupt) */
            [7] = BSP_PRV_VECT_ENUM(EVENT_CTSU_READ,GROUP7), /* CTSU READ (Measurement data transfer request interrupt) */
            [8] = BSP_PRV_VECT_ENUM(EVENT_CTSU_END,GROUP0), /* CTSU END (Measurement end interrupt) */
            [9] = BSP_PRV_VECT_ENUM(EVENT_SCI0_RXI,GROUP1), /* SCI0 RXI (Receive data full) */
            [10] = BSP_PRV_VECT_ENUM(EVENT_SCI0_TXI,GROUP2), /* SCI0 TXI (Transmit data empty) */
            [11] = BSP_PRV_VECT_ENUM(EVENT_SCI0_TEI,GROUP3), /* SCI0 TEI (Transmit end) */
            [12] = BSP_PRV_VECT_ENUM(EVENT_SCI0_ERI,GROUP4), /* SCI0 ERI (Receive error) */
            [13] = BSP_PRV_VECT_ENUM(EVENT_GPT0_COUNTER_OVERFLOW,GROUP5), /* GPT0 COUNTER OVERFLOW (Overflow) */
            [14] = BSP_PRV_VECT_ENUM(EVENT_SCI6_RXI,GROUP6), /* SCI6 RXI (Receive data full) */
            [15] = BSP_PRV_VECT_ENUM(EVENT_SCI6_TXI,GROUP7), /* SCI6 TXI (Transmit data empty) */
            [16] = BSP_PRV_VECT_ENUM(EVENT_SCI6_TEI,GROUP0), /* SCI6 TEI (Transmit end) */
            [17] = BSP_PRV_VECT_ENUM(EVENT_SCI6_ERI,GROUP1), /* SCI6 ERI (Receive error) */
            [18] = BSP_PRV_VECT_ENUM(EVENT_FCU_FRDYI,GROUP2), /* FCU FRDYI (Flash ready interrupt) */
            [19] = BSP_PRV_VECT_ENUM(EVENT_FCU_FIFERR,GROUP3), /* FCU FIFERR (Flash access error interrupt) */
            [20] = BSP_PRV_VECT_ENUM(EVENT_RTC_PERIOD,GROUP4), /* RTC PERIOD (Periodic interrupt) */
            [21] = BSP_PRV_VECT_ENUM(EVENT_RTC_CARRY,GROUP5), /* RTC CARRY (Carry interrupt) */
            [22] = BSP_PRV_VECT_ENUM(EVENT_USBFS_INT,GROUP6), /* USBFS INT (USBFS interrupt) */
            [23] = BSP_PRV_VECT_ENUM(EVENT_USBFS_RESUME,GROUP7), /* USBFS RESUME (USBFS resume interrupt) */
            [24] = BSP_PRV_VECT_ENUM(EVENT_USBFS_FIFO_0,GROUP0), /* USBFS FIFO 0 (DMA/DTC transfer request 0) */
            [25] = BSP_PRV_VECT_ENUM(EVENT_USBFS_FIFO_1,GROUP1), /* USBFS FIFO 1 (DMA/DTC transfer request 1) */
        };
        #endif
        #endif
