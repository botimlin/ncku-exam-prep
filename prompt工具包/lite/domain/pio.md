# RP2350 PIO 速查（lite）

- 用途：上機考 PIO 精簡參考（完整版見 full/domain/pio.md）
- 適用版本：RP2350（Pico 2）、PIO v1、pico-sdk 2.x
- 來源：https://datasheets.raspberrypi.com/rp2350/rp2350-datasheet.pdf 第 11 章；github.com/raspberrypi/pico-sdk `hardware_pio/pio.h`、`pio_instructions.h`
- 最後更新：2026-11

## 架構
- 3 個 PIO（pio0–2）× 4 SM；RP2040 只有 2 個。每 PIO 32 格指令記憶體，4 SM 共用。
- 每 SM：X、Y、OSR、ISR、shift counter（0–32）、PC、TX/RX FIFO 各 4 格（join 成單向 8 格）。
- 資料流：CPU→TX FIFO→(pull)→OSR→(out)→pins/X；pins/X→(in)→ISR→(push)→RX FIFO→CPU。
- 每指令 1 cycle（stall 除外）；`[n]` delay 與 side-set 共用 5 bit。
- clkdiv = INT + FRAC/256，1–65536；小數會 jitter。sysclk 預設 150 MHz（用 `clock_get_hz(clk_sys)`）。
- `.wrap_target`/`.wrap`：零成本迴圈。
- RP2350 新增：`mov pindirs`、`mov rxfifo[i], isr` / `mov osr, rxfifo[i]`（`.fifo txput/txget/putget`，CPU 用 `pio->rxf_putget[sm][i]`）、`irq/wait irq prev|next`、`wait jmppin`、IN_COUNT、8 個 IRQ flag 全可送系統中斷。`pico_generate_pio_header` 對 RP2350 自動 `-v 1`（不必寫 `.pio_version 1`）；手動跑 pioasm 才要加。

## 指令
| 指令 | 重點 |
|---|---|
| `jmp (cond) L` | `!x` `x--` `!y` `y--` `x!=y` `pin` `!osre`；`x--` 先判斷非 0 再減；絕對位址 |
| `wait p gpio/pin/irq/jmppin n` | gpio 絕對、pin = IN_BASE+n；`wait 1 irq` 會清 flag |
| `in src, n` | pins/x/y/null/isr/osr，取低 n bit |
| `out dst, n` | pins/x/y/null/pindirs/pc/isr/exec |
| `push (iffull) (noblock)` | ISR→RX，預設 block |
| `pull (ifempty) (noblock)` | TX→OSR；noblock 空時 = `mov osr, x` |
| `mov dst, (!\|::)src` | `!` 反相、`::` 位元反轉；src 可 status |
| `irq (set\|wait\|clear) n (rel)` | flag 0–7 |
| `set dst, v` | pins/x/y/pindirs，v=0–31 |

side-set 佔位：`.side_set 1`→delay ≤15；`1 opt`/`2`→≤7；`2 opt`/`3`→≤3；非 opt 每行都要寫 `side`。

## 初始化順序
```c
PIO pio; uint sm, off;
hard_assert(pio_claim_free_sm_and_add_program(&p_program, &pio, &sm, &off));
pio_sm_config c = p_program_get_default_config(off); // 含 wrap+sideset
sm_config_set_out_pins(&c, base, n);   // set_pins(base,n≤5)/in_pins(base)
sm_config_set_sideset_pins(&c, sbase); // jmp_pin(pin)
sm_config_set_out_shift(&c, true/*右移LSB先*/, true/*autopull*/, 32);
sm_config_set_in_shift(&c, false, true/*autopush*/, 32);
sm_config_set_fifo_join(&c, PIO_FIFO_JOIN_TX);
sm_config_set_clkdiv(&c, (float)clock_get_hz(clk_sys) / f_sm);
pio_gpio_init(pio, base);              // 每個輸出腳
pio_sm_set_consecutive_pindirs(pio, sm, base, n, true);
pio_sm_init(pio, sm, off, &c);         // 結束時為停用
pio_sm_set_enabled(pio, sm, true);
```
FIFO：`pio_sm_put_blocking/get_blocking`、`pio_sm_put/get`（不檢查）、`pio_sm_get_tx_fifo_level/rx`、`pio_sm_is_rx_fifo_empty`。
其他：`pio_add_program`（回 offset，<0 失敗）、`pio_claim_unused_sm(pio,true)`、`pio_sm_exec(pio,sm,pio_encode_*)`、`pio_sm_get_pc`（絕對位址）、`pio_sm_restart`、`pio_sm_clear_fifos`。
CMake：`pico_generate_pio_header(app ${CMAKE_CURRENT_LIST_DIR}/x.pio)` → `#include "x.pio.h"`；link `hardware_pio`。
DMA：dreq=`pio_get_dreq(pio,sm,true)`，write=`&pio->txf[sm]`，count 是筆數；RX 用 `&pio->rxf[sm]`、is_tx=false，先開 RX。

## demo echo
`out x,32` / `in x,32` / `push`：需 autopull，不要同時 autopush（會多推 0）；改成 autopush 刪 push → 每 word 2 cycle。

## 時序
- 每指令 1+delay cycle；`jmp x--` 迴圈跑 X+1 次。
- `div = f_sys / (bit_rate × cycles_per_bit)`；UART 8 cycle/bit、115200@150MHz → 162.76。
- 輸入同步器 2 cycle 延遲。

## 常見錯誤
1. 沒 `pio_gpio_init` 或 pindirs → 無輸出
2. 預設 SET/OUT count=0 → `set pins` 無效
3. 用 `pio_get_default_sm_config` 沒設 wrap（或沒加 offset）→ 跑飛
4. shift 方向/門檻錯 → 位元順序或寬度錯；右移+門檻<32 資料在高位
5. 沒 autopull 又沒 `pull` → 讀到殘值
6. 忘 `pio_sm_set_enabled`
7. `get_blocking` 但 SM 不 push → 卡死；先 put 全部再 get → 互卡
8. 指令記憶體滿（32 格）
9. side-set 吃掉 delay bit
10. `pio_encode_jmp` 沒加 offset
11. v1 指令組譯失敗：build 成 RP2040（沒設 `PICO_BOARD=pico2`）

## 除錯
PC：`pio_sm_get_pc-off`；FIFO level；`pio->fdebug`（TXSTALL/TXOVER/RXUNDER/RXSTALL，寫 1 清）；`pio->dbg_padout/padoe`；停用後 `pio_sm_exec` 注入指令。
