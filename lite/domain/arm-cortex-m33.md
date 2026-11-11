# Arm Cortex-M33（RP2350）組語速查

- 用途：備援包；考場用 Arm 核心時取代 riscv-hazard3.md
- 適用版本：RP2350 M33、pico-sdk、arm-none-eabi-gcc 14
- 來源：RP2350 datasheet §3.7（§3.7.4.9 週期）https://datasheets.raspberrypi.com/rp2350/rp2350-datasheet.pdf ；AAPCS32 github.com/ARM-software/abi-aa ；github.com/raspberrypi/pico-sdk
- 最後更新：2026-11

## ISA / 旗標
- SDK：`-mcpu=cortex-m33 -mthumb -march=armv8-m.main+fp+dsp -mcmse -mfloat-abi=softfp`；`PICO_PLATFORM=rp2350-arm-s`（預設，Secure）
- Thumb-2 only；DSP、FPv5 單精度 FPU；double 走 DCP（pico_double）
- 無 popcount/ctz/min/max；ctz=`rbit`+`clz`
- 非對齊 LDR/LDRH 可；LDRD/LDM/周邊非對齊 fault
- 除以 0 → 0；移位量 ≥32 → 0（ASR 補符號）

## AAPCS
- 參數 r0–r3，回傳 r0(/r1)；64-bit 用偶數對 r0:r1/r2:r3
- callee-saved r4–r11、s16–s31；r12=ip 暫存；lr 返回
- sp 8-byte 對齊（push 偶數個暫存器）
- softfp：float 參數在 r0，`.S` 內 `vmov s0,r0`
- char 無號

## 週期（datasheet）
- ALU 1；複雜 Operand2（移位非 LSL#0–3、需移位的立即值）結果延遲 +1，加 S 必 +1
- UBFX/SBFX/BFI、LSL/LSR/ASR/ROR、MOVW、ADDW 無延遲
- LDR 1/暫存器，結果下一條用 +1（LDM 只最後一個）；STR 1
- MUL/MLA/UMULL 1+延遲1；MAC 連鎖累加同暫存器無懲罰
- SDIV/UDIV：n=最高位差，n<0→2，否則 4+⌊n/4⌋（≤11）
- 分支 taken=2+L+U−(K&F)，not-taken=1−F；L=load 分支、U=目標未 word 對齊且為 32-bit、F=可 fold（B/Bcc/BX LR 且前一條 16-bit）、K=0 若條件分支前一條設旗標
- IT 失敗指令 1 cycle；16-bit nop 可 fold → 用 `nop.w`
- FPU：VADD/VMUL 1+1；VFMA/VMLA 3+1；VDIV/VSQRT 14+1；相依鏈改多累加器
- DCP double：dadd 6、dmul 17、ddiv 51（內聯）
- SRAM 執行時 literal 在 PC+8(mod16) 可能 +1；熱點放 SRAM

## 指令
| 指令 | 語意 |
|---|---|
| bic/orn | a&~b、a\|~b |
| ubfx/sbfx #l,#w | 取欄位 |
| bfi/bfc | 寫/清欄位 |
| clz/rbit/rev/rev16/revsh | |
| uxtb/sxth | 轉型 |
| add r0,r1,r2,lsl #2 | 索引 |
| ror | 左旋用 32−n |
| mla/mls/umull/smull/umlal | 乘加/64-bit |
| ssat/usat #n | 夾限 |
| qadd、smlad、uqadd8、usad8、sadd16、sel | DSP |
| ldr r,[p],#4；ldmia r0!,{..}；ldrd | |
| cbz（向前 ≤126）、it、tbb/tbh | |
| movw/movt | 32-bit 常數 |
| adds+adc | 64-bit 加 |

## intrinsic
- `<arm_acle.h>`：`__smlad __qadd __ssat(x,n) __usat __uqadd8 __usad8 __sadd16`
- CMSIS：link `cmsis_core`，`#include "RP2350.h"`：`__SMLAD __CLZ __RBIT __REV __set_BASEPRI`
- SDK `hardware/sync.h`：`__dmb __dsb __isb __nop __wfi __wfe __sev save_and_disable_interrupts`

## inline asm / .S
```c
pico_default_asm("rbit %0,%1":"=r"(r):"r"(x));
// 設旗標/Q 要 "cc"；改記憶體 "memory"；"t"=s 暫存器；"l"=r0–r7
```
```asm
 .syntax unified
 .thumb
 .section .time_critical.f,"ax"
 .global f
 .type f,%function
 .thumb_func
f: push {r4,lr}
 ...
 pop {r4,pc}
 .size f,.-f
```
- 符號 bit0 須為 1（否則 INVSTATE）；註解 `@`

## Cycle counter
```c
#include "hardware/structs/m33.h"
m33_hw->demcr|=M33_DEMCR_TRCENA_BITS;
m33_hw->dwt_cyccnt=0;
m33_hw->dwt_ctrl|=M33_DWT_CTRL_CYCCNTENA_BITS;
uint32_t t=m33_hw->dwt_cyccnt;
```
- 每核各自設定；150MHz 約 28.6s 回繞；SysTick 24-bit 向下

## 中斷
- 硬體推 r0–r3,r12,lr,pc,xPSR → ISR 為普通 C；lazy FP stacking（FPCCR 實際值 ⚠️未驗證）
- 4 優先權位元：0x00 最高…0xF0；SDK 預設 0x80
- PRIMASK(`cpsid i`) 全擋；BASEPRI 擋 ≥ 值者；只擋本核
- tail-chaining、late arrival；EXC_RETURN 在 lr
- fault：`m33_hw->cfsr`（UNALIGNED/NOCP/INVSTATE/DIVBYZERO）、堆疊 [sp+24]=PC
- ldrex/strex 只在 SRAM 有效（strex 回 0=成功）

## RV↔Arm
| | Hazard3 | M33 |
|---|---|---|
| 參數/回傳 | a0–a7/a0 | r0–r3/r0 |
| 保存 | s0–s11 | r4–r11 |
| 計數 | mcycle（清 mcountinhibit） | DWT_CYCCNT |
| sh2add | | add …,lsl #2 |
| cpop | 1 cycle | 無 |
| div | 18–19 | 2–11 |
| 原子 | lr/sc、amo | ldrex/strex |
| 屏障 | fence | dmb/dsb/isb |
| float | 軟體 | FPU |

## 最佳化
1. DWT 量（扣空測、取最小、關中斷）
2. 放 SRAM；`.p2align 2` 迴圈頂
3. load/乘法結果隔一條再用
4. LDM、後索引、展開＋多累加器
5. cmp 與 bne 間塞無關 16-bit 指令（taken 2→1）
6. UBFX/BFI、DSP SIMD、float 不用 double
7. objdump 找 `bl __aeabi_d*`、sdiv、spill；比對輸出
