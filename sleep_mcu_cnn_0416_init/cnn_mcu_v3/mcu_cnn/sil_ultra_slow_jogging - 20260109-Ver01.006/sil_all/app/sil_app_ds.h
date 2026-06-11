#ifndef SIL_APP_DS_H
#define SIL_APP_DS_H

#include "hal_data.h"

/* DS Mode API Declarations */
fsp_err_t SIL_APP_DS_Enter1(void);
fsp_err_t SIL_APP_DS_Enter2(void);
void SIL_APP_DS_MainLoop1(void);
void SIL_APP_DS_MainLoop2(void);
void SIL_APP_DS_Exit(void);

#endif // SIL_APP_DS_H
