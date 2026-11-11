# 貼上卡：RISC-V（RP2350 Hazard3）與 C 位元操作
> 用法：一次只複製一張卡（兩條分隔線之間），貼進對話，再在下面寫你的問題。每張 ≤ 1200 字元。
> 來源：full/domain/riscv-hazard3.md、lite/domain/riscv-hazard3.md（詳細版）｜最後更新 2026-11

---

【參考卡｜RISC-V Hazard3 1/8｜ISA 與暫存器 / 呼叫慣例】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
平台：RP2350（Pico 2）的 Hazard3 RISC-V 核心，非 RP2040。
- `-march=rv32ima_zicsr_zifencei_zba_zbb_zbs_zbkb_zca_zcb_zcmp -mabi=ilp32`（GCC 13 以前：`rv32imac_zicsr_zifencei_zba_zbb_zbs_zbkb`）
- 無 F/D（無硬體浮點，float 軟體模擬很慢）、無 Zbc（無 clmul）、無 Zicond、無 V
- 一律小端序；非自然對齊 load/store 直接例外（不是變慢）
暫存器（ILP32）：
- x0=zero 恆 0；x1=ra 返回位址；x2=sp；x3=gp、x4=tp 勿動
- t0–t6（x5–x7、x28–x31）暫存，caller-saved
- s0–s11（x8、x9、x18–x27）callee-saved（s0 也是 fp）
- a0–a7（x10–x17）參數；a0 回傳（64 位元回傳 a0 低、a1 高）
規則：
- 整數參數依序 a0–a7，放不下才上堆疊；窄整數（uint8_t、int16_t）由呼叫端依型別擴展到 32 位元
- uint64_t 用一對暫存器：低 32 位 a0、高 32 位 a1
- 大於 8 bytes 的 struct 以參考傳遞
- sp 進入函式時 16-byte 對齊
- `.S` 函式可隨意用 a0–a7、t0–t6；要用 s0–s11 或呼叫其他函式（會覆蓋 ra）必須先存堆疊、離開前還原
- 壓縮指令大多只能用 x8–x15（s0、s1、a0–a5）

---

【參考卡｜RISC-V Hazard3 2/8｜RV32I 指令、立即值、pseudo】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
平台：RP2350（Pico 2）Hazard3，RV32。
立即值範圍：
- I/S 型 12-bit 有號：-2048～2047；移位 shamt 0～31
- B（條件分支）±4 KiB；J（jal）±1 MiB；lui/auipc 20-bit（左移 12）
- 32 位元常數：addi 的 imm 會正負號擴展，低 12 位 ≥0x800 時 lui 要 +1。`hi=(x+0x800)>>12`，`lo=x-(hi<<12)`
  例：li a0,0x12345fff → `lui a0,0x12346` + `addi a0,a0,-1`
- 沒有 subi（用負 imm）；`andi a0,a0,-16` = 清低 4 位
- sll/srl/sra 只取 rs2[4:0]（移位量 mod 32）
Load/Store：lb/lh 正負號擴展，lbu/lhu 零擴展；lh 需 2-byte、lw 需 4-byte 對齊；無 lwu/ld
無旗標暫存器，64 位元加法（a1:a0）+（a3:a2）：
```asm
add  a0, a0, a2
sltu t0, a0, a2
add  a1, a1, a3
add  a1, a1, t0
```
pseudo：
- mv=addi rd,rs,0；not=xori -1；neg=sub rd,x0,rs
- seqz=sltiu rd,rs,1；snez=sltu rd,x0,rs
- j=jal x0；jr=jalr x0,0(rs)；ret=jalr x0,0(ra)
- call=auipc ra+jalr ra；tail=auipc t1+jalr x0
- bgt/ble/bgtu/bleu a,b → blt/bge/bltu/bgeu b,a（交換運算元）
- zext.b=andi 255；csrr=csrrs rd,csr,x0
M 擴充：除以 0 不 trap（div/divu 回傳全 1，rem 回傳被除數）；INT_MIN/-1 回傳 INT_MIN、餘 0（C 層級仍 UB）
fence 在 Hazard3 是 no-op；寫程式碼到 RAM 後要 fence.i

---

【參考卡｜RISC-V Hazard3 3/8｜Zbb / Zba 位元指令（全部 1 cycle）】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
平台：RP2350（Pico 2）Hazard3，已啟用 Zba、Zbb、Zbs、Zbkb；無 Zbc。
| 指令 | 語意 | 對應 C |
|---|---|---|
| andn/orn/xnor | a&~b、a\|~b、~(a^b) | 同左 |
| clz/ctz | 前導/尾端零數，a=0 回 32 | __builtin_clz/ctz（a=0 在 C 是 UB） |
| cpop | 1 的個數 | __builtin_popcount |
| min/max | 有號 | a<b?a:b（int32_t） |
| minu/maxu | 無號 | 同上（uint32_t） |
| sext.b/sext.h | 從 bit7/bit15 正負號擴展 | (int8_t)、(int16_t) |
| zext.h | 取低 16 位 | (uint16_t)a |
| rol/ror | 循環移 b[4:0] | (x<<n)\|(x>>(-n&31)) |
| rori | 立即值右旋；無 roli，左旋 n = rori 32-n | (a>>7)\|(a<<25) |
| orc.b | 每 byte 非 0→0xFF，0→0x00 | 找 0 byte |
| rev8 | 反轉 4 個 byte | __builtin_bswap32 |
| sh1add/sh2add/sh3add rd,i,base | (i<<1/2/3)+base | 陣列索引；x*3/5/9 用 shNadd x,x,x |
- zext.b 是 pseudo（andi 255）
- GCC 在 -march 含 zbb/zba 且 -O1 以上，通常自動產生上述指令；一律用 objdump 確認
- 若看到冗長移位遮罩序列，檢查 -march 是否真的含 zbb/zbs

---

【參考卡｜RISC-V Hazard3 4/8｜Zbs / Zbkb / 自訂 h3.bextm】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
平台：RP2350（Pico 2）Hazard3。以下全部 1 cycle。
Zbs（單一位元）：
- bset/bseti：a\|(1<<n) ↔ `a | (1u<<n)`
- bclr/bclri：a&~(1<<n) ↔ `a & ~(1u<<n)`
- binv/binvi：a^(1<<n) ↔ `a ^ (1u<<n)`
- bext/bexti：(a>>n)&1 ↔ `(a>>n)&1`
- 暫存器版只取 n[4:0]；bseti 可設 bit 11 以上（ori 的 12-bit imm 做不到，且 ori 會正負號擴展）
Zbkb：
- pack rd,a,b = {b[15:0], a[15:0]} ↔ `(a&0xFFFF)|(b<<16)`
- packh rd,a,b = {16'b0, b[7:0], a[7:0]} ↔ `(a&0xFF)|((b&0xFF)<<8)`
- brev8：每個 byte 內部位元反轉；brev8 + rev8 = 32 位元完整位元反轉（2 條）
- zip：低 16 位放偶數位、高 16 位放奇數位（交錯，Morton code）；unzip 反向
- pack/packh/zip/unzip/brev8 是否自動產生 ⚠️未驗證（需要時用 inline asm）
Xh3bextm（Hazard3 自訂）：
- h3.bextm rd,a,b,n = (a>>b[4:0]) & ((1<<n)-1)，n=1～8；h3.bextmi 為立即值版
- 編譯器不會自動產生，要用 `.insn`；只在真的 RP2350 Hazard3 上可用，要求可攜性或 judge 不在真硬體時不要用
- 一般寫法 srli+andi 2 cycle，h3.bextmi 1 cycle

---

【參考卡｜RISC-V Hazard3 5/8｜指令週期與管線（無 bus stall）】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
平台：RP2350（Pico 2）Hazard3，3 級管線 F/X/M，完整 bypass（連續相依 ALU 每 cycle 1 條）。
| 類別 | cycles |
|---|---|
| ALU、lui/auipc、Zba/Zbb/Zbs/Zbkb | 1 |
| mul、mulh* | 1 |
| div/rem 18～19；divu/remu 18 | |
| lw/lh/lb…；sw/sh/sb | 1 |
| load 結果被下一條使用 | +1（load-use bubble） |
| 條件分支 預測對 / 錯 | 1 / 2 |
| jal、jalr | 2 |
| 跳到未 4-byte 對齊的 32-bit 指令 | +1 |
| CSR 讀寫 | 1 |
| ecall/ebreak 3；mret 2；amo*.w 每次 4 | |
| cm.push/cm.pop | 1+n |
load-use 細節：
- load 資料 → store 資料 不 stall（如 lbu a3 後立刻 sb a3）
- load 資料 → load 位址 會 stall（指標追逐）
分支預測：單一 entry，只記最後一個 taken 的向後分支，其他一律預測不跳。典型迴圈第一次與最後一次各錯一次。
- 陷阱：迴圈本體只有一條 16-bit 指令時預測器失效 → 用 `.option norvc` 強制 32-bit + `.p2align 2`
其他：
- 非對齊 load/store 直接 trap：mcause 4（load）/ 6（store/AMO）；pico-sdk 預設加 `-mstrict-align`
- 無 FPU：float/double 呼叫軟體函式（如 __mulsf3），極慢 → 改定點數
- 表格假設無 bus stall；在 flash（XIP，0x10000000 起）執行或與 DMA/另一核搶同 SRAM bank 時會更慢
- 反組譯看到 cm.push/cm.popret（Zcmp）屬正常

---

【參考卡｜RISC-V Hazard3 6/8｜cycle 計數（mcycle）】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
平台：RP2350（Pico 2）Hazard3。
- `mcountinhibit` 重置值 0x5（bit0 CY、bit2 IR 為 1 = 停止）。pico-sdk 不會幫你清 → 不清就永遠讀到 0 或不變
- 開啟：`csrci mcountinhibit, 5`（mcycle + minstret 都開），或 `csrci mcountinhibit, 1`（只開 cycle）
- 沒有 `time` CSR（讀了 illegal instruction，mcause 2）；改用 `time_us_32()`
- Debug mode 中計數器不跑，單步除錯量不到真實 cycle
```c
static inline void cycles_enable(void) {
    asm volatile ("csrci mcountinhibit, 5");
}
static inline uint32_t mcycle32(void) {
    uint32_t c;
    asm volatile ("csrr %0, mcycle" : "=r"(c));
    return c;
}
```
pico-sdk 版：
```c
#include "hardware/riscv.h"
riscv_clear_csr(mcountinhibit, 5);
uint32_t t0 = riscv_read_csr(mcycle);
```
量測步驟：
1. 先量空測開銷：t0、t1 連讀，overhead = t1 - t0
2. cycles = (t1 - t0) - overhead（無號相減自動處理回繞）
3. 結果要被使用（印出 / 存 volatile），否則可能被優化掉
4. 多跑幾次取最小值或中位數；第一次常因 XIP cache miss 偏慢
- 64 位元：讀 mcycleh → mcycle → mcycleh，兩次 hi 不同就重試
- 150 MHz 下 32 位元 mcycle 約 28.6 秒回繞

---

【參考卡｜RISC-V Hazard3 7/8｜inline asm 與 .S 函式】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
平台：RP2350（Pico 2）Hazard3，GCC。
constraint：`"r"` 輸入、`"=r"` 只寫輸出、`"+r"` 讀寫、`"=&r"` early-clobber、`"i"` 常數、`"I"` 12-bit 有號 imm、`"K"` 5-bit CSR imm；clobber `"memory"`；改到沒列的暫存器要寫進 clobber（如 "t0"）
```c
asm ("clz %0, %1" : "=r"(r) : "r"(x));
asm ("brev8 %0, %1\n\t"
     "rev8  %0, %0" : "=r"(r) : "r"(x));
asm volatile ("" ::: "memory");
```
- 有副作用（CSR、MMIO、計時）一定加 volatile
- 指令必須在 -march 裡，否則報 unrecognized opcode
.S 檔（大寫 .S 才經前處理器）：
```asm
    .section .time_critical.f, "ax"
    .globl   f
    .type    f, @function
    .p2align 2
f:
    ...
    ret
    .size    f, . - f
```
- `.time_critical.*` 放 SRAM；放 flash 用 `.text.f`
- C 端只要宣告原型；CMake `project(xxx C CXX ASM)` 並把 .S 加進 add_executable；C++ 呼叫需 `extern "C"`
- 用 s 暫存器 / call：`addi sp,sp,-16`、`sw ra,12(sp)`、`sw s0,8(sp)`…，離開前反向還原
- C 函式放 SRAM：`__not_in_flash_func(f)` / `__time_critical_func(f)`；整個程式 `pico_set_binary_type(t copy_to_ram)`
- 反組譯：`pico_add_extra_outputs()` 產生 .dis；`objdump -d -M no-aliases` 看真實指令

---

【參考卡｜RISC-V Hazard3 8/8｜C 位元技巧與 UB 陷阱】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
平台：RP2350（Pico 2）Hazard3。一律用 uint32_t、常數加 u。
技巧：
- 2 的冪：`x && !(x & (x - 1))`
- 最低位 1：`x & -x`；清最低位 1：`x & (x - 1)`
- 取欄位（w<32）：`(x >> l) & ((1u << w) - 1)`
- 寫欄位：`m = mask << l; (x & ~m) | ((v << l) & m)`（v 要先 mask）
- w 位正負號擴展：`m = 1u << (w-1); (int32_t)((v ^ m) - m)`
- 無分支選擇（c 為 0/1）：`b ^ ((a ^ b) & -(uint32_t)c)`
- 對齊向上：`(x + a - 1) & ~(a - 1)`
- 有 0 byte：`((x - 0x01010101u) & ~x & 0x80808080u) != 0`
- 例 x=0xA5：x\|(1u<<1)=0xA7、x&~1u=0xA4、(x>>4)&0xF=0xA
UB / 陷阱：
- 移位 ≥32 或負數 UB（硬體 sll 只取低 5 位）；`1 << 31`（int）UB → `1u << 31`
- 有號溢位 UB → 用 uint32_t 運算
- __builtin_clz(0)/ctz(0) UB（硬體回 32）
- 整數提升：`~(uint8_t)a` 變 int；`b << 24`（uint8_t b）要寫 `(uint32_t)b << 24`；`(uint32_t)x * x`
- `x & 0xF == 0` 等於 `x & (0xF == 0)` → 加括號
- 有號負數 `x/4` ≠ `x>>2`
- MMIO 用 volatile（不保證原子）
- 非對齊指標轉型 `*(uint32_t *)(buf + 1)` 會 trap → memcpy
- RISC-V psABI 的 char 為無號
最佳化：先 mcycle 量、熱點放 SRAM、load 與使用間插無關指令、展開＋多累加器、用結束指標比較、迴圈內避 div/rem 與 float；測試邊界 0、0xFFFFFFFF、0x80000000、n=0/1
