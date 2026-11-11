# 貼上卡：除錯
> 用法：一次只複製一張卡（兩條分隔線之間），把 `{{...}}` 換成你的內容，貼進對話送出。提示卡＝直接用的問句；參考卡＝貼給模型當正確資料。每張 ≤ 1200 字元，每張都能在新對話直接用。
> 寫法：第一行 `Task (EN)` 是英文任務句；資料放在 `<<<資料 開始>>>` 和 `<<<資料 結束>>>` 之間；輸出格式放在資料後面。標題後的 `→` 是下一張。
> 流程：除錯 1 或 3（定位）→ 除錯 2（分不出來時做實驗）→ `06-tools-debug.md` 工具 7（最小修改 + 驗證）→ 除錯 4（修好但不懂時）。gdb、sanitizer、卡住、板子、序列埠、ROS 2 連線的專用卡在 `06-tools-debug.md`；CMake / colcon 錯誤在 `05-cmake-build.md`。
> 知識：小模型不知道硬體的預設值與陷阱（例如 DMA 預設不遞增寫入位址）。DMA / PIO / 多核 / USB 的問題，先在同一個對話貼對應的參考卡（`pico-dma.md` 2/8、`pio.md` 8/8、`multicore-sync.md`、`host-mcu-comm.md` 1/8），模型回「收到」後再貼這張。壓力測試：先貼參考卡，原本全錯的案例會答對。
> 來源：full/04-debug.md、lite/04-debug.md（詳細版）｜最後更新 2026-11

---

【提示卡｜除錯 1/6｜錯誤回報格式】→ 除錯 2 或工具 7
Task (EN): List up to 3 likely causes ranked by likelihood, each with evidence and one check. Do not fix yet. Answer in Traditional Chinese.
任務：列出可能原因與驗證方法，先不要修。
<<<資料 開始>>>
[指令與目的] {{執行了什麼、想做什麼}}
[預期] {{…}}
[實際] {{…}}
[錯誤訊息]（編譯錯誤只貼第一個 error 前後）
{{貼}}
[相關程式碼，帶行號]
{{貼}}
[上次能用之後改了] {{…}}
[已經試過] {{…}}
[環境] {{Linux 容器 / Pico 2（RP2350）ARM 或 RISC-V；編譯指令}}
<<<資料 結束>>>
規則：
1. 最多 3 個原因；每個附證據：「錯誤或程式原文」。
2. 驗證方法要是 1 個指令或 1 個小改動。
只輸出：
| # | 原因 | 可能性 高/中/低 | 證據 | 驗證方法 | 結果代表什麼 |
範例（只示範格式，內容不要照抄）：| 1 | DMA count 填成 bytes | 高 | 「dma_channel_configure(..., 4096, true)」 | 印出 count | 4096 而非 1024 → 確認 |

---

【提示卡｜除錯 2/6｜設計區分假設的實驗】→ 工具 7
Task (EN): Design ONE minimal experiment that tells hypothesis A from B. Do not modify the program logic. Answer in Traditional Chinese.
任務：設計一個最小實驗區分兩個假設，不修改程式邏輯。
<<<資料 開始>>>
[假設 A] {{…}}
[假設 B] {{…}}
[症狀] {{…}}
[相關程式碼，帶行號]
{{貼}}
<<<資料 結束>>>
實驗只能用：加一行 print / LED、改輸入、註解掉一段、改一個參數。
只輸出：
實驗步驟（≤ 3 步，每步 1 行，附檔名:行號）：
如果看到 ___ → 是 A
如果看到 ___ → 是 B
都不是 → 下一個要懷疑的：
範例（只示範格式，內容不要照抄）：
1. worker.c:30 迴圈後加 printf("n=%u\n", n)
如果看到 n=1024 → 是 A
如果看到 n=4096 → 是 B

---

【提示卡｜除錯 3/6｜看不懂的錯誤訊息】→ 除錯 1 或工具 7
Task (EN): Explain the FIRST error in one plain sentence, then list its 3 most common causes and which to check first. Answer in Traditional Chinese.
任務：解釋第一個錯誤訊息。
<<<資料 開始>>>
[環境] {{Linux 容器 / RP2350（Pico 2）+ pico-sdk / ROS 2 Jazzy；編譯指令}}
[錯誤訊息]（貼完整，不要只貼最後一行）
{{貼}}
<<<資料 結束>>>
規則：只分析第一個 error，後面的常是它連鎖引起的。
只輸出：
第一個錯誤：「原文那一行」
白話（1 句）：
| 常見原因 | 怎麼檢查（1 個指令） |（3 列）
先檢查：第幾列（理由 1 句）
範例（只示範格式，內容不要照抄）：
第一個錯誤：「undefined reference to `dma_channel_claim'」
白話：連結時找不到這個函式的實作
| 沒 link hardware_dma | grep -n target_link_libraries CMakeLists.txt |

---

【提示卡｜除錯 4/6｜修好了但不知道為什麼】
Task (EN): Explain why the change fixed the symptom, judge if it is a root-cause fix, and give one command to confirm. Answer in Traditional Chinese.
任務：解釋這個改動為什麼有效。
<<<資料 開始>>>
[原本的症狀] {{…}}
[修改前]
{{貼}}
[修改後]
{{貼}}
<<<資料 結束>>>
只輸出 5 行：
為什麼有效（≤ 2 句，附證據：「程式原文」）：
判斷（三選一：根本修正、可能只是掩蓋、資料不足）：
理由（1 句）：
確認指令（1 行）：
成功的樣子：
範例（只示範格式，內容不要照抄）：
確認指令：for i in $(seq 50); do ./prog; done | sort | uniq -c
成功的樣子：只有一種輸出，而且和 expected 相同

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
