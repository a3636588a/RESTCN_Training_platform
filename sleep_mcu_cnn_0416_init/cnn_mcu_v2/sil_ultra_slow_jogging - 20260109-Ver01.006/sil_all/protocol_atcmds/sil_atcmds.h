#ifndef SIL_ATCMDS_H
#define SIL_ATCMDS_H

#include "..\app\sil_app_type.h"
#include <stdbool.h>
#include <stdio.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/*
#if defined(__ICCARM__)

void R_BSP_WarmStart(bsp_warm_start_event_t event);

 #pragma weak R_BSP_WarmStart

#elif defined(__GNUC__) || defined(__ARMCC_VERSION)

void R_BSP_WarmStart(bsp_warm_start_event_t event) __attribute__((weak));

#endif
// */

#define SILCNTS_ATCMDS_UART_MAX_BS 128
// #define SILCNTS_ATCMDS_UART_MAX_BS 256

typedef enum SIL_ATCMDS_IO_E {
  ATCMDS_IO_UNKNOWN_E = -1,
  ATCMDS_IO_TOPC = 0,
  ATCMDS_IO_TOBLE,

  ATCMDS_IO_FINAL_E,
  ATCMDS_IO_MAXS_E = (ATCMDS_IO_FINAL_E + 2)

} sil_atcmds_io_e;

// 	SIL output
// ultra slow Jogging
#define SILCNTS_ATCMDS_SILUSJSTPS_OUT_VER_1 20240130
#define SILCNTS_ATCMDS_SILUSJSTPS_OUT_VER SILCNTS_ATCMDS_SILUSJSTPS_OUT_VER_1
//											 	$SILUSJSTPS,20240130,2,1.5,1.0*2F
#define SILCNTS_ATCMDS_SILUSJSTPS_OUT "$SILUSJSTPS,%d,%u,%u,%u*%02X\r\n"
#define SILCNTS_ATCMDS_SILUSJSTPS "$SILUSJSTPS,"

#define SILCNTS_ATCMDS_SILINO_OUT_VER_1 20240130
#define SILCNTS_ATCMDS_SILINO_OUT_VER SILCNTS_ATCMDS_SILINO_OUT_VER_1

// jumps rope count
#define SILCNTS_ATCMDS_SILJRC_OUT_VER_1 20240130
#define SILCNTS_ATCMDS_SILJRC_OUT_VER SILCNTS_ATCMDS_SILJRC_OUT_VER_1
//											 	$SILJRC,20240130,2,10*14\r\n
#define SILCNTS_ATCMDS_SILJRC_OUT "$SILJRC,%d,%u,%u*%02X\r\n"
#define SILCNTS_ATCMDS_SILJRC "$SILJRC,"

// Glove ML - Baseline Calibration
#define SILCNTS_ATCMDS_SILBASEEXT_OUT_VER_1 20240130
#define SILCNTS_ATCMDS_SILBASEEXT_OUT_VER SILCNTS_ATCMDS_SILBASEEXT_OUT_VER_1
#define SILCNTS_ATCMDS_SILBASEEXT_OUT "$SILBASEEXT,%d,%u,%u,"
#define SILCNTS_ATCMDS_SILBASEEXT "$SILBASEEXT,"

// Glove ML - Hold Calibration
#define SILCNTS_ATCMDS_SILHOLDEXT_OUT_VER_1 20240130
#define SILCNTS_ATCMDS_SILHOLDEXT_OUT_VER SILCNTS_ATCMDS_SILHOLDEXT_OUT_VER_1
#define SILCNTS_ATCMDS_SILHOLDEXT_OUT "$SILHOLDEXT,%d,%u,%u,"
#define SILCNTS_ATCMDS_SILHOLDEXT "$SILHOLDEXT,"

// Glove ML - Inference & Debug
#define SILCNTS_ATCMDS_SILMOVBASE_OUT_VER_1 20240130
#define SILCNTS_ATCMDS_SILMOVBASE_OUT_VER SILCNTS_ATCMDS_SILMOVBASE_OUT_VER_1
// challenge: "$SILMOVBASE,20240130,count,size,base1,base2...*CS\r\n"
#define SILCNTS_ATCMDS_SILMOVBASE_OUT "$SILMOVBASE,%d,%u,%u,"
#define SILCNTS_ATCMDS_SILMOVBASE "$SILMOVBASE,"

#define SILCNTS_ATCMDS_SILGESTURE_OUT "$SILGESTURE,%d*%02X\r\n"
#define SILCNTS_ATCMDS_SILGESTURE "$SILGESTURE,"

#define SILCNTS_ATCMDS_SILDYNAMICGESTURE_OUT "$SILdynamicGESTURE,%s*%02X\r\n"
#define SILCNTS_ATCMDS_SILDYNAMICGESTURE "$SILdynamicGESTURE,"

typedef enum SIL_ATCMDS_CMDS_OUT_E {
  ATCMDS_CMDS_OUT_UNKNOWN_E = -1,

  ATCMDS_CMDS_OUT_FINAL_E,
  ATCMDS_CMDS_OUT_MAXS_E = (ATCMDS_CMDS_OUT_FINAL_E + 2)
} sil_atcmds_cmds_out_e;

//  SIL input
//      SILSFI, SIL frequency channel
#define SILCNTS_ATCMDS_SILSFI_IN_VER_1 20240130
#define SILCNTS_ATCMDS_SILSFI_IN_VER SILCNTS_ATCMDS_SILSFI_IN_VER_1
#define SILCNTS_ATCMDS_SILSFI_IN "$SILSFI,%d,%d*%02X\r\n"
#define SILCNTS_ATCMDS_SILSFI "$SILSFI,"
#define SILCNTS_ATCMDS_SILSFI_IN_DEFAULT 128

//      SILSWRT, trigger software reboot
#define SILCNTS_ATCMDS_SILSWRB_IN_VER_1 20240130
#define SILCNTS_ATCMDS_SILSWRB_IN_VER SILCNTS_ATCMDS_SILSWRB_IN_VER_1
#define SILCNTS_ATCMDS_SILSWRB_IN "$SILSWRB,%d,%d,%d,%d,%d,%d*%02X\r\n"
#define SILCNTS_ATCMDS_SILSWRB "$SILSWRB,"

// 		SILRTCI, set device rtc
#define SILCNTS_ATCMDS_SILRTCI_IN_VER_1 20240130
#define SILCNTS_ATCMDS_SILRTCI_IN_VER SILCNTS_ATCMDS_SILRTCI_IN_VER_1
#define SILCNTS_ATCMDS_SILRTCI_IN                                              \
  "$SILRTCI,%d,%02d,%02d,%02d,%02d,%02d,%02d,%02d*%02X\r\n"
#define SILCNTS_ATCMDS_SILRTCI "$SILRTCI,"

// 		SILAPP, application type
#define SILCNTS_ATCMDS_SILAPP_IN_VER_1 20240130
#define SILCNTS_ATCMDS_SILAPP_IN_VER SILCNTS_ATCMDS_SILAPP_IN_VER_1
#define SILCNTS_ATCMDS_SILAPP_IN "$SILAPP,%d,%d*%02X\r\n"
#define SILCNTS_ATCMDS_SILAPP "$SILAPP,"

typedef enum SIL_ATCMDS_CMDS_IN_E {
  ATCMDS_CMDS_IN_UNKNOWN_E = -1,

  ATCMDS_CMDS_IN_SILSFI_E,
  ATCMDS_CMDS_IN_SILSWRB_E,
  ATCMDS_CMDS_IN_SILRTCI_E,

  ATCMDS_CMDS_IN_SILAPP_E,

  ATCMDS_CMDS_IN_FINAL_E,
  ATCMDS_CMDS_IN_MAXS_E = (ATCMDS_CMDS_IN_FINAL_E + 2)
} sil_atcmds_cmds_in_e;

uint16_t SIL_ATCMDS_Checksum(uint8_t *d);
void SIL_ATCMDS_IntToAsciiDecimal(int32_t s, uint8_t *d, uint16_t size);
void SIL_ATCMDS_ChecksumToHex(int32_t s, uint8_t *d, uint16_t size);
void SIL_ATCMDS_SendSilusjstps(sil_atcmds_io_e io, uint32_t cnt, uint32_t left,
                               uint32_t right);
void SIL_ATCMDS_SendSiljrc(sil_atcmds_io_e io, uint32_t cnt, uint32_t jumps);
void SIL_ATCMDS_SendSilino(sil_atcmds_io_e io, uint32_t cnt, uint16_t *ch,
                           uint16_t size);
void SIL_ATCMDS_SendSilinoGlove(sil_atcmds_io_e io, uint32_t cnt, uint16_t *ch,
                                uint16_t size);
void SIL_ATCMDS_SendSilBaseExt(sil_atcmds_io_e io, uint32_t cnt, uint16_t *avg,
                               uint16_t *minv, uint16_t *maxv, uint16_t size);
void SIL_ATCMDS_SendSilHoldExt(sil_atcmds_io_e io, uint32_t cnt, uint16_t *avg,
                               uint16_t *minv, uint16_t *maxv, uint16_t size);

void SIL_ATCMDS_SendSilMovBase(sil_atcmds_io_e io, uint32_t cnt, uint16_t *base,
                               uint16_t size);
void SIL_ATCMDS_SendSilGesture(sil_atcmds_io_e io, const char *name);
void SIL_ATCMDS_SendSilDynamicGesture(sil_atcmds_io_e io, const char *name);
void SIL_ATCMDS_SendSilNotify(sil_atcmds_io_e io, const char *msg);

char *SIL_ATCMDS_CutCommand(char *in, uint32_t *offset);
sil_atcmds_cmds_in_e SIL_ATCMDS_ProcessAtcmds(char *d, char **nD);
void SIL_ATCMDS_DispatchCmds(sil_atcmds_io_e io, sil_atcmds_cmds_in_e cmd,
                             char *buf, uint16_t len);

void SIL_ATCMDS_Enter1();
void SIL_ATCMDS_Enter2();
void SIL_ATCMDS_MainLoop1(sil_atcmds_io_e io);
void SIL_ATCMDS_MainLoop2(sil_atcmds_io_e io);

#ifdef __cplusplus
}
#endif

#endif // #ifndef SIL_ATCMDS_H
