# 規格卡：ros2/（電腦端 Python：封包、ROS 2 bridge、假 Pico、測速、多板、node 範本）
> 用法（照 `../../考場SOP.md`）：模型寫【要卡】編號時，到 `../編號卡/` Ctrl-F 那個編號複製這張卡，包在 `<<<資料 開始>>>`…`<<<資料 結束>>>` 裡、最後一行寫「繼續」再貼。本檔編號：E01（規格卡 ROS）。每張 ≤ 1200 字元。
> 來源：`../../預製程式碼/說明書/02-ros2.md`、`../../預製程式碼/ros2/*`（行號已用 cat -n 核對）｜最後更新 2026-11-13

---

【規格卡｜ROS 1/10｜ros2/ 總覽：檔案、題型、接法】
以下是正確的參考資料（預製程式碼 2026-11-13 版）。和你的記憶不同時，以這張為準。
資料夾 `預製程式碼/ros2/`。所有 `.py` 要在同一資料夾執行（都 `from frame import ...`）。
| 檔案 | 行數 | 做什麼 | 題目 | 驗證 |
| `frame.py` | 153 | 封包 encode / 解析 / transact / diff | 電腦↔Pico 二進位封包 | 實跑 OK |
| `serial_bridge.py` | 108 | node：/numbers→Pico 加總→/sum；/bytes→CRC32→/crc | topic 進→板子算→topic 出 | 只用假 rclpy 跑 callback |
| `fake_pico.py` | 97 | pty 假裝 1～N 塊 Pico | 沒板子先測電腦端 | 實跑 OK |
| `bench.py` | 45 | 各 payload 大小的 RTT、吞吐量 | 一包多大、效能報告 | 對 fake 實跑 |
| `multi_device.py` | 87 | 切塊→N 個 port 平行→依序合併 | 2 塊板子加速 | 對 2 個 fake 實跑 |
| `node_template.py` | 85 | 最小 node：訂閱→處理→發布 | 寫 / 修 node | 沒實測 |
| `custom_msg_cheatsheet.md` | 84 | 陣列型別、自訂 .msg 步驟 | 傳陣列、自訂訊息 | 沒實測 |
| `README.md` | 91 | 用途表、改題順序、ros2 CLI 小抄 | 第一個打開 | 文件 |
- 其他 4 支 .py 都 import `frame.py`；Pico 端對應 `pico/serial_proto.h`、`serial_proto.c`、`app_serial.c`。
- 沒有在實體 Pico / USB 上測過；ros2 CLI 指令都沒實測。
- 加新 cmd 的順序：`frame.py:17` 加常數 → `fake_pico.py:33` 的 `handle()` 加運算 → `serial_bridge.py:68` / `multi_device.py:69-72` 改合併 → Pico `serial_proto.h:18-20` 同步。
- 列出全部要改處：`grep -n "TODO(改這裡)" *.py`
- 先用 fake_pico 測電腦端，再換真板子。
要看程式：見各列的行號

---

【規格卡｜ROS 2/10｜frame.py：封包格式與 CRC（逐 byte）】
以下是正確的參考資料（預製程式碼 2026-11-13 版）。和你的記憶不同時，以這張為準。
定義在 `frame.py:4-6`、`encode()` `frame.py:22-25`。**必須和 Pico 端 `pico/serial_proto.c` 逐 byte 相同**（送 `proto_send()` :92-101，收 `proto_feed()` :39-76，格式 `serial_proto.h:3-7`；已實測一致）。
| 位移 | 欄位 | 大小 | 說明 |
| 0-1 | sync | 2 B | 固定 `AA 55`（`HDR`，frame.py:16） |
| 2 | cmd | u8 | 01 ECHO 原樣回 / 02 SUM_U32 回 u32 總和 mod 2^32 / 03 CRC32 回 u32 |
| 3 | seq | u8 | 回覆帶回同值（`seq & 0xFF`） |
| 4-5 | len | u16 小端 | payload 長度（低位元組在 4） |
| 6.. | payload | len B | SUM_U32 時 = u32 小端陣列 |
| 最後 4 | crc32 | u32 小端 | 範圍 = cmd 到 payload 結尾（不含 AA 55、不含 crc） |
- 整包 = 10 + len bytes。回覆用同格式、同 cmd、同 seq。
CRC = CRC-32/ISO-HDLC = Python `zlib.crc32`：
| 參數 | 值 |
| 多項式 | 0x04C11DB7（反射寫法 0xEDB88320，serial_proto.c:18） |
| 輸入 / 輸出 | 都反射（LSB 先） |
| 初值 | 0xFFFFFFFF（serial_proto.c:27） |
| 最後 XOR | 0xFFFFFFFF（serial_proto.c:29） |
| check("123456789") | 0xCBF43926 |
- 可接著算：C `crc32_update(prev, p, n)`（serial_proto.h:32-33）= Python `zlib.crc32(b, prev)`。
實例（實測）：
- ECHO seq=7 "hi" = `aa 55 01 07 02 00 68 69 ce 5e fd fb`
- SUM_U32 seq=1 [10,1] = `aa 55 02 01 08 00 0a 00 00 00 01 00 00 00 69 bc cb 6c`
要看程式：請操作者貼「cat -n frame.py | sed -n 16,25p」

---

【規格卡｜ROS 3/10｜frame.py：函式、常數、長度上限】
以下是正確的參考資料（預製程式碼 2026-11-13 版）。和你的記憶不同時，以這張為準。
| 函式 | 行號 | 回傳 | 注意 |
| `encode(cmd, seq, payload=b"")` | frame.py:22-25 | 整包 bytes | len ≥ 65536、cmd > 255 → `struct.error` |
| `pack_u32(values)` / `unpack_u32(data)` | :28-30 / :33-35 | u32 小端 bytes / int list | -1 → ff ff ff ff |
| `FrameParser(max_len=MAX_LEN)` | :38-46 | 解析器 | 計數 `.bad_crc`、`.bad_len` |
| `FrameParser.feed(data)` | :48-74 | `[(cmd, seq, payload), ...]` | 半包留著；CRC 錯或 len > max_len → 刪 1 byte 重找 AA 55 |
| `transact(ser, cmd, payload, seq=0, timeout=1.0, retries=3)` | :77-92 | 回覆 payload | 只收同 cmd 同 seq；全失敗 `TimeoutError`（最壞 3 秒） |
- `ser = serial.Serial(port, timeout=0.05)`。
| 常數 | 位置 | 值 | 意思 |
| `CMD_ECHO, CMD_SUM_U32, CMD_CRC32` | frame.py:17 | 0x01, 0x02, 0x03 | TODO(改這裡) 新指令加後面 |
| `MAX_LEN` | frame.py:18 | 8192 | parser 上限 |
| `CHUNK_BYTES` | frame.py:19 | 4096 | TODO(改這裡) 電腦端一包上限 |
| `FRAME_MAX_PAYLOAD` | pico/serial_proto.h:23 | 8192 | Pico 上限；len > 8192 丟掉、不回 |
- `CHUNK_BYTES` ≤ `MAX_LEN` = `FRAME_MAX_PAYLOAD`。8192 本身可以（判斷用 `>`）。
- Pico 改大 → `MAX_LEN` 一起改。Pico buffer 只有 N → `CHUNK_BYTES = N // 4 * 4`。
要看程式：請操作者貼「cat -n frame.py | sed -n 38,92p」

---

【規格卡｜ROS 4/10｜serial_bridge.py：參數、topic、批次、例外】
以下是正確的參考資料（預製程式碼 2026-11-13 版）。和你的記憶不同時，以這張為準。
node 名 `serial_bridge`（:33）。
| 參數 | 行號 | 預設 | 意思 |
| `port` | :34 | "/dev/ttyACM0" | TODO(改這裡) |
| `batch_size` | :35 | 0 | TODO(改這裡) ≤0 = 塞滿 4096 B；N = 一包 N 個 |
| `timeout` | :36 | 1.0 | 等回覆秒數 |
| `retries` | :37 | 3 | 逾時重送次數 |
| topic | 方向 | 型別（std_msgs/msg/） | 程式 |
| `/numbers` | 訂閱 | Int32MultiArray | `on_numbers()` :59-74 |
| `/bytes` | 訂閱 | UInt8MultiArray | `on_bytes()` :76-91 |
| `/sum` | 發布 | UInt32 | :48 TODO(改這裡) |
| `/crc` | 發布 | UInt32 | :49 |
- QoS 全用 `10`。
- 上限（:40-42）：`batch_size*4 > MAX_LEN` → 改成 2048 並印 WARN。
- 切包（:63）：`step = 4*batch`；batch ≤ 0 → 4096。
- 合併（:68 TODO）：`total = (total + unpack_u32(reply)[0]) & 0xFFFFFFFF`。CRC 不能這樣合併。
- `on_bytes`（:81-83）：> 4096 B 不送，log `… 超過一包上限 4096，CRC 不能分包算`。
- 例外（:69、:86）：接 `(TimeoutError, serial.SerialException)` → log error、不發布、node 繼續跑。port 打不開（:45）node 起不來。
- `send()`（:54-57）：seq +1 取低 8 bit。spin 單執行緒（:98），不用鎖。
執行：`python3 serial_bridge.py --ros-args -p port:=/dev/pts/N -p batch_size:=0`；pub `/numbers` `"{data: [1, 2, 3]}"` → /sum `data: 6`。
要看程式：請操作者貼「cat -n serial_bridge.py | sed -n 31,91p」

---

【規格卡｜ROS 5/10｜fake_pico.py：用法、和真 Pico 的差異】
以下是正確的參考資料（預製程式碼 2026-11-13 版）。和你的記憶不同時，以這張為準。
只用 Python 標準函式庫。`os.openpty()` 開虛擬序列埠；你的程式開它印出的 `/dev/pts/N`。
| 指令 | 效果 |
| `python3 fake_pico.py` | 1 個，印 `[fake_pico] fake0: /dev/pts/N` |
| `python3 fake_pico.py -n 2 --link /tmp/ttyFAKE` | 2 個 + 捷徑 /tmp/ttyFAKE0、/tmp/ttyFAKE1 |
| 加 `--us-per-byte 1` | 每 byte payload 多睡 1 µs（模擬算得慢） |
- 要一直開著，另開終端機跑你的程式。Ctrl+C / kill 會刪捷徑。
| 函式 | 行號 | 做什麼 |
| `handle(cmd, payload)` | :25-34 | ECHO 原樣；SUM_U32 u32 總和 mod 2^32；CRC32 `zlib.crc32`；不認得回 None = 不回覆 |
| `serve(name, fd, us_per_byte)` | :37-55 | 讀 → FrameParser → handle → 寫到完 |
| `main()` | :58-93 | 開 pty、`tty.setraw()`（:68-69）、每塊一條執行緒 |
- TODO(改這裡) `fake_pico.py:33`：在 `return None` 前加 `if cmd == CMD_XXX: return ...`，和 Pico `app_serial.c` 邏輯一致；:22 import 加新常數；改完要重開。
| 項目 | fake_pico | 真 Pico |
| payload 上限 | 8192，超過丟掉不回 | 8192 |
| 收一半停住 | 一直等 | 閒置 100 ms 自動 `proto_reset()`（app_serial.c:73-74） |
| 不認得 cmd | 不回，終端機印 `不認得的 cmd=…，不回覆` | 不回，不印 |
| CRLF / printf | raw pty，不會發生 | 會發生 |
| 一次來回 | 幾十 µs | USB ≥ 1 ms（未驗證） |
- fake 通過 ≠ 真板子通過。題目 Pico buffer N < 8192 時 fake 擋不住。
要看程式：請操作者貼「cat -n fake_pico.py | sed -n 25,55p」

---

【規格卡｜ROS 6/10｜bench.py、multi_device.py：測速、多板平行】
以下是正確的參考資料（預製程式碼 2026-11-13 版）。和你的記憶不同時，以這張為準。
bench.py：每種大小送 iters 次 ECHO 並比對。
- `python3 bench.py /dev/pts/5 --sizes 4,64,1024,4096 --iters 200`
- 參數：port（:35）、`--sizes`（:36 TODO，≤ 8192）、`--iters`（:37，100）。
- `bench(ser, size, iters)`（:21-30）回（平均 RTT 秒, bytes/s）；內容不同丟 `RuntimeError`。包越大吞吐量越高。
multi_device.py（不需 ROS）：
- `python3 fake_pico.py -n 2 --link /tmp/ttyFAKE --us-per-byte 1`，再 `python3 multi_device.py /tmp/ttyFAKE0 /tmp/ttyFAKE1`；真板 `/dev/ttyACM0 /dev/ttyACM1`。
- ≥ 2 個 port：先用第 1 個跑，再全部跑（:83）。
| 函式 | 行號 | 做什麼 |
| `split(data, chunk_bytes=CHUNK_BYTES, align=4)` | :24-27 | 每塊 ≤ chunk_bytes 且 4 的倍數 |
| `worker(port, jobs, results, cmd, stats)` | :30-48 | 一 port 一執行緒搶佇列，失敗放 None |
| `run_parallel(ports, chunks, cmd)` | :51-66 | 依 chunk 順序的 reply list；有 None 丟 `RuntimeError` |
| `merge_sum(replies)` | :69-72 | TODO(改這裡) u32 加總 & 0xFFFFFFFF |
- 合併換法：最大值 `max(unpack_u32(r)[0] for r in replies)`；排序 `list(heapq.merge(*[unpack_u32(r) for r in replies]))`；CRC32 不能加。
- 其他 TODO：:76 ports、:77 資料、:85 cmd（:80 `expect` 跟著改）。
- 成功：`正確=True`，`每個 port 做了幾塊: {…: 98, …: 98}`，實測 882 ms → 442 ms。
要看程式：請操作者貼「cat -n multi_device.py | sed -n 24,72p」

---

【規格卡｜ROS 7/10｜node_template.py：改哪幾行、QoS 規則】
以下是正確的參考資料（預製程式碼 2026-11-13 版）。和你的記憶不同時，以這張為準。
`/number`(Int32) → 乘 factor → `/double`(Int32)，node 名 `processor`。沒實測。
| 行號 | 現在 | 改法 |
| :18 | `from std_msgs.msg import Int32` | TODO 換型別，連同 :45、:46、:53、:59、:66 |
| :23-28 | `QOS`：depth 10、RELIABLE、VOLATILE | pub、sub 共用 |
| :26 | `RELIABLE` | TODO 對方 BEST_EFFORT 發布 → 改 BEST_EFFORT |
| :27 | `VOLATILE` | 對方訂閱 TRANSIENT_LOCAL → 改 TRANSIENT_LOCAL |
| :33 | `"processor"` | TODO 題目指定的 node 名 |
| :36 / :37 | `"/number"` / `"/double"` | TODO 輸入 / 輸出 topic |
| :38-39 | `factor`=2、`tick_period`=0.0 | 照型別覆蓋：`factor:=3` |
| :60 | `out.data = msg.data * self.factor` | TODO 處理邏輯 |
| :61 | `self.pub.publish(out)` | 沒 publish = 沒輸出 |
| :76 | `rclpy.spin(node)` | 沒 spin = callback 永不執行 |
- 改收 Int32MultiArray：:18 加 import、:46 換型別、:60 改 `sum(msg.data) * self.factor`。
QoS：
- 發 BEST_EFFORT + 收 RELIABLE → 收不到；反過來可以。
- 發 VOLATILE + 收 TRANSIENT_LOCAL → 收不到；其他組合可以。
- 數字 `10` = RELIABLE、VOLATILE、depth 10（:22）。
- topic 名要 `/` 開頭；`number` 會被加 namespace。
驗證：`ros2 topic pub --once /number std_msgs/msg/Int32 "{data: 21}"` → /double `data: 42`。
要看程式：請操作者貼「cat -n node_template.py | sed -n 18,63p」

---

【規格卡｜ROS 8/10｜ros2 CLI 除錯順序】
以下是正確的參考資料（預製程式碼 2026-11-13 版）。和你的記憶不同時，以這張為準。
出處 `README.md:33-69`（沒實測）。每個新終端機先 `source /opt/ros/jazzy/setup.bash`（否則 `ros2: command not found`）。
順序：node 在不在 → topic 在不在 → 兩端同一個 topic → count 合理 → 真的有資料。
| 步 | 指令 | 看什麼 → 不對時 |
| 1 | `ros2 node list` | node 有沒有出現 |
| 2 | `ros2 node info /processor` | 訂閱 / 發布哪些 topic、型別 |
| 3 | `ros2 topic list -t` | 很像的名字（/double vs /doubel）、少 `/`、同名兩種型別 |
| 4 | `ros2 topic info /x` | Publisher / Subscription count 有 0 → 那端名字錯 |
| 5 | `ros2 topic info -v /x` | 各端 Reliability / Durability / Node name → QoS 不相容 |
| 6 | `ros2 topic echo /x` | 有沒有資料（`--once`、`--field data`） |
| 7 | `ros2 topic pub --once /number std_msgs/msg/Int32 "{data: 21}"` | 一直不結束 = 沒人訂閱 → topic 名字 |
- `History (Depth): UNKNOWN` 是正常的。
- 兩個 publisher 同 topic：count 2、資料交錯、不報錯。
- QoS 測試時 CLI 也要配合：`ros2 topic echo --qos-reliability best_effort /x`。
- 改名不改程式：`--ros-args -p in_topic:=/number` 或 `-r /numbr:=/number`。
- 其他：`ros2 topic hz /x`、`ros2 param get /processor factor`；colcon build 完一定 `source install/setup.bash`。
要看程式：請操作者貼「cat -n README.md | sed -n 33,91p」

---

【規格卡｜ROS 9/10｜custom_msg_cheatsheet.md：自訂 msg】
以下是正確的參考資料（預製程式碼 2026-11-13 版）。和你的記憶不同時，以這張為準。
先用內建型別（:6-13），不用自訂：
| 資料 | 型別（std_msgs/msg/） | Python `msg.data` |
| 一串 bytes | `UInt8MultiArray` | `array('B')` |
| 一串 int32 | `Int32MultiArray` | `array('i')` |
- 不要用 `ByteMultiArray`（很慢）。
- 快的打包：`array.array('i', m.data).tobytes()`（小端）。
自訂 .msg 步驟（:39-78，沒實測）：
1. `ros2 pkg create --build-type ament_cmake my_interfaces`（:43 TODO 套件名；必須 ament_cmake）
2. `msg/Job.msg`：檔名大寫開頭，欄位小寫底線（`uint8[] payload`）
3. CMakeLists.txt（`ament_package()` 前）：`find_package(rosidl_default_generators REQUIRED)`、`rosidl_generate_interfaces(${PROJECT_NAME} "msg/Job.msg")`、`ament_export_dependencies(rosidl_default_runtime)`
4. package.xml：`<buildtool_depend>rosidl_default_generators</buildtool_depend>`、`<exec_depend>rosidl_default_runtime</exec_depend>`、`<member_of_group>rosidl_interface_packages</member_of_group>`
5. `colcon build --packages-select my_interfaces && source install/setup.bash && ros2 interface show my_interfaces/msg/Job`
- 使用端 package.xml 加 `<exec_depend>my_interfaces</exec_depend>`。
- `ModuleNotFoundError: my_interfaces` → 沒 source。
要看程式：請操作者貼「cat -n custom_msg_cheatsheet.md | sed -n 39,84p」

---

【規格卡｜ROS 10/10｜陷阱與驗證（frame.py diff）】
以下是正確的參考資料（預製程式碼 2026-11-13 版）。和你的記憶不同時，以這張為準。
封包對不上 → 跑 `python3 frame.py diff "預期hex" "實際hex"`（frame.py:126-131），不要自己數 byte。兩段都要加引號；參數不是 3 個會印 `用法: python3 frame.py diff "預期 hex" "實際 hex"（兩個都要加引號）`。
輸出：`| 欄位 | 預期 | 實際 | 相同? |` 表格、`第一個不同：…`、`線索：…`。
| 線索原文 | 修法 |
| `實際有 0d 0a、預期沒有 → CRLF 轉換沒關` | Pico `stdio_set_translate_crlf(&stdio_usb, false)`、`PICO_STDIO_DEFAULT_CRLF=0` |
| `len 兩個 byte 對調 → 大小端顛倒` | Python 用 `<`；C 低位元組先送 |
| `開頭不是 aa 55 → 混入文字（printf）或少收 / 錯位` | Pico 端不要 printf |
| `實際封包的 crc32 對不上它自己的內容` | CRC 範圍、位元組順序或最後 XOR 錯 |
- 開頭混了 printf 的 `\r\n` 時也會印 CRLF 那條 → 先處理「開頭不是 aa 55」。
| 症狀 | 修法 |
| `No module named 'frame'` | 在 `ros2/` 裡跑 |
| `No module named 'serial'` | 考場不能自己裝：舉手問；或在題目給的容器裡跑 |
| `could not open port` | `ls /dev/ttyACM*`、`chmod 666`、Docker `--device` |
| 一直 `逾時，重試 k/3` | 先對 fake 測；包 ≤ 8192；Pico 認得 cmd、沒 printf |
| 回覆 167772160 不是 10 | 大小端反 → pack_u32 / unpack_u32 |
| `struct.error: 'H' format…` | payload ≥ 65536 → 先 split |
| baudrate 設 1200 | 板子重開進 BOOTSEL → 不要用 1200 |
驗證：`python3 frame.py` → `frame.py 自我測試 OK`；bridge log `20000 個數字, 20 包, 總和=…`；multi_device `正確=True`。
要看程式：請操作者貼「cat -n frame.py | sed -n 104,131p」
