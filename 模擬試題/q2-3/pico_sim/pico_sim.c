// pico_sim.c — pico_sim.h 的實作（不要改）
#define _GNU_SOURCE
#include "pico_sim.h"
#include <pthread.h>
#include <stdarg.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

static uint64_t now_ns(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000000000ull + (uint64_t)ts.tv_nsec;
}
static uint64_t t_boot;
void stdio_init_all(void) { setvbuf(stdout, NULL, _IOLBF, 0); t_boot = now_ns(); }
uint64_t time_us_64(void) { return (now_ns() - t_boot) / 1000; }
void busy_wait_us(uint64_t us) { uint64_t end = now_ns() + us * 1000; while (now_ns() < end) { } }
void sleep_us(uint64_t us) { usleep((useconds_t)us); }

void panic(const char *fmt, ...) {
    fflush(stdout);
    fprintf(stderr, "\n*** PANIC: ");
    va_list ap; va_start(ap, fmt); vfprintf(stderr, fmt, ap); va_end(ap);
    fprintf(stderr, "\n");
    _exit(3);
}

// ---- multicore ----
static __thread uint core_num = 0;
static pthread_t core1_thread;
static int core1_started;
static void (*core1_entry)(void);
static void *core1_tramp(void *arg) { (void)arg; core_num = 1; core1_entry(); return NULL; }
void multicore_launch_core1(void (*entry)(void)) {
    if (core1_started) panic("multicore_launch_core1: core1 已經在跑了");
    core1_started = 1;
    core1_entry = entry;
    pthread_create(&core1_thread, NULL, core1_tramp, NULL);
}
uint get_core_num(void) { return core_num; }

#define FIFO_DEPTH 4
typedef struct { uint32_t buf[FIFO_DEPTH]; int head, count; pthread_mutex_t m; pthread_cond_t cv; } fifo_t;
static fifo_t fifo[2] = { { .m = PTHREAD_MUTEX_INITIALIZER, .cv = PTHREAD_COND_INITIALIZER },
                          { .m = PTHREAD_MUTEX_INITIALIZER, .cv = PTHREAD_COND_INITIALIZER } };
void multicore_fifo_push_blocking(uint32_t data) {
    fifo_t *f = &fifo[core_num];            // fifo[0]：core0 → core1，fifo[1]：core1 → core0
    pthread_mutex_lock(&f->m);
    while (f->count == FIFO_DEPTH) pthread_cond_wait(&f->cv, &f->m);
    f->buf[(f->head + f->count++) % FIFO_DEPTH] = data;
    pthread_cond_broadcast(&f->cv);
    pthread_mutex_unlock(&f->m);
}
uint32_t multicore_fifo_pop_blocking(void) {
    fifo_t *f = &fifo[1 - core_num];
    pthread_mutex_lock(&f->m);
    while (f->count == 0) pthread_cond_wait(&f->cv, &f->m);
    uint32_t v = f->buf[f->head];
    f->head = (f->head + 1) % FIFO_DEPTH; f->count--;
    pthread_cond_broadcast(&f->cv);
    pthread_mutex_unlock(&f->m);
    return v;
}

// ---- spinlock ----
#define NUM_SPIN_LOCKS 32
struct spin_lock_sim { pthread_mutex_t m; };
static spin_lock_t locks[NUM_SPIN_LOCKS];
static int lock_claimed[NUM_SPIN_LOCKS];
static pthread_mutex_t claim_m = PTHREAD_MUTEX_INITIALIZER;
int spin_lock_claim_unused(bool required) {
    pthread_mutex_lock(&claim_m);
    for (int i = 24; i < NUM_SPIN_LOCKS; i++)          // SDK 也是從 24 號開始給（PICO_SPINLOCK_ID_CLAIM_FREE_FIRST）
        if (!lock_claimed[i]) { lock_claimed[i] = 1; pthread_mutex_unlock(&claim_m); return i; }
    pthread_mutex_unlock(&claim_m);
    if (required) panic("沒有空的 spinlock 可以 claim");
    return -1;
}
spin_lock_t *spin_lock_instance(uint n) {
    if (n >= NUM_SPIN_LOCKS) panic("spinlock 編號 %u 超過範圍（0..31）", n);
    return &locks[n];
}
spin_lock_t *spin_lock_init(uint n) {
    spin_lock_t *l = spin_lock_instance(n);
    pthread_mutex_init(&l->m, NULL);
    return l;
}
uint32_t spin_lock_blocking(spin_lock_t *lock) { pthread_mutex_lock(&lock->m); return 0x5A5A0000u | core_num; }
void spin_unlock(spin_lock_t *lock, uint32_t saved_irq) {
    if ((saved_irq & 0xFFFF0000u) != 0x5A5A0000u)
        panic("spin_unlock 的第二個參數要傳 spin_lock_blocking 的回傳值");
    pthread_mutex_unlock(&lock->m);
}

// ---- DMA ----
#define CTRL_SIZE_MASK 0x3u
#define CTRL_INCR_READ 0x4u
#define CTRL_INCR_WRITE 0x8u
typedef struct {
    int claimed;
    dma_channel_config cfg;
    volatile void *wr; const volatile void *rd; uint count;
} dma_ch_t;
static dma_ch_t ch[NUM_DMA_CHANNELS];
static pthread_mutex_t dma_m = PTHREAD_MUTEX_INITIALIZER;

static void check_ch(uint c, const char *fn) {
    if (c >= NUM_DMA_CHANNELS) panic("%s: channel %u 不存在（只有 0..%d）", fn, c, NUM_DMA_CHANNELS - 1);
}
int dma_claim_unused_channel(bool required) {
    pthread_mutex_lock(&dma_m);
    for (int i = 0; i < NUM_DMA_CHANNELS; i++)
        if (!ch[i].claimed) { ch[i].claimed = 1; pthread_mutex_unlock(&dma_m); return i; }
    pthread_mutex_unlock(&dma_m);
    if (required) panic("dma_claim_unused_channel: 16 個 DMA channel 都被 claim 了，沒有空的");
    return -1;
}
void dma_channel_claim(uint c) {
    check_ch(c, "dma_channel_claim");
    pthread_mutex_lock(&dma_m);
    if (ch[c].claimed) { pthread_mutex_unlock(&dma_m); panic("dma_channel_claim: channel %u 已經被 claim", c); }
    ch[c].claimed = 1;
    pthread_mutex_unlock(&dma_m);
}
void dma_channel_unclaim(uint c) {
    check_ch(c, "dma_channel_unclaim");
    pthread_mutex_lock(&dma_m); ch[c].claimed = 0; pthread_mutex_unlock(&dma_m);
}
bool dma_channel_is_claimed(uint c) { check_ch(c, "dma_channel_is_claimed"); return ch[c].claimed; }

dma_channel_config dma_channel_get_default_config(uint c) {
    check_ch(c, "dma_channel_get_default_config");
    dma_channel_config cfg = { DMA_SIZE_32 | CTRL_INCR_READ };
    return cfg;
}
void channel_config_set_transfer_data_size(dma_channel_config *c, enum dma_channel_transfer_size s) {
    if ((unsigned)s > DMA_SIZE_32) panic("transfer_data_size 只能是 DMA_SIZE_8 / 16 / 32");
    c->ctrl = (c->ctrl & ~CTRL_SIZE_MASK) | (uint32_t)s;
}
void channel_config_set_read_increment(dma_channel_config *c, bool b) {
    c->ctrl = b ? (c->ctrl | CTRL_INCR_READ) : (c->ctrl & ~CTRL_INCR_READ);
}
void channel_config_set_write_increment(dma_channel_config *c, bool b) {
    c->ctrl = b ? (c->ctrl | CTRL_INCR_WRITE) : (c->ctrl & ~CTRL_INCR_WRITE);
}

static void run_transfer(uint c) {
    dma_ch_t *d = &ch[c];
    uint sz = 1u << (d->cfg.ctrl & CTRL_SIZE_MASK);
    if (((uintptr_t)d->rd % sz) || ((uintptr_t)d->wr % sz))
        panic("DMA channel %u：每筆 %u byte 時，讀寫位址都要對齊 %u byte", c, sz, sz);
    const volatile uint8_t *r = d->rd;
    volatile uint8_t *w = d->wr;
    for (uint i = 0; i < d->count; i++) {
        if (sz == 4)      *(volatile uint32_t *)w = *(const volatile uint32_t *)r;
        else if (sz == 2) *(volatile uint16_t *)w = *(const volatile uint16_t *)r;
        else              *w = *r;
        if (d->cfg.ctrl & CTRL_INCR_READ) r += sz;
        if (d->cfg.ctrl & CTRL_INCR_WRITE) w += sz;
    }
}
void dma_channel_configure(uint c, const dma_channel_config *cfg, volatile void *wr,
                           const volatile void *rd, uint count, bool trigger) {
    check_ch(c, "dma_channel_configure");
    if (!ch[c].claimed)
        fprintf(stderr, "[pico_sim 警告] channel %u 沒有先 claim 就使用（真的 SDK 不會擋，但很容易和別人撞）\n", c);
    ch[c].cfg = *cfg; ch[c].wr = wr; ch[c].rd = rd; ch[c].count = count;
    if (trigger) run_transfer(c);
}
void dma_channel_start(uint c) { check_ch(c, "dma_channel_start"); run_transfer(c); }
bool dma_channel_is_busy(uint c) { check_ch(c, "dma_channel_is_busy"); return false; }
void dma_channel_wait_for_finish_blocking(uint c) { check_ch(c, "dma_channel_wait_for_finish_blocking"); }
