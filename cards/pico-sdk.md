# 貼上卡：RP2350 + pico-sdk 基礎
> 用法：一次只複製一張卡（兩條分隔線之間），貼進對話，再在下面寫你的問題。每張 ≤ 1200 字元。
> 來源：full/domain/pico-sdk.md、lite/domain/pico-sdk.md（詳細版）；stdio DTR 一條取自 lite/domain/host-mcu-comm.md｜最後更新 2026-11

---

【參考卡｜RP2350 pico-sdk 1/8｜CMake 模板與 PICO_BOARD/PLATFORM】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
RP2350（Pico 2），非 RP2040。pico-sdk 2.x。
```cmake
cmake_minimum_required(VERSION 3.13)
set(PICO_BOARD pico2 CACHE STRING "Board type")
# RISC-V：set(PICO_PLATFORM rp2350-riscv CACHE STRING "Platform")
include(pico_sdk_import.cmake)        # 必須在 project() 之前
project(my_app C CXX ASM)
pico_sdk_init()                       # project() 之後、add_executable 之前
add_executable(my_app main.c)
target_link_libraries(my_app pico_stdlib hardware_dma hardware_pio hardware_clocks)
pico_generate_pio_header(my_app ${CMAKE_CURRENT_LIST_DIR}/foo.pio)
pico_enable_stdio_usb(my_app 1)       # printf 走 USB CDC
pico_enable_stdio_uart(my_app 0)      # printf 走 UART0（GPIO0/1）
pico_add_extra_outputs(my_app)        # .uf2 / .bin / .hex / .dis
```
- `cmake .. -DPICO_BOARD=pico2`（Arm）；RISC-V 加 `-DPICO_PLATFORM=rp2350-riscv`；`make -j`。
- **沒設 board/platform → 預設 rp2040 + pico，Pico 2 不能跑**。cmake 輸出應有 `Target board (PICO_BOARD) is 'pico2'`。
- 換 board/platform 要 `rm -rf build`（cache 記住舊值）。
- 沒有 `pico2_riscv` 這個 board；`rp2350` = `rp2350-arm-s`（預設 Arm Secure）。
- `PICO_BOARD`/`PICO_PLATFORM` 要在 include(pico_sdk_import.cmake) 之前設，或用 -D 傳。

---

【參考卡｜RP2350 pico-sdk 2/8｜建置類型、輸出檔、燒錄】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
RP2350（Pico 2）。`pico_stdlib` **不含** `hardware_dma`、`hardware_pio`、`pico_multicore`，要自己 link，否則找不到標頭 / undefined reference。
Build type：
- `Release`（**SDK 預設**）：`-O3 -DNDEBUG`，SDK 另加 `-g`。量效能、交卷用。`NDEBUG` 會讓 assert 失效。
- `Debug`：`-Og -g`（`PICO_DEOPTIMIZED_DEBUG=1` 改 `-O0`）。`MinSizeRel`：`-Os`。`RelWithDebInfo`：`-O2 -g`。
- 與 judge 使用相同 build 設定；題目給 CMakeLists 就照抄。
Binary type（`pico_set_binary_type(target X)`）：
- `default`：在 flash 經 XIP cache 執行；cache miss 時慢。
- `copy_to_ram`：存在 flash，開機整份複製到 SRAM 執行；快、佔 SRAM、重開機仍在。
- `no_flash`：只載入 SRAM，斷電就沒了。
- 全域：`-DPICO_DEFAULT_BINARY_TYPE=copy_to_ram`。`blocked_ram` 是 RP2040 專用。
輸出檔：`.elf`（gdb、objdump、nm）、`.uf2`（拖進 BOOTSEL）、`.dis`（反組譯）、`<target>.elf.map`（位址與大小）。
燒錄：
- BOOTSEL：按住 BOOTSEL 插 USB → 出現磁碟機（名稱 `RP2350` ⚠️未在官方文件原文確認）→ 複製 `.uf2`。
- `picotool load -x my_app.uf2`（`-x` 燒完執行，`-v` 驗證，`-f` 讓有 USB stdio 且仍在跑的板子先自動重開進 BOOTSEL；程式卡死時 `-f` 無效）。
- `picotool info -a`、`picotool reboot -u`（進 BOOTSEL）、`picotool reboot -c riscv|arm`（選架構）。

---

【參考卡｜RP2350 pico-sdk 3/8｜晶片總覽與 RP2040 差異】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
RP2350（Raspberry Pi Pico 2 = RP2350A），**不是 RP2040**。RP2040 數值放括號。
- CPU：雙核 Cortex-M33 **或**雙核 Hazard3 RISC-V（開機選，同時只用一種）（RP2040：雙核 M0+）
- 預設 clk_sys 150 MHz（125）；XOSC 12 MHz
- SRAM 520 KB，10 bank（264 KB）；Boot ROM 32 KB（16 KB）；XIP cache 16 KB
- PIO：3 block × 4 SM = 12 SM（2×4）
- DMA：16 channel、4 條 IRQ（12 / 2）
- PWM 12 slice（8）；Timer：TIMER0+TIMER1 各 4 alarm（1 個 timer）
- UART/SPI/I2C 各 2；IRQ 數 52（32）
- **沒有硬體除法器**（`hardware_divider` 在 RP2350 是軟體）（RP2040 有 SIO divider）
- 浮點：M33 單精度 FPU + DCP 加速 double；**Hazard3 無 FPU** → 用固定點（RP2040 無 FPU）
- 新增：HSTX、TRNG、SHA-256、8 KB OTP、TrustZone、POWMAN
- GPIO：RP2350A 30 支、RP2350B 48 支
- Pico 2 板：LED = GPIO25（Pico 2 **W** 的 LED 在無線晶片，要 `cyw43_arch`）、4 MB flash、uart0 TX/RX = GPIO0/1、i2c0 SDA/SCL = GPIO4/5、spi0 RX/CSn/SCK/TX = GPIO16/17/18/19
- RP2350 pad 重置後是隔離（ISO）狀態，要經 `gpio_init` / `gpio_set_function` 才會動；直接寫 IO_BANK0 不呼叫 SDK 時腳可能沒反應
- ⚠️ RP2350-E9（A2 stepping）：輸入用內部 pull-down 可能異常 → 讀按鍵用 pull-up + 接地按鈕
- IRQ 編號與 RP2040 不同，一律用名稱（`DMA_IRQ_0`=10、`PIO0_IRQ_0`=15、`UART0_IRQ`=33）；RP2040 的 `TIMER_IRQ_0` 在 RP2350 叫 `TIMER0_IRQ_0`

---

【參考卡｜RP2350 pico-sdk 4/8｜記憶體映射與擺放巨集】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
RP2350（Pico 2）位址（RP2040 不同，勿混用）：
- ROM `0x00000000`（32 KB）；XIP flash（cached）`0x10000000`；XIP 不經 cache `0x14000000`
- SRAM `0x20000000`–`0x2007FFFF`：SRAM0–7 共 512 KB striped（SRAM0–3 起 0x20000000、SRAM4–7 起 0x20040000）
- SCRATCH_X `0x20080000`（4 KB，core 1 stack）、SCRATCH_Y `0x20081000`（4 KB，core 0 stack）
- APB `0x40000000`；AHB `0x50000000`（DMA 0x50000000、PIO0/1/2 0x50200000/0x50300000/0x50400000）；SIO `0xD0000000`；PPB（M33 NVIC/DWT）`0xE0000000`
- 原子別名：+0x1000 XOR、+0x2000 SET、+0x3000 CLR → `hw_xor_bits/hw_set_bits/hw_clear_bits(&reg, mask)`。SIO 不支援，GPIO 用 `sio_hw->gpio_set/gpio_clr/gpio_togl = mask`
- 預設 stack **每核 2 KB**（`PICO_STACK_SIZE=0x800`）→ 大陣列用 static/全域
擺放巨集：
- `void __not_in_flash_func(hot)(int n) {...}`：函式放 RAM（不阻止 inline，被 inline 進 flash 函式就跟著在 flash）
- `__time_critical_func(f)` 預設同上；`__no_inline_not_in_flash_func(f)` 放 RAM 且不 inline
- `static const uint32_t __not_in_flash("tbl") lut[256] = {...};`：資料放 RAM（const 也行）
- `uint32_t __scratch_x("buf") buf[256];`：放 scratch（需字串參數；會與 stack 搶空間）
- `const` 全域陣列預設在 flash；熱查表搬 RAM
- 檢查 `build/my_app.elf.map` 或 `arm-none-eabi-nm -n`：0x10… = flash、0x20… = RAM

---

【參考卡｜RP2350 pico-sdk 5/8｜計時與效能量測】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
RP2350（Pico 2）：預設 clk_sys 150 MHz → `time_us_*` 解析度 1 µs = 150 cycles。
原則：Release、先印 `clock_get_hz(clk_sys)`、暖機、重複 N 次取 min/中位數、區段內不 printf、結果寫 `volatile` sink（被測陣列本身不要 volatile）。短函式跑 1000 次再除。
```c
static volatile uint32_t sink;
sink = work();                                    // 暖機
uint64_t t0 = time_us_64();
sink = work();
uint64_t t1 = time_us_64();
uint32_t us = (uint32_t)(t1 - t0);
```
Cortex-M33 cycle counter（DWT）：
```c
#include "hardware/structs/m33.h"
m33_hw->demcr     |= M33_DEMCR_TRCENA_BITS;
m33_hw->dwt_cyccnt = 0;
m33_hw->dwt_ctrl  |= M33_DWT_CTRL_CYCCNTENA_BITS;
uint32_t c0 = m33_hw->dwt_cyccnt; f(); uint32_t dc = m33_hw->dwt_cyccnt - c0;
```
（150 MHz 約 28.6 秒溢位；SDK 預設 Secure 模式下可用 ⚠️未在實機驗證）
Hazard3 RISC-V：讀 `mcycle`/`mcycleh` CSR；**計數器預設停止**（`mcountinhibit` reset 值 0x5），量測前必須 `csrci mcountinhibit, 5`，否則讀數永遠不變。
- `time_us_32` 約 71.6 分鐘溢位，用 `time_us_64`。
- 中斷干擾：`uint32_t s = save_and_disable_interrupts(); ... restore_interrupts(s);`（關太久 USB 可能斷線）。
- 比預期慢：Debug build、flash cache miss、RISC-V 用 float/double、隱性 double（`0.5` 是 double，寫 `0.5f`）、clk_sys 不是你以為的值。
- 150 MHz 下 1 ms = 150,000 cycles。

---

【參考卡｜RP2350 pico-sdk 6/8｜stdio 與 GPIO 陷阱】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
RP2350（Pico 2），pico-sdk 2.x。
```c
#include <stdio.h>                       // printf 要自己 include（pico/stdlib.h 不含）
#include "pico/stdlib.h"
int main(void) {
    stdio_init_all();
    while (!stdio_usb_connected()) sleep_ms(10);   // 需要時才等
    printf("hello %d\n", 42);
    int c = getchar_timeout_us(100000);  // 逾時回 PICO_ERROR_TIMEOUT（用名稱比較）
    if (c != PICO_ERROR_TIMEOUT) putchar(c);
    stdio_flush();
}
```
- USB CDC：`stdio_usb_connected()` 看主機的 **DTR**；**未連線時輸出直接丟掉**，主機停止讀取 500 ms 後也丟。開機到主機開 port 之間的 printf 會消失 → 等 `stdio_usb_connected()` 或開頭 `sleep_ms(2000)`。
- 換行：judge 逐字比對時確認 `\n` 與 CRLF 轉換（`PICO_STDIO_DEFAULT_CRLF`）。
- printf 慢，不放計時區段或 ISR。`main` 不要 return，最後 `while (true)`。
- 開 `pico_enable_stdio_uart` 時 stdio 占用 uart0（GPIO0/1）。
GPIO：
```c
gpio_init(25); gpio_set_dir(25, GPIO_OUT); gpio_put(25, 1);
gpio_init(15); gpio_set_dir(15, GPIO_IN); gpio_pull_up(15);
gpio_set_function(2, GPIO_FUNC_PIO0);   // RP2350 另有 GPIO_FUNC_PIO2
sio_hw->gpio_togl = 1u << 25;            // 直接寫 SIO
```
- `gpio_init` 後輸入腳仍是 reset 的 pull-down。
- GPIO 中斷：`gpio_set_irq_enabled_with_callback(15, GPIO_IRQ_EDGE_FALL, true, &cb)`。

---

【參考卡｜RP2350 pico-sdk 7/8｜時脈、時間 API、中斷】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
RP2350（Pico 2）：預設 clk_sys 150 MHz（RP2040 125 MHz），`clock_get_hz(clk_sys)` 取實際值（link `hardware_clocks`）。
- `set_sys_clock_khz(khz, required)`：只接受 PLL 能精確產生的頻率；回 false 表示沒變；required=true 無法達成會 panic。
- 呼叫後 SDK 把 `clk_peri` 改接 48 MHz（PLL_USB）→ **先改時脈，再 `stdio_init_all()` / `uart_init`**，否則鮑率錯。
- 電壓預設 `VREG_VOLTAGE_1_10`；超過額定 150 MHz 不保證穩定，題目沒允許不要靠超頻。
時間 API：
- `time_us_32()`、`time_us_64()`、`get_absolute_time()`、`absolute_time_diff_us(from, to)`
- `sleep_ms/sleep_us`：**ISR 內不可呼叫**；`busy_wait_us/ms` 忙等
- `add_alarm_in_ms(ms, cb, ud, fire_if_past)`：cb 回 0 不重複、>0 從現在再等 µs、<0 從上次預定時間起算
- `add_repeating_timer_ms(delay, cb, ud, &timer)`：cb 回 true 繼續；**delay<0 = 固定週期**（start-to-start），>0 = 結束到開始的間隔；`repeating_timer_t` 要 static
- callback 在 IRQ context（預設 core 0）：不可 printf/sleep
中斷：
```c
irq_set_exclusive_handler(DMA_IRQ_0, my_handler);
irq_set_priority(DMA_IRQ_0, PICO_HIGHEST_IRQ_PRIORITY); // 數值越小越優先
irq_set_enabled(DMA_IRQ_0, true);
```
- 預設優先權 0x80；RP2350 高 4 bit 有效（RP2040 高 2 bit）。
- ISR：先清週邊旗標（否則一直重進）、要短、共享變數 `volatile`；時間關鍵 ISR 用 `__not_in_flash_func` 放 RAM。

---

【參考卡｜RP2350 pico-sdk 8/8｜除錯清單】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
RP2350（Pico 2），pico-sdk 2.x。
編譯 / CMake：
- `PICO_SDK_PATH` 未設 / 找不到 `pico_sdk_import.cmake` → export 路徑；從 `$PICO_SDK_PATH/external/` 複製。
- `pico_sdk_init` 未知指令 → include 要在 `project()` 前，`pico_sdk_init()` 在 `project()` 後。
- `hardware/dma.h: No such file` 或 `undefined reference` → 漏 link `hardware_dma`（pio、multicore、clocks 同理）。
- `foo.pio.h` 找不到 → 沒呼叫 `pico_generate_pio_header`。
- 編出 RP2040 程式 → 沒設 `-DPICO_BOARD=pico2`，並 `rm -rf build`。
- `region RAM overflowed` / `SCRATCH_Y overflowed` → 資料太大或 scratch 放太多。
- RP2040 名稱不存在（`TIMER_IRQ_0` 等）→ 改 RP2350 名稱。
- TinyUSB submodule 未初始化 → SDK 目錄 `git submodule update --init`，或改 UART stdio。
沒有輸出：
1. 確認是 RP2350 build；2. `pico_enable_stdio_usb(target 1)` + `stdio_init_all()`；3. USB 太早印（等 `stdio_usb_connected()`）；4. UART：GPIO0/1、115200、改時脈後重新 init；5. `main` return 了；6. Pico 2 W 的 LED 不在 GPIO25。
卡住 / 當機：
- 一進函式就掛 → stack overflow（每核只有 2 KB）→ 大陣列 static。
- 卡等待迴圈 → 旗標沒 volatile、ISR 沒觸發、DMA 沒 start。
- 中斷後不動 → ISR 沒清旗標。
- ISR / alarm callback 裡 `sleep_ms` → 改設旗標。
- 雙核卡死 → spinlock/mutex 沒放。
- 完全沒反應、`picotool -f` 失敗 → 手動 BOOTSEL 重插。
計時怪：0 → 被優化掉；第一次慢 → cache miss（暖機）；飄動 → USB 中斷（取 min）。
