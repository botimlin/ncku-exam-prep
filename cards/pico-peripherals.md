# 貼上卡：RP2350 週邊（GPIO / UART / SPI / I2C / PWM / ADC / Timer / IRQ）
> 用法：一次只複製一張卡（兩條分隔線之間），貼進對話，再在下面寫你的問題。每張 ≤ 1200 字元。
> 來源：full/domain/pico-peripherals.md、lite/domain/pico-peripherals.md（詳細版）｜最後更新 2026-11

---

【參考卡｜RP2350 週邊 1/8｜通則、腳位對應、pad】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
RP2350（Pico 2 = RP2350A，30 GPIO），非 RP2040。pico-sdk 2.x。
最常犯的三個錯：
1. `uart_init` / `spi_init` / `i2c_init` **不會設腳位** → 一定要 `gpio_set_function(pin, GPIO_FUNC_UART/SPI/I2C/PWM)`。
2. 公式差一：PWM 週期 = TOP+1；ADC 取樣間隔 = DIV+1；UART 8N1 一個 byte = 10 bit。
3. 在 IRQ / alarm callback 裡 printf / sleep_ms / 長迴圈。
腳位規則（GPIO 0–29，查 datasheet Table 677）：
- I2C：`gpio % 4` = 0/1 → I2C0 SDA/SCL；2/3 → I2C1 SDA/SCL。
- UART：每 4 支一組 TX,RX,CTS,RTS；0–3 UART0、4–11 UART1、12–19 UART0、20–27 UART1、28–29 UART0。
- SPI：每 4 支一組 RX,CSn,SCK,TX；0–7 SPI0、8–15 SPI1、16–23 SPI0、24–29 SPI1。
- PWM：slice = `(gpio >> 1) & 7`，channel = `gpio & 1`（0=A、1=B）。
- FUNCSEL 值：HSTX 0、SPI 1、UART 2、I2C 3、PWM 4、SIO 5、PIO0/1/2 6/7/8、NULL 0x1f（RP2040 沒有 PIO2）。
Pico 2 預設：uart0 GP0/1；i2c0 GP4/5；spi0 RX16 CSn17 SCK18 TX19；LED GP25；ADC0–2 = GP26–28。
Pad（RP2350 reset 值）：ISO=1（隔離）、IE=0、**pull-down**；`gpio_set_function()` 會清 ISO、設 IE，但不動 pull。RP2040 沒有 ISO、預設 IE=1。直接寫暫存器時要自己清 ISO、設 IE。
⚠️ RP2350-E9（A2 stepping；A4 已修）：浮接 + 內建 pull-down 可能讀到 1 → 用 pull-up + 按鍵接地，或外接 ≤ 8.2 kΩ pull-down。
SIO/PIO 輸入永遠連著；DMA 不能存取 SIO（GPIO）。

---

【參考卡｜RP2350 週邊 2/8｜UART】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
RP2350（Pico 2）：2 個 UART（PL011），TX FIFO 32×8、RX FIFO 32×12。UARTCLK = clk_peri，SDK 開機設為 clk_sys = 150 MHz；呼叫 `set_sys_clock_*()` 後變 48 MHz → **先改時脈再 `uart_init`**。最大鮑率 clk_peri/16 = 9.375 Mbaud。
```c
uint actual = uart_init(uart1, 115200);       // 回傳實際鮑率
gpio_set_function(4, GPIO_FUNC_UART);         // GP4 = UART1 TX
gpio_set_function(5, GPIO_FUNC_UART);         // GP5 = UART1 RX
uart_set_format(uart1, 8, 1, UART_PARITY_NONE);
```
- `uart_write_blocking/read_blocking/putc_raw/getc/is_readable/is_writable`、`uart_tx_wait_blocking`（等最後 bit 送出）。
- 8N1 = 10 bit/byte：115200 → 11 520 B/s、每 byte 86.8 µs、32-byte FIFO 撐 2.78 ms。
- IRQ：`irq_set_exclusive_handler(UART0_IRQ, f); irq_set_enabled(UART0_IRQ, true); uart_set_irqs_enabled(uart0, true, false);`。ISR 內 `while (uart_is_readable(u))` 一次讀空（也清中斷條件），推進 ring buffer。
- RX 門檻 ≥ 4 筆觸發；不足 4 筆靠 RX timeout（32 bit 時間）觸發。
- DMA：`uart_get_dreq_num(u, is_tx)`，寫 `&uart_get_hw(u)->dr`；DMA 寫完 ≠ 線上送完。
- `pico_enable_stdio_uart` 會占用 uart0（GP0/1）；自己再用會和 printf 混在一起。
- 症狀：沒輸出 → 沒設 FUNC / 腳不屬該 UART（GP4/5 是 uart1）；亂碼 → 鮑率/格式不同或 init 後才改時脈；有 TX 沒 RX → TX/RX 要交叉、要共地。

---

【參考卡｜RP2350 週邊 3/8｜SPI】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
RP2350（Pico 2）：2 個 SPI（PL022），TX/RX FIFO 各 8，4–16 bit frame，**只支援 MSB first**。SSPCLK = clk_peri。master 最高 clk_peri/2（公式 75 MHz；datasheet 文字寫 70.5 Mb/s，不一致 ⚠️，以 `spi_init` 回傳值為準）；slave 最多 clk_peri/12。
```c
spi_init(spi0, 10 * 1000 * 1000);                 // 回傳實際值
spi_set_format(spi0, 8, SPI_CPOL_0, SPI_CPHA_0, SPI_MSB_FIRST);
gpio_set_function(16, GPIO_FUNC_SPI);             // RX = MISO
gpio_set_function(18, GPIO_FUNC_SPI);             // SCK
gpio_set_function(19, GPIO_FUNC_SPI);             // TX = MOSI
gpio_init(17); gpio_set_dir(17, GPIO_OUT); gpio_put(17, 1);  // CS 用 SIO
```
- **CS 用 GPIO 手動控制**：硬體 CSn + CPHA=0 時，PL022 每個 frame 之間會把 CSn 拉高。
- `spi_write_blocking(s, src, n)`、`spi_read_blocking(s, 0x00, dst, n)`（一直送 0x00）、`spi_write_read_blocking`；回傳值都是 len，不會報錯 → 讀到全 0x00/0xFF 要懷疑接線或 mode。
- `spi_write_blocking` 回傳前等移位完成，之後馬上拉高 CS 安全。
- Mode：0=(CPOL0,CPHA0)、1=(0,1)、2=(1,0)、3=(1,1)。
- DMA 全雙工：TX、RX 兩通道，`spi_get_dreq(s, true/false)`，寫/讀 `&spi_get_hw(s)->dr`，`dma_start_channel_mask` 同時啟動，**等 RX 完成再拉 CS**。
- 16-bit frame 配 `DMA_SIZE_16` 減半 DMA 次數。
- 症狀：全 FF/00 → MISO 沒設 SPI 功能、CS 沒拉低、mode 錯；最後 byte 被截 → DMA TX 完就拉 CS。

---

【參考卡｜RP2350 週邊 4/8｜I2C】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
RP2350（Pico 2）：2 個 I2C（DW_apb_i2c），FIFO 16，100k / 400k / 1 Mbit/s（無 3.4M High-speed）。時脈 = **clk_sys**（不是 clk_peri）。**需要 pull-up**（外部 4.7 kΩ 佳，內建只適合短線）。
```c
i2c_init(i2c0, 400 * 1000);
gpio_set_function(4, GPIO_FUNC_I2C);    // SDA
gpio_set_function(5, GPIO_FUNC_I2C);    // SCL
gpio_pull_up(4); gpio_pull_up(5);
// 讀暫存器：寫 reg（nostop=true，送 repeated START）→ 讀 n
int r = i2c_write_timeout_us(i2c0, addr, &reg, 1, true, 2000);
if (r == 1) r = i2c_read_timeout_us(i2c0, addr, buf, n, false, 2000 + 100 * n);
```
- 簽名：`int i2c_write_timeout_us(i2c, addr, src, len, nostop, timeout_us)`，read 同型。
- `addr` 是 **7-bit**（例如 0x68），不要傳左移過的 8-bit（0xD0）。
- 回傳：成功 = byte 數；位址沒 ACK = `PICO_ERROR_GENERIC`；逾時 = `PICO_ERROR_TIMEOUT`；寫入時資料被 NAK = 已成功 byte 數（< len）。一律檢查 `r < 0` 或 `r != len`，用名稱比較。
- 非 timeout 版（`i2c_write_blocking`）在沒 pull-up / SCL 被拉住時可能永遠卡住 → 考試用 `_timeout_us`。
- 寫暫存器：reg 與資料放同一 buffer 一次送，不要拆兩次 write。
- Bus scan：每個位址讀 1 byte 看回傳 ≥ 0；跳過保留位址 0x00–0x07、0x78–0x7F。
- 症狀：卡住 → 沒 pull-up；GENERIC → 位址錯/接反/沒電；讀值錯 → 寫 reg 時 nostop 用了 false。
- 每 byte = 9 個 SCL 週期；400 kHz 約 44 kB/s。優化：burst 讀連續暫存器。

---

【參考卡｜RP2350 週邊 5/8｜PWM】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
RP2350：12 slice（RP2040 8）× A/B 兩輸出；Pico 2（QFN-60）GPIO 0–29 只接 slice 0–7，slice 8–11 沒腳但可當週期中斷 timer。計數時脈 = clk_sys（預設 150 MHz）。同 slice 的 A/B **共用頻率**（TOP、分頻），duty 各自。
公式：
- `f_PWM = f_sys / ((TOP + 1) × (PH_CORRECT + 1) × DIV)`，`DIV = INT + FRAC/16`，1 ≤ DIV < 256
- duty = CC / (TOP + 1)；CC=0 → 0%、CC=TOP+1 → 100%；counter < CC 時輸出高
- **要 N 個 count 的週期：`pwm_set_wrap(slice, N - 1)`**
150 MHz 速查：20 kHz → DIV 1、TOP 7499；1 kHz → DIV 2.5（INT 2, FRAC 8）、TOP 59999；50 Hz → DIV 64、TOP 46874（1.5 ms ≈ CC 3516）。
設定順序（1 kHz 例）：`slice = pwm_gpio_to_slice_num(gpio)` → `gpio_set_function(gpio, GPIO_FUNC_PWM)` → `pwm_set_clkdiv_int_frac4(slice, 2, 8)` → `pwm_set_wrap(slice, 59999)` → `pwm_set_gpio_level(gpio, level)`（25% = (TOP+1)/4）→ `pwm_set_enabled(slice, true)`。
- `pwm_set_clkdiv(float)` 小數捨去到 1/16；精確用 `int_frac4`。
- `pwm_set_mask_enabled(mask)` 直接寫 EN：沒列在 mask 的 slice 會被關掉。
- CC、TOP 雙緩衝，下次 wrap 生效。
- Wrap IRQ：`pwm_set_irq_enabled(slice, true)` + handler 裝在 `PWM_DEFAULT_IRQ_NUM()`；handler 先 `pwm_clear_irq(slice)`。
- DMA 寫 `&pwm_hw->slice[s].cc` 必須 32-bit（低 16=A、高 16=B）；16-bit 寫會被複製成 A=B。
- B 腳可當輸入：`PWM_DIV_B_RISING` 量頻率、`PWM_DIV_B_HIGH` 量 duty。

---

【參考卡｜RP2350 週邊 6/8｜ADC 與溫度感測】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
RP2350A（Pico 2）：ADC ch0–3 = GPIO 26–29、溫度 = ch4（RP2350B：ch0–7 = GPIO 40–47、溫度 ch8）。12-bit（0–4095），ENOB 9.2 ⚠️未查證；clk_adc 48 MHz，每次 96 cycle → 2 µs = 500 kS/s（所有通道共用）。FIFO 滿了樣本直接丟（深度 8 筆 ⚠️未查證）。
```c
adc_init();
adc_gpio_init(26);                       // ch0
adc_set_temp_sensor_enabled(true);
adc_select_input(0);                     // 通道號，不是 GPIO 號
uint16_t raw = adc_read();               // one-shot，忙等約 2 µs
float v = raw * 3.3f / 4096.0f;
adc_select_input(ADC_TEMPERATURE_CHANNEL_NUM);   // A 封裝 = 4
float vt = adc_read() * 3.3f / 4096.0f;
float temp_c = 27.0f - (vt - 0.706f) / 0.001721f;  // 典型值，需校正
```
Free-running + DMA：
- `fs = 48 MHz / (DIV + 1)` → `adc_set_clkdiv(48e6f / fs - 1)`（10 kS/s → 4799）；round-robin k 通道每通道 fs/k。
- `adc_set_round_robin(mask)`、`adc_fifo_setup(true, true, 1, false, false)`（en、dreq_en、門檻、err_in_fifo、byte_shift）。
- DMA：`DMA_SIZE_16`、read_inc=false、write_inc=true、`DREQ_ADC`，read 位址 `&adc_hw->fifo`。
- 順序：**先啟動 DMA，再 `adc_run(true)`**；結束 `adc_run(false)` → `adc_fifo_drain()` → `adc_set_round_robin(0)`。
- 雜訊：過取樣平均、`adc_gpio_init`（關數位輸入）、降取樣率。
- 症狀：讀到別的腳 → 傳了 GPIO 號；溫度離譜 → 沒開 temp sensor / 通道錯。

---

【參考卡｜RP2350 週邊 7/8｜Timer、alarm、watchdog】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
RP2350：**兩個 timer TIMER0、TIMER1**（RP2040 一個），各 64-bit µs 計數器 + 4 alarm。IRQ：`TIMER0_IRQ_0..3` = 0–3、`TIMER1_IRQ_0..3` = 4–7（RP2040 的 `TIMER_IRQ_n` 在 RP2350 不存在）。
- 預設 alarm pool 占 **TIMER0 alarm 3**（`sleep_ms`、`add_alarm_*` 靠它）→ 自己用 `hardware_alarm_claim_unused(true)`，不要寫死 3。
pico_time：
- `add_alarm_in_us(us, cb, ud, fire_if_past)`：`int64_t cb(alarm_id_t, void *)` 回 0 不重複、>0 從返回時起再等、<0 從上次預定時間起。
- `add_repeating_timer_us(delay, cb, ud, &rt)`：`bool cb(repeating_timer_t *t)` 回 true 繼續。**delay < 0 = 固定頻率**（start-to-start），> 0 = 結束到開始（會漂移）。
```c
static repeating_timer_t rt;                         // static：不能放 stack
static volatile bool sample_due;
static bool on_tick(repeating_timer_t *t) { sample_due = true; return true; }
add_repeating_timer_us(-100, on_tick, NULL, &rt);    // 10 kHz，固定頻率
```
Callback 規則：在 timer IRQ context、在建立 pool 的核（預設 core 0）；要短，不可 printf / sleep；共享變數 volatile。
- `sleep_*` **ISR 內不可用**；`busy_wait_us/ms` 忙等較準。
Watchdog（link `hardware_watchdog`）：
- `watchdog_enable(ms, pause_on_debug)`（RP2350 最大約 16777 ms；RP2040 8388）、`watchdog_update()` 餵狗、`watchdog_enable_caused_reboot()` 檢查上次是否被狗重開。

---

【參考卡｜RP2350 週邊 8/8｜中斷（IRQ）規則與號碼】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
RP2350：52 個外部 IRQ（RP2040 32），優先權 8-bit 只有**高 4 bit 有效**（16 級；RP2040 高 2 bit）。Hazard3 IRQ 延遲較長 ⚠️未量測；SDK API 相同。
IRQ 號（用名稱，不寫數字）：TIMER0_IRQ_0..3=0–3、TIMER1=4–7、PWM_IRQ_WRAP_0/1=8/9、DMA_IRQ_0..3=10–13、USBCTRL=14、PIO0/1/2_IRQ_0/1=15–20、IO_IRQ_BANK0=21、SIO_IRQ_FIFO=25、SIO_IRQ_BELL=26、SPI0/1=31/32、UART0/1=33/34、ADC_IRQ_FIFO=35、I2C0/1=36/37、SPARE_IRQ_0..5=46–51。
API：
- `irq_set_exclusive_handler(num, h)`（已有 handler 會 assert）、`irq_add_shared_handler(num, h, order_priority)`、`irq_set_enabled(num, true)`、`irq_set_priority(num, p)`（0x00 最高、預設 0x80、0xff 最低）、`irq_set_pending(num)`。
- shared 的 `order_priority`：**數字大的先被呼叫**（與 `irq_set_priority` 相反）；全部 shared handler 合計上限預設 4（`PICO_MAX_SHARED_IRQ_HANDLERS`）。
- `irq_set_enabled` 只影響**呼叫的那顆核**。UART、SPI、DMA、PWM、TIMER 等只在一顆核 enable。
- GPIO IRQ 是 per-core，每核一個 callback。
ISR 規則：
1. 先清週邊旗標（PWM 寫 INTR、GPIO acknowledge、UART 讀空 FIFO、DMA 寫 INTS），否則一直重進。
2. 短：搬資料、設旗標、推 ring。
3. 不要 printf、sleep、malloc。
4. 時間關鍵 ISR 用 `__not_in_flash_func(name)` 放 RAM。
5. 共享變數 volatile；多欄位更新用 `save_and_disable_interrupts()` / `restore_interrupts()`。
6. 重活丟 bottom half：`user_irq_claim_unused` + 低優先權 + `irq_set_pending`。
