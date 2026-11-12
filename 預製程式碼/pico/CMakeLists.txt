# ============================================================
# Pico 2 (RP2350) 考試模板：一個 CMake 專案，編出好幾個小程式
# build:  mkdir build && cd build && cmake -DPICO_BOARD=pico2 .. && make -j
# RISC-V: cmake -DPICO_BOARD=pico2 -DPICO_PLATFORM=rp2350-riscv ..
# ============================================================
cmake_minimum_required(VERSION 3.13)

# 預設板子 = pico2（命令列 -DPICO_BOARD=xxx 可覆蓋）
if (NOT DEFINED PICO_BOARD)
    set(PICO_BOARD pico2)
endif()

include(pico_sdk_import.cmake)          # 從 SDK 的 external/ 複製來的，不用改
project(pico_templates C CXX ASM)
set(CMAKE_C_STANDARD 11)
pico_sdk_init()

# 共用小函式：建立一個 app，stdio 走 USB（不用 UART）
function(add_app name)
    add_executable(${name} ${ARGN})
    target_link_libraries(${name} pico_stdlib)
    target_compile_options(${name} PRIVATE -Wall -Wextra -Wno-unused-parameter)
    pico_enable_stdio_usb(${name} 1)     # printf / getchar 走 USB CDC
    pico_enable_stdio_uart(${name} 0)
    pico_add_extra_outputs(${name})      # 產生 .uf2 / .hex / .dis 等
endfunction()

# 1) 序列埠二進位協定（ECHO / SUM_U32 / CRC32）
add_app(app_serial app_serial.c serial_proto.c)
# 二進位傳輸：關掉 \n -> \r\n 自動轉換（不然資料會被改掉！）
target_compile_definitions(app_serial PRIVATE PICO_STDIO_DEFAULT_CRLF=0)
target_link_libraries(app_serial pico_multicore)  # TODO(改這裡) 想用雙核心時保留

# 2) 雙核心：FIFO、queue、spinlock、critical section、mutex
add_app(app_multicore app_multicore.c)
target_link_libraries(app_multicore pico_multicore pico_sync)

# 3) DMA：copy / fill / sniffer CRC32 / 計時比較
add_app(app_dma app_dma.c)
target_link_libraries(app_dma hardware_dma)

# 3b) DMA + PIO：用 DREQ 讓 DMA 跟著 PIO FIFO 的節奏搬資料
add_app(app_dma_pio app_dma_pio.c)
target_link_libraries(app_dma_pio hardware_dma hardware_pio)
pico_generate_pio_header(app_dma_pio ${CMAKE_CURRENT_LIST_DIR}/pio/echo.pio)

# 4) PIO：echo、位元流接收、移位輸出（含自我回環測試）
add_app(app_pio app_pio.c)
target_link_libraries(app_pio hardware_pio)
pico_generate_pio_header(app_pio ${CMAKE_CURRENT_LIST_DIR}/pio/echo.pio)
pico_generate_pio_header(app_pio ${CMAKE_CURRENT_LIST_DIR}/pio/bitstream_in.pio)
pico_generate_pio_header(app_pio ${CMAKE_CURRENT_LIST_DIR}/pio/shift_out.pio)
