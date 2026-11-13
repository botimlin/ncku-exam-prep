// pico_sim.h — 在電腦上「模擬」pico-sdk 的一小部分 API（不要改這個資料夾）
//
// 函式名稱、參數順序、預設值都照 pico-sdk 2.x 寫，所以在這裡寫對的程式，搬到真的 Pico 2 上
// 只要換成真的 #include 就能用。和真的硬體不同的地方都標了【模擬】。
//
//   真的 pico-sdk 要 include 的是：
//     #include "pico/stdlib.h"  "pico/multicore.h"  "hardware/sync.h"  "hardware/dma.h"
#pragma once
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>

typedef unsigned int uint;

// ---- pico/stdlib.h --------------------------------------------------------
void     stdio_init_all(void);
uint64_t time_us_64(void);
void     busy_wait_us(uint64_t us);
void     sleep_us(uint64_t us);
// 等待迴圈裡放這個。【模擬】這裡多了一道 compiler barrier；真的 SDK 是空函式，
// 所以真的 Pico 上被等待的變數一定要宣告成 volatile（或用鎖保護）。
static inline void tight_loop_contents(void) { __asm__ volatile("" ::: "memory"); }
void     panic(const char *fmt, ...) __attribute__((noreturn, format(printf, 1, 2)));

// ---- pico/multicore.h -----------------------------------------------------
// 【模擬】core1 是一條 pthread；main() 所在的執行緒是 core0。
void     multicore_launch_core1(void (*entry)(void));
void     multicore_fifo_push_blocking(uint32_t data);   // 送給「另一顆」核心
uint32_t multicore_fifo_pop_blocking(void);              // 從「另一顆」核心收
uint     get_core_num(void);

// ---- hardware/sync.h（硬體 spinlock）----------------------------------------
// RP2350 有 32 個硬體 spinlock。真的 spin_lock_blocking 會關掉「這顆核心」的中斷並回傳原本的狀態，
// spin_unlock 要把那個值傳回去。持有 spinlock 時不要做慢的事：另一顆核心會一直空轉等你。
// 【模擬】內部用 pthread mutex。
typedef struct spin_lock_sim spin_lock_t;
int          spin_lock_claim_unused(bool required);      // 回傳鎖的編號；required=true 時拿不到就 panic
spin_lock_t *spin_lock_init(uint lock_num);
spin_lock_t *spin_lock_instance(uint lock_num);
uint32_t     spin_lock_blocking(spin_lock_t *lock);
void         spin_unlock(spin_lock_t *lock, uint32_t saved_irq);

// ---- hardware/dma.h --------------------------------------------------------
// RP2350 有 16 個 DMA channel（RP2040 是 12 個）。通道是有限資源：claim 之後要 unclaim。
#define NUM_DMA_CHANNELS 16
enum dma_channel_transfer_size { DMA_SIZE_8 = 0, DMA_SIZE_16 = 1, DMA_SIZE_32 = 2 };
typedef struct { uint32_t ctrl; } dma_channel_config;

int  dma_claim_unused_channel(bool required);   // required=true 時沒有空的通道就 panic
void dma_channel_claim(uint channel);
void dma_channel_unclaim(uint channel);
bool dma_channel_is_claimed(uint channel);

// 預設設定（和 SDK 一樣）：每筆 32 bit、讀位址「遞增」、寫位址「不遞增」、沒有 DREQ（全速）。
dma_channel_config dma_channel_get_default_config(uint channel);
void channel_config_set_transfer_data_size(dma_channel_config *c, enum dma_channel_transfer_size size);
void channel_config_set_read_increment(dma_channel_config *c, bool incr);
void channel_config_set_write_increment(dma_channel_config *c, bool incr);

// transfer_count 的單位是「幾筆」（每筆大小由 data_size 決定），不是 byte 數。
// trigger=true 表示設定完立刻開始。
void dma_channel_configure(uint channel, const dma_channel_config *config, volatile void *write_addr,
                           const volatile void *read_addr, uint transfer_count, bool trigger);
void dma_channel_start(uint channel);
bool dma_channel_is_busy(uint channel);
void dma_channel_wait_for_finish_blocking(uint channel);
// 【模擬】搬運在 trigger 的當下就同步做完，所以 is_busy 永遠是 false。真的硬體是在背景搬，
// 一定要 wait（或檢查 is_busy）之後才能用目的地的資料。
