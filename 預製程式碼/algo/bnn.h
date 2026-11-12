/* bnn.h — 二值化神經網路（BNN / eBNN）基本零件
 *
 * ■ eBNN 是什麼？（Embedded Binarized Neural Networks, McDanel, Teerapittayanon, Kung, 2017）
 *   給「只有幾 KB RAM 的 MCU」跑的神經網路：
 *   1. 權重、激活值都只有 ±1 → 1 個 bit 存一個（+1 存成 1，-1 存成 0），32 個塞進一個 uint32
 *   2. 乘法變 XNOR：(+1)(+1)=+1、(-1)(-1)=+1、不同號=-1 → 「兩 bit 相同」就是 +1
 *      所以 dot(a,w) = (#相同) - (#不同) = 2*popcount(~(a^w)) - n
 *   3. 把 Conv/Dense → (Pool) → BatchNorm → Sign 融合成一步：BN+Sign 只是「跟門檻比大小」，
 *      所以每個神經元只要存一個整數門檻 thr，不用存浮點、也不用存中間的浮點特徵圖。
 *      （eBNN 一次算一個輸出像素就立刻二值化，省下大量 RAM。binary conv 就是對每個
 *       patch 做下面的 bnn_dot；max-pool 對整數 dot 取 max 後再比門檻。）
 *   4. 最後一層不二值化：輸出整數分數，取 argmax 當分類結果。
 *
 * ■ 位元排列：第 i 個元素 → 第 i/32 個 word 的第 i%32 個 bit（LSB 起算）
 *   長度 n 不是 32 的倍數時，最後一個 word 的多餘 bit 一律被 mask 掉（不影響結果）。
 *
 * ■ 浮點 BN 參數 → 整數門檻（離線算一次，或開機算）：
 *   y = gamma * (dot + bias - mean) / std + beta,   std = sqrt(var + eps)
 *   輸出 +1 ⇔ y >= 0
 *     gamma > 0：dot >= t,  t = mean - bias - beta*std/gamma  → thr = ceil(t), flip = 0
 *     gamma < 0：dot <= t  ⇔ -dot >= -t                       → thr = ceil(-t), flip = 1
 *   推論時：d = flip ? -dot : dot;  bit = (d >= thr)
 *   bnn_fold_bn() 就是在做這件事。
 *
 * ■ 第一層輸入：若輸入是 0/1 像素，bnn_pack 會把 0 當 -1、1 當 +1。
 *   若輸入是 8-bit 灰階，要先自己二值化（例如 >=128 → 1），或第一層用一般整數乘加。
 */
#ifndef BNN_H
#define BNN_H
#include <stdint.h>

#define BNN_WORDS(n) (((n) + 31) / 32)   /* n 個 bit 需要幾個 uint32 */

static inline int bnn_popcount(uint32_t x) {
#if defined(__GNUC__) && !defined(BNN_SWAR_POPCOUNT)
    return __builtin_popcount(x);   /* RISC-V Zbb(-march=..._zbb) → 1 條 cpop 指令 */
#else
    x = x - ((x >> 1) & 0x55555555u);                 /* SWAR：純 C 版 */
    x = (x & 0x33333333u) + ((x >> 2) & 0x33333333u);
    return (int)((((x + (x >> 4)) & 0x0F0F0F0Fu) * 0x01010101u) >> 24);
#endif
}

/* 一層 binary dense（全連接）層。W 是 n_out 列，每列 BNN_WORDS(n_in) 個 word */
typedef struct {
    int n_in, n_out;
    const uint32_t *W;      /* 權重 bits */
    const int32_t  *thr;    /* 每個輸出的門檻（隱藏層用）/ 偏差 bias（最後一層用，可 NULL）*/
    const uint8_t  *flip;   /* 每個輸出是否反向（gamma<0），可 NULL = 全 0 */
} bnn_layer_t;

/* v[i] > 0 → 1，否則 0。out 要有 BNN_WORDS(n) 個 word */
void    bnn_pack(const int8_t *v, int n, uint32_t *out);
int     bnn_get_bit(const uint32_t *bits, int i);
/* ±1 向量內積：結果範圍 -n..n */
int32_t bnn_dot(const uint32_t *a, const uint32_t *w, int n);
/* 隱藏層：dot → 跟門檻比 → 輸出 bits（out_bits 要有 BNN_WORDS(n_out) 個 word）*/
void    bnn_dense_sign(const bnn_layer_t *L, const uint32_t *in, uint32_t *out_bits);
/* 最後一層：score[j] = dot_j + thr[j]（thr 當 bias；NULL 就只有 dot）*/
void    bnn_dense_score(const bnn_layer_t *L, const uint32_t *in, int32_t *score);
int     bnn_argmax(const int32_t *s, int n);
/* 浮點 BN → 整數門檻（見上面公式）*/
void    bnn_fold_bn(float gamma, float beta, float mean, float std, float bias,
                    int32_t *thr, uint8_t *flip);

#endif
