# 規格卡：linux-perf/（計時、pthread 平行化、生產者 / 消費者 pipeline）
> 用法：一次只複製一張卡（兩條 `---` 之間），貼進對話；模型要看程式時，照卡片最後一行請操作者貼指定行號。每張 ≤ 1200 字元。
> 來源：`預製程式碼/linux-perf/` 4 個檔、`預製程式碼/說明書/07-linux-perf.md`｜最後更新 2026-11-13

---

【規格卡｜PERF 1/5｜總覽、bench.h、編譯執行】
以下是正確的參考資料（預製程式碼 2026-11-13 版）。和你的記憶不同時，以這張為準。
| 檔案 | 行數 | 做什麼 |
|---|---|---|
| `bench.h` | 55 | 計時工具，**必須是第一個 `#include`** |
| `parallel_template.c` | 136 | 切 T 塊各算各的再合併；8 種寫法比較 |
| `pipeline_template.c` | 169 | 一個收、一個算：mutex 佇列、SPSC、SPSC+批次 |
| `README.md` | 81 | 實測、10 條優化清單 |
bench.h API：
| 名稱 | 行 | 做什麼 |
|---|---|---|
| `now_ns()` | 23-27 | `CLOCK_MONOTONIC` 奈秒，只拿來算差值 |
| `do_not_optimize(x)` | 30-31 | 加進 volatile 變數，防止 `-O2` 刪掉結果 |
| `clobber_memory()` | 34-38 | 記憶體屏障，BENCH 內已呼叫 |
| `BENCH(name,reps,code)` | 42-53 | 跑 reps 次取**最快**，印 `名稱 x.xxx ms`，存 `bench_last_ns`（ns） |
用法：`BENCH("f", 5, { r = f(a, n); do_not_optimize(r); });`；加速 = `(double)base / bench_last_ns`。
編譯執行（在 `linux-perf/`）：
```sh
gcc -O2 -Wall -Wextra -std=c11 -pthread parallel_template.c -o /tmp/par && /tmp/par 4
gcc -O2 -Wall -Wextra -std=c11 -pthread pipeline_template.c -o /tmp/pipe && /tmp/pipe
```
- `par` 參數 = 執行緒數（1～64，其他用 4）；整支約 11 秒，不是當機。
- 驗證：0 警告；TSan 只報 parallel 的 racy（`:75`）。
- 陷阱：bench.h 不在第一行 → `'CLOCK_MONOTONIC' undeclared` → 移到第一行。code 裡有 `int a = 1, b = 2;` → `macro "BENCH" passed 4 arguments` → 拆成兩行。
要看程式：請操作者貼「cat -n bench.h | sed -n 13,55p」

---

【規格卡｜PERF 2/5｜parallel_template.c：8 種寫法、false sharing】
以下是正確的參考資料（預製程式碼 2026-11-13 版）。和你的記憶不同時，以這張為準。
工作：`work(x)` 加總。`run(fn)`（`:90-97`）開 T 條，第 t 條算 `[N*t/T, N*(t+1)/T)`。
| 寫法 | 行 | 熱迴圈做什麼 | 快 / 慢（T=4） |
|---|---|---|---|
| serial | 117-118 | 同一個 `w_local` 跑全部 | 基準 1x |
| local ★ | 45-50 | 區域變數 `s +=`，最後寫 `part[id]` 一次 | 3.89x 最快 |
| mutex | 51-58 | 每元素 lock、`g_sum += v` | 0.13x |
| spinlock | 59-66 | 每元素 spin_lock | 0.03x |
| atomic | 67-72 | 每元素 `atomic_fetch_add` | 0.18x |
| racy ✗ | 73-77 | 不加鎖 `g_racy +=` | **答案錯**（lost update） |
| false-share | 78-82 | `slot_packed[id] +=`，格子相鄰 | 2.75x |
| padded | 83-87 | `slot_padded[id].v +=`，每格 64 B | 3.79x |
- false sharing：64 B cache line 裝 8 個 `uint64_t`，多核寫同一條 → line 來回搬。修法：`typedef struct { _Alignas(64) volatile uint64_t v; } padded_t;`（`:42`，sizeof = 64），或用區域變數。
- 最後一行成功：`結果：全部正確（racy 錯是預期的）`，回傳 0。
`TODO(改這裡)`：
| 行 | 現在 | 改法 |
|---|---|---|
| `:22` | `N (1u << 23)` | 題目的資料量；從檔案讀改 `malloc` |
| `:27`（`:28-31` `work()`） | 8 輪 xorshift | 換成題目的計算；不是加總時 `s +=` 和 `sum_parts()`（`:99`）一起改 |
- 只交 local 版：留 serial + local（`:117-120`），刪 `:121-131` 和用不到的函式。T ≤ `nproc`。
要看程式：請操作者貼「cat -n parallel_template.c | sed -n 22,99p」

---

【規格卡｜PERF 3/5｜pipeline_template.c：SPSC ring buffer 規則】
以下是正確的參考資料（預製程式碼 2026-11-13 版）。和你的記憶不同時，以這張為準。
常數：`CAP 1024u`（`:22`，必須 2 的次方）、`N_ITEMS 1u<<20`（`:23`）、`BATCH 64u`（`:24`）、`item_t` = `uint32_t`（`:25`）、`PROD_COST`/`COMP_COST` 64（`:29-30`）。
| 名稱 | 行 | 做什麼 |
|---|---|---|
| A `mq_push/mq_pop` | 42-62 | mutex + condvar，每筆上鎖 |
| B `spsc_push/spsc_pop` | 65-86 | 無鎖，回 bool（滿 / 空回 false） |
| C `spsc_push_n/spsc_pop_n` | 88-103 | 一次多筆，回筆數；1 次 release |
| `producer/consumer` | 109-143 | `mode` 0/1/2 = A/B/C；空或滿 `sched_yield()` |
SPSC 規則：
- 只能 1 個 producer、1 個 consumer。`head` 只有 producer 寫，`tail` 只有 consumer 寫。
- head、tail 只增不歸零；索引 = 計數 & (CAP-1)。空 `head == tail`；滿 `head - tail == CAP`。
- push：讀自己 head（relaxed）→ 讀 tail（acquire，`:73`）→ 寫 `buf[h & (CAP-1)]` → `store(head, h+1, release)`（`:76`）。
- pop：讀自己 tail（relaxed）→ 讀 head（acquire，`:81`）→ 讀 buf → `store(tail, t+1, release)`（`:84`）。
- 改成 relaxed 或 `volatile` → 偶爾讀到舊資料 → 保持 acquire/release。
- `head`、`tail` 各 `_Alignas(64)`（`:67-68`）放不同 cache line。
- 陷阱：CAP 改 1000 → `&(CAP-1)` 不等於 `%CAP` → 資料錯。兩個 producer 用 SPSC → 錯亂 → 改 A 版或每個 producer 一個佇列。
要看程式：請操作者貼「cat -n pipeline_template.c | sed -n 64,103p」

---

【規格卡｜PERF 4/5｜pipeline 改法、實測數字】
以下是正確的參考資料（預製程式碼 2026-11-13 版）。和你的記憶不同時，以這張為準。
`TODO(改這裡)`（`pipeline_template.c`）：
| 行 | 現在 | 改法 |
|---|---|---|
| `:23` | `N_ITEMS (1u << 20)` | 題目筆數；不知道總數 → consumer 改成收到結束標記就停（`:131`） |
| `:25` | `typedef uint32_t item_t;` | 封包 struct，例 `{uint8_t data[64]; uint16_t len;}`；同時改 `compute()`（`:36` 的 `^` 對 struct 編不過） |
| `:27`（`:29-39`） | 模擬的 `produce`/`compute` | 換成真的收 / 算；compute 結果和順序有關，可檢查掉資料或亂序 |
- `CAP`、`BATCH` 也可調（CAP 維持 2 的次方；`tmp[BATCH]` 在堆疊上）。
實測（4 vCPU Xeon、gcc 13.3 `-O2`；機器有別的負載，數字會變）：
```text
serial 單執行緒 收一筆算一筆    200.226 ms
A mutex+condvar   292.335 ms  加速 0.68x
B SPSC 無鎖       235.446 ms  加速 0.85x
C SPSC 無鎖+批次  128.479 ms  加速 1.56x
結果：全部正確
```
- C 版三次 1.55x～1.58x 最穩；理論上限 2x。README（Ryzen 6 核）：A 0.92x、B 1.50x、C 1.70x。
- parallel（T=4，最空閒那次）：local 3.89x、padded 3.79x、false-share 2.75x、mutex 0.13x。T=8 > 4 核：local 3.32x，spinlock 5 秒。
- `-O3 -march=native`：serial 46.9 → 15.5 ms。先優化單執行緒，再平行。
- pipeline 只有在「收」和「算」都夠重、差不多重時才有用：64 B struct 版 C 只有 0.99x。
- 驗證成功的樣子：每項「結果正確」，最後 `結果：全部正確`、回傳 0。
要看程式：請操作者貼「cat -n pipeline_template.c | sed -n 22,39p」

---

【規格卡｜PERF 5/5｜陷阱、驗證、對應 Pico 2 雙核心】
以下是正確的參考資料（預製程式碼 2026-11-13 版）。和你的記憶不同時，以這張為準。
| 症狀 | 原因 | 修法 |
|---|---|---|
| 結果每次不同、偏小 | 共享變數沒保護 | local 版或 atomic |
| 加鎖後比單執行緒慢 | 每元素 lock | 鎖只在合併時用一次 |
| 各寫各的格子還是慢 | false sharing | `_Alignas(64)` |
| `undefined reference to 'pthread_create'` | 沒 `-pthread` | 加 `-pthread` |
| 程式卡住 | consumer 等的筆數比送的多 | 兩邊 `N_ITEMS` 一致 |
| CPU 100% | `sched_yield()` 忙等 | 正常；要省電用 A 版 |
- 找 race：`gcc -O1 -g -fsanitize=thread -std=c11 -pthread x.c -o x && ./x`，沒有 `WARNING: ThreadSanitizer: data race` 才算修好。
Pico 2 對照（以下沒在板子上驗證）：
| 電腦端 | Pico 端 |
|---|---|
| `pthread_create(consumer)` | `multicore_launch_core1(core1_main)`，只有 2 核 |
| A 版 mutex + condvar | `queue_t`（`queue_add_blocking`/`queue_remove_blocking`） |
| B / C 版 SPSC（C11 atomics） | 同一份可用（M33 → `lda`/`stl`；Hazard3 → `fence`） |
| `sched_yield()` | `tight_loop_contents()` 或 `__wfe()`/`__sev()` |
| `pthread_spin_lock` | `spin_lock_blocking()`（關中斷，太久漏 USB） |
| 小量命令 | `multicore_fifo_push_blocking`（每次 32 位元） |
- 做法：producer 放 core0（USB 在 core0），consumer 放 core1；先 `queue_t`，要更快換 SPSC+批次。
- core1 堆疊預設 2 KiB：大的 `item_t`、`tmp[BATCH]` 不要放 core1 區域變數。
- RP2350 核心沒有資料快取，false sharing 情況不同（未驗證）。
要看程式：見各列的行號
