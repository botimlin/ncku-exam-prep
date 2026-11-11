# 貼上卡：效能優化
> 用法：一次只複製一張卡（兩條分隔線之間），把 `{{...}}` 換成你的內容，貼進對話送出。提示卡＝直接用的問句；參考卡＝貼給模型當正確資料。每張 ≤ 1200 字元，每張都能在新對話直接用。
> 寫法：第一行 `Task (EN)` 是英文任務句；資料放在 `<<<資料 開始>>>` 和 `<<<資料 結束>>>` 之間；輸出格式放在資料後面。標題後的 `→` 是下一張。
> 流程：優化 1（瓶頸）→ 優化 2（選方案）→ 優化 3（改一處）→ 量測 → 優化 4（判讀）→ 回到 1。
> 來源：full/03-optimize.md、lite/03-optimize.md（詳細版）｜最後更新 2026-11

---

【提示卡｜優化 1/6｜瓶頸分析】→ 優化 2
Task (EN): From the measurements, pick ONE bottleneck type A–F and quote the numbers as evidence. Do not suggest fixes. Answer in Traditional Chinese.
任務：根據量測判斷瓶頸類型，先不要提改法。
<<<資料 開始>>>
[目標] {{例如 降低處理 N 筆的總時間}}
[baseline] {{數字與單位}}
[各段耗時]
{{貼量測輸出}}
[熱點程式碼]
{{貼}}
<<<資料 結束>>>
類型：A 運算　B 記憶體 / 匯流排　C I/O 或通訊等待　D 同步（鎖競爭、false sharing）　E 演算法複雜度　F 量測不足（只有總時間、沒有分段數字）
只輸出 5 行：
瓶頸在哪一段：
證據：「…」（照抄量測數字）
類型（照抄選項，例如「C I/O 或通訊等待」）：
這段佔總時間比例 p：（整段拿掉的加速上限 = 1 / (1 − p)）
還缺的量測點（選 F 時必填）：
範例（只示範格式，內容不要照抄）：
瓶頸在哪一段：send_all()
證據：「send 412 ms / total 480 ms」
類型：C I/O 或通訊等待
p：0.86（上限約 7 倍）
還缺的量測點：無

---

【提示卡｜優化 2/6｜方案排序】→ 優化 3
Task (EN): List up to 5 optimization options for this bottleneck in a table, then pick ONE to do first. Answer in Traditional Chinese.
任務：列方案，選一個先做。
<<<資料 開始>>>
[瓶頸] {{貼優化 1 的結果}}
[限制] {{不能改的檔案 / 介面 / 硬體資源 / 編譯旗標}}
[熱點程式碼]（幾行就好）{{貼}}
[剩餘時間] {{例如 3 小時}}
<<<資料 結束>>>
規則：
1. 最多 5 列；每列都要有驗證方式。
2. 不列會改到評分介面或輸出格式的方案。
3. 時間少時，優先「中收益、低風險、15 分鐘內」。
4. 先從這些常見方案挑合適的：文字改二進位 + 批次傳送、拿掉熱點裡的 printf / log、DMA 取代 CPU 複製迴圈、雙核分工（一核收一核算）、查表 / 演算法換掉、編譯 -O2。
只輸出：
| 方案 | 收益 高/中/低 | 依據（量測 / 推測） | 風險 高/中/低 | 分鐘 | 驗證方式 |
先做：（方案名稱 + 1 句理由）
範例（只示範格式，內容不要照抄）：| 改成批次傳送 | 高 | 量測：send 佔 86% | 低 | 15 | diff 輸出相同 + 計時 |

---

【提示卡｜優化 3/6｜實作單一改動】→ 量測後用優化 4
Task (EN): Implement ONE change as a minimal patch (max 15 changed lines). Keep all names. Then 1 verify command and what success looks like. Answer in Traditional Chinese.
任務：只實作這一個方案：{{方案描述}}
<<<資料 開始>>>
[要改的程式碼，帶行號]（`cat -n f.c | sed -n 30,80p`）
{{貼}}
[不能改] {{介面、輸出格式}}
<<<資料 結束>>>
規則：
1. 只改這一處，最多 15 行；變數、函式、欄位名稱照原樣。
2. 不確定存在的 API 標【推測】，我會去 header 查。
只輸出：
檔名:行號
修改前：
修改後：
數字和單位（例如 筆數 = bytes ÷ 每筆大小，寫出算式；沒有寫「無」）：
可能的副作用（1 句）：
正確性驗證指令（1 行）：
成功的樣子：
範例（只示範格式，內容不要照抄）：
main.c:57
修改前：for (i = 0; i < n; i++) send_one(a[i]);
修改後：send_batch(a, n);
可能的副作用：接收端要能一次收 n 筆
正確性驗證指令：./run.sh > out.txt && diff out.txt expected.txt
成功的樣子：diff 沒有輸出

---

【提示卡｜優化 4/6｜解讀量測結果】→ 優化 1
Task (EN): Judge this measurement in the 4 fixed slots. Pick reasons only from list A–F. Answer in Traditional Chinese.
任務：判讀這次改動的結果。
<<<資料 開始>>>
[改動] {{描述}}
[正確性] {{diff 結果：相同 / 第一個不同處}}
[效能] {{之前}} → {{之後}}（單位 {{ms / us / cycles}}，各跑 {{N}} 次取中位數）
[原本預期] {{例如 快 3 倍}}
<<<資料 結束>>>
不如預期的原因：A 量到 debug 版　B 量測區段含 printf / log　C 硬體卸載（DMA / PIO / core1）沒真的在跑　D 瓶頸其實在別處　E 變異太大、次數太少　F 其他
填法：「符合預期」只寫「是」或「否」；「決定」照下表只寫「保留並 commit」或「回復」：
正確性不同 → 回復　｜　正確性相同、變快 → 保留並 commit　｜　正確性相同、沒變快 → 保留並 commit（先修量測再重量，改動本身沒錯）
只輸出 4 行（欄位名照抄）：
符合預期：
原因（選「否」時，選 A–F + 1 句依據）：
決定：
下一步量什麼：

---

【參考卡｜優化 5/6｜瓶頸分類與手法】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
現象 → 瓶頸類型：
- CPU 滿、時間 ∝ 運算量 → 運算
- 資料大、存取跳躍、資料加大效能驟降 → 記憶體 / 快取 / 匯流排
- CPU 閒但整體慢 → I/O / 周邊 / 通訊等待
- 加執行緒沒變快或更慢 → 鎖競爭 / false sharing
- 輸入稍大時間暴增 → 演算法複雜度
- 在等另一元件（topic、FIFO、DMA 完成）→ 管線不平衡、序列化執行

手法（通常收益大 → 小）：
1. 演算法：降複雜度、換資料結構、快取 / 查表、提早結束
2. 卸載與平行：DMA 搬資料；PIO 處理時序 I/O 與位元打包；第二核心分工或管線；雙緩衝（ping-pong）讓計算與搬運重疊
3. 同步：臨界區縮到最短（計算移出鎖外）；各自累計最後合併；原子操作取代鎖；避免 false sharing
4. 記憶體：循序存取；熱碼放 SRAM；對齊、32 位元寬讀寫；熱路徑不 malloc
5. I/O：批次處理；移除熱路徑 printf；ROS 2 callback 不阻塞
6. 微優化：2 的冪次用位移 / 遮罩；branchless；迴圈展開；`__builtin_popcount/clz/ctz`
7. 編譯器：-O2 / -O3 / -Os；inline、restrict、const；看 objdump / `.dis`（先確認評分是否允許改旗標）

鐵則：正確性第一；先量測；只優化瓶頸；一次改一處；有效就 commit。
Amdahl：p = 0.6、s = 3 → 1.67 倍；s = ∞ → 上限 2.5 倍。

---

【參考卡｜優化 6/6｜量測方法與 RP2350 速查】
以下是正確的參考資料，若與你的記憶不同，以這張為準。平台：RP2350（Pico 2），非 RP2040。
量測：
- Linux：`clock_gettime(CLOCK_MONOTONIC, &t)` 包住區段，結果印到 stderr（不污染評分 stdout）；`time ./prog`；多跑幾次取中位數。
- 容器內 perf 很可能不能用（Docker 預設 seccomp 擋 `perf_event_open`），改用程式內計時或 gprof（`-pg`）。
- RP2350：`uint64_t t0 = time_us_64();` 前後相減；短區段重複 N 次再除 N；printf 放量測區段外（USB stdio 很慢）。
- ROS 2：`ros2 topic hz / bw / delay /topic`（delay 需訊息有 header 時間戳）。
量測陷阱：
- 量到 debug 版：用評分相同旗標；pico-sdk 的 Release 預設 `-O3`，Debug 為 `-Og`，以評分腳本為準。
- 結果沒被使用會被編譯器刪掉：用 `volatile` 接或印出結果。
- 冷啟動較慢；變異大時看中位數與最小值。
RP2350 情況 → 首選手法：
- CPU 迴圈搬大量資料 → DMA
- bit-bang GPIO / 精確時序 → PIO
- 一核忙一核閒 → 雙核分工或管線
- CPU 等 DMA 完成 → 雙緩衝重疊
- 熱迴圈在 XIP flash 執行 → 放 SRAM（`__not_in_flash_func`）
- RISC-V（Hazard3）核心用 float / double → 改定點數（Hazard3 無 FPU，浮點全靠軟體模擬）
- 大量位元操作 → Zbb / Zbs 指令、builtin
- 周邊輪詢浪費 CPU → 中斷或 DMA + DREQ
