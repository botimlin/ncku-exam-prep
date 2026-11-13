/* parallel_template.c — pthread 平行化模板：「切 T 塊 → 各算各的 → 最後合併」
 *
 * 編譯：gcc -O2 -Wall -Wextra -std=c11 -pthread parallel_template.c -o par && ./par 4
 *       （參數 = 執行緒數，預設 4）
 *
 * 比較 8 種寫法（serial 基準 + 7 種平行；同一個工作：把 N 個元素的 work(x) 加總）：
 *   serial      單執行緒（基準）
 *   local       ★ 每個執行緒用區域變數累加，最後各寫一次 → 熱迴圈裡沒有任何鎖（最快、推薦）
 *   mutex       每個元素都 lock/unlock 一次 → 鎖的爭搶讓它比單執行緒還慢
 *   spinlock    同上，用自旋鎖（官方 demo 的 critical section 寫法）
 *   atomic      每個元素 atomic_fetch_add → 正確，但共享變數在核心間跳來跳去，仍慢
 *   racy        ✗ 不加鎖直接 += 共享變數 → lost update，答案錯（錯誤示範，別用）
 *   false-share 每個執行緒寫自己的格子，但格子相鄰在同一條 64B cache line → 互相拖累
 *   padded      同上，但每格補到 64 bytes（_Alignas(64)）→ 恢復正常速度
 * 結論：鎖/原子操作只在「合併」時做一次；臨界區越短越好；共享資料注意 cache line。
 */
#include "bench.h"
#include <pthread.h>
#include <stdatomic.h>
#include <stdlib.h>

#define N     (1u << 23)        /* 資料量  TODO(改這裡) */
#define T_MAX 64
static uint32_t data[N];
static int T = 4;               /* 執行緒數（main 會讀 argv[1]）*/

/* 每個元素要做的事  TODO(改這裡)：換成題目的計算（例如 CRC、hash、比對）*/
static inline uint64_t work(uint32_t x) {
    for (int r = 0; r < 8; r++) { x ^= x << 13; x ^= x >> 17; x ^= x << 5; }  /* 模擬一點計算量 */
    return x & 0xFFFFu;
}

typedef struct { int id; size_t lo, hi; } job_t;   /* 每個執行緒負責 [lo, hi) */

static uint64_t          part[T_MAX];               /* local：各自的結果 */
static uint64_t          g_sum;                     /* mutex / spinlock 共用 */
static pthread_mutex_t   g_mtx = PTHREAD_MUTEX_INITIALIZER;
static pthread_spinlock_t g_spin;
static _Atomic uint64_t  g_atomic;
static volatile uint64_t g_racy;                    /* 錯誤示範用 */
static volatile uint64_t slot_packed[T_MAX];        /* 相鄰 8 bytes → false sharing */
typedef struct { _Alignas(64) volatile uint64_t v; } padded_t;   /* sizeof = 64 */
static padded_t slot_padded[T_MAX];

static void *w_local(void *arg) {
    job_t *j = arg; uint64_t s = 0;                 /* 區域變數 → 放暫存器，超快 */
    for (size_t i = j->lo; i < j->hi; i++) s += work(data[i]);
    part[j->id] = s;                                /* 只寫一次共享記憶體 */
    return NULL;
}
static void *w_mutex(void *arg) {
    job_t *j = arg;
    for (size_t i = j->lo; i < j->hi; i++) {
        uint64_t v = work(data[i]);                 /* 計算放在鎖外面（臨界區要短）*/
        pthread_mutex_lock(&g_mtx); g_sum += v; pthread_mutex_unlock(&g_mtx);
    }
    return NULL;
}
static void *w_spin(void *arg) {
    job_t *j = arg;
    for (size_t i = j->lo; i < j->hi; i++) {
        uint64_t v = work(data[i]);
        pthread_spin_lock(&g_spin); g_sum += v; pthread_spin_unlock(&g_spin);
    }
    return NULL;
}
static void *w_atomic(void *arg) {
    job_t *j = arg;
    for (size_t i = j->lo; i < j->hi; i++)
        atomic_fetch_add_explicit(&g_atomic, work(data[i]), memory_order_relaxed);
    return NULL;
}
static void *w_racy(void *arg) {                    /* ✗ 讀-改-寫不是原子的 → 互相覆蓋 */
    job_t *j = arg;
    for (size_t i = j->lo; i < j->hi; i++) g_racy += work(data[i]);
    return NULL;
}
static void *w_false(void *arg) {
    job_t *j = arg;
    for (size_t i = j->lo; i < j->hi; i++) slot_packed[j->id] += work(data[i]);
    return NULL;
}
static void *w_padded(void *arg) {
    job_t *j = arg;
    for (size_t i = j->lo; i < j->hi; i++) slot_padded[j->id].v += work(data[i]);
    return NULL;
}

/* 開 T 個執行緒跑 fn，平均切塊，等全部結束 */
static void run(void *(*fn)(void *)) {
    pthread_t th[T_MAX]; job_t job[T_MAX];
    for (int t = 0; t < T; t++) {
        job[t] = (job_t){ t, (size_t)N * t / T, (size_t)N * (t + 1) / T };
        pthread_create(&th[t], NULL, fn, &job[t]);
    }
    for (int t = 0; t < T; t++) pthread_join(th[t], NULL);
}

static uint64_t sum_parts(void) { uint64_t s = 0; for (int t = 0; t < T; t++) s += part[t]; return s; }

static int fails = 0;
static double base_ms;
static void report(const char *name, uint64_t got, uint64_t want) {
    printf("      → %s  加速 %.2fx  %s\n", got == want ? "結果正確" : "結果錯誤！",
           base_ms / (bench_last_ns / 1e6), name);
    if (got != want && name[0] != '(') fails++;     /* 名稱以 '(' 開頭 = 預期會錯 */
}

int main(int argc, char **argv) {
    if (argc > 1) T = atoi(argv[1]);
    if (T < 1 || T > T_MAX) T = 4;
    for (size_t i = 0; i < N; i++) data[i] = (uint32_t)rand();
    pthread_spin_init(&g_spin, PTHREAD_PROCESS_PRIVATE);
    printf("N = %u, 執行緒 T = %d（每種跑 3 次取最快）\n", N, T);

    uint64_t want = 0;
    job_t all = { 0, 0, N };                        /* 單執行緒：同一個函式跑全部 → 公平比較 */
    BENCH("serial", 3, { w_local(&all); want = part[0]; do_not_optimize(want); });
    base_ms = bench_last_ns / 1e6;
    BENCH("local (推薦)", 3, run(w_local));                     report("local", sum_parts(), want);
    BENCH("mutex 每元素", 3, { g_sum = 0; run(w_mutex); });     report("mutex", g_sum, want);
    BENCH("spinlock 每元素", 3, { g_sum = 0; run(w_spin); });   report("spin", g_sum, want);
    BENCH("atomic 每元素", 3, { atomic_store(&g_atomic, 0); run(w_atomic); });
    report("atomic", atomic_load(&g_atomic), want);
    BENCH("racy 不加鎖(錯誤示範)", 3, { g_racy = 0; run(w_racy); });
    report("(racy: lost update 預期會錯)", g_racy, want);
    uint64_t s;
    BENCH("false-share 相鄰格子", 3, { for (int t = 0; t < T; t++) slot_packed[t] = 0; run(w_false); });
    s = 0; for (int t = 0; t < T; t++) s += slot_packed[t];     report("false-share", s, want);
    BENCH("padded 補到 64B", 3, { for (int t = 0; t < T; t++) slot_padded[t].v = 0; run(w_padded); });
    s = 0; for (int t = 0; t < T; t++) s += slot_padded[t].v;   report("padded", s, want);

    if (fails) printf("結果：有 %d 項錯誤\n", fails);
    else printf("結果：全部正確（racy 錯是預期的）\n");
    return fails;
}
