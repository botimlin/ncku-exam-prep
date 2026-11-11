# 貼上卡：ROS 2 Jazzy
> 用法：一次只複製一張卡（兩條分隔線之間），貼進對話，再在下面寫你的問題。每張 ≤ 1200 字元。
> 來源：full/domain/ros2.md、lite/domain/ros2.md（詳細版）｜最後更新 2026-11

---

【參考卡｜ROS 2 1/8｜資料沒流動：除錯階梯】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
環境：ROS 2 Jazzy，Docker image ros:jazzy-ros-core。
依序檢查，前一層通過才往下：
0. shell 有 ROS 環境嗎：`printenv | grep -i ROS`（應有 ROS_DISTRO=jazzy）。非互動 `docker exec <c> ros2 ...` 不讀 .bashrc → 用 `docker exec -it <c> bash`，或 `bash -c 'source /opt/ros/jazzy/setup.bash && ros2 topic list'`。
1. 每個 shell 的 ROS_DOMAIN_ID / ROS_AUTOMATIC_DISCOVERY_RANGE / RMW_IMPLEMENTATION 一致：`printenv | grep -E 'ROS_|RMW'`。
2. node 存在：`ros2 node list`（懷疑快取：`ros2 daemon stop`）。沒有 → 沒啟動 / 例外崩潰 / 沒 spin / 名稱不同。
3. topic 名稱完全一致：`ros2 topic list -t`（拼字、大小寫、少 `/`、namespace `/ns/number` vs `/number`、remap 錯）。
4. 兩端連同一 topic：`ros2 node info /pub_node`、`ros2 node info /sub_node`。
5. 型別與數量：`ros2 topic info /number`（count 為 0？Int32 vs Int64？）。
6. QoS 相容：`ros2 topic info -v /number` 比對 Reliability / Durability；log 有無 `incompatible QoS`。
7. 有資料、頻率對：`ros2 topic echo /number --once`、`ros2 topic hz /number`。
8. 單測下游：`ros2 topic pub --once /number std_msgs/msg/Int32 "{data: 21}"` 同時 `ros2 topic echo /double`；看 node 終端機有無 traceback。
9. 單測上游：只開上游，echo 看輸出。
10. 系統層：`ros2 doctor --report`、`ros2 multicast receive/send`。
名稱差一字就是另一個 topic，不報錯。

---

【參考卡｜ROS 2 2/8｜症狀 → 優先懷疑】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
環境：ROS 2 Jazzy（預設 RMW rmw_fastrtps_cpp），image ros:jazzy-ros-core。
- `ros2: command not found` → 沒 `source /opt/ros/jazzy/setup.bash`。
- `Package 'x' not found` → 沒 source workspace 的 `install/setup.bash`，或 build 失敗。
- node 看得到、echo 有資料、但自己 node 的 callback 沒跑 → 沒 spin / spin 前就 return / 自己的 subscription QoS 太嚴格 / （rclcpp）subscription 物件沒存成成員被銷毀。
- 第一筆或前幾筆總是不見 → VOLATILE 下 publish 太早，discovery 未完成。
- `ros2 topic pub --once` 卡住不動 → 它預設在等 1 個相容 subscription（`-w` 預設 1）；沒 subscriber 或 QoS 不相容。用 `-w 0` 或 `--max-wait-time-secs 3`。
- 頻率比設定低 → callback 阻塞 / 過慢、單執行緒 executor 被別的 callback 佔住、print 太多。
- 偶爾少幾筆 → BEST_EFFORT、depth 太小、subscriber 太慢被覆蓋。
- 兩個同名 node（node list 出現重複）→ 參數 / service 混亂；用 `--ros-args -r __node:=新名`。
- node 消失 → 程式結束或 callback 例外；Python traceback 在啟動它的終端機。
- `topic list` 與現況不符 → daemon 快取，`ros2 daemon stop` 後重試。
- 型別不同（Int32 vs Int64）→ 連不上、通常無 WARN；`ros2 topic list -t` 同一 topic 列出兩種型別。
- `ROS_DOMAIN_ID` 不一致 → 互相看不見。
- 改完程式沒重 build / 沒重新 source（C++ 一定要重 build；Python 沒用 --symlink-install 也要）。
- 兩個 container 都 `--network host`：topic list 看得到但收不到 → Fast DDS 共享記憶體不通（實測）；兩邊加 `--ipc host`（預設 bridge 網路正常）。

---

【參考卡｜ROS 2 3/8｜QoS 預設值與相容性】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
環境：ROS 2 Jazzy。
預設 profile：
- default（`create_publisher(T, '/t', 10)` 就是這個）：KEEP_LAST、depth 10、RELIABLE、VOLATILE。
- sensor_data（`from rclpy.qos import qos_profile_sensor_data`）：KEEP_LAST、depth 5、BEST_EFFORT、VOLATILE。
相容規則：publisher 提供的品質 ≥ subscription 要求才相容。
- Reliability：pub BEST_EFFORT + sub RELIABLE → 不相容；其他相容。
- Durability：pub VOLATILE + sub TRANSIENT_LOCAL → 不相容；兩端都 TRANSIENT_LOCAL 才收得到舊訊息。
- Deadline / Lease：sub 有設而 pub 沒設，或 pub x > sub y → 不相容。
- Liveliness：pub AUTOMATIC + sub MANUAL_BY_TOPIC → 不相容。
- History / Depth 不影響相容性。任一 policy 不相容 → 這對完全不傳。
不相容 = 靜默失敗：無例外、topic info 的 pub/sub 數都正確，但收不到。log 只有 WARN：
- pub 端：`New subscription discovered on topic '/x', requesting incompatible QoS. No messages will be sent to it.`
- sub 端：`New publisher discovered on topic '/x', offering incompatible QoS. No messages will be received from it.`
確認：`topic info -v` 逐端比對。
`ros2 topic echo` 會自動配合現有 publisher 的 QoS（啟動時沒 publisher 就用 sensor_data），所以「echo 看得到、我的 node 收不到」常是自己 subscription 太嚴格。重現：`ros2 topic echo /x --qos-reliability reliable` 接 best-effort publisher。
RELIABLE + KEEP_LAST 下 subscriber 太慢，舊訊息仍會被覆蓋而掉；一筆不少需 KEEP_ALL 或夠大 depth。

---

【參考卡｜ROS 2 4/8｜rclpy 最小 pub/sub/timer 程式】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
環境：ROS 2 Jazzy rclpy 單檔。
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
    self.timer = self.create_timer(1.0, self.on_timer)
    self.count = 0
  def on_msg(self, msg):
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
- 順序：publisher (type, topic, qos)；subscription (type, topic, callback, qos)。qos=10 即 KEEP_LAST 10、RELIABLE、VOLATILE。
- 沒 spin 則 callback 不跑；timer 週期單位是秒。

---

【參考卡｜ROS 2 5/8｜Jazzy 特有陷阱】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
環境：ROS 2 Jazzy（ros2cli / rclpy jazzy 分支原始碼確認）。
1. `ros2 topic pub --once`（或 `-t N`）預設 `-w/--wait-matching-subscriptions` = 1：等到 1 個「相容」subscription 才發。沒 subscriber 或 QoS 不相容 → 一直卡著像當掉。強制發：`-w 0`，或 `--max-wait-time-secs 3`。不加 --once/-t 時 -w 預設 0、每秒發一次。
2. rclpy 訊息欄位預設不檢查範圍（Iron 起關閉）。Int32 的 `data` 給超出 int32 的值不丟例外，在 C 層轉型時靜默變錯值（取低 32 位 = 二補數回繞；實測 2**31+5 → -2147483643）。Python int 本身不溢位，要依規格自己決定截斷 / 夾限 / 回繞。設 `ROS_PYTHON_CHECK_FIELDS=1`（或建構時 `check_fields=True`）才會 assert；此時 callback 例外會讓 spin 中止、node 消失。回繞：`((v + 2**31) & 0xFFFFFFFF) - 2**31`。
3. Executor / callback group：node 預設 callback group 是 MutuallyExclusive。只換 MultiThreadedExecutor、callback 都在預設 group → 仍一次一個。要並行：MultiThreadedExecutor 且放不同 group（或 Reentrant）。Python 有 GIL，純運算不會多核加速。
4. callback 內同步 service call（`client.call()`）→ 死結；用 `call_async` + `future.add_done_callback`。
5. `ros2 topic delay` 只能用在有 `header.stamp` 的訊息（Int32 不行）。
6. `ROS_LOCALHOST_ONLY` 已 deprecated（設 1 仍生效但印 WARN），改 `ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST`（預設 SUBNET）。
7. `ros2 service call` 型別必填；`ros2 action type` 是 Jazzy 新增。
8. rclpy 有 `from rclpy.experimental import EventsExecutor`（7.1.4 起，實驗性）。

---

【參考卡｜ROS 2 6/8｜Executor 與 callback group】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
環境：ROS 2 Jazzy（rclpy / rclcpp）。
- `rclpy.spin` / `rclcpp::spin` = SingleThreadedExecutor。
- MutuallyExclusive：同組一次一個。Reentrant：同組（含同一 callback 自己）可並行。node 預設 group = MutuallyExclusive。
- 只有 MultiThreadedExecutor + 不同 group（或 Reentrant）才真的並行 → 共享資料加鎖（`threading.Lock` / `std::mutex`），鎖要短。
- rclpy 有 GIL：只讓阻塞型 callback 不互卡，純 Python 運算不加速。
- 死結：callback 內同步呼叫 service，而 response 與呼叫者同 group 或單執行緒 → 永遠等不到。解：`call_async`。
- callback 不可 `time.sleep()` / `while True`；固定頻率用 timer。
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
rclcpp：`create_callback_group(rclcpp::CallbackGroupType::MutuallyExclusive)`；subscription 用 `SubscriptionOptions opts; opts.callback_group = g;`；`create_wall_timer(10ms, tcb, g2)` 第三參數是 group。

---

【參考卡｜ROS 2 7/8｜效能 / 延遲 / 吞吐量優化】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
環境：ROS 2 Jazzy（rclpy / rclcpp）。
先量測再改：`ros2 topic hz`（頻率）、`ros2 topic bw`（頻寬與訊息大小）、`ros2 topic delay`（需 header.stamp）、程式內 `time.perf_counter()` / `std::chrono::steady_clock`。輸入 hz vs 輸出 hz：輸出較低 = 跟不上。
槓桿：
1. callback 不阻塞：移除 sleep、長迴圈、同步 I/O、同步 service call；重活移到另一 thread / group。最常見的頻率下降原因。
2. 高頻路徑不要每筆 `print(..., flush=True)` 或 `get_logger().info`；改計數，timer 每秒印一次。
3. 發布頻率合理；不需要的資料不要發。
4. QoS depth：延遲優先用小 depth（1～5）只留最新；完整性優先用大 depth 或 KEEP_ALL。depth 大 + 消費者慢 = 延遲累積。
5. 高頻感測用 BEST_EFFORT（不重送、延遲穩）；不能掉的用 RELIABLE。不需給晚到者就用 VOLATILE。
6. 訊息小：最小足夠型別（Int32 而非 String 轉數字）、避免大陣列、多筆小訊息批次成一則。
7. 獨立 callback 要並行 → MultiThreadedExecutor + 不同 callback group（Python 受 GIL 限制）。rclcpp 可試 StaticSingleThreadedExecutor 或 EventsExecutor（實驗性）。
8. 熱路徑改 rclcpp，通常提升最大（rclpy 每則訊息開銷明顯較高）。
9. 同 process 零複製（只有 rclcpp）：`rclcpp::NodeOptions().use_intra_process_comms(true)`，publish `std::unique_ptr`，subscription 也收 unique_ptr。
10. 減少 hop：A→B→C 合成一個 process。
11. 找熱點：`python3 -m cProfile -s cumtime x.py`；callback 內別重複配置物件。
12. 量測時關掉多開的 echo / hz。
延遲組成：publish → 序列化 → DDS → 反序列化 → executor 排隊 → callback；Python 與排隊通常是大頭。

---

【參考卡｜ROS 2 8/8｜CLI 速查與 rclcpp 寫法】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
環境：ROS 2 Jazzy，每個 shell 先 `source /opt/ros/jazzy/setup.bash`。
CLI：
- `ros2 topic echo /t --once`、`--field a.b`、`--filter 'm.data > 50'`、`--csv`、`--timeout SEC`
- `ros2 topic pub /t std_msgs/msg/Int32 "{data: 21}"`（YAML 冒號後要空格）；`-r HZ`（預設 1.0）、`-1/--once`、`-t N`、`-w 0`
- `ros2 interface show std_msgs/msg/Int32`；`ros2 interface proto T` 印可給 pub 用的 YAML 範本
- QoS 旗標：`--qos-reliability reliable|best_effort`、`--qos-durability volatile|transient_local`、`--qos-depth N`、`--qos-profile sensor_data`
- `ros2 param get/set/dump/load /node ...`
- `ros2 run pkg exe --ros-args -r __node:=n -r __ns:=/x -r old:=new -p k:=v`
- 名稱：`/number` 絕對；`number` 相對 → `/ns/number`；`~/number` 私有 → `/ns/n/number`。區分大小寫。
rclcpp：
```cpp
pub_=create_publisher<std_msgs::msg::Int32>("/double",10);
sub_=create_subscription<std_msgs::msg::Int32>("/number",10,cb); // (topic,qos,cb)
timer_=create_wall_timer(1s,cb,group);
```
- C++ subscription 參數是 (topic, qos, callback)，與 rclpy 不同。
- pub/sub/timer 一定要存成成員 SharedPtr，區域變數離開 scope 就被銷毀。
- C++ QoS：`rclcpp::QoS(10).best_effort().transient_local()`、`rclcpp::SensorDataQoS()`。
