# Linux / git / GitLab / 容器 / 建置工具速查

> 用途：考場作答環境的基本操作。考試透過 GitLab 網站與容器環境進行，評分為 Online Judge。
> 適用：Linux shell（bash）、git 2.x、GitLab、Docker、GNU make、gcc、CMake。
> 來源：git-scm.com/docs、docs.gitlab.com、docs.docker.com、GNU make / gcc 手冊。
> 最後更新：2026-11
>
> 注意：考場規則禁止自行安裝軟體。以下指令若環境沒有（`which 指令` 檢查），就用替代方法，不要安裝。

---

## 1. Shell 必備

### 1.1 檔案與搜尋

| 指令 | 作用 |
|---|---|
| `ls -la` / `tree -L 2`（若有）| 列出檔案 |
| `find . -name '*.c'` | 依名稱找檔案 |
| `find . -newer file.c` | 比 file.c 新的檔案 |
| `grep -rn "pattern" .` | 遞迴搜尋，顯示行號 |
| `grep -rn "pattern" --include='*.c' --include='*.h' .` | 只搜特定副檔名 |
| `grep -rnw "word" .` | 整個單字比對 |
| `grep -rn -A3 -B3 "pattern" file` | 顯示前後 3 行 |
| `less file`（`/` 搜尋、`n` 下一個、`q` 離開）| 分頁看長檔案 |
| `head -50 file` / `tail -50 file` / `tail -f log` | 開頭 / 結尾 / 持續追蹤 |
| `wc -l file` | 行數 |
| `diff -u a b` / `cmp a b` | 文字差異 / 二進位比較 |
| `xxd file \| head` / `hexdump -C file \| head` | 看二進位內容 |
| `sort \| uniq -c` | 統計重複次數 |

### 1.2 程序與系統

| 指令 | 作用 |
|---|---|
| `Ctrl-C` | 中止前景程式 |
| `Ctrl-Z` → `bg` / `fg` | 暫停 → 背景 / 前景 |
| `cmd &` | 背景執行 |
| `cmd > out.txt 2> err.txt` | stdout、stderr 分別導向 |
| `cmd 2>&1 \| tee log.txt` | 同時看到並存檔 |
| `ps aux \| grep prog` | 找程序 |
| `kill PID` / `kill -9 PID` | 結束程序 / 強制結束 |
| `pkill -f name` | 依名稱結束 |
| `top` / `htop`（若有）| CPU / 記憶體使用 |
| `nproc` | 可用 CPU 數 |
| `time cmd` | 執行時間 |
| `echo $VAR` / `env \| grep PICO` | 環境變數 |
| `which cmd` | 指令在哪、有沒有安裝 |
| `history \| grep make` | 找之前打過的指令 |
| `Ctrl-R` | 反向搜尋歷史指令 |

### 1.3 多個終端機

- 容器內若有 `tmux`：`tmux` 開新 session；`Ctrl-b c` 新視窗、`Ctrl-b n` 切換、`Ctrl-b %` 左右分割、`Ctrl-b "` 上下分割、`Ctrl-b d` 離開（session 保留）、`tmux attach` 回去。
- Docker：`docker exec -it <容器名> bash` 再開一個 shell 進同一個容器。
- ROS 2：每個新 shell 要 `source /opt/ros/jazzy/setup.bash`（除非 `.bashrc` 已設定）。

---

## 2. git

### 2.1 日常流程

```bash
git clone <url>                       # 取得專案（GitLab 網頁上的 Clone 按鈕複製 HTTPS 網址）
git status                            # 目前狀態
git diff                              # 尚未 add 的修改
git diff --staged                     # 已 add 尚未 commit 的修改
git add file.c                        # 加入要 commit 的檔案
git commit -m "說明改了什麼"
git push                              # 推到遠端（第一次可能要 git push -u origin <branch>）
git pull                              # 拉遠端更新
git log --oneline --graph -20         # 歷史
```

### 2.2 救援與比較

| 需求 | 指令 |
|---|---|
| 放棄某檔案的未 commit 修改 | `git checkout -- file.c`（或 `git restore file.c`）|
| 取消 add | `git reset file.c`（或 `git restore --staged file.c`）|
| 暫存目前修改 | `git stash` / 拿回：`git stash pop` / 列表：`git stash list` |
| 看某個 commit 改了什麼 | `git show <commit>` |
| 兩個版本的差異 | `git diff <a> <b> -- file.c` |
| 拿回舊版本的某個檔案 | `git checkout <commit> -- file.c` |
| 標記最佳版本 | `git tag best-v1`（之後 `git checkout best-v1 -- .` 可整個拿回）|
| 撤銷某個 commit 的改動（新增一個反向 commit，保留歷史）| `git revert <commit>` |
| 改了哪些檔案 | `git diff --stat <起始commit>` |
| 誰改了這行 | `git blame file.c` |
| 二分法找 bug | `git bisect start` → `git bisect bad` → `git bisect good <commit>` → 測試後標 good/bad → `git bisect reset` |

### 2.3 注意

- `git reset --hard`、`git push --force` 會丟失資料，非必要不用；用之前先 `git tag` 備份。
- 憑證：考試提供的帳號密碼只用在考試的 GitLab。不要存到別的地方。
- `.gitignore` 確認 `build/` 等產物不會被加入。

---

## 3. GitLab

| 功能 | 位置 / 用途 |
|---|---|
| Code → Repository（舊版：Repository → Files）| 瀏覽檔案 |
| Code → Commits（舊版：Repository → Commits）| 提交歷史 |
| Build → Pipelines（舊版：CI/CD → Pipelines）| 每次 push 觸發的 CI 工作；**評分結果可能在這裡** |
| Pipeline → Job → log | 編譯 / 測試 / 評分的完整輸出，失敗時看這裡 |
| `.gitlab-ci.yml` | 定義 pipeline 做什麼；讀它可以知道評分怎麼跑 |
| Plan → Issues / Wiki（舊版在左側欄直接列出）| 題目說明可能放在這 |

**評分若由 push 觸發**：push 一次 → 等 pipeline 結束 → 看結果 → 才再 push。考場規則：不得同時提交多次作答。

讀 `.gitlab-ci.yml` 要看的重點：

```yaml
stages: [build, test]       # 有哪些階段
build-job:
  stage: build              # 沒寫 stage 的 job 預設屬於 test
  image: ...                # 用哪個容器映像（= 評分環境）
  script:                   # 實際執行的指令（= 評分的編譯與執行方式）
    - cmake -B build -DCMAKE_BUILD_TYPE=Release ...
    - make -C build
  artifacts: ...            # 輸出
```

**在本地照 `script` 的指令跑一次，就能在提交前預知評分結果。**

---

## 4. Docker

| 指令 | 作用 |
|---|---|
| `docker ps` | 執行中的容器 |
| `docker ps -a` | 所有容器 |
| `docker images` | 映像 |
| `docker run --rm -it --name X image` | 啟動並進入（離開即刪除）|
| `docker run --rm -it -v "$PWD:/work" image` | 掛載目前資料夾（修改會保留在主機）|
| `docker exec -it X bash` | 在執行中的容器再開一個 shell |
| `docker cp X:/path/file .` | 從容器複製檔案出來 |
| `docker logs X` | 容器輸出 |
| `docker rm -f X` | 強制刪除容器 |

重點：**容器刪除後，沒有掛載到主機的修改會消失。** 重要的東西記得 commit / push 或掛載。

---

## 5. 建置工具

### 5.1 gcc 常用旗標

| 旗標 | 作用 |
|---|---|
| `-O0` / `-O2` / `-O3` / `-Os` | 不最佳化（除錯用）/ 標準 / 積極 / 最小程式碼 |
| `-g` | 除錯資訊（給 gdb）|
| `-Wall -Wextra` | 開啟警告 |
| `-pthread` | 多執行緒（編譯與連結都要）|
| `-lm` | 連結數學函式庫 |
| `-DNAME=value` | 定義巨集 |
| `-fsanitize=address,undefined` | 偵測記憶體錯誤、未定義行為 |
| `-fsanitize=thread` | 偵測資料競爭 |
| `-S` | 輸出組合語言（.s）|
| `-march=native` | 針對本機 CPU（評分機器不同時別用）|

### 5.2 make

```bash
make               # 預設目標
make -j$(nproc)    # 平行編譯
make clean
make -n            # 只印出會執行的指令，不執行（看它怎麼編譯）
make VERBOSE=1     # CMake 產生的 Makefile：顯示完整編譯指令
make help          # 若 Makefile 有定義
```

### 5.3 CMake

```bash
cmake -B build -S .                          # 產生建置檔到 build/
cmake -B build -DCMAKE_BUILD_TYPE=Release    # Release 建置
cmake --build build -j                       # 編譯
cmake --build build --target clean
rm -rf build && cmake -B build && cmake --build build   # 完全重建
```

CMake 快取問題（改了設定沒效果）：刪掉 `build/` 重來。

### 5.4 看組合語言 / 二進位

```bash
objdump -d prog | less                        # 反組譯（本機）
arm-none-eabi-objdump -d prog.elf             # ARM 目標
riscv32-unknown-elf-objdump -d prog.elf       # RISC-V 目標（實際名稱依工具鏈而定，用 `compgen -c | grep objdump` 或 tab 補全找）
nm prog | grep func                           # 符號
size prog.elf                                 # 各區段大小
```

pico-sdk：CMakeLists 有 `pico_add_extra_outputs(目標)` 時，建置會產生 `.dis`（反組譯）與 `.map`（記憶體配置）檔，可直接看；沒有就自己 `objdump -d`。

---

## 6. 給模型的提示範本

```
我在 {{環境：容器 / 開發板}} 中想做 {{目的}}。
目前可用的工具：{{which 檢查的結果}}
請給我具體指令，並說明每個指令的作用。不要用需要另外安裝的工具。
```

```
這是 .gitlab-ci.yml 的內容。請說明評分流程的每一步在做什麼，
以及我如何在本地重現同樣的建置與測試：
{{貼內容}}
```

```
這是 CI pipeline 的 job log（失敗）。請找出失敗的原因和第一個錯誤：
{{貼 log}}
```
