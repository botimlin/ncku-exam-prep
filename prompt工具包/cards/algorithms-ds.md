# 貼上卡：演算法與資料結構（效能優化）
> 用法（照 `../../考場SOP.md`）：模型寫【要卡】編號時，到 `../編號卡/` Ctrl-F 那個編號複製這張卡，包在 `<<<資料 開始>>>`…`<<<資料 結束>>>` 裡、最後一行寫「繼續」再貼。本檔編號：L10（參考卡 演算法）。每張 ≤ 1200 字元。
> 來源：full/domain/algorithms-ds.md、lite/domain/algorithms-ds.md（詳細版）｜最後更新 2026-11

---

【參考卡｜演算法 1/8｜慢寫法 → 演算法替代】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
情境：C11 程式要變快（Linux 主機或 RP2350 MCU）。先換演算法，收益遠大於組語微調。
| 慢寫法 | 替代 | 注意 |
|---|---|---|
| 雙層迴圈找配對 / 是否存在 O(n²) | hash set、排序+lower_bound、排序+雙指標 | 排序會改順序（必要時排索引） |
| 每個查詢線性搜尋 | 排序一次+lower_bound；key 範圍小用直接索引表 | 找不到的回傳值要和原版一樣 |
| 每次重算視窗和 | running sum：加新減舊 | 用 int64；浮點會累積誤差 |
| 每次重算視窗 min/max | monotonic deque O(n) | tie 規則 >= 或 > |
| 多次區間和 | prefix sum `P[r]-P[l]`，P 長 n+1 | 型別加寬 |
| 多次區間加、最後才讀 | difference array | 交錯查詢改 Fenwick |
| `i = (i+1) % N` | N 取 2^k 用 `& (N-1)`，或 `if (++i == N) i = 0;` | 加 _Static_assert |
| 全排序只取前 k / 中位數 | size-k heap O(n log k) / quickselect O(n) 平均 | quickselect 會打亂陣列 |
| 小整數鍵比較排序 | counting / radix O(n+K) | 穩定性 |
| 逐 bit 算 CRC | 256 項查表 | 參數不能錯 |
| bool flags[N] 逐一檢查 | bitset + ctz | 走訪順序由低到高 |
| pow 迴圈乘 n 次 | 快速冪，中間值 uint64_t | — |
| sqrt/float 比距離 | 比平方距離（int64_t） | 溢位 |
| 鏈結串列 | 陣列+索引；固定 pool | — |
| 迴圈條件 strlen(s)、反覆 strcat | 先算長度 / 記住尾端 | — |
1 秒可行 n（⚠️估計）：主機 O(n) 1e8、O(n log n) 1e7、O(n²) 1e4；RP2350 @150MHz 約十分之一。

---

【參考卡｜演算法 2/8｜Ring buffer 與雙緩衝（C，已測試）】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
單執行緒 / 單一 ISR 版。索引持續遞增、取用時 mask；可用滿 N 格。
```c
#include <stdint.h>
#include <stdbool.h>
#define RB_N 256u                         // 必須是 2 的冪
_Static_assert((RB_N & (RB_N - 1)) == 0, "RB_N must be power of 2");
typedef struct { uint8_t buf[RB_N]; uint32_t head, tail; } rb_t;   // head 寫、tail 讀
static inline uint32_t rb_count(const rb_t *r) { return r->head - r->tail; }  // 無號減法，溢位仍正確
static inline bool rb_put(rb_t *r, uint8_t v) {
    if (r->head - r->tail == RB_N) return false;      // 滿
    r->buf[r->head & (RB_N - 1)] = v; r->head++; return true;
}
static inline bool rb_get(rb_t *r, uint8_t *v) {
    if (r->head == r->tail) return false;             // 空
    *v = r->buf[r->tail & (RB_N - 1)]; r->tail++; return true;
}
```
- 另一種設計：索引留在 0..N-1、空一格區分滿/空（容量 N-1）。改寫舊程式要保持容量與「滿時」行為（丟新 / 覆蓋舊 / 回傳失敗）。
- N 不是 2 的冪：`if (++i == N) i = 0;` 比 % 快。
- 寫端讀端在 ISR 與主迴圈、或兩個核心：要 atomic + memory order（SPSC lock-free）；RP2350 跨核可用 pico-sdk 的 queue_t。
- 批次取出：連續區段 `min(count, N - (tail & (N-1)))` 用 memcpy。
雙緩衝：DMA/ISR 填 fill，CPU 處理 work，兩者都完成後「交換指標」不是 memcpy：`int16_t *t = fill; fill = work; work = t;`。處理時間必須 < 填滿時間，否則三緩衝或加大區塊。

---

【參考卡｜演算法 3/8｜CRC 參數表與除錯】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
來源 reveng CRC catalogue。check = 對 ASCII "123456789" 的結果。ref = refin/refout。
| 名稱（別名） | width | poly | init | ref | xorout | check |
|---|---|---|---|---|---|---|
| CRC-32/ISO-HDLC（CRC-32、zlib、Ethernet） | 32 | 04C11DB7 | FFFFFFFF | T | FFFFFFFF | CBF43926 |
| CRC-32/ISCSI（CRC-32C） | 32 | 1EDC6F41 | FFFFFFFF | T | FFFFFFFF | E3069283 |
| CRC-32/MPEG-2 | 32 | 04C11DB7 | FFFFFFFF | F | 0 | 0376E6E7 |
| CRC-16/IBM-3740（= CCITT-FALSE） | 16 | 1021 | FFFF | F | 0 | 29B1 |
| CRC-16/XMODEM | 16 | 1021 | 0 | F | 0 | 31C3 |
| CRC-16/KERMIT（CRC-CCITT-TRUE） | 16 | 1021 | 0 | T | 0 | 2189 |
| CRC-16/MODBUS | 16 | 8005 | FFFF | T | 0 | 4B37 |
| CRC-16/ARC | 16 | 8005 | 0 | T | 0 | BB3D |
| CRC-8/SMBUS | 8 | 07 | 0 | F | 0 | F4 |
| CRC-8/MAXIM-DOW（1-Wire） | 8 | 31 | 0 | T | 0 | A1 |
- 「CRC-CCITT」名稱混亂：常被誤指 CCITT-FALSE；題目只寫 CRC-CCITT 時一定用 check value 對答案。
- 反射（ref=T）實作 = 右移 + 反射多項式：04C11DB7→EDB88320、8005→A001、31→8C。
- Python 對拍：`zlib.crc32(b"123456789") == 0xCBF43926`；`binascii.crc_hqx(d, 0xFFFF)` = CCITT-FALSE；`crc_hqx(d, 0)` = XMODEM。
- 結果不對依序查：(1) init (2) 是否反射（右移/左移、多項式反射值）(3) xorout (4) 輸出 byte 順序 (5) 範圍是否含 header/長度 (6) 是否把 CRC 本身算進去。

---

【參考卡｜演算法 4/8｜CRC-32/ISO-HDLC 程式碼（逐位元與查表，已測試）】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
參數：poly 04C11DB7（反射 EDB88320）、init FFFFFFFF、反射、xorout FFFFFFFF、check("123456789") = 0xCBF43926。
```c
// (a) 逐 bit（無表；每 byte 8 次迴圈）
uint32_t crc32_bitwise(const uint8_t *p, size_t n) {
    uint32_t crc = 0xFFFFFFFFu;
    while (n--) {
        crc ^= *p++;
        for (int k = 0; k < 8; k++)
            crc = (crc >> 1) ^ (0xEDB88320u & -(crc & 1u));
    }
    return crc ^ 0xFFFFFFFFu;
}
// (b) 256 項查表（1 KB；每 byte 1 次查表）
static uint32_t crc32_tab[256];
void crc32_init(void) {
    for (uint32_t i = 0; i < 256; i++) {
        uint32_t c = i;
        for (int k = 0; k < 8; k++) c = (c & 1u) ? (c >> 1) ^ 0xEDB88320u : (c >> 1);
        crc32_tab[i] = c;
    }
}
// 可分段：crc = crc32_update(0, p1, n1); crc = crc32_update(crc, p2, n2);（同 zlib.crc32）
uint32_t crc32_update(uint32_t crc, const uint8_t *p, size_t n) {
    crc = ~crc;
    while (n--) crc = (crc >> 8) ^ crc32_tab[(crc ^ *p++) & 0xFFu];
    return ~crc;
}
```
- 選擇：bitwise（flash 極小）→ 256 表（預設）→ slicing-by-4（4 KB 表，主機大資料；MCU 表要放 SRAM）。
- 建表放在計時區外，但先確認計分是否包含初始化。

---

【參考卡｜演算法 5/8｜CRC-16/CCITT-FALSE、MODBUS、CRC-8/SMBUS 程式碼（已測試）】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
```c
uint16_t crc16_ccitt_false(const uint8_t *p, size_t n) { // check 0x29B1
    uint16_t crc = 0xFFFF;
    while (n--) {
        crc ^= (uint16_t)(*p++) << 8; // 非反射：byte 放高位
        for (int k = 0; k < 8; k++)
            crc = (crc & 0x8000) ? (uint16_t)((crc << 1) ^ 0x1021) : (uint16_t)(crc << 1);
    }
    return crc;
}
// CRC-16/XMODEM：同一程式，init 改 0x0000（check 0x31C3）
// 查表版：tab[i] = 上式對單一 byte i（init 0）的結果
//   crc = (uint16_t)((crc << 8) ^ tab[((crc >> 8) ^ *p++) & 0xFF]);

uint16_t crc16_modbus(const uint8_t *p, size_t n) { // check 0x4B37
    uint16_t crc = 0xFFFF;
    while (n--) { crc ^= *p++; for (int k = 0; k < 8; k++) crc = (crc & 1) ? (crc >> 1) ^ 0xA001 : (crc >> 1); }
    return crc; // Modbus RTU 低位元組先送
}

uint8_t crc8_smbus(const uint8_t *p, size_t n) { // check 0xF4
    uint8_t crc = 0x00;
    while (n--) {
        crc ^= *p++;
        for (int k = 0; k < 8; k++)
            crc = (crc & 0x80) ? (uint8_t)((crc << 1) ^ 0x07) : (uint8_t)(crc << 1);
    }
    return crc;
}
```
Python 對拍：`binascii.crc_hqx(b"123456789", 0xFFFF) == 0x29B1`。

---

【參考卡｜演算法 6/8｜Hash table（open addressing，已測試）】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
```c
#define HT_BITS 10
#define HT_SIZE (1u << HT_BITS) // 1024 槽；最多放約 0.7*HT_SIZE 筆
#define EMPTY_KEY 0xFFFFFFFFu // 保留一個不會出現的 key 當「空」
typedef struct { uint32_t key; int32_t val; } slot_t;
static slot_t ht[HT_SIZE];
static void ht_init(void) { for (uint32_t i = 0; i < HT_SIZE; i++) ht[i].key = EMPTY_KEY; }
// Fibonacci hashing：乘 2654435769 (0x9E3779B9)，取「高」HT_BITS 位
static inline uint32_t hash32(uint32_t k) { return (k * 2654435769u) >> (32 - HT_BITS); }
static int32_t *ht_get_or_insert(uint32_t key, bool *inserted) {
    uint32_t i = hash32(key);
    for (uint32_t probe = 0; probe < HT_SIZE; probe++) {
        if (ht[i].key == key)       { *inserted = false; return &ht[i].val; }
        if (ht[i].key == EMPTY_KEY) { ht[i].key = key; ht[i].val = 0; *inserted = true; return &ht[i].val; }
        i = (i + 1) & (HT_SIZE - 1);
    }
    return NULL; // 表滿
}
```
- ht_find 同迴圈：key 相等回傳；遇 EMPTY_KEY 回傳 NULL。
- 負載因子 α ≤ 0.7（α=0.9 時失敗查找約 50 次探測）。
- 取高位：取低位 `k & mask` 對有規律的 key（如 1024 的倍數）會全撞。
- 刪除不能直接設 EMPTY（切斷探測鏈）→ tombstone。
- 字串 key：FNV-1a 32（h=0x811C9DC5；`h ^= b; h *= 0x01000193;`）再比字串本身。
- 走訪順序 ≠ 插入順序（需要時另存順序陣列）。

---

【參考卡｜演算法 7/8｜二分搜尋、prefix sum、滑動視窗（C，已測試）】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
```c
// 第一個 a[i] >= x 的 i（全都 < x 回傳 n）；a 已遞增排序
static size_t lower_bound(const int32_t *a, size_t n, int32_t x) {
    size_t lo = 0, hi = n;                       // 半開 [lo, hi)
    while (lo < hi) {
        size_t mid = lo + (hi - lo) / 2;
        if (a[mid] < x) lo = mid + 1; else hi = mid;
    }
    return lo;
}
// upper_bound（第一個 > x）：條件改 a[mid] <= x；出現次數 = upper - lower
```
- 例：a={1,2,2,2,5,7}：lower_bound(2)=1、upper_bound(2)=4、lower_bound(8)=6。
- bsearch 有重複值時不保證回傳第一個。閉區間+size_t 的 hi=mid-1 會下溢。
Prefix sum：`P[0]=0; P[i+1]=P[i]+a[i];`，`sum(a[l..r)) = P[r]-P[l]`，P 用 int64_t、長度 n+1。2-D：`P[r2][c2]-P[r1][c2]-P[r2][c1]+P[r1][c1]`。
Monotonic deque（滑動視窗最小值，out[j]=min(a[j..j+w))）：
```c
static int dq[MAXN]; int head = 0, tail = 0;     // 容量 >= n
for (int i = 0; i < n; i++) {
    while (tail > head && a[dq[tail - 1]] >= a[i]) tail--;
    dq[tail++] = i;
    if (dq[head] <= i - w) head++;
    if (i >= w - 1) out[i - w + 1] = a[dq[head]];
}
```
最大值版把 >= 改 <=。要輸出索引時 >= 保留最右、> 保留最舊，要和原程式一致。

---

【參考卡｜演算法 8/8｜排序事實與「優化後輸出完全相同」檢查】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
排序：
- C qsort：不保證 quicksort、不保證複雜度、不穩定。比較函式寫 `return (a > b) - (a < b);`，不要 `a - b`（溢位 UB）。要確定結果時把原始索引當最後一個鍵。
- C++ std::sort：C++11 起最壞 O(N log N)、不穩定；stable_sort 穩定；nth_element 平均 O(N)。Python sorted 穩定。
- n ≤ 約 16 或幾乎排好 → insertion sort；radix sort 有號數先 `^ 0x80000000`，跑偶數趟（4 趟）。
等價檢查（每改一處都做）：
- 原程式產生 golden output，新版 diff/cmp；寫隨機產生器對拍幾千組。
- 邊界：n=0（size_t 的 n-1 下溢）、n=1、2、最大 n（佇列 / heap 容量 ≥ E+1、stack 深度）。
- 溢位：和、乘積、平方距離、`INF + w`。
- 有號：`x >> k` 與 `x / 2^k` 對負數不同（-7/2=-3，-7>>1=-4）；% 的符號。
- Tie：排序穩定性、heap 彈出順序、top-k 同分取誰、argmin 取第一或最後。
- 走訪順序：hash 表、迭代 DFS 與遞迴 DFS 順序不同。
- 浮點：重排加法、多累加器、乘倒數都會改末位；要逐位元相同就不動運算順序。
- 副作用：新版（quickselect、原地排序）是否多改了輸入陣列；「找不到」回傳值相同。
- CRC：對 "123456789" check value 與原程式輸出各比一次。
主機檢查 UB：`gcc -O2 -fsanitize=address,undefined`。
