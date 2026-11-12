# 第 7 章　linux-perf/：電腦端計時、pthread 平行化、生產者 / 消費者 pipeline

> 本章對應的檔案：`預製程式碼/linux-perf/` 全部 4 個（`README.md`、`bench.h`、`parallel_template.c`、`pipeline_template.c`）｜驗證狀態：✅ host gcc 13.3 `-Wall -Wextra` 0 警告、結果全部正確（racy 錯是故意的）；✅ ThreadSanitizer：`pipeline_template.c` 沒有警告、`parallel_template.c` 只在 racy 版報 data race；✅ 官方 `考試相關資訊/section2-3/critical-section` 實際跑過對照；⚠️ `perf` 這個容器沒有安裝，沒實測｜最後核對：2026-11-12（commit d102c17）

## 7.0 30 秒版：什麼時候打開這一章

- 題目出現 **「加速」「多執行緒」「pthread」「平行」「切塊」「合併」** → 7.3.3 `parallel_template.c`，改 `work()`（`:28-31`）和 `N`（`:22`），用 `local` 版。
- 題目出現 **「race condition」「結果每次不一樣、而且偏少」「lost update」「臨界區」「鎖太久」** → 7.2.3～7.2.5 概念，再看 7.4.3、7.4.4；Pico 上的同一件事見第 3 章（`pico/app_multicore.c`）。
- 題目出現 **「一個收資料、一個計算」「queue」「ring buffer」「生產者 / 消費者」「pipeline」** → 7.3.4 `pipeline_template.c`，用 C 版（SPSC + 批次）。
- 題目要你 **量時間、比較哪個快** → 7.3.2 `bench.h`：`#include "bench.h"` 放第一行，`BENCH("名稱", 5, { ... })`。
- 最常改的 3 個地方：`parallel_template.c:28-31` `work()`、`pipeline_template.c:25` `item_t`、`pipeline_template.c:31-39` `produce()` / `compute()`。
- 三條鐵律：**熱迴圈裡不要有鎖或原子操作**（各算各的，最後合併一次）；**每個執行緒寫的變數至少隔 64 bytes**；**先量再改，量的時候用 `-O2`**。

## 7.1 檔案總表

| 檔案 | 行數 | 做什麼 | 什麼時候用 | 驗證狀態 |
|---|---|---|---|---|
| `README.md` | 81 | 檔案表、編譯指令、作者的實測（Ryzen 5 5600）、10 條優化清單、量測工具指令、模板 ↔ 清單對照 | 要優化時先看清單 | ✅ 編譯指令照做；工具指令：`valgrind`、`gprof`、`time` 本章實測，`perf` 沒有安裝 |
| `bench.h` | 55 | `now_ns()`、`BENCH()`、`do_not_optimize()`、`clobber_memory()` | 任何 C 程式要計時 | ✅ 兩個模板都用它；include 順序錯誤、巨集逗號錯誤都實測過錯誤訊息 |
| `parallel_template.c` | 136 | 同一個加總工作用 8 種寫法跑（serial、local、mutex、spinlock、atomic、racy、false-share、padded）並比較 | 資料平行、示範鎖和 false sharing 的成本 | ✅ 本機 4 核實測（7.5） |
| `pipeline_template.c` | 169 | 生產者 / 消費者 3 種佇列（mutex+condvar、SPSC 無鎖、SPSC 批次） | 一邊收一邊算 | ✅ 本機實測（7.5）；TSan 無警告 |

## 7.2 先懂這些概念

### 7.2.1 執行緒、核心、牆上時間

- **執行緒（thread）**：同一個程式裡可以同時跑的一條執行流程。同一個程式的執行緒**共用記憶體**（全域變數大家都看得到）。
- **核心（core）**：真正執行指令的硬體。4 核 = 同時最多 4 條執行緒真的在跑。執行緒比核心多時，作業系統輪流讓它們跑。
- **pthread**：Linux 的執行緒 API。`pthread_create(&th, NULL, 函式, 參數)` 開一條；`pthread_join(th, NULL)` 等它結束。編譯要加 `-pthread`。
- **牆上時間（wall time / real）**：碼表量的時間。**CPU 時間（user + sys）**：所有核心加起來花的時間。`time ./prog` 看到 user + sys > real，代表有平行（本章實測 `./par 2`：`real 6.862s`、`user 11.690s`）。
- **加速（speedup）** = 單執行緒時間 ÷ 平行時間。4 核理想是 4x，實際上會被「合併」、「開執行緒」、「搶共用資源」吃掉一些。

### 7.2.2 為什麼 `counter++` 會出錯（race condition）

`counter++` 在機器上是 3 步：讀出來 → 加 1 → 寫回去。兩條執行緒同時做，就可能：

```text
時間 →
執行緒 A：讀 counter=5 ........ 加1=6 .. 寫回 6
執行緒 B：........ 讀 counter=5 ........ 加1=6 .. 寫回 6
結果：做了兩次 ++，counter 只從 5 變 6 → 少了一次（lost update）
```

- **race condition（競爭條件）**：結果取決於執行緒的先後順序。特徵：**每次跑結果不一樣，而且總是偏少**。
- **data race**：兩條執行緒同時存取同一個變數、至少一個在寫、又沒有同步。C11 規定這是未定義行為。`volatile` **不能**解決（`parallel_template.c:40` 的 `g_racy` 就是 `volatile`，結果還是錯）。

### 7.2.3 臨界區與 3 種保護方法

- **臨界區（critical section）**：存取共享資料、一次只能一條執行緒做的那幾行程式。
- **mutex（互斥鎖）**：拿不到鎖就**睡覺**，讓出 CPU，等別人放鎖時被叫醒。等很久時省 CPU；但每次 lock/unlock 都有成本，搶的時候還要進作業系統。
- **spinlock（自旋鎖）**：拿不到鎖就**一直原地繞圈**檢查。臨界區超短、而且執行緒數 ≤ 核心數時才划算；拿著鎖的執行緒被作業系統暫停時，其他人會白繞（本章 T=8 實測 spinlock 5021 ms，7.5）。官方 demo（`pthread_spin_lock`）和 Pico SDK 的 `spin_lock_*` 都是這種。
- **atomic（原子操作）**：CPU 一條指令完成「讀-改-寫」，例如 `atomic_fetch_add`。不用鎖，但那個變數所在的 cache line 會在核心之間搬來搬去，還是慢。
- 共同原則：**鎖要抓得越短越好**、**最好根本不要在熱迴圈裡共享**。

### 7.2.4 cache line 與 false sharing

- **cache（快取）**：每個核心旁邊的小而快的記憶體。CPU 不是一個 byte 一個 byte 從主記憶體拿，而是一次拿一條 **cache line**，這台機器是 **64 bytes**（`getconf LEVEL1_DCACHE_LINESIZE` 實測 64）。
- **一致性（coherence）**：某個核心要**寫**一條 line 時，其他核心手上同一條 line 的副本都要作廢。下次別人要用，得重新從寫的人那裡搬過來。
- **false sharing（偽共享）**：兩條執行緒寫的是**不同變數**，但這兩個變數剛好在**同一條 cache line**，結果那條 line 在兩個核心之間一直搬來搬去，跟真的共用一樣慢。

```text
slot_packed[T_MAX]（parallel_template.c:41，每格 uint64_t = 8 bytes）
一條 64B cache line 裝得下 8 格：
  +------+------+------+------+------+------+------+------+
  | [0]  | [1]  | [2]  | [3]  | [4]  | [5]  | [6]  | [7]  |   ← 同一條 line
  +------+------+------+------+------+------+------+------+
    ↑core0  ↑core1  ↑core2  ↑core3
  core0 寫 [0] → 其他核心的這條 line 作廢
  core1 寫 [1] → 先把整條 line 從 core0 搶過來 → core0 再寫 [0] 又搶回去 ……

slot_padded[T_MAX]（parallel_template.c:42-43，每格 _Alignas(64) → sizeof = 64）
  line A: | [0] ...................... 56 bytes 空 |   ← 只有 core0 寫
  line B: | [1] ...................... 56 bytes 空 |   ← 只有 core1 寫
  各寫各的 line，不互相干擾
```

- 修法：每個執行緒的變數補到 64 bytes（`_Alignas(64)`），或像 `local` 版一樣用區域變數（放在暫存器或自己的堆疊），最後才寫一次共享陣列。

### 7.2.5 記憶體順序（acquire / release）

- 現代 CPU 和編譯器會**重新排列**記憶體存取（只要單執行緒看起來結果一樣）。多執行緒時，另一條執行緒可能看到「旗標已經設好，但資料還沒寫進去」。
- **release store**：這個寫入之前的所有讀寫，都要在它之前完成（別人看到這個值時，前面的資料也一定看得到）。
- **acquire load**：這個讀取之後的所有讀寫，都不能提前到它前面。
- 一對 release（寫的人）+ acquire（讀的人）就能安全地「交棒」資料，不需要鎖。
- **relaxed**：只保證這個變數本身的讀寫是原子的，不保證和其他變數的先後。`parallel_template.c:70` 的 atomic 版用 relaxed，因為只關心最後總和，而且 `pthread_join` 之後才讀。

### 7.2.6 環形緩衝區（ring buffer）與 SPSC

- **ring buffer**：固定大小的陣列，寫到尾巴再從頭開始，用兩個計數器記位置：`head`（生產者下一個要寫的）、`tail`（消費者下一個要讀的）。
- **SPSC（Single-Producer Single-Consumer）**：只有一個寫的人、一個讀的人。`head` 只有生產者寫、`tail` 只有消費者寫 → 不需要鎖，只要 acquire / release。

```text
CAP = 8 的例子（pipeline_template.c 是 1024）
head、tail 一直往上加，不歸零；索引 = 計數器 & (CAP-1)
         tail=5                head=11
           ↓                     ↓
計數器:  5  6  7  8  9  10 | 11 ...
索引:    5  6  7  0  1  2  | 3
內容:   [有][有][有][有][有][有]  ← 6 筆待處理 = head - tail
空：head == tail            滿：head - tail == CAP
```

- 這種寫法 CAP 個格子全部都能用（不需要「留一格空著」分辨空和滿），因為空和滿是用計數器差值判斷，不是用索引。
- `CAP` 必須是 2 的次方，`& (CAP-1)` 才等於 `% CAP`（`pipeline_template.c:22` 註解）。計數器是 `size_t`，溢位要 2^64 筆，不會發生；就算溢位，無號減法 `head - tail` 也還是對的。

### 7.2.7 批次（batch）

- 每傳一筆都要付固定成本（一次 release store、對方一次 cache line 搬移、可能一次喚醒）。一次傳 64 筆，固定成本變 1/64。
- 這和第 2 章序列埠的批次傳輸（`ros2/serial_bridge.py`）是同一個道理。

## 7.3 逐檔說明

### 7.3.1 `README.md`

#### 用途

資料夾入口：檔案表（`:3-7`）、編譯指令（`:9-13`）、要改什麼（`:14`）、作者在 AMD Ryzen 5 5600（6 核 12 緒）上的實測（`:16-44`）、優化檢查清單 10 條（`:46-57`）、量測工具（`:59-70`）、模板 ↔ 清單對照（`:72-81`）。

#### 怎麼編譯 / 執行

README `:10-12` 原文（在 `預製程式碼/linux-perf/` 執行）：

```sh
B=/tmp/t; mkdir -p $B
gcc -O2 -Wall -Wextra -std=c11 -pthread parallel_template.c -o $B/par && $B/par 4   # 參數 = 執行緒數
gcc -O2 -Wall -Wextra -std=c11 -pthread pipeline_template.c -o $B/pipe && $B/pipe
```

本章照做，兩支都 0 警告。`par 4` 本章實測整支跑完 `real 0m10.972s`（mutex / spinlock 版很慢），不是當機。

#### 對外介面

優化清單（`:48-57`）的重點和本章對照：

| # | 清單內容 | 本章哪裡有實測 |
|---|---|---|
| 1 | 先量測，不要猜（`BENCH`、`time`） | 7.3.2、7.5 |
| 2 | 編譯選項 `-O2` → `-O3` → `-O3 -march=native` | 7.5：serial 46.9 ms → 15.5 ms |
| 3 | 熱迴圈裡不要有鎖 / 原子操作；臨界區要短 | 7.5：mutex 0.11x～0.36x、local 3.89x |
| 4 | 批次處理 | 7.5：pipeline C 版 1.56x vs B 版 0.85x |
| 5 | cache 友善、避開 false sharing | 7.5：padded 3.79x vs false-share 2.75x |
| 6 | 查表 | 第 5 章 `algo/crc32.c` |
| 7 | 強度削減（`% 256` → `& 255`） | 7.4.7：無號數編譯器自己會做，實測 1.06x |
| 8 | 迴圈展開 | 第 5 章 |
| 9 | `restrict` | 沒有實測 |
| 10 | 換演算法 | 第 5 章 `algo/sort.c` |

#### 程式流程

不適用。

#### 要改的地方

沒有 `TODO(改這裡)`。`:14` 列出要改的是 `work()`、`N`、`produce()/compute()`、`item_t`，見 7.3.3、7.3.4。

#### 實際執行輸出

README `:16-44` 的數字是作者在別台機器（Ryzen 5 5600）量的，**不是這個容器**。本章在這個容器重量的數字見 7.5，兩邊趨勢一樣（local 最快、mutex/spinlock/atomic 比單執行緒慢、padded 比 false-share 快、SPSC 批次最快），但倍數不同。

量測工具（`:61-70`）在這個容器的狀態：

| 工具 | 這個容器 | 本章實測 |
|---|---|---|
| `time ./prog` | bash 內建 `time` 可用；`/usr/bin/time` 沒有安裝 | ✅ `real 6.862s / user 11.690s / sys 0.858s`（`./par 2`） |
| `perf stat` / `perf record` | **沒有安裝**（`which perf` 沒結果）；`/proc/sys/kernel/perf_event_paranoid` = 2 | 沒有實測 |
| `valgrind --tool=callgrind` + `callgrind_annotate` | valgrind 3.22.0 可用 | ✅（下面） |
| `gcc -pg` + `gprof` | 可用 | ✅（下面） |
| ThreadSanitizer `-fsanitize=thread` | 可用（README 提到用過，沒列指令） | ✅（7.3.3、7.3.4） |

`gprof`（在暫存資料夾，`L` = `linux-perf` 的路徑）：

```sh
gcc -O2 -g -pg -std=c11 -pthread $L/parallel_template.c -o par_pg && ./par_pg 1 > /dev/null && gprof -b ./par_pg gmon.out | head -20
```

本章實測輸出（節錄）：

```text
  %   cumulative   self              self     total
 time   seconds   seconds    calls  ms/call  ms/call  name
 27.45      0.28     0.28        3    93.33    93.33  w_local
 17.65      0.46     0.18                             w_atomic
 14.71      0.61     0.15                             w_racy
 13.73      0.75     0.14                             w_false
 13.73      0.89     0.14                             w_padded
  5.88      0.95     0.06                             w_mutex
  3.92      0.99     0.04                             w_spin
```

注意：`calls` 只有主執行緒呼叫的才會被算（`w_local` 的 3 次是 serial 那 3 次），其他執行緒裡跑的函式只有取樣時間、沒有呼叫次數。gprof 適合單執行緒程式。

`callgrind`（在暫存資料夾）：

```sh
gcc -O2 -g prog.c -o prog && valgrind --tool=callgrind --callgrind-out-file=cg.out ./prog && callgrind_annotate cg.out | head -40
```

本章對 `bits-riscv/rv32_encode_decode.c`（很短的程式）實測：總指令數 `259,357`，前幾名是動態連結器（`dl-tunables.c` 42.62%、`dl-lookup.c` 9.64%）。**程式太短時，啟動成本會蓋過你的程式**；要分析就讓熱點跑久一點，或加 `--toggle-collect=函式名` 只收那個函式。

#### 常見錯誤

| 症狀 | 原因 | 修法 |
|---|---|---|
| `perf: command not found` | 沒裝 | 用 `BENCH` / `gprof` / `callgrind`；考場要用 perf 先問監考 |
| `perf_event_paranoid` 權限錯誤 | 核心限制（README `:69`） | `sudo sysctl kernel.perf_event_paranoid=1`，考場先問；這個容器是 2 |
| 加了 `-O0` 量時間，數字很奇怪 | `-O0` 和實際交出去的程式差太多 | 量測用 `-O2`；要看行號加 `-g`（README `:70`） |

### 7.3.2 `bench.h`

#### 用途

計時工具（`bench.h:1-12`）：單調時鐘 `now_ns()`、取最快一次的 `BENCH()`、防止編譯器把計算刪掉的 `do_not_optimize()`、強迫記憶體寫回的 `clobber_memory()`。

#### 怎麼編譯 / 執行

不能單獨執行。**必須是第一個 `#include`**（`bench.h:2`），因為它要在任何系統標頭之前定義 `_POSIX_C_SOURCE`（`:15-17`），`-std=c11` 下 `clock_gettime` 才會被宣告。

#### 對外介面

| 名稱 | 位置 | 參數 | 回傳 / 效果 | 注意 |
|---|---|---|---|---|
| `now_ns()` | `:23-27` | 無 | 目前時間（奈秒），`CLOCK_MONOTONIC` | 單調時鐘：不受改系統時間影響；只能拿來算差值 |
| `do_not_optimize(x)` | `:30-31` | 任何整數 | 把 x 加進 `volatile` 變數 `bench_sink_` | 每次多一次記憶體寫入，在極短的迴圈裡會有一點成本 |
| `clobber_memory()` | `:34-38` | 無 | 空的 `asm volatile("" ::: "memory")` | 告訴編譯器「記憶體可能被改了」，量寫陣列的程式時防止寫入被延後或刪掉；GCC/Clang 專用 |
| `bench_last_ns` | `:41` | — | 最近一次 `BENCH` 的最快時間（ns） | 算加速倍數用 |
| `BENCH(name, reps, code)` | `:42-53` | 名稱字串、次數、程式碼 | 跑 reps 次，印最快一次 `  名稱   x.xxx ms` | **code 裡不能有不在括號內的逗號**（見常見錯誤） |

#### 程式流程

`BENCH`（`:42-53`）：
1. `best_ = UINT64_MAX`。
2. 重複 reps 次：`t0_ = now_ns()` → 執行 `code` → `clobber_memory()` → `dt_ = now_ns() - t0_` → 取最小。
3. 存到 `bench_last_ns`，印 `printf("  %-28s %10.3f ms\n", name, best_ / 1e6)`。

**為什麼取最快一次**（`bench.h:9`）：其他次數多半被別的程式、中斷、cache 還沒熱等因素干擾，最快那次最接近程式本身的成本。本章在這個容器量的時候，同時有其他工作在跑，取最小值仍然有波動（7.5），所以比較時要多跑幾次。

**為什麼要 `do_not_optimize`**（`bench.h:11`）：`-O2` 會把「算了但結果沒人用」的程式整段刪掉，量出 0 ms。把結果丟給 `do_not_optimize` 就刪不掉。

用法：

```c
#include "bench.h"          // 一定要第一個
#include <stdlib.h>
...
uint64_t r = 0;
BENCH("my_func", 5, { r = my_func(a, n); do_not_optimize(r); });
printf("加速 %.2fx\n", (double)base_ns / bench_last_ns);
```

#### 要改的地方

沒有 `TODO(改這裡)`。

#### 實際執行輸出

`bench.h` 不放第一個時（本章實測，`order.c` 先 `#include <stdio.h>` 再 `#include "bench.h"`，`-std=c11`）：

```text
bench.h:25:5: warning: implicit declaration of function 'clock_gettime' [-Wimplicit-function-declaration]
bench.h:25:19: error: 'CLOCK_MONOTONIC' undeclared (first use in this function)
```

改用 `-std=gnu11` 就能編過（gnu 模式預設打開 POSIX 宣告），但一律把 `bench.h` 放第一個最簡單。

`code` 裡有不在括號內的逗號時（本章實測）：

```text
comma.c:2:74: error: macro "BENCH" passed 4 arguments, but takes just 3
    2 | int main(void){ BENCH("x", 3, { int a = 1, b = 2; do_not_optimize(a+b); }); return 0; }
```

大括號 `{}` 不會保護逗號（只有小括號會）。改成 `int a = 1; int b = 2;` 就好；函式呼叫的逗號 `f(a, n)` 在小括號裡，沒問題。

#### 常見錯誤

| 症狀 | 原因 | 修法 |
|---|---|---|
| `'CLOCK_MONOTONIC' undeclared` | `bench.h` 不是第一個 include | 移到第一行 |
| `macro "BENCH" passed 4 arguments` | code 區塊裡有 `int a = 1, b = 2;` 之類的逗號 | 拆成兩行宣告，或用小括號包起來 |
| 量出 0.000 ms | 結果沒用到，被最佳化刪掉 | `do_not_optimize(結果)` |
| `'bench_last_ns' defined but not used` 警告 | `static` 變數在沒用 `BENCH` 的檔案也會出現 | 無害；或在那個檔案不要 include `bench.h` |
| 同一段程式每次量差很多 | 機器上有別的工作、CPU 降頻 | 多跑幾次（reps 加大），比較時兩個版本輪流跑 |

### 7.3.3 `parallel_template.c`

#### 用途

pthread 平行化模板：「切 T 塊 → 各算各的 → 最後合併」（`:1-16`）。同一個工作（把 N 個元素的 `work(x)` 加總）用 8 種寫法跑，直接看到鎖、原子操作、false sharing 的成本。考場上要的是 **local 版**，其他是對照組。

#### 怎麼編譯 / 執行

在 `預製程式碼/linux-perf/`：

```sh
gcc -O2 -Wall -Wextra -std=c11 -pthread parallel_template.c -o /tmp/par && /tmp/par 4
```

參數 = 執行緒數 T（1～64，超出範圍或沒給就用 4，`:110-111`）。預期每一項都印「結果正確」，只有 racy 印「結果錯誤！」，最後一行 `結果：全部正確（racy 錯是預期的）`，回傳 0。

看核心數：`nproc`（這個容器是 4）。

#### 對外介面

| 名稱 | 位置 | 意思 | 注意 |
|---|---|---|---|
| `N` | `:22` | 資料量 `1u << 23` = 8,388,608 | `TODO(改這裡)` |
| `T_MAX` | `:23` | 最多 64 條執行緒 | |
| `data[N]` | `:24` | 輸入資料（`main` 用 `rand()` 填） | 32 MiB 靜態陣列 |
| `T` | `:25` | 執行緒數，`argv[1]` | |
| `work(x)` | `:28-31` | 每個元素的計算：8 輪 xorshift，回傳低 16 位 | `TODO(改這裡)` |
| `job_t` | `:33` | `{id, lo, hi}`：負責 `[lo, hi)` | |
| `part[]`、`g_sum`、`g_mtx`、`g_spin`、`g_atomic`、`g_racy`、`slot_packed[]`、`slot_padded[]` | `:35-43` | 各版本用的共享變數 | `padded_t` 用 `_Alignas(64)`，`sizeof` = 64 |
| `w_local` … `w_padded` | `:45-87` | 7 個執行緒函式 | 見下表 |
| `run(fn)` | `:90-97` | 開 T 條執行緒跑 fn，平均切塊，全部 join | 沒檢查 `pthread_create` 的回傳值 |
| `sum_parts()` | `:99` | 加總 `part[0..T-1]` | |
| `report(name, got, want)` | `:103-107` | 印正確與否和加速倍數；名稱以 `(` 開頭表示「預期會錯」，不算進 fails | |

8 種寫法，為什麼快 / 慢（倍數是本章 T=4 實測，7.5）：

| 寫法 | 熱迴圈裡做什麼 | 為什麼 | T=4 實測 |
|---|---|---|---|
| serial（`:117-118`） | 一條執行緒用 `w_local` 跑全部 | 基準 | 1x |
| local（`:45-50`） | `s += work(...)`，s 是區域變數；最後 `part[id] = s` 寫一次 | 區域變數在暫存器，執行緒之間完全不碰共享資料 | **3.89x**（最快） |
| mutex（`:51-58`） | 每個元素 `lock; g_sum += v; unlock` | 計算在鎖外（臨界區已經很短），但 lock/unlock 每次都要原子操作，而且 4 條一直搶同一把鎖 | 0.13x |
| spinlock（`:59-66`） | 每個元素 `spin_lock; g_sum += v; spin_unlock` | 同上，而且搶不到就原地繞圈，鎖變數的 cache line 在 4 核之間來回 | 0.03x |
| atomic（`:67-72`） | 每個元素 `atomic_fetch_add(relaxed)` | 不用鎖，但 `g_atomic` 那條 line 每次都要搬到正在寫的核心 | 0.18x |
| racy（`:73-77`） | `g_racy += work(...)`，沒有保護 | 讀-改-寫互相覆蓋 → 答案錯；也有 false sharing | 2.70x 但**答案錯** |
| false-share（`:78-82`） | `slot_packed[id] += ...`，每條寫自己的格子 | 答案對，但 8 格擠在同一條 64B line（7.2.4 圖） | 2.75x |
| padded（`:83-87`） | `slot_padded[id].v += ...`，每格 64 bytes | 每格自己一條 line | 3.79x |

（`slot_packed` 和 `slot_padded` 都是 `volatile`，每次 `+=` 都真的讀寫記憶體，所以這兩個的差距完全來自 cache line。local 版沒有 volatile，所以比 padded 還快一點。）

#### 程式流程

`main`（`:109-136`）：
1. 讀 T（`:110-111`），用 `rand()` 填 `data`（`:112`），初始化 spinlock（`:113`）。
2. serial：用**同一個** `w_local` 跑 `[0, N)`（`:117-118`），結果當標準答案 `want`、時間當 `base_ms`（`:119`）。用同一個函式比較才公平（README `:44`）。
3. 依序跑 local、mutex、spinlock、atomic、racy、false-share、padded（`:120-131`），每個 `BENCH` 跑 3 次取最快；每次跑之前把共享變數歸零（例：`g_sum = 0`）。
4. `report` 比對答案、印加速倍數。
5. 有非預期的錯誤就回傳錯誤數（`:133-135`）。

`run()` 的切塊（`:93`）：`lo = N*t/T`、`hi = N*(t+1)/T`。所有塊接起來剛好是 `[0, N)`，每塊大小最多差 1，N 不是 T 的倍數也對。

#### 要改的地方

| 行號 | 現在的值 | 意思 | 什麼情況要改、改成什麼 |
|---|---|---|---|
| `parallel_template.c:22` | `#define N (1u << 23)` | 資料量 | 改成題目的資料量；資料從檔案讀時，把 `data` 改成 `malloc` 的指標、N 改成變數 |
| `parallel_template.c:27` | `/* 每個元素要做的事  TODO(改這裡)… */`（`:28-31` 的 `work()`） | 每個元素的計算 | 換成題目的計算（CRC、hash、比對…）；回傳值是要加總的量。「加總」換成別的合併（最大值、計數）時，`w_local` 的 `s +=` 和 `sum_parts()` 一起改 |
| `parallel_template.c:23` | `#define T_MAX 64` | 執行緒上限 | 通常不用改 |

只要 local 版時：刪掉 mutex 到 padded（`:120` 以後只留 local），程式跑得快很多。

#### 實際執行輸出

環境：Intel Xeon @ 2.30GHz、4 vCPU（`nproc` = 4，1 thread per core）、L1d 48 KiB/核、cache line 64 B、gcc 13.3 `-O2`、x86_64。量測時 load average 1.06（同一台容器上有其他工作）。

```text
$ ./par 4
N = 8388608, 執行緒 T = 4（每種跑 3 次取最快）
  serial                           53.009 ms
  local (推薦)                   13.623 ms
      → 結果正確  加速 3.89x  local
  mutex 每元素                 398.676 ms
      → 結果正確  加速 0.13x  mutex
  spinlock 每元素             1681.163 ms
      → 結果正確  加速 0.03x  spin
  atomic 每元素                301.165 ms
      → 結果正確  加速 0.18x  atomic
  racy 不加鎖(錯誤示範)     19.628 ms
      → 結果錯誤！  加速 2.70x  (racy: lost update 預期會錯)
  false-share 相鄰格子         19.285 ms
      → 結果正確  加速 2.75x  false-share
  padded 補到 64B                13.980 ms
      → 結果正確  加速 3.79x  padded
結果：全部正確（racy 錯是預期的）
```

更多執行緒數、多次重跑的數字見 7.5。

ThreadSanitizer（本章實測，在暫存資料夾）：

```sh
gcc -O1 -g -fsanitize=thread -std=c11 -pthread $L/parallel_template.c -o par_tsan && ./par_tsan 2
```

```text
WARNING: ThreadSanitizer: data race (pid=26994)
    #0 w_racy .../linux-perf/parallel_template.c:75 (par_tsan+0x17b9)
  Location is global 'g_racy' of size 8 at 0x55b2156712c0 (par_tsan+0x62c0)
```

只有 racy 版（`:75`）被報出來，回傳值是 66（TSan 有報告時的預設值）。false-share / padded 雖然慢，但每格只有一條執行緒寫，不是 data race，TSan 不報。

#### 常見錯誤

| 症狀 | 原因 | 修法 |
|---|---|---|
| 結果每次不一樣，而且偏小 | 共享變數沒保護（racy） | 改成 local 版：區域變數累加、最後寫一次 |
| 加了鎖，結果對了但比單執行緒還慢 | 每個元素都 lock | 鎖只在合併時用一次；或 local 版完全不用鎖 |
| 每條寫自己的格子，還是沒變快 | false sharing | `_Alignas(64)`（照 `padded_t`），或區域變數 |
| `undefined reference to 'pthread_create'` | 沒加 `-pthread` | 編譯和連結都加 `-pthread` |
| 執行緒數開到 8、spinlock 版跑好幾秒 | 執行緒比核心多，拿著鎖的被作業系統暫停，其他人白繞 | 執行緒數 ≤ `nproc`；長時間等待用 mutex |
| 平行版答案和 serial 不同（不是 racy） | 合併運算不滿足交換律 / 結合律（例如浮點數加總、照順序的 hash） | 浮點容許誤差；照順序的計算不能這樣切，改用 pipeline |
| 平行反而變慢（單執行緒的 work 很輕） | 開執行緒、合併的固定成本 > 計算 | N 太小就不要平行；或一次處理更多 |

### 7.3.4 `pipeline_template.c`

#### 用途

生產者 / 消費者 ring buffer（`:1-15`）：模擬「一個核心收資料（producer），另一個核心計算（consumer）」，收和算同時進行。3 種佇列：A mutex + condvar（通用、最不容易錯、慢）、B SPSC 無鎖、C SPSC + 批次（最快）。對應 Pico 的「core0 收、core1 算」（`:13-14`）。

#### 怎麼編譯 / 執行

在 `預製程式碼/linux-perf/`：

```sh
gcc -O2 -Wall -Wextra -std=c11 -pthread pipeline_template.c -o /tmp/pipe && /tmp/pipe
```

沒有參數。預期 4 行時間、3 行「結果正確」、最後 `結果：全部正確`，回傳 0。

#### 對外介面

| 名稱 | 位置 | 意思 | 注意 |
|---|---|---|---|
| `CAP` | `:22` | 佇列容量 1024 | 必須是 2 的次方 |
| `N_ITEMS` | `:23` | 總共傳幾筆 `1u << 20` | `TODO(改這裡)` |
| `BATCH` | `:24` | C 版每批最多 64 筆 | |
| `item_t` | `:25` | 一筆資料的型別（現在是 `uint32_t`） | `TODO(改這裡)` |
| `PROD_COST`、`COMP_COST` | `:29-30` | 模擬收 / 算的成本（迴圈次數） | 兩邊都有前後依賴，編譯器無法向量化（`:27-28`） |
| `produce(&st)` | `:31-34` | 產生一筆 | `TODO(改這裡)`（`:27`） |
| `compute(acc, x)` | `:35-39` | 把一筆混進累積值，回傳新累積值 | 照順序計算（結果和順序有關），所以能檢查 pipeline 有沒有掉資料或亂序 |
| `mq`、`mq_push`、`mq_pop` | `:42-62` | A 版：mutex + 兩個 condvar | |
| `q`、`spsc_push`、`spsc_pop` | `:65-86` | B 版：SPSC 無鎖 | 只能一個生產者、一個消費者 |
| `spsc_push_n`、`spsc_pop_n` | `:88-103` | C 版：一次放 / 拿多筆，回傳實際數量 | |
| `producer`、`consumer` | `:109-143` | 執行緒本體，依 `mode` 選 A/B/C | |
| `run_pipeline(m)` | `:145-151` | 先開 consumer 再開 producer，兩個都 join | |

#### 程式流程

**A 版 mutex + condvar（`:42-62`）**：

```text
mq_push(v):                               mq_pop():
  lock(m)                                   lock(m)
  while (head - tail == CAP) wait(not_full) while (head == tail) wait(not_empty)
  buf[head++ % CAP] = v                     v = buf[tail++ % CAP]
  signal(not_empty)                         signal(not_full)
  unlock(m)                                 unlock(m)
```

- **condvar（條件變數）**：讓執行緒「睡到條件成立」。`pthread_cond_wait` 會**自動放開鎖**再睡，醒來時重新拿鎖。
- 用 `while` 不用 `if`：醒來不保證條件成立（可能被別人搶先，或是假喚醒），要重新檢查。
- 每一筆都 lock/unlock + signal，所以慢。

**B 版 SPSC（`:65-86`）**：

```c
static bool spsc_push(item_t v) {                     /* 只能由 producer 呼叫 */
    size_t h = atomic_load_explicit(&q.head, memory_order_relaxed);
    size_t t = atomic_load_explicit(&q.tail, memory_order_acquire);
    if (h - t == CAP) return false;                   /* 滿 */
    q.buf[h & (CAP - 1)] = v;
    atomic_store_explicit(&q.head, h + 1, memory_order_release);
    return true;
}
```

每一個記憶體順序的理由：

| 位置 | 動作 | 順序 | 為什麼 |
|---|---|---|---|
| `:72` | producer 讀自己的 `head` | relaxed | 只有自己寫，不用同步 |
| `:73` | producer 讀 `tail` | acquire | 看到 consumer 放出的位置時，consumer 對那一格的**讀取**一定已經完成，才能覆寫 |
| `:75` | 寫 `buf[h & (CAP-1)]` | 一般寫入 | 被下一行的 release 保護 |
| `:76` | `head = h + 1` | release | consumer 看到新的 head 時，`:75` 寫進去的資料一定看得到 |
| `:80` | consumer 讀自己的 `tail` | relaxed | 只有自己寫 |
| `:81` | consumer 讀 `head` | acquire | 和 `:76` 配對 |
| `:83` | 讀 `buf[t & (CAP-1)]` | 一般讀取 | 被 `:81` 的 acquire 保護 |
| `:84` | `tail = t + 1` | release | 和 `:73` 配對：告訴 producer 這格可以重用 |

```text
producer                               consumer
① buf[h&1023] = v
② store(head, h+1, release)  ───────→  ③ load(head, acquire) 看到 h+1
                                       ④ v = buf[t&1023]   ← 一定是 ① 寫的值
                                       ⑤ store(tail, t+1, release)
⑥ load(tail, acquire) 看到 t+1 ←─────
⑦ 才能覆寫那一格
```

- 滿：`h - t == CAP`（`:74`）→ `spsc_push` 回 false，producer `sched_yield()` 再試（`:122`）。
- 空：`h == t`（`:82`）→ `spsc_pop` 回 false，consumer `sched_yield()` 再試（`:133`）。
- `head` 和 `tail` 各自 `_Alignas(64)`（`:67-68`），在不同 cache line，避免 producer 寫 head 時把 consumer 的 tail 那條 line 搶走（false sharing）。`buf` 是 4096 bytes，剛好是 64 的倍數，head 從新的一條 line 開始。

**C 版批次（`:88-103`）**：

```text
spsc_push_n(src, n):
  h = head（relaxed）
  room = CAP - (h - tail（acquire）)     ← 還有幾格空
  n = min(n, room)
  逐筆寫 buf[(h+i) & (CAP-1)]
  head = h + n（release）               ← 只做一次 release store
  回傳 n
spsc_pop_n(dst, max)：同理，n = head（acquire）- tail，最多拿 max 筆，tail = t + n（release）
```

- producer（`:112-118`）：先產生一批 `tmp[BATCH]`，`while (done < n)` 塞到塞完，塞不進去（回傳 0）就 `sched_yield()`。
- consumer（`:134-139`）：一次最多拿 `BATCH` 筆，拿到 0 筆就 `sched_yield()`，否則逐筆 `compute`。
- 原子操作次數變成 1/批次大小。

**執行緒本體與 main**：
- `producer`（`:109-126`）：`st = 1` 當亂數種子，產生 `N_ITEMS` 筆。
- `consumer`（`:128-143`）：已知總數，收滿 `N_ITEMS` 筆就停（`:131`，註解說也可以用特殊值當結束訊號），結果寫到 `consumer_sum`。
- `run_pipeline(m)`（`:145-151`）：設 `mode`，先開 consumer 再開 producer。`mode` 和 `consumer_sum` 是普通變數也安全，因為 `pthread_create` 之前寫、`pthread_join` 之後讀（這兩個函式本身就是同步點）。
- `main`（`:153-169`）：serial 版「收一筆算一筆」當標準答案和基準；A、B、C 各跑 3 次取最快，比對 `consumer_sum == want`。
- 每次跑完 head == tail，所以下一次跑不用把 `q` 歸零。

#### 要改的地方

| 行號 | 現在的值 | 意思 | 什麼情況要改、改成什麼 |
|---|---|---|---|
| `pipeline_template.c:23` | `#define N_ITEMS (1u << 20)` | 總筆數 | 改成題目的筆數；筆數事先不知道時，consumer 改成「收到結束標記就停」（`:131` 註解） |
| `pipeline_template.c:25` | `typedef uint32_t item_t;` | 一筆的型別 | 換成封包 struct，例：`typedef struct { uint8_t data[64]; uint16_t len; } item_t;`。同時改 `compute()`（`:36` 的 `(uint32_t)acc ^ x` 對 struct 不能編譯）；`q.buf` 變成 `CAP * sizeof(item_t)`（66 KiB），Pico 上要算 RAM 夠不夠 |
| `pipeline_template.c:27` | `/* 模擬「收一筆資料」與「算一筆資料」… TODO(改這裡) 換成真的收/算 */`（`:29-39`） | `produce()`、`compute()`、`PROD_COST`、`COMP_COST` | `produce` 換成真的讀資料（讀檔、讀序列埠）；`compute` 換成真的計算。計算結果與順序無關時，`main` 的比對方式也要改 |
| `pipeline_template.c:22` | `#define CAP 1024u` | 容量 | 收的速度不穩（一陣一陣）時加大；必須維持 2 的次方 |
| `pipeline_template.c:24` | `#define BATCH 64u` | 批次大小 | 每筆很大時改小；`tmp[BATCH]` 在堆疊上 |

#### 實際執行輸出

環境同 7.3.3（Intel Xeon 4 vCPU、gcc 13.3 `-O2`），load average 1.51：

```text
$ ./pipe
傳送 1048576 筆，佇列容量 1024（每種 3 次取最快）
  serial 單執行緒 收一筆算一筆    200.226 ms
  A mutex+condvar                 292.335 ms
      → 結果正確  加速 0.68x
  B SPSC 無鎖                   235.446 ms
      → 結果正確  加速 0.85x
  C SPSC 無鎖+批次            128.479 ms
      → 結果正確  加速 1.56x
結果：全部正確
```

README 在 Ryzen 上量的是 A 0.92x、B 1.50x、C 1.70x（`:37-40`）；這台的 B 版比單執行緒還慢，C 版仍然最快。重跑的數字見 7.5。

ThreadSanitizer（本章實測）：

```sh
gcc -O1 -g -fsanitize=thread -std=c11 -pthread $L/pipeline_template.c -o pipe_tsan && ./pipe_tsan
```

輸出沒有任何 `WARNING: ThreadSanitizer`，最後 `結果：全部正確`，總時間 `real 0m7.501s`。

`item_t` 換成 struct 的改法（7.4.6）也實測過，`N_ITEMS = 1<<16` 時 3 種都「結果正確」。

**同一段 SPSC 在 RP2350 上編成什麼**（本章把 `spsc_push` 單獨拿出來交叉編譯，objdump 實測）：

```text
RISC-V（Hazard3 的 -march，gcc 13.2）            Cortex-M33（arm-none-eabi-gcc 13.2）
  lw   a3,64(a3)       ← 讀 tail                   lda   r1,[r1]        ← acquire load
  fence                ← acquire                   ...
  ...                                              str.w r0,[r1,ip,lsl #2]  ← 寫 buf
  sw   a0,0(a3)        ← 寫 buf                    stl   r3,[r2]        ← release store
  fence iorw,ow        ← release
  amoswap.w zero,a5,(a4)  ← 寫 head
```

兩顆核心都用 C11 atomics 就能產生正確的屏障指令，不需要自己寫組語。

#### 常見錯誤

| 症狀 | 原因 | 修法 |
|---|---|---|
| 兩個 producer 同時 `spsc_push`，資料錯亂 | SPSC 只能一寫一讀 | 多個生產者用 A 版，或每個生產者一個 SPSC 佇列 |
| 程式卡住不結束 | consumer 等的筆數比 producer 送的多 | `N_ITEMS` 兩邊一致；或用結束標記 |
| `CAP` 改成 1000 後資料錯 | `& (CAP-1)` 只對 2 的次方等於 `% CAP` | 用 512、1024、2048 |
| 拿掉 acquire/release 改成 relaxed，偶爾讀到舊資料 | 沒有交棒的順序保證 | 保持 `:73`、`:76`、`:81`、`:84` 的順序 |
| 用 `volatile` 取代 `_Atomic` | `volatile` 不保證順序和原子性 | 用 `<stdatomic.h>` |
| CPU 一直 100% | 空 / 滿時用 `sched_yield()` 忙等 | 正常；要省電改用 A 版（會睡） |
| `item_t` 改 struct 後編譯錯 `invalid operands to binary ^` | `compute()` 還在對整數做 `^` | 改 `compute()`（7.4.6） |

## 7.4 照題目改：食譜

### 7.4.1 把每個元素的計算換成題目的（資料平行）

題目長這樣：「對 800 萬個 32 位元數各算一個 CRC-8，加總結果，越快越好。」

改哪些行：`parallel_template.c:28-31` 的 `work()`。本章實測的替換（逐位元 CRC-32 取低 8 位，只是示範計算量）：

```c
static inline uint64_t work(uint32_t x) {
    uint32_t c = 0xFFFFFFFFu;                       /* 每個元素算一個 CRC-32（4 bytes，逐位元） */
    for (int k = 0; k < 32; k++) c = (c >> 1) ^ (0xEDB88320u & -((c ^ (x >> k)) & 1u));
    return ~c & 0xFFu;
}
```

怎麼驗證：serial 和 local 結果一致（程式自己比對）。成功的樣子（本章實測，T=4）：

```text
  serial                          255.540 ms
  local (推薦)                   73.742 ms
      → 結果正確  加速 3.47x  local
```

真正的 CRC 用第 5 章 `algo/crc32.c` 的查表版，單執行緒先快起來再平行。

### 7.4.2 只留 local 版交出去

題目只要「正確又快」，不需要對照組：
1. 保留 `work`、`w_local`、`run`、`sum_parts`、`main` 的 serial + local 兩段（`:117-120`）。
2. 刪掉 `:121-131`（mutex 到 padded）和用不到的全域變數、執行緒函式（否則 `-Wall` 會警告 unused）。
3. T 用 `nproc` 的值（這台 4）；超過核心數不會更快（7.5：T=8 是 3.32x，T=4 是 3.89x）。

### 7.4.3 鎖抓太久 → 縮短臨界區（對照官方 section2-3）

題目長這樣：「程式結果正確，但兩條執行緒一起跑反而比一條慢。」

官方 `考試相關資訊/section2-3/critical-section/main.c` 的三種寫法和模板的對照：

| 官方 demo | 位置 | 做法 | 對應模板 |
|---|---|---|---|
| 1. no lock | `main.c:56-65` | 拆開寫 `v = counter; counter = v + 1;` | `w_racy`（`parallel_template.c:73-77`） |
| 2. lock, short hold | `main.c:68-77` | `work()` 在鎖外，鎖內只 `counter++` | `w_spin`（`:59-66`） |
| 3. lock, long hold | `main.c:80-89` | `work()` 也放進鎖內 → 兩條輪流跑 | 模板沒有這個版本 |

改法（把 3 改成 2）：

```c
// 改前（鎖內做計算）
pthread_spin_lock(&lock);
sink += work(i);
counter++;
pthread_spin_unlock(&lock);
// 改後（計算移到鎖外，鎖內只留共享變數）
sink += work(i);
pthread_spin_lock(&lock);
counter++;
pthread_spin_unlock(&lock);
```

（官方 demo 的 `sink` 也是兩條共用、沒保護；它只是防止 `work()` 被最佳化掉，不影響 counter 的正確性。）

再進一步（模板的 local 版）：鎖內只做一次，`local++` 在迴圈裡、最後 `lock; counter += local; unlock;`。

怎麼驗證：本章在暫存資料夾編官方 demo（不在 repo 裡產生 `bin/`）：

```sh
cc -O2 -Wall -Wextra -pthread -o cs <repo>/考試相關資訊/section2-3/critical-section/main.c && ./cs
```

成功的樣子（本章實測 3 次，4 CPUs）：

```text
expected counter = 40000   (4 CPUs available)
1. no lock            counter = 39980    LOST UPDATES     42.3 ms
2. lock, short hold   counter = 40000    ok       43.5 ms
3. lock, long hold    counter = 40000    ok       87.2 ms
（第 2、3 次：no lock 39891 / 39884；short 41.8 / 49.8 ms；long 86.0 / 86.0 ms）
```

為什麼官方 demo 的 short hold 幾乎不比 no lock 慢，模板的 mutex/spinlock 卻慢 10 倍以上：官方的 `work()` 每次 2000 次乘加（`main.c:38-41`），鎖的成本相對很小；模板的 `work()` 只有 8 輪 xorshift，鎖的成本變成主角。**鎖的代價要和臨界區外的計算量比**。

### 7.4.4 修 race condition

題目長這樣：「多執行緒加總，結果每次不一樣而且偏少。」

三種修法，由好到差：
1. **local**（最快）：照 `w_local`（`:45-50`），每條用區域變數，最後各寫一次 `part[id]`，`main` 加總。
2. **atomic**：`static _Atomic uint64_t g;` + `atomic_fetch_add_explicit(&g, v, memory_order_relaxed)`（`:67-72`）。正確，但 T=4 實測只有 0.18x。
3. **mutex / spinlock**：在 `g += v` 前後加鎖（`:51-66`）。正確，T=4 實測 0.13x / 0.03x。

怎麼驗證：`-fsanitize=thread` 跑一次，沒有 `WARNING: ThreadSanitizer: data race` 才算修好（7.3.3 的實測示範了有 race 時長什麼樣）。結果每次都一樣、和單執行緒相同。

### 7.4.5 每條執行緒寫自己的計數器，還是慢 → false sharing

題目長這樣：「每條執行緒寫 `count[tid]`，結果對，但加執行緒沒變快。」

改法（照 `padded_t`，`parallel_template.c:42`）：

```c
// 改前
static volatile uint64_t count[T_MAX];
// 改後：每格獨占一條 64B cache line
typedef struct { _Alignas(64) volatile uint64_t v; } padded_t;
static padded_t count[T_MAX];      // 使用處 count[tid] 改成 count[tid].v
```

更好的改法：迴圈裡用區域變數，最後才寫 `count[tid]`（local 版）。

怎麼驗證：`sizeof(padded_t)` 要是 64；T=4 實測 false-share 2.75x → padded 3.79x。

### 7.4.6 pipeline 傳封包 struct

題目長這樣：「一條執行緒讀資料封包（每包 64 bytes），另一條算 hash。」

改哪些行（本章實測可編譯、3 種都「結果正確」）：

```c
// :23  先用小一點的量測試
#define N_ITEMS (1u << 16)
// :25
typedef struct { uint8_t data[64]; uint16_t len; } item_t;
// :31-34  produce：填一包
static inline item_t produce(uint32_t *st) {
    item_t it; it.len = 64;
    for (int k = 0; k < 64; k++) { *st ^= *st << 13; *st ^= *st >> 17; *st ^= *st << 5; it.data[k] = (uint8_t)*st; }
    return it;
}
// :35-39  compute：逐 byte 混進去
static inline uint64_t compute(uint64_t acc, item_t x) {
    uint32_t h = (uint32_t)acc;                      /* FNV-1a 風格：逐 byte 混進去 */
    for (int k = 0; k < x.len; k++) { h ^= x.data[k]; h *= 16777619u; }
    return acc + h;
}
```

成功的樣子（本章實測）：

```text
傳送 65536 筆，佇列容量 1024（每種 3 次取最快）
  serial 單執行緒 收一筆算一筆      7.561 ms
  A mutex+condvar                  35.861 ms
      → 結果正確  加速 0.21x
  B SPSC 無鎖                    17.080 ms
      → 結果正確  加速 0.44x
  C SPSC 無鎖+批次              7.651 ms
      → 結果正確  加速 0.99x
結果：全部正確
```

這個例子 pipeline 沒有變快：每筆的收和算都很輕（64 bytes），搬一筆 66 bytes 的成本和計算差不多。**pipeline 只有在「收」和「算」都夠重、而且差不多重時才有用**（模板預設 `PROD_COST = COMP_COST = 64` 就是這種情況，C 版 1.56x）。

### 7.4.7 用 `bench.h` 比較兩個寫法

```c
#include "bench.h"                 // 第一行
#include <stdlib.h>
static uint32_t buf[1 << 20];
static uint64_t sum_a(void) { uint64_t s = 0; for (int i = 0; i < (1 << 20); i++) s += buf[i] % 256; return s; }
static uint64_t sum_b(void) { uint64_t s = 0; for (int i = 0; i < (1 << 20); i++) s += buf[i] & 255; return s; }
int main(void) {
    for (int i = 0; i < (1 << 20); i++) buf[i] = (uint32_t)rand();
    uint64_t r;
    BENCH("% 256", 5, { r = sum_a(); do_not_optimize(r); });  uint64_t base = bench_last_ns;
    BENCH("& 255", 5, { r = sum_b(); do_not_optimize(r); });
    printf("加速 %.2fx\n", (double)base / bench_last_ns);
    return 0;
}
```

本章實測（gcc 13.3 `-O2 -Wall -Wextra -std=c11`，0 警告）：

```text
  % 256                             0.155 ms
  & 255                             0.146 ms
加速 1.06x
```

對無號數，編譯器自己就會把 `% 256` 換成 `& 255`，兩者幾乎一樣快。README 清單第 7 條（強度削減）在這種情況下不用手動做；量了才知道，這正是「先量再改」的意義。

### 7.4.8 搬到 Pico 2 雙核心

題目長這樣：「Pico 上 core0 從 USB 收資料，core1 計算，要比單核快。」

| 電腦端（本章） | Pico 端（見第 3 章 `pico/app_multicore.c`） | 說明 |
|---|---|---|
| `pthread_create(consumer)` | `multicore_launch_core1(core1_main)` | Pico 只有 2 顆核心，「執行緒」就是 core1 |
| A 版 mutex + condvar | `queue_t`（`queue_add_blocking` / `queue_remove_blocking`） | SDK 的 `queue_t` 內部用 `spin_lock_blocking` 保護（`pico_util/queue.c:46`），最省事 |
| B / C 版 SPSC（C11 atomics） | 同樣的程式碼可以直接用 | 本章實測：M33 編成 `lda` / `stl`，Hazard3 編成 `fence` / `amoswap.w`（7.3.4） |
| `sched_yield()` | 沒有作業系統，改成 `tight_loop_contents()` 或 `__wfe()` / `__sev()` | ⚠️未驗證（沒在板子上跑） |
| `pthread_spin_lock` | `spin_lock_blocking()`（會關中斷）、`critical_section_enter_blocking()` | RP2350 上 SDK 預設用**軟體** spinlock（`hardware/sync/spin_lock.h:13-16`：`PICO_USE_SW_SPIN_LOCKS` 在 RP2350 預設 1，「due to errata」）；M33 用 `ldaexb/strexb`、Hazard3 用 `amoor.w.aq`（同檔 `:113-148`） |
| `multicore_fifo_push_blocking` | 硬體 FIFO，每次一個 32 位元字 | 適合傳命令或指標，不適合大量資料 |
| false sharing（64B cache line） | ⚠️未驗證：RP2350 的 SRAM 直接接在匯流排上，核心本身沒有資料快取（XIP 快取只給 flash），所以不會有「cache line 來回搬」；但兩核同時存取同一塊 SRAM 會互相等待 | 沒有查 datasheet 原文確認 |
| 鎖要短 | 一樣，而且 `spin_lock_blocking` 拿鎖期間**關中斷**，抓太久會讓 USB 收資料漏掉 | 見第 3 章 |

做法：
1. 先用電腦端模板驗證「收」和「算」的程式正確、pipeline 有沒有加速（收和算要差不多重）。
2. 搬到 Pico：producer 放 core0（USB 在 core0 處理），consumer 放 core1；佇列先用 `queue_t`，要更快再換 SPSC + 批次。
3. core1 的堆疊預設只有 2 KiB（`pico/app_multicore.c:96` 註解），`tmp[BATCH]` 或大的 `item_t` 不要放在 core1 的區域變數。

## 7.5 效能：量測方法與實測數字

量測方法：每支程式內建 `BENCH`（每種寫法跑 3 次取最快）；加速倍數 = serial 時間 ÷ 該寫法時間。

環境：Intel Xeon Processor @ 2.30GHz、4 vCPU（1 thread per core）、16 GB RAM、cache line 64 B、Linux 6.18、gcc 13.3 `-O2 -std=c11 -pthread`。**這個容器同時有其他工作在跑**（量測時 load average 1.06～3.90），所以同一個寫法每次量的結果會變。下面列出其中 5 次（從最空閒到最忙），不做平均；其他 6 次 T=4 的 local 落在 1.25x～1.94x，在表的範圍內。

確認 4 核是真的：4 個單執行緒程式同時跑的牆上時間（1.663 s）和只跑 1 個（1.692 s）一樣（本章 `spin1.c` 實測）。

**parallel_template，T = 4，5 次（ms，括號是加速）**

| 寫法 | 第 1 次（load 1.06） | 第 2 次（load 1.33） | 第 3 次（load 1.94） | 第 4 次（load 3.45） | 第 5 次（load 3.90） |
|---|---|---|---|---|---|
| serial | 53.0 | 44.8 | 45.1 | 45.9 | 44.9 |
| local | 13.6（3.89x） | 22.2（2.01x） | 27.8（1.62x） | 34.9（1.32x） | 36.3（1.24x） |
| mutex | 398.7（0.13x） | 180.4（0.25x） | 194.4（0.23x） | 164.7（0.28x） | 164.6（0.27x） |
| spinlock | 1681.2（0.03x） | 356.2（0.13x） | 491.4（0.09x） | 324.9（0.14x） | 522.5（0.09x） |
| atomic | 301.2（0.18x） | 107.1（0.42x） | 111.6（0.40x） | 107.8（0.43x） | 145.4（0.31x） |
| racy（答案錯） | 19.6（2.70x） | 33.7（1.33x） | 49.5（0.91x） | 42.1（1.09x） | 34.1（1.32x） |
| false-share | 19.3（2.75x） | 41.3（1.09x） | 45.7（0.99x） | 46.7（0.98x） | 38.7（1.16x） |
| padded | 14.0（3.79x） | 47.4（0.95x） | 35.2（1.28x） | 30.1（1.53x） | 32.4（1.39x） |

讀法：
- 機器最空閒時（第 1 次）最接近真正的差異：local 3.89x、padded 3.79x、false-share 2.75x、racy 2.70x。
- 機器越忙，local / padded 越慢（拿不到 4 個完整的核心）；但 mutex / spinlock / atomic 在空閒時反而**更慢**：4 條執行緒真的同時在搶，衝突更多。
- 不管哪一次，mutex / spinlock / atomic 都比單執行緒慢。

**parallel_template，不同執行緒數（load 1.28～1.34，各 1 次）**

| 寫法 | T=1 | T=2 | T=4（上表第 1 次） | T=8 |
|---|---|---|---|---|
| local | 0.96x | 1.90x | 3.89x | 3.32x |
| mutex | 0.36x | 0.12x | 0.13x | 0.11x |
| spinlock | 0.74x | 0.07x | 0.03x | 0.01x（5021.8 ms） |
| atomic | 0.81x | 0.18x | 0.18x | 0.18x |
| racy | 0.82x（T=1 答案正確） | 1.32x（錯） | 2.70x（錯） | 2.03x（錯） |
| false-share | 1.02x | 1.37x | 2.75x | 1.95x |
| padded | 0.96x | 1.69x | 3.79x | 2.91x |

- T=1 時 mutex 0.36x：**沒有人搶**，每個元素 lock/unlock 一次的固定成本就讓它慢 3 倍。
- T=8 > 4 核：local 沒有更快；spinlock 慘到 5 秒（拿著鎖的執行緒被暫停，其他人白繞）。

**編譯選項（T=4，load 1.68）**：`-O3 -march=native` 時 serial 15.463 ms、local 5.723 ms（2.70x）；緊接著跑的 `-O2` 版 `./par 1` serial 46.940 ms。光換編譯選項，單執行緒就快 3.04 倍（46.9 → 15.5 ms），和 README `:44`「先把單執行緒版本優化好，再談平行化」一致。

**pipeline_template（ms，括號是加速）**

| 寫法 | 第 1 次（load 1.51） | 第 2 次（load 2.52） | 第 3 次（load 2.63） | TSan（-O1，load 不明） |
|---|---|---|---|---|
| serial | 200.2 | 202.4 | 199.4 | 229.6 |
| A mutex+condvar | 292.3（0.68x） | 526.5（0.38x） | 641.1（0.31x） | 787.5（0.29x） |
| B SPSC | 235.4（0.85x） | 227.9（0.89x） | 246.8（0.81x） | 603.2（0.38x） |
| C SPSC + 批次 | 128.5（1.56x） | 128.1（1.58x） | 128.5（1.55x） | 358.3（0.64x） |

- C 版三次都在 1.55x～1.58x，最穩定；B 版在這台比單執行緒慢（每筆一次 cache line 交接，成本和 64 輪計算差不多）。理論上限是 2x（兩邊各做一半）。

**官方 section2-3 critical-section（3 次）**：no lock 39980 / 39891 / 39884（全部 LOST UPDATES）、42.3～44.9 ms；short hold 全部 40000、41.8～49.8 ms；long hold 全部 40000、86.0～87.2 ms（是同一次 short 的 1.73～2.06 倍，就是「退回單執行緒」）。

## 7.6 限制、已知問題、沒驗證的地方

1. **數字會因機器而變**：本章數字是在一台和其他工作共用的 4 vCPU 容器上量的，同一寫法 T=4 的 local 從 1.24x 到 3.89x 都出現過。README 的數字是另一台 6 核機器。比較時要在同一台、同一時間、輪流多跑幾次。
2. **`perf` 沒有安裝**，`perf stat` / `perf record` 的指令（README `:63-65`）沒有實測；`perf_event_paranoid` 這台是 2（README `:69` 寫的「這台電腦目前是 4」是作者的機器）。
3. `gprof` 不計算其他執行緒裡的呼叫次數；`callgrind` 對很短的程式主要量到動態連結器（7.3.1 實測）。
4. `parallel_template.c:94` `run()` 沒有檢查 `pthread_create` 的回傳值；建立失敗時 `pthread_join` 一個沒初始化的 `pthread_t` 是未定義行為。正常情況（T ≤ 64）不會發生，沒有改程式。
5. `parallel_template.c:40` `g_racy` 是 `volatile`：這讓它每次真的讀寫記憶體，比「真正的錯誤程式」更慢一點，也讓 lost update 更明顯。`volatile` 不是同步工具。
6. `pipeline_template.c` 的 B / C 版在空或滿時用 `sched_yield()` 忙等，CPU 會一直 100%。在 Pico 上沒有 `sched_yield`，要換掉（7.4.8）。
7. `pipeline_template.c` 假設事先知道總筆數（`:131`）。
8. `bench.h` 的 `BENCH` 巨集不能接受不在小括號內的逗號（7.3.2 實測錯誤訊息）。
9. **對 Pico 的對照**（7.4.8）中，「RP2350 核心沒有資料快取」「`tight_loop_contents()` / `__wfe()` 取代 `sched_yield()`」都沒有在板子上或 datasheet 原文確認 ⚠️未驗證；SDK 的軟體 spinlock 與 `queue_t` 用 spinlock 是對照 pico-sdk 2.2.0 原始碼確認的。
10. 本章沒有發現 `linux-perf/` 的程式錯誤：結果全部正確，`-Wall -Wextra` 0 警告，TSan 只報預期的 racy。

## 7.7 一頁速查表

指令（在 `預製程式碼/linux-perf/`）：

| 目的 | 指令 |
|---|---|
| 平行模板 | `gcc -O2 -Wall -Wextra -std=c11 -pthread parallel_template.c -o /tmp/par && /tmp/par 4` |
| pipeline 模板 | `gcc -O2 -Wall -Wextra -std=c11 -pthread pipeline_template.c -o /tmp/pipe && /tmp/pipe` |
| 看核心數 | `nproc` |
| 牆上 vs CPU 時間 | `time ./prog`（user+sys > real = 有平行） |
| 找 data race | `gcc -O1 -g -fsanitize=thread -std=c11 -pthread x.c -o x && ./x` |
| 找最花時間的函式 | `gcc -O2 -g -pg x.c -o x && ./x && gprof -b ./x gmon.out \| head -30` |
| 逐行指令數 | `valgrind --tool=callgrind --callgrind-out-file=cg.out ./x && callgrind_annotate cg.out` |
| 更快的編譯選項 | `-O3 -march=native`（本章 serial 46.9 → 15.5 ms） |

函式簽名：

| 名稱 | 簽名 / 用法 |
|---|---|
| 計時 | `uint64_t now_ns(void)` |
| 量一段程式 | `BENCH("名稱", 次數, { 程式; do_not_optimize(結果); });` → `bench_last_ns` |
| 開執行緒 | `pthread_create(&th, NULL, fn, arg); pthread_join(th, NULL);`，`void *fn(void *arg)` |
| 原子加 | `atomic_fetch_add_explicit(&g, v, memory_order_relaxed)` |
| SPSC | `spsc_push(v)` / `spsc_pop(&v)`（回 bool）、`spsc_push_n(src, n)` / `spsc_pop_n(dst, max)`（回數量） |
| 避免 false sharing | `typedef struct { _Alignas(64) uint64_t v; } padded_t;` |

常數：

| 名稱 | 值 | 位置 |
|---|---|---|
| `N` | `1u << 23` | `parallel_template.c:22` |
| `T_MAX` | 64 | `parallel_template.c:23` |
| `CAP` | 1024（2 的次方） | `pipeline_template.c:22` |
| `N_ITEMS` | `1u << 20` | `pipeline_template.c:23` |
| `BATCH` | 64 | `pipeline_template.c:24` |
| cache line | 64 bytes | `getconf LEVEL1_DCACHE_LINESIZE` |

常見錯誤：

| 症狀 | 一句話修法 |
|---|---|
| 結果每次不同、偏少 | local 版或 atomic |
| 加鎖後比單執行緒慢 | 鎖移出熱迴圈，只在合併時用 |
| 各寫各的格子還是慢 | `_Alignas(64)` |
| `CLOCK_MONOTONIC undeclared` | `bench.h` 放第一個 include |
| `BENCH passed 4 arguments` | code 裡的逗號拆掉 |
| 量出 0 ms | `do_not_optimize` |
| pipeline 沒變快 | 收和算要都夠重；用批次 |
| T 開超過核心數 | T = `nproc` |
