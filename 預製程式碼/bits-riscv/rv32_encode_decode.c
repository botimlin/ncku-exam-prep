// rv32_encode_decode.c — RV32I 指令 編碼 / 解碼 / 反組譯 / 迷你模擬器
// 題型：「把指令變成 32 位元機器碼」「把機器碼看懂」「寫一個小 CPU 模擬器」
// 編譯：gcc -O2 -Wall -Wextra rv32_encode_decode.c -o rv && ./rv
// 六種格式（bit 31 ...................................... bit 0）：
//  R: funct7[31:25] rs2[24:20] rs1[19:15] funct3[14:12] rd[11:7]      opcode[6:0]
//  I: imm[11:0]     [31:20]    rs1        funct3        rd            opcode
//  S: imm[11:5]     rs2        rs1        funct3        imm[4:0]      opcode
//  B: imm[12|10:5]  rs2        rs1        funct3        imm[4:1|11]   opcode  ← 打亂！
//  U: imm[31:12]                                        rd            opcode
//  J: imm[20|10:1|11|19:12]                             rd            opcode  ← 打亂！
// B/J 的 imm 最低位一定是 0（跳 2 的倍數），所以不存 bit0。
#include <stdio.h>
#include <stdint.h>
#include <string.h>
// 註：在 RISC-V 上 uint32_t 是 unsigned long，printf 前一律轉 (unsigned) / int 才不會有警告

#define BITS(x, hi, lo) ((unsigned)(((x) >> (lo)) & ((1u << ((hi) - (lo) + 1)) - 1u)))   // 取 x[hi:lo]
static int sext(uint32_t v, int bits) { int s = 32 - bits; return (int32_t)(v << s) >> s; }

enum { OP_LUI = 0x37, OP_AUIPC = 0x17, OP_JAL = 0x6F, OP_JALR = 0x67, OP_BR = 0x63,
       OP_LOAD = 0x03, OP_STORE = 0x23, OP_IMM = 0x13, OP_OP = 0x33 };

// ================= 編碼（組譯器方向） =================
uint32_t enc_r(int f7, int rs2, int rs1, int f3, int rd, int op) {
    return (uint32_t)f7 << 25 | rs2 << 20 | rs1 << 15 | f3 << 12 | rd << 7 | op; }
uint32_t enc_i(int32_t imm, int rs1, int f3, int rd, int op) {
    return ((uint32_t)imm & 0xFFF) << 20 | rs1 << 15 | f3 << 12 | rd << 7 | op; }
uint32_t enc_s(int32_t imm, int rs2, int rs1, int f3, int op) {
    uint32_t u = (uint32_t)imm;
    return BITS(u, 11, 5) << 25 | rs2 << 20 | rs1 << 15 | f3 << 12 | BITS(u, 4, 0) << 7 | op; }
uint32_t enc_b(int32_t imm, int rs2, int rs1, int f3, int op) {
    uint32_t u = (uint32_t)imm;
    return BITS(u, 12, 12) << 31 | BITS(u, 10, 5) << 25 | rs2 << 20 | rs1 << 15 | f3 << 12
         | BITS(u, 4, 1) << 8 | BITS(u, 11, 11) << 7 | op; }
uint32_t enc_u(uint32_t imm20, int rd, int op) { return (imm20 & 0xFFFFF) << 12 | rd << 7 | op; }
uint32_t enc_j(int32_t imm, int rd, int op) {
    uint32_t u = (uint32_t)imm;
    return BITS(u, 20, 20) << 31 | BITS(u, 10, 1) << 21 | BITS(u, 11, 11) << 20
         | BITS(u, 19, 12) << 12 | rd << 7 | op; }

// ================= 解碼（反組譯 / 模擬器方向） =================
#define OPC(x) BITS(x, 6, 0)
#define RD(x)  BITS(x, 11, 7)
#define F3(x)  BITS(x, 14, 12)
#define RS1(x) BITS(x, 19, 15)
#define RS2(x) BITS(x, 24, 20)
#define F7(x)  BITS(x, 31, 25)
int imm_i(uint32_t x) { return sext(BITS(x, 31, 20), 12); }
int imm_s(uint32_t x) { return sext(BITS(x, 31, 25) << 5 | BITS(x, 11, 7), 12); }
int imm_b(uint32_t x) { return sext(BITS(x, 31, 31) << 12 | BITS(x, 7, 7) << 11
                                      | BITS(x, 30, 25) << 5 | BITS(x, 11, 8) << 1, 13); }
int imm_u(uint32_t x) { return (int)(x & 0xFFFFF000u);   }     // 已經是 <<12 後的值
int imm_j(uint32_t x) { return sext(BITS(x, 31, 31) << 20 | BITS(x, 19, 12) << 12
                                      | BITS(x, 20, 20) << 11 | BITS(x, 30, 21) << 1, 21); }

// 反組譯成文字（只支援子集）。TODO(改這裡)：加新指令就在對應 opcode 下加 funct3/funct7 判斷
void disasm(uint32_t x, char *out) {
    switch (OPC(x)) {
    case OP_OP:
        if (F3(x) == 0) { sprintf(out, "%s x%u, x%u, x%u", F7(x) == 0x20 ? "sub" : "add", RD(x), RS1(x), RS2(x)); return; }
        break;
    case OP_IMM:  if (F3(x) == 0) { sprintf(out, "addi x%u, x%u, %d", RD(x), RS1(x), imm_i(x)); return; } break;
    case OP_LOAD: if (F3(x) == 2) { sprintf(out, "lw x%u, %d(x%u)", RD(x), imm_i(x), RS1(x)); return; } break;
    case OP_STORE:if (F3(x) == 2) { sprintf(out, "sw x%u, %d(x%u)", RS2(x), imm_s(x), RS1(x)); return; } break;
    case OP_BR:
        if (F3(x) == 0 || F3(x) == 1) { sprintf(out, "%s x%u, x%u, %d", F3(x) ? "bne" : "beq", RS1(x), RS2(x), imm_b(x)); return; }
        break;
    case OP_JAL:  sprintf(out, "jal x%u, %d", RD(x), imm_j(x)); return;
    case OP_JALR: sprintf(out, "jalr x%u, %d(x%u)", RD(x), imm_i(x), RS1(x)); return;
    case OP_LUI:  sprintf(out, "lui x%u, 0x%x", RD(x), (unsigned)imm_u(x) >> 12); return;
    case OP_AUIPC:sprintf(out, "auipc x%u, 0x%x", RD(x), (unsigned)imm_u(x) >> 12); return;
    }
    sprintf(out, "unknown 0x%08x", (unsigned)x);
}

// ================= 迷你模擬器 =================
typedef struct { uint32_t x[32], pc; uint8_t mem[1024]; } CPU;   // TODO(改這裡)：記憶體大小
static uint32_t ld32(CPU *c, uint32_t a) { uint32_t v; memcpy(&v, c->mem + a, 4); return v; }  // 小端
static void     st32(CPU *c, uint32_t a, uint32_t v) { memcpy(c->mem + a, &v, 4); }
// 執行一條指令；回傳 0 = 正常，-1 = 不認得的指令（當成停機）
int step(CPU *c) {
    uint32_t x = ld32(c, c->pc), next = c->pc + 4;
    uint32_t a = c->x[RS1(x)], b = c->x[RS2(x)];
    int rd = RD(x);
    switch (OPC(x)) {
    case OP_OP:    if (F3(x) == 0) { c->x[rd] = F7(x) == 0x20 ? a - b : a + b; break; } return -1;
    case OP_IMM:   if (F3(x) == 0) { c->x[rd] = a + imm_i(x); break; } return -1;
    case OP_LOAD:  if (F3(x) == 2) { c->x[rd] = ld32(c, a + imm_i(x)); break; } return -1;
    case OP_STORE: if (F3(x) == 2) { st32(c, a + imm_s(x), b); break; } return -1;
    case OP_BR:
        if (F3(x) == 0) { if (a == b) next = c->pc + imm_b(x); break; }   // beq
        if (F3(x) == 1) { if (a != b) next = c->pc + imm_b(x); break; }   // bne
        return -1;
    case OP_JAL:   c->x[rd] = c->pc + 4; next = c->pc + imm_j(x); break;
    case OP_JALR:  { uint32_t t = (a + imm_i(x)) & ~1u; c->x[rd] = c->pc + 4; next = t; break; } // 先算 t 再寫 rd（rd 可能=rs1）
    case OP_LUI:   c->x[rd] = imm_u(x); break;
    case OP_AUIPC: c->x[rd] = c->pc + imm_u(x); break;
    default: return -1;
    }
    c->x[0] = 0;          // x0 永遠是 0（就算指令寫了 x0 也要清回來）
    c->pc = next;
    return 0;
}

static int fails = 0;
#define CHECK(got, exp) do { uint32_t g_ = (uint32_t)(got), e_ = (uint32_t)(exp); \
    if (g_ != e_) { printf("FAIL line %d: got 0x%08X exp 0x%08X\n", __LINE__, (unsigned)g_, (unsigned)e_); fails++; } } while (0)

int main(void) {
    // 期望值 = 用 riscv64-unknown-elf-as -march=rv32i 組譯 + objdump 得到的
    CHECK(enc_i(5, 0, 0, 1, OP_IMM), 0x00500093);            // addi x1,x0,5
    CHECK(enc_r(0, 2, 1, 0, 3, OP_OP), 0x002081b3);          // add x3,x1,x2
    CHECK(enc_r(0x20, 1, 3, 0, 4, OP_OP), 0x40118233);       // sub x4,x3,x1
    CHECK(enc_i(8, 2, 2, 5, OP_LOAD), 0x00812283);           // lw x5,8(x2)
    CHECK(enc_s(-12, 5, 2, 2, OP_STORE), 0xfe512a23);        // sw x5,-12(x2)
    CHECK(enc_i(-1, 7, 0, 6, OP_IMM), 0xfff38313);           // addi x6,x7,-1
    CHECK(enc_b(-24, 2, 1, 0, OP_BR), 0xfe2084e3);           // beq x1,x2,-24
    CHECK(enc_b(0x7e4, 4, 3, 1, OP_BR), 0x7e419263);         // bne x3,x4,+2020
    CHECK(enc_j(0x7e0, 1, OP_JAL), 0x7e0000ef);              // jal x1,+2016
    CHECK(enc_j(-4, 0, OP_JAL), 0xffdff06f);                 // jal x0,-4
    CHECK(enc_i(0, 1, 0, 0, OP_JALR), 0x00008067);           // jalr x0,0(x1) = ret
    CHECK(enc_u(0x12345, 5, OP_LUI), 0x123452b7);            // lui x5,0x12345
    CHECK(enc_u(0xFFFFF, 6, OP_AUIPC), 0xfffff317);          // auipc x6,0xfffff
    // 解碼回來要一樣（round trip）
    CHECK(imm_b(0xfe2084e3), -24);  CHECK(imm_b(0x7e419263), 0x7e4);
    CHECK(imm_j(0xffdff06f), -4);   CHECK(imm_j(0x7e0000ef), 0x7e0);
    CHECK(imm_s(0xfe512a23), -12);
    char s[64];
    disasm(0xfe2084e3, s); printf("%-12s %s\n", "0xfe2084e3", s);
    if (strcmp(s, "beq x1, x2, -24")) { printf("FAIL disasm\n"); fails++; }

    // 模擬器測試：sum = 1+2+...+10，結果存到 mem[0x100]
    CPU c; memset(&c, 0, sizeof c);
    uint32_t prog[] = {
        enc_i(0, 0, 0, 10, OP_IMM),        // 0x00 addi a0,x0,0   (sum)
        enc_i(10, 0, 0, 11, OP_IMM),       // 0x04 addi a1,x0,10  (i)
        enc_r(0, 11, 10, 0, 10, OP_OP),    // 0x08 loop: add a0,a0,a1
        enc_i(-1, 11, 0, 11, OP_IMM),      // 0x0c addi a1,a1,-1
        enc_b(-8, 0, 11, 1, OP_BR),        // 0x10 bne a1,x0,loop
        enc_s(0x100, 10, 0, 2, OP_STORE),  // 0x14 sw a0,0x100(x0)
        enc_i(5, 0, 0, 0, OP_IMM),         // 0x18 addi x0,x0,5 → x0 仍要是 0
        0xFFFFFFFF                         // 0x1c 停機
    };
    memcpy(c.mem, prog, sizeof prog);
    for (int i = 0; i < 7; i++) { disasm(prog[i], s); printf("  %02x: %08x  %s\n", i * 4, (unsigned)prog[i], s); }
    for (int i = 0; i < 1000 && step(&c) == 0; i++) { }      // 最多跑 1000 步，防無窮迴圈
    CHECK(ld32(&c, 0x100), 55);  CHECK(c.x[0], 0);  CHECK(c.pc, 0x1c);

    if (fails == 0) printf("rv32_encode_decode: ALL PASS\n");
    return fails != 0;
}
