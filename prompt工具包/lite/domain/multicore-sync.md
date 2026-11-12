# 並行與多核同步速查（pthread + RP2350/pico-sdk）

> 用途：共享資料、鎖、雙核優化題。適用：C11、glibc、pico-sdk 2.3.1、RP2350 datasheet 2026-01。
> 來源：github.com/raspberrypi/pico-sdk 標頭、rp2350-datasheet.pdf、man7.org、cppreference。
> 最後更新 2026-11。與考場文件衝突時以考場文件為準。

## 核心原則
1. `x++` = 讀/加/寫三步，並行會掉更新。`volatile` 不是同步。
2. 最快是不共享：每執行緒/每核區域累加，最後合併一次（demo counter 正解；`sink` 也是 race）。
3. 單一整數用 atomic；多欄位一起改才用鎖；鎖內只放讀寫，計算/printf 移出去。
4. 執行緒數 > CPU 數（`nproc`）時 spinlock 會空轉，改 mutex。
5. Linux false sharing：各執行緒寫的變數 `alignas(64)` 分開。

## POSIX / C11
- `pthread_mutex_lock/unlock`、`pthread_spin_init(&l, PTHREAD_PROCESS_PRIVATE)`；pthread 失敗回傳錯誤碼。
- condvar：`while(!cond) pthread_cond_wait(&cv,&m);`（不能用 if）。
- `sem_init(&s,0,n)`、`sem_wait`、`sem_post`（失敗回傳 -1 並設 errno）。
- `atomic_fetch_add_explicit(&c, local, memory_order_relaxed)` 回傳舊值。發布資料：寫資料 → release store；讀方 acquire load。
- `pthread_join` 建立 happens-before，join 後讀結果。
- 計時 `clock_gettime(CLOCK_MONOTONIC,&ts)`，多跑取中位數。
- 偵錯 `gcc -fsanitize=thread -g -O1`（慢 5–15 倍）、`valgrind --tool=helgrind`、gdb `thread apply all bt`。編譯加 `-pthread`。
- Amdahl：S=1/((1-p)+p/N)；2 核最多 2 倍。
- Deadlock：固定拿鎖順序。

## RP2350 vs RP2040
| | RP2350 | RP2040 |
|---|---|---|
| 核心 | 2×M33 或 2×Hazard3 | 2×M0+ |
| FIFO 每方向 | **4 格** | 8 格 |
| atomic 1/2/4B | lock-free | spinlock 模擬 |
| HW spinlock | 32，有 E2 | 32 |
| DMA ch | 16 | 12 |

## pico API（CMake 加 `pico_multicore`）
- `multicore_launch_core1(void(*)(void))`、`multicore_reset_core1()`；launch 用 FIFO 握手。
- core1 stack 預設 2KB（`PICO_CORE1_STACK_SIZE`）在 SCRATCH_X；大陣列改 static。
- FIFO：`multicore_fifo_push_blocking(u32)`、`_pop_blocking()`、`_rvalid()`、`_wready()`、`_drain()`。SDK 建議資料傳遞用 queue；只傳指標/索引。lockout 會佔用 FIFO。
- `queue_init(&q,size,count)`、`queue_add_blocking`、`queue_remove_blocking`、`queue_try_add/remove`（ISR 用 try）。元素 memcpy；`queue_init` 回傳 void，內部 calloc 不檢查失敗。
- `critical_section_init/enter_blocking/exit`：關本核 IRQ + spinlock，跨核+ISR 安全，極短，不可重入。
- `mutex_init/enter_blocking/exit/try_enter(&m,NULL)`：可持久，ISR 不可阻塞。
- `sem_init(&s,init,max)`、`sem_acquire_blocking`、`sem_release`。
- `spin_lock_init(spin_lock_claim_unused(true))`；`save=spin_lock_blocking(l)`…`spin_unlock(l,save)`。
- `save_and_disable_interrupts()`/`restore_interrupts(s)` 只擋本核。屏障 `__dmb()`。
- 計時 `time_us_64()`、`absolute_time_diff_us(t0,get_absolute_time())`。
- stdout 有 mutex，兩核 printf 不會撕裂但順序不定；熱迴圈勿 printf。

## RP2350-E2
寫 SIO 0x180–0x1FC 會誤釋放低 0x80 的 spinlock（A2 有；A4 公告未列為已修）。SDK 預設 `PICO_USE_SW_SPIN_LOCKS`（RAM byte + ldaex/strex 或 amoor），API 不變。不要直接寫 `sio_hw->spinlock[]`；編號用 `PICO_SPINLOCK_ID_*`。

## SRAM
- 0x20000000 起 256KB 交錯 SRAM0–3、0x20040000 起 256KB 交錯 SRAM4–7（每 4B 換 bank）。
- SRAM8 0x20080000 = SCRATCH_X（core1 stack）、SRAM9 0x20081000 = SCRATCH_Y（core0 stack），各 4KB。
- 不同 bank 可同週期並行；兩核/DMA 搶同 bank 才互等。單核熱資料 `__scratch_x("g")`；熱函式 `__not_in_flash_func(f)`。
- 跨核 exclusive 靠 global monitor，只涵蓋 SRAM（不含 XIP/PSRAM）→ atomic 放 SRAM；granule 16B ⚠️未查證。

## DMA（對應 demo engine）
`dma_claim_unused_channel(true)` → `dma_channel_get_default_config`（預設 write 不遞增！）→ `channel_config_set_transfer_data_size/_read_increment/_write_increment` → `dma_channel_configure(ch,&c,dst,src,dma_encode_transfer_count(n),true)`（n 是筆數不是 bytes；SDK < 2.2 沒有這函式 → 直接填 n）→ 做別的事 → `dma_channel_wait_for_finish_blocking` 後才讀 dst。

## ISR / 雙核共享
- 同核 ISR↔主迴圈：單 word 旗標 volatile；多欄位或 64-bit 讀取時關中斷。
- 跨核：critical_section、atomic 或 queue；只關中斷不夠。
- 雙核分工：core1 算後半、區域累加，結果寫好後 `__dmb()` 再 push FIFO 通知；core0 pop 後 `__dmb()` 再讀、合併。

## 決策樹
需要共享？否→區域累加+合併。能切分？是→各做一段。單值→atomic；傳遞→SPSC/queue；多欄位→鎖且縮短。再查 false sharing/bank 衝突、spinlock 超額、迴圈內建執行緒。每步量測+驗正確。
