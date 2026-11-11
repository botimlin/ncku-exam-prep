# Python 效能優化手冊（含 ROS 2 rclpy node）（完整版）

> 用途：**備援 pack**。考前練習只用 rclpy 當觀察對象，沒有要求優化 Python；本檔案是「萬一考題要你加速一支 Python 程式 / rclpy node」時用的。內容：量測與 profiling、CPython 成本模型、標準函式庫的快速寫法、GIL 與平行化、numpy（選用）、rclpy 的每則訊息開銷與訊息欄位內部表示、慢→快對照表、實作範例。可整份貼給考場 LLM 當參考資料。
> 適用版本：Python 3.12（Ubuntu 24.04 Noble 的 `python3.12` 3.12.3）、numpy 1.26.4（Noble 的 `python3-numpy`）、ROS 2 Jazzy rclpy 7.1.x、rosidl_generator_py 0.22.x。考前練習 image 為 `ros:jazzy-ros-core`。
> 來源（實際查閱）：
> - Python 3.12 文件：https://docs.python.org/3.12/library/timeit.html 、https://docs.python.org/3.12/library/profile.html 、https://docs.python.org/3.12/library/multiprocessing.html （另以本機 Python 3.12.3 直接執行驗證 `itertools.batched`、`int.from_bytes` 預設值、`struct.iter_unpack`、`bisect` 的 `key=`、`math.sumprod`、`sys.get_int_max_str_digits()`、`array` itemsize、`memoryview.cast`）
> - numpy 1.26 文件：https://numpy.org/doc/1.26/reference/generated/numpy.frombuffer.html
> - rclpy 原始碼（jazzy 分支）：https://github.com/ros2/rclpy/tree/jazzy/rclpy/rclpy （`__init__.py`、`executors.py`、`publisher.py`、`subscription.py`、`serialization.py`、`impl/rcutils_logger.py`、`experimental/events_executor.py`、`CHANGELOG.rst`）
> - rosidl_python 原始碼（jazzy）：https://github.com/ros2/rosidl_python/tree/jazzy/rosidl_generator_py （`resource/_msg.py.em`、`resource/_idl.py.em`、`resource/_msg_support.c.em`、`rosidl_generator_py/generate_py_impl.py`、`package.xml`）
> - ROS 2 Iron release notes（訊息欄位檢查預設關閉）：https://github.com/ros2/ros2_documentation/blob/jazzy/source/Releases/Release-Iron-Irwini.rst
> - 套件相依（確認 numpy 會被裝進 ros_core）：http://packages.ros.org/ros2/ubuntu/dists/noble/main/binary-amd64/Packages.gz 、http://archive.ubuntu.com/ubuntu/dists/noble/main/binary-amd64/Packages.gz
> - common_interfaces（jazzy）：`std_msgs/msg/Int32MultiArray.msg`、`sensor_msgs/msg/Image.msg`、`sensor_msgs/msg/Imu.msg`
> 最後更新：2026-11
>
> 標記：`⚠️未驗證` = 沒有在官方來源或實測中確認，使用前先在環境裡測。
> 本檔所有「實測」數字：x86-64 筆電、Python 3.12.3、單次量測取最小值；**只代表數量級**，考場機器會不同，一定要自己重量。
> 相關檔案：`03-optimize.md`（通用優化流程、Amdahl、實驗紀錄表）、`domain/ros2.md`（ros2 CLI、QoS、executor / callback group、rclcpp、intra-process）、`domain/multicore-sync.md`（鎖與臨界區觀念）。本檔不重複那些內容，只補 Python 層面。

---

## 0. 三十秒決策表

| 現象 | 第一個動作 | 本檔章節 |
|---|---|---|
| 不知道慢在哪 | `python3 -m cProfile -s cumtime x.py`，或在可疑段落前後放 `time.perf_counter_ns()` | §2 |
| 熱點是純 Python 迴圈 | 換演算法 / 資料結構 → 換成內建函式（C 實作）→ numpy | §3、§4、§7 |
| 熱點是讀輸入 / 印輸出 | `sys.stdin.buffer.read().split()`、`sys.stdout.write('\n'.join(...))`、拿掉 `flush=True` | §5 |
| 想用 thread 加速 CPU 運算 | 沒用（GIL）。改 `multiprocessing` / 多個 process，或 numpy / C | §6 |
| rclpy node 跟不上訊息頻率 | 拿掉 callback 內的 log / print / sleep；批次化；陣列欄位用 buffer 轉換；最後考慮改 rclcpp | §8、§10 |
| 處理 `Int32MultiArray` / `Image` 很慢 | 不要逐元素在 Python 處理；`np.frombuffer(msg.data, ...)`；回填時給 `array.array` 或 `bytes` | §8.3、§7 |
| 結果變了（優化後錯） | 先確認溢位語義（int32 回繞）、輸出格式、浮點順序 | §11 |

---

## 1. 環境事實（考前練習 image `ros:jazzy-ros-core`）

| 項目 | 狀態 | 依據 / 確認指令 |
|---|---|---|
| Python | 3.12.3（Noble `python3.12`） | `python3 --version` |
| numpy | **會被裝**：相依鏈 `ros-jazzy-ros-core → rosidl-default-runtime → rosidl-core-runtime → rosidl-generator-py → python3-numpy`（Noble 版本 1.26.4） | `python3 -c "import numpy; print(numpy.__version__)"` |
| rclpy | jazzy 7.1.x（apt 上目前 7.1.12；image 實際版本依建置日期） | `grep '<version>' /opt/ros/jazzy/share/rclpy/package.xml` |
| `rclpy.experimental.EventsExecutor` | rclpy 7.1.4（2025-04）起有 | `python3 -c "from rclpy.experimental import EventsExecutor"` |
| py-spy / perf / line_profiler | 不在 ros_core 相依中，**當作沒有**；考試不能自行安裝 | `which py-spy perf` |
| 自由執行緒 Python（無 GIL） | 3.12 沒有；3.13 起才有實驗性 `python3.13t` 建置 | `python3 -c "import sysconfig; print(sysconfig.get_config_var('Py_GIL_DISABLED'))"` → `None`/`0` 表示有 GIL |

原則：**永遠先寫純標準函式庫版本**，numpy 當加分選項（考場 image 可能和練習 image 不同，先用上面指令確認）。

```python
try:
    import numpy as np
    HAVE_NP = True
except ImportError:
    HAVE_NP = False
```

---

## 2. 量測與 profiling

鐵則（同 `03-optimize.md`）：先量測、一次改一處、改完驗證正確性再量一次。Python 特有：**第一次執行會含 import 與 .pyc 編譯時間**，量測要重複多次取最小值或中位數。

### 2.1 計時 API（`time` 模組）

| 函式 | 回傳 | 用途 |
|---|---|---|
| `time.perf_counter()` | float 秒，單調、最高解析度 | 量牆鐘時間（首選） |
| `time.perf_counter_ns()` | int 奈秒（3.7+） | 避免 float 精度損失；量很短的區段 |
| `time.process_time()` / `process_time_ns()` | 本 process 的 CPU 時間（user+sys，不含 sleep） | 判斷「是在算還是在等」 |
| `time.thread_time()` | 本 thread 的 CPU 時間（3.7+） | 多執行緒時分辨誰在燒 CPU |
| `time.monotonic()` | 單調秒數 | timeout 計算 |
| `time.time()` | 牆上時鐘，可能被調整 | **不要**拿來量效能 |

```python
import time
t0 = time.perf_counter_ns()
result = work()
dt_us = (time.perf_counter_ns() - t0) / 1000
print(f'work: {dt_us:.1f} us', file=sys.stderr)   # 量測輸出走 stderr，不污染評分用的 stdout
```

牆鐘時間 ≫ CPU 時間 → 在等 I/O / 鎖 / sleep；兩者接近 → CPU bound。

### 2.2 `timeit`（微基準）

```bash
python3 -m timeit -s 'data=list(range(10**5))' 'sum(data)'
python3 -m timeit -n 100 -r 7 -u usec -s 'import x' 'x.f()'
```

| 選項 | 意義 | 預設 |
|---|---|---|
| `-n N` | 每輪執行次數 | 自動：試 1, 2, 5, 10, 20, 50… 直到總時間 ≥ 0.2 秒 |
| `-r N` | 重複幾輪 | 5 |
| `-s S` | setup（只跑一次，不計時） | `pass` |
| `-p` | 用 `time.process_time()`（CPU 時間） | 預設用 `perf_counter` |
| `-u U` | 單位 `nsec`/`usec`/`msec`/`sec` | 自動 |
| `-v` | 印原始數據 | — |

程式內：

```python
import timeit
best = min(timeit.repeat('f(data)', globals=globals(), number=100, repeat=5)) / 100
# timeit.timeit(stmt, setup, timer, number=1000000, globals=None)
# timeit.repeat(..., repeat=5, number=1000000, ...)
```

注意：`timeit` 預設會在計時期間暫時關閉 GC；回報看「最小值」（受干擾最少）。

### 2.3 `cProfile` + `pstats`（找熱點函式）

```bash
python3 -m cProfile -s cumtime script.py arg1 2>&1 | head -40   # 依累積時間排序印出
python3 -m cProfile -o prof.out script.py                       # 存檔（-s 只在沒有 -o 時有效）
python3 -m cProfile -m package.module                           # 跑模組（3.7+）
```

```python
import pstats
p = pstats.Stats('prof.out')
p.strip_dirs().sort_stats('cumulative').print_stats(20)   # 前 20 名
p.sort_stats('tottime').print_stats(10)                    # 自身時間（不含子呼叫）
p.print_callers('hot_func')                                # 誰呼叫了 hot_func
```

| 排序鍵 | 意義 | 何時用 |
|---|---|---|
| `cumtime` / `cumulative` | 函式本身 + 它呼叫的所有東西 | 找「哪條呼叫路徑」慢 |
| `tottime` / `time` | 只算函式本身 | 找「真正燒 CPU 的那一層」 |
| `ncalls` / `calls` | 呼叫次數 | 找「被呼叫太多次」的小函式 |

只 profile 一段程式（3.8+ 支援 context manager）：

```python
import cProfile, pstats
with cProfile.Profile() as pr:
    hot_section()
pstats.Stats(pr).sort_stats('tottime').print_stats(15)
```

rclpy node：`python3 -m cProfile -o node.prof my_node.py`，跑一陣子後 Ctrl-C（確保程式有 `try/finally` 正常結束，profile 才會寫出），再用 `pstats` 看。callback 名稱會出現在清單裡。

注意：cProfile 對「Python 函式」加開銷、對「C 函式」幾乎不加，所以 profile 下 Python 程式碼看起來比實際更慢 → **profile 找位置，timeit / perf_counter 量大小**。

### 2.4 記憶體

```python
import tracemalloc, sys
tracemalloc.start()                      # tracemalloc.start(25) 記錄 25 層 traceback
build_data()
cur, peak = tracemalloc.get_traced_memory()      # bytes
print(cur, peak)
snap = tracemalloc.take_snapshot()
for st in snap.statistics('lineno')[:10]:
    print(st)                                    # 哪一行配置最多記憶體
tracemalloc.stop()

sys.getsizeof([1, 2, 3])   # 只算容器本身（指標陣列），不含元素物件
```

實測（3.12.3, 64-bit）：`sys.getsizeof(list(range(1000)))` = 8056 bytes（另外 1000 個 int 物件各 28 bytes），`sys.getsizeof(array.array('i', range(1000)))` = 4200 bytes（元素直接存 4 bytes 原始值）。大量數值 → `array` / `bytearray` / numpy 省記憶體且對 cache 友善。

### 2.5 其他內建工具

| 指令 | 用途 |
|---|---|
| `python3 -X importtime x.py 2> imp.txt` | 每個 import 花多久（啟動慢時用；評分若含啟動時間很重要） |
| `python3 -X perf x.py` + `perf record -g` | 3.12+ 讓 Linux `perf` 看得到 Python 函式名 ⚠️需要 `perf` 存在 |
| `python3 -m trace --count x.py` | 每行執行次數（純 Python，很慢） |
| `/usr/bin/time -v python3 x.py` | 牆鐘、CPU、最大 RSS ⚠️`/usr/bin/time` 不一定存在，可改用 bash 內建 `time` |
| `py-spy top --pid N` | 對執行中 process 取樣 ⚠️通常不存在 |

---

## 3. CPython 成本模型（為什麼 Python 慢、哪裡慢）

### 3.1 基本認知

- CPython 是**位元組碼直譯器**：每個運算（`x + 1`、`a[i]`、`obj.attr`）都是數個 bytecode，每個 bytecode 有分派、型別檢查、引用計數成本。一個簡單 Python 層級運算約數十 ns，比 C 慢約 10～100 倍（數量級）。
- **每個 int / float 都是 heap 物件**（int 至少 28 bytes）。`list` 存的是指標。運算結果通常要配置新物件（小整數 -5～256 有快取）。
- 3.11 起有「專門化自適應直譯器」（Faster CPython），熱的 bytecode 會被替換成型別特化版本；3.11 起 `try` 沒丟例外時幾乎零成本；3.12 的 list/dict/set comprehension 被內聯（PEP 709），不再建立額外函式框架。因此很多舊的微優化（快取 method 到區域變數等）在 3.12 收益變小，**要實測**。
- 真正的大收益來自：**(1) 演算法 / 資料結構，(2) 把迴圈推進 C（內建函式、`str.join`、`bytes` 方法、`array`、`struct`、numpy），(3) 減少每筆資料的 Python 層級操作次數**。

### 3.2 各種操作的相對成本（概念排序，由便宜到貴）

| 成本 | 操作 |
|---|---|
| 最便宜 | 區域變數讀寫（`LOAD_FAST`）、小整數運算、`is` / `==` 比較 |
| 便宜 | 全域變數 / 內建名稱查找（dict 查找，3.11+ 有快取）、`list[i]`、`dict[k]`、`len()` |
| 中等 | 屬性存取 `obj.attr`、模組屬性 `math.sqrt`、方法綁定 `lst.append` |
| 較貴 | Python 函式呼叫（建立 frame、傳參數；實測：迴圈中呼叫一個 `return x+1` 的函式約比內聯慢 2 倍）、建立物件、`**kwargs`、例外真的被丟出時 |
| 很貴 | 每筆 I/O 系統呼叫（`print(flush=True)`）、`re` 未預編譯（有快取但仍要查表）、`inspect` 類操作（rclpy logger 內部會用，見 §8.5） |
| 最貴 | 跨 process 傳資料（pickle + 複製）、網路 / DDS 傳輸 |

### 3.3 實測對照（100,000 個 int，單位 ms，僅供數量級）

| 寫法 | 時間 | 備註 |
|---|---|---|
| `for x in data: s += x` | 1.7 | |
| `sum(data)` | 0.55 | C 迴圈，約 3 倍快 |
| `for` + `out.append(x*2)` | 3.6 | |
| 同上但 `ap = out.append` 快取 | 3.7 | **3.12 已無收益** |
| `[x*2 for x in data]` | 3.1 | 約快 15%；主要成本是產生新 int |
| `list(map(lambda x: x*2, data))` | 5.2 | **lambda 比 comprehension 慢**（每次呼叫 Python 函式） |
| 迴圈內 `math.sqrt(x)` | 3.1 | |
| 迴圈內 `sq(x)`（`sq = math.sqrt`） | 2.9 | 小幅（~7%） |
| `sum(map(math.sqrt, data))` | 2.5 | map 搭配 **C 函式** 才快 |
| `sorted(100k)` | 1.3 | Timsort，C 實作；不要自己寫排序 |

結論：**`map` / `filter` 只有搭配內建或 C 函式時才比 comprehension 快**；搭配 lambda 反而慢。

### 3.4 有效的微優化（確定方向正確，但先做演算法）

1. 熱迴圈裡用到的全域函式 / 模組屬性 → 先存成區域變數（`sqrt = math.sqrt`）。
2. 把整個迴圈搬進函式（區域變數比模組層級全域變數快；在模組頂層寫的迴圈，變數都是全域）。
3. 用內建：`sum`、`min`、`max`、`any`、`all`、`sorted`、`len`、`str.join`、`str.translate`、`bytes.count`、`bytes.find`、`collections.Counter`、`itertools.*`、`operator.itemgetter`（排序 key 比 lambda 快）。
4. 避免在迴圈內重複算不變量（`len(x)`、`2**31`、`re.compile(...)`、屬性鏈 `self.a.b.c`）。
5. 條件判斷用 `dict` 分派或查表（LUT）取代長串 `if/elif`。
6. 字串累加用 `''.join(parts)`；`s += t` 在 CPython 有特殊最佳化，實測未必慢，但不保證（不同情況會退化成 O(n²)），**正規寫法是 join**。
7. 大量小物件 → `__slots__`（實測 100k 個兩欄位物件：一般 class 11.7 MiB vs `__slots__` 8.6 MiB；存取速度差異很小）或乾脆用平行的 `array`。
8. 純函式且輸入重複 → `functools.cache` / `lru_cache(maxsize=N)`（實測 `fib(25)`：7.9 ms → 0.008 ms）。參數必須可雜湊。
9. 大量配置物件的批次程式可試 `gc.disable()`（或 `gc.freeze()`）避免循環 GC 反覆掃描 ⚠️效果依程式而定，要實測；長時間執行的 node 不建議關。

---

## 4. 資料結構與標準函式庫的快速工具

### 4.1 時間複雜度速查

| 結構 | 快 | 慢（陷阱） |
|---|---|---|
| `list` | `append`、`pop()`、`a[i]`、尾端操作 O(1) | `pop(0)`、`insert(0, x)`、`x in list`、`remove` 都是 O(n) |
| `collections.deque` | 兩端 `append/appendleft/pop/popleft` O(1)；`maxlen=N` 自動丟最舊 | 中間索引 `d[i]` O(n) |
| `dict` / `set` | 查找、插入、刪除平均 O(1) | 元素需可雜湊；記憶體較多 |
| `heapq`（在 list 上） | `heappush` / `heappop` O(log n)，`heapify` O(n)，`nsmallest(k, it)` | 只有最小堆（最大堆存 `-x`） |
| `bisect`（在已排序 list 上） | 查找 O(log n) | `insort` 插入仍 O(n)（搬移元素，但是 C 的 memmove，很快） |

實測：從 10,000 個元素的佇列前端逐一取出：`list.pop(0)` 4.4 ms vs `deque.popleft()` 0.18 ms（約 24 倍）；1000 次成員查詢（10k 元素）：`in list` 46 ms vs `in set` 0.03 ms（約 1500 倍）。

```python
from collections import deque, defaultdict, Counter
ring = deque(maxlen=100)          # 環形緩衝：保留最近 100 筆
ring.append(v)                     # 滿了自動丟最舊
avg = sum(ring) / len(ring)

import heapq
h = []; heapq.heappush(h, (prio, seq, item)); prio, _, item = heapq.heappop(h)
heapq.nlargest(5, data, key=...)

import bisect
i = bisect.bisect_left(sorted_list, x)                  # 第一個 >= x 的位置
i = bisect.bisect_right(sorted_list, x, key=lambda r: r[0])   # key= 3.10+
```

滑動視窗和：維護累計值（加新的、減掉被 deque 擠出的那個），O(1)／筆，不要每次 `sum(ring)`。

```python
win = deque(maxlen=W); total = 0
def push(v):
    global total
    if len(win) == W:
        total -= win[0]          # 即將被擠掉的最舊值
    win.append(v); total += v
```

### 4.2 二進位資料：`bytes` / `bytearray` / `memoryview` / `array` / `struct` / `int.from_bytes`

| 工具 | 特性 | 典型用途 |
|---|---|---|
| `bytes` | 不可變 | 收到的原始資料、雜湊 key |
| `bytearray` | 可變、可原地修改、`+=` 攤銷 O(1) | 組封包、累積緩衝 |
| `memoryview(buf)` | **零複製**切片；`mv[a:b]` 不複製；`mv.cast('i')` 以 int32 解讀 | 大緩衝的子區段、避免 `buf[a:b]` 複製 |
| `array.array(tc)` | 同質數值陣列，元素存原始值；`frombytes` / `tobytes` 是 memcpy；支援 buffer protocol | 數值序列、與 rclpy 陣列欄位互通（§8.3） |
| `struct.Struct(fmt)` | 預編譯格式；`unpack_from(buf, off)` 不需切片 | 解析固定格式紀錄 |
| `struct.iter_unpack(fmt, buf)` | 依序解析重複紀錄（長度須整除） | 大量同格式紀錄 |
| `int.from_bytes(b, 'little', signed=True)` | bytes → int；3.11+ `byteorder` 預設 `'big'` | 單一欄位、任意長度 |
| `x.to_bytes(4, 'little', signed=True)` | int → bytes | |

`array` 型別碼（64-bit Linux 實測 itemsize）：`'b'/'B'`=1、`'h'/'H'`=2、`'i'/'I'`=4、`'l'/'L'`=**8**、`'q'/'Q'`=8、`'f'`=4、`'d'`=8。**int32 用 `'i'`，不要用 `'l'`**。

`struct` 格式：`<` 小端（無對齊）、`>` 大端、`=` 原生位元組序無對齊、`@`（預設）原生且**有對齊填充**；`b B h H i I q Q f d s ?`，前面可加數量如 `'<100i'`。

實測（解析 100,000 個 little-endian int32，共 400 KB，單位 ms）：

| 寫法 | 時間 |
|---|---|
| `[struct.unpack('<i', raw[i:i+4])[0] for i in ...]` | 12.0 |
| `S = struct.Struct('<i'); [S.unpack_from(raw, i)[0] ...]` | 6.9 |
| `[v for (v,) in struct.iter_unpack('<i', raw)]` | 4.1 |
| `struct.unpack(f'<{n}i', raw)`（一次解完，回傳 tuple） | 1.7 |
| `memoryview(raw).cast('i').tolist()` | 1.8（原生位元組序） |
| `a = array.array('i'); a.frombytes(raw)` | **0.009**（只是 memcpy，元素不轉成 Python int） |

→ 如果後續只是要「存著 / 轉發 / 交給 numpy」，用 `array.frombytes` 或 `memoryview` 不要拆成 Python int。真的要逐一計算時才 `tolist()`。

```python
import struct, array
REC = struct.Struct('<IhH')          # 4+2+2 = 8 bytes/紀錄，預編譯一次
def parse(buf: bytes):
    out = []
    ap = out.append
    for off in range(0, len(buf) - REC.size + 1, REC.size):
        ap(REC.unpack_from(buf, off))   # 不切片、不複製
    return out
# 或：list(REC.iter_unpack(buf))      # 長度必須是 8 的倍數

buf = bytearray(1024)
mv = memoryview(buf)
mv[16:20] = (1234).to_bytes(4, 'little')   # 原地寫入
ints = mv.cast('i')                         # 以原生 int32 視角（長度須整除 4）
ints[0] = -1
```

注意：`array.array('i', [2**31])` 會丟 `OverflowError: signed integer is greater than maximum`（實測）。寫入 int32 陣列前要先處理溢位語義（§11）。

### 4.3 字串

| 慢 | 快 |
|---|---|
| 迴圈 `s += str(x) + '\n'` | `'\n'.join(map(str, xs))` |
| 迴圈內 `re.match(r'...', s)` | 迴圈外 `P = re.compile(r'...')`，迴圈內 `P.match(s)`（實測 100k 次：38 ms → 16 ms） |
| 逐字元 `if c in 'abc'` 替換 | `s.translate(str.maketrans(...))` |
| 能用字串方法卻用 regex | `s.split()`、`s.startswith()`、`s.partition(':')`、`int(s)` |
| `'%s' % x` 在熱迴圈組大字串 | 一次 `join`；f-string 單次格式化很快，但不要在不會用到時先格式化（log，§8.5） |

大整數 ↔ 字串：3.11+ 預設限制 4300 位數（`sys.get_int_max_str_digits()`，實測 4300），超過會 `ValueError`；必要時 `sys.set_int_max_str_digits(0)` 解除。

### 4.4 `itertools` / `functools` / `operator` 常用

```python
import itertools as it, operator as op, functools
it.batched(data, 64)            # 3.12+：每 64 個一組（tuple），批次處理用
it.pairwise(xs)                 # 3.10+：(x0,x1),(x1,x2)...
it.accumulate(xs)               # 前綴和（C 實作）
it.islice(gen, 100)             # 取前 100 個，不建 list
it.chain.from_iterable(lists)   # 攤平
it.groupby(sorted_xs, key=...)  # 連續相同 key 分組（需先排序）
sorted(rows, key=op.itemgetter(1, 0))     # 比 lambda r: (r[1], r[0]) 快
functools.reduce(op.xor, xs, 0)
math.prod(xs); math.sumprod(a, b)         # sumprod 3.12+（內積）
```

### 4.5 預計算與查表（LUT）

```python
# 例：每筆 uint8 要做複雜轉換 → 預先算 256 項
LUT = bytes(f(i) & 0xFF for i in range(256))
out = data.translate(LUT)             # bytes.translate 在 C 內逐 byte 查表，超快
# 位元計數：3.10+ 直接 int.bit_count()
popcnt = (x).bit_count()
```

`bytes.translate(table)` 對 uint8 資料（影像、`UInt8MultiArray`）是純標準函式庫裡最快的逐元素映射方式。

### 4.6 generator vs list

- generator（`(f(x) for x in xs)`）不一次建完整 list → 省記憶體，可提早停止；但每個元素要恢復 generator frame，**總時間通常略慢於 list comprehension**。
- 結果只用一次、資料很大 → generator；要多次使用 / 要 `len` / 要索引 → list。
- `sum(x*x for x in xs)` 與 `sum([x*x for x in xs])` 差距小；資料大時前者記憶體佔優。

---

## 5. I/O：Judge 風格的快速輸入輸出與檔案

### 5.1 讀輸入

實測（200,000 行整數求和）：

| 寫法 | 時間 |
|---|---|
| `for _ in range(n): s += int(input())` | 0.20 s |
| `input = sys.stdin.readline` 後同樣迴圈 | 0.04 s |
| `data = sys.stdin.buffer.read().split(); sum(map(int, data[1:]))` | 0.03 s |

```python
import sys
def main():
    data = sys.stdin.buffer.read().split()   # list[bytes]，int(b'123') 可直接用
    n = int(data[0])
    xs = list(map(int, data[1:1 + n]))
    ...
main()
```

注意：`sys.stdin.readline()` 保留結尾 `\n`（`int()` 會忽略空白，但字串比較要 `.rstrip()`）；`buffer.read()` 拿到的是 `bytes`，字串處理時要 `.decode()`。

### 5.2 輸出

實測（印 200,000 行到檔案 / pipe）：

| 寫法 | 時間 |
|---|---|
| `for i in ...: print(i)` | 0.06 s |
| `sys.stdout.write('\n'.join(map(str, xs)) + '\n')` | 0.03 s |
| `for i in ...: print(i, flush=True)` | **0.37 s**（每行一次 write 系統呼叫，約 6 倍慢） |

- stdout 是 pipe / 檔案時為**區塊緩衝**；是終端機時為**行緩衝**（每行都寫出，且終端機渲染本身也慢）。評分時通常是 pipe。
- `flush=True` 只在「需要即時被別的 process 看到」時用（例如互動式 judge、需要在 node 被殺前看到）。**如果規格要求即時輸出，不要為了速度拿掉**。
- 互動 / 長時間執行的程式想要即時輸出又不想每行 flush：`python3 -u` 或 `PYTHONUNBUFFERED=1` 會讓 stdout 不緩衝（同樣有成本）。
- 除錯輸出寫 `sys.stderr`，不要混進評分用的 stdout。

### 5.3 檔案

```python
with open(path, 'rb') as f:
    data = f.read()                       # 檔案不大：一次讀完最快
with open(path, 'rb') as f:
    while chunk := f.read(1 << 20):       # 大檔：1 MiB 一塊
        process(chunk)
with open(path, 'rb') as f:               # 讀進既有緩衝，不配置新 bytes
    buf = bytearray(1 << 20)
    n = f.readinto(buf)
```

逐行讀文字檔：`for line in f:`（內部有緩衝，夠快）；不要 `f.read(1)` 逐 byte 讀。

---

## 6. GIL 與平行化

### 6.1 GIL 規則（CPython 3.12）

- 同一時間只有一個 thread 執行 Python bytecode → **純 Python CPU 運算開多個 thread 不會變快**（實測 4 個 CPU bound 任務：序列 0.34 s、4 threads 0.30 s、4 processes 0.08 s）。
- 阻塞 I/O（檔案、socket、`time.sleep`、等待鎖）會釋放 GIL → **I/O bound 用 thread 有效**。
- 部分 C 實作在長時間運算時會釋放 GIL（例如 `hashlib` 處理大資料、`zlib`、許多 numpy 運算）⚠️個別函式是否釋放依實作而定。
- 無 GIL 的自由執行緒建置是 3.13 起的實驗功能（PEP 703），3.12 沒有。
- thread 之間共享資料仍要加鎖：GIL 不保證你的複合操作（`d[k] += 1`、check-then-act）是原子的。

### 6.2 選擇表

| 工作型態 | 用什麼 | 注意 |
|---|---|---|
| CPU bound、可切成獨立塊 | `concurrent.futures.ProcessPoolExecutor` / `multiprocessing.Pool` | 參數與結果要 pickle + 跨 process 複製；任務太小時開銷大於收益 → 用 `chunksize` 批次 |
| CPU bound、陣列運算 | numpy 向量化（單 process 就快很多） | §7 |
| I/O bound（等網路、檔案、子程式） | `ThreadPoolExecutor` 或 `asyncio` | |
| 大量並發連線 / 等待 | `asyncio` | 單執行緒；任何阻塞呼叫都會卡住整個 event loop |
| rclpy 多個 callback 互不阻塞 | `MultiThreadedExecutor` + 不同 callback group | 見 `ros2.md` §5.3；仍受 GIL 限制 |

```python
from concurrent.futures import ProcessPoolExecutor
def work(chunk):                         # 必須是模組頂層函式（可 pickle）
    return sum(x * x for x in chunk)

if __name__ == '__main__':               # spawn / forkserver 一定要；fork 也建議
    chunks = [data[i:i + 100_000] for i in range(0, len(data), 100_000)]
    with ProcessPoolExecutor(max_workers=4) as ex:
        total = sum(ex.map(work, chunks))
```

### 6.3 start method（Linux, 3.12）

- 3.12 在 Linux 預設 `fork`（macOS 從 3.8 起是 `spawn`）；**3.14 起預設不再是 fork**。需要特定行為就明確指定：`ctx = multiprocessing.get_context('spawn')`。
- 3.12：process 內已有多個 thread 時 `fork` 會發 `DeprecationWarning`。**rclpy 初始化後的 process 有背景 thread（DDS 等）** → 在 rclpy node 內用 fork 有死結風險 ⚠️。建議：多 process 的計算放在 `rclpy.init()` 之前建立 pool，或用 `get_context('spawn')` / `'forkserver'`，或乾脆拆成多個獨立 node 程式。
- `spawn` 啟動慢（重新 import 主模組），但最安全。

### 6.4 `asyncio`（簡述）

```python
import asyncio
async def fetch(i):
    await asyncio.sleep(0.1)       # 只有 await 的地方會讓出
    return i
async def main():
    return await asyncio.gather(*(fetch(i) for i in range(100)))   # 約 0.1 s 而非 10 s
asyncio.run(main())
```

CPU 運算放 asyncio 不會變快。rclpy callback 可以是 `async def`（executor 會當 coroutine 執行），但不要在 rclpy 裡自己再 `asyncio.run`。

---

## 7. numpy（選用；先確認 `import numpy` 成功）

### 7.1 核心原則

- **把迴圈換成整個陣列的運算**（向量化）：一次 numpy 呼叫在 C 裡跑完整個陣列。
- 每次 numpy 呼叫有固定開銷（微秒級）⚠️依機器；**陣列很小（約數十個元素以下）時純 Python 可能更快**。
- 避免「numpy 陣列 + Python 迴圈逐元素存取」：`for x in arr` / `arr[i]` 每次都要把元素包成 numpy scalar，比 list 還慢。
- 選對 dtype：`int32` / `uint8` / `float32` 比預設 `int64` / `float64` 省記憶體頻寬；但**整數陣列運算溢位會靜默回繞**（不會報錯）。

### 7.2 常用寫法

```python
import numpy as np
a = np.frombuffer(buf, dtype=np.int32)        # 零複製 view；bytes 來源 → 唯讀
a = np.frombuffer(buf, dtype='<i4', count=n, offset=4)   # 指定位元組序、跳過 header
b = a.astype(np.int64)                         # 要寫入或防溢位 → 轉型（會複製）
c = np.empty_like(a); np.multiply(a, 2, out=c) # 預先配置 + out= 避免暫存陣列
a2 = a.copy(); a2 *= 2                         # 原地運算（不能對唯讀 view 做）
mask = a > 0; a[mask].sum(); np.count_nonzero(mask)
np.clip(a, lo, hi, out=a2)
np.cumsum(a); np.convolve(a, k, 'valid'); np.diff(a)
idx = np.searchsorted(sorted_arr, queries)     # 向量化 bisect
img = np.frombuffer(msg.data, np.uint8).reshape(h, w, 3)   # 影像（step == w*3 時）
```

廣播（broadcasting）：形狀從尾端對齊，維度為 1 的會被擴展，例如 `(h, w, 3) * (3,)` 對每個像素的 3 通道各乘一個係數，不需迴圈。

numpy 1.26 注意：`np.asarray` 沒有 `copy=` 參數（2.0 才加）；要確定零複製就用 `np.frombuffer`。

### 7.3 什麼時候 numpy 反而慢

| 情況 | 原因 | 改法 |
|---|---|---|
| 每則訊息只有幾個元素 | 每次呼叫的固定開銷 > 計算本身 | 純 Python，或先累積成大批再算 |
| 逐元素 `arr[i]` 迴圈 | 每次存取都建 numpy scalar | 向量化，或先 `.tolist()` 再用 Python 迴圈 |
| 反覆 `np.append` / `np.concatenate` 增長陣列 | 每次都整個複製 → O(n²) | 先收集到 list，最後一次轉；或預先配置 |
| list → `np.array(list)` 每則訊息都做 | 逐元素轉換 | 來源若是 `array.array` / `bytes` 用 `np.frombuffer` |

---

## 8. rclpy 專屬

### 8.1 rclpy 每則訊息經過的步驟（概念）

```
publisher 端：Python 物件欄位 → (C) _convert_from_py 轉成 C struct → 序列化 (CDR) → DDS
subscriber 端：DDS → 反序列化成 C struct → (C) _convert_to_py：建立 Python 訊息物件、
              逐欄位 setattr（經過 Python property setter）→ executor 排程 → 你的 callback
```

- 每則訊息都有固定的 Python 層開銷：executor 的等待與分派（`executors.py` 為純 Python：每輪收集 entity、建 wait set、用 generator 產生工作）、建立訊息物件、欄位 setter、呼叫 callback。⚠️確切 µs 數依機器，請實測；高頻（數 kHz 以上）小訊息時這通常就是瓶頸。
- 因此「**少量大訊息**」遠比「大量小訊息」有效率（批次化，§8.6）。

### 8.2 訊息欄位的 Python 型別（rosidl_generator_py jazzy）

| IDL 欄位 | Python 型別 | 範例 |
|---|---|---|
| `int32` / `float64` / `bool` 等純量 | `int` / `float` / `bool` | `Int32.data` |
| `string` | `str` | `String.data` |
| 數值**不定長 / 有上限序列** `T[]`、`T[<=N]`（T ∈ float, double, int8～int64, uint8～uint64） | **`array.array`**，型別碼 f d b B h H i I q Q | `Int32MultiArray.data` → `array('i')`；`UInt8MultiArray.data`、`Image.data` → `array('B')` |
| 數值**固定長度陣列** `T[N]` | **`numpy.ndarray`**（對應 dtype） | `Imu.orientation_covariance`（`float64[9]`） |
| `bool` / `byte`（IDL octet）序列、字串序列、巢狀訊息序列 | `list` | `MultiArrayLayout.dim` |

（`.msg` 的 `char` 會被轉成 IDL `uint8`，所以 `char[]` 也是 `array('B')`。含固定長度數值陣列的訊息模組在 import 時就 `import numpy`，這也是 numpy 一定會被裝的原因。）

### 8.3 陣列欄位的快 / 慢路徑（依 jazzy 原始碼）

**欄位檢查預設關閉**（Iron 起）：除非環境變數 `ROS_PYTHON_CHECK_FIELDS=1`（訊息模組 import 時讀取）或建構時 `Msg(check_fields=True)`，setter 不做型別 / 範圍 assert。預設關閉時，數值序列欄位的 setter 一律執行 `self._data = array.array('<tc>', value)`：

| 你指定給 `msg.data` 的值 | `array.array(tc, value)` 的成本（實測 1,000,000 個 int32） |
|---|---|
| `list` of int | 15 ms（逐元素轉換） |
| `array.array('i', ...)`（同型別碼） | 0.09 ms（memcpy） |
| `bytes` / `bytearray`（長度為 itemsize 倍數） | 0.08 ms（走 `frombytes`，memcpy） |
| `memoryview` / numpy 陣列 | 35 ms（memoryview 實測：被當一般 iterable 逐元素處理；numpy 推論相同 ⚠️未實測） |

→ **最佳實務**：
```python
msg.data = array.array('i', values_list)   # 或直接傳 list，成本相同
msg.data = out_array                        # 已是 array('i') → 最快
msg.data = np_arr.astype(np.int32, copy=False).tobytes()   # numpy → bytes → memcpy（tobytes 本身也是 memcpy）
img_msg.data = frame.tobytes()              # 影像 uint8
```
（`ROS_PYTHON_CHECK_FIELDS=1` 時，指定同型別碼的 `array.array` 會直接存參考、不複製；指定 list 會先逐元素做型別與範圍檢查，非常慢 → 量效能時確認這個環境變數沒開。）

**publish 時**：C 端對序列欄位若物件支援 buffer protocol（`array.array` 是）→ 一次 `PyBuffer_ToContiguous` 複製；否則逐元素轉換。
**接收時**：C 端用 `array.frombytes` 一次填入 → `msg.data` 是 `array.array`，取得本身便宜；**昂貴的是你在 Python 逐元素處理它**。

讀取側建議：
```python
d = msg.data                                   # array('i')
total = sum(d); mx = max(d)                    # C 迴圈，但每元素仍包成 int
a = np.frombuffer(d, dtype=np.int32)           # numpy：零複製、可寫（array.array 的 buffer 可寫）
mv = memoryview(d)                             # 零複製子區段 mv[100:200]
```
⚠️ `np.frombuffer(msg.data, ...)` 是 view：之後若修改 / 重新指定 `msg.data`，view 的內容或有效性會跟著變；要保存就 `.copy()`。

### 8.4 callback 規則

1. callback 要短：不 `sleep`、不 busy-wait、不做同步 service call（死結，見 `ros2.md` §5.3）、不做大量 I/O。
2. 不要每則訊息都建立不必要的物件：publisher、QoS、`struct.Struct`、`re.compile`、LUT、numpy 暫存陣列都在 `__init__` 建一次存在 `self`。
3. `self.xxx` 屬性在熱迴圈內反覆讀 → 先存區域變數。
4. 要輸出的訊息物件：每次 `Int32()` 建新物件的成本不大；**不要在 callback 內 `create_publisher`**（建 publisher 非常貴且會留下大量 entity）。重用輸出訊息物件是否安全：publish 會同步序列化，理論上可重用 ⚠️未驗證，保守起見每次建新物件。
5. callback 內丟例外 → `rclpy.spin` 中止、node 結束（`ros2.md` §9）。

### 8.5 logging / print 的成本（依 `rcutils_logger.py`）

`node.get_logger().info(msg, **kwargs)` 的流程：
1. `is_enabled_for(severity)`：level 不夠就直接 return（便宜）。
2. 否則**每次**建立 `CallerId`：`inspect.currentframe()` + `inspect.getframeinfo(frame)`（取原始碼行資訊）+ `os.path.abspath` → 相對昂貴。
3. 檢查 filter（`throttle_duration_sec`、`once`、`skip_first`）— **注意：filter 是在 CallerId 之後才檢查，所以 throttle 掉的呼叫仍付了第 2 步的成本**。
4. 呼叫 C 的 rcutils log → 輸出到 console + 預設還會發布到 `/rosout` topic（`Node(enable_rosout=True)` 為預設）。

另外 f-string 參數在呼叫前就已經格式化完成（不論是否真的印出）。

| 作法 | 建議 |
|---|---|
| 每則訊息 `get_logger().info(f'...')` | 避免 |
| 每則訊息 `print(..., flush=True)` | 避免（若規格要求輸出則保留，見 §5.2） |
| 計數 + timer 每秒印一次摘要 | 推薦 |
| `get_logger().debug(...)` 在預設 INFO level | 便宜（第 1 步就 return），但 f-string 仍會先算 |
| `info('...', throttle_duration_sec=1.0)` | 可用，但每次呼叫仍有 CallerId 成本 |

```python
self.n = 0
self.create_timer(1.0, self.report)
def on_msg(self, msg):
    self.n += 1
    ...
def report(self):
    self.get_logger().info(f'{self.n} msgs/s'); self.n = 0
```

### 8.6 批次化與減少訊息數

- 生產端能控制時：把 N 筆小值打包成一則 `Int32MultiArray`（或自訂陣列訊息）→ executor / 轉換開銷變成每 N 筆一次。
- 消費端無法改格式時：callback 只做「放進 `deque` / `array.append`」，由 timer 定期批次處理（再配合 numpy）。注意延遲會增加。
- 不需要的輸出就不要發（`pub.get_subscription_count() == 0` 時可跳過計算 ⚠️依題意，評分程式可能晚一點才連上）。
- QoS depth：消費者慢時 depth 大 → 延遲累積；depth 小 → 掉舊訊息。選擇依規格「要最新」還是「要完整」，細節見 `ros2.md` §3 / §8。

### 8.7 spin 迴圈與 executor

| 寫法 | 評價 |
|---|---|
| `rclpy.spin(node)` + timer | 正確、推薦 |
| `while rclpy.ok(): rclpy.spin_once(node, timeout_sec=0)` + 自己的工作 | **busy loop，CPU 100%**；且 jazzy 的 `rclpy.spin_once(node)` 每次都會把 node 加進 executor、結束再移除（額外開銷） |
| 必須自己寫迴圈時 | `ex = SingleThreadedExecutor(); ex.add_node(node)` 建一次，迴圈內 `ex.spin_once(timeout_sec=0.01)`（有 timeout 才不會空轉） |
| `MultiThreadedExecutor` | 讓阻塞型 callback 不互卡；**CPU 運算不會變快**（GIL）；需搭配不同 callback group（`ros2.md` §5.3） |
| `rclpy.experimental.EventsExecutor` | rclpy 7.1.4+ 有，C++（pybind11）實作的事件驅動 executor，有 `add_node` / `remove_node` / `spin` / `shutdown`；可降低 executor 本身的 Python 開銷（降幅 ⚠️未實測）；**實驗性**，改用前後都要驗證正確性 |

```python
from rclpy.experimental import EventsExecutor   # 先確認 import 成功
ex = EventsExecutor()
ex.add_node(node)
try:
    ex.spin()
finally:
    node.destroy_node(); rclpy.try_shutdown()
```

### 8.8 進階：raw（序列化 bytes）收發

- `create_subscription(..., raw=True)`：callback 收到的是**序列化後的 `bytes`**（CDR），省掉建 Python 訊息物件。
- `publisher.publish(b)`：參數是 `bytes` 時走 `publish_raw`（jazzy `publisher.py`）。
- `rclpy.serialization.serialize_message(msg)` → `bytes`；`deserialize_message(b, MsgType)` → 訊息物件。
- CDR 格式：前 4 bytes 為封裝 header（小端 CDR 一般是 `00 01 00 00`），之後才是欄位；`Int32` 預期為 8 bytes ⚠️未驗證，先用 `serialize_message(Int32(data=5))` 印出確認再依此解析。
- 只適合簡單、固定格式的訊息；格式解析錯誤不會有任何提示。**這是最後手段**，大多情況改 rclcpp 更穩。

```python
import struct
from rclpy.serialization import serialize_message
print(serialize_message(Int32(data=5)).hex())    # 先確認格式（預期 '0001000005000000' ⚠️）
HDR = b'\x00\x01\x00\x00'
I32 = struct.Struct('<i')
def on_raw(self, b: bytes):
    v = I32.unpack_from(b, 4)[0]
    r = ((v * 2 + 0x80000000) & 0xFFFFFFFF) - 0x80000000     # int32 回繞（依規格）
    self.pub.publish(HDR + I32.pack(r))
```

### 8.9 什麼時候改寫成 C++（rclcpp）

| 訊號 | 判斷 |
|---|---|
| 已拿掉 log / print、callback 內幾乎沒工作，頻率仍上不去 | 瓶頸在 rclpy 每則訊息開銷 → rclcpp |
| 需要同 process 零複製傳大訊息 | 只有 rclcpp 有 intra-process（`ros2.md` §5.2） |
| 需要多核真正並行運算 | rclcpp + MultiThreadedExecutor，或多個 Python process |
| 運算可完全向量化、訊息頻率不高 | numpy 通常就夠，不必改語言 |

改寫前確認：題目是否允許改語言、建置方式（`colcon` 不在 ros_core 中，`ros2.md` §0 / §6）、評分是否只看某支 Python 檔。

---

## 9. 慢 → 快 對照表

加速倍數：**約略值**，多數為本機 3.12.3 實測或可直接推得，標 ⚠️ 的是推估；實際依資料大小與機器而異。

| # | 慢寫法 | 快寫法 | 約略加速 |
|---|---|---|---|
| 1 | `x in some_list`（大 list，重複查） | 先 `s = set(some_list)`，`x in s` | 100～1000×+（依大小） |
| 2 | `list.pop(0)` 當佇列 | `deque.popleft()` | 10～100×（依長度） |
| 3 | 雙層迴圈找配對 O(n²) | dict / set 索引 O(n)，或排序 + bisect | 依 n，常見 100×+ |
| 4 | `for` 累加 | `sum()` / `max()` / `min()` / `any()` | ~3× |
| 5 | `map(lambda x: ...)` | list comprehension | ~1.5× |
| 6 | 每次 `struct.unpack(fmt, buf[i:i+k])` | `struct.iter_unpack` / 一次 `unpack(f'<{n}i')` | 3～7× |
| 7 | bytes 拆成 int list 只為了轉存 | `array.frombytes` / `memoryview` | 100×+ |
| 8 | 迴圈內 `re.match(pattern, s)` | 預編譯 `P.match(s)` | ~2.5× |
| 9 | `input()` 逐行 | `sys.stdin.buffer.read().split()` | ~5～7× |
| 10 | 每行 `print(..., flush=True)` | 一次 `sys.stdout.write('\n'.join(...))` | ~6～12× |
| 11 | 遞迴重複子問題 | `functools.cache` | 指數級 → 線性 |
| 12 | 4 個 thread 跑 CPU 運算 | 4 個 process（`ProcessPoolExecutor`） | ~接近核心數（扣 pickle 開銷） |
| 13 | Python 迴圈逐元素算 10⁵～10⁶ 個數值 | numpy 向量化 | 10～100× ⚠️推估（numpy 未在本機實測） |
| 14 | `msg.data = np_arr`（numpy 指定給序列欄位） | `msg.data = np_arr.tobytes()` | ~數百× ⚠️由 memoryview 實測推論 |
| 15 | `msg.data = list(...)` 大量元素 | 已是 `array.array` 或 `bytes` 直接指定 | ~150×（指定這一步） |
| 16 | callback 內每則 `get_logger().info` | 計數 + timer 每秒印一次 | ⚠️依頻率；高頻時常是主要成本 |
| 17 | 高頻小訊息逐則發布 | 打包成陣列訊息批次發布 | ~接近批次大小倍（每則開銷攤提）⚠️推估 |
| 18 | `while: rclpy.spin_once(node, timeout_sec=0)` | `rclpy.spin(node)` + timer | CPU 使用率大降 |
| 19 | 每次 callback 建 `struct.Struct` / LUT / 暫存陣列 | `__init__` 建一次存 `self` | 小～中 |
| 20 | 迴圈內 `math.sqrt` 屬性查找 | `sqrt = math.sqrt` 區域變數 | ~1.05～1.1×（3.12 已很小） |
| 21 | 逐 byte 映射 `bytes(f(b) for b in data)` | 預算 256 項 LUT + `data.translate(LUT)` | 數十× ⚠️推估 |
| 22 | 反覆 `np.append` 增長 | list 收集後一次 `np.array` / 預先配置 | O(n²) → O(n) |

---

## 10. 實作範例：優化 rclpy subscriber

### 10.1 起點（同考前練習 `processor.py` 的寫法，假設題目改成高頻）

```python
class Processor(Node):
    def __init__(self):
        super().__init__('processor')
        self.sub = self.create_subscription(Int32, '/number', self.on_msg, 10)
        self.pub = self.create_publisher(Int32, '/double', 10)

    def on_msg(self, received):
        print(f'received: {received.data}', flush=True)   # 每則一次 write 系統呼叫
        out = Int32()
        out.data = received.data * 2                       # 溢位語義未定義（見 §11）
        self.pub.publish(out)
```

### 10.2 步驟

1. **量測基準**：`ros2 topic hz /number` 與 `ros2 topic hz /double` 比較（輸出頻率低於輸入 → 跟不上）；在 callback 內用 `perf_counter_ns` 累計耗時，timer 每秒印平均。
2. **確認規格**：`received: ...` 這行輸出是不是評分的一部分？是 → 保留但考慮拿掉 `flush=True`（看是否需要即時）；不是 → 移除或改為計數摘要。
3. **確認溢位語義**：`data * 2` 超出 int32 時要回繞、夾限、還是報錯？Jazzy 預設不檢查欄位（§8.3），超範圍值在 C 轉換時被強制轉型 ⚠️（實際行為未實測），所以要自己明確處理。
4. 改寫並驗證輸出完全一致（用 `ros2 topic echo /double` 或自己的測試 publisher 送邊界值 0、1、-1、2³⁰、2³¹-1、-2³¹）。
5. 若仍跟不上：檢查是否能批次化（§8.6）、換 `EventsExecutor`（§8.7）、或改 rclcpp（§8.9）。

### 10.3 優化後（純量版本）

```python
import sys, time
import rclpy
from rclpy.node import Node
from rclpy.executors import ExternalShutdownException
from std_msgs.msg import Int32

MASK = 0xFFFFFFFF
SIGN = 0x80000000

def wrap_i32(v: int) -> int:
    return ((v + SIGN) & MASK) - SIGN       # 二補數回繞；若規格要求夾限則改 max/min

class Processor(Node):
    def __init__(self):
        super().__init__('processor')
        self.pub = self.create_publisher(Int32, '/double', 10)
        self.sub = self.create_subscription(Int32, '/number', self.on_msg, 10)
        self.n = 0
        self.busy_ns = 0
        self.create_timer(1.0, self.report)

    def on_msg(self, received):
        t0 = time.perf_counter_ns()
        v = received.data
        sys.stdout.write(f'received: {v}\n')      # 若規格需要此輸出；不 flush
        out = Int32()
        out.data = wrap_i32(v * 2)
        self.pub.publish(out)
        self.n += 1
        self.busy_ns += time.perf_counter_ns() - t0

    def report(self):
        if self.n:
            sys.stderr.write(f'{self.n} msg/s, avg {self.busy_ns / self.n / 1000:.1f} us\n')
        self.n = 0; self.busy_ns = 0
        sys.stdout.flush()                          # 每秒 flush 一次，兼顧即時性

def main():
    rclpy.init()
    node = Processor()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()

if __name__ == '__main__':
    main()
```

### 10.4 陣列版本（`std_msgs/msg/Int32MultiArray`，每則數千～數十萬元素）

```python
import array
from std_msgs.msg import Int32MultiArray
try:
    import numpy as np
except ImportError:
    np = None

class ArrayProc(Node):
    def __init__(self):
        super().__init__('array_proc')
        self.pub = self.create_publisher(Int32MultiArray, '/out', 10)
        self.sub = self.create_subscription(Int32MultiArray, '/in', self.on_msg, 10)

    def on_msg(self, msg):
        d = msg.data                                   # array('i')，接收端已是 memcpy 填入
        out = Int32MultiArray()
        out.layout = msg.layout                        # 若需保留 layout（依規格）
        if np is not None:
            a = np.frombuffer(d, dtype=np.int32)       # 零複製
            r = a * np.int32(2)                        # int32 運算：溢位自動二補數回繞
            out.data = r.tobytes()                     # bytes → array('i') 走 memcpy
        else:
            M, S = 0xFFFFFFFF, 0x80000000
            out.data = array.array('i', [((x * 2 + S) & M) - S for x in d])
        self.pub.publish(out)
```

本機實測（100,000 個 int32，純 Python 部分）：naive `for`+`append` 3.8 ms；comprehension 包 `array` 4.6 ms；含回繞運算的 comprehension 10.1 ms。numpy 版本預期 < 1 ms ⚠️未實測。若每秒 100 則 → 純 Python 版 CPU 約 100%，numpy 版明顯有餘裕。

`sum` / `max` / `min` 類統計直接 `sum(d)`（實測 100k 個約 1.1 ms）或 `int(a.sum(dtype=np.int64))`（避免 int32 累加溢位）。

### 10.5 驗證

- 同一組輸入（含邊界值）比對優化前後的輸出（`ros2 topic echo /out --once` 或寫一個測試 subscriber 存檔後 `diff`）。
- 比對頻率：`ros2 topic hz /out` 應等於輸入頻率。
- 記錄到 `03-optimize.md` 的實驗紀錄表。

---

## 11. 常見陷阱

1. **int 溢位語義**：Python `int` 不會溢位；`array('i')` 超範圍丟 `OverflowError`；numpy int32 陣列運算靜默回繞；rclpy Jazzy 預設不檢查訊息欄位範圍，超範圍值會在 C 轉換時被強制轉型（int32 純量欄位依 `_msg_support.c.em` 是 `(int32_t)PyLong_AsLong(v)`，64-bit Linux 上相當於取低 32 位 ⚠️未實測確切結果）。優化前後語義必須一致，且符合規格。
2. **浮點結果些微不同**：`sum` 順序改變、numpy 的 pairwise summation、float32 vs float64 → 末幾位不同；比對時看規格允許的誤差。`math.fsum` 最精確。
3. **profile 下的時間被放大**：cProfile 只對 Python 函式加開銷。
4. **量到第一次執行**：import、.pyc 編譯、DDS discovery 都在開頭；量穩態。
5. **在模組頂層寫熱迴圈**：變數全是全域，較慢 → 包進 `main()`。
6. **`np.frombuffer(bytes)` 是唯讀**：原地修改會丟 `ValueError` → 先 `.copy()` 或用 `bytearray` 來源。
7. **`memoryview` / numpy view 拉住底層緩衝**：`bytearray` 在有 export 的 view 存在時不能改大小（`BufferError`）。
8. **`array('l')` 在 64-bit Linux 是 8 bytes**：int32 用 `'i'`。
9. **`struct` 預設 `@` 有對齊填充**：解析網路 / 檔案格式用 `<` 或 `>`。
10. **multiprocessing 在 rclpy 內 fork**：有背景 thread，可能死結；用 `spawn` 或在 `rclpy.init()` 前建 pool。
11. **`ROS_PYTHON_CHECK_FIELDS=1` 開著做效能量測**：list 指定會變超慢。
12. **拿掉了評分需要的輸出**：先讀規格再刪 print。
13. **`MultiThreadedExecutor` 期待 CPU 加速**：GIL；而且所有 callback 在預設 group 時仍是一次一個。
14. **`lru_cache` 用在有副作用或參數不可雜湊（list）的函式**：錯誤或 `TypeError`；也會無限長大（`cache` 無上限）。
15. **generator 只能迭代一次**：第二次迭代是空的，結果默默變少。

---

## 12. 除錯 / 量測清單

- [ ] `python3 --version`、`import numpy`、rclpy 版本都確認了？
- [ ] 有基準數據（時間 / 頻率 / CPU%），並記錄量測方法？
- [ ] 用 cProfile 找到 `tottime` 最大的函式？熱點是 Python 迴圈、I/O、還是 rclpy 開銷？
- [ ] 牆鐘時間 vs `process_time`：CPU bound 還是在等？
- [ ] callback 內有沒有 `print(flush=True)` / `get_logger().info` / `sleep` / 同步 call？
- [ ] `ROS_PYTHON_CHECK_FIELDS` 是否被設定（`echo $ROS_PYTHON_CHECK_FIELDS`）？
- [ ] 陣列欄位是不是被逐元素處理？指定給 `msg.data` 的型別是什麼？
- [ ] `ros2 topic hz` 輸入 vs 輸出頻率？QoS depth 是否造成延遲累積或掉包？
- [ ] 量測本身（多開的 `echo` / `hz`、自己的 log）有沒有干擾？
- [ ] 優化後輸出與優化前逐筆一致（含邊界值）？

## 13. 優化清單（由收益大到小）

1. 演算法 / 資料結構（set/dict 查找、deque、heapq、bisect、預計算、快取）。
2. 移除不必要的工作（多餘輸出、重複轉換、沒人訂閱的計算、重複建立物件）。
3. I/O 批次化（一次讀、一次寫、不逐行 flush）。
4. 把迴圈推進 C：內建函式、`str.join`、`bytes.translate`、`struct.iter_unpack`、`array.frombytes`、`itertools`。
5. numpy 向量化（大陣列；先確認可 import）。
6. rclpy：callback 變短、批次化訊息、陣列欄位走 buffer 路徑、logging 改摘要、spin 用 timer 驅動、試 `EventsExecutor`。
7. 平行：CPU bound 用多 process；I/O bound 用 thread / asyncio。
8. 換語言：熱路徑改 rclcpp（`ros2.md` §5）。
9. 微優化（區域變數快取、`__slots__`、`operator.itemgetter`）— 最後才做，且 3.12 收益小。

---

## 14. 向模型提問的範本

### 14.1 找瓶頸

```
以下是一支 Python 3.12 程式（{{用途，例如：rclpy subscriber，處理 Int32MultiArray}}）與 cProfile 輸出（依 tottime 排序前 20 行）。
環境：{{ros:jazzy-ros-core / 是否有 numpy / 是否可安裝套件：不可}}。
規格要求：{{輸出格式、溢位語義、延遲 / 吞吐量目標}}。
請：1) 指出前三個瓶頸並解釋原因（引用 profile 數據）；2) 每個瓶頸給一個不改變輸出語義的改法；3) 預估收益（標明是推估）。
程式：
{{貼程式}}
profile：
{{貼 pstats 輸出}}
```

### 14.2 改寫熱迴圈

```
請把下列 Python 熱迴圈改寫得更快，限制：只能用標準函式庫（先給這版），再另外給一個 numpy 版本（numpy 為選用）。
資料規模：{{每次 N 個元素、每秒 M 次}}；資料型別：{{int32 / uint8 / float}}；溢位語義：{{回繞 / 夾限 / 不會發生}}。
兩個版本都要附一段用 timeit 比較新舊版本並驗證輸出完全相同的測試碼。
{{貼迴圈}}
```

### 14.3 rclpy node 跟不上頻率

```
這個 rclpy node（ROS 2 Jazzy，Python 3.12）收 {{topic / 型別}}，輸入頻率 {{X Hz}}，但 ros2 topic hz 量到輸出只有 {{Y Hz}}。
callback 平均耗時 {{Z us}}（perf_counter_ns 量測）。QoS：{{depth / reliability}}。
請依序檢查：callback 內的 log/print、物件建立、陣列欄位轉換方式（array.array / bytes / numpy）、executor 用法、批次化可能性，
並判斷是否必須改用 rclcpp。每個建議請說明是否會改變輸出內容。
{{貼程式}}
```

### 14.4 解析二進位資料

```
我要在 Python 3.12（只能用標準函式庫）解析這種二進位格式：{{欄位清單：名稱/型別/位元組序/偏移}}，每筆 {{K}} bytes，共 {{N}} 筆。
請用 struct.Struct 預編譯 + iter_unpack 或 unpack_from 寫出解析函式，並說明為什麼比逐筆切片快；
若後續只需要 {{某欄位}} 做 {{計算}}，請給出用 memoryview / array.frombytes 避免建立 Python 物件的寫法。
```

### 14.5 驗證優化結果

```
以下是優化前後的兩個版本與量測數據（各跑 {{次數}} 次的最小值 / 中位數）。
請：1) 設計一組能抓到語義差異的測試輸入（含邊界值：{{列出}}）；2) 判斷數據差異是否顯著；3) 指出量測方法可能的誤差來源（暖機、輸出緩衝、背景 process）。
{{貼兩版程式與數據}}
```
