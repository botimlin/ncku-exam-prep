# 08 官方文件導航圖

> 用途：考試時要查「官方原文」的入口。先在這裡找到正確的文件、節號、網址與 Ctrl+F 關鍵字，打開官方頁面，複製「一小段」原文（≤ 約 1200 字元），連同出處貼給考場的小模型，讓它照原文推理，而不是靠它自己的（常常錯的）記憶。
> 適用版本：
> - RP2350 datasheet：Release 8，Build date 01/10/2026（2026-10-01），Build version `80d627281ed5`，1371 頁（PDF 內文由 Typst 產生）。
> - pico-sdk：最新 release `2.3.1`（2026-09-04）；`master` 分支內容與 `2.3.1` 相同（2026-11-10 比對 git tree，0 個差異）。pico-examples 有對應 tag `sdk-2.3.1`。
> - 「Raspberry Pi Pico-series C/C++ SDK」PDF：build-date 2026-09-10（內含 2.3.1 release notes）。
> - Getting started with Raspberry Pi Pico-series：Release 25，Build date 01/10/2026。Pico 2 datasheet：Release 5，Build date 03/07/2026。
> - ROS 2：Jazzy Jalisco（GitHub 分支一律 `jazzy`）。
> 最後更新：2026-11（所有網址於 2026-11-10 實測；驗證方式見第 11 節）

---

## 0. 考場規則提醒（先讀）

- 考場允許：上網、登入個人帳號、開個人雲端筆記。官方 FAQ 明說要查 RP2350 datasheet、Pico SDK、ROS 2 文件請自己上網查。
- 考場禁止：其他 LLM（ChatGPT / Claude / Gemini…）、AI agent、GitHub Copilot 等 AI 程式助手、**搜尋引擎的 AI 摘要**、通訊軟體（Gmail、LINE、Discord）。
- 因此：
  - 不要點任何「AI 摘要 / AI Overview / AI 模式 / Copilot / Search Assist / Duck.ai」區塊或按鈕。
  - GitHub 頁面上的 Copilot 按鈕（檔案右上角、搜尋框旁的 Copilot 圖示）**不要按**。
  - `github.dev`（在 GitHub 按 `.`）是線上編輯器，可能帶 Copilot，考場不要開。
  - 不要開 Gmail（就算只是找書籤也不要）。
- 優先順序：**直接打開書籤 → 站內搜尋 → GitHub 檔案搜尋 → 一般搜尋引擎（加 `udm=14`）**。

---

## 1. 一眼總表：什麼問題開哪裡

| 我要查… | 第一選擇 | 備援 |
|---|---|---|
| 暫存器位址、位元欄位、硬體行為、時序、勘誤 | RP2350 datasheet PDF（第 3 節表格） | pico-sdk `hardware_regs/*.h`（第 5.3 節） |
| SDK 函式簽名、參數意義、回傳值 | pico-sdk 原始碼標頭檔 raw（第 5 節） | 線上 API 文件（第 4 節） |
| 一個功能「怎麼用」的完整範例 | pico-examples（第 6 節） | SDK PDF 第 3 章（PIO）、datasheet 範例節 |
| CMake / 建置 / pioasm / 板子設定 | SDK PDF 第 2、3.3、7、8 章 | `pico_sdk_init.cmake`、`cmake/preload/` |
| ROS 2 概念（QoS、executor、domain ID） | docs.ros.org/en/jazzy Concepts | design.ros2.org、GitHub 原始碼 |
| rclpy / rclcpp API 細節 | docs.ros.org/en/jazzy/p/rclpy、/p/rclcpp | GitHub `jazzy` 分支原始碼 |
| RISC-V 指令、CSR | RP2350 datasheet §3.8 | RISC-V ISA 手冊、Hazard3 文件 |
| Cortex-M33 指令週期 | RP2350 datasheet §3.7.4.9 | Arm TRM（developer.arm.com） |
| Linux 系統呼叫、pthread、termios | man7.org | cppreference（C/C++ 標準庫） |
| GCC 旗標、inline asm 約束 | gcc.gnu.org/onlinedocs | — |
| FreeRTOS API | freertos.org API references | FreeRTOS-Kernel 標頭檔 |
| CRC 參數 | reveng CRC catalogue | — |
| GitLab CI 語法 | docs.gitlab.com/ci/yaml | — |

---

## 2. 主角：RP2350 datasheet

- 網址：https://datasheets.raspberrypi.com/rp2350/rp2350-datasheet.pdf
- 版本字串（第 2 頁 Colophon）：`Release 8` / `Build date 01/10/2026` / `Build version 80d627281ed5`。考試當天打開時先看這三行；若不同，節號大致不變，但頁碼會漂移。
- 大小約 11 MB，1371 頁。考場網路慢時，**先開好放著**。
- 頁碼說明：下表「本版約 p.」是**印在頁面右下角的頁碼**（也是目錄上的頁碼）。PDF 檢視器頁框顯示的實體頁碼通常是它 **+1**（封面算第 1 頁）。最穩的方法：**用節號 + 節名搜尋**，不要靠頁碼。
- 找節的方法：
  1. 開側邊欄「大綱 / Outline / 書籤」，依章展開（章 → 節 → 小節）。
  2. 或 Ctrl+F 輸入「節號 + 點 + 空格 + 節名開頭」，例如 `12.6.4.1. System`；datasheet 內文的標題格式就是 `12.6.4.1. System DREQ table`。
  3. 內文的交叉參照寫成 `Section 12.6.4.1. System DREQ table`，也可用 `Section 12.6` 搜尋所有引用處。
  4. 表格標題格式為 `Table 1254.` 換行接表名；Ctrl+F `Table 1254` 即可。
- 本版的章結構（只列跟考試有關的；節號全部取自本版實際目錄）：
  - 1 Introduction（1.2.3 GPIO functions (Bank 0)）
  - 2 System bus（2.1 Bus fabric、2.2 Address map）
  - 3 Processor subsystem（3.1 SIO、3.2 Interrupts、3.6 Cortex-M33 coprocessors、3.7 Cortex-M33 processor、3.8 Hazard3 processor、3.9 Arm/RISC-V architecture switching）
  - 4 Memory（4.2 SRAM、4.4 External flash and PSRAM (XIP)）
  - 5 Bootrom（5.3 Launching code on Processor Core 1、5.4 Bootrom APIs）
  - 6 Power、7 Resets、8 Clocks（8.6 PLL）
  - 9 GPIO
  - 10 Security（10.7 DMA 安全屬性）
  - 11 PIO
  - 12 Peripherals：12.1 UART、12.2 I2C、12.3 SPI、12.4 ADC and Temperature Sensor、12.5 PWM、**12.6 DMA**、12.7 USB、12.8 System timers、12.9 Watchdog、12.10 Always-on timer、12.11 HSTX、12.12 TRNG、12.13 SHA-256 accelerator、12.14 QMI、12.15 System Control Registers
  - 13 OTP、14 Electrical and mechanical（14.9.4 IO electrical characteristics）
  - Appendix A Register field types、Appendix C Hardware revision history（A2 / A3 / A4）、**Appendix D Errata**、Appendix E Documentation release history
- 「List of registers」節：每個周邊最後一個小節都是暫存器表（例：§3.1.11 SIO、§11.7 PIO、§12.6.10 DMA、§12.8.5 TIMER）。要查某個位元欄位，Ctrl+F 暫存器名稱（例 `CH0_CTRL_TRIG`、`SM0_SHIFTCTRL`），會跳到暫存器的位元表。
- 注意：RP2350 ≠ RP2040。小模型常把兩者混為一談。凡是 RP2040 時代的知識（例如 SIO 硬體除法器、PIO 只有 2 個、DMA 只有 12 通道），都要以 RP2350 datasheet 為準：
  - §3.1.7 Integer divider 明寫 RP2040 的記憶體映射除法器在 RP2350 **不存在**（處理器有除法指令）。
  - §11.1.1、§12.6.1、§9.2、§12.3.1、§12.4.1、§12.5.1.1、§12.8.1.1、§12.9.2 都是「Changes from RP2040」，差異一次看清楚。

---

## 3. RP2350 datasheet 主題 → 節號對照表

> 每一列的「Ctrl+F 關鍵字」都已在本版 PDF 文字中、該節範圍內實際搜尋到（2026-11-10 用 `pdftotext -layout` 驗證）。關鍵字區分大小寫時請照抄。

#### 系統匯流排與記憶體

| 要找什麼 | 節號 | 官方節名 | Ctrl+F 關鍵字 | 本版約 p. |
|---|---|---|---|---|
| 匯流排總覽、誰能同時存取 | §2.1 | Bus fabric | `crossbar` / `AHB5` | 22 |
| 匯流排優先權（DMA 搶不到頻寬） | §2.1.1 | Bus priority | `BUS_PRIORITY` | 23 |
| 原子暫存器別名 XOR/SET/CLR | §2.1.3 | Atomic register access | `0x1000` / `0x2000` / `0x3000` | 23 |
| 8/16-bit 窄寫入被複製 | §2.1.5 | Narrow IO register writes | `narrow` | 24 |
| 跨核 exclusive / LDREX / lr.w | §2.1.6 | Global Exclusive Monitor | `exclusive` | 25 |
| 匯流排效能計數器 | §2.1.7 | Bus performance counters | `PERFCTR` | 27 |
| 位址總表（各周邊 base） | §2.2 | Address map | `Address Map Summary` | 27 |
| SRAM 位址、striped vs non-striped | §2.2.3 | SRAM | `SRAM0` / `striped` | 28 |
| SIO 位址 0xd0000000 | §2.2.6 | Core-local peripherals (SIO) | `0xd0000000` | 30 |
| SRAM 分 bank、striped 配置 | §4.2 | SRAM | `SRAM0` / `SRAM1` | 311 |
| XIP cache（flash 執行太慢） | §4.4.1 | XIP cache | `cache` | 315 |
| XIP cache 維護 | §4.4.1.1 | Cache maintenance | `maintenance` | 315 |
| XIP streaming DMA | §4.4.3 | Streaming DMA interface | `STREAM` | 319 |

#### SIO（單週期 IO）

| 要找什麼 | 節號 | 官方節名 | Ctrl+F 關鍵字 | 本版約 p. |
|---|---|---|---|---|
| SIO 總覽、暫存器清單 | §3.1 | SIO | `SIO` | 33 |
| CPUID（我在哪顆核） | §3.1.2 | CPUID | `CPUID` | 35 |
| SIO GPIO 控制（gpio_put 底層） | §3.1.3 | GPIO control | `GPIO_OUT` / `GPIO_HI_OUT` | 36 |
| 硬體 spinlock | §3.1.4 | Hardware spinlocks | `SPINLOCK0` / `SPINLOCK31` | 37 |
| 核間 FIFO（mailbox） | §3.1.5 | Inter-processor FIFOs (Mailboxes) | `FIFO_WR` / `FIFO_RD` / `FIFO_ST` | 38 |
| Doorbells | §3.1.6 | Doorbells | `DOORBELL` | 39 |
| 整數除法器（RP2350 已無 SIO divider） | §3.1.7 | Integer divider | `divider` | 39 |
| RISC-V platform timer（MTIME） | §3.1.8 | RISC-V platform timer | `MTIME` | 39 |
| TMDS encoder | §3.1.9 | TMDS encoder | `TMDS` | 40 |
| Interpolator 總覽 | §3.1.10 | Interpolator | `INTERP0` / `ACCUM0` | 40 |
| Interpolator lane 運算 | §3.1.10.1 | Lane operations | `SHIFT` / `MASK_LSB` | 42 |
| Interpolator blend | §3.1.10.2 | Blend mode | `BLEND` | 43 |
| Interpolator clamp | §3.1.10.3 | Clamp Mode | `CLAMP` | 46 |
| interp 範例：線性內插 | §3.1.10.4 | Sample use case: linear interpolation | `linear interpolation` | 46 |
| interp 範例：texture mapping | §3.1.10.5 | Sample use case: simple affine texture mapping | `texture` | 47 |
| SIO 暫存器表 | §3.1.11 | List of registers | `SPINLOCK_ST` / `FIFO_ST` | 49 |

#### 中斷與處理器

| 要找什麼 | 節號 | 官方節名 | Ctrl+F 關鍵字 | 本版約 p. |
|---|---|---|---|---|
| 中斷編號表（IRQ 號碼） | §3.2 | Interrupts | `DMA_IRQ_0` / `TIMER0_IRQ_0` | 80 |
| NMI | §3.2.1 | Non-maskable interrupt (NMI) | `NMI` | 81 |
| Arm 事件 SEV/WFE | §3.3 | Event signals (Arm) | `WFE` / `SEV` | 82 |
| RISC-V 事件 | §3.4 | Event signals (RISC-V) | `h3.block` | 82 |
| GPIO 協處理器 GPIOC（mcrr 快速 IO） | §3.6.1 | GPIO coprocessor (GPIOC) | `GPIOC` | 96 |
| 雙精度協處理器 DCP | §3.6.2 | Double-precision coprocessor (DCP) | `DCP` | 99 |
| Cortex-M33 設定（FPU/DSP/MPU 數量） | §3.7.2 | Configuration | `FPU` / `NVIC` | 116 |
| M33 NVIC 設定 | §3.7.2.5 | NVIC | `NVIC` | 119 |
| M33 程式模型、例外 | §3.7.4 | Programmer’s model | `Exceptions` | 122 |
| M33 未對齊存取 | §3.7.4.3.2 | Unaligned accesses | `unaligned` | 124 |
| M33 exclusive monitor | §3.7.4.4 | Exclusive monitor | `exclusive` | 124 |
| M33 指令週期（執行時間） | §3.7.4.9 | Execution timing | `cycle` | 127 |
| M33 乘法週期 | §3.7.4.9.3 | Multiply instructions | `MUL` | 128 |
| M33 除法週期 | §3.7.4.9.4 | Divide instructions | `divide` | 129 |
| M33 分支週期 | §3.7.4.9.7 | Branches | `branch` | 129 |
| M33 dual issue | §3.7.4.9.9 | Dual issue | `dual` | 131 |
| M33 浮點指令週期 | §3.7.4.9.10 | Floating-point coprocessor operations | `VADD` | 131 |
| M33 DWT（CYCCNT 量測） | §3.7.4.11 | Data Watchpoint and Trace unit (DWT) | `DWT` | 133 |
| M33 暫存器表（SysTick/SCB/NVIC） | §3.7.5 | List of registers | `SYST_CSR` / `NVIC_ISER0` | 135 |
| Hazard3 總覽 | §3.8 | Hazard3 processor | `Hazard3` | 226 |
| Hazard3 架構字串（支援哪些擴充） | §3.8.1.2 | Architecture strings | `Zba` / `Zbb` / `Zbs` / `Zcmp` | 227 |
| RV32I 指令 | §3.8.1.7 | RV32I: base ISA (register-register) | `add` | 230 |
| M 擴充（乘除） | §3.8.1.12 | M: Multiply and Divide | `mulh` / `divu` | 240 |
| A 擴充（原子；lr/sc 只在 SRAM） | §3.8.1.13 | A: Atomics | `lr.w` / `amoswap` | 241 |
| Zbb（clz/cpop/min/max/rev8） | §3.8.1.16 | Zbb: bit manipulation (basic) | `clz` / `cpop` / `rev8` | 247 |
| Zbs（bset/bclr/bext） | §3.8.1.17 | Zbs: Bit manipulation (single-bit) | `bext` | 251 |
| Zcmp（push/pop） | §3.8.1.20 | Zcmp: Compressed push, pop, and double move | `cm.push` | 254 |
| Zicsr | §3.8.1.22 | Zicsr: Control and status register access | `csrrw` | 255 |
| Hazard3 記憶體存取 | §3.8.2 | Memory access | `Endianness` | 258 |
| Hazard3 PMP | §3.8.3 | Memory protection | `pmpcfg` | 259 |
| Hazard3 中斷與例外 | §3.8.4 | Interrupts and exceptions | `mcause` / `mtvec` | 261 |
| Hazard3 中斷呼叫慣例 | §3.8.4.2.2 | Interrupt calling convention | `calling convention` | 263 |
| Xh3irq 中斷控制器（meiea/meipa/meinext） | §3.8.6.1 | Xh3irq: Hazard3 interrupt controller | `meiea` / `meinext` | 265 |
| Xh3irq 優先權 | §3.8.6.1.4 | Interrupt priority | `meipra` | 267 |
| Xh3irq 最小 handler 範例 | §3.8.6.1.6 | Minimal handler example | `handler` | 268 |
| Xh3power（h3.block/unblock） | §3.8.6.3 | Xh3power: Hazard3 power management | `h3.block` / `h3.unblock` | 270 |
| Xh3bextm（h3.bextm） | §3.8.6.4 | Xh3bextm: Hazard3 bit extract multiple | `h3.bextm` | 271 |
| Hazard3 指令週期總表 | §3.8.7 | Instruction cycle counts | `Cycles` | 272 |
| Hazard3 RV32I 週期 | §3.8.7.1 | RV32I | `branch` | 272 |
| Hazard3 M 週期（除法） | §3.8.7.2 | M extension | `div` | 274 |
| Hazard3 bitmanip 週期 | §3.8.7.6 | Bit manipulation | `Zbb` | 275 |
| Hazard3 分支預測器 | §3.8.7.10 | Branch predictor | `branch predictor` | 277 |
| Hazard3 delay loop 陷阱 | §3.8.7.10.1 | Caveat: delay loops | `delay` | 277 |
| Hazard3 設定參數（EXTENSION_*） | §3.8.8 | Configuration | `EXTENSION_A` / `MUL_FAST` | 278 |
| Hazard3 CSR 清單（mcycle/minstret/mcountinhibit） | §3.8.9 | Control and status registers | `mcycle` / `minstret` / `mcountinhibit` | 279 |
| Arm/RISC-V 切換 | §3.9 | Arm/RISC-V architecture switching | `ARCHSEL` | 309 |

#### 開機與核心 1

| 要找什麼 | 節號 | 官方節名 | Ctrl+F 關鍵字 | 本版約 p. |
|---|---|---|---|---|
| 在核心 1 上啟動程式 | §5.3 | Launching code on Processor Core 1 | `core 1` | 345 |
| Bootrom API | §5.4 | Bootrom APIs | `rom_func_lookup` | 346 |

#### 時脈、重置、電源

| 要找什麼 | 節號 | 官方節名 | Ctrl+F 關鍵字 | 本版約 p. |
|---|---|---|---|---|
| 時脈總覽（clk_sys/clk_peri/clk_adc） | §8.1 | Overview | `clk_sys` / `clk_peri` | 467 |
| 時脈來源 | §8.1.2 | Clock sources | `XOSC` | 468 |
| 時脈產生器（除頻器、glitchless mux） | §8.1.3 | Clock generators | `glitchless` | 471 |
| 頻率計數器 | §8.1.4 | Frequency counter | `frequency counter` | 474 |
| 時脈程式模型 | §8.1.6 | Programmer’s model | `clock_configure` | 476 |
| XOSC | §8.2 | Crystal oscillator (XOSC) | `XOSC` | 506 |
| PLL 參數計算（超頻） | §8.6.3 | Calculating PLL parameters | `FBDIV` / `POSTDIV1` | 527 |
| 子系統重置（RESETS） | §7.5 | Subsystem resets | `RESET` | 457 |
| 電源降低策略（SLEEP/DORMANT） | §6.5 | Power reduction strategies | `DORMANT` | 445 |

#### GPIO

| 要找什麼 | 節號 | 官方節名 | Ctrl+F 關鍵字 | 本版約 p. |
|---|---|---|---|---|
| GPIO 總覽 | §9.1 | Overview | `SIO` | 538 |
| GPIO 與 RP2040 差異（ISO 隔離） | §9.2 | Changes from RP2040 | `isolation` | 539 |
| GPIO 重置狀態 | §9.3 | Reset state | `reset` | 539 |
| 功能選擇表 F0–F11（Table 677） | §9.4 | Function select | `FUNCSEL` / `Table 677` | 540 |
| GPIO 中斷 | §9.5 | Interrupts | `edge` | 542 |
| Pads（pull/drive/slew/schmitt） | §9.6 | Pads | `DRIVE` / `slew` / `SCHMITT` | 543 |
| Pad isolation latch（RP2350 新） | §9.7 | Pad isolation latches | `ISO` | 544 |
| GPIO 範例：選功能 | §9.10.1 | Select an IO function | `gpio_set_function` | 546 |
| GPIO 範例：中斷 | §9.10.2 | Enable a GPIO interrupt | `irq` | 547 |
| IO_BANK0 暫存器 | §9.11.1 | IO - User Bank | `GPIO0_CTRL` | 548 |
| PADS_BANK0 暫存器 | §9.11.3 | Pad Control - User Bank | `GPIO0` | 704 |
| GPIO 功能表（第 1 章版本） | §1.2.3 | GPIO functions (Bank 0) | `F1` | 17 |

#### PIO

| 要找什麼 | 節號 | 官方節名 | Ctrl+F 關鍵字 | 本版約 p. |
|---|---|---|---|---|
| PIO 總覽（3 個 PIO × 4 SM） | §11.1 | Overview | `state machine` | 791 |
| PIO 與 RP2040 差異（v1 新功能） | §11.1.1 | Changes from RP2040 | `RP2040` | 792 |
| PIO 程式模型 | §11.2 | Programmer’s model | `OSR` / `ISR` | 793 |
| 控制流程（wrap） | §11.2.2 | Control flow | `wrap` | 794 |
| 暫存器 OSR/ISR/X/Y | §11.2.3 | Registers | `Output Shift Register` | 795 |
| FIFO | §11.2.4.4 | FIFOs | `FIFO` | 797 |
| Stall | §11.2.5 | Stalling | `stall` | 797 |
| Pin mapping（IN/OUT/SET/side-set 基底） | §11.2.6 | Pin mapping | `side-set` | 798 |
| IRQ flag | §11.2.7 | IRQ flags | `IRQ` | 798 |
| 多 SM 互動 | §11.2.8 | Interactions between state machines | `state machines` | 798 |
| pioasm 指令（directive） | §11.3.1 | Directives | `.side_set` / `.wrap` | 799 |
| pioasm 數值/表達式 | §11.3.2 | Values | `integer` | 800 |
| pioasm 偽指令（nop） | §11.3.7 | Pseudo-instructions | `nop` | 802 |
| 指令集總表（編碼） | §11.4.1 | Summary | `JMP` / `WAIT` | 802 |
| JMP | §11.4.2 | JMP | `X--` | 803 |
| WAIT | §11.4.3 | WAIT | `polarity` | 804 |
| IN | §11.4.4 | IN | `bit_count` | 805 |
| OUT | §11.4.5 | OUT | `PINDIRS` | 806 |
| PUSH | §11.4.6 | PUSH | `iffull` / `block` | 807 |
| PULL | §11.4.7 | PULL | `ifempty` / `noblock` | 808 |
| MOV (to RX)（RP2350 新） | §11.4.8 | MOV (to RX) | `rxfifo` | 809 |
| MOV (from RX)（RP2350 新） | §11.4.9 | MOV (from RX) | `rxfifo` | 810 |
| MOV | §11.4.10 | MOV | `Bit reverse` | 810 |
| IRQ 指令 | §11.4.11 | IRQ | `rel` | 812 |
| SET | §11.4.12 | SET | `PINDIRS` | 813 |
| Side-set 細節 | §11.5.1 | Side-set | `.side_set` | 814 |
| Program wrapping | §11.5.2 | Program wrapping | `.wrap_target` | 814 |
| FIFO joining（8 深） | §11.5.3 | FIFO joining | `FJOIN` | 816 |
| Autopush / Autopull | §11.5.4 | Autopush and Autopull | `PULL_THRESH` / `PUSH_THRESH` | 817 |
| Autopush 細節 | §11.5.4.1 | Autopush details | `autopush` | 820 |
| Autopull 細節 | §11.5.4.2 | Autopull Details | `autopull` | 820 |
| 時脈除頻器 CLKDIV | §11.5.5 | Clock Dividers | `CLKDIV` / `fractional` | 821 |
| GPIO mapping、輸出優先序 | §11.5.6 | GPIO mapping | `base` | 822 |
| 輸入同步器（INPUT_SYNC_BYPASS） | §11.5.6.3 | Input synchronisers | `INPUT_SYNC_BYPASS` | 824 |
| 強制 / EXEC 指令 | §11.5.7 | Forced and EXEC’d instructions | `SMx_INSTR` | 824 |
| 範例：Duplex SPI | §11.6.1 | Duplex SPI | `SPI` | 826 |
| 範例：WS2812 | §11.6.2 | WS2812 LEDs | `WS2812` | 829 |
| 範例：UART TX | §11.6.3 | UART TX | `UART` | 831 |
| 範例：UART RX | §11.6.4 | UART RX | `UART` | 833 |
| 範例：I2C | §11.6.7 | I2C | `I2C` | 841 |
| 範例：PWM | §11.6.8 | PWM | `PWM` | 844 |
| 範例：Addition | §11.6.9 | Addition | `addition` | 846 |
| PIO 暫存器表（CTRL/FSTAT/SM_EXECCTRL/SHIFTCTRL/PINCTRL） | §11.7 | List of registers | `FSTAT` / `SM0_EXECCTRL` / `SM0_SHIFTCTRL` / `SM0_PINCTRL` | 847 |

#### 周邊

| 要找什麼 | 節號 | 官方節名 | Ctrl+F 關鍵字 | 本版約 p. |
|---|---|---|---|---|
| UART 總覽 | §12.1 | UART | `PL011` | 871 |
| UART 鮑率除頻器 | §12.1.3.2.1 | Fractional baud rate divider | `fractional` | 874 |
| UART 硬體流控 | §12.1.4 | UART hardware flow control | `CTS` | 875 |
| UART DMA 介面 | §12.1.5 | UART DMA interface | `DMA` | 877 |
| UART 中斷 | §12.1.6 | Interrupts | `UARTRXINTR` | 878 |
| UART 鮑率計算 | §12.1.7.1 | Baud rate calculation | `baud` | 880 |
| I2C 總覽 | §12.2 | I2C | `DW_apb_i2c` | 892 |
| I2C master 操作 | §12.2.10.2 | Master mode operation | `master` | 906 |
| I2C 時脈設定（SCL 計數） | §12.2.14 | IC_CLK frequency configuration | `IC_CLK` | 909 |
| I2C DMA | §12.2.15 | DMA controller interface | `DMA` | 913 |
| SPI 總覽 | §12.3 | SPI | `PL022` | 943 |
| SPI 時脈比（最高速） | §12.3.4.4 | Clock ratios | `clock` | 947 |
| SPI 位元率 | §12.3.4.6.1 | Bit rate generation | `CPSDVSR` | 948 |
| SPI Motorola 格式（CPOL/CPHA） | §12.3.4.9 | Motorola SPI frame format | `SPO` / `SPH` | 949 |
| SPI DMA | §12.3.4.16 | PrimeCell DMA interface | `DMA` | 955 |
| ADC 總覽與溫度感測器 | §12.4 | ADC and Temperature Sensor | `temperature` | 963 |
| ADC 單次取樣 | §12.4.3.1 | One-shot sample | `START_ONCE` | 967 |
| ADC 連續取樣 | §12.4.3.2 | Free-running sampling | `START_MANY` | 968 |
| ADC 多通道輪流 | §12.4.3.3 | Sampling multiple inputs | `RROBIN` | 968 |
| ADC FIFO | §12.4.3.4 | Sample FIFO | `FIFO` | 968 |
| ADC DMA | §12.4.3.5 | DMA | `DREQ` | 969 |
| ADC ENOB | §12.4.4 | ADC ENOB | `ENOB` | 969 |
| PWM 總覽 | §12.5 | PWM | `slice` | 973 |
| PWM 雙緩衝 | §12.5.2.3 | Double buffering | `double` | 977 |
| PWM 除頻器 | §12.5.2.4 | Clock divider | `DIV` | 978 |
| PWM 週期設定（TOP 公式） | §12.5.2.6 | Configuring PWM period | `TOP` | 980 |
| PWM IRQ / DREQ | §12.5.2.7 | Interrupt Request (IRQ) and DMA Data Request (DREQ) | `DREQ` | 980 |
| System timer 總覽（TIMER0/TIMER1） | §12.8 | System timers | `TIMER1` | 1094 |
| Timer counter（TIMEHR/TIMELR 讀法） | §12.8.2 | Counter | `TIMELR` | 1095 |
| Timer alarm | §12.8.3 | Alarms | `ALARM0` | 1095 |
| Timer 讀時間範例 | §12.8.4.1 | Reading the time | `TIMERAWL` | 1096 |
| Watchdog | §12.9 | Watchdog | `watchdog` | 1105 |
| Watchdog 啟用 | §12.9.6.1 | Enabling the watchdog | `enable` | 1106 |
| AON timer | §12.10 | Always-on timer | `AON` | 1109 |
| HSTX | §12.11 | HSTX | `HSTX` | 1113 |
| HSTX 與 PIO 耦合 | §12.11.6 | PIO-to-HSTX coupled mode | `coupled` | 1118 |
| TRNG | §12.12 | TRNG | `TRNG` | 1122 |
| SHA-256 加速器 | §12.13 | SHA-256 accelerator | `SHA-256` | 1131 |
| SHA-256 DMA | §12.13.4 | DMA DREQ interface | `DREQ` | 1132 |
| SYSCFG（輸入同步器旁路等） | §12.15.2 | SYSCFG | `PROC_IN_SYNC_BYPASS` | 1166 |
| BUSCTRL（匯流排優先權、效能計數器） | §12.15.4 | BUSCTRL | `BUS_PRIORITY` / `PERFCTR` | 1170 |

#### DMA

| 要找什麼 | 節號 | 官方節名 | Ctrl+F 關鍵字 | 本版約 p. |
|---|---|---|---|---|
| DMA 總覽（16 通道） | §12.6 | DMA | `16 independent channels` | 1010 |
| DMA 與 RP2040 差異 | §12.6.1 | Changes from RP2040 | `RP2040` | 1010 |
| 設定通道 | §12.6.2 | Configuring channels | `READ_ADDR` / `WRITE_ADDR` | 1011 |
| 讀寫位址、遞增 | §12.6.2.1 | Read and write addresses | `INCR_READ` / `INCR_WRITE` | 1011 |
| 位址對齊 | §12.6.2.1.1 | Address alignment | `aligned` | 1012 |
| 傳輸次數 TRANS_COUNT | §12.6.2.2 | Transfer count | `TRANS_COUNT` | 1012 |
| Count modes（ENDLESS / TRIGGER_SELF） | §12.6.2.2.1 | Count modes | `ENDLESS` / `TRIGGER_SELF` | 1012 |
| CTRL 暫存器、ring buffer（DATA_SIZE/RING_SIZE/CHAIN_TO） | §12.6.2.3 | Control/Status | `DATA_SIZE` / `RING_SIZE` / `RING_SEL` / `CHAIN_TO` | 1013 |
| 觸發通道 | §12.6.3 | Triggering channels | `trigger` | 1013 |
| Alias 與觸發暫存器（Table 1253） | §12.6.3.1 | Aliases and triggers | `CTRL_TRIG` / `Table 1253` | 1013 |
| Chaining | §12.6.3.2 | Chaining | `CHAIN_TO` | 1014 |
| Null trigger 與 chain 中斷 | §12.6.3.3 | Null triggers and chain interrupts | `null trigger` | 1014 |
| DREQ（pacing） | §12.6.4 | Data request (DREQ) | `TREQ_SEL` | 1015 |
| DREQ 號碼表（Table 1254） | §12.6.4.1 | System DREQ table | `DREQ_PIO0_TX0` / `DREQ_ADC` | 1015 |
| Credit-based DREQ | §12.6.4.2 | Credit-based DREQ Scheme | `credit` | 1016 |
| DMA 中斷（IRQ_0..3） | §12.6.5 | Interrupts | `INTE0` / `INTS` | 1017 |
| DMA 安全 | §12.6.6 | Security | `SECCFG` | 1017 |
| 匯流排錯誤處理 | §12.6.7 | Bus error handling | `READ_ERROR` / `WRITE_ERROR` | 1019 |
| Pacing timer | §12.6.8.1 | Pacing timers | `TIMER0` | 1021 |
| CRC 計算（sniffer） | §12.6.8.2 | CRC calculation | `SNIFF_CTRL` / `SNIFF_DATA` | 1021 |
| Channel abort | §12.6.8.3 | Channel abort | `CHAN_ABORT` | 1021 |
| DMA debug | §12.6.8.4 | Debug | `DBG_TCR` | 1022 |
| 範例：用中斷重設通道 | §12.6.9.1 | Using interrupts to reconfigure a channel | `interrupt` | 1022 |
| 範例：control blocks | §12.6.9.2 | DMA control blocks | `control block` | 1023 |
| DMA 暫存器表 | §12.6.10 | List of Registers | `CH0_READ_ADDR` / `MULTI_CHAN_TRIGGER` / `SNIFF_CTRL` | 1025 |

### 3.1 勘誤 Appendix D（逐條）

> 搜尋方法：Ctrl+F `RP2350-E5`（全文會出現多次：本節 + 各周邊章節中的提醒）。Appendix D 從本版約 p.1351 開始。下表「影響版本」照抄 datasheet 的 Affects 欄。Pico 2 板上的晶片版本可看晶片上的標記，或在程式呼叫 `rp2350_chip_version()`（宣告在 pico-sdk 2.3.1 `src/rp2350/pico_platform/include/pico/platform.h`）。

| 勘誤 | 節號 | 模組 | 一句話摘要（依 datasheet Summary） | 影響版本 | datasheet 的 workaround 重點 |
|---|---|---|---|---|---|
| RP2350-E1 | §D.9.1 | SIO / interpolator | Interpolator 的 OVERF 位元因新的右旋轉行為而失效 | A2、A3、A4 | 自己檢查 ACCUM0/ACCUM1 MSB，或事先算好邊界 |
| RP2350-E2 | §D.9.2 | SIO | SPINLOCK 寫入會鏡像到 +0x80 偏移 | A2、A3、A4 | 改用處理器原子指令；SDK 在 RP2350 預設用軟體鎖；可安全使用的硬體 spinlock：5、6、7、10、11、18–31 |
| RP2350-E3 | §D.1.1 | ACCESSCTRL | QFN-60 封裝下 GPIO_NSMASK 控制到錯的 PADS 暫存器 | A2（僅 QFN-60） | — |
| RP2350-E4 | §D.6.1 | Hazard3 | 核心 1 在 clock-gated sleep 時 System Bus Access 永久卡住 | A2、A3、A4 | （除錯器相關） |
| RP2350-E5 | §D.4.1 | DMA | CHAIN_TO 與 ABORT 作用中通道的交互問題 | A2、A3、A4 | abort 前先清掉「被 abort 的通道」與「它 chain 到的通道」的 `CH0_CTRL_TRIG.EN` |
| RP2350-E6 | §D.6.2 | Hazard3 | PMPCFGx 的 RWX 欄位對調 | A2、A3、A4 | — |
| RP2350-E7 | §D.6.3 | Hazard3 | U-mode 不會忽略 mstatus.mie | A2、A3、A4 | — |
| RP2350-E8 | §D.4.2 | DMA | 零長度傳輸時 CHAIN_TO 可能不觸發 | A2、A3、A4 | 不要把 CHAIN_TO 和零長度傳輸一起用；control block 清單中間用 dummy 傳輸取代 |
| RP2350-E9 | §D.5.1 | GPIO | Bank 0 GPIO 開啟 pad 輸入時漏電增加（內建 pull-down 拉不下來） | A2 | 要 pull-down 時先關 `GPIO0.IE`，讀之前才暫時打開；或外接 ≤ 8.2 kΩ 下拉 |
| RP2350-E11 | §D.10.1 | XIP | cache clean by set/way 會改到 dirty line 的 tag | A2、A3、A4 | — |
| RP2350-E12 | §D.11.1 | USB | USB 狀態訊號同步不足 | A2、A3、A4（A3 有緩解） | — |
| RP2350-E17 | §D.7.2 | OTP | 對單一 ECC OTP row 做 guarded read，若相鄰 row 不是有效 ECC 會 fault | A2、A3、A4 | — |
| RP2350-E27 | §D.3.1 | Bus fabric | APB 與 FASTPERI 仲裁器的 bus priority 套用到錯的 manager | A2、A3、A4 | 無完整修正；在周邊端設 BUS_PRIORITY，SRAM8/SRAM9 當處理器私有記憶體，分散 SRAM0–3 / SRAM4–7 存取 |
| RP2350-E29 | §D.6.4 | Hazard3 | 被 breakpoint 擋住的 CSR 寫入仍會寫進 CSR | A2、A3、A4 | — |
| RP2350-E30 | §D.2.13 | Bootrom | `reboot()` API 在 delay_ms == 0 時不會重開機 | A2、A3、A4 | 傳 delay_ms = 1；SDK 2.3.0 起 wrapper 自動處理 |
| RP2350-E31 | §D.6.5 | Hazard3 | cm.popret / cm.popretz 期間的同步例外在某些條件下 mepc 錯 | A2、A3、A4 | — |

其他勘誤（bootrom / OTP / 安全性，考試大多用不到）：E10、E13、E14、E15、E16、E18、E19、E20、E21、E22、E23、E24、E25（§D.2.x、§D.7.x）、E26（§D.8.1 RCP）、E28（§D.7.3）。晶片版本差異見 Appendix C（§C.1 A2、§C.2 A3、§C.3 A4）。

### 3.2 常用表格編號（本版）

| 表 | 內容 | 所在節 | 本版約 p. |
|---|---|---|---|
| Table 3 | GPIO Bank 0 Functions（第 1 章版） | §1.2.3 | 17 |
| Table 8 | Address Map Summary | §2.2 | 27 |
| Table 11 / 12 | SRAM0–7（striped）/ SRAM8–9（non-striped）位址 | §2.2.3 | 28 |
| Table 13 / 14 / 15 | APB / AHB / SIO 位址表 | §2.2.4–2.2.6 | 29–31 |
| Table 95 | System-level interrupt numbering（IRQ 號碼） | §3.2 | 80 |
| Table 118 | DCP 浮點運算週期（benchmark） | §3.6.2.10 | 106 附近 |
| Table 381–386 | Hazard3 各擴充指令週期 | §3.8.7 | 272–276 |
| Table 387 | Hazard3 設定參數 | §3.8.8 | 278 |
| Table 388 | List of RVCSR Registers | §3.8.9 | 280 |
| Table 677 | GPIO Bank 0 Functions（F0–F11 完整表） | §9.4 | 540 |
| Table 1014 | PIO instruction encoding | §11.4.1 | 802 |
| Table 1253 | DMA control register aliases | §12.6.3.1 | 1013 |
| Table 1254 | DREQs（DREQ 號碼表） | §12.6.4.1 | 1015 |
| Table 1255 | List of DMA Registers | §12.6.10 | 1025 |
| Table 1338 | List of TIMER Registers | §12.8.5 | 1099 |

---

## 4. 其他 Raspberry Pi 官方 PDF 與頁面

| 文件 | 網址 | 版本（2026-11-10） | 考試會用到的章 |
|---|---|---|---|
| Raspberry Pi Pico 2 datasheet（板子） | https://datasheets.raspberrypi.com/pico/pico-2-datasheet.pdf | Release 5，03/07/2026，24 頁 | §3.1 Raspberry Pi Pico 2 pinout（腳位圖）、§5.2 General purpose I/O、§5.3 Using the ADC、§5.7 USB、§5.8 Debugging、Appendix B 電路圖 |
| Getting started with Raspberry Pi Pico-series | https://datasheets.raspberrypi.com/pico/getting-started-with-pico.pdf | Release 25，01/10/2026，36 頁 | §5「Say "Hello World" in C」（§5.1 Serial input and output、§5.3 Build your project）、Appendix A Debugprobe、Appendix B Picotool、**Appendix C Command-line toolchain setup**（不用 VS Code 時怎麼建置） |
| Raspberry Pi Pico-series C/C++ SDK | https://datasheets.raspberrypi.com/pico/raspberry-pi-pico-c-sdk.pdf | build-date 2026-09-10，828 頁，含 2.3.1 notes | 見下表 |
| Hardware design with RP2350 | https://datasheets.raspberrypi.com/rp2350/hardware-design-with-rp2350.pdf | — | 只有考硬體設計才用 |
| Raspberry Pi Pico-series Python SDK（MicroPython） | https://datasheets.raspberrypi.com/pico/raspberry-pi-pico-python-sdk.pdf | — | 題目若用 MicroPython 才用 |
| 微控制器文件入口 | https://www.raspberrypi.com/documentation/microcontrollers/ | — | 各板子與 SDK 頁面連結 |
| C/C++ SDK 說明頁 | https://www.raspberrypi.com/documentation/microcontrollers/c_sdk.html | — | 安裝、連到 SDK PDF |
| Pico 系列板子頁 | https://www.raspberrypi.com/documentation/microcontrollers/pico-series.html | — | 板子規格、debug 接頭 |
| 晶片頁 | https://www.raspberrypi.com/documentation/microcontrollers/silicon.html | — | RP2350 文件總連結（錨點 `#rp2350`） |
| Debug Probe | https://www.raspberrypi.com/documentation/microcontrollers/debug-probe.html | — | openocd / gdb 指令 |

### 4.1 C/C++ SDK PDF 重點章（節號取自該 PDF 目錄）

| 章節 | 內容 | 何時查 |
|---|---|---|
| 1.2 Anatomy of a SDK Application | 最小 CMakeLists + main | 建專案 |
| 2.1 The Build System；2.2 Every Library is an INTERFACE Library | `target_link_libraries` 為何要連 `hardware_dma` 等 | 連結錯誤 undefined reference |
| 2.3 SDK Library Structure（2.3.1–2.3.9，含 2.3.4 Hardware Structs、2.3.5 Hardware Registers、2.3.7 FreeRTOS Ports） | 各層函式庫的分工 | 要直接碰暫存器時 |
| 2.5 Conventions for Library Functions（2.5.4 Builder Pattern） | `*_get_default_config` + `channel_config_set_*` 的寫法 | 看懂 DMA / PIO 設定 API |
| 2.6 Customisation and Configuration Using Preprocessor variables | `PICO_*` 巨集怎麼設 | 改預設值 |
| 2.7 SDK Runtime（2.7.1 stdio、2.7.5 Floating-point Support、2.7.6 Hardware Divider） | printf 走 USB 還是 UART、float 實作 | 輸出看不到、浮點慢 |
| **2.8 Multi-core support** | `multicore_launch_core1` 等 | 雙核 |
| 2.10 Supporting both RP2040 and RP2350 | 平台差異巨集 | 跨晶片程式 |
| 3.2 Getting started with PIO（3.2.3 PIO and DMA (A Logic Analyser)） | PIO 從 C 端設定的完整範例 | PIO 入門 |
| **3.3 Using PIOASM, the PIO Assembler**（3.3.2 Directives … 3.3.10 Language generators） | `.pio` 語法、`pico_generate_pio_header` | 寫 / 讀 .pio |
| 3.4 PIO Instruction Set Reference（3.4.1 Encoding version 0 RP2040、3.4.2 version 1 RP2350） | 與 datasheet §11.4 同內容 | 指令編碼 |
| 5.1–5.6 Library documentation | 與線上 API 文件同內容（PDF 版） | 網站打不開時 |
| 7 CMake build configuration（7.2 Platform and Board、7.3 Compiler and Toolchain） | `PICO_PLATFORM=rp2350-arm-s` / `rp2350-riscv`、`PICO_BOARD=pico2` | 切換 Arm/RISC-V |
| 8 CMake build functions（8.2 Alphabetical List） | `pico_enable_stdio_usb`、`pico_add_extra_outputs`、`pico_set_binary_type` | CMake 函式用法 |

PDF 搜尋提示：Ctrl+F `pico_generate_pio_header`、`PICO_PLATFORM`、`multicore_launch_core1`、`copy_to_ram`、`no_flash`。

---

## 5. pico-sdk 線上 API 文件

- 入口：https://www.raspberrypi.com/documentation/pico-sdk/
- 這個網站在 Cloudflare 後面：用程式（curl）抓會得到 403「Just a moment...」，**一般瀏覽器會自動通過**。2026-11-10 用真實瀏覽器開啟並在頁面 DOM 中逐一確認下列 `id` 存在。考場若出現人機驗證，自己點過即可；若一直打不開，改用第 6 節的 GitHub 標頭檔（內容相同，而且更好貼）。
- 四個主頁面：
  - Hardware APIs：https://www.raspberrypi.com/documentation/pico-sdk/hardware.html
  - High Level APIs：https://www.raspberrypi.com/documentation/pico-sdk/high_level.html
  - Runtime Infrastructure：https://www.raspberrypi.com/documentation/pico-sdk/runtime.html
  - Networking Libraries：https://www.raspberrypi.com/documentation/pico-sdk/networking.html
- 用法：網址後面加 `#group_xxx` 直接跳到該函式庫。進去後 Ctrl+F 函式名稱。每個函式的錨點形如 `#group_hardware_dma_1g...`（雜湊值，會變，不要背；用 Ctrl+F）。

| 函式庫 | 直接連結（已確認錨點存在） | 重要子群組錨點 |
|---|---|---|
| hardware_dma | https://www.raspberrypi.com/documentation/pico-sdk/hardware.html#group_hardware_dma | `#group_channel_config`（`channel_config_set_*`） |
| hardware_pio | https://www.raspberrypi.com/documentation/pico-sdk/hardware.html#group_hardware_pio | `#group_sm_config`（`sm_config_set_*`）、`#group_pio_instructions`（`pio_encode_*`） |
| hardware_gpio | https://www.raspberrypi.com/documentation/pico-sdk/hardware.html#group_hardware_gpio | — |
| hardware_uart | https://www.raspberrypi.com/documentation/pico-sdk/hardware.html#group_hardware_uart | — |
| hardware_spi | https://www.raspberrypi.com/documentation/pico-sdk/hardware.html#group_hardware_spi | — |
| hardware_i2c | https://www.raspberrypi.com/documentation/pico-sdk/hardware.html#group_hardware_i2c | — |
| hardware_pwm | https://www.raspberrypi.com/documentation/pico-sdk/hardware.html#group_hardware_pwm | — |
| hardware_adc | https://www.raspberrypi.com/documentation/pico-sdk/hardware.html#group_hardware_adc | — |
| hardware_irq | https://www.raspberrypi.com/documentation/pico-sdk/hardware.html#group_hardware_irq | `#group_hardware_irq_1interrupt_nums`（IRQ 號碼表） |
| hardware_sync | https://www.raspberrypi.com/documentation/pico-sdk/hardware.html#group_hardware_sync | — |
| hardware_interp | https://www.raspberrypi.com/documentation/pico-sdk/hardware.html#group_hardware_interp | `#group_interp_config` |
| hardware_timer | https://www.raspberrypi.com/documentation/pico-sdk/hardware.html#group_hardware_timer | — |
| hardware_clocks | https://www.raspberrypi.com/documentation/pico-sdk/hardware.html#group_hardware_clocks | — |
| hardware_watchdog | https://www.raspberrypi.com/documentation/pico-sdk/hardware.html#group_hardware_watchdog | — |
| hardware_base（`hw_set_bits` 等） | https://www.raspberrypi.com/documentation/pico-sdk/hardware.html#group_hardware_base | — |
| hardware_claim（`dma_claim_unused_channel` 背後） | https://www.raspberrypi.com/documentation/pico-sdk/hardware.html#group_hardware_claim | — |
| hardware_hazard3 | https://www.raspberrypi.com/documentation/pico-sdk/hardware.html#group_hardware_hazard3 | — |
| hardware_riscv | https://www.raspberrypi.com/documentation/pico-sdk/hardware.html#group_hardware_riscv | `#group_hardware_riscv_platform_timer` |
| hardware_xip_cache | https://www.raspberrypi.com/documentation/pico-sdk/hardware.html#group_hardware_xip_cache | — |
| hardware_divider（RP2350 上是軟體） | https://www.raspberrypi.com/documentation/pico-sdk/hardware.html#group_hardware_divider | — |
| hardware_pll / xosc / resets / vreg / powman / sha256 / dcp / rcp / exception / flash / ticks | 同頁 `#group_hardware_pll`、`#group_hardware_xosc`、`#group_hardware_resets`、`#group_hardware_vreg`、`#group_hardware_powman`、`#group_hardware_sha256`、`#group_hardware_dcp`、`#group_hardware_rcp`、`#group_hardware_exception`、`#group_hardware_flash`、`#group_hardware_ticks` | — |
| pico_multicore | https://www.raspberrypi.com/documentation/pico-sdk/high_level.html#group_pico_multicore | `#group_multicore_fifo`、`#group_multicore_doorbell`、`#group_multicore_lockout` |
| pico_sync | https://www.raspberrypi.com/documentation/pico-sdk/high_level.html#group_pico_sync | `#group_critical_section`、`#group_lock_core`、`#group_mutex`、`#group_sem` |
| pico_time | https://www.raspberrypi.com/documentation/pico-sdk/high_level.html#group_pico_time | `#group_timestamp`、`#group_sleep`、`#group_alarm`、`#group_repeating_timer` |
| pico_stdlib | https://www.raspberrypi.com/documentation/pico-sdk/high_level.html#group_pico_stdlib | — |
| pico_util（queue 等） | https://www.raspberrypi.com/documentation/pico-sdk/high_level.html#group_pico_util | `#group_queue`、`#group_util_pheap`、`#group_fixed_bitset` |
| pico_async_context | https://www.raspberrypi.com/documentation/pico-sdk/high_level.html#group_pico_async_context | `#group_async_context_freertos` |
| pico_rand / pico_unique_id / pico_aon_timer | 同頁 `#group_pico_rand`、`#group_pico_unique_id`、`#group_pico_aon_timer` | — |
| pico_stdio | https://www.raspberrypi.com/documentation/pico-sdk/runtime.html#group_pico_stdio | `#group_pico_stdio_usb`、`#group_pico_stdio_uart`、`#group_pico_stdio_rtt` |
| pico_platform（`__not_in_flash_func` 等） | https://www.raspberrypi.com/documentation/pico-sdk/runtime.html#group_pico_platform | — |
| pico_runtime_init / pico_float / pico_double / pico_atomic | 同頁 `#group_pico_runtime_init`、`#group_pico_float`、`#group_pico_double`、`#group_pico_atomic` | — |
| pico_cyw43_arch（Pico 2 W 無線） | https://www.raspberrypi.com/documentation/pico-sdk/networking.html#group_pico_cyw43_arch | — |

---

## 6. pico-sdk GitHub 原始碼（最佳貼上來源）

### 6.1 為什麼標頭檔是最好的貼上來源

- 標頭檔裡有**精確的函式簽名 + Doxygen 註解**（`\param`、`\return`、注意事項），線上 API 文件就是從這些註解產生的，內容一樣但標頭檔是純文字，複製不會亂。
- `raw.githubusercontent.com` 是純文字頁面：不用登入、沒有按鈕、沒有 Copilot，Ctrl+F 最乾淨。
- 只要複製「一個函式的註解 + 宣告」（通常 10–30 行），就是小模型最需要的資料量。
- 許多 inline 函式的**實作就寫在標頭檔裡**（例：`dma_channel_set_read_addr` 只是寫暫存器），貼上去模型就能看懂實際行為。

### 6.2 GitHub 使用技巧（不用 AI）

- 倉庫：https://github.com/raspberrypi/pico-sdk （release tag：`2.3.1`；branch `master` = 最新 release，`develop` = 開發中）。Releases：https://github.com/raspberrypi/pico-sdk/releases
- 在倉庫頁按 `t`：檔案搜尋器（file finder），輸入 `dma.h`、`pio_instructions` 等檔名片段即可。
- 在檔案頁按 `y`：把網址換成固定 commit 的永久連結（permalink）。按 `l`：跳到指定行號。按 `w`：切換 branch / tag。按 `s` 或 `/`：聚焦搜尋框。（以上依 GitHub 官方 Keyboard shortcuts 文件）
- 檔案頁右上角「Raw」按鈕 → 純文字，再 Ctrl+F。
- 程式碼全文搜尋（code search）：在搜尋框輸入 `repo:raspberrypi/pico-sdk dma_channel_configure`。⚠️未驗證：此功能可能要求登入 GitHub；考場允許登入個人帳號。**搜尋結果頁與檔案頁上的 Copilot 按鈕都不要按。**
- 不要按 `.`（開 github.dev 編輯器）。
- 官方說明：
  - https://docs.github.com/en/get-started/accessibility/keyboard-shortcuts
  - https://docs.github.com/en/repositories/working-with-files/using-files/getting-permanent-links-to-files
  - https://docs.github.com/en/search-github/github-code-search/understanding-github-code-search-syntax

### 6.3 各函式庫主標頭檔（raw，釘在 tag 2.3.1；把 `2.3.1` 換成 `master` 也可用）

前綴 `RAW = https://raw.githubusercontent.com/raspberrypi/pico-sdk/2.3.1/`；網頁版把前綴換成 `https://github.com/raspberrypi/pico-sdk/blob/2.3.1/`。

| 函式庫 | 標頭檔路徑 | raw 網址 |
|---|---|---|
| hardware_dma | `src/rp2_common/hardware_dma/include/hardware/dma.h` | https://raw.githubusercontent.com/raspberrypi/pico-sdk/2.3.1/src/rp2_common/hardware_dma/include/hardware/dma.h |
| hardware_pio | `src/rp2_common/hardware_pio/include/hardware/pio.h` | https://raw.githubusercontent.com/raspberrypi/pico-sdk/2.3.1/src/rp2_common/hardware_pio/include/hardware/pio.h |
| PIO 指令編碼 | `src/rp2_common/hardware_pio/include/hardware/pio_instructions.h` | https://raw.githubusercontent.com/raspberrypi/pico-sdk/2.3.1/src/rp2_common/hardware_pio/include/hardware/pio_instructions.h |
| hardware_gpio | `src/rp2_common/hardware_gpio/include/hardware/gpio.h` | https://raw.githubusercontent.com/raspberrypi/pico-sdk/2.3.1/src/rp2_common/hardware_gpio/include/hardware/gpio.h |
| hardware_uart | `src/rp2_common/hardware_uart/include/hardware/uart.h` | https://raw.githubusercontent.com/raspberrypi/pico-sdk/2.3.1/src/rp2_common/hardware_uart/include/hardware/uart.h |
| hardware_spi | `src/rp2_common/hardware_spi/include/hardware/spi.h` | https://raw.githubusercontent.com/raspberrypi/pico-sdk/2.3.1/src/rp2_common/hardware_spi/include/hardware/spi.h |
| hardware_i2c | `src/rp2_common/hardware_i2c/include/hardware/i2c.h` | https://raw.githubusercontent.com/raspberrypi/pico-sdk/2.3.1/src/rp2_common/hardware_i2c/include/hardware/i2c.h |
| hardware_pwm | `src/rp2_common/hardware_pwm/include/hardware/pwm.h` | https://raw.githubusercontent.com/raspberrypi/pico-sdk/2.3.1/src/rp2_common/hardware_pwm/include/hardware/pwm.h |
| hardware_adc | `src/rp2_common/hardware_adc/include/hardware/adc.h` | https://raw.githubusercontent.com/raspberrypi/pico-sdk/2.3.1/src/rp2_common/hardware_adc/include/hardware/adc.h |
| hardware_irq | `src/rp2_common/hardware_irq/include/hardware/irq.h` | https://raw.githubusercontent.com/raspberrypi/pico-sdk/2.3.1/src/rp2_common/hardware_irq/include/hardware/irq.h |
| hardware_sync | `src/rp2_common/hardware_sync/include/hardware/sync.h` | https://raw.githubusercontent.com/raspberrypi/pico-sdk/2.3.1/src/rp2_common/hardware_sync/include/hardware/sync.h |
| hardware_interp | `src/rp2_common/hardware_interp/include/hardware/interp.h` | https://raw.githubusercontent.com/raspberrypi/pico-sdk/2.3.1/src/rp2_common/hardware_interp/include/hardware/interp.h |
| hardware_timer | `src/rp2_common/hardware_timer/include/hardware/timer.h` | https://raw.githubusercontent.com/raspberrypi/pico-sdk/2.3.1/src/rp2_common/hardware_timer/include/hardware/timer.h |
| hardware_clocks | `src/rp2_common/hardware_clocks/include/hardware/clocks.h` | https://raw.githubusercontent.com/raspberrypi/pico-sdk/2.3.1/src/rp2_common/hardware_clocks/include/hardware/clocks.h |
| hardware_watchdog | `src/rp2_common/hardware_watchdog/include/hardware/watchdog.h` | https://raw.githubusercontent.com/raspberrypi/pico-sdk/2.3.1/src/rp2_common/hardware_watchdog/include/hardware/watchdog.h |
| hardware_base（`hw_set_bits`、`hw_write_masked`） | `src/rp2_common/hardware_base/include/hardware/address_mapped.h` | https://raw.githubusercontent.com/raspberrypi/pico-sdk/2.3.1/src/rp2_common/hardware_base/include/hardware/address_mapped.h |
| hardware_claim | `src/common/hardware_claim/include/hardware/claim.h` | https://raw.githubusercontent.com/raspberrypi/pico-sdk/2.3.1/src/common/hardware_claim/include/hardware/claim.h |
| hardware_hazard3 | `src/rp2_common/hardware_hazard3/include/hardware/hazard3.h` | https://raw.githubusercontent.com/raspberrypi/pico-sdk/2.3.1/src/rp2_common/hardware_hazard3/include/hardware/hazard3.h |
| hardware_riscv（CSR 巨集） | `src/rp2_common/hardware_riscv/include/hardware/riscv.h` | https://raw.githubusercontent.com/raspberrypi/pico-sdk/2.3.1/src/rp2_common/hardware_riscv/include/hardware/riscv.h |
| hardware_xip_cache | `src/rp2_common/hardware_xip_cache/include/hardware/xip_cache.h` | https://raw.githubusercontent.com/raspberrypi/pico-sdk/2.3.1/src/rp2_common/hardware_xip_cache/include/hardware/xip_cache.h |
| hardware_sha256 | `src/rp2_common/hardware_sha256/include/hardware/sha256.h` | https://raw.githubusercontent.com/raspberrypi/pico-sdk/2.3.1/src/rp2_common/hardware_sha256/include/hardware/sha256.h |
| pico_multicore | `src/rp2_common/pico_multicore/include/pico/multicore.h` | https://raw.githubusercontent.com/raspberrypi/pico-sdk/2.3.1/src/rp2_common/pico_multicore/include/pico/multicore.h |
| pico_sync：mutex | `src/common/pico_sync/include/pico/mutex.h` | https://raw.githubusercontent.com/raspberrypi/pico-sdk/2.3.1/src/common/pico_sync/include/pico/mutex.h |
| pico_sync：semaphore | `src/common/pico_sync/include/pico/sem.h` | https://raw.githubusercontent.com/raspberrypi/pico-sdk/2.3.1/src/common/pico_sync/include/pico/sem.h |
| pico_sync：critical section | `src/common/pico_sync/include/pico/critical_section.h` | https://raw.githubusercontent.com/raspberrypi/pico-sdk/2.3.1/src/common/pico_sync/include/pico/critical_section.h |
| pico_sync：lock_core | `src/common/pico_sync/include/pico/lock_core.h` | https://raw.githubusercontent.com/raspberrypi/pico-sdk/2.3.1/src/common/pico_sync/include/pico/lock_core.h |
| pico_time | `src/common/pico_time/include/pico/time.h` | https://raw.githubusercontent.com/raspberrypi/pico-sdk/2.3.1/src/common/pico_time/include/pico/time.h |
| pico_util/queue | `src/common/pico_util/include/pico/util/queue.h` | https://raw.githubusercontent.com/raspberrypi/pico-sdk/2.3.1/src/common/pico_util/include/pico/util/queue.h |
| pico_stdlib | `src/common/pico_stdlib_headers/include/pico/stdlib.h` | https://raw.githubusercontent.com/raspberrypi/pico-sdk/2.3.1/src/common/pico_stdlib_headers/include/pico/stdlib.h |
| pico_stdio | `src/rp2_common/pico_stdio/include/pico/stdio.h` | https://raw.githubusercontent.com/raspberrypi/pico-sdk/2.3.1/src/rp2_common/pico_stdio/include/pico/stdio.h |
| pico_stdio_usb | `src/rp2_common/pico_stdio_usb/include/pico/stdio_usb.h` | https://raw.githubusercontent.com/raspberrypi/pico-sdk/2.3.1/src/rp2_common/pico_stdio_usb/include/pico/stdio_usb.h |
| pico_stdio_uart | `src/rp2_common/pico_stdio_uart/include/pico/stdio_uart.h` | https://raw.githubusercontent.com/raspberrypi/pico-sdk/2.3.1/src/rp2_common/pico_stdio_uart/include/pico/stdio_uart.h |
| pico_rand | `src/rp2_common/pico_rand/include/pico/rand.h` | https://raw.githubusercontent.com/raspberrypi/pico-sdk/2.3.1/src/rp2_common/pico_rand/include/pico/rand.h |
| 基本型別（`uint`、`absolute_time_t`） | `src/common/pico_base_headers/include/pico/types.h` | https://raw.githubusercontent.com/raspberrypi/pico-sdk/2.3.1/src/common/pico_base_headers/include/pico/types.h |
| 平台巨集（RP2350） | `src/rp2350/pico_platform/include/pico/platform.h` | https://raw.githubusercontent.com/raspberrypi/pico-sdk/2.3.1/src/rp2350/pico_platform/include/pico/platform.h |
| 放 RAM 的巨集（`__not_in_flash_func`、`__time_critical_func`；其他編譯器巨集在同層 `pico_platform_compiler/include/pico/platform/compiler.h`） | `src/rp2_common/pico_platform_sections/include/pico/platform/sections.h` | https://raw.githubusercontent.com/raspberrypi/pico-sdk/2.3.1/src/rp2_common/pico_platform_sections/include/pico/platform/sections.h |
| Pico 2 板子定義（LED 腳位等） | `src/boards/include/boards/pico2.h` | https://raw.githubusercontent.com/raspberrypi/pico-sdk/2.3.1/src/boards/include/boards/pico2.h |

函式**實作**（.c）在同一資料夾上一層，例：`src/rp2_common/hardware_dma/dma.c`、`src/rp2_common/hardware_pio/pio.c`、`src/rp2_common/pico_multicore/multicore.c`（皆已確認存在）。

### 6.4 暫存器定義與平台常數（RP2350 專用路徑，不要開成 rp2040）

- 資料夾（網頁）：https://github.com/raspberrypi/pico-sdk/tree/2.3.1/src/rp2350/hardware_regs/include/hardware/regs
- `hardware_regs`（位元欄位巨集，`*_BITS`、`*_LSB`、`*_RESET`）：`src/rp2350/hardware_regs/include/hardware/regs/<name>.h`
  - 常用：`addressmap.h`（各周邊 base）、`dreq.h`（DREQ 號碼）、`intctrl.h`（IRQ 號碼）、`dma.h`、`pio.h`、`sio.h`、`io_bank0.h`、`pads_bank0.h`、`timer.h`、`rvcsr.h`（Hazard3 CSR）、`m33.h`（Cortex-M33 系統暫存器）
  - 例：https://raw.githubusercontent.com/raspberrypi/pico-sdk/2.3.1/src/rp2350/hardware_regs/include/hardware/regs/dreq.h
  - 例：https://raw.githubusercontent.com/raspberrypi/pico-sdk/2.3.1/src/rp2350/hardware_regs/include/hardware/regs/intctrl.h
  - 例：https://raw.githubusercontent.com/raspberrypi/pico-sdk/2.3.1/src/rp2350/hardware_regs/include/hardware/regs/addressmap.h
  - 例：https://raw.githubusercontent.com/raspberrypi/pico-sdk/2.3.1/src/rp2350/hardware_regs/include/hardware/regs/rvcsr.h
- 平台常數（`NUM_DMA_CHANNELS`、`NUM_PIOS`、`NUM_SPIN_LOCKS` 等）：`src/rp2350/hardware_regs/include/hardware/platform_defs.h`
  - https://raw.githubusercontent.com/raspberrypi/pico-sdk/2.3.1/src/rp2350/hardware_regs/include/hardware/platform_defs.h
- `hardware_structs`（`dma_hw->ch[i]`、`pio0_hw->sm[i]`、`sio_hw` 結構）：`src/rp2350/hardware_structs/include/hardware/structs/<name>.h`
  - 常用：`dma.h`、`pio.h`、`sio.h`、`interp.h`、`timer.h`、`io_bank0.h`
  - 例：https://raw.githubusercontent.com/raspberrypi/pico-sdk/2.3.1/src/rp2350/hardware_structs/include/hardware/structs/dma.h
  - 例：https://raw.githubusercontent.com/raspberrypi/pico-sdk/2.3.1/src/rp2350/hardware_structs/include/hardware/structs/sio.h
- 注意：同名檔案也在 `src/rp2040/...` 下，**內容不同**（RP2040 DMA 只有 12 通道）。路徑中一定要是 `rp2350`。

### 6.5 CMake / 工具鏈

| 檔案 | 用途 | raw 網址 |
|---|---|---|
| `pico_sdk_init.cmake` | SDK 初始化 | https://raw.githubusercontent.com/raspberrypi/pico-sdk/2.3.1/pico_sdk_init.cmake |
| `external/pico_sdk_import.cmake` | 複製到自己專案用 | https://raw.githubusercontent.com/raspberrypi/pico-sdk/2.3.1/external/pico_sdk_import.cmake |
| `cmake/preload/platforms/rp2350-arm-s.cmake` | `PICO_PLATFORM=rp2350-arm-s` | https://raw.githubusercontent.com/raspberrypi/pico-sdk/2.3.1/cmake/preload/platforms/rp2350-arm-s.cmake |
| `cmake/preload/platforms/rp2350-riscv.cmake` | `PICO_PLATFORM=rp2350-riscv` | https://raw.githubusercontent.com/raspberrypi/pico-sdk/2.3.1/cmake/preload/platforms/rp2350-riscv.cmake |
| `cmake/preload/toolchains/pico_arm_cortex_m33_gcc.cmake` | Arm 工具鏈旗標 | https://raw.githubusercontent.com/raspberrypi/pico-sdk/2.3.1/cmake/preload/toolchains/pico_arm_cortex_m33_gcc.cmake |
| `cmake/preload/toolchains/pico_riscv_gcc.cmake` | RISC-V 工具鏈旗標（另有 `pico_riscv_gcc_zcb_zcmp.cmake`） | https://raw.githubusercontent.com/raspberrypi/pico-sdk/2.3.1/cmake/preload/toolchains/pico_riscv_gcc.cmake |
| `tools/pioasm/` | pioasm 原始碼（`parser.yy` 是語法定義） | https://raw.githubusercontent.com/raspberrypi/pico-sdk/2.3.1/tools/pioasm/parser.yy |

其他工具倉庫：picotool https://github.com/raspberrypi/picotool 、debugprobe https://github.com/raspberrypi/debugprobe 。

---

## 7. pico-examples（「怎麼用」的官方範例）

- 倉庫：https://github.com/raspberrypi/pico-examples （branch `master`；對應 SDK 的 tag `sdk-2.3.1`）
- raw 前綴：`https://raw.githubusercontent.com/raspberrypi/pico-examples/master/`
- 下表路徑全部用 GitHub API 列出的 tree 確認存在，主要 .c / .pio 檔另以 raw 網址測得 200。

| 主題 | 資料夾 | 最有用的範例（檔案） |
|---|---|---|
| DMA | `dma/` | `hello_dma/hello_dma.c`（最小記憶體複製）、`channel_irq/channel_irq.c`（DMA 中斷重設 + PIO）、`control_blocks/control_blocks.c`（chaining / control block）、`sniff_crc/sniff_crc.c`（sniffer CRC） |
| PIO | `pio/` | `hello_pio/hello.pio` + `hello.c`（入門）、`ws2812/ws2812.pio`（side-set）、`logic_analyser/logic_analyser.c`（PIO + DMA 擷取）、`uart_dma/uart_dma.c`、`uart_tx/`、`uart_rx/`、`spi/spi.pio`、`i2c/i2c.pio`、`squarewave/`（wrap、直接寫指令記憶體）、`pwm/`、`addition/`、`quadrature_encoder/`、`clocked_input/`、`manchester_encoding/`、`differential_manchester/`、`onewire/` |
| 多核 | `multicore/` | `hello_multicore/multicore.c`、`multicore_fifo_irqs/`、`multicore_runner/`、`multicore_runner_queue/`（配 `queue_t`）、`multicore_doorbell/` |
| Interpolator | `interp/` | `hello_interp/hello_interp.c` |
| Timer | `timer/` | `hello_timer/`（alarm、repeating timer）、`timer_lowlevel/`（直接用暫存器）、`periodic_sampler/` |
| ADC | `adc/` | `hello_adc/`、`dma_capture/dma_capture.c`（ADC + DMA）、`onboard_temperature/`、`read_vsys/`、`microphone_adc/` |
| PWM | `pwm/` | `hello_pwm/`、`led_fade/`、`measure_duty_cycle/`（PWM 當計數器） |
| UART | `uart/` | `hello_uart/`、`uart_advanced/`（中斷、FIFO） |
| SPI | `spi/` | `spi_dma/spi_dma.c`、`spi_master_slave/`、`spi_flash/` |
| I2C | `i2c/` | `bus_scan/`（掃位址）、`slave_mem_i2c/` |
| GPIO | `gpio/` | `hello_gpio_irq/` |
| FreeRTOS | `freertos/` | `hello_freertos/hello_freertos.c`、`FreeRTOSConfig_examples_common.h`、`FreeRTOS_Kernel_import.cmake` |
| 系統 | `system/` | `narrow_io_write/`（§2.1.5 窄寫入行為）、`unique_board_id/`、`rand/`、`boot_info/` |
| Flash / XIP | `flash/` | `cache_perfctr/`（XIP cache 命中計數）、`xip_stream/`、`program/` |
| 時脈 | `clocks/` | `hello_48MHz/`、`hello_gpout/`、`detached_clk_peri/` |
| 其他 | `watchdog/`、`hello_world/`（`serial/`、`usb/`）、`hstx/`、`sha/`、`dcp/`、`usb/`、`universal/`、`pico_w/`、`low_power/`、`cmake/build_variants/` | — |

範例 raw 網址（已驗證）：
- https://raw.githubusercontent.com/raspberrypi/pico-examples/master/dma/channel_irq/channel_irq.c
- https://raw.githubusercontent.com/raspberrypi/pico-examples/master/dma/control_blocks/control_blocks.c
- https://raw.githubusercontent.com/raspberrypi/pico-examples/master/pio/logic_analyser/logic_analyser.c
- https://raw.githubusercontent.com/raspberrypi/pico-examples/master/pio/ws2812/ws2812.pio
- https://raw.githubusercontent.com/raspberrypi/pico-examples/master/multicore/multicore_runner_queue/multicore_runner_queue.c
- https://raw.githubusercontent.com/raspberrypi/pico-examples/master/adc/dma_capture/dma_capture.c

---

## 8. ROS 2 Jazzy

- docs.ros.org **沒有擋程式抓取**（2026-11-10 直接 curl 測得 200）。網址都由 ros2/ros2_documentation 的 `jazzy` 分支 `source/<路徑>.rst` 對應而來：`source/A/B.rst` → `https://docs.ros.org/en/jazzy/A/B.html`。
- 站內搜尋：https://docs.ros.org/en/jazzy/search.html （右上角搜尋框；不是 AI）。
- 文件原始碼（網站掛掉時的備援）：https://github.com/ros2/ros2_documentation/tree/jazzy/source ，例：https://raw.githubusercontent.com/ros2/ros2_documentation/jazzy/source/Concepts/Intermediate/About-Quality-of-Service-Settings.rst

### 8.1 概念頁（Concepts）

| 主題 | 網址 |
|---|---|
| Nodes | https://docs.ros.org/en/jazzy/Concepts/Basic/About-Nodes.html |
| Topics | https://docs.ros.org/en/jazzy/Concepts/Basic/About-Topics.html |
| Services / Actions / Parameters | https://docs.ros.org/en/jazzy/Concepts/Basic/About-Services.html 、 https://docs.ros.org/en/jazzy/Concepts/Basic/About-Actions.html 、 https://docs.ros.org/en/jazzy/Concepts/Basic/About-Parameters.html |
| Interfaces（msg/srv 型別） | https://docs.ros.org/en/jazzy/Concepts/Basic/About-Interfaces.html |
| Launch | https://docs.ros.org/en/jazzy/Concepts/Basic/About-Launch.html |
| Discovery | https://docs.ros.org/en/jazzy/Concepts/Basic/About-Discovery.html |
| CLI 工具總覽 | https://docs.ros.org/en/jazzy/Concepts/Basic/About-Command-Line-Tools.html |
| **QoS 設定**（reliability、durability、history、depth、相容表） | https://docs.ros.org/en/jazzy/Concepts/Intermediate/About-Quality-of-Service-Settings.html |
| **Executors**（SingleThreaded / MultiThreaded / callback group） | https://docs.ros.org/en/jazzy/Concepts/Intermediate/About-Executors.html |
| **Domain ID**（`ROS_DOMAIN_ID`、埠號計算器） | https://docs.ros.org/en/jazzy/Concepts/Intermediate/About-Domain-ID.html |
| Composition（多個 node 同一 process） | https://docs.ros.org/en/jazzy/Concepts/Intermediate/About-Composition.html |
| Logging | https://docs.ros.org/en/jazzy/Concepts/Intermediate/About-Logging.html |
| 不同 RMW 實作 | https://docs.ros.org/en/jazzy/Concepts/Intermediate/About-Different-Middleware-Vendors.html |
| Topic statistics | https://docs.ros.org/en/jazzy/Concepts/Intermediate/About-Topic-Statistics.html |

### 8.2 教學與 How-to

| 主題 | 網址 |
|---|---|
| CLI 教學總目錄 | https://docs.ros.org/en/jazzy/Tutorials/Beginner-CLI-Tools.html |
| 環境設定（source、`ROS_DOMAIN_ID`、`ROS_AUTOMATIC_DISCOVERY_RANGE`） | https://docs.ros.org/en/jazzy/Tutorials/Beginner-CLI-Tools/Configuring-ROS2-Environment.html |
| `ros2 node` | https://docs.ros.org/en/jazzy/Tutorials/Beginner-CLI-Tools/Understanding-ROS2-Nodes/Understanding-ROS2-Nodes.html |
| `ros2 topic`（echo / hz / info / pub） | https://docs.ros.org/en/jazzy/Tutorials/Beginner-CLI-Tools/Understanding-ROS2-Topics/Understanding-ROS2-Topics.html |
| `ros2 service` / `ros2 param` | https://docs.ros.org/en/jazzy/Tutorials/Beginner-CLI-Tools/Understanding-ROS2-Services/Understanding-ROS2-Services.html 、 https://docs.ros.org/en/jazzy/Tutorials/Beginner-CLI-Tools/Understanding-ROS2-Parameters/Understanding-ROS2-Parameters.html |
| `ros2 bag` | https://docs.ros.org/en/jazzy/Tutorials/Beginner-CLI-Tools/Recording-And-Playing-Back-Data/Recording-And-Playing-Back-Data.html |
| Client library 教學總目錄 | https://docs.ros.org/en/jazzy/Tutorials/Beginner-Client-Libraries.html |
| **colcon**（build、`--packages-select`、`--symlink-install`） | https://docs.ros.org/en/jazzy/Tutorials/Beginner-Client-Libraries/Colcon-Tutorial.html |
| 建 workspace / 建 package | https://docs.ros.org/en/jazzy/Tutorials/Beginner-Client-Libraries/Creating-A-Workspace/Creating-A-Workspace.html 、 https://docs.ros.org/en/jazzy/Tutorials/Beginner-Client-Libraries/Creating-Your-First-ROS2-Package.html |
| rclpy pub/sub | https://docs.ros.org/en/jazzy/Tutorials/Beginner-Client-Libraries/Writing-A-Simple-Py-Publisher-And-Subscriber.html |
| rclcpp pub/sub | https://docs.ros.org/en/jazzy/Tutorials/Beginner-Client-Libraries/Writing-A-Simple-Cpp-Publisher-And-Subscriber.html |
| rclpy service/client | https://docs.ros.org/en/jazzy/Tutorials/Beginner-Client-Libraries/Writing-A-Simple-Py-Service-And-Client.html |
| 自訂 msg/srv | https://docs.ros.org/en/jazzy/Tutorials/Beginner-Client-Libraries/Custom-ROS2-Interfaces.html |
| rclpy 參數 | https://docs.ros.org/en/jazzy/Tutorials/Beginner-Client-Libraries/Using-Parameters-In-A-Class-Python.html |
| ros2doctor | https://docs.ros.org/en/jazzy/Tutorials/Beginner-Client-Libraries/Getting-Started-With-Ros2doctor.html |
| Launch 教學總目錄 / 建 launch 檔 / substitutions | https://docs.ros.org/en/jazzy/Tutorials/Intermediate/Launch/Launch-Main.html 、 https://docs.ros.org/en/jazzy/Tutorials/Intermediate/Launch/Creating-Launch-Files.html 、 https://docs.ros.org/en/jazzy/Tutorials/Intermediate/Launch/Using-Substitutions.html |
| Launch 檔 Python / XML / YAML 對照 | https://docs.ros.org/en/jazzy/How-To-Guides/Launch-file-different-formats.html |
| **Callback groups**（MultiThreadedExecutor 搭配） | https://docs.ros.org/en/jazzy/How-To-Guides/Using-callback-groups.html |
| Node 參數（`--ros-args -p`、remap） | https://docs.ros.org/en/jazzy/How-To-Guides/Node-arguments.html |
| Zero-copy loaned messages | https://docs.ros.org/en/jazzy/How-To-Guides/Configure-ZeroCopy-loaned-messages.html |
| 開發 package（ament_python / ament_cmake） | https://docs.ros.org/en/jazzy/How-To-Guides/Developing-a-ROS-2-Package.html |
| **Intra-process communication** demo | https://docs.ros.org/en/jazzy/Tutorials/Demos/Intra-Process-Communication.html |
| QoS demo | https://docs.ros.org/en/jazzy/Tutorials/Demos/Quality-of-Service.html |
| Real-time programming demo | https://docs.ros.org/en/jazzy/Tutorials/Demos/Real-Time-Programming.html |
| Action server/client（Python） | https://docs.ros.org/en/jazzy/Tutorials/Intermediate/Writing-an-Action-Server-Client/Py.html |
| Jazzy release notes | https://docs.ros.org/en/jazzy/Releases/Release-Jazzy-Jalisco.html |

### 8.3 API 文件

| 套件 | 網址 |
|---|---|
| rclpy 入口 | https://docs.ros.org/en/jazzy/p/rclpy/ |
| rclpy Node | https://docs.ros.org/en/jazzy/p/rclpy/api/node.html |
| rclpy Topics（Publisher / Subscription） | https://docs.ros.org/en/jazzy/p/rclpy/api/topics.html |
| rclpy QoS | https://docs.ros.org/en/jazzy/p/rclpy/api/qos.html |
| rclpy Execution and Callbacks（executor、callback group） | https://docs.ros.org/en/jazzy/p/rclpy/api/execution_and_callbacks.html |
| rclpy Timers / Services / Parameters | https://docs.ros.org/en/jazzy/p/rclpy/api/timers.html 、 https://docs.ros.org/en/jazzy/p/rclpy/api/services.html 、 https://docs.ros.org/en/jazzy/p/rclpy/api/parameters.html |
| rclpy 模組頁（executors / callback_groups） | https://docs.ros.org/en/jazzy/p/rclpy/rclpy.executors.html 、 https://docs.ros.org/en/jazzy/p/rclpy/rclpy.callback_groups.html |
| rclcpp 入口 / 生成的類別索引 | https://docs.ros.org/en/jazzy/p/rclcpp/ 、 https://docs.ros.org/en/jazzy/p/rclcpp/generated/index.html |
| rclcpp::Node / rclcpp::QoS | https://docs.ros.org/en/jazzy/p/rclcpp/generated/classrclcpp_1_1Node.html 、 https://docs.ros.org/en/jazzy/p/rclcpp/generated/classrclcpp_1_1QoS.html |
| rclcpp executors | https://docs.ros.org/en/jazzy/p/rclcpp/generated/classrclcpp_1_1executors_1_1MultiThreadedExecutor.html 、 https://docs.ros.org/en/jazzy/p/rclcpp/generated/classrclcpp_1_1executors_1_1SingleThreadedExecutor.html |
| std_msgs / sensor_msgs / rmw | https://docs.ros.org/en/jazzy/p/std_msgs/ 、 https://docs.ros.org/en/jazzy/p/sensor_msgs/ 、 https://docs.ros.org/en/jazzy/p/rmw/ |
| 套件索引 | https://index.ros.org/ （例 https://index.ros.org/p/rclpy/） |
| colcon 官方文件 | https://colcon.readthedocs.io/en/released/ （verb：https://colcon.readthedocs.io/en/released/reference/verb/build.html 、 https://colcon.readthedocs.io/en/released/reference/verb/test.html） |

### 8.4 GitHub 原始碼（分支 `jazzy`；raw 前綴 `https://raw.githubusercontent.com/ros2/<repo>/jazzy/`）

| repo | 最有用的檔案（皆已驗證 200） | 為什麼 |
|---|---|---|
| ros2/ros2cli | `ros2topic/ros2topic/verb/hz.py`、`echo.py`、`pub.py`、`info.py`、`bw.py`、`delay.py`；`ros2node/ros2node/verb/info.py`；`ros2param/ros2param/verb/set.py`；`ros2doctor/ros2doctor/verb/hello.py` | CLI 參數與實際行為（例：`hz` 怎麼算、`echo` 預設 QoS） |
| ros2/rclpy | `rclpy/rclpy/executors.py`、`node.py`、`qos.py`、`callback_groups.py`、`timer.py`、`publisher.py`、`subscription.py`、`task.py` | executor 排程、QoS 預設值、`create_subscription` 簽名 |
| ros2/rclcpp | `rclcpp/include/rclcpp/qos.hpp`、`node.hpp`、`node_options.hpp`（`use_intra_process_comms`）、`executor.hpp`、`executors/multi_threaded_executor.hpp`、`executors/single_threaded_executor.hpp`、`callback_group.hpp`、`intra_process_setting.hpp`、`loaned_message.hpp` | C++ API 簽名 + 註解 |
| ros2/rmw | `rmw/include/rmw/qos_profiles.h`、`rmw/include/rmw/types.h` | **QoS 預設 profile 的真正數值**（sensor data、services default…） |
| ros2/rosidl_python | `rosidl_generator_py/resource/_msg.py.em` | Python msg 類別如何產生（欄位檢查成本） |
| ros2/common_interfaces | `std_msgs/msg/Header.msg`、`String.msg`；`sensor_msgs/msg/Imu.msg`、`PointCloud2.msg`；`geometry_msgs/msg/Twist.msg` | 訊息欄位定義 |
| ros2/launch_ros | `launch_ros/launch_ros/actions/node.py` | `Node(...)` 參數 |
| ros2/examples | https://github.com/ros2/examples/tree/jazzy | 官方最小範例 |

範例：
- https://raw.githubusercontent.com/ros2/rmw/jazzy/rmw/include/rmw/qos_profiles.h
- https://raw.githubusercontent.com/ros2/rclpy/jazzy/rclpy/rclpy/executors.py
- https://raw.githubusercontent.com/ros2/ros2cli/jazzy/ros2topic/ros2topic/verb/hz.py

### 8.5 REP 與設計文件

| 文件 | 網址 | 內容 |
|---|---|---|
| REP 2001 | https://www.ros.org/reps/rep-2001.html | ROS 2 variants（ros_core / ros_base / desktop 包含哪些套件） |
| REP 2000 | https://www.ros.org/reps/rep-2000.html | 各發行版支援平台（Jazzy → Ubuntu 24.04） |
| REP 103 / REP 105 | https://www.ros.org/reps/rep-0103.html 、 https://www.ros.org/reps/rep-0105.html | 單位與座標系慣例 / 座標框架 |
| design.ros2.org | https://design.ros2.org/ | 設計文件入口 |
| QoS 設計 | https://design.ros2.org/articles/qos.html | QoS 原理 |
| Intra-process 設計 | https://design.ros2.org/articles/intraprocess_communications.html | 零拷貝條件 |
| Node lifecycle | https://design.ros2.org/articles/node_lifecycle.html | managed node 狀態機 |

---

## 9. 其他參考文件

### 9.1 RISC-V / Hazard3

| 文件 | 網址 | 備註 |
|---|---|---|
| RISC-V 已批准規格入口 | https://riscv.org/specifications/ratified/ | 連到 docs.riscv.org |
| RISC-V ISA 手冊（線上 HTML，批准版 v20260120） | https://docs.riscv.org/reference/isa/v20260120/index.html | 章節頁：`unpriv/rv32.html`（RV32I）、`unpriv/m-st-ext.html`、`unpriv/a-st-ext.html`、`unpriv/b-st-ext.html`（Zba/Zbb/Zbs）、`unpriv/c-st-ext.html`、`unpriv/zc.html`（Zcb/Zcmp）、`unpriv/zicsr.html`、`priv/machine.html`（M-mode CSR）、`priv/priv-csrs.html`；前綴皆為 `https://docs.riscv.org/reference/isa/v20260120/` |
| RISC-V ISA 手冊 GitHub | https://github.com/riscv/riscv-isa-manual 、 https://github.com/riscv/riscv-isa-manual/releases | releases 是**每日建置快照**（如 `riscv-isa-release-d50ad50-2026-11-10`，附 `riscv-spec.pdf`），不是批准版；要引用以 docs.riscv.org 版本為準 |
| RISC-V psABI（呼叫慣例） | https://github.com/riscv-non-isa/riscv-elf-psabi-doc （`riscv-cc.adoc`） | a0–a7 / s0–s11 / caller-saved |
| RISC-V 組語手冊 | https://github.com/riscv-non-isa/riscv-asm-manual | 偽指令 |
| Hazard3 倉庫 | https://github.com/Wren6991/Hazard3 （最新 release `v1.1.1`） | |
| Hazard3 文件原始碼 | https://github.com/Wren6991/Hazard3/tree/stable/doc （`doc/sections/instruction_timings.adoc`、`csr.adoc`、`custom_extensions.adoc`） | raw：https://raw.githubusercontent.com/Wren6991/Hazard3/stable/doc/sections/csr.adoc |
| Hazard3 文件 PDF | https://github.com/Wren6991/Hazard3/releases/download/v1.1.1/hazard3.pdf | |
| 優先順序 | RP2350 datasheet §3.8 > Hazard3 文件 > RISC-V 規格 | datasheet 描述的是 RP2350 實際的設定 |

### 9.2 Arm Cortex-M33

| 文件 | 網址 | 備註 |
|---|---|---|
| Cortex-M33 TRM | https://developer.arm.com/documentation/100230/latest/ | 程式抓取得到 403；用瀏覽器實測可開（會轉到 support.arm.com/documentation/100230/latest/） |
| Cortex-M33 Devices Generic User Guide | https://developer.arm.com/documentation/100235/latest/ | 同上（瀏覽器實測可開）；指令說明、NVIC、SysTick |
| Armv8-M Architecture Reference Manual | https://developer.arm.com/documentation/ddi0553/latest/ | 同上（瀏覽器實測可開） |
| AAPCS32（呼叫慣例） | https://github.com/ARM-software/abi-aa/blob/main/aapcs32/aapcs32.rst | raw：https://raw.githubusercontent.com/ARM-software/abi-aa/main/aapcs32/aapcs32.rst |
| CMSIS 6 | https://github.com/ARM-software/CMSIS_6 、 https://arm-software.github.io/CMSIS_6/latest/Core/index.html | `__DSB`、`DWT` 等巨集 |
| 優先順序 | 週期數以 RP2350 datasheet §3.7.4.9 為準 | Arm TRM 不含 RP2350 的匯流排 / SRAM 時序 |

### 9.3 GCC / 工具鏈

| 主題 | 網址 |
|---|---|
| 最佳化選項（`-O2`、`-funroll-loops`…） | https://gcc.gnu.org/onlinedocs/gcc/Optimize-Options.html |
| inline asm（Extended Asm） | https://gcc.gnu.org/onlinedocs/gcc/Extended-Asm.html |
| asm 約束（Machine Constraints，含 ARM / RISC-V） | https://gcc.gnu.org/onlinedocs/gcc/Machine-Constraints.html |
| RISC-V 選項（`-march`、`-mabi`） | https://gcc.gnu.org/onlinedocs/gcc/RISC-V-Options.html |
| ARM 選項（`-mcpu=cortex-m33`） | https://gcc.gnu.org/onlinedocs/gcc/ARM-Options.html |
| 內建函式（`__builtin_expect`、`__builtin_clz`） | https://gcc.gnu.org/onlinedocs/gcc/Other-Builtins.html |
| `__atomic` 內建 | https://gcc.gnu.org/onlinedocs/gcc/_005f_005fatomic-Builtins.html |
| 函式屬性（`section`、`noinline`、`always_inline`） | https://gcc.gnu.org/onlinedocs/gcc/Common-Function-Attributes.html |
| 警告選項 | https://gcc.gnu.org/onlinedocs/gcc/Warning-Options.html |
| Instrumentation（`-pg`、sanitizer） | https://gcc.gnu.org/onlinedocs/gcc/Instrumentation-Options.html |
| GNU ld | https://sourceware.org/binutils/docs/ld/ |
| CMake | https://cmake.org/cmake/help/latest/ |

### 9.4 Linux / C / C++

| 主題 | 網址 |
|---|---|
| pthreads 總覽 | https://man7.org/linux/man-pages/man7/pthreads.7.html |
| pthread_create | https://man7.org/linux/man-pages/man3/pthread_create.3.html |
| pthread_mutex_lock / pthread_cond_wait（POSIX 版） | https://man7.org/linux/man-pages/man3/pthread_mutex_lock.3p.html 、 https://man7.org/linux/man-pages/man3/pthread_cond_wait.3p.html |
| clock_gettime | https://man7.org/linux/man-pages/man2/clock_gettime.2.html |
| termios（序列埠設定） | https://man7.org/linux/man-pages/man3/termios.3.html |
| sched_setaffinity / taskset | https://man7.org/linux/man-pages/man2/sched_setaffinity.2.html 、 https://man7.org/linux/man-pages/man1/taskset.1.html |
| mmap / epoll | https://man7.org/linux/man-pages/man2/mmap.2.html 、 https://man7.org/linux/man-pages/man7/epoll.7.html |
| perf stat / perf record | https://man7.org/linux/man-pages/man1/perf-stat.1.html 、 https://man7.org/linux/man-pages/man1/perf-record.1.html |
| time(1) | https://man7.org/linux/man-pages/man1/time.1.html |
| cppreference 首頁 | https://en.cppreference.com/w/ |
| C atomics / C++ memory_order / C++ thread | https://en.cppreference.com/w/c/atomic 、 https://en.cppreference.com/w/cpp/atomic/memory_order 、 https://en.cppreference.com/w/cpp/thread |
| C 運算子優先序 | https://en.cppreference.com/w/c/language/operator_precedence |

### 9.5 OpenMP / 平行

| 文件 | 網址 |
|---|---|
| OpenMP 規格 | https://www.openmp.org/specifications/ |
| OpenMP 參考卡頁面 | https://www.openmp.org/resources/refguides/ |
| OpenMP 5.2 Reference Guide（PDF） | https://www.openmp.org/wp-content/uploads/OpenMPRefGuide-5.2-Web-2024.pdf |
| OpenMP 6.0 Reference Guide（PDF） | https://www.openmp.org/wp-content/uploads/OpenMP-RefGuide-6.0-OMP60SC24-web.pdf |

### 9.6 FreeRTOS

| 文件 | 網址 |
|---|---|
| 首頁 | https://www.freertos.org/ |
| SMP 介紹（雙核、core affinity） | https://www.freertos.org/Documentation/02-Kernel/02-Kernel-features/13-Symmetric-multiprocessing-introduction |
| FreeRTOSConfig.h 說明 | https://www.freertos.org/Documentation/02-Kernel/03-Supported-devices/02-Customization |
| xTaskCreate | https://www.freertos.org/Documentation/02-Kernel/04-API-references/01-Task-creation/01-xTaskCreate |
| Queue API | https://www.freertos.org/Documentation/02-Kernel/04-API-references/06-Queues/00-QueueManagement |
| Task notifications API | https://www.freertos.org/Documentation/02-Kernel/04-API-references/05-Direct-to-task-notifications/00-RTOS-task-notifications |
| Semaphore / Mutex API | https://www.freertos.org/Documentation/02-Kernel/04-API-references/10-Semaphore-and-Mutexes/00-Semaphores |
| Deferred interrupt handling | https://www.freertos.org/Documentation/02-Kernel/02-Kernel-features/11-Deferred-interrupt-handling |
| FreeRTOS-Kernel（最新 `V11.3.3`） | https://github.com/FreeRTOS/FreeRTOS-Kernel （標頭：https://raw.githubusercontent.com/FreeRTOS/FreeRTOS-Kernel/main/include/task.h 、 https://raw.githubusercontent.com/FreeRTOS/FreeRTOS-Kernel/main/include/queue.h） |
| RP2350 port（上游 Community-Supported-Ports） | https://github.com/FreeRTOS/FreeRTOS-Kernel-Community-Supported-Ports/tree/main/GCC/RP2350_ARM_NTZ 、 https://github.com/FreeRTOS/FreeRTOS-Kernel-Community-Supported-Ports/tree/main/GCC/RP2350_RISC-V |
| RP2350 port（Raspberry Pi fork） | https://github.com/raspberrypi/FreeRTOS-Kernel （`portable/ThirdParty/GCC/RP2350_ARM_NTZ`、`portable/ThirdParty/GCC/RP2350_RISC-V`；RP2040 port 在 `portable/ThirdParty/GCC/RP2040`） |
| 路徑怎麼選 | pico-examples 的 `freertos/FreeRTOS_Kernel_import.cmake` 會依 `PICO_PLATFORM` 選 `RP2350_RISC-V` 或 `RP2350_ARM_NTZ`，並支援 `portable/ThirdParty/Community-Supported-Ports/GCC` 與 `portable/ThirdParty/GCC` 兩種位置 |

### 9.7 主機端（Python / 序列埠 / CRC / GitLab / git）

| 文件 | 網址 |
|---|---|
| pySerial 首頁 / API / 工具（`miniterm`、`list_ports`） | https://pyserial.readthedocs.io/en/latest/ 、 https://pyserial.readthedocs.io/en/latest/pyserial_api.html 、 https://pyserial.readthedocs.io/en/latest/tools.html |
| Python 文件首頁 | https://docs.python.org/3/ |
| profile / cProfile（同一頁） | https://docs.python.org/3/library/profile.html |
| timeit / struct / time | https://docs.python.org/3/library/timeit.html 、 https://docs.python.org/3/library/struct.html 、 https://docs.python.org/3/library/time.html |
| threading / multiprocessing / asyncio / collections | https://docs.python.org/3/library/threading.html 、 https://docs.python.org/3/library/multiprocessing.html 、 https://docs.python.org/3/library/asyncio.html 、 https://docs.python.org/3/library/collections.html |
| NumPy | https://numpy.org/doc/stable/ 、 https://numpy.org/doc/stable/reference/index.html |
| CRC 參數目錄（RevEng） | https://reveng.sourceforge.io/crc-catalogue/all.htm （程式抓取得 403；瀏覽器實測可開，頁內有 `CRC-32/ISO-HDLC`、`CRC-16/IBM-3740` 等） |
| GitLab CI 總覽 / `.gitlab-ci.yml` 語法 | https://docs.gitlab.com/ci/ 、 https://docs.gitlab.com/ci/yaml/ |
| GitLab 預設變數 / artifacts / pipelines / caching / workflow / runners | https://docs.gitlab.com/ci/variables/predefined_variables/ 、 https://docs.gitlab.com/ci/jobs/job_artifacts/ 、 https://docs.gitlab.com/ci/pipelines/ 、 https://docs.gitlab.com/ci/caching/ 、 https://docs.gitlab.com/ci/yaml/workflow/ 、 https://docs.gitlab.com/ci/runners/ |
| git 指令參考 / Pro Git / bisect / reflog | https://git-scm.com/docs 、 https://git-scm.com/book/en/v2 、 https://git-scm.com/docs/git-bisect 、 https://git-scm.com/docs/git-reflog |
| Docker CLI | https://docs.docker.com/reference/cli/docker/ |

---

## 10. 沒有 AI 摘要的搜尋策略

### 10.1 優先順序

1. **書籤**（第 13 節做好）。
2. **站內搜尋**：
   - docs.ros.org：https://docs.ros.org/en/jazzy/search.html
   - raspberrypi.com 文件：頁面上方的搜尋框，或直接在 API 頁 Ctrl+F。
   - GitHub：倉庫內按 `t` 找檔名；搜尋框 `repo:raspberrypi/pico-sdk <關鍵字>`。
   - PDF：Ctrl+F。
3. **一般搜尋引擎**，而且一定要用不帶 AI 的模式（下面）。

### 10.2 Google：用「網頁」篩選（`udm=14`）

- 在網址加上 `udm=14` 會進入 Google 的「網頁（Web）」篩選，只有文字連結結果，不顯示 AI 摘要（AI Overviews）。格式：
  - `https://www.google.com/search?q=rp2350+datasheet+DREQ&udm=14`
- 或者：正常搜尋後，在結果上方的分頁列點「網頁」/「Web」（可能藏在「更多」裡）。
- 注意：Google 沒有正式承諾 `udm=14` 永久有效；若頁面仍出現 AI 摘要，**不要點它、不要看它**，往下捲到連結結果。也不要點「AI 模式」分頁。
- 來源（2026-11-10 搜尋確認）：Android Central「This simple Google Search trick…」、Proton blog「How to turn off Google AI」、9to5Google 報導等，皆描述 `&udm=14` = Web 篩選、無 AI Overviews。
- 有用的 `site:` 查詢（都加 `&udm=14`）：
  - `site:datasheets.raspberrypi.com rp2350`
  - `site:raspberrypi.com/documentation/pico-sdk dma_channel_configure`
  - `site:github.com/raspberrypi/pico-sdk sm_config_set_out_shift`
  - `site:github.com/raspberrypi/pico-examples pio dma`
  - `site:docs.ros.org/en/jazzy executor callback group`
  - `site:man7.org clock_gettime`
  - `site:forums.raspberrypi.com rp2350 dma chain`（論壇非官方，只當線索；論壇用程式抓會 403，瀏覽器可開 ⚠️未在瀏覽器實測）
  - `site:docs.gitlab.com ci rules`

### 10.3 Bing：避免

- Bing 搜尋結果頁會嵌 Copilot 的 AI 回答，屬於禁止的「搜尋引擎 AI 摘要」。考場**不要用 Bing**（Edge 瀏覽器網址列預設常是 Bing，請改用 Google `udm=14` 或直接開書籤）。

### 10.4 DuckDuckGo

- 用 **https://noai.duckduckgo.com/**：DuckDuckGo 提供的無 AI 版本，自動關閉 Search Assist 等 AI 功能（已測 200）。
- 或在 duckduckgo.com：Search Settings → AI Features → Search Assist 選「Never」→ Save and Exit（依 DuckDuckGo 官方說明頁 https://duckduckgo.com/duckduckgo-help-pages/ai-features/opting-out-of-ai）。
- 不要點 Duck.ai。

### 10.5 一律禁止

- 不要點任何 AI 回答框、「Ask AI」、「Copilot」、「AI 模式」、「Summarize」按鈕。
- 不要開 Gmail、LINE、Discord。
- 不要用 GitHub Copilot、Copilot Chat、github.dev。

---

## 11. 怎麼切一段可以貼的原文

### 11.1 原則

- **一次只貼一段，≤ 約 1200 字元**（考場模型的單次貼上長度有限）。
- **一定附上出處**：文件名 + 節號 + 節名（或檔案路徑 + 函式名）。小模型看到「官方文件」會比較願意相信它。
- 明說「以這段為準，若與你記憶不同以這段為準」。小模型常把 RP2350 當成 RP2040。
- 問題寫在原文**後面**，一次只問一件事。

### 11.2 從 PDF（datasheet）複製

- PDF 文字複製常見問題：換行被切斷、表格欄位變成一長串、連字號消失、上下標亂掉、頁首頁尾（`RP2350 Datasheet`、頁碼）混進去。
- 做法：
  1. 只選取需要的段落（不要整頁）。
  2. 貼到雲端筆記或文字編輯器，刪掉頁首頁尾、把斷行接回來。
  3. 表格：只留需要的幾列，自己改寫成 `欄位 = 值` 一行一個（例：`DREQ 0 = DREQ_PIO0_TX0`）。
  4. 告訴模型「這是 datasheet 摘錄，表格可能被打散」。
- 暫存器位元表：只留「Bits / Name / Description / Type / Reset」需要的那幾列。

### 11.3 從 GitHub 標頭檔複製

- 開 raw 網址 → Ctrl+F 函式名 → 從 `/*!` 或 `/**` 註解開頭選到函式宣告結尾（`;` 或 inline 實作的 `}`）。
- 只複製那一個函式（或一個 struct / enum）。不要貼整個檔案。
- 附上路徑，例如 `pico-sdk 2.3.1 src/rp2_common/hardware_dma/include/hardware/dma.h`。

### 11.4 從網頁（docs.ros.org、API 頁）複製

- 只選內文，避開側欄和「Edit on GitHub」等。
- 程式碼區塊用頁面的複製按鈕（若有），比手動選取乾淨。

### 11.5 貼上範本

```
以下摘自 RP2350 datasheet §12.6.4.1 System DREQ table（官方文件，Release 8，2026-10-01）。
晶片是 RP2350（Raspberry Pi Pico 2），不是 RP2040。若與你的記憶不同，以這段為準。
＜原文開始＞
<貼上原文>
＜原文結束＞
問題：<一句話的問題>
```

```
以下摘自 pico-sdk 2.3.1 原始碼 src/rp2_common/hardware_pio/include/hardware/pio.h（官方標頭檔，含註解）。
＜原文開始＞
<貼上函式註解 + 宣告>
＜原文結束＞
問題：我想讓 SM 每 32 bit 自動 pull，參數要怎麼填？只回答參數與一行說明。
```

```
以下摘自 ROS 2 Jazzy 官方文件 docs.ros.org/en/jazzy Concepts/Intermediate/About-Executors（官方）。
＜原文開始＞
<貼上原文>
＜原文結束＞
問題：……
```

---

## 12. 驗證紀錄（2026-11-10）

- RP2350 datasheet：下載當前 PDF，`pdfinfo` 1371 頁；`pdftotext -layout` 抽出目錄與內文標題；本檔所有節號取自實際目錄（前 3 層）或內文標題（第 4–5 層，且頁碼落在上層節範圍內）。第 3 節每個 Ctrl+F 關鍵字都以程式在該節頁碼範圍內搜尋確認。
- 其他 Raspberry Pi PDF：全部下載並讀取版本字串與目錄。
- 一般網址：`curl -sSL -o /dev/null -w '%{http_code}'` 逐一測試，得 200。
- 程式抓取被擋但瀏覽器可開（403 為 Cloudflare 或防爬蟲）：`raspberrypi.com/documentation/*`（含 pico-sdk API 頁，錨點以瀏覽器 DOM 確認）、`developer.arm.com`（Arm 文件，轉到 support.arm.com）、`reveng.sourceforge.io`。
- GitHub 路徑：以 GitHub API 取得 pico-sdk（`2.3.1` 與 `master`）、pico-examples（`master`）、ros2 各 repo（`jazzy`）的完整 tree 比對，再以 raw 網址測 200。
- ⚠️未驗證：GitHub code search 是否一定要登入；`forums.raspberrypi.com`（程式抓取 403，未在瀏覽器測）。

---

## 13. 考前要做（清單）

- [ ] 在自己的瀏覽器帳號（Chrome / Firefox 同步）建一個書籤資料夾「exam-docs」，至少放：
  - RP2350 datasheet PDF、Pico 2 datasheet、C/C++ SDK PDF、Getting started PDF
  - pico-sdk API：hardware.html、high_level.html、runtime.html
  - GitHub：pico-sdk（tag 2.3.1）、`src/rp2_common`、`src/rp2350/hardware_regs/include/hardware/regs`、pico-examples
  - 常用 raw 標頭：dma.h、pio.h、gpio.h、irq.h、sync.h、multicore.h、time.h、queue.h
  - docs.ros.org/en/jazzy：QoS、Executors、Domain ID、Topics 教學、colcon、Launch
  - rclpy API 入口、rmw `qos_profiles.h`
  - Google `udm=14` 範例網址、noai.duckduckgo.com
- [ ] 備援：把同一份連結清單放在自己 GitHub 倉庫的 README（或雲端筆記），考場電腦登入後一鍵打開。
- [ ] 在家用**一般瀏覽器**逐一點過，確認每個都能載入（特別是 raspberrypi.com 的 Cloudflare 驗證頁會不會卡住）。
- [ ] 練習三次：「找到 datasheet 某節 → 複製 → 清理 → 套範本 → 貼上」，計時，目標 2 分鐘內。
- [ ] 練習在 PDF 用 Ctrl+F 搜 `12.6.4.1. System`、`Table 1254`、`RP2350-E5`。
- [ ] 把 `lite/08-docs-map.md` 印出來（或存成手機截圖以外的紙本），考場網路慢時照著打網址。
- [ ] 考試當天打開 datasheet 第一件事：看 Colophon 的 Release / Build date。若不是 Release 8，節號以目錄為準、頁碼不要信。
