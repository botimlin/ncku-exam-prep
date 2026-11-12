// app_dma.c — DMA 模板：copy、fill、sniffer 硬體 CRC32、跟 CPU 比速度
//
// DMA 固定流程（考題的「傳輸引擎」也是這樣）：
//   1 claim 要一個通道 → 2 config 設定 → 3 start → 4 wait 等完成 → 5 unclaim 歸還
// 設定重點：
//   - count 是「傳輸次數」不是 bytes！ 搬 N bytes 用 32-bit → count = N/4
//   - size  = DMA_SIZE_8 / DMA_SIZE_16 / DMA_SIZE_32（每次搬 1/2/4 bytes）
//   - read_increment / write_increment：copy = 兩個都 true；fill = 讀 false（一直讀同一個值）
//   - RP2350 有 16 個通道（考題的假引擎可能只有 4 個），用完要 unclaim！
//   - RP2350 TRANS_COUNT：低 28 bits = 次數，高 4 bits [31:28] = MODE（0=一般、1=自己重啟、F=無限）
//     → count 一律包 dma_encode_transfer_count(n)，且 n 必須 < 2^28（regs/dma.h CH0_TRANS_COUNT）
//     （直接傳 ≥2^28 的數字會被當成 MODE，例如 0x1xxxxxxx = 跑完自己重來，永遠停不下來）
//   - 32-bit 傳輸時位址要 4-byte 對齊（u32 陣列天生對齊；char 陣列強轉就不一定）
//   - 預設設定（dma_channel_get_default_config）：32-bit、讀遞增、寫「不」遞增、DREQ_FORCE 全速、
//     chain_to = 自己（= 不串接）、sniff 關（SDK hardware/dma.h 註解表）
#include <stdio.h>
#include <string.h>
#include "pico/stdlib.h"
#include "pico/stdio_usb.h"
#include "hardware/dma.h"
#include "timing.h"

#define N_WORDS 4096                     // TODO(改這裡) 測試資料大小（u32 個數）
static uint32_t src[N_WORDS], dst[N_WORDS];

// 通用：搬 count 次，每次 size；回傳 0 成功、-1 沒通道、-2 count 太大（≥2^28）
static int dma_xfer(void *to, const void *from, uint32_t count,
                    enum dma_channel_transfer_size size, bool rinc, bool winc) {
    if (count == 0) return 0;                          // 0 次：不啟動 DMA（避免觸發一個空傳輸）
    if (count > DMA_CH0_TRANS_COUNT_COUNT_BITS) return -2;  // ≥ 2^28：要分段搬
    int ch = dma_claim_unused_channel(false);          // false = 沒有空通道時回傳 -1（不要 panic）
    if (ch < 0) return -1;                             // TODO(改這裡) 沒通道就改用 CPU 做
    dma_channel_config c = dma_channel_get_default_config((uint)ch);
    channel_config_set_transfer_data_size(&c, size);
    channel_config_set_read_increment(&c, rinc);
    channel_config_set_write_increment(&c, winc);
    dma_channel_configure((uint)ch, &c, to, from, dma_encode_transfer_count(count), true);  // true = 立刻開始
    dma_channel_wait_for_finish_blocking((uint)ch);    // 忙等到搬完
    dma_channel_unclaim((uint)ch);                     // ⚠ 一定要還！
    return 0;
}
static int dma_copy32(uint32_t *to, const uint32_t *from, uint32_t n) { return dma_xfer(to, from, n, DMA_SIZE_32, true, true); }
static int dma_fill32(uint32_t *to, uint32_t value, uint32_t n) {
    static uint32_t v;  v = value;                     // 來源必須在 DMA 跑完前都存在 → 用 static
    return dma_xfer(to, &v, n, DMA_SIZE_32, false, true);       // 讀位址不動 = fill
}

// 硬體 CRC32（DMA sniffer）：資料流過 DMA 時順便算 CRC，目標 = zlib/Python 的 crc32
// 推導（regs/dma.h SNIFF_CTRL_CALC / OUT_REV 說明 + pico-examples dma/sniff_crc.c 同樣設定）：
//   CALC=CRC32  ：IEEE 多項式 0x04C11DB7，資料「MSB 先」進去（= CRC-32/MPEG-2 那種不反射的）
//   CALC=CRC32R ：同一個引擎，但每筆資料先位元反轉 → 等於「LSB 先」= zlib 的處理順序
//                 可是暫存器本身還是不反射的方向 → 讀出時要再整個 32-bit 反轉（OUT_REV）
//   初值 FFFFFFFF 反轉後不變；zlib 最後還要 xor FFFFFFFF（可用軟體 ^，或 OUT_INV，二選一）
//   OUT_REV / OUT_INV 只影響「讀出來的值」，不影響計算本身（暫存器說明原文）
//   8-bit 傳輸：每次餵 8 bits（pico-examples 用 DMA_SIZE_8 驗證 residue==0 成立）
//   32-bit 傳輸 + CRC32R：小端序 word 反轉後正好 = byte0 LSB 先…byte3，結果同 zlib，不用 BSWAP
//     （BSWAP 是給 CRC32 非反射模式 + 32-bit 用的；以上是依暫存器說明推導 + Python 模擬，未上板）
// 自我測試：dma_crc32("123456789", 9) 必須 == 0xCBF43926（main 會檢查）
//   若 FAIL 且值 == 0x649C2FD3（= CBF43926 位元反轉）→ 把 output_reverse 改成 false 再試
//   若 FAIL 且值 == 0x340BC6D9（= ~CBF43926）→ 最後那個 ^0xFFFFFFFF 多做了
static uint32_t dma_crc32(const void *p, uint32_t nbytes) {
    if (nbytes == 0) return 0;                         // 空資料的 crc32 = 0
    int ch = dma_claim_unused_channel(true);          // true = 沒通道就 panic（印錯誤訊息停住）
    static volatile uint8_t sink;                     // 資料寫到這個垃圾桶（寫位址不動）
    dma_channel_config c = dma_channel_get_default_config((uint)ch);
    channel_config_set_transfer_data_size(&c, DMA_SIZE_8);   // 用 byte：任何長度都對（32-bit 較快但 len 要 4 的倍數）
    channel_config_set_read_increment(&c, true);
    channel_config_set_write_increment(&c, false);
    dma_sniffer_set_data_accumulator(0xFFFFFFFFu);     // 初值（SNIFF_DATA：要在開始傳輸「之前」寫）
    dma_sniffer_set_output_reverse_enabled(true);      // 讀出時位元反轉（只設 OUT_REV bit）
    // dma_sniffer_enable 是 masked write，只改 DMACH/CALC/EN，不會清掉上一行的 OUT_REV（SDK dma.h 原始碼）
    dma_sniffer_enable((uint)ch, DMA_SNIFF_CTRL_CALC_VALUE_CRC32R, false); // false：sniff 由下一行的 config 開
    channel_config_set_sniff_enable(&c, true);        // ⚠ 通道 CTRL.SNIFF_EN 也要開，否則 CRC 不會算
    // ⚠ 要「先」設好 sniffer 再啟動通道（configure 最後的 true 才開始搬）
    dma_channel_configure((uint)ch, &c, &sink, p, dma_encode_transfer_count(nbytes), true);
    dma_channel_wait_for_finish_blocking((uint)ch);    // BUSY 變 0 = 全部搬完，SNIFF_DATA 才是最終結果
    uint32_t crc = dma_sniffer_get_data_accumulator() ^ 0xFFFFFFFFu;  // 最後 xor（用軟體做，最保險）
    // 分段續算（把上次結果寫回當初值）要小心：文件只說 OUT_REV/INV 作用在「讀」，寫入是否轉換沒寫清楚
    // → 考試時最好一次 DMA 算完整段資料
    dma_sniffer_disable();                             // sniffer 全晶片只有一個，用完關掉
    dma_channel_unclaim((uint)ch);
    return crc;
}

// 軟體 CRC32（對照組，bitwise 慢速版）
static uint32_t cpu_crc32(const uint8_t *p, uint32_t n) {
    uint32_t c = 0xFFFFFFFFu;
    while (n--) { c ^= *p++; for (int k = 0; k < 8; k++) c = (c >> 1) ^ (0xEDB88320u & -(c & 1)); }
    return ~c;
}

int main(void) {
    stdio_init_all();
    while (!stdio_usb_connected()) sleep_ms(50);
    sleep_ms(200);
    for (int i = 0; i < N_WORDS; i++) src[i] = (uint32_t)i * 2654435761u;

    // ---- 1) copy：CPU 迴圈 vs memcpy vs DMA ----
    uint64_t t0 = time_us_64();
    for (int i = 0; i < N_WORDS; i++) dst[i] = src[i];
    uint64_t t_loop = time_us_64() - t0;
    t0 = time_us_64(); memcpy(dst, src, sizeof src); uint64_t t_memcpy = time_us_64() - t0;
    memset(dst, 0, sizeof dst);
    t0 = time_us_64(); dma_copy32(dst, src, N_WORDS); uint64_t t_dma = time_us_64() - t0;
    printf("copy %d words: loop=%lluus memcpy=%lluus dma=%lluus  正確=%s\n", N_WORDS,
           t_loop, t_memcpy, t_dma, memcmp(dst, src, sizeof src) == 0 ? "OK" : "FAIL");

    // ---- 2) fill ----
    dma_fill32(dst, 0xDEADBEEF, N_WORDS);
    printf("fill: dst[0]=%08lx dst[last]=%08lx\n", (unsigned long)dst[0], (unsigned long)dst[N_WORDS - 1]);

    // ---- 3) CRC32：已知答案測試 + 速度比較 ----
    cycles_init();
    uint32_t c0 = cycles_now();
    uint32_t v = dma_crc32("123456789", 9);
    uint32_t cyc = cycles_since(c0);                 // 很短的程式用 cycle 數量比較準
    printf("crc32(\"123456789\") dma=%08lx (%lu cycles) cpu=%08lx 期望=CBF43926 %s\n", (unsigned long)v, (unsigned long)cyc,
           (unsigned long)cpu_crc32((const uint8_t *)"123456789", 9), v == 0xCBF43926u ? "PASS" : "FAIL");
    t0 = time_us_64(); uint32_t a = cpu_crc32((const uint8_t *)src, sizeof src); uint64_t t_cpu = time_us_64() - t0;
    t0 = time_us_64(); uint32_t b = dma_crc32(src, sizeof src);                  t_dma = time_us_64() - t0;
    printf("crc32 %u bytes: cpu=%lluus dma=%lluus (x%.1f) 相同=%s\n", (unsigned)sizeof src,
           t_cpu, t_dma, (double)speedup(t_cpu, t_dma), a == b ? "OK" : "FAIL");

    // ---- 4) 真正的好處：DMA 在背景搬，CPU 同時做別的事 ----
    int ch = dma_claim_unused_channel(true);
    dma_channel_config c = dma_channel_get_default_config((uint)ch);   // 預設 32-bit、讀遞增、寫「不」遞增
    channel_config_set_write_increment(&c, true);                       // ⚠ copy 一定要開寫遞增！
    dma_channel_configure((uint)ch, &c, dst, src, dma_encode_transfer_count(N_WORDS), true);  // 開始，但「不等」
    uint32_t work = 0;
    for (int i = 0; i < 1000; i++) work += (uint32_t)i * (uint32_t)i;  // TODO(改這裡) CPU 同時做的事
    dma_channel_wait_for_finish_blocking((uint)ch);                    // 要用 dst 之前才等
    dma_channel_unclaim((uint)ch);
    printf("overlap: work=%lu, dma 搬完了 正確=%s\n", (unsigned long)work,
           memcmp(dst, src, sizeof src) == 0 ? "OK" : "FAIL");   // dst 之前被 fill 成 DEADBEEF，所以這檢查有意義

    while (true) tight_loop_contents();
}
