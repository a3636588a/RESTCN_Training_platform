################################################################################
# Automatically-generated file. Do not edit!
################################################################################

# Add inputs and outputs from these tool invocations to the build variables 
CC_SRCS += \
../ra/npu/tflite-micro/tensorflow/lite/micro/kernels/cmsis_nn/add.cc \
../ra/npu/tflite-micro/tensorflow/lite/micro/kernels/cmsis_nn/batch_matmul.cc \
../ra/npu/tflite-micro/tensorflow/lite/micro/kernels/cmsis_nn/conv.cc \
../ra/npu/tflite-micro/tensorflow/lite/micro/kernels/cmsis_nn/depthwise_conv.cc \
../ra/npu/tflite-micro/tensorflow/lite/micro/kernels/cmsis_nn/fully_connected.cc \
../ra/npu/tflite-micro/tensorflow/lite/micro/kernels/cmsis_nn/maximum_minimum.cc \
../ra/npu/tflite-micro/tensorflow/lite/micro/kernels/cmsis_nn/mul.cc \
../ra/npu/tflite-micro/tensorflow/lite/micro/kernels/cmsis_nn/pooling.cc \
../ra/npu/tflite-micro/tensorflow/lite/micro/kernels/cmsis_nn/softmax.cc \
../ra/npu/tflite-micro/tensorflow/lite/micro/kernels/cmsis_nn/svdf.cc \
../ra/npu/tflite-micro/tensorflow/lite/micro/kernels/cmsis_nn/transpose_conv.cc \
../ra/npu/tflite-micro/tensorflow/lite/micro/kernels/cmsis_nn/unidirectional_sequence_lstm.cc 

SREC += \
sil_ultra_slow_jogging.srec 

CC_DEPS += \
./ra/npu/tflite-micro/tensorflow/lite/micro/kernels/cmsis_nn/add.d \
./ra/npu/tflite-micro/tensorflow/lite/micro/kernels/cmsis_nn/batch_matmul.d \
./ra/npu/tflite-micro/tensorflow/lite/micro/kernels/cmsis_nn/conv.d \
./ra/npu/tflite-micro/tensorflow/lite/micro/kernels/cmsis_nn/depthwise_conv.d \
./ra/npu/tflite-micro/tensorflow/lite/micro/kernels/cmsis_nn/fully_connected.d \
./ra/npu/tflite-micro/tensorflow/lite/micro/kernels/cmsis_nn/maximum_minimum.d \
./ra/npu/tflite-micro/tensorflow/lite/micro/kernels/cmsis_nn/mul.d \
./ra/npu/tflite-micro/tensorflow/lite/micro/kernels/cmsis_nn/pooling.d \
./ra/npu/tflite-micro/tensorflow/lite/micro/kernels/cmsis_nn/softmax.d \
./ra/npu/tflite-micro/tensorflow/lite/micro/kernels/cmsis_nn/svdf.d \
./ra/npu/tflite-micro/tensorflow/lite/micro/kernels/cmsis_nn/transpose_conv.d \
./ra/npu/tflite-micro/tensorflow/lite/micro/kernels/cmsis_nn/unidirectional_sequence_lstm.d 

OBJS += \
./ra/npu/tflite-micro/tensorflow/lite/micro/kernels/cmsis_nn/add.o \
./ra/npu/tflite-micro/tensorflow/lite/micro/kernels/cmsis_nn/batch_matmul.o \
./ra/npu/tflite-micro/tensorflow/lite/micro/kernels/cmsis_nn/conv.o \
./ra/npu/tflite-micro/tensorflow/lite/micro/kernels/cmsis_nn/depthwise_conv.o \
./ra/npu/tflite-micro/tensorflow/lite/micro/kernels/cmsis_nn/fully_connected.o \
./ra/npu/tflite-micro/tensorflow/lite/micro/kernels/cmsis_nn/maximum_minimum.o \
./ra/npu/tflite-micro/tensorflow/lite/micro/kernels/cmsis_nn/mul.o \
./ra/npu/tflite-micro/tensorflow/lite/micro/kernels/cmsis_nn/pooling.o \
./ra/npu/tflite-micro/tensorflow/lite/micro/kernels/cmsis_nn/softmax.o \
./ra/npu/tflite-micro/tensorflow/lite/micro/kernels/cmsis_nn/svdf.o \
./ra/npu/tflite-micro/tensorflow/lite/micro/kernels/cmsis_nn/transpose_conv.o \
./ra/npu/tflite-micro/tensorflow/lite/micro/kernels/cmsis_nn/unidirectional_sequence_lstm.o 

MAP += \
sil_ultra_slow_jogging.map 


# Each subdirectory must supply rules for building sources it contributes
ra/npu/tflite-micro/tensorflow/lite/micro/kernels/cmsis_nn/%.o: ../ra/npu/tflite-micro/tensorflow/lite/micro/kernels/cmsis_nn/%.cc
	$(file > $@.in,-mcpu=cortex-m33 -mthumb -mfloat-abi=hard -mfpu=fpv5-sp-d16 -Oz -fmessage-length=0 -fsigned-char -ffunction-sections -fdata-sections -fno-strict-aliasing -Wunused -Wuninitialized -Wall -Wextra -Wmissing-declarations -Wconversion -Wpointer-arith -Wshadow -Wlogical-op -Waggregate-return -Wfloat-equal -g -D_RA_CORE=CM33 -D_RA_ORDINAL=1 -DCMSIS_NN -DARM_MATH_CM33 -DCMSIS_NN -DOPTIMIZED_KERNEL_DIR=cmsis_nn -I"C:/Users/USE/Desktop/SEAN_CODE/CNN_station_breathe/cnn_mcu_v1/sil_ultra_slow_jogging/sil_ultra_slow_jogging/ra_gen" -I"." -I"C:/Users/USE/Desktop/SEAN_CODE/CNN_station_breathe/cnn_mcu_v1/sil_ultra_slow_jogging/sil_ultra_slow_jogging/ra_cfg/fsp_cfg/bsp" -I"C:/Users/USE/Desktop/SEAN_CODE/CNN_station_breathe/cnn_mcu_v1/sil_ultra_slow_jogging/sil_ultra_slow_jogging/ra_cfg/fsp_cfg" -I"C:/Users/USE/Desktop/SEAN_CODE/CNN_station_breathe/cnn_mcu_v1/sil_ultra_slow_jogging/sil_ultra_slow_jogging/src" -I"C:/Users/USE/Desktop/SEAN_CODE/CNN_station_breathe/cnn_mcu_v1/sil_ultra_slow_jogging/sil_ultra_slow_jogging/sil_all" -I"C:/Users/USE/Desktop/SEAN_CODE/CNN_station_breathe/cnn_mcu_v1/sil_ultra_slow_jogging/sil_ultra_slow_jogging/ra/fsp/inc" -I"C:/Users/USE/Desktop/SEAN_CODE/CNN_station_breathe/cnn_mcu_v1/sil_ultra_slow_jogging/sil_ultra_slow_jogging/ra/fsp/inc/api" -I"C:/Users/USE/Desktop/SEAN_CODE/CNN_station_breathe/cnn_mcu_v1/sil_ultra_slow_jogging/sil_ultra_slow_jogging/ra/fsp/inc/instances" -I"C:/Users/USE/Desktop/SEAN_CODE/CNN_station_breathe/cnn_mcu_v1/sil_ultra_slow_jogging/sil_ultra_slow_jogging/ra/arm/CMSIS_6/CMSIS/Core/Include" -I"C:/Users/USE/Desktop/SEAN_CODE/CNN_station_breathe/cnn_mcu_v1/sil_ultra_slow_jogging/sil_ultra_slow_jogging/qe_gen" -I"C:/Users/USE/Desktop/SEAN_CODE/CNN_station_breathe/cnn_mcu_v1/sil_ultra_slow_jogging/sil_ultra_slow_jogging/ra/arm/CMSIS-NN/Include" -I"C:/Users/USE/Desktop/SEAN_CODE/CNN_station_breathe/cnn_mcu_v1/sil_ultra_slow_jogging/sil_ultra_slow_jogging/ra/arm/CMSIS-NN" -I"C:/Users/USE/Desktop/SEAN_CODE/CNN_station_breathe/cnn_mcu_v1/sil_ultra_slow_jogging/sil_ultra_slow_jogging/ra/arm/CMSIS-DSP/PrivateInclude" -I"C:/Users/USE/Desktop/SEAN_CODE/CNN_station_breathe/cnn_mcu_v1/sil_ultra_slow_jogging/sil_ultra_slow_jogging/ra/arm/CMSIS-DSP/Include" -I"C:/Users/USE/Desktop/SEAN_CODE/CNN_station_breathe/cnn_mcu_v1/sil_ultra_slow_jogging/sil_ultra_slow_jogging/ra_gen" -I"C:/Users/USE/Desktop/SEAN_CODE/CNN_station_breathe/cnn_mcu_v1/sil_ultra_slow_jogging/sil_ultra_slow_jogging/ra/fsp/inc" -I"C:/Users/USE/Desktop/SEAN_CODE/CNN_station_breathe/cnn_mcu_v1/sil_ultra_slow_jogging/sil_ultra_slow_jogging/ra/fsp/inc/api" -I"C:/Users/USE/Desktop/SEAN_CODE/CNN_station_breathe/cnn_mcu_v1/sil_ultra_slow_jogging/sil_ultra_slow_jogging/sil_all" -I"C:/Users/USE/Desktop/SEAN_CODE/CNN_station_breathe/cnn_mcu_v1/sil_ultra_slow_jogging/sil_ultra_slow_jogging/qe_gen" -I"C:/Users/USE/Desktop/SEAN_CODE/CNN_station_breathe/cnn_mcu_v1/sil_ultra_slow_jogging/sil_ultra_slow_jogging/ra/arm/CMSIS_6/CMSIS/Core/Include" -I"C:/Users/USE/Desktop/SEAN_CODE/CNN_station_breathe/cnn_mcu_v1/sil_ultra_slow_jogging/sil_ultra_slow_jogging/ra/npu/ruy" -I"C:/Users/USE/Desktop/SEAN_CODE/CNN_station_breathe/cnn_mcu_v1/sil_ultra_slow_jogging/sil_ultra_slow_jogging/ra/npu" -I"C:/Users/USE/Desktop/SEAN_CODE/CNN_station_breathe/cnn_mcu_v1/sil_ultra_slow_jogging/sil_ultra_slow_jogging/ra/npu/gemmlowp" -I"C:/Users/USE/Desktop/SEAN_CODE/CNN_station_breathe/cnn_mcu_v1/sil_ultra_slow_jogging/sil_ultra_slow_jogging/ra/npu/tflite-micro" -I"C:/Users/USE/Desktop/SEAN_CODE/CNN_station_breathe/cnn_mcu_v1/sil_ultra_slow_jogging/sil_ultra_slow_jogging/ra/npu/ethos-u-core-software/lib/crc/include" -I"C:/Users/USE/Desktop/SEAN_CODE/CNN_station_breathe/cnn_mcu_v1/sil_ultra_slow_jogging/sil_ultra_slow_jogging/ra/npu/ethos-u-core-software/lib/arm_profiler/include" -I"C:/Users/USE/Desktop/SEAN_CODE/CNN_station_breathe/cnn_mcu_v1/sil_ultra_slow_jogging/sil_ultra_slow_jogging/ra/arm/CMSIS-View/EventRecorder/Include" -I"C:/Users/USE/Desktop/SEAN_CODE/CNN_station_breathe/cnn_mcu_v1/sil_ultra_slow_jogging/sil_ultra_slow_jogging/ra/arm/CMSIS-View/EventRecorder/Config" -I"C:/Users/USE/Desktop/SEAN_CODE/CNN_station_breathe/cnn_mcu_v1/sil_ultra_slow_jogging/sil_ultra_slow_jogging/ra/npu/flatbuffers/include" -std=c++17 -fabi-version=0 -Wno-stringop-overflow -Wno-format-truncation -w --param=min-pagesize=0 -MMD -MP -MF"$(@:%.o=%.d)" -MT"$@" -c -o "$@" -x c++ "$<")
	@echo Building file: $< && arm-none-eabi-g++ @"$@.in"

