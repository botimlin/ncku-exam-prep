# 貼上卡：驗證與提交（題目歧義、邊界測資、對拍、量測、micro-ROS、看懂程式、push 前檢查、CI log、git 救援）
> 用法（照 `../../考場SOP.md`）：模型寫【要卡】編號時，到 `../編號卡/` Ctrl-F 那個編號複製；提示卡把 `{{...}}` 換成你的內容，**直接貼、不要包、不寫「繼續」**；同檔的參考卡要包起來＋「繼續」。手動模式（SOP 附錄 B）：開場 1/3 → 工具卡 → 這張，一個對話一張提示卡。本檔編號：Q10（提示卡 驗證）、Q11（提示卡 提交）。每張 ≤ 1200 字元。
> 寫法：第一行 `Task (EN)` 是英文任務句；資料放在 `<<<資料 開始>>>` 和 `<<<資料 結束>>>` 之間；輸出格式放在資料後面。標題後的 `→` 是下一張。
> 流程：讀完題目 → 驗證 1（歧義，早點問助教）→ 驗證 2（邊界測資）→ 驗證 3（對拍）→ 驗證 4（量測 1：計時區段裡該移出的行）→ 驗證 5（量測 2：暖身、重複、統計）。push 前提交 1 → push → 等 pipeline → 提交 2（讀 log）。git 出事用提交 3。驗證 6 是 micro-ROS 專用；驗證 7 是看不懂程式時的學習卡。
> 來源：提交 3 的 git 指令、提交 1 的 `@{u}` 指令都在暫存 repo 用 git 2.43 實跑過；驗證 3 的骨架與 5 種比對指令、驗證 2 的產生指令在 bash 5.2 / Python 3.12 實跑過；exit code 124（timeout）/ 134 / 137 / 139 實測；micro-ROS 依 `../預製程式碼/micro-ros/README.md` §3、§4；計時依 `pico/timing.h`、`linux-perf/bench.h`｜最後更新 2026-11

---

【提示卡｜驗證 1/7｜題目有歧義：列出來問助教】→ Q10-02
Task (EN): Fill the fixed 9-row table: quote the spec sentence, judge if it allows only one reading, give readings, and how to confirm. Do not choose a reading. Answer in Traditional Chinese.
任務：找出題目可以有兩種讀法的地方，開考早點問助教。
<<<資料 開始>>>
[題目原文]（一次 ≤ 40 行）
{{貼}}
<<<資料 結束>>>
規則：
1. 原文欄照抄題目裡講到這一項的那一句；沒有講到這一項的句子就寫「題目沒提」，不要抄別的句子。
2. 解讀 A、B 都要符合原文字面，不要寫和原文相反的讀法。
3. 確認方法只能是：跑一個小測試（寫出輸入）或問助教（寫出問句）。
填法：清楚？只寫「是」或「否」。原文只能有一種讀法 = 是 → 解讀 B、確認方法都寫「無」；題目沒提 = 否。
只輸出（9 列照填，不要增減列）：
| 項目 | 原文 | 清楚？ | 解讀 A | 解讀 B | 確認方法 |
| 1 單位（bytes / 筆數 / bit） | | | | | |
| 2 上限、下限含不含 | | | | | |
| 3 大小端、位元順序 | | | | | |
| 4 輸出格式（換行、大小寫、hex） | | | | | |
| 5 空輸入或錯誤輸入 | | | | | |
| 6 計時的起點和終點 | | | | | |
| 7 可以改哪些檔案 | | | | | |
| 8 輸出順序（遞增或遞減、先後） | | | | | |
| 9 其他 | | | | | |
問助教（1 句，可以直接念）：
範例（只示範格式，內容不要照抄）：| 1 單位 | 「每批最多 512」 | 否 | 512 bytes | 512 筆 | 問助教：512 是 bytes 還是筆數？ |

---

【提示卡｜驗證 2/7｜產生邊界測資】→ Q10-03
Task (EN): For each fixed row write one concrete input and a 1-line command that creates it. Expected output only if the spec states it, else write 「跑 naive」. Answer in Traditional Chinese.
任務：依規格列出邊界測資，每列一個具體輸入。
<<<資料 開始>>>
[輸入格式與範圍]（照抄題目）{{例如 一個二進位檔，長度 0～65536 bytes}}
[程式裡的上限常數] {{例如 #define BLOCK 512}}
[輸出] {{例如 印出 CRC32（8 位 hex）}}
<<<資料 結束>>>
規則：
1. 長度用上面的常數算：剛好上限 = 常數，跨界 = 常數 + 1。
2. 預期輸出：題目原文有寫這種輸入要輸出什麼（例如空檔）就照抄，其他寫「跑 naive」，不要自己算。
3. 比範圍最小值還小、或比最大值還大的列：三格都寫「不適用」。
極值：int32 -2147483648～2147483647、uint32 0～4294967295、byte 0～255
指令可用（N 換成那列的長度）：`: > t.bin`（空檔）、`head -c N /dev/urandom > t.bin`、`head -c N /dev/zero > t.bin`、`head -c N /dev/zero | tr '\0' '\377' > t.bin`（全 0xFF）、`python3 -c "print(...)" > t.txt`
填法：具體輸入寫筆數或長度 + 內容（例：100 bytes 全 0）。
只輸出（表格 10 列照填，不要增減列）：
範圍（照抄題目）：最小＝　最大＝
| 類別 | 具體輸入 | 產生指令（1 行） | 預期輸出 |
| 1 空（0 筆 / 0 bytes） | | | |
| 2 1 筆 | | | |
| 3 剛好上限 | | | |
| 4 上限 + 1（跨界） | | | |
| 5 最大長度 | | | |
| 6 負數 / 最小值 | | | |
| 7 全 0 | | | |
| 8 全 0xFF / 最大值 | | | |
| 9 長度不是 4 的倍數 | | | |
| 10 重複值 / 已排序 / 反序 | | | |

---

【提示卡｜驗證 3/7｜寫對拍腳本】→ Q10-04
Task (EN): Pick ONE compare option A–E from 怎麼算對, then fill slots ①–⑤ of the fixed bash skeleton (④ = that option's command). Keep other lines unchanged. Answer in Traditional Chinese.
任務：照骨架寫對拍：隨機輸入 → 我的程式 vs 正確答案。
<<<資料 開始>>>
[輸入格式] {{例如 第一行 n，第二行 n 個整數}}
[我的程式] {{例如 ./build/q1}}
[正確答案] {{慢但對的 python3 naive.py / 題目給的 tests/1.out…}}
[怎麼算對]（照抄題目）{{…}}
<<<資料 結束>>>
比對：A 完全相同（題目寫「完全相同」）→ `diff -q out.txt ans.txt >/dev/null`　B 忽略行尾空白與 CRLF → `diff -q -Z --strip-trailing-cr out.txt ans.txt >/dev/null`　C 順序不重要 → `diff -q <(sort out.txt) <(sort ans.txt) >/dev/null`　D 浮點誤差 → `python3 -c "import sys;a,b=(open(f).read().split() for f in('out.txt','ans.txt'));sys.exit(len(a)!=len(b) or any(abs(float(x)-float(y))>1e-6 for x,y in zip(a,b)))"`　E 二進位 → `cmp -s out.txt ans.txt`
骨架（只換 ①–⑤，符號本身刪掉）：
```bash
# 比對：⑤
for i in $(seq 1 200); do
  ① > in.txt
  ② < in.txt > out.txt
  ③ < in.txt > ans.txt
  if ! ④; then echo "FAIL i=$i"; cp in.txt fail_in.txt; exit 1; fi
done; echo "ALL PASS"
```
填法：① 寫成 `python3 -c "…"` 一行、$i 當 random seed（不要用不存在的 gen.py）；用題目測資時 ① 寫 `cat tests/$i.in`、③ 寫 `cat tests/$i.out`。④⑤ 照抄所選比對的指令、字母 + 文字。
只輸出：
依據：「照抄怎麼算對」
完整腳本（存成 check.sh，用 bash check.sh 跑）：
---

【提示卡｜驗證 4/7｜量測 1：計時區段裡該移出的行】→ Q10-05
Task (EN): Take the start and end line numbers from the two timer lines, then for each suspicious line decide if its number is between them. Answer in Traditional Chinese.
任務：找出被計時、但不該計時的行（印出、sleep、讀寫檔、產生測資）。
先跑（f.c 換成你的檔名；計時有好幾段就一次問一段）：
`grep -nE 'time_us_64|absolute_time|clock_gettime|now_ns|perf_counter|time\.time|PRINT_US|BENCH' f.c`（只留同一段的開始、結束 2 行）
`grep -nE 'printf|print\(|puts|sleep|rand|fill_|open\(|read\(|write\(' f.c`
<<<資料 開始>>>
[計時的行]（第 1 個 grep 的輸出）
{{貼}}
[可疑的行]（第 2 個 grep 的輸出）
{{貼}}
<<<資料 結束>>>
填法：行號 = 每行最前面「:」之前的數字。開始行 = [計時的行] 第 1 行的行號，結束行 = 第 2 行的行號。之間？只寫「是」或「否」：開始行 < 行號 < 結束行 才是「是」。處理：是 → 「移出」，否 → 「不用動」。
只輸出（[可疑的行] 每行 1 列）：
開始行：
結束行：
| 行號 | 內容（照抄） | 之間？ | 處理 |
要移出的行號（沒有寫「無」）：
範例（只示範格式，內容不要照抄）：| 88 | puts("x"); | 否 | 不用動 |

---

【提示卡｜驗證 5/7｜量測 2：暖身、重複、統計】
Task (EN): For each fixed row first copy the evidence line (number + code) from the data or write 「沒有」, then mark OK / NG. Answer in Traditional Chinese.
任務：檢查量測方法可不可信，排出改法。
<<<資料 開始>>>
[平台] {{Pico 2 C / Linux C / Python}}
[要比較] {{例如 CPU 迴圈 vs DMA}}
[計時區段] {{例如 第 43～48 行（驗證 4 的開始行～結束行）}}
[程式碼，帶行號]（`cat -n f.c | sed -n 30,70p`）
{{貼}}
<<<資料 結束>>>
計時：A Pico `time_us_64()`（pico/timing.h）　B Linux `clock_gettime(CLOCK_MONOTONIC)`（linux-perf/bench.h 的 now_ns、BENCH）　C Python `time.perf_counter()`
填法：證據 = 行號 + 照抄那一行；程式裡找不到就寫「沒有」，那列就是 NG。
只輸出：
計時（照抄和平台相同的字母 + 文字）：
| 項目 | 證據（行號 + 照抄） | OK/NG |
| 1 暖身：開始行之前先跑 1 次同樣的計算 | | |
| 2 重複：計時外面有 for / while 重跑 ≥ 5 次 | | |
| 3 統計：取中位數（BENCH 取最小值也可） | | |
| 4 結果有用到：結束行之後印出計算結果（只印時間不算，不然 -O2 會刪掉計算） | | |
| 5 同輸入：新舊版用同一份資料、同大小 | | |
修改建議（≤ 3 條，附行號）：

---

【提示卡｜驗證 6/7｜micro-ROS 問題定位】→ Q04-07
Task (EN): Quote one data line, copy the matching option keyword, pick ONE cause A–H, then write its fix with the real values from the data. Answer in Traditional Chinese.
任務：判斷 micro-ROS 哪裡不通（模型不懂時先貼 `預製程式碼/micro-ros/README.md` §3、§4）。
<<<資料 開始>>>
[症狀] {{例如 topic 看得到但 echo 不到}}
[agent 最後 10 行]（`micro_ros_agent serial --dev … -v6`）
{{貼}}
[ls -l /dev/serial/by-id/; ros2 topic list; ros2 topic info -v /topic]
{{貼}}
[Pico 程式相關段，帶行號]
{{貼}}
<<<資料 結束>>>
原因（→ 修法）：
A agent 沒開或連錯 port（一直 ping 不到、by-id 有 Pico 的才是板子）→ --dev 改成 by-id 的 Pico 指到的 ttyACM
B 訊息超過 MTU（大的不見、rcl_publish 回錯；best_effort ≤ 500 B、reliable ≤ 2036 B）→ host 切小塊
C sequence 沒配 capacity（callback 有被呼叫但 data.size = 0）→ 收之前設 .data=buf; .capacity=陣列長度; .size=0
D 送出前沒設 size（收到空陣列）→ publish 前 msg.data.size = n
E executor handle 不夠（timer 會動但 sub 的 callback 從沒被呼叫、init 的 N < add_ 行數）→ init 的 N 改成 add_ 行數
F printf 搶 USB（printf 後斷線、亂碼）→ 刪 printf，改 LED
G QoS 不合（topic info -v 兩端 Reliability 不同）→ 兩端改成同一種
H namespace / topic 名打錯 → 照 ros2 topic list 改名
填法：證據照抄資料 1 行，前後加「」；關鍵字照抄選項括號裡和資料相符的字；真實值 = 修法要填的 port、行數或長度（例：add_ 有 3 行 → 3）。
只輸出 6 行：
證據：
關鍵字：
原因（照抄字母 + 文字）：
真實值：
修法（照抄所選修法，填入真實值）：
確認指令（1 行）：

---

【提示卡｜驗證 7/7｜解釋程式給我聽（學習用）】
Task (EN): First list the functions and types the code uses, then those not defined in the data, then explain the code in plain words for a high-school student. End with 3 quiz questions; answers last. Answer in Traditional Chinese.
任務：用白話一段一段解釋，讓我真的看懂。
<<<資料 開始>>>
[程式，帶行號，≤ 40 行]（`cat -n f.c | sed -n 1,40p`）
{{貼}}
[我已經懂的] {{例如 C 迴圈、陣列}}
<<<資料 結束>>>
規則：
1. 看不到定義的函式：白話欄寫「看不到定義」，依名稱猜的要標【推測】。
2. 一列可以合併幾行（例如 12–15）。
3. 不改程式、不給優化建議。
填法：用到的 = 資料裡出現的函式名稱（「(」前面的字）和型別名稱，用「、」隔開寫在同一行。看不到定義的 = 用到的裡面，資料沒有寫出內容的那些；沒有寫「無」。
只輸出：
用到的：
看不到定義的：
| 行號 | 白話（≤ 25 字） | 為什麼需要 |
整段在做什麼（1 句）：
自我測驗（3 題，只寫題目）：
答案（放最後，先不要看）：
範例（只示範格式，內容不要照抄）：| 8–9 | 把 buf 每格加到 s | 要算總和 |

---

【提示卡｜提交 1/3｜push 前檢查】→ push 後 Q11-02
Task (EN): For each fixed row copy the rule and the actual value from the named data block, then mark OK / NG / 看不到. Push only if every row is OK. Answer in Traditional Chinese.
任務：push 前逐項檢查，避免交錯檔或交壞。每個指令的輸出貼在自己那一格。
<<<資料 開始>>>
[git status -sb]
{{貼}}
[git log --oneline @{u}..HEAD] {{貼}}
[git diff --name-only @{u}..HEAD]
{{貼}}
[git diff @{u}..HEAD | grep -nE '^\+.*(DEBUG|fprintf\(stderr|// *debug|# *debug)']
{{貼，沒輸出就寫「沒有輸出」}}
[CI 規定]（可改的檔案、commit message 格式）{{貼}}
[本地 build / 測試最後 3 行] {{貼}}
[上一個 pipeline] {{已結束 / 還在跑 / 第一次交}}
<<<資料 結束>>>
填法：規定空白的列照抄 [CI 規定] 那一句。實際 = 照抄項目裡寫的那一格（檔名每個都抄）；那一格是空的才寫「看不到」。實際符合規定 = OK，不符合 = NG。
只輸出（7 列照填，不要增減列）：
| 項目 | 規定 | 實際（照抄） | OK/NG/看不到 |
| 1 name-only 的檔名 | | | |
| 2 grep 的輸出 | 沒有輸出 | | |
| 3 本地 build / 測試 | 有 PASS、沒有 FAIL | | |
| 4 git log 的訊息 | | | |
| 5 name-only 有沒有 build/ .o .uf2 .elf | 都沒有 | | |
| 6 git status 的行數 | 只有 ## 那 1 行 | | |
| 7 上一個 pipeline | 已結束或第一次交 | | |
NG 或看不到的列號（沒有寫「無」）：
判定（上一行是「無」才寫「可以 push」，否則寫「不行」）：
NG 的修法（每列 1 行指令）：

---

【提示卡｜提交 2/3｜讀 CI / judge log】→ 照「下一步」那張
Task (EN): Scan the log from the top. The FIRST error decides the type; later failures are usually caused by it. Quote lines. Answer in Traditional Chinese.
任務：從 job log 找出第一個錯誤，判斷類型。
取得：GitLab → Build → Pipelines → 紅色 job → 右上「Show complete raw」複製。太長就存成 job.log，貼 `grep -nE '^\$ |error|Error|FAIL|Wrong|Traceback|Segmentation|Abort|Timeout|timed out|Killed|exit code|[Ss]core' job.log | head -40`
<<<資料 開始>>>
{{貼 log 或 grep 結果}}
<<<資料 結束>>>
類型（→ 下一步）：
A 建置錯（error:、undefined reference、CMake Error）→ Q03-02（CMake）或 Q03-03（colcon）
B 執行時崩潰（Segmentation fault、Aborted、core dumped、Traceback、exit code 139 / 134）→ Q04-01 / Q04-02
C 答案錯（Wrong Answer、expected … got、diff 有輸出、FAIL）→ Q10-03 對拍
D 超時（Timeout、timed out、TLE、exit code 124 / 137、Killed）→ Q04-03（卡住）或 F01-00（太慢）
E 環境（pull image 失敗、no space left、runner system failure）→ 重跑或問助教
F 沒評分（job skipped、commit message 不符）→ 照 CI 規定改 commit message
規則：
1. warning 不算錯誤。「ERROR: Job failed」是總結，找不到別的錯誤才抄它。
2. 出錯指令 = 第一個錯誤上方最近的 `$ ` 開頭那行。
填法：分數 = 有 Score / 分數 字樣的那 1 行照抄，沒有就寫「資料中沒有」。關鍵字 = 第一個錯誤裡、和選項括號裡相同的字。下一步 = 所選那行 → 後面的字。
只輸出 6 行：
出錯指令：
第一個錯誤：「…」
分數那一行：
關鍵字：
類型（照抄字母 + 文字）：
下一步：

---

【提示卡｜提交 3/3｜git 救援】
Task (EN): Quote the git output, pick ONE situation A–I, and copy its commands exactly (only replace 檔名 / commit). Answer in Traditional Chinese.
任務：git 出狀況時選對指令，不丟資料。
先跑：`git status; git log --oneline -5`
<<<資料 開始>>>
[我想做的事 / 發生什麼] {{例如 不小心 git add 了 build/}}
[git 輸出或錯誤訊息]
{{貼}}
<<<資料 結束>>>
情況（→ 指令）：
A 沒 commit 的修改改壞了，想丟掉 → git restore 檔名（修改會消失）
B 誤 add 還沒 commit → git restore --staged 檔名（修改保留）；已 commit 沒 push → 先 git reset --soft HEAD~1
C 想先暫存修改 → git stash，拿回 git stash pop
D 已 commit（含已 push）的版本壞了，回上一版 → git revert --no-edit HEAD 再 git push
E 看或拿回某檔舊版 → git log --oneline -- 檔名；git show commit:檔名；git restore --source=commit 檔名
F 找哪次 commit 壞掉 → git bisect start HEAD 好的commit；git bisect run 測試指令；git bisect reset
G push 被拒（rejected、fetch first）→ git pull --rebase 再 git push（有沒 commit 的修改先 C）
H 衝突（CONFLICT、<<<<<<<）→ 改檔刪標記 → git add 檔名 → GIT_EDITOR=true git rebase --continue（merge 用 git commit --no-edit）；放棄 git rebase --abort
I 其他
規則：不要給 reset --hard、push --force、clean -f。
填法：證據只抄 git 輸出 1 行，前後加「」。會不會丟資料只寫「會」或「不會」（會就先 git stash 備份）。
只輸出 5 行：
證據：
情況（照抄字母 + 文字）：
指令（照抄，只換檔名 / commit）：
會丟資料嗎：
確認指令（1 行）：
