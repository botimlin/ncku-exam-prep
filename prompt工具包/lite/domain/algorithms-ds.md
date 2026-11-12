# 演算法與資料結構速查（效能優化）

- 用途：備援 pack；換演算法 / 資料結構的精簡參考
- 適用版本：C11（GCC）、Python 3、Linux 或 RP2350 @150 MHz
- 來源：reveng.sourceforge.io/crc-catalogue ；RFC 1950、4648 ；draft-eastlake-fnv ；protobuf.dev encoding ；cppreference qsort/sort/nth_element ；docs.python.org/3/builtins/time-complexity.html
- 最後更新：2026-11（詳版 full/domain/algorithms-ds.md）

## 1 秒可行 n（⚠️估計）
| | 主機 | RP2350 |
|---|---|---|
| O(n) | 1e8 | 1e7 |
| O(n log n) | 1e7 | 1e6 |
| O(n²) | 1e4 | 3e3 |
Hazard3：div/rem 18～19 cycle、mul 1、無 FPU；熱表放 SRAM（XIP cache 16 KB）

## 慢 → 快
- 雙層迴圈找配對 → hash / 排序+lower_bound / 雙指標
- 重算視窗和 → running sum；視窗 min/max → monotonic deque
- 多次區間和 → prefix sum `P[r]-P[l]`（P 長 n+1、int64）；2-D：`P[r2][c2]-P[r1][c2]-P[r2][c1]+P[r1][c1]`
- 多次區間加 → difference array；靜態 RMQ → sparse table（僅 min/max/gcd/&/|）
- `%N` → N=2^k 用 `&(N-1)`，或 `if(++i==N)i=0`
- 全排序取前 k → size-k heap O(n log k)；第 k 小 → quickselect O(n) 平均
- 小整數鍵 → counting/radix O(n)；n≤16 或近排序 → insertion
- 逐 bit CRC → 256 表；`bool[]` → bitset + `ctz` 走訪
- 鏈結串列 → 陣列 + 索引；malloc → 固定 pool/free list
- 比距離 → 比平方（int64）；`pow` 迴圈 → 快速冪

## 結構要點
- Ring：`uint32_t head,tail` 持續遞增，`count=head-tail`，滿 `==N`，取用 `buf[i&(N-1)]`；跨 ISR/核 → multicore-sync.md §A11
- Heap：父 `(i-1)/2`、子 `2i+1,2i+2`；heapify O(n)；不穩定 → key 加序號
- Hash：open addressing + linear probing，α≤0.7；`(k*2654435769u)>>(32-bits)` 取高位；刪除用 tombstone；走訪≠插入順序
- lower_bound 半開模板：`lo=0,hi=n; while(lo<hi){mid=lo+(hi-lo)/2; if(a[mid]<x)lo=mid+1; else hi=mid;}`；upper_bound 改 `<=`；`bsearch` 有重複時不保證回傳第一個
- Bloom：誤報 ≈(1-e^(-kn/m))^k，最佳 k=(m/n)ln2，無漏報
- Union-find：路徑壓縮+union by rank ≈O(α(n))
- BFS：陣列佇列，**入隊時標記**；DFS 用顯式 stack（pico 預設 stack 2 KB）
- Dijkstra：heap + lazy deletion（`if(d!=dist[v])continue`），容量 ≥E+1；負權不可
- Kahn 拓撲：輸出 <n 表有環；LIS：tails + lower_bound O(n log n)
- 0/1 背包：容量倒序迴圈
- Monotonic deque（min）：`while(t>h&&a[dq[t-1]]>=a[i])t--; dq[t++]=i; if(dq[h]<=i-w)h++;` 輸出 `a[dq[h]]`
- LUT：256×u32=1 KB；64K×u16=128 KB（超過 XIP cache，放 flash 常 miss）

## 排序事實
- `qsort`：C/POSIX 不保證複雜度與穩定；比較用 `(a>b)-(a<b)`，勿 `a-b`
- `std::sort` C++11 起最壞 O(N log N)、不穩定；`nth_element` 平均 O(N)
- Python `sorted` 穩定；radix 有號先 `^0x80000000`

## CRC（check="123456789"）
| 名稱 | poly | init | ref | xorout | check |
|---|---|---|---|---|---|
| CRC-32/ISO-HDLC | 04C11DB7 | FFFFFFFF | T/T | FFFFFFFF | CBF43926 |
| CRC-16/IBM-3740 (=CCITT-FALSE) | 1021 | FFFF | F/F | 0 | 29B1 |
| CRC-16/XMODEM | 1021 | 0 | F/F | 0 | 31C3 |
| CRC-16/KERMIT | 1021 | 0 | T/T | 0 | 2189 |
| CRC-16/MODBUS | 8005 | FFFF | T/T | 0 | 4B37 |
| CRC-8/SMBUS | 07 | 0 | F/F | 0 | F4 |
- 反射版右移 + 反射多項式：EDB88320、A001
- CRC-32 表：`crc=(crc>>8)^T[(crc^b)&0xFF]`，前後 `~`；CRC-16 MSB：`crc=(crc<<8)^T[((crc>>8)^b)&0xFF]`
- Python：`zlib.crc32`、`binascii.crc_hqx(d,0xFFFF)`=CCITT-FALSE
- Adler-32：a=1,b=0，mod 65521，取模可延遲 5552 byte，結果 `b<<16|a`（"123456789"→091E01DE）
- FNV-1a 32：h=0x811C9DC5；`h^=b; h*=0x01000193`
- Varint：7 bit/byte、低位群組先、MSB=續；150→`96 01`；ZigZag `((uint32_t)n<<1)^(uint32_t)(n>>31)`

## 數值 / 位元
- powmod 中間值 uint64；binary GCD 用 ctz 免除法；isqrt 逐位元
- 常數除數交給編譯器；負數 `x/4≠x>>2`
- 子集枚舉 `s=(s-1)&mask`；Gray `b^(b>>1)`；其餘位元技巧見 riscv-hazard3.md §8

## 等價檢查
空/1/最大 n、溢位、有號移位、tie 與穩定性、走訪順序、浮點運算順序、找不到的回傳值、是否改輸入；舊版 golden + 隨機對拍 diff
