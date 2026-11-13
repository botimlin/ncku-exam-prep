# 2-2：位元欄位、PIO、RISC-V（20 分）

三個小題互相獨立，可以挑順序做。

| 小題 | 檔案（✅ 可以改） | 不要改 |
|---|---|---|
| A 封包標頭 | `packet.c` | `packet.h` |
| B PIO | `pio/unpack8.pio`、`pio/unpack12.pio` | `../tools/pio_sim.py` |
| C RISC-V | `rv_imm.c` | `rv_imm.h` |

自己測：`make test`（A、C 的公開測資）、`make pio`（跑 unpack8）。judge 的測資比公開測資多很多。

---

## A. 封包標頭（7 分）

6 byte 的標頭。前 4 byte 是一條**位元流**，從 `b[0]` 的最高位元（bit 7）開始依序排：

```text
 b[0]                 b[1]              b[2]                 b[3]
 7 6 5 4 3 2 1 0 | 7 6 5 4 3 2 1 0 | 7 6 5 4 3 2 1 0 | 7 6 5 4 3 2 1 0
 └ver┘└──type───┘ └────────── len (12) ────────┘└───── seq (10) ──────┘└fl┘
   3       5
```

| 欄位 | 寬度 | 說明 |
|---|---|---|
| ver | 3 | 版本，必須是 5 |
| type | 5 | |
| len | 12 | |
| seq | 10 | |
| flags | 2 | |

`b[4..5]` 是 `b[0..3]` 的 **CRC-16/CCITT-FALSE**，用 **little-endian** 存（`b[4]` 是低位元組）。`crc16_ccitt_false()` 已經寫好。

- `parse_header(b, &h)`：填好 h 的 5 個欄位。**先檢查 CRC**：不對回傳 `HDR_BAD_CRC`；CRC 對但 ver ≠ 5 回傳 `HDR_BAD_VER`；都對回傳 `HDR_OK`。
  回傳錯誤時，judge 不檢查欄位。
- `build_header(&h, out)`：反過來，填好 `out[0..5]`（含 CRC）。欄位值超過自己的寬度時只取低位元。

| 項目 | 分數 |
|---|---|
| parse_header 全部正確（94 組） | 4 |
| build_header 全部正確（42 組） | 3 |

## B. PIO（8 分）

PIO 程式用 `tools/pio_sim.py` 模擬（只模擬資料路徑：OSR / ISR / X / Y / FIFO，沒有 pin）：

```bash
python3 ../tools/pio_sim.py pio/unpack8.pio 0x44332211
python3 ../tools/pio_sim.py pio/unpack8.pio 0x44332211 --trace      # 每個 cycle 的暫存器
python3 ../tools/pio_sim.py --help                                   # 支援的指令和模型
```

設定寫在 `.pio` 檔最後的 `% c-sdk { ... %}` 區塊裡，跟真的專案一樣：

```c
sm_config_set_out_shift(&c, shift_right, autopull, pull_threshold);
sm_config_set_in_shift(&c,  shift_right, autopush, push_threshold);
```

**B-1 `unpack8.pio`（3 分）**：每個 TX word 拆成 4 個 byte，**低位元組先**（bits 7..0、15..8、23..16、31..24），
每個 byte 推成一個 RX word，值放在 bits 7..0、其他 bit 為 0。現在的程式能跑，但輸出不對。

**B-2 `unpack12.pio`（5 分）**：12-bit 樣本從 bit 0 開始緊密排成一條位元流，每 32 bit 切成一個 TX word
（8 個樣本 = 3 個 word，word 之間沒有空隙）。每個樣本推成一個 RX word，值放在 bits 11..0、其他 bit 為 0。

```text
word0 = s0 | s1 << 12 | (s2 & 0xFF) << 24
word1 = (s2 >> 8) | s3 << 4 | s4 << 16 | (s5 & 0xF) << 28
word2 = (s5 >> 4) | s6 << 8 | s7 << 20
```

| 項目 | 分數 |
|---|---|
| B-1 輸出正確 | 3 |
| B-2 輸出正確（488 個樣本） | 3 |
| B-2 平均每個樣本 ≤ 3 cycle | 2 |

## C. RISC-V 立即值（5 分）

RV32I 的指令格式見 RISC-V Unprivileged ISA 手冊「Base Instruction Formats」與「Immediate Encoding Variants」兩節。

- `imm_s` / `imm_b` / `imm_j`：從一條 32-bit 指令取出 S / B / J 型的立即值（有號數，符號延伸）。
  B 和 J 的立即值單位是 byte、bit 0 一定是 0。**不管 opcode 是什麼都照格式取**（judge 會丟任意 32-bit 值）。
- `enc_b(funct3, rs1, rs2, offset)`：組出 opcode = `0x63` 的 B 型指令。offset 是偶數，-4096～4094。

| 項目 | 分數 |
|---|---|
| imm_s、imm_b、imm_j 各 110 組 | 各 1 |
| enc_b 69 組 | 2 |

提示：`../../預製程式碼/bits-riscv/rv32_encode_decode.c` 有編碼 / 解碼函式可以參考（它的 `main` 只跑內建測試，
例：`0xfe059ce3` = `bne x11, x0, -8`）。這題練的是「照手冊的 bit 圖自己寫出來」，先自己寫再對。
