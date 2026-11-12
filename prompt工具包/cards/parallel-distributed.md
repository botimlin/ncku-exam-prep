# 貼上卡：平行與分散式計算
> 用法：一次只複製一張卡（兩條分隔線之間），貼進對話，再在下面寫你的問題。每張 ≤ 1200 字元。
> 來源：full/domain/parallel-distributed.md、lite/domain/parallel-distributed.md（詳細版）｜最後更新 2026-11

---

【參考卡｜平行 1/8｜決策：值不值得平行化】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
情境：Linux 容器（Ubuntu 24.04、GCC 13）上的 C 程式，judge 量執行時間。
步驟：
1. 可用核心：`nproc`；`cat /sys/fs/cgroup/cpu.max`（"quota period"，max = 不限）。容器用 quota 限制時 nproc 可能仍顯示全部核心 → 手動設執行緒數。
2. judge 量 wall time 還是 CPU time？（⚠️考場規則未知）量 CPU time 時平行化不會變快，忙等更差。
3. 量 serial 版：p = 熱點時間 / 總時間。Amdahl 上限 1/(1−p)。
4. 每份工作要遠大於 parallel region 啟動 + barrier（微秒級，⚠️自己量），至少大兩個數量級。
5. 迴圈第 i 次用到第 i−1 次結果 → 不能直接 parallel for（scan、wavefront 或改演算法）。
6. 驗證：輸出與 serial 逐位元相同，多次執行一致。
| 觀察 | 結論 |
|---|---|
| nproc=1 或 judge 限 1 核 | 不平行；改演算法、cache、I/O |
| 熱點是 I/O | 批次 I/O、緩衝、I/O 與計算重疊，不是加運算執行緒 |
| 熱點是記憶體頻寬（每 byte 一兩個運算） | 多核收益有限 |
| 獨立大量運算 | 資料平行，接近線性 |
| 共享累加 | 歸約：各自累加、最後合併 |
Amdahl S = 1/((1−p)+p/N)：p=0.9 時 N=4 → 3.08、N=8 → 4.71、N=∞ → 10；p=0.5 時無限核心也只有 2 倍。
Karp–Flatt e = (1/S − 1/N)/(1 − 1/N)：N 變大 e 不變 → 瓶頸是序列部分；e 變大 → 開銷（同步、通訊、不平衡）在成長。
加速比基準 T1 用最佳 serial 版，不是平行版開 1 執行緒。

---

【參考卡｜平行 2/8｜分解模式與分割方式】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
| 模式 | 適用 | 主要風險 |
|---|---|---|
| 資料平行 map | 陣列、影像、多筆獨立測資 | 記憶體頻寬、不平衡 |
| 歸約 reduction | sum/max/直方圖 | 共享累加變數 race、競爭 |
| Scan / prefix sum | 壓縮、分配位置 | 兩趟 block scan 可平行 |
| 流水線 pipeline | 串流、感測→處理→輸出、ROS 2 node 鏈 | 最慢 stage、佇列成長 |
| fork–join tasks | 分治、遞迴 | 任務太小 → 要 cutoff |
| master–worker 工作佇列 | 工作大小不一 | 佇列成為熱點 |
| stencil + halo | 影像濾波、Jacobi | 邊界交換、每步同步 |
| embarrassingly parallel | 參數掃描、Monte Carlo | 種子、輸出順序 |
歸約三種寫法：每次 critical（幾乎一定比 serial 慢）< 每次 atomic（同一 cache line 在核心間彈跳，常仍比 serial 慢）< 每執行緒區域累加、結尾合併一次（正解）。
分割（T 個執行緒，第 t 個）：
| 分割 | 範圍 | OpenMP |
|---|---|---|
| Block | `[n*t/T, n*(t+1)/T)`（先乘再除，n 大用 long long） | schedule(static) |
| Cyclic | i = t, t+T, … | schedule(static,1) |
| Dynamic | 誰閒誰拿 B 個 | schedule(dynamic,B) |
| Guided | 大塊漸小 | schedule(guided,B) |
- 本機實測三角形負載（成本 ∝ i，8 緒）：static 0.42 s、static,1 0.29 s、dynamic,64 0.26 s；成本均勻時 static 開銷最小。
- 粒度：任務數 ≈ 核心數 × 4–16，每任務至少數十微秒（⚠️經驗值）。多筆大小不同的工作：大的先排。

---

【參考卡｜平行 3/8｜OpenMP 基礎：編譯、parallel for、schedule、變數共享】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
情境：Ubuntu 24.04 GCC 13（libgomp）。
- 編譯與連結都要 `gcc -O2 -fopenmp`；`OMP_NUM_THREADS=4 ./x`。沒加 -fopenmp 時 pragma 被忽略、單執行緒跑（-Wall 出現 -Wunknown-pragmas）；omp_* 呼叫會連結失敗 → 用 `#ifdef _OPENMP`。
- GCC 13 的 _OPENMP = 201511（4.5）；masked、陣列區段 reduction、taskloop、parallel for simd 實測可用。
- 裝了 gcc 就有 omp.h（libgcc-13-dev 依賴 libgomp1）；⚠️未在考場容器實測，先試編。
```c
#pragma omp parallel for schedule(static) num_threads(4) if(n > 10000)
for (long i = 0; i < n; i++) out[i] = f(in[i]);
```
- if(expr) 為假 → 單執行緒，小輸入不平行。迴圈內不能 break（可 continue）。
- schedule：static 不給 chunk = 等長連續塊；dynamic 不給 chunk 預設 1（太小，試 16–1024）；guided 漸小；runtime 讀 OMP_SCHEDULE（libgomp 未設定時 dynamic,1）；沒寫 schedule 時 GCC 13 實測展開成 static。
- 第一個 parallel region 付建立執行緒成本 → 先熱身再計時。
變數共享：
- private 未初始化；firstprivate 複製初值；lastprivate 取序列上最後一次迭代的值。
- 建議 `default(none)`，強迫每個變數明確標示。
- C 經典 bug：內層迴圈變數宣告在 parallel 外面 = shared → race。
```c
#pragma omp parallel for        // 對：在迴圈內宣告
for (int i = 0; i < n; i++)
    for (int j = 0; j < m; j++) a[i][j] = 0;
```

---

【參考卡｜平行 4/8｜OpenMP：reduction、同步、tasks、環境變數】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
情境：GCC 13 libgomp。
```c
#pragma omp parallel for reduction(+:s) reduction(max:mx)
for (long i = 0; i < n; i++) { s += a[i]; if (b[i] > mx) mx = b[i]; }
#pragma omp parallel for reduction(+:hist[:256])   // 陣列區段 reduction（GCC 13 實測可用）
for (long i = 0; i < n; i++) hist[data[i]]++;
```
- 合併順序未指定 → 浮點總和隨執行緒數改變。陣列 reduction 每執行緒一份完整副本（大陣列可能爆 stack → 放 heap、OMP_STACKSIZE）。
| 構造 | 注意 |
|---|---|
| critical | 重；沒名字的全部共用一把鎖 |
| atomic | 單一位置 x++ / x += expr，比 critical 輕 |
| barrier | 不能放在只有部分執行緒會走到的分支（deadlock） |
| nowait | 去掉 for/single 結尾隱含 barrier；後面要用結果就不能加 |
| single | 任一執行緒執行，結尾有 barrier |
| masked / master | 只 thread 0，沒有 barrier |
| ordered | 依迭代順序，會序列化那段 |
- collapse(2)：完美巢狀矩形迴圈合併，外層很小時有用。`parallel for simd`：執行緒 + 向量化。
- tasks：`#pragma omp parallel` + `#pragma omp single` 產生根任務；`task shared(a)` 寫回結果；`taskwait` 等直接子任務。沒有 cutoff（如 n < 20 改 serial）會比 serial 慢很多。
- API：omp_get_wtime、omp_get_thread_num、omp_get_num_threads、omp_get_max_threads（配置 per-thread 陣列用）。
- 環境變數：OMP_NUM_THREADS、OMP_PROC_BIND、OMP_PLACES、OMP_DISPLAY_ENV=true（確認生效）。巢狀預設只 1 層 active。超額訂閱時用 OMP_WAIT_POLICY=PASSIVE。

---

【參考卡｜平行 5/8｜OpenMP 直方圖實測：熱迴圈內不要同步】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
本機實測（x86-64、GCC 13.3、-O2 -fopenmp、N=2^26 bytes、256 bins；只看相對關係）：
| 版本 | 1 緒 | 4 緒 | 12 緒 |
|---|---|---|---|
| serial | 0.018 s | — | — |
| 每次 atomic | 0.125 | 0.399 | 0.191 |
| 每次 critical | 0.274 | 4.3 | 12.1 |
| per-thread local + 合併 | 0.018 | 0.005 | 0.004 |
| reduction(+:h[:NB]) | 0.032 | 0.008 | 0.006 |
所有版本結果與 serial 完全相同（整數加法）。
per-thread 寫法：
```c
#pragma omp parallel
{
    long local[NB] = {0};                 // region 內宣告 → private
    #pragma omp for nowait                // 合併不需等別人做完迴圈
    for (long i = 0; i < N; i++) local[data[i]]++;
    for (int b = 0; b < NB; b++) {
        #pragma omp atomic
        h_local[b] += local[b];
    }
}                                         // region 結尾隱含 barrier
```
- bin 很多（如 2^20）：副本放 heap `calloc(T*NB)`，T = omp_get_max_threads()。
- `long part[T][NB]` 且 NB 很小：相鄰執行緒同一 cache line → false sharing；每列補到 64 bytes 倍數，或改區域變數累加。
- 計時用 omp_get_wtime()，印到 stderr。

---

【參考卡｜平行 6/8｜確定性輸出：平行版和 serial 一模一樣】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
judge 用 diff 比對輸出時必看。
| 問題 | 修法 |
|---|---|
| 輸出行順序隨機 | 平行計算 → 存 out[i] → 序列依 i 輸出（或 ordered，會序列化） |
| stdout 交錯、半行 | 只讓一個執行緒 / rank 0 輸出 |
| 浮點總和末位不同 | 固定大小分塊（與執行緒數無關），各塊存 part[b]，依 b 順序加總 |
| 整數偶爾錯 | data race → reduction / per-thread partial |
| 隨機數不同 | 每個「工作項」用由索引推導的種子；rand() 改 rand_r |
| hash map 合併順序不同 | 合併後排序再輸出 |
| 計時混進 stdout | 計時印 stderr |
```c
#define B 4096                                      // 固定塊大小，與執行緒數無關
long nb = (n + B - 1) / B;
double *part = malloc(nb * sizeof *part);
#pragma omp parallel for schedule(static)
for (long b = 0; b < nb; b++) {
    double s = 0;
    long hi = (b + 1) * B < n ? (b + 1) * B : n;
    for (long i = b * B; i < hi; i++) s += a[i];
    part[b] = s;
}
double total = 0;
for (long b = 0; b < nb; b++) total += part[b];    // 順序固定 → 結果固定
```
- 注意：與完全序列 `s += a[i]` 仍可能差末位；必須逐位元同 serial 參考時，serial 版也要用同樣分塊，或題目允許誤差。
- 多 process：fork 前 `fflush(stdout)`；子 process 把結果寫到 `MAP_SHARED|MAP_ANONYMOUS` 的 res[k]，用 `_exit(0)` 結束；父 `while (wait(NULL) > 0) {}` 後依 k 輸出。

---

【參考卡｜平行 7/8｜常見 bug 與除錯步驟】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
情境：Linux 上 OpenMP / pthread / 多 process 程式。
| 症狀 | 原因 | 修法 |
|---|---|---|
| 結果每次不同 / 偏小 | 共享累加沒 reduction、內層變數 shared | reduction；變數宣告在迴圈內；default(none) |
| 比 serial 慢 | 每次 critical/atomic、false sharing、工作太小、region 在熱迴圈內反覆進出 | per-thread partial；if(n>X)；parallel 移外層 |
| 加執行緒更慢 | 記憶體頻寬飽和、超額訂閱、忙等 | 減執行緒；OMP_WAIT_POLICY=PASSIVE |
| 卡住 CPU 0% | 鎖順序、barrier 在分支內、MPI 互相先 Send | 固定加鎖順序；MPI_Sendrecv |
| 卡住 CPU 100% | livelock / 忙等 | 改阻塞等待 |
| 只在平行版 segfault | 大區域陣列爆 stack | 放 heap；OMP_STACKSIZE |
| fork 後某些行出現兩次 | stdout 緩衝被複製 | fork 前 fflush；子 _exit |
| 第一個 region 特別慢 | 含建立執行緒 | 熱身 |
| rand/strtok/localtime 怪 | 非 thread-safe | rand_r、strtok_r、localtime_r |
超額訂閱：OpenMP 執行緒 × process 數 × ROS 2 MultiThreadedExecutor 要相乘，總數 ≤ 可用核心。
除錯順序：
1. OMP_NUM_THREADS=1 版與 serial 輸出完全相同。
2. 2、4、N 執行緒各跑 5 次 diff。
3. `gcc -fsanitize=thread -g -O1`（libgomp 可能誤報，看是否落在自己的變數；新核心配 `setarch -R`）。
4. region 內印 omp_get_num_threads() 確認真的多執行緒。
5. `time ./x`：user+sys ≈ real×N 表示有平行；real 沒降但 user 大增 → 忙等/競爭/超額訂閱。
6. 卡住：`gdb -p <pid>` → `thread apply all bt`。

---

【參考卡｜平行 8/8｜通訊成本、流水線、IPC、ROS 2】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
通訊 α–β 模型：T(n) = α + β·n（α 每則固定延遲，β = 1/頻寬）。
- k 則小訊息合成 1 則 → 省 (k−1)·α：批次化。
- 頻寬受限 → 二進位取代文字、較小型別、只傳差異。
- 例：UART 115200 baud 8N1 每 byte ≈ 86.8 µs，每筆 printf 20 字元 ≈ 1.7 ms → 輸出本身是瓶頸；MCU 先歸約、二進位批次。
流水線（k stage，每 stage t_i）：吞吐量 ≈ 1/max(t_i)；單筆延遲 = Σt_i；加速上限 = Σt_i / max(t_i) ≤ k。平衡做法：拆最慢 stage，或無狀態 stage 多個 worker。
Little's law L = λW。佇列持續成長 → 下游比上游慢。有界佇列 = backpressure。要低延遲 → 小批次、淺佇列、丟舊留新；要總時間短 → 大批次、深佇列。
IPC：
- pipe：Linux 預設容量 65536 bytes；≤ PIPE_BUF（4096）的 write 是原子的；read/write 可能只做部分 → 迴圈；不用的端要關，否則等不到 EOF。
- 共享記憶體：`shm_open("/name", O_CREAT|O_RDWR, 0600)` + ftruncate + mmap(MAP_SHARED)；glibc ≥ 2.34 不需 -lrt；要自己同步。
- MPI 考場多半沒裝（`which mpicc`）。
ROS 2（Jazzy）：
- 一個 process 一個 DDS participant → 同 process 多 node 較省；component container + `use_intra_process_comms:=true`（rclcpp only）省序列化。
- 逐段 `ros2 topic hz` 找頻率掉的 stage；`ros2 topic delay` 需要 header.stamp。
- topic 沒有端到端 backpressure；低延遲用 KEEP_LAST 小 depth；高頻小訊息改陣列批次。
