# 貼上卡：CMake 與建置（pico-sdk / colcon）
> 用法：一次只複製一張卡（兩條分隔線之間），把 `{{...}}` 換成你的內容，貼進對話送出。每張都能在新對話直接用。提示卡＝填空後送出的問句；參考卡＝貼給模型當正確資料。每張 ≤ 1200 字元。
> 寫法：第一行 `Task (EN)` 是英文任務句，給中文較弱的模型定錨；資料放在 `<<<資料 開始>>>` 和 `<<<資料 結束>>>` 之間；輸出格式放在資料後面。標題後的 `→` 是下一張。原則見 README「為什麼卡片這樣寫」。
> 流程：錯誤 → 建置 2 或 3（定位）→ 建置 4（改）→ 跑驗證指令。完整手冊（給自己讀）：`../預製程式碼/tools/cmake.md`。
> 來源：pico-sdk 2.2.0 原始碼（Docker `pico-build` 的 /opt/pico-sdk，grep 與試編確認）、`../預製程式碼/pico/CMakeLists.txt`、`../預製程式碼/micro-ros/CMakeLists.txt`、`../預製程式碼/ros2/README.md`｜最後更新 2026-11

---

【提示卡｜建置 1/7｜解讀這份 CMakeLists.txt】→ 有錯用建置 2，要改用建置 4
Task (EN): Fill the table using only the CMakeLists.txt and CI script below. Quote evidence. Answer in Traditional Chinese.
任務：只根據資料填表。
<<<資料 開始>>>
[CMakeLists.txt]（太長先貼前 60 行）
{{貼}}
[CI 建置指令]（.gitlab-ci.yml 的 script 段；沒有寫「無」）
{{貼}}
<<<資料 結束>>>
規則：只根據資料；找不到寫「資料中沒有」。證據要抄原文那一行。
只輸出這個表，每格 ≤ 1 行：
| 項目 | 內容 | 證據 |
| target 與原始檔 | | |
| 連的函式庫 | | |
| 巨集 / 編譯選項 | | |
| PICO_BOARD / PICO_PLATFORM / build type | | |
| stdio（usb / uart） | | |
| PIO header、extra outputs | | |
| 輸出檔與位置 | | |
| CI 的 configure 指令（抄 [CI 建置指令]） | | |
| CI 的 build 指令（抄 [CI 建置指令]） | | |
範例（只示範格式，內容不要照抄）：| 連的函式庫 | app_dma：pico_stdlib、hardware_dma | 「target_link_libraries(app_dma hardware_dma)」 |

---

【提示卡｜建置 2/7｜CMake / 連結錯誤：定位】→ 建置 4
Task (EN): Classify the FIRST build error into one category A–H. Quote the error line. Do not fix yet. Answer in Traditional Chinese.
任務：判斷第一個錯誤屬於哪一類，先不要修。
取得：`cmake --build build 2>&1 | tee b.log`，再 `grep -n -m1 -B10 -A10 -iE "error|undefined reference" b.log`
<<<資料 開始>>>
[指令] {{例如 cmake -B build -DPICO_BOARD=pico2 && cmake --build build -j}}
[第一個 error 前後 10 行]
{{貼}}
[該 target 的 CMakeLists 段落]
{{貼}}
[環境] pico-sdk {{2.2.0}}；PICO_BOARD={{pico2}}；PICO_PLATFORM={{rp2350-arm-s}}；最近改了 {{…}}
<<<資料 結束>>>
類別（比對錯誤裡的關鍵字）：A 找不到 SDK（SDK location、PICO_SDK_PATH）　B cache 殘留（CMakeCache … different、generator、換過 board）　C 語法或順序（Parse error、Unknown CMake command、pseudo-op .syntax = pico_sdk_import 在 project() 後）　D 找不到 header（No such file）　E undefined reference　F multiple definition（header 變數改 extern）　G overflowed（RAM / flash）　H 其他
只輸出 4 行：
證據：「…」（照抄錯誤那 1 行）
原因（1 句）：
類別（照抄選項，例如「D 找不到 header」）：
要加的函式庫（D、E 必填：hardware/xxx.h → hardware_xxx；其他寫「無」）：
要修的檔案與位置（B 一律 rm -rf build 重來）：
範例（只示範格式，內容不要照抄）：
證據：「fatal error: hardware/dma.h: No such file or directory」
原因：app_dma 沒 link hardware_dma
類別：D 找不到 header
要修的檔案與位置：CMakeLists.txt 的 target_link_libraries(app_dma …)

---

【提示卡｜建置 3/7｜colcon build 失敗：定位】→ 建置 4
Task (EN): Classify the FIRST colcon build error into one category A–H. Quote the error line. Do not fix yet. Answer in Traditional Chinese.
任務：判斷 colcon 的第一個錯誤屬於哪一類，先不要修。
取得：`colcon build --packages-select my_pkg --event-handlers console_direct+ 2>&1 | tee cb.log`（或看 `log/latest_build/my_pkg/stdout_stderr.log`）
<<<資料 開始>>>
[pwd 與 ls src/] {{貼}}
[套件類型] {{ament_cmake / ament_python}}
[第一個 error 前後 10 行]
{{貼}}
[package.xml 的 depend 段] {{貼}}
[CMakeLists.txt 或 setup.py 的 entry_points] {{貼}}
[已 source] {{/opt/ros/jazzy/setup.bash？install/setup.bash？}}
<<<資料 結束>>>
類別：A 沒 source 或不在工作區根目錄　B 找不到依賴（find_package / package.xml）　C C++ 編譯錯　D 連結錯（ament_target_dependencies 沒寫）　E setup.py / entry_points 錯　F 自訂訊息 rosidl 錯　G 舊 build 殘留　H 其他
只輸出 4 行：
證據：「…」（照抄錯誤那 1 行）
原因（1 句）：
類別（照抄選項）：
要修的檔案與位置：
修法只能改檔案或重編；考場不能安裝套件（不用 apt、pip、rosdep）。

---

【提示卡｜建置 4/7｜改建置檔：新增檔案 / 函式庫 / 巨集或修錯】
Task (EN): Output a minimal patch (max 6 changed lines) for the build file below, keeping its existing style. Then 1 verify command and what success looks like. Answer in Traditional Chinese.
任務：給最小修改。
<<<資料 開始>>>
[要做的事] {{新增 foo.c / 用 hardware_dma / 用 pico_multicore / 加 x.pio / 加巨集 FOO=1 / 修建置 2、3 的結果（貼那 4 行）}}
[檔案段落，帶行號]（`cat -n CMakeLists.txt | sed -n 20,60p`）
{{貼}}
[不能改] {{judge 用的 target 名稱、CI 指令}}
<<<資料 結束>>>
規則：
1. 最多改 6 行，只改資料中的檔案。
2. 加函式庫：修改後 = 修改前那一行，只在最後的 `)` 前面加「空格 + 新名稱」，其他字（含 PRIVATE）一個都不動。
3. 名稱看 header，不是函式名：`hardware/xxx.h` → `hardware_xxx`；`pico/xxx.h` → `pico_xxx`。
只輸出：
檔名:行號
修改前：
修改後：
要不要 rm -rf build：是 / 否（理由 1 句）
驗證指令（1 行）：
成功的樣子：
範例（只示範格式，內容不要照抄）：
CMakeLists.txt:37
修改前：target_link_libraries(app_dma hardware_dma)
修改後：target_link_libraries(app_dma hardware_dma hardware_pio)
要不要 rm -rf build：否（只加 link）
驗證指令：cmake --build build -j && ls -l build/app_dma.uf2
成功的樣子：沒有 error，.uf2 的時間是剛剛

---

【參考卡｜建置 5/7｜CMake 通用：configure、cache、target】
以下是正確的參考資料，若與你的記憶不同，以這張為準。CMake 3.x（pico-build 映像為 3.28）。
- configure：`cmake -B build -D變數=值`（或在 build/ 裡 `cmake ..`）→ 讀 CMakeLists.txt，產生 Makefile，寫入 `build/CMakeCache.txt`
- build：`cmake --build build -j`（= `make -C build -j`）→ 編譯、連結
- 只改 .c → 只要 build；改 CMakeLists.txt → build 時自動重跑 configure
- `-D` 的值記在 cache，之後不寫也沿用。換 PICO_BOARD / PICO_PLATFORM / 工具鏈，或「改了沒效果」→ `rm -rf build` 重來
- 查目前值：`grep -E "PICO_BOARD|PICO_PLATFORM|CMAKE_BUILD_TYPE" build/CMakeCache.txt`
- 看完整編譯指令：`make -C build VERBOSE=1`
- `target_link_libraries(t PRIVATE x)` 只給 t；`PUBLIC` 給 t 和連結 t 的；`INTERFACE` 只給連結 t 的
- 同一 target 的 target_link_libraries 全部寫關鍵字或全部不寫；混用 → configure 錯「All uses of target_link_libraries with a target must be either all-keyword or all-plain」（已實測）
- `target_compile_definitions(t PRIVATE FOO=1)` 只給 t；`add_compile_definitions(FOO=1)` 給此目錄之後所有 target
- 少 link 函式庫 → `fatal error: hardware/dma.h: No such file or directory`（已實測）或 undefined reference
- `undefined reference to 'f'`：f 的 .c 沒加進 add_executable，或沒 link；`multiple definition`：header 裡定義了變數
- pico-sdk 沒指定 build type 時預設 `Release`（-O3）；`Debug` 為 -Og。以 judge 指令為準。

---

【參考卡｜建置 6/7｜pico-sdk CMake 順序與名稱】
以下是正確的參考資料，若與你的記憶不同，以這張為準。pico-sdk 2.2.0，RP2350（Pico 2），非 RP2040。
順序：1. `set(PICO_BOARD pico2)` 或 `-DPICO_BOARD=pico2` → 2. `include(pico_sdk_import.cmake)`（在 project() 之前）→ 3. `project(x C CXX ASM)` → 4. `pico_sdk_init()` → 5. add_executable。
平台：pico2 預設 `PICO_PLATFORM=rp2350-arm-s`（Cortex-M33）；RISC-V 用 `-DPICO_PLATFORM=rp2350-riscv`。configure 應印出 `Target board (PICO_BOARD) is 'pico2'`；沒設 board → 預設 rp2040。
函式庫名 = SDK 資料夾名：`src/rp2_common/`（hardware_dma、hardware_pio、hardware_clocks、hardware_irq、pico_multicore、pico_stdlib）或 `src/common/`（pico_sync、pico_util、pico_time）。`pico_stdlib` 已含 hardware_gpio、hardware_uart、pico_time、pico_util、pico_stdio；**不含** hardware_dma、hardware_pio、pico_multicore。
- `pico_enable_stdio_usb(t 1)`、`pico_enable_stdio_uart(t 0)`：SDK 預設 UART 開、USB 關
- `pico_add_extra_outputs(t)`：產生 .uf2 / .bin / .hex / .dis / .map
- `pico_generate_pio_header(t ${CMAKE_CURRENT_LIST_DIR}/x.pio)` → `x.pio.h`；每個用到的 target 各寫一次
- `target_compile_definitions(t PRIVATE PICO_STDIO_DEFAULT_CRLF=0)`：關 \n→\r\n（二進位必備）。SDK 函式庫是 INTERFACE library，跟 t 一起編，所以也作用在 SDK 的 stdio
- 印出「No installed picotool … building from source」= 從 GitHub 下載編 picotool（要網路）

---

【參考卡｜建置 7/7｜colcon / ament（ROS 2 Jazzy）】
以下是正確的參考資料，若與你的記憶不同，以這張為準。ROS 2 Jazzy。
- 在工作區根目錄（有 `src/` 那層）跑 `colcon build` → 產生 `build/ install/ log/`
- `--packages-select a b` 只編這些；`--packages-up-to a` 連依賴一起
- `--symlink-install`：Python 改了不用重編
- `--event-handlers console_direct+`：印出完整編譯輸出
- `--cmake-args -DCMAKE_BUILD_TYPE=Release`
- 錯誤 log：`log/latest_build/<套件>/stdout_stderr.log`
- 每個新 shell：`source /opt/ros/jazzy/setup.bash`；build 完再 `source install/setup.bash`
- 舊結果殘留：`rm -rf build/<套件> install/<套件>` 再編
- `Could not find a package configuration file provided by "X"`：沒 source，或 X 沒安裝（考場不能裝）
ament_cmake（C++）順序：`find_package(ament_cmake REQUIRED)`、`find_package(rclcpp REQUIRED)`、`find_package(std_msgs REQUIRED)` → `add_executable(n src/n.cpp)` → `ament_target_dependencies(n rclcpp std_msgs)` → `install(TARGETS n DESTINATION lib/${PROJECT_NAME})`（少這行 `ros2 run` 找不到）→ 最後 `ament_package()`。package.xml 要有 `<depend>rclcpp</depend>`、`<depend>std_msgs</depend>`。
ament_python：setup.py `entry_points={'console_scripts': ['n = pkg.n:main']}`。
自訂 .msg 只能放 ament_cmake 套件：`rosidl_generate_interfaces(...)` + package.xml `<member_of_group>rosidl_interface_packages</member_of_group>`。
