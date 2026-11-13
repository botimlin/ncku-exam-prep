# 貼上卡：git / GitLab / 容器 / Shell
> 用法（照 `../../考場SOP.md`）：模型寫【要卡】編號時，到 `../編號卡/` Ctrl-F 那個編號複製這張卡，包在 `<<<資料 開始>>>`…`<<<資料 結束>>>` 裡、最後一行寫「繼續」再貼。本檔編號：L14（參考卡 git/環境）。每張 ≤ 1200 字元。
> 來源：full/domain/git-env.md、lite/domain/git-env.md（詳細版）｜最後更新 2026-11

---

【參考卡｜git/環境 1/4｜GitLab pipeline 與 job log】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
環境：考試透過 GitLab 網站與容器環境進行，評分為 Online Judge。考場禁止自行安裝軟體。
GitLab 選單位置（新版；括號為舊版）：
- Code → Repository（Repository → Files）：瀏覽檔案
- Code → Commits（Repository → Commits）：提交歷史
- Build → Pipelines（CI/CD → Pipelines）：每次 push 觸發的 CI 工作；評分結果可能在這裡
- Pipeline → Job → log：編譯 / 測試 / 評分的完整輸出，失敗時看這裡
- Plan → Issues / Wiki：題目說明可能放在這
`.gitlab-ci.yml` 要看的重點：
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
- 在本地照 `script` 的指令跑一次，就能在提交前預知評分結果。
- 評分若由 push 觸發：push 一次 → 等 pipeline 結束 → 看結果 → 才再 push。考場規則：不得同時提交多次作答。
失敗時：打開該 job 的 log，找失敗原因與第一個錯誤，對照 `.gitlab-ci.yml` 的 script 看是哪一個指令失敗。
提問範例：「這是 CI pipeline 的 job log（失敗）。請找出失敗的原因和第一個錯誤：〈貼 log〉」；「這是 .gitlab-ci.yml，請說明評分流程每一步在做什麼，以及我如何在本地重現同樣的建置與測試：〈貼內容〉」

---

【參考卡｜git/環境 2/4｜git 日常與救援】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
環境：git 2.x，遠端為考試的 GitLab。
日常：
```bash
git status                            # 目前狀態
git diff                              # 尚未 add 的修改
git diff --staged                     # 已 add 尚未 commit 的修改
git add file.c
git commit -m "說明改了什麼"
git push                              # 第一次可能要 git push -u origin <branch>
git pull
git log --oneline --graph -20
```
救援與比較：
- 放棄某檔未 commit 修改：`git checkout -- file.c`（或 `git restore file.c`）
- 取消 add：`git reset file.c`（或 `git restore --staged file.c`）
- 暫存修改：`git stash`；拿回 `git stash pop`；列表 `git stash list`
- 看某 commit 改了什麼：`git show <commit>`
- 兩版本差異：`git diff <a> <b> -- file.c`
- 拿回舊版某檔：`git checkout <commit> -- file.c`
- 標記最佳版：`git tag best-v1`；之後 `git checkout best-v1 -- .` 整個拿回
- 撤銷某 commit（新增反向 commit，保留歷史）：`git revert <commit>`
- 改了哪些檔：`git diff --stat <起始commit>`
- 誰改了這行：`git blame file.c`
- 二分找 bug：`git bisect start` → `git bisect bad` → `git bisect good <commit>` → 測試後標 good/bad → `git bisect reset`
注意：`git reset --hard`、`git push --force` 會丟資料，非必要不用，用前先 `git tag` 備份。考試帳密只用在考試 GitLab。`.gitignore` 確認 `build/` 等產物不會被加入。

---

【參考卡｜git/環境 3/4｜Shell 與 Docker 容器】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
環境：Linux bash、Docker。考場禁止安裝軟體，先 `which 指令` 確認有沒有。
搜尋與看檔：
- `grep -rn "pattern" --include='*.c' --include='*.h' .`（`-w` 整字、`-A3 -B3` 前後文）
- `find . -name '*.c'`；`find . -newer file.c`
- `less file`（`/` 搜尋、`n` 下一個、`q` 離開）；`head -50` / `tail -50` / `tail -f log`
- `diff -u a b`、`cmp a b`、`xxd file | head`、`wc -l`、`sort | uniq -c`
程序與導向：
- `cmd > out.txt 2> err.txt`；`cmd 2>&1 | tee log.txt`
- `Ctrl-C` 中止；`Ctrl-Z` → `bg` / `fg`；`cmd &` 背景
- `ps aux | grep prog`、`kill PID`、`kill -9 PID`、`pkill -f name`、`top`
- `nproc`、`time cmd`、`env | grep PICO`、`which cmd`、`history | grep make`、`Ctrl-R`
多終端機：tmux（若有）`Ctrl-b c` 新視窗、`n` 切換、`%` 左右分割、`"` 上下分割、`d` 離開、`tmux attach` 回去；或 `docker exec -it <容器名> bash` 再開一個 shell。ROS 2：每個新 shell 要 `source /opt/ros/jazzy/setup.bash`（除非 .bashrc 已設定）。
Docker：
- `docker ps`（執行中）/ `docker ps -a`（全部）/ `docker images`
- `docker run --rm -it --name X image`：啟動並進入，離開即刪除
- `docker run --rm -it -v "$PWD:/work" image`：掛載目前資料夾，修改保留在主機
- `docker exec -it X bash`：在執行中的容器再開 shell
- `docker cp X:/path/file .`；`docker logs X`；`docker rm -f X`
重點：容器刪除後，沒掛載到主機的修改會消失。重要的東西 commit / push 或掛載。

---

【參考卡｜git/環境 4/4｜gcc、make、CMake、看二進位】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
環境：GNU gcc / make、CMake；嵌入式交叉工具鏈（pico-sdk）。
gcc 旗標：
- `-O0`（除錯）/ `-O2`（標準）/ `-O3`（積極）/ `-Os`（最小）
- `-g` 除錯資訊；`-Wall -Wextra` 警告；`-pthread`（編譯與連結都要）；`-lm` 數學庫；`-DNAME=value`
- `-fsanitize=address,undefined` 記憶體錯誤 / UB；`-fsanitize=thread` 資料競爭
- `-S` 輸出組合語言；`-march=native` 針對本機 CPU（評分機器不同時別用）
make：
```bash
make -j$(nproc)    # 平行編譯
make clean
make -n            # 只印出會執行的指令，不執行
make VERBOSE=1     # CMake 產生的 Makefile：顯示完整編譯指令
```
CMake：
```bash
cmake -B build -DCMAKE_BUILD_TYPE=Release    # 產生建置檔到 build/
cmake --build build -j                       # 編譯
rm -rf build && cmake -B build && cmake --build build   # 完全重建
```
改了設定沒效果 = CMake 快取問題 → 刪掉 `build/` 重來。
看二進位：
```bash
objdump -d prog | less                        # 反組譯（本機）
arm-none-eabi-objdump -d prog.elf             # ARM 目標
riscv32-unknown-elf-objdump -d prog.elf       # RISC-V 目標（實際名稱依工具鏈而定）
nm prog | grep func                           # 符號
size prog.elf                                 # 各區段大小
```
- 交叉工具鏈實際名稱用 `compgen -c | grep objdump` 或 tab 補全找。
- pico-sdk：CMakeLists 有 `pico_add_extra_outputs(目標)` 時，建置會產生 `.dis`（反組譯）與 `.map`（記憶體配置）檔，可直接看。
