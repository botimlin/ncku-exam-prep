/* bench.h — 計時工具（Linux / 電腦端）
 * ★ 必須放在所有 #include 的第一個（要先定義 _POSIX_C_SOURCE 才有 clock_gettime）
 *
 * 用法：
 *   #include "bench.h"
 *   uint64_t t0 = now_ns(); 做事(); printf("%.3f ms\n", (now_ns() - t0) / 1e6);
 *
 *   BENCH("我的函式", 5, { r = f(a, n); do_not_optimize(r); });
 *   // → 跑 5 次，印出最快的一次（最快那次最接近「真正的成本」，其他次被干擾比較多）
 *
 * 為什麼要 do_not_optimize？ -O2 會把「算了但沒用到」的結果整段刪掉，量出 0 ns。
 */
#ifndef BENCH_H
#define BENCH_H
#ifndef _POSIX_C_SOURCE
#define _POSIX_C_SOURCE 200809L
#endif
#include <stdint.h>
#include <stdio.h>
#include <time.h>

/* 單調時鐘（不受改系統時間影響），單位奈秒 */
static inline uint64_t now_ns(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000000000ull + (uint64_t)ts.tv_nsec;
}

/* 吃掉一個值，讓編譯器以為它被用到了 */
static volatile uint64_t bench_sink_;
#define do_not_optimize(x) (bench_sink_ += (uint64_t)(x))

/* 強迫編譯器把記憶體寫回去（GCC/Clang 專用），量「寫陣列」的程式時用 */
#if defined(__GNUC__)
#define clobber_memory() __asm__ __volatile__("" ::: "memory")
#else
#define clobber_memory() ((void)0)
#endif

/* BENCH(名稱, 次數, 程式碼)：重複執行取最小值並印出；結果也存在 bench_last_ns */
static uint64_t bench_last_ns __attribute__((unused));   /* 只用 now_ns() 時不會有 unused 警告 */
#define BENCH(name, reps, code) do {                                    \
    uint64_t best_ = UINT64_MAX;                                        \
    for (int r_ = 0; r_ < (reps); r_++) {                               \
        uint64_t t0_ = now_ns();                                        \
        code;                                                           \
        clobber_memory();                                               \
        uint64_t dt_ = now_ns() - t0_;                                  \
        if (dt_ < best_) best_ = dt_;                                   \
    }                                                                   \
    bench_last_ns = best_;                                              \
    printf("  %-28s %10.3f ms\n", (name), best_ / 1e6);                 \
} while (0)

#endif
