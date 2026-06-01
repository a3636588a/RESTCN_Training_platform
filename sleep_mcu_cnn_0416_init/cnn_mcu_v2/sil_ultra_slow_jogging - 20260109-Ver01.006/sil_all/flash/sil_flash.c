#include "sil_flash.h"
#include <stdlib.h>

void SIL_FLASH_Callback(sil_flash_s *obj, flash_callback_args_t *p_args) {
	
	sil_flash_s *p_obj = obj;
	flash_event_t flash_event;
	
	if (p_obj && p_args) {
		flash_event = p_args->event;

		if (FLASH_EVENT_ERASE_COMPLETE == flash_event) {
			p_obj->flag_erase_complete = true;
		}
		else if (FLASH_EVENT_WRITE_COMPLETE == flash_event) {
			p_obj->flag_write_complete = true;
		}
		else if (FLASH_EVENT_BLANK == flash_event) {
			p_obj->flag_event_blank = true;
		}
		else if (FLASH_EVENT_NOT_BLANK == flash_event) {
			p_obj->flag_event_not_blank = true;
		}
		else {
			p_obj->flag_event_error = true;
			p_obj->event_error_type = flash_event;
		}
	}
}

fsp_err_t SIL_FLASH_Read(sil_flash_s *obj, uint16_t start, uint8_t *buf, uint16_t *size) {
    sil_flash_s *p_obj = (sil_flash_s *)obj;
    uint8_t *p = (uint8_t *) 0;
    fsp_err_t err = -1;
    int32_t st = start;
    int32_t sz = *size;

    if (p_obj && buf && size) {

        st = start;
        sz = *size;

        if ((st + sz) > SILCNTS_FLASH_DATA_SIZE) sz = SILCNTS_FLASH_DATA_SIZE - st;

        p = (uint8_t *)(p_obj->p_data + start);
        *size = (uint16_t) sz;
        memcpy(buf, p, *size);


        err = FSP_SUCCESS;
    }

    return err;
}

static void SIL_FLASH_ClearWriteBufferIndex(sil_flash_s *obj, uint32_t index) {
    sil_flash_s *p_obj = (sil_flash_s *)obj;

    if (p_obj && (p_obj->data_dirty > 0) && p_obj->flag_bgo) {
        p_obj->data_dirty = (uint32_t)(p_obj->data_dirty & (uint32_t)~(1 << index));
    }

}

static void SIL_FLASH_SetWriteBufferIndex(sil_flash_s *obj, uint32_t index) {
    sil_flash_s *p_obj = (sil_flash_s *)obj;

    if (p_obj && p_obj->flag_bgo) {
        p_obj->data_dirty = (uint32_t)(p_obj->data_dirty | (uint32_t)(1 << index));
    }

}

static uint32_t SIL_FLASH_GetWriteBufferIndex(sil_flash_s *obj) {
    sil_flash_s *p_obj = (sil_flash_s *)obj;
    uint32_t index = 0;

    if (p_obj && p_obj->data_dirty && p_obj->flag_bgo) {

        for (index = 0; index < 32; index ++) {
            if (p_obj->data_dirty & (1 << index)) return index;
        }

    }
    return (uint32_t) -1;
}

fsp_err_t SIL_FLASH_WriteToCache(sil_flash_s *obj, uint16_t start, uint8_t *buf, uint16_t size) {
	sil_flash_s *p_obj = (sil_flash_s *)obj;
	fsp_err_t err = -1;
	uint8_t *p = (uint8_t *) 0;
	uint32_t i, index_start, index_end;
	uint32_t block_size;
	
	if (p_obj && buf && size && ((start + size - 1) < SILCNTS_FLASH_DATA_SIZE)) {
		
	    p = (uint8_t *)(p_obj->p_data + start);
	    memcpy(p, buf, size * sizeof(uint8_t));
	    block_size = p_obj->info.data_flash.p_block_array->block_size;

	    index_start = start / block_size;
	    index_end = (start + size + block_size - 1) / block_size;

	    for (i = index_start; i < index_end; i ++) SIL_FLASH_SetWriteBufferIndex(p_obj, i);
	    if (p_obj->sts_wr == FLASH_WR_STS_UNKNOWN_E) p_obj->sts_wr = FLASH_WR_STS_GET_BLK_INDEX;

		err = FSP_SUCCESS;
	}
	

	return err;
}

static void SIL_FLASH_ClearWriteBufferAll(sil_flash_s *obj) {
    sil_flash_s *p_obj = (sil_flash_s *)obj;

    if (p_obj) {
        p_obj->flag_erase_complete = false;
        p_obj->flag_write_complete = false;
        p_obj->flag_event_blank = false;
        p_obj->flag_event_not_blank = false;
        p_obj->flag_event_error = false;
        p_obj->data_dirty = 0;
        p_obj->index_wr_curr = (uint32_t) -1;
        p_obj->count_wr_reset = 0;
        p_obj->sts_wr = FLASH_WR_STS_UNKNOWN_E;
    }
}

void SIL_FLASH_FlushWriteBuffer(sil_flash_s *obj) {

    sil_flash_s *p_obj = (sil_flash_s *)obj;
    fsp_err_t err = -1;
    flash_result_t blank_check_result = FLASH_RESULT_BLANK;
    uint32_t block_size = 0;
    uint32_t addr_dest = 0;
    uint32_t addr_src = 0;


    if (p_obj && p_obj->flag_bgo) {

        block_size = p_obj->info.data_flash.p_block_array->block_size;

        if ((p_obj->info.data_flash.num_regions == 1)) {

            p_obj->count_wr_reset ++;
            if (p_obj->count_wr_reset > SILCNTS_FLASH_DATA_WRITE_TIMEOUT_COUNT) {

                SIL_FLASH_ClearWriteBufferAll(p_obj);
                return ;
            }

            p_obj->index_wr_curr = SIL_FLASH_GetWriteBufferIndex(p_obj);
            if (p_obj->index_wr_curr == (uint32_t) -1) return;

            addr_dest = p_obj->info.data_flash.p_block_array->block_section_st_addr + (p_obj->index_wr_curr * block_size);
            addr_src = (uint32_t)p_obj->p_data + (uint32_t)(p_obj->index_wr_curr * block_size);

            switch (p_obj->sts_wr) {
            case FLASH_WR_STS_GET_BLK_INDEX:

                err = R_FLASH_HP_Erase(p_obj->p_flash->p_ctrl, addr_dest, 1);
                if (err == FSP_SUCCESS) p_obj->sts_wr = FLASH_WR_STS_ERASE;
                break;

            case FLASH_WR_STS_ERASE:
                if (p_obj->flag_erase_complete) {
                    p_obj->flag_erase_complete = false;

                    err = R_FLASH_HP_BlankCheck(p_obj->p_flash->p_ctrl, addr_dest, 1, &blank_check_result);
                    if (err == FSP_SUCCESS) {

                        if (blank_check_result == FLASH_RESULT_BLANK) {
                            p_obj->flag_event_blank = true;
                            p_obj->sts_wr = FLASH_WR_STS_BLANK_CHECK;
                        }
                        else if (FLASH_RESULT_BGO_ACTIVE == blank_check_result) {
                            p_obj->sts_wr = FLASH_WR_STS_BLANK_CHECK;
                        }
                    }
                }

                break;

            case FLASH_WR_STS_BLANK_CHECK:
                if (p_obj->flag_event_blank) {
                    p_obj->flag_event_blank = false;

                    err = R_FLASH_HP_Write(p_obj->p_flash->p_ctrl, (uint32_t)addr_src, (uint32_t)addr_dest, block_size);
                    if (FSP_SUCCESS == err) p_obj->sts_wr = FLASH_WR_STS_WRITE;
                }

                break;

            case FLASH_WR_STS_WRITE:
                if (p_obj->flag_write_complete) {
                    p_obj->flag_write_complete = false;

                    if (memcmp((void *)addr_dest, (void *)addr_src, block_size) == 0) p_obj->sts_wr = FLASH_WR_STS_VERIFY;

                }

                break;
            case FLASH_WR_STS_VERIFY:

                p_obj->count_wr_reset = 0;
                SIL_FLASH_ClearWriteBufferIndex(p_obj, p_obj->index_wr_curr);
                p_obj->index_wr_curr = SIL_FLASH_GetWriteBufferIndex(p_obj);
                if (p_obj->index_wr_curr == (uint32_t) -1) {
                    SIL_FLASH_ClearWriteBufferAll(p_obj);

                    return;
                }
                else if (p_obj->index_wr_curr) p_obj->sts_wr = FLASH_WR_STS_GET_BLK_INDEX;


                break;
            case FLASH_WR_STS_UNKNOWN_E:
            default:
                break;

            }
        }
    }
}


fsp_err_t SIL_FLASH_Enter1(sil_flash_s *obj, flash_instance_t *flash) {
	
	fsp_err_t err = -1;
	sil_flash_s *p_obj = (sil_flash_s *)obj;
	uint32_t size;
	uint32_t *p_src;
	uint32_t *p_dest;
	uint32_t i;

	//const flash_instance_t g_flash0 =
	//{ .p_ctrl = &g_flash0_ctrl, .p_cfg = &g_flash0_cfg, .p_api = &g_flash_on_flash_hp };
	
	if (p_obj && flash) {
		p_obj->p_flash = flash;
		
		if (p_obj->p_flash->p_ctrl && p_obj->p_flash->p_cfg) {
			err = R_FLASH_HP_Open(p_obj->p_flash->p_ctrl, p_obj->p_flash->p_cfg);
			if (FSP_SUCCESS == err) err = R_FLASH_HP_InfoGet(p_obj->p_flash->p_ctrl, &p_obj->info);
			if (FSP_SUCCESS == err) {

			    size = p_obj->info.data_flash.p_block_array->block_section_end_addr - p_obj->info.data_flash.p_block_array->block_section_st_addr + 1;
			    if (size > SILCNTS_FLASH_DATA_SIZE) size = SILCNTS_FLASH_DATA_SIZE;

			    p_obj->p_data = (uint8_t *) malloc(size * sizeof(uint8_t));
			    p_obj->data_len = (uint16_t) size;
			    p_obj->flag_bgo = p_obj->p_flash->p_cfg->data_flash_bgo;

			    p_src = (uint32_t *)p_obj->info.data_flash.p_block_array->block_section_st_addr;
			    p_dest = (uint32_t *)p_obj->p_data;
			    size = (size + sizeof(uint32_t) - 1) / sizeof(uint32_t);
			    for (i = 0; i < size; i ++) {
			        p_dest[i] = p_src[i];
			    }
			    SIL_FLASH_ClearWriteBufferAll(p_obj);

			}
		}
		
	}

	return err;
}

fsp_err_t SIL_FLASH_Enter2(sil_flash_s *obj) {
	
	fsp_err_t err = -1;
	sil_flash_s *p_obj = (sil_flash_s *)obj;

	(void) p_obj;


	return err;
}

void SIL_FLASH_MainLoop1(sil_flash_s *obj) {

    sil_flash_s *p_obj = (sil_flash_s *)obj;

    if (p_obj) SIL_FLASH_FlushWriteBuffer(p_obj);

}

void SIL_FLASH_MainLoop2(sil_flash_s *obj) {

    sil_flash_s *p_obj = (sil_flash_s *)obj;

    if (p_obj) SIL_FLASH_MainLoop1(p_obj);

}




