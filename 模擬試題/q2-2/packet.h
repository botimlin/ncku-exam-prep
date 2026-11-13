// packet.h — 2-2 §A 的介面（不要改這個檔案：judge 會用它編譯）
#pragma once
#include <stdint.h>

typedef struct {
    uint8_t  ver;    // 3 bit
    uint8_t  type;   // 5 bit
    uint16_t len;    // 12 bit
    uint16_t seq;    // 10 bit
    uint8_t  flags;  // 2 bit
} hdr_t;

#define HDR_SIZE      6
#define HDR_VERSION   5

#define HDR_OK        0
#define HDR_BAD_CRC  -1
#define HDR_BAD_VER  -2

uint16_t crc16_ccitt_false(const uint8_t *p, int n);
int  parse_header(const uint8_t b[HDR_SIZE], hdr_t *h);
void build_header(const hdr_t *h, uint8_t out[HDR_SIZE]);
