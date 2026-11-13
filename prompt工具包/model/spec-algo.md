# 規格卡：algo/（CRC、SHA-0/1/256、排序與合併、BNN、校驗碼）
> 用法（照 `../../考場SOP.md`）：模型寫【要卡】編號時，到 `../編號卡/` Ctrl-F 那個編號複製這張卡，包在 `<<<資料 開始>>>`…`<<<資料 結束>>>` 裡、最後一行寫「繼續」再貼。本檔編號：E04（規格卡 ALGO）。每張 ≤ 1200 字元。
> 來源：`預製程式碼/說明書/05-algo.md`、`預製程式碼/algo/` 程式碼（行號 2026-11-13 核對）｜最後更新 2026-11-13

---

【規格卡｜ALGO 1/9｜總覽：檔案、題型、驗證狀態】
以下是正確的參考資料（預製程式碼 2026-11-13 版）。和你的記憶不同時，以這張為準。
`預製程式碼/algo/`：純 C11、`stdint.h` 型別、核心檔不用 malloc，電腦和 RP2350（M33 / Hazard3）都能編。
| 檔案 | 行數 | 做什麼 |
|---|---|---|
| `crc32.c` / `.h` | 117 / 59 | CRC-32 三種實作、CRC-32C、CRC-16、通用 `crc_generic` |
| `sha1_sha0.c` / `.h` | 78 / 35 | SHA-1 與 SHA-0（同一份程式，旗標切換） |
| `sha256.c` / `.h` | 70 / 24 | SHA-256 |
| `sort.c` / `.h` | 78 / 34 | insertion、merge、radix、2 路 / k 路合併 |
| `bnn.c` / `.h` | 63 / 66 | BNN：打包、XNOR-popcount、門檻、argmax |
| `checksum_misc.c` | 106 | Adler-32、Fletcher-16、XOR、sum8、LRC、sum32、IP checksum（沒有 .h） |
| `*_test.c`、`test_util.h` | — | 只在電腦上跑（測試 + 測速），不要放進 Pico |
| `README.md` | 111 | 題型表、API 速查、編譯指令 |
題型 → 檔：CRC / zlib / poly / refin → crc32；SHA-0/1/256 / hash → sha*；排序、合併多板結果 → sort；eBNN / XNOR / popcount / BatchNorm → bnn；Adler / Fletcher / NMEA `*hh` / LRC / IP checksum → checksum_misc。
`TODO(改這裡)` 共 5 處：`crc32.c:10`（POLY32R）、`sort.c:6`（RUN）、`bnn_test.c:14`（範例網路）、`crc32_test.c:7`、`sort_test.c:7`（測速資料量）。
驗證：5 支測試在電腦上全 PASS（含 ASan/UBSan）、qemu-riscv32 全 PASS；M33 / rv32 交叉編譯 0 警告；pico-sdk 2.2.0 專案編譯連結通過。**沒有在實體 Pico 上跑過**，板上速度沒有實測。
要看程式：請操作者貼「cat -n README.md | sed -n 7,50p」

---

【規格卡｜ALGO 2/9｜crc32.c：函式、分段用法、選哪個】
以下是正確的參考資料（預製程式碼 2026-11-13 版）。和你的記憶不同時，以這張為準。
參數都是 `(crc, const uint8_t *p, size_t n)`。
| 函式 | crc32.c 行號 | 第一段的 crc | 注意 |
|---|---|---|---|
| `uint32_t crc32_bitwise` | 43-51 | 0 | zlib CRC-32；不用表；最慢 |
| `uint32_t crc32_table` | 54-59 | 0 | 1 KB 表 |
| `uint32_t crc32_slice4` | 62-75 | 0 | 4 KB 表；p 不用對齊 |
| `uint32_t crc32_update` | 77-79 | 0 | = slice4（最快） |
| `uint32_t crc32c_update` | 82-87 | 0 | CRC-32C |
| `uint16_t crc16_ccitt_false` | 90-94 | **0xFFFF** | 傳 0 = XMODEM |
| `uint32_t crc_generic(const crc_param_t *c, p, n)` | 103-117 | （用 c->init） | 任意規格，width 1..32；**不能分段** |
| `void crc32_init(void)` | 26-40 | — | constructor：main 前自動建表 |
分段（上表前 6 個）：`c = crc32_update(0, a, na); c = crc32_update(c, b, nb);` = 一次算 a+b（函式內開頭 `crc = ~crc`、結尾 `return ~crc`）。
常數：`POLY32R 0xEDB88320`（:10，TODO）、`POLY32CR 0x82F63B78`（:11）、`POLY16 0x1021`（:12）。
速度（電腦，4 MB）：bitwise 115.0 MB/s、table 484.8（4.2 倍）、slice4 1445.4（12.6 倍）、crc32c 488.6、crc16 353.9、crc_generic 28.3。
→ 要快用 `crc32_update`；`crc_generic` 用來對答案，或資料只有幾 KB 時用。
別的 refin=refout=1、init=xorout=0xFFFFFFFF 的 32-bit CRC 要快：把 :10 改成反轉多項式（例 AUTOSAR `0xC8DF352F`）。
要看程式：請操作者貼「cat -n crc32.c | sed -n 43,79p」

---

【規格卡｜ALGO 3/9｜CRC 規格表：crc_generic 參數與 check】
以下是正確的參考資料（預製程式碼 2026-11-13 版）。和你的記憶不同時，以這張為準。
`crc_param_t p = {width, poly, init, refin, refout, xorout};`（crc32.h:32-39）
`crc_generic(&p, (const uint8_t *)"123456789", 9)` == 下面的 check（全部實測 PASS）：
CRC-32（zlib、PNG）：`{32,0x04C11DB7,0xFFFFFFFF,1,1,0xFFFFFFFF}` → 0xCBF43926
CRC-32C：`{32,0x1EDC6F41,0xFFFFFFFF,1,1,0xFFFFFFFF}` → 0xE3069283
CRC-32/BZIP2：`{32,0x04C11DB7,0xFFFFFFFF,0,0,0xFFFFFFFF}` → 0xFC891918
CRC-32/MPEG-2：`{32,0x04C11DB7,0xFFFFFFFF,0,0,0}` → 0x0376E6E7
CRC-16/CCITT-FALSE：`{16,0x1021,0xFFFF,0,0,0}` → 0x29B1
CRC-16/XMODEM：`{16,0x1021,0,0,0,0}` → 0x31C3
CRC-16/KERMIT：`{16,0x1021,0,1,1,0}` → 0x2189
CRC-16/MODBUS：`{16,0x8005,0xFFFF,1,1,0}` → 0x4B37
CRC-16/ARC：`{16,0x8005,0,1,1,0}` → 0xBB3D
CRC-12/UMTS：`{12,0x80F,0,0,1,0}` → 0xDAF
CRC-8/SMBUS：`{8,0x07,0,0,0,0}` → 0xF4
CRC-8/MAXIM（1-Wire）：`{8,0x31,0,1,1,0}` → 0xA1
CRC-7/MMC：`{7,0x09,0,0,0,0}` → 0x75
CRC-5/USB：`{5,0x05,0x1F,1,1,0x1F}` → 0x19
- poly 填**一般（不反轉）寫法**。題目給 0xEDB88320 → 填 0x04C11DB7 + refin=refout=1（0x82F63B78 ↔ 0x1EDC6F41、0xA001 ↔ 0x8005）。
- x^16+x^12+x^5+1 = 0x1021（最高次項省略）。width 1..32 都可以。
要看程式：請操作者貼「cat -n crc32.c | sed -n 103,117p」

---

【規格卡｜ALGO 4/9｜sha1_sha0.c、sha256.c：API 與 SHA-0 差別】
以下是正確的參考資料（預製程式碼 2026-11-13 版）。和你的記憶不同時，以這張為準。
| 函式 | 行號 | 做什麼 |
|---|---|---|
| `void sha1_init(sha1_ctx *c, int is_sha0)` | sha1_sha0.c:40-44 | **1 = SHA-0、0 = SHA-1** |
| `void sha1_update(sha1_ctx *c, const uint8_t *p, size_t n)` | :46-55 | 餵任意長度 |
| `void sha1_final(sha1_ctx *c, uint8_t out[20])` | :57-71 | 補 padding，輸出 20 byte |
| `sha1(p, n, out)` / `sha0(p, n, out)` | :73-75 / :76-78 | 一次算完 |
| `sha256_init(&c)` / `_update(&c, p, n)` / `_final(&c, out)` | sha256.c:42-47 / 49-55 / 57-66 | out 32 byte |
| `sha256(p, n, out)` | sha256.c:68-70 | 一次算完 |
ctx：`sha1_ctx`（sha1_sha0.h:21-27）、`sha256_ctx`（sha256.h:12-17）。
串流：init 一次 → update 多次（照資料順序，長度任意）→ final 一次 = 一次算完的結果。final 後要重新 init。
SHA-0 和 SHA-1 唯一差別（sha1_sha0.c:26）：訊息擴展 W[t] 時 SHA-1 多做 `ROTL(wt, 1)`；初值、常數、80 回合都一樣。Python `hashlib` 沒有 SHA-0。
輸入用大端組字；out 逐 byte 印 `%02x` 就是標準 hex。
"abc" 的答案：
- SHA-1 `a9993e364706816aba3e25717850c26c9cd0d89d`
- SHA-0 `0164b8a914cd2a5e74c4f7ff082c4d97f1edf880`
- SHA-256 `ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad`
速度（電腦）：sha1 423.1、sha0 415.8、sha256 122.6 MB/s。SHA 不能拆給多塊板子平行算。
要看程式：請操作者貼「cat -n sha1_sha0.c | sed -n 40,78p」

---

【規格卡｜ALGO 5/9｜sort.c：排序與合併、選哪個】
以下是正確的參考資料（預製程式碼 2026-11-13 版）。和你的記憶不同時，以這張為準。
| 函式 | sort.c 行號 | 注意 |
|---|---|---|
| `void insertion_sort_u32(uint32_t *a, size_t n)` | 8-15 | O(n²)；n ≤ 32 最快 |
| `void merge_sort_u32(uint32_t *a, size_t n, uint32_t *tmp)` | 26-39 | 穩定；tmp ≥ n 個 |
| `void radix_sort_u32(uint32_t *a, size_t n, uint32_t *tmp)` | 44-57 | LSD 4 趟；tmp ≥ n 個；結果回到 a |
| `void merge_two_sorted(a, na, b, nb, uint32_t *out)` | 59-65 | out 不可和 a、b 重疊 |
| `void kway_merge(const uint32_t *const lists[], const size_t lens[], int k, uint32_t *out)` | 67-78 | **k 沒有上限**；O(n×k)；相等取編號小的 |
常數：`RUN 32`（sort.c:6，TODO，16~64 都可）；`KWAY_MAX 16`（sort.h:31）只是建議值，不限制 k。
排序（電腦，n = 2^20）：qsort 106.25 ms、merge 77.68、radix 6.88（快 15.4 倍）、兩半各 radix + merge_two_sorted 11.01。→ n ≤ 32 用 insertion；n ≥ 256 用 radix。
合併 k 段（n = 2^20）：
| k | kway_merge | 兩兩合併 |
|---|---|---|
| 4 | 12.52 ms | 7.94 ms |
| 8 | 29.05 ms | 12.19 ms |
| 16 | 62.32 ms | 15.93 ms |
→ k ≤ 4 用 `kway_merge`；k ≥ 8 用 `merge_two_sorted` 兩兩合併（tree merge，多要一個 n 大小的暫存區）。
有號 int32：排序前每個 `^= 0x80000000u`，排完再做一次。遞減：前後各取 `~x`。
電腦端合併多板結果：Python `heapq.merge`。
要看程式：請操作者貼「cat -n sort.c | sed -n 44,78p」

---

【規格卡｜ALGO 6/9｜bnn.c：位元排列、XNOR-popcount、門檻】
以下是正確的參考資料（預製程式碼 2026-11-13 版）。和你的記憶不同時，以這張為準。
排列（bnn.h:14）：第 i 個 → word `i/32` 的 bit `i%32`（LSB 起）；+1=1、-1=0。`BNN_WORDS(n)`=(n+31)/32。
| 函式 | bnn.c | 做什麼 |
|---|---|---|
| `bnn_pack(const int8_t *v, int n, uint32_t *out)` | 4-8 | v[i] > 0 → 1；**0 也當 -1** |
| `int32_t bnn_dot(a, w, n)` | 14-23 | 2*popcount(~(a^w))-n；尾巴 mask（19-21） |
| `bnn_dense_sign(&L, in, out_bits)` | 25-33 | d = flip[j] ? -dot : dot；d >= thr[j] → 1；**thr 不可 NULL** |
| `bnn_dense_score(&L, in, int32_t *score)` | 35-39 | dot+thr[j]（bias，可 NULL） |
| `int bnn_argmax(s, n)` | 41-45 | 平手取小的 |
| `bnn_fold_bn(gamma, beta, mean, std, bias, &thr, &flip)` | 53-63 | BN+sign → 整數門檻 |
`bnn_layer_t`（bnn.h:45-50）= `{n_in, n_out, W, thr, flip}`，W 每列 BNN_WORDS(n_in) word。
門檻：t = mean - bias - beta*std/gamma（std = sqrtf(var+eps)）。gamma > 0：thr = ceil(t)、flip 0；< 0：thr = ceil(-t)、flip 1。
推論：pack → dense_sign（隱藏層）→ dense_score（最後層）→ argmax（`bnn_test.c:24-32`）。
popcount（bnn.h:34-42）：RISC-V Zbb 是 1 條 cpop；M33 沒有 → 加 `-DBNN_SWAR_POPCOUNT`。電腦 784×256 一層：12.09 µs、SWAR 8.12、硬體 3.47。
換權重：`bnn_test.c:15-20`（尺寸、W1/W2）、`:73`（BN 參數）。numpy packbits（MSB 先）要先轉排列。
要看程式：請操作者貼「cat -n bnn.c | sed -n 14,39p」

---

【規格卡｜ALGO 7/9｜checksum_misc.c：簡單校驗碼】
以下是正確的參考資料（預製程式碼 2026-11-13 版）。和你的記憶不同時，以這張為準。
單一 .c、沒有 .h：把需要的函式整段複製，不要複製 `#ifdef TEST_MAIN`（72-106）。`p, n` = `const uint8_t *p, size_t n`。
| 函式 | 行號 | 算法 | 測試向量 |
|---|---|---|---|
| `uint32_t adler32(uint32_t adler, p, n)` | 21-30 | a = 1+Σbyte、b = Σa，mod 65521；(b<<16)\|a；第一次傳 **1**，可分段 | "Wikipedia" → 0x11E60398 |
| `uint16_t fletcher16(p, n)` | 32-41 | s1 = Σbyte、s2 = Σs1，mod 255；(s2<<8)\|s1；不能分段 | "abcde" → 0xC8F0 |
| `uint8_t xor8(p, n)` | 43-47 | 全部 XOR | NMEA 例句 → 0x28 |
| `uint8_t sum8(p, n)` | 49-53 | 加總低 8 位 | "123456789" → 0xDD |
| `uint8_t lrc8(p, n)` | 55 | 0 - sum8（Modbus ASCII） | sum8 + lrc8 = 0 |
| `uint32_t sum32(const uint32_t *w, size_t nwords)` | 57-61 | uint32 相加，溢位捨去；參數是 **word 數** | {0xFFFFFFFF, 2, 3} → 4 |
| `uint16_t inet_csum(p, n)` | 64-70 | RFC 1071：每 2 byte 當**大端**相加、進位折回、取反；奇數補 0 | 00 01 f2 03 f4 f5 f6 f7 → 0x220D |
常數：`ADLER_MOD 65521`（:16）、`ADLER_NMAX 5552`（:17，每 5552 byte 才取一次 mod）。
- NMEA 只算 `$` 和 `*` 之間。
- inet_csum 放回封包時高 byte 先；連 checksum 欄位一起算，結果應為 0。
- 檔案裡沒有 Fletcher-32。Python `zlib.adler32` = adler32。
要看程式：請操作者貼「cat -n checksum_misc.c | sed -n 16,70p」

---

【規格卡｜ALGO 8/9｜放進 Pico 專案：CMake、weak、記憶體】
以下是正確的參考資料（預製程式碼 2026-11-13 版）。和你的記憶不同時，以這張為準。
只複製核心檔（crc32、sha1_sha0、sha256、sort、bnn 的 .c/.h）。不要放 `*_test.c`、`test_util.h`（POSIX `clock_gettime`）。
CMake（pico-sdk 2.2.0、pico2 ARM 編譯連結通過；檔案放專案的 `algo/`）：
```cmake
add_executable(app_algo app_algo.c
    algo/crc32.c algo/sha1_sha0.c algo/sha256.c algo/sort.c algo/bnn.c)
target_include_directories(app_algo PRIVATE ${CMAKE_CURRENT_LIST_DIR}/algo)
if (PICO_PLATFORM STREQUAL "rp2350-arm-s")
    target_compile_definitions(app_algo PRIVATE BNN_SWAR_POPCOUNT)
endif()
target_link_libraries(app_algo pico_stdlib)
```
既有 `pico/CMakeLists.txt`：在 `add_app(...)` 後面加 `target_sources(app_xxx PRIVATE algo/sort.c ...)` 和上面的 include。
和 `pico/serial_proto.c` 一起用：兩邊都有 `crc32_update`；`serial_proto.c:25` 是 `__attribute__((weak))` → 連結器用 `crc32.c` 的（結果相同），不會 multiple definition。
記憶體（M33 實測 stack）：
- 大陣列（a、tmp、權重、ctx）一律 `static`。主 stack 和 core1 stack 預設都是 0x800 = 2 KB。
- `radix_sort_u32` 1064 B、sha256() 整條 496 B、sha1() 整條 280 B、kway_merge 48 + 8k B、merge_sort 64 B、crc_generic 32 B。
- 靜態只有 crc32.c 的表 5636 B；程式碼共 < 5 KB。
- 雙核：CRC 表在 main 前由 constructor 建好，兩核都能直接用。
要看程式：請操作者貼「cat -n ../pico/serial_proto.c | sed -n 20,30p」

---

【規格卡｜ALGO 9/9｜測試指令與陷阱】
以下是正確的參考資料（預製程式碼 2026-11-13 版）。和你的記憶不同時，以這張為準。
在 `預製程式碼/algo/` 執行，執行檔放 repo 外：`B=/tmp/algo_build; mkdir -p $B`，`G="gcc -O2 -Wall -Wextra -std=c11"`
| 測試 | 指令 | 成功 |
|---|---|---|
| CRC | `$G crc32.c crc32_test.c -o $B/crc && $B/crc` | 17 PASS |
| SHA | `$G sha1_sha0.c sha256.c sha_test.c -o $B/sha && $B/sha` | 10 PASS |
| 排序 | `$G sort.c sort_test.c -o $B/sort && $B/sort` | 6 PASS |
| BNN | `$G bnn.c bnn_test.c -o $B/bnn && $B/bnn` | 4 PASS |
| 校驗碼 | `$G -DTEST_MAIN checksum_misc.c -o $B/ck && $B/ck` | 13 PASS |
成功：最後一行 `結果：全部通過`。失敗印 `FAIL  說明 (檔:行)`。
陷阱（程式這樣寫 = 錯 → 改法）：
1. `crc16_ccitt_false(0, …)` → 得 0x31C3（XMODEM）→ 第一段傳 0xFFFF。
2. 分段時第二段又傳 0 → 改傳上一段的回傳值。`crc_generic` 分段算 → 改成整份一次算。
3. CRC 得 0x340BC6D9 → 少了最後 XOR；poly 填 0xEDB88320 → 改 0x04C11DB7 + refin=refout=1。
4. 要 SHA-0 卻 `sha1_init(&c, 0)` → 得 SHA-1 → 傳 1。每包都 init/final → 改成各一次。
5. int32 直接 radix → 負數排最後 → 前後 `^= 0x80000000u`。
6. `merge_two_sorted` 的 out 和輸入重疊 → 另開陣列。
7. 大陣列寫在函式裡 → Pico hard fault → 改 `static`。
8. 隱藏層 thr 傳 NULL → 當掉；權重 MSB 先沒轉 → 分類全錯。
9. `adler32(0, …)` → 錯 → 第一次傳 1。
10. 改了 `POLY32R` → crc32_test 的 CRC-32 斷言 FAIL 是預期的，改用 crc_generic 對照。
要看程式：見各列的行號
