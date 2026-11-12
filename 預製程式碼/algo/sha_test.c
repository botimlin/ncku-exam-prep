/* sha_test.c — SHA-1 / SHA-0 / SHA-256 測試 + benchmark
 * 編譯：gcc -O2 -Wall -Wextra -std=c11 sha1_sha0.c sha256.c sha_test.c -o sha_test
 */
#include "test_util.h"
#include "sha1_sha0.h"
#include "sha256.h"

#define BIG (4u << 20)
static uint8_t big[BIG];

/* 算一次並跟期望的 hex 字串比對；algo: 1=SHA-1 0=SHA-0 2=SHA-256 */
static int check_hex(int algo, const char *msg, size_t n, const char *want) {
    uint8_t d[32]; char hex[65];
    if (algo == 1)      sha1((const uint8_t *)msg, n, d);
    else if (algo == 0) sha0((const uint8_t *)msg, n, d);
    else                sha256((const uint8_t *)msg, n, d);
    to_hex(d, algo == 2 ? 32 : 20, hex);
    if (strcmp(hex, want)) printf("    得到 %s\n    應為 %s\n", hex, want);
    return strcmp(hex, want) == 0;
}

int main(void) {
    const char *m448 = "abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq";
    printf("[標準向量]\n");
    CHECK(check_hex(1, "abc", 3, "a9993e364706816aba3e25717850c26c9cd0d89d"), "SHA-1(\"abc\")");
    CHECK(check_hex(0, "abc", 3, "0164b8a914cd2a5e74c4f7ff082c4d97f1edf880"), "SHA-0(\"abc\")");
    CHECK(check_hex(1, "", 0, "da39a3ee5e6b4b0d3255bfef95601890afd80709"), "SHA-1(\"\")");
    CHECK(check_hex(1, m448, 56, "84983e441c3bd26ebaae4aa1f95129e5e54670f1"), "SHA-1(56 字元，需 2 塊 padding)");
    CHECK(check_hex(2, "abc", 3,
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"), "SHA-256(\"abc\")");
    CHECK(check_hex(2, "", 0,
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"), "SHA-256(\"\")");
    CHECK(check_hex(2, m448, 56,
        "248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1"), "SHA-256(56 字元)");

    printf("[一百萬個 'a'，用串流 API 每次餵 1000 byte]\n");
    {
        uint8_t a1000[1000], d[32]; char hex[65];
        memset(a1000, 'a', sizeof a1000);
        sha1_ctx c; sha1_init(&c, 0);
        for (int i = 0; i < 1000; i++) sha1_update(&c, a1000, 1000);
        sha1_final(&c, d); to_hex(d, 20, hex);
        CHECK(!strcmp(hex, "34aa973cd4c4daa4f61eeb2bdbad27316534016f"), "SHA-1(1e6 x 'a')");
        sha256_ctx s; sha256_init(&s);
        for (int i = 0; i < 1000; i++) sha256_update(&s, a1000, 1000);
        sha256_final(&s, d); to_hex(d, 32, hex);
        CHECK(!strcmp(hex, "cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0"),
              "SHA-256(1e6 x 'a')");
    }

    printf("[隨機切段：串流結果 == 一次算]\n");
    for (uint32_t i = 0; i < BIG; i++) big[i] = (uint8_t)rnd32();
    int ok = 1;
    for (int t = 0; t < 300; t++) {
        size_t len = rnd32() % 1000;
        for (int algo = 0; algo < 3; algo++) {
            uint8_t d1[32], d2[32]; size_t pos = 0;
            sha1_ctx c; sha256_ctx s;
            if (algo < 2) sha1_init(&c, algo == 0); else sha256_init(&s);
            while (pos < len) {                          /* 每段長度 0~99 隨機 */
                size_t k = rnd32() % 100; if (k > len - pos) k = len - pos;
                if (algo < 2) sha1_update(&c, big + pos, k); else sha256_update(&s, big + pos, k);
                pos += k;
            }
            if (algo < 2) sha1_final(&c, d1); else sha256_final(&s, d1);
            if (algo == 0) sha0(big, len, d2); else if (algo == 1) sha1(big, len, d2);
            else sha256(big, len, d2);
            if (memcmp(d1, d2, algo == 2 ? 32 : 20)) ok = 0;
        }
    }
    CHECK(ok, "300 組 x 3 種演算法");

    printf("[Benchmark：%u MB，取 5 次最快]\n", BIG >> 20);
    uint8_t d[32]; uint64_t ns;
    BENCH_MIN(ns, 5, { sha1(big, BIG, d); SINK(d[0]); });
    printf("  sha1     %8.2f ms  %7.1f MB/s\n", ns / 1e6, BIG / (ns / 1e3));
    BENCH_MIN(ns, 5, { sha0(big, BIG, d); SINK(d[0]); });
    printf("  sha0     %8.2f ms  %7.1f MB/s\n", ns / 1e6, BIG / (ns / 1e3));
    BENCH_MIN(ns, 5, { sha256(big, BIG, d); SINK(d[0]); });
    printf("  sha256   %8.2f ms  %7.1f MB/s\n", ns / 1e6, BIG / (ns / 1e3));
    return test_end();
}
