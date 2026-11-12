/* test_util.h — 只給「電腦上的測試程式 *_test.c」用（MCU 不需要）
 * 必須是第一個 #include（因為要先定義 _POSIX_C_SOURCE 才能用 clock_gettime）
 */
#ifndef TEST_UTIL_H
#define TEST_UTIL_H
#ifndef _POSIX_C_SOURCE
#define _POSIX_C_SOURCE 200809L
#endif
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

static int g_fail = 0;   /* 失敗次數，main 最後 return g_fail */

/* CHECK(條件, "說明")：失敗就印出來，不中斷 */
#define CHECK(cond, msg) do { if (cond) printf("  PASS  %s\n", msg); \
    else { printf("  FAIL  %s  (%s:%d)\n", msg, __FILE__, __LINE__); g_fail++; } } while (0)

static inline uint64_t now_ns(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000000000ull + (uint64_t)ts.tv_nsec;
}

/* 可重現的亂數（xorshift32），每次跑結果都一樣 */
static uint32_t g_rng = 2463534242u;
static inline uint32_t rnd32(void) {
    g_rng ^= g_rng << 13; g_rng ^= g_rng >> 17; g_rng ^= g_rng << 5;
    return g_rng;
}

/* 把 hash 輸出轉成十六進位字串，方便跟標準答案比對 */
static inline void to_hex(const uint8_t *d, int n, char *out) {
    for (int i = 0; i < n; i++) sprintf(out + 2 * i, "%02x", d[i]);
}

/* 編譯器不准把結果優化掉：寫進 volatile */
static volatile uint64_t g_sink;
#define SINK(x) (g_sink += (uint64_t)(x))

/* main 最後 return test_end(); */
static inline int test_end(void) {
    if (g_fail) printf("結果：有 %d 項失敗\n", g_fail); else printf("結果：全部通過\n");
    return g_fail;
}

/* BENCH_MIN(ns變數, 重複次數, 程式碼)：重複跑取最快的一次 */
#define BENCH_MIN(best, reps, code) do { best = UINT64_MAX;                \
    for (int _r = 0; _r < (reps); _r++) { uint64_t _t0 = now_ns(); code;   \
        uint64_t _dt = now_ns() - _t0; if (_dt < best) best = _dt; } } while (0)

#endif
