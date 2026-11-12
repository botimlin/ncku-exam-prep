/* bnn.c — 實作（無 malloc、無浮點運算於推論路徑；bnn_fold_bn 才用到 float）*/
#include "bnn.h"

void bnn_pack(const int8_t *v, int n, uint32_t *out) {
    for (int k = 0; k < BNN_WORDS(n); k++) out[k] = 0;      /* 先清 0，尾巴自然是 0 */
    for (int i = 0; i < n; i++)
        if (v[i] > 0) out[i >> 5] |= 1u << (i & 31);        /* i>>5 = i/32, i&31 = i%32 */
}

int bnn_get_bit(const uint32_t *bits, int i) {
    return (int)((bits[i >> 5] >> (i & 31)) & 1u);
}

int32_t bnn_dot(const uint32_t *a, const uint32_t *w, int n) {
    if (n <= 0) return 0;
    int words = BNN_WORDS(n), match = 0;
    for (int k = 0; k < words - 1; k++)                     /* 完整的 word */
        match += bnn_popcount(~(a[k] ^ w[k]));              /* XNOR 後數 1 = 相同的個數 */
    int r = n & 31;                                         /* 最後一個 word 有效 bit 數 */
    uint32_t mask = r ? ((1u << r) - 1u) : 0xFFFFFFFFu;     /* ★ 尾巴一定要 mask！*/
    match += bnn_popcount(~(a[words - 1] ^ w[words - 1]) & mask);
    return 2 * match - n;                                   /* 相同 - 不同 */
}

void bnn_dense_sign(const bnn_layer_t *L, const uint32_t *in, uint32_t *out_bits) {
    const int stride = BNN_WORDS(L->n_in);
    for (int k = 0; k < BNN_WORDS(L->n_out); k++) out_bits[k] = 0;
    for (int j = 0; j < L->n_out; j++) {
        int32_t d = bnn_dot(in, L->W + j * stride, L->n_in);
        if (L->flip && L->flip[j]) d = -d;                  /* gamma < 0 的神經元 */
        if (d >= L->thr[j]) out_bits[j >> 5] |= 1u << (j & 31);
    }
}

void bnn_dense_score(const bnn_layer_t *L, const uint32_t *in, int32_t *score) {
    const int stride = BNN_WORDS(L->n_in);
    for (int j = 0; j < L->n_out; j++)
        score[j] = bnn_dot(in, L->W + j * stride, L->n_in) + (L->thr ? L->thr[j] : 0);
}

int bnn_argmax(const int32_t *s, int n) {
    int best = 0;
    for (int j = 1; j < n; j++) if (s[j] > s[best]) best = j;   /* 平手取編號小的 */
    return best;
}

/* 不用 <math.h> 的 ceil（MCU 上少連結一個函式庫）*/
static int32_t ceil_f(float t) {
    int32_t i = (int32_t)t;                 /* 往 0 截斷 */
    return ((float)i < t) ? i + 1 : i;
}

void bnn_fold_bn(float gamma, float beta, float mean, float std, float bias,
                 int32_t *thr, uint8_t *flip) {
    if (gamma == 0.0f) {                    /* y = beta 恆定：永遠 +1 或永遠 -1 */
        *flip = 0;
        *thr = (beta >= 0.0f) ? INT32_MIN / 2 : INT32_MAX / 2;
        return;
    }
    float t = mean - bias - beta * std / gamma;
    if (gamma > 0.0f) { *flip = 0; *thr = ceil_f(t);  }
    else              { *flip = 1; *thr = ceil_f(-t); }
}
