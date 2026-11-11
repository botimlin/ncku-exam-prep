# RP2350 週邊（pico-sdk）速查
> 用途：備援包，UART/SPI/I2C/PWM/ADC/Timer/IRQ
> 適用：RP2350（Pico 2=QFN-60），pico-sdk 2.x
> 來源：RP2350 datasheet §9、§12.1–12.5、§12.8–12.9、§3.2、App.D；github.com/raspberrypi/pico-sdk hardware_*/；pico-examples
> 最後更新 2026-11

## 通則
- `*_init` **不設腳**：一定要 `gpio_set_function(pin, GPIO_FUNC_UART/SPI/I2C/PWM)`
- 腳位查 datasheet Table 677：I2C `gpio%4`=0/1→I2C0 SDA/SCL、2/3→I2C1；PWM slice=`(gpio>>1)&7`、`gpio&1`=B
- Pico2 預設：uart0 GP0/1；i2c0 GP4/5；spi0 RX16 CS17 SCK18 TX19；ADC GP26–28
- RP2350 pad 預設 IE=0、ISO=1、**pull-down**；`gpio_set_function` 自動清 ISO/設 IE
- E9（A2；A4 已修）：浮接+內建 pull-down 讀到 1 → 用 pull-up 或外接 ≤8.2kΩ
- clk_peri 預設=clk_sys=150MHz（UART/SPI）；`set_sys_clock_*` 後變 48MHz → 先改時脈再 init
- I2C、PWM 用 clk_sys；ADC 用 48MHz

## UART（PL011，FIFO 32）
- `uint uart_init(u, baud)` 回傳實際鮑率；`uart_set_format(u,8,1,UART_PARITY_NONE)`
- `uart_write_blocking/read_blocking/putc_raw/getc/is_readable/tx_wait_blocking`
- 8N1=10bit/byte：115200→11.5kB/s、87µs/byte；最大 clk/16
- IRQ：`irq_set_exclusive_handler(UART0_IRQ,f)`+`uart_set_irqs_enabled(u,true,false)`；ISR 內 `while(uart_is_readable)` 讀空
- DMA DREQ：`uart_get_dreq_num(u,is_tx)`，寫 `&uart_get_hw(u)->dr`

## SPI（PL022，FIFO 8，MSB only）
- `spi_init(s,baud)` 回傳實際；`spi_set_format(s,8,SPI_CPOL_0,SPI_CPHA_0,SPI_MSB_FIRST)`
- `spi_write_blocking`、`spi_read_blocking(s,0x00,buf,n)`、`spi_write_read_blocking`
- master 最高 clk_peri/2；slave clk_peri/12
- **CS 用 GPIO 手動**（硬體 CSn+CPHA0 每 byte 跳高）
- DMA：TX+RX 兩通道，`spi_get_dreq(s,true/false)`，等 RX 完成再拉 CS

## I2C（FIFO 16，≤1MHz）
- 需 pull-up（外部 4.7k 佳）；addr 為 **7-bit**
- `i2c_write_timeout_us(i,addr,src,n,nostop,us)`/`i2c_read_timeout_us`
- 回傳：成功=byte 數；位址 NAK=`PICO_ERROR_GENERIC`；逾時=`PICO_ERROR_TIMEOUT`
- 讀暫存器：write(reg, nostop=**true**) → read(n, false)
- 無 timeout 版沒 pull-up 會卡死；scan 跳過 0x00–07、0x78–7F

## PWM（12 slice，A/B 共用頻率）
- `f = f_sys/((TOP+1)(PH+1)(INT+FRAC/16))`；duty=CC/(TOP+1)；CC=0→0%、CC=TOP+1→100%
- **wrap=週期−1**；DIV 1..<256
- 150MHz：20kHz→TOP7499；1kHz→DIV2.5 TOP59999；50Hz→DIV64 TOP46874
- `pwm_set_wrap`、`pwm_set_chan_level`/`pwm_set_gpio_level`、`pwm_set_clkdiv_int_frac4`、`pwm_set_enabled`
- `pwm_set_mask_enabled(m)` 直接寫 EN（沒列的會關）
- IRQ：`pwm_clear_irq`+`pwm_set_irq_enabled`+`PWM_DEFAULT_IRQ_NUM()`
- B 腳輸入：`PWM_DIV_B_RISING`（頻率）/`PWM_DIV_B_HIGH`（duty）
- DMA→`&pwm_hw->slice[s].cc` 用 **32-bit**（16-bit 寫會複製到 A/B）

## ADC（12bit，ENOB 9.2⚠️未查證，500kS/s 共用）
- `adc_init`、`adc_gpio_init(26)`、`adc_select_input(ch)`（通道號非 GPIO）、`adc_read`（~2µs 忙等）
- 溫度：`adc_set_temp_sensor_enabled(true)`，ch=`ADC_TEMPERATURE_CHANNEL_NUM`（A=4）；T=27−(V−0.706)/0.001721
- free-run：`adc_set_clkdiv(48e6/fs−1)`、`adc_set_round_robin(mask)`、`adc_fifo_setup(1,1,1,0,0)`、DREQ_ADC；**先開 DMA 再 `adc_run(true)`**，結束 `adc_fifo_drain`

## Timer / Watchdog
- TIMER0/1 各 4 alarm；預設 pool 占 TIMER0 alarm3 → `hardware_alarm_claim_unused(true)`
- `add_alarm_in_us` cb 回傳 0 不重複/>0 從現在/<0 從上次預定
- `add_repeating_timer_us(−P,…)` 負數=固定頻率；`repeating_timer_t` 要 static
- callback 在 IRQ（建立 pool 的核）：不可 printf/sleep
- `watchdog_enable(ms,1)`（≤16777ms）、`watchdog_update`、`watchdog_enable_caused_reboot`

## IRQ
- 優先權 0x00 最高、預設 0x80、高 4bit 有效；shared `order_priority` **大的先呼叫**
- `irq_set_enabled` 只作用在呼叫的核；GPIO/FIFO IRQ per-core；非 local IRQ 只在一核開
- ISR：先清旗標→短→設旗標/ring buffer；`__not_in_flash_func`；共享 `volatile`
- bottom half：`user_irq_claim_unused`+`irq_set_pending`

## 效能
- 偶發少量→polling；不定時事件→IRQ+ring；大量/高速→DMA（+完成 IRQ）
- ISR 一次讀空 FIFO；批次處理；printf 移出計時區
- RP2350 新增：HSTX（GP12–19 只輸出 300Mb/s/腳）、TRNG（`get_rand_32`，pico_rand）、SHA-256（pico_sha256）

## 症狀
- UART 無輸出：沒設 FUNC/腳不屬該 UART/鮑率或時脈變
- SPI 全 FF：MISO=RX 沒設、mode 錯、CS
- I2C 卡：沒 pull-up；GENERIC：位址錯
- PWM 頻率偏：TOP 沒 −1、phase-correct 減半
- ADC 跳：平均/過取樣、`adc_gpio_init`
- ISR 一直進：沒清旗標
