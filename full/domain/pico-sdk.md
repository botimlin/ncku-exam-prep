# RP2350 + pico-sdk 基礎：晶片架構、建置系統與效能量測

- 用途：上機考（成大資工特殊選才）參考資料。給「考場 LLM」當 context，也給考生自己查。涵蓋 RP2350 晶片架構、pico-sdk 專案結構與 CMake 建置、燒錄、核心 API、記憶體擺放與速度、在板子上量測效能的方法、除錯與優化清單。DMA / PIO / RISC-V 組語 / 多核心同步只放指標，細節見同目錄其他檔案。
- 適用版本：RP2350（Raspberry Pi Pico 2，RP2350A）；pico-sdk 2.x（查證時 GitHub master，最新 release 為 2.3.1）。與 RP2040（Pico 1）不同之處會特別標註。
- 來源（實際查閱）：
  - pico-sdk GitHub 原始碼：https://github.com/raspberrypi/pico-sdk （`README.md`、`src/rp2350/hardware_regs/include/hardware/regs/addressmap.h`、`.../platform_defs.h`、`.../structs/sio.h`、`.../structs/m33.h`、`src/rp2_common/hardware_divider/include/hardware/divider.h`、`hardware_clocks/clocks.h`、`clocks.c`、`hardware_gpio/gpio.h`、`gpio.c`、`hardware_irq/irq.h`、`hardware_vreg/vreg.h`、`pico_platform_sections/.../sections.h`、`pico_platform_common/.../common.h`、`pico_standard_link/CMakeLists.txt` 與 linker script includes、`src/rp2350/pico_platform/script_include/default_locations.ld`、`src/boards/include/boards/pico2.h`、`cmake/pico_pre_load_platform.cmake`、`cmake/pico_pre_load_toolchain.cmake`、`cmake/preload/platforms/*.cmake`、`cmake/preload/toolchains/*.cmake`、`pico_float/CMakeLists.txt`、`pico_double/CMakeLists.txt`、`pico_stdlib/CMakeLists.txt`、`pico_time/time.h`、`hardware_timer/timer.h`、`pico_stdio/stdio.h`、`pico_stdio_usb/stdio_usb.h`）
  - pico-sdk 文件：https://www.raspberrypi.com/documentation/pico-sdk/hardware.html
  - RP2350 規格頁：https://www.raspberrypi.com/documentation/microcontrollers/silicon.html
  - Pico 系列板子頁：https://www.raspberrypi.com/documentation/microcontrollers/pico-series.html
  - Getting started with Raspberry Pi Pico-series（PDF）：https://datasheets.raspberrypi.com/pico/getting-started-with-pico.pdf
  - picotool README：https://github.com/raspberrypi/picotool
  - pico-examples `blink/blink.c`：https://github.com/raspberrypi/pico-examples
  - RP2350 datasheet（PDF 過大，無法整份讀取；部分數字由 SDK 標頭交叉驗證）：https://datasheets.raspberrypi.com/rp2350/rp2350-datasheet.pdf
- 最後更新：2026-11

---

## 0. 考試情境與本檔定位

考前 demo 包（`考試相關資訊/`）能看出的事實：

| 觀察 | 出處 | 推論 |
|---|---|---|
| Dockerfile 註解寫 demo image「刻意不含 pico-sdk、cross toolchain、judge」，且不在 `docker/build.sh` 的建置鏈內 | `Dockerfile` | 正式考場的 container 很可能內含 pico-sdk + 交叉編譯器 + judge，並接著開發板 |
| section2-2：`demo_pio.pio`（RP2350 PIO）、bitwise C、連到 RISC-V ISA 手冊與 RP2350 datasheet PIO 章節 | `section2-2/README.md` | 可能考 PIO、位元運算、RISC-V（Hazard3）組語 |
| section2-3：pthread 臨界區、模擬「transfer engine」（count 是筆數不是 bytes、1/2/4 bytes、位址對齊、遞增旗標、channel 要 claim/release） | `section2-3/*` | 對應 RP2350 的 DMA 與多核心 / spinlock 概念 |
| section2-1：ROS 2 CLI | `section2-1/README.md` | 與本檔無關 |
| 官方目標：「透過文件閱讀掌握特定系統軟硬體架構」「優化特定程式與整體系統效能」 | 簡章 | 重點是讀文件 + 量測 + 優化，本檔的量測方法論與優化清單是重點 |

以上是從 demo 包推論，不是考題內容。實際考題、judge 的評分方式（看輸出？看時間？）都未知，考場以題目說明為準。

---

## 1. RP2350 晶片總覽

| 項目 | RP2350 | 備註 / 與 RP2040 差異 |
|---|---|---|
| CPU | 雙核 Arm Cortex-M33，或雙核 Hazard3 RISC-V（開機時選擇） | RP2040：雙核 Cortex-M0+。RP2350 晶片上四顆核心都有，但同時只用一種架構 |
| 預設 clk_sys | 150 MHz（SDK `SYS_CLK_HZ` 預設 150000000） | RP2040：SDK 預設 125 MHz |
| 晶振 XOSC | 12 MHz（SDK `XOSC_HZ` 預設） | 同 RP2040 |
| SRAM | 520 KB，10 個 bank | RP2040：264 KB |
| Boot ROM | 32 KB，位於 0x00000000 | RP2040：16 KB |
| 外部 flash | QSPI，經 QMI 做 XIP；每個 chip select 16 MB，兩個 CS 合計最多 32 MB；第二個 CS 可接 PSRAM 或第二顆 flash | RP2040 無 PSRAM 支援 |
| XIP cache | 16 KB（SDK 把 cache-as-RAM 區定義為 0x13FFC000 起 16 KB） | RP2040：16 KB |
| 內建 flash | RP2350A/B 無；RP2354A/B 內含 2 MB 堆疊 flash | — |
| GPIO | RP2350A（QFN-60）30 支；RP2350B（QFN-80）48 支 | Pico 2 用 RP2350A |
| ADC | A：4 路類比輸入；B：8 路（另有溫度感測通道，SDK `NUM_ADC_CHANNELS` 為 5 / 9） | — |
| PIO | 3 個 PIO block × 4 state machine = 12 SM | RP2040：2 × 4 = 8 |
| DMA | 16 channel，4 條 DMA IRQ | RP2040：12 channel，2 條 IRQ |
| PWM | 12 slice（24 channel；A 封裝腳位只引出 16 channel） | RP2040：8 slice |
| UART / SPI / I2C | 各 2 | 同 |
| Timer | TIMER0、TIMER1 兩個 64-bit µs timer，各 4 個 alarm | RP2040：一個 timer |
| 其他 | USB 1.1 host/device、HSTX（高速輸出）、TRNG、SHA-256 加速、8 KB OTP、TrustZone、secure boot、POWMAN、glitch detector | 皆為 RP2350 新增（USB 除外） |
| 硬體除法器 | **沒有**（SIO divider 已移除；`hardware_divider` 在 RP2350 為軟體實作） | RP2040 有 SIO 8-cycle 除法器 |
| 浮點 | M33：單精度 FPU + RP2350 自家 DCP（double coprocessor）加速 double；Hazard3：**無 FPU** | RP2040：無 FPU，靠 ROM 軟體浮點 |
| IRQ 數 | 52（`NUM_IRQS`） | RP2040：32 |

### 1.1 兩種 CPU 架構比較

| | Cortex-M33（`rp2350-arm-s`） | Hazard3（`rp2350-riscv`） |
|---|---|---|
| ISA | Armv8-M Mainline（Thumb-2），含 DSP、FPU（單精度）、TrustZone | RV32IMAC + Zicsr、Zifencei、Zba、Zbb、Zbs、Zbkb、Zcb、Zcmp（SDK 的 `-march` 字串） |
| 編譯器 | `arm-none-eabi-gcc`（`-mcpu=cortex-m33 -mthumb -march=armv8-m.main+fp+dsp -mcmse`，預設 `-mfloat-abi=softfp`；`PICO_NO_CMSE=1` 可拿掉 `-mcmse`） | `riscv32-*-elf-gcc`（SDK 依序找 `riscv32-pico-elf`、`riscv32-unknown-elf`、`riscv32-corev-elf`、`riscv-none-elf`），`-mabi=ilp32` |
| float | 硬體 FPU（快） | 軟體模擬（慢很多），SDK 有提供優化過的 add/sub/mul |
| double | DCP coprocessor 加速（`pico_double` 預設） | 軟體（compiler 內建函式庫） |
| 整數除法 | 硬體 SDIV/UDIV 指令 | M 擴充 div/rem 指令 |
| cycle counter | DWT `CYCCNT`（見第 10 節） | `mcycle` CSR（細節見 `riscv-hazard3.md`） |
| SDK 名稱 `-s` | 「secure」：SDK 預設以 Secure 模式執行 | — |

選擇架構：用哪個 platform 編譯，產出的 UF2 / 映像就是給那個架構，bootrom 依映像自動選核心。也可以用 `picotool reboot -c arm|riscv` 指定。

---

## 2. 記憶體映射（Memory Map）

以下數值取自 SDK `addressmap.h`（RP2350）。

| 區域 | 起始位址 | 說明 |
|---|---|---|
| ROM | `0x00000000` | 32 KB boot ROM |
| XIP（cached） | `0x10000000` | 外部 flash，經 cache 讀取；程式預設在這裡執行 |
| XIP_SRAM（cache as RAM） | `0x13FFC000` – `0x13FFFFFF` | 停用 cache 時可當 16 KB RAM 用（`pico_use_xip_cache_as_ram`、`xip_ram` binary type） |
| XIP_NOCACHE_NOALLOC | `0x14000000` | 不經 cache 的 flash 視窗 |
| XIP_MAINTENANCE | `0x18000000` | cache 維護操作 |
| XIP_NOCACHE_NOALLOC_NOTRANSLATE | `0x1C000000` | — |
| SRAM（striped） | `0x20000000` – `0x2007FFFF` | SRAM0–SRAM7，8 × 64 KB = 512 KB，交錯映射 |
| SRAM4_BASE | `0x20040000` | SRAM4 起點，也是後 256 KB 交錯區（SRAM4–7）的起點；RP2350 沒有非交錯鏡像 |
| SCRATCH_X（SRAM8） | `0x20080000` | 4 KB |
| SCRATCH_Y（SRAM9） | `0x20081000` | 4 KB；`SRAM_END = 0x20082000` |
| APB 週邊 | `0x40000000` 起 | SYSINFO `0x40000000`、CLOCKS `0x40010000`、RESETS `0x40020000`、IO_BANK0 `0x40028000`、PADS_BANK0 `0x40038000`、XOSC `0x40048000`、PLL_SYS `0x40050000`、UART0 `0x40070000`、UART1 `0x40078000`、SPI0 `0x40080000`、SPI1 `0x40088000`、I2C0 `0x40090000`、I2C1 `0x40098000`、ADC `0x400A0000`、PWM `0x400A8000`、TIMER0 `0x400B0000`、TIMER1 `0x400B8000`、HSTX_CTRL `0x400C0000`、XIP_CTRL `0x400C8000`、XIP_QMI `0x400D0000`、WATCHDOG `0x400D8000`、BOOTRAM `0x400E0000`、TRNG `0x400F0000`、SHA256 `0x400F8000`、POWMAN `0x40100000`、TICKS `0x40108000`、OTP `0x40120000` |
| AHB 週邊 | `0x50000000` 起 | DMA `0x50000000`、USBCTRL `0x50100000`、PIO0 `0x50200000`、PIO1 `0x50300000`、PIO2 `0x50400000`、HSTX_FIFO `0x50600000`、XIP_AUX `0x50500000` |
| SIO | `0xD0000000` | 核心本地的單週期 IO（Non-secure 別名 `0xD0020000`） |
| PPB | `0xE0000000` | Cortex-M33 私有週邊（NVIC、SysTick、DWT…），Non-secure 別名 `0xE0020000` |

### 2.1 SRAM bank 與 linker 預設擺放

| SDK linker 區塊 | 位址 / 大小 | 預設放什麼 |
|---|---|---|
| `RAM` | `0x20000000`，512 KB | `.data`、`.bss`、heap、`__not_in_flash` / `__time_critical` 函式（`.time_critical.*`） |
| `SCRATCH_X` | `0x20080000`，4 KB | `__scratch_x("...")` 資料、**core 1 的 stack**（若有啟動 core 1） |
| `SCRATCH_Y` | `0x20081000`，4 KB | `__scratch_y("...")` 資料、**core 0 的 stack** |

- SDK 註解說明：scratch bank 適合放「只有一顆核心存取」的關鍵資料／函式，因為單一核心存取同一 bank 就不會跟別人搶 bus 而 stall。
- 512 KB 主 SRAM 分兩組交錯（striped）映射：SRAM0–3 在 `0x20000000` 起的 256 KB、SRAM4–7 在 `0x20040000` 起的 256 KB，每組內以位址 bit 3:2 按 word 輪流分到 4 個 bank，平均分擔負載。RP2350 沒有 RP2040 那種非交錯的鏡像位址。（依 RP2350 datasheet SRAM 章節，詳見 `multicore-sync.md`）
- 預設 stack 大小：`PICO_STACK_SIZE = 0x800`（**每核心 2 KB**）；預設最小 heap `PICO_HEAP_SIZE = 0x800`。heap 實際延伸到 RAM 尾端。大型陣列不要放在區域變數（stack 爆掉 → 亂跑 / HardFault），改用 `static` 或全域。

### 2.2 原子暫存器別名（atomic register aliases）

對週邊暫存器位址加上偏移，可以單一次寫入完成 XOR / SET / CLR，不必讀-改-寫，兩顆核心同時操作也安全。

| 偏移 | 意義 | SDK 函式 |
|---|---|---|
| `+0x0000` | 一般讀寫 | 直接寫 `reg = v` |
| `+0x1000` | XOR（寫 1 的位元翻轉） | `hw_xor_bits(&reg, mask)` |
| `+0x2000` | SET（寫 1 的位元設 1） | `hw_set_bits(&reg, mask)` |
| `+0x3000` | CLR（寫 1 的位元清 0） | `hw_clear_bits(&reg, mask)` |

```c
#include "hardware/address_mapped.h"
#include "hardware/structs/dma.h"
hw_set_bits(&dma_hw->inte0, 1u << 3);   // 只開 channel 3 的 IRQ0 致能，不動其他位元
hw_set_alias(dma_hw)->inte1 = 0x80;     // 整個 struct 的 SET 別名寫法（SDK 文件範例）
```

SIO 的 GPIO 輸出請用 SIO 自己提供的 `gpio_set` / `gpio_clr` / `gpio_togl` 暫存器，不要對 SIO 套用上面的別名：RP2350 的 SIO 不支援 +0x1000/+0x2000/+0x3000 原子別名（依 RP2350 datasheet，詳見 `riscv-hazard3.md`；RP2040 同樣不支援）。

---

## 3. SIO（Single-cycle IO）內容

依 SDK `sio_hw_t`（RP2350）欄位整理：

| 功能 | 欄位 / 說明 | RP2350 有？ |
|---|---|---|
| CPUID | `sio_hw->cpuid`：0 = core 0，1 = core 1（`get_core_num()`） | 有 |
| GPIO 快速存取 | `gpio_in`、`gpio_out`、`gpio_set`、`gpio_clr`、`gpio_togl`、`gpio_oe(_set/_clr/_togl)`；GPIO32–47 用 `gpio_hi_*` | 有（含 hi bank，供 RP2350B） |
| 核心間 FIFO（mailbox） | `fifo_st`、`fifo_wr`、`fifo_rd` | 有 |
| Spinlock | `spinlock[32]`、`spinlock_st` | 有，32 個 |
| Interpolator | `interp[2]`（每顆核心各 2 個） | 有 |
| Doorbell | `doorbell_out_set/clr`、`doorbell_in_set/clr`（8 個，`NUM_DOORBELLS`） | 有（RP2350 新增） |
| RISC-V 機器模式 timer | `mtime`、`mtimeh`、`mtimecmp(h)`、`mtime_ctrl`、`riscv_softirq` | 有（RP2350 新增） |
| TMDS encoder | `tmds_ctrl`、`tmds_wdata`、`tmds_peek/pop_*`（DVI 影像編碼用） | 有（RP2350 新增） |
| 整數除法器 | RP2040 的 `div_*` 暫存器 | **沒有** |

另外 Cortex-M33 上 SDK 預設用「GPIO coprocessor」（`PICO_USE_GPIO_COPROCESSOR=1`）執行 `gpio_put` 等函式，存取 GPIO 更快；RISC-V 走 SIO 暫存器。

---

## 4. Pico 2 板子（RP2350A）

| 項目 | 值（來源 `boards/pico2.h` 與官方板子頁） |
|---|---|
| 板載 LED | **GPIO 25**（`PICO_DEFAULT_LED_PIN 25`）。Pico 2 **W** 的 LED 接在無線晶片 `WL_GPIO0`，要用 `cyw43_arch` |
| Flash | 4 MB（`PICO_FLASH_SIZE_BYTES`） |
| 預設 UART | uart0，TX = GPIO0，RX = GPIO1 |
| 預設 I2C | i2c0，SDA = GPIO4，SCL = GPIO5 |
| 預設 SPI | spi0，RX = GPIO16，CSn = GPIO17，SCK = GPIO18，TX = GPIO19 |
| 內部用腳 | GPIO23 = SMPS 模式，GPIO24 = VBUS 偵測，GPIO29 = VSYS/3 量測（ADC3） |
| 引出 GPIO | 26 支多功能 GPIO；3 路 ADC 可用 |
| 按鈕 | BOOTSEL（按住再插 USB → 進入 USB 大量儲存模式） |
| 除錯 | 3-pin SWD |

⚠️ RP2350 A2 stepping 有已知 erratum（RP2350-E9）：GPIO 當輸入且使用內部 pull-down 時可能異常。需要讀按鍵時，優先用內部 pull-up + 接地按鈕，或外部電阻；細節見 datasheet errata。

---

## 5. pico-sdk 專案結構與 CMake

### 5.1 最小專案

```
my_app/
├── CMakeLists.txt
├── pico_sdk_import.cmake    ← 從 $PICO_SDK_PATH/external/ 複製過來
├── main.c
└── foo.pio                  ← 可選
```

```cmake
cmake_minimum_required(VERSION 3.13)

# 板子 / 平台：要在 include(pico_sdk_import.cmake) 之前設定（或在命令列 -D 傳入）
set(PICO_BOARD pico2 CACHE STRING "Board type")
# 要編 RISC-V 時：set(PICO_PLATFORM rp2350-riscv CACHE STRING "Platform")

include(pico_sdk_import.cmake)        # 必須在 project() 之前

project(my_app C CXX ASM)
set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)

pico_sdk_init()                       # 必須在 project() 之後、add_executable 之前

add_executable(my_app main.c)

# 用到哪個 hardware_* 就要 link 哪個，否則找不到標頭或 undefined reference
target_link_libraries(my_app
    pico_stdlib
    hardware_dma
    hardware_pio
    hardware_clocks
)

# PIO 程式 → 產生 foo.pio.h
pico_generate_pio_header(my_app ${CMAKE_CURRENT_LIST_DIR}/foo.pio)

pico_enable_stdio_usb(my_app 1)       # printf 走 USB CDC
pico_enable_stdio_uart(my_app 0)      # printf 走 UART0（GPIO0/1）

# 可選：pico_set_binary_type(my_app copy_to_ram)

pico_add_extra_outputs(my_app)        # 產生 .uf2 / .bin / .hex / .dis 等
```

### 5.2 重要 CMake 變數

| 變數 | 可選值 | 說明 |
|---|---|---|
| `PICO_SDK_PATH` | SDK 路徑 | 環境變數或 `-DPICO_SDK_PATH=...`；也可 `PICO_SDK_FETCH_FROM_GIT=on` 自動抓 |
| `PICO_BOARD` | `pico`、`pico_w`、`pico2`、`pico2_w`… | 決定腳位預設、flash 大小；`pico2.h` 會把 platform 設為 `rp2350` |
| `PICO_PLATFORM` | `rp2040`、`rp2350`、`rp2350-arm-s`、`rp2350-riscv`、`host` | `rp2350` 會展開為 `PICO_DEFAULT_RP2350_PLATFORM`，預設 `rp2350-arm-s` |
| `PICO_TOOLCHAIN_PATH` | 編譯器目錄 | RISC-V 工具鏈常需要設定 |
| `CMAKE_BUILD_TYPE` | `Release`（SDK 預設）、`Debug`、`RelWithDebInfo`、`MinSizeRel` | 見 6.2 |
| `PICO_DEFAULT_BINARY_TYPE` | `default`、`copy_to_ram`、`no_flash`… | 全專案預設；單一 target 用 `pico_set_binary_type` |

- 沒有 `pico2_riscv` 這個 board。RISC-V 的組合是 `-DPICO_BOARD=pico2 -DPICO_PLATFORM=rp2350-riscv`。
- **陷阱**：`PICO_BOARD` 和 `PICO_PLATFORM` 都沒設時，SDK 預設 platform `rp2040`、board `pico`，編出來的東西 Pico 2 不能跑。看 cmake 輸出的 `Target board (PICO_BOARD) is 'pico2'` 或 `Defaulting ...` 訊息確認。
- 換 board/platform 後要**清掉 build 目錄**（`rm -rf build`），CMake cache 會記住舊值。

### 5.3 常用函式庫（`target_link_libraries`）

| 函式庫 | 標頭 | 用途 |
|---|---|---|
| `pico_stdlib` | `pico/stdlib.h` | 打包 `hardware_gpio`、`hardware_uart`、`hardware_divider`、`pico_time`、`pico_util`、`pico_platform`、`pico_runtime`、`pico_stdio` |
| `hardware_dma` | `hardware/dma.h` | DMA（→ `pico-dma.md`） |
| `hardware_pio` | `hardware/pio.h` | PIO（→ `pio.md`） |
| `hardware_irq` | `hardware/irq.h` | 中斷 |
| `hardware_clocks` | `hardware/clocks.h` | `clock_get_hz`、`set_sys_clock_khz` |
| `hardware_vreg` | `hardware/vreg.h` | 核心電壓 |
| `hardware_timer` | `hardware/timer.h` | 低階 timer / alarm |
| `hardware_interp` | `hardware/interp.h` | interpolator |
| `hardware_sync` | `hardware/sync.h` | spinlock、關中斷、記憶體屏障 |
| `hardware_pwm`、`hardware_adc`、`hardware_spi`、`hardware_i2c` | 同名 | 週邊 |
| `pico_multicore` | `pico/multicore.h` | 啟動 core 1、FIFO（→ `multicore-sync.md`） |
| `pico_sync` | `pico/sync.h` | mutex、semaphore、critical_section |

`pico_stdlib` **不含** `hardware_dma`、`hardware_pio`、`pico_multicore`，這三個最常忘記加。

---

## 6. 建置、輸出檔、燒錄

### 6.1 建置指令

```bash
export PICO_SDK_PATH=/path/to/pico-sdk          # 若考場環境已設定可略
mkdir -p build && cd build
cmake .. -DPICO_BOARD=pico2                     # Arm（預設 rp2350-arm-s）
# cmake .. -DPICO_BOARD=pico2 -DPICO_PLATFORM=rp2350-riscv   # RISC-V
# cmake .. -G Ninja -DPICO_BOARD=pico2 && ninja              # 用 Ninja
make -j$(nproc)
# 或：cmake -S . -B build -DPICO_BOARD=pico2 && cmake --build build -j
```

### 6.2 輸出檔

| 副檔名 | 內容 | 用途 |
|---|---|---|
| `.elf` | 完整程式（含除錯資訊） | SWD/gdb 燒錄除錯、`objdump`、`size`、`nm` |
| `.uf2` | UF2 格式 | 拖進 BOOTSEL 磁碟機 |
| `.bin` | 原始二進位 | — |
| `.hex` | Intel HEX | — |
| `.dis` | 反組譯 | **看編譯器產生了什麼指令**、函式在 flash 還是 RAM |
| `.elf.map` | linker map（檔名 `<target>.elf.map`） | **看每個 section / 函式 / 變數的位址與大小** |

### 6.3 Build type 的效果

| CMAKE_BUILD_TYPE | 旗標（GCC） | 何時用 |
|---|---|---|
| `Release`（**SDK 預設**） | CMake 預設 `-O3 -DNDEBUG`，SDK 另加 `-g`（`PICO_DEBUG_INFO_IN_RELEASE=1`） | 量效能、交卷 |
| `Debug` | `-Og`（`PICO_DEOPTIMIZED_DEBUG=1` 時改 `-O0`）+ `-g` | gdb 單步 |
| `MinSizeRel` | `-Os` | 省 flash |
| `RelWithDebInfo` | `-O2 -g` | 介於中間 |

`-DNDEBUG` 會讓 `assert()` 失效。**量效能一定用 Release**，並與 judge 使用相同的 build 設定（若題目有給 CMakeLists / 指令，照抄，不要私自改旗標）。

### 6.4 Binary type（程式放哪裡執行）

| `pico_set_binary_type(target X)` | 行為 | 優缺點 |
|---|---|---|
| `default` | 程式在 flash，經 XIP cache 執行 | 程式大小只受 flash 限制；cache miss 時慢 |
| `copy_to_ram` | 存在 flash，開機時整份複製到 SRAM 再執行 | 執行快且穩定；佔 SRAM；重開機仍在 |
| `no_flash` | 只載入 SRAM（UF2 或 SWD），不寫 flash | 斷電就沒了；適合快速測試 |
| `xip_ram`（RP2350 linker script 有） | 用 XIP cache 當 RAM | 進階用途 |
| `blocked_ram` | RP2040 專用 | RP2350 不適用 |

也可以全域：`-DPICO_COPY_TO_RAM=1` / `-DPICO_NO_FLASH=1`（舊式）或 `-DPICO_DEFAULT_BINARY_TYPE=copy_to_ram`，兩種寫法不能同時用。

### 6.5 燒錄

| 方法 | 步驟 |
|---|---|
| BOOTSEL 拖放 | 按住 BOOTSEL 插 USB → 出現 USB 大量儲存磁碟機（RP2350 通常顯示為 `RP2350`，RP2040 為 `RPI-RP2` ⚠️名稱未在官方文件原文確認）→ 複製 `.uf2` 進去 → 自動重開執行 |
| picotool | `picotool load -x my_app.uf2`（`-x` 燒完執行；`-v` 驗證；`-f` 讓「正在執行相容程式」的板子先自動重開進 BOOTSEL） |
| picotool 其他 | `picotool info -a`（讀板上程式資訊）、`picotool reboot`（回應用程式）、`picotool reboot -u`（進 BOOTSEL）、`picotool reboot -c riscv`（RP2350 選架構） |
| SWD（Debug Probe） | `openocd -f interface/cmsis-dap.cfg -f target/rp2350.cfg -c "adapter speed 5000" -c "program my_app.elf verify reset exit"` |
| gdb | `openocd ... -f target/rp2350.cfg` 開 server，另一終端 `gdb my_app.elf` → `target remote localhost:3333` → `monitor reset init` |

`picotool -f` 的前提：板上程式仍在跑且有用 USB stdio（`pico_enable_stdio_usb`，內含 reset 介面）。另一招是定義 `PICO_ENTER_USB_BOOT_ON_EXIT`：`main` return 後自動進 BOOTSEL（之後不需 `-f`）。程式卡死時 `-f` 無效，只能手動按 BOOTSEL。考場若由 judge 自動燒錄，以題目說明為準。

---

## 7. 核心 API

### 7.1 stdio

```c
#include <stdio.h>                       // printf/putchar 要自己 include（pico/stdlib.h 不含）
#include "pico/stdlib.h"
int main(void) {
    stdio_init_all();                    // 初始化所有已啟用的 stdio（USB/UART）；回傳 bool
    // USB CDC 需要主機端打開序列埠；剛開機的輸出可能遺失
    while (!stdio_usb_connected()) sleep_ms(10);   // 需要時才等（要 link USB stdio）
    printf("hello %d\n", 42);
    int c = getchar_timeout_us(100000);  // 100 ms 內沒輸入 → 回傳 PICO_ERROR_TIMEOUT（值為 -2，用名稱比較）
    if (c != PICO_ERROR_TIMEOUT) putchar(c);
    stdio_flush();
}
```

- `PICO_STDIO_USB_CONNECT_WAIT_TIMEOUT_MS`（預設 0）可讓 `stdio_init_all()` 等 USB 連線。
- `printf` 本身慢（格式化），USB stdio 還有 USB 中斷與 buffer；**不要放在被計時的區段內**。
- 需要特定輸出格式給 judge 時，確認換行（`\n` 與 CRLF 轉換：`PICO_STDIO_DEFAULT_CRLF`）。

### 7.2 GPIO

```c
#include "pico/stdlib.h"
#define LED 25                       // Pico 2；或用 PICO_DEFAULT_LED_PIN
gpio_init(LED);                      // 設為 SIO 功能、輸入、輸出值 0
gpio_set_dir(LED, GPIO_OUT);         // true/GPIO_OUT = 輸出
gpio_put(LED, 1);
bool v = gpio_get(LED);

gpio_init(15);
gpio_set_dir(15, GPIO_IN);
gpio_pull_up(15);                    // 見 4 節 E9 erratum：輸入優先用 pull-up

gpio_set_function(0, GPIO_FUNC_UART);   // 把腳交給週邊（UART/SPI/PIO…）
gpio_set_function(2, GPIO_FUNC_PIO0);   // RP2350 另有 GPIO_FUNC_PIO2

// 多腳一次操作
gpio_set_mask(0x0F << 2);  gpio_clr_mask(0x0F << 2);  gpio_xor_mask(1u << 25);
gpio_put_masked(0xFF << 8, value << 8);
uint32_t all = gpio_get_all();

// 直接寫 SIO（最快的通用寫法之一；Arm 上 gpio_put 已用 GPIO coprocessor，一樣快）
#include "hardware/structs/sio.h"
sio_hw->gpio_set  = 1u << LED;
sio_hw->gpio_clr  = 1u << LED;
sio_hw->gpio_togl = 1u << LED;

// GPIO 中斷
void on_edge(uint gpio, uint32_t events) { /* 保持短 */ }
gpio_set_irq_enabled_with_callback(15, GPIO_IRQ_EDGE_FALL, true, &on_edge);
```

RP2350 的 pad 在重置後是「隔離（ISO）」狀態，`gpio_set_function()` / `gpio_init()` 會解除隔離。**直接寫 IO_BANK0 暫存器而不呼叫 SDK 函式時，腳可能沒有反應**（RP2040 沒有這個問題）。

### 7.3 時間

| API | 說明 |
|---|---|
| `uint32_t time_us_32(void)` | 開機後 µs，32 位元，約 71.6 分鐘溢位 |
| `uint64_t time_us_64(void)` | 開機後 µs，64 位元 |
| `absolute_time_t get_absolute_time(void)` | 不透明時間型別 |
| `int64_t absolute_time_diff_us(from, to)` | `to - from`（µs） |
| `absolute_time_t make_timeout_time_ms(ms)`、`time_reached(t)` | 逾時判斷 |
| `sleep_ms(uint32_t)`、`sleep_us(uint64_t)` | 讓出 CPU 的等待（可能進低功耗等待）；**不可在 ISR 內呼叫** |
| `busy_wait_us(uint64_t)`、`busy_wait_us_32`、`busy_wait_ms`、`busy_wait_until` | 忙等 |
| `add_alarm_in_ms(ms, cb, user_data, fire_if_past)` | 單次 alarm；`int64_t cb(alarm_id_t id, void *ud)`：回 0 不重複，>0 從現在起再等該 µs，<0 從上次預定時間起算 |
| `add_repeating_timer_ms(delay_ms, cb, ud, &timer)` | 週期；`bool cb(repeating_timer_t *rt)` 回 true 繼續。`delay_ms > 0`：上一次 callback 結束到下一次開始的間隔；`< 0`：callback 開始到開始的固定週期（要固定頻率用負數） |

`repeating_timer_t` 結構要活得比 timer 久（用 `static` 或全域，不要放 stack）。alarm/timer callback 在 IRQ context（預設 core 0）執行。

### 7.4 時脈與電壓

```c
#include "hardware/clocks.h"
#include "hardware/vreg.h"
uint32_t f = clock_get_hz(clk_sys);          // 預設 150000000

// 改頻率：建議在 stdio_init_all() 之前做
bool ok = set_sys_clock_khz(200000, false);  // required=true 時若無法精確達成會 panic
// 也有 set_sys_clock_hz(uint32_t hz, bool required)、set_sys_clock_pll(vco, pd1, pd2)
```

- `set_sys_clock_khz` 只接受 PLL 能「精確」產生的頻率（`check_sys_clock_khz` 檢查）；回傳 false 表示沒變。
- 呼叫後 SDK 預設把 `clk_peri` 改接 48 MHz 的 PLL_USB（除非定義 `PICO_CLOCK_ADJUST_PERI_CLOCK_WITH_SYS_CLOCK`）。若 UART 在之前已用舊的 `clk_peri` 初始化，鮑率會錯 → 先改時脈、再 `stdio_init_all()`。
- 電壓：`vreg_set_voltage(VREG_VOLTAGE_1_20)` 等；預設 `VREG_VOLTAGE_1_10`，未解鎖時上限 1.30 V（`vreg_disable_voltage_limit()` 才能更高，有損壞風險）。
- 超頻超出額定 150 MHz 不保證穩定。考試若比效能，**除非題目允許，不要靠超頻**；judge 可能以固定時脈評分或檢查設定 ⚠️（考試規則未知）。

### 7.5 中斷

```c
#include "hardware/irq.h"
void __isr my_handler(void) {
    // 1) 先清掉週邊的中斷旗標，否則會一直重進
    // 2) 做最少的事：設旗標 / 搬資料到 ring buffer
}
irq_set_exclusive_handler(DMA_IRQ_0, my_handler);   // 一個 IRQ 只能有一個 exclusive handler
irq_set_priority(DMA_IRQ_0, PICO_HIGHEST_IRQ_PRIORITY); // 數值越小越優先；0x00 最高，0xFF 最低
irq_set_enabled(DMA_IRQ_0, true);
// 共用：irq_add_shared_handler(num, handler, order_priority)
```

- 預設優先權 `PICO_DEFAULT_IRQ_PRIORITY = 0x80`；RP2350（M33 / Hazard3）只有高 4 位元有效（RP2040 只有高 2 位元）。
- IRQ 編號 RP2350 與 RP2040 **不同**，一律用名稱：`TIMER0_IRQ_0`(0)、`DMA_IRQ_0`(10)、`USBCTRL_IRQ`(14)、`PIO0_IRQ_0`(15)、`IO_IRQ_BANK0`(21)、`SIO_IRQ_FIFO`(25)、`SIO_IRQ_BELL`(26)、`UART0_IRQ`(33)。從 RP2040 範例複製時注意 `TIMER_IRQ_0`、`SIO_IRQ_PROC0` 之類舊名稱。
- ISR 裡不要 `printf`、`sleep_ms`、長迴圈；與主程式共享的變數宣告 `volatile`，多位元組更新要關中斷保護（`save_and_disable_interrupts()` / `restore_interrupts(s)`）。
- 時間敏感的 ISR 可加 `__not_in_flash_func` 放 RAM，避免 flash cache miss 延遲。

### 7.6 Interpolator（簡述）

每顆核心 2 個（`interp0`、`interp1`），硬體做「位移 + 遮罩 + 加法」，常用於查表索引計算、紋理座標、固定點運算。基本流程：

```c
#include "hardware/interp.h"     // link hardware_interp
interp_config cfg = interp_default_config();
interp_config_set_shift(&cfg, 2);           // 例：右旋轉 2（RP2350 是 right-rotate 不是右移；mask 要清掉轉上來的高位，詳見 control-dsp.md）
interp_config_set_mask(&cfg, 0, 7);         // 保留 bit 0..7
interp_set_config(interp0, 0, &cfg);        // lane 0
interp0->accum[0] = x;
interp0->base[0]  = (uintptr_t)table;
uint32_t r = interp0->pop[0];               // 讀取結果並更新累加器；peek 不更新
```

精確語意請查 SDK `hardware_interp` 文件與 datasheet SIO 章節；不常用就不必硬學。

### 7.7 除法與浮點

| 運算 | Cortex-M33 | Hazard3 RISC-V | 建議 |
|---|---|---|---|
| 整數除法 | 硬體 `SDIV/UDIV` | M 擴充 `div/divu/rem` | 除以 2 的冪改 `>>`、`& (n-1)`；迴圈內避免除法 |
| `hardware_divider` API | RP2350 為**軟體實作**（無 SIO divider） | 同 | RP2040 的「用 hw divider 加速」技巧在 RP2350 無效 |
| float | 硬體 FPU（`pico_float` 預設 `pico_vfp`） | **軟體模擬**（SDK 有優化版 add/sub/mul） | RISC-V 上改用**固定點**（如 Q16.16） |
| double | DCP 協處理器加速（`pico_double` 預設） | 軟體（compiler 函式庫） | 能用 float 就別用 double；常數寫 `1.0f` |

常見浮點陷阱：`x * 0.5`（`0.5` 是 double → 整條運算變 double）；`printf("%f", f)` 會把 float 提升成 double；`sinf`/`sqrtf` 比 `sin`/`sqrt` 快。加 `-Wdouble-promotion` 可抓出隱性 double。

固定點範例：

```c
typedef int32_t q16_t;                         // Q16.16
#define Q16(x)     ((q16_t)((x) * 65536.0f))   // 只用在編譯期常數
static inline q16_t q16_mul(q16_t a, q16_t b) { return (q16_t)(((int64_t)a * b) >> 16); }
```

---

## 8. 記憶體擺放與速度

### 8.1 速度階層（定性）

| 位置 | 特性 |
|---|---|
| SIO / 核心暫存器 | 單週期 |
| SRAM（striped 512 KB） | 很快；兩核心 + DMA 同時打同一 bank 才會互搶 |
| SCRATCH_X / SCRATCH_Y | 單一核心專用時無競爭 |
| XIP flash（cache hit） | 接近 SRAM |
| XIP flash（cache miss） | 要經 QSPI 從 flash 讀，**慢很多**，且延遲不固定 |

程式預設在 flash 執行。熱迴圈第一次執行會 cache miss；程式碼／唯讀資料總量超過 16 KB cache 或互相衝突時會一直 miss。

### 8.2 SDK 擺放巨集

| 巨集 | 用途 | 範例 |
|---|---|---|
| `__not_in_flash_func(f)` | 函式放 RAM（`.time_critical.f`） | `void __not_in_flash_func(hot)(int n) { ... }` |
| `__time_critical_func(f)` | 語意為「時間關鍵」，預設等同上者 | `void __time_critical_func(isr)(void) { ... }` |
| `__no_inline_not_in_flash_func(f)` | 放 RAM 且不 inline（避免被 inline 回 flash 函式中） | — |
| `__not_in_flash("grp")` | 資料放 RAM（即使是 const） | `static const uint32_t __not_in_flash("tbl") lut[256] = {...};` |
| `__in_flash("grp")` | 資料明確放 flash | — |
| `__scratch_x("grp")` / `__scratch_y("grp")` | 放 4 KB scratch bank | `uint32_t __scratch_x("buf") buf[256];` |
| `__uninitialized_ram(var)` | 不在開機時清零 | `uint32_t __uninitialized_ram(keep);` |
| `pico_set_binary_type(t copy_to_ram)` | 整支程式放 RAM 執行 | 見 6.4 |

- `__scratch_x/__scratch_y` 在目前 SDK 需要一個字串參數（group 名稱）；舊版或網路範例寫法可能不同，編譯錯誤時查 `pico/platform/sections.h`。
- `__not_in_flash_func` **不阻止 inline**：若被 inline 進 flash 中的呼叫者，就跟著在 flash 跑。
- 注意 scratch Y 尾端放 core 0 stack、scratch X 放 core 1 stack；在 scratch 放太多資料會跟 stack 搶空間。
- `const` 全域陣列預設在 flash（`.rodata`）。被熱迴圈頻繁隨機讀取的查表 → 考慮 `__not_in_flash` 搬進 RAM。
- 對齊：DMA、32-bit 存取需要位址對齊（`__attribute__((aligned(4)))`；DMA ring 模式需對齊到 ring 大小，見 `pico-dma.md`）。

### 8.3 檢查東西實際放在哪

```bash
# 函式位址：0x10xxxxxx = flash；0x20xxxxxx = SRAM
grep -n "hot_loop" build/my_app.elf.map                         # SDK 產生的 map 檔名是 <target>.elf.map
arm-none-eabi-nm -n build/my_app.elf | grep -i hot_loop
arm-none-eabi-nm --size-sort -S build/my_app.elf | tail -20     # 最大的符號
arm-none-eabi-size build/my_app.elf                             # text/data/bss
arm-none-eabi-objdump -d build/my_app.elf | less                # 或直接看 .dis
# RISC-V 把前綴換成 riscv32-unknown-elf-（或環境中實際的 triple）
```

---

## 9. 編譯器與「程式被優化掉」

| 現象 | 原因 | 對策 |
|---|---|---|
| 計時結果 0 µs 或極小 | 結果沒被使用 → 整段被刪 | 把結果寫入 `volatile` 全域變數或最後印出 |
| 迴圈等待旗標永遠不結束 | ISR / 另一核心 / DMA 改的變數沒宣告 `volatile`，被快取在暫存器 | 加 `volatile`，或用 SDK barrier（`__compiler_memory_barrier()`、`__dmb()`） |
| `-O0`/Debug 很慢 | 未優化 | 量效能用 Release |
| 想看某函式的指令 | — | 看 `.dis`，或 `objdump -d --disassemble=func` |

```c
static volatile uint32_t sink;      // 防止被 dead-code elimination
sink = compute(buf, N);
```

不要把**被量測的資料陣列本身**宣告成 `volatile`：會強迫每次存取都讀寫記憶體，量到的反而不是真實效能。只在「結果」與「跨執行緒旗標」用 `volatile`。

可選的局部優化旗標（確認 judge 是否採用你的 CMakeLists 後再用）：

```cmake
target_compile_options(my_app PRIVATE -O3 -Wall -Wextra -Wdouble-promotion)
# 單一函式：__attribute__((optimize("O3")))  /  #pragma GCC unroll 4
```

---

## 10. 在板子上量測效能的方法

### 10.1 原則

1. **固定條件**：相同 build type、相同 clk_sys（先印 `clock_get_hz(clk_sys)` 確認）、相同輸入資料。
2. **暖機**：先跑一次不計（填 XIP cache、初始化）。
3. **重複 N 次**，取 **最小值** 或 **中位數**（平均數易被中斷干擾拉高）。
4. **計時區段內不做 I/O**：不 `printf`、不 `sleep`；量完再一次印出。
5. **避免干擾**：USB stdio 有週期性中斷；要精確量測可暫時 `save_and_disable_interrupts()`（量完記得 restore；關太久 USB 可能斷線），或改用 UART stdio。
6. **解析度**：`time_us_*` 為 1 µs（150 MHz 下 = 150 cycles）。短函式用 cycle counter，或把它跑 1000 次再除。
7. **驗證正確性**：優化後的輸出要與原版一致（比對 checksum）。

### 10.2 µs 計時框架（兩種架構皆可用）

```c
#include <stdio.h>
#include "pico/stdlib.h"
#include "hardware/clocks.h"

#define RUNS 15
static volatile uint32_t sink;

static void sort_u32(uint32_t *a, int n) {          // 插入排序，n 很小
    for (int i = 1; i < n; i++) {
        uint32_t k = a[i]; int j = i - 1;
        while (j >= 0 && a[j] > k) { a[j + 1] = a[j]; j--; }
        a[j + 1] = k;
    }
}

uint32_t work(void);                                  // 被測函式

int main(void) {
    stdio_init_all();
    sleep_ms(2000);                                   // 給 USB 時間連上（或用 stdio_usb_connected）
    printf("clk_sys=%lu Hz\n", (unsigned long)clock_get_hz(clk_sys));

    sink = work();                                    // 暖機
    uint32_t t[RUNS];
    for (int r = 0; r < RUNS; r++) {
        uint64_t t0 = time_us_64();
        sink = work();
        uint64_t t1 = time_us_64();
        t[r] = (uint32_t)(t1 - t0);
    }
    sort_u32(t, RUNS);
    printf("min=%lu us  median=%lu us  max=%lu us\n",
           (unsigned long)t[0], (unsigned long)t[RUNS / 2], (unsigned long)t[RUNS - 1]);
    while (true) tight_loop_contents();
}
```

### 10.3 Cycle counter

Cortex-M33（DWT CYCCNT，暫存器定義在 SDK `hardware/structs/m33.h`）：

```c
#if defined(__arm__)
#include "hardware/structs/m33.h"
static inline void cyc_init(void) {
    m33_hw->demcr     |= M33_DEMCR_TRCENA_BITS;        // 開啟 DWT/ITM 追蹤
    m33_hw->dwt_cyccnt = 0;
    m33_hw->dwt_ctrl  |= M33_DWT_CTRL_CYCCNTENA_BITS;  // 開始計數
}
static inline uint32_t cyc_now(void) { return m33_hw->dwt_cyccnt; }
#endif
// 用法：uint32_t c0 = cyc_now(); f(); uint32_t dc = cyc_now() - c0;   // 無號相減可處理一次溢位
```

- 32 位元在 150 MHz 下約 28.6 秒溢位，量短區段沒問題。
- 若讀數一直是 0：確認上面兩個 enable 位元都有設；也可查 `M33_DWT_CTRL_NOCYCCNT_BITS`（為 1 表示沒有 cycle counter）。在本 SDK 的 Secure 預設模式下應可使用 ⚠️未在實機驗證。
- RISC-V（Hazard3）：讀 `mcycle`/`mcycleh` CSR（`csrr`），寫法與注意事項見 `riscv-hazard3.md`。**計數器預設是停止的**（`mcountinhibit` reset 值 0x5），量測前必須先執行 `csrci mcountinhibit, 5`，否則讀數永遠不變。

### 10.4 GPIO 翻轉 + 示波器 / 邏輯分析儀

```c
sio_hw->gpio_set = 1u << 2;   // 區段開始
hot();
sio_hw->gpio_clr = 1u << 2;   // 區段結束 → 用儀器量高電位寬度
```

幾乎零干擾，也能看中斷、DMA、PIO 的時序關係。考場是否有儀器未知；沒有的話用 10.2/10.3。

### 10.5 估算與對照

- cycles = 秒 × clk_sys。例：150 MHz 下 1 ms = 150,000 cycles。
- 處理 N 筆資料：算每筆幾個 cycle，對照 `.dis` 中迴圈的指令數，判斷是運算瓶頸還是記憶體 / flash 瓶頸。
- 搬資料量大 → 考慮 DMA（CPU 同時做別的事）；固定時序的 I/O → 考慮 PIO；可平行 → 考慮 core 1。

---

## 11. 給 Online Judge 的習慣

| 習慣 | 原因 |
|---|---|
| 嚴格照題目要求的輸出格式（空白、換行、大小寫、小數位數） | judge 多半逐字比對 |
| 除錯訊息用巨集包起來，交卷前關掉 | 多出來的輸出會被判錯，也拖慢時間 |
| 用與 judge 相同的 CMakeLists、board、platform、build type 在本地編過 | 避免「我這邊可以」 |
| 不改題目給的介面（函式名稱、參數、檔名、target 名稱） | judge 可能用自己的 main 連結你的程式 |
| 輸出前 `stdio_flush()`，必要時結束後保持 `while(1)` | 確保輸出完整送出 |
| 不依賴未初始化變數、未定義行為 | `-O3` 下行為可能改變 |
| 先求正確、再求快；每次優化後重新驗證輸出 | 錯誤答案通常 0 分 |

```c
#ifndef DEBUG_PRINT
#define DEBUG_PRINT 0
#endif
#define DBG(...) do { if (DEBUG_PRINT) printf(__VA_ARGS__); } while (0)
```

judge 實際如何評分（輸出比對、執行時間、是否在板子上跑、由誰燒錄）**未知**，考場以題目與 GitLab repo 中的說明為準。

---

## 12. 除錯清單

### 12.1 編譯 / CMake 失敗

| 錯誤訊息（大意） | 可能原因 | 修正 |
|---|---|---|
| `PICO_SDK_PATH` 未設定 / 找不到 `pico_sdk_import.cmake` | 環境變數沒設或檔案沒複製 | `export PICO_SDK_PATH=...`；從 `$PICO_SDK_PATH/external/` 複製 |
| `pico_sdk_init` / `pico_add_extra_outputs` 未知指令 | `include(pico_sdk_import.cmake)` 順序錯 | include 放在 `project()` 之前，`pico_sdk_init()` 放在 `project()` 之後 |
| `fatal error: hardware/dma.h: No such file` | 沒 link `hardware_dma` | `target_link_libraries(... hardware_dma)`；PIO、multicore、clocks 同理 |
| `undefined reference to dma_channel_configure`（等） | 同上，或 link 到錯的 target | 同上 |
| `foo.pio.h` 找不到 | 沒呼叫 `pico_generate_pio_header` | 加上，並確認 .pio 路徑 |
| 找不到 `arm-none-eabi-gcc` / `riscv32-...-gcc` | 工具鏈不在 PATH | 設 `PICO_TOOLCHAIN_PATH` 或 PATH |
| 編出來是 RP2040 程式 / 標頭顯示 rp2040 | 沒設 board/platform | `-DPICO_BOARD=pico2`，並 `rm -rf build` 重來 |
| 改了 board/platform 沒生效 | CMake cache | 刪 build 目錄 |
| `region RAM overflowed` / `SCRATCH_Y overflowed` | 資料太大或 scratch 放太多 | 縮資料、改放主 RAM、放 flash（const） |
| USB stdio 相關警告：TinyUSB submodule 未初始化 | SDK 的 `lib/tinyusb` 沒拉 | `git submodule update --init`（在 SDK 目錄）；或改用 UART stdio |
| RP2040 範例 API 名稱不存在（`TIMER_IRQ_0` 等） | RP2350 名稱不同 | 改用 RP2350 名稱 |

### 12.2 燒進去沒有輸出

1. 確認是 RP2350 的 build（`picotool info -a my_app.uf2` 或看 cmake 訊息）。
2. `pico_enable_stdio_usb(target 1)` 有寫嗎？`stdio_init_all()` 有呼叫嗎？
3. USB CDC：程式一開始就印的字可能在主機打開序列埠前送出而遺失 → 開頭 `sleep_ms(2000)` 或等 `stdio_usb_connected()`。
4. UART：TX/RX 接腳（GPIO0/1）、鮑率（預設 115200）、改 sys clock 後是否重新初始化。
5. 主程式提早 `return` → 程式結束；嵌入式 `main` 最後保持 `while (true)`。
6. Pico 2 **W** 的 LED 不在 GPIO25。

### 12.3 卡住 / 當機

| 症狀 | 檢查 |
|---|---|
| 一進某函式就掛 | stack overflow（預設每核心只有 2 KB！）→ 大陣列改 `static`；或 `PICO_STACK_SIZE` 調大 |
| 卡在等待迴圈 | 旗標沒 `volatile`；ISR 沒觸發（`irq_set_enabled`？週邊 INTE 位元？）；DMA 沒 start |
| 中斷後就不動 | ISR 沒清週邊中斷旗標 → 無限重入 |
| 呼叫 `sleep_ms` 在 ISR / alarm callback 中 | 不允許，改設旗標 |
| 雙核心卡死 | spinlock / mutex 沒釋放、兩核互等（→ `multicore-sync.md`） |
| 寫 flash 時當掉 | 另一核心或 ISR 正從 flash 執行；需用 `flash_safe_execute` 或 `multicore_lockout` ⚠️（詳見 SDK `hardware_flash` / `pico_flash` 文件） |
| `panic` / `hard_assert` | 看 stdio 是否有 panic 訊息；用 Debug build + gdb |
| 板子完全沒反應、`picotool -f` 失敗 | 手動按 BOOTSEL 重插，重新燒錄 |

### 12.4 計時結果怪怪的

| 症狀 | 可能原因 |
|---|---|
| 0 或極小 | 被優化掉（結果寫 `volatile` sink） |
| 第一次特別慢 | XIP cache miss、初始化 → 暖機、取中位數 |
| 結果飄動大 | USB / timer 中斷干擾 → 取最小值、關中斷、改 UART |
| 比預期慢很多 | Debug build；跑在 flash 且 cache 一直 miss；RISC-V 上用了 float/double；隱性 double；clk_sys 不是你以為的值 |
| `time_us_32` 相減變很大 | 溢位（約 71.6 分鐘）或有號/無號混用 → 用 `time_us_64` 或無號相減 |
| 包含了 printf 時間 | 把 printf 移出計時區 |

---

## 13. 優化清單（依投資報酬率大致排序）

1. **先量測找熱點**，別猜（10 節）。
2. **演算法 / 資料結構**：O(n²) → O(n log n)、避免重複計算、查表。
3. **Release build**（`-O3`）；看 `.dis` 確認熱迴圈沒有多餘 load/store、函式呼叫。
4. **熱函式放 RAM**：`__not_in_flash_func` / `__time_critical_func`，或整支 `copy_to_ram`。查表放 RAM。
5. **型別**：用 `uint32_t`/`int32_t`（32-bit 原生）；避免不必要的 64-bit；RISC-V 避免浮點 → 固定點；Arm 用 `float` 不用 `double`。
6. **除法 / 取餘**：2 的冪改位移與遮罩；常數除法交給編譯器（會轉乘法）；迴圈內不變式外提。
7. **記憶體存取**：循序存取、對齊、一次讀 32-bit 而非 4 次 8-bit；減少指標別名（`restrict`）。
8. **I/O 與計算分離**：資料搬運交給 **DMA**（→ `pico-dma.md`）；精確時序 / 位元流交給 **PIO**（→ `pio.md`）。
9. **平行化**：把可獨立的工作分給 **core 1**，注意共享資料與鎖的範圍要小（→ `multicore-sync.md`）。demo 的 critical-section 範例正示範「鎖抓太久等於退回單執行緒」。
10. **中斷**：ISR 短；高頻事件考慮輪詢或 DMA；設定合理優先權。
11. **SRAM bank 競爭**：兩核心各自的熱資料可放 scratch X / Y；DMA 大量搬運與 CPU 熱資料分開。
12. **組語層級**（最後手段）：手寫 inline asm / 善用 Zbb 等位元指令（→ `riscv-hazard3.md`）。
13. **時脈**：`set_sys_clock_khz` 超頻僅在題目允許時使用 ⚠️。

每做一步：重新驗證輸出正確、重新量測、記錄數字。

---

## 14. 其他 domain 檔案指標

| 檔案 | 內容 | 與本檔的連接點 |
|---|---|---|
| `pico-dma.md` | DMA channel 設定、transfer count（筆數非 bytes）、資料寬度 1/2/4、遞增旗標、DREQ、chaining、ring、IRQ | 本檔 5.3 的 `hardware_dma`、8.2 對齊、13 節第 8 點 |
| `pio.md` | PIO 指令、state machine、FIFO、autopull/autopush、`pico_generate_pio_header` | 本檔 5.1 CMake、7.2 `GPIO_FUNC_PIOx` |
| `riscv-hazard3.md` | RV32 組語、Hazard3 擴充、`mcycle`、呼叫慣例、inline asm | 本檔 1.1、10.3 |
| `multicore-sync.md` | `multicore_launch_core1`、FIFO、spinlock、mutex、critical_section、記憶體屏障 | 本檔 3 節 SIO、12.3、13 節第 9 點 |

---

## 15. 向模型提問的範本

範本 1：建置錯誤
```
我在 RP2350（Pico 2，PICO_PLATFORM={{rp2350-arm-s 或 rp2350-riscv}}）用 pico-sdk 建置。
CMakeLists.txt 如下：
{{貼上 CMakeLists.txt}}
cmake / make 的錯誤輸出如下（完整貼上第一個 error 前後各 20 行）：
{{貼上錯誤}}
請：1) 指出根本原因；2) 給出修正後的完整 CMakeLists.txt 或指令；3) 說明如何確認已修好。
限制：不可更改題目指定的 target 名稱 {{target名稱}}。
```

範本 2：效能優化
```
目標：在 RP2350 {{Cortex-M33 / Hazard3}}、clk_sys={{150 MHz}}、Release build 下，
讓函式 {{函式名稱}} 更快，且輸出必須與原版完全相同。
目前量測：{{min/median}} µs（量法：{{time_us_64 重複 N 次取中位數}}）。
程式碼：
{{貼上函式與相關資料結構}}
資料規模與特性：{{N、資料型別、存取模式}}
請依「預期效益大到小」列出 3 個優化方案，每個附：修改後程式碼、為何在 RP2350 上會變快
（考慮 XIP cache、SRAM、FPU 有無、除法成本）、可能風險。先不要用超頻。
```

範本 3：讀文件理解硬體
```
以下是題目提供的文件片段（{{文件名稱/章節}}）：
{{貼上文件片段}}
請用條列說明：1) 這個模組/暫存器做什麼；2) 每個欄位的意義與單位；
3) 在 pico-sdk 對應的 API 或 struct（例如 xxx_hw->yyy），若 SDK 沒有對應請直說；
4) 最容易用錯的 2 個地方。不確定的地方請標示「不確定」，不要猜。
```

範本 4：沒有輸出 / 卡住
```
RP2350 程式燒錄後 {{沒有任何輸出 / 印到某行後卡住 / 計時結果為 0}}。
stdio 設定：{{USB 或 UART}}；build type：{{Release/Debug}}；binary type：{{default/copy_to_ram}}。
main.c：
{{貼上程式}}
已檢查過：{{列出已檢查項目}}
請依可能性高低列出原因與逐步排查方法（每步要說明觀察到什麼代表什麼）。
```

範本 5：量測程式
```
請寫一段 pico-sdk C 程式，在 RP2350 {{Cortex-M33 / Hazard3}} 上量測 {{函式名稱}} 的執行時間：
暖機 1 次、重複 {{N}} 次、輸出 min/median/max（µs{{，以及 cycles}}），
結果寫入 volatile 變數避免被優化掉，計時區段內不得有 printf。
並附上需要加到 CMakeLists.txt 的 target_link_libraries。
```

---

## 16. 未驗證 / 待確認事項

- ⚠️ DWT CYCCNT 在實機（SDK 預設 Secure 模式、無除錯器）下的可用性未在板上驗證。
- （已確認，見 `riscv-hazard3.md`）Hazard3 的 `mcountinhibit` reset 值為 0x5，`mcycle`/`minstret` 預設停止；bootrom 與 pico-sdk 都不會打開，量測前要先 `csrci mcountinhibit, 5`。
- （已確認，見 `pico-peripherals.md`）RP2350-E9 只影響 A2 stepping（A3 已修正）：浮接輸入因漏電約 120 µA 停在約 2.2 V，內建 pull-down 拉不下來；對策是改用 pull-up、外接 ≤ 8.2 kΩ pull-down，或只在讀取時才開輸入。
- ⚠️ 寫 flash 時的安全做法（`flash_safe_execute` 等）只列名稱，未詳查。
- ⚠️ BOOTSEL 磁碟機名稱（`RP2350`）未在官方文件原文確認。
- ⚠️ 考場 judge 的評分方式、是否允許超頻、是否自動燒錄：未知。
