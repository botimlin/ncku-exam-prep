/* checksum_misc.c — 「驗證資料有沒有傳錯」常見的簡單校驗碼（單檔，沒有 .h）
 *
 * 要用就把需要的函式整段複製過去。全部純 C11、無 malloc、MCU 可用。
 *   adler32    zlib 用的，比 CRC 快，可增量（第一次傳 1）
 *   fletcher16 兩個累加器 mod 255
 *   xor8       全部 XOR（NMEA GPS 句子的 *hh 校驗就是這個）
 *   sum8 / lrc8 加總取低 8 位；LRC = 加總的二補數（Modbus ASCII）
 *   sum32      以 uint32 為單位加總（溢位自然捨去）
 *   inet_csum  網際網路校驗（IP/UDP/TCP，RFC 1071）：16-bit 一補數和再取反
 *
 * 測試：gcc -O2 -Wall -Wextra -std=c11 -DTEST_MAIN checksum_misc.c -o ck && ./ck
 */
#include <stdint.h>
#include <stddef.h>

#define ADLER_MOD  65521u   /* 小於 2^16 的最大質數 */
#define ADLER_NMAX 5552u    /* 最多累積這麼多 byte 才需要取一次 mod（不會溢位）*/

/* Adler-32：a = 1 + 所有 byte 的和，b = 每一步 a 的和，結果 = (b<<16)|a
 * 優化：不要每個 byte 都 %（除法很慢），每 5552 byte 才 % 一次 */
uint32_t adler32(uint32_t adler, const uint8_t *p, size_t n) {
    uint32_t a = adler & 0xFFFFu, b = adler >> 16;
    while (n) {
        size_t k = n < ADLER_NMAX ? n : ADLER_NMAX;
        n -= k;
        while (k--) { a += *p++; b += a; }
        a %= ADLER_MOD; b %= ADLER_MOD;
    }
    return (b << 16) | a;
}

uint16_t fletcher16(const uint8_t *p, size_t n) {
    uint32_t s1 = 0, s2 = 0;
    while (n) {
        size_t k = n < 5802 ? n : 5802;   /* 同樣延後取 mod 的技巧 */
        n -= k;
        while (k--) { s1 += *p++; s2 += s1; }
        s1 %= 255; s2 %= 255;
    }
    return (uint16_t)((s2 << 8) | s1);
}

uint8_t xor8(const uint8_t *p, size_t n) {
    uint8_t x = 0;
    while (n--) x ^= *p++;
    return x;
}

uint8_t sum8(const uint8_t *p, size_t n) {
    uint8_t s = 0;
    while (n--) s = (uint8_t)(s + *p++);
    return s;
}

uint8_t lrc8(const uint8_t *p, size_t n) { return (uint8_t)(0u - sum8(p, n)); }

uint32_t sum32(const uint32_t *w, size_t nwords) {
    uint32_t s = 0;
    while (nwords--) s += *w++;
    return s;
}

/* RFC 1071：每 2 byte 當成大端序 16-bit 相加，進位折回來，最後取反 */
uint16_t inet_csum(const uint8_t *p, size_t n) {
    uint32_t s = 0;
    while (n > 1) { s += ((uint32_t)p[0] << 8) | p[1]; p += 2; n -= 2; }
    if (n) s += (uint32_t)p[0] << 8;                 /* 奇數長度：補 0 */
    while (s >> 16) s = (s & 0xFFFFu) + (s >> 16);  /* 進位折回（end-around carry）*/
    return (uint16_t)~s;
}

#ifdef TEST_MAIN
#include <stdio.h>
#include <string.h>
static int fails = 0;
#define CHECK(c, m) do { printf((c) ? "  PASS  %s\n" : "  FAIL  %s\n", m); if (!(c)) fails++; } while (0)
#define S(str) (const uint8_t *)(str), strlen(str)

int main(void) {
    static uint8_t big[100000];
    CHECK(adler32(1, S("Wikipedia")) == 0x11E60398u, "adler32(\"Wikipedia\") = 0x11E60398");
    CHECK(adler32(1, S("")) == 1u, "adler32(\"\") = 1");
    for (size_t i = 0; i < sizeof big; i++) big[i] = 0xFF;   /* 最容易溢位的情況 */
    uint32_t a = 1, b = 0;                                    /* 逐 byte 取 mod 的笨方法 */
    for (size_t i = 0; i < sizeof big; i++) { a = (a + big[i]) % 65521u; b = (b + a) % 65521u; }
    CHECK(adler32(1, big, sizeof big) == ((b << 16) | a), "adler32 10 萬個 0xFF == 笨方法");
    CHECK(adler32(adler32(1, big, 777), big + 777, sizeof big - 777) == adler32(1, big, sizeof big),
          "adler32 增量（切兩段）");
    CHECK(fletcher16(S("abcde")) == 0xC8F0, "fletcher16(\"abcde\") = 0xC8F0");
    CHECK(fletcher16(S("abcdef")) == 0x2057, "fletcher16(\"abcdef\") = 0x2057");
    CHECK(fletcher16(S("abcdefgh")) == 0x0627, "fletcher16(\"abcdefgh\") = 0x0627");
    uint32_t s1 = 0, s2 = 0;
    for (size_t i = 0; i < sizeof big; i++) { s1 = (s1 + big[i]) % 255; s2 = (s2 + s1) % 255; }
    CHECK(fletcher16(big, sizeof big) == ((s2 << 8) | s1), "fletcher16 10 萬個 0xFF == 笨方法");
    /* NMEA 例句 $GPGLL,5300.97914,N,00259.98174,E,125926,A*28 → '$' 與 '*' 之間 XOR = 0x28 */
    CHECK(xor8(S("GPGLL,5300.97914,N,00259.98174,E,125926,A")) == 0x28, "xor8 (NMEA) = 0x28");
    CHECK(sum8(S("123456789")) == 0xDD, "sum8(\"123456789\") = 0xDD");
    CHECK((uint8_t)(sum8(S("123456789")) + lrc8(S("123456789"))) == 0, "sum8 + lrc8 = 0");
    const uint32_t w[3] = {0xFFFFFFFFu, 2u, 3u};
    CHECK(sum32(w, 3) == 4u, "sum32 溢位捨去");
    const uint8_t rfc[8] = {0x00, 0x01, 0xf2, 0x03, 0xf4, 0xf5, 0xf6, 0xf7};  /* RFC 1071 範例 */
    CHECK(inet_csum(rfc, 8) == 0x220D, "inet_csum(RFC1071 範例) = 0x220D");
    printf(fails ? "結果：有失敗\n" : "結果：全部通過\n");
    return fails;
}
#endif
