# Pico 2 (RP2350) 上機考模板

> ⚠ 這些程式**只有在電腦上編譯通過**（pico-sdk 2.2.0、ARM），**沒有在真的板子上跑過**。
> 考試時第一件事：先燒一個進去看會不會動。所有要改的地方都標了 `// TODO(改這裡)`。

## 檔案 ↔ 題型

| 檔案 | 什麼時候用 |
|---|---|
| `app_serial.c` + `serial_proto.c/.h` | 電腦送資料給板子算、板子回結果（加總 / CRC / 排序 / 雜湊…）。封包：`AA 55 cmd seq len(u16) payload crc32` |
| `app_multicore.c` | 「用兩顆核心加速」、共用變數算錯（race）、一核收一核算 |
| `app_dma.c` | 搬資料 / 填值 / 硬體算 CRC32（DMA sniffer）/ 比 CPU 快多少 |
| `app_dma_pio.c` | DMA 跟 PIO 一起用（DREQ 控制節奏），CPU 完全不用動 |
| `app_pio.c` + `pio/*.pio` | PIO：echo、位元運算、位元流收送（`shift_out` 送、`bitstream_in` 收） |
| `timing.h` | 量時間：`time_us_64()`（微秒）、`cycles_now()`（CPU cycle） |

## Build

```bash
mkdir build && cd build
cmake -DPICO_BOARD=pico2 ..          # ARM Cortex-M33（預設，最穩）
make -j                               # 產生 app_xxx.uf2
# 只編一個：make -j app_serial
```
RISC-V（Hazard3）：`cmake -DPICO_BOARD=pico2 -DPICO_PLATFORM=rp2350-riscv ..`
（需要 `riscv32-unknown-elf-gcc` 工具鏈；Ubuntu 的 `gcc-riscv64-unknown-elf` 缺 C 函式庫，連結會失敗）
第一次 cmake 會從 GitHub 下載並編 picotool（要網路）；沒網路就先裝好 picotool。

## 燒錄

- **BOOTSEL 法**：按住板上 BOOTSEL 插 USB → 出現隨身碟 `RP2350` → 把 `app_xxx.uf2` 拖進去
- **picotool**：`picotool load -x app_xxx.uf2 -f`（`-x` 燒完執行，`-f` 強制讓正在跑的板子重開進 BOOTSEL）
- 看輸出：`screen /dev/ttyACM0 115200` 或 `minicom -D /dev/ttyACM0`（Python：`pyserial`）

## 常用 API 小抄

| API | 一句話 |
|---|---|
| `stdio_init_all()` / `stdio_usb_connected()` | 開 USB 序列埠 / 電腦有沒有打開序列埠 |
| `stdio_get_until(buf,len,make_timeout_time_us(us))` | 一次讀多個 byte，有 timeout |
| `stdio_put_string(p,n,false,false)` | 送原始 bytes（不加換行、不轉 \r\n） |
| `stdio_set_translate_crlf(&stdio_usb,false)` | 關掉 \n→\r\n |
| `multicore_launch_core1(fn)` | core1 開始跑 fn |
| `multicore_fifo_push_blocking / pop_blocking` | 兩核間硬體 FIFO 傳 u32（RP2350 深度 4；SDK launch/lockout 也用它） |
| `queue_init / queue_add_blocking / queue_remove_blocking / queue_try_remove` | 安全的跨核佇列（傳 struct） |
| `spin_lock_init(spin_lock_claim_unused(true))` | 要一個 spinlock（24~31 號）並設為未上鎖 |
| `spin_lock_blocking(l)` → `spin_unlock(l, save)` | 上鎖（關中斷）/ 解鎖 |
| `critical_section_init / _enter_blocking / _exit` | 包好的 spinlock |
| `mutex_enter_blocking / mutex_exit`，`auto_init_mutex(m)` | 可長時間持有的鎖（不能在中斷用） |
| `dma_claim_unused_channel(false)` | 要 DMA 通道，沒有回 -1 |
| `dma_channel_get_default_config(ch)` | 預設：32-bit、**讀遞增、寫不遞增**、DREQ_FORCE（全速）、chain_to=自己（不串接） |
| `channel_config_set_transfer_data_size / _read_increment / _write_increment / _dreq` | 設定 |
| `dma_channel_configure(ch,&c,dst,src,dma_encode_transfer_count(n),start)` | n = 次數不是 bytes；RP2350 n < 2^28；SDK 2.2.0 起才有這函式（`app_dma*.c` 已替 2.0/2.1 補上） |
| `dma_channel_wait_for_finish_blocking(ch)` / `dma_channel_unclaim(ch)` | 等完成 / 歸還 |
| `dma_start_channel_mask(mask)` | 同時啟動多個通道 |
| `dma_sniffer_enable(ch, DMA_SNIFF_CTRL_CALC_VALUE_CRC32R, false)` | 硬體 CRC（其他：`_CRC32`、`_CRC16`、`_CRC16R`、`_SUM`、`_EVEN`）；zlib crc32 = CRC32R + 初值 FFFFFFFF + `dma_sniffer_set_output_reverse_enabled(true)` + 讀出後 `^0xFFFFFFFF` |
| `pio_add_program / pio_claim_unused_sm / pio_sm_init / pio_sm_set_enabled` | 載入、要 SM、設定、啟動 |
| `sm_config_set_out_shift(&c, 右移?, autopull?, 門檻)` / `_in_shift` | OSR / ISR 方向與自動 pull/push |
| `sm_config_set_clkdiv(&c, div)` | PIO 速度 = clk_sys / div |
| `pio_sm_put_blocking / pio_sm_get_blocking` | 寫 TX FIFO / 讀 RX FIFO |
| `pio_get_dreq(pio, sm, is_tx)` | 給 DMA 用的 DREQ 編號 |

文件：
- SDK 硬體 API：https://www.raspberrypi.com/documentation/pico-sdk/hardware.html
- SDK 高階 API（multicore / sync / queue / stdio）：https://www.raspberrypi.com/documentation/pico-sdk/high_level.html
- RP2350 Datasheet：https://datasheets.raspberrypi.com/rp2350/rp2350-datasheet.pdf
  - 第 3.1 節 SIO（spinlock、FIFO、doorbell）
  - 第 11 章 PIO（指令集、FIFO、autopush/autopull）
  - 第 12.6 節 DMA（DREQ、sniffer/CRC、transfer count）
- 範例：https://github.com/raspberrypi/pico-examples（`dma/`、`pio/`、`multicore/`）

## 常見陷阱 ⚠

1. **DMA count 是「次數」不是 bytes**：4096 bytes 用 32-bit 傳 → count = 1024。RP2350 只用低 28 bits（[31:28] 是 MODE），用 `dma_encode_transfer_count(n)` 包起來。
   **預設寫位址不遞增**：memory→memory copy 一定要 `channel_config_set_write_increment(&c, true)`。
2. **CRLF 轉換**：printf 的 `\n` 預設會變 `\r\n`，二進位資料會壞。用 `stdio_put_string(...,false,false)`，並關掉 translate。
3. **app_serial 裡不要 printf**：文字會混進二進位封包。
4. **忘了 unclaim**：DMA 通道 / PIO SM / 指令空間都有限，用完要 `dma_channel_unclaim`、`pio_remove_program_and_unclaim_sm`。
5. **volatile**：兩核共用、或 DMA/中斷會改的變數要 `volatile`，不然編譯器會把它放暫存器不重讀。但 volatile **不是**原子操作，`counter++` 照樣會 race，要用鎖。
6. **沒有 cache 但有匯流排競爭**：DMA 和兩顆 CPU 同時打同一塊 SRAM 會互相等；資料分開放在不同 bank 比較快。
7. **core1 stack 只有 2KB**（`PICO_CORE1_STACK_SIZE`）：core1 裡不要開大陣列區域變數，改用 `static` / 全域。
8. **要等 USB 連上**：`stdio_init_all()` 後立刻 printf 會丟掉，先 `while(!stdio_usb_connected()) sleep_ms(50);`
9. **臨界區要短**：spinlock 會關中斷 + 另一核忙等；先算區域結果，最後才鎖一下合併。
10. **RP2350 spinlock 勘誤**：SDK 預設 `PICO_USE_SW_SPIN_LOCKS=1`（用軟體原子指令實作），API 一樣用，不用管。
11. **RP2350 GPIO 開機是隔離狀態**：一定要 `gpio_init` / `gpio_set_function` / `pio_gpio_init`，不然讀寫都沒反應。
12. **DMA sniffer 全晶片只有一組**：同一時間只能給一個通道算 CRC。
13. **USB 速度上限約 1 MB/s**（Full Speed 12 Mbit/s）：大量資料時傳輸才是瓶頸 → 二進位、大封包、多板分工。

## 設計審查紀錄（DMA / timing）

2026-11-11 對照 pico-sdk 2.2.0 原始碼（Docker `pico-build` 的 /opt/pico-sdk）逐行檢查。暫存器說明是 SDK 從 RP2350 datasheet 複製來的；datasheet PDF 太大無法直接抓，以 header 文字為準。**仍未上板驗證**，`app_dma` 會自己印 PASS/FAIL。

| # | 項目 | 結果 | 依據 |
|---|---|---|---|
| 1 | Sniffer CRC32 = zlib：CRC32R + 初值 FFFFFFFF + OUT_REV + 軟體 `^FFFFFFFF` | OK（註解寫清楚推導） | `regs/dma.h` SNIFF_CTRL_CALC（0x1 = IEEE 多項式 + 資料位元反轉）、OUT_REV/OUT_INV（只作用在讀出、不影響計算）；pico-examples `dma/sniff_crc/sniff_crc.c` 同樣設定（DMA_SIZE_8、seed -1、OUT_REV、CRC32R）。Python 模擬「MSB 先引擎 + 資料反轉」→ "123456789" = CBF43926；8-bit 與 32-bit（不 BSWAP）都等於 zlib |
| 1a | 不確定處 | 註解標明 | 範例只驗 residue==0（對位元反轉不變），所以 OUT_REV 是否必要靠暫存器文字推導；FAIL 時看值是否 0x649C2FD3（= 反轉）。寫入 SNIFF_DATA 是否受 OUT_REV 影響文件沒寫 → 不要分段續算 |
| 2 | `dma_sniffer_enable` 跟 OUT_REV 的順序 | OK | SDK `dma_sniffer_enable` 用 `hw_write_masked` 只改 DMACH/CALC/EN，不會清掉先設的 OUT_REV；`force_channel_enable=false` + `channel_config_set_sniff_enable(&c,true)` 寫進 CTRL_TRIG 一樣有效（CH0_CTRL_TRIG_SNIFF_EN） |
| 2a | 讀寫累加器、等完成 | OK | `dma_sniffer_set/get_data_accumulator` = SNIFF_DATA（「開始前寫初值，通道完成後讀結果」）；`dma_channel_wait_for_finish_blocking` 等 CTRL_TRIG.BUSY=0 並加 compiler barrier |
| 3 | transfer count 編碼 | **已修**：全部改用 `dma_encode_transfer_count(n)`，`dma_xfer` 檢查 n==0 / n≥2^28 | `regs/dma.h` CH0_TRANS_COUNT：COUNT 28 bits、MODE [31:28]（1=TRIGGER_SELF、F=ENDLESS）；SDK 2.2.0 `dma_channel_configure` 的參數是 *encoded* count，不會幫你遮掉高 4 bits（`invalid_params_if` 預設不啟用） |
| 3a | `app_dma.c` 第 4 段「預設讀寫都遞增」 | **已修（bug）**：加 `channel_config_set_write_increment(&c,true)`，並加 memcmp 檢查；README 小抄同步更正 | SDK `dma_channel_get_default_config`：read_increment=true、**write_increment=false** |
| 3b | DREQ_FORCE、chain_to、irq_quiet、claim/unclaim | OK | 預設 DREQ_FORCE(63)=TREQ 0x3f 永久請求；chain_to=自己（CHAIN_TO 重置值 0 會串到 ch0，SDK 預設已避開）；irq_quiet=false 且沒開 IRQ 無影響；`dma_claim_unused_channel(false)` 失敗回 -1（dma.c）；用完 unclaim |
| 3c | 位址對齊 | 註解提醒 | 32-bit 傳輸用 u32 陣列（天生 4-byte 對齊）；CRC 用 8-bit 任意位址都可 |
| 4 | DMA + PIO | OK + 小修 | `pio_get_dreq` → `PIO_DREQ_NUM`（dreq.h：PIO0_TX0..3=0..3、RX0..3=4..7）；寫 `&pio->txf[sm]`、讀 `&pio->rxf[sm]`（structs/pio.h）；TX 讀遞增/寫不動、RX 讀不動/寫遞增；32-bit 對應 echo.pio autopull 32 + `in x,32` + push；echo 沒 fifo_join（TX/RX 都要用）；`dma_start_channel_mask` 同時啟動避免「只開 TX → RX 滿 → SM 卡 push → TX 卡住」。**已修**：檢查 `pio_add_program` 回傳負數（pio.h）、unclaim 前也等 ch_tx 完成 |
| 5 | timing.h SysTick（M33） | OK（改用具名常數） | `regs/m33.h`：SYST_CSR bit0 ENABLE、bit2 CLKSOURCE（1=處理器時脈）、RVR 24-bit 且重置值 UNKNOWN、寫 CVR = 清 0；`structs/systick.h` 的 `systick_hw`；SDK 本身沒用 SysTick |
| 5a | timing.h RISC-V | OK（沒有 RISC-V 工具鏈，未編譯） | `regs/rvcsr.h` MCOUNTINHIBIT 位址 0x320、重置值 0x5（CY bit0、IR bit2）；`hardware/riscv.h` 的 `riscv_clear_csr` 會把名字貼進 `csrci`，所以用數字 0x320 |

## 設計審查紀錄（multicore / serial / PIO）

審查日期 2026-11-11，依據 pico-sdk 2.2.0 原始碼（`/opt/pico-sdk`，以下路徑相對於它）、pico-examples、`../ros2/frame.py`。
編譯：`cmake -DPICO_BOARD=pico2` + `make` 全部 5 個 app 通過、無 warning。serial_proto.c 另在 PC 上用 Python `zlib` 產生的封包測過。

### multicore（app_multicore.c）
| 項目 | 結果 | 依據 |
|---|---|---|
| `core1_main(void)` 簽名、`multicore_launch_core1` | OK | `pico_multicore/include/pico/multicore.h` |
| core1 stack = `PICO_CORE1_STACK_SIZE` 預設 `PICO_STACK_SIZE`=0x800（2KB）；core1 只用小 struct，大陣列是 static | OK | multicore.h:32-39 |
| launch 時 SDK 用 FIFO 做握手（`cmd_sequence`），最後一個回應 core0 已讀走 → 模板之後讀 FIFO 不會讀到殘值 | OK | `pico_multicore/multicore.c` `multicore_launch_core1_raw()` |
| FIFO 深度：RP2350 是 4（RP2040 是 8）；SDK 建議一般資料用 queue | OK，註解改正 | multicore.h `multicore_fifo` 說明 |
| spinlock 原本用 `spin_lock_instance(claim)` 沒初始化 | **已修**：改 `spin_lock_init(spin_lock_claim_unused(true))`（官方寫法；雖然 runtime init 的 `spin_locks_reset()` 也會清） | `hardware_sync_spin_lock/sync_spin_lock.c`、`hardware/sync.h` 鎖號分配表（24~31 給 claim） |
| RP2350 erratum E2：SDK 預設 `PICO_USE_SW_SPIN_LOCKS=1`，改用 `ldaexb/strexb` 軟體鎖，API 不變 | OK | `hardware_sync_spin_lock/include/hardware/sync/spin_lock.h:13-16` |
| spinlock / critical_section 會關中斷、內含 acquire/release fence | OK | spin_lock.h（`__mem_fence_acquire`、`stlb`）、`pico_sync/include/pico/critical_section.h` |
| `queue_init(q, sizeof, 8)`：同時最多 4 個工作 + 1 個停止訊號 ≤ 8 | OK | `pico_util/include/pico/util/queue.h` |
| 4 塊 buffer 輪流用：單一 worker 依序回結果，`sent-got<4` 保證不覆蓋正在算的 buffer | OK | 邏輯推導 |
| race 示範：反組譯確認 `counter++` 是 `ldr/adds/str` 三條指令（真的會 race） | OK | build 出的 `app_multicore.dis` |
| FIFO 函式本身沒有 memory barrier | **已修**：push 前 / pop 後加 `__dmb()`（保險，成本極低） | multicore.h `multicore_fifo_push_blocking_inline()` |
| 兩核 printf：SDK 預設 `PICO_STDOUT_MUTEX=1`，單一 printf 已互斥；`SAFE_PRINTF` 給「多行要連著印」用 | OK，註解補充 | `pico_stdio/include/pico/stdio.h:19`、`pico_stdio/stdio.c` |
| mutex 不能在 IRQ 裡 blocking 使用 | OK | `pico_sync/include/pico/mutex.h` |

### serial（app_serial.c、serial_proto.c/.h ↔ ros2/frame.py）
| 項目 | 結果 | 依據 |
|---|---|---|
| 欄位順序 `AA 55 cmd seq len(u16LE) payload crc32(u32LE)`，CRC 範圍 cmd..payload，標準 zlib CRC-32 | OK，PC 測試：C 送出的封包與 `frame.encode()` 逐 byte 相同 | frame.py `encode()` |
| len > `FRAME_MAX_PAYLOAD`(8192) 丟掉不回；frame.py `CHUNK_BYTES`=4096 ≤ 8192 | OK | serial_proto.h / frame.py |
| SUM_U32：u32 相加自動 mod 2^32；len 非 4 倍數時忽略尾巴（與 `unpack_u32`、fake_pico.py 一致） | OK；原本把 `uint8_t[]` 轉 `uint32_t*`（strict aliasing 不嚴謹）**已改 memcpy** | C11 6.5p7 |
| 收到一半卡住（電腦端重開、假 AA 55 吃掉後面的資料）會永遠等不到 | **已修**：新增 `proto_reset()/proto_busy()`，閒置 100ms 自動重新找 AA 55 | — |
| `stdio_get_until(buf,len,until)`：`until` 是絕對時間；回傳讀到的 byte 數或 `PICO_ERROR_TIMEOUT`(-2) | OK | `pico_stdio/stdio.c`、`pico/error.h` |
| 輸入方向不做 CRLF 轉換（直接呼叫 `in_chars`）；輸出 `stdio_put_string(..,false,false)` 走 `out_chars` 原樣送出 | OK | `pico_stdio/stdio.c` |
| `PICO_STDIO_DEFAULT_CRLF=0` 會影響 USB driver（`PICO_STDIO_USB_DEFAULT_CRLF` 預設等於它；SDK 是 INTERFACE library，PRIVATE 定義會套到 SDK 原始碼） | OK，已確認 flags.make 有帶 | `pico_stdio_usb/include/pico/stdio_usb.h:26-28` |
| USB 未連線（DTR=0）時輸出直接丟掉；電腦不讀超過 `PICO_STDIO_USB_STDOUT_TIMEOUT_US`=0.5s 也丟 | OK，註解補充（pyserial 開 port 預設 DTR=1） | `pico_stdio_usb/stdio_usb.c` `stdio_usb_out_chars()` |
| 輸入方向 USB 有流量控制（RX buffer 64B 滿了 host 會等），不會掉 byte | OK | `pico_stdio_usb/include/tusb_config.h` |
| baudrate 1200 會讓板子重開進 BOOTSEL | OK，註解提醒 | stdio_usb.h `PICO_STDIO_USB_RESET_MAGIC_BAUD_RATE` |
| `stdio_init_all()` 不會印任何開機訊息；只有 panic/assert 會印字 | OK | `pico_stdio/stdio.c` |
| ⚠ 電腦端 `serial_bridge.py` 的 `on_bytes()`（CRC32）**不能切包**：CRC 無法分包後在電腦端合併（Pico 每包都從 0 開始算） | **已改**：送出前擋下 > `CHUNK_BYTES`（4096，`frame.py`）的資料並印 error，不會再白等 3 次逾時。上限 4096 比 Pico 的 8192 嚴；資料大時：`CHUNK_BYTES` 改 8192、加大 `FRAME_MAX_PAYLOAD`，或協定加「起始 crc」欄位 | serial_bridge.py |
| 壞 CRC 時 Pico 丟掉整包再找 AA 55，frame.py 只往後挪 1 byte；USB 不會掉 byte，所以實務上沒差 | OK（差異已知） | frame.py `FrameParser.feed()` |

### PIO（app_pio.c、pio/*.pio）
| 項目 | 結果 | 依據 |
|---|---|---|
| `sm_config_set_out_shift/in_shift(c, shift_right, auto, threshold)`；threshold 32 寫成 0 = 32 | OK | `hardware_pio/include/hardware/pio.h:649,668`；regs `PULL_THRESH` 說明 |
| echo：`out x,32`(autopull) → `in x,32` → `push`（autopush 關）；介面沒改（app_dma_pio.c 不受影響） | OK | pio.h、RP2350 datasheet PIO 章 |
| shift_out：`.side_set 1` 非 opt → 每條都要寫 side；編碼 `0x6101 / 0xb142` 確認 side+delay 正確 | OK | pioasm 產生的 `shift_out.pio.h` |
| shift_out 與 pico-examples `pio/spi` 的 `spi_cpha0` 同結構（`out side 0 [1]` / `side 1 [1]`） | OK | pico-examples pio/spi/spi.pio |
| shift_out 腳位初值沒設 | **已修**：`pio_sm_set_pins_with_mask(...,0,...)` + `pio_sm_set_pindirs_with_mask`（同 pico-examples spi） | pico-examples pio/spi |
| bitstream_in：`wait 0/1 pin 1` 是相對 `in_base`；與 pico-examples `clocked_input` 相同；IN_COUNT 預設 0=32 不遮罩 | OK | regs `PINCTRL_IN_BASE`、`SHIFTCTRL_IN_COUNT` 說明；pico-examples pio/clocked_input |
| 左移 + MSB 先送 → 收到的字 == 送出的字 | OK | 推導 |
| 速度：bitstream_in 每 bit ≥ 3 cycle，送端 clkdiv 建議 ≥ 2 | 註解補充 | 推導 |
| `pio_gpio_init` → `gpio_set_function` 會開 IE 並清除 RP2350 pad ISO | OK | `hardware_gpio/gpio.c` |
| `pio_add_program` 失敗回負數，原本直接轉 uint | **已修**：檢查 `< 0`；claim SM 失敗時也 `pio_remove_program` | pio.h:971 |
| loopback 讀 RX 原本會永遠卡住 | **已修**：100ms timeout | — |
| 時脈：150MHz/10/4 = 3.75 Mbit/s | OK | — |

### CMakeLists.txt
`PICO_BOARD` 在 `pico_sdk_import.cmake` 前設定、`pico_stdlib / pico_multicore / pico_sync / hardware_pio / hardware_dma` 名稱、`pico_enable_stdio_usb 1 / uart 0`、`pico_add_extra_outputs`、`pico_generate_pio_header`（每個 target 各自產生）→ 全部 OK，build 成功。

### 仍不確定（沒有實機，請考試時先驗證）
- 「指令因 autopull 停住時 side-set 仍輸出」：依 datasheet PIO 章的 side-set 說明及 pico-examples spi 的用法推定；datasheet PDF 太大沒能逐字再核一次。
- `__dmb()` 在 Cortex-M33（無 cache、in-order）上實務上可能不需要，加了只是保險。
- race 示範「一定會」少加：兩核同時跑 20 萬次，實際遺失多少依時序而定（偶爾可能很少）。
