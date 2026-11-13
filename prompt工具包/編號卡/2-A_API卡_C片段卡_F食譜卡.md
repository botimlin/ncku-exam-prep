# 軍火庫：API 卡、片段卡、食譜卡

> 由 `model/gen_catalog.py` 自動產生，不要手改（改原始卡片後重跑）。
> 用法：**Ctrl-F 編號**（例 `A01-01`）→ 跳到「## 編號」那一行 → 複製下面那張卡（從【 到下一條 --- 之前）。
> 模型寫 `【要卡】編號` 時來這裡找；看不清楚就開 GitHub 的 Raw 檢視再 Ctrl-F。全部編號一覽：`00-編號總表.md`。
> 包法：卡片包在 `<<<資料 開始>>>`…`<<<資料 結束>>>` 裡，最後一行寫「繼續」；**提示卡（Q、G02）直接貼，不要包**。


---

## A01-01

【API卡｜DMA 1/7｜claim / unclaim / cleanup】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
```c
int dma_claim_unused_channel(bool required);
void dma_channel_claim(uint channel);
void dma_channel_unclaim(uint channel);
bool dma_channel_is_claimed(uint channel);
void dma_channel_cleanup(uint channel);
```
| 函式 | 回傳 / 行為 |
|---|---|
| `dma_claim_unused_channel(false)` | 通道號 0–15；沒空的回 `-1` |
| `dma_claim_unused_channel(true)` | 沒空的 → panic |
| `dma_channel_claim(ch)` | 已被 claim → panic |
| `dma_channel_unclaim(ch)` | 只標記歸還，**不會停通道** |
| `dma_channel_cleanup(ch)` | 關 IRQ、abort、清 IRQ 旗標 |
- `NUM_DMA_CHANNELS` = 16（RP2350）；RP2040 = 12。
- ✗ 錯：`uint ch = dma_claim_unused_channel(false);`（-1 變成很大的數）→ ✓ 對：`int ch = …; if (ch < 0) { <改用 CPU> }`
- ✗ 錯：通道還在跑就 `dma_channel_unclaim(ch);` → ✓ 對：`dma_channel_cleanup(ch); dma_channel_unclaim(ch);`
- ✗ 錯：`dma_channel_claim(0);` 寫死號碼 → ✓ 對：`dma_claim_unused_channel(true)`
- ✗ 錯：用完不還 → 幾次後沒通道 → ✓ 對：每個 claim 配一個 unclaim
前提：`#include "hardware/dma.h"`；CMake `target_link_libraries(<app> hardware_dma)`（`pico_stdlib` 不含）。
驗證：`printf("%d\n", ch);` 印 0–15。

---

## A01-02

【API卡｜DMA 2/7｜預設設定與 transfer size】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
```c
static inline dma_channel_config_t dma_channel_get_default_config(uint channel);
static inline void channel_config_set_transfer_data_size(dma_channel_config_t *c, dma_channel_transfer_size_t size);
typedef enum dma_channel_transfer_size {
    DMA_SIZE_8 = 0,    ///< Byte transfer (8 bits)
    DMA_SIZE_16 = 1,   ///< Half word transfer (16 bits)
    DMA_SIZE_32 = 2    ///< Word transfer (32 bits)
} dma_channel_transfer_size_t;
```
`dma_channel_get_default_config(ch)` 的預設（標頭註解表）：
| 設定 | 預設 |
|---|---|
| read increment | true |
| write increment | **false** |
| DREQ | `DREQ_FORCE`（63） |
| chain_to | 自己（= 不串接） |
| data size | `DMA_SIZE_32` |
| ring | write=false, size=0（關） |
| bswap / irq_quiet / high_priority / sniff | false |
| enable | true |
- 2.1.1：型別只有 `dma_channel_config`（沒有 `_t`，寫 `_t` → `unknown type name`）。寫 `dma_channel_config c` 兩版都能編。
- ✗ 錯：`set_transfer_data_size(&c, 4)` → ✓ 對：`DMA_SIZE_32`（值是 2）
- ✗ 錯：memcpy 沒開 write increment → ✓ 對：`channel_config_set_write_increment(&c, true);`
前提：`#include "hardware/dma.h"`；link `hardware_dma`。
驗證：memcpy 後 `memcmp(dst, src, n) == 0`。

---

## A01-03

【API卡｜DMA 3/7｜遞增與 DREQ（PIO/UART/SPI）】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
```c
static inline void channel_config_set_read_increment(dma_channel_config_t *c, bool incr);
static inline void channel_config_set_write_increment(dma_channel_config_t *c, bool incr);
static inline void channel_config_set_dreq(dma_channel_config_t *c, uint dreq);
static inline uint pio_get_dreq(PIO pio, uint sm, bool is_tx);
static inline uint uart_get_dreq_num(uart_inst_t *uart, bool is_tx);
static inline uint spi_get_dreq(spi_inst_t *spi, bool is_tx);
```
- `DREQ_FORCE` = 63 = 不節流。RP2350：PIO0 TX0=0、RX0=4、SPI0 TX=24、UART0 TX=28；用函式取，別寫死。

| 週邊 | dreq | FIFO 位址 |
|---|---|---|
| PIO TX | `pio_get_dreq(pio, sm, true)` | `&pio->txf[sm]` |
| PIO RX | `pio_get_dreq(pio, sm, false)` | `&pio->rxf[sm]` |
| UART0 TX | `uart_get_dreq_num(uart0, true)` | `&uart_get_hw(uart0)->dr` |
| SPI0 TX | `spi_get_dreq(spi0, true)` | `&spi_get_hw(spi0)->dr` |
- 記憶體→週邊：read_inc=true、write_inc=false、write_addr=FIFO；週邊→記憶體全部相反（read_addr=FIFO）。
- ✗ 錯：週邊留 `DREQ_FORCE` → 掉資料 → ✓ 對：設週邊 DREQ
- ✗ 錯：`is_tx` 反了 → 卡 BUSY → ✓ 對：送進週邊 true、收回 false
前提：`hardware/dma.h` + `pio.h`/`uart.h`/`spi.h`；link 對應 `hardware_*`。
驗證：BUSY 最後變 false。

---

## A01-04

【API卡｜DMA 4/7｜chain_to / ring / irq_quiet / bswap】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
```c
static inline void channel_config_set_chain_to(dma_channel_config_t *c, uint chain_to);
static inline void channel_config_set_ring(dma_channel_config_t *c, bool write, uint size_bits);
static inline void channel_config_set_irq_quiet(dma_channel_config_t *c, bool irq_quiet);
static inline void channel_config_set_bswap(dma_channel_config_t *c, bool bswap);
```
| 函式 | 意思 |
|---|---|
| `chain_to(&c, other)` | 完成後觸發 `other`；設成自己 = 關 |
| `ring(&c, write, bits)` | write=true 繞寫位址、false 繞讀位址；`1<<bits` bytes 繞回；bits 1–15，0 = 關 |
| `irq_quiet(&c, true)` | 每段完成不發 IRQ；寫 NULL 到 trigger 才發 |
| `bswap(&c, true)` | 8-bit 無效；16-bit 兩 byte 對調；32-bit 4 byte 反序 |
- ✗ 錯：`channel_config_set_ring(&c, true, 1024);` → ✓ 對：`channel_config_set_ring(&c, true, 10);`（填 bits）
- ✗ 錯：ring buffer 沒對齊 → ✓ 對：`static uint8_t buf[1024] __attribute__((aligned(1024)));`
- ✗ 錯：chain 到沒 claim 的通道 → ✓ 對：兩個都先 `dma_claim_unused_channel(true)`
- ✗ 錯：開 irq_quiet 又等每段 IRQ → ✓ 對：保持 false（預設）
前提：`#include "hardware/dma.h"`；link `hardware_dma`。
驗證：chain：只 start A，B 也搬完。

---

## A01-05

【API卡｜DMA 5/7｜dma_channel_configure 與 count 編碼】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
```c
static inline void dma_channel_configure(uint channel, const dma_channel_config_t *config, volatile void *write_addr,
                                         const volatile void *read_addr,
                                         uint32_t encoded_transfer_count, bool trigger);
static inline uint32_t dma_encode_transfer_count(uint transfer_count);
```
- 順序：`ch, &c, write_addr（目的 dst）, read_addr（來源 src）, count, trigger`。dst 在前，同 `memcpy`。
- count = **筆數**，不是 bytes（bytes = 筆數 × 1/2/4）。
- RP2350：低 28 bit = 筆數、高 4 bit = MODE → 包 `dma_encode_transfer_count(n)`，n < 2^28。
- 2.1.1：第 5 參數是 `uint transfer_count`；沒有 `dma_encode_transfer_count`（2.2.0 才有）→ `implicit declaration`。補法（`app_dma.c` 原樣）：
```c
#if PICO_SDK_VERSION_MAJOR == 2 && PICO_SDK_VERSION_MINOR < 2
static inline uint32_t dma_encode_transfer_count(uint n) { return n; }
#endif
```
- ✗ 錯：`dma_channel_configure(ch, &c, src, dst, n, true);` → ✓ 對：`dma_channel_configure(ch, &c, dst, src, n, true);`
- ✗ 錯：count 填 `sizeof(buf)` → ✓ 對：`count_of(buf)`（元素數）
前提：`#include "hardware/dma.h"`；link `hardware_dma`。
驗證：`memcmp(dst, src, sizeof src) == 0`。

---

## A01-06

【API卡｜DMA 6/7｜start / busy / wait / abort】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
```c
static inline void dma_channel_start(uint channel);
static inline void dma_start_channel_mask(uint32_t chan_mask);
inline static bool dma_channel_is_busy(uint channel);
inline static void dma_channel_wait_for_finish_blocking(uint channel);
static inline void dma_channel_abort(uint channel);
```
| 函式 | 行為 |
|---|---|
| `dma_channel_start(ch)` | = `dma_start_channel_mask(1u << ch)` |
| `dma_start_channel_mask(mask)` | bit0 = 通道 0…；多通道同時開始；mask 不可為 0 |
| `dma_channel_is_busy(ch)` | true = 還在搬 |
| `dma_channel_wait_for_finish_blocking(ch)` | 忙等到不 BUSY，含 `__compiler_memory_barrier()` |
| `dma_channel_abort(ch)` | 停止，等 BUSY=0 才回；可能多一次完成 IRQ |
- RP2350-E5：abort 前先清該通道（和被 chain 的通道）的 EN，否則會再被觸發；簡單做法 `dma_channel_cleanup(ch)`。
- ✗ 錯：`dma_start_channel_mask(ch);` → ✓ 對：`dma_start_channel_mask(1u << ch);`
- ✗ 錯：BUSY 時再 start → 被靜默忽略 → ✓ 對：先 wait 再 start
- ✗ 錯：start 後立刻 wait（沒省時間）→ ✓ 對：中間讓 CPU 做不碰 dst 的事
- ✗ 錯：沒 wait 就讀 dst → ✓ 對：讀前 `dma_channel_wait_for_finish_blocking(ch);`
前提：`#include "hardware/dma.h"`；link `hardware_dma`。
驗證：wait 返回後 `dma_channel_is_busy(ch) == false`。

---

## A01-07

【API卡｜DMA 7/7｜完成中斷 IRQ】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
```c
static inline void dma_channel_set_irq0_enabled(uint channel, bool enabled);
static inline void dma_irqn_set_channel_enabled(uint irq_index, uint channel, bool enabled);
static inline bool dma_channel_get_irq0_status(uint channel);
static inline void dma_channel_acknowledge_irq0(uint channel);
static inline void dma_irqn_acknowledge_channel(uint irq_index, uint channel);
static inline int dma_get_irq_num(uint irq_index);
```
- RP2350：`DMA_IRQ_0..3` = 10/11/12/13。RP2040 只有 2 條（11/12）→ 用巨集。
- IRQ 2/3：`dma_irqn_set_channel_enabled(2, ch, true)`、`dma_get_irq_num(2)`。
```c
static void dma_irq0_handler(void) {
    if (dma_channel_get_irq0_status(ch)) {
        dma_channel_acknowledge_irq0(ch);
        done = true;
    }
}
dma_channel_set_irq0_enabled(ch, true);
irq_set_exclusive_handler(DMA_IRQ_0, dma_irq0_handler);
irq_set_enabled(DMA_IRQ_0, true);
```
要換：`ch` = 全域 `static int`；`done` = `static volatile bool`。
- ✗ 錯：handler 沒 ack → 一直重入卡死 → ✓ 對：`dma_channel_acknowledge_irq0(ch)`
- ✗ 錯：`irq_set_enabled(10, true)` → ✓ 對：`DMA_IRQ_0`
前提：`hardware/dma.h`、`hardware/irq.h`；link `hardware_dma`。
驗證：`done` 變 true。

---

## A02-01

【API卡｜SNIFF 1/3｜sniffer 函式】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
```c
inline static void dma_sniffer_enable(uint channel, uint mode, bool force_channel_enable);
inline static void dma_sniffer_set_data_accumulator(uint32_t seed_value);
inline static uint32_t dma_sniffer_get_data_accumulator(void);
inline static void dma_sniffer_set_byte_swap_enabled(bool swap);
inline static void dma_sniffer_set_output_reverse_enabled(bool reverse);
inline static void dma_sniffer_set_output_invert_enabled(bool invert);
inline static void dma_sniffer_disable(void);
```
- 全晶片只有 1 個 sniffer；`disable` 把 SNIFF_CTRL 整個寫 0。
- `enable` 只改 DMACH / CALC / EN，不會清掉 reverse / invert / bswap 設定。
- reverse（位元反轉）、invert（取反）只改「讀出值」，不改計算。
- `force_channel_enable=true` 直接改通道 CTRL；但 `dma_channel_configure` 會覆寫 CTRL → config 也要 `channel_config_set_sniff_enable(&c, true)`。
- 2.1.1 簽名相同。
- ✗ 錯：`dma_sniffer_enable(DMA_SNIFF_CTRL_CALC_VALUE_CRC32, ch, true)` → ✓ 對：`dma_sniffer_enable(ch, DMA_SNIFF_CTRL_CALC_VALUE_CRC32, true)`
- ✗ 錯：傳輸開始後才寫初值 → ✓ 對：先 `dma_sniffer_set_data_accumulator(…)` 再觸發
- ✗ 錯：讀結果前沒等完成 → ✓ 對：先 `dma_channel_wait_for_finish_blocking(ch)`
前提：`#include "hardware/dma.h"`；link `hardware_dma`。
驗證：見 SNIFF 3/3。

---

## A02-02

【API卡｜SNIFF 2/3｜mode 值與 zlib CRC32 組合】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
| mode 名稱（`regs/dma.h`） | 值 | 計算 |
|---|---|---|
| `DMA_SNIFF_CTRL_CALC_VALUE_CRC32` | 0x0 | CRC-32（IEEE 802.3） |
| `DMA_SNIFF_CTRL_CALC_VALUE_CRC32R` | 0x1 | CRC-32，資料位元反轉 |
| `DMA_SNIFF_CTRL_CALC_VALUE_CRC16` | 0x2 | CRC-16-CCITT |
| `DMA_SNIFF_CTRL_CALC_VALUE_CRC16R` | 0x3 | CRC-16-CCITT，資料位元反轉 |
| `DMA_SNIFF_CTRL_CALC_VALUE_EVEN` | 0xe | XOR：1 的個數奇數 = 1 |
| `DMA_SNIFF_CTRL_CALC_VALUE_SUM` | 0xf | 32-bit 加總 |
zlib / Python `zlib.crc32` 相同結果的組合（`app_dma.c`）：
| 項目 | 設定 |
|---|---|
| 初值 | `dma_sniffer_set_data_accumulator(0xFFFFFFFFu)` |
| mode | `DMA_SNIFF_CTRL_CALC_VALUE_CRC32R` |
| 讀出反轉 | `dma_sniffer_set_output_reverse_enabled(true)` |
| 最後 | 軟體 `^ 0xFFFFFFFFu`（不用 invert） |
| 資料寬 | `DMA_SIZE_8`（任何長度都對） |
- 結果 = 0x649C2FD3（正確值位元反轉）→ 反轉設定反過來：寫 true 就改 false，沒寫就加 `dma_sniffer_set_output_reverse_enabled(true)`。
- 結果 = 0x340BC6D9（正確值取反）→ 最後的反相做了 0 次或 2 次：沒寫 `^ 0xFFFFFFFFu` 就加，寫了就拿掉。
- ✗ 錯：用 `CRC32`（不反轉）比 zlib → ✓ 對：`CRC32R`
前提：`#include "hardware/dma.h"`；link `hardware_dma`。
驗證：`"123456789"` 9 bytes → `0xCBF43926`。

---

## A02-03

【API卡｜SNIFF 3/3｜dma_crc32() 原樣（app_dma.c）】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
```c
static uint32_t dma_crc32(const void *p, uint32_t nbytes) {
    if (nbytes == 0) return 0;
    int ch = dma_claim_unused_channel(true);
    static volatile uint8_t sink;
    dma_channel_config c = dma_channel_get_default_config((uint)ch);
    channel_config_set_transfer_data_size(&c, DMA_SIZE_8);
    channel_config_set_read_increment(&c, true);
    channel_config_set_write_increment(&c, false);
    dma_sniffer_set_data_accumulator(0xFFFFFFFFu);
    dma_sniffer_set_output_reverse_enabled(true);
    dma_sniffer_enable((uint)ch, DMA_SNIFF_CTRL_CALC_VALUE_CRC32R, false);
    channel_config_set_sniff_enable(&c, true);
    dma_channel_configure((uint)ch, &c, &sink, p, dma_encode_transfer_count(nbytes), true);
    dma_channel_wait_for_finish_blocking((uint)ch);
    uint32_t crc = dma_sniffer_get_data_accumulator() ^ 0xFFFFFFFFu;
    dma_sniffer_disable();
    dma_channel_unclaim((uint)ch);
    return crc;
}
```
- ✗ 錯：刪掉 `channel_config_set_sniff_enable` → CRC 不算 → ✓ 對：保留
前提：`hardware/dma.h`；link `hardware_dma`；2.1.1 補 encode（DMA 5/7）。
驗證：`dma_crc32("123456789", 9) == 0xCBF43926`。⚠️未驗證：只編譯 + Python 模型，沒上板。

---

## A03-01

【API卡｜PIO 1/6｜載入程式、claim SM】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
```c
int pio_add_program(PIO pio, const pio_program_t *program);
void pio_remove_program(PIO pio, const pio_program_t *program, uint loaded_offset);
int pio_claim_unused_sm(PIO pio, bool required);
void pio_sm_unclaim(PIO pio, uint sm);
```
| 函式 | 回傳 |
|---|---|
| `pio_add_program(pio, &<prog>_program)` | offset；失敗 < 0（`PICO_ERROR_GENERIC` = -1） |
| `pio_claim_unused_sm(pio, false)` | SM 0–3；沒空的 -1 |
| `pio_claim_unused_sm(pio, true)` | 沒空的 → panic |
- `<prog>_program` 來自 `.pio` 經 pioasm 產生的 `<prog>.pio.h`。
- 指令記憶體每個 PIO 32 條；各 PIO 4 個 SM。
- ✗ 錯：`uint off = pio_add_program(…);` 不檢查 → ✓ 對：`int off = …; if (off < 0) <失敗>`
- ✗ 錯：claim SM 失敗後忘了移除程式 → ✓ 對：`pio_remove_program(pio, &<prog>_program, (uint)off);`
- ✗ 錯：remove 用錯 offset → ✓ 對：用 add 回傳的那個
前提：`#include "hardware/pio.h"`、`#include "<prog>.pio.h"`；link `hardware_pio`；CMake `pico_generate_pio_header(<app> ${CMAKE_CURRENT_LIST_DIR}/<prog>.pio)`。
驗證：offset ≥ 0、sm 0–3。2.1.1 簽名相同。

---

## A03-02

【API卡｜PIO 2/6｜一次找 PIO+SM+載入】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
```c
bool pio_claim_free_sm_and_add_program(const pio_program_t *program, PIO *pio, uint *sm, uint *offset);
bool pio_claim_free_sm_and_add_program_for_gpio_range(const pio_program_t *program, PIO *pio, uint *sm, uint *offset, uint gpio_base, uint gpio_count, bool set_gpio_base);
void pio_remove_program_and_unclaim_sm(const pio_program_t *program, PIO pio, uint sm, uint offset);
```
- 回 true = 成功；`pio`、`sm`、`offset` 由指標**帶回**（輸出參數）。
- `_for_gpio_range`：要用 GPIO `gpio_base` 起 `gpio_count` 支（RP2350B 的 GPIO 32–47 才需要）。
```c
PIO pio; uint sm, offset;
if (!pio_claim_free_sm_and_add_program(&<prog>_program, &pio, &sm, &offset)) { <失敗> }
// ... 用完 ...
pio_remove_program_and_unclaim_sm(&<prog>_program, pio, sm, offset);
```
- ✗ 錯：`pio_claim_free_sm_and_add_program(pio0, &<prog>_program, …)` → ✓ 對：program 在第 1 個
- ✗ 錯：傳 `pio`、`sm` 不加 `&` → ✓ 對：`&pio, &sm, &offset`
- ✗ 錯：用完只 unclaim → ✓ 對：`pio_remove_program_and_unclaim_sm(…)`
前提：`#include "hardware/pio.h"`；link `hardware_pio`。
驗證：回 true。2.1.1 簽名相同。

---

## A03-03

【API卡｜PIO 3/6｜sm_config 預設與腳位】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
```c
static inline pio_sm_config pio_get_default_sm_config(void);
static inline pio_sm_config <prog>_program_get_default_config(uint offset);
static inline void sm_config_set_out_pins(pio_sm_config *c, uint out_base, uint out_count);
static inline void sm_config_set_in_pins(pio_sm_config *c, uint in_base);
static inline void sm_config_set_set_pins(pio_sm_config *c, uint set_base, uint set_count);
static inline void sm_config_set_sideset_pins(pio_sm_config *c, uint sideset_base);
static inline void sm_config_set_jmp_pin(pio_sm_config *c, uint pin);
```
- `<prog>_program_get_default_config(offset)`（pioasm 產生）= 預設 + wrap + `.side_set`。**用這個**。
- 預設：clkdiv 1；wrap 0–31；in/out shift 右移、auto 關、門檻 32；OUT/SET pin 數 0（要自己呼叫 set_out_pins / set_set_pins）；sideset/jmp pin 0。
- `out_count` 0–32；`set_count` 0–5；in / sideset 只給起點。
- ✗ 錯：用 `pio_get_default_sm_config()` → wrap 不對 → ✓ 對：`<prog>_program_get_default_config(offset)`
- ✗ 錯：`sm_config_set_in_pins(&c, pin, 1)` → ✓ 對：`(&c, pin)` 兩個參數
- ✗ 錯：`sm_config_set_set_pins(&c, pin)` → ✓ 對：`(&c, base, count)`
前提：`#include "hardware/pio.h"`；link `hardware_pio`。
驗證：編譯過；腳位見 PIO 5/6。

---

## A03-04

【API卡｜PIO 4/6｜shift / fifo_join / clkdiv】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
```c
static inline void sm_config_set_in_shift(pio_sm_config *c, bool shift_right, bool autopush, uint push_threshold);
static inline void sm_config_set_out_shift(pio_sm_config *c, bool shift_right, bool autopull, uint pull_threshold);
static inline void sm_config_set_fifo_join(pio_sm_config *c, enum pio_fifo_join join);
static inline void sm_config_set_clkdiv(pio_sm_config *c, float div);
static inline void sm_config_set_clkdiv_int_frac(pio_sm_config *c, uint16_t div_int, uint8_t div_frac8);
```
| `enum pio_fifo_join` | 值 | 意思 |
|---|---|---|
| `PIO_FIFO_JOIN_NONE` | 0 | TX 4 + RX 4 |
| `PIO_FIFO_JOIN_TX` | 1 | TX 8，RX 關 |
| `PIO_FIFO_JOIN_RX` | 2 | RX 8，TX 關 |
| `…_TXGET`/`_TXPUT`/`_PUTGET` | 4/8/12 | 只有 RP2350 |
- shift：`(c, shift_right, auto, threshold)`；false = 左移 = MSB 先；threshold 1–32。
- clkdiv：1 = 全速；`div_frac8` 單位 1/256。
- ✗ 錯：`sm_config_set_out_shift(&c, true, 32, true)` → ✓ 對：`(&c, true, true, 32)`（只改參數順序）
- ✗ 錯：程式有 `push` 又開 autopush → ✓ 對：手動 push 時 autopush=false
- ✗ 錯：JOIN_TX 後還讀 RX → ✓ 對：要收就 `PIO_FIFO_JOIN_NONE`
前提：`#include "hardware/pio.h"`；link `hardware_pio`。
驗證：`echo.pio` 送值收回相同。

---

## A03-05

【API卡｜PIO 5/6｜GPIO、init、enable】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
```c
static inline void pio_gpio_init(PIO pio, uint pin);
int pio_sm_set_consecutive_pindirs(PIO pio, uint sm, uint pins_base, uint pin_count, bool is_out);
int pio_sm_init(PIO pio, uint sm, uint initial_pc, const pio_sm_config *config);
static inline void pio_sm_set_enabled(PIO pio, uint sm, bool enabled);
```
順序（`.pio` 的 `<prog>_program_init` 範本）：
```c
pio_sm_config c = <prog>_program_get_default_config(offset);
sm_config_set_out_pins(&c, <pin>, 1);
pio_gpio_init(pio, <pin>);
pio_sm_set_consecutive_pindirs(pio, sm, <pin>, 1, true);
pio_sm_init(pio, sm, offset, &c);
pio_sm_set_enabled(pio, sm, true);
```
要換：`<pin>` = GPIO 號；`offset` = `pio_add_program` 回傳值。
- `pio_sm_init`：停 SM、清 FIFO、套 config、PC 跳到 `initial_pc`；**結束時 SM 是停的**。回 `PICO_OK`(0) 或 < 0。
- `is_out`：true = 輸出、false = 輸入。
- ✗ 錯：init 完沒 `pio_sm_set_enabled(…, true)` → 不動 → ✓ 對：最後 enable
- ✗ 錯：`pio_sm_init(pio, sm, &c, offset)` → ✓ 對：`(pio, sm, offset, &c)`
- ✗ 錯：沒 `pio_gpio_init` → 腳不受 PIO 控制 → ✓ 對：每支腳都呼叫
前提：`#include "hardware/pio.h"`；link `hardware_pio`。
驗證：`pio_sm_init` 回 0；回環 / 示波器看到訊號。

---

## A03-06

【API卡｜PIO 6/6｜FIFO 存取、DREQ、pio0–2】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
```c
static inline void pio_sm_put(PIO pio, uint sm, uint32_t data);
static inline void pio_sm_put_blocking(PIO pio, uint sm, uint32_t data);
static inline uint32_t pio_sm_get(PIO pio, uint sm);
static inline uint32_t pio_sm_get_blocking(PIO pio, uint sm);
static inline bool pio_sm_is_rx_fifo_empty(PIO pio, uint sm);
static inline bool pio_sm_is_tx_fifo_full(PIO pio, uint sm);
static inline void pio_sm_clear_fifos(PIO pio, uint sm);
static inline uint pio_get_dreq(PIO pio, uint sm, bool is_tx);
```
- `put` / `get` 不檢查：TX 滿時寫被丟；RX 空時讀到未定義值。`_blocking` 版會等。
- `pio0` / `pio1` / `pio2`（型別 `PIO`）；`NUM_PIOS` = 3（RP2040 = 2）；每個 4 SM（`NUM_PIO_STATE_MACHINES`）。
- DMA：TX `&pio->txf[sm]`、RX `&pio->rxf[sm]`；DREQ `pio_get_dreq(pio, sm, true/false)`（DMA 3/7）。
- ✗ 錯：`pio_sm_get(pio, sm)` 沒先確認 → ✓ 對：`if (!pio_sm_is_rx_fifo_empty(pio, sm)) v = pio_sm_get(pio, sm);`
- ✗ 錯：`pio_sm_get_blocking` 等不會來的值 → 卡死 → ✓ 對：`is_rx_fifo_empty` + 逾時
- ✗ 錯：DMA 服務 FIFO 時 CPU 也讀寫它 → ✓ 對：二擇一
- ✗ 錯：RP2040 用 `pio2` → ✓ 對：只有 pico2（RP2350）有
前提：`#include "hardware/pio.h"`；link `hardware_pio`。
驗證：echo 程式 put 後 get 回相同值。

---

## A04-01

【API卡｜SYNC 1/5｜multicore 啟動與 FIFO】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
- `void multicore_launch_core1(void (*entry)(void))`：core1 跑 entry
- `void multicore_reset_core1(void)`：只在 core0 呼叫
- `void multicore_fifo_push_blocking(uint32_t data)`：滿就等
- `uint32_t multicore_fifo_pop_blocking(void)`：空就等
- `bool multicore_fifo_pop_timeout_us(uint64_t timeout_us, uint32_t *out)`：逾時回 false
- `bool multicore_fifo_rvalid(void)`：有資料可讀
- `bool multicore_fifo_wready(void)`：還有空位
- `void multicore_fifo_drain(void)`：清空讀端
FIFO 每方向 32 bit × **4 格**（RP2040 是 8）。launch 也用 FIFO → 傳資料優先用 `queue_t`。
```c
static void core1_entry(void) {          // 型別 void (*)(void)
    while (true) {
        uint32_t v = multicore_fifo_pop_blocking();
        multicore_fifo_push_blocking(v * 2u);
    }
}
    multicore_launch_core1(core1_entry); // 傳函式名，不加 ()
    multicore_fifo_push_blocking(21u);
    uint32_t r;
    if (multicore_fifo_pop_timeout_us(1000, &r)) { /* r == 42 */ }
```
- ✗ `multicore_launch_core1(core1_entry())` → ✓ `(core1_entry)`
- ✗ `pop_timeout_us(&r, 1000)` → ✓ `(1000, &r)`
- core1 stack 預設 0x800（2 KB）→ 大陣列用 static。
前提：`#include "pico/multicore.h"`；CMake `pico_stdlib pico_multicore`
驗證：push 21 → pop 得 42。

---

## A04-02

【API卡｜SYNC 2/5｜queue_t 跨核佇列】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
- `void queue_init(queue_t *q, uint element_size, uint element_count)`：先大小(bytes) 後個數；回 void
- `bool queue_try_add(queue_t *q, const void *data)`：滿 → false
- `bool queue_try_remove(queue_t *q, void *data)`：空 → false
- `bool queue_try_peek(queue_t *q, void *data)`：看、不取走
- `void queue_add_blocking(queue_t *q, const void *data)`：滿就等
- `void queue_remove_blocking(queue_t *q, void *data)`：空就等
- `uint queue_get_level(queue_t *q)`：目前幾個
```c
typedef struct { uint32_t id; int32_t val; } item_t;
static queue_t q;                          // 全域 / static
    queue_init(&q, sizeof(item_t), 8);     // (q, 元素大小 bytes, 元素個數)
    item_t a = { 1, 42 }, b;
    queue_add_blocking(&q, &a);            // 傳指標；內容 memcpy 進去
    if (queue_try_remove(&q, &b)) { }      // 空 → false
    uint n = queue_get_level(&q);          // 目前幾個
```
- ✗ `queue_init(&q, 8, sizeof(item_t))` → ✓ `(&q, sizeof(item_t), 8)`（反了不報錯）
- ✗ `queue_add_blocking(&q, a)` → ✓ `&a`
- ✗ ISR 裡 `_blocking` → ✓ 只用 `queue_try_*`
- `queue_init` 要在 launch core1 前。
前提：`#include "pico/util/queue.h"`；CMake `pico_stdlib`（含 pico_util）
驗證：add 1 筆後 `queue_get_level(&q)` == 1。

---

## A04-03

【API卡｜SYNC 3/5｜spinlock 與鎖號】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
- `int spin_lock_claim_unused(bool required)`：回 24–31；false 且沒有 → -1
- `spin_lock_t *spin_lock_init(uint lock_num)`：設為未上鎖，回指標
- `uint32_t spin_lock_blocking(spin_lock_t *lock)`：關本核 IRQ＋拿鎖，回舊 IRQ 狀態
- `void spin_unlock(spin_lock_t *lock, uint32_t saved_irq)`：放鎖＋還原 IRQ
鎖號 `PICO_SPINLOCK_ID_*`：
| 號碼 | 用途 |
|---|---|
| 0–13 | SDK 保留（IRQ=9、TIMER=10、HARDWARE_CLAIM=11、RAND=12、ATOMIC=13） |
| 14–15 | OS1 / OS2 |
| 16–23 | STRIPED_FIRST..LAST（queue/mutex/sem 共用） |
| 24–31 | CLAIM_FREE_FIRST..LAST（`spin_lock_claim_unused`、`critical_section_init` 用） |
```c
    int num = spin_lock_claim_unused(true);    // 24..31；true=沒有就 panic
    lk = spin_lock_init((uint)num);            // 回傳 spin_lock_t *
    uint32_t save = spin_lock_blocking(lk);    // 拿鎖 + 關本核 IRQ
    shared++;
    spin_unlock(lk, save);                     // 一定兩個參數
```
- ✗ `spin_unlock(lk)` → ✓ `spin_unlock(lk, save)`
- ✗ 自己挑號 `spin_lock_init(3)` → ✓ 用 `spin_lock_claim_unused(true)` 的號
- RP2350 預設 `PICO_USE_SW_SPIN_LOCKS`=1（erratum E2）；不要寫 `sio_hw->spinlock[]`。
前提：`#include "hardware/sync.h"`；CMake `pico_stdlib`
驗證：兩核各加 N 次，`shared` == 2N。

---

## A04-04

【API卡｜SYNC 4/5｜critical_section 與 mutex】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
- `void critical_section_init(critical_section_t *crit_sec)`：claim 一個 24–31 的鎖
- `void critical_section_enter_blocking(critical_section_t *crit_sec)`：關本核 IRQ＋鎖
- `void critical_section_exit(critical_section_t *crit_sec)`
- `void critical_section_deinit(critical_section_t *crit_sec)`：還鎖號，之後不能用
- `void mutex_init(mutex_t *mtx)`
- `void mutex_enter_blocking(mutex_t *mtx)`：ISR 不可用
- `bool mutex_try_enter(mutex_t *mtx, uint32_t *owner_out)`：owner_out 可 NULL；ISR 可用
- `void mutex_exit(mutex_t *mtx)`
```c
    critical_section_init(&cs);
    critical_section_enter_blocking(&cs);
    shared++;                                  // 極短
    critical_section_exit(&cs);
    mutex_init(&mtx);
    mutex_enter_blocking(&mtx);
    shared++;                                  // 可較長；不能在 ISR
    mutex_exit(&mtx);
```
- critical_section：跨核＋本核 ISR 都安全，臨界區極短；mutex：持有可較久，只給兩核主程式。
- ✗ 同一核連 `mutex_enter_blocking` 兩次 → deadlock；巢狀用 `recursive_mutex_t`
- ✗ 每個變數都 `critical_section_init` → 只有 8 個號，用完 panic
- 全域 mutex 可寫 `auto_init_mutex(name);` 免 init。
前提：`#include "pico/sync.h"`；CMake `pico_stdlib`
驗證：兩核各加 N 次，`shared` == 2N。

---

## A04-05

【API卡｜SYNC 5/5｜semaphore、關中斷、__dmb】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
- `void sem_init(semaphore_t *sem, int16_t initial_permits, int16_t max_permits)`：初始可用數、上限
- `void sem_acquire_blocking(semaphore_t *sem)`：等到 >0 再 −1
- `bool sem_acquire_timeout_ms(semaphore_t *sem, uint32_t timeout_ms)`
- `bool sem_release(semaphore_t *sem)`：+1；已到上限回 false；ISR 可呼叫
- `uint32_t save_and_disable_interrupts(void)`：只關本核，回舊狀態
- `void restore_interrupts(uint32_t status)`
- `void __dmb(void)`：記憶體屏障
```c
    sem_init(&sem, 0, 1);                      // (sem, 初始, 最大)
    bool ok = sem_release(&sem);               // 另一核 / ISR 通知；已滿回 false
    sem_acquire_blocking(&sem);                // 等到 permits > 0
    uint32_t s = save_and_disable_interrupts();// 只擋本核
    shared++;
    restore_interrupts(s);
    __dmb();                                   // 記憶體屏障
```
- ✗ `sem_wait` / `sem_post`（POSIX）→ ✓ `sem_acquire_blocking` / `sem_release`
- ✗ `sem_init(&sem, 1)` → ✓ 三個參數
- ✗ 用關中斷擋另一核 → 擋不住；跨核用 spinlock / critical_section
前提：`#include "pico/sync.h"`、`"hardware/sync.h"`；CMake `pico_stdlib`
驗證：core1 `sem_release` 後 core0 的 `sem_acquire_blocking` 返回。

---

## A05-01

【API卡｜PICO-IO 1/4｜計時 API】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
- `uint32_t time_us_32(void)`：開機後 µs；約 71.6 分（1h11m35s）繞回
- `uint64_t time_us_64(void)`：不會繞回
- `absolute_time_t get_absolute_time(void)`：2.x 預設就是 `uint64_t` µs
- `int64_t absolute_time_diff_us(absolute_time_t from, absolute_time_t to)`：= to − from
- `absolute_time_t make_timeout_time_ms(uint32_t ms)`：現在 + ms
- `bool time_reached(absolute_time_t t)`：到了 → true
- `void sleep_ms(uint32_t ms)`、`void sleep_us(uint64_t us)`：低功耗等；不可在 IRQ
- `void busy_wait_us(uint64_t delay_us)`、`void busy_wait_ms(uint32_t delay_ms)`：純忙等
```c
    absolute_time_t start = get_absolute_time();
    sleep_ms(10);                              // 可讓出 CPU（低功耗等）
    int64_t us = absolute_time_diff_us(start, get_absolute_time()); // to - from
    absolute_time_t dl = make_timeout_time_ms(500);
    while (!time_reached(dl)) { tight_loop_contents(); }
```
- ✗ `absolute_time_diff_us(end, start)` → 負數；✓ `(start, end)`
- ✗ IRQ handler 裡 `sleep_ms` → ✓ `busy_wait_us`
前提：`#include "pico/stdlib.h"`；CMake `pico_stdlib`
驗證：`sleep_ms(10)` 前後 diff ≈ 10000。

---

## A05-02

【API卡｜PICO-IO 2/4｜stdio 收發與錯誤碼】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
- `int getchar_timeout_us(uint32_t timeout_us)`：回 0–255 或 `PICO_ERROR_TIMEOUT`；0 = 不等
- `bool stdio_usb_connected(void)`：主機已開 port（DTR）
- `int stdio_put_string(const char *s, int len, bool newline, bool cr_translation)`：len=-1 → strlen；回 len
- `int putchar_raw(int c)`：1 byte，不轉 CRLF
- `void stdio_flush(void)`
錯誤碼：`PICO_OK`=0、`PICO_ERROR_GENERIC`=-1、`PICO_ERROR_TIMEOUT`=**-2**、`PICO_ERROR_NO_DATA`=-3。
```c
    while (!stdio_usb_connected()) sleep_ms(50);   // 等主機開 port（DTR）
    int c = getchar_timeout_us(0);                 // 0 = 不等
    if (c != PICO_ERROR_TIMEOUT) {                 // PICO_ERROR_TIMEOUT = -2
        uint8_t b = (uint8_t)c;                    // 0..255
        (void)b;
    }
    static const char pkt[] = { 0x01, 0x0A, 0x00 };
    stdio_put_string(pkt, 3, false, false);        // (s, len, newline, cr_translation)
    stdio_flush();
```
- ✗ `c == EOF` / `c == -1` 當沒資料 → ✓ `c == PICO_ERROR_TIMEOUT`
- ✗ printf 送二進位（0x0A 變 0D 0A）→ ✓ `stdio_put_string(buf, n, false, false)`
前提：`#include "pico/stdlib.h"`、`"pico/stdio_usb.h"`；CMake `pico_stdlib`＋`pico_enable_stdio_usb(app 1)`
驗證：電腦收到 `01 0a 00`（沒有 0d）。

---

## A05-03

【API卡｜PICO-IO 3/4｜GPIO 與板載 LED】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
- `void gpio_init(uint gpio)`：設 SIO 功能、輸入、輸出值 0
- `void gpio_set_dir(uint gpio, bool out)`：`GPIO_OUT`=1、`GPIO_IN`=0
- `void gpio_put(uint gpio, bool value)`
- `bool gpio_get(uint gpio)`
- `void gpio_pull_up(uint gpio)`
`PICO_DEFAULT_LED_PIN` = **25**（pico、pico2）；`pico2_w` 沒定義（LED 在無線晶片上）。
```c
    gpio_init(PICO_DEFAULT_LED_PIN);               // pico2 = 25
    gpio_set_dir(PICO_DEFAULT_LED_PIN, GPIO_OUT);  // GPIO_OUT=1, GPIO_IN=0
    gpio_put(PICO_DEFAULT_LED_PIN, 1);             // 1 亮 / 0 暗
    gpio_init(IN_PIN);
    gpio_set_dir(IN_PIN, GPIO_IN);
    gpio_pull_up(IN_PIN);
    bool level = gpio_get(IN_PIN);
```
要換：`IN_PIN` = 你的輸入腳號（例 15）。
- ✗ 沒 `gpio_init` 就 `gpio_put` → 腳不動；✓ init → set_dir → put
- ✗ `gpio_set_dir(pin, 0)` 想當輸出 → 0 是輸入；✓ `GPIO_OUT`
前提：`#include "pico/stdlib.h"`（含 hardware/gpio.h）；CMake `pico_stdlib`
驗證：板載 LED 亮。

---

## A05-04

【API卡｜PICO-IO 4/4｜標頭 → CMake 函式庫名】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
pico-sdk 2.2.0、pico2 實測：只連 `pico_stdlib pico_multicore` 就能編譯連結本檔 SYNC、PICO-IO 全部函式。
| 標頭 | CMake |
|---|---|
| `pico/stdlib.h`、`pico/time.h`、`hardware/timer.h`、`hardware/gpio.h` | `pico_stdlib` |
| `pico/util/queue.h` | `pico_stdlib`（含 `pico_util`） |
| `pico/sync.h`、`hardware/sync.h` | `pico_stdlib`（含 `pico_sync`、`hardware_sync`） |
| `pico/multicore.h` | `pico_multicore`（要另外加） |
| `pico/stdio_usb.h` | `pico_enable_stdio_usb(app 1)` |
| `rcl/…`、`rclc/…`、`rmw_microros/…`、`std_msgs/…` | `microros` |
```cmake
target_link_libraries(app pico_stdlib pico_multicore microros)
target_include_directories(app PUBLIC libmicroros/include)
pico_enable_stdio_usb(app 1)
pico_enable_stdio_uart(app 0)
```
- micro-ROS 另要 `link_directories(libmicroros)`（放在 `add_executable` 前）。
- ✗ 寫 `hardware_multicore` / `pico_queue` → 不存在；✓ `pico_multicore`，queue 在 `pico_stdlib`
- ✗ 漏 `pico_multicore` → 連結錯 `undefined reference to 'multicore_launch_core1'`（標頭照樣找得到）
前提：`pico_sdk_init()` 之後寫
驗證：`make` 0 錯誤，產生 `app.uf2`。

---

## A06-01

【API卡｜UROS 1/6｜support、node 初始化】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
micro-ROS jazzy，全部回傳 `rcl_ret_t`：`RCL_RET_OK`=0、`RCL_RET_ERROR`=1、`RCL_RET_TIMEOUT`=2。
- `rcl_get_default_allocator()`：巨集，回 `rcl_allocator_t`
- `rclc_support_init(rclc_support_t *support, int argc, char const * const *argv, rcl_allocator_t *allocator)`
- `rclc_node_init_default(rcl_node_t *node, const char *name, const char *namespace_, rclc_support_t *support)`
```c
#define RCCHECK(fn) { rcl_ret_t rc_ = (fn); if (rc_ != RCL_RET_OK) error_loop(); }
rclc_support_t support;
rcl_node_t node;
rcl_allocator_t allocator;
    allocator = rcl_get_default_allocator();
    RCCHECK(rclc_support_init(&support, 0, NULL, &allocator));
    RCCHECK(rclc_node_init_default(&node, "compute_node", "pico0", &support));
```
要換：`"compute_node"` = node 名；`"pico0"` = namespace（每塊板子不同；不用就給 `""`）。
- `RCCHECK` 要自己 `#define`（rclc.h 沒有）；`error_loop()` 自己寫（LED 快閃）；物件放全域。
- ✗ `rclc_support_init(&support, &allocator)` → ✓ 四個參數 `(&support, 0, NULL, &allocator)`
- ✗ `rclc_node_init_default(&node, "n", &support)` → ✓ namespace 在 support 前面
前提：`#include <rcl/rcl.h>`、`<rclc/rclc.h>`
驗證：`ros2 node list` 看到 `/pico0/compute_node`。

---

## A06-02

【API卡｜UROS 2/6｜publisher、subscription、type support】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
- `rclc_publisher_init_default(rcl_publisher_t *publisher, const rcl_node_t *node, const rosidl_message_type_support_t *type_support, const char *topic_name)`
- `rclc_publisher_init_best_effort(…同上四個…)`
- `rclc_subscription_init_default(rcl_subscription_t *subscription, rcl_node_t *node, const rosidl_message_type_support_t *type_support, const char *topic_name)`
- `rclc_subscription_init_best_effort(…同上四個…)`
- `ROSIDL_GET_MSG_TYPE_SUPPORT(套件, msg, 型別)`：三個參數
```c
    const rosidl_message_type_support_t *ts =
        ROSIDL_GET_MSG_TYPE_SUPPORT(std_msgs, msg, Int32MultiArray);
    RCCHECK(rclc_publisher_init_default(&pub, &node, ts, "output"));
    RCCHECK(rclc_subscription_init_default(&sub, &node, ts, "input"));
```
- `_default` = RELIABLE；`_best_effort` = BEST_EFFORT；電腦端 QoS 要配（RELIABLE 訂閱收不到 BEST_EFFORT 發佈）。
- namespace `pico0` + `"input"` → `/pico0/input`。
- ✗ `ROSIDL_GET_MSG_TYPE_SUPPORT(std_msgs, Int32MultiArray)` → ✓ `(std_msgs, msg, Int32MultiArray)`
前提：`#include <std_msgs/msg/int32_multi_array.h>`（型別名 → 小寫底線檔名）
驗證：`ros2 topic info -v /pico0/input` 看 QoS。

---

## A06-03

【API卡｜UROS 3/6｜timer 與 executor】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
- `rclc_timer_init_default2(rcl_timer_t *timer, rclc_support_t *support, const uint64_t timeout_ns, const rcl_timer_callback_t callback, bool autostart)`
- `rclc_executor_init(rclc_executor_t *executor, rcl_context_t *context, const size_t number_of_handles, const rcl_allocator_t *allocator)`
- `rclc_executor_spin_some(rclc_executor_t *executor, const uint64_t timeout_ns)`
- `RCL_MS_TO_NS(ms)` = ms×1000000LL
```c
    RCCHECK(rclc_timer_init_default2(&timer, &support, RCL_MS_TO_NS(100), timer_cb, true));
    executor = rclc_executor_get_zero_initialized_executor();
    RCCHECK(rclc_executor_init(&executor, &support.context, 3, &allocator)); // 1 timer + 2 sub
    RCCHECK(rclc_executor_add_timer(&executor, &timer));
        rclc_executor_spin_some(&executor, RCL_MS_TO_NS(1));
```
- handles 數 = timer 數 + sub 數；不夠 → add 回錯誤。
- spin_some 沒資料回 `RCL_RET_TIMEOUT`（正常）。
- ✗ `rclc_timer_init_default(...)`（4 參數）→ deprecated warning；✓ `_default2(..., true)`
- ✗ `rclc_executor_init(&executor, &support, …)` → ✓ `&support.context`
前提：`#include <rclc/executor.h>`（rclc.h 不含）
驗證：`ros2 topic hz` ≈ 10。

---

## A06-04

【API卡｜UROS 4/6｜subscription callback 與 rcl_publish】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
- `rclc_executor_add_subscription(rclc_executor_t *executor, rcl_subscription_t *subscription, void *msg, rclc_subscription_callback_t callback, rclc_executor_handle_invocation_t invocation)`
- invocation：`ON_NEW_DATA`=0（有新資料才叫）、`ALWAYS`=1（沒資料也叫）
- `rcl_publish(const rcl_publisher_t *publisher, const void *ros_message, rmw_publisher_allocation_t *allocation)`
- sub callback：`void (*)(const void *)`；timer callback：`void (*)(rcl_timer_t *, int64_t)`
```c
void sub_cb(const void *msgin) {                       // rclc_subscription_callback_t
    const std_msgs__msg__Int32MultiArray *m = (const std_msgs__msg__Int32MultiArray *)msgin;
    if (m->data.size == 0) return;                     // 太長(>capacity)也會是 0
    RCSOFTCHECK(rcl_publish(&pub, &msg_out, NULL));    // 第 3 參數 NULL
}
    RCCHECK(rclc_executor_add_subscription(&executor, &sub, &msg_in, &sub_cb, ON_NEW_DATA));
```
- `msg` = 收件用全域變數；`RCSOFTCHECK` 自訂。
- ✗ `rcl_publish(&pub, &msg)` → ✓ `(&pub, &msg, NULL)`；回傳值不接會 warning
- ✗ `void cb(void *m)` → warning；✓ `const void *`
前提：`#include <rclc/executor.h>`
驗證：pub `/pico0/input` → `/pico0/output` 有回。

---

## A06-05

【API卡｜UROS 5/6｜custom transport 與 ping agent】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
- `rmw_ret_t rmw_uros_set_custom_transport(bool framing, void *args, open_custom_func open_cb, close_custom_func close_cb, write_custom_func write_cb, read_custom_func read_cb)`：順序 open、close、write、read
- `rmw_ret_t rmw_uros_ping_agent(const int timeout_ms, const uint8_t attempts)`：agent 在 → `RMW_RET_OK`(0)，不在 → `RMW_RET_ERROR`(1)
官方 `pico_uart_transports.h` 提供四個函式：`pico_serial_transport_open` / `_close` / `_write` / `_read`（直接傳名字，不用自己寫）。
```c
    rmw_uros_set_custom_transport(true, NULL,
        pico_serial_transport_open, pico_serial_transport_close,
        pico_serial_transport_write, pico_serial_transport_read);
    while (rmw_uros_ping_agent(1000, 1) != RMW_RET_OK) { tight_loop_contents(); }
```
- framing = `true`（序列埠要 framing）。open 裡會呼叫 `stdio_init_all()`。
- 順序：set_custom_transport → ping 到 OK → `rclc_support_init`。
- USB 被 agent 佔用 → 不要 printf（會混進封包）。
前提：`#include <rmw_microros/rmw_microros.h>`、`"pico_uart_transports.h"`；`add_executable` 要加 `pico_uart_transport.c`
驗證：agent 顯示 session established。

---

## A06-06

【API卡｜UROS 6/6｜Int32MultiArray 的 sequence 欄位】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
`std_msgs__msg__Int32MultiArray`：
- `.data`：`rosidl_runtime_c__int32__Sequence` = `{ int32_t *data; size_t size; size_t capacity; }`（size = 有效個數）
- `.layout.dim`（同上三欄）、`.layout.data_offset`
```c
#define MAX_LEN 400
std_msgs__msg__Int32MultiArray msg_in, msg_out;
static int32_t in_buf[MAX_LEN], out_buf[MAX_LEN];
    msg_in.data.data = in_buf;   msg_in.data.capacity = MAX_LEN;  msg_in.data.size = 0;
    msg_out.data.data = out_buf; msg_out.data.capacity = MAX_LEN; msg_out.data.size = 0;
    msg_in.layout.dim.data = NULL;  msg_in.layout.dim.capacity = 0;  msg_in.layout.dim.size = 0;
    msg_out.layout.dim.data = NULL; msg_out.layout.dim.capacity = 0; msg_out.layout.dim.size = 0;
    msg_in.layout.data_offset = 0;  msg_out.layout.data_offset = 0;
    msg_out.data.size = n;                             // size ≤ capacity
```
要換：`MAX_LEN` = 最大元素數；`n` = 發幾個。
- 不 malloc：沒設 `.data/.capacity` → 收不到。
- 收到 > capacity 個 → callback 照叫、`size`=0。
- ✗ `capacity = sizeof(in_buf)` → ✓ `MAX_LEN`（元素數，非 bytes）
- dim capacity=0 → 電腦端別填 dim。
前提：`#include <std_msgs/msg/int32_multi_array.h>`
驗證：pub `{data: [1,2,3]}` → size==3。

---

## A07-01

【API卡｜HOST-PY 1/4｜rclpy：publisher、subscription、timer、參數】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
從 repo 範本 `node_template.py`、`serial_bridge.py`、`host_driver.py` 原樣複製（這次沒實跑）。
- `self.create_publisher(msg_type, topic, qos)`
- `self.create_subscription(msg_type, topic, callback, qos)`
- `self.create_timer(period_sec, callback)`：秒（float）
- `self.declare_parameter(name, default)`；`self.get_parameter(name).value`
```python
        self.declare_parameter("in_topic", "/number")    # TODO(改這裡) 輸入 topic
        in_topic = self.get_parameter("in_topic").value
        self.pub = self.create_publisher(Int32, out_topic, QOS)
        self.sub = self.create_subscription(Int32, in_topic, self.on_msg, QOS)
            self.timer = self.create_timer(period, self.on_timer)
```
- qos 也可直接寫 `10`（serial_bridge.py）；多個 sub 共用 callback：`lambda msg, b=i: self.on_result(b, msg)`（host_driver.py）。
- ✗ `create_subscription(Int32, cb, topic)` → ✓ `(Int32, topic, cb, qos)`
- ✗ `create_timer(100, cb)` 想要 100 ms → ✓ `create_timer(0.1, cb)`
- ✗ `get_parameter(name)` 直接當值 → ✓ `.value`
前提：`import rclpy`、`from rclpy.node import Node`、`from std_msgs.msg import Int32`
驗證：pub `/number` 21 → `/double` 得 42。

---

## A07-02

【API卡｜HOST-PY 2/4｜rclpy：QoS 與 init / spin / shutdown】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
來源：repo 範本原樣複製（這次沒實跑）。
```python
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
QOS = QoSProfile(
    depth=10,
    history=HistoryPolicy.KEEP_LAST,
    reliability=ReliabilityPolicy.RELIABLE,   # TODO(改這裡) 收不到感測器資料時改 BEST_EFFORT
    durability=DurabilityPolicy.VOLATILE,     # TRANSIENT_LOCAL = 晚加入的訂閱者也拿得到最後一筆
)
def main():
    rclpy.init()
    node = Processor()
    try:
        rclpy.spin(node)          # 一直等 callback；沒有 spin 的話 callback 永遠不會被呼叫!
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()
```
- 自己控迴圈：`rclpy.spin_once(self, timeout_sec=0.001)`；條件 `rclpy.ok()`；結尾 `rclpy.shutdown()`（host_driver.py）。
- `ReliabilityPolicy.BEST_EFFORT`、`DurabilityPolicy.TRANSIENT_LOCAL`：範本只在註解出現 ⚠️未驗證
- `from rclpy.qos import qos_profile_sensor_data`（BEST_EFFORT、depth 5）⚠️未驗證
- ✗ 沒 `rclpy.spin` → callback 永遠不跑
前提：`from rclpy.executors import ExternalShutdownException`
驗證：Ctrl+C 結束沒有 traceback。

---

## A07-03

【API卡｜HOST-PY 3/4｜pyserial】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
pyserial 3.5（inspect＋pty 實跑）：
- `serial.Serial(port=None, baudrate=9600, bytesize=8, parity='N', stopbits=1, timeout=None, ...)`：timeout 單位秒；None = 永遠等
- `ser.read(size=1)` → bytes；逾時回 `b''`（不丟例外）
- `ser.write(data)` → int（寫了幾 byte）
- `ser.in_waiting`：屬性，不加 `()`
- `ser.reset_input_buffer()`：清掉沒讀的舊資料
- `ser.close()`
- `serial.SerialException`：開不了 / 拔線；是 `OSError` 子類
- `serial.tools.list_ports.comports()`：每項有 `.device`、`.description`
```python
ser = serial.Serial(name, 115200, timeout=0.05)   # port, baudrate, timeout=秒
print("read timeout ->", repr(ser.read(4)))         # 沒資料 → b''
print("read(ser.in_waiting or 1) ->", ser.read(ser.in_waiting or 1))
print("write ->", ser.write(b"\x0a\x0d"))           # 回傳寫了幾 byte
ser.reset_input_buffer()
for p in serial.tools.list_ports.comports():
    print(p.device, p.description)
```
要換：`name` = `/dev/ttyACM0` 等。
- ✗ `ser.in_waiting()` → ✓ `ser.in_waiting`
- ✗ `ser.write("abc")`（str）→ ✓ `b"abc"`
- ✗ `timeout=None` → 沒資料就卡死；✓ `timeout=0.05` 自己迴圈
- USB CDC 不看 baudrate。
前提：`import serial`、`import serial.tools.list_ports`
驗證：沒資料時 `read` 回 `b''`。

---

## A07-04

【API卡｜HOST-PY 4/4｜struct 格式字元與 array】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
Python 3.13 實跑：
| 字元 | 意思 | bytes |
|---|---|---|
| `<` / `>` | 小端 / 大端，無對齊（Pico 是小端） | – |
| `B` / `H` / `I` | uint8 / uint16 / uint32 | 1 / 2 / 4 |
| `i` / `f` | int32 / float32 | 4 / 4 |
不寫 `<` = 本機對齊：`calcsize("BI")`=8、`calcsize("<BI")`=5。
```python
print(struct.pack("<I", 1).hex(), struct.pack(">I", 1).hex())
print(struct.pack("<BBH", 0x10, 7, 300).hex())
(v,) = struct.unpack("<I", b"\x2a\x00\x00\x00"); print(v)
print(struct.unpack_from("<H", b"\xaa\x55\x03\x00", 2))
n = 3; print(struct.pack(f"<{n}I", 1, 2, 3).hex())
a = array.array("i", [1, -1, 300])
print(a.itemsize, a.tobytes().hex(), sys.byteorder)
```
輸出：`01000000 00000001`、`10072c01`、`42`、`(3,)`、`010000000200000003000000`、`4 01000000ffffffff2c010000 little`
- `unpack` 永遠回 tuple → ✓ `(v,) = ...`
- ✗ `pack("<B", 256)`、`pack("<I", -1)` → `struct.error`；負數用 `i`
- ✗ `unpack("<I", 2 bytes)` → `struct.error: unpack requires a buffer of 4 bytes`
- `array('i').tobytes()` 用本機序（x86/ARM 都 little）= 小端 int32。
前提：`import struct, array, sys`
驗證：輸出跟上面一樣。

---

## C01-01

【片段卡｜PICO-DMA 1/5｜CPU 複製迴圈 → DMA】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
原本：`for (i = 0; i < n; i++) dst[i] = src[i];`
```c
static int dma_copy32(uint32_t *dst, const uint32_t *src, uint32_t n) {
    if (n == 0) return 0;  // 0 筆：不啟動
    int ch = dma_claim_unused_channel(false);  // false = 沒通道回 -1
    if (ch < 0) return -1;  // 改用 CPU
    dma_channel_config c = dma_channel_get_default_config((uint)ch);
    channel_config_set_transfer_data_size(&c, DMA_SIZE_32);
    channel_config_set_read_increment(&c, true);
    channel_config_set_write_increment(&c, true);  // 預設 false！
    dma_channel_configure((uint)ch, &c, dst, src,  // dst 在前、src 在後
                          dma_encode_transfer_count(n), true);  // true = 立刻開始
    dma_channel_wait_for_finish_blocking((uint)ch);
    dma_channel_unclaim((uint)ch);  // 一定要還
    return 0;
}
// 呼叫：dma_copy32(<dst>, <src>, <n>);
```
要換：`<dst>`/`<src>` = `uint32_t` 陣列；`<n>` = 元素個數（筆數）。
✗ 錯：`n = sizeof(arr)` → ✓ 對：`n = count_of(arr)`（bytes 會搬 4 倍、蓋掉後面記憶體）
前提：`#include "pico/stdlib.h"`、`#include "hardware/dma.h"`；CMake `target_link_libraries(<app> pico_stdlib hardware_dma)`。2.1.x 無 `dma_encode_transfer_count` → 直接傳 `n`。
驗證：搬完 `memcmp(dst, src, n * 4) == 0`。

---

## C01-02

【片段卡｜PICO-DMA 2/5｜填值迴圈 → DMA fill】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
原本：`for (i = 0; i < n; i++) dst[i] = value;`（`memset` 只能填 1 byte 的值）
```c
static int dma_fill32(uint32_t *dst, uint32_t value, uint32_t n) {
    static uint32_t v;  v = value;  // 來源要活到 DMA 搬完 → static
    if (n == 0) return 0;
    int ch = dma_claim_unused_channel(false);
    if (ch < 0) return -1;
    dma_channel_config c = dma_channel_get_default_config((uint)ch);
    channel_config_set_transfer_data_size(&c, DMA_SIZE_32);
    channel_config_set_read_increment(&c, false);  // 讀位址不動 = fill
    channel_config_set_write_increment(&c, true);
    dma_channel_configure((uint)ch, &c, dst, &v,
                          dma_encode_transfer_count(n), true);
    dma_channel_wait_for_finish_blocking((uint)ch);
    dma_channel_unclaim((uint)ch);
    return 0;
}
// 呼叫：dma_fill32(<dst>, <0xDEADBEEF>, <n>);
```
要換：`<dst>` = `uint32_t` 陣列；`<0xDEADBEEF>` = 要填的值；`<n>` = 元素個數。
✗ 錯：`v` 是一般區域變數 → ✓ 對：`static`（函式返回後 stack 會被蓋）
前提：`#include "pico/stdlib.h"`、`#include "hardware/dma.h"`；CMake `target_link_libraries(<app> pico_stdlib hardware_dma)`。
驗證：`dst[0]` 和 `dst[n - 1]` 都 == 填的值。

---

## C01-03

【片段卡｜PICO-DMA 3/5｜開始後先不等：CPU 同時做別的事】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
```c
static uint32_t src[<N>], dst[<N>];  // 全域：DMA 跑的時候不能消失
static void copy_while_working(void) {
    int ch = dma_claim_unused_channel(true);  // true = 沒通道就 panic
    dma_channel_config c = dma_channel_get_default_config((uint)ch);
    channel_config_set_write_increment(&c, true);  // 預設已是 32-bit、讀遞增
    dma_channel_configure((uint)ch, &c, dst, src,
                          dma_encode_transfer_count(<N>), true);  // 開始，但不等
    <CPU同時做的事>;  // 不可以碰 dst[]
    dma_channel_wait_for_finish_blocking((uint)ch);  // 要用 dst 之前才等
    dma_channel_unclaim((uint)ch);
    <用dst的程式>;
}
```
要換：`<N>` = 元素個數（兩處一樣）；`<CPU同時做的事>` = 跟 `dst` 無關的計算；`<用dst的程式>` = 讀結果。
- 想邊等邊做：`while (dma_channel_is_busy((uint)ch)) { 做一點事; }`，之後仍呼叫 wait 再 unclaim。
- ✗ 錯：wait 之前就讀 `dst[]` → 讀到一半舊、一半新。
前提：`#include "pico/stdlib.h"`、`#include "hardware/dma.h"`；CMake `target_link_libraries(<app> pico_stdlib hardware_dma)`。
驗證：先把 `dst` 填成別的值，跑完 `memcmp(dst, src, sizeof src) == 0`；用 `time_us_64()` 量，總時間 ≈ max(DMA, CPU) 而不是相加。

---

## C01-04

【片段卡｜PICO-DMA 4/5｜兩個通道同時搬】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
```c
static void cfg_copy(int ch, uint32_t *dst, const uint32_t *src, uint32_t n) {
    dma_channel_config c = dma_channel_get_default_config((uint)ch);
    channel_config_set_write_increment(&c, true);
    dma_channel_configure((uint)ch, &c, dst, src, dma_encode_transfer_count(n), false);  // false = 先不開始
}
static void dma_copy2(uint32_t *da, const uint32_t *a,
                      uint32_t *db, const uint32_t *b, uint32_t n) {
    int ch0 = dma_claim_unused_channel(true);  // true = 沒通道就 panic
    int ch1 = dma_claim_unused_channel(true);
    cfg_copy(ch0, da, a, n);
    cfg_copy(ch1, db, b, n);
    dma_start_channel_mask((1u << ch0) | (1u << ch1));  // 同時開始
    dma_channel_wait_for_finish_blocking((uint)ch0);
    dma_channel_wait_for_finish_blocking((uint)ch1);
    dma_channel_unclaim((uint)ch0);
    dma_channel_unclaim((uint)ch1);
}
```
要換：`dma_copy2(<da>, <a>, <db>, <b>, <n>)`；`<n>` = 每段元素個數。
- 沒通道要退回 CPU：claim 用 `false`（見 PICO-DMA 5/5）。
前提：`#include "pico/stdlib.h"`、`#include "hardware/dma.h"`；CMake `target_link_libraries(<app> pico_stdlib hardware_dma)`。
驗證：`memcmp(da, a, n * 4) == 0` 且 `memcmp(db, b, n * 4) == 0`。

---

## C01-05

【片段卡｜PICO-DMA 5/5｜通道 claim / unclaim 規矩】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
```c
static int dma_job(void) {
    int ch = dma_claim_unused_channel(false);  // false：沒空的回 -1
    if (ch < 0) return -1;  // <改用CPU做>
    <設定並啟動通道>;
    if (<要中途放棄>) {  // 通道可能還在跑
        dma_channel_cleanup((uint)ch);  // 關 chain、關 IRQ、abort、清旗標
        dma_channel_unclaim((uint)ch);
        return -2;
    }
    dma_channel_wait_for_finish_blocking((uint)ch);
    dma_channel_unclaim((uint)ch);  // 每條 return 路徑都要還
    return 0;
}
```
要換：`<設定並啟動通道>` = PICO-DMA 1/5 的 config + configure；`<要中途放棄>` = 你的條件；`<改用CPU做>` = 備案。
| 情況 | 寫法 |
|---|---|
| 一定要有通道 | `dma_claim_unused_channel(true)`：沒有就 panic「No DMA channels are available」 |
| 可以退回 CPU | `dma_claim_unused_channel(false)`：回 -1 |
| 正常做完 | wait → `dma_channel_unclaim` |
| 還在跑就要停 | `dma_channel_cleanup` → `dma_channel_unclaim` |
✗ 錯：只 `dma_channel_unclaim` 想停通道 → ✓ 對：unclaim 只改借用表，不會停；先 cleanup。
RP2350 有 16 個通道（`NUM_DMA_CHANNELS`）；忘了還 → 呼叫幾次後就 -1 / panic。
前提：`#include "pico/stdlib.h"`、`#include "hardware/dma.h"`；CMake `target_link_libraries(<app> pico_stdlib hardware_dma)`。
驗證：迴圈呼叫 100 次，每次都回 0（沒有漏還）。

---

## C02-01

【片段卡｜PICO-SNIFF 1/2｜DMA sniffer 算 zlib CRC32】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
```c
static uint32_t dma_crc32(const void *p, uint32_t nbytes) {
    if (nbytes == 0) return 0;
    int ch = dma_claim_unused_channel(true);
    static volatile uint8_t sink;
    dma_channel_config c = dma_channel_get_default_config((uint)ch);
    channel_config_set_transfer_data_size(&c, DMA_SIZE_8);
    dma_sniffer_set_data_accumulator(0xFFFFFFFFu);
    dma_sniffer_set_output_reverse_enabled(true);  // 讀出時位元反轉
    dma_sniffer_enable((uint)ch, DMA_SNIFF_CTRL_CALC_VALUE_CRC32R, false);
    channel_config_set_sniff_enable(&c, true);  // 通道也要開
    dma_channel_configure((uint)ch, &c, &sink, p, dma_encode_transfer_count(nbytes), true);
    dma_channel_wait_for_finish_blocking((uint)ch);
    uint32_t crc = dma_sniffer_get_data_accumulator() ^ 0xFFFFFFFFu;
    dma_sniffer_disable();
    dma_channel_unclaim((uint)ch);
    return crc;
}
```
要換：`dma_crc32(<buf>, <nbytes>)`，`<nbytes>` = bytes。
前提：`#include "pico/stdlib.h"`、`#include "hardware/dma.h"`；CMake `target_link_libraries(<app> pico_stdlib hardware_dma)`。
驗證：`dma_crc32("123456789", 9) == 0xCBF43926`；得 0x649C2FD3 → OUT_REV 改 false；得 0x340BC6D9 → 拿掉最後的 `^`。

---

## C02-02

【片段卡｜PICO-SNIFF 2/2｜軟體 CRC32 對照組】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
```c
static uint32_t cpu_crc32(const uint8_t *p, uint32_t n) {  // 慢但一定對
    uint32_t c = 0xFFFFFFFFu;
    while (n--) { c ^= *p++; for (int k = 0; k < 8; k++) c = (c >> 1) ^ (0xEDB88320u & -(c & 1)); }
    return ~c;
}
static bool crc_selftest(const uint8_t *buf, uint32_t n) {
    uint32_t a = cpu_crc32((const uint8_t *)"123456789", 9);  // 應 = 0xCBF43926
    uint32_t b = dma_crc32("123456789", 9);  // PICO-SNIFF 1/2
    uint32_t c = cpu_crc32(buf, n), d = dma_crc32(buf, n);
    uint32_t e = crc32_update(0, buf, n);  // serial_proto.c 查表版
    return a == 0xCBF43926u && b == a && c == d && c == e;
}
```
要換：呼叫 `crc_selftest(<buf>, <n>)`；`<n>` = bytes。沒有 serial_proto.c 就刪掉 `e`（3 處）。
- 三個都是 zlib CRC-32（= Python `zlib.crc32(data)`）。
- 分段：`crc = crc32_update(crc, 下一段, 長度)`；`dma_crc32` 要一次算完整段。
前提：`#include "pico/stdlib.h"`、`#include "hardware/dma.h"`、`#include "serial_proto.h"`；`serial_proto.c` 加進 `add_executable`；CMake `target_link_libraries(<app> pico_stdlib hardware_dma)`。
驗證：回傳 `true`；`printf("%08lx", (unsigned long)c)` 跟 Python `hex(zlib.crc32(data))` 一樣。

---

## C03-01

【片段卡｜PICO-DMAPIO 1/2｜兩通道：記憶體 → TX FIFO、RX FIFO → 記憶體】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
```c
static int ch_tx, ch_rx;
static void dma_pio_setup(PIO pio, uint sm, uint32_t *dst, const uint32_t *src, uint32_t n) {
    ch_tx = dma_claim_unused_channel(true);
    ch_rx = dma_claim_unused_channel(true);
    dma_channel_config ctx = dma_channel_get_default_config((uint)ch_tx);  // 預設 = 32-bit、讀++、寫不動
    channel_config_set_dreq(&ctx, pio_get_dreq(pio, sm, true));  // TX
    dma_channel_configure((uint)ch_tx, &ctx, &pio->txf[sm], src, dma_encode_transfer_count(n), false);
    dma_channel_config crx = dma_channel_get_default_config((uint)ch_rx);
    channel_config_set_read_increment(&crx, false);
    channel_config_set_write_increment(&crx, true);
    channel_config_set_dreq(&crx, pio_get_dreq(pio, sm, false));  // RX
    dma_channel_configure((uint)ch_rx, &crx, dst, &pio->rxf[sm], dma_encode_transfer_count(n), false);
}
```
要換：`dma_pio_setup(<pio>, <sm>, <dst>, <src>, <n>)`，`<n>` = u32 個數。
前提：先做 PICO-PIO 1/2；`#include "hardware/dma.h"`、`#include "hardware/pio.h"`；CMake `target_link_libraries(<app> pico_stdlib hardware_dma hardware_pio)`。
驗證：跑完 PICO-DMAPIO 2/2 `memcmp(dst, src, n * 4) == 0`。

---

## C03-02

【片段卡｜PICO-DMAPIO 2/2｜同時啟動、等完成、歸還】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
```c
static void dma_pio_run(void) {
    dma_start_channel_mask((1u << ch_tx) | (1u << ch_rx));  // 兩個一起開
    <CPU同時做的事>;
    dma_channel_wait_for_finish_blocking((uint)ch_rx);  // 收完 = 資料都回來了
    dma_channel_wait_for_finish_blocking((uint)ch_tx);
    dma_channel_unclaim((uint)ch_tx);
    dma_channel_unclaim((uint)ch_rx);
}
```
要換：`<CPU同時做的事>` = 不碰 `dst[]` 的工作（沒有就刪掉那行）。
- 1/2 的 configure 最後 `false` = 先不開始，在這裡用 mask 一起開。
- 兩個「都要」啟動：只開 TX → RX FIFO 滿 → PIO 卡在 push → TX 永遠 BUSY（卡死）。
- DREQ：TX = TX FIFO 沒滿才寫；RX = RX FIFO 有資料才讀。不要自己寫 DREQ 數字。
- `DMA_SIZE_32` 對應 .pio 的門檻 32（`out x, 32` / `in x, 32`）。
- echo 同時用 TX 和 RX → 不能 `sm_config_set_fifo_join`。
- ✗ 錯：DMA 在跑時 CPU 也 `pio_sm_get` 同一個 FIFO → ✓ 對：等兩個通道都完成。
前提：同 PICO-DMAPIO 1/2；`.pio` 要加 CMake `pico_generate_pio_header(<app> ${CMAKE_CURRENT_LIST_DIR}/pio/echo.pio)` 並 `#include "echo.pio.h"`。
驗證：`memcmp(dst, src, n * 4) == 0`；跟 CPU `pio_sm_put_blocking`/`pio_sm_get_blocking` 迴圈比 `time_us_64()`。

---

## C04-01

【片段卡｜PICO-PIO 1/2｜載入程式 + 設定 SM（shift、autopush/autopull）】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
```c
static bool pio_start(PIO pio, uint *sm, uint *off) {
    int o = pio_add_program(pio, &<echo>_program);
    if (o < 0) return false;
    int s = pio_claim_unused_sm(pio, false);
    if (s < 0) { pio_remove_program(pio, &<echo>_program, (uint)o); return false; }
    *off = (uint)o; *sm = (uint)s;
    pio_sm_config c = <echo>_program_get_default_config(*off);
    sm_config_set_out_shift(&c, false, true, <32>);  // (右移?, autopull, 門檻)
    sm_config_set_in_shift(&c, false, <false>, <32>);  // (右移?, autopush, 門檻)
    pio_sm_init(pio, *sm, *off, &c);
    pio_sm_set_enabled(pio, *sm, true);
    return true;
}
```
要換：`<echo>` = `.program` 名稱（3 處）；`<32>` = 門檻 1～32；`<false>` = .pio 有手動 `push` 就 false。呼叫：`uint sm, off; pio_start(pio0, &sm, &off);`
- 右移?：false = 左移、MSB 先；true = 右移、LSB 先（預設 true）。
- auto：true = 滿門檻自動 push/pull。
前提：`#include "pico/stdlib.h"`、`#include "hardware/pio.h"`、`#include "<echo>.pio.h"`；CMake `target_link_libraries(<app> pico_stdlib hardware_pio)`、`pico_generate_pio_header(<app> ${CMAKE_CURRENT_LIST_DIR}/pio/<echo>.pio)`。
驗證：回傳 `true`；接 PICO-PIO 2/2 送 `0x12345678` 收回一樣的值（echo）。

---

## C04-02

【片段卡｜PICO-PIO 2/2｜put / get / 有 timeout 的收 / 歸還】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
```c
static bool pio_roundtrip(PIO pio, uint sm, uint32_t x, uint32_t *out) {
    pio_sm_put_blocking(pio, sm, x);  // TX FIFO 滿就等
    absolute_time_t until = make_timeout_time_ms(<100>);
    while (pio_sm_is_rx_fifo_empty(pio, sm) && !time_reached(until))
        tight_loop_contents();
    if (pio_sm_is_rx_fifo_empty(pio, sm)) return false;  // 超時
    *out = pio_sm_get(pio, sm);  // 確定有資料才拿
    return true;
}
static void pio_stop(PIO pio, uint sm, uint off) {
    pio_sm_set_enabled(pio, sm, false);
    pio_remove_program_and_unclaim_sm(&<echo>_program, pio, sm, off);
}
```
要換：`<100>` = 最多等幾 ms；`<echo>` = `.program` 名稱。
- 確定 PIO 一定會回：`uint32_t r = pio_sm_get_blocking(pio, sm);`（PIO 沒跑 = 永遠卡住）。
- ✗ 錯：`pio_remove_program_and_unclaim_sm(pio, &prog, sm, off)` → ✓ 對：第 1 個是 `&<echo>_program`，第 2 個才是 `pio`。
- RP2350：`pio0`/`pio1`/`pio2`，每塊 4 個 SM、32 條指令空間。
前提：同 PICO-PIO 1/2。
驗證：`pio_roundtrip(pio0, sm, 0x12345678, &r)` 回 `true` 且 `r == 0x12345678`（echo.pio）。

---

## C05-01

【片段卡｜PICO-MC 1/5｜啟動 core1 + FIFO 握手（兩核各做一半）】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
```c
#define DONE 0xD0E
static void core1_main(void) {
    while (true) {
        uint32_t cmd = multicore_fifo_pop_blocking();  // 等 core0 下命令
        __dmb();  // 看得到 core0 push 前寫的資料
        <core1的工作(cmd)>;
        __dmb();  // 結果寫完才通知
        multicore_fifo_push_blocking(DONE);
    }
}
static void run_on_both(uint32_t cmd) {  // core0 呼叫，可重複
    __dmb();
    multicore_fifo_push_blocking(cmd);  // 叫 core1 開始
    <core0的工作(cmd)>;  // core0 同時做
    multicore_fifo_pop_blocking();  // 等 core1 回 DONE
    __dmb();
}
// main 裡只呼叫一次：multicore_launch_core1(core1_main);
```
要換：`<core1的工作(cmd)>` / `<core0的工作(cmd)>` = 各做一半，例如 `add_part(a, 0, n / 2)` 和 `add_part(a, n / 2, n)`（PICO-MC 4/5）。
- RP2350 FIFO 每方向 4 個 `uint32_t`；只傳命令或指標，大資料放全域陣列。
- core1 stack 預設 0x800 = 2KB（`PICO_CORE1_STACK_SIZE`）→ 大陣列用 `static`。
- ✗ 錯：呼叫 `multicore_launch_core1` 兩次 → ✓ 對：一次，之後用 FIFO 派工。
前提：`#include "pico/stdlib.h"`、`#include "pico/multicore.h"`；CMake `target_link_libraries(<app> pico_stdlib pico_multicore)`。
驗證：兩核各算一半，合起來 == 單核算的結果。

---

## C05-02

【片段卡｜PICO-MC 2/5｜queue_t 管線：core1 計算端】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
```c
typedef struct { uint32_t id; const uint32_t *data; uint32_t n; } job_t;
typedef struct { uint32_t id; uint32_t sum; } result_t;
static queue_t q_job, q_result;
static void worker_core1(void) {
    job_t j;
    while (true) {
        queue_remove_blocking(&q_job, &j);  // 沒工作就等
        if (j.data == NULL) break;  // 約定：data == NULL = 結束
        result_t r = { j.id, 0 };
        for (uint32_t i = 0; i < j.n; i++) r.sum += <j.data[i]>;
        queue_add_blocking(&q_result, &r);  // 回傳結果
    }
    while (true) tight_loop_contents();
}
static void pipeline_init(void) {  // main 裡呼叫一次
    queue_init(&q_job, sizeof(job_t), 8);  // (佇列, 元素大小, 最多幾個)
    queue_init(&q_result, sizeof(result_t), 8);
    multicore_launch_core1(worker_core1);  // queue_init 要在 launch 之前
}
```
要換：`job_t`/`result_t` 欄位 = 題目的工作與結果；`<j.data[i]>` = 每筆要算的式子。
- `queue_t` 內建鎖，兩核傳資料最省事；元素是「複製」進去的。
前提：`#include "pico/stdlib.h"`、`#include "pico/multicore.h"`、`#include "pico/util/queue.h"`；CMake `target_link_libraries(<app> pico_stdlib pico_multicore)`。
驗證：接 PICO-MC 3/5，結果總和 == core0 自己算的總和。

---

## C05-03

【片段卡｜PICO-MC 3/5｜queue_t 管線：core0 收資料、派工、收結果】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
```c
#define CHUNK <1024>
static uint32_t data_buf[4][CHUNK];  // 4 塊輪流用
static uint64_t run_jobs(int n_jobs) {
    int sent = 0, got = 0;
    uint64_t total = 0;
    while (got < n_jobs) {
        if (sent < n_jobs && sent - got < 4) {  // 最多 4 個在算：不能蓋掉還在算的 buffer
            uint32_t *buf = data_buf[sent % 4];
            <收一塊資料到buf>;
            job_t j = { (uint32_t)sent, buf, CHUNK };
            queue_add_blocking(&q_job, &j);
            sent++;
        }
        result_t r;
        if (queue_try_remove(&q_result, &r)) { total += r.sum; got++; }  // 不阻塞
    }
    job_t stop = { 0, NULL, 0 };
    queue_add_blocking(&q_job, &stop);  // 叫 worker 結束
    return total;
}
```
要換：`<1024>` = 每塊幾個 u32；`<收一塊資料到buf>` = 例如從序列埠讀進 `buf`；呼叫 `run_jobs(<16>)`。
- 先做 PICO-MC 2/5 的 `pipeline_init()`；`stop` 送出後 worker 不再收工作。
- ✗ 錯：只用 1 塊 buffer → core1 算到一半被 core0 覆蓋。
前提：同 PICO-MC 2/5。
驗證：`run_jobs` 回傳值 == 單核迴圈算出的總和。

---

## C05-04

【片段卡｜PICO-MC 4/5｜各核先加區域變數，最後鎖一次合併】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
```c
static volatile uint32_t total;  // 兩核共用的結果
static spin_lock_t *lock;
static void merge_init(void) {  // main 裡、launch core1 之前
    lock = spin_lock_init((uint)spin_lock_claim_unused(true));
    total = 0;
}
static void add_part(const uint32_t *a, uint32_t lo, uint32_t hi) {
    uint32_t local = 0;  // 區域變數：不用鎖、最快
    for (uint32_t i = lo; i < hi; i++) local += <a[i]>;
    uint32_t save = spin_lock_blocking(lock);  // 只鎖這一次
    total += local;
    spin_unlock(lock, save);
}
```
要換：`<a[i]>` = 每筆要加的值。core0 跑 `add_part(a, 0, n / 2)`、core1 跑 `add_part(a, n / 2, n)`（用 PICO-MC 1/5 派工）。
- 範圍 `[lo, hi)` 不重疊；兩核做完（core0 收到 DONE）才讀 `total`。
- ✗ 錯：迴圈裡每次 `total += a[i]` 都鎖 → 很慢；不鎖 → 遺失更新（race）。
前提：`#include "pico/stdlib.h"`、`#include "pico/multicore.h"`、`#include "hardware/sync.h"`；CMake `target_link_libraries(<app> pico_stdlib pico_multicore)`。
驗證：`total` == 單核迴圈算的總和。

---

## C05-05

【片段卡｜PICO-MC 5/5｜spinlock / critical_section 短臨界區】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
```c
static spin_lock_t *lock;
static critical_section_t cs;
static volatile uint32_t counter;
static void locks_init(void) {  // main 裡、launch core1 之前
    lock = spin_lock_init((uint)spin_lock_claim_unused(true));
    critical_section_init(&cs);
}
static void inc_spin(void) {
    uint32_t save = spin_lock_blocking(lock);  // 拿鎖 + 關中斷
    <counter++>;  // 臨界區：越短越好
    spin_unlock(lock, save);  // 放鎖 + 恢復中斷
}
static void inc_cs(void) {
    critical_section_enter_blocking(&cs);
    <counter++>;
    critical_section_exit(&cs);
}
```
要換：`<counter++>` = 一定要保護的那幾行共用變數更新。
| 工具 | 何時用 |
|---|---|
| `spin_lock_*` | 最底層，臨界區幾行 |
| `critical_section_t` | 同上，寫法較乾淨 |
| `mutex_t` | 臨界區較長；不能在中斷裡用 |
| `queue_t` | 兩核傳資料 |
- ✗ 錯：臨界區裡 `printf`、`sleep_ms`、等 FIFO → 關中斷太久或卡死。
前提：`#include "pico/stdlib.h"`、`#include "pico/sync.h"`、`#include "hardware/sync.h"`；CMake `target_link_libraries(<app> pico_stdlib pico_sync)`（`pico_multicore` 另加）。
驗證：兩核各跑 200000 次 `inc_spin()` → `counter == 400000`。

---

## C06-01

【片段卡｜PICO-TIME 1/1｜量一段程式：微秒與 cycle（ARM / RISC-V）】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
```c
static void time_block(void) {
    uint64_t t0 = time_us_64();
    <要量的程式>;
    PRINT_US("<名稱>", t0);  // 印「[時間] 名稱  N us」
    cycles_init();  // 開一次：ARM 設 SysTick、RISC-V 開 mcycle
    uint32_t c0 = cycles_now();
    <要量的短程式>;
    uint32_t cyc = cycles_since(c0);  // 方向自動處理
    printf("%lu cycles\n", (unsigned long)cyc);
    printf("x%.1f\n", (double)speedup(<cpu_us>, <dma_us>));  // 加速倍數
}
```
要換：`<要量的程式>` = 任何長度；`<要量的短程式>` = 短的（見下表）；`<名稱>` = 標籤；`<cpu_us>`/`<dma_us>` = 兩次量到的 `uint64_t` 微秒。
| | ARM（Cortex-M33） | RISC-V（Hazard3） |
|---|---|---|
| 計數器 | SysTick 24-bit 往下數 | `mcycle` 往上數 |
| 上限 @150MHz | 2^24 ≈ 0.11 秒（超過默默算錯） | 2^32 ≈ 28 秒 |
| build | `-DPICO_BOARD=pico2` | 加 `-DPICO_PLATFORM=rp2350-riscv` |
- 結果沒被用到的計算會被編譯器刪掉 → 把結果印出來或存進 `volatile` 變數。
前提：把 `預製程式碼/pico/timing.h` 複製進專案，`#include "timing.h"`；CMake `target_link_libraries(<app> pico_stdlib)`。
驗證：`sleep_us(1000)` 量到約 1000 us；同一段兩平台都編得過。

---

## C07-01

【片段卡｜PICO-SERIAL 1/2｜封包接收迴圈（getchar_timeout_us + proto_feed）】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
```c
static frame_t rx;
int main(void) {
    stdio_init_all();
    stdio_set_translate_crlf(&stdio_usb, false);  // 關 \n→\r\n
    absolute_time_t last_rx = get_absolute_time();
    while (true) {
        int c = getchar_timeout_us(<1000>);  // 逾時回 PICO_ERROR_TIMEOUT(-2)
        if (c < 0) {  // 收一半停 100ms → 重找 AA 55
            if (proto_busy() && absolute_time_diff_us(last_rx, get_absolute_time()) > 100000)
                proto_reset();
            continue;
        }
        last_rx = get_absolute_time();
        int r = proto_feed((uint8_t)c, &rx);  // 1 完整、0 還沒、-1 CRC 錯
        if (r == 1) handle(&rx);  // app_serial.c 的 handle()
    }
}
```
要換：`<1000>` = 最多等幾 us。
- ✗ 錯：`char c = getchar_timeout_us(...)` → ✓ 對：`int c`（分得出 -2 和 0xFE）。
- ✗ 錯：這裡 `printf` → 混進二進位；除錯用 LED。
前提：`#include "pico/stdlib.h"`、`#include "pico/stdio_usb.h"`、`#include "serial_proto.h"`；CMake `add_executable(<app> <app>.c serial_proto.c)`、`target_link_libraries(<app> pico_stdlib)`、`target_compile_definitions(<app> PRIVATE PICO_STDIO_DEFAULT_CRLF=0)`、`pico_enable_stdio_usb(<app> 1)`。
驗證：送 ECHO 封包，回同 cmd、seq、payload。

---

## C07-02

【片段卡｜PICO-SERIAL 2/2｜app_serial.c 加一個新指令】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
1) `serial_proto.h`，加在 `#define CMD_CRC32 0x03` 下面：
```c
#define CMD_<MAX_U32> <0x04>
```
2) `app_serial.c` 的 `handle()`，加在 `default:` 前面：
```c
    case CMD_<MAX_U32>: {
        uint32_t n = f->len / 4;  // payload = u32 陣列
        uint32_t m = 0;
        for (uint32_t i = 0; i < n; i++) {
            uint32_t v;
            memcpy(&v, f->payload + 4 * i, 4);  // 用 memcpy 取 u32
            if (v > m) m = v;  // <計算>
        }
        memcpy(reply, &m, 4);  // little-endian
        proto_send(f->cmd, f->seq, reply, 4);  // 同 cmd、同 seq
        break;
    }
```
要換：`<MAX_U32>` = 指令名（兩處一樣）；`<0x04>` = 沒用過的代碼（0x01～0x03 已用）；`// <計算>` 那行 = 題目的計算；回覆長度 4 = 你放進 `reply` 的 bytes（≤ `FRAME_MAX_PAYLOAD` 8192）。
- 電腦端（`ros2/frame.py` 那邊）要用同一個代碼。
- ✗ 錯：忘了 `break;` → 跑進下一個 case 多回一包。
前提：`app_serial.c` 已有 `#include <string.h>`、`static uint8_t reply[FRAME_MAX_PAYLOAD];`；CMake 不用改。
驗證：送 payload = u32 `5, 9, 2`（`05 00 00 00 09 00 00 00 02 00 00 00`）→ 回 payload `09 00 00 00`。

---

## C08-01

【片段卡｜HOST-SERIAL 1/3｜開 port、送一包、等回覆（frame.py）】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
```python
import serial
from frame import CMD_SUM_U32, pack_u32, unpack_u32, transact

ser = serial.Serial("<PORT>", timeout=0.05)   # USB CDC 不看 baudrate
reply = transact(ser, CMD_SUM_U32, pack_u32(<values>), seq=<1>)
total = unpack_u32(reply)[0]
ser.close()
```
要換：`<PORT>` = `/dev/ttyACM0` 之類（`ls /dev/ttyACM*`）；`<values>` = 整數 list；`<1>` = 序號 0～255。
- `transact(ser, cmd, payload, seq=0, timeout=1.0, retries=3)` → 回傳回覆的 payload（`bytes`）；全部逾時丟 `TimeoutError`。
- 只收「同 cmd、同 seq（低 8 bit）」的回覆；每次送前先 `reset_input_buffer()`。
- 封包：`AA 55 | cmd u8 | seq u8 | len u16 | payload | crc32 u32`，全部小端；crc 範圍 = cmd 到 payload 結尾。
- cmd：`0x01` ECHO、`0x02` SUM_U32、`0x03` CRC32。
✗ 錯：`serial.Serial(port)`（timeout=None）→ 沒回覆時 `read` 永遠卡住，不會重送 → ✓ 對：`timeout=0.05`。
✗ 錯：一包 payload > `MAX_LEN`=8192 → Pico 丟包、不回 → ✓ 對：HOST-SERIAL 2/3 切包。
前提：`frame.py` 放同資料夾；要有 pyserial（`python3 -c "import serial"` 不報錯；考場不能自己裝，沒有就舉手問）。
驗證：`python3 fake_pico.py --link /tmp/ttyFAKE` → `<PORT>`=`/tmp/ttyFAKE0`；`pack_u32([1, 2, 3, -1])` → `total == 5`（實跑通過）。

---

## C08-02

【片段卡｜HOST-SERIAL 2/3｜數字一次轉 bytes、切包、加總 mod 2^32】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
```python
import array
from frame import CHUNK_BYTES, CMD_SUM_U32, transact, unpack_u32

data = array.array("i", <values>).tobytes()   # int32 小端，一次轉完
step = CHUNK_BYTES // 4 * 4                   # 每包 bytes（4 的倍數）
total = 0
for k, i in enumerate(range(0, len(data), step)):
    reply = transact(ser, CMD_SUM_U32, data[i:i + step], seq=k)
    total = (total + unpack_u32(reply)[0]) & 0xFFFFFFFF
signed = total - (1 << 32) if total >= 1 << 31 else total
```
要換：`<values>` = int32 範圍的整數 list；`ser` 照 HOST-SERIAL 1/3 開。
| 100 萬個數轉 bytes | 實測 |
|---|---|
| `array.array("i", v).tobytes()` | 19.5 ms |
| `pack_u32(v)` | 82 ms |
| 每個 `struct.pack` 再 `join` | 124 ms |
- 有 ≥ 2^31 的 u32 → 用 `array.array("I", v)` 或 `pack_u32(v)`；`"i"` 會丟 `OverflowError`。
- `seq=k` 只取低 8 bit，超過 255 繞回 0 沒關係（一次只等一包）。
- `CHUNK_BYTES`=4096，要 ≤ Pico `FRAME_MAX_PAYLOAD`=8192。
✗ 錯：`step` 不是 4 的倍數 → 一個 u32 被切兩半 → ✓ 對：`CHUNK_BYTES // 4 * 4`。
✗ 錯：CRC32 也切包再相加 → 答案錯；CRC 要整份一次算。
前提：`import array`；`frame.py` 同資料夾。
驗證：10 萬個隨機 int32 經 fake_pico 切 98 包 → `total == sum(values) & 0xFFFFFFFF`，且 `data == pack_u32(values)`（實跑通過）。

---

## C08-03

【片段卡｜HOST-SERIAL 3/3｜文字一行 vs 二進位固定長度】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
```python
import serial

ser = serial.Serial("<PORT>", timeout=1.0)        # readline 最多等 1 秒
ser.reset_input_buffer()
ser.write(("<CMD> " + " ".join(map(str, <values>)) + "\n").encode())
line = ser.readline().decode(errors="replace").strip()  # 去掉 \r\n
if not line:
    raise TimeoutError("沒收到一整行")
ans = int(line)
# 二進位：對方回固定 <n> bytes
buf = ser.read(<n>)                   # 最多等 timeout
if len(buf) < <n>:
    raise TimeoutError(f"只收到 {len(buf)} bytes")
```
要換：`<PORT>`；`<CMD>` = 題目的文字指令；`<values>` = 整數 list；`<n>` = 預期 bytes 數。
| 對方送什麼 | 用 |
|---|---|
| `printf("%d\n", x)` 一行文字 | `readline()` → `.decode().strip()` → `int()` 或 `.split(",")` |
| 二進位 / 封包 | `read(n)` 或 frame.py 的 `FrameParser` |
- 逾時**不會丟例外**：`readline()` 回 `b""`、`read(n)` 回不足 n bytes → 自己檢查。
- Pico `printf` 的 `\n` 預設變 `\r\n`（`PICO_STDIO_DEFAULT_CRLF` = 1）→ `.strip()` 去掉。
✗ 錯：二進位資料用 `readline()` → 資料裡的 `0x0A` 被當行尾（實測 16 bytes 只拿到 11）→ ✓ 對：`read(n)`。
✗ 錯：`timeout=None` → 沒換行就永遠卡住。
前提：`import serial`（pyserial）。
驗證：pty 假裝置回 `"25\r\n"` → `ans == 25`；`read(8)` 拿到 `00 01 … 07`（實跑通過）。

---

## C09-01

【片段卡｜HOST-MULTI 1/2｜N 塊板子平行算（multi_device.run_parallel）】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
```python
from multi_device import split, run_parallel, merge_sum
from frame import CMD_SUM_U32, pack_u32

ports = ["<PORT0>", "<PORT1>"]
chunks = split(pack_u32(<values>))     # 每塊 ≤ CHUNK_BYTES、4 的倍數
replies = run_parallel(ports, chunks, CMD_SUM_U32)   # 依 chunk 順序
ans = merge_sum(replies)
```
要換：`<PORT0>`、`<PORT1>` = 每塊板子的 port（可再加）；`<values>` = 整數 list。
multi_device.py 怎麼做：
- `split(data, chunk_bytes=CHUNK_BYTES, align=4)` → `list[bytes]`。
- `run_parallel(ports, chunks, cmd)`：每個 port 一條 `threading.Thread`，各自開 `serial.Serial`；chunk 放在共用 `queue.Queue`，誰先做完誰拿下一塊（快的板子多做）。
- 結果存 `results[idx]`（`seq=idx`）→ 回來順序亂也沒關係。
- 有一塊逾時 → 丟 `RuntimeError("有 chunk 失敗，見上方訊息")`。
- 會印 `每個 port 做了幾塊: {...}`。
✗ 錯：多條執行緒共用一個 `ser` → 回覆互搶 → ✓ 對：一個 port 一條執行緒、各自開。
前提：`multi_device.py`、`frame.py` 同資料夾；要有 pyserial（考場不能自己裝）。
驗證：`python3 fake_pico.py -n 2 --link /tmp/ttyFAKE` → ports = `/tmp/ttyFAKE0`、`/tmp/ttyFAKE1`；5 萬個 u32 切 49 塊（24 + 25）→ `ans == sum(values) & 0xFFFFFFFF`（實跑通過）。

---

## C09-02

【片段卡｜HOST-MULTI 2/2｜合併結果：加總 / 串接 / 排序 k-way】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
```python
import array, heapq
from frame import unpack_u32

def merge_sum(replies):          # 每塊回 1 個 u32
    return sum(unpack_u32(r)[0] for r in replies) & 0xFFFFFFFF

def merge_concat(replies):       # 逐元素運算（平方、ECHO…）
    return b"".join(replies)

def merge_sorted(replies):       # 每塊已排序 → k-way merge
    return list(heapq.merge(*(unpack_u32(r) for r in replies)))

def merge_sorted_i32(replies):   # 有號 int32 排序
    return list(heapq.merge(*(array.array("i", r).tolist() for r in replies)))
```
用法：`ans = merge_sorted(run_parallel(ports, chunks, <CMD_SORT>))`
要換：`<CMD_SORT>` = 題目的排序指令（frame.py、fake_pico.py、Pico 三邊一起加）。
| 題目 | 合併 |
|---|---|
| 加總 | `merge_sum` |
| 每個元素各自算 | `merge_concat` |
| 排序 | 各塊排好 → `merge_sorted` |
| CRC32 | 不能相加：整份一次算，或協定多帶「上一包的 crc」續算（`zlib.crc32(data, prev)`） |
✗ 錯：有號資料用 `unpack_u32` 解 → 負數變成很大的正數、排序錯 → ✓ 對：`merge_sorted_i32`。
✗ 錯：照「回來的先後」接 → 順序亂；`run_parallel` 回傳的 list 已依 chunk 編號排好。
前提：`import array, heapq`；`from frame import unpack_u32`。
驗證：fake_pico 2 個 port，用 ECHO 回各塊（先排好）→ `merge_sorted(...) == sorted(values)`、`merge_concat(...) == data`、有號版也對（實跑通過）。

---

## C10-01

【片段卡｜HOST-ROS 1/4｜最小節點 class：參數、QoS、訂閱→處理→發布】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
```python
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from std_msgs.msg import Int32

class Processor(Node):
    def __init__(self):
        super().__init__("<processor>")
        self.declare_parameter("factor", 2)
        self.factor = self.get_parameter("factor").value
        qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE)
        self.pub = self.create_publisher(Int32, "</double>", qos)
        self.sub = self.create_subscription(Int32, "</number>", self.on_msg, qos)

    def on_msg(self, msg):
        out = Int32()
        out.data = <msg.data * self.factor>
        self.pub.publish(out)
```
要換：`<processor>` = 節點名；`</number>`、`</double>` = topic；`<msg.data * self.factor>` = 運算；`Int32` = 題目型別（import 一起改）。
- 參數不改程式：`--ros-args -p factor:=3`。
- qos 直接寫 `10` = RELIABLE、VOLATILE、depth 10。
✗ 錯：RELIABLE 訂閱 BEST_EFFORT 發布者 → 收不到 → ✓ 對：`ReliabilityPolicy.BEST_EFFORT`。
前提：main 見 HOST-ROS 2/4。從 `node_template.py`、`host_driver.py` 節錄，沒有實跑（只做語法檢查）。
驗證：`ros2 node list` 看到 `/<processor>`。

---

## C10-02

【片段卡｜HOST-ROS 2/4｜main：spin、Ctrl+C 收尾、測試指令】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
```python
def main():
    rclpy.init()
    node = Processor()
    try:
        rclpy.spin(node)          # 沒有 spin，callback 永遠不會被呼叫
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()
```
```bash
source /opt/ros/jazzy/setup.bash
python3 <node.py> --ros-args -p factor:=3
ros2 topic echo /double
ros2 topic pub --once /number std_msgs/msg/Int32 "{data: 21}"
ros2 topic info -v /number      # 看 QoS、幾個 pub/sub
```
要換：`Processor` = HOST-ROS 1/4 的 class 名；`<node.py>` = 檔名。
- `rclpy.try_shutdown()`：已經 shutdown 也不會出錯（Ctrl+C 時常見）。
- `spin` 是單執行緒：callback 一個一個跑。
✗ 錯：Ctrl+C 後再 `rclpy.shutdown()` → 可能丟例外 → ✓ 對：`try_shutdown()`。
前提：`import rclpy`、`from rclpy.executors import ExternalShutdownException`。從 `node_template.py` 原樣複製，這次沒有實跑。
驗證：factor 3、pub 21 → echo 出現 `data: 63`。

---

## C10-03

【片段卡｜HOST-ROS 3/4｜Int32MultiArray / UInt8MultiArray 快速收發】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
```python
import array
from std_msgs.msg import Int32MultiArray, UInt8MultiArray

msg = Int32MultiArray()
msg.data = array.array("i", <values>)   # list 也可以；值要在 int32 範圍
self.pub.publish(msg)                   # 不要填 msg.layout

def on_numbers(self, msg):              # 收到的 msg.data 是 array('i')
    raw = msg.data.tobytes()            # 小端 int32 bytes → 直接送序列埠
    vals = msg.data.tolist()

b = UInt8MultiArray()
b.data = array.array("B", <payload>)    # <payload> = bytes
payload = bytes(msg.data)               # 收 UInt8MultiArray → bytes
```
要換：`<values>` = 整數 list。
- Jazzy 的 setter 做 `array.array('<碼>', value)`（rosidl_python `_msg.py.em`）。碼：`int32 i`、`uint32 I`、`uint8 B`、`int8 b`、`float32 f`、`float64 d`。
✗ 錯：≥ 2^31 的值放 `Int32MultiArray` → `OverflowError` → ✓ 對：用 `UInt32MultiArray` 或先 `v - (1 << 32)`。
✗ 錯：填 `layout.dim` 送 micro-ROS 板子 → 板子收不到。
前提：`source /opt/ros/jazzy/setup.bash`。從 `serial_bridge.py`、`host_driver.py` 整理，沒有實跑 rclpy（`array` 部分用純 Python 驗過）。
驗證：`ros2 topic pub --once /numbers std_msgs/msg/Int32MultiArray "{data: [1, 2, 3]}"` → callback 裡 `vals == [1, 2, 3]`。

---

## C10-04

【片段卡｜HOST-ROS 4/4｜量 callback 花多久、topic 頻率】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
```python
import time

def on_numbers(self, msg):
    t0 = time.perf_counter()
    <處理並 publish>
    ms = (time.perf_counter() - t0) * 1000
    self.get_logger().info(f"{len(msg.data)} 個數字, {ms:.1f} ms")
```
```bash
ros2 topic hz /<out_topic>     # 每秒幾筆
ros2 topic bw /<out_topic>     # 每秒多少 bytes
```
要換：`<處理並 publish>` = 你的運算 + `self.pub.publish(...)`；`<out_topic>` = 輸出 topic。
- 吞吐量：`len(msg.data) * 4 / (ms / 1000) / 1024` = KiB/s（int32 一個 4 bytes）。
- `rclpy.spin` 是單執行緒：一個 callback 慢，其他 callback 全部排隊。
- 比較前後版本：同一份輸入、各跑幾次取最快，答案也要一樣。
✗ 錯：`time.time()`（會被改系統時間影響）→ ✓ 對：`time.perf_counter()`。
✗ 錯：只量 callback 就說「整條變快」→ 端到端看 `ros2 topic hz`。
前提：`import time`；`source /opt/ros/jazzy/setup.bash`。從 `serial_bridge.py` 的 `on_numbers` 節錄，這次沒有實跑 rclpy（計時程式用假 logger 跑過）。
驗證：log 每筆印出 `N 個數字, x.x ms`；`ros2 topic hz` 印 `average rate: …`。

---

## C11-01

【片段卡｜HOST-UROS 1/4｜Pico 端：Int32MultiArray 預先配置 capacity】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
```c
#include <std_msgs/msg/int32_multi_array.h>
#define MAX_LEN 400        // 含 data[0] 的 job_id；保守取 ≤ 450
std_msgs__msg__Int32MultiArray msg_in, msg_out;
static int32_t in_buf[MAX_LEN], out_buf[MAX_LEN];   // 靜態 buffer

static void alloc_msgs(void) {
    msg_in.data.data = in_buf;   msg_in.data.capacity = MAX_LEN;  msg_in.data.size = 0;
    msg_out.data.data = out_buf; msg_out.data.capacity = MAX_LEN; msg_out.data.size = 0;
    msg_in.layout.dim.data = NULL;  msg_in.layout.dim.capacity = 0;  msg_in.layout.dim.size = 0;
    msg_out.layout.dim.data = NULL; msg_out.layout.dim.capacity = 0; msg_out.layout.dim.size = 0;
    msg_in.layout.data_offset = 0;  msg_out.layout.data_offset = 0;
}
```
要換：`MAX_LEN` = 一則最多幾個 int32（含 job_id）。
- `main` 裡在建 executor **之前**呼叫 `alloc_msgs();`。
- 收到元素數 > `capacity` → callback 仍被叫，但 `data.size = 0`。
- dim capacity = 0 → 電腦端填了 `layout.dim` 整則會被丟掉。
✗ 錯：buffer 放 stack（主 stack 只有 2 KB）。
前提：CMake `target_link_libraries(app pico_stdlib microros)`、include `libmicroros/include`。
驗證：本卡 + 2/4 + 3/4 組成 .c，pico2 + jazzy libmicroros `-Wall -Wextra` 編譯 0 警告；沒上板跑。

---

## C11-02

【片段卡｜HOST-UROS 2/4｜Pico 端：callback 收 → compute → 發】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
```c
// 你的運算：輸入 in[0..n-1]，輸出寫到 out，回傳輸出長度（≤ cap）
static size_t compute(const int32_t *in, size_t n, int32_t *out, size_t cap);

void sub_cb(const void *msgin) {
    const std_msgs__msg__Int32MultiArray *m = (const std_msgs__msg__Int32MultiArray *)msgin;
    if (m->data.size < 1) return;                       // 至少要有 job_id（太長也會變 0）
    int32_t job_id = m->data.data[0];
    size_t n = m->data.size - 1;
    size_t out_n = compute(&m->data.data[1], n, &out_buf[1], MAX_LEN - 1);
    // capacity 檢查：size 絕對不能 > capacity，不然序列化會越界
    if (out_n + 1 > msg_out.data.capacity) out_n = msg_out.data.capacity - 1;
    out_buf[0] = job_id;
    msg_out.data.size = out_n + 1;
    RCSOFTCHECK(rcl_publish(&pub, &msg_out, NULL));
}
```
要換：`compute` 的內容（範本是插入排序；可換 sort / CRC / SHA / NN）。
- 協定：`data[0]` = job_id，`data[1..]` = 資料；回傳格式一樣。
- `RCSOFTCHECK(fn)` = 錯誤也不停；`RCCHECK(fn)` = 錯誤進 LED 快閃迴圈。
- reliable 發佈會等 agent ACK 才回來。
✗ 錯：`msg_out.data.size` > `capacity` → 越界。✗ 錯：在 callback 裡 `printf` → 會混進 micro-ROS 的序列埠資料。
前提：HOST-UROS 1/4 的 `alloc_msgs`；`pub` 是 `rcl_publisher_t`。
驗證：同 1/4 一起編譯連結 0 警告；沒在板子上跑。

---

## C11-03

【片段卡｜HOST-UROS 3/4｜Pico 端：建 node、sub/pub、executor】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
```c
#define BOARD_NS "<pico0>"
allocator = rcl_get_default_allocator();
RCCHECK(rclc_support_init(&support, 0, NULL, &allocator));
RCCHECK(rclc_node_init_default(&node, "compute_node", BOARD_NS, &support));
const rosidl_message_type_support_t *ts =
    ROSIDL_GET_MSG_TYPE_SUPPORT(std_msgs, msg, Int32MultiArray);
RCCHECK(rclc_subscription_init_default(&sub, &node, ts, "input"));
RCCHECK(rclc_publisher_init_default(&pub, &node, ts, "output"));
executor = rclc_executor_get_zero_initialized_executor();
RCCHECK(rclc_executor_init(&executor, &support.context, 1, &allocator));
RCCHECK(rclc_executor_add_subscription(&executor, &sub, &msg_in, &sub_cb, ON_NEW_DATA));
while (true) {
    rclc_executor_spin_some(&executor, RCL_MS_TO_NS(1));
}
```
要換：`<pico0>` = 每塊板子不同（`pico0`、`pico1`…）。
- `"input"` + namespace `pico0` → `/pico0/input`、`/pico0/output`。
- `rclc_executor_init` 第 3 參數 = handle 數（1 個 sub = 1）。
- 一則上限：reliable ≈ 505 個 int32。
前提：`#include <rclc/rclc.h>`、`<rclc/executor.h>`；先做 `rmw_uros_set_custom_transport`、`alloc_msgs()`、`rmw_uros_ping_agent`。
驗證：同 1/4 一起編譯連結 0 警告，簽名對過 jazzy `rclc/*.h`；沒在板子上跑。

---

## C11-04

【片段卡｜HOST-UROS 4/4｜電腦端：帶 job_id 送 N 塊板子、照順序合併】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
```python
import heapq
from rclpy.qos import QoSProfile, ReliabilityPolicy
from std_msgs.msg import Int32MultiArray

qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE)
for i in range(N_BOARDS):          # 在 __init__ 裡
    self.pubs.append(self.create_publisher(Int32MultiArray, f'/pico{i}/input', qos))
    self.create_subscription(Int32MultiArray, f'/pico{i}/output',
        lambda msg, b=i: self.on_result(b, msg), qos)

def send(self, board, job_id, chunk):
    msg = Int32MultiArray()           # 不要填 layout.dim
    msg.data = [job_id] + chunk
    self.pubs[board].publish(msg)

def on_result(self, board, msg):
    job_id = msg.data[0]
    self.results[job_id] = list(msg.data[1:])

chunks = [data[i:i + CHUNK] for i in range(0, len(data), CHUNK)]
parts = [self.results[k] for k in sorted(self.results)]
out = list(heapq.merge(*parts))   # 排序；逐元素運算改串接
```
要換：`N_BOARDS` = 板子數；`CHUNK` = 每塊個數（+1 ≤ 板子 `MAX_LEN`=400）。
✗ 錯：`lambda msg: self.on_result(i, msg)` → 全部變最後一個 i → ✓ 對：`b=i`。
前提：每塊板子各一個 agent。從 `host_driver.py` 節錄，沒實跑 rclpy（切塊 / 合併用純 Python 驗過）。
驗證：`host_driver.py` 印 `correct=True`。

---

## C12-01

【片段卡｜ALGO 1/6｜CRC-32 分段算、三種實作、照規格的 crc_generic】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
```c
#include "crc32.h"
crc32_init();                              // 開機一次（不呼叫也會自動建表）
uint32_t c = crc32_update(0, <buf1>, <n1>);    // 第一段傳 0
c = crc32_update(c, <buf2>, <n2>);             // 續算：= 整段一次算
uint32_t t = crc32_table(0, <buf>, <n>);       // 1 KB 表
uint32_t s = crc32_slice4(0, <buf>, <n>);      // 4 KB 表，最快
crc_param_t spec = {16, 0x8005, 0xFFFF, 1, 1, 0x0000};  // CRC-16/MODBUS
uint32_t r = crc_generic(&spec, <buf>, <n>);
```
要換：`<buf*>` = `const uint8_t *`；`<n*>` = bytes 數；`spec` = 題目給的參數。
`crc_param_t` 欄位順序：`{width, poly, init, refin, refout, xorout}`（poly 用一般寫法，非反轉）。
| 名稱 | width | poly | init | refin/refout | xorout | "123456789" |
|---|---|---|---|---|---|---|
| CRC-32 zlib | 32 | 0x04C11DB7 | 0xFFFFFFFF | 1/1 | 0xFFFFFFFF | 0xCBF43926 |
| CRC-16/MODBUS | 16 | 0x8005 | 0xFFFF | 1/1 | 0x0000 | 0x4B37 |
| CRC-8 SMBus | 8 | 0x07 | 0x00 | 0/0 | 0x00 | 0xF4 |
✗ 錯：第一段傳 `0xFFFFFFFF` → 錯；`crc32_update` 第一段傳 `0`（跟 `zlib.crc32` 一樣）。
前提：`#include "crc32.h"`，一起編 `crc32.c`。
驗證：`crc32_update(0, "123456789", 9) == 0xCBF43926`，三種實作相同；表中各組 check 全對；其他參數見 `crc32.h`（實跑通過）。

---

## C12-02

【片段卡｜ALGO 2/6｜排序：radix_sort_u32、合併兩塊 / k 塊、有號】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
```c
#include "sort.h"
static uint32_t a[N], tmp[N];              // MCU 上用 static
radix_sort_u32(a, N, tmp);                 // tmp 至少 N 個

merge_two_sorted(<A>, <nA>, <B>, <nB>, out);   // out 至少 nA+nB 個，不可跟 A/B 重疊

const uint32_t *lists[] = {<A>, <B>, <C>};
const size_t lens[] = {<nA>, <nB>, <nC>};
kway_merge(lists, lens, 3, out);           // 3 = k；out 至少 Σlens 個

// 有號 int32：翻符號位 → 排 → 翻回來
uint32_t *u = (uint32_t *)s;
for (size_t i = 0; i < N; i++) u[i] ^= 0x80000000u;
radix_sort_u32(u, N, tmp);
for (size_t i = 0; i < N; i++) u[i] ^= 0x80000000u;
```
要換：`N` = 個數；`<A>`、`<B>`、`<C>` = 已排序的 `uint32_t` 陣列；`<nA>`… = 各自長度；`s` = 你的 `int32_t` 陣列。
| 情況 | 用 |
|---|---|
| n < ~32 | `insertion_sort_u32(a, n)` |
| 要穩定排序 | `merge_sort_u32(a, n, tmp)` |
| 大量 u32 | `radix_sort_u32(a, n, tmp)` |
| 兩塊板子 / 兩核各排一半 | `merge_two_sorted` |
| k 塊 | `kway_merge`（O(n·k)，k ≤ 8 划算） |
- 遞減：排完反轉陣列。
✗ 錯：有號直接 `radix_sort_u32` → 負數排到最後。
前提：`#include "sort.h"`，一起編 `sort.c`。
驗證：1000 個隨機數對 `qsort` 結果完全相同；k-way 輸出遞增；有號版對 `qsort` 相同（實跑通過）。

---

## C12-03

【片段卡｜ALGO 3/6｜SHA-0 / SHA-1 / SHA-256 串流 init / update / final】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
```c
#include "sha1_sha0.h"
#include "sha256.h"
sha1_ctx c;  sha1_init(&c, 0);             // 0 = SHA-1，1 = SHA-0
sha1_update(&c, <pkt1>, <n1>);             // 資料分幾包就呼叫幾次
sha1_update(&c, <pkt2>, <n2>);
uint8_t out1[20]; sha1_final(&c, out1);    // 20 bytes，大端，直接印 hex
sha256_ctx d; sha256_init(&d);             // SHA-256 沒有第二個參數
sha256_update(&d, <pkt1>, <n1>);
sha256_update(&d, <pkt2>, <n2>);
uint8_t out2[32]; sha256_final(&d, out2);
for (int i = 0; i < 20; i++) printf("%02x", out1[i]);
printf("\n");
```
要換：`<pkt*>` = `const uint8_t *`；`<n*>` = bytes 數。
- 一次算完：`sha1(p, n, out)`、`sha0(p, n, out)`、`sha256(p, n, out)`。
- SHA-0 和 SHA-1 唯一差別：SHA-1 訊息擴展 `W[t]` 多左旋 1 位。
| 輸入 "abc" | 結果 |
|---|---|
| SHA-1 | `a9993e364706816aba3e25717850c26c9cd0d89d` |
| SHA-0 | `0164b8a914cd2a5e74c4f7ff082c4d97f1edf880` |
| SHA-256 | `ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad` |
✗ 錯：`sha1_init(&c, 1)` 以為是 SHA-1 → 那是 SHA-0。
✗ 錯：final 後沒 init 就算下一份 → 答案錯（實測）→ ✓ 對：每份先 `sha1_init`。
前提：`#include "sha1_sha0.h"`、`"sha256.h"`，一起編 `sha1_sha0.c`、`sha256.c`。
驗證："a" + "bc" 分兩包 → 上表三個值都對（實跑通過）。

---

## C12-04

【片段卡｜ALGO 4/6｜BNN：±1 打包成 bits、XNOR-popcount 內積】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
```c
#include "bnn.h"
uint32_t xb[BNN_WORDS(N)], wb[BNN_WORDS(N)];   // N=70 → 3 個 word
bnn_pack(x, N, xb);                          // v>0 → 1，否則 0（0 也當 -1）
bnn_pack(wv, N, wb);
int32_t d = bnn_dot(xb, wb, N);              // = Σ x[i]*w[i]，範圍 -N..N
int bit = d >= 0;                            // sign（門檻 0）
```
要換：`N` = 元素數；`x`、`wv` = `int8_t` 陣列（值 +1 / -1）。
- 公式：`dot = 2 * popcount(~(a ^ w)) - n`（相同的個數 − 不同的個數）。
- 位元排列：第 i 個 → `word[i / 32]` 的 `bit (i % 32)`（LSB 起算）。
- 最後一個 word 只有 `n % 32` 個有效 bit → 一定要 mask（`bnn_dot` 已做）。
- 一整層：`bnn_layer_t L = {n_in, n_out, W, thr, flip};` → `bnn_dense_sign(&L, in, out_bits)`；最後一層 `bnn_dense_score(&L, in, score)` → `bnn_argmax(score, n_out)`。
✗ 錯：自己寫 popcount 沒 mask 尾巴 → 多算 `32 - n % 32` 個「相同」（實測 N=70 答案錯）。
- 注意：`bnn_pack` 把 `v ≤ 0` 都當 -1 → 0/1 像素的 0 = -1。
前提：`#include "bnn.h"`，一起編 `bnn.c`。
驗證：N=70 時 `bnn_dot == Σ x[i]*w[i]`（-14 = -14，實跑通過）。

---

## C12-05

【片段卡｜ALGO 5/6｜照規格位元表取欄位：GET_FIELD / SET_FIELD / sign_extend】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
```c
#include "bitops.h"
// 規格表：bit 31..28 VER、27..16 LEN、15..0 OFS（有號 16 bit）
#define VER_HI 31
#define VER_LO 28
#define LEN_HI 27
#define LEN_LO 16
#define OFS_HI 15
#define OFS_LO 0
uint32_t ver = GET_FIELD(x, VER_HI, VER_LO);            // 無號欄位
uint32_t len = GET_FIELD(x, LEN_HI, LEN_LO);
int32_t  ofs = sign_extend(GET_FIELD(x, OFS_HI, OFS_LO),
                           OFS_HI - OFS_LO + 1);        // 有號欄位：寬度 = hi-lo+1
x = SET_FIELD(x, LEN_HI, LEN_LO, 0x123);                // 只改 LEN，其他不動
```
要換：`VER/LEN/OFS` 的名字與 `HI`、`LO` = 題目表格的 bit 範圍；`x` = `uint32_t`。
- 參數順序：`GET_FIELD(x, hi, lo)`、`SET_FIELD(x, hi, lo, v)` → **hi 在前**；含 hi 與 lo。
- `SET_FIELD` 回傳新值（不會改 x）→ 要 `x = SET_FIELD(...)`；v 超寬會被 mask。
- `sign_extend(v, bits)`：`sign_extend(0xFFF, 12) = -1`、`(0x800, 12) = -2048`。
- `MASK(32)` 已特別處理（`1u << 32` 是未定義行為）。
✗ 錯：`GET_FIELD(x, lo, hi)` 順序顛倒 → 結果錯。✗ 錯：有號欄位只 `GET_FIELD` → 負數變大正數。
前提：`#include "bitops.h"`（`預製程式碼/bits-riscv/`，只有標頭）。
驗證：`x = 0xABCD1234` → `ver = 0xA`、`len = 0xBCD`、`ofs = 4660`，SET 後 `x = 0xA1231234`（實跑通過）。

---

## C12-06

【片段卡｜ALGO 6/6｜位元流 MSB-first 讀固定寬度欄位】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
```c
typedef struct {
    uint8_t *buf;   // 資料
    size_t   pos;   // 目前在第幾個「位元」（不是 byte！）
} BitStream;

uint32_t read_msb(BitStream *s, int n) {
    uint32_t v = 0;
    for (int i = 0; i < n; i++) {
        size_t byte = s->pos >> 3;          // pos / 8 = 第幾個 byte
        int    bit  = 7 - (s->pos & 7);     // 該 byte 內從 bit7 往下用
        v = (v << 1) | ((s->buf[byte] >> bit) & 1u);   // 新位元接在最右邊
        s->pos++;
    }
    return v;
}
```
用法：
```c
uint8_t d[] = {0xA5, 0x3C};      // 1010 0101 0011 1100
BitStream r = {d, 0};
uint32_t a = read_msb(&r, 3);    // 101      = 0x5
uint32_t b = read_msb(&r, 7);    // 0010100  = 0x14（跨 byte）
uint32_t c = read_msb(&r, 6);    // 111100   = 0x3C
```
要換：`d` = 你的 bytes；`3/7/6` = 題目每個欄位的寬度（1～32）。
- MSB-first（多數網路協定、影像格式）：每個 byte 先用 bit7。LSB-first（deflate、很多 UART/FIFO）要改用 `bitstream.c` 的 `read_lsb`。
- 寫入：`write_msb(&w, v, n)`，buf 要先清 0。
✗ 錯：`pos` 當成 byte 數 → 位移錯。✗ 錯：讀超過 `buf` 尾巴 → 越界（自己檢查 `pos + n <= 8 * len`）。
前提：`#include <stdint.h>`、`<stddef.h>`；從 `bitstream.c` 複製（它有 `main`，不能整檔一起編）。
驗證：上面用法得到 `0x5`、`0x14`、`0x3C`，`r.pos == 16`；`DE AD BE EF` 讀 32 位 = `0xDEADBEEF`（實跑通過）。

---

## C13-01

【片段卡｜PERF 1/4｜pthread 切塊：各自區域累加、最後合併一次】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
```c
#define T_MAX 64
typedef struct { int id; size_t lo, hi; } job_t;   // 每條負責 [lo, hi)
static uint64_t part[T_MAX];                        // 各自的結果

static void *w_local(void *arg) {
    job_t *j = arg; uint64_t s = 0;                 // 區域變數累加，迴圈內沒有鎖
    for (size_t i = j->lo; i < j->hi; i++) s += work(data[i]);
    part[j->id] = s;                                // 只寫一次共享記憶體
    return NULL;
}
static void run(void *(*fn)(void *)) {
    pthread_t th[T_MAX]; job_t job[T_MAX];
    for (int t = 0; t < T; t++) {
        job[t] = (job_t){ t, (size_t)N * t / T, (size_t)N * (t + 1) / T };
        pthread_create(&th[t], NULL, fn, &job[t]);
    }
    for (int t = 0; t < T; t++) pthread_join(th[t], NULL);
}
// 使用：
run(w_local);
uint64_t sum = 0;
for (int t = 0; t < T; t++) sum += part[t];     // 合併：主執行緒做一次
```
要換：`data`、`N` = 你的資料與個數；`T` = 執行緒數（≤ `T_MAX`）；`work(x)` = 每個元素的運算。
- 排序題：每條排自己那段，最後 `kway_merge`（ALGO 2/6）。
✗ 錯：每個元素都 `pthread_mutex_lock` → 比單執行緒還慢。✗ 錯：不加鎖直接 `g_sum +=` → lost update、答案錯。
前提：`#include <pthread.h>`、`<stdint.h>`；編譯加 `-pthread`。
驗證：2^22 個元素，T = 3、4、8 的 `sum` 都等於單執行緒；ASan/UBSan、TSan 無錯（實跑通過）。

---

## C13-02

【片段卡｜PERF 2/4｜SPSC 環形佇列：struct + push（producer 端）】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
```c
#define CAP 1024u                       // 必須是 2 的次方
static struct {
    item_t buf[CAP];
    _Alignas(64) _Atomic size_t head;   // 分開放兩條 cache line，避免 false sharing
    _Alignas(64) _Atomic size_t tail;
} q;

static bool spsc_push(item_t v) {                     /* 只能由 producer 呼叫 */
    size_t h = atomic_load_explicit(&q.head, memory_order_relaxed);
    size_t t = atomic_load_explicit(&q.tail, memory_order_acquire);
    if (h - t == CAP) return false;                   /* 滿 */
    q.buf[h & (CAP - 1)] = v;
    atomic_store_explicit(&q.head, h + 1, memory_order_release);
    return true;
}
```
使用（producer 執行緒）：`while (!spsc_push(v)) sched_yield();   // 滿：讓出 CPU 再試`
要換：`item_t` = 你的型別（`typedef uint32_t item_t;` 或封包 struct）；`CAP` = 2 的次方。
- 只有一個 producer、一個 consumer → 不用鎖：`head` 只有 producer 寫、`tail` 只有 consumer 寫。
- 先寫 `buf`，再 release 存 `head`。pop 見 PERF 3/4。
✗ 錯：兩個 producer 同時 push → 壞掉；多寫多讀用 mutex + condvar（`pipeline_template.c` A 版）。
前提：`#include <stdatomic.h>`、`<stdbool.h>`、`<stddef.h>`、`<sched.h>`；`-std=c11 -pthread`。
驗證：配 PERF 3/4 跑 100 萬筆，加總正確；TSan 無錯（實跑通過）。

---

## C13-03

【片段卡｜PERF 3/4｜SPSC：pop（consumer 端）+ 開兩條執行緒】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
```c
static bool spsc_pop(item_t *v) {                     /* 只能由 consumer 呼叫 */
    size_t t = atomic_load_explicit(&q.tail, memory_order_relaxed);
    size_t h = atomic_load_explicit(&q.head, memory_order_acquire);
    if (h == t) return false;                         /* 空 */
    *v = q.buf[t & (CAP - 1)];
    atomic_store_explicit(&q.tail, t + 1, memory_order_release);
    return true;
}
static void *consumer(void *arg) {
    (void)arg; uint64_t s = 0; item_t v;
    for (uint32_t got = 0; got < <N_ITEMS>; got++) {
        while (!spsc_pop(&v)) sched_yield();     // 空：讓出 CPU 再試
        s += v;
    }
    consumer_sum = s;
    return NULL;
}
// main：
pthread_t p, c;
pthread_create(&c, NULL, consumer, NULL);
pthread_create(&p, NULL, producer, NULL);
pthread_join(p, NULL); pthread_join(c, NULL);
```
要換：`<N_ITEMS>` = 總筆數；`s += v` = 你的計算；`producer` = 你的函式（迴圈呼叫 `spsc_push`）；`consumer_sum` = `static uint64_t`。
- 更快：批次版 `spsc_push_n` / `spsc_pop_n`（`pipeline_template.c` C 版）。
✗ 錯：空轉不 `sched_yield()` → 搶 CPU。
前提：PERF 2/4 的 `q`、`CAP`；`#include <pthread.h>`；`-pthread`。
驗證：100 萬筆 `consumer_sum` = 直接加總；TSan 無錯（實跑通過）。

---

## C13-04

【片段卡｜PERF 4/4｜計時：BENCH 取最快、now_ns 單次】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
```c
#include "bench.h"                 // ★ 一定放第一個 include
BENCH("f 原版", 5, { r = f(a, N); do_not_optimize(r); });   // 跑 5 次印最快
double base = bench_last_ns / 1e6;                           // ms
BENCH("f 新版", 5, { r = f(a, N); do_not_optimize(r); });
printf("加速 %.2fx\n", base / (bench_last_ns / 1e6));
uint64_t t0 = now_ns();                                      // 單次量測
r = f(a, N);
printf("%.3f ms (r=%llu)\n", (now_ns() - t0) / 1e6, (unsigned long long)r);
```
要換：`f(a, N)` = 你要量的呼叫；`r` = 接結果的變數（`uint64_t` 之類）；`5` = 重複次數。
- `BENCH(name, reps, code)`：跑 reps 次取最小值，印 `  名稱  x.xxx ms`，存在 `bench_last_ns`。
- `do_not_optimize(x)`：不用它，`-O2` 會把沒用到的結果整段刪掉 → 量出 0 ms。
- 寫陣列的程式：`BENCH` 每次已呼叫 `clobber_memory()`。
- `now_ns()` = `CLOCK_MONOTONIC`，單位奈秒。
✗ 錯：`bench.h` 放在 `<stdio.h>` 後面 → `CLOCK_MONOTONIC undeclared`（實測）→ ✓ 對：第一個 include。
✗ 錯：用 `-O0` 量 → 不是優化後的速度；用 `-O2`。
- 只用 `now_ns()`、沒用 `BENCH` 也不會有 unused 警告（`bench_last_ns` 標了 `__attribute__((unused))`）。
前提：`#include "bench.h"`（`預製程式碼/linux-perf/`）；`gcc -O2 -Wall -Wextra -std=c11`。
驗證：印出兩行 `f 原版 / f 新版  x.xxx ms` 與 `加速 1.0x`（同一個函式），實跑通過。

---

## F01-00

【食譜卡｜優化 0/14｜選哪個食譜：量測 / 現象 → 食譜編號】
Task (EN): Match my measurement below to the FIRST fitting row; output its recipe number. Answer in Traditional Chinese.
任務：對到第一個符合的列，抄「食譜」那格（沒有數字 → 先做 Q06-01）。

| 量測 / 現象 | 食譜 | 範本檔案 |
|---|---|---|
| 一次一個數字、每包都在等回覆；文字 `"123\n"` | 1 | `ros2/serial_bridge.py`、`pico/app_serial.c` |
| 只有一片板子在算；計算時間佔大部分 | 2 | `ros2/multi_device.py` |
| micro-ROS 每則很小、`time=` 很長 | 3 | `micro-ros/host_driver.py` |
| Pico 收資料時不能算、算的時候不能收 | 4 | `pico/app_multicore.c` |
| Pico 兩核加鎖後沒變快 / 比單核慢 | 5 | `pico/app_multicore.c` |
| 電腦多執行緒加鎖 / atomic 後變慢；`count[tid]` 沒變快 | 6 | `linux-perf/parallel_template.c` |
| CPU 複製迴圈 `dst[i] = src[i]` 佔大部分時間 | 7 | `pico/app_dma.c` |
| CRC 算很久，用的是逐位元（`for k<8`） | 8 | `algo/crc32.c` |
| CRC 已查表還是慢、題目要硬體 CRC | 9 | `pico/app_dma.c` |
| 排序 qsort / insertion 很慢 | 10 | `algo/sort.c` |
| 多段已排序要合併、k ≥ 8 | 11 | `algo/sort.c` |
| 迴圈 / callback 裡 print、printf 很多 | 12 | `ros2/`、`pico/app_serial.c` |
| 沒動過編譯選項；熱迴圈在 flash | 13 | `CMakeLists.txt`、`linux-perf/` |
| BNN 推論慢（popcount） | 14 | `algo/bnn.h` |
| 要 PIO 取代 CPU | 無 | 沒有驗證過的食譜 → 片段卡 PICO-PIO |

<<<資料 開始>>>
[我的量測 / 現象] {{貼 S1 各階段時間，或描述現象}}
<<<資料 結束>>>
只輸出：現象：「照抄」／食譜：編號／範本檔案：
都不像就寫「食譜：無」。

---

## F01-01

【食譜卡｜優化 1/14｜序列埠：文字 / 一次一個 → 二進位 + 批次】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
適用：每個數字一行 `ser.write(f"{v}\n".encode())`、每行等回覆；或 `batch_size=1`。
對應範本：`ros2/serial_bridge.py:62-68`、`:35`；Pico `pico/app_serial.c:30-42`。
修改後（ROS node 直接用 `serial_bridge.py -p batch_size:=0`）：
```python
import array
from frame import CHUNK_BYTES, CMD_SUM_U32, transact, unpack_u32
data = array.array("i", values).tobytes()            # 整批轉 bytes（serial_bridge.py:62）
step = CHUNK_BYTES // 4 * 4                          # serial_bridge.py:63
total = 0
for i in range(0, len(data), step):                  # serial_bridge.py:66-68
    total = (total + unpack_u32(transact(ser, CMD_SUM_U32, data[i:i + step], seq=i // step))[0]) & 0xFFFFFFFF
```
要換：`values` = 你的 int 串列；Pico 用 `app_serial.c`。
量測：log 的 `X ms`（`serial_bridge.py:73-74`）。
實測（pty + `fake_pico.py`，20000 個 int32，沒有 USB）：文字一行一個 2049.7 ms；二進位一包一個 1576.9 ms；批次 3.5 ms。本次重跑：一包一個 1503.2 → 批次 3.6 ms（20 包）。
陷阱：
- ✗ 一包 > 8192 B → Pico 不回、3 次逾時 → ✓ `step` ≤ `CHUNK_BYTES`（4096）且是 4 的倍數。
- ✗ Pico printf / 沒關 CRLF → ✓ `app_serial.c:61`、`CMakeLists.txt:31`。
- CRC32 不能切包相加。
前提：pyserial；`frame.py` 在同一資料夾。
驗證：`total == sum(values) & 0xFFFFFFFF`；先對 `fake_pico.py` 測。

---

## F01-02

【食譜卡｜優化 2/14｜多片板子：切塊平行算 + 依序合併】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
適用：只有一片板子在算、計算佔大部分；工作能切（加總、逐元素、各段排序）。
不用 ROS：`python3 multi_device.py /dev/ttyACM0 /dev/ttyACM1`（`ros2/multi_device.py`）。
ROS node（`serial_bridge.py`）先加 3 行：`:28` 下 `from multi_device import merge_sum, run_parallel, split`；`:37` 下 `self.declare_parameter("ports", ["/dev/ttyACM0", "/dev/ttyACM1"])`；`:46` 下 `self.ports = list(g("ports"))`。
修改前（`serial_bridge.py:65-69`）：
```python
        try:
            for i in range(0, len(data), step):          # 切成好幾包，每包一來一回
                reply = self.send(CMD_SUM_U32, data[i:i + step])
                total = (total + unpack_u32(reply)[0]) & 0xFFFFFFFF   # TODO(改這裡) 合併方式
        except (TimeoutError, serial.SerialException) as e:   # 沒回覆，或拔線 / port 壞掉
```
修改後：
```python
        try:
            total = merge_sum(run_parallel(self.ports, split(data, step), CMD_SUM_U32))
        except RuntimeError as e:
```
量測：`multi_device.py` 自動先跑 1 個 port 再全部。
實測（fake_pico `--us-per-byte 1`，800000 B）：1 port 882.5 → 2 port 442.5 ms（1.99x）；只有傳輸時 1.5～1.7x。本次 bridge 版：882.1 → 454.2 ms。
陷阱：✗ CRC / SHA 切塊相加 → ✓ 整份給一片。排序合併用 `heapq.merge`。
前提：每片燒同一份韌體。
驗證：log `每個 port 做了幾塊: {…: 98, …: 98}`，答案和 1 片相同。

---

## F01-03

【食譜卡｜優化 3/14｜micro-ROS：CHUNK 調大 / 加板子 / best_effort】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
適用：micro-ROS 每則訊息小、`host_driver.py` 的 `time=` 很長。一次只改一個變因。
對應範本：`micro-ros/host_driver.py:21` `N_BOARDS = 2`、`:22` `CHUNK = 300`、`:50` QoS；板子 `pico_array_compute.c:17` `BOARD_NS`、`:27` `MAX_LEN 400`、`:111-112`。
A 加大 CHUNK：reliable `CHUNK ≤ 504`；`CHUNK + 1 > 400` 時兩個板子檔的 `MAX_LEN` 改成 ≥ `CHUNK + 1`，重編、每片重燒（上限是推算值，範本建議 ≤ 450）。
B 加板子：`N_BOARDS = 3`，第 3 片 `#define BOARD_NS "pico2"`、第 3 個 agent。
C best_effort（板子 `:111-112` 改成）：
```c
RCCHECK(rclc_subscription_init_best_effort(&sub, &node, ts, "input"));
RCCHECK(rclc_publisher_init_best_effort(&pub, &node, ts, "output"));
```
host `:50`：`qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.BEST_EFFORT)`，且 `CHUNK ≤ 120`。
量測：`python3 -c 'import host_driver as h; h.CHUNK=100; h.main()'`，再試 200、300、399；`h.N_BOARDS=1` vs `2`；跑 3 次取中位數。
實測：**沒有**（沒有板子 / agent）。C 的板子程式本次編譯連結 0 警告。
陷阱：
- ✗ 兩端 QoS 不同 → reliable 訂閱收不到 best_effort → ✓ 板子和 host 一起改。
- ✗ best_effort 還用 CHUNK 300 → 超過 500 B、收不到 → ✓ ≤ 120。
- best_effort 掉一則要等 `RESEND_S`（1 秒）重送；常掉就更慢。
前提：每片一個 agent、namespace `pico0`…；rclpy 部分從範本改，這次沒有實跑。
驗證：`correct=True` 且沒有逾時；`ros2 topic info /pico0/input -v` 看 QoS。

---

## F01-04

【食譜卡｜優化 4/14｜Pico 雙核：core0 收、core1 算（queue_t）】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
適用：Pico 收資料時不能算、算的時候不能收（收和算差不多重）。
修改前（`pico/app_serial.c:77`，core0 收完自己算）：`if (r == 1) { n_ok++; handle(&rx); }`
修改後：照 `pico/app_multicore.c` 第 2 部分。core1（`:76-82`）：
```c
            while (true) {
                queue_remove_blocking(&q_job, &j);      // 拿一個工作（沒有就等）
                if (j.data == NULL) break;              // 約定：data==NULL 代表結束
                result_t r = { j.id, 0 };
                for (uint32_t i = 0; i < j.n; i++) r.sum += j.data[i];  // TODO(改這裡) 真正的計算
                queue_add_blocking(&q_result, &r);      // 回傳結果
            }
```
core0（`:121-129`）：`sent - got < 4` 才把資料放進 `data_buf[sent % 4]` 送 `q_job`；`queue_try_remove(&q_result, &r)` 收結果。
要換：`:52-53` `job_t` / `result_t`、`:80` 計算、`:123` 模擬資料、`:116` `N_JOBS`。
量測：`PRINT_US("worker 總時間", t0)`。
實測：Pico 沒有。電腦端 `pipeline_template.c`：SPSC + 批次 1.56x、SPSC 0.85x、mutex 0.68x；另一次三種都 < 1x → 在目標機器量。
陷阱：
- ✗ 只有一份 `rx` → 算到一半被覆蓋 → ✓ 多塊 buffer + `sent - got < 4`。
- `queue_init` 容量 8 ≥ 4 + 1 停止；core1 stack 2 KB。
- 瓶頸在 USB → 食譜 1、2。
前提：`#include "pico/multicore.h"`、`"pico/util/queue.h"`；CMake `pico_multicore pico_sync`。
驗證：`total` 和單核版相同。

---

## F01-05

【食譜卡｜優化 5/14｜Pico 鎖：縮小臨界區、區域變數累積後鎖一次】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
適用：兩核共用 `total`，加了 spinlock 後答案對但很慢，比單核還慢。
對應範本：`pico/app_multicore.c:32-49` `add_many()`（`:46-48` 註解就是這個做法）、`:92` 建鎖。
修改前（計算也在鎖裡，另一核一直在等）：
```c
for (int i = 0; i < n; i++) {
    uint32_t s = spin_lock_blocking(lock);
    total += heavy_compute(data[i]);
    spin_unlock(lock, s);
}
```
修改後（先在區域變數算完，最後鎖一次合併）：
```c
uint32_t local = 0;
for (int i = 0; i < n; i++) local += heavy_compute(data[i]);   // 不用鎖：local 是自己的
uint32_t s = spin_lock_blocking(lock);
total += local;                                                // 臨界區只剩 1 行、只進 1 次
spin_unlock(lock, s);
```
要換：`heavy_compute` = 你的計算；`data` / `n` = 這顆核心負責的那一段。
量測：`time_us_64()` 前後相減（`app_multicore.c:103`、`:110` 已經在量）。
實測：Pico 沒有。電腦端同概念（官方 section2-3）：計算在鎖內 86.0～87.2 ms → 鎖外 41.8～49.8 ms；本次重跑 104.0 → 49.2 ms。
陷阱：
- `spin_lock_blocking` 會關中斷 → ✗ 鎖裡 printf / 長計算（USB 會漏收）。
- ✗ `multicore_launch_core1` 之後才建鎖 → ✓ 之前 `lock = spin_lock_init((uint)spin_lock_claim_unused(true));`。
- `volatile` 不能取代鎖。
前提：`#include "hardware/sync.h"`、`static spin_lock_t *lock;`。
驗證：多跑幾次答案都一樣、等於單核答案；時間變短。

---

## F01-06

【食譜卡｜優化 6/14｜電腦 pthread：計算移出鎖、local、padded】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
適用：多執行緒結果對，但比一條慢；或每條寫 `count[tid]`，加執行緒沒變快。
對應範本：`linux-perf/parallel_template.c:45-50` `w_local`、`:59-66` `w_spin`、`:42` `padded_t`。
修改前（鎖內做計算）：
```c
pthread_spin_lock(&lock);
sink += work(i);
counter++;
pthread_spin_unlock(&lock);
```
修改後（計算移到鎖外，鎖內只留共享變數）：
```c
sink += work(i);
pthread_spin_lock(&lock);
counter++;
pthread_spin_unlock(&lock);
```
更快：照 `w_local`，迴圈用區域變數，最後只寫一次 `part[id]`。`count[tid]` → `typedef struct { _Alignas(64) volatile uint64_t v; } padded_t;`，使用處改 `count[tid].v`。
量測：範本內建 `BENCH`（3 次取最快），加速 = serial ÷ 該寫法。
實測（Xeon 2.30GHz 4 vCPU、gcc 13.3 `-O2`、T=4、最空閒那次）：local 3.89x、mutex 0.13x、spinlock 0.03x、atomic 0.18x、false-share 2.75x → padded 3.79x。本次重跑 local 4.00x、spinlock 0.02x。
陷阱：
- ✗ T 超過核心數 → T=8 local 3.32x、spinlock 5 秒 → ✓ T = `nproc`。
- 機器忙時倍數會跳（local 1.24x～3.89x）→ 同時間輪流多跑幾次。
前提：`#include <pthread.h>`；`gcc -O2 -Wall -Wextra -std=c11 -pthread`。
驗證：`-fsanitize=thread` 跑一次沒有 `data race`；結果和 serial 相同。

---

## F01-07

【食譜卡｜優化 7/14｜DMA 取代 CPU 複製迴圈】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
適用：CPU 迴圈 `dst[i] = src[i]` 佔大部分時間；題目要求用 DMA。
對應範本：把 `pico/app_dma.c:21-24`（舊 SDK 補丁）、`:31-46`（`dma_xfer`、`dma_copy32`）複製到你的檔案。
修改前：
```c
for (int i = 0; i < n; i++) dst[i] = src[i];        // uint32_t 陣列，n 個
```
修改後：
```c
if (dma_copy32(dst, src, n) != 0) {                   // count = n「個 u32」，不是 n*4 bytes
    for (int i = 0; i < n; i++) dst[i] = src[i];      // 沒通道 / 太大：退回 CPU
}
```
- `uint8_t` 陣列、`nbytes`：`dma_xfer(dst, src, nbytes, DMA_SIZE_8, true, true)`。
- CPU 同時做事：configure 最後給 `true` 但不馬上等，用到 `dst` 前才 `dma_channel_wait_for_finish_blocking`（`app_dma.c:129-136`）。
量測：燒 `app_dma.uf2`，看 `copy 4096 words: loop=…us memcpy=…us dma=…us  正確=OK`（`:102-110`）。
實測：**沒有**（要上板）。小資料 DMA 不一定比 `memcpy` 快，以實測為準。
陷阱：
- ✗ count 填 bytes → ✓ 次數；一律 `dma_encode_transfer_count(n)`，n < 2^28。
- ✗ 沒開寫遞增 → ✓ copy 要 `channel_config_set_write_increment(&c, true)`。
- ✗ 沒 `dma_channel_unclaim` → 16 個通道用完；32-bit 傳輸位址要 4-byte 對齊。
前提：`#include "hardware/dma.h"`；CMake `target_link_libraries(<app> hardware_dma)`。
驗證：`memcmp(dst, src, bytes) == 0`，搬之前先把 `dst` 清成別的值。

---

## F01-08

【食譜卡｜優化 8/14｜CRC 軟體加速：逐位元 → 查表 / slice4】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
適用：CRC-32（zlib）算很久，程式是逐位元（每 byte 跑 `for k < 8`）。
對應範本：`algo/crc32.h:20-23`；Pico 範本 `pico/serial_proto.c:25` 的 `crc32_update` 已是查表版。
修改前（`pico/app_dma.c:90-94` 的 `cpu_crc32`，或 `algo` 的 `crc32_bitwise`）：
```c
uint32_t c = crc32_bitwise(0, p, n);
```
修改後：
```c
uint32_t c = crc32_update(0, p, n);   /* = crc32_slice4，最快 */
```
- 只要查表版：`crc32_table(0, p, n)`。三種結果完全相同，第一個參數都是 0、可接續（把上次結果傳回去）。
量測：`gcc -O2 -std=c11 crc32_test.c crc32.c && ./a.out` 會印 4 MB 的 benchmark。
實測（host Xeon 2.30GHz、gcc 13.3 `-O2`、4 MB）：bitwise 36.47 ms、table 8.65 ms（4.2x）、slice4 2.90 ms（12.6x）。本次重跑 34.81 / 8.40 / 2.87 ms。`serial_proto.c` 查表 vs `cpu_crc32`：4.1～4.6x。Pico 上沒量。
陷阱：
- slice4 要 4 KB 表（`crc32.c` bss 5636 B）；RAM 很緊時用 `crc32_table`。
- `serial_proto.c` 的 `crc32_update` 是 weak：專案加了 `algo/crc32.c` 就用那份（結果相同，不會 multiple definition）。
- 其他 CRC 規格：`crc_generic` 很慢（0.25x），只拿來對答案。
前提：`#include "crc32.h"`；CMake 加 `algo/crc32.c` 和 include 路徑。
驗證：`crc32_update(0, (const uint8_t *)"123456789", 9) == 0xCBF43926`；`crc32_test` 印 `結果：全部通過`。

---

## F01-09

【食譜卡｜優化 9/14｜CRC 硬體：DMA sniffer 取代軟體 CRC】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
適用：`CMD_CRC32` 用軟體算太慢；題目要「硬體 CRC」「DMA 校驗」。
對應範本：`pico/app_serial.c:45`；函式來源 `pico/app_dma.c:65-87` `dma_crc32()`。
步驟：
1. `CMakeLists.txt:32` 改成 `target_link_libraries(app_serial pico_multicore hardware_dma)`。
2. `app_serial.c:17` 後加 `#include "hardware/dma.h"`、`app_dma.c:21-24` 的補丁、`app_dma.c:65-87` 整個 `dma_crc32()`。
3. `app_serial.c:45`：
```c
// 改前
uint32_t c = crc32_update(0, f->payload, f->len);
// 改後
uint32_t c = dma_crc32(f->payload, f->len);
```
量測：燒 `app_dma.uf2`，看 `crc32 16384 bytes: cpu=…us dma=…us (x…)`（`app_dma.c:123-126`）。
實測：速度**沒有**（要上板）。本次副本編譯連結 0 警告（text 27356 B）。
⚠️未上板：sniffer = zlib CRC32 只由暫存器文件推導 → 一定先看 `crc32("123456789") ... PASS`。
陷阱：
- FAIL 值 `0x649C2FD3` → `output_reverse` 設定反過來（true ↔ false）；`0x340BC6D9` → 最後的 `^ 0xFFFFFFFF` 有就拿掉、沒有就加。
- `dma_claim_unused_channel(true)` 沒通道會 panic；要保險改 `false`，失敗時呼叫 `crc32_update`。
- ✗ 分段續算 → ✓ 一次 DMA 算完整段；全晶片只有一個 sniffer。
- `dma_crc32` 裡不要 printf（app_serial 不能印字）。
前提：`hardware_dma`；SDK 2.0 / 2.1 要 `app_dma.c:21-24` 的補丁。
驗證：電腦端 `unpack_u32(transact(ser, CMD_CRC32, data))[0] == zlib.crc32(data)`，測 `b"123456789"`、空資料、4096 B 隨機。

---

## F01-10

【食譜卡｜優化 10/14｜排序：qsort / insertion → radix】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
適用：u32 排序很慢；n ≥ 256 還用 qsort / 插入排序（O(n²)）。
對應範本：`algo/sort.h:22-24`；Pico 指令加在 `pico/app_serial.c:51` 的 `TODO(改這裡)` 上面。
修改前：`qsort(a, n, 4, cmp);` 或插入排序迴圈。
修改後（板子 `handle()` 新指令，本次編譯通過）：
```c
#include "sort.h"
#define CMD_SORT_U32 0x04     // payload = u32 陣列 → 回排序好的 u32 陣列
static uint32_t sort_buf[FRAME_MAX_PAYLOAD / 4], sort_tmp[FRAME_MAX_PAYLOAD / 4];
...
    case CMD_SORT_U32: {
        uint32_t n = f->len / 4;
        memcpy(sort_buf, f->payload, n * 4);
        radix_sort_u32(sort_buf, n, sort_tmp);
        proto_send(f->cmd, f->seq, (const uint8_t *)sort_buf, (uint16_t)(n * 4));
        break;
    }
```
量測：`gcc -O2 -std=c11 sort_test.c sort.c && ./a.out`。
實測（host Xeon、gcc 13.3 `-O2`）：n=1000 insertion 78.48 µs、qsort 32.68、radix 4.54；n=2^20 qsort 109.10 ms、radix 6.86 ms（15.9x）。n ≤ 32 insertion 最快。本次 2^20：105.34 → 9.33 ms。Pico 沒量。
陷阱：
- 有號 int32：排序前後各 `^= 0x80000000u`。
- `radix_sort_u32` 用 1064 B stack；core1 只有 2 KB。
- 新 cmd 改 4 處：`serial_proto.h`、`handle()`、`frame.py`、`fake_pico.py`。
前提：CMake 加 `algo/sort.c` 和 include 路徑。
驗證：`unpack_u32(transact(ser, 0x04, pack_u32(vals))) == sorted(vals)`。

---

## F01-11

【食譜卡｜優化 11/14｜多段合併：kway_merge → 兩兩合併】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
適用：k 段已排序（多板 / 兩核各排一段）要合併，k ≥ 8 時 `kway_merge` 慢。
對應範本：`algo/sort.h:27-32`。2 段用 `merge_two_sorted(a, na, b, nb, out)`；3～4 段 `kway_merge(lists, lens, k, out)`。
修改後（k 段等長、連續放在 `src`，k 是 2 的冪；本次 k = 2、4、8、16 對 qsort 結果都相同）：
```c
static uint32_t *tree_merge(uint32_t *src, uint32_t *dst, size_t n, int k) {
    size_t len = n / k;
    while (len < n) {
        for (size_t lo = 0; lo < n; lo += 2 * len) {
            size_t m = lo + len < n ? len : n - lo, r = lo + 2 * len <= n ? len : (lo + len < n ? n - lo - len : 0);
            merge_two_sorted(src + lo, m, src + lo + m, r, dst + lo);
        }
        uint32_t *t = src; src = dst; dst = t; len *= 2;
    }
    return src;                     /* 結果在 src 或 dst 其中一個，用回傳值 */
}
```
電腦端合併（Python）：`out = list(heapq.merge(*[unpack_u32(r) for r in replies]))`。
量測：只量合併那段（`time_us_64()`）。
實測（host、n=2^20、ms）：k=2 kway 6.39 / 兩兩 3.97；k=8 29.05 / 12.19；k=16 62.32 / 15.93。Pico 上沒量。
陷阱：
- ✗ 直接用 `src` 當結果 → ✓ 用回傳值。
- 要一個 n 大小的 `dst` 暫存區（`static`）；`out` 不可以跟 `a` / `b` 重疊。
前提：`#include "sort.h"`；加 `algo/sort.c`。
驗證：合併結果 `== sorted(全部資料)`（電腦端 `assert out == sorted(values)`）。

---

## F01-12

【食譜卡｜優化 12/14｜熱路徑拿掉 printf / log】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
適用：ROS callback 或迴圈裡每個元素都 print / log；Pico 的 `app_serial.c`、micro-ROS 韌體裡有 printf。
對應範本：`ros2/serial_bridge.py:74`（一個 callback 只 log 一行）；`pico/app_serial.c:6-7`（不要 printf）。
修改前：
```python
def cb_before(msg):
    total = 0
    for v in msg:
        total += v
        print(f"got {v}, total {total}", file=out)   # 每個元素印一行
    return total
```
修改後：
```python
def cb_after(msg):
    total = sum(msg)
    print(f"{len(msg)} 個, total {total}", file=out)   # 一個 callback 只印一行
    return total
```
要換：`file=out` 是測試用（pty），你的程式拿掉；`self.get_logger().info` 一樣處理；除錯只在失敗時印。
量測：callback 前後 `time.perf_counter()`（`serial_bridge.py:60`、`:73`）。
實測（本卡自測：x86_64 Xeon、Python 3.13，20000 個元素，輸出到 pty 模擬終端機）：before 125.19～130.14 ms → after 0.19 ms。ROS logger 沒量（容器沒有 ROS 2）。
陷阱：
- Pico `app_serial` printf → 文字混進封包，`frame.py diff` 顯示「開頭不是 aa 55」→ ✓ 改用 LED。
- micro-ROS 的 USB 被 agent 佔用：printf 看不到還可能弄壞封包；agent 不要開 `-v6`。
- 鎖裡不要 printf（食譜 5）。
前提：無。
驗證：輸出結果和改之前相同；`git diff | grep -nE '^\+.*(printf|print\()'` 沒有多出來的除錯輸出。

---

## F01-13

【食譜卡｜優化 13/14｜編譯選項、熱迴圈放 RAM（__not_in_flash_func）】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
適用：單執行緒本身慢、還沒動過編譯選項；Pico 熱迴圈在 XIP flash 執行。先確認評分腳本允許改旗標。
A 電腦端：`gcc -O2 …` → `gcc -O3 -march=native …`。
實測（Xeon 4 vCPU、gcc 13.3、`parallel_template.c` serial）：46.9 → 15.5 ms（3.04x）；本次重跑 44.4 → 17.4 ms。
B Pico（pico-sdk）：沒給 `CMAKE_BUILD_TYPE` 時預設 `Release`，旗標是 `-g -O3 -DNDEBUG`（本次 `build/CMakeCache.txt` 確認）→ 通常不用改；`assert` 在 Release 會消失。
C 熱函式放 SRAM：
```c
// 修改前
static uint32_t hot_sum(const uint32_t *a, int n) {
// 修改後
static uint32_t __noinline __not_in_flash_func(hot_sum)(const uint32_t *a, int n) {
```
要換：`hot_sum` = 你的函式名（只包名字，括號放對位置）。
量測：`time_us_64()` 前後相減，重複上萬次取平均。
實測：Pico 速度**沒有**（沒上板）。本次編譯：`arm-none-eabi-nm build/<app>.elf | grep hot_sum` → `20000110 t hot_sum.constprop.0`（0x2000… = RAM）。
陷阱：
- ✗ 沒加 `__noinline` → 本次實測函式被 inline 進 `main`（`0x10000274`，在 flash），屬性白加。
- `__time_critical_func(f)` = 同一個東西（`pico/platform/sections.h:153`）。
- `-O3 -march=native` 的程式只能在同一種 CPU 跑。
前提：`#include "pico/stdlib.h"`（已含 `__not_in_flash_func`、`__noinline`）。
驗證：`nm` 位址開頭是 `2000`；結果和改之前相同。

---

## F01-14

【食譜卡｜優化 14/14｜BNN popcount：Zbb cpop / SWAR】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
適用：BNN（XNOR-popcount）推論慢；`bnn_dot` 是熱點。
對應範本：`algo/bnn.h:34-42` `bnn_popcount`、`algo/bnn.c:14-23` `bnn_dot`。
A RISC-V（Hazard3）：pico-sdk 預設 `-march=rv32imac_zicsr_zifencei_zba_zbb_zbs_zbkb` 已含 Zbb → `__builtin_popcount` 變 1 條 `cpop`。**什麼都不用改**。
B ARM（Cortex-M33，沒有 popcount 指令）：
```cmake
# 修改前：沒有這行（呼叫 libgcc 的 __popcountsi2）
# 修改後：
target_compile_definitions(<app> PRIVATE BNN_SWAR_POPCOUNT)
```
要換：`<app>` = 你的 target 名稱。
量測：`objdump -d` 看內迴圈；Pico 上 `time_us_64()` 重複上萬次。
實測（本次 objdump）：M33 預設 `bnn.o` 有 2 個 `bl __popcountsi2` → 加 SWAR 後 0 個（pico2 build 加這行後 elf 裡沒有 `__popcountsi2`）；rv32 + Zbb 有 2 條 `cpop`。host（Xeon、gcc 13.3 `-O2`，一層 784×256）：12.09 → 8.12 µs（SWAR，1.49x）、硬體 popcnt 3.47 µs；本次重跑 11.44 → 7.69 µs。Pico 上兩者速度沒量。
陷阱：
- ✗ 自己改 `-march` 拿掉 `zbb` → 又變成函式呼叫。
- ✗ 最後一個 word 沒 mask（`bnn.c:19-21`）→ 分數錯。
- 更進一步：雙核 / 多板分神經元（食譜 4、2）；輸入用 bits 傳（784 bit = 100 byte）。
前提：`#include "bnn.h"`；CMake 加 `algo/bnn.c`。
驗證：`bnn_test` 印 `結果：全部通過`；分數和 Python `bnn_dense_score` 逐項相同。
