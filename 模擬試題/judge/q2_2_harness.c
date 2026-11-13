// judge 用：從 stdin 讀指令、呼叫考生的函式、把結果印出來給 judge.py 比對。不用看這個檔案。
#include <stdio.h>
#include <stdint.h>
#include "packet.h"
#include "rv_imm.h"

int main(void) {
    char op;
    while (scanf(" %c", &op) == 1) {
        if (op == 'P') {
            unsigned v[6]; uint8_t b[6];
            for (int i = 0; i < 6; i++) { if (scanf("%x", &v[i]) != 1) return 2; b[i] = (uint8_t)v[i]; }
            hdr_t h = {0};
            int r = parse_header(b, &h);
            printf("%d %u %u %u %u %u\n", r, h.ver, h.type, h.len, h.seq, h.flags);
        } else if (op == 'B') {
            unsigned a[5];
            if (scanf("%u %u %u %u %u", &a[0], &a[1], &a[2], &a[3], &a[4]) != 5) return 2;
            hdr_t h = {(uint8_t)a[0], (uint8_t)a[1], (uint16_t)a[2], (uint16_t)a[3], (uint8_t)a[4]};
            uint8_t o[6] = {0};
            build_header(&h, o);
            printf("%02x%02x%02x%02x%02x%02x\n", o[0], o[1], o[2], o[3], o[4], o[5]);
        } else if (op == 'I') {
            unsigned insn;
            if (scanf("%x", &insn) != 1) return 2;
            printf("%d %d %d %d\n", imm_i(insn), imm_s(insn), imm_b(insn), imm_j(insn));
        } else if (op == 'E') {
            unsigned f3, rs1, rs2; int off;
            if (scanf("%u %u %u %d", &f3, &rs1, &rs2, &off) != 4) return 2;
            printf("%08x\n", enc_b(f3, rs1, rs2, off));
        } else {
            return 2;
        }
        fflush(stdout);
    }
    return 0;
}
