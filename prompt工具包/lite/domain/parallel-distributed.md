# 平行與分散式（精簡版）
用途：備援包；平行/分散式設計與優化。鎖/atomic/pico 雙核見 multicore-sync.md，ROS 2 基礎見 ros2.md。
適用：GCC 13 libgomp、Ubuntu 24.04、ROS 2 Jazzy、RP2350。來源：openmp.org spec 5.0、gcc.gnu.org/onlinedocs/libgomp、docs.open-mpi.org、man7、ROS 2 docs/design；本機實測。最後更新 2026-11

## 先決定值不值得
nproc + `/sys/fs/cgroup/cpu.max`；judge 量 wall 或 CPU time（⚠️未知）；量 p 算上限；每任務遠大於 region/barrier 開銷；有迴圈相依→scan/改演算法

## 常見 bug
| bug | 修法 |
|---|---|
| race（結果每次不同）| reduction/per-thread；TSan（新核心加 `setarch -R`）|
| deadlock | 固定鎖序；barrier 不放分支；Sendrecv；`gdb thread apply all bt` |
| 輸出順序亂 | 存陣列序列輸出 |
| 超額訂閱 | 執行緒總數≤核心（OpenMP×process×executor 相乘）|
| 粒度太細/不平衡 | 大 chunk、cutoff、dynamic |
| `rand`/`strtok` | `rand_r`/`strtok_r` |

## 理論
- S=T1/TN，E=S/N。Amdahl `1/((1-p)+p/N)`（固定大小）；Gustafson `N-(N-1)s`（s 在平行系統量）
- Karp–Flatt `e=(1/S-1/N)/(1-1/N)`：e 隨 N 變大=開銷成長；不變=序列部分
- Work/span：`TN≥max(T1/N,T∞)`，`TN≤T1/N+T∞`；parallelism=T1/T∞
- 通訊 `T=α+βn`：小訊息→批次化省 (k-1)α；大訊息→少傳/零複製/重疊
- 流水線：吞吐=1/max(t_i)，延遲=Σt_i+排隊；Little `L=λW`
- 開銷：建立、同步、通訊、不平衡、競爭、超額訂閱。粒度：任務≈核心×4–16

## 模式
map｜reduction（各自累加，最後合併一次）｜scan（兩趟 block）｜pipeline（平衡最慢 stage、有界佇列）｜fork-join tasks（要 cutoff）｜master-worker 佇列｜scatter-gather｜stencil+halo｜MapReduce
分割：block `[n*t/T,n*(t+1)/T)`、cyclic=`static,1`、dynamic/guided；成本不均→dynamic，大的先排

## OpenMP（`gcc -O2 -fopenmp`；GCC13 `_OPENMP=201511`）
- omp.h 隨 gcc（libgcc-13-dev→libgomp1）；沒 -fopenmp → pragma 被忽略
- schedule：static 不給 chunk=等分連續塊；dynamic 預設 chunk 1；guided 漸小；runtime 讀 `OMP_SCHEDULE`（libgomp 預設 dynamic,1）；沒寫=GCC 展開為 static
- `private` 未初始化；`firstprivate` 複製初值；`lastprivate`；`default(none)` 抓漏
- C 陷阱：內層迴圈變數宣告在外=shared→race
- `reduction(+:s)`、`max/min`、陣列 `reduction(+:h[:NB])`（4.5）
- `critical` 重、`atomic` 單一位置、`nowait` 去 barrier、`single`、`masked`、`ordered`
- `collapse(2)`、`parallel for simd`、`task`+`taskwait`、`if(n>X)`
- API：`omp_get_wtime/thread_num/num_threads/max_threads`
- env：`OMP_NUM_THREADS`、`OMP_PROC_BIND`、`OMP_PLACES`、`OMP_WAIT_POLICY=PASSIVE`（超額訂閱時）、`OMP_DISPLAY_ENV=true`；巢狀預設只 1 層
- 第一個 region 含建立成本→先熱身

## 直方圖實測（12 緒，N=2^26）
serial 0.018s｜每次 atomic 0.19–0.40s（更慢）｜每次 critical 4–12s｜per-thread local+合併 0.004s｜reduction 0.006s
→ 熱迴圈內不同步；false sharing：寫區域變數，padding 64B

## 多 process / IPC
- fork+`MAP_SHARED|MAP_ANONYMOUS` 結果陣列，父依序輸出；fork 前 `fflush`，子 `_exit`
- pipe 容量 64KiB，≤PIPE_BUF(4096) 原子；read/write 可能部分→迴圈；EOF 需關閉所有寫端
- `shm_open("/n",O_CREAT|O_RDWR,0600)`+`ftruncate`+`mmap`；glibc≥2.34 不需 -lrt
- Python：GIL→multiprocessing，大 chunksize，`__main__` 保護

## MPI（多半沒裝：`which mpicc`）
`MPI_Send(buf,count,type,dest,tag,comm)`、`Recv(...,src,tag,comm,&st)`、`Isend/Irecv`+`Wait`（完成前不可動緩衝）、`Bcast`、`Reduce(s,r,n,t,op,root,c)`、`Allreduce`、`Scatter/Gather`（count 為每 rank）。互相先 Send=大訊息死結→`Sendrecv`。root 執行需 `--allow-run-as-root`；`--oversubscribe`

## 分散式觀念
CLOCK_MONOTONIC 量時間；跨機時鐘不同步→RTT/2；序號偵測遺失/重複/亂序；冪等+去重≈exactly-once；at-most-once≈BEST_EFFORT、at-least-once≈RELIABLE；有界佇列=backpressure；心跳+逾時

## ROS 2
- 一 process 一 DDS participant（Foxy+）→同 process 多 node 較省
- `ros2 run rclcpp_components component_container`；`ros2 component load /ComponentManager pkg pkg::Cls -e use_intra_process_comms:=true`（rclcpp only）
- 逐段 `ros2 topic hz` 找頻率掉的 stage；`bw` 看大小；`delay` 需 header.stamp
- 低延遲：KEEP_LAST 小 depth；高頻小訊息→陣列批次；Python CPU 重→拆多 process
- topic 無端到端 backpressure，要自己 ack/credit

## RP2350+host
2 核、16 DMA、12 PIO SM；跨裝置流水線逐段量；UART 115200≈11.5kB/s 常是瓶頸→MCU 先歸約、二進位批次、雙緩衝

## 確定性（judge diff）
平行算→存 out[i]→序列輸出；計時印 stderr；浮點用固定大小分塊依序合併；PRNG 種子由工作索引推導
