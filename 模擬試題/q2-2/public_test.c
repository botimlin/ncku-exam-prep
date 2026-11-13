// public_test.c — 2-2 的公開測資（make test）。judge 用的是更多組隱藏測資。
#include <stdio.h>
#include <string.h>
#include "packet.h"
#include "rv_imm.h"

static int fails = 0;
#define CHECK(cond, ...) do { if (cond) printf("  PASS  " __VA_ARGS__); \
                              else { printf("  FAIL  " __VA_ARGS__); fails++; } printf("\n"); } while (0)

int main(void) {
    printf("[A] packet header\n");
    CHECK(crc16_ccitt_false((const uint8_t *)"123456789", 9) == 0x29B1, "crc16(\"123456789\") == 0x29B1");

    // ver=5 type=0x13 len=0x2A7 seq=0x1F5 flags=2 → 0xB3 0x2A 0x77 0xD6 + crc(LE)
    const uint8_t pkt[6] = {0xB3, 0x2A, 0x77, 0xD6, 0x00, 0x00};
    uint8_t b[6]; memcpy(b, pkt, 6);
    uint16_t c = crc16_ccitt_false(b, 4); b[4] = (uint8_t)c; b[5] = (uint8_t)(c >> 8);
    hdr_t h; int r = parse_header(b, &h);
    CHECK(r == HDR_OK, "parse 回傳 HDR_OK（得到 %d）", r);
    CHECK(h.ver == 5 && h.type == 0x13 && h.len == 0x2A7 && h.seq == 0x1F5 && h.flags == 2,
          "欄位 ver=%u type=0x%X len=0x%X seq=0x%X flags=%u（預期 5 0x13 0x2A7 0x1F5 2）",
          h.ver, h.type, h.len, h.seq, h.flags);
    uint8_t o[6]; build_header(&h, o);
    CHECK(memcmp(o, b, 6) == 0, "build(parse(x)) == x（得到 %02X %02X %02X %02X %02X %02X）",
          o[0], o[1], o[2], o[3], o[4], o[5]);
    b[2] ^= 0x01;
    CHECK(parse_header(b, &h) == HDR_BAD_CRC, "改一個 bit → HDR_BAD_CRC");

    printf("[C] RISC-V immediates\n");
    CHECK(imm_i(0xfff00513) == -1, "addi a0, zero, -1 → imm_i = -1");
    CHECK(imm_s(0x10a02023) == 256, "sw a0, 256(zero) → imm_s = 256（得到 %d）", imm_s(0x10a02023));
    CHECK(imm_b(0xfe059ce3) == -8, "bne a1, zero, -8 → imm_b = -8（得到 %d）", imm_b(0xfe059ce3));
    CHECK(imm_j(0x0080006f) == 8, "jal zero, +8 → imm_j = 8（得到 %d）", imm_j(0x0080006f));
    CHECK(enc_b(1, 11, 0, -8) == 0xfe059ce3, "enc_b(bne, a1, zero, -8) == 0xfe059ce3（得到 0x%08x）",
          enc_b(1, 11, 0, -8));

    printf(fails ? "\n%d 項沒過\n" : "\n公開測資全部通過（judge 還有隱藏測資）\n", fails);
    return fails != 0;
}
