# 04 除錯：系統化找出問題

> 用途：程式編譯不過、跑不起來、結果不對、卡住、時好時壞時，照流程排查，並用固定格式向模型回報問題。
> 最後更新：2026-11

---

## 0. 通用除錯流程

```
① 重現：穩定地讓問題出現（同樣的輸入、同樣的步驟）
        ↓
② 縮小：找出最小的重現條件（最少的程式、最小的輸入）
        ↓
③ 假設：列出可能原因（2–4 個），依可能性排序
        ↓
④ 驗證：每個假設設計一個能區分真假的實驗（加 print、改輸入、註解掉某段）
        ↓
⑤ 修正：只改確認的原因
        ↓
⑥ 回歸：確認問題消失，且原本正常的功能沒壞
```

### 時間止損規則

- **同一個問題卡 20 分鐘** → 停下來，寫錯誤回報給模型，或換個角度（回到上一個能用的版本、用二分法找）。
- **卡 40 分鐘** → 認真考慮放棄這條路，回到上一個能用的 commit，改做別的。
- 「上一個能用的版本」永遠要存在：每次能用就 `git commit`。

---

## 1. 向模型回報錯誤的格式

模型的除錯品質取決於你給的資訊。**一律用這個格式**：

```
/除錯
【做了什麼】我執行了 {{指令}}，目的是 {{目的}}
【預期】{{應該發生什麼}}
【實際】{{實際發生什麼}}
【完整錯誤訊息】（不要只貼最後一行；編譯錯誤貼「第一個」error 及其前後）
{{貼錯誤}}
【相關程式碼】（出錯的函式、最近改過的地方）
{{貼程式碼}}
【最近改了什麼】{{上次能用之後改了哪些東西}}
【已經試過】{{試過什麼、結果如何}}
【環境】{{Linux 容器 / 開發板；ARM 或 RISC-V；編譯指令}}

請：列出可能原因（依可能性排序）→ 每個原因的驗證方法 → 最可能的修正。
不要一次給大量修改。
```

---

## 2. 依症狀分類的排查手冊

### 2.1 編譯錯誤

| 訊息 | 常見原因 | 處理 |
|---|---|---|
| 很多錯誤 | 通常是第一個錯誤連鎖引起 | **只看第一個 error**，修完重新編譯 |
| `implicit declaration of function` | 少 `#include`，或函式名拼錯 | 找該函式在哪個 header：`grep -rn "函式名" $PICO_SDK_PATH/src --include=*.h` |
| `unknown type name` | 少 include 或型別名稱錯 | 同上 |
| `expected ';' before` | 語法錯誤，常在**前一行** | 看報錯位置的前一行 |
| `incompatible pointer type` | 指標型別不符 | 確認函式簽名 |
| `No such file or directory`（header）| include 路徑或 CMake 沒連對應函式庫 | pico-sdk 中 `target_link_libraries` 要加 `hardware_dma` 等 |

### 2.2 連結錯誤

| 訊息 | 常見原因 | 處理 |
|---|---|---|
| `undefined reference to 'xxx'` | 函式有宣告沒定義；或沒連結對應函式庫；或 C/C++ 名稱修飾問題 | pico-sdk：CMakeLists.txt 的 `target_link_libraries(... hardware_xxx pico_xxx)`；pthread：加 `-pthread`；math：加 `-lm` |
| `multiple definition of` | 同一個函式 / 變數在多個 .c 定義 | header 中的變數要用 `extern`，定義放在一個 .c |
| `region 'RAM' overflowed` | 記憶體不夠 | 縮小 buffer、改用 const 放 flash |

### 2.3 程式執行後崩潰

**Linux：**
```bash
gcc -g -O0 -fsanitize=address,undefined -o prog prog.c   # 越界、use-after-free、未定義行為
./prog
gdb ./prog                    # 然後：run → 崩潰後 bt（看呼叫堆疊）→ frame N → print 變數
```

常見原因：陣列越界、空指標、使用已釋放記憶體、堆疊溢位（大陣列放區域變數）、整數溢位導致索引錯誤。

**微控制器：**
- 卡在 hard fault / 板子沒反應 → 通常是非法位址存取、堆疊溢位、未對齊存取。
- 用 printf 二分法：在不同位置印標記，找出最後一個印出來的地方。
- 有除錯器（SWD + gdb）才能看堆疊；考場可能沒有，以 printf / GPIO 為主。

### 2.4 程式卡住（hang）

| 可能原因 | 檢查 |
|---|---|
| 阻塞呼叫等不到東西 | `*_blocking` 函式、`pio_sm_get_blocking`（RX FIFO 一直空）、`multicore_fifo_pop_blocking`、`dma_channel_wait_for_finish_blocking`（DMA 沒啟動或設定錯）|
| 死結（deadlock） | 兩個鎖取得順序不一致；拿著鎖呼叫會再拿同一把鎖的函式 |
| 等待的條件永遠不成立 | 輪詢的變數沒加 `volatile` 或沒用原子操作，編譯器把讀取最佳化掉了 |
| 中斷沒觸發 | 沒致能、handler 沒註冊、沒清除中斷旗標導致一直重入 |
| 無窮迴圈 | 迴圈條件、unsigned 遞減到 0 以下（`for (unsigned i = n; i >= 0; i--)` 永遠成立）|
| ROS 2 node 沒反應 | 沒呼叫 `spin`；callback 被阻塞 |

找卡在哪：在可疑位置前後加 print；Linux 用 `gdb` 附加後 Ctrl-C 看 `bt`；或 `gdb -p $(pidof prog)`。

### 2.5 結果錯誤

1. **對照 baseline**：`diff expected.txt actual.txt` 找到第一個不同的地方。
2. **縮小輸入**：用最小的輸入重現，手算正確答案。
3. **印中間值**：在資料流的每個階段印出來，找出第一個錯的階段。
4. 常見原因：

| 類別 | 例子 |
|---|---|
| 差一（off-by-one）| `<` vs `<=`、陣列長度、迴圈邊界 |
| 單位 | **DMA count 是「筆數」不是「位元組數」**；ms vs us；位元 vs 位元組 |
| 型別 | 有號 / 無號混用、整數提升（`uint8_t` 運算會提升成 `int`）、溢位、整數除法截斷 |
| 位元運算 | 運算子優先序（`a & b == c` 是 `a & (b == c)`）、右移有號數、位移量 ≥ 型別寬度是未定義行為 |
| 位元組順序 | endianness、DMA / PIO 的 shift 方向、bswap |
| 對齊 | 不對齊的 32 位元存取 |
| 資料競爭 | 多執行緒 / 多核心 / 中斷同時寫同一份資料 |
| 快取 / 時序 | 讀到 DMA 還沒寫完的資料（沒等完成就讀）|
| 輸出格式 | 多餘空白、換行、debug 訊息混入 stdout |

### 2.6 時好時壞（非決定性）

幾乎都是**並行問題**或**未初始化**：

- 多跑幾十次確認：`for i in $(seq 50); do ./prog; done | sort | uniq -c`
- 競爭條件：`gcc -g -fsanitize=thread -pthread prog.c`（ThreadSanitizer）
- 未初始化變數：`-Wall -Wextra` 看警告；`valgrind ./prog`（若有安裝）
- 嵌入式：中斷與主程式共用變數沒保護；DMA 還在跑就讀 buffer；兩顆核心同時存取。

### 2.7 效能比預期差

- 確認是 Release 建置、跟評分條件一致。
- 確認量測區段沒有包含 printf。
- 確認硬體卸載真的有在動（DMA 是否真的在跑？PIO 是否被 CPU 輪詢拖累？）。
- 多執行緒：鎖競爭、false sharing、執行緒數超過核心數。
- 見 `03-optimize.md`。

### 2.8 ROS 2 資料沒在傳

依序檢查（詳見 `domain/ros2.md`）：

```
ros2 node list           → node 有在跑嗎？
ros2 topic list          → topic 存在嗎？名稱完全一樣嗎（大小寫、斜線、namespace）？
ros2 node info /node     → 實際訂閱 / 發布了哪些 topic？
ros2 topic info /topic -v → 型別一致嗎？publisher / subscriber 數量對嗎？QoS 相容嗎？
ros2 topic echo /topic   → 真的有資料嗎？
ros2 topic hz /topic     → 頻率正常嗎？
ros2 topic pub --once ... → 手動送資料，單獨測試某個 node（Jazzy 預設會等到有相符 QoS 的 subscriber 才送；看起來卡住時加 `-w 0`）
```

### 2.9 開發板沒有輸出

| 檢查 | |
|---|---|
| 有呼叫 `stdio_init_all()` 嗎？ | |
| CMake 啟用了正確的 stdio 嗎？ | `pico_enable_stdio_usb(target 1)` 或 `pico_enable_stdio_uart(target 1)` |
| USB stdio：開機後太快印，主機還沒連上 | 開頭加 `sleep_ms(2000)` 或等待 `stdio_usb_connected()` |
| USB stdio：主機沒拉起 DTR、或主機停止讀取 500 ms | 輸出會被**靜默丟棄**；主機端要真的開著 port 在讀（詳見 `domain/host-mcu-comm.md`）|
| 二進位資料被改掉（多了 `\r`）| stdout 預設做 CRLF 轉換；送二進位用 `stdio_put_string(buf, len, false, false)` |
| 燒錄的是新版嗎？ | 確認 build 有成功、上傳的 .uf2 時間戳 |
| 程式是否在印之前就崩潰 / 卡住 | 用 LED 閃爍確認程式有在跑 |

### 2.10 容器 / 環境問題

| 症狀 | 處理 |
|---|---|
| `ros2: command not found` | `source /opt/ros/jazzy/setup.bash`（`docker exec` 開的 shell 不一定有自動 source）|
| 自己的 ROS 2 套件找不到 | `colcon build` 之後要 `source install/setup.bash` |
| `PICO_SDK_PATH` 未設定 | `echo $PICO_SDK_PATH`；看題目說明的路徑 |
| 權限不足 | 不要自己改系統設定；回報監考 |
| 改了但沒效果 | 確認重新編譯了、執行的是新的執行檔（`ls -la` 看時間）|

---

## 3. 除錯工具速查

### 3.1 gdb 常用指令

| 指令 | 作用 |
|---|---|
| `gdb ./prog` → `run [args]` | 執行 |
| `break file.c:42` / `break func` | 設中斷點 |
| `next` / `step` / `finish` / `continue` | 下一行 / 進入函式 / 跑完目前函式 / 繼續 |
| `print x` / `print *p@10` / `print/x v` | 印變數 / 印陣列 10 個元素 / 十六進位 |
| `bt` | 呼叫堆疊 |
| `info threads` / `thread N` | 多執行緒 |
| `watch x` | x 被修改時停下 |

### 3.2 printf 除錯技巧

```c
#define DBG(fmt, ...) fprintf(stderr, "[%s:%d] " fmt "\n", __FILE__, __LINE__, ##__VA_ARGS__)
DBG("i=%d val=0x%08x", i, val);
```

- 印到 **stderr**，不會污染評分用的 stdout。
- 提交前用 `grep -rn "DBG\|printf" src/` 找出並移除或關閉。
- 可用 `#ifdef DEBUG` 包起來，編譯時 `-DDEBUG` 才開。

### 3.3 git 救援

```bash
git status / git diff              # 改了什麼
git stash                          # 暫存目前修改，回到乾淨狀態測試
git stash pop                      # 拿回暫存的修改
git checkout -- file.c             # 放棄某檔案的修改
git log --oneline                  # 找能用的版本
git diff <好的commit> -- file.c    # 比較跟能用的版本差在哪
git bisect start / good / bad      # 二分法找出哪個 commit 引入 bug
```

---

## 4. 給模型的其他除錯提示

### 4.1 看不懂的錯誤訊息

```
這個錯誤訊息是什麼意思？最常見的 3 個原因是什麼？我該先檢查哪個？
環境：{{環境}}
{{貼錯誤訊息}}
```

### 4.2 設計實驗區分假設

```
我懷疑問題是 {{假設 A}} 或 {{假設 B}}。
請設計一個最小的實驗（加 print、改輸入、註解某段）來區分這兩個假設，
並說明每種結果分別代表什麼。
```

### 4.3 修好了但不知道為什麼

```
我把 {{改動}} 之後問題消失了，但我不確定根本原因。
請解釋為什麼這個改動能修好問題，以及它是否只是掩蓋了問題（例如時序剛好改變）。
```
