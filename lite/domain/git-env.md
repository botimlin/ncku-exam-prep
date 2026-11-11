# Linux / git / GitLab / 建置（精簡版）
不要自行安裝軟體；先 `which 指令` 確認有沒有。

## Shell
| 指令 | 作用 |
|---|---|
| `grep -rn "x" --include='*.c' .` | 遞迴搜尋（-w 整字、-A3 -B3 前後文）|
| `find . -name '*.c'` | 找檔案 |
| `less f`（/ 搜尋、n 下一個）、`head/tail -50`、`tail -f` | 看檔 |
| `diff -u a b`、`cmp a b`、`xxd f \| head` | 比較 / 看二進位 |
| `cmd > out 2> err`、`cmd 2>&1 \| tee log` | 導向 |
| `ps aux \| grep p`、`kill PID`、`pkill -f n` | 程序 |
| `nproc`、`time cmd`、`env \| grep PICO`、Ctrl-R | 系統 / 歷史 |
| `docker exec -it <容器> bash` | 再開一個 shell |
| tmux：`Ctrl-b c` 新窗、`n` 切換、`%` / `"` 分割、`d` 離開 | 多視窗 |

## git
```bash
git status; git diff; git diff --staged
git add f && git commit -m "msg" && git push
git log --oneline -20
git stash / git stash pop           # 暫存修改
git checkout -- f                   # 放棄修改
git checkout <commit> -- f          # 拿回舊版檔案
git diff <a> <b> -- f               # 比較版本
git diff --stat <起點>              # 改了哪些檔
git tag best-v1                     # 標記最佳版
git bisect start/bad/good/reset     # 二分找 bug
```
`reset --hard`、`push --force` 會丟資料，先 tag 再用。

## GitLab
- Build → Pipelines → Job log：編譯 / 評分輸出，失敗看這裡
- `.gitlab-ci.yml`：`image` = 評分環境，`script` = 評分實際指令 → **本地照跑可預知結果**
- push 一次 → 等 pipeline 結束 → 再 push（不得同時提交多次）

## Docker
`docker ps`｜`docker run --rm -it -v "$PWD:/work" img`｜`docker exec -it X bash`｜`docker cp X:/p .`｜容器刪掉，沒掛載的修改就消失

## gcc
`-O0/-O2/-O3/-Os`｜`-g`｜`-Wall -Wextra`｜`-pthread`｜`-lm`｜`-DX=1`｜`-fsanitize=address,undefined`｜`-fsanitize=thread`｜`-S` 輸出組語

## make / CMake
```bash
make -j$(nproc); make clean; make -n     # -n：只印指令不執行
make VERBOSE=1                           # 看完整編譯指令
cmake -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build -j
rm -rf build                             # 快取問題時完全重建
```

## 看二進位
`objdump -d`（交叉工具鏈加前綴：`arm-none-eabi-`、`riscv32-unknown-elf-`，實際名稱用 tab 補全確認）｜`nm`｜`size`｜pico-sdk 會產生 `.dis` 反組譯與 `.map`
