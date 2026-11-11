# 貼上卡：讓模型改我的預製範本（不要從頭寫）
> 用法：開新對話先貼「開場 1/3」，再貼「範本 1/7」。之後一次只複製一張卡，把 `{{...}}` 換成你的內容送出。每張 ≤ 1200 字元，每張都能在新對話直接用（範本 1/7 是補充背景，忘了貼也能用）。
> 寫法：第一行 `Task (EN)` 是英文任務句；資料放在 `<<<資料 開始>>>` 和 `<<<資料 結束>>>` 之間；輸出格式放在資料後面。標題後的 `→` 是下一張。
> 流程：範本 2（對照）或 4、5、6（設計）→ 範本 3（改一段）→ 編譯測試 → 範本 7（檢查）。
> 取資料：檔頭 `sed -n 1,30p 檔名`；TODO 位置 `grep -n "TODO(改這裡)" 檔名`；一段帶行號 `cat -n 檔名 | sed -n 40,80p`。
> 來源：`../預製程式碼/README.md`、各資料夾 README 與「設計審查紀錄」（pico/、micro-ros/）、`pico/serial_proto.h`、`ros2/frame.py`｜最後更新 2026-11

---

【提示卡｜範本 1/7｜開場補充：我有預製範本】
Task (EN): I have tested template code. Prefer minimal edits to it. Reply only 「了解」. Answer in Traditional Chinese later.
我有考前寫好、測過的範本（繁中註解，要改處標 `TODO(改這裡)`）。之後請照這 4 條：
1. 在範本上做最小修改；給「檔名:行號 / 修改前 / 修改後」。
2. 協定欄位的名稱、順序、大小端照原樣；`TODO(改這裡)` 標記保留，旁邊註明改了什麼。
3. 範本沒有的功能才新增，說明放在哪個函式。
4. 範本和題目不同時，以題目為準，並說出哪裡不同。
封包協定（Pico `pico/serial_proto.c` ↔ 電腦 `ros2/frame.py`，兩邊一致）：
`AA 55 | cmd u8 | seq u8 | len u16 LE | payload[len] | crc32 u32 LE`
- crc32 = zlib CRC-32，範圍 cmd 到 payload 結尾（不含 AA 55）；回覆用同 cmd、同 seq
- cmd：0x01 ECHO 原樣回傳；0x02 SUM_U32（payload = u32 LE 陣列，回 u32 總和）；0x03 CRC32（回 u32）
- Pico `FRAME_MAX_PAYLOAD` = 8192，超過整包丟掉不回；電腦 `CHUNK_BYTES` = 4096（必須 ≤ 8192）
資料夾：
- `ros2/`：node_template.py、frame.py、serial_bridge.py（批次）、multi_device.py（多板）、fake_pico.py（假板子）
- `pico/`：app_serial.c、app_multicore.c、app_dma.c、app_dma_pio.c、app_pio.c、pio/*.pio、timing.h
- `micro-ros/`：pico_array_compute.c、pico_dualcore_micro_ros.c、host_driver.py
- `bits-riscv/`：位元欄位、位元流、RV32 編解碼、組語
- `algo/`：CRC、SHA、排序、BNN；`linux-perf/`：pthread 平行、pipeline
只回覆「了解」。

---

【提示卡｜範本 2/7｜題目規格 → 範本對照】→ 範本 3
Task (EN): Map each requirement in the spec to the template. Fill the table; status must be one of: 直接可用 / 要改 / 範本沒有. Quote evidence. Answer in Traditional Chinese.
任務：把題目每一項要求對到範本，填表。
<<<資料 開始>>>
[題目規格]
{{貼相關段落}}
[範本檔頭註解]
{{貼 sed -n 1,30p 的結果}}
[範本 TODO 位置]
{{貼 grep -n "TODO(改這裡)" 的結果}}
<<<資料 結束>>>
規則：只根據資料；範本裡看不到的功能算「範本沒有」。
只輸出這個表，每格 ≤ 1 行，最多 10 列：
| 題目要求 | 範本對應（函式 / 常數 / 行號） | 狀態 | 證據 |
表後再輸出 1 行：先做哪一列（能最快跑出第一版的那列）。
範例（只示範格式，內容不要照抄）：
| 回傳 u32 總和 | handle() 的 CMD_SUM_U32（app_serial.c:30） | 直接可用 | 「case CMD_SUM_U32」 |
| topic 叫 /input | node_template.py 的 in_topic | 要改 | 「declare_parameter("in_topic", "/number")」 |

---

【提示卡｜範本 3/7｜依規格改這段 TODO】→ 範本 7
Task (EN): Edit only the template block below to meet the spec. Output a minimal patch (max 10 changed lines), keep all names and TODO markers, then 1 verify command and what success looks like. Answer in Traditional Chinese.
任務：只改下面這段範本，符合規格。
<<<資料 開始>>>
[規格原文（只貼相關幾行）或上一張卡的結論]
{{貼}}
[範本這一段，帶行號]（`cat -n pico/app_serial.c | sed -n 24,57p`）
{{貼}}
[不能改] {{封包格式、函式名稱、輸出格式}}
<<<資料 結束>>>
規則：
1. 最多改 10 行；變數、函式、協定欄位名稱照原樣。
2. 只輸出真的改了的行；`TODO(改這裡)` 保留，只在改了的那一行後面加「// 已改：…」。
3. 另一端要一起改時，寫出檔名和要改什麼（改了計算方式 → 假板子 fake_pico.py 的 handle() 也要一樣改）。新增 cmd 要改 4 處：serial_proto.h、app_serial.c 的 handle()、frame.py 常數、fake_pico.py 的 handle()。
只輸出：
檔名:行號
修改前：
修改後：
另一端要改：（沒有寫「無」）
驗證指令（1 行）：
成功的樣子：
範例（只示範格式，內容不要照抄）：
app_serial.c:37
修改前：sum += v;   // TODO(改這裡)
修改後：sum += v * v;   // TODO(改這裡) // 已改：平方和
另一端要改：fake_pico.py 的 handle() 同樣改平方和
驗證指令：python3 serial_bridge.py --ros-args -p port:=/dev/pts/N（另開 fake_pico.py）
成功的樣子：/sum 的值等於電腦端算的平方和

---

【提示卡｜範本 4/7｜把文字傳輸改成二進位批次】→ 範本 3
Task (EN): Design a binary batched encoding for this data. Fill the fixed slots only. Do not write code yet. Answer in Traditional Chinese.
任務：設計「二進位 + 批次」的格式，先不要寫程式。
<<<資料 開始>>>
[現在的傳送端] {{貼幾行}}
[現在的接收端] {{貼幾行}}
[資料] 型別 {{int32 / uint8 / float}}、範圍 {{…}}、總共 {{N}} 筆
[路徑] {{USB 序列埠（frame.py ↔ serial_proto）/ micro-ROS / ROS 2 topic}}
<<<資料 結束>>>
已知限制（以這些為準）：
- 序列埠：一包 payload ≤ CHUNK_BYTES 4096；u32 是 4 bytes little-endian，切包要 4 的倍數。範本 serial_bridge.py 的 `batch_size:=0` 就是塞滿一包，可用 frame.py 的 pack_u32 / unpack_u32。
- micro-ROS（預編函式庫）：Int32MultiArray reliable 約 505 個、best_effort 約 121 個；範本 MAX_LEN 用 400。
- 範本實測：fake_pico 加總 20000 個數字，一次一個 664 ms，批次 1.9 ms。
只輸出這 5 格，每格 ≤ 2 行：
每筆編碼：
每包幾筆：
要改的檔案與函式：
怎麼確認結果不變：
預估加速與依據：

---

【提示卡｜範本 5/7｜把工作拆給 N 片板子 / 2 個核心】→ 範本 3
Task (EN): Decide if this work can be split, then pick ONE template from the list. CRC / SHA over one stream can NOT be split. Fill the fixed slots only. Answer in Traditional Chinese.
任務：判斷能不能拆（CRC、SHA 這種一段接一段的運算不能拆），選一個範本。
<<<資料 開始>>>
[計算] {{排序 / CRC / SHA / BNN / 加總}}，資料量 {{N}}，現在耗時 {{…}}
[拆法] {{N 片板子 / Pico 雙核 / 電腦多執行緒}}
[合併方式] {{加總 / 依順序接 / 各自排序再 merge}}
[現在的計算程式] {{貼幾行}}
<<<資料 結束>>>
範本選項：
A multi_device.py：序列埠多板；切塊 4 bytes 對齊、每個 port 一條執行緒搶工作、results[塊編號] 保證順序
B host_driver.py：micro-ROS 多板；data[0]=job_id、CHUNK=300、MERGE="concat" 或 "sorted"、namespace pico0..
C app_multicore.c：Pico 雙核；job_t / result_t + queue_t、core1_main（core1 stack 只有 2 KB，大陣列用 static）
D pico_dualcore_micro_ros.c：core0 跑 micro-ROS、core1 算
E linux-perf/parallel_template.c：pthread 切塊、各自累加最後合併
合併可用 algo/sort.c 的 merge_two_sorted / kway_merge。
填法：「能不能拆」只寫「可以」或「不行」再接理由（CRC、SHA 這類一段接一段的串列運算一律「不行」）；「瓶頸在」只寫「傳輸」或「計算」再接依據；「合併用」寫 algo/sort.c 的函式名或「不用合併」。
只輸出 6 行（欄位名照抄）：
能不能拆：
選：A–E
瓶頸在：
合併用：
要改的 TODO(改這裡)：
怎麼確認平行版 == 單機版：

---

【提示卡｜範本 6/7｜範本和題目的介面不合】→ 範本 3
Task (EN): List every interface difference between the spec and the template in a table. Suggest converting at the boundary. No code yet. Answer in Traditional Chinese.
任務：列出題目和範本的介面差異。
<<<資料 開始>>>
[題目的介面原文] {{例如 topic /input 型別 UInt8MultiArray；封包順序 cmd、len、seq；len big-endian}}
[範本的介面] {{例如 frame.py：AA 55 cmd seq len(u16LE) payload crc32；node_template.py：Int32 /number → /double}}
[相關程式碼] {{encode / parser / 訂閱與發布那幾行}}
<<<資料 結束>>>
比對項目：topic 名稱、訊息型別、欄位順序、欄位寬度、大小端、CRC 規格、單位、回傳格式。
規則：只列資料中看得到的；看不到寫「資料中沒有」。Python `struct`：`<` 小端、`>` 大端。
只輸出：
| 項目 | 題目 | 範本 | 要改的檔案:函式 |
改法（1 句）：在哪一層加轉換
範例（只示範格式，內容不要照抄）：| len 大小端 | big-endian | `<H` 小端 | frame.py:encode、serial_proto.c:proto_feed |

---

【提示卡｜範本 7/7｜檢查我改完的範本】
Task (EN): First copy every + / - line of the diff. Then fill the 9-row table with OK / 有問題 / 看不到 and the diff line as evidence. Answer in Traditional Chinese.
任務：用固定清單檢查我的修改。
<<<資料 開始>>>
{{貼 git diff -U2 檔名 | head -80}}
<<<資料 結束>>>
規則：只有 diff 裡 + 或 - 開頭的行能判「有問題」，證據抄那一行；diff 沒有相關的行 →「看不到」。
先輸出：diff 裡 + / - 開頭的行（逐行照抄，≤ 10 行）
再輸出這張表（9 列照填，不要增減）：
| 檢查項目 | 結果 | 證據（diff 那一行） |
| 1 大小端：多位元組欄位兩端都 little-endian（Python `<`） | | |
| 2 DMA count 是傳輸次數不是 bytes（4096 bytes 用 32-bit = 1024），有包 `dma_encode_transfer_count` | | |
| 3 memory→memory DMA 有 `channel_config_set_write_increment(&c, true)`（預設 false）；用完 `dma_channel_unclaim` | | |
| 4 spinlock 用 `spin_lock_init(spin_lock_claim_unused(true))`；鎖內沒有計算、printf、sleep | | |
| 5 payload ≤ FRAME_MAX_PAYLOAD 8192；大陣列是 static / 全域 | | |
| 6 二進位 USB 串流（app_serial）裡沒有 printf / puts | | |
| 7 micro-ROS 收：先配 `.data/.capacity/.size=0`；發：publish 前設 `.size` | | |
| 8 新 cmd 在 serial_proto.h、handle()、frame.py、fake_pico.py 都有且編號一致 | | |
| 9 兩核 / 中斷共用的變數有 volatile 和鎖 | | |
最嚴重的 1 個問題與修法（沒有就寫「無」，≤ 2 行）：