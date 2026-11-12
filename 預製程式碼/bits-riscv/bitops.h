// bitops.h — 位元操作工具箱（直接 #include "bitops.h" 就能用）
// 規則：位元編號從 0 開始，bit 0 = 最右邊（最低位 LSB），bit 31 = 最左邊（MSB）
// 全部用 uint32_t（無號 32 位元），避免有號數右移/溢位的怪問題
#ifndef BITOPS_H
#define BITOPS_H
#include <stdint.h>

// ---------- 單一位元 ----------
#define BIT(n)            (1u << (n))              // 第 n 位是 1 的數，BIT(3)=0b1000=0x8
#define SET_BIT(x, n)     ((x) |  BIT(n))          // 把第 n 位設成 1（OR）
#define CLR_BIT(x, n)     ((x) & ~BIT(n))          // 把第 n 位清成 0（AND NOT）
#define TOGGLE_BIT(x, n)  ((x) ^  BIT(n))          // 把第 n 位反轉（XOR）
#define TEST_BIT(x, n)    (((x) >> (n)) & 1u)      // 讀第 n 位，結果 0 或 1
// 用法：x = SET_BIT(x, 5);   if (TEST_BIT(x, 5)) {...}

// ---------- 多位元欄位 [hi:lo]（含 hi 和 lo，寬度 = hi-lo+1） ----------
// MASK(w)：低 w 位全 1。w=32 要特別處理，因為 1u<<32 在 C 是未定義行為！
#define MASK(w)  ((w) >= 32 ? 0xFFFFFFFFu : ((1u << (w)) - 1u))
// 取出 x 的第 hi..lo 位，例：GET_FIELD(0xABCD, 11, 8) = 0xB
#define GET_FIELD(x, hi, lo)    (((x) >> (lo)) & MASK((hi) - (lo) + 1))
// 把 v 放進 x 的第 hi..lo 位（先清空該欄位再 OR 進去），回傳新值
#define SET_FIELD(x, hi, lo, v) \
    (((x) & ~(MASK((hi) - (lo) + 1) << (lo))) | (((uint32_t)(v) & MASK((hi) - (lo) + 1)) << (lo)))
// 兩個 byte 合成 16 位元：COMBINE16(0x12, 0x34) = 0x1234
#define COMBINE16(a, b)  ((((uint32_t)(a) & 0xFF) << 8) | ((uint32_t)(b) & 0xFF))

// ---------- 符號延伸 ----------
// 把「bits 位寬的有號數」變成 32 位元有號數。例：sign_extend(0xFFF, 12) = -1
// 原理：把該數的最高位（符號位）推到 bit31，再「有號右移」回來
static inline int32_t sign_extend(uint32_t v, int bits) {
    int sh = 32 - bits;
    return (int32_t)(v << sh) >> sh;   // gcc 的有號右移是算術右移（補符號位）
}
// 另一種完全可攜的寫法：m = 1u<<(bits-1); return (int32_t)((v ^ m) - m);（v 需先 & MASK(bits)）

// ---------- 數 1 的個數（popcount） ----------
static inline int popcount32(uint32_t x) {       // 可攜版：每次清掉最低的 1
    int c = 0;
    while (x) { x &= x - 1; c++; }               // x&(x-1) 會把最右邊的 1 變 0
    return c;
}
#define POPCOUNT(x) __builtin_popcount(x)        // gcc 內建，RISC-V+Zbb 會變成 cpop 指令

// ---------- 前導 0 / 尾端 0 ----------
// clz：從最高位往下數有幾個 0；ctz：從最低位往上數有幾個 0
// 注意：__builtin_clz(0) / __builtin_ctz(0) 是未定義！所以先判斷 0
static inline int clz32(uint32_t x) { return x ? __builtin_clz(x) : 32; }
static inline int ctz32(uint32_t x) { return x ? __builtin_ctz(x) : 32; }
// 最高的 1 在第幾位（log2 取整）：31 - clz32(x)，例：x=0x10 → 4

// ---------- 位元組順序（endian）互換 ----------
// 0x11223344 → 0x44332211（大端 <-> 小端），RP2350/x86 都是小端（little-endian）
static inline uint32_t bswap32(uint32_t x) {
    return (x >> 24) | ((x >> 8) & 0x0000FF00u) | ((x << 8) & 0x00FF0000u) | (x << 24);
}
static inline uint16_t bswap16(uint16_t x) { return (uint16_t)((x >> 8) | (x << 8)); }
// 也可用 __builtin_bswap32(x)，RISC-V+Zbb 會變成 rev8 指令

// ---------- 旋轉（rotate，移出去的位元從另一邊補回來） ----------
static inline uint32_t rotl32(uint32_t x, int n) { n &= 31; return n ? (x << n) | (x >> (32 - n)) : x; }
static inline uint32_t rotr32(uint32_t x, int n) { n &= 31; return n ? (x >> n) | (x << (32 - n)) : x; }

// ---------- 2 的次方 ----------
static inline int is_pow2(uint32_t x) { return x && !(x & (x - 1)); }   // 只有一個 1
static inline uint32_t round_up_pow2(uint32_t x) {   // 往上取到 2 的次方：5→8, 8→8, 0→0
    if (x == 0) return 0;
    x--;                                              // 先減 1，讓剛好是 2^k 的不會變大
    x |= x >> 1; x |= x >> 2; x |= x >> 4; x |= x >> 8; x |= x >> 16;   // 把最高的 1 往右全部填滿
    return x + 1;
}
// 對齊到 a 的倍數（a 必須是 2 的次方）：ALIGN_UP(13, 4) = 16
#define ALIGN_UP(x, a)   (((x) + ((a) - 1)) & ~((a) - 1))

// ---------- 位元反轉 ----------
// 整個 32 位元左右顛倒：bit0<->bit31。例：0x00000001 → 0x80000000
static inline uint32_t bitrev32(uint32_t x) {
    x = ((x >> 1) & 0x55555555u) | ((x & 0x55555555u) << 1);   // 相鄰 1 位互換
    x = ((x >> 2) & 0x33333333u) | ((x & 0x33333333u) << 2);   // 每 2 位一組互換
    x = ((x >> 4) & 0x0F0F0F0Fu) | ((x & 0x0F0F0F0Fu) << 4);   // 每 4 位一組互換
    return bswap32(x);                                          // 最後 byte 順序顛倒
}
// 反轉「低 n 位」：bitrev_n(0b0011, 4) = 0b1100
static inline uint32_t bitrev_n(uint32_t x, int n) { return bitrev32(x) >> (32 - n); }
// 只反轉每個 byte 內部（= Zbkb 的 brev8）
static inline uint32_t brev8(uint32_t x) { return bswap32(bitrev32(x)); }

// ---------- 小技巧速查 ----------
// x & -x        ：只留最低的 1（0b10110 → 0b00010）
// x & (x-1)     ：清掉最低的 1
// ~x            ：全部反相（NOT）
// a ^ b         ：不同的位為 1；popcount(a ^ b) = 漢明距離
// ~(a ^ b)      ：XNOR，相同的位為 1（二值神經網路 BNN 用）
// (x >> n) & 1  ：第 n 位；x >> n 是除以 2^n（無號數）；x << n 是乘 2^n
// 十六進位 1 位 = 二進位 4 位：0xA = 1010, 0xF = 1111
#endif
