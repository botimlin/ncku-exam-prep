# 貼上卡：讀題與文件
> 題目太長：前幾段只貼資料區塊（開頭寫「第 k/N 段」，模型會回「收到」），最後一段才貼讀題 1/6。開考時用 `10-exam-day-flow.md` 的開考 1/5、3/5（讀題 2/6、1/6 是同一件事的舊版）。
> 用法：一次只複製一張卡（兩條分隔線之間），把 `{{...}}` 換成你的內容，貼進對話送出。提示卡＝直接用的問句；參考卡＝貼給模型當正確資料。每張 ≤ 1200 字元，每張都能在新對話直接用。
> 寫法：第一行 `Task (EN)` 是英文任務句；資料放在 `<<<資料 開始>>>` 和 `<<<資料 結束>>>` 之間；輸出格式放在資料後面。標題後的 `→` 是下一張。開考當天的前 30 分鐘流程另見 `10-exam-day-flow.md`。
> 來源：full/02-read-spec.md、lite/02-read-spec.md（詳細版）｜最後更新 2026-11

---

【提示卡｜讀題 1/6｜題目理解卡】→ 讀題 2
Task (EN): Fill the understanding card using only the problem text. Write 「資料中沒有」 for anything not stated. Answer in Traditional Chinese.
任務：只根據題目文字填理解卡。
<<<資料 開始>>>
{{貼題目說明}}
<<<資料 結束>>>
規則：
1. 只填題目明確寫的；沒寫就寫「資料中沒有」。
2. 數字、單位、格式照抄原文。
只輸出這張卡，每項 ≤ 2 行：
- 一句話目標：
- 輸入（來源、格式、範圍、大小）：
- 輸出（目的地、格式，精確到空白與換行）：
- 正確性怎麼判：
- 效能指標與單位：
- 給分方式（門檻 / 排名 / 比例）：
- 提交方式與次數限制：
- 時間 / 記憶體限制：
- 硬體（板子、核心、時脈）：
- 不能改的檔案 / 介面：
- 不能用的方法：
- 可以改的地方：
- baseline：
- 最容易誤解的 3 點：

---

【提示卡｜讀題 2/6｜檔案盤點與閱讀順序】→ 讀題 3 或 5
Task (EN): Classify every file into one category A–G, then list the 5 files to read first. Use only the data. Answer in Traditional Chinese.
任務：把檔案分類，選出先讀的 5 個。
取得：`find . -maxdepth 3 -not -path './.git' -not -path './.git/*' -not -path '*/build/*' -not -path '*/libmicroros/*' | sort | head -100`
<<<資料 開始>>>
[檔案清單]
{{貼 find 輸出}}
[題目一句話目標]
{{貼}}
<<<資料 結束>>>
類別：A 題目說明　B 評分（.gitlab-ci.yml、judge、test）　C 建置（CMakeLists.txt、Makefile、package.xml）　D 主要程式　E 輔助程式　F 不能改　G 不確定
只輸出：
| 路徑 | 類別 | 理由（≤ 10 字） |
先讀（依序 5 個，每個附一句理由）：
範例（只示範格式，內容不要照抄）：| ./judge/run.sh | B | 評分腳本 |

---

【提示卡｜讀題 3/6｜系統架構圖】→ 讀題 5
Task (EN): Draw an ASCII architecture diagram and fill the component table using only the data. Mark unknowns with ?. Answer in Traditional Chinese.
任務：畫架構圖，填元件表。
<<<資料 開始>>>
{{貼相關程式或說明}}
<<<資料 結束>>>
規則：
1. 只畫資料中出現的元件；不知道的寫 ?。
2. 沒有依據的瓶頸標【推測】。
只輸出這 4 段：
1. ASCII 圖（≤ 10 行），格式：[來源] --(機制, 資料格式)--> [元件] --> [輸出]
2. 元件表：| 元件 | 在哪跑（核心 / process / 板子） | 怎麼觸發（輪詢 / 中斷 / timer / 事件） | 證據 |
3. 共享資源與保護方式（≤ 3 行）
4. 還不確定、要我查的地方（≤ 3 點）
範例（第 1 段）：[PC node] --(topic /numbers, Int32MultiArray)--> [serial_bridge] --(USB, AA 55 封包)--> [Pico core0]

---

【提示卡｜讀題 4/6｜文件段落精讀】
Task (EN): Summarize this document section in the 5 fixed slots using only the text. Keep all numbers exactly as written. Answer in Traditional Chinese.
任務：整理這段文件（{{文件名稱}} 的 {{章節}}）。我的題目：{{一句話目標}}。
<<<資料 開始>>>
{{貼段落，一次一小節}}
<<<資料 結束>>>
規則：
1. 只寫原文有的；數值照原文寫法，不換算。
2. 沒有的寫「資料中沒有」。
只輸出這 5 段：
1. 摘要（3 句）
2. 欄位表：| 名稱 | 位元 | 意義 | 預設值 | 讀寫（RO / RW / WC） |（有列舉值的欄位，每個值寫一列；文件沒寫的格填「資料中沒有」，不要猜 0）
3. 操作順序（1. 2. 3.）
4. 限制與陷阱（對齊、最大值、時序、errata），每點附證據：「原文」
5. 和我的題目的關係（≤ 2 行）
範例（第 2 段）：| EN | 0 | 啟動通道 | 0 | RW |

---

【提示卡｜讀題 5/6｜程式走讀】→ 優化 1 或除錯 1
Task (EN): Describe this code in the 5 fixed slots. Do not suggest changes. Say 「看不到定義」 for functions not shown. Answer in Traditional Chinese.
任務：描述這段程式（{{檔名}}），先不要提出修改。
<<<資料 開始>>>
{{貼程式碼}}
<<<資料 結束>>>
規則：
1. 看不到定義的函式寫「看不到定義」，不要猜。
2. 每個熱點和可疑處附行號。
只輸出這 5 段：
1. 呼叫結構（縮排條列，≤ 12 行，不要貼程式碼）：初始化 / 主流程 / 輸出 / 同步點
2. 熱點（≤ 3 個）：行號 + 為什麼耗時
3. 可疑處（≤ 3 個）：行號 + 為什麼可疑
4. 用到的硬體或系統 API：| API | 作用 | 行號 |（例如 dma_、pio_、multicore_、spin_lock、create_subscription）
5. 看不到定義的函式（逐一列出；沒有寫「無」）：
範例（第 2 段）：L42 for 迴圈每筆呼叫 printf → USB I/O 很慢

---

【參考卡｜讀題 6/6｜讀題檢查清單】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
讀題原則：
- 先廣後深：先知道有哪些元件、怎麼連，再看細節。
- 先找評分方式：評分腳本 / `.gitlab-ci.yml` 比文字說明更準。
- 分清事實（附出處）與推測（待實驗確認）。
- datasheet 只讀相關段落，順序：Overview 與方塊圖 → 操作流程（Programmer's model）→ 暫存器表（看 reset 預設值、讀寫屬性）→ 限制 / errata → 範例程式。
- PDF 用搜尋找暫存器名、函式名、"must"、"note"、"errata"。
- 走讀順序：main → 主迴圈 → 標出初始化 / 處理 / 輸出 / 同步點 → 再深入熱點。
- 動手前先跑 baseline：編譯、執行、可以的話提交一次，記下基準分數。

常見錯誤：
- 沒看評分腳本 → 優化了不計分的部分
- 輸出格式差一個空白或換行 → 被判錯（用 `diff` 對照範例輸出）
- 單位搞錯：bytes vs 筆數、ms vs us、Hz vs 週期
- 改到不能改的檔案或介面
- 沒跑 baseline → 不知道優化有沒有效
- 從頭細讀整章 datasheet → 時間耗盡
- 沒查證模型說的 API → 用 `grep` 查 header 確認存在
