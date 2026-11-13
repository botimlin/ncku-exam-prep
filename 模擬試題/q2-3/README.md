# 2-3：雙核心管線 + spinlock + DMA（20 分）

## 1. 情境

Pico 2（RP2350）有兩顆核心。學長的設計：

```text
core0：receive_packet() ──> ring（8 格的環狀緩衝區，spinlock 保護）──> core1：DMA 搬到 work_buf ──> process_block()
        約 30 µs / 個                                                                         約 30 µs / 個
```

3000 個封包。全部做完後 core1 用 multicore FIFO 通知 core0，core0 印出：

```text
RESULT packets=3000 bytes=<所有 payload 的 byte 數總和> xor=<所有 process_block 結果的 XOR>
TIME ms=<core0 開始收到 core1 通知為止的時間>
```

兩邊各 30 µs，如果真的同時跑，總時間應該接近 3000 × 30 µs = 90 ms；一顆核心依序做完大約 180 ms。

現在的狀況：一跑就 panic。學長說「我記得之前可以跑」。

沒有板子：`pico_sim/` 在電腦上模擬 pico-sdk 的 multicore、spinlock、DMA，**函式名稱、參數、預設值都和 pico-sdk 2.x 一樣**，
在這裡寫對的程式碼搬到真的 Pico 2 上也是對的。和真的硬體不一樣的地方，在 `pico_sim/pico_sim.h` 標了【模擬】。

## 2. 檔案

| 檔案 | 能不能改 |
|---|---|
| `main.c` | ✅ 任何地方都可以改（但不能拿掉 `check_guard()`，輸出格式不能變） |
| `work.c`、`work.h` | ❌ |
| `pico_sim/` | ❌ |

```bash
make run     # 編譯並執行
make tsan    # 用 ThreadSanitizer 編譯並執行：會指出兩顆核心同時碰、又沒有被保護的變數
```

## 3. 規格

- `packet_t.len` 的單位是 **byte**（64～256，一定是 4 的倍數）。
- `process_block(words, n_words)` 的第二個參數是 **word 數**。
- 每個封包都要經過 DMA 搬到 `work_buf` 再算（題目規定，不能直接對 ring 裡的 payload 算）。
- 結果要和封包的處理順序無關（XOR 本來就無關），但每個封包都要剛好處理一次。

## 4. 評分（`python3 judge.py q2-3`）

| 項目 | 分數 |
|---|---|
| 結果正確（連跑 5 次都要對） | 12 |
| `make tsan` 沒有 data race 警告 | 3 |
| 時間 ≤ 單核心依序做完的 0.85 倍 | 2 |
| 時間 ≤ 單核心依序做完的 0.65 倍 | 3 |

「單核心依序做完」是 judge 在同一台電腦上實際量的。電腦只有 1 顆 CPU 時效能分拿不到（兩個「核心」沒辦法真的同時跑）。

## 5. 提示

- 考前練習 `../../考試相關資訊/section2-3/` 的兩個 demo 講的就是這題的觀念：count 的單位、位址遞增、通道要歸還、鎖要抓短。
- panic 修好之後結果還是不對？`dma_channel_get_default_config` 的預設值是什麼（看 `pico_sim.h` 的註解，或 SDK 文件）？
- 結果「偶爾」不對？跑 `make tsan`。
- 修好 race 之後變慢了？看看鎖裡面做了哪些事。
