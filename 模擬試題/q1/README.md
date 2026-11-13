# 第一大題：電腦 ↔ Pico 的計算管線（40 分）

## 1. 情境

實驗室要對大量 16 byte 的資料做一種計算，這個計算**只有板子能算**（結果和板子的序號有關，電腦算不出來）。
學長寫好了兩邊的程式：

```text
in.bin ──> host.py ──USB 序列埠──> Pico 韌體（device_main.c）──> compute_record()
            電腦端     /dev/ttyACM0                                   約 100 µs / 筆
out.txt <──────────────────────────── 結果 ─────────────────────────┘
```

學長說「小資料跑過沒問題」。但 judge 用 4000 筆資料就掛了，而且就算不掛也慢得不能用。
你的任務：**讓它正確，然後讓它快**。judge 會插 **2 片**板子（給 2 個 `--dev`）。

沒有板子：`device_main.c` 編譯成電腦上的程式，透過虛擬序列埠（pty）跟 `host.py` 溝通，行為模仿真的 USB 序列埠，
包括「每一來一回大約 1 ms」的成本（見 `device/pico_shim.h`）。

## 2. 通訊協定（兩邊都要遵守）

每個 frame：

| 欄位 | 大小 | 說明 |
|---|---|---|
| SOF | 2 | 固定 `A5 5A` |
| cmd | 1 | 指令，見下表 |
| seq | 1 | 序號，回應會帶回同一個值 |
| len | 2 | payload 的長度（byte），**little-endian**，0～1024 |
| payload | len | |
| crc | 4 | `zlib.crc32(cmd seq len_lo len_hi payload)`，**little-endian** |

指令：

| cmd | 名稱 | 請求的 payload | 回應的 cmd | 回應的 payload |
|---|---|---|---|---|
| `0x01` | PING | 任意 | `0x81` | 原樣送回 |
| `0x10` | CALC_ONE | 1 筆資料（16 byte） | `0x90` | 結果（4 byte，little-endian） |
| `0x11` | CALC_BATCH | k 筆資料（16k byte，1 ≤ k ≤ 64） | `0x91` | k 個結果（4k byte，順序和輸入相同） |
| — | 錯誤 | — | `0xEE` | `[原本的 cmd, 錯誤碼]`，錯誤碼 1 = CRC 錯、2 = 長度錯、3 = 不認得的指令 |

- 裝置一次只處理一個 frame：收完一個、算完、回完，才收下一個。
- 收到 CRC 錯誤的 frame 要回錯誤，然後繼續找下一個 `A5 5A`。

## 3. 檔案

| 檔案 | 能不能改 | 說明 |
|---|---|---|
| `host/host.py` | ✅ | 電腦端主程式 |
| `host/proto.py` | ✅ | 電腦端的 frame 打包 / 解析 |
| `device/device_main.c` | ✅ | Pico 韌體：frame 解析、指令處理（`CALC_BATCH` 還沒寫） |
| `host/link.py` | ❌ | 打開序列埠 |
| `device/pico_shim.*` | ❌ | 模擬 pico-sdk 的 stdio_usb（含 USB 的時間成本） |
| `device/compute.*` | ❌ | 板子上的計算 |

`host.py` 的命令列（judge 就是這樣呼叫的，不能改）：

```bash
python3 host.py --input in.bin --output out.txt --dev /dev/pts/5 [--dev /dev/pts/6]
```

- `in.bin`：N 筆 16 byte 的資料直接接在一起。
- `out.txt`：N 行，第 i 行是第 i 筆的結果，8 位小寫十六進位（例：`0badc0de`）。

## 4. 自己跑

```bash
# 終端機 1：接上 2 片模擬板子（會先自動編譯 device/），印出兩個 /dev/pts/N
python3 tools/fake_link.py -n 2

# 終端機 2：產生測資、執行
head -c 64000 /dev/urandom > /tmp/in.bin            # 4000 筆
python3 q1/host/host.py --input /tmp/in.bin --output /tmp/out.txt --dev /dev/pts/5 --dev /dev/pts/6
```

改了 `device_main.c` 之後，要重開 `fake_link.py`（它會重新編譯）。
judge 用的板子序號和 `fake_link.py` 預設的不一樣，所以自己跑的結果不能拿來和 judge 比，只能拿來看「有沒有跑完、快不快」。

## 5. 評分（`python3 judge.py q1`）

| 項目 | 分數 |
|---|---|
| 小測資：37 筆、1 片板子，全部正確 | 6 |
| 大測資：4000 筆、2 片板子，全部正確 | 14 |
| 大測資 ≤ 2.5 秒 | 6 |
| 大測資 ≤ 0.75 秒 | 6 |
| 大測資 ≤ 0.45 秒 | 8 |

效能分要大測資正確才算。

## 6. 提示

- 先讓它**正確**，再讓它**快**。judge 印出來的錯誤訊息就是第一個線索。
- 編譯 `device/` 時有警告嗎？
- 算一下：4000 筆 × 每筆一來一回約 1 ms 是多少？一次送 64 筆呢？兩片板子同時算呢？
- 「小資料沒問題、大資料才出事」：想想有哪些欄位只有 1 byte。
