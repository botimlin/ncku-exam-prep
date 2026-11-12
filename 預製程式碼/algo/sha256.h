/* sha256.h — 精簡 SHA-256（API 跟 sha1_sha0.h 一樣的風格）
 *   uint8_t out[32]; sha256(data, len, out);
 *   或 sha256_ctx c; sha256_init(&c); sha256_update(&c,p,n)...; sha256_final(&c,out);
 * 驗證：SHA-256("abc") =
 *   ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
 */
#ifndef SHA256_H
#define SHA256_H
#include <stdint.h>
#include <stddef.h>

typedef struct {
    uint32_t h[8];
    uint64_t total;
    uint8_t  buf[64];
    uint32_t used;
} sha256_ctx;

void sha256_init  (sha256_ctx *c);
void sha256_update(sha256_ctx *c, const uint8_t *p, size_t n);
void sha256_final (sha256_ctx *c, uint8_t out[32]);
void sha256(const uint8_t *p, size_t n, uint8_t out[32]);

#endif
