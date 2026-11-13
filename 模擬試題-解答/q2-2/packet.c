// 解答：packet.c
#include "packet.h"

uint16_t crc16_ccitt_false(const uint8_t *p, int n) {
    uint16_t crc = 0xFFFF;
    for (int i = 0; i < n; i++) {
        crc ^= (uint16_t)p[i] << 8;
        for (int k = 0; k < 8; k++)
            crc = (crc & 0x8000) ? (uint16_t)((crc << 1) ^ 0x1021) : (uint16_t)(crc << 1);
    }
    return crc;
}

// 位元流（MSB 先）：ver[2:0] type[4:0] | len[11:4] | len[3:0] seq[9:6] | seq[5:0] flags[1:0]
// 最簡單不會錯的寫法：先把 4 個 byte 接成一個 32-bit 大端數，再用 shift + mask 取欄位。
int parse_header(const uint8_t b[HDR_SIZE], hdr_t *h) {
    uint32_t w = (uint32_t)b[0] << 24 | (uint32_t)b[1] << 16 | (uint32_t)b[2] << 8 | b[3];
    h->ver   = (w >> 29) & 0x7;
    h->type  = (w >> 24) & 0x1F;     // bug 1：原本 mask 0x0F，少了 1 bit
    h->len   = (w >> 12) & 0xFFF;
    h->seq   = (w >> 2)  & 0x3FF;    // bug 2：原本 (b[2]&0x0F)<<4，應該 <<6
    h->flags =  w        & 0x3;

    uint16_t got = (uint16_t)(b[4] | (b[5] << 8));   // bug 3：CRC 是 little-endian
    if (got != crc16_ccitt_false(b, 4)) return HDR_BAD_CRC;   // 先檢查 CRC 再檢查版本（規格的順序）
    if (h->ver != HDR_VERSION) return HDR_BAD_VER;
    return HDR_OK;
}

void build_header(const hdr_t *h, uint8_t out[HDR_SIZE]) {
    uint32_t w = (uint32_t)(h->ver & 0x7) << 29 | (uint32_t)(h->type & 0x1F) << 24 |
                 (uint32_t)(h->len & 0xFFF) << 12 | (uint32_t)(h->seq & 0x3FF) << 2 |
                 (uint32_t)(h->flags & 0x3);
    out[0] = (uint8_t)(w >> 24); out[1] = (uint8_t)(w >> 16);
    out[2] = (uint8_t)(w >> 8);  out[3] = (uint8_t)w;
    uint16_t c = crc16_ccitt_false(out, 4);
    out[4] = (uint8_t)c; out[5] = (uint8_t)(c >> 8);
}
