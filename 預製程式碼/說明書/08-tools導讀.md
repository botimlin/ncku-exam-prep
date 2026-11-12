# 第 8 章　tools/：考場工具導讀（CMake、除錯、序列埠、ROS 2、VS Code）

> 本章對應的檔案：`tools/README.md`、`cmake.md`、`debug-host.md`、`debug-pico.md`、`debug-ros2.md`、`vscode.md`｜驗證狀態：指令大多實跑過，沒實測的在原文標「沒有實測」｜最後核對：2026-11-12
>
> 這一章是導讀：告訴你遇到什麼狀況該翻哪一份、哪一節，並把最常用的指令整理在一起。5 份手冊的全文在 PDF 版的附錄 A～E（Markdown 版直接打開 `tools/` 裡的檔案）。

## 8.0 30 秒版

- build 失敗 → `cmake.md` §6 錯誤對照表（22 種，每一種都實際製造過），**只看第一個 error**。
- 程式當掉（Segmentation fault） → `debug-host.md` §3：`gdb -batch -ex run -ex bt ./程式`。
- 結果有時對有時錯 → `debug-host.md` §1–2：加 `-fsanitize=address,undefined` 或 `-fsanitize=thread`。
- 板子沒反應 → `debug-pico.md` §1（LED）、§7（症狀表）。
- 序列埠看不到東西 → `debug-pico.md` §3：同一時間只能有一個程式打開 `/dev/ttyACM0`。
- ROS node 收不到 → `debug-ros2.md` §10：5 個指令。
- 誤入 vim → 按 `Esc`，打 `:q!`，按 Enter。

## 8.1 檔案總表

| 檔案 | 行數 | 做什麼 | 什麼時候用 | 驗證狀態 |
|---|---|---|---|---|
| `tools/README.md` | 57 | 索引 + 考場工具 SOP（10 步）+ 驗證環境 | 開考時照 SOP 走 | ✅ |
| `tools/cmake.md` | 215 | CMake 觀念、讀 CMakeLists 的 6 個問題、常見修改、pico-sdk 專用寫法、colcon、22 種錯誤對照 | build 相關的任何問題 | ✅（RISC-V 工具鏈那列是「找不到編譯器」的實測） |
| `tools/debug-host.md` | 212 | 除錯 / 正式編譯參數、sanitizer 輸出怎麼讀、gdb、卡住、strace、Python 除錯、printf 紀律 | 電腦上的 C / Python 出錯 | ✅ |
| `tools/debug-pico.md` | 189 | LED 確認、燒錄與 picotool、序列埠監看、除錯訊息不弄壞協定、`.dis`/`.map`、Debug Probe、症狀表 | Pico 端出錯 | ⚠️ 燒錄、實體序列埠、Debug Probe 沒有實測 |
| `tools/debug-ros2.md` | 174 | `ros2 doctor`、log、參數、remap、QoS、rosbag、看不到對方、daemon、坑、速查 | ROS 2 進階除錯 | ✅（在 `ros:jazzy-ros-core` 容器裡） |
| `tools/vscode.md` | 164 | 沒有擴充套件的 VS Code、快捷鍵、搜尋、比較檔案、tasks.json、容器內編輯、nano、vim | 編輯器 | ✅ |

## 8.2 考場工具 SOP（10 步，出自 `tools/README.md`）

| 步驟 | 做什麼 | 指令 | 細節 |
|---|---|---|---|
| 1 | 開 repo、留原點 | `git clone …`、`git log --oneline -5`、`git tag start` | 隨時 `git diff start` 看自己改了什麼 |
| 2 | 讀說明 | VS Code 開 `README.md`，Ctrl+Shift+V 預覽 | 輸入、輸出、評分方式 |
| 3 | 讀 `.gitlab-ci.yml` | `cat .gitlab-ci.yml` | `script:` 就是評分方法，抄下 image、cmake 參數、執行指令 |
| 4 | 讀 `CMakeLists.txt`、找埋的 bug | `grep -rn "TODO\|FIXME\|BUG" --include='*.c' --include='*.py' .` | `cmake.md` §2 的 6 個問題 |
| 5 | 原封不動先 build | `cmake -S . -B build <CI 的參數> && cmake --build build -j8 2>&1 \| tee build.log` | 題目可能故意埋了 build bug |
| 6 | 先跑起來 | 電腦程式直接跑；Pico 燒錄後看 LED / 序列埠；ROS 用 `ros2 node list` | `debug-pico.md` §1–3 |
| 7 | 在本機重現評分 | 照 `.gitlab-ci.yml` 的指令跑，存輸出，`diff -u expected.txt out.txt` | |
| 8 | 除錯 | 一次改一處 → build → 回第 7 步 | 當掉 gdb、結果怪 sanitizer、卡住 gdb+Ctrl-C / strace、ROS `debug-ros2.md` §10 |
| 9 | commit | `git status`（沒有 `build/`、`log/`、`install/`）→ 拿掉 DEBUG 輸出 → `git add 檔案` → `git commit -m "說明"` | commit message 格式照題目規定 |
| 10 | push 一次、等結果 | `git push` → 看 pipeline 的 job log 第一個錯誤 | 拿到分數就 `git tag ok-v1`，再優化 |

## 8.3 遇到什麼情況 → 看哪裡

| 情況 | 檔案 | 章節 |
|---|---|---|
| cmake / make 報錯、看不懂錯誤訊息 | `cmake.md` | §6 錯誤對照表 |
| 看不懂題目的 CMakeLists.txt | `cmake.md` | §2 六個問題 |
| 要加 .c 檔、加函式庫、改 -O、加執行檔 | `cmake.md` | §3 |
| `#include "hardware/xxx.h"` 找不到、不知道要 link 什麼 | `cmake.md` | §4 函式庫名稱表 |
| colcon build 失敗、`ros2 run` 找不到 | `cmake.md` | §5 |
| 電腦上的 C 程式當掉 | `debug-host.md` | §3 |
| 結果怪怪的、有時候對有時候錯 | `debug-host.md` | §1–2 sanitizer |
| 程式卡住不動 | `debug-host.md` | §4 gdb + Ctrl-C、§5 strace |
| Python 報錯 / 卡住 | `debug-host.md` | §6 |
| 除錯訊息弄亂了評分的輸出 | `debug-host.md` | §7 |
| 板子沒反應 | `debug-pico.md` | §1 LED、§7 症狀表 |
| 燒錄、picotool | `debug-pico.md` | §2 |
| 看不到序列埠輸出、`/dev/ttyACM0` 打不開 | `debug-pico.md` | §3 |
| 想印除錯訊息但會弄壞二進位協定 | `debug-pico.md` | §4 |
| 程式太大、RAM 不夠、函式在 flash 還是 RAM | `debug-pico.md` | §5 |
| 考場有 Debug Probe | `debug-pico.md` | §6（沒有實測） |
| ROS node 看不到彼此、不同容器 | `debug-ros2.md` | §7 |
| `ros2 topic list` 列出已經關掉的東西 | `debug-ros2.md` | §8 `ros2 daemon stop` |
| 參數、remap、log 等級 | `debug-ros2.md` | §2–4 |
| QoS 不相容 | `debug-ros2.md` | §5 |
| 評分用 rosbag、要自己錄來檢查 | `debug-ros2.md` | §6 |
| VS Code 找不到定義、要全域搜尋 | `vscode.md` | §1、§3 |
| 比較兩個檔案、看自己改了什麼 | `vscode.md` | §4 |
| 檔案在容器裡、容器沒有編輯器 | `vscode.md` | §6 |
| 誤入 vim | `vscode.md` | §8 |

## 8.4 build 失敗時的判讀順序（出自 `cmake.md` §6）

1. 分清楚是哪一種錯：
   - **configure 錯**：`CMake Error at CMakeLists.txt:行號` → 改 `CMakeLists.txt`。
   - **compile 錯**：`檔名.c:行:欄: error:` → 改程式。
   - **link 錯**：`undefined reference`、`cannot find -l…`、`ld returned 1 exit status` → 少連結函式庫或函式沒定義。
2. 只看**第一個** error，後面常常是它連帶造成的。
3. `gmake[2]: *** … Error 1` 只是「失敗了」的通知，原因在它上面。
4. 改了 `PICO_BOARD`、`PICO_SDK_PATH`、工具鏈，或搬過資料夾 → `rm -rf build` 重新 configure。

pico-sdk 最常見的 5 個錯誤（完整 22 種見 `cmake.md` §6）：

| 關鍵錯誤訊息 | 修法 |
|---|---|
| `SDK location was not specified.  Please set PICO_SDK_PATH` | `export PICO_SDK_PATH=/opt/pico-sdk`（考場路徑以題目為準）後 `rm -rf build` |
| `boot2_w25q080.S:22: Error: unknown pseudo-op: '.syntax'` | `include(pico_sdk_import.cmake)` 移到 `project()` 前面，`rm -rf build` |
| `Unknown CMake command "pico_enable_stdio_usb"` | 在 `project()` 後面補 `pico_sdk_init()` |
| `fatal error: hardware/dma.h: No such file or directory` | `target_link_libraries(x hardware_dma)` |
| `undefined reference to 'dma_encode_transfer_count'` | SDK 2.0 / 2.1 沒有這個函式 → 直接填筆數，或照 `pico/app_dma.c` 補相容函式（第 3 章） |

`#include` → 要 link 的名字（`cmake.md` §4）：

| `#include` | `target_link_libraries` |
|---|---|
| `pico/stdlib.h` | `pico_stdlib` |
| `hardware/dma.h` | `hardware_dma` |
| `hardware/pio.h` | `hardware_pio` |
| `pico/multicore.h` | `pico_multicore` |
| `pico/mutex.h`、`pico/sem.h`、`pico/critical_section.h` | `pico_sync` |
| `hardware/sync.h`、`pico/util/queue.h`、`hardware/uart.h`、`hardware/gpio.h` | 已包含在 `pico_stdlib` |

## 8.5 電腦端除錯指令速查（出自 `debug-host.md`）

| 目的 | 指令 |
|---|---|
| 除錯版編譯 | `gcc -O0 -g -Wall -Wextra -fsanitize=address,undefined -fno-omit-frame-pointer x.c -o x` |
| 找 data race | `gcc -O1 -g -fsanitize=thread x.c -o x -pthread`（不能和 address 一起用） |
| 當掉時印呼叫堆疊 | `gdb -batch -ex run -ex bt --args ./x 參數` |
| 卡住時看每個執行緒在哪 | 在 gdb 裡執行（`gdb --args ./x 參數` → `run`）→ 卡住時按 Ctrl-C → `thread apply all bt`（`gdb -p PID` 在實測環境被 ptrace_scope 擋住） |
| 看開了哪些檔案、哪個失敗 | `strace -f -e trace=openat,read,write ./x` |
| Python 一步一步跑 | `python3 -m pdb x.py` → `b 函式名`、`c`、`n`、`s`、`p 變數`、`where`、`q` |
| Python 卡住時印堆疊 | 程式開頭加 `import faulthandler, signal; faulthandler.register(signal.SIGUSR1)`，卡住時 `kill -USR1 PID` |
| Python 的 C 擴充模組 segfault | `python3 -X faulthandler x.py` |

sanitizer 的報告要找「第一個在你程式裡的 frame」（`#0` 往下數，第一個檔名是你的 `.c` 的那一行）。

## 8.6 Pico 端除錯指令速查（出自 `debug-pico.md`）

| 目的 | 指令 / 方法 |
|---|---|
| 燒錄（最可靠） | 按住 BOOTSEL 插 USB → 出現磁碟 `RP2350` → `cp build/app.uf2 /media/$USER/RP2350/` |
| 用 picotool 燒錄 | `picotool load -x build/app.uf2 -f`（pico-build 容器裡 SDK 編的 picotool 沒有 USB 功能，會 `Unknown command`） |
| 看 .uf2 是什麼程式、哪顆晶片 | `picotool info -a build/app.uf2`（不用板子） |
| 列出序列埠 | `ls /dev/ttyACM* /dev/serial/by-id/`、`python3 -m serial.tools.list_ports` |
| 監看文字輸出 | `python3 -m serial.tools.miniterm /dev/ttyACM0 115200`（離開：Ctrl-]） |
| 一定有的監看方法 | `stty -F /dev/ttyACM0 raw -echo; cat /dev/ttyACM0` |
| 看二進位 | `cat /dev/ttyACM0 \| xxd` |
| 開機先等電腦開序列埠 | `target_compile_definitions(x PRIVATE PICO_STDIO_USB_CONNECT_WAIT_TIMEOUT_MS=3000)` |

注意：
- **不要用 1200 baud 打開序列埠**：會讓板子重開進 BOOTSEL（SDK 預設 `PICO_STDIO_USB_RESET_MAGIC_BAUD_RATE=1200`）。
- 同一時間只能有一個程式打開序列埠。監看程式開著，bridge 或 `micro_ros_agent` 就讀不到。
- `Permission denied: '/dev/ttyACM0'`：用 `sudo`，或在用 `--device` 啟動的容器裡以 root 執行。
- Release 版（SDK 預設）有 `-DNDEBUG`，`assert` 整個消失；要檢查用 `hard_assert`。
- 二進位協定不要混 `printf`：除錯訊息改走 UART（GP0/GP1）、LED，或在協定裡加一個除錯指令。

## 8.7 ROS 2 除錯速查（出自 `debug-ros2.md` §10 與官方練習 section2-1）

一個 node 沒反應時，依序跑（`debug-ros2.md` §10）：

```bash
ros2 node list
```

```bash
ros2 node info /你的node
```

```bash
ros2 topic info -v /你的topic
```

```bash
ros2 topic hz /你的topic
```

```bash
ros2 run 套件 執行檔 --ros-args --log-level 你的node:=debug
```

1. 它有在跑嗎、名字對嗎？ 2. 它訂閱 / 發布了哪些 topic？ 3. 兩端都有嗎、QoS 一樣嗎？ 4. 輸入有在進來嗎、多快？ 5. 看它自己的 debug 訊息。要看資料內容用 `ros2 topic echo /你的topic`。

- 名稱差一個字元就是另一個 topic；`ros2 topic info` 某一側數量是 0 就是沒接上。
- `ros2 topic info -v` 會列出兩邊的 QoS；reliable 的 subscriber 收不到 best_effort 的 publisher。
- 列出已經關掉的 node → `ros2 daemon stop` 再查一次。
- 兩個容器看不到對方 → 每個終端機的 `ROS_DOMAIN_ID`、`ROS_AUTOMATIC_DISCOVERY_RANGE` 要一樣（`printenv | grep ROS_`；`debug-ros2.md` §7）。
- 自己送測試資料：`ros2 topic pub --once /number std_msgs/msg/Int32 "{data: 21}"`。

## 8.8 VS Code 與編輯器速查（出自 `vscode.md`）

| 目的 | 按鍵 |
|---|---|
| 找檔案 | Ctrl+P |
| 全部檔案搜尋 | Ctrl+Shift+F |
| 跳到某一行 | Ctrl+G |
| 開終端機 | Ctrl+` |
| Markdown 預覽 | Ctrl+Shift+V |
| 比較兩個檔案 | 檔案總管選兩個檔案 → 右鍵「Compare Selected」 |
| nano 存檔 / 離開 | Ctrl+O Enter / Ctrl+X |
| vim 不存檔離開 | Esc，`:q!`，Enter |

沒有 C/C++ 擴充套件時「跳到定義」不能用，改用 Ctrl+Shift+F 搜尋函式名稱，或在終端機 `grep -rn "函式名(" .`。
