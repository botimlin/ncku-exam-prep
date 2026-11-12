# RISC-V 組合語言（RP2350 / Hazard3）與 C 位元操作參考

- 用途：上機考第二大題（demo 檔名 `demo_asm.c`，內容為 bitwise 操作）相關的背景參考。可貼給考場 LLM 當 context，也可給考生自己查。涵蓋 RV32I 基本指令、Hazard3 在 RP2350 上啟用的擴充、指令週期數、GCC inline asm / `.S` 檔、pico-sdk RISC-V 建置、cycle 計數、C 位元技巧與陷阱、最佳化與除錯清單。
- 適用版本：RP2350（Raspberry Pi Pico 2 等）的 Hazard3 RISC-V 核心（RP2350 使用 Hazard3 commit `86fc4e3`）；RP2350 datasheet build 2026-01-10；pico-sdk master（2026-11 查閱）；GCC 14 系列 RISC-V 工具鏈。考場實際環境以考題文件為準。
- 來源（實際查閱）：
  - RP2350 datasheet §2.1.3、§3.8（Hazard3 指令參考、§3.8.7 指令週期、§3.8.8 設定參數、§3.8.9 CSR）、§4.2 SRAM：https://datasheets.raspberrypi.com/rp2350/rp2350-datasheet.pdf
  - Hazard3 repo（Readme、doc/sections/introduction.adoc、instruction_timings.adoc、configuration_and_integration.adoc）：https://github.com/Wren6991/Hazard3
  - pico-sdk：`cmake/preload/toolchains/pico_riscv_gcc.cmake`、`cmake/preload/toolchains/util/set_flags.cmake`、`cmake/preload/platforms/rp2350-riscv.cmake`、`src/rp2_common/hardware_base/include/hardware/address_mapped.h`、`src/rp2350/hardware_regs/include/hardware/regs/addressmap.h`、`src/rp2_common/hardware_riscv/include/hardware/riscv.h`、`src/rp2_common/pico_platform_sections/include/pico/platform/sections.h`、`src/cmake/on_device.cmake`、`test/sync_interop_test/interop_harness.c`：https://github.com/raspberrypi/pico-sdk
  - pico-bootrom-rp2350 `src/main/riscv/riscv_bootrom_rt0.S`：https://github.com/raspberrypi/pico-bootrom-rp2350
  - RISC-V psABI 呼叫慣例 `riscv-cc.adoc`：https://github.com/riscv-non-isa/riscv-elf-psabi-doc
  - GCC Machine Constraints（RISC-V 段）：https://gcc.gnu.org/onlinedocs/gcc/Machine-Constraints.html
  - RISC-V 官方規格入口（demo README 指定）：https://riscv.org/specifications/ratified/ 、https://github.com/riscv/riscv-isa-manual
- 最後更新：2026-11

> 標記說明：`⚠️未驗證` = 查不到一手來源或依版本而異，使用前請用 objdump / 實測確認。

---

## 0. 三十秒重點

1. pico-sdk 對 RP2350 Hazard3 的編譯旗標**依 SDK 版本不同**（版本看 `build/generated/pico_base/pico/version.h` 的 `PICO_SDK_VERSION_STRING`）：
   - **2.2.0**：預設 `-march=rv32imac_zicsr_zifencei_zba_zbb_zbs_zbkb -mabi=ilp32`。硬體也支援 Zcb/Zcmp，但只有 `-DPICO_COMPILER=pico_riscv_gcc_zcb_zcmp` 時才改用 `rv32ima_zicsr_zifencei_zba_zbb_zbs_zbkb_zca_zcb_zcmp`。
   - **2.3.0 / 2.3.1**：`cmake/preload/toolchains/pico_riscv_gcc.cmake` 依序試 `-mcpu=hazard3-rp2350` → `-march=rv32ima_…_zca_zcb_zcmp` → `-march=rv32imac_…_zbkb`，用第一個 gcc 編得過的。
2. 沒有 F/D（沒有硬體浮點）、沒有 Zbc（無 clmul）、沒有 Zicond（無 czero）、沒有 V。`float`/`double` 全部是軟體模擬，很慢。
3. 3 級管線 F/X/M。大多數 ALU、Zba/Zbb/Zbs/Zbkb、`mul`、`mulh*` 都是 1 cycle；`div/rem` 18～19 cycle；load 後緊接著使用結果會多 1 cycle；分支預測正確 1 cycle、錯誤 2 cycle；`jal/jalr` 2 cycle。
4. Hazard3 遇到非自然對齊的 load/store 會產生例外（不是變慢，是直接 trap）。`-mstrict-align`：pico-sdk 2.2.0、2.3.0 **沒有**加；2.3.1 起預設加（`-DPICO_NO_STRICT_ALIGN=1` 可關）。不論版本，packed struct、`(uint32_t *)` 指標轉型都要自己避免（改用 `memcpy`）：指標轉型時編譯器假設位址已對齊，加了 `-mstrict-align` 也照樣 trap。
5. `mcycle`/`minstret` 開機預設是停的（`mcountinhibit` 重置值 0x5）。量測前先 `csrci mcountinhibit, 1`（開 cycle）或 `csrci mcountinhibit, 5`（兩個都開）。
6. 周邊暫存器原子別名：`+0x1000` XOR、`+0x2000` SET、`+0x3000` CLEAR（SIO 不適用）。pico-sdk：`hw_xor_bits` / `hw_set_bits` / `hw_clear_bits`。
7. 熱點程式放 SRAM：`__not_in_flash_func(f)` / `__time_critical_func(f)`（section `.time_critical.*`），或整個程式 `pico_set_binary_type(target copy_to_ram)`。

---

## 1. 暫存器與 ABI（ILP32）

| 暫存器 | ABI 名 | 用途 | 跨呼叫保存者 |
|---|---|---|---|
| x0 | zero | 恆為 0，寫入無效 | — |
| x1 | ra | 返回位址 | caller（呼叫者） |
| x2 | sp | 堆疊指標 | callee（被呼叫者） |
| x3 | gp | global pointer（crt0 設為 `__global_pointer$`） | 不可配置，勿動 |
| x4 | tp | thread pointer | 不可配置，勿動 |
| x5–x7 | t0–t2 | 暫存 | caller |
| x8 | s0 / fp | 保存 / frame pointer | callee |
| x9 | s1 | 保存 | callee |
| x10–x11 | a0–a1 | 參數 / 回傳值 | caller |
| x12–x17 | a2–a7 | 參數 | caller |
| x18–x27 | s2–s11 | 保存 | callee |
| x28–x31 | t3–t6 | 暫存 | caller |

呼叫慣例要點（psABI）：

- 整數參數依序放 a0–a7，放不下才上堆疊。比 32 位元窄的整數（`uint8_t`、`int16_t`）由呼叫端依型別的正負號擴展到 32 位元後再傳。
- 64 位元純量（`uint64_t`）用一對暫存器：低 32 位在編號小的（例如 a0），高 32 位在下一個（a1）。若只剩一個參數暫存器，低半在暫存器、高半上堆疊。（變參 `...` 的 64 位元參數才要求偶數對齊的暫存器對。）
- 回傳值：與「第一個同型別參數」的傳法相同 → 32 位元回傳 a0；64 位元回傳 a0（低）/a1（高）。大於 2×XLEN（8 bytes）的 struct 以參考傳遞（呼叫端配置記憶體並傳指標）。
- `sp` 在函式進入時必須 16-byte（128-bit）對齊（ILP32E 才是 4-byte）。
- 寫 `.S` 函式時：可以隨意用 a0–a7、t0–t6；若要用 s0–s11 或呼叫其他函式（會覆蓋 ra），必須先存到堆疊、離開前還原。
- 壓縮指令（C/Zca）大多只能用 x8–x15（s0、s1、a0–a5），把熱點變數放在這些暫存器可以讓程式更小。

---

## 2. 指令格式與立即值範圍（RV32I）

| 格式 | 位元配置（31→0） | 例 | 立即值 |
|---|---|---|---|
| R | funct7[31:25] rs2[24:20] rs1[19:15] funct3[14:12] rd[11:7] opcode[6:0] | `add` | 無 |
| I | imm[11:0][31:20] rs1 funct3 rd opcode | `addi`、`lw`、`jalr` | 12-bit 有號：-2048～2047（-0x800～0x7ff） |
| I（移位） | funct7 shamt[24:20] rs1 funct3 rd opcode | `slli/srli/srai` | 0～31 |
| S | imm[11:5][31:25] rs2 rs1 funct3 imm[4:0][11:7] opcode | `sw` | 12-bit 有號 |
| B | imm[12\|10:5] rs2 rs1 funct3 imm[4:1\|11] opcode | `beq` | 偶數，-4096～4094（±4 KiB） |
| U | imm[31:12] rd opcode | `lui`、`auipc` | 20-bit（左移 12） |
| J | imm[20\|10:1\|11\|19:12] rd opcode | `jal` | 偶數，±1 MiB |

壓縮版範圍較小：`c.beqz/c.bnez` ±256 B、`c.j/c.jal` ±2 KiB、`c.addi/c.li/c.andi` 立即值 -32～31。

### 2.1 32 位元常數的組成（li 的展開）

`addi` 的 12-bit 立即值會被**正負號擴展**，所以 `lui` 的高 20 位要先補進位：

```asm
# li a0, 0x12345fff  →  低 12 位 0xfff 會被當成 -1
lui  a0, 0x12346        # a0 = 0x12346000（已加 1 補償）
addi a0, a0, -1         # a0 = 0x12345fff
```

規則：`hi = (x + 0x800) >> 12`，`lo = x - (hi << 12)`（lo 落在 -2048～2047）。pico-sdk `riscv_encode_imm_u_hi()` 就是用 `x += (x & 0x800) << 1` 處理此進位。

---

## 3. RV32I 指令總表

### 3.1 算術 / 邏輯 / 比較

| 指令 | 語意 | 備註 |
|---|---|---|
| `add/sub rd, rs1, rs2` | rd = rs1 ± rs2 | 溢位不 trap，直接回繞 |
| `addi rd, rs1, imm` | rd = rs1 + imm | 沒有 `subi`，用負的 imm |
| `and/or/xor` 與 `andi/ori/xori` | 位元運算 | imm 會正負號擴展：`andi a0,a0,-16` = 清低 4 位 |
| `slt/sltu rd, rs1, rs2` | rd = (rs1 < rs2) ? 1 : 0 | 有號 / 無號 |
| `slti/sltiu rd, rs1, imm` | 同上，立即值 | `sltiu` 的 imm 先正負號擴展再當無號比較 |
| `sll/srl/sra rd, rs1, rs2` | 左移 / 邏輯右移 / 算術右移 | 只取 rs2[4:0]，即移位量 mod 32 |
| `slli/srli/srai rd, rs1, sh` | 立即值移位 | sh = 0～31 |
| `lui rd, imm20` | rd = imm20 << 12 | |
| `auipc rd, imm20` | rd = pc + (imm20 << 12) | PC 相對定址 |

沒有旗標暫存器（沒有 carry/overflow flag）。64 位元加法要自己算進位：

```asm
# (a1:a0) + (a3:a2) → (a1:a0)
add  a0, a0, a2
sltu t0, a0, a2      # 低位相加溢位 → 進位 1
add  a1, a1, a3
add  a1, a1, t0
```

### 3.2 Load / Store

| 指令 | 寬度 | 擴展 | 對齊需求（Hazard3） |
|---|---|---|---|
| `lb` | 8 | 正負號擴展 | 任意 |
| `lbu` | 8 | 零擴展 | 任意 |
| `lh` | 16 | 正負號擴展 | 2-byte |
| `lhu` | 16 | 零擴展 | 2-byte |
| `lw` | 32 | — | 4-byte |
| `sb / sh / sw` | 8/16/32 | 存 rs2 的低位 | 同上 |

- 語法：`lw rd, imm(rs1)`、`sw rs2, imm(rs1)`；位址 = rs1 + imm（-2048～2047）。
- RV32 沒有 `lwu`、`ld`。
- Hazard3 一律小端序（little-endian）。
- 非自然對齊 → 例外（mcause 4 = load address misaligned，6 = store/AMO address misaligned）。datasheet 明說 Hazard3 不支援非對齊存取（只產生標準例外）。

### 3.3 分支與跳躍

| 指令 | 條件 / 動作 |
|---|---|
| `beq/bne rs1, rs2, L` | 相等 / 不等 |
| `blt/bge rs1, rs2, L` | 有號 < / ≥ |
| `bltu/bgeu rs1, rs2, L` | 無號 < / ≥ |
| `jal rd, L` | rd = pc+4（壓縮版 +2）；pc = L |
| `jalr rd, imm(rs1)` | rd = pc+4；pc = (rs1+imm) & ~1 |

### 3.4 記憶體順序

| 指令 | Hazard3 行為 |
|---|---|
| `fence`（= `fence iorw, iorw`） | Hazard3 沒有 store buffer、假設記憶體循序一致 → 執行為 no-op ⚠️未查證（SDK 仍會用，為可攜性） |
| `fence.i`（Zifencei） | 清除分支目標緩衝與 prefetch buffer；寫入程式碼到 RAM 後要執行它，之後的取指才看得到新內容 |

### 3.5 常用 pseudo-instruction 對照

| Pseudo | 實際指令 |
|---|---|
| `nop` | `addi x0, x0, 0` |
| `li rd, imm` | `addi rd, x0, imm`（12-bit 內）或 `lui`+`addi` |
| `la rd, sym` | `auipc rd, %pcrel_hi(sym)` + `addi rd, rd, %pcrel_lo(...)`（非 PIC） |
| `mv rd, rs` | `addi rd, rs, 0`（壓縮成 `c.mv`） |
| `not rd, rs` | `xori rd, rs, -1` |
| `neg rd, rs` | `sub rd, x0, rs` |
| `seqz rd, rs` | `sltiu rd, rs, 1` |
| `snez rd, rs` | `sltu rd, x0, rs` |
| `sltz rd, rs` / `sgtz rd, rs` | `slt rd, rs, x0` / `slt rd, x0, rs` |
| `beqz/bnez rs, L` | `beq/bne rs, x0, L` |
| `bltz/bgez/blez/bgtz rs, L` | 與 x0 比較（`blez`/`bgtz` 交換運算元） |
| `bgt/ble/bgtu/bleu a, b, L` | `blt/bge/bltu/bgeu b, a, L`（交換運算元） |
| `j L` | `jal x0, L` |
| `jal L` | `jal ra, L` |
| `jr rs` | `jalr x0, 0(rs)` |
| `jalr rs` | `jalr ra, 0(rs)` |
| `ret` | `jalr x0, 0(ra)` |
| `call sym` | `auipc ra, hi` + `jalr ra, lo(ra)`（linker relax 可能縮成 `jal`） |
| `tail sym` | `auipc t1, hi` + `jalr x0, lo(t1)`（尾呼叫，不存 ra） |
| `zext.b rd, rs` | `andi rd, rs, 255` |
| `csrr rd, csr` | `csrrs rd, csr, x0` |
| `csrw csr, rs` | `csrrw x0, csr, rs` |
| `csrs / csrc csr, rs` | `csrrs / csrrc x0, csr, rs` |
| `csrwi / csrsi / csrci csr, uimm5` | 立即值版（uimm 0～31） |
| `rdcycle / rdcycleh / rdinstret rd` | `csrrs rd, cycle/cycleh/instret, x0`（新版 binutils 可能要求 `-march` 含 `zicntr` ⚠️未驗證；改寫 `csrr rd, mcycle` 最保險） |

### 3.6 M 擴充（乘除）

| 指令 | 語意 | Hazard3 on RP2350 cycles |
|---|---|---|
| `mul` | 低 32 位 | 1 |
| `mulh / mulhsu / mulhu` | 64 位乘積的高 32 位（有號×有號 / 有號×無號 / 無號×無號） | 1 |
| `div / rem` | 有號除 / 餘 | 18 或 19（視正負號修正） |
| `divu / remu` | 無號除 / 餘 | 18 |

- 除以 0 不 trap：`div`/`divu` 回傳全 1（-1 / 0xFFFFFFFF），`rem`/`remu` 回傳被除數。`INT_MIN / -1` 回傳 `INT_MIN`，餘數 0。（C 語言層級這些仍是 UB。）
- RP2350 設定：`MUL_FAST=1`、`MUL_FASTER=1`、`MULH_FAST=1`、`MULDIV_UNROLL=2`。依 Hazard3 文件，`MUL_FASTER` 讓 `mul` 結果回到 stage 2，延遲 1 cycle（相依指令可緊接）。`mulh*` 的相依延遲是否同為 1 ⚠️未驗證。
- 除以常數時編譯器會改用 `mulhu` + 移位（1～數 cycle），遠快於 `divu`（18 cycle）。

### 3.7 A 擴充（原子）

- `lr.w` / `sc.w`（`sc.w` 成功時 rd = 0）、`amoswap/amoadd/amoand/amoor/amoxor/amomin/amomax/amominu/amomaxu.w`（每次嘗試 4 cycle 起）。
- 只在主 SRAM 有效。在其他區域：`lr/sc` 迴圈會永遠失敗，`amo*.w` 會 Store/AMO Fault。跨核共享鎖請用 pico-sdk 的 `spin_lock_*` API（`hardware_sync`）：RP2350 因 erratum E2 預設改用軟體 spinlock，鎖變數本身也在 SRAM；不要直接操作 SIO 硬體 spinlock 暫存器（詳見 `multicore-sync.md`）。

---

## 4. Hazard3 在 RP2350 上啟用的擴充（已對照 datasheet §3.8 / §3.8.8）

| 擴充 | 狀態 | 內容 |
|---|---|---|
| RV32I | 有 | 基本整數 |
| M | 有 | 乘除 |
| A | 有 | 原子（AHB5 exclusive） |
| C（= Zca） | 有 | 16-bit 壓縮指令 |
| Zicsr | 有 | CSR 指令 |
| Zifencei | 有 | `fence.i` |
| Zba | 有 | `sh1add/sh2add/sh3add` |
| Zbb | 有 | 基本位元操作 |
| Zbs | 有 | 單一位元操作 |
| Zbkb | 有 | `pack/packh/brev8/zip/unzip`（另含與 Zbb 重疊的 rol/ror/andn 等） |
| Zcb | 有 | 更多 16-bit 指令（`c.lbu/c.lh/c.lhu/c.sb/c.sh/c.zext.b/c.not/c.sext.b/c.zext.h/c.sext.h/c.mul`） |
| Zcmp | 有 | `cm.push/cm.pop/cm.popret/cm.popretz/cm.mva01s/cm.mvsa01` |
| Xh3power | 有（自訂） | `h3.block`（`slt x0,x0,x0`）、`h3.unblock`（`slt x0,x0,x1`）、`msleep` CSR |
| Xh3bextm | 有（自訂） | `h3.bextm` / `h3.bextmi`：右移後取 1～8 位 |
| Xh3irq | 有（自訂） | 本地中斷控制器（52 條 IRQ、16 級優先權） |
| Xh3pmpm | 有（自訂） | M-mode PMP |
| Zbc（clmul） | **無**（`EXTENSION_ZBC=0`） | |
| Zbkx、Zilsd、Zclsd | **無**（RP2350 版 Hazard3 未列入；這些是 Hazard3 後續版本才有） | |
| F / D / V / Zicond | **無** | |
| 特權 | M-mode + U-mode（無 S-mode），PMP 8 個動態區 + 3 個固定區 | |

注意：Hazard3 repo master 分支的 Readme 列出更多擴充（Zbc、Zbkx、Zilsd…），那是新版核心的「可選」功能，**不是 RP2350 晶片上的設定**。以 datasheet 為準。

### 4.1 位元操作指令表（全部 1 cycle）

| 指令 | 擴充 | 語意 | 取代的 C 慣用寫法 / builtin |
|---|---|---|---|
| `andn rd, a, b` | Zbb | a & ~b | `a & ~b`（清除遮罩位） |
| `orn rd, a, b` | Zbb | a \| ~b | `a \| ~b` |
| `xnor rd, a, b` | Zbb | ~(a ^ b) | `~(a ^ b)` |
| `clz rd, a` | Zbb | 前導零數（a=0 → 32） | `__builtin_clz(a)`（C 中 a=0 為 UB） |
| `ctz rd, a` | Zbb | 尾端零數（a=0 → 32） | `__builtin_ctz(a)`（a=0 為 UB） |
| `cpop rd, a` | Zbb | 1 的個數 | `__builtin_popcount(a)` |
| `max / min rd, a, b` | Zbb | 有號最大 / 最小 | `a > b ? a : b`（int32_t） |
| `maxu / minu rd, a, b` | Zbb | 無號最大 / 最小 | 同上（uint32_t） |
| `sext.b / sext.h rd, a` | Zbb | 從 bit7 / bit15 正負號擴展 | `(int32_t)(int8_t)a`、`(int32_t)(int16_t)a` |
| `zext.h rd, a` | Zbb | 取低 16 位 | `(uint16_t)a`、`a & 0xFFFF` |
| `zext.b rd, a` | pseudo | = `andi rd, a, 255` | `(uint8_t)a` |
| `rol / ror rd, a, b` | Zbb/Zbkb | 循環左 / 右移 b[4:0] 位 | `(a << n) \| (a >> (-n & 31))` |
| `rori rd, a, sh` | Zbb/Zbkb | 立即值循環右移（無 `roli`，左移 n = `rori 32-n`） | `(a >> 7) \| (a << 25)` |
| `orc.b rd, a` | Zbb | 每個 byte：非 0 → 0xFF，0 → 0x00 | 找字串中的 0 byte（strlen/memchr） |
| `rev8 rd, a` | Zbb/Zbkb | 反轉 4 個 byte 順序 | `__builtin_bswap32(a)`（大小端轉換） |
| `sh1add rd, i, base` | Zba | (i << 1) + base | `&((uint16_t*)base)[i]`、`i*3`（`sh1add i,i,i`） |
| `sh2add rd, i, base` | Zba | (i << 2) + base | `&((uint32_t*)base)[i]`、`i*5` |
| `sh3add rd, i, base` | Zba | (i << 3) + base | `&((uint64_t*)base)[i]`、`i*9` |
| `bset / bseti rd, a, n` | Zbs | a \| (1 << n) | `a \| (1u << n)` |
| `bclr / bclri rd, a, n` | Zbs | a & ~(1 << n) | `a & ~(1u << n)` |
| `binv / binvi rd, a, n` | Zbs | a ^ (1 << n) | `a ^ (1u << n)` |
| `bext / bexti rd, a, n` | Zbs | (a >> n) & 1 | `(a >> n) & 1` |
| `pack rd, a, b` | Zbkb | {b[15:0], a[15:0]} | `(a & 0xFFFF) \| (b << 16)` |
| `packh rd, a, b` | Zbkb | {16'b0, b[7:0], a[7:0]} | `(a & 0xFF) \| ((b & 0xFF) << 8)` |
| `brev8 rd, a` | Zbkb | 每個 byte 內部位元反轉 | 查表反轉 byte；`rev8(brev8(x))` = 32 位元完整位元反轉（2 條指令） |
| `zip rd, a` | Zbkb | a 的低 16 位放偶數位、高 16 位放奇數位（交錯） | Morton code / 位元交錯迴圈 |
| `unzip rd, a` | Zbkb | zip 的反運算：偶數位 → 低半，奇數位 → 高半 | 拆分交錯位元 |
| `h3.bextm rd, a, b, n` | Xh3bextm | (a >> b[4:0]) & ((1<<n)-1)，n = 1～8 | `(a >> s) & mask`（短欄位） |
| `h3.bextmi rd, a, sh, n` | Xh3bextm | 立即值版 | 同上 |

- `bset/bclr/binv/bext` 的暫存器版只取 n[4:0]。`bseti` 可以設 bit 11 以上（`ori` 的 12-bit 立即值做不到，且 `ori` 會正負號擴展）。
- `h3.bextm` 是自訂指令，編譯器不會自動產生，要用 `.insn`（見 §6.4）。若考題要求可攜性或 judge 不在真硬體上跑，不要用。
- 編譯器會自動產生哪些：GCC 在 `-march` 含 zbb/zbs/zba 且 `-O1` 以上時，通常會把 `clz/ctz/popcount/bswap32/旋轉/min/max/andn/orn/xnor/sext/zext/bset/bclr/binv/bext/陣列索引 sh*add` 產生為對應指令。`pack/packh/zip/unzip/brev8` 是否自動產生 ⚠️未驗證（需要時用 inline asm）。一律用 objdump 確認。

### 4.2 Zcmp（函式序言 / 結語）

- `cm.push {ra, s0-sN}, -frame`：存 ra 與 s0 起連續的 s 暫存器，並降 sp（16-byte 對齊）。`cm.popret` = pop + ret；`cm.popretz` = pop + `li a0,0` + ret。
- 只能推 ra、s0…s11（s0-s10 這種 11 個不行，要推 12 個）。
- 用 `pico_riscv_gcc_zcb_zcmp` 工具鏈（`-march` 含 zcmp），或 SDK 2.3.x 搭配支援 Zcmp 的 gcc 時，反組譯看到 `cm.push`/`cm.popret` 是正常的編譯器輸出；SDK 2.2.0 預設 `-march` 不含 zcmp，不會產生。週期：`cm.push/cm.pop` = 1 + n（n = 暫存器數）。

---

## 5. Hazard3 效能特性（datasheet §3.8.7，假設匯流排無等待）

### 5.1 管線

| 階段 | 名稱 | 主要工作 |
|---|---|---|
| 1 | F（Fetch） | 取指資料、prefetch buffer、預解碼暫存器編號、分支預測比對 |
| 2 | X（Execute） | 解碼與執行、ALU 結果在此階段結束時可用、load/store 位址相位、分支目標、CSR 讀寫 |
| 3 | M（Memory） | load/store 資料相位、暫存器寫回 |

RP2350 設定 `REDUCED_BYPASS=0`（完整 bypass）→ 連續相依的 ALU 指令每 cycle 1 條，沒有 stall。

### 5.2 週期表

| 類別 | cycles | 說明 |
|---|---|---|
| ALU（add/sub/邏輯/移位/比較/lui/auipc） | 1 | |
| Zba / Zbb / Zbs / Zbkb 全部 | 1 | 包含 clz/ctz/cpop/rev8/rol/ror |
| `lw/lh/lhu/lb/lbu` | 1；下一條指令用到結果時 2 | load-use bubble 1 cycle |
| `sw/sh/sb` | 1 | |
| `mul`、`mulh*` | 1 | |
| `div/rem` | 18～19；`divu/remu` 18 | |
| 條件分支 | 預測正確 1，錯誤 2 | |
| `jal`、`jalr` | 2 | |
| 跳到「未 4-byte 對齊的 32-bit 指令」 | +1 | 因為要兩次對齊的取指 |
| CSR 讀寫 | 1 | 寫 PMP/trigger 類 CSR 為 3（Hazard3 repo 文件；datasheet 表未列） |
| `ecall/ebreak` | 3（到 mtvec） | `mret` 2 ⚠️未查證 |
| `lr.w/sc.w` | 1～2 | `amo*.w` 每次嘗試 4 起 |
| `cm.push/cm.pop` | 1+n | `cm.popret` 2+n（n≥2），n=1 時 4 |
| 壓縮指令 | 與對應 32 位元指令相同 | |

Load-use 細節（datasheet 註腳）：

- stage 2 的指令要用 stage 3 的 load 結果 → 插 1 個 bubble。例：`lw a0,0(a1)` 後立刻 `add a2,a0,a3`。
- **load 資料 → store 資料** 不算（都在 stage 3）：`lbu a3,(a1)` 後立刻 `sb a3,(a0)` 不 stall。
- **load 資料 → load 位址** 會 stall（指標追逐）：`lw a0,0(a0)` 後立刻 `lw a1,0(a0)`。
- `sc.w` 結果 → `beqz` 也會 stall。

### 5.3 分支預測器

- 單一 entry BTB：記住「最後一個被採用的向後分支」，下次遇到預測 taken；其他分支一律預測 not-taken。
- 預測 taken 但實際沒跳 → 清除 BTB，下次預測 not-taken。
- 典型迴圈：第一次迭代結尾錯一次（+1）、最後一次離開錯一次（+1），中間每次 1 cycle。
- datasheet 例：逐 byte 複製迴圈（`lbu`、`sb`、2 個 `addi`、`bltu`）穩態每次 5 cycle；複製 10 bytes 共 52 cycle。沒有預測器時每次 6 cycle。
- 只有最內層迴圈的向後分支受益；巢狀迴圈中，內層離開後外層分支會把 BTB 換掉。
- 陷阱：迴圈本體只有**一條 16-bit 指令**且 4-byte 對齊時，預測器不會生效（每次 3 cycle 而不是 2）⚠️未查證。解法：本體用 32-bit 指令（`.option norvc`）並 `.p2align 2`：

```asm
    .p2align 2
delay_cycles:            # a0 = 次數
    .option push
    .option norvc        # 強制 32-bit 編碼
    addi a0, a0, -1
    .option pop
    bgez a0, delay_cycles
    ret
```

### 5.4 記憶體系統（影響實測時間）

- 時脈：RP2350 標稱 150 MHz。
- SRAM：共 520 kB。0x20000000～0x2007FFFF 為 SRAM0–7（各 64 kB）；前 256 kB（SRAM0–3）與後 256 kB（SRAM4–7）各自在 4 個 bank 間按 word 交錯（詳見 `multicore-sync.md`），另有 SRAM8/9 各 4 kB（scratch X 0x20080000、scratch Y 0x20081000）。不同 bus master 存取不同 bank 可同時進行。
- Flash 經 XIP 執行：位址 0x10000000 起，XIP cache 16 kB。cache miss 要走 QSPI，延遲遠大於 SRAM（具體 cycle 數 ⚠️未驗證，與 flash 時脈設定有關）。
- 上面的週期表假設「無匯流排 stall」。程式在 flash 執行或與 DMA/另一核搶同一 SRAM bank 時，實測會比表上慢。

---

## 6. GCC inline asm 與獨立 `.S` 函式

### 6.1 Inline asm 語法

```c
asm volatile ("指令模板" : 輸出運算元 : 輸入運算元 : clobber 清單);
```

| constraint | 意義 |
|---|---|
| `"r"` | 任意通用暫存器（輸入） |
| `"=r"` | 只寫的輸出暫存器 |
| `"+r"` | 讀又寫（輸入兼輸出） |
| `"=&r"` | early-clobber：輸出在讀完所有輸入前就會被寫，不能和輸入共用暫存器 |
| `"i"` | 編譯期常數 |
| `"I"` | 12-bit 有號立即值（RISC-V） |
| `"K"` | 5-bit 無號立即值（CSR 立即值指令用） |
| `"J"` | 整數 0 |
| `"A"` | 存在通用暫存器中的位址（給 `lr.w`/`amo` 用） |
| `"cr"` | RVC 暫存器 x8–x15 |
| clobber `"memory"` | 告訴編譯器 asm 會讀寫記憶體（防止重排 / 快取在暫存器） |

範例：

```c
#include <stdint.h>

static inline uint32_t my_clz(uint32_t x) {
    uint32_t r;
    asm ("clz %0, %1" : "=r"(r) : "r"(x));        // 純運算，不需 volatile
    return r;
}

static inline uint32_t my_brev32(uint32_t x) {     // 完整 32 位元反轉
    uint32_t r;
    asm ("brev8 %0, %1\n\t"
         "rev8  %0, %0" : "=r"(r) : "r"(x));
    return r;
}

static inline uint32_t my_pack(uint32_t lo, uint32_t hi) {
    uint32_t r;
    asm ("pack %0, %1, %2" : "=r"(r) : "r"(lo), "r"(hi));
    return r;
}

static inline void add_in_place(uint32_t *acc, uint32_t v) {
    asm volatile ("add %0, %0, %1" : "+r"(*acc) : "r"(v));
}

static inline void compiler_barrier(void) {
    asm volatile ("" ::: "memory");
}
```

規則：

- 有副作用（讀 CSR、碰 MMIO、計時）一定加 `volatile`，否則可能被刪掉或移位置。
- 會改記憶體但沒有列成輸出 → 加 `"memory"` clobber。
- 改到沒列出的暫存器 → 要寫進 clobber，例如 `: : : "t0", "t1"`。
- 用到的指令必須在 `-march` 裡（例如 `clz` 需要 zbb），否則組譯器報 `unrecognized opcode` 或 `extension 'zbb' required`。

### 6.2 讀 CSR / cycle 計數

```c
#include <stdint.h>

static inline void cycles_enable(void) {
    // mcountinhibit 重置值 0x5（CY=bit0, IR=bit2 都是 1 = 停止計數）
    asm volatile ("csrci mcountinhibit, 5");      // 同時開 mcycle 與 minstret
}
static inline uint32_t mcycle32(void) {
    uint32_t c;
    asm volatile ("csrr %0, mcycle" : "=r"(c));
    return c;
}
static inline uint32_t minstret32(void) {
    uint32_t c;
    asm volatile ("csrr %0, minstret" : "=r"(c));
    return c;
}
static inline uint64_t mcycle64(void) {           // RV32 讀 64 位元：防止低位溢位時讀錯
    uint32_t hi, lo, hi2;
    do {
        asm volatile ("csrr %0, mcycleh" : "=r"(hi));
        asm volatile ("csrr %0, mcycle"  : "=r"(lo));
        asm volatile ("csrr %0, mcycleh" : "=r"(hi2));
    } while (hi != hi2);
    return ((uint64_t)hi << 32) | lo;
}
```

pico-sdk 版本（`hardware/riscv.h`）：

```c
#include "hardware/riscv.h"
riscv_clear_csr(mcountinhibit, 5);
uint32_t t0 = riscv_read_csr(mcycle);
```

CSR 事實（datasheet §3.8.9）：

| CSR | 位址 | 說明 |
|---|---|---|
| `mcycle` / `mcycleh` | 0xB00 / 0xB80 | cycle 計數低 / 高 32 位，可寫 |
| `minstret` / `minstreth` | 0xB02 / 0xB82 | 退休指令數 |
| `mcountinhibit` | 0x320 | bit0 CY、bit2 IR；重置 = 1（停止，省電） |
| `mcounteren` | 0x306 | 控制 **U-mode** 能否讀 `cycle`/`instret` |
| `cycle/cycleh/instret/instreth` | 0xC00/0xC80/0xC02/0xC82 | 唯讀別名（U-mode 需 mcounteren） |
| `mhartid` | 0xF14 | core 0 → 0、core 1 → 1 |
| `time` | — | **未實作**（讀了會 illegal instruction）。用 SIO 的 MTIME 或 pico-sdk `time_us_32()` |

- `mcountinhibit` 重置即為「停止」；bootrom 只在內部量測開機時間時暫時開啟、離開前關回。pico-sdk 執行期不會幫你清（在 SDK 原始碼中搜尋，只有測試程式自己清）。所以**不清就永遠讀到 0 或不變的值**。
- 未實作的 CSR 一律 illegal instruction（mcause 2）。
- Debug mode 中計數器不跑（`dcsr.STOPCOUNT` 固定為 1），單步除錯時量不到真實 cycle。

量測範本：

```c
cycles_enable();
uint32_t t0 = mcycle32();
uint32_t t1 = mcycle32();
uint32_t overhead = t1 - t0;          // 先量空測的固定開銷

t0 = mcycle32();
result = func_under_test(buf, n);     // 結果要被使用（印出 / 存 volatile），否則可能被優化掉
t1 = mcycle32();
uint32_t cycles = (t1 - t0) - overhead;   // 無號相減自動處理 32 位元回繞
```

- 多跑幾次取最小值或中位數；第一次常因 XIP cache miss 偏慢。
- 150 MHz 下 32 位元 mcycle 約 28.6 秒回繞一次；較長量測用 `mcycle64()`。

### 6.3 獨立 `.S` 函式（可從 C 呼叫）

檔名用大寫 `.S`（會先經 C 前處理器，可用 `#include`、`#define`、`//` 註解）；小寫 `.s` 不經前處理器。

```asm
// popcount_sum.S
// uint32_t popcount_sum(const uint32_t *p, uint32_t n);
// a0 = p, a1 = n ；回傳 a0 = 所有 word 的 1 位元總數

    .section .time_critical.popcount_sum, "ax"   // 放 SRAM；要放 flash 用 .text.popcount_sum
    .globl   popcount_sum
    .type    popcount_sum, @function
    .p2align 2
popcount_sum:
    li      a2, 0                 // sum = 0
    beqz    a1, 2f
    sh2add  a3, a1, a0            // end = p + n*4    (Zba)
1:
    lw      a4, 0(a0)
    addi    a0, a0, 4             // 夾在 load 與使用之間 → 無 load-use stall
    cpop    a4, a4                // Zbb
    add     a2, a2, a4
    bltu    a0, a3, 1b            // 向後分支，穩態預測正確
2:
    mv      a0, a2
    ret
    .size    popcount_sum, . - popcount_sum
```

C 端：

```c
#include <stdint.h>
uint32_t popcount_sum(const uint32_t *p, uint32_t n);   // 宣告即可
```

CMake（pico-sdk 專案）：`project(xxx C CXX ASM)`，並把 `popcount_sum.S` 加進 `add_executable(...)` 的來源清單。

用到 callee-saved 暫存器的函式骨架：

```asm
    .text
    .globl  f
    .type   f, @function
f:
    addi    sp, sp, -16           // 保持 16-byte 對齊
    sw      ra, 12(sp)
    sw      s0, 8(sp)
    sw      s1, 4(sp)
    // ... 使用 s0、s1，可以 call 其他函式 ...
    lw      s1, 4(sp)
    lw      s0, 8(sp)
    lw      ra, 12(sp)
    addi    sp, sp, 16
    ret
    .size   f, . - f
```

常見指示詞：`.text`、`.data`、`.section 名稱,"ax"`（a=配置、x=可執行）、`.globl`、`.type sym, @function`、`.size`、`.p2align 2`（4-byte 對齊）、`.option push/pop`、`.option norvc`（暫停壓縮）、`.word`、`.byte`、`.equ`。

### 6.4 自訂指令 h3.bextm（用 `.insn`）

依 datasheet 提供的編碼（custom0 opcode 0x0b）：

```c
// rd = (rs1 >> (rs2 & 31)) & ((1u << nbits) - 1)，nbits 為 1..8 的常數
#define H3_BEXTM(nbits, rs1, rs2) ({ uint32_t _r; \
    asm (".insn r 0x0b, 0, %3, %0, %1, %2" \
         : "=r"(_r) : "r"(rs1), "r"(rs2), "i"((((nbits) - 1) & 7) << 1)); _r; })

// rd = (rs1 >> shamt) & ((1u << nbits) - 1)，nbits 1..8、shamt 0..31 皆為常數
#define H3_BEXTMI(nbits, rs1, shamt) ({ uint32_t _r; \
    asm (".insn i 0x0b, 0x4, %0, %1, %2" \
         : "=r"(_r) : "r"(rs1), "i"(((((nbits) - 1) & 7) << 6) | ((shamt) & 31))); _r; })
```

一般寫法 `srli` + `andi` 只要 2 cycle；`h3.bextmi` 1 cycle，但只有在真的 RP2350 Hazard3 上可用。

---

## 7. pico-sdk 的 RISC-V 建置

| 項目 | 值 / 做法 |
|---|---|
| 選平台 | `cmake -DPICO_PLATFORM=rp2350-riscv -DPICO_BOARD=pico2 ..`（`rp2350-riscv` 預設板子為 pico2）；也可用環境變數 `PICO_PLATFORM` |
| 工具鏈搜尋三元組 | 依序 `riscv32-pico-elf`、`riscv32-unknown-elf`、`riscv32-corev-elf`、`riscv-none-elf` |
| 工具鏈路徑 | `PICO_TOOLCHAIN_PATH`（CMake 變數或環境變數），會在 `<path>/bin/` 下找 gcc |
| 編譯旗標 | 2.2.0：預設 `-march=rv32imac_zicsr_zifencei_zba_zbb_zbs_zbkb -mabi=ilp32`（`cmake/preload/toolchains/pico_riscv_gcc.cmake`），`-DPICO_COMPILER=pico_riscv_gcc_zcb_zcmp` 才改用 `rv32ima_zicsr_zifencei_zba_zbb_zbs_zbkb_zca_zcb_zcmp`；2.3.x：依序試 `-mcpu=hazard3-rp2350` → zcb_zcmp → rv32imac。`-mstrict-align`：2.3.1 起預設加，2.2.0 / 2.3.0 不加 |
| 預設 build type | `Release`（pico-sdk 加 `-g`；最佳化等級來自 CMake 的 GCC 預設，通常 `-O3 -DNDEBUG` ⚠️未驗證於考場版本） |
| Debug | `-Og`（`PICO_DEOPTIMIZED_DEBUG=1` 時 `-O0`） |
| 其他 | `MinSizeRel`（-Os）、`RelWithDebInfo`（-O2 -g） |
| 反組譯輸出 | `pico_add_extra_outputs(target)` 或 `pico_add_dis_output(target)` 產生 `<target>.dis`（內含 `objdump -h` 與 `objdump -d`） |
| 放 SRAM | `__not_in_flash_func(f)`、`__time_critical_func(f)`（都放到 `.time_critical.*` section，開機時由 flash 複製到 SRAM）；不想被內聯回 flash 函式用 `__no_inline_not_in_flash_func(f)` |
| 整個程式在 RAM | `pico_set_binary_type(target copy_to_ram)`（或 `no_flash`） |

考場容器裡的工具鏈名稱、版本、CMake 參數以考題文件 / 既有 Makefile 為準；先 `ls` 看工具鏈、`make VERBOSE=1` 或看 `compile_commands.json` 確認實際旗標。

### 7.1 看編譯器輸出

```sh
riscv32-unknown-elf-objdump -d build/app.elf | less          # 全部反組譯
riscv32-unknown-elf-objdump -d -M no-aliases build/app.elf   # 顯示真實指令（不顯示 li/mv/ret 等別名）
riscv32-unknown-elf-objdump -d -M numeric build/app.elf      # 暫存器用 x0..x31
riscv32-unknown-elf-objdump -dS build/app.elf                # 原始碼與組語交錯（需 -g）
riscv32-unknown-elf-objdump -h build/app.elf                 # section 大小與位址
riscv32-unknown-elf-nm -S --size-sort build/app.elf          # 符號大小
riscv32-unknown-elf-gcc -O2 -march=... -mabi=ilp32 -S foo.c -o foo.s   # 只產生組語
```

（工具名稱前綴依實際工具鏈替換，例如 `riscv32-pico-elf-`。）

判讀重點：

- 函式位址在 0x10xxxxxx → 在 flash（XIP）；0x20xxxxxx → 在 SRAM。
- 指令旁 2 bytes 編碼（4 個 hex 字元）是壓縮指令，4 bytes 是一般指令。
- 熱迴圈中找：`div/rem`（慢）、`call __mulsf3`/`__adddf3` 等（軟體浮點，極慢）、`lw` 後立刻使用、迴圈內重複載入的常數或位址、`call memcpy`。
- `-O2` 下期望看到 `clz/ctz/cpop/rev8/sh2add/bset/bext/minu/maxu/andn/rori` 等。若看到冗長的移位遮罩序列，檢查 `-march` 是否真的含 zbb/zbs。

---

## 8. C 位元操作大全（延伸 demo_asm.c）

一律優先使用**無號型別**（`uint32_t`），常數加 `u` 後綴。

### 8.1 基本操作

```c
#include <stdint.h>

#define BIT(n)            (1u << (n))                 // n 必須 0..31
#define SET_BIT(x, n)     ((x) |  BIT(n))             // bset
#define CLR_BIT(x, n)     ((x) & ~BIT(n))             // bclr
#define TOG_BIT(x, n)     ((x) ^  BIT(n))             // binv
#define TEST_BIT(x, n)    (((x) >> (n)) & 1u)         // bext

// 低 w 位全 1 的遮罩（w = 1..31；w = 32 要特判，因為 1u << 32 是 UB）
#define MASK(w)           ((1u << (w)) - 1u)
static inline uint32_t mask_w(unsigned w) { return w >= 32 ? 0xFFFFFFFFu : (1u << w) - 1u; }

// 取出 [lsb, lsb+w) 欄位（demo 的「先右移再 mask」）
static inline uint32_t get_field(uint32_t x, unsigned lsb, unsigned w) {
    return (x >> lsb) & mask_w(w);
}
// 寫入欄位：先清再放，v 要先 mask 避免污染相鄰欄位
static inline uint32_t set_field(uint32_t x, unsigned lsb, unsigned w, uint32_t v) {
    uint32_t m = mask_w(w) << lsb;
    return (x & ~m) | ((v << lsb) & m);
}
// 有號欄位的正負號擴展（w 位二補數 → int32_t）
static inline int32_t sext_field(uint32_t v, unsigned w) {   // 1 <= w <= 32
    uint32_t m = 1u << (w - 1);
    v &= mask_w(w);
    return (int32_t)((v ^ m) - m);       // 無 UB（無號轉 int32_t 為 implementation-defined，GCC 定義為模 2^32）
}
// 另一寫法：(int32_t)(v << (32 - w)) >> (32 - w)
// 依賴「有號右移為算術右移」與「無號轉有號超出範圍」— 兩者在 GCC 上定義良好，但屬 implementation-defined
```

範例對照（x = 0xA5 = 1010 0101，與 demo 一致）：

| 運算 | 結果 |
|---|---|
| `x \| BIT(1)` | 0xA7 |
| `x & ~BIT(0)` | 0xA4 |
| `(x >> 7) & 1` | 1 |
| `(x >> 4) & 0xF` | 0xA |
| `get_field(x, 4, 4)` | 0xA |
| `set_field(x, 0, 4, 0x3)` | 0xA3 |
| `sext_field(0xA, 4)` | -6 |

### 8.2 經典技巧

| 目的 | 寫法 | 說明 / Hazard3 對應 |
|---|---|---|
| 是否 2 的冪 | `x && !(x & (x - 1))` | |
| 最低位的 1 | `x & -x`（或 `x & (~x + 1)`） | 0 → 0 |
| 清除最低位的 1 | `x & (x - 1)` | Kernighan popcount 迴圈 |
| 把最低的 0 設 1 | `x \| (x + 1)` | |
| 最低位 1 的索引 | `__builtin_ctz(x)`（x≠0） | `ctz`；x=0 時硬體回傳 32 |
| 最高位 1 的索引 | `31 - __builtin_clz(x)`（x≠0） | `clz` |
| floor(log2 x) | 同上 | |
| 向上取到 2 的冪 | `x <= 1 ? 1 : 1u << (32 - __builtin_clz(x - 1))` | x > 2^31 時變成 `1u << 32`，UB |
| 對齊到 a（2 的冪）向上 | `(x + a - 1) & ~(a - 1)` | 向下：`x & ~(a - 1)` |
| x mod 2^k（無號） | `x & ((1u << k) - 1)` | 有號數不可直接這樣做 |
| x / 2^k（無號） | `x >> k` | 有號負數 `x/4` ≠ `x>>2`（前者朝 0 取整） |
| popcount | `__builtin_popcount(x)` | `cpop` 1 cycle |
| 奇偶校驗 | `__builtin_parity(x)` 或 `__builtin_popcount(x) & 1` | |
| byte swap | `__builtin_bswap32(x)`、`__builtin_bswap16(x)` | `rev8`（16 位版 = rev8 後右移 16） |
| 32 位元位元反轉 | 見下 | `brev8` + `rev8` |
| 旋轉 | `(x << (n & 31)) \| (x >> (-n & 31))` | GCC 認得 → `rol`；n 為常數時 → `rori` |
| 有任一 byte 為 0 | `((x - 0x01010101u) & ~x & 0x80808080u) != 0` | Zbb：`orc.b` 後 `!= 0xFFFFFFFF` |
| 兩數交換（不建議） | `a ^= b; b ^= a; a ^= b;` | a、b 同位址時變 0；直接用暫存變數較快 |

可攜的位元反轉（沒有 Zbkb 時）：

```c
static inline uint32_t bitrev32(uint32_t x) {
    x = ((x >> 1) & 0x55555555u) | ((x & 0x55555555u) << 1);
    x = ((x >> 2) & 0x33333333u) | ((x & 0x33333333u) << 2);
    x = ((x >> 4) & 0x0F0F0F0Fu) | ((x & 0x0F0F0F0Fu) << 4);
    return __builtin_bswap32(x);          // Zbb: rev8
}
// Hazard3：brev8 + rev8 兩條指令完成（見 §6.1 my_brev32）
```

可攜的 popcount（SWAR，沒有 cpop 時）：

```c
static inline uint32_t popcount32(uint32_t x) {
    x = x - ((x >> 1) & 0x55555555u);
    x = (x & 0x33333333u) + ((x >> 2) & 0x33333333u);
    x = (x + (x >> 4)) & 0x0F0F0F0Fu;
    return (x * 0x01010101u) >> 24;
}
```

### 8.3 無分支（branchless）寫法

| 目的 | 寫法 | 注意 |
|---|---|---|
| 條件遮罩 | `uint32_t m = -(uint32_t)(cond != 0);` | cond 為真 → 0xFFFFFFFF |
| 選擇 | `r = (a & m) \| (b & ~m);` 或 `r = b ^ ((a ^ b) & m);` | Zbb 的 `andn` 可省一條 |
| min/max（Zbb 下） | `a < b ? a : b` | 編譯器 → `min/minu/max/maxu`；不用自己寫位元技巧 |
| 無 Zbb 的 min | `b ^ ((a ^ b) & -(a < b))` | |
| abs | `x < 0 ? -x : x` | Zbb 常見輸出 `neg` + `max` ⚠️未驗證；`abs(INT_MIN)` 溢位 UB |
| 符號 | `(x > 0) - (x < 0)` | → `slt`/`sgtz` |
| 飽和加（無號） | `s = a + b; s \|= -(s < a);` | 溢位時變 0xFFFFFFFF |
| 夾限 clamp | `x < lo ? lo : (x > hi ? hi : x)` | → `max` + `min` |

Hazard3 分支預測正確只要 1 cycle、錯誤 2 cycle，懲罰很小。無分支寫法在「資料隨機、難預測」時才明顯有利，迴圈結尾的向後分支本來就預測得很好。

### 8.4 未定義行為（UB）與型別陷阱

| 陷阱 | 例子 | 正確做法 |
|---|---|---|
| 移位量 ≥ 型別寬度 | `1u << 32`、`x >> n`（n 可能 32） | 特判；硬體 `sll` 只取低 5 位（`<<32` 等同 `<<0`），但 C 是 UB，編譯器可能做任何事 |
| 移位量為負 | `x << -1` | UB |
| 左移有號負數 | `-1 << 3` | UB；改用無號 |
| 左移有號數溢位 | `1 << 31`（int） | UB；寫 `1u << 31` |
| 有號溢位 | `INT_MAX + 1`、`a * b` 溢位 | UB；改用 `uint32_t` 運算再轉回 |
| 有號右移 | `-8 >> 1` | implementation-defined（GCC 為算術右移 → -4） |
| `__builtin_clz(0)` / `ctz(0)` | | UB（雖然 Hazard3 硬體回傳 32） |
| 整數提升（uint8_t） | `uint8_t a = 0x0F; if (~a == 0xF0)` 為假 | `~a` 先提升成 int → 0xFFFFFFF0；寫 `(uint8_t)~a` |
| 整數提升（左移） | `uint8_t b = 0x80; uint32_t r = b << 24;` | `b` 提升成 int，`0x80 << 24` 溢位 int → UB；寫 `(uint32_t)b << 24` |
| uint16_t 相乘 | `uint16_t x = 0xFFFF; uint32_t r = x * x;` | 提升為 int 相乘溢位 → UB；寫 `(uint32_t)x * x` |
| 有號 / 無號比較 | `int i = -1; if (i < sizeof(buf))` 為假 | -1 轉成無號變很大；統一型別 |
| `char` 正負號 | `char c = 0x80;` | 不同平台 char 有號性不同（RISC-V psABI 規定 `char` 為無號，與 Arm 相同；x86 為有號）；用 `int8_t`/`uint8_t` |
| 非對齊指標轉型 | `*(uint32_t *)(buf + 1)` | Hazard3 直接 trap；用 `memcpy(&v, buf + 1, 4)` 或逐 byte 組合 |
| strict aliasing | 用 `float*` 讀 `uint32_t` 物件 | 用 `memcpy` 或 union |
| 運算子優先序 | `x & 0xF == 0` 等於 `x & (0xF == 0)` | 加括號：`(x & 0xF) == 0` |
| 運算子優先序 | `1 << n + 1` 等於 `1 << (n+1)` | 加括號 |

### 8.5 MMIO（記憶體映射暫存器）

```c
#include <stdint.h>
#define REG32(addr)   (*(volatile uint32_t *)(addr))

// 讀-改-寫（非原子：中斷或另一核可能在讀與寫之間插入）
REG32(BASE + OFF) = (REG32(BASE + OFF) & ~MASK) | (val & MASK);
```

- MMIO 一定用 `volatile`：否則編譯器可能合併、刪除、或重排讀寫（例如輪詢迴圈被優化成無窮迴圈或只讀一次）。
- `volatile` 不保證原子性，也不是執行緒同步工具。
- RP2350 周邊（APB/AHB 周邊暫存器區塊，每塊 4 kB）原子別名：

| 位址 | 寫入效果 |
|---|---|
| reg + 0x0000 | 一般讀寫 |
| reg + 0x1000 | XOR：寫入值中為 1 的位元翻轉 |
| reg + 0x2000 | SET：寫入值中為 1 的位元設 1 |
| reg + 0x3000 | CLEAR：寫入值中為 1 的位元清 0 |

```c
#include "hardware/address_mapped.h"
hw_set_bits(&some_hw->ctrl, BIT(3));          // *(reg + 0x2000) = mask
hw_clear_bits(&some_hw->ctrl, BIT(3));        // *(reg + 0x3000) = mask
hw_xor_bits(&some_hw->ctrl, BIT(3));          // *(reg + 0x1000) = mask
hw_write_masked(&some_hw->ctrl, v, mask);     // = hw_xor_bits(addr, (*addr ^ v) & mask)
```

- `hw_write_masked` 先讀再 XOR：不同位元可安全並行修改，**同一批位元**的並行修改仍不安全。
- SIO（0xD0000000）**不支援**這組別名；但 SIO 的 GPIO 有自己的 set/clr/xor 暫存器（例如 `sio_hw->gpio_set`、`gpio_clr`、`gpio_togl`；pico-sdk `gpio_put()` 就是用它們）。
- I2C、UART、SPI 等透過 bus interposer 支援別名，原子寫入多 2 個 clock。
- 用別名寫入時，**不要**寫「讀出值 | mask」，只寫 mask 本身。

---

## 9. 組語層級最佳化清單

1. **先量測**：`mcycle` 前後差（記得 `csrci mcountinhibit, 5`），確認熱點在哪。
2. **放 SRAM**：熱點函式 `__not_in_flash_func` / `.time_critical.*`；避免 XIP cache miss。
3. **避開 load-use**：load 與第一次使用之間插入一條無關指令（例如指標遞增）。指標追逐（load 結果當下一個 load 的位址）無法避免 stall，盡量改成陣列索引。
4. **展開迴圈**：減少分支與迴圈計數指令；用多個累加器打斷相依鏈；先一次 load 多個 word 再運算，可把 load-use 間隔填滿。
5. **減少迴圈內指令**：用「結束指標」比較取代計數器（`bltu p, end`）；把不變量移出迴圈。
6. **強度折減**：`x * 2^k` → 移位；`x * 3/5/9` → `sh1add/sh2add/sh3add x, x, x`；除以常數交給編譯器（會變 `mulhu`）；`% 2^k`（無號）→ `andi`；迴圈裡避免 `div/rem`（18～19 cycle）。
7. **Zba 定址**：`a[i]` → `sh2add t, i, base` 一條取代 `slli`+`add`。
8. **Zbb/Zbs 取代序列**：`clz/ctz/cpop/rev8/rol/ror/min/max/andn/sext/zext`、`bset/bclr/binv/bext` 各 1 cycle。
9. **Zbkb**：`pack/packh` 組合半字/位元組；`brev8`+`rev8` 位元反轉；`zip/unzip` 位元交錯。
10. **不用浮點**：Hazard3 沒有 FPU，`float` 會呼叫軟體函式庫；改用定點數（例如 Q16.16，乘法用 `mulh`/`mul` 組 64 位元）。
11. **對齊分支目標**：熱迴圈開頭 `.p2align 2`，避免跳到未對齊的 32-bit 指令（+1 cycle）。單一 16-bit 指令的迴圈本體要改成 32-bit（§5.3）。
12. **資料型別**：迴圈索引與運算用 32 位元型別；`uint8_t`/`uint16_t` 運算常需額外的 `zext`/`andi`。
13. **`restrict`**：`void f(uint32_t *restrict dst, const uint32_t *restrict src)` 讓編譯器知道不重疊，可重排 load/store。
14. **大量搬資料**：交給 DMA（demo section2-3 的 transfer engine 概念），CPU 去做別的事。
15. **最佳化等級**：`-O2` 通常最平衡；`-O3` 會更積極展開 / 內聯，程式變大，在小 cache 的 XIP 上未必更快；`-Os` 最小（大量使用壓縮指令；Zcmp 需 zcb_zcmp 工具鏈）。每次改動都用 objdump 與 mcycle 確認，不要只憑感覺。
16. **正確性第一**：OJ 判分先看結果正確；最佳化後用相同輸入比對輸出（含邊界：0、1、0xFFFFFFFF、0x80000000、n=0、n=1、未對齊長度）。

### 9.1 迴圈展開範例（4 倍 + 2 個累加器）

```asm
// uint32_t sum4(const uint32_t *p, uint32_t n);  n 為 4 的倍數
    .section .time_critical.sum4, "ax"
    .globl  sum4
    .type   sum4, @function
    .p2align 2
sum4:
    li      a2, 0
    li      a3, 0
    beqz    a1, 2f
    sh2add  a1, a1, a0        // end
1:
    lw      t0, 0(a0)
    lw      t1, 4(a0)
    lw      t2, 8(a0)
    lw      t3, 12(a0)
    add     a2, a2, t0        // t0 已在 3 條指令前載入，無 stall
    add     a3, a3, t1
    add     a2, a2, t2
    add     a3, a3, t3        // t3 緊接其 load 後第 4 條，無 stall
    addi    a0, a0, 16
    bltu    a0, a1, 1b
2:
    add     a0, a2, a3
    ret
    .size   sum4, . - sum4
```

穩態每 4 個 word：4 lw + 4 add + addi + bltu = 10 cycle（2.5 cycle/word），未展開版約 4 cycle/word（`lw`+`addi`+`add`+`bltu`，且需安排避免 load-use）。

---

## 10. 除錯清單

| 症狀 | 可能原因 | 檢查 |
|---|---|---|
| `Error: unrecognized opcode 'clz'` / 要求某 extension | `-march` 沒包含 zbb/zbs/zba/zbkb | 看實際編譯旗標；或改用 C builtin |
| link error: undefined reference to `my_func` | `.S` 沒 `.globl`、名字拼錯、沒加進 CMake 來源、C++ 檔需 `extern "C"` | `nm` 看符號 |
| 函式回傳錯值 | 回傳值沒放 a0；用了 s 暫存器沒存；ra 被 `call` 覆蓋沒存 | 對照 §1 ABI |
| 呼叫 asm 後 C 端變數錯亂 | inline asm 漏寫 clobber / 輸出；漏 `"memory"` | 檢查 constraint |
| 偶發 HardFault/例外，mcause=4 或 6 | 非對齊 load/store | 位址是否為 2/4 的倍數；改 `memcpy` |
| mcause=2（illegal instruction） | 讀不存在的 CSR（如 `time`）；用了 RP2350 沒有的指令（Zbc、F） | 對照 §4 擴充表 |
| `amo*.w` fault / `lr/sc` 卡死 | 原子操作位址不在主 SRAM | 鎖變數放主 SRAM；或用 pico-sdk `spin_lock_*` API（RP2350 預設是 SRAM 中的軟體 spinlock，勿直接碰 SIO 硬體 spinlock，E2） |
| `mcycle` 永遠 0 或不變 | `mcountinhibit` 未清 | `csrci mcountinhibit, 5` |
| 量到的 cycle 忽大忽小 | XIP cache miss、中斷、另一核或 DMA 搶 bus | 放 SRAM、多次取最小值、暫時關中斷 |
| 開 -O2 後行為改變 | UB（有號溢位、越界、移位 ≥32、未初始化）；MMIO 少 `volatile` | §8.4；`-fsanitize` 在主機上先測 C 邏輯 |
| 輪詢旗標的迴圈不結束 | 旗標沒 `volatile`（或中斷改的變數） | 加 `volatile` |
| 位元欄位寫入破壞相鄰欄位 | 沒先清欄位、值沒先 mask | `set_field` 寫法 |
| `~` 或比較結果怪 | 整數提升 | 強制轉回窄型別 |
| 分支跳不到（relocation truncated） | 條件分支超過 ±4 KiB | 反轉條件 + `j`（±1 MiB） |

主機端先驗證 C 邏輯：位元演算法與目標平台無關的部分，可先在容器內用 `gcc -O2 -Wall -Wextra -fsanitize=undefined,address` 跑單元測試，再搬到 RISC-V。

---

## 11. 速查：C 慣用寫法 → Hazard3 指令

| C | 期望指令 |
|---|---|
| `a & ~b` | `andn` |
| `~(a ^ b)` | `xnor` |
| `x \| (1u << n)` / `x & ~(1u << n)` / `x ^ (1u << n)` | `bset` / `bclr` / `binv`（n 常數 → `*i` 版） |
| `(x >> n) & 1` | `bext` / `bexti` |
| `__builtin_clz/ctz/popcount` | `clz` / `ctz` / `cpop` |
| `__builtin_bswap32` | `rev8` |
| 旋轉 | `rol` / `ror` / `rori` |
| `(int8_t)x`、`(int16_t)x`、`(uint16_t)x`、`(uint8_t)x` | `sext.b`、`sext.h`、`zext.h`、`andi 255` |
| `a < b ? a : b`（有號/無號） | `min` / `minu` |
| `p[i]`（4-byte 元素） | `sh2add` + `lw` |
| `x * 3`、`x * 5`、`x * 9` | `sh1add/sh2add/sh3add x, x, x` |
| `x / 10`（無號常數） | `mulhu` + 移位 |
| `(lo & 0xFFFF) \| (hi << 16)` | `pack`（自動產生與否 ⚠️未驗證） |

---

## 12. 向模型提問的範本

範本 1：把 C 函式改寫成 Hazard3 組語

```
目標：RP2350 Hazard3（RV32IMAC + Zba/Zbb/Zbs/Zbkb/Zcb/Zcmp，無 FPU、無 Zbc），ABI ilp32。
請把下面的 C 函式改寫成可從 C 呼叫的 .S 函式，函式名 {{函式名}}，放在 section {{.text 或 .time_critical.名稱}}。
要求：遵守呼叫慣例（a0–a7 參數、a0 回傳、s 暫存器需保存）、避免 load-use stall、善用 Zba/Zbb、
在每行註解說明暫存器用途，最後估算穩態每次迴圈的 cycle 數（load-use +1、分支預測錯 +1、jal/jalr 2、div 18–19）。
C 原始碼：
{{貼上 C 程式碼}}
```

範本 2：讀 objdump 找瓶頸

```
以下是 {{函式名}} 在 -march=rv32imac_zicsr_zifencei_zba_zbb_zbs_zbkb（SDK 2.2.0 預設；2.3.x 看 build 實際旗標）{{-O 等級}} 的 objdump 輸出，
以及我量到的 mcycle 為 {{數字}} cycle（輸入大小 {{n}}）。
請逐條標出熱迴圈的指令、每條在 Hazard3 上的 cycle（含 load-use 與分支），指出可改善之處（未使用的 Zbb/Zba 指令、
div/rem、軟體浮點呼叫、多餘的 zext、從 flash 執行等），並給出修改後的 C 或組語。
objdump：
{{貼上}}
```

範本 3：位元操作需求轉成正確 C

```
我需要對 32 位元暫存器 {{暫存器名 / 位址}} 做：{{例如：把 bit[{{msb}}:{{lsb}}] 設為 {{值}}，其他位元不變；讀出 bit {{n}}}}。
請給出：(1) 只用 uint32_t 與無 UB 的 C 寫法；(2) 若是 RP2350 周邊，使用原子別名（+0x1000 XOR、+0x2000 SET、+0x3000 CLR）
或 pico-sdk hw_set_bits/hw_clear_bits/hw_write_masked 的版本；(3) 指出整數提升、移位 >=32、volatile 等陷阱。
相關文件段落：{{貼上 datasheet 暫存器表}}
```

範本 4：除錯例外 / 錯誤結果

```
在 RP2350 Hazard3 上執行 {{程式 / 函式}} 時發生 {{現象：例外 mcause={{值}} / 結果錯誤 / 卡住}}。
mepc={{值}}，相關原始碼與反組譯如下。請依序檢查：非對齊存取、未實作 CSR 或不支援的指令、
呼叫慣例（s 暫存器與 ra 保存、sp 16-byte 對齊）、inline asm constraint 與 clobber、volatile、
原子操作是否在主 SRAM。列出最可能的原因與驗證方法。
{{貼上程式碼 / objdump}}
```

範本 5：最佳化並驗證

```
請把 {{函式名}} 最佳化，目標是降低 mcycle 量測值，但輸出必須與原版完全相同。
限制：{{例如：不能改函式介面 / 只能改某檔案 / 需通過 OJ}}。
請提供：(1) 修改後程式；(2) 用 mcycle 量測的測試碼（含 csrci mcountinhibit,5 與空測開銷扣除）；
(3) 正確性測試輸入（0、1、0xFFFFFFFF、0x80000000、n=0、n=1、非 4 倍數長度）；
(4) 預期 cycle 估算與理由。
原始碼：
{{貼上}}
```
