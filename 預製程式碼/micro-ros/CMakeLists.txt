# CMakeLists.txt — 照官方 micro_ros_raspberrypi_pico_sdk（jazzy 分支）的 CMakeLists.txt 改的
# ✅ 編譯、連結通過（pico-sdk 2.2.0、PICO_BOARD=pico2、官方 jazzy libmicroros.a、arm-none-eabi-gcc 13.2）；沒燒錄、沒在板子上跑過
# 跟官方唯一的差別：多了 PICO_BOARD 預設、APP_SRC 選檔、pico_multicore、target 名稱 app。
# 用法：把本檔 + 你的 .c 放進官方 repo 資料夾（要有 libmicroros/、pico_uart_transport.c、
#       pico_uart_transports.h），然後：
#   export PICO_SDK_PATH=~/pico-sdk          # TODO(改這裡) 你的 pico-sdk 路徑（需含 lib/tinyusb）
#   mkdir build && cd build
#   cmake -DPICO_BOARD=pico2 ..              # Pico 2；舊 Pico 用 -DPICO_BOARD=pico
#   make -j4
#   → 得到 build/app.uf2，按住 BOOTSEL 插 USB，拖進 RP2350 / RPI-RP2 磁碟
cmake_minimum_required(VERSION 3.13)     # 官方寫 3.12；pico-sdk 2.x 要求 ≥ 3.13

# 板子要在 import SDK「之前」設定（命令列 -DPICO_BOARD=... 會蓋過這個預設）
# pico2 的 board header 會自動設 PICO_PLATFORM=rp2350 → 預設 rp2350-arm-s（Cortex-M33）
set(PICO_BOARD pico2 CACHE STRING "Board type")   # TODO(改這裡) pico / pico2

include($ENV{PICO_SDK_PATH}/external/pico_sdk_import.cmake)

project(app C CXX ASM)
set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)

pico_sdk_init()

# TODO(改這裡) 要編哪支程式就改這行：
#   pico_pingpong.c / pico_array_compute.c / pico_dualcore_micro_ros.c
#   ⚠ 換檔時 host_driver.py 的 MERGE 也要跟著改：pico_array_compute.c → "sorted"、pico_dualcore_micro_ros.c → "concat"
set(APP_SRC pico_array_compute.c)

link_directories(libmicroros)            # 預編好的 libmicroros.a 在這（官方寫法）
add_executable(app
    ${APP_SRC}
    pico_uart_transport.c                # 官方檔名（單數 transport.c，header 是複數 transports.h）
)
target_link_libraries(app
    pico_stdlib pico_unique_id           # unique_id：pico_pingpong.c 用板子序號當 ID
    pico_multicore                       # 雙核心版需要（其他版本連了也沒差）
    microros                             # = libmicroros/libmicroros.a（官方沒有別的 CMake target）
)
target_include_directories(app PUBLIC libmicroros/include)

SET(CMAKE_C_FLAGS   "${CMAKE_C_FLAGS} -ffunction-sections -fdata-sections")
SET(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -ffunction-sections -fdata-sections")

# micro-ROS 走 USB CDC 序列埠（/dev/ttyACM0）；UART 關掉（同官方）
pico_enable_stdio_usb(app 1)
pico_enable_stdio_uart(app 0)
# 二進位封包不能被自動加 \r（SDK 預設三個都是 1，會毀掉資料）→ 官方同樣關掉
add_compile_definitions(PICO_UART_ENABLE_CRLF_SUPPORT=0)
add_compile_definitions(PICO_STDIO_ENABLE_CRLF_SUPPORT=0)
add_compile_definitions(PICO_STDIO_DEFAULT_CRLF=0)

pico_add_extra_outputs(app)              # 產生 .uf2

# ---- Pico 2（RP2350）注意（詳見 README §6）----
# 官方預編 libmicroros.a 是用 -mcpu=cortex-m0plus -march=armv6-m 編的（toolchain.cmake），
# 官方 README 只寫支援 Pico（RP2040）；RP2350 支援 issue #1482 仍 open。
# 實測（2026-11-12，SDK 2.2.0、pico2）：M0+ 物件可以連進 M33 / -mfloat-abi=softfp 的程式，
# 本資料夾 3 支程式都連結成功，沒有缺 __atomic_*_4。換了 SDK 或改了程式後若出現
#   undefined reference to `__atomic_exchange_4'（或 _compare_exchange_4 / _fetch_add_4）
# → 照 README §6 加一個小檔補上；仍不行就重編 libmicroros（toolchain.cmake 改 -mcpu=cortex-m33）。
