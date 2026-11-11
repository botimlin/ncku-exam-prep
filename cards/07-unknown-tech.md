# 貼上卡：陌生技術速學（備援）
> 用法：一次只複製一張卡（兩條分隔線之間），把 `{{...}}` 換成你的內容，貼進對話送出。提示卡＝直接用的問句；參考卡＝貼給模型當正確資料。每張 ≤ 1200 字元，每張都能在新對話直接用。
> 寫法：第一行 `Task (EN)` 是英文任務句；資料放在 `<<<資料 開始>>>` 和 `<<<資料 結束>>>` 之間；輸出格式放在資料後面。標題後的 `→` 是下一張。小模型對陌生技術幾乎一定記錯，所以每張都要貼官方文字（README 開頭、header、範例）給它根據。
> 來源：full/07-unknown-tech.md、lite/07-unknown-tech.md（詳細版）｜最後更新 2026-11

---

【提示卡｜速學 1/6｜陌生技術定位】→ 速學 2
Task (EN): Using only the pasted official text, fill the 6 fixed slots about this technology. Write 「資料中沒有」 when not stated. Answer in Traditional Chinese.
任務：根據官方文字定位 {{技術名稱}}（版本 {{版本}}）。我熟的是 {{熟悉的技術}}。
<<<資料 開始>>>
{{貼官方 README / 文件開頭 1–2 段}}
<<<資料 結束>>>
規則：
1. 只根據資料；沒有的寫「資料中沒有」。
2. 每格附證據：「原文」。類比那格可以用你的知識，但標【推測】。
只輸出這 6 格，每格 ≤ 2 行：
1. 類別（函式庫 / 框架 / 硬體周邊 / 協定 / 工具 / 語言）與解決什麼：
2. 輸入、輸出：
3. 像我熟的哪個東西、差在哪：
4. 核心概念（3–5 個）：
5. 使用流程（初始化 → 設定 → 啟動 → 等待 / 處理 → 釋放）：
6. 文件提到的限制或陷阱：
範例（第 5 格）：claim channel → configure → start → wait → unclaim　證據：「Channels must be claimed …」

---

【提示卡｜速學 2/6｜API 地圖】→ 速學 3
Task (EN): List only functions that appear in the pasted header, in usage order, in a table. Mark the 5 most relevant to my goal with ★. Answer in Traditional Chinese.
任務：把 {{技術名稱}} 的 header 整理成 API 表。我的目標：{{一句話}}
<<<資料 開始>>>
{{貼 header 或 API 文件；太長先 `grep -n "^[a-z].*(" x.h` 只貼函式宣告}}
<<<資料 結束>>>
規則：
1. 只列資料中真的出現的函式，不補記憶中的。
2. 依使用順序排（init / config → start → stop → deinit），最多 15 列。
只輸出：
| ★ | 函式 | 用途 | 阻塞? 是/否/看不出 | 重要參數 | 回傳值 |
struct / enum（≤ 5 列）：| 名稱 | 用途 |
範例（只示範格式，內容不要照抄）：| ★ | dma_channel_configure | 設定並可立即啟動 | 否 | count = 傳輸次數 | 無 |

---

【提示卡｜速學 3/6｜解讀最小範例】→ 速學 4
Task (EN): Explain the example line by line in a table: what it does, required or optional, affects performance or not. Say 「看不到定義」 for unknown functions. Answer in Traditional Chinese.
任務：逐行解讀 {{技術名稱}} 的官方最小範例。
<<<資料 開始>>>
{{貼範例，帶行號（cat -n）}}
<<<資料 結束>>>
規則：
1. 看不到定義的函式寫「看不到定義」，不要猜。
2. 空行、註解、include 可以合併成一列。
只輸出：
| 行號 | 在做什麼 | 必要 / 可選 | 影響效能?（buffer、批次、模式、硬體加速） |
最後 1 行：照抄這個範例要先準備什麼（檔案、函式庫、硬體接線）。
範例（只示範格式，內容不要照抄）：| 12 | 設定每次傳 32 bit | 必要 | 是：搭配 count 決定總量 |

---

【提示卡｜速學 4/6｜驗證我的理解】→ 速學 5
Task (EN): Check each of my statements against the pasted docs. Answer exactly 對 / 錯 / 資料中沒有 for each, with a quote. Answer in Traditional Chinese.
任務：用文件逐句檢查我對 {{技術名稱}} 的理解。
<<<資料 開始>>>
[文件段落]
{{貼}}
[我的理解]
1. 它是 ___，用來 ___
2. 使用順序：{{初始化 → … → 釋放}}
3. 關鍵 API：{{…}}
4. 限制（資源數、對齊、執行緒安全、阻塞、單位）：{{…}}
<<<資料 結束>>>
規則：只根據文件段落判斷；判「錯」時給正確說法。提到的 API 名稱要逐一在文件找到原文才算「對」，有一個找不到 → 「資料中沒有」並寫出名稱。
只輸出：
| # | 對 / 錯 / 資料中沒有 | 證據：「原文」 | 正確說法（判錯時） |
想用實驗確認某一句時，改用除錯 2/6。

---

【提示卡｜速學 5/6｜對準題目】→ 優化 2 或範本 2
Task (EN): Map the task requirement to concepts/APIs that appear in the pasted code and docs. Fill the 3 fixed slots. Answer in Traditional Chinese.
任務：把題目要求對到 {{技術名稱}} 的概念和 API。
<<<資料 開始>>>
[題目要求] {{…}}
[相關程式碼，帶行號]
{{貼}}
[相關文件段落]（可省略）
{{貼}}
<<<資料 結束>>>
規則：只用資料中出現的 API；不確定的標【推測】。
只輸出這 3 格，每格 ≤ 3 行：
1. 題目要改的地方用到哪些概念 / API（附行號）：
2. 文件或程式中可用來優化的選項（模式、硬體加速、批次、buffer）：
3. 建議的第一步（1 個動作 + 怎麼確認做對了）：
範例（第 3 格）：把 L40 的 CPU 迴圈換成 dma_channel_configure；確認：memcmp 結果為 0

---

【參考卡｜速學 6/6｜五步速學法與類別重點】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
目標：只學到能解這題的程度；先跑起來再讀；找類比；題目附的文件與程式碼最可靠（網路資料可能版本不同）。
五步（共約 60 分）：
1. 定位（5 分）：類別、解決什麼、輸入輸出、在本題跟誰互動、像什麼、版本
2. 跑起來（15–20 分）：範例來源依序為題目附的範例 → 專案內已用到的地方（`grep -rn 關鍵字 .`）→ 官方 Getting Started → 官方 repo 的 examples/tests → header 註解。原封不動先跑一次。
3. 建模型（15 分）：3–7 個核心概念、生命週期、5–10 個關鍵 API、限制、陷阱。通用框架：初始化 → 設定 → 啟動 → 等待 / 處理 → 釋放（例：DMA 為 claim channel → configure → start → wait → release；ROS 2 node 為 init → create pub/sub → spin → shutdown）。
4. 小改動（10 分）：改一個參數，先寫預測再跑；預測錯處就是誤解。
5. 對準題目（10 分）：用到哪些概念 / API、哪些效能選項。
依類別先看：
- 硬體周邊：datasheet Overview、方塊圖、Programmer's model、SDK 範例；問設定順序、FIFO / DMA / IRQ、時脈、資源數
- 函式庫：header、範例；問初始化順序、阻塞、記憶體誰管、回傳值
- 框架：架構概念、CLI；問誰呼叫誰、callback 在哪個執行緒
- 協定：封包格式、狀態機；問分框、校驗、流控、endianness
讀 header：`grep -n "^[a-z].*(" x.h`（函式）、`grep -n "typedef\|struct\|enum" x.h`（型別）。datasheet 搜 "must" "note" "errata" "not supported"。
止損：跑不起來超過 20 分 → 環境問題問監考，或從專案現有程式碼下手；整體超過 60 分 → 先做別題；只佔題目一小部分 → 照範例當黑盒子用。
