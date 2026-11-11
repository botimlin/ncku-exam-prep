# Python / rclpy 效能速查（精簡版）
用途：備援 pack，加速 Python 程式與 rclpy node。適用：Python 3.12.3、numpy 1.26（ros_core 經 rosidl_generator_py 相依會裝）、Jazzy rclpy 7.1.x。來源：docs.python.org/3.12、github.com/ros2/{rclpy,rosidl_python}（jazzy）、numpy.org/doc/1.26。最後更新 2026-11。數字為本機實測數量級。

## 量測
- `time.perf_counter_ns()` 牆鐘；`time.process_time()` CPU（差很多=在等）。量測輸出寫 stderr
- `python3 -m timeit -s 'setup' 'stmt'`（-n 次數 -r 輪數=5，看最小值）
- `python3 -m cProfile -s cumtime x.py`；`-o p.out` 後 `pstats.Stats('p.out').strip_dirs().sort_stats('tottime').print_stats(20)`。cProfile 只放大 Python 函式開銷
- `tracemalloc.start(); ...; tracemalloc.get_traced_memory()`；`python3 -X importtime`
- 先確認：`import numpy`、`echo $ROS_PYTHON_CHECK_FIELDS`（=1 時欄位檢查很慢）

## 慢→快（約略倍數）
| 慢 | 快 | 倍 |
|---|---|---|
| `x in list` | `set` | 100～1000+ |
| `list.pop(0)` | `deque.popleft()`；環形緩衝 `deque(maxlen=N)` | 10～100 |
| for 累加 | `sum/max/min/any` | ~3 |
| `map(lambda)` | list comprehension（map 只配 C 函式才快） | ~1.5 |
| 逐筆 `struct.unpack(buf[i:i+4])` | `Struct.unpack_from`/`iter_unpack`/一次 `unpack(f'<{n}i')` | 3～7 |
| bytes→int list 只為轉存 | `array.frombytes`/`memoryview` 零複製 | 100+ |
| 迴圈內 `re.match(pat)` | 預編譯 `P.match` | ~2.5 |
| `input()` | `sys.stdin.buffer.read().split()` | 5～7 |
| 每行 `print(flush=True)` | `sys.stdout.write('\n'.join(map(str,xs)))` | 6～12 |
| 重複子問題 | `functools.cache` | 指數→線性 |
| uint8 逐 byte 映射 | 256 項 LUT + `bytes.translate` | 數十 ⚠️ |
| 大陣列 Python 迴圈 | numpy 向量化（小陣列反而慢） | 10～100 ⚠️ |
- 3.12 快取 `ap=lst.append` 已無收益；熱迴圈包進函式；`s+=` 改 `join`
- `array('i')`=int32（`'l'` 是 8 bytes）；超範圍丟 `OverflowError`；`struct` 用 `<`/`>` 免對齊

## GIL / 平行
- 純 Python CPU 運算：thread 無效（4 thread 0.30s vs 序列 0.34s vs 4 process 0.08s）；I/O 用 thread/asyncio
- `ProcessPoolExecutor`：函式需頂層、`if __name__=='__main__':`、pickle 成本→大塊/`chunksize`
- 3.12 預設 fork；rclpy 有背景 thread → 用 `get_context('spawn')` 或在 `rclpy.init()` 前建 pool。3.12 無 free-threaded
- `MultiThreadedExecutor` 只讓阻塞 callback 不互卡，不加速運算

## rclpy 內部（jazzy 原始碼）
- 數值序列 `T[]`→`array.array`（int32 `'i'`、uint8 `'B'`：`Int32MultiArray.data`、`Image.data`）；固定長 `T[N]`→`numpy.ndarray`
- 欄位檢查預設關（Iron 起）；setter 一律 `array.array(tc, value)`：給 `array`/`bytes`=memcpy（1M 元素 0.09ms）、`list` 15ms、memoryview/numpy 逐元素 35ms → numpy 用 `msg.data = a.tobytes()`
- 讀：`np.frombuffer(msg.data, np.int32)` 零複製可寫 view；`np.frombuffer(bytes)` 唯讀
- 不檢查範圍：int32 超範圍在 C 端強制轉型 ⚠️→自己處理 `((v+2**31)&0xFFFFFFFF)-2**31`
- 每則訊息有固定 Python 開銷（executor 純 Python + 建物件 + setter）→ 批次成陣列訊息
- `get_logger().info`：每次都 `inspect` 取呼叫者（throttle 也一樣）+ /rosout → 熱 callback 改計數、timer 每秒印
- 不要 `while: rclpy.spin_once(node,timeout_sec=0)`（空轉，且每次 add/remove node）；用 `spin`+timer，或 executor 建一次再 `ex.spin_once(timeout_sec=0.01)`
- `from rclpy.experimental import EventsExecutor`（7.1.4+，C++ 實作，實驗性，先驗證）
- `create_subscription(..., raw=True)` 收 CDR bytes；`pub.publish(bytes)` 走 raw；`rclpy.serialization.serialize_message` 先印出確認格式 ⚠️
- 仍跟不上 → rclcpp（intra-process 零複製見 ros2.md）

## 陷阱
規格要求的輸出不能刪；優化前後比對邊界值（0、-1、2³¹-1、-2³¹）；浮點順序改變末位不同；量穩態不量首次；numpy int32 靜默回繞、累加用 `sum(dtype=np.int64)`；generator 只能迭代一次。
