// 解答：rv_imm.c（RISC-V Unprivileged ISA 2.3 節 Figure 2.4）
#include "rv_imm.h"

int32_t imm_i(uint32_t insn) { return (int32_t)insn >> 20; }

// S：imm[11:5] = insn[31:25]，imm[4:0] = insn[11:7]
int32_t imm_s(uint32_t insn) {
    return ((int32_t)insn >> 25) << 5 | (int32_t)((insn >> 7) & 0x1F);
}

// B：imm[12] = insn[31]，imm[10:5] = insn[30:25]，imm[4:1] = insn[11:8]，imm[11] = insn[7]
int32_t imm_b(uint32_t insn) {
    return ((int32_t)insn >> 31) << 12          // 符號 bit 延伸到 12 以上
         | (int32_t)(((insn >> 7) & 0x1) << 11)
         | (int32_t)(((insn >> 25) & 0x3F) << 5)
         | (int32_t)(((insn >> 8) & 0xF) << 1);
}

// J：imm[20] = insn[31]，imm[10:1] = insn[30:21]，imm[11] = insn[20]，imm[19:12] = insn[19:12]
int32_t imm_j(uint32_t insn) {
    return ((int32_t)insn >> 31) << 20
         | (int32_t)(insn & 0x000FF000)
         | (int32_t)(((insn >> 20) & 0x1) << 11)
         | (int32_t)(((insn >> 21) & 0x3FF) << 1);
}

uint32_t enc_b(uint32_t funct3, uint32_t rs1, uint32_t rs2, int32_t offset) {
    uint32_t i = (uint32_t)offset;
    return ((i >> 12) & 1) << 31 | ((i >> 5) & 0x3F) << 25 | (rs2 & 31) << 20 | (rs1 & 31) << 15 |
           (funct3 & 7) << 12 | ((i >> 1) & 0xF) << 8 | ((i >> 11) & 1) << 7 | 0x63;
}
