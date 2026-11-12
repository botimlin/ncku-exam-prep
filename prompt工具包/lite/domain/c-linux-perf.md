# C / Linux 效能優化速查（備援包）

> 用途：備援，容器內 C 程式變快。流程見 03-optimize.md；多執行緒見 multicore-sync.md。適用 GCC 12+（Ubuntu 24.04=GCC 13）、x86-64/aarch64。
> 來源：gcc.gnu.org/onlinedocs、man7.org（perf、setvbuf、mmap）、kernel cgroup-v2、Agner Fog。最後更新 2026-11。倍數為本機實測（Zen 3、GCC 13）僅供參考。

## 先做
- 看 judge 編譯指令/旗標、量牆鐘或 CPU 時間；旗標固定就只改原始碼。
- `which perf valgrind gprof strace`；不能安裝。perf 常被擋（`perf_event_paranoid`>2，Ubuntu 預設 4；Docker seccomp）→ `clock_gettime(CLOCK_MONOTONIC)` 分段計時：暖機 1 次、跑 11 次取 min/median，印 stderr；結果要用掉（volatile sink）。
- `/usr/bin/time -v`：Max RSS、page faults、context switches。
- `nproc` 不一定看 cgroup 配額（coreutils 9.8 前）→ `cat /sys/fs/cgroup/cpu.max`（"150000 100000"≈1.5 核）。

## 工具
- `perf stat -e cycles,instructions,cache-misses,branch-misses`；IPC<1 多半等記憶體。
- `gcc -O2 -g -fno-omit-frame-pointer` → `perf record -g` → `perf report --stdio --no-children` → `perf annotate --stdio -s f`
- gprof：編譯連結 `-pg`，正常結束產生 gmon.out，`gprof -b ./p gmon.out`
- `valgrind --tool=callgrind` + `callgrind_annotate`（慢數十倍）

## 數量級（約略）
| 項目 | 延遲 |
|---|---|
| L1/L2/L3 | ~4 / ~14 / ~40–70 cycles |
| DRAM | ~60–120 ns |
| 分支失誤 | ~15–20 cycles |
| div r32 / r64 | ~10–26 / 最多 ~90（舊 CPU） |
| FP add/mul | ~4 lat，2/cycle |
| syscall | ~300 ns；首觸 4K 頁 ~1–2 µs |

## 熱點 → 修法
| 熱點 | 修法 |
|---|---|
| O(n²) | 排序+二分、hash、前綴和 |
| 內層沿列走 2D 陣列 | 迴圈交換 ijk→ikj（-O2 約 11 倍）；分塊要實測（本機 N=1024 沒贏） |
| scanf/printf 大量 | fread 64KB+自寫解析、buffer+fwrite（約 4 倍）；結束前 flush |
| 每行 fflush/stderr/endl | 移除（互動題要保留 fflush） |
| 熱迴圈 malloc | 外提、重用、arena |
| 鏈結串列 | 陣列+索引 |
| AoS 只用少數欄位 | SoA |
| struct padding | 欄位由大到小（{char,double,char,int}=24→16） |
| `i<strlen(s)` | 先算長度 |
| 迴圈內除變數 | 外提、計數器、2 的冪+遮罩 |
| `s+=a[i]` 相依鏈 | 整數多累加器 |
| 隨機 if | 先看組語 cmov/csel（-O2 常已做） |
| 沒向量化 | `restrict`、inline、去掉 break/呼叫 |
| 跨檔小函式 | static inline 或 -flto |
| 執行緒>配額 | 依 cpu.max |

## 向量化
- -O2（GCC12+）只做 very-cheap：本機 n 未知不向量化；-O3 會。
- `-fopt-info-vec-optimized` / `-fopt-info-vec-missed`
- 向量擴充：`typedef float v4sf __attribute__((vector_size(16)));`，未對齊用 memcpy 載入。
- x86 `<immintrin.h>` `_mm256_loadu_si256/_mm256_add_epi32`（-mavx2）；ARM `<arm_neon.h>` `vld1q_f32/vaddq_f32/vst1q_f32`。
- `-march=native` 可能在 judge SIGILL；可攜用 `__builtin_cpu_supports("avx2")`+`target("avx2")`。

## 浮點（exact judge 禁區）
- `-ffast-math`/`-Ofast`、重排、多累加器、倒數乘法都會改位元。
- GNU 模式預設 `-ffp-contract=fast`：有 FMA 時（aarch64、-march=native）結果可能變 → `-ffp-contract=off`。
- -O3 浮點歸約仍依序加（結果不變）。

## 旗標
-O0 不要拿來量；-O2 常見；-O3 要量；-flto 編譯+連結都加；PGO `-fprofile-generate`→跑→`-fprofile-use`；看組語 `gcc -O2 -S -fverbose-asm`、`objdump -d -M intel`；`gcc -O2 -Q --help=optimizers`。

## I/O / 系統
- stdout 接檔案/管線=全緩衝，終端=行緩衝，stderr 無緩衝。`setvbuf(stdout,buf,_IOFBF,1<<20)` 要在第一次輸出前呼叫。
- 浮點輸入用 `strtod`，不要自寫。大檔可 `mmap`+`MADV_SEQUENTIAL`（stdin 是管線會失敗，留 fread 備案）。
- 大 buffer 重複使用，避免每輪 malloc/free（page fault）。
- `strace -c` 看 syscall 次數（若有）。

## 其他
- `restrict` 騙編譯器=UB；型別轉換用 memcpy 不用指標 cast。
- `__builtin_expect` 只排程式碼；`__builtin_prefetch(p,0,1)` 只對間接/不規則存取。
- `aligned_alloc(64,size)`（size 湊倍數）。
- C++：`sync_with_stdio(false)`、`cin.tie(nullptr)`、`'\n'`、`reserve`、`std::sort`>qsort。
- 每改一處：`cmp` 輸出、量時間、commit。
