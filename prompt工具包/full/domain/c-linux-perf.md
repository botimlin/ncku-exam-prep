# C / Linux 程式效能優化深入（x86-64 / aarch64 主機或容器）

> 用途：**備援包**。考前 demo 沒有直接提到「在 Linux 主機 / 容器上把一支 C 程式變快」，但考試目標二是「優化特定程式與整體系統效能」，若題目給的是跑在容器裡的 C 程式（judge 量執行時間），用本檔。通用流程（量測 → 假設 → 改一處 → 驗證、Amdahl、實驗紀錄表）見 `03-optimize.md`，本檔只補 Linux / GCC / CPU 層級的細節，不重複。多執行緒、鎖、false sharing 見 `domain/multicore-sync.md`；RISC-V / Hazard3 組語層級見 `domain/riscv-hazard3.md`。
> 適用版本：GCC 12 以上（demo 容器 `ros:jazzy-ros-core` = Ubuntu 24.04，內建 GCC 13；本檔實測用 GCC 13.3）、glibc、Linux 5.x 以上、cgroup v2。x86-64 與 aarch64 的差異會標出。
> 來源（實際查閱過）：
> - GCC 手冊 https://gcc.gnu.org/onlinedocs/gcc/ ：Optimize-Options、Developer-Options（`-fopt-info`）、Instrumentation-Options（`-fprofile-generate`）、Code-Gen-Options（`-fno-plt`）、x86-Options（`-march=native`）、Common-Attributes（`always_inline`、`aligned`、`hot/cold`、`flatten`、`target_clones`）、Other-Builtins（`__builtin_expect`、`__builtin_prefetch`、`__builtin_assume_aligned`）、Vector-Extensions、Loop-Specific-Pragmas（`#pragma GCC unroll/ivdep`）、x86-Built-in-Functions（`__builtin_cpu_supports`）
> - man7.org：perf-stat(1)、perf-record(1)、perf-report(1)、perf-annotate(1)、perf_event_open(2)、time(1)、gprof(1)、setvbuf(3)、mmap(2)、madvise(2)、sched_setaffinity(2)、taskset(1)、aligned_alloc(3)、posix_memalign(3)、nproc(1)
> - Linux kernel docs：admin-guide/cgroup-v2（`cpu.max`、`cpu.stat`）、admin-guide/mm/transhuge（THP）
> - GNU coreutils NEWS（nproc 自 9.8 起考慮 cgroup v2 quota）
> - Valgrind 手冊：cg-manual（Cachegrind）、cl-manual（Callgrind）
> - Docker docs：engine/security/seccomp（預設 profile 擋 `perf_event_open`）
> - Agner Fog：instruction_tables.pdf、microarchitecture.pdf（延遲數量級）
> 最後更新：2026-11
>
> 給模型的說明：所有「延遲 / 加速倍數」都是**數量級參考**，依 CPU、編譯器版本、資料大小差很多，一律以考場實測為準。標「本機實測」的數字來自 AMD Ryzen 5 5600（Zen 3）+ GCC 13.3 + Linux，僅示範趨勢。標 ⚠️未驗證 的是沒有一手來源的推論。若考場文件與本檔衝突，**以考場文件為準**。

---

## 0. 三十秒重點

1. **先確定 judge 怎麼編譯**（看 Makefile / CMakeLists / `.gitlab-ci.yml` / 題目文件）。如果旗標固定，你只能改原始碼；改本機旗標量到的加速在 judge 上不存在。
2. **熱點順序**：演算法 > 記憶體存取模式（cache）> I/O 方式 > 分支 / 相依鏈 / 向量化 > 微調旗標。
3. **I/O 常是隱形大頭**：`scanf/printf` 改成 `fread` 大區塊 + 自寫解析 + 輸出緩衝一次 `fwrite`，本機實測約 4 倍。
4. **cache 友善**：最內層迴圈要沿著記憶體連續方向走（C 是 row-major：`a[i][j]` 的 j 連續）。矩陣乘法改迴圈順序 ijk → ikj，本機實測約 11 倍。
5. **不要信直覺**：GCC `-O2` 常已經做了 if-conversion（cmov）、除以常數變乘法、迴圈不變量外提。先看組語（`gcc -O2 -S`）或量測，再手改。
6. **浮點結果不能變**：`-ffast-math` / `-Ofast` / 重排加法 / FMA 收縮都可能改變輸出位元，exact-output judge 會判錯。
7. **工具可能不能用**：`perf` 在 Ubuntu 預設 `perf_event_paranoid=4` 且 Docker 預設 seccomp 擋 `perf_event_open`；`valgrind` 多半沒裝。不能安裝軟體 → 用 `clock_gettime` 手動分段計時。
8. **容器 CPU 數**：`nproc` 不一定等於 cgroup 配額；看 `/sys/fs/cgroup/cpu.max`。

---

## 1. 環境偵查（開工前 2 分鐘）

```bash
uname -m                         # x86_64 或 aarch64
gcc --version | head -1          # 版本影響預設行為（GCC 12+ 的 -O2 才會向量化）
cc -v 2>&1 | grep -i target      # 目標三元組
lscpu | head -30                 # CPU 型號、cache 大小、旗標（avx2 / neon 等）
nproc; nproc --all               # 可用 / 全部 CPU 數
cat /sys/fs/cgroup/cpu.max 2>/dev/null     # 容器 CPU 配額（cgroup v2）
getconf LEVEL1_DCACHE_LINESIZE             # cache line 大小（可能印 0 → 改看下一行）
cat /sys/devices/system/cpu/cpu0/cache/index0/coherency_line_size
cat /proc/sys/kernel/perf_event_paranoid   # >=2 代表一般使用者用 perf 會受限
for t in perf valgrind gprof gdb strace ltrace objdump kcachegrind callgrind_annotate cg_annotate; do
  printf '%-20s %s\n' "$t" "$(command -v $t || echo '-')"; done
ls /usr/bin/time && /usr/bin/time --version   # bash 內建 time 不支援 -v
```

| 工具 | 用途 | 沒有 / 不能用時的替代 |
|---|---|---|
| `perf stat` | cycles、instructions、IPC、cache/branch misses | 程式內 `clock_gettime` 分段計時；改資料大小觀察時間是否跳升（cache 效應） |
| `perf record/report/annotate` | 找熱點函式 / 熱點指令 | `gprof`（`-pg`）；手動分段計時；`gdb` 隨機中斷幾次看 backtrace（窮人版取樣） |
| `gprof` | 函式層級時間 + 呼叫次數 | 手動計數器 + 計時 |
| `valgrind --tool=callgrind/cachegrind` | 精確指令數、cache 模擬 | 無；改用分段計時與縮小輸入 |
| `/usr/bin/time -v` | 最大 RSS、page faults、context switches | `getrusage(RUSAGE_SELF, &ru)` 在程式內讀 |
| `objdump -d` / `gcc -S` | 看編譯器產出 | 一定有（binutils 隨 gcc） |

**規則**：不安裝任何軟體（考試規定）。`which` 找不到就用替代方案，不要浪費時間。

---

## 2. 量測

### 2.1 計時 harness（暖機 + 多次 + 取最小值 / 中位數）

```c
#define _POSIX_C_SOURCE 200809L
#include <stdio.h>
#include <stdlib.h>
#include <time.h>

static inline double now_ns(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);          /* 不受設定系統時間（時間跳動）影響 */
    return (double)ts.tv_sec * 1e9 + (double)ts.tv_nsec;
}

/* 防止編譯器把「結果沒用到」的計算刪掉 */
static volatile long long g_sink;
#define KEEP(x) (g_sink = (long long)(x))
/* 或：強迫值存在、且視為記憶體可能被讀寫（GCC inline asm，x86-64 / aarch64 皆可） */
#define BARRIER_VAL(x) __asm__ volatile("" : : "r"(x) : "memory")

static int cmp_d(const void *a, const void *b) {
    double x = *(const double *)a, y = *(const double *)b;
    return (x > y) - (x < y);
}

#define REPS 11
void bench(const char *name, void (*fn)(void)) {
    double t[REPS];
    fn();                                         /* 暖機：載入 cache、觸發 page fault */
    for (int r = 0; r < REPS; r++) {
        double t0 = now_ns();
        fn();
        t[r] = now_ns() - t0;
    }
    qsort(t, REPS, sizeof t[0], cmp_d);
    fprintf(stderr, "%-12s min %.3f ms  median %.3f ms\n",
            name, t[0] / 1e6, t[REPS / 2] / 1e6);   /* 用 stderr，不污染評分輸出 */
}
```

| 時鐘 | 量什麼 | 何時用 |
|---|---|---|
| `CLOCK_MONOTONIC` | 牆鐘時間（單調遞增） | 預設選擇；judge 多半量牆鐘或 CPU 時間 |
| `CLOCK_MONOTONIC_RAW` | 不受 NTP 調頻影響的單調時鐘（Linux 專有） | 很短的區段、想排除調頻 |
| `CLOCK_PROCESS_CPUTIME_ID` | 本行程所有執行緒用掉的 CPU 時間 | 想排除等待 I/O / 被排程走的時間 |
| `CLOCK_THREAD_CPUTIME_ID` | 本執行緒 CPU 時間 | 多執行緒分析 |

- `clock_gettime` 在 Linux 上通常走 vDSO，不進核心；本機實測約 20 ns / 次。太短的區段要重複 N 次再除。
- **min** 代表「沒被干擾時」的能力，適合比較兩版程式；**median** 代表一般情況。兩者差很多 → 環境很吵（背景程式、調頻、別的容器）。
- 改一處就跑同一組輸入、同一組旗標；記錄在 `03-optimize.md` 的實驗紀錄表。
- 量「整支程式」：`for i in 1 2 3 4 5; do /usr/bin/time -f "%e s %M KB" ./prog < in.txt > /dev/null; done`。注意 `> /dev/null` 與寫到檔案 / 管線的 I/O 成本不同，要和 judge 的方式一致。

### 2.2 `/usr/bin/time -v`（GNU time，要用完整路徑）

| `-v` 輸出欄位 | 格式碼 | 意義 / 看到什麼代表什麼 |
|---|---|---|
| Elapsed (wall clock) time | `%e` / `%E` | 牆鐘時間 |
| User time / System time | `%U` / `%S` | 使用者 / 核心態 CPU 秒數。`%S` 很大 → syscall 或 page fault 太多 |
| Percent of CPU | `%P` | (U+S)/E。遠低於 100% → 在等 I/O；遠高於 100% → 多執行緒 |
| Maximum resident set size | `%M` | 最大記憶體（KB）。超過題目限制會被殺 |
| Major / Minor page faults | `%F` / `%R` | Minor 很多 → 大量新配置記憶體首次觸碰 |
| Voluntary / Involuntary context switches | `%w` / `%c` | voluntary 多 → 常阻塞（I/O、鎖）；involuntary 多 → 時間片用完、CPU 被搶 |

程式內可用 `getrusage(RUSAGE_SELF, &ru)` 讀同類資料（`ru_maxrss`、`ru_minflt`、`ru_nvcsw`、`ru_nivcsw`）。

### 2.3 `perf stat`（硬體計數器）

```bash
perf stat ./prog < in.txt > /dev/null
perf stat -e cycles,instructions,cache-references,cache-misses,branches,branch-misses ./prog
perf stat -r 5 ./prog          # 重複 5 次，印平均與標準差
perf stat -d ./prog            # 加 L1 / LLC 資料快取事件；-d -d 加 TLB
perf list                      # 這台機器支援哪些事件
```

| 指標 | 怎麼讀 | 大約門檻（⚠️經驗值，非官方） |
|---|---|---|
| IPC = instructions / cycles | 每 cycle 完成幾條指令 | 現代亂序核心 > 2 算順；< 1 多半在等記憶體或分支失誤 |
| cache-misses / cache-references | LLC miss 比例 | 高且 IPC 低 → 記憶體瓶頸，改存取模式 |
| branch-misses / branches | 分支預測失誤率 | > 5% 且熱迴圈有資料相依分支 → 試無分支寫法 / 排序資料 |
| task-clock vs elapsed | CPU 使用率 | 遠小於 elapsed → 在等待 |

**權限問題（很常遇到）**：
- `/proc/sys/kernel/perf_event_paranoid`：kernel 文件定義 2 = 只允許 user-space 量測（Linux 4.6 起預設）。部分發行版 kernel 的預設值更高（本機 Ubuntu 實測為 4，一般使用者執行 `perf stat` 直接 `No supported events found`）。
- Docker 預設 seccomp profile 擋 `perf_event_open`（Docker 文件列為 blocked syscall）。容器裡沒加權限就不能用 perf。
- 不能改 sysctl（屬於修改系統設定，考試也不允許）→ 直接改用手動計時 / gprof。
- 在 VM 裡硬體事件可能顯示 `<not supported>`，只剩軟體事件（task-clock、page-faults、context-switches）。

### 2.4 `perf record` / `perf report` / `perf annotate`（取樣找熱點）

```bash
gcc -O2 -g -fno-omit-frame-pointer prog.c -o prog   # -g 給符號與原始碼行；保留 frame pointer 讓 -g 呼叫鏈正確
perf record -g ./prog < in.txt > /dev/null           # 產生 perf.data
perf report --stdio --no-children | head -60         # 依函式自身時間排序
perf report --stdio --sort=symbol,srcline | head     # 細到原始碼行
perf annotate --stdio -s hot_function                # 熱點函式的組語，每行標 % 樣本
perf record --call-graph dwarf ./prog                # 沒有 frame pointer 時改用 DWARF 展開（檔案較大）
```

- `-g` 預設用 frame pointer（`fp`）展開 user space 呼叫鏈；GCC `-O1` 以上預設 `-fomit-frame-pointer`，所以要加 `-fno-omit-frame-pointer` 或用 `--call-graph dwarf`。
- `--children`（預設）把被呼叫者的時間也算進呼叫者；找「自己最花時間的函式」用 `--no-children`。
- `perf annotate` 看到某條 load 指令後面那條指令樣本特別多 → 那個 load cache miss（樣本常「滑」到下一條指令）。

### 2.5 gprof（`-pg`）

```bash
gcc -O2 -pg prog.c -o prog        # 編譯與連結都要 -pg
./prog < in.txt > /dev/null       # 正常結束（exit 或 main return）才會寫出 gmon.out
gprof -b ./prog gmon.out | head -40   # -b：省略說明文字；先 flat profile 再 call graph
```

- 優點：不需要特殊權限，容器內可用（若有 `gprof`，屬 binutils）。
- 缺點：被 inline 的函式看不到（可對熱點暫時加 `__attribute__((noinline))` 細分）；計時是取樣，短程式誤差大；不量 shared library 內的時間。

### 2.6 Valgrind：Callgrind / Cachegrind（若有安裝）

```bash
valgrind --tool=callgrind ./prog < small.txt > /dev/null      # 產生 callgrind.out.<pid>
callgrind_annotate callgrind.out.<pid> | head -40              # 依函式自身成本（Ir = 執行指令數）排序
valgrind --tool=callgrind --cache-sim=yes --branch-sim=yes ./prog   # 加 cache / 分支模擬（再慢約 2 倍）
valgrind --tool=cachegrind --cache-sim=yes ./prog < small.txt  # Cachegrind；cache 模擬預設是關的
cg_annotate cachegrind.out.<pid>
kcachegrind callgrind.out.<pid>                                # GUI，考場多半沒有
```

- 原理是指令層級模擬，**非常慢（數十倍量級）**，用小輸入跑。指令數（Ir）是決定性的，很適合比較「改前改後少了多少指令」，不受背景雜訊影響。
- cache 模擬的是簡化模型，結論要回到真機計時確認。

### 2.7 沒有任何工具時

1. 在懷疑的區段前後插 `now_ns()`，累加到全域變數，結束時印到 stderr。
2. 縮放輸入（N、N×2、N×4）：時間成長比例 → 推演算法複雜度；在某個大小突然變慢 → 資料超過某層 cache。
3. 註解掉某段（保持輸出不被刪掉）看總時間變化 → 那段的上限佔比（Amdahl，見 `03-optimize.md`）。
4. `gdb -p <pid>` 或在 gdb 中執行、手動 Ctrl-C 5～10 次看 `bt`：最常出現的函式就是熱點。

---

## 3. 成本數量級表（⚠️全部是約略值）

數字來自 Agner Fog 的表（Intel Skylake / Ice Lake、AMD Zen 3/4）與本機實測；不同 CPU 差異可達數倍。

| 操作 | 約略延遲 | 備註 |
|---|---|---|
| 整數加減、邏輯、移位 | 1 cycle | 每 cycle 可做 3–4 條 |
| 整數乘法 `imul` | 3 cycles | 每 cycle 1 條 |
| 整數除法 32 位元 | 約 10–26 cycles | Ice Lake 12、Zen 4 10–13、Skylake 26 |
| 整數除法 64 位元 | 約 10–18（新 CPU）到 35–88 cycles（Skylake 及更舊） | 能用 32 位元就用 32 位元 |
| FP 加 / 乘 / FMA | 約 3–5 cycles 延遲（Skylake 皆 4），每 cycle 可發 2 條 | 相依鏈受延遲限制，見 §5.8 |
| FP 除法（double） | 約 13–14 cycles | 迴圈內除以不變量 → 先算倒數（會改變位元結果，見 §6.8） |
| 分支預測失誤 | 約 15–20 cycles | Agner：Zen 4 15–18、Intel 多數 15–20 |
| L1D 命中 | 約 4–5 cycles | L1D 32–48 KB / core，line 64 B |
| L2 命中 | 約 12–17 cycles | 0.5–2 MB / core |
| L3 命中 | 約 40–70 cycles（Ice Lake 列 50–100） | 數 MB 到數十 MB，共用 |
| DRAM | 約 60–120 ns（數百 cycles）⚠️ | 循序存取靠硬體 prefetch 可隱藏大部分延遲 |
| `clock_gettime`（vDSO） | 約 20 ns（本機實測） | 不進核心 |
| 簡單 syscall（`getpid`、`write` 1 byte 到 /dev/null） | 約 300–400 ns（本機實測） | 依核心安全緩解措施差很多 |
| `malloc(32)+free` 熱路徑 | 約 7 ns（本機實測，glibc tcache 命中） | 大塊、跨執行緒、碎片化時貴很多 |
| 首次觸碰新頁（minor page fault, 4 KB） | 約 1–2 µs（本機實測） | 第二次觸碰同頁約 17 ns |
| context switch | 數 µs ⚠️未驗證 | 加上 cache 被洗掉的間接成本 |

**用法**：估「一次 cache miss ≈ 數十到數百次加法」，所以存取模式往往比運算量重要。

---

## 4. 記憶體階層

### 4.1 cache line 與 locality

- cache 以 **cache line** 為單位搬資料，x86-64 與大多數 aarch64 Linux 平台是 **64 bytes**（Apple M 系列 128 B；用 §1 的指令查）。
- **空間局部性**：讀了 `a[i]` 就順便載入 `a[i+1..]`，循序走過陣列最划算；硬體 prefetcher 也最擅長辨認循序 / 固定步長。
- **時間局部性**：剛用過的資料很快再用 → 留在 cache。把「對同一份資料的多次處理」合併成一次走訪（loop fusion），或分塊（tiling）讓工作集小於 cache。
- 步長（stride）= 一次跳 `stride × sizeof(elem)` bytes；超過 64 B 時每次存取都是新 line，等於 cache 只用了一小部分。

### 4.2 迴圈交換（loop interchange）

```c
/* 慢：內層 i 變動 → a[i][j] 每次跳一整列（stride = N*sizeof(int)） */
for (int j = 0; j < N; j++)
    for (int i = 0; i < N; i++)
        sum += a[i][j];

/* 快：內層 j 變動 → 連續記憶體 */
for (int i = 0; i < N; i++)
    for (int j = 0; j < N; j++)
        sum += a[i][j];
```

GCC `-O3` 有 `-floop-interchange`，但只在能證明安全時才換，不要依賴；手動換最可靠。

### 4.3 分塊（blocking / tiling）

```c
/* C = A × B，N×N double，C 先清零。BS 讓三個 BS×BS 區塊放得進 L1/L2 */
#define BS 64
for (int ii = 0; ii < N; ii += BS)
  for (int kk = 0; kk < N; kk += BS)
    for (int jj = 0; jj < N; jj += BS)
      for (int i = ii; i < ii + BS && i < N; i++)
        for (int k = kk; k < kk + BS && k < N; k++) {
            double a = A[i][k];                      /* 內層不變量外提 */
            for (int j = jj; j < jj + BS && j < N; j++)
                C[i][j] += a * B[k][j];              /* 內層連續 → 可向量化 */
        }
```

- 分塊的收益取決於**資料大小 vs cache 大小**。本機實測（N=1024，8 MB/矩陣，L3 32 MB）：`-O2` 下分塊（0.31 s）反而比單純 ikj（0.15 s）慢；`-O3 -march=native` 下 BS=128 分塊 0.082 s 與 ikj 0.087 s 差不多。資料遠大於 L3 或 cache 較小的機器上分塊才明顯有利。
- **結論**：先做迴圈交換（收益最大、風險最低），分塊要實測、BS 試 32/64/128。

### 4.4 AoS vs SoA

```c
/* AoS：一個粒子的欄位放一起 */
struct P { float x, y, z, mass; char name[16]; };
struct P ps[N];
for (int i = 0; i < N; i++) ps[i].x += vx;   /* 每個 32 B 結構只用 4 B → 浪費 7/8 頻寬 */

/* SoA：同一欄位放一起 */
struct Ps { float x[N], y[N], z[N], mass[N]; };
static struct Ps s;
for (int i = 0; i < N; i++) s.x[i] += vx;    /* 連續 float → 容易向量化 */
```

| 存取模式 | 選擇 |
|---|---|
| 熱迴圈只碰少數欄位、對所有元素做同樣運算 | SoA |
| 每次處理一個元素的大部分欄位（隨機存取單一元素） | AoS |
| 混合 | 熱欄位拆出來（hot/cold splitting）：熱欄位 SoA 或小結構，冷欄位另放 |

### 4.5 struct 欄位順序與 padding

每個欄位對齊到自身大小（x86-64 / aarch64 LP64：`double`/指標/`long` 8、`int` 4、`short` 2）；整個 struct 大小補到最大對齊的倍數。

```c
#include <stddef.h>
#include <stdio.h>
struct S1 { char a; double b; char c; int d; };   /* a@0 b@8 c@16 d@20 → sizeof 24 */
struct S2 { double b; int d; char a; char c; };   /* b@0 d@8 a@12 c@13 → sizeof 16 */

int main(void) {
    printf("%zu %zu %zu\n", sizeof(struct S1), offsetof(struct S1, d), sizeof(struct S2));
    return 0;   /* 本機實測：24 20 16 */
}
```

- 規則：**欄位由大到小排**，可減少 padding。陣列很大時，struct 從 24 B 變 16 B = 少 1/3 記憶體流量。
- 用 `_Static_assert(sizeof(struct S2) == 16, "layout");` 鎖住假設。
- 不要用 `__attribute__((packed))` 求快：未對齊存取在部分平台變慢，且取欄位位址會產生未對齊指標問題。
- 若 struct 是題目給的介面（檔案格式、與其他模組共用），**不能改順序**。

### 4.6 對齊

```c
#include <stdlib.h>
#include <stdalign.h>

/* 靜態 / 全域：兩種寫法皆可 */
static float buf1[1024] __attribute__((aligned(64)));
static alignas(64) float buf2[1024];               /* C11 */

/* 動態：aligned_alloc(alignment, size)，alignment 為 2 的冪次；
   C11 原本要求 size 是 alignment 的倍數（C17 已放寬），保險起見湊成倍數 */
size_t n = 1000;
size_t bytes = (n * sizeof(float) + 63) & ~(size_t)63;
float *p = aligned_alloc(64, bytes);               /* 用 free(p) 釋放 */

/* 舊介面：int posix_memalign(void **memptr, size_t alignment, size_t size); 成功回傳 0 */

/* 告訴編譯器指標已對齊（騙它是 UB） */
float *q = __builtin_assume_aligned(p, 64);
```

- 對齊對 SIMD load（aligned 版本指令）、跨 cache line 存取、避免 false sharing 有幫助。現代 x86 的 unaligned load（`loadu`）在資料其實對齊時幾乎不慢，所以對齊**通常是小收益**。
- `malloc` 只保證對「不大於請求大小的任何型別」足夠對齊（man malloc(3)）；glibc 在 64 位元平台實作上是 16 B。要 64 B 對齊必須用 `aligned_alloc`。

### 4.7 軟體 prefetch

```c
/* __builtin_prefetch(addr, rw, locality)
   rw: 0 = 讀（預設）、1 = 寫；locality: 0（用完不留）～3（盡量留在各層 cache，預設） */
for (int i = 0; i < n; i++) {
    __builtin_prefetch(&data[idx[i + 16]], 0, 1);   /* 提前約十幾次迭代 */
    sum += data[idx[i]];
}
```

- 只對**硬體 prefetcher 猜不到的模式**（間接索引 `a[idx[i]]`、鏈結結構、大步長）可能有用；循序存取加 prefetch 通常沒效甚至變慢。
- prefetch 無效位址不會 fault，但位址運算本身要合法（例如 `idx[i+16]` 不能越界讀 → 迴圈尾端要處理）。
- 距離要實測（太近沒效、太遠被擠出 cache）。新版 GCC 手冊多了 rw=2，GCC 13 只用 0/1。

### 4.8 TLB 與 huge pages（簡述）

- 每次存取要把虛擬位址轉實體位址，TLB 是這個轉換的 cache。4 KB 頁時，隨機存取幾百 MB 的資料會大量 TLB miss。
- Transparent Huge Pages（THP）：x86-64 常見 2 MB 頁。系統設定在 `/sys/kernel/mm/transparent_hugepage/enabled`（`always` / `madvise` / `never`；只讀，不要改）。若是 `madvise`，可對大塊記憶體：

```c
#include <sys/mman.h>
size_t sz = 512u << 20;
void *m = aligned_alloc(2u << 20, sz);          /* 2 MB 對齊 */
madvise(m, sz, MADV_HUGEPAGE);                    /* 建議 kernel 用 huge page；失敗不影響正確性 */
```

- 收益不保證，屬最後才試的手段。

### 4.9 避免指標追逐（pointer chasing）

```c
/* 鏈結串列：下一個位址要等這次 load 完成才知道 → 每個節點一次完整記憶體延遲，prefetcher 無效 */
for (Node *p = head; p; p = p->next) sum += p->val;

/* 陣列：位址可預測、可並行載入、可向量化 */
for (int i = 0; i < n; i++) sum += vals[i];
```

- 樹 / 圖：用陣列 + 索引（`int left, right`）取代指標，節點集中配置；BFS 順序重新排列節點。
- hash table：開放定址（open addressing）比 chaining 對 cache 友善。
- 「排序後再處理」常讓隨機存取變循序（例如依 key 排序後再 group-by）。

### 4.10 記憶體配置成本

| 問題 | 修法 |
|---|---|
| 熱迴圈裡 `malloc/free` 小物件 | 迴圈外配置一次重複使用；或 free-list / 物件池 |
| 大量同生命週期的小配置 | arena（bump allocator）：一次配一大塊，用指標往前推，最後一次釋放 |
| `realloc` 每次 +1 | 容量倍增（×2 或 ×1.5），攤銷 O(1) |
| `calloc` 後又自己清零 | 擇一；大塊 `calloc` 由 mmap 來的頁本身就是零，不需要再 memset |
| 每次呼叫都重新配置暫存 buffer | `static` buffer 或由呼叫者傳入 |

```c
/* 最小 arena：只配不放，最後一次 free */
typedef struct { char *base; size_t used, cap; } Arena;
static void *arena_alloc(Arena *a, size_t n) {
    n = (n + 15) & ~(size_t)15;                   /* 16 B 對齊 */
    if (a->used + n > a->cap) return NULL;        /* 簡化：不擴充 */
    void *p = a->base + a->used;
    a->used += n;
    return p;
}
/* Arena a = { malloc(64u << 20), 0, 64u << 20 };  ...  free(a.base); */
```

### 4.11 `memcpy` / `memset` / `memmove`

- glibc 的版本依 CPU 在執行期選最佳實作（SIMD、`rep movsb` 等），通常比手寫迴圈快；GCC 也會把「明顯是複製 / 清零」的迴圈改成呼叫它們（`-ftree-loop-distribute-patterns`）。
- 區域重疊必須用 `memmove`；用 `memcpy` 是 UB。
- 小而固定長度的 `memcpy(&x, p, 4)` 會被編譯成單一 load，是**合法的型別轉換 / 未對齊讀取**寫法（取代 `*(uint32_t *)p` 的 strict aliasing 違規）。

### 4.12 二維陣列

```c
/* 慢：指標陣列，每列分開配置 → 多一次間接存取、列不連續 */
double **m = malloc(n * sizeof *m); for (int i = 0; i < n; i++) m[i] = malloc(n * sizeof **m);

/* 快：一塊連續記憶體，自己算索引 */
double *m2 = malloc((size_t)n * n * sizeof *m2);
#define M2(i, j) m2[(size_t)(i) * n + (j)]
```

---

## 5. CPU 層級

### 5.1 分支預測與無分支寫法

- 可預測的分支（幾乎總是同一方向、或固定模式）幾乎免費；**依資料隨機**的分支每次失誤約 15–20 cycles。
- GCC `-O2` 會自己把簡單的 `if` 轉成 `cmov` / 遮罩（if-conversion）。本機實測：`if (a[i] >= 128) s += a[i];` 在 `-O2` 下隨機資料與排序資料一樣快——編譯器已轉成無分支，手寫遮罩沒有額外收益。**先看組語有沒有 `cmov`（x86）/ `csel`（aarch64）再決定**。
- 編譯器不轉的情況：分支裡有 store、函式呼叫、可能 fault 的 load、兩邊工作量差很多。

```c
/* 手動無分支技巧（確認 -O2 沒做到時才用） */
int mn = b ^ ((a ^ b) & -(a < b));       /* min(a,b)；-(cond) 為全 1 或全 0 */
int ab = (x ^ (x >> 31)) - (x >> 31);    /* abs(x)，假設 int 32 位元、算術右移（GCC 保證）；x=INT_MIN 溢位 */
s += v & -(v >= 128);                    /* 條件累加 */
cnt += (a[i] < pivot);                   /* 比較結果直接當 0/1 用 */
r = cond ? x : y;                        /* 簡單三元運算子，編譯器多半直接出 cmov/csel */
```

- 查表取代多層 `if/switch`；`switch` 連續的 case 編譯器會生成跳躍表。
- 把資料**排序或分群**讓分支變可預測，有時比改寫分支更有效（但排序本身有成本）。

### 5.2 `__builtin_expect` / likely / unlikely

```c
#define likely(x)   __builtin_expect(!!(x), 1)
#define unlikely(x) __builtin_expect(!!(x), 0)

if (unlikely(ptr == NULL)) { handle_error(); }   /* 錯誤路徑放到冷區，熱路徑直線化 */
```

- 只影響**程式碼排列**（哪邊是 fall-through）與編譯器的機率估計（預設 90%），不會改變 CPU 的動態預測器。收益通常很小，只在錯誤處理等極度偏斜的分支用。
- GCC 手冊建議優先用真實 profile（PGO，§7.3）。函式層級可用 `__attribute__((cold))` 標記錯誤處理函式。

### 5.3 迴圈展開

```c
#pragma GCC unroll 4            /* 緊接在 for/while/do 前；0 或 1 = 禁止展開 */
for (int i = 0; i < n; i++) a[i] = b[i] * k;
```

- `-funroll-loops`：展開「進入迴圈時就知道次數」的迴圈；程式變大，不一定變快。通用的 `-O2/-O3` 不開（`-fprofile-use` 會開）；但 x86 的 `-O2` 預設開 `-munroll-only-small-loops`（只把少於 4 條指令的小迴圈展開 1 次；GCC x86-Options，本機 GCC 13.3 `-Q --help=optimizers` 也顯示 `-funroll-loops [enabled]`），所以看到小迴圈被展開不要意外。
- 手動展開的真正價值通常是**打斷相依鏈**（多累加器，§5.8），而不是省迴圈計數指令。
- 手動展開要處理尾端（`n % 4` 剩下的元素）——最常出錯的地方。

### 5.4 迴圈不變量外提、強度折減、共同子運算式

```c
/* 前：每次迭代都呼叫 strlen → O(n²)（s 若在迴圈內被修改，編譯器就不能外提） */
for (size_t i = 0; i < strlen(s); i++) if (s[i] == ' ') cnt++;
/* 後 */
for (size_t i = 0, len = strlen(s); i < len; i++) if (s[i] == ' ') cnt++;

/* 前：每次都算 i*stride 與透過指標讀 p->scale（可能被 a[] 的寫入改到 → 編譯器不敢外提） */
for (int i = 0; i < n; i++) a[i * stride] = x * p->scale;
/* 後：手動外提 + 以加法取代乘法 */
const float sc = x * p->scale;
for (int i = 0, off = 0; i < n; i++, off += stride) a[off] = sc;
```

- 編譯器會做大部分外提，但遇到**可能別名（aliasing）**的記憶體讀取、或函式呼叫（不知道有沒有副作用）就不敢。手動存到區域變數最可靠。
- 熱迴圈裡的 `%`：若是循環計數，用計數器歸零取代 `i % k`。

### 5.5 函式呼叫與 inline

| 手段 | 說明 |
|---|---|
| `static inline` | 同一編譯單元內小函式，`-O2` 多半會自動 inline；`static` 讓編譯器知道沒有外部呼叫者 |
| `static inline __attribute__((always_inline))` | 強制 inline，失敗會報錯（手冊：對宣告為 inline 的函式有效） |
| `__attribute__((noinline))` | 禁止 inline；用來讓 profiler 看得到某函式，或把冷路徑分開 |
| `__attribute__((flatten))` | 把此函式內所有呼叫盡量 inline 進來 |
| `__attribute__((hot))` / `((cold))` | 提示熱 / 冷；cold 會以大小優化並集中放置 |
| `-flto` | 跨 `.c` 檔 inline 與分析；**編譯與連結都要加**同樣旗標 |

- 呼叫本身的成本不大（數 cycles），真正的收益是 inline 之後**能做其他最佳化**（常數傳播、向量化、消除重複載入）。
- 熱迴圈裡透過函式指標呼叫（例如 `qsort` 的比較函式）無法 inline → 自己寫特化版本（§10 `std::sort` 也是同理）。
- 遞迴改迭代：省去呼叫與堆疊，也避免深遞迴 stack overflow。

### 5.6 aliasing、`restrict`、`const`

```c
/* 編譯器不知道 dst 與 src 是否重疊 → 每次寫 dst 後都要重讀 src，或產生「執行期檢查重疊」的兩個版本 */
void add(float *dst, const float *a, const float *b, int n);

/* restrict：承諾在此函式內，透過這些指標存取的物件不會經由其他指標存取 */
void add(float *restrict dst, const float *restrict a, const float *restrict b, int n) {
    for (int i = 0; i < n; i++) dst[i] = a[i] + b[i];
}
```

- 本機實測 GCC 13 `-O3 -fopt-info-vec`：沒有 `restrict` 時報 `loop versioned for vectorization because of possible aliasing`（多一段執行期檢查）；加了 `restrict` 就直接向量化。
- **騙編譯器是 UB**：呼叫者真的傳入重疊的指標時，結果會錯。只在確定不重疊時加。
- `const` 指標參數（`const float *a`）**不**保證資料不被別處修改，對最佳化幫助有限；主要是介面文件。真正有用的是 `restrict` 與區域變數。
- strict aliasing：`-O2` 起開 `-fstrict-aliasing`，編譯器假設不同型別的指標不指向同一物件。用 `*(uint32_t *)float_ptr` 做型別轉換是 UB → 改用 `memcpy`。
- C++ 用 `__restrict__` 或 `__restrict`（C++ 沒有 `restrict` 關鍵字）。

### 5.7 除法與取餘數

| 情況 | 做法 |
|---|---|
| 除以**編譯期常數** | 編譯器開最佳化時自動轉成乘法 + 位移，不用手改 |
| 除以 2 的冪次 | 無號：`x >> k`、`x & (m-1)`。有號負數的 `/` 與 `>>` 結果不同（向零截斷 vs 向下取整），交給編譯器或改用無號 |
| 迴圈內除以**執行期不變**的整數 | 迴圈外預先計算「magic number」（libdivide 的概念 ⚠️需自行驗證正確性），或改變演算法避免除法 |
| 浮點除以不變量 | `inv = 1.0 / d;` 再乘：**結果位元可能不同**（只差最後一位也會讓 exact judge 錯） |
| 同時要商與餘數 | `q = a / b; r = a - q * b;`（或 `div()`），編譯器多半自動合併 |
| 64 位元除法 | 值域允許就用 32 位元型別，舊 CPU 上快數倍 |

### 5.8 延遲 vs 吞吐量、相依鏈、多累加器

- **延遲（latency）**：一條指令從輸入到輸出要幾 cycles。**吞吐量（throughput）**：每 cycle 能開始幾條。
- 迴圈每次迭代都依賴上一次的結果（`s += a[i]`）→ 速度被**延遲**限制：FP 加法約 4 cycles 延遲 → 每 4 cycles 只做 1 次加法，雖然硬體每 cycle 能做 2 次。
- 拆成多個獨立累加器 → 被**吞吐量**限制：

```c
/* 整數：結果與原版完全相同（整數加法可交換結合；溢位用無號型別才有定義） */
unsigned long long s0 = 0, s1 = 0, s2 = 0, s3 = 0;
int i = 0;
for (; i + 4 <= n; i += 4) {
    s0 += a[i]; s1 += a[i + 1]; s2 += a[i + 2]; s3 += a[i + 3];
}
for (; i < n; i++) s0 += a[i];                    /* 尾端 */
unsigned long long s = (s0 + s1) + (s2 + s3);
```

- **浮點**用多累加器會改變加法順序 → 結果可能差最後幾位。若 judge 要求與參考輸出逐字相同（例如印 `%.10f`），必須確認差異不影響輸出，或不要做。
- 指標追逐（§4.9）也是相依鏈：每次 load 的位址依賴上一次 load。

### 5.9 型別選擇

- 迴圈索引用 `int` / `size_t` 皆可；`unsigned` 索引在 `i - 1` 時會繞回巨大值（常見 bug）。有號整數溢位是 UB，反而讓編譯器能假設迴圈不溢位而做更多最佳化。
- 資料能用較窄型別（`int32_t` vs `int64_t`、`float` vs `double`、`uint8_t`）→ 記憶體流量減半、SIMD 一次處理更多元素。但要確認值域與精度不會改變結果。
- `bool` / `char` 陣列做旗標 → 大量時考慮 bitset（`uint64_t` + `__builtin_popcountll` / `__builtin_ctzll`）。

---

## 6. 向量化（SIMD）

### 6.1 自動向量化：`-O2` vs `-O3`

- GCC 手冊：`-O2` 開啟 `-ftree-loop-vectorize`、`-ftree-slp-vectorize`，cost model 是 `very-cheap`（GCC 12 起；GCC 11 以前 `-O2` 不向量化）。`very-cheap` 在需要執行期檢查（別名 / 對齊）時不向量化，也不產生 epilogue 迴圈。`-O3` 用 `dynamic` cost model。
- 本機實測 GCC 13.3 x86-64：

| 迴圈 | `-O2` | `-O3` |
|---|---|---|
| `D[i]=A[i]+B[i]`，次數為常數 1024（全域陣列） | 向量化 | 向量化 |
| 同上，次數 `n` 未知、指標參數 | **不**向量化 | 向量化（加執行期別名檢查 + 尾端） |
| `float` 內積 `s += a[i]*b[i]` | 不向量化 | 乘法向量化，但加法仍依序（`addss`，fold-left reduction，結果與原版相同） |
| 同上 + `-ffast-math` | — | 加法也向量化（`addps`），**結果可能改變** |

- 若 judge 用 `-O2` 編譯：優先讓迴圈變簡單（`restrict`、常數次數、手動多累加器 / 向量擴充 §6.5）。也可在函式上加 `__attribute__((optimize("O3")))` 或 `#pragma GCC optimize("O3")`，但 GCC 手冊明說 optimize 屬性「只應用於除錯，不適合正式程式碼」→ 當最後手段，且要確認題目允許。

### 6.2 看向量化報告

```bash
gcc -O3 -c hot.c -fopt-info-vec-optimized          # 成功：hot.c:12:5: optimized: loop vectorized using 16 byte vectors
gcc -O3 -c hot.c -fopt-info-vec-missed             # 失敗原因（很多雜訊，用 grep 過濾行號）
gcc -O3 -c hot.c -fopt-info-vec-all=vec.txt        # 全部寫到檔案
gcc -O2 -Q --help=optimizers | grep vectorize      # 查某個 -O 等級實際開了哪些旗標
```

`16 byte vectors` = SSE / NEON 寬度；用 `-mavx2`（或支援 AVX2 的 `-march`）會看到 32 byte。

### 6.3 向量化的條件與常見阻礙

| 阻礙（`missed` 訊息關鍵字） | 修法 |
|---|---|
| 可能別名（`possible aliasing`、`versioned`） | `restrict`、改用區域陣列、`#pragma GCC ivdep`（承諾沒有迴圈間相依） |
| 迴圈內函式呼叫（`statement clobbers memory`） | inline、把呼叫移出迴圈 |
| 迴圈次數不可數（`while` 依資料結束、迴圈中 `break`） | 先算出次數；把提早結束移到迴圈外 |
| 控制流（`control flow in loop`） | 改成條件運算式 / 遮罩；GCC 可做 if-conversion，但 store 在 `if` 裡較難 |
| 迴圈間真相依（`a[i] = a[i-1] + x`） | 演算法改寫（prefix sum 有平行版本）；否則無法向量化 |
| 非連續存取（間接索引、大 stride） | 改資料排列（SoA）；gather 很慢 |
| 浮點歸約（reduction） | 不加 `-ffast-math` 只能依序加；手動多累加器（會改變結果） |
| 混合型別（`unsupported data-type`） | 統一寬度；例如 `uint8_t` 累加到 `long long` 不易向量化，可先累加到 `uint32_t` 分段 |
| 次數太少 / cost model 判斷不划算 | 正常；不要硬來 |

### 6.4 `-march=native` 的陷阱

- `-march=native` 啟用**編譯機器**支援的所有指令集，產出的程式**可能無法在別台機器執行**（SIGILL: illegal instruction）。judge 機器可能和你的容器 / 開發機不同。
- `-mtune=native` 只調排程、不加新指令，可攜。
- x86-64 可攜等級：`x86-64`（SSE2，預設）、`x86-64-v2`（SSE4.2、POPCNT）、`x86-64-v3`（AVX2、FMA、BMI2）、`x86-64-v4`（AVX-512）。
- aarch64：NEON（Advanced SIMD）是 ARMv8-A 必備，預設就能用；SVE 要特別指定。
- 想用 AVX2 又要安全：執行期偵測 + 函式多版本：

```c
__attribute__((target("avx2"))) static void kernel_avx2(float *d, const float *a, int n);
static void kernel_generic(float *d, const float *a, int n);

void kernel(float *d, const float *a, int n) {
    if (__builtin_cpu_supports("avx2")) kernel_avx2(d, a, n);   /* x86 專用 builtin */
    else kernel_generic(d, a, n);
}
/* 或讓 GCC 自動做：__attribute__((target_clones("avx2", "default"))) */
```

### 6.5 GCC 向量擴充（可攜，x86 與 aarch64 都能編）

```c
#include <string.h>
typedef float v4sf __attribute__((vector_size(16)));   /* 4 個 float */

float sum_v(const float *a, int n) {
    v4sf acc = {0, 0, 0, 0};
    int i = 0;
    for (; i + 4 <= n; i += 4) {
        v4sf x;
        memcpy(&x, a + i, sizeof x);        /* 未對齊安全的載入；直接 *(v4sf*) 需要 16 B 對齊 */
        acc += x;                           /* 逐元素相加 */
    }
    float s = (acc[0] + acc[1]) + (acc[2] + acc[3]);   /* 可用 [] 取元素 */
    for (; i < n; i++) s += a[i];
    return s;                               /* 注意：加法順序已改變 → 浮點結果可能與純量版不同 */
}
```

- 支援 `+ - * / % & | ^ ~ << >>`、與純量混用（純量自動擴充）、比較運算子結果為 0 / -1（全 1）的整數向量。
- 目標不支援該寬度時，GCC 會用較窄指令合成，程式仍然正確。

### 6.6 x86 intrinsics（SSE / AVX2）

```c
#include <immintrin.h>

/* AVX2：一次 8 個 int32 相加；編譯需 -mavx2（或 target("avx2") 屬性） */
void add_i32_avx2(int *d, const int *a, const int *b, int n) {
    int i = 0;
    for (; i + 8 <= n; i += 8) {
        __m256i x = _mm256_loadu_si256((const __m256i *)(a + i));   /* u = unaligned */
        __m256i y = _mm256_loadu_si256((const __m256i *)(b + i));
        _mm256_storeu_si256((__m256i *)(d + i), _mm256_add_epi32(x, y));
    }
    for (; i < n; i++) d[i] = a[i] + b[i];
}

/* SSE（x86-64 預設就有 SSE2）：4 個 float */
void add_f32_sse(float *d, const float *a, const float *b, int n) {
    int i = 0;
    for (; i + 4 <= n; i += 4)
        _mm_storeu_ps(d + i, _mm_add_ps(_mm_loadu_ps(a + i), _mm_loadu_ps(b + i)));
    for (; i < n; i++) d[i] = a[i] + b[i];
}
```

命名規則：`_mm`（128）/ `_mm256`（256）/ `_mm512`；後綴 `_ps` float、`_pd` double、`_epi32` int32、`_si256` 整個暫存器。

### 6.7 aarch64 NEON intrinsics

```c
#include <arm_neon.h>

void add_f32_neon(float *d, const float *a, const float *b, int n) {
    int i = 0;
    for (; i + 4 <= n; i += 4)
        vst1q_f32(d + i, vaddq_f32(vld1q_f32(a + i), vld1q_f32(b + i)));   /* q = 128 位元 */
    for (; i < n; i++) d[i] = a[i] + b[i];
}
/* 水平加總（AArch64）：float s = vaddvq_f32(v); 常數廣播：vdupq_n_f32(x) */
```

**優先順序**：自動向量化（加 `restrict`、簡化迴圈）> GCC 向量擴充（可攜）> intrinsics（不可攜，要寫兩套）。

### 6.8 浮點：`-ffast-math`、重排、FMA

- `-ffast-math` 會開：`-fno-math-errno`、`-funsafe-math-optimizations`（含 `-fassociative-math`、`-freciprocal-math`、`-fno-signed-zeros`、`-fno-trapping-math`）、`-ffinite-math-only`（假設沒有 NaN / Inf → `isnan()` 可能被優化掉）等；`-Ofast` = `-O3` + `-ffast-math` + `-fallow-store-data-races`。連結時還可能載入改變 FPU 控制字的啟動檔（例如把 denormal 當 0）。
- **exact-output judge 下避免使用**，除非能證明輸出（例如四捨五入到固定位數）不受影響，且經過大量比對。
- **FMA 收縮**：GCC 手冊說 C 在 GNU 模式（預設 `-std=gnu17` 等）下預設 `-ffp-contract=fast`，標準模式（`-std=c11`）下為 `off`。目標有 FMA 指令時（aarch64 一律有；x86 需 `-mfma` / `-march=x86-64-v3` / `native`），`a*b+c` 可能被合成一條 FMA，**只少一次捨入 → 結果可能和沒有 FMA 的版本差最後一位**。所以「加 `-march=native` 後輸出變了」可能是 FMA 造成；要保持一致可加 `-ffp-contract=off`。
- `float` → `double` 或反之都會改變結果；不要為了速度把題目的 `double` 改 `float`。

---

## 7. 編譯旗標

### 7.1 旗標總表

| 旗標 | 作用 | 風險 / 備註 |
|---|---|---|
| `-O0` | 不優化（預設），除錯最直觀 | 慢 2–10 倍以上；**絕不要用 -O0 量效能** |
| `-O1` | 基本優化（含 `-fomit-frame-pointer`、if-conversion） | |
| `-O2` | 幾乎所有不涉及空間換時間的優化；GCC 12+ 含 very-cheap 向量化 | 最常見的 judge 設定 |
| `-O3` | `-O2` + 更積極：`-floop-interchange`、`-funswitch-loops`、`-fpeel-loops`、`-fvect-cost-model=dynamic` 等 | 程式變大，偶爾更慢；要量 |
| `-Os` / `-Oz` | 優化大小 | 一般比 `-O2` 慢一點；小 cache 時偶爾更快 |
| `-Ofast` | `-O3` + `-ffast-math` + `-fallow-store-data-races` | 不符合標準，可能改變浮點結果 |
| `-Og` | 保留除錯體驗的優化 | 用於除錯，不用於量測 |
| `-march=X` | 允許使用 X 的指令集 | `native` 可能在 judge 上 SIGILL |
| `-mtune=X` | 只針對 X 調整排程 | 可攜 |
| `-flto` | 連結期跨檔案優化 | 編譯與連結都要加；多檔專案才有意義 |
| `-fprofile-generate` / `-fprofile-use` | PGO：依實際執行資料優化分支、inline、展開 | 流程見 §7.3；judge 自己重新編譯時通常用不到 |
| `-funroll-loops` | 展開次數可知的迴圈 | 不一定更快 |
| `-fno-plt` | 呼叫 shared library 函式時不經 PLT stub，直接從 GOT 取址 | 收益小；停用 lazy binding |
| `-fomit-frame-pointer` | 省一個暫存器；`-O1` 起預設 | perf 呼叫鏈要 `-fno-omit-frame-pointer` |
| `-ffp-contract=off` | 禁止 FMA 收縮 | 保持浮點結果與無 FMA 版本一致 |
| `-fno-math-errno` | `sqrt` 等不設 errno → 可直接用硬體指令 | 程式不檢查 errno 時通常安全（仍要比對輸出） |
| `-static` | 靜態連結 | 啟動稍快、免 PLT；judge 環境可能不允許 |
| `-g` | 除錯資訊 | GCC 的設計目標是不改變產生的機器碼，量效能時可以留著（perf/gprof 需要符號） |

- 多個 `-O` 時最後一個生效。
- 看某等級實際開了哪些旗標：`gcc -O2 -Q --help=optimizers | grep enabled`。

### 7.2 看組合語言

```bash
gcc -O2 -S -fverbose-asm hot.c -o hot.s        # 組語 + 註解（變數名）
gcc -O2 -S -masm=intel hot.c -o hot.s           # x86 Intel 語法
objdump -d -M intel --no-show-raw-insn prog | less   # 反組譯執行檔（x86 Intel 語法）
objdump -d -S prog | less                       # 搭配 -g 編譯，可對照原始碼
gcc -O2 -g -c hot.c && objdump -d -S hot.o      # 只看單一檔案
```

| 要確認的事 | x86-64 看什麼 | aarch64 看什麼 |
|---|---|---|
| 向量化了嗎 | `xmm`（16 B）/ `ymm`（32 B）暫存器、`addps/vpaddd/vfmadd...` | `v0.4s` 之類的向量暫存器、`fadd v.., ld1` |
| 分支變無分支了嗎 | `cmovXX`、`setXX` | `csel`、`cset` |
| 除法還在嗎 | `div`/`idiv`（慢）vs `imul` + 移位 | `udiv/sdiv` vs `umulh/smulh` |
| 函式被 inline 了嗎 | 熱迴圈裡還有沒有 `call` | `bl` |
| 被刪掉了嗎 | 量測的程式碼整段不見 → 結果沒被使用 | 同左 |

Compiler Explorer（godbolt.org）是線上即時看組語的工具；考場可上網的話可用來快速比較，但**不能貼題目程式碼到外部網站**時就改用本機 `gcc -S`。

### 7.3 PGO 與 LTO 流程

```bash
# PGO（Profile-Guided Optimization）
gcc -O2 -fprofile-generate prog.c -o prog      # 編譯 + 連結都要此旗標
./prog < train_input.txt > /dev/null           # 產生 .gcda 檔
gcc -O2 -fprofile-use prog.c -o prog           # 依 profile 重新編譯（開啟 -funroll-loops、-fpeel-loops 等）

# LTO
gcc -c -O2 -flto a.c
gcc -c -O2 -flto b.c
gcc -O2 -flto a.o b.o -o prog
```

PGO 需要「訓練輸入要具代表性」，且 judge 若用自己的指令從原始碼編譯，你的 `.gcda` 不會被用到——**只在你能控制 build 時考慮**。

---

## 8. I/O 速度

### 8.1 stdio 緩衝

- man setvbuf(3)：stdout 接終端機時是**行緩衝**，接檔案 / 管線時是**完全緩衝**；stderr 預設**不緩衝**。judge 通常把 stdout 接到檔案或管線 → 已是完全緩衝。
- 常見拖慢原因：每行 `fflush(stdout)`、`setvbuf(stdout, NULL, _IONBF, 0)`、大量寫 stderr（無緩衝，每次一個 syscall）。
- 加大緩衝（必須在第一次 I/O **之前**呼叫）：

```c
static char outbuf[1 << 20];
setvbuf(stdout, outbuf, _IOFBF, sizeof outbuf);   /* 成功回傳 0 */
```

- 互動題（judge 與程式來回對話）**必須**每次輸出後 `fflush(stdout)`，否則會卡住；不要為了速度拿掉。

### 8.2 快速輸入：`fread` 大區塊 + 自己解析

```c
#include <stdio.h>

static char ibuf[1 << 16];
static size_t ilen = 0, ipos = 0;

static inline int gc(void) {                       /* 回傳下一個字元，EOF 回傳 -1 */
    if (ipos == ilen) {
        ilen = fread(ibuf, 1, sizeof ibuf, stdin);
        ipos = 0;
        if (ilen == 0) return -1;
    }
    return (unsigned char)ibuf[ipos++];
}

static int read_int(int *out) {                    /* 成功回傳 1，EOF 回傳 0 */
    int c = gc();
    while (c != '-' && (c < '0' || c > '9')) { if (c == -1) return 0; c = gc(); }
    int neg = 0;
    if (c == '-') { neg = 1; c = gc(); }
    long long v = 0;
    while (c >= '0' && c <= '9') { v = v * 10 + (c - '0'); c = gc(); }
    *out = (int)(neg ? -v : v);
    return 1;
}
```

- 只處理十進位整數；浮點數解析很難寫對，**用 `strtod`**（可先 `fread` 整塊，再在 buffer 上用 `strtod` 前進）。
- 輸入格式若有其他字元（例如 `+5`、科學記號），自寫解析會錯 → 先看規格。
- 單字元讀取也可用 `getchar_unlocked()`（POSIX，省去每次加鎖；單執行緒才安全）。

### 8.3 快速輸出：自寫 itoa + 一次 `fwrite`

```c
static char obuf[1 << 16];
static size_t opos = 0;

static inline void flush_out(void) { fwrite(obuf, 1, opos, stdout); opos = 0; }

static void write_int(int x) {
    if (opos > sizeof obuf - 16) flush_out();
    char t[12]; int n = 0;
    unsigned u = x < 0 ? 0u - (unsigned)x : (unsigned)x;   /* INT_MIN 也正確 */
    do { t[n++] = (char)('0' + u % 10); u /= 10; } while (u);
    if (x < 0) obuf[opos++] = '-';
    while (n) obuf[opos++] = t[--n];
    obuf[opos++] = '\n';
}
/* main 結束前一定要 flush_out()！忘記 = 輸出不完整 = 答案錯 */
```

本機實測（500 萬個整數讀入並各輸出一行，`-O2`，輸出寫檔）：`scanf("%d")` + `printf("%d\n")` 約 0.57 s → `fread` 自寫解析 + 自寫輸出約 0.14 s（約 4 倍），兩者輸出 `cmp` 完全相同。

### 8.4 大檔案：`mmap`

```c
#include <sys/mman.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>

int fd = open(path, O_RDONLY);
struct stat st; fstat(fd, &st);
const char *p = mmap(NULL, (size_t)st.st_size, PROT_READ, MAP_PRIVATE, fd, 0);
if (p == MAP_FAILED) { /* 退回 fread */ }
madvise((void *)p, (size_t)st.st_size, MADV_SEQUENTIAL);   /* 提示循序讀，積極預讀 */
/* ... 直接在 p[0 .. st_size-1] 上解析；注意檔案結尾沒有 '\0' ... */
munmap((void *)p, (size_t)st.st_size); close(fd);
```

- 只適用於**一般檔案**；stdin 若是管線 → `mmap` 失敗，要有 `fread` 備案。
- 相對大區塊 `fread`，收益通常不大（省一次複製）；大區塊 `fread` 已經足夠快。
- `MAP_POPULATE` 旗標可預先建立頁表、減少之後的 page fault。

### 8.5 C++ 注意

```cpp
std::ios::sync_with_stdio(false);   // 解除 iostream 與 stdio 同步；之後不要混用 printf/scanf 與 cin/cout
std::cin.tie(nullptr);              // cin 讀之前不自動 flush cout
std::cout << x << '\n';             // 用 '\n'，不要用 std::endl（endl 每次都 flush）
```

---

## 9. 系統層級

### 9.1 syscall 成本與批次化

- 每次 syscall 數百 ns（本機實測 `write` 1 byte 約 380 ns）→ **每個位元組 / 每行一次 `write`/`read` 非常慢**。用緩衝批次處理（§8）。
- 若有 `strace`：`strace -c ./prog < in.txt > /dev/null` 統計各 syscall 次數與時間；`strace -f -e trace=write ./prog` 看某類呼叫。在容器中 `strace` 也可能因 ptrace 權限受限。
- 常見浪費：迴圈裡 `fopen/fclose`、`time()`/`clock_gettime` 太頻繁（後者便宜，前者看實作）、`usleep(0)`、`sched_yield()` 自旋。

### 9.2 context switch 與執行緒數

- 執行緒數 > 可用 CPU 數 → 頻繁被切換，加鎖時更糟（持鎖者被切走）。執行緒數取「實際可用 CPU 數」（§9.5）。
- `/usr/bin/time -v` 的 involuntary context switches 很高 → CPU 不夠分；voluntary 很高 → 常阻塞（鎖、I/O、`sleep`）。
- 多執行緒同步細節見 `domain/multicore-sync.md`。

### 9.3 nice / CPU affinity（只觀察，不要改系統）

```bash
taskset -p <pid>               # 查看行程目前允許的 CPU
taskset -c 0 ./prog            # 把自己的程式綁在 CPU 0 執行（減少量測變異；只影響自己的行程）
nice -n 10 ./prog              # 降低自己的優先權（一般使用者不能調高）
```

```c
#define _GNU_SOURCE
#include <sched.h>
cpu_set_t set;
CPU_ZERO(&set);
sched_getaffinity(0, sizeof set, &set);   /* 0 = 自己 */
int ncpu = CPU_COUNT(&set);               /* 可用 CPU 數（不含 cgroup 配額） */
/* int sched_setaffinity(pid_t pid, size_t cpusetsize, const cpu_set_t *mask); 綁核心 */
```

- 綁核心只在量測時降低變異；judge 怎麼排程你控制不了，不要在提交的程式裡依賴特定 CPU 編號。

### 9.4 page fault

- 新配置的記憶體首次寫入時才真正分配頁（minor fault，本機實測約 1–2 µs / 4 KB 頁）。配置 1 GB 並全部碰一次 ≈ 26 萬次 fault。
- 修法：重複使用 buffer 而不是每輪重新 `malloc`/`free` 大塊（glibc 對大塊用 `mmap`，`free` 時還回 kernel，下次又要 fault）；只配置需要的大小；`MAP_POPULATE`。
- `/usr/bin/time -v` 的 Minor page faults 數量 ≈ 碰過的頁數 → 可估記憶體使用模式。

### 9.5 容器 CPU 限制：`nproc` vs cgroup 配額

```bash
nproc                              # 可用處理器數（affinity 限制）
cat /sys/fs/cgroup/cpu.max         # 格式 "$MAX $PERIOD"（微秒）；"max 100000" = 不限
# 例："150000 100000" → 每 100 ms 最多用 150 ms CPU ≈ 1.5 顆
cat /sys/fs/cgroup/cpu.stat        # nr_throttled / throttled_usec 增加 → 被配額節流
```

- `nproc` 計算的是**本行程可用的處理器數**（受 affinity / `OMP_NUM_THREADS` 影響）。GNU coreutils **9.8（2025-09）起**才會參考 cgroup v2 的 CPU quota；Ubuntu 24.04 的 coreutils 較舊，`nproc` 可能回報 12 但配額只有 2 顆。
- `sysconf(_SC_NPROCESSORS_ONLN)` 是系統上線的 CPU 數，同樣不看配額。
- 被配額限制時開太多執行緒：總 CPU 時間不變，但被節流造成延遲尖峰，常常**更慢**。
- 若 judge 量的是 CPU 時間（user+sys）而不是牆鐘時間，多執行緒**不會**降低分數上的時間，反而因同步開銷增加。先確認 judge 量什麼。

### 9.6 NUMA（簡述）

多插槽伺服器上，每顆 CPU 有自己近端的記憶體，存取遠端記憶體較慢。Linux 預設「first-touch」：頁面配置在**第一次寫入它的執行緒**所在節點。多執行緒程式讓每個執行緒初始化自己要處理的資料。單插槽桌機 / 一般容器通常不用管（`lscpu` 看 `NUMA node(s)`）。

### 9.7 量測雜訊

CPU 頻率調整（turbo、溫度）、其他容器 / 背景程式、SMT 鄰居共用核心。對策：多跑取最小值與中位數、交錯跑 A/B 版本（ABABAB）、拉長單次執行時間到 0.5 s 以上。

---

## 10. C++ 補充

| 問題 | 修法 |
|---|---|
| `vector` 一直 `push_back` 造成多次重新配置與複製 | 事先 `v.reserve(n)` |
| 傳大型物件 by value | `const T&` 傳參；要轉移所有權用 `std::move` |
| 回傳大型容器 | 直接 `return v;`（RVO / move），不要用 `std::move(v)` 包回傳值（會妨礙 RVO） |
| 熱迴圈裡 virtual 呼叫 | 無法 inline；改模板 / `final` / 依型別分組後批次處理 |
| `std::map` / `std::set`（紅黑樹，節點分散） | 只需查詢 → 排序過的 `vector` + `lower_bound`，或 `unordered_map` + `reserve` |
| `std::list` | 幾乎總是 `vector` 較快（cache） |
| `std::endl` | `'\n'` |
| `qsort` vs `std::sort` | `std::sort` 的比較器可 inline，通常明顯較快；C 裡可自己寫特化的排序（例如整數用 radix sort） |
| `std::string` 重複串接 | `reserve`，或一次組到 buffer |
| 例外用於一般流程控制 | 例外很慢，只用於真正的錯誤 |
| `shared_ptr` 複製 | 原子計數成本；傳 `const shared_ptr&` 或裸指標 / 參考 |

---

## 11. 熱點模式 → 修法 大表

| # | 症狀 / 熱點模式 | 為什麼慢 | 修法 | 典型收益（⚠️約略） | 風險 |
|---|---|---|---|---|---|
| 1 | 巢狀迴圈 O(n²) 搜尋 / 比對 | 演算法 | 排序 + 二分、hash、前綴和、雙指標 | 數十～數千倍 | 邏輯錯誤；需重新驗證 |
| 2 | 內層迴圈沿著「列」方向走 2D 陣列 | 每次存取新 cache line | 迴圈交換 / 轉置 | 數倍～十倍以上 | 低 |
| 3 | `scanf/printf` 大量資料 | 格式解析 + 鎖 | `fread` + 自寫解析；輸出 buffer + `fwrite` | 2～5 倍（I/O 部分） | 忘記 flush、格式邊界 |
| 4 | 每行 `fflush` / 寫 stderr / `endl` | 每次 syscall | 移除（非互動題）；debug 輸出拿掉 | 大 | 互動題不能拿 |
| 5 | 熱迴圈裡 `malloc/free` | 配置器開銷 + page fault | 迴圈外配置、重複使用、arena | 小～數倍 | 記憶體重用時忘了清 |
| 6 | 鏈結串列 / 指標樹走訪 | pointer chasing | 陣列 + 索引、連續配置 | 數倍 | 改動大 |
| 7 | AoS 只用一兩個欄位 | 頻寬浪費 | SoA / 熱冷分離 | 1.5～4 倍 | 介面改動 |
| 8 | `for (i < strlen(s))` | O(n²) | 先算長度 | 大 | 低 |
| 9 | 迴圈內除法 / 取餘數（變數） | 除法延遲 10～90 cycles | 外提倒數、改計數器、用 2 的冪次 + 遮罩 | 1.2～3 倍 | 浮點倒數改變結果 |
| 10 | `s += a[i]` 浮點歸約 | 相依鏈（延遲） | 多累加器（整數）；浮點需評估結果差異 | 2～4 倍 | 浮點結果改變 |
| 11 | 隨機資料的 `if` | 分支失誤 | 先看是否已 cmov；無分支 / 查表 / 排序 | 0～數倍 | 可讀性 |
| 12 | 迴圈沒向量化（`-fopt-info-vec-missed`） | 別名 / 呼叫 / 控制流 | `restrict`、inline、簡化迴圈 | 2～8 倍（該迴圈） | `restrict` 用錯是 UB |
| 13 | 小函式在另一個 `.c` 被熱迴圈呼叫 | 無法 inline | 移到 header 做 `static inline`，或 `-flto` | 小～數倍 | 低 |
| 14 | `qsort` 大量整數 | 函式指標比較 | 自寫排序 / radix sort / C++ `std::sort` | 1.5～3 倍 | 穩定性需求 |
| 15 | 重複計算相同結果 | 多餘工作 | 快取 / 查表 / 預先計算 | 視情況 | 記憶體 |
| 16 | struct 很多 padding 的大陣列 | 記憶體流量 | 欄位由大到小排 | 小～1.5 倍 | 介面固定時不能改 |
| 17 | 多執行緒寫相鄰計數器 | false sharing | 區域累加、padding 到 64 B | 數倍 | 見 multicore-sync.md |
| 18 | 執行緒數 = `nproc`，但容器配額更少 | 被節流 | 依 `cpu.max` 決定執行緒數 | 視情況 | — |
| 19 | 大量小 `write`/`read` | syscall 成本 | 緩衝批次 | 大 | flush 時機 |
| 20 | 每輪重新配置大 buffer | page fault | 重複使用 | 小～中 | — |
| 21 | `-O0` 編譯 | 未優化 | 確認 judge 旗標；若可改則 `-O2` | 2～10 倍 | judge 旗標固定時無效 |
| 22 | 以 `double` 運算整數問題 | 轉換 + 精度 | 改整數運算 | 小 | 溢位 |
| 23 | `pow(x, 2)`、`sqrt` 比較距離 | 函式呼叫 | `x*x`；比較平方距離 | 小～中 | `pow` 精度與 `x*x` 可能不同（極少） |
| 24 | 大型 `switch`/字串比較分派 | 分支 + `strcmp` | 預先轉成整數 id / hash / 查表 | 中 | — |

---

## 12. 實例：矩陣乘法從 baseline 到優化

題目假設：`C = A × B`，N = 1024，`double`，輸出 C 的檢查值。以下時間為**本機實測**（Ryzen 5 5600、GCC 13.3、單執行緒），只看相對趨勢；各版本檢查值完全相同（輸入值是 0.25 的倍數，乘加皆精確，所以重排不改變結果——一般資料**不保證**）。

```c
/* v0 baseline：ijk，內層 B[k][j] 沿著行走（stride = 8 KB） */
for (int i = 0; i < N; i++)
    for (int j = 0; j < N; j++) {
        double s = 0;
        for (int k = 0; k < N; k++) s += A[i][k] * B[k][j];
        C[i][j] = s;
    }

/* v1 迴圈交換 ikj：內層 C[i][j]、B[k][j] 都連續，且可向量化 */
memset(C, 0, sizeof C);
for (int i = 0; i < N; i++)
    for (int k = 0; k < N; k++) {
        double a = A[i][k];
        for (int j = 0; j < N; j++) C[i][j] += a * B[k][j];
    }
```

| 版本 | `-O0` | `-O2` | `-O3` | `-O3 -march=native` |
|---|---|---|---|---|
| v0 ijk | 3.19 s | 1.67 s | 1.59 s | 0.73 s |
| v1 ikj（迴圈交換） | 1.52 s | **0.15 s** | 0.15 s | 0.087 s |
| v2 三層分塊 BS=64 | 2.21 s | 0.31 s | 0.22 s | 0.095 s |
| v2' 分塊 BS=128 | — | 0.35 s | — | 0.082 s |
| v3 先轉置 B + ijk + 4 累加器 | — | 0.20 s | — | 0.18 s |

**解讀**：
1. 最大收益來自**迴圈交換**（`-O2` 下約 11 倍），而且風險最低。
2. `-O0` 下所有版本都慢——量效能絕對不要用 `-O0`。
3. 分塊在這台機器（L3 32 MB，三個矩陣共 24 MB 幾乎放得下）沒有贏過 ikj，`-O2` 下甚至更慢（多了迴圈開銷、內層只有 64 次）。資料更大或 cache 更小時才可能贏 → **一定要量**。
4. `-march=native`（AVX2 + FMA）再快約 1.7 倍，但 judge 機器不一定支援；且 FMA 一般會改變浮點結果（§6.8）。
5. 多執行緒（依 i 切分列給各執行緒）是下一步，見 `domain/multicore-sync.md`；先確認容器可用 CPU 數（§9.5）。

**同樣思路的 I/O 例子**：500 萬整數讀寫，`scanf/printf` 0.57 s → `fread`/`fwrite` 自寫 0.14 s（§8.3）。若整支程式本來 0.7 s 而 I/O 佔 0.57 s，只優化運算最多省 0.13 s——**先看比例**（Amdahl）。

**直方圖（histogram）例子的思路**（未實測，⚠️收益依資料而定）：
- `hist[data[i]]++` 隨機分布時，`hist` 小（例如 256 格）→ 都在 L1，瓶頸是同一格連續 `++` 的 store→load 相依；可用 2～4 份子直方圖交錯累加最後合併。
- `hist` 很大（數百萬格）→ 隨機存取 cache miss，考慮先依高位元分桶（radix 分割）再統計。

---

## 13. 除錯清單（效能相關）

| 症狀 | 檢查 |
|---|---|
| 優化後結果不同 | 浮點重排 / FMA / `-ffast-math`？`restrict` 用在重疊指標？展開的尾端漏處理？未初始化變數在不同優化等級表現不同？用 `-fsanitize=address,undefined -g -O1` 跑一次 |
| 本機變快，judge 沒變 | judge 旗標不同（看 build 腳本）？judge 量 CPU 時間而你優化的是牆鐘（多執行緒）？輸入規模 / 分布不同？瓶頸在 I/O 而 judge 輸出接法不同？ |
| judge 上 crash（SIGILL） | 用了 `-march=native` / intrinsics 但 judge CPU 不支援 |
| 改了旗標沒效果 | Makefile / CMake 沒吃到（`make VERBOSE=1` 或 `make -n` 看實際指令）；舊的 `.o` 沒重編（`make clean`） |
| 量測數字跳很大 | 背景程式、頻率調整；取 min/median；拉長執行時間 |
| 量到 0 秒 / 快得不合理 | 結果沒使用 → 被編譯器刪除；用 `KEEP()` / 印出結果 |
| `perf` 不能用 | `perf_event_paranoid`、Docker seccomp → 改手動計時 / gprof |
| 加了執行緒反而變慢 | false sharing、鎖競爭、執行緒數 > 配額 CPU、工作太小（建立執行緒成本） |
| 程式被 kill / MLE | `/usr/bin/time -v` 看 Max RSS；減少暫存、改用較窄型別 |
| 輸出少了最後一段 | 自寫輸出 buffer 忘了 `flush_out()`；`_exit()` 不 flush stdio |
| 互動題卡住 | 拿掉了必要的 `fflush(stdout)` |

---

## 14. 優化清單（依序打勾）

1. [ ] 確認 judge 的編譯指令、旗標、量測方式（牆鐘 / CPU 時間）、時間限制、輸入規模。
2. [ ] 建 baseline：正確輸出存檔 + 用 judge 相同旗標量時間（多次取 min/median）。
3. [ ] 偵查工具（§1），選定剖析方式（perf → gprof → 手動計時）。
4. [ ] 找出前 1～3 個熱點與時間比例（Amdahl 估上限）。
5. [ ] 演算法 / 資料結構：有沒有降複雜度的機會？
6. [ ] I/O：資料量大時改 `fread`/`fwrite` 緩衝；拿掉多餘 flush 與 debug 輸出。
7. [ ] 記憶體：迴圈順序、連續存取、SoA、避免 pointer chasing、熱迴圈不配置。
8. [ ] 編譯器能不能幫忙：`-fopt-info-vec-missed` 看熱迴圈為何沒向量化 → `restrict`、inline、簡化。
9. [ ] CPU 微調：外提不變量、除法、多累加器（整數）、分支（先看組語）。
10. [ ] 系統：執行緒數對照 `cpu.max`；syscall 批次；重複使用 buffer。
11. [ ] 每一步：`diff`/`cmp` 比對輸出（含邊界：n=0、1、非 4/8 倍數、最大值、負數）→ 量時間 → commit → 記錄。
12. [ ] 最後用 judge 的完整建置流程從乾淨狀態重編（`make clean && make`）再驗證一次。

---

## 15. 向模型提問的範本

### 15.1 找熱點

```
我在 Linux 容器（{{x86_64 / aarch64}}，GCC {{版本}}）優化一支 C 程式，judge 的編譯指令是：{{例如 gcc -O2 -std=c11 main.c -lm}}。
judge 量的是 {{牆鐘 / CPU 時間}}，時間限制 {{秒}}，輸入規模 {{N = ...}}。
可用工具：{{perf 可用 / perf 被擋 / 有 gprof / 只能手動計時}}。
目前量測：
{{貼 perf report / gprof flat profile / 分段計時輸出}}
程式碼（熱點部分）：
{{貼程式碼}}
請：1) 指出前三個熱點與估計比例；2) 判斷每個熱點是演算法 / 記憶體 / I/O / 分支 / 相依鏈 / 向量化 問題，並說明依據；
3) 若資料不足，告訴我要在哪裡加計時點。先不要給修改後的程式碼。
```

### 15.2 為什麼沒向量化

```
這個迴圈在 {{-O2 / -O3}} 下沒有向量化。`-fopt-info-vec-missed` 輸出：
{{貼相關行}}
迴圈程式碼：
{{貼程式碼}}
請解釋每一條 missed 訊息的意思，提出不改變輸出結果的修改（例如 restrict、改資料排列、拆迴圈），
並明確標出哪些修改會改變浮點結果或依賴未定義行為的假設。
```

### 15.3 cache / 記憶體存取改寫

```
資料結構定義：{{貼 struct / 陣列宣告}}
熱迴圈：{{貼程式碼}}
資料大小：{{元素數 × 每個大小 = 總 bytes}}；機器 cache：{{lscpu 的 L1d/L2/L3}}。
請分析存取模式（stride、是否 pointer chasing、每個 cache line 用到多少 bytes），
提出 1～3 種改寫（迴圈交換 / 分塊 / SoA / 欄位重排 / 預先排序），每種附預期收益（數量級）、風險、要驗證的邊界情況。
限制：{{不能改的介面或檔案}}。
```

### 15.4 I/O 加速

```
輸入格式：{{貼題目的輸入規格}}；輸出格式：{{貼輸出規格}}；是否互動題：{{是 / 否}}。
目前用 {{scanf/printf / cin/cout}}，資料量約 {{行數 / MB}}。
請寫一組 fread 緩衝讀取 + 自寫整數（{{有無負數 / 是否有浮點}}）解析 + 輸出緩衝 fwrite 的函式，
處理 EOF、負數、INT_MIN、行尾 \r\n，並提醒我程式結束前要 flush 的地方。浮點數請用 strtod，不要自己解析。
```

### 15.5 解讀量測結果

```
改動：{{描述}}。編譯旗標：{{...}}。
改前：{{時間 min/median，perf stat 的 IPC / cache-misses / branch-misses（若有）}}
改後：{{同上}}
輸出比對：{{cmp 結果}}
這個變化合理嗎？若沒變快或變慢，最可能的三個原因是什麼？各設計一個小實驗區分它們。
```
