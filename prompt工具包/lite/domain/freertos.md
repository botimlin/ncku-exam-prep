# FreeRTOS SMP on RP2350 速查（備援）

> 用途：考場若出現 `FreeRTOS.h`/`FreeRTOSConfig.h` 才用。適用 FreeRTOS-Kernel V11、RP2350 port（Community-Supported-Ports `GCC/RP2350_ARM_NTZ`、`RP2350_RISC-V`）、pico-sdk 2.3.1。
> 來源：github.com/FreeRTOS/FreeRTOS-Kernel、FreeRTOS-Kernel-Community-Supported-Ports、pico-examples/freertos。最後更新 2026-11。以考場 FreeRTOSConfig.h 為準。

## 核心規則
1. task 優先權**數字大=優先**（idle=0）；IRQ 優先權相反（0x00 最高）。
2. stack 單位 **words**（4 B）。有 printf 至少 512。
3. 不忙等：`xQueueReceive(q,&x,portMAX_DELAY)`、`ulTaskNotifyTake(pdTRUE,portMAX_DELAY)`。
4. 週期用 `xTaskDelayUntil(&last,pdMS_TO_TICKS(T))`（last 先設 `xTaskGetTickCount()`）；`vTaskDelay` 會漂移。
5. `pdMS_TO_TICKS` 捨去；tick 100Hz 時 <10ms 變 0。
6. SMP：`vTaskStartScheduler()` 在 **core 0** 呼叫，它自己 launch core1；**勿再 `multicore_launch_core1`**、勿動 spinlock OS1/OS2 與 doorbell（port 用，非 FIFO）。
7. SMP 下不同優先權 task、ISR 與 task 都可並行 → 共享資料必須保護。
8. `xTaskCreate` 成功=`pdPASS`，失敗回 -1；`xQueueCreate` 失敗回 NULL。都要檢查。

## CMake
```cmake
pico_sdk_init()
include(FreeRTOS_Kernel_import.cmake)  # 或 -DFREERTOS_KERNEL_PATH=
target_include_directories(app PRIVATE ${CMAKE_CURRENT_LIST_DIR}) # FreeRTOSConfig.h
target_link_libraries(app PRIVATE pico_stdlib FreeRTOS-Kernel-Heap4)
```
target：`FreeRTOS-Kernel`、`-Heap1..5`、`-Static`；上游 repo 要 init submodule。

## FreeRTOSConfig.h 重點
`configNUMBER_OF_CORES 2`、`configUSE_CORE_AFFINITY 1`、`configTICK_CORE 0`、`configUSE_PASSIVE_IDLE_HOOK 0`（SMP 必設）、`configRUN_MULTIPLE_PRIORITIES 1`（0=只同優先權並行）、`configTICK_RATE_HZ 1000`、`configTOTAL_HEAP_SIZE (128*1024)`、`configSUPPORT_PICO_SYNC_INTEROP 1`（task 內 `sleep_ms` 靠它讓出 CPU；`busy_wait_ms` 不會）、`configSUPPORT_PICO_TIME_INTEROP 1`、`configCHECK_FOR_STACK_OVERFLOW 2`、`configUSE_MALLOC_FAILED_HOOK 1`、`configASSERT(x)`（未設 build type 預設 Release，-DNDEBUG 使其失效）。RP2350 Arm 必設：`configENABLE_MPU 0`、`configENABLE_TRUSTZONE 0`、`configRUN_FREERTOS_SECURE_ONLY 1`、`configENABLE_FPU 1`、`configMAX_SYSCALL_INTERRUPT_PRIORITY 16`。

## API
- `xTaskCreate(fn,"n",words,arg,prio,&h)`；`xTaskCreateAffinitySet(...,prio,1u<<core,&h)`；`vTaskCoreAffinitySet(h,mask)`
- `vTaskDelete(NULL)`、`vTaskSuspend/Resume`、`taskYIELD()`、`portGET_CORE_ID()`
- queue：`xQueueCreate(len,size)`、`xQueueSend/Receive(q,p,ticks)`（複製資料；大資料傳指標）、`xQueueOverwrite`（長度 1）
- `xSemaphoreCreateBinary/Counting(max,init)/Mutex/RecursiveMutex`、`xSemaphoreTake(s,ticks)/Give`（Recursive 用 `TakeRecursive/GiveRecursive`）。mutex 有優先權繼承、**不可在 ISR**；互斥用 mutex，事件用 notification/binary。
- notification（官方：比 binary sem 快 45%，限 1 接收者）：`xTaskNotifyGive(h)`、`ulTaskNotifyTake(pdTRUE,t)`、`xTaskNotify(h,v,eSetBits)`、`xTaskNotifyWait(...)`
- event group：`xEventGroupWaitBits(g,bits,clear,all,t)`，bit 0–23；`SetBitsFromISR` 經 timer task（需 configUSE_TIMERS、INCLUDE_xTimerPendFunctionCall 為 1）。
- stream/message buffer：單寫單讀（多寫者包 critical+block 0）。
- 軟體 timer：`xTimerCreate("t",ticks,pdTRUE,id,cb)`+`xTimerStart(t,0)`；cb 在 `Tmr Svc` task，**不可阻塞**。
- `taskENTER/EXIT_CRITICAL()`：遮本核 IRQ（Arm BASEPRI 擋 ≥0x10；RISC-V 全關）+取 OS1/OS2 spinlock，全系統一把，只放幾行。ISR 版 `s=taskENTER_CRITICAL_FROM_ISR()`…`taskEXIT_CRITICAL_FROM_ISR(s)`

## ISR
```c
BaseType_t w=pdFALSE;
vTaskNotifyGiveFromISR(h,&w);   // 只能用 ...FromISR
portYIELD_FROM_ISR(w);
```
- （Arm）呼叫 API 的 IRQ 須 ≥0x10（預設 0x80 OK；0x00 禁用）。RISC-V：無巢狀、無 MAX_SYSCALL。
- IRQ 在哪核啟用就在哪核跑；handle 建好後才啟用。
- 陷阱：main() 首次建 task/queue 後 IRQ 被遮罩到第一個 task 跑 → 硬體初始化放建物件前；需 IRQ/sleep_ms 的放進 task。

## 裸機→RTOS
FIFO→queue；spin_lock→critical/mutex；repeating_timer→週期 task/軟體 timer；flag 輪詢→notification；launch_core1→affinity task。

## 診斷/效能
- `uxTaskGetStackHighWaterMark(NULL)`（剩餘 words）、`xPortGetMinimumEverFreeHeapSize()`
- run-time stats：`configGENERATE_RUN_TIME_STATS`/`USE_STATS_FORMATTING_FUNCTIONS`/`USE_TRACE_FACILITY` 設 1，`portGET_RUN_TIME_COUNTER_VALUE()`→`time_us_32()`（CONFIGURE 巨集留空）；`vTaskGetRunTimeStatistics(buf,len)` 看 IDLE0/1 %。
- 優化序：去忙等→ISR 延後處理→notification→綁核（I/O、運算分核）→縮短臨界區→各核區域累加。

## 常見錯
stack 爆（HardFault）、heap 不足沒檢查、ISR 用非 FromISR、0x00 IRQ 呼叫 API、忘 `portYIELD_FROM_ISR`、忙等餓死、共享變數沒鎖、deadlock（固定取鎖順序）、沒開 FPU、沒 link heap。
