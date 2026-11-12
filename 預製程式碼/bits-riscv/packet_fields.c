// packet_fields.c — 依「規格」把欄位打包進一個 32 位元數 / 從中拆出來
// 題型：「將欄位填入固定位置」「依規格重新排列位元」「封包 header 編碼解碼」
// 編譯：gcc -O2 -Wall -Wextra packet_fields.c -o pf && ./pf
//
// 假想規格（TODO(改這裡)：換成題目給的表格）：
//   bit 31..29  version (3 bits)
//   bit 28..24  type    (5 bits)
//   bit 23..12  length  (12 bits)
//   bit 11..0   id      (12 bits)
// 小技巧：shift = 該欄位的「lo」位置；mask = (1<<寬度)-1
#include <stdio.h>
#include <stdint.h>

// TODO(改這裡)：每個欄位的 SHIFT（最低位位置）與 WIDTH（寬度）
#define VER_SHIFT 29
#define VER_W     3
#define TYPE_SHIFT 24
#define TYPE_W     5
#define LEN_SHIFT 12
#define LEN_W     12
#define ID_SHIFT  0
#define ID_W      12
#define M(w) ((1u << (w)) - 1u)     // w 位的全 1（w < 32）

typedef struct { uint32_t ver, type, len, id; } Header;

// ---------- 方法 1：shift + mask（推薦！結果固定、可攜） ----------
uint32_t pack(Header h) {
    return ((h.ver  & M(VER_W))  << VER_SHIFT)    // 先 & mask 防止超出寬度污染別的欄位
         | ((h.type & M(TYPE_W)) << TYPE_SHIFT)
         | ((h.len  & M(LEN_W))  << LEN_SHIFT)
         | ((h.id   & M(ID_W))   << ID_SHIFT);
}
Header unpack(uint32_t x) {
    Header h;
    h.ver  = (x >> VER_SHIFT)  & M(VER_W);        // 先右移到最低位，再 & mask
    h.type = (x >> TYPE_SHIFT) & M(TYPE_W);
    h.len  = (x >> LEN_SHIFT)  & M(LEN_W);
    h.id   = (x >> ID_SHIFT)   & M(ID_W);
    return h;
}
// 只改一個欄位（例：把 type 設成 7），其他不動
uint32_t set_type(uint32_t x, uint32_t t) {
    x &= ~(M(TYPE_W) << TYPE_SHIFT);              // 1. 清空欄位
    x |= (t & M(TYPE_W)) << TYPE_SHIFT;           // 2. 填入新值
    return x;
}

// ---------- 方法 2：C bitfield（看起來方便，但「不建議」考試用） ----------
// 警告：bitfield 的排列順序（從 LSB 或 MSB 開始放）、填充、對齊都是
// 「implementation-defined」由編譯器決定！gcc 在 x86 / RISC-V 小端機器上
// 是「第一個成員放在最低位」，所以要「倒著寫」才對得上規格。換編譯器/大端機可能就錯。
typedef union {
    uint32_t raw;
    struct {                 // 從 LSB 往上寫（gcc 小端）
        uint32_t id   : 12;  // bit 11..0
        uint32_t len  : 12;  // bit 23..12
        uint32_t type : 5;   // bit 28..24
        uint32_t ver  : 3;   // bit 31..29
    } f;
} HeaderBF;

// ---------- 多 byte 欄位的 endian ----------
// 網路 / 很多檔案格式是「大端」（big-endian，高位 byte 先放）；RP2350 和 PC 是小端
// 用「逐 byte 組合」最安全，不管機器是大端還小端都對：
uint32_t load_be32(const uint8_t *p) { return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) | ((uint32_t)p[2] << 8) | p[3]; }
uint32_t load_le32(const uint8_t *p) { return ((uint32_t)p[3] << 24) | ((uint32_t)p[2] << 16) | ((uint32_t)p[1] << 8) | p[0]; }
uint16_t load_be16(const uint8_t *p) { return (uint16_t)((p[0] << 8) | p[1]); }
void store_be32(uint8_t *p, uint32_t v) { p[0] = v >> 24; p[1] = v >> 16; p[2] = v >> 8; p[3] = (uint8_t)v; }
void store_le32(uint8_t *p, uint32_t v) { p[0] = (uint8_t)v; p[1] = v >> 8; p[2] = v >> 16; p[3] = v >> 24; }

// ---------- 依規格「重新排列」位元：例 把 bit i 搬到 perm[i] ----------
uint32_t permute_bits(uint32_t x, const int perm[], int n) {
    uint32_t y = 0;
    for (int i = 0; i < n; i++)
        y |= ((x >> i) & 1u) << perm[i];          // 第 i 位 → 第 perm[i] 位
    return y;
}

static int fails = 0;
#define CHECK(c) do { if (!(c)) { printf("FAIL line %d: %s\n", __LINE__, #c); fails++; } } while (0)

int main(void) {
    Header h = {5, 0x13, 0x2A0, 0xBEE};
    uint32_t x = pack(h);
    // 手算：101 10011 0010 1010 0000 1011 1110 1110 = 1011 0011 0010 1010 0000 1011 1110 1110
    printf("pack = 0x%08X\n", (unsigned)x);   // printf 印 uint32_t 先轉 (unsigned) 最保險
    CHECK(x == 0xB32A0BEEu);
    Header g = unpack(x);
    CHECK(g.ver == 5 && g.type == 0x13 && g.len == 0x2A0 && g.id == 0xBEE);
    CHECK(unpack(set_type(x, 7)).type == 7 && unpack(set_type(x, 7)).len == 0x2A0);
    CHECK(pack((Header){9, 0, 0, 0}) == (1u << 29));       // 9 超過 3 位，被 mask 成 1

    HeaderBF b; b.raw = 0;
    b.f.ver = 5; b.f.type = 0x13; b.f.len = 0x2A0; b.f.id = 0xBEE;
    printf("bitfield = 0x%08X (gcc 小端應該一樣)\n", (unsigned)b.raw);
    CHECK(b.raw == x);

    uint8_t bytes[4] = {0x12, 0x34, 0x56, 0x78}, out[4];
    CHECK(load_be32(bytes) == 0x12345678u);
    CHECK(load_le32(bytes) == 0x78563412u);
    CHECK(load_be16(bytes + 2) == 0x5678);
    store_be32(out, 0xCAFEBABEu); CHECK(out[0] == 0xCA && out[3] == 0xBE);
    store_le32(out, 0xCAFEBABEu); CHECK(out[0] == 0xBE && out[3] == 0xCA);

    int rev4[4] = {3, 2, 1, 0};                              // 4 位左右顛倒
    CHECK(permute_bits(0x3, rev4, 4) == 0xC);

    if (fails == 0) printf("packet_fields: ALL PASS\n");
    return fails != 0;
}
