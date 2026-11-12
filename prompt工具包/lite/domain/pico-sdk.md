# RP2350 + pico-sdk 基礎（精簡版）

- 用途：上機考速查；晶片、建置、API、量測、除錯
- 適用版本：RP2350 / Pico 2、pico-sdk 2.x
- 來源：github.com/raspberrypi/pico-sdk 原始碼；raspberrypi.com/documentation/pico-sdk 與 microcontrollers/silicon.html、pico-series.html；getting-started-with-pico.pdf；picotool README
- 最後更新：2026-11

## 晶片（與 RP2040 差異）
- 雙核 Cortex-M33 或雙核 Hazard3 RISC-V（開機選），預設 clk_sys 150 MHz（RP2040 125）
- SRAM 520 KB：0x20000000 起 512 KB striped（SRAM0-7）+ SCRATCH_X 0x20080000、SCRATCH_Y 0x20081000 各 4 KB
- ROM 0x00000000（32 KB）；XIP flash 0x10000000（cache 16 KB）；APB 0x40000000；AHB 0x50000000（DMA、PIO0/1/2）；SIO 0xD0000000
- 原子別名：+0x1000 XOR、+0x2000 SET、+0x3000 CLR → `hw_xor_bits/hw_set_bits/hw_clear_bits`（SIO 不支援，GPIO 用 `sio_hw->gpio_set/clr/togl`）
- SIO：GPIO set/clr/togl、FIFO、32 spinlock、每核 2 interpolator、doorbell、RISC-V mtime、TMDS。**無硬體除法器**（`hardware_divider` 為軟體）
- 3 PIO×4 SM、16 DMA ch、2 timer。RP2350A 30 GPIO / B 48 GPIO
- M33：單精度 FPU，double 由 DCP 加速。**Hazard3 無 FPU** → 用固定點
- Pico 2：LED=GPIO25（Pico 2 W 不是）、4 MB flash、UART0=GPIO0/1
- RP2350 pad 預設隔離，要經 `gpio_init`/`gpio_set_function` 才會動

## CMake
```cmake
cmake_minimum_required(VERSION 3.13)
set(PICO_BOARD pico2 CACHE STRING "")
include(pico_sdk_import.cmake)   # 在 project() 前
project(app C CXX ASM)
pico_sdk_init()
add_executable(app main.c)
target_link_libraries(app pico_stdlib hardware_dma hardware_pio)
pico_generate_pio_header(app ${CMAKE_CURRENT_LIST_DIR}/x.pio)
pico_enable_stdio_usb(app 1)
pico_enable_stdio_uart(app 0)
pico_add_extra_outputs(app)
```
- `cmake .. -DPICO_BOARD=pico2 [-DPICO_PLATFORM=rp2350-riscv]`；`make -j`
- 沒設 board/platform → 預設 rp2040！換設定要 `rm -rf build`
- 無 `pico2_riscv` board；`rp2350` = `rp2350-arm-s`
- `pico_stdlib` 不含 dma/pio/multicore，要自己 link
- 預設 Release（-O3）；Debug 為 -Og
- `pico_set_binary_type(app copy_to_ram|no_flash)`
- 輸出 .elf；`pico_add_extra_outputs` 才有 .uf2 .dis .elf.map；燒錄：BOOTSEL 拖 uf2，或 `picotool load -x app.uf2`（`-f` 強制重開）

## API
- `stdio_init_all()`；USB 開頭輸出易遺失→`sleep_ms(2000)`/`stdio_usb_connected()`
- `getchar_timeout_us(us)` 逾時回 `PICO_ERROR_TIMEOUT`
- GPIO：`gpio_init/set_dir/put/get/pull_up/set_function`；`sio_hw->gpio_set/clr/togl = mask`
- 時間：`time_us_32/64`、`absolute_time_diff_us`、`sleep_ms`（ISR 禁用）、`busy_wait_us`、`add_alarm_in_ms`、`add_repeating_timer_ms`（負值=固定週期）
- `clock_get_hz(clk_sys)`；`set_sys_clock_khz(khz, required)` 在 stdio_init_all 前
- IRQ：`irq_set_exclusive_handler`、`irq_set_priority`（小=優先）、`irq_set_enabled`；ISR 要清旗標、要短；用名稱（`DMA_IRQ_0`），編號與 RP2040 不同

## 記憶體與速度
- 預設在 flash 跑；cache miss 慢。熱函式 `__not_in_flash_func(f)` / `__time_critical_func(f)`；資料 `__not_in_flash("g")`、`__scratch_x("g")`
- stack 預設每核 2 KB（core0 在 SCRATCH_Y）→ 大陣列用 static
- `.elf.map`/`nm`：0x10… = flash、0x20… = RAM
- copy_to_ram：開機整份複製到 SRAM 執行（快、佔 RAM）；no_flash：只在 RAM，斷電消失
- 浮點：常數寫 `1.0f`（`0.5` 是 double）；RISC-V 用 Q16.16 固定點；除以 2 的冪改位移
- `const` 陣列在 flash；熱查表搬 RAM。DMA/32-bit 存取需對齊

## 量測
- Release、暖機、重複 N 次取 min/中位數；區段內不 printf
- 結果寫 `volatile` sink 防優化
- M33 cycle：`m33_hw->demcr|=M33_DEMCR_TRCENA_BITS; m33_hw->dwt_ctrl|=M33_DWT_CTRL_CYCCNTENA_BITS;` 讀 `m33_hw->dwt_cyccnt`；RISC-V 用 mcycle
- 先印 clk_sys；中斷干擾可短暫關中斷（`save_and_disable_interrupts()`/`restore_interrupts()`）
- time_us 解析度 1 µs = 150 cycles；短函式跑 1000 次再除
- 比預期慢：Debug build、flash cache miss、RISC-V 浮點、隱性 double

## 除錯
- 找不到 `hardware/x.h`/undefined reference → 漏 link
- 無輸出：stdio 沒啟用、USB 太早印、main return
- 當機：stack 爆、ISR 沒清旗標、旗標未 volatile、spinlock 沒放
- OJ：格式逐字、關 debug print、與 judge 相同設定編譯

## 其他檔
pico-dma.md、pio.md、riscv-hazard3.md、multicore-sync.md
