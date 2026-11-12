# 貼上卡：Python / rclpy 效能
> 用法：一次只複製一張卡（兩條分隔線之間），貼進對話，再在下面寫你的問題。每張 ≤ 1200 字元。
> 來源：full/domain/python-perf.md、lite/domain/python-perf.md（詳細版）｜最後更新 2026-11

---

【參考卡｜Python 效能 1/7｜決策表與量測】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
環境：Python 3.12.3（Ubuntu 24.04）、ROS 2 Jazzy rclpy 7.1.x。py-spy / perf / line_profiler 當作沒有，考場不能安裝。
決策：
- 不知道慢在哪 → `python3 -m cProfile -s cumtime x.py`，或可疑段落前後放 `time.perf_counter_ns()`。
- 熱點是純 Python 迴圈 → 換演算法 / 資料結構 → 換內建函式（C 實作）→ numpy。
- 熱點是讀輸入 / 印輸出 → `sys.stdin.buffer.read().split()`、`sys.stdout.write('\n'.join(...))`、拿掉 `flush=True`。
- 想用 thread 加速 CPU 運算 → 沒用（GIL），改多 process 或 numpy / C。
- rclpy node 跟不上 → 拿掉 callback 內 log / print / sleep；批次化；陣列欄位走 buffer 轉換；最後改 rclcpp。
量測：
- `time.perf_counter_ns()` 牆鐘；`time.process_time()` CPU 時間。牆鐘 ≫ CPU → 在等 I/O / 鎖 / sleep。不要用 `time.time()`。量測輸出寫 `sys.stderr`，不污染評分用 stdout。
- `python3 -m timeit -s 'setup' 'stmt'`（`-n` 每輪次數、`-r` 輪數預設 5），看最小值。
- `python3 -m cProfile -o prof.out x.py` 後 `pstats.Stats('prof.out').strip_dirs().sort_stats('tottime').print_stats(20)`。cumtime = 含子呼叫；tottime = 只算自身。
- cProfile 只對 Python 函式加開銷 → profile 找位置，timeit / perf_counter 量大小。
- 記憶體：`tracemalloc.start()` … `tracemalloc.get_traced_memory()`；啟動慢：`python3 -X importtime x.py`。
- 第一次執行含 import / .pyc 編譯 / DDS discovery → 量穩態，重複取最小或中位數。
- 先確認：`import numpy` 是否成功、`echo $ROS_PYTHON_CHECK_FIELDS`（=1 時欄位檢查很慢）。

---

【參考卡｜Python 效能 2/7｜慢 → 快 對照表】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
環境：CPython 3.12.3。倍數為約略值（⚠️ = 推估），考場要重量。
- `x in 大list` 重複查 → 先 `s = set(lst)` 再 `x in s`：100～1000×+
- `list.pop(0)` 當佇列 → `deque.popleft()`；環形緩衝 `deque(maxlen=N)`：10～100×
- 雙層迴圈找配對 O(n²) → dict / set 索引，或排序 + bisect：常見 100×+
- for 累加 → `sum()` / `max()` / `min()` / `any()`：~3×
- `map(lambda ...)` → list comprehension：~1.5×（map 只有配 C 函式才快）
- 逐筆 `struct.unpack(fmt, buf[i:i+k])` → `Struct.unpack_from` / `struct.iter_unpack` / 一次 `struct.unpack(f'<{n}i', raw)`：3～7×
- bytes 拆成 int list 只為轉存 → `array.array('i').frombytes(raw)` / `memoryview`：100×+
- 迴圈內 `re.match(pattern, s)` → 迴圈外 `P = re.compile(...)`，內 `P.match(s)`：~2.5×
- `input()` 逐行 → `sys.stdin.buffer.read().split()`：~5～7×
- 每行 `print(..., flush=True)` → 一次 `sys.stdout.write('\n'.join(map(str, xs)))`：~6～12×
- 遞迴重複子問題 → `functools.cache`：指數 → 線性
- 4 thread 跑 CPU 運算 → 4 process（ProcessPoolExecutor）：~接近核心數
- 大陣列 Python 迴圈 → numpy 向量化：10～100× ⚠️（小陣列反而慢）
- uint8 逐 byte 映射 → 256 項 LUT + `data.translate(LUT)`：數十× ⚠️
- 每次 callback 建 `struct.Struct` / LUT / 暫存陣列 → `__init__` 建一次存 self
- 字串 `s += t` 累加 → `''.join(parts)`
- 熱迴圈寫在模組頂層 → 包進 `main()`。3.12 下 `ap = lst.append` 快取已無收益。

---

【參考卡｜Python 效能 3/7｜rclpy 訊息欄位與陣列快路徑】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
環境：ROS 2 Jazzy rclpy、numpy 1.26。
欄位的 Python 型別：
- 純量 int32 / float64 / bool → int / float / bool；string → str。
- 數值不定長序列 `T[]`（如 `Int32MultiArray.data`）→ `array.array`（int32 = `'i'`，uint8 = `'B'`，如 `Image.data`、`UInt8MultiArray.data`）。
- 固定長度 `T[N]`（如 `Imu.orientation_covariance`）→ `numpy.ndarray`。
指定給 `msg.data`（欄位檢查預設關閉時，setter 一律 `array.array(tc, value)`；實測 1,000,000 個 int32）：
- list of int：15 ms（逐元素）
- 同型別碼 `array.array('i', ...)`：0.09 ms（memcpy）
- `bytes` / `bytearray`：0.08 ms（memcpy）
- memoryview：36 ms；numpy 陣列：71 ms（都被當一般 iterable 逐元素，比 list 還慢）
寫法：
```python
msg.data = out_array                        # 已是 array('i') → 最快
msg.data = np_arr.astype(np.int32, copy=False).tobytes()   # numpy → bytes → memcpy
```
讀取：
```python
d = msg.data                                   # array('i')
a = np.frombuffer(d, dtype=np.int32)           # 零複製、可寫
mv = memoryview(d)                             # 零複製子區段 mv[100:200]
```
- `np.frombuffer(msg.data)` 是 view，要保存就 `.copy()`；`np.frombuffer(bytes)` 是唯讀。
- `ROS_PYTHON_CHECK_FIELDS=1` 時指定 list 會先逐元素檢查，非常慢 → 量效能前確認沒開。
- int32 用 `array('i')`，不要 `'l'`（8 bytes）。

---

【參考卡｜Python 效能 4/7｜rclpy callback、log、spin 的開銷】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
環境：ROS 2 Jazzy rclpy 7.1.x（原始碼確認），Python 3.12。
- 每則訊息都有固定 Python 開銷：executor 是純 Python（建 wait set、分派）、建訊息物件、欄位 setter、呼叫 callback。高頻小訊息時這通常就是瓶頸 → 少量大訊息遠比大量小訊息有效率（打包成 Int32MultiArray 批次發）。
- callback 要短：不 sleep、不 busy-wait、不同步 service call（死結）、不大量 I/O。publisher、`struct.Struct`、`re.compile`、LUT 在 `__init__` 建一次；不要在 callback 內 `create_publisher`。
- `get_logger().info(...)`：level 夠時每次都用 `inspect` 取呼叫者資訊（相對昂貴），throttle 的 filter 在這之後才檢查，被 throttle 掉的呼叫也付了成本；還會發布到 /rosout。f-string 在呼叫前就格式化。→ 熱 callback 改計數，timer 每秒印一次。
- `print(flush=True)` 每行一次系統呼叫；規格要求的輸出要保留。
- spin：
  - `rclpy.spin(node)` + timer：正確、推薦。
  - `while rclpy.ok(): rclpy.spin_once(node, timeout_sec=0)`：busy loop CPU 100%，且每次都把 node 加進 / 移出 executor。
  - 必須自己寫迴圈：`ex = SingleThreadedExecutor(); ex.add_node(node)` 建一次，迴圈內 `ex.spin_once(timeout_sec=0.01)`。
- MultiThreadedExecutor：讓阻塞型 callback 不互卡，CPU 運算不會變快（GIL），且要搭配不同 callback group。
- `from rclpy.experimental import EventsExecutor`（rclpy 7.1.4+，C++ 實作，實驗性）：可降低 executor 的 Python 開銷（降幅 ⚠️未實測），改用前後都要驗證正確性。
- 已拿掉 log、callback 幾乎沒工作仍上不去 → 瓶頸在 rclpy 本身 → 改 rclcpp（先確認題目允許、建置方式）。

---

【參考卡｜Python 效能 5/7｜GIL 與平行化】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
環境：CPython 3.12（有 GIL；3.12 沒有無 GIL 版本）。
- 同一時間只有一個 thread 執行 Python bytecode → 純 Python CPU 運算多 thread 不會變快（實測 4 個 CPU 任務：序列 0.34 s、4 threads 0.30 s、4 processes 0.08 s）。
- 阻塞 I/O（檔案、socket、sleep、等鎖）會釋放 GIL → I/O bound 用 thread 有效。
- GIL 不保證複合操作（`d[k] += 1`、check-then-act）原子 → 共享資料仍要加鎖。
選擇：
- CPU bound、可切塊 → `concurrent.futures.ProcessPoolExecutor`；pickle + 複製有成本，任務太小用 `chunksize` 或大塊。
- CPU bound、陣列運算 → numpy 向量化（單 process 就快很多）。
- I/O bound → `ThreadPoolExecutor` 或 `asyncio`。
- rclpy callback 互不阻塞 → MultiThreadedExecutor + 不同 callback group。
```python
from concurrent.futures import ProcessPoolExecutor
def work(chunk):                         # 必須是模組頂層函式（可 pickle）
    return sum(x * x for x in chunk)
if __name__ == '__main__':
    chunks = [data[i:i + 100_000] for i in range(0, len(data), 100_000)]
    with ProcessPoolExecutor(max_workers=4) as ex:
        total = sum(ex.map(work, chunks))
```
start method：
- 3.12 在 Linux 預設 fork；process 內已有多個 thread 時 fork 會發 DeprecationWarning。
- rclpy 初始化後有背景 thread（DDS 等）→ 在 rclpy node 內 fork 有死結風險 ⚠️。建議：在 `rclpy.init()` 之前建 pool，或 `multiprocessing.get_context('spawn')`，或拆成多個獨立 node 程式。

---

【參考卡｜Python 效能 6/7｜快速 I/O 與二進位解析】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
環境：Python 3.12.3，數字為本機實測數量級。
讀輸入（200,000 行整數）：`input()` 0.20 s；`input = sys.stdin.readline` 0.04 s；`sys.stdin.buffer.read().split()` 0.03 s。
```python
import sys
def main():
    data = sys.stdin.buffer.read().split()   # list[bytes]，int(b'123') 可直接用
    n = int(data[0])
    xs = list(map(int, data[1:1 + n]))
main()
```
輸出（200,000 行）：逐行 print 0.06 s；`sys.stdout.write('\n'.join(map(str, xs)) + '\n')` 0.03 s；逐行 `print(flush=True)` 0.37 s。stdout 是 pipe 時區塊緩衝、終端機時行緩衝。規格要求即時輸出就別拿掉 flush。除錯輸出寫 stderr。
解析 100,000 個 little-endian int32（ms）：逐筆 `struct.unpack('<i', raw[i:i+4])` 12.0；`Struct.unpack_from` 6.9；`struct.iter_unpack` 4.1；一次 `struct.unpack(f'<{n}i', raw)` 1.7；`memoryview(raw).cast('i').tolist()` 1.8；`array.array('i').frombytes(raw)` 0.009（只是 memcpy）。
- 只要存 / 轉發 / 給 numpy → 用 `array.frombytes` 或 `memoryview`，別拆成 Python int。
- struct 前綴：`<` 小端無對齊（協定用這個）；`@`（預設）原生且有對齊 padding。
- `array` 型別碼：`'i'` = 4 bytes（int32）；`'l'` = 8 bytes。`array('i', [2**31])` 丟 OverflowError。
- `int.from_bytes(b, 'little', signed=True)`；3.11+ byteorder 預設 `'big'`。
- `memoryview(buf)[a:b]` 零複製；`bytearray` 組封包 `+=` 攤銷 O(1)。

---

【參考卡｜Python 效能 7/7｜陷阱與驗證清單】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
環境：Python 3.12、ROS 2 Jazzy rclpy、numpy 1.26。
陷阱：
1. int 溢位語義：Python int 不溢位；`array('i')` 超範圍丟 OverflowError；numpy int32 陣列運算靜默回繞；rclpy Jazzy 預設不檢查訊息欄位範圍，超範圍值在 C 轉換時取低 32 位（實測 Int32 給 2**31+5 → -2147483643）。優化前後語義要一致且符合規格。int32 回繞：`((v + 0x80000000) & 0xFFFFFFFF) - 0x80000000`。
2. 浮點：sum 順序、numpy pairwise summation、float32 vs float64 → 末幾位不同；看規格容許誤差。
3. numpy int32 累加會溢位 → `a.sum(dtype=np.int64)`。
4. `np.frombuffer(bytes)` 唯讀，原地修改丟 ValueError → `.copy()`。
5. `struct` 預設 `@` 有對齊；協定用 `<` / `>`。
6. generator 只能迭代一次，第二次是空的。
7. `lru_cache` / `cache` 用在有副作用或參數不可雜湊的函式會錯；`cache` 無上限。
8. 拿掉了評分需要的輸出 → 先讀規格再刪 print。
9. `ROS_PYTHON_CHECK_FIELDS=1` 開著做量測 → list 指定超慢。
10. MultiThreadedExecutor 期待 CPU 加速 → GIL；callback 都在預設 group 時仍一次一個。
11. 在 rclpy 內 fork 多 process → 可能死結，用 spawn。
驗證：
- 同一組輸入（含邊界 0、1、-1、2³⁰、2³¹-1、-2³¹）比對優化前後輸出逐筆一致（echo 或測試 subscriber 存檔後 `diff`）。
- `ros2 topic hz` 輸出頻率應等於輸入頻率。
- 有基準數據並記錄量測方法；量穩態不量首次；關掉多開的 echo / hz。
優化順序（收益大→小）：演算法 / 資料結構 → 移除不必要工作 → I/O 批次化 → 迴圈推進 C（內建、join、translate、iter_unpack、frombytes）→ numpy → rclpy 專屬（短 callback、批次訊息、buffer 路徑、log 摘要）→ 多 process → 改 rclcpp → 微優化。
