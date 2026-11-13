# 軍火庫：優化食譜（量測 / 現象 → 食譜 → 修改前 / 修改後）
> 用法：先貼「食譜卡 優化 0」，請模型照你的現象選食譜編號 → 貼那張食譜卡（模型回「收到」）→ 貼「提示卡 套用 1/1」，附你的程式（帶行號）和量測。一次貼一張；沒變快就 `git checkout -- 檔案` 還原。
> 來源與驗證：`預製程式碼/說明書/` 第 1～7 章的食譜（N.4）與實測（N.5）；修改後的程式在副本上重新套用：Pico 端用 pico-sdk 2.2.0（pico2、ARM）編譯 0 錯誤 0 警告，電腦端用 x86_64 Python 3.13 / gcc 13.3 執行；Pico 端都沒有上板｜最後更新 2026-11-13

---

【食譜卡｜優化 0/14｜選哪個食譜：量測 / 現象 → 食譜編號】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
先量再選（沒有數字 → 先做提示卡 優化 1/6）。對到第一個符合的列，抄「食譜」那格。

| 量測 / 現象 | 食譜 | 範本檔案 |
|---|---|---|
| 一次一個數字、每包都在等回覆；文字 `"123\n"` | 1 | `ros2/serial_bridge.py`、`pico/app_serial.c` |
| 只有一片板子在算；計算時間佔大部分 | 2 | `ros2/multi_device.py` |
| micro-ROS 每則很小、`time=` 很長 | 3 | `micro-ros/host_driver.py` |
| Pico 收資料時不能算、算的時候不能收 | 4 | `pico/app_multicore.c` |
| Pico 兩核加鎖後沒變快 / 比單核慢 | 5 | `pico/app_multicore.c` |
| 電腦多執行緒加鎖、atomic 後比單執行緒慢；`count[tid]` 加執行緒沒變快 | 6 | `linux-perf/parallel_template.c` |
| CPU 複製迴圈 `dst[i] = src[i]` 佔大部分時間 | 7 | `pico/app_dma.c` |
| CRC 算很久，用的是逐位元（`for k<8`） | 8 | `algo/crc32.c` |
| CRC 已查表還是慢、題目要硬體 CRC | 9 | `pico/app_dma.c` → `app_serial.c` |
| 排序 qsort / insertion 很慢 | 10 | `algo/sort.c` |
| 多段已排序要合併、k ≥ 8 | 11 | `algo/sort.c` |
| ROS callback / 迴圈裡 print 很多；Pico 有 printf | 12 | `ros2/`、`pico/app_serial.c` |
| 單執行緒本身慢、沒動過編譯選項；熱迴圈在 flash | 13 | `CMakeLists.txt`、`linux-perf/` |
| BNN 推論慢（popcount） | 14 | `algo/bnn.h` |
| 要 PIO 取代 CPU | 無 | 說明書沒有驗證過的 PIO 加速食譜 → 看 `snippets-pico.md` 的 PIO 片段卡 |

只輸出：現象：「照抄」／食譜：編號／範本檔案：
前提：說明書第 1～7 章。
驗證：選的食譜「適用」那行要和你的現象一樣；不一樣就回來重選。

---

【食譜卡｜優化 1/14｜序列埠：文字 / 一次一個 → 二進位 + 批次】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
適用：每個數字一行 `ser.write(f"{v}\n".encode())`、每行等回覆；或 `batch_size=1`。
對應範本：`ros2/serial_bridge.py:62-68`、`:35`；Pico `pico/app_serial.c:30-42`。
修改後（ROS node 直接用 `serial_bridge.py -p batch_size:=0`）：
```python
import array
from frame import CHUNK_BYTES, CMD_SUM_U32, transact, unpack_u32
data = array.array("i", values).tobytes()            # 整批轉 bytes（serial_bridge.py:62）
step = CHUNK_BYTES // 4 * 4                          # serial_bridge.py:63
total = 0
for i in range(0, len(data), step):                  # serial_bridge.py:66-68
    total = (total + unpack_u32(transact(ser, CMD_SUM_U32, data[i:i + step], seq=i // step))[0]) & 0xFFFFFFFF
```
要換：`values` = 你的 int 串列；Pico 用 `app_serial.c`。
量測：log 的 `X ms`（`serial_bridge.py:73-74`）。
實測（pty + `fake_pico.py`，20000 個 int32，沒有 USB）：文字一行一個 2049.7 ms；二進位一包一個 1576.9 ms；批次 3.5 ms。本次重跑：1503.2 → 3.6 ms（20 包）。
陷阱：
- ✗ 一包 > 8192 B → Pico 不回、3 次逾時 → ✓ `step` ≤ `CHUNK_BYTES`（4096）且是 4 的倍數。
- ✗ Pico printf / 沒關 CRLF → ✓ `app_serial.c:61`、`CMakeLists.txt:31`。
- CRC32 不能切包相加。
前提：pyserial；`frame.py` 在同一資料夾。
驗證：`total == sum(values) & 0xFFFFFFFF`；先對 `fake_pico.py` 測。

---

【食譜卡｜優化 2/14｜多片板子：切塊平行算 + 依序合併】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
適用：只有一片板子在算、計算佔大部分；工作能切（加總、逐元素、各段排序）。
不用 ROS：`python3 multi_device.py /dev/ttyACM0 /dev/ttyACM1`（`ros2/multi_device.py`）。
ROS node（`serial_bridge.py`）先加 3 行：`:28` 下 `from multi_device import merge_sum, run_parallel, split`；`:37` 下 `self.declare_parameter("ports", ["/dev/ttyACM0", "/dev/ttyACM1"])`；`:46` 下 `self.ports = list(g("ports"))`。
修改前（`serial_bridge.py:65-69`）：
```python
        try:
            for i in range(0, len(data), step):          # 切成好幾包，每包一來一回
                reply = self.send(CMD_SUM_U32, data[i:i + step])
                total = (total + unpack_u32(reply)[0]) & 0xFFFFFFFF   # TODO(改這裡) 合併方式
        except (TimeoutError, serial.SerialException) as e:   # 沒回覆，或拔線 / port 壞掉
```
修改後：
```python
        try:
            total = merge_sum(run_parallel(self.ports, split(data, step), CMD_SUM_U32))
        except RuntimeError as e:
```
量測：`multi_device.py` 自動先跑 1 個 port 再全部。
實測（fake_pico `--us-per-byte 1`，800000 B）：1 port 882.5 → 2 port 442.5 ms（1.99x）；只有傳輸時 1.5～1.7x。本次 bridge 版：882.1 → 454.2 ms。
陷阱：✗ CRC / SHA 切塊相加 → ✓ 整份給一片。排序合併用 `heapq.merge`。
前提：每片燒同一份韌體。
驗證：log `每個 port 做了幾塊: {…: 98, …: 98}`，答案和 1 片相同。

---

【食譜卡｜優化 3/14｜micro-ROS：CHUNK 調大 / 加板子 / best_effort】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
適用：micro-ROS 每則訊息小、`host_driver.py` 的 `time=` 很長。一次只改一個變因。
對應範本：`micro-ros/host_driver.py:21` `N_BOARDS = 2`、`:22` `CHUNK = 300`、`:50` QoS；板子 `pico_array_compute.c:17` `BOARD_NS`、`:27` `MAX_LEN 400`、`:111-112`。
A 加大 CHUNK：reliable `CHUNK ≤ 504`；`CHUNK + 1 > 400` 時兩個板子檔的 `MAX_LEN` 改成 ≥ `CHUNK + 1`，重編、每片重燒（上限是推算值，範本建議 ≤ 450）。
B 加板子：`N_BOARDS = 3`，第 3 片 `#define BOARD_NS "pico2"`、第 3 個 agent。
C best_effort（板子 `:111-112` 改成）：
```c
RCCHECK(rclc_subscription_init_best_effort(&sub, &node, ts, "input"));
RCCHECK(rclc_publisher_init_best_effort(&pub, &node, ts, "output"));
```
host `:50`：`qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.BEST_EFFORT)`，且 `CHUNK ≤ 120`。
量測：`python3 -c 'import host_driver as h; h.CHUNK=100; h.main()'`，再試 200、300、399；`h.N_BOARDS=1` vs `2`；跑 3 次取中位數。
實測：**沒有**（沒有板子 / agent）。C 的板子程式本次編譯連結 0 警告。
陷阱：
- ✗ 兩端 QoS 不同 → reliable 訂閱收不到 best_effort → ✓ 板子和 host 一起改。
- ✗ best_effort 還用 CHUNK 300 → 超過 500 B、收不到 → ✓ ≤ 120。
- best_effort 掉一則要等 `RESEND_S`（1 秒）重送；常掉就更慢。
前提：每片一個 agent、namespace `pico0`…；rclpy 部分從範本改，這次沒有實跑。
驗證：`correct=True` 且沒有逾時；`ros2 topic info /pico0/input -v` 看 QoS。

---

【食譜卡｜優化 4/14｜Pico 雙核：core0 收、core1 算（queue_t）】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
適用：Pico 收資料時不能算、算的時候不能收（收和算差不多重）。
修改前（`pico/app_serial.c:77`，core0 收完自己算）：`if (r == 1) { n_ok++; handle(&rx); }`
修改後：照 `pico/app_multicore.c` 第 2 部分。core1（`:76-82`）：
```c
            while (true) {
                queue_remove_blocking(&q_job, &j);      // 拿一個工作（沒有就等）
                if (j.data == NULL) break;              // 約定：data==NULL 代表結束
                result_t r = { j.id, 0 };
                for (uint32_t i = 0; i < j.n; i++) r.sum += j.data[i];  // TODO(改這裡) 真正的計算
                queue_add_blocking(&q_result, &r);      // 回傳結果
            }
```
core0（`:121-129`）：`sent - got < 4` 才把資料放進 `data_buf[sent % 4]` 送 `q_job`；`queue_try_remove(&q_result, &r)` 收結果。
要換：`:52-53` `job_t` / `result_t`、`:80` 計算、`:123` 模擬資料、`:116` `N_JOBS`。
量測：`PRINT_US("worker 總時間", t0)`。
實測：Pico 沒有。電腦端 `pipeline_template.c`：SPSC + 批次 1.56x、SPSC 0.85x、mutex 0.68x；另一次三種都 < 1x → 在目標機器量。
陷阱：
- ✗ 只有一份 `rx` → 算到一半被覆蓋 → ✓ 多塊 buffer + `sent - got < 4`。
- `queue_init` 容量 8 ≥ 4 + 1 停止；core1 stack 2 KB。
- 瓶頸在 USB → 食譜 1、2。
前提：`#include "pico/multicore.h"`、`"pico/util/queue.h"`；CMake `pico_multicore pico_sync`。
驗證：`total` 和單核版相同。

---

【食譜卡｜優化 5/14｜Pico 鎖：縮小臨界區、區域變數累積後鎖一次】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
適用：兩核共用 `total`，加了 spinlock 後答案對但很慢，比單核還慢。
對應範本：`pico/app_multicore.c:32-49` `add_many()`（`:46-48` 註解就是這個做法）、`:92` 建鎖。
修改前（計算也在鎖裡，另一核一直在等）：
```c
for (int i = 0; i < n; i++) {
    uint32_t s = spin_lock_blocking(lock);
    total += heavy_compute(data[i]);
    spin_unlock(lock, s);
}
```
修改後（先在區域變數算完，最後鎖一次合併）：
```c
uint32_t local = 0;
for (int i = 0; i < n; i++) local += heavy_compute(data[i]);   // 不用鎖：local 是自己的
uint32_t s = spin_lock_blocking(lock);
total += local;                                                // 臨界區只剩 1 行、只進 1 次
spin_unlock(lock, s);
```
要換：`heavy_compute` = 你的計算；`data` / `n` = 這顆核心負責的那一段。
量測：`time_us_64()` 前後相減（`app_multicore.c:103`、`:110` 已經在量）。
實測：Pico 沒有。電腦端同概念（官方 section2-3）：計算在鎖內 86.0～87.2 ms → 鎖外 41.8～49.8 ms；本次重跑 104.0 → 49.2 ms。
陷阱：
- `spin_lock_blocking` 會關中斷 → ✗ 鎖裡 printf / 長計算（USB 會漏收）。
- ✗ `multicore_launch_core1` 之後才建鎖 → ✓ 之前 `lock = spin_lock_init((uint)spin_lock_claim_unused(true));`。
- `volatile` 不能取代鎖。
前提：`#include "hardware/sync.h"`、`static spin_lock_t *lock;`。
驗證：多跑幾次答案都一樣、等於單核答案；時間變短。

---

【食譜卡｜優化 6/14｜電腦 pthread：計算移出鎖、local、padded】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
適用：多執行緒結果對，但比一條慢；或每條寫 `count[tid]`，加執行緒沒變快。
對應範本：`linux-perf/parallel_template.c:45-50` `w_local`、`:59-66` `w_spin`、`:42` `padded_t`。
修改前（鎖內做計算）：
```c
pthread_spin_lock(&lock);
sink += work(i);
counter++;
pthread_spin_unlock(&lock);
```
修改後（計算移到鎖外，鎖內只留共享變數）：
```c
sink += work(i);
pthread_spin_lock(&lock);
counter++;
pthread_spin_unlock(&lock);
```
更快：照 `w_local`，迴圈用區域變數，最後只寫一次 `part[id]`。`count[tid]` → `typedef struct { _Alignas(64) volatile uint64_t v; } padded_t;`，使用處改 `count[tid].v`。
量測：範本內建 `BENCH`（3 次取最快），加速 = serial ÷ 該寫法。
實測（Xeon 2.30GHz 4 vCPU、gcc 13.3 `-O2`、T=4、最空閒那次）：local 3.89x、mutex 0.13x、spinlock 0.03x、atomic 0.18x、false-share 2.75x → padded 3.79x。本次重跑 local 4.00x、spinlock 0.02x。
陷阱：
- ✗ T 超過核心數 → T=8 local 3.32x、spinlock 5 秒 → ✓ T = `nproc`。
- 機器忙時倍數會跳（local 1.24x～3.89x）→ 同時間輪流多跑幾次。
前提：`#include <pthread.h>`；`gcc -O2 -Wall -Wextra -std=c11 -pthread`。
驗證：`-fsanitize=thread` 跑一次沒有 `data race`；結果和 serial 相同。

---

【食譜卡｜優化 7/14｜DMA 取代 CPU 複製迴圈】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
適用：CPU 迴圈 `dst[i] = src[i]` 佔大部分時間；題目要求用 DMA。
對應範本：把 `pico/app_dma.c:21-24`（舊 SDK 補丁）、`:31-46`（`dma_xfer`、`dma_copy32`）複製到你的檔案。
修改前：
```c
for (int i = 0; i < n; i++) dst[i] = src[i];        // uint32_t 陣列，n 個
```
修改後：
```c
if (dma_copy32(dst, src, n) != 0) {                   // count = n「個 u32」，不是 n*4 bytes
    for (int i = 0; i < n; i++) dst[i] = src[i];      // 沒通道 / 太大：退回 CPU
}
```
- `uint8_t` 陣列、`nbytes`：`dma_xfer(dst, src, nbytes, DMA_SIZE_8, true, true)`。
- CPU 同時做事：configure 最後給 `true` 但不馬上等，用到 `dst` 前才 `dma_channel_wait_for_finish_blocking`（`app_dma.c:129-136`）。
量測：燒 `app_dma.uf2`，看 `copy 4096 words: loop=…us memcpy=…us dma=…us  正確=OK`（`:102-110`）。
實測：**沒有**（要上板）。小資料 DMA 不一定比 `memcpy` 快，以實測為準。
陷阱：
- ✗ count 填 bytes → ✓ 次數；一律 `dma_encode_transfer_count(n)`，n < 2^28。
- ✗ 沒開寫遞增 → ✓ copy 要 `channel_config_set_write_increment(&c, true)`。
- ✗ 沒 `dma_channel_unclaim` → 16 個通道用完；32-bit 傳輸位址要 4-byte 對齊。
前提：`#include "hardware/dma.h"`；CMake `target_link_libraries(<app> hardware_dma)`。
驗證：`memcmp(dst, src, bytes) == 0`，搬之前先把 `dst` 清成別的值。

---

【食譜卡｜優化 8/14｜CRC 軟體加速：逐位元 → 查表 / slice4】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
適用：CRC-32（zlib）算很久，程式是逐位元（每 byte 跑 `for k < 8`）。
對應範本：`algo/crc32.h:20-23`；Pico 範本 `pico/serial_proto.c:25` 的 `crc32_update` 已是查表版。
修改前（`pico/app_dma.c:90-94` 的 `cpu_crc32`，或 `algo` 的 `crc32_bitwise`）：
```c
uint32_t c = crc32_bitwise(0, p, n);
```
修改後：
```c
uint32_t c = crc32_update(0, p, n);   /* = crc32_slice4，最快 */
```
- 只要查表版：`crc32_table(0, p, n)`。三種結果完全相同，第一個參數都是 0、可接續（把上次結果傳回去）。
量測：`gcc -O2 -std=c11 crc32_test.c crc32.c && ./a.out` 會印 4 MB 的 benchmark。
實測（host Xeon 2.30GHz、gcc 13.3 `-O2`、4 MB）：bitwise 36.47 ms、table 8.65 ms（4.2x）、slice4 2.90 ms（12.6x）。本次重跑 34.81 / 8.40 / 2.87 ms。`serial_proto.c` 查表 vs `cpu_crc32`：4.1～4.6x。Pico 上沒量。
陷阱：
- slice4 要 4 KB 表（`crc32.c` bss 5636 B）；RAM 很緊時用 `crc32_table`。
- `serial_proto.c` 的 `crc32_update` 是 weak：專案加了 `algo/crc32.c` 就用那份（結果相同，不會 multiple definition）。
- 其他 CRC 規格：`crc_generic` 很慢（0.25x），只拿來對答案。
前提：`#include "crc32.h"`；CMake 加 `algo/crc32.c` 和 include 路徑。
驗證：`crc32_update(0, (const uint8_t *)"123456789", 9) == 0xCBF43926`；`crc32_test` 印 `結果：全部通過`。

---

【食譜卡｜優化 9/14｜CRC 硬體：DMA sniffer 取代軟體 CRC】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
適用：`CMD_CRC32` 用軟體算太慢；題目要「硬體 CRC」「DMA 校驗」。
對應範本：`pico/app_serial.c:45`；函式來源 `pico/app_dma.c:65-87` `dma_crc32()`。
步驟：
1. `CMakeLists.txt:32` 改成 `target_link_libraries(app_serial pico_multicore hardware_dma)`。
2. `app_serial.c:17` 後加 `#include "hardware/dma.h"`、`app_dma.c:21-24` 的補丁、`app_dma.c:65-87` 整個 `dma_crc32()`。
3. `app_serial.c:45`：
```c
// 改前
uint32_t c = crc32_update(0, f->payload, f->len);
// 改後
uint32_t c = dma_crc32(f->payload, f->len);
```
量測：燒 `app_dma.uf2`，看 `crc32 16384 bytes: cpu=…us dma=…us (x…)`（`app_dma.c:123-126`）。
實測：速度**沒有**（要上板）。本次副本編譯連結 0 警告（text 27356 B）。
⚠️未上板：sniffer = zlib CRC32 只由暫存器文件推導 → 一定先看 `crc32("123456789") ... PASS`。
陷阱：
- FAIL 值 `0x649C2FD3` → `output_reverse` 改 false；`0x340BC6D9` → 最後的 `^ 0xFFFFFFFF` 多做了。
- `dma_claim_unused_channel(true)` 沒通道會 panic；要保險改 `false`，失敗時呼叫 `crc32_update`。
- ✗ 分段續算 → ✓ 一次 DMA 算完整段；全晶片只有一個 sniffer。
- `dma_crc32` 裡不要 printf（app_serial 不能印字）。
前提：`hardware_dma`；SDK 2.0 / 2.1 要 `app_dma.c:21-24` 的補丁。
驗證：電腦端 `unpack_u32(transact(ser, CMD_CRC32, data))[0] == zlib.crc32(data)`，測 `b"123456789"`、空資料、4096 B 隨機。

---

【食譜卡｜優化 10/14｜排序：qsort / insertion → radix】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
適用：u32 排序很慢；n ≥ 256 還用 qsort / 插入排序（O(n²)）。
對應範本：`algo/sort.h:22-24`；Pico 指令加在 `pico/app_serial.c:51` 的 `TODO(改這裡)` 上面。
修改前：`qsort(a, n, 4, cmp);` 或插入排序迴圈。
修改後（板子 `handle()` 新指令，本次編譯通過）：
```c
#include "sort.h"
#define CMD_SORT_U32 0x04     // payload = u32 陣列 → 回排序好的 u32 陣列
static uint32_t sort_buf[FRAME_MAX_PAYLOAD / 4], sort_tmp[FRAME_MAX_PAYLOAD / 4];
...
    case CMD_SORT_U32: {
        uint32_t n = f->len / 4;
        memcpy(sort_buf, f->payload, n * 4);
        radix_sort_u32(sort_buf, n, sort_tmp);
        proto_send(f->cmd, f->seq, (const uint8_t *)sort_buf, (uint16_t)(n * 4));
        break;
    }
```
量測：`gcc -O2 -std=c11 sort_test.c sort.c && ./a.out`。
實測（host Xeon、gcc 13.3 `-O2`）：n=1000 insertion 78.48 µs、qsort 32.68、radix 4.54；n=2^20 qsort 109.10 ms、radix 6.86 ms（15.9x）。n ≤ 32 insertion 最快。本次 2^20：105.34 → 9.33 ms。Pico 沒量。
陷阱：
- 有號 int32：排序前後各 `^= 0x80000000u`。
- `radix_sort_u32` 用 1064 B stack；core1 只有 2 KB。
- 新 cmd 改 4 處：`serial_proto.h`、`handle()`、`frame.py`、`fake_pico.py`。
前提：CMake 加 `algo/sort.c` 和 include 路徑。
驗證：`unpack_u32(transact(ser, 0x04, pack_u32(vals))) == sorted(vals)`。

---

【食譜卡｜優化 11/14｜多段合併：kway_merge → 兩兩合併】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
適用：k 段已排序（多板 / 兩核各排一段）要合併，k ≥ 8 時 `kway_merge` 慢。
對應範本：`algo/sort.h:27-32`。2 段用 `merge_two_sorted(a, na, b, nb, out)`；3～4 段 `kway_merge(lists, lens, k, out)`。
修改後（k 段等長、連續放在 `src`，k 是 2 的冪；本次 k = 2、4、8、16 對 qsort 結果都相同）：
```c
static uint32_t *tree_merge(uint32_t *src, uint32_t *dst, size_t n, int k) {
    size_t len = n / k;
    while (len < n) {
        for (size_t lo = 0; lo < n; lo += 2 * len) {
            size_t m = lo + len < n ? len : n - lo, r = lo + 2 * len <= n ? len : (lo + len < n ? n - lo - len : 0);
            merge_two_sorted(src + lo, m, src + lo + m, r, dst + lo);
        }
        uint32_t *t = src; src = dst; dst = t; len *= 2;
    }
    return src;                     /* 結果在 src 或 dst 其中一個，用回傳值 */
}
```
電腦端合併（Python）：`out = list(heapq.merge(*[unpack_u32(r) for r in replies]))`。
量測：只量合併那段（`time_us_64()`）。
實測（host、n=2^20、ms）：k=2 kway 6.39 / 兩兩 3.97；k=8 29.05 / 12.19；k=16 62.32 / 15.93。Pico 上沒量。
陷阱：
- ✗ 直接用 `src` 當結果 → ✓ 用回傳值。
- 要一個 n 大小的 `dst` 暫存區（`static`）；`out` 不可以跟 `a` / `b` 重疊。
前提：`#include "sort.h"`；加 `algo/sort.c`。
驗證：合併結果 `== sorted(全部資料)`（電腦端 `assert out == sorted(values)`）。

---

【食譜卡｜優化 12/14｜熱路徑拿掉 printf / log】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
適用：ROS callback 或迴圈裡每個元素都 print / log；Pico 的 `app_serial.c`、micro-ROS 韌體裡有 printf。
對應範本：`ros2/serial_bridge.py:74`（一個 callback 只 log 一行）；`pico/app_serial.c:6-7`（不要 printf）。
修改前：
```python
def cb_before(msg):
    total = 0
    for v in msg:
        total += v
        print(f"got {v}, total {total}", file=out)   # 每個元素印一行
    return total
```
修改後：
```python
def cb_after(msg):
    total = sum(msg)
    print(f"{len(msg)} 個, total {total}", file=out)   # 一個 callback 只印一行
    return total
```
要換：`print` / `self.get_logger().info` 都一樣處理；要除錯就只在失敗時印。
量測：callback 前後 `time.perf_counter()`（`serial_bridge.py:60`、`:73`）。
實測（本卡自測：x86_64 Xeon、Python 3.13，20000 個元素，輸出到 pty 模擬終端機）：before 125.19～130.14 ms → after 0.19 ms。ROS logger 沒量（容器沒有 ROS 2）。
陷阱：
- Pico `app_serial` printf → 文字混進封包，`frame.py diff` 顯示「開頭不是 aa 55」→ ✓ 改用 LED。
- micro-ROS 的 USB 被 agent 佔用：printf 看不到還可能弄壞封包；agent 不要開 `-v6`。
- 鎖裡不要 printf（食譜 5）。
前提：無。
驗證：輸出結果和改之前相同；`git diff | grep -nE '^\+.*(printf|print\()'` 沒有多出來的除錯輸出。

---

【食譜卡｜優化 13/14｜編譯選項、熱迴圈放 RAM（__not_in_flash_func）】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
適用：單執行緒本身慢、還沒動過編譯選項；Pico 熱迴圈在 XIP flash 執行。先確認評分腳本允許改旗標。
A 電腦端：`gcc -O2 …` → `gcc -O3 -march=native …`。
實測（Xeon 4 vCPU、gcc 13.3、`parallel_template.c` serial）：46.9 → 15.5 ms（3.04x）；本次重跑 44.4 → 17.4 ms。
B Pico（pico-sdk）：沒給 `CMAKE_BUILD_TYPE` 時預設 `Release`，旗標是 `-g -O3 -DNDEBUG`（本次 `build/CMakeCache.txt` 確認）→ 通常不用改；`assert` 在 Release 會消失。
C 熱函式放 SRAM：
```c
// 修改前
static uint32_t hot_sum(const uint32_t *a, int n) {
// 修改後
static uint32_t __noinline __not_in_flash_func(hot_sum)(const uint32_t *a, int n) {
```
要換：`hot_sum` = 你的函式名（只包名字，括號放對位置）。
量測：`time_us_64()` 前後相減，重複上萬次取平均。
實測：Pico 速度**沒有**（沒上板）。本次編譯：`arm-none-eabi-nm build/<app>.elf | grep hot_sum` → `20000110 t hot_sum.constprop.0`（0x2000… = RAM）。
陷阱：
- ✗ 沒加 `__noinline` → 本次實測函式被 inline 進 `main`（`0x10000274`，在 flash），屬性白加。
- `__time_critical_func(f)` = 同一個東西（`pico/platform/sections.h:153`）。
- `-O3 -march=native` 的程式只能在同一種 CPU 跑。
前提：`#include "pico/stdlib.h"`（已含 `__not_in_flash_func`、`__noinline`）。
驗證：`nm` 位址開頭是 `2000`；結果和改之前相同。

---

【食譜卡｜優化 14/14｜BNN popcount：Zbb cpop / SWAR】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
適用：BNN（XNOR-popcount）推論慢；`bnn_dot` 是熱點。
對應範本：`algo/bnn.h:34-42` `bnn_popcount`、`algo/bnn.c:14-23` `bnn_dot`。
A RISC-V（Hazard3）：pico-sdk 預設 `-march=rv32imac_zicsr_zifencei_zba_zbb_zbs_zbkb` 已含 Zbb → `__builtin_popcount` 變 1 條 `cpop`。**什麼都不用改**。
B ARM（Cortex-M33，沒有 popcount 指令）：
```cmake
# 修改前：沒有這行（呼叫 libgcc 的 __popcountsi2）
# 修改後：
target_compile_definitions(<app> PRIVATE BNN_SWAR_POPCOUNT)
```
要換：`<app>` = 你的 target 名稱。
量測：`objdump -d` 看內迴圈；Pico 上 `time_us_64()` 重複上萬次。
實測（本次 objdump）：M33 預設 `bnn.o` 有 2 個 `bl __popcountsi2` → 加 SWAR 後 0 個（pico2 build 加這行後 elf 裡沒有 `__popcountsi2`）；rv32 + Zbb 有 2 條 `cpop`。host（Xeon、gcc 13.3 `-O2`，一層 784×256）：12.09 → 8.12 µs（SWAR，1.49x）、硬體 popcnt 3.47 µs；本次重跑 11.44 → 7.69 µs。Pico 上兩者速度沒量。
陷阱：
- ✗ 自己改 `-march` 拿掉 `zbb` → 又變成函式呼叫。
- ✗ 最後一個 word 沒 mask（`bnn.c:19-21`）→ 分數錯。
- 更進一步：雙核 / 多板分神經元（食譜 4、2）；輸入用 bits 傳（784 bit = 100 byte）。
前提：`#include "bnn.h"`；CMake 加 `algo/bnn.c`。
驗證：`bnn_test` 印 `結果：全部通過`；分數和 Python `bnn_dense_score` 逐項相同。

---

【提示卡｜套用 1/1｜把食譜 / 片段套到我的程式】
Task (EN): Apply the recipe or snippet card below to my code. Output a minimal patch that changes only the <slots> or the lines the card marks (修改前 → 修改後), keep every name from the card verbatim, then 1 verify command, 1 measure command and what success looks like. Answer in Traditional Chinese.
任務：把卡片的「修改後」套到我的程式，只改卡片標出來的那幾行。
<<<資料 開始>>>
[食譜卡或片段卡原文]
{{貼整張卡}}
[我的程式，帶行號]（`cat -n 檔名 | sed -n 起,迄p`）
{{貼}}
[量測]（改之前的數字和指令）
{{例如 callback 2049.7 ms，指令 python3 bench.py …}}
<<<資料 結束>>>
規則：
1. 只改對到卡片「修改前」或 `<尖括號>` 的行；最多改 15 行，其他行不動。
2. 函式名、參數順序、常數照卡片原樣抄；`<尖括號>` 換成我程式裡的名稱。
3. 我的程式裡找不到卡片的「修改前」→ 寫「對不到：」加原因，不要猜。
4. 卡片「前提」要的 include / CMake / import，寫在「另外要加」。
只輸出：
檔名:行號
修改前：
修改後：
另外要加：（沒有寫「無」）
驗證指令（1 行）：
量測指令（1 行）：
成功的樣子：（結果和改之前相同，數字變小多少）
範例（只示範格式，內容不要照抄）：
filter.c:52
修改前：uint32_t h = slow_hash(0, buf, len);
修改後：uint32_t h = fast_hash(0, buf, len);
另外要加：CMakeLists.txt 加 hash.c
驗證指令：./filter_test
量測指令：./filter_bench
成功的樣子：輸出和改之前相同，210 ms → 50 ms
