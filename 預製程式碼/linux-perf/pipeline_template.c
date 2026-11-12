/* pipeline_template.c — 生產者/消費者 環形緩衝區（ring buffer）
 * 模擬「一個核心負責收資料（producer），另一個核心負責計算（consumer）」→ 收和算同時進行
 *
 * 編譯：gcc -O2 -Wall -Wextra -std=c11 -pthread pipeline_template.c -o pipe && ./pipe
 *
 * A. mutex + condvar 佇列：最通用、最不容易錯；每個元素都要上鎖 → 慢
 * B. SPSC 無鎖佇列（Single-Producer Single-Consumer）：只有「一個寫、一個讀」時才能用。
 *    head 只有 producer 寫、tail 只有 consumer 寫 → 不需要鎖，只要 acquire/release：
 *      producer：先寫 buf[h]，再 store(head, h+1, release)   ← release：前面的寫入先完成
 *      consumer：load(head, acquire) 看到新 head，才讀 buf    ← acquire：之後的讀一定看到資料
 * C. SPSC + 批次（batch）：一次搬很多個，原子操作次數變 1/批次大小 → 更快
 *
 * RP2350 對應：core0 收 USB/UART/ROS2 資料 push，core1 pop 後計算。
 *   同樣的 SPSC 程式碼可直接用（C11 atomics），或用 pico SDK 的 queue_t / multicore_fifo。
 */
#include "bench.h"
#include <pthread.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <sched.h>

#define CAP     1024u            /* 容量，必須是 2 的次方（才能用 & 取代 %）*/
#define N_ITEMS (1u << 20)       /* 總共傳幾個  TODO(改這裡) */
#define BATCH   64u              /* C 版每批幾個 */
typedef uint32_t item_t;         /* TODO(改這裡) 換成封包 struct，例如 {uint8_t data[64]; uint16_t len;} */

/* 模擬「收一筆資料」與「算一筆資料」各花一點時間  TODO(改這裡) 換成真的收/算
 * 兩邊都有前後依賴（像 CRC/hash 一樣要照順序），編譯器無法向量化 → 比較公平 */
#define PROD_COST 64
#define COMP_COST 64
static inline item_t produce(uint32_t *st) {
    for (int r = 0; r < PROD_COST; r++) { *st ^= *st << 13; *st ^= *st >> 17; *st ^= *st << 5; }
    return *st;
}
static inline uint64_t compute(uint64_t acc, item_t x) {   /* 回傳新的累積值 */
    uint32_t h = (uint32_t)acc ^ x;
    for (int r = 0; r < COMP_COST; r++) { h ^= h << 7; h ^= h >> 9; h *= 0x9E3779B1u; }
    return acc + h;
}

/* ================= A. mutex + condvar ================= */
static struct {
    item_t buf[CAP]; size_t head, tail;
    pthread_mutex_t m; pthread_cond_t not_full, not_empty;
} mq = { .m = PTHREAD_MUTEX_INITIALIZER,
         .not_full = PTHREAD_COND_INITIALIZER, .not_empty = PTHREAD_COND_INITIALIZER };

static void mq_push(item_t v) {
    pthread_mutex_lock(&mq.m);
    while (mq.head - mq.tail == CAP) pthread_cond_wait(&mq.not_full, &mq.m);  /* 滿了就睡 */
    mq.buf[mq.head++ % CAP] = v;
    pthread_cond_signal(&mq.not_empty);                                        /* 叫醒消費者 */
    pthread_mutex_unlock(&mq.m);
}
static item_t mq_pop(void) {
    pthread_mutex_lock(&mq.m);
    while (mq.head == mq.tail) pthread_cond_wait(&mq.not_empty, &mq.m);       /* 空了就睡 */
    item_t v = mq.buf[mq.tail++ % CAP];
    pthread_cond_signal(&mq.not_full);
    pthread_mutex_unlock(&mq.m);
    return v;
}

/* ================= B. SPSC 無鎖 ================= */
static struct {
    item_t buf[CAP];
    _Alignas(64) _Atomic size_t head;   /* 分開放兩條 cache line，避免 false sharing */
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
static bool spsc_pop(item_t *v) {                     /* 只能由 consumer 呼叫 */
    size_t t = atomic_load_explicit(&q.tail, memory_order_relaxed);
    size_t h = atomic_load_explicit(&q.head, memory_order_acquire);
    if (h == t) return false;                         /* 空 */
    *v = q.buf[t & (CAP - 1)];
    atomic_store_explicit(&q.tail, t + 1, memory_order_release);
    return true;
}
/* C. 批次版：能放/能拿多少就一次處理多少，只做一次 release store */
static size_t spsc_push_n(const item_t *src, size_t n) {
    size_t h = atomic_load_explicit(&q.head, memory_order_relaxed);
    size_t room = CAP - (h - atomic_load_explicit(&q.tail, memory_order_acquire));
    if (n > room) n = room;
    for (size_t i = 0; i < n; i++) q.buf[(h + i) & (CAP - 1)] = src[i];
    atomic_store_explicit(&q.head, h + n, memory_order_release);
    return n;
}
static size_t spsc_pop_n(item_t *dst, size_t max) {
    size_t t = atomic_load_explicit(&q.tail, memory_order_relaxed);
    size_t n = atomic_load_explicit(&q.head, memory_order_acquire) - t;
    if (n > max) n = max;
    for (size_t i = 0; i < n; i++) dst[i] = q.buf[(t + i) & (CAP - 1)];
    atomic_store_explicit(&q.tail, t + n, memory_order_release);
    return n;
}

/* ================= 執行緒本體 ================= */
static int mode;                 /* 0 = A, 1 = B, 2 = C */
static uint64_t consumer_sum;

static void *producer(void *arg) {
    (void)arg;
    uint32_t st = 1;
    if (mode == 2) {
        item_t tmp[BATCH];
        for (uint32_t i = 0; i < N_ITEMS; i += BATCH) {
            size_t n = (N_ITEMS - i < BATCH) ? N_ITEMS - i : BATCH, done = 0;
            for (size_t k = 0; k < n; k++) tmp[k] = produce(&st);
            while (done < n) { size_t d = spsc_push_n(tmp + done, n - done); if (!d) sched_yield(); done += d; }
        }
    } else {
        for (uint32_t i = 0; i < N_ITEMS; i++) {
            if (mode == 0) mq_push(produce(&st));
            else { item_t v = produce(&st); while (!spsc_push(v)) sched_yield(); }   /* 滿了：讓出 CPU 再試 */
        }
    }
    return NULL;
}

static void *consumer(void *arg) {
    (void)arg;
    uint64_t s = 0; item_t v, tmp[BATCH];
    for (uint32_t got = 0; got < N_ITEMS; ) {     /* 已知總數就收滿為止（也可用特殊值當結束訊號）*/
        if (mode == 0)      { s = compute(s, mq_pop()); got++; }
        else if (mode == 1) { while (!spsc_pop(&v)) sched_yield(); s = compute(s, v); got++; }
        else {
            size_t n = spsc_pop_n(tmp, BATCH);
            if (!n) { sched_yield(); continue; }
            for (size_t k = 0; k < n; k++) s = compute(s, tmp[k]);
            got += (uint32_t)n;
        }
    }
    consumer_sum = s;
    return NULL;
}

static void run_pipeline(int m) {
    pthread_t p, c;
    mode = m;
    pthread_create(&c, NULL, consumer, NULL);
    pthread_create(&p, NULL, producer, NULL);
    pthread_join(p, NULL); pthread_join(c, NULL);
}

int main(void) {
    uint64_t want = 0; int fails = 0;
    printf("傳送 %u 筆，佇列容量 %u（每種 3 次取最快）\n", N_ITEMS, CAP);
    BENCH("serial 單執行緒 收一筆算一筆", 3, { uint32_t st = 1; want = 0;
        for (uint32_t i = 0; i < N_ITEMS; i++) want = compute(want, produce(&st));
        do_not_optimize(want); });
    uint64_t base = bench_last_ns;
    const char *name[3] = { "A mutex+condvar", "B SPSC 無鎖", "C SPSC 無鎖+批次" };
    for (int m = 0; m < 3; m++) {
        BENCH(name[m], 3, run_pipeline(m));
        printf("      → %s  加速 %.2fx\n", consumer_sum == want ? "結果正確" : "結果錯誤！",
               (double)base / bench_last_ns);
        if (consumer_sum != want) fails++;
    }
    if (fails) printf("結果：有 %d 項錯誤\n", fails); else printf("結果：全部正確\n");
    return fails;
}
