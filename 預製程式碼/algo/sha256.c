/* sha256.c — 結構跟 sha1_sha0.c 幾乎一樣：64 byte 一塊、64 回合、同樣的 padding。
 * 差別：8 個狀態字、64 個常數 K、用「右旋」ROTR。
 */
#include "sha256.h"

#define ROTR(x, n) (((x) >> (n)) | ((x) << (32 - (n))))

static const uint32_t K[64] = {   /* 前 64 個質數立方根的小數部分 */
    0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
    0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
    0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
    0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
    0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
    0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
    0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
    0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2 };

static void compress(sha256_ctx *ctx, const uint8_t *blk) {
    uint32_t w[64], s[8];
    for (int i = 0; i < 16; i++)
        w[i] = ((uint32_t)blk[4*i] << 24) | ((uint32_t)blk[4*i+1] << 16) |
               ((uint32_t)blk[4*i+2] << 8) | (uint32_t)blk[4*i+3];
    for (int i = 16; i < 64; i++) {
        uint32_t s0 = ROTR(w[i-15], 7) ^ ROTR(w[i-15], 18) ^ (w[i-15] >> 3);
        uint32_t s1 = ROTR(w[i-2], 17) ^ ROTR(w[i-2], 19)  ^ (w[i-2] >> 10);
        w[i] = w[i-16] + s0 + w[i-7] + s1;
    }
    for (int i = 0; i < 8; i++) s[i] = ctx->h[i];      /* s = a,b,c,d,e,f,g,h */
    for (int i = 0; i < 64; i++) {
        uint32_t S1 = ROTR(s[4], 6) ^ ROTR(s[4], 11) ^ ROTR(s[4], 25);
        uint32_t ch = (s[4] & s[5]) ^ (~s[4] & s[6]);
        uint32_t t1 = s[7] + S1 + ch + K[i] + w[i];
        uint32_t S0 = ROTR(s[0], 2) ^ ROTR(s[0], 13) ^ ROTR(s[0], 22);
        uint32_t mj = (s[0] & s[1]) ^ (s[0] & s[2]) ^ (s[1] & s[2]);
        for (int j = 7; j > 0; j--) s[j] = s[j-1];      /* 全體往後挪一格 */
        s[4] += t1;
        s[0] = t1 + S0 + mj;
    }
    for (int i = 0; i < 8; i++) ctx->h[i] += s[i];
}

void sha256_init(sha256_ctx *c) {
    static const uint32_t H0[8] = { 0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,
                                    0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19 };
    for (int i = 0; i < 8; i++) c->h[i] = H0[i];
    c->total = 0; c->used = 0;
}

void sha256_update(sha256_ctx *c, const uint8_t *p, size_t n) {
    c->total += n;
    while (n--) {                       /* 簡單版：逐 byte 放進 buf（夠快且不易錯）*/
        c->buf[c->used++] = *p++;
        if (c->used == 64) { compress(c, c->buf); c->used = 0; }
    }
}

void sha256_final(sha256_ctx *c, uint8_t out[32]) {
    uint64_t bits = c->total * 8;
    c->buf[c->used++] = 0x80;
    if (c->used > 56) { while (c->used < 64) c->buf[c->used++] = 0; compress(c, c->buf); c->used = 0; }
    while (c->used < 56) c->buf[c->used++] = 0;
    for (int i = 7; i >= 0; i--) c->buf[c->used++] = (uint8_t)(bits >> (8 * i));
    compress(c, c->buf);
    for (int i = 0; i < 8; i++)
        for (int j = 0; j < 4; j++) out[4*i + j] = (uint8_t)(c->h[i] >> (24 - 8*j));
}

void sha256(const uint8_t *p, size_t n, uint8_t out[32]) {
    sha256_ctx c; sha256_init(&c); sha256_update(&c, p, n); sha256_final(&c, out);
}
