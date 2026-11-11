# RP2350 DMA（pico-sdk hardware_dma）速查

> 用途：DMA 搬資料/餵 PIO/優化效能
> 適用版本：RP2350，pico-sdk 2.x（標 2.2+ 者 2.1 無）
> 來源：github.com/raspberrypi/pico-sdk（hardware_dma/dma.h、rp2350 regs）、datasheets.raspberrypi.com/rp2350/rp2350-datasheet.pdf §12.6、pico-examples/dma
> 最後更新 2026-11

## 硬體
- 16 通道（RP2040=12）；4 條 IRQ `DMA_IRQ_0..3`（RP2040 2 條）；4 個 pacing timer
- 整顆 DMA 每 cycle 1 讀+1 寫（≤32bit），多通道 round-robin 平分 → 拆多通道不加速
- 每通道：READ_ADDR、WRITE_ADDR、TRANS_COUNT、CTRL；寫 trigger alias 即啟動
- TRANS_COUNT=**筆數非 bytes**；低 28bit 次數，高 4bit MODE：0 NORMAL、1 TRIGGER_SELF（完成自動重啟）、0xF ENDLESS（RP2350 only）
- BUSY 時再觸發被靜默忽略；寫 0 到 trigger = null trigger
- 位址須對齊 size，硬體**不檢查**，未對齊=未定義
- DMA 不能存取 SIO(GPIO)→用 PIO
- 只有 XIP 有 cache；DMA↔SRAM 不需 cache 維護，但要 compiler barrier

## 標準流程
```c
int ch = dma_claim_unused_channel(true);
dma_channel_config c = dma_channel_get_default_config(ch);
channel_config_set_transfer_data_size(&c, DMA_SIZE_32); // 0/1/2 非 bytes
channel_config_set_read_increment(&c, true);   // 預設 true
channel_config_set_write_increment(&c, true);  // 預設 false!
channel_config_set_dreq(&c, DREQ_FORCE);       // 預設；週邊用其 DREQ
dma_channel_configure(ch, &c, dst, src, n_transfers, true); // 先 dst 後 src
dma_channel_wait_for_finish_blocking(ch);      // 含 barrier
dma_channel_cleanup(ch); dma_channel_unclaim(ch);
```
- fill：`read_increment=false`，src 指 static pattern
- PIO TX：dst=`&pio->txf[sm]`、write_inc=false、dreq=`pio_get_dreq(pio,sm,true)`
- PIO RX：src=`&pio->rxf[sm]`、read_inc=false、write_inc=true、dreq=`pio_get_dreq(pio,sm,false)`

## 其他 API
- `dma_channel_start(ch)`、`dma_start_channel_mask(m)`、`dma_channel_is_busy(ch)`
- `dma_channel_set_read_addr/write_addr(ch,p,trig)`、`dma_channel_set_trans_count`（2.2+ 名 `set_transfer_count`）
- `channel_config_set_chain_to(&c,other)`（自己=不 chain）、`_ring(&c,write,bits)`（buf 對齊 1<<bits）、`_bswap`、`_irq_quiet`、`_high_priority`、`_sniff_enable`
- IRQ：`dma_channel_set_irq0_enabled(ch,1); irq_set_exclusive_handler(DMA_IRQ_0,h); irq_set_enabled(DMA_IRQ_0,1);` handler 內 `dma_channel_acknowledge_irq0(ch)`；IRQ2/3 用 `dma_irqn_*`
- timer：`dma_timer_set_fraction(t,num,den)`（clk_sys*num/den）+`dma_get_timer_dreq(t)`
- CRC：`dma_sniffer_enable(ch,DMA_SNIFF_CTRL_CALC_VALUE_CRC32R,true)`+seed
- 2.2+：`dma_encode_transfer_count_with_self_trigger(n)`、`dma_encode_endless_transfer_count()`

## 對照練習引擎
| engine | pico-sdk |
|---|---|
| claim/release | claim_unused_channel / cleanup+unclaim |
| XFER_8/16/32=1/2/4 | DMA_SIZE_8/16/32=0/1/2 |
| src/dst_increment | read/write_increment |
| configure+start | configure(...,dst,src,count,trig) |
| busy/wait | is_busy / wait_for_finish_blocking |
| 檢查對齊/BUSY | 硬體不檢查 |

## 陷阱
1. count 填 bytes→溢寫 2/4 倍
2. 忘開 write_increment
3. 參數順序 dst 在前
4. buffer 是區域變數
5. IRQ 未 ack→重入卡死
6. CPU 同時碰 DMA 服務中的 FIFO、兩通道同 DREQ：禁止
7. 8/16bit 寫 IO 暫存器會複製到 32bit
8. E5：abort 前先清 EN+CHAIN_TO（cleanup 已做）
9. E8：零長度傳輸 CHAIN_TO 可能不觸發（⚠️未查證）
10. DREQ/IRQ 編號與 RP2040 不同，用巨集
11. sniff：config 也要 sniff_enable
12. count≥2^28 會變 MODE
13. unclaim 不會停通道

## 除錯
- `dma_hw->ch[ch].ctrl_trig`：EN b0、DATA_SIZE b3:2、TREQ b22:17、BUSY b26、R/W_ERROR b30/29
- transfer_count 卡住→DREQ 沒來（SM 沒跑/TX RX 選錯）
- `dma_debug_hw->ch[ch].dbg_tcr` 看 reload 筆數；read/write_addr 看進度
- 只第一格對→write_inc；IRQ 沒進→INTE/irq_set_enabled/IRQ_QUIET
- R/W_ERROR：等 BUSY=0 後寫 1 清除才能重啟
- `print_dma_ctrl(&dma_hw->ch[ch])`（僅 Debug build）

## 優化
- 先用 `time_us_64()` 量
- 啟動後 CPU 做別事再 wait；串流用 ping-pong(chain) 或 ring+TRIGGER_SELF
- ping-pong：A↔B 互 chain，ISR ack 後 `set_write_addr(ch,buf,false)` 重設不觸發
- ISR 快速重啟：`dma_channel_set_read_addr(ch,p,true)`（沿用 reload count）
- 對齊用 32bit；小量(門檻⚠️需實測)留給 CPU
- 多段用 control block+IRQ_QUIET 減中斷
- CPU/DMA buffer 分 bank（SRAM0-3 / 4-7 / 8,9）
