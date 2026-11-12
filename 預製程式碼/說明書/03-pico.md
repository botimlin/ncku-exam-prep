# 第 3 章　pico/：Pico 2（RP2350）上的 pico-sdk 範本（序列埠協定、雙核心、DMA、PIO、計時）

> 本章對應的檔案：`預製程式碼/pico/` 全部 14 個檔案｜驗證狀態：5 個 app 在電腦上編譯通過（ARM：pico-sdk 2.2.0 與 2.1.1，0 個 warning；RISC-V：用替代工具鏈編過）；`serial_proto.c` 與 `app_serial.c` 的封包處理在電腦上模擬測過；**沒有任何一個程式在真的板子上跑過 ⚠️**｜最後核對：2026-11-12（commit d102c17）

## 3.0 30 秒版：什麼時候打開這一章

- 題目出現「Pico」「RP2350」「pico-sdk」「.uf2」「燒錄」「/dev/ttyACM」→ 先看 3.3.1（怎麼編譯、燒錄、看輸出）。
- 題目是「電腦送資料給板子算、板子回結果」（加總、CRC、排序、雜湊）→ 開 `app_serial.c` + `serial_proto.h`，見 3.3.3～3.3.5 與食譜 3.4.6。
- 題目有「race condition」「共用變數算錯」「spinlock」「臨界區太長」「一核收一核算」→ 開 `app_multicore.c`，見 3.3.6、食譜 3.4.1、3.4.2。
- 題目有「DMA」「count 是筆數不是位元組」「claim / unclaim」「sniffer」「硬體 CRC」→ 開 `app_dma.c`，見 3.3.8、食譜 3.4.3、3.4.4。
- 題目有「PIO」「OSR / ISR / X / Y」「autopull / autopush」「位元流」→ 開 `app_pio.c` 和 `pio/*.pio`，見 3.3.10～3.3.13、食譜 3.4.5。
- 題目要「量時間、比加速倍數」→ `timing.h`，見 3.3.7 與 3.5。
- 最常改的 3 個地方：`app_serial.c:51`（加新指令）、`app_multicore.c:80`（core1 真正的計算）、`app_dma.c:27` / `app_dma_pio.c:34`（資料量）。
- **考場第一件事**：先編譯並燒一個 `app_multicore.uf2` 或 `app_dma.uf2`，確認板子會印字、self-test 是 PASS。這些程式從沒上過板。

## 3.1 檔案總表

| 檔案 | 行數 | 做什麼 | 什麼時候用 | 驗證狀態 |
|---|---|---|---|---|
| `CMakeLists.txt` | 52 | 一個 CMake 專案編出 5 個 app，stdio 走 USB | 每次 build | ✅ 編譯通過（ARM 2.2.0 / 2.1.1；RISC-V 替代工具鏈） |
| `pico_sdk_import.cmake` | 121 | 從 SDK 複製來的「找 SDK」腳本，不用改 | 每次 cmake | ✅ 與 SDK 2.2.0 `external/pico_sdk_import.cmake` 逐字相同（`diff` 無差異） |
| `serial_proto.h` | 47 | 封包格式、指令代碼、`frame_t`、函式宣告 | 序列埠題 | ✅ 電腦上模擬測過 |
| `serial_proto.c` | 101 | 軟體 CRC32（查表）、收封包狀態機、送封包 | 序列埠題 | ✅ 電腦上模擬測過（與 `ros2/frame.py` 對打） |
| `app_serial.c` | 88 | USB 二進位封包伺服器：ECHO / SUM_U32 / CRC32 | 電腦送資料、Pico 算 | ✅ 電腦上模擬測過；⚠️ 沒上板 |
| `app_multicore.c` | 137 | race 示範 + spinlock / critical_section 修法 + queue 派工 | 雙核心、鎖、pipeline | ✅ 編譯；⚠️ 沒上板 |
| `app_dma.c` | 141 | DMA copy / fill / sniffer CRC32 / 跟 CPU 比速度 | DMA、硬體 CRC | ✅ 編譯；sniffer 設定用 Python 模型驗證；⚠️ 沒上板 |
| `app_dma_pio.c` | 95 | DMA 依 DREQ 餵 PIO、收 PIO | DMA + PIO 串接 | ✅ 編譯；⚠️ 沒上板 |
| `app_pio.c` | 102 | PIO echo 測試 + shift_out → bitstream_in 自我回環 | PIO 題 | ✅ 編譯；⚠️ 沒上板 |
| `timing.h` | 69 | `PRINT_US`、`cycles_init/now/since`（ARM SysTick / RISC-V mcycle）、`speedup` | 量時間 | ✅ 兩種架構都編譯並看過反組譯；⚠️ 沒上板 |
| `pio/echo.pio` | 26 | TX FIFO → OSR → X → ISR → RX FIFO | PIO 入門、DMA+PIO | ✅ pioasm 2.2.0 組譯 |
| `pio/bitstream_in.pio` | 35 | CLK 上升沿取樣 DATA，每 32 bit 自動 push | 收位元流 | ✅ pioasm 組譯；⚠️ 沒上板 |
| `pio/shift_out.pio` | 34 | 把 32-bit 一位一位送到 DATA，side-set 產生 CLK | 送位元流 | ✅ pioasm 組譯；⚠️ 沒上板 |
| `README.md` | 168 | 檔案↔題型、build、燒錄、API 小抄、陷阱、設計審查紀錄 | 快速複習 | 內容已逐條核對，1 處過時（見 3.6.1） |

## 3.2 先懂這些概念

### 3.2.1 RP2350 有哪些硬體（本章會用到的）

下面的數字都從 pico-sdk 2.2.0 的 `src/rp2350/hardware_regs/include/hardware/platform_defs.h` 查到（不是憑記憶）：

| 資源 | 數量 | 出處 |
|---|---|---|
| DMA 通道 | 16 | `platform_defs.h:21` `NUM_DMA_CHANNELS` |
| PIO 區塊 | 3（pio0、pio1、pio2） | `platform_defs.h:27` `NUM_PIOS` |
| 每塊 PIO 的狀態機（SM） | 4 | `platform_defs.h:28` |
| 每塊 PIO 的指令記憶體 | 32 條 | `platform_defs.h:59` `PIO_INSTRUCTION_COUNT` |
| spinlock | 32 個（24～31 給 `spin_lock_claim_unused`） | `platform_defs.h:32`；`hardware_sync/include/hardware/sync.h:53` |
| 核心間 FIFO 深度 | 每個方向 4 個 u32（RP2040 是 8） | `pico_multicore/include/pico/multicore.h:128` |
| 預設 clk_sys | 150 MHz | `platform_defs.h:114` `SYS_CLK_HZ` |
| core1 stack | 0x800 = 2 KB | `pico_multicore/include/pico/multicore.h:32-37` |

- **兩種 CPU 二選一**：RP2350 有 2 顆 ARM Cortex-M33 和 2 顆 Hazard3 RISC-V，開機時只會用其中一種（由燒進去的映像檔決定）。編譯時用 `PICO_PLATFORM` 選：`rp2350-arm-s`（預設）或 `rp2350-riscv`。
- **GPIO 開機是隔離狀態**：pad 暫存器 `ISO` 重置值是 1（`regs/pads_bank0.h:195`），一定要呼叫 `gpio_init` / `gpio_set_function` / `pio_gpio_init` 才會動。重置時預設下拉（`PDE` 重置值 1，`pads_bank0.h:244`）。

### 3.2.2 編譯流程：從 .c / .pio 到 .uf2

```text
  pio/echo.pio ──pioasm──► build/echo.pio.h（指令陣列 + xxx_program_init）
        │                         │
  app_pio.c ──#include────────────┘
        │
   arm-none-eabi-gcc（或 riscv32-unknown-elf-gcc）編譯 + 連結 SDK
        │
        ▼
  app_pio.elf ──objdump──► app_pio.dis   （反組譯，查 counter++ 變幾條指令）
        │      ──linker──► app_pio.elf.map（每個函式 / 變數放在哪、多大）
        │      ──objcopy─► app_pio.bin / app_pio.hex
        └──picotool uf2 convert──► app_pio.uf2（拖進 BOOTSEL 隨身碟的檔案）
```

- `pioasm`、`picotool` 是 SDK 的兩個電腦端工具。`pioasm` 每次 build 會從 SDK 原始碼自己編（不用網路）；`picotool` 如果系統沒裝，第一次 cmake 會**從 GitHub 下載**（`pico-sdk/tools/Findpicotool.cmake:47` 印 `Downloading Picotool`），沒網路就會失敗。

### 3.2.3 USB 序列埠（USB CDC）與 stdio

- 板子插 USB 後，在 Linux 上出現 `/dev/ttyACM0`（第二片是 `/dev/ttyACM1`…）。這叫 USB CDC：USB 模擬一個序列埠。**baud rate 沒有意義**（USB 用自己的速度），但 **不要設 1200**：SDK 預設看到 1200 會重開進 BOOTSEL（`pico_stdio_usb/include/pico/stdio_usb.h:76` `PICO_STDIO_USB_RESET_MAGIC_BAUD_RATE 1200`）。
- `CMakeLists.txt` 對每個 app 呼叫 `pico_enable_stdio_usb(name 1)`，所以 `printf` / `getchar` 都走 USB。
- 電腦沒打開序列埠（DTR=0）時，板子輸出的東西會**直接丟掉**；電腦打開了但不讀，超過 `PICO_STDIO_USB_STDOUT_TIMEOUT_US`（預設 500000 µs，`stdio_usb.h:33`）也會丟。所以印字的 app 都先 `while (!stdio_usb_connected()) sleep_ms(50);`。
- printf 的 `\n` 預設會變成 `\r\n`（`pico_stdio/include/pico/stdio.h:31` `PICO_STDIO_DEFAULT_CRLF 1`）。傳文字沒差，**傳二進位會壞資料**，所以 `app_serial` 關掉它（見 3.3.5）。

### 3.2.4 二進位封包格式（`serial_proto.h` 與 `ros2/frame.py` 共用）

```text
 位元組  0     1     2     3     4       5       6 ... 6+len-1   6+len ... 9+len
       +-----+-----+-----+-----+-------+-------+---------------+-------------------+
       | AA  | 55  | cmd | seq | len_lo| len_hi|  payload[len] | crc32 (u32 小端)  |
       +-----+-----+-----+-----+-------+-------+---------------+-------------------+
                   |<------------ CRC32 計算範圍 ------------>|
 總長度 = 10 + len bytes；len 是 u16 小端；crc32 = 標準 zlib CRC-32（Python 的 zlib.crc32）
```

- **sync（AA 55）**：讓接收端在一串 bytes 裡找到封包開頭。
- **cmd**：指令代碼，`0x01` ECHO、`0x02` SUM_U32、`0x03` CRC32（`serial_proto.h:18-20`）。
- **seq**：序號，回覆會帶同一個 seq，電腦端用它配對問答。
- **小端（little-endian）**：多位元組數字「低位元組先送」。`0x1234` 送成 `34 12`。ARM 和 RISC-V 都是小端，所以 `memcpy` 就能轉。
- 實測（電腦上）：`encode(0x03, 9, b"")` = `aa 55 03 09 00 00 7d 4b 20 3c`（10 bytes，空 payload）。

### 3.2.5 race condition 與四種同步工具

**race condition（競爭條件）**：兩顆核心同時改同一個變數，結果跟執行順序有關、會算錯。`counter++` 在機器上是三條指令。實際反組譯（`build/app_multicore.dis`，ARM、SDK 2.2.0）：

```text
10000286:	6811      	ldr	r1, [r2, #0]     ← 讀 counter
10000288:	3101      	adds	r1, #1           ← 加 1
1000028a:	6011      	str	r1, [r2, #0]     ← 寫回
```

兩核都讀到 100、都寫回 101，就少加了一次（遺失更新）。

| 工具 | 是什麼 | 等鎖時 | 能在中斷（IRQ）裡用？ | 什麼時候用 |
|---|---|---|---|---|
| `spin_lock_t` | 最底層的硬體 / 軟體鎖 | 關中斷 + 忙等 | 可以 | 臨界區只有幾行、要最快 |
| `critical_section_t` | 包好的 spinlock | 關中斷 + 忙等 | 可以 | 同上，寫法乾淨、自動要鎖號 |
| `mutex_t` | 有擁有者的鎖 | 可以低功耗等 | 不行（`pico_sync/include/pico/mutex.h:33`：在 IRQ 裡 blocking 呼叫是壞主意） | 臨界區比較長（例如 printf 好幾行） |
| `queue_t` | 內建鎖的 FIFO 佇列 | 佇列滿/空時等 | `try_` 版本可以 | 兩核傳資料（傳 struct），最推薦 |

- **臨界區（critical section）**：被鎖保護、同一時間只能一個核心執行的那幾行。**越短越好**：spinlock 會關中斷，另一核在忙等，鎖越久另一核浪費越多。
- RP2350 硬體 spinlock 有勘誤（erratum），SDK 預設 `PICO_USE_SW_SPIN_LOCKS=1` 改用 `ldaexb/strexb` 軟體實作（`hardware_sync_spin_lock/include/hardware/sync/spin_lock.h:13-16`）。API 一樣，你不用管。上面 `add_many` 反組譯裡看得到 `ldaexb` / `strexb` / `stlb`。
- **volatile 不是鎖**：`volatile` 只叫編譯器每次真的讀寫記憶體，不保證三步不被插隊。
- **核心間 FIFO**（`multicore_fifo_push_blocking` / `pop_blocking`）：硬體的 u32 管道，RP2350 每個方向只有 4 格，SDK 的 `multicore_launch_core1` 和 lockout 也用它。一般資料用 `queue_t`。

### 3.2.6 DMA 是什麼、固定 5 步

**DMA（Direct Memory Access）**：一個「搬運工」硬體。CPU 告訴它「從哪讀、寫到哪、搬幾次、每次多大」，它自己搬，CPU 可以同時做別的事。

```text
 1 claim   dma_claim_unused_channel(false)      要一個空通道；沒有回 -1
 2 config  c = dma_channel_get_default_config(ch); channel_config_set_xxx(&c, ...)
 3 start   dma_channel_configure(ch, &c, 寫位址, 讀位址, dma_encode_transfer_count(次數), true)
 4 wait    dma_channel_wait_for_finish_blocking(ch)   等 BUSY 變 0
 5 unclaim dma_channel_unclaim(ch)                     還回去（通道只有 16 個）
```

- **transfer count = 傳輸「次數」不是 bytes**。每次搬多大由 `channel_config_set_transfer_data_size` 決定（`DMA_SIZE_8/16/32` = 1/2/4 bytes）。4096 bytes 用 32-bit 搬 → count = 1024。
- **RP2350 的 TRANS_COUNT 暫存器高 4 bits 是 MODE**：`regs/dma.h:68` `DMA_CH0_TRANS_COUNT_MODE_BITS 0xf0000000`，`0x0` NORMAL、`0x1` TRIGGER_SELF（跑完自己重來）、`0xf` ENDLESS（`regs/dma.h:72-74`）；次數只有低 28 bits（`regs/dma.h:99` `DMA_CH0_TRANS_COUNT_COUNT_BITS 0x0fffffff`）。所以 count 必須 < 2^28，而且要用 `dma_encode_transfer_count(n)` 包起來。直接傳 `0x10000005` 會變成「每次 5 筆、跑完自己重來」，永遠停不下來。
- SDK 2.2.0 的 `dma_encode_transfer_count`（`hardware_dma/include/hardware/dma.h:531-538`）在 RP2350 上會把 n 和 `0x0fffffff` 做 AND；`invalid_params_if` 預設不檢查，所以**傳太大的數字不會報錯，只會被截掉**。
- **DREQ（Data REQuest）**：周邊（PIO、UART…）告訴 DMA「我準備好了」的訊號。預設 `DREQ_FORCE`＝全速一直搬（記憶體↔記憶體用）。對 PIO 要設成 `pio_get_dreq(pio, sm, is_tx)`，DMA 才會「FIFO 有空位才寫、有資料才讀」。
- **sniffer**：DMA 裡唯一一組「旁聽」硬體，資料流過指定通道時順便算 CRC32 / CRC16 / 加總 / 奇偶。全晶片只有一組。

### 3.2.7 PIO 是什麼：OSR / ISR / X / Y

**PIO（Programmable I/O）**：晶片裡的小型狀態機，每個時脈執行一條指令，專門做精準的位元 I/O（自己做 SPI、讀奇怪的協定）。每個 SM 有：

| 名稱 | 意思 | 寬度 |
|---|---|---|
| TX FIFO | CPU / DMA → SM 的佇列 | 4 格 u32（join 後 8 格） |
| RX FIFO | SM → CPU / DMA 的佇列 | 4 格 u32（join 後 8 格） |
| OSR（Output Shift Register） | `pull` 從 TX FIFO 拿一個字放這裡，`out` 從這裡一次移出 n bits | 32 bit |
| ISR（Input Shift Register） | `in` 把 n bits 移進來，`push` 送到 RX FIFO | 32 bit |
| X、Y | 兩個暫存器，可當變數或計數器（`jmp x--`） | 32 bit |

- **autopull**：OSR 移出的 bits 數達到門檻（pull threshold）時，下一次 `out` 前自動從 TX FIFO 補一個字；TX FIFO 空就停在 `out` 等。
- **autopush**：ISR 移入的 bits 數達到門檻（push threshold）時，自動 push 到 RX FIFO；RX FIFO 滿就停住等。
- **門檻 32 要寫 32**：SDK 的 `sm_config_set_out_shift` / `_in_shift` 會把門檻 `& 0x1f`，32 就變成暫存器值 0，而暫存器說明是「Write 0 for value of 32」（`regs/pio.h:1004-1007`）。
- **移位方向**（`regs/pio.h:1024-1035`）：
  - OUT 左移（`shift_right=false`）：`out` 從 OSR 的 **最高位（bit31）** 開始拿 → MSB 先送。
  - OUT 右移（`shift_right=true`）：從 **最低位（bit0）** 開始拿 → LSB 先送。
  - IN 左移：新 bits 從右邊（LSB）進來，舊的往左推 → 收 n bits 後值在 `bits[n-1:0]`。
  - IN 右移：「data enters from left」→ 收 n bits 後值在 `bits[31:32-n]`，要 `>> (32-n)`。
- **SDK 預設**（`hardware_pio/include/hardware/pio.h:758-768` `pio_get_default_sm_config`）：in/out 都是**右移**、不 autopush/autopull、門檻 32、clkdiv 1、wrap 0～31。範本的 `.pio` 檔都自己改成左移。
- **side-set**：每條指令「順便」設定幾支腳（常拿來產生時脈），不用多花指令。
- **delay `[n]`**：指令執行完多等 n 個 cycle。
- **`.wrap_target` / `.wrap`**：程式跑到 `.wrap` 自動跳回 `.wrap_target`，不花指令。
- **clkdiv**：SM 速度 = clk_sys / clkdiv。150 MHz / 10 = 15 MHz。

### 3.2.8 計時兩種單位

- `time_us_64()`：開機後經過幾微秒（64-bit，不會繞回）。量任何長度都可以，精度 1 µs。
- `cycles_now()`（`timing.h`）：CPU 時脈 cycle 數。很短的程式（< 0.1 秒）用。ARM 和 RISC-V 實作不同，見 3.3.7。

## 3.3 逐檔說明

### 3.3.1 `CMakeLists.txt`

#### 用途

一個 CMake 專案，用 `add_app()` 函式（`CMakeLists.txt:19-26`）一次定義 5 個 app。每個 app 都：連 `pico_stdlib`、開 `-Wall -Wextra -Wno-unused-parameter`、stdio 走 USB 不走 UART、`pico_add_extra_outputs` 產生 .uf2/.hex/.bin/.dis/.map。

| target | 來源 | 額外函式庫 / 設定 | 行號 |
|---|---|---|---|
| `app_serial` | `app_serial.c serial_proto.c` | `PICO_STDIO_DEFAULT_CRLF=0`、`pico_multicore` | `CMakeLists.txt:29-32` |
| `app_multicore` | `app_multicore.c` | `pico_multicore pico_sync` | `CMakeLists.txt:35-36` |
| `app_dma` | `app_dma.c` | `hardware_dma` | `CMakeLists.txt:39-40` |
| `app_dma_pio` | `app_dma_pio.c` | `hardware_dma hardware_pio`、產生 `echo.pio.h` | `CMakeLists.txt:43-45` |
| `app_pio` | `app_pio.c` | `hardware_pio`、產生 `echo/bitstream_in/shift_out.pio.h` | `CMakeLists.txt:48-52` |

另外還有 pioasm 產生標頭的輔助 target：`app_dma_pio_echo_pio_h`、`app_pio_echo_pio_h`、`app_pio_bitstream_in_pio_h`、`app_pio_shift_out_pio_h`（`make` 會自動先做）。

- `PICO_BOARD` 預設 `pico2`（`CMakeLists.txt:9-11`），要在 `include(pico_sdk_import.cmake)` 前設，命令列 `-DPICO_BOARD=xxx` 可覆蓋。
- `pico_generate_pio_header` 每個 target 各自呼叫一次（同一個 `echo.pio` 被 `app_dma_pio` 和 `app_pio` 各產生一份），這是正常的。

#### 怎麼編譯 / 執行

**ARM（預設、最穩，考試建議用這個）**，在 `預製程式碼/pico/` 資料夾：

```bash
export PICO_SDK_PATH=/opt/pico-sdk        # 換成考場 SDK 的實際位置（README 審查用的 Docker 是 /opt/pico-sdk）
mkdir -p build && cd build
cmake -DPICO_BOARD=pico2 ..                # 預設 PICO_PLATFORM=rp2350-arm-s
make -j4                                   # 全部 5 個
make -j4 app_serial                        # 只編一個
```

**RISC-V（Hazard3）**，另開一個 build 資料夾（不要跟 ARM 共用，CMake 快取會記住工具鏈）：

```bash
mkdir -p build-rv && cd build-rv
cmake -DPICO_BOARD=pico2 -DPICO_PLATFORM=rp2350-riscv ..
make -j4
```

- SDK 2.2.0 找 RISC-V 編譯器時只找 `riscv32-unknown-elf-gcc` 和 `riscv32-corev-elf-gcc`（`cmake/preload/toolchains/pico_riscv_gcc.cmake:3`）。找不到時 cmake 會停在（實測訊息）：`Compiler 'riscv32-unknown-elf-gcc / riscv32-corev-elf-gcc' not found`。工具鏈在別的路徑就加 `-DPICO_TOOLCHAIN_PATH=<工具鏈資料夾>`，名字不同就加 `-DPICO_GCC_TRIPLE=<前綴>`。
- Ubuntu 套件的 `riscv64-unknown-elf-gcc` 沒有 newlib（缺 `nosys.specs`），直接用會在連結 `bs2_default.elf` 時失敗（實測：`riscv64-unknown-elf-gcc: fatal error: cannot read spec file 'nosys.specs'`）。這個容器裡繞過的做法見下面「實際執行輸出」，**只是證明程式碼能編成 RISC-V，不建議考場照抄**。

**沒有 picotool 也沒網路時**：指向一個已經編好的 picotool（裡面要有 `picotoolConfig.cmake`）：

```bash
cmake -DPICO_BOARD=pico2 -Dpicotool_DIR=<picotool 資料夾> ..
```

**產生的檔案**（在 build 資料夾）：

| 檔案 | 用途 |
|---|---|
| `app_xxx.uf2` | 燒錄用（拖進 BOOTSEL 隨身碟或給 `picotool load`） |
| `app_xxx.elf` | 含除錯資訊的執行檔（gdb、`arm-none-eabi-size`、`picotool info`） |
| `app_xxx.dis` | 反組譯（`objdump -h` + `objdump -d`），查某行 C 變成哪些指令 |
| `app_xxx.elf.map` | 連結地圖：每個函式 / 變數的位址與大小 |
| `app_xxx.bin` / `.hex` | 原始映像（一般用不到） |
| `echo.pio.h` 等 | pioasm 產生的標頭（看指令編碼） |

**燒錄**（⚠️ 這個容器沒有板子，以下兩種方法都沒有實測）：

- **BOOTSEL 法**：按住板上 BOOTSEL 鍵 → 插 USB → 放開 → 電腦出現一個叫 `RP2350` 的隨身碟 → 把 `app_xxx.uf2` 複製進去 → 板子自動重開並執行。指令版：`cp app_xxx.uf2 /media/$USER/RP2350/`（掛載點依系統而定）。
- **picotool**（`README.md:32`）：`picotool load -x app_xxx.uf2 -f`。`-x` 燒完立刻執行；`-f` 讓正在跑（且有開 USB stdio）的板子自己重開進 BOOTSEL。這個容器裡的 picotool 是「沒有 USB 支援」版本，`load` 不能用，只驗證了離線的 `picotool info`。
- 分辨 ARM / RISC-V 映像：`picotool info app_xxx.uf2` 會印 `image type: ARM Secure` 或 `image type: RISC-V`（見下面實測）。

**看輸出**（⚠️ 沒有實測）：

```bash
ls /dev/ttyACM*                       # 插上板子後出現；Docker 要 --privileged 或 --device 才看得到
screen /dev/ttyACM0 115200            # 離開：Ctrl-A 再按 k
python3 -m serial.tools.miniterm /dev/ttyACM0 115200   # pyserial 內建；離開：Ctrl-]
```

- 印字的 app（multicore / dma / dma_pio / pio）會**等電腦打開序列埠**才開始跑，所以晚開 terminal 不會漏字。它們只跑一次，要重看就拔插或重燒。
- `app_serial` 不印字，只回二進位封包，要用 `ros2/frame.py` 的 `transact()` 測（見 3.3.5）。

#### 對外介面

| 名稱 | 參數 | 回傳 / 效果 | 注意 |
|---|---|---|---|
| `add_app(name src...)` | target 名稱、原始檔 | 建一個 USB stdio 的 app | 只是本檔定義的 CMake 函式 |
| `-DPICO_BOARD=` | `pico2` | 選板子（LED 腳位、flash 大小） | 預設 `pico2` |
| `-DPICO_PLATFORM=` | `rp2350-arm-s` / `rp2350-riscv` | 選 CPU 架構 | 不寫 = ARM |
| `PICO_SDK_PATH` | 環境變數或 `-D` | SDK 位置 | 沒設就失敗（見常見錯誤） |
| `make <target>` | 上表 5 個名稱 | 只編那一個 | 名稱打錯會 `No rule to make target` |

#### 程式流程

1. `CMakeLists.txt:6` 要求 cmake ≥ 3.13。
2. `:9-11` 沒指定板子就用 `pico2`。
3. `:13` `include(pico_sdk_import.cmake)` 找 SDK（見 3.3.2）。
4. `:14` `project(pico_templates C CXX ASM)`；`:15` C11；`:16` `pico_sdk_init()`。
5. `:19-26` 定義 `add_app`。
6. `:29-52` 五個 app。

#### 要改的地方

| 行號 | 現在的值 | 意思 | 什麼情況要改、改成什麼 |
|---|---|---|---|
| `CMakeLists.txt:32` | `target_link_libraries(app_serial pico_multicore)` | app_serial 已連 multicore，要用雙核心時保留 | 要在 app_serial 用 DMA sniffer → 加 `hardware_dma`；用 PIO → 加 `hardware_pio`（見食譜 3.4.4） |
| （新增） | — | 新 app | 照 `add_app(app_new app_new.c)` + `target_link_libraries(app_new hardware_xxx)` 加一段 |

#### 實際執行輸出

環境：x86_64、4 核、cmake 3.28.3、`arm-none-eabi-gcc` 13.2.1、pico-sdk 2.2.0，在 `$S/ch03/build-arm`（`$S` = 本 session 的 scratchpad），picotool 用已編好的 `-Dpicotool_DIR`。cmake 摘錄：

```text
Using PICO_SDK_PATH from environment ('.../scratchpad/pico-sdk')
Target board (PICO_BOARD) is 'pico2'.
Auto-converting non-specific PICO_PLATFORM='rp2350' to 'rp2350-arm-s'
Defaulting platform (PICO_PLATFORM) to 'rp2350-arm-s' based on PICO_BOARD setting.
-- Defaulting build type to 'Release' since not specified.
Defaulting compiler (PICO_COMPILER) to 'pico_arm_cortex_m33_gcc' since not specified.
-- The C compiler identification is GNU 13.2.1
Build type is Release
Using picotool from .../scratchpad/pico/build/_deps/picotool/picotool
TinyUSB available at .../pico-sdk/lib/tinyusb/hw/bsp/rp2040; enabling build support for USB.
-- Configuring done (0.8s)
```

`make -j4`（全新 build 資料夾）：0 個 warning、0 個 error，`real 0m20.010s`。

```text
[ 70%] Built target app_serial
[ 75%] Built target app_multicore
[ 80%] Built target app_dma
[ 89%] Built target app_dma_pio
[100%] Built target app_pio
```

`arm-none-eabi-size app_*.elf`（ARM）：

```text
   text	   data	    bss	    dec	    hex	filename
  36152	      0	  36568	  72720	  11c10	app_dma.elf
  36384	      0	  36576	  72960	  11d00	app_dma_pio.elf
  38796	      0	  22652	  61448	   f008	app_multicore.elf
  35440	      0	   3808	  39248	   9950	app_pio.elf
  27164	      0	  23792	  50956	   c70c	app_serial.elf
```

`picotool info -a app_serial.uf2`（離線讀檔，picotool v2.2.0）摘錄：

```text
File app_serial.uf2 family ID 'rp2350-arm-s':
 name:                app_serial
 features:            USB stdin / stdout
 binary start:        0x10000000
 target chip:         RP2350
 image type:          ARM Secure
 sdk version:         2.2.0
 pico_board:          pico2
```

**pico-sdk 2.1.1**（`$S/sdk211`，同樣指令、`$S/ch03/build-arm211`）：5 個 app 全部 `Built target`、0 warning。這證明 `app_dma*.c` 的相容補丁有效（2.1.1 沒有 `dma_encode_transfer_count`，見 3.3.8）。

**RISC-V**（`$S/ch03/build-rv`）：這個容器只有 Ubuntu 的 `riscv64-unknown-elf-gcc` 13.2.0 + `picolibc`，用了以下替代設定才編過，**不是考場標準做法**：`-DPICO_GCC_TRIPLE=riscv64-unknown-elf -DPICO_CLIB=picolibc`、`CMAKE_C/CXX/ASM_FLAGS` 加 `-march=rv32imac_zicsr_zifencei_zba_zbb_zbs_zbkb -mabi=ilp32 --specs=<去掉 -Tpicolibc.ld 與 --gc-sections 的 picolibc.specs>`、C++ 加 `-DPICO_CXX_DISABLE_ALLOCATION_OVERRIDES=1`、連結時用一個空的 `nosys.specs` 和空的 `libstdc++.a`。結果：5 個 app 全部 `Built target`、0 warning。

```text
   text	   data	    bss	    dec	    hex	filename
  43880	      0	  35884	  79764	  13794	app_dma.elf
  43860	      0	  35896	  79756	  1378c	app_dma_pio.elf
  43932	      0	  21620	  65552	  10010	app_multicore.elf
  43308	      0	   3124	  46432	   b560	app_pio.elf
  27204	      0	  23112	  50316	   c48c	app_serial.elf
```

`picotool info build-rv/app_serial.uf2`：`family ID 'rp2350-riscv'`、`image type: RISC-V`、`binary start: 0x10000000`。⚠️ 這份 RISC-V 映像沒有上板，用 picolibc 取代 newlib 的影響沒有驗證。

#### 常見錯誤

| 症狀 | 原因 | 修法 |
|---|---|---|
| `CMake Error at pico_sdk_import.cmake:103 (message): SDK location was not specified.`（實測） | 沒設 `PICO_SDK_PATH` | `export PICO_SDK_PATH=...` 後刪掉 build 資料夾重跑 cmake |
| `Directory '...' does not appear to contain the Raspberry Pi Pico SDK` | 路徑指到 SDK 上一層或下一層 | 指到有 `pico_sdk_init.cmake` 的那層 |
| cmake 卡在 `Downloading Picotool` 或 git 失敗 | 系統沒有 picotool、沒網路 | 用考場裝好的 picotool：`-Dpicotool_DIR=...`；或問監考 |
| `Compiler 'riscv32-unknown-elf-gcc / riscv32-corev-elf-gcc' not found` | 沒有 RISC-V 工具鏈 | 改用 ARM（不加 `PICO_PLATFORM`）；或 `-DPICO_TOOLCHAIN_PATH=` |
| `cannot read spec file 'nosys.specs'` | 用了沒 newlib 的 riscv64 工具鏈 | 用 ARM，或用 pico-sdk 官方的 riscv32 工具鏈 |
| 改了 `PICO_PLATFORM` 卻還是舊架構 | CMake 快取記住舊值 | 另開 build 資料夾，或 `rm -rf build` |
| `fatal error: echo.pio.h: No such file or directory` | 新 app 忘了 `pico_generate_pio_header` | 在 CMakeLists 加 `pico_generate_pio_header(app_new ${CMAKE_CURRENT_LIST_DIR}/pio/xxx.pio)` |
| `undefined reference to dma_channel_...` / `pio_...` | 沒連 `hardware_dma` / `hardware_pio` | `target_link_libraries(app hardware_dma)` |
| 燒完沒有 `/dev/ttyACM0` | 程式卡死在 USB 起來前；或 Docker 沒給裝置 | 先燒已知會動的 app；容器要 `--privileged`；`dmesg` 看有沒有 `cdc_acm` |

### 3.3.2 `pico_sdk_import.cmake`

#### 用途

讓專案找到 pico-sdk。從 SDK 的 `external/pico_sdk_import.cmake` 複製來的，跟 SDK 2.2.0 版本逐字相同（實測 `diff` 無輸出）。**不用改。**

#### 怎麼編譯 / 執行

由 `CMakeLists.txt:13` 自動 include，不會單獨執行。

#### 對外介面

| 名稱 | 參數 | 回傳 / 效果 | 注意 |
|---|---|---|---|
| `PICO_SDK_PATH`（環境變數或 `-D`） | SDK 路徑 | 用這份 SDK | `pico_sdk_import.cmake:28-31` 會印 `Using PICO_SDK_PATH from environment` |
| `PICO_SDK_FETCH_FROM_GIT` | `on` | 從 GitHub 下載 SDK | 要網路；考場不要用 |
| `PICO_SDK_FETCH_FROM_GIT_PATH` / `_TAG` | 路徑 / tag | 下載位置 / 版本 | 預設 tag `master`（`:48-51`） |

#### 程式流程

1. `:28-46` 從環境變數讀上面 4 個設定。
2. `:58-106` 沒有 `PICO_SDK_PATH`：若 `FETCH_FROM_GIT` 開了就用 FetchContent 下載，否則 `:103` `FATAL_ERROR`。
3. `:108-116` 檢查資料夾存在、裡面有 `pico_sdk_init.cmake`。
4. `:121` include SDK 的初始化腳本。

#### 要改的地方

沒有 `TODO(改這裡)`。不要改。

#### 實際執行輸出

見 3.3.1（`Using PICO_SDK_PATH from environment (...)`、沒設時的 `FATAL_ERROR`）。

#### 常見錯誤

見 3.3.1 常見錯誤前兩列。

### 3.3.3 `serial_proto.h`

#### 用途

電腦和 Pico 共用的封包格式（3.2.4）：sync 位元組、指令代碼、payload 上限、`frame_t` 結構、4 個函式宣告。

#### 怎麼編譯 / 執行

被 `app_serial.c` 和 `serial_proto.c` include，不單獨執行。

#### 對外介面

| 名稱 | 參數 | 回傳 / 效果 | 注意 |
|---|---|---|---|
| `SYNC0` / `SYNC1` | — | `0xAA` / `0x55`（`serial_proto.h:14-15`） | 和 `frame.py` 的 `HDR` 一致 |
| `CMD_ECHO` / `CMD_SUM_U32` / `CMD_CRC32` | — | `0x01` / `0x02` / `0x03`（`:18-20`） | 和 `frame.py:17` 一致 |
| `FRAME_MAX_PAYLOAD` | — | `8192`（`:23`） | 電腦端 `CHUNK_BYTES` 必須 ≤ 這個 |
| `frame_t` | — | `cmd`、`seq`、`len`、`payload[8192]`（4-byte 對齊）（`:25-30`） | 一個就 8 KB，放全域，不要放 stack |
| `crc32_update(crc, p, n)` | 前一段的 crc（第一段給 0）、資料、長度 | zlib CRC32（`:33`） | 可分段：`c = crc32_update(c, b, n2)` |
| `proto_feed(byte, f)` | 一個 byte、輸出用的 frame | `1` 收到完整且 CRC 對；`0` 還沒完；`-1` CRC 錯或 len 太大（`:37`） | 回 1 時內容在 `*f` |
| `proto_reset()` | — | 狀態機回「找 AA」（`:40`） | 收到一半斷線時用 |
| `proto_busy()` | — | `1` = 正在收封包中間（`:42`） | |
| `proto_send(cmd, seq, payload, len)` | | 送一個完整封包（`:45`） | 自動加 AA 55、len、crc32 |

#### 程式流程

只有定義，沒有流程。

#### 要改的地方

| 行號 | 現在的值 | 意思 | 什麼情況要改、改成什麼 |
|---|---|---|---|
| `serial_proto.h:17-20` | 3 個 `CMD_` | 指令代碼 | 題目有新指令：加 `#define CMD_SORT_U32 0x04`，**電腦端 `ros2/frame.py:17` 也要加同一個數字**（食譜 3.4.6） |
| `serial_proto.h:22-23` | `8192` | payload 上限 | 題目一包資料更大：加大（例如 `32768`）。注意 `len` 是 u16，最大 65535；`frame_t rx` 和 `reply` 各占這麼多 RAM（RP2350 有 520 KB） |

#### 實際執行輸出

見 3.3.4。

#### 常見錯誤

| 症狀 | 原因 | 修法 |
|---|---|---|
| 電腦送大資料，Pico 完全不回、電腦端 3 次逾時 | `len > FRAME_MAX_PAYLOAD`，Pico 丟包不回 | 電腦端切小包（`CHUNK_BYTES`），或加大 `FRAME_MAX_PAYLOAD` |
| 新指令電腦收不到回覆 | 兩邊指令代碼不同 | 對照 `serial_proto.h` 和 `frame.py` 的數字 |

### 3.3.4 `serial_proto.c`

#### 用途

三件事：軟體 CRC32（查表法）、收封包的狀態機 `proto_feed`、送封包 `proto_send`。

#### 怎麼編譯 / 執行

由 `CMakeLists.txt:29` 和 `app_serial.c` 一起編。電腦上也能單獨測（本章作者做過，見下面實際執行輸出）。

#### 對外介面

見 3.3.3 表格。內部：`crc_table[256]`、`crc32_make_table()`（`serial_proto.c:11-22`）、`put_raw()`（`:88-90`）。

#### 程式流程

**CRC32（`serial_proto.c:14-30`）**

1. 第一次呼叫 `crc32_update` 時建 256 格表（`:26`，`crc_table_ready` 旗標）。表的每一格是「一個 byte 用反射多項式 `0xEDB88320` 跑 8 次」（`:18`）。
2. `crc ^= 0xFFFFFFFF`（`:27`）→ 每個 byte 查表一次（`:28`）→ 最後再 `^ 0xFFFFFFFF`（`:29`）。前後各 XOR 一次，所以把上一段的結果直接傳進來就能接著算。
3. 驗證值：`crc32_update(0, "123456789", 9)` = `0xCBF43926`（`:24` 註解；電腦上實測相同）。

**收封包狀態機（`serial_proto.c:33-76`）**

```text
           收到 AA                 收到 55                  收滿 4 bytes（cmd seq len）
 WAIT_AA ──────────► WAIT_55 ──────────────► HEADER ───────────────────────────┐
   ▲  ▲                │ 收到 AA：留在 WAIT_55（AA AA 55 也能對齊）             │
   │  │                │ 其他：回 WAIT_AA                                      │
   │  │                                                                       ▼
   │  │   len > 8192：回 -1、回 WAIT_AA ◄──────────────────────────── 檢查 len
   │  │                                                       len=0 │    │ len>0
   │  │                                                             ▼    ▼
   │  └──── 收滿 4 bytes：比對 CRC，回 1 或 -1 ◄──────── CRC ◄──── PAYLOAD（收 len bytes）
   └──── proto_reset()（app_serial 閒置 100 ms 時呼叫）
```

1. `ST_WAIT_AA`（`:41-43`）：不是 `0xAA` 的 byte 都丟掉。
2. `ST_WAIT_55`（`:44-47`）：是 `0x55` → 進 HEADER；又是 `0xAA` → 留著（處理 `AA AA 55`）；其他 → 回 WAIT_AA。
3. `ST_HEADER`（`:48-57`）：存 4 bytes 到 `hdr[]`，組出 `cmd`、`seq`、`len`（小端，`:53`）。`len > FRAME_MAX_PAYLOAD` → 回 -1（`:54`）。`len == 0` 直接跳到 CRC（`:56`）。
4. `ST_PAYLOAD`（`:58-61`）：一個一個存進 `f->payload`，存滿 `len` 個就到 CRC。
5. `ST_CRC`（`:62-72`）：收 4 bytes 組成 `got`；用 `hdr`（cmd..len）接著 payload 算 CRC（`:69-70`）；相等回 1，否則 -1。不管對錯都回到 WAIT_AA。

**送封包（`serial_proto.c:92-101`）**

1. 組 6 bytes 表頭 `AA 55 cmd seq len_lo len_hi`（`:93`）。
2. CRC 從 `h[2]`（cmd）開始算 4 bytes，再接 payload（`:94-95`）。
3. 依序送表頭、payload、CRC（`:97-99`），用 `stdio_put_string(p, n, false, false)`（`:89`）：不加換行、不轉 `\r\n`，直接送原始 bytes。
4. `stdio_flush()`（`:100`）立刻送出。

**跟 `ros2/frame.py` 的差別**：CRC 錯時，Pico 丟掉整包、從下一個 byte 重新找 AA；`frame.py` 的 `FrameParser.feed()` 只往後挪 1 byte（`frame.py:68`）。USB 不會掉 byte，實務上沒差（`README.md:144`）。

#### 要改的地方

沒有 `TODO(改這裡)`。上限與指令代碼在 `serial_proto.h` 改。

#### 實際執行輸出

環境：x86_64、host gcc 13.3.0、`-O2 -Wall -Wextra`。把 `serial_proto.c` 原封不動和一個假的 `pico/stdlib.h`（`stdio_put_string` 改成寫 stdout）一起編，再用 `ros2/frame.py` 的 `encode()` 產生 8 種輸入一次餵進去（測試程式在 `$S/ch03/host/`）：

```text
送: ECHO 5 bytes              15 bytes  aa 55 01 07 05 00 68 65 6c 6c 6f c8 ...
送: SUM_U32 [1,2,3]           22 bytes  aa 55 02 08 0c 00 01 00 00 00 02 00 ...
送: len=0                     10 bytes  aa 55 03 09 00 00 7d 4b 20 3c
送: 垃圾 + AA AA 55 開頭          14 bytes  00 11 aa aa 55 01 0a 01 00 78 f0 ad ...
送: CRC 被改壞                   13 bytes  aa 55 01 0b 03 00 61 62 63 09 c6 19 ...
送: len=8192（上限）            8202 bytes  aa 55 01 0c 00 20 00 01 02 03 04 05 ...
送: len=8193（超過）表頭             6 bytes  aa 55 01 0d 01 20
送: 超過之後的正常包                  15 bytes  aa 55 01 0e 05 00 61 66 74 65 72 24 ...
OK  cmd=01 seq=7 len=5
OK  cmd=02 seq=8 len=12
OK  cmd=03 seq=9 len=0
OK  cmd=01 seq=10 len=1
BAD (crc 錯或 len 太大)
OK  cmd=01 seq=12 len=8192
BAD (crc 錯或 len 太大)
OK  cmd=01 seq=14 len=5
busy=0
frame.py 解回覆: cmd=0x01 seq=7 len=5
...（共 6 包）
回覆 bytes 與 frame.encode 逐 byte 相同: True
```

`crc32_update(0, "123456789", 9)` 實測輸出 `cbf43926`。

#### 常見錯誤

| 症狀 | 原因 | 修法 |
|---|---|---|
| 電腦端收到的封包 CRC 錯 | 用了 `printf` 混進文字；或沒關 CRLF 轉換 | `app_serial` 不要 printf；確認 `CMakeLists.txt:31` 和 `app_serial.c:61` |
| 兩核都呼叫 `crc32_update`，第一次結果偶爾怪 | 查表是第一次呼叫才建（`:26`），沒有鎖 | 在 `multicore_launch_core1` 前先呼叫一次 `crc32_update(0, NULL, 0)` 把表建好（兩核同時建表寫入的值相同，⚠️ 沒有實測會不會出錯，先建好最保險） |
| 想分包算 CRC，結果跟電腦不同 | 每包都從 0 開始算 | 協定加「前一段 crc」欄位，Pico 端 `crc32_update(prev, ...)`；或電腦端 `zlib.crc32(data, prev)` 自己合併 |

### 3.3.5 `app_serial.c`

#### 用途

USB 二進位封包伺服器：電腦送封包、Pico 依 `cmd` 計算、用同樣的 cmd / seq 回覆。題型「電腦送資料給板子算」的起點。**不印任何文字**（`app_serial.c:6`）。

#### 怎麼編譯 / 執行

```bash
cd 預製程式碼/pico/build && make -j4 app_serial     # 產生 app_serial.uf2
```

燒進去後，在電腦上（`預製程式碼/` 資料夾，需要 pyserial）：

```python
import sys, serial
sys.path.insert(0, "ros2")
from frame import transact, pack_u32, unpack_u32, CMD_ECHO, CMD_SUM_U32, CMD_CRC32
ser = serial.Serial("/dev/ttyACM0", timeout=0.05)          # timeout 要小（frame.py:73 說明）
print(transact(ser, CMD_ECHO, b"hello"))                     # 預期 b'hello'
print(unpack_u32(transact(ser, CMD_SUM_U32, pack_u32([1, 2, 3])))[0])   # 預期 6
print(hex(unpack_u32(transact(ser, CMD_CRC32, b"123456789"))[0]))      # 預期 0xcbf43926
```

⚠️ 上面這段沒有接板子跑過；回覆的內容在電腦模擬上實測正確（見下面）。

#### 對外介面

| 名稱 | 參數 | 回傳 / 效果 | 注意 |
|---|---|---|---|
| `CMD_ECHO`（0x01） | 任意 payload | 原樣回傳 | |
| `CMD_SUM_U32`（0x02） | u32 小端陣列 | 4 bytes：總和 mod 2^32 | len 不是 4 的倍數時，尾巴 1～3 bytes 忽略（`app_serial.c:31`） |
| `CMD_CRC32`（0x03） | 任意 bytes | 4 bytes：zlib CRC32 | 軟體查表算（`:45`） |
| 其他 cmd | | **不回覆**（`:54-55`） | 電腦端會逾時重送 3 次 |
| CRC 錯 / len 太大 | | **不回覆**，`n_bad++`（`:78`） | |
| LED（GPIO 25） | | `n_ok` 的 bit4 → 每收 16 包換一次亮暗（`:80`） | 唯一的除錯指示 |

#### 程式流程

1. `stdio_init_all()`（`app_serial.c:60`）開 USB stdio。
2. `stdio_set_translate_crlf(&stdio_usb, false)`（`:61`）關掉 `\n→\r\n`。這和 `CMakeLists.txt:31` 的 `PICO_STDIO_DEFAULT_CRLF=0`、`proto_send` 用的 `stdio_put_string(..., false, false)` 是三重保險。
3. 初始化 LED（`:62-63`）。**不等** `stdio_usb_connected()`：電腦一定先開 port 才送封包（`:65`）。
4. 主迴圈（`:69-81`）：
   - `stdio_get_until(buf, 512, make_timeout_time_us(1000))`（`:71`）：最多等 1 ms，有資料就回傳讀到幾個 byte，沒資料回 `PICO_ERROR_TIMEOUT`（-2，`pico/error.h:26`）。
   - 有資料就更新 `last_rx`（`:72`）；沒資料且封包收到一半超過 100 ms → `proto_reset()`（`:73-74`）。
   - 每個 byte 丟進 `proto_feed`（`:76`）；回 1 就 `handle(&rx)`（`:77`）。
5. `handle()`（`:24-57`）依 cmd 計算並 `proto_send` 回覆。SUM_U32 用 `memcpy(&v, f->payload + 4*i, 4)` 取 u32（`:36`，避免 strict aliasing 問題）。

#### 要改的地方

| 行號 | 現在的值 | 意思 | 什麼情況要改、改成什麼 |
|---|---|---|---|
| `app_serial.c:32` | `uint32_t n = f->len / 4;` | u32 個數 | 題目規定 len 不是 4 的倍數要回錯誤：加 `if (f->len % 4) { proto_send(f->cmd, f->seq, NULL, 0); break; }`（回空 payload 當錯誤，格式依題目） |
| `app_serial.c:37` | `sum += v;` | 每個元素的運算 | 換成題目要的（例如 `sum += v * v;`、`sum ^= v;`） |
| `app_serial.c:51-52` | 註解範例 | 新指令放這 | 見食譜 3.4.6 |
| `app_serial.c:78` | `else if (r < 0) n_bad++;` | CRC 錯就丟 | 題目要 NACK：在這裡 `proto_send(0xFF, rx.seq, NULL, 0);`（注意 CRC 錯時 `rx.seq` 可能是錯的） |

#### 實際執行輸出

環境：x86_64、host gcc 13.3.0。把 `app_serial.c` + `serial_proto.c` **原封不動**和假的 `pico/stdlib.h`、`pico/stdio_usb.h`（`stdio_get_until` 改成讀 stdin、讀完就結束）一起編，用 `frame.py` 送 6 包（測試程式在 `$S/ch03/host2/`）：

```text
回覆 cmd=0x01 seq=1 len=2  ECHO = b'hi'
回覆 cmd=0x02 seq=2 len=4  SUM = 3459707144 期望 3459707144
回覆 cmd=0x02 seq=3 len=4  SUM = 6 期望 6
回覆 cmd=0x03 seq=4 len=4  CRC = 0x53cf2bff 期望 0x53cf2bff
回覆 cmd=0x03 seq=5 len=4  CRC = 0xcbf43926 期望 0xcbf43926
seq=6（未知指令 0x7F）沒有回覆
```

（seq=2 是 1000 個隨機 u32；seq=3 是 `[1,2,3]` 後面多 1 byte，被忽略；seq=4 是 4096 個隨機 bytes。）板子上沒有實測。

#### 常見錯誤

| 症狀 | 原因 | 修法 |
|---|---|---|
| 電腦端一直 `[transact] ... 逾時，重試` | 指令代碼沒有對應的 case；封包太大；port 錯；Pico 沒在跑 | 確認 cmd 數字、`len ≤ 8192`、`ls /dev/ttyACM*` |
| 回覆的資料被改掉（多了 `0d`） | CRLF 轉換沒關 | 檢查 `CMakeLists.txt:31` 與 `app_serial.c:61` |
| 加了 `printf` 除錯後電腦端解不出來 | 文字混進二進位串流 | 拿掉 printf；改用 LED，或在回覆 payload 裡帶除錯值 |
| 電腦端設 baud 1200 後板子變成隨身碟 | SDK 的 1200 baud 魔法重開 | 用其他 baud（USB CDC 的 baud 沒作用） |
| 大陣列放在 `handle()` 區域變數，板子當掉 | stack 不夠 | 用 `static` 或全域（像 `reply[]`，`:20`） |

### 3.3.6 `app_multicore.c`

#### 用途

兩部分：

1. **race 示範**：兩顆核心同時對 `counter` 加 20 萬次，分「不鎖」「spinlock」「critical_section」三種模式各跑一次，看結果差多少、花多久。
2. **工作佇列（pipeline）**：core0 準備資料（模擬「收資料」）丟進 `q_job`，core1 計算後把結果丟進 `q_result`，core0 收結果。

#### 怎麼編譯 / 執行

```bash
cd 預製程式碼/pico/build && make -j4 app_multicore
# 燒 app_multicore.uf2，然後：
screen /dev/ttyACM0 115200
```

#### 對外介面

| 名稱 | 參數 | 回傳 / 效果 | 注意 |
|---|---|---|---|
| `N_ADD` | — | 每核加幾次（`app_multicore.c:21`） | 預設 200000 |
| `add_many()` | — | 依 `lock_mode` 加 `N_ADD` 次（`:32-49`） | 兩核都呼叫 |
| `job_t` / `result_t` | — | 工作 / 結果結構（`:52-53`） | 改成題目要的欄位 |
| `core1_main()` | — | core1 的主程式：等 FIFO 命令（`:64-85`） | `CMD_RACE`=1、`CMD_WORKER`=2、`DONE`=0xD0E（`:62`） |
| `SAFE_PRINTF(...)` | 同 printf | 包 mutex 的 printf（`:60`） | 單一 printf 本來就互斥（`PICO_STDOUT_MUTEX=1`，`pico_stdio/include/pico/stdio.h:21`）；多行要連著印才需要 |

SDK 函式（pico-sdk 2.2.0）：

| 函式 | 出處 | 一句話 |
|---|---|---|
| `spin_lock_claim_unused(true)` | `hardware_sync/include/hardware/sync.h:349` | 要一個 24～31 號的鎖；`true` = 沒有就 panic |
| `spin_lock_init(num)` | `sync/spin_lock.h:345` | 設成未上鎖，回傳 `spin_lock_t *` |
| `spin_lock_blocking(l)` | `sync/spin_lock.h:301` | 關中斷 + 拿鎖，回傳原本的中斷狀態 |
| `spin_unlock(l, save)` | `sync/spin_lock.h:332` | 放鎖 + 恢復中斷 |
| `critical_section_init / _enter_blocking / _exit` | `pico_sync/include/pico/critical_section.h:45` 起 | 自動要鎖號的 spinlock |
| `queue_init(q, 元素大小, 個數)` | `pico_util/include/pico/util/queue.h:61` | 建佇列 |
| `queue_add_blocking / queue_remove_blocking` | `queue.h:202`、`:212` | 滿/空就等 |
| `queue_try_add / queue_try_remove` | `queue.h:166`、`:178` | 不等，回 bool |
| `multicore_launch_core1(fn)` | `pico_multicore/include/pico/multicore.h` | core1 開始跑 `fn` |
| `multicore_fifo_push_blocking / pop_blocking` | `multicore.h:184`、`:231`（inline 版） | 硬體 FIFO 傳 u32，深度 4 |

#### 程式流程

1. `stdio_init_all()`，等 USB 連上，再等 200 ms（`app_multicore.c:88-90`）。
2. 要一個 spinlock（`:92`）、初始化 critical_section（`:93`）、兩個佇列各 8 格（`:94-95`）。
3. `multicore_launch_core1(core1_main)`（`:96`）。core1 進到 `:68` 等 FIFO。SDK 啟動時用 FIFO 握手，最後一步的回應 core0 已經讀走，所以 core1 不會讀到殘值（`:66-67` 註解）。
4. **第 1 部分**（`:100-111`），三種模式 `m = 0, 1, 2`：
   - core0 清 `counter`、設 `lock_mode`，`__dmb()` 確保寫入完成（`:101-104`）。
   - FIFO 送 `CMD_RACE` 給 core1（`:105`），core0 自己也 `add_many()`（`:106`）。
   - core1 做完 `__dmb()` 後送 `DONE`（`:71-73`）；core0 `pop` 等它（`:107`）。
   - 印 `counter` 和時間（`:109-110`）。
5. **第 2 部分**（`:114-134`）：
   - FIFO 送 `CMD_WORKER`（`:114`），core1 進入 `:76-82` 的迴圈：`queue_remove_blocking` 拿工作 → 加總 → `queue_add_blocking` 回結果；`data == NULL` 代表結束（`:78`）。
   - core0 的迴圈（`:119-130`）：只要「已送 − 已收 < 4」就填一塊 buffer（`data_buf[sent % 4]`，`:122-123`）送出；同時用 `queue_try_remove` 不阻塞地收結果（`:129`）。
   - 4 塊 buffer 輪流用：第 `sent` 個工作用第 `sent % 4` 塊，要等第 `sent − 4` 個結果收回來才能覆蓋（`sent - got < 4` 保證）。
   - 送停止訊號（`:131-132`），印總和與時間（`:133-134`）。

**為什麼 queue 是 8 格**：同時最多 4 個工作 + 1 個停止訊號 ≤ 8（`README.md:122`）。

```text
 core0（收/派工）                        core1（計算）
  填 data_buf[k%4] ─► q_job (8 格) ─►  queue_remove_blocking
                                         r.sum = Σ data[i]
  queue_try_remove ◄─ q_result (8 格) ◄─ queue_add_blocking
  （同時最多 4 個工作在路上）
```

#### 預期輸出（⚠️ 沒有上板，依程式碼推算）

```text
不鎖(錯誤示範) counter=<小於 400000，每次不同> (應為 400000)  <時間> us
spinlock           counter=400000 (應為 400000)  <時間> us
critical_section   counter=400000 (應為 400000)  <時間> us
worker: 16 jobs, total=8503296
[時間] worker 總時間             <時間> us
```

- `total=8503296` 是算出來的：第 s 個工作的資料是 `s+i`（i = 0..1023），16 個工作加總 = 1024×(0+…+15) + 16×(0+…+1023) = 8503296。
- 不鎖那一行「一定會少」不保證：README 也寫了遺失多少看時序（`README.md:168`）。如果剛好等於 400000，再跑一次或加大 `N_ADD`。
- `%-18s` 用的是 byte 數對齊，中文字（UTF-8 每字 3 bytes）那行會跟其他行對不齊，只是外觀。
- 時間數字沒有實測，不要引用。

#### 要改的地方

| 行號 | 現在的值 | 意思 | 什麼情況要改、改成什麼 |
|---|---|---|---|
| `app_multicore.c:21` | `200000` | 每核加幾次 | race 看不出來就加大（例如 2000000） |
| `app_multicore.c:52` | `job_t { id, data, n }` | 工作內容 | 題目的工作要帶什麼就加欄位（例如 `uint8_t op;`）。佇列是「複製 struct」，指標指向的資料要在算完前保持不變 |
| `app_multicore.c:53` | `result_t { id, sum }` | 結果內容 | 例如改成 `uint32_t crc;` |
| `app_multicore.c:80` | `r.sum += j.data[i];` | core1 真正的計算 | 換成題目的計算（排序、CRC、BNN…） |
| `app_multicore.c:116` | `N_JOBS = 16` | 工作數 | 依資料量 |

#### 實際執行輸出

編譯通過（3.3.1）。`counter++` 的反組譯與 spinlock 的 `ldaexb/strexb` 見 3.2.5（實際取自 `build-arm/app_multicore.dis` 的 `<add_many>`）。板子上沒有實測。

#### 常見錯誤

| 症狀 | 原因 | 修法 |
|---|---|---|
| 不鎖也剛好 400000 | 兩核沒真的交錯；或編譯器把迴圈合併 | `counter` 必須 `volatile`（`:27`）；加大 `N_ADD` |
| core1 一跑就當掉（HardFault） | core1 stack 只有 2 KB，在 core1 開了大區域陣列 | 改 `static` 或全域 |
| 兩核互相等、整個卡住 | 兩邊都在等對方的 FIFO / queue；或拿鎖後又等另一個鎖 | 畫出誰等誰；鎖裡不要呼叫會等待的函式 |
| 結果偶爾錯（pipeline） | core0 覆蓋了 core1 還在讀的 buffer | 保持「在路上的工作數 < buffer 數」 |
| `multicore_fifo_pop_blocking` 讀到怪值 | FIFO 被別人用（例如 `multicore_lockout`、flash 寫入） | 一般資料改用 `queue_t` |
| printf 的字被另一核插隊 | 多個 printf 要連著印 | 用 `SAFE_PRINTF` |

### 3.3.7 `timing.h`

#### 用途

量時間的小工具，`#include "timing.h"` 就能用。兩種單位：微秒（`time_us_64()`）和 CPU cycle（`cycles_*`）。

#### 怎麼編譯 / 執行

header-only，被 `app_multicore.c`、`app_dma.c`、`app_dma_pio.c`、`app_pio.c` include。

```c
uint64_t t0 = time_us_64();
/* 要量的程式 */
PRINT_US("CPU 迴圈", t0);                 // 印 [時間] CPU 迴圈            1234 us

cycles_init();                             // 程式開頭呼叫一次
uint32_t c0 = cycles_now();
/* 很短的程式 */
printf("%lu cycles\n", (unsigned long)cycles_since(c0));
printf("x%.1f\n", (double)speedup(slow_us, fast_us));
```

#### 對外介面

| 名稱 | 參數 | 回傳 / 效果 | 注意 |
|---|---|---|---|
| `PRINT_US(label, t0)` | 字串、起點 | 印 `[時間] %-20s %8llu us`（`timing.h:29-30`） | |
| `cycles_init()` | — | 啟動 cycle 計數器（`:33-44`） | 用 cycles 前呼叫一次 |
| `cycles_now()` | — | 目前 cycle 值（`:47-53`） | ARM 往下數、RISC-V 往上數，不要自己相減 |
| `cycles_since(c0)` | 起點 | 經過的 cycle（`:56-62`） | ARM 最多 2^24−1 個 cycle |
| `speedup(slow, fast)` | 兩個時間 | `slow/fast`（`:65-67`） | fast=0 回 0 |

**ARM（Cortex-M33）vs RISC-V（Hazard3）**

| | ARM | RISC-V |
|---|---|---|
| 計數器 | SysTick（24-bit 往下數） | `mcycle` CSR（讀低 32 bits，往上數） |
| 啟動 | `csr=0` → `rvr=0xFFFFFF` → `cvr=0` → `csr=ENABLE+CLKSOURCE`（`timing.h:39-42`） | 清 `mcountinhibit`（CSR 0x320）的 bit0（`timing.h:37`） |
| 為什麼要啟動 | `RVR` 重置值 UNKNOWN（`regs/m33.h`） | `mcountinhibit` 重置值 0x5，CY 被暫停（`regs/rvcsr.h`） |
| 最長可量 | 2^24−1 = 16777215 cycles，150 MHz 下 0.1118 秒，超過**默默繞回** | 2^32 cycles，150 MHz 下 28.6 秒 |
| 差值 | `(c0 - now) & 0x00FFFFFF`（`:60`） | `now - c0`（`:58`） |
| 編出來的指令（實測反組譯） | 讀 `systick_hw->cvr` | `csrci mcountinhibit,1`、`csrr s8,mcycle`（`build-rv/app_dma.dis:385-386`） |

- `riscv_clear_csr(0x320, 1)` 用數字不用名字：SDK 的巨集會把參數直接貼進 `csrci` 組合語言（`timing.h:36` 註解）。實測組譯結果正是 `csrci mcountinhibit,1`。
- SDK 本身不用 SysTick；如果你自己用 SysTick 中斷，`cycles_init` 會改掉你的設定（`timing.h:10`）。

**怎麼量才準**

1. 要量的東西跑一次「暖身」，再量第二次（第一次可能有 flash 快取 miss）。
2. 很短的東西重複 N 次量總時間再除以 N，而不是量一次。
3. 比較兩種做法時，用同樣的資料、同樣的輸出檢查（例如 `memcmp`），避免一個被編譯器最佳化掉。
4. 結果要「用到」（印出來或存 `volatile`），不然 `-O3` 可能把整段刪掉。

#### 程式流程

見上表；只有 inline 函式。

#### 要改的地方

沒有 `TODO(改這裡)`。

#### 實際執行輸出

ARM 與 RISC-V 都編譯通過；RISC-V 反組譯如上表。板子上沒有實測（cycle 數字沒有）。

#### 常見錯誤

| 症狀 | 原因 | 修法 |
|---|---|---|
| ARM 上 cycles 很小或亂跳 | 量的東西超過 0.11 秒，SysTick 繞回 | 改用 `time_us_64()` |
| cycles 永遠 0 | 忘了 `cycles_init()` | 開頭呼叫 |
| `%llu` 印出怪數字 | 參數不是 `unsigned long long` | 轉型 `(unsigned long long)` |
| 量到 0 us | 被量的程式被最佳化掉，或太短 | 用結果、重複 N 次 |

### 3.3.8 `app_dma.c`

#### 用途

DMA 四個示範：(1) copy：CPU 迴圈 vs `memcpy` vs DMA；(2) fill；(3) sniffer 硬體 CRC32 的已知答案測試 + 跟 CPU 比速度；(4) DMA 在背景搬、CPU 同時做別的事。

#### 怎麼編譯 / 執行

```bash
cd 預製程式碼/pico/build && make -j4 app_dma
# 燒 app_dma.uf2；screen /dev/ttyACM0 115200
```

#### 對外介面

| 名稱 | 參數 | 回傳 / 效果 | 注意 |
|---|---|---|---|
| `dma_encode_transfer_count(n)`（相容補丁） | 次數 | SDK < 2.2 時直接回傳 n（`app_dma.c:21-24`） | 2.2.0 用 SDK 自己的版本 |
| `dma_xfer(to, from, count, size, rinc, winc)` | 目的、來源、次數、每次大小、讀/寫遞增 | 0 成功；-1 沒通道；-2 count ≥ 2^28（`:31-45`） | count=0 直接回 0 不啟動 |
| `dma_copy32(to, from, n)` | n = u32 個數 | 同上（`:46`） | 讀寫都遞增 |
| `dma_fill32(to, value, n)` | | 同上（`:47-50`） | 讀不遞增；值存在 `static v`（DMA 跑完前必須還在） |
| `dma_crc32(p, nbytes)` | 資料、bytes 數 | zlib CRC32（`:65-87`） | 用 `DMA_SIZE_8`，任何長度都行；沒通道會 panic |
| `cpu_crc32(p, n)` | | 逐 bit 軟體 CRC32（`:90-94`） | 對照組 |
| `N_WORDS` | — | 4096 個 u32 = 16384 bytes（`:27`） | |

**用到的 SDK 函式與 `channel_config_*`**（pico-sdk 2.2.0 `src/rp2_common/hardware_dma/include/hardware/dma.h`）

| 函式 | 行號 | 做什麼 | 本檔哪裡用 |
|---|---|---|---|
| `dma_claim_unused_channel(required)` | `dma.h:118` | 要一個空通道；`false` 沒有回 -1，`true` 沒有 panic | `:35`、`:67`、`:129` |
| `dma_channel_get_default_config(ch)` | `dma.h:430-443` | 預設：讀遞增、**寫不遞增**、`DREQ_FORCE`、chain_to = 自己、32-bit、ring 關、bswap 關、irq_quiet 關、enable 開、sniff 關、high_priority 關 | `:37`、`:69`、`:130` |
| `channel_config_set_transfer_data_size(&c, size)` | `dma.h:310` | 每次 1/2/4 bytes | `:38`、`:70` |
| `channel_config_set_read_increment(&c, b)` | `dma.h:246` | 讀位址每次往後走 | `:39`、`:71` |
| `channel_config_set_write_increment(&c, b)` | `dma.h:263` | 寫位址每次往後走 | `:40`、`:72`、`:131` |
| `channel_config_set_sniff_enable(&c, b)` | `dma.h:405` | 這個通道給 sniffer 聽 | `:77` |
| `channel_config_set_dreq(&c, dreq)` | `dma.h:282` | 節奏來源（本檔沒用，見 `app_dma_pio.c`） | — |
| `channel_config_set_chain_to(&c, ch2)` | `dma.h:296` | 做完自動啟動 ch2（預設 = 自己 = 不串） | — |
| `dma_channel_configure(ch, &c, dst, src, count, trigger)` | `dma.h:639-646` | 一次寫讀位址、寫位址、count、設定；`trigger=true` 立刻開始 | `:41`、`:79`、`:132` |
| `dma_encode_transfer_count(n)` | `dma.h:531-538` | RP2350：`n & 0x0fffffff` | 每個 configure |
| `dma_channel_wait_for_finish_blocking(ch)` | `dma.h:939-943` | 忙等 `CTRL_TRIG.BUSY` 變 0，再加 compiler barrier | `:42`、`:80`、`:135` |
| `dma_channel_unclaim(ch)` | `dma.h:103` | 歸還通道 | `:43`、`:85`、`:136` |
| `dma_sniffer_set_data_accumulator(v)` | `dma.h:1044` | 寫 `SNIFF_DATA` 初值（傳輸前） | `:73` |
| `dma_sniffer_set_output_reverse_enabled(b)` | `dma.h:1021` | 只設/清 `OUT_REV` bit（`hw_set_bits`） | `:74` |
| `dma_sniffer_enable(ch, mode, force)` | `dma.h:965-978` | `hw_write_masked` 只改 DMACH / CALC / EN，**不會清掉 OUT_REV** | `:76` |
| `dma_sniffer_get_data_accumulator()` | `dma.h:1053` | 讀 `SNIFF_DATA` | `:81` |
| `dma_sniffer_disable()` | `dma.h:1032` | `sniff_ctrl = 0` | `:84` |

#### 程式流程

1. 等 USB、填 `src[i] = i * 2654435761`（`app_dma.c:97-100`）。
2. **copy**（`:103-110`）：分別量 CPU 迴圈、`memcpy`、`dma_copy32` 的時間；DMA 前先把 `dst` 清 0，最後 `memcmp` 檢查。
3. **fill**（`:113-114`）：`dma_fill32(dst, 0xDEADBEEF, N_WORDS)`，印第一個和最後一個。
4. **sniffer CRC32**（`:117-126`）：
   - `dma_crc32("123456789", 9)` 用 cycles 量，跟 `cpu_crc32` 和期望值 `0xCBF43926` 比，印 PASS/FAIL。
   - 再對 16384 bytes 的 `src` 各算一次，比時間和結果。
5. **背景搬運**（`:129-138`）：configure 時 `trigger=true` 但**不等**，CPU 先算 `work`，要用 `dst` 前才 `wait`，最後檢查 `dst == src`（dst 之前被 fill 成 DEADBEEF，所以這個檢查有意義）。

**`dma_crc32()` 逐步（`:65-87`）**

1. `nbytes == 0` 回 0（空資料的 CRC32 就是 0）。
2. claim 通道；寫位址固定在 `static volatile uint8_t sink`（垃圾桶）。
3. 設 8-bit、讀遞增、寫不遞增。
4. **先設 sniffer 再啟動**：`SNIFF_DATA = 0xFFFFFFFF` → `OUT_REV = 1` → `dma_sniffer_enable(ch, CRC32R, false)` → 通道設定裡 `sniff_enable = true`。
5. `dma_channel_configure(..., true)` 開始搬，`wait` 等完。
6. 讀 `SNIFF_DATA` 再 `^ 0xFFFFFFFF`，關 sniffer，unclaim。

**為什麼這樣設就等於 zlib CRC32**（`regs/dma.h` 暫存器說明 + Python 模型）：

- `CALC = 0x1 CRC32R`：「CRC-32 (IEEE802.3 polynomial) with bit reversed data」（`regs/dma.h:7622`）。引擎本身是 MSB 先進；資料先反轉 = LSB 先進 = zlib 的順序。
- 引擎的暫存器方向和 zlib 相反，所以讀出時要整個 32-bit 反轉：`OUT_REV`「the result appears bit-reversed when read. This does not affect the way the checksum is calculated」（`regs/dma.h:7597-7601`）。
- zlib 初值 `FFFFFFFF`（反轉後不變），最後 `^ FFFFFFFF`（軟體做，或改設 `OUT_INV`，二選一）。
- `SNIFF_DATA`：「Write an initial seed value here before starting a DMA transfer ... Once the channel completes, the final result can be read from this register」（`regs/dma.h:7655-7661`）。

#### 預期輸出（⚠️ 沒有上板，依程式碼推算；時間是占位）

```text
copy 4096 words: loop=<t>us memcpy=<t>us dma=<t>us  正確=OK
fill: dst[0]=deadbeef dst[last]=deadbeef
crc32("123456789") dma=cbf43926 (<n> cycles) cpu=cbf43926 期望=CBF43926 PASS
crc32 16384 bytes: cpu=<t>us dma=<t>us (x<倍數>) 相同=OK
overlap: work=332833500, dma 搬完了 正確=OK
```

如果第 3 行是 FAIL：

| 讀到的 dma 值 | 意思 | 改法 |
|---|---|---|
| `649c2fd3` | 少了一次位元反轉 | `app_dma.c:74` 改 `dma_sniffer_set_output_reverse_enabled(false)` 再試（`:63` 註解） |
| `340bc6d9` | 多做了一次 `^FFFFFFFF` | `:81` 拿掉 `^ 0xFFFFFFFFu` |
| 其他 | 設定順序或 sniff_enable 沒開 | 確認 `:77` 有 `channel_config_set_sniff_enable(&c, true)`；先設 sniffer 再啟動 |

#### 要改的地方

| 行號 | 現在的值 | 意思 | 什麼情況要改、改成什麼 |
|---|---|---|---|
| `app_dma.c:27` | `4096` | 測試資料 u32 個數 | 依題目資料量；`src`/`dst` 是 static，RAM 夠就好 |
| `app_dma.c:36` | `if (ch < 0) return -1;` | 沒通道 | 題目「通道不夠」：改成 CPU fallback：`if (ch < 0) { memcpy(...); return 0; }`（食譜 3.4.7） |
| `app_dma.c:134` | `work += i*i` 迴圈 | DMA 搬運時 CPU 做的事 | 換成題目的計算，展示重疊 |

#### 實際執行輸出

- 編譯：SDK 2.2.0 與 2.1.1、ARM 與 RISC-V 都通過（3.3.1）。
- sniffer 設定的 Python 模型（`$S/ch03/sniff/model.py`，python 3.13，模型 = MSB 先進、多項式 `0x04C11DB7` 的引擎，CRC32R = 每筆資料先反轉）：

```text
zlib            = 0xcbf43926
8-bit  CRC32R+OUT_REV ^FFFFFFFF = 0xcbf43926
8-bit  沒開 OUT_REV  ^FFFFFFFF = 0x649c2fd3
8-bit  沒做 ^FFFFFFFF          = 0x340bc6d9
隨機 200 組（8-bit 與 32-bit 傳輸）都等於 zlib: 200 / 200
```

  這只證明「如果硬體照暫存器說明的方式運作」，設定是對的。**硬體實際行為要上板看 PASS/FAIL**（已知問題 9，見 3.6）。

#### 常見錯誤

| 症狀 | 原因 | 修法 |
|---|---|---|
| copy 後只有 `dst[0]` 對、其他沒變 | 預設寫**不**遞增 | `channel_config_set_write_increment(&c, true)` |
| 只搬了 1/4 的資料 | count 填成 bytes 又用 32-bit… 或反過來 count 填成 words 卻用 8-bit | count = bytes ÷ 每次大小 |
| DMA 永遠不結束 | count ≥ 2^28 被當成 MODE（例如 TRIGGER_SELF） | 用 `dma_encode_transfer_count(n)`，n < 2^28，太大分段 |
| `panic: No DMA channels are available` 或回 -1 | 用完沒 `unclaim` | 每個 claim 都配一個 unclaim |
| fill 出來是亂碼 | 來源變數是區域變數，DMA 還在讀它就被蓋掉 | 來源用 `static`（`:48`） |
| 32-bit 搬運資料錯位 | 位址沒 4-byte 對齊（`char` 陣列強轉） | 用 `uint32_t` 陣列，或改 `DMA_SIZE_8` |
| CRC 每次都一樣錯 | sniffer 在啟動通道之後才設定 | 順序：設 accumulator → 設 sniffer → 啟動通道 |
| 兩個通道同時算 CRC 結果亂 | sniffer 全晶片只有一組 | 一次只給一個通道用 |
| `'dma_encode_transfer_count' undeclared`（舊 SDK、新寫的檔案） | SDK < 2.2.0 沒有這個函式 | 照抄 `app_dma.c:21-24` 的補丁 |

### 3.3.9 `app_dma_pio.c`

#### 用途

用 DREQ 讓 DMA 跟著 PIO FIFO 的節奏搬資料：`src[]` → PIO TX FIFO →（echo 程式原樣送回）→ PIO RX FIFO → `dst[]`。CPU 完全不用動。再跟「CPU 自己 put/get」比速度。

```text
           ch_tx（DREQ = PIO0_TX<sm>：TX FIFO 沒滿才寫）
 src[N] ──讀遞增──► &pio0->txf[sm] ──► TX FIFO(4) ──autopull──► OSR
                                                                 │ out x,32
                                                                 ▼
                                                                 X
                                                                 │ in x,32
                                                                 ▼
 dst[N] ◄──寫遞增── &pio0->rxf[sm] ◄── RX FIFO(4) ◄───push────── ISR
           ch_rx（DREQ = PIO0_RX<sm>：RX FIFO 有資料才讀）
```

#### 怎麼編譯 / 執行

```bash
cd 預製程式碼/pico/build && make -j4 app_dma_pio
# 燒 app_dma_pio.uf2；screen /dev/ttyACM0 115200
```

#### 對外介面

| 名稱 | 參數 | 回傳 / 效果 | 注意 |
|---|---|---|---|
| `N` | — | 搬幾個 u32（`app_dma_pio.c:34`） | 預設 4096 |
| `pio_get_dreq(pio, sm, is_tx)` | | DREQ 編號（`hardware_pio/include/hardware/pio.h:911-915`） | = `PIO_DREQ_NUM`（`pio.h:229`）；PIO0 TX0..3 = 0..3、RX0..3 = 4..7（`regs/dreq.h:16-23`） |
| `&pio->txf[sm]` / `&pio->rxf[sm]` | | FIFO 的暫存器位址 | 寫 TX、讀 RX |
| `dma_start_channel_mask(mask)` | 通道位元遮罩 | 同時啟動（`dma.h:704-707`） | 寫 `multi_channel_trigger` |

#### 程式流程

1. 等 USB、填 `src[i] = i * 0x9E3779B9`（`:39-41`）。
2. 載入 echo：`pio_add_program` 檢查 `< 0`（`:45-47`）、`pio_claim_unused_sm(pio, true)`（`:48`）、`echo_program_init`（`:49`）。
3. 要兩個 DMA 通道（`:52-54`），任一個失敗就印 `DMA 通道不夠` 停住。
4. **ch_tx**（`:56-62`）：32-bit、讀遞增、寫不遞增、DREQ = TX；configure 時 `trigger=false`（先不開始）。
5. **ch_rx**（`:64-69`）：32-bit、讀不遞增、寫遞增、DREQ = RX；也先不開始。
6. `dma_start_channel_mask((1u << ch_tx) | (1u << ch_rx))`（`:73`）同時啟動。
7. 先等 ch_rx（資料全回來），再等 ch_tx（確認 BUSY=0 才 unclaim）（`:75-76`）。
8. 印 DMA 時間與 `memcmp` 結果（`:79-80`）。
9. 對照組：清 `dst`，CPU 一次 `pio_sm_put_blocking` 一次 `pio_sm_get_blocking`（`:82-87`）。
10. 收拾：unclaim 兩個通道、停 SM、`pio_remove_program_and_unclaim_sm`（`:90-93`）。

**為什麼一定要兩個通道一起開**：只開 TX → RX FIFO 滿 → SM 卡在 `push` → OSR 不再 pull → TX FIFO 滿 → ch_tx 永遠 BUSY（`:16-17` 註解）。

**為什麼 echo 不能 fifo_join**：echo 同時用 TX 和 RX；join 會讓其中一個停用（`regs/pio.h:992-996`：「RX FIFO is disabled as a result」）。

#### 預期輸出（⚠️ 沒有上板）

```text
DMA+PIO 4096 words: <t> us, 結果 OK
CPU put/get 4096 words: <t> us (DMA 快 x<倍數>) 結果 OK
```

#### 要改的地方

| 行號 | 現在的值 | 意思 | 什麼情況要改、改成什麼 |
|---|---|---|---|
| `app_dma_pio.c:34` | `4096` | 搬幾個 u32 | 依題目；必須 < 2^28 |
| `app_dma_pio.c:74` | 註解 | DMA 搬運時 CPU 可以做的事 | 放題目的計算，展示 CPU 空出來 |

#### 實際執行輸出

編譯通過（3.3.1）。板子上沒有實測。

#### 常見錯誤

| 症狀 | 原因 | 修法 |
|---|---|---|
| 永遠卡在 wait | 只啟動了一個通道；或 DREQ 設反（TX 用了 RX 的） | 用 mask 一起開；`pio_get_dreq(pio, sm, true)` 給 TX |
| 資料重複 / 掉資料 | 忘了設 DREQ（用預設 DREQ_FORCE 全速塞） | `channel_config_set_dreq` |
| 改成 8-bit DMA 後值不對 | `.pio` 門檻與移位方向沒跟著改 | 見食譜 3.4.5 |
| 第二次執行時 `PIO 指令空間不夠` | 前一個程式沒 remove | `pio_remove_program_and_unclaim_sm` |

### 3.3.10 `app_pio.c`

#### 用途

兩個 PIO 測試：`test_echo()`（pio0 上跑 echo，送 4 個字、量 10000 字的時間）和 `test_loopback()`（pio1 上同時跑 `shift_out` 送、`bitstream_in` 收，同一顆晶片自己收自己送的腳，不用接線）。

```text
 CPU ─put─► [pio1 SM_tx: shift_out]  TX FIFO(8, join) → OSR ─out pins,1─► GPIO2 (DATA)
                                                      side-set ─────────► GPIO3 (CLK)
                                                                           │ │（PIO 讀得到自己輸出的腳）
 CPU ◄get── [pio1 SM_rx: bitstream_in] RX FIFO(8, join) ◄─autopush─ ISR ◄─in pins,1 (DATA)，wait pin 1 (CLK)
```

#### 怎麼編譯 / 執行

```bash
cd 預製程式碼/pico/build && make -j4 app_pio
# 燒 app_pio.uf2；screen /dev/ttyACM0 115200。不需要接線。
```

#### 對外介面

| 名稱 | 參數 | 回傳 / 效果 | 注意 |
|---|---|---|---|
| `DATA_PIN` / `CLK_PIN` | — | 2 / 3（`app_pio.c:21-22`） | **CLK 必須 = DATA + 1**（bitstream_in 規定） |
| `load(pio, prog, &sm, &offset)` | | 載入程式 + 要 SM；失敗回 false（`:25-33`） | SM 要不到時會把程式拿掉 |
| `test_echo()` | — | `:35-57` | 用完會 remove + unclaim |
| `test_loopback()` | — | `:59-81` | **用完沒有釋放**（已知問題 6） |

SDK 函式（`hardware_pio/include/hardware/pio.h`，SDK 2.2.0）：

| 函式 | 行號 | 一句話 |
|---|---|---|
| `pio_add_program(pio, &prog)` | `pio.h:974` | 載入指令，回 offset；失敗回負數 |
| `pio_remove_program(pio, &prog, off)` | `pio.h:996` | 拿掉指令 |
| `pio_claim_unused_sm(pio, required)` | `pio.h:1980` | 要 SM；`false` 沒有回 -1 |
| `pio_sm_init(pio, sm, pc, &c)` | `pio.h:1027` | 套用設定、PC 指到 pc |
| `pio_sm_put_blocking / pio_sm_get_blocking` | `pio.h:1740`、`:1753` | TX 滿 / RX 空就等 |
| `pio_sm_is_rx_fifo_empty`、`pio_sm_get` | `pio.h` | 不等版本 |
| `pio_remove_program_and_unclaim_sm` | `pio.h:2038` | 一次收拾 |
| `pio_gpio_init(pio, pin)` | `pio.h:898` | 腳位交給 PIO（也解除 RP2350 pad 隔離） |

#### 程式流程

1. 等 USB，印 `clk_sys`（`:84-87`）。
2. `test_echo()`：載入 → `echo_program_init` → 4 個測試值各 put 再 get，印出（`:41-46`）→ 10000 個字 put/get 量時間，印 xor（`:49-53`）→ 停 SM、remove + unclaim（`:55-56`）。
3. `test_loopback()`：pio1 載入 `bitstream_in`（先開接收端）和 `shift_out`（clkdiv 10）（`:62-66`）→ 4 個訊息各 put 到 SM_tx，最多等 100 ms 等 SM_rx 的 RX FIFO 有東西（`:71-75`）→ 印每個結果與 `n/4 正確`。

#### 預期輸出（⚠️ 沒有上板，依程式碼推算）

```text
clk_sys = 150000000 Hz
echo: 送 12345678 收 12345678
echo: 送 ffffffff 收 ffffffff
echo: 送 00000001 收 00000001
echo: 送 a5a5a5a5 收 a5a5a5a5
echo 10000 字: <t> us (xor=00000000)
loopback: 送 deadbeef 收 deadbeef OK
loopback: 送 0f0f0f0f 收 0f0f0f0f OK
loopback: 送 80000001 收 80000001 OK
loopback: 送 12345678 收 12345678 OK
loopback: 4/4 正確
```

- `clk_sys = 150000000` 是 SDK 預設（`platform_defs.h:114`），板子上沒確認。
- `xor=00000000`：0 xor 1 xor … xor 9999，因為 9999 除以 4 餘 3，結果是 0（計算）。
- loopback 速度：150 MHz / 10 / 4 cycle = 3.75 Mbit/s（計算，`shift_out.pio:6`）。
- loopback 若收 `00000000 錯`：100 ms 內沒收到東西（腳位錯、CLK 不是 DATA+1、SM 沒啟動）。

#### 要改的地方

| 行號 | 現在的值 | 意思 | 什麼情況要改、改成什麼 |
|---|---|---|---|
| `app_pio.c:21` | `DATA_PIN 2` | 資料腳 | 題目規定的腳位 |
| `app_pio.c:22` | `CLK_PIN 3` | 時脈腳 | 必須 = DATA_PIN + 1；不想受限就把 `bitstream_in.pio` 改成 `wait 1 gpio N`（絕對編號） |
| `app_pio.c:41` | 4 個測試值 | echo 測試資料 | 題目的測試向量 |
| `app_pio.c:66` | `10.0f` | shift_out 的 clkdiv | 位元速率 = clk_sys / clkdiv / 4；配 bitstream_in 時 clkdiv 建議 ≥ 2（`bitstream_in.pio:25-26`） |

#### 實際執行輸出

編譯通過（3.3.1）。板子上沒有實測。

#### 常見錯誤

| 症狀 | 原因 | 修法 |
|---|---|---|
| `echo: 載入失敗` / `loopback: 載入失敗` | 指令空間（32 條）不夠或 SM 用完 | 換一個 PIO 區塊（pio0/1/2），或先 remove 舊的 |
| loopback 全部 `錯` | 腳位沒 `pio_gpio_init`；CLK ≠ DATA+1 | 檢查 `bitstream_in_program_init` 的腳位 |
| loopback 值整個錯位（例如左移了幾 bits） | 接收端在送端開始前抓到假的 CLK 邊緣 | 先開接收端（現在就是）；確認腳位初值是 0 |
| `pio_sm_get_blocking` 永遠卡住 | RX FIFO 沒資料（push 沒發生、門檻不對） | 用有 timeout 的寫法（`:73-75`） |

### 3.3.11 `pio/echo.pio`

#### 用途

最簡單的 PIO 程式：TX FIFO 進來的 32-bit 原樣推回 RX FIFO。`app_pio.c` 和 `app_dma_pio.c` 都用它。

#### 怎麼編譯 / 執行

CMake 的 `pico_generate_pio_header` 用 pioasm 轉成 `build/echo.pio.h`。實際產生的指令（pioasm 2.2.0）：

```text
    0x6020, //  0: out    x, 32
    0x4020, //  1: in     x, 32
    0x8020, //  2: push   block
```

#### 對外介面

| 名稱 | 參數 | 回傳 / 效果 | 注意 |
|---|---|---|---|
| `echo_program` | — | 3 條指令的程式（`echo.pio.h`） | `pio_add_program(pio, &echo_program)` |
| `echo_program_init(pio, sm, offset)` | | 設定 + 啟動（`echo.pio:19-25`） | 不碰任何 GPIO |

#### 程式流程（逐條指令）

| 行 | 指令 | 做什麼 | 什麼時候停住 |
|---|---|---|---|
| `echo.pio:8` | `.wrap_target` | 迴圈起點 | — |
| `echo.pio:9` | `out x, 32` | OSR 的 32 bits 全部移到 X。autopull 開、門檻 32：OSR 空了就自動從 TX FIFO 補 | TX FIFO 空時停在這裡 |
| `echo.pio:13` | `in x, 32` | X 的 32 bits 移進 ISR（autopush 關，不會自動送） | 不會停 |
| `echo.pio:14` | `push` | ISR → RX FIFO（pioasm 預設 `block`） | RX FIFO 滿時停在這裡（= 自動流量控制） |
| `echo.pio:15` | `.wrap` | 跳回 `:8`，不花 cycle | — |

C 設定（`echo.pio:19-25`）：

| 呼叫 | 意思 |
|---|---|
| `echo_program_get_default_config(offset)` | 預設設定 + wrap 範圍（pioasm 產生） |
| `sm_config_set_out_shift(&c, false, true, 32)` | OSR 左移、autopull 開、門檻 32 |
| `sm_config_set_in_shift(&c, false, false, 32)` | ISR 左移、autopush **關**（手動 push，否則會 push 兩次）、門檻 32 |
| `pio_sm_init` / `pio_sm_set_enabled(..., true)` | 套用、啟動 |

- 每個字最少 3 個 SM cycle（3 條指令、沒有 delay）。
- 32-bit 整個搬，所以左移右移結果一樣。

#### 要改的地方

| 行號 | 現在的值 | 意思 | 什麼情況要改、改成什麼 |
|---|---|---|---|
| `echo.pio:10-12` | 註解 | 在 `out` 和 `in` 中間做位元運算 | 每個 bit 反相：加 `mov x, ~x`；位元順序反轉（bit31↔bit0）：加 `mov x, ::x`。`app_pio.c` 的期望值要跟著改 |

#### 實際執行輸出

pioasm 組譯結果如上（`build-arm/echo.pio.h`）。板子上沒有實測。

#### 常見錯誤

| 症狀 | 原因 | 修法 |
|---|---|---|
| 每個字收到兩次 | autopush 開了又手動 push | `in_shift` 第三個參數 `false` |
| 收到一串 0、跟送的對不上 | autopull 沒開：`out` 不等 TX FIFO，直接從空的 OSR 移出 0 | `out_shift` 第三個參數 `true` |
| put 之後 get 永遠卡住 | SM 沒啟動 | `pio_sm_set_enabled(pio, sm, true)` |

### 3.3.12 `pio/bitstream_in.pio`

#### 用途

收位元流：每次 CLK 上升沿取樣 DATA 一個 bit，每 32 bits 自動 push 一個字到 RX FIFO（和 pico-examples 的 `pio/clocked_input` 同結構）。

#### 怎麼編譯 / 執行

pioasm 產生的指令（`build-arm/bitstream_in.pio.h`）：

```text
    0x2021, //  0: wait   0 pin, 1
    0x20a1, //  1: wait   1 pin, 1
    0x4001, //  2: in     pins, 1
```

#### 對外介面

| 名稱 | 參數 | 回傳 / 效果 | 注意 |
|---|---|---|---|
| `bitstream_in_program_init(pio, sm, offset, data_pin)` | DATA 腳 | 設定 + 啟動（`bitstream_in.pio:19-34`） | CLK = `data_pin + 1` |

#### 程式流程（逐條指令）

| 行 | 指令 | 做什麼 | 什麼時候停住 |
|---|---|---|---|
| `:7` | `.wrap_target` | 起點 | |
| `:8` | `wait 0 pin 1` | 等「in_base + 1」那支腳（CLK）= 0 | CLK 是 1 時 |
| `:9` | `wait 1 pin 1` | 等 CLK = 1 → 抓到上升沿 | CLK 是 0 時 |
| `:10` | `in pins, 1` | 從 in_base（DATA）讀 1 bit 移進 ISR；autopush 門檻 32 → 滿 32 bits 自動 push | RX FIFO 滿時 |
| `:11` | `.wrap` | 回 `:8` | |

- `pin 1` 的 1 是**相對 in_base**（`sm_config_set_in_pins` 設的那支）。要用絕對 GPIO 編號寫 `wait 1 gpio N`（`:2-3`）。
- 每個 bit 至少 3 個 SM cycle；送端 CLK 高、低各至少要維持 2 個接收端 cycle 才不會漏（`:25-26` 註解，推導）。

C 設定（`:19-34`）：

| 呼叫 | 意思 |
|---|---|
| `sm_config_set_in_pins(&c, data_pin)` | in_base = DATA（`in pins` 和 `wait pin` 的基準） |
| `sm_config_set_in_shift(&c, false, true, 32)` | ISR 左移（第一個收到的 bit 最後在 bit31）、autopush 開、門檻 32 |
| `sm_config_set_fifo_join(&c, PIO_FIFO_JOIN_RX)` | 不用 TX → RX FIFO 4 格變 8 格 |
| `sm_config_set_clkdiv(&c, 1.0f)` | 全速取樣 |
| `pio_gpio_init(pio, data_pin)`、`(data_pin + 1)` | 兩支腳交給 PIO；**不設 pindirs**（保持輸入，不跟送端搶腳） |
| `pio_sm_init`、`pio_sm_set_enabled` | 套用、啟動 |

**左移 + MSB 先送 → 收到的字 = 送出的字**：送端先送 bit31，收端每收一個 bit 就把 ISR 往左推，32 次後最早收到的 bit 剛好在 bit31。

#### 要改的地方

| 行號 | 現在的值 | 意思 | 什麼情況要改、改成什麼 |
|---|---|---|---|
| `bitstream_in.pio:13-16` | 註解 | 常見變化 | 沒有 CLK、固定速率：迴圈只留 `in pins, 1`，取樣率 = clk_sys / clkdiv。一次讀 8 支腳：`in pins, 8`，門檻 32 → 每 4 次取樣 push 一次。量脈衝長度：用 `jmp x--` 當計數器 |
| `bitstream_in.pio:22` | 門檻 `32` | 幾個 bit 組成一個字 | 8-bit 一組：`sm_config_set_in_shift(&c, false, true, 8)`，push 出來的值在 `bits[7:0]`（食譜 3.4.5） |

#### 實際執行輸出

pioasm 組譯結果如上。板子上沒有實測。

#### 常見錯誤

| 症狀 | 原因 | 修法 |
|---|---|---|
| 永遠收不到 | 外部訊號沒 `pio_gpio_init`（RP2350 pad 隔離）；CLK 不是 DATA+1 | 兩支都 init；改腳位或改 `wait gpio` |
| 收到的值位元順序相反 | 送端 LSB 先送 | 改 `in_shift` 為右移（`true`）：32 bits 時第一個收到的 bit 會落在 bit0 |
| 每個字多/少 1 bit | 接收端比送端晚開，漏了邊緣；或雜訊 | 先開接收端；送端 clkdiv 加大 |

### 3.3.13 `pio/shift_out.pio`

#### 用途

把 32-bit 資料一位一位送到 DATA 腳，同時用 side-set 在 CLK 腳產生時脈（最簡單的 SPI 輸出）。

#### 怎麼編譯 / 執行

pioasm 產生的指令（`build-arm/shift_out.pio.h`）：

```text
    0x6101, //  0: out    pins, 1         side 0 [1]
    0xb142, //  1: nop                    side 1 [1]
```

`shift_out_program_get_default_config` 裡 pioasm 自動加了 `sm_config_set_sideset(&c, 1, false, false)`（1 支、非 optional、不是 pindirs）。

#### 對外介面

| 名稱 | 參數 | 回傳 / 效果 | 注意 |
|---|---|---|---|
| `shift_out_program_init(pio, sm, offset, data_pin, clk_pin, clkdiv)` | | 設定 + 啟動（`shift_out.pio:18-33`） | 兩支腳不必相鄰 |

#### 程式流程（逐條指令）

時序（每個 bit 4 個 SM cycle）：

```text
 SM cycle:   0    1    2    3    4    5    6    7
 DATA     ===<b31=======><b30=======><b29 ...
 CLK      ____|‾‾‾‾‾‾‾‾‾|____|‾‾‾‾‾‾‾‾‾|____
          out [1]   nop [1]   out [1]  nop [1]
          (CLK=0)   (CLK=1)   ...      接收端在 CLK 上升沿取樣
```

| 行 | 指令 | 做什麼 | 什麼時候停住 |
|---|---|---|---|
| `:9` | `.side_set 1` | 每條指令有 1 bit side-set 欄位（非 optional：每條都要寫 `side`） | |
| `:11` | `out pins, 1 side 0 [1]` | OSR 拿 1 bit 到 DATA；CLK = 0；再多等 1 cycle（共 2 cycle） | OSR 空且 TX FIFO 空時（autopull 等資料），CLK 保持 0 |
| `:12` | `nop side 1 [1]` | CLK = 1；多等 1 cycle（共 2 cycle） | 不會停 |
| `:13` | `.wrap` | 回 `:11` | |

- 編碼：`.side_set 1`（非 opt）→ 指令裡 5 bit 的 delay/side-set 欄位，1 bit 給 side、4 bit 給 delay，`[n]` 最大 15（`:15`）。
- 「停在 `out` 時 side-set 仍然生效」：依 datasheet side-set 說明與 pico-examples `pio/spi` 的用法推定（`README.md:166`），⚠️未驗證。

C 設定（`:18-33`）：

| 呼叫 | 意思 |
|---|---|
| `sm_config_set_out_pins(&c, data_pin, 1)` | `out pins` 從 DATA 開始、1 支 |
| `sm_config_set_sideset_pins(&c, clk_pin)` | side-set 從 CLK 開始 |
| `sm_config_set_out_shift(&c, false, true, 32)` | OSR 左移 = MSB 先送；autopull 門檻 32 |
| `sm_config_set_fifo_join(&c, PIO_FIFO_JOIN_TX)` | 不用 RX → TX FIFO 4 格變 8 格 |
| `sm_config_set_clkdiv(&c, clkdiv)` | 速度 |
| `pio_sm_set_pins_with_mask(pio, sm, 0, mask)` | DATA、CLK 先設 0（同 pico-examples spi） |
| `pio_sm_set_pindirs_with_mask(pio, sm, mask, mask)` | 兩支都設成輸出 |
| `pio_gpio_init` ×2、`pio_sm_init`、`pio_sm_set_enabled` | 交給 PIO、套用、啟動 |

#### 要改的地方

| 行號 | 現在的值 | 意思 | 什麼情況要改、改成什麼 |
|---|---|---|---|
| `shift_out.pio:25` | `sm_config_set_clkdiv(&c, clkdiv)` | 速度由呼叫端給（`app_pio.c:66` 傳 10） | 位元速率 = clk_sys / clkdiv / 4 |
| `shift_out.pio:23` | 左移、門檻 32 | MSB 先、一次 32 bits | 8-bit 一組見食譜 3.4.5；LSB 先送改 `true`（右移） |

#### 實際執行輸出

pioasm 組譯結果如上。板子上沒有實測。

#### 常見錯誤

| 症狀 | 原因 | 修法 |
|---|---|---|
| pioasm 報錯說缺 side | `.side_set 1` 非 optional，某條指令沒寫 `side` | 每條都寫 `side 0/1`，或改 `.side_set 1 opt` |
| CLK 腳沒動 | 沒 `sm_config_set_sideset_pins` 或沒設 pindir | 照 `:22`、`:28` |
| 送出的 bit 順序相反 | 移位方向 | 左移 = MSB 先 |

### 3.3.14 `README.md`

#### 用途

資料夾的總說明：檔案↔題型（`README.md:6-15`）、build（`:17-27`）、燒錄（`:29-33`）、API 小抄（`:35-61`）、文件連結（`:63-70`）、13 條陷阱（`:72-87`）、設計審查紀錄（`:89-168`）。本章已把內容逐條對照 SDK 2.2.0 原始碼核對過。

#### 怎麼編譯 / 執行

不需要。

#### 對外介面

無。

#### 程式流程

無。

#### 要改的地方

沒有 `TODO(改這裡)`（`:4` 只是說明慣例）。

#### 實際執行輸出

不適用。

#### 常見錯誤

| 症狀 | 原因 | 修法 |
|---|---|---|
| 以為電腦端 `on_bytes()` 沒擋大資料（舊版 `README.md:143` 這樣寫） | 那一列過時（已更新） | 見 3.6.1：現在會拒絕 > 4096 bytes |
| `README.md:87` 寫「USB 速度上限約 1 MB/s」 | Full Speed 12 Mbit/s 是規格；實際吞吐量沒有實測 | 需要數字就自己用 `ros2/bench.py` 量 |

## 3.4 照題目改：食譜

下面食譜的「改後」程式碼，作者在 `$S/ch03/recipe_src`（`pico/` 的副本）實際改過並用 SDK 2.2.0 ARM 編譯通過、0 warning（3.4.1 的鎖、3.4.2、3.4.4、3.4.5 的 echo8、3.4.6 的排序）。**都沒有上板。**

### 3.4.1 修 race：加 spinlock

**題目長這樣**：「兩顆核心同時把結果加到 `total`，答案每次都不一樣，請修正。」

**改哪裡**（以 `app_multicore.c` 的寫法為準）：

1. 全域加一個鎖指標：

```c
static spin_lock_t *lock;                 // 同 app_multicore.c:29
```

2. `main()` 在 `multicore_launch_core1` **之前**初始化：

```c
lock = spin_lock_init((uint)spin_lock_claim_unused(true));   // 同 app_multicore.c:92
```

3. 改共用變數的那一行，前後加鎖：

```c
// 改前
total += x;
// 改後
uint32_t save = spin_lock_blocking(lock);   // 關中斷 + 拿鎖
total += x;                                  // 只放「一定要保護」的那一行
spin_unlock(lock, save);                     // 放鎖 + 恢復中斷
```

4. `total` 要宣告成 `volatile`（讓另一核讀得到最新值），但 volatile 不能取代鎖。
5. 也可以用 critical_section（`app_multicore.c:41-43`）：`critical_section_enter_blocking(&cs); total += x; critical_section_exit(&cs);`，`critical_section_init(&cs)` 一樣在 launch 前呼叫。

**怎麼驗證**：跑多次，結果都一樣且等於單核算的答案（`app_multicore` 的預期輸出：spinlock 那行 `counter=400000`）。

**成功的樣子**：每次都正確；但會比不鎖慢（每次加都要拿鎖），所以接著做 3.4.2。

### 3.4.2 縮小臨界區（鎖抓太長）

**題目長這樣**：「已經加了鎖，答案對了但很慢；請在保持正確的前提下加速。」

**原則**：鎖裡只放「讀寫共用資料」那幾行；耗時的計算移到鎖外面；能先在區域變數累積就最後只鎖一次。

```c
// 改前：計算也在鎖裡（另一核一直在等）
for (int i = 0; i < n; i++) {
    uint32_t s = spin_lock_blocking(lock);
    total += heavy_compute(data[i]);
    spin_unlock(lock, s);
}
// 改後：先在區域變數算完，最後鎖一次合併
uint32_t local = 0;
for (int i = 0; i < n; i++) local += heavy_compute(data[i]);   // 不用鎖：local 是自己的
uint32_t s = spin_lock_blocking(lock);
total += local;                                                // 臨界區只剩 1 行、只進 1 次
spin_unlock(lock, s);
```

作者在副本裡把這個寫法加成 `app_multicore` 的第 4 種模式（`lock_mode == 3`，名稱「區域變數+鎖一次」），編譯通過。`app_multicore.c:46-48` 的註解就是這個做法。

**怎麼驗證**：結果和 3.4.1 一樣；用 `time_us_64()` 比較兩種寫法的時間（`app_multicore.c:103`、`:110` 已經在量）。

**成功的樣子**：答案相同、時間明顯變短（倍數沒有實測，要自己量）。

**更進一步**：如果題目是「一核收資料、一核計算」，改用 `queue_t` pipeline（`app_multicore.c` 第 2 部分）：core0 收封包放進 `q_job`，core1 算完放 `q_result`。注意 `app_serial.c` 的 `rx` 只有一份，要像 `data_buf[4][...]` 那樣輪流用多塊 buffer（`app_serial.c:85-86` 註解）。

### 3.4.3 把 CPU 複製迴圈換成 DMA

**題目長這樣**：「下面的迴圈把資料從 A 複製到 B，請改用 DMA。」

**改哪裡**：把 `app_dma.c:21-24`（相容補丁）、`:31-46`（`dma_xfer`、`dma_copy32`）複製到你的檔案，CMakeLists 加 `hardware_dma`。

```c
// 改前
for (int i = 0; i < n; i++) dst[i] = src[i];        // uint32_t 陣列，n 個
// 改後
if (dma_copy32(dst, src, n) != 0) {                   // count = n「個 u32」，不是 n*4 bytes
    for (int i = 0; i < n; i++) dst[i] = src[i];      // 沒通道 / 太大：退回 CPU
}
```

- 資料是 `uint8_t` 陣列、長度 `nbytes`：`dma_xfer(dst, src, nbytes, DMA_SIZE_8, true, true)`；或位址 4-byte 對齊且 `nbytes % 4 == 0` 時用 `DMA_SIZE_32` 搬 `nbytes / 4` 次（比較快）。
- 要 CPU 同時做事：照 `app_dma.c:129-136`，configure 時 `trigger=true` 但不馬上等，用到 `dst` 前才 `dma_channel_wait_for_finish_blocking`。
- 檢查清單：寫遞增有開？count 是次數？< 2^28？有 unclaim？來源在 DMA 跑完前還存在？

**怎麼驗證**：`memcmp(dst, src, bytes) == 0`；先把 `dst` 清成別的值再搬（`app_dma.c:107`）。

**成功的樣子**：`正確=OK`，DMA 時間印出來（倍數要上板量）。

### 3.4.4 用 sniffer 算 CRC32（取代軟體 CRC）

**題目長這樣**：「`CMD_CRC32` 用軟體算太慢，請用硬體 CRC。」

**先決條件**：先燒 `app_dma.uf2`，確認 `crc32("123456789") ... PASS`。FAIL 就照 3.3.8 的表調整後再搬過來。

**改哪裡**（以 `app_serial` 為例，作者已在副本編譯通過）：

1. `CMakeLists.txt:32` 改成 `target_link_libraries(app_serial pico_multicore hardware_dma)`。
2. `app_serial.c:17`（`#include "serial_proto.h"` 後）加：`#include "hardware/dma.h"`、`app_dma.c:21-24` 的相容補丁、`app_dma.c:65-87` 的 `dma_crc32()` 整個函式。
3. `app_serial.c:45` 改：

```c
// 改前
uint32_t c = crc32_update(0, f->payload, f->len);
// 改後
uint32_t c = dma_crc32(f->payload, f->len);
```

- 不要在 `dma_crc32` 裡 printf（app_serial 不能印字）。
- `dma_crc32` 用 `dma_claim_unused_channel(true)`：沒通道會 panic；要保險改成 `false` + 失敗時呼叫 `crc32_update`。
- 分段續算不要用 sniffer（`app_dma.c:82-83`：寫入 `SNIFF_DATA` 時 OUT_REV 是否作用文件沒寫）。

**怎麼驗證**：電腦端 `unpack_u32(transact(ser, CMD_CRC32, data))[0] == zlib.crc32(data)`，測 `b"123456789"`、空資料、4096 bytes 隨機資料。

**成功的樣子**：三種都相等。⚠️ 沒有上板。

### 3.4.5 改 PIO 的位元寬度

**先記住兩條規則**（`regs/pio.h:1024-1035`）：OUT 左移從 bit31 拿、右移從 bit0 拿；IN 左移新資料進 bit0、右移新資料進 bit31。門檻 = 幾個 bit 觸發 autopull/autopush。

**(a) echo 改成一次 8 bits**（作者在副本建了 `pio/echo8.pio` + `app_echo8.c`，編譯通過，pioasm 輸出 `0x6028 out x, 8`、`0x4028 in x, 8`、`0x8020 push block`）：

```text
.program echo8
.wrap_target
    out x, 8           ; OSR 右移：取最低 8 bits；門檻 8 → 用完 8 bits 就 autopull 下一個字
    in  x, 8           ; ISR 左移：新 bits 從 LSB 進來 → push 出去的值在 bits[7:0]
    push
.wrap
```

```c
sm_config_set_out_shift(&c, true, true, 8);    // 右移、autopull、門檻 8
sm_config_set_in_shift(&c, false, false, 8);   // 左移、autopush 關、門檻 8
```

預期：put `0xA0` → get `0x000000A0`（⚠️ 沒上板）。如果 out 用左移，`out x, 8` 會拿到 bit31..24，CPU 就要 put `v << 24`。

**(b) shift_out 一次送 8 bits、MSB 先**：`shift_out.pio:23` 改成 `sm_config_set_out_shift(&c, false, true, 8);`，送的時候 `pio_sm_put_blocking(pio, sm, (uint32_t)byte << 24);`（左移從 bit31 開始拿，只送最高 8 bits）。想 LSB 先送：改右移 `true`，直接 put `byte`。

**(c) bitstream_in 每 8 bits push 一次**：`bitstream_in.pio:22` 改 `sm_config_set_in_shift(&c, false, true, 8);`，收到的值在 `bits[7:0]`。若改右移，值在 `bits[31:24]`，要 `>> 24`。

**(d) 配 DMA 用 8-bit 傳輸**：DMA `DMA_SIZE_8` 寫 PIO TX FIFO 時，每次寫入仍然推一整個 32-bit 字進 FIFO；窄寫入在匯流排上的 byte lane 行為（是否把 byte 複製到 4 個位置）⚠️未驗證（`app_dma_pio.c:19-20` 也這樣註明）。最保險：DMA 維持 32-bit，PIO 端用門檻 32、`out x, 8` 四次拆開。

**怎麼驗證**：`app_pio` 的 loopback：送端和收端改成同樣的寬度與方向，送 `0x00..0xFF` 每個值比對。

**成功的樣子**：送什麼收什麼；位元順序錯時檢查兩端的移位方向是否一致。

### 3.4.6 在序列埠協定加一個新指令

**題目長這樣**：「新增指令 0x04：payload 是 u32 陣列，回傳排序後的陣列。」

**改哪裡**（作者已在副本編譯通過）：

1. `serial_proto.h:20` 下面加：`#define CMD_SORT_U32 0x04  // payload = u32 陣列 → 回排序後的 u32 陣列`
2. `app_serial.c:51`（`// TODO(改這裡) 新指令加在這裡`）上面加：

```c
    case CMD_SORT_U32: {
        uint32_t n = f->len / 4;
        static uint32_t a[FRAME_MAX_PAYLOAD / 4];      // static：不要放 stack；u32 陣列天生 4-byte 對齊
        memcpy(a, f->payload, n * 4);
        for (uint32_t i = 1; i < n; i++) {             // 插入排序（小資料夠用；大資料換 algo/ 的排序）
            uint32_t v = a[i]; uint32_t j = i;
            while (j > 0 && a[j - 1] > v) { a[j] = a[j - 1]; j--; }
            a[j] = v;
        }
        proto_send(f->cmd, f->seq, (const uint8_t *)a, (uint16_t)(n * 4));
        break;
    }
```

3. 電腦端 `ros2/frame.py:17` 加 `CMD_SORT_U32 = 0x04`（數字一定要一樣），`ros2/fake_pico.py` 若要用模擬板也要加對應處理（見第 2 章）。
4. 回覆長度 ≤ `FRAME_MAX_PAYLOAD`；結果比輸入大的指令（例如回傳 u64）要檢查。

**怎麼驗證**：

```python
vals = [5, 3, 9, 1]
r = unpack_u32(transact(ser, 0x04, pack_u32(vals)))
assert r == sorted(vals), r
```

**成功的樣子**：`assert` 通過；電腦端沒有逾時訊息。⚠️ 沒上板；插入排序是 O(n²)，2048 個數以上換 `algo/` 的排序（見第 5 章）。

### 3.4.7 DMA 通道不夠用

**題目長這樣**：「要做 5 個搬運，但只有 4 個通道（或你沒 unclaim）。」

- 先找有沒有 claim 了沒 unclaim 的地方（每個 `dma_claim_unused_channel` 都要對到一個 `dma_channel_unclaim`）。
- 用 `dma_claim_unused_channel(false)`，回 -1 就排隊：等前一個 `dma_channel_wait_for_finish_blocking` + unclaim 後再要。
- 或退回 CPU（`app_dma.c:36` 的 TODO）。
- 同一個通道可以重複用：改位址後再 configure 一次。

**怎麼驗證**：每次搬完 `memcmp`；`dma_channel_is_claimed(ch)`（`dma.h:128`）檢查有沒有還。

## 3.5 效能：量測方法與實測數字

**量測方法**

| 要量什麼 | 用什麼 | 範例在哪 |
|---|---|---|
| 一段程式（毫秒級以上） | `time_us_64()` 前後相減、`PRINT_US` | `app_dma.c:103-108`、`app_multicore.c:103-110` |
| 很短的程式（< 0.1 秒） | `cycles_init` / `cycles_now` / `cycles_since` | `app_dma.c:117-120` |
| 加速倍數 | `speedup(慢, 快)` | `app_dma.c:126`、`app_dma_pio.c:87` |
| 電腦 ↔ Pico 傳輸 | 電腦端 `ros2/bench.py`（第 2 章） | — |
| 某行 C 變成幾條指令 | 看 `build/app_xxx.dis` | 3.2.5 |

**實測數字（都在電腦上，不是板子）**

| 項目 | 數字 | 環境 |
|---|---|---|
| ARM 全新 build（5 個 app） | `real 0m20.010s` | x86_64、4 核、`make -j4`、SDK 2.2.0、picotool 已預先編好 |
| ARM `.text` 大小 | app_serial 27164、app_multicore 38796、app_dma 36152、app_dma_pio 36384、app_pio 35440 bytes | `arm-none-eabi-size` |
| RISC-V `.text` 大小 | app_serial 27204、app_multicore 43932、app_dma 43880、app_dma_pio 43860、app_pio 43308 bytes | `riscv64-unknown-elf-size`（替代工具鏈 + picolibc） |
| CRC32 查表 vs 逐 bit | 查表 65.5～71.0 ms、逐 bit 290.8～302.6 ms，3 次各 4.4×、4.6×、4.1× | Intel Xeon 2.30GHz、host gcc 13.3.0 `-O2`、16384 bytes × 2000 次；用 `serial_proto.c` 的 `crc32_update` 和 `app_dma.c` 的 `cpu_crc32` 原樣 |

- `serial_proto.c:10` 註解寫「比一次算 1 bit 快約 8 倍」，在電腦上實測只有 4.1～4.6 倍；Pico 上的倍數沒有實測。

**沒有實測（要上板才知道）**：DMA vs CPU copy 的時間、sniffer CRC 的速度、DMA+PIO vs CPU put/get、race 三種模式的時間、pipeline 時間、USB 實際吞吐量。

**計算值（不是實測）**

- shift_out 位元速率 = 150 MHz / 10 / 4 = 3.75 Mbit/s（`shift_out.pio:6`，假設 clk_sys = 150 MHz）。
- echo 每字最少 3 個 SM cycle（3 條指令），150 MHz 下理論上限 50 M 字/秒；實際受 FIFO、CPU 或 DMA 餵資料的速度限制。
- USB Full Speed 規格 12 Mbit/s（`README.md:87`），實際有協定開銷。

## 3.6 限制、已知問題、沒驗證的地方

### 3.6.1 審查已知問題（已逐條核對）

| # | 問題 | 核對結果 | 影響 / 怎麼處理 |
|---|---|---|---|
| 2 | `README.md:143` 原本說電腦端 `serial_bridge.py` 的 `on_bytes()`「沒有切包…未改」 | **確認過時，2026-11-12 已更新 README**。現在 `ros2/serial_bridge.py:78` 會拒絕 `len(msg.data) > CHUNK_BYTES`（`frame.py:19`，4096）並印錯誤。 | 電腦端上限 4096 比 Pico 的 8192 嚴。題目 CRC 資料 4097～8192 bytes 時 Pico 收得了，但電腦端先擋掉。要放寬就把 `CHUNK_BYTES` 改成 8192（≤ `FRAME_MAX_PAYLOAD`） |
| 6 | `app_pio.c` 的 `test_loopback` / `load()`：狀態機和程式沒釋放；第二次 load 失敗時第一個一直占著 | **確認**。`app_pio.c:62-63`：`bitstream_in` 載入成功、`shift_out` 失敗時直接 return，`sm_rx` 和 `off_rx` 沒有 remove；成功跑完（`:80`）也沒有 `pio_sm_set_enabled(false)` / `pio_remove_program_and_unclaim_sm` | 目前 `main` 只呼叫一次，不影響輸出；但把 `test_loopback` 拿去重複呼叫或在同一個 pio1 再載別的程式，會遇到指令空間 / SM 不夠。修法：失敗分支與結尾都對已載入的那個呼叫 `pio_remove_program_and_unclaim_sm(&prog, pio, sm, off)` |
| 9 | DMA sniffer 的 zlib CRC32 等價（CRC32R + OUT_REV + 軟體 XOR）只從暫存器文件推得 | **確認仍未上板**。暫存器說明（`regs/dma.h` SNIFF_CTRL、SNIFF_DATA）與 SDK 函式（`dma.h:965-1055`）都核對過；Python 模型 200/200 組等於 zlib（3.3.8）；但模型是依文件寫的，不能取代硬體 | 考場先跑 `app_dma`，看 `PASS`；FAIL 照 3.3.8 的對照表改；正式答案保留軟體 CRC 當備案 |
| 10 | pico-sdk 版本差異 | `dma_encode_transfer_count`：SDK 2.2.0 有（`dma.h:531`），2.1.1 沒有 → `app_dma.c:21-24`、`app_dma_pio.c:27-29` 的補丁在 2.1.1 實際編譯通過。RISC-V：SDK 2.2.0 的 `pico_riscv_gcc.cmake` 固定 `-march=rv32imac_zicsr_zifencei_zba_zbb_zbs_zbkb -mabi=ilp32`、**沒有** `-mstrict-align`；2.3.x 的 `pico_riscv_gcc.cmake` 會依序試 `-mcpu=hazard3-rp2350`、含 `zcb_zcmp` 的 `-march`、最後才退回同一組，；`-mstrict-align` 是 2.3.1 才預設加（2.3.0 還沒有，已對照兩版原始碼；可用 `PICO_NO_STRICT_ALIGN` 關） | 補丁版本在 2.0/2.1 直接回傳 n、不遮 MODE bits，所以 count 必須自己保證 < 2^28（`dma_xfer` 有檢查）。RISC-V 在 SDK 2.2.0 沒有 `-mstrict-align`：Hazard3 遇到不對齊存取的行為 ⚠️未驗證；考場用 ARM 最穩 |

### 3.6.2 本章作者另外發現的

| 檔案:行號 | 問題 | 嚴重度 | 建議 |
|---|---|---|---|
| `serial_proto.c:26` | CRC 表在第一次呼叫時才建，沒有鎖；兩核第一次同時呼叫會同時寫表（寫入值相同） | 低（目前只有 core0 用） | 雙核心版本在 launch core1 前先呼叫一次 `crc32_update(0, NULL, 0)` |
| `app_dma_pio.c:52-54` | `ch_tx` 要到、`ch_rx` 失敗時直接停住，沒有 unclaim `ch_tx` | 低（程式本來就停住） | 改寫成可恢復時要先 unclaim |
| `app_multicore.c:109` | `%-18s` 以 byte 對齊，中文那行對不齊 | 外觀 | 不用改 |
| `serial_proto.c:10` | 註解「快約 8 倍」，電腦上實測 4.1～4.6 倍 | 註解不準 | 以實測為準（3.5） |
| RISC-V 工具鏈 | `README.md:26` 說 Ubuntu 的 riscv64 工具鏈連結會失敗：實測確認（`nosys.specs`）；另外 SDK 2.2.0 預設只找 `riscv32-*` 名稱 | 環境 | 用 ARM；或用 SDK 官方 riscv32 工具鏈 |

### 3.6.3 沒驗證的地方（考場先確認）

- 所有 app 都沒在板子上跑過：開機訊息、PASS/FAIL、時間都只是依程式碼推算。
- `picotool load -x -f` 沒有實測（容器裡的 picotool 沒有 USB 支援）。
- sniffer CRC32 是否真的等於 zlib（已知問題 9）。
- PIO 停在 `out`（autopull 等資料）時 side-set 是否維持 CLK=0（`README.md:166`）。
- DMA 8-bit 寫入 PIO FIFO 的 byte lane 行為（3.4.5 d）。
- race 示範的「不鎖」一定會少加（時序決定）。
- `__dmb()` 在 M33 上是否必要（`README.md:167`，加了只是保險）。
- RISC-V 映像（替代工具鏈 + picolibc）能不能正常開機。

## 3.7 一頁速查表

**指令**

| 要做什麼 | 指令（在 `預製程式碼/pico/`） |
|---|---|
| ARM build | `export PICO_SDK_PATH=...; mkdir -p build && cd build && cmake -DPICO_BOARD=pico2 .. && make -j4` |
| RISC-V build | `mkdir -p build-rv && cd build-rv && cmake -DPICO_BOARD=pico2 -DPICO_PLATFORM=rp2350-riscv .. && make -j4` |
| 只編一個 | `make -j4 app_serial` |
| 沒網路找不到 picotool | `cmake ... -Dpicotool_DIR=<含 picotoolConfig.cmake 的資料夾>` |
| 燒錄 | BOOTSEL 按住插 USB → 複製 `.uf2` 到 `RP2350`；或 `picotool load -x app.uf2 -f` |
| 看是哪種架構 | `picotool info app.uf2`（`ARM Secure` / `RISC-V`） |
| 看輸出 | `ls /dev/ttyACM*`；`screen /dev/ttyACM0 115200`；`python3 -m serial.tools.miniterm /dev/ttyACM0 115200` |
| 看程式大小 | `arm-none-eabi-size app_*.elf` |
| 看反組譯 | `grep -n "<add_many>:" app_multicore.dis` |

**常數**

| 名稱 | 值 | 位置 |
|---|---|---|
| `FRAME_MAX_PAYLOAD` | 8192 | `serial_proto.h:23` |
| `CMD_ECHO / SUM_U32 / CRC32` | 0x01 / 0x02 / 0x03 | `serial_proto.h:18-20` |
| `CHUNK_BYTES`（電腦端） | 4096 | `ros2/frame.py:19` |
| DMA 通道 / PIO 區塊 / SM / 指令 | 16 / 3 / 4 / 32 | `platform_defs.h` |
| 核心間 FIFO 深度 | 4 | `multicore.h:128` |
| core1 stack | 2 KB | `multicore.h:32-37` |
| TRANS_COUNT 次數上限 | 2^28 − 1 | `regs/dma.h:99` |
| zlib CRC32("123456789") | `0xCBF43926` | — |
| sniffer FAIL 值 | `0x649C2FD3`（少反轉）/ `0x340BC6D9`（多 XOR） | `app_dma.c:63-64` |
| `N_ADD` / `N_WORDS` / `N` | 200000 / 4096 / 4096 | `app_multicore.c:21` / `app_dma.c:27` / `app_dma_pio.c:34` |
| `DATA_PIN` / `CLK_PIN` | 2 / 3 | `app_pio.c:21-22` |

**函式簽名**

```c
// serial_proto.h
uint32_t crc32_update(uint32_t crc, const uint8_t *p, size_t n);
int  proto_feed(uint8_t byte, frame_t *f);   // 1 完整 / 0 未完 / -1 壞
void proto_reset(void);  int proto_busy(void);
void proto_send(uint8_t cmd, uint8_t seq, const uint8_t *payload, uint16_t len);
// DMA 5 步
int ch = dma_claim_unused_channel(false);                       // -1 = 沒有
dma_channel_config c = dma_channel_get_default_config(ch);      // 讀遞增、寫不遞增、32-bit、DREQ_FORCE
channel_config_set_transfer_data_size(&c, DMA_SIZE_32);
channel_config_set_read_increment(&c, true);
channel_config_set_write_increment(&c, true);                   // copy 一定要開
channel_config_set_dreq(&c, pio_get_dreq(pio, sm, true));       // 只有配周邊時
dma_channel_configure(ch, &c, dst, src, dma_encode_transfer_count(n), true);   // n = 次數
dma_channel_wait_for_finish_blocking(ch);
dma_channel_unclaim(ch);
// sniffer zlib CRC32（8-bit 傳輸）
dma_sniffer_set_data_accumulator(0xFFFFFFFF);
dma_sniffer_set_output_reverse_enabled(true);
dma_sniffer_enable(ch, DMA_SNIFF_CTRL_CALC_VALUE_CRC32R, false);
channel_config_set_sniff_enable(&c, true);          // 然後 configure(..., true)、wait
uint32_t crc = dma_sniffer_get_data_accumulator() ^ 0xFFFFFFFF;  dma_sniffer_disable();
// 鎖
spin_lock_t *l = spin_lock_init(spin_lock_claim_unused(true));
uint32_t s = spin_lock_blocking(l); /* 短短幾行 */ spin_unlock(l, s);
critical_section_init(&cs); critical_section_enter_blocking(&cs); critical_section_exit(&cs);
queue_init(&q, sizeof(T), 8); queue_add_blocking(&q, &x); queue_remove_blocking(&q, &x); queue_try_remove(&q, &x);
// PIO
int off = pio_add_program(pio, &prog);  int sm = pio_claim_unused_sm(pio, false);
sm_config_set_out_shift(&c, shift_right, autopull, threshold);   // 左移 = 從 bit31 拿
sm_config_set_in_shift(&c, shift_right, autopush, threshold);    // 左移 = 新 bit 進 bit0
pio_remove_program_and_unclaim_sm(&prog, pio, sm, off);
```

**常見錯誤**

| 症狀 | 第一個要查的 |
|---|---|
| cmake：SDK location was not specified | `PICO_SDK_PATH` |
| 沒有 `/dev/ttyACM0` | 重燒已知會動的 app；Docker `--privileged` |
| 電腦端 transact 逾時 | cmd 數字兩邊一致？len ≤ 8192？port 對？ |
| 二進位資料多了 `0d` | CRLF 轉換沒關 |
| DMA copy 只有第一格對 | `write_increment` |
| DMA 不結束 | count ≥ 2^28；DMA+PIO 只開了一個通道 |
| sniffer FAIL | 看值是 `649c2fd3` 還是 `340bc6d9` |
| race 修好但很慢 | 臨界區太長 → 區域變數累積、最後鎖一次 |
| core1 當掉 | core1 stack 2 KB，大陣列改 static |
| PIO 收到的值順序錯 | 兩端移位方向、門檻、put 時要不要 `<< 24` |
