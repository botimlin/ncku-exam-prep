# VS Code（不能裝擴充套件）+ nano / vim 求生

> 快捷鍵不能「執行測試」，這裡的 **Linux** 快捷鍵是對照官方文件確認的：
> code.visualstudio.com 的 `docs/reference/default-keybindings`、`docs/editing/codebasics`、`docs/terminal/basics`、
> `docs/getstarted/userinterface`、`docs/sourcecontrol/overview`、`docs/debugtest/tasks`。
> 考場快捷鍵可能被改過：**Ctrl+K Ctrl+S** 打開快捷鍵設定，可以搜尋某個功能目前的按鍵。
> 忘記任何功能：**Ctrl+Shift+P**（Command Palette）輸入英文關鍵字，例如 `compare`、`wrap`、`terminal`。

## 1. 沒有擴充套件時，什麼能用、什麼不能用

| 功能 | C / C++ | Python | 替代方法 |
|---|---|---|---|
| 語法上色、括號配對、摺疊 | ✅ 內建 | ✅ 內建 | |
| 依照檔案裡出現過的字自動完成 | ✅ | ✅ | |
| F12 跳到定義、F2 重新命名、Ctrl+T 找符號 | ❌ 要 C/C++ 擴充套件 | ❌ 要 Python 擴充套件 | **Ctrl+Shift+F 搜尋函式名稱**，或終端機 `grep -rn "func(" --include='*.c' .` |
| 紅色波浪底線（錯誤） | ❌ | ❌ | 看編譯器的輸出；§5 的 tasks.json 可以讓錯誤出現在 Problems |
| Format Document（Ctrl+Shift+I） | ❌ 會說沒有 formatter | ❌ | 不要整份重新排版（會讓 git diff 變得很亂） |
| git（Source Control） | ✅ 內建 | ✅ | |
| Markdown 預覽 | ✅ Ctrl+Shift+V | | 看題目的 README.md |
| 中斷點除錯（F5） | ❌ 要擴充套件 | ❌ | 用終端機 gdb / pdb（見 `debug-host.md`） |
| 打開容器裡的資料夾（Dev Containers） | ❌ 要擴充套件 | | §6 |

## 2. 最常用的快捷鍵（Linux）

| 快捷鍵 | 功能 |
|---|---|
| **Ctrl+P** | 用檔名快速開檔（打 `ser_pro` 就能找到 `serial_proto.c`）|
| **Ctrl+Shift+P** | Command Palette（所有指令）|
| **Ctrl+Shift+F** | 在所有檔案中搜尋 |
| **Ctrl+Shift+H** | 在所有檔案中取代 |
| Ctrl+F / Ctrl+H | 在目前的檔案中搜尋 / 取代 |
| **Ctrl+G** | 跳到第幾行（編譯錯誤說 `main.c:42` → Ctrl+G 42）|
| Ctrl+Shift+O | 跳到這個檔案裡的符號（沒有語言支援時可能是空的）|
| Ctrl+Alt+- / Ctrl+Shift+- | 回到上一個位置 / 下一個位置 |
| Ctrl+Shift+\ | 跳到對應的括號 |
| **Ctrl+`** | 打開 / 關閉終端機 |
| Ctrl+Shift+` | 開一個新的終端機 |
| Ctrl+Shift+5 | 分割終端機（一邊跑程式、一邊監看）|
| Ctrl+Shift+C / Ctrl+Shift+V | 在終端機裡複製 / 貼上 |
| **Ctrl+\\** | 左右分割編輯器（一邊看 .h 一邊改 .c）|
| Ctrl+1 / Ctrl+2 / Ctrl+3 | 切換到第 1 / 2 / 3 個編輯器群組 |
| Ctrl+B | 顯示 / 隱藏側邊欄 |
| Ctrl+Shift+E | Explorer（檔案列表）|
| **Ctrl+Shift+G** | Source Control（git）|
| Ctrl+W / Ctrl+Shift+T | 關閉分頁 / 重新打開剛關掉的分頁 |
| Alt+Z | 自動換行開關（看很長的 log 時）|
| Ctrl+Shift+[ / Ctrl+Shift+] | 摺疊 / 展開程式區塊 |
| F8 | 跳到下一個 Problem |
| Ctrl+K Z | Zen mode（只剩編輯器）|

## 3. 編輯技巧

| 快捷鍵 | 功能 | 用在哪 |
|---|---|---|
| **Ctrl+/** | 註解 / 取消註解這幾行 | 暫時關掉一段程式 |
| Alt+Up / Alt+Down | 把這一行往上 / 往下移 | |
| Ctrl+Shift+Alt+Up / Down | 複製這一行到上面 / 下面 | |
| Ctrl+Shift+K | 刪除這一行 | |
| **Ctrl+D** | 選這個字，再按一次就**再多選下一個一樣的字** | 一次改好幾個變數名稱 |
| Ctrl+Shift+L | 選取**所有**一樣的字 | |
| Alt+Enter | 在搜尋框裡：選取所有找到的結果 | |
| **Alt+Click** | 多加一個游標 | |
| Shift+Alt+Up / Shift+Alt+Down | 在上面 / 下面多加一個游標 | 一次改好幾行的開頭 |
| Shift+Alt+拖曳滑鼠 | 方塊（欄）選取 | 改一整欄的數字 |

### 在所有檔案中搜尋（Ctrl+Shift+F）
- 搜尋框右邊的按鈕：`Aa` 大小寫、`ab` 整個字、`.*` **正規表示式**。
- 點 `…`（Toggle Search Details）會出現 **files to include / files to exclude**：
  - `*.c, *.h` → 只搜尋 C 檔；`src/**` → 只搜尋 src 底下；exclude 填 `build/**` → 不要搜尋 build 的產物。
  - glob 規則：`*` 是路徑中的一段、`**` 是任意多層資料夾、`?` 是一個字元。
- 常用的正規表示式：
  - `\bproto_feed\(` → 找函式在哪裡被呼叫
  - `^\w.*\bproto_feed\(` → 找函式定義（行首就開始的那一行）
  - `TODO|FIXME|BUG` → 找題目埋的提示
  - `#define\s+BUF_SIZE` → 找常數在哪裡定義

## 4. 比較檔案、看 git 差異（全部內建）

| 想做什麼 | 怎麼做 |
|---|---|
| 比較兩個檔案 | Explorer 裡用 Ctrl+Click 選兩個檔案 → 按右鍵 → **Compare Selected** |
| 比較兩個檔案（另一種方法） | 第一個檔案按右鍵 → **Select for Compare** → 第二個檔案按右鍵 → **Compare with Selected** |
| 這個檔案我改了哪裡 | 行號旁邊的顏色條：綠 = 新增、藍 = 修改、紅色三角形 = 刪除；點下去可以看原本的內容 |
| 全部改了什麼 | Ctrl+Shift+G → 點 **Changes** 底下的檔案 → 左右對照的 diff |
| commit | 在 Source Control 上面的輸入框寫訊息 → 按 Commit（檔案旁邊的 `+` 是 stage）|
| 拿回原本的版本 | 檔案旁邊的 ↶（Discard Changes）—— ⚠ 沒辦法復原 |

push 建議還是在終端機用 `git push`，才看得到完整的錯誤訊息（git 指令見 `../../prompt工具包/cards/git-env.md`）。

## 5. 用 Ctrl+Shift+B 編譯，錯誤直接點得到（tasks.json，內建）

VS Code 內建的 problem matcher **沒有 gcc 的**（`$gcc` 是 C/C++ 擴充套件提供的）→ 自己寫 regexp。
在專案裡建立 `.vscode/tasks.json`（⚠ 不要 commit 進題目的 repo，除非題目允許）：
```json
{
  "version": "2.0.0",
  "tasks": [
    {
      "label": "build",
      "type": "shell",
      "command": "cmake -S . -B build && cmake --build build -j8",
      "group": { "kind": "build", "isDefault": true },
      "problemMatcher": {
        "owner": "gcc",
        "fileLocation": ["autoDetect", "${workspaceFolder}"],
        "pattern": {
          "regexp": "^(.*):(\\d+):(\\d+):\\s+(warning|error|fatal error):\\s+(.*)$",
          "file": 1, "line": 2, "column": 3, "severity": 4, "message": 5
        }
      }
    }
  ]
}
```
- 要在容器裡編譯：`"command": "docker exec 容器名稱 bash -c 'cd /work && cmake --build build -j8'"`。
  ⚠ 容器裡的路徑（例如 `/work/main.c`）跟主機不一樣，這時候錯誤點下去可能打不開 → 就用 Ctrl+P 開檔 + Ctrl+G 跳到那一行。
- 按 **Ctrl+Shift+B** 執行，錯誤會出現在 Problems 面板（Ctrl+Shift+M），**F8** 跳到下一個。
- 這個 regexp 實測可以抓到 `main.c:2:10: fatal error: ...` 和 `w.c:5:9: warning: ...`；**抓不到連結錯誤**（`undefined reference`），那種要看終端機。

## 6. 程式在容器裡、但沒有 Dev Containers 擴充套件

1. **最好的方法**：容器啟動時有掛載（`-v "$PWD:/work"`）→ 用 VS Code **直接打開主機上的那個資料夾**來改，在終端機用 `docker exec -it 容器 bash` 進去編譯和執行。兩邊看到的是同一份檔案。
2. 確認有沒有掛載：`docker inspect -f '{{json .Mounts}}' 容器名稱`。
3. 沒有掛載 → `docker cp 容器:/path/file.c .` 拿出來改，再 `docker cp file.c 容器:/path/` 放回去（容易忘記，改完馬上放回去）。
4. ⚠ 實測：`pico-build`、`ros:jazzy-ros-core` 容器裡**沒有 vim、vi、nano**。只能在容器裡改的話：
   - `sed -i 's/舊的/新的/' file.c`（先 `grep -n 舊的 file.c` 確認只有你要改的地方）
   - 整個檔案重寫：`cat > file.c <<'EOF'` … `EOF`
5. 容器裡用 root 產生的檔案（例如 `build/`），在主機上會是 root 的，刪不掉或改不了 → `docker run -u $(id -u):$(id -g) ...`（實測 build 產物就變成自己的），或在容器裡 `rm -rf build`。

## 7. nano（最簡單；這台主機有 nano 7.2）

| 按鍵 | 功能 |
|---|---|
| 直接打字 | 編輯 |
| **Ctrl+O** 然後 Enter | 存檔 |
| **Ctrl+X** | 離開（有改過的話會問要不要存：Y / N）|
| Ctrl+W | 搜尋（再按 Alt+W 找下一個）|
| Ctrl+\\ | 取代 |
| Ctrl+K / Ctrl+U | 剪下這一行 / 貼上 |
| Ctrl+_ 或 Alt+G | 跳到第幾行 |
| `nano +42 main.c` | 打開時直接跳到第 42 行 |

## 8. vim 求生（這台主機的 `vi` 是 vim.tiny 9.1）

vim 有**兩種模式**：一般模式（按鍵是指令）和插入模式（按鍵是打字）。**不知道在哪個模式 → 按 Esc。**

| 按鍵（一般模式） | 功能 |
|---|---|
| **i** | 進入插入模式（左下角出現 `-- INSERT --`）|
| **Esc** | 回到一般模式 |
| **:wq** Enter | 存檔並離開 |
| **:q!** Enter | **不存檔**離開（改壞了就用這個）|
| :w Enter | 只存檔 |
| /字串 Enter | 搜尋；n 下一個、N 上一個 |
| :42 Enter | 跳到第 42 行 |
| u / Ctrl+R | 復原 / 重做 |
| dd / yy / p | 刪除（剪下）這一行 / 複製這一行 / 貼上 |
| x | 刪除游標上的那個字元 |
| :%s/舊/新/g Enter | 整個檔案取代 |
| :set nu Enter | 顯示行號 |

不進入 vim 也能改（實測可用）：`vi -es -c '%s/foo/bar/g' -c 'wq' file.c`。
`git commit` 沒有加 `-m` 時會跳出編輯器：如果是 vim → 按 `i` 寫訊息 → Esc → `:wq`；如果是 nano → 打字 → Ctrl+O、Enter、Ctrl+X。
以後都用 `git commit -m "訊息"` 就不會遇到。
