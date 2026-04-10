################################################################################
# Automatically-generated file. Do not edit!
################################################################################

# Add inputs and outputs from these tool invocations to the build variables 
C_SRCS += \
../ra/arm/CMSIS-NN/Source/NNSupportFunctions/arm_nn_depthwise_conv_nt_t_padded_s8.c \
../ra/arm/CMSIS-NN/Source/NNSupportFunctions/arm_nn_depthwise_conv_nt_t_s16.c \
../ra/arm/CMSIS-NN/Source/NNSupportFunctions/arm_nn_depthwise_conv_nt_t_s4.c \
../ra/arm/CMSIS-NN/Source/NNSupportFunctions/arm_nn_depthwise_conv_nt_t_s8.c \
../ra/arm/CMSIS-NN/Source/NNSupportFunctions/arm_nn_lstm_calculate_gate_s16.c \
../ra/arm/CMSIS-NN/Source/NNSupportFunctions/arm_nn_lstm_calculate_gate_s8_s16.c \
../ra/arm/CMSIS-NN/Source/NNSupportFunctions/arm_nn_lstm_step_s16.c \
../ra/arm/CMSIS-NN/Source/NNSupportFunctions/arm_nn_lstm_step_s8.c \
../ra/arm/CMSIS-NN/Source/NNSupportFunctions/arm_nn_mat_mul_core_1x_s4.c \
../ra/arm/CMSIS-NN/Source/NNSupportFunctions/arm_nn_mat_mul_core_1x_s8.c \
../ra/arm/CMSIS-NN/Source/NNSupportFunctions/arm_nn_mat_mul_core_4x_s8.c \
../ra/arm/CMSIS-NN/Source/NNSupportFunctions/arm_nn_mat_mult_nt_interleaved_t_even_s4.c \
../ra/arm/CMSIS-NN/Source/NNSupportFunctions/arm_nn_mat_mult_nt_t_s16.c \
../ra/arm/CMSIS-NN/Source/NNSupportFunctions/arm_nn_mat_mult_nt_t_s4.c \
../ra/arm/CMSIS-NN/Source/NNSupportFunctions/arm_nn_mat_mult_nt_t_s8.c \
../ra/arm/CMSIS-NN/Source/NNSupportFunctions/arm_nn_mat_mult_nt_t_s8_s32.c \
../ra/arm/CMSIS-NN/Source/NNSupportFunctions/arm_nn_transpose_conv_row_s8_s32.c \
../ra/arm/CMSIS-NN/Source/NNSupportFunctions/arm_nn_vec_mat_mul_result_acc_s16.c \
../ra/arm/CMSIS-NN/Source/NNSupportFunctions/arm_nn_vec_mat_mul_result_acc_s8_s16.c \
../ra/arm/CMSIS-NN/Source/NNSupportFunctions/arm_nn_vec_mat_mult_t_per_ch_s8.c \
../ra/arm/CMSIS-NN/Source/NNSupportFunctions/arm_nn_vec_mat_mult_t_s16.c \
../ra/arm/CMSIS-NN/Source/NNSupportFunctions/arm_nn_vec_mat_mult_t_s16_s16.c \
../ra/arm/CMSIS-NN/Source/NNSupportFunctions/arm_nn_vec_mat_mult_t_s4.c \
../ra/arm/CMSIS-NN/Source/NNSupportFunctions/arm_nn_vec_mat_mult_t_s8.c \
../ra/arm/CMSIS-NN/Source/NNSupportFunctions/arm_nn_vec_mat_mult_t_svdf_s8.c \
../ra/arm/CMSIS-NN/Source/NNSupportFunctions/arm_nntables.c \
../ra/arm/CMSIS-NN/Source/NNSupportFunctions/arm_q7_to_q15_with_offset.c \
../ra/arm/CMSIS-NN/Source/NNSupportFunctions/arm_s8_to_s16_unordered_with_offset.c 

SREC += \
sil_ultra_slow_jogging.srec 

C_DEPS += \
./ra/arm/CMSIS-NN/Source/NNSupportFunctions/arm_nn_depthwise_conv_nt_t_padded_s8.d \
./ra/arm/CMSIS-NN/Source/NNSupportFunctions/arm_nn_depthwise_conv_nt_t_s16.d \
./ra/arm/CMSIS-NN/Source/NNSupportFunctions/arm_nn_depthwise_conv_nt_t_s4.d \
./ra/arm/CMSIS-NN/Source/NNSupportFunctions/arm_nn_depthwise_conv_nt_t_s8.d \
./ra/arm/CMSIS-NN/Source/NNSupportFunctions/arm_nn_lstm_calculate_gate_s16.d \
./ra/arm/CMSIS-NN/Source/NNSupportFunctions/arm_nn_lstm_calculate_gate_s8_s16.d \
./ra/arm/CMSIS-NN/Source/NNSupportFunctions/arm_nn_lstm_step_s16.d \
./ra/arm/CMSIS-NN/Source/NNSupportFunctions/arm_nn_lstm_step_s8.d \
./ra/arm/CMSIS-NN/Source/NNSupportFunctions/arm_nn_mat_mul_core_1x_s4.d \
./ra/arm/CMSIS-NN/Source/NNSupportFunctions/arm_nn_mat_mul_core_1x_s8.d \
./ra/arm/CMSIS-NN/Source/NNSupportFunctions/arm_nn_mat_mul_core_4x_s8.d \
./ra/arm/CMSIS-NN/Source/NNSupportFunctions/arm_nn_mat_mult_nt_interleaved_t_even_s4.d \
./ra/arm/CMSIS-NN/Source/NNSupportFunctions/arm_nn_mat_mult_nt_t_s16.d \
./ra/arm/CMSIS-NN/Source/NNSupportFunctions/arm_nn_mat_mult_nt_t_s4.d \
./ra/arm/CMSIS-NN/Source/NNSupportFunctions/arm_nn_mat_mult_nt_t_s8.d \
./ra/arm/CMSIS-NN/Source/NNSupportFunctions/arm_nn_mat_mult_nt_t_s8_s32.d \
./ra/arm/CMSIS-NN/Source/NNSupportFunctions/arm_nn_transpose_conv_row_s8_s32.d \
./ra/arm/CMSIS-NN/Source/NNSupportFunctions/arm_nn_vec_mat_mul_result_acc_s16.d \
./ra/arm/CMSIS-NN/Source/NNSupportFunctions/arm_nn_vec_mat_mul_result_acc_s8_s16.d \
./ra/arm/CMSIS-NN/Source/NNSupportFunctions/arm_nn_vec_mat_mult_t_per_ch_s8.d \
./ra/arm/CMSIS-NN/Source/NNSupportFunctions/arm_nn_vec_mat_mult_t_s16.d \
./ra/arm/CMSIS-NN/Source/NNSupportFunctions/arm_nn_vec_mat_mult_t_s16_s16.d \
./ra/arm/CMSIS-NN/Source/NNSupportFunctions/arm_nn_vec_mat_mult_t_s4.d \
./ra/arm/CMSIS-NN/Source/NNSupportFunctions/arm_nn_vec_mat_mult_t_s8.d \
./ra/arm/CMSIS-NN/Source/NNSupportFunctions/arm_nn_vec_mat_mult_t_svdf_s8.d \
./ra/arm/CMSIS-NN/Source/NNSupportFunctions/arm_nntables.d \
./ra/arm/CMSIS-NN/Source/NNSupportFunctions/arm_q7_to_q15_with_offset.d \
./ra/arm/CMSIS-NN/Source/NNSupportFunctions/arm_s8_to_s16_unordered_with_offset.d 

OBJS += \
./ra/arm/CMSIS-NN/Source/NNSupportFunctions/arm_nn_depthwise_conv_nt_t_padded_s8.o \
./ra/arm/CMSIS-NN/Source/NNSupportFunctions/arm_nn_depthwise_conv_nt_t_s16.o \
./ra/arm/CMSIS-NN/Source/NNSupportFunctions/arm_nn_depthwise_conv_nt_t_s4.o \
./ra/arm/CMSIS-NN/Source/NNSupportFunctions/arm_nn_depthwise_conv_nt_t_s8.o \
./ra/arm/CMSIS-NN/Source/NNSupportFunctions/arm_nn_lstm_calculate_gate_s16.o \
./ra/arm/CMSIS-NN/Source/NNSupportFunctions/arm_nn_lstm_calculate_gate_s8_s16.o \
./ra/arm/CMSIS-NN/Source/NNSupportFunctions/arm_nn_lstm_step_s16.o \
./ra/arm/CMSIS-NN/Source/NNSupportFunctions/arm_nn_lstm_step_s8.o \
./ra/arm/CMSIS-NN/Source/NNSupportFunctions/arm_nn_mat_mul_core_1x_s4.o \
./ra/arm/CMSIS-NN/Source/NNSupportFunctions/arm_nn_mat_mul_core_1x_s8.o \
./ra/arm/CMSIS-NN/Source/NNSupportFunctions/arm_nn_mat_mul_core_4x_s8.o \
./ra/arm/CMSIS-NN/Source/NNSupportFunctions/arm_nn_mat_mult_nt_interleaved_t_even_s4.o \
./ra/arm/CMSIS-NN/Source/NNSupportFunctions/arm_nn_mat_mult_nt_t_s16.o \
./ra/arm/CMSIS-NN/Source/NNSupportFunctions/arm_nn_mat_mult_nt_t_s4.o \
./ra/arm/CMSIS-NN/Source/NNSupportFunctions/arm_nn_mat_mult_nt_t_s8.o \
./ra/arm/CMSIS-NN/Source/NNSupportFunctions/arm_nn_mat_mult_nt_t_s8_s32.o \
./ra/arm/CMSIS-NN/Source/NNSupportFunctions/arm_nn_transpose_conv_row_s8_s32.o \
./ra/arm/CMSIS-NN/Source/NNSupportFunctions/arm_nn_vec_mat_mul_result_acc_s16.o \
./ra/arm/CMSIS-NN/Source/NNSupportFunctions/arm_nn_vec_mat_mul_result_acc_s8_s16.o \
./ra/arm/CMSIS-NN/Source/NNSupportFunctions/arm_nn_vec_mat_mult_t_per_ch_s8.o \
./ra/arm/CMSIS-NN/Source/NNSupportFunctions/arm_nn_vec_mat_mult_t_s16.o \
./ra/arm/CMSIS-NN/Source/NNSupportFunctions/arm_nn_vec_mat_mult_t_s16_s16.o \
./ra/arm/CMSIS-NN/Source/NNSupportFunctions/arm_nn_vec_mat_mult_t_s4.o \
./ra/arm/CMSIS-NN/Source/NNSupportFunctions/arm_nn_vec_mat_mult_t_s8.o \
./ra/arm/CMSIS-NN/Source/NNSupportFunctions/arm_nn_vec_mat_mult_t_svdf_s8.o \
./ra/arm/CMSIS-NN/Source/NNSupportFunctions/arm_nntables.o \
./ra/arm/CMSIS-NN/Source/NNSupportFunctions/arm_q7_to_q15_with_offset.o \
./ra/arm/CMSIS-NN/Source/NNSupportFunctions/arm_s8_to_s16_unordered_with_offset.o 

MAP += \
sil_ultra_slow_jogging.map 


# Each subdirectory must supply rules for building sources it contributes
ra/arm/CMSIS-NN/Source/NNSupportFunctions/%.o: ../ra/arm/CMSIS-NN/Source/NNSupportFunctions/%.c
	$(file > $@.in,-mcpu=cortex-m33 -mthumb -mfloat-abi=hard -mfpu=fpv5-sp-d16 -Oz -fmessage-length=0 -fsigned-char -ffunction-sections -fdata-sections -fno-strict-aliasing -Wunused -Wuninitialized -Wall -Wextra -Wmissing-declarations -Wconversion -Wpointer-arith -Wshadow -Wlogical-op -Waggregate-return -Wfloat-equal -g -D_RENESAS_RA_ -D_RA_ORDINAL=1 -DQE_TOUCH_CONFIGURATION -D_RA_CORE=CM33 -DCMSIS_NN -DARM_MATH_CM33 -DCMSIS_NN -DOPTIMIZED_KERNEL_DIR=cmsis_nn -I"C:/Users/USE/Desktop/SEAN_CODE/CNN_station_breathe/cnn_mcu_v1/sil_ultra_slow_jogging/sil_ultra_slow_jogging/ra_gen" -I"." -I"C:/Users/USE/Desktop/SEAN_CODE/CNN_station_breathe/cnn_mcu_v1/sil_ultra_slow_jogging/sil_ultra_slow_jogging/ra_cfg/fsp_cfg/bsp" -I"C:/Users/USE/Desktop/SEAN_CODE/CNN_station_breathe/cnn_mcu_v1/sil_ultra_slow_jogging/sil_ultra_slow_jogging/ra_cfg/fsp_cfg" -I"C:/Users/USE/Desktop/SEAN_CODE/CNN_station_breathe/cnn_mcu_v1/sil_ultra_slow_jogging/sil_ultra_slow_jogging/src" -I"C:/Users/USE/Desktop/SEAN_CODE/CNN_station_breathe/cnn_mcu_v1/sil_ultra_slow_jogging/sil_ultra_slow_jogging/sil_all" -I"C:/Users/USE/Desktop/SEAN_CODE/CNN_station_breathe/cnn_mcu_v1/sil_ultra_slow_jogging/sil_ultra_slow_jogging/ra/fsp/inc" -I"C:/Users/USE/Desktop/SEAN_CODE/CNN_station_breathe/cnn_mcu_v1/sil_ultra_slow_jogging/sil_ultra_slow_jogging/ra/fsp/inc/api" -I"C:/Users/USE/Desktop/SEAN_CODE/CNN_station_breathe/cnn_mcu_v1/sil_ultra_slow_jogging/sil_ultra_slow_jogging/ra/fsp/inc/instances" -I"C:/Users/USE/Desktop/SEAN_CODE/CNN_station_breathe/cnn_mcu_v1/sil_ultra_slow_jogging/sil_ultra_slow_jogging/ra/arm/CMSIS_6/CMSIS/Core/Include" -I"C:/Users/USE/Desktop/SEAN_CODE/CNN_station_breathe/cnn_mcu_v1/sil_ultra_slow_jogging/sil_ultra_slow_jogging/qe_gen" -I"C:/Users/USE/Desktop/SEAN_CODE/CNN_station_breathe/cnn_mcu_v1/sil_ultra_slow_jogging/sil_ultra_slow_jogging/ra/arm/CMSIS-NN/Include" -I"C:/Users/USE/Desktop/SEAN_CODE/CNN_station_breathe/cnn_mcu_v1/sil_ultra_slow_jogging/sil_ultra_slow_jogging/ra/arm/CMSIS-NN" -I"C:/Users/USE/Desktop/SEAN_CODE/CNN_station_breathe/cnn_mcu_v1/sil_ultra_slow_jogging/sil_ultra_slow_jogging/ra/arm/CMSIS-DSP/PrivateInclude" -I"C:/Users/USE/Desktop/SEAN_CODE/CNN_station_breathe/cnn_mcu_v1/sil_ultra_slow_jogging/sil_ultra_slow_jogging/ra/arm/CMSIS-DSP/Include" -I"C:/Users/USE/Desktop/SEAN_CODE/CNN_station_breathe/cnn_mcu_v1/sil_ultra_slow_jogging/sil_ultra_slow_jogging/ra_gen" -I"C:/Users/USE/Desktop/SEAN_CODE/CNN_station_breathe/cnn_mcu_v1/sil_ultra_slow_jogging/sil_ultra_slow_jogging/ra/fsp/inc" -I"C:/Users/USE/Desktop/SEAN_CODE/CNN_station_breathe/cnn_mcu_v1/sil_ultra_slow_jogging/sil_ultra_slow_jogging/ra/fsp/inc/api" -I"C:/Users/USE/Desktop/SEAN_CODE/CNN_station_breathe/cnn_mcu_v1/sil_ultra_slow_jogging/sil_ultra_slow_jogging/sil_all" -I"C:/Users/USE/Desktop/SEAN_CODE/CNN_station_breathe/cnn_mcu_v1/sil_ultra_slow_jogging/sil_ultra_slow_jogging/qe_gen" -I"C:/Users/USE/Desktop/SEAN_CODE/CNN_station_breathe/cnn_mcu_v1/sil_ultra_slow_jogging/sil_ultra_slow_jogging/ra/arm/CMSIS_6/CMSIS/Core/Include" -I"C:/Users/USE/Desktop/SEAN_CODE/CNN_station_breathe/cnn_mcu_v1/sil_ultra_slow_jogging/sil_ultra_slow_jogging/ra/npu/ruy" -I"C:/Users/USE/Desktop/SEAN_CODE/CNN_station_breathe/cnn_mcu_v1/sil_ultra_slow_jogging/sil_ultra_slow_jogging/ra/npu/gemmlowp" -I"C:/Users/USE/Desktop/SEAN_CODE/CNN_station_breathe/cnn_mcu_v1/sil_ultra_slow_jogging/sil_ultra_slow_jogging/ra/npu/tflite-micro" -I"C:/Users/USE/Desktop/SEAN_CODE/CNN_station_breathe/cnn_mcu_v1/sil_ultra_slow_jogging/sil_ultra_slow_jogging/ra/npu/ethos-u-core-software/lib/crc/include" -I"C:/Users/USE/Desktop/SEAN_CODE/CNN_station_breathe/cnn_mcu_v1/sil_ultra_slow_jogging/sil_ultra_slow_jogging/ra/npu/ethos-u-core-software/lib/arm_profiler/include" -I"C:/Users/USE/Desktop/SEAN_CODE/CNN_station_breathe/cnn_mcu_v1/sil_ultra_slow_jogging/sil_ultra_slow_jogging/ra/arm/CMSIS-View/EventRecorder/Include" -I"C:/Users/USE/Desktop/SEAN_CODE/CNN_station_breathe/cnn_mcu_v1/sil_ultra_slow_jogging/sil_ultra_slow_jogging/ra/arm/CMSIS-View/EventRecorder/Config" -I"C:/Users/USE/Desktop/SEAN_CODE/CNN_station_breathe/cnn_mcu_v1/sil_ultra_slow_jogging/sil_ultra_slow_jogging/ra/npu/flatbuffers/include" -std=c99 -Wno-stringop-overflow -Wno-format-truncation -w --param=min-pagesize=0 -MMD -MP -MF"$(@:%.o=%.d)" -MT"$@" -c -o "$@" -x c "$<")
	@echo Building file: $< && arm-none-eabi-gcc @"$@.in"

