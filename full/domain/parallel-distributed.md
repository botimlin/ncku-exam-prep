# 平行與分散式計算：理論、分解模式、OpenMP / MPI / IPC、ROS 2 與 RP2350 + host

> 用途：**備援包**（考前 demo 沒有提到這個主題，學生特別要求）。當題目要求「設計 / 優化一個平行或分散式系統」時使用：判斷值不值得平行化、選分解模式、選工具（OpenMP、pthread、多 process、MPI、ROS 2 多 node、雙核 MCU + host），以及量測與除錯。可整份貼給考場 LLM 當參考資料。
> 與其他檔案的分工（本檔**不重複**以下內容，只引用）：
> - 鎖、mutex、spinlock、cond var、semaphore、C11 atomics、memory order、false sharing 基礎、SPSC ring buffer、deadlock、pico multicore / FIFO / spinlock / queue_t、兩核分工 → `domain/multicore-sync.md`
> - ROS 2 CLI、QoS policy 與相容性、executor / callback group、intra-process 程式寫法、環境變數 → `domain/ros2.md`
> - 通用優化流程、Amdahl 速算、量測方法 → `03-optimize.md`
> - DMA / PIO 細節 → `domain/pico-dma.md`、`domain/pio.md`；RP2350 總覽 → `domain/pico-sdk.md`
> - Python 效能（若工具包內有此檔）→ `domain/python-perf.md`
>
> 適用版本：Ubuntu 24.04（`ros:jazzy-ros-core` base）、GCC 13 / libgomp、glibc 2.39、OpenMP 4.5–5.x 子集、MPI 3.x/4.x 標準 C binding（Open MPI 5.0 文件）、ROS 2 Jazzy、RP2350 + pico-sdk 2.x。
> 來源（實際查閱）：
> - OpenMP 5.0 規格 Worksharing-Loop Construct：https://www.openmp.org/spec-html/5.0/openmpsu41.html
> - GCC libgomp 文件：https://gcc.gnu.org/onlinedocs/libgomp/Environment-Variables.html （以及 `OMP_SCHEDULE`、`OMP_NUM_THREADS`、`OMP_MAX_ACTIVE_LEVELS`、`OMP_PROC_BIND`、`OMP_WAIT_POLICY`、`Implementation-defined-ICV-Initialization`、`OpenMP-Implementation-Status` 各頁）
> - Open MPI 5.0 man pages：https://docs.open-mpi.org/en/v5.0.x/man-openmpi/man1/mpirun.1.html 、`man3/MPI_Scatter.3.html`、`MPI_Isend.3.html`、`MPI_Allreduce.3.html`
> - man7.org：`shm_open(3)`、`pipe(7)`
> - ROS 2 文件原始檔（jazzy 分支）：https://github.com/ros2/ros2_documentation/tree/jazzy/source （`Concepts/Intermediate/About-Composition.rst`、`Tutorials/Intermediate/Composition.rst`、`Concepts/Intermediate/About-Domain-ID.rst`）
> - ROS 2 設計文件：https://design.ros2.org/articles/Node_to_Participant_mapping.html
> - REP 2001：https://github.com/ros-infrastructure/rep/blob/master/rep-2001.rst ；ros2cli `ros2component/package.xml`（jazzy）
> - Python：https://docs.python.org/3/library/multiprocessing.html
> - 理論定義：Wikipedia「Analysis of parallel algorithms」「Gustafson's law」「Karp–Flatt metric」；Gustafson & Barsis, *Reevaluating Amdahl's Law*, CACM 31(5), 1988；Lamport, *Time, Clocks, and the Ordering of Events in a Distributed System*, CACM 1978
> - 本機實測（Ubuntu 24.04.5、GCC 13.3.0、12 執行緒 x86-64）：`_OPENMP`、`omp.h` 的套件歸屬、GCC 對無 schedule 子句迴圈的展開方式、本檔的 OpenMP / pthread 範例都編譯並執行過
> 最後更新：2026-11
>
> 給模型的說明：考場文件、題目規格、judge 規則與本檔衝突時，**以考場為準**。標 `⚠️未驗證` 的是推論或沒找到一手來源的內容。考場**不能安裝軟體**：OpenMP 隨 gcc 一起來（見 5.1），MPI 多半**沒有**，MPI 段落主要用於讀懂程式與概念題。

---

## 0. 一頁總結（先看這裡）

1. **先問值不值得**：量出可平行部分比例 p 與每份工作的大小。p 小、工作小（< 數十微秒）、或 judge 只給 1 核 → 不要平行化，先做演算法 / 記憶體優化（`03-optimize.md`）。
2. **加速上限**：Amdahl（固定問題大小）`S = 1/((1-p)+p/N)`；Gustafson（問題隨 N 放大）`S = N-(N-1)s`。實測後用 Karp–Flatt `e = (1/S - 1/N)/(1 - 1/N)` 反推「實際的序列比例」：e 隨 N 增加 → 開銷在變大（同步 / 通訊 / 不平衡）。
3. **Work / span**：`T_N ≥ max(T1/N, T∞)`，貪婪排程 `T_N ≤ T1/N + T∞`。關鍵路徑（span）太長時加核心沒用。
4. **最常用的四種模式**：資料平行（map）、歸約（各自累加最後合併）、流水線（吞吐量 = 最慢的 stage）、master–worker / 工作佇列（動態負載平衡）。
5. **共享記憶體首選 OpenMP**：`gcc -O2 -fopenmp`。`#pragma omp parallel for reduction(+:s) schedule(static)`。GCC 13 的 `_OPENMP = 201511`（OpenMP 4.5，再加上部分 5.x 功能）。
6. **頭號效能殺手**：每次迭代都進 `critical` / `atomic`、false sharing、太細的粒度、迴圈裡開執行緒。修法都一樣：**各自做一大塊，最後合併一次**。
7. **通訊成本模型** `T(n) = α + β·n`：小訊息被 α（固定延遲）主導 → **批次化**；大訊息被頻寬主導 → 減少資料量 / 零複製 / 與計算重疊。
8. **流水線**：吞吐量 = 1 / max(t_i)；延遲 = Σt_i + 排隊時間。Little's law `L = λW`：佇列裡平均有幾筆 = 到達率 × 平均停留時間。
9. **ROS 2 多 node = 分散式系統**：同 process 多 node 共用一個 DDS participant；同 process 加上 component container + intra-process 可省掉序列化；用 `ros2 topic hz` 逐段找頻率掉下來的那一個 stage。
10. **輸出順序要確定**：平行程式的 `printf` 順序不固定 → judge diff 失敗。把結果存進陣列，**平行計算、序列輸出**；浮點歸約順序不同會差最後幾位 → 固定分塊並依序合併。

---

## 1. 決策入口：值不值得平行化？

```
1. 有沒有多核可用？ nproc；cat /sys/fs/cgroup/cpu.max（cgroup v2：「quota period」，max = 不限）
   judge 是量 wall time 還是 CPU time？（⚠️考場規則未知；若量 CPU time，平行化不會變快，spin 等待反而更差）
2. 量 serial 版本：總時間、熱點函式時間 → p = 熱點 / 總時間
3. Amdahl 上限 1/(1-p) 夠不夠？ p=0.5 時無限核心也只有 2 倍
4. 每份工作多大？ 一個 parallel region 啟動 + barrier 約為微秒級（⚠️依機器而定，自己量）
   工作量 / 執行緒 至少要比這大兩個數量級
5. 有沒有依賴？ 迴圈第 i 次要用第 i-1 次的結果 → 不能直接 parallel for（考慮 scan、wavefront、或改演算法）
6. 選模式（§3）→ 選粒度（§4）→ 選工具（§5–§9）
7. 驗證：輸出與 serial 版逐位元相同（或在容許誤差內），且執行多次結果一致
```

| 觀察 | 結論 |
|---|---|
| `nproc` = 1 或 judge 限 1 核 | 不平行化；改演算法、cache、I/O |
| 熱點是 I/O（讀檔、`printf`、等待感測器 / 網路） | 用批次 I/O、緩衝、或 I/O 與計算重疊（pipeline），不是加運算執行緒 |
| 熱點是記憶體頻寬（單純掃大陣列、每 byte 只做一兩個運算） | 多核收益有限（共用記憶體頻寬）；先減少資料量 / 改資料結構 |
| 熱點是獨立的大量運算 | 資料平行，接近線性加速 |
| 熱點裡有共享累加 | 歸約模式（§14 範例） |
| 每筆資料要經過多個不同步驟 | 流水線，或每核做完整流程的一部分資料 |

---

## 2. 理論

### 2.1 基本定義

| 名詞 | 定義 | 備註 |
|---|---|---|
| T1 | 一個處理器的執行時間（最好用「最佳 serial 版本」，不是平行版本開 1 執行緒） | 用平行版開 1 執行緒當基準會高估加速 |
| T_N | N 個處理器的執行時間 | |
| Speedup S(N) | T1 / T_N | S = N 為完美線性；> N 為超線性（通常是 cache 變大造成） |
| Efficiency E(N) | S(N) / N | E 接近 1 = 沒有浪費 |
| Cost | N · T_N | cost-optimal：N·T_N 與 T1 同階 |
| Overhead | T_o = N·T_N − T1 | 所有「不是有用工作」的時間總和 |

### 2.2 Amdahl、Gustafson、Karp–Flatt

| 定律 | 公式 | 假設 | 何時用 |
|---|---|---|---|
| Amdahl（1967） | `S(N) = 1 / ((1−p) + p/N)`，上限 `1/(1−p)` | 問題大小固定；p 在 serial 機器上量 | 「同一筆測資跑多快」— judge 題目幾乎都是這種 |
| Gustafson–Barsis（1988） | `S(N) = s + p·N = N − (N−1)·s` | 問題大小隨 N 放大，總時間固定；s 是在**平行系統上**量到的序列時間比例 | 「給更多核，能在同時間內處理多大的資料」 |
| Karp–Flatt（1990） | `e = (1/S − 1/N) / (1 − 1/N)` | 由實測 S 反推實驗性序列比例 | 診斷：N 增加時 e 不變 → 受限於真正的序列部分；e 變大 → 開銷（同步、通訊、不平衡）在成長 |

速算（Amdahl 基本例子見 `03-optimize.md`、`multicore-sync.md` A13）：

| p | N=2 | N=4 | N=8 | N=12 | N=∞ |
|---|---|---|---|---|---|
| 0.50 | 1.33 | 1.60 | 1.78 | 1.85 | 2 |
| 0.90 | 1.82 | 3.08 | 4.71 | 5.71 | 10 |
| 0.95 | 1.90 | 3.48 | 5.93 | 7.74 | 20 |
| 0.99 | 1.98 | 3.88 | 7.48 | 10.81 | 100 |

Karp–Flatt 例：N=4 實測 S=3.0 → e = (0.333−0.25)/(0.75) ≈ 0.111；N=8 實測 S=4.5 → e = (0.222−0.125)/0.875 ≈ 0.111。e 不變 → 瓶頸是固有的序列部分（約 11%），去優化那段，而不是減少同步。

### 2.3 Strong scaling vs weak scaling

| | Strong scaling | Weak scaling |
|---|---|---|
| 做法 | 問題大小固定，N = 1, 2, 4, 8… | 每個處理器的工作量固定，總問題 ∝ N |
| 理想結果 | T_N = T1/N | T_N 不變 |
| 對應定律 | Amdahl | Gustafson |
| 報告方式 | 畫 S(N) 或 E(N) | 畫 T_N 或 weak efficiency T1/T_N |

考試寫報告時：列表 N、T_N、S、E、e（Karp–Flatt），每格跑 3–5 次取中位數。

### 2.4 Work / span（DAG 模型）

- 把程式看成工作的 DAG。**Work T1** = 所有節點時間總和；**Span T∞**（critical path、depth）= 最長路徑。
- **Work law**：`T_N ≥ T1 / N`；**Span law**：`T_N ≥ T∞`。
- **Parallelism** = `T1 / T∞` = 任何 N 下可達的最大加速。
- **Brent / 貪婪排程上界**：`T_N ≤ T∞ + (T1 − T∞)/N ≤ T1/N + T∞`。
- **Slackness** = `T1 / (N · T∞)`：< 1 表示 N 個處理器不可能完美加速；經驗上 parallelism 要比 N 大一個數量級以上，排程才有彈性。
- **Work-efficient**：平行演算法的總 work 與最佳 serial 同階（例如平行 prefix sum 若 work 變成 O(n log n) 就不是 work-efficient）。

| 演算法 | Work | Span | 說明 |
|---|---|---|---|
| map（n 個獨立運算） | O(n) | O(1) | 完美平行 |
| 樹狀歸約（sum/max） | O(n) | O(log n) | 兩兩合併 |
| 實務歸約（N 執行緒各自掃 n/N，再合併） | O(n) | O(n/N + N) 或 O(n/N + log N) | N 小時序列合併就夠 |
| 兩趟 block scan（§3.3） | O(n) | O(n/N + N) | |
| 合併排序（平行遞迴、序列 merge） | O(n log n) | O(n) | merge 是瓶頸 → parallelism 只有 O(log n) |

### 2.5 開銷分類與粒度（granularity）

| 開銷 | 來源 | 典型對策 |
|---|---|---|
| 建立 / 銷毀 | `pthread_create`、`fork`、每次進 parallel region | 建一次重複用（thread pool；OpenMP 本身會重用執行緒）；把多個小 region 合成一個大 region |
| 同步 | 鎖、atomic、barrier、條件變數喚醒 | 減少共享；各自累加；`nowait`；鎖外計算（`multicore-sync.md` A2、A10） |
| 通訊 | 資料搬移、序列化、cache coherence 流量 | 批次化、少傳、就地計算、零複製 |
| 負載不平衡 | 每份工作時間不同，最慢的人決定結束時間 | 動態排程、較小 chunk、work stealing |
| 冗餘計算 | 為避免通訊而重算（halo 擴寬、重複初始化） | 有時值得：用計算換通訊 |
| 資源競爭 | 記憶體頻寬、共享 cache、SRAM bank、超額訂閱（oversubscription） | 執行緒數 ≤ 可用核心；資料局部性 |

**粒度**：每個任務的計算量 / 每個任務的開銷。
- 太細（fine-grained）：開銷主導，甚至比 serial 慢（§14 的 atomic 版就是例子）。
- 太粗（coarse-grained）：任務數 < 核心數，或少數大任務造成不平衡。
- 經驗法則：任務數 ≈ 核心數 × 4–16（需要動態平衡時），每個任務至少數十微秒（⚠️經驗值，以實測為準）。

### 2.6 通訊成本：α–β（latency–bandwidth）模型

```
T(n) = α + β·n        α = 每則訊息的固定延遲（啟動、系統呼叫、header、排程）
                      β = 每 byte 的時間 = 1 / 頻寬
半效能訊息大小 n½ = α/β   （訊息比這小 → 時間主要花在 α）
```

| 推論 | 說明 |
|---|---|
| k 則訊息各 n bytes vs 1 則 k·n bytes | `k·α + β·k·n` vs `α + β·k·n` → **批次化省下 (k−1)·α** |
| 頻寬受限時 | 減少 bytes：二進位取代文字、較小型別、只傳差異、壓縮（壓縮本身要時間） |
| 延遲受限時 | 減少訊息數 / round trip：批次、管線化請求、不要「問一筆等一筆」 |
| 樹狀廣播 / 歸約（P 個參與者） | 約 `⌈log2 P⌉ · (α + β·n)` |
| Ring allreduce（大訊息常用） | 約 `2(P−1)·α + 2·(P−1)/P · n·β` → 頻寬項幾乎與 P 無關（Thakur, Rabenseifner & Gropp 2005，MPICH 集體通訊論文） |

數值例（UART，`pico-sdk` stdio 預設 115200 baud，8N1 每 byte 10 bit）：每 byte ≈ 86.8 µs，1 kB ≈ 89 ms。若每筆結果都 `printf` 一行 20 字元 → 每筆 ≈ 1.7 ms，**輸出本身就是瓶頸**；改成二進位、批次或只印摘要。

### 2.7 吞吐量、延遲、Little's law、流水線公式

| 量 | 定義 |
|---|---|
| Latency（延遲） | 一筆資料從進入到離開的時間 |
| Throughput（吞吐量） | 單位時間完成幾筆 |
| Little's law | `L = λ · W`：系統內平均筆數 = 平均到達率 × 平均停留時間（穩態、任何排隊系統都成立） |

k 個 stage、每 stage 時間 t_i、處理 n 筆（每 stage 一個 worker、中間有緩衝）：

```
吞吐量 ≈ 1 / max(t_i)                      瓶頸 stage 決定
單筆延遲（無排隊）= Σ t_i
總時間 ≈ Σ t_i + (n − 1) · max(t_i)
serial 總時間 = n · Σ t_i       → 加速上限 = Σ t_i / max(t_i)  ≤ k
```

- **平衡 stage**：把最慢 stage 拆開（再切成兩個 stage），或讓它有多個 worker（replicate，若該 stage 無狀態）。
- **緩衝**：stage 之間的佇列吸收抖動（jitter）。佇列長度 > 0 且持續成長 → 下游比上游慢（Little's law：L 成長 = W 成長 = 延遲變大）。
- **有界佇列 = backpressure**：佇列滿時讓上游阻塞或丟棄，避免記憶體無限成長與延遲爆炸（§10、§11）。
- 吞吐量 vs 延遲的取捨：批次化提升吞吐量但增加單筆延遲（要等湊滿一批）；加深佇列提升吞吐量穩定度但增加延遲。題目若要求「延遲」→ 小批次、淺佇列、丟舊留新；要求「總時間」→ 大批次、深佇列。

---

## 3. 分解模式（decomposition patterns）

| 模式 | 形狀 | 適用 | 主要風險 | 工具對應 |
|---|---|---|---|---|
| 資料平行 / map | 每個元素獨立運算 | 陣列、影像、獨立測資 | 記憶體頻寬、不平衡 | `omp parallel for`；雙核各做一半（`multicore-sync.md` B11.1） |
| 歸約 reduction | 多個值合成一個（sum/max/histogram） | 統計、累加 | 共享累加變數的 race / contention | `reduction(...)`；per-thread partial + 合併 |
| Scan / prefix sum | out[i] = a[0]+…+a[i] | 壓縮、分配位置、計數排序 | 看似有依賴，其實可兩趟完成 | §3.3 |
| 流水線 pipeline | 資料依序經過 stage | 串流、感測 → 處理 → 輸出；ROS 2 node 鏈 | 最慢 stage、佇列成長 | 執行緒 + 有界佇列；pico `queue_t`（`multicore-sync.md` B7）；ROS 2 topic |
| Task parallel / fork–join | 遞迴拆成子問題，等子問題完成再合併 | 分治、樹走訪 | 任務太小、遞迴太深 | `omp task` + `taskwait`；cutoff |
| Producer–consumer | 生產者放入佇列，消費者取出 | I/O 與計算分離 | 佇列滿 / 空時的同步 | cond var 佇列、SPSC ring（`multicore-sync.md` A4、A11） |
| Master–worker / work queue | 一個分派者，多個 worker 取工作 | 工作大小不一 | 佇列成為熱點 | thread pool（§6.1）；`schedule(dynamic)` |
| Work stealing | 每個 worker 有自己的 deque，閒的去偷別人的 | 不規則遞迴任務 | 實作複雜 | OpenMP tasks / TBB / Cilk 的執行期（概念即可） |
| Scatter–gather | 根把資料分給所有人 → 各自處理 → 收回 | 分散式批次運算 | 根是瓶頸 | `MPI_Scatter`/`MPI_Gather`；多 process |
| Stencil + halo exchange | 每格依賴鄰居（模板） | 熱傳導、影像濾波、Jacobi | 邊界交換、同步每一步 | 切塊 + ghost cell；OpenMP 每步 barrier；MPI Sendrecv（§8.4） |
| MapReduce | map 產生 (key, value) → 依 key 分組（shuffle）→ reduce | 字數統計、分組彙總 | shuffle 的通訊量 | 概念；單機可用「per-thread hash map + 合併」 |
| Embarrassingly parallel | 完全獨立的工作 | 多筆測資、參數掃描、Monte Carlo | 隨機數種子、輸出順序 | 多 process / `parallel for`；結果依索引存放 |

### 3.1 歸約的三種寫法（由差到好）

| 寫法 | 同步次數 | 說明 |
|---|---|---|
| 每次都 `critical` / mutex | n | 幾乎一定比 serial 慢 |
| 每次都 `atomic` | n | 比 critical 好，但同一位址的 cache line 在核心間來回彈跳，常常仍比 serial 慢 |
| 每執行緒區域累加 + 結尾合併一次 | N | 正解。合併用 `reduction` 子句、`critical`、或依執行緒編號存陣列後序列合併 |

### 3.2 樹狀歸約（概念）

```
第 1 輪：t0+=t1  t2+=t3  t4+=t5  t6+=t7   （4 個並行加法）
第 2 輪：t0+=t2  t4+=t6
第 3 輪：t0+=t4                           → log2(8)=3 輪
```
執行緒數小（≤ 16）時，「各自 partial，最後由一個執行緒依序加總」通常就夠快，且順序固定、浮點結果可重現。

### 3.3 Scan（prefix sum）：兩趟 block scan

```c
// 兩趟 inclusive scan：part 大小為 omp_get_max_threads()+1，且 part[0] = 0
#pragma omp parallel
{
    int t = omp_get_thread_num(), T = omp_get_num_threads();
    long lo = n * t / T, hi = n * (t + 1) / T, s = 0;
    for (long i = lo; i < hi; i++) { s += a[i]; out[i] = s; }   // 第 1 趟：區塊內 scan
    part[t + 1] = s;
    #pragma omp barrier
    #pragma omp single                                        // 單一執行緒做區塊總和的 scan
    for (int k = 1; k <= T; k++) part[k] += part[k - 1];
    // single 結尾有隱含 barrier
    long off = part[t];
    for (long i = lo; i < hi; i++) out[i] += off;              // 第 2 趟：加上前面區塊的總和
}
```
（本機 GCC 13 編譯執行，結果與 serial 相同。）

---

## 4. 負載平衡與分割

| 分割 | 第 t 個執行緒（共 T 個）負責 | 優點 | 缺點 | OpenMP |
|---|---|---|---|---|
| Block（連續區塊） | `[n·t/T, n·(t+1)/T)` | 局部性最好、零排程開銷 | 每元素成本不均時不平衡 | `schedule(static)`（不給 chunk） |
| Cyclic（輪流） | `i = t, t+T, t+2T, …` | 成本隨 i 遞增 / 遞減時平衡 | 局部性差；相鄰元素被不同執行緒寫 → false sharing | `schedule(static,1)` |
| Block-cyclic | 大小 B 的區塊輪流分配 | 兩者折衷 | 要選 B | `schedule(static,B)` |
| Dynamic | 誰閒誰拿下一塊（大小 B） | 不規則成本也平衡 | 每拿一次有排程開銷（共用計數器） | `schedule(dynamic,B)` |
| Guided | 一開始大塊，逐漸變小（≥ B） | 開銷少又能收尾平衡 | 成本前重後輕時可能不平衡 | `schedule(guided,B)` |

- 區塊邊界用 `n * t / T` 計算（先乘再除），確保總和剛好 n；n 大時用 `long long` 避免溢位。
- **chunk 大小取捨**：越小越平衡但開銷越大；越大開銷越小但尾端不平衡。dynamic 的預設 chunk 是 1（OpenMP 規格），對便宜的迭代通常太小 → 給 16–1024 試。
- 本機實測（8 執行緒，第 i 次迭代成本 ∝ i 的三角形負載）：`static` 0.42 s、`static,1` 0.29 s、`dynamic,64` 0.26 s。成本均勻時三者差不多，`static` 開銷最小。
- 多筆測資 / 多個檔案：每筆大小不同時，**大的先排**（依大小遞減排序後動態分派，LPT 啟發式），能明顯縮短尾巴。

---

## 5. OpenMP 深入（共享記憶體，Linux 上最省力的工具）

### 5.1 編譯、可用性、版本

```bash
gcc -O2 -fopenmp x.c -o x          # 編譯與連結都要 -fopenmp
OMP_NUM_THREADS=4 ./x
echo _OPENMP | gcc -fopenmp -E -x c - | tail -1   # 查支援的規格版本日期
```

- Ubuntu 24.04 上 `omp.h` 屬於 `libgcc-13-dev`，而 `libgcc-13-dev` 依賴 `libgomp1`（本機 `dpkg -S` / `apt-cache depends` 確認）。所以裝了 `gcc` 就有 OpenMP；考前 Dockerfile 有裝 `gcc libc6-dev`，推論考場容器可用 `-fopenmp`（⚠️未在考場容器實測，先 `gcc -fopenmp` 試編一個 `#include <omp.h>` 的檔案）。
- GCC 13 的 `_OPENMP` = `201511`（OpenMP 4.5）；但部分 5.x 功能已可用（本機實測：`masked`、陣列區段 reduction `reduction(+:h[:NB])`、`taskloop`、`parallel for simd`、`atomic capture` 都能編譯執行）。新版 libgomp 文件寫 `_OPENMP` = `202111`（5.2），那是較新的 GCC。
- **沒加 `-fopenmp`** 時 pragma 被忽略，程式照樣以單執行緒跑（`-Wall` 會出現 `-Wunknown-pragmas` 警告）。呼叫 `omp_*` 函式則會連結失敗 → 可用 `#ifdef _OPENMP` 包住。
- `-fopenmp-simd`：只啟用 `simd` 類 pragma，不需要 runtime。

### 5.2 執行模型

- **fork–join**：遇到 `#pragma omp parallel` 時產生一個 team（主執行緒 + 其他執行緒），區塊結束有**隱含 barrier**，然後只剩主執行緒。libgomp 會**重用**執行緒，第一個 parallel region 才付建立成本 → 計時要先熱身一次，或把第一次排除。
- **worksharing**（`for`、`sections`、`single`）把工作分給已存在的 team，本身不產生執行緒；`for` / `sections` / `single` 結尾都有隱含 barrier，可加 `nowait` 去掉。
- 預設執行緒數：libgomp 在 `OMP_NUM_THREADS` 未設定時「每個 CPU 一個執行緒」；可用 CPU 數會受 affinity（cpuset）限制。⚠️ 容器用 CFS quota（`docker --cpus`）限制時，`nproc` 可能仍顯示全部核心 → 會超額訂閱，請看 `/sys/fs/cgroup/cpu.max` 並手動設 `OMP_NUM_THREADS`（⚠️未驗證 libgomp 是否讀 quota）。

### 5.3 `parallel for` 與 schedule

```c
#pragma omp parallel for schedule(static) num_threads(4) if(n > 10000)
for (long i = 0; i < n; i++) out[i] = f(in[i]);
```

| schedule | 規格語意（OpenMP 5.0 §2.9.2） |
|---|---|
| `static` | 不給 chunk：迭代切成約等長的連續塊，每個執行緒最多一塊。給 chunk：大小 chunk 的塊依執行緒編號輪流分配 |
| `dynamic[,c]` | 執行緒做完就再要一塊；**不給 chunk 時預設 1** |
| `guided[,c]` | 塊大小與「剩餘迭代 / 執行緒數」成正比，逐漸縮小，不小於 c（最後一塊可能更小）|
| `auto` | 交給編譯器 / runtime 決定 |
| `runtime` | 由 `OMP_SCHEDULE` 或 `omp_set_schedule()` 決定；libgomp 在未設定 `OMP_SCHEDULE` 時為 `dynamic,1` |
| （沒寫 schedule） | 由 def-sched-var 決定，屬實作定義。本機實測 GCC 13 把它展開成 static 分塊（只呼叫 `omp_get_num_threads/omp_get_thread_num`，沒有呼叫 `GOMP_loop_*`） |

- 修飾詞：`monotonic` 是 `static` 的預設；其他 kind 預設 `nonmonotonic`（塊的執行順序不保證遞增）。
- `if(expr)`：expr 為假時以單執行緒執行 → **小輸入不要平行**的簡單作法。
- `num_threads(k)`：只影響這個 region。
- 迴圈需為「canonical form」：`for (init; var relop bound; var += step)`，迭代次數在進入時可算出；不能在迴圈內 `break`（可以 `continue`）。

### 5.4 資料共享屬性

| 子句 | 語意 | 常見用途 / 陷阱 |
|---|---|---|
| `shared(x)` | 所有執行緒同一份 | parallel 外宣告的變數預設 shared（除了下列例外）|
| `private(x)` | 每執行緒一份，**未初始化** | 讀它前要先寫；結束後原變數值不變 |
| `firstprivate(x)` | 每執行緒一份，初始值 = 進入前的值 | 參數、種子 |
| `lastprivate(x)` | 迴圈結束後，原變數 = **序列上最後一次迭代**的值 | |
| `reduction(op:x)` | 每執行緒一份，初值為 op 的單位元素，結束時合併回原變數 | 見 5.5 |
| `default(none)` | 強迫每個變數都明確標示 | **強烈建議**：編譯器會幫你抓漏標的共享變數 |
| `threadprivate` | 全域 / static 變數每執行緒一份（跨 region 保留） | 少用 |

自動 private 的：`parallel for` 的迴圈變數；在 parallel 區塊**內部**宣告的區域變數。
**C 的經典 bug**：巢狀迴圈的內層變數若宣告在 parallel 外面，它是 **shared** → race。

```c
int i, j;                       // 錯：j 是 shared
#pragma omp parallel for
for (i = 0; i < n; i++)
    for (j = 0; j < m; j++) a[i][j] = 0;

#pragma omp parallel for        // 對：在迴圈內宣告
for (int i = 0; i < n; i++)
    for (int j = 0; j < m; j++) a[i][j] = 0;
```

### 5.5 reduction

```c
double s = 0; long mx = LONG_MIN;
#pragma omp parallel for reduction(+:s) reduction(max:mx)
for (long i = 0; i < n; i++) { s += a[i]; if (b[i] > mx) mx = b[i]; }

long hist[256] = {0};
#pragma omp parallel for reduction(+:hist[:256])   // 陣列區段 reduction（GCC 13 實測可用）
for (long i = 0; i < n; i++) hist[data[i]]++;
```

- 內建運算子（C）：`+ * & | ^ && || max min`（`-` 已在 5.2 deprecated，行為同 `+`）。
- 每個執行緒的私有副本以單位元素初始化（`+`→0、`*`→1、`max`→該型別最小值…），結束時以**未指定的順序**合併 → 浮點結果會隨執行緒數改變（見 §13）。
- 陣列 reduction 每個執行緒會配置一份完整副本（大陣列 × 執行緒數 = 記憶體；在 stack 上可能爆）。很大的陣列改用 §14 的手動 per-thread 版本並把副本放 heap。
- 自訂歸約：`#pragma omp declare reduction(name : type : combiner) initializer(...)`（較少用到）。

### 5.6 同步構造

| 構造 | 語意 | 成本 / 注意 |
|---|---|---|
| `#pragma omp critical [(name)]` | 同名 critical 一次只能一個執行緒進入；沒寫名字的全部共用一把鎖 | 重；不同資源用不同名字 |
| `#pragma omp atomic`（預設 update） | 單一記憶體位置的 `x++`、`x += expr`、`x = x op expr` 原子化 | 比 critical 輕；expr 本身不是原子的 |
| `atomic read` / `write` / `capture` | 原子讀、寫、讀改寫並取得舊/新值（`v = x++;`） | |
| `#pragma omp barrier` | team 內全部到齊才繼續 | 不能放在只有部分執行緒會走到的分支裡（會 deadlock）|
| `nowait` | 去掉 `for`/`single`/`sections` 結尾的隱含 barrier | 後面若用到這個迴圈的結果就不能加 |
| `#pragma omp single` | 只有一個（任意）執行緒執行；結尾有 barrier | 常用來產生 tasks |
| `#pragma omp masked`（5.1）/ `master`（舊名） | 只有主執行緒（thread 0）執行；**沒有** barrier | GCC 13 兩者皆可 |
| `#pragma omp ordered` | 搭配 `for ordered`：區塊依迭代順序執行 | 可確保輸出順序，但會序列化那一段 |
| `#pragma omp flush` | 記憶體一致性點 | barrier、critical、atomic 等已隱含；一般程式不需手寫 |
| `omp_lock_t` | `omp_init_lock / omp_set_lock / omp_unset_lock / omp_destroy_lock` | 需要「一個元素一把鎖」時 |

### 5.7 `collapse` 與 `simd`

```c
#pragma omp parallel for collapse(2) schedule(static)
for (int i = 0; i < H; i++)
    for (int j = 0; j < W; j++) img[i][j] = g(i, j);   // H 很小（< 執行緒數）時特別有用

#pragma omp parallel for simd reduction(+:s)         // 執行緒 + 向量化
for (int i = 0; i < n; i++) s += a[i] * b[i];
```

- `collapse(k)`：把 k 層**完美巢狀**（中間沒有其他敘述）的迴圈合成一個迭代空間後再分配。保守起見只用在矩形迴圈（內層邊界不依賴外層）。
- `simd`：告訴編譯器可向量化（包括允許重排浮點歸約）。要搭配 `-O2` 以上；可用 `-fopt-info-vec` 看哪些迴圈被向量化。

### 5.8 Tasks（不規則、遞迴平行）

```c
long fib(int n) {
    if (n < 20) return fib_serial(n);        // cutoff：任務太小就不要再切
    long a, b;
    #pragma omp task shared(a)
    a = fib(n - 1);
    #pragma omp task shared(b)
    b = fib(n - 2);
    #pragma omp taskwait                     // 等這兩個子任務
    return a + b;
}
// 呼叫端：一個 team，只有一個執行緒產生根任務
#pragma omp parallel
#pragma omp single
result = fib(40);
```

- task 內引用的變數：外層不是 shared 的（例如函式內的區域變數）預設 `firstprivate`（複製一份）；要把結果寫回外面就要 `shared(a)`。
- `taskwait`：等**直接子任務**；`taskgroup`：等區塊內產生的所有後代任務。
- `taskloop [grainsize(g) | num_tasks(k)]`：把迴圈切成任務。
- `depend(in: x) depend(out: y)`：以資料相依性排序任務（可做 DAG / 流水線）。
- **沒有 cutoff** 的遞迴任務會產生數百萬個極小任務 → 比 serial 慢很多。

### 5.9 Runtime API 與環境變數

| API | 說明 |
|---|---|
| `double omp_get_wtime(void)` | 牆鐘秒數（從過去某個任意時間點起算），相減得經過時間 |
| `int omp_get_thread_num(void)` | 自己在 team 中的編號 0..T−1 |
| `int omp_get_num_threads(void)` | 目前 team 大小（在 parallel 外 = 1） |
| `int omp_get_max_threads(void)` | 下一個 parallel region 預設會用的執行緒數（配置 per-thread 陣列用這個）|
| `int omp_get_num_procs(void)` | 可用處理器數 |
| `void omp_set_num_threads(int)` | 設定之後 region 的預設執行緒數 |
| `int omp_in_parallel(void)` | 是否在 active parallel region 內 |

| 環境變數（libgomp） | 值 | 預設 |
|---|---|---|
| `OMP_NUM_THREADS` | 正整數，或逗號清單（每層巢狀一個值） | 每個 CPU 一個執行緒 |
| `OMP_SCHEDULE` | `type[,chunk]`，type = `static/dynamic/guided/auto` | `dynamic,1`（只影響 `schedule(runtime)`） |
| `OMP_PROC_BIND` | `TRUE/FALSE` 或 `primary,close,spread` 清單 | 設了 `OMP_PLACES` 或 `GOMP_CPU_AFFINITY` 時為 TRUE，否則 FALSE |
| `OMP_PLACES` | `threads` / `cores` / `sockets` / 明確 CPU 清單 | — |
| `OMP_MAX_ACTIVE_LEVELS` | 正整數 | 1（除非 `OMP_NESTED=true` 或 `OMP_NUM_THREADS`/`OMP_PROC_BIND` 給了多項清單）|
| `OMP_NESTED` | `true/false`（已 deprecated） | — |
| `OMP_WAIT_POLICY` | `ACTIVE` / `PASSIVE` | 未設定：先短暫忙等再改被動等待（忙等長度可由 `GOMP_SPINCOUNT` 調） |
| `OMP_DISPLAY_ENV` | `true` / `verbose` | 啟動時印出版本與 ICV，**確認設定有生效** |
| `OMP_STACKSIZE` | 如 `16M` | 執行緒 stack 大小（大區域陣列 / 陣列 reduction 用到）|

- **巢狀平行**：預設只有一層 active → 內層 `parallel` 只得到 1 個執行緒（不會爆量，但也不會加速）。打開巢狀時要小心 T_outer × T_inner 超額訂閱。
- 超額訂閱 + `ACTIVE` 忙等 = 災難（等待的執行緒搶走工作執行緒的 CPU）。共用機器或執行緒數 > 核心時用 `OMP_WAIT_POLICY=PASSIVE`。

### 5.10 OpenMP 常見 bug

| 症狀 | 原因 | 修法 |
|---|---|---|
| 結果每次不同 / 偏小 | 共享累加變數沒有 reduction；內層迴圈變數 shared；暫存變數宣告在外面 | `reduction`；變數宣告在迴圈內；`default(none)` |
| 比 serial 慢 | 每次迭代 `critical`/`atomic`；false sharing；工作太小；region 在熱迴圈內反覆進出 | per-thread partial；`if(n>T)`；把 parallel 移到外層 |
| 加執行緒反而更慢 | 記憶體頻寬飽和；超額訂閱；忙等 | 減少執行緒；`OMP_WAIT_POLICY=PASSIVE` |
| `rand()` 結果怪 / 慢 | `rand()` 有共享狀態，不是 thread-safe | 每執行緒自己的 PRNG（例如 `rand_r(&seed)`，seed = 固定值 + 執行緒編號）|
| segfault 只在平行版出現 | 每執行緒大區域陣列爆 stack；陣列 reduction 副本太大 | 放 heap；`OMP_STACKSIZE` |
| 輸出行順序亂 | 多執行緒 `printf` | 存陣列，最後序列輸出（§13）|
| 浮點總和最後幾位不同 | 合併順序隨執行緒數變 | 固定分塊 + 依序合併（§13）|
| barrier 卡死 | barrier / worksharing 放在只有部分執行緒會進的 `if` 內 | 所有執行緒都要遇到同樣的 barrier 序列 |
| ThreadSanitizer 報一堆 libgomp 內部 race | libgomp 本身未經 TSan instrument，可能誤報（⚠️未驗證於考場）| 先用 pthread 版或 `OMP_NUM_THREADS=1` 對照；看 race 是否落在自己的變數上 |

---

## 6. 其他共享記憶體工具

### 6.1 pthread thread pool（master–worker / 工作佇列）

原語（mutex、cond var 的正確用法）見 `multicore-sync.md` A3–A4。下面是最小可用的固定大小 thread pool：有界佇列（滿了 `submit` 會阻塞 = backpressure）、`pool_wait` 等全部完成、`pool_stop` 關閉。（本機以 `-fsanitize=thread` 執行，無 race 報告。）

```c
#include <pthread.h>
#include <stdbool.h>
#define NW   4
#define QCAP 256
typedef struct { void (*fn)(void *); void *arg; } task_t;

static task_t q[QCAP];
static int q_head, q_tail, q_count, pending;      // pending = 已送出但尚未完成
static bool stop;
static pthread_mutex_t mu = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t not_empty = PTHREAD_COND_INITIALIZER;
static pthread_cond_t not_full  = PTHREAD_COND_INITIALIZER;
static pthread_cond_t all_done  = PTHREAD_COND_INITIALIZER;
static pthread_t th[NW];

void pool_submit(void (*fn)(void *), void *arg) {
    pthread_mutex_lock(&mu);
    while (q_count == QCAP) pthread_cond_wait(&not_full, &mu);   // 有界：滿了就等
    q[q_tail] = (task_t){fn, arg};
    q_tail = (q_tail + 1) % QCAP; q_count++; pending++;
    pthread_cond_signal(&not_empty);
    pthread_mutex_unlock(&mu);
}

static void *worker(void *unused) {
    (void)unused;
    for (;;) {
        pthread_mutex_lock(&mu);
        while (q_count == 0 && !stop) pthread_cond_wait(&not_empty, &mu);
        if (q_count == 0 && stop) { pthread_mutex_unlock(&mu); return NULL; }
        task_t t = q[q_head];
        q_head = (q_head + 1) % QCAP; q_count--;
        pthread_cond_signal(&not_full);
        pthread_mutex_unlock(&mu);

        t.fn(t.arg);                                  // 在鎖外執行工作

        pthread_mutex_lock(&mu);
        if (--pending == 0) pthread_cond_broadcast(&all_done);
        pthread_mutex_unlock(&mu);
    }
}

void pool_start(void) { for (int i = 0; i < NW; i++) pthread_create(&th[i], NULL, worker, NULL); }
void pool_wait(void) {
    pthread_mutex_lock(&mu);
    while (pending > 0) pthread_cond_wait(&all_done, &mu);
    pthread_mutex_unlock(&mu);
}
void pool_stop(void) {
    pthread_mutex_lock(&mu); stop = true; pthread_cond_broadcast(&not_empty); pthread_mutex_unlock(&mu);
    for (int i = 0; i < NW; i++) pthread_join(th[i], NULL);
}
```

使用要點：
- 每個任務寫自己的結果欄位（例如 `job_t { lo, hi, result }` 陣列），`pool_wait()` 之後主執行緒依索引順序合併 → 結果與輸出順序確定。
- 任務太小時佇列的鎖就是瓶頸 → 一個任務處理一段範圍，而不是一個元素。
- 若工作量均勻，**更簡單的做法**：直接開 T 個執行緒各做 `[n·t/T, n·(t+1)/T)`，`join` 後合併（`multicore-sync.md` A9）。
- 編譯：`gcc -O2 -Wall -pthread x.c`。TSan 在新核心上若出現 `FATAL: ThreadSanitizer: unexpected memory mapping`，用 `setarch -R ./x`（關閉此 process 的 ASLR）執行（本機 kernel 7.0 實測有效）。

### 6.2 C11 `<threads.h>`（簡述）

| C11 | 對應 pthread |
|---|---|
| `int thrd_create(thrd_t *thr, thrd_start_t func, void *arg)`，`func` 型別為 `int (*)(void *)` | `pthread_create` |
| `int thrd_join(thrd_t thr, int *res)` | `pthread_join` |
| `mtx_init(&m, mtx_plain)`、`mtx_lock`、`mtx_unlock` | `pthread_mutex_*` |
| `cnd_init`、`cnd_wait(&c, &m)`、`cnd_signal`、`cnd_broadcast` | `pthread_cond_*` |
| 回傳值 `thrd_success` / `thrd_error` / ... | 回傳 0 / errno |

glibc 2.28 起支援 `<threads.h>`。功能比 pthread 少（沒有 affinity、rwlock 等），考試用 pthread 即可；遇到既有程式用 C11 threads 時照上表對照。

### 6.3 Python（簡述；細節見 `python-perf.md`）

- CPython 有 GIL：`threading` 不能讓純 Python 運算多核並行（I/O 等待可以重疊）。
- CPU 密集用 `multiprocessing.Pool` / `concurrent.futures.ProcessPoolExecutor`：每個 worker 是獨立 process，參數與結果經 pickle 傳遞（序列化成本）→ 每個任務要夠大，`pool.map(f, items, chunksize=k)` 用大一點的 chunksize。
- 主程式一定要有 `if __name__ == '__main__':` 保護。
- Linux 預設 start method：Python 3.14 之前是 `fork`，3.14 起改為 `forkserver`。Jazzy 用 Python 3.12 → `fork`。
- 可用 CPU 數：`len(os.sched_getaffinity(0))`（`os.process_cpu_count()` 是 3.13 才有）。
- NumPy 等原生函式庫在 C 裡執行時會釋放 GIL；向量化通常比多 process 更划算。

---

## 7. 多 process 與 IPC（單機「分散式」）

| 機制 | API | 特性 | 適用 |
|---|---|---|---|
| `fork` + `wait` | `pid_t fork(void)`、`waitpid` | 子 process 複製位址空間（copy-on-write）；彼此記憶體獨立 → 無 data race | 平行跑獨立工作；隔離崩潰 |
| pipe | `int pipe(int fd[2])` | 單向 byte stream；Linux 預設容量 65536 bytes（2.6.11+），2.6.35+ 可用 `fcntl(F_SETPIPE_SZ)` 調整；≤ `PIPE_BUF`（Linux 4096）的 write 是原子的 | 父子間傳結果；shell 管線 |
| Unix domain socket | `socketpair(AF_UNIX, SOCK_STREAM, 0, sv)`；或 bind 到路徑 | 雙向；本機最快的 socket | 雙向 RPC |
| TCP socket | `socket/bind/listen/accept/connect` | 跨機器；有 Nagle 演算法（小訊息延遲 → `TCP_NODELAY`）| 跨 container / 跨機器 |
| POSIX 共享記憶體 | `shm_open` + `ftruncate` + `mmap(MAP_SHARED)` | 零複製；**需要自己同步** | 大量資料、低延遲 |
| 檔案 | write → rename | 最簡單，最慢 | 一次性交換結果 |

**Byte stream 的陷阱**（pipe / stream socket）：`read`/`write` 可能只處理部分 bytes → 要迴圈直到完成；訊息之間沒有邊界 → 自己加長度前綴或固定大小紀錄。寫端全部關閉後，讀端 `read` 回傳 0（EOF）；讀端全關後再寫 → `SIGPIPE` / `EPIPE`。父子都要關掉不用的那一端，否則永遠等不到 EOF。

### 7.1 共享記憶體範例

```c
#include <sys/mman.h>
#include <fcntl.h>
#include <unistd.h>
// 建立：名稱必須以 '/' 開頭，後面不能再有 '/'；新物件長度為 0，要 ftruncate
int fd = shm_open("/myshm", O_CREAT | O_RDWR, 0600);
ftruncate(fd, size);
void *p = mmap(NULL, size, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
close(fd);                       // mmap 後 fd 可關
/* ... 使用 p ... */
munmap(p, size);
shm_unlink("/myshm");            // 移除名稱（物件位於 /dev/shm 的 tmpfs）
```

- glibc 2.34 起 `shm_open` 在 libc 內，不用 `-lrt`（本機 glibc 2.39 不加 `-lrt` 實測可連結；加了也無害）。man page 仍寫要 `-lrt`（舊系統）。
- 同步：放在共享區域中的 `sem_t`（`sem_init(&s, 1, 0)`，第二個參數 pshared=1）、`PTHREAD_PROCESS_SHARED` 的 mutex，或 C11 atomic（lock-free 型別才跨 process 安全，⚠️依平台）。概念同 `multicore-sync.md` A5、A11。
- 更簡單：`fork` 前 `mmap(NULL, size, PROT_READ|PROT_WRITE, MAP_SHARED|MAP_ANONYMOUS, -1, 0)`，父子共用，不需要名稱。

### 7.2 Fork 平行 + 依序收結果（確定性輸出）

```c
// 每個子 process 處理 chunk k，把結果寫到共享陣列 res[k]；父 process 等全部結束後依 k 順序輸出
long *res = mmap(NULL, K * sizeof(long), PROT_READ | PROT_WRITE, MAP_SHARED | MAP_ANONYMOUS, -1, 0);
for (int k = 0; k < K; k++) {
    if (fork() == 0) { res[k] = work(k); _exit(0); }   // 子 process 用 _exit，避免重複 flush stdio 緩衝
}
while (wait(NULL) > 0) {}
for (int k = 0; k < K; k++) printf("%ld\n", res[k]);
```
注意：`fork` 前若 stdout 緩衝區有未 flush 的資料，子 process 會複製一份 → 用 `fflush(stdout)` 再 fork，子 process 結束用 `_exit`。

### 7.3 序列化成本

| 格式 | 成本 | 注意 |
|---|---|---|
| 原始 struct（memcpy） | 最低 | 兩端要同 ABI（endianness、padding、型別大小）；RP2350 與 x86-64 都是 little-endian，但 `long` 大小不同（32 vs 64 bit）→ 用 `<stdint.h>` 固定寬度型別 |
| 固定格式二進位（手動 pack） | 低 | 可攜 |
| 文字（`printf`/`scanf`、CSV） | 高（格式化 / 解析） | 易除錯；judge 輸入輸出通常是文字 |
| JSON / pickle | 更高 | 彈性高 |
| ROS 2 message（CDR） | 中；rclpy 每筆還有 Python ↔ C 轉換 | 大陣列用固定型別（如 `uint8[]`）比很多小欄位好 |

---

## 8. MPI（訊息傳遞；考場多半沒裝）

先檢查：`which mpicc mpirun`。考前 image（`ros:jazzy-ros-core` + gcc/make）沒有 MPI，考場又不能安裝 → 實作題改用多 process（§7）或 OpenMP。MPI 知識主要用於：讀懂既有程式、回答設計題、把 MPI 概念（rank、集體通訊）套用到多 process / 多 node。

### 8.1 編譯與執行（Open MPI）

```bash
mpicc -O2 x.c -o x
mpirun -n 4 ./x                  # -n / -np：process 數；預設以「核心」為 slot
mpirun -n 8 --oversubscribe ./x  # process 數 > slot 數時需要
mpirun --allow-run-as-root -n 4 ./x   # 容器常以 root 執行；Open MPI 預設拒絕 root
# 或 export OMPI_ALLOW_RUN_AS_ROOT=1 OMPI_ALLOW_RUN_AS_ROOT_CONFIRM=1
```

### 8.2 核心 API（C binding）

```c
int MPI_Init(int *argc, char ***argv);
int MPI_Finalize(void);
int MPI_Comm_rank(MPI_Comm comm, int *rank);
int MPI_Comm_size(MPI_Comm comm, int *size);
double MPI_Wtime(void);
int MPI_Barrier(MPI_Comm comm);

int MPI_Send(const void *buf, int count, MPI_Datatype datatype, int dest, int tag, MPI_Comm comm);
int MPI_Recv(void *buf, int count, MPI_Datatype datatype, int source, int tag,
             MPI_Comm comm, MPI_Status *status);       // MPI_ANY_SOURCE / MPI_ANY_TAG / MPI_STATUS_IGNORE
int MPI_Sendrecv(const void *sendbuf, int sendcount, MPI_Datatype sendtype, int dest, int sendtag,
                 void *recvbuf, int recvcount, MPI_Datatype recvtype, int source, int recvtag,
                 MPI_Comm comm, MPI_Status *status);

int MPI_Isend(const void *buf, int count, MPI_Datatype datatype, int dest, int tag,
              MPI_Comm comm, MPI_Request *request);
int MPI_Irecv(void *buf, int count, MPI_Datatype datatype, int source, int tag,
              MPI_Comm comm, MPI_Request *request);
int MPI_Wait(MPI_Request *request, MPI_Status *status);
int MPI_Waitall(int count, MPI_Request array_of_requests[], MPI_Status array_of_statuses[]);

int MPI_Bcast(void *buffer, int count, MPI_Datatype datatype, int root, MPI_Comm comm);
int MPI_Reduce(const void *sendbuf, void *recvbuf, int count, MPI_Datatype datatype,
               MPI_Op op, int root, MPI_Comm comm);
int MPI_Allreduce(const void *sendbuf, void *recvbuf, int count, MPI_Datatype datatype,
                  MPI_Op op, MPI_Comm comm);            // sendbuf 可為 MPI_IN_PLACE
int MPI_Scatter(const void *sendbuf, int sendcount, MPI_Datatype sendtype,
                void *recvbuf, int recvcount, MPI_Datatype recvtype, int root, MPI_Comm comm);
int MPI_Gather(const void *sendbuf, int sendcount, MPI_Datatype sendtype,
               void *recvbuf, int recvcount, MPI_Datatype recvtype, int root, MPI_Comm comm);
```

- 常用型別：`MPI_INT`、`MPI_LONG`、`MPI_LONG_LONG`、`MPI_FLOAT`、`MPI_DOUBLE`、`MPI_CHAR`、`MPI_BYTE`；常用運算：`MPI_SUM`、`MPI_PROD`、`MPI_MAX`、`MPI_MIN`、`MPI_LAND`、`MPI_BAND`、`MPI_LOR`、`MPI_BOR`、`MPI_MAXLOC`、`MPI_MINLOC`。
- `count` 是**元素個數**不是 bytes。Scatter 的 `sendcount` 是**給每個 process 的**個數（root 相當於對每個 rank i 送出 `sendbuf + i*sendcount` 開始的一段）；Gather 的 `recvcount` 同理。不能整除時用 `MPI_Scatterv`/`MPI_Gatherv`。
- 集體通訊（Bcast/Reduce/…）**所有 rank 都必須呼叫**，且順序一致，否則卡死。
- 訊息順序：同一對 (來源, 目的)、同一 communicator、可匹配的訊息不會超車（non-overtaking）；不同來源之間沒有順序保證。
- `MPI_Isend` 後、完成（`MPI_Wait`）前**不能修改**送出緩衝；`MPI_Irecv` 完成前不能讀接收緩衝。

### 8.3 最小範例：分散求和

```c
#include <mpi.h>
#include <stdio.h>
int main(int argc, char **argv) {
    MPI_Init(&argc, &argv);
    int rank, size;
    MPI_Comm_rank(MPI_COMM_WORLD, &rank);
    MPI_Comm_size(MPI_COMM_WORLD, &size);
    long n = 100000000, lo = n * rank / size, hi = n * (rank + 1) / size;
    double t0 = MPI_Wtime();
    long local = 0, total = 0;
    for (long i = lo; i < hi; i++) local += i % 7;
    MPI_Reduce(&local, &total, 1, MPI_LONG, MPI_SUM, 0, MPI_COMM_WORLD);
    if (rank == 0) printf("total=%ld time=%.3f\n", total, MPI_Wtime() - t0);   // 只有 rank 0 輸出
    MPI_Finalize();
    return 0;
}
```

### 8.4 Halo exchange 與 deadlock

1D 切塊，每個 rank 有 `u[0..m+1]`，`u[0]`、`u[m+1]` 是 ghost cell：

```c
int left  = (rank > 0)        ? rank - 1 : MPI_PROC_NULL;   // MPI_PROC_NULL：對它收送 = 無動作
int right = (rank < size - 1) ? rank + 1 : MPI_PROC_NULL;
// 把自己最右邊的格子送給右鄰，同時從左鄰收到 ghost u[0]
MPI_Sendrecv(&u[m], 1, MPI_DOUBLE, right, 0, &u[0],   1, MPI_DOUBLE, left,  0, MPI_COMM_WORLD, MPI_STATUS_IGNORE);
MPI_Sendrecv(&u[1], 1, MPI_DOUBLE, left,  1, &u[m+1], 1, MPI_DOUBLE, right, 1, MPI_COMM_WORLD, MPI_STATUS_IGNORE);
```

- **Deadlock**：兩個 rank 都先 `MPI_Send` 再 `MPI_Recv`。標準模式 send 可能要等到對方開始接收才返回（是否先緩衝由實作決定，小訊息常會緩衝、大訊息不會）→ 小測資正常、大測資卡死。修法：`MPI_Sendrecv`、奇偶 rank 交錯順序、或 `Isend/Irecv + Waitall`。
- **重疊通訊與計算**：先 `Irecv`/`Isend` 邊界 → 計算不需要 ghost 的內部格子 → `Waitall` → 計算邊界格子。

---

## 9. 通訊優化通則（MPI、socket、ROS 2、UART/USB 都適用）

| 手法 | 說明 | 代價 |
|---|---|---|
| 批次化（batching / aggregation） | 多筆小訊息合成一筆，省 (k−1)·α | 延遲增加（要湊批）；要訂批次上限與逾時 |
| 少傳 | 只傳需要的欄位、用小型別、只傳變化量 | 程式較複雜 |
| 就地計算（move compute to data） | 在資料所在處先歸約 / 過濾再傳 | |
| 重疊（overlap） | 非阻塞傳送 + 先算不依賴的部分；雙緩衝（DMA 填 A 時 CPU 算 B，見 `pico-dma.md`）| 需要兩倍緩衝 |
| 零複製 | 共享記憶體、`unique_ptr` intra-process、DMA | 生命週期管理 |
| 減少 hop | A→B→C 合成一個 process 或直接 A→C | 失去隔離 |
| 減少同步點 | 不要每步都 barrier / 等 ack；用 credit（允許 k 筆未確認）| 錯誤處理較複雜 |
| 降低 per-message 成本 | 換低開銷傳輸（同機 shared memory / Unix socket 取代 TCP）；關閉高頻 log | |

量測順序：先量「一筆空訊息的往返時間」（≈ 2α）與「大訊息的吞吐量」（≈ 1/β），再決定該批次化還是減量。

---

## 10. 分散式系統基本觀念（實務版）

| 觀念 | 重點 | 在考試情境的意義 |
|---|---|---|
| 時鐘 | 不同機器的牆鐘不同步；量經過時間用 `CLOCK_MONOTONIC`（不會被 NTP 調回去）；`CLOCK_REALTIME` 只用來標記日期時間 | 跨裝置延遲（pico ↔ host）不能直接相減兩邊的時間戳；用往返時間 / 2 估單程，或只在同一台機器上相減 |
| 順序 | 單一連線（TCP、同一 publisher→subscriber、MPI 同一對 rank）通常保序；多來源之間沒有全域順序。Lamport 邏輯時鐘：每個事件計數 +1，收訊息時取 max(本地, 訊息)+1 → 得到與因果一致的順序 | 多個 worker 的結果要依「序號」排序後再輸出 |
| 序號 | 每則訊息帶遞增 sequence number | 偵測遺失（跳號）、重複（相同號）、亂序（倒退）|
| 冪等（idempotent） | 重複執行同一請求結果不變（「設成 5」是冪等，「加 1」不是） | 重送時不會重複計算；配合序號去重 |
| 重送與逾時 | 等不到回應就重送；逾時要大於正常往返時間；重送間隔指數退避（+ 隨機抖動）避免同步風暴 | |
| 傳遞語意 | at-most-once：不重送，可能遺失（≈ BEST_EFFORT）；at-least-once：重送直到確認，可能重複（≈ RELIABLE）；exactly-once：實務上 = at-least-once + 冪等 / 去重 | 選 QoS 的依據 |
| Backpressure | 下游處理不完時要讓上游知道：阻塞上游（有界佇列）、丟棄（最舊或最新）、或降低上游速率 | 無界佇列 = 記憶體成長 + 延遲無限增加 |
| 失效偵測 | 心跳（heartbeat）+ 逾時；逾時只能說「懷疑」，分不清是對方掛了還是很慢 | ROS 2 的 liveliness / deadline QoS 就是這類機制 |
| 一致性 | 強一致（每次讀到最新寫入）vs 最終一致（暫時可能讀到舊值）；網路分割時無法同時保證一致與可用（CAP） | 多 node 共用狀態時：只讓一個 node 擁有寫入權（single writer），其他人訂閱 |

---

## 11. ROS 2 作為分散式系統

基礎（CLI、QoS 表、executor、callback group、intra-process 程式碼、環境變數）見 `ros2.md`。本節講**系統層級的設計與優化**。

### 11.1 Discovery 與部署拓撲

- DDS discovery 讓同一 `ROS_DOMAIN_ID` 的參與者自動互相發現（預設 domain 0；範圍與 `ROS_AUTOMATIC_DISCOVERY_RANGE` 見 `ros2.md` 2.9）。
- UDP 埠：基底 7400 + 250 × domain ID；discovery multicast = +0，user multicast = +1，discovery unicast = +10 + 2×participant ID，user unicast = +11 + 2×participant ID。每個 participant 佔 2 個埠 → 單機超過約 120 個 ROS 2 process 可能溢到別的 domain 的埠（官方 About-Domain-ID）。
- **Node 與 participant 的對應**（Foxy 起）：一個 **context（通常 = 一個 process）一個 DDS participant**，不是一個 node 一個。官方設計文件列出的理由：每個 participant 都參與 discovery（CPU 與網路負擔）、各自追蹤其他實體（記憶體重複）、各自開執行緒。→ **同一 process 放多個 node 比多個 process 便宜**。

| 部署 | 通訊路徑 | 每筆成本 | 隔離 | 平行 |
|---|---|---|---|---|
| 同 process、intra-process 開啟（rclcpp） | 指標傳遞（`unique_ptr` 可零複製） | 最低 | 無（一個崩全崩） | 靠 MultiThreadedExecutor + callback group |
| 同 process、未開 intra-process | 經 RMW（序列化） | 中 | 無 | 同上 |
| 同機不同 process | DDS（Fast DDS 同機通常走共享記憶體傳輸，⚠️依 RMW 設定）| 中 | 有 | 真正多核（Python 也能繞過 GIL） |
| 不同 container / 機器 | UDP 網路 | 高 | 有 | 有 |

### 11.2 Component container（composition）

```bash
ros2 run rclcpp_components component_container        # SingleThreadedExecutor
# component_container_mt：MultiThreadedExecutor；component_container_isolated：每個 component 一個 executor
ros2 component types                                    # 列出可載入的 component
ros2 component load /ComponentManager <pkg> <pkg::Class> -e use_intra_process_comms:=true
ros2 component list
ros2 component unload /ComponentManager <id>
```

- Component 是編成 shared library 的 `rclcpp::Node` 子類別（`RCLCPP_COMPONENTS_REGISTER_NODE` 巨集 + CMake `rclcpp_components_register_node(s)`）。好處：部署時才決定要「各自 process（隔離）」或「同一 process（低開銷、可 intra-process）」。
- `ros_core` variant 沒直接列 `rclcpp_components`，但 `ros2cli_common_extensions` 內的 `ros2component` 執行期依賴它 → 推論考場容器有（⚠️未實測：`ros2 pkg executables rclcpp_components`）。官方 `composition` 範例套件只在 desktop variant，考場大概沒有。
- 只有 rclcpp 有 component / intra-process；rclpy 沒有。

### 11.3 Executor 與平行 callback（摘要）

- 只換成 MultiThreadedExecutor 不夠，callback 要分到不同 callback group（或 Reentrant）才會並行；共享資料要加鎖（`ros2.md` 5.3）。
- rclpy 受 GIL 限制：CPU 密集的 callback 要嘛改 C++，要嘛拆成**多個 process**（多個 node 程式），由 DDS 在 process 間傳遞。
- 不要在 callback 內做長時間阻塞；把重活交給 worker thread（thread pool），callback 只負責放入佇列與發布結果。

### 11.4 流水線：找瓶頸 stage

```
/sensor (pub) → /filter → /detect → /output (sub)
```

```bash
ros2 topic hz /raw            # 每段輸出的頻率：第一個「頻率明顯下降」的地方就是瓶頸 stage
ros2 topic hz /filtered
ros2 topic hz /detections
ros2 topic bw /raw            # 訊息大小 × 頻率 = 頻寬；大訊息先懷疑序列化 / 複製
ros2 topic delay /detections  # 需要 header.stamp：now − stamp，代表從源頭到這裡的累積延遲
ros2 topic info -v /filtered  # 看每端的 QoS（depth、reliability）
```

- 頻率一路相同但延遲逐段增加 → 某段有排隊（佇列深 + 處理慢）。
- 延遲量測：在源頭把時間戳放進 `header.stamp`，每個 stage **原樣轉傳**，終點計算 `now − stamp`（同機才準；跨機器有時鐘偏差，§10）。
- 也可以在訊息中帶序號，終點統計跳號 = 遺失率。
- 量測工具本身（`hz`/`echo`）是 Python node，會吃 CPU、極高頻時不準（`ros2.md` 2.2）；正式比較時在程式裡計時。

### 11.5 QoS 作為 backpressure / 佇列控制

| 需求 | QoS | 行為 |
|---|---|---|
| 只要最新值（控制、顯示、感測） | `KEEP_LAST` depth 1–5 + `BEST_EFFORT` | 消費者慢時舊資料被覆蓋 → 延遲有上限，丟舊留新 |
| 每筆都要（記錄、計數類題目） | `RELIABLE` + 足夠大的 depth（或 `KEEP_ALL`） | 消費者長期慢於生產者時，佇列終究會滿，KEEP_LAST 仍會丟（`ros2.md` 3.6） |
| 真正的流量控制 | ROS 2 topic **沒有**端到端 backpressure 的標準 API；要自己做：下游回報 ack / credit，上游依此限速，或用 service / action 一次一筆 | ⚠️ DDS 在 RELIABLE + KEEP_ALL 且資源滿時 publish 可能阻塞，依 RMW 設定而異（未驗證）|

- 從 Little's law：depth 越大 → 允許排隊越多 → 穩態延遲越大。延遲題目把 depth 調小；完整性題目讓消費者變快（而不是只加大 depth）。

### 11.6 訊息批次化與切分工作

- 高頻小訊息（例如 1 kHz 的 `Int32`）：per-message 開銷（序列化、DDS、executor 排程、Python 轉換）主導 → 合成陣列訊息（例如每 10 ms 送一個 `Int32MultiArray`，或自訂含 `int32[]` 的 msg），頻率降 10 倍、資料量不變。代價：延遲最多增加一個批次週期。
- 大訊息（影像、點雲）：頻寬與複製主導 → 同 process + intra-process + `unique_ptr`；降低解析度 / 頻率；只傳 ROI。

| 拆成多個 node（多 process）| 在一個 node 內用多執行緒 |
|---|---|
| 真多核（含 Python）；崩潰隔離；可分散到多台機器 | 無序列化成本；共享記憶體；延遲低 |
| 每次跨 node 有序列化 + 傳輸成本；discovery 負擔 | 要處理鎖；Python 受 GIL；一個崩全崩 |
| 適合：stage 之間資料小、每 stage 計算大 | 適合：資料大、stage 間通訊頻繁 |

---

## 12. RP2350 + host 的異質平行

RP2350 硬體與 API 細節見 `pico-sdk.md`、`multicore-sync.md` Part B、`pico-dma.md`、`pio.md`。本節是「把它們當成平行單元來規劃」。

### 12.1 可用的平行單元

| 單元 | 數量（RP2350） | 適合 | 不適合 |
|---|---|---|---|
| CPU core0 / core1 | 2（Cortex-M33 或 Hazard3 RISC-V，開機時選架構）| 一般運算；一核 I/O、一核計算 | — |
| DMA channel | 16 | 搬資料、memcpy / memset、餵 PIO / UART、與 CPU 並行 | 需要逐元素運算的轉換（除了 sniffer CRC / sum） |
| PIO state machine | 12（3 block × 4 SM） | 精確時序的位元 I/O、自訂協定、序列化 / 反序列化位元 | 一般算術（每 block 只有 32 條指令空間）|
| 其他硬體輔助 | 每核 2 個 interpolator（位移 + 遮罩 + 加法，`pico-sdk.md` 7.6）、DMA sniffer（CRC / 加總）；RP2350 **沒有** SIO 硬體除法器（改用 CPU 除法指令） | 查表索引、checksum | 一般運算 |
| Host（Linux） | 多核、記憶體大 | 重運算、ROS 2、記錄 | 精確時序、低延遲 I/O |

### 12.2 典型分工

```
[PIO] 擷取 / 產生位元流 ──DMA──▶ [SRAM 緩衝 A/B] ──▶ [core1 運算] ──queue_t──▶ [core0 打包 + USB/UART] ──▶ [host 程式 / ROS 2 node]
```

- 這是一條**跨裝置流水線**：吞吐量 = 最慢的那段。逐段量測：
  - PIO / DMA：時脈與 FIFO 決定的理論速率（`pio.md` §7）；DMA 完成中斷間隔。
  - core 運算：`time_us_64()` 或 cycle counter 包住處理一個 block 的時間（`pico-sdk.md` 量測）。
  - 連結：UART 115200 ≈ 11.5 kB/s；USB full-speed 名目 12 Mbit/s，實際 CDC 吞吐量較低（⚠️未驗證具體數字，自己量）。
  - host：程式內計時。
- **連結常是瓶頸** → 在 pico 端先歸約 / 過濾（move compute to data），只送結果；或用二進位批次格式（§7.3）。
- **雙緩衝**：DMA 填 A 時 core 處理 B，完成後交換（`pico-dma.md` 範例）。這是「通訊與計算重疊」的 MCU 版本。
- **兩核分工**：資料分割（各做一半，最後合併）vs 流水線（一核 I/O 一核運算），選擇表見 `multicore-sync.md` B11.3。兩核最多 2 倍（Amdahl），而 DMA / PIO 是「額外」的平行單元，常常比第二顆核心更划算。
- **host 卸載**：運算量大、時序不敏感 → 送到 host；時序敏感、資料量大 → 留在 MCU 先處理。判斷式：`傳輸時間(原始資料) + host 計算時間` vs `MCU 計算時間 + 傳輸時間(結果)`。

### 12.3 跨裝置量測注意

- 兩邊時鐘不同步：用「host 送 ping → pico 立刻回 → host 量往返」估連結延遲；單程 ≈ RTT/2（假設對稱）。
- pico 端計時結果用批次方式回傳（例如每 1000 筆回報一次統計），不要每筆印，否則量測本身改變了結果。

---

## 13. 確定性：讓平行版輸出和 serial 一模一樣（judge diff 關鍵）

| 問題 | 原因 | 修法 |
|---|---|---|
| 輸出行順序隨機 | 多執行緒 / 多 process 各自 `printf` | **平行計算 → 結果存到 `out[i]` → 序列依 i 輸出**；或 `ordered`（會序列化那段） |
| stdout 交錯、半行 | 多 process 共用 stdout；緩衝 | 只讓一個執行緒 / rank 0 輸出 |
| 浮點總和末位不同 | 加法不滿足結合律；reduction 合併順序隨執行緒數與排程改變 | 若 judge 要求逐位元相同：把資料切成**固定大小**的塊（與執行緒數無關），每塊各自加總存 `part[b]`，最後**依 b 順序**序列加總 → 任何執行緒數結果都相同 |
| 整數結果偶爾錯 | data race | `reduction` / atomic / per-thread partial；TSan |
| 隨機數結果不同 | 共用 PRNG 的呼叫順序不定 | 每個**工作項**（不是每個執行緒）用由索引推導的種子 |
| 合併 map / set 時順序不同 | hash map 迭代順序、執行緒完成順序 | 合併後排序再輸出 |
| 計時資訊混進 stdout | 量測輸出被 judge 比對 | 計時印到 `stderr` |

固定分塊確定性求和：

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
（注意：與完全序列的 `for i: s += a[i]` 仍可能差末位，因為分組方式不同；若必須與 serial 參考答案逐位元相同，serial 版也要用同樣的分塊加法，或題目允許誤差。）

---

## 14. 完整範例：OpenMP 直方圖，從 atomic 到 per-thread partial

題目型態：`N` 個 byte，統計 256 個 bin 的出現次數。

```c
#include <stdio.h>
#include <string.h>
#include <omp.h>
#define N  (1 << 26)
#define NB 256
static unsigned char data[N];
static long h_serial[NB], h_atomic[NB], h_local[NB], h_red[NB];

int main(void) {
    /* ...填入 data... */
    double t;

    // 版本 0：serial（基準）
    t = omp_get_wtime();
    for (long i = 0; i < N; i++) h_serial[data[i]]++;
    fprintf(stderr, "serial %.3f s\n", omp_get_wtime() - t);

    // 版本 1：天真的 atomic —— 正確，但每次都爭搶同一組 cache line
    t = omp_get_wtime();
    #pragma omp parallel for
    for (long i = 0; i < N; i++) {
        #pragma omp atomic
        h_atomic[data[i]]++;
    }
    fprintf(stderr, "atomic %.3f s\n", omp_get_wtime() - t);

    // 版本 2：每執行緒私有直方圖，最後合併一次（NB 次 atomic / 執行緒）
    t = omp_get_wtime();
    #pragma omp parallel
    {
        long local[NB] = {0};                 // 在 region 內宣告 → private，在自己的 stack
        #pragma omp for nowait                // 合併不需要等別人做完迴圈
        for (long i = 0; i < N; i++) local[data[i]]++;
        for (int b = 0; b < NB; b++) {
            #pragma omp atomic
            h_local[b] += local[b];
        }
    }                                         // region 結尾的隱含 barrier 保證合併完成
    fprintf(stderr, "local  %.3f s\n", omp_get_wtime() - t);

    // 版本 3：交給 reduction 子句（陣列區段，OpenMP 4.5）
    t = omp_get_wtime();
    #pragma omp parallel for reduction(+:h_red[:NB])
    for (long i = 0; i < N; i++) h_red[data[i]]++;
    fprintf(stderr, "reduct %.3f s\n", omp_get_wtime() - t);

    // 驗證 + 確定性輸出（只輸出到 stdout 的才是答案）
    if (memcmp(h_serial, h_local, sizeof h_serial) || memcmp(h_serial, h_red, sizeof h_serial))
        fprintf(stderr, "MISMATCH\n");
    for (int b = 0; b < NB; b++) printf("%d %ld\n", b, h_local[b]);
    return 0;
}
```

本機實測（x86-64、GCC 13.3、`-O2 -fopenmp`、N = 2^26；數字只代表量級與相對關係，考場機器會不同）：

| 版本 | 1 執行緒 | 4 執行緒 | 12 執行緒 | 解讀 |
|---|---|---|---|---|
| serial | 0.018 s | — | — | 基準 |
| atomic | 0.125 s | 0.399 s | 0.191 s | 比 serial 慢約 7–22 倍：atomic 本身有成本，多執行緒時同一 cache line 在核心間彈跳 |
| critical（同樣每次一進） | 0.274 s | 4.3 s | 12.1 s | 執行緒越多越慢：全域鎖完全序列化 + 鎖競爭 |
| per-thread local | 0.018 s | 0.005 s | 0.004 s | 約 3.6–4.5 倍；受記憶體頻寬與 region 開銷限制 |
| reduction 子句 | 0.032 s | 0.008 s | 0.006 s | 與 local 同級；runtime 幫你做 per-thread 副本 |

所有版本結果都與 serial 完全相同（整數加法結合律成立）。

延伸：
- bin 數很大（例如 2^20）：每執行緒一份完整直方圖太大 → 放 heap（`calloc(T*NB)`，T = `omp_get_max_threads()`）；或先依 bin 範圍分區（每執行緒只負責一段 bin，但要掃全部資料）。
- bin 數很小（例如 2–8）且只用 per-thread 陣列 `long part[T][NB]` 時，相鄰執行緒的列可能同在一條 cache line → false sharing；每列補到 64 bytes 的倍數（`multicore-sync.md` A8）。本機 `-O0` 下「每次迭代直接寫 `partial[tid]`」比「區域變數累加」慢約 30 倍；`-O2` 下編譯器常把它放進暫存器而看不出差異 → 不要依賴這點，寫成區域變數。
- pthread 版、pico 雙核版的同一個模式：`multicore-sync.md` A9、B11.1。

---

## 15. 常見 bug 對照表

| Bug | 症狀 | 偵測 | 修法 |
|---|---|---|---|
| Data race（共享變數未保護） | 結果偶爾錯、每次不同、開優化後才錯 | TSan（`-fsanitize=thread`）、`OMP_NUM_THREADS=1` 對照、跑多次比對 | reduction、per-thread partial、atomic、鎖 |
| Deadlock（鎖順序、barrier 在分支內、MPI 互相 Send、callback 同步呼叫 service） | 程式卡住、CPU 0% | `gdb` → `thread apply all bt`；ROS 2 看 executor 設定 | 固定加鎖順序；所有執行緒經過相同 barrier；Sendrecv；`call_async` |
| Livelock / 忙等 | 卡住但 CPU 100% | `top -H` 看執行緒 | 改用阻塞等待（cond var、semaphore） |
| 輸出順序不定 | judge diff 失敗但內容都對 | 跑兩次 diff 自己的輸出 | 存陣列、序列輸出；排序 |
| 浮點不確定 | 末幾位數變動 | 改執行緒數比較 | 固定分塊 + 依序合併（§13） |
| 超額訂閱（oversubscription） | 加執行緒變慢、`sys` 時間高、context switch 多 | `time`、`perf stat -e context-switches`（若有）、`top` | 執行緒總數 ≤ 可用核心；OpenMP × 多 process × MultiThreadedExecutor 要相乘計算；`OMP_WAIT_POLICY=PASSIVE` |
| False sharing | 結果正確但多執行緒幾乎不加速 | 改成區域變數後明顯變快；`perf c2c`（若有） | 區域累加；padding 到 64 bytes |
| 粒度太細 | 平行比 serial 慢 | 量每個任務的時間 vs 任務數 | 加大 chunk；cutoff；`if` 子句 |
| 不平衡 | 一個執行緒最後還在跑 | 每執行緒計時 | dynamic / guided；大的先排 |
| 執行緒 / process 建立在熱迴圈中 | 很慢、`sys` 時間高 | profile | thread pool；parallel region 移到外層 |
| 共享 PRNG / 非 thread-safe 函式（`rand`、`strtok`、`localtime`） | 結果怪、偶爾崩 | 讀 man page 的 MT-Safe 標記 | `rand_r`、`strtok_r`、`localtime_r` |
| fork 後 stdout 重複輸出 | 某些行出現兩次 | 重導到檔案時才出現 | fork 前 `fflush`；子 process `_exit` |
| 第一個 parallel region 特別慢 | 計時包含執行緒建立 | 重複量 | 熱身一次再計時 |
| ROS 2 前幾筆訊息遺失 | publish 太早，discovery 未完成 | `count_subscribers` | `ros2.md` 3.6 |
| ROS 2 延遲越來越大 | 消費者慢 + depth 大 → 佇列排隊 | `ros2 topic delay`、在訊息中帶時間戳 | 小 depth；讓消費者變快；批次化 |

---

## 16. 除錯檢查清單

1. 先讓 `OMP_NUM_THREADS=1`（或單 process）版本與 serial 輸出完全相同。
2. 再用 2、4、N 執行緒各跑 5 次，`diff` 輸出；不同 → race 或順序問題。
3. `gcc -fsanitize=thread -g -O1`（OpenMP 可能誤報，對照 pthread 版或看是否落在自己的變數）；新核心上配 `setarch -R`。
4. `-Wall` 看有沒有 `-Wunknown-pragmas`（代表沒加 `-fopenmp`，其實沒有平行）。
5. 印 `omp_get_num_threads()`（在 region 內）確認真的有 N 個執行緒；`OMP_DISPLAY_ENV=true` 看設定。
6. `time ./x`：`user+sys` ≈ `real` × N 表示有在平行；`real` 沒降但 `user` 大增 → 忙等 / 競爭 / 超額訂閱。
7. 卡住 → `gdb -p <pid>` 或 Ctrl-C → `thread apply all bt`，看大家等在哪個鎖 / barrier / Recv。
8. 多 process：檢查是否關閉不用的 pipe 端、是否處理 partial read/write、子 process 是否 `_exit`。
9. ROS 2：逐段 `ros2 topic hz`、`ros2 topic info -v` 看 QoS、`ros2 node info` 看連線（`ros2.md` §7 除錯階梯）。
10. pico + host：分段計時；先量連結的原始吞吐量，再加上處理。

---

## 17. 設計 / 優化檢查清單

**設計（寫程式前）**
- [ ] 量了 serial 版本的總時間與熱點比例 p；算出 Amdahl 上限，值得做嗎？
- [ ] 確認可用核心數（`nproc`、cgroup）與 judge 的計時方式（⚠️ wall vs CPU time）
- [ ] 選模式：map / reduction / pipeline / master–worker / fork–join / stencil
- [ ] 選粒度：任務數 ≈ 核心 × 4–16，每任務遠大於排程開銷；小輸入不平行（`if` 子句）
- [ ] 資料歸屬：每份資料只有一個寫入者；共享只讀；結果寫到依索引分開的位置
- [ ] 通訊：算過 α–β？要不要批次化？能不能在資料所在處先歸約？
- [ ] 輸出：平行計算、序列輸出；浮點要不要固定分塊？

**實作**
- [ ] `default(none)` 標清楚每個變數
- [ ] 累加用 reduction 或 per-thread partial，熱迴圈內沒有 critical / atomic / mutex
- [ ] 沒有在熱迴圈中建立執行緒 / process / parallel region
- [ ] 多執行緒寫入的相鄰小變數有 padding 或改區域變數
- [ ] 不規則負載用 `dynamic`/`guided` 並調 chunk

**驗證與報告**
- [ ] 1 / 2 / 4 / N 執行緒的輸出與 serial 完全一致，各跑多次
- [ ] 計時表：N、T_N、S、E、Karp–Flatt e（中位數，計時輸出到 stderr）
- [ ] 熱身後計時；排除 I/O 或分開列出
- [ ] e 隨 N 增加 → 找開銷（同步、通訊、不平衡）；e 不變 → 優化序列部分

---

## 18. 向模型提問的範本

### 18.1 值不值得平行化 + 選模式

```
我有一支程式要優化，環境：{{Linux 容器 / RP2350 / ROS 2 多 node}}，可用核心 {{nproc 輸出}}，judge 計時方式 {{wall time / CPU time / 未知}}。
serial 版量測：總時間 {{T}}，熱點 {{函式名}} 佔 {{比例}}，熱點的程式碼如下：
{{貼上熱點程式碼}}
資料大小 {{N}}，每筆工作的成本 {{均勻 / 不均勻，描述}}，迭代之間 {{有 / 沒有}} 相依。
請：1) 用 Amdahl 算加速上限；2) 判斷適合哪種分解模式（map / reduction / pipeline / master-worker / fork-join / stencil）並說明理由；
3) 指出 race、false sharing、輸出順序等風險；4) 給出最小修改的 OpenMP 或 pthread 版本，輸出必須與 serial 逐位元相同。
參考資料：parallel-distributed.md、multicore-sync.md。
```

### 18.2 OpenMP 版本變慢或結果不對

```
這段 OpenMP 程式 {{比 serial 慢 / 結果每次不同 / 末位數不同}}。
編譯指令：{{gcc ... -fopenmp}}；OMP_NUM_THREADS={{值}}；
量測：1 執行緒 {{t1}}、{{k}} 執行緒 {{tk}}；time 的 real/user/sys = {{...}}。
程式碼：
{{貼上 parallel region 與相關變數宣告}}
請逐一檢查：每個變數的 data-sharing 屬性（是否該 private / reduction）、熱迴圈內的 critical/atomic、false sharing、
schedule 與 chunk、region 是否在熱迴圈內反覆進出、超額訂閱。列出問題、修正後的程式碼，以及預期變化。
```

### 18.3 流水線 / ROS 2 多 node 找瓶頸

```
系統是一條流水線：{{stage1 → stage2 → stage3（每段是 ROS 2 node / 執行緒 / 裝置）}}。
各段量測：{{ros2 topic hz 每個 topic 的頻率、ros2 topic delay、或每段處理時間}}；QoS：{{depth / reliability}}；
語言：{{rclpy / rclcpp}}；部署：{{同 process / 不同 process / 不同 container}}。
目標：{{提高吞吐量到 X Hz / 降低端到端延遲到 Y ms / 不能掉訊息}}。
請用「吞吐量 = 1/max(stage 時間)」和 Little's law 分析瓶頸，提出依效益排序的改法
（拆 stage、多 worker、批次化、改 QoS depth、intra-process / component container、改 C++、MultiThreadedExecutor + callback group），並說明每個改法的代價。
```

### 18.4 MCU + host 分工

```
硬體：RP2350（2 核 + 16 DMA channel + 12 PIO SM）透過 {{USB CDC / UART 115200}} 連到 Linux host。
資料流：{{來源（PIO / ADC / GPIO）}} → {{處理步驟}} → {{輸出 / host 端程式}}。
每段量測：{{PIO/DMA 速率、core 處理一個 block 的 µs、連結吞吐量、host 處理時間}}。
請畫出跨裝置流水線，算每段的吞吐量找出瓶頸，判斷哪些運算應該留在 MCU（先歸約 / 過濾）或卸載到 host，
並設計雙緩衝 / 兩核分工 / 批次二進位格式。引用 multicore-sync.md、pico-dma.md、pio.md 的 API，不確定的標 ⚠️。
```

### 18.5 多 process / 訊息傳遞設計

```
因為 {{Python GIL / 需要隔離 / 跨機器}}，我想把工作拆成 {{K}} 個 process。
可用機制：{{pipe / Unix socket / shm_open+mmap / ROS 2 topic / MPI（請先確認是否安裝）}}。
每個任務輸入 {{大小}}、輸出 {{大小}}、計算時間約 {{t}}。
請用 α–β 模型估算通訊成本與合適的批次大小，給出 fork + 共享記憶體（或指定機制）的最小實作，
處理 partial read/write、EOF、子 process 結束與錯誤，並保證最後依任務編號順序輸出。
```
