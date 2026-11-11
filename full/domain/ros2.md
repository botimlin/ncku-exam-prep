# ROS 2 Jazzy 速查與除錯手冊（完整版）

> 用途：考場上觀察、除錯、優化 ROS 2 系統（node / topic / QoS / executor），以及撰寫最小的 rclpy / rclcpp 程式。可整份貼給考場 LLM 當參考資料。
> 適用版本：ROS 2 Jazzy Jalisco（Ubuntu 24.04 Noble、Python 3.12、預設 RMW `rmw_fastrtps_cpp`）。考前練習 image 為 `ros:jazzy-ros-core`。
> 來源（實際查閱）：
> - https://docs.ros.org/en/jazzy/ （網站擋爬蟲，實際讀的是同內容的原始檔 https://github.com/ros2/ros2_documentation/tree/jazzy/source ）
>   - Concepts/Intermediate/About-Quality-of-Service-Settings、About-Executors、About-Domain-ID
>   - How-To-Guides/Using-callback-groups
>   - Tutorials/Beginner-CLI-Tools（Configuring-ROS2-Environment、Understanding-ROS2-Nodes / Topics / Services / Parameters / Actions）
>   - Tutorials/Beginner-Client-Libraries（Writing-A-Simple-Py / Cpp-Publisher-And-Subscriber）
>   - Tutorials/Intermediate/Launch/Creating-Launch-Files、Tutorials/Demos/Intra-Process-Communication、Tutorials/Advanced/Improved-Dynamic-Discovery
>   - Releases/Release-Jazzy-Jalisco、Release-Iron-Irwini
> - ros2cli 原始碼（jazzy 分支）：https://github.com/ros2/ros2cli/tree/jazzy （ros2topic / ros2service / ros2action / ros2param / ros2interface / ros2doctor / daemon）
> - rclpy 原始碼（jazzy）：https://github.com/ros2/rclpy/tree/jazzy （`__init__.py`、`node.py`、`qos.py`、`executors.py`、`event_handler.py`）
> - rclcpp 原始碼（jazzy）：https://github.com/ros2/rclcpp/tree/jazzy （`qos.hpp`、`multi_threaded_executor.hpp`、`publisher_base.cpp`、`experimental/executors/events_executor`）
> - rmw QoS 預設值：https://github.com/ros2/rmw/blob/jazzy/rmw/include/rmw/qos_profiles.h
> - ros2launch：https://github.com/ros2/launch_ros/tree/jazzy/ros2launch
> - REP 2001（variant 內容）：https://github.com/ros-infrastructure/rep/blob/master/rep-2001.rst
> - micro-ROS Pico：https://github.com/micro-ROS/micro_ros_raspberrypi_pico_sdk
> 最後更新：2026-11
>
> 標記：`⚠️未驗證` = 沒有在官方來源逐字確認，使用前先在環境裡實測。

---

## 0. 考前練習（section2-1）給的線索

- 環境：Docker `ros:jazzy-ros-core` + `gcc libc6-dev make`。Dockerfile 只把 `source /opt/ros/jazzy/setup.bash` 寫進 `/root/.bashrc`，因為 base image 的 entrypoint 只幫「第一個 shell」source，`docker exec` 進來的 shell 靠 `.bashrc`。
- `ros_core` variant（REP 2001）含：`rclpy`、`rclcpp`、`rclcpp_action`、`launch`、`launch_ros`、`ros2cli_common_extensions`（內含 `ros2topic/ros2node/ros2service/ros2param/ros2action/ros2interface/ros2doctor/ros2launch/ros2run/ros2pkg/ros2component/ros2lifecycle/ros2multicast` 等）、`common_interfaces`（`std_msgs`、`std_srvs`、`geometry_msgs`、`sensor_msgs`…）、`ament_cmake`、`rosidl_default_generators`。
  - **不含** `colcon`、`demo_nodes_*`、`turtlesim`、`rosbag2`（rosbag2 在 `ros_base`）。
  - Dockerfile 只裝 `gcc`，⚠️未驗證 image 內是否有 `g++`；要編 rclcpp 前先 `which g++ cmake colcon`。
- 練習的程式是「直接 `python3 xxx.py` 執行的單檔 rclpy node」，不是套件，不需要 colcon。
- 練習資料流：

```text
/publisher --(/number, std_msgs/msg/Int32, depth 10)--> /processor --(/double, Int32)--> 
publisher.py: create_timer(1.0, tick) 每秒 publish random 1..100
processor.py: on_msg(received) -> print -> out.data = received.data * 2 -> publish
```

- 練習 README 的除錯階梯（官方給的）：node 是否存在 → topic 是否存在 → 兩端是否連到同一個 topic → pub/sub 數量是否合理 → 是否真的有資料。第 7 節把它擴充成完整版。
- 練習 README 的核心觀念：「topic 名稱差一個字就是另一個 topic，程式不會報錯」；「topic 存在不代表有資料在傳」；`ros2 topic echo` = 暫時的 subscriber、`ros2 topic pub` = 暫時的 publisher。

---

## 1. 核心概念

| 概念 | 說明 | 重點 |
|---|---|---|
| node | 參與 ROS 通訊的單位；一個 process 可以有多個 node | 全名 = namespace + name，例如 `/publisher`、`/ns1/sim` |
| topic | 具名、單一 message type 的非同步多對多通道 | 名稱與型別都要一致才會連上 |
| message type | `pkg/msg/Name`，例如 `std_msgs/msg/Int32`（欄位 `int32 data`）| 用 `ros2 interface show` 看欄位 |
| service | 一次 request/response，`pkg/srv/Name`；`.srv` 用 `---` 分隔 request / response | 預設 QoS = services_default（reliable、volatile、depth 10） |
| action | 長時間工作：goal → feedback（多次）→ result，可取消；`.action` 有兩個 `---`（goal / result / feedback） | 底層是數個 service + topic |
| parameter | 每個 node 自己的設定值（int/double/string/bool/陣列） | 每個 node 預設有 `use_sim_time` |
| QoS | 每個 publisher / subscription 的傳輸策略 | 不相容就**完全不傳**，且程式不會丟例外，只印 warning |
| executor | 負責等待事件並呼叫 callback 的排程器 | 沒有 spin，callback 永遠不會跑 |
| callback group | 控制哪些 callback 可以並行 | 預設是 node 的 MutuallyExclusive group |
| discovery | DDS 自動找到同 domain 的其他參與者 | `ROS_DOMAIN_ID` 不同就看不見 |
| RMW | 中介層實作，Jazzy 預設 `rmw_fastrtps_cpp`（Fast DDS） | 用 `RMW_IMPLEMENTATION` 環境變數切換 |

### 1.1 名稱解析規則

| 寫法 | node 在 namespace `/ns`、名稱 `n` 時解析為 |
|---|---|
| `/number`（前導斜線，絕對） | `/number` |
| `number`（相對） | `/ns/number` |
| `~/number`（私有） | `/ns/n/number` |

- 練習裡 node 沒有 namespace，所以 `number` 和 `/number` 結果相同；一旦用 `--ros-args -r __ns:=/robot1` 或 launch 的 `namespace=` 啟動，相對名稱會跟著變，絕對名稱不會。
- 名稱區分大小寫：`/Number` ≠ `/number`；`/number` ≠ `/number_`。

---

## 2. `ros2` CLI 完整速查

> 所有指令前提：shell 已 `source /opt/ros/jazzy/setup.bash`（若有自己的 workspace 再 `source install/setup.bash`）。
> 列表類指令（list / info）預設透過背景 **ros2 daemon** 取得快取的 graph；懷疑結果過時就加 `--no-daemon` 或 `ros2 daemon stop`。

### 2.1 node

| 指令 | 作用 / 預期輸出 |
|---|---|
| `ros2 node list` | 每行一個 node 全名，例如 `/processor`、`/publisher` |
| `ros2 node info /processor` | 分區列出 `Subscribers:`、`Publishers:`、`Service Servers:`、`Service Clients:`、`Action Servers:`、`Action Clients:`，每行 `topic: type` |
| `ros2 run <pkg> <exe> --ros-args -r __node:=new_name` | 執行時改 node 名稱 |

node info 中看到 `/parameter_events`、`/rosout` 及一堆 `~/describe_parameters` 等 service 是每個 node 預設就有的，可忽略。

### 2.2 topic（verbs：`bw delay echo find hz info list pub type`）

| 指令 | 作用 / 預期輸出 |
|---|---|
| `ros2 topic list` | 列出 topic；`-t/--show-types` 顯示 `[type]`；`-c/--count-topics` 只印數量；`--include-hidden-topics`；`-v/--verbose` |
| `ros2 topic type /number` | `std_msgs/msg/Int32` |
| `ros2 topic find std_msgs/msg/Int32` | 列出所有該型別的 topic |
| `ros2 topic info /number` | `Type: ...` / `Publisher count: N` / `Subscription count: M` |
| `ros2 topic info -v /number` | 額外列出每個端點的 node name、namespace、topic type、type hash、GID、**QoS profile**（查 QoS 不相容的關鍵指令） |
| `ros2 topic echo /number` | 持續印 `data: 82` 與 `---` 分隔 |
| `ros2 topic hz /number` | `average rate: 1.000` 與 `min: ...s max: ...s std dev: ...s window: N` |
| `ros2 topic bw /number` | 例如 `12.34 KB/s from 50 messages` 與 `Message size mean/min/max` |
| `ros2 topic delay /topic` | `average delay: ...`；**只對有 `header.stamp` 的訊息有效**（Int32 沒有 header，不能用） |
| `ros2 topic pub /number std_msgs/msg/Int32 "{data: 21}"` | 每秒發一次（預設 `-r 1.0`），持續到 Ctrl-C |

#### `ros2 topic echo` 參數（jazzy 原始碼確認）

| 參數 | 說明 |
|---|---|
| `topic_name [message_type]` | 型別可省略（自動從 graph 查） |
| `--once` | 收到第一筆就結束 |
| `--timeout SEC` | 從啟動起經過 SEC 秒就結束（是總時間，收到訊息也不會重新計時） |
| `--field data` | 只印某欄位，子欄位用 `.`，例如 `--field pose.pose.position` |
| `--filter 'm.data > 50'` | Python 運算式過濾，`m` 代表訊息 |
| `--csv` | 逗號分隔輸出（方便貼進試算表） |
| `-f/--full-length`、`-l/--truncate-length N`（預設 128） | 陣列 / 字串截斷控制 |
| `--no-arr`、`--no-str` | 不印陣列 / 字串欄位 |
| `--flow-style` | 改變集合輸出樣式 |
| `--no-lost-messages` | 不回報遺失訊息 |
| `--raw` | 印出序列化後的原始 bytes |
| `-i/--include-message-info` | 附上 message info（時間戳記等） |
| `--qos-profile / --qos-depth / --qos-history / --qos-reliability / --qos-durability / --qos-liveliness / --qos-liveliness-lease-duration-seconds` | 指定 QoS |

**echo 的 QoS 自動配對**：未指定 QoS 時，以 `sensor_data` 為基礎，再看現有 publisher：全部 RELIABLE 才用 RELIABLE，否則用 BEST_EFFORT；全部 TRANSIENT_LOCAL 才用 TRANSIENT_LOCAL，否則用 VOLATILE。所以 `echo` 幾乎總能連上已存在的 publisher。**若 echo 啟動當下沒有任何 publisher**，就直接用 `sensor_data`（BEST_EFFORT、VOLATILE、depth 5）：仍能接上之後出現的任何 publisher，但拿不到 TRANSIENT_LOCAL 的舊訊息、高負載時可能掉包。需要時先開 publisher 再開 echo，或明確加 `--qos-reliability reliable --qos-durability transient_local`。

#### `ros2 topic hz / bw / delay` 參數

| 指令 | 參數 |
|---|---|
| `hz` | `-w/--window N`（預設 10000）、`--filter EXPR`、`--wall-time`（用牆鐘而非 ROS clock）；只接受一個 topic；訂閱用 `qos_profile_sensor_data`（best effort） |
| `bw` | `-w/--window N`（預設 100）；訂閱用 sensor_data、raw 模式 |
| `delay` | `-w/--window N`（預設 10000）；需 `header.stamp` |

`hz/bw/delay` 本身是 Python node，在極高頻率（數千 Hz 以上）時量測本身可能跟不上（⚠️未驗證臨界值），要精準量測請在自己程式裡計時。

#### `ros2 topic pub` 參數（jazzy 原始碼確認）

| 參數 | 預設 | 說明 |
|---|---|---|
| `values`（位置參數） | `'{}'` | YAML，例如 `"{data: 21}"`；冒號後要有空格 |
| `-r/--rate HZ` | 1.0 | 發布頻率 |
| `-1/--once` | — | 發一筆就結束 |
| `-t/--times N` | 0（無限） | 發 N 筆後結束 |
| `-w/--wait-matching-subscriptions N` | 用 `--once/--times` 時為 **1**，否則 0 | 等到有 N 個**相容**的 subscription 才開始發 |
| `--max-wait-time-secs SEC` | 無 | 搭配上面那個的最長等待 |
| `--keep-alive SEC` | 0.1 | 最後一筆發完後 node 再存活多久 |
| `-p/--print N` | 1 | 每 N 筆印一次 |
| `-n/--node-name NAME` | 自動 | 臨時 publisher node 名稱 |
| `--stdin` | — | 從標準輸入讀 values |
| `--qos-*` | profile `default`（reliable、volatile、keep_last 10） | 同 echo 的 QoS 參數 |

- 預期輸出：`publisher: beginning loop` 然後 `publishing #1: std_msgs.msg.Int32(data=21)`。
- **陷阱**：`--once` 預設會等到 1 個相容 subscription 才發。如果沒有 subscriber（或 QoS 不相容），它會一直卡在等待，看起來像當掉。要強制發就 `-w 0`，或加 `--max-wait-time-secs 3`。
- 有 `std_msgs/msg/Header` 的訊息可寫 `"{header: auto}"`（自動填現在時間、空 frame_id）；`builtin_interfaces/msg/Time` 欄位可寫 `now`。
- 巢狀訊息範例：`ros2 topic pub /cmd geometry_msgs/msg/Twist "{linear: {x: 2.0}, angular: {z: 1.8}}"`。
- 不知道欄位怎麼寫：`ros2 interface proto std_msgs/msg/Int32` 會印出 YAML 範本。

### 2.3 interface

| 指令 | 作用 |
|---|---|
| `ros2 interface show std_msgs/msg/Int32` | `int32 data`；`--all-comments` / `--no-comments` |
| `ros2 topic type /number \| ros2 interface show -` | 用 `-` 從 stdin 讀型別 |
| `ros2 interface proto <type>` | 印出可直接給 `pub` 用的 YAML 範本 |
| `ros2 interface list` | 全部介面；`-m` 只 msg、`-s` 只 srv、`-a` 只 action |
| `ros2 interface package std_msgs` / `ros2 interface packages` | 某套件的介面 / 所有有介面的套件 |

### 2.4 service（verbs：`call echo find info list type`）

| 指令 | 作用 / 預期輸出 |
|---|---|
| `ros2 service list [-t]` | 列出 service（加型別） |
| `ros2 service type /srv` | 型別 |
| `ros2 service info /srv` | `Type:`、`Clients count:`、`Services count:` |
| `ros2 service find std_srvs/srv/Trigger` | 找該型別的 service |
| `ros2 service call /srv std_srvs/srv/Trigger` | **型別必填**；values 預設 `'{}'`；`-r/--rate HZ` 重複呼叫；server 不在時印 `waiting for service to become available...` |
| `ros2 service call /set std_srvs/srv/SetBool "{data: true}"` | 帶參數的呼叫 |
| `ros2 service echo /srv` | 印出 REQUEST_SENT / REQUEST_RECEIVED / RESPONSE_SENT / RESPONSE_RECEIVED 事件；**需 server 或 client 有開 service introspection（`configure_introspection`）**，否則提示沒有 publisher |

### 2.5 parameter（verbs：`delete describe dump get list load set`）

| 指令 | 預期輸出 |
|---|---|
| `ros2 param list [/node]` | 依 node 分組的參數名稱 |
| `ros2 param get /node name` | 例如 `Integer value is: 86` |
| `ros2 param set /node name 150` | `Set parameter successful` |
| `ros2 param describe /node name` | 型別、描述、限制 |
| `ros2 param dump /node > p.yaml` | 輸出到 **stdout** 的 YAML：`/node:` → `ros__parameters:` → `name: value` |
| `ros2 param load /node p.yaml` | 每個參數印 `Set parameter xxx successful` |
| `ros2 run pkg exe --ros-args --params-file p.yaml` | 啟動時載入 |
| `ros2 run pkg exe --ros-args -p name:=value` | 啟動時設定單一參數 |

`set` 只是執行期修改，程序重啟就沒了。QoS override 之類的唯讀參數只能在啟動時給。

### 2.6 action（verbs：`info list send_goal type`）

| 指令 | 作用 |
|---|---|
| `ros2 action list [-t]` | 列出 action |
| `ros2 action type /act` | 型別（Jazzy 新增的 verb） |
| `ros2 action info /act` | `Action clients: N`、`Action servers: M` 及 node 名 |
| `ros2 action send_goal /act pkg/action/T "{...}" -f` | `-f/--feedback` 同時印 feedback；`-t/--timeout N` |

### 2.7 doctor / daemon / 其他

| 指令 | 作用 |
|---|---|
| `ros2 doctor` | 檢查平台、網路、RMW、套件版本、topic 狀態等；只印摘要與警告 |
| `ros2 doctor --report`（`-r`） | 印完整報告（含 `ROS_DISTRO`、RMW、網卡、topic 列表） |
| `ros2 doctor -rf` / `-iw` / `-ep` | 只印失敗項 / 把 warning 也算失敗 / 排除套件檢查 |
| `ros2 doctor hello` | 跨機器（或跨 shell）互相發 hello 測試連通性 |
| `ros2 daemon status / stop / start` | graph 快取 daemon；結果奇怪先 `stop` |
| `ros2 <cmd> --no-daemon` | 不使用 daemon，直接自行 discovery（可搭 `--spin-time 2`，預設 0.5 秒） |
| `ros2 multicast receive` / `ros2 multicast send` | 測試 multicast 是否通（DDS discovery 依賴它） |
| `ros2 pkg list` / `ros2 pkg executables <pkg>` / `ros2 pkg prefix <pkg>` | 套件資訊 |
| `ros2 component list` | 列出 component container 中載入的元件 |

ros2 doctor 常見 warning 例如某 topic「有 publisher 沒 subscriber」或反之 —— 這正好是「資料沒流動」的訊號。

### 2.8 run / launch

```bash
ros2 run <pkg> <exe> --ros-args -r __node:=my_node -r __ns:=/robot1 -r number:=/num_in -p rate_hz:=10.0 --params-file p.yaml --log-level debug
# -r __node:= 改 node 名；-r __ns:= 改 namespace；-r 舊:=新 topic remap；-p 參數；--params-file 參數檔；--log-level 日誌等級
# （注意：行尾 `\` 續行時不能在中間行加 # 註解，否則指令在那一行就斷掉）
```

```bash
ros2 launch <pkg> <file.launch.py> [arg:=value]
ros2 launch ./my.launch.py       # 也可以直接給檔案路徑
# -s/--show-args 顯示可用參數；-p/--print 只印描述不執行；-d/--debug；-a/--show-all-subprocesses-output
```

```python
# my.launch.py（Python launch file 最小樣板）
from launch import LaunchDescription
from launch_ros.actions import Node

def generate_launch_description():
    return LaunchDescription([
        Node(package='my_pkg', executable='talker', name='talker',
             namespace='robot1',
             parameters=[{'rate_hz': 10.0}],
             remappings=[('/number', '/num_in')],
             output='screen'),
    ])
```

### 2.9 環境變數

| 變數 | 說明 |
|---|---|
| `ROS_DISTRO` | 應為 `jazzy`；`printenv \| grep -i ROS` 檢查 |
| `ROS_DOMAIN_ID` | 預設 0；不同值 = 互相看不見。官方建議 0–101（Linux 上 215–232 也安全） |
| `ROS_AUTOMATIC_DISCOVERY_RANGE` | `SUBNET`（預設）/ `LOCALHOST` / `OFF` / `SYSTEM_DEFAULT` |
| `ROS_STATIC_PEERS` | 以 `;` 分隔的位址清單 |
| `ROS_LOCALHOST_ONLY` | Iron 起 deprecated，改用 `ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST` |
| `RMW_IMPLEMENTATION` | 例如 `rmw_fastrtps_cpp`（預設）、`rmw_cyclonedds_cpp`（若已安裝） |

---

## 3. QoS（Quality of Service）

### 3.1 policy 一覽

| Policy | 選項 | 意義 |
|---|---|---|
| History | `KEEP_LAST` / `KEEP_ALL` | 保留最後 N 筆 / 全部（受中介層資源限制） |
| Depth | 整數 | KEEP_LAST 時的佇列長度 |
| Reliability | `RELIABLE` / `BEST_EFFORT` | 重送保證送達 / 可能掉包但延遲低 |
| Durability | `VOLATILE` / `TRANSIENT_LOCAL` | 不保留 / publisher 保留最後 depth 筆給晚加入的 subscriber |
| Deadline | duration | 兩筆訊息間的最大間隔期望 |
| Lifespan | duration | 訊息過期時間，過期不送 |
| Liveliness | `AUTOMATIC` / `MANUAL_BY_TOPIC` | 存活判斷方式 |
| Lease Duration | duration | liveliness 的期限 |

Jazzy 另有 `BEST_AVAILABLE`（reliability / durability / liveliness 皆可設）：建立端點時依現有對方端點選「能全部連上中最嚴格」的設定。

### 3.2 預設 profile（rmw `qos_profiles.h`，jazzy）

| Profile | History | Depth | Reliability | Durability |
|---|---|---|---|---|
| default（`create_publisher(..., 10)` 就是這個） | KEEP_LAST | 10 | RELIABLE | VOLATILE |
| sensor_data | KEEP_LAST | 5 | BEST_EFFORT | VOLATILE |
| services_default | KEEP_LAST | 10 | RELIABLE | VOLATILE |
| parameters / parameter_events | KEEP_LAST | 1000 | RELIABLE | VOLATILE |
| system_default | 全部交給 RMW 預設 | | | |
| best_available | KEEP_LAST | 10 | BEST_AVAILABLE | BEST_AVAILABLE |

rclcpp 另有 `rclcpp::RosoutQoS`（depth 1000、reliable、transient local）、`rclcpp::ClockQoS`（depth 1、best effort）。

rclpy 中把整數傳給 `qos_profile`（如 `create_publisher(Int32, '/number', 10)`）= KEEP_LAST、depth=10，其餘用預設值（即 reliable、volatile）。

### 3.3 相容性表（publisher 提供 offered / subscription 要求 requested）

規則：**publisher 的品質 ≥ subscription 要求** 才相容。

| Reliability：Pub \ Sub | BEST_EFFORT | RELIABLE |
|---|---|---|
| BEST_EFFORT | 相容 | **不相容** |
| RELIABLE | 相容 | 相容 |

| Durability：Pub \ Sub | VOLATILE | TRANSIENT_LOCAL |
|---|---|---|
| VOLATILE | 相容（只收新訊息） | **不相容** |
| TRANSIENT_LOCAL | 相容（只收新訊息） | 相容（新 + 舊訊息） |

| Deadline / Lease Duration：Pub \ Sub | Sub 未設定 | Sub = y |
|---|---|---|
| Pub 未設定 | 相容 | **不相容** |
| Pub = x | 相容 | x ≤ y 相容；x > y **不相容** |

| Liveliness：Pub \ Sub | AUTOMATIC | MANUAL_BY_TOPIC |
|---|---|---|
| AUTOMATIC | 相容 | **不相容** |
| MANUAL_BY_TOPIC | 相容 | 相容 |

只要任一 policy 不相容，這一對就**完全不傳任何訊息**。History / Depth 不影響相容性。

### 3.4 不相容的症狀（「靜默失敗」）

- 兩邊程式都沒有例外，`ros2 topic info` 的 pub / sub 數量都正確（都 ≥ 1），但 subscriber 收不到。
- 預設事件 callback 會在 log 印 WARN（rclpy / rclcpp 原始碼確認的字串）：
  - publisher 端：`New subscription discovered on topic '/x', requesting incompatible QoS. No messages will be sent to it. Last incompatible policy: RELIABILITY`
  - subscription 端：`New publisher discovered on topic '/x', offering incompatible QoS. No messages will be received from it. Last incompatible policy: ...`
  - 型別不同：**通常沒有 WARN**，只是收不到；`ros2 topic list -t` 會看到同一個 topic 列出兩種型別（例：`/y [std_msgs/msg/Int32, std_msgs/msg/Int64]`，Jazzy 實測）
- 確認方式：`ros2 topic info -v /x`，逐一比對每個端點的 Reliability / Durability。
- `ros2 topic echo` 會自動配對 publisher，所以「echo 看得到、我的 node 收不到」常是自己的 subscription QoS 太嚴格（例如要求 RELIABLE 但 publisher 是 BEST_EFFORT）。
- 用 CLI 重現：`ros2 topic echo /x --qos-reliability reliable` 去接 best-effort publisher → 收不到且出現 warning。

### 3.5 QoS 程式寫法

```python
# rclpy
from rclpy.qos import (QoSProfile, ReliabilityPolicy, DurabilityPolicy,
                       HistoryPolicy, qos_profile_sensor_data)

qos = QoSProfile(depth=10,                       # KEEP_LAST 時 depth 必填
                 history=HistoryPolicy.KEEP_LAST,
                 reliability=ReliabilityPolicy.BEST_EFFORT,
                 durability=DurabilityPolicy.VOLATILE)
self.pub = self.create_publisher(Int32, '/number', qos)
self.sub = self.create_subscription(Int32, '/number', self.cb, qos_profile_sensor_data)

# 「latched」：晚加入的 subscriber 也收得到最後一筆（兩端都要 TRANSIENT_LOCAL）
latched = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)
```

```cpp
// rclcpp
auto qos = rclcpp::QoS(rclcpp::KeepLast(10)).best_effort().durability_volatile();
pub_ = create_publisher<std_msgs::msg::Int32>("/number", qos);
sub_ = create_subscription<std_msgs::msg::Int32>("/number", rclcpp::SensorDataQoS(), cb);
auto latched = rclcpp::QoS(1).transient_local();      // QoS(size_t) = KeepLast(n)
// 其他鏈式方法：reliable()、keep_all()、keep_last(n)、deadline(d)、lifespan(d)、
//              reliability_best_available()、durability_best_available()
```

CLI 對應：`--qos-reliability {reliable,best_effort,system_default,best_available}`、`--qos-durability {volatile,transient_local,...}`、`--qos-history {keep_last,keep_all}`、`--qos-depth N`、`--qos-profile {default,sensor_data,services_default,parameters,parameter_events,system_default,action_status_default,best_available}`。

### 3.6 QoS 語義上的細節

- RELIABLE 不等於「一定不掉」：在 KEEP_LAST 下，若 subscriber 處理太慢，佇列被新訊息覆蓋，舊訊息仍會遺失。要「一筆都不能少」需 `KEEP_ALL` 或足夠大的 depth，並讓 subscriber 跟得上。
- VOLATILE 時，publisher 剛建立就馬上 publish，discovery 尚未完成（通常數十到數百毫秒，⚠️未驗證實際數值），**第一批訊息會直接沒人收**。解法：TRANSIENT_LOCAL、或等 `count_subscribers(topic) > 0` 再發、或用 timer 晚一點發。
- BEST_EFFORT 在同一台機器上通常幾乎不掉包，但在負載高或訊息大時會掉；它的好處是不重送、延遲較穩。

---

## 4. rclpy 最小樣板（Jazzy）

### 4.1 API 簽名（jazzy rclpy 原始碼）

```python
rclpy.init(*, args=None, context=None, domain_id=None, signal_handler_options=None)
rclpy.spin(node, executor=None)
rclpy.spin_once(node, *, executor=None, timeout_sec=None)
rclpy.spin_until_future_complete(node, future, executor=None, timeout_sec=None)
rclpy.shutdown(*, context=None, uninstall_handlers=None)
rclpy.try_shutdown()        # 已 shutdown 也不會丟例外（練習程式用這個）

Node(node_name, *, namespace=None, parameter_overrides=None,
     allow_undeclared_parameters=False,
     automatically_declare_parameters_from_overrides=False, ...)
node.create_publisher(msg_type, topic, qos_profile, *, callback_group=None,
                      event_callbacks=None, qos_overriding_options=None)
node.create_subscription(msg_type, topic, callback, qos_profile, *, callback_group=None,
                         event_callbacks=None, qos_overriding_options=None,
                         raw=False, content_filter_options=None)
node.create_timer(timer_period_sec, callback, callback_group=None, clock=None, autostart=True)
node.create_service(srv_type, srv_name, callback, *, qos_profile=qos_profile_services_default,
                    callback_group=None)
node.create_client(srv_type, srv_name, *, qos_profile=qos_profile_services_default,
                   callback_group=None)
node.declare_parameter(name, value=None, descriptor=None, ignore_override=False)
node.get_parameter(name).value
node.add_on_set_parameters_callback(cb)   # cb(list[Parameter]) -> SetParametersResult
node.count_subscribers(topic) / node.count_publishers(topic)
node.get_logger().info('...') / .warn / .error / .debug
node.get_clock().now()                    # rclpy.time.Time，.nanoseconds
node.destroy_node()
```

注意參數順序：**publisher 是 (type, topic, qos)**；**subscription 是 (type, topic, callback, qos)**。

### 4.2 publisher + timer + subscriber + 參數（單檔可直接 `python3 x.py`）

```python
import rclpy
from rclpy.node import Node
from rclpy.executors import ExternalShutdownException
from std_msgs.msg import Int32


class Relay(Node):
    def __init__(self):
        super().__init__('relay')
        self.declare_parameter('scale', 2)
        self.scale = self.get_parameter('scale').value
        self.pub = self.create_publisher(Int32, '/double', 10)
        self.sub = self.create_subscription(Int32, '/number', self.on_msg, 10)
        self.timer = self.create_timer(1.0, self.on_timer)   # 週期單位：秒（float）
        self.count = 0

    def on_msg(self, msg: Int32):
        out = Int32()
        out.data = msg.data * self.scale
        self.pub.publish(out)
        self.count += 1

    def on_timer(self):
        self.get_logger().info(f'relayed {self.count} msgs')


def main():
    rclpy.init()
    node = Relay()
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

執行時改參數：`python3 relay.py --ros-args -p scale:=3`（`rclpy.init()` 預設讀 `sys.argv`）⚠️未驗證：單檔 script 傳 `--ros-args` 的行為與 `ros2 run` 一致（依 rclpy 設計應一致，考前實測）。

### 4.3 service server / client（std_srvs 在 ros_core 內）

```python
from std_srvs.srv import Trigger

# server
self.srv = self.create_service(Trigger, '/reset_count', self.on_reset)
def on_reset(self, request, response):
    self.count = 0
    response.success = True
    response.message = 'reset'
    return response                       # 一定要 return response

# client（不要在 callback 裡用同步 call，見 5.3）
cli = node.create_client(Trigger, '/reset_count')
while not cli.wait_for_service(timeout_sec=1.0):
    node.get_logger().info('waiting...')
future = cli.call_async(Trigger.Request())
rclpy.spin_until_future_complete(node, future)
print(future.result().message)
```

### 4.4 自訂 QoS 事件 callback（偵測不相容）

```python
from rclpy.event_handler import SubscriptionEventCallbacks
cbs = SubscriptionEventCallbacks(
    incompatible_qos=lambda e: self.get_logger().error(f'incompatible QoS: {e.last_policy_kind}'))
self.sub = self.create_subscription(Int32, '/number', self.on_msg, 10, event_callbacks=cbs)
```

`SubscriptionEventCallbacks` 可用 kwargs：`deadline, incompatible_qos, liveliness, message_lost, incompatible_type, matched, use_default_callbacks`；`PublisherEventCallbacks`：`deadline, liveliness, incompatible_qos, incompatible_type, matched, use_default_callbacks`。（`e.last_policy_kind` 為 rclpy jazzy `event_handler.py` 預設 callback 實際使用的屬性，值是 policy kind 整數）

### 4.5 rclpy 型別範圍檢查

rclpy 產生的 message 類別**預設不檢查欄位範圍**（Iron 起預設關閉；只有設環境變數 `ROS_PYTHON_CHECK_FIELDS=1`，或建構時傳 `check_fields=True` 才會在設值時 assert，依 rosidl_python jazzy `_msg.py.em`）。預設情況下，像練習的 `received.data * 2` 若超出 int32 範圍，不會丟例外，而是在 C 層轉型時**靜默變成錯誤的值**（`_msg_support.c.em` 對 int32 欄位做 `(int32_t)PyLong_AsLong(v)`，64-bit Linux 上相當於取低 32 位 = 二補數回繞；⚠️未實測），node 照常執行但輸出錯誤。Python 的 `int` 本身不會溢位，需自行決定截斷 / 夾限 / 回繞的語義（依題目規格）；除錯時可設 `ROS_PYTHON_CHECK_FIELDS=1` 讓越界直接報錯。

---

## 5. rclcpp 最小樣板（Jazzy）

```cpp
#include <chrono>
#include <memory>
#include "rclcpp/rclcpp.hpp"
#include "std_msgs/msg/int32.hpp"
using namespace std::chrono_literals;

class Relay : public rclcpp::Node {
public:
  Relay() : Node("relay") {
    scale_ = this->declare_parameter<int>("scale", 2);
    pub_ = this->create_publisher<std_msgs::msg::Int32>("/double", 10);
    sub_ = this->create_subscription<std_msgs::msg::Int32>(
      "/number", 10,                                   // 注意：C++ 是 (topic, qos, callback)
      [this](std_msgs::msg::Int32::UniquePtr msg) {
        std_msgs::msg::Int32 out;
        out.data = msg->data * scale_;                 // 有號溢位是 UB，必要時用 int64 計算
        pub_->publish(out);
      });
    timer_ = this->create_wall_timer(1s, [this]() {
      RCLCPP_INFO(this->get_logger(), "alive");
    });
  }
private:
  int scale_;
  rclcpp::Publisher<std_msgs::msg::Int32>::SharedPtr pub_;
  rclcpp::Subscription<std_msgs::msg::Int32>::SharedPtr sub_;
  rclcpp::TimerBase::SharedPtr timer_;
};

int main(int argc, char * argv[]) {
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<Relay>());   // = SingleThreadedExecutor
  rclcpp::shutdown();
  return 0;
}
```

- subscription callback 也可寫成 `const std_msgs::msg::Int32 & msg` 或 `std_msgs::msg::Int32::ConstSharedPtr msg`。
- 其他 spin：`rclcpp::spin_some(node)`、`rclcpp::spin_until_future_complete(node, future, timeout)`。
- 參數讀取：`this->get_parameter("scale").as_int()`。
- 成員 `SharedPtr` 一定要存起來；區域變數的 publisher / subscription / timer 離開 scope 就被銷毀，callback 不會再被呼叫。rclpy 不同：`Node` 內部會把建立的 publisher / subscription / timer 等存進自己的清單（jazzy `node.py` 的 `self._timers.append(...)` 等），沒存成 `self.xxx` 也不會被回收；但存起來才能之後 `cancel()` / `destroy_*()`，仍建議保存。

### 5.1 CMakeLists.txt / package.xml（官方教學格式）

```cmake
cmake_minimum_required(VERSION 3.8)
project(my_pkg)
find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(std_msgs REQUIRED)
add_executable(relay src/relay.cpp)
ament_target_dependencies(relay rclcpp std_msgs)
install(TARGETS relay DESTINATION lib/${PROJECT_NAME})
ament_package()
```

```xml
<depend>rclcpp</depend>
<depend>std_msgs</depend>
```

Python 套件則在 `package.xml` 加 `<exec_depend>rclpy</exec_depend>`、`<exec_depend>std_msgs</exec_depend>`，`setup.py` 的 `entry_points={'console_scripts': ['relay = my_pkg.relay:main']}`。

### 5.2 Intra-process communication（只有 rclcpp）

```cpp
auto opts = rclcpp::NodeOptions().use_intra_process_comms(true);
auto producer = std::make_shared<Producer>(opts);   // Node 建構子要接 NodeOptions
auto consumer = std::make_shared<Consumer>(opts);
rclcpp::executors::SingleThreadedExecutor exec;
exec.add_node(producer); exec.add_node(consumer);   // 同一個 process
exec.spin();

// 零複製：publish std::unique_ptr
auto msg = std::make_unique<std_msgs::msg::Int32>();
msg->data = 42;
pub_->publish(std::move(msg));
```

- 零複製條件：同 process、雙方都開 intra-process、以 `std::unique_ptr` publish，且 subscription callback 也收 `std::unique_ptr`（官方 demo 文件：用 `const &` / `shared_ptr` 收發不會零複製）；只有一個 subscription 時可完全不複製，多個 subscription 時除最後一個之外都要複製。
- 同 process 外的 subscriber 仍照常走 DDS，不影響內部零複製。
- rclpy 的 `Node` 建構子沒有對應選項（依 jazzy 原始碼簽名）。

### 5.3 Executor 與 callback group

| 類別 | rclcpp | rclpy |
|---|---|---|
| 單執行緒 | `rclcpp::executors::SingleThreadedExecutor`（`rclcpp::spin` 預設） | `rclpy.executors.SingleThreadedExecutor`（`rclpy.spin` 用全域 executor） |
| 多執行緒 | `rclcpp::executors::MultiThreadedExecutor(options, number_of_threads=0, ...)`：0 = CPU 核心數（最少 2） | `MultiThreadedExecutor(num_threads=None)`：None = `len(os.sched_getaffinity(0))`，失敗退回 `os.cpu_count()`，再不行 2 |
| 靜態 | `rclcpp::executors::StaticSingleThreadedExecutor`（entity 不變時省掉重複掃描） | — |
| 實驗性 | `rclcpp::experimental::executors::EventsExecutor`（標頭 `rclcpp/experimental/executors/events_executor/events_executor.hpp`） | rclpy 也有：`from rclpy.experimental import EventsExecutor`（rclpy 7.1.4 起 backport 到 Jazzy，實驗性） |

| Callback group | 行為 |
|---|---|
| `MutuallyExclusive` | 同組 callback 一次只跑一個 |
| `Reentrant` | 同組 callback（包含同一個 callback 自己）可並行 |
| 預設 | 每個 node 有一個 default group，型別是 **MutuallyExclusive** |

- **重點**：只有 MultiThreadedExecutor + 不同 group（或 Reentrant）才會真的並行。只換成 MultiThreadedExecutor、所有 callback 仍在預設 group → 仍然一次一個。
- 不同 group 的 callback 永遠可能並行 → 共享資料要加鎖（`threading.Lock` / `std::mutex`），而且鎖要抓短（同 section2-3 的觀念）。
- rclpy 每次 wait 後處理 ready entity 的順序：先 waitables，再逐個 node 依 timers → subscriptions → guard conditions → clients → services（jazzy `executors.py` `_wait_for_ready_callbacks`）。官方概念文件說明 executor 對訊息是 round-robin，不保證 FIFO。
- **死結**：在 callback 裡對 service 做同步呼叫（rclpy `client.call()`），而 client 的 response callback 與呼叫者在同一個 MutuallyExclusive group（或單執行緒 executor）→ 永遠等不到。解法：用 `call_async` + `future.add_done_callback`，或把 client 放到另一個 group 並用 MultiThreadedExecutor。

```python
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup, ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor

g_timer = MutuallyExclusiveCallbackGroup()
g_sub = MutuallyExclusiveCallbackGroup()
self.create_timer(0.01, self.fast_loop, callback_group=g_timer)
self.create_subscription(Int32, '/number', self.on_msg, 10, callback_group=g_sub)

ex = MultiThreadedExecutor()
ex.add_node(node)
ex.spin()
```

```cpp
auto g  = this->create_callback_group(rclcpp::CallbackGroupType::MutuallyExclusive);
auto g2 = this->create_callback_group(rclcpp::CallbackGroupType::MutuallyExclusive);
rclcpp::SubscriptionOptions opts;
opts.callback_group = g;
sub_ = create_subscription<std_msgs::msg::Int32>("/number", 10, cb, opts);
timer_ = create_wall_timer(10ms, tcb, g2);   // create_wall_timer 第三個參數是 callback group

rclcpp::executors::MultiThreadedExecutor exec;
exec.add_node(node);
exec.spin();
```

- Python 有 GIL：rclpy 的 MultiThreadedExecutor 讓「等待 I/O / 阻塞」的 callback 不互相卡住，但**純 Python 運算無法真正多核並行**。CPU 密集要改 C++、或拆成多個 process（多個 node 程式）。

### 5.4 Timer 注意事項

- rclpy `create_timer(period_sec, cb)`；rclcpp `create_wall_timer(std::chrono duration, cb)`。可 `timer.cancel()`、`timer.reset()`。
- callback 執行時間 > 週期 → 實際頻率下降（timer 不會同時跑兩次，同 group 時）。`ros2 topic hz` 看到的頻率低於設定值，先懷疑 callback 太慢。
- 不要在 callback 裡 `time.sleep()` / `while True` 迴圈：單執行緒 executor 整個被卡住，其他 subscription / timer 都不會跑。
- rclpy `Rate.sleep()` 在 executor 的 callback 內使用可能永遠卡住（rate 依賴 executor 觸發）⚠️未驗證細節；需要固定頻率一律用 timer。

---

## 6. 套件與建置（簡要）

```bash
# 假設 workspace 在 ~/ws，原始碼放 ~/ws/src
cd ~/ws/src
ros2 pkg create --build-type ament_python --license Apache-2.0 --node-name relay my_py_pkg --dependencies rclpy std_msgs
ros2 pkg create --build-type ament_cmake  --license Apache-2.0 --node-name relay my_cpp_pkg --dependencies rclcpp std_msgs
cd ~/ws
colcon build --packages-select my_py_pkg      # 只建一個套件
colcon build --symlink-install                # Python 改檔不用重 build
source install/setup.bash                     # 每個新 shell 都要做（在 /opt/ros/jazzy 之後）
ros2 run my_py_pkg relay
```

- `colcon` 不在 `ros_core` image 內；考場環境先 `which colcon` 確認。沒有就用單檔 `python3 x.py`（如練習），或照題目給的建置方式。
- 新增 executable / entry point 後要重 build 並重新 `source install/setup.bash`，否則 `ros2 run` 說找不到 executable。
- `ros2 run` 找不到套件 → 沒 source workspace，或 build 失敗（看 `log/latest_build/`）。
- C++ 改完一定要重 build；Python 沒用 `--symlink-install` 也要重 build。

---

## 7. 「資料沒有流動」除錯階梯（完整版）

依序檢查，前一層通過才往下。

| # | 檢查 | 指令 | 異常時的典型原因 |
|---|---|---|---|
| 0 | 這個 shell 有 ROS 環境嗎 | `printenv \| grep -i ROS`（應有 `ROS_DISTRO=jazzy`）；`which ros2` | `docker exec` 進來的 shell 沒 source；用 `docker exec srecruit-demo ros2 ...` 非互動執行不會讀 `.bashrc` → 改用 `docker exec -it <c> bash` 或 `bash -c 'source /opt/ros/jazzy/setup.bash && ros2 topic list'` |
| 1 | 兩邊 `ROS_DOMAIN_ID` / `ROS_AUTOMATIC_DISCOVERY_RANGE` / `RMW_IMPLEMENTATION` 一致嗎 | `printenv \| grep -E 'ROS_|RMW'`（每個 shell 都看） | 一邊 export 過別的值 → 互相看不見 |
| 2 | 預期的 node 存在嗎 | `ros2 node list`（懷疑快取就 `--no-daemon` 或 `ros2 daemon stop`） | 程式沒啟動 / 已崩潰（callback 例外）/ 沒呼叫 spin / node 名稱和預期不同 |
| 3 | 預期的 topic 存在嗎、名稱完全一致嗎 | `ros2 topic list -t` | 拼字、大小寫、少了 `/`、namespace 造成 `/ns/number` vs `/number`、remap 寫錯 |
| 4 | 兩端真的連在同一個 topic 嗎 | `ros2 node info /pub_node`、`ros2 node info /sub_node` | 一邊 publish `/number`、另一邊 subscribe `/numbers` |
| 5 | 型別一致嗎、數量合理嗎 | `ros2 topic info /number`（`-t` 出現兩個型別 = 型別衝突） | `Publisher count: 0`（publisher 沒起來或名稱不同）/ `Subscription count: 0` / 型別不同（Int32 vs Int64） |
| 6 | QoS 相容嗎 | `ros2 topic info -v /number` 比對 Reliability / Durability；看 log 有無 `incompatible QoS` | sub 要 RELIABLE、pub 是 BEST_EFFORT；sub 要 TRANSIENT_LOCAL、pub 是 VOLATILE |
| 7 | 線上真的有資料嗎、頻率對嗎 | `ros2 topic echo /number --once`、`ros2 topic hz /number` | publisher 只在條件成立時才發 / timer 沒建立 / 頻率太低 |
| 8 | 單獨測下游 node | `ros2 topic pub --once /number std_msgs/msg/Int32 "{data: 21}"` 同時 `ros2 topic echo /double` | 下游邏輯錯、callback 丟例外（看該 node 的終端機輸出） |
| 9 | 單獨測上游 node | 只開上游，`ros2 topic echo` 看輸出 | 上游根本沒發 / 發到別的 topic |
| 10 | 系統層 | `ros2 doctor --report`、`ros2 multicast receive/send` | 網路、multicast、RMW 問題 |

補充症狀對照：

| 症狀 | 優先懷疑 |
|---|---|
| `ros2: command not found` | 沒 source `/opt/ros/jazzy/setup.bash` |
| `Package 'x' not found` | 沒 source workspace 的 `install/setup.bash` |
| `node list` 看得到、`echo` 有資料、但自己的 node callback 沒跑 | 沒 spin / spin 前就 return / QoS 太嚴格 / subscription 物件被回收（rclcpp） |
| 第一筆或前幾筆訊息總是不見 | publish 太早（discovery 未完成），VOLATILE |
| `ros2 topic pub --once` 卡住不動 | 它在等 1 個相容 subscription（`-w` 預設 1），沒有 subscriber 或 QoS 不相容 |
| 頻率比設定低 | callback 阻塞 / 過慢、單執行緒 executor 被別的 callback 佔住、`print` 太多 |
| 偶爾少幾筆 | BEST_EFFORT、depth 太小、subscriber 太慢被覆蓋 |
| 兩個同名 node | `ros2 node list` 出現重複，參數 / service 會混亂；改 `__node:=` |
| node 消失 | 程式結束或例外；Python traceback 在啟動它的終端機 |
| `topic list` 結果與現況不符 | daemon 快取 → `ros2 daemon stop` 後重試 |
| 跨 container 通訊時 discovery 正常但收不到資料 | Fast DDS 共享記憶體傳輸在不同 container 間不通（⚠️未驗證於考場環境；同一 container 內不會發生） |

---

## 8. 效能 / 延遲 / 吞吐量優化清單

先量測再優化：`ros2 topic hz`（頻率）、`ros2 topic bw`（頻寬與訊息大小）、`ros2 topic delay`（需 header）、程式內用 `time.perf_counter()` / `std::chrono::steady_clock` 或 `node.get_clock().now()` 計時。

| 槓桿 | 作法 | 影響 |
|---|---|---|
| 不要阻塞 callback | 移除 `sleep`、長迴圈、同步 I/O、同步 service call；重活移到另一個 thread / group | 最常見的頻率下降原因 |
| 減少 log / print | 高頻路徑不要每筆 `print(..., flush=True)` 或 `get_logger().info`；改計數後由 timer 定期印 | stdout I/O 很貴 |
| 發布頻率 | timer 週期設合理值；不需要的資料不要發 | 直接降 CPU 與頻寬 |
| QoS depth | 延遲優先：小 depth（1～5）只留最新；完整性優先：大 depth 或 KEEP_ALL | depth 大 + 消費者慢 = 延遲累積 |
| Reliability | 高頻感測資料用 BEST_EFFORT（不重送、延遲穩）；控制命令 / 不能掉的資料用 RELIABLE | 重送會增加尾延遲 |
| Durability | 不需要給晚到的 subscriber 時用 VOLATILE | TRANSIENT_LOCAL 需要保存歷史 |
| 訊息大小 | 用最小足夠的型別（Int32 而非 String 轉數字）、避免大陣列、批次化多筆小訊息 | 序列化成本 ∝ 大小 |
| 序列化成本 | 同 process 用 rclcpp intra-process + `unique_ptr`（零複製）；Python 側每筆訊息都有轉換開銷 | |
| Executor | 多個獨立 callback 要並行 → MultiThreadedExecutor + 不同 callback group；rclcpp 靜態系統可試 `StaticSingleThreadedExecutor` 或 `EventsExecutor`（實驗性） | Python 受 GIL 限制 |
| 語言 | 熱路徑改 rclcpp；rclpy 每筆訊息的 per-message overhead 明顯較高 | 通常是最大幅度的提升 |
| 減少 hop | 把 A→B→C 三個 process 合成一個 process（或 composition）減少序列化與排程延遲 | |
| 計算本身 | 先用 profiler 找熱點（`python3 -m cProfile -s cumtime x.py`、`perf`）；避免在 callback 內重複配置物件 | |
| 量測工具本身 | 同時開很多 `echo` / `hz` 也會消耗 CPU；正式量測時關掉不需要的 | |

延遲的組成（概念）：publish 呼叫 → 序列化 → RMW/DDS 傳輸 → 反序列化 → executor 排到這個 callback 的等待時間 → callback 執行。Python 與 executor 排隊通常是大頭。

---

## 9. 常見陷阱總表

1. topic 名稱打錯 / 大小寫 / 前導 `/` / namespace 造成名稱不同 → 程式不報錯，只是連不上。
2. 型別不一致（`std_msgs/msg/Int32` vs `Int64` vs `example_interfaces/msg/Int32`）→ 連不上，rclpy / rclcpp 預設會印 incompatible type WARN。
3. 忘了 `rclpy.spin` / `rclcpp::spin` → callback 永遠不跑；用 `spin_once` 時要放在迴圈裡。
4. QoS 不相容 → 靜默失敗，只有 WARN log。
5. `ROS_DOMAIN_ID` 不一致 → 互相看不見。
6. 新 shell（尤其 `docker exec`）沒 source → `ros2` 指令不存在或套件找不到。
7. 自己的 workspace 改完沒重 build / 沒重新 source。
8. `create_publisher` 參數順序（rclpy：type, topic, qos；subscription：type, topic, callback, qos；rclcpp：topic, qos, callback）。
9. rclcpp：publisher / subscription / timer 沒存成成員 → 被銷毀（rclpy 的 Node 自己持有參考，不會被回收）。
10. 數值超出 message 欄位範圍（例如 Int32）→ 預設**不報錯、值靜默出錯**；設 `ROS_PYTHON_CHECK_FIELDS=1` 才會丟例外（此時 callback 例外會讓 spin 中止、node 消失）。
11. callback 內同步 service call → 死結。
12. `ros2 topic pub --once` 在沒有 subscriber 時會等待。
13. `ros2 topic echo` 看到資料不代表你的 subscriber 收得到（echo 會自動配合 QoS）。
14. `ros2 topic delay` 只能用在有 header 的訊息。
15. 練習的 container 用 `--rm`，離開第一個 shell 後 container 與修改全部消失；要保留就 `-v "$PWD:/demo"` 掛載。

---

## 10. ROS 2 與微控制器（推測性背景，⚠️與考題的關聯完全未知）

考試環境據 Dockerfile 註解會有 pico-sdk、交叉編譯工具鏈與開發板（推測為 RP2350 / Pico 2）。若題目讓 ROS 2 與板子溝通，常見做法有兩類：

| 方式 | 說明 | 備註 |
|---|---|---|
| micro-ROS | MCU 上跑 micro-ROS client（rclc API），經 serial / USB CDC 連到主機上的 **micro-ROS agent**，agent 把它轉成一般 ROS 2 node / topic | 官方 Pico 範例 repo `micro_ros_raspberrypi_pico_sdk` 有 jazzy 分支，但附的預編譯 `libmicroros.a` 是以 `-mcpu=cortex-m0plus`（RP2040）建置；用在 RP2350 ARM 是否可行 ⚠️未驗證，RISC-V 核心需重新編譯（詳見 `host-mcu-comm.md`） |
| 自寫 serial bridge | 主機寫一個 rclpy / rclcpp node：讀 `/dev/ttyACM0`（USB CDC）或 UART，解析位元組後 publish 到 topic；反向則 subscribe 後寫入 serial | 需要自訂封包格式（起始位元組、長度、checksum）；Python 需 `pyserial`（⚠️未驗證環境是否有） |

micro-ROS agent 連線指令（官方 Pico repo README 的寫法）：`micro-ros-agent serial --dev /dev/ttyACM0 -b 115200`；以 ROS 2 套件形式安裝時常見寫法為 `ros2 run micro_ros_agent micro_ros_agent serial --dev /dev/ttyACM0 -b 115200`（⚠️未驗證）。

自寫 bridge 的效能要點：serial 讀取不要在單執行緒 executor 的 callback 裡阻塞（用獨立 thread 讀、或非阻塞讀 + timer）；批次讀取；封包要能重新同步（掉一個 byte 不應讓之後全部錯位）。

---

## 11. 向模型提問的範本

**範本 1：資料沒流動**
```
我在 ROS 2 Jazzy 系統中，預期資料流是 {{上游node}} --{{topic名稱}} ({{訊息型別}})--> {{下游node}}，但 {{症狀，例如 下游 callback 沒被呼叫 / echo 沒資料}}。
以下是我執行的指令與輸出：
ros2 node list: {{輸出}}
ros2 topic list -t: {{輸出}}
ros2 topic info -v {{topic}}: {{輸出}}
相關程式碼：{{create_publisher / create_subscription 那幾行}}
請依「環境→node→topic 名稱→型別→pub/sub 數量→QoS→實際資料」的順序判斷最可能的原因，並給我下一個要執行的 ros2 指令。
```

**範本 2：QoS 判斷**
```
Publisher 的 QoS 是 {{reliability / durability / history / depth}}，subscriber 的 QoS 是 {{...}}。
需求是 {{例如 延遲最低、允許掉包 / 一筆都不能掉 / 晚啟動的 node 也要拿到最後一筆}}。
請判斷目前是否相容，並給出兩端應該設定的 QoS（附 rclpy 程式碼與對應的 ros2 topic echo/pub --qos-* 測試指令）。
```

**範本 3：效能優化**
```
這個 {{rclpy/rclcpp}} node 目前 `ros2 topic hz {{topic}}` 只有 {{實測}} Hz，目標 {{目標}} Hz（或延遲目標 {{...}} ms）。
callback 程式碼如下：{{程式碼}}
executor 與 callback group 設定：{{設定}}
評分方式：{{題目說明的評分/量測方式}}
請找出瓶頸（阻塞、log、QoS depth、executor、序列化、語言），依「改動小、收益大」排序列出修改，並說明我要怎麼用 ros2 CLI 驗證改善。不要改變輸出的正確性：{{輸出格式/語義要求}}。
```

**範本 4：從規格寫 node**
```
題目要求：{{題目文字，含 topic 名稱、型別、頻率、轉換規則、邊界條件}}
環境：ROS 2 Jazzy，{{用 python3 單檔 / colcon 套件}}，可用的訊息套件 {{std_msgs 等}}。
請寫出最小可執行的 {{rclpy/rclcpp}} node，topic 名稱一字不差照規格，處理 {{溢位/負數/空輸入}} 邊界，並給我一組 `ros2 topic pub --once` + `ros2 topic echo` 測試指令與預期輸出。
```

**範本 5：閱讀陌生程式碼的資料流**
```
以下是 {{檔案}} 的程式碼：{{程式碼}}
請列出：每個 node 名稱、它 publish / subscribe 的 topic（解析後的絕對名稱，namespace={{...}}）、型別、QoS、timer 週期、callback group 與 executor 型別，並畫出 ASCII 資料流圖；指出任何可能造成資料不流動或效能瓶頸的地方。
```
