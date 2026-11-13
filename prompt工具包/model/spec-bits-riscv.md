# 規格卡：bits-riscv/（位元欄位、位元流、RV32 編解碼、組語）
> 用法：一次只複製一張卡（兩條 `---` 之間），貼進對話；模型要看程式時，照卡片最後一行請操作者貼指定行號。每張 ≤ 1200 字元。
> 來源：`預製程式碼/bits-riscv/` 8 個檔、`預製程式碼/說明書/06-bits-riscv.md`｜最後更新 2026-11-13

---

【規格卡｜BITS 1/11｜總覽：bits-riscv/ 8 個檔】
以下是正確的參考資料（預製程式碼 2026-11-13 版）。和你的記憶不同時，以這張為準。
| 檔案 | 行數 | 做什麼 | 題目關鍵字 |
|---|---|---|---|
| `bitops.h` | 97 | 位元巨集 / inline 函式，`#include` 直接用 | mask、欄位、popcount、endian、反轉 |
| `packet_fields.c` | 111 | 規格位元表 → pack/unpack；大小端讀寫；位元重排 | header、bit 31..24、打包 |
| `bitstream.c` | 113 | byte 陣列逐位元讀寫（MSB/LSB-first）、跨 word | 位元流、跨 byte |
| `rv32_encode_decode.c` | 160 | RV32I 編碼、立即值解碼、反組譯、迷你模擬器 | opcode、機器碼、模擬器 |
| `asm_examples.S` | 133 | 7 個 C 可呼叫的組語函式 | 組語函式、cpop、BNN |
| `asm_test.c` | 86 | 測 `.S`（和 C 參考版比對）+ inline asm | |
| `rv32_asm_cheatsheet.md` | 99 | ABI、偽指令、Hazard3 擴充、opcode/funct 表 | 只查不改 |
| `README.md` | 48 | 檔案→題型、位元題 SOP、編譯指令 | |
- `TODO(改這裡)` 共 4 處：`packet_fields.c:5`、`:14`；`rv32_encode_decode.c:56`、`:78`。
- 3 個 `.c` 各有 `main` 自我測試，最後印 `<名稱>: ALL PASS`、回傳 0。`asm_test.c` 只能和 `asm_examples.S` 一起用 RISC-V gcc 編。
- 驗證：host gcc 13.3 全 PASS、0 警告；rv32（gcc 13.2 + picolibc + qemu-riscv32）基本 ISA 版與 Zbb 版全 PASS；機器碼和 GNU as 對過。**沒在 Pico 2 實機跑過**。
- repo 裡沒有 `bitops.h` 的測試檔（`README.md:43` 說的「另寫測試」不在）。
- 鐵律：一律 `uint32_t`；位移量 0～31（`1u << 32` 是未定義行為 UB）；手算 1～2 組寫成 `CHECK`。
要看程式：請操作者貼「cat -n README.md | sed -n 1,27p」

---

【規格卡｜BITS 2/11｜bitops.h 前半：位元、欄位、符號延伸、clz】
以下是正確的參考資料（預製程式碼 2026-11-13 版）。和你的記憶不同時，以這張為準。
bit 0 = LSB，全部 `uint32_t`，沒有 `TODO(改這裡)`。
| 名稱 | 行 | 做什麼 | 邊界 / 注意 |
|---|---|---|---|
| `BIT(n)` | 9 | `1u<<n` | n≥32 是 UB |
| `SET_BIT/CLR_BIT/TOGGLE_BIT(x,n)` | 10-12 | OR / AND NOT / XOR | 回傳新值、不改 x：`x = SET_BIT(x,5);` |
| `TEST_BIT(x,n)` | 13 | `(x>>n)&1u`，0 或 1 | n≥32 是 UB |
| `MASK(w)` | 18 | 低 w 位全 1 | w≥32 → `0xFFFFFFFF`；w=0 → 0 |
| `GET_FIELD(x,hi,lo)` | 20 | 取 [hi:lo]，移到最低位 | 順序 hi 在前；hi<lo 是 UB |
| `SET_FIELD(x,hi,lo,v)` | 22-23 | 清空 [hi:lo] 再放 v | 回傳新值；v 超寬被丟：`(0,7,4,0x1F)` = `0xF0` |
| `COMBINE16(a,b)` | 25 | `(0x12,0x34)` = `0x1234` | a、b 各自 &0xFF |
| `sign_extend(v,bits)` | 30-35 | 有號延伸成 `int32_t` | bits≤0 → 0；bits≥32 → `(int32_t)v`；`(0xFFF,12)` = -1 |
| `popcount32(x)` | 39-43 | 1 的個數 | 可攜迴圈 `x &= x-1` |
| `POPCOUNT(x)` | 44 | `__builtin_popcount` | Zbb 下 = 1 條 `cpop` |
| `clz32/ctz32(x)` | 49-50 | 前導 / 尾端 0 個數 | x=0 → 32（避開 builtin 的 UB） |
- 最高的 1 在第幾位 = `31 - clz32(x)`；x=0 得 -1，先判斷 x≠0。
- 巨集參數會算兩次，不要放 `i++`。
- 陷阱：`SET_BIT(x,3);` 單獨一行 → x 沒變 → 改 `x = SET_BIT(x,3);`。自己寫 `(1u<<32)-1` → UB → 改 `MASK(32)`。
要看程式：請操作者貼「cat -n bitops.h | sed -n 8,51p」

---

【規格卡｜BITS 3/11｜bitops.h 後半：endian、rotate、2 的次方、反轉】
以下是正確的參考資料（預製程式碼 2026-11-13 版）。和你的記憶不同時，以這張為準。
| 名稱 | 行 | 做什麼 | 邊界 / 注意 |
|---|---|---|---|
| `bswap32(x)` | 55-57 | byte 順序顛倒 | `0x11223344` → `0x44332211`；Zbb = `rev8` |
| `bswap16(x)` | 58 | `0x1234` → `0x3412` | |
| `rotl32/rotr32(x,n)` | 62-63 | 循環左 / 右移 | 先 `n &= 31`（n=36 等於 4）；n=0 特判 |
| `is_pow2(x)` | 66 | 2 的次方回 1 | 0 → 0 |
| `round_up_pow2(x)` | 67-72 | 往上取 2^k：5→8、8→8 | 0 → 0；> `0x80000000` 溢位成 0 |
| `ALIGN_UP(x,a)` | 74 | 對齊 a 的倍數：`(13,4)` = 16 | a 必須 2^k：`(7,6)` 得 8 是錯的 |
| `bitrev32(x)` | 78-83 | 32 位左右顛倒 | `0x1` → `0x80000000`；`0x12345678` → `0x1E6A2C48` |
| `bitrev_n(x,n)` | 85 | 只反轉低 n 位 | n≤0 → 0；`(0b0011,4)` = `0b1100`；x 高於 n 的位不影響 |
| `brev8(x)` | 87 | 每個 byte 內部反轉 | `0x01020380` → `0x8040C001`；C 版編成 28 條 |
- RP2350 和 x86 都是小端。
- 要 1 條指令的 brev8：`__builtin_riscv_brev8(x)`（Zbkb）。
- 寬度 0：`sign_extend`、`bitrev_n` 回傳 0（無 UB）。別的檔沒處理：`packet_fields.c:23` 的 `M(32)`、`rv32_encode_decode.c:17` `BITS` 寬 32、`:18` `sext(v,0)` 都是 UB。
- 小技巧（`:89-96` 註解）：`x & -x` 只留最低的 1；`x & (x-1)` 清最低的 1；`popcount(a ^ b)` = 漢明距離；`~(a ^ b)` = XNOR（BNN 用）。
要看程式：請操作者貼「cat -n bitops.h | sed -n 53,97p」

---

【規格卡｜BITS 4/11｜packet_fields.c：規格表 → SHIFT/W、pack、endian】
以下是正確的參考資料（預製程式碼 2026-11-13 版）。和你的記憶不同時，以這張為準。
規格表 → `#define`（`:15-22`；`TODO(改這裡)` 在 `:5`、`:14`）：
```text
bit 31..29 version(3) → VER_SHIFT 29  VER_W 3
bit 28..24 type(5)    → TYPE_SHIFT 24 TYPE_W 5
bit 23..12 length(12) → LEN_SHIFT 12  LEN_W 12
bit 11..0  id(12)     → ID_SHIFT 0    ID_W 12
```
規則：SHIFT = lo；W = hi−lo+1；W 加總 = 32。
| 名稱 | 行 | 做什麼 |
|---|---|---|
| `M(w)` | 23 | `(1u<<w)-1`；w=32 是 UB |
| `pack(h)` | 28-33 | 每欄 `(v & M(W)) << SHIFT` 再 OR |
| `unpack(x)` | 34-41 | `(x >> SHIFT) & M(W)` |
| `set_type(x,t)` | 43-47 | 先清欄位再 OR |
| `HeaderBF` | 53-61 | bitfield 版，不要用 |
| `load_be32/load_le32/load_be16(p)` | 66-68 | 逐 byte 讀 |
| `store_be32/store_le32(p,v)` | 69-70 | 逐 byte 寫 |
| `permute_bits(x,perm,n)` | 73-78 | 輸入 bit i → 輸出 bit perm[i] |
- 測試：`{5,0x13,0x2A0,0xBEE}` → `0xB32A0BEE`（`:88`）。
- 大端上線：`store_be32(buf,pack(h))` → `B3 2A 0B EE`；收 `unpack(load_be32(buf))`。`memcpy` 是小端。
- 欄位數不同 → `Header`（`:25`）、`pack`、`unpack`、`main` 一起改；有 32 位欄位 → 用 `MASK`。
- 陷阱：SHIFT 填成 hi → 錯位 → 改填 lo。規格是「輸出 bit j 取自輸入 bit src[j]」時 `permute_bits` 方向反 → 改寫 `y |= ((x>>src[j])&1u)<<j`。
要看程式：請操作者貼「cat -n packet_fields.c | sed -n 14,47p」

---

【規格卡｜BITS 5/11｜bitstream.c：MSB/LSB-first 讀寫、跨 word】
以下是正確的參考資料（預製程式碼 2026-11-13 版）。和你的記憶不同時，以這張為準。
`BitStream`（`:11-14`）= `{uint8_t *buf; size_t pos;}`，**pos 是位元位置**，初始化 `{buf, 0}`。沒有 `TODO(改這裡)`。
| 函式 | 行 | 順序 | 做法 |
|---|---|---|---|
| `read_msb(s,n)` | 18-27 | MSB-first | bit=7-(pos&7)；先讀的放高位 |
| `write_msb(s,v,n)` | 29-37 | MSB-first | 從 v 的 bit n-1 往下寫 |
| `read_lsb(s,n)` | 40-49 | LSB-first | bit=pos&7；第 i 個讀到的放 bit i |
| `write_lsb(s,v,n)` | 50-58 | LSB-first | 從 v 的 bit 0 往上寫 |
| `get_bits_words(w,pos,n)` | 62-68 | LSB-first | w[idx+1]:w[idx] 拼 64 位，右移 pos%32 再 mask |
- n = 0～32（n=0 回 0）；不檢查越界；自動處理跨 byte / 跨 word。
- write 會設或清寫到的每一位；沒寫到的位要先 `memset(buf,0,…)`。
- `get_bits_words` 一定讀 `w[idx+1]` → 陣列尾巴多留 1 個 0。
- MSB-first：網路協定、影像。LSB-first：deflate/zip、UART/FIFO。
測試（`:77-108`，資料 `A5 3C`）：
```text
read_msb 3,7,6 → 0x5 0x14 0x3C
read_lsb 3,7,6 → 0x5 0x14 0x0F
get_bits_words({0xA0000000,0xB,0},28,8) = 0xBA
```
- word 陣列 MSB-first（pos 0 = w[0] 的 bit31）不能用 `get_bits_words` → 另寫：`two = (uint64_t)w[idx]<<32 | w[idx+1]`，回傳 `(two >> (64-off-n)) & mask`。
- 陷阱：讀出的值位元反過來 → MSB/LSB 用錯，拿題目範例手算決定。重用舊 `BitStream` → pos 沒歸零 → 新資料用新的 `{buf,0}`。
要看程式：請操作者貼「cat -n bitstream.c | sed -n 11,68p」

---

【規格卡｜BITS 6/11｜RV32I 六種格式、B/J 立即值打亂】
以下是正確的參考資料（預製程式碼 2026-11-13 版）。和你的記憶不同時，以這張為準。
位置（`rv32_encode_decode.c:4-11`）：
```text
R: funct7[31:25] rs2[24:20] rs1[19:15] funct3[14:12] rd[11:7] opcode[6:0]
I: [31:20]=imm11:0 rs1 funct3 rd opcode
S: [31:25]=imm11:5 rs2 rs1 funct3 [11:7]=imm4:0 opcode
B: [31]=imm12 [30:25]=imm10:5 rs2 rs1 funct3 [11:8]=imm4:1 [7]=imm11 opcode
U: [31:12]=imm31:12 rd opcode
J: [31]=imm20 [30:21]=imm10:1 [20]=imm11 [19:12]=imm19:12 rd opcode
```
- 符號位都在 bit31。B/J 不存 imm[0]（一定是 0）：B 13 位、J 21 位。偏移相對本指令位址。
B 編碼 `beq x5,x6,+0x812` = `0x006289e3`：
1. 拆：imm12=0 imm11=1 imm10:5=000000 imm4:1=1001
2. 放：bit31←imm12、30:25←imm10:5、11:8←imm4:1、bit7←imm11
B 解碼 `0xfe0598e3`：bit31=1、30:25=111111、11:8=1000、bit7=1 → 拼 imm12,imm11,imm10:5,imm4:1,0 = `1 1 111111 1000 0` = −16。
J 編碼 `jal x1,+0x12344` = `0x344120ef`：imm20=0、imm19:12=00010010、imm11=0、imm10:1=0110100010。`0xffdff06f` = `jal x0,-4`。
- S：`sw x5,-12(x2)` = `0xfe512a23`。
- `li` = `lui+addi`；低 12 位 ≥ 0x800 時 lui +1：`li x6,0x12345fff` → `lui x6,0x12346; addi x6,x6,-1`。
- opcode（`:20-21`）：LUI 37、AUIPC 17、JAL 6F、JALR 67、BRANCH 63、LOAD 03、STORE 23、OP-IMM 13、OP 33（hex）。
要看程式：請操作者貼「cat -n rv32_encode_decode.c | sed -n 4,54p」

---

【規格卡｜BITS 7/11｜rv32_encode_decode.c：函式表】
以下是正確的參考資料（預製程式碼 2026-11-13 版）。和你的記憶不同時，以這張為準。
| 名稱 | 行 | 做什麼 / 注意 |
|---|---|---|
| `BITS(x,hi,lo)`、`sext(v,bits)` | 17-18 | 取欄位、符號延伸 |
| `enc_r(f7,rs2,rs1,f3,rd,op)` | 24-25 | 參數順序 = 機器碼由左到右 |
| `enc_i(imm,rs1,f3,rd,op)` | 26-27 | imm `&0xFFF`，範圍不檢查 |
| `enc_s(imm,rs2,rs1,f3,op)` | 28-30 | |
| `enc_b(imm,rs2,rs1,f3,op)` | 31-34 | imm = byte 偏移（偶數） |
| `enc_u(imm20,rd,op)` | 35 | 吃**高 20 位**：`(0x12345,5,OP_LUI)` = `lui x5,0x12345` |
| `enc_j(imm,rd,op)` | 36-39 | |
| `OPC/RD/F3/RS1/RS2/F7(x)` | 42-47 | 取欄位 |
| `imm_i/imm_s/imm_b/imm_j(x)` | 48-54 | 已符號延伸 |
| `imm_u(x)` | 52 | `x & 0xFFFFF000`（已 <<12） |
| `disasm(x,out)` | 57-75 | 子集反組譯，暫存器印 `x10` |
| `CPU` | 78 | `x[32]`、`pc`、`mem[1024]` |
| `ld32/st32` | 79-80 | 小端 memcpy，本身不檢查 |
| `MEM_OK(c,a)` | 81 | `a <= sizeof mem - 4` |
| `step(c)` | 83-106 | 執行 1 條：0 正常；−1 停機 |
- `main` `:112-160`：13 個編碼 CHECK（期望值 = GNU as）、立即值往返、disasm、模擬 1+…+10 = 55 存 `mem[0x100]`、停在 pc `0x1c`。
- 陷阱：`enc_u` 傳 <<12 後的值 → 多 12 個 0 → 傳高 20 位。解碼負立即值變大正數 → 沒符號延伸 → 用 `imm_*()`。
要看程式：請操作者貼「cat -n rv32_encode_decode.c | sed -n 17,54p」

---

【規格卡｜BITS 8/11｜rv32_encode_decode.c：disasm/step 行為、加指令】
以下是正確的參考資料（預製程式碼 2026-11-13 版）。和你的記憶不同時，以這張為準。
支援子集（disasm `:57-75` 和 step `:83-106` 相同）：add/sub/mul、addi、lw、sw、beq/bne、jal、jalr、lui、auipc。
- OP_OP（`:60`、`:88`）：只收 funct3=0 且 funct7 = 0x00 add、0x20 sub、0x01 mul。其他 funct7（mulh、div…）→ disasm 印 `unknown 0x…`、step 回 −1。
- step 取指令：pc 不符 `MEM_OK` → 當 `0xFFFFFFFF`（停機）。`lw`/`sw` 位址先 `MEM_OK`，超出回 −1。
- `jalr`：先算 `t=(a+imm)&~1` 再寫 rd（rd 可能 = rs1）；沒檢查 funct3。
- 每步最後 `x[0]=0`、`pc=next`。分支偏移相對本指令。
`TODO(改這裡)`：
| 行 | 現在 | 改法 |
|---|---|---|
| `:56` | disasm 只支援子集 | 在對應 opcode 的 case 依 F3/F7 加；step 也要加 |
| `:78` | `mem[1024]` | 程式 > 1 KiB 就改大（例 65536）；很大時 `main` 的 `CPU c`（`:142`）改 `static` |
加指令要點：
- OP-IMM funct3：0 addi、1 slli、2 slti、3 sltiu、4 xori、5 srli/srai（F7=0x20 是 srai）、6 ori、7 andi。shamt = `RS2(x)`（bit24..20）。
- OP funct3：1 sll、2 slt、3 sltu、4 xor、5 srl/sra、6 or、7 and。
- 分支 funct3：0 beq、1 bne、4 blt、5 bge、6 bltu、7 bgeu。
- srai 用 `(int32_t)a >> sh`；slti 有號比較、sltiu 無號；位移量只取低 5 位。
- 驗證：GNU as 產生機器碼丟進 `disasm` 比對；原本 13 個 CHECK 仍要 `ALL PASS`。
要看程式：請操作者貼「cat -n rv32_encode_decode.c | sed -n 56,106p」

---

【規格卡｜BITS 9/11｜asm_examples.S、asm_test.c、呼叫慣例】
以下是正確的參考資料（預製程式碼 2026-11-13 版）。和你的記憶不同時，以這張為準。
ABI：參數 a0～a7，回傳 a0；t0-t6 隨便用；s0-s11 用了要先存後還；ra = 回傳位址；sp 16 byte 對齊。
| 函式 | 行 | 注意 |
|---|---|---|
| `uint32_t asm_sum_u32(const uint32_t *a, uint32_t n)` | 8-18 | 葉函式；n=0 → 0 |
| `asm_memcpy_words(dst,src,n)` | 21-30 | 複製 n 個 word |
| `asm_get_field(x,lo,w)` | 33-40 | w=32 回 0 |
| `asm_popcount_array_base(a,n)` | 43-57 | 只用基本指令 |
| `asm_popcount_array_fast(a,n)` | 60-75 | Zbb 用 `cpop`；否則跳 base |
| `int32_t asm_bnn_dot(w,x,n)` | 80-107 | 2·popcount(XNOR)−32n |
| `asm_apply(f,a,n)`：a[i]=f(a[i]) | 111-133 | 開 16 B 堆疊存 ra、s0-s2 |
- 大寫 `.S` 才能 `#ifdef __riscv_zbb`。`1:` 配 `1b`（往回）/`1f`（往前）。
- `asm_test.c`：宣告 `:8-14`（完整原型）、C 參考版 `:17-24`、inline asm `:29-42`、`main` `:48-86`；印 `(基本 ISA 版本：迴圈 popcount)` 或 `(Zbb 版本：使用 cpop/xnor)`，再 `asm_test: ALL PASS`。
- 加函式：葉函式抄 `asm_sum_u32`，會呼叫別人抄 `asm_apply`；加 `.globl`；`asm_test.c` 加宣告、參考版、CHECK。
- inline：`asm volatile("add %0, %1, %2" : "=r"(r) : "r"(a), "r"(b));`
- 陷阱：少 `.globl` → `undefined reference`。s 暫存器沒還原 → C 變數被改。讀 `uint8_t` 用 `lb` → 負數 → 改 `lbu`。沒 `_zbb` 用 `cpop` → `extension 'zbb' required`。
要看程式：請操作者貼「cat -n asm_examples.S | sed -n 1,40p」

---

【規格卡｜BITS 10/11｜編譯執行：PC、objdump、qemu】
以下是正確的參考資料（預製程式碼 2026-11-13 版）。和你的記憶不同時，以這張為準。
PC（在 `bits-riscv/`，3 個 `.c` 同樣寫法）：
```sh
gcc -O2 -Wall -Wextra packet_fields.c -o /tmp/pf && /tmp/pf
```
成功：最後一行 `packet_fields: ALL PASS`（另兩個是 `bitstream: ALL PASS`、`rv32_encode_decode: ALL PASS`）。
看組語機器碼：
```sh
riscv64-unknown-elf-gcc -march=rv32imac_zicsr_zifencei_zba_zbb_zbs_zbkb -mabi=ilp32 -c asm_examples.S -o /tmp/a.o && riscv64-unknown-elf-objdump -d /tmp/a.o
```
GNU as 對答案（`numeric` = 印 x1 不印 ra）：
```sh
echo "addi x1, x0, 5" | riscv64-unknown-elf-as -march=rv32i - -o /tmp/x.o && riscv64-unknown-elf-objdump -d -M no-aliases,numeric /tmp/x.o
```
qemu 跑 asm_test（`<M>` = `rv32imac_zicsr_zifencei` 或上面的 Zbb 版字串）：
```sh
riscv64-unknown-elf-gcc -march=<M> -mabi=ilp32 -O2 --specs=picolibc.specs -nostartfiles asm_test.c asm_examples.S linux_shim.c -o t.elf && qemu-riscv32 ./t.elf
```
- `linux_shim.c` 不在 repo（全文在說明書 6.3.6）：自寫 `_start`（設 gp、清 .bss、設 sp）、printf 接 Linux `write`。只給 qemu，不放進 Pico 專案。
- 少 `--specs=picolibc.specs` → `stdio.h: No such file`；少 shim → Segmentation fault；.bss 沒清 → 沒 PASS 也沒 FAIL。
- 用 host `gcc` 編 `asm_test.c` 會失敗（`.S` 是 RISC-V）。
要看程式：請操作者貼「cat -n README.md | sed -n 21,48p」

---

【規格卡｜BITS 11/11｜Pico 2、Hazard3 擴充、SDK 的 -march】
以下是正確的參考資料（預製程式碼 2026-11-13 版）。和你的記憶不同時，以這張為準。
Pico 2（沒實測）：`asm_examples.S` 加進 `add_executable(...)`，`PICO_PLATFORM=rp2350-riscv` 編譯，C 端照 `asm_test.c:8-14` 宣告，printf 經 USB/UART。
Hazard3 = RV32IMAC + Zba Zbb Zbs Zbkb Zcb Zcmp Zicsr。**沒有 Zbc → 沒有 `clmul`**（CRC 用查表）。
| 指令 | 擴充 | 意思 |
|---|---|---|
| `cpop`、`clz`/`ctz` | Zbb | popcount；0 → 32 |
| `rev8` | Zbb | bswap32 |
| `xnor`、`andn`、`maxu`、`rol`/`ror` | Zbb | |
| `sh1add`/`sh2add`/`sh3add` | Zba | (a<<k)+b |
| `bset`/`bclr`/`binv`/`bext` | Zbs | 單一位元 |
| `pack`/`packh`/`brev8`/`zip` | Zbkb | `pack a,b` = b 低 16 在高半 |
- 判斷：`#ifdef __riscv_zbb`（`__riscv_zba`、`__riscv_zbs`、`__riscv_zbkb`）。
- `-march`：`rv32imac_zicsr_zifencei_zba_zbb_zbs_zbkb -mabi=ilp32`（gcc 13）。`asm_examples.S:3` 寫的較短字串也能組譯，以 README 為準。
- SDK 2.1.1 / 2.2.0：固定上面那串，沒 `-mstrict-align`；預設 triple 是 `riscv32-unknown-elf`，riscv64 工具鏈加 `-DPICO_GCC_TRIPLE=riscv64-unknown-elf`。
- SDK 2.3.x：預設加 `-mstrict-align`（`-DPICO_NO_STRICT_ALIGN=1` 關掉）；依序試 `-mcpu=hazard3-rp2350` → `rv32ima_…_zca_zcb_zcmp` → 上面那串。gcc 13.2 不認前兩個 → 用第三個。
- 讀線上資料一律 `load_be32/load_le32`（逐 byte），不受對齊旗標影響。
要看程式：請操作者貼「cat -n rv32_asm_cheatsheet.md | sed -n 69,99p」
