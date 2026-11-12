// asm_test.c — 測試 asm_examples.S：每個組語函式都和「C 參考版」比對
// 只能用 RISC-V 編譯器編（因為要連結 .S），指令見 README.md
// 也示範 C 裡面的 inline asm（asm volatile）
#include <stdio.h>
#include <stdint.h>

// ---- 組語函式的宣告（名字、參數要和 .S 完全對上） ----
uint32_t asm_sum_u32(const uint32_t *a, uint32_t n);
void     asm_memcpy_words(uint32_t *dst, const uint32_t *src, uint32_t n);
uint32_t asm_get_field(uint32_t x, uint32_t lo, uint32_t w);
uint32_t asm_popcount_array_base(const uint32_t *a, uint32_t n);
uint32_t asm_popcount_array_fast(const uint32_t *a, uint32_t n);
int32_t  asm_bnn_dot(const uint32_t *w, const uint32_t *x, uint32_t n);
void     asm_apply(uint32_t (*f)(uint32_t), uint32_t *a, uint32_t n);

// ---- C 參考版（標準答案） ----
static uint32_t c_sum(const uint32_t *a, uint32_t n) { uint32_t s = 0; for (uint32_t i = 0; i < n; i++) s += a[i]; return s; }
static int c_pop(uint32_t x) { int c = 0; while (x) { x &= x - 1; c++; } return c; }
static uint32_t c_pop_arr(const uint32_t *a, uint32_t n) { uint32_t s = 0; for (uint32_t i = 0; i < n; i++) s += c_pop(a[i]); return s; }
static int32_t c_bnn(const uint32_t *w, const uint32_t *x, uint32_t n) {
    int32_t m = 0; for (uint32_t i = 0; i < n; i++) m += c_pop(~(w[i] ^ x[i]));
    return 2 * m - 32 * (int32_t)n;
}
static uint32_t times3(uint32_t v) { return v * 3; }

// ---- inline asm 範例 ----
// 格式：asm volatile("指令" : 輸出 : 輸入 : 會被弄髒的東西);
//   "=r"(out) 輸出到某暫存器；"r"(in) 輸入放某暫存器；%0 %1 %2 依序對應
static uint32_t inline_add(uint32_t a, uint32_t b) {
    uint32_t r;
    asm volatile("add %0, %1, %2" : "=r"(r) : "r"(a), "r"(b));
    return r;
}
static uint32_t inline_popcount(uint32_t x) {
#ifdef __riscv_zbb
    uint32_t r;
    asm volatile("cpop %0, %1" : "=r"(r) : "r"(x));   // Hazard3 可用
    return r;
#else
    return (uint32_t)c_pop(x);
#endif
}

static int fails = 0;
#define CHECK(got, exp) do { long g_ = (long)(got), e_ = (long)(exp); \
    if (g_ != e_) { printf("FAIL line %d: got %ld exp %ld\n", __LINE__, g_, e_); fails++; } } while (0)

int main(void) {
    uint32_t a[] = {1, 2, 3, 0xFFFFFFFFu, 0x80000000u, 0x12345678u, 0, 7};
    uint32_t b[] = {0xFFFFFFFFu, 0, 0xAAAAAAAAu, 0x0F0F0F0Fu, 0x80000001u, 0x12345678u, 5, 9};
    uint32_t n = sizeof a / sizeof a[0];

    CHECK(asm_sum_u32(a, n), c_sum(a, n));
    CHECK(asm_sum_u32(a, 0), 0);

    uint32_t d[8] = {0};
    asm_memcpy_words(d, a, n);
    for (uint32_t i = 0; i < n; i++) CHECK(d[i], a[i]);

    CHECK(asm_get_field(0xABCD1234u, 8, 8), 0x12);
    CHECK(asm_get_field(0xABCD1234u, 28, 4), 0xA);

    CHECK(asm_popcount_array_base(a, n), c_pop_arr(a, n));
    CHECK(asm_popcount_array_fast(a, n), c_pop_arr(a, n));
    CHECK(asm_popcount_array_fast(b, n), c_pop_arr(b, n));

    CHECK(asm_bnn_dot(a, b, n), c_bnn(a, b, n));
    CHECK(asm_bnn_dot(a, a, n), 32 * (int32_t)n);           // 自己跟自己：全部相同
    uint32_t na[8]; for (uint32_t i = 0; i < n; i++) na[i] = ~a[i];
    CHECK(asm_bnn_dot(a, na, n), -32 * (int32_t)n);         // 完全相反

    uint32_t e[3] = {1, 10, 100};
    asm_apply(times3, e, 3);
    CHECK(e[0], 3); CHECK(e[1], 30); CHECK(e[2], 300);

    CHECK(inline_add(40, 2), 42);
    CHECK(inline_popcount(0xF0F0u), 8);

#ifdef __riscv_zbb
    printf("(Zbb 版本：使用 cpop/xnor)\n");
#else
    printf("(基本 ISA 版本：迴圈 popcount)\n");
#endif
    if (fails == 0) printf("asm_test: ALL PASS\n");
    return fails != 0;
}
