/* sort_test.c — 跟 qsort 比對 + benchmark
 * 編譯：gcc -O2 -Wall -Wextra -std=c11 sort.c sort_test.c -o sort_test
 */
#include "test_util.h"
#include "sort.h"

#define N (1u << 20)                 /* 1M 個 uint32  TODO(改這裡) */
static uint32_t orig[N], a[N], ref[N], tmp[N], out[N];

static int cmp_u32(const void *x, const void *y) {
    uint32_t p = *(const uint32_t *)x, q = *(const uint32_t *)y;
    return (p > q) - (p < q);
}

static void fill(size_t n, uint32_t mask) {          /* mask 小 → 很多重複值 */
    for (size_t i = 0; i < n; i++) orig[i] = rnd32() & mask;
}

int main(void) {
    printf("[正確性：各種 n 與資料分布，結果需與 qsort 相同]\n");
    const size_t sizes[] = {0, 1, 2, 3, 31, 32, 33, 100, 1000, 4097, 100000};
    const uint32_t masks[] = {0xFFFFFFFFu, 0xFFu, 0x3u, 0xFFFF0000u};
    int ok_ins = 1, ok_mer = 1, ok_rad = 1;
    for (size_t si = 0; si < sizeof sizes / sizeof *sizes; si++)
        for (size_t mi = 0; mi < 4; mi++) {
            size_t n = sizes[si];
            fill(n, masks[mi]);
            memcpy(ref, orig, n * 4); qsort(ref, n, 4, cmp_u32);
            if (n <= 4097) { memcpy(a, orig, n * 4); insertion_sort_u32(a, n);
                             if (memcmp(a, ref, n * 4)) ok_ins = 0; }
            memcpy(a, orig, n * 4); merge_sort_u32(a, n, tmp); if (memcmp(a, ref, n * 4)) ok_mer = 0;
            memcpy(a, orig, n * 4); radix_sort_u32(a, n, tmp); if (memcmp(a, ref, n * 4)) ok_rad = 0;
        }
    CHECK(ok_ins, "insertion_sort_u32");
    CHECK(ok_mer, "merge_sort_u32");
    CHECK(ok_rad, "radix_sort_u32（含大量重複、高位相同的資料）");

    printf("[合併：模擬 2 塊板子 / 4 個核心各排一段]\n");
    fill(N, 0xFFFFFFFFu);
    memcpy(ref, orig, N * 4); qsort(ref, N, 4, cmp_u32);
    size_t h = N / 3;                                 /* 故意不平均切 */
    memcpy(a, orig, N * 4);
    radix_sort_u32(a, h, tmp); radix_sort_u32(a + h, N - h, tmp);
    merge_two_sorted(a, h, a + h, N - h, out);
    CHECK(!memcmp(out, ref, N * 4), "merge_two_sorted");
    const uint32_t *lists[4]; size_t lens[4], start = 0;
    memcpy(a, orig, N * 4);
    for (int i = 0; i < 4; i++) {
        lens[i] = (i < 3) ? N / 5 * (size_t)(i + 1) / 2 : N - start;
        lists[i] = a + start; radix_sort_u32(a + start, lens[i], tmp); start += lens[i];
    }
    kway_merge(lists, lens, 4, out);
    CHECK(!memcmp(out, ref, N * 4), "kway_merge (k=4)");
    const uint32_t *l20[20]; size_t n20[20];            /* k=20 > KWAY_MAX：舊版會默默丟掉後 4 段 */
    memcpy(a, orig, N * 4);
    for (int i = 0; i < 20; i++) {
        size_t s0 = N / 20 * (size_t)i; n20[i] = (i < 19) ? N / 20 : N - s0;
        l20[i] = a + s0; radix_sort_u32(a + s0, n20[i], tmp);
    }
    kway_merge(l20, n20, 20, out);
    CHECK(!memcmp(out, ref, N * 4), "kway_merge (k=20)");

    printf("[Benchmark：n = %u 個隨機 uint32，取 3 次最快]\n", N);
    uint64_t ns;
    BENCH_MIN(ns, 3, { memcpy(a, orig, N * 4); qsort(a, N, 4, cmp_u32); });
    printf("  qsort (libc)       %8.2f ms\n", ns / 1e6);
    BENCH_MIN(ns, 3, { memcpy(a, orig, N * 4); merge_sort_u32(a, N, tmp); });
    printf("  merge_sort_u32     %8.2f ms\n", ns / 1e6);
    BENCH_MIN(ns, 3, { memcpy(a, orig, N * 4); radix_sort_u32(a, N, tmp); });
    printf("  radix_sort_u32     %8.2f ms\n", ns / 1e6);
    BENCH_MIN(ns, 3, { memcpy(a, orig, N * 4);            /* 兩半分開排 + 合併 */
        radix_sort_u32(a, N / 2, tmp); radix_sort_u32(a + N / 2, N / 2, tmp);
        merge_two_sorted(a, N / 2, a + N / 2, N / 2, out); });
    printf("  2x radix(半) + merge %6.2f ms（單核模擬；真的分兩核/兩板時只算一半+合併）\n", ns / 1e6);
    BENCH_MIN(ns, 3, { memcpy(out, a, N * 4); });
    printf("  （memcpy 本身      %8.2f ms，以上都含這一次複製）\n", ns / 1e6);
    BENCH_MIN(ns, 3, { memcpy(a, orig, 10000 * 4); insertion_sort_u32(a, 10000); });
    printf("  insertion n=10000  %8.2f ms（O(n^2)，大 n 千萬別用）\n", ns / 1e6);
    BENCH_MIN(ns, 3, { memcpy(a, orig, 10000 * 4); radix_sort_u32(a, 10000, tmp); });
    printf("  radix     n=10000  %8.2f ms\n", ns / 1e6);
    return test_end();
}
