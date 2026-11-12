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
