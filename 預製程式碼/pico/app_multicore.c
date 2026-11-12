// app_multicore.c — 雙核心模板：FIFO、queue_t、spinlock、critical_section、mutex
//
// 題型：「用兩顆核心加速」「一顆收資料、一顆計算」「多核心共用變數會算錯（race）」
// 第 1 部分：故意做出 race（兩核同時 counter++ 會遺失更新），再用鎖修好
// 第 2 部分：core0 生產工作 → queue → core1 計算 → queue → core0 收結果
//
// 鎖怎麼選：
//   spin_lock_*        最底層；拿鎖時會「關中斷」+ 忙等，臨界區一定要超短
//   critical_section_t 就是包好的 spinlock（一樣關中斷），寫法比較乾淨
//   mutex_t            等鎖時可以讓出 CPU（低功耗等待），臨界區可以長一點；不能在中斷裡用
//   queue_t            內建鎖的 FIFO，兩核傳資料最省事（推薦！）
#include <stdio.h>
#include "pico/stdlib.h"
#include "pico/stdio_usb.h"     // stdio_usb_connected()
#include "pico/multicore.h"
#include "pico/util/queue.h"
#include "pico/sync.h"           // critical_section_t, mutex_t
#include "hardware/sync.h"       // spin_lock_*
#include "timing.h"

#define N_ADD 200000             // TODO(改這裡) 每顆核心加幾次

// ---------------- 第 1 部分：race condition ----------------
// volatile：每次 counter++ 都真的「讀記憶體→加→寫回」，race 才會出現。
// 沒有 volatile 時編譯器可能把整個迴圈變成 counter += N_ADD，錯誤示範就看不到了。
// 注意：volatile 只防編譯器最佳化，「不保證」原子性，也不能取代鎖。
static volatile uint32_t counter;
static volatile int lock_mode;             // 0=不鎖(錯), 1=spinlock, 2=critical_section
static spin_lock_t *lock;
static critical_section_t cs;

static void add_many(void) {
    for (int i = 0; i < N_ADD; i++) {
        if (lock_mode == 0) {
            counter++;                     // ❌ 讀-加-寫 三步，兩核交錯 → 遺失更新
        } else if (lock_mode == 1) {
            uint32_t save = spin_lock_blocking(lock);  // 拿鎖（同時關中斷）
            counter++;                     // ✅ 臨界區：只放「一定要保護」的那一行
            spin_unlock(lock, save);       // 放鎖（恢復中斷）
        } else {
            critical_section_enter_blocking(&cs);
            counter++;
            critical_section_exit(&cs);
        }
    }
    // ⭐ 更快的做法：各自先加到「區域變數」，最後只鎖一次加回去
    //    uint32_t local = 0; for (...) local++;
    //    uint32_t s = spin_lock_blocking(lock); counter += local; spin_unlock(lock, s);
}

// ---------------- 第 2 部分：工作佇列 ----------------
typedef struct { uint32_t id; const uint32_t *data; uint32_t n; } job_t;   // TODO(改這裡) 工作內容
typedef struct { uint32_t id; uint32_t sum; } result_t;                    // TODO(改這裡) 結果內容
static queue_t q_job, q_result;
static uint32_t data_buf[4][1024];                  // 4 塊資料輪流用

// SDK 預設 PICO_STDOUT_MUTEX=1：單一個 printf 本身就不會被另一核插隊；
// 這個 mutex 是給「好幾個 printf 要連在一起印」時用的
auto_init_mutex(print_mtx);
#define SAFE_PRINTF(...) do { mutex_enter_blocking(&print_mtx); printf(__VA_ARGS__); mutex_exit(&print_mtx); } while (0)

enum { CMD_RACE = 1, CMD_WORKER = 2, DONE = 0xD0E };

static void core1_main(void) {
    while (true) {
        // 硬體 FIFO：RP2350 每個方向深度 4 個 u32（RP2040 是 8）。launch 時 SDK 用 FIFO 做握手，
        // 但握手最後一步就是 core1 回傳 entry，core0 已讀走 → 進到這裡時 FIFO 是空的，不會讀到殘值。
        uint32_t cmd = multicore_fifo_pop_blocking();   // 等 core0 下命令
        __dmb();                                        // 保險：確保之後讀到的是 core0 在 push 前寫好的值
        if (cmd == CMD_RACE) {
            add_many();
            __dmb();                                    // 先讓 counter 的寫入完成，再通知 core0
            multicore_fifo_push_blocking(DONE);
        } else if (cmd == CMD_WORKER) {
            job_t j;
            while (true) {
                queue_remove_blocking(&q_job, &j);      // 拿一個工作（沒有就等）
                if (j.data == NULL) break;              // 約定：data==NULL 代表結束
                result_t r = { j.id, 0 };
                for (uint32_t i = 0; i < j.n; i++) r.sum += j.data[i];  // TODO(改這裡) 真正的計算
                queue_add_blocking(&q_result, &r);      // 回傳結果
            }
        }
    }
}

int main(void) {
    stdio_init_all();
    while (!stdio_usb_connected()) sleep_ms(50);       // 等電腦打開序列埠，不然前面的輸出會不見
    sleep_ms(200);

    lock = spin_lock_init((uint)spin_lock_claim_unused(true));  // 要一個沒人用的鎖(24~31號)並設成「未上鎖」
    critical_section_init(&cs);
    queue_init(&q_job, sizeof(job_t), 8);               // 元素大小、最多幾個
    queue_init(&q_result, sizeof(result_t), 8);
    multicore_launch_core1(core1_main);                 // core1 開始跑（stack = PICO_CORE1_STACK_SIZE，預設 0x800 = 2KB！）

    // ---- 第 1 部分：三種模式各跑一次 ----
    const char *name[] = { "不鎖(錯誤示範)", "spinlock", "critical_section" };
    for (int m = 0; m < 3; m++) {
        counter = 0;
        lock_mode = m;
        uint64_t t0 = time_us_64();
        __dmb();                                        // counter / lock_mode 寫好了才通知 core1
        multicore_fifo_push_blocking(CMD_RACE);         // 叫 core1 開始加
        add_many();                                     // core0 同時加
        multicore_fifo_pop_blocking();                  // 等 core1 做完
        __dmb();
        printf("%-18s counter=%lu (應為 %d)  %llu us\n", name[m],
               (unsigned long)counter, 2 * N_ADD, (unsigned long long)(time_us_64() - t0));
    }

    // ---- 第 2 部分：core0 派工、core1 計算 ----
    multicore_fifo_push_blocking(CMD_WORKER);
    uint64_t t0 = time_us_64();
    const int N_JOBS = 16;                              // TODO(改這裡)
    int sent = 0, got = 0;
    uint64_t total = 0;
    while (got < N_JOBS) {
        // 一次最多 4 個工作在跑（因為只有 4 塊 buffer，不能覆蓋還在算的資料）
        if (sent < N_JOBS && sent - got < 4) {
            uint32_t *buf = data_buf[sent % 4];
            for (int i = 0; i < 1024; i++) buf[i] = (uint32_t)(sent + i); // 模擬「收到資料」
            job_t j = { (uint32_t)sent, buf, 1024 };
            queue_add_blocking(&q_job, &j);
            sent++;
        }
        result_t r;
        if (queue_try_remove(&q_result, &r)) { total += r.sum; got++; }  // 不阻塞地收結果
    }
    job_t stop = { 0, NULL, 0 };
    queue_add_blocking(&q_job, &stop);                  // 叫 core1 的 worker 結束
    SAFE_PRINTF("worker: %d jobs, total=%llu\n", N_JOBS, (unsigned long long)total);
    PRINT_US("worker 總時間", t0);

    while (true) tight_loop_contents();
}
