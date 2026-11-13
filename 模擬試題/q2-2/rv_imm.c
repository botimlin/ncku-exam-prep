// rv_imm.c — 2-2 §C：RISC-V RV32I 立即值的解碼與 B-type 編碼（規格在 README.md §C）
//
// imm_i 是寫好的範例，其他四個是 TODO。
// 提示：RISC-V Unprivileged ISA 手冊 2.3 節「Immediate Encoding Variants」有每種格式的 bit 對照圖。

#include "rv_imm.h"

int32_t imm_i(uint32_t insn) {
    return (int32_t)insn >> 20;          // bits 31..20，算術右移 = 符號延伸
}

int32_t imm_s(uint32_t insn) {
    (void)insn;
    return 0;                             // TODO(改這裡)
}

int32_t imm_b(uint32_t insn) {
    (void)insn;
    return 0;                             // TODO(改這裡)
}

int32_t imm_j(uint32_t insn) {
    (void)insn;
    return 0;                             // TODO(改這裡)
}

uint32_t enc_b(uint32_t funct3, uint32_t rs1, uint32_t rs2, int32_t offset) {
    (void)funct3; (void)rs1; (void)rs2; (void)offset;
    return 0x63;                          // TODO(改這裡)
}
