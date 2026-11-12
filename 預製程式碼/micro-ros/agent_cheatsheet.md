# micro-ROS Agent 速查表（ROS 2 Jazzy）

> ⚠ 指令來自官方文件（pico repo jazzy README、eProsima Agent CLI 文件），未在本機實際執行驗證。

## 1. 啟動 agent（一塊板子 = 一個 agent = 一個終端機）

```bash
# 方法 A：docker（官方 README 寫法）
docker run -it --rm -v /dev:/dev --privileged --net=host \
  microros/micro-ros-agent:jazzy serial --dev /dev/ttyACM0 -b 115200

# 方法 B：已用 colcon 編好 micro_ros_agent 套件
source /opt/ros/jazzy/setup.bash
source ~/microros_ws/install/local_setup.bash      # TODO(改這裡) 你的 workspace
ros2 run micro_ros_agent micro_ros_agent serial --dev /dev/ttyACM0 -b 115200

# 方法 C：snap（pico README 寫法；要先 sudo snap install micro-ros-agent）
# ⚠ 未驗證：snap 內的 ROS 版本不一定是 jazzy；序列埠權限可能要另外 snap connect。考場優先用 A/B。
micro-ros-agent serial --dev /dev/ttyACM0 -b 115200
```

- serial 參數（eProsima CLI）：`--dev/-D`（必填）、`--baudrate/-b`（預設 115200）、`-v 0~6`（預設 4）。
- `-v6`：最詳細 log（看得到每個封包），除錯用；跑速度測試時拿掉（log 會拖慢）。
- USB CDC 其實不看 baud rate，`-b 115200` 寫什麼都一樣快（USB Full Speed ≈ 12 Mbit/s 上限）。
- 看到 `session established` 之類的訊息 → 板子連上了。

## 2. 多塊板子

```bash
ls /dev/ttyACM*                 # ttyACM0, ttyACM1 ...（插拔順序會變！）
ls -l /dev/serial/by-id/        # 每塊板子有固定名稱（含序號），推薦用這個
```

```bash
# 終端機 1
ros2 run micro_ros_agent micro_ros_agent serial --dev /dev/serial/by-id/usb-Raspberry_Pi_Pico_XXXX-if00
# 終端機 2
ros2 run micro_ros_agent micro_ros_agent serial --dev /dev/serial/by-id/usb-Raspberry_Pi_Pico_YYYY-if00
```

- **建議一塊板子一個 agent**；絕對不能兩個 agent 開同一個 port（會搶資料）。
  （Agent 另有 `multiserial` 子指令可一次開多個 port，但沒驗證過、而且同一份韌體的
   client key 可能相同 → 不建議考場用。）
- 每塊板子燒錄前改 `BOARD_NS`（pico0 / pico1 …），不然 topic 名稱撞在一起。
- 記住「哪個 by-id ↔ 哪個 namespace」：先只插一塊、開 agent、`ros2 topic list` 確認。

## 3. 權限問題（Permission denied: /dev/ttyACM0）

```bash
groups                              # 有沒有 dialout？
sudo usermod -aG dialout $USER      # 加入後要「登出再登入」才生效
sudo chmod 666 /dev/ttyACM0         # 考場臨時解（重插會失效）
```

- 序列埠被別的程式占用（minicom、screen、Arduino IDE、另一個 agent）→ 先關掉。
  `sudo lsof /dev/ttyACM0` 看是誰。
- ModemManager 會亂碰 ttyACM：`sudo systemctl stop ModemManager`。

## 4. 檢查 topic

```bash
ros2 node list                      # 看得到 /pico0/compute_node 嗎？
ros2 topic list                     # /pico0/input /pico0/output
ros2 topic info /pico0/input -v     # 看 QoS（RELIABLE / BEST_EFFORT）跟發布者/訂閱者數
ros2 topic echo /pico0/output
ros2 topic hz /pico0/output         # 每秒幾則
ros2 topic bw /pico0/output         # 每秒幾 bytes（算 throughput 用）
ros2 topic pub --once /pico0/input std_msgs/msg/Int32MultiArray "{data: [7, 3, 1, 2]}"
```

- `topic echo` 什麼都沒有但 `topic list` 有 → 可能 QoS 不合。Jazzy 的 echo 會「依照已存在的
  publisher 自動選 QoS」（ros2topic echo.py choose_qos），但若 echo 先開、板子後上線，就會用
  預設 reliable → 收不到 best_effort 的發佈 → 明確指定：
  `ros2 topic echo --qos-reliability best_effort /topic`。
- `ros2 topic pub --once` 會自動等到至少 1 個訂閱者配對才發（`-w` 預設 1），不會發太早。
- docker agent 時 list 看得到、echo 收不到：試 `--ipc=host`，或 agent 加
  `-e FASTDDS_BUILTIN_TRANSPORTS=UDPv4`（Fast DDS 同機共享記憶體問題；未驗證，備案）。
- topic 完全沒出現 → agent 沒連上 / 板子卡在等 agent / `ROS_DOMAIN_ID` 不一樣
  （agent 那個終端機跟你下指令的終端機要同一個 `ROS_DOMAIN_ID`；docker 版要加
  `-e ROS_DOMAIN_ID=$ROS_DOMAIN_ID`）。
- 板子重開或 agent 重開後 topic 消失：用 `pico_pingpong.c` 的重連狀態機，或按 reset 重來。
