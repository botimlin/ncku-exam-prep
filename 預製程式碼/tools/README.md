# tools/：考場基本工具手冊（索引）

> 每份都 ≤ 250 行，指令都實際跑過（除非標了「沒有實測」）。可以印出來，或一次貼一小節給本機的 LLM。
> 已經有的資料不重複：git / shell / docker → [`../../prompt工具包/cards/git-env.md`](../../prompt工具包/cards/git-env.md)；
> 症狀 → 原因大表 → [`../../prompt工具包/cards/04-debug.md`](../../prompt工具包/cards/04-debug.md)；
> ROS 2 基本 CLI → [`../ros2/README.md`](../ros2/README.md)。

## 遇到什麼情況 → 看哪一份

| 情況 | 檔案 | 章節 |
|---|---|---|
| cmake / make 報錯、看不懂錯誤訊息 | [`cmake.md`](cmake.md) | §6 錯誤對照表（22 種，全部實際製造過） |
| 看不懂題目的 CMakeLists.txt | [`cmake.md`](cmake.md) | §2 六個問題 |
| 要加 .c 檔、加函式庫、改 -O、加執行檔 | [`cmake.md`](cmake.md) | §3 |
| `#include "hardware/xxx.h"` 找不到、不知道要 link 什麼 | [`cmake.md`](cmake.md) | §4 函式庫名稱表 |
| colcon build 失敗、`ros2 run` 找不到 | [`cmake.md`](cmake.md) | §5 |
| 電腦上的 C 程式當掉（Segmentation fault） | [`debug-host.md`](debug-host.md) | §3 `gdb -batch -ex run -ex bt` |
| 結果怪怪的、有時候對有時候錯 | [`debug-host.md`](debug-host.md) | §1–2 sanitizer |
| 程式卡住不動 | [`debug-host.md`](debug-host.md) | §4 gdb + Ctrl-C、§5 strace |
| 檔案打不開、路徑錯 | [`debug-host.md`](debug-host.md) | §5 strace |
| Python 報錯 / 卡住 | [`debug-host.md`](debug-host.md) | §6 |
| 除錯訊息弄亂了評分的輸出 | [`debug-host.md`](debug-host.md) | §7 |
| 板子沒反應、不知道有沒有在跑 | [`debug-pico.md`](debug-pico.md) | §1 LED、§7 症狀表 |
| 燒錄、picotool | [`debug-pico.md`](debug-pico.md) | §2 |
| 看不到序列埠輸出、`/dev/ttyACM0` 打不開 | [`debug-pico.md`](debug-pico.md) | §3 |
| 想印除錯訊息但會弄壞二進位協定 | [`debug-pico.md`](debug-pico.md) | §4 |
| 程式太大、RAM 不夠、函式在 flash 還是 RAM | [`debug-pico.md`](debug-pico.md) | §5 `.dis` `.map` |
| 考場有給 Debug Probe | [`debug-pico.md`](debug-pico.md) | §6（沒有實測） |
| ROS node 看不到彼此、不同容器 | [`debug-ros2.md`](debug-ros2.md) | §7 DOMAIN_ID / DISCOVERY_RANGE |
| `ros2 topic list` 列出已經關掉的東西 | [`debug-ros2.md`](debug-ros2.md) | §8 `ros2 daemon stop` |
| 參數、remap、log 等級 | [`debug-ros2.md`](debug-ros2.md) | §2–4 |
| 評分用 rosbag、要自己錄來檢查 | [`debug-ros2.md`](debug-ros2.md) | §6 |
| VS Code 沒有擴充套件、找不到定義 | [`vscode.md`](vscode.md) | §1、§3 搜尋 |
| 要比較兩個檔案、看自己改了什麼 | [`vscode.md`](vscode.md) | §4 |
| 檔案在容器裡要怎麼改、容器沒有編輯器 | [`vscode.md`](vscode.md) | §6 |
| 不小心進了 vim 出不來 | [`vscode.md`](vscode.md) | §8：按 Esc，打 `:q!` Enter |

## 考場工具 SOP（10 步）

1. **開 repo**：`git clone` → `git log --oneline -5`（看出題者的 commit）→ `git tag start`（隨時可以回到原點）。
2. **讀說明**：`README.md`（VS Code 裡 Ctrl+Shift+V）→ 題目要什麼輸入、什麼輸出、怎麼評分。
3. **讀 `.gitlab-ci.yml`**：`script:` 就是評分的方法（用什麼 image、cmake 參數、執行什麼指令）—— 抄下來。
4. **讀 `CMakeLists.txt`**：用 `cmake.md` §2 的 6 個問題；`grep -rn "TODO\|FIXME\|BUG" --include='*.c' --include='*.py' .`。
5. **原封不動先 build 一次**：`cmake -S . -B build <CI 的參數> && cmake --build build -j8 2>&1 | tee build.log` → 看第一個 error（題目可能故意埋了 bug）。
6. **先跑起來**：電腦端 → 執行；Pico → 燒錄 → LED / 序列埠確認有在跑（`debug-pico.md` §1–3）；ROS → `ros2 node list`。
7. **在本機重現評分**：照 `.gitlab-ci.yml` 的指令跑一遍，把輸出存檔，跟題目的範例比對：`diff -u expected.txt out.txt`。
8. **除錯**：一次只改一個地方 → 重新 build → 重跑第 7 步。當掉用 gdb、結果怪用 sanitizer、卡住用 gdb+Ctrl-C/strace、ROS 用 `debug-ros2.md` §10。
9. **commit**：`git status` 確認**沒有** `build/`、`log/`、`install/`、除錯用的檔案 → 拿掉 DEBUG 輸出 → `git add 要的檔案` → `git commit -m "說明"`。
10. **push 一次、等 pipeline 結果**：看 job log 第一個錯誤 → 回到第 8 步。拿到分數的版本馬上 `git tag ok-v1`，之後再優化。

## 驗證環境（2026-11 在這台電腦上）

| 工具 | 版本 / 位置 | 備註 |
|---|---|---|
| 主機 | Ubuntu 24.04、gcc 13.3、gdb 15.1、strace、perf、python3.12 + pyserial 3.5、nano 7.2、vim.tiny 9.1 | **沒有** cmake、ltrace、valgrind、screen、picocom、minicom、gdb-multiarch、openocd |
| `pico-build` 容器 | CMake 3.28、arm-none-eabi-gcc 13.2.1、pico-sdk 2.2.0（`/opt/pico-sdk`） | 沒有 gdb、沒有編輯器、沒有 libusb（→ picotool 沒有 USB 功能） |
| `ros:jazzy-ros-core` | ROS 2 Jazzy、rmw_fastrtps_cpp | 沒有 colcon、gcc、`ros2 bag`、demo nodes、編輯器（apt 裝在拋棄式容器測試） |
