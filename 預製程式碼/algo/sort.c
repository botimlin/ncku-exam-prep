/* sort.c — 實作 */
#include "sort.h"

static void copy_u32(uint32_t *d, const uint32_t *s, size_t n) { while (n--) *d++ = *s++; }

#define RUN 32   /* merge sort 先用 insertion sort 排好每 32 個  TODO(改這裡) 16~64 都可 */

void insertion_sort_u32(uint32_t *a, size_t n) {
    for (size_t i = 1; i < n; i++) {
        uint32_t x = a[i];
        size_t j = i;
        while (j > 0 && a[j - 1] > x) { a[j] = a[j - 1]; j--; }   /* 比 x 大的往右挪 */
        a[j] = x;
    }
}

/* 合併 src[lo..mid) 與 src[mid..hi) 到 dst[lo..hi)。用 <= 保持穩定 */
static void merge_run(const uint32_t *src, uint32_t *dst, size_t lo, size_t mid, size_t hi) {
    size_t i = lo, j = mid, k = lo;
    while (i < mid && j < hi) dst[k++] = (src[i] <= src[j]) ? src[i++] : src[j++];
    while (i < mid) dst[k++] = src[i++];
    while (j < hi)  dst[k++] = src[j++];
}

/* 迭代式（bottom-up）merge sort：不用遞迴 → MCU 不怕 stack 爆 */
void merge_sort_u32(uint32_t *a, size_t n, uint32_t *tmp) {
    for (size_t lo = 0; lo < n; lo += RUN)                  /* 第一步：每 RUN 個一組排好 */
        insertion_sort_u32(a + lo, (n - lo < RUN) ? n - lo : RUN);
    uint32_t *src = a, *dst = tmp;
    for (size_t w = RUN; w < n; w *= 2) {                   /* 寬度 32, 64, 128 ... */
        for (size_t lo = 0; lo < n; lo += 2 * w) {
            size_t mid = (lo + w < n) ? lo + w : n;
            size_t hi  = (lo + 2 * w < n) ? lo + 2 * w : n;
            merge_run(src, dst, lo, mid, hi);
        }
        uint32_t *t = src; src = dst; dst = t;              /* 交換角色（ping-pong）*/
    }
    if (src != a) copy_u32(a, src, n);            /* 結果在 tmp 就抄回來 */
}

/* LSD radix sort：每次看 8 bits（一個 byte），從最低 byte 到最高 byte，共 4 趟。
 * 每趟：① 數每個桶有幾個 ② 前綴和 = 每個桶的起點 ③ 依序搬過去（穩定）
 * 4 趟是偶數 → 最後結果剛好回到 a。 */
void radix_sort_u32(uint32_t *a, size_t n, uint32_t *tmp) {
    uint32_t *src = a, *dst = tmp;
    if (n < 2) return;
    for (int shift = 0; shift < 32; shift += 8) {
        size_t cnt[256] = {0};
        for (size_t i = 0; i < n; i++) cnt[(src[i] >> shift) & 0xFF]++;
        if (cnt[(src[0] >> shift) & 0xFF] == n) continue;     /* 這個 byte 全部一樣 → 跳過 */
        size_t sum = 0;
        for (int b = 0; b < 256; b++) { size_t c = cnt[b]; cnt[b] = sum; sum += c; }
        for (size_t i = 0; i < n; i++) dst[cnt[(src[i] >> shift) & 0xFF]++] = src[i];
        uint32_t *t = src; src = dst; dst = t;
    }
    if (src != a) copy_u32(a, src, n);            /* 有跳過某趟時可能停在 tmp */
}

void merge_two_sorted(const uint32_t *a, size_t na,
                      const uint32_t *b, size_t nb, uint32_t *out) {
    size_t i = 0, j = 0, k = 0;
    while (i < na && j < nb) out[k++] = (a[i] <= b[j]) ? a[i++] : b[j++];
    while (i < na) out[k++] = a[i++];
    while (j < nb) out[k++] = b[j++];
}

void kway_merge(const uint32_t *const lists[], const size_t lens[], int k, uint32_t *out) {
    size_t pos[k > 0 ? k : 1];                              /* 每個序列讀到第幾個；k 沒有上限 */
    for (int i = 0; i < k; i++) pos[i] = 0;
    for (;;) {
        int best = -1;
        for (int i = 0; i < k; i++)                         /* 找 k 個頭裡最小的 */
            if (pos[i] < lens[i] && (best < 0 || lists[i][pos[i]] < lists[best][pos[best]]))
                best = i;
        if (best < 0) break;                                /* 全部用完 */
        *out++ = lists[best][pos[best]++];
    }
}
