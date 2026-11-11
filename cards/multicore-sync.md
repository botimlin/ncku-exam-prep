# 貼上卡：並行、臨界區與多核同步（pthread + RP2350 / pico-sdk）
> 用法：一次只複製一張卡（兩條分隔線之間），貼進對話，再在下面寫你的問題。每張 ≤ 1200 字元。
> 來源：full/domain/multicore-sync.md、lite/domain/multicore-sync.md（詳細版）｜最後更新 2026-11

---

【參考卡｜多核同步 1/8｜臨界區原則與「各自累加再合併」】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
適用：Linux pthread 與 RP2350（Pico 2）雙核 pico-sdk。
原則：
- `counter++` = 讀 → 加 → 寫三步，兩個執行緒 / 兩顆核同時做會掉更新（結果偏少、每次不同；單核可能剛好對）
- `volatile` 不是同步：不保證原子、不保證跨執行緒順序；只讓 race 更容易出現
- C11：兩執行緒存取同一非 atomic 物件、至少一方寫、沒有 happens-before → data race = UB
- 臨界區越短越好：計算、I/O、printf、malloc 移到鎖外；鎖內只做讀 / 寫；鎖內不呼叫會阻塞的函式
- 最快是不共享：每執行緒 / 每核累加區域變數，最後合併一次
- 單一整數 → atomic；多欄位一起改 → 鎖
- 執行緒數 > CPU 數（`nproc`）時 spinlock 空轉 → 改 mutex
- Linux false sharing：各執行緒寫的變數 `alignas(64)` 分開（RP2350 無 data cache，沒有這問題）
正解範例（demo counter，連 sink 的 race 一起修）：
```c
static atomic_long counter;
static void *worker_partitioned(void *arg) {
    (void)arg;
    long local = 0;
    uint32_t local_sink = 0;
    for (int i = 0; i < ROUNDS; i++) {
        local_sink += work(i);
        local++;
    }
    atomic_fetch_add_explicit(&counter, local, memory_order_relaxed);
    return (void *)(uintptr_t)local_sink;
}
```
- main 在 `pthread_join` 之後讀 counter（join 建立 happens-before，relaxed 就夠）
- 同步次數從 N×ROUNDS 降到 N 次
- demo 的 `sink += work(i)` 沒鎖也是 race

---

【參考卡｜多核同步 2/8｜POSIX pthread API 與工具（Linux）】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
```c
pthread_mutex_t m = PTHREAD_MUTEX_INITIALIZER;
pthread_mutex_lock(&m); pthread_mutex_unlock(&m);
pthread_mutex_trylock(&m);                 // 拿不到回傳 EBUSY
pthread_spin_init(&l, PTHREAD_PROCESS_PRIVATE);
pthread_spin_lock(&l); pthread_spin_unlock(&l);
```
- 所有 pthread 函式成功回 0，失敗回傳錯誤碼（不設 errno）
- 同一把 spinlock 重複 lock 或 unlock 沒持有的鎖：UB
- mutex 拿不到會睡（futex），適合一般情況；spinlock 忙等，只適合持鎖極短且每執行緒獨佔一核
條件變數（一定用 while，有虛假喚醒）：
```c
pthread_mutex_lock(&m);
while (count == 0)
    pthread_cond_wait(&not_empty, &m);
/* 取資料 */
pthread_cond_signal(&not_full);
pthread_mutex_unlock(&m);
```
- 改條件後持鎖時 signal；關閉時 broadcast
Semaphore：`sem_init(&s, 0, n)`、`sem_wait`、`sem_trywait`、`sem_post`；失敗回 -1 並設 errno（sem_wait 可能 EINTR）
- 其他：rwlock、`pthread_barrier_wait`、`pthread_once`
Deadlock：固定拿鎖順序（例如先拿位址小的）
量測：`clock_gettime(CLOCK_MONOTONIC, &ts)`；多跑取中位數；先暖身；`-O2`；執行緒只建立一次
- Amdahl：S = 1/((1-p)+p/N)；p=0.9、N=2 → 約 1.82 倍；2 核最多 2 倍
工具：
- 編譯加 `-pthread`
- `gcc -fsanitize=thread -g -O1`（慢 5–15 倍，不能和 address 同用）
- `valgrind --tool=helgrind`
- 卡住：gdb `thread apply all bt`
- `time`：user 很高但 real 沒降 → spinlock 空轉

---

【參考卡｜多核同步 3/8｜C11 atomics 與 memory order】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
適用：Linux 與 RP2350（Pico 2）。
```c
#include <stdatomic.h>
atomic_long counter = 0;
atomic_fetch_add(&counter, 1);         // 回傳舊值，預設 seq_cst
atomic_fetch_add_explicit(&counter, 1, memory_order_relaxed);
long v = atomic_load_explicit(&counter, memory_order_acquire);
atomic_store_explicit(&flag, 1, memory_order_release);
long expected = atomic_load(&x);
while (!atomic_compare_exchange_weak(&x, &expected, expected * 2)) { }
```
- compare_exchange_weak 可能偽失敗 → 放迴圈；失敗時 expected 被更新成目前值
- atomic_flag 是唯一保證 lock-free 的型別
memory order：
- relaxed：只保證本身原子；用於計數（join 後才讀）
- acquire（load）：之後的讀寫不會移到前面
- release（store）：之前的讀寫不會移到後面
- seq_cst（預設）：不確定時用
- 發布資料：寫資料 → release store 旗標；讀方 acquire load 讀到旗標後看得到資料
限制：
- 很多執行緒狂打同一 atomic 仍慢 → 各自累加再合併
- 兩個 atomic 各自原子，合起來不是原子 → 要一起改用鎖
RP2350：
- 1/2/4 byte 對齊的 atomic 是 lock-free（Arm ldrex/strex、RISC-V lr/sc/amo）；64-bit 由 pico_atomic 用 spinlock 保護
- RP2040 全部用 spinlock 模擬
- exclusive 只在 SRAM 有效（flash/XIP 一律失敗）→ atomic 變數放 SRAM；reservation granule 16 bytes
- 兩核對同一 16-byte 區塊內不同變數做 atomic 會互相干擾 ⚠️未驗證（推論）

---

【參考卡｜多核同步 4/8｜pico 多核 API：launch、FIFO、queue_t】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
平台：RP2350（Pico 2），非 RP2040。CMake `target_link_libraries(app pico_stdlib pico_multicore)`；`#include "pico/multicore.h"`、`"pico/util/queue.h"`。
啟動 core1：
- `multicore_launch_core1(void (*entry)(void))`；`multicore_reset_core1()`（只能 core0 呼叫）
- launch 內部用 FIFO 握手 → launch 前不要在 FIFO 放自己的資料
- core1 stack 預設 2 kB（`PICO_CORE1_STACK_SIZE`）在 SCRATCH_X（4 kB）→ 大陣列改 static，或調大 stack
- core1 entry 寫成 `while (1)` 不返回；`get_core_num()` 回 0 或 1
FIFO：
- RP2350 每方向只有 4 格 × 32 bit（RP2040 是 8 格）
- `multicore_fifo_push_blocking(u32)`、`multicore_fifo_pop_blocking()`、`_rvalid()`、`_wready()`、`_drain()`、`_push_timeout_us`、`_pop_timeout_us`
- 滿了還寫 → 丟棄並設 WOF；空了還讀 → 無效值並設 ROE
- 只傳指標或索引；SDK 建議資料傳遞優先用 queue_t（FIFO 被 launch、lockout 佔用）
- 兩核 FIFO IRQ 共用 `SIO_IRQ_FIFO`
queue_t（跨核 + IRQ 安全）：
```c
queue_init(&q, sizeof(job_t), 4);
queue_add_blocking(&q, &j);
queue_remove_blocking(&q, &j);
queue_try_add(&q, &j);      // 滿 → false
queue_try_remove(&q, &j);   // 空 → false
```
- 元素 memcpy 複製；內部 calloc（失敗回 false）
- ISR 中只用 `queue_try_*`
- queue 先初始化，再 launch core1
- 傳 buffer 指標時，交出後到拿回前生產者不能再碰（所有權轉移）

---

【參考卡｜多核同步 5/8｜pico 鎖：critical_section、mutex、sem、spinlock、E2】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
平台：RP2350（Pico 2）pico-sdk，`#include "pico/sync.h"`、`"hardware/sync.h"`。
- `critical_section_init(&cs)` / `_enter_blocking` / `_exit`：關本核 IRQ + spinlock → 跨核 + ISR 都安全；極短；不可重入（巢狀要 `critical_section_init_with_lock_num` 給不同編號）
- `mutex_init` / `mutex_enter_blocking` / `mutex_exit` / `mutex_try_enter(&m, NULL)`：可持有較久；同核再 enter 會 deadlock（用 recursive_mutex_t）；ISR 不可阻塞，只能 try
- `sem_init(&s, init, max)`、`sem_acquire_blocking`、`sem_release`（ISR 可呼叫）；名稱不同於 POSIX
- spinlock：
```c
lk = spin_lock_init(spin_lock_claim_unused(true));
uint32_t save = spin_lock_blocking(lk);
shared_x++;
spin_unlock(lk, save);
```
  只能持有很短；持有時不拿別的 spinlock；不可重入
- `save_and_disable_interrupts()` / `restore_interrupts(s)` 只擋本核
- `multicore_lockout_*` 不是資料鎖（寫 flash 用）
RP2350-E2 erratum：
- 寫 SIO 0x180–0x1FC 會誤釋放低 0x80 的硬體 spinlock（A2/A3/A4 皆有）
- SDK 預設 `PICO_USE_SW_SPIN_LOCKS`（RAM 中軟體 spinlock），API 不變
- 不要直接寫 `sio_hw->spinlock[]`（RP2040 舊寫法）；編號用 `PICO_SPINLOCK_ID_*`
選哪個：
- 單一 32-bit 計數 / 旗標跨核 → C11 atomic
- 幾個欄位一起改、ISR 或另一核會碰 → critical_section_t
- 持有較久、只有兩核主程式碰 → mutex_t
- 通知 → semaphore_t；傳資料 → queue_t；只有同核 ISR 與主迴圈 → 關中斷

---

【參考卡｜多核同步 6/8｜ISR 與主迴圈共享變數】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
平台：RP2350（Pico 2）pico-sdk 裸機。
```c
static volatile bool data_ready;
static volatile uint32_t sample;
void my_isr(void) {
    sample = read_hw();
    data_ready = true;
}
int main(void) {
    while (true) {
        if (data_ready) {
            uint32_t save = save_and_disable_interrupts();
            uint32_t s = sample;
            data_ready = false;
            restore_interrupts(save);
            handle(s);
        }
    }
}
```
規則：
- 同核 ISR ↔ 主迴圈：單一對齊 32-bit 旗標用 volatile 是嵌入式慣例（C 標準正式只保證 volatile sig_atomic_t）
- 多欄位或 RMW（`count++`）→ 主程式那側關中斷，或用 atomic
- 64-bit 變數在 32-bit 核心上讀寫不是一條指令 → 會讀到一半新一半舊，一定要保護
- ISR 與另一核共享 → 只關中斷不夠，用 critical_section_t、atomic 或 queue_t
- 關中斷時間越短越好（會延誤 timer、USB、UART）；處理放在關中斷區外
- ISR 內不要 printf、不要阻塞（不呼叫 mutex_enter_blocking、queue_add_blocking）、不要拿主程式可能長時間持有的鎖 → 會直接 deadlock
- ISR 中用 `_try_` 版本（queue_try_add、mutex_try_enter）；sem_release 可在 ISR
- stdout 有 mutex：兩核 printf 不會撕裂但順序不定；熱迴圈與臨界區內不要 printf

---

【參考卡｜多核同步 7/8｜RP2350 雙核分工、SRAM bank、DMA】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
平台：RP2350（Pico 2），2 核，最多 2 倍加速。
資料分割（每核一半，各自累加，最後合併）：
```c
static void core1_main(void) {
    core1_result = sum_range(N / 2, N);
    __dmb();
    multicore_fifo_push_blocking(1);
    while (true) __wfi();
}
// core0：
multicore_launch_core1(core1_main);
int64_t s0 = sum_range(0, N / 2);
(void)multicore_fifo_pop_blocking();
__dmb();
int64_t total = s0 + core1_result;
```
- FIFO 本身不是 C 層級 barrier → push 前、pop 後各 `__dmb()`；或結果放 queue_t
- launch 握手也算時間；重複使用時 core1 常駐、用 queue 派工
- pipeline：吞吐量取決於最慢階段
SRAM：
- 0x20000000 起 256 kB 交錯 SRAM0–3、0x20040000 起 256 kB 交錯 SRAM4–7（每 4 bytes 換 bank）
- SRAM8 0x20080000 = SCRATCH_X（core1 stack）、SRAM9 0x20081000 = SCRATCH_Y（core0 stack），各 4 kB
- 不同 bank 可同週期並行；兩核 / DMA 搶同 bank 才互等
- 單核熱資料 `__scratch_x("name")`；熱函式 `__not_in_flash_func(f)`
DMA（RP2350 16 channel）：
- `dma_claim_unused_channel(true)` → `dma_channel_get_default_config(ch)` → `channel_config_set_write_increment(&c, true)`（預設 write 不遞增！）→ `dma_channel_configure(ch, &c, dst, src, dma_encode_transfer_count(N), true)`（N 是筆數不是 bytes）→ 做別的事 → `dma_channel_wait_for_finish_blocking(ch)` 後才讀 dst

---

【參考卡｜多核同步 8/8｜常見 bug → 症狀 → 修法】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
適用：Linux pthread 與 RP2350（Pico 2）pico-sdk。
| Bug | 症狀 | 修法 |
|---|---|---|
| 共享 counter++ 沒保護 | 結果偏少、每次不同 | 區域累加合併；atomic；短鎖 |
| 耗時計算在鎖內 | 對但比單執行緒慢 | 計算移到鎖外 |
| 以為 volatile 安全 | 偶爾錯、TSan 報 race | _Atomic 或鎖 |
| cond_wait 用 if | 取到垃圾值 | 改 while |
| 忘了 signal/broadcast | 永遠睡著 | 持鎖時 signal；關閉時 broadcast |
| 兩把鎖順序不一致 | 偶爾卡死 | 固定拿鎖順序 |
| 早 return 忘 unlock | 下次 lock 卡死 | 每條路徑都 unlock |
| 單 CPU 用 spinlock | 很慢、user 時間高 | 改 mutex |
| partial[id] 相鄰 | 加執行緒反而慢 | alignas(64) 或區域變數 |
| 沒 join 就讀結果 | 結果不完整 | join 後才讀 |
| core1 stack overflow | core1 當機、HardFault | 大陣列 static；調大 PICO_CORE1_STACK_SIZE |
| 自用 FIFO 又用 lockout | 怪值、卡住 | 改 queue_t |
| FIFO 滿還寫 | 資料遺失、WOF=1 | _blocking 或先查 wready |
| 只關中斷當跨核保護 | 另一核仍在改 | critical_section_t |
| ISR 呼叫 _blocking | 系統卡死 | ISR 用 _try_ |
| 巢狀 critical_section 同一把鎖 | 卡死 | _init_with_lock_num 不同編號 |
| 直接寫 SIO spinlock | 鎖被莫名釋放（E2） | 用 SDK API |
| DMA 未完成就讀 dst | 舊 / 部分資料 | wait_for_finish 後讀 |
| DMA count 填 bytes | 寫超過 buffer | count = bytes / 每筆大小 |
| 64-bit 共享被 ISR 改 | 一半新一半舊 | 關中斷 / critical_section |
| 熱迴圈 printf | 很慢、順序亂 | 先存起來最後印 |
