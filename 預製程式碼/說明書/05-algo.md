# 第 5 章　algo/：純 C 演算法工具箱（CRC、SHA-0/1/256、排序與合併、BNN、其他校驗碼）

> 本章對應的檔案：`algo/README.md`、`crc32.h`、`crc32.c`、`crc32_test.c`、`sha1_sha0.h`、`sha1_sha0.c`、`sha256.h`、`sha256.c`、`sha_test.c`、`sort.h`、`sort.c`、`sort_test.c`、`bnn.h`、`bnn.c`、`bnn_test.c`、`checksum_misc.c`、`test_util.h`（另對照 `pico/app_dma.c`、`pico/app_serial.c`、`pico/serial_proto.c`、`ros2/multi_device.py`）｜驗證狀態：5 支測試程式在 host 全部 PASS（另用 ASan/UBSan 再跑一次也全過）；同 5 支在 `qemu-riscv32`（rv32 + Zbb）全部 PASS；6 個核心檔用 Cortex-M33 與 rv32 Zbb 交叉編譯 0 警告；放進 pico-sdk 2.2.0 專案（pico2、ARM）編譯連結通過；**沒有在實體 Pico 上跑過**｜最後核對：2026-11-12（commit d102c17）

本章實測環境（以下簡稱「本次實測」）：host = x86_64、Intel Xeon @ 2.30GHz、4 核、gcc 13.3.0（Ubuntu 24.04）、Python 3.13.18；交叉編譯 = `arm-none-eabi-gcc` 13.2.1、`riscv64-unknown-elf-gcc` 13.2.0 + picolibc；模擬器 = `qemu-riscv32`（Linux user mode）；pico-sdk 2.2.0。所有編譯、測試都在 repo 外的 scratch 資料夾做，沒有在 repo 產生任何檔案。本章自己寫的測試程式（CRC 規格表、Python 對照、查表版通用 CRC 等）都標「ch05 自寫」，**不在 repo 裡**，要用就照本章抄。

## 5.0 30 秒版：什麼時候打開這一章

- 題目出現 **CRC、CRC32、zlib、Ethernet、PNG、校驗、poly、init、refin、refout、xorout** → `crc32.c`。標準 zlib CRC-32 用 `crc32_update(0, buf, n)`；題目給了一組參數 → 查 5.2.4 的規格表，用 `crc_generic` 填參數（食譜 5.4.1）。
- 題目出現 **SHA-0、SHA-1、SHA-256、雜湊、hash、digest** → `sha1_sha0.c`、`sha256.c`。一次算完用 `sha0(buf, n, out)`；資料分好幾包收到用 `sha1_init(&c, 1)` / `sha1_update` / `sha1_final`（食譜 5.4.4）。
- 題目出現 **排序、sort、merge、合併兩塊板子的結果** → `sort.c`。大量 `uint32` 用 `radix_sort_u32`（本次實測 n = 2^20 時比 `qsort` 快 15.4 倍）；分給多塊板子再合併用 `merge_two_sorted` / `kway_merge`（食譜 5.4.3）。
- 題目出現 **eBNN、BNN、二值化、XNOR、popcount、權重、門檻、BatchNorm** → `bnn.c`。先讀 5.2.8，再把 `bnn_test.c:14` 的範例網路換成題目的權重。
- 題目出現 **Adler-32、Fletcher、XOR 校驗、NMEA `*hh`、LRC、IP/UDP checksum** → `checksum_misc.c`，整段複製需要的函式。
- 板子上要「邊搬資料邊算 CRC」→ DMA sniffer，見第 3 章 `app_dma.c` 一節與食譜 5.4.2；**先用本章的 `crc32_update` 驗證硬體結果**。
- 最常改的 3 個地方：`crc_generic` 的參數（5.2.4 表格整列照抄）、`bnn_test.c:15-22` 的網路尺寸與權重、`sort.h:31` 的 `KWAY_MAX`（超過 16 段會**靜悄悄漏資料**，見 5.6）。
- 全部 `TODO(改這裡)`：`grep -n "TODO(改這裡)" *.c *.h`（在 `algo/` 執行，共 6 處：`crc32.c:10`、`crc32_test.c:7`、`sort.c:6`、`sort.c:69`、`sort_test.c:7`、`bnn_test.c:14`）。

## 5.1 檔案總表

| 檔案 | 行數 | 做什麼 | 什麼時候用 | 驗證狀態 |
|---|---|---|---|---|
| `README.md` | 111 | 題型對照、API 速查、編譯指令、作者機器上的實測數字、考場要改哪裡 | 第一次打開 `algo/` | 文件；指令本次照跑過 |
| `crc32.h` | 59 | CRC 介面宣告、`crc_param_t`、10 種常見規格的參數表（註解） | 要知道函式簽名、要查 CRC 參數 | ✅ 表內 10 列本次用 `crc_generic` 重算全對 |
| `crc32.c` | 117 | CRC-32 三種實作（逐位元、查表、slice-by-4）、CRC-32C、CRC-16/CCITT-FALSE、通用 `crc_generic` | 所有 CRC 題 | ✅ host、qemu-rv32 測試 PASS；M33/rv32 0 警告 |
| `crc32_test.c` | 67 | 標準向量、規格表、200 組隨機一致性、4 MB 測速 | 改了 `crc32.c` 之後驗證、量速度 | ✅ 本次實跑 |
| `sha1_sha0.h` | 35 | SHA-1/SHA-0 共用的 `sha1_ctx` 與 5 個函式 | 要算 SHA-0 或 SHA-1 | ✅ |
| `sha1_sha0.c` | 78 | SHA-1/SHA-0 實作（差一個左旋） | 同上 | ✅ host、qemu-rv32 PASS；Python 獨立實作 200 組一致 |
| `sha256.h` | 24 | `sha256_ctx` 與 4 個函式 | 要算 SHA-256 | ✅ |
| `sha256.c` | 70 | SHA-256 實作 | 同上 | ✅ host、qemu-rv32 PASS；`hashlib` 200 組一致 |
| `sha_test.c` | 82 | 7 組標準向量、一百萬個 `a`、300 組隨機切段、測速 | 改了 SHA 之後驗證 | ✅ 本次實跑 |
| `sort.h` | 34 | 5 個排序 / 合併函式、`KWAY_MAX`、選用建議 | 要排序或合併 | ✅ |
| `sort.c` | 78 | insertion、bottom-up merge sort、LSD radix sort、2-way merge、k-way merge | 同上 | ✅ host、qemu-rv32 PASS |
| `sort_test.c` | 74 | 與 `qsort` 比對（11 種 n × 4 種分布）、合併測試、測速 | 改了 `sort.c` 之後驗證 | ✅ 本次實跑 |
| `bnn.h` | 66 | eBNN 原理註解、位元排列規則、BN 折門檻公式、`bnn_layer_t`、`bnn_popcount` | 做 BNN 題先讀這個檔頭 | ✅ |
| `bnn.c` | 63 | 打包、XNOR-popcount 內積、隱藏層、輸出層、argmax、BN 折門檻 | BNN 推論 | ✅ host、qemu-rv32 PASS；Python 獨立實作一致 |
| `bnn_test.c` | 94 | 與笨方法比對、20000 組 BN 參數、2 層範例網路、784×256 測速 | 換權重時當範本 | ✅ 本次實跑 |
| `checksum_misc.c` | 106 | Adler-32、Fletcher-16、XOR、sum8、LRC、sum32、Internet checksum（沒有 `.h`） | 題目要簡單校驗碼 | ✅ host、qemu-rv32 PASS |
| `test_util.h` | 54 | 只給 `*_test.c` 用：`CHECK`、計時、亂數、`to_hex`、`BENCH_MIN` | 自己寫測試程式時 | ✅（用 POSIX `clock_gettime`，MCU 上不能用） |

規則（`README.md:3-5`）：核心檔不用 `malloc`、只用 `stdint.h` 型別，電腦和 RP2350 兩種核心都能編；`*_test.c` 和 `test_util.h` **只在電腦上用**，不要放進 Pico 專案。

## 5.2 先懂這些概念

### 5.2.1 名詞

| 名詞 | 一句話解釋 |
|---|---|
| bit 0 / LSB | 一個整數最右邊（值為 1）的那一位 |
| MSB | 最左邊的那一位（8-bit 是值 0x80 的那位，32-bit 是 0x80000000） |
| 小端序（little-endian） | 多 byte 整數「低位 byte 放在低位址」。x86、ARM Cortex-M33、RISC-V 全是小端 |
| 大端序（big-endian） | 「高位 byte 放在低位址」。網路封包、SHA 的輸入切字與輸出都用大端 |
| 位元反轉（reflect） | 把一個數的 bit 順序倒過來，例如 8-bit 的 `0x01` → `0x80` |
| GF(2) | 只有 0 和 1 的算術，加法 = 減法 = XOR，沒有進位 |
| 雜湊（hash） | 任意長度資料 → 固定長度摘要；改 1 bit 結果就完全不同 |
| 穩定排序（stable） | 相等的元素排完後保持原本的先後順序 |
| popcount | 數一個整數裡有幾個 1（例：`popcount(0b1011) = 3`） |
| SWAR | 「一個暫存器當好幾個小格子平行算」的純 C 技巧，`bnn_popcount` 的備用版就是 |
| Zbb | RISC-V 的位元運算擴充指令集，有 `cpop`（popcount）、`xnor`、`rori` 等；RP2350 的 Hazard3 核心有 |

### 5.2.2 CRC 是什麼

CRC（循環冗餘校驗）把整串資料看成一個很長的二進位多項式，除以一個固定的「生成多項式」`poly`，**餘數**就是 CRC。除法裡的減法換成 XOR（GF(2) 算術），所以只用到位移和 XOR（`crc32.c:1-2` 的註解）。

逐位元做法（MSB 先，也叫「不反轉」）：

```text
crc = init
對每個輸入 byte b：
    crc ^= b << (width-8)          把 byte 放到 crc 的最高 8 位
    重複 8 次：
        若 crc 的最高位是 1： crc = (crc << 1) ^ poly
        否則：                 crc =  crc << 1
    crc &= (2^width - 1)
最後：crc ^= xorout
```

這就是 `crc_generic`（`crc32.c:103-117`）的內容。「LSB 先」的 CRC（zlib 那種）可以把每個 byte 反轉後照上面做，最後再把結果反轉；或等價地改成「右移 + 反轉多項式」（`crc32.c:43-51` 的 `crc32_bitwise`），兩種寫法結果相同。

### 5.2.3 CRC 的 7 個參數

所有 CRC 規格都用這 7 個數字描述（業界通用的「Rocksoft 模型」，`crc32.h:32-39` 的 `crc_param_t` 就是前 6 個）：

| 參數 | `crc_param_t` 欄位 | 意思 | zlib CRC-32 的值 |
|---|---|---|---|
| width | `width`（`uint8_t`） | CRC 幾個 bit | 32 |
| poly | `poly` | 生成多項式，**一般（不反轉）寫法**，最高位的 1 省略 | `0x04C11DB7` |
| init | `init` | 開始前暫存器的值 | `0xFFFFFFFF` |
| refin | `refin` | 1 = 每個輸入 byte 先位元反轉（等於 LSB 先處理） | 1 |
| refout | `refout` | 1 = 最後結果整個位元反轉（反轉 width 位） | 1 |
| xorout | `xorout` | 最後再 XOR 的值 | `0xFFFFFFFF` |
| check | （不是參數） | 對 ASCII 字串 `"123456789"`（9 byte）算出來的結果，用來驗證你填對了 | `0xCBF43926` |

重點：
- 題目只寫「多項式 0xEDB88320」時，那是**反轉後**的寫法（`0x04C11DB7` 反轉 32 位），`crc_generic` 要填 `0x04C11DB7` 加 `refin=refout=1`。對照表在 `crc32.h:55-57`：`0x04C11DB7 ↔ 0xEDB88320`、`0x1EDC6F41 ↔ 0x82F63B78`、`0x8005 ↔ 0xA001`。
- 「多項式 x^16+x^12+x^5+1」= 把指數 15..0 的位設 1：`0x1021`（x^16 那項省略）。
- refin 和 refout 可以不同（例如 CRC-12/UMTS：refin=0、refout=1），`crc_generic` 支援。
- **width 一定要 8..32**（`crc32.h:33` 註解）。width < 8（CRC-5、CRC-7）會觸發未定義行為，見 5.6 與食譜 5.4.1 的替代函式。

### 5.2.4 常見 CRC 規格表（全部用 `crc_generic` 實測過）

本次實測方法：ch05 自寫 `crcspec.c`，對每一列呼叫 `crc_generic(&p, "123456789", 9)`，和標準 check 值比較；34 列**全部 PASS**（輸出見 5.3.3）。另外用 Python `zlib.crc32` 和 Python 獨立實作（食譜 5.4.7）各對 200 組隨機資料比對 CRC-32、CRC-32C、CRC-16/MODBUS，全一致。

「C 初始化寫法」整格可以直接貼進程式：`crc_param_t p = {...};` 順序是 `{width, poly, init, refin, refout, xorout}`。

| 名稱（別名） | C 初始化寫法 | check |
|---|---|---|
| CRC-32/ISO-HDLC（zlib、PNG、Ethernet、`zlib.crc32`） | `{32, 0x04C11DB7, 0xFFFFFFFF, 1, 1, 0xFFFFFFFF}` | `0xCBF43926` |
| CRC-32/ISCSI（CRC-32C、Castagnoli） | `{32, 0x1EDC6F41, 0xFFFFFFFF, 1, 1, 0xFFFFFFFF}` | `0xE3069283` |
| CRC-32/BZIP2 | `{32, 0x04C11DB7, 0xFFFFFFFF, 0, 0, 0xFFFFFFFF}` | `0xFC891918` |
| CRC-32/MPEG-2（= sniffer `CRC32` 不反轉模式的計算方向） | `{32, 0x04C11DB7, 0xFFFFFFFF, 0, 0, 0x00000000}` | `0x0376E6E7` |
| CRC-32/CKSUM（POSIX `cksum` 的核心，不含長度） | `{32, 0x04C11DB7, 0x00000000, 0, 0, 0xFFFFFFFF}` | `0x765E7680` |
| CRC-32/JAMCRC（= zlib 少做最後的 XOR） | `{32, 0x04C11DB7, 0xFFFFFFFF, 1, 1, 0x00000000}` | `0x340BC6D9` |
| CRC-32/AUTOSAR | `{32, 0xF4ACFB13, 0xFFFFFFFF, 1, 1, 0xFFFFFFFF}` | `0x1697D06A` |
| CRC-32/BASE91-D（CRC-32D） | `{32, 0xA833982B, 0xFFFFFFFF, 1, 1, 0xFFFFFFFF}` | `0x87315576` |
| CRC-32/AIXM（CRC-32Q） | `{32, 0x814141AB, 0x00000000, 0, 0, 0x00000000}` | `0x3010BF7F` |
| CRC-32/XFER | `{32, 0x000000AF, 0x00000000, 0, 0, 0x00000000}` | `0xBD0BE338` |
| CRC-24/OPENPGP | `{24, 0x864CFB, 0xB704CE, 0, 0, 0}` | `0x21CF02` |
| CRC-16/IBM-3740（CCITT-FALSE、`crc16_ccitt_false`） | `{16, 0x1021, 0xFFFF, 0, 0, 0x0000}` | `0x29B1` |
| CRC-16/XMODEM（ZMODEM、`binascii.crc_hqx(d, 0)`） | `{16, 0x1021, 0x0000, 0, 0, 0x0000}` | `0x31C3` |
| CRC-16/KERMIT（CCITT-TRUE） | `{16, 0x1021, 0x0000, 1, 1, 0x0000}` | `0x2189` |
| CRC-16/IBM-SDLC（X-25） | `{16, 0x1021, 0xFFFF, 1, 1, 0xFFFF}` | `0x906E` |
| CRC-16/GENIBUS | `{16, 0x1021, 0xFFFF, 0, 0, 0xFFFF}` | `0xD64E` |
| CRC-16/MCRF4XX | `{16, 0x1021, 0xFFFF, 1, 1, 0x0000}` | `0x6F91` |
| CRC-16/SPI-FUJITSU（AUG-CCITT） | `{16, 0x1021, 0x1D0F, 0, 0, 0x0000}` | `0xE5CC` |
| CRC-16/ARC（IBM、LHA） | `{16, 0x8005, 0x0000, 1, 1, 0x0000}` | `0xBB3D` |
| CRC-16/MODBUS | `{16, 0x8005, 0xFFFF, 1, 1, 0x0000}` | `0x4B37` |
| CRC-16/USB | `{16, 0x8005, 0xFFFF, 1, 1, 0xFFFF}` | `0xB4C8` |
| CRC-16/MAXIM-DOW | `{16, 0x8005, 0x0000, 1, 1, 0xFFFF}` | `0x44C2` |
| CRC-16/UMTS（BUYPASS） | `{16, 0x8005, 0x0000, 0, 0, 0x0000}` | `0xFEE8` |
| CRC-16/DNP | `{16, 0x3D65, 0x0000, 1, 1, 0xFFFF}` | `0xEA82` |
| CRC-16/T10-DIF | `{16, 0x8BB7, 0x0000, 0, 0, 0x0000}` | `0xD0DB` |
| CRC-12/UMTS（refin 和 refout 不同） | `{12, 0x80F, 0x000, 0, 1, 0x000}` | `0xDAF` |
| CRC-8/SMBUS（`crc32.h` 叫 CRC-8） | `{8, 0x07, 0x00, 0, 0, 0x00}` | `0xF4` |
| CRC-8/I-432-1（ITU） | `{8, 0x07, 0x00, 0, 0, 0x55}` | `0xA1` |
| CRC-8/ROHC | `{8, 0x07, 0xFF, 1, 1, 0x00}` | `0xD0` |
| CRC-8/MAXIM-DOW（Dallas 1-Wire） | `{8, 0x31, 0x00, 1, 1, 0x00}` | `0xA1` |
| CRC-8/AUTOSAR | `{8, 0x2F, 0xFF, 0, 0, 0xFF}` | `0xDF` |
| CRC-8/SAE-J1850 | `{8, 0x1D, 0xFF, 0, 0, 0xFF}` | `0x4B` |
| CRC-8/BLUETOOTH | `{8, 0xA7, 0x00, 1, 1, 0x00}` | `0x26` |
| CRC-8/NRSC-5 | `{8, 0x31, 0xFF, 0, 0, 0x00}` | `0xF7` |

width 小於 8 的規格要用食譜 5.4.1 的 `crc_bits`（ch05 自寫，本次實測）：CRC-7/MMC `crc_bits(7, 0x09, 0x00, 0, 0, 0x00, ...)` = `0x75`、CRC-5/USB `crc_bits(5, 0x05, 0x1F, 1, 1, 0x1F, ...)` = `0x19`、CRC-4/G-704 `crc_bits(4, 0x3, 0x0, 1, 1, 0x0, ...)` = `0x7`、CRC-3/GSM `crc_bits(3, 0x3, 0x0, 0, 0, 0x7, ...)` = `0x4`。

### 5.2.5 CRC 的三種寫法：逐位元、查表、slice-by-4

三個函式結果完全相同（`crc32_test.c:37-51` 用 200 組隨機長度、隨機起點驗證），差在速度和記憶體：

| 寫法 | 函式 | 每個 byte 做什麼 | 額外記憶體 | 本次實測 host 速度（4 MB，`-O2`） |
|---|---|---|---|---|
| 逐位元 | `crc32_bitwise`（`crc32.c:43`） | 8 次「右移 + 視最低位 XOR poly」 | 0 | 115.0 MB/s（1x） |
| 查表 | `crc32_table`（`crc32.c:54`） | 1 次查 256 格的表 | 1 KB（`T[0]`） | 484.8 MB/s（4.2x） |
| slice-by-4 | `crc32_slice4`（`crc32.c:62`） | 每 4 byte 查 4 張表、XOR 起來 | 4 KB（`T[0..3]`） | 1445.4 MB/s（12.6x） |
| 通用逐位元 | `crc_generic`（`crc32.c:103`） | 8 次左移 + 反轉輸入 byte | 0 | 28.3 MB/s（CRC-32/AUTOSAR，ch05 自寫測速） |

為什麼查表快：一個 byte 對暫存器造成的影響只取決於「暫存器低 8 位 XOR 這個 byte」這 256 種可能，所以先把 256 種結果算好（`crc32_init`，`crc32.c:26-40`），之後每 byte 只查一次表：

```c
while (n--) crc = (crc >> 8) ^ T[0][(crc ^ *p++) & 0xFF];
```

為什麼 slice-by-4 更快：`T[t][i]` =「byte i 後面再接 t 個 0 byte」的影響（`crc32.c:35-38`）。一次吃 4 byte 時，4 次查表彼此獨立，CPU 可以同時做，迴圈次數也少 4 倍：

```c
crc = T[3][crc & 0xFF] ^ T[2][(crc >> 8) & 0xFF] ^
      T[1][(crc >> 16) & 0xFF] ^ T[0][crc >> 24];
```

本次在 qemu-riscv32 上三者的比例是 1 : 7.0 : 18.7（77.77 / 11.05 / 4.15 ms），但 qemu 不模擬真實時序，只能當參考。Pico 上的實際速度**沒有實測**；Pico 上的 RAM 存取不像 x86 有多層 cache，比例會不同（⚠️未驗證）。

### 5.2.6 SHA-1、SHA-0、SHA-256

三個都是「Merkle–Damgård 結構」：資料切成 64 byte 一塊，每塊用壓縮函式 `compress` 更新內部狀態，最後補 padding。

**padding 格式（三個一樣，`sha1_sha0.c:57-66`、`sha256.c:57-63`）**：

```text
原始資料 ... | 0x80 | 0x00 ... 0x00 | 總位元數（8 byte，大端序）
             ^ 1 byte  ^ 補到「長度 ≡ 56 (mod 64)」  ^ 例：3 byte 資料 → 00 00 00 00 00 00 00 18
若剩下的空間放不下 0x80 + 8 byte 長度（尾巴 > 55 byte），就多補一整塊（sha1_sha0.c:60-63）
```

**SHA-0 和 SHA-1 唯一的差別**（`sha1_sha0.h:3-5`、`sha1_sha0.c:26`）：訊息擴展時 SHA-1 多做一次左旋 1 位。

```c
wt = w[(t - 3) & 15] ^ w[(t - 8) & 15] ^ w[(t - 14) & 15] ^ w[t & 15];
if (!ctx->is_sha0) wt = ROTL(wt, 1);    /* ★ SHA-1 與 SHA-0 唯一差別 */
```

SHA-0 是 1993 年的版本，因為有弱點，1995 年改成 SHA-1（就是加這個旋轉）。兩者初值、常數、80 回合函式全都一樣。Python 的 `hashlib` 有 SHA-1 沒有 SHA-0，所以電腦端要對 SHA-0 答案只能用自己寫的版本（食譜 5.4.7）。

**SHA-256 和 SHA-1 的差別**（`sha256.c:1-3` 註解）：8 個 32-bit 狀態字（輸出 32 byte），64 回合，每回合用不同常數 `K[i]`（`sha256.c:8-16`），用右旋 `ROTR`。本次實測 SHA-256 比 SHA-1 慢 3.5 倍（122.6 vs 423.1 MB/s），一部分是演算法本身較重，一部分是 `sha256_update` 逐 byte 複製（`sha256.c:51-54`，見 5.6）。

**串流 API vs 一次算完**：

| 方式 | 寫法 | 什麼時候用 |
|---|---|---|
| 一次算完 | `sha0(buf, n, out)`、`sha1(...)`、`sha256(...)` | 整份資料已經在記憶體裡 |
| 串流 | `init` → 多次 `update` → `final` | 資料分好幾包從序列埠 / ROS 2 topic 收到；資料太大放不進 RAM |

串流的結果和一次算完**完全相同**，不管每包多長（`sha_test.c:51-71` 用 300 組隨機切段驗證、`sha_test.c:36-49` 用 1000 次 × 1000 byte 算一百萬個 `a`）。

**SHA 不能拆給多塊板子平行算**：每一塊的輸入是前一塊的輸出，只能依序算。能平行的只有「一核收資料、一核算 SHA」這種管線（見第 3 章 `app_multicore.c` 一節）。

**標準測試向量**（全部在 `sha_test.c` 裡，本次 PASS）：

| 輸入 | 演算法 | 結果 |
|---|---|---|
| `"abc"` | SHA-1 | `a9993e364706816aba3e25717850c26c9cd0d89d` |
| `"abc"` | SHA-0 | `0164b8a914cd2a5e74c4f7ff082c4d97f1edf880` |
| `""` | SHA-1 | `da39a3ee5e6b4b0d3255bfef95601890afd80709` |
| `"abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq"`（56 字元，需 2 塊） | SHA-1 | `84983e441c3bd26ebaae4aa1f95129e5e54670f1` |
| `"abc"` | SHA-256 | `ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad` |
| `""` | SHA-256 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| 同上 56 字元 | SHA-256 | `248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1` |
| 1,000,000 個 `'a'` | SHA-1 | `34aa973cd4c4daa4f61eeb2bdbad27316534016f` |
| 1,000,000 個 `'a'` | SHA-256 | `cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0` |

### 5.2.7 排序與合併

| 方法 | 函式 | 時間複雜度 | 額外記憶體 | 穩定 | 適合 |
|---|---|---|---|---|---|
| 插入排序 | `insertion_sort_u32` | 平均 O(n²)；已排好時 O(n) | 0 | 是（`a[j-1] > x` 才搬，`sort.c:12`） | n ≤ 64 |
| 合併排序（bottom-up） | `merge_sort_u32` | O(n log n) | n 個 `uint32_t`（`tmp`） | 是（`<=`，`sort.c:20`） | 要穩定、資料不是整數鍵 |
| LSD radix sort | `radix_sort_u32` | O(4n + 4×256) | n 個 `tmp` + 1 KB 計數陣列（在 stack） | 是（計數排序依序搬） | 大量 `uint32`，通常最快 |
| 2 路合併 | `merge_two_sorted` | O(na + nb) | 輸出陣列 | 是（相等時先拿 a） | 兩塊板子 / 兩核各排一半 |
| k 路合併 | `kway_merge` | O(n × k) | 輸出陣列 + stack 上 16 個 `size_t` | 是（相等時拿編號小的那段） | k ≤ 8 段 |

**radix sort 怎麼做**（`sort.c:41-57`）：把 32-bit 整數切成 4 個 byte，從最低 byte 到最高 byte 各做一次「計數排序」：

```text
一趟（shift = 0, 8, 16, 24）：
  1. cnt[b] = 這個 byte 值為 b 的元素有幾個        （sort.c:49）
  2. 前綴和：cnt[b] = 比 b 小的元素總數 = b 桶的起點   （sort.c:52）
  3. 依原順序把每個元素搬到 dst[cnt[b]++]           （sort.c:53，穩定）
  4. src、dst 對調                                   （sort.c:54）
這一趟所有元素的 byte 都一樣 → 整趟跳過              （sort.c:50）
```

因為每一趟都穩定，排完最高 byte 時，最高 byte 相同的元素已經按低 byte 排好，所以整體有序。

**有號整數（`int32_t`）**：直接當 `uint32_t` 排，負數（最高位是 1）會跑到最後面。本次實測 `{-5, 3, -1, 7}` 直接排得到 `3 7 -5 -1`（錯）。正確做法（`sort.h:14`）：排序前每個元素 `^= 0x80000000u`（把符號位翻過來，負數變小、正數變大），排完再 `^= 0x80000000u` 翻回來。本次對 100,000 個隨機 `int32`（含 `INT32_MIN`、`INT32_MAX`、-1、0）和 `qsort` 比對一致。

**遞減**（`sort.h:15`）：排序前每個元素取 `~x`，排完再取 `~` 回來（本次實測 1000 筆 PASS）；或排完把陣列反轉。

**穩定性什麼時候重要**：這些函式只排 `uint32_t` 本身，相等的數字長得一樣，穩定與否看不出來。只有「依某個鍵排紀錄」時才重要，這時可以把「鍵」放高位、「原索引」放低位組成一個 `uint32_t`（例如鍵 ≤ 20 bit、索引 ≤ 12 bit：`(key << 12) | idx`），排完再拆開。`qsort` **不保證穩定**。

**2 路 vs k 路合併**（本次實測，n = 2^20，見 5.5.3）：`kway_merge` 每輸出一個元素要看 k 個頭，k=16 時 62.32 ms；改成「兩兩合併」（像比賽樹，O(n log k)，需要多一個 n 大小的暫存區）k=16 只要 15.93 ms。k ≤ 4 用 `kway_merge` 就好；k ≥ 8 改兩兩合併（食譜 5.4.3）。

### 5.2.8 BNN / eBNN

**二值化神經網路（BNN）**：權重和激活值都只有 +1、-1 兩種，所以 1 個 bit 就能存一個值。eBNN（Embedded Binarized Neural Networks，McDanel、Teerapittayanon、Kung，2017，`bnn.h:3`）是給只有幾 KB RAM 的 MCU 用的 BNN 推論方式。

**1. 二值化與打包**（`bnn.h:5`、`bnn.c:4-8`）：+1 存成 bit 1，-1 存成 bit 0，32 個塞進一個 `uint32_t`。`bnn_pack` 的規則是 `v[i] > 0` → 1，**0 也當成 -1**。

**2. 位元排列**（`bnn.h:14-15`）：第 i 個元素 → 第 `i/32` 個 word 的第 `i%32` 個 bit（從 LSB 算）。

```text
元素編號:   0   1   2  ...  31 | 32  33 ... 63 | 64 ...
存放位置: w[0] bit0 bit1 ... bit31 | w[1] bit0 ... bit31 | w[2] bit0 ...
n = 40 → 需要 BNN_WORDS(40) = 2 個 word；w[1] 只用 bit0..bit7，bit8..bit31 是「尾巴」，計算時一律 mask 掉
```

權重矩陣：第 j 個輸出神經元的權重是一列，佔 `BNN_WORDS(n_in)` 個 word，列與列緊接著放（`bnn.h:44`、`bnn.c:26,29` 的 `stride`）。

**3. XNOR-popcount 內積**（`bnn.h:6-7`、`bnn.c:14-23`）：±1 相乘時「同號 = +1、異號 = -1」，而「同號」就是兩個 bit 相同，也就是 XNOR = 1。所以：

```text
dot(a, w) = (#相同) - (#不同) = m - (n - m) = 2m - n,   m = popcount(~(a ^ w))（只數有效的 n 個 bit）

例：a = (+1, -1, +1, +1) → bits 1,0,1,1（i=0 在 bit0）→ a = 0b1101
    w = (+1, +1, -1, +1) → bits 1,1,0,1             → w = 0b1011
    ~(a ^ w) 的低 4 位 = ~0b0110 = 0b1001 → m = 2 → dot = 2*2 - 4 = 0
    直接算：(+1)(+1) + (-1)(+1) + (+1)(-1) + (+1)(+1) = 1 - 1 - 1 + 1 = 0  ✓
```

一次 32 個乘加變成 1 次 XOR + 1 次 NOT + 1 次 popcount。最後一個 word 的尾巴一定要 mask（`bnn.c:19-21`），否則 XNOR 會把兩邊都是 0 的尾巴算成「相同」；`bnn_test.c:46` 故意在尾巴塞垃圾 bit 驗證這件事。

**4. BatchNorm 折成整數門檻**（`bnn.h:17-23`、`bnn.c:53-63`）：隱藏層的輸出 = sign(BN(dot + bias))：

```text
y = gamma * (dot + bias - mean) / std + beta,   std = sqrt(var + eps)
輸出 +1 ⇔ y >= 0
  gamma > 0：dot >= t,   t = mean - bias - beta*std/gamma   → thr = ceil(t),  flip = 0
  gamma < 0：dot <= t ⇔ -dot >= -t                         → thr = ceil(-t), flip = 1
  gamma = 0：y = beta 恆定 → 永遠 +1（thr = INT32_MIN/2）或永遠 -1（thr = INT32_MAX/2）
推論：d = flip ? -dot : dot;  bit = (d >= thr)        （bnn.c:29-31）
```

例（gamma < 0）：gamma = -2、beta = 1、mean = 3、std = 2、bias = 0 → t = 3 - 0 - 1×2/(-2) = 4 → thr = ceil(-4) = -4、flip = 1。dot = 4：y = -2×(4-3)/2 + 1 = 0 → +1；程式 d = -4 ≥ -4 → 1 ✓。dot = 5：y = -1 → -1；程式 d = -5 < -4 → 0 ✓。

好處：推論路徑完全沒有浮點運算，每個神經元只存一個 `int32_t` 門檻和一個 `uint8_t` flip（`bnn.c:1` 註解）。`bnn_test.c:52-70` 用 20000 組隨機 BN 參數（gamma 有正、負、0）比對「浮點 BN 再取 sign」，本次全部一致。

**5. 層的結構**（`bnn.h:10-12`）：

```text
輸入 bits ──bnn_dense_sign(L1)──▶ 隱藏層 bits ──bnn_dense_sign(L2)──▶ ... ──bnn_dense_score(Lk)──▶ 整數分數 ──bnn_argmax──▶ 類別
            （dot → 比門檻 → 1 bit）                                    （最後一層不二值化：dot + bias）
```

eBNN 的 binary conv = 對每個 patch 做 `bnn_dot`；max-pool = 對整數 dot 取 max 後再比門檻；一次算一個輸出像素就立刻二值化，所以不用存浮點特徵圖（`bnn.h:9-10`）。`bnn.c` 只實作 dense（全連接）層，conv 要自己用 `bnn_dot` 組（⚠️ repo 裡沒有 conv 範例）。

**6. 第一層輸入**（`bnn.h:25-26`）：輸入是 0/1 像素 → `bnn_pack` 把 0 當 -1。輸入是 8-bit 灰階 → 先自己二值化（例如 `>= 128` → 1），或第一層改用一般整數乘加。

**去年考題對照**（來源：`預製程式碼/預測考題.md` 一、1 的表格；⚠️ 原始題目、權重檔格式不在 repo 裡，以下是依摘要推的對應）：

| 去年（115 學年度）的要求 | 本章對應 |
|---|---|
| ① ROS 2 跑 eBNN 推論，「資料轉 binary 加速傳輸」 | 電腦端把 ±1 輸入打包成 bits（Python `bnn_pack`，食譜 5.4.7）→ 784 個輸入只要 25 個 `uint32` = 100 byte，比文字少很多；板子端 `bnn_dense_sign` → `bnn_dense_score` → `bnn_argmax` 回 1 byte 類別。傳輸見第 2 章 2.4.3 |
| ② 把 ① 拆給 2 片板子平行跑再收回 | 最簡單：**依樣本切**（每塊板子分到一半的圖片，各自跑完整網路），電腦端依編號接回（第 2 章 2.4.4、`ros2/multi_device.py`）。依神經元切（每塊算一半隱藏神經元）要交換隱藏層 bits，比較複雜，不建議先做 |
| ③ 用雙核心（一核收、一核算） | 把隱藏層神經元 j 分成兩半，core0 算 `j < n_out/2`、core1 算其餘（各寫各自的 `out_bits` word，n_out/2 要是 32 的倍數才不會兩核寫同一個 word）；或 core0 收下一張圖、core1 算這一張（見第 3 章 `app_multicore.c` 一節）。⚠️ 本章沒有寫雙核版程式 |

### 5.2.9 其他校驗碼（`checksum_misc.c`）

| 名稱 | 函式 | 算法一句話 | 起始值 / 可否分段 | 測試向量（本次 PASS） |
|---|---|---|---|---|
| Adler-32 | `adler32(adler, p, n)` | a = 1 + Σbyte、b = Σ(每一步的 a)，都 mod 65521；結果高 16 位放 b、低 16 位放 a | 第一次傳 1；可分段（傳上次結果） | `"Wikipedia"` → `0x11E60398`；`""` → 1 |
| Fletcher-16 | `fletcher16(p, n)` | s1 = Σbyte、s2 = Σs1，都 mod 255；結果高 8 位放 s2、低 8 位放 s1 | 不可分段（函式沒有接續參數） | `"abcde"` → `0xC8F0`、`"abcdef"` → `0x2057`、`"abcdefgh"` → `0x0627` |
| Fletcher-32 | **檔案裡沒有**（ch05 自寫版見 5.3.11） | 16-bit 字（小端組字）相加，mod 65535 | — | `"abcde"` → `0xF04FC729`、`"abcdef"` → `0x56502D2A`、`"abcdefgh"` → `0xEBE19591` |
| XOR | `xor8(p, n)` | 全部 byte XOR | 0 | NMEA `GPGLL,5300.97914,N,00259.98174,E,125926,A` → `0x28` |
| 加總 | `sum8(p, n)` | 全部 byte 相加取低 8 位 | 0 | `"123456789"` → `0xDD` |
| LRC | `lrc8(p, n)` | `sum8` 的二補數（`0 - sum8`），Modbus ASCII 用 | — | `sum8 + lrc8 == 0` |
| 32-bit 加總 | `sum32(w, nwords)` | 以 `uint32_t` 為單位相加，溢位捨去 | 0 | `{0xFFFFFFFF, 2, 3}` → 4 |
| Internet checksum | `inet_csum(p, n)` | 每 2 byte 當**大端** 16-bit 相加，進位折回，最後取反（RFC 1071） | — | RFC 1071 範例 `00 01 f2 03 f4 f5 f6 f7` → `0x220D` |

Adler 和 Fletcher 的加速技巧（`checksum_misc.c:19-20`、`:35`）：除法很慢，所以先累加很多 byte 再取一次 mod。5552 是 zlib 用的上限：累加 5552 個 0xFF 後 b 還不會超過 32 位元（`checksum_misc.c:17`）。本次用 100,000 個 0xFF（最容易溢位）和「每 byte 都取 mod」的笨方法比對，Adler-32、Fletcher-16 都一致。

### 5.2.10 位元組順序總整理

| 函式 | 輸入怎麼讀 | 輸出怎麼排 | 跟 CPU 大小端有關嗎 |
|---|---|---|---|
| `crc32_*`、`crc32c_update`、`crc16_ccitt_false`、`crc_generic` | 一次一個 byte | 回傳整數 | 無關。`crc32_slice4` 用 4 個 byte 自己組成小端 word（`crc32.c:66-68`），不怕沒對齊 |
| CRC 放進封包 | — | `serial_proto.h:5` 的封包用小端（`memcpy` 到 `uint8_t[4]`） | 電腦端 `struct.pack("<I", crc)` |
| `sha1` / `sha0` / `sha256` | 每 4 byte 用**大端**組字（`sha1_sha0.c:11-14`、`sha256.c:20-22`） | `out[]` 大端，直接逐 byte 印 hex 就是標準寫法 | 無關 |
| `radix_sort_u32` 等 | `uint32_t` 陣列 | `uint32_t` 陣列 | 從序列埠收 byte 時要自己組；Pico、x86 都是小端，`memcpy` 即可（`app_serial.c` 的做法）；電腦端 `pack_u32` 用 `<I` |
| `bnn_*` | `uint32_t` word，bit i%32 從 LSB 算 | 同左 | 以 word 傳時同上；若題目給的是「每 byte MSB 先」的打包（例如 numpy `packbits` 預設），要轉換（食譜 5.4.5） |
| `adler32`、`fletcher16`、`xor8`、`sum8` | 一次一個 byte | 整數 | 無關 |
| `sum32` | `uint32_t` 陣列 | 整數 | 資料若是 byte 流，結果取決於你怎麼組成 word |
| `inet_csum` | 每 2 byte 當**大端**（`checksum_misc.c:66`） | 整數；放回封包時高 byte 先 | 無關 |

## 5.3 逐檔說明

所有指令都在 `預製程式碼/algo/` 資料夾執行（考場上換成你 clone 下來的路徑）。執行檔一律輸出到 repo 外面，**不要**留在 `algo/` 裡，交卷 commit 時也不要加進去：

```bash
cd ~/ncku-exam-prep/預製程式碼/algo     # 換成你的路徑
B=/tmp/algo_build; mkdir -p $B
```

### 5.3.1 `README.md`

#### 用途
`algo/` 的入口：題目關鍵字 → 檔案 → 函式（`README.md:7-18`）、API 速查（`:20-50`）、編譯指令（`:52-63`）、作者機器上的實測數字（`:65-102`，AMD Ryzen 5 5600）、考場上要改哪裡（`:104-111`）。

#### 怎麼編譯 / 執行
`README.md:54-63` 的指令本次照跑，全部通過（輸出見各檔）。README 用 `B=/tmp/t`，本章用 `B=/tmp/algo_build`，兩者都在 repo 外，效果一樣。

#### 對外介面
無（文件）。

#### 程式流程
不適用。

#### 要改的地方
無 `TODO(改這裡)`（`README.md:5` 只是說明）。

#### 實際執行輸出
README 的數字是另一台機器（Ryzen 5 5600）。本次（Xeon 2.30GHz）重量的數字和 README 對照：

| 項目 | README（Ryzen） | 本次實測（Xeon） |
|---|---|---|
| crc32_bitwise / table / slice4 | 134 / 554 / 1663 MB/s | 115.0 / 484.8 / 1445.4 MB/s |
| SHA-1 / SHA-0 / SHA-256 | 485 / 485 / 120 MB/s | 423.1 / 415.8 / 122.6 MB/s |
| qsort / merge / radix（n = 2^20） | 95.9 / 55.6 / 10.7 ms | 106.25 / 77.68 / 6.88 ms |
| BNN 784×256：`-O2` / SWAR / 硬體 popcnt | 13.2 / 9.1 / 4.2 µs | 12.09 / 8.12 / 3.47 µs |

結論一樣：slice4 最快、radix 遠快於 qsort、有硬體 popcount 的 BNN 快 3 倍以上。

#### 常見錯誤

| 症狀 | 原因 | 修法 |
|---|---|---|
| `algo/` 裡多了執行檔，被 commit 進去 | 編譯時 `-o` 沒指到 repo 外 | 用 `-o $B/xxx`；`git status` 檢查 |
| 數字跟 README 不一樣 | 不同 CPU | 正常；看倍數關係就好 |

### 5.3.2 `crc32.h`、`crc32.c`

#### 用途
CRC 家族：zlib 相容 CRC-32（三種速度的實作）、CRC-32C、CRC-16/CCITT-FALSE、任意參數的 `crc_generic`。核心檔，可以直接放進 Pico 專案。

#### 怎麼編譯 / 執行
```bash
gcc -O2 -Wall -Wextra -std=c11 crc32.c crc32_test.c -o $B/crc && $B/crc
```
預期最後一行 `結果：全部通過`（完整輸出見 5.3.3）。只編核心檔（MCU）：
```bash
arm-none-eabi-gcc -mcpu=cortex-m33 -mthumb -O2 -Wall -Wextra -std=c11 -c crc32.c -o $B/crc32.o
```

#### 對外介面

| 名稱 | 參數 | 回傳 / 效果 | 複雜度 / 記憶體 | 注意 |
|---|---|---|---|---|
| `void crc32_init(void)` | 無 | 建 `T[4][256]`、`TC[256]`、`T16[256]` 三組表，設 `inited = 1` | 一次約 256×(8+8+8) 步；表在 `.bss` 共 5636 byte（M33 `size` 實測） | 不呼叫也會在第一次查表時自動呼叫；**雙核心時要在 `multicore_launch_core1` 前呼叫**（見 5.6） |
| `uint32_t crc32_bitwise(uint32_t crc, const uint8_t *p, size_t n)` | `crc`：第一段傳 0，之後傳上次結果；`p`、`n`：資料 | zlib CRC-32 | O(8n)；不用表；M33 stack 4 byte | 最慢但最不容易錯，適合當對照組 |
| `uint32_t crc32_table(uint32_t crc, const uint8_t *p, size_t n)` | 同上 | 同上 | O(n)；用 `T[0]` 1 KB | 第一次呼叫會建表 |
| `uint32_t crc32_slice4(uint32_t crc, const uint8_t *p, size_t n)` | 同上 | 同上 | O(n)，每 4 byte 一次迴圈；用 `T[0..3]` 4 KB | `p` 不用對齊 |
| `uint32_t crc32_update(uint32_t crc, const uint8_t *p, size_t n)` | 同上 | 同上（= `crc32_slice4`） | 同 slice4 | **跟 `pico/serial_proto.c:25` 同名**，兩個檔放同一個執行檔會連結失敗（見 5.6、食譜 5.4.6） |
| `uint32_t crc32c_update(uint32_t crc, const uint8_t *p, size_t n)` | 同上 | CRC-32C（check `0xE3069283`） | O(n)；`TC` 1 KB | 只有查表版 |
| `uint16_t crc16_ccitt_false(uint16_t crc, const uint8_t *p, size_t n)` | `crc`：**第一段傳 `0xFFFF`**，之後傳上次結果 | CRC-16/IBM-3740（check `0x29B1`） | O(n)；`T16` 512 byte | 傳 0 開始 = CRC-16/XMODEM（沒有 xorout，所以 init 0 就是 XMODEM） |
| `crc_param_t` | `width`、`poly`、`init`、`refin`、`refout`、`xorout` | 結構（M33 上 20 byte） | — | 欄位順序固定，照 5.2.4 表格填 |
| `uint32_t crc_generic(const crc_param_t *c, const uint8_t *p, size_t n)` | 參數、資料 | 照參數算出的 CRC | O(8n) 次位移（refin 時每 byte 再加 8 次反轉）；不用表；M33 stack 32 byte | **width 只能 8..32**；**不能分段**（每次呼叫都重新套 init、xorout） |

`crc32_bitwise` / `table` / `slice4` / `update` / `crc32c_update` 的分段規則跟 zlib 一樣：`c = f(0, a, na); c = f(c, b, nb);` 等於 `f(0, a+b, na+nb)`。原理：函式開頭 `crc = ~crc`、結尾 `return ~crc`（`crc32.c:44,50`），把 init 和 xorout 都藏在裡面，所以傳 0 進去 = 從 `0xFFFFFFFF` 開始。

#### 程式流程

1. `crc32.c:10-12` 三個多項式常數：`POLY32R = 0xEDB88320`（CRC-32 反轉寫法）、`POLY32CR = 0x82F63B78`（CRC-32C 反轉寫法）、`POLY16 = 0x1021`（CRC-16 不反轉）。
2. `crc32.c:14-17` 表格與 `inited` 旗標，全部是 `static`（放 `.bss`，不佔 stack）。
3. `make_entry_r`（`crc32.c:20-24`）：對一個 byte 做 8 次「右移，最低位是 1 就 XOR 多項式」。`polyr & (0u - (c & 1u))` 是無分支寫法：最低位是 1 時 `0u - 1 = 0xFFFFFFFF`，AND 後就是 `polyr`；是 0 時結果 0。
4. `crc32_init`（`crc32.c:26-40`）：
   - `:28-29` 建 `T[0]` 和 `TC`。
   - `:30-33` 建 `T16`：不反轉的 CRC 從最高位開始，`i << 8` 放到 16 位的高 8 位，左移 8 次。
   - `:36-38` 建 slice-by-4 延伸表：`T[t][i] = (T[t-1][i] >> 8) ^ T[0][T[t-1][i] & 0xFF]`，等於「再多吃一個 0 byte」。
5. `crc32_bitwise`（`crc32.c:43-51`）：`crc = ~crc` → 每 byte `crc ^= *p++` 後做 8 次右移步驟 → `return ~crc`。
6. `crc32_table`（`crc32.c:54-59`）：沒建表就先建（`:55`），每 byte 一次查表（`:57`）。
7. `crc32_slice4`（`crc32.c:62-75`）：每次取 4 byte 組成小端 word XOR 進 `crc`（`:67-68`），查 4 張表（`:69-70`）；剩下 0~3 byte 用一般查表（`:73`）。
8. `crc32_update`（`crc32.c:77-79`）：直接呼叫 `crc32_slice4`。
9. `crc32c_update`（`crc32.c:82-87`）：跟 `crc32_table` 一樣，只是查 `TC`。
10. `crc16_ccitt_false`（`crc32.c:90-94`）：不反轉 → 左移，用「高 8 位 XOR 輸入 byte」查表：`crc = (crc << 8) ^ T16[((crc >> 8) ^ *p++) & 0xFF]`。沒有 `~`，所以 init 由呼叫者傳。
11. `reflect`（`crc32.c:97-101`）：把 `v` 的低 `bits` 位反轉。
12. `crc_generic`（`crc32.c:103-117`）：
    - `:104-105` `top` = 最高位遮罩、`mask` = width 位全 1（width = 32 時特別處理，避免 `1u << 32`）。
    - `:106` `crc = init & mask`。
    - `:109` refin 時先反轉輸入 byte。
    - `:110` `crc ^= b << (c->width - 8)` 把 byte 放到最高 8 位（**width < 8 時位移量是負數 → 未定義行為**）。
    - `:111-112` 8 次左移步驟、`:113` 遮罩。
    - `:115-116` refout 時反轉整個 width 位，再 XOR `xorout`。

#### 要改的地方

| 行號 | 現在的值 | 意思 | 什麼情況要改、改成什麼 |
|---|---|---|---|
| `crc32.c:10` | `#define POLY32R 0xEDB88320u` | `crc32_bitwise/table/slice4/update` 用的反轉多項式 | 題目要別種「refin=refout=1、init=xorout=0xFFFFFFFF」的 32-bit CRC 而且要快：換成新多項式的 32 位反轉值，例如 CRC-32/AUTOSAR `0xF4ACFB13` 反轉 = `0xC8DF352F`、CRC-32D `0xA833982B` 反轉 = `0xD419CC15`。改完 `crc32_test.c` 的 CRC-32 斷言會 FAIL（正常），改用 `crc_generic` 對照。init 或 xorout 不同時不要改這行，用食譜 5.4.1 的 `crcf` |
| `crc32.c:11` | `#define POLY32CR 0x82F63B78u` | CRC-32C 反轉多項式 | 一般不改 |
| `crc32.c:12` | `#define POLY16 0x1021u` | `crc16_ccitt_false` 的多項式（不反轉） | 要別的「不反轉、無 xorout」的 16-bit CRC，例如 CRC-16/UMTS 換 `0x8005`（init 傳 0）、CRC-16/T10-DIF 換 `0x8BB7` |

`POLY32R` 的反轉值可以用 `crc32.c:97` 的 `reflect(poly, 32)` 算，或在 Python：`int(f"{0xF4ACFB13:032b}"[::-1], 2)`。本次用 Python 算出 `0xC8DF352F`、`0xD419CC15`；並在 repo 外的複本把 `POLY32R` 改成 `0xC8DF352Fu`，`crc32_update`、`crc32_bitwise`、切兩段算 `"123456789"` 都得到 `0x1697D06A`（= CRC-32/AUTOSAR 的 check）。

#### 實際執行輸出
見 5.3.3（`crc32_test`）與 5.3.3 的「CRC 規格表」輸出。

#### 常見錯誤

| 症狀 | 原因 | 修法 |
|---|---|---|
| 結果是正確值的 `~`（例如 `0x340BC6D9`） | 多做或少做最後的 XOR | 對照 5.2.4：`0x340BC6D9` 是 JAMCRC = zlib 少 XOR |
| 分段算的結果跟一次算不同 | 第二段又傳 0 | 第二段要傳第一段的回傳值 |
| `crc16_ccitt_false` 結果是 `0x31C3` | 第一段傳了 0 | CCITT-FALSE 要傳 `0xFFFF`；`0x31C3` 是 XMODEM |
| `crc_generic` 回傳 0 或亂數（width 5、7） | width < 8 未定義行為（本次 UBSan：`crc32.c:110:18: runtime error: shift exponent -1 is negative`，回傳 0） | 改用食譜 5.4.1 的 `crc_bits` |
| 用 `crc_generic` 分兩段算錯 | `crc_generic` 每次都重套 init/xorout | 整份一次算，或用食譜 5.4.1 的 `crcf_start/feed/finish` |
| 連結錯誤 `multiple definition of 'crc32_update'` | 同一個執行檔也有 `pico/serial_proto.c` | 見食譜 5.4.6 |
| 題目說 poly = `0xEDB88320`，填進 `crc_generic` 結果錯 | 那是反轉寫法 | 填 `0x04C11DB7` + refin=refout=1 |

### 5.3.3 `crc32_test.c`

#### 用途
電腦上的 CRC 測試與測速。只在 host 用。

#### 怎麼編譯 / 執行
```bash
gcc -O2 -Wall -Wextra -std=c11 crc32.c crc32_test.c -o $B/crc && $B/crc
```

#### 對外介面
無（`main` 回傳失敗數，0 = 全過）。

#### 程式流程
1. `crc32_test.c:7-8` 4 MB 測速用的靜態陣列 `big`。
2. `:12` `crc32_init()`。
3. `:13-19` 標準向量：三種 CRC-32 實作、CRC-32C、CRC-16、空字串 = 0。
4. `:21-35` 規格表 10 列，每列 `crc_generic` 對 `"123456789"`。
5. `:37-51` 隨機資料：200 組隨機起點（0~63，故意不對齊）、隨機長度（0~2999），比對 bitwise / table / slice4 / 切兩段的 update / `crc_generic`，以及 CRC-32C 切兩段 vs `crc_generic`。
6. `:53-64` 每個版本跑 5 次取最快，印 ms 與 MB/s。
7. `:66` `return test_end()`。

#### 要改的地方

| 行號 | 現在的值 | 意思 | 什麼情況要改、改成什麼 |
|---|---|---|---|
| `crc32_test.c:7` | `#define BIG (4u << 20)` | 測速資料 4 MB | 想測題目的實際資料量就改（例如 `(64u << 10)` = 64 KB）；只影響測速 |

#### 實際執行輸出
本次實測（host gcc 13.3、x86_64 Xeon 2.30GHz、`-O2`）：

```text
[CRC 標準向量]
  PASS  crc32_bitwise("123456789")
  PASS  crc32_table
  PASS  crc32_slice4
  PASS  crc32c = 0xE3069283
  PASS  crc16_ccitt_false = 0x29B1
  PASS  空字串 CRC-32 = 0
[通用 CRC 對照參數表]
  PASS  CRC-32
  PASS  CRC-32/BZIP2
  PASS  CRC-32/MPEG-2
  PASS  CRC-32C
  PASS  CRC-16/CCITT-FALSE
  PASS  CRC-16/XMODEM
  PASS  CRC-16/KERMIT
  PASS  CRC-16/MODBUS
  PASS  CRC-16/ARC
  PASS  CRC-8
[隨機資料：各版本一致 + 增量 API]
  PASS  200 組隨機長度：bitwise/table/slice4/分段/generic 全相同
[Benchmark：4 MB，取 5 次最快]
  crc32_bitwise      36.47 ms    115.0 MB/s
  crc32_table         8.65 ms    484.8 MB/s
  crc32_slice4        2.90 ms   1445.4 MB/s
  crc32c(table)       8.58 ms    488.6 MB/s
  crc16(table)       11.85 ms    353.9 MB/s
結果：全部通過
```

ch05 自寫 `crcspec.c`（34 種規格，見 5.2.4；編譯 `gcc -O2 -Wall -Wextra -std=c11 -I<algo> crcspec.c <algo>/crc32.c`）本次輸出節錄（每列格式相同，全部 34 列 PASS）：

```text
CRC-32/ISO-HDLC (zlib)           w=32 poly=0x04C11DB7 init=0xFFFFFFFF refin=1 refout=1 xorout=0xFFFFFFFF -> 0xCBF43926 PASS
CRC-32/CKSUM (POSIX)             w=32 poly=0x04C11DB7 init=0x00000000 refin=0 refout=0 xorout=0xFFFFFFFF -> 0x765E7680 PASS
CRC-24/OPENPGP                   w=24 poly=0x00864CFB init=0x00B704CE refin=0 refout=0 xorout=0x00000000 -> 0x0021CF02 PASS
CRC-16/IBM-SDLC (X-25)           w=16 poly=0x00001021 init=0x0000FFFF refin=1 refout=1 xorout=0x0000FFFF -> 0x0000906E PASS
CRC-12/UMTS (refin!=refout)      w=12 poly=0x0000080F init=0x00000000 refin=0 refout=1 xorout=0x00000000 -> 0x00000DAF PASS
CRC-8/MAXIM-DOW (1-Wire)         w= 8 poly=0x00000031 init=0x00000000 refin=1 refout=1 xorout=0x00000000 -> 0x000000A1 PASS
34 個規格，0 個失敗
```

同一支 `crc32_test.c` 在 qemu-riscv32（rv32imac + Zbb、picolibc，見 5.5.5）也是 17 項全 PASS。

#### 常見錯誤

| 症狀 | 原因 | 修法 |
|---|---|---|
| 改了 `POLY32R` 之後 4 項 FAIL | 斷言寫死 zlib 的 check 值 | 預期內；用 `crc_generic` 的結果比 |
| `undefined reference to clock_gettime`（交叉編譯） | `test_util.h` 用 POSIX 計時，MCU 沒有 | `*_test.c` 只在電腦上編 |

### 5.3.4 `sha1_sha0.h`、`sha1_sha0.c`

#### 用途
SHA-1 和 SHA-0 共用一份程式，用 `is_sha0` 旗標切換。輸出 20 byte。

#### 怎麼編譯 / 執行
```bash
gcc -O2 -Wall -Wextra -std=c11 sha1_sha0.c sha256.c sha_test.c -o $B/sha && $B/sha
```
（輸出見 5.3.6）

#### 對外介面

| 名稱 | 參數 | 回傳 / 效果 | 複雜度 / 記憶體 | 注意 |
|---|---|---|---|---|
| `sha1_ctx` | `h[5]` 狀態、`total` 已餵 byte 數（`uint64_t`）、`buf[64]` 尾巴、`used`、`is_sha0` | 結構，M33 上 104 byte | — | 放 `static` 或全域；一個 ctx 同時只能算一份資料 |
| `void sha1_init(sha1_ctx *c, int is_sha0)` | `is_sha0`：**1 = SHA-0、0 = SHA-1** | 設初值 | O(1) | 參數意思容易記反，`sha1_sha0.h:9` 有註解 |
| `void sha1_update(sha1_ctx *c, const uint8_t *p, size_t n)` | 資料 | 吃進資料；滿 64 byte 就壓縮一次 | O(n)；M33 stack：本函式 24 byte + `compress` 128 byte | 整塊 64 byte 直接從 `p` 算，不複製（`sha1_sha0.c:53`） |
| `void sha1_final(sha1_ctx *c, uint8_t out[20])` | 輸出緩衝 | 補 padding、寫 20 byte 結果（大端） | 1~2 次壓縮 | 呼叫後 ctx 不能再 `update`，要重新 `init` |
| `void sha1(const uint8_t *p, size_t n, uint8_t out[20])` | 資料、輸出 | 一次算完 SHA-1 | M33 stack 128 byte（含 ctx）+ 下層 | — |
| `void sha0(const uint8_t *p, size_t n, uint8_t out[20])` | 同上 | 一次算完 SHA-0 | 同上 | — |

所有函式都不用 `malloc`。`total` 是 `uint64_t`，資料長度上限遠超過 Pico 的記憶體。

#### 程式流程
1. `sha1_sha0.c:9` `ROTL` 巨集；rv32 Zbb 會編成 `rori`/`rol` 指令（本次 objdump：`sha1_sha0.o` 有 5 個旋轉指令）。
2. `load_be32`（`:11-14`）：大端序讀 4 byte。
3. `compress`（`:16-38`）：
   - `:18` 讀 16 個大端 word 到 `w[16]`。
   - `:19` 取出 a..e。
   - `:20-36` 80 回合：`t < 16` 直接用 `w[t]`；之後用 16 格循環陣列 `w[(t-3)&15] ^ w[(t-8)&15] ^ w[(t-14)&15] ^ w[t&15]`（`w[t&15]` 此時存的是 W[t-16]），SHA-1 再左旋 1（`:26`），寫回 `w[t&15]`（`:27`）。
   - `:30-33` 四段回合函式與常數 `0x5A827999`、`0x6ED9EBA1`、`0x8F1BBCDC`、`0xCA62C1D6`。
   - `:34-35` `tmp = ROTL(a,5) + f + e + k + wt`，狀態往後挪。
   - `:37` 加回 `h[]`。
4. `sha1_init`（`:40-44`）：五個初值 `0x67452301 0xEFCDAB89 0x98BADCFE 0x10325476 0xC3D2E1F0`，`total = used = 0`。
5. `sha1_update`（`:46-55`）：`total += n`；`buf` 有上次的尾巴就先補滿 64（不滿就 return，`:48-52`）；然後整塊直接壓縮（`:53`）；剩下的存進 `buf`（`:54`）。
6. `sha1_final`（`:57-71`）：`bits = total*8`；補 `0x80`；`used > 56` 就補 0 到 64 先壓一次（`:60-63`）；補 0 到 56；寫 8 byte 大端長度（`:65`）；壓縮；輸出 5 個 word 大端（`:67-70`）。
7. `sha1` / `sha0`（`:73-78`）：在 stack 上開 ctx，init → update → final。

#### 要改的地方
沒有 `TODO(改這裡)`。要「SHA-1 改成 SHA-0」不用改程式，呼叫 `sha0()` 或 `sha1_init(&c, 1)` 即可。

#### 實際執行輸出
見 5.3.6。另外 ch05 自寫 Python 對照：200 組隨機資料（0~299 byte），C 的 `sha0` 和 Python 獨立實作（食譜 5.4.7）、C 的 `sha1` 和 `hashlib.sha1`，本次全部一致。

#### 常見錯誤

| 症狀 | 原因 | 修法 |
|---|---|---|
| 「SHA-0」結果跟 `hashlib.sha1` 一樣 | `sha1_init(&c, 0)`，0 是 SHA-1 | SHA-0 傳 1 |
| 每包分開算出來的值不對 | 每包都 `init`/`final` | 整份資料只 `init` 一次、最後 `final` 一次 |
| 印出來的 hex 順序怪 | 把 `out` 當 `uint32_t` 印 | 逐 byte `%02x` 印（`test_util.h:35-37` 的 `to_hex`） |
| `final` 後再 `update` 結果亂掉 | ctx 已經補過 padding | 重新 `sha1_init` |

### 5.3.5 `sha256.h`、`sha256.c`

#### 用途
SHA-256，API 風格跟 SHA-1 一樣。輸出 32 byte。

#### 怎麼編譯 / 執行
同 5.3.4（`sha_test.c` 一起測）。

#### 對外介面

| 名稱 | 參數 | 回傳 / 效果 | 複雜度 / 記憶體 | 注意 |
|---|---|---|---|---|
| `sha256_ctx` | `h[8]`、`total`、`buf[64]`、`used` | 結構，M33 上 112 byte | — | 沒有演算法旗標 |
| `void sha256_init(sha256_ctx *c)` | — | 設 8 個初值 | O(1) | — |
| `void sha256_update(sha256_ctx *c, const uint8_t *p, size_t n)` | 資料 | 吃進資料 | O(n)，**逐 byte 複製進 `buf`**；M33 stack 24 + `compress` 336 byte | 比 SHA-1 的 update 多一次複製 |
| `void sha256_final(sha256_ctx *c, uint8_t out[32])` | 輸出 | 補 padding、寫 32 byte（大端） | 1~2 次壓縮 | — |
| `void sha256(const uint8_t *p, size_t n, uint8_t out[32])` | 資料、輸出 | 一次算完 | M33 stack 136 byte + 下層 | — |

#### 程式流程
1. `sha256.c:6` `ROTR`；`:8-16` 64 個常數 `K`（前 64 個質數立方根的小數部分）。
2. `compress`（`:18-40`）：讀 16 個大端 word（`:20-22`）；擴展到 64 個（`:23-27`，`s0`、`s1`）；8 個狀態 `s[0..7]` = a..h（`:28`）；64 回合（`:29-38`）；加回（`:39`）。`w[64]` 在 stack 上 256 byte，是 M33 上 `compress` 用 336 byte stack 的主因。
3. `sha256_init`（`:42-47`）：8 個初值。
4. `sha256_update`（`:49-55`）：逐 byte 放進 `buf`，滿 64 就壓縮。
5. `sha256_final`（`:57-66`）：同 SHA-1 的 padding，輸出 8 個 word 大端。
6. `sha256`（`:68-70`）：一次算完。

#### 要改的地方
沒有 `TODO(改這裡)`。

#### 實際執行輸出
見 5.3.6。另 200 組隨機資料和 `hashlib.sha256` 比對本次全部一致。

#### 常見錯誤

| 症狀 | 原因 | 修法 |
|---|---|---|
| Pico 上 hard fault / 亂跳 | stack 不夠（壓縮函式要 336 byte，加上呼叫者） | ctx 放 `static`；在 core1 上算時確認 `PICO_CORE1_STACK_SIZE`（預設 0x800 = 2 KB，`pico/multicore.h:32`） |
| 輸出長度 20 | 用了 SHA-1 的緩衝或 `to_hex(d, 20, ...)` | SHA-256 是 32 byte |

### 5.3.6 `sha_test.c`

#### 用途
SHA-1、SHA-0、SHA-256 的測試與測速。只在 host 用。

#### 怎麼編譯 / 執行
```bash
gcc -O2 -Wall -Wextra -std=c11 sha1_sha0.c sha256.c sha_test.c -o $B/sha && $B/sha
```

#### 對外介面
`check_hex(algo, msg, n, want)`（`sha_test.c:12-20`）：`algo` 1 = SHA-1、0 = SHA-0、2 = SHA-256；不一致時印出「得到 / 應為」。

#### 程式流程
1. `sha_test.c:24-34` 7 組標準向量（5.2.6 表格）。
2. `:36-49` 一百萬個 `'a'`：用串流 API 每次餵 1000 byte、餵 1000 次。
3. `:51-71` 300 組隨機長度（0~999），每段長度 0~99 隨機切，三種演算法都比「串流」和「一次算」。
4. `:73-80` 4 MB 測速。

#### 要改的地方
無 `TODO(改這裡)`。`sha_test.c:8` 的 `BIG` 可改測速資料量。

#### 實際執行輸出
本次實測（host gcc 13.3、x86_64、`-O2`）：

```text
[標準向量]
  PASS  SHA-1("abc")
  PASS  SHA-0("abc")
  PASS  SHA-1("")
  PASS  SHA-1(56 字元，需 2 塊 padding)
  PASS  SHA-256("abc")
  PASS  SHA-256("")
  PASS  SHA-256(56 字元)
[一百萬個 'a'，用串流 API 每次餵 1000 byte]
  PASS  SHA-1(1e6 x 'a')
  PASS  SHA-256(1e6 x 'a')
[隨機切段：串流結果 == 一次算]
  PASS  300 組 x 3 種演算法
[Benchmark：4 MB，取 5 次最快]
  sha1         9.91 ms    423.1 MB/s
  sha0        10.09 ms    415.8 MB/s
  sha256      34.20 ms    122.6 MB/s
結果：全部通過
```

qemu-riscv32（Zbb）本次也全部 PASS。

#### 常見錯誤

| 症狀 | 原因 | 修法 |
|---|---|---|
| 印出「得到 … 應為 …」 | 改壞了 `compress` 或 padding | 先跑 `"abc"` 和 56 字元那組，56 字元是「多一塊 padding」的邊界 |

### 5.3.7 `sort.h`、`sort.c`

#### 用途
`uint32_t` 排序與合併。暫存區由呼叫者提供（不用 `malloc`）。

#### 怎麼編譯 / 執行
```bash
gcc -O2 -Wall -Wextra -std=c11 sort.c sort_test.c -o $B/sort && $B/sort
```
（輸出見 5.3.8）

#### 對外介面

| 名稱 | 參數 | 回傳 / 效果 | 複雜度 / 記憶體 | 注意 |
|---|---|---|---|---|
| `void insertion_sort_u32(uint32_t *a, size_t n)` | 陣列、個數 | 原地遞增排序 | O(n²)；0 額外；M33 stack 16 byte | n=10000 本次 6.69 ms，比 radix 慢 141 倍 |
| `void merge_sort_u32(uint32_t *a, size_t n, uint32_t *tmp)` | `tmp` 至少 n 個 | 原地遞增排序（結果回到 `a`），穩定 | O(n log n)；n 個 `tmp`；M33 stack 64 byte | 迭代式，不遞迴 |
| `void radix_sort_u32(uint32_t *a, size_t n, uint32_t *tmp)` | `tmp` 至少 n 個 | 原地遞增排序（結果回到 `a`），穩定 | O(n)，4 趟；n 個 `tmp`；**M33 stack 1064 byte**（`cnt[256]`） | 有號數 / 遞減見 5.2.7 |
| `void merge_two_sorted(const uint32_t *a, size_t na, const uint32_t *b, size_t nb, uint32_t *out)` | 兩個已排序陣列、輸出 | `out[na+nb]` 有序 | O(na+nb)；M33 stack 28 byte | `out` **不能**跟 `a`、`b` 重疊 |
| `KWAY_MAX` | — | 16 | — | `kway_merge` 最多段數 |
| `void kway_merge(const uint32_t *const lists[], const size_t lens[], int k, uint32_t *out)` | k 個已排序陣列的指標與長度 | `out` 有序（長度 = Σlens） | O(n×k)；M33 stack 88 byte | **k > 16 會被截成 16，多的段直接不見，沒有錯誤訊息** |

#### 程式流程
1. `sort.c:4` `copy_u32`：自己寫的複製迴圈（不依賴 `string.h`）。
2. `sort.c:6` `RUN 32`：merge sort 先用 insertion sort 排好每 32 個。
3. `insertion_sort_u32`（`:8-15`）：每個新元素往左找位置，比它大的往右挪（`:12`）。
4. `merge_run`（`:18-23`）：合併兩段，`src[i] <= src[j]` 先拿左邊（穩定）。
5. `merge_sort_u32`（`:26-39`）：`:27-28` 每 RUN 個先排好；`:30-36` 寬度 32、64、128…每次把相鄰兩段合併到另一個陣列，然後交換 `src`/`dst`（ping-pong）；`:38` 結果若停在 `tmp` 就抄回 `a`。
6. `radix_sort_u32`（`:44-57`）：`n < 2` 直接返回（`:46`）；`shift = 0, 8, 16, 24` 四趟（`:47`）；每趟計數（`:49`）、全同就跳過（`:50`）、前綴和（`:52`）、穩定搬移（`:53`）、交換（`:54`）；跳過奇數趟時結果可能在 `tmp`，`:56` 抄回。
7. `merge_two_sorted`（`:59-65`）：標準雙指標合併，`<=` 穩定。
8. `kway_merge`（`:67-78`）：`pos[16]` 記每段走到哪（`:68`）；`:69` k 截到 `KWAY_MAX`；每次掃 k 個頭找最小（`:72-74`，`<` 所以相等取編號小的）；全部用完就結束（`:75`）。

#### 要改的地方

| 行號 | 現在的值 | 意思 | 什麼情況要改、改成什麼 |
|---|---|---|---|
| `sort.c:6` | `#define RUN 32` | merge sort 第一步每組多大 | 16~64 都可（註解）；一般不用改 |
| `sort.c:69` | `if (k > KWAY_MAX) k = KWAY_MAX;` | 段數上限 | 段數超過 16 → 改 `sort.h:31` 的 `KWAY_MAX`（`pos[]` 會跟著變大）；或改用兩兩合併（食譜 5.4.3）。**不要依賴這行默默截斷** |
| `sort.h:31` | `#define KWAY_MAX 16` | 同上 | 同上 |

#### 實際執行輸出
見 5.3.8。

#### 常見錯誤

| 症狀 | 原因 | 修法 |
|---|---|---|
| 負數排在最後面 | 把 `int32_t` 當 `uint32_t` 排 | 前後各 `^= 0x80000000u` |
| 合併結果少了一大段 | `kway_merge` 的 k > 16 | 加大 `KWAY_MAX` 或兩兩合併 |
| `merge_two_sorted` 結果亂 | `out` 跟輸入重疊 | 另外開一個輸出陣列 |
| Pico 上 hard fault | `a`、`tmp` 放 stack（例如 `uint32_t a[4096];` 寫在函式裡 = 16 KB） | 改成 `static`（`sort.h:11` 的建議） |
| 結果「幾乎有序」 | `tmp` 比 n 小，寫出界 | `tmp` 至少 n 個 |

### 5.3.8 `sort_test.c`

#### 用途
跟 `qsort` 比對正確性、合併測試、測速。只在 host 用。

#### 怎麼編譯 / 執行
```bash
gcc -O2 -Wall -Wextra -std=c11 sort.c sort_test.c -o $B/sort && $B/sort
```
這支程式用 5 個 4 MB 的靜態陣列（`sort_test.c:8`，共 20 MB）。

#### 對外介面
`cmp_u32`（`sort_test.c:10-13`）：給 `qsort` 用的比較函式，寫成 `(p > q) - (p < q)`，不會像 `p - q` 那樣溢位。`fill(n, mask)`（`:15-17`）：`mask` 小時很多重複值。

#### 程式流程
1. `sort_test.c:20-36` 正確性：n ∈ {0, 1, 2, 3, 31, 32, 33, 100, 1000, 4097, 100000} × mask ∈ {全部、0xFF、0x3、0xFFFF0000}，三種排序都跟 `qsort` 比（insertion 只測 n ≤ 4097）。
2. `:38-53` 合併：故意 1/3 : 2/3 不平均切兩段 → `merge_two_sorted`；不等長切 4 段 → `kway_merge`。
3. `:55-72` 測速：qsort、merge、radix、兩半 radix + merge、memcpy 本身、n=10000 的 insertion 和 radix。

#### 要改的地方

| 行號 | 現在的值 | 意思 | 什麼情況要改、改成什麼 |
|---|---|---|---|
| `sort_test.c:7` | `#define N (1u << 20)` | 測速筆數 | 想模擬題目的資料量就改；RAM 不夠時改小 |

#### 實際執行輸出
本次實測（host gcc 13.3、x86_64、`-O2`）：

```text
[正確性：各種 n 與資料分布，結果需與 qsort 相同]
  PASS  insertion_sort_u32
  PASS  merge_sort_u32
  PASS  radix_sort_u32（含大量重複、高位相同的資料）
[合併：模擬 2 塊板子 / 4 個核心各排一段]
  PASS  merge_two_sorted
  PASS  kway_merge (k=4)
[Benchmark：n = 1048576 個隨機 uint32，取 3 次最快]
  qsort (libc)         106.25 ms
  merge_sort_u32        77.68 ms
  radix_sort_u32         6.88 ms
  2x radix(半) + merge  11.01 ms（單核模擬；真的分兩核/兩板時只算一半+合併）
  （memcpy 本身          0.28 ms，以上都含這一次複製）
  insertion n=10000      6.98 ms（O(n^2)，大 n 千萬別用）
  radix     n=10000      0.08 ms
結果：全部通過
```

各種 n 的比較見 5.5.3。

#### 常見錯誤

| 症狀 | 原因 | 修法 |
|---|---|---|
| 交叉編譯時 RAM 爆掉 | 20 MB 靜態陣列 | 這支只在電腦上跑 |

### 5.3.9 `bnn.h`、`bnn.c`

#### 用途
BNN / eBNN 推論零件：打包、XNOR-popcount 內積、隱藏層（二值輸出）、輸出層（整數分數）、argmax、BN 折門檻。推論路徑沒有浮點、沒有 `malloc`。

#### 怎麼編譯 / 執行
```bash
gcc -O2 -Wall -Wextra -std=c11 bnn.c bnn_test.c -o $B/bnn && $B/bnn
gcc -O2 -Wall -Wextra -std=c11 -DBNN_SWAR_POPCOUNT bnn.c bnn_test.c -o $B/bnn_swar && $B/bnn_swar
gcc -O2 -march=native -Wall -Wextra -std=c11 bnn.c bnn_test.c -o $B/bnn_nat && $B/bnn_nat
```

#### 對外介面

| 名稱 | 參數 | 回傳 / 效果 | 複雜度 / 記憶體 | 注意 |
|---|---|---|---|---|
| `BNN_WORDS(n)` | bit 數 | `(n + 31) / 32` 個 word | — | 宣告陣列用 |
| `static inline int bnn_popcount(uint32_t x)` | 32-bit 值 | 1 的個數 | GCC 預設用 `__builtin_popcount`；定義 `BNN_SWAR_POPCOUNT` 改用純 C SWAR | M33 沒有 popcount 指令，`__builtin_popcount` 變成呼叫 `__popcountsi2`（本次 objdump 確認），建議加 `-DBNN_SWAR_POPCOUNT`；rv32 Zbb 變成 1 條 `cpop` |
| `bnn_layer_t` | `n_in`、`n_out`、`W`、`thr`、`flip` | 一層的描述（M33 上 20 byte） | — | `W` 有 `n_out` 列，每列 `BNN_WORDS(n_in)` 個 word |
| `void bnn_pack(const int8_t *v, int n, uint32_t *out)` | ±1（或任何整數）向量 | `v[i] > 0` → bit 1，否則 0 | O(n)；`out` 要 `BNN_WORDS(n)` 個 | 0 當 -1 |
| `int bnn_get_bit(const uint32_t *bits, int i)` | bits、索引 | 第 i 個 bit（0/1） | O(1) | 除錯用 |
| `int32_t bnn_dot(const uint32_t *a, const uint32_t *w, int n)` | 兩個打包向量、長度 | ±1 內積，範圍 -n..n，和 n 同奇偶 | O(n/32)；M33 stack 40 byte | `n <= 0` 回 0；尾巴自動 mask |
| `void bnn_dense_sign(const bnn_layer_t *L, const uint32_t *in, uint32_t *out_bits)` | 層、輸入 bits | `out_bits` 第 j 位 = `(flip[j] ? -dot : dot) >= thr[j]` | O(n_out × n_in/32)；`out_bits` 要 `BNN_WORDS(n_out)` 個 | **`thr` 不能是 NULL**（`bnn.c:31` 直接讀）；`flip` 可 NULL |
| `void bnn_dense_score(const bnn_layer_t *L, const uint32_t *in, int32_t *score)` | 層、輸入 bits | `score[j] = dot_j + thr[j]`（`thr` 當 bias，可 NULL） | 同上 | 最後一層用 |
| `int bnn_argmax(const int32_t *s, int n)` | 分數 | 最大值的索引，平手取小的 | O(n) | — |
| `void bnn_fold_bn(float gamma, float beta, float mean, float std, float bias, int32_t *thr, uint8_t *flip)` | BN 參數（`std = sqrt(var + eps)`，自己先算好）、前一步的 bias | 輸出整數門檻與 flip | O(1)；用 float | 離線或開機時每個神經元算一次 |

#### 程式流程
1. `bnn_pack`（`bnn.c:4-8`）：先把 `out` 清 0（尾巴自然是 0），再對 `v[i] > 0` 的位置 `out[i >> 5] |= 1u << (i & 31)`。
2. `bnn_get_bit`（`:10-12`）。
3. `bnn_dot`（`:14-23`）：完整的 word 做 `popcount(~(a ^ w))` 累加（`:17-18`）；最後一個 word 只看低 `n & 31` 位（`:19-21`，`n` 是 32 的倍數時 mask 全 1）；回傳 `2*match - n`（`:22`）。
4. `bnn_dense_sign`（`:25-33`）：`stride = BNN_WORDS(n_in)`；清 `out_bits`；對每個 j：`d = bnn_dot(in, W + j*stride, n_in)`（`:29`），`flip[j]` 就取負（`:30`），`d >= thr[j]` 設 bit（`:31`）。
5. `bnn_dense_score`（`:35-39`）：`dot + (thr ? thr[j] : 0)`。
6. `bnn_argmax`（`:41-45`）。
7. `ceil_f`（`:48-51`）：不用 `<math.h>` 的無條件進位（往 0 截斷後，若小於原值就 +1）。
8. `bnn_fold_bn`（`:53-63`）：gamma = 0 特判（`:55-59`）；`t = mean - bias - beta*std/gamma`（`:60`）；gamma > 0 → `thr = ceil(t)`、flip 0；否則 `thr = ceil(-t)`、flip 1（`:61-62`）。

#### 要改的地方
`bnn.c`、`bnn.h` 沒有 `TODO(改這裡)`；要改的是 `bnn_test.c` 的範例網路（5.3.10）和編譯旗標：

| 位置 | 現在 | 意思 | 什麼情況要改 |
|---|---|---|---|
| `bnn.h:35` | `#if defined(__GNUC__) && !defined(BNN_SWAR_POPCOUNT)` | 選 popcount 實作 | Pico ARM（M33）編譯時加 `-DBNN_SWAR_POPCOUNT`；Pico RISC-V 不用加（SDK 預設 `-march` 含 `zbb`，見 5.5.4） |

#### 實際執行輸出
見 5.3.10。

#### 常見錯誤

| 症狀 | 原因 | 修法 |
|---|---|---|
| dot 差一點點、n 不是 32 的倍數時才錯 | 自己寫的內積沒 mask 尾巴 | 用 `bnn_dot`，或照 `bnn.c:19-21` 加 mask |
| 分類全錯但 dot 對 | 權重 bit 順序不同（題目是 MSB 先） | 食譜 5.4.5 的 `bnn_from_packbits` 轉換 |
| 隱藏層全 0 或全 1 | `flip` 沒給（gamma < 0 的神經元方向反了），或 thr 用了浮點門檻直接截斷 | 用 `bnn_fold_bn` 算 thr、flip |
| 輸入為 0 的位置結果不同 | `bnn_pack` 把 0 當 -1；題目的 sign(0) 可能是 +1 | 打包前自己決定：`v[i] = (x[i] >= 0) ? 1 : -1` |
| `bnn_dense_sign` 當掉 | `thr` 傳 NULL | 隱藏層一定要給 `thr` |

### 5.3.10 `bnn_test.c`

#### 用途
① 和笨方法比對 ② 2 層範例網路（換權重時的範本）③ 784×256 測速。只在 host 用。

#### 怎麼編譯 / 執行
見 5.3.9。

#### 對外介面
`predict(x)`（`bnn_test.c:24-32`）：輸入 40 bit → `bnn_dense_sign(L1)` → `bnn_dense_score(L2)` → `bnn_argmax`。這就是一個完整推論的寫法，可以直接抄去 Pico。

#### 程式流程
1. `bnn_test.c:10-14` 範例網路說明：隱藏神經元 c 的權重 = 原型 P_c；BN（gamma=1, beta=0, mean=20, std=1）→ 門檻 20；dot = 40 - 2×漢明距離 ≥ 20 ⇔ 跟原型差 ≤ 10 bit 才亮；輸出層第 c 列只有 bit c = 1。
2. `:15-22` 尺寸、`W1`（4 列 × 2 word）、`W2`（4 列 × 1 word）、`thr1`、`flip1`。
3. `:38-50` 12 種 n（1~1024）× 50 組，`bnn_dot` vs 逐元素乘加；`bnn_get_bit` vs 原值；尾巴塞垃圾（`:46`）。
4. `:52-70` 20000 組隨機 n（1~200）與 BN 參數（gamma 含 0 與負數），`bnn_dense_sign` vs 浮點 BN 再取 sign。
5. `:72-82` 用 `bnn_fold_bn(1,0,20,1,0)` 算門檻（`:73`），確認 thr = 20（`:74`）；1000 個原型加 0~3 bit 雜訊的樣本都要分對。
6. `:84-92` 隨機權重 784×256，跑 1000 次取平均、5 輪取最快。

#### 要改的地方

| 行號 | 現在的值 | 意思 | 什麼情況要改、改成什麼 |
|---|---|---|---|
| `bnn_test.c:14`（TODO）、`:15-17` | `N_IN 40`、`N_HID 4`、`N_OUT 4` | 網路尺寸 | 改成題目的尺寸（例如 784、256、10） |
| `bnn_test.c:18-19` | `W1` 4 列 | 第一層權重 bits | 換成題目的權重（每列 `BNN_WORDS(N_IN)` 個 word，順序見 5.2.8） |
| `bnn_test.c:20` | `W2 = {1},{2},{4},{8}` | 輸出層權重 | 同上 |
| `bnn_test.c:73` | `bnn_fold_bn(1.0f, 0.0f, 20.0f, 1.0f, 0.0f, ...)` | 每個隱藏神經元的 BN 參數 | 換成題目的 gamma、beta、mean、`sqrtf(var+eps)`、bias（每個 j 不同）；若題目直接給整數門檻，跳過這行直接填 `thr1` |
| `bnn_test.c:75-81` | 原型加 0~3 bit 雜訊的自我測試（`:77` 選類別、`:78` 取原型、`:79` 加雜訊、`:80` 比對） | 範例網路專用的檢查 | 換成題目的測試資料與答案。**`:78` 的 `uint32_t x[2]` 是寫死 2 個 word**，改 `N_IN` 後要改成 `x[BNN_WORDS(N_IN)]` 並複製整列 |

#### 實際執行輸出
本次實測（host gcc 13.3、x86_64）：

```text
[① bnn_dot 與笨方法一致（含 n 不是 32 倍數的尾巴）]
  PASS  bnn_dot / bnn_pack 600 組
[① BN 折成整數門檻 == 浮點 BN 再取 sign（gamma 有正有負）]
  PASS  20000 組隨機 BN 參數
[② 範例 2 層網路：原型加 0~3 bit 雜訊，要分對]
  PASS  fold_bn(1,0,20,1,0) → thr=20
  PASS  1000 個加雜訊樣本全部分對
[③ Benchmark：784 輸入 x 256 神經元 dense，取 5 次最快]
  每層 12.09 us（16599 M 個 binary MAC / 秒）
結果：全部通過
```

`-DBNN_SWAR_POPCOUNT`：`每層 8.12 us（24721 M 個 binary MAC / 秒）`；`-march=native`（硬體 popcnt）：`每層 3.47 us（57871 M 個 binary MAC / 秒）`。三種都 `結果：全部通過`。

#### 常見錯誤

| 症狀 | 原因 | 修法 |
|---|---|---|
| 換權重後 `1000 個加雜訊樣本` FAIL | 這項只對範例網路成立 | 換成題目自己的測試資料 |

### 5.3.11 `checksum_misc.c`

#### 用途
簡單校驗碼合集，單一 `.c`、沒有 `.h`。要用就整段複製需要的函式（`checksum_misc.c:3`）。檔尾 `#ifdef TEST_MAIN` 內是測試。

#### 怎麼編譯 / 執行
```bash
gcc -O2 -Wall -Wextra -std=c11 -DTEST_MAIN checksum_misc.c -o $B/ck && $B/ck
```

#### 對外介面

| 名稱 | 參數 | 回傳 | 複雜度 / M33 stack | 注意 |
|---|---|---|---|---|
| `uint32_t adler32(uint32_t adler, const uint8_t *p, size_t n)` | 第一次傳 **1**，之後傳上次結果 | Adler-32 | O(n)；20 byte | 跟 Python `zlib.adler32(data)` 相同（本次 200 組一致） |
| `uint16_t fletcher16(const uint8_t *p, size_t n)` | 資料 | Fletcher-16 | O(n)；16 byte | 不能分段 |
| `uint8_t xor8(const uint8_t *p, size_t n)` | 資料 | 全部 XOR | O(n)；0 | NMEA 只算 `$` 和 `*` 之間 |
| `uint8_t sum8(const uint8_t *p, size_t n)` | 資料 | 加總低 8 位 | O(n)；0 | — |
| `uint8_t lrc8(const uint8_t *p, size_t n)` | 資料 | `0 - sum8` | O(n)；0 | — |
| `uint32_t sum32(const uint32_t *w, size_t nwords)` | `uint32_t` 陣列、**word 數** | 加總 mod 2^32 | O(n)；0 | 參數是 word 數不是 byte 數；跟 `pico/app_serial.c` 的 `CMD_SUM_U32` 同一種算法 |
| `uint16_t inet_csum(const uint8_t *p, size_t n)` | 資料（奇數長度補 0） | RFC 1071 checksum | O(n)；0 | 大端 16-bit；驗證時把 checksum 欄位一起算，結果應為 0 |

**Fletcher-32（檔案裡沒有，ch05 自寫，本次實測 PASS）**：

```c
/* Fletcher-32：16-bit 字（小端組字，奇數長度補 0），兩個累加器 mod 65535 */
uint32_t fletcher32(const uint8_t *p, size_t n) {
    uint32_t s1 = 0, s2 = 0;
    size_t words = (n + 1) / 2;
    while (words) {
        size_t k = words < 359 ? words : 359;     /* 359 個字內不會溢位 */
        words -= k;
        while (k--) {
            uint32_t w = p[0] | ((n > 1 ? (uint32_t)p[1] : 0u) << 8);
            s1 += w; s2 += s1;
            p += 2; n = n > 1 ? n - 2 : 0;
        }
        s1 %= 65535; s2 %= 65535;
    }
    return (s2 << 16) | s1;
}
```

本次：`"abcde"` → `0xF04FC729`、`"abcdef"` → `0x56502D2A`、`"abcdefgh"` → `0xEBE19591`，100,001 個 0xFF 和逐字取 mod 的笨方法一致（UBSan 下無錯誤）。題目若規定「大端組字」，把 `w` 那行改成 `((uint32_t)p[0] << 8) | (n > 1 ? p[1] : 0)`（⚠️ 這個變體本次沒有對照標準向量）。

#### 程式流程
1. `adler32`（`checksum_misc.c:21-30`）：拆出 a（低 16）、b（高 16）；每次最多處理 5552 byte（`ADLER_NMAX`）再取 mod。
2. `fletcher16`（`:32-41`）：每 5802 byte 取一次 mod 255。
3. `xor8`、`sum8`、`lrc8`、`sum32`（`:43-61`）：一行迴圈。
4. `inet_csum`（`:64-70`）：每 2 byte 大端相加（`:66`）；奇數長度最後一 byte 放高位（`:67`）；進位折回直到沒有進位（`:68`）；取反（`:69`）。
5. `main`（`:79-105`，`TEST_MAIN` 才編）：13 項測試。

#### 要改的地方
沒有 `TODO(改這裡)`。

#### 實際執行輸出
本次實測（host gcc 13.3）：

```text
  PASS  adler32("Wikipedia") = 0x11E60398
  PASS  adler32("") = 1
  PASS  adler32 10 萬個 0xFF == 笨方法
  PASS  adler32 增量（切兩段）
  PASS  fletcher16("abcde") = 0xC8F0
  PASS  fletcher16("abcdef") = 0x2057
  PASS  fletcher16("abcdefgh") = 0x0627
  PASS  fletcher16 10 萬個 0xFF == 笨方法
  PASS  xor8 (NMEA) = 0x28
  PASS  sum8("123456789") = 0xDD
  PASS  sum8 + lrc8 = 0
  PASS  sum32 溢位捨去
  PASS  inet_csum(RFC1071 範例) = 0x220D
結果：全部通過
```

#### 常見錯誤

| 症狀 | 原因 | 修法 |
|---|---|---|
| `adler32` 結果差很多 | 第一次傳 0 | 第一次傳 1 |
| NMEA 校驗不對 | 把 `$` 或 `*hh` 也算進去 | 只算兩者之間 |
| `inet_csum` 高低 byte 相反 | 放回封包時用了小端 | 高 byte 先寫 |
| 複製到 Pico 專案後 `multiple definition of 'main'` | 連 `TEST_MAIN` 那段也複製了 | 只複製需要的函式 |

### 5.3.12 `test_util.h`

#### 用途
只給 `*_test.c` 用的小工具。**必須是第一個 `#include`**，因為它要先定義 `_POSIX_C_SOURCE` 才能用 `clock_gettime`（`test_util.h:2`、`:6-8`）。

#### 怎麼編譯 / 執行
不單獨編譯，被 `*_test.c` include。

#### 對外介面

| 名稱 | 參數 | 效果 | 注意 |
|---|---|---|---|
| `CHECK(cond, msg)` | 條件、說明 | 印 `PASS`/`FAIL`，失敗時 `g_fail++` 並印檔名行號 | 不中斷 |
| `now_ns()` | — | `CLOCK_MONOTONIC` 奈秒 | POSIX；picolibc / pico-sdk 沒有 |
| `rnd32()` | — | xorshift32 亂數，種子固定 `2463534242`（`:28`） | 每次跑結果一樣，方便重現 |
| `to_hex(d, n, out)` | byte 陣列、長度、輸出字串（至少 2n+1） | 轉小寫 hex | — |
| `SINK(x)` | 值 | 加進 `volatile g_sink`，避免編譯器把要測速的程式優化掉 | — |
| `test_end()` | — | 印總結，回傳失敗數 | `main` 最後 `return test_end();` |
| `BENCH_MIN(best, reps, code)` | 輸出變數、次數、程式碼 | 跑 reps 次取最快的奈秒數 | `code` 裡有逗號時用 `{ }` 包起來（`sha_test.c:75` 的寫法） |

#### 程式流程
`test_util.h:15` 失敗計數 → `:18-19` `CHECK` → `:21-25` 計時 → `:28-32` 亂數 → `:35-37` hex → `:40-41` sink → `:44-47` 結束 → `:50-52` 測速巨集。

#### 要改的地方
無。

#### 實際執行輸出
不適用（所有 `*_test.c` 的輸出都用到它）。

#### 常見錯誤

| 症狀 | 原因 | 修法 |
|---|---|---|
| `implicit declaration of function 'clock_gettime'` | `test_util.h` 不是第一個 include | 放第一行 |
| 測出來 0 ns | 結果沒用到被優化掉 | 用 `SINK()` |

## 5.4 照題目改：食譜

### 5.4.1 題目給了一個不常見的 CRC 規格

**題目長這樣**：「封包最後 2 byte 是 CRC-16，多項式 0x1021，初值 0x1D0F，不反轉，無最後 XOR」或「CRC-32/AUTOSAR」或「CRC-7，多項式 x^7+x^3+1」。

**步驟**：
1. 把題目的描述翻成 7 個參數（5.2.3）。多項式寫成「反轉」形式（例如 `0xA001`、`0xEDB88320`）時，先換回一般寫法並設 refin=refout=1。
2. 查 5.2.4 表格有沒有同一列；有就整格複製。
3. **先驗證參數**：寫一個 3 行的測試，對 `"123456789"` 算，和題目給的範例（或表格 check 值）比對。
   ```c
   crc_param_t p = {16, 0x1021, 0x1D0F, 0, 0, 0x0000};      /* CRC-16/SPI-FUJITSU */
   printf("%04X\n", (unsigned)crc_generic(&p, (const uint8_t *)"123456789", 9));   /* 應為 E5CC */
   ```
4. 正確後再決定要不要換成快的版本：
   - 資料小（幾 KB）：直接用 `crc_generic`（28~31 MB/s，本次實測）。
   - refin=refout=1、init=xorout=`0xFFFFFFFF` 的 32-bit CRC：改 `crc32.c:10` 的 `POLY32R` 成反轉多項式，直接用 `crc32_update`。
   - 其他（不反轉、init 不是全 1、width 8..32 任意）：用下面的 `crcf`（ch05 自寫查表版，可分段）。
   - width < 8：用下面的 `crc_bits`。

**`crcf`：任意 refin==refout 規格的查表版（ch05 自寫；本次對 12 種規格 × 100 組隨機長度、切兩段算，和 `crc_generic` 全一致；CRC-32/AUTOSAR 470.0 MB/s，`crc_generic` 28.3 MB/s，快 16.6 倍）**：

```c
#include <stdint.h>
#include <stddef.h>
typedef struct { uint8_t width, ref; uint32_t poly, init, xorout; uint32_t T[256]; } crcf_t;
static uint32_t refl(uint32_t v, int bits) { uint32_t r = 0; for (int i = 0; i < bits; i++) { r = (r << 1) | (v & 1u); v >>= 1; } return r; }
void crcf_init(crcf_t *c, int width, uint32_t poly, uint32_t init, int ref, uint32_t xorout) {
    uint32_t mask = (width == 32) ? 0xFFFFFFFFu : ((1u << width) - 1u);
    c->width = (uint8_t)width; c->ref = (uint8_t)ref; c->poly = poly; c->init = init; c->xorout = xorout;
    for (uint32_t i = 0; i < 256; i++) {
        uint32_t r;
        if (ref) { uint32_t pr = refl(poly, width); r = i;
                   for (int k = 0; k < 8; k++) r = (r >> 1) ^ (pr & (0u - (r & 1u))); }
        else     { uint32_t top = 1u << (width - 1); r = i << (width - 8);
                   for (int k = 0; k < 8; k++) r = (r & top) ? (r << 1) ^ poly : (r << 1);
                   r &= mask; }
        c->T[i] = r;
    }
}
/* 「原始暫存器」版：可以分段。開始 reg = crcf_start(c)，最後 crcf_finish(c, reg) */
uint32_t crcf_start(const crcf_t *c) { return c->ref ? refl(c->init, c->width) : c->init; }
uint32_t crcf_feed(const crcf_t *c, uint32_t reg, const uint8_t *p, size_t n) {
    uint32_t mask = (c->width == 32) ? 0xFFFFFFFFu : ((1u << c->width) - 1u);
    if (c->ref) while (n--) reg = (reg >> 8) ^ c->T[(reg ^ *p++) & 0xFF];
    else        while (n--) reg = ((reg << 8) ^ c->T[((reg >> (c->width - 8)) ^ *p++) & 0xFF]) & mask;
    return reg;
}
uint32_t crcf_finish(const crcf_t *c, uint32_t reg) {
    uint32_t mask = (c->width == 32) ? 0xFFFFFFFFu : ((1u << c->width) - 1u);
    return (reg ^ c->xorout) & mask;
}
```

用法：`static crcf_t c; crcf_init(&c, 16, 0x1021, 0x1D0F, 0, 0); uint32_t r = crcf_start(&c); r = crcf_feed(&c, r, buf1, n1); r = crcf_feed(&c, r, buf2, n2); uint16_t crc = crcf_finish(&c, r);`。`crcf_t` 有 1 KB 的表，在 MCU 上放 `static`。refin ≠ refout 的規格（例如 CRC-12/UMTS）不支援，用 `crc_generic`。

**`crc_bits`：width 1..32 都可用的逐位元版（ch05 自寫；本次 CRC-7/MMC、CRC-5/USB、CRC-4/G-704、CRC-3/GSM、CRC-32、CRC-16/CCITT-FALSE 共 6 個 check 值 PASS，UBSan 無錯誤）**：

```c
uint32_t crc_bits(int width, uint32_t poly, uint32_t init, int refin, int refout, uint32_t xorout,
                  const uint8_t *p, size_t n) {
    uint32_t mask = (width == 32) ? 0xFFFFFFFFu : ((1u << width) - 1u), crc = init & mask;
    while (n--) {
        uint8_t b = *p++;
        for (int k = 0; k < 8; k++) {
            int in = refin ? (b >> k) & 1 : (b >> (7 - k)) & 1;      /* refin：LSB 先 */
            int fb = (int)((crc >> (width - 1)) & 1u) ^ in;
            crc = (crc << 1) & mask;
            if (fb) crc ^= poly;
        }
    }
    if (refout) { uint32_t r = 0; for (int i = 0; i < width; i++) { r = (r << 1) | (crc & 1u); crc >>= 1; } crc = r; }
    return (crc ^ xorout) & mask;
}
```

**怎麼驗證**：電腦端用 Python 版 `crc_generic`（食譜 5.4.7）對同一份資料算，跟板子回傳值比。**成功的樣子**：`"123456789"` 的結果等於表格 check 值，且隨機資料 C 與 Python 一致。

### 5.4.2 軟體 CRC 換成 DMA sniffer（硬體 CRC）

**題目長這樣**：「CRC 計算太慢，請用硬體加速」「用 DMA 的校驗功能」（`預測考題.md` 2-3-D）。

**先知道**：RP2350 的 DMA sniffer 只會 4 種 CRC 計算（`regs/dma.h` 的 `SNIFF_CTRL_CALC`，pico-sdk 2.2.0）：`0x0` CRC-32（IEEE 多項式，資料 MSB 先）、`0x1` CRC-32 資料位元反轉、`0x2` CRC-16-CCITT、`0x3` CRC-16-CCITT 資料位元反轉，另有 `0xe` 全部 XOR 的奇偶、`0xf` 32-bit 加總。暫存器說明寫明 `OUT_REV`、`OUT_INV` 只改「讀出來的值」，不影響計算。**整顆晶片只有一個 sniffer**（第 3 章 `app_dma.c` 一節）。

**步驟（zlib CRC-32，最常見）**：
1. 從 `pico/app_dma.c:65-87` 把 `dma_crc32()` 整個函式複製到你的程式（設定：8-bit 傳輸、初值 `0xFFFFFFFF`、`OUT_REV`、`CALC_VALUE_CRC32R`、讀出後軟體 `^ 0xFFFFFFFF`）。
2. CMake：`target_link_libraries(你的app ... hardware_dma)`，程式 `#include "hardware/dma.h"`。
3. 把原本的軟體呼叫換掉。以 `pico/app_serial.c:44-49` 的 `CMD_CRC32` 為例：
   - 改前（`app_serial.c:45`）：`uint32_t c = crc32_update(0, f->payload, f->len);`
   - 改後：`uint32_t c = dma_crc32(f->payload, f->len);`
4. **開機自我測試**：先跑第 3 章的 `app_dma`，看 `crc32("123456789") ... PASS`。或在你的程式開頭比 `dma_crc32("123456789", 9) == 0xCBF43926`，並和軟體 `crc32_update` 對一份隨機資料比。FAIL 時看 `app_dma.c:63-64` 的提示：值是 `0x649C2FD3` → 把 `output_reverse` 改 false；值是 `0x340BC6D9` → 最後的 XOR 多做了。
5. 一次 DMA 算完整段資料，不要分段續算（`app_dma.c:82-83` 註解：寫回初值時是否受 OUT_REV 影響文件沒寫）。

本次把上面這個改法（加上排序、串流 SHA-0 兩個新指令，見 5.4.3、5.4.4）放進 `app_serial.c` 的複本 `app_serial_ch05.c`，用 pico-sdk 2.2.0（pico2、ARM）**編譯連結通過、0 警告**（`text 28816 / bss 38240`）。⚠️ **沒有上板**；sniffer 結果和 zlib 相同這件事目前只由暫存器文件推導（已知問題 9），一定要看自我測試。

**其他 CRC 規格**：
- CRC-32/MPEG-2（`{32, 0x04C11DB7, 0xFFFFFFFF, 0, 0, 0}`）：推導上是 `CALC_VALUE_CRC32`、不設 `OUT_REV`、不做最後 XOR；BZIP2 再加 `^0xFFFFFFFF`。⚠️未驗證。
- CRC-16（CCITT 多項式 `0x1021` 系列：XMODEM、CCITT-FALSE、KERMIT…）：用 `CALC_VALUE_CRC16` / `CRC16R`。16-bit 結果落在 32-bit 累加器的哪一半、`OUT_REV` 會不會把它反轉到高 16 位，文件沒寫清楚 → ⚠️未驗證。上板時把 `r`、`r & 0xFFFF`、`r >> 16` 都印出來，和 `crc_generic` 的答案比。
- 其他多項式（`0x8005` 的 MODBUS、CRC-32C…）：sniffer 不支援，只能軟體算。

**成功的樣子**：自我測試 PASS，且同一份資料 DMA 與軟體結果相同。速度數字見第 3 章（`app_dma` 會印 `cpu=…us dma=…us`）。

### 5.4.3 大陣列分給多塊板子排序，再 k-way merge

**題目長這樣**：「把 N 個整數排序，可以用多塊板子」（`預測考題.md` 1-B，去年 ③）。

**板子端**（每塊收一段、排好、回傳）：在 `app_serial.c` 的 `handle()` 加一個指令（第 2 章 2.4.6 有電腦端加指令的步驟）。本次編譯通過的寫法：

```c
#include "sort.h"
#define CMD_SORT_U32 0x04     // payload = u32 陣列 → 回排序好的 u32 陣列
static uint32_t sort_buf[FRAME_MAX_PAYLOAD / 4], sort_tmp[FRAME_MAX_PAYLOAD / 4];
...
    case CMD_SORT_U32: {
        uint32_t n = f->len / 4;
        memcpy(sort_buf, f->payload, n * 4);
        radix_sort_u32(sort_buf, n, sort_tmp);
        proto_send(f->cmd, f->seq, (const uint8_t *)sort_buf, (uint16_t)(n * 4));
        break;
    }
```

CMake 加 `algo/sort.c` 和 include 路徑（食譜 5.4.6）。有號數就在 `radix_sort_u32` 前後各做一次 `^= 0x80000000u`。

**電腦端**（切塊 → 平行送 → 合併），沿用 `ros2/multi_device.py` 的 `split`、`run_parallel`（第 2 章 2.3.5），合併換成 `heapq.merge`：

```python
import heapq
from frame import pack_u32, unpack_u32
from multi_device import split, run_parallel
CMD_SORT_U32 = 0x04
chunks = split(pack_u32(values))                 # 每塊 <= CHUNK_BYTES（4096 B = 1024 個 u32）
replies = run_parallel(ports, chunks, CMD_SORT_U32)
out = list(heapq.merge(*[unpack_u32(r) for r in replies]))
assert out == sorted(values)
```

本次用假的序列埠（`transact` 換成「Python 排好回傳」）跑這段：100,000 個隨機 `uint32`、98 塊、2 個 port，`合併正確 True`。真的板子沒有實測。有號數：`pack_u32` 會把負數轉成二補數（`frame.py:28-30`），收回來要轉回有號再比：`[x - (1 << 32) if x >> 31 else x for x in ...]`。

**合併在板子上做時**（例如 core0、core1 各排一半，或一塊板子收回兩塊的結果）：
- 2 段：`merge_two_sorted(a, na, b, nb, out)`。
- 3~4 段：`kway_merge(lists, lens, k, out)`。
- 8 段以上：兩兩合併比 `kway_merge` 快（本次 n = 2^20、k = 16：15.93 ms vs 62.32 ms），但需要一個 n 大小的暫存區。ch05 自寫版（k 段等長、連續放在 `src`，k 是 2 的冪；本次 k = 2、4、8、16 都排序正確）：

```c
static uint32_t *tree_merge(uint32_t *src, uint32_t *dst, size_t n, int k) {
    size_t len = n / k;
    while (len < n) {
        for (size_t lo = 0; lo < n; lo += 2 * len) {
            size_t m = lo + len < n ? len : n - lo, r = lo + 2 * len <= n ? len : (lo + len < n ? n - lo - len : 0);
            merge_two_sorted(src + lo, m, src + lo + m, r, dst + lo);
        }
        uint32_t *t = src; src = dst; dst = t; len *= 2;
    }
    return src;                     /* 結果在 src 或 dst 其中一個，用回傳值 */
}
```

**注意**：`seq` 只有 8 bit（`multi_device.py` 用 chunk 編號的低 8 位），塊數超過 256 時 seq 會重複；`run_parallel` 依索引存結果所以順序仍正確，但重送時可能收到舊回覆（見第 2 章 2.6）。

**成功的樣子**：電腦端 `out == sorted(values)` 為 True；兩塊板子時間接近單塊的一半加上合併時間（本次單核模擬：兩半各 radix + merge 11.01 ms，單次 radix 6.88 ms）。

### 5.4.4 資料分好幾包收到：串流算 SHA-0

**題目長這樣**：「Host 會分多個封包送出一份資料，請回傳整份資料的 SHA-0」。

**步驟**：
1. 用一個全域的 `sha1_ctx`（不要放 stack，也不要每包重開）。
2. 收到第一包前 `sha1_init(&ctx, 1)`（**1 = SHA-0**）。
3. 每包 `sha1_update(&ctx, payload, len)`，長度任意、不用湊 64。
4. 收到「結束」的訊號（題目會定義：最後一包的旗標、另一個指令、或總長度到了）才 `sha1_final(&ctx, out)`，回傳 20 byte。
5. 下一份資料重新 `init`。

本次放進 `app_serial_ch05.c` 編譯通過的寫法（兩個新指令：`0x05` 餵資料、`0x06` 結束）：

```c
#include "sha1_sha0.h"
#define CMD_SHA0_UPDATE 0x05     // payload = 下一段資料 → 回空封包（ack）
#define CMD_SHA0_FINAL  0x06     // 回 20 byte SHA-0，並重新開始
static sha1_ctx sha_ctx;
static int sha_started = 0;
...
    case CMD_SHA0_UPDATE:
        if (!sha_started) { sha1_init(&sha_ctx, 1); sha_started = 1; }   // 1 = SHA-0
        sha1_update(&sha_ctx, f->payload, f->len);
        proto_send(f->cmd, f->seq, NULL, 0);
        break;
    case CMD_SHA0_FINAL:
        if (!sha_started) sha1_init(&sha_ctx, 1);      // 沒資料 = SHA-0("")
        sha1_final(&sha_ctx, reply);
        sha_started = 0;                               // 下一次 UPDATE 重新開始
        proto_send(f->cmd, f->seq, reply, 20);
        break;
```

**順序很重要**：SHA 對資料順序敏感，封包必須照順序餵。用 `multi_device.py` 那種「多執行緒搶工作」的方式送會亂序，**這題只能用一個 port、依序送**。若電腦端會重送（`frame.transact` 逾時重試），板子要用 `seq` 判斷是不是重複的包，否則同一段會被餵兩次（⚠️ 上面的範例沒有處理重送）。

**怎麼驗證**：電腦端用 Python 版 `sha0`（食譜 5.4.7）算整份資料，和板子回的 20 byte 比。在電腦上先用 `sha_test.c` 的「隨機切段」那段邏輯（`sha_test.c:51-71`）確認你的切法不影響結果。

**加速**：一核收封包、一核算 SHA（第 3 章 `app_multicore.c` 一節）；注意 `rx` 只有一份，要多個 buffer 輪流（`app_serial.c:85-86` 註解）。

**成功的樣子**：板子回的 hex 等於 Python `sha0(data).hex()`；`"abc"` 分成 `"a"`、`"bc"` 兩包送，結果是 `0164b8a914cd2a5e74c4f7ff082c4d97f1edf880`。

### 5.4.5 BNN 用 popcount 加速（含權重格式轉換）

**題目長這樣**：「eBNN 推論太慢」「請優化推論速度」。

**步驟**：
1. **選對 popcount**（最重要，零成本）：
   - Pico 2 用 RISC-V（Hazard3）編：pico-sdk 預設 `-march=rv32imac_zicsr_zifencei_zba_zbb_zbs_zbkb`（`pico-sdk/cmake/preload/toolchains/pico_riscv_gcc.cmake:5`），已含 Zbb，`__builtin_popcount` 會變成 1 條 `cpop`，`bnn_dot` 內迴圈只有 8 條指令（本次 objdump：`lw lw addi addi xnor cpop add bne`）。什麼都不用改。
   - Pico 2 用 ARM（Cortex-M33）編：M33 沒有 popcount 指令，預設會呼叫 libgcc 的 `__popcountsi2`（本次 objdump 確認 `bnn.o` 有 2 個呼叫）。加 `target_compile_definitions(你的app PRIVATE BNN_SWAR_POPCOUNT)` 改用 SWAR，內迴圈 18 條指令、沒有函式呼叫（本次 objdump）。
   - 板子上兩者的實際速度**沒有實測**；host 上 SWAR 比 `__builtin_popcount`（無硬體指令）快 1.49 倍（12.09 → 8.12 µs），硬體 popcnt 快 3.48 倍（3.47 µs）。
2. **改成數「不同」**：`dot = n - 2 * popcount(a ^ w)`，省掉 NOT。本次在 M33 上內迴圈從 18 條變 17 條（幾乎沒差）；host 上因為編譯器自動向量化差很多（SWAR 6.82 → 2.61 µs），**這個差距不代表 Pico**。不急的話不用改。
3. **用雙核心或多板分神經元 / 分樣本**（5.2.8 的去年考題對照）。
4. **少搬資料**：權重放 `static const`（在 flash，透過 XIP cache 讀）或複製到 RAM 再算。哪個快在 Pico 上**沒有實測**（⚠️未驗證）。
5. **傳輸**：輸入用 bits 傳（784 bit = 100 byte），回傳只回類別編號（1 byte）。

**權重格式轉換**：題目的權重若是 numpy `packbits`（預設 `bitorder='big'`：第 i 個元素在 byte `i/8` 的 bit `7 - i%8`，MSB 先），要轉成 `bnn.h` 的排列。ch05 自寫（本次 100 個元素與 `bnn_pack` 結果相同）：

```c
/* numpy.packbits（bitorder='big'）的位元組 → bnn.h 的排列（第 i 個 → word i/32 的 bit i%32） */
static void bnn_from_packbits(const uint8_t *pb, int n, uint32_t *out) {
    for (int k = 0; k < BNN_WORDS(n); k++) out[k] = 0;
    for (int i = 0; i < n; i++)
        if ((pb[i >> 3] >> (7 - (i & 7))) & 1) out[i >> 5] |= 1u << (i & 31);
}
```

開機時轉一次存進 RAM 陣列，推論時不要每次轉。若題目給的是 `bitorder='little'` 的 bytes，那就是 `bnn.h` 的排列（小端 CPU 上 4 byte 直接當一個 word），可以直接 `memcpy`。

**怎麼驗證**：用 Python 版 `bnn_dense_sign` / `bnn_dense_score`（食譜 5.4.7）算同一組輸入，比對分數。**成功的樣子**：分數陣列逐項相同，argmax 相同；改了 popcount 之後 `bnn_test` 仍 `結果：全部通過`。

### 5.4.6 把 algo 的檔案放進 Pico 專案

**要複製哪些檔**：只複製核心檔，**不要**複製 `*_test.c`、`test_util.h`。

| 要用 | 複製 |
|---|---|
| CRC | `crc32.c`、`crc32.h` |
| SHA-0 / SHA-1 | `sha1_sha0.c`、`sha1_sha0.h` |
| SHA-256 | `sha256.c`、`sha256.h` |
| 排序 | `sort.c`、`sort.h` |
| BNN | `bnn.c`、`bnn.h` |
| Adler / Fletcher / XOR / IP | 把需要的函式從 `checksum_misc.c` 貼到你的 `.c`（不要貼 `#ifdef TEST_MAIN` 那段） |

**CMake**（本次在 pico-sdk 2.2.0、`PICO_BOARD=pico2`、ARM 編譯連結通過，0 警告）。假設檔案放在專案的 `algo/` 子資料夾：

```cmake
add_executable(app_algo
    app_algo.c
    algo/crc32.c algo/sha1_sha0.c algo/sha256.c algo/sort.c algo/bnn.c)   # 只放核心檔，不要放 *_test.c
target_include_directories(app_algo PRIVATE ${CMAKE_CURRENT_LIST_DIR}/algo)
target_compile_options(app_algo PRIVATE -O2 -Wall -Wextra)
if (PICO_PLATFORM STREQUAL "rp2350-arm-s")
    target_compile_definitions(app_algo PRIVATE BNN_SWAR_POPCOUNT)       # M33 沒有 popcount 指令
endif()
target_link_libraries(app_algo pico_stdlib)
pico_enable_stdio_usb(app_algo 1)
pico_enable_stdio_uart(app_algo 0)
pico_add_extra_outputs(app_algo)
```

（`PICO_PLATFORM` 在 `-DPICO_BOARD=pico2` 時是 `rp2350-arm-s`，本次 `CMakeCache.txt` 確認；加 `-DPICO_PLATFORM=rp2350-riscv` 時條件不成立，就用 `cpop`。）要加到既有的 `pico/CMakeLists.txt`：在對應的 `add_app(...)` 後面補 `target_sources(app_xxx PRIVATE algo/sort.c ...)` 和上面的 `target_include_directories`。

本次的測試程式 `app_algo.c`（ch05 自寫，開機印 CRC、SHA-0 自我測試與 CRC/SHA/radix/BNN 的時間）連結結果：`text 34588 / bss 232792`（bss 大是因為測試用了 64 KB 資料 + 128 KB 排序陣列 + 25 KB 權重）。⚠️ 沒有上板，沒有板上速度數字。

**和 `pico/serial_proto.c` 同時用的衝突**：`serial_proto.c:25` 和 `crc32.c:77` 都定義了 `crc32_update`（同樣是 zlib CRC-32），放進同一個執行檔會出錯。本次實測：

```text
crc32.c:78: multiple definition of `crc32_update'; CMakeFiles/app_conflict.dir/serial_proto.c.o:serial_proto.c:25: first defined here
collect2: error: ld returned 1 exit status
```

（報錯行號 78 是函式本體那行。）修法擇一：
- 只需要 zlib CRC-32 → 不要加 `crc32.c`，直接用 `serial_proto.c` 的 `crc32_update`（同樣結果）。
- 還需要 `crc32c_update`、`crc_generic` 等 → 對 `crc32.c` 改名：`set_source_files_properties(algo/crc32.c PROPERTIES COMPILE_DEFINITIONS "crc32_update=algo_crc32_update")`。本次這樣改後 `app_serial` + `crc32.c` 連結通過；注意這個屬性對所有用到 `algo/crc32.c` 的 target 都生效，別的 target 若呼叫 `crc32_update` 會找不到，改呼叫 `crc32_slice4`。

**MCU 上的記憶體注意**：
- 大陣列一律 `static`（Pico 主 stack 只有 `PICO_STACK_SIZE` = 0x800 = 2 KB 的保留空間，pico-sdk `rp2350/pico_platform/include/pico/platform.h:45`）。
- `radix_sort_u32` 本身用 1064 byte stack、`sha256` 壓縮用 336 byte（5.5.6），在 core1（預設 2 KB）上用時要留意。
- 有用雙核心：開機先呼叫一次 `crc32_init()` 再 `multicore_launch_core1`（避免兩核同時第一次建表）。

**RISC-V 版**：本次在這個容器用 `-DPICO_PLATFORM=rp2350-riscv -DPICO_GCC_TRIPLE=riscv64-unknown-elf` 可以 configure，但連結 SDK 的 boot stage2 時失敗（`cannot read spec file 'nosys.specs'`：容器的 RISC-V 工具鏈只有 picolibc、沒有 newlib）。這是容器限制，不是 algo 的問題；6 個核心檔用 SDK 同樣的 `-march` 單獨編譯 0 警告（5.5.4）。考場 Docker 的工具鏈⚠️未驗證。

### 5.4.7 在電腦上用 Python 對答案（`algo_ref.py`）

**題目長這樣**：板子回了一個 CRC / SHA-0 / 分數，你要知道對不對。電腦端 Python 有 `zlib.crc32`、`zlib.adler32`、`hashlib.sha1`、`hashlib.sha256`、`binascii.crc_hqx`（= CRC-16/XMODEM），**沒有** SHA-0、任意參數 CRC、Fletcher、BNN。下面這個檔補齊（ch05 自寫，純標準函式庫）。

本次驗證：`python3 -I algo_ref.py` 自我測試通過；C 程式讀 stdin 印出 9 種結果，對 200 組隨機資料（0~299 byte）和 Python 比對 **0 組不一致**（`sha0`、`sha1`、`sha256`、`crc32`、CRC-32C、`adler32`、`fletcher16`、`inet_csum`、CRC-16/MODBUS）；隨機 2 層 BNN（100→40→10，含 gamma 正負）的隱藏 bits、10 個分數、argmax 和 C 完全相同。速度（本次）：100 KB 的 `sha0` 66.9 ms、`crc_generic` 122.1 ms（`zlib.crc32` 0.052 ms）→ 幾 MB 以內的資料夠用。

```python
"""algo_ref.py — 電腦端對答案用（純 Python，只用標準函式庫）。對應 algo/ 的 C 函式。"""
import struct, zlib, hashlib

def reflect(v, bits):
    r = 0
    for _ in range(bits):
        r = (r << 1) | (v & 1); v >>= 1
    return r

def crc_generic(data, width, poly, init, refin, refout, xorout):
    """= algo/crc32.c crc_generic（width 8..32）"""
    top, mask = 1 << (width - 1), (1 << width) - 1
    crc = init & mask
    for b in data:
        if refin: b = reflect(b, 8)
        crc ^= b << (width - 8)
        for _ in range(8):
            crc = ((crc << 1) ^ poly) if crc & top else (crc << 1)
        crc &= mask
    if refout: crc = reflect(crc, width)
    return (crc ^ xorout) & mask

def _sha1_core(data, is_sha0):
    h = [0x67452301, 0xEFCDAB89, 0x98BADCFE, 0x10325476, 0xC3D2E1F0]
    rotl = lambda x, n: ((x << n) | (x >> (32 - n))) & 0xFFFFFFFF
    msg = data + b'\x80' + b'\x00' * ((55 - len(data)) % 64) + struct.pack('>Q', len(data) * 8)
    for off in range(0, len(msg), 64):
        w = list(struct.unpack('>16I', msg[off:off + 64]))
        for t in range(16, 80):
            x = w[t-3] ^ w[t-8] ^ w[t-14] ^ w[t-16]
            w.append(x if is_sha0 else rotl(x, 1))       # 唯一差別
        a, b, c, d, e = h
        for t in range(80):
            if t < 20:   f, k = (b & c) | (~b & d), 0x5A827999
            elif t < 40: f, k = b ^ c ^ d, 0x6ED9EBA1
            elif t < 60: f, k = (b & c) | (b & d) | (c & d), 0x8F1BBCDC
            else:        f, k = b ^ c ^ d, 0xCA62C1D6
            a, b, c, d, e = (rotl(a, 5) + f + e + k + w[t]) & 0xFFFFFFFF, a, rotl(b, 30), c, d
        h = [(x + y) & 0xFFFFFFFF for x, y in zip(h, (a, b, c, d, e))]
    return struct.pack('>5I', *h)

def sha0(data): return _sha1_core(data, True)
def sha1(data): return _sha1_core(data, False)        # 可用 hashlib.sha1 對照

def fletcher16(data):
    s1 = s2 = 0
    for b in data:
        s1 = (s1 + b) % 255; s2 = (s2 + s1) % 255
    return (s2 << 8) | s1

def inet_csum(data):
    if len(data) % 2: data += b'\x00'
    s = sum(struct.unpack('>%dH' % (len(data) // 2), data))
    while s >> 16: s = (s & 0xFFFF) + (s >> 16)
    return ~s & 0xFFFF

def bnn_pack(v):                      # list of ±1 → list of uint32（第 i 個 → word i//32 的 bit i%32）
    out = [0] * ((len(v) + 31) // 32)
    for i, x in enumerate(v):
        if x > 0: out[i >> 5] |= 1 << (i & 31)
    return out

def bnn_dot(a_bits, w_bits, n):       # = bnn.c bnn_dot
    match = 0
    for i in range(n):
        match += ((a_bits[i >> 5] >> (i & 31)) & 1) == ((w_bits[i >> 5] >> (i & 31)) & 1)
    return 2 * match - n

def bnn_fold_bn(gamma, beta, mean, std, bias):   # = bnn.c bnn_fold_bn → (thr, flip)
    import math
    if gamma == 0: return (-(2**30) if beta >= 0 else 2**30 - 1, 0)   # = INT32_MIN/2、INT32_MAX/2
    t = mean - bias - beta * std / gamma
    return (math.ceil(t), 0) if gamma > 0 else (math.ceil(-t), 1)

def bnn_dense_sign(x_bits, n_in, W_rows, thr, flip=None):  # W_rows[j] = 第 j 個神經元的 bits（list of uint32）
    out = [0] * ((len(W_rows) + 31) // 32)
    for j, w in enumerate(W_rows):
        d = bnn_dot(x_bits, w, n_in)
        if flip and flip[j]: d = -d
        if d >= thr[j]: out[j >> 5] |= 1 << (j & 31)
    return out

def bnn_dense_score(x_bits, n_in, W_rows, bias=None):
    return [bnn_dot(x_bits, w, n_in) + (bias[j] if bias else 0) for j, w in enumerate(W_rows)]

if __name__ == '__main__':
    s = b'123456789'
    assert crc_generic(s, 32, 0x04C11DB7, 0xFFFFFFFF, 1, 1, 0xFFFFFFFF) == zlib.crc32(s) == 0xCBF43926
    assert crc_generic(s, 16, 0x8005, 0xFFFF, 1, 1, 0) == 0x4B37
    assert sha0(b'abc').hex() == '0164b8a914cd2a5e74c4f7ff082c4d97f1edf880'
    assert sha1(b'abc') == hashlib.sha1(b'abc').digest()
    assert zlib.adler32(b'Wikipedia') == 0x11E60398
    assert fletcher16(b'abcde') == 0xC8F0
    assert inet_csum(bytes([0, 1, 0xf2, 3, 0xf4, 0xf5, 0xf6, 0xf7])) == 0x220D
    assert bnn_dot(bnn_pack([1, -1, 1]), bnn_pack([1, 1, 1]), 3) == 1
    print('algo_ref 自我測試：全部通過')
```

**用法**：存成 `algo_ref.py`（放在 repo 外，或放在你自己的工作資料夾），`python3 algo_ref.py` 看到 `algo_ref 自我測試：全部通過`。在其他程式 `import algo_ref as R` 後：`R.sha0(data).hex()`、`R.crc_generic(data, 16, 0x1021, 0x1D0F, 0, 0, 0)`。排序用 Python 內建 `sorted()`，k-way merge 用 `heapq.merge`。

**注意**：`bnn_fold_bn` 在 Python 用 double、C 用 float，`t` 剛好落在整數邊界附近時 `ceil` 可能差 1（⚠️ 本次隨機測試沒遇到，但沒排除）。題目若有給整數門檻，兩邊都直接用那個門檻。

### 5.4.8 CRC-32 的資料被拆給多塊板子：在電腦端合併

**題目長這樣**：「資料很大，分給兩塊板子各算一半的 CRC-32，最後要整份的 CRC-32」。`ros2/multi_device.py` 的 `merge_sum` 註解寫「CRC32 不能直接相加」——確實不能相加，但可以用下面的公式合併。

CRC 是「仿射」函數（線性 + 常數），所以只要知道 A 的 CRC、B 的 CRC、B 的長度，就能算 A+B 的 CRC（ch05 自寫；本次 500 組隨機兩段、1 組 5 段，和 `zlib.crc32(a + b)` 全部一致）：

```python
import zlib
def crc32_combine(crc_a, crc_b, len_b):
    """crc32(A+B)，只知道 crc32(A)、crc32(B)、len(B)。花 O(len_b) 時間（電腦端夠快）。"""
    z = bytes(len_b)
    return zlib.crc32(z, crc_a) ^ crc_b ^ zlib.crc32(z)
```

多段依序合併：`c = crcs[0]; for i in range(1, k): c = crc32_combine(c, crcs[i], lens[i])`。

**成功的樣子**：合併結果等於 `zlib.crc32(整份資料)`。（SHA 不能這樣拆，見 5.2.6。）

## 5.5 效能：量測方法與實測數字

### 5.5.1 量測方法

- 測速都用 `test_util.h` 的 `BENCH_MIN(ns, reps, code)`：同一段程式跑 `reps` 次（CRC/SHA/BNN 5 次、排序 3 次）取最快那次，`CLOCK_MONOTONIC` 計時；結果寫進 `volatile` 的 `SINK` 避免被優化掉。
- 速度欄位 `MB/s` = byte 數 ÷ 微秒（10^6 byte/s）；4 MB = 4,194,304 byte。
- 排序的時間**都含一次 `memcpy` 還原資料**（n = 2^20 時 memcpy 本身 0.28 ms）。
- 本次 host：x86_64 Intel Xeon @ 2.30GHz、4 核、gcc 13.3.0、`-O2`。qemu-riscv32 的時間**不代表真實硬體**，只列出來證明程式在 rv32 上跑得完。
- Pico 2 上的速度**全部沒有實測**（沒有板子）。要量就用 `pico/timing.h`（第 3 章）或 5.4.6 的 `app_algo.c` 那種 `time_us_64()` 前後相減。

### 5.5.2 CRC 與 SHA（host，4 MB）

| 函式 | 時間 | 速度 | 相對 `crc32_bitwise` |
|---|---|---|---|
| `crc32_bitwise` | 36.47 ms | 115.0 MB/s | 1x |
| `crc32_table` | 8.65 ms | 484.8 MB/s | 4.2x |
| `crc32_slice4`（= `crc32_update`） | 2.90 ms | 1445.4 MB/s | 12.6x |
| `crc32c_update` | 8.58 ms | 488.6 MB/s | 4.3x |
| `crc16_ccitt_false` | 11.85 ms | 353.9 MB/s | 3.1x |
| `crc_generic`（CRC-32/AUTOSAR，ch05 自寫測速） | 148.03 ms | 28.3 MB/s | 0.25x |
| `crc_generic`（CRC-16/SPI-FUJITSU） | 135.18 ms | 31.0 MB/s | 0.27x |
| `crcf` 查表（CRC-32/AUTOSAR，食譜 5.4.1） | 8.92 ms | 470.0 MB/s | 4.1x |
| `crcf` 查表（CRC-16/SPI-FUJITSU，不反轉） | 11.63 ms | 360.6 MB/s | 3.1x |
| `sha1` | 9.91 ms | 423.1 MB/s | — |
| `sha0` | 10.09 ms | 415.8 MB/s | — |
| `sha256` | 34.20 ms | 122.6 MB/s | — |

### 5.5.3 排序與合併（host）

各種 n（ch05 自寫 `sortb.c`，單次排序的微秒數，含 memcpy，取最快）：

| n | insertion | merge | radix | qsort | radix 對 qsort |
|---|---|---|---|---|---|
| 16 | 0.04 | 0.05 | 0.40 | 0.17 | 0.4x（較慢） |
| 32 | 0.16 | 0.16 | 0.49 | 0.37 | 0.8x |
| 64 | 0.72 | 0.43 | 0.69 | 0.82 | 1.2x |
| 256 | 6.96 | 2.02 | 1.44 | 4.19 | 2.9x |
| 1000 | 78.48 | 10.14 | 4.54 | 32.68 | 7.2x |
| 10000 | 6691.55 | 420.43 | 47.41 | 645.84 | 13.6x |
| 100000 | — | 5634.73 | 499.44 | 8312.02 | 16.6x |
| 1048576 | — | 77191.39 | 6856.08 | 109096.96 | 15.9x |

結論：n ≤ 32 用 insertion（radix 有固定 4×256 的計數成本）；n ≥ 256 用 radix；要穩定又不是整數鍵用 merge。`sort_test` 本身（n = 2^20）：qsort 106.25 ms、merge 77.68 ms、radix 6.88 ms（15.4 倍）、兩半 radix + merge 11.01 ms。

合併（n = 2^20 切 k 段等長，各段先 radix 排好，只量合併）：

| k | `kway_merge` | 兩兩合併（食譜 5.4.3 `tree_merge`） | `merge_two_sorted` |
|---|---|---|---|
| 2 | 6.39 ms | 3.97 ms | 3.93 ms |
| 4 | 12.52 ms | 7.94 ms | — |
| 8 | 29.05 ms | 12.19 ms | — |
| 16 | 62.32 ms | 15.93 ms | — |

### 5.5.4 BNN（host，784 輸入 × 256 神經元一層）

| 編譯方式 | `bnn_test`（`bnn_dense_sign`） | 直接呼叫 `bnn_dot` 256 次 | 改數「不同」（食譜 5.4.5 第 2 步） |
|---|---|---|---|
| `-O2`（`__builtin_popcount` 沒有硬體指令） | 12.09 µs | 10.99 µs | 11.60 µs |
| `-O2 -DBNN_SWAR_POPCOUNT` | 8.12 µs | 6.82 µs | 2.61 µs（x86 自動向量化，不代表 Pico） |
| `-O2 -march=native` / `-mpopcnt`（硬體 popcnt） | 3.47 µs | 2.42 µs | 1.91 µs |

靜態分析（本次 objdump，`bnn_dot` 每個 word 的內迴圈指令數）：

| 目標 | popcount 怎麼來 | 內迴圈 |
|---|---|---|
| rv32 + Zbb（pico-sdk 預設 `-march`） | `cpop` 指令 | 8 條（`lw lw addi addi xnor cpop add bne`） |
| rv32 沒有 Zbb（`-march=rv32imac_zicsr_zifencei`） | 呼叫 `__popcountsi2` | 函式呼叫（本次 objdump 有 2 個呼叫） |
| Cortex-M33 預設 | 呼叫 `__popcountsi2` | 函式呼叫 |
| Cortex-M33 `-DBNN_SWAR_POPCOUNT` | SWAR | 18 條，無呼叫 |
| Cortex-M33 SWAR + 數「不同」 | SWAR | 17 條 |

### 5.5.5 交叉編譯與 qemu-riscv32

6 個核心檔交叉編譯（本次，`-O2 -Wall -Wextra -std=c11`，**全部 0 警告**）：

```bash
# 在 algo/ 外面的資料夾執行；A 指向 algo/
A=~/ncku-exam-prep/預製程式碼/algo
mkdir -p /tmp/algo_arm && cd /tmp/algo_arm
for f in crc32 sha1_sha0 sha256 sort bnn checksum_misc; do
  arm-none-eabi-gcc -mcpu=cortex-m33 -mthumb -O2 -Wall -Wextra -std=c11 -c $A/$f.c -o $f.o; done
arm-none-eabi-size *.o
mkdir -p /tmp/algo_rv && cd /tmp/algo_rv
for f in crc32 sha1_sha0 sha256 sort bnn checksum_misc; do
  riscv64-unknown-elf-gcc -march=rv32imac_zicsr_zifencei_zba_zbb_zbs_zbkb -mabi=ilp32 -O2 -Wall -Wextra -std=c11 -c $A/$f.c -o $f.o; done
riscv64-unknown-elf-size *.o
```

`size` 結果（byte；`text` 含唯讀常數，例如 SHA-256 的 `K` 表）：

| 檔案 | M33 text | M33 bss | rv32 Zbb text | rv32 Zbb bss |
|---|---|---|---|---|
| `crc32.o` | 800 | 5636 | 1044 | 5636 |
| `sha1_sha0.o` | 1088 | 0 | 1468 | 0 |
| `sha256.o` | 1096 | 0 | 1446 | 0 |
| `sort.o` | 936 | 0 | 1008 | 0 |
| `bnn.o` | 700（`-DBNN_SWAR_POPCOUNT` 768） | 0 | 844（無 Zbb 926） | 0 |
| `checksum_misc.o` | 392 | 0 | 352 | 0 |

全部核心檔加起來 M33 不到 5 KB 程式碼 + 5.5 KB 表格（RP2350 有 520 KB SRAM）。

**qemu-riscv32 跑測試**：picolibc 沒有 `CLOCK_MONOTONIC`，也不會自己呼叫 Linux 系統呼叫，所以 ch05 自寫了一個小墊片 `shim.c`（stdout 走 Linux `write`、`clock_gettime` 走 `clock_gettime64`、自己的 stack）和 `shim_main.c`（把測試的 `main` 改名成 `test_main` 再呼叫），編譯旗標：

```text
riscv64-unknown-elf-gcc -march=rv32imac_zicsr_zifencei_zba_zbb_zbs_zbkb -mabi=ilp32 --specs=picolibc.specs -O2 -std=c11
  -include shim.h -Dmain=test_main（只加在測試檔）
  -Wl,--defsym=__ram_size=0x4000000 -Wl,--defsym=__data_source=__data_start -Wl,--defsym=__tdata_source=__tdata_start
  -Wl,--defsym=__stack=shim_stack+0x100000 -Wl,--no-gc-sections
```

結果：`crc32_test`、`sha_test`、`sort_test`、`bnn_test`、`checksum_misc -DTEST_MAIN` **5 支全部 `結果：全部通過`、exit 0**。這證明程式在 32-bit `size_t`、rv32 + Zbb 上也正確。qemu 上的時間（只供參考，不是硬體速度）：

```text
crc32_bitwise 77.77 ms / crc32_table 11.05 ms / crc32_slice4 4.15 ms（4 MB）
sha1 34.36 ms / sha0 41.07 ms / sha256 321.61 ms（4 MB）
qsort 607.89 ms / merge 148.91 ms / radix 24.44 ms（n = 2^20）
bnn 每層 12.26 us
```

### 5.5.6 記憶體（Cortex-M33，`-fstack-usage`，本次實測）

| 函式 | 本身 stack（byte） | 備註 |
|---|---|---|
| `radix_sort_u32` | 1064 | `size_t cnt[256]` = 1 KB |
| `sha256` 的 `compress` | 336 | `w[64]` = 256 byte |
| `sha256` | 136 | 含 `sha256_ctx`（112） |
| `sha1` / `sha0` | 128 | 含 `sha1_ctx`（104） |
| `sha1_sha0.c` 的 `compress` | 128 | |
| `kway_merge` | 88 | `pos[16]` |
| `merge_sort_u32` | 64 | |
| `bnn_dense_sign` / `bnn_dot` | 48 / 40 | |
| `crc_generic` | 32 | |
| 其他（CRC 查表、checksum、insertion…） | 0~28 | |

最壞的呼叫鏈：`sha256()` → `sha256_update` → `compress` = 136 + 24 + 336 = 496 byte；`sha1()` 鏈 = 128 + 24 + 128 = 280 byte。靜態記憶體只有 `crc32.c` 的表 5636 byte。

## 5.6 限制、已知問題、沒驗證的地方

**程式問題（本次發現，沒有改程式）**：

1. **`crc_generic` 的 width < 8 是未定義行為**（`crc32.c:110`：`crc ^= b << (c->width - 8);`）。`crc32.h:33` 註解寫了「8..32」，但程式沒檢查。本次 UBSan 對 width = 7 回報 `crc32.c:110:18: runtime error: shift exponent -1 is negative`，回傳 0（CRC-7/MMC 正確值 0x75）。width = 0 或 > 32 同樣會出錯。替代：食譜 5.4.1 的 `crc_bits`。
2. **`crc32_update` 和 `pico/serial_proto.c:25` 同名**，同一個執行檔同時放 `algo/crc32.c` 和 `pico/serial_proto.c` 會 `multiple definition` 連結失敗（本次實測）。修法見食譜 5.4.6。
3. **`kway_merge` 的 k > `KWAY_MAX`（16）會默默截斷**（`sort.c:69`），第 17 段以後的資料不會出現在輸出裡，也沒有回傳錯誤。輸出長度少了，呼叫者若照 Σlens 讀 `out` 會讀到舊資料。
4. **CRC 表的懶惰初始化不是執行緒安全的**：`crc32_table`、`crc32_slice4`、`crc32c_update`、`crc16_ccitt_false` 在 `!inited` 時呼叫 `crc32_init()`（例如 `crc32.c:55`）。兩核同時第一次呼叫會同時寫表（寫的值一樣，實務上多半沒事，但屬於資料競爭）。雙核心時先在 core0 呼叫 `crc32_init()` 再啟動 core1。
5. **`radix_sort_u32` 在 M33 上用 1064 byte stack**（`sort.c:48` 的 `size_t cnt[256]`）。Pico 的 core1 預設 stack 是 `PICO_CORE1_STACK_SIZE` = 0x800（2 KB，pico-sdk `pico/multicore.h:32-37`），呼叫鏈深時會不夠。檔頭沒有提醒。
6. **`bnn_fold_bn` 的 `(int32_t)t`**（`bnn.c:49` 的 `ceil_f`）：`|t| > 2^31` 時是未定義行為。正常 BN 參數不會發生（只有 gamma 非常接近 0 時）。
7. **`bnn_dense_sign` 要求 `thr` 非 NULL**（`bnn.c:31` 直接讀 `L->thr[j]`），`bnn.h:48` 的註解只說最後一層可 NULL，容易誤用。
8. **`bnn_test.c:78` 的 `uint32_t x[2]` 寫死 2 個 word**，改 `N_IN` 超過 64 時會出界（`TODO` 註解沒提到這行）。

**註解和實測不符（不影響正確性）**：

9. `sha1_sha0.c:1` 說「stack 用約 64 byte」；M33 實測 `compress` 128 byte、`sha1()` 整條呼叫鏈 280 byte。
10. `crc32.c:53` 說查表「約快 5~8 倍」、`:61` 說 slice-by-4「再快 2~3 倍」；本次 host 實測查表 4.2 倍、slice4 再 3.0 倍（README 在 Ryzen 上是 4.1 倍、3.0 倍）。
11. `sha256_update` 逐 byte 複製進 `buf`（`sha256.c:51-54`），不像 `sha1_update` 整塊直接算。這是 SHA-256 比 SHA-1 慢的原因之一（另一個是回合計算較重）；本次沒有拆開量兩者各占多少。

**功能限制**：

12. `crc_generic` 不能分段（每次呼叫都重套 init、xorout）；`fletcher16` 也不能分段。
13. `checksum_misc.c` 沒有 Fletcher-32（5.3.11 有 ch05 自寫版）。
14. `bnn.c` 只有 dense 層，沒有 binary conv / max-pool（`bnn.h:9-10` 只在註解說明作法）。
15. `test_util.h` 用 POSIX 計時，`*_test.c` 不能直接在 Pico 上跑（設計如此，`README.md:4`）。

**沒驗證的地方**：

16. **所有 Pico 2 上的速度都沒有實測**；DMA sniffer = zlib CRC-32 的設定只由暫存器文件推導（已知問題 9，屬第 3 章 `pico/app_dma.c`，上板要看自我測試 PASS/FAIL）。sniffer 的 CRC-16 / 不反轉 CRC-32 對應（食譜 5.4.2）⚠️未驗證。
17. RISC-V 版 Pico 專案在本容器無法完整連結（缺 newlib 的 `nosys.specs`，5.4.6）；核心檔單獨編譯與 qemu 測試都通過。
18. 去年 eBNN 題目的原始檔案、權重格式不在 repo 裡；5.2.8 的對照是依 `預測考題.md` 的摘要推的。
19. Python `bnn_fold_bn`（double）和 C（float）在門檻剛好落在整數邊界時可能差 1（5.4.7）。
20. eBNN 原論文程式的位元順序、BN 實作細節本次沒有查證（⚠️未驗證）；題目給權重時以題目說明為準，用 5.4.5 的轉換。

## 5.7 一頁速查表

**編譯（在 `algo/`，`B=/tmp/algo_build`）**

| 要做 | 指令 | 成功的樣子 |
|---|---|---|
| CRC 測試 | `gcc -O2 -Wall -Wextra -std=c11 crc32.c crc32_test.c -o $B/crc && $B/crc` | `結果：全部通過`（17 PASS） |
| SHA 測試 | `gcc -O2 -Wall -Wextra -std=c11 sha1_sha0.c sha256.c sha_test.c -o $B/sha && $B/sha` | 10 PASS |
| 排序測試 | `gcc -O2 -Wall -Wextra -std=c11 sort.c sort_test.c -o $B/sort && $B/sort` | 5 PASS |
| BNN 測試 | `gcc -O2 -Wall -Wextra -std=c11 bnn.c bnn_test.c -o $B/bnn && $B/bnn` | 4 PASS |
| 校驗碼測試 | `gcc -O2 -Wall -Wextra -std=c11 -DTEST_MAIN checksum_misc.c -o $B/ck && $B/ck` | 13 PASS |
| 用 sanitizer 再跑 | 把 `-O2` 換成 `-O1 -g -fsanitize=address,undefined` | 同上、沒有 `runtime error` |
| M33 只編核心 | `arm-none-eabi-gcc -mcpu=cortex-m33 -mthumb -O2 -c crc32.c` | 0 警告 |
| rv32 只編核心 | `riscv64-unknown-elf-gcc -march=rv32imac_zicsr_zifencei_zba_zbb_zbs_zbkb -mabi=ilp32 -O2 -c bnn.c` | 0 警告 |

**函式簽名**

| 函式 | 一句話 |
|---|---|
| `uint32_t crc32_update(uint32_t crc, const uint8_t *p, size_t n)` | zlib CRC-32；第一段傳 0，可分段 |
| `uint32_t crc32c_update(uint32_t crc, const uint8_t *p, size_t n)` | CRC-32C；第一段傳 0 |
| `uint16_t crc16_ccitt_false(uint16_t crc, const uint8_t *p, size_t n)` | 第一段傳 `0xFFFF`（傳 0 = XMODEM） |
| `uint32_t crc_generic(const crc_param_t *c, const uint8_t *p, size_t n)` | `{width, poly, init, refin, refout, xorout}`，width 8..32，不能分段 |
| `void sha1_init(sha1_ctx *c, int is_sha0)` | **1 = SHA-0**、0 = SHA-1 |
| `void sha1_update(sha1_ctx *c, const uint8_t *p, size_t n)` / `void sha1_final(sha1_ctx *c, uint8_t out[20])` | 串流 |
| `void sha0(const uint8_t *p, size_t n, uint8_t out[20])` / `sha1(...)` / `sha256(..., uint8_t out[32])` | 一次算完 |
| `void radix_sort_u32(uint32_t *a, size_t n, uint32_t *tmp)` | 最快；有號數前後 `^= 0x80000000u` |
| `void merge_sort_u32(uint32_t *a, size_t n, uint32_t *tmp)` / `void insertion_sort_u32(uint32_t *a, size_t n)` | 穩定 / 小陣列 |
| `void merge_two_sorted(const uint32_t *a, size_t na, const uint32_t *b, size_t nb, uint32_t *out)` | out 不可重疊 |
| `void kway_merge(const uint32_t *const lists[], const size_t lens[], int k, uint32_t *out)` | k ≤ 16，否則默默截斷 |
| `void bnn_pack(const int8_t *v, int n, uint32_t *out)` | `v > 0` → 1 |
| `int32_t bnn_dot(const uint32_t *a, const uint32_t *w, int n)` | `2*popcount(~(a^w)) - n` |
| `void bnn_dense_sign(const bnn_layer_t *L, const uint32_t *in, uint32_t *out_bits)` | 隱藏層；thr 必填 |
| `void bnn_dense_score(const bnn_layer_t *L, const uint32_t *in, int32_t *score)` / `int bnn_argmax(const int32_t *s, int n)` | 輸出層 |
| `void bnn_fold_bn(float gamma, float beta, float mean, float std, float bias, int32_t *thr, uint8_t *flip)` | `std = sqrtf(var + eps)` |
| `uint32_t adler32(uint32_t adler, const uint8_t *p, size_t n)` | 第一次傳 1 |
| `uint16_t inet_csum(const uint8_t *p, size_t n)` | RFC 1071，大端 |

**標準答案（拿來驗證）**

| 輸入 | 結果 |
|---|---|
| CRC-32（zlib）`"123456789"` | `0xCBF43926`（少 XOR = `0x340BC6D9`、位元反轉 = `0x649C2FD3`） |
| CRC-32C `"123456789"` | `0xE3069283` |
| CRC-16/CCITT-FALSE、XMODEM、MODBUS `"123456789"` | `0x29B1`、`0x31C3`、`0x4B37` |
| SHA-0 `"abc"` | `0164b8a914cd2a5e74c4f7ff082c4d97f1edf880` |
| SHA-1 `"abc"` | `a9993e364706816aba3e25717850c26c9cd0d89d` |
| SHA-256 `"abc"` | `ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad` |
| Adler-32 `"Wikipedia"` | `0x11E60398` |
| Fletcher-16 `"abcde"` | `0xC8F0` |

**常見錯誤**

| 症狀 | 第一個要檢查的 |
|---|---|
| CRC 差一個 `~` | xorout（5.2.4 JAMCRC 那列） |
| CRC-16 = `0x31C3` 但要 `0x29B1` | `crc16_ccitt_false` 第一段要傳 `0xFFFF` |
| `multiple definition of 'crc32_update'` | 和 `pico/serial_proto.c` 衝突（食譜 5.4.6） |
| SHA-0 結果 = SHA-1 | `sha1_init` 第二個參數要 1 |
| 分包 SHA 結果錯 | 只能 init 一次、final 一次、照順序餵 |
| 負數排在最後 | `^= 0x80000000u` |
| 合併結果少資料 | `kway_merge` k > 16 |
| BNN 分數差、n 非 32 倍數才錯 | 尾巴 mask |
| BNN 全錯 | 權重 bit 順序（`bnn_from_packbits`）、flip |
| Pico 當掉 | 大陣列放 stack；改 `static` |
