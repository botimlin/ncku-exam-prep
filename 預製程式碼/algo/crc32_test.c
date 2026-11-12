/* crc32_test.c — 電腦上測試 + benchmark
 * 編譯：gcc -O2 -Wall -Wextra -std=c11 crc32.c crc32_test.c -o crc32_test && ./crc32_test
 */
#include "test_util.h"
#include "crc32.h"

#define BIG (4u << 20)            /* 4 MB 測速資料  TODO(改這裡) */
static uint8_t big[BIG];

int main(void) {
    const uint8_t *s = (const uint8_t *)"123456789";
    crc32_init();
    printf("[CRC 標準向量]\n");
    CHECK(crc32_bitwise(0, s, 9) == 0xCBF43926u, "crc32_bitwise(\"123456789\")");
    CHECK(crc32_table(0, s, 9)   == 0xCBF43926u, "crc32_table");
    CHECK(crc32_slice4(0, s, 9)  == 0xCBF43926u, "crc32_slice4");
    CHECK(crc32c_update(0, s, 9) == 0xE3069283u, "crc32c = 0xE3069283");
    CHECK(crc16_ccitt_false(0xFFFF, s, 9) == 0x29B1, "crc16_ccitt_false = 0x29B1");
    CHECK(crc32_update(0, (const uint8_t *)"", 0) == 0, "空字串 CRC-32 = 0");

    printf("[通用 CRC 對照參數表]\n");
    const struct { crc_param_t p; uint32_t check; const char *name; } tbl[] = {
        {{32, 0x04C11DB7u, 0xFFFFFFFFu, 1, 1, 0xFFFFFFFFu}, 0xCBF43926u, "CRC-32"},
        {{32, 0x04C11DB7u, 0xFFFFFFFFu, 0, 0, 0xFFFFFFFFu}, 0xFC891918u, "CRC-32/BZIP2"},
        {{32, 0x04C11DB7u, 0xFFFFFFFFu, 0, 0, 0x00000000u}, 0x0376E6E7u, "CRC-32/MPEG-2"},
        {{32, 0x1EDC6F41u, 0xFFFFFFFFu, 1, 1, 0xFFFFFFFFu}, 0xE3069283u, "CRC-32C"},
        {{16, 0x1021u, 0xFFFFu, 0, 0, 0}, 0x29B1u, "CRC-16/CCITT-FALSE"},
        {{16, 0x1021u, 0x0000u, 0, 0, 0}, 0x31C3u, "CRC-16/XMODEM"},
        {{16, 0x1021u, 0x0000u, 1, 1, 0}, 0x2189u, "CRC-16/KERMIT"},
        {{16, 0x8005u, 0xFFFFu, 1, 1, 0}, 0x4B37u, "CRC-16/MODBUS"},
        {{16, 0x8005u, 0x0000u, 1, 1, 0}, 0xBB3Du, "CRC-16/ARC"},
        {{8,  0x07u,   0x00u,   0, 0, 0}, 0xF4u,   "CRC-8"},
    };
    for (size_t i = 0; i < sizeof tbl / sizeof tbl[0]; i++)
        CHECK(crc_generic(&tbl[i].p, s, 9) == tbl[i].check, tbl[i].name);

    printf("[隨機資料：各版本一致 + 增量 API]\n");
    for (uint32_t i = 0; i < BIG; i++) big[i] = (uint8_t)rnd32();
    int ok = 1;
    for (int t = 0; t < 200; t++) {
        size_t off = rnd32() % 64, len = rnd32() % 3000;     /* 故意不對齊、長度任意 */
        uint32_t a = crc32_bitwise(0, big + off, len);
        uint32_t b = crc32_table(0, big + off, len);
        uint32_t c = crc32_slice4(0, big + off, len);
        size_t cut = len ? rnd32() % len : 0;                 /* 切兩段算 */
        uint32_t d = crc32_update(crc32_update(0, big + off, cut), big + off + cut, len - cut);
        uint32_t e = crc_generic(&tbl[0].p, big + off, len);
        uint32_t f = crc32c_update(crc32c_update(0, big, cut), big + cut, len - cut);
        if (a != b || a != c || a != d || a != e || f != crc_generic(&tbl[3].p, big, len)) ok = 0;
    }
    CHECK(ok, "200 組隨機長度：bitwise/table/slice4/分段/generic 全相同");

    printf("[Benchmark：%u MB，取 5 次最快]\n", BIG >> 20);
    uint64_t ns;
    BENCH_MIN(ns, 5, SINK(crc32_bitwise(0, big, BIG)));
    printf("  crc32_bitwise   %8.2f ms  %7.1f MB/s\n", ns / 1e6, BIG / (ns / 1e3));
    BENCH_MIN(ns, 5, SINK(crc32_table(0, big, BIG)));
    printf("  crc32_table     %8.2f ms  %7.1f MB/s\n", ns / 1e6, BIG / (ns / 1e3));
    BENCH_MIN(ns, 5, SINK(crc32_slice4(0, big, BIG)));
    printf("  crc32_slice4    %8.2f ms  %7.1f MB/s\n", ns / 1e6, BIG / (ns / 1e3));
    BENCH_MIN(ns, 5, SINK(crc32c_update(0, big, BIG)));
    printf("  crc32c(table)   %8.2f ms  %7.1f MB/s\n", ns / 1e6, BIG / (ns / 1e3));
    BENCH_MIN(ns, 5, SINK(crc16_ccitt_false(0xFFFF, big, BIG)));
    printf("  crc16(table)    %8.2f ms  %7.1f MB/s\n", ns / 1e6, BIG / (ns / 1e3));

    return test_end();
}
