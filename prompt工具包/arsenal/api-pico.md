# 軍火庫：pico-sdk API（DMA / Sniffer / PIO）
> 用法：一次只貼一張卡（兩條 `---` 之間），模型回「收到」後再問。函式名、參數順序、數值一律照卡上抄。
> 來源與驗證：pico-sdk 2.2.0 標頭（`hardware/dma.h`、`hardware/pio.h`、`regs/dreq.h`、`regs/intctrl.h`、`regs/dma.h`）逐行 grep 複製；2.1.1 差異比對 2.1.1 標頭並實際編譯；卡上所有函式寫進一個測試檔，pico2 + SDK 2.2.0 編譯 0 錯誤 0 警告（沒在板子上跑）｜最後更新 2026-11-13

---

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
- 結果 = 0x649C2FD3 → 改 `output_reverse_enabled(false)`。
- 結果 = 0x340BC6D9 → 拿掉最後的 `^`。
- ✗ 錯：用 `CRC32`（不反轉）比 zlib → ✓ 對：`CRC32R`
前提：`#include "hardware/dma.h"`；link `hardware_dma`。
驗證：`"123456789"` 9 bytes → `0xCBF43926`。

---

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
- 預設：clkdiv 1；wrap 0–31；in/out shift 右移、auto 關、門檻 32；out pins 32 支從 0；set pins 0 支；sideset/jmp pin 0。
- `out_count` 0–32；`set_count` 0–5；in / sideset 只給起點。
- ✗ 錯：用 `pio_get_default_sm_config()` → wrap 不對 → ✓ 對：`<prog>_program_get_default_config(offset)`
- ✗ 錯：`sm_config_set_in_pins(&c, pin, 1)` → ✓ 對：`(&c, pin)` 兩個參數
- ✗ 錯：`sm_config_set_set_pins(&c, pin)` → ✓ 對：`(&c, base, count)`
前提：`#include "hardware/pio.h"`；link `hardware_pio`。
驗證：編譯過；腳位初始化見 PIO 5/6。

---

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
- ✗ 錯：`sm_config_set_out_shift(&c, true, 32, true)` → ✓ 對：`(&c, false, true, 32)`
- ✗ 錯：程式有 `push` 又開 autopush → ✓ 對：手動 push 時 autopush=false
- ✗ 錯：JOIN_TX 後還讀 RX → ✓ 對：要收就 `PIO_FIFO_JOIN_NONE`
前提：`#include "hardware/pio.h"`；link `hardware_pio`。
驗證：`echo.pio` 送值收回相同。

---

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
