// rv_imm.h — 2-2 §C 的介面（不要改這個檔案）
#pragma once
#include <stdint.h>

int32_t  imm_i(uint32_t insn);   // I-type（addi、lw、jalr…）
int32_t  imm_s(uint32_t insn);   // S-type（sw、sh、sb）
int32_t  imm_b(uint32_t insn);   // B-type（beq、bne…），單位是 byte，一定是偶數
int32_t  imm_j(uint32_t insn);   // J-type（jal），單位是 byte，一定是偶數

// 組出一條 B-type 指令：opcode 固定 0x63。offset 是 byte 數（偶數，-4096..4094）。
uint32_t enc_b(uint32_t funct3, uint32_t rs1, uint32_t rs2, int32_t offset);
