/* sha1_sha0.c — 實作（純 C11，不用 malloc，MCU 可用；stack 用約 64 byte）
 *
 * 流程：資料切成 64 byte 一塊 → 每塊做一次 compress（80 回合）→ 最後補 padding：
 *   0x80，再補 0 直到長度 ≡ 56 (mod 64)，最後 8 byte 放「總位元數」（大端序）。
 * 優化點：W 只用 16 格循環陣列（省 RAM、cache 友善）；ROTL 編譯器會變成一條指令。
 */
#include "sha1_sha0.h"

#define ROTL(x, n) (((x) << (n)) | ((x) >> (32 - (n))))

static uint32_t load_be32(const uint8_t *p) {        /* 大端序讀 4 byte */
    return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) |
           ((uint32_t)p[2] << 8)  |  (uint32_t)p[3];
}

static void compress(sha1_ctx *ctx, const uint8_t *blk) {
    uint32_t w[16];
    for (int i = 0; i < 16; i++) w[i] = load_be32(blk + 4 * i);
    uint32_t a = ctx->h[0], b = ctx->h[1], c = ctx->h[2], d = ctx->h[3], e = ctx->h[4];
    for (int t = 0; t < 80; t++) {
        uint32_t wt;
        if (t < 16) wt = w[t];
        else {
            /* w[(t-3)&15] 等於 W[t-3] ... 循環陣列寫法 */
            wt = w[(t - 3) & 15] ^ w[(t - 8) & 15] ^ w[(t - 14) & 15] ^ w[t & 15];
            if (!ctx->is_sha0) wt = ROTL(wt, 1);    /* ★ SHA-1 與 SHA-0 唯一差別 */
            w[t & 15] = wt;
        }
        uint32_t f, k;
        if (t < 20)      { f = (b & c) | (~b & d);          k = 0x5A827999u; }
        else if (t < 40) { f = b ^ c ^ d;                   k = 0x6ED9EBA1u; }
        else if (t < 60) { f = (b & c) | (b & d) | (c & d); k = 0x8F1BBCDCu; }
        else             { f = b ^ c ^ d;                   k = 0xCA62C1D6u; }
        uint32_t tmp = ROTL(a, 5) + f + e + k + wt;
        e = d; d = c; c = ROTL(b, 30); b = a; a = tmp;
    }
    ctx->h[0] += a; ctx->h[1] += b; ctx->h[2] += c; ctx->h[3] += d; ctx->h[4] += e;
}

void sha1_init(sha1_ctx *c, int is_sha0) {
    c->h[0] = 0x67452301u; c->h[1] = 0xEFCDAB89u; c->h[2] = 0x98BADCFEu;
    c->h[3] = 0x10325476u; c->h[4] = 0xC3D2E1F0u;
    c->total = 0; c->used = 0; c->is_sha0 = is_sha0;
}

void sha1_update(sha1_ctx *c, const uint8_t *p, size_t n) {
    c->total += n;
    if (c->used) {                                   /* 先把上次剩的尾巴補滿 64 */
        while (n && c->used < 64) { c->buf[c->used++] = *p++; n--; }
        if (c->used < 64) return;
        compress(c, c->buf); c->used = 0;
    }
    while (n >= 64) { compress(c, p); p += 64; n -= 64; }   /* 整塊直接算，不複製 */
    while (n--) c->buf[c->used++] = *p++;                    /* 剩下的存起來 */
}

void sha1_final(sha1_ctx *c, uint8_t out[20]) {
    uint64_t bits = c->total * 8;
    c->buf[c->used++] = 0x80;
    if (c->used > 56) {                              /* 放不下長度 → 多一塊 */
        while (c->used < 64) c->buf[c->used++] = 0;
        compress(c, c->buf); c->used = 0;
    }
    while (c->used < 56) c->buf[c->used++] = 0;
    for (int i = 7; i >= 0; i--) c->buf[c->used++] = (uint8_t)(bits >> (8 * i));
    compress(c, c->buf);
    for (int i = 0; i < 5; i++) {                    /* 輸出：大端序 */
        out[4 * i]     = (uint8_t)(c->h[i] >> 24); out[4 * i + 1] = (uint8_t)(c->h[i] >> 16);
        out[4 * i + 2] = (uint8_t)(c->h[i] >> 8);  out[4 * i + 3] = (uint8_t)c->h[i];
    }
}

void sha1(const uint8_t *p, size_t n, uint8_t out[20]) {
    sha1_ctx c; sha1_init(&c, 0); sha1_update(&c, p, n); sha1_final(&c, out);
}
void sha0(const uint8_t *p, size_t n, uint8_t out[20]) {
    sha1_ctx c; sha1_init(&c, 1); sha1_update(&c, p, n); sha1_final(&c, out);
}
