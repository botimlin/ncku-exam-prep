# 貼上卡：RP2350 DMA（pico-sdk hardware_dma）
> 用法：一次只複製一張卡（兩條分隔線之間），貼進對話，再在下面寫你的問題。每張 ≤ 1200 字元。
> 來源：full/domain/pico-dma.md、lite/domain/pico-dma.md（詳細版）｜最後更新 2026-11

---

【參考卡｜RP2350 DMA 1/8｜標準設定流程與 API】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
RP2350（Pico 2）：16 DMA channel、4 DMA IRQ（RP2040 只有 12/2）。pico-sdk 2.x，`#include "hardware/dma.h"`，CMake link `hardware_dma`（pico_stdlib 不含）。
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
- `dma_channel_configure(ch, &c, write_addr, read_addr, count, trigger)`：**第 3 參數 = 目的地，第 4 = 來源**（同 memcpy）。
- count 是「傳輸筆數」不是 bytes（bytes = 筆數 × 1/2/4）。
- trigger=false 時用 `dma_channel_start(ch)` 或 `dma_start_channel_mask(mask)` 啟動。
- 其他：`dma_channel_is_busy(ch)`、`dma_channel_set_read_addr/write_addr(ch,p,trig)`。
- fill（memset）：read_increment=false，src 指向 static pattern 變數。

---

【參考卡｜RP2350 DMA 2/8｜預設值與陷阱】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
RP2350（Pico 2）DMA：TRANS_COUNT 低 28 bit=次數、高 4 bit=MODE（RP2040 是 32 bit 全為次數）。
`dma_channel_get_default_config(ch)` 預設：
- read increment = **true**；write increment = **false**
- DREQ = `DREQ_FORCE`（全速）；chain_to = 自己（不 chain）
- data size = `DMA_SIZE_32`；ring 關
- bswap / irq_quiet / high_priority / sniff = false；enable = true
→ 記憶體到記憶體 memcpy 一定要再 `channel_config_set_write_increment(&c, true)`。
`DMA_SIZE_8/16/32` = 0/1/2（log2，不是 bytes 數）。
陷阱（依頻率）：
1. count 填成 bytes → 搬 2/4 倍、蓋掉後面記憶體。用 `count_of(arr)`（元素數），不要 `sizeof(arr)`。
2. 參數順序：dst 在前、src 在後。
3. 忘開 write_increment → 結果 dst[0] = src 最後一筆，其餘不變。
4. 位址須對齊 data size；硬體**不檢查**，未對齊 = 未定義。
5. buffer / pattern 是區域變數 → 返回後 stack 被重用。用 static/全域。
6. 通道 BUSY 時再觸發被**靜默忽略**；BUSY 時改位址會改到進行中的傳輸。
7. IRQ 沒 acknowledge → handler 不斷重入卡死。
8. count 必須 < 2^28，否則高位被當 MODE；`dma_encode_transfer_count(n)`（2.2+）只做遮罩，不會讓更大的 n 合法 → 拆段或 chain。
9. `dma_channel_unclaim` 不會停通道；先 `dma_channel_cleanup`。
10. 8/16-bit 寫 IO 暫存器會被複製到整個 32 bit。
11. 從 RP2040 搬程式：IRQ 號、DREQ 號、通道數不同，一律用巨集。

---

【參考卡｜RP2350 DMA 3/8｜練習 transfer engine → pico-sdk 對照】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
RP2350（Pico 2）：16 DMA channel（RP2040 12）。考前練習 section2-3 的 transfer engine 模仿 DMA，對照：
- `ENGINE_CHANNELS 4` → `NUM_DMA_CHANNELS`（16）；通道用完要還
- `engine_claim()` 滿回 -1 → `dma_claim_unused_channel(false)` 回 -1（`true` 則 panic）
- `.dst` / `.src` → `dma_channel_configure` 第 3 參數 write_addr / 第 4 參數 read_addr（dst 在前）
- `.count`（筆數）→ 第 5 參數，同樣是筆數；填 bytes = 搬 2/4 倍
- `.size = XFER_8/16/32`（值 1/2/4）→ `DMA_SIZE_8/16/32`（值 **0/1/2**）
- `.src_increment` → `channel_config_set_read_increment`，預設 true
- `.dst_increment` → `channel_config_set_write_increment`，預設 false
- `engine_configure`（BUSY 時拒絕）→ `dma_channel_configure`（硬體不擋）
- `engine_start` → `dma_channel_start(ch)` 或 configure 最後參數 `true`；BUSY 時觸發被忽略
- `engine_busy` / `engine_wait` → `dma_channel_is_busy` / `dma_channel_wait_for_finish_blocking`
- `engine_release` → `dma_channel_cleanup(ch); dma_channel_unclaim(ch);`（unclaim 不會停通道）
- 引擎檢查對齊 → 硬體不檢查、結果未定義，自己 `__attribute__((aligned(4)))`
- 引擎拒絕 count=0 → 硬體允許 0（立即完成，不搬資料）；配 CHAIN_TO 有 errata RP2350-E8（⚠️未查證）
- 複製 vs 填值只差 src_increment → 填值 = read_increment=false 指向 pattern 變數

---

【參考卡｜RP2350 DMA 4/8｜DMA 與 PIO / 週邊（DREQ）】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
RP2350（Pico 2）：3 個 PIO（pio0–2）；DREQ 編號與 RP2040 不同，用 `pio_get_dreq()`/巨集。
記憶體 → PIO TX FIFO：
```c
dma_channel_config c = dma_channel_get_default_config(ch);
channel_config_set_transfer_data_size(&c, DMA_SIZE_32);
channel_config_set_read_increment(&c, true);
channel_config_set_write_increment(&c, false);              // FIFO 位址固定
channel_config_set_dreq(&c, pio_get_dreq(pio, sm, true));   // TX DREQ
dma_channel_configure(ch, &c, &pio->txf[sm], buf, words, true);
```
PIO RX FIFO → 記憶體：read_increment=false、write_increment=true、dreq=`pio_get_dreq(pio, sm, false)`、`dma_channel_configure(ch, &c, buf, &pio->rxf[sm], words, true)`。
- 雙向（echo）：兩通道，**先啟動 RX 再 TX**，或 `dma_start_channel_mask` 同時啟動。
- DMA 服務某 FIFO 時 CPU 不可同時存取該 FIFO；不可讓兩個通道接同一 DREQ。
- UART `uart_get_dreq_num(u,is_tx)` 寫 `&uart_get_hw(u)->dr`；SPI `spi_get_dreq(s,is_tx)` TX+RX 兩通道；PWM `pwm_get_dreq(slice)` 寫 `&pwm_hw->slice[s].cc` 用 32-bit；ADC `DREQ_ADC`，先開 DMA 再 `adc_run(true)`。
- 定速：`dma_timer_set_fraction(t,num,den)`（clk_sys×num/den）+`dma_get_timer_dreq(t)`。
- DMA 不能存取 SIO（GPIO），改經 PIO。
- RP2350 DREQ 號：PIO0 TX 0-3、RX 4-7；PIO1 8-15；PIO2 16-23；ADC 48；FORCE 63。

---

【參考卡｜RP2350 DMA 5/8｜chaining、ping-pong、ring】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
RP2350（Pico 2）DMA；TRIGGER_SELF/ENDLESS 模式 RP2040 沒有。
- `channel_config_set_chain_to(&c, other)`：完成後觸發 other；設成自己=不 chain。兩通道都先 claim。
Ping-pong（A↔B 互 chain）：
```c
for (int i = 0; i < 2; i++) {
    dma_channel_config c = dma_channel_get_default_config(chs[i]);
    channel_config_set_transfer_data_size(&c, DMA_SIZE_32);
    channel_config_set_read_increment(&c, false);
    channel_config_set_write_increment(&c, true);
    channel_config_set_dreq(&c, pio_get_dreq(pio, sm, false));
    channel_config_set_chain_to(&c, chs[i ^ 1]);           // A→B、B→A
    dma_channel_configure(chs[i], &c, buf[i], &pio->rxf[sm], N, false);
}
```
接著開兩通道的 IRQ0、裝 DMA_IRQ_0 handler、`dma_channel_start(ch_a)`。ISR：ack 後 `dma_channel_set_write_addr(ch_a, buf[0], false)`（重設不觸發），B 同理；須在另一 buffer 填滿前處理完。兩通道同 DREQ 是否違規 ⚠️未驗證，出錯改 ring。
Ring + TRIGGER_SELF：buffer 對齊 `1<<bits`；`channel_config_set_ring(&c, true, 10)`（寫端 1024 bytes 繞回）；count = `dma_encode_transfer_count_with_self_trigger(128)`（2.2+；2.1 用 `(1u<<28)|128`），每 128 筆 IRQ 並自動重啟。
ENDLESS：`dma_encode_endless_transfer_count()`，只能 abort 停。ISR 快速重啟：`dma_channel_set_read_addr(ch, p, true)`。

---

【參考卡｜RP2350 DMA 6/8｜完成中斷（IRQ）】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
RP2350（Pico 2）：4 條 DMA IRQ `DMA_IRQ_0..3`（IRQ 號 10–13；RP2040 只有 2 條，號碼 11/12）→ 一律用巨集。
```c
static int ch;
static volatile bool done;
static void dma_irq0_handler(void) {
    if (dma_channel_get_irq0_status(ch)) {
        dma_channel_acknowledge_irq0(ch);   // 一定要清，否則 handler 會一直重入
        done = true;
    }
}
// setup：
dma_channel_configure(ch, &c, dst, src, N, false);
dma_channel_set_irq0_enabled(ch, true);                 // INTE0
irq_set_exclusive_handler(DMA_IRQ_0, dma_irq0_handler);
irq_set_enabled(DMA_IRQ_0, true);
dma_channel_start(ch);
// 主迴圈：while (!done) {...}  __compiler_memory_barrier(); 之後才讀 dst
```
- DMA_IRQ_2/3 只能用通用版：`dma_irqn_set_channel_enabled(2, ch, true)`、`irq_set_exclusive_handler(dma_get_irq_num(2), h)`；handler 內 `dma_irqn_get_channel_status(2, ch)` → `dma_irqn_acknowledge_channel(2, ch)`。
- 該 IRQ 已有 handler 時 exclusive 會出錯 → `irq_add_shared_handler` 或換另一條 DMA_IRQ_n。
- IRQ API 只作用在呼叫的那顆核；不要兩核都 enable 同一條 DMA IRQ。
- RP2350 只有 XIP cache，DMA↔SRAM 不需 cache flush；但旗標要 volatile、讀 buffer 前加 compiler barrier。

---

【參考卡｜RP2350 DMA 7/8｜除錯檢查清單】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
RP2350（Pico 2）DMA；以下 CTRL 位元是 RP2350 配置。`dma_hw->ch[ch].ctrl_trig`：EN=bit0、DATA_SIZE=bit3:2、INCR_READ=bit4、INCR_WRITE=bit6、CHAIN_TO=bit16:13、TREQ_SEL=bit22:17、IRQ_QUIET=bit23、BUSY=bit26、WRITE_ERROR=bit29、READ_ERROR=bit30。
1. ch ≥ 0？（claim(false) 可能回 -1）
2. `print_dma_ctrl(&dma_hw->ch[ch])` 只在 Debug build（未定義 NDEBUG）存在。
3. `transfer_count` 卡在非 0 且 BUSY=1 → DREQ 沒來：SM/週邊沒啟動、TX/RX 選錯、PIO 或 SM 號錯。
4. `dma_debug_hw->ch[ch].dbg_tcr` = reload 筆數 → 抓「填成 bytes」。
5. `read_addr/write_addr` 停在哪：(現值 − 起點) / 筆寬 = 完成筆數。
6. 只第一格對 → write_increment 沒開；整個 buffer 同一值 → read_increment 誤關；多寫 2/4 倍 → count 用了 bytes。
7. IRQ 沒進：INTE、`irq_set_enabled`、IRQ 號一致、IRQ_QUIET、`dma_hw->intr`。
8. IRQ 進來後卡死：沒 ack。
9. 第二次傳輸沒發生：仍 BUSY；CHAIN_TO 遇零長度（RP2350-E8 ⚠️未查證）；EN=0。
10. abort 後又自己跑（RP2350-E5）：先清 EN 與 CHAIN_TO 再 abort，或直接 `dma_channel_cleanup(ch)`。
11. READ/WRITE_ERROR（例如存取 SIO）：等 BUSY=0 後寫 1 清除才能重啟。
12. 資料偶爾錯：CPU 同時碰 DMA 的 FIFO、兩通道同 DREQ、buffer 是區域變數、讀前少 barrier。
13. ring 怪：buffer 沒對齊 `1<<bits`、write 參數選錯邊。
14. 編譯錯：`dma_channel_config_t`、`dma_encode_*`、`dma_channel_set_transfer_count` 是 2.2.0+。

---

【參考卡｜RP2350 DMA 8/8｜效能：何時不會更快、優化、CRC】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
RP2350（Pico 2）：整顆 DMA 每 clk_sys 最多 1 讀 + 1 寫（≤32 bit），多通道 round-robin 平分 → 一份 memcpy 拆多通道**不會更快**。150 MHz 理論上限約 600 MB/s。
不會比較快：
- 很短的傳輸（數十 bytes 等級，門檻 ⚠️需實測）：設定成本 > memcpy。
- 啟動後立刻 wait：應先讓 CPU 做不碰 dst 的工作，最後才 wait。
- `DMA_SIZE_8` 搬大量：頻寬只用 1/4 → 對齊後用 32-bit，頭尾零碎 bytes 給 CPU。
- CPU 與 DMA 搶同一 SRAM bank → 分開放（SRAM0–3 起 0x20000000、SRAM4–7 起 0x20040000、SRAM8/9 各 4 KB）。
- 讀 flash（XIP）/ APB 週邊：受 QSPI / APB 速度限制。
- 受週邊 DREQ 節流：好處是 CPU 空出來，不是更快。
- 需逐筆運算：DMA 只能搬、bswap、算 CRC/sum。
優化：重疊運算、ping-pong、control block + IRQ_QUIET 減中斷、ISR 只寫一個 trigger alias 重啟、config 算一次重用、`channel_config_set_bswap` 做位元組序。
量測：`time_us_64()` 包住 CPU 版與 DMA 版，各重複 100 次比較。
CRC32：config 也要 `channel_config_set_sniff_enable(&c, true)`（configure 會覆寫 CTRL）；`dma_sniffer_set_data_accumulator(0xFFFFFFFFu)`、`dma_sniffer_set_output_reverse_enabled(true)`、`dma_sniffer_enable(ch, DMA_SNIFF_CTRL_CALC_VALUE_CRC32R, true)`、DMA_SIZE_8，完成後 `dma_sniffer_get_data_accumulator() ^ 0xFFFFFFFFu`（同片段卡 PICO-SNIFF 1）。驗證 "123456789" → 0xCBF43926（沒上板測過）。
