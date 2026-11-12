# 主機 ↔ 微控制器通訊：Linux / ROS 2 主機與 RP2350（Pico 2）之間的序列連線、協定設計與效能

- 用途：上機考（成大資工特殊選才）**備援包**。考前 demo 沒有提到這個主題，但若考題要求「主機程式（Linux / ROS 2）與 Pico 2 板子互傳資料、並讓連線更快更穩」時使用。給「考場 LLM」當 context，也給考生自己查。涵蓋：USB CDC / UART 連線、pico-sdk stdio 內部行為、Linux termios / pySerial、封包框架（COBS / SLIP / 長度前綴）、CRC、序號與重送、位元組序與 struct、吞吐量與延遲計算、ROS 2 橋接 node、micro-ROS 概觀、完整範例（已在主機上以 pty 模擬測試）、除錯與優化清單。
- 適用版本：RP2350（Raspberry Pi Pico 2）；pico-sdk 2.x（查證時 GitHub master 與 release 2.3.1；與 2.1.0 有差異處會標註）；pico-sdk 2.3.1 內附 TinyUSB 0.18.0；pySerial 3.5；Linux kernel cdc-acm 驅動；ROS 2 Jazzy；Python 3.12（Ubuntu 24.04）。
- 來源（實際查閱）：
  - pico-sdk 原始碼 https://github.com/raspberrypi/pico-sdk ：`src/rp2_common/pico_stdio/include/pico/stdio.h`、`pico_stdio/stdio.c`、`pico_stdio/CMakeLists.txt`、`pico_stdio_usb/include/pico/stdio_usb.h`、`pico_stdio_usb/stdio_usb.c`、`pico_stdio_usb/include/tusb_config.h`（master、2.3.1、2.2.0、2.1.0 比對）、`pico_stdio_usb/stdio_usb_descriptors.c`、`pico_stdio_usb/CMakeLists.txt`、`pico_stdio_uart/stdio_uart.c`、`pico_stdio_uart/include/pico/stdio_uart.h`、`hardware_uart/include/hardware/uart.h`、`pico_clib_interface/newlib_interface.c`、`pico_usb_reset/include/pico/usb_reset_config.h`、`src/common/pico_base_headers/include/pico/error.h`、`src/boards/include/boards/pico2.h`
  - TinyUSB https://github.com/hathach/tinyusb ：`src/class/cdc/cdc_device.h`、`cdc_device.c`、`src/tusb.c`、`src/tusb_option.h`（pico-sdk 2.3.1 釘選的 commit）
  - RP2350 datasheet https://datasheets.raspberrypi.com/rp2350/rp2350-datasheet.pdf （12.1 UART、USB 章節、3.7.4.3.2 Cortex-M33 unaligned accesses）
  - Hazard3 文件 https://github.com/Wren6991/Hazard3 （`doc/sections/config.adoc`：未對齊 load/store 會產生例外）
  - pySerial 原始碼 https://github.com/pyserial/pyserial （`serial/serialposix.py`、`serial/serialutil.py`）與 API 文件 https://pyserial.readthedocs.io/en/latest/pyserial_api.html
  - Linux kernel：`drivers/usb/class/cdc-acm.c`、`drivers/tty/tty_io.c`（`tty_std_termios`）、`drivers/tty/tty_port.c`（開啟時拉高 DTR/RTS）；`man 3 termios`；GNU coreutils 9.4 `stty --help`
  - micro-ROS https://github.com/micro-ROS/micro_ros_raspberrypi_pico_sdk （jazzy 分支：`README.md`、`CMakeLists.txt`、`pico_uart_transport.c`、`pico_micro_ros_example.c`、`microros_static_library/library_generation/toolchain.cmake`）
  - rosidl_python（jazzy）`rosidl_generator_py/resource/_msg.py.em`（數值陣列欄位用 `array.array`）
  - COBS：Wikipedia「Consistent Overhead Byte Stuffing」（範例表）與 Cheshire & Baker 1999 論文（Wikipedia 引用）；SLIP：RFC 1055 https://www.rfc-editor.org/rfc/rfc1055.txt
  - Python 標準庫 `struct`、`binascii.crc_hqx`、`zlib.crc32`、`tty`、`termios`（本機 Python 3.12.3 實測）
- 最後更新：2026-11

> 本檔所有 C / Python 範例都是自行撰寫的短程式。**主機端程式與與平台無關的 C 函式（CRC、COBS、frame 組裝、termios 開 port）已在 Linux 主機上編譯並用 pty 模擬序列埠測試過**；Pico 端 `main.c` 只用 stub 標頭做過語法檢查與主機模擬，**未在真正的 pico-sdk / 板子上編譯**，考場使用前請先編譯驗證。

---

## 0. 快速決策表（先看這裡）

| 情境 | 建議 |
|---|---|
| 只要印 debug 訊息、資料量小 | `printf` + `stdio_usb`，主機 `cat` / `python3 -m serial.tools.miniterm` 看 |
| 要傳大量數值給主機（>10 KB/s）| **二進位 + COBS 框架 + CRC16**，批次寫出（§4、§6） |
| 用 UART 轉接器 / Debug Probe 的 UART | 兩端 baud 要一致；115200 只有 ~11.5 KB/s（§5） |
| 主機程式是 ROS 2 node | 讀 serial 不可阻塞 executor：timer 非阻塞輪詢或獨立 thread（§7） |
| 環境沒有 pyserial 也不能裝 | 用 Python 標準庫 `os` + `termios` + `tty` + `select`（§3.7，已測） |
| 二進位資料出現多餘的 `0x0D` | pico 端 CRLF 轉換沒關（§2.4） |
| 主機完全收不到東西 | 先看 §8 除錯清單第 1 列（port、stdio 沒開、DTR、CRLF） |

---

## 1. 實體 / 邏輯連線

| 連線 | Pico 端 | Linux 端裝置 | baud rate | 速度上限 | 備註 |
|---|---|---|---|---|---|
| **USB CDC-ACM**（板子 USB 直接接主機） | `pico_stdio_usb`（TinyUSB device） | `/dev/ttyACM*`（`cdc_acm` 驅動） | **不影響實際速度**（只是通知 device 的數值） | USB 1.1 Full Speed 12 Mbit/s，bulk 封包最大 64 B | **baud 設 1200 會讓板子重開進 BOOTSEL**（見 §3.8） |
| **UART + USB-serial 轉接器** | `pico_stdio_uart` 或 `hardware_uart`；預設 UART0 TX=GP0、RX=GP1 | `/dev/ttyUSB*`（FTDI/CP210x/CH34x/PL2303 等 usb-serial 驅動）或 `/dev/ttyACM*`（CDC 類轉接器） | **兩端必須一致** | 8N1 每 byte 10 bit → 115200 baud ≈ 11.5 KB/s | 交叉接線 TX↔RX，共地 |
| **Debug Probe（SWD + UART 橋）** | UART（同上） | 通常是 `/dev/ttyACM*`（probe 自己的 CDC） | 兩端一致 | 同 UART | 與板子自己的 USB CDC 同時存在時會有 ttyACM0、ttyACM1，順序依列舉順序 |
| semihosting / RTT（經 SWD） | `pico_stdio_semihosting`、`pico_stdio_rtt`（SDK 有這兩個 stdio driver） | 需要 debugger（OpenOCD 等）⚠️未驗證考場是否提供 | — | — | 只當備援 debug 輸出 |

RP2350 硬體事實（datasheet）：
- USB：USB 1.1 controller + PHY，device 為 Full Speed；有 4 KB USB DPRAM。
- UART：ARM PL011 相容，TX / RX 各 **32 byte FIFO**；最高 baud = UARTCLK / 16。
- 預設 UART baud：`PICO_DEFAULT_UART_BAUD_RATE` = 115200（`hardware/uart.h`）。`uart_init()` 預設格式 8N1、開 FIFO，回傳實際 baud。

---

## 2. Pico 端（pico-sdk）

### 2.1 CMake：選擇 stdio 通道

```cmake
add_executable(app main.c crc_cobs.c)
target_link_libraries(app pico_stdlib)
pico_enable_stdio_usb(app 1)     # USB CDC → /dev/ttyACM*
pico_enable_stdio_uart(app 0)    # 關掉 UART stdio（見下方「兩個都開」陷阱）
# 可選：全域關掉 \n → \r\n 轉換（二進位傳輸時建議）
target_compile_definitions(app PRIVATE PICO_STDIO_DEFAULT_CRLF=0)
pico_add_extra_outputs(app)
```

- 全域預設（`pico_stdio/CMakeLists.txt`）：`PICO_STDIO_UART` 預設 **1**、`PICO_STDIO_USB` 預設 **0**。不寫 `pico_enable_stdio_usb(app 1)` 就沒有 USB 輸出。
- **兩個都開時**：`stdio_put_string` / `printf` 會對「所有已啟用 driver」逐一輸出（`stdio.c`）。UART driver 的 `out_chars` 是逐 byte `uart_putc`（阻塞），所以 USB 吞吐量會被 115200 baud 的 UART 拖到 ~11.5 KB/s。要快就關掉 UART stdio，或用 `stdio_filter_driver(&stdio_usb)`。
- micro-ROS 官方 Pico 範例的 CMake 也是：`pico_enable_stdio_usb(... 1)`、`pico_enable_stdio_uart(... 0)`，並加上 `PICO_UART_ENABLE_CRLF_SUPPORT=0`、`PICO_STDIO_ENABLE_CRLF_SUPPORT=0`、`PICO_STDIO_DEFAULT_CRLF=0`（二進位協定要關 CRLF 的佐證）。

### 2.2 stdio API（`pico/stdio.h`，2.1.0 / 2.2.0 / 2.3.1 皆有）

| 函式 | 行為（依原始碼） |
|---|---|
| `bool stdio_init_all(void)` | 初始化有 link 進來的 UART / semihosting / RTT / USB stdio；至少一個成功回傳 true |
| `void stdio_flush(void)` | 對每個 driver 呼叫 `out_flush` |
| `int stdio_getchar_timeout_us(uint32_t timeout_us)` / `getchar_timeout_us` | 回傳 0–255，逾時回傳 `PICO_ERROR_TIMEOUT`（-2）。`timeout_us=0` = 不等 |
| `int stdio_get_until(char *buf, int len, absolute_time_t until)` | **一次讀多個 byte**：只要有 ≥1 byte 就立刻回傳讀到的數量（≤ len）；到 `until` 都沒有 → `PICO_ERROR_TIMEOUT`。輸入**沒有**任何 CR/LF 轉換 |
| `int stdio_put_string(const char *s, int len, bool newline, bool cr_translation)` | **一次寫多個 byte**；`cr_translation=false` → 原始位元組；`len=-1` 用 strlen |
| `int stdio_putchar_raw(int c)` / `putchar_raw` | 不做 CRLF 轉換的 putchar |
| `int stdio_puts_raw(const char *s)` / `puts_raw` | 不轉換、自動加 `\n`、會 flush |
| `void stdio_set_translate_crlf(stdio_driver_t *driver, bool translate)` | 關/開某個 driver 的 `\n → \r\n`；需在 driver 初始化後呼叫。**若編譯時 `PICO_STDIO_ENABLE_CRLF_SUPPORT=0`，呼叫此函式會 `panic_unsupported()`** |
| `void stdio_filter_driver(stdio_driver_t *driver)` | 只用這一個 driver 輸入輸出（NULL = 全部） |
| `void stdio_set_driver_enabled(stdio_driver_t *driver, bool enabled)` | 加入/移除 driver |
| `void stdio_set_chars_available_callback(void (*fn)(void*), void *param)` | 有輸入時通知（USB 版由背景 task 呼叫；不要在 callback 裡做重活） |
| `bool stdio_usb_connected(void)`（`pico/stdio_usb.h`） | 預設檢查 **DTR**（`tud_cdc_connected()`）；`PICO_STDIO_USB_CONNECTION_WITHOUT_DTR=1` 改成 `tud_ready()` |
| `extern stdio_driver_t stdio_usb;` / `stdio_uart` | driver 物件，給 `stdio_set_translate_crlf` / `stdio_filter_driver` 用 |

錯誤碼（`pico/error.h`）：`PICO_OK=0`、`PICO_ERROR_GENERIC=-1`、`PICO_ERROR_TIMEOUT=-2`、`PICO_ERROR_NO_DATA=-3`。比較時用名稱。

### 2.3 `stdio_usb` 內部行為（讀 `stdio_usb.c` 得到的事實）

| 行為 | 細節 | 影響 |
|---|---|---|
| **未連線時輸出直接丟掉** | `stdio_usb_out_chars` 先檢查 `stdio_usb_connected()`（DTR），沒連線就什麼都不送 | 開機到主機開 port 之間的 `printf` 全部消失；主機關 port（DTR 掉）後的輸出也消失 |
| 主機不讀時 500 ms 後丟資料 | TX FIFO 滿且超過 `PICO_STDIO_USB_STDOUT_TIMEOUT_US`（預設 500000 µs）→ 放棄這次輸出 | 主機讀太慢 → 裝置端**靜默掉資料**（用序號偵測，§4.7） |
| 每段都 flush | 每次把 `min(剩餘, tud_cdc_write_available())` 寫進 FIFO 後就 `tud_task()` + `tud_cdc_write_flush()` | 很多小 `printf` = 很多小 USB 封包；批次成一大塊再寫比較有效率 |
| `printf` 結尾會 `stdio_flush()` | `vprintf` wrapper 在格式化後呼叫 `stdio_flush()` | 每個 printf 都推出一次 |
| CDC FIFO 大小 | `tusb_config.h`：2.2.0 起 Full Speed 下 `CFG_TUD_CDC_RX_BUFSIZE`/`TX_BUFSIZE`/`EP_BUFSIZE` 都是 **64**；**2.1.0 是 256** | FIFO 小 → 每 64 B 就要 flush 一次。這些巨集有 `#ifndef` 保護，可用 `target_compile_definitions(app PRIVATE CFG_TUD_CDC_TX_BUFSIZE=1024)` 覆寫（依原始碼可行；對吞吐量的實際效果⚠️未驗證，請實測） |
| 背景 task | 預設每 `PICO_STDIO_USB_TASK_INTERVAL_US`（1000 µs）透過低優先權 IRQ 跑 `tud_task()`；有 shared USB IRQ handler 時也會在 USB 事件時觸發 | 你不必自己呼叫 `tud_task()`（直接用 TinyUSB 時才要） |
| 互斥鎖 | 所有 USB stdio 操作拿 `stdio_usb_mutex`；拿不到最多等 `PICO_STDIO_DEADLOCK_TIMEOUT_MS`（1000 ms） | **不要在 IRQ handler 裡 printf**（可能卡 1 s 後丟資料） |
| 只能在擁有 default alarm pool 的核心初始化 | `stdio_usb_init` 檢查 `get_core_num()`，不符則 assert / 回傳 false | 在 core 0 呼叫 `stdio_init_all()` |
| 等待連線 | `PICO_STDIO_USB_CONNECT_WAIT_TIMEOUT_MS`（預設 0 = 不等；負數 = 永遠等），連上後再等 `PICO_STDIO_USB_POST_CONNECT_WAIT_DELAY_MS`（預設 50 ms） | 也可自己寫 `while (!stdio_usb_connected()) sleep_ms(10);` |
| USB ID | VID `0x2E8A`；PID：RP2040 `0x000a`、其他（RP2350）`0x0009`；product 字串 "Pico" | 用來在 `/dev/serial/by-id/` 辨認 |

### 2.4 CRLF 轉換：二進位傳輸的頭號殺手

- 預設 `PICO_STDIO_ENABLE_CRLF_SUPPORT=1`、`PICO_STDIO_DEFAULT_CRLF=1`（USB：`PICO_STDIO_USB_DEFAULT_CRLF`、UART stdio：`PICO_STDIO_UART_DEFAULT_CRLF` 都跟著它）→ **輸出時把前面不是 `\r` 的 `\n`（0x0A）變成 `\r\n`**。只影響輸出；輸入不轉換。
- 會被轉換的路徑：`printf`、`putchar`、`puts`、**`fwrite(…, stdout)` / `write(1, …)`**（newlib 的 `_write` 呼叫 `stdio_put_string(buf, len, false, true)`，`cr_translation=true`）。
- 不轉換的路徑：`putchar_raw`、`puts_raw`、`stdio_put_string(buf, len, false, false)`。
- 二進位資料裡 0x0A 隨時會出現（數值、CRC、COBS 碼），被插入 0x0D 就整個 frame CRC 錯。

三種關法（擇一）：

```c
// (1) 執行期：只關 USB driver（stdio_init_all 之後）
#include "pico/stdio_usb.h"
stdio_set_translate_crlf(&stdio_usb, false);

// (2) 每次寫都用 raw 路徑
stdio_put_string((const char *)buf, (int)len, false, false);

// (3) 編譯期（CMake）：target_compile_definitions(app PRIVATE PICO_STDIO_DEFAULT_CRLF=0)
```

`hardware_uart` 層另有自己的轉換：`uart_putc` / `uart_puts` 在 `uart_set_translate_crlf(uart, true)` 後會轉；預設 `PICO_UART_DEFAULT_CRLF=0`（不轉）。`uart_putc_raw` 永遠不轉。

### 2.5 Pico 端讀取

```c
// 非阻塞：until = 現在，檢查一次就回傳
char in[64];
int k = stdio_get_until(in, sizeof in, make_timeout_time_us(0));
if (k > 0) { /* 處理 in[0..k) —— 可能少於 64，可能半個 frame */ }

// 等最多 10 ms 拿 1 byte
int c = getchar_timeout_us(10000);
if (c != PICO_ERROR_TIMEOUT) { /* 0..255 */ }
```

讀一行文字指令（要同時接受 `\r` 與 `\n`：screen / minicom / miniterm 按 Enter 常送 `\r`）：

```c
// 回傳行長度；逾時回傳 -1。line 以 '\0' 結尾。
int read_line(char *line, int max, uint32_t timeout_us) {
    int n = 0;
    absolute_time_t until = make_timeout_time_us(timeout_us);
    while (!time_reached(until)) {
        int c = getchar_timeout_us(1000);
        if (c == PICO_ERROR_TIMEOUT) continue;
        if (c == '\r' || c == '\n') { if (n == 0) continue; line[n] = 0; return n; }
        if (n < max - 1) line[n++] = (char)c;
    }
    return -1;
}
```

- `scanf` / `getchar` 走 `stdio_get_until(..., at_the_end_of_time)`：**永遠阻塞**直到有輸入。
- 輸入緩衝：USB CDC RX FIFO 只有 64 B（2.2.0+）。主機一次送很多、Pico 很久才讀 → USB 端 NAK 反壓（主機 write 變慢），不會像 UART 那樣直接掉資料⚠️未驗證細節。
- UART RX FIFO 只有 32 B：115200 baud 下 32 × 86.8 µs ≈ **2.8 ms** 不讀就溢位丟資料 → 高速 UART 接收要用 IRQ 或 DMA（DMA 見 `pico-dma.md`，`DREQ_UART0_RX` 等）。

### 2.6 直接用 TinyUSB CDC API（進階）

`pico_stdio_usb` 底層就是 TinyUSB。API（`class/cdc/cdc_device.h`，單介面版本，`_n_` 版本多一個 `itf` 參數）：

| 函式 | 說明 |
|---|---|
| `bool tud_cdc_connected(void)` | DTR 為 1（且 `tud_ready()`） |
| `bool tud_cdc_ready(void)` | 介面可用 |
| `uint32_t tud_cdc_available(void)` | RX FIFO 內可讀 byte 數 |
| `uint32_t tud_cdc_read(void *buf, uint32_t bufsize)` | 讀最多 bufsize，回傳實際讀到 |
| `int32_t tud_cdc_read_char(void)` | 沒資料回傳 -1 |
| `void tud_cdc_read_flush(void)` | 清 RX |
| `uint32_t tud_cdc_write(const void *buf, uint32_t bufsize)` | 寫進 TX FIFO，**回傳實際寫入數（FIFO 滿時 < bufsize，要迴圈）**；FIFO 內 ≥ 一個封包（64 B）時會自動開始傳 |
| `uint32_t tud_cdc_write_available(void)` | TX FIFO 剩餘空間 |
| `uint32_t tud_cdc_write_flush(void)` | 把 FIFO 內剩下的（不足一包的）送出 |
| `void tud_task(void)` | TinyUSB 事件處理，自己用 TinyUSB 時要在主迴圈頻繁呼叫 |
| callback：`tud_cdc_rx_cb(uint8_t itf)`、`tud_cdc_line_state_cb(uint8_t itf, bool dtr, bool rts)`、`tud_cdc_line_coding_cb(...)`、`tud_cdc_tx_complete_cb(uint8_t itf)` | weak，自己定義即可 |

- **與 `stdio_usb` 混用的風險**：`stdio_usb` 的背景 IRQ 在持有 `stdio_usb_mutex` 時呼叫 `tud_task()`；你在主程式直接呼叫 `tud_cdc_write()` 沒拿這把鎖 → 可能競爭。⚠️未驗證是否實際出錯。比較安全的「高吞吐」做法：仍用 `stdio_usb`，但用 `stdio_put_string(buf, len, false, false)` 一次寫一大塊（內部就是迴圈 `tud_cdc_write` + flush，並且有加鎖）。
- 完全自己用 TinyUSB：link `tinyusb_device`（`pico_stdio_usb` 會自動退出）、自備 `tusb_config.h` 與 USB descriptor、呼叫 `tusb_init()`、主迴圈 `tud_task()`。工程量大，考試時間有限時不建議，除非題目已提供。

### 2.7 hardware_uart（用 UART 連線、不走 stdio 時）

```c
#include "hardware/uart.h"
#include "hardware/gpio.h"
uint actual = uart_init(uart0, 921600);          // 回傳實際 baud；8N1、開 FIFO
gpio_set_function(0, GPIO_FUNC_UART);            // GP0 = UART0 TX
gpio_set_function(1, GPIO_FUNC_UART);            // GP1 = UART0 RX
uart_write_blocking(uart0, buf, len);            // 阻塞到全部進 TX FIFO
uart_tx_wait_blocking(uart0);                    // 等 FIFO 真的送完
if (uart_is_readable(uart0)) { uint8_t b = (uint8_t)uart_getc(uart0); }
bool ok = uart_is_readable_within_us(uart0, 1000);
uart_read_blocking(uart0, dst, n);               // 阻塞到讀滿 n
uart_set_irqs_enabled(uart0, true, false);       // RX 中斷：≥4 字元或 32 bit 時間無新資料（RX timeout）
uint dreq = uart_get_dreq_num(uart0, false);     // 給 DMA 用（false = RX）
```

---

## 3. Linux 主機端

### 3.1 找到裝置

```bash
ls -l /dev/ttyACM* /dev/ttyUSB* 2>/dev/null
ls -l /dev/serial/by-id/            # 穩定名稱（需要 udev；容器內可能沒有）
python3 -m serial.tools.list_ports -v   # 有 pyserial 時：列出 port 與 VID:PID、描述
dmesg | tail -20                    # 插拔後看是 ttyACM 幾號（容器內可能無權限）
```

- `/dev/ttyACMn`：USB CDC-ACM（Pico `stdio_usb`、Debug Probe、部分轉接器）。`/dev/ttyUSBn`：usb-serial 驅動的轉接器。
- 板子重新燒錄 / 重開會**重新列舉**：port 消失再出現，編號可能改變，已開啟的 fd 失效（讀會出錯或 EOF）。程式要能重開 port。
- **容器**：裝置要由啟動容器時傳入（`--device` 或 `--privileged`）；重新列舉後容器內節點是否跟著更新 ⚠️未驗證（依考場設定），出問題就重新 `ls /dev/ttyACM*`。

### 3.2 權限

- 一般 Linux 上 `/dev/ttyACM*` 屬於 `root:dialout`、權限 660（依 udev 規則，⚠️發行版差異）。`Permission denied` → 使用者不在 dialout 群組。**考場不要改系統設定 / 群組**（禁止安裝與改設定）；容器內通常是 root，不會遇到。真的遇到就回報監考或改用題目給的方式。

### 3.3 預設 termios 會破壞二進位資料

kernel `cdc-acm` 驅動的初始 termios 是 `tty_std_termios`（`c_cflag` 改成 `B9600|CS8|CREAD|HUPCL|CLOCAL`）。`tty_std_termios` 預設：

| flag | 效果 | 對二進位資料的破壞 |
|---|---|---|
| `ICANON` | 一行一行給（收到 `\n` 才返回 read） | 沒有換行就一直讀不到；特殊字元被吃掉 |
| `ECHO` | 收到的 byte **回送給裝置** | Pico 收到自己送出的資料 → 協定亂掉 |
| `ICRNL` | 收到的 0x0D 變 0x0A | 資料被改 |
| `OPOST`+`ONLCR` | 主機送出的 0x0A 變 0x0D 0x0A | 送給 Pico 的資料被改 |
| `IXON` | 0x11/0x13 被當 XON/XOFF 吃掉 | 資料消失 |
| `ISIG` | 0x03 等觸發訊號 | 資料消失 |

→ **一定要設 raw mode**。pySerial 開 port 時會自動關掉 `ICANON|ECHO|ECHOE|ECHOK|ECHONL|ISIG|IEXTEN`、`OPOST|ONLCR|OCRNL`、`INLCR|IGNCR|ICRNL|IGNBRK`，並依參數關 `IXON` 等（`serialposix.py`）；用 `cat` / shell 時要自己 `stty`。

```bash
stty -F /dev/ttyACM0 raw -echo 115200      # raw 不含 -echo，要另外加
stty -F /dev/ttyACM0 -a                    # 檢查目前設定
```

- GNU stty 的 `raw` = `-ignbrk -brkint -ignpar -parmrk -inpck -istrip -inlcr -igncr -icrnl -ixon -ixoff -icanon -opost -isig -iuclc -ixany -imaxbel -xcase min 1 time 0`。
- 設定會留在 tty 上，但下一個程式（或裝置重新列舉）可能改回 ⚠️未驗證保留多久。最穩：用一個 fd 從頭開到尾：

```bash
exec 3<>/dev/ttyACM0 && stty -F /dev/ttyACM0 raw -echo   # fd 3 保持開啟（DTR 維持）
timeout 5 cat <&3 > dump.bin &                            # 收 5 秒
printf '\x01\x02\x00' >&3                                 # 送
wait; exec 3>&-
```

### 3.4 Shell 工具（不用寫程式就能看資料）

```bash
cat /dev/ttyACM0                              # 文字輸出（先 stty raw -echo）
timeout 3 cat /dev/ttyACM0 | xxd | head       # 十六進位
timeout 3 cat /dev/ttyACM0 | od -An -tx1 -v | head
timeout 5 cat /dev/ttyACM0 | wc -c            # 粗略吞吐量：5 秒收到幾 byte
python3 -m serial.tools.miniterm /dev/ttyACM0 115200 --raw   # pyserial 內建終端機；Ctrl+] 離開
screen /dev/ttyACM0 115200                    # 若有安裝（Ctrl+A K 離開）；minicom/picocom 同理
```

- 同一個 port **不要同時被兩個程式讀**（例如背景還有一個 `cat`）：byte 會被兩邊搶，看起來像隨機掉資料。pySerial 可加 `exclusive=True`（POSIX 用 `flock`，只擋其他也用 flock 的程式）。

### 3.5 C：termios raw + poll（已在 pty 上測試）

```c
#include <fcntl.h>
#include <termios.h>
#include <unistd.h>
#include <poll.h>
#include <errno.h>
#include <stdio.h>

int serial_open(const char *path, speed_t baud) {
    int fd = open(path, O_RDWR | O_NOCTTY | O_CLOEXEC);
    if (fd < 0) { perror("open"); return -1; }
    struct termios t;
    if (tcgetattr(fd, &t) < 0) { perror("tcgetattr"); close(fd); return -1; }
    cfmakeraw(&t);                       // 關 ICANON/ECHO/ISIG/IEXTEN/OPOST/ICRNL/IXON…，CS8
    t.c_cflag |= CLOCAL | CREAD;
    t.c_cc[VMIN] = 0;                    // 搭配 poll：read 不阻塞
    t.c_cc[VTIME] = 0;
    cfsetispeed(&t, baud); cfsetospeed(&t, baud);   // UART 轉接器才有意義；CDC 忽略（但別用 B1200）
    if (tcsetattr(fd, TCSANOW, &t) < 0) { perror("tcsetattr"); close(fd); return -1; }
    tcflush(fd, TCIFLUSH);               // 丟掉開啟前殘留的輸入
    return fd;
}

int write_all(int fd, const void *buf, size_t n) {   // write 可能只寫一部分
    const unsigned char *p = buf;
    while (n) {
        ssize_t k = write(fd, p, n);
        if (k < 0) { if (errno == EINTR || errno == EAGAIN) continue; return -1; }
        p += k; n -= (size_t)k;
    }
    return 0;
}

// 讀迴圈：poll 等資料 → 一次 read 一大塊（回傳數量可能少於要求，交給 parser 累積）
void rx_loop(int fd) {
    unsigned char buf[4096];
    for (;;) {
        struct pollfd pfd = { .fd = fd, .events = POLLIN };
        int r = poll(&pfd, 1, 1000);
        if (r < 0) { if (errno == EINTR) continue; perror("poll"); break; }
        if (r == 0) continue;                                   // 1 s 沒資料
        if (pfd.revents & (POLLERR | POLLHUP)) break;           // 裝置拔掉 / 重新列舉
        ssize_t n = read(fd, buf, sizeof buf);
        if (n < 0) { if (errno == EINTR || errno == EAGAIN) continue; perror("read"); break; }
        if (n == 0) continue;
        /* parser_feed(buf, n); */
    }
}
```

VMIN / VTIME（`man 3 termios`，非 canonical 模式）：

| VMIN | VTIME | read 行為 |
|---|---|---|
| 0 | 0 | 輪詢：有多少回多少（≤ 要求數），沒有回 0 |
| >0 | 0 | 阻塞到至少 VMIN byte |
| 0 | >0 | 計時（單位 0.1 s，從 read 呼叫開始）：≥1 byte 或逾時就回，逾時回 0 |
| >0 | >0 | byte 間計時：收到第一個 byte 後開始，每收一 byte 重設 |

- `cfmakeraw` 依 man page 設定：`c_iflag &= ~(IGNBRK|BRKINT|PARMRK|ISTRIP|INLCR|IGNCR|ICRNL|IXON)`；`c_oflag &= ~OPOST`；`c_lflag &= ~(ECHO|ECHONL|ICANON|ISIG|IEXTEN)`；`c_cflag &= ~(CSIZE|PARENB); c_cflag |= CS8`。VMIN/VTIME 請自己明確設定。
- 也可以 `O_NONBLOCK` 開檔 + `select`/`poll`；沒資料時 read 回 -1、`errno=EAGAIN`。

### 3.6 pySerial（3.5）

```python
import serial
s = serial.Serial('/dev/ttyACM0', 115200, timeout=0.05)   # 開啟即設定 raw、拉 DTR/RTS
```

| API | 行為（原始碼 / 文件） |
|---|---|
| `Serial(port=None, baudrate=9600, bytesize=EIGHTBITS, parity=PARITY_NONE, stopbits=STOPBITS_ONE, timeout=None, xonxoff=False, rtscts=False, write_timeout=None, dsrdtr=False, inter_byte_timeout=None, exclusive=None)` | 給 port 就立刻開啟；`dsrdtr=False` 時開啟後設定 DTR（預設 DTR=True） |
| `timeout=None` | read 阻塞到讀滿 size |
| `timeout=0` | 非阻塞：立即回傳 0..size byte |
| `timeout=x`（秒，可小數） | 讀滿就回；否則等到 x 秒後回傳**已收到的部分**（可能是空 bytes） |
| `read(size=1)` | 回傳 `bytes`，**長度可能小於 size**（逾時） |
| `in_waiting` | OS 輸入緩衝 byte 數（`TIOCINQ`） |
| `read_until(expected=LF, size=None)` | **內部每次 `read(1)`**：每 byte 一次 select + os.read，高速資料下很慢 |
| `readline()` | 來自 `io.RawIOBase`，同樣逐 byte 讀（無 peek）⚠️依 CPython io 實作推論 |
| `write(data)` | 預設阻塞直到寫完（除非設 `write_timeout`），回傳寫入數 |
| `flush()` | 等輸出送完（`tcdrain`） |
| `reset_input_buffer()` / `reset_output_buffer()` | 丟掉 OS 緩衝內容（舊名 `flushInput()` / `flushOutput()`） |
| `dtr` / `rts` 屬性 | 讀寫控制線 |
| `close()` / `with serial.Serial(...) as s:` | 關閉（HUPCL：DTR 掉 → Pico `stdio_usb_connected()` 變 false） |
| 拔線 | read 丟 `SerialException('device reports readiness to read but returned no data ...')` |

**高速讀取的正確寫法**（避免逐 byte）：

```python
chunk = s.read(max(1, s.in_waiting))   # 有多少拿多少；沒有就最多等 timeout 拿 1 byte
buf += chunk                            # 累積到自己的 bytearray，再切 frame
```

- 檢查是否有 pyserial：`python3 -c "import serial, sys; print(serial.__version__)"`。ROS 2 Jazzy 映像是否內建 ⚠️未驗證；**沒有就用 §3.7**。

### 3.7 只用 Python 標準庫（沒有 pyserial 時，已在 pty 上測試）

```python
import os, termios, tty, select

def open_raw(path, baud=termios.B115200):
    fd = os.open(path, os.O_RDWR | os.O_NOCTTY)
    tty.setraw(fd)                                   # 等同 cfmakeraw（另有 tty.cfmakeraw，3.12+）
    attr = termios.tcgetattr(fd)                     # [iflag, oflag, cflag, lflag, ispeed, ospeed, cc]
    attr[4] = attr[5] = baud                         # UART 轉接器需要；CDC 無影響
    attr[2] |= termios.CLOCAL | termios.CREAD
    termios.tcsetattr(fd, termios.TCSANOW, attr)
    termios.tcflush(fd, termios.TCIFLUSH)
    return fd

fd = open_raw('/dev/ttyACM0')
r, _, _ = select.select([fd], [], [], 0.05)          # 最多等 50 ms
data = os.read(fd, 4096) if r else b''               # 回傳數量可能 < 4096
os.write(fd, b'\x01\x02\x00')                        # 回傳實際寫入數；大量資料要迴圈
```

### 3.8 DTR、1200 baud、重新列舉

- Linux tty 開啟時（baud ≠ 0）會**拉高 DTR/RTS**（`tty_port.c`），關閉時若 `HUPCL` 就放掉 DTR。Pico `stdio_usb_connected()` 看的就是 DTR → 「主機開 port 之前 / 關掉之後」Pico 的輸出全部丟掉。
- **1200 baud 魔術值**：`pico_usb_reset` 預設 `PICO_ENABLE_USB_RESET_VIA_BAUD_RATE=1`（應用未直接用 TinyUSB 時），`PICO_USB_RESET_MAGIC_BAUD_RATE=1200`：主機把 CDC 設成 1200 baud → 板子**重開進 BOOTSEL**（程式不跑了）。所以 `stty ... 1200`、`Serial(..., 1200)` 都不要用。
- 板子也提供 vendor reset interface（`PICO_ENABLE_USB_RESET_VIA_VENDOR_INTERFACE`），讓 `picotool` 可以在不按按鈕的情況下重開（見 `pico-sdk.md` 燒錄章節）。

---

## 4. 協定設計

### 4.1 文字 vs 二進位

| | 文字（`printf("%d,%d\n")` + 主機 `split`） | 二進位（struct + 框架 + CRC） |
|---|---|---|
| 開發速度 | 最快，可直接用 `cat` 看 | 要寫 encoder/decoder |
| 大小 | 16 個 int16，每個 1–6 字元 + 逗號 → 約 32–112 B | 32 B payload + 12 B 標頭/CRC + COBS 2 B ≈ **46 B** |
| Pico CPU | `printf` 格式化慢（尤其 float） | 幾乎只有搬移 + CRC |
| 主機 CPU | Python `split` + `int()` 每欄位都有成本 | `struct.unpack` / `array.array` 一次解 |
| 錯誤偵測 | 只有「格式不對」 | CRC 抓位元錯誤 |
| 同步 | 天然以 `\n` 同步 | 需要框架（COBS / SLIP / sync+len） |

建議：除錯期用文字；要效能時切二進位，**兩者用不同 port 或不同模式，不要混在同一條串流**（printf 的 debug 字串會打斷 frame；若一定要混，COBS 能在下一個 0x00 重新同步，只損失那一個 frame）。

### 4.2 框架方式比較

| 方式 | 規則 | 最壞額外負擔 | 重新同步 | 備註 |
|---|---|---|---|---|
| 分隔字元（`\n`） | 文字專用 | 0 | 下一個 `\n` | 資料不可含 `\n` |
| **COBS** + 0x00 | 把所有 0x00 消掉，0x00 當 frame 結尾 | ⌈n/254⌉ B + 1 B 分隔 | 下一個 0x00 | 開銷固定可預測；本檔推薦 |
| SLIP（RFC 1055） | `END=0xC0` 結尾；資料中的 0xC0 → `0xDB 0xDC`，0xDB → `0xDB 0xDD` | 最壞 2 倍 | 下一個 0xC0 | 實作最簡單 |
| sync + 長度前綴 | `AA 55 len payload crc` | 固定標頭 | 找下一個 `AA 55` 再驗 CRC | 長度欄錯誤時可能等很久；必須有 CRC |
| 固定長度 | 每 frame 固定 N byte | 0 | **很難**（錯一個 byte 之後全錯位） | 不建議單獨使用 |

### 4.3 COBS（Consistent Overhead Byte Stuffing）

規則：把資料切成「最多 254 個非零 byte + 一個 0」的組；每組前面放一個碼 = 該組非零 byte 數 + 1，並刪掉那個 0。碼 `0xFF` 表示「254 個非零、後面沒有隱含的 0」。最後再補一個 0x00 當 frame 分隔（不屬於 COBS 本體）。

手算範例 `11 22 00 33`：
1. 第一組 `11 22` 後面接 0 → 碼 = 2+1 = `03`，輸出 `03 11 22`
2. 第二組 `33` 到結尾（結尾視為有個 0）→ 碼 = 1+1 = `02`，輸出 `02 33`
3. 加分隔 → `03 11 22 02 33 00`

解碼：讀碼 `03` → 複製 2 個 byte `11 22`，碼不是 FF 且後面還有資料 → 補 `00`；讀碼 `02` → 複製 `33`，已到結尾 → 不補。

| 原始 | COBS（含結尾 00） |
|---|---|
| `00` | `01 01 00` |
| `00 00` | `01 01 01 00` |
| `11 22 00 33` | `03 11 22 02 33 00` |
| `11 22 33 44` | `05 11 22 33 44 00` |
| `11 00 00 00` | `02 11 01 01 01 00` |
| `01 02 … FE`（254 個非零） | `FF 01 02 … FE 00` |

（以上與 Wikipedia 範例表一致，且已用下方程式驗證。）

C 實作（與平台無關，已在主機上 fuzz 測試：0–700 byte 隨機資料來回、輸出不含 0x00、長度 ≤ n + n/254 + 1）：

```c
#include <stdint.h>
#include <stddef.h>
// out 至少要 n + n/254 + 1 byte。回傳編碼長度（不含結尾 0x00，呼叫端自己補）。
size_t cobs_encode(const uint8_t *in, size_t n, uint8_t *out) {
    size_t code_idx = 0, o = 1;
    uint8_t code = 1;
    for (size_t i = 0; i < n; i++) {
        if (in[i] == 0) {
            out[code_idx] = code; code_idx = o++; code = 1;
        } else {
            out[o++] = in[i]; code++;
            if (code == 0xFF && i + 1 < n) { out[code_idx] = code; code_idx = o++; code = 1; }
        }
    }
    out[code_idx] = code;
    return o;
}
// 輸入不含結尾 0x00。回傳解碼長度；格式錯誤回傳 0（空 frame 也是 0，呼叫端用長度檢查區分）。
size_t cobs_decode(const uint8_t *in, size_t n, uint8_t *out) {
    size_t i = 0, o = 0;
    while (i < n) {
        uint8_t code = in[i++];
        if (code == 0 || i + code - 1 > n) return 0;
        for (uint8_t k = 1; k < code; k++) out[o++] = in[i++];
        if (code != 0xFF && i < n) out[o++] = 0;
    }
    return o;
}
```

Python 版見 §6.2 `frameparser.py`。

### 4.4 SLIP（RFC 1055）簡版

```c
#define SLIP_END 0xC0
#define SLIP_ESC 0xDB
#define SLIP_ESC_END 0xDC
#define SLIP_ESC_ESC 0xDD
size_t slip_encode(const uint8_t *in, size_t n, uint8_t *out) {   // out 至少 2n+1
    size_t o = 0;
    for (size_t i = 0; i < n; i++) {
        if (in[i] == SLIP_END)      { out[o++] = SLIP_ESC; out[o++] = SLIP_ESC_END; }
        else if (in[i] == SLIP_ESC) { out[o++] = SLIP_ESC; out[o++] = SLIP_ESC_ESC; }
        else out[o++] = in[i];
    }
    out[o++] = SLIP_END;
    return o;
}
```

（RFC 1055 也建議在 frame **前面**也送一個 END，清掉線路雜訊造成的半個 frame。）

### 4.5 sync + 長度前綴 + 重新同步（Python，已測）

關鍵：**驗證失敗只丟 1 byte 再往後找 sync**，不要丟整個「宣稱的長度」，否則一個假 sync 會吃掉後面的好 frame。

```python
import struct, binascii
SYNC = b'\xAA\x55'
def lp_build(payload: bytes) -> bytes:          # AA 55 | len u16 LE | payload | crc16(len+payload)
    body = struct.pack('<H', len(payload)) + payload
    return SYNC + body + struct.pack('<H', binascii.crc_hqx(body, 0xFFFF))

class LPParser:
    def __init__(self, max_len=1024):
        self.buf = bytearray(); self.max_len = max_len; self.bad = 0
    def feed(self, chunk):
        self.buf += chunk; out = []
        while True:
            i = self.buf.find(SYNC)
            if i < 0:                               # 保留最後 1 byte（可能是 0xAA）
                del self.buf[:max(0, len(self.buf) - 1)]; break
            del self.buf[:i]
            if len(self.buf) < 4: break
            ln = struct.unpack_from('<H', self.buf, 2)[0]
            if ln > self.max_len:                   # 長度不合理 → 假 sync
                del self.buf[:1]; self.bad += 1; continue
            if len(self.buf) < 4 + ln + 2: break    # 還沒收完
            body = bytes(self.buf[2:4 + ln])
            crc = struct.unpack_from('<H', self.buf, 4 + ln)[0]
            if binascii.crc_hqx(body, 0xFFFF) != crc:
                del self.buf[:1]; self.bad += 1; continue
            out.append(body[2:]); del self.buf[:4 + ln + 2]
        return out
```

缺點：假 sync 帶一個「合理但很大」的長度時，parser 會等到收滿才發現 CRC 錯 → 延遲尖峰。`max_len` 設越小越好。

### 4.6 檢查碼與 CRC

| 方法 | 長度 | 能抓到 | 抓不到 | 成本 |
|---|---|---|---|---|
| XOR 全部 byte | 1 B | 任一 bit 位置上奇數個錯 | byte 互換、同位置偶數個錯 | 最低 |
| 8-bit 加總 | 1 B | 多數單一錯誤 | byte 順序互換、互相抵消的錯 | 低 |
| CRC-16 | 2 B | 所有 ≤16 bit 的連續錯誤（burst）、所有單/雙 bit 錯（短 frame） | 極少數 | 中（查表或逐 bit） |
| CRC-32 | 4 B | 所有 ≤32 bit burst | 更少 | 中 |

**CRC-16/CCITT-FALSE**（poly 0x1021、init 0xFFFF、不反射、xorout 0）；check 值 `"123456789"` → **0x29B1**：

```c
uint16_t crc16_ccitt(const uint8_t *p, size_t n) {
    uint16_t crc = 0xFFFF;
    while (n--) {
        crc ^= (uint16_t)(*p++) << 8;
        for (int i = 0; i < 8; i++)
            crc = (crc & 0x8000) ? (uint16_t)((crc << 1) ^ 0x1021) : (uint16_t)(crc << 1);
    }
    return crc;
}
```

**CRC-32（IEEE 802.3 / zlib）**（反射 poly 0xEDB88320、init 0xFFFFFFFF、xorout 0xFFFFFFFF）；check 值 → **0xCBF43926**：

```c
uint32_t crc32_ieee(const uint8_t *p, size_t n) {
    uint32_t crc = 0xFFFFFFFFu;
    while (n--) {
        crc ^= *p++;
        for (int i = 0; i < 8; i++)
            crc = (crc >> 1) ^ (0xEDB88320u & (0u - (crc & 1u)));   // 無分支
    }
    return ~crc;
}
```

Python 對應（已實測，與上面 C 結果相同）：

```python
import binascii, zlib
binascii.crc_hqx(data, 0xFFFF)   # CRC-16/CCITT-FALSE → b'123456789' 得 0x29B1
zlib.crc32(data)                 # CRC-32 → 0xCBF43926（binascii.crc32 相同）
# binascii.crc_hqx(data, 0) 是 CRC-16/XMODEM（init 0）
```

- 兩端**參數必須完全一致**（poly、init、反射、xorout、CRC 欄位本身的 byte 序）。先用 `"123456789"` 的 check 值互相驗證。
- CRC 計算範圍要明確：本檔範例 = 「COBS 前的 header + payload」，CRC 本身以 little-endian 附在最後。
- 速度：逐 bit 版每 byte 8 次迴圈；要更快可用 256 項查表版（每 byte 1 次查表），或讓 **RP2350 DMA sniffer** 在搬資料時順便算（支援 CRC-32、CRC-32 bit 反轉、CRC-16-CCITT、CRC-16-CCITT 反轉、XOR、32-bit 加總；用法與 SNIFF_EN 陷阱見 `pico-dma.md` §2.8、§4.10）。sniffer 設定要與軟體 CRC-16/CCITT-FALSE 或 zlib CRC-32 完全相同時需要的 seed / invert / reverse 組合 ⚠️未驗證，先與上面的軟體版比對 check 值。

### 4.7 標頭設計：版本、型別、序號、長度、時間戳

本檔範例標頭（10 B，little-endian）：

| offset | 型別 | 欄位 | 用途 |
|---|---|---|---|
| 0 | u8 | `ver` | 協定版本；不認得就丟（日後改格式不會誤解） |
| 1 | u8 | `type` | 1=SAMPLE、2=PING、3=PONG、4=CMD… |
| 2 | u16 | `seq` | 序號（16-bit 回繞）；接收端算 `(seq - last - 1) & 0xFFFF` 得到遺失數 |
| 4 | u32 | `t_us` | 裝置時間 `time_us_32()`（約 71.6 分鐘回繞） |
| 8 | u16 | `len` | payload 長度（與實際長度比對，多一層檢查） |
| 10 | … | payload | |
| 10+len | u16 | CRC-16 | 對 offset 0..10+len-1 |

- 序號用途：偵測遺失（裝置端 500 ms 逾時丟資料、主機緩衝溢位）、偵測重複（重送時）、配對請求與回應（PING/PONG）。**每種 type 各自計數**，或統一一個計數器但接收端只對同一 type 比較。
- 時間戳用途：主機計算裝置端實際取樣率與 jitter（`Δt_us`），不受 USB 傳輸延遲影響。

### 4.8 ACK / 重送

| 策略 | 做法 | 適合 |
|---|---|---|
| 不確認（fire-and-forget） | 只用 seq 統計遺失 | 感測資料串流（遺失一筆無所謂、要最新值） |
| Stop-and-wait | 送 → 等 ACK(seq) → 逾時重送（最多 N 次）→ 下一筆 | 指令、設定值（必須送到） |
| 滑動視窗 | 最多 W 筆未確認；ACK 帶「已連續收到的最大 seq」 | 大量且必須可靠（如傳檔），W 越大吞吐越高 |

- 接收端要**去重**：記住最近處理過的 seq，重複的就只回 ACK、不重做動作（idempotent）。
- 逾時至少要 > 量到的 RTT p99（§6.4 的 ping 可以量）。
- USB CDC 本身在 USB 層有 CRC 與重送，**線路位元錯誤極少**；真正會丟資料的是緩衝溢位 / 逾時丟棄 / 程式 bug / 重新列舉。UART 線路（尤其長線、高 baud）才會有位元錯誤。

### 4.9 位元組序與 struct packing

- RP2350（Cortex-M33 與 Hazard3 RISC-V）是 little-endian；x86-64 與 arm64 Linux 也是 little-endian。仍應**在協定中明訂 little-endian**，並在兩端都用明確的格式。
- C struct 有 padding，例：`struct { uint8_t a; uint32_t b; uint16_t c; }` 在 32-bit ARM/RISC-V 與 x86-64 上 `sizeof` 都是 **12**（a@0、b@4、c@8）；加 `__attribute__((packed))` 後是 **7**（c@5）（本機 gcc 實測 -m32 與 64-bit）。
- `packed` 的風險：成員可能未對齊。Cortex-M33 的單一 LDR/LDRH/STR/STRH 支援未對齊（但 LDRD/LDM 會 fault，Device memory 也會 fault）；**Hazard3 對未對齊 load/store 產生例外**。GCC 存取 packed 成員時會自動用安全的方式，但若取 `&pkt->field` 轉成 `uint32_t *` 再解參考就可能出錯（GCC 有 `-Waddress-of-packed-member` 警告）。
- **建議：明確序列化**（逐 byte 放），不依賴 struct 記憶體配置：

```c
static inline void put_u16le(uint8_t *p, uint16_t v) { p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8); }
static inline void put_u32le(uint8_t *p, uint32_t v) {
    p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8); p[2] = (uint8_t)(v >> 16); p[3] = (uint8_t)(v >> 24);
}
static inline uint16_t get_u16le(const uint8_t *p) { return (uint16_t)(p[0] | (p[1] << 8)); }
static inline uint32_t get_u32le(const uint8_t *p) {
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}
// float：memcpy 到 uint32_t 再 put_u32le（兩端都是 IEEE 754 binary32）
```

Python `struct` 格式（本機實測）：

| 前綴 | 位元組序 | 大小 / 對齊 |
|---|---|---|
| `<` | little | 標準大小、**不對齊**（協定用這個） |
| `>` / `!` | big（網路序） | 標準、不對齊 |
| `=` | 本機 | 標準、不對齊 |
| `@`（預設） | 本機 | 本機大小、**有對齊 padding，但結尾不補** |

| 碼 | C 型別 | 大小 | 碼 | C 型別 | 大小 |
|---|---|---|---|---|---|
| `B` / `b` | uint8 / int8 | 1 | `Q` / `q` | uint64 / int64 | 8 |
| `H` / `h` | uint16 / int16 | 2 | `f` / `d` | float / double | 4 / 8 |
| `I` / `i` | uint32 / int32 | 4 | `x` / `Ns` | pad byte / N bytes | 1 / N |

```python
import struct, array
struct.pack('<IhB', 0x12345678, -2, 255)   # → 78 56 34 12 fe ff ff
struct.calcsize('<BIH')   # 7（同 packed）
struct.calcsize('@BIH')   # 10 —— 與 C 的 sizeof 12 不同！（結尾不補 padding）
struct.calcsize('@BIH0I') # 12（用 0I 強制結尾對齊）
HDR = struct.Struct('<BBHIH'); HDR.unpack_from(buf, 0)   # 預先編譯格式，較快
list(struct.iter_unpack('<hh', payload))                 # 重複結構
array.array('h', payload)                                # 一次把 bytes 變 int16 陣列（本機序 = little）
int.from_bytes(b'\x34\x12', 'little')                    # 4660
```

---

## 5. 吞吐量與延遲計算

### 5.1 UART（8N1：start + 8 data + stop = 10 bit / byte）

| baud | 每 byte 時間 | 最大 B/s | 46 B frame / s | 32 B FIFO 填滿時間 |
|---|---|---|---|---|
| 9600 | 1.04 ms | 960 | 20 | 33 ms |
| 115200 | 86.8 µs | 11 520 | 250 | 2.78 ms |
| 460800 | 21.7 µs | 46 080 | 1 001 | 0.69 ms |
| 921600 | 10.85 µs | 92 160 | 2 003 | 0.35 ms |
| 3 000 000 | 3.33 µs | 300 000 | 6 521 | 0.11 ms |

- RP2350 UART 上限 UARTCLK/16（datasheet 範例：125 MHz 時 7.8 Mbaud）；實際上限常由 USB-serial 轉接器決定（各型號不同 ⚠️未驗證）。
- 分數除頻：`uart_init` 回傳實際 baud；兩端誤差太大（一般經驗值 >2–3%）會出現亂碼 ⚠️經驗值。

### 5.2 USB CDC（Full Speed）

- 線路 12 Mbit/s；bulk 端點最大封包 64 B；USB frame 每 1 ms 一個。
- USB 2.0 規格中 Full Speed bulk 每 frame 最多 19 筆 64 B 交易 → 理論上限約 1.2 MB/s ⚠️未驗證（未直接查閱規格表，為常見引用數字）；實際 CDC 吞吐量受裝置端 `tud_task` 頻率、FIFO 大小（2.2.0+ 只有 64 B）、每段 flush、主機驅動影響，**必須實測**（§6.3 rx.py 會印 KiB/s）。
- **USB CDC 的 baud 設定不影響速度**：設 115200 或 921600 都一樣（但不要設 1200）。

### 5.3 延遲來源與取捨

| 來源 | 量級 | 控制方法 |
|---|---|---|
| 裝置端 `tud_task` 週期 | ≤ 1 ms（`PICO_STDIO_USB_TASK_INTERVAL_US`） | 寫出時 `stdio_usb` 本身會呼叫 `tud_task` |
| USB frame / 主機輪詢 | ~1 ms 量級 ⚠️未驗證 | 無法控制 |
| 批次（BATCH 個 frame 才寫一次） | BATCH / 產生速率 | 批次大小 = 吞吐與延遲的取捨 |
| 主機 read timeout | 最多 timeout | `read(max(1, in_waiting))` + 小 timeout；不要 `read(大N)` 等滿 |
| Python 每 frame 處理 | µs 級 ⚠️依機器 | 一次 feed 多個 frame；用 `struct.Struct` 預編譯 |
| ROS 2 timer 輪詢週期 | = 週期 | 2–5 ms 常見；或用 thread 阻塞讀 |

類 Nagle 的取捨：「累積滿一塊再送」→ 吞吐高、延遲高；「每筆立刻送」→ 延遲低、封包多、吞吐低。折衷：**累積到 N byte 或超過 T µs 就送**（兩個條件先到者觸發）。

```c
// Pico：累積到 1 KB 或 2 ms 就送
if (used >= 1024 || (used && time_us_32() - t_first >= 2000)) {
    stdio_put_string((const char *)txbuf, (int)used, false, false);
    used = 0;
}
```

### 5.4 減少 syscall / 函式呼叫次數

- 主機：每次 `read()` 都是一次 syscall；Python 的 `read_until` / `readline` 每 byte 一次 → 大量資料時改「讀一大塊 + 自己切」。
- Pico：`putchar` 一次一 byte 會每 byte 拿一次鎖並走 CRLF 判斷 → 改 `stdio_put_string` 一次一大塊（micro-ROS 官方 transport 用 `putchar` 逐 byte 送，是可以改進的地方）。
- 寫入要檢查回傳值並迴圈（`write` / `tud_cdc_write` 都可能只寫一部分）。

---

## 6. 完整範例：Pico 送二進位 frame → Python 收、驗 CRC、量吞吐與延遲

協定：`frame = COBS( header(10 B) + payload + CRC16_LE ) + 0x00`，標頭見 §4.7。Pico 持續送 SAMPLE（16 個 int16），收到 PING 就回 PONG（payload 原樣帶回）。

### 6.1 Pico 端

`frame.h`（與平台無關，主機也能編）：

```c
#include <stdint.h>
#include <stddef.h>
#define PROTO_VER   1
#define HDR_LEN     10
#define MAX_PAYLOAD 240
static inline void put_u16le(uint8_t *p, uint16_t v) { p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8); }
static inline void put_u32le(uint8_t *p, uint32_t v) {
    p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8); p[2] = (uint8_t)(v >> 16); p[3] = (uint8_t)(v >> 24);
}
uint16_t crc16_ccitt(const uint8_t *p, size_t n);
size_t cobs_encode(const uint8_t *in, size_t n, uint8_t *out);
// 組一個完整 frame（含 COBS 與結尾 0x00）到 out，回傳總長度（最多 254 B）
static size_t build_frame(uint8_t *out, uint8_t type, uint16_t seq, uint32_t t_us,
                          const uint8_t *payload, uint16_t len) {
    uint8_t raw[HDR_LEN + MAX_PAYLOAD + 2];
    if (len > MAX_PAYLOAD) return 0;
    raw[0] = PROTO_VER; raw[1] = type;
    put_u16le(raw + 2, seq); put_u32le(raw + 4, t_us); put_u16le(raw + 8, len);
    for (uint16_t i = 0; i < len; i++) raw[HDR_LEN + i] = payload[i];
    uint16_t crc = crc16_ccitt(raw, HDR_LEN + len);
    put_u16le(raw + HDR_LEN + len, crc);
    size_t n = cobs_encode(raw, HDR_LEN + len + 2, out);
    out[n++] = 0x00;
    return n;
}
```

`crc_cobs.c`：§4.6 的 `crc16_ccitt`（可加 `crc32_ieee`）+ §4.3 的 `cobs_encode` / `cobs_decode`，開頭 `#include <stdint.h>` 與 `<stddef.h>`。

`main.c`：

```c
// main.c — Pico 2：持續送 SAMPLE frame；收到 PING 就回 PONG（payload 原封不動帶回）
#include <string.h>
#include "pico/stdlib.h"
#include "pico/stdio_usb.h"
#include "frame.h"

#define T_SAMPLE 1
#define T_PING   2
#define T_PONG   3
#define BATCH    8                               // 一次 write 送 8 個 frame（批次化）

size_t cobs_decode(const uint8_t *in, size_t n, uint8_t *out);

#define FRAME_MAX 254                            // COBS(10+240+2) + 0x00
static uint8_t txbuf[(BATCH + 2) * FRAME_MAX];  // 前 2 格留給 PONG
static uint8_t rxacc[300];                       // 累積到 0x00 為止的 COBS 資料
static size_t  rxlen;

static uint16_t get_u16le(const uint8_t *p) { return (uint16_t)(p[0] | (p[1] << 8)); }

// 解一個 frame；是 PING 就把 PONG 寫到 out，回傳寫了幾個 byte
static size_t on_frame(const uint8_t *enc, size_t n, uint8_t *out) {
    uint8_t raw[HDR_LEN + MAX_PAYLOAD + 2];
    if (n > sizeof raw + 1) return 0;
    size_t m = cobs_decode(enc, n, raw);
    if (m < HDR_LEN + 2) return 0;
    if (crc16_ccitt(raw, m - 2) != get_u16le(raw + m - 2)) return 0;   // CRC 錯：丟棄
    uint16_t len = get_u16le(raw + 8);
    if (raw[0] != PROTO_VER || (size_t)(HDR_LEN + len + 2) != m) return 0;
    if (raw[1] == T_PING)
        return build_frame(out, T_PONG, get_u16le(raw + 2), time_us_32(), raw + HDR_LEN, len);
    return 0;
}

int main(void) {
    stdio_init_all();
    stdio_set_translate_crlf(&stdio_usb, false); // 二進位資料：關掉 \n -> \r\n
    while (!stdio_usb_connected()) sleep_ms(10); // 等主機開 port（DTR 拉高）
    sleep_ms(50);

    uint16_t seq = 0;
    for (;;) {
        size_t used = 0;
        // 1) 非阻塞收資料：until = 現在 → 只檢查一次
        char in[64];
        int k = stdio_get_until(in, sizeof in, make_timeout_time_us(0));
        for (int i = 0; i < k; i++) {            // k < 0（PICO_ERROR_TIMEOUT）時不進迴圈
            uint8_t b = (uint8_t)in[i];
            if (b == 0x00) {                     // frame 結束
                if (rxlen && used + FRAME_MAX <= 2 * FRAME_MAX)
                    used += on_frame(rxacc, rxlen, txbuf + used);
                rxlen = 0;
            } else if (rxlen < sizeof rxacc) {
                rxacc[rxlen++] = b;
            } else {
                rxlen = 0;                       // 太長：丟掉，等下一個 0x00 重新同步
            }
        }
        // 2) 產生 BATCH 個 SAMPLE frame
        for (int f = 0; f < BATCH; f++) {
            uint8_t pl[32];
            for (int i = 0; i < 16; i++)
                put_u16le(pl + 2 * i, (uint16_t)(int16_t)(seq * 7 + i * 1000 - 8000));
            used += build_frame(txbuf + used, T_SAMPLE, seq++, time_us_32(), pl, sizeof pl);
        }
        // 3) 一次寫出；cr_translation=false → 原始位元組
        stdio_put_string((const char *)txbuf, (int)used, false, false);
    }
}
```

CMake：用 §2.1 的範本（`add_executable(app main.c crc_cobs.c)`、`pico_enable_stdio_usb(app 1)`、`pico_enable_stdio_uart(app 0)`）。

### 6.2 主機端 `frameparser.py`（已測：隨機切塊餵入、插入垃圾、翻轉 1 bit → 只丟壞的那個 frame）

```python
import struct, binascii

HDR = struct.Struct('<BBHIH')      # ver, type, seq, t_us, len  = 10 bytes
PROTO_VER = 1

def crc16_ccitt(data: bytes) -> int:          # CRC-16/CCITT-FALSE
    return binascii.crc_hqx(data, 0xFFFF)

def cobs_encode(data: bytes) -> bytes:
    out = bytearray(b'\x00'); code_idx = 0; code = 1
    for i, b in enumerate(data):
        if b == 0:
            out[code_idx] = code; code_idx = len(out); out.append(0); code = 1
        else:
            out.append(b); code += 1
            if code == 0xFF and i + 1 < len(data):
                out[code_idx] = code; code_idx = len(out); out.append(0); code = 1
    out[code_idx] = code
    return bytes(out)

def build_frame(typ: int, seq: int, t_us: int, payload: bytes) -> bytes:
    body = HDR.pack(PROTO_VER, typ, seq & 0xFFFF, t_us & 0xFFFFFFFF, len(payload)) + payload
    return cobs_encode(body + struct.pack('<H', crc16_ccitt(body))) + b'\x00'

def cobs_decode(data: bytes) -> bytes:
    out = bytearray(); i = 0; n = len(data)
    while i < n:
        code = data[i]; i += 1
        if code == 0 or i + code - 1 > n:
            raise ValueError('bad COBS')
        out += data[i:i + code - 1]; i += code - 1
        if code != 0xFF and i < n:
            out.append(0)
    return bytes(out)

class FrameParser:
    """餵任意長度的 bytes 進來，吐出 (type, seq, t_us, payload)。自動跳過壞 frame。"""
    def __init__(self, max_frame=512):
        self.buf = bytearray(); self.max_frame = max_frame
        self.ok = self.bad_crc = self.bad_cobs = self.bad_len = self.lost = 0
        self.last_seq = {}                     # 每種 type 各自追蹤 seq

    def feed(self, chunk: bytes):
        self.buf += chunk
        frames = []
        while True:
            z = self.buf.find(0)
            if z < 0:
                if len(self.buf) > self.max_frame:   # 太久沒看到分隔符號：丟掉，等下一個 0x00
                    self.buf.clear()
                break
            enc = bytes(self.buf[:z]); del self.buf[:z + 1]
            if not enc:
                continue                             # 連續 0x00（空 frame）
            try:
                raw = cobs_decode(enc)
            except ValueError:
                self.bad_cobs += 1; continue
            if len(raw) < HDR.size + 2:
                self.bad_len += 1; continue
            body, crc_rx = raw[:-2], struct.unpack_from('<H', raw, len(raw) - 2)[0]
            if crc16_ccitt(body) != crc_rx:
                self.bad_crc += 1; continue
            ver, typ, seq, t_us, ln = HDR.unpack_from(body, 0)
            if ver != PROTO_VER or ln != len(body) - HDR.size:
                self.bad_len += 1; continue
            prev = self.last_seq.get(typ)
            if prev is not None:
                self.lost += (seq - prev - 1) & 0xFFFF   # seq 是 16-bit，會回繞
            self.last_seq[typ] = seq
            self.ok += 1
            frames.append((typ, seq, t_us, body[HDR.size:]))
        return frames
```

### 6.3 主機端 `rx.py`：吞吐量（有 pyserial 用 pyserial，沒有就用標準庫；兩條路都在 pty 上測過）

```python
#!/usr/bin/env python3
# 用法：python3 rx.py /dev/ttyACM0 [秒數]
import sys, time, struct
from frameparser import FrameParser

def open_port(path, baud=115200):
    try:
        import serial
        s = serial.Serial(path, baud, timeout=0.05)   # CDC 的 baud 無意義但要合法、不要 1200
        s.reset_input_buffer()
        return lambda: s.read(max(1, s.in_waiting))   # 一次讀「目前有的全部」
    except ImportError:
        import os, termios, tty, select
        fd = os.open(path, os.O_RDWR | os.O_NOCTTY)
        tty.setraw(fd)
        termios.tcflush(fd, termios.TCIFLUSH)
        def rd():
            r, _, _ = select.select([fd], [], [], 0.05)
            return os.read(fd, 4096) if r else b''
        return rd

def main():
    path = sys.argv[1] if len(sys.argv) > 1 else '/dev/ttyACM0'
    dur = float(sys.argv[2]) if len(sys.argv) > 2 else 5.0
    read = open_port(path)
    p = FrameParser()
    nbytes = 0; t0 = time.perf_counter(); last = t0; first = True
    while time.perf_counter() - t0 < dur:
        chunk = read()
        nbytes += len(chunk)
        for typ, seq, t_us, payload in p.feed(chunk):
            if typ == 1 and first:
                print('first samples:', struct.unpack_from('<4h', payload)); first = False
        now = time.perf_counter()
        if now - last >= 1.0:
            el = now - t0
            print(f'{nbytes/el/1024:8.1f} KiB/s  frames ok={p.ok} ({p.ok/el:.0f}/s) '
                  f'crc={p.bad_crc} cobs={p.bad_cobs} len={p.bad_len} lost={p.lost}')
            last = now

if __name__ == '__main__':
    main()
```

判讀：`lost > 0` → 裝置端丟資料（主機讀太慢 / 500 ms 逾時）或主機緩衝溢位；`crc/cobs > 0` 但 `lost` 對應增加 → 線路或 CRLF 問題；剛開始的 1–2 個 `cobs` 錯誤通常是開 port 時接到半個 frame，正常。

### 6.4 主機端 `ping.py`：來回延遲（RTT）（已用 pty 模擬裝置測試）

```python
#!/usr/bin/env python3
# 用法：python3 ping.py /dev/ttyACM0 [次數]
import sys, time, struct, serial
from frameparser import FrameParser, build_frame
T_PING, T_PONG = 2, 3

port = sys.argv[1] if len(sys.argv) > 1 else '/dev/ttyACM0'
count = int(sys.argv[2]) if len(sys.argv) > 2 else 200
s = serial.Serial(port, 115200, timeout=0.005)
s.reset_input_buffer()
p = FrameParser(); rtt_us = []; timeouts = 0
for i in range(count):
    t0 = time.perf_counter_ns()
    s.write(build_frame(T_PING, i, 0, struct.pack('<Q', t0)))
    deadline = time.perf_counter() + 0.5; got = False
    while not got and time.perf_counter() < deadline:
        for typ, seq, t_us, pl in p.feed(s.read(max(1, s.in_waiting))):
            if typ == T_PONG and seq == (i & 0xFFFF):
                rtt_us.append((time.perf_counter_ns() - struct.unpack('<Q', pl)[0]) / 1000)
                got = True
    timeouts += not got
rtt_us.sort()
if rtt_us:
    n = len(rtt_us)
    print(f'n={n} timeouts={timeouts} min={rtt_us[0]:.0f} median={rtt_us[n//2]:.0f} '
          f'p99={rtt_us[min(n-1, n*99//100)]:.0f} max={rtt_us[-1]:.0f} us')
```

- 回報 min / median / p99 / max，不要只看平均（延遲分布有長尾）。
- 時鐘對齊（類 NTP）：PONG 帶裝置時間 `t_dev`；主機送出 `t1`、收到 `t2` → 裝置時鐘相對主機的偏移 ≈ `t_dev − (t1 + t2)/2`（假設來回對稱）。單向延遲無法在不同步時鐘下直接量。
- 範例裝置端在送 SAMPLE 串流時順便回 PONG，所以 RTT 包含排在前面的 SAMPLE 批次；要量純延遲可先讓裝置停送 SAMPLE。

---

## 7. ROS 2 橋接

### 7.1 rclpy：timer 非阻塞輪詢（不阻塞 executor，全部在 executor 執行緒內）

```python
#!/usr/bin/env python3
# pico_bridge.py — serial ⇄ ROS 2。執行：python3 pico_bridge.py --ros-args -p port:=/dev/ttyACM0
import array, struct
import rclpy
from rclpy.node import Node
from rclpy.executors import ExternalShutdownException
from std_msgs.msg import Int16MultiArray, Int32
import serial
from frameparser import FrameParser, build_frame

class PicoBridge(Node):
    def __init__(self):
        super().__init__('pico_bridge')
        self.declare_parameter('port', '/dev/ttyACM0')
        self.declare_parameter('poll_period', 0.002)
        port = self.get_parameter('port').value
        self.ser = serial.Serial(port, 115200, timeout=0)    # timeout=0：read 立即返回
        self.ser.reset_input_buffer()
        self.parser = FrameParser()
        self.tx_seq = 0
        self.pub = self.create_publisher(Int16MultiArray, 'pico/samples', 10)
        self.sub = self.create_subscription(Int32, 'pico/cmd', self.on_cmd, 10)
        self.timer = self.create_timer(self.get_parameter('poll_period').value, self.poll)

    def poll(self):
        n = self.ser.in_waiting
        if n == 0:
            return
        for typ, seq, t_us, pl in self.parser.feed(self.ser.read(n)):
            if typ == 1:
                msg = Int16MultiArray()
                msg.data = array.array('h', pl)   # int16[] 欄位底層就是 array('h')，免逐元素轉換
                self.pub.publish(msg)

    def on_cmd(self, msg: Int32):
        self.ser.write(build_frame(4, self.tx_seq, 0, struct.pack('<i', msg.data)))
        self.tx_seq += 1

def main():
    rclpy.init()
    node = PicoBridge()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.ser.close()
        node.destroy_node()
        rclpy.try_shutdown()

if __name__ == '__main__':
    main()
```

- `array.array('h', bytes)`：rosidl_python 產生的訊息類別對 int16 序列欄位接受 typecode `'h'` 的 `array.array`；`array('h', b)` 用本機位元組序解讀（x86-64 / arm64 皆 little-endian）。
- 一個 SAMPLE frame 發一則訊息，每秒上千則時 ROS 2 本身的發布成本會變瓶頸 → 把多個 frame 的樣本合併成一則訊息發布（批次化）。
- QoS：感測串流可用 `qos_profile_sensor_data`（best effort），細節與相容性見 `ros2.md` §3。

### 7.2 rclpy：獨立 reader thread（延遲較低、不用輪詢）

```python
import threading
# 在 __init__ 中（serial 改用 timeout=0.05，讓 thread 能定期檢查停止旗標）：
self._stop = threading.Event()
self._th = threading.Thread(target=self._reader, daemon=True)
self._th.start()

def _reader(self):
    while not self._stop.is_set():
        data = self.ser.read(max(1, self.ser.in_waiting))   # 最多阻塞 50 ms
        for typ, seq, t_us, pl in self.parser.feed(data):
            if typ == 1:
                msg = Int16MultiArray(); msg.data = array.array('h', pl)
                self.pub.publish(msg)      # 從非 executor 執行緒 publish ⚠️未驗證執行緒安全保證（常見用法）

# 結束時：self._stop.set(); self._th.join(); self.ser.close()
```

- 若 thread 與 callback 共用狀態（如 `tx_seq`、parser）要加 `threading.Lock`。保守做法：thread 只負責讀資料放進 `queue.Queue`，由 timer callback 取出並 publish。
- 不要在 callback 內 `ser.read()` 阻塞等資料（`timeout=None`）：單執行緒 executor 會被卡住，其他 callback 都不跑（`ros2.md` §5.3–5.4）。

### 7.3 rclcpp 版大綱

```cpp
// 1) 建構子：fd_ = serial_open(port, B115200)（§3.5 的 C 函式，VMIN=0/VTIME=0）
// 2) 方案 A：timer 輪詢
timer_ = create_wall_timer(std::chrono::milliseconds(2), [this] {
    uint8_t buf[4096];
    ssize_t n = ::read(fd_, buf, sizeof buf);          // 非阻塞，可能 0 或 -1(EAGAIN)
    if (n > 0) for (auto &f : parser_.feed(buf, n)) pub_->publish(to_msg(f));
});
// 3) 方案 B：std::thread 用 poll() 阻塞等資料，收到後 publish（rclcpp publisher 可跨執行緒呼叫 ⚠️依 rcl 文件確認）
//    解構時設 atomic<bool> stop_，join thread，close(fd_)
// 4) 方向 host→MCU：subscription callback 內 build_frame + write_all(fd_, ...)
```

### 7.4 micro-ROS 概觀

| 項目 | 說明 |
|---|---|
| 架構 | MCU 上跑 micro-ROS **client**（rclc API，底層 Micro XRCE-DDS）；主機跑 **micro-ROS agent**，把 client 代理成一般 ROS 2 node / topic |
| Pico 官方 repo | `micro_ros_raspberrypi_pico_sdk`，有 `jazzy` 分支；`libmicroros/libmicroros.a` 是**預編譯**靜態庫 |
| 編譯旗標 | 預編譯庫的 toolchain：`-march=armv6-m -mcpu=cortex-m0plus -mthumb`（RP2040 用）。RP2350 ARM（Cortex-M33，ARMv8-M Mainline 相容 ARMv6-M 指令）實測可以編譯、連結（2026-11-12，pico-sdk 2.2.0、pico2、`../預製程式碼/micro-ros/` 三支程式），板上執行 ⚠️未驗證；**RP2350 RISC-V 模式不能用**此庫（需自行用 docker builder 重編 ⚠️未驗證可行性） |
| transport | `pico_uart_transport.c`：用 `stdio_init_all`、逐 byte `putchar` 寫、`getchar_timeout_us` 讀；在 `main` 中以 `rmw_uros_set_custom_transport(true, NULL, open, close, write, read)` 註冊 |
| 連線流程 | `rmw_uros_ping_agent(timeout_ms, attempts)` → `rclc_support_init` → `rclc_node_init_default` → `rclc_publisher_init_default` → `rclc_executor_spin_some` 迴圈 |
| agent 指令（README） | `micro-ros-agent serial --dev /dev/ttyACM0 -b 115200`（snap）或 docker `microros/micro-ros-agent:jazzy serial --dev /dev/ttyACM0 -b 115200`；ROS 2 套件形式 `ros2 run micro_ros_agent micro_ros_agent serial --dev /dev/ttyACM0 -b 115200` ⚠️未驗證（同 `ros2.md` §10） |

**自訂協定 vs micro-ROS**

| 條件 | 選擇 |
|---|---|
| 考場不能安裝軟體，agent / micro-ROS 庫沒有預裝 | **自訂協定 + rclpy 橋接 node**（本檔 §6–§7.1） |
| 題目已提供 micro-ROS 專案與 agent | 用 micro-ROS（訊息型別、QoS 由 ROS 2 處理） |
| 要極致吞吐 / 低延遲、資料格式簡單 | 自訂二進位協定（可完全控制批次與緩衝） |
| 要用很多 ROS 2 訊息型別、service、parameter | micro-ROS |

---

## 8. 除錯清單（症狀 → 原因 → 檢查 / 修正）

| # | 症狀 | 可能原因 | 檢查 / 修正 |
|---|---|---|---|
| 1 | 主機完全收不到 | 開錯 port（ttyACM0 是 Debug Probe、板子是 ttyACM1） | `ls -l /dev/serial/by-id/`、拔插比較、`python3 -m serial.tools.list_ports -v` |
| 2 | 同上 | 沒有 `pico_enable_stdio_usb(app 1)`（預設 USB stdio 關、UART 開） | 檢查 CMake；`picotool info -a` 看 binary info 是否有 "USB stdin / stdout" ⚠️ |
| 3 | 同上 | 沒呼叫 `stdio_init_all()`，或在 core 1 呼叫 | 在 core 0 的 main 開頭呼叫 |
| 4 | 開機訊息不見 | 主機開 port（DTR）之前的輸出被丟掉 | Pico 端 `while (!stdio_usb_connected()) sleep_ms(10);` 或 `PICO_STDIO_USB_CONNECT_WAIT_TIMEOUT_MS` |
| 5 | 主機程式比板子先啟動，之後一直沒資料 | 開 port 時裝置還沒列舉 / 燒錄後重新列舉，舊 fd 失效 | 程式在 open 失敗 / 讀到斷線例外時重試開啟；燒錄後重開程式 |
| 6 | 板子突然變成 USB 隨身碟（RP2350） | 主機把 baud 設成 1200 → 進 BOOTSEL | 不要用 1200；重新燒錄 |
| 7 | 二進位資料多出 0x0D，CRC 常錯 | pico 端 CRLF 轉換沒關（`printf`/`fwrite` 會轉） | §2.4：`stdio_set_translate_crlf(&stdio_usb,false)` 或 `stdio_put_string(...,false,false)` |
| 8 | 收到的 0x0D 變 0x0A、資料被回送給板子、讀要等換行 | 主機 tty 不是 raw（ICRNL / ECHO / ICANON） | `stty -F ... raw -echo`、或用 pyserial / cfmakeraw |
| 9 | 亂碼（UART） | 兩端 baud 不一致、TX/RX 沒交叉、沒共地、8N1 不一致 | 先用 115200 文字測；示波器/邏輯分析儀 ⚠️考場可能沒有 |
| 10 | 只收到一部分 / 要求 100 byte 只拿到 37 | `read` 本來就可能回傳較少 | 永遠迴圈累積到 parser；不要假設一次 read = 一個 frame |
| 11 | 不定期少資料、seq 跳號 | 主機讀太慢 → 裝置 500 ms 逾時丟棄；或兩個程式同時讀同一 port | 主機改大塊讀、批次處理；`fuser /dev/ttyACM0` ⚠️（若有）找另一個讀者；`exclusive=True` |
| 12 | 輸出很慢（~11 KB/s） | USB 與 UART stdio 同時開，被 UART 拖慢 | `pico_enable_stdio_uart(app 0)` 或 `stdio_filter_driver(&stdio_usb)` |
| 13 | 印到一半卡住 ~1 s | 在 IRQ 中 printf，或另一核心持有 stdio 鎖 | 不要在 IRQ 印；用 queue 交給主迴圈印 |
| 14 | ROS 2 node 其他 callback 不跑 | serial read 在 callback 中阻塞 | `timeout=0` + timer，或 reader thread（§7） |
| 15 | 開頭 1–2 個 frame 壞 | 開 port 時接到半個 frame | 正常；COBS 會在下一個 0x00 同步。開啟後 `reset_input_buffer()` |
| 16 | 解出的數值怪（大小顛倒、差 256 倍） | 位元組序不一致、struct padding 不同（`@` vs `<`） | 協定一律 `<`；C 端明確序列化（§4.9） |
| 17 | RISC-V 版本 HardFault / 例外，ARM 版正常 | packed struct 未對齊存取（Hazard3 不支援未對齊 load/store） | 改用逐 byte 序列化或 `memcpy` |

**通用除錯技巧**

```bash
timeout 2 cat /dev/ttyACM0 | xxd | head -20        # 看原始位元組：找 0x00 分隔、0x0d 0x0a
timeout 2 cat /dev/ttyACM0 | od -An -tx1 -v | head
stty -F /dev/ttyACM0 -a                            # 確認 -icanon -echo -icrnl -opost
```

- **迴路測試（loopback）**：Pico 端寫一個 echo 程式（收到什麼回什麼，`stdio_get_until` → `stdio_put_string(...,false,false)`），主機送已知序列比對 → 分離「主機程式問題」與「Pico 程式問題」。UART 轉接器可把自己的 TX 接 RX 先測主機端。
- 先用**文字**確認連線（`printf("alive %u\n", n++)`），再切二進位。
- 主機端先存檔（`cat > dump.bin`），用 Python 離線解析 → 可重現、可反覆修 parser。
- 在 frame 中放遞增 `seq` 與已知 pattern（像範例的 `seq*7 + i*1000 - 8000`），主機端驗證內容而不只驗 CRC。

---

## 9. 優化清單（由大到小）

1. **確認瓶頸在哪**：先量（`rx.py` 的 KiB/s、frames/s、lost；`ping.py` 的 RTT）。方法見 `03-optimize.md`。
2. **關掉不需要的 stdio driver**（UART 與 USB 同開會被 UART 拖慢）。
3. **文字 → 二進位**：資料量縮成 1/2–1/3，Pico 省掉 printf 格式化。
4. **批次化寫出**：Pico 累積多個 frame 一次 `stdio_put_string`；主機一次 `read(in_waiting)`。
5. **避免逐 byte API**：Pico 不用 `putchar` 迴圈；主機不用 `read_until`/`readline`/`read(1)` 處理大量資料。
6. **增大 TinyUSB CDC FIFO**（`CFG_TUD_CDC_TX_BUFSIZE` 等，2.2.0+ 預設只有 64）⚠️效果請實測。
7. **主機端解析向量化**：`struct.Struct` 預編譯、`array.array('h', payload)` 一次轉、多個 frame 合併成一則 ROS 訊息。
8. **CRC 加速**：查表版、或 DMA sniffer（`pico-dma.md`）；CRC-16 比 CRC-32 少一半欄位。
9. **延遲優先時**：減小批次、主機用 reader thread + 小 timeout，避免 timer 輪詢週期造成的延遲。
10. **UART 連線**：提高 baud（兩端同步改）、Pico 接收用 IRQ / DMA 避免 32 B FIFO 溢位。
11. **把資料產生與傳輸分到兩個核心**（core 1 產生、core 0 傳輸，用 queue；見 `multicore-sync.md`）⚠️ `stdio_usb` 必須在 core 0 初始化。
12. 每次優化後重新量，並確認 `crc/cobs/lost` 計數沒有增加（快但錯 = 0 分）。

---

## 10. 常見陷阱總表（一行版）

- `pico_enable_stdio_usb` 預設關；`pico_enable_stdio_uart` 預設開。
- `stdio_usb` 未連線（DTR=0）時輸出直接丟；主機不讀 500 ms 後也丟。
- CRLF 轉換預設開，`printf`/`putchar`/`puts`/`fwrite` 都會轉；二進位要用 `stdio_put_string(...,false,false)` 或關轉換。
- `PICO_STDIO_ENABLE_CRLF_SUPPORT=0` 時呼叫 `stdio_set_translate_crlf` 會 panic。
- CDC baud 無意義，但 **1200 baud = 重開進 BOOTSEL**。
- Linux tty 預設 cooked + echo：沒設 raw 會改資料並回送。
- `stty raw` 不含 `-echo`。
- `read()` / `os.read()` / `serial.read(n)` 可能回傳較少；`write` 可能寫一部分。
- pySerial `read_until`/`readline` 逐 byte，慢。
- Python `struct` 的 `@`（預設）與 C struct 大小可能不同；協定用 `<`。
- Hazard3 不支援未對齊 load/store；packed struct 取指標要小心。
- 2.2.0 起 TinyUSB CDC FIFO 從 256 改 64 B。
- 不要在 IRQ 中 printf；`stdio_usb` 在 core 0 初始化。
- ROS 2 callback 內不可阻塞讀 serial。

---

## 11. 向模型提問的範本

**範本 1：收不到 / 資料錯**
```
我用 RP2350（Pico 2，pico-sdk {{版本}}，{{ARM 或 RISC-V}}）透過 {{USB CDC /dev/ttyACM0 或 UART 轉接器 /dev/ttyUSB0 @ baud}} 傳資料給 Linux 主機。
Pico 端 CMake 的 stdio 設定：{{pico_enable_stdio_usb/uart 那幾行}}
Pico 端送資料的程式碼：{{貼上}}
主機端讀取方式：{{cat / pyserial / termios C，貼上程式}}
症狀：{{完全沒資料 / 多了 0x0D / 數值錯 / 偶爾少 frame}}
`timeout 2 cat {{port}} | xxd | head` 的輸出：{{貼上}}
請依「port 是否正確 → stdio driver 是否啟用 → DTR/連線時機 → CRLF 轉換 → 主機 termios raw → 框架/位元組序」的順序逐項判斷最可能原因，並給出最小修改。
```

**範本 2：設計協定**
```
我要在 Pico 2 與 {{Python / rclpy / C}} 主機之間傳 {{資料內容，例如：每 1 ms 一筆 16 個 int16 ADC 值}}，反方向傳 {{指令內容}}。
限制：{{不能安裝套件 / 必須可靠 / 延遲 < X ms / 吞吐 > Y KB/s}}。
請設計二進位協定：框架方式（COBS 或其他並說明理由）、標頭欄位與 byte offset（little-endian）、CRC 參數（poly/init/reflect/xorout 與 check 值）、序號與遺失偵測、是否需要 ACK/重送。
並給出 Pico C 端 encoder 與主機端 parser（要能從任意切塊與垃圾中重新同步），以及一個驗證測試。
```

**範本 3：吞吐量 / 延遲優化**
```
目前量測：{{rx.py 輸出，例如 85 KiB/s、frames 1900/s、lost=…}}；{{ping.py 的 min/median/p99}}。
目標：{{吞吐 ≥ … / p99 延遲 ≤ …}}。
Pico 端寫出方式：{{printf / putchar 迴圈 / stdio_put_string 批次 N 個}}，CDC FIFO 設定：{{預設或自訂}}。
主機端讀取方式：{{read_until / read(in_waiting) / os.read}}，是否在 ROS 2 node 中：{{是/否，timer 週期或 thread}}。
請先用數字估算各段上限（線路、USB、Pico CPU、主機解析、ROS 發布），指出瓶頸，再依「效益/風險」排序列出修改，每一項說明如何量測驗證且不破壞正確性（crc/lost 不可增加）。
```

**範本 4：ROS 2 橋接 node**
```
請寫一個 ROS 2 Jazzy 的 {{rclpy / rclcpp}} node：從 {{/dev/ttyACM0}} 讀取下列格式的 frame：{{貼上協定定義}}，
解析後發布到 {{topic 名稱}}（型別 {{例如 std_msgs/Int16MultiArray}}），並訂閱 {{topic}} 把指令編碼後寫回 serial。
要求：不阻塞 executor（說明你選 timer 輪詢或 reader thread 的理由）、裝置拔插後能自動重連、port 用 parameter 設定、
{{環境沒有 pyserial 時改用 termios}}。附上執行指令與用 `ros2 topic hz/echo` 驗證的方法。
```

**範本 5：讀官方原始碼確認行為**
```
以下是 pico-sdk {{檔案路徑}} 的片段：{{貼上}}
請說明：(1) {{函式}} 在 {{情境，例如 USB 未連線 / FIFO 滿 / 主機不讀}} 時的確切行為；(2) 相關的 PICO_CONFIG 巨集與預設值；
(3) 對我的程式 {{用途}} 有什麼影響，應該怎麼改。只根據貼上的程式碼回答，不確定處明確標示。
```
