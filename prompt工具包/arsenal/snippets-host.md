# 軍火庫：電腦端程式片段（序列埠、多板、ROS 2、micro-ROS、演算法、效能）
> 用法：一次只貼一張卡（兩條 `---` 之間），再寫你的問題。程式照抄，只換 `<尖括號>`；「要換」寫了每個要換的東西。
> 來源與驗證：`預製程式碼/` 的 ros2、micro-ros、algo、bits-riscv、linux-perf。Python 用 pyserial + `fake_pico.py` 實跑；C 用 `gcc -O2 -Wall -Wextra -std=c11 -fsanitize=address,undefined` 實跑（PERF 另跑 `-fsanitize=thread`）；rclpy 沒裝 → ROS 卡從範本複製；micro-ROS 卡只驗編譯｜最後更新 2026-11-13

---

【片段卡｜HOST-SERIAL 1/3｜開 port、送一包、等回覆（frame.py）】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
```python
import serial
from frame import CMD_SUM_U32, pack_u32, unpack_u32, transact

ser = serial.Serial("<PORT>", timeout=0.05)   # USB CDC 不看 baudrate
reply = transact(ser, CMD_SUM_U32, pack_u32(<values>), seq=<1>)
total = unpack_u32(reply)[0]
ser.close()
```
要換：`<PORT>` = `/dev/ttyACM0` 之類（`ls /dev/ttyACM*`）；`<values>` = 整數 list；`<1>` = 序號 0～255。
- `transact(ser, cmd, payload, seq=0, timeout=1.0, retries=3)` → 回傳回覆的 payload（`bytes`）；全部逾時丟 `TimeoutError`。
- 只收「同 cmd、同 seq（低 8 bit）」的回覆；每次送前先 `reset_input_buffer()`。
- 封包：`AA 55 | cmd u8 | seq u8 | len u16 | payload | crc32 u32`，全部小端；crc 範圍 = cmd 到 payload 結尾。
- cmd：`0x01` ECHO、`0x02` SUM_U32、`0x03` CRC32。
✗ 錯：`serial.Serial(port)`（timeout=None）→ 沒回覆時 `read` 永遠卡住，不會重送 → ✓ 對：`timeout=0.05`。
✗ 錯：一包 payload > `MAX_LEN`=8192 → Pico 丟包、不回 → ✓ 對：HOST-SERIAL 2/3 切包。
前提：`frame.py` 放同資料夾；`pip install pyserial`；`import serial`。
驗證：`python3 fake_pico.py --link /tmp/ttyFAKE` → `<PORT>`=`/tmp/ttyFAKE0`；`pack_u32([1, 2, 3, -1])` → `total == 5`（實跑通過）。

---

【片段卡｜HOST-SERIAL 2/3｜數字一次轉 bytes、切包、加總 mod 2^32】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
```python
import array
from frame import CHUNK_BYTES, CMD_SUM_U32, transact, unpack_u32

data = array.array("i", <values>).tobytes()   # int32 小端，一次轉完
step = CHUNK_BYTES // 4 * 4                   # 每包 bytes（4 的倍數）
total = 0
for k, i in enumerate(range(0, len(data), step)):
    reply = transact(ser, CMD_SUM_U32, data[i:i + step], seq=k)
    total = (total + unpack_u32(reply)[0]) & 0xFFFFFFFF
signed = total - (1 << 32) if total >= 1 << 31 else total
```
要換：`<values>` = int32 範圍的整數 list；`ser` 照 HOST-SERIAL 1/3 開。
| 100 萬個數轉 bytes | 實測 |
|---|---|
| `array.array("i", v).tobytes()` | 19.5 ms |
| `pack_u32(v)` | 82 ms |
| 每個 `struct.pack` 再 `join` | 124 ms |
- 有 ≥ 2^31 的 u32 → 用 `array.array("I", v)` 或 `pack_u32(v)`；`"i"` 會丟 `OverflowError`。
- `seq=k` 只取低 8 bit，超過 255 繞回 0 沒關係（一次只等一包）。
- `CHUNK_BYTES`=4096，要 ≤ Pico `FRAME_MAX_PAYLOAD`=8192。
✗ 錯：`step` 不是 4 的倍數 → 一個 u32 被切兩半 → ✓ 對：`CHUNK_BYTES // 4 * 4`。
✗ 錯：CRC32 也切包再相加 → 答案錯；CRC 要整份一次算。
前提：`import array`；`frame.py` 同資料夾。
驗證：10 萬個隨機 int32 經 fake_pico 切 98 包 → `total == sum(values) & 0xFFFFFFFF`，且 `data == pack_u32(values)`（實跑通過）。

---

【片段卡｜HOST-SERIAL 3/3｜文字一行 vs 二進位固定長度】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
```python
import serial

ser = serial.Serial("<PORT>", timeout=1.0)        # readline 最多等 1 秒
ser.reset_input_buffer()
ser.write(("<CMD> " + " ".join(map(str, <values>)) + "\n").encode())
line = ser.readline().decode(errors="replace").strip()  # 去掉 \r\n
if not line:
    raise TimeoutError("沒收到一整行")
ans = int(line)
# 二進位：對方回固定 <n> bytes
buf = ser.read(<n>)                   # 最多等 timeout
if len(buf) < <n>:
    raise TimeoutError(f"只收到 {len(buf)} bytes")
```
要換：`<PORT>`；`<CMD>` = 題目的文字指令；`<values>` = 整數 list；`<n>` = 預期 bytes 數。
| 對方送什麼 | 用 |
|---|---|
| `printf("%d\n", x)` 一行文字 | `readline()` → `.decode().strip()` → `int()` 或 `.split(",")` |
| 二進位 / 封包 | `read(n)` 或 frame.py 的 `FrameParser` |
- 逾時**不會丟例外**：`readline()` 回 `b""`、`read(n)` 回不足 n bytes → 自己檢查。
- Pico `printf` 的 `\n` 預設變 `\r\n`（`PICO_STDIO_DEFAULT_CRLF` = 1）→ `.strip()` 去掉。
✗ 錯：二進位資料用 `readline()` → 資料裡的 `0x0A` 被當行尾（實測 16 bytes 只拿到 11）→ ✓ 對：`read(n)`。
✗ 錯：`timeout=None` → 沒換行就永遠卡住。
前提：`import serial`（pyserial）。
驗證：pty 假裝置回 `"25\r\n"` → `ans == 25`；`read(8)` 拿到 `00 01 … 07`（實跑通過）。

---

【片段卡｜HOST-MULTI 1/2｜N 塊板子平行算（multi_device.run_parallel）】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
```python
from multi_device import split, run_parallel, merge_sum
from frame import CMD_SUM_U32, pack_u32

ports = ["<PORT0>", "<PORT1>"]
chunks = split(pack_u32(<values>))     # 每塊 ≤ CHUNK_BYTES、4 的倍數
replies = run_parallel(ports, chunks, CMD_SUM_U32)   # 依 chunk 順序
ans = merge_sum(replies)
```
要換：`<PORT0>`、`<PORT1>` = 每塊板子的 port（可再加）；`<values>` = 整數 list。
multi_device.py 怎麼做：
- `split(data, chunk_bytes=CHUNK_BYTES, align=4)` → `list[bytes]`。
- `run_parallel(ports, chunks, cmd)`：每個 port 一條 `threading.Thread`，各自開 `serial.Serial`；chunk 放在共用 `queue.Queue`，誰先做完誰拿下一塊（快的板子多做）。
- 結果存 `results[idx]`（`seq=idx`）→ 回來順序亂也沒關係。
- 有一塊逾時 → 丟 `RuntimeError("有 chunk 失敗，見上方訊息")`。
- 會印 `每個 port 做了幾塊: {...}`。
✗ 錯：多條執行緒共用一個 `ser` → 回覆互搶 → ✓ 對：一個 port 一條執行緒、各自開。
✗ 錯：同一個 port 在 `ports` 寫兩次 → 兩條執行緒搶同一個 port。
前提：`multi_device.py`、`frame.py` 同資料夾；`pip install pyserial`。
驗證：`python3 fake_pico.py -n 2 --link /tmp/ttyFAKE` → ports = `/tmp/ttyFAKE0`、`/tmp/ttyFAKE1`；5 萬個 u32 切 49 塊（24 + 25）→ `ans == sum(values) & 0xFFFFFFFF`（實跑通過）。

---

【片段卡｜HOST-MULTI 2/2｜合併結果：加總 / 串接 / 排序 k-way】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
```python
import array, heapq
from frame import unpack_u32

def merge_sum(replies):          # 每塊回 1 個 u32
    return sum(unpack_u32(r)[0] for r in replies) & 0xFFFFFFFF

def merge_concat(replies):       # 逐元素運算（平方、ECHO…）
    return b"".join(replies)

def merge_sorted(replies):       # 每塊已排序 → k-way merge
    return list(heapq.merge(*(unpack_u32(r) for r in replies)))

def merge_sorted_i32(replies):   # 有號 int32 排序
    return list(heapq.merge(*(array.array("i", r).tolist() for r in replies)))
```
用法：`ans = merge_sorted(run_parallel(ports, chunks, <CMD_SORT>))`
要換：`<CMD_SORT>` = 題目的排序指令（frame.py、fake_pico.py、Pico 三邊一起加）。
| 題目 | 合併 |
|---|---|
| 加總 | `merge_sum` |
| 每個元素各自算 | `merge_concat` |
| 排序 | 各塊排好 → `merge_sorted` |
| CRC32 | 不能相加：整份一次算，或協定多帶「上一包的 crc」續算（`zlib.crc32(data, prev)`） |
✗ 錯：有號資料用 `unpack_u32` 解 → 負數變成很大的正數、排序錯 → ✓ 對：`merge_sorted_i32`。
✗ 錯：照「回來的先後」接 → 順序亂；`run_parallel` 回傳的 list 已依 chunk 編號排好。
前提：`import array, heapq`；`from frame import unpack_u32`。
驗證：fake_pico 2 個 port，用 ECHO 回各塊（先排好）→ `merge_sorted(...) == sorted(values)`、`merge_concat(...) == data`、有號版也對（實跑通過）。

---

【片段卡｜HOST-ROS 1/4｜最小節點 class：參數、QoS、訂閱→處理→發布】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
```python
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from std_msgs.msg import Int32

class Processor(Node):
    def __init__(self):
        super().__init__("<processor>")
        self.declare_parameter("factor", 2)
        self.factor = self.get_parameter("factor").value
        qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE)
        self.pub = self.create_publisher(Int32, "</double>", qos)
        self.sub = self.create_subscription(Int32, "</number>", self.on_msg, qos)

    def on_msg(self, msg):
        out = Int32()
        out.data = <msg.data * self.factor>
        self.pub.publish(out)
```
要換：`<processor>` = 節點名；`</number>`、`</double>` = topic；`<msg.data * self.factor>` = 運算；`Int32` = 題目型別（import 一起改）。
- 參數不改程式：`--ros-args -p factor:=3`。
- qos 直接寫 `10` = RELIABLE、VOLATILE、depth 10。
✗ 錯：RELIABLE 訂閱 BEST_EFFORT 發布者 → 收不到 → ✓ 對：`ReliabilityPolicy.BEST_EFFORT`。
前提：main 見 HOST-ROS 2/4。從 `node_template.py`、`host_driver.py` 節錄，沒有實跑（只做語法檢查）。
驗證：`ros2 node list` 看到 `/<processor>`。

---

【片段卡｜HOST-ROS 2/4｜main：spin、Ctrl+C 收尾、測試指令】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
```python
def main():
    rclpy.init()
    node = Processor()
    try:
        rclpy.spin(node)          # 沒有 spin，callback 永遠不會被呼叫
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()
```
```bash
source /opt/ros/jazzy/setup.bash
python3 <node.py> --ros-args -p factor:=3
ros2 topic echo /double
ros2 topic pub --once /number std_msgs/msg/Int32 "{data: 21}"
ros2 topic info -v /number      # 看 QoS、幾個 pub/sub
```
要換：`Processor` = HOST-ROS 1/4 的 class 名；`<node.py>` = 檔名。
- `rclpy.try_shutdown()`：已經 shutdown 也不會出錯（Ctrl+C 時常見）。
- `spin` 是單執行緒：callback 一個一個跑。
✗ 錯：Ctrl+C 後再 `rclpy.shutdown()` → 可能丟例外 → ✓ 對：`try_shutdown()`。
前提：`import rclpy`、`from rclpy.executors import ExternalShutdownException`。從 `node_template.py` 原樣複製，這次沒有實跑。
驗證：factor 3、pub 21 → echo 出現 `data: 63`。

---

【片段卡｜HOST-ROS 3/4｜Int32MultiArray / UInt8MultiArray 快速收發】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
```python
import array
from std_msgs.msg import Int32MultiArray, UInt8MultiArray

msg = Int32MultiArray()
msg.data = array.array("i", <values>)   # list 也可以；值要在 int32 範圍
self.pub.publish(msg)                   # 不要填 msg.layout

def on_numbers(self, msg):              # 收到的 msg.data 是 array('i')
    raw = msg.data.tobytes()            # 小端 int32 bytes → 直接送序列埠
    vals = msg.data.tolist()

b = UInt8MultiArray()
b.data = array.array("B", <payload>)    # <payload> = bytes
payload = bytes(msg.data)               # 收 UInt8MultiArray → bytes
```
要換：`<values>` = 整數 list。
- Jazzy 的 setter 做 `array.array('<碼>', value)`（rosidl_python `_msg.py.em`）。碼：`int32 i`、`uint32 I`、`uint8 B`、`int8 b`、`float32 f`、`float64 d`。
✗ 錯：≥ 2^31 的值放 `Int32MultiArray` → `OverflowError` → ✓ 對：用 `UInt32MultiArray` 或先 `v - (1 << 32)`。
✗ 錯：填 `layout.dim` 送 micro-ROS 板子 → 板子收不到。
前提：`source /opt/ros/jazzy/setup.bash`。從 `serial_bridge.py`、`host_driver.py` 整理，沒有實跑 rclpy（`array` 部分用純 Python 驗過）。
驗證：`ros2 topic pub --once /numbers std_msgs/msg/Int32MultiArray "{data: [1, 2, 3]}"` → callback 裡 `vals == [1, 2, 3]`。

---

【片段卡｜HOST-ROS 4/4｜量 callback 花多久、topic 頻率】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
```python
import time

def on_numbers(self, msg):
    t0 = time.perf_counter()
    <處理並 publish>
    ms = (time.perf_counter() - t0) * 1000
    self.get_logger().info(f"{len(msg.data)} 個數字, {ms:.1f} ms")
```
```bash
ros2 topic hz /<out_topic>     # 每秒幾筆
ros2 topic bw /<out_topic>     # 每秒多少 bytes
```
要換：`<處理並 publish>` = 你的運算 + `self.pub.publish(...)`；`<out_topic>` = 輸出 topic。
- 吞吐量：`len(msg.data) * 4 / (ms / 1000) / 1024` = KiB/s（int32 一個 4 bytes）。
- `rclpy.spin` 是單執行緒：一個 callback 慢，其他 callback 全部排隊。
- 比較前後版本：同一份輸入、各跑幾次取最快，答案也要一樣。
✗ 錯：`time.time()`（會被改系統時間影響）→ ✓ 對：`time.perf_counter()`。
✗ 錯：只量 callback 就說「整條變快」→ 端到端看 `ros2 topic hz`。
前提：`import time`；`source /opt/ros/jazzy/setup.bash`。從 `serial_bridge.py` 的 `on_numbers` 節錄，這次沒有實跑 rclpy（計時程式用假 logger 跑過）。
驗證：log 每筆印出 `N 個數字, x.x ms`；`ros2 topic hz` 印 `average rate: …`。

---

【片段卡｜HOST-UROS 1/4｜Pico 端：Int32MultiArray 預先配置 capacity】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
```c
#include <std_msgs/msg/int32_multi_array.h>
#define MAX_LEN 400        // 含 data[0] 的 job_id；保守取 ≤ 450
std_msgs__msg__Int32MultiArray msg_in, msg_out;
static int32_t in_buf[MAX_LEN], out_buf[MAX_LEN];   // 靜態 buffer

static void alloc_msgs(void) {
    msg_in.data.data = in_buf;   msg_in.data.capacity = MAX_LEN;  msg_in.data.size = 0;
    msg_out.data.data = out_buf; msg_out.data.capacity = MAX_LEN; msg_out.data.size = 0;
    msg_in.layout.dim.data = NULL;  msg_in.layout.dim.capacity = 0;  msg_in.layout.dim.size = 0;
    msg_out.layout.dim.data = NULL; msg_out.layout.dim.capacity = 0; msg_out.layout.dim.size = 0;
    msg_in.layout.data_offset = 0;  msg_out.layout.data_offset = 0;
}
```
要換：`MAX_LEN` = 一則最多幾個 int32（含 job_id）。
- `main` 裡在建 executor **之前**呼叫 `alloc_msgs();`。
- 收到元素數 > `capacity` → callback 仍被叫，但 `data.size = 0`。
- dim capacity = 0 → 電腦端填了 `layout.dim` 整則會被丟掉。
✗ 錯：buffer 放 stack（主 stack 只有 2 KB）。
前提：CMake `target_link_libraries(app pico_stdlib microros)`、`target_include_directories(app PUBLIC libmicroros/include)`。
驗證：`pico_array_compute.c` 原樣 `make` 0 錯 0 警告；沒在板子上跑。

---

【片段卡｜HOST-UROS 2/4｜Pico 端：callback 收 → compute → 發】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
```c
// 你的運算：輸入 in[0..n-1]，輸出寫到 out，回傳輸出長度（≤ cap）
static size_t compute(const int32_t *in, size_t n, int32_t *out, size_t cap);

void sub_cb(const void *msgin) {
    const std_msgs__msg__Int32MultiArray *m = (const std_msgs__msg__Int32MultiArray *)msgin;
    if (m->data.size < 1) return;                       // 至少要有 job_id（太長也會變 0）
    int32_t job_id = m->data.data[0];
    size_t n = m->data.size - 1;
    size_t out_n = compute(&m->data.data[1], n, &out_buf[1], MAX_LEN - 1);
    // capacity 檢查：size 絕對不能 > capacity，不然序列化會越界
    if (out_n + 1 > msg_out.data.capacity) out_n = msg_out.data.capacity - 1;
    out_buf[0] = job_id;
    msg_out.data.size = out_n + 1;
    RCSOFTCHECK(rcl_publish(&pub, &msg_out, NULL));
}
```
要換：`compute` 的內容（範本是插入排序；可換 sort / CRC / SHA / NN）。
- 協定：`data[0]` = job_id，`data[1..]` = 資料；回傳格式一樣。
- `RCSOFTCHECK(fn)` = 錯誤也不停；`RCCHECK(fn)` = 錯誤進 LED 快閃迴圈。
- reliable 發佈會等 agent ACK 才回來。
✗ 錯：`msg_out.data.size` > `capacity` → 越界。✗ 錯：在 callback 裡 `printf` → 會混進 micro-ROS 的序列埠資料。
前提：HOST-UROS 1/4 的 `alloc_msgs`；`pub` 是 `rcl_publisher_t`。
驗證：同 `pico_array_compute.c` 編譯通過；沒在板子上跑。

---

【片段卡｜HOST-UROS 3/4｜Pico 端：建 node、sub/pub、executor】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
```c
#define BOARD_NS "<pico0>"
allocator = rcl_get_default_allocator();
RCCHECK(rclc_support_init(&support, 0, NULL, &allocator));
RCCHECK(rclc_node_init_default(&node, "compute_node", BOARD_NS, &support));
const rosidl_message_type_support_t *ts =
    ROSIDL_GET_MSG_TYPE_SUPPORT(std_msgs, msg, Int32MultiArray);
RCCHECK(rclc_subscription_init_default(&sub, &node, ts, "input"));
RCCHECK(rclc_publisher_init_default(&pub, &node, ts, "output"));
executor = rclc_executor_get_zero_initialized_executor();
RCCHECK(rclc_executor_init(&executor, &support.context, 1, &allocator));
RCCHECK(rclc_executor_add_subscription(&executor, &sub, &msg_in, &sub_cb, ON_NEW_DATA));
while (true) {
    rclc_executor_spin_some(&executor, RCL_MS_TO_NS(1));
}
```
要換：`<pico0>` = 每塊板子不同（`pico0`、`pico1`…）。
- `"input"` + namespace `pico0` → `/pico0/input`、`/pico0/output`。
- `rclc_executor_init` 第 3 參數 = handle 數（1 個 sub = 1）。
- 一則上限：reliable ≈ 505 個 int32。
前提：`#include <rclc/rclc.h>`、`<rclc/executor.h>`；先做 `rmw_uros_set_custom_transport`、`alloc_msgs()`、`rmw_uros_ping_agent`。
驗證：同範本編譯通過、簽名對過 jazzy `rclc/*.h`；沒在板子上跑。

---

【片段卡｜HOST-UROS 4/4｜電腦端：帶 job_id 送 N 塊板子、照順序合併】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
```python
import heapq
from rclpy.qos import QoSProfile, ReliabilityPolicy
from std_msgs.msg import Int32MultiArray

qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE)
for i in range(N_BOARDS):          # 在 __init__ 裡
    self.pubs.append(self.create_publisher(Int32MultiArray, f'/pico{i}/input', qos))
    self.create_subscription(Int32MultiArray, f'/pico{i}/output',
        lambda msg, b=i: self.on_result(b, msg), qos)

def send(self, board, job_id, chunk):
    msg = Int32MultiArray()           # 不要填 layout.dim
    msg.data = [job_id] + chunk
    self.pubs[board].publish(msg)

def on_result(self, board, msg):
    job_id = msg.data[0]
    self.results[job_id] = list(msg.data[1:])

chunks = [data[i:i + CHUNK] for i in range(0, len(data), CHUNK)]
parts = [self.results[k] for k in sorted(self.results)]
out = list(heapq.merge(*parts))   # 排序；逐元素運算改串接
```
要換：`N_BOARDS` = 板子數；`CHUNK` = 每塊個數（+1 ≤ 板子 `MAX_LEN`=400）。
✗ 錯：`lambda msg: self.on_result(i, msg)` → 全部變最後一個 i → ✓ 對：`b=i`。
前提：每塊板子各一個 agent。從 `host_driver.py` 節錄，沒實跑 rclpy（切塊 / 合併用純 Python 驗過）。
驗證：`host_driver.py` 印 `correct=True`。

---

【片段卡｜ALGO 1/6｜CRC-32 分段算、三種實作、照規格的 crc_generic】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
```c
#include "crc32.h"
crc32_init();                              // 開機一次（不呼叫也會自動建表）
uint32_t c = crc32_update(0, <buf1>, <n1>);    // 第一段傳 0
c = crc32_update(c, <buf2>, <n2>);             // 續算：= 整段一次算
uint32_t t = crc32_table(0, <buf>, <n>);       // 1 KB 表
uint32_t s = crc32_slice4(0, <buf>, <n>);      // 4 KB 表，最快
crc_param_t spec = {16, 0x8005, 0xFFFF, 1, 1, 0x0000};  // CRC-16/MODBUS
uint32_t r = crc_generic(&spec, <buf>, <n>);
```
要換：`<buf*>` = `const uint8_t *`；`<n*>` = bytes 數；`spec` = 題目給的參數。
`crc_param_t` 欄位順序：`{width, poly, init, refin, refout, xorout}`（poly 用一般寫法，非反轉）。
| 名稱 | width | poly | init | refin/refout | xorout | "123456789" |
|---|---|---|---|---|---|---|
| CRC-32 zlib | 32 | 0x04C11DB7 | 0xFFFFFFFF | 1/1 | 0xFFFFFFFF | 0xCBF43926 |
| CRC-16/MODBUS | 16 | 0x8005 | 0xFFFF | 1/1 | 0x0000 | 0x4B37 |
| CRC-8 SMBus | 8 | 0x07 | 0x00 | 0/0 | 0x00 | 0xF4 |
✗ 錯：第一段傳 `0xFFFFFFFF` → 錯；`crc32_update` 第一段傳 `0`（跟 `zlib.crc32` 一樣）。
前提：`#include "crc32.h"`，一起編 `crc32.c`。
驗證：`crc32_update(0, "123456789", 9) == 0xCBF43926`，三種實作相同；表中各組 check 全對；其他參數見 `crc32.h`（實跑通過）。

---

【片段卡｜ALGO 2/6｜排序：radix_sort_u32、合併兩塊 / k 塊、有號】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
```c
#include "sort.h"
static uint32_t a[N], tmp[N];              // MCU 上用 static
radix_sort_u32(a, N, tmp);                 // tmp 至少 N 個

merge_two_sorted(<A>, <nA>, <B>, <nB>, out);   // out 至少 nA+nB 個，不可跟 A/B 重疊

const uint32_t *lists[] = {<A>, <B>, <C>};
const size_t lens[] = {<nA>, <nB>, <nC>};
kway_merge(lists, lens, 3, out);           // 3 = k

// 有號 int32：翻符號位 → 排 → 翻回來
uint32_t *u = (uint32_t *)s;
for (size_t i = 0; i < N; i++) u[i] ^= 0x80000000u;
radix_sort_u32(u, N, tmp);
for (size_t i = 0; i < N; i++) u[i] ^= 0x80000000u;
```
要換：`N` = 個數；`<A>`、`<B>`、`<C>` = 已排序的 `uint32_t` 陣列；`<nA>`… = 各自長度；`s` = 你的 `int32_t` 陣列。
| 情況 | 用 |
|---|---|
| n < ~32 | `insertion_sort_u32(a, n)` |
| 要穩定排序 | `merge_sort_u32(a, n, tmp)` |
| 大量 u32 | `radix_sort_u32(a, n, tmp)` |
| 兩塊板子 / 兩核各排一半 | `merge_two_sorted` |
| k 塊 | `kway_merge`（O(n·k)，k ≤ 8 划算） |
- 遞減：排完反轉陣列。
✗ 錯：有號直接 `radix_sort_u32` → 負數排到最後。
前提：`#include "sort.h"`，一起編 `sort.c`。
驗證：1000 個隨機數對 `qsort` 結果完全相同；k-way 輸出遞增；有號版對 `qsort` 相同（實跑通過）。

---

【片段卡｜ALGO 3/6｜SHA-0 / SHA-1 / SHA-256 串流 init / update / final】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
```c
#include "sha1_sha0.h"
#include "sha256.h"
sha1_ctx c;  sha1_init(&c, 0);             // 0 = SHA-1，1 = SHA-0
sha1_update(&c, <pkt1>, <n1>);             // 資料分幾包就呼叫幾次
sha1_update(&c, <pkt2>, <n2>);
uint8_t out1[20]; sha1_final(&c, out1);    // 20 bytes，大端，直接印 hex
sha256_ctx d; sha256_init(&d);             // SHA-256 沒有第二個參數
sha256_update(&d, <pkt1>, <n1>);
sha256_update(&d, <pkt2>, <n2>);
uint8_t out2[32]; sha256_final(&d, out2);
for (int i = 0; i < 20; i++) printf("%02x", out1[i]);
printf("\n");
```
要換：`<pkt*>` = `const uint8_t *`；`<n*>` = bytes 數。
- 一次算完：`sha1(p, n, out)`、`sha0(p, n, out)`、`sha256(p, n, out)`。
- SHA-0 和 SHA-1 唯一差別：SHA-1 訊息擴展 `W[t]` 多左旋 1 位。
| 輸入 "abc" | 結果 |
|---|---|
| SHA-1 | `a9993e364706816aba3e25717850c26c9cd0d89d` |
| SHA-0 | `0164b8a914cd2a5e74c4f7ff082c4d97f1edf880` |
| SHA-256 | `ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad` |
✗ 錯：`sha1_init(&c, 1)` 以為是 SHA-1 → 那是 SHA-0。
✗ 錯：final 後繼續 update → 要重新 init。
前提：`#include "sha1_sha0.h"`、`"sha256.h"`，一起編 `sha1_sha0.c`、`sha256.c`。
驗證："a" + "bc" 分兩包 → 上表三個值都對（實跑通過）。

---

【片段卡｜ALGO 4/6｜BNN：±1 打包成 bits、XNOR-popcount 內積】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
```c
#include "bnn.h"
uint32_t xb[BNN_WORDS(N)], wb[BNN_WORDS(N)];   // N=70 → 3 個 word
bnn_pack(x, N, xb);                          // v>0 → 1，否則 0（0 也當 -1）
bnn_pack(wv, N, wb);
int32_t d = bnn_dot(xb, wb, N);              // = Σ x[i]*w[i]，範圍 -N..N
int bit = d >= 0;                            // sign（門檻 0）
```
要換：`N` = 元素數；`x`、`wv` = `int8_t` 陣列（值 +1 / -1）。
- 公式：`dot = 2 * popcount(~(a ^ w)) - n`（相同的個數 − 不同的個數）。
- 位元排列：第 i 個 → `word[i / 32]` 的 `bit (i % 32)`（LSB 起算）。
- 最後一個 word 只有 `n % 32` 個有效 bit → 一定要 mask（`bnn_dot` 已做）。
- 一整層：`bnn_layer_t L = {n_in, n_out, W, thr, flip};` → `bnn_dense_sign(&L, in, out_bits)`；最後一層 `bnn_dense_score(&L, in, score)` → `bnn_argmax(score, n_out)`。
✗ 錯：自己寫 popcount 沒 mask 尾巴 → 多算 `32 - n % 32` 個「相同」（實測 N=70 答案錯）。
✗ 錯：0/1 像素直接當 ±1 以外的值乘 → `bnn_pack` 把 0 當 -1。
前提：`#include "bnn.h"`，一起編 `bnn.c`。
驗證：N=70 時 `bnn_dot == Σ x[i]*w[i]`（-14 = -14，實跑通過）。

---

【片段卡｜ALGO 5/6｜照規格位元表取欄位：GET_FIELD / SET_FIELD / sign_extend】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
```c
#include "bitops.h"
// 規格表：bit 31..28 VER、27..16 LEN、15..0 OFS（有號 16 bit）
#define VER_HI 31
#define VER_LO 28
#define LEN_HI 27
#define LEN_LO 16
#define OFS_HI 15
#define OFS_LO 0
uint32_t ver = GET_FIELD(x, VER_HI, VER_LO);            // 無號欄位
uint32_t len = GET_FIELD(x, LEN_HI, LEN_LO);
int32_t  ofs = sign_extend(GET_FIELD(x, OFS_HI, OFS_LO),
                           OFS_HI - OFS_LO + 1);        // 有號欄位：寬度 = hi-lo+1
x = SET_FIELD(x, LEN_HI, LEN_LO, 0x123);                // 只改 LEN，其他不動
```
要換：`VER/LEN/OFS` 的名字與 `HI`、`LO` = 題目表格的 bit 範圍；`x` = `uint32_t`。
- 參數順序：`GET_FIELD(x, hi, lo)`、`SET_FIELD(x, hi, lo, v)` → **hi 在前**；含 hi 與 lo。
- `SET_FIELD` 回傳新值（不會改 x）→ 要 `x = SET_FIELD(...)`；v 超寬會被 mask。
- `sign_extend(v, bits)`：`sign_extend(0xFFF, 12) = -1`、`(0x800, 12) = -2048`。
- `MASK(32)` 已特別處理（`1u << 32` 是未定義行為）。
✗ 錯：`GET_FIELD(x, lo, hi)` 順序顛倒 → 結果錯。✗ 錯：有號欄位只 `GET_FIELD` → 負數變大正數。
前提：`#include "bitops.h"`（`預製程式碼/bits-riscv/`，只有標頭）。
驗證：`x = 0xABCD1234` → `ver = 0xA`、`len = 0xBCD`、`ofs = 4660`，SET 後 `x = 0xA1231234`（實跑通過）。

---

【片段卡｜ALGO 6/6｜位元流 MSB-first 讀固定寬度欄位】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
```c
typedef struct {
    uint8_t *buf;   // 資料
    size_t   pos;   // 目前在第幾個「位元」（不是 byte！）
} BitStream;

uint32_t read_msb(BitStream *s, int n) {
    uint32_t v = 0;
    for (int i = 0; i < n; i++) {
        size_t byte = s->pos >> 3;          // pos / 8 = 第幾個 byte
        int    bit  = 7 - (s->pos & 7);     // 該 byte 內從 bit7 往下用
        v = (v << 1) | ((s->buf[byte] >> bit) & 1u);   // 新位元接在最右邊
        s->pos++;
    }
    return v;
}
```
用法：
```c
uint8_t d[] = {0xA5, 0x3C};      // 1010 0101 0011 1100
BitStream r = {d, 0};
uint32_t a = read_msb(&r, 3);    // 101      = 0x5
uint32_t b = read_msb(&r, 7);    // 0010100  = 0x14（跨 byte）
uint32_t c = read_msb(&r, 6);    // 111100   = 0x3C
```
要換：`d` = 你的 bytes；`3/7/6` = 題目每個欄位的寬度（1～32）。
- MSB-first（多數網路協定、影像格式）：每個 byte 先用 bit7。LSB-first（deflate、很多 UART/FIFO）要改用 `bitstream.c` 的 `read_lsb`。
- 寫入：`write_msb(&w, v, n)`，buf 要先清 0。
✗ 錯：`pos` 當成 byte 數 → 位移錯。✗ 錯：讀超過 `buf` 尾巴 → 越界（自己檢查 `pos + n <= 8 * len`）。
前提：`#include <stdint.h>`、`<stddef.h>`；從 `bitstream.c` 複製（它有 `main`，不能整檔一起編）。
驗證：上面用法得到 `0x5`、`0x14`、`0x3C`，`r.pos == 16`；`DE AD BE EF` 讀 32 位 = `0xDEADBEEF`（實跑通過）。

---

【片段卡｜PERF 1/4｜pthread 切塊：各自區域累加、最後合併一次】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
```c
#define T_MAX 64
typedef struct { int id; size_t lo, hi; } job_t;   // 每條負責 [lo, hi)
static uint64_t part[T_MAX];                        // 各自的結果

static void *w_local(void *arg) {
    job_t *j = arg; uint64_t s = 0;                 // 區域變數累加，迴圈內沒有鎖
    for (size_t i = j->lo; i < j->hi; i++) s += work(data[i]);
    part[j->id] = s;                                // 只寫一次共享記憶體
    return NULL;
}
static void run(void *(*fn)(void *)) {
    pthread_t th[T_MAX]; job_t job[T_MAX];
    for (int t = 0; t < T; t++) {
        job[t] = (job_t){ t, (size_t)N * t / T, (size_t)N * (t + 1) / T };
        pthread_create(&th[t], NULL, fn, &job[t]);
    }
    for (int t = 0; t < T; t++) pthread_join(th[t], NULL);
}
// 使用：
run(w_local);
uint64_t sum = 0;
for (int t = 0; t < T; t++) sum += part[t];     // 合併：主執行緒做一次
```
要換：`data`、`N` = 你的資料與個數；`T` = 執行緒數（≤ `T_MAX`）；`work(x)` = 每個元素的運算。
- 排序題：每條排自己那段，最後 `kway_merge`（ALGO 2/6）。
✗ 錯：每個元素都 `pthread_mutex_lock` → 比單執行緒還慢。✗ 錯：不加鎖直接 `g_sum +=` → lost update、答案錯。
前提：`#include <pthread.h>`、`<stdint.h>`；編譯加 `-pthread`。
驗證：2^22 個元素，T = 3、4、8 的 `sum` 都等於單執行緒；ASan/UBSan、TSan 無錯（實跑通過）。

---

【片段卡｜PERF 2/4｜SPSC 環形佇列：struct + push（producer 端）】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
```c
#define CAP 1024u                       // 必須是 2 的次方
static struct {
    item_t buf[CAP];
    _Alignas(64) _Atomic size_t head;   // 分開放兩條 cache line，避免 false sharing
    _Alignas(64) _Atomic size_t tail;
} q;

static bool spsc_push(item_t v) {                     /* 只能由 producer 呼叫 */
    size_t h = atomic_load_explicit(&q.head, memory_order_relaxed);
    size_t t = atomic_load_explicit(&q.tail, memory_order_acquire);
    if (h - t == CAP) return false;                   /* 滿 */
    q.buf[h & (CAP - 1)] = v;
    atomic_store_explicit(&q.head, h + 1, memory_order_release);
    return true;
}
```
使用（producer 執行緒）：`while (!spsc_push(v)) sched_yield();   // 滿：讓出 CPU 再試`
要換：`item_t` = 你的型別（`typedef uint32_t item_t;` 或封包 struct）；`CAP` = 2 的次方。
- 只有一個 producer、一個 consumer → 不用鎖：`head` 只有 producer 寫、`tail` 只有 consumer 寫。
- 先寫 `buf`，再 release 存 `head`。pop 見 PERF 3/4。
✗ 錯：兩個 producer 同時 push → 壞掉；多寫多讀用 mutex + condvar（`pipeline_template.c` A 版）。
前提：`#include <stdatomic.h>`、`<stdbool.h>`、`<stddef.h>`、`<sched.h>`；`-std=c11 -pthread`。
驗證：配 PERF 3/4 跑 100 萬筆，加總正確；TSan 無錯（實跑通過）。

---

【片段卡｜PERF 3/4｜SPSC：pop（consumer 端）+ 開兩條執行緒】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
```c
static bool spsc_pop(item_t *v) {                     /* 只能由 consumer 呼叫 */
    size_t t = atomic_load_explicit(&q.tail, memory_order_relaxed);
    size_t h = atomic_load_explicit(&q.head, memory_order_acquire);
    if (h == t) return false;                         /* 空 */
    *v = q.buf[t & (CAP - 1)];
    atomic_store_explicit(&q.tail, t + 1, memory_order_release);
    return true;
}
static void *consumer(void *arg) {
    (void)arg; uint64_t s = 0; item_t v;
    for (uint32_t got = 0; got < <N_ITEMS>; got++) {
        while (!spsc_pop(&v)) sched_yield();     // 空：讓出 CPU 再試
        s += v;
    }
    consumer_sum = s;
    return NULL;
}
// main：
pthread_t p, c;
pthread_create(&c, NULL, consumer, NULL);
pthread_create(&p, NULL, producer, NULL);
pthread_join(p, NULL); pthread_join(c, NULL);
```
要換：`<N_ITEMS>` = 總筆數；`s += v` = 你的計算；`producer` = 你的函式（迴圈呼叫 `spsc_push`）；`consumer_sum` = `static uint64_t`。
- 更快：批次版 `spsc_push_n` / `spsc_pop_n`（`pipeline_template.c` C 版）。
✗ 錯：空轉不 `sched_yield()` → 搶 CPU。
前提：PERF 2/4 的 `q`、`CAP`；`#include <pthread.h>`；`-pthread`。
驗證：100 萬筆 `consumer_sum` = 直接加總；TSan 無錯（實跑通過）。
---

【片段卡｜PERF 4/4｜計時：BENCH 取最快、now_ns 單次】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
```c
#include "bench.h"                 // ★ 一定放第一個 include
BENCH("f 原版", 5, { r = f(a, N); do_not_optimize(r); });   // 跑 5 次印最快
double base = bench_last_ns / 1e6;                           // ms
BENCH("f 新版", 5, { r = f(a, N); do_not_optimize(r); });
printf("加速 %.2fx\n", base / (bench_last_ns / 1e6));
uint64_t t0 = now_ns();                                      // 單次量測
r = f(a, N);
printf("%.3f ms (r=%llu)\n", (now_ns() - t0) / 1e6, (unsigned long long)r);
```
要換：`f(a, N)` = 你要量的呼叫；`r` = 接結果的變數（`uint64_t` 之類）；`5` = 重複次數。
- `BENCH(name, reps, code)`：跑 reps 次取最小值，印 `  名稱  x.xxx ms`，存在 `bench_last_ns`。
- `do_not_optimize(x)`：不用它，`-O2` 會把沒用到的結果整段刪掉 → 量出 0 ms。
- 寫陣列的程式：`BENCH` 每次已呼叫 `clobber_memory()`。
- `now_ns()` = `CLOCK_MONOTONIC`，單位奈秒。
✗ 錯：`bench.h` 不是第一個 include → 沒有 `clock_gettime`（`_POSIX_C_SOURCE` 太晚定義）。
✗ 錯：用 `-O0` 量 → 數字沒意義；用 `-O2`。
- 只用 `now_ns()`、沒用 `BENCH` → `-Wall` 會警告 `bench_last_ns defined but not used`（無害）。
前提：`#include "bench.h"`（`預製程式碼/linux-perf/`）；`gcc -O2 -Wall -Wextra -std=c11`。
驗證：印出兩行 `f 原版 / f 新版  x.xxx ms` 與 `加速 1.0x`（同一個函式），實跑通過。
