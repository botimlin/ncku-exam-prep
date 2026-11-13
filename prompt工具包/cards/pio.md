# 貼上卡：RP2350 PIO（Programmable I/O）
> 用法：一次只複製一張卡（兩條分隔線之間），貼進對話，再在下面寫你的問題。每張 ≤ 1200 字元。
> 來源：full/domain/pio.md、lite/domain/pio.md（詳細版）｜最後更新 2026-11

---

【參考卡｜RP2350 PIO 1/8｜C 端初始化順序】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
RP2350（Pico 2）：3 個 PIO（pio0/1/2）× 4 SM（RP2040 只有 2 個 PIO）。
```c
PIO pio; uint sm, offset;
hard_assert(pio_claim_free_sm_and_add_program(&myprog_program, &pio, &sm, &offset));
pio_sm_config c = myprog_program_get_default_config(offset);
sm_config_set_out_pins(&c, OUT_BASE, OUT_COUNT);
sm_config_set_set_pins(&c, SET_BASE, SET_COUNT);
sm_config_set_in_pins(&c, IN_BASE);
sm_config_set_sideset_pins(&c, SIDE_BASE);
sm_config_set_out_shift(&c, true /*右移=LSB先*/, true /*autopull*/, 32);
sm_config_set_in_shift(&c, false /*左移*/, true /*autopush*/, 32);
// 只送不收才加：sm_config_set_fifo_join(&c, PIO_FIFO_JOIN_TX);
sm_config_set_clkdiv(&c, (float)clock_get_hz(clk_sys) / f_sm);
pio_gpio_init(pio, OUT_BASE);
pio_sm_set_consecutive_pindirs(pio, sm, OUT_BASE, OUT_COUNT, true);
pio_sm_init(pio, sm, offset, &c);
pio_sm_set_enabled(pio, sm, true);
```
- default config 已含 wrap 與 side-set 位數。
- 每個輸出腳都要 `pio_gpio_init`；SET count ≤5；init 後 SM 停用。
- 備案：`pio_add_program(pio, &p)` 回 offset（<0 失敗）+ `pio_claim_unused_sm(pio, true)`。
- CMake：`pico_generate_pio_header(app ${CMAKE_CURRENT_LIST_DIR}/myprog.pio)`＋link `hardware_pio`，`#include "myprog.pio.h"`。

---

【參考卡｜RP2350 PIO 2/8｜9 條指令】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
RP2350 PIO = version 1（RP2040 為 v0）。9 條：JMP WAIT IN OUT PUSH PULL MOV IRQ SET；`nop` = `mov y, y`。
| 指令 | 重點 |
|---|---|
| `jmp (cond) L` | cond：無 `!x` `x--` `!y` `y--` `x!=y` `pin` `!osre`。`x--`：X≠0 則跳，先判斷再減（一定減）。L 絕對位址，SDK 自動加 offset |
| `wait pol gpio/pin/irq n` | gpio=絕對號；pin=IN_BASE+n；`wait 1 irq` 成立後自動清 flag |
| `in src, n` | src：pins x y null isr osr；取 src 最低 n bit 移入 ISR |
| `out dst, n` | dst：pins x y null pindirs pc isr exec；從 OSR 移出 n bit |
| `push (iffull) (block\|noblock)` | ISR→RX FIFO，ISR 清 0；預設 block |
| `pull (ifempty) (block\|noblock)` | TX FIFO→OSR；預設 block；noblock 遇空 = `mov osr, x` |
| `mov dst, (op) src` | op：`!`/`~` 反相、`::` 位元反轉；src 含 status |
| `irq (set\|wait\|clear) n (rel)` | flag 0–7；wait=設後等清；rel=加 SM 號 |
| `set dst, v` | dst：pins x y pindirs；v=0–31 |
- n=1–32。大常數用 `pull`+`out y, 32`。
- 不開 autopull 時 `out` 不會等 TX 資料（移出殘值/0）；autopull 開時 `mov` 讀 OSR 未定義 ⚠️未查證。
- Stall：wait 未成立、pull 遇 TX 空、push 遇 RX 滿、irq wait。
- v1 新增（SDK 對 RP2350 自動 `-v 1`；手動 pioasm 加 `.pio_version 1`）：`mov pindirs`、`mov rxfifo[i]`（↔ isr/osr）、`irq prev/next`（不配 rel）、`wait jmppin`。
- 編碼：`out x, 32`=0x6020、`in x, 32`=0x4020、`push`=0x8020。

---

【參考卡｜RP2350 PIO 3/8｜side-set / delay 預算、wrap、directives】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
RP2350 PIO（v1）：delay `[n]` 與 side-set 共用指令 bit 12–8，共 5 bit。
| `.side_set` 宣告 | 佔 bit（含 opt） | 最大 delay |
|---|---|---|
| 無 | 0 | 31 |
| `.side_set 1` | 1 | 15 |
| `.side_set 1 opt` / `.side_set 2` | 2 | 7 |
| `.side_set 2 opt` / `.side_set 3` | 3 | 3 |
| `.side_set 4` | 4 | 1 |
| `.side_set 5` / `.side_set 4 opt` | 5 | 0 |
- 非 opt：**每一條指令都必須寫 `side x`**，否則組譯錯誤。opt 可省略，但多吃 1 bit。
- `pindirs` 參數：改方向而非電位。side-set 在指令第一個 cycle 生效，stall 中也生效。
- C 端：`<prog>_program_get_default_config(offset)` 已呼叫 `sm_config_set_sideset(&c, bit_count含opt, opt, pindirs)`；你只需 `sm_config_set_sideset_pins(&c, base)`。
- 每條指令 = 1 + delay 個 SM cycle（不含 stall）。
Wrap：PC 到 `.wrap` 時跳回 `.wrap_target`，0 cycle、0 指令。`pio_get_default_sm_config()` 的 wrap 是 0..31、OUT/SET count=0 → **一定用 `<prog>_program_get_default_config(offset)`**（內含 `sm_config_set_wrap(&c, offset + wrap_target, offset + wrap)`）。
Directives：`.program name`、`.pio_version 1`（宣告用 v1）、`.side_set`、`.wrap_target`/`.wrap`（各一次）、`.origin`、`.define PUBLIC sym v`、`.fifo txrx|tx|rx|txput|txget|putget`、`.clock_div`、`% c-sdk { ... %}`（放 init helper）。
每個 PIO 只有 32 格指令記憶體（4 SM 共用）。

---

【參考卡｜RP2350 PIO 4/8｜echo 範例逐步追蹤】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
RP2350（Pico 2）PIO，考前 demo `demo_pio.pio`：
```
.program echo
.wrap_target
    out x, 32       ; OSR 的 32 bit → X（autopull：OSR 空時自動從 TX FIFO 補）
    in  x, 32       ; X → ISR（ISR counter = 32）
    push            ; ISR → RX FIFO（預設 block：RX 滿就等），ISR 清 0
.wrap               ; 零成本回到 out
```
追蹤（autopull 開、門檻 32、autopush 關）：開機 OSR counter=32（空）→ TX 有資料時 autopull 填 OSR → `out x, 32` 整個 word 給 X → `in x, 32` ISR=X → `push` 進 RX FIFO。穩態每 word 3 個 SM cycle。
- **必須開 autopull**（`sm_config_set_out_shift(&c, true, true, 32)`），否則 `out` 不會自己 pull，回傳錯誤資料（⚠️依 datasheet 推論，未實測）；或在 `out` 前加 `pull`。
- **不要同時開 autopush**：`in x, 32` 觸發 autopush 後 `push` 會再推一個 0（推論，未實測）。要 autopush 就刪掉 `push` → 每 word 2 cycle。
- 沒用 GPIO，不需 `pio_gpio_init`/pindirs。不能用 `mov isr, osr` 取代（autopull 時未定義 ⚠️未查證）。
C 端：`echo_program_get_default_config(offset)` → `sm_config_set_out_shift(&c, true, true, 32)` → `sm_config_set_in_shift(&c, true, false, 32)` → `pio_sm_init` → `pio_sm_set_enabled` → 迴圈 `pio_sm_put_blocking` 一筆、`pio_sm_get_blocking` 一筆。
死結：先 put 一大串再 get → TX(4)+管線+RX(4) 塞滿後 SM 卡 push、CPU 卡 put。交錯 put/get，或用兩個 DMA（先啟動 RX）。

---

【參考卡｜RP2350 PIO 5/8｜blink 範例追蹤與 SM 資源】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
RP2350（Pico 2）PIO；預設 clk_sys 150 MHz（RP2040 125 MHz），用 `clock_get_hz(clk_sys)`。
可調頻率 blink（pico-examples `pio_blink`）：
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
- 半週期 = 1（mov）+ 1（set）+（n+1）（jmp 迴圈）= n + 3 cycle → C 端送 `clock_get_hz(clk_sys) / (2 * freq) - 3`。
- 32-bit 常數送進 Y 的標準手法：`pull` + `out y, 32`（`set` 只能 0–31）。
- C 端：`sm_config_set_set_pins(&c, pin, 1)`（預設 SET count=0 → `set pins` 無效）+ `pio_gpio_init(pio, pin)` + pindirs 設輸出。
- 最快方波：`set pindirs, 1` 後 wrap 內 `set pins, 1` / `set pins, 0`，週期 2 SM cycle → 150 MHz、div=1 時 75 MHz。
SM 資源速記：
- 每 PIO 32 格指令記憶體（4 SM 共用）。
- 每 SM：X、Y（32-bit）、OSR、ISR、shift counter（0–32）、PC（5-bit）、clkdiv、TX/RX FIFO 各 4 格（join 成單向 8 格）。
- 資料流：CPU → TX FIFO →（pull）→ OSR →（out）→ pins/X；pins/X →（in）→ ISR →（push）→ RX FIFO → CPU。
- 多個 SM 寫同一腳 → 編號大的 SM 優先；同 SM 的 OUT/SET 與 side-set 衝突 → side-set 優先。
- Pico 2 板載 LED = GPIO25（Pico 2 W 不是）。

---

【參考卡｜RP2350 PIO 6/8｜時序計算與 clkdiv】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
RP2350（Pico 2）：預設 clk_sys 150 MHz（RP2040 為 125 MHz）。不要假設，用 `clock_get_hz(clk_sys)`。
- `f_sm = f_sys / div`，`div = INT + FRAC/256`，1 ≤ div ≤ 65536。
- 一條指令 = 1 + delay 個 SM cycle（不含 stall）。
- `jmp x-- L` 迴圈：X 初值 n → 迴圈體執行 n+1 次。
- `div = f_sys / (bit_rate × cycles_per_bit)`。
- 設計法：先決定每 bit 幾 cycle，每條路徑用 delay 補平，再用 clkdiv 對準速率。
- 小數 div：一階 delta-sigma，部分週期 n、部分 n+1 個 sysclk → 平均對但有 jitter（最多 1 sysclk）。能整數就整數。
- 輸入同步器 2 cycle 延遲。
速查（150 MHz）：
| 目標 | cycles/bit | div |
|---|---|---|
| 最大方波 | 2/週期 | 1 → 75 MHz |
| UART 115200（uart_tx） | 8 | 162.76 |
| UART 1 Mbaud | 8 | 18.75 |
| 10 MHz SM clock | — | 15（整數） |
| 最慢 | — | 65536 → 約 2289 Hz |
uart_tx（`.side_set 1 opt`，delay 上限 7）：
```
    pull       side 1 [7]  ; 停止位 / 閒置高電位
    set x, 7   side 0 [7]  ; 起始位 8 cycle，bit 計數 7
bitloop:
    out pins, 1            ; LSB 先 → out shift 右移
    jmp x-- bitloop [6]    ; 1 + 6 + out 1 = 8 cycle/bit
```
init：out shift 右移、**不** autopull（有明確 pull）、OUT 與 side-set 同一腳、`PIO_FIFO_JOIN_TX`；先 `pio_sm_set_pins_with_mask` 設高再設方向，避免假起始位。

---

【參考卡｜RP2350 PIO 7/8｜DMA 餵 PIO、優化】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
RP2350（Pico 2）：16 DMA ch、3 個 PIO；DREQ 號與 RP2040 不同，用 `pio_get_dreq()`。
```c
int ch = dma_claim_unused_channel(true);
dma_channel_config dc = dma_channel_get_default_config(ch);
channel_config_set_transfer_data_size(&dc, DMA_SIZE_32);
channel_config_set_read_increment(&dc, true);    // 來源陣列往前走
channel_config_set_write_increment(&dc, false);  // 目的地固定是 FIFO
channel_config_set_dreq(&dc, pio_get_dreq(pio, sm, true));
dma_channel_configure(ch, &dc,
                      &pio->txf[sm],   // write_addr（先目的地）
                      src,             // read_addr
                      N,               // 筆數，不是 byte 數！
                      true);
dma_channel_wait_for_finish_blocking(ch);
```
- RX：read_increment=false、write_increment=true、dreq=`pio_get_dreq(pio, sm, false)`、read_addr=`&pio->rxf[sm]`。
- 雙向：**先啟動 RX channel 再 TX**。DMA 跑時 CPU 不可 put/get 同一 FIFO。
優化：
- `.wrap` 取代尾端 `jmp`（每圈少 1 cycle）；autopull/autopush 省 pull/push。
- 時脈/控制線放 side-set；單向用 `PIO_FIFO_JOIN_TX/RX`。
- 位元打包：`in pins, 8` + autopush 32 → 每 word 4 樣本。
- 同程式載入一次、多 SM 跑不同腳；整數 clkdiv 無 jitter。
- 單純位元運算 CPU 可能更快（M33 有 `RBIT`、SDK `__rev()`）；PIO 價值在與 I/O 同步、與 CPU 並行。

---

【參考卡｜RP2350 PIO 8/8｜常見錯誤與除錯】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
RP2350（Pico 2）PIO（v1，3 個 PIO block）。
常見錯誤：
1. 腳沒輸出：沒 `pio_gpio_init(pio, pin)`，或沒設 pindirs（`pio_sm_set_consecutive_pindirs(...,true)` 或 `set pindirs, 1`）。
2. `set pins`/`out pins` 無效：SET/OUT count 預設 0 → `sm_config_set_set_pins/out_pins`。
3. 跑飛：用 `pio_get_default_sm_config()` 沒設 wrap，或 wrap 沒加 offset。
4. 位元順序反：LSB-first 用右移、MSB-first 用左移。右移+門檻<32 時資料在 ISR 高位。
5. `out` 讀到殘值：沒 autopull 也沒 `pull`。
6. 多推 0：autopush 與 `push` 同時用。
7. 忘了 `pio_sm_set_enabled(pio, sm, true)`（`pio_sm_init` 後為停用）。
8. `get_blocking` 永遠卡：SM 沒跑/卡 wait/沒 push；先全 put 再 get。
9. `pio_add_program` 回負值：32 格滿。
10. side-set 吃掉 delay bit；非 opt 某行沒寫 `side`。
11. `pio_encode_jmp()` 沒加 offset。
12. v1 指令組譯失敗：build 成 RP2040（沒設 pico2）。
13. `pio_sm_put` 不檢查滿，TX 滿時資料丟。
除錯：
- `pio->ctrl` 低 4 bit=SM enable。
- `pio_sm_get_pc(pio, sm) - offset` 對照 `.pio.h` 反組譯：卡 pull/out → TX 沒資料；卡 push/in → RX 滿；卡 wait → 條件沒到。
- `pio_sm_get_tx_fifo_level`、`pio_sm_get_rx_fifo_level`。
- `pio->fdebug`（寫 1 清）：TXSTALL 27:24、TXOVER 19:16、RXUNDER 11:8、RXSTALL 3:0。
- `pio->dbg_padout`/`dbg_padoe` 看驅動電位/方向。
- 停用 SM 後用 `pio_sm_exec(pio, sm, pio_encode_...)` 注入指令；`pio_sm_set_clkdiv(pio, sm, 65535.0f)` 放慢。
