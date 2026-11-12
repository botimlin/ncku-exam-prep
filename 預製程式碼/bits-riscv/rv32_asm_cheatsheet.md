# RV32 組合語言速查（RP2350 的 Hazard3 核心）

## 1. 暫存器與呼叫慣例（ABI）
| 名字 | 編號 | 用途 | 呼叫別人後還在嗎？ |
|---|---|---|---|
| zero | x0 | 永遠是 0，寫進去也沒用 | - |
| ra | x1 | 回傳位址（call 會寫它） | 不會（要自己存） |
| sp | x2 | 堆疊指標，**永遠 16 byte 對齊** | 會 |
| gp / tp | x3 / x4 | 全域 / 執行緒指標，別動 | - |
| t0-t2, t3-t6 | x5-7, x28-31 | 暫時用，隨便用 | 不會 |
| s0-s1, s2-s11 | x8-9, x18-27 | 要保留的變數（s0 = fp） | **會**：你用了就要先存後還 |
| a0-a1 | x10-11 | 參數 1-2 **和回傳值** | 不會 |
| a2-a7 | x12-17 | 參數 3-8 | 不會 |

- 超過 8 個參數 → 放堆疊。64 位元回傳值 → a0（低 32）+ a1（高 32）。
- 「葉函式」（不呼叫別人）通常只用 a/t 暫存器，連堆疊都不用開。
- 會呼叫別人 → 開堆疊存 ra（和用到的 s 暫存器），範例見 `asm_examples.S` 的 `asm_apply`。

## 2. 常用偽指令（組譯器幫你展開）
| 偽指令 | 實際上 | 意思 |
|---|---|---|
| `li rd, imm` | lui + addi | 載入常數 |
| `la rd, sym` | auipc + addi | 載入位址 |
| `mv rd, rs` | addi rd, rs, 0 | 複製 |
| `not rd, rs` | xori rd, rs, -1 | 反相 |
| `neg rd, rs` | sub rd, x0, rs | 取負 |
| `seqz / snez rd, rs` | sltiu / sltu | ==0 → 1 / !=0 → 1 |
| `j lbl` | jal x0, lbl | 跳（不存回傳位址） |
| `call f` | auipc ra + jalr ra | 呼叫函式 |
| `tail f` | auipc + jalr x0 | 尾呼叫 |
| `ret` | jalr x0, 0(ra) | 回去 |
| `beqz / bnez rs, l` | beq/bne rs, x0, l | 等於 / 不等於 0 跳 |
| `bgt / ble a, b, l` | blt / bge b, a, l | 交換運算元 |
| `nop` | addi x0, x0, 0 | 什麼都不做 |

## 3. 載入 / 儲存大小
| 指令 | 大小 | 說明 |
|---|---|---|
| `lb` / `lbu` | 1 byte | lb 符號延伸，lbu 補 0（**讀 uint8_t 用 lbu！**） |
| `lh` / `lhu` | 2 byte | 同上 |
| `lw` | 4 byte | |
| `sb` / `sh` / `sw` | 1 / 2 / 4 byte | 存低幾個 byte |
- 寫法 `lw t0, 8(a0)` = t0 = *(a0 + 8)，位移是 **byte**，陣列第 i 個 = `i*4`。
- 比較：`blt/bge` 有號，`bltu/bgeu` 無號。右移：`srl` 補 0，`sra` 補符號位。
- M 擴充：`mul`、`mulh/mulhu`（乘積高 32 位）、`div/divu`、`rem/remu`。

## 4. 在 .S 檔寫一個 C 可以呼叫的函式
```asm
    .text
    .globl my_add3          # 讓 C 看得到
my_add3:                    # uint32_t my_add3(uint32_t a, uint32_t b, uint32_t c)
    add  a0, a0, a1
    add  a0, a0, a2         # 結果放 a0
    ret
```
C 端：`uint32_t my_add3(uint32_t a, uint32_t b, uint32_t c);` 宣告後直接呼叫。
檔名用大寫 `.S` 才能用 `#ifdef __riscv_zbb`。區域標籤 `1:` 配 `1b`（往回）/`1f`（往前）。

## 5. C 裡面的 inline asm
```c
uint32_t r;
asm volatile("add %0, %1, %2" : "=r"(r) : "r"(a), "r"(b));      // 輸出 : 輸入
asm volatile("addi %0, %0, 1" : "+r"(r));                       // "+r" 又讀又寫
asm volatile("slli %0, %1, %2" : "=r"(r) : "r"(a), "i"(3));     // "i" = 常數
asm volatile("sw %1, 0(%0)" :: "r"(p), "r"(v) : "memory");      // 動到記憶體 → 加 "memory"
```
`%0 %1 ...` 依「輸出再輸入」的順序編號。`volatile` = 不准編譯器刪掉或搬走。

## 6. Hazard3 有的位元操作擴充（RP2350 datasheet 3.8 節）
Hazard3 = **RV32IMAC + Zba + Zbb + Zbs + Zbkb + Zcb + Zcmp + Zicsr**（另有自訂 Xh3bextm 等）。
**沒有 Zbc / Zbkc → 沒有 `clmul`**，CRC 要用查表或逐位元迴圈。
gcc 13 用：`-march=rv32imac_zicsr_zifencei_zba_zbb_zbs_zbkb -mabi=ilp32`
（以下全部已用這個 -march 組譯驗證過）

| 指令 | 擴充 | 意思（C 寫法） |
|---|---|---|
| `cpop rd, rs` | Zbb | popcount(rs)，數 1 的個數 |
| `clz / ctz rd, rs` | Zbb | 前導 0 / 尾端 0 個數（rs=0 → 32） |
| `rev8 rd, rs` | Zbb | byte 順序顛倒 = bswap32（endian 互換） |
| `orc.b rd, rs` | Zbb | 每個 byte：非 0 → 0xFF，0 → 0x00（找字串結尾） |
| `andn / orn / xnor` | Zbb | a & ~b / a \| ~b / ~(a ^ b) |
| `min / max / minu / maxu` | Zbb | 有號 / 無號 最小最大 |
| `sext.b / sext.h / zext.h` | Zbb | 8 / 16 位元符號延伸、16 位元補 0 |
| `rol / ror / rori` | Zbb | 循環左移 / 右移 |
| `sh1add / sh2add / sh3add rd, a, b` | Zba | (a<<1)+b / (a<<2)+b / (a<<3)+b，算陣列位址 |
| `bset / bclr / binv rd, rs, n` | Zbs | rs \| (1<<n) / rs & ~(1<<n) / rs ^ (1<<n)；有 `bseti` 等立即數版 |
| `bext rd, rs, n` | Zbs | (rs >> n) & 1 |
| `pack rd, a, b` | Zbkb | (b[15:0] << 16) \| a[15:0] |
| `packh rd, a, b` | Zbkb | (b[7:0] << 8) \| a[7:0] |
| `brev8 rd, rs` | Zbkb | 每個 byte 內部位元反轉 |
| `zip / unzip rd, rs` | Zbkb | 交錯：低半與高半的位元互相穿插 / 反過來拆開 |
| `h3.bextm` | Xh3bextm | (rs1 >> rs2) & 1~8 位遮罩（自訂指令，要用 `.insn`，見 datasheet） |
- C 內建函式會自動變成這些指令（有開 -march）：`__builtin_popcount`→cpop、`__builtin_clz`→clz、`__builtin_bswap32`→rev8。
- 在 C/組語裡判斷：`#ifdef __riscv_zbb`、`__riscv_zba`、`__riscv_zbs`、`__riscv_zbkb`。

## 7. 指令格式（編碼用，詳見 rv32_encode_decode.c）
opcode：LUI 0x37、AUIPC 0x17、JAL 0x6F、JALR 0x67、BRANCH 0x63、LOAD 0x03、STORE 0x23、OP-IMM 0x13、OP 0x33。
funct3：add/sub/addi=0、sll=1、slt=2、sltu=3、xor=4、srl/sra=5、or=6、and=7；beq=0 bne=1 blt=4 bge=5 bltu=6 bgeu=7；lb=0 lh=1 lw=2 lbu=4 lhu=5。
funct7：sub / sra = 0x20，其他 0。srai 是 imm[11:5]=0x20。
