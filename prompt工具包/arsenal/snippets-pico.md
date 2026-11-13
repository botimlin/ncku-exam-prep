# 軍火庫：Pico 2 程式片段（DMA、sniffer、PIO、雙核心、計時、序列埠）
> 用法（照 `../../考場SOP.md`）：模型寫【要卡】編號時，到 `../編號卡/` Ctrl-F 那個編號複製這張卡，包在 `<<<資料 開始>>>`…`<<<資料 結束>>>` 裡、最後一行寫「繼續」再貼。本檔編號：C01（片段卡 PICO-DMA）、C02（片段卡 PICO-SNIFF）、C03（片段卡 PICO-DMAPIO）、C04（片段卡 PICO-PIO）、C05（片段卡 PICO-MC）、C06（片段卡 PICO-TIME）、C07（片段卡 PICO-SERIAL）。每張 ≤ 1200 字元。
> 來源與驗證：預製程式碼/pico/*.c 精簡（名稱、參數不改）＋ pico-sdk 2.2.0 標頭；每段都在同一個測試專案編過（pico2 ARM 與 rp2350-riscv，0 錯 0 警告），沒在板子上跑｜最後更新 2026-11-13

---

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
