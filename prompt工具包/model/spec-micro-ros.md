# 規格卡：micro-ROS on Pico 2（預製程式碼/micro-ros/）
> 用法：一次只複製一張卡（兩條分隔線之間），貼進對話；模型要看程式時，照卡片最後一行請操作者貼。每張 ≤ 1200 字元。
> 來源：預製程式碼/說明書/04-micro-ros.md、預製程式碼/micro-ros/ 程式本身（行號已逐一核對）｜最後更新 2026-11-13

---

【規格卡｜UROS 1/9｜總覽：檔案、概念、驗證狀態】
以下是正確的參考資料（預製程式碼 2026-11-13 版）。和你的記憶不同時，以這張為準。
資料夾 `預製程式碼/micro-ros/`（ROS 2 Jazzy、Pico 2）：
| 檔案 | 行數 | 做什麼 |
|---|---|---|
| `README.md` | 166 | 概念、§3 排查表、§4 大小限制、§5 加速、§6 RP2350 |
| `agent_cheatsheet.md` | 81 | agent 指令、多板子、權限、`ros2 topic` 檢查 |
| `CMakeLists.txt` | 61 | 官方寫法 + `APP_SRC` 選檔 → `app.uf2` |
| `pico_pingpong.c` | 160 | `/microROS/ping`、`/microROS/pong` + 重連狀態機 |
| `pico_array_compute.c` | 123 | 主範本：收 Int32MultiArray → `compute()` → 發回 |
| `pico_dualcore_micro_ros.c` | 113 | core0 跑 micro-ROS、core1 算後半 |
| `host_driver.py` | 131 | 電腦端 rclpy：切塊分給 N 塊板子、依 job_id 合併、計時、對答案 |
概念：
- client = Pico 上的 rclc 程式 + 預編 `libmicroros.a`（Micro XRCE-DDS）。
- agent = 電腦上的 `micro_ros_agent`，在 USB 序列埠（XRCE-DDS）和 DDS 之間翻譯。板子的 node/pub/sub 是請 agent 代建 → agent 沒開，什麼都建不起來。
- 1 塊板子 = 1 個 agent = 1 個序列埠。
- namespace：node 的 ns `pico0` + 相對名稱 `"input"` → `/pico0/input`。每塊板子不同 ns，host 才能指定送給誰。
選檔：陣列運算 → `pico_array_compute.c` + `host_driver.py`；ping-pong → `pico_pingpong.c`；運算很重 → `pico_dualcore_micro_ros.c` + `host_driver.py`。
驗證狀態：3 支 .c 在 pico2 編譯、連結通過；沒燒錄、沒在板子上跑、沒接 agent。`host_driver.py` 只用假 rclpy 測過邏輯。cheatsheet 指令沒實測。
要看程式：請操作者貼「cat -n README.md | sed -n 12,41p」

---

【規格卡｜UROS 2/9｜CMakeLists.txt：build、APP_SRC 切換】
以下是正確的參考資料（預製程式碼 2026-11-13 版）。和你的記憶不同時，以這張為準。
在官方 repo `micro_ros_raspberrypi_pico_sdk`（jazzy）資料夾裡 build（要用它的 `libmicroros/`、`pico_uart_transport.c`）；在 `預製程式碼/micro-ros/` 直接 build 會失敗。
```bash
export PICO_SDK_PATH=~/pico-sdk   # 要含 lib/tinyusb
cp CMakeLists.txt CMakeLists.official.txt
cp <repo>/預製程式碼/micro-ros/{CMakeLists.txt,pico_*.c} .
sed -i 's/^set(APP_SRC .*)/set(APP_SRC pico_array_compute.c)/' CMakeLists.txt
mkdir -p build && cd build && cmake -DPICO_BOARD=pico2 .. && make -j4
cp app.uf2 /media/$USER/RP2350/   # 按住 BOOTSEL 插 USB
```
成功：`[100%] Built target app`，產 `build/app.uf2`。
| 名稱 | 行號 | 值 / 注意 |
|---|---|---|
| `PICO_BOARD` | 15 | `pico2`（舊 Pico：`pico`）；換了要 `rm -rf build` |
| `APP_SRC` | 28 | `pico_array_compute.c`（預設）/ `pico_pingpong.c` / `pico_dualcore_micro_ros.c` |
| 連結 | 35-39 | `pico_stdlib pico_unique_id pico_multicore microros` |
| CRLF ×3 | 49-51 | 全 0（二進位封包不能補 `\r`） |
- 換 `APP_SRC` 後直接 `make -j4`，不用重跑 cmake。
- `APP_SRC` ↔ `MERGE` 成對：`pico_array_compute.c` ↔ `host_driver.py:24` `MERGE = "sorted"`；`pico_dualcore_micro_ros.c` ↔ `"concat"`。只改一邊會造成 `correct=False`。
要看程式：請操作者貼「cat -n CMakeLists.txt | sed -n 11,53p」

---

【規格卡｜UROS 3/9｜agent 指令、裝置路徑、topic 檢查】
以下是正確的參考資料（預製程式碼 2026-11-13 版）。和你的記憶不同時，以這張為準。
（`agent_cheatsheet.md`，指令沒實測。）一塊板子一個終端機：
- docker（`:9-10`）：`docker run -it --rm -v /dev:/dev --privileged --net=host microros/micro-ros-agent:jazzy serial --dev /dev/ttyACM0 -b 115200`
- colcon（`:13-15`）：source `/opt/ros/jazzy/setup.bash` 和 `~/microros_ws/install/local_setup.bash`（`:14` TODO 你的 workspace），再 `ros2 run micro_ros_agent micro_ros_agent serial --dev /dev/ttyACM0 -b 115200`
- `--dev/-D` 必填；`-b` 寫多少都一樣（USB CDC）；`-v6` 印每個封包，測速時拿掉。
裝置路徑（`:30-31`）：
- `ls /dev/ttyACM*` → ttyACM0、ttyACM1…，插拔順序會變。
- `ls -l /dev/serial/by-id/` → 每塊板子固定名稱，多板子用這個。
- 兩個 agent 開同一個 port 會互搶資料 → 一個 port 一個 agent。
- 先只插一塊、開 agent、`ros2 topic list`，記下 by-id ↔ namespace。
權限：`Permission denied` → `sudo usermod -aG dialout $USER`（重登）或 `sudo chmod 666 /dev/ttyACM0`。被占用 → `sudo lsof /dev/ttyACM0`。
檢查（陣列版預期）：
- `ros2 topic list` → `/pico0/input`、`/pico0/output`
- `ros2 topic info /pico0/input -v` → RELIABLE
- `ros2 topic pub --once /pico0/input std_msgs/msg/Int32MultiArray "{data: [7, 3, 1, 2]}"` → 排序版回 `[7, 1, 2, 3]`，平方版 `[7, 9, 1, 4]`
要看程式：請操作者貼「cat -n agent_cheatsheet.md | sed -n 7,81p」

---

【規格卡｜UROS 4/9｜rclc 建立順序、handle 數、訊息大小上限】
以下是正確的參考資料（預製程式碼 2026-11-13 版）。和你的記憶不同時，以這張為準。
建立順序（3 支共通）：
```text
rmw_uros_set_custom_transport(true, NULL, open, close, write, read)
rmw_uros_ping_agent(...)   等 agent
rclc_support_init(&support, 0, NULL, &allocator)
rclc_node_init_default(&node, 名稱, namespace, &support)
rclc_publisher_init_* / rclc_subscription_init_*
rclc_timer_init_default2(...)   只有 pingpong
rclc_executor_init(&executor, &support.context, handle數, &allocator)
rclc_executor_add_subscription / add_timer
while (1) rclc_executor_spin_some(...)
```
- handle 數 = timer 數 + subscription 數（publisher 不算）：pingpong 3（`pico_pingpong.c:97`）、陣列 1（`pico_array_compute.c:115`）、雙核 1（`pico_dualcore_micro_ros.c:106`）。加了 sub/timer 沒加大 → `add_*` 失敗。
- 每板上限：1 node、10 pub、5 sub、1 service、1 client。
大小（預編 libmicroros：MTU 512 B、STREAM_HISTORY 4）：
| QoS | 一則上限 | int32 個數（含 job_id） |
|---|---|---|
| reliable（`_default`） | 512×4−12 = 2036 B | ≈ 505 |
| best_effort | 512−12 = 500 B | ≈ 121 |
- Int32MultiArray ≈ 16 + 4×元素數 B。規則：`CHUNK + 1 ≤ MAX_LEN（400）≤ 傳輸上限`。
- 超過傳輸上限：板子收不到；板子發太大 → `rcl_publish` 回錯誤（被忽略）。
- 沒超過傳輸上限、但 > MAX_LEN：callback 照叫、`data.size == 0` → 範本不回（上限是推算值，沒實測）。
要看程式：見各列的行號

---

【規格卡｜UROS 5/9｜pico_array_compute.c：函式、job_id 協定】
以下是正確的參考資料（預製程式碼 2026-11-13 版）。和你的記憶不同時，以這張為準。
協定（和 `host_driver.py` 約好）：
```text
收 /<BOARD_NS>/input ：data[0] = job_id，data[1..n] = 資料
回 /<BOARD_NS>/output：data[0] = 同一個 job_id，data[1..out_n] = 結果
```
| 名稱 | 行號 | 做什麼 / 注意 |
|---|---|---|
| `BOARD_NS` | 17 | `"pico0"`；TODO 每塊板子燒錄前改 pico0/pico1/… |
| `MAX_LEN` | 27 | 400；TODO capacity，含 job_id，≥ CHUNK+1 |
| `error_loop()` | 30-32 | LED 快閃；`RCCHECK` 失敗進這裡，要按 reset |
| `in_buf`/`out_buf` | 43 | `static int32_t[MAX_LEN]`（主 stack 只有 2 KB） |
| `compute(in, n, out, cap)` | 46-55 | TODO 你的運算（範例插入排序），回傳輸出個數 |
| `sub_cb()` | 57-70 | size<1 就 return → compute 寫進 out_buf[1..] → out_buf[0]=job_id → size=out_n+1 → `rcl_publish` |
| `alloc_msgs()` | 75-91 | `.data=buf; .capacity=MAX_LEN; .size=0`；`layout.dim` capacity 0 |
| `main()` | 93-123 | 等 agent（102）→ node `compute_node`、ns BOARD_NS（106）→ sub `"input"`、pub `"output"`（111-112，reliable）→ executor 1 handle（115） |
- LED：不亮 = 等 agent；恆亮 = OK；快閃 = 建立失敗。
- 沒有重連：重開後要按 reset。
- host 填 `layout.dim` 會造成整則丟掉 → host 只填 `data`。
- 換運算：`compute()`、`host_compute()`（`host_driver.py:38-42`）、`MERGE` 一起改。
要看程式：請操作者貼「cat -n pico_array_compute.c | sed -n 46,70p」

---

【規格卡｜UROS 6/9｜pico_dualcore_micro_ros.c：雙核心】
以下是正確的參考資料（預製程式碼 2026-11-13 版）。和你的記憶不同時，以這張為準。
規則：rcl / rclc / rmw 呼叫只能在 core0；core1 只做純運算，不碰 micro-ROS、不 printf（libmicroros 非執行緒安全）。
| 名稱 | 行號 | 做什麼 / 注意 |
|---|---|---|
| `BOARD_NS` / `MAX_LEN` | 24 / 25 | `"pico0"` / 400，同陣列版 TODO |
| `task_t` | 34 | `{lo, hi}`：給 core1 的範圍 [lo, hi) |
| `q_task` / `q_done` | 35 / 36 | core0→core1（task_t）/ core1→core0（hi 當完成訊號），深度 4 |
| `compute_range(in,out,lo,hi)` | 44-47 | TODO 純運算（範例平方）；兩核都呼叫，不用全域暫存 |
| `core1_main()` | 51-58 | 等 q_task → 算 → 放 q_done |
| `sub_cb()` | 60-75 | n=size−1、mid=1+n/2；[mid,1+n) 給 core1、core0 算 [1,mid)；等 q_done；out_buf[0]=job_id；size=n+1；publish |
| `main()` | 77-112 | queue_init（85-86）→ `multicore_launch_core1`（87）→ 綁 sequence（90-94）→ 等 agent（96）→ node `dual_node`（100）→ executor 1 handle（106） |
int32 平方（45-46）：`out[i] = (int32_t)((uint32_t)in[i] * (uint32_t)in[i])`。|x| > 46340 照 int32 繞回（46341² → −2147479015），不是未定義行為；`host_compute`（`host_driver.py:40-41`）也照 int32 繞回 → `correct=True`。要真正的平方 → 換 Int64MultiArray。
- 每派 1 個 task 就要取 1 次 q_done，否則卡死。core1 stack 2 KB → 不開大區域陣列。
- 搭配 `MERGE = "concat"`。瓶頸在 USB 時雙核沒用。
要看程式：請操作者貼「cat -n pico_dualcore_micro_ros.c | sed -n 44,75p」

---

【規格卡｜UROS 7/9｜pico_pingpong.c：重連狀態機、板子 ID】
以下是正確的參考資料（預製程式碼 2026-11-13 版）。和你的記憶不同時，以這張為準。
絕對名稱 topic（ns 不影響）：`/microROS/ping`、`/microROS/pong`（`std_msgs/Header`）。
| 名稱 | 行號 | 值 / 做什麼 |
|---|---|---|
| `LED_PIN` / `PING_PERIOD_MS` | 23 / 25 | 25 / 2000（TODO） |
| `RCCHECK` | 28 | 失敗 `return false`（回去等 agent） |
| `ping_timer_cb` | 53-64 | frame_id=`"亂數_device_id"`、設 .size、發 ping |
| `ping_sub_cb` | 68-73 | 不是自己的 ping → 原封不動發 pong |
| `pong_sub_cb` | 75-79 | 自己的 pong → `pong_count++`（沒輸出） |
| `create_entities` | 81-103 | node `pingpong_node`（85，TODO 多板改名）；ping pub reliable，其餘 best_effort；3 handle（97） |
| `destroy_entities` | 105-117 | destroy timeout 設 0，全部 fini |
板子 ID（131-134）：`pico_get_unique_board_id()` 出廠序號算成 `device_id` → 每塊一定不同。
狀態機（138-158）：
```text
WAITING_AGENT 每500ms ping(100,1)成功 → AGENT_AVAILABLE
AGENT_AVAILABLE create 成功 → AGENT_CONNECTED
  失敗 → destroy → WAITING_AGENT
AGENT_CONNECTED 每200ms ping 失敗 → AGENT_DISCONNECTED
  連著 → 每圈 spin_some(10ms)
AGENT_DISCONNECTED destroy → WAITING_AGENT
```
LED 亮 = 已連上。測：`ros2 topic pub --once /microROS/ping std_msgs/msg/Header "{frame_id: 'host'}"` → pong 回 `frame_id: host`。
要看程式：請操作者貼「cat -n pico_pingpong.c | sed -n 81,158p」

---

【規格卡｜UROS 8/9｜host_driver.py：常數、run() 排程、重送】
以下是正確的參考資料（預製程式碼 2026-11-13 版）。和你的記憶不同時，以這張為準。
| 常數 | 行號 | 值 | 意思 |
|---|---|---|---|
| `N_BOARDS` | 21 | 2 | TODO；ns 必須是 pico0..pico{N-1} |
| `CHUNK` | 22 | 300 | TODO；CHUNK+1 ≤ MAX_LEN；reliable ≤ 504、BE ≤ 120 |
| `MERGE` | 24 | `"sorted"` | TODO；sorted = heapq k-way merge、concat = 依 job_id 串接 |
| `TIMEOUT_S` | 27 | 10.0 | run() 最多等幾秒 |
| `RESEND_S` | 28 | 1.0 | TODO；一塊送出幾秒沒回就重送 |
函式：`make_data` 31-35；`host_compute` 38-42；`__init__` 46-57（QoS RELIABLE 在 50；lambda `b=i`）；`on_result` 59-65；`send` 67-72（`data=[job_id]+chunk`）；`wait_boards` 74-82；`run` 84-114；`main` 117-127。
run() 排程：
```text
chunks 每 CHUNK 個一塊（3000/300 = 10 塊，job_id 0..9）
while 沒收齊 且 沒到 TIMEOUT_S:
  for 每塊板子 b:
    忙 且 送出 > RESEND_S → [WARN] 重送；沒結果就 todo.appendleft(job)
    丟掉 todo 前面已有結果的
    b 空閒 → send(b, todo.popleft())   # 每塊板子同時最多 1 塊
  rclpy.spin_once(1 ms)
依 job_id 排序後合併
```
- `on_result` 只在回的是「手上那一塊」才標空閒；重送後才到的舊回覆只存結果。
- `wait_boards` 等 input 有訂閱者且 output 有發佈者；計時不含它。
- RESEND_S 比板子算一塊的時間短會造成重算 → 調大。
成功：`boards=2 n=3000 chunk=300 time=… ms throughput=… KiB/s correct=True`
要看程式：請操作者貼「cat -n host_driver.py | sed -n 84,114p」

---

【規格卡｜UROS 9/9｜陷阱與驗證】
以下是正確的參考資料（預製程式碼 2026-11-13 版）。和你的記憶不同時，以這張為準。
| 症狀 | 原因 | 修法 |
|---|---|---|
| agent 沒反應、LED 不亮 | port 錯 / 沒權限 / 被占用 | by-id 路徑、dialout、`sudo lsof` |
| agent 連上但 `ros2 topic list` 沒板子的 topic | create 失敗（陣列版 LED 快閃）：handle 數不夠、超過實體上限、名稱不合法；ROS_DOMAIN_ID 不同；陣列版沒重連 | agent `-v6`；加大 handle 數；同 ROS_DOMAIN_ID；`ros2 topic list --no-daemon`；按 reset |
| topic 有、echo 收不到 | QoS 不合：best_effort 發佈 → reliable 訂閱收不到 | `ros2 topic echo --qos-reliability best_effort /topic`；兩端同 QoS（`host_driver.py:50`） |
| 大訊息沒回、`逾時！只收到 x/y 塊` | 訊息太大：CHUNK+1 > MAX_LEN 或 > 傳輸上限（505/121） | 調小 CHUNK，或加大 MAX_LEN（≤ 上限）重燒 |
| 板子完全不回 | host 填了 `layout.dim` | 只填 data |
| 收到空陣列 | 沒綁 capacity / 沒設 `.size` | 綁 buffer；publish 前設 size |
| `correct=False`、沒逾時 | `APP_SRC` ↔ `MERGE` 沒成對；host_compute ≠ 板子運算 | 兩邊一起改 |
| 每塊板子收同一塊 | BOARD_NS 一樣 | 每塊不同 |
| 雙核隨機當機 | core1 呼叫 rcl / printf | 移回 core0 |
| `undefined reference to __atomic_exchange_4` | M0+ 預編函式庫 | README.md §6 shim |
驗證：官方範例能動 → LED 恆亮 → `ros2 topic list` 有 `/pico0/input` → `topic pub --once` `[7, 3, 1, 2]` 回 `[7, 1, 2, 3]` → `python3 host_driver.py` 最後一行 `correct=True`。偶爾 `[WARN] … 重送` 但 `correct=True` 正常。
要看程式：請操作者貼「cat -n README.md | sed -n 43,72p」
