# algo/ — 上機考常見「計算題」預製程式碼

全部是 **純 C11**、用 `stdint.h` 型別、**核心函式不用 malloc**，電腦和 MCU（RP2350 的 Cortex-M33 或 Hazard3 RISC-V）都能直接編譯。
`*_test.c` 只在電腦上跑（測試 + 測速），**不要**放進 MCU 專案。
要改的地方都標了 `TODO(改這裡)`。

## 1. 看到什麼題目 → 用哪個檔案

| 題目關鍵字 | 檔案 | 主要函式 |
|---|---|---|
| CRC、CRC32、校驗、zlib、Ethernet、PNG | `crc32.c/.h` | `crc32_update(0, buf, n)` |
| 題目給一組 CRC 參數（poly/init/refin/refout/xorout）| `crc32.c/.h` | `crc_generic(&param, buf, n)`，參數表在 `crc32.h` |
| CRC-32C / CRC-16 / Modbus / XMODEM | `crc32.c/.h` | `crc32c_update`、`crc16_ccitt_false`、`crc_generic` |
| SHA-0、SHA-1、雜湊 | `sha1_sha0.c/.h` | `sha0(buf,n,out)`、`sha1(buf,n,out)` |
| SHA-256 | `sha256.c/.h` | `sha256(buf,n,out)` |
| 排序、合併兩塊板子的結果 | `sort.c/.h` | `radix_sort_u32`、`merge_two_sorted`、`kway_merge` |
| eBNN、BNN、二值化神經網路、XNOR、popcount | `bnn.c/.h` | `bnn_pack`、`bnn_dot`、`bnn_dense_sign`、`bnn_argmax` |
| Adler-32、Fletcher、XOR/加總校驗、IP checksum | `checksum_misc.c` | 複製需要的函式即可 |

## 2. API 速查

```c
/* CRC-32（zlib 相容）——可分段算 */
crc32_init();                               // 開機一次（不呼叫也會自動建表）
uint32_t c = crc32_update(0, p1, n1);       // 第一段傳 0
c = crc32_update(c, p2, n2);                // 接著算
// 驗證：crc32_update(0,"123456789",9) == 0xCBF43926

/* 任意 CRC：照題目填參數 */
crc_param_t modbus = {16, 0x8005, 0xFFFF, 1, 1, 0x0000};
uint32_t r = crc_generic(&modbus, buf, n);  // "123456789" → 0x4B37

/* SHA-1 / SHA-0（串流：資料分多包收到時）*/
sha1_ctx s; sha1_init(&s, 1);               // 1 = SHA-0，0 = SHA-1
sha1_update(&s, pkt, len);  /* ...重複... */
uint8_t out[20]; sha1_final(&s, out);

/* 排序：tmp 由你提供（MCU 上用 static 陣列）*/
static uint32_t a[N], tmp[N], out[2*N];
radix_sort_u32(a, N, tmp);
merge_two_sorted(boardA, nA, boardB, nB, out);   // 兩塊板子各排一半 → 合併

/* BNN：一層 dense + BN 折成門檻 */
bnn_fold_bn(gamma, beta, mean, sqrtf(var+eps), bias, &thr[j], &flip[j]);  // 每個神經元一次
bnn_layer_t L1 = { n_in, n_hid, W1, thr, flip };
bnn_pack(x_pm1, n_in, xbits);               // int8 ±1 → bits
bnn_dense_sign(&L1, xbits, hbits);          // 隱藏層 → bits
bnn_dense_score(&L2, hbits, score);         // 最後一層 → 整數分數
int cls = bnn_argmax(score, n_out);
```

## 3. 編譯與測試（輸出放 /tmp，不要留執行檔在這個資料夾）

```bash
B=/tmp/t; mkdir -p $B
gcc -O2 -Wall -Wextra -std=c11 crc32.c crc32_test.c        -o $B/crc && $B/crc
gcc -O2 -Wall -Wextra -std=c11 sha1_sha0.c sha256.c sha_test.c -o $B/sha && $B/sha
gcc -O2 -Wall -Wextra -std=c11 sort.c sort_test.c          -o $B/sort && $B/sort
gcc -O2 -Wall -Wextra -std=c11 bnn.c bnn_test.c            -o $B/bnn && $B/bnn
gcc -O2 -Wall -Wextra -std=c11 -DTEST_MAIN checksum_misc.c -o $B/ck  && $B/ck
# MCU 只編核心檔（不要編 *_test.c）：
arm-none-eabi-gcc -mcpu=cortex-m33 -mthumb -O2 -c crc32.c
```

## 4. 實測結果（2026-11-11，AMD Ryzen 5 5600，gcc 13.3，`-O2`）

**正確性：全部 PASS**（另外用 ASan/UBSan 跑過、SHA-0/SHA-1/SHA-256 也用 Python 獨立實作對 160 組隨機長度資料比對過，全一致）。
`arm-none-eabi-gcc -mcpu=cortex-m33 -mthumb -O2 -Wall -Wextra` 與 `riscv64-unknown-elf-gcc -march=rv32imac_..._zbb -mabi=ilp32`（pico-build Docker）6 個核心檔都 **0 警告編過**。

### CRC（4 MB 隨機資料）
| 版本 | 時間 | 速度 | 備註 |
|---|---|---|---|
| crc32_bitwise | 31.3 ms | 134 MB/s | 不用表，最省記憶體 |
| crc32_table | 7.6 ms | 554 MB/s | 1 KB 表，**4.1x** |
| crc32_slice4 | 2.5 ms | 1663 MB/s | 4 KB 表，**12.4x** |
| crc32c (table) | 7.6 ms | 554 MB/s | |
| crc16_ccitt_false (table) | 8.5 ms | 492 MB/s | |

### SHA（4 MB）
| 演算法 | -O2 | -O3 -march=native |
|---|---|---|
| SHA-1 | 8.7 ms（485 MB/s）| 8.3 ms（503 MB/s）|
| SHA-0 | 8.7 ms（485 MB/s）| 8.7 ms |
| SHA-256 | 35.0 ms（120 MB/s）| 15.2 ms（275 MB/s）|

### 排序（n = 1,048,576 個隨機 uint32，含一次 memcpy）
| 方法 | 時間 | 對 qsort |
|---|---|---|
| qsort（libc）| 95.9 ms | 1x |
| merge_sort_u32 | 55.6 ms | 1.7x |
| **radix_sort_u32** | **10.7 ms** | **9x** |
| 兩半各 radix + merge_two_sorted（單核）| 14.0 ms | 真的分兩核/兩板時 ≈ 一半 radix + 合併 |
| insertion n=10000 | 5.7 ms | radix n=10000 只要 0.05 ms → 大 n 別用 insertion |

### BNN（784 輸入 × 256 神經元 dense 一層）
| 編譯方式 | 每層時間 |
|---|---|
| `-O2`（`__builtin_popcount` 沒有硬體指令 → 呼叫函式）| 13.2 µs |
| `-O2 -DBNN_SWAR_POPCOUNT`（純 C 位元技巧）| 9.1 µs |
| `-O2 -march=native`（硬體 popcnt）| 4.2 µs |

→ **有硬體 popcount 就快 3 倍**。RP2350 的 Hazard3 有 Zbb `cpop`：用 `-march=..._zbb` 編，我用 objdump 確認 `bnn.o` 裡確實是 `cpop`。Cortex-M33 沒有 popcount 指令，建議加 `-DBNN_SWAR_POPCOUNT`（板子上的實際速度**尚未實測**）。

## 5. 考場上要改哪裡

- **CRC 規格不同**：先用 `crc_generic` 填參數，用 "123456789" 比對參數表的 check 值；確定後再換查表版的多項式（`crc32.c` 頂端的 `POLY32R`）。
- **RP2350 硬體 CRC**：DMA sniffer 可以邊搬邊算 CRC-32，幾乎不花 CPU；一定要用 `crc32_update` 的結果驗證硬體設定。
- **SHA 題目**：通常只要 `sha0()`/`sha1()` 一行；資料分包收 → 用 init/update/final。
- **排序要分給 2 塊板子/2 個核心**：各自 `radix_sort_u32` 一半 → 收回來 `merge_two_sorted`。有號數：先 `^= 0x80000000u`。
- **BNN**：把 `bnn_test.c` 範例網路的 `W1/W2/thr` 換成題目的權重，`N_IN/N_HID/N_OUT` 改尺寸。權重位元順序：第 i 個 → word i/32 的 bit i%32（若題目是 MSB 先，要自己轉）。
- **checksum_misc.c**：只複製需要的那一個函式。
