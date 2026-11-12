// bitstream.c — 從 byte 陣列「一個位元一個位元」讀 / 寫固定寬度欄位
// 題型：「從位元流中取出固定寬度的欄位」「把欄位依序填入位元流」
// 兩種順序（題目一定會講，看清楚！）：
//   MSB-first（大部分網路協定、影像格式）：每個 byte 先用 bit7，欄位也是高位先出
//   LSB-first（deflate/zip、很多 UART/硬體 FIFO）：每個 byte 先用 bit0，欄位低位先出
// 編譯：gcc -O2 -Wall -Wextra bitstream.c -o bs && ./bs
#include <stdio.h>
#include <stdint.h>
#include <string.h>

typedef struct {
    uint8_t *buf;   // 資料
    size_t   pos;   // 目前在第幾個「位元」（不是 byte！）
} BitStream;

// ===== MSB-first =====
// 讀 n 位（1..32）。一次讀 1 位最好懂，也自動處理跨 byte / 跨 word 的欄位
uint32_t read_msb(BitStream *s, int n) {
    uint32_t v = 0;
    for (int i = 0; i < n; i++) {
        size_t byte = s->pos >> 3;          // pos / 8 = 第幾個 byte
        int    bit  = 7 - (s->pos & 7);     // 該 byte 內從 bit7 往下用
        v = (v << 1) | ((s->buf[byte] >> bit) & 1u);   // 新位元接在最右邊
        s->pos++;
    }
    return v;
}
// 寫 n 位（buf 要先清 0！否則 OR 會殘留舊資料）
void write_msb(BitStream *s, uint32_t v, int n) {
    for (int i = n - 1; i >= 0; i--) {      // 欄位高位先寫
        size_t byte = s->pos >> 3;
        int    bit  = 7 - (s->pos & 7);
        if ((v >> i) & 1u) s->buf[byte] |= (uint8_t)(1u << bit);
        else               s->buf[byte] &= (uint8_t)~(1u << bit);
        s->pos++;
    }
}

// ===== LSB-first =====
uint32_t read_lsb(BitStream *s, int n) {
    uint32_t v = 0;
    for (int i = 0; i < n; i++) {
        size_t byte = s->pos >> 3;
        int    bit  = s->pos & 7;           // 該 byte 內從 bit0 往上用
        v |= (uint32_t)((s->buf[byte] >> bit) & 1u) << i;   // 第 i 個讀到的放到第 i 位
        s->pos++;
    }
    return v;
}
void write_lsb(BitStream *s, uint32_t v, int n) {
    for (int i = 0; i < n; i++) {           // 欄位低位先寫
        size_t byte = s->pos >> 3;
        int    bit  = s->pos & 7;
        if ((v >> i) & 1u) s->buf[byte] |= (uint8_t)(1u << bit);
        else               s->buf[byte] &= (uint8_t)~(1u << bit);
        s->pos++;
    }
}

// ===== 從 uint32_t 陣列（word）取欄位：第 pos 位開始、寬 n 位，LSB-first =====
// 例：硬體暫存器陣列、把 32 位元 word 當成連續位元串。欄位可能跨兩個 word
uint32_t get_bits_words(const uint32_t *w, size_t pos, int n) {
    size_t idx = pos >> 5;                  // pos / 32
    int    off = pos & 31;                  // pos % 32
    uint64_t two = ((uint64_t)w[idx + 1] << 32) | w[idx];   // 兩個 word 拼成 64 位（注意 idx+1 不能越界）
    uint64_t mask = (n == 32) ? 0xFFFFFFFFull : ((1ull << n) - 1);
    return (uint32_t)((two >> off) & mask);
}

// ===== 自我測試 =====
static int fails = 0;
#define CHECK(got, exp) do { uint32_t g_ = (got), e_ = (exp); \
    if (g_ != e_) { printf("FAIL line %d: got 0x%X exp 0x%X\n", __LINE__, (unsigned)g_, (unsigned)e_); fails++; } } while (0)

int main(void) {
    // --- MSB-first：bytes A5 3C = 1010 0101 0011 1100
    uint8_t d1[] = {0xA5, 0x3C};
    BitStream r = {d1, 0};
    CHECK(read_msb(&r, 3), 0x5);     // 101
    CHECK(read_msb(&r, 7), 0x14);    // 00101 00 → 跨 byte：0010100
    CHECK(read_msb(&r, 6), 0x3C);    // 111100

    // --- LSB-first：0xA5 的 bit0 先出 → 1,0,1,0,0,1,0,1
    BitStream q = {d1, 0};
    CHECK(read_lsb(&q, 3), 0x5);     // bit2..0 = 101
    CHECK(read_lsb(&q, 7), 0x14);    // 低 5 位 = A5 的 bit7..3 (10100)，高 2 位 = 3C 的 bit1..0 (00) → 跨 byte
    CHECK(read_lsb(&q, 6), 0x0F);    // 3C 的 bit7..2 = 001111

    // --- 寫入後讀回（round trip），欄位寬度 1..32 混合
    int widths[] = {3, 5, 12, 1, 32, 7, 17, 9};
    uint32_t vals[] = {5, 0x1F, 0xABC, 1, 0xDEADBEEF, 0x55, 0x1ABCD, 0x101};
    uint8_t buf[16]; memset(buf, 0, sizeof buf);
    BitStream w = {buf, 0};
    for (int i = 0; i < 8; i++) write_msb(&w, vals[i], widths[i]);
    BitStream rr = {buf, 0};
    for (int i = 0; i < 8; i++) CHECK(read_msb(&rr, widths[i]), vals[i]);
    CHECK(buf[0], 0xBF);             // 101 11111 → 1011 1111

    memset(buf, 0, sizeof buf);
    BitStream w2 = {buf, 0};
    for (int i = 0; i < 8; i++) write_lsb(&w2, vals[i], widths[i]);
    BitStream r2 = {buf, 0};
    for (int i = 0; i < 8; i++) CHECK(read_lsb(&r2, widths[i]), vals[i]);
    CHECK(buf[0], 0xFD);             // 低 3 位 101，再往上 5 位 11111 → 1111 1101

    // --- 跨 word：bit 28 開始取 8 位 = w0 的高 4 位 + w1 的低 4 位
    uint32_t words[] = {0xA0000000u, 0x0000000Bu, 0};
    CHECK(get_bits_words(words, 28, 8), 0xBA);
    CHECK(get_bits_words(words, 0, 32), 0xA0000000u);

    if (fails == 0) printf("bitstream: ALL PASS\n");
    return fails != 0;
}
