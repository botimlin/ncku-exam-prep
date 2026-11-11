# 貼上卡：除錯
> 用法：一次只複製一張卡（兩條分隔線之間），把 `{{...}}` 換成你的內容，貼進對話送出。提示卡＝直接用的問句；參考卡＝貼給模型當正確資料。每張 ≤ 1200 字元。
> 來源：full/04-debug.md、lite/04-debug.md（詳細版）｜最後更新 2026-11

---

【提示卡｜除錯 1/6｜錯誤回報格式】
請幫我除錯。資訊如下：
- 做了什麼：我執行了 {{指令}}，目的是 {{目的}}
- 預期：{{應該發生什麼}}
- 實際：{{實際發生什麼}}
- 完整錯誤訊息（編譯錯誤貼「第一個」error 及其前後）：
{{貼錯誤}}
- 相關程式碼（出錯的函式、最近改過的地方）：
{{貼程式碼}}
- 最近改了什麼：{{上次能用之後改了哪些}}
- 已經試過：{{試過什麼、結果如何}}
- 環境：{{Linux 容器 / 開發板（RP2350 Pico 2）；ARM 或 RISC-V；編譯指令}}

請：
1. 列出可能原因，依可能性排序
2. 每個原因給一個驗證方法
3. 給最可能的修正
不要一次給大量修改。不確定存在的 API 標【推測】。

---

【提示卡｜除錯 2/6｜設計區分假設的實驗】
我懷疑問題是 {{假設 A}} 或 {{假設 B}}。
- 症狀：{{描述}}
- 相關程式碼：
{{貼程式碼}}

請設計一個最小的實驗（加 print、改輸入、註解掉某段）來區分這兩個假設，並說明每種結果分別代表什麼。
只設計實驗，先不要修改程式。

---

【提示卡｜除錯 3/6｜看不懂的錯誤訊息】
這個錯誤訊息是什麼意思？最常見的 3 個原因是什麼？我該先檢查哪個？
- 環境：{{Linux 容器 / RP2350（Pico 2）+ pico-sdk / ROS 2 Jazzy；編譯指令}}
- 錯誤訊息（貼完整，不要只貼最後一行）：
{{貼錯誤訊息}}
如果有很多個 error，只分析第一個，後面的常是它連鎖引起的。

---

【提示卡｜除錯 4/6｜修好了但不知道為什麼】
我把 {{改動}} 之後問題消失了，但我不確定根本原因。
- 原本的症狀：{{描述}}
- 改動前後的程式碼：
{{貼修改前 / 修改後}}

請解釋：
1. 為什麼這個改動能修好問題
2. 它是否只是掩蓋了問題（例如時序剛好改變）
3. 要怎麼確認真的修好（例如多跑幾十次看結果是否每次一樣）

---

【參考卡｜除錯 5/6｜症狀→原因：編譯、連結、崩潰、卡住】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
編譯 / 連結：
- 一堆錯誤 → 只修第一個 error，再重編
- `implicit declaration` / `unknown type name` → 少 `#include` 或名稱拼錯；`grep -rn 名稱 $PICO_SDK_PATH/src --include=*.h`
- `expected ';' before` → 錯常在前一行
- header `No such file` / `undefined reference` → pico-sdk 的 CMakeLists.txt `target_link_libraries(... hardware_xxx pico_xxx)` 沒加；pthread 加 `-pthread`；math 加 `-lm`
- `multiple definition` → header 裡的變數要 `extern`，定義只放一個 .c
- `region 'RAM' overflowed` → 縮小 buffer、常數改 const 放 flash
崩潰：
- Linux：`gcc -g -O0 -fsanitize=address,undefined`；`gdb ./prog` → run → bt
- 板子 hard fault / 沒反應：非法位址、堆疊溢位、未對齊存取；用 printf 二分法找最後印出的位置
卡住（hang）：
- `*_blocking` 等不到：`pio_sm_get_blocking`（RX FIFO 空）、`multicore_fifo_pop_blocking`、`dma_channel_wait_for_finish_blocking`（DMA 沒啟動或設定錯）
- 死結：兩把鎖取得順序不一致；拿著鎖又去拿同一把
- 輪詢的變數沒加 `volatile` 或沒用原子操作，讀取被最佳化掉
- 中斷沒致能、handler 沒註冊、沒清旗標導致一直重入
- `for (unsigned i = n; i >= 0; i--)` 永遠成立
- ROS 2 node 沒呼叫 spin，或 callback 被阻塞

---

【參考卡｜除錯 6/6｜症狀→原因：結果錯、時好時壞、沒輸出】
以下是正確的參考資料，若與你的記憶不同，以這張為準。平台：RP2350（Pico 2），非 RP2040；ROS 2 Jazzy。
結果錯（先 `diff expected.txt actual.txt` 找第一個不同處，再縮小輸入、印各階段中間值）：
- 差一：`<` vs `<=`、陣列長度、迴圈邊界
- 單位：DMA count 是「筆數」不是位元組數；ms vs us
- 型別：有號無號混用、`uint8_t` 運算提升成 `int`、溢位、整數除法截斷
- 位元：`a & b == c` 是 `a & (b == c)`；位移量 ≥ 型別寬度是 UB；endianness、DMA / PIO shift 方向
- 沒等 DMA 完成就讀 buffer；資料競爭；debug 輸出混入 stdout
時好時壞（幾乎都是並行或未初始化）：
- `for i in $(seq 50); do ./prog; done | sort | uniq -c`
- `-fsanitize=thread -pthread`；`-Wall -Wextra`
- 嵌入式：中斷 / 雙核共用變數沒保護
板子沒輸出：
- 有呼叫 `stdio_init_all()` 嗎？CMake 有 `pico_enable_stdio_usb(target 1)` 或 `pico_enable_stdio_uart(target 1)` 嗎？
- USB 開機太快印：開頭 `sleep_ms(2000)` 或等 `stdio_usb_connected()`
- 主機沒開 port 讀取時輸出會被靜默丟棄
- 二進位被加 `\r`：用 `stdio_put_string(buf, len, false, false)`
- 確認燒的是新版 .uf2；用 LED 確認程式有在跑
ROS 2 沒資料：`ros2 node list` → `topic list`（名稱完全一致？）→ `node info` → `topic info -v`（型別、pub/sub 數、QoS）→ `topic echo` → `topic hz` → `topic pub --once`（看起來卡住時加 `-w 0`）
環境：`ros2: command not found` → `source /opt/ros/jazzy/setup.bash`；自己的套件 → `source install/setup.bash`；改了沒效果 → 沒重編或跑到舊執行檔
