# RP2350 週邊（GPIO / UART / SPI / I2C / PWM / ADC / Timer / IRQ）與 pico-sdk

- 用途：**備援包**。考前 demo 沒有提到這些週邊；萬一考題要求「讀 datasheet 某週邊章節 → 用 pico-sdk 寫出 / 優化驅動程式」時使用。給考場 LLM 當 context，也給考生直接查。內容：GPIO 功能選擇與 pad、UART、SPI、I2C、PWM、ADC、Timer / alarm / watchdog、中斷深入、HSTX / TRNG / SHA-256 簡介、每個週邊的效能取捨（polling / IRQ / DMA）、讀新週邊章節的方法、症狀 → 原因對照表。
- 適用版本：RP2350（Pico 2 = RP2350A，QFN-60）；pico-sdk 2.x（查證時為 GitHub master，commit 079c6f3，2026-09）。與 RP2040 不同處標「RP2040：」。
- 來源（實際查閱）：
  - RP2350 Datasheet（build 01/10/2026）：https://datasheets.raspberrypi.com/rp2350/rp2350-datasheet.pdf — §2.1.5、§3.2、§3.8.6.1、§9.1–9.9、§12.1–12.5、§12.8、§12.9、§12.11–12.13、§12.15.2、Appendix A、Appendix D（D.5.1 RP2350-E9）
  - pico-sdk 原始碼：https://github.com/raspberrypi/pico-sdk — `src/rp2_common/hardware_{gpio,uart,spi,i2c,pwm,adc,timer,watchdog,irq,sha256}/`（.h 與 .c）、`pico_time/include/pico/time.h`、`pico_rand/include/pico/rand.h`、`pico_i2c_slave/include/pico/i2c_slave.h`、`pico_runtime_init/runtime_init_clocks.c`、`hardware_clocks/clocks.c`、`src/rp2350/hardware_regs/include/hardware/{platform_defs.h,regs/intctrl.h}`、`src/rp2350/hardware_structs/include/hardware/structs/io_bank0.h`、`pico_stdlib/CMakeLists.txt`、`pico_crt0/crt0_riscv.S`
  - pico-examples：https://github.com/raspberrypi/pico-examples — `i2c/bus_scan`、`i2c/slave_mem_i2c`、`uart/uart_advanced`、`spi/spi_dma`、`adc/dma_capture`、`adc/onboard_temperature`、`pwm/led_fade`、`pwm/measure_duty_cycle`
- 相關檔案（不重複的內容請去那邊看）：`pico-sdk.md`（晶片總覽、CMake、GPIO 基本 API、時間 API、時脈、量測方法）、`pico-dma.md`（DMA 全部細節、DREQ 表）、`pio.md`（自訂協定）、`multicore-sync.md`（ISR 共享變數、critical_section、queue_t）、`riscv-hazard3.md`、`../03-optimize.md`（通用優化流程）
- 最後更新：2026-11

---

## 0. 一分鐘總覽

| 週邊 | 數量（RP2350） | 時脈來源 | FIFO | 標頭 / CMake 函式庫 | 最大速率 |
|---|---|---|---|---|---|
| GPIO | A：30 支；B：48 支（Bank 0） | — | — | `hardware/gpio.h` / `hardware_gpio`（pico_stdlib 已含） | — |
| UART | 2（PL011） | `clk_peri`（預設 = clk_sys = 150 MHz） | TX 32×8、RX 32×12 | `hardware/uart.h` / `hardware_uart`（pico_stdlib 已含） | clk_peri/16 = 9.375 Mbaud |
| SPI | 2（PL022） | `clk_peri` | TX/RX 各 8 個（4–16 bit） | `hardware/spi.h` / `hardware_spi` | master：clk_peri/2；slave：clk_peri/12 |
| I2C | 2（DW_apb_i2c） | `clk_sys` | TX/RX 各 16 | `hardware/i2c.h` / `hardware_i2c` | 1 Mbit/s（Fast-mode Plus）；無 High-speed |
| PWM | 12 slice × 2 ch（A 封裝腳位只接到 slice 0–7） | `clk_sys` | — | `hardware/pwm.h` / `hardware_pwm` | 16-bit 計數、8.4 分頻 |
| ADC | 1（SAR），A：4 外部 + 溫度；B：8 + 溫度 | `clk_adc` 48 MHz | 8 筆 ⚠️未查證 | `hardware/adc.h` / `hardware_adc` | 500 kS/s，12-bit，ENOB 9.2 ⚠️未查證 |
| Timer | TIMER0、TIMER1，各 64-bit µs 計數 + 4 alarm | 1 µs tick（由 clk_ref/XOSC） | — | `hardware/timer.h`、`pico/time.h` | 1 µs 解析度 |
| Watchdog | 1 | 1 µs tick | — | `hardware/watchdog.h` / `hardware_watchdog` | 最長約 16.7 s（RP2040：8.3 s） |

最常犯的三個錯：
1. **沒有 `gpio_set_function(pin, GPIO_FUNC_xxx)`**（`uart_init` / `spi_init` / `i2c_init` 都**不會**幫你設腳位）。
2. **公式差一**：PWM 週期 = `TOP + 1`；ADC 取樣間隔 = `DIV + 1`；UART 一個 byte = 10 bit（8N1）。
3. **在 IRQ / alarm callback 裡 `printf` / `sleep_ms` / 長迴圈**。

---

## 1. GPIO 深入（datasheet §9）

基本 API（`gpio_init`、`gpio_put`、`gpio_set_dir`、mask 操作、`sio_hw`）已在 `pico-sdk.md` §7.2，這裡補功能選擇、pad 與中斷。

### 1.1 功能選擇（FUNCSEL，§9.4 Table 677）

每支 GPIO 同一時間只能選**一個**功能。`gpio_function_t`（RP2350，`structs/io_bank0.h`）：

| 值 | 巨集 | 說明 |
|---|---|---|
| 0 | `GPIO_FUNC_HSTX` | 只有 GPIO 12–19 |
| 1 | `GPIO_FUNC_SPI` | |
| 2 | `GPIO_FUNC_UART` | |
| 3 | `GPIO_FUNC_I2C` | |
| 4 | `GPIO_FUNC_PWM` | |
| 5 | `GPIO_FUNC_SIO` | CPU 軟體控制（`gpio_init` 會選這個） |
| 6 / 7 / 8 | `GPIO_FUNC_PIO0` / `PIO1` / `PIO2` | RP2040 沒有 PIO2 |
| 9 | `GPIO_FUNC_GPCK`（= `XIP_CS1` = `CORESIGHT_TRACE`） | 時脈輸入/輸出、QMI CS1、trace |
| 10 | `GPIO_FUNC_USB` | VBUS 偵測等 |
| 11 | `GPIO_FUNC_UART_AUX` | RP2350 新增：在 CTS/RTS 腳上當 TX/RX |
| 0x1f | `GPIO_FUNC_NULL` | 無功能（輸出高阻抗；reset 預設） |

Bank 0 腳位 → 週邊（只列 F1–F4 與規律；F5 SIO、F6–F8 PIO0/1/2 每支都有）：

| GPIO | F1 SPI | F2 UART | F3 I2C | F4 PWM |
|---|---|---|---|---|
| 0, 1, 2, 3 | SPI0 RX, CSn, SCK, TX | UART0 TX, RX, CTS, RTS | I2C0 SDA, I2C0 SCL, I2C1 SDA, I2C1 SCL | PWM0 A, 0 B, 1 A, 1 B |
| 4, 5, 6, 7 | SPI0 RX, CSn, SCK, TX | UART1 TX, RX, CTS, RTS | 同上規律（偶數 SDA、奇數 SCL；每 2 支交替 I2C0/I2C1） | PWM2 A … PWM3 B |
| 8–11 | SPI1 RX, CSn, SCK, TX | UART1 TX, RX, CTS, RTS | 〃 | PWM4 A … PWM5 B |
| 12–15 | SPI1 | UART0 | 〃 | PWM6 A … PWM7 B |
| 16–19 | SPI0 | UART0 | 〃 | PWM0 A … PWM1 B |
| 20–23 | SPI0 | UART1 | 〃 | PWM2 A … PWM3 B |
| 24–27 | SPI1 | UART1 | 〃 | PWM4 A … PWM5 B |
| 28, 29 | SPI1 RX, CSn | UART0 TX, RX | I2C0 SDA, SCL | PWM6 A, B |
| 30–47（只有 QFN-80） | 依同樣 4 支一組規律 | | | GPIO32–39 = PWM8–11，GPIO40–47 再重複一次 PWM8–11 |

速記規則（GPIO 0–29）：
- **I2C**：`gpio % 4` = 0/1 → I2C0 SDA/SCL；2/3 → I2C1 SDA/SCL。
- **UART**：每 4 支一組 TX, RX, CTS, RTS；組別 0–3 → UART0、4–11 → UART1、12–19 → UART0、20–27 → UART1、28–29 → UART0。
- **SPI**：每 4 支一組 RX, CSn, SCK, TX；0–7 → SPI0、8–15 → SPI1、16–23 → SPI0、24–29 → SPI1。
- **PWM**：`slice = (gpio >> 1) & 7`（GPIO < 32），`channel = gpio & 1`（0 = A、1 = B）。
- 有疑問一律查 datasheet Table 677，或用 SDK 的 `pwm_gpio_to_slice_num()`、`UART_FUNCSEL_NUM(uart, gpio)`。

規則（§9.4）：
- 同一個週邊**輸入**（例如 UART0 RX）只應接到一支 GPIO；接到多支時週邊看到的是它們的 **OR**。
- 同一個週邊**輸出**可以選在多支腳，每支都會出現相同訊號。
- **SIO 與 PIO 的輸入永遠連著**：不論 FUNCSEL 選什麼，`gpio_get()` / PIO `in pins` 都讀得到腳位狀態；要**輸出**才需要選對功能。
- **DMA 不能存取 SIO**（GPIO 暫存器）；要用 DMA 送資料到腳位 → PIO（`pio.md`）。

Pico 2 板子預設腳位（`boards/pico2.h`）：uart0 TX=GP0 / RX=GP1；i2c0 SDA=GP4 / SCL=GP5；spi0 RX=GP16 / CSn=GP17 / SCK=GP18 / TX=GP19；LED=GP25（= PWM4 B）；ADC0–2 = GP26–28，GP29 = VSYS/3（ADC3）。

### 1.2 Pad 控制（§9.6、PADS_BANK0 GPIOx 暫存器）

| 欄位 | Reset 值 | SDK 函式 |
|---|---|---|
| ISO（隔離閂鎖，RP2350 新增） | 1（隔離中） | `gpio_set_function()` / `gpio_init()` 會清掉 |
| OD（輸出停用） | 0 | `gpio_set_function()` 會清 0 |
| IE（輸入致能） | **0** | `gpio_set_function()` 會設 1；`gpio_set_input_enabled(gpio, bool)` |
| DRIVE | 1 = 4 mA | `gpio_set_drive_strength(gpio, GPIO_DRIVE_STRENGTH_2MA/4MA/8MA/12MA)` |
| PUE / PDE | PUE=0，**PDE=1（預設 pull-down）** | `gpio_pull_up`、`gpio_pull_down`、`gpio_disable_pulls`、`gpio_set_pulls(gpio, up, down)` |
| SCHMITT | 1（開） | `gpio_set_input_hysteresis_enabled(gpio, bool)` |
| SLEWFAST | 0（慢） | `gpio_set_slew_rate(gpio, GPIO_SLEW_RATE_SLOW/FAST)` |

- `gpio_set_function()` 只改 IE/OD/ISO 與 FUNCSEL，**不動 pull**。所以 `gpio_init()` 之後的輸入腳仍是 reset 的 **pull-down**。
- PUE 與 PDE 同時設 1 = **bus keeper**（弱保持目前邏輯準位）。
- 高速輸出（SPI > 數十 MHz、PIO 高速訊號）可考慮 `GPIO_SLEW_RATE_FAST` + 較大 drive；I2C 建議 slew 慢、Schmitt 開、pull-up 開（§12.2.1.3）。
- RP2350 reset 後 pad：輸出高阻抗、**輸入停用**、pull-down、**隔離**。RP2040 沒有 ISO、預設 IE=1。**自己直接寫 IO_BANK0 / PADS 暫存器時必須自己清 ISO、設 IE**，否則腳沒反應。
- 輸入同步器：每支 GPIO 進 SIO 與 PIO 前各有 2-flop 同步器（多 2 cycle 延遲）。可以 bypass（SIO：`SYSCFG.PROC_IN_SYNC_BYPASS`；PIO：`INPUT_SYNC_BYPASS` / SDK `pio_set_input_sync_bypass_with_mask()`），只在同步訊號且你確定時序時用，否則有 metastability 風險。

### 1.3 Erratum RP2350-E9（§9.6 Caution、Appendix D.5.1）

| 項目 | 內容 |
|---|---|
| 影響 | **RP2350 A2 stepping**（A4 已修正；A3 ⚠️未查證；Appendix C.2） |
| 現象 | Bank 0 GPIO 0–47 在「IE=1、輸出關閉、腳位電壓落在 VIL~VIH 之間」時漏電流異常（3.3 V 下典型約 120 µA），把腳撐在約 2.2 V。內建 **pull-down 太弱拉不下來** → 浮接 + pull-down 的腳可能讀到 1 |
| 不受影響 | pull-up 正常；QSPI pad、USB pin 不受影響 |
| 對策 | 1) 改用 pull-up + 按鍵接地（低電位有效）；2) 外接 ≤ 8.2 kΩ pull-down；3) 平時關 IE（`gpio_set_input_enabled(pin,false)`），讀之前開、讀完關 |
| 查 stepping | `rp2350_chip_version()`（`pico/platform.h`，回傳 `uint8_t`；SDK 註解：A2 回 2、A3/A4 回 3）⚠️未在板上驗證 |

### 1.4 GPIO 中斷（§9.5、`gpio.h`）

事件（`enum gpio_irq_level`，可 OR）：

| 巨集 | 值 | 行為 |
|---|---|---|
| `GPIO_IRQ_LEVEL_LOW` | 0x1 | 腳為 0 時**持續**觸發（不閂鎖） |
| `GPIO_IRQ_LEVEL_HIGH` | 0x2 | 腳為 1 時持續觸發（不閂鎖） |
| `GPIO_IRQ_EDGE_FALL` | 0x4 | 1→0，閂鎖在 INTR，需 acknowledge |
| `GPIO_IRQ_EDGE_RISE` | 0x8 | 0→1，閂鎖 |

```c
typedef void (*gpio_irq_callback_t)(uint gpio, uint32_t event_mask);
void gpio_set_irq_enabled_with_callback(uint gpio, uint32_t event_mask, bool enabled, gpio_irq_callback_t callback);
void gpio_set_irq_enabled(uint gpio, uint32_t event_mask, bool enabled);   // 之後再加其他腳
void gpio_set_irq_callback(gpio_irq_callback_t callback);                  // 每核只有一個
void gpio_acknowledge_irq(uint gpio, uint32_t event_mask);
void gpio_add_raw_irq_handler(uint gpio, irq_handler_t handler);           // 進階：自己的 handler（需自己 acknowledge）
void gpio_add_raw_irq_handler_masked(uint32_t gpio_mask, irq_handler_t handler);
```

- `gpio_set_irq_enabled_with_callback` = `gpio_set_irq_enabled` + `gpio_set_irq_callback` + `irq_set_enabled(IO_IRQ_BANK0, true)`。
- **每核一個共用 callback**，所有腳都進同一個函式，用 `gpio` 參數分辨。
- GPIO 中斷是 **per-core** 的：在哪顆核呼叫，就在哪顆核觸發（IO_IRQ_BANK0 是 core-local 中斷）。
- SDK 預設 handler 會先 acknowledge edge 事件再呼叫 callback。
- `gpio_set_irq_enabled()` 開啟時會先清掉該腳之前閂鎖的 edge 事件。

範例：按鍵（GP15 接地，用 pull-up 避開 E9）+ 軟體去彈跳，ISR 只計數，主迴圈處理：

```c
#include <stdio.h>
#include "pico/stdlib.h"
#define BTN 15
#define DEBOUNCE_US 20000u

static volatile uint32_t press_count;
static volatile uint32_t last_accept_us;

static void gpio_cb(uint gpio, uint32_t events) {
    if (gpio == BTN && (events & GPIO_IRQ_EDGE_FALL)) {
        uint32_t now = time_us_32();
        if (now - last_accept_us >= DEBOUNCE_US) {   // 無號減法：溢位也正確
            last_accept_us = now;
            press_count++;                            // 只有 ISR 寫，主程式只讀
        }
    }
}

int main(void) {
    stdio_init_all();
    gpio_init(BTN);
    gpio_set_dir(BTN, GPIO_IN);
    gpio_pull_up(BTN);
    gpio_set_irq_enabled_with_callback(BTN, GPIO_IRQ_EDGE_FALL, true, &gpio_cb);
    uint32_t seen = 0;
    while (true) {
        uint32_t c = press_count;
        if (c != seen) { seen = c; printf("press %lu\n", (unsigned long)c); }
        tight_loop_contents();
    }
}
```

另一種去彈跳：第一個 edge 進來就 `gpio_set_irq_enabled(BTN, ..., false)`，用 `add_alarm_in_ms(20, cb, ...)` 在 20 ms 後讀腳位並重新開中斷（比時間戳更穩，callback 都很短）。

---

## 2. UART（datasheet §12.1、`hardware/uart.h`）

### 2.1 硬體重點

- PL011，TX FIFO 32×8 bit；RX FIFO 32×12 bit（8 data + 4 個錯誤旗標：framing / parity / break / overrun）。
- 資料框：start bit + 5–8 data（LSB first）+ 可選 parity + 1 或 2 stop。
- 鮑率產生器：`BRD = UARTCLK / (16 × baud)`，整數部分寫 IBRD（16 bit），小數部分 ×64 寫 FBRD（6 bit）。最大鮑率 = UARTCLK/16（150 MHz → 9.375 Mbaud）。
- UARTCLK = `clk_peri`。SDK 開機設 `clk_peri = clk_sys = 150 MHz`（`runtime_init_clocks.c`）；呼叫 `set_sys_clock_*()` 後 SDK 預設把 clk_peri 改成 48 MHz PLL_USB（見 `pico-sdk.md` §7.4）→ **改時脈要在 `uart_init` 之前**。
- 中斷：只接出合併的 `UARTINTR` → `UART0_IRQ`(33) / `UART1_IRQ`(34)。來源有 RX（FIFO 到門檻）、RT（RX timeout：FIFO 非空且 32 bit 時間沒新資料）、TX、錯誤。
- DMA：`DREQ_UART0_TX/RX` = 28/29，`DREQ_UART1_TX/RX` = 30/31；SDK 函式 `uart_get_dreq_num(uart, is_tx)`。
- 沒有 UART 相關 errata（Appendix D 無 UART 項目）。

### 2.2 API（簽名照 SDK 標頭）

```c
uint uart_init(uart_inst_t *uart, uint baudrate);        // 重置+啟用；8N1、開 FIFO、開 DMACR；回傳「實際」鮑率；clk_peri=0 時回 0
void uart_deinit(uart_inst_t *uart);
uint uart_set_baudrate(uart_inst_t *uart, uint baudrate); // 回傳實際鮑率
void uart_set_format(uart_inst_t *uart, uint data_bits /*5..8*/, uint stop_bits /*1..2*/, uart_parity_t parity);
//   parity: UART_PARITY_NONE / UART_PARITY_EVEN / UART_PARITY_ODD
void uart_set_fifo_enabled(uart_inst_t *uart, bool enabled);      // 關掉時 TX FIFO 內資料會遺失
static inline void uart_set_hw_flow(uart_inst_t *uart, bool cts, bool rts);
static inline void uart_set_irqs_enabled(uart_inst_t *uart, bool rx_has_data, bool tx_needs_data);
//   舊名 uart_set_irq_enables() 仍可用（SDK < 2.0 相容）
static inline bool uart_is_writable(uart_inst_t *uart);   // TX FIFO 有空間
static inline bool uart_is_readable(uart_inst_t *uart);   // RX FIFO 有資料
bool uart_is_readable_within_us(uart_inst_t *uart, uint32_t us);
static inline void uart_write_blocking(uart_inst_t *uart, const uint8_t *src, size_t len);
static inline void uart_read_blocking(uart_inst_t *uart, uint8_t *dst, size_t len);
static inline void uart_putc_raw(uart_inst_t *uart, char c);
static inline void uart_putc(uart_inst_t *uart, char c);   // 可做 LF→CRLF 轉換（若開啟）
static inline void uart_puts(uart_inst_t *uart, const char *s);
static inline char uart_getc(uart_inst_t *uart);           // 阻塞
static inline void uart_tx_wait_blocking(uart_inst_t *uart); // 等到最後一個 bit 真的送出
void uart_set_translate_crlf(uart_inst_t *uart, bool translate);
void uart_set_break(uart_inst_t *uart, bool en);
static inline uint uart_get_dreq_num(uart_inst_t *uart, bool is_tx);
static inline uart_hw_t *uart_get_hw(uart_inst_t *uart);  // 直接存取暫存器：->dr, ->fr, ->imsc, ->icr ...
```

- `uart_write_blocking` / `uart_read_blocking` 是 inline 的逐 byte 忙等迴圈；寫入回傳時資料可能還在 FIFO，要確定送完用 `uart_tx_wait_blocking`。
- `uart_set_irqs_enabled(uart, true, …)` 會同時開 RX 與 RT（timeout）中斷，並把 RX 門檻設最低（FIFO ≥ 4 筆觸發；不足 4 筆靠 32 bit 時間的 timeout 觸發）。
- 若專案開了 `pico_enable_stdio_uart(target 1)`，stdio 會占用 uart0（GP0/GP1）；自己再用 uart0 會和 `printf` 混在一起。

### 2.3 鮑率與吞吐量

一個 frame 的 bit 數 = 1（start）+ data + parity(0/1) + stop(1/2)。8N1 = **10 bit / byte**。

| 鮑率 | 8N1 bytes/s | 每 byte 時間 | 32-byte RX FIFO 可撐 |
|---|---|---|---|
| 9600 | 960 | 1.04 ms | 33 ms |
| 115200 | 11 520 | 86.8 µs | 2.78 ms |
| 921600 | 92 160 | 10.9 µs | 347 µs |
| 3 000 000 | 300 000 | 3.33 µs | 107 µs |

實際鮑率誤差範例（clk_peri = 150 MHz）：依 SDK 公式 `div = 8×150e6/115200 + 1 = 10417` → IBRD = 81、FBRD = 24 → 實際 = 4×150e6/(64×81+24) ≈ 115 207 baud（誤差約 +0.006%）。接收端一般容忍約 ±2–3%（⚠️ 經驗值，依對端而定）。

### 2.4 範例

Polling（最簡單）：

```c
#include "pico/stdlib.h"
#include "hardware/uart.h"
#define U uart1
int main(void) {
    uint actual = uart_init(U, 115200);          // 先 init，再設腳
    gpio_set_function(4, GPIO_FUNC_UART);        // GP4 = UART1 TX
    gpio_set_function(5, GPIO_FUNC_UART);        // GP5 = UART1 RX
    uart_set_format(U, 8, 1, UART_PARITY_NONE);
    (void)actual;
    uart_puts(U, "hello\n");
    while (true) {
        if (uart_is_readable(U)) {
            char c = uart_getc(U);
            uart_putc_raw(U, c);                 // echo
        }
    }
}
```

IRQ 驅動 RX + ring buffer（ISR 只搬資料，主迴圈解析）：

```c
#include "pico/stdlib.h"
#include "hardware/uart.h"
#include "hardware/irq.h"
#include "hardware/sync.h"                        // __wfi()
#define U uart0
#define RXN 256u                                  // 2 的次方
static volatile uint8_t rxbuf[RXN];
static volatile uint32_t rx_head, rx_tail, rx_drop;   // head 只有 ISR 寫，tail 只有主程式寫

static void on_uart_rx(void) {
    while (uart_is_readable(U)) {                 // 一次把 FIFO 讀空（也會清掉 RX/RT 中斷條件）
        uint8_t c = (uint8_t)uart_get_hw(U)->dr;  // 高位是錯誤旗標，取低 8 bit
        uint32_t h = rx_head, n = (h + 1) & (RXN - 1);
        if (n != rx_tail) { rxbuf[h] = c; rx_head = n; } else { rx_drop++; }
    }
}

static int rx_pop(void) {                          // 主迴圈用；無資料回 -1
    uint32_t t = rx_tail;
    if (t == rx_head) return -1;
    int c = rxbuf[t];
    rx_tail = (t + 1) & (RXN - 1);
    return c;
}

int main(void) {
    uart_init(U, 115200);
    gpio_set_function(0, GPIO_FUNC_UART);
    gpio_set_function(1, GPIO_FUNC_UART);
    irq_set_exclusive_handler(UART0_IRQ, on_uart_rx);
    irq_set_enabled(UART0_IRQ, true);
    uart_set_irqs_enabled(U, true, false);        // RX + RX timeout
    while (true) {
        int c;
        while ((c = rx_pop()) >= 0) { /* 解析 */ }
        __wfi();                                   // 沒事就睡到下一個中斷
    }
}
```

（單一 producer / 單一 consumer 且同一核時這樣寫可行；跨核或多 producer 見 `multicore-sync.md` A11 / B7。）

DMA TX（大量輸出時 CPU 完全不用等）：

```c
#include "hardware/dma.h"
static const char msg[] = "....long text....";
int ch = dma_claim_unused_channel(true);
dma_channel_config c = dma_channel_get_default_config(ch);
channel_config_set_transfer_data_size(&c, DMA_SIZE_8);
channel_config_set_read_increment(&c, true);
channel_config_set_write_increment(&c, false);
channel_config_set_dreq(&c, uart_get_dreq_num(uart0, true));   // TX FIFO 有空位才搬
dma_channel_configure(ch, &c, &uart_get_hw(uart0)->dr, msg, sizeof msg - 1, true);
// ...CPU 做別的事...
dma_channel_wait_for_finish_blocking(ch);   // DMA 寫完 ≠ 線上送完；需要時再 uart_tx_wait_blocking(uart0)
```

DMA RX 適合「已知長度」或配合 ring buffer（`pico-dma.md` §4.7）；DMA 用 8-bit 讀 DR 只拿到資料，看不到錯誤旗標。DMA 服務 FIFO 時 CPU 不要同時讀寫同一個 FIFO（`pico-dma.md` §1.7）。

### 2.5 UART 效能取捨

| 作法 | CPU 負擔 | 適用 |
|---|---|---|
| `uart_write_blocking` / `getc` 忙等 | 100%（等 FIFO） | 少量、低速、簡單題 |
| polling 但先查 `uart_is_writable/readable` | 低（只在有資料時處理） | 主迴圈很短時 |
| IRQ + ring buffer | 每 4 byte 或 timeout 一次中斷 | 不定長、非同步接收 |
| DMA | 幾乎 0 | 大量 TX、固定長度 RX、高鮑率 |

瓶頸通常是**線速**而不是 CPU：115200 baud 每 byte 87 µs，CPU 跑 150 MHz 可以做約 13 000 cycle 的事。優化方向：提高鮑率（雙方都支援時）、減少送出的字元數（二進位代替文字、`printf` 改手寫轉換）、讓輸出與運算重疊（DMA / IRQ）。

---

## 3. SPI（datasheet §12.3、`hardware/spi.h`）

### 3.1 硬體重點

- PL022，Motorola SPI / TI SSI / Microwire；4–16 bit frame；TX/RX FIFO 各 **8 個**。
- 腳位名：`SPIx TX`（MOSI，master 時）、`SPIx RX`（MISO）、`SCK`、`CSn`。TX 永遠是輸出、RX 永遠是輸入（不分 master/slave）。
- 時脈：SSPCLK = `clk_peri`；`SCK = clk_peri / (CPSDVSR × (1 + SCR))`，CPSDVSR 為 2–254 偶數，SCR 0–255。
- 最高 SCK：master = clk_peri/2（公式上 150 MHz → 75 MHz；datasheet §12.3.4.4 文字寫 "70.5Mb/s"，與公式不一致 ⚠️，以 `spi_init` 回傳值為準）；slave 要求 SSPCLK ≥ 12 × SCK → 最多 12.5 MHz。實際可用速度還受接線與對端晶片限制。
- 只支援 **MSB first**（`SPI_LSB_FIRST` 只在開了 param assertion 時被 assert 擋掉；否則被忽略，仍是 MSB first）。
- **硬體 CSn 的坑**：Motorola 格式 CPHA=0 時，連續傳多個 frame，PL022 會在每個 frame 之間把 CSn 拉高一下（§12.3.4.x）。多數感測器要求整個交易 CS 保持低 → **CS 用一般 GPIO 手動控制**（pico-examples 都這樣做）。
- RP2350 新增：slave 未被選取時 TX 輸出自動三態（nSSPOE），多 slave 共線不用軟體管 OE（§12.3.1）。
- DMA：`DREQ_SPI0_TX/RX` = 24/25、`DREQ_SPI1_TX/RX` = 26/27；`spi_get_dreq(spi, is_tx)`。`spi_init` 會開 TX/RX DMA 請求。

### 3.2 API

```c
uint spi_init(spi_inst_t *spi, uint baudrate);   // 重置、設鮑率、8 bit / CPOL0 / CPHA0 / MSB、開 DMACR、enable；回傳實際鮑率
void spi_deinit(spi_inst_t *spi);
uint spi_set_baudrate(spi_inst_t *spi, uint baudrate);   // 回傳實際值（≤ 要求值）
uint spi_get_baudrate(const spi_inst_t *spi);
static inline void spi_set_format(spi_inst_t *spi, uint data_bits /*4..16*/,
                                  spi_cpol_t cpol, spi_cpha_t cpha, spi_order_t order /*只能 SPI_MSB_FIRST*/);
static inline void spi_set_slave(spi_inst_t *spi, bool slave);
static inline bool spi_is_writable(const spi_inst_t *spi);
static inline bool spi_is_readable(const spi_inst_t *spi);
static inline bool spi_is_busy(const spi_inst_t *spi);   // 仍在移位中
int spi_write_read_blocking(spi_inst_t *spi, const uint8_t *src, uint8_t *dst, size_t len);
int spi_write_blocking(spi_inst_t *spi, const uint8_t *src, size_t len);        // 丟棄收到的資料
int spi_read_blocking(spi_inst_t *spi, uint8_t repeated_tx_data, uint8_t *dst, size_t len); // 一直送 repeated_tx_data
int spi_write16_read16_blocking(spi_inst_t *spi, const uint16_t *src, uint16_t *dst, size_t len);
int spi_write16_blocking(spi_inst_t *spi, const uint16_t *src, size_t len);
int spi_read16_blocking(spi_inst_t *spi, uint16_t repeated_tx_data, uint16_t *dst, size_t len);
static inline uint spi_get_dreq(spi_inst_t *spi, bool is_tx);
```

- 回傳值都是 `len`（傳輸筆數），不會報錯；SPI 本身沒有 ACK，**讀到全 0x00 / 0xFF 時要自己懷疑接線或 mode**。
- `spi_write_blocking` 回傳前會等移位完成並清空 RX FIFO，所以之後馬上拉高 CS 是安全的。
- 這三個 blocking 函式在 SDK 中標成 `__not_in_flash_func`（放 RAM 執行）。
- `spi_write_read_blocking` 會控制在途筆數不超過 RX FIFO 深度 8，被中斷打斷也不會溢位。

SPI mode 對照：

| Mode | CPOL | CPHA | SDK |
|---|---|---|---|
| 0 | 0 | 0 | `SPI_CPOL_0, SPI_CPHA_0`（spi_init 預設） |
| 1 | 0 | 1 | `SPI_CPOL_0, SPI_CPHA_1` |
| 2 | 1 | 0 | `SPI_CPOL_1, SPI_CPHA_0` |
| 3 | 1 | 1 | `SPI_CPOL_1, SPI_CPHA_1` |

### 3.3 範例：讀感測器暫存器（CS 手動）

```c
#include "pico/stdlib.h"
#include "hardware/spi.h"
#define SPI   spi0
#define P_RX  16   // MISO
#define P_CS  17
#define P_SCK 18
#define P_TX  19   // MOSI

static inline void cs(bool active) { gpio_put(P_CS, !active); }   // 低電位有效

void spi_dev_init(void) {
    spi_init(SPI, 10 * 1000 * 1000);                 // 要求 10 MHz；回傳實際值
    spi_set_format(SPI, 8, SPI_CPOL_0, SPI_CPHA_0, SPI_MSB_FIRST);
    gpio_set_function(P_RX,  GPIO_FUNC_SPI);
    gpio_set_function(P_SCK, GPIO_FUNC_SPI);
    gpio_set_function(P_TX,  GPIO_FUNC_SPI);
    gpio_init(P_CS);                                  // CS 用 SIO，不用 GPIO_FUNC_SPI
    gpio_set_dir(P_CS, GPIO_OUT);
    gpio_put(P_CS, 1);
}

// 很多感測器：位址最高位 = 1 代表讀（依元件 datasheet！）
void spi_reg_read(uint8_t reg, uint8_t *buf, size_t n) {
    uint8_t cmd = reg | 0x80;
    cs(true);
    spi_write_blocking(SPI, &cmd, 1);
    spi_read_blocking(SPI, 0x00, buf, n);
    cs(false);
}
```

### 3.4 DMA 全雙工（TX 與 RX 兩個通道都要）

```c
#include "hardware/dma.h"
// 前提：CS 已拉低；txbuf/rxbuf 長度 N
uint tx = dma_claim_unused_channel(true), rx = dma_claim_unused_channel(true);
dma_channel_config c = dma_channel_get_default_config(tx);
channel_config_set_transfer_data_size(&c, DMA_SIZE_8);
channel_config_set_dreq(&c, spi_get_dreq(SPI, true));
dma_channel_configure(tx, &c, &spi_get_hw(SPI)->dr, txbuf, N, false);

c = dma_channel_get_default_config(rx);
channel_config_set_transfer_data_size(&c, DMA_SIZE_8);
channel_config_set_dreq(&c, spi_get_dreq(SPI, false));
channel_config_set_read_increment(&c, false);
channel_config_set_write_increment(&c, true);
dma_channel_configure(rx, &c, rxbuf, &spi_get_hw(SPI)->dr, N, false);

dma_start_channel_mask((1u << tx) | (1u << rx));   // 同時啟動
dma_channel_wait_for_finish_blocking(rx);          // 以 RX 完成為準（最後一個 bit 收完）
cs(false);
```

- 只寫不讀時可只開 TX 通道，但 RX FIFO 會滿（PL022 設 overrun 旗標，資料被丟，SDK 註解說沒開 RORIM 就無害）；結束時要 `while (spi_is_busy(SPI))` 再拉 CS，並把 RX FIFO 讀空（`while (spi_is_readable(SPI)) (void)spi_get_hw(SPI)->dr;`）。
- 16-bit frame（`spi_set_format(SPI, 16, …)`）配 `DMA_SIZE_16`，每筆搬兩倍資料，DMA 次數減半。
- 更多 DMA 設定（chain、ring、IRQ）看 `pico-dma.md`。

### 3.5 SPI 效能取捨

| 方法 | 說明 |
|---|---|
| blocking（CPU 餵 FIFO） | SCK 高時 CPU 可能來不及餵 → frame 間有空隙 ⚠️未實測；CPU 被占滿 |
| DMA TX+RX | 可跑滿線速、CPU 空出來；長度 ≥ 數十 byte 才划算（設定 DMA 本身要時間） |
| 提高 SCK | 最直接；先確認對端晶片上限與接線（杜邦線 > 20 MHz 容易出錯） |
| 16-bit frame | 減少 FIFO / DMA 次數 |
| 減少 CS 交易數 | 用元件的 burst / auto-increment 一次讀多個暫存器 |

---

## 4. I2C（datasheet §12.2、`hardware/i2c.h`）

### 4.1 硬體重點

- Synopsys DW_apb_i2c；Master 或 Slave（同一個 block 不可同時當兩者）；7-bit（master 可 10-bit）位址。
- Standard 100 kbit/s、Fast 400 kbit/s、Fast-mode Plus 1 Mbit/s；**不支援 High-speed 3.4 Mbit/s**。
- TX / RX buffer 各 16 筆；可用 DMA（`DREQ_I2C0_TX/RX` = 44/45、`DREQ_I2C1_TX/RX` = 46/47）。
- 時脈 = **clk_sys**（不是 clk_peri）；SDK `i2c_set_baudrate` 用 clk_sys 算 SCL 高低計數（低 60%、高 40%）。
- 開汲極匯流排：**SDA、SCL 都需要 pull-up**。datasheet 建議 pad 開 pull-up、slew 慢、Schmitt 開，並說板上應有**外部 pull-up**（內建 pull-up 約數十 kΩ ⚠️未查到確切值，對長線/多元件不夠強）。常用外部 4.7 kΩ（100/400 kHz）。
- I2C 位址 0x00–0x07 與 0x78–0x7F 為保留位址，SDK 會 assert（若開 param assert）；bus scan 要跳過。

### 4.2 API

```c
uint i2c_init(i2c_inst_t *i2c, uint baudrate);        // master 模式、啟用 restart；回傳實際鮑率
void i2c_deinit(i2c_inst_t *i2c);
uint i2c_set_baudrate(i2c_inst_t *i2c, uint baudrate);
void i2c_set_slave_mode(i2c_inst_t *i2c, bool slave, uint8_t addr);

int i2c_write_blocking(i2c_inst_t *i2c, uint8_t addr, const uint8_t *src, size_t len, bool nostop);
int i2c_read_blocking (i2c_inst_t *i2c, uint8_t addr, uint8_t *dst, size_t len, bool nostop);
int i2c_write_timeout_us(i2c_inst_t *i2c, uint8_t addr, const uint8_t *src, size_t len, bool nostop, uint timeout_us);
int i2c_read_timeout_us (i2c_inst_t *i2c, uint8_t addr, uint8_t *dst, size_t len, bool nostop, uint timeout_us);
int i2c_write_blocking_until(i2c_inst_t *i2c, uint8_t addr, const uint8_t *src, size_t len, bool nostop, absolute_time_t until);
int i2c_read_blocking_until (i2c_inst_t *i2c, uint8_t addr, uint8_t *dst, size_t len, bool nostop, absolute_time_t until);
int i2c_write_timeout_per_char_us(i2c_inst_t *i2c, uint8_t addr, const uint8_t *src, size_t len, bool nostop, uint timeout_per_char_us);
int i2c_read_timeout_per_char_us (i2c_inst_t *i2c, uint8_t addr, uint8_t *dst, size_t len, bool nostop, uint timeout_per_char_us);
// 低階（slave 或自己組命令用）
static inline size_t  i2c_get_write_available(i2c_inst_t *i2c);
static inline size_t  i2c_get_read_available(i2c_inst_t *i2c);
static inline uint8_t i2c_read_byte_raw(i2c_inst_t *i2c);
static inline void    i2c_write_byte_raw(i2c_inst_t *i2c, uint8_t value);
static inline uint    i2c_get_dreq(i2c_inst_t *i2c, bool is_tx);
```

回傳值語意（照 `i2c.c`）：

| 狀況 | 回傳 |
|---|---|
| 成功 | 傳輸的 byte 數（= len） |
| 位址沒 ACK / 匯流排上沒裝置 | `PICO_ERROR_GENERIC`（負值） |
| 位址 ACK 但某個資料 byte 被 NAK（寫入） | 已成功的 byte 數（< len） |
| 逾時（`_timeout_us` / `_until` 版本） | `PICO_ERROR_TIMEOUT` |

- **一律檢查 `ret < 0` 或 `ret != len`**；用名稱比較錯誤碼，不要寫死數字。
- `nostop = true`：這次傳輸結束**不送 STOP**，下一次傳輸開頭送 **repeated START** → 「寫暫存器位址 → 讀資料」的標準作法。
- `addr` 是 **7-bit** 位址（例如 0x68），不要傳左移過的 8-bit 位址（0xD0）。
- 非 timeout 版本在 SCL 被拉住或沒有 pull-up 時可能**永遠卡住** → 考試 / judge 環境用 `_timeout_us` 版本。

### 4.3 範例

初始化（`i2c_init` 不會設腳位與 pull-up）：

```c
#include "pico/stdlib.h"
#include "hardware/i2c.h"
#define I2C  i2c0
#define SDA  4
#define SCL  5
void i2c_setup(void) {
    i2c_init(I2C, 400 * 1000);
    gpio_set_function(SDA, GPIO_FUNC_I2C);
    gpio_set_function(SCL, GPIO_FUNC_I2C);
    gpio_pull_up(SDA);                 // 內建 pull-up 只適合短線少量元件；最好再加外部電阻
    gpio_pull_up(SCL);
}
```

暫存器讀 / 寫：

```c
// 讀：START addr+W reg  (repeated) START addr+R data... STOP
int i2c_reg_read(uint8_t addr, uint8_t reg, uint8_t *buf, size_t n) {
    int r = i2c_write_timeout_us(I2C, addr, &reg, 1, true, 2000);          // nostop = true
    if (r != 1) return (r < 0) ? r : PICO_ERROR_GENERIC;
    return i2c_read_timeout_us(I2C, addr, buf, n, false, 2000 + 100 * n);  // 最後送 STOP
}

// 寫：位址與資料放在同一個 buffer，一次送完（不要拆成兩次 write）
int i2c_reg_write(uint8_t addr, uint8_t reg, const uint8_t *data, size_t n) {
    uint8_t tmp[1 + 16];
    if (n > 16) return PICO_ERROR_GENERIC;
    tmp[0] = reg;
    for (size_t i = 0; i < n; i++) tmp[1 + i] = data[i];
    int r = i2c_write_timeout_us(I2C, addr, tmp, n + 1, false, 2000 + 100 * n);
    return (r == (int)(n + 1)) ? (int)n : ((r < 0) ? r : PICO_ERROR_GENERIC);
}
```

Bus scan（pico-examples `i2c/bus_scan` 的作法：對每個位址讀 1 byte，看回傳是否 < 0）：

```c
static bool reserved(uint8_t a) { return (a & 0x78) == 0 || (a & 0x78) == 0x78; }
void i2c_scan(void) {
    for (uint8_t a = 0; a < 0x80; a++) {
        uint8_t d;
        int r = reserved(a) ? PICO_ERROR_GENERIC
                            : i2c_read_timeout_us(I2C, a, &d, 1, false, 5000);
        if (r >= 0) printf("found 0x%02x\n", a);
    }
}
```

### 4.4 Slave 模式（`pico/i2c_slave.h`，CMake `pico_i2c_slave`）

```c
typedef enum { I2C_SLAVE_RECEIVE, I2C_SLAVE_REQUEST, I2C_SLAVE_FINISH } i2c_slave_event_t;
typedef void (*i2c_slave_handler_t)(i2c_inst_t *i2c, i2c_slave_event_t event);
void i2c_slave_init(i2c_inst_t *i2c, uint8_t address, i2c_slave_handler_t handler);
void i2c_slave_deinit(i2c_inst_t *i2c);
```

- handler 在 **I2C 中斷 context** 被呼叫：RECEIVE → 用 `i2c_read_byte_raw()` 取資料；REQUEST → 用 `i2c_write_byte_raw()` 回資料；FINISH → master 送了 STOP 或 restart。
- 流程：設腳 + pull-up → `i2c_init(i2c, baud)` → `i2c_slave_init(i2c, addr, handler)`（pico-examples `i2c/slave_mem_i2c` 模擬一顆 256-byte EEPROM）。

### 4.5 I2C 吞吐量與優化

每 byte 在線上 = 8 data + 1 ACK = 9 個 SCL 週期，另加 START / 位址 byte / STOP。

| 模式 | 純資料上限 | 讀一個 1-byte 暫存器（約 4 byte 時間 + 起停） |
|---|---|---|
| 100 kHz | ≈ 11 kB/s | ≈ 0.4 ms |
| 400 kHz | ≈ 44 kB/s | ≈ 0.1 ms |
| 1 MHz（FM+，對端也要支援） | ≈ 111 kB/s | ≈ 40 µs |

（估算值，未含 SCL clock stretching 與 SDK 開銷。）

優化：提高速度（看元件 datasheet）、**一次 burst 讀連續暫存器**（多數感測器位址自動遞增）、避免每個 byte 一次交易、用 timeout 版本避免卡死。I2C 用 DMA 需要寫入含命令位元的 `IC_DATA_CMD`，較複雜（§12.2.15），通常不值得。

---

## 5. PWM（datasheet §12.5、`hardware/pwm.h`）

### 5.1 硬體重點

- **12 個 slice**（RP2040：8），每 slice 兩個輸出 A/B：同一 slice 的 A/B **共用頻率（TOP、分頻）**，duty 各自獨立。
- QFN-60（Pico 2）：GPIO 0–29 只接到 slice 0–7（與 RP2040 腳位相容）；slice 8–11 只在 QFN-80 的 GPIO 32–47 上，**但在 A 封裝仍可當週期性中斷 timer 使用**（§12.5.2 Note）。
- 每 slice：16-bit 計數器、8.4 分數分頻（DIV_INT 8 bit + DIV_FRAC 4 bit）、計數到 TOP 後 wrap 或（phase-correct）倒數。
- 計數時脈 = **clk_sys**。
- CC（比較值）與 TOP **雙緩衝**：軟體隨時可寫，在下一次 wrap 才生效 → 不會產生毛刺。
- 輸出規則：`counter < CC` 時輸出高。**CC = 0 → 0%；CC = TOP + 1 → 100%**（無毛刺）。
- 兩條 IRQ：`PWM_IRQ_WRAP_0`(8)、`PWM_IRQ_WRAP_1`(9)（RP2040 只有一條 `PWM_IRQ_WRAP`；SDK 在 RP2350 把 `PWM_IRQ_WRAP` 定義成 `PWM_IRQ_WRAP_0`，可移植寫法 `PWM_DEFAULT_IRQ_NUM()`）。
- DREQ：每 slice wrap 一次發一個 DREQ（`DREQ_PWM_WRAP0..11` = 32–43；`pwm_get_dreq(slice)`）。
- B 腳可當**輸入**：B 高時計數（量 duty）、B 上升/下降沿計數（量頻率）。輸入的高、低時間都必須 **嚴格大於 1 個 clk_sys 週期**。

### 5.2 公式（clk_sys = 150 MHz）

```
DIV = DIV_INT + DIV_FRAC/16          （1 ≤ DIV < 256；DIV_INT = 0 代表 256，此時 FRAC 應為 0 ⚠️未驗證）
period（clk_sys cycles）= (TOP + 1) × (PH_CORRECT + 1) × DIV
f_PWM = f_sys / ((TOP + 1) × (PH_CORRECT + 1) × DIV)
duty  = CC / (TOP + 1)               （phase-correct 也一樣是 CC/(TOP+1)）
解析度 = TOP + 1 階
```

| 目標 | DIV | TOP | 實際 | 說明 |
|---|---|---|---|---|
| 20 kHz 馬達 | 1 | 7499 | 20.000 kHz | 150e6/20e3 = 7500 = TOP+1 |
| 1 kHz | 2.5（INT 2, FRAC 8） | 59999 | 1.000 kHz | 150e6/1e3 = 150 000 > 65536 → 需要分頻 |
| 50 Hz 伺服 | 64 | 46874 | 50.000 Hz | 1 count = 64/150 MHz ≈ 0.4267 µs；1.5 ms ≈ CC 3516 |
| 最高頻（2 階） | 1 | 1 | 75 MHz | duty 只有 0/50/100% |
| 最低頻 | 256（INT 0） | 65535 | ≈ 8.94 Hz | phase-correct 再減半 ≈ 4.47 Hz；更低用 Timer |

**off-by-one**：想要 N 個 count 的週期，`pwm_set_wrap(slice, N - 1)`。

### 5.3 API

```c
static inline uint pwm_gpio_to_slice_num(uint gpio);
static inline uint pwm_gpio_to_channel(uint gpio);              // PWM_CHAN_A = 0, PWM_CHAN_B = 1
static inline pwm_config pwm_get_default_config(void);          // DIV=1、wrap=0xffff、非 phase-correct、free-running
static inline void pwm_config_set_wrap(pwm_config *c, uint16_t wrap);
static inline void pwm_config_set_clkdiv(pwm_config *c, float div);
static inline void pwm_config_set_clkdiv_int_frac4(pwm_config *c, uint32_t div_int, uint8_t div_frac4);
static inline void pwm_config_set_phase_correct(pwm_config *c, bool phase_correct);
static inline void pwm_config_set_clkdiv_mode(pwm_config *c, enum pwm_clkdiv_mode mode);
//   PWM_DIV_FREE_RUNNING / PWM_DIV_B_HIGH / PWM_DIV_B_RISING / PWM_DIV_B_FALLING
static inline void pwm_config_set_output_polarity(pwm_config *c, bool a, bool b);
static inline void pwm_init(uint slice_num, pwm_config *c, bool start);

static inline void pwm_set_wrap(uint slice_num, uint16_t wrap);
static inline void pwm_set_chan_level(uint slice_num, uint chan, uint16_t level);
static inline void pwm_set_both_levels(uint slice_num, uint16_t level_a, uint16_t level_b);
static inline void pwm_set_gpio_level(uint gpio, uint16_t level);
static inline void pwm_set_clkdiv(uint slice_num, float divider);   // 1.0 ≤ divider < 256
static inline void pwm_set_clkdiv_int_frac4(uint slice_num, uint8_t div_int, uint8_t div_frac4);
static inline void pwm_set_phase_correct(uint slice_num, bool phase_correct);
static inline void pwm_set_clkdiv_mode(uint slice_num, enum pwm_clkdiv_mode mode);
static inline void pwm_set_output_polarity(uint slice_num, bool a, bool b);
static inline uint16_t pwm_get_counter(uint slice_num);
static inline void pwm_set_counter(uint slice_num, uint16_t c);
static inline void pwm_advance_count(uint slice_num);   // 相位 +1 count
static inline void pwm_retard_count(uint slice_num);    // 相位 −1 count
static inline void pwm_set_enabled(uint slice_num, bool enabled);
static inline void pwm_set_mask_enabled(uint32_t mask);  // 直接寫 EN 暫存器：沒列在 mask 的 slice 會被「關掉」

static inline void pwm_set_irq_enabled(uint slice_num, bool enabled);   // IRQ0（= PWM_DEFAULT_IRQ_NUM()）
static inline void pwm_set_irq0_enabled(uint slice_num, bool enabled);
static inline void pwm_set_irq1_enabled(uint slice_num, bool enabled);  // RP2350 才有
static inline void pwm_set_irq_mask_enabled(uint32_t slice_mask, bool enabled);
static inline void pwm_clear_irq(uint slice_num);
static inline uint32_t pwm_get_irq_status_mask(void);
static inline uint pwm_get_dreq(uint slice_num);
```

- `pwm_set_clkdiv(slice, float)` 小數部分**無條件捨去**到 1/16；`pwm_config_set_clkdiv(&cfg, float)` 則預設**四捨五入**到最近的 1/16（`PICO_PWM_CLKDIV_ROUND_NEAREST` 預設 = `PICO_CLKDIV_ROUND_NEAREST` = 1）。要精確就用 `int_frac4` 整數版。
- `pwm_set_mask_enabled` 可讓多個 slice **同一個 cycle 同步啟動**（lockstep）。
- Hazard3 沒有 FPU，浮點分頻只在初始化時算一次即可；迴圈內用整數。

### 5.4 範例

設定頻率與 duty（整數版，解析度最大化）：

```c
#include "pico/stdlib.h"
#include "hardware/pwm.h"
#include "hardware/clocks.h"

// 回傳 TOP；duty 用 pwm_set_gpio_level(gpio, duty_permille * (top + 1) / 1000)
uint16_t pwm_setup(uint gpio, uint32_t freq_hz) {
    uint slice = pwm_gpio_to_slice_num(gpio);
    uint32_t fsys = clock_get_hz(clk_sys);
    // 先求 16×DIV（4 bit 小數），無條件進位，保證 TOP ≤ 65535
    uint64_t div16 = ((uint64_t)fsys * 16 + (uint64_t)freq_hz * 65536 - 1) / ((uint64_t)freq_hz * 65536);
    if (div16 < 16) div16 = 16;                 // DIV ≥ 1
    if (div16 > 255 * 16 + 15) div16 = 255 * 16 + 15;
    uint32_t top = (uint32_t)(((uint64_t)fsys * 16 / (div16 * freq_hz)) - 1);
    if (top > 65535) top = 65535;
    gpio_set_function(gpio, GPIO_FUNC_PWM);
    pwm_set_clkdiv_int_frac4(slice, (uint8_t)(div16 >> 4), (uint8_t)(div16 & 0xF));
    pwm_set_wrap(slice, (uint16_t)top);
    pwm_set_gpio_level(gpio, 0);
    pwm_set_enabled(slice, true);
    return (uint16_t)top;
}
// 例：uint16_t top = pwm_setup(25, 1000); pwm_set_gpio_level(25, (top + 1) / 4);  // 25%
```

Wrap 中斷（每個 PWM 週期更新一次 duty；pico-examples `pwm/led_fade` 的架構）：

```c
static uint slice;
static void on_wrap(void) {
    pwm_clear_irq(slice);                 // 先清旗標（寫 INTR）
    // 計算下一個 level，pwm_set_chan_level(...)；新值在「下一次」wrap 生效
}
// setup：
pwm_clear_irq(slice);
pwm_set_irq_enabled(slice, true);
irq_set_exclusive_handler(PWM_DEFAULT_IRQ_NUM(), on_wrap);
irq_set_enabled(PWM_DEFAULT_IRQ_NUM(), true);
```

多個 slice 共用同一條 IRQ 時，handler 內用 `pwm_get_irq_status_mask()` 看是哪些 slice，再逐一 `pwm_clear_irq`。

把 PWM 當輸入計數器（B 腳，例：量 GP5 的頻率，pico-examples `pwm/measure_duty_cycle` 的變形）：

```c
// GP5 = PWM2 B
float measure_freq_hz(uint gpio, uint32_t window_ms) {
    uint slice = pwm_gpio_to_slice_num(gpio);       // 必須是 B 腳：pwm_gpio_to_channel(gpio) == PWM_CHAN_B
    pwm_config cfg = pwm_get_default_config();
    pwm_config_set_clkdiv_mode(&cfg, PWM_DIV_B_RISING);   // 每個上升沿計數 1（DIV=1）
    pwm_init(slice, &cfg, false);
    gpio_set_function(gpio, GPIO_FUNC_PWM);
    pwm_set_counter(slice, 0);
    pwm_set_enabled(slice, true);
    sleep_ms(window_ms);
    pwm_set_enabled(slice, false);
    return pwm_get_counter(slice) * 1000.0f / window_ms;  // 16-bit：窗口內邊緣數需 < 65536（否則加大 DIV 或開 wrap IRQ 累計）
}
```

量 duty：改 `PWM_DIV_B_HIGH`，`duty ≈ count / (f_sys / DIV × 窗口秒數)`。

DMA 寫 CC 產生波形（每個 PWM 週期換一個 duty，CPU 不介入）：

```c
#include "hardware/dma.h"
// CC 暫存器：低 16 bit = A、高 16 bit = B。DMA 要用 32-bit 寫：
// RP2350 的 8/16-bit 寫 IO 暫存器會被「複製」到整個 32 bit（§2.1.5），16-bit 寫會讓 A 和 B 變同一個值。
static uint32_t wave[256];                       // wave[i] = ((uint32_t)levelB << 16) | levelA
int ch = dma_claim_unused_channel(true);
dma_channel_config c = dma_channel_get_default_config(ch);
channel_config_set_transfer_data_size(&c, DMA_SIZE_32);
channel_config_set_read_increment(&c, true);
channel_config_set_write_increment(&c, false);
channel_config_set_dreq(&c, pwm_get_dreq(slice));   // 每次 wrap 搬一筆
dma_channel_configure(ch, &c, &pwm_hw->slice[slice].cc, wave, 256, true);
// 連續循環：用 ring（read 位址環繞）或兩通道 chain，見 pico-dma.md §4.6 / §4.7
```

### 5.5 PWM 效能與用途

- PWM slice 可當**免費的週期中斷源**（尤其 A 封裝的 slice 8–11 沒接腳）：`TOP`+`DIV` 決定週期，開 wrap IRQ 即可。
- 波形輸出：IRQ 每週期改 CC（簡單，CPU 有負擔）→ DMA 改 CC（零 CPU，適合高頻或長波形）。
- 頻率 ↔ 解析度取捨：`f × (TOP+1) = f_sys / DIV`；150 MHz 下 10 bit 解析度最高約 146 kHz，8 bit 約 586 kHz。

---

## 6. ADC 與溫度感測（datasheet §12.4、`hardware/adc.h`）

### 6.1 硬體重點

| 項目 | RP2350A（QFN-60，Pico 2） | RP2350B（QFN-80） |
|---|---|---|
| 外部通道 | 4：ch0–3 = GPIO 26–29 | 8：ch0–7 = GPIO 40–47 |
| 溫度感測 | ch4 | ch8 |
| SDK | `ADC_BASE_PIN` 26、`NUM_ADC_CHANNELS` 5 | `ADC_BASE_PIN` 40、`NUM_ADC_CHANNELS` 9 |

- SAR、12-bit（0–4095），**ENOB 9.2** ⚠️未查證；每次轉換 96 個 clk_adc 週期，clk_adc = 48 MHz → **2 µs / 樣本 = 500 kS/s**（所有通道共用，round-robin 時要平分）。
- 模式：one-shot（`CS.START_ONCE`）、free-running（`CS.START_MANY`，由 DIV 定速）。
- FIFO（深度 8 筆 ⚠️未查證），可觸發 IRQ（`ADC_IRQ_FIFO` = 35）或 DMA（`DREQ_ADC` = 48）；滿了會設 `FCS.OVER`，之後的樣本**直接丟失**。
- `FCS.SHIFT`：右移成 8 bit（方便 DMA 到 byte 陣列）；`FCS.ERR`：在樣本裡帶 conversion error 旗標（有錯誤的樣本要丟掉）。
- 切換 AINSEL 不需要 settling time；ADC 輸入是電容性（約 1 pF），等效阻抗 > 100 kΩ。
- 輸入電壓不可超過 IOVDD；使用 ADC 腳時應關掉該腳的數位功能（`adc_gpio_init` 會做）。
- RP2350 改善：移除 RP2040-E11 的 DNL 尖峰（§12.4.1）。沒有 ADC 相關的 RP2350 errata。

### 6.2 API

```c
void adc_init(void);                                   // 重置 ADC、致能、等 READY
static inline void adc_gpio_init(uint gpio);           // GPIO_FUNC_NULL + 關 pull + 關 IE（數位輸入）
static inline void adc_select_input(uint input);       // 「通道號」0..NUM_ADC_CHANNELS-1，不是 GPIO 號
static inline uint adc_get_selected_input(void);
static inline uint16_t adc_read(void);                 // one-shot：觸發 + 忙等 READY（約 2 µs）+ 讀 RESULT
static inline void adc_set_temp_sensor_enabled(bool enable);
static inline void adc_set_round_robin(uint input_mask);   // 0 = 關閉
static inline void adc_set_clkdiv(float clkdiv);        // free-running 取樣間隔 = clkdiv + 1 個 clk_adc
static inline void adc_run(bool run);                   // START_MANY
static inline void adc_fifo_setup(bool en, bool dreq_en, uint16_t dreq_thresh, bool err_in_fifo, bool byte_shift);
static inline bool adc_fifo_is_empty(void);
static inline uint8_t adc_fifo_get_level(void);
static inline uint16_t adc_fifo_get(void);
static inline uint16_t adc_fifo_get_blocking(void);
static inline void adc_fifo_drain(void);
static inline void adc_irq_set_enabled(bool enabled);
// 溫度通道號：ADC_TEMPERATURE_CHANNEL_NUM（= NUM_ADC_CHANNELS - 1）
```

取樣率公式（free-running）：

```
DIV = 0            → 每 96 cycle 一次 → 500 kS/s
DIV = n（n ≥ 96）  → 每 n + 1 個 clk_adc 一次 → fs = 48 MHz / (n + 1)
adc_set_clkdiv(48e6f / fs - 1);    例：fs = 10 kS/s → 4799；1 kS/s → 47999；100 kS/s → 479
round-robin k 個通道 → 每通道 fs / k
```

### 6.3 範例

One-shot + 溫度：

```c
#include <stdio.h>
#include "pico/stdlib.h"
#include "hardware/adc.h"
int main(void) {
    stdio_init_all();
    adc_init();
    adc_gpio_init(26);                       // ch0
    adc_set_temp_sensor_enabled(true);       // 溫度感測器偏壓（多約 40 µA）
    while (true) {
        adc_select_input(0);
        uint16_t raw = adc_read();           // 0..4095
        float v = raw * 3.3f / 4096.0f;      // 假設 ADC 參考 = 3.3 V（Pico 2 板上 ADC_AVDD）
        adc_select_input(ADC_TEMPERATURE_CHANNEL_NUM);   // A 封裝 = 4
        float vt = adc_read() * 3.3f / 4096.0f;
        float temp_c = 27.0f - (vt - 0.706f) / 0.001721f;  // datasheet 典型值，需校正才準
        printf("%.3f V  %.1f C\n", v, temp_c);
        sleep_ms(500);
    }
}
```

Free-running + round-robin + DMA（兩通道各 100 kS/s）：

```c
#include "hardware/adc.h"
#include "hardware/dma.h"
#define N 2048
static uint16_t buf[N];                       // 交錯：ch0, ch1, ch0, ch1, ...

void adc_capture(void) {
    adc_init();
    adc_gpio_init(26); adc_gpio_init(27);
    adc_select_input(0);                       // 第一個樣本從 ch0 開始
    adc_set_round_robin((1u << 0) | (1u << 1));
    adc_fifo_setup(true,  /* 寫入 FIFO */
                   true,  /* 開 DREQ */
                   1,     /* 1 筆就觸發 DREQ */
                   false, /* 不帶 ERR bit */
                   false  /* 不右移，保留 12 bit */);
    adc_set_clkdiv(48000000.0f / 200000.0f - 1.0f);   // 總取樣率 200 kS/s

    int ch = dma_claim_unused_channel(true);
    dma_channel_config c = dma_channel_get_default_config(ch);
    channel_config_set_transfer_data_size(&c, DMA_SIZE_16);
    channel_config_set_read_increment(&c, false);
    channel_config_set_write_increment(&c, true);
    channel_config_set_dreq(&c, DREQ_ADC);
    dma_channel_configure(ch, &c, buf, &adc_hw->fifo, N, true);   // 先啟動 DMA

    adc_run(true);                             // 再啟動 ADC
    dma_channel_wait_for_finish_blocking(ch);
    adc_run(false);
    adc_fifo_drain();                          // datasheet：停止後等 READY、把殘留樣本清掉
    adc_set_round_robin(0);
}
```

順序重點（§12.4.3.5）：設好速率 → 先開 DMA → 再 `adc_run(true)`；結束 `adc_run(false)` → 清 FIFO。8-bit 模式（`byte_shift=true` + `DMA_SIZE_8`）緩衝區大小減半。

### 6.4 ADC 雜訊與精度

| 原因 | 對策 |
|---|---|
| ENOB 只有 9.2 bit | 過取樣平均：平均 4^k 筆約多 k bit（雜訊夠隨機時）；或中位數濾波 |
| 數位腳干擾 | 用 `adc_gpio_init`（關 IE / pull）；ADC 腳附近不要切換大電流 |
| 電源漣波 | Pico 2 的 GPIO23 控制板上 SMPS 模式（`pico2.h`），拉高改 PWM 模式可降低漣波 ⚠️（Pico 1 datasheet 的建議，Pico 2 未驗證） |
| 訊號源阻抗高 / 取樣太快 | 降低取樣率或加緩衝；DC 量測通常不需要 |
| conversion error | `err_in_fifo = true`，丟掉帶 ERR 的樣本 |
| FIFO overflow | DMA 或提高 FIFO 讀取頻率；檢查 `adc_hw->fcs & ADC_FCS_OVER_BITS` |

---

## 7. Timer、Alarm、Watchdog（datasheet §12.8、§12.9）

基本時間 API（`time_us_64`、`sleep_ms`、`add_alarm_in_ms`、`add_repeating_timer_ms` 等）見 `pico-sdk.md` §7.3 與 `multicore-sync.md` B13。

### 7.1 硬體

- **兩個 timer：TIMER0、TIMER1**（RP2040 一個），各自：64-bit 計數器（每 µs +1，實務上不會溢位）+ **4 個 alarm**（比對低 32 bit → 最遠約 72 分鐘）。
- 讀 64-bit：先讀 TIMELR 再讀 TIMEHR（讀 L 會閂鎖 H）；SDK `time_us_64()` 已處理。
- 每個 alarm 一條 IRQ：`TIMER0_IRQ_0..3` = 0–3、`TIMER1_IRQ_0..3` = 4–7（RP2040 名稱 `TIMER_IRQ_n` 在 RP2350 不存在）。
- RP2350 新增 SOURCE 暫存器可讓 timer 改數 clk_sys（SDK 預設仍數 1 µs tick）。
- 其他計時資源：PWM slice（12 個 16-bit）、PIO SM、DMA pacing timer（4 個）、M33 SysTick、SIO 的 RISC-V platform timer（`SIO_IRQ_MTIMECMP`）、POWMAN AON timer（ms 等級，低功耗）。

### 7.2 hardware_alarm（低階，一個 alarm 一個 callback）

```c
typedef void (*hardware_alarm_callback_t)(uint alarm_num);
int  hardware_alarm_claim_unused(bool required);        // 回傳 alarm 號；預設 TIMER0
void hardware_alarm_claim(uint alarm_num);
void hardware_alarm_unclaim(uint alarm_num);
void hardware_alarm_set_callback(uint alarm_num, hardware_alarm_callback_t callback); // 在「呼叫的這顆核」裝 IRQ
bool hardware_alarm_set_target(uint alarm_num, absolute_time_t t);   // 回傳 true = 目標已過（missed）
void hardware_alarm_cancel(uint alarm_num);
void hardware_alarm_force_irq(uint alarm_num);
// 指定 timer 的版本：timer_hardware_alarm_claim_unused(timer1_hw, true) 等（前綴 timer_，多一個 timer_hw_t* 參數）
```

- **default alarm pool 占用 TIMER0 的 alarm 3**（`PICO_TIME_DEFAULT_ALARM_POOL_HARDWARE_ALARM_NUM` = 3），`sleep_ms`、`add_alarm_*` 都靠它 → 自己用請 `hardware_alarm_claim_unused(true)`，不要寫死 3。

精準週期（以「上一次目標時間」累加，不累積誤差）：

```c
#include "pico/stdlib.h"
#include "hardware/timer.h"
#define PERIOD_US 1000
static absolute_time_t next;
static int alarm;
static volatile uint32_t ticks;

static void on_alarm(uint a) {
    ticks++;                                   // 工作越短越好
    next = delayed_by_us(next, PERIOD_US);
    hardware_alarm_set_target(a, next);        // 重新設定下一次
}
void start_tick(void) {
    alarm = hardware_alarm_claim_unused(true);
    hardware_alarm_set_callback(alarm, on_alarm);
    next = make_timeout_time_us(PERIOD_US);
    hardware_alarm_set_target(alarm, next);
}
```

### 7.3 pico_time（alarm pool，高階）

```c
typedef int64_t (*alarm_callback_t)(alarm_id_t id, void *user_data);
//   回傳 0：不重複；>0：從「callback 返回時」起再等該 µs；<0：從「上次預定時間」起再等 |值| µs
alarm_id_t add_alarm_in_us(uint64_t us, alarm_callback_t callback, void *user_data, bool fire_if_past);
alarm_id_t add_alarm_in_ms(uint32_t ms, alarm_callback_t callback, void *user_data, bool fire_if_past);
alarm_id_t add_alarm_at(absolute_time_t time, alarm_callback_t callback, void *user_data, bool fire_if_past);
//   回傳 >0：id；0：時間已過且 fire_if_past=false；<0：沒有空槽（預設 pool 最多 16 個，PICO_TIME_DEFAULT_ALARM_POOL_MAX_TIMERS）
bool cancel_alarm(alarm_id_t alarm_id);

typedef bool (*repeating_timer_callback_t)(repeating_timer_t *rt);   // 回 true 繼續
bool add_repeating_timer_us(int64_t delay_us, repeating_timer_callback_t callback, void *user_data, repeating_timer_t *out);
bool add_repeating_timer_ms(int32_t delay_ms, repeating_timer_callback_t callback, void *user_data, repeating_timer_t *out);
bool cancel_repeating_timer(repeating_timer_t *timer);
```

**`delay_us` 正負號**（照 `time.h` 註解）：

| 值 | 意義 | 實際週期 |
|---|---|---|
| `> 0` | 上一次 callback **結束**到下一次**開始**的間隔 | 間隔 + callback 執行時間（會漂移） |
| `< 0` | 兩次 callback **開始**之間的間隔為 `-delay_us` | 固定頻率（要定速取樣用這個） |
| `0` | 當作 1 | |

```c
static repeating_timer_t rt;                         // static：不能放 stack
static volatile bool sample_due;
static bool on_tick(repeating_timer_t *t) { sample_due = true; return true; }
add_repeating_timer_us(-100, on_tick, NULL, &rt);    // 10 kHz，固定頻率
```

### 7.4 Callback 規則（alarm / repeating timer / hardware_alarm 都一樣）

- 在 **timer IRQ context** 執行，在**建立 pool 的那顆核**（預設 pool 在 core 0）。
- 要**短**：不要 `printf`（慢、可能取鎖）、不要 `sleep_*`、不要等 I/O；設旗標、推 queue 就回來。
- 同一個 pool 的 callback 依序執行，一個卡住，其他 alarm 全部延後。
- callback 裡可以再呼叫 `add_alarm_*`（SDK 註明 IRQ 安全）。
- 和主程式共享資料用 `volatile` / 關中斷 / atomic（`multicore-sync.md` B8）。

### 7.5 busy_wait vs sleep

| | `sleep_us/ms/until` | `busy_wait_us/ms/until`、`busy_wait_us_32` |
|---|---|---|
| 作法 | 設 alarm 後 WFE 等待（低功耗） | 讀 timer 忙等 |
| IRQ 內可用 | **不可**（會死結 / assert） | 可以（但會卡住整個 ISR，盡量不要） |
| 精準度 | 受 IRQ 喚醒延遲影響 | 較準（仍會被中斷打斷） |
| 短延遲 | 有額外開銷 | 適合 µs 等級 |
| 更短（數十 ns） | — | `busy_wait_at_least_cycles(n)`（`pico/platform.h`，「至少」n cycle） |

### 7.6 Watchdog（`hardware/watchdog.h`，CMake `hardware_watchdog`）

```c
void watchdog_enable(uint32_t delay_ms, bool pause_on_debug);   // RP2350 最大約 16777 ms（RP2040 8388 ms）
void watchdog_update(void);                                       // 餵狗：重新載入計數
void watchdog_disable(void);
bool watchdog_caused_reboot(void);          // 上次重開是 watchdog 觸發（RP2350 版另要求 bootrom 回報 boot type 為 normal）
bool watchdog_enable_caused_reboot(void);   // 更嚴格：是 watchdog_enable 之後的逾時造成的（看 scratch[4] 魔數）
void watchdog_reboot(uint32_t pc, uint32_t sp, uint32_t delay_ms);   // 主動重開
uint32_t watchdog_get_time_remaining_ms(void);
```

```c
if (watchdog_enable_caused_reboot()) printf("上次卡死被 watchdog 重開\n");
watchdog_enable(500, true);          // 500 ms 沒餵就重開；接除錯器暫停時不計
while (true) { work(); watchdog_update(); }
```

- 8 個 watchdog scratch 暫存器可跨 soft reset 保存；只有 watchdog 被設成觸發 chip-level reset（POWMAN_WATCHDOG）或 RUN pin / 斷電時才清掉。SDK 的 `watchdog_enable` 走 PSM_WDSEL（非 chip-level），所以能用 scratch[4] 記錄魔數（細節 §12.9.4–12.9.5）。
- 在 OJ / 自動測試環境，watchdog 可避免卡死吃掉時間；但別在長時間初始化前開。

---

## 8. 中斷深入（datasheet §3.2、`hardware/irq.h`）

基本範例見 `pico-sdk.md` §7.5；ISR 與主程式共享變數見 `multicore-sync.md` B8。

### 8.1 架構

| | Cortex-M33（Arm 模式） | Hazard3（RISC-V 模式） |
|---|---|---|
| 中斷控制器 | NVIC（每核一個） | Xh3irq（每核一個，CSR：MEIEA / MEIPA / MEIFA / MEIPRA / MEINEXT / MEICONTEXT） |
| 外部 IRQ 數 | 52（0–45 有接，46–51 = `SPARE_IRQ_0..5`，給軟體自觸發） | 同 |
| 優先權 | 8-bit 欄位只有**高 4 bit 有效** → 16 級 | 16 級 pre-emption |
| 分派 | 硬體向量表直接跳 handler | 單一 `mip.meip` 入口 + 軟體分派（SDK `isr_riscv_machine_external_irq`，讀 MEINEXT 找 IRQ 再呼叫 C handler） |
| SDK API | `hardware_irq` 兩邊相同（RISC-V 也用「數字越小越優先」的 Arm 慣例） | 同 |

- RP2040：NVIC 32 條（26 條有接），優先權只有高 2 bit。
- 同優先權同時 pending：IRQ 號小的先（§3.2；IRQ 編號大致依重要性排）。
- 支援巢狀：高優先權可搶占低優先權 handler。
- 延遲：M33 有硬體自動堆疊；Hazard3 經軟體分派多一些指令 → RISC-V 模式的 IRQ 進入延遲通常較長 ⚠️未量測具體 cycle 數，要數字請用 GPIO 翻轉 + 邏輯分析儀量（`pico-sdk.md` §10.4）。

### 8.2 IRQ 號（RP2350，`regs/intctrl.h`，一律用名稱）

| # | 名稱 | # | 名稱 | # | 名稱 |
|---|---|---|---|---|---|
| 0–3 | `TIMER0_IRQ_0..3` | 15–20 | `PIO0/1/2_IRQ_0/1` | 33/34 | `UART0_IRQ` / `UART1_IRQ` |
| 4–7 | `TIMER1_IRQ_0..3` | 21 | `IO_IRQ_BANK0`（core-local） | 35 | `ADC_IRQ_FIFO` |
| 8/9 | `PWM_IRQ_WRAP_0/1` | 25 | `SIO_IRQ_FIFO`（core-local） | 36/37 | `I2C0_IRQ` / `I2C1_IRQ` |
| 10–13 | `DMA_IRQ_0..3` | 26 | `SIO_IRQ_BELL`（core-local） | 39 | `TRNG_IRQ` |
| 14 | `USBCTRL_IRQ` | 29 | `SIO_IRQ_MTIMECMP`（core-local） | 31/32 | `SPI0_IRQ` / `SPI1_IRQ` |
| 46–51 | `SPARE_IRQ_0..5`（軟體用） | 30 | `CLOCKS_IRQ` | 38 | `OTP_IRQ` |

### 8.3 API

```c
typedef void (*irq_handler_t)(void);
void irq_set_exclusive_handler(uint num, irq_handler_t handler);   // 該 IRQ 已有任何 handler 會 assert
void irq_add_shared_handler(uint num, irq_handler_t handler, uint8_t order_priority);
void irq_remove_handler(uint num, irq_handler_t handler);
bool irq_has_handler(uint num);
void irq_set_enabled(uint num, bool enabled);          // 只影響「呼叫的這顆核」
bool irq_is_enabled(uint num);
void irq_set_mask_enabled(uint32_t mask, bool enabled);          // IRQ 0..31
void irq_set_mask_n_enabled(uint n, uint32_t mask, bool enabled); // n=1 → IRQ 32..63
void irq_set_priority(uint num, uint8_t hardware_priority);      // 0x00 最高 … 0xff 最低；預設 0x80
uint irq_get_priority(uint num);
void irq_set_pending(uint num);                                   // 軟體觸發
static inline void irq_clear(uint int_num);
int  user_irq_claim_unused(bool required);                        // 取得一個 SPARE_IRQ（user IRQ）
void user_irq_unclaim(uint irq_num);
// 常數：PICO_HIGHEST_IRQ_PRIORITY 0x00、PICO_DEFAULT_IRQ_PRIORITY 0x80、PICO_LOWEST_IRQ_PRIORITY 0xff
//       PICO_SHARED_IRQ_HANDLER_DEFAULT_ORDER_PRIORITY 0x80、..._HIGHEST_ORDER_PRIORITY 0xff、..._LOWEST_ORDER_PRIORITY 0x00
```

| | exclusive | shared |
|---|---|---|
| 用途 | 一個 IRQ 只有一個來源 / 要最低延遲 | 多個來源共用一條（GPIO、DMA、PIO 常見） |
| 開銷 | 最低 | 依序呼叫鏈上每個 handler；每個 handler 要檢查是不是自己的事件 |
| 排序 | — | `order_priority` **數字大的先被呼叫**（與 `irq_set_priority` 相反！） |
| 上限 | — | 全部 shared handler 合計 `PICO_MAX_SHARED_IRQ_HANDLERS`（預設 4） |

- SDK 預設兩核**共用同一張向量表**：handler 對兩核都生效；同一 IRQ 號在兩核都 enable 時，handler 內用 `get_core_num()` 分辨。
- **非 core-local 的 IRQ（UART、SPI、DMA、PWM、TIMER…）只在一顆核 enable**，否則兩核搶同一個事件。
- 哪顆核處理 = 在哪顆核呼叫 `irq_set_enabled`（`gpio_set_irq_enabled_with_callback`、`hardware_alarm_set_callback` 也是「呼叫者那顆核」）。想讓 core 1 處理，就在 core 1 的程式裡初始化。
- `irq_set_exclusive_handler` assert 失敗 → 該 IRQ 已被別人裝了 handler（例如某個 SDK 函式庫）→ 改用 shared 或換一條 IRQ（DMA 有 4 條、PWM / PIO 各 2 條）。

### 8.4 寫好 ISR 的規則

1. **先清週邊的中斷旗標**（PWM 寫 INTR、GPIO edge acknowledge、UART 讀空 FIFO、DMA 寫 INTS），否則一離開又進來。
2. **短**：搬資料、設旗標、推 ring buffer / `queue_t`（`queue_try_add`，不阻塞）。
3. 不要 `printf`、`sleep_*`、malloc、可能長時間持有的 mutex。
4. 時間關鍵的 ISR 加 `__not_in_flash_func(name)` 放 RAM（避免 XIP cache miss）。
5. 共享變數 `volatile`；多欄位或 read-modify-write → 主程式那邊 `save_and_disable_interrupts()` / `restore_interrupts()`；跨核 → `critical_section_t` / atomic / `queue_t`。
6. 優先權只在真的需要時調：讓「資料會丟」的（UART RX、高速 ADC 非 DMA）比「只是慢一點」的高。

延後處理（bottom half）：SPARE_IRQ 讓高優先權 ISR 把較重的工作丟到低優先權中斷執行（datasheet §3.2 的建議用法）：

```c
#include "hardware/irq.h"
static int bh_irq;
static volatile uint32_t pending_work;

static void bottom_half(void) {          // 低優先權：可做較多事（仍不要 printf）
    uint32_t w = pending_work;
    pending_work = 0;
    (void)w; /* 處理 */
}
static void top_half(void) {             // 高優先權：只記錄、觸發
    /* 清週邊旗標、讀資料 */
    pending_work++;
    irq_set_pending(bh_irq);
}
void setup(void) {
    bh_irq = user_irq_claim_unused(true);
    irq_set_exclusive_handler(bh_irq, bottom_half);
    irq_set_priority(bh_irq, PICO_LOWEST_IRQ_PRIORITY);
    irq_set_enabled(bh_irq, true);
}
```

（`pending_work++` 在 top half、`= 0` 在 bottom half；兩者優先權不同會互相搶占，正式使用時讀改寫要保護或改成只增不減的計數器。這裡示意結構。）

---

## 9. RP2350 新增週邊（簡介與指標）

| 週邊 | 重點 | SDK / 範例 |
|---|---|---|
| **HSTX**（§12.11） | 只輸出；GPIO 12–19（8 腳）；DDR，每腳每 clk_hstx 2 bit；clk_hstx 最高 150 MHz → 300 Mb/s/腳；8×32-bit 非同步 FIFO 給 DMA（`DREQ_HSTX` 52）；有 command expander（TMDS 編碼、重複）、bit crossbar；用於 DVI、高速並列輸出 | `hardware/structs/hstx_ctrl.h`、`hstx_fifo.h`（無高階 API）；pico-examples `hstx/dvi_out_hstx_encoder`、`hstx/spi_lcd` |
| **TRNG**（§12.12） | Arm TRNG，每次產生 192 bit；約 7.5 kb/s（150 MHz）；產生時間不固定，偶爾超過平均 100 倍 | `pico/rand.h`（CMake `pico_rand`）：`uint32_t get_rand_32(void)`、`uint64_t get_rand_64(void)`、`void get_rand_128(rng_128_t *)`。這是**軟體 PRNG（xoroshiro128**）＋硬體熵混入**，RP2350 預設以 TRNG 為熵源；首次呼叫要約 1 ms seed，之後約 10–20 µs/次；可在 IRQ 與兩核呼叫但可能阻塞數 µs |
| **SHA-256**（§12.13） | 硬體 SHA-256；每 512-bit block 121 cycle → 150 MHz 時最高 79.3 MB/s（用 DMA 32-bit 寫）；軟體需自行 padding（`pico_sha256` 會做）；`DREQ_SHA256` 54 | 高階 `pico/sha256.h`（`pico_sha256_start_blocking`、`pico_sha256_update`、`pico_sha256_finish`）；低階 `hardware/sha256.h`；範例 `sha/sha256` |
| Flash / XIP | 寫 flash 前要停 XIP 存取（另一核也要停） | `hardware/flash.h`、`pico/flash.h`（`flash_safe_execute`）；範例 `flash/` ⚠️細節未查 |
| OTP | 8 KB OTP，存金鑰/設定；寫入**不可逆** | `pico/bootrom.h` 的 `rom_func_otp_access()`、範例 `otp/`；考試不要碰 |
| AON timer / POWMAN | 低功耗計時、休眠喚醒 | `pico/aon_timer.h`；範例 `low_power/` |

---

## 10. 效能角度：polling vs IRQ vs DMA

### 10.1 決策表

| 情境 | 建議 | 理由 |
|---|---|---|
| 少量、偶發、延遲不敏感 | polling（查狀態旗標） | 程式最簡單、沒有中斷開銷 |
| 不定時到達的事件（按鍵、UART RX） | IRQ | CPU 不必一直查；延遲 = 中斷延遲 |
| 每筆資料都觸發 IRQ 且速率高（> 數十萬筆/秒） | DMA（+ 完成 IRQ） | 每次中斷要進出 handler，速率高時 CPU 全耗在 ISR |
| 固定長度大量傳輸（SPI 顯示、ADC 擷取、UART dump） | DMA | 零 CPU，線速 |
| 需要逐筆判斷內容（協定解析） | IRQ 收進 buffer，主迴圈批次解析 | 解析與接收解耦 |
| 精準時序輸出 | PWM / PIO / DMA+DREQ | 硬體定時，不受軟體抖動影響 |

### 10.2 各週邊速查

| 週邊 | FIFO 深度 | DMA DREQ | 最大線速（150 MHz） | 主要優化 |
|---|---|---|---|---|
| UART | 32 | 28–31 | 9.375 Mbaud | 提高鮑率、二進位格式、DMA TX、IRQ+ring RX |
| SPI | 8 | 24–27 | 75 MHz（公式值） | DMA TX+RX、16-bit frame、burst 讀、手動 CS 包整個交易 |
| I2C | 16 | 44–47 | 1 Mbit/s | 400k/1M、burst 讀、timeout 版 API |
| PWM | 雙緩衝 CC/TOP | 32–43（wrap） | 75 MHz（TOP=1） | DMA 寫 CC 產生波形、wrap IRQ 當 timer |
| ADC | 8 | 48 | 500 kS/s 總和 | free-running + DMA、8-bit shift 省空間、round-robin |
| GPIO | — | 無（SIO 不可 DMA） | — | `gpio_put_masked` / `sio_hw->gpio_togl` 一次多腳；高速 → PIO |

### 10.3 通用手法

- **讓 FIFO 發揮作用**：一次把 FIFO 讀空 / 填滿（`while (readable) read;`），而不是每次中斷只處理一筆。
- **批次化**：收一整塊再處理；`printf` 改成收集到 buffer 最後一次輸出。
- **重疊**：DMA 傳上一塊時 CPU 處理下一塊（ping-pong，`pico-dma.md` §4.6）。
- **把等待移出關鍵路徑**：`uart_write_blocking` → DMA；`adc_read` 一次 2 µs 忙等 → free-running + FIFO。
- **ISR 放 RAM、資料放 RAM**：`__not_in_flash_func`、避免 flash cache miss。
- **先量再改**：GPIO 翻轉 + 邏輯分析儀，或 `time_us_64()` 包住重複 N 次的區段（`pico-sdk.md` §10）。

---

## 11. 如何讀一個新的週邊章節（datasheet 閱讀法）

1. **Overview / feature 清單**：數量、FIFO 深度、資料寬度、最大速率。先看「**Changes from RP2040**」小節（網路上的範例多半是 RP2040）。
2. **時脈**：週邊用 clk_sys、clk_peri、clk_adc 還是 1 µs tick？速率公式（分頻器幾 bit、是否 `+1`）全從這裡來。
3. **腳位**：§9.4 Table 677 找 FUNCSEL（F1–F11）；確認你的 GPIO 真的有這個功能。
4. **Programmer's model / Operation**：初始化順序（reset → 設定 → enable）、哪些欄位要在 disable 時才能改。
5. **中斷**：§3.2 Table 95 查 IRQ 號；看「怎麼清」：寫 1 清（WC）、讀資料清、或寫 INTR。
6. **DMA**：§12.6.4 Table 1254 查 DREQ 號；看資料寬度與 FIFO 門檻。
7. **List of registers**：看 Reset 值、欄位型別（Appendix A：RW、RO、WO、SC 自清、WC 寫 1 清、RF/WF/RWF FIFO）。RP2350 的 IO 暫存器有原子 set/clr/xor 別名（`hw_set_bits` 等，`pico-sdk.md` §2.2）；8/16-bit 寫會被複製到整個 32 bit（§2.1.5）。
8. **Errata（Appendix D）**：搜尋週邊名稱與你的 stepping（A2/A3/A4）。
9. **對照 SDK**：`src/rp2_common/hardware_<name>/include/hardware/<name>.h`（API 與註解）+ `<name>.c`（實際暫存器操作，最好的「datasheet 白話翻譯」）+ pico-examples 對應資料夾。
10. **寫最小測試**：先讓一個 byte / 一個 pulse 出來（示波器、邏輯分析儀、loopback），再加功能、再優化。

給 LLM 的提問技巧：貼「暫存器表 + Operation 小節」原文，請它「列出初始化步驟對應的暫存器寫入，並對照 SDK 函式」。

---

## 12. 症狀 → 原因 對照表

| 症狀 | 最可能原因 | 檢查 / 修法 |
|---|---|---|
| UART 完全沒輸出 | 沒 `gpio_set_function(…, GPIO_FUNC_UART)`；腳位不屬於該 UART（GP4/5 是 uart1 不是 uart0） | 查 Table 677；`UART_FUNCSEL_NUM` |
| UART 亂碼 | 鮑率 / 格式不一致；`uart_init` 之後才 `set_sys_clock_khz`（clk_peri 改變） | 雙方 8N1 + 同鮑率；先改時脈再 init；印 `uart_init` 回傳值 |
| UART 有 TX 沒 RX | TX/RX 對接錯（要交叉）、沒共地、RX 腳選錯 | TX→對方 RX、RX←對方 TX、GND 相連 |
| `printf` 和自己的 UART 資料混在一起 | `pico_enable_stdio_uart` 占用 uart0 | 改用 USB stdio 或 uart1 |
| UART 收資料掉 byte | ISR 太慢 / 在 ISR 裡 printf；只讀一筆就離開；FIFO 被關 | ISR 讀空 FIFO；ring buffer；DMA |
| 單一 byte 收到但 IRQ 晚觸發 | RX 門檻 ≥ 4 筆，單筆靠 32 bit 時間的 RX timeout | 正常現象；要更即時就關 FIFO（`uart_set_fifo_enabled(false)`） |
| SPI 讀回全 0xFF / 0x00 | MISO 腳沒設 SPI 功能；CS 沒拉低；SPI mode 錯 | SPIx **RX** = MISO；確認 CPOL/CPHA；邏輯分析儀看 SCK |
| SPI CS 在每個 byte 之間跳高 | 用硬體 CSn + CPHA=0（PL022 行為） | CS 改 GPIO 手動控制 |
| SPI 最後一個 byte 被截斷 | DMA TX 完成就拉高 CS，但還在移位 | 等 RX DMA 完成或 `while (spi_is_busy())` |
| I2C 卡住不返回 | 沒有 pull-up / SDA 被拉住；用了非 timeout API | 加 pull-up（外部 4.7 kΩ）；用 `_timeout_us`；必要時手動打 9 個 SCL 釋放匯流排 |
| I2C 回 `PICO_ERROR_GENERIC` | 位址 NAK：位址錯（傳了 8-bit 位址）、元件沒電、SDA/SCL 接反 | 先跑 bus scan；7-bit 位址 |
| I2C 讀暫存器值錯 | 寫位址時 `nostop=false`（有些元件 STOP 後重置指標） | 寫位址用 `nostop=true` 再讀 |
| PWM 頻率差一點 | `wrap = 週期` 沒減 1；phase-correct 頻率減半；`pwm_set_clkdiv` 小數被捨去 | `TOP = 週期 − 1`；用整數 `int_frac4` |
| PWM 沒輸出 | 沒 `GPIO_FUNC_PWM`；slice 沒 enable；`pwm_set_mask_enabled` 把別的 slice 關了；改錯 channel | `pwm_gpio_to_slice_num/channel`；檢查 EN |
| 同 slice 的兩腳頻率互相影響 | A/B 共用 TOP 與分頻 | 不同頻率要用不同 slice |
| PWM 一直 100% | `level > TOP`（≥ TOP+1 就是 100%） | level 範圍 0..TOP+1 |
| PWM 用 DMA 寫 CC，A/B 變一樣 | 16-bit 寫被複製到兩半 | 用 32-bit 寫 `(B<<16)|A` |
| ADC 讀值跳動大 | ENOB 9.2；電源雜訊；沒用 `adc_gpio_init` | 過取樣平均；關數位輸入；降低取樣率 |
| ADC 讀到別的腳 | `adc_select_input(26)`（傳了 GPIO 號） | 傳通道號 0–3（A）/ 0–7（B） |
| ADC DMA 資料錯位 / 缺 | FIFO overflow（`FCS.OVER`）；先開 ADC 才開 DMA；round-robin 起始通道不明 | 先 DMA 後 `adc_run`；`adc_select_input` 設起始；結束 drain |
| 溫度值離譜 | 沒 `adc_set_temp_sensor_enabled(true)`；選錯通道（B 封裝是 8） | `ADC_TEMPERATURE_CHANNEL_NUM`；需個體校正 |
| GPIO 浮接 + pull-down 卻讀到 1 | RP2350-E9（A2 stepping；A4 已修） | 改 pull-up 邏輯或外接 ≤ 8.2 kΩ 下拉 |
| 直接寫暫存器的 GPIO 沒反應 | ISO 未清、IE=0（RP2350 預設） | 用 `gpio_set_function()` 或自己清 ISO、設 IE |
| 按一次按鍵觸發多次 | 彈跳；用了 level IRQ（持續觸發） | 軟體去彈跳；用 edge |
| GPIO IRQ 在 core 1 不觸發 | GPIO IRQ 是 per-core；在 core 0 設定的 | 在要處理的那顆核呼叫設定函式 |
| alarm / timer callback 讓系統卡住 | callback 裡 printf / sleep / 長迴圈 | callback 只設旗標 |
| repeating timer 跑幾次就停 / 亂跳 | `repeating_timer_t` 放在 stack 上；callback 回 false | 用 `static`；回 true |
| 定速取樣頻率漂移 | `add_repeating_timer_us` 用了正數 | 用負數（固定 start-to-start） |
| 在 ISR 呼叫 `sleep_ms` 當機 | sleep 依賴 alarm IRQ | ISR 內用 `busy_wait_us` 或改設計 |
| `hardware_alarm_claim(3)` assert | 預設 alarm pool 已占 alarm 3 | `hardware_alarm_claim_unused(true)` |
| 莫名其妙重開機 | watchdog 沒餵、逾時 > 16.7 s 被截、除錯暫停 | `watchdog_enable_caused_reboot()` 確認；縮短工作或加餵狗點 |
| `irq_set_exclusive_handler` assert | 該 IRQ 已有 handler | 改 `irq_add_shared_handler` 或換 IRQ（DMA_IRQ_1..3） |
| 一進 ISR 就出不來 / CPU 100% | 沒清週邊中斷旗標 | 照各週邊規則清（WC、讀 FIFO、acknowledge） |
| 主迴圈看不到 ISR 改的變數 | 沒 `volatile`，編譯器把讀取提到迴圈外 | `volatile`（或 atomic） |
| RISC-V 版比 Arm 版中斷反應慢 | Hazard3 軟體分派 | 時間關鍵改 PIO/DMA；ISR 放 RAM；量測確認 |

---

## 13. 除錯檢查清單

- [ ] CMake 有 link 對應函式庫（`hardware_spi`、`hardware_i2c`、`hardware_pwm`、`hardware_adc`、`hardware_dma`、`hardware_watchdog`、`pico_i2c_slave`、`pico_rand`；`hardware_gpio`、`hardware_uart`、`pico_time` 已在 `pico_stdlib` 內）。
- [ ] 每支腳都 `gpio_set_function` 成正確功能（CS 例外用 SIO）；查 Table 677 該腳真的有這個週邊實例（uart0 vs uart1、spi0 vs spi1、i2c0 vs i2c1）。
- [ ] 印出 `uart_init` / `spi_init` / `i2c_init` 的回傳值（實際速率）。
- [ ] 時脈：`clock_get_hz(clk_sys)`、`clock_get_hz(clk_peri)`；改時脈要在週邊 init 之前。
- [ ] I2C 有 pull-up；用 `_timeout_us` 版本；位址是 7-bit；先跑 bus scan。
- [ ] SPI mode（CPOL/CPHA）與元件一致；CS 手動；MISO=RX、MOSI=TX。
- [ ] PWM：`TOP = 週期 − 1`；同 slice 共用頻率；slice 有 enable。
- [ ] ADC：`adc_select_input` 用通道號；`adc_gpio_init`；DMA 先於 `adc_run`。
- [ ] IRQ：在正確的核設定；清週邊旗標；handler 沒有被重複安裝；優先權合理。
- [ ] callback / ISR 內沒有 printf / sleep / 阻塞。
- [ ] 共享變數 `volatile`；多欄位更新有保護。
- [ ] 板子 stepping（E9：A2 有、A4 已修）；輸入用 pull-up 優先。
- [ ] 用邏輯分析儀 / 示波器 / loopback（UART TX 接 RX、SPI 開 `SPI_SSPCR1_LBM_BITS` 內部 loopback，pico-examples `spi_dma` 用法）隔離硬體與軟體問題。

## 14. 優化檢查清單

- [ ] 先量測：哪一段是瓶頸？等線速、等 CPU 還是等中斷？
- [ ] 線速瓶頸 → 提高鮑率 / SCK / I2C 速度（在元件允許內）、減少傳輸量（二進位、burst、少 printf）。
- [ ] CPU 在忙等 → 改 IRQ 或 DMA，讓傳輸和運算重疊。
- [ ] IRQ 太頻繁 → 提高 FIFO 門檻、一次處理整個 FIFO、或改 DMA。
- [ ] ISR 太長 → 移到 bottom half / 主迴圈；ISR 放 RAM。
- [ ] ADC：`adc_read` 迴圈 → free-running + DMA。
- [ ] PWM 波形：IRQ 改 CC → DMA 改 CC。
- [ ] GPIO 多腳 → mask 一次寫；高速協定 → PIO。
- [ ] 計時用 hardware alarm 或負數 repeating timer，避免累積漂移。
- [ ] 每次改動後重新量測、確認結果正確（OJ 看輸出正確性優先）。

---

## 15. 向模型提問的範本

**範本 1：從 datasheet 章節寫驅動**
```
我在 RP2350（Pico 2, pico-sdk 2.x, {{Arm 或 RISC-V}}）上要使用 {{週邊名稱，例如 SPI1}}。
datasheet 相關段落如下：
{{貼上 Overview + Operation + 相關暫存器表}}
需求：{{例如：以 8 MHz、mode 3 讀取裝置的 0x0F 暫存器，CS 在 GP13}}。
請：1) 列出要用的 pico-sdk 函式與每個參數的值；2) 寫出最小可編譯的 C 程式（含 CMake target_link_libraries）；
3) 標出哪些地方你不確定、需要我查 datasheet 的哪一節確認。不要使用 RP2040 專用的名稱。
```

**範本 2：公式與參數計算**
```
clk_sys = {{150 MHz}}，clk_peri = {{150 MHz}}，clk_adc = 48 MHz。
我要 {{PWM 頻率 X Hz、duty 解析度至少 Y 階 / ADC 每通道 Z S/s、通道 {{...}} round-robin / UART 鮑率 B}}。
請用 datasheet 公式（PWM: f = f_sys/((TOP+1)(PH+1)(INT+FRAC/16))；ADC: fs = 48MHz/(DIV+1)；UART: BRD = clk/(16·baud)）
算出暫存器/SDK 參數、實際值與誤差，並逐步列出計算過程。
```

**範本 3：症狀除錯**
```
硬體：Pico 2（RP2350A），接線：{{腳位對照}}。
程式（節錄）：
{{貼程式}}
預期：{{...}}；實際：{{...}}（{{邏輯分析儀/輸出觀察}}）。
請依可能性排序列出原因，每個原因給一個可以在 5 分鐘內驗證的測試。
特別檢查：gpio_set_function、腳位是否屬於該週邊實例、時脈、pull-up、IRQ 在哪顆核、ISR 是否清旗標。
```

**範本 4：效能優化（polling → IRQ / DMA）**
```
目前用 {{polling / blocking API}} 處理 {{週邊}}，資料量 {{N bytes / 每秒 M 筆}}，量測到 {{T µs}}，瓶頸在 {{...}}。
限制：{{不可超頻 / 只能用 DMA 通道 X / 輸出格式固定}}。
請比較 polling、IRQ+ring buffer、DMA（含 chain/ring）三種改法的預期收益與風險，
選一個寫出完整改法，並說明如何用 time_us_64 或 GPIO 翻轉量測驗證。
```

**範本 5：讀懂新週邊**
```
以下是 RP2350 datasheet 中我不熟的週邊章節：{{貼上}}。
請整理成：時脈來源與速率公式、初始化步驟（對應暫存器欄位）、中斷與清除方式、DREQ、與 RP2040 的差異、
相關 errata，以及對應的 pico-sdk 標頭檔與函式（若你不確定 SDK 有沒有該函式，請明說）。
```

---

## 16. 未驗證 / 待確認事項

- ⚠️ SPI master 最高速率：SDK 公式為 clk_peri/2（150 MHz → 75 MHz），datasheet §12.3.4.4 文字寫 70.5 Mb/s，兩者不一致；以 `spi_init` 回傳值與實測為準。
- ⚠️ blocking SPI 在高 SCK 下是否出現 frame 間隙，未實測。
- ⚠️ 內建 pull-up / pull-down 阻值（datasheet 電氣特性章節）未查。
- ⚠️ IRQ 進入延遲的具體 cycle 數（M33 vs Hazard3）未查證，需實測。
- ⚠️ Pico 2 上 GPIO23（SMPS 模式）對 ADC 雜訊的效果，未在 Pico 2 文件中確認。
- ⚠️ `rp2350_chip_version()` 回傳值：SDK 註解為 A2→2、A3/A4→3，未在板上驗證。
- ⚠️ UART 接收端可容忍的鮑率誤差（±2–3%）為一般經驗值。
- ⚠️ Flash 寫入（`flash_safe_execute`）、OTP 細節只列指標。
