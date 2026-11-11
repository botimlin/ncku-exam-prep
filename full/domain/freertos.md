# FreeRTOS（SMP）on RP2350 + pico-sdk

> 用途：**備援包**。考前 demo 沒有提到 RTOS；若考場專案出現 `FreeRTOS.h`、`FreeRTOSConfig.h`、`xTaskCreate`、`FREERTOS_KERNEL_PATH`，就用本檔。內容涵蓋：概念、pico-sdk 整合（CMake / FreeRTOSConfig.h）、API 簽名、ISR 規則、SMP 雙核注意事項、效能與除錯。裸機的 pico 多核（`multicore_fifo`、spinlock、`queue_t`、`critical_section_t`）請看 `multicore-sync.md`；RP2350 基礎、CMake、IRQ 基本 API 請看 `pico-sdk.md`。
> 適用版本：FreeRTOS-Kernel V11.x（查證時最新 release 為 V11.3.3，以及 main 分支 2026-10），RP2350 port 來自 FreeRTOS-Kernel-Community-Supported-Ports（`GCC/RP2350_ARM_NTZ`、`GCC/RP2350_RISC-V`，2026-03）；pico-sdk 2.3.1；pico-examples `freertos/hello_freertos`。port 的 CMake 要求 pico-sdk ≥ 2.0.0。
> 來源（實際查證過）：
> - FreeRTOS-Kernel 原始碼 https://github.com/FreeRTOS/FreeRTOS-Kernel （`include/task.h`、`queue.h`、`semphr.h`、`event_groups.h`、`timers.h`、`stream_buffer.h`、`message_buffer.h`、`projdefs.h`、`FreeRTOS.h`、`tasks.c`（SMP `vTaskEnterCritical/ExitCritical`、idle task 命名）、`timers.c`、`portable/MemMang/heap_1..5.c`、`examples/template_configuration/FreeRTOSConfig.h`（每個 config 的官方說明）、`.gitmodules`）
> - RP2350 port https://github.com/FreeRTOS/FreeRTOS-Kernel-Community-Supported-Ports （`GCC/RP2350_ARM_NTZ/{README.md,CMakeLists.txt,library.cmake,FreeRTOS_Kernel_import.cmake,non_secure/port.c,portasm.c,portmacro.h,portmacrocommon.h,rp2040_config.h,freertos_sdk_config.h}`、`GCC/RP2350_RISC-V/{README.md,port.c}`）；舊位置 https://github.com/raspberrypi/FreeRTOS-Kernel （`portable/ThirdParty/GCC/RP2350_*`）
> - pico-examples https://github.com/raspberrypi/pico-examples （`freertos/CMakeLists.txt`、`freertos/FreeRTOS_Kernel_import.cmake`、`freertos/FreeRTOSConfig_examples_common.h`、`freertos/hello_freertos/{CMakeLists.txt,hello_freertos.c}`）
> - pico-sdk 2.3.1 原始碼（`hardware_sync_spin_lock/.../spin_lock.h` 的 `PICO_SPINLOCK_ID_OS1/OS2`、`pico_multicore/.../multicore.h`、`pico_flash/.../flash.h`）
> - FreeRTOS 官方網站：https://www.freertos.org/RTOS-task-notifications.html （task notification 效能敘述）、AWS FreeRTOS User Guide「Symmetric multiprocessing (SMP) support」https://docs.aws.amazon.com/freertos/latest/userguide/smp-support.html
> 最後更新：2026-11
>
> 給模型的說明：本檔 API 簽名與 config 名稱都對照過上列原始碼。**若考場提供的 FreeRTOSConfig.h、kernel 版本或題目文件與本檔衝突，以考場為準**。標 ⚠️未驗證 的是推論或沒找到一手來源的內容。FreeRTOS 的 config 大多是「沒定義就用預設值」，判斷行為時一定要先讀考場的 `FreeRTOSConfig.h`。

---

## 0. 一頁總結（先看這裡）

1. **優先權：數字越大越優先**（`tskIDLE_PRIORITY` = 0 最低，最高 `configMAX_PRIORITIES - 1`）。這跟 Cortex-M 的 **IRQ 優先權相反**（IRQ 是數字越小越優先）。
2. **stack 大小單位是 word（`StackType_t` = `uint32_t` = 4 bytes）**，不是 byte。`xTaskCreate(..., 512, ...)` = 2 KB。有 `printf` 的 task 至少給 512 words（pico-examples 的 `configMINIMAL_STACK_SIZE` 就是 512）。
3. task 不要忙等。等資料用 `xQueueReceive(q, &x, portMAX_DELAY)`、等事件用 `ulTaskNotifyTake(pdTRUE, portMAX_DELAY)`、等時間用 `vTaskDelay` / `xTaskDelayUntil`。**被阻塞的 task 不吃 CPU**。
4. **週期性迴圈用 `xTaskDelayUntil(&last, period)`**，不要用 `vTaskDelay(period)`（後者會累積漂移）。
5. **ISR 裡只能呼叫結尾是 `FromISR` 的 API**，並用 `BaseType_t woken = pdFALSE; ...FromISR(..., &woken); portYIELD_FROM_ISR(woken);` 模式。mutex 不能在 ISR 用。
6. RP2350 Arm port：`configMAX_SYSCALL_INTERRUPT_PRIORITY = 16`（0x10）。**呼叫 FreeRTOS API 的 IRQ 優先權數值必須 ≥ 0x10**；pico-sdk 預設 `PICO_DEFAULT_IRQ_PRIORITY = 0x80`，沒問題；設成 `PICO_HIGHEST_IRQ_PRIORITY`（0x00）的 IRQ 不可呼叫任何 FreeRTOS API。
7. **SMP（`configNUMBER_OF_CORES = 2`）**：`vTaskStartScheduler()` 必須在 core 0 呼叫，它會自己 `multicore_reset_core1()` + `multicore_launch_core1()`。**不要再自己 launch core1**。
8. SMP 下「高優先權 task 在跑，低優先權就不會跑」這個單核假設**不成立**（`configRUN_MULTIPLE_PRIORITIES = 1` 時），而且兩核上的 ISR 和 task 可能同時執行。共享資料一定要保護（mutex / critical section / queue）。
9. `taskENTER_CRITICAL()` 在 SMP 下會**關本核中斷（BASEPRI）＋取得兩把跨核 spinlock**，等於全系統 kernel 鎖。只放幾行讀寫，越短越好。
10. 最快的 task 間訊號是 **task notification**（官方說解除阻塞比 binary semaphore 快 45%、更省 RAM），但只能有一個接收者。
11. 必開除錯：`configASSERT`、`configCHECK_FOR_STACK_OVERFLOW = 2`、`configUSE_MALLOC_FAILED_HOOK = 1`；檢查 `xTaskCreate` 回傳值是否 `pdPASS`、`xQueueCreate` 是否回傳 NULL。
12. 在 task 裡可以用 pico-sdk 的 `sleep_ms()`（`configSUPPORT_PICO_TIME_INTEROP = 1` 時會變成 FreeRTOS 層級的阻塞），但 `busy_wait_ms()` 會真的佔住 CPU。

---

## 1. 怎麼判斷考場在用 FreeRTOS、用哪個 port

| 看到什麼 | 代表 |
|---|---|
| `#include "FreeRTOS.h"`、`"task.h"`、`"queue.h"`、`"semphr.h"` | FreeRTOS 應用程式 |
| 專案目錄有 `FreeRTOSConfig.h` | kernel 設定，**第一個要讀的檔案** |
| CMake 有 `include(FreeRTOS_Kernel_import.cmake)`、`FREERTOS_KERNEL_PATH` | pico-sdk + FreeRTOS 整合 |
| `target_link_libraries(... FreeRTOS-Kernel-Heap4 ...)` | 使用 heap_4 動態配置 |
| `FreeRTOS-Kernel-Static` | 只用靜態配置（`xTaskCreateStatic`） |
| `configNUMBER_OF_CORES` 為 2（或沒定義但 pico-examples 共用設定預設 2） | SMP，兩核都跑 FreeRTOS |
| `configNUMBER_OF_CORES=1` + `multicore_launch_core1(vLaunch)` | FreeRTOS 只跑在 core 1（pico-examples 的寫法），core 0 另有用途 |
| `PICO_PLATFORM=rp2350-riscv` | 用 `RP2350_RISC-V` port（Hazard3） |
| `PICO_PLATFORM=rp2350`（或 `rp2350-arm-s`）/ 預設 | 用 `RP2350_ARM_NTZ` port（Cortex-M33，Non-TrustZone） |

### 1.1 命名慣例（讀 API 文件用）

| 前綴 | 意義 | 例 |
|---|---|---|
| `x` | 回傳 `BaseType_t` 或 handle 等非標準型別 | `xQueueSend`、`xTaskCreate` |
| `v` | 回傳 `void` | `vTaskDelay` |
| `ul` / `uc` / `us` | 回傳 `uint32_t` / `uint8_t` / `uint16_t` | `ulTaskNotifyTake` |
| `ux` | 回傳 `UBaseType_t` | `uxTaskGetStackHighWaterMark` |
| `pv` / `pc` | `void *` / `char *` | `pvPortMalloc` |
| `pd` | 通用常數 | `pdTRUE`=1、`pdFALSE`=0、`pdPASS`=`pdTRUE`、`pdFAIL`=`pdFALSE` |
| `port` | port 層巨集 | `portMAX_DELAY`、`portYIELD_FROM_ISR` |
| `config` / `INCLUDE_` | `FreeRTOSConfig.h` 的設定 / 是否編入某 API | `configTICK_RATE_HZ`、`INCLUDE_vTaskSuspend` |

型別：`TickType_t`（RP2350 port 為 32 位元，`portMAX_DELAY = 0xFFFFFFFF`）、`BaseType_t`（32 位元有號）、`UBaseType_t`、`TaskHandle_t`、`QueueHandle_t`、`SemaphoreHandle_t`、`EventGroupHandle_t`、`TimerHandle_t`、`StreamBufferHandle_t`、`MessageBufferHandle_t`。

---

## 2. 核心概念

### 2.1 Task 與狀態

task 是一個永不返回的函式：`void task_fn(void *pvParameters) { for (;;) { ... } }`。**不能 return**；要結束就呼叫 `vTaskDelete(NULL)`（刪除自己，記憶體由 idle task 回收）。

| 狀態（`eTaskState`） | 意義 | 怎麼進入 |
|---|---|---|
| `eRunning` | 正在某顆核上執行（SMP 下最多同時 2 個） | 被 scheduler 選中 |
| `eReady` | 可以跑，等 CPU | 被喚醒、時間到、被搶占 |
| `eBlocked` | 等事件（queue / semaphore / notification / delay），**有逾時** | 呼叫阻塞 API |
| `eSuspended` | 不參與排程，直到 `vTaskResume`。註：用 `portMAX_DELAY` 無限期阻塞的 task 內部雖放在 suspended list，V11 的 `eTaskGetState` 仍回報 `eBlocked`（在等 queue/semaphore/notification 時） | `vTaskSuspend` |
| `eDeleted` | 已刪除但 TCB 還沒被 idle task 釋放 | `vTaskDelete` |

`portMAX_DELAY` 當逾時值：若 `INCLUDE_vTaskSuspend == 1`，代表**無限期**等待；否則就只是最大 tick 數。

### 2.2 排程

| 概念 | 說明 | 相關 config |
|---|---|---|
| 固定優先權搶占 | Ready 中**優先權最高**的 task 執行；更高優先權 task 變 Ready 時立刻搶占 | `configUSE_PREEMPTION`（1 = 搶占；0 = 合作式，只有 task 主動 yield/阻塞才切換） |
| Time slicing | 同優先權的 Ready task 每個 tick 輪流 | `configUSE_TIME_SLICING`（沒定義時預設 1） |
| Tick | 週期中斷，推進時間、處理逾時、做 time slicing。Arm port 用 **SysTick**，SMP 時由 `configTICK_CORE`（預設 0）那顆核處理 | `configTICK_RATE_HZ`（pico-examples 用 1000 → 1 tick = 1 ms） |
| Idle task | scheduler 啟動時自動建立，優先權 0；回收被刪除 task 的記憶體；可掛 idle hook。SMP 建立 `configNUMBER_OF_CORES` 個：`IDLE0` 是一般 idle（做回收、跑 idle hook），`IDLE1` 是 passive idle；idle task **沒有綁核**，`IDLE0` 不一定在 core 0 跑 | `configUSE_IDLE_HOOK`、`configIDLE_SHOULD_YIELD`（預設 1：有同為優先權 0 的使用者 task 時 idle 會讓出） |
| Timer service task | 執行軟體 timer callback 的 daemon task，名稱 `Tmr Svc` | `configUSE_TIMERS`、`configTIMER_TASK_PRIORITY`、`configTIMER_QUEUE_LENGTH`、`configTIMER_TASK_STACK_DEPTH` |

時間換算：`pdMS_TO_TICKS(ms)` = `(ms * configTICK_RATE_HZ) / 1000`（**整數除法無條件捨去**），`portTICK_PERIOD_MS` = `1000 / configTICK_RATE_HZ`。若 tick rate = 100 Hz，`pdMS_TO_TICKS(5)` = 0。

### 2.3 SMP 與單核的差異（重要）

| 項目 | 說明 |
|---|---|
| `configNUMBER_OF_CORES` | 核心數；RP2350 SMP 設 2。舊名 `configNUM_CORES`（pico-examples 兩個都定義） |
| `configRUN_MULTIPLE_PRIORITIES` | **0**（FreeRTOS 預設）：只有**相同優先權**的 task 才會同時在不同核執行，維持「高優先權能跑時低優先權不跑」。**1**（pico-examples 設定）：不同優先權的 task 可以同時在兩核執行 |
| `configUSE_CORE_AFFINITY` | 1 才能用 `xTaskCreateAffinitySet`、`vTaskCoreAffinitySet/Get` 把 task 綁到特定核。affinity 是 bitmask：bit 0 = core 0、bit 1 = core 1；`tskNO_AFFINITY` = 任一核 |
| `configTASK_DEFAULT_CORE_AFFINITY` | 沒指定 affinity 時的預設（預設 `tskNO_AFFINITY`） |
| `configUSE_TASK_PREEMPTION_DISABLE` | 1 才能用 `vTaskPreemptionDisable/Enable` 讓個別 task 不被搶占 |
| `configUSE_PASSIVE_IDLE_HOOK` | passive idle task（非 core 0）的 hook |
| `configTICK_CORE` | 處理 tick 的核（RP2350 port 預設 0） |

官方（AWS FreeRTOS User Guide）點名的兩個單核假設，在 SMP 下會失效：
1. 「高優先權 task 正在跑時，低優先權 task 不會跑」：多核時兩者可同時跑。**用優先權當互斥手段的程式會出錯**。
2. 「ISR 不會和其他 ISR 或 task 同時執行」：多核時會同時執行。task 與 ISR 共用的資料要有適當的互斥。

### 2.4 記憶體：heap 方案

FreeRTOS 動態建立的物件（task 的 TCB 與 stack、queue、semaphore…）都從 `pvPortMalloc()` 配置，而不是從 C `malloc()`（heap_3 除外）。CMake link 哪一個 `FreeRTOS-Kernel-HeapN`，就用哪一個方案。

| 方案 | 可 free | 合併相鄰空閒塊 | 記憶體來源 | 適用 |
|---|---|---|---|---|
| heap_1 | 否 | — | `configTOTAL_HEAP_SIZE` 靜態陣列 | 只在啟動時建立物件、永不刪除 |
| heap_2 | 是 | **否**（會碎片化） | 同上 | 舊方案，一般改用 heap_4 |
| heap_3 | 是 | 由 C library 決定 | 包裝 C `malloc/free`（配置期間暫停 scheduler）；**不使用** `configTOTAL_HEAP_SIZE` | 想共用 newlib heap |
| **heap_4** | 是 | **是** | `configTOTAL_HEAP_SIZE` 靜態陣列（放在 .bss） | **最常用**（pico-examples 用這個） |
| heap_5 | 是 | 是 | 多個不連續區域，使用前必須先呼叫 `vPortDefineHeapRegions()` | 多塊 RAM |

- 查詢（heap_4/5）：`size_t xPortGetFreeHeapSize(void)`、`size_t xPortGetMinimumEverFreeHeapSize(void)`（歷史最低值，判斷 heap 夠不夠最好用這個）。
- pico-examples 設 `configTOTAL_HEAP_SIZE = 128*1024`。RP2350 有 520 KB SRAM，但 heap_4 的陣列是靜態的，會直接吃掉 .bss；要留空間給全域陣列與 C heap。
- `configSUPPORT_STATIC_ALLOCATION = 1` 時可以用 `xTaskCreateStatic` 等 `...Static` API 自己提供記憶體。link `FreeRTOS-Kernel-Static` 時 port 會設 `configKERNEL_PROVIDED_STATIC_MEMORY=1`，由 kernel 提供 idle/timer task 的記憶體。

### 2.5 Stack

- 單位：**words**（`StackType_t` = `uint32_t`）。`configSTACK_DEPTH_TYPE` 在 pico-examples 設為 `uint32_t`。
- 每個 task 的 stack 都從 FreeRTOS heap 配置（動態建立時），**與 pico-sdk 的 `PICO_STACK_SIZE` / `PICO_CORE1_STACK_SIZE` 無關**。後兩者在 Arm port 上是中斷用的 main stack（MSP）⚠️未驗證：RP2350 port 啟動 scheduler 後 MSP 的確切用法未逐行查證。
- 局部大陣列、深遞迴、`printf`（格式化需要不少 stack）都很吃 stack。大陣列改 `static` 或全域。
- 量測：`uxTaskGetStackHighWaterMark(handle)` 回傳**歷史最少剩餘量（words）**，越接近 0 越危險（需要 `INCLUDE_uxTaskGetStackHighWaterMark = 1`）。

---

## 3. 與 pico-sdk 整合

### 3.1 kernel 原始碼在哪裡

- **上游 FreeRTOS-Kernel 主 repo 本身沒有 RP2350 port**：`portable/ThirdParty/GCC/` 只有 `RP2040`。RP2350 的兩個 port 在 git submodule `portable/ThirdParty/Community-Supported-Ports`（repo `FreeRTOS-Kernel-Community-Supported-Ports`）的 `GCC/RP2350_ARM_NTZ` 與 `GCC/RP2350_RISC-V`。clone 時需要 `git submodule update --init portable/ThirdParty/Community-Supported-Ports`（考場若已附好 kernel 就不用管）。
- Raspberry Pi 的 fork `raspberrypi/FreeRTOS-Kernel` 則放在 `portable/ThirdParty/GCC/RP2350_ARM_NTZ`、`RP2350_RISC-V`（舊位置）。
- `FreeRTOS_Kernel_import.cmake`（pico-examples 附的版本）**兩個位置都會找**：先找 `portable/ThirdParty/GCC/<port>`，再找 `portable/ThirdParty/Community-Supported-Ports/GCC/<port>`。依 `PICO_PLATFORM` 選 port：`rp2040` → `RP2040`；`rp2350-riscv` → `RP2350_RISC-V`；其他 → `RP2350_ARM_NTZ`。
- kernel 路徑尋找順序：`FREERTOS_KERNEL_PATH`（CMake 變數或環境變數）→ `PICO_SDK_PATH/../FreeRTOS-Kernel`（和 SDK 同層）→ 專案目錄下的 `FreeRTOS-Kernel` / `Source` / `FreeRTOS/Source`。都找不到會 `FATAL_ERROR "FreeRTOS location was not specified"`。

### 3.2 最小 CMakeLists.txt

```cmake
cmake_minimum_required(VERSION 3.13)
set(PICO_BOARD pico2)                       # 要編 RISC-V：set(PICO_PLATFORM rp2350-riscv)
include(pico_sdk_import.cmake)
project(rtos_demo C CXX ASM)
pico_sdk_init()

# 從 pico-examples/freertos/ 或 port 目錄複製 FreeRTOS_Kernel_import.cmake 到專案
# SDK >= 1.3.2 時可以放在 pico_sdk_init() 之後（pico-examples 就是這樣）
include(FreeRTOS_Kernel_import.cmake)       # 或 cmake -DFREERTOS_KERNEL_PATH=/path/FreeRTOS-Kernel

add_executable(rtos_demo main.c)
# FreeRTOSConfig.h 所在目錄必須在 include path（kernel 是 INTERFACE library，用你的 target 的 include path 編譯）
target_include_directories(rtos_demo PRIVATE ${CMAKE_CURRENT_LIST_DIR})
target_link_libraries(rtos_demo PRIVATE
    pico_stdlib
    FreeRTOS-Kernel-Heap4)                  # 已包含 FreeRTOS-Kernel → 已包含 pico_multicore
pico_add_extra_outputs(rtos_demo)
```

### 3.3 CMake target（`library.cmake`，RP2350_ARM_NTZ）

| target | 內容 |
|---|---|
| `FreeRTOS-Kernel-Core` | kernel 共用 C 檔：`tasks.c queue.c list.c timers.c event_groups.c stream_buffer.c croutine.c` + `include/`；設定 `PICO_CONFIG_RTOS_ADAPTER_HEADER` 指向 port 的 `freertos_sdk_config.h`（讓 pico_sync / pico_time 與 FreeRTOS 互通） |
| `FreeRTOS-Kernel` | port（`port.c`、`portasm.c`）＋ link `FreeRTOS-Kernel-Core pico_base_headers hardware_clocks hardware_exception pico_multicore`；定義 `LIB_FREERTOS_KERNEL=1`、`FREE_RTOS_KERNEL_SMP=1` |
| `FreeRTOS-Kernel-Heap1` … `FreeRTOS-Kernel-Heap5` | `FreeRTOS-Kernel` + 對應的 `portable/MemMang/heap_N.c` |
| `FreeRTOS-Kernel-Static` | `FreeRTOS-Kernel` + `configSUPPORT_STATIC_ALLOCATION=1`、`configKERNEL_PROVIDED_STATIC_MEMORY=1` |

一個 target 只 link 一個 heap 方案。只 link `FreeRTOS-Kernel` 而沒有 heap 也沒有 Static → `pvPortMalloc` undefined reference。

### 3.4 FreeRTOSConfig.h 範本（RP2350 SMP，改自 pico-examples）

```c
#ifndef FREERTOS_CONFIG_H
#define FREERTOS_CONFIG_H

/* 排程 */
#define configUSE_PREEMPTION                    1
#define configUSE_TICKLESS_IDLE                 0      /* RP2350 port README：tickless 未測試 */
#define configUSE_IDLE_HOOK                     0
#define configUSE_TICK_HOOK                     0
#define configTICK_RATE_HZ                      ( ( TickType_t ) 1000 )
#define configMAX_PRIORITIES                    32
#define configMINIMAL_STACK_SIZE                ( configSTACK_DEPTH_TYPE ) 512   /* words */
#define configUSE_16_BIT_TICKS                  0
#define configIDLE_SHOULD_YIELD                 1
#define configUSE_TIME_SLICING                  1
#define configMAX_TASK_NAME_LEN                 16

/* 同步物件 */
#define configUSE_MUTEXES                       1
#define configUSE_RECURSIVE_MUTEXES             1
#define configUSE_COUNTING_SEMAPHORES           1
#define configQUEUE_REGISTRY_SIZE               8
#define configUSE_QUEUE_SETS                    1
#define configUSE_TASK_NOTIFICATIONS            1
#define configTASK_NOTIFICATION_ARRAY_ENTRIES   1

/* 型別 */
#define configSTACK_DEPTH_TYPE                  uint32_t
#define configMESSAGE_BUFFER_LENGTH_TYPE        size_t

/* 記憶體 */
#ifndef configSUPPORT_STATIC_ALLOCATION
#define configSUPPORT_STATIC_ALLOCATION         0
#endif
#ifndef configSUPPORT_DYNAMIC_ALLOCATION
#define configSUPPORT_DYNAMIC_ALLOCATION        1
#endif
#define configTOTAL_HEAP_SIZE                   ( 128 * 1024 )
#define configAPPLICATION_ALLOCATED_HEAP        0

/* 除錯 hook（開了就要自己實作對應函式，見 §4.11） */
#define configCHECK_FOR_STACK_OVERFLOW          2
#define configUSE_MALLOC_FAILED_HOOK            1

/* 統計（要量 CPU 使用率時才開，見 §4.11） */
#define configUSE_TRACE_FACILITY                1
#define configGENERATE_RUN_TIME_STATS           0
#define configUSE_STATS_FORMATTING_FUNCTIONS    0

/* 軟體 timer */
#define configUSE_TIMERS                        1
#define configTIMER_TASK_PRIORITY               ( configMAX_PRIORITIES - 1 )
#define configTIMER_QUEUE_LENGTH                10
#define configTIMER_TASK_STACK_DEPTH            1024

/* SMP（FREE_RTOS_KERNEL_SMP 由 RP2350/RP2040 port 的 CMake 定義） */
#if FREE_RTOS_KERNEL_SMP
#ifndef configNUMBER_OF_CORES
#define configNUMBER_OF_CORES                   2
#endif
#define configNUM_CORES                         configNUMBER_OF_CORES
#define configTICK_CORE                         0
#define configRUN_MULTIPLE_PRIORITIES           1
#if configNUMBER_OF_CORES > 1
#define configUSE_CORE_AFFINITY                 1
#endif
#define configUSE_PASSIVE_IDLE_HOOK             0
#endif

/* pico-sdk 互通（沒定義時 port 會在有 link pico_sync / pico_time 時自動設 1） */
#define configSUPPORT_PICO_SYNC_INTEROP         1
#define configSUPPORT_PICO_TIME_INTEROP         1

/* RP2350 Arm port 必要設定（port README） */
#if PICO_RP2350
#define configENABLE_MPU                        0
#define configENABLE_TRUSTZONE                  0
#define configRUN_FREERTOS_SECURE_ONLY          1
#define configENABLE_FPU                        1      /* 有用浮點就要開 */
#define configMAX_SYSCALL_INTERRUPT_PRIORITY    16     /* README：目前唯一測試過的值 */
#endif

#include <assert.h>
#define configASSERT( x )                       assert( x )   /* Release(-DNDEBUG) 會失效，見 §9 */

/* 要編入的 API */
#define INCLUDE_vTaskPrioritySet                1
#define INCLUDE_uxTaskPriorityGet               1
#define INCLUDE_vTaskDelete                     1
#define INCLUDE_vTaskSuspend                    1
#define INCLUDE_xTaskDelayUntil                 1      /* 舊名 INCLUDE_vTaskDelayUntil，兩個不能同時定義 */
#define INCLUDE_vTaskDelay                      1
#define INCLUDE_xTaskGetSchedulerState          1
#define INCLUDE_xTaskGetCurrentTaskHandle       1
#define INCLUDE_uxTaskGetStackHighWaterMark     1
#define INCLUDE_xTaskGetIdleTaskHandle          1
#define INCLUDE_eTaskGetState                   1
#define INCLUDE_xTimerPendFunctionCall          1      /* xEventGroupSetBitsFromISR 需要 */
#define INCLUDE_xTaskAbortDelay                 1
#define INCLUDE_xTaskGetHandle                  1
#define INCLUDE_xTaskResumeFromISR              1
#define INCLUDE_xQueueGetMutexHolder            1

#endif
```

pico-examples 原版與上面的差別：原版 `configCHECK_FOR_STACK_OVERFLOW 0`、`configUSE_MALLOC_FAILED_HOOK 0`、`INCLUDE_vTaskDelayUntil 1`，另外有 `configENABLE_BACKWARD_COMPATIBILITY 1`、`configNUM_THREAD_LOCAL_STORAGE_POINTERS 5`、`configUSE_DAEMON_TASK_STARTUP_HOOK 0`、`configUSE_CO_ROUTINES 0` 等。

### 3.5 config 重點速查

| config | 建議 / 說明 |
|---|---|
| `configNUMBER_OF_CORES` | 2 = SMP 雙核；1 = 單核（可用 `multicore_launch_core1(vLaunch)` 讓 FreeRTOS 跑在 core 1） |
| `configUSE_CORE_AFFINITY` | 1（才能綁核；`pico_flash` 的 `flash_safe_execute` 在 FreeRTOS SMP 下也要求它，否則 `#error`） |
| `configRUN_MULTIPLE_PRIORITIES` | pico 用 1；設 0 時兩核只會同時跑同優先權的 task |
| `configSUPPORT_PICO_SYNC_INTEROP` | 1：SDK 的 `mutex_t`、`semaphore_t`、`queue_t` 等在 FreeRTOS task 裡阻塞時會以 FreeRTOS 方式阻塞（讓出 CPU）；可在 FreeRTOS task 與非 FreeRTOS 核 / IRQ 間共用 |
| `configSUPPORT_PICO_TIME_INTEROP` | 1：`sleep_ms/sleep_us/sleep_until` 在 task 中會真正在 FreeRTOS 層阻塞 |
| `configTICK_RATE_HZ` | 1000（1 ms 解析度）。調低 → tick 中斷開銷少，但延遲解析度變粗 |
| `configTOTAL_HEAP_SIZE` | heap_1/2/4 的總大小（bytes）。用 `xPortGetMinimumEverFreeHeapSize()` 校正 |
| `configCHECK_FOR_STACK_OVERFLOW` | 0 不檢查；1 context switch 時檢查 SP 是否越界（快、不完整）；2 再檢查 stack 尾端填充 pattern 是否被改（較慢，能抓到大多數） |
| `configUSE_TRACE_FACILITY` | 1：`uxTaskGetSystemState`、`vTaskListTasks` 需要 |
| `configGENERATE_RUN_TIME_STATS` | 1：每 task CPU 時間統計；**必須**另外定義 `portCONFIGURE_TIMER_FOR_RUN_TIME_STATS()` 與 `portGET_RUN_TIME_COUNTER_VALUE()`，RP2350 port 沒有提供，否則 `#error` |
| `configMAX_SYSCALL_INTERRUPT_PRIORITY` | RP2350 Arm：16（0x10）。RISC-V port 不使用 |
| `configENABLE_FPU` | 1：context switch 保存 FPU 暫存器；task 用 float 時要開 |

### 3.6 port 在底層做了什麼（RP2350_ARM_NTZ，`port.c`）

- `xPortStartScheduler()`（SMP）：
  1. `spin_lock_claim(configSMP_SPINLOCK_0)`、`spin_lock_claim(configSMP_SPINLOCK_1)`：預設為 `PICO_SPINLOCK_ID_OS1/OS2`（RP2350 用硬體 spinlock 時為 18/19，用軟體 spinlock〔RP2350 預設〕時為 14/15；見 `multicore-sync.md` B4.2）。**這兩把是 kernel 專用，應用程式不要碰**。
  2. `multicore_doorbell_claim_unused(0b11, true)`：claim 一個 **doorbell** 做跨核 yield（RP2040 port 則是用 SIO FIFO 中斷）。doorbell IRQ 優先權設為最低。
  3. `configASSERT(get_core_num() == 0)`：**必須在 core 0 啟動**。
  4. `multicore_reset_core1(); multicore_launch_core1(...)`：由 FreeRTOS 自己啟動 core 1（launch 握手會用到 FIFO）。
- SysTick reload 值在啟動時依 `clock_get_hz(clk_sys) / configTICK_RATE_HZ` 計算。**要改系統時脈請在 `vTaskStartScheduler()` 之前改**，之後改 tick 會不準 ⚠️未驗證（從程式碼推論，未實測）。
- PendSV 與 SysTick 優先權設為最低（`portMIN_INTERRUPT_PRIORITY` = 255）。
- 關中斷（`portDISABLE_INTERRUPTS`）是寫 **BASEPRI = configMAX_SYSCALL_INTERRUPT_PRIORITY**，不是 PRIMASK：優先權 0x00 的 IRQ 在 critical section 中仍可執行。
- 在 pico-sdk 的 RTOS adapter header 中把 `PICO_USE_MALLOC_MUTEX` 設為 1（讓 C `malloc` thread-safe），並在 SYNC interop 時把 `PICO_TIME_SLEEP_OVERHEAD_ADJUST_US` 設為 150。

### 3.7 SMP 下 pico_multicore / pico_sync / pico_time 的變化

| 裸機習慣 | FreeRTOS SMP（2 核）下 |
|---|---|
| `multicore_launch_core1(core1_main)` | **不要用**：core 1 由 scheduler 啟動。要讓工作跑在 core 1 → 建 task 並設 affinity `1u << 1` |
| `multicore_fifo_push/pop_blocking` 自己傳資料 | 不建議（SDK 的 `multicore.h` 也建議不要自己用 FIFO，因為 RTOS / launch 會用）；改用 FreeRTOS queue / notification |
| `spin_lock_blocking` + 自己的 spinlock | 仍可用於極短的跨核保護，但不能在持鎖時呼叫任何 FreeRTOS API；task 間通常改用 `taskENTER_CRITICAL` 或 mutex |
| `critical_section_t`、`mutex_t`、`semaphore_t`、`queue_t`（pico_sync / pico_util） | 開 `configSUPPORT_PICO_SYNC_INTEROP` 後在 task 裡可用，阻塞時會讓出 CPU；適合「FreeRTOS task ↔ 非 FreeRTOS 核 / IRQ」的情境 |
| `sleep_ms(10)` | 開 TIME_INTEROP 後在 task 中 = FreeRTOS 阻塞，OK；但慣例上仍建議 `vTaskDelay(pdMS_TO_TICKS(10))` |
| `busy_wait_ms(10)` | 真的佔住 CPU 10 ms（pico-examples 用它示範「忙等會餓死低優先權 task」） |
| `add_repeating_timer_ms` | 仍可用（callback 在 IRQ context）；在 callback 中只能呼叫 `FromISR` API |
| `multicore_lockout_*` / flash 寫入 | 用 `flash_safe_execute()`；FreeRTOS SMP 下 pico_flash 會用 FreeRTOS 機制讓另一核停下來（`PICO_FLASH_SAFE_EXECUTE_SUPPORT_FREERTOS_SMP`，預設 1） |
| 單核 FreeRTOS（`configNUMBER_OF_CORES=1`）+ 另一核裸機 | 另一核可以自由用 pico_multicore；兩邊用 pico_sync 物件溝通（interop） |

### 3.8 RISC-V port（`RP2350_RISC-V`）的差異

- 同樣是 SMP、同樣的 CMake target 名稱與 import 檔，用 doorbell 做跨核通知。
- README 的 Known Limitations：**Hazard3 的 IRQ 搶占（巢狀中斷）目前不支援**；mtvec 與 IRQ handler 會裝在兩核上。
- `configMAX_SYSCALL_INTERRUPT_PRIORITY` 這類 Arm NVIC 設定不適用；API 用法相同。

---

## 4. API 參考（簽名對照 kernel 標頭）

### 4.1 建立與控制 task

```c
#include "FreeRTOS.h"
#include "task.h"

BaseType_t xTaskCreate(TaskFunction_t pxTaskCode, const char * const pcName,
                       const configSTACK_DEPTH_TYPE uxStackDepth,   /* words */
                       void * const pvParameters, UBaseType_t uxPriority,
                       TaskHandle_t * const pxCreatedTask);          /* 可為 NULL */
/* 成功 pdPASS；記憶體不足回傳 errCOULD_NOT_ALLOCATE_REQUIRED_MEMORY（-1）。檢查時寫 != pdPASS */

/* SMP + configUSE_CORE_AFFINITY == 1 */
BaseType_t xTaskCreateAffinitySet(TaskFunction_t pxTaskCode, const char * const pcName,
                                  const configSTACK_DEPTH_TYPE uxStackDepth,
                                  void * const pvParameters, UBaseType_t uxPriority,
                                  UBaseType_t uxCoreAffinityMask,     /* bit n = core n */
                                  TaskHandle_t * const pxCreatedTask);
void        vTaskCoreAffinitySet(const TaskHandle_t xTask, UBaseType_t uxCoreAffinityMask);
UBaseType_t vTaskCoreAffinityGet(ConstTaskHandle_t xTask);

TaskHandle_t xTaskCreateStatic(TaskFunction_t pxTaskCode, const char * const pcName,
                               const configSTACK_DEPTH_TYPE uxStackDepth, void * const pvParameters,
                               UBaseType_t uxPriority, StackType_t * const puxStackBuffer,
                               StaticTask_t * const pxTaskBuffer);   /* 需 configSUPPORT_STATIC_ALLOCATION */

void vTaskStartScheduler(void);          /* 正常不會返回；SMP 必須在 core 0 呼叫 */
void vTaskDelete(TaskHandle_t xTaskToDelete);      /* NULL = 自己 */
void vTaskSuspend(TaskHandle_t xTaskToSuspend);    /* NULL = 自己；需 INCLUDE_vTaskSuspend */
void vTaskResume(TaskHandle_t xTaskToResume);
BaseType_t xTaskResumeFromISR(TaskHandle_t xTaskToResume);  /* 回傳是否需要 yield */
void vTaskPrioritySet(TaskHandle_t xTask, UBaseType_t uxNewPriority);
UBaseType_t uxTaskPriorityGet(const TaskHandle_t xTask);
TaskHandle_t xTaskGetCurrentTaskHandle(void);
taskYIELD();                             /* 讓給同優先權的其他 Ready task */
portGET_CORE_ID();                       /* RP2350 port = get_core_num() */
```

- `vTaskSuspend/Resume` 不會累計次數（suspend 兩次，resume 一次就恢復），也不適合當同步手段（resume 若在 suspend 之前發生就遺失）。同步改用 notification。
- `xTaskResumeFromISR` 官方也不建議用來同步 ISR 與 task（同樣有遺失問題）⚠️未驗證（官方文件原文未取得，依 API 語意推論）。

### 4.2 時間與延遲

```c
void       vTaskDelay(const TickType_t xTicksToDelay);       /* 相對延遲：從現在起 */
BaseType_t xTaskDelayUntil(TickType_t * const pxPreviousWakeTime,
                           const TickType_t xTimeIncrement); /* 絕對延遲：固定週期 */
/* 回傳 pdTRUE = 有延遲；pdFALSE = 下次喚醒時間已經過了（deadline miss），不延遲直接返回 */
#define vTaskDelayUntil(pxPrev, xInc)   /* 舊版，無回傳值 */
TickType_t xTaskGetTickCount(void);
TickType_t xTaskGetTickCountFromISR(void);
pdMS_TO_TICKS(ms)                        /* 捨去；1000 Hz 時 1 tick = 1 ms */
```

- 較新的 kernel（V11.3.x 有）另有 `TickType_t xTaskPeriodicDelay(TickType_t * const pxPreviousWakeTime, const TickType_t xTimeIncrement)`，回傳補上的週期數（0、1 或 >1 表示有漏掉週期）。考場版本不一定有，用之前先 grep `task.h`。
- `vTaskDelay(n)`：第一個 tick 不完整，實際阻塞時間大約是 (n−1)～n 個 tick 週期 ⚠️未驗證（依 tick 機制推論，沒找到官方原句）。需要 µs 級精度不要靠 tick，改用硬體 timer / alarm / PIO。
- `vTaskDelay(0)` 不會阻塞（只等於有機會 yield）。

```c
/* 正確的週期迴圈：不會漂移 */
void periodic_task(void *p) {
    const TickType_t period = pdMS_TO_TICKS(10);
    TickType_t last = xTaskGetTickCount();        /* 必須先初始化 */
    for (;;) {
        if (xTaskDelayUntil(&last, period) == pdFALSE) {
            /* 上一輪工作超過 10 ms：deadline miss，記錄下來 */
        }
        do_work();
    }
}
/* 錯誤：每輪週期 = 10 ms + do_work 時間 + 搶占時間，誤差會累積 */
void drifting_task(void *p) { for (;;) { do_work(); vTaskDelay(pdMS_TO_TICKS(10)); } }
```

### 4.3 Queue（以複製方式傳資料）

```c
#include "queue.h"
QueueHandle_t xQueueCreate(UBaseType_t uxQueueLength, UBaseType_t uxItemSize);  /* 失敗回 NULL */
BaseType_t xQueueSend(QueueHandle_t q, const void *pvItemToQueue, TickType_t xTicksToWait); /* = SendToBack */
BaseType_t xQueueSendToFront(QueueHandle_t q, const void *pvItemToQueue, TickType_t xTicksToWait);
BaseType_t xQueueReceive(QueueHandle_t q, void * const pvBuffer, TickType_t xTicksToWait);
BaseType_t xQueuePeek(QueueHandle_t q, void * const pvBuffer, TickType_t xTicksToWait);   /* 不移除 */
BaseType_t xQueueOverwrite(QueueHandle_t q, const void *pvItemToQueue); /* 只能用在長度 1 的 queue（mailbox） */
UBaseType_t uxQueueMessagesWaiting(const QueueHandle_t q);
/* ISR 版本：不可阻塞，多一個 pxHigherPriorityTaskWoken */
BaseType_t xQueueSendFromISR(QueueHandle_t q, const void *pvItemToQueue, BaseType_t *pxHigherPriorityTaskWoken);
BaseType_t xQueueReceiveFromISR(QueueHandle_t q, void * const pvBuffer, BaseType_t *pxHigherPriorityTaskWoken);
BaseType_t xQueueOverwriteFromISR(QueueHandle_t q, const void *pvItemToQueue, BaseType_t *pxHigherPriorityTaskWoken);
```

- 回傳 `pdPASS`；滿了（Send）回 `errQUEUE_FULL`，空的（Receive）回 `errQUEUE_EMPTY`（兩者值都是 0 = `pdFALSE`）。
- `xTicksToWait`：0 = 不等、立即返回；`portMAX_DELAY` = 永遠等。
- **資料是複製進去的**（`uxItemSize` bytes）。大資料改傳指標（`sizeof(buf_t *)`），但要約定好所有權（誰負責 free / 誰可以再寫）。
- queue 是多生產者、多消費者安全的，也跨核安全。

### 4.4 Semaphore 與 Mutex

```c
#include "semphr.h"
SemaphoreHandle_t xSemaphoreCreateBinary(void);                 /* 建立時是「空」的，要先 Give 才 Take 得到 */
SemaphoreHandle_t xSemaphoreCreateCounting(UBaseType_t uxMaxCount, UBaseType_t uxInitialCount);
SemaphoreHandle_t xSemaphoreCreateMutex(void);                  /* 有 priority inheritance */
SemaphoreHandle_t xSemaphoreCreateRecursiveMutex(void);         /* 同一 task 可重複 Take */
BaseType_t xSemaphoreTake(SemaphoreHandle_t s, TickType_t xBlockTime);
BaseType_t xSemaphoreGive(SemaphoreHandle_t s);
BaseType_t xSemaphoreTakeRecursive(SemaphoreHandle_t m, TickType_t xBlockTime);
BaseType_t xSemaphoreGiveRecursive(SemaphoreHandle_t m);       /* Take 幾次就要 Give 幾次 */
BaseType_t xSemaphoreGiveFromISR(SemaphoreHandle_t s, BaseType_t *pxHigherPriorityTaskWoken);
BaseType_t xSemaphoreTakeFromISR(SemaphoreHandle_t s, BaseType_t *pxHigherPriorityTaskWoken);
void vSemaphoreDelete(SemaphoreHandle_t s);
```

| 物件 | 用途 | 可在 ISR give | priority inheritance | 需要的 config |
|---|---|---|---|---|
| binary semaphore | 事件同步（ISR → task） | 是 | 否 | — |
| counting semaphore | 計數事件 / 資源池 | 是 | 否 | `configUSE_COUNTING_SEMAPHORES` |
| mutex | 互斥（保護共享資源）；**誰 Take 誰 Give** | **否**（mutex 不能在 ISR 使用） | 是 | `configUSE_MUTEXES` |
| recursive mutex | 會重入的函式 | 否 | 是 | `configUSE_RECURSIVE_MUTEXES` |

- **Priority inversion**：低優先權 L 持有鎖，高優先權 H 等鎖，中優先權 M 搶占 L → H 被 M 間接卡住。FreeRTOS mutex 的 priority inheritance 會把 L 暫時提升到 H 的優先權，讓 L 盡快放鎖。binary semaphore 沒有這個機制，所以**互斥用 mutex，不要用 binary semaphore**。
- 事件同步則相反：用 binary semaphore 或（更快的）task notification，不要用 mutex。

```c
static SemaphoreHandle_t uart_mtx;      /* main 裡 uart_mtx = xSemaphoreCreateMutex(); */
void log_safe(const char *s) {
    if (xSemaphoreTake(uart_mtx, pdMS_TO_TICKS(50)) == pdTRUE) {
        puts(s);                         /* 臨界區只放必要的事 */
        xSemaphoreGive(uart_mtx);
    } /* else: 逾時，可能 deadlock 或持有者太久 */
}
```

### 4.5 Task notification（最快、最省 RAM 的 1 對 1 訊號）

每個 task 內建一個（或 `configTASK_NOTIFICATION_ARRAY_ENTRIES` 個）32 位元 notification value + 狀態。官方：用 notification 解除 task 阻塞比用 binary semaphore 快 45%，且更省 RAM（不需要另外的 queue 物件）。

```c
/* 當作 binary / counting semaphore */
BaseType_t xTaskNotifyGive(TaskHandle_t xTaskToNotify);                       /* 值 +1 */
void       vTaskNotifyGiveFromISR(TaskHandle_t xTaskToNotify, BaseType_t *pxHigherPriorityTaskWoken);
uint32_t   ulTaskNotifyTake(BaseType_t xClearCountOnExit, TickType_t xTicksToWait);
/* xClearCountOnExit = pdTRUE：返回前清 0（binary 語意，回傳累計次數）；pdFALSE：減 1（counting 語意） */

/* 一般形式：傳一個 32 位元值或設 bit */
BaseType_t xTaskNotify(TaskHandle_t xTaskToNotify, uint32_t ulValue, eNotifyAction eAction);
BaseType_t xTaskNotifyFromISR(TaskHandle_t xTaskToNotify, uint32_t ulValue, eNotifyAction eAction,
                              BaseType_t *pxHigherPriorityTaskWoken);
BaseType_t xTaskNotifyWait(uint32_t ulBitsToClearOnEntry, uint32_t ulBitsToClearOnExit,
                           uint32_t *pulNotificationValue, TickType_t xTicksToWait);
/* 另有 ...Indexed 版本（xTaskNotifyGiveIndexed、ulTaskNotifyTakeIndexed…）多一個 index 參數 */
```

| `eNotifyAction` | 效果 |
|---|---|
| `eNoAction` | 只喚醒，不改值 |
| `eSetBits` | `value \|= ulValue`（當輕量 event group） |
| `eIncrement` | `value++`（等同 Give） |
| `eSetValueWithOverwrite` | 直接覆寫（當長度 1 的 mailbox） |
| `eSetValueWithoutOverwrite` | 上一個值還沒被讀時不寫，回傳 `pdFAIL` |

限制：
- **只有一個接收者**（就是被通知的那個 task）；多個 task 要等同一事件 → 用 event group 或 semaphore。
- 沒有緩衝多筆資料（只有一個 32 位元值 / 計數）；要傳多筆資料 → queue / stream buffer。
- 發送端不能阻塞等待接收端。
- 需要知道接收 task 的 handle（建立時用 `&handle` 取得）。
- stream buffer / message buffer 內部預設使用 notification index 0（`tskDEFAULT_INDEX_TO_NOTIFY`）；自己用 index 0 同時又在該 task 上等 stream buffer 時要小心。

### 4.6 Event group（多個事件 bit、多個等待者）

```c
#include "event_groups.h"
EventGroupHandle_t xEventGroupCreate(void);
EventBits_t xEventGroupSetBits(EventGroupHandle_t g, const EventBits_t uxBitsToSet);
EventBits_t xEventGroupClearBits(EventGroupHandle_t g, const EventBits_t uxBitsToClear);
EventBits_t xEventGroupWaitBits(EventGroupHandle_t g, const EventBits_t uxBitsToWaitFor,
                                const BaseType_t xClearOnExit,     /* pdTRUE：返回時清掉等待的 bit */
                                const BaseType_t xWaitForAllBits,  /* pdTRUE = AND；pdFALSE = OR */
                                TickType_t xTicksToWait);          /* 回傳返回當下的 bits，自行判斷是否逾時 */
EventBits_t xEventGroupSync(EventGroupHandle_t g, const EventBits_t uxBitsToSet,
                            const EventBits_t uxBitsToWaitFor, TickType_t xTicksToWait);  /* barrier */
BaseType_t xEventGroupSetBitsFromISR(EventGroupHandle_t g, const EventBits_t uxBitsToSet,
                                     BaseType_t *pxHigherPriorityTaskWoken);
```

- 32 位元 tick 時可用 **24 個 bit（bit 0～23）**，高 8 bit 保留給 kernel。
- `xEventGroupSetBitsFromISR` 不是在 ISR 內直接設 bit，而是**丟給 timer service task 執行**，所以需要 `configUSE_TIMERS = 1` 與 `INCLUDE_xTimerPendFunctionCall = 1`，而且實際生效時間取決於 timer task 的優先權；回傳 `pdFAIL` 表示 timer command queue 滿了。
- 「等 N 個 worker 都完成」：每個 worker 設自己的 bit，主 task `xEventGroupWaitBits(g, ALL, pdTRUE, pdTRUE, portMAX_DELAY)`。

### 4.7 Stream buffer / Message buffer

```c
#include "stream_buffer.h"
#include "message_buffer.h"
StreamBufferHandle_t xStreamBufferCreate(size_t xBufferSizeBytes, size_t xTriggerLevelBytes);
size_t xStreamBufferSend(StreamBufferHandle_t sb, const void *pvTxData, size_t xDataLengthBytes, TickType_t xTicksToWait);
size_t xStreamBufferReceive(StreamBufferHandle_t sb, void *pvRxData, size_t xBufferLengthBytes, TickType_t xTicksToWait);
size_t xStreamBufferSendFromISR(StreamBufferHandle_t sb, const void *pvTxData, size_t xDataLengthBytes,
                                BaseType_t * const pxHigherPriorityTaskWoken);
MessageBufferHandle_t xMessageBufferCreate(size_t xBufferSizeBytes);
size_t xMessageBufferSend(MessageBufferHandle_t mb, const void *pvTxData, size_t xDataLengthBytes, TickType_t xTicksToWait);
size_t xMessageBufferReceive(MessageBufferHandle_t mb, void *pvRxData, size_t xBufferLengthBytes, TickType_t xTicksToWait);
```

- stream buffer：位元組流（像 UART RX）；接收端在累積到 `xTriggerLevelBytes` 時被喚醒。回傳值是實際傳送 / 收到的 byte 數。
- message buffer：保留訊息邊界的可變長度訊息；每則訊息另存一個長度欄位（`configMESSAGE_BUFFER_LENGTH_TYPE`，pico-examples 設 `size_t` = 4 bytes）。
- **假設只有一個寫入者和一個讀取者**（task 或 ISR）。多個寫入者 / 讀取者時，必須把 Send / Receive 包在 critical section 內，或改用 queue。
- 比 queue 輕（單一 reader/writer 的 ring buffer + notification）；適合 ISR → task 的大量位元組。

### 4.8 軟體 timer

```c
#include "timers.h"
typedef void (*TimerCallbackFunction_t)(TimerHandle_t xTimer);
TimerHandle_t xTimerCreate(const char * const pcTimerName, const TickType_t xTimerPeriodInTicks,
                           const BaseType_t xAutoReload,        /* pdTRUE 週期；pdFALSE 單次 */
                           void * const pvTimerID, TimerCallbackFunction_t pxCallbackFunction);
BaseType_t xTimerStart(TimerHandle_t t, TickType_t xTicksToWait);   /* 送命令到 timer queue 的等待時間 */
BaseType_t xTimerStop(TimerHandle_t t, TickType_t xTicksToWait);
BaseType_t xTimerReset(TimerHandle_t t, TickType_t xTicksToWait);
BaseType_t xTimerChangePeriod(TimerHandle_t t, TickType_t xNewPeriod, TickType_t xTicksToWait);
BaseType_t xTimerStartFromISR(TimerHandle_t t, BaseType_t *pxHigherPriorityTaskWoken);
void *pvTimerGetTimerID(const TimerHandle_t t);
BaseType_t xTimerPendFunctionCallFromISR(PendedFunction_t f, void *pv1, uint32_t ul2, BaseType_t *pxHigherPriorityTaskWoken);
```

- 所有 callback 都在 **timer service task（`Tmr Svc`）** 中依序執行，不在 ISR 中。
- **callback 不可阻塞**：不要呼叫 `vTaskDelay`，呼叫其他 API 時 `xTicksToWait` 用 0。callback 執行太久會延誤其他所有 timer。
- `xTimerStart` 等 API 只是把命令送進 timer command queue（長度 `configTIMER_QUEUE_LENGTH`），由 timer task 處理；scheduler 啟動前呼叫時不要給等待時間。
- timer 精度是 tick；`configTIMER_TASK_PRIORITY` 通常設最高（pico-examples：`configMAX_PRIORITIES - 1`）。
- SMP 下 timer task 預設沒有綁核（`configTIMER_SERVICE_TASK_CORE_AFFINITY` 預設 `tskNO_AFFINITY`）。

### 4.9 Critical section 與暫停 scheduler（SMP 行為）

```c
taskENTER_CRITICAL();                      /* task 中使用；可巢狀 */
/* ... 極短的共享資料讀寫，不可呼叫阻塞 API ... */
taskEXIT_CRITICAL();

UBaseType_t s = taskENTER_CRITICAL_FROM_ISR();   /* ISR 中使用 */
/* ... */
taskEXIT_CRITICAL_FROM_ISR(s);

vTaskSuspendAll();   /* 暫停 scheduler（不關中斷）；期間不可呼叫會阻塞的 API */
xTaskResumeAll();    /* 回傳 pdTRUE 表示恢復時已經做了 context switch */
```

SMP 版 `vTaskEnterCritical()`（`tasks.c`）的實際行為：
1. `portDISABLE_INTERRUPTS()`：RP2350 Arm 是把 BASEPRI 設成 `configMAX_SYSCALL_INTERRUPT_PRIORITY`，**只關本核**、只遮罩優先權數值 ≥ 0x10 的 IRQ。
2. 若 scheduler 已執行且巢狀計數為 0：取得 **task lock 與 ISR lock**（兩把 RP2350 spinlock：`configSMP_SPINLOCK_1`、`configSMP_SPINLOCK_0`）→ 另一核進入 critical section 或 kernel 內部時會在 spinlock 上自旋等待。
3. 在 ISR 中呼叫非 FromISR 版本會觸發 assert（若有定義 `configASSERT`）。

結論：
- `taskENTER_CRITICAL` 在 SMP 下**是跨核互斥**，可以保護兩核 task 共用的小結構；但它是**全系統共用的一把鎖**，所有核的 kernel 操作都會被擋住。只放幾行。
- 要保護較長的操作（例如 printf、走訪 linked list），用 **mutex**（可阻塞、有 priority inheritance）。
- **陷阱**：SMP 版在 scheduler **尚未啟動**時，`vTaskEnterCritical` 會關中斷，`vTaskExitCritical` 卻不會重新開中斷（只有 scheduler 執行中才走開中斷的路徑）。所以在 `main()` 中呼叫 `xTaskCreate` / `xQueueCreate` 之後，優先權數值 ≥ 0x10 的 IRQ 會一直被遮罩到 scheduler 啟動為止。⚠️未驗證：此結論讀原始碼推論，未實機驗證。**實務建議**：硬體初始化（`stdio_init_all()`、時脈、GPIO）放在建立 RTOS 物件之前；需要 IRQ 或 `sleep_ms` 的初始化放到 task 裡做；`xTaskCreate` 與 `vTaskStartScheduler` 之間不要等待任何東西。

### 4.10 ISR 規則與中斷優先權

1. ISR 中**只能**呼叫名稱有 `FromISR` 的 API（以及 `portYIELD_FROM_ISR`、`taskENTER_CRITICAL_FROM_ISR`）。FromISR API 不會阻塞。
2. 標準模式：

```c
void my_irq_handler(void) {
    BaseType_t woken = pdFALSE;             /* 一定要初始化成 pdFALSE */
    /* 1. 清中斷旗標、讀硬體 */
    /* 2. 通知 task（可呼叫多個 FromISR，共用同一個 woken） */
    vTaskNotifyGiveFromISR(worker_handle, &woken);
    /* 3. 若喚醒了比被中斷 task 更高優先權的 task，離開 ISR 時就切換 */
    portYIELD_FROM_ISR(woken);              /* Arm port：設 PendSV pending */
}
```

3. 不呼叫 `portYIELD_FROM_ISR` 也不會出錯，只是被喚醒的 task 要等到下一個 tick / 下一次排程才跑 → 延遲變大。
4. 優先權（RP2350 Arm Cortex-M33，NVIC 只有高 4 bit 有效，可用值 0x00, 0x10, …, 0xF0；**數字越小越優先**）：

| IRQ 優先權數值 | 可呼叫 FreeRTOS API？ | 會被 critical section 遮罩？ |
|---|---|---|
| 0x00（`PICO_HIGHEST_IRQ_PRIORITY`） | **不可**（configASSERT 會抓；不抓就會偶發損壞 kernel 資料） | 不會（延遲最低） |
| 0x10～0xF0（含 SDK 預設 `PICO_DEFAULT_IRQ_PRIORITY` = 0x80） | 可以（只能用 FromISR） | 會 |
| kernel 的 PendSV / SysTick / doorbell | — | 設為最低（0xFF） |

5. pico-sdk 的 IRQ 註冊方式不變：`irq_set_exclusive_handler(irq, handler)`、`irq_set_enabled(irq, true)`；GPIO 用 `gpio_set_irq_enabled_with_callback(pin, events, true, cb)`（callback 在 IRQ context，**在呼叫它的那顆核上**啟用）。在哪一核啟用 IRQ，ISR 就在哪一核執行：想讓 ISR 跑在 core 1，就在綁 core 1 的 task 裡啟用。
6. 在 IRQ 會用到的 queue / task handle 建立好之前，不要啟用該 IRQ。
7. RISC-V port：不支援巢狀中斷（見 §3.8）。

### 4.11 診斷：stack、heap、CPU 使用率

```c
UBaseType_t uxTaskGetStackHighWaterMark(TaskHandle_t xTask);   /* NULL = 自己；單位 words，越小越危險 */
size_t xPortGetFreeHeapSize(void);
size_t xPortGetMinimumEverFreeHeapSize(void);
void vTaskListTasks(char *pcWriteBuffer, size_t uxBufferLength);            /* 舊巨集 vTaskList(buf) */
void vTaskGetRunTimeStatistics(char *pcWriteBuffer, size_t uxBufferLength); /* 舊巨集 vTaskGetRunTimeStats(buf) */
UBaseType_t uxTaskGetNumberOfTasks(void);
```

Hook 實作（對應 §3.4 開的 config）：

```c
void vApplicationStackOverflowHook(TaskHandle_t xTask, char *pcTaskName) {
    (void)xTask;
    panic("stack overflow: %s", pcTaskName);    /* pico-sdk panic()；或 for(;;) 停住再用 gdb 看 */
}
void vApplicationMallocFailedHook(void) {
    panic("FreeRTOS heap exhausted");
}
```

run-time stats（每 task CPU 時間）設定，RP2350 port 沒有提供計數器，要自己接 µs timer：

```c
/* FreeRTOSConfig.h */
#define configGENERATE_RUN_TIME_STATS           1
#define configUSE_STATS_FORMATTING_FUNCTIONS    1
#define configUSE_TRACE_FACILITY                1
#ifndef __ASSEMBLER__
extern uint32_t ulAppRunTimeCounter(void);
#endif
#define portCONFIGURE_TIMER_FOR_RUN_TIME_STATS()   /* 空：pico 的 timer 開機就在跑 */
#define portGET_RUN_TIME_COUNTER_VALUE()        ulAppRunTimeCounter()

/* main.c */
uint32_t ulAppRunTimeCounter(void) { return time_us_32(); }   /* µs；約 71.6 分鐘溢位 */

void stats_task(void *p) {
    static char buf[1024];                     /* 每個 task 一行約 40 bytes；static 避免吃 stack */
    for (;;) {
        vTaskDelay(pdMS_TO_TICKS(2000));
        vTaskGetRunTimeStatistics(buf, sizeof buf);
        printf("Task\t\tAbs(us)\t\t%%\n%s\n", buf);   /* IDLE0/IDLE1 的 % 越高 = 越閒 */
        vTaskListTasks(buf, sizeof buf);
        printf("Name\t\tState\tPrio\tStack\tNum\n%s\n", buf);  /* Stack 欄 = high water mark */
    }
}
```

- `vTaskGetRunTimeStatistics` 需要 `configGENERATE_RUN_TIME_STATS == 1`、`configUSE_STATS_FORMATTING_FUNCTIONS > 0`、`configUSE_TRACE_FACILITY == 1`；內部用 `snprintf`。
- 輸出欄位格式（tab 分隔順序、狀態字母）隨版本略有不同，以實際輸出為準。
- CPU 使用率 ≈ 100% − idle task 的百分比。SMP 下每個 task 的 % 是相對於牆鐘時間（所有 task 加總最多約 200%），所以雙核整體使用率 ≈ 100% − (`IDLE0`% + `IDLE1`%)/2；idle task 不綁核，不能把 `IDLE0` 當成 core 0（依 `tasks.c` 讀碼）。
- 量單一段程式的時間仍用 `time_us_32()` 或 cycle counter（見 `pico-sdk.md` / `03-optimize.md`）。

---

## 5. 常用模式

### 5.1 Deferred interrupt processing（ISR 只做最少，重活交給 task）

```c
static TaskHandle_t adc_task_h;
static volatile uint16_t last_raw;

static void adc_irq(void) {                      /* 例：資料就緒中斷 */
    BaseType_t woken = pdFALSE;
    last_raw = read_and_clear_hw();              /* 只做必要的硬體動作 */
    vTaskNotifyGiveFromISR(adc_task_h, &woken);
    portYIELD_FROM_ISR(woken);
}

static void adc_task(void *p) {
    for (;;) {
        uint32_t n = ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(100));
        if (n == 0) { /* 100 ms 沒有中斷：逾時處理 */ continue; }
        /* n > 1 代表處理太慢，期間來了多次中斷（資料可能被覆蓋 → 改用 queue / stream buffer） */
        process(last_raw);
    }
}
```

處理 task 的優先權要夠高（通常高於一般運算 task），中斷後才能立刻執行。

### 5.2 生產者 / 消費者

```c
typedef struct { uint32_t id; int32_t value; } msg_t;
static QueueHandle_t q;                          /* q = xQueueCreate(16, sizeof(msg_t)); */

void producer(void *p) {
    msg_t m = {0};
    for (;;) {
        m.value = compute(m.id++);
        if (xQueueSend(q, &m, pdMS_TO_TICKS(5)) != pdPASS) { dropped++; }  /* 不要無限等，避免卡死 */
    }
}
void consumer(void *p) {
    msg_t m;
    for (;;) {
        xQueueReceive(q, &m, portMAX_DELAY);    /* 沒資料時阻塞，不吃 CPU */
        output(&m);
    }
}
```

大資料（例如 1 KB buffer）：建立兩個 queue `free_q`、`full_q`，裡面放 `uint8_t *` 指標，生產者從 `free_q` 拿空 buffer、填完丟 `full_q`；消費者反過來。只複製 4 bytes 指標，零拷貝。

### 5.3 雙核平行計算（data parallel）+ 等待全部完成

```c
#define BIT_W0 (1u << 0)
#define BIT_W1 (1u << 1)
static EventGroupHandle_t done;          /* done = xEventGroupCreate(); */
static TaskHandle_t w[2];
static int64_t partial[2];

static void worker(void *p) {
    uint32_t idx = (uint32_t)(uintptr_t)p;       /* 0 或 1 */
    for (;;) {
        ulTaskNotifyTake(pdTRUE, portMAX_DELAY); /* 等主 task 發工作 */
        int64_t s = 0;
        for (size_t i = idx * N / 2; i < (idx + 1) * N / 2; i++) s += data[i];   /* 各自累加，不共享 */
        partial[idx] = s;
        xEventGroupSetBits(done, 1u << idx);
    }
}
/* 建立：xTaskCreateAffinitySet(worker, "w0", 512, (void *)0, 3, 1u << 0, &w[0]);
         xTaskCreateAffinitySet(worker, "w1", 512, (void *)1, 3, 1u << 1, &w[1]); */
static void master(void *p) {
    for (;;) {
        xTaskNotifyGive(w[0]); xTaskNotifyGive(w[1]);
        xEventGroupWaitBits(done, BIT_W0 | BIT_W1, pdTRUE, pdTRUE, portMAX_DELAY);
        int64_t total = partial[0] + partial[1];  /* event group 的同步確保看得到 partial（⚠️未驗證：kernel 內部 critical section 提供的記憶體順序，依慣例成立） */
        use(total);
    }
}
```

### 5.4 軟體 timer 取代忙等的 LED / watchdog 檢查

```c
static void blink_cb(TimerHandle_t t) { (void)t; gpio_xor_mask(1u << PICO_DEFAULT_LED_PIN); }  /* 不可阻塞 */
/* 在 main 或 task 中：
   TimerHandle_t bt = xTimerCreate("blink", pdMS_TO_TICKS(500), pdTRUE, NULL, blink_cb);
   configASSERT(bt); xTimerStart(bt, 0); */
```

---

## 6. 裸機（pico-sdk）↔ FreeRTOS 對照

| 裸機做法 | FreeRTOS 對應 | 備註 |
|---|---|---|
| `while(1)` 主迴圈 + 狀態機 | 每個功能一個 task，`for(;;)` 中阻塞等待 | 優先權決定誰先跑 |
| `multicore_launch_core1(core1_main)` | `xTaskCreateAffinitySet(..., 1u << 1, ...)` | SMP 下 scheduler 自己啟動 core 1 |
| `multicore_fifo_push/pop_blocking` | `xQueueSend/xQueueReceive`（或 `xTaskNotify` 傳 32 位元） | queue 可多對多、可設逾時 |
| `queue_t`（pico_util） | FreeRTOS queue | `queue_t` 在 interop 下仍可用，跨「FreeRTOS ↔ 非 FreeRTOS」時用它 |
| `spin_lock_blocking` / `critical_section_enter_blocking` | `taskENTER_CRITICAL()`（極短）或 mutex（較長） | 持 spinlock 時不可呼叫 FreeRTOS API |
| `mutex_enter_blocking`（pico_sync） | `xSemaphoreTake(mutex, timeout)` | FreeRTOS mutex 有 priority inheritance |
| `volatile bool flag` 在 ISR 設、主迴圈輪詢 | `vTaskNotifyGiveFromISR` + `ulTaskNotifyTake` | 不再輪詢，零 CPU 浪費、延遲更低 |
| `__wfi()` / `__wfe()` 等待 | 阻塞 API；沒事做時 idle task 執行 | idle hook 可放低功耗指令 |
| `add_repeating_timer_ms(-10, cb, ...)` | `xTaskDelayUntil` 週期 task，或 `xTimerCreate(..., pdTRUE, ...)` | 前者有 task 優先權與自己的 stack；後者 callback 不可阻塞 |
| `add_alarm_in_ms` 單次 | `xTimerCreate(..., pdFALSE, ...)` 或 `vTaskDelay` | |
| `sleep_ms` | `vTaskDelay(pdMS_TO_TICKS(ms))` | interop 開啟時 `sleep_ms` 亦可 |
| `busy_wait_us` | 仍是忙等，task 內盡量避免；µs 級精準等待時才用 | 忙等期間同核低優先權 task 無法執行 |
| 兩核各自累加再合併 | 兩個綁核 worker task + event group / notification | 同 `multicore-sync.md` B11.1 的思路 |

---

## 7. 完整範例：雙核 queue + ISR notification

功能：core 0 的 `producer` 每 100 ms 產生一筆資料丟進 queue；core 1 的 `consumer` 收資料印出；GPIO 15 按鈕中斷（在 core 1 啟用）用 task notification 喚醒 core 1 的 `button` task。

`main.c`：

```c
#include <stdio.h>
#include "pico/stdlib.h"
#include "FreeRTOS.h"
#include "task.h"
#include "queue.h"

#define BTN_PIN         15
#define PRIO_CONSUMER   (tskIDLE_PRIORITY + 1)
#define PRIO_PRODUCER   (tskIDLE_PRIORITY + 2)
#define PRIO_BUTTON     (tskIDLE_PRIORITY + 3)   /* 處理中斷的 task 優先權最高 */
#define CORE0           (1u << 0)
#define CORE1           (1u << 1)

typedef struct { uint32_t seq; uint32_t t_us; } sample_t;

static QueueHandle_t sample_q;
static TaskHandle_t  button_h;
static volatile uint32_t dropped;

/* GPIO IRQ callback：IRQ context，只能用 FromISR */
static void gpio_cb(uint gpio, uint32_t events) {
    BaseType_t woken = pdFALSE;
    if (gpio == BTN_PIN && (events & GPIO_IRQ_EDGE_FALL)) {
        vTaskNotifyGiveFromISR(button_h, &woken);
    }
    portYIELD_FROM_ISR(woken);
}

static void producer_task(void *p) {
    (void)p;
    uint32_t seq = 0;
    TickType_t last = xTaskGetTickCount();
    for (;;) {
        sample_t s = { .seq = seq++, .t_us = time_us_32() };
        if (xQueueSend(sample_q, &s, pdMS_TO_TICKS(10)) != pdPASS) dropped++;
        xTaskDelayUntil(&last, pdMS_TO_TICKS(100));          /* 固定 100 ms 週期 */
    }
}

static void consumer_task(void *p) {
    (void)p;
    sample_t s;
    for (;;) {
        if (xQueueReceive(sample_q, &s, portMAX_DELAY) == pdPASS) {
            printf("[core%u] seq=%lu latency=%lu us dropped=%lu\n", get_core_num(),
                   (unsigned long)s.seq, (unsigned long)(time_us_32() - s.t_us),
                   (unsigned long)dropped);
        }
    }
}

static void button_task(void *p) {
    (void)p;
    gpio_init(BTN_PIN);
    gpio_set_dir(BTN_PIN, GPIO_IN);
    gpio_pull_up(BTN_PIN);
    /* 在這個 task（綁 core 1）裡啟用 → IRQ 在 core 1 處理；此時 button_h 已有效 */
    gpio_set_irq_enabled_with_callback(BTN_PIN, GPIO_IRQ_EDGE_FALL, true, gpio_cb);
    for (;;) {
        uint32_t n = ulTaskNotifyTake(pdTRUE, portMAX_DELAY);
        printf("[core%u] button x%lu, stack left=%lu words\n", get_core_num(),
               (unsigned long)n, (unsigned long)uxTaskGetStackHighWaterMark(NULL));
        vTaskDelay(pdMS_TO_TICKS(50));                       /* 簡易防彈跳 */
        ulTaskNotifyTake(pdTRUE, 0);                         /* 丟掉彈跳期間累積的通知 */
    }
}

int main(void) {
    stdio_init_all();                                        /* 硬體初始化放在建立 RTOS 物件之前 */

    sample_q = xQueueCreate(8, sizeof(sample_t));
    configASSERT(sample_q != NULL);

    BaseType_t ok = pdPASS;
    ok &= (xTaskCreateAffinitySet(producer_task, "prod", 512,  NULL, PRIO_PRODUCER, CORE0, NULL) == pdPASS);
    ok &= (xTaskCreateAffinitySet(consumer_task, "cons", 1024, NULL, PRIO_CONSUMER, CORE1, NULL) == pdPASS);
    ok &= (xTaskCreateAffinitySet(button_task,   "btn",  1024, NULL, PRIO_BUTTON,   CORE1, &button_h) == pdPASS);
    configASSERT(ok);

    vTaskStartScheduler();                                   /* core 0 呼叫；自動啟動 core 1；不返回 */
    for (;;) { }                                             /* 到這裡代表 heap 不足以建立 idle/timer task */
}
```

`CMakeLists.txt`：用 §3.2 的內容（`target_link_libraries(rtos_demo PRIVATE pico_stdlib FreeRTOS-Kernel-Heap4)`；`hardware_gpio` 已包含在 `pico_stdlib`）。`FreeRTOSConfig.h`：§3.4（`configUSE_CORE_AFFINITY 1`、`configNUMBER_OF_CORES 2`、`configCHECK_FOR_STACK_OVERFLOW 2` 時記得加 §4.11 的兩個 hook）。

驗證點：
- 輸出每 100 ms 一行，`seq` 連續、`dropped` 為 0；`latency` 是 queue 傳遞延遲（含 printf 等待）。
- 按鈕後立即出現 button 行；`stack left` 遠大於 0。
- `printf` 從兩個 task 呼叫：pico stdio 內部有 mutex，開 SYNC interop 時會正確阻塞；輸出行不交錯但可能互相等待。

---

## 8. 效能

### 8.1 先問自己的問題

1. 有沒有 task 在**忙等**（`while(!flag);`、`busy_wait_*`、輪詢 queue 用 0 逾時的迴圈）？→ 改成阻塞 API。忙等會霸占該核，同核較低優先權的 task 與 idle 全部停擺。
2. 優先權是否合理？→ 對延遲敏感的（處理中斷的 task、控制迴圈）高；批次運算、log、統計低。
3. 兩個熱點 task 是否被排到同一核、或在兩核間跳來跳去？→ 用 affinity 綁核。
4. 臨界區 / 持鎖時間是否太長？→ 計算移出鎖外（同 `multicore-sync.md` 原則）。
5. 通訊機制是否太重？→ 1 對 1 訊號用 notification；大資料傳指標或用 stream buffer。
6. tick 太高？→ 1000 Hz 已是常見上限；沒必要時降低可減少中斷開銷。

### 8.2 機制成本比較（定性）

| 機制 | 相對成本 | 何時用 |
|---|---|---|
| task notification | 最低（不需另外物件；官方：比 binary semaphore 快 45%） | 1 個接收者的事件 / 計數 / 32 位元值 |
| binary / counting semaphore | 中（底層是 queue） | 多個可能接收者、或需要 handle 傳來傳去 |
| queue | 中到高（每筆 `uxItemSize` bytes 複製兩次：送入、取出） | 多筆資料、多生產者/消費者 |
| stream / message buffer | 中（單讀單寫 ring buffer） | ISR → task 的位元組流 |
| event group | 中；`SetBitsFromISR` 要經 timer task（多一次 context switch） | 多事件 AND/OR、多等待者、barrier |
| mutex | 中（含 priority inheritance） | 保護較長的共享資源存取 |
| `taskENTER_CRITICAL` | 單次很低，但會擋住**兩核**的 kernel 操作與本核 IRQ | 幾行內的共享變數讀寫 |
| context switch | 每次數百 cycles 等級 ⚠️未驗證（未找到 RP2350 實測數據） | 減少不必要的喚醒 / 切換 |

具體數字請**自己量**：用 `time_us_32()` 或 cycle counter 量 1000 次 give/take 往返的平均時間。

### 8.3 SMP 與綁核

- 不綁核時 scheduler 可能把 task 移到另一核。RP2350 兩核共享 SRAM、沒有 per-core data cache（只有 XIP cache），所以搬核的主要代價是 scheduler 開銷，而非 cache 失效 ⚠️未驗證（依 RP2350 架構推論）。
- 綁核的好處：行為可預測、兩個熱點 task 不會擠在同一核、可以把 ISR 與處理它的 task 放同一核（中斷在哪核啟用就在哪核跑）。
- 經典配置：core 0 放 I/O 與通訊（USB stdio、UART、中斷處理），core 1 放純運算。
- 資料平行時，每核一個 worker、各自累加，最後合併；不要讓兩核頻繁搶同一把鎖。
- `configRUN_MULTIPLE_PRIORITIES = 1` 才能讓不同優先權的 task 同時佔滿兩核。

### 8.4 Tick rate 取捨

| `configTICK_RATE_HZ` | 優點 | 缺點 |
|---|---|---|
| 1000 | 1 ms 延遲解析度、time slice 短 | 每秒 1000 次 tick 中斷 |
| 100 | 中斷開銷小 | 10 ms 解析度；`pdMS_TO_TICKS(<10)` 變 0 |

改 tick rate 會改變所有以 tick 為單位的常數；程式中一律用 `pdMS_TO_TICKS()`，不要寫死 tick 數。

### 8.5 Priority inversion 示意

```
H: ──────等 mutex(阻塞)──────────────────────┐ 取得鎖
M: ────────────  一直在跑（搶占 L）  ────────┘
L: 取得 mutex ─被 M 搶占─────────────────────── 放鎖
```

- 用 binary semaphore 當鎖 → H 會被 M 卡住不定時間。
- 用 mutex → L 暫時繼承 H 的優先權，M 搶不走 L，L 很快放鎖。
- SMP 下另一核可能剛好在跑 M 或 L，現象較不明顯但仍會發生；不要依賴「另一核會救」。

---

## 9. 常見錯誤（症狀 → 原因 → 修法）

| 症狀 | 常見原因 | 修法 |
|---|---|---|
| HardFault / 亂跑 / 變數莫名被改 | task stack 太小（printf、大區域陣列） | 加大 stack（words！）、大陣列改 static；開 `configCHECK_FOR_STACK_OVERFLOW 2`；看 `uxTaskGetStackHighWaterMark` |
| task 沒有被建立、某功能完全不動 | heap 不足，`xTaskCreate` 回傳 `errCOULD_NOT_ALLOCATE_REQUIRED_MEMORY` 但沒檢查 | 檢查回傳 `!= pdPASS`；開 malloc failed hook；加大 `configTOTAL_HEAP_SIZE` 或縮小 stack |
| `vTaskStartScheduler` 之後的程式被執行 | 建立 idle / timer task 的 heap 不足 | 同上 |
| configASSERT 在 `vPortValidateInterruptPriority` 失敗 | 在優先權 0x00 的 IRQ 呼叫 FromISR API | IRQ 優先權改成 ≥ 0x10（例如維持預設 0x80） |
| ISR 中呼叫 `xQueueSend` / `xSemaphoreTake` 後當機或 assert | ISR 用了非 FromISR API | 改 FromISR 版本，加 `portYIELD_FROM_ISR` |
| 中斷後 task 很久才反應 | 忘了 `portYIELD_FROM_ISR(woken)`，或處理 task 優先權太低 | 加上；提高處理 task 優先權 |
| 低優先權 task 永遠不跑 | 高優先權 task 忙等 / 從不阻塞（starvation） | 高優先權 task 必須阻塞；或降低其優先權 |
| idle 的百分比是 0、記憶體沒被回收 | 有 task 在優先權 > 0 忙等，idle 永遠拿不到 CPU（idle 負責回收被刪 task 的記憶體） | 消除忙等 |
| 週期越跑越慢 / 時間漂移 | 週期迴圈用 `vTaskDelay` | 改 `xTaskDelayUntil` |
| `vTaskDelay(pdMS_TO_TICKS(1))` 沒延遲 | tick rate 太低，換算結果為 0 | 提高 tick rate 或改用硬體 timer |
| 兩核計數結果偶爾少 | SMP 下共享變數沒保護（以為「同一時間只有一個 task 在跑」） | `taskENTER_CRITICAL`、mutex、atomic，或改成各自累加再合併 |
| 程式卡死在兩個 mutex | deadlock：兩 task 以相反順序取鎖 | 固定取鎖順序；Take 用有限逾時並處理失敗 |
| 呼叫 API 時卡住（scheduler 尚未啟動） | 在 `main()` 中用了有等待時間的阻塞 API、`vTaskDelay`，或依賴 IRQ 的初始化（`sleep_ms`、USB stdio 等待連線）放在 `xTaskCreate` 之後 | scheduler 啟動前只做建立物件；等待類動作放進 task（見 §4.9 陷阱） |
| core 1 行為異常 / launch 失敗 | SMP 下又自己 `multicore_launch_core1`，或動了 FIFO / `PICO_SPINLOCK_ID_OS1/2` | 交給 scheduler；用 task + affinity |
| `vTaskStartScheduler` 在 core 1 呼叫就 assert | SMP port 要求在 core 0 啟動 | 改在 core 0 呼叫 |
| 用了 `assert` 的檢查完全沒作用 | Release build（SDK 預設）帶 `-DNDEBUG`，`assert` 被移除 → `configASSERT` 也消失 | 除錯時用 Debug build，或把 `configASSERT(x)` 定義成 `if (!(x)) panic(...)` 之類不受 NDEBUG 影響的寫法 |
| 浮點運算結果偶爾錯亂 | 沒開 `configENABLE_FPU`，context switch 沒保存 FPU 暫存器 | `configENABLE_FPU 1` |
| link 錯誤 `pvPortMalloc` undefined | 只 link `FreeRTOS-Kernel`，沒有 heap | link `FreeRTOS-Kernel-Heap4` |
| `FreeRTOSConfig.h: No such file` | 該目錄沒加進 target 的 include path | `target_include_directories(app PRIVATE <dir>)` |
| CMake：`does not contain a 'rp2350' port` | kernel 是沒有 RP2350 port 的上游版本，submodule 沒初始化 | `git submodule update --init portable/ThirdParty/Community-Supported-Ports` 或用 raspberrypi fork |
| 軟體 timer 時間不準、其他 timer 被延誤 | callback 太久或在 callback 裡阻塞 | callback 只送 notification，工作交給 task |
| `xEventGroupSetBitsFromISR` 沒效果 / 編譯不到 | 沒開 `configUSE_TIMERS` / `INCLUDE_xTimerPendFunctionCall`，或 timer queue 滿 | 開 config；或改用 `xTaskNotifyFromISR(..., eSetBits, ...)` |
| 多個 task 寫同一個 stream buffer 時資料錯亂 | stream / message buffer 只支援單一寫入者 | 包 critical section，或改用 queue |

---

## 10. 除錯檢查清單

1. 讀 `FreeRTOSConfig.h`：核心數、`configRUN_MULTIPLE_PRIORITIES`、affinity、tick rate、heap 大小、哪些 INCLUDE_ 有開、`configASSERT` 是否定義、build type 是否 Release。
2. 列出所有 task：名稱、優先權、stack（words）、affinity、會阻塞在哪個 API。畫出誰等誰（queue / notification / mutex）的關係圖，看有沒有環（deadlock）。
3. 所有 `xTaskCreate*` / `xQueueCreate` / `xSemaphoreCreate*` / `xTimerCreate` 都有檢查回傳值嗎？
4. 開 `configCHECK_FOR_STACK_OVERFLOW 2`、malloc failed hook，用 Debug build 重跑。
5. 定期印 `uxTaskGetStackHighWaterMark` 與 `xPortGetMinimumEverFreeHeapSize()`。
6. 所有 ISR：只用 FromISR API？`woken` 初始化成 pdFALSE？有 `portYIELD_FROM_ISR`？IRQ 優先權 ≥ 0x10？IRQ 在需要的 handle 建好之後才啟用？
7. 共享變數：列出哪些變數被兩個以上 task / ISR / 核存取，各用什麼保護。SMP 下「優先權不同」不是保護。
8. 有沒有忙等或從不阻塞的 task？看 run-time stats 裡 IDLE0 / IDLE1 的比例。
9. 卡住時用 gdb：`info threads` 不一定認得 FreeRTOS task ⚠️未驗證（需要 RTOS-aware 的 OpenOCD 設定）；至少看兩核目前 PC（`bt`），以及 `pxCurrentTCBs` ⚠️未驗證（SMP 版 kernel 內部變數名，依 `tasks.c` 原始碼）。
10. 時間相關問題：確認 `pdMS_TO_TICKS` 換算不是 0、週期 task 用 `xTaskDelayUntil`、系統時脈在 scheduler 啟動前就設好。

## 11. 優化檢查清單

- [ ] 沒有任何 task 忙等；等待一律用阻塞 API（有合理逾時）。
- [ ] 中斷處理採 deferred processing：ISR 只清旗標 + notification，處理 task 高優先權。
- [ ] 1 對 1 訊號改用 task notification；只有需要多筆緩衝時才用 queue。
- [ ] 大資料傳指標（雙 queue 管理 buffer 所有權）或用 stream buffer，不複製整塊。
- [ ] 熱點 task 綁核；I/O 與運算分核；ISR 與其處理 task 同核。
- [ ] 平行運算各核區域累加、最後合併，避免共享鎖。
- [ ] `taskENTER_CRITICAL` 區段只有幾行；長的改 mutex；計算移出鎖外。
- [ ] 週期工作用 `xTaskDelayUntil`；檢查回傳 pdFALSE（deadline miss）次數。
- [ ] 用 run-time stats 確認瓶頸 task 的 CPU 百分比，優化前後各量一次（Release build、同樣條件）。
- [ ] stack / heap 依 high water mark 調整到「有餘裕但不浪費」（留 20～30% 是常見經驗值 ⚠️未驗證，非官方數字）。
- [ ] 若題目只看吞吐量、不在乎即時性：考慮減少 task 數與切換次數，甚至把熱點迴圈放在單一 task 內不切換。

---

## 12. 向模型提問的範本

**範本 1：讀懂考場的 FreeRTOS 專案**

```
以下是考場專案的 FreeRTOSConfig.h 與 CMakeLists.txt：
{{貼 FreeRTOSConfig.h}}
{{貼 CMakeLists.txt}}
以及 main.c：
{{貼 main.c}}
請整理：
1. kernel 是單核還是 SMP（configNUMBER_OF_CORES）、configRUN_MULTIPLE_PRIORITIES、affinity 是否開啟、tick rate、heap 方案與大小。
2. 每個 task 的名稱、優先權（數字越大越優先）、stack（words → bytes）、affinity、阻塞點。
3. task / ISR 之間的通訊圖（queue、notification、semaphore、mutex、event group）。
4. 哪些 config 沒定義而使用 FreeRTOS 預設值，可能影響行為。
只分析，不要改程式。
```

**範本 2：把裸機程式改寫成 FreeRTOS**

```
平台：RP2350（{{Arm / RISC-V}}），pico-sdk {{版本}}，FreeRTOS SMP（configNUMBER_OF_CORES = {{2}}）。
以下是裸機版本（用了 {{multicore_fifo / spin_lock / repeating_timer / flag 輪詢}}）：
{{貼程式碼}}
請改寫成 FreeRTOS 版本：
- 每個功能一個 task，標明優先權、stack（words）、affinity 與理由；
- 依對照表把 FIFO→queue、spin_lock→critical section 或 mutex、repeating_timer→xTaskDelayUntil 週期 task、flag 輪詢→task notification；
- ISR 只用 FromISR API 並使用 portYIELD_FROM_ISR；
- 不要自己呼叫 multicore_launch_core1；
- 所有建立物件的 API 都檢查回傳值。
只使用 FreeRTOS-Kernel V11 與 pico-sdk 實際存在的 API，不確定的請標明。
```

**範本 3：效能優化**

```
目標：{{提高吞吐量 / 降低中斷到處理的延遲 / 降低 CPU 使用率}}。
目前量測：{{run-time stats 輸出 / 每筆處理時間 X us / 延遲 Y us}}。
FreeRTOSConfig.h 重點：{{tick rate、核心數、RUN_MULTIPLE_PRIORITIES}}。
{{貼相關 task 與 ISR 程式碼}}
請依序檢查：忙等 → 優先權配置 → 綁核 → 通訊機制成本（notification / queue / stream buffer）→ 臨界區長度 → tick rate，
每個建議說明預期效果、正確性風險，以及我該怎麼量測驗證（Release build、多次取中位數）。
```

**範本 4：當機 / 卡住 / 偶發錯誤**

```
症狀：{{HardFault / 卡住不動 / configASSERT 失敗在 檔名:行號 / 結果偶爾錯}}。
發生時機：{{開機立刻 / 按按鈕後 / 跑 N 分鐘後}}。
輸出 / gdb bt：
{{貼輸出}}
相關程式碼與 FreeRTOSConfig.h：
{{貼程式碼}}
請依可能性列出 3～5 個原因（優先考慮：stack overflow、heap 不足、ISR 優先權或非 FromISR API、SMP 共享資料未保護、deadlock、scheduler 啟動前呼叫阻塞 API），
每個原因給一個能確認或排除的實驗（例如開 configCHECK_FOR_STACK_OVERFLOW 2、印 high water mark）。
```

**範本 5：查證 API 細節**

```
考場文件 / 標頭檔寫的是：{{貼 API 宣告或文件段落}}。
請說明：參數單位（tick / ms / words / bytes）、回傳值意義、會不會阻塞、能不能在 ISR 使用、需要哪些 config / INCLUDE_ 巨集，
以及在 SMP（兩核）下有沒有不同。若與你的記憶不同，以我貼的內容為準並指出差異。
```
