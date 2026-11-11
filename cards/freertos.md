# 貼上卡：FreeRTOS（SMP）on RP2350 + pico-sdk
> 用法：一次只複製一張卡（兩條分隔線之間），貼進對話，再在下面寫你的問題。每張 ≤ 1200 字元。
> 來源：full/domain/freertos.md、lite/domain/freertos.md（詳細版）｜最後更新 2026-11

---

【參考卡｜FreeRTOS 1/8｜核心規則（先看這張）】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
平台：RP2350（Pico 2），非 RP2040；FreeRTOS-Kernel V11 SMP，port 為 Community-Supported-Ports 的 `RP2350_ARM_NTZ`（Cortex-M33）或 `RP2350_RISC-V`（Hazard3）；pico-sdk 2.3.1。以考場 FreeRTOSConfig.h 為準。
1. task 優先權數字越大越優先（`tskIDLE_PRIORITY` = 0 最低）；IRQ 優先權相反（0x00 最高）
2. stack 單位是 words（4 bytes）：`xTaskCreate(..., 512, ...)` = 2 KB；有 printf 至少 512
3. task 不忙等：`xQueueReceive(q, &x, portMAX_DELAY)`、`ulTaskNotifyTake(pdTRUE, portMAX_DELAY)`；被阻塞的 task 不吃 CPU
4. 週期迴圈用 `xTaskDelayUntil(&last, pdMS_TO_TICKS(T))`（last 先設 `xTaskGetTickCount()`）；`vTaskDelay` 會漂移
5. `pdMS_TO_TICKS` 整數除法捨去；tick 100 Hz 時 <10 ms 變 0
6. ISR 只能呼叫結尾 `FromISR` 的 API，並用 `portYIELD_FROM_ISR(woken)`；mutex 不能在 ISR 用
7. 呼叫 API 的 IRQ 優先權數值必須 ≥ 0x10（SDK 預設 0x80 可；0x00 不可）
8. SMP：`vTaskStartScheduler()` 在 core 0 呼叫，它自己 launch core1 → 不要再 `multicore_launch_core1`、不要自己用 FIFO、不要動 spinlock OS1/OS2
9. SMP 下高低優先權 task 可同時跑、ISR 與 task 可並行 → 共享資料一定要保護
10. `xTaskCreate` 成功 = `pdPASS`，失敗 -1；`xQueueCreate` 失敗回 NULL；都要檢查
11. task 內 `sleep_ms()` 會讓出 CPU（TIME_INTEROP=1 時）；`busy_wait_ms()` 不會
12. task 函式不能 return；結束用 `vTaskDelete(NULL)`

---

【參考卡｜FreeRTOS 2/8｜CMake 與 FreeRTOSConfig.h】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
平台：RP2350（Pico 2）pico-sdk + FreeRTOS SMP。
```cmake
pico_sdk_init()
include(FreeRTOS_Kernel_import.cmake)
target_include_directories(app PRIVATE ${CMAKE_CURRENT_LIST_DIR})
target_link_libraries(app PRIVATE pico_stdlib FreeRTOS-Kernel-Heap4)
```
- kernel 路徑：`-DFREERTOS_KERNEL_PATH=`；target `FreeRTOS-Kernel`、`-Heap1`～`-Heap5`（heap_4 最常用）、`-Static`；只 link Kernel 沒 heap → pvPortMalloc undefined
- FreeRTOSConfig.h 所在目錄要在 include path
FreeRTOSConfig.h 重點：
- `configNUMBER_OF_CORES 2`、`configUSE_CORE_AFFINITY 1`
- `configRUN_MULTIPLE_PRIORITIES 1`（0 = 只有同優先權 task 才會同時跑）
- `configTICK_RATE_HZ 1000`、`configTOTAL_HEAP_SIZE (128*1024)`、`configMINIMAL_STACK_SIZE 512`（words）
- `configSUPPORT_PICO_SYNC_INTEROP 1`、`configSUPPORT_PICO_TIME_INTEROP 1`
- 除錯：`configCHECK_FOR_STACK_OVERFLOW 2`、`configUSE_MALLOC_FAILED_HOOK 1`、`configASSERT(x)`（Release 的 -DNDEBUG 讓 assert 失效）
- RP2350 Arm 必設：`configENABLE_MPU 0`、`configENABLE_TRUSTZONE 0`、`configRUN_FREERTOS_SECURE_ONLY 1`、`configENABLE_FPU 1`、`configMAX_SYSCALL_INTERRUPT_PRIORITY 16`
- 要 `INCLUDE_xTaskDelayUntil 1`；config 沒定義就用預設值 → 先讀考場的 FreeRTOSConfig.h

---

【參考卡｜FreeRTOS 3/8｜task、時間 API】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
平台：RP2350（Pico 2）FreeRTOS V11 SMP。`#include "FreeRTOS.h"`、`"task.h"`。
```c
BaseType_t xTaskCreate(fn, "name", stack_words, arg, prio, &handle);
BaseType_t xTaskCreateAffinitySet(fn, "name", stack_words, arg, prio,
                                  1u << core, &handle);
vTaskCoreAffinitySet(handle, mask);
vTaskStartScheduler();   // core 0 呼叫，不返回
vTaskDelete(NULL);       // 刪自己
vTaskSuspend(h); vTaskResume(h);
taskYIELD();
portGET_CORE_ID();       // = get_core_num()
```
- 成功回 pdPASS；記憶體不足回 errCOULD_NOT_ALLOCATE_REQUIRED_MEMORY（-1）→ 寫 `!= pdPASS`
- affinity bitmask：bit 0 = core 0、bit 1 = core 1；`tskNO_AFFINITY` = 任一核
- vTaskSuspend/Resume 不累計、不適合當同步 → 用 notification
時間：
```c
void periodic_task(void *p) {
    const TickType_t period = pdMS_TO_TICKS(10);
    TickType_t last = xTaskGetTickCount();
    for (;;) {
        if (xTaskDelayUntil(&last, period) == pdFALSE) {
            /* deadline miss */
        }
        do_work();
    }
}
```
- `vTaskDelay(ticks)` 相對延遲；`vTaskDelay(0)` 不阻塞
- `portMAX_DELAY` 在 `INCLUDE_vTaskSuspend == 1` 時 = 無限期等待
- `pdMS_TO_TICKS(ms)` = ms * configTICK_RATE_HZ / 1000（捨去）
- µs 級精度不要靠 tick，改用硬體 timer

---

【參考卡｜FreeRTOS 4/8｜queue、semaphore、mutex、notification、event group、timer】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
平台：RP2350（Pico 2）FreeRTOS V11 SMP。
queue（複製資料，多生產者 / 消費者、跨核安全）：
- `q = xQueueCreate(len, item_size)`（失敗 NULL）
- `xQueueSend(q, &item, ticks)`、`xQueueReceive(q, &buf, ticks)`、`xQueuePeek`
- `xQueueOverwrite` 只用於長度 1 的 queue
- 滿 / 空回 errQUEUE_FULL / errQUEUE_EMPTY（= 0）；大資料傳指標
semaphore / mutex（`#include "semphr.h"`）：
- `xSemaphoreCreateBinary()`（建立時是空的）、`xSemaphoreCreateCounting(max, init)`
- `xSemaphoreCreateMutex()`（priority inheritance，誰 Take 誰 Give，不可在 ISR）、`...RecursiveMutex()`
- `xSemaphoreTake(s, ticks)` / `xSemaphoreGive(s)`
- 互斥用 mutex（不用 binary）；事件同步用 notification / binary（不用 mutex）
task notification（最快，官方：比 binary semaphore 快 45%；只有 1 個接收者）：
- `xTaskNotifyGive(h)` + `ulTaskNotifyTake(pdTRUE, ticks)`（pdTRUE 清 0、回傳累計次數）
- `xTaskNotify(h, value, eSetBits)`、`xTaskNotifyWait(clr_entry, clr_exit, &val, ticks)`
event group：`xEventGroupWaitBits(g, bits, clearOnExit, waitAll, ticks)`；bit 0–23；`...SetBitsFromISR` 經 timer task（需 configUSE_TIMERS）
stream / message buffer：只支援單一寫入者與單一讀取者
軟體 timer：`xTimerCreate("t", ticks, pdTRUE, id, cb)` + `xTimerStart(t, 0)`；cb 在 `Tmr Svc` task 執行，不可阻塞

---

【參考卡｜FreeRTOS 5/8｜ISR 規則與中斷優先權】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
平台：RP2350（Pico 2）Cortex-M33 port（RP2350_ARM_NTZ），pico-sdk。
```c
void my_irq_handler(void) {
    BaseType_t woken = pdFALSE;
    /* 清中斷旗標、讀硬體 */
    vTaskNotifyGiveFromISR(worker_handle, &woken);
    portYIELD_FROM_ISR(woken);
}
```
規則：
- ISR 只能呼叫 `...FromISR` API（及 `portYIELD_FROM_ISR`、`taskENTER_CRITICAL_FROM_ISR`）；FromISR 不阻塞
- `woken` 一定初始化成 pdFALSE；多個 FromISR 可共用同一個 woken
- 忘了 `portYIELD_FROM_ISR`：被喚醒的 task 要等下次排程 → 延遲變大
- ISR 內的 critical：`UBaseType_t s = taskENTER_CRITICAL_FROM_ISR(); … taskEXIT_CRITICAL_FROM_ISR(s);`
IRQ 優先權（NVIC 高 4 bit 有效，0x00、0x10…0xF0，數字越小越優先）：
- 0x00（PICO_HIGHEST_IRQ_PRIORITY）：不可呼叫任何 FreeRTOS API；不會被 critical section 遮罩
- 0x10～0xF0（含 SDK 預設 0x80）：可呼叫 FromISR API；會被 critical section 遮罩
- 在 0x00 呼叫 → configASSERT 在 vPortValidateInterruptPriority 失敗
其他：
- 註冊方式不變：`irq_set_exclusive_handler(irq, fn)`、`irq_set_enabled(irq, true)`；GPIO `gpio_set_irq_enabled_with_callback(pin, events, true, cb)`
- IRQ 在哪核啟用就在哪核執行 → 想在 core 1 處理，就在綁 core 1 的 task 裡啟用
- IRQ 用到的 queue / task handle 建立好之後才啟用 IRQ
- 處理中斷的 task 優先權要高（ISR 只清旗標 + notification）
- RISC-V port：不支援巢狀中斷；不使用 configMAX_SYSCALL_INTERRUPT_PRIORITY

---

【參考卡｜FreeRTOS 6/8｜SMP、綁核、critical section、裸機對照】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
平台：RP2350（Pico 2）FreeRTOS SMP（configNUMBER_OF_CORES 2）。
- port 啟動時 claim 兩把 spinlock（`PICO_SPINLOCK_ID_OS1/OS2`，kernel 專用）與一個 doorbell（跨核 yield），然後自己 `multicore_reset_core1()` + launch
- `configRUN_MULTIPLE_PRIORITIES 1`：不同優先權 task 可同時在兩核跑 → 用優先權當互斥會出錯
- 綁核：`xTaskCreateAffinitySet(..., 1u << 1, ...)`；經典配置 core 0 放 I/O 與通訊、core 1 放純運算；ISR 與處理 task 同核
- 資料平行：每核一個 worker、各自累加，用 event group / notification 等全部完成再合併
- idle task 不綁核（IDLE0 不一定在 core 0）
critical section：
- `taskENTER_CRITICAL(); … taskEXIT_CRITICAL();`：SMP 下關本核 IRQ（BASEPRI，只擋數值 ≥ 0x10）+ 取跨核 spinlock，是全系統一把鎖 → 只放幾行，不可呼叫阻塞 API
- 較長操作（printf、走訪 list）用 mutex
- 陷阱：scheduler 啟動前在 main() 建立物件後，IRQ 可能一直被遮罩到 scheduler 啟動 ⚠️未驗證（讀碼推論）→ 硬體初始化放在建立物件前；需要 IRQ 或 sleep_ms 的初始化放進 task
裸機 → FreeRTOS：
- `multicore_launch_core1` → affinity task
- `multicore_fifo_*` → FreeRTOS queue / notification
- `spin_lock_blocking` / `critical_section_*` → `taskENTER_CRITICAL`（極短）或 mutex
- flag 輪詢 → `vTaskNotifyGiveFromISR` + `ulTaskNotifyTake`
- `add_repeating_timer_ms` → `xTaskDelayUntil` 週期 task 或軟體 timer
- pico `queue_t` / `mutex_t` 在 SYNC_INTEROP 下仍可用（FreeRTOS ↔ 非 FreeRTOS 時）

---

【參考卡｜FreeRTOS 7/8｜診斷與效能】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
平台：RP2350（Pico 2）FreeRTOS V11 SMP。
診斷：
- `uxTaskGetStackHighWaterMark(NULL)`：歷史最少剩餘 stack（words），越接近 0 越危險
- `xPortGetMinimumEverFreeHeapSize()`：判斷 heap 夠不夠
- 開 `configCHECK_FOR_STACK_OVERFLOW 2` 與 `configUSE_MALLOC_FAILED_HOOK 1` 就要實作 hook：
```c
void vApplicationStackOverflowHook(TaskHandle_t xTask, char *pcTaskName) {
    (void)xTask;
    panic("stack overflow: %s", pcTaskName);
}
void vApplicationMallocFailedHook(void) {
    panic("FreeRTOS heap exhausted");
}
```
run-time stats（RP2350 port 沒提供計數器）：
- `configGENERATE_RUN_TIME_STATS 1`、`configUSE_STATS_FORMATTING_FUNCTIONS 1`、`configUSE_TRACE_FACILITY 1`
- `#define portCONFIGURE_TIMER_FOR_RUN_TIME_STATS()`（空）
- `#define portGET_RUN_TIME_COUNTER_VALUE() ulAppRunTimeCounter()`，其中回傳 `time_us_32()`
- `vTaskGetRunTimeStatistics(buf, len)`、`vTaskListTasks(buf, len)`；buf 用 static
- 雙核整體使用率 ≈ 100% −（IDLE0% + IDLE1%）/ 2
優化順序：
1. 去忙等（改阻塞 API）
2. ISR 延後處理（ISR 只 notification，處理 task 高優先權）
3. 1 對 1 訊號改 notification；大資料傳指標或 stream buffer
4. 綁核（I/O 與運算分核）
5. 縮短臨界區，計算移出鎖外
6. 各核區域累加再合併
- 優化前後都量（Release build、同條件、多次取中位數）

---

【參考卡｜FreeRTOS 8/8｜常見錯誤（症狀 → 修法）】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
平台：RP2350（Pico 2）FreeRTOS SMP + pico-sdk。
| 症狀 | 原因 → 修法 |
|---|---|
| HardFault、變數被亂改 | task stack 太小 → 加大（words）、大陣列 static、開 stack 檢查 |
| task 沒建立、功能不動 | heap 不足沒檢查 → 檢查 != pdPASS、加大 heap |
| vTaskStartScheduler 之後的程式被執行 | heap 不足以建 idle/timer task |
| assert 在 vPortValidateInterruptPriority | 0x00 IRQ 呼叫 FromISR → 改 ≥ 0x10 |
| ISR 呼叫 xQueueSend 後當機 | 改 FromISR 版 + portYIELD_FROM_ISR |
| 中斷後 task 很久才反應 | 忘 portYIELD_FROM_ISR 或處理 task 優先權太低 |
| 低優先權 task 永遠不跑 | 高優先權 task 忙等 → 必須阻塞 |
| 週期漂移 | vTaskDelay → xTaskDelayUntil |
| vTaskDelay(pdMS_TO_TICKS(1)) 沒延遲 | tick 太低換算為 0 |
| 兩核計數偶爾少 | SMP 共享變數沒保護 → critical / mutex / 各自累加 |
| 卡死在兩個 mutex | 取鎖順序相反 → 固定順序、有限逾時 |
| scheduler 前呼叫 API 卡住 | main 中用了阻塞 API 或依賴 IRQ 的初始化 → 放進 task |
| core 1 異常 | 自己 multicore_launch_core1 或動 FIFO/OS spinlock |
| 在 core 1 啟動 scheduler 就 assert | 改 core 0 |
| assert 沒作用 | Release 帶 -DNDEBUG → Debug build 或改用 panic |
| 浮點偶爾錯 | 沒開 configENABLE_FPU |
| pvPortMalloc undefined | link FreeRTOS-Kernel-Heap4 |
| FreeRTOSConfig.h: No such file | target_include_directories 加目錄 |
| 多 task 寫同一 stream buffer 錯亂 | 只支援單寫入者 → 包 critical 或改 queue |
