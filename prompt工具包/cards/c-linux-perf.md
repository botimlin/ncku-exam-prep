# 貼上卡：C / Linux 效能優化
> 用法：一次只複製一張卡（兩條分隔線之間），貼進對話，再在下面寫你的問題。每張 ≤ 1200 字元。
> 來源：full/domain/c-linux-perf.md、lite/domain/c-linux-perf.md（詳細版）｜最後更新 2026-11

---

【參考卡｜C/Linux 效能 1/8｜熱點模式 → 修法（演算法、記憶體、I/O）】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
情境：Linux 主機或容器（x86-64 / aarch64）上的 C 程式，GCC 13（Ubuntu 24.04）。先改演算法，再改記憶體存取，再改 I/O，最後才是微調。收益為約略值。
| 熱點模式 | 修法 | 收益 / 風險 |
|---|---|---|
| 巢狀迴圈 O(n²) 搜尋 / 比對 | 排序+二分、hash、前綴和、雙指標 | 數十～數千倍；要重新驗證 |
| 內層迴圈沿「列」走 2D 陣列（a[i][j] 內層變 i） | 迴圈交換讓內層走 j（C 是 row-major）；矩陣乘 ijk→ikj | 本機實測 -O2 約 11 倍；風險低 |
| 分塊（tiling） | 要實測，BS 試 32/64/128 | 本機 N=1024 沒贏過 ikj |
| 大量 scanf/printf | fread 大區塊+自寫解析；輸出 buffer+一次 fwrite | 本機實測約 4 倍；忘記 flush 會漏輸出 |
| 每行 fflush / 寫 stderr / endl | 移除（非互動題） | 互動題必須保留 fflush |
| 熱迴圈 malloc/free | 外提、重複使用、arena | 小～數倍 |
| 鏈結串列 / 指標樹 | 陣列+索引、連續配置 | 數倍；改動大 |
| AoS 只用一兩個欄位 | SoA 或熱冷欄位分離 | 1.5～4 倍 |
| struct padding 多的大陣列 | 欄位由大到小排（{char,double,char,int} 24B→16B） | 介面固定時不能改 |
| `for (i < strlen(s))` | 先算一次長度 | O(n²)→O(n) |
| 大量小 write/read | 緩衝批次（syscall 約 300–400 ns/次） | 注意 flush 時機 |
| 每輪重新配置大 buffer | 重複使用（首觸 4KB 頁約 1–2 µs） | 小～中 |

---

【參考卡｜C/Linux 效能 2/8｜熱點模式 → 修法（CPU、編譯器、系統）】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
情境：Linux 容器內 C 程式，GCC 13。改之前先看組語（gcc -O2 -S）：-O2 常已做 cmov、除以常數變乘法、不變量外提。
| 熱點模式 | 修法 | 風險 |
|---|---|---|
| 迴圈內除 / 取餘「變數」（div 約 10–90 cycles） | 外提、改計數器、2 的冪+遮罩 | 浮點倒數乘法會改結果 |
| `s += a[i]` 相依鏈 | 整數用 4 個累加器+處理尾端 | 浮點會改結果 |
| 隨機資料的 if | 先看組語有無 cmov(x86)/csel(arm)；再試無分支/查表 | -O2 常已轉好 |
| 熱迴圈沒向量化 | restrict、inline、去掉 break 與函式呼叫 | restrict 騙編譯器=UB |
| 跨 .c 檔的小函式在熱迴圈 | 移到 header 做 static inline，或 -flto | 低 |
| qsort 大量整數 | 自寫排序 / radix / C++ std::sort | 穩定性需求 |
| 重複計算相同結果 | 快取 / 查表 / 預先計算 | 記憶體 |
| 多執行緒寫相鄰計數器 | 區域累加、padding 64B（false sharing） | — |
| 執行緒數 = nproc 但容器配額更少 | 依 /sys/fs/cgroup/cpu.max 決定 | — |
| -O0 編譯 | 確認 judge 旗標；能改才改 -O2 | judge 旗標固定時無效 |
| 用 double 算整數問題 | 改整數運算 | 溢位 |
| pow(x,2)、sqrt 比距離 | x*x；比平方距離 | 精度極少不同 |
| 大型 switch / strcmp 分派 | 預先轉整數 id / hash / 查表 | — |
規則：一次改一處 → cmp 比對輸出 → 量時間 → 記錄。

---

【參考卡｜C/Linux 效能 3/8｜開工偵查：工具能不能用（perf 多半被擋）】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
情境：考場 Linux 容器（如 ros:jazzy-ros-core = Ubuntu 24.04，GCC 13），不可安裝軟體、不可改系統設定。
- 先看 judge 怎麼編譯（Makefile / CMakeLists / CI 檔）。旗標固定時只能改原始碼。
- 偵查：`uname -m`、`gcc --version`、`lscpu`、`nproc`、`cat /sys/fs/cgroup/cpu.max`、`cat /proc/sys/kernel/perf_event_paranoid`、`command -v perf valgrind gprof strace`。
- perf 常不能用：Ubuntu 實測預設 perf_event_paranoid=4（一般使用者 perf stat 出現 No supported events found）；Docker 預設 seccomp 擋 perf_event_open；VM 內硬體事件可能 <not supported>。不能改 sysctl → 改用 gprof 或 clock_gettime 手動計時。
- gprof：`gcc -O2 -pg`（編譯與連結都要），程式正常結束才寫 gmon.out，`gprof -b ./prog gmon.out`。被 inline 的函式看不到。
- valgrind 多半沒裝；有的話 `valgrind --tool=callgrind` 慢數十倍，用小輸入。
- `/usr/bin/time -v ./prog`（要完整路徑，bash 內建 time 不支援 -v）：Max RSS、page faults、context switches。
- 沒工具時：分段插 clock_gettime 計時印到 stderr；把輸入放大 N、2N、4N 看成長比例；gdb 執行中 Ctrl-C 數次看 bt。
- 容器 CPU：nproc 不一定看 cgroup 配額（coreutils 9.8 前不看）。cpu.max "150000 100000" ≈ 1.5 顆；"max 100000" = 不限。
- judge 若量 CPU 時間（user+sys），多執行緒不會讓分數變快。

---

【參考卡｜C/Linux 效能 4/8｜計時 harness（暖機 + 11 次取 min/median）】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
情境：Linux 容器，perf 不能用時手動量測。結果印 stderr，不污染評分輸出。
```c
#define _POSIX_C_SOURCE 200809L
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
static inline double now_ns(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec * 1e9 + (double)ts.tv_nsec;
}
static volatile long long g_sink;              /* 防止結果沒用到被刪掉 */
#define KEEP(x) (g_sink = (long long)(x))
static int cmp_d(const void *a, const void *b) {
    double x = *(const double *)a, y = *(const double *)b;
    return (x > y) - (x < y);
}
#define REPS 11
void bench(const char *name, void (*fn)(void)) {
    double t[REPS];
    fn();                                      /* 暖機 */
    for (int r = 0; r < REPS; r++) {
        double t0 = now_ns();
        fn();
        t[r] = now_ns() - t0;
    }
    qsort(t, REPS, sizeof t[0], cmp_d);
    fprintf(stderr, "%-12s min %.3f ms  median %.3f ms\n",
            name, t[0] / 1e6, t[REPS / 2] / 1e6);
}
```
- min 用來比較兩版；min 和 median 差很多 = 環境吵。量到 0 秒 = 結果沒被使用而被刪。
- 整支程式：`/usr/bin/time -f "%e s %M KB" ./prog < in.txt > /dev/null` 跑 5 次；不用 -O0 量。

---

【參考卡｜C/Linux 效能 5/8｜編譯旗標與浮點結果不能變】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
情境：GCC 12+（Ubuntu 24.04 為 GCC 13），x86-64 / aarch64。
| 旗標 | 說明 / 風險 |
|---|---|
| -O0 | 不優化，慢 2–10 倍以上，絕不用來量 |
| -O2 | 最常見 judge 設定；GCC 12+ 含 very-cheap 向量化 |
| -O3 | 更積極（向量化 cost model dynamic）；偶爾更慢，要量 |
| -Ofast | -O3 + -ffast-math，可能改浮點結果 |
| -march=native | 用編譯機全部指令集；judge 機器可能 SIGILL |
| -mtune=native | 只調排程，可攜 |
| -flto | 編譯與連結都要加；多檔才有意義 |
| -fprofile-generate → 跑 → -fprofile-use | PGO；judge 自己重編時無效 |
| -fno-omit-frame-pointer -g | perf 呼叫鏈需要；-g 不改機器碼 |
| -ffp-contract=off | 禁止 FMA 收縮，保持浮點結果一致 |
浮點（exact-output judge 禁區）：
- -ffast-math / -Ofast、重排加法、浮點多累加器、乘倒數取代除法、float↔double 互換，都可能改輸出位元。
- GNU 模式（預設 -std=gnu17）預設 -ffp-contract=fast：有 FMA 時（aarch64 一律有；x86 需 -mfma / x86-64-v3 / native）a*b+c 可能合成 FMA，末位不同 → 加 -ffp-contract=off。
- -O3 浮點歸約仍依序加，結果不變。
看產出：`gcc -O2 -S -fverbose-asm x.c`、`objdump -d -M intel prog`、`gcc -O2 -Q --help=optimizers | grep enabled`。旗標沒生效：`make -n` 看實際指令、`make clean`。

---

【參考卡｜C/Linux 效能 6/8｜向量化：-O2 vs -O3、報告、阻礙、可攜】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
情境：GCC 13 x86-64 本機實測（aarch64 NEON 為 ARMv8-A 必備）。
- -O2（GCC 12 起）只做 very-cheap 向量化：需要執行期別名/對齊檢查就不做。`D[i]=A[i]+B[i]` 次數常數 1024 → -O2 會；次數 n 未知+指標參數 → -O2 不會，-O3 會。
- float 內積 `s += a[i]*b[i]` 在 -O3：乘法向量化、加法仍依序（結果相同）；加 -ffast-math 才全向量化（結果可能變）。
- 報告：`gcc -O3 -c hot.c -fopt-info-vec-optimized`（成功），`-fopt-info-vec-missed`（原因）。16 byte vectors = SSE/NEON，-mavx2 才 32 byte。
| missed 原因 | 修法 |
|---|---|
| possible aliasing / versioned | restrict（確定不重疊才加）、區域陣列、#pragma GCC ivdep |
| 迴圈內函式呼叫 | inline、移出迴圈 |
| 次數不可數、迴圈內 break | 先算次數；提早結束移到外面 |
| control flow in loop | 條件運算式 / 遮罩 |
| 真相依 a[i]=a[i-1]+x | 改演算法，否則不能 |
| 間接索引、大 stride | SoA |
| 混合型別 | 統一寬度 |
- -march=native 可能在 judge SIGILL。可攜做法：`__builtin_cpu_supports("avx2")` 選 `__attribute__((target("avx2")))` 版本，或 `__attribute__((target_clones("avx2","default")))`。
- 可攜 SIMD：`typedef float v4sf __attribute__((vector_size(16)));`，未對齊資料用 memcpy 載入。
- judge 用 -O2 時：讓迴圈變簡單（restrict、常數次數、手動多累加器）。

---

【參考卡｜C/Linux 效能 7/8｜快速輸入：fread 64KB + 自寫 read_int】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
情境：Linux 容器內 C 程式，judge 大量輸入。本機實測 500 萬整數：scanf+printf 0.57 s → fread/fwrite 自寫 0.14 s，輸出 cmp 相同。
```c
#include <stdio.h>
static char ibuf[1 << 16];
static size_t ilen = 0, ipos = 0;
static inline int gc(void) {           /* 下一個字元，EOF 回傳 -1 */
    if (ipos == ilen) {
        ilen = fread(ibuf, 1, sizeof ibuf, stdin);
        ipos = 0;
        if (ilen == 0) return -1;
    }
    return (unsigned char)ibuf[ipos++];
}
static int read_int(int *out) {        /* 成功 1，EOF 0 */
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
- 只處理十進位整數；`+5`、科學記號會錯 → 先看規格。浮點用 strtod，不要自寫。
- 單執行緒可用 getchar_unlocked()。
- mmap+MADV_SEQUENTIAL 只適用一般檔案；stdin 是管線會失敗，要留 fread 備案。收益通常不大。

---

【參考卡｜C/Linux 效能 8/8｜快速輸出與 stdio 緩衝】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
情境：Linux 容器內 C 程式大量輸出。
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
/* main 結束前一定要 flush_out()！忘記 = 輸出不完整 */
```
- stdout 接檔案/管線 = 完全緩衝；接終端 = 行緩衝；stderr 不緩衝（大量寫 stderr 很慢）。
- 加大緩衝：`static char outbuf[1 << 20]; setvbuf(stdout, outbuf, _IOFBF, sizeof outbuf);` 必須在第一次輸出前呼叫。
- 互動題必須每次輸出後 fflush(stdout)，否則卡住。
- `_exit()` 不 flush stdio。
- C++：`std::ios::sync_with_stdio(false); std::cin.tie(nullptr);`，用 '\n' 不用 std::endl，之後不混用 printf 與 cout。
- 量測要和 judge 一樣的輸出接法（> /dev/null 與寫檔成本不同）。
