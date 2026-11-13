# micro-ROS on Pico 2 — 預製程式碼（ROS 2 Jazzy）

> ## 驗證狀態（2026-11-12）
> - ✅ **編譯、連結通過**：3 支 Pico 端程式（`APP_SRC` 逐一切換）都用這份 `CMakeLists.txt` 產出 `app.uf2`。
>   環境：pico-sdk 2.2.0、`-DPICO_BOARD=pico2`（rp2350-arm-s）、官方 `micro_ros_raspberrypi_pico_sdk` jazzy 分支的預編 `libmicroros.a`、arm-none-eabi-gcc 13.2。
>   沒有出現 `__atomic_*_4` undefined reference（§6 的 shim 不需要）。
> - ⚠ **沒燒錄、沒在板子上跑過、沒接 agent 測過**；`host_driver.py` 只檢查過語法（容器裡沒有 rclpy）。
> - API 已逐行對過官方 repo 內 `libmicroros/include` 的標頭檔（見文末審查紀錄）。
> **考場第一件事：用官方範例 build + flash 一次，確認環境能動，再換成這裡的程式。**
> **換板子程式時**：`CMakeLists.txt` 的 `APP_SRC` 和 `host_driver.py` 的 `MERGE` 要一起改（`pico_array_compute.c` → `"sorted"`、`pico_dualcore_micro_ros.c` → `"concat"`），否則會顯示 `correct=False`。

## 檔案
| 檔案 | 用途 |
|---|---|
| `pico_pingpong.c` | Ping-Pong（/microROS/ping、/microROS/pong，std_msgs/Header）+ 斷線重連狀態機 |
| `pico_array_compute.c` | 收 Int32MultiArray → `compute()` → 發回；示範 sequence 記憶體配置 |
| `pico_dualcore_micro_ros.c` | core0 跑 micro-ROS、core1 用 queue 幫忙算一半 |
| `CMakeLists.txt` | 官方寫法 + Pico 2 設定；改 `APP_SRC` 選要編哪支 |
| `host_driver.py` | 電腦端：切塊分給 N 塊板子、照順序合併、計時、對答案 |
| `agent_cheatsheet.md` | agent 指令、多板子、權限、`ros2 topic hz/bw` |

## 1. 概念（先懂這個）
- **ROS 2**：電腦上的節點用 **DDS**（UDP 網路協定，很肥）互相溝通，topic / pub / sub。
- **MCU（Pico）RAM 只有幾百 KB，跑不動 DDS** → 用 **Micro XRCE-DDS**（超精簡版協定）。
- **micro-ROS agent**：跑在電腦上的「翻譯官」。一邊用 XRCE-DDS 跟板子講話（走 USB 序列埠），
  一邊用 DDS 代替板子出現在 ROS 2 世界。所以 `ros2 topic list` 看得到板子的 topic。
- **rclc**：MCU 版的 C API（電腦上是 rclcpp / rclpy）。**executor** 負責呼叫 callback。
- 板子上的 node/pub/sub 其實是「請 agent 幫忙建立」→ agent 沒開，板子什麼都建不起來。

```
[Pico: rclc + XRCE-DDS client] --USB serial--> [micro-ros-agent] --DDS--> [ros2 CLI / rclpy]
```

## 2. 流程
1. `export PICO_SDK_PATH=...`；把本資料夾的 .c + CMakeLists.txt 放進官方 repo 資料夾
   （要有 `libmicroros/`、`pico_uart_transport.c`、`pico_uart_transports.h`）。
2. `mkdir build && cd build && cmake -DPICO_BOARD=pico2 .. && make -j4`
3. 按住 BOOTSEL 插 USB → 出現磁碟 → `cp app.uf2 /media/$USER/RP2350/`（Pico 1 是 `RPI-RP2`）
4. 開 agent：`ros2 run micro_ros_agent micro_ros_agent serial --dev /dev/ttyACM0`（見 cheatsheet）
5. `ros2 topic list` → `ros2 topic echo /pico0/output` → `python3 host_driver.py`
6. 板子先開或 agent 先開都可以（程式會一直 ping agent）；不行就按 reset / 重插。

## 3. 錯誤排查
| 症狀 | 可能原因 | 解法 |
|---|---|---|
| agent 一直沒反應、LED 不亮 | port 錯 / 權限 / 被別的程式占用 | `ls /dev/serial/by-id/`、加 dialout 群組、關 minicom |
| agent 連上但 topic 沒出現 | create 某步失敗（名字錯、超過實體數上限） | 每步用 RCCHECK（陣列版、雙核版 LED 快閃；pingpong 的 RCCHECK 是 return false → 回去等 agent，LED 不閃）；上限：1 node、10 pub、5 sub、1 service、1 client |
| topic 有但 echo 不到 | QoS 不合（best_effort vs reliable） | `--qos-reliability best_effort`；兩端用同 QoS |
| 小訊息 OK、大訊息不見 | 超過傳輸上限（板子收不到）或 > capacity（callback 收到 size=0） | 見 §4；host 切小塊 |
| `rclc_executor_add_*` 失敗 | executor handle 數 < timer + sub 數 | `rclc_executor_init(..., N, ...)` 的 N 加大 |
| 收不到陣列/字串訊息 | **忘了配置 sequence 記憶體**（capacity=0） | `.data=buf; .capacity=N; .size=0`（見 array_compute） |
| 送出去的陣列是空的 | 忘了設 `.size` | publish 前 `msg.data.size = n` |
| 想 printf 除錯 | USB 被 agent 佔用：字看不到、還混進封包串流（framing 可能丟掉也可能弄壞封包，未驗證） | 不要 printf；改用 LED 或 UART0 + USB-TTL |
| 板子重開後 topic 消失 | 沒有重連機制 | 抄 pingpong 狀態機，或重開 agent |
| 連結失敗（RP2350）`undefined reference to __atomic_*_4` | 預編函式庫是 M0+ 版 | 見 §6 補丁 |

## 4. 訊息大小限制（重要）
- 預編函式庫實際值（`libmicroros/include/uxr/client/config.h`、`rmw_microxrcedds_c/config.h`）：
  `UXR_CONFIG_CUSTOM_TRANSPORT_MTU = 512`、`RMW_UXRCE_STREAM_HISTORY_INPUT/OUTPUT = 4`、
  `RMW_UXRCE_MAX_HISTORY = 4`（每個訂閱暫存幾則，不是大小上限）。
- 官方公式（micro.ros.org「Middleware Configuration」）：
  **best_effort** ≤ MTU − 12 B = **500 B**；**reliable** ≤ MTU × STREAM_HISTORY − 12 B = **2036 B**。
- Int32MultiArray 序列化 overhead ≈ 16 B（CDR 頭 4 + dim 長度 4 + data_offset 4 + data 長度 4）
  → best_effort ≈ **121 個 int32**、reliable ≈ **505 個 int32**（含 job_id）。模板 MAX_LEN=400 留餘裕。
- 超過時：板子**發**太大 → `rcl_publish` 回傳錯誤；板子**收**太大 → 收不到；
  沒超過傳輸上限但 > capacity → callback 照叫、`data.size == 0`（模板會忽略）。
- reliable 發佈會等 agent ACK 才返回（每則一個來回）；best_effort 不等 → 小訊息較快。
- 要更大：改 `microros_static_library/library_generation/colcon.meta`
  （`rmw_microxrcedds` 加 `-DRMW_UXRCE_STREAM_HISTORY=8`（須 2 的次方）、
  `microxrcedds_client` 加 `-DUCLIENT_CUSTOM_TRANSPORT_MTU=1024`）
  然後用 docker `microros/micro_ros_static_library_builder:jazzy` **重編 libmicroros**。
- 實體數上限也在 colcon.meta：`RMW_UXRCE_MAX_NODES/PUBLISHERS/SUBSCRIPTIONS`。

## 5. Throughput 優化清單（去年加速關鍵）
1. **用二進位，不要用文字**：`Int32MultiArray` / `UInt8MultiArray`，不要 `String` 存 "1,2,3"。
   能壓就壓：資料只要 0~255 就用 UInt8（小 4 倍）。
2. **大塊傳**：每則訊息塞到接近上限（每則都有固定 overhead）；但別超過（會被丟）。
3. **多塊板子平行**：每塊不同 namespace，host 切塊 round-robin 分派（host_driver.py）。
4. **雙核心**：運算重時 core1 分一半（pico_dualcore_micro_ros.c）。傳輸是瓶頸時沒用。
5. `rclc_executor_spin_some` timeout 設小（1 ms）；重連 ping 週期拉長（例如 1000 ms）。
6. agent 不要開 `-v6`；host 端不要每則都 print。
7. 小訊息 + 可容忍掉包 → best_effort（無 ACK，較快）；大訊息/不能掉 → reliable。
8. 提高 CPU 時脈（`set_sys_clock_khz`，Pico 2 預設 150 MHz）——小心穩定性。
9. 先量再優化：`ros2 topic hz/bw`、host 端 `time.perf_counter()`。

## 6. Pico 2 / RP2350 支援狀態（2026-11 查原始碼結果）
- 官方 README **只寫 Pico（RP2040）**；issue #1482「Request for RP2350 support」（2025-10）仍 **open**。
- 預編 `libmicroros.a` 用 `-march=armv6-m -mcpu=cortex-m0plus` 編（toolchain.cmake）。
  **結論：在 pico2（ARM）上編譯、連結都成功（2026-11-12 實測，見檔頭）；能不能在板子上正常跑還沒驗證，也沒有官方保證。**理由：
  1. ARMv8-M Mainline（M33）指令集包含 ARMv6-M → M0+ 程式碼能在 M33 上跑。
  2. ABI 相容：M0+ 是 soft-float，pico-sdk 對 RP2350 用 `-mfloat-abi=softfp`（同一種呼叫慣例）；
     自己寫的小測試（M0+ 物件連進 M33 softfp 執行檔）連結成功。
  3. 唯一風險：GCC 在 M0+ 上把 4-byte 的 atomic exchange/CAS/fetch_add 編成函式呼叫
     `__atomic_*_4`；pico-sdk 的 `pico_atomic` 在 RP2350 **只提供 8-byte 版**。rcl 只有
     `rcl_timer_exchange_callback` 用到（本模板沒用，`--gc-sections` 會丟掉）→ 應該不會出錯。
- 萬一出現 `undefined reference to __atomic_exchange_4` 等：新增 `atomic_shim.c` 加進 add_executable：
  ```c
  #include "hardware/sync.h"   // 仿 pico_atomic/atomic.c 的 spinlock 寫法（未驗證）
  #define LK spin_lock_instance(PICO_SPINLOCK_ID_ATOMIC)
  uint __atomic_exchange_4(volatile void *p, uint v, int m) { uint32_t s = spin_lock_blocking(LK);
    uint o = *(volatile uint *)p; *(volatile uint *)p = v; spin_unlock(LK, s); return o; }
  // 其他缺的（_compare_exchange_4、_fetch_add_4）照同樣模式補
  ```
- 其他 Plan B：(a) 改 toolchain.cmake 為 `-mcpu=cortex-m33 -mthumb -mfloat-abi=softfp` 用 docker 重編函式庫；
  (b) 不用 micro-ROS：板子用 `getchar_timeout_us/putchar_raw` 收發自訂二進位格式，
  電腦端寫一個 rclpy 節點用 pyserial 轉成 topic（自己當 agent）。

## 7. 去年練習題簡答
**Q1 micro-ROS 與 ROS 2 的關係？用到哪些裝置？**
micro-ROS = 把 ROS 2 的 API（rcl/rclc）搬到 MCU，中介層換成 Micro XRCE-DDS。
裝置：MCU 板（去年 ESP32，今年 Pico 2）跑 micro-ROS client；電腦跑 micro-ros-agent
（XRCE-DDS ↔ DDS 橋接）與 ROS 2 節點。Linux 練習版則是 client 也跑在 Linux 上。

**Q2 Host 與 MCU 間傳資料怎麼實作？（C / C++ / Python）**
MCU：C + rclc（`rclc_publisher_init_default` / `rcl_publish` / subscription callback）。
Host：Python rclpy 或 C++ rclcpp 一般 ROS 2 節點，pub/sub 同一個 topic 即可，agent 自動轉發。
傳輸層是 USB CDC 序列埠（也可 UART / UDP Wi-Fi）。

**Q3 資料型態限制？自訂訊息？**
MCU 沒有動態記憶體 → 字串/陣列要先配置（capacity）；訊息有大小上限（§4）；
實體數量有上限（colcon.meta）。自訂 .msg 要放進 `library_generation/extra_packages/`
然後 **重編 libmicroros**（現場很花時間 → 優先用 std_msgs 的 MultiArray 湊）。

**Q4 實體板子 vs Linux 開發流程差在哪？**
Linux：直接編譯執行、能 printf / gdb、transport 是 UDP。
實體：交叉編譯 → .uf2 燒錄 → 序列埠 transport、要開 serial agent、不能在同一條 USB printf、
記憶體/訊息大小受限、要處理 agent 斷線重連、多板子要分 port 與 namespace。

## 參考來源
- github.com/micro-ROS/micro_ros_raspberrypi_pico_sdk（jazzy：README、example、transport、CMakeLists、colcon.meta、toolchain.cmake）
- github.com/ros2/rclc（jazzy：timer.h、executor.h）；github.com/micro-ROS/micro_ros_utilities（type_utilities.h）
- micro_ros_arduino reconnection example；freertos_apps ping_pong app.c；micro.ros.org middleware 設定說明

## 設計審查紀錄（2026-11-11，只讀原始碼；2026-11-12 補上實際編譯、連結，見檔頭）
來源縮寫：**PICO** = `https://raw.githubusercontent.com/micro-ROS/micro_ros_raspberrypi_pico_sdk/jazzy/`，
**INC** = PICO + `libmicroros/include/`（= build 時實際用的標頭檔），**SDK** = pico-sdk 2.2.0（docker `pico-build:/opt/pico-sdk`）。

| # | 項目 | 結果 | 依據 |
|---|---|---|---|
| 1 | `rclc_support_init(support, argc, argv, allocator*)`、`rclc_node_init_default(node, name, ns, support)` | OK | INC `rclc/init.h`、`rclc/node.h` |
| 1 | `rclc_publisher_init_default/_best_effort`、`rclc_subscription_init_default/_best_effort` | OK | INC `rclc/publisher.h`、`rclc/subscription.h` |
| 1 | `rclc_timer_init_default2(timer, support, timeout_ns, cb, autostart)`；舊版已 deprecated | OK | INC `rclc/timer.h` |
| 1 | `rclc_executor_init(exec, context*, n_handles, allocator*)`、`add_subscription(..., msg*, cb, ON_NEW_DATA)`、`add_timer`、`spin_some(exec, timeout_ns)` | OK | INC `rclc/executor.h`、`rclc/executor_handle.h` |
| 1 | `rclc/rclc.h` 不含 executor.h → 各檔另外 include | OK | INC `rclc/rclc.h` |
| 1 | RCCHECK/RCSOFTCHECK 函式庫沒提供 → 自己定義；rcl_* 有 `RCL_WARN_UNUSED` → 改用 RCSOFTCHECK 接回傳值 | fixed | INC `rclc/rclc.h`、`rcl/publisher.h` |
| 1 | `rmw_uros_set_custom_transport(framing, args, open, close, write, read)`、transport 函式名 `pico_serial_transport_*` | OK | INC `rmw_microros/custom_transport.h`、PICO `pico_uart_transports.h` |
| 1 | `rmw_uros_ping_agent(timeout_ms, attempts)`、`rmw_uros_sync_session(ms)`、`rmw_uros_epoch_millis()`、`rmw_uros_set_context_entity_destroy_session_timeout` | OK | INC `rmw_microros/ping.h`、`time_sync.h`、`timing.h` |
| 1 | `rcl_publish(pub, msg, NULL)`、`rcl_*_fini`、`rcl_context_get_rmw_context`、timer callback 簽名 | OK | INC `rcl/publisher.h`、`rcl/context.h`、`rcl/timer.h` |
| 2 | 程式結構同官方 `pico_micro_ros_example.c`（transport → ping agent → support → node → executor → spin_some） | OK | PICO `pico_micro_ros_example.c` |
| 2 | CMake：`link_directories(libmicroros)`、連 `microros`、include `libmicroros/include`、3 個 CRLF=0、stdio_usb 1/uart 0（沒有 `micro_ros_pico` 這種 target） | OK | PICO `CMakeLists.txt` |
| 2 | CMake 註解「可試 `-DPICO_PLATFORM=rp2350-arm-s`」無意義（pico2 預設就是它） | fixed | SDK `src/boards/include/boards/pico2.h`、`cmake/pico_pre_load_platform.cmake` |
| 2 | RP2350 能否連結 | unverifiable（推論：很可能可以，見 §6） | PICO `microros_static_library/library_generation/toolchain.cmake`；SDK `pico_atomic/atomic.c`、`pico_arm_cortex_m33_gcc.cmake`；ros2/rcl jazzy `src/rcl/timer.c` |
| 3 | Int32MultiArray 欄位 `data.data/size/capacity`、`layout.dim`、`layout.data_offset`；Header `stamp`、`frame_id`(String) | OK | INC `std_msgs/msg/detail/int32_multi_array__struct.h`、`multi_array_layout__struct.h`、`header__struct.h`、`rosidl_runtime_c/primitives_sequence.h` |
| 3 | 收訊息是反序列化進使用者給的記憶體、不 malloc；primitive/字串超過 capacity → size=0 但 callback 照叫；巢狀 sequence（dim）超過 → 整則失敗 | OK；callback 加 size 檢查（fixed） | micro-ROS/rosidl_typesupport_microxrcedds jazzy `rosidl_typesupport_microxrcedds_c/resource/msg__type_support_c.c.em` |
| 3 | micro_ros_utilities 註解範例：欄位名、函式簽名正確；`conf = {0}` 也可（allocator NULL → 預設），改寫成 `micro_ros_utilities_memory_conf_default` 較清楚 | OK | INC `micro_ros_utilities/type_utilities.h`；micro_ros_utilities jazzy `src/type_utilities.c` |
| 4 | colcon.meta：NODES 1、PUB 10、SUB 5、SERVICES 1、CLIENTS 1、MAX_HISTORY 4、transport custom；沒覆寫 MTU/STREAM_HISTORY（用預設 512 / 4） | OK | PICO `microros_static_library/library_generation/colcon.meta`；INC `rmw_microxrcedds_c/config.h`、`uxr/client/config.h` |
| 4 | 大小上限：reliable 原寫「≈450 int32」→ 依公式 2036 B ≈ 505 int32；best_effort 500 B ≈ 121 int32 | fixed | micro.ros.org Middleware Configuration（micro-ROS.github.io `_docs/tutorials/advanced/microxrcedds_rmw_configuration`）；rmw_microxrcedds jazzy `CMakeLists.txt` |
| 4 | 發太大 → rcl_publish 回錯誤（非無聲）；reliable 發佈會等 ACK | fixed（註解） | rmw_microxrcedds jazzy `rmw_microxrcedds_c/src/rmw_publish.c` |
| 5 | `queue_init/add_blocking/remove_blocking`、`multicore_launch_core1` 簽名；queue 跨核心安全；core1 stack 2 KB；不寫 flash 就不需 lockout | OK | SDK `common/pico_util/include/pico/util/queue.h`、`rp2_common/pico_multicore/include/pico/multicore.h` |
| 5 | rcl 呼叫只在 core0 | OK | colcon.meta `RCUTILS_NO_THREAD_SUPPORT=ON` |
| 6 | 重連狀態機（4 狀態、500/200 ms、ping(100,1)、destroy timeout 0、fini 順序） | OK | micro_ros_arduino jazzy `examples/micro-ros_reconnection_example/micro-ros_reconnection_example.ino` |
| 7 | host：QoS RELIABLE 對板子 `_default`；list → array('i')；lambda 綁 b=i；namespace /picoN/input、/picoN/output 與 C 端一致；job_id 協定一致 | OK；加等 output publisher、空訊息檢查（fixed）；py_compile 通過 | rclpy Jazzy API（未連板子實跑：unverifiable） |
| 8 | docker `microros/micro-ros-agent:jazzy serial --dev /dev/ttyACM0 -b 115200`、snap 指令 | OK | PICO `README.md` |
| 8 | `-D/--dev`、`-b`（預設 115200）、`-v 0~6`、`multiserial` | OK（補註） | micro-xrce-dds.docs.eprosima.com `agent.html` |
| 8 | 「echo 預設 reliable 收不到 BE」→ Jazzy echo 會依 publisher 自動選 QoS；`pub --once` 預設等 1 個訂閱者 | fixed | ros2/ros2cli jazzy `ros2topic/verb/echo.py`、`pub.py` |
| 8 | 「printf 會讓 agent 報錯」過度宣稱 → 改成「看不到且可能干擾」 | fixed / unverifiable | PICO `pico_uart_transport.c`（write 用 `putchar`，跟 printf 同一條 USB） |
