# bits-riscv：位元操作 + RISC-V 預製程式碼（對應官方 demo 2-2）

## 檔案 → 題型對照
| 檔案 | 什麼題目用它 | 要改哪裡 |
|---|---|---|
| `bitops.h` | 任何「取出 / 設定 / 清除位元」「符號延伸」「popcount」「endian」「位元反轉」 | 不用改，`#include "bitops.h"` 直接用 |
| `bitstream.c` | 「從位元流取出固定寬度欄位」「把欄位依序寫入 byte 陣列」（MSB-first / LSB-first、跨 byte、跨 word） | 看題目是哪種順序，挑 `read_msb` 或 `read_lsb` |
| `packet_fields.c` | 「依規格把欄位打包成一個 32 位元數」「拆封包 header」「大小端轉換」「位元重新排列」 | 最上面 `TODO(改這裡)` 的 SHIFT / WIDTH 換成題目的表 |
| `rv32_encode_decode.c` | 「把 RISC-V 指令編成機器碼 / 解回來」「寫反組譯器」「寫一個小模擬器」 | `disasm()`、`step()` 裡照著 switch 加新指令 |
| `asm_examples.S` + `asm_test.c` | 「用 RISC-V 組語寫一個函式給 C 呼叫」「BNN 的 XNOR-popcount」「inline asm」 | 複製最接近的函式改；宣告要同步加到 asm_test.c |
| `rv32_asm_cheatsheet.md` | 查暫存器用途、偽指令、Hazard3 位元指令（cpop/clz/rev8/bset…） | 只查不改 |

## 解題 SOP（位元題）
1. 先在紙上畫出 32 個格子，標出每個欄位的 `[hi:lo]`。
2. 取出：`(x >> lo) & ((1u << 寬度) - 1)`；放入：先 `x &= ~(mask << lo)` 再 `x |= (v & mask) << lo`。
3. 有號欄位（例如 RISC-V 的 imm）取出後要 `sign_extend(v, 寬度)`。
4. 一律用 `uint32_t`；`1u << 32` 是未定義行為（寬度 32 要特判）。
5. printf 印 `uint32_t` 時轉 `(unsigned)` 再用 `%u` / `%X`（RISC-V 上 uint32_t 是 unsigned long）。
6. 用 self-test：手算 1~2 組答案寫成 `CHECK`，跑出 PASS 再交。

## 在 PC 上編譯測試（C 檔）
```sh
gcc -O2 -Wall -Wextra bitstream.c          -o /tmp/bs && /tmp/bs
gcc -O2 -Wall -Wextra packet_fields.c      -o /tmp/pf && /tmp/pf
gcc -O2 -Wall -Wextra rv32_encode_decode.c -o /tmp/rv && /tmp/rv
```
每個都應該印出 `... ALL PASS`。

## RISC-V 交叉編譯（組語檔）
Hazard3 的 -march（gcc 13）：`rv32imac_zicsr_zifencei_zba_zbb_zbs_zbkb`，ABI：`ilp32`
```sh
# 只組譯 + 看機器碼（不需要 C 函式庫，一定能用）
riscv64-unknown-elf-gcc -march=rv32imac_zicsr_zifencei_zba_zbb_zbs_zbkb -mabi=ilp32 -c asm_examples.S -o /tmp/a.o
riscv64-unknown-elf-objdump -d /tmp/a.o
# 用 GNU as 驗證自己編的機器碼（和 rv32_encode_decode.c 對答案）
echo "addi x1, x0, 5" | riscv64-unknown-elf-as -march=rv32i - -o /tmp/x.o && riscv64-unknown-elf-objdump -d -M no-aliases,numeric /tmp/x.o   # numeric = 顯示 x1 而不是 ra
```
- 在 Pico SDK 專案裡：把 `asm_examples.S` 加進 `add_executable(...)` 的來源檔，`PICO_PLATFORM=rp2350-riscv` 編譯，
  C 端照 `asm_test.c` 宣告後呼叫，用 `printf` 經 USB/UART 印結果。
- 想驗證「沒有 Zbb 也對」：改成 `-march=rv32imac` 再編，`#ifdef __riscv_zbb` 的另一條路就會被用到。

## 已驗證（2026-11-11）
- 主機 gcc 13：bitops.h（另寫測試）、bitstream.c、packet_fields.c、rv32_encode_decode.c 全部 PASS，0 警告。
- `rv32_encode_decode.c` 的期望機器碼全部是用 `riscv64-unknown-elf-as -march=rv32i` + objdump 得到的。
- RISC-V：在 `pico-build` 映像（gcc 13.2）+ picolibc + `qemu-riscv32` 跑 asm_test（基本 ISA 版與 Zbb 版）
  和上面所有 C 測試，全部 PASS；`rv32_asm_cheatsheet.md` 列的指令都組譯過。
- 註：`pico-build` 映像本身沒有 rv32 的 C 函式庫（沒有 stdio.h），所以那裡只能 `-c` 組譯，
  要連結 printf 程式請用 Pico SDK（它自帶函式庫）。
