/* sort.h — uint32 排序工具箱（不用 malloc：暫存區由呼叫者提供）
 *
 * 選哪個？
 *   n < ~32              → insertion_sort_u32（最簡單，小陣列最快）
 *   一般 / 需要穩定排序  → merge_sort_u32（O(n log n)，需要 n 個 tmp）
 *   大量 uint32 整數     → radix_sort_u32（O(n)，4 趟，通常最快，需要 n 個 tmp）
 *   兩塊板子/兩個核心各排一半 → merge_two_sorted 合併
 *   k 塊板子各排一份    → kway_merge
 *
 * 範例：
 *   static uint32_t a[N], tmp[N];      // MCU 上用 static，不要放 stack
 *   radix_sort_u32(a, N, tmp);
 *
 * 有號 int32？ 排序前每個元素 ^= 0x80000000u，排完再 ^= 回去（把負數翻到前面）。
 * 要遞減？ 排完再反轉陣列，或排序前每個元素取 ~x，排完再取 ~ 回去。
 */
#ifndef SORT_H
#define SORT_H
#include <stdint.h>
#include <stddef.h>

void insertion_sort_u32(uint32_t *a, size_t n);
void merge_sort_u32(uint32_t *a, size_t n, uint32_t *tmp);   /* tmp 至少 n 個 */
void radix_sort_u32(uint32_t *a, size_t n, uint32_t *tmp);   /* tmp 至少 n 個 */

/* 把已排序的 a[na]、b[nb] 合併到 out[na+nb]（out 不可以跟 a/b 重疊）*/
void merge_two_sorted(const uint32_t *a, size_t na,
                      const uint32_t *b, size_t nb, uint32_t *out);

/* k 個已排序陣列合併到 out。k 不限（舊版上限 KWAY_MAX 已拿掉）。O(n*k)，k 小（≤8）時最划算 */
#define KWAY_MAX 16      /* 只是建議值：k 很大時，用 merge_two_sorted 兩兩合併（O(n log k)）通常比較快 */
void kway_merge(const uint32_t *const lists[], const size_t lens[], int k, uint32_t *out);

#endif
