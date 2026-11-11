# 貼上卡：用參考卡問問題
> 用法：同一個對話先貼 1～2 張參考卡（`pico-dma.md`、`pio.md`、`ros2.md`…），模型回「收到」，再貼這裡的提示卡。小模型沒有硬體知識，**參考卡就是它的知識**；不貼參考卡直接問，它會用記憶亂答（常和 RP2040 搞混）。每張 ≤ 1200 字元，每張都能在新對話直接用。
> 寫法：第一行 `Task (EN)` 是英文任務句；資料放在 `<<<資料 開始>>>` 和 `<<<資料 結束>>>` 之間；輸出格式放在資料後面。
> 來源：stress-test 結果（貼參考卡後，原本全錯的硬體知識題會答對）｜最後更新 2026-11

---

【提示卡｜查詢 1/2｜根據參考卡回答】
Task (EN): Answer my question using ONLY the reference card(s) pasted earlier in this conversation. Quote the line you use. If the card does not say it, write 「資料中沒有」 and where to look. Answer in Traditional Chinese.
任務：只根據前面貼的參考卡回答我的問題。
<<<資料 開始>>>
[問題] {{例如 DMA 設定 count 的單位是什麼？}}
[我的情境]（可省略）{{例如 要搬 4096 bytes，用 32-bit 傳輸}}
<<<資料 結束>>>
規則：
1. 只用參考卡上寫的；卡上沒有 → 「資料中沒有」，再寫要查哪份官方文件（照卡上的網址或章節）。
2. 函式名、巨集名、數字照抄，不改名；要換算時寫出算式。
只輸出 4 行（欄位名照抄）：
證據：「…」（照抄參考卡 1～2 行）
答案（≤ 2 句）：
注意事項（卡上寫的陷阱；沒有寫「無」）：
不確定的地方（沒有寫「無」）：
範例（只示範格式，內容不要照抄）：
證據：「count = 傳輸次數，不是 bytes」
答案：填傳輸次數；4096 bytes ÷ 4 = 1024。
注意事項：要包 dma_encode_transfer_count(n)
不確定的地方：無

---

【提示卡｜查詢 2/2｜用參考卡檢查我的程式】
Task (EN): First list the rules written on the pasted reference card(s). For each rule, copy the related code line(s) with line numbers BEFORE judging, then judge OK / 違反 / 看不到. Answer in Traditional Chinese.
任務：用前面貼的參考卡上的規則，逐條檢查我的程式。
<<<資料 開始>>>
[我的程式，帶行號]（`cat -n f.c | sed -n 30,70p`）
{{貼}}
<<<資料 結束>>>
規則：
1. 規則只能來自參考卡，最多 8 條：先挑和這段程式有關的（程式有 ISR 就挑 ISR 的、有 DMA count 就挑 count 的），照抄卡上的寫法。
2. 程式裡找不到相關的行 → 「看不到」；只有找得到那一行才能判「違反」。
填法：一列 = 一條規則（不是一行程式）；規則有「之前 / 之後 / 先 / 最後」→ 抄出兩邊的行號比大小；規則有「每次 / 一定要」→ 每個出現的地方都要找。
先輸出：參考卡上的規則（逐條照抄，≤ 8 條，編號 1～8）
再輸出：
| 規則 # | 規則（照抄，≤ 20 字） | 程式相關的行（照抄，含行號；沒有寫「無」） | 結果 OK / 違反 / 看不到 |
最該先修的 1 條（沒有寫「無」）：
