# 演算法與資料結構：效能優化工具箱（C 嵌入式寫法 + Python 註記）

- 用途：**備援（backup）pack**。demo 沒有直接提到演算法題，但「優化特定程式與整體系統效能」的題目最大收益常來自換演算法 / 資料結構。本檔整理「慢寫法 → 演算法替代」、緩衝區 / 查表 / 預先計算 / 排序 / 檢查碼 / 位元演算法 / 圖論 / 數值技巧，C 程式碼一律以嵌入式風格撰寫（熱路徑不 malloc、固定大小緩衝、`uint32_t` 等定寬型別）。可貼給考場 LLM 當 context，也可給考生自己查。
- 適用版本：C11（GCC / Clang，`__builtin_*` 為 GCC 擴充）；Python 3（CPython）；目標平台 Linux 主機或 RP2350（Hazard3 RISC-V / Cortex-M33，預設 150 MHz）。
- 來源（實際查閱）：
  - CRC 參數：Greg Cook, *Catalogue of parametrised CRC algorithms* https://reveng.sourceforge.io/crc-catalogue/all.htm （CRC-32/ISO-HDLC、CRC-16/IBM-3740 = CCITT-FALSE、CRC-16/XMODEM、CRC-16/KERMIT、CRC-16/MODBUS、CRC-16/ARC、CRC-8/SMBUS、CRC-8/MAXIM-DOW、CRC-32/ISCSI、CRC-32/MPEG-2）
  - Adler-32：RFC 1950 https://www.rfc-editor.org/rfc/rfc1950
  - FNV：IETF draft-eastlake-fnv https://datatracker.ietf.org/doc/html/draft-eastlake-fnv
  - Varint / ZigZag：Protocol Buffers Encoding https://protobuf.dev/programming-guides/encoding/
  - Base64：RFC 4648 https://www.rfc-editor.org/rfc/rfc4648
  - cppreference：`qsort` https://en.cppreference.com/w/c/algorithm/qsort 、`std::sort`、`std::nth_element`、`std::partial_sort`（https://en.cppreference.com/w/cpp/algorithm/ ）
  - Python：Time complexity of operations on built-in types https://docs.python.org/3/builtins/time-complexity.html （舊 wiki.python.org/moin/TimeComplexity 有同類表）
  - 演算法定義（BFS/DFS、Dijkstra、Kahn 拓撲排序、union-find、LIS、Bloom filter、Fibonacci hashing）：CLRS 等級標準內容，Wikipedia 對照定義
  - 本檔 C 程式碼（ring buffer、heap、hash、lower_bound、prefix sum、sparse table、monotonic deque、各排序、quickselect、全部 CRC / Adler / FNV、varint、Gray、union-find、LIS、BFS、Kahn、Dijkstra、powmod、gcd、isqrt、knapsack、base64）已在主機上以 `gcc -O2 -fsanitize=address,undefined` 實際編譯並與 Python `zlib` / `binascii` / 暴力解對拍通過。
- 最後更新：2026-11

> 標記：`⚠️未驗證` = 查不到一手來源；`⚠️估計` = 數量級估算，實際以量測為準。
> 相關檔案（不重複其內容）：`03-optimize.md`（量測流程、Amdahl）、`domain/riscv-hazard3.md`（§8 C 位元技巧、Hazard3 指令週期）、`domain/multicore-sync.md`（§A11 SPSC lock-free ring、§B7 `queue_t`）、`domain/pico-sdk.md`（§8 記憶體擺放、§10 量測）、`domain/pico-dma.md`（DMA ring / 雙緩衝）、`domain/control-dsp.md`（定點數）、`domain/c-linux-perf.md`（快取、blocking、perf）。

---

## 0. 三十秒重點

1. **先換演算法再微調**：O(n²) → O(n log n) / O(n) 的收益通常遠大於任何組語技巧。先看「巢狀迴圈」、「迴圈裡重算同一件事」、「線性搜尋」。
2. **固定大小 + 2 的冪**：ring buffer、hash table 容量取 2^k，索引用 `& (N-1)` 取代 `%`（Hazard3 `div/rem` 18～19 cycle，`and` 1 cycle）。
3. **陣列勝過鏈結**：MCU / 主機都一樣，連續記憶體 + 索引比指標追逐快且好除錯；需要「節點」時用固定 pool + 索引。
4. **預先計算**：prefix sum（區間和 O(1)）、running sum / monotonic deque（滑動視窗 O(1) 攤銷）、LUT（查表）、sparse table（靜態區間最小值 O(1)）。
5. **排序看資料**：n ≤ ~16 或幾乎排好 → insertion sort；小整數鍵 → counting / radix（O(n)）；只要前 k 名 → heap 或 quickselect，不要全排。`qsort` 不保證穩定、不保證複雜度。
6. **CRC 一定對 check value**：輸入 `"123456789"`，CRC-32/ISO-HDLC = `0xCBF43926`、CRC-16/CCITT-FALSE（= CRC-16/IBM-3740）= `0x29B1`。查表法 1 KB 表換約 8 倍迴圈次數減少。
7. **改完一定對拍**：舊版輸出當 golden，邊界（空、1 個、最大、重複值、溢位、tie 的順序）全部 `diff` 一致才算完成（§14）。

---

## 1. 複雜度速查：多大的 n 在 1 秒內可行

假設「一次簡單操作」≈ 幾個指令（載入、比較、加法）。⚠️估計：主機（現代 x86/ARM，-O2）約 1e8～1e9 簡單操作/秒；RP2350 150 MHz、程式在 SRAM 或 cache hit、整數運算，約 3e7～1e8 簡單操作/秒（Hazard3 大多數 ALU 指令 1 cycle，但 load-use、分支、除法、flash cache miss 會拉低）。

| 複雜度 | 主機 1 s 內可行 n（⚠️估計） | RP2350 @150 MHz 1 s 內（⚠️估計） | 典型演算法 |
|---|---|---|---|
| O(1) / O(log n) | 任意 | 任意 | 查表、hash、二分搜尋 |
| O(n) | 1e8 | 1e7～5e7 | 單趟掃描、prefix sum、counting sort |
| O(n log n) | 1e7 | 1e6（但 520 KB SRAM 先限制 n） | 排序、heap、Dijkstra |
| O(n√n) | 1e6 | 1e5 | 分塊 |
| O(n²) | 1e4～3e4 | 3e3～1e4 | 巢狀迴圈、DP 二維 |
| O(n³) | 500～1000 | 200～400 | Floyd–Warshall、矩陣乘 |
| O(2ⁿ) | 25～27 | 20～22 | 子集枚舉 |
| O(n!) | 11 | 9 | 全排列 |

MCU 上「常數因子」很重要（Hazard3 數字取自 `riscv-hazard3.md` §5）：

| 操作 | Hazard3 成本 | 替代 |
|---|---|---|
| `mul` / `mulh*` | 1 cycle | 用乘法取代除法（§10.4） |
| `div` / `rem` | 18～19 cycle | 2 的冪用 shift/mask；常數除數讓編譯器轉乘法 |
| load 後立刻用 | +1 cycle | 交錯指令 / 多累加器 |
| 分支預測錯 | 2 cycle（懲罰小） | 資料隨機時才考慮無分支 |
| `float` / `double` | 軟體模擬（Hazard3 無 FPU），數十～上百 cycle ⚠️估計 | 定點數（`control-dsp.md`）、整數比較（比平方距離不開根號） |
| XIP flash cache miss | 遠慢於 SRAM、不固定 | 熱碼 / 熱表放 SRAM（`pico-sdk.md` §8） |
| `malloc` / `free` | 不固定、可能碎片化 | 靜態陣列、pool（§3.5） |
| `printf` | 很慢（格式化 + I/O） | 熱路徑內不印；最後一次輸出 |

---

## 2. 慢寫法 → 演算法替代（最先看這張表）

| 慢寫法（特徵） | 複雜度 | 替代 | 新複雜度 | 注意 |
|---|---|---|---|---|
| 雙層迴圈找「是否存在 / 配對」 | O(n²) | hash set / 排序 + 二分 / 排序 + 雙指標 | O(n) 平均 / O(n log n) | hash 要處理碰撞；排序會改順序（必要時排索引） |
| 每個查詢都線性搜尋陣列 | O(nq) | 排序一次 + `lower_bound`；或 key 範圍小 → 直接索引表 | O((n+q) log n) / O(1) | 重複 key、找不到時的回傳值要和原版一致 |
| 每次重算視窗和 `sum(a[i..i+w))` | O(nw) | running sum：加新的、減舊的 | O(n) | 累加器寬度（int64）；浮點會累積誤差 → 用整數 |
| 每次重算視窗最大 / 最小 | O(nw) | monotonic deque | O(n) 攤銷 | tie 用 `>=` 或 `>` 決定保留哪個索引 |
| 多次查詢區間和 | O(nq) | prefix sum（1-D / 2-D） | O(n + q) | P 陣列長度 n+1，型別加寬 |
| 多次區間加值、最後才讀 | O(nq) | difference array | O(n + q) | 離線；中途要讀就要 Fenwick tree |
| 靜態陣列多次區間最小值 | O(nq) | sparse table | O(n log n + q) | 只適用 idempotent 運算（min/max/gcd/and/or） |
| ring 索引 `i = (i+1) % N` | 每次 div | N 取 2^k，`i & (N-1)`；或 `if (++i == N) i = 0;` | 1～2 cycle | 改 N 時要確認仍是 2 的冪（加 `_Static_assert`） |
| 全排序後只取前 k 個 / 中位數 | O(n log n) | 大小 k 的 heap / quickselect | O(n log k) / O(n) 平均 | quickselect 會打亂陣列；tie 順序不同 |
| 小整數鍵（0..255、0..65535）用比較排序 | O(n log n) | counting sort / radix sort | O(n + K) | 額外 buffer；穩定性 |
| 逐 bit 算 CRC | 8 迴圈 / byte | 256 項查表；slicing-by-4 | 1 次查表 / byte | 參數（refin/refout/init/xorout）不能錯 |
| 逐 bit 檢查旗標陣列 `bool flags[N]` | O(N) | bitset + `ctz` 只走被設的位元 | O(N/32 + 設定數) | 迭代順序（由低到高）要和原版相同 |
| `pow(x, n)` 迴圈乘 n 次 | O(n) | 快速冪 | O(log n) | 取模時中間值用 `uint64_t` |
| 重複呼叫純函式同參數 | 指數 | memoization / DP 表 | 狀態數 × 轉移 | 表大小、未初始化哨兵值 |
| `sqrt` / `float` 比距離 | 軟體浮點 | 比平方距離（整數） | — | 平方可能溢位 → `int64_t` |
| 鏈結串列走訪 / 插入 | cache miss | 陣列 + 索引；pool | — | 刪除時順序是否重要 |
| 迴圈裡 `strlen(s)` 當條件 | O(n²) | 先算一次長度 | O(n) | 迴圈內修改 s 的情況 |
| 字串反覆 `strcat` | O(n²) | 記住尾端指標 / 長度 | O(n) | 緩衝區上限 |
| 每次插入後重新排序 | O(n² log n) | 二分找位置 + `memmove`；或 heap | O(n²) 但常數極小 / O(n log n) | — |
| 重複除以同一個執行期變數 | n 次 div | 預算倒數（§10.4）；或改用乘法比較 | — | 一定要證明所有輸入結果相同 |
| 輪詢等待周邊 + 一筆一筆搬 | CPU 忙等 | DMA + 雙緩衝（`pico-dma.md`） | — | 見 §3.2 |

---

## 3. 緩衝區與佇列

### 3.1 Ring buffer（環形緩衝，單執行緒 / 單一 ISR 版）

```c
#include <stdint.h>
#include <stdbool.h>

#define RB_N 256u                         // 必須是 2 的冪
_Static_assert((RB_N & (RB_N - 1)) == 0, "RB_N must be power of 2");

typedef struct { uint8_t buf[RB_N]; uint32_t head, tail; } rb_t;   // head 寫、tail 讀，持續遞增

static inline uint32_t rb_count(const rb_t *r) { return r->head - r->tail; }  // 無號減法，溢位仍正確
static inline bool rb_put(rb_t *r, uint8_t v) {
    if (r->head - r->tail == RB_N) return false;      // 滿（可用滿 N 格，不浪費一格）
    r->buf[r->head & (RB_N - 1)] = v; r->head++; return true;
}
static inline bool rb_get(rb_t *r, uint8_t *v) {
    if (r->head == r->tail) return false;             // 空
    *v = r->buf[r->tail & (RB_N - 1)]; r->tail++; return true;
}
```

- 兩種常見設計：(a) 本例「索引持續遞增 + 取用時 mask」，滿 = `head - tail == N`；(b) 索引保持在 0..N-1，留一格空來區分滿 / 空（容量 N-1）。改寫舊程式時要保持**容量與滿時行為**（丟新資料 / 覆蓋舊資料 / 回傳失敗）一致。
- 若 N 必須不是 2 的冪：`if (++i == N) i = 0;` 比 `%` 快。
- 一個寫、一個讀分別在 ISR 與主迴圈，或兩個核心 → 要用 atomic + memory order：見 `multicore-sync.md` §A11（SPSC lock-free）、§B8（ISR 共享變數）；pico 跨核可直接用 `queue_t`（§B7）。
- 批次：一次取出連續區段 `min(count, N - (tail & (N-1)))` 用 `memcpy`，比逐 byte 快。

### 3.2 雙緩衝（double / ping-pong buffering）

```c
#define BLK 512
static int16_t bufA[BLK], bufB[BLK];
int16_t *fill = bufA, *work = bufB;
// 迴圈：啟動 DMA/ISR 填 fill；CPU 處理 work；兩者都完成後交換指標（不是複製資料）
// int16_t *t = fill; fill = work; work = t;
```

- 重點：**交換指標**而非 `memcpy`；處理時間必須 < 填滿時間，否則要三緩衝或加大 BLK。
- DMA 實作細節（chain、ring、IRQ）見 `pico-dma.md`；跨核管線見 `multicore-sync.md` §B7 範例。

### 3.3 Deque（雙端佇列）

用 ring buffer 實作：`push_back` 寫 `buf[head++ & M]`、`push_front` 寫 `buf[--tail & M]`、`pop_back` 讀 `buf[--head & M]`、`pop_front` 讀 `buf[tail++ & M]`；數量仍為 `head - tail`（無號）。§5.6 的 monotonic deque 因為長度上限 = 視窗大小，常直接用線性陣列 + 兩個索引。

Python：`collections.deque` 兩端 append/pop 皆 O(1)；中間索引 O(n)；`deque(maxlen=w)` 自動丟掉舊元素。`list.pop(0)` / `list.insert(0, x)` 是 O(n)（官方表：`pop(k)` 為 O(n-k)），當佇列用要換 deque。

### 3.4 Priority queue：binary heap（min-heap，固定容量）

```c
#define HEAP_MAX 1024
typedef struct { int32_t a[HEAP_MAX]; int n; } heap_t;

static bool heap_push(heap_t *h, int32_t v) {           // O(log n)
    if (h->n == HEAP_MAX) return false;
    int i = h->n++;
    while (i > 0) {                                      // sift-up：父節點 (i-1)/2
        int p = (i - 1) / 2;
        if (h->a[p] <= v) break;
        h->a[i] = h->a[p]; i = p;
    }
    h->a[i] = v; return true;
}
static bool heap_pop(heap_t *h, int32_t *out) {         // O(log n)，取最小
    if (h->n == 0) return false;
    *out = h->a[0];
    int32_t v = h->a[--h->n];
    int i = 0;
    for (;;) {                                           // sift-down：子節點 2i+1, 2i+2
        int c = 2 * i + 1;
        if (c >= h->n) break;
        if (c + 1 < h->n && h->a[c + 1] < h->a[c]) c++;
        if (v <= h->a[c]) break;
        h->a[i] = h->a[c]; i = c;
    }
    h->a[i] = v; return true;
}
```

- 建堆：n 個元素逐一 push 是 O(n log n)；由 `n/2-1` 往下逐一 sift-down 是 O(n)。
- max-heap：比較反過來，或存 `-x`（注意 `INT32_MIN` 取負溢位）。
- heap **不穩定**：相同 key 的彈出順序不保證是插入順序。要穩定 → key 加上遞增序號 `(key, seq)` 一起比較。
- Python：`heapq` 是 min-heap，`heappush`/`heappop` O(log n)，`heapify` O(n)；`heapq.nlargest(k, it)` / `nsmallest`。

### 3.5 固定大小 pool / free list（取代 malloc）

```c
#define POOL_N 64
typedef struct node { struct node *next; int payload[4]; } node_t;
static node_t pool[POOL_N];
static node_t *free_list;

static void pool_init(void) {
    for (int i = 0; i < POOL_N - 1; i++) pool[i].next = &pool[i + 1];
    pool[POOL_N - 1].next = NULL; free_list = &pool[0];
}
static node_t *pool_alloc(void) { node_t *n = free_list; if (n) free_list = n->next; return n; }  // O(1)
static void    pool_free(node_t *n) { n->next = free_list; free_list = n; }                       // O(1)
```

- O(1)、無碎片、可預測。耗盡時回傳 NULL —— 必須處理。
- 也可用 `uint16_t next_idx` 索引取代指標（省記憶體、可序列化）。
- ISR 與主迴圈都會 alloc/free → 包臨界區（`multicore-sync.md` §B6）。

### 3.6 Bitset / bitmap

```c
#define NBITS 1000
static uint32_t bs[(NBITS + 31) / 32];
#define BS_SET(i)  (bs[(i) >> 5] |=  (1u << ((i) & 31)))
#define BS_CLR(i)  (bs[(i) >> 5] &= ~(1u << ((i) & 31)))
#define BS_TEST(i) ((bs[(i) >> 5] >> ((i) & 31)) & 1u)

// 只走訪被設定的位元（由小到大），跳過整個 0 字組
for (unsigned w = 0; w < (NBITS + 31) / 32; w++) {
    uint32_t x = bs[w];
    while (x) {
        unsigned i = w * 32 + (unsigned)__builtin_ctz(x);   // x != 0 才能呼叫 ctz
        /* visit(i) */
        x &= x - 1;                                         // 清掉最低位的 1
    }
}
// 計數：sum of __builtin_popcount(bs[w])；集合運算：逐字組 & | ^ ~
```

- 用途：大量布林旗標（8 倍省記憶體）、集合交集 / 聯集一次 32 個、已訪問標記、空閒 slot 分配（找第一個 0：`__builtin_ctz(~x)`，`~x != 0` 時）。
- Hazard3 有 `ctz`/`cpop` 單週期指令（`riscv-hazard3.md` §4.1）。
- 最後一個字組的多餘位元（NBITS 不是 32 的倍數）在 `~` / popcount 時要遮掉。

---

## 4. 查找（Lookup）

### 4.1 直接索引表（最快的「hash」）

key 範圍小（例如 0..255、0..4095）→ 直接 `table[key]`。O(1)、無碰撞、無比較。
- 字元分類：`static const uint8_t is_delim[256]`。
- 「是否出現過」：bitset（§3.6）。
- 稀疏但範圍中等：先 `key - min` 平移。
- 記憶體換時間：表大小 = 範圍 × 元素大小，確認放得下（RP2350 SRAM 520 KB；XIP cache 16 KB → 大的 const 表放 flash 會頻繁 miss，熱表用 `__not_in_flash`，見 `pico-sdk.md` §8.2）。

### 4.2 Hash table：open addressing + linear probing（固定容量）

```c
#define HT_BITS 10
#define HT_SIZE (1u << HT_BITS)                 // 1024 槽；最多放 ~0.7*HT_SIZE 筆
#define EMPTY_KEY 0xFFFFFFFFu                   // 保留一個不會出現的 key 當「空」
typedef struct { uint32_t key; int32_t val; } slot_t;
static slot_t ht[HT_SIZE];

static void ht_init(void) { for (uint32_t i = 0; i < HT_SIZE; i++) ht[i].key = EMPTY_KEY; }

// Fibonacci（乘法）hashing：乘 floor(2^32/φ) = 2654435769 = 0x9E3779B9，取「高」HT_BITS 位
static inline uint32_t hash32(uint32_t k) { return (k * 2654435769u) >> (32 - HT_BITS); }

static int32_t *ht_get_or_insert(uint32_t key, bool *inserted) {
    uint32_t i = hash32(key);
    for (uint32_t probe = 0; probe < HT_SIZE; probe++) {
        if (ht[i].key == key)       { *inserted = false; return &ht[i].val; }
        if (ht[i].key == EMPTY_KEY) { ht[i].key = key; ht[i].val = 0; *inserted = true; return &ht[i].val; }
        i = (i + 1) & (HT_SIZE - 1);           // linear probing
    }
    return NULL;                               // 表滿
}
static int32_t *ht_find(uint32_t key) {
    uint32_t i = hash32(key);
    for (uint32_t probe = 0; probe < HT_SIZE; probe++) {
        if (ht[i].key == key)       return &ht[i].val;
        if (ht[i].key == EMPTY_KEY) return NULL;   // 遇到空槽 = 不存在
        i = (i + 1) & (HT_SIZE - 1);
    }
    return NULL;
}
```

| 重點 | 說明 |
|---|---|
| 負載因子 α = 筆數 / 槽數 | linear probing 平均探測數（Knuth）：成功 ≈ ½(1 + 1/(1−α))，失敗 ≈ ½(1 + 1/(1−α)²)。α = 0.5 → 1.5 / 2.5；α = 0.9 → 5.5 / 50.5。**保持 α ≤ 0.7** |
| 為何取高位 | 乘法雜湊的高位混合了所有輸入位元；`k & mask`（取低位）對「都是 1024 的倍數」這類 key 會全部撞在同一槽 |
| 刪除 | 不能直接設 EMPTY（會切斷探測鏈）→ 用 tombstone 標記，或 backward-shift deletion；若題目不需刪除就別做 |
| 64-bit key | 常數 `0x9E3779B97F4A7C15`，`(k * C) >> (64 - bits)` |
| 字串 key | 先用 FNV-1a（§7.5）算 32-bit 雜湊，再比字串本身確認 |
| 迭代順序 | hash 表走訪順序 ≠ 插入順序。原程式若「依出現順序輸出」，要另存順序陣列 |
| 最壞情況 | 所有 key 撞在一起 → O(n)；對手可控輸入時要注意 |
| Python | `dict` / `set` 平均 O(1)，最壞 O(n)（官方表註明）；`collections.Counter` 計數；Python 3.7+ dict 保持插入順序 |

### 4.3 二分搜尋：`lower_bound` / `upper_bound`（半開區間寫法）

```c
// 回傳第一個 a[i] >= x 的 i（全都 < x 時回傳 n）。a 必須已遞增排序。
static size_t lower_bound(const int32_t *a, size_t n, int32_t x) {
    size_t lo = 0, hi = n;                       // 搜尋 [lo, hi)
    while (lo < hi) {
        size_t mid = lo + (hi - lo) / 2;         // 不寫 (lo+hi)/2，避免溢位
        if (a[mid] < x) lo = mid + 1; else hi = mid;
    }
    return lo;
}
// 第一個 a[i] > x：把條件改成 a[mid] <= x
// x 的出現次數 = upper_bound - lower_bound；存在與否：i < n && a[i] == x
```

例：`a = {1,2,2,2,5,7}` → `lower_bound(2) = 1`、`upper_bound(2) = 4`、`lower_bound(8) = 6`、`lower_bound(0) = 0`、n = 0 時回傳 0。

| 陷阱 | 後果 | 正確 |
|---|---|---|
| `mid = (lo + hi) / 2` 用 int | 溢位 | `lo + (hi - lo) / 2` |
| 閉區間 `[lo, hi]` 用 `size_t`，`hi = mid - 1` | mid = 0 時下溢成巨大值 | 用半開區間 `[lo, hi)` |
| `lo = mid`（而非 mid+1） | 剩兩個元素時無窮迴圈 | 半開寫法固定 `lo = mid + 1` / `hi = mid` |
| 用 `bsearch` 找「插入位置」 | `bsearch` 只回傳「某一個」相等元素或 NULL，有重複時不保證是第一個 | 自己寫 lower_bound |
| 陣列沒排序 / 排序用的比較與搜尋不一致 | 錯誤結果 | 同一個比較函式 |
| 浮點 / 單調函數上二分答案 | 終止條件 | 整數答案用同一模板，條件換成 `!ok(mid)` |

標準庫：C `bsearch(key, base, n, size, cmp)`；C++ `std::lower_bound` / `std::upper_bound` / `std::equal_range`；Python `bisect.bisect_left`（= lower_bound）、`bisect_right`（= upper_bound）。`bisect.insort` 搜尋 O(log n) 但插入 O(n)。

### 4.4 排序陣列 vs 樹 vs hash

| 結構 | 查找 | 插入 / 刪除 | 有序走訪 | 嵌入式適合度 |
|---|---|---|---|---|
| 未排序陣列 | O(n) | O(1) 尾端 | 否 | n 很小（≤ ~16）時其實最快 ⚠️估計 |
| 排序陣列 + 二分 | O(log n) | O(n)（`memmove`） | 是 | **讀多寫少首選**；連續記憶體、無指標 |
| 平衡樹（紅黑 / AVL） | O(log n) | O(log n) | 是 | 程式碼長、指標多、cache 不友善；考場少自己寫 |
| Hash（open addressing） | O(1) 平均 | O(1) 平均 | 否 | key 隨機查、只問等不等 |
| 直接索引表 | O(1) | O(1) | 是 | key 範圍小 |

「建表一次、查很多次」→ 排序陣列 / 靜態 hash；「邊插邊查、要有序」→ 才考慮樹或 skip list。

### 4.5 Trie（簡述）

- 每個節點有 `child[alphabet]`，查一個長度 L 的字串 O(L)，與字典大小無關；可做前綴查詢。
- 嵌入式寫法：節點放固定陣列 `uint16_t child[MAXNODE][26]`，0 表示沒有子節點（根為節點 0，新節點從 1 開始配）。記憶體 = 節點數 × 字母數 × 2 B，容易爆 → 字母表大時用排序陣列 / hash 取代。
- 只需「整字是否存在」時 hash 通常更省。

### 4.6 Bloom filter（簡述）

- m 個位元的 bitset + k 個雜湊函數；插入設 k 個位元，查詢檢查 k 個位元全為 1。
- **可能誤報（false positive），不會漏報**；不能刪除（除非 counting Bloom filter）。
- 誤報率 p ≈ (1 − e^(−kn/m))^k；最佳 k = (m/n)·ln 2。例：每個元素 10 bit（m/n = 10）→ k ≈ 7，p ≈ 0.8%。
- k 個雜湊可用兩個雜湊組合：`h_i = h1 + i*h2`。
- 用途：在昂貴查找（flash、網路）前先快速排除「一定不存在」。若題目要求精確答案，只能當前置過濾，命中後仍要真正查。

---

## 5. 預先計算（Precomputation）

### 5.1 Prefix sum（1-D）

```c
// P[0] = 0, P[i+1] = P[i] + a[i]；sum(a[l..r)) = P[r] - P[l]（半開）
int64_t P[N + 1];                 // 加寬型別：n 個 int32 相加會溢位 int32
P[0] = 0;
for (size_t i = 0; i < n; i++) P[i + 1] = P[i] + a[i];
```

- 平均 / 計數 / 「區間內有幾個符合條件」（先把條件轉 0/1 再做 prefix）。
- Python：`itertools.accumulate(a, initial=0)`（`initial` 參數 3.8+）。

### 5.2 Prefix sum（2-D）

```c
// P 為 (R+1)×(C+1)，第 0 列 / 第 0 行為 0
for (int i = 1; i <= R; i++)
    for (int j = 1; j <= C; j++)
        P[i][j] = a[i-1][j-1] + P[i-1][j] + P[i][j-1] - P[i-1][j-1];
// 矩形 [r1, r2) × [c1, c2) 的和：
// P[r2][c2] - P[r1][c2] - P[r2][c1] + P[r1][c1]
```

用途：影像 box filter / 積分影像（integral image）、矩形區域計數，查詢從 O(面積) 變 O(1)。

### 5.3 Difference array（離線區間加值）

```c
// 對 [l, r) 全部加 v：D[l] += v; D[r] -= v;   (D 長度 n+1，初始 0)
// 全部操作做完後：a[i] = D[0] + ... + D[i]（再做一次 prefix sum）
```

q 次區間更新 + 最後讀一次：O(n + q)。若更新與查詢交錯，改用 Fenwick tree（BIT，更新 / 查詢皆 O(log n)）。

### 5.4 Sparse table（靜態 RMQ，O(1) 查詢）

```c
#define ST_N 1024
#define ST_LOG 11                                 // floor(log2(ST_N)) + 1
static int32_t st[ST_LOG][ST_N];                  // st[k][i] = min(a[i .. i+2^k))
static void st_build(const int32_t *a, int n) {   // O(n log n)
    memcpy(st[0], a, n * sizeof a[0]);
    for (int k = 1; (1 << k) <= n; k++)
        for (int i = 0; i + (1 << k) <= n; i++) {
            int32_t x = st[k-1][i], y = st[k-1][i + (1 << (k-1))];
            st[k][i] = x < y ? x : y;
        }
}
static int32_t st_min(int l, int r) {             // 閉區間 [l, r]，l <= r
    int k = 31 - __builtin_clz((unsigned)(r - l + 1));   // floor(log2(len))
    int32_t x = st[k][l], y = st[k][r - (1 << k) + 1];   // 兩段重疊沒關係（min 為 idempotent）
    return x < y ? x : y;
}
```

只適用「重疊計算兩次結果不變」的運算（min、max、gcd、&、|）；區間和**不行**（用 prefix sum）。記憶體 n·log n 個元素，MCU 上要算清楚。

### 5.5 LUT（查表）與 memoization

| 方式 | 何時用 | 代價 |
|---|---|---|
| 編譯期常數表 `static const T lut[N] = {...}` | 函數輸入範圍小（8-bit 輸入、角度 0..359） | flash 空間；放 flash 時隨機讀可能 cache miss |
| 開機時建表（如 CRC 表） | 表可由程式產生、不想手打 | 初始化時間、RAM |
| 小表 + 內插 | 平滑函數（sin、exp）的定點近似 | 精度 vs 表大小（詳見 `control-dsp.md`） |
| 拆分查表 | 32-bit 輸入 → 4 次 8-bit 查表（如 popcount、bit reverse、CRC slicing） | 256 項 × 4 |
| memoization | 遞迴有重疊子問題 | 狀態數 × 元素大小 |

表大小直覺：256 × `uint8_t` = 256 B；256 × `uint32_t` = 1 KB；65536 × `uint16_t` = 128 KB（超過 RP2350 16 KB XIP cache，放 flash 幾乎每次都 miss，放 SRAM 則吃掉 1/4 SRAM）。**表越大不一定越快**，要量測。

Memoization（C，固定陣列 + 哨兵）：

```c
#define MAXN 92
static int64_t memo[MAXN + 1];                // 0 表示「未計算」（fib(0)=0 另外處理）
int64_t fib(int n) {
    if (n < 2) return n;
    if (memo[n]) return memo[n];
    return memo[n] = fib(n - 1) + fib(n - 2);
}
// 更好：改成由小到大的迴圈（bottom-up DP），沒有遞迴深度 / stack 風險
```

Python：`@functools.cache`（3.9+）或 `@functools.lru_cache(maxsize=None)`；遞迴深度預設上限約 1000（`sys.getrecursionlimit()`），深遞迴改迴圈。

### 5.6 滑動視窗：running sum 與 monotonic deque

Running sum（視窗大小 w）：

```c
int64_t s = 0;
for (int i = 0; i < n; i++) {
    s += a[i];
    if (i >= w) s -= a[i - w];
    if (i >= w - 1) out[i - w + 1] = s;       // 視窗 [i-w+1, i]
}
```

- 移動平均：輸出 `s / w` 時注意原程式的取整方式（C 整數除法朝 0 截斷；負數與 `>>` 不同）。
- **浮點** running sum 會累積誤差，與「每次重算」輸出不一定逐位元相同 → 要求完全相同就用整數，或定期重算。

Monotonic deque（滑動視窗最小值，O(n) 攤銷）：

```c
// out[j] = min(a[j .. j+w))，j = 0 .. n-w；dq 存索引，對應值單調遞增
static void sliding_min(const int32_t *a, int n, int w, int32_t *out) {
    static int dq[MAXN]; int head = 0, tail = 0;       // 線性陣列：tail 最多到 n，所以容量要 >= n
    for (int i = 0; i < n; i++) {
        while (tail > head && a[dq[tail - 1]] >= a[i]) tail--;   // 丟掉不可能再成為最小的
        dq[tail++] = i;
        if (dq[head] <= i - w) head++;                           // 最前面的已滑出視窗
        if (i >= w - 1) out[i - w + 1] = a[dq[head]];
    }
}
```

記憶體吃緊時把 `dq` 改成 ring buffer（同時存在的索引最多 w+1 個，容量取 ≥ w+1 的 2 的冪）。最大值版本把 `>=` 改成 `<=`。只輸出值時 `>=`/`>` 都對；若要輸出「最小值的索引」，`>=` 保留最新（最右）的、`>` 保留最舊的，要和原程式 tie 規則一致。

### 5.7 雙指標（two-pointer）

```c
// 例 1：已排序陣列中，和 == target 的配對是否存在（O(n)）
size_t i = 0, j = n - 1;                       // n >= 2
while (i < j) {
    int64_t s = (int64_t)a[i] + a[j];
    if (s == target) return true;
    if (s < target) i++; else j--;
}
// 例 2：非負陣列，和 <= S 的最長連續子陣列（O(n)）
int64_t s = 0; size_t best = 0;
for (size_t r = 0, l = 0; r < n; r++) {
    s += a[r];
    while (s > S) s -= a[l++];
    if (r + 1 - l > best) best = r + 1 - l;
}
```

例 2 只在元素**非負**時成立（視窗和單調）；有負數時要改用 prefix sum + 其他方法。

---

## 6. 排序

### 6.1 依資料選演算法

| 情況 | 選擇 | 複雜度 | 穩定 | 額外記憶體 |
|---|---|---|---|---|
| n ≤ ~16，或幾乎已排序 | insertion sort | O(n²) 最壞，O(n + 逆序數) | 是 | O(1) |
| 一般、不要求穩定 | `qsort` / 手寫 introsort / heap sort | 實作而定 / O(n log n) | 否 | O(log n) / O(1) |
| 要求穩定、一般 key | merge sort（需 buffer） | O(n log n) | 是 | O(n) |
| key 為小範圍整數（K 小） | counting sort | O(n + K) | 是（反向填或用前綴位置） | O(n + K) |
| 32-bit 整數、n 大 | LSD radix sort（4 趟 × 8 bit） | O(4n + 4·256) | 是 | O(n) |
| 只要前 k 名 | heap（大小 k）/ `std::partial_sort` | O(n log k) | 否 | O(k) |
| 只要第 k 小 / 中位數 | quickselect / `std::nth_element` | O(n) 平均 | 否 | O(1) |

標準庫事實（cppreference）：
- C `qsort`：C 與 POSIX **都不要求**使用 quicksort，也**不保證複雜度與穩定性**。比較函式回傳負 / 0 / 正，且對同一對元素必須給一致結果。
- C++ `std::sort`：C++11 起最壞 O(N log N) 次比較；**不穩定**。`std::stable_sort` 穩定。`std::partial_sort` 約 N·log(M) 次比較。`std::nth_element` 平均 O(N)。
- Python `list.sort()` / `sorted()`：O(n log n)，**保證穩定**；`key=` 比 `cmp_to_key` 快。

### 6.2 qsort 比較函式（不要用減法）

```c
static int cmp_i32(const void *pa, const void *pb) {
    int32_t a = *(const int32_t *)pa, b = *(const int32_t *)pb;
    return (a > b) - (a < b);          // 不要寫 return a - b;（INT_MIN - 1 溢位 → UB、順序錯）
}
qsort(arr, n, sizeof arr[0], cmp_i32);
```

- `qsort` 每次比較都經過函式指標 + `void*` 轉型，無法 inline；手寫 `int32_t` 專用排序（或 C++ `std::sort`）常快數倍 ⚠️估計。
- 多鍵排序：先比主鍵，相等再比次鍵；需要「穩定」時把原始索引當最後一個鍵（讓 `qsort` 結果變確定）。

### 6.3 Insertion sort

```c
static void insertion_sort(int32_t *a, int n) {
    for (int i = 1; i < n; i++) {
        int32_t v = a[i]; int j = i - 1;
        while (j >= 0 && a[j] > v) { a[j + 1] = a[j]; j--; }   // 用 > 才穩定
        a[j + 1] = v;
    }
}
```

用途：小陣列、即時資料每次只新增一筆（插入維持排序）、作為 quicksort / introsort 小區段的收尾。

### 6.4 Counting sort（uint8_t，穩定）

```c
static void counting_sort_u8(const uint8_t *in, uint8_t *out, int n) {
    uint32_t cnt[256] = {0};
    for (int i = 0; i < n; i++) cnt[in[i]]++;
    uint32_t sum = 0;
    for (int v = 0; v < 256; v++) { uint32_t c = cnt[v]; cnt[v] = sum; sum += c; }  // 前綴 → 起始位置
    for (int i = 0; i < n; i++) out[cnt[in[i]]++] = in[i];                         // 依原順序放 → 穩定
}
```

只需要排序後的「值」時，可以直接依 cnt 重寫陣列，不需 out。排的是結構（依某欄位）時要用上面「起始位置」版本才穩定。

### 6.5 LSD radix sort（uint32_t）

```c
static void radix_sort_u32(uint32_t *a, uint32_t *tmp, size_t n) {   // tmp 長度 n
    for (int shift = 0; shift < 32; shift += 8) {
        uint32_t cnt[256] = {0};
        for (size_t i = 0; i < n; i++) cnt[(a[i] >> shift) & 0xFF]++;
        uint32_t sum = 0;
        for (int d = 0; d < 256; d++) { uint32_t c = cnt[d]; cnt[d] = sum; sum += c; }
        for (size_t i = 0; i < n; i++) tmp[cnt[(a[i] >> shift) & 0xFF]++] = a[i];
        uint32_t *t = a; a = tmp; tmp = t;           // 交換角色；4 趟（偶數）後結果回到原 a
    }
}
```

- 有號 `int32_t`：先 `x ^ 0x80000000u` 轉成無號序再排，排完轉回。
- 某一位元組全部相同時可跳過該趟（cnt 只有一個非零），但要注意 4 趟偶數次交換的假設會被打破。
- n 很小時（< 幾百 ⚠️估計）radix 的固定成本（每趟 256 項）不划算。

### 6.6 Quickselect（第 k 小，0-based，平均 O(n)）

```c
static int32_t quickselect(int32_t *a, int n, int k) {   // 會重排 a
    int lo = 0, hi = n - 1;
    while (lo < hi) {
        int32_t pivot = a[lo + (hi - lo) / 2];
        int i = lo, j = hi;
        while (i <= j) {                                  // Hoare 風格分割
            while (a[i] < pivot) i++;
            while (a[j] > pivot) j--;
            if (i <= j) { int32_t t = a[i]; a[i] = a[j]; a[j] = t; i++; j--; }
        }
        if (k <= j) hi = j;
        else if (k >= i) lo = i;
        else return a[k];                                 // j < k < i：已就位（等於 pivot）
    }
    return a[k];
}
```

- 最壞 O(n²)（pivot 一直選爛）；取中間或三數取中通常足夠。
- 中位數：n 奇數 k = n/2；n 偶數時原程式可能取 `(a[n/2-1] + a[n/2]) / 2`，要確認定義與取整。
- 不能改原陣列 → 先複製。

### 6.7 Top-k（heap）

保留大小 k 的 **min-heap**，裝目前最大的 k 個：新元素 > 堆頂才替換堆頂並 sift-down。O(n log k)，記憶體 O(k)，適合資料串流。結束後堆內無序，需要排序輸出再排 k 個。Tie（等於堆頂）時要不要替換，決定了「同分取先出現或後出現」，要和原程式一致。

---

## 7. 檢查碼、雜湊與編碼

### 7.1 CRC 參數（reveng CRC catalogue，check = 對 ASCII `"123456789"` 計算的結果）

| 名稱（catalogue 正式名） | 常見別名 | width | poly | init | refin | refout | xorout | check |
|---|---|---|---|---|---|---|---|---|
| CRC-32/ISO-HDLC | CRC-32、PKZIP、V-42、XZ（zlib/Ethernet 用的） | 32 | 0x04C11DB7 | 0xFFFFFFFF | true | true | 0xFFFFFFFF | **0xCBF43926** |
| CRC-32/ISCSI | CRC-32C、Castagnoli | 32 | 0x1EDC6F41 | 0xFFFFFFFF | true | true | 0xFFFFFFFF | 0xE3069283 |
| CRC-32/MPEG-2 | — | 32 | 0x04C11DB7 | 0xFFFFFFFF | false | false | 0x00000000 | 0x0376E6E7 |
| CRC-16/IBM-3740 | **CRC-16/CCITT-FALSE**、CRC-16/AUTOSAR | 16 | 0x1021 | 0xFFFF | false | false | 0x0000 | **0x29B1** |
| CRC-16/XMODEM | ZMODEM、CRC-16/ACORN、CRC-16/LTE | 16 | 0x1021 | 0x0000 | false | false | 0x0000 | 0x31C3 |
| CRC-16/KERMIT | CRC-16/CCITT、CRC-16/CCITT-TRUE、CRC-CCITT | 16 | 0x1021 | 0x0000 | true | true | 0x0000 | 0x2189 |
| CRC-16/MODBUS | MODBUS | 16 | 0x8005 | 0xFFFF | true | true | 0x0000 | 0x4B37 |
| CRC-16/ARC | CRC-16、CRC-IBM、LHA | 16 | 0x8005 | 0x0000 | true | true | 0x0000 | 0xBB3D |
| CRC-8/SMBUS | CRC-8 | 8 | 0x07 | 0x00 | false | false | 0x00 | 0xF4 |
| CRC-8/MAXIM-DOW | CRC-8/MAXIM、DOW-CRC（1-Wire） | 8 | 0x31 | 0x00 | true | true | 0x00 | 0xA1 |

- **「CRC-CCITT」名稱混亂**：catalogue 指出 CRC-16/IBM-3740 常被誤稱為 CRC-CCITT；嚴格說 CRC-CCITT 是 LSB-first 的 KERMIT 版本。題目只寫「CRC-CCITT」時，一定用 check value 對答案或問清楚參數。
- refin = true（反射）時，實作用「右移 + 反射多項式」：0x04C11DB7 反射 = **0xEDB88320**；0x8005 反射 = **0xA001**；0x31 反射 = 0x8C。
- poly 寫法用「省略最高位」的 normal 表示（catalogue 慣例）。

### 7.2 CRC-32/ISO-HDLC：逐位元 → 查表 → slicing-by-4

```c
// (a) 逐 bit（無表，最省記憶體；每 byte 8 次迴圈）
uint32_t crc32_bitwise(const uint8_t *p, size_t n) {
    uint32_t crc = 0xFFFFFFFFu;                                  // init
    while (n--) {
        crc ^= *p++;                                             // refin=true：從 LSB 開始
        for (int k = 0; k < 8; k++)
            crc = (crc >> 1) ^ (0xEDB88320u & -(crc & 1u));      // 無分支：最低位為 1 才 xor
    }
    return crc ^ 0xFFFFFFFFu;                                    // xorout
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
// 可分段呼叫：crc = crc32_update(0, p1, n1); crc = crc32_update(crc, p2, n2);（與 zlib.crc32 相同介面）
uint32_t crc32_update(uint32_t crc, const uint8_t *p, size_t n) {
    crc = ~crc;
    while (n--) crc = (crc >> 8) ^ crc32_tab[(crc ^ *p++) & 0xFFu];
    return ~crc;
}
```

(c) Slicing-by-4（4 KB 表，每 4 byte 一次處理，打破相依鏈）：

```c
static uint32_t T4[4][256];                        // T4[0] = crc32_tab
void crc32_s4_init(void) {
    crc32_init();
    for (int i = 0; i < 256; i++) {
        T4[0][i] = crc32_tab[i];
        for (int t = 1; t < 4; t++) T4[t][i] = (T4[t-1][i] >> 8) ^ crc32_tab[T4[t-1][i] & 0xFF];
    }
}
uint32_t crc32_s4(const uint8_t *p, size_t n) {
    uint32_t crc = 0xFFFFFFFFu;
    while (n >= 4) {                               // 逐 byte 組成 little-endian word：避免非對齊存取（Hazard3 會 trap）
        crc ^= (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
        crc = T4[3][crc & 0xFF] ^ T4[2][(crc >> 8) & 0xFF] ^ T4[1][(crc >> 16) & 0xFF] ^ T4[0][crc >> 24];
        p += 4; n -= 4;
    }
    while (n--) crc = (crc >> 8) ^ crc32_tab[(crc ^ *p++) & 0xFF];
    return ~crc;
}
```

| 方法 | 表大小 | 每 byte 工作量 | 適用 |
|---|---|---|---|
| bitwise | 0 | 8 次 shift/xor | flash 極小、資料量小 |
| 4-bit 表（nibble） | 16 項 | 2 次查表 | 折衷（MCU 常用） |
| 256 項表 | 1 KB（CRC-32）/ 512 B（CRC-16） | 1 次查表 | 預設選擇 |
| slicing-by-4 / -8 | 4 KB / 8 KB | 每 4/8 byte 4/8 次查表 | 主機大資料；MCU 上表要放 SRAM 才有意義 |
| 硬體 | — | — | RP2350 DMA 有 sniffer 可邊搬邊算 CRC（見 `pico-dma.md`） |

### 7.3 CRC-16/CCITT-FALSE（MSB-first，非反射）與 CRC-8/SMBUS

```c
uint16_t crc16_ccitt_false(const uint8_t *p, size_t n) {         // check 0x29B1
    uint16_t crc = 0xFFFF;
    while (n--) {
        crc ^= (uint16_t)(*p++) << 8;                            // refin=false：byte 放到高位
        for (int k = 0; k < 8; k++)
            crc = (crc & 0x8000) ? (uint16_t)((crc << 1) ^ 0x1021) : (uint16_t)(crc << 1);
    }
    return crc;                                                  // xorout = 0
}
// 查表版：tab[i] = 上式對單一 byte i（init 0）跑 8 次的結果
//   crc = (uint16_t)((crc << 8) ^ tab[((crc >> 8) ^ *p++) & 0xFF]);
// CRC-16/XMODEM：同一程式，只把 init 改 0x0000（check 0x31C3）

uint8_t crc8_smbus(const uint8_t *p, size_t n) {                 // check 0xF4
    uint8_t crc = 0x00;
    while (n--) {
        crc ^= *p++;
        for (int k = 0; k < 8; k++)
            crc = (crc & 0x80) ? (uint8_t)((crc << 1) ^ 0x07) : (uint8_t)(crc << 1);
    }
    return crc;
}

uint16_t crc16_modbus(const uint8_t *p, size_t n) {              // check 0x4B37（反射：右移 + 0xA001）
    uint16_t crc = 0xFFFF;
    while (n--) { crc ^= *p++; for (int k = 0; k < 8; k++) crc = (crc & 1) ? (crc >> 1) ^ 0xA001 : (crc >> 1); }
    return crc;                                                  // Modbus RTU 傳送時低位元組先送
}
```

Python 對拍：`zlib.crc32(b"123456789") == 0xCBF43926`；`binascii.crc_hqx(data, 0xFFFF)` = CRC-16/CCITT-FALSE（`0x29B1`），`binascii.crc_hqx(data, 0)` = XMODEM（`0x31C3`）。

CRC 除錯：結果不對時依序檢查 (1) init、(2) 是否反射（右移 vs 左移、多項式是否用反射值）、(3) xorout、(4) 輸出 byte 順序、(5) 計算範圍是否含 header / 長度欄位、(6) 是否把 CRC 本身也算進去。

### 7.4 Adler-32（RFC 1950，zlib 格式用）

```c
uint32_t adler32(const uint8_t *p, size_t n) {    // "123456789" → 0x091E01DE
    uint32_t a = 1, b = 0;                        // s1 初值 1，s2 初值 0
    while (n) {
        size_t blk = n < 5552 ? n : 5552;          // RFC：取模可延遲 5552 byte 不溢位
        n -= blk;
        while (blk--) { a += *p++; b += a; }
        a %= 65521u; b %= 65521u;                  // 65521 = 小於 2^16 的最大質數
    }
    return (b << 16) | a;                         // 存放時 MSB first
}
```

延遲取模：把 n 次 `%` 降成 n/5552 次（Hazard3 上省很多 `rem`）。比 CRC 快但錯誤偵測較弱（短訊息尤其差）。Python：`zlib.adler32`。

### 7.5 FNV-1a（非加密雜湊，hash table 字串 key 常用）

```c
uint32_t fnv1a32(const uint8_t *p, size_t n) {    // "123456789" → 0xBB86B11C；空字串 → 0x811C9DC5
    uint32_t h = 2166136261u;                     // offset basis 0x811C9DC5
    while (n--) { h ^= *p++; h *= 16777619u; }    // FNV prime 0x01000193；先 xor 再乘（FNV-1 相反）
    return h;
}
// 64-bit：offset 0xCBF29CE484222325、prime 0x00000100000001B3
```

不可用於安全用途（可被刻意製造碰撞）。整數 key 用 §4.2 的乘法雜湊即可。

### 7.6 RLE、delta、varint、ZigZag、base64

Run-length encoding（`(count, value)` 配對，count ≤ 255）：

```c
size_t rle_enc(const uint8_t *in, size_t n, uint8_t *out) {      // out 最壞 2n
    size_t o = 0;
    for (size_t i = 0; i < n; ) {
        uint8_t v = in[i]; size_t run = 1;
        while (i + run < n && in[i + run] == v && run < 255) run++;
        out[o++] = (uint8_t)run; out[o++] = v; i += run;
    }
    return o;
}
// {5,5,5,1,1,9,9,9,9,9} → {3,5, 2,1, 5,9}
```

格式（count 在前或後、最大 run、是否有 literal 模式）完全依題目規格；**不同 RLE 變體互不相容**。

Delta encoding：`d[0] = x[0]; d[i] = x[i] - x[i-1]`；解碼為 prefix sum。緩變訊號（溫度、時間戳）的差值小 → 配合 varint 大幅壓縮。用無號運算做差（模 2^32 自然 wrap）可避免有號溢位 UB。

Varint（Protocol Buffers base-128）：每 byte 低 7 bit 放資料、**低位群組先**，最高位（MSB）= 1 表示後面還有。uint32 最多 5 byte、uint64 最多 10 byte。例：150 → `96 01`。

```c
size_t varint_enc(uint32_t v, uint8_t *out) {
    size_t i = 0;
    while (v >= 0x80) { out[i++] = (uint8_t)(v | 0x80); v >>= 7; }
    out[i++] = (uint8_t)v;
    return i;
}
size_t varint_dec(const uint8_t *in, size_t n, uint32_t *v) {    // 回傳用掉的 byte 數，0 = 錯誤
    uint32_t r = 0;
    for (size_t i = 0; i < n && i < 5; i++) {
        r |= (uint32_t)(in[i] & 0x7F) << (7 * i);
        if (!(in[i] & 0x80)) { *v = r; return i + 1; }
    }
    return 0;                                                     // 截斷或超過 5 byte
}
// ZigZag（有號 → 無號，小絕對值 → 小數字）：0→0, -1→1, 1→2, -2→3
static inline uint32_t zigzag32(int32_t x)    { return ((uint32_t)x << 1) ^ (uint32_t)(x >> 31); }  // x>>31 依賴算術右移（GCC 定義）
static inline int32_t  unzigzag32(uint32_t z) { return (int32_t)(z >> 1) ^ -(int32_t)(z & 1); }
```

Base64（RFC 4648）：每 3 byte → 4 字元（`A–Z a–z 0–9 + /`），不足補 `=`。輸出長度 = 4·⌈n/3⌉。例：`"foobar"` → `Zm9vYmFy`、`"fo"` → `Zm8=`、`"f"` → `Zg==`。URL-safe 變體用 `-` `_`。Python：`base64.b64encode`。

---

## 8. 位元層級演算法（演算法用途；基本技巧見 `riscv-hazard3.md` §8）

`riscv-hazard3.md` §8.2 已有：2 的冪判斷、最低位 1、`ctz`/`clz`、floor(log2)、向上取 2 的冪、對齊、popcount（SWAR）、parity、bswap、bit reverse、rotate、零 byte 偵測。以下只補「演算法上的用法」。

| 用途 | 做法 | 說明 |
|---|---|---|
| 走訪所有被設的位元 | `while (x) { i = ctz(x); ...; x &= x - 1; }` | 迭代次數 = popcount，不是 32 |
| 枚舉 mask 的所有子集 | `for (s = mask; ; s = (s - 1) & mask) { ...; if (s == 0) break; }` | 包含空集合；共 2^popcount(mask) 個 |
| 枚舉所有 n 元素子集 | `for (m = 0; m < (1u << n); m++)` | n ≤ 31；O(2ⁿ) |
| 小集合的集合運算 | 交 `&`、聯 `\|`、差 `a & ~b`、對稱差 `^`、包含 `(a & b) == a` | 32/64 個元素一次 |
| Gray code | `g = b ^ (b >> 1)` | 相鄰值只差 1 bit（編碼器、跨時脈計數器） |
| Gray 反轉 | `g ^= g>>1; g ^= g>>2; g ^= g>>4; g ^= g>>8; g ^= g>>16;` | 結果即二進位 |
| 下一個 2 的冪 / log2 | 見 `riscv-hazard3.md` §8.2 | hash 表大小、buffer 大小取整 |
| 二進位長度（bit 數） | `x ? 32 - __builtin_clz(x) : 0` | varint 長度估算：`(bits + 6) / 7`（x=0 時 1 byte） |
| parity 查表 | 8-bit 256 項表，或 `__builtin_parity` | 序列協定奇偶位 |
| 快速 byte 查表合成 32-bit 結果 | 4 次 8-bit 查表後組合 | bit reverse、popcount 沒有硬體指令時 |
| 位元交錯（Morton / Z-order） | 分散 x、y 的 bit 再 OR | 2-D 資料的 cache 友善排列 ⚠️ 少見 |

位元流打包（bit writer，MSB first）：

```c
typedef struct { uint8_t *buf; size_t pos; uint32_t acc; int nbits; } bw_t;
void bw_put(bw_t *w, uint32_t v, int n) {            // 寫入 v 的低 n bit（n <= 32）
    for (int i = n - 1; i >= 0; i--) {
        w->acc = (w->acc << 1) | ((v >> i) & 1u);
        if (++w->nbits == 8) { w->buf[w->pos++] = (uint8_t)w->acc; w->acc = 0; w->nbits = 0; }
    }
}
void bw_flush(bw_t *w) {                              // 不足 8 bit 以 0 補在低位
    if (w->nbits) { w->buf[w->pos++] = (uint8_t)(w->acc << (8 - w->nbits)); w->acc = 0; w->nbits = 0; }
}
// put(0b101,3) put(0b11111,5) put(0b11,2) flush → 0xBF 0xC0
```

逐 bit 版易懂但慢；加速版：用 32/64-bit 累加器一次塞 n bit，滿 8 bit 才吐出。位元順序（MSB/LSB first）、欄位排列以規格為準；欄位的 get/set 寫法見 `riscv-hazard3.md` §8.1。

---

## 9. 圖與搜尋（用陣列實作）

### 9.1 圖的表示（固定陣列）

| 表示 | 記憶體 | 走訪鄰居 | 適用 |
|---|---|---|---|
| 鄰接矩陣 `uint8_t adj[V][V]`（或 bitset） | V² | O(V) | V ≤ 幾百、稠密 |
| 鄰接串列（前向星 / 陣列鏈） `head[V]`、`nxt[E]`、`to[E]` | V + E | O(deg) | 一般 |
| CSR（`off[V+1]`、`adj[E]`） | V + E | O(deg)，連續 | 靜態圖、最快走訪 |
| 格子圖 | 不需存邊 | 4/8 方向 `dr[]`、`dc[]` | 地圖、影像 |

```c
// 前向星：加邊 u→v
static int head[V], nxt[E], to[E], ecnt;     // head 初始化為 -1
void add_edge(int u, int v) { to[ecnt] = v; nxt[ecnt] = head[u]; head[u] = ecnt++; }
// for (int k = head[u]; k != -1; k = nxt[k]) { int v = to[k]; ... }
```

注意：前向星走訪鄰居的順序是**加入順序的反向**。原程式若依鄰接順序輸出（DFS 順序、BFS 平手時），要保持一致（改用 CSR 依原順序）。

### 9.2 BFS（無權最短路，陣列佇列）

```c
// 格子 BFS：'#' 為牆；回傳 (sr,sc)→(tr,tc) 的步數，不可達 -1
int bfs_grid(const char g[H][W + 1], int sr, int sc, int tr, int tc) {
    static int16_t dist[H][W];
    static uint16_t q[H * W];                   // 每格最多入佇列一次 → 容量 H*W 足夠
    int qh = 0, qt = 0;
    for (int r = 0; r < H; r++) for (int c = 0; c < W; c++) dist[r][c] = -1;
    dist[sr][sc] = 0; q[qt++] = (uint16_t)(sr * W + sc);
    static const int dr[4] = {-1, 1, 0, 0}, dc[4] = {0, 0, -1, 1};
    while (qh < qt) {
        int cur = q[qh++], r = cur / W, c = cur % W;
        if (r == tr && c == tc) return dist[r][c];
        for (int d = 0; d < 4; d++) {
            int nr = r + dr[d], nc = c + dc[d];
            if (nr < 0 || nr >= H || nc < 0 || nc >= W) continue;
            if (g[nr][nc] == '#' || dist[nr][nc] >= 0) continue;
            dist[nr][nc] = dist[r][c] + 1;      // 入佇列時就標記，避免重複入隊
            q[qt++] = (uint16_t)(nr * W + nc);
        }
    }
    return -1;
}
```

- 「出佇列時才標記」會讓同一格入隊多次 → 佇列爆掉或變慢，常見 bug。
- 0-1 BFS（邊權只有 0/1）：用 deque，權 0 推前、權 1 推後。

### 9.3 DFS（避免遞迴爆 stack）

MCU stack 很小（pico-sdk 預設 `PICO_STACK_SIZE = 0x800`，每核心 2 KB，見 `pico-sdk.md` §2.1），深遞迴會默默覆蓋記憶體。改用顯式 stack 陣列：

```c
int stk[V], sp = 0; stk[sp++] = src; visited[src] = 1;
while (sp) {
    int u = stk[--sp];
    for (int k = head[u]; k != -1; k = nxt[k])
        if (!visited[to[k]]) { visited[to[k]] = 1; stk[sp++] = to[k]; }   // 入堆疊時標記 → 最多 V 個
}
```

注意此寫法的走訪順序和遞迴 DFS 不同（前序序列可能不同）。若輸出依賴 DFS 順序，要模擬遞迴（stack 存 `(u, 下一條邊索引)`）。

### 9.4 Dijkstra（非負權，binary heap + lazy deletion）

```c
typedef struct { uint32_t d; int v; } hn_t;          // heap 節點：距離、頂點
// heap 操作同 §3.4，比較 .d；容量需 ≥ E+1（lazy deletion 同一頂點可能多次入堆）
void dijkstra(int n, int src, uint32_t *dist) {
    for (int i = 0; i < n; i++) dist[i] = UINT32_MAX;
    dist[src] = 0; heap_push_n((hn_t){0, src});
    while (heap_size() > 0) {
        hn_t t = heap_pop_n();
        if (t.d != dist[t.v]) continue;               // 過期的項目，跳過
        for (int k = head[t.v]; k != -1; k = nxt[k]) {
            uint32_t nd = t.d + w[k];                 // 確認不會溢位（權重 × 邊數 < 2^32）
            if (nd < dist[to[k]]) { dist[to[k]] = nd; heap_push_n((hn_t){nd, to[k]}); }
        }
    }
}
```

- O((V + E) log E)。V 很小（≤ 幾百）且稠密 → O(V²) 陣列版（每輪線性找最小）反而簡單快速。
- 負權邊 → Dijkstra 錯，要 Bellman-Ford（O(VE)）。
- 「無限大」用 `UINT32_MAX` 時，`INF + w` 會 wrap → 先判斷 `dist[u] != INF`。
- 平手（多條等長路徑）時前驅節點的選擇和原程式可能不同 → 若輸出路徑要比對。

### 9.5 拓撲排序（Kahn）

```c
// 計算入度 → 入度 0 的放佇列 → 逐一取出、把鄰居入度 -1、變 0 就入佇列
// 輸出數量 < n 表示有環
int topo(int n, int *order) {
    int indeg[V] = {0}, q[V], qh = 0, qt = 0, cnt = 0;
    for (int u = 0; u < n; u++) for (int k = head[u]; k != -1; k = nxt[k]) indeg[to[k]]++;
    for (int i = 0; i < n; i++) if (indeg[i] == 0) q[qt++] = i;
    while (qh < qt) {
        int u = q[qh++]; order[cnt++] = u;
        for (int k = head[u]; k != -1; k = nxt[k]) if (--indeg[to[k]] == 0) q[qt++] = to[k];
    }
    return cnt;                                      // == n 才是合法拓撲序
}
```

拓撲序不唯一；要「字典序最小」→ 佇列換成 min-heap。用途：任務 / 依賴排程、DAG 上的 DP（最長路徑）。

### 9.6 Union-Find（路徑壓縮 + union by rank）

```c
#define UF_N 1024
static int parent[UF_N]; static uint8_t rnk[UF_N];
void uf_init(int n) { for (int i = 0; i < n; i++) { parent[i] = i; rnk[i] = 0; } }
int uf_find(int x) {                                  // 非遞迴 + 完整路徑壓縮
    int r = x; while (parent[r] != r) r = parent[r];
    while (parent[x] != r) { int nx = parent[x]; parent[x] = r; x = nx; }
    return r;
}
bool uf_union(int a, int b) {                         // 回傳是否真的合併（原本不同集合）
    a = uf_find(a); b = uf_find(b);
    if (a == b) return false;
    if (rnk[a] < rnk[b]) { int t = a; a = b; b = t; }
    parent[b] = a;
    if (rnk[a] == rnk[b]) rnk[a]++;
    return true;
}
```

兩者合用，m 次操作 O(m·α(n))（α 為反 Ackermann，實務上 ≤ 4）。用途：連通分量計數、Kruskal 最小生成樹、影像連通區域標記（取代遞迴 flood fill）、判斷加邊是否成環。

### 9.7 DP 基礎

0/1 背包（容量 W，一維滾動）：

```c
int dp[WMAX + 1] = {0};                     // dp[c] = 容量 c 的最大價值
for (int i = 0; i < n; i++)
    for (int c = W; c >= w[i]; c--)         // 倒序：每個物品只用一次（正序 = 無限背包）
        if (dp[c - w[i]] + v[i] > dp[c]) dp[c] = dp[c - w[i]] + v[i];
// O(nW) 時間、O(W) 空間
```

最長嚴格遞增子序列（LIS），O(n log n)：

```c
int lis_strict(const int32_t *a, int n) {   // tails[k] = 長度 k+1 的遞增子序列的最小結尾
    static int32_t tails[MAXN]; int len = 0;
    for (int i = 0; i < n; i++) {
        size_t pos = lower_bound(tails, (size_t)len, a[i]);   // 非遞減（可相等）版改用 upper_bound
        tails[pos] = a[i];
        if ((int)pos == len) len++;
    }
    return len;                             // {3,1,4,1,5,9,2,6,5,3,5} → 4
}
```

`tails` 本身**不是**一個合法的 LIS；要還原序列需另存每個元素的前驅索引。

DP 優化思路：(1) 找出狀態與轉移；(2) 只依賴上一列 → 滾動陣列；(3) 轉移是「區間最小 / 最大」→ monotonic deque / sparse table；(4) 狀態太多 → 檢查是否有不可能的狀態可剪掉。

---

## 10. 數值技巧

### 10.1 快速冪（含取模）

```c
uint32_t powmod(uint32_t b, uint32_t e, uint32_t m) {   // m >= 1
    uint64_t r = 1 % m, x = b % m;                       // 中間乘積用 64 bit（< 2^64）
    while (e) { if (e & 1) r = r * x % m; x = x * x % m; e >>= 1; }
    return (uint32_t)r;
}
// powmod(2,10,1000000007) = 1024
```

O(log e)。同一思路適用矩陣快速冪（線性遞迴第 n 項）、重複套用同一變換。注意 `uint64 % m` 在 RV32 是軟體函式（`__umoddi3`），很慢 ⚠️估計；能用 2 的冪模數或 Montgomery 就更快，但考場通常不需要。

### 10.2 GCD

```c
uint32_t gcd_u32(uint32_t a, uint32_t b) { while (b) { uint32_t t = a % b; a = b; b = t; } return a; }

// Binary GCD（Stein）：只用 shift / 減法 / ctz，無除法 → 適合 Hazard3（div 18～19 cycle，ctz 1 cycle）
uint32_t gcd_bin(uint32_t a, uint32_t b) {
    if (a == 0) return b;
    if (b == 0) return a;
    int s = __builtin_ctz(a | b);                // 共同的 2 的次方
    a >>= __builtin_ctz(a);
    do {
        b >>= __builtin_ctz(b);
        if (a > b) { uint32_t t = a; a = b; b = t; }
        b -= a;
    } while (b);
    return a << s;
}
// lcm(a,b) = a / gcd(a,b) * b   （先除再乘，避免溢位）
```

### 10.3 整數平方根（floor(√x)，無浮點）

```c
uint32_t isqrt32(uint32_t x) {                   // 逐位元法，16 次迭代；isqrt32(0xFFFFFFFF) = 65535
    uint32_t r = 0, bit = 1u << 30;
    while (bit > x) bit >>= 2;
    while (bit) {
        if (x >= r + bit) { x -= r + bit; r = (r >> 1) + bit; }
        else r >>= 1;
        bit >>= 2;
    }
    return r;
}
```

比較距離時**根本不用開根號**：`dx*dx + dy*dy < R*R`（用 `int64_t` 防溢位）。Python：`math.isqrt`（3.8+）。

### 10.4 避免除法與取模

| 情況 | 做法 | 條件 / 陷阱 |
|---|---|---|
| 除 / 模 2^k（無號） | `x >> k`、`x & (2^k - 1)` | 有號負數 `x / 4 ≠ x >> 2`（前者朝 0 取整）、`x % 4` 可能為負 |
| 除以編譯期常數 | 直接寫 `x / 10`，`-O2` 會轉成乘法 + 右移 | 不要手寫，除非看過 objdump 發現沒轉；例：`(uint32_t)(((uint64_t)x * 0xCCCCCCCDu) >> 35) == x / 10` 對所有 uint32 成立（主機實測） |
| 迴圈中除以同一執行期變數 d | 預先算倒數（定點）或改寫成乘法比較 | 正確性要證明（或改用浮點倒數後再修正一步）；不確定就不做 ⚠️ |
| 比較分數 `a/b < c/d` | `a*d < c*b`（b, d > 0，用 int64） | 交叉相乘避免除法與取整誤差（但結果可能和原本「先整數除再比」不同！） |
| ring 索引 `% N` | N = 2^k 用 mask；否則 `if (++i == N) i = 0;` | — |
| 迴圈中 `i % k == 0` | 另一個計數器倒數到 0 再重設 | — |
| 平均值 `(a + b) / 2` | `a + (b - a) / 2` 或 `(a & b) + ((a ^ b) >> 1)`（無號） | 防溢位 |
| 時間 / 單位換算 | 選 2 的冪單位（例如 1/1024 秒）或預乘常數 | 輸出格式要求十進位時仍要換回 |
| 浮點除法 | 乘以倒數常數 `x * (1.0f / 3.0f)` | 浮點結果可能差 1 ulp，與原輸出不逐位元相同 |

定點數（Q 格式、乘法後右移、飽和）細節見 `control-dsp.md`；RP2350 上的 float / double 成本見 `pico-sdk.md` §7.7。

---

## 11. Cache / 記憶體友善的選擇

| 原則 | 說明 |
|---|---|
| 陣列 > 鏈結結構 | 連續存取可預取、無指標追逐；鏈結串列每個節點可能一次 cache miss |
| SoA vs AoS | 只用到部分欄位的熱迴圈 → SoA（`float x[N], y[N]`）只讀需要的資料，也較容易向量化；每次都用整筆 → AoS |
| 循序走訪 | 二維陣列 `a[i][j]` 內層迴圈跑 j（row-major）；反過來跑會跨步存取 |
| Blocking / tiling | 矩陣乘、轉置分成小塊讓工作集放進 cache（詳見 `c-linux-perf.md`） |
| 縮小資料型別 | 能用 `uint8_t`/`int16_t` 就不用 `int64_t`：同樣 cache / SRAM 放更多（但運算可能要加寬防溢位） |
| 索引取代指標 | `uint16_t` 索引比 32/64-bit 指標小，也方便放進固定陣列 |
| 熱 / 冷分離 | 常用欄位集中在一個結構，罕用欄位另放 |
| RP2350 | SRAM 本身不經 data cache；瓶頸常在 XIP flash（16 KB cache）→ 熱程式與熱表放 SRAM；雙核 / DMA 同時打同一 SRAM bank 會互搶（`pico-sdk.md` §8、`multicore-sync.md` §B9） |

---

## 12. Python 速查（若題目程式是 Python）

| 慢寫法 | 替代 | 備註（官方 time-complexity 表） |
|---|---|---|
| `x in list`（迴圈內） | 先建 `set(list)` | list O(n) → set 平均 O(1) |
| `list.pop(0)` / `insert(0, x)` | `collections.deque` | list O(n−k)；deque 兩端 O(1) |
| 手寫計數 dict | `collections.Counter` | |
| 每次 `sorted()` 後取前 k | `heapq.nsmallest/nlargest(k, ...)` | O(n log k) |
| 線性找插入位置 | `bisect.bisect_left` | 搜尋 O(log n)；`insort` 插入仍 O(n) |
| 字串 `s += t` 迴圈 | `''.join(parts)` | 反覆串接可能 O(n²) |
| 手寫 prefix sum 迴圈 | `itertools.accumulate` | |
| 遞迴重算 | `functools.cache` / `lru_cache` | 注意遞迴深度上限 |
| 逐 bit 數 1 | `int.bit_count()`（3.10+）、`int.bit_length()` | |
| `x**e % m` | `pow(x, e, m)` | 三參數 pow 內建模冪 |
| 浮點開根號取整 | `math.isqrt` | 大整數也精確 |
| 手寫 CRC-32 / Adler | `zlib.crc32`、`zlib.adler32`、`binascii.crc_hqx` | C 實作，快很多 |
| 數值大迴圈 | 若環境有 NumPy 才向量化；考場不能裝套件 ⚠️ | 先確認可用 |
| 全域變數在熱迴圈 | 綁成區域變數（`f = obj.method`） | 屬性 / 全域查找較慢 |

---

## 13. 嵌入式（無 malloc）實作規則

1. 所有容量用 `#define` 常數，並加 `_Static_assert` 檢查（2 的冪、夠大）。
2. 大陣列宣告為 `static`（或全域），不要放 stack（MCU stack 小）。
3. 每個 push / insert 都有「滿了怎麼辦」的分支，行為和原程式一致（丟棄 / 覆蓋 / 回報錯誤）。
4. 索引型別：容量 ≤ 65535 用 `uint16_t` 省記憶體；迴圈變數用 `uint32_t`/`size_t` 避免反覆截斷。
5. 遞迴改迭代（DFS、quicksort 的大段用迴圈、小段遞迴），或確定深度上界。
6. 查表 `const`；熱表放 SRAM（`__not_in_flash`）；冷表留 flash。
7. 初始化成本（建 CRC 表、建 hash 表）放在計時區外 —— 但先確認題目計分是否包含初始化。
8. 跨 ISR / 跨核共享的結構（ring、pool）要有同步（`multicore-sync.md`）。

---

## 14. 證明「優化版輸出完全相同」的檢查清單

| 項目 | 要檢查的事 |
|---|---|
| Golden output | 先用**原程式**對一批輸入產生輸出存檔；之後每改一次就 `diff` / `cmp`（流程見 `03-optimize.md` §5） |
| 對拍（random test） | 寫產生器隨機產生輸入，原版與新版各跑一次比較，跑幾千組；發現不同就縮小輸入找最小反例 |
| 空輸入 / n = 0 | `n - 1` 對 `size_t` 下溢；二分 / 雙指標起始值 |
| n = 1、n = 2 | 視窗 w > n、`i < j` 迴圈不進入 |
| 最大 n | 陣列容量、佇列容量（BFS 佇列、heap 容量 ≥ E+1）、stack 深度 |
| 溢位 | 和、乘積、平方距離、prefix sum 用加寬型別；`INF + w`；`a - b` 比較函式 |
| 有號 / 無號 | `x >> k` vs `x / 2^k` 對負數不同；`%` 結果符號；比較時隱式轉型 |
| Tie / 重複值 | 排序穩定性（`qsort` 不穩定）、heap 彈出順序、top-k 同分取誰、argmin 取第一個還是最後一個、Dijkstra 前驅 |
| 走訪順序 | hash 表走訪 ≠ 插入順序；前向星鄰居反序；迭代 DFS ≠ 遞迴 DFS 順序 |
| 浮點 | 結合律不成立：重排加法順序（running sum、平行化、展開多累加器）會改變最後幾位；乘倒數 ≠ 除法；要求逐位元相同就不要動浮點運算順序 |
| 整數除法取整 | 平均值、縮放：C 朝 0 截斷；`>>` 朝負無限大 |
| 邊界條件 | 半開 vs 閉區間（`[l, r)` vs `[l, r]`）、`<` vs `<=`（lower vs upper bound） |
| 副作用 | 原程式會修改輸入陣列嗎？新版（quickselect、原地排序）會不會多改了？ |
| 未找到 | 找不到時原程式回傳 -1？n？最後一個？新版必須相同 |
| CRC / 編碼 | 對 check value（`"123456789"`）和原程式輸出各比一次；byte 順序 |
| 時間量測 | 新版的確較快：量測多次取中位數，計時範圍與題目一致（`03-optimize.md` §2） |

---

## 15. 除錯清單

| 症狀 | 可能原因 | 檢查 |
|---|---|---|
| 二分搜尋卡住 | `lo = mid`、閉區間 + 無號下溢 | 改半開模板 |
| hash 表越來越慢 / 卡死 | α 太高、全部撞同一槽（取低位、key 有規律）、表滿無限探測 | 印探測次數；改乘法雜湊取高位；探測上限 |
| hash 找不到剛插入的 key | 刪除時直接設 EMPTY 切斷探測鏈；find 與 insert 雜湊不同 | tombstone；同一 hash 函式 |
| ring buffer 資料錯位 / 遺失 | N 不是 2 的冪卻用 mask；滿 / 空判斷；ISR 競爭 | `_Static_assert`；atomic |
| heap 輸出順序錯 | sift-down 沒比兩個子節點；`n` 先減後讀錯位 | 小資料手動跑 |
| CRC 不對 | init / 反射 / xorout / byte 序 / 範圍 | 先對 `"123456789"` check value |
| radix sort 結果錯 | 趟數為奇數導致結果在 tmp；有號數沒轉換 | 4 趟；`^ 0x80000000` |
| BFS 很慢 / 佇列溢位 | 出隊時才標記 | 入隊時標記 |
| 遞迴程式在 MCU 當機 | stack overflow | 改迭代 |
| prefix sum 結果錯 | P 長度 n 而非 n+1；off-by-one；溢位 | 半開公式 `P[r]-P[l]` |
| 滑動視窗前幾個輸出錯 | `i >= w - 1` 條件；w > n | 對拍暴力 |
| 優化後偶爾不同 | tie 順序、浮點順序、未初始化記憶體 | §14；`-fsanitize=address,undefined`（主機） |
| 優化後反而變慢 | 表太大 cache miss、n 太小固定成本高、`qsort` 函式指標、64-bit 除法軟體實作 | 量測、看 objdump |

---

## 16. 優化清單（依收益大致排序）

1. [ ] 量測找出熱點（`03-optimize.md`）；確認熱點是「演算法」問題（時間隨 n 超線性成長）。
2. [ ] 找巢狀迴圈與重算：能否 hash / 排序 + 二分 / prefix sum / running sum / 雙指標？
3. [ ] 只要部分結果？（top-k、第 k 小、存在與否、提早結束 `break`）
4. [ ] 資料結構：鏈結 → 陣列；線性搜尋 → 直接索引 / hash；`bool[]` → bitset。
5. [ ] 排序：小 n 用 insertion；小整數鍵用 counting / radix；`qsort` 換專用比較。
6. [ ] 預先計算：LUT、CRC 表、常數外提出迴圈；初始化與熱迴圈分開。
7. [ ] 去掉熱迴圈中的 `%` `/` 浮點 `printf` `malloc`。
8. [ ] 記憶體佈局：SoA、縮小型別、熱表放 SRAM、循序存取。
9. [ ] 再考慮平行 / 硬體卸載（DMA、第二核、PIO：見各 domain 檔）與微優化（`riscv-hazard3.md` §9）。
10. [ ] 每一步都跑 §14 對拍，通過才提交；記錄前後時間。

---

## 17. 向模型提問的範本

### 17.1 找演算法瓶頸

```text
以下是題目程式的熱點函式（語言：{{C / Python}}，平台：{{Linux 主機 / RP2350 Hazard3 @150MHz}}）：
{{貼程式碼}}
輸入規模：n = {{...}}，查詢數 q = {{...}}，資料特性：{{是否已排序 / 值域範圍 / 是否有重複}}。
請：(1) 標出時間複雜度與主要成本所在行；(2) 從「hash / 排序+二分 / prefix sum / 滑動視窗 / heap / 查表」中提出可行的替代，
寫出新複雜度；(3) 列出新寫法可能和原程式輸出不同的情況（tie、順序、溢位、浮點）。先不要寫完整程式。
```

### 17.2 改寫成嵌入式友善版本

```text
請把下面的 {{資料結構 / 演算法}} 改寫成 C11，限制：不使用 malloc、所有容量為編譯期常數 {{MAX_N = ...}}、
索引用 uint32_t、熱路徑不使用 % 和浮點、容量用 2 的冪並加 _Static_assert。
滿了時的行為必須和原程式一樣：{{丟棄 / 覆蓋 / 回傳錯誤}}。
原程式：
{{貼程式碼}}
請一併給出一個主機上可跑的對拍 main()：隨機產生 {{數量}} 組輸入，比較新舊版本輸出。
```

### 17.3 CRC / 檢查碼參數確認

```text
題目規格寫：{{貼規格原文，例如 polynomial、初值、是否反射、輸出 xor、byte 順序}}。
請對照 reveng CRC catalogue 判斷這是哪一個 CRC（名稱、width、poly、init、refin、refout、xorout、check），
並寫出 {{bitwise / 256 表 / slicing-by-4}} 版本的 C 實作。
用 "123456789" 的 check value 自我驗證；原程式對輸入 {{hex bytes}} 的輸出是 {{值}}，也要一致。
```

### 17.4 確認優化等價

```text
原版：
{{貼原程式}}
優化版：
{{貼新程式}}
請逐項檢查兩者對所有輸入是否輸出完全相同：空輸入、n=1、最大 n={{...}}、重複值與平手、負數、
溢位（型別 {{...}}）、浮點運算順序、找不到時的回傳值、是否修改輸入。
對每個可能不同的情況給出一個具體反例輸入；若確定相同，說明理由。
```

### 17.5 選排序 / 選擇演算法

```text
需要對 {{n}} 筆 {{型別，例如 uint16_t 感測值 / struct {key, id}}} 做 {{全排序 / 取前 k={{...}} / 取中位數}}，
{{需要 / 不需要}} 穩定，平台 {{...}}，可用額外記憶體 {{... KB}}。原程式用 {{qsort / 泡沫排序 / ...}}。
請比較 insertion / qsort / counting / radix / heap / quickselect 在這個情況下的預期成本，
推薦一個並寫出 C 實作，說明 tie 的處理如何與原程式保持一致。
```
