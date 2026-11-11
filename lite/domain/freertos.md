# FreeRTOS SMP on RP2350 速查（備援）

> 用途：考場若出現 `FreeRTOS.h`/`FreeRTOSConfig.h` 才用。適用 FreeRTOS-Kernel V11、RP2350 port（Community-Supported-Ports `GCC/RP2350_ARM_NTZ`、`RP2350_RISC-V`）、pico-sdk 2.3.1。
> 來源：github.com/FreeRTOS/FreeRTOS-Kernel 標頭、FreeRTOS-Kernel-Community-Supported-Ports、pico-examples/freertos。最後更新 2026-11。以考場 FreeRTOSConfig.h 為準。

## 核心規則
1. task 優先權**數字大=優先**（idle=0）；IRQ 優先權相反（0x00 最高）。
2. stack 單位 **words**（4 B）。有 printf 至少 512。
3. 不忙等：`xQueueReceive(q,&x,portMAX_DELAY)`、`ulTaskNotifyTake(pdTRUE,portMAX_DELAY)`。
4. 週期用 `xTaskDelayUntil(&last,pdMS_TO_TICKS(T))`（last 先設 `xTaskGetTickCount()`）；`vTaskDelay` 會漂移。
5. `pdMS_TO_TICKS` 捨去；tick 100Hz 時 <10ms 變 0。
6. SMP：`vTaskStartScheduler()` 在 **core 0** 呼叫，它自己 launch core1；**勿再 `multicore_launch_core1`**、勿用 FIFO、勿動 spinlock OS1/OS2（kernel 用）。跨核 yield 用 doorbell。
7. SMP 下高低優先權 task 可同時跑、ISR 與 task 可並行 → 共享資料必須保護。
8. `xTaskCreate` 成功=`pdPASS`，失敗回 -1；`xQueueCreate` 失敗回 NULL。都要檢查。

## CMake
```cmake
pico_sdk_init()
include(FreeRTOS_Kernel_import.cmake)  # 或 -DFREERTOS_KERNEL_PATH=
target_include_directories(app PRIVATE ${CMAKE_CURRENT_LIST_DIR}) # FreeRTOSConfig.h
target_link_libraries(app PRIVATE pico_stdlib FreeRTOS-Kernel-Heap4)
```
target：`FreeRTOS-Kernel`（含 pico_multicore）、`-Heap1..5`、`-Static`。上游 repo 需 init submodule Community-Supported-Ports。

## FreeRTOSConfig.h 重點
`configNUMBER_OF_CORES 2`、`configUSE_CORE_AFFINITY 1`、`configRUN_MULTIPLE_PRIORITIES 1`（0=只同優先權並行）、`configTICK_RATE_HZ 1000`、`configTOTAL_HEAP_SIZE (128*1024)`、`configSUPPORT_PICO_SYNC_INTEROP 1`、`configSUPPORT_PICO_TIME_INTEROP 1`（task 內 `sleep_ms` 會讓出 CPU；`busy_wait_ms` 不會）、`configCHECK_FOR_STACK_OVERFLOW 2`、`configUSE_MALLOC_FAILED_HOOK 1`、`configASSERT(x)`（Release -DNDEBUG 會讓 assert 失效）。RP2350 Arm 必設：`configENABLE_MPU 0`、`configENABLE_TRUSTZONE 0`、`configRUN_FREERTOS_SECURE_ONLY 1`、`configENABLE_FPU 1`、`configMAX_SYSCALL_INTERRUPT_PRIORITY 16`。

## API
- `xTaskCreate(fn,"n",words,arg,prio,&h)`；`xTaskCreateAffinitySet(...,prio,1u<<core,&h)`；`vTaskCoreAffinitySet(h,mask)`
- `vTaskDelete(NULL)`、`vTaskSuspend/Resume`、`taskYIELD()`、`portGET_CORE_ID()`
- queue：`xQueueCreate(len,size)`、`xQueueSend/Receive(q,p,ticks)`（複製資料；大資料傳指標）、`xQueueOverwrite`（長度 1）
- `xSemaphoreCreateBinary/Counting(max,init)/Mutex/RecursiveMutex`、`xSemaphoreTake(s,ticks)/Give`。mutex 有 priority inheritance、**不可在 ISR**；互斥用 mutex，事件用 notification/binary。
- notification（最快，官方：比 binary sem 快 45%，只限 1 個接收者）：`xTaskNotifyGive(h)`、`ulTaskNotifyTake(pdTRUE,t)`、`xTaskNotify(h,v,eSetBits)`、`xTaskNotifyWait(...)`
- event group：`xEventGroupWaitBits(g,bits,clear,all,t)`，可用 bit 0–23；`SetBitsFromISR` 經 timer task（需 configUSE_TIMERS）。
- stream/message buffer：單寫單讀。
- 軟體 timer：`xTimerCreate("t",ticks,pdTRUE,id,cb)`+`xTimerStart(t,0)`；cb 在 `Tmr Svc` task，**不可阻塞**。
- `taskENTER/EXIT_CRITICAL()`：SMP=關本核 IRQ(BASEPRI)+取跨核 spinlock，全系統一把，只放幾行。ISR 用 `s=taskENTER_CRITICAL_FROM_ISR(); taskEXIT_CRITICAL_FROM_ISR(s);`

## ISR
```c
BaseType_t w=pdFALSE;
vTaskNotifyGiveFromISR(h,&w);   // 只能用 ...FromISR
portYIELD_FROM_ISR(w);
```
- 呼叫 API 的 IRQ 優先權須 ≥0x10（SDK 預設 0x80 OK；0x00 禁用 API）。
- IRQ 在哪核啟用就在哪核跑；handle 建好後才啟用。
- 陷阱：SMP 在 scheduler 啟動前建物件後中斷被遮罩（讀碼推論 ⚠️未驗證）→ 等待類初始化放進 task。

## 裸機→RTOS
FIFO→queue；spin_lock→critical/mutex；repeating_timer→週期 task/軟體 timer；flag 輪詢→notification；launch_core1→affinity task。

## 診斷/效能
- `uxTaskGetStackHighWaterMark(NULL)`（剩餘 words）、`xPortGetMinimumEverFreeHeapSize()`
- run-time stats：`configGENERATE_RUN_TIME_STATS 1`+`configUSE_STATS_FORMATTING_FUNCTIONS 1`+`configUSE_TRACE_FACILITY 1`，自訂 `portCONFIGURE_TIMER_FOR_RUN_TIME_STATS()`（空）與 `portGET_RUN_TIME_COUNTER_VALUE()`→`time_us_32()`；`vTaskGetRunTimeStatistics(buf,len)`，看 IDLE0/IDLE1 %。
- 優化序：去忙等→ISR 延後處理→notification→綁核（I/O 與運算分核）→縮短臨界區→各核區域累加。

## 常見錯
stack 爆（HardFault）、heap 不足沒檢查、ISR 用非 FromISR、IRQ 優先權 0x00 呼叫 API、忘 `portYIELD_FROM_ISR`、高優先權忙等餓死、SMP 共享變數沒鎖、deadlock（固定取鎖順序）、沒開 `configENABLE_FPU`、只 link Kernel 沒 heap。
