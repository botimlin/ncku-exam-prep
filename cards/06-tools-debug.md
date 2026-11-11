# 貼上卡：用工具除錯（gdb、sanitizer、卡住、板子、序列埠、ROS 2 連線）
> 用法：一次只複製一張卡（兩條分隔線之間），把 `{{...}}` 換成你的內容，貼進對話送出。每張都能在新對話直接用。每張 ≤ 1200 字元。
> 寫法：第一行 `Task (EN)` 是英文任務句；資料放在 `<<<資料 開始>>>` 和 `<<<資料 結束>>>` 之間；輸出格式放在資料後面。標題後的 `→` 是下一張。
> 流程：工具 1、2、3、5（定位）→ 工具 7（改 + 驗證）。工具 4、6 是一問一答的檢查清單。症狀→原因總表在 `04-debug.md` 除錯 5/6、6/6，這裡不重複。
> 完整工具手冊（給自己讀）：`../預製程式碼/tools/debug-host.md`、`debug-pico.md`、`debug-ros2.md`。
> 來源：GNU gdb / GCC sanitizer 文件、pico-sdk 2.2.0 原始碼（`pico_stdio_usb`、`boards/pico2.h`）、`../預製程式碼/pico/README.md` 設計審查紀錄、`cards/ros2.md`｜最後更新 2026-11

---

【提示卡｜工具 1/9｜幫我讀 gdb backtrace】→ 工具 7
Task (EN): From the gdb output, find the crash line in MY code and pick one cause A–G. Quote evidence. Do not fix yet. Answer in Traditional Chinese.
任務：找出崩潰在「我的程式」哪一行、是哪類原因。
取得：`gdb -batch -ex run -ex bt -ex "info locals" --args ./prog 參數`
<<<資料 開始>>>
[訊號] {{SIGSEGV / SIGABRT / SIGFPE}}
[bt 與 info locals]
{{貼}}
[bt 裡第一個我的函式，原始碼前後 10 行帶行號]（`cat -n f.c | sed -n 30,50p`）
{{貼}}
<<<資料 結束>>>
原因：A NULL 指標　B 陣列越界　C 用了已 free 的記憶體　D stack overflow（深遞迴、大區域陣列）　E 除以 0　F assert / abort　G 其他
規則：跳過 libc / SDK 內部的框，從第一個我的函式看起。資料沒有的寫「資料中沒有」。
只輸出 5 行：
位置：檔名:行號 函式
證據：「…」（照抄 bt 或變數值）
說明（1 句）：
原因（照抄選項，例如「B 陣列越界」）：
確認用的 gdb 指令（1 個）：
範例（只示範格式，內容不要照抄）：
位置：foo.c:77 foo_fill
證據：「k = 64」「char tmp[64]」
說明：迴圈 k <= len 多跑一次
原因：B 陣列越界
確認用的 gdb 指令：print len

---

【提示卡｜工具 2/9｜幫我讀 sanitizer 報告】→ 工具 7
Task (EN): From the FIRST sanitizer report, give the line in MY code and pick one type A–H. Quote evidence. Do not fix yet. Answer in Traditional Chinese.
任務：讀第一個 sanitizer 報告，找出位置與類型。
取得：`gcc -g -O1 -fno-omit-frame-pointer -fsanitize=address,undefined …`；資料競爭用 `-fsanitize=thread -pthread`（不能和 address 一起）
<<<資料 開始>>>
[報告]（從 `ERROR:`、`WARNING: ThreadSanitizer` 或 `runtime error:` 那行，到 `SUMMARY:`）
{{貼}}
[報告指到的程式碼，前後 10 行帶行號]
{{貼}}
<<<資料 結束>>>
類型：A heap-buffer-overflow　B stack-buffer-overflow　C heap-use-after-free　D double-free　E memory leak　F 整數溢位 / 位移量太大（UBSan）　G data race（TSan）　H 其他
規則：只看第一個報告。位置選報告 `#0 #1…` 中第一個我的檔案。
只輸出 5 行：
位置：檔名:行號
證據：「…」（照抄報告 1 行）
誰出錯（變數、越界幾 bytes，或哪兩個執行緒）：
類型（照抄選項，例如「A heap-buffer-overflow」）：
說明（1 句）：
範例（只示範格式，內容不要照抄）：
位置：foo.c:17
證據：「READ of size 4 … 0 bytes after 400-byte region」
誰出錯：arr[100]，陣列只有 100 個 int
類型：A heap-buffer-overflow
說明：迴圈上限用了 <=

---

【提示卡｜工具 3/9｜程式卡住，幫我判斷卡在哪】→ 工具 7
Task (EN): Find the ONE blocking call where the program hangs and pick one cause A–I. Quote evidence. Do not fix yet. Answer in Traditional Chinese.
任務：找出卡住的那一個呼叫，以及它在等什麼。
取得：Linux `gdb -p $(pgrep -n prog) -batch -ex "thread apply all bt"`；Python 按 Ctrl-C 看 traceback；Pico 看最後印出的那行。
<<<資料 開始>>>
[平台] {{Linux pthread / ROS 2 / Pico 單核 / Pico 雙核}}；{{每次都卡 / 偶爾卡}}
[最後印出的幾行]
{{貼}}
[thread apply all bt 或 traceback]（Pico 沒有就寫「無」）
{{貼}}
[最後印出那行之後的程式碼]
{{貼}}
<<<資料 結束>>>
原因：A 等資料（*_get_blocking、getchar、queue_remove_blocking、read）　B 死結（兩把鎖順序相反）　C 鎖沒放　D 輪詢的旗標沒 volatile 或沒人設　E 中斷沒觸發或沒清旗標　F FIFO / queue 滿、對方沒在收　G DMA 沒啟動　H 對方（node、core1、板子）沒在跑　I 其他
只輸出 5 行：
卡住的呼叫：檔名:行號 函式
它在等：
證據：「…」（照抄 1 行）
原因（照抄選項，例如「A 等資料」）：
確認實驗（1 個，例如在哪加 LED 或改成 timeout 版）：

---

【提示卡｜工具 4/9｜板子沒反應：一步一步檢查】
Task (EN): Act as a checklist host. Ask me ONE check at a time in the fixed order below. Wait for my result before the next. Answer in Traditional Chinese.
任務：主持檢查清單。一次只問一項，等我回報再問下一項。
板子：Raspberry Pi Pico 2（RP2350），pico-sdk 2.2.0，USB 序列埠。
<<<資料 開始>>>
[程式做什麼] {{…}}
[現象] {{沒有 /dev/ttyACM / 有 port 沒字 / 印到一半停 / 燒錄失敗}}
[已試過] {{…}}
<<<資料 結束>>>
固定順序：
1. 燒錄：`picotool info -a` 看到的程式名是新的嗎
2. 有在跑：板載 LED（GP25）開頭閃一下，有閃嗎
3. USB：`ls /dev/ttyACM*`、`lsusb | grep 2e8a` 有東西嗎
4. 佔用：minicom、screen、agent、別的 python 有沒有開同一個 port
5. 設定：CMake 有 `pico_enable_stdio_usb(t 1)`、程式有 `stdio_init_all()` 嗎
6. 太早印：開頭有等 `stdio_usb_connected()` 嗎
7. 建置：configure 印的是 `PICO_BOARD is 'pico2'` 嗎
8. Docker：容器有 `--device /dev/ttyACM0` 或 `--privileged` 嗎
每次只輸出：
檢查 n：要做的事（指令）
正常的樣子：
不正常就代表：
從第 1 項開始；我回報正常就跳下一項。

---

【提示卡｜工具 5/9｜序列埠收到的資料不對】→ 工具 7
Task (EN): The table below was made by a script. Pick ONE cause A–H and say which side to fix. Do not recount bytes yourself. Answer in Traditional Chinese.
任務：看程式比對好的表，判斷原因。
取得（3 步）：
1 實際：先關掉其他用這個 port 的程式，`stty -F /dev/ttyACM0 raw -echo; timeout 2 cat /dev/ttyACM0 | xxd -p | head -5`
2 預期：`python3 -c "from frame import encode;print(encode(0x02,1,bytes(4)).hex(' '))"`
3 比對：`cd ros2 && python3 frame.py diff "預期hex" "實際hex"`，整段輸出貼下面
<<<資料 開始>>>
{{貼 frame.py diff 的輸出}}
[送出端] {{電腦 → Pico / Pico → 電腦}}
<<<資料 結束>>>
原因（→ 修法）：A 多了 0D（CRLF 轉換沒關）→ Pico 端 PICO_STDIO_DEFAULT_CRLF=0　B 混入文字（printf）→ 刪掉二進位串流裡的 printf　C 大小端顛倒 → 送出端改 little-endian（struct "<"）　D len 單位錯（bytes vs 筆數）→ len 填 bytes　E CRC 範圍或初值錯 → 範圍 cmd..payload、zlib crc32　F 少收（read 沒累積）→ 接收端累積到滿一包　G 錯一格（同步字被吃掉、多一個 byte）→ 接收端重新對齊 AA 55　H 其他
規則：表和「線索」是程式算的，以它為準。
只輸出 4 行：
第一個不同：（照抄表下面那行）
證據：「表裡不同的那一列」
原因（照抄選項，例如「C 大小端顛倒」）：
哪一端要改（照抄所選原因的修法）：
範例（只示範格式，內容不要照抄）：
第一個不同：len（預期 14 bytes，實際 14 bytes）
證據：「| len | 04 00 | 00 04 | 否 |」
原因：C 大小端顛倒
哪一端要改：送出端，len 改用 little-endian（struct "<H"）
---

【提示卡｜工具 6/9｜ROS 2 節點看不到彼此】
Task (EN): For each row, copy the value from side A and side B, mark NG where they differ, then name the FIRST NG row. Answer in Traditional Chinese.
任務：每一列先抄兩邊的值，不同就是 NG，找出第一個 NG。ROS 2 Jazzy。
<<<資料 開始>>>
[兩邊在哪跑] {{同容器不同 shell / 不同容器 / 主機+容器}}；docker run 參數：{{例如 --net=host}}
[A：printenv | grep -E 'ROS_|RMW'] {{貼}}
[B：printenv | grep -E 'ROS_|RMW'] {{貼}}
[A：ros2 node list; ros2 topic list -t] {{貼}}
[B：ros2 node list; ros2 topic list -t] {{貼}}
[ros2 topic info -v /{{topic}}] {{貼}}
<<<資料 結束>>>
只輸出（照這 8 列填，不要增減列；A、B 填資料裡的原值，沒有就寫「沒設」；A ≠ B 就是 NG）：
| 項目 | A 的值 | B 的值 | OK/NG |
| 1 ROS_DISTRO | | | |
| 2 ROS_DOMAIN_ID（沒設=0） | | | |
| 3 ROS_AUTOMATIC_DISCOVERY_RANGE | | | |
| 4 RMW_IMPLEMENTATION | | | |
| 5 --net=host（不同容器才需要） | | | |
| 6 topic 名稱（含 namespace） | | | |
| 7 型別 | | | |
| 8 Publisher / Subscription count | | | |
第一個 NG：（寫項目編號和名稱）
下一步（1 個指令）：
提示：看得到 node 卻收不到資料、又是不同容器 → 可能是 Fast DDS 共享記憶體跨容器，兩邊加 `--ipc=host` 試試（⚠️未實測）。名單顯示怪就先 `ros2 daemon stop`。
---

【提示卡｜工具 7/9｜依定位結果最小修改（程式碼）】
Task (EN): Using the diagnosis, output a minimal patch (max 8 changed lines), keep all names, then 1 verify command and what success looks like. Answer in Traditional Chinese.
任務：依上一步的定位結果，給最小修改。
<<<資料 開始>>>
[定位結果]（貼工具 1、2、3、5 或除錯卡的輸出）
{{貼}}
[要改的程式碼，帶行號]（`cat -n f.c | sed -n 30,60p`）
{{貼}}
[不能改] {{介面、輸出格式、協定欄位}}
<<<資料 結束>>>
規則：
1. 最多改 8 行，只改資料中的程式碼。
2. 變數、函式、協定欄位名稱照原樣；`TODO(改這裡)` 標記保留。
3. 不確定存在的 API 標【推測】。
只輸出：
檔名:行號
修改前：
修改後：
為什麼（1 句）：
驗證指令（1 行）：
成功的樣子：
範例（只示範格式，內容不要照抄）：
foo.c:77
修改前：for (k = 0; k <= len; k++)
修改後：for (k = 0; k < len; k++)
為什麼：tmp 只有 len 格
驗證指令：gcc -g -fsanitize=address foo.c -o foo && ./foo
成功的樣子：沒有 ERROR，輸出和 expected.txt 相同

---

【參考卡｜工具 8/9｜gdb 速查（Linux）】
以下是正確的參考資料，若與你的記憶不同，以這張為準。GNU gdb，Linux 容器。
準備：`gcc -g -O0`（-O2 也能用，但變數常顯示 `<optimized out>`）
啟動：
- `gdb --args ./prog a b` → `run`（`run < in.txt` 導入輸入）
- 一次跑完拿 bt：`gdb -batch -ex run -ex bt --args ./prog a b`
- 接上正在跑的程式：`gdb -p PID`（容器可能因 ptrace 權限失敗 → 改在 gdb 裡 run，卡住時按 Ctrl-C）
- core dump：`ulimit -c unlimited` 後執行，再 `gdb ./prog core`（容器內 core 檔位置不一定）
看：
- `bt`、`bt full`（含區域變數）、`frame N`、`up`、`down`
- `info locals`、`info args`、`print x`、`print *p`、`print arr[0]@10`、`print/x v`、`ptype v`
停：
- `break file.c:42`、`break func`、`break 42 if i == 100`、`tbreak`、`info break`、`delete N`
- `watch var`（變數被改就停）、`display x`（每步顯示）
走：`next`（不進函式）、`step`（進函式）、`finish`（跑完這層）、`continue`、`until 50`
執行緒：`info threads`、`thread N`、`thread apply all bt`
離開：`kill`（結束被除錯的程式）、`quit`
訊號：SIGSEGV = 非法記憶體存取；SIGABRT = assert / abort / glibc 發現 heap 損壞；SIGFPE = 整數除以 0。
Pico 板子通常沒有接除錯器：用 LED 或 printf 二分法找最後執行到的位置。

---

【參考卡｜工具 9/9｜Pico 2 板子端檢查清單】
以下是正確的參考資料，若與你的記憶不同，以這張為準。RP2350（Pico 2），pico-sdk 2.2.0，非 RP2040。
1. 燒錄：按住 BOOTSEL 插 USB → 出現隨身碟 → 複製 .uf2；或 `picotool load -x app.uf2 -f`（`-f` 只對「有 USB stdio 且還在跑」的程式有效，卡死就手動 BOOTSEL）。`picotool info -a` 看板上程式名。
2. 有在跑：板載 LED = `PICO_DEFAULT_LED_PIN` = GP25（Pico 2 W 的 LED 不在 GPIO 上）。開頭先閃一下。
3. USB：`ls /dev/ttyACM*`、`ls -l /dev/serial/by-id/`、`dmesg | tail`；`lsusb` 看到 `2e8a:0009` = SDK 的 USB stdio。沒有 → 沒 `pico_enable_stdio_usb(t 1)`、沒 `stdio_init_all()`、程式當掉、Docker 沒給 `--device`。
4. 有 port 沒字：主機開 port 前印的字會丟（SDK 預設不等連線）→ 開頭等 `stdio_usb_connected()`；主機 0.5 s 沒讀，輸出也會丟。
5. **一個 port 同時只給一個程式**：minicom、screen、micro-ROS agent、python 只能開一個，不然資料被搶走、像在掉 byte。查誰在用：`fuser /dev/ttyACM0`（若有）。
6. **baud 1200 = 板子重開進 BOOTSEL**（`PICO_STDIO_USB_RESET_MAGIC_BAUD_RATE`）。USB CDC 不看 baud，用 115200。
7. 燒完會重新列舉：舊 port 失效，主機程式要重開 port；ttyACM 編號可能改變。
8. 多片板子：用 `/dev/serial/by-id/` 分辨；每片的 namespace / ID 要不同。
9. 看原始 bytes：`stty -F /dev/ttyACM0 raw -echo; timeout 2 cat /dev/ttyACM0 | xxd | head`。
