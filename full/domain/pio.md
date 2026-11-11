# RP2350 PIO（Programmable I/O）與 pico-sdk 參考

- 用途：成大資工特殊選才上機考（2026-11-14）備考參考。可直接貼給考場 LLM 當 context，或自己查閱。內容涵蓋 RP2350 PIO 硬體架構、9 條指令、`.pio` 組譯語法、pico-sdk `hardware_pio` API、時序計算、DMA 餵資料、效能優化、常見錯誤與除錯。
- 適用版本：RP2350（Raspberry Pi Pico 2 = RP2350A，30 個 GPIO）、PIO version 1；pico-sdk 2.x（API 簽名依 2026-11 的 `master` 分支核對，最新 release 為 2.3.1）。凡 RP2040（PIO version 0）不同之處皆有標示。
- 來源（實際查閱）：
  - RP2350 Datasheet 第 11 章 PIO：https://datasheets.raspberrypi.com/rp2350/rp2350-datasheet.pdf
  - pico-sdk `hardware_pio`：https://github.com/raspberrypi/pico-sdk/blob/master/src/rp2_common/hardware_pio/include/hardware/pio.h 、`pio_instructions.h`、`pio.c`
  - pico-sdk 平台定義：`src/rp2350/hardware_regs/include/hardware/platform_defs.h`、`regs/dreq.h`、`regs/intctrl.h`、`src/rp2350/hardware_structs/include/hardware/structs/pio.h`、`src/boards/include/boards/pico2.h`
  - pico-sdk 工具：`tools/pioasm/c_sdk_output.cpp`、`tools/pioasm/main.cpp`、`tools/CMakeLists.txt`（`pico_generate_pio_header`）
  - pico-sdk `hardware_dma/include/hardware/dma.h`、`hardware_irq/irq.h`、`hardware_clocks/clocks.h`
  - pico-examples：https://github.com/raspberrypi/pico-examples/tree/master/pio （`pio_blink`、`uart_tx`、`ws2812`、`pwm`、`squarewave`、`addition`）
  - 考前 demo 包 `section2-2/demo_pio.pio`
- 最後更新：2026-11

> 標記說明：⚠️未驗證 = 沒有在官方原始碼或 datasheet 中直接確認的內容，使用前請自行核對。

---

## 0. 一分鐘總覽（給 LLM 的摘要）

- RP2350 有 **3 個 PIO block**（`pio0`、`pio1`、`pio2`），每個 block 有 **4 個 state machine（SM）**，共 12 個 SM。RP2040 只有 2 個 block（8 個 SM）。
- 每個 block 有 **32 格共用指令記憶體**（每格 16-bit 指令），同一 block 的 4 個 SM 共用；CPU 對它只能寫不能讀。
- 每個 SM 有：`X`、`Y`（32-bit scratch）、`OSR`（output shift register）、`ISR`（input shift register）、兩個 shift counter（0–32）、`PC`（5-bit）、clock divider（16.8 定點，範圍 1–65536）、TX FIFO 與 RX FIFO（各 4 × 32-bit，可 join 成單向 8 深）。
- 資料流：`CPU/DMA → TX FIFO → (pull/autopull) → OSR → (out) → pins/X/Y/...`，以及 `pins/X/Y/... → (in) → ISR → (push/autopush) → RX FIFO → CPU/DMA`。
- 每條指令固定 **1 個 SM cycle**（除非 stall），可加 `[n]` delay，可帶 side-set。delay 與 side-set **共用 5-bit 欄位**。
- 9 條指令：`JMP WAIT IN OUT PUSH PULL MOV IRQ SET`。`nop` 是 `mov y, y` 的別名。
- `.wrap_target` / `.wrap` 是**零成本**的無條件跳回，省一條 `jmp` 和一個 cycle。
- 預設 sysclk：pico-sdk 對 RP2350 預設 `SYS_CLK_HZ = 150000000`（150 MHz，也是 datasheet 標稱最高系統時脈）。`clock_get_hz(clk_sys)` 取實際值。
- 標準初始化：`pio_add_program`（或 `pio_claim_free_sm_and_add_program`）→ `<prog>_program_get_default_config(offset)` → 設 pins / shift / clkdiv / fifo join → `pio_gpio_init` 每個輸出腳 → `pio_sm_set_consecutive_pindirs` → `pio_sm_init` → `pio_sm_set_enabled(true)`。

---

## 1. 硬體架構

### 1.1 Block 與 SM

| 項目 | RP2350 | RP2040 |
|---|---|---|
| PIO block 數 | 3（`NUM_PIOS = 3`） | 2 |
| 每 block SM 數 | 4（`NUM_PIO_STATE_MACHINES = 4`） | 4 |
| 每 block 指令記憶體 | 32 格（`PIO_INSTRUCTION_COUNT = 32`），4 個 SM 共用、1 寫 4 讀，不會互相 stall | 同 |
| 每 block 系統 IRQ 線 | 2 條（`NUM_PIO_IRQS = 2`）：`PIOx_IRQ_0`、`PIOx_IRQ_1` | 同 |
| block 內 IRQ flag | 8 個（0–7），全部 SM 都看得到 | 8 個 |
| 可送到系統中斷的 IRQ flag | 0–7 全部 | 只有 0–3 |
| 基底位址 | `0x50200000`、`0x50300000`、`0x50400000` | — |
| PIO version | 1（`DBG_CFGINFO.VERSION` 讀到 1） | 0 |

系統中斷編號（RP2350）：`PIO0_IRQ_0=15, PIO0_IRQ_1=16, PIO1_IRQ_0=17, PIO1_IRQ_1=18, PIO2_IRQ_0=19, PIO2_IRQ_1=20`。程式中請用 `pio_get_irq_num(pio, 0/1)`，不要寫死。

DREQ 編號（RP2350）：`DREQ_PIO0_TX0..3 = 0..3`、`DREQ_PIO0_RX0..3 = 4..7`、PIO1 為 8–15、PIO2 為 16–23。程式中用 `pio_get_dreq(pio, sm, is_tx)`。

### 1.2 每個 SM 的暫存器

| 暫存器 | 寬度 | 用途與重點 |
|---|---|---|
| `X`, `Y` | 32 | scratch。可當迴圈計數器（`jmp x--`）、條件判斷（`jmp !x`、`jmp x!=y`）、暫存。`set x, n` 只能設 0–31（高位清 0）。 |
| `OSR` | 32 | 從 TX FIFO 拿到的資料放這裡；`out` 每次移出 1–32 bit；移出後補 0。 |
| `ISR` | 32 | `in` 每次移入 1–32 bit；`push` 後清 0。 |
| output shift counter | 0–32 飽和 | 已從 OSR 移出多少 bit。reset 時為 32（代表 OSR 空）。 |
| input shift counter | 0–32 飽和 | 已移入 ISR 多少 bit。reset 時為 0。 |
| `PC` | 5 | 目前執行位址（絕對位址 0–31）。`pio_sm_get_pc()` 可讀。 |
| clock divider | 16.8 | `INT`（16-bit）+ `FRAC`（8-bit，1/256）。`INT=0` 代表 65536。 |

Shift counter 會被這些操作改變（datasheet 11.2.4.2 / 11.5.4）：

- `out` 加上 bit count；`in` 加上 bit count（皆飽和在 32）。
- 成功的 `pull` 或 autopull → output counter 清 0；成功的 `push` 或 autopush → input counter 清 0。
- `mov osr, ...` → output counter 清 0（視為「滿」）；`mov isr, ...` → input counter 清 0（視為「空」）。
- `out isr, n` → input counter 設為 n。
- `pio_sm_restart()` / `pio_sm_init()` → input counter = 0，output counter = 32。

### 1.3 FIFO

- 預設每個 SM：TX 4 格、RX 4 格（每格 32-bit）。
- FIFO join（`sm_config_set_fifo_join` / `.fifo`）：

| enum（`enum pio_fifo_join`） | `.fifo` 值 | 效果 | 版本 |
|---|---|---|---|
| `PIO_FIFO_JOIN_NONE = 0` | `txrx`（預設） | TX 4 + RX 4 | v0/v1 |
| `PIO_FIFO_JOIN_TX = 1` | `tx` | TX 8，RX 停用（`push` 會永遠 stall） | v0/v1 |
| `PIO_FIFO_JOIN_RX = 2` | `rx` | RX 8，TX 停用 | v0/v1 |
| `PIO_FIFO_JOIN_TXGET = 4` | `txget` | TX 4；RX 的 4 格變成「SM 用 `mov osr, rxfifo[i]` 隨機讀、CPU 隨機寫」→ 當**控制暫存器** | 僅 v1（RP2350） |
| `PIO_FIFO_JOIN_TXPUT = 8` | `txput` | TX 4；RX 的 4 格變成「SM 用 `mov rxfifo[i], isr` 隨機寫、CPU 隨機讀」→ 當**狀態暫存器** | 僅 v1 |
| `PIO_FIFO_JOIN_PUTGET = 12` | `putget` | RX 4 格給 SM 隨機讀寫，CPU 不能存取 → 額外 scratch | 僅 v1 |

- CPU 端存取那 4 格：`pio->rxf_putget[sm][i]`（對應暫存器 `RXFsm_PUTGETi`）。
- 改變 FIFO join 會**清空 FIFO**（datasheet caution）。
- 用了 PUT/GET 模式時：`push` 行為未定義、不可開 autopush。
- 8 格 FIFO 足以讓系統 DMA 達到每 clock 1 word（若 DMA 沒有和其他 master 搶匯流排）。

### 1.4 Stall（暫停）的時機

PC 不前進、下一個 cycle 重試，delay 要等 stall 結束才開始算：

- `wait` 條件尚未成立
- blocking `pull` 遇 TX FIFO 空；blocking `push` 遇 RX FIFO 滿
- `irq wait` 設了 flag，等待被清除
- autopull 開啟且 OSR 已到門檻、TX FIFO 空時執行 `out`
- autopush 開啟、`in` 讓 ISR 到門檻、RX FIFO 滿

**side-set 不受 stall 影響**：在指令第一個 cycle 就生效（UART TX 利用這點在 stall 時保持 idle high）。

### 1.5 腳位對應（pin mapping）

每個 SM 有 5 組對應（datasheet 原文說 OUT / SET / IN / side-set 四組連續範圍，加上 JMP pin）：

| 群組 | 使用者 | 設定 API | 寬度 |
|---|---|---|---|
| OUT | `out pins/pindirs`、`mov pins`、`mov pindirs`（v1） | `sm_config_set_out_pins(&c, base, count)` | 0–32 |
| SET | `set pins/pindirs` | `sm_config_set_set_pins(&c, base, count)` | 0–5 |
| IN | `in pins`、`wait pin`、`mov x, pins` | `sm_config_set_in_pins(&c, base)`；RP2350 另有 `sm_config_set_in_pin_count(&c, n)` | 讀 32 bit（右旋，LSB = IN_BASE） |
| side-set | 指令的 `side` 欄位 | `sm_config_set_sideset_pins(&c, base)` + `sm_config_set_sideset(&c, bits, opt, pindirs)`（pioasm 產生的 default config 會幫你呼叫後者） | 0–5（含 opt bit） |
| JMP pin | `jmp pin`、`wait jmppin`（v1） | `sm_config_set_jmp_pin(&c, pin)` | 1 腳 |

規則：

- 各群組可重疊（例：UART TX 把 OUT 與 side-set 都映射到同一腳）。
- 同一 SM 在同一 cycle 的 OUT/SET 與 side-set 寫到同一腳 → **side-set 優先**。
- 多個 SM 寫同一腳 → **編號最大的 SM 優先**（level 與 direction 分開判斷）。
- 沒人寫的腳維持原值。
- 範圍超過 31 會 wrap 回 0（模 32）。
- `wait gpio n` 用**絕對** GPIO 編號；`wait pin n` 用 IN_BASE + n。
- 輸入有 2 級同步器（2 cycle 延遲），可用 `pio_set_input_sync_bypass_with_mask()` 關閉（只建議同步介面，否則有亞穩態風險）。
- RP2350A（Pico 2）只有 30 個 GPIO；RP2350B 有 48 個，每個 PIO 一次只能看 32 個，用 `GPIOBASE`（0 或 16）選範圍，SDK 用 `pio_set_gpio_base()`、`pio_claim_free_sm_and_add_program_for_gpio_range()` 處理。Pico 2 不需要管 GPIOBASE。
- Pico 2 板：`PICO_DEFAULT_LED_PIN = 25`，預設 UART0 TX/RX = GPIO 0/1（`boards/pico2.h`）。

### 1.6 RP2350 相對 RP2040 的新功能（全部經 datasheet 11.1.1 確認）

| 新功能 | 說明 |
|---|---|
| 3 個 PIO block | 8 → 12 個 SM |
| `GPIOBASE` | 讓 PIO 存取 >32 GPIO（RP2350B），仍是一次 32 個 |
| `CTRL.NEXT_PIO_MASK / PREV_PIO_MASK`、`NEXTPREV_SM_ENABLE/DISABLE`、`NEXTPREV_CLKDIV_RESTART` | 一次同步啟停 / 同步 clock divider 跨多個 PIO block（SDK：`pio_set_sm_multi_mask_enabled`、`pio_enable_sm_multi_mask_in_sync`、`pio_clkdiv_restart_sm_multi_mask`） |
| `SHIFTCTRL.IN_COUNT` | 把 IN 映射中不需要的腳遮成 0（主要給 `mov x, pins` 用） |
| IRQ0_INTE / IRQ1_INTE 可送出全部 8 個 SM IRQ flag | RP2040 只有 0–3 |
| RX FIFO 隨機存取（PUT/GET） | `mov rxfifo[y|i], isr`、`mov osr, rxfifo[y|i]`，CPU 端 `rxf_putget[sm][i]` |
| `wait jmppin (+ 0..3)` | WAIT 的新 source：JMP_PIN + 偏移 0–3 |
| `mov pindirs, src` | 一條指令改所有 OUT 腳方向（例 `mov pindirs, ~null` 全輸出、`mov pindirs, null` 全輸入） |
| `mov x, status` 可選 IRQ flag | `STATUS_SEL = IRQ`（`.mov_status irq (prev|next) set n`） |
| `irq` / `wait irq` 的 `prev` / `next` | 設定、清除、等待**相鄰 PIO block** 的 IRQ flag；跨 block 無額外延遲，下一 cycle 即可見 |
| DREQ 延遲少 1 cycle、GPIO 延遲與 skew 改善 | — |

---

## 2. 指令集

### 2.1 編碼總表（16-bit）

```
bit:   15 14 13 | 12 ........ 8 | 7 ................................. 0
JMP     0  0  0 | delay/sideset | cond(3)      | address(5)
WAIT    0  0  1 | delay/sideset | pol | src(2) | index(5)
IN      0  1  0 | delay/sideset | src(3)       | bitcount(5, 0=32)
OUT     0  1  1 | delay/sideset | dest(3)      | bitcount(5, 0=32)
PUSH    1  0  0 | delay/sideset | 0 IfF Blk 0 0 0 0 0
PULL    1  0  0 | delay/sideset | 1 IfE Blk 0 0 0 0 0
MOV→RX  1  0  0 | delay/sideset | 0 0 0 1 IdxI 0 index(2)     (v1 only)
MOV←RX  1  0  0 | delay/sideset | 1 0 0 1 IdxI 0 index(2)     (v1 only)
MOV     1  0  1 | delay/sideset | dest(3) | op(2) | src(3)
IRQ     1  1  0 | delay/sideset | 0 Clr Wait | idxmode(2) | index(3)
SET     1  1  1 | delay/sideset | dest(3)      | data(5)
```

範例編碼（可用來核對 pioasm 輸出）：`set pindirs, 1` = `0xe081`；`set pins, 1 [1]` = `0xe101`；`out x, 32` = `0x6020`；`in x, 32` = `0x4020`；`push`（block）= `0x8020`；`pull`（block）= `0x80a0`。

### 2.2 九條指令參考

| 指令 | 語法 | 功能與重點 |
|---|---|---|
| **JMP** | `jmp (cond) target` | cond：（無）永遠、`!x`（X==0）、`x--`（X≠0 則跳，**先判斷再遞減**，遞減一定發生）、`!y`、`y--`、`x!=y`、`pin`（JMP_PIN 為高則跳）、`!osre`（OSR 尚未移到 pull 門檻）。位址是**絕對位址**，SDK 載入時自動加 offset；自己用 `pio_encode_jmp()` 時要自己加 offset。delay 不論是否跳轉都生效。 |
| **WAIT** | `wait pol gpio n`／`wait pol pin n`／`wait pol irq (prev\|next) n (rel)`／`wait pol jmppin (+ off)` | 停住直到條件成立。`gpio`=絕對 GPIO；`pin`=IN_BASE+n；`irq`：pol=1 時條件成立後**自動清除**該 flag；`jmppin`（v1）=JMP_PIN+0..3。datasheet 提醒：不要對已送去系統中斷的 IRQ flag 用 `wait 1 irq`（與 ISR 有 race）。 |
| **IN** | `in src, n`（n=1–32） | 從 src 移 n bit 進 ISR。src：`pins`、`x`、`y`、`null`（補 0）、`isr`、`osr`。永遠取 src 的**最低 n bit**；ISR 依 `IN_SHIFTDIR` 左移或右移騰出空間。autopush 開啟時到門檻即自動 push（RX 滿則 stall）。 |
| **OUT** | `out dest, n`（n=1–32） | 從 OSR 移出 n bit 寫到 dest。dest：`pins`、`x`、`y`、`null`（丟棄）、`pindirs`、`pc`（無條件跳）、`isr`（並設 ISR counter=n）、`exec`（把資料當指令下個 cycle 執行）。右移取 OSR 低位、左移取高位。寫入值高位補 0。 |
| **PUSH** | `push (iffull) (block\|noblock)` | ISR → RX FIFO，ISR 清 0。預設 `block`。`iffull`：shift counter 未達 push 門檻就不做事。`noblock` 遇 RX 滿：不 stall，資料丟掉，ISR 仍清 0，設 `FDEBUG.RXSTALL`。 |
| **PULL** | `pull (ifempty) (block\|noblock)` | TX FIFO → OSR。預設 `block`。`ifempty`：shift counter 未達 pull 門檻就不做事。`noblock` 遇 TX 空：效果等於 `mov osr, x`（PWM 範例用這招重用上一個值）。autopull 開啟時，OSR 滿的 `pull` 是 no-op（當 fence）。 |
| **MOV** | `mov dest, (op) src` | op：無、`!` 或 `~`（位元反相）、`::`（位元反轉 bit n ↔ bit 31−n）。dest：`pins`、`x`、`y`、`pindirs`（v1）、`exec`、`pc`、`isr`（counter=0）、`osr`（counter=0）。src：`pins`（IN 映射，受 IN_COUNT 遮罩）、`x`、`y`、`null`、`status`、`isr`、`osr`。v1 另有 `mov rxfifo[y\|0-3], isr`、`mov osr, rxfifo[y\|0-3]`。 |
| **IRQ** | `irq (prev\|next) (set\|nowait\|wait\|clear) n (rel)` | 設定或清除 IRQ flag 0–7。`wait`：設了之後等它被清除才繼續。`clear` 時 Wait bit 無效。`rel`：flag 低 2 bit 加上 SM 編號（模 4，bit 2 不受影響），讓同一程式跑在多個 SM 時各用各的 flag。同一 cycle 同時 set 與 clear → set 勝。`prev`/`next` 為 v1，且**不能與 `rel` 並用**（共用 2-bit idxmode；`wait irq` 同理，pioasm 會報錯）。 |
| **SET** | `set dest, value`（0–31） | 立即值寫入 dest：`pins`、`x`、`y`、`pindirs`。寫 X/Y 時高 27 bit 清 0。寫 pins 用 SET 映射（最多 5 腳）。 |
| `nop` | `nop` | 偽指令 = `mov y, y`。常用來只做 side-set 或 delay。 |

### 2.3 `mov x, status` 的 STATUS 來源

`sm_config_set_mov_status(&c, sel, n)` 或 `.mov_status`：

| sel | `.mov_status` 語法 | STATUS 值 |
|---|---|---|
| `STATUS_TX_LESSTHAN` | `.mov_status txfifo < n` | TX FIFO 數量 < n 時全 1，否則全 0 |
| `STATUS_RX_LESSTHAN` | `.mov_status rxfifo < n` | RX FIFO 數量 < n 時全 1 |
| `STATUS_IRQ_SET`（v1） | `.mov_status irq (prev\|next) set n` | 指定 IRQ flag 為 1 時全 1 |

### 2.4 Delay 與 side-set 共用 5 bit

指令的 bit 12–8：高位給 side-set（含 opt 的 enable bit），剩下低位給 delay。

| `.side_set` 宣告 | 佔用 bit 數（含 opt） | 最大 delay `[n]` |
|---|---|---|
| 無 | 0 | 31 |
| `.side_set 1` | 1 | 15 |
| `.side_set 1 opt` | 2 | 7 |
| `.side_set 2` | 2 | 7 |
| `.side_set 2 opt` | 3 | 3 |
| `.side_set 3` | 3 | 3 |
| `.side_set 4` | 4 | 1 |
| `.side_set 5` 或 `.side_set 4 opt` | 5 | 0（不能 delay） |

- 非 opt：**每一條指令都必須寫 `side x`**，否則組譯錯誤。
- opt：可省略 `side`，代價是多吃 1 bit（opt 時 side-set 資料最多 4 bit）。
- `pindirs` 參數：side-set 改的是方向不是電位（例：open-drain 式 I2C）。
- SDK `sm_config_set_sideset(&c, bit_count, optional, pindirs)` 的 `bit_count` **包含 opt bit**；pioasm 產生的 `_get_default_config` 已幫你呼叫（例 `.side_set 1 opt` 產生 `sm_config_set_sideset(&c, 2, true, false)`）。你只需自己設 `sm_config_set_sideset_pins(&c, base)`。

### 2.5 PC 更新規則與 wrap

每條指令（從指令記憶體執行）之後：

1. 若是 `jmp` 且條件成立 → PC = 目標。
2. 否則若 PC == `WRAP_TOP`（`.wrap` 位置）→ PC = `WRAP_BOTTOM`（`.wrap_target` 位置）。
3. 否則 PC + 1（31 之後回 0）。

`.wrap` 是**零 cycle、零指令**的跳回。`pio_get_default_sm_config()` 預設 wrap = 0..31，所以**務必用 `<prog>_program_get_default_config(offset)`**，它會呼叫 `sm_config_set_wrap(&c, offset + wrap_target, offset + wrap)`。沒寫 `.wrap_target` 預設為程式開頭；沒寫 `.wrap` 預設為最後一條。

### 2.6 從其他來源執行的指令

- `pio_sm_exec(pio, sm, instr)`：寫入 `SMx_INSTR`，立即執行，**忽略 delay 與 clock divider**，PC 不前進（除非指令本身改 PC）。SM 停用時也可執行（PWM 範例就是先停用 SM 再 exec 設定 ISR）。
- 若 exec 的指令 stall（例如 TX 空時 `pull block`），會被鎖存，`EXECCTRL.EXEC_STALLED`=1（`pio_sm_is_exec_stalled()`）。寫一個 `nop` 或 restart 可清除。用 `pio_sm_exec_wait_blocking()` 會等到完成。
- `out exec, n` / `mov exec, src`：該指令本身 1 cycle，被執行的指令在下個 cycle；本身的 delay 被忽略。

---

## 3. `.pio` 組譯語法（pioasm）

### 3.1 指令通用格式

```
<instruction> (side <value>) ([<delay>])
```

- 大小寫不敏感；逗號可省略（`out pins, 3` = `out pins 3`）。
- 註解：`;`、`//`、`/* ... */`。
- 數值：十進位、`0x..`、`0b..`、`.define` 的符號、label、`(expression)`（支援 `+ - * / << >>`、負號、`::` 位元反轉，**必須加括號**）。

### 3.2 Directives

| Directive | 說明 |
|---|---|
| `.program <name>` | 開始一個程式。產生 `<name>_program`（`pio_program_t`）、`<name>_program_instructions[]`、`<name>_wrap_target`、`<name>_wrap`、`<name>_pio_version`、`<name>_program_get_default_config(uint offset)`。 |
| `.pio_version <0\|1\|RP2040\|RP2350>` | 目標 PIO 版本。放在第一個 `.program` 前為全域預設。用了 v1 功能（`mov pindirs`、`rxfifo[]`、`prev/next`、`jmppin`、`.fifo txput` 等）時：用 SDK 的 `pico_generate_pio_header` 建置 RP2350 **不需要**寫 `.pio_version 1`——它會傳 `-v ${PICO_PIO_VERSION}`（RP2350 建置時 `src/rp2350-*.cmake` 設為 1，RP2040 為 0/未設時傳 0）。只有**手動單獨執行 pioasm**（預設 0）時才要加 `.pio_version 1` 或 `-v 1`。寫了也無害，但組譯失敗時真正原因通常是 build 成了 RP2040。 |
| `.side_set <n> (opt) (pindirs)` | 見 2.4。 |
| `.wrap_target` / `.wrap` | 見 2.5，各只能用一次。 |
| `.origin <offset>` | 程式必須載入在指定位址（例如用 `out pc` 做資料驅動跳轉時）。 |
| `.define (PUBLIC) <sym> <value>` | 定義常數；PUBLIC 會輸出 `#define <prog>_<sym> value`（在 `.program` 前定義則為全域 `#define <sym> value`）。 |
| `PUBLIC <label>:` | 輸出 `#define <prog>_offset_<label> <n>u`（相對程式起點）。 |
| `.in <count> (left\|right) (auto) (<threshold>)` | 預設 IN 設定（產生 `sm_config_set_in_pin_count` + `sm_config_set_in_shift`）。v0 時 count 必須 32。 |
| `.out <count> (left\|right) (auto) (<threshold>)` | 預設 OUT 設定（產生 `sm_config_set_out_pin_count` + `sm_config_set_out_shift`）。 |
| `.set <count>` | 預設 SET 腳數（產生 `sm_config_set_set_pin_count`）。 |
| `.fifo <txrx\|tx\|rx\|txput\|txget\|putget>` | 預設 FIFO join（後三者僅 v1）。 |
| `.mov_status ...` | 見 2.3。 |
| `.clock_div <float>` | 預設 clock divider（不能用運算式或 define）。 |
| `.lang_opt <lang> <name> <option>` | 給其他語言產生器（如 python）的選項。 |
| `.word <value>` | 直接放一個 16-bit 原始指令。 |
| `% c-sdk { ... %}` | 原樣貼進產生的 `.pio.h`（放在 `#if !PICO_NO_HARDWARE` 內、`get_default_config` 之後）。通常放 `xxx_program_init()` helper。 |

### 3.3 產生的 header 長相（pioasm `c-sdk` 輸出，節錄）

```c
#define echo_wrap_target 0
#define echo_wrap 2
#define echo_pio_version 0
static __pio_const uint16_t echo_program_instructions[] = {
            //     .wrap_target
    0x6020, //  0: out    x, 32
    0x4020, //  1: in     x, 32
    0x8020, //  2: push   block
            //     .wrap
};
static __pio_const struct pio_program echo_program = {
    .instructions = echo_program_instructions,
    .length = 3,
    .origin = -1,
    .pio_version = echo_pio_version,
#if PICO_PIO_VERSION > 0
    .used_gpio_ranges = 0x0
#endif
};
static inline pio_sm_config echo_program_get_default_config(uint offset) {
    pio_sm_config c = pio_get_default_sm_config();
    sm_config_set_wrap(&c, offset + echo_wrap_target, offset + echo_wrap);
    return c;
}
```

（以 pioasm 2.3.1 實際輸出核對，略去檔頭與 `#if !PICO_NO_HARDWARE` 包裝；`__pio_const` 在 C 中就是 `const`，C++ 為 `constexpr`。）

### 3.4 CMake 與 pioasm

```cmake
add_executable(app main.c)
# 產生 ${CMAKE_CURRENT_BINARY_DIR}/echo.pio.h，並自動加入 include path
pico_generate_pio_header(app ${CMAKE_CURRENT_LIST_DIR}/echo.pio)
# 可選：OUTPUT_DIR ${CMAKE_CURRENT_LIST_DIR}  把 header 產生到原始碼目錄
target_link_libraries(app PRIVATE pico_stdlib hardware_pio hardware_dma)
pico_add_extra_outputs(app)
```

- 產生的檔名是「原檔名 + `.h`」：`demo_pio.pio` → `#include "demo_pio.pio.h"`。
- 單獨執行：`pioasm [-o c-sdk] [-v 0|1] [-p param] input.pio [output.h]`（不給 output 則輸出到 stdout）。產生的 header 註解有每條指令的反組譯，很適合核對編碼。

---

## 4. pico-sdk API（`#include "hardware/pio.h"`）

型別：`typedef pio_hw_t *PIO;`，實例 `pio0`、`pio1`、`pio2`（RP2350）。`PIO_NUM(pio)` / `pio_get_index(pio)` 取編號，`pio_get_instance(n)` 反查。

### 4.1 載入程式與取得 SM

| 函式 | 簽名 | 說明 |
|---|---|---|
| `pio_can_add_program` | `bool (PIO pio, const pio_program_t *program)` | 指令記憶體是否放得下 |
| `pio_can_add_program_at_offset` | `bool (PIO pio, const pio_program_t *program, uint offset)` | |
| `pio_add_program` | `int (PIO pio, const pio_program_t *program)` | 回傳載入 offset；失敗回負值（標頭註解寫 -1，但 2.3.1 實作在空間不足時回 `PICO_ERROR_INSUFFICIENT_RESOURCES` = -9；一律用 `< 0` 判斷） |
| `pio_add_program_at_offset` | `int (PIO pio, const pio_program_t *program, uint offset)` | |
| `pio_remove_program` | `void (PIO pio, const pio_program_t *program, uint loaded_offset)` | |
| `pio_clear_instruction_memory` | `void (PIO pio)` | |
| `pio_claim_unused_sm` | `int (PIO pio, bool required)` | required=true 時沒有空的會 panic；否則回負值 |
| `pio_sm_claim` / `pio_sm_unclaim` / `pio_sm_is_claimed` | `void (PIO, uint sm)` / `void (PIO, uint sm)` / `bool (PIO, uint sm)` | 已被 claim 再 claim 會 panic |
| `pio_claim_sm_mask` | `void (PIO pio, uint sm_mask)` | |
| `pio_claim_free_sm_and_add_program` | `bool (const pio_program_t *program, PIO *pio_out, uint *sm_out, uint *offset_out)` | 自動找有空 SM 且放得下程式的 PIO |
| `pio_claim_free_sm_and_add_program_for_gpio_range` | `bool (const pio_program_t *program, PIO *pio_out, uint *sm_out, uint *offset_out, uint gpio_start, uint gpio_count, bool set_gpio_base)` | RP2350B 用；RP2350A/RP2040 上 `gpio_start+gpio_count` 須 ≤32，`set_gpio_base` 被忽略 |
| `pio_remove_program_and_unclaim_sm` | `void (const pio_program_t *program, PIO pio, uint sm, uint offset)` | 與上面成對 |
| `pio_set_gpio_base` / `pio_get_gpio_base` | `int (PIO pio, uint gpio_base)` / `uint (PIO pio)` | base 只能 0 或 16（RP2350） |

⚠️ `pio_claim_free_sm_and_add_program*` 是 SDK 2.x 才有的 API；若考場 SDK 較舊（1.x）就不存在 ⚠️未驗證考場版本，備案是 `pio_add_program` + `pio_claim_unused_sm`。

### 4.2 SM 設定（`pio_sm_config`，先改 config 再一次套用）

| 函式 | 簽名 | 說明 |
|---|---|---|
| `pio_get_default_sm_config` | `pio_sm_config (void)` | 預設：clkdiv 1、wrap 0..31、in/out 都右移、不 auto、門檻 32、**所有 pin base=0、OUT/SET count=0**、無 side-set。 |
| `<prog>_program_get_default_config` | `pio_sm_config (uint offset)` | pioasm 產生；以上預設 + wrap + `.side_set/.in/.out/.set/.fifo/.mov_status/.clock_div` |
| `sm_config_set_out_pins` | `void (pio_sm_config *c, uint out_base, uint out_count)` | count 0–32；也有 `_out_pin_base`、`_out_pin_count` |
| `sm_config_set_set_pins` | `void (pio_sm_config *c, uint set_base, uint set_count)` | count 0–5；也有 `_set_pin_base`、`_set_pin_count` |
| `sm_config_set_in_pins` | `void (pio_sm_config *c, uint in_base)` | 同 `sm_config_set_in_pin_base` |
| `sm_config_set_in_pin_count` | `void (pio_sm_config *c, uint in_count)` | 1–32；v0 只能 32 |
| `sm_config_set_sideset_pins` | `void (pio_sm_config *c, uint sideset_base)` | 同 `sm_config_set_sideset_pin_base` |
| `sm_config_set_sideset` | `void (pio_sm_config *c, uint bit_count, bool optional, bool pindirs)` | bit_count ≤5，含 opt bit |
| `sm_config_set_jmp_pin` | `void (pio_sm_config *c, uint pin)` | |
| `sm_config_set_out_shift` | `void (pio_sm_config *c, bool shift_right, bool autopull, uint pull_threshold)` | threshold 1–32 |
| `sm_config_set_in_shift` | `void (pio_sm_config *c, bool shift_right, bool autopush, uint push_threshold)` | threshold 1–32 |
| `sm_config_set_fifo_join` | `void (pio_sm_config *c, enum pio_fifo_join join)` | 見 1.3 |
| `sm_config_set_clkdiv` | `void (pio_sm_config *c, float div)` | 1.0–65536.0 |
| `sm_config_set_clkdiv_int_frac` | `void (pio_sm_config *c, uint16_t div_int, uint8_t div_frac8)` | 舊名，保留相容 |
| `sm_config_set_clkdiv_int_frac8` | `void (pio_sm_config *c, uint32_t div_int, uint8_t div_frac8)` | 新名（SDK 2.1.0 起才有，2.0.0 沒有；用 `_int_frac` 或 float 版最保險） |
| `sm_config_set_wrap` | `void (pio_sm_config *c, uint wrap_target, uint wrap)` | **絕對位址**（要加 offset） |
| `sm_config_set_mov_status` | `void (pio_sm_config *c, enum pio_mov_status_type status_sel, uint status_n)` | |
| `sm_config_set_out_special` | `void (pio_sm_config *c, bool sticky, bool has_enable_pin, uint enable_bit_index)` | |
| `pio_sm_set_config` | `int (PIO pio, uint sm, const pio_sm_config *config)` | 直接套用（不 reset、不清 FIFO） |

### 4.3 GPIO

| 函式 | 簽名 | 說明 |
|---|---|---|
| `pio_gpio_init` | `void (PIO pio, uint pin)` | 把 GPIO function 設成該 PIO（內部呼叫 `gpio_set_function`，並打開 pad 的輸入/輸出、RP2350 上解除 pad isolation）。**每個 PIO 要驅動的腳都要呼叫一次**。只當輸入的腳理論上不必選 PIO function，但 pad 仍要設定；呼叫它最省事。 |
| `pio_sm_set_consecutive_pindirs` | `int (PIO pio, uint sm, uint pins_base, uint pin_count, bool is_out)` | 用 exec `set pindirs` 設方向；SM 運作中不要用 |
| `pio_sm_set_pins` | `void (PIO pio, uint sm, uint32_t pin_values)` | 設初始電位（僅 <32 腳；另有 `_pins64`） |
| `pio_sm_set_pins_with_mask` | `void (PIO pio, uint sm, uint32_t pin_values, uint32_t pin_mask)` | 另有 `_with_mask64` |
| `pio_sm_set_pindirs_with_mask` | `void (PIO pio, uint sm, uint32_t pin_dirs, uint32_t pin_mask)` | 另有 `_with_mask64` |
| `pio_set_input_sync_bypass_with_mask` | `void (PIO pio, uint32_t bypass_enables, uint32_t pin_mask)` | |

### 4.4 啟動、停止、重設

| 函式 | 簽名 | 說明 |
|---|---|---|
| `pio_sm_init` | `int (PIO pio, uint sm, uint initial_pc, const pio_sm_config *config)` | 依序：停用 SM → 套 config（NULL 則用預設）→ 清 FIFO → 清 FDEBUG → `pio_sm_restart` → `pio_sm_clkdiv_restart` → exec `jmp initial_pc`。**結束時 SM 為停用**。 |
| `pio_sm_set_enabled` | `void (PIO pio, uint sm, bool enabled)` | |
| `pio_set_sm_mask_enabled` | `void (PIO pio, uint32_t mask, bool enabled)` | |
| `pio_enable_sm_mask_in_sync` | `void (PIO pio, uint32_t mask)` | 同時啟動並同步 clock divider |
| `pio_sm_restart` | `void (PIO pio, uint sm)` | 清 shift counter、ISR 內容、delay counter、IRQ wait 狀態、stall 中的 exec 指令、sticky 輸出。**不改** enable 狀態、PC、OSR 內容、X、Y |
| `pio_sm_clkdiv_restart` | `void (PIO pio, uint sm)` | divider 相位歸零 |
| `pio_sm_clear_fifos` | `void (PIO pio, uint sm)` | 清空 TX/RX（實作：切換 FJOIN_RX 兩次） |
| `pio_sm_drain_tx_fifo` | `void (PIO pio, uint sm)` | 以 exec pull 清 TX（會改 OSR） |
| `pio_sm_set_clkdiv` | `void (PIO pio, uint sm, float div)` | 執行中改速度；另有 `_int_frac`、`_int_frac8` |
| `pio_sm_set_wrap` / `pio_sm_set_out_pins` / `pio_sm_set_set_pins` / `pio_sm_set_in_pins` / `pio_sm_set_sideset_pins` / `pio_sm_set_jmp_pin` | 對應 `sm_config_*` 但直接改 SM | |

### 4.5 FIFO 存取

| 函式 | 簽名 | 說明 |
|---|---|---|
| `pio_sm_put` | `void (PIO pio, uint sm, uint32_t data)` | 直接寫 `pio->txf[sm]`，**不檢查滿**；滿時資料被丟、設 `FDEBUG.TXOVER` |
| `pio_sm_put_blocking` | `void (PIO pio, uint sm, uint32_t data)` | TX 滿就忙等 |
| `pio_sm_get` | `uint32_t (PIO pio, uint sm)` | 直接讀 `pio->rxf[sm]`，**不檢查空**；空時值未定義、設 `FDEBUG.RXUNDER` |
| `pio_sm_get_blocking` | `uint32_t (PIO pio, uint sm)` | RX 空就忙等（SM 永遠不 push 就永遠卡住） |
| `pio_sm_is_tx_fifo_full` / `_empty` | `bool (PIO pio, uint sm)` | |
| `pio_sm_is_rx_fifo_full` / `_empty` | `bool (PIO pio, uint sm)` | |
| `pio_sm_get_tx_fifo_level` / `pio_sm_get_rx_fifo_level` | `uint (PIO pio, uint sm)` | 目前筆數 |

RP2350 PUT/GET 模式：CPU 用 `pio->rxf_putget[sm][i]`（i=0–3）讀寫。

小技巧（datasheet）：RP2350 對 32-bit IO 暫存器做 8/16-bit 寫入時，資料會在 32 bit 內複製（byte 寫入會出現在四個 byte lane），所以用 byte 寫 TX FIFO 時左移或右移都拿得到資料。讀取時若資料在 ISR 高位（右移 + 門檻 < 32），可以 byte 讀 `(uint8_t*)&pio->rxf[sm] + 3`。

### 4.6 指令執行、狀態查詢

| 函式 | 簽名 |
|---|---|
| `pio_sm_exec` | `void (PIO pio, uint sm, uint instr)` |
| `pio_sm_exec_wait_blocking` | `void (PIO pio, uint sm, uint instr)` |
| `pio_sm_is_exec_stalled` | `bool (PIO pio, uint sm)` |
| `pio_sm_get_pc` | `uint8_t (PIO pio, uint sm)`（回傳**絕對**位址，減 offset 才是程式內行號） |

### 4.7 指令編碼函式（`hardware/pio_instructions.h`，由 `pio.h` 引入）

`pio_encode_jmp(addr)`、`pio_encode_jmp_not_x/x_dec/not_y/y_dec/x_ne_y/pin/not_osre(addr)`、`pio_encode_wait_gpio(bool polarity, uint gpio)`、`pio_encode_wait_pin(bool polarity, uint pin)`、`pio_encode_wait_irq(bool polarity, bool relative, uint irq)`、`pio_encode_in(enum pio_src_dest src, uint count)`、`pio_encode_out(enum pio_src_dest dest, uint count)`、`pio_encode_push(bool if_full, bool block)`、`pio_encode_pull(bool if_empty, bool block)`、`pio_encode_mov(dest, src)`、`pio_encode_mov_not(dest, src)`、`pio_encode_mov_reverse(dest, src)`、`pio_encode_irq_set/irq_wait/irq_clear(bool relative, uint irq)`、`pio_encode_set(dest, uint value)`、`pio_encode_nop()`。修飾：`| pio_encode_delay(cycles)`、`| pio_encode_sideset(bit_count, value)`、`| pio_encode_sideset_opt(bit_count, value)`。

`enum pio_src_dest` 常用值：`pio_pins`、`pio_x`、`pio_y`、`pio_null`、`pio_pindirs`、`pio_pc`、`pio_isr`、`pio_osr`、`pio_status`、`pio_exec_mov`、`pio_exec_out`。

### 4.8 中斷

| 函式 | 簽名 |
|---|---|
| `pio_get_irq_num` | `int (PIO pio, uint irqn)`（irqn = 0 或 1） |
| `pio_set_irq0_source_enabled` / `pio_set_irq1_source_enabled` | `void (PIO pio, pio_interrupt_source_t source, bool enabled)` |
| `pio_set_irqn_source_enabled` | `void (PIO pio, uint irq_index, pio_interrupt_source_t source, bool enabled)` |
| `pio_set_irq0_source_mask_enabled` 等 | `void (PIO pio, uint32_t source_mask, bool enabled)` |
| `pio_interrupt_get` / `pio_interrupt_clear` | `bool (PIO pio, uint n)` / `void (PIO pio, uint n)`（n = 0–7） |
| `pio_get_tx_fifo_not_full_interrupt_source` / `pio_get_rx_fifo_not_empty_interrupt_source` | `pio_interrupt_source_t (uint sm)` |

`pio_interrupt_source_t`：`pis_interrupt0..3`（RP2350 另有 `pis_interrupt4..7`）、`pis_smN_tx_fifo_not_full`、`pis_smN_rx_fifo_not_empty`。

```c
// SM 執行 `irq 0` → CPU 中斷
static void my_pio_irq_handler(void) {
    if (pio_interrupt_get(pio0, 0)) {
        pio_interrupt_clear(pio0, 0);   // 一定要清，否則一直進中斷 / irq wait 不會放行
        // ... 處理 ...
    }
}
void setup_irq(void) {
    pio_set_irq0_source_enabled(pio0, pis_interrupt0, true);
    irq_set_exclusive_handler(pio_get_irq_num(pio0, 0), my_pio_irq_handler);  // void irq_set_exclusive_handler(uint num, irq_handler_t handler)
    irq_set_enabled(pio_get_irq_num(pio0, 0), true);                // void irq_set_enabled(uint num, bool enabled)
}
```

---

## 5. 標準初始化流程（記這個順序）

```c
#include "pico/stdlib.h"
#include "hardware/pio.h"
#include "hardware/clocks.h"
#include "myprog.pio.h"

PIO pio; uint sm, offset;
// 1. 載入程式 + 取得 SM（或：pio = pio0; offset = pio_add_program(pio, &myprog_program); sm = pio_claim_unused_sm(pio, true);）
hard_assert(pio_claim_free_sm_and_add_program(&myprog_program, &pio, &sm, &offset));

// 2. 取得預設 config（含 wrap、side-set 位數）
pio_sm_config c = myprog_program_get_default_config(offset);

// 3. 腳位群組
sm_config_set_out_pins(&c, OUT_BASE, OUT_COUNT);
sm_config_set_set_pins(&c, SET_BASE, SET_COUNT);
sm_config_set_in_pins(&c, IN_BASE);
sm_config_set_sideset_pins(&c, SIDE_BASE);
sm_config_set_jmp_pin(&c, JMP_PIN);

// 4. shift / auto / 門檻
sm_config_set_out_shift(&c, true /*右移=LSB先*/, true /*autopull*/, 32);
sm_config_set_in_shift(&c, false /*左移*/, true /*autopush*/, 32);

// 5. FIFO join（單向時）
sm_config_set_fifo_join(&c, PIO_FIFO_JOIN_TX);

// 6. 速度：每秒需要 f_sm 個 SM cycle
sm_config_set_clkdiv(&c, (float)clock_get_hz(clk_sys) / f_sm);

// 7. GPIO：交給 PIO + 方向
pio_gpio_init(pio, OUT_BASE);                       // 每一個輸出腳都要
pio_sm_set_consecutive_pindirs(pio, sm, OUT_BASE, OUT_COUNT, true);

// 8. 初始化（停用狀態）→ 9. 啟動
pio_sm_init(pio, sm, offset, &c);
pio_sm_set_enabled(pio, sm, true);
```

慣例：把 2–9 寫成 `.pio` 檔 `% c-sdk { ... %}` 裡的 `static inline void myprog_program_init(PIO pio, uint sm, uint offset, ...)`。

---

## 6. 範例與逐行解說

### 6.1 考前 demo：`echo`（`section2-2/demo_pio.pio`）

```
.program echo
.wrap_target
    out x, 32       ; OSR 的 32 bit → X（autopull：OSR 空時自動從 TX FIFO 補）
    in  x, 32       ; X → ISR（ISR counter = 32）
    push            ; ISR → RX FIFO（預設 block：RX 滿就等），ISR 清 0
.wrap               ; 零成本回到 out
```

逐 cycle 行為（假設 autopull 開、門檻 32、autopush 關）：

1. 啟動時 OSR counter = 32（空），TX 有資料時 autopull 先填 OSR（不能在同一 cycle 填入又 out），之後 `out x, 32` 把整個 word 給 X，counter 回到 32，若 TX 還有資料就同時補下一筆。
2. `in x, 32`：ISR = X。32-bit 全移入時，移動方向不影響結果。
3. `push`：送進 RX FIFO。
4. 穩態每個 word 3 個 SM cycle（TX 有資料、RX 未滿時）。

這支程式與 datasheet 11.5.7 的 `instructions_to_push` 範例相同。注意事項：

- **必須開 autopull**（`sm_config_set_out_shift(&c, x, true, 32)`），否則 `out` 在 OSR 空時不會自己 pull，也不會 stall，只會移出 OSR 裡殘留的內容（移空後補 0）——echo 會回傳錯誤資料（⚠️依 datasheet 對 OUT/autopull 的描述推論，未實測）。替代做法是在 `out` 前加一條 `pull`。
- **不要同時開 autopush**：`in x, 32` 會觸發 autopush，接著的 `push`（無 iffull）會再推一個 0 進 RX（依 PUSH 定義推論，未實測）。要開 autopush 就把 `push` 刪掉，變成 datasheet 的 `auto_push_pull`（`out x, 32` / `in x, 32`），**每 word 2 cycle**。
- 沒有用到 GPIO，所以不需要 `pio_gpio_init`、pindirs、pin 設定。
- 不能用 `mov isr, osr` 取代：autopull 開啟時 `mov` 讀 OSR 是未定義行為（datasheet 11.5.4.2 ⚠️未查證）。

C 端（自寫範例，未編譯）：

```c
#include <stdio.h>
#include "pico/stdlib.h"
#include "hardware/pio.h"
#include "demo_pio.pio.h"

int main(void) {
    stdio_init_all();
    PIO pio; uint sm, offset;
    hard_assert(pio_claim_free_sm_and_add_program(&echo_program, &pio, &sm, &offset));
    pio_sm_config c = echo_program_get_default_config(offset);
    sm_config_set_out_shift(&c, true, true, 32);    // autopull, 門檻 32
    sm_config_set_in_shift(&c, true, false, 32);    // 不 autopush（程式自己 push）
    pio_sm_init(pio, sm, offset, &c);
    pio_sm_set_enabled(pio, sm, true);
    for (uint32_t i = 0; i < 8; i++) {
        pio_sm_put_blocking(pio, sm, 0x11111111u * i);
        printf("%08lx\n", (unsigned long)pio_sm_get_blocking(pio, sm));
    }
}
```

死結陷阱：若 CPU 先 `put_blocking` 一大串、最後才 `get`，當 RX FIFO（4）+ 管線（ISR/X/OSR）+ TX FIFO（4）都塞滿後，SM 卡在 `push`、CPU 卡在 `put_blocking` → 永久卡住。解法：交錯 put/get、或 TX 與 RX 各用一個 DMA channel（先啟動 RX 的 DMA）。

### 6.2 方波 / 閃爍（`set` + delay + wrap）

datasheet 的 `squarewave`（4 cycle 週期）→ `squarewave_wrap`（用 wrap 去掉 jmp）→ `squarewave_fast`：

```
.program squarewave_fast
    set pindirs, 1     ; 程式內自己設方向（取代 C 端 pindirs）
.wrap_target
    set pins, 1        ; 1 cycle 高
    set pins, 0        ; 1 cycle 低
.wrap
```

- 週期 = 2 SM cycle。sysclk 150 MHz、div=1 → 75 MHz；div = 2.5 → 週期 5 sysclk、30 MHz（但 fractional 會讓高低寬度不均，見 7.2）。
- C 端必須 `sm_config_set_set_pins(&c, pin, 1)`（預設 SET count = 0，`set pins` 會沒效果）＋ `pio_gpio_init(pio, pin)`。

可調頻率的 blink（pico-examples `pio_blink`）：

```
.program blink
    pull block         ; 從 TX 取得半週期計數 n
    out y, 32          ; Y = n
.wrap_target
    mov x, y
    set pins, 1        ; LED on
lp1:
    jmp x-- lp1        ; 執行 n+1 次
    mov x, y
    set pins, 0        ; LED off
lp2:
    jmp x-- lp2
.wrap
```

- 半週期 = 1（mov）+ 1（set）+（n+1）（jmp 迴圈）= n + 3 cycle，所以 C 端送 `clock_get_hz(clk_sys) / (2 * freq) - 3`。
- 這是「把 32-bit 常數從 CPU 送進 Y」的標準手法：`set` 只能 0–31，大常數要用 `pull` + `out y, 32`（或 CPU 端 `pio_sm_put` + `pio_sm_exec(pull)` + `pio_sm_exec(out y,32)`）。

### 6.3 UART TX（side-set + opt）

pico-examples `uart_tx`（8N1）：

```
.program uart_tx
.side_set 1 opt
    pull       side 1 [7]  ; 停止位 / 閒置高電位；TX 空時 stall 在這（side-set 在 stall 時仍生效 → 線保持高）
    set x, 7   side 0 [7]  ; 起始位（低）8 cycle，同時設 bit 計數 7
bitloop:
    out pins, 1            ; 1 bit（LSB 先，所以 out shift 右移）
    jmp x-- bitloop [6]    ; 1 + 6 = 7，加上 out 共 8 cycle/bit，跑 8 次
```

- `.side_set 1 opt` 佔 2 bit → delay 最大 7，`[7]` 剛好用滿。
- 每 bit 8 SM cycle → `div = sysclk / (8 * baud)`。150 MHz、115200 baud → div ≈ 162.76（INT 162，FRAC ≈ 0.76×256 ≈ 194–195，取決於 `PICO_PIO_CLKDIV_ROUND_NEAREST`）。
- init 重點：`pio_sm_set_pins_with_mask64(pio, sm, 1ull<<pin, 1ull<<pin)`（先輸出高，避免一開始送出假起始位）、`pio_sm_set_pindirs_with_mask64(...)`、`pio_gpio_init`、`sm_config_set_out_shift(&c, true, false, 32)`（右移、**不** autopull，因為程式有明確 `pull`）、`sm_config_set_out_pins(&c, pin, 1)` + `sm_config_set_sideset_pins(&c, pin)`（同一腳）、`sm_config_set_fifo_join(&c, PIO_FIFO_JOIN_TX)`（只要 TX → 8 深）。
- 送字元：`pio_sm_put_blocking(pio, sm, (uint32_t)c)`。

### 6.4 自動 pull + side-set 的時脈輸出（datasheet `autopull` / `spi_tx_fast`）

```
.program spi_tx_fast
.side_set 1
loop:
    out pins, 1  side 0    ; 資料變化同時時脈拉低
    jmp loop     side 1    ; 時脈拉高
```

- 每 bit 2 cycle；用 `.wrap` 再省 jmp 也可以（把 `jmp` 換成 `nop side 1`，或兩行都包在 wrap 中）。
- 開 autopull 後 OSR 會自動補，同一程式可每 word 送 8/16/32 bit，只看門檻。

### 6.5 邊緣計數器（自寫範例，已用 pioasm 2.3.1 組譯通過；⚠️未在硬體上測試）

RP2350 版（用 `txput` 把 RX FIFO 當狀態暫存器，CPU 隨時讀最新計數、SM 永不因 FIFO 滿而卡住）：

```
.pio_version 1
.program edge_counter
.fifo txput
    mov x, ~null        ; X = 0xFFFFFFFF
.wrap_target
    wait 0 pin 0        ; 等低
    wait 1 pin 0        ; 等高 → 偵測到上升緣
    jmp x-- dec_done    ; X 一定 -1（dec_done 就是下一條，跳不跳都一樣）
dec_done:               ; 注意：label 不能叫 next/prev（pioasm 保留字，會 syntax error）
    mov isr, ~x         ; ~(0xFFFFFFFF - n) = n
    mov rxfifo[0], isr  ; 寫進狀態格 0
.wrap
```

```c
pio_sm_config c = edge_counter_program_get_default_config(offset); // 已含 fifo join TXPUT
sm_config_set_in_pins(&c, PIN);                     // wait pin 0 = PIN
pio_gpio_init(pio, PIN);
pio_sm_set_consecutive_pindirs(pio, sm, PIN, 1, false);  // 輸入
pio_sm_init(pio, sm, offset, &c);
pio_sm_set_enabled(pio, sm, true);
// ...
uint32_t count = pio->rxf_putget[sm][0];
```

- 每個邊緣至少 5 個 SM cycle 才能回到 `wait 0`，加上輸入同步器 2 cycle 延遲；脈波太窄（< 數個 cycle）會漏算。
- RP2040 相容版：把 `.fifo txput` 與 `mov rxfifo[0], isr` 改成 `push noblock`（FIFO 滿就丟，CPU 讀時要把 FIFO 讀到空、取最後一筆）。

### 6.6 PWM（`pull noblock` 重用舊值、ISR 當設定暫存器）

datasheet `pwm`：`pull noblock side 0` → `mov x, osr` → `mov y, isr` → 用 `jmp x!=y` 比較計數，`jmp y--` 倒數。CPU 設週期的手法：

```c
pio_sm_set_enabled(pio, sm, false);
pio_sm_put_blocking(pio, sm, period);
pio_sm_exec(pio, sm, pio_encode_pull(false, false));
pio_sm_exec(pio, sm, pio_encode_out(pio_isr, 32));
pio_sm_set_enabled(pio, sm, true);
```

重點：程式不用 `in` 時 ISR 可當「CPU 寫一次、SM 一直讀」的設定暫存器；`pull noblock` 在 TX 空時等於 `mov osr, x`，所以沒新值就沿用舊值。

### 6.7 其他官方範例速記

| 範例 | 學到的技巧 |
|---|---|
| `ws2812`（4 條指令） | `.define public T1/T2/T3` 由 C 端算 clkdiv；`out x, 1` + `jmp !x` 依 bit 分支；左移 + autopull 門檻 24，CPU 送 `grb << 8` |
| `addition` | 用 `x + y == ~(~x - y)` 與 `jmp x--`/`jmp y--` 做加法（示範，極慢） |
| `uart_rx`、`spi`、`i2c`、`manchester`、`logic_analyser` | 見 pico-examples `pio/` |

---

## 7. 時序計算

### 7.1 基本公式

- `f_sm = f_sys / div`，`div = INT + FRAC/256`，1 ≤ div ≤ 65536。
- 一條指令 = `1 + delay` 個 SM cycle（不含 stall）。
- `jmp x-- label` 迴圈：X 初值 n → 迴圈體執行 n+1 次。
- 資料率：`bit_rate = f_sm / cycles_per_bit` → `div = f_sys / (bit_rate × cycles_per_bit)`。
- 程式寫法建議：決定「每 bit 幾個 cycle」（例 8），每條路徑的 cycle 數用 delay 補平，再用 clkdiv 對準速率。

### 7.2 Clock divider 細節

- 整數 div = n：每 n 個 sysclk 執行 1 cycle。
- 小數：用一階 delta-sigma，部分週期是 n、部分是 n+1 個 sysclk → 平均正確但有 **jitter**（最多 1 sysclk）。n 小時影響明顯；高速非同步串列建議用整除或 1 Mbaud 的倍數。
- `pio_sm_clkdiv_restart()` / `pio_enable_sm_mask_in_sync()` 讓多個 SM 的 divider 同相位。

### 7.3 數字速查（f_sys = 150 MHz）

| 目標 | cycles/bit | div |
|---|---|---|
| 最大方波（`squarewave_fast`） | 2 cycle/週期 | 1 → 75 MHz |
| UART 115200（uart_tx） | 8 | 162.76 |
| UART 1 Mbaud | 8 | 18.75 |
| 每 cycle 1 個 SM tick 的 10 MHz | — | 15（整數，無 jitter） |
| 最慢 | — | 65536 → 約 2289 Hz 的 SM clock |

- 不要假設 sysclk：用 `clock_get_hz(clk_sys)`（`uint32_t clock_get_hz(clock_handle_t clock)`）。

---

## 8. 用 DMA 餵 PIO

```c
#include "hardware/dma.h"

// TX：記憶體 → PIO TX FIFO
int ch = dma_claim_unused_channel(true);
dma_channel_config dc = dma_channel_get_default_config(ch);
channel_config_set_transfer_data_size(&dc, DMA_SIZE_32);
channel_config_set_read_increment(&dc, true);    // 來源陣列往前走
channel_config_set_write_increment(&dc, false);  // 目的地固定是 FIFO
channel_config_set_dreq(&dc, pio_get_dreq(pio, sm, true));   // 由 TX FIFO「有空位」節流
dma_channel_configure(ch, &dc,
                      &pio->txf[sm],   // write_addr
                      src,             // read_addr
                      N,               // 筆數（transfer 數，不是 byte 數！）
                      true);           // 立即開始
dma_channel_wait_for_finish_blocking(ch);

// RX：PIO RX FIFO → 記憶體
//   read_increment=false、write_increment=true、dreq = pio_get_dreq(pio, sm, false)、read_addr = &pio->rxf[sm]
```

- `count` 是**傳輸筆數**不是 byte 數（考前 section2-3 transfer-engine 也在強調這點）。
- 新版 SDK 的 `dma_channel_configure` 第 5 參數名為 `encoded_transfer_count`；RP2350 上直接傳 < 2^28 的筆數即可（`dma_encode_transfer_count(n)` 對一般 n 就是 n）。
- 雙向（如 echo）：**先啟動 RX channel，再啟動 TX channel**，避免 RX FIFO 滿而 stall。
- 資料寬度 8-bit 時（`DMA_SIZE_8`）：搭配 autopull 門檻 8；RP2350 byte 寫入會在 32 bit 中複製，左/右移都能用。
- FIFO join（8 深）讓 DMA 更不容易斷流；datasheet：8 格足以每 clock 1 word。

---

## 9. 效能優化清單

| 槓桿 | 做法 | 效果 |
|---|---|---|
| `.wrap` 取代 `jmp` | 主迴圈尾巴用 `.wrap` | 少 1 指令、每圈少 1 cycle |
| autopull / autopush | `sm_config_set_out_shift(..., true, thr)` / `in_shift(..., true, thr)` | 省 `pull`/`push` 指令與 cycle；OSR 可每 cycle 輸出 |
| side-set | 時脈/控制線放 side-set | 同 cycle 改資料 + 時脈；省 `set` 指令 |
| FIFO join | 單向傳輸時 `PIO_FIFO_JOIN_TX/RX` | FIFO 4 → 8，CPU/DMA 喘息時間加倍 |
| 用 DMA | `pio_get_dreq` + `&pio->txf[sm]` | CPU 完全不參與搬運 |
| 位元打包 | `in pins, 8` + autopush 32 → 每 word 4 個樣本；`out pins, 8` + autopull 32 反之 | FIFO/DMA 流量降為 1/4 |
| 對齊 | 右移 + 門檻 <32 時資料在高位：`in null, 32-n` 補齊，或改左移，或 byte 讀 offset+3 | 省 CPU 端移位 |
| `mov` 運算 | `mov isr, ::osr`（位元反轉）、`mov x, ~y`（反相）、`mov x, ~null`（0xFFFFFFFF） | 1 cycle 完成位元操作（注意 autopull 開時不要 mov 讀 OSR ⚠️未查證；需手動 `pull`） |
| 平行化 | 同一程式載入一次，多個 SM 用不同 pin 跑（同 block 的 SM 共用指令） | 4 SM × 3 block |
| clkdiv = 1 | 能用 delay 調時序就讓 SM 全速 | 最高吞吐 |
| 整數 clkdiv | 避免小數 | 無 jitter |
| RX FIFO 當狀態暫存器（v1） | `.fifo txput` + `mov rxfifo[i], isr` | SM 不會因 RX 滿而卡住；CPU 隨時讀最新值 |
| `out exec` / `pio_sm_exec` | 把指令夾在資料流或由 CPU 注入 | 省指令記憶體、動態控制流程 |
| 指令記憶體不夠 | 共用程式、用 side-set/autopull/wrap 精簡、拆到其他 PIO block | 每 block 只有 32 格 |

⚠️ 不要高估 PIO 運算：例如單純反轉 32 bit，Cortex-M33 本身有 `RBIT` 指令，pico-sdk 也提供 `uint32_t __rev(uint32_t)`（`pico/bit_ops.h`，反轉 32 bit 位元順序），CPU 做也很快；PIO 的價值在於「與 I/O 同步、與 CPU 並行」，而不是比 CPU 快。

---

## 10. 常見錯誤（pitfalls）

| 症狀 | 可能原因 | 修正 |
|---|---|---|
| 腳位完全沒輸出 | 沒 `pio_gpio_init(pio, pin)`（GPIO function 不是 PIO） | 每個輸出腳都呼叫 |
| 腳位沒輸出 | 沒設方向（pindirs 預設輸入） | `pio_sm_set_consecutive_pindirs(..., true)` 或程式內 `set pindirs, 1` |
| `set pins` 沒效果 | `pio_get_default_sm_config()` 的 SET count = 0 | `sm_config_set_set_pins(&c, base, count)` 或 `.set n` |
| `out pins` 沒效果 | OUT count = 0 | `sm_config_set_out_pins(&c, base, count)` |
| 程式跑飛、跑到別的程式 | 用 `pio_get_default_sm_config()` 沒設 wrap；或 wrap 沒加 offset | 用 `<prog>_program_get_default_config(offset)` |
| 位元順序顛倒 | shift 方向錯：UART/SPI LSB-first → 右移；MSB-first → 左移 | `sm_config_set_out_shift(&c, shift_right, ...)` |
| 收到的資料在高位 | in 右移 + 門檻 < 32 | `in null, k`、改左移、或 byte 讀 |
| 每 word 只送出部分 bit 或多送 | autopull/autopush 門檻錯 | 門檻 = 每筆有效 bit 數 |
| `out` 讀到殘值/0、不等 TX 資料 | autopull 沒開但程式沒有 `pull`（不開 autopull 時 `out` 不會 stall，見 6.1） | 開 autopull 或加 `pull` |
| 多推了 0 進 RX | 開了 autopush 又寫 `push` | 二擇一，或 `push iffull` |
| side-set 組譯錯誤 / delay 不能寫 `[n]` | side-set 吃掉 delay bit | 見 2.4 表；opt 多吃 1 bit |
| 非 opt side-set 某行沒寫 `side` | 非 opt 時每行都必須有 | 加 `side` 或改 `opt` |
| `pio_add_program` 回負值 / panic | 32 格指令記憶體滿 | `pio_can_add_program` 檢查、換 block、精簡程式 |
| `pio_sm_get_blocking` 永遠卡住 | SM 沒啟動、卡在 wait、沒 push、或 RX join 掉了 | 查 PC、FIFO level、enable |
| SM 完全沒動 | 忘了 `pio_sm_set_enabled(pio, sm, true)`（`pio_sm_init` 後為停用） | 啟用 |
| 資料遺失 | `pio_sm_put` 不檢查滿（TX 滿直接丟） | 用 `_blocking` 或先檢查；看 `FDEBUG.TXOVER` |
| CPU 與 SM 互卡 | 先全部 put 再 get | 交錯或用兩個 DMA |
| `jmp` 用 `pio_encode_jmp()` 跳錯 | 位址是絕對的 | 加 `offset` |
| 跨 SM 腳位衝突 | 高編號 SM 優先 | 分配不重疊的 pin |
| UART 一開始送出雜訊 | 初始腳位為低 → 被當起始位 | 先 `pio_sm_set_pins_with_mask` 設高再設方向 |
| 新指令組譯失敗（`mov pindirs`、`rxfifo[]` 等） | build 成 RP2040（沒設 `PICO_BOARD=pico2` / `PICO_PLATFORM`）→ pioasm 收到 `-v 0`；或手動跑 pioasm 沒加 `-v 1` | 設 pico2 重新 configure（刪 build）；手動 pioasm 才加 `.pio_version 1` |
| `wait 1 irq n` 與 CPU ISR 搶 | datasheet 明確警告 | 改用 `irq wait n` 讓 CPU 清除 |
| 改 FIFO join 後資料不見 | 改 FJOIN 會清空 FIFO | 先 drain |
| 窄脈波量不到 | 2-cycle 同步器延遲 + 迴圈 cycle 數 | 縮短迴圈、clkdiv = 1、必要時 bypass（僅同步訊號） |

---

## 11. 除錯流程

1. **它有沒有在跑？** 讀 `pio->ctrl` 低 4 bit（SM enable）。
2. **PC 卡在哪？** `pio_sm_get_pc(pio, sm) - offset` 對照 `.pio.h` 的反組譯註解；`pio->sm[sm].instr` 讀出目前 PC 上的指令編碼。卡在 `pull`/`out` → TX 沒資料；卡在 `push`/`in` → RX 滿；卡在 `wait` → 條件沒到。
3. **FIFO 狀態**：`pio_sm_get_tx_fifo_level()`、`pio_sm_get_rx_fifo_level()`、`pio_sm_is_*_fifo_*()`。
4. **Sticky 錯誤旗標** `pio->fdebug`（寫 1 清除）：bits 27:24 `TXSTALL`（SM 因 TX 空而等，依 SM 編號）、19:16 `TXOVER`（CPU 寫滿的 TX）、11:8 `RXUNDER`（CPU 讀空的 RX）、3:0 `RXSTALL`（SM 因 RX 滿而等，或 `push noblock` 丟資料）。
5. **腳位實際輸出**：`pio->dbg_padout`（PIO 驅動的電位）、`pio->dbg_padoe`（方向）。配合 `gpio_get(pin)` 看實際電位。
6. **偷看 X/Y**（會改 ISR，除錯用）：
   ```c
   pio_sm_set_enabled(pio, sm, false);
   pio_sm_exec(pio, sm, pio_encode_mov(pio_isr, pio_x));
   pio_sm_exec(pio, sm, pio_encode_push(false, false));
   uint32_t x = pio_sm_get(pio, sm);   // 若 RX 已滿則此值不可靠
   ```
7. **手動單步 / 放慢**：停用 SM 後用 `pio_sm_exec` 一條條注入指令觀察；或 `pio_sm_set_clkdiv(pio, sm, 65535.0f)` 讓 SM 慢到可以在迴圈中取樣 PC。
8. **核對編碼**：看 pioasm 產生的 `.pio.h` 註解；手寫 `pio_encode_*` 的結果可與它比對。
9. **核對設定**：印出 `pio->sm[sm].pinctrl / execctrl / shiftctrl / clkdiv`，對照 datasheet 欄位（PINCTRL：SIDESET_COUNT 31:29、SET_COUNT 28:26、OUT_COUNT 25:20、IN_BASE 19:15、SIDESET_BASE 14:10、SET_BASE 9:5、OUT_BASE 4:0；SHIFTCTRL：FJOIN_RX 31、FJOIN_TX 30、PULL_THRESH 29:25、PUSH_THRESH 24:20、OUT_SHIFTDIR 19、IN_SHIFTDIR 18、AUTOPULL 17、AUTOPUSH 16、FJOIN_RX_PUT 15、FJOIN_RX_GET 14、IN_COUNT 4:0；EXECCTRL：EXEC_STALLED 31、SIDE_EN 30、SIDE_PINDIR 29、JMP_PIN 28:24、WRAP_TOP 16:12、WRAP_BOTTOM 11:7、STATUS_SEL 6:5、STATUS_N 4:0）。

### 除錯檢查表（照順序打勾）

- [ ] `.pio.h` 有產生且 include 正確（`xxx.pio.h`）
- [ ] `pio_add_program` 成功（offset ≥ 0）
- [ ] 用 `<prog>_program_get_default_config(offset)`
- [ ] 每個用到的 pin 群組都設了 base（和 count）
- [ ] `pio_gpio_init` 每個輸出腳、pindirs 正確
- [ ] shift 方向、auto、門檻符合資料格式
- [ ] clkdiv 由 `clock_get_hz(clk_sys)` 算出
- [ ] `pio_sm_init` 後有 `pio_sm_set_enabled(true)`
- [ ] CPU 端 put/get 不會互相卡死
- [ ] FDEBUG 沒有 TXOVER / RXUNDER

### 優化檢查表

- [ ] 主迴圈用 `.wrap`，沒有多餘 `jmp`
- [ ] 能 autopull/autopush 就開
- [ ] 時脈/控制線用 side-set
- [ ] 單向傳輸有 FIFO join
- [ ] 大量資料用 DMA（先 RX 後 TX）
- [ ] 窄資料有打包（每 word 多筆）
- [ ] 每條路徑 cycle 數相等（用 delay 補）
- [ ] clkdiv 能整數就整數
- [ ] 沒有把 CPU 做得更快的事硬塞給 PIO

---

## 12. 向模型提問的範本

範本 1：寫 PIO 程式

```
我在 RP2350（Pico 2，pico-sdk 2.x，sysclk {{150 MHz}}）上要用 PIO 實作 {{協定/功能，例如：8N1 UART TX 115200 baud}}。
腳位：{{輸出 GPIO x、輸入 GPIO y}}。資料格式：{{每筆幾 bit、LSB/MSB first}}。
限制：指令記憶體剩 {{N}} 格、{{是否可用 DMA}}。
請給：(1) .pio 程式（含 .program、.side_set、.wrap），每行註解 cycle 數；(2) % c-sdk 的 init 函式，
明確寫出 out/in shift 方向、autopull/autopush 門檻、clkdiv 計算式、pio_gpio_init 與 pindirs；
(3) 每 bit/每 word 的 cycle 計算；(4) 這個設計可能卡住（stall）的地方。請依我貼的 pio.md 參考，不確定的 API 請標明。
```

範本 2：除錯

```
我的 PIO 程式行為不對。.pio 內容：
{{貼 .pio}}
C 初始化：
{{貼 C}}
觀察到：{{例如：pio_sm_get_blocking 卡住 / 腳位無輸出 / 資料位元順序錯}}。
pio_sm_get_pc - offset = {{值}}，TX level = {{值}}，RX level = {{值}}，fdebug = {{0x...}}。
請依 pio.md 第 10、11 節逐項排查，指出最可能原因與修改後的完整程式碼。
```

範本 3：效能優化

```
這支 PIO + C 程式目前 {{吞吐量/延遲數據}}，目標是 {{目標數據}}。
{{貼程式}}
請分析：每 word 的 SM cycle 數、CPU 端瓶頸（put/get 迴圈、中斷）、是否可用 .wrap/autopull/autopush/side-set/FIFO join/DMA/位元打包/多個 SM 平行。
列出每項改動預估省下多少 cycle，並給修改後程式碼。不要改變對外行為：{{必須保持的輸出格式/時序}}。
```

範本 4：閱讀文件後實作

```
以下是考題提供的硬體/系統文件片段：
{{貼文件}}
請先用條列整理：涉及哪些 PIO 資源（block/SM/腳位/FIFO/IRQ）、資料流向、時序要求。
再對照 pio.md 判斷哪些需要 RP2350 專屬功能（PIO v1；確認 build 是 pico2）。最後給實作步驟與程式碼骨架。
```

範本 5：解釋與驗算

```
請逐 cycle 模擬這段 PIO 程式（autopull={{on/off}}, 門檻={{n}}, autopush={{on/off}}, shift={{left/right}}），
初始 TX FIFO = {{資料}}，列出每 cycle 的 PC、X、Y、OSR、ISR、shift counter、FIFO 內容與腳位：
{{貼 .pio}}
```
