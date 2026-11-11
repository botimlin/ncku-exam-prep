# 貼上卡：驗證與提交（題目歧義、邊界測資、對拍、量測、micro-ROS、看懂程式、push 前檢查、CI log、git 救援）
> 用法：一次只複製一張卡（兩條分隔線之間），先跑卡上「先跑」的指令，把輸出填進 `{{...}}`，再整張貼進對話送出。每張 ≤ 1200 字元，每張都能在新對話直接用。
> 寫法：第一行 `Task (EN)` 是英文任務句；資料放在 `<<<資料 開始>>>` 和 `<<<資料 結束>>>` 之間；輸出格式放在資料後面。標題後的 `→` 是下一張。
> 流程：讀完題目 → 驗證 1（歧義，早點問助教）→ 驗證 2（邊界測資）→ 驗證 3（對拍）→ 驗證 4（量測）。push 前提交 1 → push → 等 pipeline → 提交 2（讀 log）。git 出事用提交 3。驗證 5 是 micro-ROS 專用；驗證 6 是看不懂程式時的學習卡。
> 來源：提交 3 的 git 指令、提交 1 的 `@{u}` 指令都在暫存 repo 用 git 2.43 實跑過；驗證 3 的骨架與 5 種比對指令、驗證 2 的產生指令在 bash 5.2 / Python 3.12 實跑過；exit code 124（timeout）/ 134 / 137 / 139 實測；micro-ROS 依 `../預製程式碼/micro-ros/README.md` §3、§4；計時依 `pico/timing.h`、`linux-perf/bench.h`｜最後更新 2026-11

---

【提示卡｜驗證 1/6｜題目有歧義：列出來問助教】→ 驗證 2
Task (EN): Fill the fixed 8-row table: quote the spec sentence, give two readings, and how to confirm. Do not choose a reading. Answer in Traditional Chinese.
任務：找出題目可以有兩種讀法的地方，開考早點問助教。
<<<資料 開始>>>
[題目原文]（一次 ≤ 40 行）
{{貼}}
<<<資料 結束>>>
規則：
1. 原文欄不能空白：照抄題目一句；題目沒提到就寫「題目沒提」，不要自己補。
2. 解讀 A、B 都要符合原文字面；原文已經寫清楚（只有一種讀法）→ 解讀 B 寫「無」。
3. 確認方法只能是：跑一個小測試（寫出輸入）或問助教（寫出問句）。
只輸出（8 列照填，不要增減列）：
| 項目 | 原文 | 解讀 A | 解讀 B | 確認方法 |
| 1 單位（bytes / 筆數 / bit） | | | | |
| 2 邊界（含不含、< 或 ≤） | | | | |
| 3 大小端、位元順序 | | | | |
| 4 輸出格式（換行、大小寫、hex、遞增或遞減） | | | | |
| 5 空輸入或錯誤輸入怎麼處理 | | | | |
| 6 計時範圍（含不含傳輸、初始化） | | | | |
| 7 可以改哪些檔案 | | | | |
| 8 其他 | | | | |
問助教（1 句，可以直接念）：
範例（只示範格式，內容不要照抄）：| 1 單位 | 「每批最多 512」 | 512 bytes | 512 筆 | 問助教：512 是 bytes 還是筆數？ |

---

【提示卡｜驗證 2/6｜產生邊界測資】→ 驗證 3
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

【提示卡｜驗證 3/6｜寫對拍腳本】→ 驗證 4
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

【提示卡｜驗證 4/6｜量測設計：量哪段、怎麼量】
Task (EN): The timed region runs from the 1st to the 2nd timer call. Copy every line inside it, mark lines that print/sleep/do I/O/make test data, then fill the fixed plan table. Answer in Traditional Chinese.
任務：檢查我的計時區段，排出可信的量測方法。
<<<資料 開始>>>
[平台] {{Pico 2 C / Linux C / Python}}
[要比較] {{例如 CPU 迴圈 vs DMA}}
[程式碼，帶行號]（`cat -n f.c | sed -n 30,70p`）
{{貼}}
<<<資料 結束>>>
計時：A Pico `time_us_64()`（pico/timing.h）　B Linux `clock_gettime(CLOCK_MONOTONIC)`（linux-perf/bench.h 的 now_ns、BENCH）　C Python `time.perf_counter()`
規則：
1. 區段內的 printf / print / puts / sleep / 檔案或序列埠讀寫 / 產生測資（random、fill_random）→ 標「移出」。
2. 結果要在區段外用到（印 checksum 或 do_not_optimize），不然 -O2 會把計算刪掉。
填法：行號照抄資料最左邊的數字。開始行 = 第 1 個計時呼叫那行，結束行 = 第 2 個計時呼叫那行（後面的 print 不算區段內）。表格：程式裡看不到這個做法就寫 NG。
只輸出：
開始行：
結束行：
區段內每一行（逐行照抄，行尾標 OK 或 移出）：
計時（照抄和平台相同的 1 個）：
| 項目 | 做法 | 我的程式 OK/NG |
| 1 暖身 | 計時前先跑 1 次不計時 | |
| 2 重複 | 計時外面有迴圈重跑 ≥ 5 次 | |
| 3 統計 | 取中位數（BENCH 取最小值也可） | |
| 4 區段內乾淨 | 上面沒有標「移出」的行 | |
| 5 結果有用到 | 結束行之後有印出計算結果或 checksum | |
| 6 同輸入 | 新舊版用同一份資料、同大小 | |
修改建議（≤ 3 條，附行號）：

---

【提示卡｜驗證 5/6｜micro-ROS 問題定位】→ 工具 7
Task (EN): Quote one data line, copy the option keyword it matches, then pick ONE cause A–H and copy its fix with real names from the data. Do not invent API. Answer in Traditional Chinese.
任務：判斷 micro-ROS 哪裡不通（模型不懂時先在同一對話貼 `預製程式碼/micro-ros/README.md` §3、§4）。
<<<資料 開始>>>
[症狀] {{例如 topic 看得到但 echo 不到}}
[agent 最後 10 行]（`micro_ros_agent serial --dev … -v6`）
{{貼}}
[ls /dev/ttyACM*; ros2 topic list; ros2 topic info -v /topic]
{{貼}}
[Pico 程式相關段，帶行號]
{{貼}}
<<<資料 結束>>>
原因（→ 修法）：
A agent 沒開或連錯 port（一直 ping 不到、by-id 名稱有 Pico 的才是板子、被 minicom 佔用）→ --dev 改成板子那個 /dev/ttyACM*
B 訊息超過 MTU（大的不見、rcl_publish 回錯；best_effort ≤ 500 B、reliable ≤ 2036 B）→ host 切小塊
C sequence 沒配 capacity（callback 有被呼叫但 data.size = 0）→ 收之前設 .data=buf; .capacity=N; .size=0
D 送出前沒設 size（收到空陣列）→ publish 前 msg.data.size = n
E executor handle 不夠（timer 會動但 sub 的 callback 從沒被呼叫、init 的 N < add_* 行數）→ rclc_executor_init 的 N 改成 add_* 的行數
F printf 搶 USB（printf 後斷線、亂碼）→ 刪 printf，改 LED
G QoS 不合（topic info -v 兩端 Reliability 不同）→ 兩端同為 reliable 或 best_effort
H namespace / topic 名打錯 → 照 ros2 topic list 改名
填法：證據照抄資料 1 行，前後加「」；關鍵字照抄選項括號裡和資料相符的字。
只輸出 5 行：
證據：
關鍵字：
原因（照抄字母 + 文字）：
修法（照抄所選修法，換成資料裡的名稱）：
確認指令（1 行）：

---

【提示卡｜驗證 6/6｜解釋程式給我聽（學習用）】
Task (EN): Explain the code in plain words for a high-school student. For functions not defined in the data write 「看不到定義」. End with 3 quiz questions; put the answers last. Answer in Traditional Chinese.
任務：用白話一段一段解釋，讓我真的看懂。
<<<資料 開始>>>
[程式，帶行號，≤ 40 行]（`cat -n f.c | sed -n 1,40p`）
{{貼}}
[我已經懂的] {{例如 C 迴圈、陣列}}
<<<資料 結束>>>
規則：
1. 資料裡沒有定義的函式或巨集：白話欄寫「看不到定義」，依名稱猜的要標【推測】。
2. 一列可以合併幾行（例如 12–15）。
3. 不改程式、不給優化建議。
填法：看不到定義的 = 資料裡有呼叫、但沒寫出內容的函式或型別，名稱用「、」隔開寫在同一行；沒有寫「無」。
只輸出：
看不到定義的：
| 行號 | 白話（≤ 25 字） | 為什麼需要 |
整段在做什麼（1 句）：
自我測驗（3 題，只寫題目）：
答案（放最後，先不要看）：
範例（只示範格式，內容不要照抄）：| 8–9 | 把 buf 每格加到 s | 要算總和 |

---

【提示卡｜提交 1/3｜push 前檢查】→ push 後 提交 2
Task (EN): For each fixed row, first copy the evidence from the data, then mark OK / NG / 看不到. Push only if every row is OK. Answer in Traditional Chinese.
任務：push 前逐項檢查，避免交錯檔或交壞。
先跑：`git status -sb; git log --oneline @{u}..HEAD; git diff --stat @{u}..HEAD; git diff @{u}..HEAD | grep -nE '^\+.*(printf|print\(|DEBUG)'`
<<<資料 開始>>>
[上面指令的輸出]
{{貼}}
[題目 / CI 規定]（可改的檔案、commit message 格式）{{貼}}
[本地 build / 測試最後 3 行] {{貼}}
[上一個 pipeline] {{已結束 / 還在跑 / 第一次交}}
<<<資料 結束>>>
規則：證據照抄資料原文（diff --stat 只抄檔名，不抄 `|`）；資料裡沒有就寫「看不到」，不要猜 OK。
填法：第 1 列有任何一個檔名不在允許範圍就 NG。判定：7 列都 OK 才寫「可以 push」，否則寫「不行」。
只輸出（7 列照填，不要增減列）：
| 項目 | 證據（照抄） | OK/NG/看不到 |
| 1 diff --stat 每個檔名都允許修改 | | |
| 2 沒有 debug 輸出（grep 沒輸出 = OK） | | |
| 3 本地 build / 測試通過 | | |
| 4 commit message（git log 那行 hash 後的字）符合規定 | | |
| 5 diff --stat 沒有 build/、*.o、*.uf2、*.elf、Bin | | |
| 6 git status 沒有該交卻沒 commit 的檔 | | |
| 7 上一個 pipeline 已結束（不能同時提交多次） | | |
判定：
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
A 建置錯（error:、undefined reference、CMake Error）→ 05 建置卡
B 執行時崩潰（Segmentation fault、Aborted、core dumped、Traceback、exit code 139 / 134）→ 工具 1 / 2
C 答案錯（Wrong Answer、expected … got、diff 有輸出、FAIL）→ 驗證 3 對拍
D 超時（Timeout、timed out、TLE、exit code 124 / 137、Killed）→ 驗證 4 量測
E 環境（pull image 失敗、no space left、runner system failure）→ 重跑或問助教
F 沒評分（job skipped、commit message 不符）→ 照 CI 規定改 commit message
規則：
1. warning 不算錯誤。「ERROR: Job failed」是總結，找不到別的錯誤才抄它。
2. 出錯指令 = 第一個錯誤上方最近的 `$ ` 開頭那行。
填法：分數 = 有 Score / 分數 字樣的那 1 行照抄；沒有就寫「資料中沒有」。
只輸出 6 行：
失敗的 job：
出錯指令：
第一個錯誤：「…」
分數那一行：
類型（照抄字母 + 文字）：
下一步（照抄同一個字母 → 後面）：

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
