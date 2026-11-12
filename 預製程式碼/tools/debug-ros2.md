# ROS 2 Jazzy 進階除錯

> 基本 CLI（node/topic list、echo、pub、QoS 規則、colcon、launch）在 [`../ros2/README.md`](../ros2/README.md)，這份不重複。
> 全部在 `ros:jazzy-ros-core` 容器裡實際跑過。**ros-core 少了這些**（用 apt 裝在拋棄式容器裡測）：

| 少了什麼 | 症狀 | 套件 |
|---|---|---|
| `ros2 bag` | `ros2: error: argument ...: invalid choice: 'bag' (choose from 'action', ...)` | `ros-jazzy-ros2bag` + `ros-jazzy-rosbag2-storage-default-plugins`（預設格式 mcap） |
| `colcon` | `colcon: command not found` | `python3-colcon-common-extensions` |
| gcc / g++ | 編 C++ 套件失敗 | `build-essential` |
| `demo_nodes_py` talker/listener | `Package 'demo_nodes_py' not found` | `ros-jazzy-demo-nodes-py` |

ros-core **有**：`ros2 doctor / param / topic / node / service / launch / run / pkg / daemon / interface`、rclpy、rclcpp、std_msgs。
考場映像檔可能是更完整的版本 → 先 `ros2 -h` 看有哪些指令，`ros2 pkg list | grep -E "bag|demo"`。

## 1. `ros2 doctor`：環境總檢查

```bash
ros2 doctor                 # 最後一行：All 5 checks passed
ros2 doctor --report        # 完整報告
ros2 doctor --report | grep -A4 "RMW MIDDLEWARE\|ROS 2 INFORMATION\|TOPIC LIST"
```
實測報告裡有用的部分：
```
   RMW MIDDLEWARE
middleware name    : rmw_fastrtps_cpp          ← 兩邊的 RMW 不一樣會連不上
   ROS 2 INFORMATION
distribution name      : jazzy
   TOPIC LIST
topic               : none                     ← 目前看得到的 topic
   NETWORK CONFIGURATION                       ← 看網卡：只有 lo = 不會跟別的機器/容器通
```
- `UserWarning: ... has been updated to a new version` 只是說套件有新版，**不用理**。它會上網查版本，沒網路時可能多一些警告。

## 2. log 等級和格式

```bash
ros2 run pkg exe --ros-args --log-level debug          # 全部 debug (連 rcl 內部都會印，很多)
ros2 run pkg exe --ros-args --log-level pnode:=debug   # 只把 node "pnode" 調成 debug ← 推薦
ros2 run pkg exe --ros-args --log-level warn           # 只看警告以上 (安靜)
export RCUTILS_CONSOLE_OUTPUT_FORMAT="[{severity}] [{name}] {file_name}:{line_number} {message}"
export RCUTILS_COLORIZED_OUTPUT=0                       # 關掉顏色 (存成檔案時比較乾淨)
```
實測（同一個 node，`self.get_logger().debug/info/warn(...)`）：
```
預設：            [INFO] [1794403061.339106394] [pnode]: info msg: factor=5      ← debug 看不到
pnode:=debug：     [DEBUG] [...] [pnode]: debug msg: factor=2
--log-level debug：[DEBUG] [...] [rcl]: Initializing node 'pnode' in namespace ''   ← 一大堆內部訊息
                  [DEBUG] [...] [rcl]: Using domain ID of '0'                       ← 但可以看到 domain ID
自訂格式：         [INFO] [pnode] /tmp/pnode.py:8 info msg: factor=2               ← 有檔名和行號
```
- ROS 的 log 預設印到 **stderr**（實測 `2>/dev/null` 之後什麼都看不到）。評分如果是看 topic 內容，log 不會影響結果；如果是看 stdout，用 `get_logger()` 而不是 `print()`。
- log 檔也會存到 `~/.ros/log/`。

## 3. 參數（param）

```bash
ros2 param list /tk                          # 實測：start_type_description_service、use_sim_time
ros2 param get /tk use_sim_time              # Boolean value is: False
ros2 param set /tk use_sim_time true         # Set parameter successful
ros2 param dump /tk                          # 印成 yaml，可以直接存成參數檔
ros2 run pkg exe --ros-args -p factor:=5     # 啟動時設定
ros2 run pkg exe --ros-args --params-file p.yaml
```
參數檔格式（實測讀到 `factor=9`）：
```yaml
pnode:                 # ← node 名稱，要跟程式裡 super().__init__("pnode") 一樣，否則不會套用
  ros__parameters:     # ← 兩個底線
    factor: 9
```
- 型別錯誤（實測）：`-p factor:=abc` → `InvalidParameterTypeException: Trying to set parameter 'factor' to 'abc' of type 'STRING', expecting type 'INTEGER'`。
  `-p x:=5` 是整數、`-p x:=5.0` 是浮點數、`-p x:="'5'"` 是字串。
- 程式裡沒有 `declare_parameter` 的參數，`ros2 param set` 會失敗（實測：`Setting parameter failed: Invalid access to undeclared parameter(s)`）。
- `ros2 param set` 改了值，**程式不一定會用到新的值**：要程式每次都重新 `get_parameter`，或有註冊 callback。

## 4. 重新對應（remap）

```bash
ros2 run demo_nodes_py talker --ros-args -r chatter:=/chat2 -r __node:=tk
#   -r 舊topic:=新topic    -r __node:=新node名稱    -r __ns:=/robot1 (namespace)
```
實測：`ros2 node list` → `/tk`；`ros2 topic list -t` → `/chat2 [std_msgs/msg/String]`。
- 題目給的程式 topic 名稱寫錯時，可以**不改程式碼**，直接 remap 修好（先確認題目允許）。
- 多個參數：`--ros-args -r a:=b -p x:=1 --log-level warn`（只寫一次 `--ros-args`）。

## 5. QoS 不相容：看 `-v` 和警告訊息

```bash
ros2 topic info -v /q | grep -E "Endpoint type|Reliability|Durability"
```
實測：發布端 `--qos-reliability best_effort`、訂閱端 `reliable` → 兩邊都會印出警告：
```
[WARN] ... New publisher discovered on topic '/q', offering incompatible QoS. No messages will be received from it. Last incompatible policy: RELIABILITY
[WARN] ... New subscription discovered on topic '/q', requesting incompatible QoS. No messages will be sent to it. Last incompatible policy: RELIABILITY
```
→ 只要在 log 裡看到 `incompatible QoS`，就看 `Last incompatible policy:` 是哪一項，把兩邊改成一樣。

## 6. rosbag：錄起來、重播、看內容

**2024 年的評分系統就是用 rosbag**（錄下你的輸出 topic 來評分 / 播放輸入資料給你）。
```bash
ros2 bag record -o mybag /chatter            # 錄指定的 topic；全部錄：ros2 bag record -a -o mybag
#   → 按 Ctrl-C 停止。會產生 mybag/mybag_0.mcap + mybag/metadata.yaml
ros2 bag info mybag                          # 有哪些 topic、幾筆、多久
ros2 bag play mybag                          # 重播 (原本的時間間隔)
ros2 bag play mybag -r 2.0                   # 2 倍速
ros2 bag play mybag -l                       # 重複播放
ros2 bag play mybag --topics /chatter        # 只播某些 topic
ros2 bag play mybag --remap /chatter:=/input # 播的時候換 topic 名稱（實測 listener 在 /input 收到）
```
`ros2 bag info` 實測輸出：
```
Files:             bag2_0.mcap
Storage id:        mcap
Duration:          3.000032543s
Messages:          4
Topic information: Topic: /chatter | Type: std_msgs/msg/String | Count: 4 | Serialization Format: cdr
```
- **用 Ctrl-C（SIGINT）或 `kill PID`（SIGTERM）正常停止**，才會寫出 `metadata.yaml`（兩種都實測成功）。
- ⚠ 坑（實測）：在 script 裡用 `ros2 bag record ... &` 放到背景，再 `kill -INT` → **沒有效果**（背景程式會忽略 SIGINT），錄影一直在跑。要用 `kill PID`（SIGTERM）或 `timeout -s INT 10 ros2 bag record ...`。
- 被 `kill -9` 或直接關掉終端機 → 沒有 metadata → `ros2 bag info` 顯示 `Could not find metadata in bag directory`。`ros2 bag reindex mybag` 可以試著修復，但實測 mcap 沒寫完的時候會失敗 → 重錄。
- 重播的資料和你自己的 publisher 會**同時**出現在同一個 topic（實測 listener 交錯收到兩邊的資料）→ 重播前先把真的 publisher 關掉。
- 錄你的輸出來自己檢查：`ros2 bag record -o out /result` → 跑完 → `ros2 bag info out` 看筆數對不對。

## 7. 兩個 node（或兩個容器）看不到對方

| 變數 | 作用 | 實測結果（兩個容器在同一個 docker bridge 網路） |
|---|---|---|
| 都不設 | 預設 domain 0、`ROS_AUTOMATIC_DISCOVERY_RANGE=SUBNET` | ✅ 收得到 |
| `ROS_DOMAIN_ID=5` vs 沒設 | 不同 domain = 不同的世界 | ❌ 收不到（`echo` 一直等到 timeout） |
| 兩邊都 `ROS_DOMAIN_ID=5` | | ✅ 收得到 |
| 兩邊都 `ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST` | 只找同一台機器（同一個容器）上的 node | ❌ 跨容器收不到；✅ 同一個容器內收得到 |
| `LOCALHOST` + `ROS_STATIC_PEERS=<對方 IP>` | 指定要連的 IP | ✅ 跨容器收得到 |
| `ROS_LOCALHOST_ONLY=1` | **Jazzy 已經不建議用** | 印出 `ROS_LOCALHOST_ONLY is deprecated but still honored`，效果同 LOCALHOST |

檢查順序：
```bash
printenv | grep -E "ROS_DOMAIN_ID|ROS_AUTOMATIC_DISCOVERY_RANGE|ROS_STATIC_PEERS|ROS_LOCALHOST_ONLY|RMW_IMPLEMENTATION"
hostname -i                         # 容器的 IP（實測 172.17.0.2 / 172.17.0.3）
ros2 doctor --report | grep -A3 "RMW MIDDLEWARE"
```
- **每個終端機都要設一樣的值**（`export` 只影響目前這個 shell）。題目的 README / launch 檔 / `.gitlab-ci.yml` 可能有指定 `ROS_DOMAIN_ID`。
- 容器用 `--net=host` 啟動時，等於跟主機共用網路。

## 8. `ros2 topic list` 的結果是舊的：daemon

`ros2` 指令會透過背景的 daemon 查詢，daemon 會**快取**。實測：用 `kill -9` 砍掉發布 `/ghost` 的程式後，
等了 10 秒，`ros2 topic list` 還是列出 `/ghost`；用 `--no-daemon` 就沒有。
```bash
ros2 daemon stop            # The daemon has been stopped → 下一個 ros2 指令會自動重新啟動它
ros2 topic list             # 實測 /ghost 消失了
ros2 topic list --no-daemon # 不用快取，直接查（比較慢）
ros2 daemon status
```
也會發生在：改了 `ROS_DOMAIN_ID` 之後，看到的還是舊 domain 的東西 → 也是 `ros2 daemon stop`。

## 9. 其他實測的坑

| 症狀 | 原因 |
|---|---|
| `pkill -f demo_nodes` 把自己的 shell 也砍掉了（exit 143） | `-f` 比對整行指令，你的 bash 指令也包含那個字 → 用更精確的字，例如 `pkill -f lib/demo_nodes_py` |
| `ros2 topic echo` 一直沒輸出 | 沒有 publisher / QoS 不合 / domain 不同 → `ros2 topic info -v` |
| 改了參數檔沒效果 | yaml 裡的 node 名稱跟實際的不一樣（被 `-r __node:=` 改過名字） |
| `ros2 run` 出現 `No executable found` | 見 [`cmake.md`](cmake.md) §5 |

## 10. 速查：一個 node 沒反應時的 5 個指令

```bash
ros2 node list                       # 1. 它有在跑嗎？名字對嗎？
ros2 node info /processor            # 2. 它訂閱 / 發布了哪些 topic？
ros2 topic info -v /input            # 3. 兩端都有嗎？QoS 一樣嗎？
ros2 topic hz /input                 # 4. 輸入有在進來嗎？多快？
ros2 run pkg exe --ros-args --log-level processor:=debug   # 5. 看它自己的 debug 訊息
```
