# CMake 實戰手冊（考場用）

> 所有指令都在 `pico-build` 容器裡實際跑過（CMake 3.28、pico-sdk 2.2.0），輸出是真的。
> 注意：**這台主機本身沒有 cmake**，只有容器裡有；考場的 Docker 環境也一樣，要在容器裡跑。
> git、shell、docker 的基本操作看 [`../../prompt工具包/cards/git-env.md`](../../prompt工具包/cards/git-env.md)，這份不重複。

## 1. 先建立正確的概念：兩個步驟 + 一個快取

| 步驟 | 指令 | 做什麼 | 什麼時候要重跑 |
|---|---|---|---|
| ① configure | `cmake -S . -B build` | 讀 `CMakeLists.txt`，產生 `build/Makefile`，把設定寫進 `build/CMakeCache.txt` | 改了 CMakeLists.txt（其實 make 會自動重跑） |
| ② build | `cmake --build build -j8`（等於 `make -C build -j8`） | 真正呼叫 gcc 編譯和連結 | 每次改 .c/.h |

- `-S .`：原始碼在這裡；`-B build`：所有產物放 `build/`（**out-of-source**：原始碼資料夾保持乾淨，`rm -rf build` 就全清）。
- **快取會「記住」舊設定**：`-DUSE_FAST=ON` 設過一次後，下次只打 `cmake -B build` 還是 ON（實測）。
- 想清掉設定有兩種方法：`cmake --fresh -B build`（CMake ≥ 3.24，實測後 `USE_FAST` 回到 OFF），或最保險的 `rm -rf build`。
- **「改了設定卻沒效」、「換了資料夾」、「換了 -G」→ 一律 `rm -rf build` 重來。**

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Debug -DUSE_FAST=ON   # -D 設快取變數
cmake -L -N build | head          # 列出快取變數 (實測會看到 CMAKE_BUILD_TYPE:STRING=Debug, USE_FAST:BOOL=OFF)
grep USE_FAST build/CMakeCache.txt
cmake --build build -j8           # 編全部
cmake --build build --target app  # 只編一個 target（等於 make -C build app）
cmake --build build -v            # 看真正的 gcc 指令（等於 make -C build VERBOSE=1）
make -C build help                # 列出所有 target
cmake --build build --target clean
```

`make help` 實際輸出（mini 專案）：
```
... all (the default if no target is provided)
... clean
... app
... mylib
```
`-v` 看到的真正指令（要確認 `-O`、`-D`、`-I` 有沒有真的加上去時用）：
```
/usr/bin/cc  -I/w/mini/include -I/w/mini/lib -O3 -DNDEBUG -Wall -Wextra ... -c /w/mini/src/main.c
/usr/bin/cc -O3 -DNDEBUG CMakeFiles/app.dir/src/main.c.o ... -o app  lib/libmylib.a -lm
```
- 坑：`if(NOT CMAKE_BUILD_TYPE) set(CMAKE_BUILD_TYPE Release)` 這種寫法，快取裡顯示 `CMAKE_BUILD_TYPE:STRING=`（空的），但實際用 Release（`-O3 -DNDEBUG`）。**要確認就看 `-v` 的輸出，不要只看快取。**
- `-DNDEBUG` = `assert()` 被拿掉！Release 版 assert 不會觸發。

## 2. 看不懂的 CMakeLists.txt：問 6 個問題

| # | 問題 | 找這些字 | 指令 |
|---|---|---|---|
| 1 | 有哪些 target（會產生什麼執行檔或函式庫）？ | `add_executable`、`add_library`、自訂 `function(add_app ...)` | `make -C build help` |
| 2 | 每個 target 用哪些原始碼？ | `add_executable(名字 a.c b.c)`、`set(SRCS ...)`、`file(GLOB ...)` | `grep -n "add_executable\|set(" CMakeLists.txt` |
| 3 | 連結了哪些函式庫？ | `target_link_libraries` | `grep -n target_link CMakeLists.txt` |
| 4 | 有哪些 define、選項、編譯參數？ | `option(`、`target_compile_definitions`、`-D`、`CMAKE_BUILD_TYPE` | `cmake -L -N build` |
| 5 | 有沒有子資料夾？ | `add_subdirectory(lib)` → 去看 `lib/CMakeLists.txt` | `find . -name CMakeLists.txt -not -path './build/*'` |
| 6 | 產物在哪？ | 預設是 `build/`（子資料夾的 target 在 `build/<子資料夾>/`） | `find build -name '*.uf2' -o -name '*.elf'` |

**另外一定要看 `.gitlab-ci.yml` 的 `script:`**：評分機器用什麼參數跑 cmake，你就用一樣的參數。

## 3. 常見修改（直接複製）

```cmake
# 加一個 .c 檔：加在原本的 add_executable 裡
add_executable(app src/main.c src/util.c src/new.c)
# 或另外加
target_sources(app PRIVATE src/new.c)

# 加 include 資料夾（#include "xxx.h" 找不到時）
target_include_directories(app PRIVATE include)

# 連結函式庫（優先用 target_ 開頭的，只影響這個 target）
target_link_libraries(app PRIVATE mylib m)     # m = libm (sqrt、sin…)
target_link_libraries(app PRIVATE pthread)     # 或 find_package(Threads) + Threads::Threads
# link_libraries(m)  ← 舊式寫法：影響「之後」所有 target，要寫在 add_executable 前面才有效（實測可用，但不建議）

# 定義巨集（等於 -DUSE_FAST=1）
target_compile_definitions(app PRIVATE USE_FAST=1)

# 開關選項：cmake -DUSE_FAST=ON 打開
option(USE_FAST "use fast path" OFF)
if(USE_FAST)
  target_compile_definitions(app PRIVATE USE_FAST=1)
endif()

# 最佳化
#   命令列：cmake -B build -DCMAKE_BUILD_TYPE=Release   (-O3 -DNDEBUG)
#           cmake -B build -DCMAKE_BUILD_TYPE=Debug     (-g，主機 gcc 是 -O0；pico 是 -Og -g)
target_compile_options(app PRIVATE -O2 -Wall -Wextra) # 排在後面的 -O 會蓋掉前面的（實測 -g ... -O2 → 用 -O2）

# 再加一個執行檔
add_executable(app2 src/app2.c src/util.c)
target_include_directories(app2 PRIVATE include)
target_link_libraries(app2 PRIVATE mylib m)

# 子資料夾
add_subdirectory(lib)        # lib/CMakeLists.txt 裡要有 add_library(mylib STATIC mylib.c)
```

### PRIVATE / PUBLIC 是什麼
- `target_include_directories(mylib PUBLIC dir)`：mylib 自己用，**連結 mylib 的人也自動拿到** `-Idir`。
- 改成 `PRIVATE`：只有 mylib 自己用 → app 編譯時 `fatal error: mylib.h: No such file or directory`（實測）。
- 規則：函式庫的標頭要給別人用 → `PUBLIC`；執行檔 → 都用 `PRIVATE`。

### find_package 基本
```cmake
find_package(Threads REQUIRED)
target_link_libraries(app PRIVATE Threads::Threads)
```
`REQUIRED` 找不到就在 configure 階段直接報錯（錯誤訊息見 §6 表格 #10）。`Xxx::Yyy` 這種有 `::` 的名字是 target，打錯會在 configure 報錯；沒有 `::` 的名字打錯，要到 link 才報錯。

## 4. pico-sdk 專用

| 規則 | 寫法 / 說明 |
|---|---|
| 順序 | `cmake_minimum_required` → `set(PICO_BOARD pico2)` → **`include(pico_sdk_import.cmake)`** → `project(x C CXX ASM)` → **`pico_sdk_init()`** → add_executable… |
| SDK 位置 | 環境變數 `PICO_SDK_PATH`（容器裡是 `/opt/pico-sdk`）；檢查 `echo $PICO_SDK_PATH` |
| 板子 | `-DPICO_BOARD=pico2`（預設 ARM = `rp2350-arm-s`） |
| RISC-V | `-DPICO_PLATFORM=rp2350-riscv`，要 `riscv32-unknown-elf-gcc`；pico-build 只有 `riscv64-unknown-elf-gcc`，實測找不到編譯器（見 §6 #21） |
| 每個程式 | `target_link_libraries(x pico_stdlib)` 一定要 |
| stdio 走哪 | `pico_enable_stdio_usb(x 1)`（/dev/ttyACM*）、`pico_enable_stdio_uart(x 1)`（GP0=TX、GP1=RX，115200） |
| 產生檔案 | `pico_add_extra_outputs(x)` → `x.uf2 x.bin x.hex x.dis x.elf.map`（沒加就只有 `.elf`） |
| PIO | `pico_generate_pio_header(x ${CMAKE_CURRENT_LIST_DIR}/pio/echo.pio)` → 產生 `build/echo.pio.h` |
| 二進位傳輸 | `target_compile_definitions(x PRIVATE PICO_STDIO_DEFAULT_CRLF=0)`（預設 1，會把 `\n` 改成 `\r\n`） |
| 產物位置 | `build/x.uf2`（如果 target 在子資料夾，就在 `build/子資料夾/`） |

### 常用函式庫名稱（`#include` → 要 link 的名字）

| `#include` | target_link_libraries |
|---|---|
| `pico/stdlib.h` | `pico_stdlib` |
| `hardware/dma.h` | `hardware_dma` |
| `hardware/pio.h` | `hardware_pio` |
| `pico/multicore.h` | `pico_multicore` |
| `hardware/sync.h`（spin_lock、`__dmb`） | `hardware_sync`（pico_stdlib 已包含） |
| `pico/mutex.h`、`pico/sem.h`、`pico/critical_section.h` | `pico_sync` |
| `pico/util/queue.h` | `pico_util`（pico_stdlib 已包含） |
| `hardware/uart.h`、`hardware/gpio.h` | `hardware_uart`、`hardware_gpio`（pico_stdlib 已包含） |
| `hardware/adc.h`、`hardware/pwm.h`、`hardware/i2c.h`、`hardware/spi.h`、`hardware/irq.h`、`hardware/interp.h` | `hardware_adc`、`hardware_pwm`、`hardware_i2c`、`hardware_spi`、`hardware_irq`、`hardware_interp` |

**不知道某個標頭要 link 什麼 → 去 SDK 找：標頭上面兩層的資料夾名稱 = 函式庫名稱。**
```bash
cd $PICO_SDK_PATH/src
find . -name dma.h -path '*include*'
#  ./rp2_common/hardware_dma/include/hardware/dma.h   ← 函式庫名稱 = hardware_dma
find . -name multicore.h
#  ./rp2_common/pico_multicore/include/pico/multicore.h  ← pico_multicore
#  ./host/pico_multicore/...   (host/ 是給電腦模擬用的，不要管)
ls rp2_common common            # 所有函式庫的清單
```

### picotool 在哪
- SDK 找不到已安裝的 picotool 時，會在第一次 configure **從 GitHub 下載並編譯**（要網路）：`build/_deps/picotool/picotool`。
- ⚠ 實測：pico-build 容器裡沒有 libusb，所以編出來的 picotool 印出 `This version of picotool was compiled without USB support`，**只有 `info`、`uf2` 等指令，沒有 `load`、`reboot`**。要用 load 就要有 USB 版的 picotool（考場映像檔裡如果有，用 `which picotool` 找）。
- 已經編過一次了，重開 build 資料夾不想再下載：`cmake -B build2 -Dpicotool_DIR=$PWD/build/_deps/picotool`（實測可用）。

## 5. ROS 2：colcon / ament

在 `ros:jazzy-ros-core` 加裝 `python3-colcon-common-extensions build-essential` 後實測（ros-core **沒有 colcon 也沒有 gcc**）。

```bash
cd ~/ws                                   # workspace 根目錄 (底下有 src/)
colcon build --symlink-install            # 全部
colcon build --packages-select my_cpp_pkg # 只編一個 (名字打錯只會 WARNING + "0 packages finished"，不會報錯！)
colcon build --packages-select my_cpp_pkg --event-handlers console_direct+   # 即時印出完整 CMake/gcc 輸出
source install/setup.bash                 # 每次 build 完、每開新終端機都要
rm -rf build install log                  # 完全清除 (CMake 快取問題時)
```

| 套件類型 | 建置描述檔 | 執行檔怎麼註冊 |
|---|---|---|
| `ament_cmake`（C++，或 msg/srv 介面套件） | `CMakeLists.txt` + `package.xml` | `install(TARGETS talker_cpp DESTINATION lib/${PROJECT_NAME})` |
| `ament_python` | `setup.py` + `package.xml` | `entry_points={'console_scripts': ['talker_py = my_py_pkg.talker_py:main']}` |

- `ros2 pkg create --build-type ament_cmake --dependencies rclcpp std_msgs --node-name talker_cpp my_cpp_pkg` 可以產生骨架（ros-core 有這個指令）。
- `--symlink-install` 的效果：`build/my_py_pkg/my_py_pkg -> /ws/src/my_py_pkg/my_py_pkg`，改 .py 不用重 build（改 setup.py 還是要）。
- **錯誤記錄在哪**：終端機只印摘要；完整內容在 `log/latest_build/<pkg>/stdout_stderr.log`（還有 `stderr.log`、`command.log`）。
- 實測：把 `find_package(std_msgs REQUIRED)` 打成 `std_msgz` → `--- stderr: my_cpp_pkg` 底下出現 `CMake Error at CMakeLists.txt:11 (find_package): ... "std_msgz"`。
- 自訂 msg 套件看 [`../ros2/custom_msg_cheatsheet.md`](../ros2/custom_msg_cheatsheet.md)。

| 症狀（實測） | 原因 | 修法 |
|---|---|---|
| `Package 'my_py_pkg' not found` | 新終端機沒 source | `source install/setup.bash` |
| `No executable found` | 執行檔名字打錯，或 setup.py 沒有 entry_points | `ros2 pkg executables my_py_pkg` 看正確名字 |
| `ModuleNotFoundError: No module named 'my_py_pkg.talker_pi'` | entry_points 的模組路徑打錯 | 修 setup.py → 重 build |
| `ignoring unknown package 'x' in --packages-select` | 套件名稱打錯（看 package.xml 的 `<name>`） | `colcon list` 看正確名稱 |

## 6. CMake 錯誤 → 修法對照表（每一行都是實際製造出來的錯誤）

| # | 關鍵錯誤訊息 | 原因 | 修法 |
|---|---|---|---|
| 1 | `CMake 3.99 or higher is required.  You are running version 3.28.3` | `cmake_minimum_required` 版本太高 | 改成 `VERSION 3.13`（pico）或 `3.16` |
| 2 | `Cannot find source file: src/utils.c` + `No SOURCES given to target: app` | 檔名打錯或檔案不存在 | `ls src/` 確認後修正 |
| 3 | 只有 `No SOURCES given to target: app` | 變數名稱打錯：`set(APP_SRCS ...)` 卻寫 `${APP_SRC}`（CMake 不認識的變數 = 空字串，**不會報錯**） | 名稱改成一致；可以用 `message(STATUS "SRCS=${APP_SRCS}")` 印出來檢查 |
| 4 | `fatal error: util.h: No such file or directory` | 少了 `target_include_directories` | 加上 include 資料夾 |
| 5 | `undefined reference to 'sqrt'` + `ld returned 1 exit status` | 有標頭但沒連結函式庫（libm） | `target_link_libraries(app PRIVATE m)` |
| 6 | `fatal error: mylib.h: No such file or directory`（其實是 link 名稱打成 `mylibb`） | target 名字打錯 → 拿不到它的 PUBLIC include | 對照 `add_library(...)` 的名字 |
| 7 | `cannot find -lpico_multicor: No such file or directory`（ld） | 沒有 `::` 的名字打錯 → CMake 當成系統函式庫 `-l` | 改正名稱（§4 表格） |
| 8 | `Target "app" links to: Foo::bar but the target was not found` | `::` target 打錯或少了 `find_package` | 補 `find_package` 或改正名稱 |
| 9 | `Cannot specify link libraries for target "app2" which is not built by this project` | target 名字打錯，或 `target_link_libraries` 寫在 `add_executable` **前面** | 移到後面或改正名字 |
| 10 | `By not providing "FindFoo.cmake" in CMAKE_MODULE_PATH ... did not find one` | `find_package(Foo REQUIRED)` 找不到套件（ROS：忘了 source 或少裝套件） | source 環境 / 確認套件名稱 |
| 11 | `Unknown CMake command "target_compile_option"` | 指令名稱打錯（少了 s） | 改正 |
| 12 | `Parse error.  Function missing ending ")".  End of file reached.` | 括號沒有關 | 看它指出的行號 |
| 13 | `The current CMakeCache.txt directory ... is different than the directory ... where CMakeCache.txt was created` | 把整個專案（含 build/）複製或搬到別的地方 | `rm -rf build` |
| 14 | `generator : Ninja  Does not match the generator used previously: Unix Makefiles` | 同一個 build/ 換了 `-G` | `rm -rf build` 或換一個 `-B` 資料夾 |
| 15 | `SDK location was not specified.  Please set PICO_SDK_PATH` | 環境變數沒設（新開的 shell、不是在容器裡） | `export PICO_SDK_PATH=/opt/pico-sdk` 後 `rm -rf build` 重來 |
| 16 | `boot2_w25q080.S:22: Error: unknown pseudo-op: '.syntax'` | `include(pico_sdk_import.cmake)` 寫在 `project()` **後面** → 用了電腦的 gcc（快取裡 `CMAKE_C_COMPILER=/usr/bin/cc`） | 移到 `project()` 前面，`rm -rf build` |
| 17 | `Unknown CMake command "pico_enable_stdio_usb"` | 忘了 `pico_sdk_init()` | 在 `project()` 後面補上 |
| 18 | `fatal error: hardware/dma.h: No such file or directory` | 沒 link `hardware_dma`（或名字打錯成 `hardware_dmaa`） | `target_link_libraries(x hardware_dma)` |
| 19 | `fatal error: bitstream_in.pio.h: No such file or directory` | 少了 `pico_generate_pio_header` | 補上那一行 |
| 20 | `Unable to find definition of board 'pico3' (specified by PICO_BOARD)` | 板子名稱錯 | `-DPICO_BOARD=pico2`，`rm -rf build` |
| 21 | `Compiler 'riscv32-unknown-elf-gcc / riscv32-corev-elf-gcc' not found` | 指定 `rp2350-riscv` 但容器沒有 riscv32 工具鏈 | 改用 ARM，或 `-DPICO_TOOLCHAIN_PATH=...` 指到考場提供的工具鏈 |

**看錯誤的順序**：
1. 先分出是 **configure 錯**（`CMake Error at CMakeLists.txt:行號`）、**compile 錯**（`file.c:行:欄: error:`），還是 **link 錯**（`undefined reference`、`cannot find -l`、`ld returned`）。
2. 只看**第一個** error，後面的常常是它連帶造成的。
3. `gmake[2]: *** ... Error 1` 這幾行只是「失敗了」的通知，原因在它的**上面**。
