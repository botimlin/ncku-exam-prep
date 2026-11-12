# ros2/ 預製程式碼 (ROS 2 Jazzy + Pico 序列埠)

所有 `.py` 都要放在**同一個資料夾**執行 (它們會 `from frame import ...`)。
要改的地方都標了 `# TODO(改這裡)`，用 `grep -n "TODO(改這裡)" *.py` 一次找出來。

## 檔案 → 題目類型

| 檔案 | 什麼題目用 | 怎麼跑 |
|---|---|---|
| `node_template.py` | 「寫一個 node」「修這個 node」(訂閱→處理→發布) | `python3 node_template.py --ros-args -p in_topic:=/number -p out_topic:=/double` |
| `custom_msg_cheatsheet.md` | 要自訂 .msg、或要傳陣列 | 看文件 |
| `frame.py` | 主機↔Pico 封包 (AA 55 cmd seq len payload crc32) | `python3 frame.py` 自我測試 |
| `serial_bridge.py` | ROS topic 進 → 丟給 Pico 算 → 結果發回 topic | `python3 serial_bridge.py --ros-args -p port:=/dev/ttyACM0 -p batch_size:=0` |
| `multi_device.py` | 「用 2 塊板子平行加速」 | `python3 multi_device.py /dev/ttyACM0 /dev/ttyACM1` |
| `fake_pico.py` | 沒板子 / 板子壞了，先在電腦上測 | `python3 fake_pico.py -n 2 --link /tmp/ttyFAKE` |
| `bench.py` | 量一包多大最快 (要寫報告/優化) | `python3 bench.py /dev/ttyACM0` |

**先用 fake_pico 測主機端，再換真板子** — 出錯時才知道是主機還是 Pico 的問題。

## 改題目時的順序
1. 新 cmd：`frame.py` 加常數 → `fake_pico.py` 的 `handle()` 加運算 → bridge/multi_device 改送哪個 cmd 跟怎麼合併結果。
2. Pico buffer 比較小：改 `frame.py` 的 `CHUNK_BYTES`。
3. 序列埠找不到：`ls /dev/ttyACM*`；Docker 要 `--device /dev/ttyACM0`；權限不足 `sudo chmod 666 /dev/ttyACM0`。
4. 沒有 pyserial：`apt install python3-serial` 或 `pip install pyserial`。

## 量到的數字 (fake_pico, 參考用)
- serial_bridge 加總 20000 個數字：`batch_size:=1` (20000 包) **664 ms**；`batch_size:=0` (20 包) **1.9 ms**。
- multi_device 80 萬 bytes、模擬慢板子：1 個 port 836 ms → 2 個 port 420 ms。
- 真的 USB 每包來回大約 ≥1 ms，差距只會更大 → **一定要批次 + 二進位**。

---

## ros2 CLI 除錯小抄

```bash
source /opt/ros/jazzy/setup.bash          # 每開一個新終端機都要! (ros2: command not found 就是忘了)
ros2 node list                            # 有哪些 node 在跑
ros2 node info /processor                 # 這個 node 訂閱/發布了哪些 topic
ros2 topic list -t                        # 所有 topic + 型別
ros2 topic info /number                   # Publisher count / Subscription count
ros2 topic info -v /number                # 加 -v 看每一端的 QoS (Reliability / Durability)
ros2 topic echo /double                   # 看內容；--once 只看一筆；--field data 只看某欄位
ros2 topic hz /double                     # 每秒幾筆
ros2 topic bw /double                     # 每秒多少 bytes
ros2 topic pub --once /number std_msgs/msg/Int32 "{data: 21}"
ros2 topic pub -r 2 /number std_msgs/msg/Int32 "{data: 1}"      # 每秒 2 次一直發
ros2 topic pub --once /numbers std_msgs/msg/Int32MultiArray "{data: [1, 2, 3]}"
ros2 interface show std_msgs/msg/Int32MultiArray                # 看訊息有哪些欄位
ros2 param list /processor ; ros2 param get /processor factor
```
- `pub --once` **一直卡住不結束** = 它在等訂閱者，代表**沒有人訂閱這個 topic** → 多半是名字打錯。
- `ros2 topic info -v` 的 `History (Depth): UNKNOWN` 是正常的，不用管。

### topic 名字打錯 checklist (官方 demo 必考)
1. `ros2 topic list` — 有沒有兩個很像的 topic (`/double` vs `/doubel`、`/number` vs `number_`)？
2. `ros2 topic info /x` — Publisher count 或 Subscription count 是 0 → 那一端名字錯了。
3. 有沒有前面少 `/`？(`number` 會被加上 namespace，`/number` 不會)
4. 型別一樣嗎？同名不同型別 → 連不起來 (`ros2 topic list -t` 會看到同名兩種型別)。
5. 程式裡 publisher/subscriber 用的是參數嗎？檢查 `--ros-args -p` 或 launch 檔有沒有覆蓋。

### 兩個 publisher 發同一個 topic (官方 demo 思考題)
- `ros2 topic info` 會看到 Publisher count: 2；訂閱者會收到**兩邊交錯**的資料，ROS 不會報錯。
- 找出是誰：`ros2 topic info -v /x` 看每個 publisher 的 Node name，再 `ros2 node info`。

### QoS 不相容的症狀
- 現象：topic info 兩端都有，count 都 ≥1，但**完全收不到**；有時會印 `incompatible QoS` 警告。
- 規則：發布端 BEST_EFFORT + 訂閱端 RELIABLE → **收不到**。反過來 (發 RELIABLE、收 BEST_EFFORT) 可以。
- 規則：訂閱端 TRANSIENT_LOCAL + 發布端 VOLATILE → 收不到。
- 修法：把兩端改成一樣 (見 `node_template.py` 的 `QOS`)，或 CLI 加 `--qos-reliability best_effort`。

### colcon 套件 / ros2 run / ros2 launch
```bash
cd ~/ws && colcon build --symlink-install         # 在 workspace 根目錄 (有 src/ 的那層) 跑
colcon build --packages-select my_pkg             # 只編一個，比較快
source install/setup.bash                         # 每次 build 完都要 source! 不然找不到新套件
ros2 pkg list | grep my_pkg                        # 確認找得到
ros2 run my_pkg my_node --ros-args -p in_topic:=/number -r __node:=proc2   # -r 改名字/重新對應
ros2 launch my_pkg demo.launch.py                  # 一次開多個 node
```
- `ros2 run` 找不到執行檔 → Python 套件要在 `setup.py` 的 `entry_points` 加 `'my_node = my_pkg.my_node:main'`，然後重 build + source。
- 改了 Python 程式沒反應 → 沒用 `--symlink-install` 就要重 build。
- 最小 launch 檔：
```python
from launch import LaunchDescription
from launch_ros.actions import Node
def generate_launch_description():
    return LaunchDescription([
        Node(package='my_pkg', executable='my_node', name='processor',
             parameters=[{'in_topic': '/number'}], remappings=[('/double', '/out')]),
    ])
```
