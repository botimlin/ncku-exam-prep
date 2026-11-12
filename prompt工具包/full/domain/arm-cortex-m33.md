# Arm 組合語言（RP2350 / Cortex-M33）與 C 位元操作參考

- 用途：**備援包**。若考場要求用 RP2350 的 Arm 核心（`PICO_PLATFORM=rp2350-arm-s`，pico-sdk 對 RP2350 的預設）而不是 Hazard3，用這份取代 `riscv-hazard3.md`。章節編號 0～11 與 `riscv-hazard3.md` 一一對應（可直接替換），另加 §12 例外 / 中斷 / 記憶體模型、§13 RISC-V ↔ Arm 對照表、§14 向模型提問的範本。涵蓋 Armv8-M Mainline（Thumb-2）指令、AAPCS 呼叫慣例、DSP / FPU、RP2350 datasheet 實測的指令週期、GCC inline asm / `.S`、DWT cycle 計數、pico-sdk Arm 建置、C 慣用寫法對應、最佳化與除錯清單。可貼給考場 LLM 當 context，也可給考生自己查。
- 適用版本：RP2350（Raspberry Pi Pico 2 等）的雙核 Arm Cortex-M33（r1p0，CMSIS 標頭 `__CM33_REV 0x0100`）；RP2350 datasheet build 2026-01-10；pico-sdk master（commit `079c6f3`，2026-09，2026-11 查閱）；`arm-none-eabi-gcc` 14 系列。考場實際環境以考題文件為準。
- 來源（實際查閱）：
  - RP2350 datasheet §3.6.2（DCP，Table 118 benchmark）、§3.7（Cortex-M33：§3.7.2 Configuration、§3.7.3.5 FPU、§3.7.4.3 Memory model / unaligned、§3.7.4.4 Exclusive monitor、§3.7.4.6 Exceptions、§3.7.4.9 **Execution timing**、§3.7.4.11 DWT、§3.7.5 暫存器表 ACTLR / SYST_* / FPCCR）、§3.5.9 Security（debug 授權）：https://datasheets.raspberrypi.com/rp2350/rp2350-datasheet.pdf
  - Arm Cortex-M33 Processor Datasheet（3-stage pipeline、limited dual-issue、DMIPS/CoreMark）：https://documentation-service.arm.com/static/627bc262ad18e323faf45445 ；TRM 入口 https://developer.arm.com/documentation/100230/latest/
  - AAPCS32（Arm Procedure Call Standard）：https://github.com/ARM-software/abi-aa/blob/main/aapcs32/aapcs32.rst
  - GCC ACLE 標頭 `gcc/config/arm/arm_acle.h`（GCC 14）：https://github.com/gcc-mirror/gcc/blob/releases/gcc-14/gcc/config/arm/arm_acle.h
  - GCC 文件：ARM Options（`-mfloat-abi`、`-munaligned-access`、`-masm-syntax-unified`、`-mcmse`）https://gcc.gnu.org/onlinedocs/gcc/ARM-Options.html ；Machine Constraints（ARM 段）https://gcc.gnu.org/onlinedocs/gcc/Machine-Constraints.html
  - pico-sdk：`cmake/preload/toolchains/pico_arm_cortex_m33_gcc.cmake`、`.../util/pico_arm_gcc_common.cmake`、`.../util/set_flags.cmake`、`cmake/preload/platforms/rp2350-arm-s.cmake`、`src/rp2350-arm-s.cmake`、`src/rp2_common/hardware_sync/include/hardware/sync.h`、`src/rp2_common/pico_platform_compiler/include/pico/platform/compiler.h`、`src/rp2350/hardware_structs/include/hardware/structs/m33.h`、`src/rp2350/hardware_regs/include/hardware/regs/m33.h`、`src/rp2350/pico_platform/include/pico/asm_helper.S`、`src/rp2_common/pico_crt0/crt0.S`、`src/rp2_common/pico_runtime_init/runtime_init.c`、`src/rp2_common/pico_float/CMakeLists.txt`、`src/rp2_common/pico_double/CMakeLists.txt`、`src/rp2_common/cmsis/`（`CMakeLists.txt`、`stub/CMSIS/Core/Include/cmsis_gcc.h`、`core_cm33.h`、`Device/RP2350/Include/RP2350.h`）、`src/rp2_common/hardware_gpio/include/hardware/gpio_coproc.h`、`src/rp2_common/hardware_irq/include/hardware/irq.h`：https://github.com/raspberrypi/pico-sdk
- 最後更新：2026-11

> 標記說明：`⚠️未驗證` = 查不到一手來源、依版本而異，或是我依規則推算的估計值；使用前用 objdump / DWT 實測確認。
> 週期數一律以 **RP2350 datasheet §3.7.4.9** 為準（Raspberry Pi 在 RP2350 上量測：單核執行、無 XIP cache miss、無 DMA）。⚠️本檔週期表未逐條對照 datasheet 原文，FPU / DCP 週期未查證，關鍵數字以 DWT cycle 計數實測為準。

---

## 0. 三十秒重點

1. pico-sdk 對 `rp2350-arm-s` 的編譯旗標：`-mcpu=cortex-m33 -mthumb -march=armv8-m.main+fp+dsp -mcmse -mfloat-abi=softfp`（`PICO_HARD_FLOAT_ABI=1` 改為 `-mfloat-abi=hard`；`PICO_NO_CMSE=1` 拿掉 `-mcmse`）。工具鏈 triple `arm-none-eabi`。
2. 只有 Thumb（16/32-bit 混合的 Thumb-2），沒有 ARM 32-bit 狀態。有 DSP 擴充（SIMD、飽和、MAC）、單精度 FPU（FPv5-SP，`.fpu fpv5-sp-d16`）、TrustZone、MPU。**沒有** popcount / ctz / min / max 指令（ctz = `RBIT`+`CLZ`）。
3. `float` 用硬體 FPU 很便宜（`VADD/VMUL` 1 cycle + 1 cycle 結果延遲；`VDIV/VSQRT` 14+1）；`double` 由 RP2350 自家 DCP 協處理器加速（`pico_double` 預設），但仍比 float 慢一個數量級 → 用 `float`、常數寫 `1.0f`。
4. 週期（datasheet）：大多數 ALU 1 cycle；load 1 cycle/暫存器，結果下一條就用 +1；乘法 / MAC 1 cycle + 1 延遲（MAC 連鎖累加無懲罰）；`SDIV/UDIV` 2～11 cycle（依運算元，提早結束）；taken 分支約 2 cycle、not-taken 0～1；分支目標「未 word 對齊的 32-bit 指令」+1。
5. Cycle counter：`m33_hw->demcr |= M33_DEMCR_TRCENA_BITS; m33_hw->dwt_cyccnt = 0; m33_hw->dwt_ctrl |= M33_DWT_CTRL_CYCCNTENA_BITS;` 之後讀 `m33_hw->dwt_cyccnt`（`#include "hardware/structs/m33.h"`）。重置時預設關閉。
6. AAPCS：參數 r0–r3、回傳 r0（64-bit 為 r0:r1）、callee-saved r4–r11 與 s16–s31、r12 = ip（暫存）、sp 在公開介面 8-byte 對齊。softfp 下 **float 參數也在 r0–r3**，不在 s0。
7. 非對齊 `LDR/LDRH/STR/STRH` 在一般記憶體可以（較慢，拆成多筆匯流排存取）；`LDRD/STRD/LDM/STM` 與周邊（Device）記憶體非對齊會 fault。
8. 熱點程式放 SRAM：`__not_in_flash_func(f)` / `__time_critical_func(f)`（section `.time_critical.*`）或 `pico_set_binary_type(target copy_to_ram)`（同 RISC-V）。

---

## 1. 暫存器與 ABI（AAPCS32）

### 1.1 核心暫存器

| 暫存器 | 別名 | AAPCS 用途 | 跨呼叫保存者 |
|---|---|---|---|
| r0–r1 | a1–a2 | 參數 1–2、回傳值（64-bit 用 r0 低 / r1 高） | caller |
| r2–r3 | a3–a4 | 參數 3–4 | caller |
| r4–r8 | v1–v5 | 保存變數 | **callee** |
| r9 | v6 / SB / TR | 平台暫存器；bare-metal pico-sdk 中當一般 callee-saved 使用（AAPCS 允許平台另作他用） | **callee** |
| r10–r11 | v7–v8（r11 常作 fp） | 保存變數 | **callee** |
| r12 | ip | intra-procedure-call scratch（linker veneer 可能破壞） | caller |
| r13 | sp | 堆疊指標（實體上有 MSP / PSP，各分 Secure / Non-secure） | callee（必須還原） |
| r14 | lr | 返回位址（BL 寫入；例外時放 EXC_RETURN） | caller |
| r15 | pc | 程式計數器（讀 pc 得到「目前指令位址 + 4」） | — |

- 16-bit Thumb 指令大多只能用 **r0–r7（low registers）**；用到 r8–r12 常需要 32-bit 編碼。熱迴圈變數放 r0–r7 可讓程式較小。
- 「16-bit 資料處理指令在 IT 區塊外會設旗標」：`MOVS/ADDS/SUBS/ANDS/LSLS…` 的 16-bit 形式都帶 `S`。所以反組譯常看到 `adds`、`movs`，這是正常的。

### 1.2 xPSR 與條件碼

- APSR 旗標：`N`（負）、`Z`（零）、`C`（進位）、`V`（有號溢位）、`Q`（飽和黏著旗標，DSP）、`GE[3:0]`（SIMD 每 lane 的 ≥ 旗標，給 `SEL` 用）。IPSR = 目前例外編號（0 = Thread mode）。EPSR 有 T bit（必須為 1）與 IT 狀態。
- **減法的 C = NOT borrow**：`CMP a, b` 後 `a ≥ b`（無號）時 C=1。

| 條件 | 意義 | 旗標 | | 條件 | 意義 | 旗標 |
|---|---|---|---|---|---|---|
| EQ / NE | = / ≠ | Z=1 / Z=0 | | HI / LS | 無號 > / ≤ | C=1&Z=0 / C=0\|Z=1 |
| CS(HS) / CC(LO) | 無號 ≥ / < | C=1 / C=0 | | GE / LT | 有號 ≥ / < | N=V / N≠V |
| MI / PL | 負 / 非負 | N=1 / N=0 | | GT / LE | 有號 > / ≤ | Z=0&N=V / Z=1\|N≠V |
| VS / VC | 溢位 / 無 | V=1 / V=0 | | AL | 永遠 | — |

64 位元加減用進位鏈（RISC-V 沒有旗標要自己算，Arm 一條就好）：

```asm
@ (r1:r0) += (r3:r2)
adds  r0, r0, r2      @ 低位，設定 C
adc   r1, r1, r3      @ 高位加上進位
@ (r1:r0) -= (r3:r2)
subs  r0, r0, r2
sbc   r1, r1, r3
```

### 1.3 呼叫慣例要點（AAPCS32）

- 整數 / 指標參數依序放 r0–r3，剩下的上堆疊。窄於 32 位元的整數由呼叫端擴展。
- 64 位元參數（`uint64_t`、`double`）需要**偶數號**暫存器對（r0:r1 或 r2:r3，小端：低 32 位在編號小的）；必要時跳過一個暫存器。`f(uint32_t a, uint64_t b)` → a 在 r0，r1 空著，b 在 r2:r3。基本型別不會一半在暫存器一半在堆疊。
- 回傳：32 位元以內 → r0；64 位元 → r0:r1；超過 4 bytes 的 struct 由呼叫端配置記憶體並把位址當隱藏的第一個參數（r0）傳入。
- 公開介面上 **sp mod 8 = 0**（8-byte 對齊）。函式內部任意時刻至少 4-byte 對齊。`PUSH` 偶數個暫存器即可維持 8-byte 對齊（例如 `push {r4, lr}`、`push {r4-r6, lr}`）。
- callee-saved：r4–r11、sp，以及 FPU 的 **s16–s31（d8–d15）**；s0–s15、FPSCR 旗標為 caller-saved。
- `char` 在 Arm AAPCS 是**無號** byte（`LDRB` 零擴展）。要有號請寫 `int8_t`。

### 1.4 FPU 暫存器與 float ABI

| 項目 | 內容 |
|---|---|
| 暫存器 | `s0`–`s31`（32-bit），也可看成 `d0`–`d15`（64-bit，只用於 load/store/搬移） |
| 控制 | `FPSCR`（旗標 N/Z/C/V、捨入模式、FZ flush-to-zero、DN default NaN、累積例外旗標）；不支援 FP 例外 trap |
| `-mfloat-abi=softfp`（**pico-sdk 預設**） | 可產生 FPU 指令，但**呼叫慣例同 soft-float**：`float` 參數放 r0–r3、回傳 r0；編譯器用 `VMOV` 在 r 與 s 暫存器間搬 |
| `-mfloat-abi=hard`（`PICO_HARD_FLOAT_ABI=1`） | float 參數放 s0–s15、回傳 s0；所有物件與函式庫必須同一 ABI（hard 與 soft/softfp 不可混連結） |
| 開機 | SDK runtime 在每顆核心設定 `CPACR` 開啟 FPU（CP10）、DCP（CP4）、GPIO 協處理器（CP0）（`runtime_init_per_core_enable_coprocessors`）。沒開就執行 FPU 指令 → UsageFault（NOCP） |

> 寫 `.S` 函式接收 float 時：softfp 下引數在 **r0**，要先 `vmov s0, r0`；回傳前 `vmov r0, s0`。

---

## 2. 指令格式與立即值範圍（Thumb-2）

- 指令長度 16 或 32 bit，**halfword 對齊**。32-bit 指令的第一個 halfword 高 5 bit 為 `0b11101/0b11110/0b11111`。
- 組譯器自動選短編碼；可用後綴強制：`.n`（16-bit）、`.w`（32-bit），例如 `nop.w`、`b.w`。
- 一律用 **unified syntax**（`.syntax unified`）：三運算元寫法 `add r0, r1, r2`，`S` 後綴明確寫出。

| 類型 | 範圍 / 規則 |
|---|---|
| 16-bit `MOVS Rd, #imm` / `ADDS/SUBS Rdn, #imm` / `CMP Rn, #imm` | 0～255（只限 r0–r7） |
| 16-bit `ADDS/SUBS Rd, Rn, #imm` | 0～7 |
| 32-bit 資料處理「修飾立即值」（`MOV.W/MVN/AND/ORR/EOR/BIC/ORN/ADD/SUB/CMP/TST…`） | 下列之一：`0x000000XY`、`0x00XY00XY`、`0xXY00XY00`、`0xXYXYXYXY`，或「最高位為 1 的 8-bit 值」左移到任意位置（例 `0x3FC00000`）。其他值組譯器會報錯或改用 `MOVW/MOVT` |
| `ADDW / SUBW Rd, Rn, #imm12` | 0～4095（純 12-bit，不移位） |
| `MOVW Rd, #imm16` / `MOVT Rd, #imm16` | 0～65535 寫低半（清高半）/ 寫高半（保留低半） |
| 移位立即值 | `LSL #0～31`；`LSR/ASR #1～32`；`ROR #1～31` |
| `LDR/STR{B,H} Rt, [Rn, #imm]` | 32-bit：+0～4095；負位移 -255～-1 |
| 前 / 後索引 `[Rn, #imm]!`、`[Rn], #imm` | -255～+255 |
| `LDR Rt, [Rn, Rm, LSL #k]` | k = 0～3 |
| `LDRD/STRD Rt, Rt2, [Rn, #imm]` | ±1020，4 的倍數（可前 / 後索引） |
| 16-bit `LDR Rt, [Rn, #imm]` | 0～124（word、4 的倍數，r0–r7）；`[sp, #imm]` 0～1020 |
| `LDR Rt, =label` / literal | 32-bit：pc ± 4095；16-bit：向前 0～1020（word 對齊） |
| 16-bit `B<cond>` | -256～+254 |
| 16-bit `B` | ±2 KiB |
| 32-bit `B<cond>.W` | ±1 MiB |
| 32-bit `B.W` / `BL` | ±16 MiB |
| `CBZ / CBNZ Rn, label` | 只能**向前** 0～126 bytes，Rn 只能 r0–r7，不能放在 IT 區塊內 |

### 2.1 32 位元常數的組成

```asm
movw  r0, #0x5678          @ r0 = 0x00005678
movt  r0, #0x1234          @ r0 = 0x12345678（2 條 32-bit 指令，各 1 cycle；MOVW 無 result-use 懲罰，MOVT ⚠️未驗證）
ldr   r1, =0xDEADBEEF      @ pseudo：組譯器選 MOV/MVN 或放 literal pool（PC 相對 load）
ldr   r2, =some_symbol     @ 取位址（放 literal pool）
adr   r3, local_label      @ pc 相對位址（範圍小）
```

- 編譯器預設用 literal pool（`ldr rX, [pc, #off]`）放常數與位址。程式在 flash 時這是一次 XIP 讀取；在 SRAM 時可能與取指衝突（§5.6）。
- `MOV.W` / `MVN` 能用修飾立即值時只要 1 條；`0x000000FF` 這類小值 16-bit `movs` 就夠。

---

## 3. Armv8-M Mainline 指令總表

### 3.1 資料處理（彈性第二運算元 Operand2）

Operand2 可以是：暫存器、**移位後的暫存器**（`Rm, LSL #n` / `LSR` / `ASR` / `ROR` / `RRX`）、或修飾立即值。

| 指令 | 語意 | 備註 |
|---|---|---|
| `ADD{S} Rd, Rn, Op2` | Rd = Rn + Op2 | `add r0, r1, r2, lsl #2` = r1 + r2*4（一條做完陣列索引） |
| `ADC{S}` | + C | 64 位元加法高位 |
| `SUB{S} Rd, Rn, Op2` | Rd = Rn − Op2 | |
| `SBC{S}` | − NOT C | |
| `RSB{S} Rd, Rn, Op2` | Rd = Op2 − Rn（反向減） | `rsb r0, r0, #0` = 取負（`neg` 別名）；`rsb r0, r1, r1, lsl #3` = r1*7 |
| `AND{S} / ORR{S} / EOR{S}` | & / \| / ^ | |
| `BIC{S} Rd, Rn, Op2` | Rn & ~Op2 | 清除遮罩位元（= RISC-V `andn`） |
| `ORN{S} Rd, Rn, Op2` | Rn \| ~Op2 | 僅 32-bit 編碼 |
| `MVN{S} Rd, Op2` | ~Op2 | = `not` |
| `MOV{S} Rd, Op2` | 搬移 | `mov r0, r1, lsl #3` 會被寫成 `lsl r0, r1, #3` |
| `CMP Rn, Op2` / `CMN Rn, Op2` | 設旗標（Rn−Op2 / Rn+Op2） | 不寫回 |
| `TST Rn, Op2` / `TEQ Rn, Op2` | 設旗標（Rn&Op2 / Rn^Op2） | `tst r0, #1<<5` 測 bit 5 |

- 加 `S` 才會更新 N/Z（以及 C/V）。不需要旗標時就不要加 `S`（帶 `S` 的「複雜」運算一定有 1 cycle 懲罰，見 §5.2）。
- 移位的第二運算元會把移出的最後一位寫進 C（邏輯運算加 S 時）。

### 3.2 移位與旋轉

| 指令 | 語意 |
|---|---|
| `LSL Rd, Rm, #n` / `LSL Rd, Rm, Rs` | 邏輯左移 |
| `LSR` | 邏輯右移 |
| `ASR` | 算術右移（補符號位） |
| `ROR` | 循環右移（**沒有 ROL**；左旋 n = `ROR #(32−n)`） |
| `RRX Rd, Rm` | 帶 C 右旋 1 位（33-bit 旋轉） |

- **暫存器移位量取 Rs 的低 8 位**：`LSL/LSR` 移 ≥ 32 → 結果 0；`ASR` 移 ≥ 32 → 全為符號位；`ROR` 等效 mod 32。與 RISC-V（只取低 5 位，`<<32` 等於 `<<0`）**不同**。C 語言中移位 ≥ 寬度仍是 UB，兩邊都不要依賴。

### 3.3 位元欄位與位元操作

| 指令 | 語意 | 取代的 C 寫法 |
|---|---|---|
| `UBFX Rd, Rn, #lsb, #w` | Rd = (Rn >> lsb) & ((1<<w)−1) | `(x >> lsb) & mask`（取欄位） |
| `SBFX Rd, Rn, #lsb, #w` | 同上但正負號擴展 | 取有號欄位 |
| `BFI Rd, Rn, #lsb, #w` | 把 Rn[w−1:0] 插入 Rd[lsb+w−1:lsb]，其他位不變 | `(x & ~m) \| ((v << lsb) & m)` |
| `BFC Rd, #lsb, #w` | 清除 Rd 的欄位 | `x & ~(mask << lsb)` |
| `CLZ Rd, Rm` | 前導零數（0 → 32） | `__builtin_clz`（C 中 0 為 UB） |
| `RBIT Rd, Rm` | 32 位元位元反轉 | 位元反轉迴圈；`RBIT`+`CLZ` = ctz |
| `REV Rd, Rm` | 4 個 byte 反轉 | `__builtin_bswap32` |
| `REV16 Rd, Rm` | 每個 halfword 內 2 byte 交換 | 兩個 16-bit 同時換位元組序 |
| `REVSH Rd, Rm` | 低 halfword 換 byte 後正負號擴展 | `(int16_t)__builtin_bswap16(x)` |
| `UXTB / UXTH / SXTB / SXTH Rd, Rm{, ROR #8/16/24}` | 零 / 正負號擴展（可先旋轉取第 n 個 byte） | `(uint8_t)x`、`(int16_t)x`、`(uint8_t)(x >> 8)` |

- 兩個 C 寫法常見的指令：`TST`（測位元）＋條件分支；`ORR r0, r0, #(1<<n)`（設位元，n 為常數時修飾立即值一定能表示單一位元）。
- **沒有**：popcount、ctz、min/max、andn 以外的 Zbs 類單位元指令（用 `ORR/BIC/EOR` + 立即值或 `LSL` 代替）、`pack`、`zip`。

### 3.4 乘法

| 指令 | 語意 |
|---|---|
| `MUL{S} Rd, Rn, Rm` | 低 32 位 |
| `MLA Rd, Rn, Rm, Ra` | Rd = Ra + Rn*Rm |
| `MLS Rd, Rn, Rm, Ra` | Rd = Ra − Rn*Rm |
| `UMULL RdLo, RdHi, Rn, Rm` | 64 位元 = 無號 Rn*Rm |
| `SMULL RdLo, RdHi, Rn, Rm` | 64 位元 = 有號 Rn*Rm |
| `UMLAL / SMLAL RdLo, RdHi, Rn, Rm` | 64 位元累加：RdHi:RdLo += Rn*Rm |
| `UMAAL RdLo, RdHi, Rn, Rm`（DSP） | RdHi:RdLo = Rn*Rm + RdHi + RdLo（多精度乘法好用） |
| `SMMUL / SMMULR / SMMLA / SMMLS`（DSP） | 有號 32×32 的**高 32 位**（R = 四捨五入） |
| `SMULxy / SMLAxy`（DSP，x,y = B/T） | 16×16（取底 / 頂 halfword），SMLA 加 32 位元累加 |
| `SMULWy / SMLAWy`（DSP） | 32×16 取高 32 位（Q15 係數乘法） |
| `SMLALxy`（DSP） | 16×16 累加到 64 位元 |

### 3.5 除法

| 指令 | 語意 | 特例 |
|---|---|---|
| `SDIV Rd, Rn, Rm` | 有號商（朝 0 取整） | `INT_MIN / -1` = `INT_MIN`（不 trap） |
| `UDIV Rd, Rn, Rm` | 無號商 | |
| 除以 0 | 結果 **0**（`CCR.DIV_0_TRP` 預設 0）；設 1 則觸發 UsageFault（DIVBYZERO） | RISC-V 回傳全 1，**不同** |

- 沒有餘數指令：`a % b` = `MLS r, q, b, a`（先 `SDIV q, a, b`）。
- 週期見 §5.4（2～11 cycle）。

### 3.6 飽和運算

| 指令 | 語意 | 擴充 |
|---|---|---|
| `SSAT Rd, #n, Rm{, LSL/ASR #s}` | 夾到 n 位元有號範圍 [−2^(n−1), 2^(n−1)−1]，n = 1～32 | Main |
| `USAT Rd, #n, Rm{, shift}` | 夾到 [0, 2^n − 1]，n = 0～31 | Main |
| `QADD / QSUB Rd, Rm, Rn` | 32 位元有號飽和加 / 減 | DSP |
| `QDADD / QDSUB` | 先飽和加倍再飽和加 / 減 | DSP |
| `SSAT16 / USAT16` | 兩個 halfword 各自飽和 | DSP |

- 發生飽和時 `Q` 旗標設 1 且**黏著**（只能用 `MSR APSR_nzcvq, Rn` 清除）。

### 3.7 Load / Store

| 指令 | 寬度 / 動作 | 備註 |
|---|---|---|
| `LDR / STR` | 32 | |
| `LDRB / LDRH` | 8 / 16 零擴展 | |
| `LDRSB / LDRSH` | 8 / 16 正負號擴展 | |
| `STRB / STRH` | 存低 8 / 16 位 | |
| `LDRD / STRD Rt, Rt2, [Rn, #imm]` | 兩個 word | 位址需 4-byte 對齊 |
| `LDM{IA,DB} Rn{!}, {reglist}` / `STM` | 多個 word（暫存器編號小的放低位址） | 需 word 對齊；`!` 回寫基底 |
| `PUSH {reglist}` / `POP {reglist}` | = `STMDB sp!` / `LDMIA sp!` | `POP {…, pc}` 直接返回 |
| `LDR Rt, [pc, #imm]` | literal load | |
| `LDREX / STREX`、`LDREXB/H`、`STREXB/H`、`CLREX` | exclusive（§12.6） | |
| `LDA / STL`、`LDAEX / STLEX`（含 B/H） | Armv8-M acquire / release 版本 | pico-sdk 軟體 spinlock 用 `ldaexb`/`stlb` |
| `TBB [Rn, Rm]` / `TBH [Rn, Rm, LSL #1]` | 查表分支（switch 跳表）：pc += 2 * table[Rm] | 只能向前跳 |
| `PLD [Rn, #imm]` | 預取提示 | |

定址模式：

| 寫法 | 位址 | 基底回寫 |
|---|---|---|
| `[Rn, #imm]` | Rn + imm | 否 |
| `[Rn, #imm]!` | Rn + imm（前索引） | Rn = Rn + imm |
| `[Rn], #imm` | Rn（後索引） | Rn = Rn + imm |
| `[Rn, Rm{, LSL #0-3}]` | Rn + (Rm << k) | 否 |

```asm
ldr   r3, [r0], #4          @ r3 = *p++（後索引：一條做完 load + 指標遞增）
ldr   r3, [r1, r2, lsl #2]  @ r3 = base[i]
ldrd  r4, r5, [r0, #8]      @ r4 = p[2], r5 = p[3]
ldmia r0!, {r3-r6}          @ 一次載 4 個 word，r0 += 16
```

- **非對齊**：`LDR/LDRH/STR/STRH`（含 `TBH`）在 Normal memory 支援非對齊（拆成 2 筆以上匯流排存取）；`LDRD/STRD/LDM/STM` 只接受 word 對齊；Device memory（周邊）任何非對齊都 fault。`CCR.UNALIGN_TRP=1` 時所有非對齊都 fault（重置為 0）。GCC 對 Armv8-M Mainline 預設 `-munaligned-access`（packed struct 會直接用 LDR 讀）。
- 小端序（little-endian）。

### 3.8 分支、IT 區塊

| 指令 | 動作 |
|---|---|
| `B label` / `B<cond> label` | 跳躍 |
| `BL label` | lr = 返回位址（bit0 = 1，Thumb）；跳躍 |
| `BX Rm` / `BLX Rm` | 跳到暫存器位址（bit0 必須為 1，否則 INVSTATE fault）；`bx lr` 是返回 |
| `CBZ / CBNZ Rn, label` | Rn == 0 / != 0 時向前跳（不影響旗標） |
| `TBB / TBH` | 跳表 |
| `IT{x{y{z}}} cond` | 接下來 1～4 條指令條件執行（`T` = 同條件、`E` = 相反條件） |

```asm
@ r0 = (r0 < r1) ? r0 : r1       （有號 min）
cmp    r0, r1
it     ge
movge  r0, r1

@ r2 = (r0 == 0) ? 5 : 9
cmp    r0, #0
ite    eq
moveq  r2, #5
movne  r2, #9
```

- IT 區塊內的 16-bit 資料處理指令**不**設旗標（`movge` 不是 `movsge`）；組譯器會檢查 IT 與後續條件一致。
- IT 區塊中條件不成立的指令仍佔 1 cycle（§5.7）；分支只能是 IT 區塊最後一條。

### 3.9 系統 / 屏障 / 提示

| 指令 | 作用 |
|---|---|
| `DMB` | 資料記憶體屏障：之前的記憶體存取在之後的存取之前被觀察到 |
| `DSB` | 等之前所有記憶體存取**完成**才繼續 |
| `ISB` | 清管線，之後的指令重新取指（改 CONTROL、VTOR、寫程式碼到 RAM 後用） |
| `CPSID i` / `CPSIE i` | 關 / 開 PRIMASK（關所有可設定優先權的例外） |
| `MRS Rd, spec` / `MSR spec, Rn` | 讀寫 PRIMASK、BASEPRI、BASEPRI_MAX、FAULTMASK、CONTROL、MSP、PSP、APSR… |
| `WFI` / `WFE` / `SEV` | 等中斷 / 等事件 / 送事件（兩核都收到） |
| `NOP` | 16-bit `nop` 可能與前一條 16-bit 指令 dual-issue（0 cycle）；要確實耗 1 cycle 用 `nop.w`（pico-sdk 的 `__nop()` 在 RP2350 Arm 就是 `nop.w`） |
| `SVC #imm` / `BKPT #imm` / `UDF #imm` | 系統呼叫 / 斷點 / 必定未定義 |
| `MCR/MRC/MCRR/MRRC/CDP p<n>, …` | 協處理器（RP2350：p0 GPIO、p4/p5 DCP、p7 RCP） |

### 3.10 常見別名 / 寫法對照

| 寫法 | 實際 |
|---|---|
| `neg rd, rm` | `rsbs rd, rm, #0` |
| `mov rd, #imm16` | `movw`（imm 不是修飾立即值時） |
| `lsl rd, rm, #n` | `mov rd, rm, lsl #n` |
| `ldr rd, =const` | `mov/mvn/movw` 或 literal pool |
| `push {..}` / `pop {..}` | `stmdb sp!` / `ldmia sp!` |
| `bx lr` / `pop {…, pc}` | 函式返回 |
| `cpy rd, rm` | `mov rd, rm`（舊寫法） |

---

## 4. RP2350 Cortex-M33 的設定與擴充（datasheet §3.7.2）

| 項目 | RP2350 設定 |
|---|---|
| 架構 | Armv8-M Main Extension（Mainline）、Security Extension、PMSA、Floating-point Extension、DSP Extension、Debug Extension、FPB v2 |
| 指令 | 全部 base + Main + Security + DSP 指令；FPU 的全部單精度指令，加上 double 的 load/store/搬移 |
| FPU | 單精度 FPv5（`-march=...+fp`；SDK `.fpu fpv5-sp-d16`）；IEEE 754-2008；無 FP 例外 trap |
| DSP | 有（`+dsp`；編譯器定義 `__ARM_FEATURE_DSP`、`__ARM_FEATURE_SIMD32`） |
| TrustZone | 有：SAU 8 區；重置進入 Secure state |
| MPU | Secure 8 區 + Non-secure 8 區 |
| NVIC | 52 個外部 IRQ；**4 個優先權位元（16 級）**（CMSIS `__NVIC_PRIO_BITS = 4`） |
| Debug | 8 個斷點比較器、4 個 watchpoint；DWT（含 CYCCNT）、ITM、ETM；無 MTB |
| 協處理器介面 | 有：p0 = GPIO coprocessor、p4/p5 = DCP（Secure / Non-secure）、p7 = RCP（安全用，SDK/bootrom 使用） |
| UNCROSS_I_D（RPi 修改） | 所有取指走 Code port，所有 load/store 走 System port（原設計依位址 < 0x20000000 分流），減少內部衝突 |
| 時脈 | 標稱 150 MHz（clk_sys） |
| 效能（Arm datasheet） | 1.50 DMIPS/MHz、4.02 CoreMark/MHz |

### 4.1 DSP / SIMD 指令（32 位元暫存器內打包 2×16 或 4×8）

| 指令 | 語意 | 用途 |
|---|---|---|
| `SADD16 / SSUB16 / UADD16 / USUB16` | 兩個 halfword 各自加減（回繞），設 GE | 兩聲道 / 兩像素同時算 |
| `SADD8 / UADD8 / SSUB8 / USUB8` | 四個 byte 各自加減，設 GE | |
| `QADD16 / QSUB16 / QADD8 / QSUB8` | 有號飽和 | 音訊混音 |
| `UQADD16 / UQSUB16 / UQADD8 / UQSUB8` | 無號飽和 | 8-bit 影像亮度相加不溢出 |
| `SHADD16 / UHADD8 …` | 加後右移 1（halving，取平均） | 平均兩像素 |
| `SASX / SSAX / UASX …` | 交換 halfword 後一加一減 | 複數運算 |
| `SEL Rd, Rn, Rm` | 依 GE 旗標逐 byte 選 Rn 或 Rm | 配 `USUB8` 做逐 byte max/min |
| `USAD8 Rd, Rn, Rm` / `USADA8 Rd, Rn, Rm, Ra` | 4 個 byte 絕對差總和（/ 再加 Ra） | 影像比對（SAD） |
| `SMUAD / SMUADX` | lo*lo + hi*hi（X = 交叉） | 2 元素內積 |
| `SMUSD / SMUSDX` | lo*lo − hi*hi | 複數乘法實部 |
| `SMLAD / SMLADX Rd, Rn, Rm, Ra` | Ra + lo*lo + hi*hi（累加溢位設 Q） | **int16 內積 / FIR 每次 2 個 MAC** |
| `SMLSD`、`SMLALD / SMLSLD` | 減版本 / 64 位元累加版本 | |
| `PKHBT / PKHTB Rd, Rn, Rm{, shift}` | 從兩暫存器各取一個 halfword 組合 | 打包 int16 對 |
| `SXTB16 / UXTB16 Rd, Rm{, ROR #n}` | 取 byte 0 與 byte 2 擴展成兩個 halfword | uint8 → 2×uint16 |
| `SXTAB / UXTAB / SXTAH / UXTAH / SXTAB16 / UXTAB16` | 擴展後加到另一暫存器 | |

什麼時候值得用：資料本來就是 `int16_t` / `uint8_t` 陣列（音訊、影像、FIR、內積、SAD），且可以每次 load 一個 word 拿到 2 或 4 個元素。對一般 32 位元整數程式沒幫助。編譯器幾乎不會自動向量化成這些指令 → 用 intrinsic。

### 4.2 ACLE / CMSIS intrinsic

| 來源 | 名稱風格 | 怎麼取得 |
|---|---|---|
| ACLE（GCC 內建 `<arm_acle.h>`） | 小寫：`__smlad`、`__qadd`、`__ssat`、`__usat`、`__sadd16`、`__uqadd8`、`__usad8`、`__sel`、`__smuad`、`__smlald`、`__sxtb16`、`__smlabb`… | `#include <arm_acle.h>`，不需連結任何函式庫 |
| CMSIS-Core 6（pico-sdk 內附 stub） | 大寫：`__SMLAD`、`__QADD`、`__SSAT`、`__USAT`、`__CLZ`、`__RBIT`、`__REV`、`__REV16`、`__REVSH`、`__ROR`、`__LDREXW`/`__STREXW`、`__get_PRIMASK`、`__set_BASEPRI`… | `target_link_libraries(app cmsis_core)` 後 `#include "RP2350.h"`（它會引入 `core_cm33.h`、`cmsis_gcc.h`）。CMSIS 的 SIMD 大寫名大多只是 `#define __SMLAD __smlad` 轉到 ACLE |
| pico-sdk `hardware/sync.h` | `__dmb()`、`__dsb()`、`__isb()`、`__nop()`、`__sev()`、`__wfe()`、`__wfi()`、`save_and_disable_interrupts()`、`restore_interrupts()` | `pico_stdlib` 已帶 |
| GCC builtin | `__builtin_clz/ctz/popcount/bswap32/bswap16`、`__builtin_add_overflow` 等 | 不需標頭 |

- GCC 14 的 `<arm_acle.h>` 型別：`int16x2_t`（= `int32_t`）、`uint8x4_t`（= `uint32_t`）等，本質都是 32 位元整數。
- GCC 14 的 `<arm_acle.h>` **有** `__clz`、`__rev`、`__rev16`、`__revsh`、`__rbit`、`__ror`（以 `_GCC_ARM_ACLE_DATA_ALIAS` 巨集定義，GCC 13 以前沒有）；舊工具鏈改用 CMSIS 的 `__CLZ`/`__RBIT`/`__REV` 或 GCC builtin / inline asm。
- `__ssat(x, n)` / `__usat(x, n)` 的 n 必須是編譯期常數（標頭內有範圍檢查：ssat 1～32、usat 0～31）。
- CMSIS 會把 SDK 的例外名改成 CMSIS 名（`isr_systick` → `SysTick_Handler` 等，`PICO_CMSIS_RENAME_EXCEPTIONS` 預設 1）。

```c
#include <stdint.h>
#include <arm_acle.h>

// int16 內積：每次 load 兩個元素（一個 word），一條 SMLAD 做兩個 MAC
// 前提：a、b 4-byte 對齊，n 為偶數；累加若溢位只設 Q 旗標，不飽和
int32_t dot_q15(const int16_t *a, const int16_t *b, uint32_t n) {
    const uint32_t *pa = (const uint32_t *)a, *pb = (const uint32_t *)b;   // 嚴格說違反 aliasing，可用 memcpy 取代
    int32_t acc = 0;
    for (uint32_t i = 0; i < n / 2; i++)
        acc = __smlad((int16x2_t)pa[i], (int16x2_t)pb[i], acc);
    return acc;
}

// 4 個 uint8 像素飽和相加
static inline uint32_t add_pixels_sat(uint32_t p, uint32_t q) { return __uqadd8(p, q); }

// 8 個 byte 的 SAD（兩個 word）
static inline uint32_t sad8(uint32_t a0, uint32_t b0, uint32_t a1, uint32_t b1) {
    return __usada8(a1, b1, __usad8(a0, b0));
}

// 夾限到 int16
static inline int32_t clamp_s16(int32_t x) { return __ssat(x, 16); }
```

### 4.3 FPU 指令（單精度）

| 指令 | 語意 | 週期（datasheet §3.7.4.9.10；⚠️未查證，以實測為準） |
|---|---|---|
| `VADD.F32 / VSUB.F32 / VMUL.F32 Sd, Sn, Sm` | + − × | 1 + 1 cycle 結果延遲 |
| `VNMUL.F32` | −(Sn×Sm) | ⚠️未驗證（推測同 VMUL） |
| `VMLA.F32 / VMLS.F32` | Sd ± Sn×Sm（**非融合**，兩次捨入） | 佔 FPU 3 cycle + 1 延遲 |
| `VFMA.F32 / VFMS.F32` | 融合乘加（一次捨入） | 佔 FPU 3 cycle + 1 延遲；同累加器連續每 3 cycle 一條 |
| `VDIV.F32` / `VSQRT.F32` | ÷ / √ | 佔 FPU 14 cycle + 1 延遲（整數核心可同時做別的事） |
| `VABS / VNEG / VMOV Sd, Sm` | | VMOV s↔s 1 cycle |
| `VMOV Sd, Rn` / `VMOV Rd, Sn` | r → s / s → r | 1 / 1 + 1 延遲 |
| `VMOV Dd, Rlo, Rhi` / `VMOV Rlo, Rhi, Dd` | 64 位元搬移 | FPU 2 cycle（整數核心 1）/ 兩者各 2 |
| `VLDR / VSTR`、`VLDM / VSTM`、`VPUSH / VPOP` | FP load/store（含 D 暫存器） | ⚠️未驗證 |
| `VCMP.F32 / VCMPE.F32` + `VMRS APSR_nzcv, FPSCR` | 比較後把旗標搬到 APSR 才能條件分支 | ⚠️未驗證 |
| `VCVT.S32.F32 / VCVT.F32.S32 / .U32` | float ↔ int（float→int 預設朝 0 截斷） | ⚠️未驗證 |
| `VCVT.F32.S32 Sd, Sd, #fbits` | 定點 ↔ 浮點（fbits 個小數位） | ⚠️未驗證 |
| `VCVTA/N/P/M`、`VRINTA/N/P/M/Z/R/X`、`VSEL<cond>`、`VMAXNM / VMINNM` | FPv5 新增：指定捨入、條件選擇、IEEE max/min | ⚠️未驗證 |
| `VMOV.F32 Sd, #imm` | 少數可編碼的浮點常數 | |

- 發一條 FPU 指令佔整數核心 1 cycle，之後整數指令可繼續；再發 FPU 指令會等到 FPU 可接受。
- 相依鏈 `VADD s0,s0,s2; VADD s0,s0,s3; …` 是 **2 cycle/條**；用兩個累加器交錯（s0、s1）可達 **1 cycle/條**。
- 可交錯時，分開的 `VMUL` + `VADD` 比一條 `VMLA` 快（datasheet 明說）。GCC 在 `-O2` 預設 `-ffp-contract=fast`（非 ISO 模式）可能把 `a*b+c` 合成 `VFMA` ⚠️未驗證於考場版本；在意可加 `-ffp-contract=off`，並以 objdump 確認。
- `double` 只能 load/store/搬移，**運算全部走函式**（`__aeabi_dadd`、`__aeabi_dmul`…），pico-sdk 預設把它們包到 DCP 實作。

### 4.4 float / double / 定點怎麼選（Arm 版）

| 方案 | Cortex-M33 成本 | 建議 |
|---|---|---|
| `float` + − × | 1 cycle 發射、1 cycle 延遲 | **首選**：不需改寫成定點 |
| `float` ÷ √ | 14+1 cycle（可與整數運算重疊） | 迴圈內 `x / c` 改 `x * (1.0f / c)`（數值會有最後一位差異，需確認判題容忍） |
| `double` | DCP：dadd 6、dmul 17、ddiv 51、dsqrt 49 cycle ⚠️未查證（datasheet Table 118，**內聯**使用協處理器時；經 SDK 函式呼叫還有額外開銷） | 避免；`0.5` → `0.5f`；`-Wdouble-promotion` 抓隱性 double |
| 定點（Q16.16 / Q15） | 整數 1 cycle、`SMULL` 1+1、`SMLAD` 一次兩個 MAC | 需要**位元精確**結果、或資料本來就是整數 / int16 時 |

（與 `pico-sdk.md` §7.7 一致：`pico_float` 預設 `pico_vfp`、`pico_double` 預設 DCP；RISC-V 才需要大量改定點。）

---

## 5. Cortex-M33 效能特性（RP2350 datasheet §3.7.4.9）

前提：單核、無 XIP cache miss、無 DMA。⚠️未逐條對照 datasheet 原文，以 cycle 計數實測為準。多核搶匯流排、flash 執行、DMA 都會讓實測變慢。

### 5.1 管線概觀

- 3 級 in-order 管線（Arm 官方說法；包含 5×16-bit 指令佇列、部分運算可在前段提早完成）⚠️各級名稱依 Arm 簡介，datasheet 未細列。
- Harvard：取指與資料各 32 bit/cycle；順序執行的程式取指頻寬足夠。
- **有限的 dual-issue（folding）**：某些 16-bit 指令可與前一條在同一 cycle 完成（§5.8）。`ACTLR.DISFOLD`（bit 2）可關閉（預設 0 = 開）。

### 5.2 結果延遲（result-use penalty）規則

某些指令的結果有 2 cycle 延遲；**下一條指令**拿它當來源運算元就多 1 cycle。來源運算元包括：ALU 的任何來源暫存器、LDR/LDM 用來算位址的暫存器（POP 的 sp）、STR/STM 用來算位址的暫存器（**不含**要存的資料暫存器）。

| 類別 | 週期 | 結果延遲（下一條用就 +1） |
|---|---|---|
| 一般 ALU（ADD/SUB/AND/ORR/EOR/BIC/MOV/CMP…） | 1 | 無 |
| Operand2 移位為 `LSL #0～#3` | 1 | 無 |
| Operand2 為其他移位（`LSL #4`、`LSR #n`、`ASR`、`ROR`） | 1 | **有** |
| 修飾立即值需移位（非 `0x000000XY/0x00XY00XY/0xXY00XY00/0xXYXYXYXY`） | 1 | **有** |
| 上述「複雜」運算加 `S` | 1 | **一定 +1**（即使下一條不用旗標） |
| `ADD/SUB #imm12`（ADDW/SUBW）、`MOV/MOVS #imm`、`MOVW` | 1 | 無 |
| `LSL/LSR/ASR/ROR` 獨立移位指令（立即值或暫存器移位量） | 1 | 無 |
| `UBFX / SBFX / BFI` | 1 | 無 |
| `SEL` | 1 | **有** |
| `MUL / MLA / MLS / UMULL / SMULL / UMLAL / SMLAL` | 1 | **有**（MAC 連鎖例外，見 §5.3） |
| `SDIV / UDIV` | 2～11（§5.4） | 有 |
| `LDR` / `LDM` / `POP` 的最後一個暫存器 | 1 / 暫存器 | **有**（只有最後一個暫存器） |
| `STR`（含 `STR r0,[r1,r2,LSL #2]`） | 1 | — |
| `CLZ / RBIT / REV / UXTB…` | 1 ⚠️未驗證（datasheet 未逐條列出） | ⚠️未驗證 |
| DSP SIMD 加減（SADD16、UQADD8…） | 1 ⚠️未驗證 | ⚠️未驗證 |
| `SMLAD / SMUAD` 等 DSP 乘法 | 1 ⚠️推測同乘法類 | ⚠️推測有 |

datasheet 範例：

```asm
and  r0, r1, r2, lsl #4
mov  r3, r4            @ 無懲罰（不相依）

and  r0, r1, r2, lsl #4
mov  r3, r0            @ +1（用到複雜運算結果）

ands r0, r1, r2, lsl #4
mov  r3, r4            @ +1（複雜 + S 一定懲罰）
```

### 5.3 乘法與 MAC

- 乘法器在 cycle n 需要乘數，n+1 需要累加值，n+2 產出結果。
- **連續 MAC 累加到同一暫存器（或暫存器對）**、乘數來自其他暫存器時可以每 cycle 一條：

```asm
mla   r0, r1, r2, r3
mla   r3, r1, r2, r0      @ 用前一條結果當累加值：無懲罰
umlal r0, r1, r4, r5
umlal r2, r3, r6, r7
umlal r0, r1, r4, r5      @ 交錯兩組 64 位元累加：1 條/cycle
```

- `ADD r2, r0, r1, LSL #23` 後接 `MLA r3, r4, r5, r2`：ADD 的懲罰被吸收（MLA 第 2 cycle 才要累加值）。

### 5.4 除法

- 令 n = |被除數| 與 |除數| 最高位 1 的位置差。n < 0（商為 0）→ 2 cycle；否則 **4 + ⌊n/4⌋ cycle**（最多約 11）。結果下一條就用 +1。
- 例：`1000 / 10`（bit 9 vs bit 3，n = 6）→ 5 cycle；`0xFFFFFFFF / 1`（n = 31）→ 11 cycle。
- 比 Hazard3（18～19 cycle）快很多，但除以常數仍應交給編譯器（變成 `UMULL` + 移位，約 2～3 cycle ⚠️估算）。

### 5.5 Load / Store

- Load：每個暫存器 1 cycle，加上可能的 1 cycle 結果延遲（`LDR` 的目的暫存器、`LDM/POP` 的**最後一個**暫存器）。
- 例：`LDR r7, [r5, r6]` → r7 有延遲；`LDMIA r0, {r1-r7}` → 只有 r7 有延遲，r1–r6 沒有。
- Store：1 cycle（即使用 3 個暫存器定址）。`STM/PUSH` n 個暫存器 ≈ n cycle ⚠️未驗證（datasheet 只寫 store 1 cycle）。
- 目標記憶體忙（例如與取指搶同一 SRAM bank）會更慢。
- 位址暫存器是「來源運算元」：`ldr r0, [r0]` 後立刻 `ldr r1, [r0]`（指標追逐）一定 +1。

### 5.6 分支

datasheet 公式（L、U、F、K 各為 0 或 1）：

- **taken 分支** = 基本時間 + 2 + L + U − (K & F)
- **not-taken 分支** = 基本時間 + 1 − F
- 基本時間：`B/B<cond>/BL/BX/MOV pc,Rx` 為 0；由 load 產生的分支（`LDR pc`、`POP {…,pc}`、`LDM …,pc`）為該 load 的時間。

| 參數 | = 1 的條件 |
|---|---|
| L | 分支來自 load（`POP {pc}`、`LDR pc,…`） |
| U | 目標位址**不是 word 對齊**且目標是 **32-bit 指令**，且分支前一條不是 PUSH/POP |
| F | 可 fold：分支是 `B`、`B<cond>` 或 `BX LR`；前一條是 16-bit；前一條是循序執行到的（或 word 對齊）；前一條本身沒被 fold |
| K | 「分支前一條執行前就已知會跳」：除非「條件分支且前一條會設旗標」，否則為 1 |

datasheet 延遲迴圈例：

```asm
10000002: movs r5, #100
10000004: subs r5, r5, #1      @ 迴圈起點 word 對齊
10000006: bne  0x10000004      @ 總共 299 cycle（taken 2 cycle，最後一次 not-taken 0）
```

同一段程式起點換成 `0x10000002`（未對齊）變 300 cycle；在 `subs` 和 `bne` 之間插一條無關的 16-bit 指令（例如 `mov r1, r2`）也是 300 cycle —— 等於**那條插入的指令免費**（K=F=1，taken 分支只要 1 cycle）。

實用規則：

1. 條件分支前一條**不要**是設旗標的指令時（把 `subs`/`cmp` 往前移，中間夾一條 16-bit 無關指令），taken 分支只要 1 cycle。
2. 分支目標（含 `BL` 之後那條，它是 return 的目標）最好是 word 對齊，或是 16-bit 指令。迴圈開頭用 `.p2align 2`。
3. `POP {r4-r7, pc}` = 5（load 5 個暫存器）+ 2 + 1 = 約 8 cycle；`BX LR` 可 fold，返回較便宜。
4. 能展開迴圈 / 內聯就能完全省掉分支成本。
5. datasheet 的公式裡沒有分支預測項（不像 Hazard3 的單 entry BTB 會「學」迴圈分支）：以上面公式估算即可。

### 5.7 IT 區塊

- IT 區塊中**條件不成立**的指令仍佔 1 cycle；成立的指令與無條件版相同。
- `IT` 後面接 16-bit 指令時，`IT` 本身 0 cycle（被 fold）。
- 所以短的 if/else（1～2 條）用 IT（編譯器自動）通常比分支（taken 2 cycle）划算。

### 5.8 Dual issue（folding）

- 16-bit `NOP`（`0xBF00`，不是 `0x46C0` 的 `mov r8,r8`）接在 16-bit 指令後會 fold → 0 cycle；可用來對齊分支目標而不花時間。
- not-taken 分支也像 NOP 一樣可以 fold。
- 兩條多週期指令 fold 時最多重疊 1 cycle。
- fold 條件：前一條是 16-bit、循序到達（或 word 對齊）、前一條本身沒被 fold。

### 5.9 協處理器

- `MCR`/`MCRR` 1 cycle；`MRC`/`MRRC` 1 cycle + 1 延遲；`CDP` 1 cycle（無 stall 時）。
- GPIO coprocessor（p0）：pico-sdk 在 Arm 上預設 `PICO_USE_GPIO_COPROCESSOR=1`，`gpio_put()` 等用 `mcr p0, …`，比 SIO MMIO 寫入更快。直接 API：`#include "hardware/gpio_coproc.h"`，例如 `gpioc_lo_out_set(mask)`、`gpioc_lo_out_xor(mask)`、`gpioc_bit_out_put(pin, val)`。

### 5.10 取指與記憶體

- 主 SRAM 以 4 word 為一組做 striping：位址 mod 16 不同的 word 在不同 bank。
- prefetcher 通常領先執行約 2 個 word（8 bytes）。**從 SRAM 執行時，讀取「自身位址 + 8（mod 16）」附近的 literal 可能與取指衝突 +1 cycle**（datasheet 範例 `LDR R8,[PC,#32]`）。
- 從 flash（XIP，0x10000000 起）執行：cache 命中時接近 SRAM；miss 要走 QSPI，延遲大很多 ⚠️具體 cycle 數未驗證。熱迴圈放 SRAM。
- 兩核或 DMA 同時存取同一 SRAM bank / 同一下游 port 時會仲裁等待（細節見 `multicore-sync.md` B0、B9）。

---

## 6. GCC inline asm 與獨立 `.S` 函式（Arm）

### 6.1 Inline asm 語法與 constraint

```c
asm volatile ("指令模板" : 輸出 : 輸入 : clobber);
```

| constraint | 意義（ARM 段，GCC 文件） |
|---|---|
| `"r"` | 任意核心暫存器 |
| `"l"` | Thumb 下的 r0–r7（要 16-bit 編碼時） |
| `"h"` | r8–r15 |
| `"=r"` / `"+r"` / `"=&r"` | 只寫 / 讀寫 / early-clobber 輸出 |
| `"t"` | VFP 單精度暫存器 s0–s31（`float`） |
| `"w"` | VFP 64-bit d 暫存器 |
| `"I"` | 資料處理指令可用的立即值（GCC 文件以 ARM 狀態描述「0～255 旋轉偶數位」；Thumb-2 規則不同 ⚠️，建議只對小常數用，否則改傳暫存器） |
| `"J"` | −4095～4095 |
| `"M"` | 0～32 |
| `"i"` / `"n"` | 編譯期常數 |
| `"m"` / `"Q"` | 記憶體運算元 / 單一暫存器定址的記憶體（exclusive 用） |
| clobber `"cc"` | asm 會改 APSR 旗標（用了 `S` 後綴、`CMP`、`TST`、`Q`/`GE` 旗標的指令時必寫） |
| clobber `"memory"` | asm 讀寫了沒列出的記憶體 |

- GCC 文件說 `-masm-syntax-unified`「對 Thumb-2 沒有影響」；pico-sdk 仍用 `pico_default_asm(...)` / `pico_default_asm_volatile(...)` 巨集自動在前面加 `.syntax unified\n`。自己寫 inline asm 時用 SDK 巨集或自己加上，最保險。
- 指令模板裡的 IT 區塊要自己寫 `it` 指令（或依賴組譯器 `-mimplicit-it`，⚠️預設值依工具鏈而異）。

```c
#include <stdint.h>
#include "pico/platform/compiler.h"   // pico_default_asm*（pico_stdlib 已間接引入）

static inline uint32_t my_rbit(uint32_t x) {
    uint32_t r;
    pico_default_asm ("rbit %0, %1" : "=r"(r) : "r"(x));
    return r;
}

static inline uint32_t my_ctz(uint32_t x) {          // x == 0 時回傳 32
    uint32_t r;
    pico_default_asm ("rbit %0, %1\n\t"
                      "clz  %0, %0" : "=r"(r) : "r"(x));
    return r;
}

static inline uint32_t my_bfi(uint32_t x, uint32_t v) {   // x[15:8] = v[7:0]
    pico_default_asm ("bfi %0, %1, #8, #8" : "+r"(x) : "r"(v));
    return x;
}

static inline int32_t sat_add(int32_t a, int32_t b) {     // QADD 會設 Q 旗標 → "cc"
    int32_t r;
    pico_default_asm ("qadd %0, %1, %2" : "=r"(r) : "r"(a), "r"(b) : "cc");
    return r;
}

static inline uint64_t umul64(uint32_t a, uint32_t b) {
    uint32_t lo, hi;
    pico_default_asm ("umull %0, %1, %2, %3" : "=&r"(lo), "=&r"(hi) : "r"(a), "r"(b));
    return ((uint64_t)hi << 32) | lo;
}

static inline float my_vsqrt(float x) {
    float r;
    pico_default_asm ("vsqrt.f32 %0, %1" : "=t"(r) : "t"(x));
    return r;
}

static inline uint32_t get_primask(void) {
    uint32_t r;
    pico_default_asm_volatile ("mrs %0, PRIMASK" : "=r"(r));
    return r;
}

static inline void compiler_barrier(void) { __asm volatile ("" ::: "memory"); }
```

規則（同 RISC-V）：有副作用（讀計數器、MMIO、改 PRIMASK）加 `volatile`；改記憶體加 `"memory"`；改旗標加 `"cc"`；改了未列出的暫存器寫進 clobber（`"r12"`）；指令必須在 `-march` 內（DSP 指令需 `+dsp`）。

### 6.2 Cycle 計數：DWT CYCCNT（首選）

```c
#include <stdint.h>
#include "hardware/structs/m33.h"   // m33_hw（PPB_BASE 0xE0000000）、M33_* 位元定義

static inline void cyc_init(void) {
    m33_hw->demcr     |= M33_DEMCR_TRCENA_BITS;         // 1) 開 DWT/ITM（DEMCR bit 24）
    m33_hw->dwt_cyccnt = 0;                             // 2) 歸零（可省略，用差值即可）
    m33_hw->dwt_ctrl  |= M33_DWT_CTRL_CYCCNTENA_BITS;   // 3) 開始計數（DWT_CTRL bit 0）
}
static inline uint32_t cyc_now(void) { return m33_hw->dwt_cyccnt; }   // 0xE0001004
```

| 暫存器 | 位址（Secure 視角） | SDK 名稱 |
|---|---|---|
| DEMCR | 0xE000EDFC | `m33_hw->demcr`、`M33_DEMCR_TRCENA_BITS`（0x01000000） |
| DWT_CTRL | 0xE0001000 | `m33_hw->dwt_ctrl`、`M33_DWT_CTRL_CYCCNTENA_BITS`（0x1）、`M33_DWT_CTRL_NOCYCCNT_BITS`（=1 表示沒有 CYCCNT） |
| DWT_CYCCNT | 0xE0001004 | `m33_hw->dwt_cyccnt`（32 位元，每個處理器 clock +1） |
| DWT_EXCCNT / LSUCNT / FOLDCNT | | `m33_hw->dwt_exccnt` / `dwt_lsucnt` / `dwt_foldcnt`（8-bit，需在 DWT_CTRL 開 `EXCEVTENA`/`LSUEVTENA`/`FOLDEVTENA`）：例外處理 cycle、load/store 額外 cycle、被 fold 的指令數 |

- CMSIS 寫法（連結 `cmsis_core`）：`DCB->DEMCR |= DCB_DEMCR_TRCENA_Msk; DWT->CYCCNT = 0; DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;`（舊名 `CoreDebug->DEMCR`、`CoreDebug_DEMCR_TRCENA_Msk` 仍有別名）。
- 每顆核心有自己的 DWT；在 core1 量要在 core1 上 `cyc_init()`。
- 150 MHz 下 32 位元約 28.6 秒回繞；無號相減 `t1 - t0` 自動處理一次回繞。
- 權限：PPB 只允許 privileged 存取（SDK 預設 Thread mode privileged，沒問題）。若 OTP 設了 secure debug disable（SPNIDEN = 0），Secure 狀態下的 DWT 計數可能被禁止 ⚠️推論；出廠預設是「fully open」。`pico-sdk.md` §10.3 也標了「實機未驗證」。

量測範本（同 RISC-V 版流程）：

```c
cyc_init();
uint32_t t0 = cyc_now(), t1 = cyc_now();
uint32_t overhead = t1 - t0;                 // 空測開銷（約幾個 cycle）

t0 = cyc_now();
volatile uint32_t sink = func_under_test(buf, n);   // 結果要被使用
t1 = cyc_now();
uint32_t cycles = (t1 - t0) - overhead;
```

- 多跑幾次取最小值或中位數；第一次常有 XIP cache miss。
- 量測期間要排除中斷可包 `uint32_t s = save_and_disable_interrupts(); … restore_interrupts(s);`。

### 6.3 替代：SysTick（24 位元向下計數）

```c
#include "hardware/structs/m33.h"
m33_hw->syst_rvr = 0x00FFFFFF;                                   // 最大 reload
m33_hw->syst_cvr = 0;                                            // 寫任意值 = 清 0（也清 COUNTFLAG）
m33_hw->syst_csr = M33_SYST_CSR_CLKSOURCE_BITS                   // 1 = 處理器時脈
                 | M33_SYST_CSR_ENABLE_BITS;                     // 不設 TICKINT → 不產生中斷
uint32_t a = m33_hw->syst_cvr;  /* … */  uint32_t b = m33_hw->syst_cvr;
uint32_t elapsed = (a - b) & 0x00FFFFFF;                         // 向下計數，所以 a - b
```

- 150 MHz 下約 0.11 秒回繞一次；只適合短區段。若程式或 RTOS 已在用 SysTick，不要動它。
- µs 等級量測用 `time_us_32()` / `time_us_64()`（TIMER，兩種架構都可用，見 `pico-sdk.md` §10.2）。

### 6.4 獨立 `.S` 函式（可從 C 呼叫）

檔名用大寫 `.S`（先經 C 前處理器）。Thumb 函式必須讓符號位址 bit0 = 1：用 `.thumb_func`（或在 `.thumb` 下 `.type f, %function`）。

```asm
// sum4.S
// uint32_t sum4(const uint32_t *p, uint32_t n);   n 為 4 的倍數
// r0 = p, r1 = n；回傳 r0 = 總和

    .syntax unified
    .cpu    cortex-m33
    .thumb

    .section .time_critical.sum4, "ax"      // 放 SRAM；放 flash 用 .text.sum4
    .global  sum4
    .type    sum4, %function
    .thumb_func
    .p2align 2
sum4:
    push    {r4-r6, lr}             // 4 個暫存器 = 16 bytes，維持 8-byte 對齊
    movs    r2, #0                  // sum
    cbz     r1, 2f
    add     r1, r0, r1, lsl #2      // end = p + n*4（LSL #2：無結果延遲）
    .p2align 2
1:
    ldmia   r0!, {r3-r6}            // 4 cycle；只有 r6 有結果延遲
    add     r2, r2, r3
    add     r2, r2, r4
    add     r2, r2, r5
    add     r2, r2, r6              // 離 ldm 已 3 條，無 stall
    cmp     r0, r1
    bne     1b                      // 前一條設旗標 → K=0，taken 2 cycle
2:
    mov     r0, r2
    pop     {r4-r6, pc}
    .size    sum4, . - sum4
```

穩態估計（依 §5 規則推算 ⚠️估算）：`ldmia` 4 + 4×`add` 4 + `cmp` 1 + `bne` 2 = 約 11 cycle / 4 word（≈ 2.75 cycle/word）。逐 word `ldr r3,[r0],#4; add; cmp; bne` 約 1+1+1+2 = 5 cycle/word（`ldr` 結果下一條就用時再 +1）。

pico-sdk 自己的 `.S` 用 `#include "pico/asm_helper.S"`，提供巨集：`pico_default_asm_setup`（= `.syntax unified` / `.cpu cortex-m33` / `.fpu fpv5-sp-d16` / `.thumb`）、`regular_func name`（= `.global` + `.type %function` + `.thumb_func` + label）、`regular_func_with_section name`（放 `.text.name`）。

C 端與 CMake：

```c
#include <stdint.h>
uint32_t sum4(const uint32_t *p, uint32_t n);        // C++ 需 extern "C"
```

```cmake
project(xxx C CXX ASM)
add_executable(app main.c sum4.S)
```

用到 FPU callee-saved 暫存器的骨架：

```asm
f:
    push    {r4, lr}
    vpush   {s16-s17}               // s16–s31 是 callee-saved
    // ...
    vpop    {s16-s17}
    pop     {r4, pc}
```

常見指示詞：`.syntax unified`、`.thumb`、`.thumb_func`、`.cpu cortex-m33`、`.fpu fpv5-sp-d16`、`.global`、`.type sym, %function`（Arm 用 `%`，不是 `@`，因為 `@` 是 Arm 組語的註解符號）、`.size`、`.p2align 2`、`.section name, "ax"`、`.word`、`.ltorg`（在此處放 literal pool）。註解：`@` 或（.S 經前處理器時）`//`。

### 6.5 `__attribute__((naked))`

```c
__attribute__((naked)) uint32_t add3(uint32_t a, uint32_t b, uint32_t c) {
    __asm volatile (
        ".syntax unified\n"
        "add r0, r0, r1\n"
        "add r0, r0, r2\n"
        "bx  lr\n");
}
```

- 不產生序言 / 結語，函式體內**只能**放基本 asm（不能用 C 變數或擴展 asm 運算元）；自己負責 AAPCS 與返回。比寫 `.S` 省一個檔案。

### 6.6 看編譯器輸出

```sh
arm-none-eabi-objdump -d build/app.elf | less              # 反組譯（或直接看 pico_add_extra_outputs 產生的 .dis）
arm-none-eabi-objdump -dS build/app.elf                    # 原始碼交錯（需 -g；SDK Release 預設含 -g）
arm-none-eabi-objdump -d --disassemble=sum4 build/app.elf  # 只看一個函式（binutils 2.32+）
arm-none-eabi-objdump -h build/app.elf                     # section 位址 / 大小
arm-none-eabi-nm -S --size-sort build/app.elf
arm-none-eabi-gcc -O2 -mcpu=cortex-m33 -mthumb -march=armv8-m.main+fp+dsp -mfloat-abi=softfp -S foo.c -o foo.s
```

判讀重點：

- 位址 0x10xxxxxx = flash（XIP）；0x20xxxxxx = SRAM。Thumb 函式符號值的 bit0 為 1（例如 `0x10000235`），實際指令從偶數位址開始。
- 編碼 4 個 hex = 16-bit，8 個 hex = 32-bit 指令。
- 熱迴圈中找：`bl __aeabi_d*`（double 運算）、`bl __aeabi_*div`/`__aeabi_uidivmod`（不該出現，M33 有硬體除法）、`bl __popcountsi2`、`bl memcpy`、`vdiv.f32`、`sdiv/udiv`、`ldr` 後立刻用、literal pool 反覆載入同一常數、`push/pop` 太多（暫存器不夠用，spill）。
- `.word` 出現在函式尾端 = literal pool（不是指令）。

---

## 7. pico-sdk 的 Arm 建置

| 項目 | 值 / 做法 |
|---|---|
| 選平台 | `cmake -DPICO_BOARD=pico2 ..`（RP2350 預設 `rp2350-arm-s`）；或 `-DPICO_PLATFORM=rp2350-arm-s`。`-s` = Secure；另有 `rp2350-arm-ns`（Non-secure，進階用途 ⚠️未深入查證） |
| 工具鏈 | `arm-none-eabi-gcc`（`PICO_DEFAULT_GCC_TRIPLE arm-none-eabi`）；路徑 `PICO_TOOLCHAIN_PATH` |
| 共通旗標 | `-mcpu=cortex-m33 -mthumb -march=armv8-m.main+fp+dsp`；預設加 `-mcmse`（`PICO_NO_CMSE=1` 可關）；`-mfloat-abi=softfp`（`PICO_HARD_FLOAT_ABI=1` → `hard`）；`-ftls-model=local-exec` |
| Build type | Debug：`-Og`（`PICO_DEOPTIMIZED_DEBUG=1` → `-O0`）；Release / MinSizeRel 另加 `-g`（`PICO_DEBUG_INFO_IN_RELEASE` 預設 1）；最佳化等級來自 CMake GCC 預設（Release 通常 `-O3 -DNDEBUG` ⚠️以考場 `compile_commands.json` 為準） |
| float 實作 | `pico_float` 預設 `pico_vfp`（直接用 FPU 指令，並加 `-fno-math-errno` 讓 `sqrtf` 內聯成 `vsqrt`）；`pico_set_float_implementation(t pico_dcp)` 可改走 DCP（會加 `-msoft-float`，hard-float ABI 不支援） |
| double 實作 | `pico_double` 預設 `pico_dcp`（包裝 `__aeabi_dadd` 等到 DCP 協處理器） |
| CMSIS | `target_link_libraries(app cmsis_core)` + `#include "RP2350.h"`（CMSIS-Core 6 stub，只有 core 部分） |
| 放 SRAM | `__not_in_flash_func(f)`、`__time_critical_func(f)`（section `.time_critical.<name>`）、`__no_inline_not_in_flash_func(f)`；整個程式 `pico_set_binary_type(t copy_to_ram)` |
| 反組譯 | `pico_add_extra_outputs(t)` → `.dis`、`.map`、`.uf2`、`.hex`、`.bin` |
| 切換架構 | 同一份原始碼改 `PICO_PLATFORM` 重新建置（`rm -rf build` 或另開 build 目錄）；`picotool reboot -c arm` / `-c riscv` |

在 C 中判斷架構：

```c
#if defined(__arm__)          // Cortex-M33（__ARM_ARCH_8M_MAIN__ 也會定義）
#  include "hardware/structs/m33.h"
#elif defined(__riscv)        // Hazard3
#  include "hardware/riscv.h"
#endif
#if defined(__ARM_FEATURE_DSP)
#  include <arm_acle.h>
#endif
```

---

## 8. C 位元操作 → Arm 指令（延伸 `riscv-hazard3.md` §8）

C 層的位元技巧、無分支寫法與 UB 表格**與架構無關**，直接沿用 `riscv-hazard3.md` §8.1～§8.4。這裡只列 Arm 特有的對應與差異。

### 8.1 慣用寫法與期望的 Arm 指令

下表為 GCC `-O2` 的**典型**輸出，版本間可能不同，一律用 objdump 確認 ⚠️未在考場工具鏈逐一驗證。

| C | 期望指令 |
|---|---|
| `(x >> 4) & 0xFFF` | `ubfx r0, r0, #4, #12` |
| `(int32_t)(x << 20) >> 24` | `sbfx r0, r0, #4, #8` |
| `(x & ~(0xFFu << 8)) \| ((v & 0xFF) << 8)` | `bfi r0, r1, #8, #8` |
| `x & ~(0xFFu << 8)` | `bic r0, r0, #0xFF00`（或 `bfc`） |
| `a & ~b` / `a \| ~b` | `bic` / `orn` |
| `x \| (1u << n)`（n 常數） | `orr r0, r0, #(1<<n)` |
| `x \| (1u << n)`（n 變數） | `movs r2, #1` + `lsls r2, r1` + `orrs`（Thumb-2 的 Operand2 不能用暫存器指定移位量，所以要分開寫） |
| `(x >> n) & 1` | `lsrs` + `and #1`（n 常數：`ubfx r0, r0, #n, #1`） |
| `__builtin_clz(x)` | `clz` |
| `__builtin_ctz(x)` | `rbit` + `clz` |
| `__builtin_popcount(x)` | 沒有指令：可能呼叫 libgcc `__popcountsi2` 或展開 SWAR ⚠️ → 熱點自己寫 SWAR（`riscv-hazard3.md` §8.2 `popcount32`） |
| `__builtin_bswap32(x)` | `rev` |
| `__builtin_bswap16(x)` | `rev16` + `uxth` |
| `(int16_t)__builtin_bswap16(x)` | `revsh` |
| 位元反轉 | 沒有 `__builtin`（GCC）→ `__rbit()`（GCC 14 `<arm_acle.h>`）、CMSIS `__RBIT()` 或 inline asm `rbit` |
| `(x << n) \| (x >> (-n & 31))` | `rsb` + `ror`（左旋 = 右旋 32−n） |
| `(x << 7) \| (x >> 25)` | `ror r0, r0, #25` |
| `(uint8_t)x` / `(int16_t)x` | `uxtb` / `sxth` |
| `a < b ? a : b` | `cmp` + `it` + `mov`（無 min 指令） |
| `x < -128 ? -128 : (x > 127 ? 127 : x)` | 可能辨識成 `ssat r0, #8, r0` ⚠️；確定要用就寫 `__ssat(x, 8)` |
| `x < 0 ? 0 : (x > 255 ? 255 : x)` | `usat r0, #8, r0` ⚠️同上，`__usat(x, 8)` |
| `x < 0 ? -x : x` | `cmp` + `it lt` + `rsblt`，或 `eor/sub` 配 `asr #31` ⚠️ |
| `a * b + c` / `c - a * b` | `mla` / `mls` |
| `(uint64_t)a * b` | `umull` |
| `(int32_t)(((int64_t)a * b) >> 32)` | `smull` 取高位（DSP：`smmul`） |
| `(int32_t)(((int64_t)a * b) >> 16)`（Q16.16 乘） | `smull` + `lsrs` + `orr …, lsl #16` ⚠️ |
| `x / 10u` | `umull`（乘魔數）+ `lsrs`，不會用 `udiv` |
| `a / b`、`a % b`（變數） | `sdiv`（+ `mls` 取餘） |
| `p[i]`（uint32） | `ldr r0, [r1, r2, lsl #2]` |
| `*p++` | `ldr r0, [r1], #4` |
| `switch` 連續 case | `tbb` / `tbh` 跳表 |
| 短 if/else | `it` 區塊 |
| `x == 0` 時跳 | `cbz` |
| `float` 運算 | `vadd.f32/vmul.f32/vdiv.f32`，softfp 下前後有 `vmov s,r`/`vmov r,s` |
| `sqrtf(x)` | `vsqrt.f32`（pico_vfp 加了 `-fno-math-errno`） |
| `double` 運算 | `bl __aeabi_dadd` 等（被 SDK 包到 DCP） |
| `(int)f` | `vcvt.s32.f32` |

### 8.2 Arm 與 RISC-V 在 C 層級的差異

| 項目 | Arm Cortex-M33 | Hazard3 |
|---|---|---|
| 非對齊 `*(uint32_t*)(buf+1)` | 一般記憶體可（較慢）；但若編譯器用 `LDRD/LDM`（例如 `uint64_t` 或結構複製）會 **UsageFault**；周邊必 fault | 一律 trap |
| 暫存器移位 ≥ 32 | `LSL/LSR` → 0、`ASR` → 符號位 | 取 mod 32 |
| 除以 0 | 商 0（預設不 trap） | 商全 1 |
| `char` | 無號（AAPCS） | 無號（psABI） |
| `float` | 硬體 | 軟體模擬 |
| 旗標 | 有 N/Z/C/V/Q/GE，`adds/adc` 做多精度 | 無，用 `sltu` |
| 有號溢位 | 硬體回繞（C 中 UB） | 同 |

- 仍然建議用 `memcpy(&v, p, 4)` 讀非對齊資料：可攜、編譯器會產生正確（通常是單一 `ldr`）的程式碼。
- `volatile`、整數提升、優先序陷阱與 RISC-V 完全相同（`riscv-hazard3.md` §8.4）。

### 8.3 MMIO

與 RISC-V 相同：`volatile`、RP2350 周邊原子別名 `+0x1000` XOR / `+0x2000` SET / `+0x3000` CLR、`hw_set_bits` / `hw_clear_bits` / `hw_xor_bits` / `hw_write_masked`，SIO 不支援別名（見 `riscv-hazard3.md` §8.5、`pico-sdk.md` §2.2）。Arm 額外有：

- Cortex-M33 私有周邊在 PPB（0xE0000000，`m33_hw`），Non-secure 別名 0xE0020000（`m33_ns_hw`）。NVIC 暫存器只能 word 存取。
- 寫 MMIO 後要確保生效再繼續（例如改中斷設定後立刻 `WFI`、改 VTOR）時加 `__dsb()`（必要時 `__isb()`）。

---

## 9. 組語層級最佳化清單（Arm）

1. **先量測**：DWT CYCCNT（§6.2），扣空測開銷、多次取最小值。
2. **放 SRAM**：`__not_in_flash_func` / `.time_critical.*`，避開 XIP miss。
3. **避開結果延遲**：`LDR` 的結果、乘法結果、「複雜 Operand2」結果都不要下一條就用；中間插無關指令（指標遞增、另一個 load）。
4. **用 LDM / LDRD / 後索引**：`ldmia r0!, {r3-r6}` 一條載 4 個 word，只有最後一個暫存器有延遲；`ldr r3, [r0], #4` 省掉 `add`。
5. **展開 + 多累加器**：打斷相依鏈（FPU 尤其重要：VADD 相依 2 cycle/條，交錯 1 cycle/條）。
6. **分支成本**：taken ≈ 2 cycle。把 `cmp`/`subs` 和 `bne` 之間塞一條 16-bit 無關指令（K=F=1 → taken 1 cycle，那條指令免費）；迴圈頂端 `.p2align 2`；分支目標用 16-bit 指令或 word 對齊；短條件用 IT。
7. **倒數迴圈**：`subs r1, r1, #1; bne` 省掉 `cmp`（但 subs 緊接 bne 時 K=0）；或用結束指標比較。
8. **Operand2 免費移位**：`add r0, r1, r2, lsl #2`（LSL #0～3 無延遲）；`rsb r0, r1, r1, lsl #3` = ×7。
9. **位元欄位**：`UBFX/SBFX/BFI`（datasheet 明列無延遲；`BFC` 未列 ⚠️）取代 shift+mask 序列。
10. **乘除**：迴圈內避 `sdiv/udiv`（2～11 cycle），除以常數交給編譯器；MAC 連鎖（`mla`/`umlal`/`smlad`）每 cycle 一條。
11. **DSP SIMD**：int16/uint8 資料用 `__smlad`、`__uqadd8`、`__usad8`、`__sadd16`，一條處理 2～4 個元素；資料要 word 對齊打包。
12. **浮點**：用 `float` 不用 `double`；`x / c` → `x * inv_c`；`-Wdouble-promotion`；FPU 與整數指令可重疊（VDIV 14 cycle 期間整數核心繼續跑）。
13. **型別**：迴圈索引 / 運算用 32 位元；`uint8_t`/`uint16_t` 運算常多 `uxtb`/`uxth`。
14. **`restrict`**、把不變量移出迴圈、減少 spill（函式內同時活著的變數 ≤ 約 10 個核心暫存器）。
15. **大量搬資料**：DMA（`pico-dma.md`）；兩核分工（`multicore-sync.md`）。
16. **最佳化等級**：`-O2` 平衡；`-O3` 展開多、程式變大，XIP 上未必快；`-Os` 最小。`__attribute__((optimize("O3")))`、`#pragma GCC unroll 4` 可單點調整。
17. **正確性第一**：用相同輸入比對最佳化前後的輸出（0、1、0xFFFFFFFF、0x80000000、n=0、n=1、非 4 倍數長度、非對齊指標）。

### 9.1 FPU 交錯累加範例

```c
// 4 個累加器打斷 VADD 相依鏈；n 為 4 的倍數
float sum_f32(const float *x, uint32_t n) {
    float s0 = 0.f, s1 = 0.f, s2 = 0.f, s3 = 0.f;
    for (uint32_t i = 0; i < n; i += 4) {
        s0 += x[i]; s1 += x[i + 1]; s2 += x[i + 2]; s3 += x[i + 3];
    }
    return (s0 + s1) + (s2 + s3);     // 浮點加法順序改變 → 結果最後幾位可能不同（判題若要求位元一致要小心）
}
```

---

## 10. 除錯清單（Arm）

| 症狀 | 可能原因 | 檢查 |
|---|---|---|
| `Error: selected processor does not support 'smlad'` / `'vsqrt.f32'` | `-march` 沒有 `+dsp` / `+fp`；或在 RP2040（M0+）目標 | 看實際旗標；`PICO_PLATFORM` |
| `Error: instruction not supported in Thumb16 mode` / `lo register required` | 16-bit 指令用了 r8–r12，或忘了 `.syntax unified` 導致 `adds/movs` 解讀不同 | 加 `.syntax unified`；改用 `.w` 或 low register |
| `Error: thumb conditional instruction should be in IT block` | 條件指令前沒寫 `it` | 補 `it`/`ite` |
| `Error: branch out of range` / `relocation truncated` | `cbz` 向後或超過 126 bytes；16-bit 條件分支太遠 | 改 `cmp` + `beq.w` |
| link：`undefined reference to 'f'` | `.S` 沒 `.global`、沒加進 CMake、C++ 沒 `extern "C"`、`project()` 沒 ASM | `nm` |
| 呼叫 `.S` 函式立刻 HardFault（UsageFault INVSTATE） | 符號 bit0 = 0（漏 `.thumb_func`/`.type %function`）、`bx` 到偶數位址 | `nm` 看位址是否為奇數 |
| 回傳值錯 / 呼叫後 C 變數錯亂 | 用了 r4–r11 沒保存；lr 被 `bl` 覆蓋沒存；s16–s31 沒存 | 對照 §1.3；`push {r4-…, lr}` |
| 呼叫 printf 或 double 函式後當機 / 輸出亂 | sp 不是 8-byte 對齊（push 奇數個暫存器） | push 偶數個暫存器 |
| softfp 下 `.S` 收到的 float 參數是垃圾 | 從 s0 讀，但 softfp 參數在 r0 | `vmov s0, r0` |
| hard / softfp 連結錯誤（`uses VFP register arguments`） | 物件檔 float ABI 不一致 | 全部用同一 `PICO_HARD_FLOAT_ABI` |
| UsageFault NOCP | 未開 CPACR 就用 FPU / DCP / GPIO 協處理器（例如在 SDK runtime 初始化前執行、或 core1 未經 SDK 啟動） | 經 `multicore_launch_core1` 啟動；或自行設 `CPACR` |
| UsageFault UNALIGNED | `LDRD/LDM/STRD/STM` 非對齊（常見：`uint64_t*` / struct 指標指向 `buf+1`），或 `CCR.UNALIGN_TRP=1` | `memcpy`；檢查 `m33_hw->cfsr` 的 `M33_CFSR_UFSR_UNALIGNED_BITS` |
| BusFault PRECISERR | 存取不存在的位址、周邊非對齊、周邊時脈 / reset 未開 | `m33_hw->bfar`（`BFARVALID` 時有效） |
| UsageFault DIVBYZERO | 設了 `CCR.DIV_0_TRP` | 預設除以 0 回 0，不會 fault |
| `ldrex/strex` 迴圈永遠失敗 | 位址不在 SRAM（RP2350 global exclusive monitor 只在 SRAM 支援） | 原子變數放 SRAM（`multicore-sync.md` B4.4） |
| `dwt_cyccnt` 一直是 0 | 沒設 `DEMCR.TRCENA` 或 `CYCCNTENA`；在另一核設的；`NOCYCCNT=1` | §6.2 |
| 量到的 cycle 忽大忽小 | XIP miss、中斷、另一核 / DMA 搶 bus、分支目標對齊不同 | 放 SRAM、關中斷、多次取最小、`.p2align` |
| 改了程式碼對齊後時間變 1 cycle | §5.6 的 U / F 條件 | 正常現象 |
| `-O2` 後行為改變 | UB；MMIO 沒 `volatile`；inline asm 漏 `"cc"`/`"memory"` | §6.1、`riscv-hazard3.md` §8.4 |
| ISR 中用 float 後主程式 float 值錯 | FP 上下文未保存 ⚠️（FPCCR.ASPEN/LSPEN 狀態見 §12.2） | 讀 `m33_hw->fpccr` 確認 |

HardFault 時看「出事的 PC」：例外堆疊框第 7 個 word（`[sp + 24]`）是被打斷的 PC；`m33_hw->cfsr`（0xE000ED28）、`hfsr`（0xE000ED2C）、`mmfar`、`bfar` 指出原因。pico-sdk 不會在 `SHCSR` 啟用 MemManage/BusFault/UsageFault（原始碼中未設定），所以它們依架構規則升級為 HardFault（`isr_hardfault`），讀 `cfsr` 即可分辨真正原因。

主機端先驗證 C 邏輯：與 RISC-V 版相同，`gcc -O2 -Wall -Wextra -fsanitize=undefined,address` 在容器內跑單元測試。

---

## 11. 速查：C 慣用寫法 → Cortex-M33 指令

| C | 指令 |
|---|---|
| `a & ~b` / `a \| ~b` | `bic` / `orn` |
| `(x >> l) & ((1u<<w)-1)` | `ubfx` |
| 有號欄位 | `sbfx` |
| 寫欄位 / 清欄位 | `bfi` / `bfc` |
| `__builtin_clz` / `ctz` | `clz` / `rbit`+`clz` |
| `__builtin_popcount` | 無（libgcc 或 SWAR） |
| `__builtin_bswap32` / `16` | `rev` / `rev16` |
| 旋轉 | `ror`（左旋用 32−n） |
| `(uint8_t)` / `(int16_t)` 轉型 | `uxtb` / `sxth` |
| min / max | `cmp` + `it` + `mov` |
| 夾限 int8/int16/uint8 | `ssat` / `usat`（`__ssat`/`__usat`） |
| `a*b+c` / `c-a*b` | `mla` / `mls` |
| 64 位元乘積 / 高 32 位 | `umull`/`smull` / `smmul` |
| 64 位元加減 | `adds`+`adc` / `subs`+`sbc` |
| `p[i]` / `*p++` | `ldr r, [b, i, lsl #2]` / `ldr r, [p], #4` |
| `x / 常數` | `umull` + 移位 |
| `x % 2^k`（無號） | `and` 或 `ubfx` |
| int16 內積 | `smlad`（`__smlad`） |
| uint8 飽和加 / SAD | `uqadd8` / `usad8` |
| float + − × ÷ √ | `vadd/vsub/vmul/vdiv/vsqrt.f32` |
| double | `bl __aeabi_d*`（DCP） |
| switch | `tbb`/`tbh` |

---

## 12. 例外、中斷與記憶體模型

### 12.1 向量表（pico-sdk `crt0.S`，`__vectors` / `__VECTOR_TABLE`）

| 偏移（word） | 內容 |
|---|---|
| 0 | 初始 MSP（`__StackTop`） |
| 1 | Reset（`_reset_handler`） |
| 2 / 3 | NMI / HardFault（`isr_nmi` / `isr_hardfault`） |
| 4 / 5 / 6 / 7 | MemManage / BusFault / UsageFault / SecureFault |
| 8–10 | 保留 |
| 11 | SVCall（`isr_svcall`） |
| 12 | DebugMonitor |
| 13 | 保留 |
| 14 / 15 | PendSV / SysTick（`isr_pendsv` / `isr_systick`） |
| 16 + n | 外部 IRQ n（`isr_irq0` …，RP2350 共 52 個） |

- 每個 entry 的 bit0 必須為 1（Thumb），否則進 handler 就 INVSTATE fault。VTOR 依 Secure / Non-secure 分開（VTOR_S / VTOR_NS）。
- 平常用 SDK API 掛 handler：`irq_set_exclusive_handler(IRQ, fn)`、`irq_add_shared_handler(...)`、`irq_set_enabled(IRQ, true)`（見 `pico-sdk.md` §7.5）。

### 12.2 例外進入 / 返回

- 硬體自動把 **r0–r3、r12、lr、pc、xPSR**（8 word，32 bytes）推到目前堆疊，並把堆疊對齊到 8 bytes；同時平行抓取向量。所以 **ISR 就是普通的 AAPCS C 函式**（不需要 `__attribute__((interrupt))`；SDK 的 `__isr` 巨集是空的）。
- 有 FP 上下文時（CONTROL.FPCA=1）堆疊框再加 s0–s15、FPSCR、保留 word（共 +18 word）。**Lazy stacking**：先只保留空間，ISR 真的用到 FPU 指令才存；不用 FPU 的 ISR 沒有額外成本。lazy 保存可被更高優先權的例外打斷，之後重來。
- 是否啟用由 `FPCCR.ASPEN`（自動設 FPCA）與 `FPCCR.LSPEN`（lazy）決定；datasheet 暫存器表列兩者 reset 為 0，與 Arm 一般預設不同 ⚠️未驗證實際值 → 需要時讀 `m33_hw->fpccr`（`M33_FPCCR_ASPEN_BITS` / `M33_FPCCR_LSPEN_BITS`）。
- 進入中斷延遲：Arm 常引用約 12 cycle（無 FP 上下文、零等待記憶體）⚠️未在一手文件中查到 M33 的確切數字；handler 在 flash 時還要加 XIP 延遲 → 時間敏感 ISR 放 SRAM。
- **Tail-chaining**：一個 ISR 結束時若有另一個等待中的例外，直接跳過去，不做出棧 / 入棧。**Late arrival**：入棧期間來了更高優先權的例外，直接改跑它。
- 返回：硬體在 lr 放 **EXC_RETURN**（`0xFFFFFFxx` 這類特殊值），handler 執行 `bx lr` 或 `pop {…, pc}` 時由硬體辨識並出棧。不要在 ISR 中把 lr 當一般資料覆蓋。
- 進 handler 時為 Handler mode（一律 privileged、用 MSP）。
- 出棧後的 PC 在 `[sp+24]`、xPSR 在 `[sp+28]`（HardFault 除錯用）。

### 12.3 NVIC 優先權與遮罩

- RP2350 M33 有 **4 個優先權位元 → 16 級**，數值放在 8-bit 欄位的**高 4 位**：有效值 0x00、0x10、…、0xF0。**數值越小越優先**。pico-sdk：`PICO_HIGHEST_IRQ_PRIORITY 0x00`、`PICO_DEFAULT_IRQ_PRIORITY 0x80`、`PICO_LOWEST_IRQ_PRIORITY 0xff`；`irq_set_priority(num, prio)`。
- Reset / NMI / HardFault 的優先權固定且高於所有可設定的例外。
- 優先權高（數值小）的可以打斷正在執行的低優先權 ISR（nesting）；同優先權不互相打斷，依 IRQ 編號決定誰先。

| 遮罩 | 效果 | 用法 |
|---|---|---|
| `PRIMASK` | =1 時擋住所有可設定優先權的例外（只剩 NMI、HardFault） | `cpsid i` / `cpsie i`；SDK `save_and_disable_interrupts()`（= `mrs %0, PRIMASK; cpsid i`）/ `restore_interrupts(s)`（= `msr PRIMASK, s`） |
| `BASEPRI` | ≠0 時擋住優先權數值 **≥ BASEPRI** 的例外；0 = 不擋 | `msr BASEPRI, r0`（CMSIS `__set_BASEPRI(0x40)`）；只擋低優先權、讓高優先權 ISR 照常進來 |
| `BASEPRI_MAX` | 只在新值會「更嚴格」時才寫入 | 巢狀臨界區 |
| `FAULTMASK` | 擋住除 NMI（與 Secure HardFault）外的一切 | 罕用 |

- 這些都只影響**本核**。跨核保護仍需 spinlock / `critical_section_t`（`multicore-sync.md` B5、B6）。
- 改完 `BASEPRI`/`PRIMASK` 立刻要求生效時，一般不需額外屏障（`cpsid` 自身即生效）；改 NVIC 暫存器後若要確保下一條指令前生效，加 `__dsb(); __isb();`。

### 12.4 TrustZone-M（簡述）

- 兩個安全狀態：Secure / Non-secure；處理器**一律重置進 Secure**。許多 PPB 暫存器（VTOR、SysTick、MPU、PRIMASK、BASEPRI、CONTROL、MSP/PSP…）依狀態 banked；Secure 端可經 0xE0020000 別名存取 Non-secure 版本（`m33_ns_hw`）。
- `rp2350-arm-s` 建出的程式在 **Secure** 狀態執行；SAU 重置為停用且 `ALLNS=0` → 除少數 PPB 區外全部視為 Secure。一般考題不需要碰 TrustZone。
- `-mcmse` 只是讓編譯器支援 `cmse_*` intrinsic 與 `__attribute__((cmse_nonsecure_entry))`，對普通程式碼沒影響。
- Secure 呼叫 Non-secure 等跨狀態行為（`SG`、`BXNS`、`BLXNS`）屬進階內容，此處略。

### 12.5 MPU（簡述）

- Armv8-M PMSA：每個安全狀態 8 個 region（Secure 8 + Non-secure 8），以 base / limit 位址定義（32-byte 粒度 ⚠️依 Armv8-M 架構，未在 RP2350 文件逐字確認），可設讀寫 / 執行權限與記憶體屬性。違規 → MemManage fault。
- 用途：堆疊溢位保護、禁止執行資料區。另有 `MSPLIM`/`PSPLIM` 堆疊下限暫存器，越界直接 fault（Armv8-M 新增）。
- 預設（MPU 關）使用架構預設記憶體映射：周邊區、PPB、0xE0100000 以上不能執行。

### 12.6 Exclusive 存取與記憶體屏障

```c
#include <stdint.h>
// 原子加（等同 C11 atomic_fetch_add 的 relaxed 版；跨核時要搭配屏障）
static inline uint32_t atomic_add_u32(volatile uint32_t *p, uint32_t v) {
    uint32_t old, tmp, fail;
    __asm volatile (
        ".syntax unified\n"
        "1: ldrex  %0, [%3]\n"
        "   add    %1, %0, %4\n"
        "   strex  %2, %1, [%3]\n"      // 成功時 %2 = 0
        "   cmp    %2, #0\n"
        "   bne    1b\n"
        : "=&r"(old), "=&r"(tmp), "=&r"(fail)
        : "r"(p), "r"(v)
        : "cc", "memory");
    return old;
}
```

- 實務上用 C11 `<stdatomic.h>`（RP2350 上 1/2/4 byte 對齊的 atomic 由 exclusive 指令實作，見 `multicore-sync.md` B4.4）或 SDK spinlock，比手寫安全。
- Cortex-M33 的**本地** exclusive monitor 不記位址：任何 `STREX` 都視為與前一個 `LDREX` 相符（granule = 整個位址空間）。跨核由 RP2350 的 global exclusive monitor 負責（只在 SRAM；16-byte granule；SDK 軟體 spinlock 會設 `ACTLR.EXTEXCLALL`）。
- 例外進入 / 返回會清除本地 monitor，所以中斷打斷 LDREX/STREX 之間時 STREX 會失敗並重試 ⚠️依 Armv8-M 架構描述；可手動 `clrex`。
- `LDREX` 與 `STREX` 之間保持簡短，不要放其他 load/store 或函式呼叫。
- 屏障：`__dmb()`（順序）、`__dsb()`（完成）、`__isb()`（清管線）。SDK 的 `__mem_fence_acquire()` / `__mem_fence_release()` 目前都是 `__dmb()`。Armv8-M 另有 `LDA/STL`、`LDAEX/STLEX` 帶 acquire/release 語意。
- `__compiler_memory_barrier()` 只擋編譯器重排，不產生指令。

---

## 13. RISC-V（Hazard3）↔ Arm（Cortex-M33）對照表

### 13.1 指令

| 功能 | Hazard3 | Cortex-M33 |
|---|---|---|
| 加 / 減 / 立即值 | `add`、`sub`、`addi`（無 `subi`） | `add`、`sub`、`add/sub #imm`（ADDW/SUBW 0～4095） |
| 反向減 / 取負 | `sub rd, x0, rs`（`neg`） | `rsb rd, rs, #0`（`neg`） |
| 位元 | `and/or/xor`、`andn/orn/xnor`（Zbb） | `and/orr/eor`、`bic/orn`；xnor = `eor`+`mvn` |
| not | `xori rd, rs, -1` | `mvn` |
| 移位 | `sll/srl/sra`（+i） | `lsl/lsr/asr`，或 Operand2 內嵌移位 |
| 旋轉 | `rol/ror/rori` | `ror`（無 rol） |
| 移位加（索引） | `sh1add/sh2add/sh3add` | `add rd, base, i, lsl #1/2/3` |
| clz / ctz / popcount | `clz` / `ctz` / `cpop` | `clz` / `rbit`+`clz` / 無 |
| byte 反轉 / bit 反轉 | `rev8` / `brev8`+`rev8` | `rev` / `rbit` |
| 擴展 | `sext.b/sext.h/zext.h` | `sxtb/sxth/uxth`（`uxtb`） |
| 欄位取出 / 插入 | `srli`+`andi`（或 `h3.bextmi`） / 多條 | `ubfx`/`sbfx` / `bfi`/`bfc` |
| 單一位元 | `bset/bclr/binv/bext` | `orr/bic/eor #(1<<n)`、`tst` / `ubfx #n,#1` |
| min / max | `min/max/minu/maxu` | `cmp`+`it`+`mov` |
| 比較設值 | `slt/sltu` | `cmp` + `it` + `mov`（或 `movs`/`adc` 技巧） |
| 乘 / 高位 | `mul` / `mulh/mulhu/mulhsu` | `mul` / `smull/umull`（高位在 RdHi）、`smmul` |
| 乘加 | 無（`mul`+`add`） | `mla/mls/umlal/smlal`、DSP `smlad` |
| 除 / 餘 | `div/divu`（18～19 cycle）/ `rem/remu` | `sdiv/udiv`（2～11 cycle）/ `sdiv`+`mls` |
| 除以 0 | 商全 1 | 商 0 |
| 飽和 | 無 | `ssat/usat`、`qadd/qsub`、SIMD |
| 32 位元常數 | `lui`+`addi`（注意進位） | `movw`+`movt` 或 literal pool |
| load / store | `lw/lh/lhu/lb/lbu`、`sw/sh/sb` | `ldr/ldrh/ldrsh/ldrb/ldrsb`、`str/strh/strb` |
| 多暫存器 | `cm.push/cm.pop`（Zcmp；SDK 2.2.0 需 zcb_zcmp 工具鏈，否則逐條 sw/lw；2.3.x 若 gcc 支援 Zcmp 會自動用） | `push/pop`、`ldm/stm`、`ldrd/strd` |
| 後索引 | 無（另寫 `addi`） | `ldr r, [p], #4` |
| 條件分支 | `beq/bne/blt/bge/bltu/bgeu rs1, rs2` | `cmp` + `b<cond>`；`cbz/cbnz` |
| 呼叫 / 返回 | `jal ra, f` / `ret` | `bl f` / `bx lr` 或 `pop {…, pc}` |
| 條件執行 | 無（分支） | `it` 區塊 |
| 跳表 | 編譯器產生位址表 + `jr` | `tbb/tbh` |
| 記憶體屏障 | `fence`（Hazard3 上為 no-op） | `dmb` / `dsb` |
| 指令屏障 | `fence.i` | `isb` |
| 原子 | `lr.w/sc.w`、`amo*.w` | `ldrex/strex`、`ldaex/stlex`（無 AMO） |
| 關中斷 | `csrci mstatus, 8` | `cpsid i` |
| 睡眠 / 事件 | `h3.block` / `h3.unblock`（`__wfe`/`__sev`） | `wfe` / `sev`、`wfi` |

### 13.2 ABI、計數器、其他

| 項目 | Hazard3（ilp32） | Cortex-M33（AAPCS，softfp） |
|---|---|---|
| 參數 | a0–a7 | r0–r3 |
| 回傳 | a0（a1） | r0（r1） |
| callee-saved | s0–s11、sp | r4–r11、sp、s16–s31 |
| 返回位址 | ra（x1） | lr（r14） |
| 暫存 | t0–t6、a* | r0–r3、r12 |
| sp 對齊 | 16 bytes | 8 bytes（公開介面） |
| 64 位元參數 | 任意相鄰對 | 偶數號暫存器對 |
| float 參數 | 整數暫存器（無 FPU） | 整數暫存器（softfp） |
| cycle counter | `mcycle`/`mcycleh` CSR；先 `csrci mcountinhibit, 5` | DWT `CYCCNT`；先 `DEMCR.TRCENA` + `DWT_CTRL.CYCCNTENA` |
| 讀計數器 | `csrr %0, mcycle` | `m33_hw->dwt_cyccnt`（MMIO load） |
| 指令退休數 | `minstret` | 無直接對應（DWT 有 CPI/LSU/FOLD/EXC 8-bit 輔助計數） |
| 中斷控制器 | Xh3irq（52 IRQ、16 級） | NVIC（52 IRQ、16 級） |
| 非對齊存取 | trap | LDR/STR 可、LDRD/LDM fault |
| 浮點 | 軟體 | FPU（float）+ DCP（double） |
| 編譯旗標 | `-march=rv32imac_zicsr_zifencei_zba_zbb_zbs_zbkb -mabi=ilp32`（SDK 2.2.0 預設；zcb_zcmp 工具鏈才加 `_zca_zcb_zcmp`；2.3.x 依序試 `-mcpu=hazard3-rp2350` → zcb_zcmp → rv32imac） | `-mcpu=cortex-m33 -mthumb -march=armv8-m.main+fp+dsp -mfloat-abi=softfp` |
| 工具鏈前綴 | `riscv32-unknown-elf-`（或 `riscv32-pico-elf-`） | `arm-none-eabi-` |
| `PICO_PLATFORM` | `rp2350-riscv` | `rp2350-arm-s`（預設） |
| 架構巨集 | `__riscv` | `__arm__`、`__ARM_ARCH_8M_MAIN__` |
| 組語註解 | `#`（.S 也可 `//`） | `@`（.S 也可 `//`） |
| 函式型別指示詞 | `.type f, @function` | `.type f, %function` + `.thumb_func` |
| 分支成本 | 預測對 1、錯 2；`jal/jalr` 2 | taken 約 2（可降到 1）、not-taken 0～1 |
| load-use | +1 | +1 |
| 乘法 | 1，結果可直接用 | 1，結果延遲 1（MAC 連鎖除外） |

---

## 14. 向模型提問的範本

範本 1：把 C 函式改寫成 Cortex-M33 組語

```
目標：RP2350 Cortex-M33（Armv8-M Mainline、Thumb-2、DSP、單精度 FPU），pico-sdk 旗標
-mcpu=cortex-m33 -mthumb -march=armv8-m.main+fp+dsp -mfloat-abi=softfp。
請把下面的 C 函式改寫成可從 C 呼叫的 .S 函式，函式名 {{函式名}}，放在 section {{.text.名稱 或 .time_critical.名稱}}。
要求：.syntax unified / .thumb / .thumb_func；遵守 AAPCS（r0–r3 參數、r0 回傳、r4–r11 與 s16–s31 需保存、
sp 8-byte 對齊、softfp 下 float 參數在 r0–r3）；善用 LDM/後索引、UBFX/BFI、Operand2 移位、{{DSP 指令如 SMLAD}}；
每行註解暫存器用途；依 RP2350 datasheet §3.7.4.9 規則估算穩態每次迴圈 cycle
（load/乘法/複雜 Operand2 結果下一條就用 +1、taken 分支 2+L+U−(K&F)、SDIV 4+n/4）。
C 原始碼：
{{貼上 C 程式碼}}
```

範本 2：讀 objdump 找瓶頸

```
以下是 {{函式名}} 用 arm-none-eabi-gcc {{版本}} {{-O 等級}}（rp2350-arm-s）編譯的 objdump，
函式位址 {{0x10xxxxxx（flash）或 0x20xxxxxx（SRAM）}}，DWT CYCCNT 量到 {{數字}} cycle（輸入大小 {{n}}）。
請逐條標出熱迴圈每條指令在 Cortex-M33 上的 cycle（含結果延遲、分支公式、對齊造成的 U、fold），
找出可改善處（bl __aeabi_d* 的 double、sdiv/udiv、vdiv、ldr 後立刻使用、literal pool 重複載入、
未用 UBFX/BFI/LDM/後索引/SMLAD、push/pop spill、從 flash 執行），並給出修改後的 C 或組語與預期 cycle。
objdump：
{{貼上}}
```

範本 3：位元 / DSP 需求轉成正確 C

```
我需要在 RP2350 Cortex-M33 上對 {{資料型別與陣列，例如 uint8_t 影像 / int16_t 音訊}} 做：{{運算描述}}。
請給出：(1) 可攜、無 UB 的 C 參考版本；(2) 使用 <arm_acle.h> intrinsic（__smlad、__uqadd8、__usad8、__ssat 等）
或 CMSIS（cmsis_core，__SMLAD 等）的加速版本，說明資料打包與對齊前提；(3) 兩版的正確性比對測試
（含邊界值、飽和、奇數長度）；(4) 指出整數提升、移位 ≥32、非對齊 LDRD/LDM、Q 旗標黏著等陷阱。
```

範本 4：除錯 HardFault / 錯誤結果

```
在 RP2350 Cortex-M33（pico-sdk，Secure，rp2350-arm-s）執行 {{程式 / 函式}} 時發生 {{HardFault / 結果錯 / 卡住}}。
CFSR={{值}}、HFSR={{值}}、BFAR={{值或無}}、堆疊框中的 PC={{值}}、LR={{值}}。相關原始碼與反組譯如下。
請依序檢查：UsageFault 位元（INVSTATE=Thumb bit、NOCP=CPACR 未開、UNALIGNED=LDRD/LDM 非對齊、UNDEFINSTR）、
BusFault（周邊位址 / 非對齊 / 未開時脈）、AAPCS（r4–r11、lr、s16–s31 保存，sp 8-byte 對齊，softfp float 在 r0）、
inline asm constraint 與 "cc"/"memory" clobber、volatile、exclusive 變數是否在 SRAM。列出最可能原因與驗證方法。
{{貼上程式碼 / objdump}}
```

範本 5：最佳化並驗證（含量測碼）

```
請把 {{函式名}} 在 RP2350 Cortex-M33 上最佳化，目標降低 DWT CYCCNT 量測值，輸出必須與原版完全一致
（{{浮點是否需位元一致}}）。限制：{{例如：不能改介面 / 只能改某檔 / 需通過 OJ}}。
請提供：(1) 修改後程式（考慮放 SRAM、展開與多累加器、LDM、UBFX/BFI、DSP SIMD、float 取代 double、
避免除法、分支對齊）；(2) 量測碼（m33_hw->demcr |= M33_DEMCR_TRCENA_BITS、dwt_ctrl |= M33_DWT_CTRL_CYCCNTENA_BITS、
扣空測開銷、多次取最小、量測時關中斷）；(3) 正確性測試輸入（0、1、0xFFFFFFFF、0x80000000、n=0、n=1、
非 4 倍數長度、非對齊指標）；(4) 依 datasheet §3.7.4.9 規則估算 cycle 並說明理由。
原始碼：
{{貼上}}
```
