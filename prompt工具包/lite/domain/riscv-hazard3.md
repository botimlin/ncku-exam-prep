# RISC-V（RP2350 Hazard3）與 C 位元操作速查

- 用途：第二大題（組語 / 位元操作 / 最佳化）精簡參考
- 適用版本：RP2350 Hazard3、pico-sdk、GCC 14
- 來源：RP2350 datasheet §2.1.3、§3.8 https://datasheets.raspberrypi.com/rp2350/rp2350-datasheet.pdf ；github.com/Wren6991/Hazard3 ；github.com/raspberrypi/pico-sdk ；RISC-V psABI
- 最後更新：2026-11

## ISA
- 旗標依 SDK 版本（`build/generated/pico_base/pico/version.h`）：2.2.0 預設 `-march=rv32imac_zicsr_zifencei_zba_zbb_zbs_zbkb -mabi=ilp32`，`-DPICO_COMPILER=pico_riscv_gcc_zcb_zcmp` 才用 `…_zca_zcb_zcmp`；2.3.x 自動依序試 `-mcpu=hazard3-rp2350` → `…_zcb_zcmp` → rv32imac（硬體支援 Zcb/Zcmp）
- 無 FPU（float 軟體模擬）、無 Zbc、無 Zicond。自訂：Xh3bextm、Xh3power、Xh3irq、Xh3pmpm
- 非對齊 load/store 直接例外（mcause 4/6）；`-mstrict-align` SDK 2.3.1 起才預設加（2.2.0、2.3.0 沒加）→ packed struct/指標轉型自己避免（轉型加了也會 trap）

## ABI
- a0–a7 參數，a0（/a1）回傳；uint64 用 a0 低 a1 高
- callee-saved：s0–s11、sp；其餘（ra、t*、a*）caller-saved；gp/tp 勿動
- sp 16-byte 對齊；用 s 暫存器或 call 前要存 ra/s*
- imm：I/S 12-bit 有號（-2048～2047）、shamt 0～31、B ±4KiB、J ±1MiB、lui/auipc 20-bit
- `li` 若低 12 位 ≥0x800，lui 要 +1（addi 正負號擴展）
- lb/lh 正負號擴展、lbu/lhu 零擴展；lh/lw 需 2/4-byte 對齊
- pseudo：mv=addi 0、not=xori -1、neg=sub x0、seqz=sltiu 1、snez=sltu x0、j=jal x0、ret=jalr x0,0(ra)、call=auipc+jalr、bgt/ble 交換運算元
- 無旗標：64 位元加法進位用 `sltu t0,lo,b_lo`
- div 除 0 不 trap（商 -1、餘=被除數）

## 週期（無 bus stall）
- ALU、Zba/Zbb/Zbs/Zbkb、mul、mulh*：1
- load：1；下一條用結果 +1（load→store 資料不算；load→load 位址算）
- div/rem 18～19；分支預測對 1、錯 2；jal/jalr 2；跳到未對齊 32-bit 指令 +1
- 預測：只記最後一個 taken 的向後分支，其他預測不跳
- 3 級管線 F/X/M，完整 bypass
- 迴圈本體只有 1 條 16-bit 指令時預測器失效 ⚠️未查證 → `.option norvc` + `.p2align 2`
- 反組譯看到 cm.push/cm.popret（Zcmp）屬正常：zcb_zcmp 工具鏈，或 SDK 2.3.x + 支援 Zcmp 的 gcc

## 位元指令（1 cycle）
| 指令 | 語意 / 取代 |
|---|---|
| andn/orn/xnor | a&~b、a\|~b、~(a^b) |
| clz/ctz/cpop | __builtin_clz/ctz/popcount（clz/ctz(0)→32；builtin_clz/ctz(0) 為 UB） |
| min/max(u) | 三元運算 |
| sext.b/h、zext.h | (int8_t)、(int16_t)、(uint16_t) 轉型 |
| rol/ror/rori | `(x<<n)\|(x>>(-n&31))` |
| rev8 | __builtin_bswap32 |
| orc.b | 非零 byte→0xFF（找 0 byte） |
| sh1/2/3add rd,i,b | (i<<k)+b：陣列索引、×3/5/9 |
| bset/bclr/binv/bext(+i) | x\|(1u<<n)、x&~、x^、(x>>n)&1 |
| pack / packh | {b[15:0],a[15:0]} / {b[7:0],a[7:0]} |
| brev8 | 每 byte 內位元反轉；brev8+rev8 = 32 位元反轉 |
| zip/unzip | 低/高半交錯到偶/奇位元，及反向 |

## inline asm / .S
```c
asm("clz %0,%1":"=r"(r):"r"(x));
asm volatile("csrci mcountinhibit, 5"); // 開 mcycle/minstret（預設停）
asm volatile("csrr %0, mcycle":"=r"(t));
```
- `"+r"` 讀寫、`"=&r"` early-clobber、`"I"` 12-bit imm、`"K"` 5-bit CSR imm；改記憶體加 `"memory"`
- 無 `time` CSR；64 位元讀 mcycleh→mcycle→mcycleh 重試
```asm
    .section .time_critical.f,"ax"   // SRAM；flash 用 .text.f
    .globl f
    .type f,@function
    .p2align 2
f:  ...
    ret
    .size f,.-f
```

## pico-sdk
- `-DPICO_PLATFORM=rp2350-riscv`；`PICO_TOOLCHAIN_PATH`；triple riscv32-pico-elf / riscv32-unknown-elf 等
- Release 預設；Debug 為 -Og
- `pico_add_extra_outputs()` 產生 .dis；`objdump -d [-M no-aliases]`
- 放 SRAM：`__not_in_flash_func(f)`、`__time_critical_func(f)`；或 `pico_set_binary_type(t copy_to_ram)`
- 原子別名：+0x1000 XOR、+0x2000 SET、+0x3000 CLR（SIO 不支援）；`hw_set_bits/hw_clear_bits/hw_xor_bits`
- AMO / lr/sc 只在主 SRAM 有效
- `hw_write_masked` 先讀再 XOR，同一批位元並行修改仍不安全

## C 技巧
- 2 的冪 `x&&!(x&(x-1))`；最低位 1 `x&-x`；清最低位 1 `x&(x-1)`
- 取欄位（w<32）`(x>>l)&((1u<<w)-1)`；寫欄位 `(x&~m)|((v<<l)&m)`
- 正負號擴展 w 位：`m=1u<<(w-1); (v^m)-m`
- 無分支選擇（c 為 0/1）`b^((a^b)&-(uint32_t)c)`

## UB / 陷阱
- 移位 ≥32 或負數、`1<<31`（int）、有號溢位：UB → 用 `uint32_t`、`1u`
- 提升：`~(uint8_t)` 變 int；`(uint32_t)b<<24`；`(uint32_t)x*x`
- `x & 0xF == 0` 優先序錯
- MMIO 用 `volatile`（不保證原子）
- 非對齊指標轉型會 trap → memcpy

## 最佳化
1. 先 mcycle 量（扣空測、多次取最小）
2. 熱點放 SRAM
3. load 與使用間插無關指令
4. 展開 + 多累加器，用結束指標比較
5. 用 Zba/Zbb/Zbs 取代序列；迴圈內避 div/rem 與 float
6. objdump 確認；比對輸出正確性（0、0xFFFFFFFF、0x80000000、n=0/1）
