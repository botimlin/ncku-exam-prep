# 自訂訊息 (.msg) 與陣列訊息小抄

## 1. 先問自己：真的需要自訂嗎？
傳一串數字 / bytes → **直接用內建的，不用自訂**：

| 資料 | 用這個 | Python 裡 `msg.data` 是 |
|---|---|---|
| 一串 bytes (封包、影像片段) | `std_msgs/msg/UInt8MultiArray` | `array.array('B')` ← 最快 |
| 一串 int32 | `std_msgs/msg/Int32MultiArray` | `array.array('i')` |
| 一串 uint32 / float | `UInt32MultiArray` / `Float32MultiArray` | `array('I')` / `array('f')` |
| 一個數字 | `std_msgs/msg/Int32`、`UInt32`、`Float64` | int / float |
| 文字 | `std_msgs/msg/String` | str |
| 影像 | `sensor_msgs/msg/Image` (`data` 是 uint8[]) | `array('B')` |

- **不要用 `ByteMultiArray`**：它的 `data` 是 `byte[]`，Python 裡變成「一個一個 bytes 物件的 list」，很慢。用 `UInt8MultiArray`。
- `ros2 interface show` 會說 MultiArray「deprecated」— 只是建議，Jazzy 照樣能用，考試直接用。
- `layout` 欄位可以不填 (留空就好)。

## 2. 陣列打包 / 解包 (快 vs 慢)
```python
import array, struct
from std_msgs.msg import UInt8MultiArray, Int32MultiArray

# bytes -> UInt8MultiArray (快：直接給 bytes)
m = UInt8MultiArray(); m.data = payload_bytes          # 也可以 array.array('B', payload_bytes)
raw = bytes(m.data)                                     # 收到後轉回 bytes

# int list -> Int32MultiArray
m = Int32MultiArray(); m.data = [1, 2, 3]               # 或 array.array('i', 大量資料) 更快
raw = array.array('i', m.data).tobytes()                # int32 -> 小端 bytes，直接丟給 Pico (x86/ARM 都是小端)
vals = array.array('i'); vals.frombytes(raw)            # bytes -> int32 陣列

# 慢的寫法 (不要): m.data = [int(x) for x in text.split()] 一個一個轉、或 for 迴圈 append
# 有 numpy 時: m.data = np_arr.astype(np.int32).tolist() 比較穩；np_arr.astype('<i4').tobytes() 拿 bytes
# struct 寫法: struct.pack(f'<{n}I', *vals)  /  struct.unpack(f'<{n}I', raw)
```
- 從 CLI 發：`ros2 topic pub --once /bytes std_msgs/msg/UInt8MultiArray "{data: [1, 2, 255]}"`

## 3. 真的要自訂：建一個 interface 套件
**.msg 只能放在 ament_cmake 套件** (Python 套件不能產生訊息)。另外開一個套件專門放訊息。
```bash
cd ~/ws/src
ros2 pkg create --build-type ament_cmake my_interfaces     # TODO(改這裡) 套件名
mkdir -p my_interfaces/msg
```
`my_interfaces/msg/Job.msg` (檔名**大寫開頭 CamelCase**，欄位**小寫底線**)：
```
uint8 cmd
uint32 seq
uint8[] payload       # 不定長度陣列
int32[4] fixed        # 固定長度 4
string note
```
`CMakeLists.txt` — 在 `find_package(ament_cmake REQUIRED)` 後面、`ament_package()` 前面加：
```cmake
find_package(rosidl_default_generators REQUIRED)
rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/Job.msg"
  # DEPENDENCIES std_msgs      # 如果 .msg 裡用到 std_msgs/Header 之類才要
)
ament_export_dependencies(rosidl_default_runtime)
```
`package.xml` — 在 `<buildtool_depend>ament_cmake</buildtool_depend>` 下面加：
```xml
<buildtool_depend>rosidl_default_generators</buildtool_depend>
<exec_depend>rosidl_default_runtime</exec_depend>
<member_of_group>rosidl_interface_packages</member_of_group>
```
編譯 + 檢查：
```bash
cd ~/ws && colcon build --packages-select my_interfaces && source install/setup.bash
ros2 interface show my_interfaces/msg/Job
```
在 Python 用 (使用的套件 package.xml 要加 `<exec_depend>my_interfaces</exec_depend>`)：
```python
from my_interfaces.msg import Job
j = Job(cmd=2, seq=1, payload=b'\x01\x02', fixed=[1, 2, 3, 4], note='hi')
```

## 常見錯誤
- `ModuleNotFoundError: my_interfaces` → 沒 `source install/setup.bash`，或在 build 之前開的終端機。
- `rosidl_generate_interfaces` 出錯 → 檔名小寫開頭、或欄位名有大寫。
- 固定長度陣列 (`int32[4]`) 在 Python 裡是 numpy array，**給錯長度時設定當下不會報錯** (實測 Jazzy)，要自己確保長度剛好，不然 publish 時才會出事。
- 改了 .msg → 用到它的所有 node 都要重開。
