# arsenal/：軍火庫（給模型照抄的參考）

小模型最常幻覺的是**函式名、參數順序、列舉值、常數、數字**。與其讓它憑記憶寫，不如給它驗證過的「參照物」照抄：

| 檔案 | 卡別 | 內容 | 怎麼驗證的 |
|---|---|---|---|
| `api-pico.md`（16 張） | API 卡 | pico-sdk 2.2.0 的 DMA、sniffer、PIO：完整函式簽名、參數順序、列舉名稱與數值、預設值、常見誤用 | 簽名從 SDK 標頭複製；所有函式寫進一個測試檔，pico2 編譯 0 錯誤 0 警告 |
| `api-sync-ros.md`（19 張） | API 卡 | 雙核 / 鎖 / queue、時間 / stdio / GPIO、micro-ROS rclc、rclpy、pyserial、struct | C 簽名從標頭複製並編譯；pyserial 用 inspect 核對；rclpy 只取範本裡實跑過的用法 |
| `snippets-pico.md`（19 張） | 片段卡 | Pico 端照抄就能用的程式：DMA 複製 / 填值、sniffer CRC32、DMA+PIO、PIO 初始化、雙核 pipeline、短臨界區、計時、序列埠收封包 | 全部放進測試專案編譯（pico2、SDK 2.2.0）；沒有在板子上跑 |
| `snippets-host.md`（23 張） | 片段卡 | 電腦端：序列埠批次傳送、多板平行與合併、rclpy node、micro-ROS 陣列收發、CRC / 排序 / SHA / BNN / 位元欄位、pthread 與 SPSC | Python 片段實跑（有板子的部分用 `fake_pico.py`）；C 片段編譯執行；rclpy 部分從範本複製 |
| `recipes-optimize.md`（16 張） | 食譜卡、提示卡 | 優化 0：現象 / 量測 → 食譜編號；每張食譜一種優化（修改前 / 修改後、量測方法、實測效果、陷阱）；「套用 1/1」提示卡 | 修改從說明書第 1～7 章已實測的食譜複製，套到副本上重新編譯 / 執行 |

每張卡 ≤ 1200 字元，可以單張貼給 context 小的模型。給 local model 一次載入用的合併版：`../print/06-軍火庫.md`（`python3 model/gen_catalog.py` 產生）。

## 怎麼用

**叫模型優化**（最常用）：
1. 開新對話貼 `model/00-總說明.md` 的總說明 1/3～3/3（或手動模式的 `cards/00-starter.md` 開場 1/3）。
2. 貼「食譜卡 優化 0」和你的量測（資料 S1），請它選食譜編號。
3. 貼那張食譜卡 → 模型回「收到」。
4. 貼「提示卡 套用 1/1」，填上你的程式（帶行號）和量測。
5. 照模型給的修改改、編譯、跑驗證和量測指令。沒變快就 `git checkout -- 檔案` 還原。

**叫模型寫新程式**（例如題目要用 DMA 搬資料）：
1. 貼對應的片段卡（例「片段卡 PICO-DMA 1」），再貼 API 卡（例「API卡 DMA 2」）。
2. 請它「照片段卡改，只換 <> 的值；用到的函式要能在 API 卡找到」。
3. 模型說的函式、參數順序和 API 卡對不上 → 以 API 卡為準。

**模型用【要卡】要卡片時**：名稱照 `model/01-資源目錄.md`（目錄卡），對照下表找檔案。

| 模型寫 | 去哪拿 |
|---|---|
| `API卡 DMA n`、`API卡 SNIFF n`、`API卡 PIO n` | `arsenal/api-pico.md` |
| `API卡 SYNC n`（雙核、queue、鎖）、`API卡 PICO-IO n`（時間、stdio、GPIO、CMake 庫名）、`API卡 UROS n`（rclc）、`API卡 HOST-PY n`（rclpy、pyserial、struct） | `arsenal/api-sync-ros.md` |
| `片段卡 PICO-DMA`、`PICO-SNIFF`、`PICO-DMAPIO`、`PICO-PIO`、`PICO-MC`、`PICO-TIME`、`PICO-SERIAL` | `arsenal/snippets-pico.md` |
| `片段卡 HOST-SERIAL`、`HOST-MULTI`、`HOST-ROS`、`HOST-UROS`、`ALGO`、`PERF` | `arsenal/snippets-host.md` |
| `食譜卡 優化 n`（0 = 選哪個）、`提示卡 套用 1/1` | `arsenal/recipes-optimize.md` |

注意同名系列：`規格卡 UROS`（範本規格）、`API卡 UROS`（rclc 簽名）、`片段卡 HOST-UROS`（程式片段）是不同的卡，看前面的卡別。

## 限制

- **沒有用 GPU 壓力測試過**；寫法照 `../README.md` 的 25 條規則。
- **只驗證到編譯 / 電腦上執行**：Pico 端片段都沒有在實體板子上跑過；rclpy 片段在這個容器沒有 ROS 2，是從之前在 Jazzy 容器跑過的範本複製的。
- **版本**：API 卡以 pico-sdk 2.2.0 為準（卡上有註明 2.1.1 的差異）。考場的版本先用 `grep VERSION_STRING build/generated/pico_base/pico/version.h` 確認，不同時以考場的 header 為準。
