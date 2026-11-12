/* crc32.c — 實作。原理一句話：CRC = 把資料當成 GF(2) 多項式除以 poly 的餘數，
 * 「XOR 取代減法」。查表法 = 先把「一個 byte 會造成的影響」預先算好 256 種。
 *
 * RP2350 提示：DMA 有硬體 sniffer 可以邊搬資料邊算 CRC-32（幾乎 0 CPU 時間），
 *   zlib 相容的設定大約是：bit-reversed 模式 + 種子 0xFFFFFFFF + 輸出反轉+取反。
 *   務必用本檔 crc32_update 的結果去驗證硬體設定（考場上先比對 "123456789"）。
 */
#include "crc32.h"

#define POLY32R  0xEDB88320u   /* CRC-32  反轉多項式  TODO(改這裡) 換別的 reflected CRC-32 */
#define POLY32CR 0x82F63B78u   /* CRC-32C 反轉多項式 */
#define POLY16   0x1021u       /* CRC-16/CCITT 多項式（不反轉）*/

static uint32_t T[4][256];     /* T[0] = 一般表；T[1..3] = slice-by-4 用的延伸表 */
static uint32_t TC[256];       /* CRC-32C 表 */
static uint16_t T16[256];      /* CRC-16 表 */
static int inited = 0;

/* 用一個 byte 建出「反轉式」表格的一格：跑 8 次 bitwise 步驟 */
static uint32_t make_entry_r(uint32_t c, uint32_t polyr) {
    for (int k = 0; k < 8; k++)
        c = (c >> 1) ^ (polyr & (0u - (c & 1u)));  /* 最低位是 1 才 XOR poly（無分支寫法）*/
    return c;
}

void crc32_init(void) {
    for (uint32_t i = 0; i < 256; i++) {
        T[0][i] = make_entry_r(i, POLY32R);
        TC[i]   = make_entry_r(i, POLY32CR);
        uint32_t c = i << 8;                       /* 非反轉：從最高位開始 */
        for (int k = 0; k < 8; k++)
            c = ((c & 0x8000u) ? (c << 1) ^ POLY16 : (c << 1)) & 0xFFFFu;
        T16[i] = (uint16_t)c;
    }
    /* T[t][i] = 「byte i 後面再接 t 個 0 byte」的 CRC 影響 */
    for (int i = 0; i < 256; i++)
        for (int t = 1; t < 4; t++)
            T[t][i] = (T[t - 1][i] >> 8) ^ T[0][T[t - 1][i] & 0xFF];
    inited = 1;
}

/* ① 逐位元版：最慢（每 byte 8 次迴圈），但不需要表，最不容易寫錯 */
uint32_t crc32_bitwise(uint32_t crc, const uint8_t *p, size_t n) {
    crc = ~crc;                                   /* init = 0xFFFFFFFF（因為傳入 0）*/
    while (n--) {
        crc ^= *p++;
        for (int k = 0; k < 8; k++)
            crc = (crc >> 1) ^ (POLY32R & (0u - (crc & 1u)));
    }
    return ~crc;                                  /* xorout = 0xFFFFFFFF */
}

/* ② 查表版：每 byte 一次查表，約快 5~8 倍 */
uint32_t crc32_table(uint32_t crc, const uint8_t *p, size_t n) {
    if (!inited) crc32_init();
    crc = ~crc;
    while (n--) crc = (crc >> 8) ^ T[0][(crc ^ *p++) & 0xFF];
    return ~crc;
}

/* ③ slice-by-4：一次吃 4 byte，4 次查表互相獨立 → CPU 可並行，再快 2~3 倍 */
uint32_t crc32_slice4(uint32_t crc, const uint8_t *p, size_t n) {
    if (!inited) crc32_init();
    crc = ~crc;
    while (n >= 4) {
        /* 逐 byte 組成 little-endian 字：不怕沒對齊、不怕大小端 */
        crc ^= (uint32_t)p[0] | ((uint32_t)p[1] << 8) |
               ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
        crc = T[3][crc & 0xFF] ^ T[2][(crc >> 8) & 0xFF] ^
              T[1][(crc >> 16) & 0xFF] ^ T[0][crc >> 24];
        p += 4; n -= 4;
    }
    while (n--) crc = (crc >> 8) ^ T[0][(crc ^ *p++) & 0xFF];   /* 剩下 0~3 byte */
    return ~crc;
}

uint32_t crc32_update(uint32_t crc, const uint8_t *p, size_t n) {
    return crc32_slice4(crc, p, n);
}

/* CRC-32C：跟 CRC-32 一模一樣，只是換多項式（表不同）*/
uint32_t crc32c_update(uint32_t crc, const uint8_t *p, size_t n) {
    if (!inited) crc32_init();
    crc = ~crc;
    while (n--) crc = (crc >> 8) ^ TC[(crc ^ *p++) & 0xFF];
    return ~crc;
}

/* CRC-16/CCITT-FALSE：非反轉 → 左移，用「高 8 位」查表 */
uint16_t crc16_ccitt_false(uint16_t crc, const uint8_t *p, size_t n) {
    if (!inited) crc32_init();
    while (n--) crc = (uint16_t)((crc << 8) ^ T16[((crc >> 8) ^ *p++) & 0xFF]);
    return crc;
}

/* ---- 通用版 ---- */
static uint32_t reflect(uint32_t v, int bits) {
    uint32_t r = 0;
    for (int i = 0; i < bits; i++) { r = (r << 1) | (v & 1u); v >>= 1; }
    return r;
}

uint32_t crc_generic(const crc_param_t *c, const uint8_t *p, size_t n) {
    const uint32_t top  = 1u << (c->width - 1);
    const uint32_t mask = (c->width == 32) ? 0xFFFFFFFFu : ((1u << c->width) - 1u);
    uint32_t crc = c->init & mask;
    while (n--) {
        uint32_t b = *p++;
        if (c->refin) b = reflect(b, 8);
        crc ^= b << (c->width - 8);               /* 把 byte 放到最高的 8 位 */
        for (int k = 0; k < 8; k++)
            crc = (crc & top) ? ((crc << 1) ^ c->poly) : (crc << 1);
        crc &= mask;
    }
    if (c->refout) crc = reflect(crc, c->width);
    return (crc ^ c->xorout) & mask;
}
