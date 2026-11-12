/* sha1_sha0.h — SHA-1 與 SHA-0（共用同一份程式碼）
 *
 * SHA-0 與 SHA-1 唯一差別：訊息擴展 W[t] 計算時，SHA-1 多做「左旋 1 位」。
 *   SHA-1: W[t] = ROTL1(W[t-3] ^ W[t-8] ^ W[t-14] ^ W[t-16])
 *   SHA-0: W[t] =       W[t-3] ^ W[t-8] ^ W[t-14] ^ W[t-16]
 *
 * 一次算完：   uint8_t out[20]; sha1(data, len, out);   sha0(data, len, out);
 * 串流（資料分好幾包收到時）：
 *     sha1_ctx c; sha1_init(&c, 0);   // 第二個參數：0 = SHA-1，1 = SHA-0
 *     sha1_update(&c, pkt1, n1);  sha1_update(&c, pkt2, n2); ...
 *     sha1_final(&c, out);            // out = 20 bytes（大端序，直接印 hex 即可）
 *
 * 驗證：SHA-1("abc") = a9993e364706816aba3e25717850c26c9cd0d89d
 *       SHA-0("abc") = 0164b8a914cd2a5e74c4f7ff082c4d97f1edf880
 */
#ifndef SHA1_SHA0_H
#define SHA1_SHA0_H
#include <stdint.h>
#include <stddef.h>

typedef struct {
    uint32_t h[5];       /* 目前的雜湊狀態 */
    uint64_t total;      /* 目前為止總共餵了幾個 byte */
    uint8_t  buf[64];    /* 湊不滿 64 byte 的尾巴先放這 */
    uint32_t used;       /* buf 裡已有幾個 byte */
    int      is_sha0;    /* 1 = SHA-0 */
} sha1_ctx;

void sha1_init  (sha1_ctx *c, int is_sha0);
void sha1_update(sha1_ctx *c, const uint8_t *p, size_t n);
void sha1_final (sha1_ctx *c, uint8_t out[20]);
void sha1(const uint8_t *p, size_t n, uint8_t out[20]);
void sha0(const uint8_t *p, size_t n, uint8_t out[20]);

#endif
