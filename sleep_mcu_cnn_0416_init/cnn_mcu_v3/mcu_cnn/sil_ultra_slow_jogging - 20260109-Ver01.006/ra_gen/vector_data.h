/* generated vector header file - do not edit */
#ifndef VECTOR_DATA_H
#define VECTOR_DATA_H
#ifdef __cplusplus
        extern "C" {
        #endif
/* Number of interrupts allocated */
#ifndef VECTOR_DATA_IRQ_COUNT
#define VECTOR_DATA_IRQ_COUNT    (26)
#endif
/* ISR prototypes */
void agt_int_isr(void);
void sci_uart_rxi_isr(void);
void sci_uart_txi_isr(void);
void sci_uart_tei_isr(void);
void sci_uart_eri_isr(void);
void ctsu_write_isr(void);
void ctsu_read_isr(void);
void ctsu_end_isr(void);
void gpt_counter_overflow_isr(void);
void fcu_frdyi_isr(void);
void fcu_fiferr_isr(void);
void rtc_alarm_periodic_isr(void);
void rtc_carry_isr(void);
void usbfs_interrupt_handler(void);
void usbfs_resume_handler(void);
void usbfs_d0fifo_handler(void);
void usbfs_d1fifo_handler(void);

/* Vector table allocations */
#define VECTOR_NUMBER_AGT1_INT ((IRQn_Type) 4) /* AGT1 INT (AGT interrupt) */
#define AGT1_INT_IRQn          ((IRQn_Type) 4) /* AGT1 INT (AGT interrupt) */
#define VECTOR_NUMBER_SCI9_RXI ((IRQn_Type) 5) /* SCI9 RXI (Receive data full) */
#define SCI9_RXI_IRQn          ((IRQn_Type) 5) /* SCI9 RXI (Receive data full) */
#define VECTOR_NUMBER_SCI9_TXI ((IRQn_Type) 6) /* SCI9 TXI (Transmit data empty) */
#define SCI9_TXI_IRQn          ((IRQn_Type) 6) /* SCI9 TXI (Transmit data empty) */
#define VECTOR_NUMBER_SCI9_TEI ((IRQn_Type) 7) /* SCI9 TEI (Transmit end) */
#define SCI9_TEI_IRQn          ((IRQn_Type) 7) /* SCI9 TEI (Transmit end) */
#define VECTOR_NUMBER_SCI9_ERI ((IRQn_Type) 8) /* SCI9 ERI (Receive error) */
#define SCI9_ERI_IRQn          ((IRQn_Type) 8) /* SCI9 ERI (Receive error) */
#define VECTOR_NUMBER_AGT0_INT ((IRQn_Type) 9) /* AGT0 INT (AGT interrupt) */
#define AGT0_INT_IRQn          ((IRQn_Type) 9) /* AGT0 INT (AGT interrupt) */
#define VECTOR_NUMBER_CTSU_WRITE ((IRQn_Type) 10) /* CTSU WRITE (Write request interrupt) */
#define CTSU_WRITE_IRQn          ((IRQn_Type) 10) /* CTSU WRITE (Write request interrupt) */
#define VECTOR_NUMBER_CTSU_READ ((IRQn_Type) 11) /* CTSU READ (Measurement data transfer request interrupt) */
#define CTSU_READ_IRQn          ((IRQn_Type) 11) /* CTSU READ (Measurement data transfer request interrupt) */
#define VECTOR_NUMBER_CTSU_END ((IRQn_Type) 12) /* CTSU END (Measurement end interrupt) */
#define CTSU_END_IRQn          ((IRQn_Type) 12) /* CTSU END (Measurement end interrupt) */
#define VECTOR_NUMBER_SCI0_RXI ((IRQn_Type) 13) /* SCI0 RXI (Receive data full) */
#define SCI0_RXI_IRQn          ((IRQn_Type) 13) /* SCI0 RXI (Receive data full) */
#define VECTOR_NUMBER_SCI0_TXI ((IRQn_Type) 14) /* SCI0 TXI (Transmit data empty) */
#define SCI0_TXI_IRQn          ((IRQn_Type) 14) /* SCI0 TXI (Transmit data empty) */
#define VECTOR_NUMBER_SCI0_TEI ((IRQn_Type) 15) /* SCI0 TEI (Transmit end) */
#define SCI0_TEI_IRQn          ((IRQn_Type) 15) /* SCI0 TEI (Transmit end) */
#define VECTOR_NUMBER_SCI0_ERI ((IRQn_Type) 16) /* SCI0 ERI (Receive error) */
#define SCI0_ERI_IRQn          ((IRQn_Type) 16) /* SCI0 ERI (Receive error) */
#define VECTOR_NUMBER_GPT0_COUNTER_OVERFLOW ((IRQn_Type) 17) /* GPT0 COUNTER OVERFLOW (Overflow) */
#define GPT0_COUNTER_OVERFLOW_IRQn          ((IRQn_Type) 17) /* GPT0 COUNTER OVERFLOW (Overflow) */
#define VECTOR_NUMBER_SCI6_RXI ((IRQn_Type) 18) /* SCI6 RXI (Receive data full) */
#define SCI6_RXI_IRQn          ((IRQn_Type) 18) /* SCI6 RXI (Receive data full) */
#define VECTOR_NUMBER_SCI6_TXI ((IRQn_Type) 19) /* SCI6 TXI (Transmit data empty) */
#define SCI6_TXI_IRQn          ((IRQn_Type) 19) /* SCI6 TXI (Transmit data empty) */
#define VECTOR_NUMBER_SCI6_TEI ((IRQn_Type) 20) /* SCI6 TEI (Transmit end) */
#define SCI6_TEI_IRQn          ((IRQn_Type) 20) /* SCI6 TEI (Transmit end) */
#define VECTOR_NUMBER_SCI6_ERI ((IRQn_Type) 21) /* SCI6 ERI (Receive error) */
#define SCI6_ERI_IRQn          ((IRQn_Type) 21) /* SCI6 ERI (Receive error) */
#define VECTOR_NUMBER_FCU_FRDYI ((IRQn_Type) 22) /* FCU FRDYI (Flash ready interrupt) */
#define FCU_FRDYI_IRQn          ((IRQn_Type) 22) /* FCU FRDYI (Flash ready interrupt) */
#define VECTOR_NUMBER_FCU_FIFERR ((IRQn_Type) 23) /* FCU FIFERR (Flash access error interrupt) */
#define FCU_FIFERR_IRQn          ((IRQn_Type) 23) /* FCU FIFERR (Flash access error interrupt) */
#define VECTOR_NUMBER_RTC_PERIOD ((IRQn_Type) 24) /* RTC PERIOD (Periodic interrupt) */
#define RTC_PERIOD_IRQn          ((IRQn_Type) 24) /* RTC PERIOD (Periodic interrupt) */
#define VECTOR_NUMBER_RTC_CARRY ((IRQn_Type) 25) /* RTC CARRY (Carry interrupt) */
#define RTC_CARRY_IRQn          ((IRQn_Type) 25) /* RTC CARRY (Carry interrupt) */
#define VECTOR_NUMBER_USBFS_INT ((IRQn_Type) 26) /* USBFS INT (USBFS interrupt) */
#define USBFS_INT_IRQn          ((IRQn_Type) 26) /* USBFS INT (USBFS interrupt) */
#define VECTOR_NUMBER_USBFS_RESUME ((IRQn_Type) 27) /* USBFS RESUME (USBFS resume interrupt) */
#define USBFS_RESUME_IRQn          ((IRQn_Type) 27) /* USBFS RESUME (USBFS resume interrupt) */
#define VECTOR_NUMBER_USBFS_FIFO_0 ((IRQn_Type) 28) /* USBFS FIFO 0 (DMA/DTC transfer request 0) */
#define USBFS_FIFO_0_IRQn          ((IRQn_Type) 28) /* USBFS FIFO 0 (DMA/DTC transfer request 0) */
#define VECTOR_NUMBER_USBFS_FIFO_1 ((IRQn_Type) 29) /* USBFS FIFO 1 (DMA/DTC transfer request 1) */
#define USBFS_FIFO_1_IRQn          ((IRQn_Type) 29) /* USBFS FIFO 1 (DMA/DTC transfer request 1) */
/* The number of entries required for the ICU vector table. */
#define BSP_ICU_VECTOR_NUM_ENTRIES (30)

#ifdef __cplusplus
        }
        #endif
#endif /* VECTOR_DATA_H */
