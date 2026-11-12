# 第 6 章　bits-riscv/：位元欄位、位元流、RISC-V 指令編碼與組合語言

> 本章對應的檔案：`預製程式碼/bits-riscv/` 全部 8 個（`bitops.h`、`packet_fields.c`、`bitstream.c`、`rv32_encode_decode.c`、`asm_examples.S`、`asm_test.c`、`rv32_asm_cheatsheet.md`、`README.md`）｜驗證狀態：✅ host gcc 13.3 全部 PASS、0 警告；✅ RISC-V（`riscv64-unknown-elf-gcc` 13.2 + picolibc 1.8.6 + `qemu-riscv32` 8.2.2）基本 ISA 版與 Zbb 版全部 PASS；✅ 機器碼和 GNU as / objdump 對過；⚠️ 沒有在 Pico 2 實機上跑過｜最後核對：2026-11-12（commit d102c17）

## 6.0 30 秒版：什麼時候打開這一章

- 題目出現 **「bit 31..24」「欄位」「打包 / 拆解」「header」「mask」「endian / 大端 / 小端」「重新排列位元」** → 6.3.1 `bitops.h` + 6.3.2 `packet_fields.c`，食譜 6.4.1。
- 題目出現 **「位元流」「固定寬度欄位」「跨 byte」「MSB-first / LSB-first」** → 6.3.3 `bitstream.c`，食譜 6.4.2、6.4.3。
- 題目出現 **「RISC-V」「opcode」「funct3」「立即值（imm）」「機器碼」「反組譯」「模擬器」** → 6.2.6～6.2.8 的格式圖，再看 6.3.4 `rv32_encode_decode.c`，食譜 6.4.5、6.4.6。
- 題目要你 **寫組合語言函式給 C 呼叫、inline asm、`cpop` / `clz`** → 6.3.5 `asm_examples.S`、6.3.6 `asm_test.c`、6.3.7 速查表，食譜 6.4.7。
- 最常改的 3 個地方：
  1. `packet_fields.c:15-22` 的 `*_SHIFT` / `*_W`（換成題目的欄位表）。
  2. `rv32_encode_decode.c:57` `disasm()` 和 `:81` `step()` 的 `switch`（加新指令）。
  3. `asm_examples.S`：複製最接近的函式改，宣告同步加到 `asm_test.c:8-14`。
- 位元題三條鐵律：**一律用 `uint32_t`**；**位移量必須在 0～31**（`1u << 32`、寬度 0 都是未定義行為，見 6.6）；**先手算 1～2 組答案寫成 `CHECK`，PASS 再交**。

## 6.1 檔案總表

| 檔案 | 行數 | 做什麼 | 什麼時候用 | 驗證狀態 |
|---|---|---|---|---|
| `bitops.h` | 95 | 位元工具巨集與 inline 函式：BIT、MASK、GET/SET_FIELD、sign_extend、popcount、clz/ctz、bswap、rotate、2 的次方、位元反轉 | 任何位元題，`#include "bitops.h"` 直接用 | ✅ 本章自寫測試 PASS（host、UBSan、rv32 qemu）；repo 內沒有測試檔（已知問題 8） |
| `packet_fields.c` | 111 | 依規格表把欄位打包成 32 位元 / 拆回來；bitfield 寫法；大小端讀寫；位元重排 | 封包 header、暫存器欄位、規格位元表 | ✅ host、rv32 qemu `ALL PASS` |
| `bitstream.c` | 113 | 從 byte 陣列逐位元讀寫欄位（MSB-first、LSB-first）；從 word 陣列取跨 word 欄位 | 位元流解析、欄位跨 byte / 跨 word | ✅ host、rv32 qemu `ALL PASS` |
| `rv32_encode_decode.c` | 151 | RV32I 六種格式的編碼器、立即值解碼、反組譯器（子集）、迷你模擬器 | 指令編碼 / 解碼、寫反組譯器或 CPU 模擬器 | ✅ host、rv32 qemu `ALL PASS`；期望值與 GNU as 一致 |
| `asm_examples.S` | 133 | 7 個可從 C 呼叫的 RV32 組語函式（加總、複製、取欄位、popcount 兩版、BNN 內積、回呼） | 寫組語函式、示範呼叫慣例 | ✅ qemu 基本 ISA / Zbb 兩版 PASS |
| `asm_test.c` | 86 | 測 `asm_examples.S`：每個組語函式和 C 參考版比對；inline asm 範例 | 改完組語後驗證 | ✅ 同上 |
| `rv32_asm_cheatsheet.md` | 99 | 暫存器 / ABI、偽指令、載入儲存、`.S` 寫法、inline asm、Hazard3 位元擴充、opcode/funct 表 | 只查不改 | ✅ 表 6 的 29 條指令本章重新組譯過 |
| `README.md` | 48 | 檔案 → 題型對照、位元題 SOP、編譯指令、驗證紀錄 | 第一次打開資料夾時 | ✅ 指令本章照做過；「另寫測試」不在 repo（已知問題 8） |

## 6.2 先懂這些概念

### 6.2.1 位元編號、十六進位、二進位

- **位元（bit）**：0 或 1。`uint32_t` 有 32 個位元。
- **位元編號**：最右邊是 bit 0（最低位，LSB = Least Significant Bit），最左邊是 bit 31（最高位，MSB）。`bitops.h:2` 就是這個規則。
- **十六進位 1 位 = 二進位 4 位**。把 hex 一位一位展開就是二進位：

```text
0xA5     = 1010 0101
0xB32A0BEE = 1011 0011 0010 1010 0000 1011 1110 1110
            bit31                                bit0
```

- 欄位寫成 `[hi:lo]`（例：`[23:12]`）代表 bit hi 到 bit lo，**包含兩端**，寬度 = hi − lo + 1。

### 6.2.2 mask 與 shift：所有位元題的基本動作

- **mask（遮罩）**：低 w 位全是 1 的數，`(1u << w) - 1`。w = 5 → `0b11111` = `0x1F`。
- **取出欄位 [hi:lo]**：先右移 lo 位讓欄位跑到最右邊，再 AND mask：`(x >> lo) & mask`。
- **放入欄位**：先把那幾位清成 0，再 OR 進去：`x = (x & ~(mask << lo)) | ((v & mask) << lo)`。`v & mask` 是防止 v 太大蓋到隔壁欄位。

```text
取出 x = 0xABCD 的 [11:8]：
  x            = 1010 1011 1100 1101
  x >> 8       = 0000 0000 1010 1011
  & 0xF (w=4)  = 0000 0000 0000 1011 = 0xB
放入 v = 0x3 到 0xFFFFFFFF 的 [11:8]：
  mask << 8    = 0000 ... 0000 1111 0000 0000
  x & ~(...)   = 1111 ... 1111 0000 1111 1111
  | (3 << 8)   = 1111 ... 1111 0011 1111 1111 = 0xFFFFF3FF
```

### 6.2.3 有號數與符號延伸

- **二補數（two's complement）**：電腦表示負數的方法。w 位的有號數，最高位（bit w−1）是符號位：1 = 負。12 位元的 `0xFFF` = −1，`0x800` = −2048，`0x7FF` = 2047。
- **符號延伸（sign extension）**：把「w 位寬的有號數」變成 32 位有號數。做法：把符號位複製到 bit w～31。RISC-V 的立即值（imm）全部要這樣處理。
- `bitops.h:30` `sign_extend()` 的做法：先左移讓符號位到 bit 31，再「有號右移」回來。gcc 對 `int32_t` 的右移是**算術右移**（補符號位），所以高位會填滿符號位。

```text
sign_extend(0x800, 12)：
  v            = 0000 0000 0000 0000 0000 1000 0000 0000
  v << 20      = 1000 0000 0000 0000 0000 0000 0000 0000
  (int32_t)>>20= 1111 1111 1111 1111 1111 1000 0000 0000 = -2048
```

### 6.2.4 C 的位移陷阱（未定義行為）

- **未定義行為（UB, undefined behavior）**：C 標準沒規定結果，編譯器怎麼做都算對。可能「剛好對」，換個最佳化等級就錯。
- 對 32 位元的數，**位移量 ≥ 32 或 < 0 都是 UB**：`1u << 32`、`x >> 32` 都不行。所以 `bitops.h:18` 的 `MASK(w)` 特判 w ≥ 32。
- 有號數左移溢位也是 UB（`1 << 31` 用 `int` 就是），所以一律寫 `1u`。
- x86 硬體只看位移量的低 5 位（`x << 32` 實際上變 `x << 0`）；RISC-V 的 `sll/srl/sra` 也只看 `rs2` 的低 5 位。本章在 qemu 上實測 `asm_get_field(x, 0, 32)` 回傳 `0x00000000`（mask = (1<<0)−1 = 0），見 6.3.5。

### 6.2.5 位元組順序（endian）

- **endian**：一個多位元組的數，在記憶體裡哪個 byte 放前面（位址小的地方）。
- **小端（little-endian）**：最低位的 byte 放在最前面。x86、RP2350（Cortex-M33 和 Hazard3 都是）都是小端。
- **大端（big-endian）**：最高位的 byte 放在最前面。網路協定（「network byte order」）和很多檔案格式用大端。

```text
uint32_t v = 0x12345678，放在位址 p：
             p+0  p+1  p+2  p+3
小端（host） 78   56   34   12      ← memcpy(&buf, &v, 4) 得到的就是這個
大端（網路） 12   34   56   78      ← store_be32(buf, v) 得到的就是這個
```

- **規則**：線上（序列埠、檔案、封包）的位元組順序由「規格」決定，和 CPU 無關。用 `packet_fields.c:66-70` 的 `load_be32 / store_be32 / load_le32 / store_le32` 逐 byte 組合，不管 CPU 是哪種 endian 都對。不要用 `*(uint32_t *)p` 或 `memcpy` 去讀線上的資料，那樣讀到的是「host 的順序」。
- endian 只管「byte 的順序」，不改變 byte 裡面 8 個位元的順序。位元在 byte 裡的順序是「位元流」的問題（6.2.9）。

### 6.2.6 RV32I 是什麼

- **RISC-V**：開放的指令集架構（ISA）。RP2350 有兩顆 Hazard3 RISC-V 核心（和兩顆 Cortex-M33 二選一開機）。
- **RV32I**：32 位元基本整數指令集。32 個暫存器 x0～x31（x0 永遠是 0），一個程式計數器 pc。每條指令固定 32 位元（開了 C 擴充才有 16 位元的壓縮指令）。
- 指令一定落在 6 種格式之一：R、I、S、B、U、J。**opcode（bit 6..0）決定是哪一類**；rd、rs1、rs2、funct3 在所有格式的位置固定，立即值被「拆開」塞進剩下的位置。

### 6.2.7 六種指令格式（bit 圖）

```text
 31        25 24    20 19    15 14  12 11          7 6      0
+------------+--------+--------+------+-------------+--------+
|   funct7   |  rs2   |  rs1   |funct3|     rd      | opcode |  R  add/sub/and/or/xor/sll/srl/sra/slt
+------------+--------+--------+------+-------------+--------+
|      imm[11:0]      |  rs1   |funct3|     rd      | opcode |  I  addi/andi/lw/lbu/jalr/slli...
+------------+--------+--------+------+-------------+--------+
| imm[11:5]  |  rs2   |  rs1   |funct3|  imm[4:0]   | opcode |  S  sw/sh/sb
+------------+--------+--------+------+-------------+--------+
|imm[12|10:5]|  rs2   |  rs1   |funct3| imm[4:1|11] | opcode |  B  beq/bne/blt/bge/bltu/bgeu
+------------+--------+--------+------+-------------+--------+
|              imm[31:12]              |     rd      | opcode |  U  lui/auipc
+--------------------------------------+-------------+--------+
|        imm[20|10:1|11|19:12]         |     rd      | opcode |  J  jal
+--------------------------------------+-------------+--------+
```

opcode（`rv32_encode_decode.c:20-21`、`rv32_asm_cheatsheet.md:97`）：

| 類別 | opcode（hex） | 二進位 | 格式 |
|---|---|---|---|
| LUI | 0x37 | 0110111 | U |
| AUIPC | 0x17 | 0010111 | U |
| JAL | 0x6F | 1101111 | J |
| JALR | 0x67 | 1100111 | I |
| BRANCH | 0x63 | 1100011 | B |
| LOAD | 0x03 | 0000011 | I |
| STORE | 0x23 | 0100011 | S |
| OP-IMM | 0x13 | 0010011 | I |
| OP | 0x33 | 0110011 | R |

funct3 / funct7（`rv32_asm_cheatsheet.md:98-99`）：

| 類別 | funct3 = 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 |
|---|---|---|---|---|---|---|---|---|
| OP / OP-IMM | add/sub/addi | sll/slli | slt/slti | sltu/sltiu | xor/xori | srl/sra/srli/srai | or/ori | and/andi |
| BRANCH | beq | bne | （無） | （無） | blt | bge | bltu | bgeu |
| LOAD | lb | lh | lw | （無） | lbu | lhu | （無） | （無） |
| STORE | sb | sh | sw | （無） | （無） | （無） | （無） | （無） |

- `sub`、`sra` 的 funct7 = `0x20`（`0100000`），其他 R 型是 0。
- `slli/srli/srai`：imm[4:0] 是位移量 shamt，`srai` 的 imm[11:5] = `0x20`（所以 `srai x5,x6,3` = `0x40335293`，GNU as 實測）。
- M 擴充（`mul` 等）也是 opcode `0x33`，但 funct7 = `0x01`。這點和 6.6 的已知限制有關。

### 6.2.8 立即值為什麼被打亂、怎麼編碼解碼

為什麼打亂：
- 所有格式的**符號位都在 bit 31**，硬體做符號延伸只要看同一條線。
- rs1、rs2、rd 永遠在同一位置，解碼器不用先知道格式就能先讀暫存器。
- B 和 J 的目標位址一定是 2 的倍數，所以 **imm[0] 不存**，多出一位給範圍：B 是 13 位（±4 KiB），J 是 21 位（±1 MiB）。

**B 型編碼一步一步：`beq x5, x6, +0x812`**（GNU as 實測 = `0x006289e3`）

```text
1. imm = 0x812 = 2066，寫成 13 位（bit12..bit0）：
     bit: 12 11 10 9 8 7 6 5 4 3 2 1 0
          0  1  0  0 0 0 0 0 1 0 0 1 0
2. 拆欄位：imm[12]=0  imm[11]=1  imm[10:5]=000000  imm[4:1]=1001  （imm[0]=0 丟掉）
3. 放位置：bit31 ← imm[12]，bit30..25 ← imm[10:5]，bit11..8 ← imm[4:1]，bit7 ← imm[11]
4. 其他欄位：rs2=x6=00110，rs1=x5=00101，funct3=000（beq），opcode=1100011
     31 | 30..25 | 24..20 | 19..15 | 14..12 | 11..8 | 7 | 6..0
     0  | 000000 | 00110  | 00101  |  000   | 1001  | 1 | 1100011
5. 每 4 位一組：0000 0000 0110 0010 1000 1001 1110 0011 = 0x006289E3
```

對應程式：`rv32_encode_decode.c:31-34` `enc_b()`：

```c
    return BITS(u, 12, 12) << 31 | BITS(u, 10, 5) << 25 | rs2 << 20 | rs1 << 15 | f3 << 12
         | BITS(u, 4, 1) << 8 | BITS(u, 11, 11) << 7 | op; }
```

負數也一樣，先把 imm 當 `uint32_t` 看（二補數）：`beq x1, x2, -24` → imm13 = `1111111101000` → imm[12]=1、imm[11]=1、imm[10:5]=111111、imm[4:1]=0100 → `0xfe2084e3`（`rv32_encode_decode.c:117`，GNU as 實測一致）。

**B 型解碼一步一步：`0xfe0598e3`**（這是 `asm_examples.S` 的 `bnez a1, 1b` 在 `-march=rv32i` 下的機器碼，objdump 實測，位址 0x18 跳回 0x8）

```text
1. 展開：1111 1110 0000 0101 1001 1000 1110 0011
2. 切欄位：
     bit31     = 1         → imm[12]
     bit30..25 = 111111    → imm[10:5]
     bit24..20 = 00000     → rs2 = x0
     bit19..15 = 01011     → rs1 = x11 (a1)
     bit14..12 = 001       → bne
     bit11..8  = 1000      → imm[4:1]
     bit7      = 1         → imm[11]
     bit6..0   = 1100011   → BRANCH
3. 拼回 13 位：imm[12] imm[11] imm[10:5] imm[4:1] 0 = 1 1 111111 1000 0 = 1111111110000
4. 符號延伸（bit12 = 1 → 負）：-16 → 目標 = 0x18 - 16 = 0x8
```

對應程式：`rv32_encode_decode.c:50-51` `imm_b()`：

```c
int imm_b(uint32_t x) { return sext(BITS(x, 31, 31) << 12 | BITS(x, 7, 7) << 11
                                      | BITS(x, 30, 25) << 5 | BITS(x, 11, 8) << 1, 13); }
```

**J 型編碼一步一步：`jal x1, +0x12344`**（GNU as 實測 = `0x344120ef`）

```text
1. imm = 0x12344，寫成 21 位：0 0001 0010 0011 0100 0100
     imm[20]=0  imm[19:12]=00010010  imm[11]=0  imm[10:1]=0110100010  （imm[0]=0 丟掉）
2. 放位置：bit31 ← imm[20]，bit30..21 ← imm[10:1]，bit20 ← imm[11]，bit19..12 ← imm[19:12]
3. rd = x1 = 00001，opcode = 1101111
     31 | 30..21     | 20 | 19..12   | 11..7 | 6..0
     0  | 0110100010 | 0  | 00010010 | 00001 | 1101111
4. 每 4 位一組：0011 0100 0100 0001 0010 0000 1110 1111 = 0x344120EF
```

對應程式：`rv32_encode_decode.c:36-39` `enc_j()`。

**J 型解碼一步一步：`0xffdff06f`**（`jal x0, -4`，`rv32_encode_decode.c:120`）

```text
1. 展開：1111 1111 1101 1111 1111 0000 0110 1111
2. bit31 = 1 → imm[20]；bit30..21 = 1111111110 → imm[10:1]；bit20 = 1 → imm[11]
   bit19..12 = 11111111 → imm[19:12]；bit11..7 = 00000 → rd = x0；opcode = 1101111
3. 拼回 21 位：imm[20] imm[19:12] imm[11] imm[10:1] 0 = 1 11111111 1 1111111110 0
4. 符號延伸：全 1 只有最低兩位 00 → -4
```

對應程式：`rv32_encode_decode.c:53-54` `imm_j()`。

**S 型**：imm[11:5] 放 bit31..25、imm[4:0] 放 bit11..7（沒有打亂順序，只是拆兩段）。`sw x5, -12(x2)`：−12 = `111111110100` → `1111111 00101 00010 010 10100 0100011` = `0xfe512a23`。

**U 型**：imm[31:12] 直接放 bit31..12。`lui` 把 20 位放到暫存器的高 20 位（低 12 位是 0）。`li` 一個 32 位常數會拆成 `lui + addi`，而且因為 `addi` 的 imm 是**有號**的，低 12 位 ≥ 0x800 時高 20 位要 +1。GNU as 實測：

```text
li x5, 0x12345678 → lui x5,0x12345 ; addi x5,x5,1656      (0x678 = 1656)
li x6, 0x12345fff → lui x6,0x12346 ; addi x6,x6,-1        (0x12346000 - 1)
```

### 6.2.9 位元流的兩種順序

- **位元流（bit stream）**：一串位元，欄位一個接一個，**不對齊 byte**。一個 7 位的欄位可能一半在 byte 0、一半在 byte 1。
- **MSB-first**：每個 byte 先用 bit7；欄位也是高位先出。網路協定、影像格式常用。
- **LSB-first**：每個 byte 先用 bit0；欄位低位先出。deflate/zip、很多 UART / 硬體 FIFO。
- 圖解見 6.3.3。

### 6.2.10 呼叫慣例（ABI）一頁版

- **ABI**：大家約好「參數放哪、回傳值放哪、哪些暫存器呼叫後還要在」。C 和組語要互相呼叫，就要照它（`rv32_asm_cheatsheet.md:3-17`）。

| 暫存器 | ABI 名 | 用途 | 呼叫別人之後還在嗎 |
|---|---|---|---|
| x0 | zero | 永遠 0 | — |
| x1 | ra | 回傳位址（`call`/`jal` 寫它） | 不保證（要用就自己存） |
| x2 | sp | 堆疊指標，16 byte 對齊 | 會 |
| x5-7, x28-31 | t0-t6 | 暫時用 | 不會（caller-saved） |
| x8-9, x18-27 | s0-s11 | 長期變數 | 會（callee-saved：你用了要先存後還） |
| x10-11 | a0-a1 | 參數 1-2、回傳值 | 不會 |
| x12-17 | a2-a7 | 參數 3-8 | 不會 |

- 葉函式（不呼叫別人）：只用 a、t 暫存器，不用開堆疊。例：`asm_sum_u32`。
- 會呼叫別人：開堆疊、存 `ra` 和用到的 `s` 暫存器。例：`asm_apply`（6.3.5）。

### 6.2.11 Hazard3 的擴充與 `-march`

- **`-march`**：告訴 gcc 可以用哪些指令。字串 = 基本 ISA + 擴充。`rv32imac_zicsr_zifencei_zba_zbb_zbs_zbkb`：
  - `i` 基本整數、`m` 乘除、`a` 原子操作、`c` 16 位元壓縮指令、`zicsr` CSR 指令、`zifencei` 指令快取同步。
  - `zba` 位址計算（`sh1add/sh2add/sh3add`）、`zbb` 基本位元操作（`cpop/clz/ctz/rev8/andn/xnor/min/max/rol/ror`…）、`zbs` 單一位元（`bset/bclr/binv/bext`）、`zbkb` 密碼學用位元操作（`pack/packh/brev8/zip/unzip`）。
- **`-mabi=ilp32`**：int、long、指標都是 32 位，沒有硬體浮點暫存器。
- Hazard3 另外有 Zcb、Zcmp（更多壓縮指令），沒有 Zbc（**沒有 `clmul`**）。SDK 2.3.x 的 `-march` 第二候選是 `rv32ima_zicsr_zifencei_zba_zbb_zbs_zbkb_zca_zcb_zcmp`（`$S/sdk/pico_riscv_gcc.cmake:13`），和這個清單一致。速查表寫的出處「RP2350 datasheet 3.8 節」本章沒有對照 datasheet 原文，⚠️未驗證節號。

## 6.3 逐檔說明

### 6.3.1 `bitops.h`

#### 用途

位元操作工具箱。純標頭檔，只依賴 `<stdint.h>`，電腦、ARM、RISC-V 都能用。所有巨集和函式都用 `uint32_t`，位元編號 bit 0 = LSB（`bitops.h:1-3`）。

#### 怎麼編譯 / 執行

沒有 `main`，要被別的檔 `#include`。repo 裡**沒有**它的測試檔（README 說的「另寫測試」不在 repo，已知問題 8）。本章寫了一份 `bitops_selftest.c`，原文如下，考場可以照打：

```c
// bitops_selftest.c — 補 README 說的「另寫測試」（repo 裡沒有這個檔）
#include <stdio.h>
#include "bitops.h"
static int fails = 0;
#define CHECK(got, exp) do { long long g_ = (long long)(got), e_ = (long long)(exp); \
    if (g_ != e_) { printf("FAIL line %d: got %lld exp %lld\n", __LINE__, g_, e_); fails++; } } while (0)
int main(void) {
    CHECK(BIT(3), 0x8);               CHECK(SET_BIT(0xA5u, 1), 0xA7);
    CHECK(CLR_BIT(0xA5u, 0), 0xA4);   CHECK(TOGGLE_BIT(0xA5u, 7), 0x25);
    CHECK(TEST_BIT(0xA5u, 7), 1);     CHECK(MASK(5), 0x1F);
    CHECK(MASK(32), 0xFFFFFFFFu);     CHECK(GET_FIELD(0xABCDu, 11, 8), 0xB);
    CHECK(GET_FIELD(0xDEADBEEFu, 31, 0), 0xDEADBEEFu);
    CHECK(SET_FIELD(0xFFFFFFFFu, 11, 8, 0x3), 0xFFFFF3FFu);
    CHECK(SET_FIELD(0u, 7, 4, 0x1F), 0xF0);            // 超出寬度的位元被丟掉
    CHECK(COMBINE16(0x12, 0x34), 0x1234);
    CHECK(sign_extend(0xFFF, 12), -1);  CHECK(sign_extend(0x800, 12), -2048);
    CHECK(sign_extend(0x7FF, 12), 2047); CHECK(sign_extend(0x1FFF, 12), -1); // 高位髒也沒關係
    CHECK(popcount32(0xF0F0), 8);     CHECK(POPCOUNT(0xFFFFFFFFu), 32);
    CHECK(clz32(0x10), 27);  CHECK(ctz32(0x10), 4);  CHECK(clz32(0), 32);  CHECK(ctz32(0), 32);
    CHECK(bswap32(0x11223344u), 0x44332211u);  CHECK(bswap16(0x1234), 0x3412);
    CHECK(rotl32(0x80000001u, 1), 0x3);  CHECK(rotr32(0x80000001u, 1), 0xC0000000u);
    CHECK(rotl32(0x12345678u, 36), 0x23456781u);       // 36 & 31 = 4
    CHECK(is_pow2(0), 0);  CHECK(is_pow2(8), 1);  CHECK(is_pow2(12), 0);
    CHECK(round_up_pow2(5), 8);  CHECK(round_up_pow2(8), 8);  CHECK(round_up_pow2(0), 0);
    CHECK(ALIGN_UP(13, 4), 16);  CHECK(ALIGN_UP(16, 4), 16);
    CHECK(bitrev32(1), 0x80000000u);  CHECK(bitrev32(0x12345678u), 0x1E6A2C48u);
    CHECK(bitrev_n(0x3, 4), 0xC);     CHECK(bitrev_n(0x6, 3), 0x3);
    CHECK(brev8(0x01020380u), 0x8040C001u);
    if (fails == 0) printf("bitops: ALL PASS\n");
    return fails != 0;
}
```

在 `預製程式碼/bits-riscv/` 的上一層找個暫存資料夾放這個檔，然後：

```sh
gcc -O2 -Wall -Wextra -I<bits-riscv 的路徑> bitops_selftest.c -o bt && ./bt
# 預期：bitops: ALL PASS
```

#### 對外介面

單一位元（`bitops.h:9-13`）：

| 名稱 | 參數 | 回傳 / 效果 | 注意 |
|---|---|---|---|
| `BIT(n)` | n：0～31 | `1u << n` | n ≥ 32 是 UB；`BIT(31)` 沒問題（用 `1u`） |
| `SET_BIT(x, n)` | x、n | `x \| BIT(n)` | **回傳新值，不會改 x**：要寫 `x = SET_BIT(x, 5);` |
| `CLR_BIT(x, n)` | x、n | `x & ~BIT(n)` | 同上 |
| `TOGGLE_BIT(x, n)` | x、n | `x ^ BIT(n)` | 同上 |
| `TEST_BIT(x, n)` | x、n | `(x >> n) & 1u`，0 或 1 | n ≥ 32 是 UB |

多位元欄位（`bitops.h:18-25`）：

| 名稱 | 參數 | 回傳 / 效果 | 注意 |
|---|---|---|---|
| `MASK(w)` | w：寬度 | 低 w 位全 1；w ≥ 32 → `0xFFFFFFFF` | w = 0 → 0（正確）；w < 0 是 UB；參數會被算兩次，不要放 `i++` |
| `GET_FIELD(x, hi, lo)` | hi ≥ lo，0～31 | x 的 [hi:lo]，已右移到最低位 | hi < lo → 寬度 ≤ 0 → MASK 負數 UB；lo = 32 是 UB |
| `SET_FIELD(x, hi, lo, v)` | 同上，v 新值 | 清空 [hi:lo] 後放入 `v & MASK`，回傳新值 | v 超出寬度的位元被丟掉：`SET_FIELD(0,7,4,0x1F)` = `0xF0`（實測） |
| `COMBINE16(a, b)` | 兩個 byte | `(a & 0xFF) << 8 \| (b & 0xFF)` | 自動 mask：`COMBINE16(0x1FF, 0x2AB)` = `0xFFAB`（實測） |

符號延伸、popcount、clz/ctz（`bitops.h:30-49`）：

| 名稱 | 參數 | 回傳 / 效果 | 注意 |
|---|---|---|---|
| `sign_extend(v, bits)` | v：原始位元；bits：1～32 | 32 位有號數 | v 高於 bits 的位元會被左移推掉，不用先 mask；**bits = 0 → 位移 32，UB（已知問題 7）**；bits > 32 → 位移量負數，UB |
| `popcount32(x)` | x | 1 的個數（0～32） | 可攜版，迴圈次數 = 1 的個數 |
| `POPCOUNT(x)` | x | `__builtin_popcount(x)` | gcc/clang 才有；Hazard3 `-march` 下編成一條 `cpop`（實測） |
| `clz32(x)` | x | 前導 0 個數；x = 0 → 32 | `__builtin_clz(0)` 是 UB，所以先判斷；Zbb 下整個函式編成一條 `clz`（實測，因為硬體 `clz(0)` = 32） |
| `ctz32(x)` | x | 尾端 0 個數；x = 0 → 32 | 同上，Zbb 下一條 `ctz` |
| （註解）`31 - clz32(x)` | x | 最高的 1 在第幾位（log2 取整） | x = 0 → −1（`bitops.h:49`） |

endian、rotate、2 的次方（`bitops.h:53-72`）：

| 名稱 | 參數 | 回傳 / 效果 | 注意 |
|---|---|---|---|
| `bswap32(x)` | x | byte 順序顛倒：`0x11223344` → `0x44332211` | Zbb 下編成一條 `rev8`（實測） |
| `bswap16(x)` | 16 位 | `0x1234` → `0x3412` | |
| `rotl32(x, n)` / `rotr32(x, n)` | n 任意整數 | 循環左移 / 右移 | 先 `n &= 31`，所以 n = 36 等於 4、n = −4 等於 28（實測 `rotl32(0x12345678,-4)` = `0x81234567`）；n = 0 特判避免 `>> 32`；Zbb 下編成 `andi + rol` |
| `is_pow2(x)` | x | 是 2 的次方回 1 | 0 → 0 |
| `round_up_pow2(x)` | x | 往上取到 2 的次方；0 → 0 | x > 0x80000000 會溢位成 0（實測 `0x80000001` → 0） |
| `ALIGN_UP(x, a)` | a 必須是 2 的次方 | 對齊到 a 的倍數 | a 不是 2 的次方會算錯：`ALIGN_UP(13, 6)` = 18（實測，正確答案應該是 18？不是，13 往上對齊 6 是 18，碰巧對；`ALIGN_UP(7, 6)` = 7 & ~5 系列一般不對）→ 一律只用 2 的次方 |

位元反轉（`bitops.h:76-85`）：

| 名稱 | 參數 | 回傳 / 效果 | 注意 |
|---|---|---|---|
| `bitrev32(x)` | x | 32 位左右顛倒：`0x1` → `0x80000000`、`0x12345678` → `0x1E6A2C48` | 先相鄰 1、2、4 位互換，最後 `bswap32` |
| `bitrev_n(x, n)` | n：1～32 | 只反轉低 n 位：`bitrev_n(0b0011, 4)` = `0b1100` | x 高於 n 的位元不影響結果（實測 `bitrev_n(0xFF03, 4)` = `0xC`）；**n = 0 → 位移 32，UB（已知問題 7）** |
| `brev8(x)` | x | 每個 byte 內部反轉、byte 順序不變：`0x01020380` → `0x8040C001` | 等於 Zbkb 的 `brev8`；但 gcc 不會自動認出，C 版編成約 30 條指令；要一條指令請用 `__builtin_riscv_brev8(x)`（本章實測可用，編成 `brev8 a0,a0`） |

小技巧速查（`bitops.h:87-94`，只是註解）：`x & -x` 只留最低的 1（`0b10110` → `0b00010`，實測）、`x & (x-1)` 清掉最低的 1、`popcount(a ^ b)` 是漢明距離、`~(a ^ b)` 是 XNOR。

> 更正上表 `ALIGN_UP` 那一列：不要拿非 2 的次方去試，結果沒有保證。`ALIGN_UP(13, 6)` 實測輸出 18，只是碰巧；公式 `(x + a-1) & ~(a-1)` 只有在 a-1 是「低位全 1」時才代表「清掉低位」。

#### 程式流程

沒有流程，每個都是獨立的巨集或 `static inline` 函式。需要注意的實作細節：

1. `sign_extend`（`bitops.h:30-33`）：`sh = 32 - bits`；`(int32_t)(v << sh) >> sh`。依賴「gcc 對有號數右移是算術右移」（gcc 文件保證；C 標準說是 implementation-defined）。`bitops.h:34` 的註解給了完全可攜的寫法 `(v ^ m) - m`（v 要先 mask）。
2. `popcount32`（`bitops.h:37-41`）：`x &= x - 1` 每次清掉最低的 1，計數。
3. `round_up_pow2`（`bitops.h:65-70`）：先減 1，再把最高的 1 往右填滿（`x |= x >> 1 … >> 16`），最後 +1。
4. `bitrev32`（`bitops.h:76-81`）：分治法，3 次交換 + `bswap32`，沒有迴圈。

#### 要改的地方

沒有 `TODO(改這裡)`，直接用。

#### 實際執行輸出

環境：host gcc 13.3、x86_64、4 核；本章自寫 `bitops_selftest.c`。

```text
$ gcc -O2 -Wall -Wextra -I.../bits-riscv bitops_selftest.c -o bst && ./bst
bitops: ALL PASS
$ gcc -O1 -fsanitize=undefined ... && ./bstu          # UBSan 也沒有報錯
bitops: ALL PASS
$ riscv64-unknown-elf-gcc -march=rv32imac_zicsr_zifencei_zba_zbb_zbs_zbkb -mabi=ilp32 -O2 \
    --specs=picolibc.specs -nostartfiles bitops_selftest.c linux_shim.c -o bst.elf && qemu-riscv32 ./bst.elf
bitops: ALL PASS
```

二進位對照（本章另一支印出程式，節錄）：

```text
SET_FIELD(0xFFFFFFFF,11,8,0x3)     = 0xFFFFF3FF  1111_1111_1111_1111_1111_0011_1111_1111
GET_FIELD(0xABCD,11,8)             = 0x0000000B  0000_0000_0000_0000_0000_0000_0000_1011
bswap32(0x11223344)                = 0x44332211  0100_0100_0011_0011_0010_0010_0001_0001
bitrev32(0x12345678)               = 0x1E6A2C48  0001_1110_0110_1010_0010_1100_0100_1000
brev8(0x01020380)                  = 0x8040C001  1000_0000_0100_0000_1100_0000_0000_0001
clz32(0x10)=27 ctz32(0x10)=4 clz32(0)=32 ctz32(0)=32 clz32(1)=31 ctz32(0x80000000)=31
```

寬度 0 的 UB（已知問題 7）用 UBSan 實測（位移量用執行期變數，編譯器不能事先算掉）：

```text
bitops.h:32:24: runtime error: shift exponent 32 is too large for 32-bit type 'unsigned int'
bitops.h:32:31: runtime error: shift exponent 32 is too large for 32-bit type 'int'
bitops.h:83:73: runtime error: shift exponent 32 is too large for 32-bit type 'unsigned int'
[UB] sign_extend(5, 0) = 5
[UB] bitrev_n(5, 0)                = 0xA0000000
```

`-O2` 不開 UBSan 時，x86 上 `sign_extend(5,0)` 回傳 5、`bitrev_n(5,0)` 回傳 `0xA0000000`（等於沒位移），**不是 0**。換平台或最佳化可能又不一樣。

#### 常見錯誤

| 症狀 | 原因 | 修法 |
|---|---|---|
| `SET_BIT(x, 3);` 之後 x 沒變 | 巨集回傳新值，不改參數 | `x = SET_BIT(x, 3);` |
| 寬度 32 的欄位取出來是 0 或亂碼 | 自己寫 `(1u << 32) - 1` | 用 `MASK(32)`（有特判）或直接 `0xFFFFFFFFu` |
| `sign_extend(v, 0)`、`bitrev_n(x, 0)` 結果不對 | 寬度 0 → 位移 32（UB） | 呼叫前判斷寬度 ≥ 1；寬度 0 的欄位直接當 0 |
| `GET_FIELD(x, lo, hi)` 結果怪 | hi、lo 順序反了 | 順序是 `(x, hi, lo)`，高位在前 |
| `clz32` 在 x = 0 時回傳 32，`31 - clz32(0)` = −1 | 0 沒有最高位 | 先判斷 x ≠ 0 |
| 在 `int` 上用 `BIT(31)` 比較得到負數 | `int` 和 `unsigned` 混用 | 變數一律宣告 `uint32_t` |
| `brev8()` 很慢 | gcc 13 不會把 C 版認成 `brev8` 指令 | RISC-V + Zbkb：`__builtin_riscv_brev8(x)` 或 inline asm |

### 6.3.2 `packet_fields.c`

#### 用途

示範「題目給一張位元表 → 寫出打包 / 拆解程式」的完整做法（`packet_fields.c:1-3`）。也示範為什麼**不要用 C bitfield**、大小端怎麼讀寫、怎麼照規格重新排列位元。

#### 怎麼編譯 / 執行

在 `預製程式碼/bits-riscv/`：

```sh
gcc -O2 -Wall -Wextra packet_fields.c -o /tmp/pf && /tmp/pf
```

預期最後一行 `packet_fields: ALL PASS`，回傳值 0。

#### 對外介面

| 名稱 | 參數 | 回傳 / 效果 | 注意 |
|---|---|---|---|
| `VER_SHIFT`…`ID_W`（`:15-22`） | — | 每個欄位的最低位位置與寬度 | `TODO(改這裡)` |
| `M(w)`（`:23`） | w < 32 | `(1u << w) - 1` | **w = 32 是 UB**（和 `bitops.h` 的 `MASK` 不同，沒有特判） |
| `Header`（`:25`） | — | `{ver, type, len, id}` 各用 `uint32_t` | 欄位改名要一起改 |
| `pack(Header h)`（`:28-33`） | h | 32 位元封包 | 每個欄位先 `& M(W)` 再左移，超寬的值被截掉（`pack({9,0,0,0})` = `1u<<29`，`:92`） |
| `unpack(uint32_t x)`（`:34-41`） | x | `Header` | 右移再 mask |
| `set_type(x, t)`（`:43-47`） | x、新的 type | 只改 type，其他不動 | 範例「改一個欄位」的寫法 |
| `HeaderBF`（`:53-61`） | — | `union { raw; struct bitfield }` | gcc 小端「第一個成員放最低位」，所以倒著寫；**考試不建議** |
| `load_be32(p)` / `load_le32(p)`（`:66-67`） | `const uint8_t *p` | 大端 / 小端讀 4 byte | 逐 byte 組合，不需要對齊、不管 host endian |
| `load_be16(p)`（`:68`） | p | 大端讀 2 byte | |
| `store_be32(p, v)` / `store_le32(p, v)`（`:69-70`） | p、v | 大端 / 小端寫 4 byte | |
| `permute_bits(x, perm, n)`（`:73-78`） | perm[i] = 第 i 位要搬到哪 | 重排後的值 | 方向是「來源 i → 目的 perm[i]」；規格如果寫「輸出第 j 位來自輸入第 src[j] 位」，要反過來寫（食譜 6.4.4） |

#### 程式流程

1. `main`（`:83`）建立 `Header h = {5, 0x13, 0x2A0, 0xBEE}`（`:84`），`pack` 後印出並檢查 `0xB32A0BEE`（`:85-88`）。註解 `:86` 有手算過程：`101 | 10011 | 0010 1010 0000 | 1011 1110 1110` 重新每 4 位分組 = `B32A0BEE`。
2. `unpack` 回來比對每個欄位（`:89-90`）；`set_type` 只改 type（`:91`）；超寬值被 mask（`:92`）。
3. bitfield 版本填同樣的值，`raw` 應該等於 `pack` 的結果（`:94-97`）。
4. endian：`{0x12,0x34,0x56,0x78}` 大端讀 = `0x12345678`、小端讀 = `0x78563412`（`:99-104`）。
5. `permute_bits` 用 `{3,2,1,0}` 把 4 位左右顛倒：`0x3` → `0xC`（`:106-107`）。
6. 全部通過印 `ALL PASS`（`:109`）。

**規格表 → 程式碼的對照**（以檔案內的假想規格 `:5-9` 為例）：

```text
規格表                         程式碼
bit 31..29  version (3 bits)  →  #define VER_SHIFT 29   #define VER_W 3
bit 28..24  type    (5 bits)  →  #define TYPE_SHIFT 24  #define TYPE_W 5
bit 23..12  length  (12 bits) →  #define LEN_SHIFT 12   #define LEN_W 12
bit 11..0   id      (12 bits) →  #define ID_SHIFT 0     #define ID_W 12
規則：SHIFT = 欄位的 lo；W = hi - lo + 1；所有 W 加起來要 = 32（或你的總寬度）
```

```text
 31 29 28   24 23            12 11             0
+-----+-------+----------------+----------------+
| ver | type  |     length     |       id       |
+-----+-------+----------------+----------------+
 101   10011   0010 1010 0000   1011 1110 1110     ← h = {5, 0x13, 0x2A0, 0xBEE}
```

**host 順序 vs 網路順序**：`pack()` 得到的是一個「數」（`0xB32A0BEE`），還沒有 byte 順序。要送上線時：
- 規格說大端 → `store_be32(buf, x)` → `B3 2A 0B EE`。
- 規格說小端 → `store_le32(buf, x)` → `EE 0B 2A B3`。
- 直接 `memcpy(buf, &x, 4)` 在 RP2350 / x86 上得到的是小端，等於 `store_le32`；但寫成 `store_le32` 才看得出意圖，也不怕換平台。

#### 要改的地方

| 行號 | 現在的值 | 意思 | 什麼情況要改、改成什麼 |
|---|---|---|---|
| `packet_fields.c:5` | `// 假想規格（TODO(改這裡)：換成題目給的表格）：`（`:6-9` 四個欄位） | 註解裡的規格表 | 把題目的表抄進來，方便對照 |
| `packet_fields.c:14` | `// TODO(改這裡)：每個欄位的 SHIFT（最低位位置）與 WIDTH（寬度）` | 下面 `:15-22` 的 8 個 `#define` | 每個欄位一對 `X_SHIFT`（= lo）、`X_W`（= hi−lo+1）；欄位數不同就同時改 `Header`（`:25`）、`pack`（`:28-33`）、`unpack`（`:34-41`）、`main` 的測試值 |
| `packet_fields.c:23` | `#define M(w) ((1u << (w)) - 1u)` | 遮罩 | 有 32 位寬的欄位時改成 `((w) >= 32 ? 0xFFFFFFFFu : ((1u << (w)) - 1u))`，或改用 `bitops.h` 的 `MASK` |

#### 實際執行輸出

環境：host gcc 13.3、x86_64。

```text
$ gcc -O2 -Wall -Wextra packet_fields.c -o pf && ./pf
pack = 0xB32A0BEE
bitfield = 0xB32A0BEE (gcc 小端應該一樣)
packet_fields: ALL PASS
```

rv32（gcc 13.2 + picolibc + qemu-riscv32，基本 ISA 與 Zbb 兩種 `-march`）：最後一行同樣是 `packet_fields: ALL PASS`。

#### 常見錯誤

| 症狀 | 原因 | 修法 |
|---|---|---|
| 某欄位值跑到隔壁欄位 | 沒有先 `& M(W)` 就左移 | 照 `pack()` 的寫法，每個欄位都 `(v & M(W)) << SHIFT` |
| 拆出來的值整個錯位 | SHIFT 填成 hi 而不是 lo | SHIFT = 欄位最低位（右邊那個數） |
| 線上收到的 byte 順序反了 | 用 `memcpy` 或 `*(uint32_t*)` 讀大端資料 | 用 `load_be32 / store_be32` |
| bitfield 版本和 pack 結果不同 | bitfield 排列由編譯器決定；換編譯器、大端機、或欄位跨越儲存單位就會變 | 考試用 shift + mask，不要用 bitfield |
| `-Wall` 下 printf 警告 `%X` 對 `uint32_t` | RISC-V 上 `uint32_t` 是 `unsigned long` | 印之前轉 `(unsigned)`（`:87` 已經這樣做） |
| 32 位寬欄位出錯 | `M(32)` 是 UB | 見「要改的地方」第 3 列 |

### 6.3.3 `bitstream.c`

#### 用途

從 byte 陣列「一個位元一個位元」讀 / 寫固定寬度的欄位，兩種順序都有；另有從 `uint32_t` 陣列取跨 word 欄位（`bitstream.c:1-5`）。一次處理 1 位最好懂，而且自動處理跨 byte、跨 word。

#### 怎麼編譯 / 執行

在 `預製程式碼/bits-riscv/`：

```sh
gcc -O2 -Wall -Wextra bitstream.c -o /tmp/bs && /tmp/bs
```

預期 `bitstream: ALL PASS`。

#### 對外介面

| 名稱 | 參數 | 回傳 / 效果 | 注意 |
|---|---|---|---|
| `BitStream`（`:11-14`） | `buf`、`pos` | 讀寫狀態 | **pos 是位元位置，不是 byte**；初始化 `{buf, 0}` |
| `read_msb(s, n)`（`:18-27`） | n：0～32 | 讀 n 位，MSB-first | n = 0 回傳 0；不檢查越界 |
| `write_msb(s, v, n)`（`:29-37`） | v、n | 寫 v 的低 n 位，高位先寫 | 每一位都會設或清，所以舊資料不影響寫到的位元（`:28` 註解說要先清 0 是保守說法，只有「沒寫到的位元」才需要清） |
| `read_lsb(s, n)`（`:40-49`） | n：0～32 | 讀 n 位，LSB-first | 第 i 個讀到的位元放在結果的 bit i |
| `write_lsb(s, v, n)`（`:50-58`） | v、n | 寫 v 的低 n 位，低位先寫 | |
| `get_bits_words(w, pos, n)`（`:62-68`） | word 陣列、起點位元、n：0～32 | LSB-first（bit 0 = `w[0]` 的 bit 0） | **一定會讀 `w[idx+1]`**，陣列尾巴要多留一個 word（測試的 `words[]` 第 3 個 0 就是這個用途） |

#### 程式流程

`read_msb` 每一圈（`:20-25`）：
1. `byte = pos >> 3`（第幾個 byte）。
2. `bit = 7 - (pos & 7)`（byte 內從 bit7 往下）。
3. `v = (v << 1) | ((buf[byte] >> bit) & 1)`（新位元接在最右邊，所以先讀的變高位）。
4. `pos++`。

`read_lsb` 每一圈（`:42-47`）：`bit = pos & 7`（從 bit0 往上），`v |= 位元 << i`（第 i 個讀到的放 bit i，所以先讀的變低位）。

**MSB-first 圖解**（測試資料 `A5 3C`，`:77-81`）：

```text
byte:        |------- 0xA5 -------|------- 0x3C -------|
byte 內 bit:  7 6 5 4 3 2 1 0      7 6 5 4 3 2  1 0
值:           1 0 1 0 0 1 0 1      0 0 1 1 1 1  0 0
pos:          0 1 2 3 4 5 6 7      8 9 10 ...     15
欄位:        [ 3 ][----- 7 -----]  [---- 6 ----]
read_msb(3) = 101            = 0x5
read_msb(7) = 00101 00       = 0x14   ← 跨 byte：A5 的低 5 位 + 3C 的高 2 位
read_msb(6) = 111100         = 0x3C
```

**LSB-first 圖解**（同一份資料，`:84-87`）：

```text
byte:        |------- 0xA5 -------|------- 0x3C -------|
byte 內 bit:  0 1 2 3 4 5 6 7      0 1 2 3 4 5  6 7      ← 注意：從 bit0 開始排
值:           1 0 1 0 0 1 0 1      0 0 1 1 1 1  0 0
pos:          0 1 2 3 4 5 6 7      8 9 10 ...     15
read_lsb(3)：讀到 1,0,1 → bit0=1 bit1=0 bit2=1      = 0b101     = 0x5
read_lsb(7)：讀到 0,0,1,0,1,0,0 → bit2、bit4 = 1     = 0b0010100 = 0x14
read_lsb(6)：讀到 1,1,1,1,0,0 → bit0..3 = 1          = 0b001111  = 0x0F
```

**跨 word（`get_bits_words`，`:62-68`）**：把 `w[idx+1]:w[idx]` 拼成 64 位（高 word 在左），右移 `off` 再 mask。

```text
words = {0xA0000000, 0x0000000B}，pos = 28，n = 8
  two = 0x0000000B_A0000000
  two >> 28 = 0x...BA
  & 0xFF    = 0xBA          ← w0 的 bit31..28（A）在低 4 位，w1 的 bit3..0（B）在高 4 位
```

如果題目的 word 陣列是 MSB-first（pos 0 = `w[0]` 的 bit31），要另外寫，見食譜 6.4.3。

main 的其他測試：8 個寬度 1～32 混合的欄位寫入再讀回（`:89-96`、`:99-103`），並檢查第一個 byte：MSB 版 `0xBF`（`101 11111`）、LSB 版 `0xFD`（低 3 位 101、往上 5 位 11111）。

#### 要改的地方

沒有 `TODO(改這裡)`。依題目挑 `read_msb` 或 `read_lsb`。

#### 實際執行輸出

環境：host gcc 13.3、x86_64。

```text
$ gcc -O2 -Wall -Wextra bitstream.c -o bs && ./bs
bitstream: ALL PASS
```

rv32 qemu 兩種 `-march` 也是 `bitstream: ALL PASS`。

#### 常見錯誤

| 症狀 | 原因 | 修法 |
|---|---|---|
| 讀出來的值剛好位元反過來 | MSB-first / LSB-first 用錯 | 拿題目範例手算第一個欄位，確定是哪一種 |
| 讀第二批資料從錯的位置開始 | 重複用同一個 `BitStream`，pos 沒歸零 | 新一批資料用新的 `BitStream x = {buf, 0}` |
| 寫完的 buffer 尾巴有舊資料 | 沒寫到的位元沒清 | 寫之前 `memset(buf, 0, sizeof buf)` |
| `get_bits_words` 讀到陣列外 / 當機 | 最後一個 word 時讀了 `w[idx+1]` | 陣列多配一個 word，設成 0 |
| 一次讀 33 位以上 | 回傳只有 32 位 | 拆成兩次讀 |
| 太慢（大量資料） | 一次 1 位 | 先求正確交出去；要優化再改成一次取一個 byte |

### 6.3.4 `rv32_encode_decode.c`

#### 用途

RV32I 指令的「組譯器方向」（欄位 → 機器碼）與「反組譯器方向」（機器碼 → 欄位、文字），加上一個能跑程式的迷你模擬器（`rv32_encode_decode.c:1-11`）。期望值是用 `riscv64-unknown-elf-as -march=rv32i` + objdump 得到的（`:110`）。

#### 怎麼編譯 / 執行

在 `預製程式碼/bits-riscv/`：

```sh
gcc -O2 -Wall -Wextra rv32_encode_decode.c -o /tmp/rv && /tmp/rv
```

#### 對外介面

| 名稱 | 參數 | 回傳 / 效果 | 注意 |
|---|---|---|---|
| `BITS(x, hi, lo)`（`:17`） | x、hi、lo | `x[hi:lo]`，`unsigned` | 寬度 32 會 UB；這檔只用到 ≤ 20 位 |
| `sext(v, bits)`（`:18`） | v、bits | 符號延伸 | 同 `sign_extend`，bits = 0 UB |
| `OP_LUI`…`OP_OP`（`:20-21`） | — | 9 個 opcode | 見 6.2.7 表 |
| `enc_r(f7, rs2, rs1, f3, rd, op)`（`:24-25`） | 欄位 | R 型機器碼 | **參數順序照機器碼由左到右** |
| `enc_i(imm, rs1, f3, rd, op)`（`:26-27`） | imm 12 位有號 | I 型 | imm 自動 `& 0xFFF`；範圍 −2048～2047 不檢查 |
| `enc_s(imm, rs2, rs1, f3, op)`（`:28-30`） | imm 12 位 | S 型 | |
| `enc_b(imm, rs2, rs1, f3, op)`（`:31-34`） | imm = 位元組偏移，偶數 | B 型 | imm 是「相對本指令位址」的 byte 數；奇數的 bit0 被丟掉 |
| `enc_u(imm20, rd, op)`（`:35`） | **高 20 位的值**（不是 <<12 之後） | U 型 | `enc_u(0x12345, 5, OP_LUI)` = `lui x5,0x12345` |
| `enc_j(imm, rd, op)`（`:36-39`） | imm 偶數，±1 MiB | J 型 | |
| `OPC/RD/F3/RS1/RS2/F7(x)`（`:42-47`） | 機器碼 | 各欄位 | |
| `imm_i/imm_s/imm_b/imm_j(x)`（`:48-54`） | 機器碼 | 已符號延伸的立即值 | |
| `imm_u(x)`（`:52`） | 機器碼 | `x & 0xFFFFF000`（已經 <<12） | 和 `enc_u` 的參數單位不同，注意 |
| `disasm(x, out)`（`:57-74`） | 機器碼、輸出字串 | 子集反組譯 | 支援：add/sub、addi、lw、sw、beq/bne、jal、jalr、lui、auipc；其他印 `unknown 0x...`；暫存器印 `x10` 不印 `a0` |
| `CPU`（`:77`） | — | `x[32]`、`pc`、`mem[1024]` | `TODO(改這裡)` 記憶體大小 |
| `ld32/st32`（`:78-79`） | 位址 | 小端 4 byte 讀寫 | **不檢查越界** |
| `step(c)`（`:81-103`） | CPU | 執行一條；0 = 正常、−1 = 不認得（當停機） | 和 `disasm` 支援同一個子集 |

#### 程式流程

`step()`（`:81-103`）：
1. 取指令 `x = ld32(c, c->pc)`，預設 `next = pc + 4`（`:82`）。
2. 先讀 `a = x[rs1]`、`b = x[rs2]`、`rd`（`:83-84`）。不管格式都先讀，沒用到也沒關係。
3. 依 opcode 執行（`:85-99`）：分支成立就改 `next = pc + imm_b`；`jal` 寫 `rd = pc + 4`、`next = pc + imm_j`；`jalr` 先算目標 `t = (a + imm) & ~1` 再寫 rd（`:95`，因為 rd 可能等於 rs1）。
4. `x[0] = 0`（`:100`）：就算指令寫了 x0，也清回 0。
5. `pc = next`（`:101`）。

`main`（`:109-151`）：
1. 13 個編碼測試（`:111-123`），每個註解都寫了組語。
2. B / J / S 立即值解碼往返（`:125-127`）。
3. `disasm(0xfe2084e3)` 要等於 `"beq x1, x2, -24"`（`:128-130`）。
4. 模擬器測試（`:133-147`）：組一段「sum = 1+2+…+10，存到 mem[0x100]」的程式（`:134-143`），印出反組譯（`:145`），最多跑 1000 步（`:146`），檢查 `mem[0x100] = 55`、`x0 = 0`、停在 `pc = 0x1c`（`:147`）。

模擬器測試程式（`:134-143`）展開：

```text
0x00  addi a0,x0,0        sum = 0
0x04  addi a1,x0,10       i = 10
0x08  add  a0,a0,a1       loop: sum += i
0x0c  addi a1,a1,-1       i--
0x10  bne  a1,x0,-8       i != 0 → 跳回 0x08
0x14  sw   a0,0x100(x0)   mem[0x100] = sum
0x18  addi x0,x0,5        寫 x0（應該被忽略）
0x1c  0xFFFFFFFF          不認得 → step 回 -1 → 停
```

#### 要改的地方

| 行號 | 現在的值 | 意思 | 什麼情況要改、改成什麼 |
|---|---|---|---|
| `rv32_encode_decode.c:56` | `// 反組譯成文字（只支援子集）。TODO(改這裡)：加新指令就在對應 opcode 下加 funct3/funct7 判斷` | `disasm()` 的 switch（`:58-72`） | 題目的指令不在子集內 → 照 6.2.7 的 funct3 表加 case；完整範例見食譜 6.4.5（實測過） |
| `rv32_encode_decode.c:77` | `uint8_t mem[1024]` | 模擬器記憶體 1 KiB | 題目程式或資料超過 1 KiB → 改大（例 65536）；`CPU c` 在 `main` 裡是區域變數（`:133`），改很大時改成 `static CPU c;` 避免堆疊不夠 |
| `rv32_encode_decode.c:81-99` | `step()` 只支援子集 | 模擬器 | 加指令時 `disasm` 和 `step` 兩邊都要加；範例見食譜 6.4.6（實測過） |

#### 實際執行輸出

環境：host gcc 13.3、x86_64。

```text
$ gcc -O2 -Wall -Wextra rv32_encode_decode.c -o rv && ./rv
0xfe2084e3   beq x1, x2, -24
  00: 00000513  addi x10, x0, 0
  04: 00a00593  addi x11, x0, 10
  08: 00b50533  add x10, x10, x11
  0c: fff58593  addi x11, x11, -1
  10: fe059ce3  bne x11, x0, -8
  14: 10a02023  sw x10, 256(x0)
  18: 00500013  addi x0, x0, 5
rv32_encode_decode: ALL PASS
```

和 GNU as / objdump 對答案（`riscv64-unknown-elf-as -march=rv32i`、`objdump -d -M no-aliases,numeric`，本章實際執行）：

```text
   0:	00500093          	addi	x1,x0,5
   4:	002081b3          	add	x3,x1,x2
   8:	40118233          	sub	x4,x3,x1
   c:	00812283          	lw	x5,8(x2)
  10:	fe512a23          	sw	x5,-12(x2)
  14:	fff38313          	addi	x6,x7,-1
  18:	123452b7          	lui	x5,0x12345
  1c:	fffff317          	auipc	x6,0xfffff
  20:	00008067          	jalr	x0,0(x1)
  24:	fe2084e3          	beq	x1,x2,c <L0-0x18>
  28:	7e419263          	bne	x3,x4,80c <L0+0x7e8>
  2c:	7e0000ef          	jal	x1,80c <L0+0x7e8>
  30:	ffdff06f          	jal	x0,2c <L0+0x8>
```

13 個值和 `rv32_encode_decode.c:111-123` 的期望值完全一樣。objdump 在分支後面印的是「目標位址」（例 `0x24 - 24 = 0xc`），不是偏移量。

其他本章額外組譯的指令（食譜用）：

```text
   0:	344120ef          	jal	x1,12344
   4:	006289e3          	beq	x5,x6,816
   8:	007342b3          	xor	x5,x6,x7
   c:	0ff37293          	andi	x5,x6,255
  10:	00331293          	slli	x5,x6,0x3
  14:	40335293          	srai	x5,x6,0x3
  18:	0062c863          	blt	x5,x6,28
  1c:	00334283          	lbu	x5,3(x6)
  20:	005303a3          	sb	x5,7(x6)
```

驗證自己編的機器碼的指令（README `:36`）：

```sh
echo "addi x1, x0, 5" | riscv64-unknown-elf-as -march=rv32i - -o /tmp/x.o && riscv64-unknown-elf-objdump -d -M no-aliases,numeric /tmp/x.o
```

分支 / 跳躍要寫成 `.+偏移` 或用標籤，例：`echo "jal x1, .+0x12344" | riscv64-unknown-elf-as -march=rv32i - -o /tmp/x.o`。

#### 常見錯誤

| 症狀 | 原因 | 修法 |
|---|---|---|
| `enc_r` 結果錯 | 參數順序搞錯（rs1/rs2 顛倒） | 順序是 `f7, rs2, rs1, f3, rd, op`，和機器碼由左到右一樣 |
| `lui` 編出來多了 12 個 0 | 傳入已經 <<12 的值 | `enc_u` 吃「高 20 位」；`imm_u` 回傳的才是 <<12 後的值 |
| 分支偏移差 4 | 以為是相對「下一條」 | RISC-V 的分支 / jal 偏移相對「本指令」位址 |
| 解碼負數立即值變成很大的正數 | 忘了符號延伸 | 用 `imm_*()`（都有 `sext`） |
| 模擬器跑到一半 segfault | pc 或 load/store 位址超過 `mem` | 加大 `mem` 或在 `ld32/st32` 加邊界檢查 |
| `mul x3,x1,x2` 被印成 `add` | `disasm` / `step` 只看 funct3、不看 funct7 = 0x01 | 見 6.6；要支援 M 擴充時先判斷 `F7(x) == 1` |
| RISC-V 上 printf 警告 | `uint32_t` 是 `unsigned long` | 轉 `(unsigned)`（`:15` 註解） |

### 6.3.5 `asm_examples.S`

#### 用途

7 個可以從 C 呼叫的 RV32 組語函式，示範迴圈、陣列、位元操作、Zbb 指令、會呼叫別的函式時怎麼存暫存器。副檔名是大寫 `.S`：gcc 會先跑 C 前處理器，所以能用 `#ifdef __riscv_zbb`（`asm_examples.S:1-4`）。

#### 怎麼編譯 / 執行

只組譯、看機器碼（不需要 C 函式庫），在 `預製程式碼/bits-riscv/`：

```sh
riscv64-unknown-elf-gcc -march=rv32imac_zicsr_zifencei_zba_zbb_zbs_zbkb -mabi=ilp32 -c asm_examples.S -o /tmp/a.o
riscv64-unknown-elf-objdump -d /tmp/a.o
```

連結成可執行檔在 qemu 上跑：見 6.3.6。檔頭 `:3` 寫的 `-march=rv32imac_zba_zbb_zbs` 也能組譯（本章實測），但和 README、SDK 的字串不同；以 README 的為準。

#### 對外介面

| 函式（C 原型） | 位置 | 做什麼 | 用到的暫存器 | 注意 |
|---|---|---|---|---|
| `uint32_t asm_sum_u32(const uint32_t *a, uint32_t n)` | `:8-18` | 陣列總和 | a0、a1、t0、t1 | 葉函式；n = 0 回 0 |
| `void asm_memcpy_words(uint32_t *dst, const uint32_t *src, uint32_t n)` | `:21-30` | 複製 n 個 word | a0、a1、a2、t0 | dst/src 要 4 byte 對齊；重疊時不保證 |
| `uint32_t asm_get_field(uint32_t x, uint32_t lo, uint32_t w)` | `:33-40` | `(x >> lo) & ((1<<w)-1)` | a0、a1、a2、t0 | **w 要 < 32**：w = 32 時硬體 `sll` 只看低 5 位 → mask = 0 → 回傳 0（qemu 實測） |
| `uint32_t asm_popcount_array_base(const uint32_t *a, uint32_t n)` | `:43-57` | 陣列 popcount，只用基本指令 | t0、t1、t2 | 內層迴圈次數 = 1 的個數 |
| `uint32_t asm_popcount_array_fast(...)` | `:60-75` | 有 Zbb 用 `cpop` | t0、t1 | 沒 Zbb 時 `j asm_popcount_array_base`（尾呼叫） |
| `int32_t asm_bnn_dot(const uint32_t *w, const uint32_t *x, uint32_t n)` | `:80-107` | BNN 內積 = 2·popcount(XNOR) − 32n | t0～t4 | Zbb：`xnor + cpop`；沒 Zbb：`xor + not + 迴圈` |
| `void asm_apply(uint32_t (*f)(uint32_t), uint32_t *a, uint32_t n)` | `:111-133` | `a[i] = f(a[i])` | s0～s2、ra、sp | 示範開堆疊、存 ra 和 s 暫存器 |

#### 程式流程（逐行）

`asm_sum_u32`（`:9-18`）：

```text
:10  li   t0, 0       t0 = sum = 0
:11  beqz a1, 2f      n == 0 → 跳到前面的標籤 2（f = forward）
:12  1: lw t1, 0(a0)  t1 = *a              ← 迴圈開頭，標籤 1
:13  add  t0, t0, t1  sum += t1
:14  addi a0, a0, 4   a++（一個 uint32_t = 4 byte）
:15  addi a1, a1, -1  n--
:16  bnez a1, 1b      n != 0 → 跳回標籤 1（b = back）
:17  2: mv a0, t0     回傳值放 a0
:18  ret              = jalr x0, 0(ra)
```

`asm_memcpy_words`（`:22-30`）：和上面同一個樣子，`lw t0,0(a1)` 讀、`sw t0,0(a0)` 寫，兩個指標都 +4。

`asm_get_field`（`:34-40`）：`srl a0,a0,a1`（邏輯右移，補 0）→ `li t0,1; sll t0,t0,a2; addi t0,t0,-1`（mask）→ `and a0,a0,t0`。

`asm_popcount_array_base`（`:44-57`）：外層 `1:` 每個 word；內層 `2:` 在 t1 ≠ 0 時 `t2 = t1-1; t1 &= t2; t0++`，`j 2b` 回內層開頭；t1 = 0 跳 `3:` 換下一個 word；`9:` 回傳。

`asm_popcount_array_fast`（`:61-75`）：
- `#ifdef __riscv_zbb`：每個 word `lw` → `cpop t1,t1` → `add`。
- `#else`：`j asm_popcount_array_base`。這是**尾呼叫**：不用 `call`，ra 不變，所以 base 版 `ret` 直接回到 C 的呼叫者。

`asm_bnn_dot`（`:81-107`）：
- `slli t3, a2, 5`：先算 32n（`:83`）。
- 每個 word：`lw t1`（w）、`lw t2`（x）。
- Zbb：`xnor t1,t1,t2`、`cpop t1,t1`、`add t0,t0,t1`（`:88-90`）。
- 無 Zbb：`xor` + `not`（= `xori -1`）+ 和 base 版一樣的清最低位迴圈（`:92-99`）。
- 最後 `slli t0,t0,1`（×2）、`sub a0,t0,t3`（−32n）（`:105-106`）。

`asm_apply`（`:112-133`），會呼叫別人的函式要做 4 件事：

```text
:113 addi sp, sp, -16    開 16 byte 堆疊（sp 必須維持 16 的倍數）
:114 sw ra, 12(sp)       呼叫 f 會蓋掉 ra，先存
:115-117 sw s0/s1/s2     s 暫存器是 callee-saved：我用了就要負責還原
:118-120 mv s0,a0 ...    把 f、a、n 搬到 s 暫存器（呼叫 f 之後 a 暫存器會被改，s 不會）
:122 lw a0, 0(s1)        參數 = a[i]
:123 jalr ra, 0(s0)      呼叫 f（間接呼叫）
:124 sw a0, 0(s1)        a[i] = 回傳值
:128-131 lw ...          還原 s2、s1、s0、ra
:132 addi sp, sp, 16     關堆疊
:133 ret
```

堆疊排列：

```text
sp+12  ra
sp+8   s0
sp+4   s1
sp+0   s2      ← sp（進函式後）
```

**從 C 呼叫**：C 端只要宣告原型（`asm_test.c:8-14`），連結時把 `.S` 一起給 gcc。參數依序放 a0、a1、a2…，回傳值從 a0 拿。C 編譯器會假設你遵守 ABI：t、a 暫存器隨便你改；s 暫存器、sp 要還原。

**機器碼長什麼樣**：用 Hazard3 的 `-march`（有 `c`）時，很多指令被壓成 16 位元（objdump 顯示 4 個 hex 字），實測：

```text
0000005c <asm_popcount_array_fast>:
  5c:	4281                	li	t0,0
  5e:	c989                	beqz	a1,70 <.L9^B2>
  60:	00052303          	lw	t1,0(a0)
  64:	60231313          	cpop	t1,t1
  68:	929a                	add	t0,t0,t1
  6a:	0511                	addi	a0,a0,4
  6c:	15fd                	addi	a1,a1,-1
  6e:	f9ed                	bnez	a1,60 <.L1^B4>
  70:	8516                	mv	a0,t0
  72:	8082                	ret
```

`-march=rv32i`（沒 `c`、沒 Zbb）時全部是 32 位元，而且 `fast` 版只剩一條跳躍（實測）：

```text
00000000 <asm_sum_u32>:
   0:	00000293          	li	t0,0
   4:	00058c63          	beqz	a1,1c <.L2^B1>
   8:	00052303          	lw	t1,0(a0)
   c:	006282b3          	add	t0,t0,t1
  10:	00450513          	addi	a0,a0,4
  14:	fff58593          	addi	a1,a1,-1
  18:	fe0598e3          	bnez	a1,8 <.L1^B1>
  1c:	00028513          	mv	a0,t0
  20:	00008067          	ret
00000090 <asm_popcount_array_fast>:
  90:	fcdff06f          	j	5c <asm_popcount_array_base>
```

`fe0598e3` 的解碼就是 6.2.8 的 B 型範例；`fcdff06f` 是 `jal x0, -52`（0x90 − 52 = 0x5c）。

#### 要改的地方

沒有 `TODO(改這裡)`。寫新函式：複製最接近的一個（葉函式抄 `asm_sum_u32`，要呼叫別人抄 `asm_apply`），改名、加 `.globl`，`asm_test.c` 同步加宣告與測試（食譜 6.4.7）。

#### 實際執行輸出

見 6.3.6（兩個檔一起測）。

#### 常見錯誤

| 症狀 | 原因 | 修法 |
|---|---|---|
| `undefined reference to 'asm_xxx'` | 少了 `.globl asm_xxx`，或連結時沒給 `.S` | 加 `.globl`；gcc 指令列把 `.S` 一起列 |
| `Error: unrecognized opcode 'cpop a0,a1', extension 'zbb' required` | `-march` 沒有 `_zbb`（實測訊息） | 用 README 的 `-march`，或包在 `#ifdef __riscv_zbb` |
| `#ifdef` 沒作用、被當成註解或報錯 | 檔名是小寫 `.s`（不跑前處理器） | 改成大寫 `.S` |
| 從組語呼叫 C 函式後當機 / 回不去 | 沒存 ra | 照 `asm_apply` 開堆疊存 ra |
| C 端的變數莫名其妙被改 | 用了 s 暫存器沒還原 | 用到的 s0～s11 都要先存後還 |
| 讀 `uint8_t` 陣列得到負數 | 用了 `lb`（符號延伸） | 用 `lbu`（速查表 `:39`） |
| 陣列第 i 個位址算錯 | 位移是 byte，不是元素 | `i*4`：`slli t0,i,2; add t0,t0,a0`，或 Zba 的 `sh2add` |
| `asm_get_field(x, lo, 32)` 回傳 0 | 硬體位移只看低 5 位 | 寬度 32 在呼叫端特判 |

### 6.3.6 `asm_test.c`

#### 用途

測試 `asm_examples.S`：每個組語函式都和 C 參考版比對；另外示範 inline asm（`asm_test.c:1-3`）。只能用 RISC-V 編譯器編。

#### 怎麼編譯 / 執行

README 沒有給「在 qemu 上連結執行」的完整指令。這個容器的 `riscv64-unknown-elf-gcc` 只附 picolibc（沒有 newlib），而 picolibc 預設的 crt0 / 連結腳本是給裸機用的，`qemu-riscv32`（Linux user mode）上直接跑會 segfault（本章實測：`__stack` = `0x80400000` 沒有對應的記憶體）。所以要一個小 shim：自己寫進入點、把 printf 接到 Linux 的 `write` 系統呼叫。本章用的 `linux_shim.c`（放在自己的暫存資料夾，**不要放進 Pico 專案**）：

```c
/* linux_shim.c -- 讓 picolibc 的 printf 在 qemu-riscv32（Linux user mode）印得出來
 * 只給 qemu 測試用，不要放進 Pico 專案（Pico SDK 有自己的 crt0 和 stdio）。
 * 編譯時加 -nostartfiles：不用 picolibc 的 crt0（它的 __stack 位址在 qemu-user 沒有對應的記憶體）。
 * stdout 每個字元用 Linux 系統呼叫 write(1,...)（a7=64），結束用 exit（a7=93）。 */
#include <stdio.h>
static long sys_call3(long n, long a, long b, long c) {
    register long a0 asm("a0") = a, a1 asm("a1") = b, a2 asm("a2") = c, a7 asm("a7") = n;
    asm volatile("ecall" : "+r"(a0) : "r"(a1), "r"(a2), "r"(a7) : "memory");
    return a0;
}
static int shim_putc(char ch, FILE *f) { (void)f; sys_call3(64, 1, (long)&ch, 1); return (unsigned char)ch; }
static FILE shim_out = FDEV_SETUP_STREAM(shim_putc, NULL, NULL, _FDEV_SETUP_WRITE);
FILE *const stdout = &shim_out;
FILE *const stderr = &shim_out;
void _exit(int code) { for (;;) sys_call3(93, code, 0, 0); }

char shim_stack[64 * 1024] __attribute__((aligned(16)));   /* 在 .bss 裡；清 .bss 時還沒開始用它 */
/* 進入點：設 gp → 把 .bss 清 0（qemu 載入時 .bss 和 .data 同一頁，不一定是 0）→ 設 sp → main → exit */
__attribute__((naked, section(".init"))) void _start(void) {
    asm volatile(".option push\n.option norelax\n la gp, __global_pointer$\n.option pop\n"
                 " la t0, __bss_start\n la t1, __bss_end\n"
                 "1: bgeu t0, t1, 2f\n sb zero, 0(t0)\n addi t0, t0, 1\n j 1b\n"
                 "2: la sp, shim_stack + 65536\n"
                 " call main\n"
                 " call _exit\n");     /* main 的回傳值已經在 a0 = _exit 的參數 */
}
```

為什麼要清 `.bss`：第一版沒有清，程式印出 `(基本 ISA 版本…)` 但沒有 `ALL PASS`、也沒有 `FAIL`，回傳 1。原因是 picolibc 連結腳本把 `.bss` 和 `.data` 放在同一頁（`fails` 在 `0x80200020`），qemu 載入 `.data` 那一頁時把檔案裡後面的位元組也帶進來，`fails` 一開始就不是 0。加上清 `.bss` 後全部正常。這也是「靜態變數一定是 0」的前提：crt0 有做清 0。

執行（`B` = `預製程式碼/bits-riscv` 的完整路徑，在放 `linux_shim.c` 的資料夾執行）：

```sh
for M in rv32imac_zicsr_zifencei rv32imac_zicsr_zifencei_zba_zbb_zbs_zbkb; do
  echo "== -march=$M"
  riscv64-unknown-elf-gcc -march=$M -mabi=ilp32 -O2 -Wall -Wextra --specs=picolibc.specs -nostartfiles \
     $B/asm_test.c $B/asm_examples.S linux_shim.c -o asm_$M.elf && qemu-riscv32 ./asm_$M.elf; echo "exit=$?"
done
```

在 Pico 2 上：把 `asm_examples.S` 加進 `add_executable(...)`，`PICO_PLATFORM=rp2350-riscv` 編譯，`printf` 經 USB/UART 印（README `:38-39`）。**本章沒有實測**：這個容器的 RISC-V 工具鏈沒有 newlib，用 pico-sdk 2.2.0 設定 `-DPICO_PLATFORM=rp2350-riscv -DPICO_GCC_TRIPLE=riscv64-unknown-elf -DPICO_CLIB=picolibc` 後，cmake 設定成功，但編 boot_stage2 時失敗：

```text
riscv64-unknown-elf-gcc: fatal error: cannot read spec file 'nosys.specs': No such file or directory
```

考場容器如果有 pico-sdk 的 RISC-V 工具鏈（例如 `riscv32-unknown-elf` 或 SDK 官方的 `riscv32-pico-elf`）就不會有這個問題 ⚠️未驗證。Pico 的 build 流程見第 3 章。

#### 對外介面

| 名稱 | 位置 | 做什麼 |
|---|---|---|
| 7 個組語函式的宣告 | `:8-14` | 名字、參數要和 `.S` 完全一致 |
| `c_sum`、`c_pop`、`c_pop_arr`、`c_bnn` | `:17-23` | C 參考版（標準答案） |
| `times3` | `:24` | 給 `asm_apply` 用的回呼函式 |
| `inline_add(a, b)` | `:29-33` | `asm volatile("add %0, %1, %2" : "=r"(r) : "r"(a), "r"(b));` |
| `inline_popcount(x)` | `:34-42` | 有 Zbb 用 `cpop`，沒有就呼叫 `c_pop` |
| `CHECK(got, exp)` | `:45-46` | 轉 `long` 比較，失敗印行號 |

inline asm 格式：`asm volatile("指令" : 輸出 : 輸入 : 會被弄髒的東西);`。`"=r"` = 輸出到某暫存器、`"r"` = 輸入、`"+r"` = 又讀又寫、`"i"` = 常數；`%0 %1 %2` 依「先輸出再輸入」編號；有讀寫記憶體要加 `"memory"`（速查表 `:59-67`）。

#### 程式流程

`main`（`:48-86`）：
1. 測試資料 `a[]`、`b[]` 各 8 個，包含 `0xFFFFFFFF`、`0x80000000`、0（`:49-51`）。
2. `asm_sum_u32` 對 `c_sum`，以及 n = 0（`:53-54`）。
3. `asm_memcpy_words` 複製後逐個比對（`:56-58`）。
4. `asm_get_field`：`(0xABCD1234, 8, 8)` = `0x12`、`(…, 28, 4)` = `0xA`（`:60-61`）。
5. popcount 兩版對 `c_pop_arr`（`:63-65`）。
6. BNN：一般資料、自己對自己 = +32n、對自己的反相 = −32n（`:67-70`）。
7. `asm_apply(times3, {1,10,100})` → `{3,30,300}`（`:72-74`）。
8. inline asm（`:76-77`）。
9. 印目前是哪個版本（`:79-83`），全部通過印 `asm_test: ALL PASS`（`:84`）。

#### 要改的地方

沒有 `TODO(改這裡)`。加新組語函式時：`:8-14` 加宣告、`:17-24` 加 C 參考版、`main` 加 `CHECK`。

#### 實際執行輸出

環境：`riscv64-unknown-elf-gcc` 13.2.0、picolibc 1.8.6、`qemu-riscv32` 8.2.2（x86_64 host）。

```text
== -march=rv32imac_zicsr_zifencei
(基本 ISA 版本：迴圈 popcount)
asm_test: ALL PASS
exit=0
== -march=rv32imac_zicsr_zifencei_zba_zbb_zbs_zbkb
(Zbb 版本：使用 cpop/xnor)
asm_test: ALL PASS
exit=0
```

另外 `-march=rv32i_zicsr`（最小的整數指令集）也是 `(基本 ISA 版本：迴圈 popcount)`、`asm_test: ALL PASS`。同一個 shim 也跑了 `bitstream.c`、`packet_fields.c`、`rv32_encode_decode.c`，兩種 `-march` 都是 `ALL PASS`。

Hazard3 指令在 qemu 上的實測（本章另寫的 `edge.c`，Zbb/Zbkb `-march`）：

```text
asm_get_field(0xABCD1234, 0, 32) = 0x00000000
asm_get_field(0xABCD1234, 4, 0)  = 0x00000000
clz(0) = 32
ctz(0) = 32
rev8(0x11223344) = 0x44332211
orc.b(0x00120034) = 0x00FF00FF
pack(0x1234ABCD,0x5678EF01) = 0xEF01ABCD
brev8(0x01020380) = 0x8040C001
```

#### 常見錯誤

| 症狀 | 原因 | 修法 |
|---|---|---|
| 用 host `gcc` 編 `asm_test.c` 失敗 | `.S` 是 RISC-V 組語 | 用 `riscv64-unknown-elf-gcc` |
| `fatal error: stdio.h: No such file or directory` | 沒有加 `--specs=picolibc.specs`（這個容器沒有 newlib） | 加 `--specs=picolibc.specs`；Pico 專案用 SDK 自己的 C 函式庫 |
| qemu `Segmentation fault`（exit 139） | 用了 picolibc 預設 crt0 | 加 `-nostartfiles` 和上面的 shim |
| 沒有 `ALL PASS` 也沒有 `FAIL`，exit 1 | `.bss` 沒清 0 | shim 裡清 `.bss`（上面版本已經有） |
| `undefined reference to 'shim_stack'` | 在 naked 函式的 asm 字串裡用了 `static` 變數 | 堆疊陣列不要加 `static` |
| 宣告和 `.S` 的參數不同，結果亂 | C 不會檢查組語的參數 | 宣告逐字對照 `.S` 開頭的註解 |

### 6.3.7 `rv32_asm_cheatsheet.md`

#### 用途

紙本速查。7 節：ABI（`:3-17`）、偽指令（`:19-34`）、載入 / 儲存大小（`:36-45`）、`.S` 函式寫法（`:47-57`）、inline asm（`:59-67`）、Hazard3 位元擴充（`:69-94`）、opcode / funct 表（`:96-99`）。

#### 怎麼編譯 / 執行

不用編譯。本章把第 6 節列的 29 條指令用 `riscv64-unknown-elf-as -march=rv32imac_zicsr_zifencei_zba_zbb_zbs_zbkb` 重新組譯，全部成功：

```text
60259513 cpop a0,a1      | 60059513 clz a0,a1       | 60159513 ctz a0,a1
6985d513 rev8 a0,a1      | 2875d513 orc.b a0,a1     | 40c5f533 andn a0,a1,a2
40c5e533 orn a0,a1,a2    | 40c5c533 xnor a0,a1,a2   | 0ac5c533 min a0,a1,a2
0ac5f533 maxu a0,a1,a2   | 60459513 sext.b a0,a1    | 60559513 sext.h a0,a1
0805c533 zext.h a0,a1    | 60c59533 rol a0,a1,a2    | 60c5d533 ror a0,a1,a2
6075d513 rori a0,a1,0x7  | 20c5a533 sh1add a0,a1,a2 | 20c5c533 sh2add a0,a1,a2
20c5e533 sh3add a0,a1,a2 | 28c59533 bset a0,a1,a2   | 48c59533 bclr a0,a1,a2
68c59533 binv a0,a1,a2   | 28559513 bseti a0,a1,0x5 | 48c5d533 bext a0,a1,a2
08c5c533 pack a0,a1,a2   | 08c5f533 packh a0,a1,a2  | 6875d513 brev8 a0,a1
08f59513 zip a0,a1       | 08f5d513 unzip a0,a1
```

（`h3.bextm` 是 Hazard3 自訂指令，GNU as 不認得，要用 `.insn`；本章沒有測試 ⚠️未驗證。）

#### 對外介面

重點條目（原文見檔案）：

| 主題 | 速查表內容 | 本章補充 |
|---|---|---|
| `li rd, imm` | lui + addi | 低 12 位 ≥ 0x800 時 lui 的值 +1（6.2.8 實測） |
| `call f` / `tail f` | auipc + jalr | `asm_popcount_array_fast` 用的是 `j`（範圍 ±1 MiB，同一檔案夠用） |
| `lb` vs `lbu` | 讀 `uint8_t` 用 `lbu` | |
| `blt/bge` vs `bltu/bgeu` | 有號 vs 無號 | |
| `srl` vs `sra` | 補 0 vs 補符號位 | |
| C 內建 → 指令 | `__builtin_popcount`→`cpop`、`__builtin_clz`→`clz`、`__builtin_bswap32`→`rev8` | 本章實測：`bitops.h` 的 `POPCOUNT`→`cpop`、`clz32`→`clz`、`ctz32`→`ctz`、`bswap32`（C 版）→`rev8`、`rotl32`→`rol`、`SET_BIT`→`bset`、`TEST_BIT`→`bext`、`a[i]`→`sh2add`；`brev8`（C 版）**不會**變成指令 |
| 判斷擴充 | `#ifdef __riscv_zbb`、`__riscv_zba`、`__riscv_zbs`、`__riscv_zbkb` | |

#### 程式流程

不適用。

#### 要改的地方

沒有 `TODO(改這裡)`，只查不改。

#### 實際執行輸出

見上面「怎麼編譯 / 執行」。

#### 常見錯誤

| 症狀 | 原因 | 修法 |
|---|---|---|
| 想用 `clmul` 算 CRC，組譯失敗 | Hazard3 沒有 Zbc | 用查表（第 5 章 `algo/crc32.c`）或 DMA sniffer（第 3 章） |
| `pack` 的結果高低半顛倒 | `pack rd, a, b` = `(b[15:0] << 16) \| a[15:0]`，第二個運算元在高位 | 實測 `pack(0x1234ABCD, 0x5678EF01)` = `0xEF01ABCD` |

### 6.3.8 `README.md`

#### 用途

資料夾入口：檔案 → 題型對照（`:3-11`）、位元題 SOP 6 步（`:13-19`）、PC 編譯指令（`:21-27`）、RISC-V 交叉編譯（`:29-40`）、驗證紀錄（`:42-48`）。

#### 怎麼編譯 / 執行

README 的 3 行 PC 指令（`:23-25`）本章照做，3 個都印 `ALL PASS`（輸出見各節）。`:33-34` 的「只組譯 + objdump」和 `:36` 的「用 GNU as 驗證」也照做過（6.3.4、6.3.5）。

#### 對外介面

位元題 SOP（`:14-19`）原樣：畫 32 格標 `[hi:lo]` → 取出 `(x >> lo) & ((1u << 寬度) - 1)`、放入先清再 OR → 有號欄位 `sign_extend` → 一律 `uint32_t`，`1u << 32` 要特判 → printf 轉 `(unsigned)` → 手算 1～2 組寫成 `CHECK`。

#### 程式流程

不適用。

#### 要改的地方

沒有 `TODO(改這裡)`。

#### 實際執行輸出

見 6.3.2～6.3.6。

#### 常見錯誤

| 症狀 | 原因 | 修法 |
|---|---|---|
| 找不到 README `:43` 說的 bitops 測試 | 不在 repo 裡（已知問題 8） | 用 6.3.1 的 `bitops_selftest.c` |
| `:45` 說「pico-build 映像 + picolibc + qemu 跑 asm_test」，照 `:33` 的指令做不出可執行檔 | README 沒寫連結指令和 shim | 用 6.3.6 的指令和 `linux_shim.c` |

## 6.4 照題目改：食譜

### 6.4.1 題目給一張封包欄位表 → 打包 / 拆解 / 上線

題目長這樣：「header 32 位：bit31 valid(1)、bit30..27 prio(4)、bit26..16 addr(11)、bit15..8 cmd(8)、bit7..0 seq(8)。以 big-endian 傳送。」

改哪些行（複製 `packet_fields.c` 成新檔再改）：
1. `:15-22` 的 `#define` 換成：

```c
#define VALID_SHIFT 31
#define VALID_W     1
#define PRIO_SHIFT  27
#define PRIO_W      4
#define ADDR_SHIFT  16
#define ADDR_W      11
#define CMD_SHIFT   8
#define CMD_W       8
#define SEQ_SHIFT   0
#define SEQ_W       8
```

2. 先檢查：1 + 4 + 11 + 8 + 8 = 32，每個 SHIFT = 上一個 SHIFT − 自己的 W。
3. `Header`（`:25`）改成 `typedef struct { uint32_t valid, prio, addr, cmd, seq; } Hdr;`，`pack/unpack`（`:28-41`）照原本的樣子每個欄位一行。
4. 上線用 `store_be32(wire, pack(h))`，收到用 `unpack(load_be32(wire))`。

怎麼驗證：手算一組。`{1, 0x9, 0x5A5, 0x42, 0x07}`：

```text
 1 | 1001 | 101 1010 0101 | 0100 0010 | 0000 0111
 = 1100 1101 1010 0101 0100 0010 0000 0111 = 0xCDA54207
```

成功的樣子（本章實測）：

```text
pack = 0xCDA54207
wire(大端) = CD A5 42 07
memcpy(host 小端) = 07 42 A5 CD
unpack: valid=1 prio=9 addr=0x5A5 cmd=0x42 seq=7
```

第三行示範：直接 `memcpy` 得到的是 host（小端）順序，和規格的大端不同。

### 6.4.2 從位元流讀固定寬度的樣本（MSB-first）

題目長這樣：「感測器資料是連續的 10 位元樣本，MSB-first 緊密排列。」

改哪些行：不用改 `bitstream.c` 的函式，在自己的 `main` 寫：

```c
BitStream r = {buf, 0};
for (int i = 0; i < n_samples; i++) sample[i] = read_msb(&r, 10);
```

怎麼驗證：寫 4 個已知值再讀回。成功的樣子（本章實測，寫入 `0x3FF, 0x001, 0x2AA, 0x155`）：

```text
MSB-first 4x10bit -> FF C0 1A A9 55 (pos=40)
 3FF 001 2AA 155
```

手算對照：`1111111111 0000000001 1010101010 0101010101` 每 8 位切 = `FF C0 1A A9 55`。

### 6.4.3 LSB-first、或 word 陣列 MSB-first

- 題目說「LSB-first」（deflate 那種）：上面改用 `read_lsb` / `write_lsb`。同樣 4 個值，本章實測寫出 `FF 07 A0 6A 55`，讀回 `3FF 001 2AA 155`。
- 題目給的是 `uint32_t` 陣列、pos 0 = `w[0]` 的 bit31（MSB-first）：`get_bits_words` 是 LSB-first，不能直接用。加這個函式（本章實測 `{0x0000000A, 0xB0000000}` 從 pos 28 取 8 位 = `0xAB`）：

```c
/* MSB-first 版的跨 word 取欄位：pos 0 = w[0] 的 bit31；n = 1..32；陣列尾巴多留一個 word */
uint32_t get_bits_words_msb(const uint32_t *w, size_t pos, int n) {
    size_t idx = pos >> 5; int off = pos & 31;
    uint64_t two = ((uint64_t)w[idx] << 32) | w[idx + 1];       /* 高位 word 在前 */
    uint64_t mask = (n == 32) ? 0xFFFFFFFFull : ((1ull << n) - 1);
    return (uint32_t)((two >> (64 - off - n)) & mask);
}
```

- 題目給的是 byte 陣列但說「以 32 位元大端 word 為單位 MSB-first」：等於 byte 陣列的 MSB-first，直接用 `read_msb`。

### 6.4.4 依規格重新排列位元

題目長這樣：「輸出的 bit j 取自輸入的 bit src[j]」。

`permute_bits`（`packet_fields.c:73-78`）的方向是「輸入 bit i → 輸出 bit perm[i]」。兩種寫法：
- 題目給「i 搬到哪」→ 直接用 `permute_bits(x, perm, n)`。
- 題目給「j 從哪來」→ 自己寫一個反方向的：

```c
uint32_t gather_bits(uint32_t x, const int src[], int n) {
    uint32_t y = 0;
    for (int j = 0; j < n; j++) y |= ((x >> src[j]) & 1u) << j;   // 輸出第 j 位 ← 輸入第 src[j] 位
    return y;
}
```

怎麼驗證：左右顛倒時兩種寫法結果一樣（`{3,2,1,0}`：`0x3` → `0xC`，`packet_fields.c:106-107`）；不對稱的排列要手算一組。RISC-V 的 B / J 立即值就是這種重排（6.2.8）。

### 6.4.5 反組譯器加指令

題目長這樣：「反組譯器要支援 xor、andi、slli、srai、blt…」。

改哪些行：`rv32_encode_decode.c:59-67` 的三個 case。改後（本章在副本實測，13 個原本的測試仍 PASS）：

```c
    case OP_OP:
        if (F7(x) == 0x00 || F7(x) == 0x20) {
            static const char *nm[8] = {"add","sll","slt","sltu","xor","srl","or","and"};
            const char *n = nm[F3(x)];
            if (F7(x) == 0x20) { if (F3(x) == 0) n = "sub"; else if (F3(x) == 5) n = "sra"; else break; }
            sprintf(out, "%s x%u, x%u, x%u", n, RD(x), RS1(x), RS2(x)); return;
        }
        break;
    case OP_IMM: {
        static const char *nm[8] = {"addi","slli","slti","sltiu","xori","srli","ori","andi"};
        unsigned f3 = F3(x);
        if (f3 == 1 || f3 == 5) {                       /* 移位：imm[4:0] = shamt，imm[11:5] 分 srli/srai */
            sprintf(out, "%s x%u, x%u, %u", f3 == 1 ? "slli" : (F7(x) == 0x20 ? "srai" : "srli"), RD(x), RS1(x), RS2(x));
        } else sprintf(out, "%s x%u, x%u, %d", nm[f3], RD(x), RS1(x), imm_i(x));
        return; }
```

分支（取代 `:65-67`）：

```c
    case OP_BR:
        { static const char *nm[8] = {"beq","bne",0,0,"blt","bge","bltu","bgeu"};
          if (nm[F3(x)]) { sprintf(out, "%s x%u, x%u, %d", nm[F3(x)], RS1(x), RS2(x), imm_b(x)); return; } }
        break;
```

（移位指令的 shamt 剛好在 rs2 的位置 bit24..20，所以用 `RS2(x)` 取；srai 的 imm[11:5] = 0x20 剛好在 F7 的位置。）

怎麼驗證：用 GNU as 產生機器碼（6.3.4 的指令），丟進 `disasm` 比對。成功的樣子（本章實測）：

```text
  ext 007342b3  xor x5, x6, x7
  ext 0ff37293  andi x5, x6, 255
  ext 00331293  slli x5, x6, 3
  ext 40335293  srai x5, x6, 3
  ext 0062c863  blt x5, x6, 16
  ext 006289e3  beq x5, x6, 2066
  ext 344120ef  jal x1, 74564
  ext 40118233  sub x4, x3, x1
rv32_encode_decode: ALL PASS
```

### 6.4.6 模擬器加指令

改哪些行：`rv32_encode_decode.c:87` 的 `case OP_IMM` 換成（本章在副本實測）：

```c
    case OP_IMM: {
        uint32_t im = (uint32_t)imm_i(x), sh = im & 31;
        switch (F3(x)) {
        case 0: c->x[rd] = a + im; break;                                 /* addi */
        case 1: c->x[rd] = a << sh; break;                                /* slli */
        case 2: c->x[rd] = (int32_t)a < (int32_t)im; break;               /* slti */
        case 3: c->x[rd] = a < im; break;                                 /* sltiu */
        case 4: c->x[rd] = a ^ im; break;                                 /* xori */
        case 5: c->x[rd] = F7(x) == 0x20 ? (uint32_t)((int32_t)a >> sh) : a >> sh; break; /* srai / srli */
        case 6: c->x[rd] = a | im; break;                                 /* ori */
        case 7: c->x[rd] = a & im; break;                                 /* andi */
        }
        break; }
```

重點：`slti` 用有號比較、`sltiu` 用無號比較（但 imm 先符號延伸再當無號，這是規格）；`srai` 要轉 `int32_t` 才是算術右移；位移量只取低 5 位。OP（R 型）照同樣方式加 `and/or/xor/sll/srl/sra/slt/sltu`；分支加 `blt/bge`（有號）`bltu/bgeu`（無號）。

怎麼驗證：寫一段 3 條指令的程式跑完看暫存器。成功的樣子（本章實測：`addi x5,x0,-16; srai x5,x5,3; andi x6,x5,255`）：

```text
  sim ext: x5=-2 x6=0xfe
rv32_encode_decode: ALL PASS
```

### 6.4.7 寫一個組語函式給 C 呼叫（含 Zbb 版）

題目長這樣：「用 RISC-V 組語寫 `uint32_t asm_max_u32(const uint32_t *a, uint32_t n)`，回傳陣列最大值。」

改哪些行：在 `asm_examples.S` 最後加（或另開 `.S`），複製 `asm_sum_u32` 的骨架（本章實測）：

```asm
# uint32_t asm_max_u32(const uint32_t *a, uint32_t n)：陣列最大值（n==0 回傳 0）
    .text
    .globl asm_max_u32
asm_max_u32:
    li   t0, 0              # t0 = 目前最大值
    beqz a1, 9f
1:  lw   t1, 0(a0)
#ifdef __riscv_zbb
    maxu t0, t0, t1         # Zbb：一條指令取無號最大
#else
    bgeu t0, t1, 2f         # t0 >= t1 就不換
    mv   t0, t1
2:
#endif
    addi a0, a0, 4
    addi a1, a1, -1
    bnez a1, 1b
9:  mv   a0, t0
    ret
```

C 端：`uint32_t asm_max_u32(const uint32_t *a, uint32_t n);`，測試資料要包含 `0x80000000` 以上的值（測無號比較）。

怎麼驗證：兩種 `-march` 各編一次跑 qemu（6.3.6 的指令）。成功的樣子（本章實測，資料 `{3, 0x80000000, 7, 0xFFFFFFF0, 5}`）：

```text
[rv32imac_zicsr_zifencei]
max5=0xFFFFFFF0 max0=0 max3=0x80000000
my_test: PASS
[rv32imac_zicsr_zifencei_zba_zbb_zbs_zbkb]
max5=0xFFFFFFF0 max0=0 max3=0x80000000
my_test: PASS
```

如果有號最大值：`bgeu` → `bge`、`maxu` → `max`。

### 6.4.8 BNN（XNOR-popcount）在 Pico 上加速

題目長這樣：「Pico 上跑二值神經網路內積，要更快。」

- C 寫法（任何平台）：`2 * __builtin_popcount(~(w ^ x)) - 32`，配合 Hazard3 的 `-march` 會編成 `xnor`/`cpop`（`bitops.h:42`、速查表 `:90`）。演算法本身見第 5 章 `algo/bnn.c`。
- 組語寫法：直接用 `asm_bnn_dot`（`asm_examples.S:80-107`）。
- 怎麼驗證：`asm_test.c:67-70` 的 3 個 CHECK（一般、全同 = +32n、全反 = −32n）。
- 在 Cortex-M33 上沒有 `cpop`；`__builtin_popcount` 會變成軟體實作。RISC-V 和 ARM 誰快，本章沒有在板子上量 ⚠️未驗證。

## 6.5 效能：量測方法與實測數字

本章的程式都是「正確性」範本，沒有計時程式。這個容器沒有 Pico 2，qemu 的執行時間不代表硬體，所以**沒有實測 RISC-V 上的執行時間**。

能確定的是「指令數」（從 objdump 數，本章實測）：

| 寫法 | 每個 word 的指令數 | 來源 |
|---|---|---|
| `asm_popcount_array_base` | 外層 5 條 + 每個 1 位元 4 條（`beqz/addi/and/addi` + `j`，實際 5 條含 `j`） | `-march=rv32i` 的 objdump |
| `asm_popcount_array_fast`（Zbb） | 6 條（`lw/cpop/add/addi/addi/bnez`），和 1 的個數無關 | 6.3.5 的 objdump |
| `POPCOUNT(x)`（Zbb） | 1 條 `cpop` | 6.3.7 |
| `brev8()` C 版 | 約 30 條（objdump 實數：`f_brev8` 從 0x34 到 0x88，共 34 條） | 本章 `zbbcheck.c` |
| `__builtin_riscv_brev8()` | 1 條 | 本章 `b8.c` |

要在 Pico 上量：用 `pico/timing.h`（見第 3 章 3.3），重複呼叫上萬次取平均。

## 6.6 限制、已知問題、沒驗證的地方

1. **已知問題 7（核對屬實）**：`bitops.h:30-33` `sign_extend(v, 0)` 和 `bitops.h:83` `bitrev_n(x, 0)` 會位移 32 位，是 C 的未定義行為，檔案沒有註明。UBSan 實測報 `bitops.h:32:24`、`32:31`、`83:73` 三處 `shift exponent 32 is too large`。`-O2` 下 x86 實際回傳 `5` 和 `0xA0000000`（等於沒位移）。同類問題：`sign_extend(v, bits)` 的 bits > 32、`GET_FIELD` 的 hi < lo 或 lo ≥ 32、`BIT(n)` / `TEST_BIT(x,n)` 的 n ≥ 32、`rv32_encode_decode.c:18` 的 `sext(v, 0)`、`packet_fields.c:23` 的 `M(32)`。修法（沒有改程式）：呼叫端保證寬度 1～32；或在函式內 `if (bits <= 0) return 0; if (bits >= 32) return (int32_t)v;`。
2. **已知問題 8（核對屬實）**：`README.md:43` 寫「bitops.h（另寫測試）」，但 repo 裡沒有這個測試檔（`ls bits-riscv/` 只有 8 個檔）。本章 6.3.1 補了一份 `bitops_selftest.c`（host、UBSan、rv32 qemu 都 PASS），沒有放進 repo。
3. **已知問題 10（RISC-V 部分，核對 SDK 原始碼）**：
   - SDK 2.1.1 與 2.2.0：`cmake/preload/toolchains/pico_riscv_gcc.cmake:5` 固定 `-march=rv32imac_zicsr_zifencei_zba_zbb_zbs_zbkb -mabi=ilp32`，沒有 `-mstrict-align`；`pico_riscv_gcc_zcb_zcmp.cmake:8` 是 `rv32ima_zicsr_zifencei_zba_zbb_zbs_zbkb_zca_zcb_zcmp`。預設 GCC triple 是 `riscv32-unknown-elf riscv32-corev-elf`；本容器的是 `riscv64-unknown-elf`，要 `-DPICO_GCC_TRIPLE=riscv64-unknown-elf`（`util/pico_arm_gcc_common.cmake:6-15`）。
   - SDK 2.3.x（`$S/sdk/pico_riscv_gcc.cmake`）：`:5-8` 預設加 `-mstrict-align`（`-DPICO_NO_STRICT_ALIGN=1` 關掉）；`:11-14` 依序試 `-mcpu=hazard3-rp2350` → `rv32ima_…_zca_zcb_zcmp` → `rv32imac_…_zbkb`，用 `:18-21` 的測試檔確認編譯器支援。「2.3.1 起」這個版本號依審查紀錄，本章只有 2.3.x 片段，沒有逐版比對 ⚠️未驗證。
   - 本容器的 gcc 13.2：`-mcpu=hazard3-rp2350` 報 `unknown CPU`、`zcmp` 報 `unknown prefixed ISA extension`（實測）→ 2.3.x 會退到第三個候選，和 2.2.0 一樣。
   - `-mstrict-align` 的影響：gcc 13.2 的 `-Q --help=target` 顯示 `-mstrict-align [enabled]` 已經是預設；`memcpy` 讀 4 個未對齊 byte 在預設、`-mstrict-align`、`-mno-strict-align` 三種下產生**相同**的逐 byte 程式碼（實測）。新版 gcc 搭配 `-mcpu=hazard3-rp2350` 時差異可能不同 ⚠️未驗證。Hazard3 對未對齊存取的硬體行為本章沒有查 datasheet ⚠️未驗證。結論：**讀線上資料一律用 `load_be32/load_le32` 逐 byte 組合**，不受這些旗標影響。
4. **`disasm()` / `step()` 不看 funct7（本章發現）**：`rv32_encode_decode.c:60` 和 `:86` 只判斷 `F3(x) == 0`、`F7(x) == 0x20` 就當 `sub`，其他 funct7 一律當 `add`。M 擴充的 `mul x3,x1,x2`（GNU as 實測 `0x022081b3`，funct7 = 0x01）會被印成 `add x3, x1, x2`（本章實測）、模擬成加法。題目只要 RV32I 就沒影響；要支援 M 時先判斷 `F7(x) == 0x01`。`:69`/`:95` 的 `jalr` 也沒檢查 funct3 = 0。
5. 模擬器 `ld32/st32`（`:78-79`）不檢查越界；pc 跑出 `mem` 會讀到陣列外。
6. `bitstream.c:28` 註解說 `write_msb` 前 buf 要先清 0，實際上函式會設或清每個寫到的位元（`:33-34`、`:54-55`），只有沒寫到的位元需要先清。不是 bug，只是說法比需要的保守。
7. `asm_examples.S:3` 的 `-march` 字串（`rv32imac_zba_zbb_zbs`）和 README `:30` 不同。兩個都能組譯（實測）；以 README 和 SDK 的為準。
8. `rv32_asm_cheatsheet.md:69` 的「RP2350 datasheet 3.8 節」和 `h3.bextm` 的編碼，本章沒有對照 datasheet ⚠️未驗證。擴充清單和 SDK 2.3.x 的 `-march` 一致。
9. 全部程式沒有在 Pico 2 實機上跑過；RISC-V 只在 qemu-riscv32 上跑過。Pico SDK + RISC-V 的完整 build 在本容器因為沒有 newlib 失敗（6.3.6）。

## 6.7 一頁速查表

位元操作：

| 要做什麼 | 寫法 |
|---|---|
| 取出 [hi:lo] | `GET_FIELD(x, hi, lo)` = `(x >> lo) & MASK(hi-lo+1)` |
| 放入 [hi:lo] | `x = SET_FIELD(x, hi, lo, v)` |
| 第 n 位 | `TEST_BIT(x, n)`；設 / 清 / 反：`x = SET_BIT/CLR_BIT/TOGGLE_BIT(x, n)` |
| 有號欄位 | `sign_extend(v, 寬度)`，寬度 1～32 |
| 1 的個數 | `POPCOUNT(x)`（Zbb → `cpop`） |
| 最高的 1 在哪 | `31 - clz32(x)`（x ≠ 0） |
| byte 順序顛倒 | `bswap32(x)`（Zbb → `rev8`） |
| 大端讀 / 寫 | `load_be32(p)` / `store_be32(p, v)` |
| 小端讀 / 寫 | `load_le32(p)` / `store_le32(p, v)` |
| 位元流 | `BitStream s = {buf, 0}; read_msb(&s, n)` 或 `read_lsb(&s, n)` |
| 跨 word（LSB-first） | `get_bits_words(w, pos, n)`，陣列多留 1 個 word |

RISC-V 格式：

| 格式 | imm 怎麼放 | 編碼函式 | 解碼函式 |
|---|---|---|---|
| R | 無 | `enc_r(f7, rs2, rs1, f3, rd, op)` | `F7/RS2/RS1/F3/RD` |
| I | [31:20] = imm[11:0] | `enc_i(imm, rs1, f3, rd, op)` | `imm_i` |
| S | [31:25]=imm[11:5]、[11:7]=imm[4:0] | `enc_s(imm, rs2, rs1, f3, op)` | `imm_s` |
| B | [31]=12、[30:25]=10:5、[11:8]=4:1、[7]=11 | `enc_b(imm, rs2, rs1, f3, op)` | `imm_b` |
| U | [31:12]=imm[31:12] | `enc_u(高20位, rd, op)` | `imm_u`（已 <<12） |
| J | [31]=20、[30:21]=10:1、[20]=11、[19:12]=19:12 | `enc_j(imm, rd, op)` | `imm_j` |

指令（全部在本章實測過）：

| 目的 | 指令（在哪個資料夾） |
|---|---|
| PC 測 C 檔 | `gcc -O2 -Wall -Wextra bitstream.c -o /tmp/bs && /tmp/bs`（`bits-riscv/`） |
| 看組語的機器碼 | `riscv64-unknown-elf-gcc -march=rv32imac_zicsr_zifencei_zba_zbb_zbs_zbkb -mabi=ilp32 -c asm_examples.S -o /tmp/a.o && riscv64-unknown-elf-objdump -d /tmp/a.o` |
| GNU as 對答案 | `echo "addi x1, x0, 5" \| riscv64-unknown-elf-as -march=rv32i - -o /tmp/x.o && riscv64-unknown-elf-objdump -d -M no-aliases,numeric /tmp/x.o` |
| qemu 跑 RISC-V C 程式 | `riscv64-unknown-elf-gcc -march=… -mabi=ilp32 -O2 --specs=picolibc.specs -nostartfiles 你的.c linux_shim.c -o x.elf && qemu-riscv32 ./x.elf` |
| 測 UB | `gcc -O1 -fsanitize=undefined …` |

常見錯誤：

| 症狀 | 一句話修法 |
|---|---|
| 位移 32 / 寬度 0 | 呼叫前保證寬度 1～32 |
| 線上 byte 順序反 | 用 `load_be32/store_be32`，不要 `memcpy` |
| MSB/LSB 讀反 | 手算第一個欄位決定順序 |
| 分支偏移差 4 | 偏移相對本指令 |
| `extension 'zbb' required` | `-march` 加 `_zbb` 或用 `#ifdef __riscv_zbb` |
| qemu segfault | `-nostartfiles` + `linux_shim.c` |
| `mul` 被當 `add` | 判斷 `F7(x) == 0x01` |
