# 第 4 章　micro-ros/：Pico 2 上跑 micro-ROS，電腦用 ROS 2 topic 分工給多塊板子

> 本章對應的檔案：`micro-ros/` 的 `README.md`、`agent_cheatsheet.md`、`CMakeLists.txt`、`pico_pingpong.c`、`pico_array_compute.c`、`pico_dualcore_micro_ros.c`、`host_driver.py`｜驗證狀態：3 支 Pico 程式在本 session 實際編譯、連結成功（pico2），`host_driver.py` 用假 rclpy 跑過邏輯；**沒有燒錄、沒有接 agent、沒有在板子上跑過**｜最後核對：2026-11-12（commit d102c17）

## 4.0 30 秒版：什麼時候打開這一章

- 題目出現 **micro-ROS、micro-ros-agent、rclc、XRCE-DDS、`/microROS/ping`、`/microROS/pong`、`std_msgs/Header`**，或要求「電腦用 ROS 2 topic 把資料送到 Pico 算再收回」→ 本章。
- 如果題目是「USB 序列埠 + 自己定義封包」，不是 micro-ROS → 看第 2 章（`ros2/serial_bridge.py`）和第 3 章（`pico/app_serial.c`）。
- **考場第一件事**：先用官方 repo 的 `pico_micro_ros_example.c` build + 燒錄 + 開 agent 一次，確認環境能動（`micro-ros/README.md:9`），再換成這裡的程式。
- 先開的檔案：要算陣列 → `pico_array_compute.c` + `host_driver.py`；要 ping-pong → `pico_pingpong.c`；運算很重 → `pico_dualcore_micro_ros.c`。
- 最常改的 3 個地方：
  1. `pico_array_compute.c:46` 的 `compute()`（你的運算）和 `host_driver.py:38` 的 `host_compute()`（對答案用）。
  2. `pico_array_compute.c:17` 的 `BOARD_NS`（每塊板子燒錄前改成 `pico0`、`pico1`…）和 `host_driver.py:21` 的 `N_BOARDS`。
  3. `CMakeLists.txt:28` 的 `APP_SRC` 和 `host_driver.py:24` 的 `MERGE`（**兩個要一起改**：`pico_array_compute.c` → `"sorted"`，`pico_dualcore_micro_ros.c` → `"concat"`）。
- 一則訊息的上限：reliable 一則最多 2036 B（≈ 505 個 int32，含 `job_id`），best_effort 500 B（≈ 121 個 int32）；範本 `MAX_LEN=400`、`CHUNK=300`。

## 4.1 檔案總表

| 檔案 | 行數 | 做什麼 | 什麼時候用 | 驗證狀態 |
|---|---|---|---|---|
| `README.md` | 166 | 概念、流程、錯誤排查表、訊息大小限制、加速清單、Pico 2 支援狀態、去年題目簡答、審查紀錄 | 卡住時先查 §3 排查表、§4 大小限制 | 文件；數字對過官方標頭檔 |
| `agent_cheatsheet.md` | 81 | 啟動 agent（docker / colcon / snap）、多板子、權限、`ros2 topic` 檢查指令 | 開 agent、找序列埠、topic 看不到時 | ⚠️ 指令全部沒有實測（容器裡沒有 ROS 2） |
| `CMakeLists.txt` | 61 | 官方 CMakeLists 加上 `PICO_BOARD` 預設、`APP_SRC` 選檔、`pico_multicore` | 每次 build | ✅ 本 session 3 支程式都編譯、連結成功 |
| `pico_pingpong.c` | 160 | `/microROS/ping`、`/microROS/pong`（`std_msgs/Header`）+ agent 斷線重連狀態機 | 去年的 Ping-Pong 題；要抄重連機制時 | ✅ 編譯、連結；⚠️ 沒在板子上跑 |
| `pico_array_compute.c` | 123 | 收 `Int32MultiArray` → `compute()`（範例：插入排序）→ 發回；示範 sequence 記憶體配置 | 「電腦送資料、Pico 算、送回」的主範本 | ✅ 編譯、連結；`compute()` 在 host 測過；⚠️ 沒在板子上跑 |
| `pico_dualcore_micro_ros.c` | 113 | core0 跑 micro-ROS，core1 用 queue 幫忙算後半（範例：平方） | 運算時間遠大於傳輸時間時 | ✅ 編譯、連結；`compute_range()` 在 host 測過；⚠️ 沒在板子上跑 |
| `host_driver.py` | 131 | 電腦端 rclpy 節點：切塊、分給 N 塊板子、照 `job_id` 合併、計時、對答案 | 搭配上面兩支陣列程式 | ⚠️ 沒有用真的 rclpy 跑；用假 rclpy 跑過 7 種情境（4.3.7） |

## 4.2 先懂這些概念

### 4.2.1 micro-ROS 是什麼

- **ROS 2**：電腦上的程式（叫 **node**，節點）透過 **topic**（有名字的資料頻道）互相傳訊息。一個 node 用 **publisher**（發佈者）往 topic 送，另一個 node 用 **subscription**（訂閱）收。底層協定是 **DDS**（走 UDP 網路，功能多、很吃記憶體）。
- **Pico 2 的 RAM 只有 520 KB**，跑不動完整的 DDS。所以 micro-ROS 換成 **Micro XRCE-DDS**：一個精簡版協定，板子只當「client（客戶端）」，把重活交給電腦上的 **agent（代理程式）**。
- **micro-ROS client**：跑在 Pico 上，就是你寫的 `.c` 加上預編好的 `libmicroros.a`。C API 叫 **rclc**（電腦上對應的是 rclpy / rclcpp）。
- **micro-ROS agent**：跑在電腦上的「翻譯官」。一邊用 XRCE-DDS 透過 USB 序列埠跟板子講話，一邊在 DDS 世界裡「代替板子」建立 node、publisher、subscription。所以電腦上 `ros2 topic list` 看得到板子的 topic，`rclpy` 程式可以直接 pub/sub，不需要知道對面是 MCU。
- 板子上呼叫 `rclc_node_init_default()`、`rclc_publisher_init_default()` 時，其實是「送請求給 agent，請 agent 幫忙建立」。**agent 沒開，板子什麼都建不起來**，所以每支程式一開始都先 `rmw_uros_ping_agent()` 等 agent。

```text
 Pico 2（client）                         電腦
 ┌─────────────────────────┐  USB CDC    ┌──────────────────┐  DDS(UDP)   ┌──────────────────────┐
 │ 你的 .c（rclc API）       │  序列埠     │ micro-ros-agent   │ ─────────> │ ros2 topic echo/pub   │
 │ libmicroros.a            │ <────────> │ (XRCE-DDS ↔ DDS) │ <───────── │ host_driver.py(rclpy) │
 │ pico_uart_transport.c    │ /dev/ttyACM0└──────────────────┘            └──────────────────────┘
 └─────────────────────────┘
```

### 4.2.2 序列埠傳輸（transport）

- Pico 的 USB 接到電腦後會變成一個序列埠（USB CDC，Linux 上是 `/dev/ttyACM0`、`/dev/ttyACM1`…）。
- 官方 `pico_uart_transport.c` 提供 4 個函式：`pico_serial_transport_open`（第一次呼叫 `stdio_init_all()`）、`_close`（什麼都不做）、`_write`（逐位元組 `putchar()`）、`_read`（逐位元組 `getchar_timeout_us()`，逾時就停）。也就是說 **micro-ROS 的封包和 `printf` 走同一條 USB stdio**。
- 每支程式第一行都是 `rmw_uros_set_custom_transport(true, NULL, open, close, write, read)`。第 1 個參數 `true` = 開啟 XRCE **framing**（標頭檔註解：「Enable XRCE framing」）。序列埠只是一串位元組，沒有「一包」的邊界，framing 會在每包前後加旗標位元組（`UXR_FRAMING_BEGIN_FLAG 0x7E`、跳脫字元 `0x7D`，見 `libmicroros/include/uxr/client/profile/transport/stream_framing/stream_framing_protocol.h:24`）讓 agent 切得出封包。
- **所以不能 `printf`**：字元會混進封包串流；agent 那邊看不到你的字，framing 可能丟掉或弄壞封包（`README.md:53`，⚠️未驗證是哪一種）。除錯只能看 LED，或改用 UART0 + USB-TTL 線。
- **baud rate 沒有意義**：USB CDC 不看 baud，agent 的 `-b 115200` 寫什麼都一樣（`agent_cheatsheet.md:24`）。
- CMake 把 stdio 的 CRLF 轉換關掉（`CMakeLists.txt:49`–`51`），否則送 `\n`（0x0A）時 SDK 會自動補 `\r`，二進位封包就壞了。

### 4.2.3 為什麼每塊板子要自己的 agent、自己的 namespace

- **一個序列埠只能被一個程式打開讀**。兩個 agent 開同一個 port 會互搶位元組，兩邊都壞（`agent_cheatsheet.md:41`）。所以 N 塊板子 = N 個 agent = N 個終端機，各自 `--dev` 指到自己的 `/dev/serial/by-id/...`。
- 所有 agent 都加入同一個 DDS domain（同一個 `ROS_DOMAIN_ID`），所以電腦上看到的是「一張圖」：每塊板子的 topic 都在裡面。
- **namespace（命名空間）** 是 topic 名稱前面的資料夾。板子程式訂閱的是相對名稱 `"input"`、發佈 `"output"`；node 的 namespace 設 `pico0` → 實際 topic 變成 `/pico0/input`、`/pico0/output`；設 `pico1` → `/pico1/input`。
- 不分 namespace 的後果：大家都訂閱同一個 `/input`，host 送一塊資料**每塊板子都會收到、都會算、都會回**，沒有加速，而且 host 會收到重複的 `job_id`（`host_driver.py:6`–`9` 的註解）。
- node 名稱可以一樣（都叫 `compute_node`），因為完整名稱是 `/pico0/compute_node`、`/pico1/compute_node`，不會撞。
- **例外：`pico_pingpong.c` 用的是絕對名稱** `"/microROS/ping"`（開頭有 `/`），namespace 不會加上去。這是故意的：ping-pong 就是要所有板子共用同一個 topic 互相回應。

### 4.2.4 QoS：reliable 和 best_effort

- **QoS（Quality of Service）** 決定訊息遺失時要不要重送。
- **reliable**（可靠）：要 ACK，掉了會重送；板子端 `rcl_publish` 會等 agent 確認才返回（`pico_array_compute.c:68` 的註解，依據 rmw_microxrcedds `rmw_publish.c`）。可以傳比較大的訊息（多個 MTU 片段）。`rclc_*_init_default()` = reliable。
- **best_effort**（盡力而為）：不等 ACK，掉了就掉了；比較快，但一則只能放 1 個 MTU。`rclc_*_init_best_effort()`。
- 配對規則：**reliable 發佈 → best_effort 訂閱：可以收**；**best_effort 發佈 → reliable 訂閱：收不到**（QoS 不相容）。所以兩端最好用同一種。
- `host_driver.py:50` 用 `ReliabilityPolicy.RELIABLE`，配合板子的 `_default`。

### 4.2.5 訊息大小限制（`README.md` §4）

預編 `libmicroros.a` 的實際設定（本 session 用 `grep` 在 `$S/uros/libmicroros/include` 核對過）：

| 常數 | 值 | 位置 | 意思 |
|---|---|---|---|
| `UXR_CONFIG_CUSTOM_TRANSPORT_MTU` | 512 | `uxr/client/config.h:60` | 一個傳輸封包最多 512 B |
| `RMW_UXRCE_STREAM_HISTORY_INPUT` / `_OUTPUT` | 4 | `rmw_microxrcedds_c/config.h:43`–`44` | reliable 串流的緩衝格數 |
| `RMW_UXRCE_MAX_HISTORY` | 4 | `rmw_microxrcedds_c/config.h:49` | 每個訂閱暫存幾則（不是大小上限） |
| `RMW_UXRCE_MAX_INPUT_BUFFER_SIZE` | MTU × 4 = 2048 | `rmw_microxrcedds_c/config.h:50` | 收訊息緩衝 |
| `RMW_UXRCE_MAX_NODES` / `PUBLISHERS` / `SUBSCRIPTIONS` / `SERVICES` / `CLIENTS` | 1 / 10 / 5 / 1 / 1 | `colcon.meta:43`–`47` | 每塊板子的實體數上限 |

官方公式（micro.ros.org「Middleware Configuration」，`README.md:61`–`62`）：

```text
best_effort 一則 ≤ MTU − 12         = 512 − 12     = 500 B
reliable    一則 ≤ MTU × HISTORY − 12 = 512 × 4 − 12 = 2036 B

Int32MultiArray 序列化（CDR）大小 ≈ 16 + 4 × 元素數
  4 B  CDR 封裝頭
  4 B  layout.dim 的長度（0）
  4 B  layout.data_offset
  4 B  data 的長度
  4 B × 元素數（含 data[0] 的 job_id）

best_effort：(500 − 16) / 4  = 121 個 int32（含 job_id）→ CHUNK ≤ 120
reliable   ：(2036 − 16) / 4 = 505 個 int32（含 job_id）→ CHUNK ≤ 504
```

⚠️未驗證：16 B overhead 和 2036 B 上限是照文件與 CDR 規則推算，沒有在板子上實測邊界。考場要逼近上限時，先用 4.4.6 的方法實際試。

`CHUNK`、`MAX_LEN` 和這些上限的關係：

```text
host_driver.py CHUNK + 1(job_id)  ≤  板子 MAX_LEN（capacity，預設 400）  ≤  傳輸上限（reliable 505 / best_effort 121）
```

超過時發生什麼（行為不一樣，要分清楚；`pico_array_compute.c:23`–`26`）：

| 情況 | 結果 |
|---|---|
| 板子**收**的訊息超過傳輸上限 | 板子收不到，callback 不會被叫 → host 等到逾時 |
| 板子**發**的訊息超過傳輸上限 | `rcl_publish` 回傳錯誤（範本用 `RCSOFTCHECK` 忽略）→ host 收不到 |
| 沒超過傳輸上限，但元素數 > `capacity`（`MAX_LEN`） | callback **會被叫**，但 `data.size == 0` → 範本直接 `return`，不回覆 → host 等到逾時 |
| `layout.dim` 個數 > dim 的 capacity（範本是 0） | 巢狀 sequence 反序列化失敗，整則丟掉 → **host 送訊息時不能填 `layout.dim`** |

要更大的上限：改 `microros_static_library/library_generation/colcon.meta`（`-DRMW_UXRCE_STREAM_HISTORY=8`，必須是 2 的次方；`-DUCLIENT_CUSTOM_TRANSPORT_MTU=1024`），再用 docker `microros/micro_ros_static_library_builder:jazzy` 重編 libmicroros（`README.md:68`–`71`）。⚠️沒有實測，而且需要網路和很多時間，考場優先「切小塊」。

### 4.2.6 MCU 上沒有 malloc：sequence 要先給記憶體

- `Int32MultiArray` 的 `data` 欄位型別是 `rosidl_runtime_c__int32__Sequence`，有三個欄位：`.data`（指標）、`.size`（目前幾個）、`.capacity`（最多幾個）。字串（`rosidl_runtime_c__String`，例如 `Header.frame_id`）也一樣。
- micro-ROS 收訊息時是「反序列化進你給的記憶體」，**不會幫你 malloc**。所以 `capacity = 0`（全域變數預設值）時，任何陣列都收不進來（`size` 變 0）。
- 做法：開靜態陣列，然後 `msg.data.data = buf; msg.data.capacity = N; msg.data.size = 0;`（`pico_array_compute.c:76`–`77`）。
- 發訊息前要自己設 `.size`，忘了設 → 送出空陣列（`README.md:52`）。
- 大型物件放全域，不要放 stack：Pico 2 主 stack 只有 2 KB（`PICO_STACK_SIZE` = `0x800`，pico-sdk 2.2.0 `src/rp2350/pico_platform/include/pico/platform.h:45`）。

### 4.2.7 rclc 物件的建立順序（3 支程式共通）

```text
rmw_uros_set_custom_transport(...)     設定傳輸（USB 序列埠）
rmw_uros_ping_agent(...)               等 agent（沒有 agent 就停在這）
allocator = rcl_get_default_allocator()
rclc_support_init(&support, ...)       建立 context（和 agent 的 session）
rclc_node_init_default(&node, 名稱, namespace, &support)
rclc_publisher_init_*/rclc_subscription_init_*(..., type_support, topic名稱)
rclc_timer_init_default2(...)          （只有 pingpong 有 timer）
executor = rclc_executor_get_zero_initialized_executor()
rclc_executor_init(&executor, &support.context, handle數, &allocator)
rclc_executor_add_subscription / add_timer
while (1) rclc_executor_spin_some(&executor, timeout_ns)   處理收到的訊息、到期的 timer
```

- **executor（執行器）**：負責「有新資料時呼叫你的 callback」。`handle 數` = timer 數 + subscription 數（publisher 不算）。數少了 → `rclc_executor_add_*` 回傳錯誤。
- `rclc_executor_spin_some(exec, timeout_ns)`：等最多 `timeout_ns` 看有沒有事，有就執行 callback。範本用 1 ms（陣列版）或 10 ms（pingpong）。
- 每支程式都自己定義 `RCCHECK` / `RCSOFTCHECK`（函式庫沒提供）。`rcl_*` 函式有 warn-unused-result，`RCSOFTCHECK` 用變數接住回傳值避免警告。

### 4.2.8 Pico 2（RP2350）支援狀態（`README.md` §6）

- 官方 `micro_ros_raspberrypi_pico_sdk` 的 README **只寫支援 Pico（RP2040）**；RP2350 支援的 issue #1482 仍是 open（`README.md:87`）。
- 預編 `libmicroros.a` 用 `-march=armv6-m -mcpu=cortex-m0plus` 編譯（本 session 核對：`microros_static_library/library_generation/toolchain.cmake:26`）。
- Pico 2 的 ARM 核心是 Cortex-M33（ARMv8-M Mainline），指令集包含 ARMv6-M，ABI 相容 → **能連結**。本 session 實測：3 支程式都連結成功，最終 ELF 的屬性是 `Tag_CPU_arch: v8-M.mainline`，裡面只有 `__atomic_exchange_8` / `__atomic_load_8` / `__atomic_store_8`，**沒有** `__atomic_*_4` → `README.md` §6 的 atomic 補丁不需要。
- ⚠️未驗證：**能不能在板子上正常跑**。沒有燒錄、沒有官方保證。萬一連結出現 `undefined reference to __atomic_exchange_4`，照 `README.md:96`–`103` 加 `atomic_shim.c`；再不行就照 `README.md:104`–`106` 的 Plan B（重編函式庫，或不用 micro-ROS，改用第 2、3 章的自訂序列埠協定）。

## 4.3 逐檔說明

### 4.3.1 `README.md`

#### 用途

資料夾的總說明。內容依序：驗證狀態（第 3–10 行）、檔案表（12–20）、§1 概念（22–32）、§2 流程（34–41）、§3 錯誤排查（43–55）、§4 訊息大小限制（57–72）、§5 throughput 優化清單（74–84）、§6 Pico 2 支援狀態（86–106）、§7 去年練習題簡答（108–127）、參考來源（129–132）、設計審查紀錄（134–166）。

#### 怎麼編譯 / 執行

不用編譯。考場上當查表用。

#### 對外介面

| 段落 | 行號 | 什麼時候查 |
|---|---|---|
| §2 流程 | 34–41 | 第一次 build + 燒錄 + 開 agent |
| §3 錯誤排查 | 43–55 | 任何「沒反應」「收不到」「topic 沒出現」 |
| §4 訊息大小 | 57–72 | 決定 `CHUNK` / `MAX_LEN`、大訊息不見 |
| §5 加速清單 | 74–84 | 題目要 throughput、完成後要優化 |
| §6 Pico 2 | 86–106 | 連結錯誤、被問「Pico 2 有沒有支援」 |
| §7 去年題目 | 108–127 | 題目問 micro-ROS 和 ROS 2 的關係、資料型態限制、Linux vs 實體差異 |

§5 加速清單重點（`README.md:75`–`84`）：用二進位 MultiArray 不要用字串；能用 `UInt8MultiArray` 就用（小 4 倍）；每則塞到接近上限；多板子平行；運算重才用雙核心；`spin_some` timeout 設小；agent 不要開 `-v6`、host 不要每則都 print；小訊息可容忍掉包才用 best_effort；`set_sys_clock_khz` 超頻（Pico 2 預設 150 MHz）；先用 `ros2 topic hz/bw`、`time.perf_counter()` 量。

§7 去年題目的答案要點（考試可能再問）：
- micro-ROS = 把 ROS 2 的 rcl/rclc API 搬到 MCU，中介層換成 Micro XRCE-DDS；裝置 = MCU 跑 client、電腦跑 agent + ROS 2 node。
- Host ↔ MCU：MCU 用 C + rclc；Host 用 rclpy / rclcpp 一般節點 pub/sub 同一個 topic，agent 自動轉發；傳輸層是 USB CDC 序列埠（也可 UART / UDP）。
- 資料型態限制：沒有動態記憶體 → sequence 要先配置；有大小上限；實體數有上限；自訂 `.msg` 要放 `library_generation/extra_packages/` 並重編 libmicroros。
- Linux 版 vs 實體板子：Linux 直接編譯執行、能 printf / gdb、transport 是 UDP；實體要交叉編譯、燒 .uf2、序列埠 transport、不能在同一條 USB printf、要處理斷線重連、多板子分 port 和 namespace。

#### 要改的地方

無 `TODO(改這裡)`。

#### 實際執行輸出

不適用（文件）。本章核對過 §4 的常數（見 4.2.5）和 §6 的結論（見 4.2.8）。

#### 常見錯誤

| 症狀 | 原因 | 修法 |
|---|---|---|
| §3 表格寫「上限：1 node、10 pub、5 sub」但 pingpong 用了 2 pub + 2 sub | 沒有矛盾，都在上限內 | 不用改 |

### 4.3.2 `agent_cheatsheet.md`

#### 用途

開 agent、處理多板子、權限、檢查 topic 的指令。**全部沒有在這個容器實測**（沒有 ROS 2、沒有板子）；檔案第 3 行也這樣標註。

#### 怎麼編譯 / 執行

在電腦端終端機執行（考場的 ROS 2 Jazzy 環境）。每塊板子開一個終端機跑一個 agent，另開終端機下 `ros2` 指令。

啟動 agent 的三種方法（`agent_cheatsheet.md:7`–`19`）：

```bash
# 方法 A：docker（官方 README 寫法）。--privileged + -v /dev:/dev 讓容器看得到序列埠；--net=host 讓 DDS 能和主機上的 ros2 互通
docker run -it --rm -v /dev:/dev --privileged --net=host \
  microros/micro-ros-agent:jazzy serial --dev /dev/ttyACM0 -b 115200

# 方法 B：已用 colcon 編好 micro_ros_agent 套件
source /opt/ros/jazzy/setup.bash
source ~/microros_ws/install/local_setup.bash      # TODO(改這裡) 你的 workspace
ros2 run micro_ros_agent micro_ros_agent serial --dev /dev/ttyACM0 -b 115200

# 方法 C：snap（要先 sudo snap install micro-ros-agent）。⚠ snap 內的 ROS 版本不一定是 jazzy，考場優先用 A/B
micro-ros-agent serial --dev /dev/ttyACM0 -b 115200
```

預期看到（依 cheatsheet 第 25 行）：板子連上時 agent 印出 `session established` 之類的訊息。⚠️未驗證確切字樣。

#### 對外介面

agent `serial` 子指令參數（`agent_cheatsheet.md:22`，來源 eProsima Agent CLI 文件）：

| 參數 | 意思 | 注意 |
|---|---|---|
| `--dev` / `-D` | 序列埠裝置路徑 | 必填；多板子用 `/dev/serial/by-id/...` |
| `--baudrate` / `-b` | baud rate，預設 115200 | USB CDC 不看 baud，寫多少都一樣 |
| `-v 0`～`-v 6` | log 詳細程度，預設 4 | `-v6` 會印每個封包，除錯用；測速時拿掉 |
| `multiserial` | 一個 agent 開多個 port | ⚠️未驗證；同一份韌體的 client key 可能相同 → 考場不建議 |

裝置路徑（`agent_cheatsheet.md:30`–`31`）：

| 指令 | 看什麼 |
|---|---|
| `ls /dev/ttyACM*` | `ttyACM0`、`ttyACM1`…（**插拔順序會變**） |
| `ls -l /dev/serial/by-id/` | 每塊板子固定名稱（含序號），推薦用這個 |

檢查 topic（`agent_cheatsheet.md:62`–`68`）：

| 指令 | 用途 | 陣列範本預期看到（⚠️未實測） |
|---|---|---|
| `ros2 node list` | node 有沒有建立 | `/pico0/compute_node`（雙核心版是 `/pico0/dual_node`） |
| `ros2 topic list` | topic 有沒有出現 | `/pico0/input`、`/pico0/output` |
| `ros2 topic info /pico0/input -v` | QoS、發佈者 / 訂閱者數 | Reliability: RELIABLE |
| `ros2 topic echo /pico0/output` | 看板子回什麼 | — |
| `ros2 topic hz /pico0/output` | 每秒幾則 | — |
| `ros2 topic bw /pico0/output` | 每秒幾 bytes | — |
| `ros2 topic pub --once /pico0/input std_msgs/msg/Int32MultiArray "{data: [7, 3, 1, 2]}"` | 手動送一塊 | 排序版回 `data: [7, 1, 2, 3]`；雙核心平方版回 `[7, 9, 1, 4]`（依程式邏輯推得） |

pingpong 版（`pico_pingpong.c:6`–`9`）：

```bash
ros2 topic echo /microROS/ping          # 每 2 秒看到板子的 ping，frame_id 像 "12345_678"
ros2 topic pub --once /microROS/ping std_msgs/msg/Header "{frame_id: 'host'}"
ros2 topic echo /microROS/pong          # 板子回 frame_id: host 的 pong
```

#### 程式流程

建議順序（`agent_cheatsheet.md:44`–`45`）：

1. 一次只插一塊板子 → `ls -l /dev/serial/by-id/` 記下名稱。
2. 開 agent 指向該名稱 → `ros2 topic list` 確認是 `/pico0/...` → 記下「by-id ↔ namespace」對應。
3. 插第二塊，重複。

#### 要改的地方

| 行號 | 現在的值 | 意思 | 什麼情況要改、改成什麼 |
|---|---|---|---|
| `agent_cheatsheet.md:14` | `source ~/microros_ws/install/local_setup.bash` | 方法 B 的 micro_ros_agent workspace | 改成考場實際編好 agent 的 workspace 路徑；用 docker（方法 A）就不需要這行 |

#### 實際執行輸出

沒有實測。原因：容器裡沒有 ROS 2、沒有 docker 映像、沒有板子（規範禁止安裝 ROS 2）。

#### 常見錯誤

| 症狀 | 原因 | 修法 |
|---|---|---|
| `Permission denied: /dev/ttyACM0` | 使用者不在 `dialout` 群組 | `sudo usermod -aG dialout $USER` 後登出再登入；臨時解 `sudo chmod 666 /dev/ttyACM0`（重插失效） |
| agent 開了沒反應 | port 被 minicom / screen / 另一個 agent 占用；ModemManager 亂碰 | `sudo lsof /dev/ttyACM0` 找出來關掉；`sudo systemctl stop ModemManager` |
| `topic list` 有、`echo` 沒東西 | QoS 不合：echo 先開、板子後上線時 echo 用預設 reliable，收不到 best_effort | `ros2 topic echo --qos-reliability best_effort /topic` |
| docker agent：list 看得到、echo 收不到 | Fast DDS 同機共享記憶體問題（⚠️未驗證） | docker 加 `--ipc=host`，或 `-e FASTDDS_BUILTIN_TRANSPORTS=UDPv4` |
| topic 完全沒出現 | agent 沒連上 / 板子卡在等 agent / `ROS_DOMAIN_ID` 不同 | 兩個終端機 `echo $ROS_DOMAIN_ID` 要一樣；docker 加 `-e ROS_DOMAIN_ID=$ROS_DOMAIN_ID` |
| 板子或 agent 重開後 topic 消失 | 陣列範本沒有重連機制 | 按板子 reset / 重插；或抄 `pico_pingpong.c` 的狀態機 |
| 兩塊板子的 topic 撞名 | 兩塊燒了同一個 `BOARD_NS` | 燒錄前改 `BOARD_NS`（4.4.3） |

### 4.3.3 `CMakeLists.txt`

#### 用途

照官方 jazzy 分支的 `CMakeLists.txt` 改的。跟官方的差別只有 4 個（`CMakeLists.txt:3`）：`PICO_BOARD` 預設 `pico2`、`APP_SRC` 選要編哪個 `.c`、多連 `pico_multicore`、target 名稱叫 `app`（所以產物是 `build/app.uf2`）。

#### 怎麼編譯 / 執行

**前提**：要有官方 repo `micro_ros_raspberrypi_pico_sdk`（jazzy 分支），裡面有 `libmicroros/`（含預編 `libmicroros.a`，本 session 看到的大小 14,056,780 B）、`pico_uart_transport.c`、`pico_uart_transports.h`。本章的 `$S/uros` 就是它（commit `339ae3f`「micro-ROS jazzy Library auto-update 06-12-2025」）。

考場步驟（在你放官方 repo 的資料夾執行；`<repo>` 換成 `ncku-exam-prep` 的路徑）：

```bash
# 0) 取得官方 repo（⚠ 考場若沒網路，看主辦方有沒有提供；本 session 用的是事先 clone 好的 $S/uros）
git clone -b jazzy https://github.com/micro-ROS/micro_ros_raspberrypi_pico_sdk.git
cd micro_ros_raspberrypi_pico_sdk

# 1) pico-sdk 路徑（要含 lib/tinyusb，否則沒有 USB stdio）
export PICO_SDK_PATH=~/pico-sdk                 # 改成考場實際路徑
ls $PICO_SDK_PATH/lib/tinyusb | head -1        # 有東西才對

# 2) 備份官方 CMakeLists，放入本資料夾的檔案
cp CMakeLists.txt CMakeLists.official.txt
cp <repo>/預製程式碼/micro-ros/CMakeLists.txt .
cp <repo>/預製程式碼/micro-ros/pico_*.c .

# 3) 選要編哪支（也可以直接用編輯器改第 28 行）
sed -i 's/^set(APP_SRC .*)/set(APP_SRC pico_array_compute.c)/' CMakeLists.txt
grep -n '^set(APP_SRC' CMakeLists.txt          # 預期：28:set(APP_SRC pico_array_compute.c)

# 4) build（Pico 2）
mkdir -p build && cd build
cmake -DPICO_BOARD=pico2 ..
make -j4
ls -l app.uf2

# 5) 燒錄：按住 BOOTSEL 插 USB → 出現 RP2350 磁碟
cp app.uf2 /media/$USER/RP2350/                # 舊 Pico 是 RPI-RP2
```

- **換程式**：只要改 `CMakeLists.txt:28` 再 `make -j4`，不用重跑 cmake（CMakeLists 變了，make 會自己重新 configure）。本 session 實測：同一個 build 資料夾換 `APP_SRC` 後 `make` 1 秒內就完成。
- **換程式時 `host_driver.py:24` 的 `MERGE` 要一起改**（`CMakeLists.txt:27`）。

#### 對外介面

| 名稱 | 行號 | 值 | 效果 / 注意 |
|---|---|---|---|
| `cmake_minimum_required` | 11 | 3.13 | 官方寫 3.12；pico-sdk 2.x 要 ≥ 3.13 |
| `PICO_BOARD` | 15 | `pico2`（CACHE） | 要在 `include(pico_sdk_import.cmake)` 之前；命令列 `-DPICO_BOARD=` 會蓋過；pico2 → 平台自動是 `rp2350-arm-s`（Cortex-M33） |
| `include(...pico_sdk_import.cmake)` | 17 | 用 `$ENV{PICO_SDK_PATH}` | 沒設環境變數 → cmake 直接失敗 |
| `project(app C CXX ASM)` | 19 | — | target 名稱 `app` |
| `APP_SRC` | 28 | `pico_array_compute.c` | 要編的程式 |
| `link_directories(libmicroros)` | 30 | — | 找 `libmicroros.a` |
| `add_executable(app ${APP_SRC} pico_uart_transport.c)` | 31–34 | — | transport 檔名是單數 `transport.c`，header 是複數 `transports.h` |
| `target_link_libraries` | 35–39 | `pico_stdlib`、`pico_unique_id`（pingpong 的板子序號）、`pico_multicore`、`microros` | `microros` = `libmicroros/libmicroros.a`；`pico_multicore` 非雙核心版連了也沒差 |
| `target_include_directories` | 40 | `libmicroros/include` | rcl/rclc/std_msgs 標頭都在這 |
| `-ffunction-sections -fdata-sections` | 42–43 | — | 搭配連結時 `--gc-sections` 丟掉沒用到的函式（例如需要 `__atomic_*_4` 的 `rcl_timer_exchange_callback`） |
| `pico_enable_stdio_usb(app 1)` / `_uart(app 0)` | 46–47 | — | micro-ROS 走 USB CDC |
| CRLF 三個定義 | 49–51 | 全部 0 | 二進位封包不能被補 `\r` |
| `pico_add_extra_outputs(app)` | 53 | — | 產生 `app.uf2`、`app.bin`、`app.hex`、`app.dis` |

#### 程式流程

1. 設 `PICO_BOARD`（15）→ 2. 匯入 SDK（17）→ 3. `project`、C11 / C++17（19–21）→ 4. `pico_sdk_init()`（23）→ 5. 建 `app` 執行檔、連函式庫（30–40）→ 6. 編譯旗標（42–43）→ 7. stdio 設定（46–51）→ 8. 產生 uf2（53）。第 55–61 行是 Pico 2 注意事項註解。

#### 要改的地方

| 行號 | 現在的值 | 意思 | 什麼情況要改、改成什麼 |
|---|---|---|---|
| `CMakeLists.txt:6` | `#   export PICO_SDK_PATH=~/pico-sdk` | 註解中的用法：pico-sdk 路徑 | 不用改檔；在終端機 `export PICO_SDK_PATH=<考場 pico-sdk 路徑>`（要含 `lib/tinyusb`） |
| `CMakeLists.txt:15` | `set(PICO_BOARD pico2 CACHE STRING "Board type")` | 預設板子 | 舊 Pico（RP2040）改 `pico`，或命令列 `-DPICO_BOARD=pico`；Pico 2 W 改 `pico2_w`（⚠️ W 版 LED 不是 GP25） |
| `CMakeLists.txt:25`（實際值在 28） | `set(APP_SRC pico_array_compute.c)` | 要編哪支 | `pico_pingpong.c` / `pico_array_compute.c` / `pico_dualcore_micro_ros.c`；改了要同步改 `host_driver.py:24` 的 `MERGE` |

#### 實際執行輸出

環境：x86_64 容器、4 核、cmake 3.28.3、arm-none-eabi-gcc 13.2.1（13.2.rel1）、pico-sdk 2.2.0（`$S/pico-sdk`）、官方 repo jazzy commit `339ae3f`（`$S/uros`）。做法：把 `$S/uros` 複製成 `$S/ch04/uros_<app>/`，放入本資料夾的 `CMakeLists.txt` 和 `.c`，用 `sed` 改 `APP_SRC`，`cmake -DPICO_BOARD=pico2 .. && make -j4`。

cmake 輸出重點（`$S/ch04/uros_pico_pingpong/build/cmake.log`）：

```text
Target board (PICO_BOARD) is 'pico2'.
Auto-converting non-specific PICO_PLATFORM='rp2350' to 'rp2350-arm-s'
Defaulting platform (PICO_PLATFORM) to 'rp2350-arm-s' based on PICO_BOARD setting.
-- Defaulting build type to 'Release' since not specified.
Defaulting compiler (PICO_COMPILER) to 'pico_arm_cortex_m33_gcc' since not specified.
CMake Warning at .../pico-sdk/tools/Findpicotool.cmake:30 (message):
  No installed picotool with version 2.1.1 found - building from source
Downloading Picotool
```

- 這個 picotool 警告是 pico-sdk 的，不是本資料夾的問題。這個容器有網路所以自動下載、編譯 picotool 成功；**考場沒網路時這一步可能失敗** → 處理方式見第 3 章（pico/ 的 build）與第 8 章。

結果（3 支都 `make` 回傳 0，最後一行 `[100%] Built target app`）：

| APP_SRC | cmake + make 時間 | `app.uf2` | `app.bin` | text | bss | 預設 build 的警告 |
|---|---|---|---|---|---|---|
| `pico_pingpong.c` | 28 s | 221,696 B | 110,508 B | 114,604 | 26,132 | 0 |
| `pico_array_compute.c` | 25 s | 223,744 B | 111,568 B | 115,664 | 29,260 | 0 |
| `pico_dualcore_micro_ros.c` | 24 s | 225,280 B | 112,256 B | 116,352 | 29,292 | 0 |

- text / bss 來自 `arm-none-eabi-size app.elf`（單位 B）。bss 是 26,132–29,292 B，Pico 2 SRAM 520 KB，記憶體很寬裕；陣列版比 pingpong 多 3,128 B，主要是 `in_buf` + `out_buf`（2 × 400 × 4 = 3,200 B；pingpong 自己有 3 個 50 B 字串 buffer 等，所以差值略小）。
- UF2 檢查（自己寫的 Python 讀 UF2 區塊）：三個檔各 433 / 437 / 440 個 512 B 區塊；family ID 有 `0xe48bff59`（RP2350 ARM-S）和 `0xe48bff57`，第一個區塊位址 `0x10ffff00`（pico-sdk 對 RP2350 額外加的一個「absolute」區塊）。
- `arm-none-eabi-readelf -A app.elf`：`Tag_CPU_arch: v8-M.mainline`。`arm-none-eabi-nm app.elf | grep atomic`：只有 `__atomic_exchange_8`、`__atomic_load_8`、`__atomic_store_8`，沒有 `_4` 版。
- 換 `APP_SRC` 的流程也實測（`$S/ch04/uros_switch/`）：先 build `pico_array_compute.c`（26 s），`sed` 改成 `pico_pingpong.c` 再 `make` → 1 s，`app.uf2` 221,696 B；再改 `pico_dualcore_micro_ros.c` → `make` 0–1 s，225,280 B。大小和獨立 build 一致。

加 `-Wall -Wextra` 的結果（`CFLAGS="-Wall -Wextra" cmake -DPICO_BOARD=pico2 ..`，只編 app 的 `.o`；注意：用 `-DCMAKE_C_FLAGS=` 會蓋掉 SDK 的 `-mcpu` 旗標，組譯器會報 `mcrr` 指令錯誤，要用 `CFLAGS` 環境變數）：

```text
pico_pingpong.c:33:5: warning: this 'if' clause does not guard... [-Wmisleading-indentation]
   32 |     if (t_ == -1) t_ = now_; if (now_ - t_ > (MS)) { X; t_ = now_; } } while (0)
pico_pingpong.c:142:13: note: in expansion of macro 'EVERY_N_MS'
（同一個警告在 146:13 再出現一次）
```

`pico_array_compute.c`、`pico_dualcore_micro_ros.c`：0 個警告。

#### 常見錯誤

| 症狀 | 原因 | 修法 |
|---|---|---|
| `CMake Error ... pico_sdk_import.cmake` 找不到 | 沒 `export PICO_SDK_PATH` | `export PICO_SDK_PATH=...` 後刪掉 `build/` 重來 |
| `Cannot find source file: pico_uart_transport.c` 或找不到 `libmicroros` | 本資料夾的檔案沒放進官方 repo，而是在 `預製程式碼/micro-ros/` 裡直接 build | 照上面步驟複製到官方 repo 資料夾 |
| 換了 `-DPICO_BOARD` 沒效果 | 舊的 `build/CMakeCache.txt` 留著 | `rm -rf build` 重來 |
| `undefined reference to __atomic_exchange_4` | 預編函式庫是 M0+ 版（本 session 沒出現） | `README.md` §6 的 `atomic_shim.c` |
| host 顯示 `correct=False` | 換了 `APP_SRC` 沒改 `MERGE` | 4.6 已知問題 1 |
| picotool 下載失敗（沒網路） | pico-sdk 2.x 預設要 picotool 產生 uf2 | 見第 3 章；或用考場已安裝的 picotool |

### 4.3.4 `pico_pingpong.c`

#### 用途

去年 Linux 練習題的 Ping-Pong 搬到 Pico（`pico_pingpong.c:3`–`4`）：

- timer 每 2 秒發一則 `/microROS/ping`（`std_msgs/Header`，`frame_id = "亂數_裝置ID"`）。
- 收到**別人**的 ping → 原封不動發到 `/microROS/pong`。
- 收到**自己** ping 的 pong → `pong_count++`。
- 含 agent 斷線重連狀態機（照官方 `micro-ros_reconnection_example`）。

#### 怎麼編譯 / 執行

`CMakeLists.txt:28` 改成 `set(APP_SRC pico_pingpong.c)`，`make -j4`，燒錄，開 agent，然後用 4.3.2 的 pingpong 指令測。LED 亮 = 已連上 agent。

#### 對外介面

| 名稱 | 行號 | 型別 / 參數 | 效果 / 注意 |
|---|---|---|---|
| `LED_PIN` | 23 | 25 | Pico / Pico 2 板載 LED = GP25（pico-sdk `boards/pico2.h:38` 也是 25） |
| `STR_CAP` | 24 | 50 | `frame_id` buffer 大小，最多 49 字元 + `'\0'` |
| `PING_PERIOD_MS` | 25 | 2000 | ping 週期 |
| `RCCHECK(fn)` | 28 | — | 出錯 `return false`（給 `create_entities` 用，讓狀態機回去等 agent） |
| `RCSOFTCHECK(fn)` | 30 | — | 忽略錯誤 |
| `EVERY_N_MS(MS, X)` | 32–33 | — | 每隔 `MS` 毫秒才執行 `X` 一次；每個展開處有自己的 `static t_`；第一次呼叫只記時間，`MS` 毫秒後才第一次執行 |
| 全域物件 | 36–42 | `support`、`node`、`allocator`、`executor`、`timer`、`ping_pub`、`pong_pub`、`ping_sub`、`pong_sub` | 放全域避免 2 KB stack 不夠 |
| 訊息與 buffer | 46–47 | `out_ping`、`in_ping`、`in_pong` + 3 個 `char[STR_CAP]` | `frame_id` 字串要先綁 buffer |
| `state` | 50 | `WAITING_AGENT` / `AGENT_AVAILABLE` / `AGENT_CONNECTED` / `AGENT_DISCONNECTED` | 重連狀態機 |
| `ping_timer_cb(rcl_timer_t *t, int64_t last_call_time)` | 53 | timer callback | 填 `frame_id` 和時間戳，發 ping |
| `ping_sub_cb(const void *msgin)` | 68 | subscription callback | 不是自己的 ping → 發 pong |
| `pong_sub_cb(const void *msgin)` | 75 | subscription callback | 是自己 ping 的 pong → 計數 |
| `bool create_entities(void)` | 81 | 回傳是否全部成功 | 建立 support → node → 2 pub → 2 sub → timer → executor |
| `void destroy_entities(void)` | 105 | — | 全部 fini |

#### 程式流程

`main()`（`pico_pingpong.c:119`）：

1. `rmw_uros_set_custom_transport(true, NULL, pico_serial_transport_open, ...)`（121–123）：設定 USB 序列埠傳輸，開 framing。
2. LED 腳位設輸出（124–125）。
3. 把 3 個 Header 的 `frame_id` 綁到靜態 buffer（128–130）：`.data = buf; .capacity = STR_CAP; .size = 0`。只做一次，重連不用重做。
4. 讀板子出廠的 8 byte 唯一序號（`pico_get_unique_board_id()`），算成 `device_id`，再 `srand(device_id)`（131–134）：每塊板子的 ID 一定不同。2026-11-12 前是用開機微秒數，兩塊板子同時上電時可能撞號。
5. 狀態機（138–158），每圈最後 `gpio_put(LED_PIN, state == AGENT_CONNECTED)`：

```text
WAITING_AGENT ──每 500 ms ping(100 ms, 1 次) 成功──> AGENT_AVAILABLE
AGENT_AVAILABLE ──create_entities() 成功──> AGENT_CONNECTED
                └─失敗──> destroy_entities()，回 WAITING_AGENT
AGENT_CONNECTED ──每 200 ms ping(100 ms, 1 次)；成功就保持──> 每圈 spin_some(10 ms)
                └─ping 失敗──> AGENT_DISCONNECTED
AGENT_DISCONNECTED ──destroy_entities()──> WAITING_AGENT
```

- 第 142 行：`EVERY_N_MS(500, state = (rmw_uros_ping_agent(100, 1) == RMW_RET_OK) ? AGENT_AVAILABLE : WAITING_AGENT);`
- 第 149–150 行：每 200 ms 檢查一次 agent；只要還連著，**每圈**都 `rclc_executor_spin_some(&executor, RCL_MS_TO_NS(10))`（`if` 在巨集外面）。

`create_entities()`（81–103），照順序：

| 行 | 呼叫 | 說明 |
|---|---|---|
| 82 | `allocator = rcl_get_default_allocator()` | 預設記憶體配置器 |
| 83 | `rclc_support_init(&support, 0, NULL, &allocator)` | 建立 context / session |
| 85 | `rclc_node_init_default(&node, "pingpong_node", "", &support)` | namespace 空字串 |
| 86 | `ROSIDL_GET_MSG_TYPE_SUPPORT(std_msgs, msg, Header)` | 訊息型別 |
| 88 | `rclc_publisher_init_default(&ping_pub, ..., "/microROS/ping")` | ping 用 reliable 發 |
| 89 | `rclc_publisher_init_best_effort(&pong_pub, ..., "/microROS/pong")` | pong 用 best_effort 發 |
| 90–91 | `rclc_subscription_init_best_effort(&ping_sub / &pong_sub, ...)` | 兩個訂閱都 best_effort（BE 訂閱可以收 reliable 發佈）；QoS 安排照官方 freertos_apps ping_pong |
| 93–94 | `rclc_timer_init_default2(&timer, &support, RCL_MS_TO_NS(PING_PERIOD_MS), ping_timer_cb, true)` | 最後的 `true` = 建立後立刻開始計時；舊的 `rclc_timer_init_default` 在 jazzy 已 deprecated（`rclc/timer.h:61`） |
| 96 | `executor = rclc_executor_get_zero_initialized_executor()` | — |
| 97 | `rclc_executor_init(&executor, &support.context, 3, &allocator)` | **handle 數 3 = 1 timer + 2 subscription** |
| 98–100 | `add_timer`、`add_subscription(&ping_sub, &in_ping, &ping_sub_cb, ON_NEW_DATA)`、`add_subscription(&pong_sub, &in_pong, ...)` | `ON_NEW_DATA` = 有新資料才呼叫 |
| 101 | `(void)rmw_uros_sync_session(1000)` | 跟 agent 對時，失敗也沒關係；成功後 `rmw_uros_epoch_millis()` 才是真實時間 |

callback 細節：

- `ping_timer_cb`（53–64）：`snprintf(out_ping.frame_id.data, STR_CAP, "%d_%d", rand(), device_id)`；`.size = strlen(...)`（不含 `'\0'`，要自己設）；`stamp` 由 `rmw_uros_epoch_millis()` 換成秒 + 奈秒；`pong_count = 0`；`rcl_publish(&ping_pub, &out_ping, NULL)`。
- `ping_sub_cb`（68–73）：`size == 0` 就 return（字串超過 capacity 時 typesupport 會把 size 設 0，但 callback 照叫）；`strcmp` 跟自己最後一次發的 `frame_id` 不同 → 把收到的訊息原封不動 `rcl_publish(&pong_pub, m, NULL)`。板子會收到自己的 ping（同一個 topic），靠這個 `strcmp` 不回自己。
- `pong_sub_cb`（75–79）：`frame_id` 和自己的一樣 → `pong_count++`。`pong_count` 只計數，**沒有送出或顯示**；題目要回報時要自己加（例如另開一個 publisher）。

`destroy_entities()`（105–117）：先 `rmw_uros_set_context_entity_destroy_session_timeout(rmw_ctx, 0)`（agent 已經不在，不要等），再依序 fini：2 pub → 2 sub → timer → executor → node → support。

#### 要改的地方

| 行號 | 現在的值 | 意思 | 什麼情況要改、改成什麼 |
|---|---|---|---|
| `pico_pingpong.c:23` | `#define LED_PIN 25` | 板載 LED 腳位 | Pico / Pico 2 不用改；Pico W / Pico 2 W 的 LED 接在無線晶片上，不是 GP25（要改用 `pico_cyw43_arch` 的 API，⚠️未驗證） |
| `pico_pingpong.c:25` | `#define PING_PERIOD_MS 2000` | ping 週期（毫秒） | 題目指定頻率時改，例如 10 Hz → `100` |
| `pico_pingpong.c:84`（實際值在 84） | `rclc_node_init_default(&node, "pingpong_node", "", &support)` | node 名稱 / namespace | 多塊板子時改成不同 node 名稱（例如 `"pingpong_pico0"`），避免 ROS 2 出現同名 node；topic 是絕對名稱，不受 namespace 影響 |

#### 實際執行輸出

- 編譯、連結：✅（4.3.3 表格，`app.uf2` 221,696 B）。
- `-Wall` 下 `EVERY_N_MS` 觸發 `-Wmisleading-indentation`（4.3.3 有原文）。
- 在板子上跑：沒有實測（沒有板子、沒有 agent）。

#### 常見錯誤

| 症狀 | 原因 | 修法 |
|---|---|---|
| LED 一直不亮 | 停在 `WAITING_AGENT`：agent 沒開、port 錯 | 4.3.2 常見錯誤 |
| LED 亮一下又滅、反覆 | `create_entities()` 某步失敗 → 拆掉重來；或 ping 不穩 | agent 開 `-v6` 看哪個 create 失敗 |
| 收得到 ping、看不到 pong | 只有一塊板子時，板子不回自己的 ping | 用 `ros2 topic pub --once /microROS/ping ...` 從電腦送一則 |
| `ros2 topic echo /microROS/pong` 收不到 | pong 是 best_effort；echo 先開時預設 reliable | `--qos-reliability best_effort` |
| 改了 executor handle 數以外的東西後 `add_*` 失敗 → 一直重連 | 新增 sub / timer 卻沒把第 97 行的 3 加大 | handle 數 = timer + subscription 數 |
| `-Wall` 出現 `misleading-indentation` | `EVERY_N_MS` 巨集寫在一行（外觀問題，不影響功能） | 可忽略；要消掉就把巨集裡第一個 `if` 加大括號 |

### 4.3.5 `pico_array_compute.c`

#### 用途

主範本：訂閱 `/<BOARD_NS>/input`（`Int32MultiArray`），呼叫 `compute()`，把結果發到 `/<BOARD_NS>/output`。協定跟 `host_driver.py` 約好（`pico_array_compute.c:5`–`6`）：

```text
收：data[0] = job_id（第幾塊）, data[1..n] = 資料
回：data[0] = 同一個 job_id,    data[1..out_n] = 結果
```

`job_id` 讓 host 能「照順序合併」多塊板子亂序回來的結果。只等一次 agent，**沒有重連**（`pico_array_compute.c:7`）。

#### 怎麼編譯 / 執行

`CMakeLists.txt:28` = `set(APP_SRC pico_array_compute.c)`（預設就是），`make -j4`，燒錄。LED 狀態：

| LED | 意思 |
|---|---|
| 不亮 | 還在第 102 行等 agent |
| 恆亮 | 全部建立成功，開始 spin（第 118 行） |
| 快閃（100 ms 亮、100 ms 滅） | 某個 `RCCHECK` 失敗，進了 `error_loop()`（第 30–32 行），要按 reset |

測試：`ros2 topic echo /pico0/output` 開著，另一個終端機 `ros2 topic pub --once /pico0/input std_msgs/msg/Int32MultiArray "{data: [7, 3, 1, 2]}"`，預期回 `data: [7, 1, 2, 3]`（⚠️未實測，依程式邏輯推得）。

#### 對外介面

| 名稱 | 行號 | 型別 / 參數 | 效果 / 注意 |
|---|---|---|---|
| `BOARD_NS` | 17 | `"pico0"` | node 的 namespace → topic 前綴 |
| `LED_PIN` | 18 | 25 | — |
| `MAX_LEN` | 27 | 400 | `in_buf` / `out_buf` 大小 = sequence capacity，**含 job_id** |
| `error_loop()` | 30–32 | — | 無限快閃 LED |
| `RCCHECK(fn)` | 33 | — | 失敗 → `error_loop()`（不是 return） |
| `RCSOFTCHECK(fn)` | 34 | — | 忽略錯誤 |
| 全域 | 36–43 | `support`、`node`、`allocator`、`executor`、`pub`、`sub`、`msg_in`、`msg_out`、`static int32_t in_buf[MAX_LEN], out_buf[MAX_LEN]` | 主 stack 只有 2 KB，buffer 不能放 stack |
| `compute(const int32_t *in, size_t n, int32_t *out, size_t cap)` | 46–55 | 輸入 `in[0..n-1]`，寫到 `out`，回傳輸出個數 | 範例：插入排序；`n > cap` 時只取前 `cap` 個 |
| `sub_cb(const void *msgin)` | 57–70 | subscription callback | 拆 job_id → compute → 組回 → publish |
| `alloc_msgs()` | 75–91 | — | 綁 buffer、dim capacity 0 |

#### 程式流程

`main()`（93–123）：

1. 設定 transport（94–96）、LED（97–98）。
2. `alloc_msgs()`（99）：
   - `msg_in.data.data = in_buf; .capacity = MAX_LEN; .size = 0`，`msg_out` 同樣綁 `out_buf`（76–77）。
   - `layout.dim` 給 `NULL` / capacity 0 / size 0（80–81）：`dim` 是巢狀 sequence，收到的 dim 個數 > capacity 會讓**整則訊息反序列化失敗** → host 端不能填 `layout.dim`。
   - `layout.data_offset = 0`（82）。
   - 83–90 行註解是另一種做法：`micro_ros_utilities_create_message_memory()` 自動配置（用 malloc，可以處理字串和巢狀欄位）。範本沒用。
3. `while (rmw_uros_ping_agent(1000, 1) != RMW_RET_OK) { tight_loop_contents(); }`（102）：每次最多等 1 秒，一直試到 agent 回應。所以先開板子或先開 agent 都可以。
4. `rclc_support_init`（105）→ `rclc_node_init_default(&node, "compute_node", BOARD_NS, &support)`（106）。
5. `rclc_subscription_init_default(&sub, &node, ts, "input")`（111）、`rclc_publisher_init_default(&pub, &node, ts, "output")`（112）：相對名稱 + namespace → `/pico0/input`、`/pico0/output`；`_default` = reliable。
6. `rclc_executor_init(&executor, &support.context, 1, &allocator)`（115）：**handle 數 1 = 1 個 subscription**（publisher 不算）。
7. `rclc_executor_add_subscription(&executor, &sub, &msg_in, &sub_cb, ON_NEW_DATA)`（116）：收到的資料會反序列化進 `msg_in`（也就是 `in_buf`）。
8. LED 亮（118），`while (true) rclc_executor_spin_some(&executor, RCL_MS_TO_NS(1));`（119–121）。

`sub_cb()`（57–70）：

| 行 | 做什麼 |
|---|---|
| 59 | `msgin` 就是 `&msg_in` |
| 60 | `data.size < 1` → return（空的，或超過 `MAX_LEN` 時 size 變 0） |
| 61 | `job_id = m->data.data[0]` |
| 62 | `n = size - 1`（資料個數） |
| 63 | `out_n = compute(&m->data.data[1], n, &out_buf[1], MAX_LEN - 1)`：結果直接寫進 `out_buf[1..]` |
| 65 | `out_n + 1 > capacity` 就截斷（size 絕對不能 > capacity，否則序列化越界） |
| 66–67 | `out_buf[0] = job_id`，`msg_out.data.size = out_n + 1` |
| 69 | `rcl_publish(&pub, &msg_out, NULL)`：reliable → 等 agent ACK 才返回 |

#### 要改的地方

| 行號 | 現在的值 | 意思 | 什麼情況要改、改成什麼 |
|---|---|---|---|
| `pico_array_compute.c:17` | `#define BOARD_NS "pico0"` | 這塊板子的 namespace | 每塊板子燒錄前改：第 1 塊 `pico0`、第 2 塊 `pico1`…，要跟 `host_driver.py` 的 `/pico{i}/` 一致 |
| `pico_array_compute.c:27` | `#define MAX_LEN 400` | 陣列 capacity（含 job_id） | `CHUNK + 1` 要 ≤ `MAX_LEN`；reliable 最大 505、best_effort 最大 121（4.2.5）；註解寫「保守取 ≤ 450」 |
| `pico_array_compute.c:45`（函式在 46） | `compute()` = 插入排序 | 你的運算 | 換成題目要的運算；輸出個數可以和輸入不同（例如 CRC 只回 1 個）；同時改 `host_driver.py` 的 `host_compute()` 和 `MERGE`（4.4.1） |

#### 實際執行輸出

- 編譯、連結：✅（`app.uf2` 223,744 B，`-Wall -Wextra` 0 警告）。
- `compute()` 在 host 上單獨測（把 `pico_array_compute.c:46`–`55` 用 `sed` 抽出來，加測試 `main`，host gcc 13.3.0、`-O2 -Wall -fsanitize=undefined`；檔案 `$S/ch04/ctest/t.c`）：

```text
sort n=8: -1000 -3 0 2 5 9 9 1000          ← 輸入 {5,-3,9,0,9,-1000,1000,2}
cap=4 n=4: -3 0 5 9                         ← cap=4：只排前 4 個輸入，其餘丟掉
```

- 在板子上跑：沒有實測。

#### 常見錯誤

| 症狀 | 原因 | 修法 |
|---|---|---|
| LED 快閃 | 建立 node / pub / sub / executor 失敗（名字不合法、超過實體數、handle 數不夠） | agent `-v6` 看錯誤；檢查新增的 sub 有沒有加大第 115 行的 handle 數 |
| 小陣列 OK，大陣列沒回應 | 超過 `MAX_LEN`（size 變 0 被忽略）或超過傳輸上限 | 4.4.6 |
| host 送的訊息板子完全沒反應 | host 填了 `layout.dim`（板子 dim capacity 0 → 整則丟掉） | host 只填 `data` |
| 回來的陣列是空的 | 自己改 `sub_cb` 時忘了設 `msg_out.data.size` | publish 前設 `.size` |
| 板子重開後要重開 agent / host | 這支沒有重連機制 | 抄 `pico_pingpong.c` 的狀態機，或按 reset |
| 自己改 compute 後當機 | 在 callback 裡開大區域陣列，爆 2 KB stack | 改成 `static` 或全域 |

### 4.3.6 `pico_dualcore_micro_ros.c`

#### 用途

同 `pico_array_compute.c` 的協定（`data[0] = job_id`），但運算切兩半：core0 算前半，core1 算後半。範例運算是逐元素平方。

**雙核心的鐵則**（`pico_dualcore_micro_ros.c:4`–`5`）：**所有 rcl / rclc / rmw 呼叫只能在 core0**。core1 只做純運算，不碰 micro-ROS、不 printf。原因：libmicroros 編譯時 `RCUTILS_NO_THREAD_SUPPORT=ON`（`colcon.meta:25`）、沒開 `UCLIENT_PROFILE_MULTITHREAD` → 不是執行緒安全的。

#### 怎麼編譯 / 執行

`CMakeLists.txt:28` 改成 `set(APP_SRC pico_dualcore_micro_ros.c)`（`pico_multicore` 已經在 `CMakeLists.txt:37` 連上），`make -j4`。**`host_driver.py:24` 改成 `MERGE = "concat"`**。手動測：`ros2 topic pub --once /pico0/input std_msgs/msg/Int32MultiArray "{data: [7, 3, 1, 2]}"` → 預期 `[7, 9, 1, 4]`（⚠️未實測）。

#### 對外介面

| 名稱 | 行號 | 型別 / 參數 | 效果 / 注意 |
|---|---|---|---|
| `BOARD_NS` | 24 | `"pico0"` | 同陣列版 |
| `MAX_LEN` | 25 | 400 | 同陣列版 |
| `task_t` | 34 | `{ uint32_t lo, hi; }` | 給 core1 的工作範圍 `[lo, hi)` |
| `q_task` | 35 | `queue_t` | core0 → core1，元素 `task_t`，深度 4 |
| `q_done` | 36 | `queue_t` | core1 → core0，元素 `uint32_t`（做完的 `hi`），當完成訊號 |
| `in_buf`、`out_buf` | 38 | `static int32_t[MAX_LEN]` | 兩核心共用（SRAM 共享） |
| `compute_range(in, out, lo, hi)` | 44–47 | 處理 `in[lo..hi)` 寫到 `out[lo..hi)` | 兩核心都會呼叫 → **不能用全域暫存變數** |
| `core1_main()` | 51–58 | — | 無限迴圈：等工作 → 算 → 回報 |
| `sub_cb()` | 60–75 | — | 切半、派工、自己算、等、publish |

#### 程式流程

`main()`（77–112）：

1. transport（78–80）、LED（81–82）。
2. `queue_init(&q_task, sizeof(task_t), 4)`、`queue_init(&q_done, sizeof(uint32_t), 4)`（85–86）。
3. `multicore_launch_core1(core1_main)`（87）：**queue 要先 init 好才能啟動 core1**。
4. 綁 sequence 記憶體、dim capacity 0（90–94），和陣列版 `alloc_msgs()` 一樣。
5. 等 agent（96）→ support（99）→ `rclc_node_init_default(&node, "dual_node", BOARD_NS, &support)`（100）→ sub `"input"`（103）、pub `"output"`（104）→ executor handle 數 1（106）→ add_subscription（107）→ LED 亮（109）→ spin_some 1 ms（110）。

`sub_cb()` 的切分（60–75）：

```text
msg_in.data.data == in_buf
index:  0        1 ........ mid-1 | mid ........ n
        job_id   core0 算 [1, mid) | core1 算 [mid, 1+n)
        mid = 1 + n/2
```

| 行 | 做什麼 |
|---|---|
| 62 | `size < 1` → return |
| 63–64 | `n = size - 1`；`mid = 1 + n / 2` |
| 67–68 | `task_t t = { .lo = mid, .hi = 1 + n }`；`queue_add_blocking(&q_task, &t)` 把後半交給 core1 |
| 69 | `compute_range(in_buf, out_buf, 1, mid)`：core0 自己算前半 |
| 71 | `queue_remove_blocking(&q_done, &done)`：等 core1 做完 |
| 72 | `out_buf[0] = m->data.data[0]`：job_id 帶回 |
| 73 | `msg_out.data.size = n + 1`（≤ capacity，因為收進來時就 ≤ MAX_LEN） |
| 74 | `rcl_publish` — 在 core0 |

- callback 在 core0 裡等 core1 做完才返回，executor 不會在中途收下一則 → `in_buf` 不會被覆寫（65 行註解）。
- pico-sdk 注意事項（9–13 行，已對 pico-sdk 2.2.0）：`pico/util/queue.h` 是跨核心安全佇列（內部 spinlock）；core1 stack 預設 `PICO_CORE1_STACK_SIZE` = `0x800`（2 KB，本 session 核對 `pico_multicore/include/pico/multicore.h:32`–`37`）→ core1 裡不要開大陣列；只有寫 flash 才需要 `multicore_lockout`；USB（TinyUSB）中斷在 core0。
- 48–49 行提示：排序題 → 兩核各排一半，core0 最後 merge（要多一個暫存陣列）；加總 / CRC → 各算部分結果，用 `q_done` 傳回再合併。

#### 要改的地方

| 行號 | 現在的值 | 意思 | 什麼情況要改、改成什麼 |
|---|---|---|---|
| `pico_dualcore_micro_ros.c:24` | `#define BOARD_NS "pico0"` | namespace | 每塊板子不同（同陣列版） |
| `pico_dualcore_micro_ros.c:25` | `#define MAX_LEN 400` | capacity（含 job_id） | 同陣列版的上限 |
| `pico_dualcore_micro_ros.c:43`（函式在 44–47） | `out[i] = (int32_t)((uint32_t)in[i] * (uint32_t)in[i])` | 純運算 | 換成題目的逐元素運算；不是逐元素的（排序、加總）照 48–49 行的提示改 `sub_cb`。乘法用無號數算，溢位時照 int32 繞回（`host_compute` 也一樣） |

#### 實際執行輸出

- 編譯、連結：✅（`app.uf2` 225,280 B，`-Wall -Wextra` 0 警告）。
- `compute_range()` 在 host 上測（host gcc 13.3.0、`-fsanitize=undefined`）。**修正前**（`in[i] * in[i]`）：

```text
t.c:15:55: runtime error: signed integer overflow: 46341 * 46341 cannot be represented in type 'int'
square: 2147395600 -2147479015 1000000      ← 輸入 {46340, 46341, -1000}
```

**修正後**（2026-11-12，用無號乘法，結果照 int32 繞回），UBSan 沒有任何錯誤，和 `host_compute` 的 Python 算法逐一相同：

```text
C      : 2147395600 2147395600 -2147479015 1000000 1 0      ← 輸入 {46340, -46340, 46341, 1000, -2147483647, 65536}
Python : 2147395600 2147395600 -2147479015 1000000 1 0
```

46340² = 2,147,395,600 還在 int32 內；46341² 超過 int32，現在**固定**繞回成 −2,147,479,015（兩邊一樣），不再是未定義行為。題目要「真正的平方」時，int32 裝不下，要換訊息型別（例如 `Int64MultiArray`）。

- 雙核心實際加速：沒有實測（沒有板子）。

#### 常見錯誤

| 症狀 | 原因 | 修法 |
|---|---|---|
| 隨機當機、封包壞掉 | 在 core1 呼叫了 rcl / rmw / printf | 所有 micro-ROS 呼叫移回 core0 |
| core1 當機（HardFault） | core1 裡開大區域陣列，爆 2 KB stack | 用全域 / static，或放大 `PICO_CORE1_STACK_SIZE` |
| 卡死、不回覆 | `queue_init` 放在 `multicore_launch_core1` 之後，或自己改的派工次數和等待次數不一致 | 每派 1 個 task 就要 remove 1 次 done |
| 結果和「真正的平方」不同，數值很大時 | int32 裝不下，照 int32 繞回（板子和 `host_compute` 一樣，所以還是 `correct=True`） | 題目要真正的值就換 `Int64MultiArray`；4.6 問題 3 |
| 雙核心沒有變快 | 瓶頸在 USB 傳輸，不在運算（112 行註解） | 先優化傳輸（`README.md` §5） |

### 4.3.7 `host_driver.py`

#### 用途

電腦端 rclpy 節點（`host_driver.py:2`）：把大陣列切成 `CHUNK` 個一塊，分給 `N_BOARDS` 塊板子算，收回後依 `job_id` 排好合併，計時，並和電腦算的答案比對。搭配 `pico_array_compute.c` 或 `pico_dualcore_micro_ros.c`。

#### 怎麼編譯 / 執行

```bash
# 每塊板子都要有自己的 agent 在跑（4.3.2）
source /opt/ros/jazzy/setup.bash
cd <repo>/預製程式碼/micro-ros
python3 host_driver.py
```

不改檔、臨時換常數（本 session 用假 rclpy 驗證過這個寫法有效，因為函式在執行時才讀全域變數）：

```bash
python3 -c 'import host_driver as h; h.CHUNK=399; h.N_BOARDS=3; h.main()'
```

預期輸出格式（`host_driver.py:124`–`125`；格式是本 session 用假 rclpy 跑出來的，數字要在考場實測）：

```text
[INFO] 等板子上線中…（ros2 topic list 看看）      ← 板子還沒上線時每 0.5 秒一次
boards=2 n=3000 chunk=300 time=<實測> ms throughput=<實測> KiB/s correct=True
```

#### 對外介面

常數：

| 名稱 | 行號 | 值 | 意思 |
|---|---|---|---|
| `N_BOARDS` | 21 | 2 | 板子數；namespace 必須是 `pico0`..`pico{N-1}` |
| `CHUNK` | 22 | 300 | 每塊資料個數；`CHUNK + 1` ≤ 板子 `MAX_LEN`（400），且 ≤ reliable 上限 505 |
| `MERGE` | 24 | `"sorted"` | `"concat"`：依 job_id 接起來；`"sorted"`：各塊已排序 → k-way merge |
| `TIMEOUT_S` | 27 | 10.0 | 整個 `run()` 最多等幾秒 |
| `RESEND_S` | 28 | 1.0 | 一塊送出後幾秒沒回就收回來重送（2026-11-12 加的；回覆遺失時不用等到 `TIMEOUT_S`） |

函式 / 方法：

| 名稱 | 行號 | 參數 | 回傳 / 效果 | 注意 |
|---|---|---|---|---|
| `make_data()` | 31–35 | — | `random.seed(0)` 後 3000 個 −1000..1000 的整數 | 換成題目輸入 |
| `host_compute(data)` | 38–42 | 全部資料 | `MERGE == "concat"` → 每個平方；否則 `sorted(data)` | 對答案用；要和板子運算一致 |
| `Driver.__init__()` | 46–57 | — | node 名 `host_driver`；QoS depth 10 RELIABLE；對每塊板子建 `/pico{i}/input` publisher 和 `/pico{i}/output` subscription；`busy`、`job_of`（每塊板子手上那一塊的 `(job_id, 送出時間)`） | lambda 用 `b=i` 預設參數記住板子編號（56–57） |
| `on_result(board, msg)` | 59–65 | 板子編號、訊息 | 空訊息忽略；`results[job_id] = data[1:]`；**回的是這塊板子手上那一塊**才把它標成空閒 | 重送之後才到的舊回覆只存結果，不會把板子誤標成空閒 |
| `send(board, job_id, chunk)` | 67–72 | — | `msg.data = [job_id] + chunk`，publish，`busy[board] = True`，記下 `job_of[board]` | 不填 `layout.dim` |
| `wait_boards()` | 74–82 | — | 等到每塊板子的 input 有訂閱者、且 output 有發佈者 | 只等 input 不夠：output 還沒配對時板子回的第一則會掉（volatile QoS 不補發） |
| `run(data)` | 84–114 | 全部資料 | `(out, dt)`：合併後的結果、秒數 | 見下面流程 |
| `main()` | 117–127 | — | init → `Driver` → `wait_boards` → `make_data` → `run` → 比對 → print → shutdown | — |

#### 程式流程

`run()` 的排程（流量控制：每塊板子同時最多 1 塊工作；回覆遺失會重送）：

```text
chunks = [data[0:300], data[300:600], ...]      # 3000 / 300 = 10 塊，job_id 0..9（85 行）
todo = deque([0, 1, ..., 9])；t0；deadline = t0 + TIMEOUT_S（86–88 行）
while 還沒收齊 且 沒逾時：（90 行）
    for b in 0..N_BOARDS-1:                     # 92 行
        板子 b 忙、而且這一塊送出超過 RESEND_S 秒 → 印 [WARN]、把板子標成空閒、
            這塊還沒有結果就放回 todo 最前面（93–98 行）
        todo 前面已經有結果的丟掉（99–100 行）
        板子 b 空閒 且 todo 還有 → send(b, todo.popleft())（101–103 行）
    rclpy.spin_once(timeout 1 ms)               # 104 行：處理回覆 → on_result 存結果、把板子標成空閒
dt = perf_counter() - t0                        # 105 行
沒收齊 → log error「逾時！只收到 x/y 塊」          # 106–107 行
parts = 依 job_id 排序後的各塊結果                 # 109 行
MERGE == "sorted" → heapq.merge(*parts)         # 110–111 行：k-way merge，各塊已排序 → 全體排序
否則              → 依序串接                       # 112–113 行
```

- 計時從第一塊送出前開始，**不含** `wait_boards()` 等板子上線的時間。
- `throughput = len(data) * 4 / dt / 1024`（KiB/s，只算單向的輸入資料量，不含 job_id 和回傳）。
- `correct = (out == host_compute(data))`（123 行）：Python 整數比對。`host_compute` 的平方照 int32 繞回（40–41 行），跟板子的 `Int32MultiArray` 一致。
- 排程是「誰空就給誰」：板子一樣快時等於輪流（round-robin）；某塊比較快就會拿到比較多塊。
- **`RESEND_S` 要比「板子算一塊的時間」長**：板子還在算就被判定逾時的話，同一塊會重算一次（結果還是對的，只是浪費時間）。考場先用預設 1.0 秒，看到很多 `[WARN] … 重送` 而且最後都對，就把它調大。

#### 要改的地方

| 行號 | 現在的值 | 意思 | 什麼情況要改、改成什麼 |
|---|---|---|---|
| `host_driver.py:21` | `N_BOARDS = 2` | 板子數 | 實際插幾塊就填幾；每塊的 `BOARD_NS` 要是 `pico0`..`pico{N-1}` |
| `host_driver.py:22` | `CHUNK = 300` | 每塊資料個數 | 越大每則 overhead 比例越低；上限 `MAX_LEN − 1`（399）且 reliable ≤ 504、best_effort ≤ 120 |
| `host_driver.py:24` | `MERGE = "sorted"` | 合併方式 | 板子是排序 → `"sorted"`；板子是逐元素運算 → `"concat"`；**跟 `CMakeLists.txt:28` 一起改** |
| `host_driver.py:28` | `RESEND_S = 1.0` | 幾秒沒回就重送 | 板子算一塊要超過 1 秒時調大（例如 3.0）；想更快發現遺失就調小 |
| `host_driver.py:32`（函式 31–35） | 3000 個亂數 | 輸入資料 | 換成題目給的輸入（讀檔等） |
| `host_driver.py:39`（函式 38–42） | 平方或 `sorted` | 正確答案 | 換成題目運算的 Python 版；注意要和「每塊各自算再合併」的結果形狀一樣（4.4.1） |

#### 實際執行輸出

- 環境：python 3.13.18；**沒有真的 rclpy**。用一個假 rclpy：publisher 一送出就模擬板子（排序或 int32 平方、超過 `MAX_LEN` 時不回、可指定某個 job 的回覆遺失），回覆在下一次 `spin_once` 送達。測試腳本 `import host_driver` 後改全域常數再呼叫 `main()`。**這只驗證排程、重送、合併、比對的邏輯；時間和 throughput 數字沒有意義**（下面以 `…` 省略，重送的情況保留時間）。2026-11-12 修好重送後重跑：

```text
1 預設（板子排序、MERGE=sorted）
boards=2 n=3000 chunk=300 time=… correct=True
sent per board: {'pico0': 5, 'pico1': 5}

2 板子平方、MERGE="concat"                          → correct=True
3 板子平方、MERGE="sorted"（沒一起改）                → correct=False
4 板子排序、MERGE="concat"（沒一起改）                → correct=False

5 job 3 的回覆遺失一次、TIMEOUT_S=2.0
[WARN] pico1 第 3 塊 1.0s 沒回，重送
boards=2 n=3000 chunk=300 time=1001.1 ms … correct=True
sent per board: {'pico0': 8, 'pico1': 3}

5b job 3 的回覆每次都掉（板子在這塊上壞掉）、TIMEOUT_S=2.5
[WARN] pico1 第 3 塊 1.0s 沒回，重送
[WARN] pico1 第 3 塊 1.0s 沒回，重送
[ERROR] 逾時！只收到 9/10 塊
boards=2 n=3000 chunk=300 time=2500.6 ms … correct=False

6 CHUNK=500（+1 > MAX_LEN 400，板子 size=0 不回）、TIMEOUT_S=3.0
[WARN] pico0 第 0 塊 1.0s 沒回，重送
[WARN] pico1 第 1 塊 1.0s 沒回，重送
[ERROR] 逾時！只收到 0/6 塊
sent per board: {'pico0': 3, 'pico1': 3}

7 N_BOARDS=3                                       → correct=True，分配 pico0:4、pico1:3、pico2:3

8 板子 int32 平方、資料 [46340, -46340, 46341, 1000]、MERGE="concat" → correct=True（修正前 False：host 用 Python 大整數）
8b 板子 int32 平方、3000 個 int32 全範圍亂數、MERGE="concat"   → correct=True
```

- 修正前（同一個情境 5）：`[ERROR] 逾時！只收到 9/10 塊`、`time=2000.1 ms`、`correct=False`，而且 pico1 之後再也拿不到工作。
- 情境 5b、6：重送救不了「每次都不回」，最後還是逾時；但 `[WARN] … 重送` 會告訴你是哪塊板子、哪一塊出事。
- 語法：上面每個測試都成功 `import host_driver`（等於語法檢查通過）。

#### 常見錯誤

| 症狀 | 原因 | 修法 |
|---|---|---|
| 一直印「等板子上線中…」 | 某塊板子的 agent 沒開 / namespace 不是 `pico{i}` / `N_BOARDS` 比實際多 | `ros2 topic list` 對照 `/pico0/input`…`/pico{N-1}/input` |
| `ModuleNotFoundError: rclpy` | 沒 `source /opt/ros/jazzy/setup.bash` | 先 source |
| `correct=False`、沒有逾時訊息 | `MERGE` 和板子程式不配；或 `host_compute` 和板子運算不一致 | 4.6 問題 1 |
| 偶爾 `[WARN] pico… 第 n 塊 … 重送`，最後 `correct=True` | 回覆遺失一次，或 `RESEND_S` 比板子算一塊的時間短 | 不影響正確性；很多次就把 `RESEND_S` 調大 |
| 同一塊一直 `重送`，最後 `逾時！只收到 x/y 塊` | 板子每次都不回：`CHUNK + 1` > `MAX_LEN`；訊息超過 MTU；板子當掉 | 4.4.6；看 `[WARN]` 是哪塊板子 |
| 全部板子都收到同一塊 | 板子燒了同一個 `BOARD_NS` | 每塊不同 namespace |
| `ros2 topic echo` 收不到 host 的訊息 | QoS 不合（板子改 best_effort、host 還是 RELIABLE，或反過來） | 4.4.4 |

## 4.4 照題目改：食譜

### 4.4.1 題目：「Pico 要算 X（不是排序）」→ 換運算函式

**逐元素運算（例如每個數 ×3+1）**：

1. `pico_array_compute.c:46`–`55`，把 `compute()` 換成：

   ```c
   static size_t compute(const int32_t *in, size_t n, int32_t *out, size_t cap) {
       if (n > cap) n = cap;
       for (size_t i = 0; i < n; i++) out[i] = in[i] * 3 + 1;
       return n;
   }
   ```

2. `host_driver.py:24`：`MERGE = "concat"`。
3. `host_driver.py:40`：`return [x * 3 + 1 for x in data]`（注意 int32 範圍）。

**整塊縮成一個值（例如加總、CRC32）**：

1. `compute()` 回傳 1：`int32_t s = 0; for (...) s += in[i]; out[0] = s; return 1;`（CRC32 演算法見第 5 章）。
2. `MERGE = "concat"` → host 拿到的是「每塊一個值」的串列。
3. `host_compute` 也要照塊算：`return [sum(data[i:i + CHUNK]) for i in range(0, len(data), CHUNK)]`；最後總和在 `main()` 裡再 `sum(out)`。
4. 雙核心版要改 `sub_cb`：core1 的部分結果用 `q_done` 傳回（`pico_dualcore_micro_ros.c:49`）。

驗證：先 `ros2 topic pub --once /pico0/input std_msgs/msg/Int32MultiArray "{data: [0, 1, 2, 3]}"` + `ros2 topic echo /pico0/output` 看單塊對不對，再跑 `host_driver.py`。成功的樣子：`correct=True`。

### 4.4.2 題目：「資料量 N 個、要調每則大小」→ 改陣列大小 / CHUNK

1. 資料量：`host_driver.py:35` 的 `range(3000)` 改成題目大小，或換成讀檔。
2. `CHUNK`（`host_driver.py:22`）：先確定 QoS（reliable 或 best_effort），用 4.2.5 的上限算：reliable `CHUNK ≤ 504`、best_effort `CHUNK ≤ 120`。
3. 若 `CHUNK + 1 > 400`：板子端兩個檔的 `MAX_LEN`（`pico_array_compute.c:27`、`pico_dualcore_micro_ros.c:25`）改成 ≥ `CHUNK + 1`，重新 build、燒每塊板子。RAM 代價：每多 1 個元素多 8 B（`in_buf` + `out_buf`），很寬裕。
4. 輸出比輸入長的運算（例如每個輸入產生 2 個輸出）：`out_n + 1` 也要 ≤ `MAX_LEN` 和傳輸上限，`CHUNK` 要再減半。

驗證：`CHUNK` 從小（100）往上加，每次看 `correct=True` 且沒有逾時；記下 `time=` 找最快的值（4.5）。⚠️ 接近 505 的上限沒有實測，留一點餘裕（範本建議 ≤ 450）。

### 4.4.3 題目：「用 3 塊板子」→ 加第三塊

1. 依序 build 三個 uf2（在官方 repo 的 `build/` 裡）：

   ```bash
   for ns in pico0 pico1 pico2; do
     sed -i "s/^#define BOARD_NS \".*\"/#define BOARD_NS \"$ns\"/" ../pico_array_compute.c
     make -j4 && cp app.uf2 app_$ns.uf2
   done
   grep -n '^#define BOARD_NS' ../pico_array_compute.c   # 最後會停在 pico2
   ```

   （`sed` 指令沒有在本 session 實測；不放心就用編輯器手改 `pico_array_compute.c:17` 三次。）namespace 叫 `pico2` 只是名字，和板子型號 `PICO_BOARD=pico2` 無關。
2. 一次插一塊、燒一個 uf2，貼標籤。
3. 開三個 agent，各指向自己的 `/dev/serial/by-id/...`（`agent_cheatsheet.md:35`–`38`）。
4. `host_driver.py:21`：`N_BOARDS = 3`。
5. 驗證：`ros2 topic list` 要有 `/pico0/input`、`/pico1/input`、`/pico2/input`；跑 `host_driver.py`，成功的樣子：`boards=3 … correct=True`。假 rclpy 測試中 3 塊板子分到 4 / 3 / 3 塊。

### 4.4.4 題目：「訊息小、要更快」→ reliable 改 best_effort

1. 板子（`pico_array_compute.c:111`–`112` 或 `pico_dualcore_micro_ros.c:103`–`104`）：

   ```c
   RCCHECK(rclc_subscription_init_best_effort(&sub, &node, ts, "input"));
   RCCHECK(rclc_publisher_init_best_effort(&pub, &node, ts, "output"));
   ```

2. host（`host_driver.py:50`）：`qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.BEST_EFFORT)`。
3. `CHUNK ≤ 120`（`host_driver.py:22`），因為 best_effort 一則只能 500 B。
4. 風險：best_effort 掉了不會重送；`host_driver.py` 會在 `RESEND_S`（預設 1 秒）後自己重送那一塊（4.3 的 `run()` 流程），所以掉一則只多等約 1 秒。掉得很頻繁時反而更慢，題目沒要求極限速度時，維持 reliable。
5. 驗證：`ros2 topic info /pico0/input -v` 顯示 BEST_EFFORT；`ros2 topic echo --qos-reliability best_effort /pico0/output`；跑 `host_driver.py` 比較 `time=`。⚠️ best_effort 比較快是文件說法（`README.md:67`、`82`），本 session 沒有實測。

### 4.4.5 症狀：「agent 連上了，可是 `ros2 topic list` 沒有板子的 topic」

照順序檢查：

1. **看 LED**：陣列版不亮 = 還在等 agent（其實沒連上）；快閃 = `RCCHECK` 失敗；恆亮 = 都建好了。pingpong 版亮 = `AGENT_CONNECTED`。
2. **看 agent log**：用 `-v6` 重開 agent，看有沒有 session 建立、有沒有建立 participant / topic / publisher 的錯誤。⚠️ 確切訊息沒有實測。
3. **`ROS_DOMAIN_ID`**：agent 的終端機和下 `ros2` 的終端機要一樣；docker agent 加 `-e ROS_DOMAIN_ID=$ROS_DOMAIN_ID` 和 `--net=host`。
4. **ROS 2 daemon 快取**：`ros2 topic list --no-daemon`，或 `ros2 daemon stop` 後再 list（一般 ROS 2 行為，⚠️沒在本 session 實測）。
5. **實體數 / handle 數**：自己加了 sub、timer 卻沒改 `rclc_executor_init` 的 handle 數 → `add_*` 失敗 → LED 快閃；sub 超過 5、pub 超過 10、node 超過 1 → create 失敗（`colcon.meta:43`–`45`）。
6. **topic 名稱**：名稱不合法（空白、開頭數字等）會建立失敗；namespace 和 host 端 `/pico{i}/` 對不上 → topic 有出現但名字不同。
7. **板子先上線、agent 後重開**：陣列版沒重連 → 按 reset。
8. 都不行：燒官方 `pico_micro_ros_example.c`（`CMakeLists.official.txt` 改回 `CMakeLists.txt`）確認環境本身能動。

### 4.4.6 症狀：「小訊息 OK，大訊息沒有回應」→ 訊息太大

1. 算大小：`16 + 4 × (CHUNK + 1)` B。reliable > 2036、best_effort > 500 → 超過傳輸上限；`CHUNK + 1 > MAX_LEN` → 板子 `size == 0` 被忽略。兩種的外觀都是「host 逾時」。
2. 用 CLI 直接試邊界（`N` 是含 job_id 的元素數）：

   ```bash
   ros2 topic echo /pico0/output &
   N=401; ros2 topic pub --once /pico0/input std_msgs/msg/Int32MultiArray \
     "{data: $(python3 -c "print(list(range($N)))")}"
   ```

   `N=400` 有回、`N=401` 沒回 → 是 `MAX_LEN` 限制；把 `MAX_LEN` 加大後 `N=505` 有回、`N=506` 沒回 → 是傳輸上限（⚠️ 這兩個邊界值是推算的，沒有實測）。
3. 修法：把 `CHUNK` 調到上限以下（最簡單）；或加大 `MAX_LEN`（不超過傳輸上限）；真的要更大才重編 libmicroros（4.2.5）。
4. 板子**發**太大（輸出比輸入長）時 `rcl_publish` 回傳錯誤但被 `RCSOFTCHECK` 吃掉：要確認就暫時改成 `RCCHECK`（失敗會 LED 快閃）。

## 4.5 效能：量測方法與實測數字

本 session 實測到的只有 build 相關數字（4.3.3）：

| 項目 | 實測值 | 環境 |
|---|---|---|
| 第一次 cmake + make | 24–28 s | x86_64 容器 4 核、`make -j4`、含下載編譯 picotool |
| 換 `APP_SRC` 後再 `make` | 0–1 s | 同一個 build 資料夾 |
| `app.uf2` | 221,696 / 223,744 / 225,280 B | pingpong / array / dualcore |
| 靜態 RAM（bss） | 26,132 / 29,260 / 29,292 B | `arm-none-eabi-size` |

**傳輸 throughput、雙核心加速、多板加速：沒有實測**（沒有板子、沒有 agent）。考場量測方法：

1. `host_driver.py` 的輸出：`time=… ms throughput=… KiB/s`（計時用 `time.perf_counter()`，不含等板子上線）。
2. 變因一次只改一個：
   - `CHUNK`：`python3 -c 'import host_driver as h; h.CHUNK=100; h.main()'`，再試 200、300、399。
   - 板子數：`h.N_BOARDS=1` vs `2` vs `3`。
   - 單核 vs 雙核：同一份資料分別燒 `pico_array_compute.c`（改成同樣的平方運算）和 `pico_dualcore_micro_ros.c`。
3. 每個設定跑 3 次取中位數；agent 不開 `-v6`；host 不要在 callback 裡 print（`README.md:80`）。
4. 只看單塊板子的輸出頻率：`ros2 topic hz /pico0/output`、`ros2 topic bw /pico0/output`。

預期趨勢（依程式結構推論，⚠️未實測）：reliable 每則都要等 ACK（`pico_array_compute.c:68`），而 host 每塊板子同時只給 1 塊 → 每塊板子的速度受「一來一回」的延遲限制；所以加大 `CHUNK`、加板子通常比雙核心有效，除非運算本身很重。

## 4.6 限制、已知問題、沒驗證的地方

**已知問題（本 session 核對過）：**

1. **`APP_SRC` 和 `MERGE` 要成對改**（審查已知問題 1）。
   - `CMakeLists.txt:27` 和 `host_driver.py:25`–`26` 都有註明。沒一起改 → `correct=False`（假 rclpy 測試 3、4 重現）。
   - **回覆遺失不會重送（已修，2026-11-12）**：原本送出後 `busy[b] = True` 只有收到回覆才清掉，回覆遺失時那塊永遠不重送、那塊板子也不再被派工，最後等到 `TIMEOUT_S` 才報逾時、`correct=False`。現在 `run()` 記錄每塊的送出時間，超過 `RESEND_S`（`host_driver.py:28`，預設 1.0 秒）沒回就收回來重送（`host_driver.py:93`–`98`）；`on_result` 只在回的是「手上那一塊」時才把板子標成空閒（`:64`–`65`）。假 rclpy 測試 5 從 `correct=False`（2000 ms 逾時）變成 `correct=True`（約 1000 ms）。板子每次都不回的情況（測試 5b、6）重送救不了，還是會逾時。
2. **`pico_pingpong.c:32`–`33` 的 `EVERY_N_MS` 在 `-Wall` 下觸發 `-Wmisleading-indentation`**（審查已知問題 4）。本 session 實測：第 142、149 行展開處各一次（修正前的行號是 139、146）。外觀問題，不影響功能；SDK 預設 build 不開 `-Wall`，所以平常看不到。
3. **（已修）`pico_dualcore_micro_ros.c` 的 `in[i] * in[i]` 在 |x| > 46340 時 int32 溢位**（審查已知問題 5）：有號整數溢位是 C 的未定義行為，host 端 `host_compute` 又用 Python 大整數，所以會 `correct=False`。2026-11-12 起板子用無號乘法、照 int32 繞回（`pico_dualcore_micro_ros.c:45-46`），`host_compute` 也照 int32 繞回（`host_driver.py:40-41`），兩邊結果一致：UBSan 無錯誤，假 rclpy 測試 8、8b（int32 全範圍亂數）都 `correct=True`。題目要「真正的平方」時 int32 裝不下，要換訊息型別。
4. **文件不一致（已修）**：`CMakeLists.txt:58`–`59` 的註解原本寫「推論（未實際連結驗證）」，和檔頭矛盾；2026-11-12 已改成實測結果。
5. **陣列版沒有重連**：板子或 agent 重開後要按 reset（`pico_array_compute.c:7`）。
6. **（已修）`pico_pingpong.c` 的 `device_id`** 原本用開機微秒數，兩塊板子不保證不同。2026-11-12 起改用板子出廠的唯一序號（`pico_get_unique_board_id()`，`pico_pingpong.c:131-133`；`CMakeLists.txt` 連 `pico_unique_id`），每塊板子一定不同；3 支程式重新編譯連結通過。`pong_count` 仍然只計數、沒有輸出（USB 被 agent 佔用，不能 printf；要回報就自己加一個 publisher）。
7. **`pico_pingpong.c:146`**：`create_entities()` 中途失敗時對「還沒建立的物件」呼叫 fini（照官方 reconnection 範例的寫法，錯誤被 `RCSOFTCHECK` 忽略）。⚠️ 在板子上的行為沒有驗證。

**沒驗證的地方：**

- 3 支程式都**沒燒錄、沒在 Pico 2 上跑過**；官方沒有正式支援 RP2350（issue #1482 open）。能連結 ≠ 能跑。
- `agent_cheatsheet.md` 所有指令、agent 的 log 字樣、`ros2 topic echo` 的輸出格式。
- `host_driver.py` 只用假 rclpy 驗證邏輯，沒有用真的 rclpy、DDS、agent 跑。
- 訊息大小上限（500 B / 2036 B、16 B overhead、121 / 505 個 int32）是依文件和標頭檔推算。
- best_effort 比 reliable 快多少、雙核心 / 多板加速多少，都沒有數字。
- 考場沒網路時，pico-sdk 下載 picotool、clone 官方 repo、拉 docker 映像都可能失敗。

## 4.7 一頁速查表

**Build（在官方 repo 資料夾）：**

| 步驟 | 指令 |
|---|---|
| SDK 路徑 | `export PICO_SDK_PATH=~/pico-sdk` |
| 放檔案 | `cp CMakeLists.txt CMakeLists.official.txt; cp <repo>/預製程式碼/micro-ros/{CMakeLists.txt,pico_*.c} .` |
| 選程式 | `sed -i 's/^set(APP_SRC .*)/set(APP_SRC pico_array_compute.c)/' CMakeLists.txt` |
| 編譯 | `mkdir -p build && cd build && cmake -DPICO_BOARD=pico2 .. && make -j4` |
| 燒錄 | 按 BOOTSEL 插 USB，`cp app.uf2 /media/$USER/RP2350/` |

**Agent 與檢查（⚠️未實測）：**

| 用途 | 指令 |
|---|---|
| agent（docker） | `docker run -it --rm -v /dev:/dev --privileged --net=host microros/micro-ros-agent:jazzy serial --dev /dev/ttyACM0 -b 115200` |
| agent（ros2） | `ros2 run micro_ros_agent micro_ros_agent serial --dev /dev/ttyACM0 -b 115200` |
| 找板子 | `ls -l /dev/serial/by-id/` |
| 權限 | `sudo usermod -aG dialout $USER`（重登）或 `sudo chmod 666 /dev/ttyACM0` |
| 看 topic | `ros2 topic list`、`ros2 topic info /pico0/input -v` |
| 手動送 | `ros2 topic pub --once /pico0/input std_msgs/msg/Int32MultiArray "{data: [7, 3, 1, 2]}"` |
| BE 收 | `ros2 topic echo --qos-reliability best_effort /topic` |
| 跑 host | `source /opt/ros/jazzy/setup.bash && python3 host_driver.py` |

**要成對改的設定：**

| 板子端 | host 端 |
|---|---|
| `CMakeLists.txt:28` `APP_SRC = pico_array_compute.c` | `host_driver.py:24` `MERGE = "sorted"` |
| `CMakeLists.txt:28` `APP_SRC = pico_dualcore_micro_ros.c` | `host_driver.py:24` `MERGE = "concat"` |
| `BOARD_NS` = `pico0`..`pico{N-1}`（`pico_array_compute.c:17`） | `host_driver.py:21` `N_BOARDS = N` |
| `MAX_LEN`（`pico_array_compute.c:27`） | `host_driver.py:22` `CHUNK + 1 ≤ MAX_LEN` |
| `rclc_*_init_default` / `_best_effort` | `host_driver.py:50` `RELIABLE` / `BEST_EFFORT` |
| `compute()` / `compute_range()` | `host_driver.py:38` `host_compute()` |

**常數：**

| 常數 | 值 |
|---|---|
| MTU | 512 B |
| stream history / max history | 4 / 4 |
| 上限 reliable / best_effort | 2036 B（505 個 int32）/ 500 B（121 個 int32），含 job_id |
| 實體上限（每板） | 1 node、10 pub、5 sub、1 service、1 client |
| executor handle 數 | timer 數 + subscription 數（pingpong 3、陣列 1、雙核 1） |
| 主 stack / core1 stack | 2 KB / 2 KB |
| LED | GP25；陣列版：不亮 = 等 agent、恆亮 = OK、快閃 = 建立失敗 |

**rclc 函式簽名：**

| 函式 | 簽名 |
|---|---|
| 傳輸 | `rmw_uros_set_custom_transport(bool framing, void *args, open, close, write, read)` |
| 等 agent | `rmw_uros_ping_agent(int timeout_ms, uint8_t attempts)` → `RMW_RET_OK` |
| support | `rclc_support_init(rclc_support_t *, int argc, char const *const *argv, rcl_allocator_t *)` |
| node | `rclc_node_init_default(rcl_node_t *, const char *name, const char *ns, rclc_support_t *)` |
| pub / sub | `rclc_publisher_init_default(pub, node, type_support, topic)`；`_best_effort` 同參數 |
| timer | `rclc_timer_init_default2(timer, support, timeout_ns, callback, bool autostart)` |
| executor | `rclc_executor_init(exec, &support.context, size_t n_handles, allocator *)` |
| 加訂閱 | `rclc_executor_add_subscription(exec, sub, msg *, callback, ON_NEW_DATA)` |
| spin | `rclc_executor_spin_some(exec, uint64_t timeout_ns)` |
| 發佈 | `rcl_publish(pub, msg *, NULL)` |
| sequence | `msg.data.data = buf; msg.data.capacity = N; msg.data.size = 0;` |

**常見錯誤：**

| 症狀 | 第一個檢查 |
|---|---|
| `correct=False` | `APP_SRC` ↔ `MERGE`；`host_compute` 和板子運算不一致 |
| 逾時 `只收到 x/y 塊` | `CHUNK + 1` vs `MAX_LEN` / 傳輸上限；板子當掉（偶爾遺失會自動重送，看 `[WARN]`） |
| topic 沒出現 | LED、agent `-v6`、`ROS_DOMAIN_ID`、handle 數 |
| echo 收不到 | QoS（`--qos-reliability best_effort`） |
| 陣列收不到 | sequence 沒配置 capacity；host 填了 `layout.dim` |
| 雙核當機 | core1 碰了 rcl / printf；core1 stack 2 KB |
| `__atomic_*_4` undefined | `README.md` §6 shim（本 session 沒出現） |
