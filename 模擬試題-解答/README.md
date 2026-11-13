# 模擬試題 解答與講解

> 做完 `../模擬試題/` 再看。這裡只放「有改的檔案」，其他檔案和題目一樣。
> 套用解答：`for f in $(cd 模擬試題-解答 && find q1 q2-1 q2-2 q2-3 -type f); do cp 模擬試題-解答/$f 模擬試題/$f; done`
> （會覆蓋你的作答，先 commit 或 stash。）

驗證（2026-11-13，4 核 Linux，gcc 13.3，Python 3.13）：題目原樣 6/80，套用解答 80/80（2-1 需要 ROS 2，這台沒有，judge 跳過）。

---

## 第一大題（40 分）

| # | bug / 待辦 | 在哪 | 怎麼發現 | 修法 |
|---|---|---|---|---|
| 1 | seq 只有 1 byte，`seq = i` 到第 256 筆 `struct.pack` 就爆 | `host.py` | judge 訊息直接寫 `'B' format requires 0 <= number <= 255` | `i & 0xFF` |
| 2 | 韌體 `uint8_t len`，len ≥ 256 被截斷 → 讀錯長度 → CRC 錯 | `device_main.c` | **編譯警告** `comparison is always false due to limited range of data type`；或是 batch ≥ 16 筆就收到 `BAD_CRC` | 改成 `uint16_t` |
| 3 | `CALC_BATCH` 沒寫 | `device_main.c` | 看 TODO | 迴圈對每筆呼叫 `compute_record`，回 4k byte |
| 4 | `recv_frame` 用 `os.read(fd, length)` 讀 payload，可能只讀到一部分 | `proto.py` | 讀程式時發現 header 和 crc 都用 `read_exact`、只有 payload 沒有 | 改成 `read_exact` |
| 5 | 每筆一來一回 ~1 ms → 4000 筆要 5 秒 | 設計 | 算時間 | 批次：每 frame 64 筆（1024 byte 上限） |
| 6 | 只用 1 片板子 | 設計 | judge 給了 2 個 `--dev` | 資料切兩半，兩條執行緒各管一片 |

實測（大測資）：修好 1 → 5.3 秒；batch 15 筆（剛好躲過 bug 2）→ 0.86 秒；batch 64、1 片 → 0.60 秒；batch 64、2 片 → 0.32 秒。

注意：bug 4 在模擬的 pty 上**不一定會發生**（pty 通常一次就把整包交出來），但真的 USB 序列埠很常只回一部分。
這種 bug 不能靠「測過沒事」排除，要靠讀程式。

考場對應：
- 預製範本：`預製程式碼/ros2/frame.py`（同樣的 frame 結構）、`ros2/serial_bridge.py` 的批次模式、`ros2/multi_device.py`。
- 卡片：`cards/09-template-adapt.md` 範本 4/7（文字 → 二進位批次）、範本 5/7（拆給 N 片板子）；
  `cards/06-tools-debug.md` 工具 5/9（序列埠收到的資料不對）。

## 2-1（20 分）

| # | bug | 怎麼用 CLI 發現 | 修法 |
|---|---|---|---|
| 1 | filter 發布到 `/sensor/filterd`（拼錯） | `ros2 topic list` 同時看到 `/sensor/filterd` 和 `/sensor/filtered`；`ros2 topic info /sensor/filtered` → Publisher count: 0 | 改名 |
| 2 | QoS 不相容：sensor 是 best effort，filter 訂閱用預設（reliable） | `ros2 topic info -v /sensor/raw`：兩邊的 Reliability 一個 BEST_EFFORT、一個 RELIABLE；filter 的終端機也會印 `incompatible QoS` 警告 | 訂閱端改成 `qos_profile_sensor_data` |
| 3 | 移動平均的 list 一直變長（變成全部的平均） | `ros2 topic echo /sensor/filtered` 看值越來越平滑、跟手算的不一樣 | `deque(maxlen=4)` |
| 4 | timer 0.5 秒 = 2 Hz | `ros2 topic hz /sensor/raw` → 約 2.0 | 0.05 秒 |

規則記法：**publisher 給的 ≥ subscriber 要的** 才相容。reliable 的 publisher 可以配 best effort 的 subscriber，反過來不行。
（bug 1 修好之前看不到 bug 2 以後的現象：一次只修一個，每修一個就重新觀察一次。）

考場對應：`預製程式碼/ros2/README.md` 的 CLI 除錯清單、`cards/06-tools-debug.md` 工具 6/9、`cards/ros2.md` 參考卡。

## 2-2（20 分）

**A**：`parse_header` 有 3 個 bug：type 的 mask 少 1 bit（`0x0F` → `0x1F`）、seq 的高 4 bit 位移錯（`<< 4` → `<< 6`）、
CRC 讀成 big-endian（規格是 little-endian）。解答的寫法是先把 4 byte 接成一個大端 32-bit 數，再對每個欄位 `>> 位移 & mask`：
位移 = 這個欄位右邊所有欄位的寬度總和（flags 0、seq 2、len 12、type 24、ver 29）。這樣不用處理「欄位跨 byte」。

**B-1**：兩個設定都反了。`out_shift` 要 **right**（先出低位元 → 先出 bits 7..0）；`in_shift` 要 **left**
（shift right 時新資料從 ISR 高位元進來，8 bit 推出去時在 bits 31..24）。用 `--trace` 看 ISR 一眼就知道。

**B-2**：天真的 `out x, 12` / `in x, 12` 會錯，因為 **autopull 只在 OSR 用完時才補**：OSR 剩 8 bit 時 `out x, 12`
拿到的是 8 bit 資料 + 4 個 0，不會接到下一個 word。解法是每 3 個 word（8 個樣本）展開成 20 條指令，
跨 word 的 s2、s5 分兩次 out（低段到 y、高段到 x），再「先 in 高段、後 in 低段」（shift left）。20 cycle / 8 樣本 = 2.5。
另一種解法一次搬 1 bit（`unpack12_bitloop.pio`），正確但約 39 cycle / 樣本，只拿 3 分。

**C**：照手冊的圖。B 型最容易錯的是 imm[11] 在 insn[7]、imm[12] 在 insn[31]；J 型是 imm[11] 在 insn[20]、
imm[19:12] 原地不動。符號延伸用 `(int32_t)insn >> 31` 再左移到最高位。

考場對應：`預製程式碼/bits-riscv/bitops.h`、`packet_fields.c`、`rv32_encode_decode.c`；`cards/12-implement.md`
的位元欄位、PIO 解讀、RISC-V 卡；`cards/pio.md` 參考卡（shift 方向、autopull 門檻）。
**數字一律用工具算**（`pio_sim.py --trace`、寫個小 C 程式印出來），不要叫小模型算 bit。

## 2-3（20 分）

| # | bug | 現象 | 修法 |
|---|---|---|---|
| 1 | 每個封包都 `dma_claim_unused_channel`，從不 unclaim | 第 17 個封包 panic（16 個 channel 用完） | 開機 claim 一次（或用完 unclaim） |
| 2 | `transfer_count` 填 `p->len`（byte 數） | 修好 3 之後 `work_buf 後面的記憶體被寫壞了` | `p->len / 4` |
| 3 | 預設設定寫位址**不遞增** | 修好 1 之後結果錯（每筆都寫到 `work_buf[0]`） | `channel_config_set_write_increment(&c, true)` |
| 4 | core0 的 `ring.count++` 沒有拿鎖 | 結果偶爾錯；`make tsan` 直接指出 | count 的讀寫都在鎖裡 |
| 5 | core1 拿著鎖算 `process_block`（30 µs） | 修 4 時如果 core0 也拿著鎖收資料 → 比單核心還慢（實測 235 ms vs 單核 183 ms） | 鎖裡只做「取出 + DMA 搬走 + tail/count」，計算在鎖外 |

解答的時間約 92 ms（單核 182 ms 的 0.51 倍）。

為什麼 core0 的「ring 滿了就等」也要在鎖裡讀 count：不在鎖裡讀的話，core0 看到「有空格」和 core1「把那格搬走」之間
沒有先後保證（ThreadSanitizer 會報 race）。拿鎖讀 count，core1 放鎖之前做的事 core0 拿鎖之後一定看得到。

考場對應：`預製程式碼/pico/app_dma.c`（DMA 預設值、claim/unclaim）、`pico/app_multicore.c`、
`linux-perf/pipeline_template.c`；`cards/pico-dma.md`、`cards/multicore-sync.md` 參考卡 + `cards/11-ask-reference.md` 查詢 2/2
（用參考卡檢查我的程式：count 單位、write_increment、unclaim 都在卡上的陷阱清單裡）。

---

## 出題檔案

- `gen_vectors.py`：產生 `../模擬試題/judge/vectors.json`（隱藏測資、2-3 的正確答案、不能改的檔案的 sha256）。
  **改了任何受保護的檔案（含 judge 本身）都要重跑**，不然 judge 會說那個檔案被改過。
