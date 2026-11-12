# 貼上卡：考試當天前 30 分鐘
> 用法：開考後照順序做 1 → 5。每張先在終端機跑「先跑」的指令，把輸出填進 `{{...}}`，再整張貼給模型。每張 ≤ 1200 字元，每張都能在新對話直接用。
> 寫法：第一行 `Task (EN)` 是英文任務句；資料放在 `<<<資料 開始>>>` 和 `<<<資料 結束>>>` 之間；輸出格式放在資料後面。標題後的 `→` 是下一張。
> 貼上長度：指令都用 `head` / `sed -n` 限制行數。模型說「太長」或回答變怪，就把行數砍半分兩次貼（先貼的那次加一句「先不要分析，回覆『收到』」）。
> 注意：`find` 不要用 `-not -path './.git*'`，它會把 `.gitlab-ci.yml` 也藏掉；下面的寫法只排除 `.git/` 資料夾。
> 來源：`../預製程式碼/預測考題.md`（歷屆題型、2024 完成次序分）、`cards/git-env.md`、`cards/02-read-spec.md`｜最後更新 2026-11

---

【提示卡｜開考 1/5｜repo 結構地圖】→ 開考 2（約 0:00–0:05）
Task (EN): Classify every path into one category A–G. Use only the data. Answer in Traditional Chinese.
任務：把每個檔案或資料夾分類。
先跑（在題目 repo 根目錄）：
`find . -maxdepth 3 -not -path './.git' -not -path './.git/*' -not -path '*/build/*' | sort | head -100`
`git log --oneline -5`
<<<資料 開始>>>
{{貼 find 輸出}}
{{貼 git log 輸出}}
<<<資料 結束>>>
類別：A 題目說明（README、*.md、*.pdf）　B 評分（.gitlab-ci.yml、judge、test、*.sh）　C 建置（CMakeLists.txt、Makefile、package.xml、Dockerfile）　D 主要程式　E 輔助 / 範例　F 看起來不能改（judge、測資、expected）　G 不確定
只輸出：
| 路徑 | 類別 | 理由（≤ 10 字） |
技術判斷（每項 是 / 否 + 證據檔名）：ROS 2（package.xml、*.launch.py）、pico-sdk（pico_sdk_import.cmake、*.pio）、micro-ROS（libmicroros）、純 Linux C、Python
先打開的 5 個檔：
範例（只示範格式，內容不要照抄）：| ./.gitlab-ci.yml | B | CI 評分 |

---

【提示卡｜開考 2/5｜評分流程（.gitlab-ci.yml）】→ 開考 3（約 0:05–0:12）
Task (EN): Explain each CI job in the fixed slots. Quote the YAML lines. Use only the data. Answer in Traditional Chinese.
任務：說明 CI 怎麼評分、我怎麼在本地重現。
先跑：
`wc -l .gitlab-ci.yml; sed -n 1,80p .gitlab-ci.yml`（超過 80 行，第二次貼 `sed -n 81,160p`）
`grep -rlE "judge|score|grade" --include=*.sh --include=*.py --include=*.yml . | head`
<<<資料 開始>>>
{{貼 .gitlab-ci.yml}}
[評分相關檔案] {{貼 grep 結果}}
<<<資料 結束>>>
規則：只根據資料；沒有寫「資料中沒有」。每格附 證據：「YAML 原文」。
只輸出這 7 格，每格 ≤ 2 行：
1 stages 與 job 名稱：
2 每個 job 的 image：
3 觸發條件（rules / only / commit message / 分支）：
4 建置指令：
5 評分怎麼判定、分數印在 log 哪裡：
6 本地重現的指令（照 script 抄）：
7 不能改的檔名 / 路徑 / target / 輸出格式：
範例（只示範格式，內容不要照抄）：3 觸發條件：commit message 要含題號　證據：「if: $CI_COMMIT_MESSAGE =~ /Q1/」

---

【提示卡｜開考 3/5｜題目 → 理解卡】→ 開考 4（約 0:12–0:20）
Task (EN): Fill the understanding card using only the problem text. Write 「資料中沒有」 for anything not stated. Answer in Traditional Chinese.
任務：只根據題目文字填理解卡。
先跑：`wc -c README.md; sed -n 1,60p README.md`（太長就分段：`sed -n 61,120p README.md`…）。PDF 或 Wiki 就從瀏覽器複製文字。
<<<資料 開始>>>
{{貼題目說明}}
<<<資料 結束>>>
規則：只填題目明確寫的；沒寫就寫「資料中沒有」。數字和單位照抄原文。
只輸出這張卡，每項 ≤ 2 行：
- 小題清單與配分（總分＋細項都寫，例如 X 分＝正確性 a＋速度 b）：
- 每小題的目標（一句）：
- 輸入（來源、格式、大小）：
- 輸出（目的地、格式）：
- 正確性怎麼判：
- 效能指標與單位：
- 提交方式、次數限制：
- 硬體（板子、片數、核心）：
- 不能改的檔案 / 介面：
- 不能用的方法：
- 範例輸入輸出在哪：
- 最容易誤解的 2 點：
題目太長分段貼時：前幾段只寫「第 k/N 段，先不要分析，回覆『收到』」，最後一段才貼這張卡。

---

【提示卡｜開考 4/5｜對應猜題 → 選範本】→ 開考 5（約 0:20–0:25）
Task (EN): For each sub-question, pick ONE category A–I from the list and quote the sentence that supports it. Answer in Traditional Chinese.
任務：每一小題選一個最像的類別。
<<<資料 開始>>>
{{貼開考 3 的理解卡}}
<<<資料 結束>>>
類別（→ 我的範本）：
A 電腦用 ROS 2 送資料給 Pico 算再收回、改二進位批次 → ros2/serial_bridge.py、frame.py、pico/app_serial.c
B micro-ROS（agent、MTU、sequence capacity）→ micro-ros/
C 拆給多片板子平行、依序合併 → ros2/multi_device.py、micro-ros/host_driver.py
D Pico 上跑 BNN / 排序 / SHA / CRC → algo/
E ROS 2 node 收不到 / 看不到、寫 node、CLI 除錯（topic 名、型別、QoS）→ ros2/node_template.py、ros2/README.md
F 位元欄位、位元流、endian → bits-riscv/bitops.h、packet_fields.c、bitstream.c
G PIO、RISC-V 編解碼或組語 → pico/pio/、bits-riscv/rv32_encode_decode.c、asm_examples.S
H 雙核 race、臨界區、一核收一核算 → pico/app_multicore.c、linux-perf/
I DMA 複製、count 單位、unclaim、sniffer CRC、DMA+PIO → pico/app_dma.c、app_dma_pio.c
規則：選不出來就選「都不像」。
只輸出：
| 小題 | 類別 | 證據：「題目原句」 | 範本 |
範例（只示範格式，內容不要照抄）：| 2-3 | I | 「count 是筆數不是位元組」 | pico/app_dma.c |

---

【提示卡｜開考 5/5｜時間預算與先交一版】（約 0:25–0:30）
Task (EN): Make a time plan table. Every sub-question first gets a working version submitted, then optimization. Answer in Traditional Chinese.
任務：排今天的時間表。
<<<資料 開始>>>
[現在時間 / 結束時間] {{HH:MM / HH:MM}}
[小題、配分、類別、範本]（開考 3、4 的結果）
{{貼}}
[我的熟悉度] {{熟：… 不熟：…}}
<<<資料 結束>>>
規則：
1. 計分可能有完成次序分（2024：分數 = 解題分 + (1 − 完成次序 / 考生數)）→ 每一小題先交「能動、正確」的版本，再優化。
2. 先做最有把握、最快拿分的小題。
3. 每列有時間上限；超時就交目前最好版本，換下一題。
4. 最後 30 分鐘只確認：最終版已 push、pipeline 通過。
5. push 一次就等 pipeline 結束再 push（不能同時提交多次）。
只輸出：
| 時段 | 小題 | 目標（能動版 / 某項優化） | 完成判準 | 超時備案 |
第一個能動版要做的最小改動（≤ 3 條）：
範例（只示範格式，內容不要照抄）：| 0:30–1:10 | 2-3 | 能動版：DMA count 改筆數 | CI 正確性 PASS | 先交 CPU 版 |
