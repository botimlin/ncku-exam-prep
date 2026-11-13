// packet.c — 2-2 §A：封包標頭的打包與拆解（規格在 README.md §A）
//
// 這份是同學寫到一半的版本：parse_header 有 bug，build_header 還沒寫。
// 自己測：make test（只有幾個公開測資；judge 的測資更多）

#include "packet.h"

// CRC-16/CCITT-FALSE：poly 0x1021、init 0xFFFF、不反轉、不 xor。
// "123456789" → 0x29B1。這個函式是對的，不用改。
uint16_t crc16_ccitt_false(const uint8_t *p, int n) {
    uint16_t crc = 0xFFFF;
    for (int i = 0; i < n; i++) {
        crc ^= (uint16_t)p[i] << 8;
        for (int k = 0; k < 8; k++)
            crc = (crc & 0x8000) ? (uint16_t)((crc << 1) ^ 0x1021) : (uint16_t)(crc << 1);
    }
    return crc;
}

int parse_header(const uint8_t b[HDR_SIZE], hdr_t *h) {
    h->ver   = b[0] >> 5;
    h->type  = b[0] & 0x0F;
    h->len   = (uint16_t)((b[1] << 4) | (b[2] >> 4));
    h->seq   = (uint16_t)(((b[2] & 0x0F) << 4) | (b[3] >> 2));
    h->flags = b[3] & 0x03;

    uint16_t got = (uint16_t)((b[4] << 8) | b[5]);
    if (got != crc16_ccitt_false(b, 4)) return HDR_BAD_CRC;
    if (h->ver != HDR_VERSION) return HDR_BAD_VER;
    return HDR_OK;
}

void build_header(const hdr_t *h, uint8_t out[HDR_SIZE]) {
    // TODO(改這裡)：依規格把 h 的欄位放進 out[0..3]，再算 CRC 放進 out[4..5]。
    // 欄位值超過自己的寬度時，只取低位元（例如 len = 0x1234 → 只放 0x234）。
    (void)h;
    for (int i = 0; i < HDR_SIZE; i++) out[i] = 0;
}
