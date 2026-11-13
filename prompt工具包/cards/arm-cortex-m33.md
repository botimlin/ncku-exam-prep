# 貼上卡：Arm Cortex-M33（RP2350）組語與位元操作
> 用法（照 `../../考場SOP.md`）：模型寫【要卡】編號時，到 `../編號卡/` Ctrl-F 那個編號複製這張卡，包在 `<<<資料 開始>>>`…`<<<資料 結束>>>` 裡、最後一行寫「繼續」再貼。本檔編號：L07（參考卡 Cortex-M33）。每張 ≤ 1200 字元。
> 來源：full/domain/arm-cortex-m33.md、lite/domain/arm-cortex-m33.md（詳細版）｜最後更新 2026-11

---

【參考卡｜Cortex-M33 1/8｜ISA、旗標與 AAPCS 呼叫慣例】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
平台：RP2350（Pico 2）的 Arm Cortex-M33，非 RP2040（RP2040 是 M0+）。pico-sdk 對 RP2350 預設 `PICO_PLATFORM=rp2350-arm-s`（Secure）。
- 旗標：`-mcpu=cortex-m33 -mthumb -march=armv8-m.main+fp+dsp -mcmse -mfloat-abi=softfp`；工具鏈 arm-none-eabi
- 只有 Thumb-2（16/32-bit 混合）；有 DSP、單精度 FPU（FPv5-SP）；double 由 DCP 協處理器（pico_double）
- 沒有 popcount / ctz / min / max 指令；ctz = rbit + clz
- 非對齊 LDR/LDRH/STR/STRH 在一般記憶體可（較慢）；LDRD/STRD/LDM/STM 與周邊非對齊會 fault
- 除以 0 → 商 0（不 trap）；暫存器移位 ≥32：LSL/LSR → 0、ASR → 全符號位
AAPCS：
- 參數 r0–r3，其餘上堆疊；回傳 r0（64 位元 r0:r1）
- 64 位元參數用偶數號暫存器對：f(uint32_t a, uint64_t b) → a 在 r0、r1 空、b 在 r2:r3
- callee-saved：r4–r11、sp、s16–s31；r12=ip 暫存；lr 返回位址
- 公開介面 sp 8-byte 對齊 → push 偶數個暫存器（如 `push {r4, lr}`）
- softfp：float 參數也在 r0–r3（不在 s0）；.S 內要 `vmov s0, r0`，回傳前 `vmov r0, s0`
- 超過 4 bytes 的 struct 回傳：呼叫端配置記憶體，位址當隱藏第一參數（r0）
- char 無號；16-bit 指令大多只能用 r0–r7
- 64 位元加：`adds r0,r0,r2` + `adc r1,r1,r3`；減：`subs` + `sbc`

---

【參考卡｜Cortex-M33 2/8｜立即值、條件碼、IT、load/store】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
平台：RP2350（Pico 2）Cortex-M33，Thumb-2，用 `.syntax unified`。
立即值：
- 16-bit MOVS/ADDS/SUBS/CMP #imm：0～255（r0–r7）
- 32-bit 修飾立即值：0x000000XY、0x00XY00XY、0xXY00XY00、0xXYXYXYXY，或 8-bit 值左移到任意位置
- ADDW/SUBW #imm12：0～4095；MOVW/MOVT 各 16 位（32 位元常數 = movw 低半 + movt 高半）
- 移位：LSL #0～31、LSR/ASR #1～32、ROR #1～31；無 ROL（左旋 n = ROR 32−n）
- CBZ/CBNZ 只能向前 0～126 bytes、只能 r0–r7、不能在 IT 內
- 16-bit B<cond> -256～+254；B.W/BL ±16 MiB
條件碼：EQ/NE、CS(HS)/CC(LO) 無號 ≥/<、HI/LS 無號 >/≤、GE/LT/GT/LE 有號、MI/PL。減法 C = NOT borrow。
- 只有加 S 才更新旗標；16-bit 資料處理指令在 IT 外會設旗標（反組譯看到 adds/movs 正常）
IT 區塊（1～4 條條件執行，T 同條件、E 相反）：
```asm
cmp    r0, r1
it     ge
movge  r0, r1
```
Load/Store：
- LDRB/LDRH 零擴展；LDRSB/LDRSH 正負號擴展
- `ldr r3, [r0], #4`（後索引 *p++）；`ldr r3, [r1, r2, lsl #2]`（base[i]）
- `ldmia r0!, {r3-r6}` 一次 4 word；LDRD/LDM 需 word 對齊
- 無餘數指令：a % b = SDIV 後 MLS
- 屏障：DMB 順序、DSB 完成、ISB 清管線

---

【參考卡｜Cortex-M33 3/8｜位元操作：C → Arm 指令】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
平台：RP2350（Pico 2）Cortex-M33。GCC -O2 典型輸出，版本間可能不同，一律 objdump 確認。
| C | 指令 |
|---|---|
| `a & ~b` / `a \| ~b` | bic / orn |
| `(x >> 4) & 0xFFF` | ubfx r0, r0, #4, #12 |
| 有號欄位 | sbfx |
| `(x & ~(0xFFu<<8)) \| ((v&0xFF)<<8)` | bfi r0, r1, #8, #8 |
| 清欄位 | bfc 或 bic |
| `x \| (1u<<n)`（n 常數） | orr r0, r0, #(1<<n) |
| `(x >> n) & 1`（n 常數） | ubfx r0, r0, #n, #1；測位元用 tst |
| __builtin_clz / ctz | clz / rbit + clz |
| __builtin_popcount | 無指令（libgcc 或 SWAR） |
| __builtin_bswap32 / 16 | rev / rev16 + uxth |
| 位元反轉 | rbit（`__rbit()` 或 CMSIS `__RBIT()`） |
| `(x << 7) \| (x >> 25)` | ror r0, r0, #25 |
| (uint8_t)x / (int16_t)x | uxtb / sxth |
| `a < b ? a : b` | cmp + it + mov |
| 夾限 int8 / uint8 | ssat / usat（`__ssat(x,8)`、`__usat(x,8)`） |
| `a*b+c` / `c-a*b` | mla / mls |
| `(uint64_t)a * b` | umull |
| `x / 10u` | umull 魔數 + lsrs（不用 udiv） |
| `p[i]` / `*p++` | ldr r,[b,i,lsl #2] / ldr r,[p],#4 |
| switch 連續 case | tbb / tbh |
- 沒有：popcount、ctz、min/max、pack、zip
- n 為變數的 `x | (1u<<n)`：movs + lsls + orrs（Operand2 不能用暫存器移位量）
- C 層 UB 同 RISC-V：移位 ≥32、`1<<31`（int）、有號溢位、整數提升、`x & 0xF == 0` 優先序

---

【參考卡｜Cortex-M33 4/8｜DSP / FPU / float 選擇】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
平台：RP2350（Pico 2）Cortex-M33，有 DSP 與單精度 FPU。
DSP（32 位元內打包 2×16 或 4×8）：
- SMLAD：Ra + lo*lo + hi*hi → int16 內積 / FIR 每次 2 個 MAC
- UQADD8（4 個 uint8 飽和加）、USAD8/USADA8（4 byte 絕對差和）、SADD16、SEL
- SSAT/USAT 夾限；QADD/QSUB 飽和加減；飽和時 Q 旗標設 1 且黏著
- 編譯器幾乎不會自動產生 → 用 intrinsic
intrinsic：
- `<arm_acle.h>`（不需連結）：`__smlad __qadd __ssat(x,n) __usat __uqadd8 __usad8 __sadd16`；n 必須是編譯期常數
- CMSIS：`target_link_libraries(app cmsis_core)` + `#include "RP2350.h"`：`__SMLAD __CLZ __RBIT __REV __set_BASEPRI`
- SDK `hardware/sync.h`：`__dmb __dsb __isb __nop __wfi __wfe __sev save_and_disable_interrupts`
```c
acc = __smlad((int16x2_t)pa[i], (int16x2_t)pb[i], acc);
```
FPU 週期（⚠️未查證，以實測為準）：
- VADD/VSUB/VMUL.F32：1 + 1 結果延遲；相依鏈 2 cycle/條，兩個累加器交錯 1 cycle/條
- VMLA/VFMA：佔 FPU 3 + 1；可交錯時分開 VMUL + VADD 比 VMLA 快
- VDIV/VSQRT：14 + 1（期間整數核心可繼續）
選擇：
- float 首選；`x / c` → `x * (1.0f / c)`（最後一位可能不同）
- double 走 DCP：dadd 6、dmul 17、ddiv 51 cycle ⚠️未查證（內聯時；經函式呼叫還有開銷）→ 避免；`0.5` 寫 `0.5f`；`-Wdouble-promotion`
- 定點（Q15、Q16.16）用在需要位元精確或資料本來就是整數時

---

【參考卡｜Cortex-M33 5/8｜指令週期（RP2350 datasheet §3.7.4.9）】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
平台：RP2350（Pico 2）Cortex-M33。前提：單核、無 XIP cache miss、無 DMA。⚠️未逐條對照 datasheet 原文，以 cycle 計數實測為準。「延遲」= 下一條用到結果就 +1。
- 一般 ALU 1，無延遲
- Operand2 移位非 LSL #0～3（如 LSL #4、LSR、ASR、ROR），或立即值需移位：1 + 延遲；這類加 S 一定 +1
- UBFX/SBFX/BFI、獨立 LSL/LSR/ASR/ROR、MOVW、ADDW/SUBW：1，無延遲
- SEL：有延遲
- LDR：1 / 暫存器，有延遲（LDM/POP 只有最後一個暫存器有）；STR 1
- 位址暫存器也算來源：`ldr r0,[r0]` 後立刻 `ldr r1,[r0]` 一定 +1
- MUL/MLA/UMULL/SMULL：1 + 延遲；連續 MAC 累加同一暫存器（對）無懲罰
- SDIV/UDIV：n = 兩數最高位 1 的位置差；n<0 → 2，否則 4+⌊n/4⌋（最多約 11）。例 1000/10 → 5
分支：
- taken = 2 + L + U − (K&F)；not-taken = 1 − F
- L=1：分支來自 load（POP {pc}、LDR pc）
- U=1：目標未 word 對齊且為 32-bit 指令
- F=1：可 fold（B、B<cond>、BX LR，且前一條是 16-bit）
- K=0：條件分支且前一條設旗標；其他情況 K=1
- 技巧：cmp/subs 與 bne 間塞一條無關 16-bit 指令 → taken 1 cycle，那條免費
- 無分支預測項；迴圈頂 `.p2align 2`
其他：IT 中條件不成立的指令仍 1 cycle；16-bit nop 可 fold（0 cycle）→ 要耗 1 cycle 用 `nop.w`（`__nop()`）
- 從 SRAM 執行時 literal 在 PC+8（mod 16）附近可能 +1；flash（0x10000000 起）miss 慢很多 → 熱點放 SRAM

---

【參考卡｜Cortex-M33 6/8｜cycle 計數（DWT CYCCNT）】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
平台：RP2350（Pico 2）Cortex-M33，pico-sdk。CYCCNT 重置時預設關閉。
```c
#include "hardware/structs/m33.h"
static inline void cyc_init(void) {
    m33_hw->demcr     |= M33_DEMCR_TRCENA_BITS;
    m33_hw->dwt_cyccnt = 0;
    m33_hw->dwt_ctrl  |= M33_DWT_CTRL_CYCCNTENA_BITS;
}
static inline uint32_t cyc_now(void) { return m33_hw->dwt_cyccnt; }
```
- 位址：DEMCR 0xE000EDFC、DWT_CTRL 0xE0001000、DWT_CYCCNT 0xE0001004
- CMSIS 寫法：`DCB->DEMCR |= DCB_DEMCR_TRCENA_Msk; DWT->CYCCNT = 0; DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;`
- 每顆核心各有 DWT：在 core1 量要在 core1 上 cyc_init()
- 150 MHz 約 28.6 秒回繞；無號相減 t1 - t0 處理一次回繞
- 一直是 0：沒設 TRCENA 或 CYCCNTENA、在另一核設的、NOCYCCNT=1
量測步驟：
```c
cyc_init();
uint32_t t0 = cyc_now(), t1 = cyc_now();
uint32_t overhead = t1 - t0;
t0 = cyc_now();
volatile uint32_t sink = func_under_test(buf, n);
t1 = cyc_now();
uint32_t cycles = (t1 - t0) - overhead;
```
- 多次取最小值或中位數；第一次常有 XIP cache miss
- 排除中斷：`uint32_t s = save_and_disable_interrupts(); … restore_interrupts(s);`
- 替代：SysTick 24 位元向下計數，150 MHz 約 0.11 秒回繞；RTOS 已用 SysTick 時不要動
- µs 等級用 `time_us_32()`

---

【參考卡｜Cortex-M33 7/8｜inline asm 與 .S 函式】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
平台：RP2350（Pico 2）Cortex-M33，GCC。
constraint：`"r"` 核心暫存器、`"l"` r0–r7、`"=r"/"+r"/"=&r"`、`"t"` s0–s31（float）、`"i"/"n"` 常數；clobber `"cc"`（用了 S 後綴、CMP、TST、Q/GE 旗標必寫）、`"memory"`
```c
pico_default_asm ("rbit %0, %1\n\t"
                  "clz  %0, %0" : "=r"(r) : "r"(x));
pico_default_asm ("qadd %0, %1, %2" : "=r"(r) : "r"(a), "r"(b) : "cc");
pico_default_asm ("vsqrt.f32 %0, %1" : "=t"(r) : "t"(x));
```
- `pico_default_asm(...)` / `pico_default_asm_volatile(...)` 自動加 `.syntax unified`；有副作用要 volatile
- inline asm 內的條件指令要自己寫 `it`
.S 檔（大寫 .S）：
```asm
    .syntax unified
    .cpu    cortex-m33
    .thumb
    .section .time_critical.f, "ax"
    .global  f
    .type    f, %function
    .thumb_func
    .p2align 2
f:
    push    {r4, lr}
    ...
    pop     {r4, pc}
    .size    f, . - f
```
- 符號 bit0 必須為 1（漏 .thumb_func → 呼叫即 INVSTATE fault）；`nm` 看位址是否奇數
- Arm 註解用 `@`（.S 也可 `//`）；.type 用 `%function` 不是 `@function`
- 用 s16–s31 要 `vpush {s16-s17}` / `vpop`
- CMake：`project(xxx C CXX ASM)`、`add_executable(app main.c f.S)`；C++ 需 `extern "C"`
- 放 SRAM：`__not_in_flash_func(f)`；objdump 熱迴圈找 `bl __aeabi_d*`、`sdiv`、spill

---

【參考卡｜Cortex-M33 8/8｜中斷、原子、fault 除錯】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
平台：RP2350（Pico 2）Cortex-M33，pico-sdk。
中斷：
- 硬體自動推 r0–r3、r12、lr、pc、xPSR → ISR 就是普通 C 函式
- 有 FP 上下文時 lazy stacking；FPCCR.ASPEN/LSPEN 實際值 ⚠️未驗證（讀 m33_hw->fpccr）
- 4 個優先權位元（16 級）：0x00 最高 … 0xF0；數值越小越優先；SDK 預設 0x80；`irq_set_priority()`
- PRIMASK（`cpsid i`、`save_and_disable_interrupts()`）擋全部可設定例外；BASEPRI 擋數值 ≥ BASEPRI 者
- 這些遮罩只影響本核；跨核要 spinlock / critical_section_t
- tail-chaining、late arrival；返回值 EXC_RETURN 在 lr，ISR 中不要覆蓋 lr
- 掛 handler：`irq_set_exclusive_handler(IRQ, fn)` + `irq_set_enabled(IRQ, true)`
原子：
- LDREX/STREX（STREX 回 0 = 成功）只在 SRAM 有效；之間保持簡短
- 實務用 C11 `<stdatomic.h>` 或 SDK spinlock；屏障 `__dmb()`
Fault 除錯：
- SDK 未開 MemManage/BusFault/UsageFault → 都升級成 HardFault；讀 `m33_hw->cfsr` 分辨
- 出事 PC = 例外堆疊框 [sp+24]
- INVSTATE：符號 bit0=0
- NOCP：未開 CPACR 就用 FPU/DCP（core1 要經 `multicore_launch_core1` 啟動）
- UNALIGNED：LDRD/LDM 非對齊（uint64_t* 指向 buf+1）→ memcpy
- PRECISERR：位址不存在、周邊非對齊、時脈未開（看 bfar）
- 呼叫 printf/double 後當機：sp 未 8-byte 對齊
- softfp .S 讀到垃圾 float：參數在 r0 不在 s0
