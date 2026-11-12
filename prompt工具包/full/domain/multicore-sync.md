# 並行、臨界區與多核同步（POSIX threads + RP2350 / pico-sdk）

> 用途：處理「多執行緒 / 雙核共享資料、鎖、效能優化」類題目時的參考。Part A 是 Linux / POSIX（考前 demo `section2-3/critical-section` 就在 Linux 上跑）；Part B 是 RP2350 + pico-sdk（考場 Dockerfile 註解提到正式環境有 pico-sdk、cross toolchain、judge 與開發板，推測為 Raspberry Pi Pico 2 / RP2350）。
> 適用版本：POSIX.1-2024 / glibc pthreads；C11 `<stdatomic.h>`；pico-sdk 2.3.1（2026-09 release，也就是目前 master）；RP2350 datasheet build 2026-01-10（晶片版本 A2/A3/A4）。RP2040 不同之處會特別標出。
> 來源（實際查證過）：
> - pico-sdk 原始碼 https://github.com/raspberrypi/pico-sdk （`src/rp2_common/pico_multicore/include/pico/multicore.h`、`multicore.c`、`src/rp2_common/hardware_sync/include/hardware/sync.h`、`src/rp2_common/hardware_sync_spin_lock/include/hardware/sync/spin_lock.h`、`src/common/pico_sync/include/pico/{critical_section,mutex,sem,lock_core}.h`、`src/common/pico_util/include/pico/util/queue.h`、`src/common/pico_util/queue.c`、`src/common/pico_time/include/pico/time.h`、`src/rp2_common/hardware_timer/include/hardware/timer.h`、`src/rp2_common/hardware_dma/include/hardware/dma.h`、`src/rp2_common/pico_atomic/`、`src/rp2_common/pico_platform_sections/include/pico/platform/sections.h`、`src/rp2350/pico_platform/script_include/default_locations.ld`、`src/rp2_common/pico_standard_link/script_include/sections_stack.incl`、`src/rp2350/hardware_regs/include/hardware/platform_defs.h`、`.../regs/addressmap.h`、`src/rp2_common/pico_stdio/stdio.c`）
> - RP2350 datasheet https://datasheets.raspberrypi.com/rp2350/rp2350-datasheet.pdf （§2.1 Bus fabric、§2.1.6 Global Exclusive Monitor、§2.2.3 SRAM、§3.1.4 Spinlocks、§3.1.5 FIFOs、§4.2 SRAM、附錄 D.9.2 RP2350-E2）
> - man7.org：pthread_spin_init(3)、pthread_spin_lock(3)、sem_init(3)、clock_gettime(2)；POSIX pthread_cond_wait（pubs.opengroup.org/onlinepubs/9799919799）
> - cppreference：atomic_fetch_add、memory_order、atomic_flag_test_and_set
> - clang.llvm.org/docs/ThreadSanitizer.html、valgrind.org/docs/manual/hg-manual.html
> 最後更新：2026-11
>
> 給模型的說明：本檔所有 pico-sdk API 名稱與簽名都對照過 SDK 2.3.1 標頭檔。若考場提供的 SDK 版本或題目文件與本檔衝突，**以考場文件為準**。標 ⚠️未驗證 的是推論或沒找到一手來源的內容。

---

## 0. 一頁總結（先看這裡）

1. `counter++` = 讀 → 加 → 寫三步。兩個執行緒 / 兩顆核同時做會掉更新（lost update）。這就是 demo 第 1 行少掉幾百的原因。
2. 鎖保護的那一段叫臨界區。**鎖要抓得越短越好**：耗時的計算放在鎖外面（demo 第 2 行對、第 3 行慢一倍以上就是在示範這點）。
3. 最快的同步是**根本不共享**：每個執行緒 / 每顆核先累加自己的區域變數，最後合併一次。
4. 真的必須共享：單一整數 → C11 atomic；多個欄位要一起改 → mutex（Linux）/ `critical_section_t` 或 `mutex_t`（pico）。
5. `volatile` **不是**同步工具：不保證原子性，也不保證跨執行緒的順序。
6. Linux：多個執行緒各自寫的變數如果擠在同一條 cache line（x86 通常 64 bytes）就是 false sharing，要 padding。
7. RP2350：兩顆核心；SIO 的 inter-core FIFO **每個方向只有 4 格**（RP2040 是 8 格）；32 個 hardware spinlock 有 erratum **RP2350-E2**，所以 SDK 在 RP2350 上預設改用**軟體 spinlock**（`PICO_USE_SW_SPIN_LOCKS`）。
8. RP2350 SRAM：0x20000000–0x2007FFFF 共 512 kB，分兩個 256 kB 區，各自以 word 為單位交錯（striped）分到 4 個 bank；另外 SRAM8 / SRAM9（各 4 kB）不交錯，即 scratch X / scratch Y，預設放 core1 / core0 的 stack。
9. 量測：Linux 用 `clock_gettime(CLOCK_MONOTONIC)`；pico 用 `time_us_64()` 或 `get_absolute_time()` 搭配 `absolute_time_diff_us()`。
10. 偵測 data race：`gcc -fsanitize=thread -g -O1`（ThreadSanitizer），或 `valgrind --tool=helgrind`。

---

# Part A：通用 / POSIX（Linux）

## A1. Race condition 與 read-modify-write

### A1.1 demo 在示範什麼

`section2-3/critical-section/main.c` 的三種 worker：

| 版本 | 寫法 | 結果 | 原因 |
|---|---|---|---|
| `worker_unlocked` | `long v = counter; counter = v + 1;` | 少於 40000，每次不同 | 讀和寫之間另一個執行緒插進來，其中一次更新被覆蓋 |
| `worker_locked` | `work()` 在鎖外，鎖內只有 `counter++` | 40000，時間跟無鎖差不多 | 臨界區只有一行 |
| `worker_locked_too_long` | `work()` 也放進鎖內 | 40000，但慢一倍以上 | 兩個 worker 輪流做，等於退回單執行緒 |

交錯示意（兩個執行緒，counter 原本是 5）：

```
T1: v = counter (5)
                        T2: v = counter (5)
T1: counter = v+1 (6)
                        T2: counter = v+1 (6)   ← T1 的 +1 消失
```

### A1.2 demo 裡值得注意的細節（讀程式碼時會被問到的點）

- `static volatile long counter;` 的註解說 volatile 是為了讓每次 `++` 真的讀寫記憶體，好讓三步拆開看得到。**volatile 只是讓 race 更容易出現，並沒有修好它**。
- `sink += work(i);` 在兩個執行緒裡都沒有鎖，本身也是一個 data race（`sink` 只是用來防止編譯器把 `work()` 刪掉）。ThreadSanitizer 會回報它。如果題目要你「修正所有 race」，`sink` 也要改成每執行緒區域變數，最後再合併。
- 用 `pthread_spinlock_t`，而且 `usable_cpus()` 會提醒只有 1 顆 CPU 時第 1 行可能顯示 ok。只有 1 顆 CPU 時 spinlock 特別糟：持鎖的執行緒被換下 CPU 後，另一個執行緒會空轉一整個 time slice（見 A3）。
- `transfer-engine/engine.c` 的 `volatile bool busy` 由引擎執行緒寫、主執行緒輪詢。照 C11 這也是 data race；真正讓主執行緒看得到 `dst` 內容的，是 `engine_wait()` 裡的 `pthread_join()`（join 建立 happens-before）。正規寫法是 `atomic_bool busy` 搭配 release store / acquire load。

### A1.3 C11 的規則

- 兩個執行緒存取同一個非 atomic 物件、至少一方是寫入、而且之間沒有 happens-before 關係，就是 **data race，屬於未定義行為（UB）**。編譯器可以假設沒有 race 來做最佳化（例如把迴圈裡的讀取提到迴圈外）。
- 建立 happens-before 的方法：mutex 的 unlock → 下一次 lock、atomic 的 release → acquire、`pthread_create`（建立前的動作對新執行緒可見）、`pthread_join`（被 join 的執行緒做的事對 join 之後可見）。

---

## A2. 臨界區（Critical Section）

- 臨界區：存取共享資料、同一時間只能有一個執行者的程式段。
- 三個要求：互斥（mutual exclusion）、有進展（progress）、有限等待（bounded waiting）。
- 原則：
  1. **只鎖存取共享資料的那幾行**。計算、I/O、`printf`、`malloc` 都移到鎖外。
  2. 先在鎖外把要寫的值算好，鎖內只做「讀 / 寫」。
  3. 鎖內不要呼叫可能阻塞的函式（`sleep`、I/O、等另一把鎖）。

```c
// 不好：計算在鎖內
pthread_mutex_lock(&m);
result = expensive(x);
table[k] = result;
pthread_mutex_unlock(&m);

// 好：計算在鎖外，鎖內只寫入
int r = expensive(x);
pthread_mutex_lock(&m);
table[k] = r;
pthread_mutex_unlock(&m);
```

---

## A3. Mutex vs Spinlock

### A3.1 API

```c
#include <pthread.h>

// mutex
pthread_mutex_t m = PTHREAD_MUTEX_INITIALIZER;            // 靜態初始化
int pthread_mutex_init(pthread_mutex_t *m, const pthread_mutexattr_t *attr);
int pthread_mutex_lock(pthread_mutex_t *m);
int pthread_mutex_trylock(pthread_mutex_t *m);            // 拿不到回傳 EBUSY
int pthread_mutex_unlock(pthread_mutex_t *m);
int pthread_mutex_destroy(pthread_mutex_t *m);

// spinlock
int pthread_spin_init(pthread_spinlock_t *lock, int pshared); // PTHREAD_PROCESS_PRIVATE / _SHARED
int pthread_spin_lock(pthread_spinlock_t *lock);
int pthread_spin_trylock(pthread_spinlock_t *lock);       // 拿不到回傳 EBUSY
int pthread_spin_unlock(pthread_spinlock_t *lock);
int pthread_spin_destroy(pthread_spinlock_t *lock);
```

- 所有 pthread 函式成功回傳 0，失敗**回傳錯誤碼**（不設 `errno`）。
- 對同一把 spinlock 重複 lock（自己已持有）或 unlock 沒持有的鎖：未定義行為（man pthread_spin_lock）。

### A3.2 比較

| | mutex（glibc，底層 futex） | spinlock |
|---|---|---|
| 拿不到鎖時 | 經 futex 進 kernel 睡眠，讓出 CPU（glibc 預設型別不先自旋；`PTHREAD_MUTEX_ADAPTIVE_NP` 才會先短暫自旋） | 一直忙等（busy-wait），持續佔 CPU |
| 沒有競爭時成本 | 很低（user space 一次 atomic 操作） | 很低 |
| 適合 | 一般情況；持鎖時間不確定；執行緒數 > 核心數 | 持鎖極短、每個執行緒獨佔一顆核、不會被搶占 |
| 持鎖者被搶占時 | 等待者睡覺，損失小 | 等待者空轉整個 time slice，損失大 |

man pthread_spin_init 的建議：大多數程式應該用 mutex；spinlock 搭配 real-time 排程（`SCHED_FIFO`）才合理，在一般 `SCHED_OTHER` 下使用通常代表設計有問題。

**考場判斷**：容器可能只給 1–2 顆 CPU（demo 也特別提醒）。執行緒數 > 可用 CPU 數時，spinlock 可能比 mutex 慢很多。先 `nproc` 確認。

### A3.3 其他 pthread 工具

```c
// 讀寫鎖：讀多寫少時讓多個讀者並行
pthread_rwlock_t rw = PTHREAD_RWLOCK_INITIALIZER;
pthread_rwlock_rdlock(&rw); /* 讀 */ pthread_rwlock_unlock(&rw);
pthread_rwlock_wrlock(&rw); /* 寫 */ pthread_rwlock_unlock(&rw);

// barrier：所有執行緒到齊才往下走（分階段計算）
pthread_barrier_t b;
pthread_barrier_init(&b, NULL, NTHREADS);
pthread_barrier_wait(&b);   // 其中一個執行緒會拿到 PTHREAD_BARRIER_SERIAL_THREAD，其他拿到 0

// once：只初始化一次
pthread_once_t once = PTHREAD_ONCE_INIT;
pthread_once(&once, init_fn);
```

---

## A4. 條件變數（Condition Variable）

規則：**一定要在 while 迴圈裡等**。POSIX 允許虛假喚醒（spurious wakeup），被喚醒也不代表條件已成立（可能被別的執行緒先搶走）。

```c
pthread_mutex_t m = PTHREAD_MUTEX_INITIALIZER;
pthread_cond_t  not_empty = PTHREAD_COND_INITIALIZER;
pthread_cond_t  not_full  = PTHREAD_COND_INITIALIZER;
int buf[CAP], head = 0, tail = 0, count = 0;

void put(int x) {
    pthread_mutex_lock(&m);
    while (count == CAP)                       // while，不是 if
        pthread_cond_wait(&not_full, &m);      // 會原子地「解鎖並睡覺」，醒來時已重新持鎖
    buf[tail] = x; tail = (tail + 1) % CAP; count++;
    pthread_cond_signal(&not_empty);
    pthread_mutex_unlock(&m);
}

int get(void) {
    pthread_mutex_lock(&m);
    while (count == 0)
        pthread_cond_wait(&not_empty, &m);
    int x = buf[head]; head = (head + 1) % CAP; count--;
    pthread_cond_signal(&not_full);
    pthread_mutex_unlock(&m);
    return x;
}
```

| 函式 | 說明 |
|---|---|
| `pthread_cond_wait(cond, mutex)` | 呼叫前必須持有 mutex |
| `pthread_cond_timedwait(cond, mutex, abstime)` | `abstime` 是絕對時間（預設用 `CLOCK_REALTIME`）；逾時回傳 `ETIMEDOUT` |
| `pthread_cond_signal(cond)` | 至少喚醒一個等待者 |
| `pthread_cond_broadcast(cond)` | 喚醒全部（例如要關閉、或有多種不同條件時） |

常見錯誤：先改條件再 signal 時沒持鎖 → lost wakeup；用 `if` 而不是 `while`；關閉時忘記 broadcast，執行緒永遠卡住。

---

## A5. Semaphore（POSIX unnamed）

```c
#include <semaphore.h>
int sem_init(sem_t *sem, int pshared, unsigned int value);  // pshared=0：同一 process 的執行緒間共用
int sem_wait(sem_t *sem);       // 值 > 0 就減 1，否則阻塞
int sem_trywait(sem_t *sem);    // 不阻塞；失敗回傳 -1，errno = EAGAIN
int sem_post(sem_t *sem);       // 加 1，喚醒一個等待者
int sem_destroy(sem_t *sem);
```

- 注意：`sem_*` 失敗是回傳 **-1 並設 `errno`**（跟 pthread 回傳錯誤碼不同）。`sem_wait` 可能被 signal 中斷，回傳 -1 並設 `errno = EINTR`，必要時要重試。
- 用途：限制同時存取資源的數量（計數）、單向通知（「資料好了」）。
- 用兩個 semaphore（空格數 / 資料數）+ 一把 mutex 也可以寫出 bounded buffer。

---

## A6. C11 Atomics（`<stdatomic.h>`）

### A6.1 常用 API

```c
#include <stdatomic.h>

atomic_long counter = 0;                 // 或 _Atomic long counter;
atomic_fetch_add(&counter, 1);           // 回傳「加之前的舊值」，預設 seq_cst
atomic_fetch_add_explicit(&counter, 1, memory_order_relaxed);
long v = atomic_load_explicit(&counter, memory_order_acquire);
atomic_store_explicit(&flag, 1, memory_order_release);
long old = atomic_exchange(&x, 42);

// CAS：比較並交換。失敗時 expected 會被更新成目前的值
long expected = atomic_load(&x);
while (!atomic_compare_exchange_weak(&x, &expected, expected * 2)) { /* 重試 */ }

// atomic_flag：唯一保證 lock-free 的型別
atomic_flag f = ATOMIC_FLAG_INIT;
while (atomic_flag_test_and_set_explicit(&f, memory_order_acquire)) ;  // 回傳舊值：true 代表已被別人拿走
/* 臨界區 */
atomic_flag_clear_explicit(&f, memory_order_release);

atomic_thread_fence(memory_order_seq_cst);   // 獨立的 fence
atomic_is_lock_free(&counter);               // 這個物件是否不靠鎖實作
```

- `compare_exchange_weak` 可能偽失敗（spurious failure），所以要放在迴圈裡；`_strong` 不會偽失敗。
- 其他 fetch 系列：`atomic_fetch_sub / _or / _and / _xor`，同樣回傳舊值。

### A6.2 Memory order 速查

| order | 保證 | 典型用途 |
|---|---|---|
| `memory_order_relaxed` | 只保證這個操作本身是原子的，不保證和其他記憶體操作的順序 | 單純計數器、統計值（最後 join 之後才讀） |
| `memory_order_acquire`（load） | 這個 load 之後的讀寫不會被移到它前面 | 消費者讀「資料已就緒」旗標 |
| `memory_order_release`（store） | 這個 store 之前的讀寫不會被移到它後面 | 生產者寫完資料後設旗標 |
| `memory_order_acq_rel`（RMW） | 同時有 acquire 和 release | CAS 實作的鎖 / 堆疊 |
| `memory_order_seq_cst`（預設） | acq_rel，再加上所有 seq_cst 操作有一個全域一致的順序 | 不確定時用它，正確性優先 |

**release/acquire 配對**：執行緒 A 先寫資料、再 release-store 旗標；執行緒 B acquire-load 讀到該旗標後，保證看得到 A 在 store 之前寫的所有資料。

### A6.3 atomic 不是萬靈丹

- 每次 atomic RMW 都要獨佔那條 cache line。很多執行緒狂打同一個 atomic counter，效能仍然很差（cache line 在核心間來回搬，cache-line bouncing）。→ 用 A9 的「各自累加再合併」。
- 兩個 atomic 變數各自原子，**合起來不是原子**（例如 `a` 和 `b` 要一起改）。這種情況要用鎖。

---

## A7. 為什麼 `volatile` 不是同步

| `volatile` 會做的 | `volatile` 不會做的 |
|---|---|
| 每次存取都真的讀寫記憶體，不被快取在暫存器 | 讓 `x++` 變成原子操作 |
| 不刪除、不合併 volatile 存取 | 阻止非 volatile 存取跨越它被重排 |
| 適合 MMIO 暫存器（硬體會自己改值） | 阻止 CPU 層級的重排 / 提供 memory barrier |
|  | 讓 data race 變成合法（照 C11 仍然是 UB） |

結論：執行緒之間共享 → 用 `_Atomic` 或鎖；硬體暫存器 → 用 `volatile`；ISR 與主程式之間 → 見 B8。

---

## A8. False sharing 與 cache-line padding

- CPU cache 以 cache line（x86-64 通常 64 bytes；Apple M 系列是 128 bytes）為單位維持一致性。兩個執行緒寫**不同變數**，只要它們在**同一條 line**，就會互相使對方的 cache 失效，效能可能掉好幾倍，而且結果仍然正確，很難察覺。
- 典型地雷：`long partial[NTHREADS];` 每個執行緒寫 `partial[id]`。8 個 long 剛好 64 bytes，全部擠在同一條 line。

```c
#include <stdalign.h>
#define CACHELINE 64

typedef struct {
    alignas(CACHELINE) long value;   // 對齊到 64，struct 大小也會補到 64 的倍數
} padded_long;

padded_long partial[NTHREADS];       // 每個元素各佔一條 cache line
```

- 更好的做法：迴圈內累加**區域變數**（在暫存器 / 自己的 stack 上），迴圈結束才寫回共享陣列一次。這樣 false sharing 也只會發生一次。
- 查 cache line 大小：`getconf LEVEL1_DCACHE_LINESIZE`，或 `cat /sys/devices/system/cpu/cpu0/cache/index0/coherency_line_size`。
- 工具：`perf c2c`（若環境有 perf）可以找出 false sharing。
- **RP2350 注意**：Cortex-M33 / Hazard3 對 SRAM 沒有 data cache（晶片上唯一的 cache 是 16 kB 的 XIP cache），所以沒有 x86 那種 cache-line false sharing。對應的問題是 **SRAM bank 衝突**（B9）和 **exclusive monitor 的 16-byte reservation granule**（B4.4）。

---

## A9. 經典修法：各自累加，最後合併（demo counter 的正解）

```c
#define _GNU_SOURCE
#include <pthread.h>
#include <stdatomic.h>
#include <stdint.h>

#define WORKERS 2
#define ROUNDS  20000

static atomic_long counter;            // 只在最後合併時碰一次

static void *worker_partitioned(void *arg) {
    (void)arg;
    long local = 0;                    // 區域變數：沒有共享，不需要鎖
    uint32_t local_sink = 0;           // 連 sink 的 race 一起修掉
    for (int i = 0; i < ROUNDS; i++) {
        local_sink += work(i);
        local++;
    }
    atomic_fetch_add_explicit(&counter, local, memory_order_relaxed);  // 每個執行緒只做一次
    return (void *)(uintptr_t)local_sink;   // 或寫進 padded 的陣列
}
// main：pthread_join 之後讀 counter 就是正確值（join 建立 happens-before，relaxed 就夠了）
```

各種方法比較：

| 方法 | 同步次數 | 正確 | 擴展性 |
|---|---|---|---|
| 無鎖 `counter++` | 0 | 錯 | — |
| 每次都鎖 | N×ROUNDS | 對 | 差（全部排隊） |
| 每次 `atomic_fetch_add` | N×ROUNDS 次 atomic | 對 | 普通（cache line 來回搬） |
| **區域累加 + 結束時合併一次** | N 次 | 對 | 最好 |

同樣的模式也能用在：直方圖（每執行緒一份 histogram，最後逐格相加）、求最大值、找符合條件的元素個數。

如果題目規定「每次都要立刻更新共享值」（例如別的執行緒會即時讀），才退而求其次用 atomic 或短鎖。

---

## A10. 鎖的粒度（granularity）

| 粒度 | 做法 | 優點 | 缺點 |
|---|---|---|---|
| 粗（一把大鎖） | 整個資料結構一把鎖 | 簡單、不容易 deadlock | 並行度低 |
| 細（每個元素 / 每個 bucket 一把） | hash table 每個 bucket 一把鎖 | 並行度高 | 鎖數多、記憶體多；要同時拿兩把時容易 deadlock |
| Lock striping | K 把鎖，元素 `i` 用 `locks[i % K]` | 折衷 | 要決定 K |
| 無鎖（lock-free） | atomic + CAS | 沒有 deadlock | 難寫、難驗證 |

改細鎖前先量測：如果 contention 本來就低，改了也不會快。

---

## A11. 生產者-消費者：SPSC lock-free ring buffer

單一生產者、單一消費者（SPSC）時，不需要鎖：`head` 只有生產者寫，`tail` 只有消費者寫。

```c
#include <stdatomic.h>
#include <stdalign.h>
#include <stdbool.h>
#include <stddef.h>

#define RB_SIZE 1024                     // 必須是 2 的次方
#define RB_MASK (RB_SIZE - 1)

typedef struct {
    alignas(64) atomic_size_t head;      // 生產者寫，消費者讀
    alignas(64) atomic_size_t tail;      // 消費者寫，生產者讀
    alignas(64) int buf[RB_SIZE];
} ring_t;

bool rb_push(ring_t *r, int v) {         // 只有生產者呼叫
    size_t h = atomic_load_explicit(&r->head, memory_order_relaxed);   // 自己寫的，relaxed 即可
    size_t t = atomic_load_explicit(&r->tail, memory_order_acquire);   // 看見消費者已讀走的空間
    if (h - t == RB_SIZE) return false;                                // 滿
    r->buf[h & RB_MASK] = v;                                           // 先寫資料
    atomic_store_explicit(&r->head, h + 1, memory_order_release);      // 再公告
    return true;
}

bool rb_pop(ring_t *r, int *out) {       // 只有消費者呼叫
    size_t t = atomic_load_explicit(&r->tail, memory_order_relaxed);
    size_t h = atomic_load_explicit(&r->head, memory_order_acquire);   // 看見生產者寫好的資料
    if (h == t) return false;                                          // 空
    *out = r->buf[t & RB_MASK];
    atomic_store_explicit(&r->tail, t + 1, memory_order_release);      // 告訴生產者這格可以重用
    return true;
}
```

- `head` / `tail` 用不斷遞增的 `size_t`，用 `h - t` 算數量（無號數溢位仍然正確），就不需要「浪費一格」來分辨滿和空。
- 多生產者或多消費者（MPMC）→ 不要自己寫，用 mutex + condvar 的 bounded buffer（A4）。
- 批次處理：一次 push / pop 多筆，可以減少 atomic 操作次數。

---

## A12. Deadlock 與 priority inversion

### A12.1 Deadlock 四個必要條件（缺一就不會發生）

互斥、持有並等待（hold and wait）、不可搶占、循環等待。最實用的破法是打破**循環等待**：

```c
// 全域固定順序：永遠先拿位址小的那把（或編號小的）
void lock_pair(pthread_mutex_t *a, pthread_mutex_t *b) {
    if (a > b) { pthread_mutex_t *t = a; a = b; b = t; }
    pthread_mutex_lock(a);
    pthread_mutex_lock(b);
}
```

其他做法：`trylock` 拿不到就把已拿的全部放掉再重試；縮小設計，讓一次只需要一把鎖。

除錯：程式卡住 → `gdb -p <pid>` → `thread apply all bt`，看每個執行緒卡在哪把鎖。

### A12.2 Priority inversion（簡述）

低優先權任務持鎖，被中優先權任務搶占，高優先權任務等這把鎖 → 高優先權任務間接被中優先權任務卡住。解法：priority inheritance（`pthread_mutexattr_setprotocol(&attr, PTHREAD_PRIO_INHERIT)`）或 priority ceiling。在沒有 RTOS 的 pico 裸機程式中，對應情況是「ISR 等主迴圈持有的鎖」→ 會直接 deadlock（B6）。

---

## A13. 量測

```c
#include <time.h>
static double now_ms(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);   // 不受手動調整系統時間影響（NTP 微調頻率仍會影響）
    return ts.tv_sec * 1e3 + ts.tv_nsec / 1e6;
}
// double t0 = now_ms(); ... ; printf("%.3f ms\n", now_ms() - t0);
```

量測守則：

1. 跑多次（例如 5–10 次），看中位數或最小值，不要只跑一次。
2. 先暖身一次（page fault、cache、CPU 升頻）。
3. 用 `-O2` 量測（跟 demo Makefile 的 `CFLAGS` 一致），結果要「用掉」（印出或寫入 sink），避免被最佳化刪除。
4. 分開量「建立執行緒」與「計算」的時間。
5. 確認可用 CPU 數：`nproc`；也可以用 `taskset -c 0,1 ./prog` 固定核心。
6. `time ./prog`：`real` 是經過時間；`user + sys` 遠大於 `real` 代表有並行；`user` 很高但沒變快，可能是 spinlock 空轉。
7. 若有 perf：`perf stat -e task-clock,context-switches,cpu-migrations ./prog`。

### Amdahl's law

```
Speedup(N) = 1 / ((1 - p) + p / N)
p = 可並行部分的比例，N = 核心數
```

例：p = 0.9、N = 2 → 1 / (0.1 + 0.45) ≈ 1.82 倍。p = 0.5、N = 2 → 1.33 倍。
**含意**：RP2350 只有 2 顆核心，就算完美並行，最多也只有 2 倍。如果序列部分（I/O、等待、鎖）佔大比例，先優化序列部分。臨界區本身就是序列部分，鎖抓太久 = p 變小。

### 執行緒建立成本

`pthread_create` / `pthread_join` 比一次 mutex lock 貴好幾個數量級（要配置 stack、進 kernel）。工作量小的話，開執行緒反而變慢。→ 一次建立，重複使用（thread pool），或者每個執行緒分配一大塊工作。

---

## A14. 編譯與偵錯工具

| 工具 | 指令 | 說明 |
|---|---|---|
| pthread 連結 | `gcc -O2 -Wall -pthread x.c -o x` | `-pthread` 同時影響編譯（定義巨集）與連結；比只寫 `-lpthread` 正確 |
| ThreadSanitizer | `gcc -fsanitize=thread -g -O1 x.c -o x && ./x` | 執行時偵測 data race，印出兩邊的 stack。典型會慢 5–15 倍、記憶體 5–10 倍。不能和 `-fsanitize=address` 同時使用 |
| Helgrind | `valgrind --tool=helgrind ./x` | 偵測 race、鎖順序不一致（可能 deadlock）、pthread API 誤用；很慢 |
| DRD | `valgrind --tool=drd ./x` | 另一個 race detector |
| gdb | `gdb ./x` → `run` → 卡住時 Ctrl-C → `info threads`、`thread apply all bt` | 找 deadlock |

TSan 只會報**實際執行到**的 race；沒報不代表沒有。考場不能自行安裝軟體，先用 `which valgrind`、試編 `-fsanitize=thread` 確認可不可以用。

---

# Part B：RP2350 / pico-sdk

## B0. 硬體重點（RP2350 vs RP2040）

| 項目 | RP2350 | RP2040 |
|---|---|---|
| 核心 | 2 顆，Cortex-M33 **或** Hazard3 RISC-V（RV32IMAC+），開機時選；兩種可混用但實用性很低 | 2 顆 Cortex-M0+ |
| 時脈 | 最高 150 MHz（datasheet 標稱） | 133 MHz |
| 原子指令 | 有（Arm `ldrex/strex`、RISC-V `lr/sc`/`amo*`），由 Global Exclusive Monitor 支援跨核 | **沒有**，C11 atomic 由 `pico_atomic` 用 spinlock 模擬 |
| Inter-core FIFO | 每方向 **4 格** × 32 bit | 每方向 8 格 |
| Hardware spinlock | 32 個，但有 erratum **E2**；SDK 預設改用軟體 spinlock | 32 個，正常 |
| Doorbell | 8 個（`NUM_DOORBELLS`），`multicore_doorbell_*` | 無 |
| SRAM | 520 kB：SRAM0–3 與 SRAM4–7 各 256 kB、各自 4 bank 交錯；SRAM8/9 各 4 kB | 264 kB：SRAM0–3 交錯 256 kB；SRAM4/5 各 4 kB |
| DMA | 16 個 channel | 12 個 channel |
| FIFO IRQ | 兩核共用同一個 IRQ 號 `SIO_IRQ_FIFO`（25） | 每核不同：`SIO_IRQ_PROC0` / `SIO_IRQ_PROC1` |

匯流排：AHB5 crossbar 有 6 個 manager（core0 I/D、core1 I/D、DMA R/W），每個 cycle 最多 6 筆傳輸並行，只要它們存取**不同**的下游 port（例如不同 SRAM bank）。150 MHz 下理論最大頻寬 3.6 GB/s。同一 port 同時被多個 manager 存取時才需要仲裁（`BUSCTRL` 的 `BUS_PRIORITY` 可調 2 級優先權，同級 round-robin）。

CMake：

```cmake
target_link_libraries(app pico_stdlib pico_multicore)   # pico_stdlib 已經帶入 pico_time → pico_sync、pico_util(queue)
# 用 DMA 另外加 hardware_dma；pico_atomic 由 C library 介面自動帶入
```

標頭：`#include "pico/multicore.h"`、`"hardware/sync.h"`、`"pico/sync.h"`（含 critical_section / mutex / sem）、`"pico/util/queue.h"`、`"hardware/dma.h"`。

---

## B1. pico_multicore：啟動 core1

```c
void multicore_reset_core1(void);                      // 只能從 core0 呼叫
void multicore_launch_core1(void (*entry)(void));      // 用預設 core1 stack
void multicore_launch_core1_with_stack(void (*entry)(void), uint32_t *stack_bottom, size_t stack_size_bytes); // 大小必須是 4 的倍數
void multicore_launch_core1_raw(void (*entry)(void), uint32_t *sp, uint32_t vector_table);  // 低階，無 stack guard
uint get_core_num(void);                               // 0 或 1（pico/platform.h）
```

- core1 必須處於 reset 狀態（剛開機，或呼叫過 `multicore_reset_core1()`）才能 launch。
- `multicore_launch_core1` 內部**用 inter-core FIFO 做握手**（依序送 0, 0, 1, vector table, sp, entry，core1 逐一回傳）。所以：launch 之前不要在 FIFO 裡放自己的資料；core1 啟動前不要讓 core1 那側的程式碼讀 FIFO。
- core1 預設 stack：`PICO_CORE1_STACK_SIZE`，預設等於 `PICO_STACK_SIZE`（0x800 = **2 kB**），由 linker 放在 **SCRATCH_X**（SRAM8，0x20080000，4 kB）；core0 的 stack 放在 **SCRATCH_Y**（SRAM9）。
  - core1 有大區域陣列或深遞迴會 stack overflow → 改成 `static` / 全域陣列，或在 CMake 加 `target_compile_definitions(app PRIVATE PICO_CORE1_STACK_SIZE=0x1000)`（上限 0x10000；SCRATCH_X 只有 4 kB，超過時 ⚠️未驗證 linker 如何配置），或用 `multicore_launch_core1_with_stack` 自己給一塊 RAM。
- core1 的 entry 通常寫成 `while (1)` 不返回（返回後的行為 ⚠️未驗證，不要依賴）。

```c
#include "pico/stdlib.h"
#include "pico/multicore.h"

void core1_main(void) {
    while (true) {
        uint32_t x = multicore_fifo_pop_blocking();
        multicore_fifo_push_blocking(x * 2);
    }
}

int main(void) {
    stdio_init_all();
    multicore_launch_core1(core1_main);
    multicore_fifo_push_blocking(21);
    printf("%lu\n", (unsigned long)multicore_fifo_pop_blocking());   // 42
}
```

---

## B2. Inter-core FIFO（mailbox）

```c
bool     multicore_fifo_rvalid(void);                  // 讀 FIFO 有資料？（VLD）
bool     multicore_fifo_wready(void);                  // 寫 FIFO 有空位？（RDY）
void     multicore_fifo_push_blocking(uint32_t data);  // 滿就等；送出後 __sev()
bool     multicore_fifo_push_timeout_us(uint32_t data, uint64_t timeout_us);
uint32_t multicore_fifo_pop_blocking(void);            // 空就 __wfe() 等
bool     multicore_fifo_pop_timeout_us(uint64_t timeout_us, uint32_t *out);
void     multicore_fifo_drain(void);                   // 丟掉讀 FIFO 內所有資料
void     multicore_fifo_clear_irq(void);               // 清 ROE/WOF 黏著旗標（VLD 要靠 pop/drain 清）
uint32_t multicore_fifo_get_status(void);              // bit0 VLD, bit1 RDY, bit2 WOF, bit3 ROE
// 中斷：irq_set_exclusive_handler(SIO_FIFO_IRQ_NUM(get_core_num()), handler); irq_set_enabled(..., true);
```

重點：

- **深度：RP2350 每方向 4 格**（datasheet §3.1.5 與 SDK 文件一致）；RP2040 是 8 格。每格 32 bit。
- 一個 FIFO 只能 core0 寫 / core1 讀，另一個反過來。
- 滿了還寫 → 資料被丟棄，設 WOF；空了還讀 → 讀到無效值，設 ROE。所以要用 `_blocking` 或先檢查 `wready` / `rvalid`。
- SDK 官方建議：FIFO 很珍貴（core1 啟動、`multicore_lockout` 會用到；RP2040 的 FreeRTOS SMP port 也用它，RP2350 的 port 改用 doorbell，只在啟動 core1 時碰 FIFO，見 `freertos.md`），一般資料傳遞**優先用 `queue_t`**。
- 一次只傳得了 32 bit → 要傳大量資料就傳**指標或 buffer 索引**，資料本身放在共享 SRAM。
- 用了 `multicore_lockout_victim_init()` 之後，該 FIFO 就不能再拿來做別的事。

---

## B3. multicore_lockout（讓另一核暫停）

```c
void multicore_lockout_victim_init(void);              // 被暫停的那一核先呼叫（會佔用 FIFO IRQ）
void multicore_lockout_victim_deinit(void);
bool multicore_lockout_victim_is_initialized(uint core_num);
void multicore_lockout_start_blocking(void);           // 要求另一核暫停並等它進入暫停
bool multicore_lockout_start_timeout_us(uint64_t timeout_us);
void multicore_lockout_end_blocking(void);
bool multicore_lockout_end_timeout_us(uint64_t timeout_us);
```

- 被暫停的核在 RAM 中的小迴圈裡空轉、中斷關閉。主要用途：寫 flash 時確保另一核沒有從 flash 執行程式（`flash_safe_execute` 等）。
- **不是**一般資料同步用的鎖，成本高；保護共享資料請用 B4–B6。

---

## B4. Spinlock（hardware_sync）與 RP2350-E2

### B4.1 API

```c
int          spin_lock_claim_unused(bool required);    // 取得一個沒人用的 lock 編號；required=true 時找不到就 panic，否則回傳 -1
void         spin_lock_claim(uint lock_num);           // 已被 claim 會 panic
void         spin_lock_unclaim(uint lock_num);
bool         spin_lock_is_claimed(uint lock_num);
spin_lock_t *spin_lock_init(uint lock_num);            // 初始化為未上鎖並回傳 instance
spin_lock_t *spin_lock_instance(uint lock_num);        // 編號 → instance
uint         spin_lock_get_num(spin_lock_t *lock);
uint32_t     spin_lock_blocking(spin_lock_t *lock);    // 先關「本核」中斷再上鎖，回傳舊的中斷狀態
void         spin_unlock(spin_lock_t *lock, uint32_t saved_irq);   // 解鎖並恢復中斷
void         spin_lock_unsafe_blocking(spin_lock_t *lock);         // 不關中斷（呼叫者自己負責）
void         spin_unlock_unsafe(spin_lock_t *lock);
bool         is_spin_locked(spin_lock_t *lock);
uint         next_striped_spin_lock_num(void);         // 從共用的 striped 範圍輪流給一個編號（非獨佔）
```

```c
static spin_lock_t *lk;
void setup(void) { lk = spin_lock_init(spin_lock_claim_unused(true)); }

void update(void) {
    uint32_t save = spin_lock_blocking(lk);   // 關本核 IRQ + 擋另一核
    shared_x++;                               // 越短越好
    spin_unlock(lk, save);
}
```

規則（SDK 文件）：spinlock 只能持有**很短**的時間；持有時不要再拿別的 spinlock（會 deadlock）；不可重入（同一核拿兩次會卡死）。`spin_lock_blocking` 會關中斷，所以 ISR 和主程式可以共用同一把。

### B4.2 數量與編號分配

- 共 32 個（`NUM_SPIN_LOCKS`）。
- SDK 預設分配（RP2040，以及 RP2350 使用軟體 spinlock 的預設情況）：

| 編號 | 用途 |
|---|---|
| 0–13 | SDK 內部保留（IRQ=9、TIMER=10、HARDWARE_CLAIM=11、RAND=12、ATOMIC=13 等） |
| 14–15 | OS 保留（`PICO_SPINLOCK_ID_OS1/OS2`） |
| 16–23 | striped 共用範圍（`next_striped_spin_lock_num()`，`queue_init` / `mutex_init` / `sem_init` 用這裡） |
| 24–31 | 給 `spin_lock_claim_unused()` 配發（`critical_section_init` 也是從這裡獨佔一把；只有 8 把，用完再 claim 會 panic） |

- RP2350 若設定 `PICO_USE_SW_SPIN_LOCKS=0`（用硬體 spinlock），編號會改成避開 E2：OS 18–19、striped 20–25、claim 範圍 26–31。**請用 `PICO_SPINLOCK_ID_*` 巨集，不要寫死數字。**

### B4.3 RP2350-E2 erratum 與軟體 spinlock

- 內容（datasheet 附錄 D.9.2；A2 有，A4 公告未列為已修，用文件 + 軟體解決）：SIO spinlock 暫存器在 SIO offset 0x100–0x17C。RP2350 在 0x180 以上新增了暫存器（doorbell、PERI_NONSEC、RISC-V soft IRQ、RISC-V MTIME、TMDS encoder）。位址解碼只看 bit 8，所以**寫入 0x180–0x1FC 會被誤認成寫入低 0x80 的 spinlock，也就是把那把鎖意外釋放**。只有寫入受影響，讀取正常。
- datasheet 列出不受影響、可正常使用的硬體 spinlock：5、6、7、10、11、18–31（18–24 對應的是唯讀的 TMDS 暫存器，寫入誤解碼不會發生）。
- SDK 對策：`PICO_USE_SW_SPIN_LOCKS` 在 RP2350 預設開啟（SDK 2.3.x 的預設值是 `!PICO_XIP_RAM`；2.2.0 是 1）。開啟時 `spin_lock_t` 變成 RAM 中的一個 byte 旗標（陣列 `_sw_spin_locks[32]`）：
  - Arm（Cortex-M33）：`ldaexb` / `strexb` 迴圈上鎖、`stlb` 解鎖；SDK 會設定 `ACTLR.EXTEXCLALL`，讓 exclusive 存取都經過全域 exclusive monitor，跨核才正確。
  - RISC-V（Hazard3）：`amoor.w.aq` 上鎖、`fence` + store 解鎖。
- **對使用者的影響**：API 完全相同（`spin_lock_blocking` 等照用）。只要用 SDK 的 API 而不要自己直接讀寫 SIO spinlock 暫存器，就不會踩到 E2。
- 讀到舊範例（RP2040 時代）直接操作 `sio_hw->spinlock[n]` 的程式碼時，要特別小心。

### B4.4 RP2350 的 C11 atomic 與 exclusive monitor

- RP2350：1/2/4 byte 且對齊的 atomic 由編譯器直接產生處理器的 exclusive / AMO 指令（lock-free，`pico_atomic` 的 `__atomic_is_lock_free` 也回報 true）；其他大小（例如 64-bit）由 `pico_atomic` 用 spinlock（`PICO_SPINLOCK_ID_ATOMIC`）保護。RP2040：**全部**用 spinlock 模擬。
- Global Exclusive Monitor（datasheet §2.1.6）：跨核 exclusive 靠它，只涵蓋 SRAM（0x20000000–0x20082000，不含 XIP / PSRAM）；**reservation granule = 16 bytes** ⚠️未查證、每個 PE 只追蹤一個 reservation；DMA 寫入也會被監看（會讓 CPU 的 exclusive 失敗而重試）。
- 推論（⚠️未驗證於實測）：兩核分別對**同一個 16-byte 區塊內的不同變數**做 atomic RMW，會互相使對方的 exclusive write 失敗而重試，類似 false sharing。高頻 atomic 變數建議各自對齊到 16 bytes（`__attribute__((aligned(16)))`）。軟體 spinlock 陣列 32 bytes 只佔 2 個 granule，不同鎖之間理論上也會互相干擾，但持鎖很短時影響應該很小（⚠️推論）。
- Global monitor 不涵蓋 SRAM 以外（例如 flash/XIP、外部 PSRAM）→ 那裡的 exclusive 無法跨核保證 → **atomic 變數必須放在 SRAM**（一般全域 / static 變數本來就在 SRAM）。

---

## B5. 中斷控制與記憶體屏障

```c
uint32_t save_and_disable_interrupts(void);   // 關「目前這一核」的中斷，回傳原狀態
void     restore_interrupts(uint32_t status);
void     restore_interrupts_from_disabled(uint32_t status);  // 已知目前是關閉時用（RISC-V 較省）
void     __dmb(void);    // Arm: dmb；RISC-V: fence rw, rw
void     __dsb(void);
void     __isb(void);
void     __mem_fence_acquire(void);   // 目前實作 = __dmb()
void     __mem_fence_release(void);   // 目前實作 = __dmb()
void     __sev(void);    // 發 event（喚醒另一核的 __wfe）
void     __wfe(void);    // 等 event（省電忙等）
void     __wfi(void);    // 等中斷
void     tight_loop_contents(void);   // 忙等迴圈的空函式（標示用）
#define  __compiler_memory_barrier()  // 只阻止編譯器重排，不產生指令
```

- **關中斷只擋得住本核**，擋不住另一核。跨核保護一定要加 spinlock（或直接用 `critical_section_t`，它兩者都做）。
- 關中斷的時間越短越好，否則會延誤 timer、USB、UART 等中斷。

---

## B6. pico_sync：critical_section / mutex / semaphore

### B6.1 critical_section_t（IRQ + 跨核都安全，極短）

```c
void critical_section_init(critical_section_t *cs);                       // 內部 spin_lock_claim_unused(true)：獨佔 claim 範圍的一把（pico_sync/critical_section.c）
void critical_section_init_with_lock_num(critical_section_t *cs, uint lock_num);
void critical_section_enter_blocking(critical_section_t *cs);             // = spin_lock_blocking（關本核 IRQ + spinlock）
void critical_section_exit(critical_section_t *cs);
void critical_section_deinit(critical_section_t *cs);                     // 只用於 critical_section_init 建立的
bool critical_section_is_initialized(critical_section_t *cs);
```

- 不可重入；要巢狀時必須用 `_init_with_lock_num` 給**不同**的 spinlock（否則同一把鎖拿兩次 → 卡死）。
- 持有期間本核中斷是關的 → 只放幾行讀寫。

```c
static critical_section_t cs;
static struct { uint32_t sum; uint32_t n; } stats;     // 兩個欄位要一起更新 → 不能只靠 atomic

void stats_add(uint32_t v) {          // core0、core1、ISR 都可以呼叫
    critical_section_enter_blocking(&cs);
    stats.sum += v;
    stats.n++;
    critical_section_exit(&cs);
}
// main 開頭：critical_section_init(&cs);
```

### B6.2 mutex_t / recursive_mutex_t（可以持有較久，不可在 ISR 阻塞）

```c
void mutex_init(mutex_t *mtx);
void mutex_enter_blocking(mutex_t *mtx);
bool mutex_try_enter(mutex_t *mtx, uint32_t *owner_out);   // owner_out 可為 NULL
bool mutex_enter_timeout_ms(mutex_t *mtx, uint32_t timeout_ms);
bool mutex_enter_timeout_us(mutex_t *mtx, uint32_t timeout_us);
bool mutex_enter_block_until(mutex_t *mtx, absolute_time_t until);
void mutex_exit(mutex_t *mtx);
bool mutex_is_initialized(mutex_t *mtx);
auto_init_mutex(name);            // 靜態宣告，執行時自動初始化
// 遞迴版：recursive_mutex_init / recursive_mutex_enter_blocking / recursive_mutex_try_enter /
//         recursive_mutex_enter_timeout_ms|us / recursive_mutex_enter_block_until / recursive_mutex_exit
// auto_init_recursive_mutex(name);
```

- owner 是「核心編號」（裸機 SDK 下 `lock_get_caller_owner_id()` = `get_core_num()`）。同一核對 `mutex_t` 再 enter 一次 → deadlock；需要重入用 `recursive_mutex_t`。
- 等待時內部用 `__wfe()`，釋放時 `__sev()`，所以不會像 spinlock 一樣燒滿 bus，也不會長時間關中斷。
- ISR 裡不要呼叫阻塞的 `mutex_enter_*`；可以用 `mutex_try_enter`，拿不到就跳過。

### B6.3 semaphore_t

```c
void sem_init(semaphore_t *sem, int16_t initial_permits, int16_t max_permits);
int  sem_available(semaphore_t *sem);
bool sem_release(semaphore_t *sem);           // +1（不超過 max）；可在 ISR 呼叫
void sem_reset(semaphore_t *sem, int16_t permits);
void sem_acquire_blocking(semaphore_t *sem);
bool sem_acquire_timeout_ms(semaphore_t *sem, uint32_t timeout_ms);
bool sem_acquire_timeout_us(semaphore_t *sem, uint32_t timeout_us);
bool sem_acquire_block_until(semaphore_t *sem, absolute_time_t until);
bool sem_try_acquire(semaphore_t *sem);
```

注意名稱和 POSIX 不同：pico 是 `sem_acquire_blocking` / `sem_release`，POSIX 是 `sem_wait` / `sem_post`。典型用法：ISR 或另一核 `sem_release()` 通知「資料好了」，工作端 `sem_acquire_blocking()` 等。

### B6.4 該用哪個（pico）

| 情境 | 用 |
|---|---|
| 單一 32-bit 計數 / 旗標，跨核 | C11 `atomic_*`（RP2350 lock-free） |
| 幾個欄位一起改，可能被 ISR 或另一核碰 | `critical_section_t` |
| 持有時間較長（例如整段 printf、操作周邊），只有兩核主程式會碰 | `mutex_t` |
| 通知 / 計數資源 | `semaphore_t` |
| 跨核傳資料 | `queue_t`（B7） |
| 只有同一核的 ISR 和主迴圈共用 | `save_and_disable_interrupts()` 包住讀寫即可 |

---

## B7. queue_t（pico_util/queue）：跨核 / IRQ 安全的佇列

```c
#include "pico/util/queue.h"
void queue_init(queue_t *q, uint element_size, uint element_count);     // 用 striped spinlock；回傳 void
void queue_init_with_spinlock(queue_t *q, uint element_size, uint element_count, uint spinlock_num);
void queue_free(queue_t *q);
uint queue_get_level(queue_t *q);           // 目前元素數（有加鎖）
uint queue_get_level_unsafe(queue_t *q);
bool queue_is_empty(queue_t *q);
bool queue_is_full(queue_t *q);
bool queue_try_add(queue_t *q, const void *data);      // 滿 → 立刻回傳 false
bool queue_try_remove(queue_t *q, void *data);         // 空 → 立刻回傳 false；data 可為 NULL
bool queue_try_peek(queue_t *q, void *data);
void queue_add_blocking(queue_t *q, const void *data);
void queue_remove_blocking(queue_t *q, void *data);
void queue_peek_blocking(queue_t *q, void *data);
// PICO_QUEUE_MAX_LEVEL=1 時另有 queue_get_max_level / queue_reset_max_level（看最高水位）
```

- 元素是**複製**進去的（`memcpy` element_size bytes），整個操作在 spinlock + 關中斷下進行。
- `queue_init` 內部用 `calloc(element_count + 1, element_size)` 配置 → 用到 heap；**回傳 void，也不檢查 calloc 失敗** → 無法從回傳值判斷成功；大 queue 先估 heap。
- ISR 中只用 `queue_try_*`。
- 效能：每筆都要上鎖 + memcpy。元素很小、數量很大時，改成**傳 buffer 指標 / 索引**或一次傳一批。

### 流水線切分範例（core0 產生 → core1 處理）

```c
#include "pico/stdlib.h"
#include "pico/multicore.h"
#include "pico/util/queue.h"

typedef struct { uint32_t *buf; uint32_t len; } job_t;

static queue_t jobs, done;
#define NBUF 4
#define BLK  256
static uint32_t pool[NBUF][BLK];

static void core1_main(void) {
    while (true) {
        job_t j;
        queue_remove_blocking(&jobs, &j);
        for (uint32_t i = 0; i < j.len; i++) j.buf[i] = process(j.buf[i]);  // 重活在 core1
        queue_add_blocking(&done, &j);
    }
}

int main(void) {
    stdio_init_all();
    queue_init(&jobs, sizeof(job_t), NBUF);
    queue_init(&done, sizeof(job_t), NBUF);
    multicore_launch_core1(core1_main);      // queue 先初始化，再啟動 core1

    for (int k = 0; k < NBUF; k++) {         // core0 填資料（或從周邊讀）
        produce(pool[k], BLK);
        job_t j = { pool[k], BLK };
        queue_add_blocking(&jobs, &j);       // 傳的是指標，不是 256 個 word
    }
    for (int k = 0; k < NBUF; k++) { job_t j; queue_remove_blocking(&done, &j); consume(j.buf, j.len); }
}
```

重點：buffer 在交出去之後到拿回來之前，生產者**不能再碰**（所有權隨訊息轉移）。queue 的鎖會提供需要的記憶體順序。

---

## B8. ISR 與主迴圈共享變數

```c
static volatile bool data_ready;          // 單一 word 旗標：volatile 讓主迴圈每次都重新讀
static volatile uint32_t sample;

void my_isr(void) {                       // 同一核上的中斷
    sample = read_hw();
    data_ready = true;
}

int main(void) {
    while (true) {
        if (data_ready) {
            uint32_t save = save_and_disable_interrupts();   // 一次讀多個欄位時，關中斷避免讀到一半被改
            uint32_t s = sample;
            data_ready = false;
            restore_interrupts(save);
            handle(s);                                       // 處理放在關中斷區外面
        }
        // 也可以 __wfi() 省電
    }
}
```

- 同一核的 ISR ↔ 主迴圈：單一對齊 32-bit 旗標用 `volatile` 是嵌入式常見慣例（C 標準正式只保證 `volatile sig_atomic_t`）；多個欄位或 RMW（例如 `count++`）→ 主程式那側要關中斷，或改用 atomic。
- ISR 和**另一核**共享 → 關中斷不夠，要 `critical_section_t`、atomic 或 `queue_t`。
- 64-bit 變數（例如 `uint64_t` 計數）在 32-bit 核心上讀寫不是一個指令 → 會讀到一半新一半舊，一定要保護。
- ISR 內不要 `printf`、不要阻塞、不要拿可能被主程式長時間持有的鎖。

---

## B9. SRAM bank、striping 與資料擺放

### B9.1 位址配置（RP2350，datasheet §2.2.3、§4.2；SDK addressmap.h）

| 區域 | 位址 | 大小 | bank 對應 |
|---|---|---|---|
| SRAM0–3（striped） | 0x20000000–0x2003FFFF | 256 kB | 依位址 bit 3:2 交錯：0x…0→bank0、0x…4→bank1、0x…8→bank2、0x…C→bank3，每 16 bytes 一輪 |
| SRAM4–7（striped） | 0x20040000–0x2007FFFF | 256 kB | 同上方式交錯到 bank4–7 |
| SRAM8 = SCRATCH_X | 0x20080000–0x20080FFF | 4 kB | 單一 bank，不交錯；預設放 **core1 stack** |
| SRAM9 = SCRATCH_Y | 0x20081000–0x20081FFF | 4 kB | 單一 bank，不交錯；預設放 **core0 stack** |

- 每個 bank 有自己的 AHB5 仲裁器：不同 manager（core0、core1、DMA）在同一 cycle 存取**不同 bank** → 同時進行；存取**同一 bank** → 其中一方要等（round-robin 或依 `BUS_PRIORITY`）。
- SRAM 都是單週期存取（沒有衝突時），所以一般可以把它當成一整塊 520 kB 記憶體。只有在極端追求頻寬或延遲穩定時才需要考慮 bank。
- RP2040 有「非交錯鏡像」位址可以把資料固定在某一個 bank；**RP2350 沒有這個鏡像**。RP2350 能做的明確切分是：兩個 256 kB 區域（SRAM0–3 vs SRAM4–7）以及 SRAM8 / SRAM9。

### B9.2 實用擺放策略

| 目的 | 做法 |
|---|---|
| 單一核專用的小型熱資料 | `uint32_t __scratch_x("c1") buf[64];`（core1 用）/ `__scratch_y("c0")`（core0 用）。注意 4 kB 中已有 2 kB 預設被 stack 佔用 |
| 熱函式不要從 flash 執行（避免 XIP cache miss） | `void __not_in_flash_func(f)(int a) { ... }` 或 `__time_critical_func(f)`（預設放 RAM） |
| DMA 大量搬運時，讓 CPU 的資料和 DMA 的 buffer 不搶同一組 bank | DMA buffer 放一個 256 kB 區，CPU 熱資料放另一個（需自訂 linker section，⚠️進階，考場不一定值得） |
| 指令與資料衝突 | datasheet 提到：在 striped SRAM 中，從 PC 往前約 8 bytes（mod 16）的 literal load 可能和預取撞同一 bank，偶爾多 1 cycle。一般不需要處理 |

範例：

```c
#include "pico/platform.h"   // 或 pico/platform/sections.h

static uint32_t __scratch_x("core1_data") core1_hist[256];   // 1 kB，core1 專用
static uint32_t __scratch_y("core0_data") core0_hist[256];   // 1 kB，core0 專用
```

- 先確認：`.map` 檔或 `arm-none-eabi-size` / `riscv*-size` 看 scratch 區有沒有爆（core1 stack 2 kB + 資料要 ≤ 4 kB）。

---

## B10. 用 DMA 讓 CPU 空出來（對應 demo 的 transfer engine）

demo `transfer-engine` 的四拍「描述 → 啟動 → 等待 → 取用結果」就是 pico-sdk `hardware_dma` 的使用方式。對照：

| demo engine.h | pico-sdk hardware_dma |
|---|---|
| `engine_claim()` | `int dma_claim_unused_channel(bool required)` |
| `.size = XFER_32` | `channel_config_set_transfer_data_size(&c, DMA_SIZE_32)`（`DMA_SIZE_8/16/32`） |
| `.src_increment` / `.dst_increment` | `channel_config_set_read_increment(&c, bool)` / `channel_config_set_write_increment(&c, bool)` |
| `engine_configure()` + `engine_start()` | `dma_channel_configure(ch, &c, write_addr, read_addr, encoded_count, trigger)` |
| `.count`（筆數，不是 bytes） | `encoded_transfer_count`：**也是筆數**；RP2350 只有低 28 bit 是筆數，高 4 bit 是模式 → 用 `dma_encode_transfer_count(n)` |
| `engine_busy()` / `engine_wait()` | `dma_channel_is_busy(ch)` / `dma_channel_wait_for_finish_blocking(ch)` |
| `engine_release()` | `dma_channel_unclaim(ch)` |
| 4 個 channel | RP2350 16 個（RP2040 12 個） |

```c
#include "hardware/dma.h"

int ch = dma_claim_unused_channel(true);
dma_channel_config_t c = dma_channel_get_default_config(ch);  // 預設：32-bit、read 遞增、write 「不」遞增、DREQ_FORCE（全速）
channel_config_set_transfer_data_size(&c, DMA_SIZE_32);
channel_config_set_read_increment(&c, true);
channel_config_set_write_increment(&c, true);
dma_channel_configure(ch, &c, dst, src, dma_encode_transfer_count(N), true);  // N 筆 word，立刻啟動

do_other_work();                              // CPU 同時做別的事（真的不佔 CPU 指令，只佔 bus 頻寬）
dma_channel_wait_for_finish_blocking(ch);     // 等完成之後才能讀 dst
dma_channel_unclaim(ch);
```

- 舊版 SDK 型別名叫 `dma_channel_config`；新版是 `dma_channel_config_t`（保留 typedef，兩者都能用）。
- **同步注意**：DMA 寫完之前讀 `dst` = 讀到舊資料；DMA 進行中 CPU 改 `src` = 搬到一半新一半舊。CPU 和 DMA 也是「兩個並行的執行者」。
- Ping-pong（雙緩衝）：DMA 填 buffer B 的時候 CPU 處理 buffer A，完成後交換。可以用 DMA 完成中斷（`dma_channel_set_irq0_enabled` + `irq_set_exclusive_handler(DMA_IRQ_0, ...)`）或 chain（`channel_config_set_chain_to`）。
- DMA 和 CPU 搶同一個 SRAM bank 時會互相拖慢（B9）；DMA 寫入也會讓 CPU 在同一 16-byte granule 的 exclusive 失敗（B4.4）。

---

## B11. 兩核分工模式

### B11.1 資料分割（data parallel）：每核處理一半，各自累加，最後合併

```c
#include "pico/stdlib.h"
#include "pico/multicore.h"

#define N 100000
static int32_t data[N];
static volatile int64_t core1_result;     // 只有 core1 寫；core0 在收到 FIFO 通知後才讀

static int64_t sum_range(int lo, int hi) {
    int64_t s = 0;                         // 區域累加：不碰共享變數
    for (int i = lo; i < hi; i++) s += data[i];
    return s;
}

static void core1_main(void) {
    core1_result = sum_range(N / 2, N);
    __dmb();                               // 保守：確保結果先寫入，再發通知
    multicore_fifo_push_blocking(1);       // 通知 core0：結果好了
    while (true) __wfi();
}

int main(void) {
    stdio_init_all();
    fill(data, N);
    uint64_t t0 = time_us_64();
    multicore_launch_core1(core1_main);
    int64_t s0 = sum_range(0, N / 2);
    (void)multicore_fifo_pop_blocking();   // 等 core1
    __dmb();                               // 保守：收到通知後才讀結果
    int64_t total = s0 + core1_result;
    printf("sum=%lld  %llu us\n", (long long)total, (unsigned long long)(time_us_64() - t0));
}
```

- 為什麼 core0 讀 `core1_result` 看得到正確值：core1 先寫結果、再 push FIFO；core0 pop 之後才讀。⚠️嚴格來說 FIFO 本身不是 C 層級的 memory barrier；保守做法是 core1 在 push 前加 `__dmb()`、core0 在 pop 後加 `__dmb()`，或把結果做成 atomic（release/acquire）。也可以直接把結果放進 `queue_t`（內部有鎖 + 屏障）。
- 注意 launch 的時間（FIFO 握手）也算進去；重複使用時讓 core1 常駐、用 FIFO / queue 派工，不要每次都 reset + launch。

### B11.2 流水線（pipeline）：core0 讀取 / 前處理 → core1 運算 → 輸出

見 B7 範例。適合「每筆資料都要經過多個階段」。整體吞吐量取決於**最慢的那一階段** → 量每一階段的時間，讓兩邊工作量接近。

### B11.3 選擇

| 情境 | 選 |
|---|---|
| 大陣列、每個元素獨立運算 | 資料分割（最簡單，接近 2 倍） |
| 有 I/O（UART/USB/感測器）+ 運算 | 一核專做 I/O，一核運算（pipeline） |
| 一核要即時反應中斷 | 那核只跑 ISR + 輕量工作，重活給另一核 |
| 搬資料 | 交給 DMA，兩核都不要寫複製迴圈 |

---

## B12. stdio 從兩核使用

- `PICO_STDOUT_MUTEX` 預設為 1：stdout 有一把 mutex，兩核同時 `printf` **不會**交錯在同一行中間，但順序不保證。
- 取得 mutex 有逾時（`PICO_STDIO_DEADLOCK_TIMEOUT_MS`），避免卡死。
- `printf` 很慢（尤其 UART / USB），而且會拿鎖 → **不要放在熱迴圈或臨界區裡**。量測時先把結果存進陣列，結束後再印。
- 不要在 ISR 裡 `printf`。

---

## B13. 計時（pico_time / hardware_timer）

```c
uint64_t time_us_64(void);                  // 開機後微秒數（64-bit，不會溢位）
uint32_t time_us_32(void);                  // 32-bit，約 71.6 分鐘溢位
absolute_time_t get_absolute_time(void);
int64_t  absolute_time_diff_us(absolute_time_t from, absolute_time_t to);  // to - from
uint32_t to_ms_since_boot(absolute_time_t t);
absolute_time_t make_timeout_time_us(uint64_t us);
absolute_time_t make_timeout_time_ms(uint32_t ms);
absolute_time_t delayed_by_us(absolute_time_t t, uint64_t us);
void sleep_us(uint64_t us);
void sleep_ms(uint32_t ms);
void sleep_until(absolute_time_t target);
```

```c
absolute_time_t t0 = get_absolute_time();
work();
int64_t us = absolute_time_diff_us(t0, get_absolute_time());
```

- 解析度 1 µs。要量很短的程式段 → 重複執行 1000 次取平均，或用 cycle counter（⚠️未驗證 RP2350 上的具體 SDK API，考場查文件）。
- 兩核讀到的是同一個 timer，可以直接比較兩核的時間戳。

---

# Part C：分析流程、bug 對照表、檢查清單

## C1. 並行優化題的分析決策樹

```
拿到一段「多執行緒 / 雙核 + 共享資料」的程式
│
├─ 0. 先量：總時間、單執行緒時間、可用核心數（nproc / RP2350 = 2）
│      → 用 Amdahl 估上限；如果瓶頸在 I/O 或 printf，先處理那裡
│
├─ 1. 這份資料真的需要共享嗎？
│      ├─ 否（只是「大家都寫同一個累加器」）→ 改成每執行緒 / 每核區域變數 → 最後合併（A9 / B11.1）★最常見的正解
│      └─ 是 → 2
│
├─ 2. 能不能切分（partition）？
│      ├─ 依索引切（前半 / 後半、i % N）→ 各自處理、互不重疊 → 不用鎖
│      ├─ 依 key 切（hash 到不同 bucket / 不同鎖）→ lock striping
│      └─ 不能切 → 3
│
├─ 3. 共享的是什麼？
│      ├─ 單一整數 / 旗標 → atomic（計數用 relaxed；發布資料用 release/acquire）
│      ├─ 一對一傳遞資料 → SPSC ring buffer（Linux）/ queue_t 或 FIFO 傳指標（pico）
│      ├─ 多欄位一致性 → 鎖（mutex / critical_section_t）
│      └─ 讀多寫少 → rwlock
│
├─ 4. 用了鎖 → 縮短持鎖時間
│      ├─ 計算、I/O、printf、malloc 移出鎖外
│      ├─ 批次：一次拿鎖處理多筆
│      └─ 量測 contention（見下）
│
├─ 5. 檢查效能殺手
│      ├─ false sharing（Linux：padding 到 64B）
│      ├─ spinlock + 執行緒數 > 核心數 → 改 mutex
│      ├─ 在迴圈中建立 / join 執行緒 → 只建立一次
│      ├─ RP2350：兩核 + DMA 狂打同一組 SRAM bank → 錯開；熱資料放 scratch
│      └─ RP2350：用 CPU 複製大量資料 → 改 DMA
│
└─ 6. 驗證：結果正確（多跑幾次、TSan）＋ 速度確實變快（多次量測取中位數）
```

### 如何量測 contention

- 最簡單：比較「有鎖」與「把鎖拿掉（結果會錯，只看時間）」的時間差，差很多 → contention 高。
- 計數：用 `pthread_mutex_trylock` 先試，失敗就計數一次再 `lock`，最後看失敗比例。
- 比較 1、2、4 個執行緒的時間：執行緒越多反而越慢 → 嚴重 contention 或 false sharing。
- `time` 的 `user` 時間暴增但 `real` 沒降 → spinlock 空轉。
- pico：在臨界區前後用 `time_us_32()` 累加等待時間（只做除錯用）。

---

## C2. 常見 bug → 症狀 → 修法

| Bug | 症狀 | 修法 |
|---|---|---|
| 共享 `counter++` 沒保護 | 結果比預期少、每次不同；單核環境可能「剛好對」 | 區域累加後合併；或 atomic；或短鎖 |
| 耗時計算放在鎖裡 | 結果對但多執行緒比單執行緒慢 | 計算移到鎖外，鎖內只讀寫 |
| 以為 `volatile` 就安全 | 偶爾錯、TSan 報 race | 改 `_Atomic` / 鎖 |
| `pthread_cond_wait` 用 `if` | 偶爾從空佇列取出垃圾值 / 越界 | 改 `while` |
| 改條件後忘記 signal / broadcast | 執行緒永遠睡著，程式卡住 | 改完條件、仍持鎖時 signal；關閉時 broadcast |
| 兩把鎖順序不一致 | 偶爾整個卡死（deadlock） | 全域固定拿鎖順序；gdb `thread apply all bt` 確認 |
| 早 return / `break` 忘了 unlock | 下一次 lock 卡死 | 單一出口；每條路徑都 unlock |
| 對同一把非遞迴鎖重複 lock | 自己卡死自己 | 重新設計，或 recursive mutex |
| 單 CPU 上用 spinlock | 非常慢、`user` 時間很高 | 改 mutex |
| false sharing（`partial[id]` 相鄰） | 加執行緒反而變慢，但結果正確 | `alignas(64)` padding，或迴圈內用區域變數 |
| 傳區域變數位址給 `pthread_create`，迴圈變數被改 | 執行緒拿到錯的 id | 用陣列 `args[i]` 或把值轉成 `(void*)(intptr_t)i` |
| 忘了 `pthread_join` 就讀結果 | 結果偶爾不完整 | join 之後才讀 |
| 少了 `-pthread` | 連結錯誤或行為異常 | 編譯與連結都加 `-pthread` |
| pico：core1 stack overflow | core1 當機 / 資料被亂改 / HardFault | 大陣列改 static；調大 `PICO_CORE1_STACK_SIZE` 或自己給 stack |
| pico：自己使用 FIFO，又呼叫 `multicore_lockout_*` / 用到會佔 FIFO 的功能 | 收到奇怪的值、卡住 | 改用 `queue_t` |
| pico：FIFO 滿了還寫（非 blocking 寫法） | 資料遺失，`multicore_fifo_get_status()` 的 WOF=1 | 用 `_blocking`，或先檢查 `multicore_fifo_wready()` |
| pico：只關中斷就以為跨核安全 | 另一核仍然同時改資料 | `critical_section_t` 或 spinlock |
| pico：ISR 裡呼叫 `mutex_enter_blocking` / `queue_add_blocking` | 系統卡死 | ISR 用 `_try_` 版本 |
| pico：巢狀 `critical_section` 共用同一把 spinlock | 卡死 | `critical_section_init_with_lock_num` 給不同編號 |
| pico：直接讀寫 SIO spinlock 暫存器（舊 RP2040 寫法） | RP2350 上鎖被莫名釋放（E2） | 用 SDK API（預設軟體 spinlock） |
| pico：DMA 未完成就讀 dst | 讀到舊資料 / 部分資料 | `dma_channel_wait_for_finish_blocking` 之後才讀 |
| pico：DMA count 填 bytes | 寫超過 buffer（demo `make mistake`） | count = bytes / 每筆大小；用 `dma_encode_transfer_count` |
| pico：以為預設 config 就是 memcpy | 只有 dst 最後一個 word 被寫（預設 write 不遞增） | 明確呼叫 `channel_config_set_write_increment(&c, true)` |
| pico：64-bit 共享變數被 ISR / 另一核改 | 偶爾讀到一半新一半舊的值 | 關中斷 / critical_section / atomic |
| pico：熱迴圈裡 `printf` | 非常慢、兩核輸出順序亂 | 先存起來，最後印 |

---

## C3. 除錯檢查清單

- [ ] 能穩定重現嗎？多跑 10 次看結果是否都不同（不同 → 幾乎一定是 race）。
- [ ] Linux：`-fsanitize=thread -g -O1` 跑一次，逐一看每個報告（包括 demo 裡的 `sink`）。
- [ ] 卡住時：gdb 的 `thread apply all bt`（Linux）；pico 用 LED / UART 印出每核目前階段。
- [ ] 列出**所有**共享變數：誰寫、誰讀、受什麼保護？沒有保護的寫入都是嫌疑犯。
- [ ] 每個 lock 在所有路徑上（包括錯誤處理、早 return）都有對應的 unlock？
- [ ] condvar 都在 `while` 裡等？
- [ ] 拿多把鎖的地方順序一致？
- [ ] pico：core1 stack 夠嗎？有沒有在 core1 宣告大區域陣列？
- [ ] pico：FIFO 是否同時被自己的程式和 SDK 功能使用？
- [ ] pico：ISR 有沒有呼叫阻塞函式？
- [ ] pico：DMA 是否完成後才讀結果？count 單位正確？
- [ ] 改完後：結果正確 + 時間真的變短（多次量測）。

## C4. 優化檢查清單

- [ ] 量出 baseline（正確版本的時間），記錄下來。
- [ ] 能否完全不共享？（區域累加、分割資料）
- [ ] 鎖內只剩存取共享資料的幾行？
- [ ] 同步次數從 O(N) 降到 O(執行緒數)？
- [ ] 熱點沒有 false sharing（Linux）/ 沒有兩核 + DMA 搶同一 bank（pico）？
- [ ] 執行緒只建立一次？執行緒數 ≤ 可用核心數？
- [ ] spinlock 只用在持鎖極短、執行緒不超過核心數的情況？
- [ ] 熱迴圈裡沒有 `printf`、`malloc`、系統呼叫？
- [ ] pico：大量搬資料用 DMA？熱函式 `__not_in_flash_func`？熱資料放 scratch？
- [ ] 每改一項就量一次，確認是真的變快，而不是雜訊。
- [ ] 最後再跑一次正確性測試（以及 TSan），才提交。

## C5. Linux ↔ pico 對照

| 概念 | POSIX / C11 | pico-sdk |
|---|---|---|
| 建立並行執行者 | `pthread_create` / `pthread_join` | `multicore_launch_core1`（只有一個額外核心） |
| 互斥鎖 | `pthread_mutex_*` | `mutex_*`、`recursive_mutex_*` |
| 自旋鎖 | `pthread_spin_*` | `spin_lock_blocking` / `spin_unlock`（會關本核中斷） |
| 極短臨界區（含 IRQ） | — | `critical_section_*` |
| 號誌 | `sem_wait` / `sem_post` | `sem_acquire_blocking` / `sem_release` |
| 佇列 | 自己寫（A4 / A11） | `queue_t`、`multicore_fifo_*` |
| 原子操作 | `<stdatomic.h>` | 同左（RP2350 lock-free；RP2040 用 spinlock 模擬） |
| 屏障 | `atomic_thread_fence` | `__dmb()`、`__mem_fence_acquire/release()` |
| 計時 | `clock_gettime(CLOCK_MONOTONIC)` | `time_us_64()`、`absolute_time_diff_us()` |
| 偵錯 | TSan、helgrind、gdb | UART 印出、LED、SWD 除錯器（若有） |

---

## C6. 向模型提問的範本

**範本 1：分析共享資料**

```
以下是一段 {{C / pico-sdk}} 程式，執行環境是 {{Linux 容器，nproc = ? / RP2350 雙核}}。
{{貼程式碼}}
請：
1. 列出所有被兩個以上執行緒（或核心 / ISR）存取的變數，標明誰讀、誰寫、目前用什麼保護。
2. 指出每一個 data race 或 read-modify-write 沒保護的位置（行號）。
3. 判斷哪些變數其實可以改成每執行緒區域變數、最後合併。
只分析，先不要改程式。
```

**範本 2：優化臨界區**

```
目標：在結果正確的前提下讓 {{函式名 / 程式}} 變快。目前量測：{{單執行緒 X ms，N 執行緒 Y ms}}。
限制：{{不能改介面 / 必須保留某行為 / 題目規定}}。
{{貼程式碼}}
請依照「先不共享 → 再分割 → 再 atomic → 最後才用鎖、鎖越短越好」的順序提出修改，
每個修改說明：為什麼正確（happens-before 從哪裡來）、預期加速多少、有什麼風險。
給完整可編譯的程式碼，並附上我該怎麼量測驗證。
```

**範本 3：卡住 / 結果時好時壞**

```
程式 {{卡住 / 結果每次不同 / 偶爾當機}}。
重現步驟：{{指令}}，跑 {{10}} 次有 {{?}} 次出錯。
{{TSan / gdb bt / UART 輸出}}：
{{貼輸出}}
相關程式碼：
{{貼程式碼}}
請列出最可能的 3 個原因（依可能性排序），每個原因給一個能確認或排除它的實驗。
```

**範本 4：RP2350 雙核分工**

```
平台：RP2350（{{Arm Cortex-M33 / Hazard3 RISC-V}}），pico-sdk {{版本}}。
目前單核流程：{{步驟 1 → 步驟 2 → 步驟 3}}，各步驟時間約 {{a / b / c µs}}。
請設計 core0 / core1（以及是否用 DMA）的分工，說明：
- 用 queue_t、FIFO 還是共享記憶體 + critical_section 傳資料，為什麼；
- buffer 的所有權怎麼轉移、哪裡需要記憶體屏障；
- core1 stack 是否足夠、資料放哪個 SRAM 區；
- 預期加速上限（Amdahl）。
API 請只使用 pico-sdk 實際存在的函式，不確定的請標明。
```

**範本 5：查證 API**

```
我在考場文件看到 {{API 名稱 / 暫存器 / 段落}}：{{貼文字}}。
請用自己的話解釋它做什麼、參數單位、阻塞與否、能不能在 ISR / 另一核使用，
並指出和 {{我原本以為的 API}} 的差異。如果文件與你的記憶不同，以文件為準並說明差在哪。
```
