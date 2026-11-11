# ROS 2 Jazzy 速查（精簡版）
用途：考場除錯/優化 ROS 2。適用：Jazzy（預設 RMW rmw_fastrtps_cpp，image ros:jazzy-ros-core，無 colcon）。來源：docs.ros.org/en/jazzy、github.com/ros2/{ros2cli,rclpy,rclcpp,rmw}（jazzy 分支）。最後更新 2026-11

## CLI
| 指令 | 用途 |
|---|---|
| `ros2 node list` / `node info /n` | node；其 pub/sub/service |
| `ros2 topic list -t` | topic+型別 |
| `ros2 topic info -v /t` | 型別、pub/sub 數、每端 **QoS** |
| `ros2 interface show T` / `proto T` | 欄位 / YAML 範本 |
| `ros2 topic echo /t [--once] [--field a.b] [--filter 'm.data>5']` | 看資料 |
| `ros2 topic hz /t` / `bw /t` | 頻率 / 頻寬（`-w N` 視窗）|
| `ros2 topic delay /t` | 僅限有 header.stamp |
| `ros2 topic pub -1 /t std_msgs/msg/Int32 "{data: 21}"` | 發一筆；`-r HZ`、`-t N` |
| `ros2 service call /s std_srvs/srv/Trigger` | 型別必填 |
| `ros2 param get/set/dump/load /n ...` | 參數 |
| `ros2 action send_goal /a T "{...}" -f` | action+feedback |
| `ros2 doctor --report`；`ros2 daemon stop`；`--no-daemon` | 系統檢查 / 清快取 |
| `ros2 run pkg exe --ros-args -r old:=new -r __ns:=/x -p k:=v` | remap/參數 |

- `pub --once/-t` 預設等 1 個**相容** subscriber（`-w`）→ 沒 sub 會卡住；`-w 0` 或 `--max-wait-time-secs 3`。
- echo 自動配合 publisher QoS（沒 pub 時用 sensor_data）；hz/bw 用 best effort。echo 收得到 ≠ 你的 node 收得到。
- QoS 旗標：`--qos-reliability reliable|best_effort`、`--qos-durability volatile|transient_local`、`--qos-depth N`、`--qos-profile sensor_data`。

## QoS
- `create_publisher(T, '/t', 10)` = KEEP_LAST 10、RELIABLE、VOLATILE。sensor_data = depth 5、BEST_EFFORT、VOLATILE。
- 相容 = pub 品質 ≥ sub 要求。**不相容**：pub BEST_EFFORT↔sub RELIABLE；pub VOLATILE↔sub TRANSIENT_LOCAL；sub 設 deadline 而 pub 沒設或較長。
- 不相容 = 完全不傳、不丟例外，只有 WARN：`requesting incompatible QoS` / `offering incompatible QoS`。
- RELIABLE+KEEP_LAST 消費太慢仍會被覆蓋而掉。VOLATILE 時 publish 太早（discovery 未完）前幾筆會丟。

## rclpy / rclcpp
```python
self.pub=self.create_publisher(Int32,'/double',10)            # (type,topic,qos)
self.sub=self.create_subscription(Int32,'/number',self.cb,10) # (type,topic,cb,qos)
self.timer=self.create_timer(1.0,self.tick)                  # 秒
rclpy.init(); rclpy.spin(node); node.destroy_node(); rclpy.try_shutdown()
```
```cpp
pub_=create_publisher<std_msgs::msg::Int32>("/double",10);
sub_=create_subscription<std_msgs::msg::Int32>("/number",10,cb); // (topic,qos,cb)
timer_=create_wall_timer(1s,cb,group);
```
- QoS：`QoSProfile(depth=10, reliability=ReliabilityPolicy.BEST_EFFORT)`；C++ `rclcpp::QoS(10).best_effort().transient_local()`。
- 預設 callback group = MutuallyExclusive；並行要 MultiThreadedExecutor **且**不同 group/Reentrant。共享資料加鎖、鎖要短。Python 有 GIL。
- callback 內同步 service call → 死結；用 `call_async`。
- rclpy 預設不檢查欄位範圍：Int32 越界不報錯、值靜默出錯（`ROS_PYTHON_CHECK_FIELDS=1` 才 assert）。C++ 有號溢位 UB。
- rclcpp 實體要存成成員，否則被銷毀（rclpy Node 自己持有參考，但仍建議存）。

## 資料不流動階梯
0 `printenv|grep -E 'ROS_|RMW'`（有 jazzy？`docker exec` shell 有 source？DOMAIN_ID 一致？）
1 `node list` → 2 `topic list -t`（拼字/大小寫/`/`/namespace）→ 3 `node info` 兩端同 topic？→ 4 `topic info` 型別、pub/sub 數 → 5 `topic info -v` QoS → 6 `echo --once`、`hz` → 7 `pub -1` 測下游 + `echo` 看輸出 → 8 `doctor --report`、`daemon stop`
- 常見：沒 spin、callback 例外、node 名重複、沒重 build/source。
- 型別不同（Int32 vs Int64）→ 連不上、通常無 WARN，`topic list -t` 同 topic 列兩種型別。兩 container 都 `--network host` 卻收不到 → 兩邊加 `--ipc host`（Fast DDS 共享記憶體）。

## 優化槓桿
- callback 不阻塞（無 sleep/長迴圈/同步 I/O）；高頻路徑不 print/log。
- depth：延遲優先小（1~5）；完整性優先大或 KEEP_ALL。
- 高頻感測 BEST_EFFORT；不可掉 RELIABLE。
- 訊息小、型別精簡、批次化；降低不必要的發布率。
- 熱路徑改 rclcpp；同 process 用 intra-process：`NodeOptions().use_intra_process_comms(true)` + publish `unique_ptr`（零複製）。
- 合併 node 減少 hop；先量測（hz/bw/perf_counter）再改。

## MCU（推測⚠️）
micro-ROS agent 經 serial 橋接（Pico 範例 repo 為 RP2040，RP2350 未驗證）；或自寫 serial→topic bridge（讀取放獨立 thread）。
