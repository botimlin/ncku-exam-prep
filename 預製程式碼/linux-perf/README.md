# linux-perf/ — 電腦端效能優化模板

| 檔案 | 用途 |
|---|---|
| `bench.h` | 計時：`now_ns()`、`BENCH(名稱, 次數, 程式碼)`（取最快一次）、`do_not_optimize(x)`。**要放第一個 #include** |
| `parallel_template.c` | pthread「切塊 → 各算各的 → 合併」，對比 mutex / spinlock / atomic / 不加鎖 / false sharing |
| `pipeline_template.c` | 生產者/消費者 ring buffer（mutex+condvar、SPSC 無鎖、SPSC 批次）＝「一核收、一核算」|

```bash
B=/tmp/t; mkdir -p $B
gcc -O2 -Wall -Wextra -std=c11 -pthread parallel_template.c -o $B/par && $B/par 4   # 參數 = 執行緒數
gcc -O2 -Wall -Wextra -std=c11 -pthread pipeline_template.c -o $B/pipe && $B/pipe
```
要改：`work()`（每個元素做什麼）、`N`、`produce()/compute()`、`item_t`，都標了 `TODO(改這裡)`。

## 實測（2026-11-11，AMD Ryzen 5 5600 6 核 12 緒，gcc 13.3 `-O2`）

結果全部正確（racy 版答案錯是故意的）；`pipeline_template.c` 也用 ThreadSanitizer 跑過，沒有 data race 警告。

### parallel_template（N = 8M，T = 4）
| 寫法 | 時間 | 加速 |
|---|---|---|
| serial | 45.9 ms | 1x |
| **local（區域變數累加，最後合併）** | **11.6 ms** | **3.95x** |
| mutex 每個元素 lock | 203.7 ms | 0.23x（比單執行緒還慢 4 倍）|
| spinlock 每個元素 | 374.9 ms | 0.12x |
| atomic 每個元素 | 86.9 ms | 0.53x |
| racy 不加鎖 | 43.2 ms | **答案錯**（lost update）|
| false sharing（相鄰格子）| 42.2 ms | 1.09x（4 核等於沒用）|
| padded 每格 64 bytes | 12.2 ms | 3.75x |

T=1/2/4/8 時 local 的加速 = 1.00x / 1.99x / 3.75x / 5.36x。

### pipeline_template（1M 筆，「收」和「算」成本差不多）
| 寫法 | 時間 | 加速 |
|---|---|---|
| serial（收一筆算一筆）| 183.0 ms | 1x |
| A mutex+condvar | 199.8 ms | 0.92x（鎖的成本吃掉並行的好處）|
| B SPSC 無鎖 | 122.0 ms | 1.50x |
| **C SPSC 無鎖 + 批次 64** | **107.9 ms** | **1.70x**（理論上限約 2x）|

### 一個意外的教訓：編譯器自動向量化
同樣的 `work()` 迴圈，寫在 `main` 裡、`N` 是常數時，gcc 自動用 SIMD，單執行緒只要 12 ms（比 thread 函式裡的 46 ms 快 4 倍）。`-O3 -march=native` 後 serial 變 6.7 ms、4 執行緒 1.8 ms。
→ **先把單執行緒版本優化好（編譯選項、資料排列），再談平行化**；比較時兩邊要用同一個函式才公平（模板已經這樣做）。

## 優化檢查清單（照順序做）

1. **先量測，不要猜**：`BENCH(...)` 包住可疑的地方；`time ./prog` 看 real/user/sys。只優化最花時間的部分。
2. **編譯選項**：`-O2` → `-O3` → `-O3 -march=native`（開 SIMD/popcnt；SHA-256 從 35 ms 變 15 ms）。MCU 端：`-O2` 或 `-O3`，RISC-V 加 `_zbb`。
3. **熱迴圈裡不要有鎖/原子操作**：各算各的，最後合併一次（`parallel_template` local 版）。臨界區要短：計算放鎖外面，鎖內只做 `sum += v`。
4. **批次處理（batch）**：一次傳/處理很多筆，固定開銷（鎖、系統呼叫、通訊封包頭、ROS2 訊息）攤平。上一屆加速的關鍵之一就是二進位批次傳輸，而不是一筆一筆傳文字。
5. **cache 友善的資料排列**：連續存取陣列；每個執行緒寫的變數分開 64 bytes（避免 false sharing）；struct of arrays。
6. **查表（lookup table）**：CRC 從逐位元 → 查表 → slice-by-4 快 12 倍（見 `../algo`）。
7. **強度削減（strength reduction）**：`x % 256` → `x & 255`；`x / 8` → `x >> 3`；除法/取 mod 延後做（Adler-32 每 5552 byte 才 mod 一次）。
8. **迴圈展開（unrolling）**：一次處理 4 個/8 個，讓 CPU 同時算互不相依的工作（slice-by-4 就是這概念）。`-O3` 或 `#pragma GCC unroll 4`。
9. **`restrict`**：`void f(uint32_t *restrict dst, const uint32_t *restrict src)` 告訴編譯器兩個指標不重疊 → 才敢向量化。
10. **演算法本身**：O(n²) → O(n log n) → O(n)（insertion → merge → radix）。

## 量測工具

```bash
time ./prog                              # real = 牆上時間；user+sys > real 代表有平行
perf stat ./prog                         # cycles、instructions、IPC、cache-misses、branch-misses
perf stat -e cache-misses,cache-references ./prog
perf record -g ./prog && perf report     # 哪個函式最花時間（-g 含呼叫鏈）
valgrind --tool=callgrind ./prog && callgrind_annotate callgrind.out.*   # 指令數精確到每一行（慢 50 倍）
gcc -O2 -pg prog.c -o prog && ./prog && gprof ./prog gmon.out | head -30 # gprof：不需權限
```
- `perf` 若出現 `perf_event_paranoid` 權限錯誤：需要 `sudo sysctl kernel.perf_event_paranoid=1`（考場電腦要先問監考能否使用；這台電腦目前是 4，我沒有改）。
- 編譯時加 `-g` 才看得到原始碼行號；量測要用 `-O2`，不要用 `-O0`。

## 模板 ↔ 檢查清單

| 模板 | 示範的優化 |
|---|---|
| `parallel_template.c` local | #3 熱迴圈無鎖、資料平行切塊 |
| `parallel_template.c` padded | #5 false sharing → `_Alignas(64)` |
| `parallel_template.c` mutex/spin/atomic | #3 反例：鎖粒度太細 |
| `pipeline_template.c` B/C | #4 批次、無鎖 SPSC（acquire/release）、一核收一核算 |
| `bench.h` | #1 量測（取最小值、防止被優化掉）|
| `../algo/crc32.c`、`sort.c`、`bnn.c` | #6 查表、#8 展開、#10 演算法、硬體 popcount |
