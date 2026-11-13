/* bnn_test.c — ① 跟「逐元素 ±1 乘加 + 浮點 BN」的笨方法比對 ② 2 層小網路範例 ③ 測速
 * 編譯：gcc -O2 -Wall -Wextra -std=c11 bnn.c bnn_test.c -o bnn_test
 */
#include "test_util.h"
#include "bnn.h"

#define MAXN 1024
static int8_t rnd_pm1(void) { return (rnd32() & 1) ? 1 : -1; }

/* ---------- ② 範例網路：40 bit 輸入 → 4 個隱藏神經元 → 4 類 ----------
 * 隱藏神經元 c 的權重 = 原型 P_c；BN 參數 (gamma=1,beta=0,mean=20,std=1) → 門檻 20
 *   dot = 40 - 2*漢明距離 ≥ 20 ⇔ 跟 P_c 差 ≤ 10 bit 才亮
 * 輸出層第 c 列只有 bit c = 1 → 只有 h_c 亮時第 c 類分數最高
 * TODO(改這裡) 換成題目給的權重/門檻：把 W/thr 陣列換掉、改 N_IN/N_HID/N_OUT 即可 */
#define N_IN  40
#define N_HID 4
#define N_OUT 4
static const uint32_t W1[N_HID][BNN_WORDS(N_IN)] = {
    {0x892f902bu, 0x18u}, {0x5d9dc9f8u, 0x95u}, {0x0ed90475u, 0xe8u}, {0x81e74ef5u, 0x36u} };
static const uint32_t W2[N_OUT][BNN_WORDS(N_HID)] = { {0x1u}, {0x2u}, {0x4u}, {0x8u} };
static int32_t thr1[N_HID];
static uint8_t flip1[N_HID];

static int predict(const uint32_t *x) {
    const bnn_layer_t L1 = { N_IN, N_HID, &W1[0][0], thr1, flip1 };
    const bnn_layer_t L2 = { N_HID, N_OUT, &W2[0][0], NULL, NULL };
    uint32_t h[BNN_WORDS(N_HID)];
    int32_t score[N_OUT];
    bnn_dense_sign(&L1, x, h);
    bnn_dense_score(&L2, h, score);
    return bnn_argmax(score, N_OUT);
}

int main(void) {
    static int8_t a[MAXN], w[MAXN];
    static uint32_t pa[BNN_WORDS(MAXN)], pw[BNN_WORDS(MAXN)];

    printf("[① bnn_dot 與笨方法一致（含 n 不是 32 倍數的尾巴）]\n");
    const int ns[] = {1, 5, 31, 32, 33, 40, 63, 64, 65, 100, 784, 1024};
    int ok = 1;
    for (size_t t = 0; t < sizeof ns / sizeof *ns; t++)
        for (int rep = 0; rep < 50; rep++) {
            int n = ns[t], ref = 0;
            for (int i = 0; i < n; i++) { a[i] = rnd_pm1(); w[i] = rnd_pm1(); ref += a[i] * w[i]; }
            bnn_pack(a, n, pa); bnn_pack(w, n, pw);
            if (n & 31) pw[BNN_WORDS(n) - 1] |= ~0u << (n & 31);   /* 尾巴故意塞垃圾 bit */
            if (bnn_dot(pa, pw, n) != ref) ok = 0;
            for (int i = 0; i < n; i++) if (bnn_get_bit(pa, i) != (a[i] > 0)) ok = 0;
        }
    CHECK(ok, "bnn_dot / bnn_pack 600 組");

    printf("[① BN 折成整數門檻 == 浮點 BN 再取 sign（gamma 有正有負）]\n");
    ok = 1;
    for (int rep = 0; rep < 20000; rep++) {
        int n = 1 + (int)(rnd32() % 200), ref = 0;
        for (int i = 0; i < n; i++) { a[i] = rnd_pm1(); w[i] = rnd_pm1(); ref += a[i] * w[i]; }
        float gamma = ((int)(rnd32() % 2001) - 1000) / 337.0f;   /* 含 0 與負數 */
        float beta  = ((int)(rnd32() % 2001) - 1000) / 97.0f;
        float mean  = ((int)(rnd32() % 2001) - 1000) / 13.0f, sd = 0.1f + (rnd32() % 100) / 7.0f;
        float bias  = ((int)(rnd32() % 201) - 100) / 3.0f;
        int want = gamma * ((float)ref + bias - mean) / sd + beta >= 0.0f;
        int32_t thr; uint8_t flip;
        bnn_fold_bn(gamma, beta, mean, sd, bias, &thr, &flip);
        bnn_pack(a, n, pa); bnn_pack(w, n, pw);
        const bnn_layer_t L = { n, 1, pw, &thr, &flip };
        uint32_t out;
        bnn_dense_sign(&L, pa, &out);
        if ((int)(out & 1) != want) ok = 0;
    }
    CHECK(ok, "20000 組隨機 BN 參數");

    printf("[② 範例 2 層網路：原型加 0~3 bit 雜訊，要分對]\n");
    for (int j = 0; j < N_HID; j++) bnn_fold_bn(1.0f, 0.0f, 20.0f, 1.0f, 0.0f, &thr1[j], &flip1[j]);
    CHECK(thr1[0] == 20 && flip1[0] == 0, "fold_bn(1,0,20,1,0) → thr=20");
    ok = 1;
    for (int rep = 0; rep < 1000; rep++) {
        int c = (int)(rnd32() % N_OUT);
        uint32_t x[BNN_WORDS(N_IN)]; memcpy(x, W1[c], sizeof x);   /* 大小跟著 N_IN 變（舊版寫死 2 個 word）*/
        for (int f = (int)(rnd32() % 4); f > 0; f--) { int i = (int)(rnd32() % N_IN); x[i >> 5] ^= 1u << (i & 31); }
        if (predict(x) != c) ok = 0;
    }
    CHECK(ok, "1000 個加雜訊樣本全部分對");

    printf("[③ Benchmark：784 輸入 x 256 神經元 dense，取 5 次最快]\n");
    static uint32_t Wb[256 * BNN_WORDS(784)], hb[8]; static int32_t tb[256];
    for (int i = 0; i < 256 * BNN_WORDS(784); i++) Wb[i] = rnd32();
    for (int i = 0; i < 25; i++) pa[i] = rnd32();
    const bnn_layer_t LB = { 784, 256, Wb, tb, NULL };
    uint64_t ns_best;
    BENCH_MIN(ns_best, 5, for (int k = 0; k < 1000; k++) { bnn_dense_sign(&LB, pa, hb); SINK(hb[0]); });
    printf("  每層 %.2f us（%.0f M 個 binary MAC / 秒）\n", ns_best / 1e3 / 1000,
           784.0 * 256 * 1000 / (ns_best / 1e3));
    return test_end();
}
